#!/usr/bin/env python3
"""L4: source-grounded summary judging with an adapted Google rubric."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.llm import call_llm, llm_model, llm_provider

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures/summary_eval.json"
MOCK_FIXTURE = HERE / "fixtures/summary_eval_mock.json"
PROMPT = HERE / "prompts/summarization_quality.md"
OUTPUTS = HERE.parent / "outputs/summary-eval"
RUBRIC_VERSION = "google-teaching-v1"
CRITERIA = ("instruction_following", "groundedness", "conciseness", "fluency")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def validate_input(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    require_text(data.get("instruction"), "instruction")
    for field in ("messages", "summaries"):
        items = data.get(field)
        if not isinstance(items, list) or not items:
            raise ValueError(f"{field} must be a non-empty list")
        ids = set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{field} entries must be objects")
            for key in ("id", "text"):
                require_text(item.get(key), f"{field}.{key}")
            if item["id"] in ids:
                raise ValueError(f"duplicate {field} id: {item['id']}")
            ids.add(item["id"])
    return data


def input_fingerprint(data):
    """Bind replay to the entire input, not just a user-controlled sample ID."""
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_verdict(raw, messages):
    verdict = json.loads(raw)
    if not isinstance(verdict, dict):
        raise ValueError("verdict must be an object")
    score = verdict.get("score")
    if type(score) is not int or not 1 <= score <= 5:
        raise ValueError("score must be an integer from 1 to 5")
    feedback = verdict.get("feedback")
    if not isinstance(feedback, dict):
        raise ValueError("feedback must be an object")
    for criterion in CRITERIA:
        require_text(feedback.get(criterion), f"feedback.{criterion}")
    evidence = verdict.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("at least one evidence quote is required")
    sources = {m["id"]: m["text"] for m in messages}
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("evidence entries must be objects")
        for key in ("message_id", "quote", "comment"):
            require_text(item.get(key), f"evidence.{key}")
        if item["message_id"] not in sources:
            raise ValueError("evidence refers to an unknown message")
        if item["quote"] not in sources[item["message_id"]]:
            raise ValueError("evidence quote is not an exact source substring")
    # Do not trust model-provided status or identifiers.
    return {"score": score, "feedback": {k: feedback[k] for k in CRITERIA},
            "evidence": [{k: e[k] for k in ("message_id", "quote", "comment")}
                         for e in evidence]}


def evaluate_summary(instruction, messages, summary, *, template=None, replay_raw=None,
                     temperature=0):
    """Shared single-summary scorer; replay identity is the caller's responsibility."""
    if template is None:
        template = PROMPT.read_text(encoding="utf-8")
    request = {"system": template,
               "user": json.dumps({"instruction": instruction, "messages": messages,
                                   "summary": summary}, ensure_ascii=False),
               "temperature": temperature, "max_output_tokens": 2200}
    raw = None
    try:
        raw = replay_raw if replay_raw is not None else call_llm(**request)
        result = {"summary_id": summary["id"], "status": "ok", **parse_verdict(raw, messages)}
    except Exception as exc:
        result = {"summary_id": summary["id"], "status": "error", "score": None,
                  "feedback": {}, "evidence": [], "error": f"{type(exc).__name__}: {exc}"}
    return {**result, "raw_output": raw, "request": request}


def evaluate(data, *, mock=False):
    validate_input(data)
    provider = "mock" if mock else llm_provider()
    replay = provider == "mock"
    template = PROMPT.read_text(encoding="utf-8")
    canned = None
    if replay:
        canned = read_json(MOCK_FIXTURE)
        if (input_fingerprint(data) != canned["input_sha256"]
                or canned["rubric_version"] != RUBRIC_VERSION
                or canned["prompt_sha256"] != hashlib.sha256(template.encode("utf-8")).hexdigest()):
            raise ValueError("离线仅支持未修改的内置输入和评分模板；自定义输入请配置真实模型。")
    report = {
        "mode": "mock_replay" if replay else "live",
        "provider": provider, "model": "human-authored-examples" if replay else llm_model(),
        "rubric_version": RUBRIC_VERSION, "prompt": template,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": data, "results": [],
    }
    for summary in data["summaries"]:
        result = evaluate_summary(data["instruction"], data["messages"], summary,
                                  template=template,
                                  replay_raw=json.dumps(canned["verdicts"][summary["id"]],
                                                        ensure_ascii=False) if replay else None)
        report["results"].append(result)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=FIXTURE)
    parser.add_argument("--mock", action="store_true", help="强制人工示例回放，不调用模型")
    args = parser.parse_args(argv)
    try:
        report = evaluate(read_json(args.input), mock=args.mock)
    except (ValueError, OSError) as exc:
        print(f"输入/配置错误：{exc}", file=sys.stderr)
        return 1
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    path = OUTPUTS / run_id / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Google 模板教学改编 · " + (
        "人工示例回放（不代表模型评分）" if report["mode"] == "mock_replay"
        else f"真实评分 {report['provider']}/{report['model']}"))
    for result in report["results"]:
        print(f"\n{result['summary_id']}: {result['score']}/5" if result["status"] == "ok"
              else f"\n{result['summary_id']}: ERROR — {result['error']}")
        for criterion, comment in result["feedback"].items():
            print(f"  {criterion}: {comment}")
        for evidence in result["evidence"]:
            print(f"  [{evidence['message_id']}] {evidence['quote']} → {evidence['comment']}")
    print(f"\n报告：{path}")
    return int(any(r["status"] == "error" for r in report["results"]))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
