# Author:HankQueen
# Date:2026/6/29

import json
import sys
from pathlib import Path

from openai import OpenAI

try:
    from AI_model.workspace_tools import TOOLS, execute_tool, list_files, read_file, search_code
except ModuleNotFoundError:
    from workspace_tools import TOOLS, execute_tool, list_files, read_file, search_code

try:
    from AI_model.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
except ModuleNotFoundError:
    from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
)


CURRENT_DIR = Path(__file__).resolve().parent
HISTORY_FILE = CURRENT_DIR / "chat_history.json"
SYSTEM_MESSAGE = {"role": "system", "content": "你是一个有帮助的中文代码助手。需要检查本地项目时，先使用 list_files、search_code 或 read_file 工具；不要假设自己能直接访问磁盘。工具是只读的。"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def ask_ai(messages):
    for round_number in range(6):
        request = {"model": OPENAI_MODEL, "messages": messages, "tools": TOOLS}
        # Require a tool call on the first turn so we can verify that the
        # OpenAI-compatible proxy really supports tool calling.
        if round_number == 0:
            request["tool_choice"] = "required"
        response = client.chat.completions.create(**request)
        if not hasattr(response, "choices"):
            raise RuntimeError("接口没有返回标准 OpenAI JSON，请检查 OPENAI_BASE_URL 是否以 /v1 结尾。")
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return message.content or ""
        for call in tool_calls:
            print(f"[模型请求工具] {call.function.name}({call.function.arguments})")
        messages.append({"role": "assistant", "content": message.content, "tool_calls": [call.model_dump() for call in tool_calls]})
        for call in tool_calls:
            try:
                result = execute_tool(call.function.name, call.function.arguments)
            except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
                result = json.dumps({"error": str(exc)}, ensure_ascii=False)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    raise RuntimeError("工具调用超过最大轮数")


def local_command(user_input):
    """Turn explicit slash commands into model context."""
    parts = user_input.split(maxsplit=1)
    command = parts[0].lower()
    argument = parts[1] if len(parts) > 1 else ""
    if command == "/tree":
        return "本地工作区文件列表：\n" + json.dumps(list_files(), ensure_ascii=False)
    if command == "/search" and argument:
        return "本地搜索结果：\n" + json.dumps(search_code(argument), ensure_ascii=False)
    if command == "/read" and argument:
        return "本地文件内容：\n" + json.dumps(read_file(argument), ensure_ascii=False)
    return None


def local_context_for_request(user_input):
    """Provide deterministic local context when the proxy ignores tool calls."""
    lowered = user_input.casefold()
    keyword_map = (
        ("redis", "redis"),
        ("数据库", "database"),
        ("接口", "api"),
        ("配置", "config"),
        ("代码", "class"),
    )
    query = next((query for keyword, query in keyword_map if keyword in lowered), None)
    if query is None:
        return None

    search_result = search_code(query, limit=20)
    print(f"[本地预读取兜底] 关键词: {query}")
    context_parts = ["本地代码上下文（由 Python 只读工具预先提供；不要再声称无法访问本地代码）："]
    context_parts.append(json.dumps(search_result, ensure_ascii=False))
    # Include a few matching files so this fallback also works with proxies
    # that accept chat completions but do not implement tool_calls.
    seen = set()
    for match in search_result["matches"]:
        path = match["path"]
        if path in seen or len(seen) >= 3:
            continue
        seen.add(path)
        try:
            context_parts.append(json.dumps(read_file(path, 1, 160), ensure_ascii=False))
        except (ValueError, OSError):
            continue
    return "\n".join(context_parts)


def read_user_input():
    """Read one message, or collect a pasted multi-line message."""
    first_line = input("你：")
    if first_line.strip().lower() not in {"/multi", "/paste"}:
        return first_line.strip()

    print("进入多行输入模式，粘贴内容后单独输入 /send 提交，输入 /cancel 取消。")
    lines = []
    while True:
        line = input("... ")
        command = line.strip().lower()
        if command == "/send":
            return "\n".join(lines).strip()
        if command == "/cancel":
            return ""
        lines.append(line)


def load_messages():
    if not HISTORY_FILE.exists():
        return [SYSTEM_MESSAGE.copy()]

    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as file:
            history = json.load(file)
    except (json.JSONDecodeError, OSError):
        return [SYSTEM_MESSAGE.copy()]

    if not isinstance(history, list):
        return [SYSTEM_MESSAGE.copy()]
    return [SYSTEM_MESSAGE.copy(), *history]


def save_messages(messages):
    history = [message for message in messages if message.get("role") != "system"]
    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)


def clear_messages():
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
    return [SYSTEM_MESSAGE.copy()]


def chat():
    messages = load_messages()

    print("开始和 AI 对话，输入 exit 或 quit 退出，输入 clear 清空历史；输入 /multi 可粘贴多行内容。")
    while True:
        user_input = read_user_input()
        if user_input.lower() in {"exit", "quit"}:
            print("已退出。")
            break
        if user_input.lower() == "clear":
            messages = clear_messages()
            print("历史已清空。")
            continue
        if not user_input:
            continue

        local_result = local_command(user_input)
        if local_result is not None:
            messages.append({"role": "user", "content": f"{user_input}\n\n{local_result}"})
        else:
            messages.append({"role": "user", "content": user_input})
        try:
            answer = ask_ai(messages)
        except Exception as exc:
            print(f"调用失败：{exc}")
            continue

        print(f"AI：{answer}")
        messages.append({"role": "assistant", "content": answer})
        save_messages(messages)


if __name__ == "__main__":
    chat()
