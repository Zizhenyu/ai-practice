#!/usr/bin/env python3
"""Practice program for Session 1: reply with one classical Chinese poem line.

The point of this exercise is architecture reuse: the program calls the shared
course-demos/common/llm.py entry point instead of creating a new LLM client.
"""
import sys
from argparse import ArgumentParser
from pathlib import Path

from dotenv import load_dotenv

COURSE_DEMOS = Path(__file__).resolve().parents[2]
if str(COURSE_DEMOS) not in sys.path:
    sys.path.insert(0, str(COURSE_DEMOS))

from common.llm import call_llm_safe

load_dotenv(COURSE_DEMOS / ".env")

SYSTEM_PROMPT = """你是一个中文诗词聊天机器人。
用户会输入一句自然语言。请先理解用户的情绪、场景或意图，然后只用一句合适的古诗词回答。
输出格式：
诗句：<一句古诗词>
说明：<不超过30个字，说明为什么适合>
不要编造现代句子冒充古诗词。"""

ARCHITECTURE_MERMAID = """flowchart TD
    user["用户输入<br/>一句自然语言"] --> entry["course-demos/session-01-setup/practices/session_01_poem_bot.py<br/>聊天入口"]
    entry --> clean["clean_user_input()<br/>清洗输入文本"]
    clean --> prompt["build_user_prompt()<br/>构造诗词选择Prompt"]
    prompt --> llm["course-demos/common/llm.py<br/>call_llm_safe()"]

    env["course-demos/.env<br/>OPENAI_API_KEY / DEEPSEEK_API_KEY / ANTHROPIC_API_KEY"] --> llm
    example["course-demos/.env.example<br/>配置模板"] --> env

    llm --> provider{"是否有可用模型密钥?"}
    provider -- yes --> real["真实LLM<br/>理解输入并选择诗句"]
    provider -- no或API失败 --> mock["mock_poem_reply()<br/>固定规则返回诗句"]

    real --> reply["输出一句古诗词<br/>附简短说明"]
    mock --> reply
"""


def clean_user_input(text: str) -> str:
    """Normalize a user's message before building the LLM prompt."""
    return " ".join(text.strip().split())


def mock_poem_reply(text: str) -> str:
    """Deterministic fallback for offline demos and tests."""
    lowered = text.lower()
    if any(word in text for word in ("想家", "故乡", "家乡", "思念")):
        return "诗句：举头望明月，低头思故乡。\n说明：适合表达思乡之情。"
    if any(word in text for word in ("朋友", "分别", "离别", "送别")):
        return "诗句：海内存知己，天涯若比邻。\n说明：适合回应友情与距离。"
    if any(word in text for word in ("努力", "坚持", "学习", "考试")):
        return "诗句：长风破浪会有时，直挂云帆济沧海。\n说明：适合鼓励继续前行。"
    if any(word in lowered for word in ("sad", "tired", "hard")) or any(
            word in text for word in ("难过", "累", "压力", "失落")):
        return "诗句：山重水复疑无路，柳暗花明又一村。\n说明：适合安慰低落时刻。"
    return "诗句：欲穷千里目，更上一层楼。\n说明：适合鼓励拓展视野。"


def build_user_prompt(text: str) -> str:
    return f"用户输入：{text}\n请用一句合适的古诗词回答。"


def answer_with_poem(text: str, mock: bool = False) -> str:
    cleaned = clean_user_input(text)
    if not cleaned:
        return "诗句：欲穷千里目，更上一层楼。\n说明：请输入一句话后再试。"
    if mock:
        return mock_poem_reply(cleaned)
    return call_llm_safe(
        system=SYSTEM_PROMPT,
        user=build_user_prompt(cleaned),
        mock=lambda _system, _user: mock_poem_reply(cleaned),
        temperature=0.2,
    )


def run_console(mock: bool = False):
    print("Poem bot. Type a message, 'quit' to exit.\n")
    while True:
        try:
            text = input("you> ")
        except EOFError:
            break
        if text.strip().lower() in ("quit", "exit", ""):
            break
        print("bot>", answer_with_poem(text, mock=mock))


def parse_args():
    parser = ArgumentParser(description="Session 1 practice: poem chat bot.")
    parser.add_argument("--mock", action="store_true",
                        help="force deterministic offline poem replies")
    parser.add_argument("--once", metavar="TEXT",
                        help="answer one message and exit")
    parser.add_argument("--diagram", action="store_true",
                        help="print this program's Mermaid architecture diagram")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.diagram:
        print(ARCHITECTURE_MERMAID)
        return
    if args.once is not None:
        print(answer_with_poem(args.once, mock=args.mock))
        return
    run_console(mock=args.mock)


if __name__ == "__main__":
    main()
