from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from payment_python_tests.ai.assistant import analyze_failure


def build_markdown_report(
    records: list[dict[str, Any]], title: str = "支付通道自动化证据报告"
) -> str:
    counts = Counter(record.get("kind", "unknown") for record in records)
    orders = sorted(
        {record.get("order_no", "") for record in records if record.get("order_no")}
    )
    analysis = analyze_failure(records)
    lines = [
        f"# {title}",
        "",
        f"- 证据条数：{len(records)}",
        f"- 涉及订单：{', '.join(orders) or '无'}",
        f"- 初步分析：{analysis['summary']}",
        "",
        "## 证据类型",
        "",
    ]
    lines.extend(f"- {kind}: {count}" for kind, count in sorted(counts.items()))
    lines.extend(["", "## 时间线", ""])
    for record in records:
        payload = json.dumps(
            record.get("payload"), ensure_ascii=False, default=str
        )
        lines.append(
            f"- `{record.get('created_at', '')}` `{record.get('kind', '')}` "
            f"`{record.get('order_no', '')}`: {payload[:500]}"
        )
    return "\n".join(lines) + "\n"


def save_markdown_report(
    records: list[dict[str, Any]], path: str | Path
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_markdown_report(records), encoding="utf-8")
    return target
