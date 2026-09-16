from conftest import load_session

reference = load_session('session-03-pipeline-agent/practices', 'rate_limit_reference')


def test_rolling_window_author_isolation_and_rejection_not_counted():
    now = [0.0]
    limiter = reference.rate_limit(lambda: now[0])
    received = []

    def send(at, author='U1'):
        now[0] = at
        return limiter({'user': author}, lambda msg: received.append(author) or 'ok')

    assert [send(t) for t in (0, 10, 20)] == ['ok'] * 3
    assert send(30) == 'rate_limited'
    assert send(30, 'U2') == 'ok'
    assert send(59.999) == 'rate_limited'
    assert send(60) == 'ok'  # Exactly 60 seconds evicts the first acceptance.
    assert send(60) == 'rate_limited'  # The other two old entries remain.
    assert send(70) == 'ok'  # Rejections at 30/59.999/60 did not consume quota.
    assert received == ['U1', 'U1', 'U1', 'U2', 'U1', 'U1']


def test_pipeline_order_filters_and_logs_rejection(capsys):
    pipe = reference.build_pipeline(clock=lambda: 0)
    handled = []

    def send(ts, **extra):
        return pipe.run({'ts': ts, 'user': 'U1', 'text': ' hi ', **extra},
                        lambda msg: handled.append(msg['text']) or 'ok')

    assert send('bot', bot_id='B1') is None
    assert send('1') == 'ok'
    assert send('1') is None
    assert send('2') == 'ok'
    assert send('3') == 'ok'
    capsys.readouterr()
    assert send('4') == 'rate_limited'
    assert '[logger] 4 handled' in capsys.readouterr().out
    assert handled == ['hi'] * 3
