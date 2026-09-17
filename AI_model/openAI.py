# Author:HankQueen
# Date:2026/6/29

import json
import sys
from pathlib import Path

from openai import OpenAI

try:
    from AI.AI_model.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
except ModuleNotFoundError:
    from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
)

CURRENT_DIR = Path(__file__).resolve().parent
HISTORY_FILE = CURRENT_DIR / "chat_history.json"
SYSTEM_MESSAGE = {"role": "system", "content": "你是一个有帮助的中文助手。"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def ask_ai(messages):
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
    )
    print(response)
    if not hasattr(response, "choices"):
        raise RuntimeError("接口没有返回标准 OpenAI JSON，请检查 OPENAI_BASE_URL 是否以 /v1 结尾。")
    return response.choices[0].message.content


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
