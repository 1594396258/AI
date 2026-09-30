"""一个可独立运行的 PPP 代付链路教学模型。

真实项目中，FakePaymentSystem 会替换成 requests 调用 Java 服务；
PppChannelMock 会替换成 WireMock/MockServer。
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LocalState(str, Enum):
    INIT = "INIT"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


def ppp_sign_plain_text(values: dict[str, Any]) -> str:
    """PPP: key ASCII 排序，只拼 value，空值保留位置，排除 hash。"""
    return "|".join("" if values[key] is None else str(values[key])
                    for key in sorted(values)
                    if key != "hash")


def ppp_hmac(values: dict[str, Any], secret: str) -> str:
    text = ppp_sign_plain_text(values)
    return hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()


@dataclass
class Order:
    order_no: str
    amount: str
    state: LocalState = LocalState.INIT
    notify_count: int = 0
    notify_success: bool = False
    merchant_notifications: list[dict[str, Any]] = field(default_factory=list)
    reversal_review_created: bool = False


class MerchantSink:
    """模拟商户 notifyUrl；fail_times 用于测试通知重试。"""

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.received: list[dict[str, Any]] = []

    def receive(self, body: dict[str, Any]) -> bool:
        self.received.append(body)
        if self.fail_times > 0:
            self.fail_times -= 1
            return False
        return True


class PppChannelMock:
    """模拟 PPP 三方接口，只保存通道状态，不实现真实网络。"""

    def __init__(self, secret: str = "ppp-test-secret"):
        self.secret = secret
        self.status_by_order: dict[str, str] = {}

    def create_payout(self, order_no: str) -> dict[str, Any]:
        self.status_by_order[order_no] = "pending"
        return {"status": "pending", "orderId": f"PPP-{order_no}"}

    def query_payout(self, order_no: str) -> dict[str, Any]:
        status = self.status_by_order.get(order_no)
        if status is None:
            return {"statusCode": "404", "error": "payment is not exist"}
        return {"status": status, "orderId": f"PPP-{order_no}"}

    def set_status(self, order_no: str, status: str) -> None:
        self.status_by_order[order_no] = status

    def build_callback(self, order_no: str, status: str) -> dict[str, Any]:
        body = {
            "orderId": order_no,
            "status": status,
            "message": f"PPP {status}",
            "amount": "100.00",
        }
        body["hash"] = ppp_hmac(body, self.secret)
        return body


class FakePaymentSystem:
    """模拟平台公共链路：下单、查询、回调、商户通知和幂等。"""

    def __init__(self, channel: PppChannelMock, merchant: MerchantSink):
        self.channel = channel
        self.merchant = merchant
        self.orders: dict[str, Order] = {}

    def disburse(self, order_no: str, amount: str = "100.00") -> Order:
        order = Order(order_no=order_no, amount=amount)
        self.orders[order_no] = order
        response = self.channel.create_payout(order_no)
        self._apply_channel_status(order, response["status"])
        return order

    def query(self, order_no: str) -> Order:
        order = self.orders[order_no]
        response = self.channel.query_payout(order_no)
        if "status" in response:
            self._apply_channel_status(order, response["status"])
        return order

    def receive_callback(self, body: dict[str, Any]) -> str:
        order_no = body.get("orderId")
        order = self.orders.get(order_no)
        if order is None or not self._verify_callback(body):
            return "FAIL"

        status = body.get("status")
        # PPP 成功单收到迟到 failed：保留成功，创建人工审核证据。
        if order.state == LocalState.SUCCESS and status == "failed":
            order.reversal_review_created = True
            return "SUCCESS"

        if order.state in {LocalState.SUCCESS, LocalState.FAIL}:
            return "SUCCESS"  # 重复回调只 ACK，不重复落库/通知

        self._apply_channel_status(order, status)
        return "SUCCESS"

    def retry_merchant_notification(self, order_no: str) -> bool:
        order = self.orders[order_no]
        if order.notify_success:
            return True
        return self._notify_merchant(order)

    def _verify_callback(self, body: dict[str, Any]) -> bool:
        received = body.get("hash")
        expected = ppp_hmac(body, self.channel.secret)
        return bool(received) and hmac.compare_digest(received, expected)

    def _apply_channel_status(self, order: Order, status: str) -> None:
        if status in {"pending", "disputed"}:
            if order.state == LocalState.INIT:
                order.state = LocalState.PROCESSING
            return
        if status == "success":
            if order.state in {LocalState.INIT, LocalState.PROCESSING}:
                order.state = LocalState.SUCCESS
                self._notify_merchant(order)
            return
        if status == "failed":
            if order.state in {LocalState.INIT, LocalState.PROCESSING}:
                order.state = LocalState.FAIL
                self._notify_merchant(order)
            return
        raise ValueError(f"unknown PPP status: {status}")

    def _notify_merchant(self, order: Order) -> bool:
        if order.notify_success:
            return True
        body = {
            "orderNo": order.order_no,
            "trxState": order.state.value,
            "trxAmount": order.amount,
        }
        order.notify_count += 1
        order.merchant_notifications.append(body)
        order.notify_success = self.merchant.receive(body)
        return order.notify_success
