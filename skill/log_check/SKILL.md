---
name: wft-prod-log-check
description: WFT production Elasticsearch log and Elastic APM investigation for production incidents. Use when Codex needs to search production logs by order ID, trace ID, request path, service name, error text, time window, or other conditions; summarize API error/slow-request status; inspect Elastic APM transaction/span SQL or Redis timing; inspect log/APM indices or fields; or handle Chinese triggers such as 生产日志, 查生产日志, 排查生产问题, 接口运行情况, 接口报错, 错误率, 慢接口, SQL耗时, APM, traceId, orderId.
---

# WFT Prod Log Check

This skill is an AI execution contract for read-only production log investigation through Elasticsearch.

## Hard Rules

- Use this skill only for production log search and API runtime diagnosis from logs.
- Use the bundled script instead of ad hoc Elasticsearch queries.
- Keep every query bounded by time and result size.
- Do not print credentials, Authorization headers, or full sensitive payloads in final answers.
- Do not run destructive Elasticsearch operations such as delete, update, reindex, close index, reroute, allocation changes, or cluster setting changes.
- Do not call production business APIs unless the user explicitly asks for an HTTP call and provides the target URL/method.
- Treat findings as evidence-based. Do not claim an interface is healthy without hit counts, error counts, slow counts, or sample log evidence.

## Skill Directory

Resolve paths from this skill folder. Default Windows location:

```powershell
$SkillDir = "$env:USERPROFILE\.codex\skills\wft-prod-log-check"
```

## Fixed Defaults

| Setting | Default |
| --- | --- |
| Elasticsearch | `https://elasticsearch-k8s-hwy.wallyt.com` |
| Auth | bundled `elastic` account defaults; override with env vars when needed |
| Index pattern | `logs-*` |
| APM index pattern | `.ds-traces-apm-default-*` |
| Time field | `@timestamp` |
| Time window | user-provided range; otherwise last 30 minutes |
| Log search size | 50 hits |
| API health sample size | 500 hits |
| APM trace sample size | 200 hits |
| Slow request threshold | 2000 ms |
| Timezone for display | `Asia/Shanghai` |

Environment overrides:

```powershell
$env:WFT_PROD_ES_URL = "https://elasticsearch-k8s-hwy.wallyt.com"
$env:WFT_PROD_ES_USER = "elastic"
$env:WFT_PROD_ES_PASS = "..."
$env:WFT_PROD_ES_INDEX = "custom-index-*"
$env:WFT_PROD_APM_INDEX = ".ds-traces-apm-default-*"
$env:WFT_PROD_ES_TIME_FIELD = "@timestamp"
```

## Route Table

| User intent | Required action | Command |
| --- | --- | --- |
| Search logs by keyword/order/trace/error | Run bounded log search | `python "$SkillDir\scripts\es_prod_log_check.py" search --q "keyword"` |
| Search logs for an API path | Add `--api` and optional `--service` | `python "$SkillDir\scripts\es_prod_log_check.py" search --api "/cms/xxx" --minutes 30` |
| Check interface runtime status | Summarize count/error/slow/latest samples | `python "$SkillDir\scripts\es_prod_log_check.py" api-status --api "/cms/xxx"` |
| Check APM transaction or SQL/Redis span timing | Run `apm-trace` with trace/service/API and bounded time | `python "$SkillDir\scripts\es_prod_log_check.py" apm-trace --trace "<trace>" --from "<start>" --to "<end>"` |
| Find candidate log indices | Inspect index names and doc counts | `python "$SkillDir\scripts\es_prod_log_check.py" indices --pattern "*log*"` |
| Discover field names | Inspect field capabilities | `python "$SkillDir\scripts\es_prod_log_check.py" fields --index "*log*" --filter "trace"` |

## Workflow

1. Extract conditions from the user request:
   - Time: explicit range, "今天", "最近 N 分钟/小时", or default last 30 minutes.
   - Scope: API path, service/app name, order ID, trace ID, merchant/user ID, error text.
   - Output need: raw samples, error summary, slow-request summary, or timeline.
2. If the user says "今天", convert it to today's `00:00:00+08:00` through now. If the user provides a Kibana UTC range, preserve that exact range.
3. If the user gives no result limit, keep the script default. Increase `--size` only when needed and keep it under 200 for raw search.
4. For API status, use `api-status` first. Then use `search` for the most relevant error/slow samples.
5. For SQL/Redis timing from Elastic APM, use `apm-trace` against `.ds-traces-apm-default-*`. Prefer a specific APM `trace.id`; otherwise use service/API plus a narrow time window. Treat "no APM hits" separately from "no slow SQL": APM retention, sampling, or ingestion gaps can make span data absent.
6. If no hits are found, run `indices` or `fields` to check whether the index pattern or time field is wrong before concluding there is no issue.
7. Present concise evidence:
   - Time window, index pattern, query conditions.
   - Total hits or sampled hits.
   - Error count/rate and slow count/rate when checking an API.
   - For APM SQL timing: transaction duration, `span.type=db` count, top DB spans, top SQL statements, and whether data may be missing due to sampling/retention.
   - 3-5 representative log samples with sensitive values redacted.
   - Conclusion and next checks.

## Examples

Search production logs for an order ID in the last hour:

```powershell
python "$SkillDir\scripts\es_prod_log_check.py" search --q "PAY202606220001" --minutes 60
```

Check an interface's recent runtime status:

```powershell
python "$SkillDir\scripts\es_prod_log_check.py" api-status --api "/cms/merchantAccount/list" --minutes 30 --slow-ms 2000
```

Check Elastic APM SQL/Redis timing for a trace:

```powershell
python "$SkillDir\scripts\es_prod_log_check.py" apm-trace --trace "947773b41a7cd4b1147f65a4da602463" --from "2026-06-17T16:49:00+08:00" --to "2026-06-17T16:50:00+08:00"
```

Check only DB spans for a service/API window:

```powershell
python "$SkillDir\scripts\es_prod_log_check.py" apm-trace --service "finance-admin-service" --api "/gateway/base/fin/pay/single/list" --from "2026-06-19T14:40:00+08:00" --to "2026-06-19T14:47:00+08:00" --db-only
```

Search a trace ID with the same style as Kibana Discover:

```powershell
python "$SkillDir\scripts\es_prod_log_check.py" search --index "logs-*" --trace "21de799c7552358acd3d0ad3d52782a3" --from "2026-06-18T16:00:00.000Z" --to "2026-06-19T15:50:00.000Z"
```

## Reference

Read `references/query-patterns.md` when query results look incomplete, field names need tuning, or the final report needs a structured incident-style summary.
