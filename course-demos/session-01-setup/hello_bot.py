#!/usr/bin/env python3
"""Session 01: hello-world bot.

With SLACK_BOT_TOKEN + SLACK_APP_TOKEN (Socket Mode): responds to @mentions.
Without tokens: console simulation, same handler logic — the teaching point
is that handler code should not care where the message came from.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def handle_message(user: str, text: str) -> str:
    """The bot's 'brain' — shared by both transports."""
    return f"Hello <@{user}>! You said: “{text}”. I'm alive and listening."


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

    @app.event("app_mention")
    def on_mention(event, say):
        say(handle_message(event["user"], event["text"]))

    print("Connecting to Slack via Socket Mode...")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    if os.environ.get("SLACK_BOT_TOKEN") and os.environ.get("SLACK_APP_TOKEN"):
        run_slack()
    else:
        run_console()
