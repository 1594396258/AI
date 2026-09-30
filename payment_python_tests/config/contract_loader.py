from __future__ import annotations

from pathlib import Path

import yaml

from payment_python_tests.models.channel_contract import ChannelContract


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
