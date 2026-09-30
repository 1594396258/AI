from __future__ import annotations

import json
from typing import Any

from payment_python_tests.config.settings import RedisSettings


class RedisClient:
    def __init__(self, settings: RedisSettings):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Install redis before using RedisClient") from exc
        self.key_prefix = settings.key_prefix
        self.client = redis.Redis(
            host=settings.host,
            port=settings.port,
            password=settings.password or None,
            db=settings.db,
            decode_responses=settings.decode_responses,
            protocol=settings.protocol,
        )

    def _key(self, key: str) -> str:
        return f"{self.key_prefix}{key}"

    def get(self, key: str) -> Any:
        return self.client.get(self._key(key))

    def get_json(self, key: str, default: Any = None) -> Any:
        value = self.get(key)
        if value is None:
            return default
        return json.loads(value)

    def set(self, key: str, value: Any, *, expire_seconds: int | None = None) -> bool:
        return bool(self.client.set(self._key(key), value, ex=expire_seconds))

    def set_json(
        self, key: str, value: Any, *, expire_seconds: int | None = None
    ) -> bool:
        return self.set(
            key,
            json.dumps(value, ensure_ascii=False, default=str),
            expire_seconds=expire_seconds,
        )

    def delete(self, key: str) -> int:
        return int(self.client.delete(self._key(key)))

    def exists(self, key: str) -> bool:
        return bool(self.client.exists(self._key(key)))

    def ping(self) -> bool:
        return bool(self.client.ping())

    def close(self) -> None:
        self.client.close()
