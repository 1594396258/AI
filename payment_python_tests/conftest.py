import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from payment_python_tests.api.payment_api import PaymentApi
from payment_python_tests.api.mock_admin_api import MockAdminApi
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
def mock_admin_api(app_settings):
    client = MockAdminApi(
        app_settings.mock_service.base_url,
        app_settings.mock_service.timeout,
        admin_token=app_settings.mock_service.admin_token,
    )
    yield client
    client.close()


@pytest.fixture
def live_enabled(app_settings):
    if not app_settings.runtime.run_live_tests:
        pytest.skip(
            "RUN_LIVE_TESTS 当前解析为 false；请在 payment_python_tests/.env "
            "中配置 RUN_LIVE_TESTS=true（行尾注释前需要空格）"
        )


@pytest.fixture
def ppp_capture_api(live_enabled, app_settings, mock_admin_api):
    """Return the HTTP client for the separately running PPP request capture."""
    if os.getenv("PPP_MOCK_ENABLED", "false").strip().lower() != "true":
        pytest.skip("设置 PPP_MOCK_ENABLED=true 后才会校验 Java 的真实 PPP 请求")

    try:
        mock_admin_api.health()
    except Exception as exc:
        pytest.fail(
            f"无法连接独立 Mock 服务 {app_settings.mock_service.base_url}：{exc}；"
            r"请先运行 .\payment_channel_mocks\start.ps1"
        )

    return mock_admin_api


@pytest.fixture
def live_required(live_enabled, app_settings):
    missing = []
    if not app_settings.payment.base_url:
        missing.append("PAYMENT_BASE_URL")
    if not app_settings.merchant.merchant_id:
        missing.append("MCH_ID")
    if not app_settings.merchant.private_key:
        missing.append("MCH_PRIVATE_KEY")
    if not app_settings.payment.disburse_service:
        missing.append("payment.disburse_service")
    if not app_settings.payment.query_service:
        missing.append("payment.query_service")
    if missing:
        pytest.skip("真实测试缺少配置：" + ", ".join(missing))
