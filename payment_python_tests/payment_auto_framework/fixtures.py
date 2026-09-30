from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


class RecordedHandler(BaseHTTPRequestHandler):
    records: list[dict[str, Any]] = []
    response_factory = None

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            body: Any = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = raw.decode("utf-8", errors="replace")
        record = {"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body}
        type(self).records.append(record)
        response = type(self).response_factory(record) if type(self).response_factory else {"code": "SUCCESS"}
        encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        record = {"method": "GET", "path": parsed.path, "query": parse_qs(parsed.query), "headers": dict(self.headers), "body": {}}
        type(self).records.append(record)
        response = type(self).response_factory(record) if type(self).response_factory else {"code": "SUCCESS"}
        encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_: Any) -> None:
        return


class MockHttpServer:
    def __init__(self, response_factory=None):
        self.handler = type(f"Handler{uuid.uuid4().hex}", (RecordedHandler,), {})
        self.handler.records = []
        self.handler.response_factory = response_factory
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    @property
    def records(self) -> list[dict[str, Any]]:
        return self.handler.records

    def last_record(self, method: str | None = None) -> dict[str, Any] | None:
        records = self.records if method is None else [item for item in self.records if item.get("method") == method]
        return records[-1] if records else None

    def start(self) -> "MockHttpServer":
        self.thread.start()
        return self

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class MockPppServer(MockHttpServer):
    def __init__(self):
        self.behaviors: dict[str, dict[str, Any]] = {}
        super().__init__(self._respond)

    def configure(self, order_no: str, *, create_status: str = "pending", query_status: str = "success", amount: str = "100.00") -> None:
        self.behaviors[order_no] = {"create_status": create_status, "query_status": query_status, "amount": amount, "transaction_id": f"ppp-{order_no}"}

    def _respond(self, record: dict[str, Any]) -> dict[str, Any]:
        body = record["body"] if isinstance(record["body"], dict) else {}
        query = record.get("query", {})
        order_no = body.get("merchantOrderId") or body.get("orderNo") or body.get("originalMsgId") or (query.get("merchantOrderId") or query.get("orderNo") or [""])[0]
        if not order_no and record["method"] == "GET":
            transaction_id = record["path"].rstrip("/").rsplit("/", 1)[-1]
            order_no = next((key for key, value in self.behaviors.items() if value["transaction_id"] == transaction_id), "")
        behavior = self.behaviors.get(order_no, {"create_status": "pending", "query_status": "success", "amount": "100.00", "transaction_id": f"ppp-{order_no}"})
        is_query = record["method"] == "GET" or "query" in record["path"].lower() or "originalMsgId" in body
        return {"status": behavior["query_status"] if is_query else behavior["create_status"], "merchantOrderId": order_no, "transactionId": behavior["transaction_id"], "amount": behavior["amount"]}


class MockMerchantServer(MockHttpServer):
    pass
