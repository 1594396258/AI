from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    payment_base_url: str
    merchant_id: str
    merchant_private_key: str
    response_public_key: str
    request_timeout: float
    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password: str
    ai_base_url: str
    ai_api_key: str
    ai_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            payment_base_url=_env("PAYMENT_BASE_URL", "http://127.0.0.1:9012/finance-payment-service/v1").rstrip("/"),
            merchant_id=_env("MCH_ID"),
            merchant_private_key=_env("MCH_PRIVATE_KEY"),
            response_public_key=_env("RESPONSE_PUBLIC_KEY"),
            request_timeout=float(_env("REQUEST_TIMEOUT", "15")),
            database_host=_env("DB_HOST"),
            database_port=int(_env("DB_PORT", "3306")),
            database_name=_env("DB_NAME"),
            database_user=_env("DB_USER"),
            database_password=_env("DB_PASSWORD"),
            ai_base_url=_env("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            ai_api_key=_env("AI_API_KEY") or _env("OPENAI_API_KEY"),
            ai_model=_env("AI_MODEL"),
        )

    def require_live_payment(self) -> None:
        missing = [name for name, value in {"MCH_ID": self.merchant_id, "MCH_PRIVATE_KEY": self.merchant_private_key}.items() if not value]
        if missing:
            raise RuntimeError(f"真实 Java 测试缺少环境变量: {', '.join(missing)}")

    def require_database(self) -> None:
        missing = [name for name, value in {"DB_HOST": self.database_host, "DB_NAME": self.database_name, "DB_USER": self.database_user}.items() if not value]
        if missing:
            raise RuntimeError(f"数据库验证缺少环境变量: {', '.join(missing)}")
