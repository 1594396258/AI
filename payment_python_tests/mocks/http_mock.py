from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


ResponseFactory = Callable[[dict[str, Any]], dict[str, Any]]


class RecordedHandler(BaseHTTPRequestHandler):
    records: list[dict[str, Any]] = []
    response_factory: ResponseFactory | None = None

    def _read_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return raw.decode("utf-8", errors="replace")

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        body = self._read_body() if method in {"POST", "PUT", "PATCH"} else {}
        record = {
            "method": method,
            "path": parsed.path,
            "query": parse_qs(parsed.query),
            "headers": dict(self.headers),
            "body": body,
        }
        type(self).records.append(record)
        factory = type(self).response_factory
        response = factory(record) if factory else {"code": "SUCCESS"}
        status_code = int(response.pop("__status_code__", 200))
        encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle("PATCH")

    def log_message(self, *_: Any) -> None:
        return


class MockHttpServer:
    def __init__(
        self, response_factory: ResponseFactory | None = None, *, port: int = 0
    ):
        self.handler = type(f"Handler{uuid.uuid4().hex}", (RecordedHandler,), {})
        self.handler.records = []
        self.handler.response_factory = response_factory
        self.server = ThreadingHTTPServer(("127.0.0.1", port), self.handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    @property
    def records(self) -> list[dict[str, Any]]:
        return self.handler.records

    def last_record(self, method: str | None = None) -> dict[str, Any] | None:
        records = (
            self.records
            if method is None
            else [item for item in self.records if item.get("method") == method]
        )
        return records[-1] if records else None

    def start(self) -> "MockHttpServer":
        self.thread.start()
        return self

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def __enter__(self) -> "MockHttpServer":
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.close()
