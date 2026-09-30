from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests


def generate_contract_draft(samples: list[dict[str, Any]], *, channel: str, model: str = "") -> dict[str, Any]:
    """Generate a conservative contract draft locally; optionally delegate to an LLM later."""
    fields = set().union(*(sample.keys() for sample in samples)) if samples else set()
    identity = {"local_order_field": "merchantOrderId" if "merchantOrderId" in fields else "orderNo", "channel_order_field": "transactionId" if "transactionId" in fields else "channelOrderNo"}
    amount_field = "amount" if "amount" in fields else "tradeAmount"
    return {
        "channel": channel,
        "service": "",
        "query_service": "",
        "identity": identity,
        "amount": {"field": amount_field, "unit": "REVIEW_REQUIRED"},
        "status": {"field": "status", "mapping": {"pending": "PROCESSING", "processing": "PROCESSING", "success": "SUCCESS", "failed": "FAIL"}},
        "signature": {"algorithm": "REVIEW_REQUIRED"},
        "outbound_request": {
            "method": "REVIEW_REQUIRED",
            "body": {field: {"source": "REVIEW_REQUIRED"} for field in sorted(fields)},
            "headers": {},
            "forbidden_fields": [],
        },
        "required_fields": sorted(fields),
    }


def save_contract_draft(draft: dict[str, Any], path: str | Path) -> None:
    import yaml
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(yaml.safe_dump(draft, sort_keys=False, allow_unicode=True), encoding="utf-8")


def analyze_failure(records: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = [record.get("kind", "") for record in records]
    hints = []
    if not records:
        hints.append("没有证据记录：先检查 Java 服务、Mock 地址和测试是否真正发出请求")
    if "merchant_notice" not in kinds:
        hints.append("没有商户通知证据：检查订单是否到达终态、notifyUrl、MQ 和通知重试")
    if any("callback" in kind for kind in kinds) and "database" not in kinds:
        hints.append("有回调但没有数据库证据：检查回调处理异常或数据库连接")
    if "channel_request" not in kinds and "merchant_request" in kinds:
        hints.append("有商户请求但没有通道出站请求证据：检查 Java 路由、通道配置或 Mock URL")
    return {"summary": "; ".join(hints) if hints else "证据链完整，继续检查断言详情", "record_count": len(records), "kinds": sorted(set(kinds))}


def ask_llm(
    prompt: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    timeout: float = 60,
) -> str:
    """Call an OpenAI-compatible chat endpoint only when explicitly requested."""
    key = api_key or os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    selected_model = model or os.getenv("AI_MODEL")
    if not key or not selected_model:
        raise RuntimeError("AI 增强需要配置 AI_API_KEY/OPENAI_API_KEY 和 AI_MODEL")
    endpoint = (base_url or os.getenv("AI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    response = requests.post(
        f"{endpoint}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": selected_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "你是支付测试配置审查助手。只能根据输入证据给建议，不能编造字段、状态或签名规则。输出简洁中文。"},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def review_contract_with_ai(draft: dict[str, Any]) -> str:
    prompt = (
        "审查下面的支付通道 YAML 初稿对应数据。指出必须人工确认的字段映射、金额单位、"
        "状态映射、签名规则、回调 ACK，以及建议补充的异常测试。不要改写未确认事实。\n"
        + json.dumps(draft, ensure_ascii=False, indent=2)
    )
    return ask_llm(prompt)


def analyze_failure_with_ai(records: list[dict[str, Any]]) -> str:
    prompt = (
        "根据下面的脱敏支付测试证据，按可能性从高到低给出失败阶段、证据依据和下一步检查项。"
        "如果证据不足必须明确说明。不要输出或猜测密钥。\n"
        + json.dumps(records, ensure_ascii=False, default=str, indent=2)
    )
    return ask_llm(prompt)
