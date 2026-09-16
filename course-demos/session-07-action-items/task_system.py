#!/usr/bin/env python3
"""Session 07: action-item system — dedupe, prioritize, remind.

Input: tasks extracted in session 06. This session demonstrates local rules:
1. dedupe near-identical tasks (same task mentioned in standup AND postmortem)
2. sort by (priority, due date)
3. daily reminder sweep on a simulated clock (in prod: cron / Slack scheduler)
"""
import json
import argparse
import copy
import math
import re
import sys
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.task_contracts import (CONTRACT_VERSION, fingerprint, read_json, task_id,
                                   validate_chat, validate_tasks, valid_date)

HERE = Path(__file__).resolve().parent
PAIR_FIXTURE = HERE / "fixtures/camping_pairs.json"

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
SESSION_06_OUT = Path(__file__).resolve().parents[1] / "session-06-structured-extraction" / "extracted_tasks.json"

FALLBACK_TASKS = [
    {"task": "Fix N+1 query and re-ship saved-payment-methods behind feature flag",
     "owner": "jake", "due": "2026-07-20", "priority": "high"},
    {"task": "fix the N+1 query, re-ship saved payment methods behind a feature flag",
     "owner": "jake", "due": "2026-07-20", "priority": "high"},          # duplicate, phrased differently
    {"task": "Add connection-pool saturation alert to monitoring",
     "owner": "tom", "due": "2026-07-17", "priority": "high"},
    {"task": "Add payment-path load test to CI pipeline",
     "owner": "aisha", "due": "2026-07-24", "priority": "medium"},
    {"task": "Update payment-service runbook with pool-exhaustion playbook",
     "owner": "priya", "due": "2026-07-15", "priority": "medium"},
    {"task": "Notify requesting merchants about CSV export plan",
     "owner": "david", "due": None, "priority": "low"},
]


def tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - {"the", "a", "to", "and", "with"}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def bigrams(text):
    """Adjacent characters within runs; whitespace/punctuation form boundaries."""
    return {run[i:i + 2] for run in re.findall(r"[a-z0-9\u3400-\u9fff]+", text.lower())
            for i in range(len(run) - 1)}


