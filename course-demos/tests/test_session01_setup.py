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
