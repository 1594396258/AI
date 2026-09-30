from __future__ import annotations

from typing import Any, Iterable

from payment_python_tests.config.settings import DatabaseSettings


class MysqlClient:
    """Small MySQL wrapper with read-only mode enabled by default."""

    def __init__(self, settings: DatabaseSettings, *, allow_write: bool = False):
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError("Install PyMySQL before using MysqlClient") from exc
        self.allow_write = allow_write
        self.connection = pymysql.connect(
            host=settings.host,
            port=settings.port,
            user=settings.user,
            password=settings.password,
            database=settings.name,
            charset=settings.charset,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    def query_one(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> dict[str, Any] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, tuple(params or ()))
            return cursor.fetchone()

    def query_all(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, tuple(params or ()))
            return list(cursor.fetchall())

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> int:
        if not self.allow_write:
            raise PermissionError("MysqlClient is read-only; enable allow_write explicitly")
        with self.connection.cursor() as cursor:
            return cursor.execute(sql, tuple(params or ()))

    def ping(self) -> None:
        self.connection.ping(reconnect=True)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "MysqlClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
