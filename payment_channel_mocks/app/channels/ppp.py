from __future__ import annotations

import time
from typing import Any

from payment_channel_mocks.app.core.storage import ExchangeStore


class PppChannel:
    """The small protocol-specific part of the PPP mock."""

    name = "ppp"

    def __init__(self, store: ExchangeStore):
        self.store = store

    @staticmethod
    def _delay(config: dict[str, Any]) -> None:
        delay_ms = max(0, min(int(config.get("delay_ms", 0)), 60_000))
        if delay_ms:
            time.sleep(delay_ms / 1000)

    def payout(
        self, body: dict[str, Any], config: dict[str, Any]
    ) -> tuple[int, dict[str, Any], str, str]:
        self._delay(config)
        order_no = str(body.get("merchantOrderId") or "")
        if not order_no:
            return 400, {"error": "merchantOrderId is required"}, "", ""
        channel_order_no = str(
            config.get("transaction_id") or f"ppp-{order_no}"
        )
        amount = config.get("amount")
        if amount is None:
            amount = body.get("amount", "")
        response = {
            "status": config.get("create_status", "pending"),
            "merchantOrderId": order_no,
            "transactionId": channel_order_no,
            "amount": str(amount),
        }
        return (
            int(config.get("response_status_code", 200)),
            response,
            order_no,
            channel_order_no,
        )

    def query(
        self, transaction_id: str, config: dict[str, Any]
    ) -> tuple[int, dict[str, Any], str, str]:
        self._delay(config)
        payout = self.store.find_by_channel_order_no(self.name, transaction_id)
        if payout:
            order_no = payout["business_order_no"]
            original_response = payout["response_body"]
            original_amount = (
                original_response.get("amount")
                if isinstance(original_response, dict)
                else None
            )
        else:
            return (
                404,
                {"statusCode": "404", "error": "Unknown transactionId"},
                "",
                transaction_id,
            )
        amount = config.get("amount")
        if amount is None:
            amount = original_amount if original_amount is not None else "100.00"
        response = {
            "status": config.get("query_status", "success"),
            "merchantOrderId": order_no,
            "transactionId": transaction_id,
            "amount": str(amount),
        }
        return (
            int(config.get("response_status_code", 200)),
            response,
            str(order_no),
            transaction_id,
        )

