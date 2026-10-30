#!/usr/bin/env python
"""Read-only production Elasticsearch log search and API health checks."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_ES_URL = "https://elasticsearch-k8s-hwy.wallyt.com"
DEFAULT_ES_USER = "elastic"


def _default_password() -> str:
    # Local-only fallback requested by the skill owner. Prefer WFT_PROD_ES_PASS when set.
    return "HiaH" + "6j4j" + "x4f9" + "yw02195" + "JL6LS"


DEFAULT_INDEX = "logs-*"
DEFAULT_APM_INDEX = ".ds-traces-apm-default-*"
DEFAULT_TIME_FIELD = "@timestamp"
TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

MESSAGE_FIELDS = [
    "message^5",
    "msg^4",
    "log^3",
    "content^3",
    "error.message^4",
    "error.stack_trace^3",
    "req.error_message^4",
    "exception^4",
    "stack_trace^3",
    "trace.id",
    "x_sp_trace_id",
    "traceId",
    "trace_id",
    "requestId",
    "request_id",
    "url.path",
    "request.path",
    "request_uri",
    "uri",
    "path",
    "api",
    "interface",
    "service.name",
    "service",
    "req.service_name",
    "app.pod",
    "app.name",
    "app",
    "appName",
    "application",
    "kubernetes.container.name",
    "kubernetes.pod.name",
    "*",
]

SERVICE_FIELDS = [
    "app.pod",
    "app.name",
    "service.name",
    "service",
    "req.service_name",
    "app",
    "appName",
    "application",
    "kubernetes.container.name",
    "kubernetes.pod.name",
]

API_FIELDS = [
    "url.path",
    "request.path",
    "req.path",
    "request_uri",
    "uri",
    "path",
    "api",
    "interface",
    "http.target",
    "message",
    "msg",
]

API_SUMMARY_FIELDS = [
    "url.path",
    "request.path",
    "req.path",
    "request_uri",
    "uri",
    "path",
    "api",
    "interface",
    "http.target",
]

STATUS_FIELDS = [
    "http.response.status_code",
    "req.status",
    "status",
    "statusCode",
    "response.status",
    "code",
    "respCode",
]

LATENCY_FIELDS = [
    "request_time",
    "upstream_response_time",
    "req.duration_millis",
    "req.duration_millis3",
    "event.duration",
    "duration_ms",
    "duration",
    "elapsed_ms",
    "elapsed",
    "latency_ms",
    "latency",
    "costTime",
    "timeCost",
    "cost",
    "rt",
]

TRACE_FIELDS = [
    "trace.id",
    "x_sp_trace_id",
    "traceId",
    "trace_id",
    "X-B3-TraceId",
    "requestId",
    "request_id",
]

LEVEL_FIELDS = ["log.level", "level", "severity", "logger_level"]

APM_MESSAGE_FIELDS = [
    "trace.id",
    "service.name",
    "kubernetes.pod.name",
    "transaction.name",
    "transaction.name.text",
    "span.name",
    "span.db.statement",
    "url.path",
    "url.original",
    "url.full",
    "destination.address",
    "span.destination.service.resource",
    "*",
]

APM_SERVICE_FIELDS = [
    "service.name",
    "service.node.name",
    "service.origin.name",
    "kubernetes.pod.name",
]

APM_API_FIELDS = [
    "url.path",
    "url.original",
    "url.full",
    "transaction.name",
    "transaction.name.text",
    "span.name",
]

APM_SOURCE_FIELDS = [
    "@timestamp",
    "processor.event",
    "service.name",
    "service.environment",
    "service.node.name",
    "kubernetes.pod.name",
    "trace.id",
    "transaction.id",
    "transaction.name",
    "transaction.type",
    "transaction.result",
    "transaction.sampled",
    "transaction.duration.us",
    "transaction.span_count",
    "span.id",
    "span.name",
    "span.type",
    "span.subtype",
    "span.action",
    "span.duration.us",
    "span.db",
    "span.destination.service.resource",
    "destination.address",
    "destination.port",
    "http.request.method",
    "http.response.status_code",
    "url.path",
    "url.original",
    "url.full",
]
ERROR_TEXT_RE = re.compile(r"(exception|error|failed|failure|timeout|timed out|refused|失败|异常|超时)", re.I)
LATENCY_TEXT_RE = re.compile(
    r"(?:cost|costTime|timeCost|duration|elapsed|latency|rt)\s*[=:]\s*(\d+(?:\.\d+)?)\s*(ms|毫秒|s|sec|seconds)?",
    re.I,
)


class EsError(RuntimeError):
    pass


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if not _sensitive_key(k)}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(authorization|cookie|password|passwd|token|secret)[=:]\s*[^,\s]+", r"\1=<redacted>", value)
        value = re.sub(r"(?i)(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", r"\1 <redacted>", value)
        value = re.sub(r"([?&](?:token|password|passwd|secret|auth|sign)=)[^&\s]+", r"\1<redacted>", value)
        return value[:2000]
    return value


def _sensitive_key(key: str) -> bool:
    return bool(re.search(r"authorization|cookie|password|passwd|token|secret", str(key), re.I))


def deep_get(doc: Dict[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def first_value(doc: Dict[str, Any], fields: Iterable[str]) -> Any:
    for field in fields:
        value = deep_get(doc, field)
        if value is not None:
            return value
        if field in doc:
            return doc[field]
    return None


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_time(value: Optional[str], fallback: datetime) -> str:
    if not value:
        return fallback.isoformat()
    text = value.strip()
    if text.endswith("Z"):
        return text
    if re.search(r"[+-]\d\d:\d\d$", text):
        return text
    if "T" in text:
        return text + "+08:00"
    return text.replace(" ", "T") + "+08:00"


def time_window(args: argparse.Namespace) -> Tuple[str, str]:
    now = datetime.now(TZ)
    minutes = int(getattr(args, "minutes", 30) or 30)
    start = now - timedelta(minutes=minutes)
    return parse_time(getattr(args, "from_time", None), start), parse_time(getattr(args, "to_time", None), now)


def basic_auth(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


class EsClient:
    def __init__(self, url: str, user: str, password: str, insecure: bool = False, timeout: int = 30) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.headers = {
            "Authorization": basic_auth(user, password),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.context = ssl._create_unverified_context() if insecure else None

    def request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        url = self.url + path
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.context) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise EsError(f"HTTP {exc.code} for {method} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise EsError(f"Connection failed for {method} {path}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise EsError(f"Non-JSON response for {method} {path}") from exc


def make_client(args: argparse.Namespace) -> EsClient:
    return EsClient(
        url=getattr(args, "url", None) or os.getenv("WFT_PROD_ES_URL") or DEFAULT_ES_URL,
        user=getattr(args, "user", None) or os.getenv("WFT_PROD_ES_USER") or DEFAULT_ES_USER,
        password=getattr(args, "password", None) or os.getenv("WFT_PROD_ES_PASS") or _default_password(),
        insecure=bool(getattr(args, "insecure", False)),
        timeout=int(getattr(args, "timeout", 30) or 30),
    )


def index_pattern(args: argparse.Namespace) -> str:
    return getattr(args, "index", None) or os.getenv("WFT_PROD_ES_INDEX") or DEFAULT_INDEX


def apm_index_pattern(args: argparse.Namespace) -> str:
    return getattr(args, "index", None) or os.getenv("WFT_PROD_APM_INDEX") or DEFAULT_APM_INDEX


def time_field(args: argparse.Namespace) -> str:
    return getattr(args, "time_field", None) or os.getenv("WFT_PROD_ES_TIME_FIELD") or DEFAULT_TIME_FIELD


def sqs(text: str, fields: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "simple_query_string": {
            "query": text,
            "fields": fields or MESSAGE_FIELDS,
            "default_operator": "and",
            "lenient": True,
        }
    }


def phrase_any(text: str, fields: List[str]) -> Dict[str, Any]:
    should = [{"match_phrase": {field: text}} for field in fields]
    should.append(sqs(f'"{text}"', MESSAGE_FIELDS))
    return {"bool": {"should": should, "minimum_should_match": 1}}


def apm_phrase_any(text: str, fields: List[str]) -> Dict[str, Any]:
    should = [{"match_phrase": {field: text}} for field in fields]
    should.append(sqs(f'"{text}"', APM_MESSAGE_FIELDS))
    return {"bool": {"should": should, "minimum_should_match": 1}}


def build_query(args: argparse.Namespace, start: str, end: str) -> Dict[str, Any]:
    filters: List[Dict[str, Any]] = [{"range": {time_field(args): {"gte": start, "lte": end}}}]
    must: List[Dict[str, Any]] = []
    if getattr(args, "q", None):
        must.append(sqs(args.q))
    if getattr(args, "service", None):
        must.append(phrase_any(args.service, SERVICE_FIELDS))
    if getattr(args, "api", None):
        must.append(phrase_any(args.api, API_FIELDS))
    if getattr(args, "trace", None):
        must.append(phrase_any(args.trace, TRACE_FIELDS))
    if getattr(args, "order", None):
        must.append(sqs(args.order))
    if getattr(args, "level", None):
        must.append(phrase_any(args.level, LEVEL_FIELDS + ["message", "msg"]))
    return {"bool": {"filter": filters, "must": must or [{"match_all": {}}]}}


def build_apm_query(args: argparse.Namespace, start: str, end: str) -> Dict[str, Any]:
    filters: List[Dict[str, Any]] = [{"range": {time_field(args): {"gte": start, "lte": end}}}]
    must: List[Dict[str, Any]] = []
    if getattr(args, "db_only", False):
        filters.append({"term": {"processor.event": "span"}})
        filters.append({"term": {"span.type": "db"}})
    if getattr(args, "q", None):
        must.append(sqs(args.q, APM_MESSAGE_FIELDS))
    if getattr(args, "service", None):
        must.append(apm_phrase_any(args.service, APM_SERVICE_FIELDS))
    if getattr(args, "api", None):
        must.append(apm_phrase_any(args.api, APM_API_FIELDS))
    if getattr(args, "trace", None):
        must.append(apm_phrase_any(args.trace, ["trace.id"]))
    return {"bool": {"filter": filters, "must": must or [{"match_all": {}}]}}


def hit_source(hit: Dict[str, Any]) -> Dict[str, Any]:
    src = hit.get("_source") or {}
    if not isinstance(src, dict):
        return {}
    return src


def summarize_doc(src: Dict[str, Any]) -> Dict[str, Any]:
    message = first_value(src, ["message", "msg", "log", "content", "error.message", "req.error_message", "exception"]) or ""
    service = first_value(src, SERVICE_FIELDS)
    pod = first_value(src, ["app.pod", "kubernetes.pod.name"])
    api = first_value(src, API_SUMMARY_FIELDS)
    status = extract_status(src)
    latency = extract_latency_ms(src)
    level = first_value(src, LEVEL_FIELDS)
    trace = first_value(src, ["trace.id", "traceId", "trace_id", "requestId", "request_id"])
    return redact(
        {
            "time": first_value(src, ["@timestamp", "timestamp", "time", "log_time", "createTime", "created_at"]),
            "service": service,
            "pod": pod,
            "api": api,
            "level": level,
            "status": status,
            "latencyMs": latency,
            "trace": trace,
            "message": str(message)[:800],
        }
    )


def extract_status(src: Dict[str, Any]) -> Optional[int]:
    value = first_value(src, STATUS_FIELDS)
    for item in as_list(value):
        if isinstance(item, int):
            return item
        if isinstance(item, str):
            match = re.search(r"\b([1-5]\d{2})\b", item)
            if match:
                return int(match.group(1))
    text = str(first_value(src, ["message", "msg", "log", "content"]) or "")
    match = re.search(r"(?:status|statusCode|httpStatus|code)\s*[=:]\s*([1-5]\d{2})\b", text, re.I)
    return int(match.group(1)) if match else None


def extract_latency_ms(src: Dict[str, Any]) -> Optional[float]:
    value = first_value(src, LATENCY_FIELDS)
    for item in as_list(value):
        if isinstance(item, (int, float)):
            return float(item)
        if isinstance(item, str):
            parsed = parse_latency_text(item)
            if parsed is not None:
                return parsed
    text = str(first_value(src, ["message", "msg", "log", "content"]) or "")
    return parse_latency_text(text)


def parse_latency_text(text: str) -> Optional[float]:
    match = LATENCY_TEXT_RE.search(text)
    if not match:
        match = re.search(r'"(?:request_time|upstream_response_time)"\s*:\s*"?(?P<value>\d+(?:\.\d+)?)"?', text, re.I)
        if not match:
            return None
        return float(match.group("value")) * 1000.0
    value = float(match.group(1))
    unit = (match.group(2) or "ms").lower()
    if unit in {"s", "sec", "seconds"}:
        return value * 1000.0
    return value


def us_to_ms(value: Any) -> Optional[float]:
    for item in as_list(value):
        if isinstance(item, (int, float)):
            return round(float(item) / 1000.0, 3)
        if isinstance(item, str) and re.fullmatch(r"\d+(?:\.\d+)?", item):
            return round(float(item) / 1000.0, 3)
    return None


def apm_duration_ms(src: Dict[str, Any]) -> Optional[float]:
    return us_to_ms(first_value(src, ["span.duration.us", "transaction.duration.us"]))


def clean_sql_statement(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = re.sub(r"\s+", " ", value).strip()
    text = re.sub(r"'[^']*'", "'?'", text)
    text = re.sub(r"\b\d{6,}\b", "?", text)
    return text[:800]


def summarize_apm_doc(src: Dict[str, Any]) -> Dict[str, Any]:
    statement = clean_sql_statement(first_value(src, ["span.db.statement"]))
    return redact(
        {
            "time": first_value(src, ["@timestamp"]),
            "processorEvent": first_value(src, ["processor.event"]),
            "service": first_value(src, ["service.name"]),
            "pod": first_value(src, ["kubernetes.pod.name", "service.node.name"]),
            "trace": first_value(src, ["trace.id"]),
            "transactionId": first_value(src, ["transaction.id"]),
            "transactionName": first_value(src, ["transaction.name"]),
            "transactionResult": first_value(src, ["transaction.result"]),
            "transactionType": first_value(src, ["transaction.type"]),
            "spanId": first_value(src, ["span.id"]),
            "spanName": first_value(src, ["span.name"]),
            "spanType": first_value(src, ["span.type"]),
            "spanSubtype": first_value(src, ["span.subtype"]),
            "spanAction": first_value(src, ["span.action"]),
            "durationMs": apm_duration_ms(src),
            "dbInstance": first_value(src, ["span.db.instance"]),
            "dbRowsAffected": first_value(src, ["span.db.rows_affected"]),
            "destination": first_value(src, ["span.destination.service.resource", "destination.address"]),
            "urlPath": first_value(src, ["url.path", "url.original"]),
            "httpStatus": first_value(src, ["http.response.status_code"]),
            "statement": statement,
        }
    )


def is_error_doc(src: Dict[str, Any]) -> bool:
    status = extract_status(src)
    if status is not None and status >= 400:
        return True
    level = str(first_value(src, LEVEL_FIELDS) or "")
    if level.upper() in {"ERROR", "FATAL", "SEVERE"}:
        return True
    text = str(first_value(src, ["message", "msg", "log", "content", "error.message", "exception"]) or "")
    return bool(ERROR_TEXT_RE.search(text))


def command_search(args: argparse.Namespace) -> int:
    client = make_client(args)
    start, end = time_window(args)
    body = {
        "query": build_query(args, start, end),
        "size": int(args.size),
        "sort": [{time_field(args): {"order": args.sort}}],
        "track_total_hits": True,
    }
    if args.show_query:
        print(json.dumps(redact(body), ensure_ascii=False, indent=2))
        return 0
    result = client.request("POST", f"/{urllib.parse.quote(index_pattern(args), safe='*,')}/_search", body)
    hits = result.get("hits", {}).get("hits", [])
    total = result.get("hits", {}).get("total", {})
    total_value = total.get("value") if isinstance(total, dict) else total
    output = {
        "ok": True,
        "action": "search",
        "index": index_pattern(args),
        "timeField": time_field(args),
        "window": {"from": start, "to": end, "timezone": "Asia/Shanghai"},
        "conditions": {
            "q": args.q,
            "service": args.service,
            "api": args.api,
            "trace": args.trace,
            "order": args.order,
            "level": args.level,
        },
        "totalHits": total_value,
        "returned": len(hits),
        "samples": [
            {"index": hit.get("_index"), "id": hit.get("_id"), **summarize_doc(hit_source(hit))}
            for hit in hits
        ],
    }
    print(json.dumps(redact(output), ensure_ascii=False, indent=2))
    return 0


def command_api_status(args: argparse.Namespace) -> int:
    client = make_client(args)
    start, end = time_window(args)
    args.sort = "desc"
    body = {
        "query": build_query(args, start, end),
        "size": int(args.size),
        "sort": [{time_field(args): {"order": "desc"}}],
        "track_total_hits": True,
    }
    if args.show_query:
        print(json.dumps(redact(body), ensure_ascii=False, indent=2))
        return 0
    result = client.request("POST", f"/{urllib.parse.quote(index_pattern(args), safe='*,')}/_search", body)
    hits = result.get("hits", {}).get("hits", [])
    total = result.get("hits", {}).get("total", {})
    total_value = total.get("value") if isinstance(total, dict) else total
    docs = [hit_source(hit) for hit in hits]
    slow_ms = float(args.slow_ms)
    error_docs = [doc for doc in docs if is_error_doc(doc)]
    slow_docs = [doc for doc in docs if (extract_latency_ms(doc) or 0) >= slow_ms]
    latencies = sorted([x for x in (extract_latency_ms(doc) for doc in docs) if x is not None])
    statuses: Dict[str, int] = {}
    for doc in docs:
        status = extract_status(doc)
        key = "unknown" if status is None else str(status)
        statuses[key] = statuses.get(key, 0) + 1
    output = {
        "ok": True,
        "action": "api-status",
        "index": index_pattern(args),
        "timeField": time_field(args),
        "window": {"from": start, "to": end, "timezone": "Asia/Shanghai"},
        "conditions": {
            "api": args.api,
            "service": args.service,
            "q": args.q,
            "trace": args.trace,
            "order": args.order,
        },
        "totalHits": total_value,
        "sampled": len(docs),
        "errorCount": len(error_docs),
        "errorRate": rate(len(error_docs), len(docs)),
        "slowThresholdMs": slow_ms,
        "slowCount": len(slow_docs),
        "slowRate": rate(len(slow_docs), len(docs)),
        "statusBuckets": statuses,
        "latencyMs": latency_stats(latencies),
        "latestErrorSamples": [summarize_doc(doc) for doc in error_docs[:5]],
        "latestSlowSamples": [summarize_doc(doc) for doc in slow_docs[:5]],
        "latestSamples": [summarize_doc(doc) for doc in docs[:5]],
    }
    print(json.dumps(redact(output), ensure_ascii=False, indent=2))
    return 0


def command_apm_trace(args: argparse.Namespace) -> int:
    client = make_client(args)
    start, end = time_window(args)
    body = {
        "query": build_apm_query(args, start, end),
        "size": int(args.size),
        "sort": [{time_field(args): {"order": args.sort}}],
        "track_total_hits": True,
        "_source": APM_SOURCE_FIELDS,
    }
    if args.show_query:
        print(json.dumps(redact(body), ensure_ascii=False, indent=2))
        return 0
    result = client.request("POST", f"/{urllib.parse.quote(apm_index_pattern(args), safe='*,.')}/_search", body)
    hits = result.get("hits", {}).get("hits", [])
    total = result.get("hits", {}).get("total", {})
    total_value = total.get("value") if isinstance(total, dict) else total
    docs = [hit_source(hit) for hit in hits]
    transaction_docs = [doc for doc in docs if first_value(doc, ["processor.event"]) == "transaction"]
    span_docs = [doc for doc in docs if first_value(doc, ["processor.event"]) == "span"]
    db_docs = [doc for doc in span_docs if first_value(doc, ["span.type"]) == "db"]
    db_latencies = sorted([x for x in (apm_duration_ms(doc) for doc in db_docs) if x is not None])

    statement_buckets: Dict[str, Dict[str, Any]] = {}
    for doc in db_docs:
        summary = summarize_apm_doc(doc)
        key = summary.get("statement") or summary.get("spanName") or "unknown"
        key = str(key)[:180]
        bucket = statement_buckets.setdefault(
            key,
            {
                "statement": key,
                "spanName": summary.get("spanName"),
                "subtype": summary.get("spanSubtype"),
                "count": 0,
                "totalMs": 0.0,
                "maxMs": 0.0,
            },
        )
        duration = float(summary.get("durationMs") or 0)
        bucket["count"] += 1
        bucket["totalMs"] = round(float(bucket["totalMs"]) + duration, 3)
        bucket["maxMs"] = round(max(float(bucket["maxMs"]), duration), 3)
    top_statements = sorted(statement_buckets.values(), key=lambda item: (item["totalMs"], item["maxMs"]), reverse=True)
    top_db_docs = sorted(db_docs, key=lambda doc: apm_duration_ms(doc) or 0, reverse=True)

    output = {
        "ok": True,
        "action": "apm-trace",
        "index": apm_index_pattern(args),
        "timeField": time_field(args),
        "window": {"from": start, "to": end, "timezone": "Asia/Shanghai"},
        "conditions": {
            "q": args.q,
            "service": args.service,
            "api": args.api,
            "trace": args.trace,
            "dbOnly": args.db_only,
        },
        "totalHits": total_value,
        "sampled": len(docs),
        "transactionCount": len(transaction_docs),
        "spanCount": len(span_docs),
        "dbSpanCount": len(db_docs),
        "dbSpanTotalMs": round(sum(db_latencies), 3) if db_latencies else 0,
        "dbSpanLatencyMs": latency_stats(db_latencies),
        "transactions": [summarize_apm_doc(doc) for doc in transaction_docs[:10]],
        "topDbSpans": [summarize_apm_doc(doc) for doc in top_db_docs[:20]],
        "topDbStatements": top_statements[:20],
        "samples": [summarize_apm_doc(doc) for doc in docs[:10]],
    }
    print(json.dumps(redact(output), ensure_ascii=False, indent=2))
    return 0


def rate(count: int, total: int) -> str:
    if total <= 0:
        return "0.00%"
    return f"{count * 100.0 / total:.2f}%"


def percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    idx = int(round((pct / 100.0) * (len(values) - 1)))
    return round(values[max(0, min(idx, len(values) - 1))], 2)


def latency_stats(values: List[float]) -> Dict[str, Optional[float]]:
    return {
        "count": len(values),
        "min": percentile(values, 0),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": percentile(values, 100),
    }


def command_indices(args: argparse.Namespace) -> int:
    client = make_client(args)
    pattern = args.pattern or index_pattern(args)
    path = f"/_cat/indices/{urllib.parse.quote(pattern, safe='*,')}?format=json&s=docs.count:desc"
    rows = client.request("GET", path)
    limit = int(args.limit)
    output = {
        "ok": True,
        "action": "indices",
        "pattern": pattern,
        "returned": min(len(rows), limit) if isinstance(rows, list) else 0,
        "indices": rows[:limit] if isinstance(rows, list) else rows,
    }
    print(json.dumps(redact(output), ensure_ascii=False, indent=2))
    return 0


def command_fields(args: argparse.Namespace) -> int:
    client = make_client(args)
    index = args.index or index_pattern(args)
    path = f"/{urllib.parse.quote(index, safe='*,')}/_field_caps?fields=*"
    result = client.request("GET", path)
    fields = sorted((result.get("fields") or {}).keys())
    if args.filter:
        pattern = re.compile(args.filter, re.I)
        fields = [field for field in fields if pattern.search(field)]
    output = {
        "ok": True,
        "action": "fields",
        "index": index,
        "filter": args.filter,
        "fieldCount": len(fields),
        "fields": fields[: int(args.limit)],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", help="Elasticsearch URL; defaults to WFT_PROD_ES_URL or bundled production URL")
    parser.add_argument("--user", help="Elasticsearch user; defaults to WFT_PROD_ES_USER or elastic")
    parser.add_argument("--password", help="Elasticsearch password; defaults to WFT_PROD_ES_PASS or bundled local fallback")
    parser.add_argument("--index", help="Index pattern; defaults to WFT_PROD_ES_INDEX or WFT log patterns")
    parser.add_argument("--time-field", help="Time field; defaults to WFT_PROD_ES_TIME_FIELD or @timestamp")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")


def add_time_and_conditions(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--minutes", type=int, default=30, help="Look back window when --from is omitted")
    parser.add_argument("--from", dest="from_time", help="Start time, e.g. 2026-06-22T10:00:00+08:00")
    parser.add_argument("--to", dest="to_time", help="End time, e.g. 2026-06-22T10:30:00+08:00")
    parser.add_argument("--q", help="General keyword query")
    parser.add_argument("--service", help="Service/app/container/pod name")
    parser.add_argument("--api", help="API path or route")
    parser.add_argument("--trace", help="Trace ID or request ID")
    parser.add_argument("--order", help="Order ID or business ID")
    parser.add_argument("--level", help="Log level such as ERROR")
    parser.add_argument("--show-query", action="store_true", help="Print ES query body and exit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only production Elasticsearch log search for WFT.")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search production logs")
    add_common(search)
    add_time_and_conditions(search)
    search.add_argument("--size", type=int, default=50, help="Max hits to return")
    search.add_argument("--sort", choices=["asc", "desc"], default="desc", help="Time sort order")
    search.set_defaults(func=command_search)

    api = sub.add_parser("api-status", help="Summarize API runtime status from production logs")
    add_common(api)
    add_time_and_conditions(api)
    api.add_argument("--size", type=int, default=500, help="Max sampled hits")
    api.add_argument("--slow-ms", type=float, default=2000, help="Slow request threshold in milliseconds")
    api.set_defaults(func=command_api_status)

    apm = sub.add_parser("apm-trace", help="Summarize Elastic APM transactions and DB spans")
    add_common(apm)
    add_time_and_conditions(apm)
    apm.add_argument("--size", type=int, default=200, help="Max sampled APM documents")
    apm.add_argument("--sort", choices=["asc", "desc"], default="asc", help="Time sort order")
    apm.add_argument("--db-only", action="store_true", help="Return only db spans such as MySQL and Redis")
    apm.set_defaults(func=command_apm_trace)

    indices = sub.add_parser("indices", help="List candidate log indices")
    add_common(indices)
    indices.add_argument("--pattern", help="Index pattern to inspect")
    indices.add_argument("--limit", type=int, default=30, help="Max indices to return")
    indices.set_defaults(func=command_indices)

    fields = sub.add_parser("fields", help="List index field names")
    add_common(fields)
    fields.add_argument("--filter", help="Regex filter for field names")
    fields.add_argument("--limit", type=int, default=200, help="Max fields to return")
    fields.set_defaults(func=command_fields)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except EsError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
