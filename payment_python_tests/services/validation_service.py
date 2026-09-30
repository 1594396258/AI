from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from payment_python_tests.models.channel_contract import ChannelContract
from payment_python_tests.utils.sign_utils import hmac_sha256_sorted_values


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
    issues: list[ValidationIssue] = []
    order_field = contract.identity.get("local_order_field", "merchantOrderId")
    channel_field = contract.identity.get("channel_order_field", "transactionId")
    amount_field = contract.amount.get("field", "amount")
    if order_field in payload and payload[order_field] != local_order_no:
        issues.append(
            ValidationIssue(
                "ORDER_MISMATCH",
                order_field,
                local_order_no,
                payload[order_field],
                "Channel order identity differs",
            )
        )
    if amount_field in payload:
        try:
            actual = contract.to_minor(payload[amount_field])
            if actual != local_amount_minor:
                issues.append(
                    ValidationIssue(
                        "AMOUNT_MISMATCH",
                        amount_field,
                        local_amount_minor,
                        actual,
                        "Channel amount differs",
                    )
                )
        except (TypeError, ValueError, InvalidOperation):
            issues.append(
                ValidationIssue(
                    "AMOUNT_INVALID",
                    amount_field,
                    local_amount_minor,
                    payload[amount_field],
                    "Amount is not numeric",
                )
            )
    if (
        local_channel_order_no
        and channel_field in payload
        and payload[channel_field] != local_channel_order_no
    ):
        issues.append(
            ValidationIssue(
                "CHANNEL_ORDER_MISMATCH",
                channel_field,
                local_channel_order_no,
                payload[channel_field],
                "Channel transaction id differs",
            )
        )
    return issues


def assert_valid_channel_payload(*args: Any, **kwargs: Any) -> None:
    issues = validate_channel_payload(*args, **kwargs)
    if issues:
        raise AssertionError(_format_issues(issues))


def _resolve(context: dict[str, Any], dotted_path: str) -> Any:
    value: Any = context
    for part in dotted_path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise KeyError(dotted_path)
    return value


def _transform(value: Any, transform: str | None) -> Any:
    if not transform:
        return value
    if transform == "minor_to_major_2":
        return f"{Decimal(str(value)) / Decimal(100):.2f}"
    if transform == "lower":
        return str(value).lower()
    if transform == "upper":
        return str(value).upper()
    if transform == "string":
        return str(value)
    raise ValueError(f"Unsupported transform: {transform}")


def validate_outbound_request(
    contract: ChannelContract,
    record: dict[str, Any],
    context: dict[str, Any],
    *,
    operation: str = "payout",
    signing_secret: str | None = None,
) -> list[ValidationIssue]:
    if operation not in {"payout", "query"}:
        raise ValueError(f"Unsupported outbound operation: {operation}")
    config = (
        contract.outbound_query if operation == "query" else contract.outbound_request
    )
    if not config:
        raise ValueError(f"{contract.name} has no outbound {operation} contract")
    issues: list[ValidationIssue] = []
    body = record.get("body") if isinstance(record.get("body"), dict) else {}
    headers = {str(key).lower(): value for key, value in record.get("headers", {}).items()}
    expected_method = config.get("method")
    if expected_method and record.get("method") != expected_method:
        issues.append(
            ValidationIssue(
                "METHOD_MISMATCH", "method", expected_method, record.get("method"), "HTTP method differs"
            )
        )
    path = urlsplit(record.get("path", "")).path
    prefix = config.get("path_prefix")
    if prefix and not path.startswith(prefix):
        issues.append(
            ValidationIssue("PATH_MISMATCH", "path", prefix, path, "URL path prefix differs")
        )
    suffix_source = config.get("path_suffix_source")
    if suffix_source:
        try:
            suffix = str(_resolve(context, suffix_source))
            if not path.endswith("/" + suffix):
                issues.append(
                    ValidationIssue(
                        "PATH_MISMATCH", "path", ".../" + suffix, path, "URL uses wrong transaction id"
                    )
                )
        except KeyError as exc:
            issues.append(
                ValidationIssue("EXPECTED_VALUE_UNAVAILABLE", "path", suffix_source, None, str(exc))
            )
    for field, rule in config.get("body", {}).items():
        actual = body.get(field)
        if field not in body:
            issues.append(
                ValidationIssue("REQUEST_FIELD_MISSING", field, rule, None, "Body field is missing")
            )
            continue
        if "constant" in rule:
            expected = rule["constant"]
        elif "source" in rule:
            try:
                expected = _transform(_resolve(context, rule["source"]), rule.get("transform"))
            except (KeyError, ValueError, InvalidOperation) as exc:
                issues.append(
                    ValidationIssue("EXPECTED_VALUE_UNAVAILABLE", field, rule["source"], None, str(exc))
                )
                continue
        elif "pattern" in rule:
            if re.fullmatch(rule["pattern"], str(actual)) is None:
                issues.append(
                    ValidationIssue("FORMAT_MISMATCH", field, rule["pattern"], actual, "Value format differs")
                )
            continue
        elif rule.get("validator") == "hmac_sha256_sorted_values":
            if not signing_secret:
                issues.append(
                    ValidationIssue("SIGNING_SECRET_MISSING", field, "test secret", None, "Cannot verify signature")
                )
                continue
            expected = hmac_sha256_sorted_values(body, signing_secret)
        else:
            continue
        if actual != expected:
            issues.append(
                ValidationIssue("REQUEST_VALUE_MISMATCH", field, expected, actual, "Body value differs")
            )
    for field in config.get("forbidden_fields", []):
        if field in body:
            issues.append(
                ValidationIssue("FORBIDDEN_FIELD_PRESENT", field, "absent", body[field], "Field must not be sent")
            )
    for field, rule in config.get("headers", {}).items():
        actual = headers.get(field.lower())
        if actual is None:
            issues.append(
                ValidationIssue("HEADER_MISSING", field, rule, None, "Header is missing")
            )
            continue
        if "constant" in rule:
            expected = rule["constant"]
        elif "source" in rule:
            try:
                expected = f"{rule.get('prefix', '')}{_resolve(context, rule['source'])}"
            except KeyError as exc:
                issues.append(
                    ValidationIssue("EXPECTED_VALUE_UNAVAILABLE", field, rule["source"], None, str(exc))
                )
                continue
        else:
            continue
        if actual != expected:
            hidden_expected = "***" if rule.get("sensitive") else expected
            hidden_actual = "***" if rule.get("sensitive") else actual
            issues.append(
                ValidationIssue("HEADER_VALUE_MISMATCH", field, hidden_expected, hidden_actual, "Header differs")
            )
    return issues


def assert_valid_outbound_request(*args: Any, **kwargs: Any) -> None:
    issues = validate_outbound_request(*args, **kwargs)
    if issues:
        raise AssertionError(_format_issues(issues))


def _format_issues(issues: list[ValidationIssue]) -> str:
    return "; ".join(
        f"{issue.code}[{issue.field}]: expected={issue.expected!r}, actual={issue.actual!r}"
        for issue in issues
    )
