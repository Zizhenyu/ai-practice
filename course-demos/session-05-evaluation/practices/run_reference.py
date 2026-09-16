"""L4 single-change A/B and pointwise evaluation; live calls are explicit."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DEMOS = HERE.parents[1]
sys.path.insert(0, str(DEMOS))
sys.path.insert(0, str(HERE.parent))
from common import llm
import judge
import compare_prompts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--l3-results', type=Path, default=DEMOS / 'session-03-pipeline-agent/practices/reference_results.json')
    args = parser.parse_args()
    if not args.live:
        data = json.loads((HERE / 'reference_results.json').read_text(encoding='utf-8'))
        print('Saved real-run evidence; no new API calls.')
    else:
        if not llm.llm_available() or not args.output:
            parser.error('--live requires a configured model and --output; no mock fallback')
        l3 = json.loads(args.l3_results.read_text(encoding='utf-8'))
        gt = json.loads(judge.GROUND_TRUTH.read_text(encoding='utf-8'))
        points = [{'id': f'P{i}', 'text': p} for i, p in enumerate(gt['summaries']['incident_2026_07_13']['must_include'], 1)]
        messages = [json.loads(line) for line in compare_prompts.SIM_DATA.read_text(encoding='utf-8').splitlines() if line.strip()]
        # Both A/B variants receive the same expanded input; m024 grounds customer impact.
        messages = [m for m in messages if m['channel'] == '#incidents' or m['id'] == 'm024']
        transcript = '\n'.join(f"[{m['sim_ts']}] {m['author']}: {m['text']}" for m in messages)
        prompts = {'A': compare_prompts.PROMPT_V1,
                   'B': compare_prompts.PROMPT_V1 + '\nInclude each follow-up action with its owner and due date.'}
        requests = {}

        def generate(item):
            name, prompt = item
            # Reuse compare_prompts.summarize_with, fixing generation parameters explicitly.
            def fixed_call(**kwargs):
                kwargs.update(temperature=0, max_output_tokens=1500)
                requests[name] = {k: v for k, v in kwargs.items() if k != 'mock'}
                return llm.call_llm(**kwargs)
            return name, prompt, fixed_call

        outputs = {}
        original = compare_prompts.call_llm
        try:
            for name, prompt, fixed_call in map(generate, prompts.items()):
                compare_prompts.call_llm = fixed_call
                outputs[name] = compare_prompts.summarize_with(prompt, transcript, None)
        finally:
            compare_prompts.call_llm = original
        summaries = {name: l3['results']['incident_' + name]['text'] for name in ('engineer', 'manager')}
        summaries.update(outputs)
        # Strict judge.py entry point preserves YES/NO responses and distinguishes errors from misses.
        with ThreadPoolExecutor(max_workers=4) as pool:
            scores = dict(pool.map(lambda item: (item[0], judge.evaluate_points(item[1], points, temperature=0)), summaries.items()))
        data = {'recorded_at': datetime.now(timezone.utc).isoformat(),
                'mode': 'live', 'provider': llm.llm_provider(), 'model': llm.llm_model(),
                'temperature': 0, 'l3_snapshot_sha256': l3['snapshot_sha256']['incident'],
                'ab_input': messages, 'prompts': prompts, 'generation_requests': requests,
                'points': points, 'summaries': summaries, 'scores': scores}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name, score in data['scores'].items():
        print(name, score['status'], score['hits'], '/', score['total'], score['coverage'])


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    main()
