# Query Patterns

Use this reference only when the default script behavior needs interpretation or tuning.

## Common Field Candidates

The script searches across these common field families:

- Time: `@timestamp`, `timestamp`, `time`, `log_time`, `createTime`, `created_at`
- Message: `message`, `msg`, `log`, `content`, `error.message`, `error.stack_trace`, `req.error_message`, `exception`, `stack_trace`
- Service/pod: `app.pod`, `app.name`, `service.name`, `service`, `req.service_name`, `app`, `appName`, `application`, `kubernetes.container.name`, `kubernetes.pod.name`
- API path: `url.path`, `request.path`, `req.path`, `request_uri`, `uri`, `path`, `api`, `interface`, `http.target`
- Trace: `trace.id`, `x_sp_trace_id`, `traceId`, `trace_id`, `X-B3-TraceId`, `requestId`, `request_id`
- Status: `http.response.status_code`, `req.status`, `status`, `statusCode`, `response.status`, `code`, `respCode`
- Latency: `request_time`, `upstream_response_time`, `req.duration_millis`, `req.duration_millis3`, `event.duration`, `duration`, `duration_ms`, `elapsed`, `elapsed_ms`, `latency`, `latency_ms`, `cost`, `costTime`, `timeCost`, `rt`
- Level: `log.level`, `level`, `severity`, `logger_level`
- APM: `processor.event`, `transaction.name`, `transaction.duration.us`, `span.type`, `span.subtype`, `span.name`, `span.duration.us`, `span.db.statement`, `span.db.instance`, `destination.address`

## Default Query Strategy

- Use a range filter on the selected time field.
- Use exact `match_phrase` on `trace.id` plus fallback trace fields for trace IDs.
- Use phrase checks against likely API fields plus a generic text clause for API paths.
- Fetch recent hits sorted by time descending.
- Compute API status locally from sampled documents because production mappings can differ across log pipelines.

## API Health Interpretation

Classify a sampled log as error when any of these are true:

- HTTP-like status is `>= 400`.
- Log level is `ERROR`, `FATAL`, or `SEVERE`.
- Message contains obvious failure terms such as `Exception`, `timeout`, `failed`, `error`, `失败`, `异常`, `超时`.

Classify a sampled log as slow when extracted latency is greater than or equal to `--slow-ms`.

## Elastic APM SQL Timing

Use `apm-trace` when the user asks for SQL耗时, Redis耗时, span, transaction, or "接口里面" timing. The command reads `.ds-traces-apm-default-*` by default.

- `processor.event=transaction` documents show request/transaction duration.
- `processor.event=span` with `span.type=db` shows SQL/Redis/cache calls.
- `span.duration.us` and `transaction.duration.us` are microseconds; the script reports milliseconds.
- MySQL SQL text is usually in `span.db.statement`; values are parameterized or redacted in output.
- Absence of APM hits does not prove the request had no slow SQL. Check retention, sampling, ingestion gaps, and whether the log `trace.id` is the same as Elastic APM `trace.id`.
- When business logs and APM traces use different trace IDs, use a narrow time window plus `service.name`, `url.path`, `transaction.name`, or pod name.

## Final Report Shape

Use this structure when reporting production investigation results:

```text
任务: checked <api/keyword> production logs
时间窗口: <from> ~ <to>, timezone Asia/Shanghai
条件: index=<pattern>, service=<service>, api=<api>, q=<keyword>
证据:
- totalHits=<n>, sampled=<n>
- errors=<n> (<rate>), slow>=<ms>=<n> (<rate>)
- latest error samples: <time> <service> <status> <message summary>
- APM SQL: transactionCount=<n>, dbSpanCount=<n>, topDbSpans=<duration/name/statement>
结论: <healthy/degraded/failing/no evidence found>
下一步: <one or two concrete checks only if unresolved>
```

Do not paste full stack traces by default. Summarize stack traces and include the exception class, top application frame, request path, and trace/order ID when present.
