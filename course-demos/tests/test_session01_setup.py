from conftest import load_session

check_env = load_session("session-01-setup", "check_env")
hello_bot = load_session("session-01-setup", "hello_bot")


def test_check_env_reports_ok_for_installed_required_packages(capsys):
    check_env.main()
    out = capsys.readouterr().out
    assert "[OK     ] yaml" in out
    assert "[OK     ] flask" in out
    assert "mock (all demos still runnable)" in out


def test_hello_bot_handler_is_transport_agnostic():
    reply = hello_bot.handle_message("U42", "are you there?")
    assert "U42" in reply and "are you there?" in reply


def test_hello_bot_builds_thread_key_from_mention_event():
    event = {"channel": "C42", "ts": "1700000000.000100", "user": "U42"}
    assert hello_bot.thread_key(event) == ("C42", "1700000000.000100")


def test_hello_bot_answers_human_replies_in_active_threads():
    active_threads = {("C42", "1700000000.000100")}
    event = {
        "channel": "C42",
        "thread_ts": "1700000000.000100",
        "ts": "1700000001.000200",
        "user": "U42",
        "text": "following up without mention",
    }
    assert hello_bot.should_answer_thread_reply(event, active_threads)


def test_hello_bot_ignores_untracked_or_bot_thread_messages():
    active_threads = {("C42", "1700000000.000100")}
    assert not hello_bot.should_answer_thread_reply(
        {"channel": "C42", "thread_ts": "999.000100", "user": "U42"},
        active_threads,
    )
    assert not hello_bot.should_answer_thread_reply(
        {"channel": "C42", "thread_ts": "1700000000.000100", "bot_id": "B42"},
        active_threads,
    )
