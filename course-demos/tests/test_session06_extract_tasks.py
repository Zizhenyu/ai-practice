from conftest import load_session

extract_tasks_mod = load_session("session-06-structured-extraction", "extract_tasks")


def test_validate_accepts_well_formed_list():
    tasks = [{"task": "fix bug", "owner": "jake", "due": "2026-07-20", "priority": "high"}]
    assert extract_tasks_mod.validate(tasks) == []


def test_validate_rejects_unknown_owner():
    tasks = [{"task": "fix bug", "owner": "not-a-team-member", "due": None, "priority": "high"}]
    assert any("owner" in e for e in extract_tasks_mod.validate(tasks))


def test_validate_rejects_bad_date_format():
    tasks = [{"task": "fix bug", "owner": "jake", "due": "07/20/2026", "priority": "high"}]
    assert any("due" in e for e in extract_tasks_mod.validate(tasks))


def test_validate_rejects_non_list():
    assert extract_tasks_mod.validate({"not": "a list"}) != []


def test_parse_json_array_ignores_surrounding_prose():
    raw = 'Sure, here you go:\n[{"task": "x", "owner": null, "due": null, "priority": "low"}]\nDone.'
    assert extract_tasks_mod.parse_json_array(raw) == [
        {"task": "x", "owner": None, "due": None, "priority": "low"}]


def test_extract_with_retry_mock_path_produces_valid_tasks():
    messages = extract_tasks_mod.load_postmortem_messages()
    tasks = extract_tasks_mod.extract_with_retry(messages)
    assert tasks and extract_tasks_mod.validate(tasks) == []
