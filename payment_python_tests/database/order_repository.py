from __future__ import annotations

from payment_python_tests.database.mysql_client import MysqlClient
from payment_python_tests.models.order import OrderSnapshot


class OrderRepository:
    SELECT_COLUMNS = """
        SELECT ORDER_NO, OUT_ORDER_NO, TRADE_STATE, TRANSACTION_ID,
               AMOUNT, CHANNEL_AMOUNT, NOTIFY_STATE
        FROM FIN_PAY_ORDER
    """

    def __init__(self, client: MysqlClient):
        self.client = client

    def get(self, order_no: str) -> OrderSnapshot | None:
        return self._find("ORDER_NO", order_no)

    def get_by_out_order_no(self, out_order_no: str) -> OrderSnapshot | None:
        return self._find("OUT_ORDER_NO", out_order_no)

    def _find(self, column: str, value: str) -> OrderSnapshot | None:
        if column not in {"ORDER_NO", "OUT_ORDER_NO"}:
            raise ValueError("Unsupported order lookup column")
        row = self.client.query_one(
            f"{self.SELECT_COLUMNS} WHERE {column} = %s LIMIT 1", (value,)
        )
        if not row:
            return None
        return OrderSnapshot(
            order_no=row["ORDER_NO"],
            out_order_no=row.get("OUT_ORDER_NO"),
            trade_state=row["TRADE_STATE"],
            transaction_id=row.get("TRANSACTION_ID"),
            amount=row.get("AMOUNT"),
            channel_amount=row.get("CHANNEL_AMOUNT"),
            notify_state=row.get("NOTIFY_STATE"),
            raw=row,
        )
