#!/usr/bin/env python3
"""Session 01: hello-world bot.

With SLACK_BOT_TOKEN + SLACK_APP_TOKEN (Socket Mode): responds to @mentions.
After a mention starts a thread, replies in that same thread do not need to
mention the bot again.
Without tokens: console simulation, same handler logic — the teaching point
is that handler code should not care where the message came from.
"""
import os
from typing import Optional, Set, Tuple

from dotenv import load_dotenv

load_dotenv()


def handle_message(user: str, text: str) -> str:
    """The bot's 'brain' — shared by both transports."""
    return f"Hello <@{user}>! You said: “{text}”. I'm alive and listening."


ThreadKey = Tuple[str, str]


def thread_key(event: dict) -> Optional[ThreadKey]:
    """Return a stable Slack thread identity for events that can live in a thread."""
    channel = event.get("channel")
    thread_ts = event.get("thread_ts") or event.get("ts")
    if not channel or not thread_ts:
        return None
    return channel, thread_ts


def should_answer_thread_reply(event: dict, active_threads: Set[ThreadKey]) -> bool:
    """True when a human replied inside a thread the bot is already part of."""
    if not event.get("thread_ts"):
        return False
    if event.get("subtype") or event.get("bot_id") or not event.get("user"):
        return False
    key = thread_key(event)
    return key in active_threads if key else False


def run_console():
    print("Console mode (no Slack tokens). Type a message, 'quit' to exit.\n")
    while True:
        try:
            text = input("you> ").strip()
        except EOFError:
            break
        if text.lower() in ("quit", "exit", ""):
            break
        print("bot>", handle_message("console_user", text))


def run_slack():
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    active_threads: Set[ThreadKey] = set()

    @app.event("app_mention")
    def on_mention(event, say):
        key = thread_key(event)
        if key:
            active_threads.add(key)
        say(handle_message(event["user"], event["text"]),
            thread_ts=(event.get("thread_ts") or event.get("ts")))

    @app.event("message")
    def on_thread_reply(event, say):
        if should_answer_thread_reply(event, active_threads):
            say(handle_message(event["user"], event["text"]),
                thread_ts=event["thread_ts"])

    print("Connecting to Slack via Socket Mode...")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    if os.environ.get("SLACK_BOT_TOKEN") and os.environ.get("SLACK_APP_TOKEN"):
        run_slack()
    else:
        run_console()
