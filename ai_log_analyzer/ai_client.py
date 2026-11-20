from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def load_env_file(path: str | Path = ENV_FILE) -> bool:
    """读取项目配置；已有系统环境变量优先，不会被 .env 覆盖。"""

    return load_dotenv(dotenv_path=path, override=False)


# 无论从哪个工作目录启动 Uvicorn，都固定读取本项目目录中的 .env。
load_env_file()


@dataclass(frozen=True)
class AIConfig:
    base_url: str
    api_key: str
    model: str
    timeout: int

    @classmethod
    def from_env(cls) -> "AIConfig":
        timeout_value = os.getenv("AI_TIMEOUT", "60")
        try:
            timeout = int(timeout_value)
        except ValueError as exc:
            raise ValueError("AI_TIMEOUT 必须是整数秒") from exc
        return cls(
            base_url=os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            api_key=os.getenv("AI_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            model=os.getenv("AI_MODEL", "gpt-4.1-mini"),
            timeout=timeout,
        )

    @property
    def configured(self) -> bool:
        # Local OpenAI-compatible services (for example Ollama) often need no key.
        return bool(self.api_key) or self.base_url.startswith(("http://localhost", "http://127.0.0.1"))


SYSTEM_PROMPT = """你是一名资深 SRE 和软件故障分析专家。请基于给定日志和本地初步分析，谨慎判断故障根因。
要求：
1. 只使用日志中有证据支持的事实，不虚构服务、代码或配置。
2. 区分“直接错误”“深层根因”和“连带现象”；证据不足时明确说出需要补充什么。
3. 修复步骤必须具体、按优先级排列，并提供验证方法。
4. 如果提供了源码片段，必须把日志堆栈与具体文件、行号和代码逻辑关联起来；源码只代表局部上下文，不要假设未提供的实现。
5. 返回严格 JSON，不要 Markdown，字段固定为：
{
  "summary": "一句话结论",
  "root_cause": "根因解释",
  "reasoning": ["证据链1", "证据链2"],
  "actions": [{"title": "操作", "detail": "具体说明"}],
  "verification": ["验证方法"],
  "risk_notes": ["风险或不确定性"]
}
回答使用简体中文。"""


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型没有返回可解析的 JSON")
        value = json.loads(content[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型返回格式不是 JSON 对象")
    return value


def chat_completion(
    messages: list[dict[str, str]],
    config: AIConfig | None = None,
    *,
    max_tokens: int = 1800,
    temperature: float = 0.1,
) -> str:
    """调用 OpenAI 兼容的 Chat Completions，并返回文本内容。"""

    config = config or AIConfig.from_env()
    if not config.configured:
        raise RuntimeError("AI 未配置：请在 .env 设置 AI_API_KEY（或 OPENAI_API_KEY）")

    endpoint = config.base_url
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"AI 服务返回 HTTP {exc.code}：{detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"无法连接 AI 服务：{exc}") from exc

    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("AI 服务响应格式不兼容 Chat Completions") from exc


def analyze_with_ai(
    sanitized_log: str,
    local_report: dict[str, Any],
    config: AIConfig | None = None,
    code_context: str | None = None,
) -> dict[str, Any]:
    config = config or AIConfig.from_env()
    local_context = {key: value for key, value in local_report.items() if key != "sanitized_log"}
    # Keep the most relevant beginning and ending when a log is very large.
    if len(sanitized_log) > 80_000:
        sanitized_log = sanitized_log[:40_000] + "\n... [中间日志已截断] ...\n" + sanitized_log[-40_000:]
    user_prompt = (
        "本地规则分析：\n"
        + json.dumps(local_context, ensure_ascii=False)
        + "\n\n已脱敏日志：\n"
        + sanitized_log
    )
    if code_context:
        user_prompt += "\n\n与日志匹配的已脱敏源码片段：\n" + code_context
    content = chat_completion(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        config,
    )
    result = _extract_json(content)
    result["model"] = config.model
    return result

