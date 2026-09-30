from pathlib import Path

import pytest

from payment_python_tests.config.contract_loader import load_contract
from payment_python_tests.mocks import MockMerchantServer, MockPppServer
from payment_python_tests.ai.assistant import analyze_failure, generate_contract_draft
from payment_python_tests.reports.report_builder import build_markdown_report
from payment_python_tests.services.evidence_service import EvidenceStore
from payment_python_tests.services.validation_service import (
    validate_channel_payload,
    validate_outbound_request,
)
from payment_python_tests.utils.redact_utils import redact
from payment_python_tests.utils.sign_utils import hmac_sha256_sorted_values


ROOT = Path(__file__).parents[1]


def test_ppp_contract_and_common_validation():
    contract = load_contract(ROOT / "contracts" / "ppp.yaml")
    assert contract.map_status("success") == "SUCCESS"
    assert not validate_channel_payload(contract, {"merchantOrderId": "o-1", "transactionId": "t-1", "amount": "100.00"}, local_order_no="o-1", local_amount_minor=10000, local_channel_order_no="t-1")
    issues = validate_channel_payload(contract, {"merchantOrderId": "other", "transactionId": "t-2", "amount": "99.99"}, local_order_no="o-1", local_amount_minor=10000, local_channel_order_no="t-1")
    assert {issue.code for issue in issues} == {"ORDER_MISMATCH", "AMOUNT_MISMATCH", "CHANNEL_ORDER_MISMATCH"}


def test_mock_servers_are_order_scoped():
    ppp = MockPppServer().start()
    merchant = MockMerchantServer().start()
    try:
        ppp.configure("o-1", query_status="success")
        assert ppp.url.startswith("http://127.0.0.1:")
        assert merchant.records == []
    finally:
        ppp.close()
        merchant.close()


def test_evidence_and_failure_analysis(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.db")
    try:
        store.record("callback", {"status": "success"}, "o-1")
        result = analyze_failure(store.records("o-1"))
        assert "商户通知" in result["summary"]
    finally:
        store.close()


def test_ai_contract_draft_is_reviewable():
    draft = generate_contract_draft([{ "merchantOrderId": "o-1", "transactionId": "t-1", "amount": "100.00", "status": "pending"}], channel="newpay")
    assert draft["channel"] == "newpay"
    assert draft["signature"]["algorithm"] == "REVIEW_REQUIRED"


def test_markdown_report_contains_evidence_summary():
    report = build_markdown_report([{"created_at": "2026-09-30T00:00:00Z", "kind": "database", "order_no": "o-1", "payload": {"trade_state": 2}}])
    assert "支付通道自动化证据报告" in report
    assert "database: 1" in report


def test_ppp_outbound_request_values_match_sources_and_signature():
    contract = load_contract(ROOT / "contracts" / "ppp.yaml")
    context = {
        "merchant": {
            "inrQuantity": "10000",
            "bankCardNo": "602801536155",
            "bankCode": "PUNB0027120",
            "mobileNumber": "9770038888",
            "bankAccount": "Test User",
        },
        "database": {"orderNo": "PPP-ORDER-001"},
        "channel_config": {"payMerchant": "merchant-001", "pin": "test-pin"},
    }
    body = {
        "amount": "100.00",
        "currencyKey": "inr",
        "customerAccNo": "602801536155",
        "customerEmail": "WLT20260930_1234567@gmail.com",
        "customerIfsc": "PUNB0027120",
        "customerMobile": "9770038888",
        "customerName": "Test User",
        "merchantIdentifier": "merchant-001",
        "merchantOrderId": "PPP-ORDER-001",
        "transactionModeKey": "imps",
    }
    body["hash"] = hmac_sha256_sorted_values(body, "test-secret")
    record = {"method": "POST", "path": "/v1/payouts/", "headers": {"Authorization": "Bearer test-pin", "Content-Type": "application/json"}, "body": body}

    assert not validate_outbound_request(contract, record, context, signing_secret="test-secret")


def test_ppp_outbound_request_finds_wrong_mapping_and_forbidden_field():
    contract = load_contract(ROOT / "contracts" / "ppp.yaml")
    context = {
        "merchant": {"inrQuantity": "10000", "bankCardNo": "correct", "bankCode": "IFSC", "mobileNumber": "13800000000", "bankAccount": "User"},
        "database": {"orderNo": "ORDER-1"},
        "channel_config": {"payMerchant": "merchant-1", "pin": "pin-1"},
    }
    record = {"method": "POST", "headers": {"Authorization": "Bearer wrong", "Content-Type": "application/json"}, "body": {"amount": "99.99", "currencyKey": "usd", "customerAccNo": "wrong", "customerEmail": "invalid", "customerIfsc": "IFSC", "customerMobile": "13800000000", "customerName": "User", "merchantIdentifier": "merchant-1", "merchantOrderId": "ORDER-1", "transactionModeKey": "imps", "notifyUrl": "must-not-send", "hash": "wrong"}}
    codes = {issue.code for issue in validate_outbound_request(contract, record, context, signing_secret="secret")}

    assert {"REQUEST_VALUE_MISMATCH", "FORMAT_MISMATCH", "FORBIDDEN_FIELD_PRESENT", "HEADER_VALUE_MISMATCH"} <= codes


def test_ai_failure_analysis_mentions_missing_outbound_evidence():
    result = analyze_failure([{"kind": "merchant_request", "order_no": "o-1", "payload": {}}])
    assert "出站请求" in result["summary"]


def test_ppp_query_outbound_path_uses_saved_transaction_id():
    contract = load_contract(ROOT / "contracts" / "ppp.yaml")
    context = {"database": {"transactionId": "txn-001"}, "channel_config": {"pin": "test-pin"}}
    record = {"method": "GET", "path": "/v1/payouts/status/txn-001", "body": {}, "headers": {"Authorization": "Bearer test-pin", "Content-Type": "application/json"}}
    assert not validate_outbound_request(contract, record, context, operation="query")
    record["path"] = "/v1/payouts/status/other-order"
    assert any(issue.code == "PATH_MISMATCH" for issue in validate_outbound_request(contract, record, context, operation="query"))


def test_redaction_hides_sensitive_outbound_data_without_mutating_original():
    record = {"headers": {"Authorization": "Bearer private"}, "body": {"customerAccNo": "123456", "customerMobile": "987654", "merchantOrderId": "o-1", "hash": "secret-hash"}}
    sanitized = redact(record)
    assert sanitized["headers"]["Authorization"] == "***"
    assert sanitized["body"]["customerAccNo"] == "***"
    assert sanitized["body"]["merchantOrderId"] == "o-1"
    assert record["body"]["customerAccNo"] == "123456"
