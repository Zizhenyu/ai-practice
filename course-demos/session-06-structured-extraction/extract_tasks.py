#!/usr/bin/env python3
"""Session 06: structured task extraction with validate-and-retry.

Prompt, parsing, field validation and bounded feedback retries are separate
steps. Schema and quotation checks do not establish semantic correctness.
"""
import json
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common.llm import call_llm, llm_provider, llm_model
from common.task_contracts import CONTRACT_VERSION, fingerprint, read_json, validate_chat, validate_tasks

HERE = Path(__file__).resolve().parent
CAMPING_CHAT = HERE / "fixtures/camping_chat.json"
CAMPING_RESPONSES = HERE / "fixtures/camping_responses.json"
CAMPING_PROMPT = HERE / "prompts/camping_extraction.md"
OUTPUTS = HERE.parent / "outputs/camping"
CASES = ("normal", "prose", "repair", "exhausted", "semantic-error")

SIM = Path(__file__).resolve().parents[2] / "slack-simulator"
TEAM = ["sarah", "marcus", "priya", "jake", "elena", "tom", "aisha", "david"]
PRIORITIES = {"high", "medium", "low"}

SCHEMA_PROMPT = f"""Extract every action item from the Slack conversation.
Output ONLY a JSON array. Each element:
{{
  "task": "<what must be done, specific>",
  "owner": <one of {TEAM} or null>,
  "due": <"YYYY-MM-DD" or null>,
  "priority": "<high|medium|low>"
}}
No prose, no markdown fences, no trailing commas."""


