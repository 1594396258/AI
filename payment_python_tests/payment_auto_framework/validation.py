from __future__ import annotations

from dataclasses import dataclass
from decimal import InvalidOperation
from typing import Any

from .contracts import ChannelContract


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    field: str
    expected: Any
    actual: Any
    message: str


def validate_channel_payload(
    contract: ChannelContract,
    payload: dict[str, Any],
    *,
    local_order_no: str,
    local_amount_minor: int,
    local_channel_order_no: str | None = None,
) -> list[ValidationIssue]:
    """Validate facts common to payout responses, queries, and callbacks."""
    issues: list[ValidationIssue] = []
    order_field = contract.identity.get("local_order_field", "merchantOrderId")
    channel_field = contract.identity.get("channel_order_field", "transactionId")
    amount_field = contract.amount.get("field", "amount")

    if order_field in payload and payload[order_field] != local_order_no:
        issues.append(ValidationIssue("ORDER_MISMATCH", order_field, local_order_no, payload[order_field], "channel order identity differs"))
    if amount_field in payload:
        try:
            actual = contract.to_minor(payload[amount_field])
            if actual != local_amount_minor:
                issues.append(ValidationIssue("AMOUNT_MISMATCH", amount_field, local_amount_minor, actual, "channel amount differs"))
        except (TypeError, ValueError, InvalidOperation):
            issues.append(ValidationIssue("AMOUNT_INVALID", amount_field, local_amount_minor, payload[amount_field], "amount is not numeric"))
    if local_channel_order_no and channel_field in payload and payload[channel_field] != local_channel_order_no:
        issues.append(ValidationIssue("CHANNEL_ORDER_MISMATCH", channel_field, local_channel_order_no, payload[channel_field], "channel transaction id differs"))
    return issues


def assert_valid_channel_payload(*args: Any, **kwargs: Any) -> None:
    issues = validate_channel_payload(*args, **kwargs)
    if issues:
        details = "; ".join(f"{i.code}: {i.message} (expected={i.expected!r}, actual={i.actual!r})" for i in issues)
        raise AssertionError(details)
