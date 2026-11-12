"""THE TRAFFIC LEDGER (M5 C12 observation contract; residual R2, 2026-10-15): keys are declared routes, fixed pages
or fixed buckets (never request text); at most ROUTE_KEY_LIMIT rows in total, overflow included; declared request
lengths parsed only as bounded ASCII decimal and otherwise labelled, never guessed; the observer never throws into a
request and never leaves a half-begun exchange; observed versus failed writes; the event stream's lifecycle;
self-reads apart; copy-only reads. The live server path is in tests/test_scanner.py."""
import pytest

from laplace.web import traffic


@pytest.fixture(autouse=True)
def fresh():
    traffic._reset_for_tests()
    yield
    traffic._reset_for_tests()


def test_keys_are_declared_routes_fixed_pages_or_fixed_buckets_never_request_text():
    assert traffic.route_key('/authoring/session-turn?project=p&id=T1') == '/authoring/session-turn', 'a declared route, no query'
    assert traffic.route_key('/authoring/health') == '/authoring/health' and traffic.route_key('/authoring/events') == '/authoring/events'
    assert traffic.route_key('/shared/workspace.mjs') == '/shared/*' and traffic.route_key('/vendor/pdf.mjs') == '<static>'
    assert traffic.route_key('/walk') == '/walk' and traffic.route_key('/project') == '/project' and traffic.route_key('/') == '/'
    assert traffic.route_key('/corpus/node') == '/corpus/*'
    # undeclared path text is never retained: a writing family keeps only its fixed bucket, anything else is <other>
    assert traffic.route_key('/research/private-source-title') == '/research/*'
    assert traffic.route_key('/research/artifact') == '/research/*'
    assert traffic.route_key('/private-document-slug/path') == '<other>'
    assert traffic.route_key('/authoring/' + 'a' * 300) == '/authoring/*'
    fixed = set(traffic.PAGE_ROUTES) | {key for _, key in traffic.BUCKETS} | set(traffic._WRITING_BUCKETS.values()) | {'<other>'}
    for path in ('/research/My Secret Title', '/x' * 40, '/authoring/../etc/passwd', '/ü/ß', ''):
        key = traffic.route_key(path)
        assert key in fixed or key in traffic._declared(), (path, key)
        assert len(key.encode()) <= traffic.ROUTE_KEY_BYTES


def test_at_most_the_advertised_number_of_rows_exist_in_total_overflow_included(monkeypatch):
    many = frozenset('/authoring/r%d' % n for n in range(200))
    monkeypatch.setattr(traffic, '_declared_routes', many)
    for route in sorted(many):
        traffic.end(traffic.begin('GET', route), 200)
    shot = traffic.snapshot()
    assert shot['limits']['route_keys'] == traffic.ROUTE_KEY_LIMIT == 64
    assert shot['limits']['route_keys_used'] == len(shot['routes']) == 64, 'the cap includes the overflow row'
    assert shot['routes']['<overflow>']['requests'] == 200 - 63 and shot['routes']['<overflow>']['in_flight'] == 0
    assert sum(row['requests'] for row in shot['routes'].values()) == 200, 'nothing is dropped'


@pytest.mark.parametrize('value,label', [('22', 'declared'), (None, 'absent'), ('²', 'invalid'), ('-1', 'invalid'), (' 22', 'invalid'),
                                         ('22.0', 'invalid'), ('٢٢', 'invalid'), ('9' * 16, 'oversized'), ('9' * 5000, 'oversized')])
def test_declared_lengths_are_bounded_ascii_and_otherwise_labelled_never_guessed(value, label):
    size, got = traffic.declared_length(value)
    assert got == label and (size == 22 if label == 'declared' else size is None)
    exchange = traffic.begin('POST', '/work/task', content_length=value)
    traffic.end(exchange, 200)
    row = traffic.snapshot()['routes'][traffic.route_key('/work/task')]
    assert row['requests'] == 1 and row['in_flight'] == 0 and row['request_length'] == {label: 1}
    assert row['request_declared_bytes'] == (22 if label == 'declared' else 0)


def test_the_observer_never_half_begins_and_counts_its_own_failures(monkeypatch):
    def broken(path):
        raise RuntimeError('observer fault')
    monkeypatch.setattr(traffic, 'route_key', broken)
    with pytest.raises(RuntimeError):
        traffic.begin('GET', '/walk')
    monkeypatch.undo()
    assert traffic.snapshot()['routes'] == {}, 'nothing was counted for an exchange that failed to begin'
    traffic.observer_failed()
    writer = traffic.CountingWriter(type('W', (), {'write': lambda self, data: len(data)})(), lambda: (_ for _ in ()).throw(KeyError('gone')))
    assert writer.write(b'abc') == 3, 'a failing observer never changes what the socket did'
    assert traffic.snapshot()['observer_errors'] == 2


def test_writes_are_observed_or_failed_and_self_reads_apart():
    exchange = traffic.begin('POST', '/work/task', content_length='22')
    writer = traffic.CountingWriter(type('W', (), {'write': lambda self, data: len(data)})(), lambda: exchange)
    writer.write(b'HTTP/1.0 200 OK\r\n\r\n'); writer.write(b'{"ok":true}')
    broken = traffic.CountingWriter(type('B', (), {'write': lambda self, data: (_ for _ in ()).throw(BrokenPipeError())})(), lambda: exchange)
    with pytest.raises(BrokenPipeError):
        broken.write(b'lost bytes')
    traffic.end(exchange, 200)
    traffic.end(traffic.begin('POST', '/work/task'), 413)
    view = traffic.begin('GET', '/authoring/health', diagnostic=True)
    traffic.wrote(view, 999); traffic.end(view, 200)
    traffic.wrote(None, 7)
    shot = traffic.snapshot(); row = shot['routes'][traffic.route_key('/work/task')]
    assert row['requests'] == 2 and row['in_flight'] == 0 and row['status'] == {'2xx': 1, '4xx': 1}
    assert row['response_bytes_written'] == 30 and row['response_bytes_failed'] == 10 and row['write_failures'] == 1
    assert row['request_declared_bytes'] == 22 and row['request_length'] == {'declared': 1, 'absent': 1}
    assert '/authoring/health' not in shot['routes'] and shot['diagnostic'] == {'reads': 1, 'bytes_written': 999}
    assert shot['unattributed']['bytes_written'] == 7 and shot['schema_version'] == 'laplace.writing-traffic/1'
    key = traffic.route_key('/work/task')
    shot['routes'][key]['requests'] = 99
    assert traffic.snapshot()['routes'][key]['requests'] == 2, 'a read is a copy'


def test_the_event_stream_lifecycle_counts_actual_writes_and_close():
    stream = traffic.begin('GET', '/authoring/events')
    assert traffic.snapshot()['event_stream']['open_now'] == 1
    for chunk in (b': heartbeat\n\n', b'id: 1\ndata: {}\n\n'):
        traffic.wrote(stream, len(chunk))
    traffic.wrote(stream, 5, failed=True)
    traffic.end(stream, 200)
    assert traffic.snapshot()['event_stream'] == {'opened': 1, 'closed': 1, 'open_now': 0, 'writes': 2, 'bytes_written': 29, 'write_failures': 1}
