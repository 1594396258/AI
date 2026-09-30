from __future__ import annotations

from typing import Any

from .contracts import ChannelContract
from .database import MysqlOrderRepository, OrderSnapshot
from .evidence import EvidenceStore
from .payment_client import PaymentClient
from .redaction import redact
from .waiting import wait_until


class PayoutScenario:
    """Business-readable facade over HTTP, callback, database, and evidence steps."""

    def __init__(self, contract: ChannelContract, payment: PaymentClient, orders: MysqlOrderRepository, evidence: EvidenceStore):
        self.contract = contract
        self.payment = payment
        self.orders = orders
        self.evidence = evidence

    def wait_order_state(self, order_no: str, expected: str, timeout: float = 30) -> OrderSnapshot:
        snapshot = wait_until(lambda: self.orders.get(order_no), lambda order: order is not None and order.state_name == expected, timeout=timeout, description=f"订单 {order_no} 进入 {expected}")
        self.evidence.record("database", snapshot.raw, order_no)
        return snapshot

    def assert_identity_and_amount(self, order: OrderSnapshot, *, channel_order_no: str, amount_minor: int) -> None:
        assert order.transaction_id == channel_order_no, f"通道订单号不一致: DB={order.transaction_id}, expected={channel_order_no}"
        assert int(order.channel_amount or -1) == amount_minor, f"通道金额不一致: DB={order.channel_amount}, expected={amount_minor}"

    def merchant_notice_count(self, records: list[dict[str, Any]], order_no: str) -> int:
        return sum(1 for item in records if isinstance(item.get("body"), dict) and (item["body"].get("orderNo") == order_no or item["body"].get("originalMsgId") == order_no))

    def record_channel_requests(self, records: list[dict[str, Any]], order_no: str = "") -> None:
        for record in records:
            self.evidence.record("channel_request", redact(record), order_no)