def chinese_jaccard(a, b):
    ta, tb = bigrams(a), bigrams(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def dedupe(tasks, threshold=0.55, *, similarity=jaccard, merge_log=None):
    """Greedy, same-known-owner merge. Similarity is a lexical teaching baseline."""
    if not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be finite and between 0 and 1")
    kept = []
    for t in tasks:
        dup_of = next((k for k in kept
                       if t.get("owner") is not None and k["owner"] == t["owner"]
                       and similarity(k["task"], t["task"]) >= threshold),
                       None)
        if dup_of:
            before = copy.deepcopy(dup_of)
            print(f"  [dedupe] '{t['task'][:50]}...' merged into existing task "
                  f"(similarity {similarity(dup_of['task'], t['task']):.2f})")
            # keep the stricter constraint of the two
            if t.get("due") and (not dup_of.get("due") or t["due"] < dup_of["due"]):
                dup_of["due"] = t["due"]
            if PRIORITY_RANK[t["priority"]] < PRIORITY_RANK[dup_of["priority"]]:
                dup_of["priority"] = t["priority"]
            evidence = [t["evidence"]] if "evidence" in t else t.get("sources", [])
            for e in evidence:
                if e not in dup_of.setdefault("sources", []):
                    dup_of["sources"].append(copy.deepcopy(e))
            if evidence:
                print(f"    [merge] earlier due: {before.get('due')} -> {dup_of.get('due')}; "
                      f"higher priority: {before['priority']} -> {dup_of['priority']}; "
                      "sources: " + ",".join(e["message_id"] for e in dup_of["sources"]))
            if merge_log is not None:
                merge_log.append({"kept": before, "incoming": copy.deepcopy(t),
                                  "similarity": similarity(before["task"], t["task"]),
                                  "threshold": threshold, "result": copy.deepcopy(dup_of),
                                  "rule": "same known owner; first text; earlier due; higher priority; union sources"})
        else:
            item = copy.deepcopy(t)
            if "evidence" in item:
                item["sources"] = [item.pop("evidence")]
            kept.append(item)
    return kept


def sort_tasks(tasks):
    return sorted(tasks, key=lambda t: (PRIORITY_RANK.get(t["priority"], 9),
                                        t.get("due") or "9999-12-31"))


def reminder_sweep(tasks, start: date, end: date, *, members=None):
    """Print simulated reminders and return events. No network or real scheduler."""
    if start > end:
        raise ValueError("start must not be after end")
    events = []
    day = start
    while day <= end:
        active = [t for t in tasks if t.get("owner") is not None and not t.get("done")]
        due_today = [t for t in active if t.get("due") == day.isoformat()]
        overdue = [t for t in active if t.get("due") and t["due"] < day.isoformat()]
        if due_today or (overdue and day.weekday() == 0):   # nag overdue on Mondays
            print(f"\n  --- {day.isoformat()} ({day.strftime('%a')}) ---")
            for t in due_today:
                owner = (members or {}).get(t["owner"], t["owner"])
                print(f"  [remind] @{owner}: '{t['task'][:60]}' is DUE TODAY ({t['priority']})")
                events.append({"date": day.isoformat(), "kind": "due_today", "task_id": t.get("task_id"),
                               "owner": t["owner"], "task": t["task"], "due": t["due"]})
            if day.weekday() == 0:
                for t in overdue:
                    owner = (members or {}).get(t["owner"], t["owner"])
                    print(f"  [nag]    @{owner}: '{t['task'][:60]}' overdue since {t['due']}")
                    events.append({"date": day.isoformat(), "kind": "overdue", "task_id": t.get("task_id"),
                                   "owner": t["owner"], "task": t["task"], "due": t["due"]})
        day += timedelta(days=1)
    return events


def incident_main():
    if SESSION_06_OUT.exists():
        tasks = json.loads(SESSION_06_OUT.read_text(encoding="utf-8"))
        print(f"Loaded {len(tasks)} tasks from session-06 output")
        tasks = tasks + [FALLBACK_TASKS[1]]   # inject a near-duplicate to demo dedupe
    else:
        tasks = FALLBACK_TASKS
        print(f"Session-06 output not found; using {len(tasks)} built-in sample tasks")

    print("\n== 1. Dedupe ==")
    tasks = dedupe(tasks)
    print(f"  {len(tasks)} unique tasks remain")

    print("\n== 2. Priority order ==")
    tasks = sort_tasks(tasks)
    for t in tasks:
        print(f"  {t['priority']:6s} due={str(t.get('due')):12s} @{t['owner']}: {t['task'][:60]}")

    print("\n== 3. Reminder sweep (simulated clock 2026-07-13 .. 2026-07-27) ==")
    reminder_sweep(tasks, date(2026, 7, 13), date(2026, 7, 27))


def validate_bundle(bundle):
    if not isinstance(bundle, dict) or bundle.get("status") != "ok" or bundle.get("scenario") != "camping":
        raise ValueError("input must be an explicit successful camping extraction bundle")
    if bundle.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("unsupported extraction contract")
    data = validate_chat(bundle.get("input"))
    if bundle.get("input_sha256") != fingerprint(data):
        raise ValueError("input fingerprint mismatch")
    errors = validate_tasks(bundle.get("tasks"), data["members"], messages=data["messages"])
    if errors:
        raise ValueError("; ".join(errors))
    if bundle.get("extraction_sha256") != fingerprint(bundle["tasks"]):
        raise ValueError("extraction fingerprint mismatch")
    # Completion and task IDs are program state, not model-generated data.
    if any(set(t) - {"task", "owner", "due", "priority", "evidence"} for t in bundle["tasks"]):
        raise ValueError("unexpected model task fields; completion state must come from --done")
    return bundle


def prepare_camping(bundle, threshold=0.6):
    validate_bundle(bundle)
    log = []
    tasks = sort_tasks(dedupe(bundle["tasks"], threshold, similarity=chinese_jaccard, merge_log=log))
    for task in tasks:
        task["task_id"] = task_id(task)
        task["done"] = False
    if len({t["task_id"] for t in tasks}) != len(tasks):
        raise ValueError("ambiguous duplicate task IDs; inspect the source records")
    return tasks, log


def apply_done(tasks, bundle, state):
    if not isinstance(state, dict) or state.get("input_sha256") != bundle["input_sha256"]:
        raise ValueError("done snapshot belongs to a different chat")
    if state.get("extraction_sha256") != bundle["extraction_sha256"]:
        raise ValueError("done snapshot belongs to a different extraction")
    if not valid_date(state.get("as_of")):
        raise ValueError("done.as_of must be YYYY-MM-DD")
    ids = state.get("completed_task_ids")
    known = {t["task_id"] for t in tasks}
    if (not isinstance(ids, list) or any(not isinstance(i, str) or i not in known for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("done snapshot contains unknown or duplicate task IDs")
    for task in tasks:
        task["done"] = task["task_id"] in ids


def run_camping(bundle, *, threshold=0.6, start=None, end=None, done=None):
    tasks, merges = prepare_camping(bundle, threshold)
    if done is not None:
        apply_done(tasks, bundle, done)
    start = start or date.fromisoformat(done["as_of"] if done is not None else "2026-09-17")
    end = end or date(2026, 9, 21)
    if done is not None and start < date.fromisoformat(done["as_of"]):
        raise ValueError("cannot apply a completion snapshot to dates before its as_of date")
    if start > end:
        raise ValueError("start must not be after end")
    members = bundle["input"]["members"]
    assigned = [t for t in tasks if t["owner"] is not None]
    pending = [t for t in tasks if t["owner"] is None]
    print(f"原始记录 {len(bundle['tasks'])} → 任务 {len(tasks)}；阈值 {threshold}")
    print("来源模式：" + bundle.get("mode", "unknown") + "；字段与引文校验不等于事实正确。")
    for title, group in (("已分配", assigned), ("待分配", pending)):
        print(f"\n== {title} ==")
        for t in group:
            print(f"{t['task_id']} | {members.get(t['owner'], '待分配')} | {t['due'] or '日期待定'} | "
                  f"{t['priority']} | {'已完成' if t['done'] else '未完成'} | {t['task']} | "
                  + ",".join(e["message_id"] for e in t["sources"]))
    if done is not None:
        print(f"\n人工完成状态快照，生效于 {done['as_of']}；只重放该日及之后。")
    print(f"\n== 模拟提醒 {start} .. {end}（只打印，不发送） ==")
    events = reminder_sweep(tasks, start, end, members=members)
    return {"scenario": "camping", "input_sha256": bundle["input_sha256"],
            "extraction_sha256": bundle["extraction_sha256"], "input_bundle": bundle,
            "created_at": datetime.now(timezone.utc).isoformat(), "similarity": "character-bigram-jaccard-v1",
            "threshold": threshold, "start": start.isoformat(), "end": end.isoformat(),
            "done_snapshot": done, "tasks": tasks, "merge_log": merges, "events": events,
            "pending_task_ids": [t["task_id"] for t in pending]}


def scan_pairs():
    data = read_json(PAIR_FIXTURE)
    for threshold in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        tp = fp = fn = tn = 0
        for pair in data["pairs"]:
            score = chinese_jaccard(pair["a"], pair["b"])
            predicted = (pair["owner_a"] is not None and pair["owner_a"] == pair["owner_b"]
                         and score >= threshold)
            expected = pair["merge"]
            tp += predicted and expected
            fp += predicted and not expected
            fn += not predicted and expected
            tn += not predicted and not expected
            print(f"{threshold:.1f} {pair['id']} similarity={score:.3f} merge={predicted} label={expected}")
        print(f"SUMMARY {threshold:.1f}: TP={tp} FP={fp} FN={fn} TN={tn}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("incident", "camping"), default="incident")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--done", type=Path, help="manual completion snapshot")
    parser.add_argument("--scan-pairs", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.scenario == "incident":
            if any(v is not None for v in (args.input, args.threshold, args.start, args.end, args.done)) or args.scan_pairs:
                raise ValueError("extra options require --scenario camping")
            incident_main()
            return 0
        if args.scan_pairs:
            if any(v is not None for v in (args.input, args.threshold, args.start, args.end, args.done)):
                raise ValueError("--scan-pairs cannot be combined with task processing options")
            scan_pairs()
            return 0
        if args.input is None:
            raise ValueError("camping requires --input from a specific successful run; no old-file fallback")
        report = run_camping(read_json(args.input), threshold=0.6 if args.threshold is None else args.threshold,
                             start=args.start, end=args.end, done=read_json(args.done) if args.done else None)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        path = args.input.parent / "task-runs" / run_id / "task_report.json"
        path.parent.mkdir(parents=True, exist_ok=False)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"任务报告：{path}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
