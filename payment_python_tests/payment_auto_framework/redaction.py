from __future__ import annotations

from typing import Any


SENSITIVE_FIELDS = {"authorization", "cookie", "set-cookie", "hash", "signature", "pin", "secretkey", "password", "bankcardno", "customeraccno", "customermobile", "customername", "customeremail", "bankaccount", "mobileNumber".lower()}


def redact(value: Any) -> Any:
    """Remove credentials and personal data before writing HTTP evidence to disk."""
    if isinstance(value, dict):
        return {key: "***" if str(key).lower() in SENSITIVE_FIELDS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
