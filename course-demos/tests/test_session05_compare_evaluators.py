import copy
import json

import pytest
from conftest import load_session

c = load_session("session-05-evaluation", "compare_evaluators")


def data():
    return c.quality.read_json(c.FIXTURE)


def canned():
    return c.quality.read_json(c.MOCK_FIXTURE)["verdicts"]


def no_network(**kwargs):
    pytest.fail("network or token overlap must not run in replay")


def test_replay_matrix_and_selection_use_full_input(monkeypatch):
    monkeypatch.setattr(c.judge, "call_llm", no_network)
    monkeypatch.setattr(c.quality, "call_llm", no_network)
    monkeypatch.setattr(c.judge, "token_overlap", no_network)
    report = c.evaluate(data(), mock=True)
    assert report["mode"] == "mock_replay"
    assert report["model"] == "human-authored-examples"
    assert report["application_calls"] == {"coverage": 0, "quality": 0}
    assert [(r["coverage"]["coverage"], r["quality"]["score"]) for r in report["results"]] == [
        (1, 5), (1, 1), (0.4, 2)]
    selected = c.evaluate(data(), mock=True, summary_id="B")
    assert selected["input"] == report["input"]
    assert selected["input_sha256"] == report["input_sha256"]
    assert selected["selected_summary_ids"] == ["B"]


@pytest.mark.parametrize("field", ["instruction", "source", "messages", "summaries", "must_include"])
def test_modified_input_cannot_reuse_replay(field):
    changed = data()
    if field == "instruction":
        changed[field] += " changed"
    elif field == "source":
        changed[field]["edition_note"] += " changed"
    else:
        changed[field][0]["text"] += " changed"
    with pytest.raises(ValueError, match="离线"):
        c.evaluate(changed, mock=True, summary_id="B")


@pytest.mark.parametrize("field", ["COVERAGE_SYSTEM", "COVERAGE_USER", "COVERAGE_VERSION"])
def test_modified_coverage_rules_reject_replay(monkeypatch, field):
    monkeypatch.setattr(c.judge, field, getattr(c.judge, field) + " changed")
    with pytest.raises(ValueError, match="离线"):
        c.evaluate(data(), mock=True)


