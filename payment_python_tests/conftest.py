from pathlib import Path

import pytest
from dotenv import load_dotenv

from payment_python_tests.api.payment_api import PaymentApi
from payment_python_tests.config.contract_loader import load_contract
from payment_python_tests.config.settings import AppSettings
from payment_python_tests.services.evidence_service import EvidenceStore


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")


@pytest.fixture(scope="session")
def app_settings() -> AppSettings:
    return AppSettings.from_env()


@pytest.fixture(scope="session")
def ppp_contract():
    return load_contract(PROJECT_DIR / "contracts" / "ppp.yaml")


@pytest.fixture
def evidence_store(tmp_path):
    store = EvidenceStore(tmp_path / "evidence.db")
    yield store
    store.close()


@pytest.fixture
def payment_api(app_settings, evidence_store):
    client = PaymentApi(app_settings, evidence_store)
    yield client
    client.close()


@pytest.fixture
def settings(app_settings, ppp_contract):
    """Legacy dictionary fixture retained for the original example tests."""
    return {
        "base_url": app_settings.payment.base_url,
        "mch_id": app_settings.merchant.merchant_id,
        "mch_private_key": app_settings.merchant.private_key,
        "service": ppp_contract.service,
        "query_service": ppp_contract.query_service,
        "order_no": "",
        "notify_url": "",
        "timeout": app_settings.payment.timeout,
    }


@pytest.fixture
def live_required(settings, app_settings):
    required = ["base_url", "mch_id", "service", "query_service"]
    missing = [name for name in required if not settings[name]]
    if missing or not app_settings.runtime.run_live_tests:
        pytest.skip("未启用真实测试，请配置 .env 并设置 RUN_LIVE_TESTS=true")
