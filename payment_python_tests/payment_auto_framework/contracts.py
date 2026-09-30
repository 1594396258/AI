from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ChannelContract:
    name: str
    service: str
    query_service: str
    identity: dict[str, str]
    amount: dict[str, Any]
    status_mapping: dict[str, str]
    signature: dict[str, Any] = field(default_factory=dict)
    callback: dict[str, Any] = field(default_factory=dict)
    outbound_request: dict[str, Any] = field(default_factory=dict)
    outbound_query: dict[str, Any] = field(default_factory=dict)
    required_fields: tuple[str, ...] = ()

    @property
    def amount_scale(self) -> int:
        unit = str(self.amount.get("unit", "minor")).lower()
        return 2 if unit in {"yuan", "major", "decimal"} else 0

    def to_minor(self, value: Any) -> int:
        number = Decimal(str(value))
        if self.amount_scale == 0:
            return int(number)
        return int(number * (Decimal(10) ** self.amount_scale))

    def map_status(self, channel_status: str | None) -> str | None:
        if channel_status is None:
            return None
        return self.status_mapping.get(channel_status.lower())


def load_contract(path: str | Path) -> ChannelContract:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    status = raw.get("status", {})
    return ChannelContract(
        name=raw["channel"],
        service=raw.get("service", ""),
        query_service=raw.get("query_service", ""),
        identity=raw.get("identity", {}),
        amount=raw.get("amount", {}),
        status_mapping=status.get("mapping", raw.get("status_mapping", {})),
        signature=raw.get("signature", {}),
        callback=raw.get("callback", {}),
        outbound_request=raw.get("outbound_request", {}),
        outbound_query=raw.get("outbound_query", {}),
        required_fields=tuple(raw.get("required_fields", [])),
    )
