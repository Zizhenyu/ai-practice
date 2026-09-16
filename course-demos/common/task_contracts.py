"""Data checks shared by extraction and the downstream task demo.

These checks validate shapes and exact quotations, not semantic truth.
"""
from datetime import date, datetime
import hashlib
import json
import re

PRIORITIES = {"high", "medium", "low"}
CONTRACT_VERSION = "task-records-v2"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate_tasks(tasks, team, *, messages=None):
    errors = []
    if not isinstance(tasks, list):
        return ["top-level value must be a JSON array"]
    sources = {m["id"]: m["text"] for m in messages} if messages is not None else None
    for i, task in enumerate(tasks):
        prefix = f"item {i}: "
        if not isinstance(task, dict):
            errors.append(prefix + "not an object")
            continue
        for field in ("task", "owner", "due", "priority"):
            if field not in task:
                errors.append(prefix + f"'{field}' missing")
        if not isinstance(task.get("task"), str) or not task["task"].strip():
            errors.append(prefix + "'task' missing or not a non-empty string")
        owner = task.get("owner")
        if owner is not None and (not isinstance(owner, str) or owner not in team):
            errors.append(prefix + f"owner {owner!r} is not a team member")
        if task.get("due") is not None and not valid_date(task["due"]):
            errors.append(prefix + "due must be a real calendar date in YYYY-MM-DD or null")
        priority = task.get("priority")
        if not isinstance(priority, str) or priority not in PRIORITIES:
            errors.append(prefix + "priority must be high, medium or low")
        if sources is not None:
            extra = set(task) - {"task", "owner", "due", "priority", "evidence"}
            if extra:
                errors.append(prefix + "unexpected fields: " + ", ".join(sorted(extra)))
            evidence = task.get("evidence")
            if not isinstance(evidence, dict):
                errors.append(prefix + "evidence object missing")
                continue
            mid, quote = evidence.get("message_id"), evidence.get("quote")
            if not isinstance(mid, str) or mid not in sources:
                errors.append(prefix + "evidence.message_id is unknown")
            elif not isinstance(quote, str) or not quote.strip() or quote not in sources[mid]:
                errors.append(prefix + "evidence.quote must be an exact non-empty source substring")
    return errors


def validate_chat(data):
    if not isinstance(data, dict):
        raise ValueError("chat must be an object")
    for field in ("title", "reference_time", "timezone", "event_date"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"chat.{field} must be non-empty text")
    timestamp = datetime.fromisoformat(data["reference_time"])
    if timestamp.utcoffset() is None or not valid_date(data["event_date"]):
        raise ValueError("reference_time needs an offset; event_date must be YYYY-MM-DD")
    # This teaching scenario deliberately has a fixed timezone, not a timezone conversion lesson.
    if data["timezone"] != "Asia/Shanghai" or timestamp.utcoffset().total_seconds() != 28800:
        raise ValueError("camping reference_time must use Asia/Shanghai (+08:00)")
    members = data.get("members")
    if not isinstance(members, dict) or not members or any(
            not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
            for k, v in members.items()):
        raise ValueError("members must map non-empty IDs to display names")
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list")
    ids = set()
    for msg in messages:
        if not isinstance(msg, dict) or any(
                not isinstance(msg.get(k), str) or not msg[k].strip() for k in ("id", "author", "text")):
            raise ValueError("each message needs id, author and text")
        if msg["id"] in ids or msg["author"] not in members:
            raise ValueError("duplicate message id or unknown author")
        ids.add(msg["id"])
    return data


def task_id(task):
    """Stable for identical merged content and provenance, independent of list position."""
    identity = {"task": task["task"], "owner": task["owner"],
                "sources": sorted({e["message_id"] for e in task.get("sources", [])})}
    return "task-" + fingerprint(identity)[:16]
