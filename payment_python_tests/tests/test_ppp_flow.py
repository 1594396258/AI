import base64
import json
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def merchant_request(settings, service, **fields):
    """构造商户侧请求；签名规则与 Java 商户测试保持 SHA256withRSA。"""
    request = {
        "msgId": f"pytest-{int(time.time() * 1000)}",
        "mchId": settings["mch_id"],
        "service": service,
        **fields,
    }
    private_key_text = settings["mch_private_key"]
    if not private_key_text:
        return {"request": request, "signature": "REPLACE_WITH_TEST_SIGNATURE"}
    private_key = serialization.load_der_private_key(
        base64.b64decode(private_key_text), password=None
    )
    request_text = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
    signature = private_key.sign(
        request_text.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
    )
    return {"request": request, "signature": base64.b64encode(signature).decode()}


def post_json(settings, path, body):
    response = requests.post(
        f"{settings['base_url']}/{path.lstrip('/')}",
        json=body,
        timeout=settings["timeout"],
    )
    response.raise_for_status()
    return response.json()


def test_disburse_returns_business_response(settings, live_required):
    body = merchant_request(
        settings,
        settings["service"],
        trxAmount="100",
        amount="10000",
        currency="USD",
        bankCardNo="TEST_ACCOUNT",
        bankCode="TEST_BANK",
        bankAccount="Test User",
        notifyUrl=settings["notify_url"],
    )
    result = post_json(settings, "/disburse", body)

    assert isinstance(result, dict)
    assert "response" in result or "code" in result


def test_disburse_query_returns_business_response(settings, live_required):
    body = merchant_request(
        settings,
        settings["query_service"],
        originalMsgId=settings["order_no"],
    )
    result = post_json(settings, "/disburse/query", body)

    assert isinstance(result, dict)
    assert "response" in result or "code" in result


def test_callback_rejects_malformed_route(settings, live_required):
    response = requests.post(
        f"{settings['base_url']}/disburse/notifyv2/not-a-valid-route",
        json={"status": "success"},
        timeout=settings["timeout"],
    )

    assert response.status_code < 500
