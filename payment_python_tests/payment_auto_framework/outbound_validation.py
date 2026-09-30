from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from .contracts import ChannelContract
from .signing import hmac_sha256_sorted_values
from .validation import ValidationIssue


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
    raise ValueError(f"unsupported transform: {transform}")


def validate_outbound_request(
    contract: ChannelContract,
    record: dict[str, Any],
    context: dict[str, Any],
    *,
    operation: str = "payout",
    signing_secret: str | None = None,
) -> list[ValidationIssue]:
    """Validate the actual HTTP request sent by Java to a channel mock."""
    if operation not in {"payout", "query"}:
        raise ValueError(f"unsupported outbound operation: {operation}")
    config = contract.outbound_query if operation == "query" else contract.outbound_request
    if not config:
        raise ValueError(f"{contract.name} has no outbound {operation} contract")
    issues: list[ValidationIssue] = []
    actual_body = record.get("body") if isinstance(record.get("body"), dict) else {}
    actual_headers = {str(key).lower(): value for key, value in record.get("headers", {}).items()}

    expected_method = config.get("method")
    if expected_method and record.get("method") != expected_method:
        issues.append(ValidationIssue("METHOD_MISMATCH", "method", expected_method, record.get("method"), "HTTP method differs"))

    path = urlsplit(record.get("path", "")).path
    expected_prefix = config.get("path_prefix")
    if expected_prefix and not path.startswith(expected_prefix):
        issues.append(ValidationIssue("PATH_MISMATCH", "path", expected_prefix, path, "outbound URL path prefix differs"))
    if "path_suffix_source" in config:
        try:
            suffix = str(_resolve(context, config["path_suffix_source"]))
            if not path.endswith("/" + suffix):
                issues.append(ValidationIssue("PATH_MISMATCH", "path", ".../" + suffix, path, "outbound URL uses the wrong channel transaction id"))
        except KeyError as exc:
            issues.append(ValidationIssue("EXPECTED_VALUE_UNAVAILABLE", "path", config["path_suffix_source"], None, str(exc)))

    for field, rule in config.get("body", {}).items():
        actual = actual_body.get(field)
        if field not in actual_body:
            issues.append(ValidationIssue("REQUEST_FIELD_MISSING", field, rule, None, "outbound body field is missing"))
            continue
        if "constant" in rule:
            expected = rule["constant"]
        elif "source" in rule:
            try:
                expected = _transform(_resolve(context, rule["source"]), rule.get("transform"))
            except (KeyError, ValueError, InvalidOperation) as exc:
                issues.append(ValidationIssue("EXPECTED_VALUE_UNAVAILABLE", field, rule["source"], None, str(exc)))
                continue
        elif "pattern" in rule:
            if re.fullmatch(rule["pattern"], str(actual)) is None:
                issues.append(ValidationIssue("FORMAT_MISMATCH", field, rule["pattern"], actual, "outbound value format differs"))
            continue
        elif rule.get("validator") == "hmac_sha256_sorted_values":
            if not signing_secret:
                issues.append(ValidationIssue("SIGNING_SECRET_MISSING", field, "test secret", None, "cannot verify outbound signature"))
                continue
            expected = hmac_sha256_sorted_values(actual_body, signing_secret)
        else:
            continue
        if actual != expected:
            issues.append(ValidationIssue("REQUEST_VALUE_MISMATCH", field, expected, actual, "outbound body value differs"))

    for field in config.get("forbidden_fields", []):
        if field in actual_body:
            issues.append(ValidationIssue("FORBIDDEN_FIELD_PRESENT", field, "absent", actual_body[field], "field must not be sent to channel"))

    for field, rule in config.get("headers", {}).items():
        actual = actual_headers.get(field.lower())
        if actual is None:
            issues.append(ValidationIssue("HEADER_MISSING", field, rule, None, "outbound header is missing"))
            continue
        if "constant" in rule:
            expected = rule["constant"]
        elif "source" in rule:
            try:
                expected = f"{rule.get('prefix', '')}{_resolve(context, rule['source'])}"
            except KeyError as exc:
                issues.append(ValidationIssue("EXPECTED_VALUE_UNAVAILABLE", field, rule["source"], None, str(exc)))
                continue
        else:
            continue
        if actual != expected:
            display_expected = "***" if rule.get("sensitive") else expected
            display_actual = "***" if rule.get("sensitive") else actual
            issues.append(ValidationIssue("HEADER_VALUE_MISMATCH", field, display_expected, display_actual, "outbound header value differs"))
    return issues


def assert_valid_outbound_request(*args: Any, **kwargs: Any) -> None:
    issues = validate_outbound_request(*args, **kwargs)
    if issues:
        details = "; ".join(f"{issue.code}[{issue.field}]: expected={issue.expected!r}, actual={issue.actual!r}" for issue in issues)
        raise AssertionError(details)
