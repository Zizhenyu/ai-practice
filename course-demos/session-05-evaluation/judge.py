#!/usr/bin/env python3
"""Session 05: score a summary against ground-truth must_include points.

Method: for each required point, ask an LLM judge "does the summary cover
this?" (yes/no). Coverage = hits / total. Offline fallback: token-overlap.
This turns 'my summary looks good' into a number you can improve and report.
"""
import json
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common.llm import call_llm

SIM = Path(__file__).resolve().parents[2] / "slack-simulator"
GROUND_TRUTH = SIM / "data" / "ground_truth.json"
COVERAGE_VERSION = "pointwise-coverage-v1"
COVERAGE_SYSTEM = "You are a strict evaluator. Answer only YES or NO."
COVERAGE_USER = ("Does this summary cover the following point (fully or in substance)?\n\n"
                 "POINT: {point}\n\nSUMMARY:\n{summary}")


def evaluate_points(summary, points, *, replay=None, temperature=0):
    """Strict coverage path; failures are not misses. Never uses token overlap.

    replay maps point IDs to raw YES/NO strings; its identity is checked by
    the comparison runner before this function is called.
    """
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary must be non-empty text")
    if not isinstance(points, list) or not points:
        raise ValueError("points must be a non-empty list")
    ids = set()
    for point in points:
        if not isinstance(point, dict) or any(
                not isinstance(point.get(k), str) or not point[k].strip() for k in ("id", "text")):
            raise ValueError("points need non-empty id and text")
        if point["id"] in ids:
            raise ValueError("duplicate point id")
        ids.add(point["id"])
    results = []
    for point in points:
        raw = None
        request = {"system": COVERAGE_SYSTEM,
                   "user": COVERAGE_USER.format(point=point["text"], summary=summary),
                   "temperature": temperature, "max_output_tokens": 32}
        try:
            raw = replay[point["id"]] if replay is not None else call_llm(**request)
            if not isinstance(raw, str) or raw.strip() not in ("YES", "NO"):
                raise ValueError("coverage response must be exactly YES or NO")
            result = {"point_id": point["id"], "status": "ok", "hit": raw.strip() == "YES"}
        except Exception as exc:
            result = {"point_id": point["id"], "status": "error", "hit": None,
                      "error": f"{type(exc).__name__}: {exc}"}
        results.append({**result, "raw_output": raw, "request": request})
    hits = sum(r["hit"] is True for r in results)
    ok = all(r["status"] == "ok" for r in results)
    return {"status": "ok" if ok else "error", "hits": hits, "total": len(points),
            "coverage": hits / len(points) if ok else None, "points": results,
            "application_calls": len(points) if replay is None else 0}


def token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]+", a.lower()))
    tb = set(re.findall(r"[a-z0-9]+", b.lower()))
    return len(ta & tb) / len(tb) if tb else 0.0


def judge_point(summary: str, point: str) -> bool:
    verdict = call_llm(
        system=COVERAGE_SYSTEM,
        user=COVERAGE_USER.format(point=point, summary=summary),
        mock=lambda s, u: "YES" if token_overlap(summary, point) >= 0.35 else "NO")
    return verdict.strip().upper().startswith("YES")


def evaluate(summary: str, spec_name: str = "incident_2026_07_13") -> float:
    gt = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    spec = gt["summaries"][spec_name]
    points = spec["must_include"]

    print(f"Evaluating against '{spec_name}' ({len(points)} required points):\n")
    hits = 0
    for p in points:
        ok = judge_point(summary, p)
        hits += ok
        print(f"  [{'HIT ' if ok else 'MISS'}] {p[:90]}")

    coverage = hits / len(points)
    print(f"\nCoverage: {hits}/{len(points)} = {coverage:.0%}")
    return coverage


DEFAULT_SUMMARY = """SEV-2 payment outage on 7/13, impact window 08:55-09:58 (~63 minutes of degraded checkout).
Root cause: v2.14.0's saved-payment-methods endpoint had an N+1 query that exhausted the DB
connection pool (200/200), starving the /charges path. Tom rolled back to v2.13.2 at 09:58;
metrics recovered (p99 720ms, 5xx 0.3%). No double charges — failed requests errored before capture.
Postmortem set for 7/15 with four action items: Jake fixes the query behind a feature flag (7/20),
Tom adds pool saturation alerts (7/17), Aisha adds a CI load test (7/24), Priya updates the runbook (7/15)."""


if __name__ == "__main__":
    summary = sys.stdin.read() if not sys.stdin.isatty() else DEFAULT_SUMMARY
    if not summary.strip():
        summary = DEFAULT_SUMMARY
    evaluate(summary)
