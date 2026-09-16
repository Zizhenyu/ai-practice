import copy
from datetime import date
import json

import pytest
from conftest import load_session
from common.task_contracts import CONTRACT_VERSION, fingerprint, validate_chat, validate_tasks

extract = load_session("session-06-structured-extraction", "extract_tasks")
system = load_session("session-07-action-items", "task_system")


def chat():
    return extract.read_json(extract.CAMPING_CHAT)


def raw_tasks():
    return json.loads(extract.read_json(extract.CAMPING_RESPONSES)["cases"]["normal"][0])


def bundle():
    data, tasks = chat(), raw_tasks()
    return {"scenario": "camping", "case": "normal", "status": "ok", "mode": "mock_replay",
            "contract_version": CONTRACT_VERSION, "input": data, "input_sha256": fingerprint(data),
            "tasks": tasks, "extraction_sha256": fingerprint(tasks)}


def never_call(**kwargs):
    pytest.fail("replay must never call a model")


@pytest.mark.parametrize("case,attempts,status", [
    ("normal", 1, "ok"), ("prose", 1, "ok"), ("repair", 3, "ok"),
    ("exhausted", 3, "error"), ("semantic-error", 1, "ok"),
])
def test_replay_cases_are_explicit_and_bounded(monkeypatch, case, attempts, status):
    monkeypatch.setattr(extract, "call_llm", never_call)
    monkeypatch.setattr(extract, "llm_provider", lambda: "deepseek")
    result = extract.extract_camping(chat(), mock=True, case=case)
    assert result["mode"] == "mock_replay" and result["application_calls"] == 0
    assert result["status"] == status and len(result["attempts"]) == attempts
    if case == "repair":
        assert result["attempts"][0]["raw_output"] in result["attempts"][1]["user_prompt"]
        assert "outsider" in result["attempts"][2]["user_prompt"]
        assert "2026-99-99" in result["attempts"][2]["user_prompt"]
    if case == "exhausted":
        assert result["tasks"] is None and result["failure"] == "retries_exhausted"
    if case == "semantic-error":
        # Correct shape and real quotation cannot detect misassigned ownership.
        assert result["tasks"][0]["owner"] == "yu"
        assert result["tasks"][0]["evidence"]["message_id"] == "m02"


@pytest.mark.parametrize("field", ["members", "messages", "reference_time", "event_date"])
def test_changed_input_rejects_replay(field):
    data = chat()
    if field == "members":
        data[field]["jie"] += " changed"
    elif field == "messages":
        data[field][0]["text"] += " changed"
    elif field == "reference_time":
        data[field] = "2026-09-17T20:00:00+08:00"
    else:
        data[field] = "2026-09-20"
    with pytest.raises(ValueError, match="离线"):
        extract.extract_camping(data, mock=True)


def test_changed_prompt_rejects_replay(tmp_path, monkeypatch):
    path = tmp_path / "prompt.md"
    path.write_text(extract.CAMPING_PROMPT.read_text(encoding="utf-8") + "changed", encoding="utf-8")
    monkeypatch.setattr(extract, "CAMPING_PROMPT", path)
    with pytest.raises(ValueError, match="离线"):
        extract.extract_camping(chat(), mock=True)


@pytest.mark.parametrize("change", ["author", "duplicate", "timezone", "date", "members", "messages"])
def test_input_preflight(change):
    data = chat()
    if change == "author":
        data["messages"][0]["author"] = "unknown"
    elif change == "duplicate":
        data["messages"].append(copy.deepcopy(data["messages"][0]))
    elif change == "timezone":
        data["reference_time"] = "2026-09-16T20:00:00"
    elif change == "date":
        data["event_date"] = "2026-99-99"
    else:
        data[change] = None
    with pytest.raises(ValueError):
        validate_chat(data)


@pytest.mark.parametrize("field,value", [
    ("task", "  "), ("owner", []), ("owner", "阿杰"), ("priority", []),
    ("priority", {}), ("due", 20260918), ("due", "2026-02-30"), ("due", "2026-9-18"),
    ("evidence", None), ("done", True),
])
def test_invalid_values_return_errors_not_crashes(field, value):
    tasks = raw_tasks()
    tasks[0][field] = value
    assert validate_tasks(tasks, chat()["members"], messages=chat()["messages"])


