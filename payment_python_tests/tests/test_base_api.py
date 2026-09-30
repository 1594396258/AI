from __future__ import annotations

from typing import Any

import pytest

from payment_python_tests.api.base_api import BaseApi


class FakeResponse:
    status_code = 200
    text = '{"ok": true}'

    def json(self):
        return {"ok": True}


class FakeSession:
    def __init__(self):
        self.headers: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    ("method_name", "expected_method"),
    [
        ("get", "GET"),
        ("post", "POST"),
        ("put", "PUT"),
        ("delete", "DELETE"),
        ("patch", "PATCH"),
    ],
)
def test_base_api_wraps_http_methods(method_name, expected_method):
    session = FakeSession()
    client = BaseApi("http://example.test/api", timeout=12, session=session)

    getattr(client, method_name)("orders", json={"orderNo": "o-1"})

    call = session.calls[0]
    assert call["method"] == expected_method
    assert call["url"] == "http://example.test/api/orders"
    assert call["timeout"] == 12


def test_base_api_manages_shared_headers_and_session():
    session = FakeSession()
    client = BaseApi("http://example.test", session=session)
    client.set_token("token-1")
    client.set_header("X-Test", "yes")
    client.close()

    assert session.headers["Authorization"] == "Bearer token-1"
    assert session.headers["X-Test"] == "yes"
    assert session.closed is True
