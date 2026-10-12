from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class ExchangeStore:
    """SQLite persistence for active scenarios and complete HTTP exchanges."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS active_scenario (
                    channel TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    scenario_name TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS scenario_history (
                    channel TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    scenario_name TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (channel, run_id)
                );

                CREATE TABLE IF NOT EXISTS mock_exchange_record (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE,
                    channel TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    method TEXT NOT NULL,
                    request_url TEXT NOT NULL DEFAULT '',
                    path TEXT NOT NULL,
                    query_json TEXT NOT NULL,
                    request_headers_json TEXT NOT NULL,
                    request_body_json TEXT NOT NULL,
                    response_status INTEGER NOT NULL,
                    response_headers_json TEXT NOT NULL,
                    response_body_json TEXT NOT NULL,
                    business_order_no TEXT,
                    channel_order_no TEXT,
                    scenario_name TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    request_hash TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    elapsed_ms INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_exchange_run
                    ON mock_exchange_record(run_id);
                CREATE INDEX IF NOT EXISTS idx_exchange_order
                    ON mock_exchange_record(business_order_no);
                CREATE INDEX IF NOT EXISTS idx_exchange_channel_order
                    ON mock_exchange_record(channel_order_no);
                CREATE INDEX IF NOT EXISTS idx_exchange_created
                    ON mock_exchange_record(created_at);
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(mock_exchange_record)")}
            if "request_url" not in columns:
                connection.execute("ALTER TABLE mock_exchange_record ADD COLUMN request_url TEXT NOT NULL DEFAULT ''")

    def set_scenario(
        self,
        *,
        channel: str,
        run_id: str,
        scenario_name: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        updated_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO scenario_history(
                    channel, run_id, scenario_name, config_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(channel, run_id) DO UPDATE SET
                    scenario_name=excluded.scenario_name,
                    config_json=excluded.config_json,
                    updated_at=excluded.updated_at
                """,
                (channel, run_id, scenario_name, json_text(config), updated_at),
            )
            connection.execute(
                """
                INSERT INTO active_scenario(
                    channel, run_id, scenario_name, config_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(channel) DO UPDATE SET
                    run_id=excluded.run_id,
                    scenario_name=excluded.scenario_name,
                    config_json=excluded.config_json,
                    updated_at=excluded.updated_at
                """,
                (channel, run_id, scenario_name, json_text(config), updated_at),
            )
        return {
            "channel": channel,
            "run_id": run_id,
            "scenario_name": scenario_name,
            "config": config,
            "updated_at": updated_at,
        }

    def get_scenario(self, channel: str, run_id: str = "") -> dict[str, Any]:
        with self._connect() as connection:
            if run_id:
                row = connection.execute(
                    "SELECT * FROM scenario_history WHERE channel = ? AND run_id = ?",
                    (channel, run_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM active_scenario WHERE channel = ?", (channel,)
                ).fetchone()
        if row is None:
            return {
                "channel": channel,
                "run_id": run_id or "unassigned",
                "scenario_name": "default",
                "config": {},
            }
        return {
            "channel": row["channel"],
            "run_id": row["run_id"],
            "scenario_name": row["scenario_name"],
            "config": json.loads(row["config_json"]),
            "updated_at": row["updated_at"],
        }

    def record_exchange(
        self,
        *,
        request_id: str,
        run_id: str,
        channel: str,
        direction: str,
        method: str,
        path: str,
        query: dict[str, Any],
        request_headers: dict[str, Any],
        request_body: Any,
        response_status: int,
        response_headers: dict[str, Any],
        response_body: Any,
        business_order_no: str = "",
        channel_order_no: str = "",
        request_url: str = "",
        scenario_name: str = "default",
        started_at: str,
        finished_at: str,
        elapsed_ms: int,
    ) -> int:
        request_hash = hashlib.sha256(
            json.dumps(
                {
                    "method": method,
                    "path": path,
                    "query": query,
                    "body": request_body,
                },
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        with self._connect() as connection:
            # Reserve the write transaction before counting; concurrent retries
            # must not receive the same attempt number.
            connection.execute("BEGIN IMMEDIATE")
            attempt_no = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM mock_exchange_record
                    WHERE run_id = ? AND channel = ? AND direction = ?
                      AND method = ? AND path = ? AND business_order_no = ?
                    """,
                    (
                        run_id,
                        channel,
                        direction,
                        method,
                        path,
                        business_order_no,
                    ),
                ).fetchone()[0]
            ) + 1
            cursor = connection.execute(
                """
                INSERT INTO mock_exchange_record(
                    run_id, request_id, channel, direction, method, request_url, path,
                    query_json, request_headers_json, request_body_json,
                    response_status, response_headers_json, response_body_json,
                    business_order_no, channel_order_no, scenario_name,
                    attempt_no, request_hash, started_at, finished_at,
                    elapsed_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    request_id,
                    channel,
                    direction,
                    method,
                    request_url,
                    path,
                    json_text(query),
                    json_text(request_headers),
                    json_text(request_body),
                    response_status,
                    json_text(response_headers),
                    json_text(response_body),
                    business_order_no,
                    channel_order_no,
                    scenario_name,
                    attempt_no,
                    request_hash,
                    started_at,
                    finished_at,
                    elapsed_ms,
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def list_records(
        self,
        *,
        run_id: str = "",
        channel: str = "",
        business_order_no: str = "",
        direction: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("run_id", run_id),
            ("channel", channel),
            ("business_order_no", business_order_no),
            ("direction", direction),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(limit, 1000)))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM mock_exchange_record"
                + where
                + " ORDER BY id ASC LIMIT ?",
                params,
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def find_by_channel_order_no(
        self, channel: str, channel_order_no: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM mock_exchange_record
                WHERE channel = ? AND channel_order_no = ?
                  AND direction = 'java_to_mock' AND method = 'POST'
                ORDER BY id DESC LIMIT 1
                """,
                (channel, channel_order_no),
            ).fetchone()
        return self._record_from_row(row) if row else None

    def get_record(self, request_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM mock_exchange_record WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return self._record_from_row(row) if row else None

    def find_payout_by_order(
        self, channel: str, business_order_no: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM mock_exchange_record
                WHERE channel = ? AND business_order_no = ?
                  AND direction = 'java_to_mock' AND method = 'POST'
                ORDER BY id DESC LIMIT 1
                """,
                (channel, business_order_no),
            ).fetchone()
        return self._record_from_row(row) if row else None

    def delete_records(self, run_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM mock_exchange_record WHERE run_id = ?", (run_id,)
            )
            return int(cursor.rowcount)

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "request_id": row["request_id"],
            "channel": row["channel"],
            "direction": row["direction"],
            "method": row["method"],
            "url": row["request_url"],
            "path": row["path"],
            "query": json.loads(row["query_json"]),
            "headers": json.loads(row["request_headers_json"]),
            "body": json.loads(row["request_body_json"]),
            "response_status": row["response_status"],
            "response_headers": json.loads(row["response_headers_json"]),
            "response_body": json.loads(row["response_body_json"]),
            "business_order_no": row["business_order_no"],
            "channel_order_no": row["channel_order_no"],
            "scenario_name": row["scenario_name"],
            "attempt_no": row["attempt_no"],
            "request_hash": row["request_hash"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "elapsed_ms": row["elapsed_ms"],
            "created_at": row["created_at"],
        }

