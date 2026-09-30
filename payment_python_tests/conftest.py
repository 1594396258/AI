import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@pytest.fixture
def settings():
    return {
        "base_url": env("PAYMENT_BASE_URL").rstrip("/"),
        "mch_id": env("MCH_ID"),
        "mch_private_key": env("MCH_PRIVATE_KEY"),
        "service": env("SERVICE"),
        "query_service": env("QUERY_SERVICE"),
        "order_no": env("ORDER_NO"),
        "notify_url": env("NOTIFY_URL"),
        "timeout": float(env("REQUEST_TIMEOUT", "15")),
    }


@pytest.fixture
def live_required(settings):
    required = ["base_url", "mch_id", "service", "query_service"]
    missing = [name for name in required if not settings[name]]
    if missing or env("RUN_LIVE_TESTS", "false").lower() != "true":
        pytest.skip("未启用真实测试，请配置 .env 并设置 RUN_LIVE_TESTS=true")
