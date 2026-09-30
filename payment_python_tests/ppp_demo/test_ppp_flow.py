import pytest

from .system import FakePaymentSystem, LocalState, MerchantSink, PppChannelMock


def make_system(merchant_fail_times=0):
    channel = PppChannelMock(secret="demo-secret")
    merchant = MerchantSink(fail_times=merchant_fail_times)
    return FakePaymentSystem(channel, merchant), channel, merchant


def test_full_flow_disburse_query_success_and_notify_once():
    system, channel, merchant = make_system()
    order = system.disburse("ORDER-001")
    assert order.state == LocalState.PROCESSING

    channel.set_status("ORDER-001", "success")
    system.query("ORDER-001")

    assert order.state == LocalState.SUCCESS
    assert order.notify_success is True
    assert order.notify_count == 1
    assert merchant.received[0]["trxState"] == "SUCCESS"


def test_callback_success_changes_state_and_notifies_merchant():
    system, channel, merchant = make_system()
    order = system.disburse("ORDER-002")

    ack = system.receive_callback(channel.build_callback("ORDER-002", "success"))

    assert ack == "SUCCESS"
    assert order.state == LocalState.SUCCESS
    assert len(merchant.received) == 1


def test_duplicate_callback_is_idempotent():
    system, channel, merchant = make_system()
    system.disburse("ORDER-003")
    callback = channel.build_callback("ORDER-003", "success")

    assert system.receive_callback(callback) == "SUCCESS"
    assert system.receive_callback(callback) == "SUCCESS"
    assert system.orders["ORDER-003"].notify_count == 1
    assert len(merchant.received) == 1


def test_invalid_signature_does_not_change_order():
    system, channel, merchant = make_system()
    order = system.disburse("ORDER-004")
    callback = channel.build_callback("ORDER-004", "success")
    callback["status"] = "failed"

    assert system.receive_callback(callback) == "FAIL"
    assert order.state == LocalState.PROCESSING
    assert merchant.received == []


def test_failed_callback_changes_state_and_notifies_failure():
    system, channel, merchant = make_system()
    order = system.disburse("ORDER-005")

    assert system.receive_callback(channel.build_callback("ORDER-005", "failed")) == "SUCCESS"
    assert order.state == LocalState.FAIL
    assert merchant.received[0]["trxState"] == "FAIL"


def test_success_then_failed_is_review_not_automatic_reversal():
    system, channel, merchant = make_system()
    order = system.disburse("ORDER-006")
    assert system.receive_callback(channel.build_callback("ORDER-006", "success")) == "SUCCESS"

    assert system.receive_callback(channel.build_callback("ORDER-006", "failed")) == "SUCCESS"
    assert order.state == LocalState.SUCCESS
    assert order.reversal_review_created is True
    assert order.notify_count == 1


def test_merchant_notification_is_retried_after_failure():
    system, channel, _ = make_system(merchant_fail_times=1)
    order = system.disburse("ORDER-007")
    system.receive_callback(channel.build_callback("ORDER-007", "success"))

    assert order.notify_success is False
    assert order.notify_count == 1
    assert system.retry_merchant_notification("ORDER-007") is True
    assert order.notify_success is True
    assert order.notify_count == 2


@pytest.mark.parametrize(
    ("channel_status", "local_state"),
    [
        ("pending", LocalState.PROCESSING),
        ("disputed", LocalState.PROCESSING),
        ("success", LocalState.SUCCESS),
        ("failed", LocalState.FAIL),
    ],
)
def test_ppp_status_mapping(channel_status, local_state):
    system, channel, _ = make_system()
    system.disburse("ORDER-MATRIX")
    channel.set_status("ORDER-MATRIX", channel_status)
    system.query("ORDER-MATRIX")

    assert system.orders["ORDER-MATRIX"].state == local_state
