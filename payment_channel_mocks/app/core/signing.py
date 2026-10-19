from __future__ import annotations

import hashlib
import hmac
import re
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


def verify_hmac_sha256_sorted_values(payload: dict[str, Any], secret: str) -> bool:
    """Verify PPP's lowercase hex hash without changing the recorded payload."""
    signature = payload.get("hash")
    if (
        not secret
        or not isinstance(signature, str)
        or re.fullmatch(r"[0-9a-f]{64}", signature) is None
    ):
        return False
    expected = hmac_sha256_sorted_values(payload, secret)
    return hmac.compare_digest(signature, expected)

