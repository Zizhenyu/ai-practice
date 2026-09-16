"""L2 homework: per-author rolling-window middleware for the small pipeline."""
from collections import defaultdict, deque
from pathlib import Path
import sys
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import Pipeline, ignore_bots, normalize, logger, handle


def rate_limit(clock=monotonic):
    accepted = defaultdict(deque)

    def middleware(msg, next_):
        now = clock()
        recent = accepted[msg['user']]
        while recent and now - recent[0] >= 60:
            recent.popleft()
        if len(recent) >= 3:
            return 'rate_limited'
        recent.append(now)
        return next_(msg)

    return middleware


def build_pipeline(clock=monotonic):
    # Per-pipeline dedupe state avoids leaking history across independent demos.
    seen = set()

    def dedupe(msg, next_):
        if msg['ts'] in seen:
            return None
        seen.add(msg['ts'])
        return next_(msg)

    # Bots/duplicates must not consume quota. Logger wraps the limiter so a
    # rejected request is logged too. Normalize only messages that pass.
    return (Pipeline().use(ignore_bots).use(dedupe).use(logger)
            .use(rate_limit(clock)).use(normalize))


if __name__ == '__main__':
    now = [0.0]
    pipe = build_pipeline(clock=lambda: now[0])
    for index, (timestamp, user) in enumerate(
            [(0, 'U1'), (10, 'U1'), (20, 'U1'), (30, 'U1'),
             (30, 'U2'), (59.999, 'U1'), (60, 'U1')]):
        now[0] = timestamp
        outcome = pipe.run({'ts': str(index), 'user': user, 'text': ' hello '}, handle)
        print(f't={timestamp:g} user={user} -> {outcome}')
