from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TRADE_STATE_NAMES = {
    0: "INIT",
    1: "PROCESSING",
    2: "SUCCESS",
    3: "FAIL",
    4: "REVERSAL",
    5: "CLOSED",
}


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
