from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    category: str
    title: str
    cause: str
    actions: tuple[str, ...]
    severity: str = "medium"
    confidence: int = 82


def _rule(
    pattern: str,
    category: str,
    title: str,
    cause: str,
    actions: tuple[str, ...],
    severity: str = "medium",
    confidence: int = 82,
) -> Rule:
    return Rule(re.compile(pattern, re.IGNORECASE), category, title, cause, actions, severity, confidence)


RULES: tuple[Rule, ...] = (
    _rule(
        r"outofmemory|heap space|memoryerror|oomkilled|cannot allocate memory",
        "资源",
        "内存耗尽",
        "进程申请内存失败，可能由内存泄漏、一次性加载过多数据或容器内存上限过低引起。",
        ("检查报错时刻的内存曲线和 OOM/Kill 事件", "获取堆转储或对象统计，定位持续增长的对象", "限制批次大小；确认无泄漏后再调整内存上限"),
        "critical",
        94,
    ),
    _rule(
        r"no space left on device|disk quota exceeded|enospc",
        "资源",
        "磁盘空间耗尽",
        "磁盘或 inode 已用尽，导致日志、临时文件或数据库无法继续写入。",
        ("检查磁盘和 inode 使用率", "清理可安全删除的历史日志与临时文件", "为日志配置轮转和容量告警"),
        "critical",
        96,
    ),
    _rule(
        r"deadlock found|deadlock detected|lock wait timeout",
        "数据库",
        "数据库死锁或锁等待超时",
        "并发事务以不同顺序持有资源，或长事务长期占锁。",
        ("查看数据库死锁日志和阻塞会话", "统一事务内的表与记录访问顺序", "缩短事务并为可重试操作增加带抖动的退避重试"),
        "high",
        94,
    ),
    _rule(
        r"duplicate entry|duplicate key|unique constraint|ora-00001",
        "数据库",
        "唯一键冲突",
        "写入的数据与唯一索引中的现有记录重复，常见于重复请求、幂等控制缺失或主键生成异常。",
        ("从报错中确认冲突的索引和键值", "检查请求是否被重复提交或重试", "按业务语义增加幂等键、upsert 或冲突处理"),
        "medium",
        95,
    ),
    _rule(
        r"too many connections|max connections|connection pool.*exhaust|pool timeout",
        "数据库",
        "数据库连接池耗尽",
        "连接未及时释放、慢查询堆积或连接池容量与并发量不匹配。",
        ("检查连接池活跃数、等待数和连接泄漏指标", "确认连接在 finally/上下文管理器中被释放", "定位慢查询，之后再评估池容量"),
        "high",
        92,
    ),
    _rule(
        r"(sqlstate|database|jdbc|mysql|postgres|oracle).*(connection refused|connection reset|could not connect|communications link failure)|ora-125(?:14|41)",
        "数据库",
        "数据库连接失败",
        "数据库服务不可达、监听异常、网络被拦截，或连接地址/端口配置错误。",
        ("从应用所在主机测试数据库地址和端口连通性", "核对连接串、DNS、端口与数据库监听状态", "检查防火墙、安全组和数据库连接数"),
        "high",
        91,
    ),
    _rule(
        r"connection refused|econnrefused|connectex.*actively refused",
        "网络",
        "目标服务拒绝连接",
        "目标端口没有进程监听，服务尚未就绪，或请求使用了错误的主机/端口。",
        ("确认目标服务实例健康且端口正在监听", "核对环境变量中的主机、端口和协议", "检查容器 Service/Ingress 映射及启动依赖"),
        "high",
        93,
    ),
    _rule(
        r"timed? out|timeout(?:exception)?|etimedout|deadline exceeded|504 gateway",
        "超时",
        "请求或任务执行超时",
        "下游响应过慢、网络不稳定、资源竞争或超时阈值小于正常处理耗时。",
        ("用 traceId 定位耗时最长的下游调用或 SQL", "对比连接超时与读取超时，确认超时发生阶段", "先优化瓶颈，再按延迟分位数调整超时和重试策略"),
        "high",
        86,
    ),
    _rule(
        r"name or service not known|unknownhost|nodename nor servname|enotfound|getaddrinfo failed|temporary failure in name resolution",
        "网络",
        "DNS 解析失败",
        "域名不存在、DNS 配置异常或运行环境暂时无法访问 DNS 服务。",
        ("在同一运行环境中执行域名解析测试", "核对域名拼写、搜索域和 DNS 配置", "检查集群 DNS 健康状态及网络策略"),
        "high",
        94,
    ),
    _rule(
        r"certificate verify failed|sslhandshakeexception|unable to find valid certification path|certificate has expired|self.signed certificate",
        "安全/网络",
        "TLS 证书校验失败",
        "证书过期、主机名不匹配、证书链不完整，或客户端不信任签发机构。",
        ("检查服务端证书有效期、域名和完整证书链", "更新客户端信任库或 CA 证书", "不要通过关闭证书校验来长期规避问题"),
        "high",
        95,
    ),
    _rule(
        r"(?:http[^\n]*\s)?401\b|unauthorized|invalid (?:token|signature)|token.*expired",
        "鉴权",
        "身份认证失败",
        "凭据缺失、无效或已过期，也可能是签名算法、时钟或请求头不一致。",
        ("确认 Authorization 头是否发送且格式正确", "检查 token 有效期、签发方、受众和服务器时钟", "核对签名密钥、算法与参与签名的字段"),
        "high",
        88,
    ),
    _rule(
        r"(?:http[^\n]*\s)?403\b|forbidden|access denied",
        "鉴权",
        "权限不足",
        "身份已识别，但缺少访问资源所需的角色、策略或数据权限。",
        ("确认当前账号/服务账号拥有目标资源权限", "检查网关、IAM/RBAC 和业务权限规则", "对比成功请求的身份与权限上下文"),
        "high",
        87,
    ),
    _rule(
        r"429\b|too many requests|rate limit|throttl",
        "流量",
        "触发限流",
        "请求频率或并发超过服务配额，或者所有实例共享的额度被集中消耗。",
        ("读取响应中的重试时间和限流维度", "使用指数退避与随机抖动，避免立即重试", "降低并发、合并请求或申请合理配额"),
        "medium",
        94,
    ),
    _rule(
        r"nullpointerexception|cannot invoke .* because .* is null",
        "代码",
        "Java 空指针异常",
        "代码使用了未初始化或意外为空的对象；第一条业务代码堆栈通常是最直接的定位点。",
        ("定位堆栈中第一条项目代码并检查该行各对象", "沿调用链确认哪个输入或查询结果可能为空", "在边界处校验输入并为合法空值设计明确处理"),
        "high",
        96,
    ),
    _rule(
        r"attributeerror:.*nonetype|cannot read propert(?:y|ies) .* of (?:undefined|null)|typeerror:.*(?:undefined|null)",
        "代码",
        "空对象属性访问",
        "变量得到 null/None/undefined 后仍继续读取属性，通常源于未命中的查询、缺失字段或异常分支。",
        ("从首个业务堆栈帧确认哪个变量为空", "检查其来源函数在未命中或失败时的返回值", "补充输入校验与可解释的错误处理，并新增回归测试"),
        "high",
        95,
    ),
    _rule(
        r"keyerror:|nosuchelementexception|cannot find key",
        "代码",
        "缺少预期字段或元素",
        "代码假设键或元素必然存在，但实际输入、配置或查询结果不满足该假设。",
        ("打印或检查脱敏后的实际输入结构", "确认字段名、大小写和接口版本", "对可选字段使用安全读取，并对必填字段提前校验"),
        "medium",
        92,
    ),
    _rule(
        r"modulenotfounderror|importerror|classnotfoundexception|noclassdeffounderror|cannot find module|module not found",
        "依赖",
        "依赖或模块缺失",
        "运行环境未安装依赖、依赖版本冲突，或模块搜索路径与开发环境不一致。",
        ("确认报错中的模块已写入依赖清单", "在实际运行环境检查已安装版本与模块路径", "重新构建干净环境并锁定依赖版本"),
        "high",
        96,
    ),
    _rule(
        r"jsondecodeerror|unexpected token.*json|invalid json|jackson.*(?:parse|mapping)|mismatchedinputexception",
        "数据格式",
        "JSON 解析或映射失败",
        "输入不是合法 JSON，或字段类型/结构与反序列化模型不匹配。",
        ("保留并校验脱敏后的原始响应体与 Content-Type", "根据错误位置检查截断、多余逗号、转义或 HTML 错误页", "校对接口契约和字段类型，为兼容字段增加测试"),
        "medium",
        92,
    ),
    _rule(
        r"filenotfounderror|no such file or directory|enoent",
        "文件",
        "文件或路径不存在",
        "运行时路径与预期不一致、文件未被打包/挂载，或使用了错误的相对路径。",
        ("打印并确认解析后的绝对路径", "检查部署包、工作目录和容器卷挂载", "对必要文件在启动阶段做存在性校验"),
        "medium",
        94,
    ),
    _rule(
        r"permissionerror|permission denied|eacces|access is denied",
        "权限",
        "操作系统权限不足",
        "当前进程用户无权读取、写入或执行目标资源，也可能被安全策略拦截。",
        ("确认进程实际用户和目标文件/端口权限", "检查父目录权限、只读挂载和安全策略", "授予最小必要权限，不要长期使用管理员权限运行"),
        "high",
        93,
    ),
    _rule(
        r"syntaxerror|compilation failed|syntax error at or near|ora-009(?:00|07|33|36)",
        "语法",
        "代码或 SQL 语法错误",
        "解析器在指示位置附近遇到不符合语法的内容，也可能是运行版本不支持该语法。",
        ("从错误位置向前检查括号、引号、逗号和关键字", "确认运行时/数据库版本支持所用语法", "用最小片段复现并增加编译或静态检查"),
        "medium",
        94,
    ),
    _rule(
        r"crashloopbackoff|back-off restarting failed container|liveness probe failed|readiness probe failed",
        "容器",
        "容器反复重启或探针失败",
        "应用启动失败、探针配置不匹配，或依赖尚未就绪导致容器被持续重启。",
        ("查看容器上一次退出日志和退出码", "检查启动命令、配置/Secret 和依赖服务", "核对探针路径、端口、初始延迟与超时"),
        "high",
        93,
    ),
)


SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|secret|password|passwd|pwd)\s*[=:]\s*)['\"]?[^\s,'\";&]+"), r"\1[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
)


TIMESTAMP_PATTERNS = (
    re.compile(r"\b(20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z| ?[+-]\d{2}:?\d{2})?)\b"),
    re.compile(r"\b(20\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\b"),
)


def sanitize_log(text: str) -> tuple[str, int]:
    sanitized = text
    replacements = 0
    for pattern, replacement in SECRET_PATTERNS:
        sanitized, count = pattern.subn(replacement, sanitized)
        replacements += count
    return sanitized, replacements


def _parse_timestamp(value: str) -> datetime | None:
    normalized = value.replace(",", ".").replace("/", "-").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized.replace(" ", "T", 1))
    except ValueError:
        return None


def _time_range(text: str) -> dict[str, str] | None:
    found: list[tuple[datetime, str]] = []
    for pattern in TIMESTAMP_PATTERNS:
        for value in pattern.findall(text):
            parsed = _parse_timestamp(value)
            if parsed:
                found.append((parsed, value))
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return {"start": found[0][1], "end": found[-1][1]}


def _level_counts(lines: list[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for line in lines:
        upper = line.upper()
        for level in ("FATAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE"):
            if re.search(rf"(?:^|[\s\[|:-]){level}(?:$|[\s\]|:-])", upper):
                counts[level] += 1
                break
    return dict(counts)


def _interesting_lines(lines: list[str], limit: int = 12) -> list[dict[str, Any]]:
    keywords = re.compile(
        r"exception|error|fatal|failed|failure|panic|traceback|caused by|timeout|timed out|denied|refused|oom|killed",
        re.IGNORECASE,
    )
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, line in enumerate(lines, 1):
        clean = line.strip()
        if not clean or not keywords.search(clean):
            continue
        signature = re.sub(r"\b\d+\b", "#", clean.lower())[:240]
        if signature in seen:
            continue
        seen.add(signature)
        found.append({"line": number, "text": clean[:500]})
        if len(found) >= limit:
            break
    return found


def _exception_types(text: str) -> list[dict[str, Any]]:
    patterns = (
        re.compile(r"\b([A-Za-z_][\w.]*(?:Exception|Error))(?::|\b)"),
        re.compile(r"\b(panic)(?::|\b)", re.IGNORECASE),
        re.compile(r"\b(ORA-\d{5})\b"),
        re.compile(r"\b(SQLSTATE\[?[A-Z0-9]+\]?)\b", re.IGNORECASE),
    )
    counts: Counter[str] = Counter()
    for pattern in patterns:
        for match in pattern.findall(text):
            name = match.split(".")[-1]
            counts[name] += 1
    return [{"name": name, "count": count} for name, count in counts.most_common(8)]


def _first_project_frame(lines: list[str]) -> str | None:
    frames: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.search(r'File "[^"]+", line \d+', stripped) or re.match(r"at\s+[\w.$<>]+\([^)]*:\d+\)", stripped):
            frames.append(stripped)
        elif re.match(r"at\s+[^\s]+\s+\([^)]*:\d+:\d+\)", stripped):
            frames.append(stripped)
    if not frames:
        return None
    ignored = re.compile(r"site-packages|node_modules|java\.|javax\.|sun\.|jdk\.|org\.springframework|reactor\.", re.IGNORECASE)
    return next((frame for frame in frames if not ignored.search(frame)), frames[0])[:500]


def _severity_rank(value: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(value, 1)


def analyze_log(text: str) -> dict[str, Any]:
    text = text.replace("\x00", "").strip()
    if not text:
        raise ValueError("日志内容不能为空")

    sanitized, redacted_count = sanitize_log(text)
    lines = sanitized.splitlines()
    matches: list[tuple[Rule, str, int]] = []
    for rule in RULES:
        found = rule.pattern.search(sanitized)
        if found:
            line_number = sanitized[: found.start()].count("\n") + 1
            evidence = lines[line_number - 1].strip()[:500]
            matches.append((rule, evidence, line_number))
    matches.sort(key=lambda item: (_severity_rank(item[0].severity), item[0].confidence), reverse=True)

    frame = _first_project_frame(lines)
    causes = []
    action_titles: set[str] = set()
    actions = []
    for rule, evidence, line_number in matches[:4]:
        causes.append(
            {
                "title": rule.title,
                "category": rule.category,
                "explanation": rule.cause,
                "confidence": rule.confidence,
                "evidence": f"第 {line_number} 行：{evidence}",
            }
        )
        for title in rule.actions:
            if title not in action_titles:
                actions.append({"priority": len(actions) + 1, "title": title})
                action_titles.add(title)
    if not causes:
        causes.append(
            {
                "title": "未匹配到明确的已知故障模式",
                "category": "待确认",
                "explanation": "日志信息可能不完整，或错误只在业务上下文中可解释。建议结合首次异常、请求参数和调用链继续定位。",
                "confidence": 35,
                "evidence": "当前日志中没有命中高置信度规则",
            }
        )
        actions = [
            {"priority": 1, "title": "补充错误发生前后 30～100 行日志"},
            {"priority": 2, "title": "用 traceId/requestId 串联完整调用链"},
            {"priority": 3, "title": "确认最近发布、配置和依赖变更"},
        ]

    primary = matches[0][0] if matches else None
    severity = primary.severity if primary else ("high" if re.search(r"fatal|panic|crash", sanitized, re.I) else "medium")
    confidence = primary.confidence if primary else 35
    summary = f"最可能是{causes[0]['title']}：{causes[0]['explanation']}"
    if frame:
        summary += f" 建议优先检查首个业务堆栈帧：{frame}"

    return {
        "summary": summary,
        "severity": severity,
        "confidence": confidence,
        "likely_causes": causes,
        "actions": actions[:8],
        "project_frame": frame,
        "evidence": _interesting_lines(lines),
        "exceptions": _exception_types(sanitized),
        "stats": {
            "lines": len(lines),
            "characters": len(sanitized),
            "levels": _level_counts(lines),
            "time_range": _time_range(sanitized),
            "redacted_items": redacted_count,
        },
        "sanitized_log": sanitized,
        "analysis_mode": "local",
    }

