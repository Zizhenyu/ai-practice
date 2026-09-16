from datetime import date

from conftest import load_session

task_system = load_session("session-07-action-items", "task_system")


def test_dedupe_merges_similar_tasks_same_owner_and_keeps_earlier_due():
    tasks = [
        {"task": "Fix the N+1 query in saved-payment-methods", "owner": "jake",
         "due": "2026-07-20", "priority": "high"},
        {"task": "fix the n+1 query saved payment methods", "owner": "jake",
         "due": "2026-07-18", "priority": "high"},
    ]
    deduped = task_system.dedupe(tasks)
    assert len(deduped) == 1
    assert deduped[0]["due"] == "2026-07-18"


def test_dedupe_keeps_distinct_owners_separate():
    tasks = [
        {"task": "write the runbook", "owner": "priya", "due": None, "priority": "medium"},
        {"task": "write the runbook", "owner": "tom", "due": None, "priority": "medium"},
    ]
    assert len(task_system.dedupe(tasks)) == 2


def test_sort_tasks_orders_by_priority_then_due():
    tasks = [
        {"task": "low task", "owner": "a", "due": "2026-07-01", "priority": "low"},
        {"task": "high task later", "owner": "b", "due": "2026-07-20", "priority": "high"},
        {"task": "high task sooner", "owner": "c", "due": "2026-07-10", "priority": "high"},
    ]
    ordered = task_system.sort_tasks(tasks)
    assert [t["task"] for t in ordered] == ["high task sooner", "high task later", "low task"]


def test_reminder_sweep_prints_due_today(capsys):
    tasks = [{"task": "ship the fix", "owner": "jake", "due": "2026-07-15", "priority": "high"}]
    task_system.reminder_sweep(tasks, date(2026, 7, 14), date(2026, 7, 16))
    out = capsys.readouterr().out
    assert "ship the fix" in out and "DUE TODAY" in out
