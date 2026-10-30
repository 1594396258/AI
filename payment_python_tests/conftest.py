import os
import re
from pathlib import Path
from pprint import pformat

import pytest
from dotenv import load_dotenv

from payment_python_tests.api.payment_api import PaymentApi
from payment_python_tests.api.mock_admin_api import MockAdminApi
from payment_python_tests.config.contract_loader import load_contract
from payment_python_tests.config.settings import AppSettings
from payment_python_tests.services.evidence_service import EvidenceStore

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:authorization|api[_-]?key|access[_-]?token|token|secret|"
    r"password|private[_-]?key|signature|hash)\b\s*[:=]\s*)[^\s,;]+"
)
_BEARER_TOKEN = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/-]+=*")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){12,19}(?!\d)")


def _redact_ai_text(value: str) -> str:
    value = _BEARER_TOKEN.sub(r"\1***", value)
    value = _SENSITIVE_ASSIGNMENT.sub(r"\1***", value)
    value = _EMAIL.sub("***@***", value)
    return _LONG_NUMBER.sub("***", value)


def _ai_failure_record(item, report) -> dict[str, str]:
    crash = getattr(report.longrepr, "reprcrash", None)  # report.longrepr 是 pytest 的失败表示，可能包含 traceback 和断言失败信息
    message = getattr(crash, "message", "") or str(report.longrepr) #优先取 report.longrepr.reprcrash.message，也就是失败摘要；取不到时才用整个 longrepr 的字符串形式
    description = getattr(getattr(item, "obj", None), "__doc__", "") or ""
    return {
        "kind": "pytest_failure",
        "test": item.originalname or item.name,
        "description": _redact_ai_text(description.strip()[:1000]),
        "phase": report.when,
        "failure": _redact_ai_text(message[:2000]),
    }


def _debug_report_attributes(item, report) -> None:
    item_attributes = {
        "type": type(item).__name__,
        "name": getattr(item, "name", None),
        "originalname": getattr(item, "originalname", None),
        "nodeid": getattr(item, "nodeid", None),
        "location": getattr(item, "location", None),
        "test_function": repr(getattr(item, "obj", None)),
        "fixtures": list(getattr(item, "fixturenames", [])),
        "markers": [marker.name for marker in item.iter_markers()],
    }
    longrepr = getattr(report, "longrepr", None)
    report_attributes = {
        "type": type(report).__name__,
        "nodeid": getattr(report, "nodeid", None),
        "location": getattr(report, "location", None),
        "when": getattr(report, "when", None),
        "outcome": getattr(report, "outcome", None),
        "passed": getattr(report, "passed", None),
        "failed": getattr(report, "failed", None),
        "skipped": getattr(report, "skipped", None),
        "duration_seconds": round(getattr(report, "duration", 0.0), 6),
        "longrepr": _redact_ai_text(str(longrepr))[:3000] if longrepr else None,
        "sections": [
            (name, _redact_ai_text(str(content))[:1000])
            for name, content in getattr(report, "sections", [])
        ],
    }
    print("\n========== pytest report debug ==========")
    print("item attributes:\n" + pformat(item_attributes, sort_dicts=False))
    print("report attributes:\n" + pformat(report_attributes, sort_dicts=False))
    print("=========================================\n")


def pytest_addoption(parser):
    parser.addoption(
        "--ai-analysis",
        action="store_true",
        default=False,
        help="调用已配置的 AI 分析失败摘要，并附加到 Allure 报告",
    )
    parser.addoption(
        "--debug-test-report",
        action="store_true",
        default=False,
        help="调试用：打印 pytest 的常用 item 和 TestReport 属性",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    # 调试用：打印常用属性；避免展开 config、session 等庞大内部对象。
    if item.config.getoption("--debug-test-report"):
        _debug_report_attributes(item, report)

    if (
            call.when != "call"
            or not report.failed
            or not item.config.getoption("--ai-analysis")
    ):
        return

    from payment_python_tests.ai.assistant import analyze_failure_with_ai

    try:
        analysis = analyze_failure_with_ai([_ai_failure_record(item, report)])
    except Exception as exc:
        analysis = f"AI 分析调用失败：{type(exc).__name__}"

    report.sections.append(("AI failure analysis", analysis))
    try:
        import allure
    except ImportError:
        return
    try:
        allure.attach(
            analysis,
            name="AI 失败分析",
            attachment_type=allure.attachment_type.TEXT,
        )
    except Exception:
        report.sections.append(("Allure attachment error", "无法写入 AI 分析附件"))


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