def test_modified_quality_prompt_rejects_replay(monkeypatch, tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text(c.quality.PROMPT.read_text(encoding="utf-8") + " changed", encoding="utf-8")
    monkeypatch.setattr(c.quality, "PROMPT", prompt)
    with pytest.raises(ValueError, match="离线"):
        c.evaluate(data(), mock=True)


@pytest.mark.parametrize("change", ["empty", "duplicate", "quote", "id", "text", "source", "summary_id"])
def test_invalid_input_before_calls(change, monkeypatch):
    d = data()
    if change == "empty":
        d["must_include"] = []
    elif change == "duplicate":
        d["must_include"].append(copy.deepcopy(d["must_include"][0]))
    elif change in ("quote", "id", "text"):
        d["must_include"][0][{"quote": "quote", "id": "message_id", "text": "text"}[change]] = (
            "absent" if change != "text" else " ")
    elif change == "source":
        d["source"] = None
    else:
        d["summaries"].append(copy.deepcopy(d["summaries"][0]))
    monkeypatch.setattr(c.judge, "call_llm", no_network)
    with pytest.raises(ValueError):
        c.evaluate(d)


@pytest.mark.parametrize("raw", ["YES because...", "yes", "", "YES NO", None, 1])
def test_coverage_bad_responses_are_errors_not_misses(raw):
    result = c.judge.evaluate_points("summary", [{"id": "k", "text": "point"}], replay={"k": raw})
    assert result["status"] == "error" and result["coverage"] is None
    assert result["points"][0]["hit"] is None
    assert result["points"][0]["raw_output"] == raw


def test_live_requests_are_paired_and_have_no_teacher_answers(monkeypatch):
    coverage_requests, quality_requests = [], []
    monkeypatch.setattr(c, "llm_provider", lambda: "test")
    monkeypatch.setattr(c, "llm_model", lambda: "test-model")
    monkeypatch.setattr(c.judge, "call_llm", lambda **kw: coverage_requests.append(kw) or "YES")

    def quality_call(**kw):
        quality_requests.append(kw)
        summary_id = json.loads(kw["user"])["summary"]["id"]
        return json.dumps(canned()[summary_id]["quality"], ensure_ascii=False)

    monkeypatch.setattr(c.quality, "call_llm", quality_call)
    d = data()
    result = c.evaluate(d)
    assert result["application_calls"] == {"coverage": 15, "quality": 3}
    for i, summary in enumerate(d["summaries"]):
        q = json.loads(quality_requests[i]["user"])
        assert q == {"instruction": d["instruction"], "messages": d["messages"], "summary": summary}
        for j, point in enumerate(d["must_include"]):
            request = coverage_requests[i * 5 + j]
            assert request["user"] == c.judge.COVERAGE_USER.format(point=point["text"], summary=summary["text"])
            assert request["temperature"] == quality_requests[i]["temperature"] == 0
    assert all(r["quality"]["status"] == "ok" for r in result["results"])


@pytest.mark.parametrize("failed_method", ["coverage", "quality"])
def test_one_method_failure_does_not_hide_other_result(monkeypatch, failed_method):
    monkeypatch.setattr(c, "llm_provider", lambda: "test")
    monkeypatch.setattr(c, "llm_model", lambda: "test-model")

    def fail(**kw):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(c.judge, "call_llm", fail if failed_method == "coverage" else lambda **kw: "NO")
    monkeypatch.setattr(c.quality, "call_llm", fail if failed_method == "quality" else
                        lambda **kw: json.dumps(canned()["B"]["quality"]))
    r = c.evaluate(data(), summary_id="B")["results"][0]
    assert r[failed_method]["status"] == "error"
    assert r[failed_method]["coverage" if failed_method == "coverage" else "score"] is None
    other = "quality" if failed_method == "coverage" else "coverage"
    assert r[other]["status"] == "ok"
    if other == "quality":
        assert r[other]["score"] == 1  # low score is not an execution failure


def test_quality_invalid_evidence_is_not_a_score(monkeypatch):
    monkeypatch.setattr(c, "llm_provider", lambda: "test")
    monkeypatch.setattr(c, "llm_model", lambda: "test")
    monkeypatch.setattr(c.judge, "call_llm", lambda **kw: "YES")
    bad = canned()["A"]["quality"]
    bad["evidence"][0]["quote"] = "fabricated quote"
    raw = json.dumps(bad)
    monkeypatch.setattr(c.quality, "call_llm", lambda **kw: raw)
    q = c.evaluate(data(), summary_id="A")["results"][0]["quality"]
    assert q["status"] == "error" and q["score"] is None
    assert q["raw_output"] == raw


def test_cli_report_and_exit_codes(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(c, "OUTPUTS", tmp_path)
    assert c.main(["--mock", "--summary-id", "B"]) == 0
    output = capsys.readouterr().out
    assert "人工示例" in output and "100%" in output and "1/5" in output
    path = next(tmp_path.glob("*/report.json"))
    report = c.quality.read_json(path)
    assert report["input"] == data()
    assert report["results"][0]["coverage"]["points"][0]["raw_output"] == "YES"
    assert c.main(["--mock", "--summary-id", "absent"]) == 1
    monkeypatch.setattr(c, "llm_provider", lambda: "test")
    monkeypatch.setattr(c, "llm_model", lambda: "test")
    monkeypatch.setattr(c.judge, "call_llm", lambda **kw: "invalid")
    monkeypatch.setattr(c.quality, "call_llm", lambda **kw: "invalid")
    assert c.main(["--summary-id", "B"]) == 1
    assert len(list(tmp_path.glob("*/report.json"))) == 2


def test_missing_replay_entry_never_falls_through_to_live(monkeypatch, tmp_path):
    replay = c.quality.read_json(c.MOCK_FIXTURE)
    del replay["verdicts"]["B"]["coverage"]["k1"]
    path = tmp_path / "replay.json"
    path.write_text(json.dumps(replay), encoding="utf-8")
    monkeypatch.setattr(c, "MOCK_FIXTURE", path)
    monkeypatch.setattr(c.judge, "call_llm", no_network)
    with pytest.raises(ValueError, match="incomplete replay"):
        c.evaluate(data(), mock=True)
