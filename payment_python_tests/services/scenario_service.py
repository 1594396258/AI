from __future__ import annotations

from typing import Any

from payment_python_tests.api.payment_api import PaymentApi
from payment_python_tests.database.order_repository import OrderRepository
from payment_python_tests.models.channel_contract import ChannelContract
from payment_python_tests.models.order import OrderSnapshot
from payment_python_tests.services.evidence_service import EvidenceStore
from payment_python_tests.utils.redact_utils import redact
from payment_python_tests.utils.wait_utils import wait_until


class PayoutScenario:
    def __init__(
        self,
        contract: ChannelContract,
        payment_api: PaymentApi,
        order_repository: OrderRepository,
        evidence: EvidenceStore,
    ):
        self.contract = contract
        self.payment_api = payment_api
        self.order_repository = order_repository
        self.evidence = evidence

    def wait_order_state(
        self, order_no: str, expected: str, timeout: float = 30
    ) -> OrderSnapshot:
        snapshot = wait_until(
            lambda: self.order_repository.get(order_no),
            lambda order: order is not None and order.state_name == expected,
            timeout=timeout,
            description=f"order {order_no} to enter {expected}",
        )
        self.evidence.record("database", snapshot.raw, order_no)
        return snapshot

    @staticmethod
    def assert_identity_and_amount(
        order: OrderSnapshot, *, channel_order_no: str, amount_minor: int
    ) -> None:
        assert order.transaction_id == channel_order_no
        assert int(order.channel_amount or -1) == amount_minor

    @staticmethod
    def merchant_notice_count(
        records: list[dict[str, Any]], order_no: str
    ) -> int:
        return sum(
            1
            for item in records
            if isinstance(item.get("body"), dict)
            and (
                item["body"].get("orderNo") == order_no
                or item["body"].get("originalMsgId") == order_no
            )
        )

    def record_channel_requests(
        self, records: list[dict[str, Any]], order_no: str = ""
    ) -> None:
        for record in records:
            self.evidence.record("channel_request", redact(record), order_no)
