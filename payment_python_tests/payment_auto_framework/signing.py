from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature


def compact_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def rsa_sha256_sign(data: str, private_key_base64: str) -> str:
    private_key = serialization.load_der_private_key(base64.b64decode(private_key_base64), password=None)
    signature = private_key.sign(data.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def rsa_sha256_verify(data: str, signature_base64: str, public_key_base64: str) -> bool:
    public_key = serialization.load_der_public_key(base64.b64decode(public_key_base64))
    try:
        public_key.verify(base64.b64decode(signature_base64), data.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return True
    except (ValueError, InvalidSignature):
        return False


def hmac_sha256_sorted_values(
    payload: dict[str, Any],
    secret: str,
    *,
    excluded: tuple[str, ...] = ("hash",),
    delimiter: str = "|",
) -> str:
    plain = delimiter.join("" if payload[key] is None else str(payload[key]) for key in sorted(payload) if key not in excluded)
    return hmac.new(secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha256).hexdigest()