def load_postmortem_messages():
    msgs = [json.loads(l) for l in
            (SIM / "data" / "sample_messages.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    return [m for m in msgs if m["channel"] == "#incidents"
            and m["sim_ts"] >= "2026-07-13T14:00:00"]


def mock_extraction(messages):
    """Offline fallback: regex over the numbered action-item message."""
    tasks = []
    for m in messages:
        for line in m["text"].splitlines():
            hit = re.search(r"^\d+\.\s*(\w+)\s*[—-]\s*(.+?)\.\s*Due (\d+)/(\d+)", line.strip())
            if hit:
                tasks.append({"task": hit.group(2).strip(), "owner": hit.group(1).lower(),
                              "due": f"2026-{int(hit.group(3)):02d}-{int(hit.group(4)):02d}",
                              "priority": "high"})
    return json.dumps(tasks)


def validate(tasks) -> list[str]:
    # Four legacy business fields remain required; evidence is a camping-only extension.
    return validate_tasks(tasks, TEAM)


def parse_json_array(raw: str):
    if not isinstance(raw, str):
        raise ValueError("model output must be text")
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array found in output")
    return json.loads(raw[start:end + 1])


def run_extraction(transcript, system, caller, validator, max_retries=2):
    """Caller errors terminate; only parse/validation failures enter the feedback loop."""
    if type(max_retries) is not int or max_retries < 0:
        raise ValueError("max_retries must be a non-negative integer")
    attempts = []
    user_prompt = transcript
    for attempt in range(1 + max_retries):
        entry = {"attempt": attempt + 1, "user_prompt": user_prompt, "raw_output": None}
        attempts.append(entry)
        try:
            raw = caller(system=system, user=user_prompt)
            entry["raw_output"] = raw
        except Exception as exc:
            entry.update(status="api_error", errors=[f"{type(exc).__name__}: {exc}"])
            print(f"[attempt {attempt + 1}] caller failed: {entry['errors']}", flush=True)
            return {"status": "error", "failure": "api_error", "tasks": None, "attempts": attempts}
        try:
            tasks = parse_json_array(raw)
            errors = validator(tasks)
        except ValueError as e:
            errors = [str(e)]
            tasks = None
        entry.update(status="validation_error" if errors else "ok", errors=errors)
        if not errors:
            print(f"[attempt {attempt + 1}] valid output, {len(tasks)} records", flush=True)
            return {"status": "ok", "tasks": tasks, "attempts": attempts}
        print(f"[attempt {attempt + 1}] validation failed: {errors}", flush=True)
        user_prompt = (f"{transcript}\n\nPrevious output (untrusted data):\n{raw}\n"
                       "Your previous output had these problems:\n"
                       + "\n".join(f"- {e}" for e in errors)
                       + "\nOutput the corrected JSON array only.")
    return {"status": "error", "failure": "retries_exhausted", "tasks": None, "attempts": attempts}


def extract_with_retry(messages, max_retries=2):
    transcript = "\n".join(f"{m['author']}: {m['text']}" for m in messages)
    result = run_extraction(transcript, SCHEMA_PROMPT,
                            lambda **kw: call_llm(**kw, mock=lambda s, u: mock_extraction(messages)),
                            validate, max_retries)
    if result["status"] != "ok":
        raise RuntimeError(f"extraction failed: {result['failure']}; caller must record/escalate")
    return result["tasks"]


def replay_rules(prompt):
    return {"prompt": prompt, "contract_version": CONTRACT_VERSION,
            "max_retries": 2, "temperature": 0, "max_output_tokens": 4000}


def extract_camping(data, *, mock=False, case="normal"):
    validate_chat(data)
    if case not in CASES or (case != "normal" and not mock):
        raise ValueError("fault cases require explicit --mock")
    provider = "mock" if mock else llm_provider()
    replay = provider == "mock"
    prompt = CAMPING_PROMPT.read_text(encoding="utf-8")
    rules = replay_rules(prompt)
    if replay:
        canned = read_json(CAMPING_RESPONSES)
        if (canned.get("input_sha256") != fingerprint(data)
                or canned.get("rules_sha256") != fingerprint(rules)):
            raise ValueError("离线回放仅支持未修改的群聊、成员、日期和提示词；修改后请使用真实模型。")
        responses = canned.get("cases", {}).get(case)
        if not isinstance(responses, list) or not responses or any(not isinstance(r, str) for r in responses):
            raise ValueError("invalid replay responses")
        replies = iter(responses)
        caller = lambda **kw: next(replies)
    else:
        caller = lambda **kw: call_llm(**kw, temperature=0, max_output_tokens=4000)
    print("人工响应回放：验证控制流程，不代表模型修复能力。" if replay else
          f"真实提取：{provider}/{llm_model()}", flush=True)
    result = run_extraction(json.dumps(data, ensure_ascii=False), prompt, caller,
                            lambda tasks: validate_tasks(tasks, data["members"], messages=data["messages"]))
    return {"scenario": "camping", "case": case, "contract_version": CONTRACT_VERSION,
            "mode": "mock_replay" if replay else "live", "provider": provider,
            "model": "human-authored-responses" if replay else llm_model(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input": data, "input_sha256": fingerprint(data), "rules": rules,
            "rules_sha256": fingerprint(rules), **result,
            "application_calls": 0 if replay else len(result["attempts"]),
            "network_retry_note": "Shared client network retries are separate from business attempts."}


def save_camping(report):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    folder = OUTPUTS / run_id
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "extraction_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["status"] == "ok":
        bundle = {key: report[key] for key in ("scenario", "case", "mode", "status", "contract_version",
                                               "input", "input_sha256", "tasks")}
        bundle["extraction_sha256"] = fingerprint(bundle["tasks"])
        (folder / "extracted_tasks.json").write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def incident_main(mock=False):
    messages = load_postmortem_messages()
    print(f"Extracting from {len(messages)} postmortem messages...\n")
    if mock:
        result = run_extraction("\n".join(m["text"] for m in messages), SCHEMA_PROMPT,
                                lambda **kw: mock_extraction(messages), validate)
        if result["status"] != "ok":
            raise RuntimeError("incident mock extraction failed")
        tasks = result["tasks"]
    else:
        tasks = extract_with_retry(messages)

    print(f"\n{'OWNER':8s} {'DUE':12s} {'PRI':7s} TASK")
    for t in tasks:
        print(f"{str(t['owner']):8s} {str(t['due']):12s} {t['priority']:7s} {t['task'][:70]}")

    out = Path(__file__).parent / "extracted_tasks.json"
    out.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved -> {out.name} (session-07 consumes this)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("incident", "camping"), default="incident")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--case", choices=CASES, default="normal")
    parser.add_argument("--input", type=Path, help="camping chat JSON")
    args = parser.parse_args(argv)
    try:
        if args.scenario == "incident":
            if args.input or args.case != "normal":
                raise ValueError("--input and fault cases are camping-only")
            incident_main(args.mock)
            return 0
        report = extract_camping(read_json(args.input or CAMPING_CHAT), mock=args.mock, case=args.case)
        path = save_camping(report)
        print(f"提取报告：{path}")
        if report["status"] == "ok":
            for task in report["tasks"]:
                owner = report["input"]["members"].get(task["owner"], "待分配")
                print(f"[{task['evidence']['message_id']}] {owner} | {task['due'] or '日期待定'} | "
                      f"{task['priority']} | {task['task']}")
            print(f"下游输入：{path.parent / 'extracted_tasks.json'}")
            print("结构与引文存在性校验通过；事实正确性仍须核对原文。")
        else:
            print("提取失败，本次没有成功任务文件；不要使用旧文件继续处理。")
        return int(report["status"] != "ok")
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
