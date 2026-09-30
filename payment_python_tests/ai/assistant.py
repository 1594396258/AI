from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from payment_python_tests.api.base_api import BaseApi
from payment_python_tests.config.settings import AiSettings, AppSettings


def generate_contract_draft(
    samples: list[dict[str, Any]], *, channel: str
) -> dict[str, Any]:
    fields = set().union(*(sample.keys() for sample in samples)) if samples else set()
    identity = {
        "local_order_field": (
            "merchantOrderId" if "merchantOrderId" in fields else "orderNo"
        ),
        "channel_order_field": (
            "transactionId" if "transactionId" in fields else "channelOrderNo"
        ),
    }
    amount_field = "amount" if "amount" in fields else "tradeAmount"
    return {
        "channel": channel,
        "service": "",
        "query_service": "",
        "identity": identity,
        "amount": {"field": amount_field, "unit": "REVIEW_REQUIRED"},
        "status": {
            "field": "status",
            "mapping": {
                "pending": "PROCESSING",
                "processing": "PROCESSING",
                "success": "SUCCESS",
                "failed": "FAIL",
            },
        },
        "signature": {"algorithm": "REVIEW_REQUIRED"},
        "outbound_request": {
            "method": "REVIEW_REQUIRED",
            "body": {
                field: {"source": "REVIEW_REQUIRED"} for field in sorted(fields)
            },
            "headers": {},
            "forbidden_fields": [],
        },
        "required_fields": sorted(fields),
    }


def save_contract_draft(draft: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(draft, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def analyze_failure(records: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = [record.get("kind", "") for record in records]
    hints = []
    if not records:
        hints.append("没有证据记录：检查 Java、Mock 地址和请求是否真正发出")
    if "merchant_notice" not in kinds:
        hints.append("没有商户通知：检查终态、notifyUrl、MQ 和通知重试")
    if any("callback" in kind for kind in kinds) and "database" not in kinds:
        hints.append("有回调但没有数据库证据：检查回调处理或数据库连接")
    if "channel_request" not in kinds and "merchant_request" in kinds:
        hints.append("有商户请求但没有通道出站请求：检查路由、通道配置和 Mock URL")
    return {
        "summary": "; ".join(hints) if hints else "证据链完整，继续检查断言详情",
        "record_count": len(records),
        "kinds": sorted(set(kinds)),
    }


class AiAssistant:
    def __init__(self, settings: AiSettings):
        if not settings.api_key or not settings.model:
            raise RuntimeError("AI_API_KEY/OPENAI_API_KEY and AI_MODEL are required")
        self.settings = settings
        self.client = BaseApi(
            settings.base_url,
            timeout=60,
            default_headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
            },
        )

    @classmethod
    def from_app_settings(cls, settings: AppSettings) -> "AiAssistant":
        return cls(settings.ai)

    def ask(self, prompt: str) -> str:
        response = self.client.post(
            "chat/completions",
            json={
                "model": self.settings.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是支付测试配置审查助手。只能根据输入证据给建议，"
                            "不能编造字段、状态或签名规则。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def review_contract_with_ai(draft: dict[str, Any]) -> str:
    assistant = AiAssistant.from_app_settings(AppSettings.from_env())
    return assistant.ask(
        "审查支付通道契约初稿。指出必须人工确认的字段映射、金额单位、状态、"
        "签名、回调 ACK 和异常测试，不要改写未确认事实。\n"
        + json.dumps(draft, ensure_ascii=False, indent=2)
    )


def analyze_failure_with_ai(records: list[dict[str, Any]]) -> str:
    assistant = AiAssistant.from_app_settings(AppSettings.from_env())
    return assistant.ask(
        "根据脱敏测试证据，按可能性给出失败阶段、依据和下一步检查项。"
        "证据不足时必须说明，不要猜测密钥。\n"
        + json.dumps(records, ensure_ascii=False, default=str, indent=2)
    )
