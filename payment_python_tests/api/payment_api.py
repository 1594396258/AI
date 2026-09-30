from __future__ import annotations

import time
import uuid
from typing import Any, Protocol

import requests

from payment_python_tests.api.base_api import BaseApi
from payment_python_tests.config.settings import AppSettings
from payment_python_tests.utils.redact_utils import redact
from payment_python_tests.utils.sign_utils import compact_json, rsa_sha256_sign, rsa_sha256_verify


class EvidenceRecorder(Protocol):
    def record(self, kind: str, payload: Any, order_no: str = "") -> None: ...


class PaymentApi(BaseApi):
    """Merchant-facing client for the real Java payment service."""

    def __init__(self, settings: AppSettings, evidence: EvidenceRecorder | None = None):
        super().__init__(settings.payment.base_url, settings.payment.timeout)
        self.settings = settings
        self.evidence = evidence

    @staticmethod
    def new_message_id(prefix: str = "AUTO") -> str:
        return f"{prefix}{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"

    def build_merchant_packet(self, service: str, **fields: Any) -> dict[str, Any]:
        self.settings.require_live_payment()
        request_data = {
            "msgId": fields.pop("msgId", self.new_message_id()),
            "mchId": self.settings.merchant.merchant_id,
            "service": service,
            **fields,
        }
        signature = rsa_sha256_sign(
            compact_json(request_data), self.settings.merchant.private_key
        )
        return {"request": request_data, "signature": signature}

    def post_merchant(self, path: str, service: str, **fields: Any) -> dict[str, Any]:
        packet = self.build_merchant_packet(service, **fields)
        evidence_order = str(
            fields.get("orderNo")
            or fields.get("originalMsgId")
            or packet["request"]["msgId"]
        )
        if self.evidence:
            self.evidence.record(
                "merchant_request",
                redact({"path": path, "request": packet["request"]}),
                evidence_order,
            )
        response = self.post(path, json=packet)
        response.raise_for_status()
        result = response.json()
        if self.evidence:
            self.evidence.record("java_response", redact(result), evidence_order)
        self.verify_merchant_response(result)
        return result

    def create_payout(self, service: str, **fields: Any) -> dict[str, Any]:
        return self.post_merchant("disburse", service, **fields)

    def query_payout(self, service: str, original_msg_id: str) -> dict[str, Any]:
        return self.post_merchant(
            "disburse/query", service, originalMsgId=original_msg_id
        )

    def send_dynamic_callback(
        self, service: str, order_no: str, payload: dict[str, Any]
    ) -> requests.Response:
        return self._send_callback(
            f"disburse/notifyv2/{service}@{order_no}", order_no, payload
        )

    def send_static_callback(
        self, path: str, order_no: str, payload: dict[str, Any]
    ) -> requests.Response:
        return self._send_callback(path, order_no, payload)

    def _send_callback(
        self, path: str, order_no: str, payload: dict[str, Any]
    ) -> requests.Response:
        if self.evidence:
            self.evidence.record("channel_callback", redact(payload), order_no)
        response = self.post(path, json=payload)
        if self.evidence:
            self.evidence.record(
                "callback_ack",
                {"status_code": response.status_code, "text": response.text},
                order_no,
            )
        return response

    def healthcheck(self) -> requests.Response:
        health_url = self.settings.payment.base_url.rsplit("/v1", 1)[0]
        with BaseApi(health_url, min(self.settings.payment.timeout, 5)) as client:
            response = client.get("actuator/health")
            response.raise_for_status()
            return response

    def verify_merchant_response(self, result: dict[str, Any]) -> None:
        public_key = self.settings.merchant.response_public_key
        if not public_key:
            return
        response_data = result.get("response")
        signature = result.get("signature")
        if not isinstance(response_data, str) or not isinstance(signature, str):
            raise AssertionError("Java response has no response/signature fields")
        if not rsa_sha256_verify(response_data, signature, public_key):
            raise AssertionError("Java merchant response signature verification failed")
