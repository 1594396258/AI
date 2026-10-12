from __future__ import annotations

import hashlib
import hmac
from typing import Any


def hmac_sha256_sorted_values(
    payload: dict[str, Any],
    secret: str,
    *,
    excluded: tuple[str, ...] = ("hash",),
    delimiter: str = "|",
) -> str:
    plain = delimiter.join(
        "" if payload[key] is None else str(payload[key])
        for key in sorted(payload)
        if key not in excluded
    )
    return hmac.new(
        secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha256
    ).hexdigest()

