#!/usr/bin/env python3
"""Same source and summaries, two evaluation methods: coverage and quality."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

import judge
import judge_google as quality
from common.llm import llm_model, llm_provider

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures/mulan_eval.json"
MOCK_FIXTURE = HERE / "fixtures/mulan_eval_mock.json"
OUTPUTS = HERE.parent / "outputs/evaluator-comparison"
TEMPERATURE = 0


def validate_input(data):
    quality.validate_input(data)
    source = data.get("source")
    if not isinstance(source, dict):
        raise ValueError("source must be an object")
    for key in ("title", "url", "accessed_on", "edition_note"):
        quality.require_text(source.get(key), f"source.{key}")
    points = data.get("must_include")
    if not isinstance(points, list) or not points:
        raise ValueError("must_include must be a non-empty list")
    sources = {m["id"]: m["text"] for m in data["messages"]}
    ids = set()
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("must_include entries must be objects")
        for key in ("id", "text", "message_id", "quote"):
            quality.require_text(point.get(key), f"must_include.{key}")
        if point["id"] in ids:
            raise ValueError("duplicate must_include id")
        ids.add(point["id"])
        if point["message_id"] not in sources or point["quote"] not in sources[point["message_id"]]:
            raise ValueError("must_include quote must be an exact source substring")
    return data


def method_config():
    return {
        "coverage": {"version": judge.COVERAGE_VERSION, "system": judge.COVERAGE_SYSTEM,
                     "user_template": judge.COVERAGE_USER, "temperature": TEMPERATURE,
                     "max_output_tokens": 32, "context": "single point + summary"},
        "quality": {"version": quality.RUBRIC_VERSION,
                    "system": quality.PROMPT.read_text(encoding="utf-8"),
                    "user_fields": ["instruction", "messages", "summary"],
                    "criteria": list(quality.CRITERIA), "temperature": TEMPERATURE,
                    "max_output_tokens": 2200, "context": "instruction + source + summary"},
    }


def load_replay(data, methods):
    canned = quality.read_json(MOCK_FIXTURE)
    if (canned.get("input_sha256") != quality.input_fingerprint(data)
            or canned.get("methods_sha256") != quality.input_fingerprint(methods)):
        raise ValueError("离线仅支持未修改的内置输入和两种评分规则；自定义输入请配置真实模型。")
    # Preflight the whole replay so a missing item cannot silently make a live call.
    try:
        for summary in data["summaries"]:
            item = canned["verdicts"][summary["id"]]
            if not isinstance(item["quality"], dict):
                raise ValueError("quality replay must be an object")
            for point in data["must_include"]:
                if not isinstance(item["coverage"][point["id"]], str):
                    raise ValueError("coverage replay must contain raw strings")
    except (KeyError, TypeError) as exc:
        raise ValueError("incomplete replay fixture") from exc
    return canned["verdicts"]


def evaluate(data, *, mock=False, summary_id=None, progress=None):
    validate_input(data)
    summaries = [s for s in data["summaries"] if summary_id is None or s["id"] == summary_id]
    if not summaries:
        raise ValueError(f"unknown summary id: {summary_id}")
    provider = "mock" if mock else llm_provider()
    replay = provider == "mock"
    methods = method_config()
    canned = load_replay(data, methods) if replay else None
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "mock_replay" if replay else "live", "provider": provider,
        "model": "human-authored-examples" if replay else llm_model(),
        "input": data, "input_sha256": quality.input_fingerprint(data),
        "methods": methods, "methods_sha256": quality.input_fingerprint(methods),
        "selected_summary_ids": [s["id"] for s in summaries],
        "application_calls": {"coverage": 0, "quality": 0},
        "network_retry_note": "Shared client may retry network requests; counts are application-level.",
        "results": [],
    }
    for summary in summaries:
        if progress:
            progress(f"{summary['id']}: 评估要点覆盖率…")
        coverage = judge.evaluate_points(
            summary["text"], data["must_include"], temperature=TEMPERATURE,
            replay=canned[summary["id"]]["coverage"] if replay else None)
        if progress:
            progress(f"{summary['id']}: 评估综合质量（Google 模板教学改编）…")
        result = quality.evaluate_summary(
            data["instruction"], data["messages"], summary,
            template=methods["quality"]["system"], temperature=TEMPERATURE,
            replay_raw=json.dumps(canned[summary["id"]]["quality"], ensure_ascii=False) if replay else None)
        report["application_calls"]["coverage"] += coverage["application_calls"]
        report["application_calls"]["quality"] += int(not replay)
        report["results"].append({"summary_id": summary["id"], "coverage": coverage, "quality": result})
    return report


def print_report(report):
    print("人工示例回放（不代表模型评分）" if report["mode"] == "mock_replay"
          else f"真实评分 {report['provider']}/{report['model']}")
    print("同稿双评：覆盖率看指定要点；综合质量看原文依据、任务完成与表达。两种分数不换算。")
    print("摘要 | 要点覆盖率 | 综合质量（Google 模板教学改编，1–5）")
    for r in report["results"]:
        c, q = r["coverage"], r["quality"]
        cov = f"{c['hits']}/{c['total']} = {c['coverage']:.0%}" if c["status"] == "ok" else "ERROR"
        score = f"{q['score']}/5" if q["status"] == "ok" else "ERROR"
        print(f"{r['summary_id']} | {cov} | {score}")
    summaries = {s["id"]: s["text"] for s in report["input"]["summaries"]}
    points = {p["id"]: p["text"] for p in report["input"]["must_include"]}
    for r in report["results"]:
        print(f"\n== {r['summary_id']} ==\n{summaries[r['summary_id']]}")
        for p in r["coverage"]["points"]:
            label = "ERROR" if p["status"] == "error" else "HIT" if p["hit"] else "MISS"
            print(f"  [{label}] {p['point_id']}: {points[p['point_id']]}")
            if p["status"] == "error":
                print(f"    {p['error']}")
        q = r["quality"]
        if q["status"] == "error":
            print(f"  ERROR: {q['error']}")
        for key, comment in q["feedback"].items():
            print(f"  {key}: {comment}")
        for e in q["evidence"]:
            print(f"  [{e['message_id']}] {e['quote']} → {e['comment']}")
    print(f"\n应用层调用数：{report['application_calls']}（网络重试另计）")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=FIXTURE)
    parser.add_argument("--mock", action="store_true", help="强制人工回放，无网络调用")
    parser.add_argument("--summary-id", help="只评指定 ID，仍校验完整回放输入")
    args = parser.parse_args(argv)
    try:
        report = evaluate(quality.read_json(args.input), mock=args.mock, summary_id=args.summary_id,
                          progress=lambda message: print(message, flush=True))
    except (ValueError, OSError) as exc:
        print(f"输入/配置错误：{exc}", file=sys.stderr)
        return 1
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    path = OUTPUTS / run_id / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_report(report)
    print(f"\n报告：{path}")
    return int(any(r[m]["status"] == "error" for r in report["results"] for m in ("coverage", "quality")))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
