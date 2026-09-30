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
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS evidence (id INTEGER PRIMARY KEY, created_at TEXT, kind TEXT, order_no TEXT, payload TEXT)")
        self.conn.commit()

    def record(self, kind: str, payload: Any, order_no: str = "") -> None:
        self.conn.execute("INSERT INTO evidence(created_at, kind, order_no, payload) VALUES (?, ?, ?, ?)", (datetime.now(timezone.utc).isoformat(), kind, order_no, json.dumps(payload, ensure_ascii=False, default=str)))
        self.conn.commit()

    def records(self, order_no: str = "") -> list[dict[str, Any]]:
        query = "SELECT created_at, kind, order_no, payload FROM evidence"
        args: tuple[Any, ...] = ()
        if order_no:
            query += " WHERE order_no = ?"
            args = (order_no,)
        return [{"created_at": a, "kind": b, "order_no": c, "payload": json.loads(d)} for a, b, c, d in self.conn.execute(query, args)]

    def export_json(self, path: str | Path, order_no: str = "") -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.records(order_no), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return target

    def close(self) -> None:
        self.conn.close()
