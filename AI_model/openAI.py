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
    for _ in range(6):
        response = client.chat.completions.create(model=OPENAI_MODEL, messages=messages, tools=TOOLS)
        if not hasattr(response, "choices"):
            raise RuntimeError("接口没有返回标准 OpenAI JSON，请检查 OPENAI_BASE_URL 是否以 /v1 结尾。")
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return message.content or ""
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

    print("开始和 AI 对话，输入 exit 或 quit 退出，输入 clear 清空历史。")
    while True:
        user_input = input("你：").strip()
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
