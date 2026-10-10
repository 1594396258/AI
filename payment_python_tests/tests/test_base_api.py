from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from payment_python_tests.api.base_api import BaseApi
from payment_python_tests.api.payment_api import PaymentApi
from payment_python_tests.utils.sign_utils import compact_json


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


class FakeSettings:
    def __init__(self, *, response_public_key: str = ""):
        self.payment = SimpleNamespace(
            base_url="http://example.test/v1",
            timeout=10,
            disburse_service="pay.cbtis.disburse",
            query_service="unified.disburse.query",
        )
        self.merchant = SimpleNamespace(
            merchant_id="merchant-1",
            private_key="private-key",
            response_public_key=response_public_key,
        )

    def require_live_payment(self):
        return None


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


def test_payment_packet_signs_the_same_order_that_is_sent(monkeypatch):
    signed = {}

    def fake_sign(data, private_key):
        signed["data"] = data
        signed["private_key"] = private_key
        return "signature"

    monkeypatch.setattr(
        "payment_python_tests.api.payment_api.rsa_sha256_sign", fake_sign
    )
    client = PaymentApi(FakeSettings())
    try:
        packet = client.build_merchant_packet(
            "pay.example.disburse",
            msgId="AUTO001",
            zField="last",
            aField="first",
        )
    finally:
        client.close()

    assert list(packet["request"]) == sorted(packet["request"])
    assert signed["data"] == compact_json(packet["request"])
    assert signed["private_key"] == "private-key"


def test_payment_response_verifies_nested_response_object(monkeypatch):
    verified = {}

    def fake_verify(data, signature, public_key):
        verified.update(data=data, signature=signature, public_key=public_key)
        return True

    monkeypatch.setattr(
        "payment_python_tests.api.payment_api.rsa_sha256_verify", fake_verify
    )
    client = PaymentApi(FakeSettings(response_public_key="public-key"))
    try:
        client.verify_merchant_response(
            {
                "response": {"code": "200", "message": "ok"},
                "signature": "response-signature",
            }
        )
    finally:
        client.close()

    assert verified == {
        "data": '{"code":"200","message":"ok"}',
        "signature": "response-signature",
        "public_key": "public-key",
    }


def test_payment_business_methods_use_global_merchant_services():
    calls = []
    client = PaymentApi(FakeSettings())

    def fake_post_merchant(path, service, **fields):
        calls.append((path, service, fields))
        return {"ok": True}

    client.post_merchant = fake_post_merchant
    try:
        client.create_payout(msgId="ORDER001", amount="100")
        client.query_payout("ORDER001")
    finally:
        client.close()

    assert calls == [
        (
            "disburse",
            "pay.cbtis.disburse",
            {"msgId": "ORDER001", "amount": "100"},
        ),
        (
            "disburse/query",
            "unified.disburse.query",
            {"originalMsgId": "ORDER001"},
        ),
    ]
