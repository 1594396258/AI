from __future__ import annotations

import time
import uuid
from typing import Any

import requests

from .evidence import EvidenceStore
from .signing import compact_json, rsa_sha256_sign, rsa_sha256_verify
from .settings import Settings


class PaymentClient:
    def __init__(self, settings: Settings, evidence: EvidenceStore | None = None):
        self.settings = settings
        self.evidence = evidence

    def new_message_id(self, prefix: str = "AUTO") -> str:
        return f"{prefix}{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"

    def merchant_packet(self, service: str, **fields: Any) -> dict[str, Any]:
        self.settings.require_live_payment()
        request_data = {"msgId": fields.pop("msgId", self.new_message_id()), "mchId": self.settings.merchant_id, "service": service, **fields}
        signature = rsa_sha256_sign(compact_json(request_data), self.settings.merchant_private_key)
        return {"request": request_data, "signature": signature}

    def post_merchant(self, path: str, service: str, **fields: Any) -> dict[str, Any]:
        packet = self.merchant_packet(service, **fields)
        order_no = str(fields.get("orderNo") or fields.get("originalMsgId") or packet["request"]["msgId"])
        if self.evidence:
            self.evidence.record("merchant_request", {"path": path, "request": packet["request"]}, order_no)
        response = requests.post(f"{self.settings.payment_base_url}/{path.lstrip('/')}", json=packet, timeout=self.settings.request_timeout)
        response.raise_for_status()
        result = response.json()
        if self.evidence:
            self.evidence.record("java_response", result, order_no)
        self._verify_response(result)
        return result

    def create_payout(self, service: str, **fields: Any) -> dict[str, Any]:
        return self.post_merchant("disburse", service, **fields)

    def query_payout(self, service: str, original_msg_id: str) -> dict[str, Any]:
        return self.post_merchant("disburse/query", service, originalMsgId=original_msg_id)

    def send_callback(self, service: str, order_no: str, payload: dict[str, Any]) -> requests.Response:
        url = f"{self.settings.payment_base_url}/disburse/notifyv2/{service}@{order_no}"
        if self.evidence:
            self.evidence.record("channel_callback", payload, order_no)
        response = requests.post(url, json=payload, timeout=self.settings.request_timeout)
        if self.evidence:
            self.evidence.record("callback_ack", {"status_code": response.status_code, "text": response.text}, order_no)
        return response

    def send_static_callback(self, path: str, order_no: str, payload: dict[str, Any]) -> requests.Response:
        """Send webhooks such as PPP whose URL does not carry the order number."""
        url = f"{self.settings.payment_base_url}/{path.lstrip('/')}"
        if self.evidence:
            self.evidence.record("channel_callback", payload, order_no)
        response = requests.post(url, json=payload, timeout=self.settings.request_timeout)
        if self.evidence:
            self.evidence.record("callback_ack", {"status_code": response.status_code, "text": response.text}, order_no)
        return response

    def healthcheck(self) -> None:
        response = requests.get(self.settings.payment_base_url.rsplit("/v1", 1)[0] + "/actuator/health", timeout=min(self.settings.request_timeout, 5))
        response.raise_for_status()

    def _verify_response(self, result: dict[str, Any]) -> None:
        if not self.settings.response_public_key:
            return
        response_data = result.get("response")
        signature = result.get("signature")
        if not isinstance(response_data, str) or not isinstance(signature, str):
            raise AssertionError("Java 响应缺少 response/signature，无法验签")
        if not rsa_sha256_verify(response_data, signature, self.settings.response_public_key):
            raise AssertionError("Java 商户响应签名校验失败")
