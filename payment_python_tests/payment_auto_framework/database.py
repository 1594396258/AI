"""Backward-compatible database facade."""

from payment_python_tests.config.settings import AppSettings
from payment_python_tests.database.mysql_client import MysqlClient
from payment_python_tests.database.order_repository import OrderRepository
from payment_python_tests.models.order import OrderSnapshot, TRADE_STATE_NAMES


class MysqlOrderRepository(OrderRepository):
    def __init__(self, settings: AppSettings):
        settings.require_database()
        self._client = MysqlClient(settings.database)
        super().__init__(self._client)

    def close(self) -> None:
        self._client.close()


__all__ = [
    "MysqlClient",
    "MysqlOrderRepository",
    "OrderRepository",
    "OrderSnapshot",
    "TRADE_STATE_NAMES",
]
