"""Backward-compatible payment API client."""

from typing import Any

import requests

from payment_python_tests.api.payment_api import PaymentApi


class PaymentClient(PaymentApi):
    merchant_packet = PaymentApi.build_merchant_packet

    def send_callback(
        self, service: str, order_no: str, payload: dict[str, Any]
    ) -> requests.Response:
        return self.send_dynamic_callback(service, order_no, payload)


__all__ = ["PaymentClient"]
