from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[1]


def _env(name: str, default: Any = "") -> str:
    value = os.getenv(name)
    return str(default if value is None else value).strip()


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PaymentSettings:
    base_url: str
    timeout: float


@dataclass(frozen=True)
class MerchantSettings:
    merchant_id: str
    private_key: str
    response_public_key: str


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    name: str
    user: str
    password: str
    charset: str = "utf8mb4"


@dataclass(frozen=True)
class RedisSettings:
    host: str
    port: int
    password: str
    db: int
    decode_responses: bool = True
    protocol: int = 2
    key_prefix: str = ""


@dataclass(frozen=True)
class AiSettings:
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class RuntimeSettings:
    run_live_tests: bool


@dataclass(frozen=True)
class AppSettings:
    payment: PaymentSettings
    merchant: MerchantSettings
    database: DatabaseSettings
    redis: RedisSettings
    ai: AiSettings
    runtime: RuntimeSettings

    @classmethod
    def from_env(
        cls,
        environment: str | None = None,
        config_path: str | Path | None = None,
    ) -> "AppSettings":
        return load_settings(environment=environment, config_path=config_path)

    def require_live_payment(self) -> None:
        missing = [
            name
            for name, value in {
                "MCH_ID": self.merchant.merchant_id,
                "MCH_PRIVATE_KEY": self.merchant.private_key,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing live payment settings: {', '.join(missing)}")

    def require_database(self) -> None:
        missing = [
            name
            for name, value in {
                "DB_HOST": self.database.host,
                "DB_NAME": self.database.name,
                "DB_USER": self.database.user,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing database settings: {', '.join(missing)}")

    # Compatibility properties for existing callers.
    @property
    def payment_base_url(self) -> str:
        return self.payment.base_url

    @property
    def merchant_id(self) -> str:
        return self.merchant.merchant_id

    @property
    def merchant_private_key(self) -> str:
        return self.merchant.private_key

    @property
    def response_public_key(self) -> str:
        return self.merchant.response_public_key

    @property
    def request_timeout(self) -> float:
        return self.payment.timeout

    @property
    def database_host(self) -> str:
        return self.database.host

    @property
    def database_port(self) -> int:
        return self.database.port

    @property
    def database_name(self) -> str:
        return self.database.name

    @property
    def database_user(self) -> str:
        return self.database.user

    @property
    def database_password(self) -> str:
        return self.database.password

    @property
    def ai_base_url(self) -> str:
        return self.ai.base_url

    @property
    def ai_api_key(self) -> str:
        return self.ai.api_key

    @property
    def ai_model(self) -> str:
        return self.ai.model


def load_settings(
    environment: str | None = None,
    config_path: str | Path | None = None,
) -> AppSettings:
    load_dotenv(PROJECT_DIR / ".env")
    env_name = environment or _env("PAYMENT_TEST_ENV", "test")
    path = Path(config_path) if config_path else Path(__file__).with_name("config.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = raw.get(env_name, {})
    payment = config.get("payment", {})
    database = config.get("database", {})
    redis = config.get("redis", {})
    ai = config.get("ai", {})
    runtime = config.get("runtime", {})
    return AppSettings(
        payment=PaymentSettings(
            base_url=_env("PAYMENT_BASE_URL", payment.get("base_url", "")).rstrip("/"),
            timeout=float(_env("REQUEST_TIMEOUT", payment.get("timeout", 15))),
        ),
        merchant=MerchantSettings(
            merchant_id=_env("MCH_ID"),
            private_key=_env("MCH_PRIVATE_KEY"),
            response_public_key=_env("RESPONSE_PUBLIC_KEY"),
        ),
        database=DatabaseSettings(
            host=_env("DB_HOST"),
            port=int(_env("DB_PORT", database.get("port", 3306))),
            name=_env("DB_NAME"),
            user=_env("DB_USER"),
            password=_env("DB_PASSWORD"),
            charset=_env("DB_CHARSET", database.get("charset", "utf8mb4")),
        ),
        redis=RedisSettings(
            host=_env("REDIS_HOST"),
            port=int(_env("REDIS_PORT", redis.get("port", 6379))),
            password=_env("REDIS_PASSWORD"),
            db=int(_env("REDIS_DB", redis.get("db", 0))),
            decode_responses=_as_bool(
                _env("REDIS_DECODE_RESPONSES", redis.get("decode_responses", True))
            ),
            protocol=int(_env("REDIS_PROTOCOL", redis.get("protocol", 2))),
            key_prefix=_env("REDIS_KEY_PREFIX"),
        ),
        ai=AiSettings(
            base_url=_env("AI_BASE_URL", ai.get("base_url", "")).rstrip("/"),
            api_key=_env("AI_API_KEY") or _env("OPENAI_API_KEY"),
            model=_env("AI_MODEL"),
        ),
        runtime=RuntimeSettings(
            run_live_tests=_as_bool(
                _env("RUN_LIVE_TESTS", runtime.get("run_live_tests", False))
            )
        ),
    )
