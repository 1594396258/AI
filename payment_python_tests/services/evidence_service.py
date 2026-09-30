from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EvidenceStore:
    def __init__(self, path: str | Path = "artifacts/evidence.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS evidence "
            "(id INTEGER PRIMARY KEY, created_at TEXT, kind TEXT, "
            "order_no TEXT, payload TEXT)"
        )
        self.connection.commit()

    def record(self, kind: str, payload: Any, order_no: str = "") -> None:
        self.connection.execute(
            "INSERT INTO evidence(created_at, kind, order_no, payload) "
            "VALUES (?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                kind,
                order_no,
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )
        self.connection.commit()

    def records(self, order_no: str = "") -> list[dict[str, Any]]:
        query = "SELECT created_at, kind, order_no, payload FROM evidence"
        params: tuple[Any, ...] = ()
        if order_no:
            query += " WHERE order_no = ?"
            params = (order_no,)
        rows = self.connection.execute(query, params)
        return [
            {
                "created_at": created_at,
                "kind": kind,
                "order_no": current_order_no,
                "payload": json.loads(payload),
            }
            for created_at, kind, current_order_no, payload in rows
        ]

    def export_json(self, path: str | Path, order_no: str = "") -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                self.records(order_no), ensure_ascii=False, indent=2, default=str
            ),
            encoding="utf-8",
        )
        return target

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "EvidenceStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
