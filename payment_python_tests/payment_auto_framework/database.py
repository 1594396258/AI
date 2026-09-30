from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .settings import Settings


TRADE_STATE_NAMES = {0: "INIT", 1: "PROCESSING", 2: "SUCCESS", 3: "FAIL", 4: "REVERSAL", 5: "CLOSED"}


@dataclass(frozen=True)
class OrderSnapshot:
    order_no: str
    out_order_no: str | None
    trade_state: int
    transaction_id: str | None
    amount: int | None
    channel_amount: int | None
    notify_state: int | None
    raw: dict[str, Any]

    @property
    def state_name(self) -> str:
        return TRADE_STATE_NAMES.get(self.trade_state, f"UNKNOWN({self.trade_state})")


class MysqlOrderRepository:
    QUERY = """
        SELECT ORDER_NO, OUT_ORDER_NO, TRADE_STATE, TRANSACTION_ID,
               AMOUNT, CHANNEL_AMOUNT, NOTIFY_STATE
        FROM FIN_PAY_ORDER WHERE ORDER_NO = %s LIMIT 1
    """

    def __init__(self, settings: Settings):
        settings.require_database()
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError("需要安装 PyMySQL: pip install -r requirements.txt") from exc
        self.connection = pymysql.connect(host=settings.database_host, port=settings.database_port, user=settings.database_user, password=settings.database_password, database=settings.database_name, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=True)

    def get(self, order_no: str) -> OrderSnapshot | None:
        return self._find("ORDER_NO", order_no)

    def get_by_out_order_no(self, out_order_no: str) -> OrderSnapshot | None:
        return self._find("OUT_ORDER_NO", out_order_no)

    def _find(self, column: str, value: str) -> OrderSnapshot | None:
        if column not in {"ORDER_NO", "OUT_ORDER_NO"}:
            raise ValueError("unsupported order lookup column")
        query = self.QUERY.replace("ORDER_NO = %s", f"{column} = %s")
        with self.connection.cursor() as cursor:
            cursor.execute(query, (value,))
            row = cursor.fetchone()
        if not row:
            return None
        return OrderSnapshot(order_no=row["ORDER_NO"], out_order_no=row.get("OUT_ORDER_NO"), trade_state=row["TRADE_STATE"], transaction_id=row.get("TRANSACTION_ID"), amount=row.get("AMOUNT"), channel_amount=row.get("CHANNEL_AMOUNT"), notify_state=row.get("NOTIFY_STATE"), raw=row)

    def close(self) -> None:
        self.connection.close()
