import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from payment_python_tests.api.payment_api import PaymentApi
from payment_python_tests.config.contract_loader import load_contract
from payment_python_tests.config.settings import AppSettings
from payment_python_tests.services.evidence_service import EvidenceStore
from payment_python_tests.utils.sign_utils import hmac_sha256_sorted_values


ROOT = Path(__file__).parents[2]
load_dotenv(ROOT / ".env")


pytestmark = pytest.mark.live


@pytest.fixture
def live_context(tmp_path):
    if os.getenv("RUN_LIVE_TESTS", "false").lower() != "true":
        pytest.skip("设置 RUN_LIVE_TESTS=true 后才会调用真实 Java")
    settings = AppSettings.from_env()
    settings.require_live_payment()
    evidence = EvidenceStore(tmp_path / "evidence.db")
    yield settings, load_contract(ROOT / "contracts" / "ppp.yaml"), evidence
    evidence.close()


def test_ppp_static_callback_rejects_wrong_amount(live_context):
    """教学样例：填入已存在的处理中订单后，错误金额必须被 PPP webhook 拒绝。"""
    settings, contract, evidence = live_context
    order_no = os.getenv("EXISTING_PROCESSING_ORDER_NO", "")
    channel_order_no = os.getenv("EXISTING_CHANNEL_ORDER_NO", "")
    secret = os.getenv("PPP_TEST_SECRET", "")
    if not all((order_no, channel_order_no, secret)):
        pytest.skip("需要 EXISTING_PROCESSING_ORDER_NO、EXISTING_CHANNEL_ORDER_NO、PPP_TEST_SECRET")

    payload = {
        "status": "success",
        "merchantOrderId": order_no,
        "transactionId": channel_order_no,
        "amount": "99.99",
        "utr": "AUTO-WRONG-AMOUNT",
    }
    payload["hash"] = hmac_sha256_sorted_values(payload, secret)
    with PaymentApi(settings, evidence) as payment_api:
        response = payment_api.send_static_callback(
            contract.callback["endpoint"], order_no, payload
        )

    assert response.status_code == 400
    assert response.text == "FAIL"
