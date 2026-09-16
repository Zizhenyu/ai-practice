#!/usr/bin/env python3
"""Session 05: A/B compare two summarization prompts with the judge.

Prompt V1: lazy one-liner. Prompt V2: structured, with explicit requirements.
Both summarize the same incident conversation; the judge scores both.
The score delta is your resume number.
"""
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common.llm import call_llm
from judge import evaluate

SIM_DATA = Path(__file__).resolve().parents[2] / "slack-simulator" / "data" / "sample_messages.jsonl"

PROMPT_V1 = "Summarize this Slack conversation."

PROMPT_V2 = """Summarize this Slack incident conversation for an engineering audience.
Requirements:
- State severity, impact window, and duration
- State the root cause precisely (component + mechanism)
- State the mitigation and when metrics recovered
- State customer impact facts (e.g. whether double charges occurred)
- List every action item with owner and due date
Be factual; do not omit numbers."""

# Mock outputs so the A/B works without a key: V1 is vague, V2 is complete.
MOCK_V1 = ("There was a payment incident caused by a deploy. The team investigated, "
           "rolled it back, and things recovered. Follow-ups were assigned.")
MOCK_V2 = ("SEV-2, impact 08:55-09:58 (~63 min degraded checkout). Root cause: N+1 query in "
           "v2.14.0 saved-payment-methods endpoint exhausted the DB connection pool (200/200), "
           "starving /charges. Rolled back to v2.13.2 at 09:58; p99 720ms, 5xx 0.3%. No double "
           "charges (failed before capture). Action items: Jake fix+flag by 7/20, Tom pool alert "
           "by 7/17, Aisha CI load test by 7/24, Priya runbook by 7/15. Postmortem 7/15.")


def summarize_with(prompt: str, transcript: str, mock: str) -> str:
    return call_llm(system=prompt, user=transcript, mock=mock)


def main():
    msgs = [json.loads(l) for l in SIM_DATA.read_text(encoding="utf-8").splitlines() if l.strip()]
    incident = [m for m in msgs if m["channel"] == "#incidents"]
    transcript = "\n".join(f"[{m['sim_ts']}] {m['author']}: {m['text']}" for m in incident)

    results = {}
    for name, prompt, mock in [("V1 (lazy)", PROMPT_V1, MOCK_V1),
                               ("V2 (structured)", PROMPT_V2, MOCK_V2)]:
        print(f"\n================ {name} ================")
        summary = summarize_with(prompt, transcript, mock)
        print(f"--- summary ---\n{summary}\n--- scoring ---")
        results[name] = evaluate(summary)

    print("\n================ RESULT ================")
    for name, score in results.items():
        print(f"  {name:20s} coverage = {score:.0%}")
    v1, v2 = list(results.values())
    if v2 > v1:
        print(f"\nPrompt iteration improved coverage by {(v2 - v1) * 100:.0f} percentage points."
              f"\n(This is the number that goes on the resume — with the receipts above.)")


if __name__ == "__main__":
    main()