@pytest.mark.parametrize("field", ["task", "owner", "due", "priority", "evidence"])
def test_required_fields_are_not_null(field):
    tasks = raw_tasks()
    del tasks[0][field]
    assert validate_tasks(tasks, chat()["members"], messages=chat()["messages"])
    assert validate_tasks(raw_tasks(), chat()["members"], messages=chat()["messages"]) == []


@pytest.mark.parametrize("field,value", [("message_id", "missing"), ("quote", "fabricated"), ("quote", " ")])
def test_invalid_evidence(field, value):
    tasks = raw_tasks()
    tasks[0]["evidence"][field] = value
    assert validate_tasks(tasks, chat()["members"], messages=chat()["messages"])


def test_live_records_and_api_failure_are_not_replayed(monkeypatch):
    requests = []
    monkeypatch.setattr(extract, "llm_provider", lambda: "test")
    monkeypatch.setattr(extract, "llm_model", lambda: "test-model")

    def caller(**kwargs):
        requests.append(kwargs)
        return json.dumps(raw_tasks())

    monkeypatch.setattr(extract, "call_llm", caller)
    result = extract.extract_camping(chat())
    assert result["mode"] == "live" and result["application_calls"] == 1
    assert json.loads(requests[0]["user"]) == chat()
    assert "cases" not in requests[0]["user"]

    def failing(**kwargs):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(extract, "call_llm", failing)
    result = extract.extract_camping(chat())
    assert result["failure"] == "api_error" and result["tasks"] is None
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["raw_output"] is None


def test_fault_case_requires_explicit_mock():
    with pytest.raises(ValueError, match="explicit"):
        extract.extract_camping(chat(), case="repair")


def test_artifacts_are_isolated_and_cli_failure_is_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr(extract, "OUTPUTS", tmp_path)
    assert extract.main(["--scenario", "camping", "--mock"]) == 0
    good = next(tmp_path.glob("*/extracted_tasks.json"))
    content = good.read_bytes()
    assert extract.main(["--scenario", "camping", "--mock", "--case", "exhausted"]) == 1
    assert len(list(tmp_path.glob("*/extraction_report.json"))) == 2
    assert list(tmp_path.glob("*/extracted_tasks.json")) == [good]
    assert good.read_bytes() == content
    reports = [extract.read_json(p) for p in tmp_path.glob("*/extraction_report.json")]
    assert sorted(r["status"] for r in reports) == ["error", "ok"]


def test_normal_merge_sources_dates_priority_and_no_mutation():
    original = bundle()
    saved = copy.deepcopy(original)
    tasks, logs = system.prepare_camping(original)
    assert original == saved
    assert len(tasks) == 7 and len(logs) == 1
    pickup = next(t for t in tasks if t["task"] == "领取租用的帐篷")
    assert pickup["due"] == "2026-09-17"
    assert [e["message_id"] for e in pickup["sources"]] == ["m02", "m06"]
    assert tasks[0]["owner"] == "jie" and tasks[1]["owner"] == "ning"
    assert tasks[-1]["priority"] == "low"
    assert any(t["task"] == "归还租用的帐篷" for t in tasks)
    # IDs are based on content and source, not the sorted row number.
    assert system.task_id(pickup) == system.task_id({**pickup, "sources": list(reversed(pickup["sources"]))})


def test_merge_takes_higher_priority_and_earlier_due():
    a = {"task": "检查炉具", "owner": "peng", "due": None, "priority": "low"}
    b = {**a, "due": "2026-09-18", "priority": "high"}
    result = system.dedupe([a, b], similarity=system.chinese_jaccard)
    assert result[0]["priority"] == "high" and result[0]["due"] == "2026-09-18"
    assert a["priority"] == "low"


