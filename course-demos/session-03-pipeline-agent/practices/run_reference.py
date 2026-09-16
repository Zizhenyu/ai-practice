"""Reproduce the L3 reference: replay saved evidence, or explicitly call a model."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
DEMOS = HERE.parents[1]
sys.path.insert(0, str(DEMOS))
from common import llm
from common.summarization import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.live:
        data = json.loads((HERE / 'reference_results.json').read_text(encoding='utf-8'))
        print('Saved real-run evidence; no new API calls.')
    else:
        if not llm.llm_available():
            parser.error('--live requires a configured model; no mock fallback')
        if not args.output:
            parser.error('--live requires --output to preserve the checked-in reference')
        fixture = json.loads((HERE.parent / 'fixtures/long.json').read_text(encoding='utf-8'))
        long_messages = [dict(m, channel=fixture['channel_id']) for m in fixture['messages']]
        all_messages = [json.loads(line) for line in
                        (DEMOS.parent / 'slack-simulator/data/sample_messages.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        incident = [m for m in all_messages if m['channel'] == '#incidents']
        jobs = [('long_engineer', long_messages, 'engineer', 'single'),
                ('long_manager', long_messages, 'manager', 'single'),
                ('long_map_reduce', long_messages, 'engineer', 'map-reduce'),
                ('incident_engineer', incident, 'engineer', 'single'),
                ('incident_manager', incident, 'manager', 'single')]

        def run(job):
            name, messages, audience, strategy = job
            requests = []

            def caller(**kwargs):
                kwargs['temperature'] = 0
                requests.append({k: v for k, v in kwargs.items() if k != 'mock'})
                return llm.call_llm(**kwargs)

            result = summarize(messages, audience=audience, strategy=strategy,
                               chunk_tokens=2000, caller=caller)
            return name, {**result, 'requests': requests, 'application_calls': len(requests)}

        with ThreadPoolExecutor(max_workers=3) as pool:
            results = dict(pool.map(run, jobs))
        data = {'recorded_at': datetime.now(timezone.utc).isoformat(),
                'mode': 'live', 'provider': llm.llm_provider(), 'model': llm.llm_model(),
                'temperature': 0, 'source': 'fixture (local shared API; no Slack send)',
                'snapshots': {'long': long_messages, 'incident': incident},
                'results': results}
        data['snapshot_sha256'] = {k: hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                                   for k, v in data['snapshots'].items()}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name, result in data['results'].items():
        print(name, result['model'], result['strategy'], 'calls:', result['application_calls'])
        print(result['text'])


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    main()
