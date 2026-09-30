from __future__ import annotations

from typing import Any

from payment_python_tests.mocks.http_mock import MockHttpServer


class MockPppServer(MockHttpServer):
    def __init__(self, *, port: int = 0):
        self.behaviors: dict[str, dict[str, Any]] = {}
        super().__init__(self._respond, port=port)

    def configure(
        self,
        order_no: str,
        *,
        create_status: str = "pending",
        query_status: str = "success",
        amount: str = "100.00",
        transaction_id: str | None = None,
    ) -> None:
        self.behaviors[order_no] = {
            "create_status": create_status,
            "query_status": query_status,
            "amount": amount,
            "transaction_id": transaction_id or f"ppp-{order_no}",
        }

    def _respond(self, record: dict[str, Any]) -> dict[str, Any]:
        body = record["body"] if isinstance(record["body"], dict) else {}
        query = record.get("query", {})
        order_no = (
            body.get("merchantOrderId")
            or body.get("orderNo")
            or body.get("originalMsgId")
            or (query.get("merchantOrderId") or query.get("orderNo") or [""])[0]
        )
        if not order_no and record["method"] == "GET":
            transaction_id = record["path"].rstrip("/").rsplit("/", 1)[-1]
            order_no = next(
                (
                    key
                    for key, value in self.behaviors.items()
                    if value["transaction_id"] == transaction_id
                ),
                "",
            )
            if not order_no and transaction_id.startswith("ppp-"):
                order_no = transaction_id.removeprefix("ppp-")
        behavior = self.behaviors.get(
            order_no,
            {
                "create_status": "pending",
                "query_status": "success",
                "amount": "100.00",
                "transaction_id": f"ppp-{order_no}",
            },
        )
        is_query = record["method"] == "GET"
        return {
            "status": behavior["query_status"] if is_query else behavior["create_status"],
            "merchantOrderId": order_no,
            "transactionId": behavior["transaction_id"],
            "amount": behavior["amount"],
        }