def test_chinese_similarity_and_false_merge_boundary():
    assert system.chinese_jaccard("领取租用的帐篷", "归还租用的帐篷") == 0.5
    assert system.chinese_jaccard("领取租用的帐篷", "领取租用的帐篷") == 1
    assert system.chinese_jaccard("准备音箱", "带上蓝牙播放器") == 0
    assert system.bigrams("帐篷，音箱") == {"帐篷", "音箱"}
    assert len(system.prepare_camping(bundle(), 0.5)[0]) == 6
    for threshold in (-0.1, 1.1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            system.prepare_camping(bundle(), threshold)


def test_unknown_and_different_owners_do_not_merge():
    template = {"task": "准备音箱", "due": None, "priority": "medium"}
    tasks = [{**template, "owner": owner} for owner in (None, None, "jie", "peng")]
    assert len(system.dedupe(tasks, similarity=system.chinese_jaccard)) == 4


def test_reminder_dates_pending_and_completion(capsys):
    original = bundle()
    monday = date(2026, 9, 21)
    report = system.run_camping(original)
    assert len(report["pending_task_ids"]) == 1
    assert sum(e["kind"] == "due_today" for e in report["events"]) == 6
    assert sum(e["kind"] == "overdue" for e in report["events"]) == 5
    assert all(e["date"] == monday.isoformat() for e in report["events"] if e["kind"] == "overdue")
    state = system.read_json(system.HERE / "fixtures/camping_done.json")
    completed = system.run_camping(original, done=state)
    assert completed["start"] == monday.isoformat()
    assert sum(e["kind"] == "overdue" for e in completed["events"]) == 3
    assert not any(e["task_id"] in state["completed_task_ids"] for e in completed["events"])
    assert "@None" not in capsys.readouterr().out
    task = {"task": "x", "owner": "jie", "priority": "high", "due": monday.isoformat(), "done": True}
    assert system.reminder_sweep([task], monday, monday) == []


@pytest.mark.parametrize("change", ["chat", "extraction", "unknown", "duplicate", "date"])
def test_bad_completion_snapshot(change):
    state = system.read_json(system.HERE / "fixtures/camping_done.json")
    if change in ("chat", "extraction"):
        state["input_sha256" if change == "chat" else "extraction_sha256"] = "changed"
    elif change == "unknown":
        state["completed_task_ids"] = ["unknown"]
    elif change == "duplicate":
        state["completed_task_ids"] *= 2
    else:
        state["as_of"] = "2026-99-99"
    with pytest.raises(ValueError):
        system.run_camping(bundle(), done=state)


def test_completion_cannot_be_applied_to_past_or_wrong_merged_tasks():
    state = system.read_json(system.HERE / "fixtures/camping_done.json")
    with pytest.raises(ValueError, match="before"):
        system.run_camping(bundle(), done=state, start=date(2026, 9, 17))
    with pytest.raises(ValueError, match="unknown"):
        system.run_camping(bundle(), done=state, threshold=0.5)


@pytest.mark.parametrize("change", ["status", "input", "tasks", "contract", "field"])
def test_downstream_refuses_invalid_bundle(change):
    item = bundle()
    if change == "status":
        item["status"] = "error"
    elif change == "input":
        item["input"]["title"] += " changed"
    elif change == "tasks":
        item["tasks"][0]["owner"] = "yu"
    elif change == "contract":
        item["contract_version"] = "unknown"
    else:
        item["tasks"][0]["done"] = True
        item["extraction_sha256"] = fingerprint(item["tasks"])
    with pytest.raises(ValueError):
        system.prepare_camping(item)


def test_task_cli_requires_explicit_file_and_saves_separate_runs(tmp_path):
    assert system.main(["--scenario", "camping"]) == 1
    path = tmp_path / "extracted_tasks.json"
    path.write_text(json.dumps(bundle()), encoding="utf-8")
    assert system.main(["--scenario", "camping", "--input", str(path)]) == 0
    assert system.main(["--scenario", "camping", "--input", str(path), "--threshold", "0.5"]) == 0
    reports = [system.read_json(p) for p in tmp_path.glob("task-runs/*/task_report.json")]
    assert sorted(len(r["tasks"]) for r in reports) == [6, 7]
    path.write_text('{"status":"error"}', encoding="utf-8")
    assert system.main(["--scenario", "camping", "--input", str(path)]) == 1
    assert len(list(tmp_path.glob("task-runs/*/task_report.json"))) == 2


def test_pair_scan_has_both_false_positives_and_false_negatives(capsys):
    system.scan_pairs()
    output = capsys.readouterr().out
    assert "SUMMARY 0.5: TP=1 FP=1 FN=2 TN=2" in output
    assert "SUMMARY 0.6: TP=1 FP=0 FN=2 TN=3" in output
