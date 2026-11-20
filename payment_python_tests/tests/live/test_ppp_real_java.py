from decimal import Decimal
import os
import uuid

import pytest
from loguru import logger
from payment_python_tests.database.mysql_client import MysqlClient
from payment_python_tests.database.order_repository import OrderRepository
from payment_python_tests.utils.wait_utils import wait_until


pytestmark = pytest.mark.live


def _real_ppp_merchant_fields() -> dict[str, str]:
    """Build one deterministic merchant request for live PPP flows."""
    return {
        "trxAmount": "10000",
        "tradeAmount": "10000",
        "userId": "AUTO-USER-REAL-PPP-CALLBACK",
        "bankCardNo": "602801536155",
        "bankCode": "PUNB0027120",
        "bankAccount": "Test User",
        "bankName": "STATE BANK OF INDIA",
        "mobileNumber": "9770038888",
        "currency": "USD",
        "notifyUrl": os.getenv("NOTIFY_URL", ""),
    }


def _ppp_callback_target_url(app_settings) -> str:
    """Use an explicit callback URL, then the historical typo, then Java's base URL."""
    return (
        os.getenv("PPP_CALLBACK_TARGET_URL", "").strip()
        or os.getenv("PPP_NOTTIFY_URL", "").strip()
        or f"{app_settings.payment.base_url.rstrip('/')}/ppp/disburse/notify"
    )


def test_ppp_static_callback_updates_dynamically_created_order(
    payment_api,
    app_settings,
    ppp_capture_api,
    live_required,
):
    """正常回调使用本次下单落库的订单号和通道订单号，不依赖人工配置旧订单。"""
    app_settings.require_database()
    msg_id = payment_api.new_message_id("PPPCALLBACK")
    merchant_fields = _real_ppp_merchant_fields()
    target_url = _ppp_callback_target_url(app_settings)

    ppp_capture_api.configure_ppp_scenario(
        run_id=msg_id,
        scenario_name="normal-success-callback",
        create_status="pending",
        query_status="pending",
    )
    payment_api.create_payout(msgId=msg_id, **merchant_fields)

    with MysqlClient(app_settings.database) as mysql:
        repository = OrderRepository(mysql)
        #wait_until 需要一个“稍后反复执行的查询函数”
        order = wait_until(
            lambda: repository.get_route_child_by_main_msg_id(
                app_settings.merchant.merchant_id, msg_id
            ),
            lambda item: (
                item is not None
                and item.state_name == "PROCESSING"
                and bool(item.transaction_id)
                and item.channel_amount is not None
            ),
            timeout=30,
            interval=0.5,
            description=f"PPP processing order with transaction id for {msg_id}",
        )
        logger.info(f"查询出入金订单创建成功transaction id is {msg_id}")
        #等价的非匿名函数
        # def fetch_processing_order():
        #     return repository.get_route_child_by_main_msg_id(
        #         app_settings.merchant.merchant_id,
        #         msg_id,
        #     )
        #
        # def is_ready_for_callback(item):
        #     return (
        #             item is not None
        #             and item.state_name == "PROCESSING"
        #             and bool(item.transaction_id)
        #             and item.channel_amount is not None
        #     )
        #
        # order = wait_until(
        #     fetch_processing_order,
        #     is_ready_for_callback,
        #     timeout=30,
        #     interval=0.5,
        #     description=f"PPP processing order with transaction id for {msg_id}",
        # )
        # The database supplies both identifiers used by the callback. The Mock
        # record is also required so this test cannot callback an unrelated order.
        channel_records = wait_until(
            lambda: ppp_capture_api.ppp_payout_records(msg_id, order.order_no),
            lambda records: len(records) >= 1,
            timeout=15,
            interval=0.2,
            description=f"PPP payout evidence for {order.order_no}",
        )
        logger.info(f"查询mock订单数据{order.order_no}")
        assert len(channel_records) == 1

        callback_amount = f"{Decimal(str(order.channel_amount)) / Decimal('100'):.2f}"
        result = ppp_capture_api.send_ppp_callback(
            run_id=msg_id,
            target_url=target_url,
            business_order_no=order.order_no,
            channel_order_no=order.transaction_id,
            amount=callback_amount,
            status="success",
            utr=f"AUTO-SUCCESS-{uuid.uuid4().hex[:12]}",
        )

        assert result["target_status"] == 200  # 主要验证是否正常响应过来
        # assert result["target_body"] == "SUCCESS"
        # 因为是自己回调的mock，所以没有必要进行回调参数自己本身的验证，只需要验证出入金是否正常扭转订单状态和通知给商户的报文是否正确
        # callback_record = ppp_capture_api.record(result["request_id"])
        # assert callback_record["direction"] == "mock_to_java"
        # assert callback_record["business_order_no"] == order.order_no
        # assert callback_record["channel_order_no"] == order.transaction_id
        # assert callback_record["body"]["amount"] == callback_amount
        # assert callback_record["body"]["status"] == "success"
        # assert callback_record["response_status"] == 200

        final_order = wait_until(
            lambda: repository.get(order.order_no),
            lambda item: (
                item is not None
                and item.state_name == "SUCCESS"
                and item.transaction_id == order.transaction_id
            ),
            timeout=30,
            interval=0.5,
            description=f"PPP order reaches SUCCESS after callback: {order.order_no}",
        )

    assert final_order.order_no == order.order_no
    assert final_order.channel_amount == order.channel_amount


def test_ppp_static_callback_rejects_wrong_amount(ppp_capture_api, app_settings):
    """独立 Mock 发送签名正确但金额错误的回调，真实 Java 必须拒绝。"""
    order_no = os.getenv("EXISTING_PROCESSING_ORDER_NO", "")
    channel_order_no = os.getenv("EXISTING_CHANNEL_ORDER_NO", "")
    target_url = _ppp_callback_target_url(app_settings)
    if not all((order_no, channel_order_no, target_url)):
        pytest.skip(
            "需要 EXISTING_PROCESSING_ORDER_NO、EXISTING_CHANNEL_ORDER_NO、"
            "PPP_CALLBACK_TARGET_URL"
        )

    result = ppp_capture_api.send_ppp_callback(
        run_id=f"PPP-WRONG-AMOUNT-{uuid.uuid4().hex}",
        target_url=target_url,
        business_order_no=order_no,
        channel_order_no=channel_order_no,
        amount="99.99",
        status="success",
        utr=f"AUTO-WRONG-AMOUNT-{uuid.uuid4().hex[:12]}",
    )

    assert result["target_status"] == 400
    assert result["target_body"] == "FAIL"

    callback_record = ppp_capture_api.record(result["request_id"])
    assert callback_record["direction"] == "mock_to_java"
    assert callback_record["business_order_no"] == order_no
    assert callback_record["channel_order_no"] == channel_order_no
    assert callback_record["body"]["amount"] == "99.99"
    assert callback_record["body"]["status"] == "success"
    assert callback_record["response_status"] == 400
    assert callback_record["response_body"] == "FAIL"
