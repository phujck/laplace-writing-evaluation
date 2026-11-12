"""CR-R1 (M5 2026-10-15): every changed consulted read of a refused candidate is reachable in bounded pages.

The refusal's own summary stays bounded (proposal_currentness.consumed_read_recovery) and now says so, naming
changed_reads_page: the existing proposal read owner's view=changed-reads (proposal_navigation -> proposal_currentness
.changed_read_page). Every page observes all of the candidate's consulted reads (at most PAGE_CONSULTED_MAX); that
observation is its cut, and a continuation is served only while the evidence gives the same cut (repair1, AR-R1).
A page returns at most `limit` rows within PAGE_BYTES of row UTF-8 and PAGE_RESPONSE_BYTES of whole-response
UTF-8 (the HTTP body). Pages renew nothing, bank no baseline and authorize nothing. Disposable fixtures only.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from laplace.core import bodies as core_bodies
from laplace.web import authoring as surface
from laplace.manuscript import proposal_navigation as nav
from laplace.native import tools as writing_tools
from laplace.projects import artifacts as writing_artifacts
from laplace.writing import records as writing_records
from laplace.manuscript import proposal_currentness as currentness
from laplace.manuscript import source_application
from laplace.writing import session_reads
from laplace.core import checkout
from test_consumed_read_recovery import seed_reads


def _http(root, monkeypatch, handle, *, raw=False):
    monkeypatch.setattr(checkout, 'repo_root', lambda: root)
    url = urlparse(handle['http']['url'])
    status, _, body = surface.handle(url.path, parse_qs(url.query), 'GET', b'')
    return (status, json.loads(body), body) if raw else (status, json.loads(body))


def _traverse(root, monkeypatch, first):
    pages, handle = [], first
    while handle:
        status, page, body = _http(root, monkeypatch, handle, raw=True)
        assert status == 200, page
        assert page['response_bytes'] == len(body) <= currentness.PAGE_RESPONSE_BYTES, 'the whole HTTP body is bounded'
        pages.append(page)
        handle = page['next']
        assert len(pages) <= 60
    return pages


def _refusal(root, turn, version):
    with pytest.raises(currentness.ProposalBasisRefused) as refused:
        source_application.apply_proposal(root, {'turn_id': turn, 'proposal_version': version})
    return writing_tools.failure_response(root, 'fixture', 'revise', 'apply_revision',
                                          {'turn_id': turn, 'proposal_version': version}, refused.value, turn)


def test_every_changed_consulted_read_is_reached_exactly_once_in_bounded_pages(tmp_path, monkeypatch):
    md, turn, version, paths, calls = seed_reads(tmp_path, monkeypatch, 39)
    for path in paths:
        path.write_text('Changed evidence.')
    summary = _refusal(tmp_path, turn, version)['consumed_read_recovery']
    assert summary['observed_changed_read_count'] == 39 and summary['changed_reads_omitted'] > 0
    assert 'first of them' in summary['note'] and 'listed here at once' not in summary['note'], 'the bound is stated, not hidden'
    journal = (tmp_path / 'contract' / 'talk.jsonl').read_bytes()
    pages = _traverse(tmp_path, monkeypatch, summary['changed_reads_page'])
    ids = [row['read_id'] for page in pages for row in page['changed_reads']]
    sealed = session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][version]['read_ids']
    assert len(ids) == len(set(ids)) == 39 and set(ids) <= set(sealed), 'every changed read once, no omission or duplicate'
    assert [page['changed']['from'] for page in pages] == [0] + [page['changed']['to'] for page in pages[:-1]]
    assert pages[-1]['changed']['to'] == pages[-1]['changed']['of'] == 39 and pages[-1]['complete'] and pages[-1]['next'] is None
    assert not any(page['complete'] for page in pages[:-1])
    for page in pages:
        assert page['status'] == 'OBSERVED' and len(page['changed_reads']) <= currentness.PAGE_ROWS
        assert page['observation'] == {**pages[0]['observation']}, 'one observation cut for the whole traversal'
        assert page['observation']['consulted'] == 39 and page['observation']['replayed'] == 39 and page['observation']['changed'] == 39
        delivered = sum(len(json.dumps(row, ensure_ascii=False).encode()) for row in page['changed_reads'])
        assert page['page_bytes'] == delivered <= currentness.PAGE_BYTES and page['proposal_version'] == version
        assert page['coverage']['evidence_replays'] == 39, 'every page observes every consulted read (stated cost)'
    assert (tmp_path / 'contract' / 'talk.jsonl').read_bytes() == journal, 'HTTP pages bank nothing'
    assert not calls and (md / 'main.tex').read_text().startswith('\\documentclass')


def test_the_native_door_pages_the_same_owner_and_banks_only_its_navigation_receipt(tmp_path, monkeypatch):
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, 12)
    for path in paths:
        path.write_text('Changed.')
    request = nav.handle('fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads', 'limit': 4})['native_request']
    native, ids = [], []
    while request:
        page = writing_tools.call(tmp_path, 'fixture', 'revise', request, turn_id=turn)['owner_response']
        native.append(page); ids += [row['read_id'] for row in page['changed_reads']]
        request = page['next'] and page['next']['native_request']
    assert len(ids) == len(set(ids)) == 12 and all(len(page['changed_reads']) <= 4 for page in native)
    _, http_first = _http(tmp_path, monkeypatch, nav.handle('fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads', 'limit': 4}))
    assert [row['read_id'] for row in http_first['changed_reads']] == ids[:4], 'one owner behind both doors'
    rows = [json.loads(line) for line in (tmp_path / 'contract' / 'talk.jsonl').read_text().splitlines()]
    banked = [row for row in rows if row.get('operation') == 'authoring/proposal-preview']
    assert len(banked) == len(native) and all(row['record'] == 'writing-tool-read' for row in banked)
    assert not any(row.get('record') in {'writing-tool-read-baseline', 'writing-application'} for row in rows)


def _synthetic_reads(root, turn, payloads):
    for index, (operation, payload) in enumerate(payloads):
        writing_records.bank(root, {'record': 'writing-tool-read', 'id': f'READ-page-{index}', 'turn_id': turn, 'project': 'fixture',
                             'operation': operation, 'payload': payload, 'output_sha256': 'sha256:' + '1' * 64})


def test_cjk_escaped_and_oversized_payloads_stay_bounded_with_exact_detail_handles(tmp_path, monkeypatch):
    from test_proposal_lifecycle import setup
    from test_writing_controller import _bind_rewrite_fixture
    md, turn, changes, _ = setup(tmp_path)
    _bind_rewrite_fixture(monkeypatch, md)
    project = writing_artifacts.project_root(tmp_path, 'fixture')
    names = ['证据-“引号”.txt', 'quote-"\\-tab\t.txt', 'résumé.txt']
    for name in names:
        (project / name).write_text('Original.')
        writing_tools.execute(tmp_path, 'fixture', 'revise', 'read_artifact', {'path': name, 'scope': 'project'}, turn_id=turn)
    long = {'path': 'long-' + '长' * 900 + '.txt', 'scope': 'project'}
    _synthetic_reads(tmp_path, turn, [('read_artifact', long)])
    writing_records.bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-cjk', 'turn_id': turn, 'project': 'fixture',
                             'proposal': {'answer': 'x', 'edits': changes}})
    version = session_reads._records(tmp_path)['turns'][turn]['pending_proposal_version']
    for name in names:
        (project / name).write_text('Changed 变更.')
    pages = _traverse(tmp_path, monkeypatch, nav.handle('fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads', 'limit': 2}))
    rows = [row for page in pages for row in page['changed_reads']]
    assert len(rows) == 4 and all(page['page_bytes'] <= currentness.PAGE_BYTES for page in pages)
    oversized = next(row for row in rows if row['read_id'] == 'READ-page-0')
    assert oversized['renew'] is None and oversized['payload_omitted'] is True
    assert oversized['read_detail'] == {'operation': 'author_history', 'payload': {'view': 'record', 'id': 'activity:journal:READ-page-0'}}
    renewed = {row['renew']['payload']['path'] for row in rows if row['renew']}
    assert renewed == set(names), 'exact payloads, escaping and CJK intact'
    for page in pages:   # bytes are UTF-8 bytes, not characters
        assert page['page_bytes'] == sum(len(json.dumps(row, ensure_ascii=False).encode()) for row in page['changed_reads'])


def test_a_current_candidate_observes_everything_and_lists_nothing(tmp_path, monkeypatch):
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, 6)
    page = nav.read(tmp_path, 'fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads'})
    assert page['status'] == 'OBSERVED' and page['observation']['consulted'] == 6 and page['observation']['changed'] == 0
    assert page['changed_reads'] == [] and page['complete'] is True and page['next'] is None


def _first_and_cursor(root, monkeypatch, turn, version):
    _, first = _http(root, monkeypatch, nav.handle('fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads', 'limit': 2}))
    return first, first['next']['native_request']['payload']['cursor']


def test_foreign_stale_tampered_and_misplaced_continuations_refuse(tmp_path, monkeypatch):
    import base64
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, 8)
    for path in paths:
        path.write_text('Changed.')
    first, cursor = _first_and_cursor(tmp_path, monkeypatch, turn, version)
    page = lambda **extra: nav.read(tmp_path, 'fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads', **extra})
    with pytest.raises(ValueError, match='malformed'):
        page(cursor='not-a-cursor!')
    decoded = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
    for change, said in ((dict(position=999), 'outside'), (dict(position=0), 'outside'), (dict(cut='sha256:' + '0' * 64), 'changed since this traversal'),
                         (dict(schema='other'), 'malformed')):
        forged = base64.urlsafe_b64encode(json.dumps({**decoded, **change}).encode()).decode().rstrip('=')
        with pytest.raises(ValueError, match=said):
            page(cursor=forged)
    with pytest.raises(ValueError, match='queue filters'):     # a page cursor belongs to this view only
        nav.read(tmp_path, 'fixture', {'id': turn, 'proposal_version': version, 'view': 'summary', 'cursor': cursor})
    with pytest.raises(ValueError, match='another project|registered'):
        nav.read(tmp_path, 'another-project', {'id': turn, 'proposal_version': version, 'view': 'changed-reads', 'cursor': cursor})
    with pytest.raises(ValueError, match='unavailable'):
        nav.read(tmp_path, 'fixture', {'id': turn, 'proposal_version': 'sha256:' + 'f' * 64, 'view': 'changed-reads'})
    # another candidate of the same turn: its cut differs, so the first candidate's cursor is refused there
    writing_records.bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-other', 'turn_id': turn, 'project': 'fixture',
                             'proposal': {'answer': 'A different candidate.', 'edits': session_reads._records(tmp_path)['turns'][turn]['proposal_versions'][version]['edits']}})
    other = session_reads._records(tmp_path)['turns'][turn]['pending_proposal_version']
    assert other != version
    with pytest.raises(ValueError, match='changed since this traversal'):
        nav.read(tmp_path, 'fixture', {'id': turn, 'proposal_version': other, 'view': 'changed-reads', 'cursor': cursor})
    assert page(cursor=cursor)['changed']['from'] == first['changed']['to'], 'the original continuation still works'


def test_a_selected_source_change_ends_the_traversal_explicitly(tmp_path, monkeypatch):
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, 8)
    for path in paths:
        path.write_text('Changed.')
    _, cursor = _first_and_cursor(tmp_path, monkeypatch, turn, version)
    (md / 'main.tex').write_text((md / 'main.tex').read_text() + '\n% moved\n')
    try:
        page = nav.read(tmp_path, 'fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads', 'cursor': cursor})
    except ValueError as refused:
        assert 'start again' in str(refused)
    else:   # the candidate itself no longer stands on its consumed source: no rows, no continuation
        assert page['changed_reads'] == [] and page['next'] is None and page['currentness'] != 'CURRENT'


def test_pages_renew_nothing_and_an_exact_read_renews_only_its_own_witness(tmp_path, monkeypatch):
    md, turn, version, paths, calls = seed_reads(tmp_path, monkeypatch, 3)
    for path in paths:
        path.write_text('Changed.')
    pages = _traverse(tmp_path, monkeypatch, nav.handle('fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads'}))
    first = pages[0]['changed_reads'][0]
    assert _refusal(tmp_path, turn, version)['consumed_read_recovery']['observed_changed_read_count'] == 3, 'pages renewed nothing'
    writing_tools.execute(tmp_path, 'fixture', 'revise', first['renew']['operation'], first['renew']['payload'], turn_id=turn)
    assert _refusal(tmp_path, turn, version)['consumed_read_recovery']['observed_changed_read_count'] == 3, \
        'the sealed candidate stays refused: a later read never rebases its consumed receipts'
    writing_records.bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-fresh', 'turn_id': turn, 'project': 'fixture',
                             'proposal': {'answer': 'Fresh candidate.', 'edits': session_reads._records(tmp_path)['turns'][turn]['proposal_versions'][version]['edits']}})
    fresh = session_reads._records(tmp_path)['turns'][turn]['pending_proposal_version']
    recovery = _refusal(tmp_path, turn, fresh)['consumed_read_recovery']
    assert recovery['observed_changed_read_count'] == 2, 'the fresh candidate consumed the renewed read and still refuses the two changed ones'
    assert first['read_id'] not in {row['read_id'] for row in recovery['changed_reads']}
    assert not calls


def test_the_saved_failure_record_carries_the_page_handle_for_the_human_view(tmp_path, monkeypatch):
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, 9)
    for path in paths:
        path.write_text('Changed.')
    with pytest.raises(currentness.ProposalBasisRefused) as refused:
        source_application.apply_proposal(tmp_path, {'turn_id': turn, 'proposal_version': version})
    writing_tools.tool_failure(tmp_path, 'fixture', 'revise', 'apply_revision', {'turn_id': turn, 'proposal_version': version},
                               refused.value, turn)
    failure = next(json.loads(line) for line in (tmp_path / 'contract' / 'talk.jsonl').read_text().splitlines()
                   if '"writing-tool-failure"' in line)
    status, record = _http(tmp_path, monkeypatch, {'http': {'method': 'GET', 'url': '/authoring/history?project=fixture&view=record&id=activity%3Ajournal%3A' + failure['id']}})
    assert status == 200, record
    saved = json.dumps(record)
    assert '"changed_reads_page"' in saved, 'the public saved-failure record offers the page handle the human view opens'
    page = next(value for value in _walk(record) if isinstance(value, dict) and 'changed_reads_page' in value)['changed_reads_page']
    assert page['http']['url'].startswith('/authoring/proposal-preview?') and 'view=changed-reads' in page['http']['url']
    status, first = _http(tmp_path, monkeypatch, page)
    assert status == 200 and first['turn_id'] == turn and len(first['changed_reads']) >= 1


def _walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


# --- repair1 (2026-10-16): AR-R1 observation cut, AR-R2 actual work and whole-response bound ---

def _page(root, turn, version, **extra):
    return nav.read(root, 'fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads', **extra})


@pytest.mark.parametrize('moved', ['already-observed unchanged read', 'not-yet-listed changed read', 'disappearance'])
def test_evidence_that_moves_between_pages_refuses_the_continuation_and_nothing_is_called_complete(tmp_path, monkeypatch, moved):
    """Sol's shape: eight consulted artifact reads; the later ones changed; then evidence moves between pages."""
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, 8)
    for path in paths[5:]:
        path.write_text('Changed.')
    first = _page(tmp_path, turn, version, limit=1)
    assert first['changed'] == {'from': 0, 'to': 1, 'of': 3} and first['complete'] is False
    cursor = first['next']['native_request']['payload']['cursor']
    {'already-observed unchanged read': lambda: paths[0].write_text('Moved after it was observed.'),
     'not-yet-listed changed read': lambda: paths[7].write_text('Changed again.'),
     'disappearance': lambda: paths[6].unlink()}[moved]()
    with pytest.raises(ValueError, match='changed since this traversal started'):
        _page(tmp_path, turn, version, limit=1, cursor=cursor)
    fresh = _page(tmp_path, turn, version, limit=1)
    assert fresh['observation']['cut'] != first['observation']['cut'], 'the new evidence is another observation cut'
    assert fresh['observation']['changed'] == {'already-observed unchanged read': 4, 'not-yet-listed changed read': 3, 'disappearance': 3}[moved]


def test_evidence_that_returns_to_the_observed_bytes_gives_the_same_cut_and_the_traversal_completes_exactly(tmp_path, monkeypatch):
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, 8)
    for path in paths[5:]:
        path.write_text('Changed.')
    first = _page(tmp_path, turn, version, limit=1)
    paths[6].unlink()
    with pytest.raises(ValueError, match='changed since'):
        _page(tmp_path, turn, version, limit=1, cursor=first['next']['native_request']['payload']['cursor'])
    paths[6].write_text('Changed.')                                  # reappears exactly as observed
    ids, request = [row['read_id'] for row in first['changed_reads']], first['next']['native_request']['payload']
    while request:
        page = _page(tmp_path, turn, version, **{key: request[key] for key in ('cursor', 'limit')})
        assert page['observation']['cut'] == first['observation']['cut']
        ids += [row['read_id'] for row in page['changed_reads']]
        request = page['next'] and page['next']['native_request']['payload']
    assert len(ids) == len(set(ids)) == 3 and page['complete'], 'exact for the one stated cut'


def _counting(monkeypatch):
    """Instrument the actual raw journal opens (with their indexed line bytes) and custody body reads."""
    from laplace.representation import writing_bodies as bodies
    seen = {'raw': 0, 'raw_bytes': 0, 'custody': 0, 'custody_bytes': 0}
    raw, read_bytes = nav._raw, bodies.read_bytes
    def counted_raw(idx, meta):
        seen['raw'] += 1; seen['raw_bytes'] += meta['_end'] - meta['_offset']
        return raw(idx, meta)
    def counted_bytes(value, root):
        seen['custody'] += 1
        raw = read_bytes(value, root)
        seen['custody_bytes'] += len(raw)
        return raw
    monkeypatch.setattr(nav, '_raw', counted_raw)
    monkeypatch.setattr(bodies, 'read_bytes', counted_bytes)
    return seen


def _superseded(tmp_path, monkeypatch, answer='Measured.'):
    """Sol's AR-R2 shape: 39 sealed reads plus 20 superseding re-reads, then a new candidate on them."""
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, 39)
    for path in paths[:20]:
        path.write_text('Re-read.')
        writing_tools.execute(tmp_path, 'fixture', 'revise', 'read_artifact', {'path': path.name, 'scope': 'project'}, turn_id=turn)
    edits = session_reads._records(tmp_path)['turns'][turn]['proposal_versions'][version]['edits']
    writing_records.bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-measured', 'turn_id': turn, 'project': 'fixture',
                             'proposal': {'answer': answer, 'edits': edits}})
    return turn, session_reads._records(tmp_path)['turns'][turn]['pending_proposal_version'], paths


def test_projection_counters_equal_the_actual_raw_opens_bytes_and_custody_reads(tmp_path, monkeypatch):
    turn, version, _ = _superseded(tmp_path, monkeypatch, answer='Long candidate text. ' * 600)   # > 8 KiB: custodied
    seen = _counting(monkeypatch)
    coverage = nav.selected_records(tmp_path, 'fixture', turn, version)['coverage']
    assert coverage['raw_records'] == seen['raw'] == coverage['planned']['records'] == coverage['body_reads']
    assert coverage['raw_line_bytes'] == seen['raw_bytes'] == coverage['planned']['line_bytes']
    assert coverage['custody_reads'] == seen['custody'] >= 1 and coverage['custody_bytes'] == seen['custody_bytes'] > 8192
    roles = coverage['raw_by_role']
    assert roles['positional-read'] == coverage['positional_reads'] == 20 and roles['sealed-read'] == 39
    assert sum(roles.values()) == coverage['raw_records'], 'every open has a role; positional work is not hidden'


def test_one_row_page_and_full_traversal_report_their_whole_work(tmp_path, monkeypatch):
    turn, version, paths = _superseded(tmp_path, monkeypatch)
    for path in paths:
        path.write_text('Changed.')
    seen = _counting(monkeypatch)
    one = _page(tmp_path, turn, version, limit=1)
    work = one['coverage']
    assert work['raw_records'] == seen['raw'] and work['raw_line_bytes'] == seen['raw_bytes'], 'a one-row page states its whole preparation'
    assert work['positional_reads'] == 20 and work['evidence_replays'] == 39 and len(one['changed_reads']) == 1
    assert work['budget']['spent'] == work['raw_line_bytes'] + work['custody_bytes'] <= work['budget']['bytes']
    pages, request = [one], one['next']['native_request']['payload']
    while request:
        pages.append(_page(tmp_path, turn, version, cursor=request['cursor'], limit=1))
        request = pages[-1]['next'] and pages[-1]['next']['native_request']['payload']
    assert len(pages) == 39 and sum(page['coverage']['raw_records'] for page in pages) == seen['raw'], 'per page, input-dependent, stated'
    assert sum(page['coverage']['evidence_replays'] for page in pages) == 39 * 39


def test_a_selection_over_the_preparation_bound_is_refused_before_anything_is_opened(tmp_path, monkeypatch):
    turn, version, paths = _superseded(tmp_path, monkeypatch)
    paths[0].write_text('Changed.')
    seen = _counting(monkeypatch)
    monkeypatch.setattr(nav, 'PREPARATION_RECORDS', 10)
    with pytest.raises(ValueError, match='allows 10 records'):
        _page(tmp_path, turn, version)
    assert seen == {'raw': 0, 'raw_bytes': 0, 'custody': 0, 'custody_bytes': 0}
    monkeypatch.setattr(nav, 'PREPARATION_RECORDS', 4096)
    monkeypatch.setattr(currentness, 'PAGE_CONSULTED_MAX', 10)
    with pytest.raises(ValueError, match='observes at most 10'):
        _page(tmp_path, turn, version)


def test_the_whole_response_bound_trims_rows_and_the_traversal_stays_exact(tmp_path, monkeypatch):
    from test_proposal_lifecycle import setup
    from test_writing_controller import _bind_rewrite_fixture
    md, turn, changes, _ = setup(tmp_path)
    _bind_rewrite_fixture(monkeypatch, md)
    project = writing_artifacts.project_root(tmp_path, 'fixture')
    names = ['证据-%02d-“引号”\\"转义\t.txt' % n for n in range(12)]
    for name in names:
        (project / name).write_text('原文 ' * 50)
        writing_tools.execute(tmp_path, 'fixture', 'revise', 'read_artifact', {'path': name, 'scope': 'project'}, turn_id=turn)
    writing_records.bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-wide', 'turn_id': turn, 'project': 'fixture',
                             'proposal': {'answer': 'x', 'edits': changes}})
    version = session_reads._records(tmp_path)['turns'][turn]['pending_proposal_version']
    for name in names:
        (project / name).write_text('变更 ' * 60)
    monkeypatch.setattr(currentness, 'PAGE_RESPONSE_BYTES', 6500)
    pages = _traverse(tmp_path, monkeypatch, nav.handle('fixture', {'id': turn, 'proposal_version': version, 'view': 'changed-reads', 'limit': 20}))
    rows = [row for page in pages for row in page['changed_reads']]
    assert len(rows) == len({row['read_id'] for row in rows}) == 12 and len(pages) > 1
    assert all(page['response_bytes'] <= 6500 for page in pages) and all(len(page['changed_reads']) >= 1 for page in pages)
    assert all(len(json.dumps(row, ensure_ascii=False).encode()) <= currentness.ROW_BYTES for row in rows)


def test_an_early_refusal_is_not_an_observation_and_not_complete(tmp_path, monkeypatch):
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, 4)
    (md / 'main.tex').write_text((md / 'main.tex').read_text().replace('First premise.', 'Someone else edited this.'))
    page = _page(tmp_path, turn, version)
    assert page['status'] == 'REFUSED' and page['observation'] is None and page['complete'] is False
    assert page['changed_reads'] == [] and page['next'] is None and 'nothing was observed' in page['note']


def test_one_row_never_exceeds_its_byte_bound_whatever_its_parts(tmp_path):
    # every part sits just under its own limit (inspect 800, selectors 1200, renew 1600), so only the row bound trims
    observed = {'read_id': 'READ-' + 'x' * 200, 'operation': 'read_artifact', 'currentness': 'CHANGED',
                'consumed_output_sha256': 'sha256:' + 'a' * 64, 'observed_output_sha256': 'sha256:' + 'b' * 64,
                'changed_selectors': {'changed': ['é' * 540], 'removed': [], 'added': [], 'coverage': {'complete': True}},
                'inspect_reads': [{'operation': 'read_artifact', 'payload': {'path': 'é' * 360}}] * 2}
    read = {'operation': 'read_artifact', 'payload': {'path': 'é' * 740}}
    parts = [observed['inspect_reads'][0], {k: v for k, v in observed['changed_selectors'].items() if k != 'coverage'},
             {'operation': 'read_artifact', 'payload': read['payload']}]
    assert [len(json.dumps(part, ensure_ascii=False).encode()) < limit for part, limit in zip(parts, (800, 1200, 1600))] == [True] * 3
    row = currentness._page_row(observed, read)
    assert len(json.dumps(row, ensure_ascii=False).encode()) <= currentness.ROW_BYTES
    assert 'inspect_reads' not in row, 'the inspect reads gave way first'
    assert row['read_detail']['payload']['id'] == 'activity:journal:' + observed['read_id'], 'the exact receipt always remains'


# --- repair2 (2026-10-16): AR-R2-R1 recursive custody and legacy detail inside one preparation budget ---

def _custodied(tmp_path, monkeypatch, reads=2, answer='长' * 20000):
    """Sol's witness shape: a few consulted reads and a candidate whose ~60 KB answer the real custody owner stores."""
    md, turn, version, paths, _ = seed_reads(tmp_path, monkeypatch, reads)
    edits = session_reads._records(tmp_path)['turns'][turn]['proposal_versions'][version]['edits']
    writing_records.bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-custodied', 'turn_id': turn, 'project': 'fixture',
                             'proposal': {'answer': answer, 'edits': edits}})
    rows = [json.loads(line) for line in (tmp_path / 'contract' / 'talk.jsonl').read_text().splitlines()]
    carrier = next(row for row in rows if row.get('id') == 'PROP-custodied')
    assert carrier['proposal'].get('content_handle') and carrier['proposal']['bytes'] > 60000, 'stored through the custody owner'
    for path in paths:
        path.write_text('Changed.')
    return turn, carrier['proposal_instance_version'], carrier


def _blob_gets(monkeypatch):
    from atlas.store import BlobStore
    calls, get = [], BlobStore.get
    def counted(self, key, **kwargs):
        calls.append(key)
        return get(self, key, **kwargs)
    monkeypatch.setattr(BlobStore, 'get', counted)
    return calls


def test_expanded_custody_counts_against_the_preparation_and_is_refused_before_it_is_read(tmp_path, monkeypatch):
    """Sol witness 1: the byte bound held raw journal bytes only; the 60 KB candidate body expanded outside it."""
    turn, version, carrier = _custodied(tmp_path, monkeypatch)
    probe = _page(tmp_path, turn, version)
    raw = probe['coverage']['raw_line_bytes']
    assert probe['status'] == 'OBSERVED' and probe['coverage']['custody_bytes'] == carrier['proposal']['bytes']
    assert probe['coverage']['budget']['spent'] == raw + carrier['proposal']['bytes'], 'one combined preparation budget'
    monkeypatch.setattr(nav, 'PREPARATION_BYTES', raw + 1)
    gets = _blob_gets(monkeypatch)
    with pytest.raises(ValueError, match='budget') as refused:
        _page(tmp_path, turn, version)
    assert 'custody body' in str(refused.value) and 'fresh proposal' in str(refused.value)
    assert gets == [], 'the body was refused on its declared size, before a byte of it was read'


@pytest.mark.parametrize('select', ['by version', 'by legacy record id'])
def test_modern_and_legacy_selected_detail_share_the_before_any_open_boundary(tmp_path, monkeypatch, select):
    """Sol witness 3: a carrier without index projection metadata (a custodied body) was opened by _detail's projection
    before the preparation check; now every open is inside the same records/bytes preparation."""
    turn, version, carrier = _custodied(tmp_path, monkeypatch)
    journal = tmp_path / 'contract' / 'talk.jsonl'
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    for row in rows:      # Sol's legacy model: remove only the optional projection metadata from this disposable carrier
        if row.get('id') == 'PROP-custodied':
            row.pop('proposal_projection', None)
    journal.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    assert 'proposal_projection' not in nav.writing_records.index(tmp_path).by_id['PROP-custodied'][0], 'the legacy shape'
    seen, gets = _counting(monkeypatch), _blob_gets(monkeypatch)
    monkeypatch.setattr(nav, 'PREPARATION_RECORDS', 1)
    query = {'id': turn, 'view': 'changed-reads', **({'proposal_version': version} if select == 'by version' else {'record_id': 'PROP-custodied'})}
    with pytest.raises(ValueError, match='budget|allows 1 records'):
        nav.read(tmp_path, 'fixture', query)
    assert seen['raw'] <= 1 and gets == [] and seen['custody'] == 0, 'no custody body expands before the refusal'
    monkeypatch.setattr(nav, 'PREPARATION_RECORDS', 4096)
    page = _page(tmp_path, turn, version) if select == 'by version' else nav.read(tmp_path, 'fixture', {'id': turn, 'record_id': 'PROP-custodied', 'view': 'changed-reads'})
    assert page['status'] == 'OBSERVED' and page['record_id'] == 'PROP-custodied'
    assert page['coverage']['raw_records'] == seen['raw'] and page['coverage']['custody_reads'] == seen['custody']


def _reference(root, value):
    from laplace.representation import writing_bodies as bodies
    raw = core_bodies.encode(value)
    return {'schema_version': core_bodies.REFERENCE_SCHEMA, 'content_handle': bodies.store(root).put(raw),
            'store': 'contract/writing_bodies', 'bytes': len(raw), 'encoding': 'application/json'}


def test_nested_custody_reads_are_counted_and_charged_at_every_depth(tmp_path, monkeypatch):
    """Sol witness 2: an outer candidate body holding a public referenced answer; the old counter saw one reference."""
    from laplace.representation import writing_bodies as bodies
    inner = _reference(tmp_path, 'Inner answer ' * 20)
    outer = _reference(tmp_path, {'answer': inner, 'edits': []})
    seen = _counting(monkeypatch)
    work = nav._work()
    with core_bodies.budget() as ledger:
        resolved = nav._resolved({'proposal': outer}, tmp_path, work)
    assert resolved['proposal']['answer'] == 'Inner answer ' * 20
    assert work['custody_reads'] == seen['custody'] == 2 and work['custody_bytes'] == seen['custody_bytes'] == outer['bytes'] + inner['bytes']
    assert ledger['spent'] == outer['bytes'] + inner['bytes']
    with core_bodies.budget(outer['bytes'] + inner['bytes'] - 1):            # the inner body no longer fits
        with pytest.raises(core_bodies.BudgetExceeded):
            nav._resolved({'proposal': outer}, tmp_path, nav._work())


@pytest.mark.parametrize('damage', ['malformed size', 'grown blob', 'corrupt blob', 'missing blob'])
def test_malformed_grown_corrupt_or_missing_custody_refuses_without_unbounded_reads(tmp_path, monkeypatch, damage):
    from laplace.representation import writing_bodies as bodies
    reference = _reference(tmp_path, 'Body ' * 400)
    blob = bodies.store(tmp_path).key_path(reference['content_handle'])
    if damage == 'malformed size':
        reference = {**reference, 'bytes': 'many'}
    elif damage == 'grown blob':
        blob.write_bytes(blob.read_bytes() + b'x' * 50000)
    elif damage == 'corrupt blob':
        raw = bytearray(blob.read_bytes()); raw[3] ^= 1; blob.write_bytes(bytes(raw))
    else:
        blob.unlink()
    said = {'malformed size': 'size is malformed', 'grown blob': 'larger than its reference', 'corrupt blob': 'do not match their key',
            'missing blob': 'not in the store'}[damage]
    with core_bodies.budget(10 ** 6) as ledger:
        with pytest.raises(ValueError, match=said):
            nav._resolved({'proposal': reference}, tmp_path, nav._work())
    assert ledger['reads'] == 0 and ledger['read_bytes'] == 0, 'no damaged body is accepted or counted as read'
    if damage == 'grown blob':
        from atlas.store import BlobStore
        from atlas.errors import BlobHashMismatch
        with pytest.raises(BlobHashMismatch, match='larger than its reference'):
            BlobStore(blob.parent.parent).get(reference['content_handle'], max_bytes=reference['bytes'])


def test_a_pre_instance_legacy_carrier_is_projected_only_inside_the_byte_budget(tmp_path, monkeypatch):
    """A carrier with neither projection metadata nor an instance version must be opened to learn its version: that
    open and its custody expansion are charged to the same preparation, and refused before the body is read."""
    turn, version, carrier = _custodied(tmp_path, monkeypatch)
    journal = tmp_path / 'contract' / 'talk.jsonl'
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    for row in rows:
        if row.get('id') == 'PROP-custodied':
            row.pop('proposal_projection', None); row.pop('proposal_instance_version', None)
    journal.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    seen, gets = _counting(monkeypatch), _blob_gets(monkeypatch)
    monkeypatch.setattr(nav, 'PREPARATION_RECORDS', 0)                         # not even the carrier may be opened
    with pytest.raises(ValueError, match='0-record'):
        nav.read(tmp_path, 'fixture', {'id': turn, 'record_id': 'PROP-custodied', 'view': 'changed-reads'})
    assert seen['raw'] == 0 and gets == []
    monkeypatch.setattr(nav, 'PREPARATION_RECORDS', 4096)
    monkeypatch.setattr(nav, 'PREPARATION_BYTES', 20000)                       # the carrier line fits; its 60 KB body does not
    with pytest.raises(ValueError, match='custody body'):
        nav.read(tmp_path, 'fixture', {'id': turn, 'record_id': 'PROP-custodied', 'view': 'changed-reads'})
    assert gets == [], 'refused on the declared size, before the body was read'


# --- repair3 (2026-10-16): AR-R2-R2 a finite budget never reaches the unbounded nonlocal Atlas fallback ---

def _nonlocal(handle='sha256:' + 'a' * 64, size=3, **extra):
    from laplace.representation import writing_bodies as bodies
    return {'schema_version': core_bodies.REFERENCE_SCHEMA, 'content_handle': handle, 'store': 'atlas', 'bytes': size,
            'encoding': 'application/json', **extra}


def _fallback(monkeypatch, text):
    from laplace.representation import atlas_bridge
    calls = []
    def fallback(*, handle):
        calls.append(handle)
        return {'text': text}
    monkeypatch.setattr(atlas_bridge, 'custody_body', fallback)
    return calls


def test_sol_direct_resolver_nonlocal_reference_under_a_finite_budget_is_refused_before_the_fallback(tmp_path, monkeypatch):
    """Sol reproducer 1: store=atlas, declared 3 bytes, budget 8, a fallback that would return 10,002 bytes."""
    from laplace.representation import writing_bodies as bodies
    calls = _fallback(monkeypatch, json.dumps('x' * 10000))
    with core_bodies.budget(8) as ledger:
        with pytest.raises(core_bodies.BudgetExceeded, match='nonlocal fallback'):
            nav._resolved({'proposal': _nonlocal()}, tmp_path, nav._work())
    assert calls == [] and ledger['reads'] == 0 and ledger['read_bytes'] == 0, 'zero unbounded backend calls'


def test_sol_changed_read_route_legacy_nonlocal_carrier_is_refused_before_the_fallback(tmp_path, monkeypatch):
    """Sol reproducer 2: a legacy carrier whose exact public body ref is marked store=atlas with no local copy, under a
    finite preparation of raw + body + 100 bytes; the fallback would return 120,002 bytes."""
    from laplace.representation import writing_bodies as bodies
    md, turn, old, paths, _ = seed_reads(tmp_path, monkeypatch, 2)
    edits = session_reads._records(tmp_path)['turns'][turn]['proposal_versions'][old]['edits']
    writing_records.bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-legacy-fallback', 'turn_id': turn, 'project': 'fixture',
                             'proposal': {'answer': 'x' * 60000, 'edits': edits}})
    version = session_reads._records(tmp_path)['turns'][turn]['pending_proposal_version']
    raw = _page(tmp_path, turn, version)['coverage']['raw_line_bytes']
    journal = tmp_path / 'contract' / 'talk.jsonl'
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    for row in rows:
        if row.get('id') == 'PROP-legacy-fallback':
            reference = dict(row['proposal']); row['proposal']['store'] = 'atlas'
    bodies.store(tmp_path).key_path(reference['content_handle']).unlink()
    journal.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    monkeypatch.setattr(nav, 'PREPARATION_BYTES', raw + reference['bytes'] + 100)
    calls = _fallback(monkeypatch, json.dumps('x' * 120000))
    with pytest.raises(core_bodies.BudgetExceeded, match='nonlocal fallback') as refused:
        _page(tmp_path, turn, version)
    assert calls == [] and 'fresh proposal' in str(refused.value), 'refused before the fallback, with the way forward'


@pytest.mark.parametrize('case', ['within bound', 'malformed size', 'grown', 'corrupt', 'missing'])
def test_every_nonlocal_shape_under_a_finite_budget_makes_zero_fallback_calls(tmp_path, monkeypatch, case):
    from laplace.representation import writing_bodies as bodies
    text = {'within bound': json.dumps('ok'), 'grown': json.dumps('x' * 5000), 'corrupt': json.dumps('ko')}.get(case, json.dumps('ok'))
    calls = _fallback(monkeypatch, text) if text else None
    if case == 'missing':
        from laplace.representation import atlas_bridge
        calls = []
        monkeypatch.setattr(atlas_bridge, 'custody_body', lambda *, handle: calls.append(handle) or (_ for _ in ()).throw(FileNotFoundError(handle)))
    reference = _nonlocal(size='three' if case == 'malformed size' else len(json.dumps('ok').encode()))
    with core_bodies.budget(10 ** 6):
        with pytest.raises(ValueError, match='size is malformed' if case == 'malformed size' else 'nonlocal fallback'):
            nav._resolved({'proposal': reference}, tmp_path, nav._work())
    assert calls == [], 'a finite budget fails closed for every nonlocal shape, valid ones included'


def test_unbudgeted_and_observing_reads_keep_the_nonlocal_fallback(tmp_path, monkeypatch):
    from laplace.representation import writing_bodies as bodies
    reference = _nonlocal(size=len(json.dumps('ok').encode()))
    calls = _fallback(monkeypatch, json.dumps('ok'))
    assert bodies.resolve_fields({'proposal': reference}, tmp_path)['proposal'] == 'ok', 'default compatibility unchanged'
    with core_bodies.budget() as ledger:                                          # observing ledger: no limit
        assert nav._resolved({'proposal': reference}, tmp_path, nav._work())['proposal'] == 'ok'
    assert len(calls) == 2 and ledger['reads'] == 1 and ledger['read_bytes'] == reference['bytes']
    bad = _nonlocal(size=3)                                                          # default path still refuses a mismatch
    with pytest.raises(ValueError, match='byte count mismatch'):
        bodies.resolve_fields({'proposal': bad}, tmp_path)


def test_a_nonlocal_reference_with_a_local_copy_stays_a_bounded_local_read(tmp_path, monkeypatch):
    from laplace.representation import writing_bodies as bodies
    local = _reference(tmp_path, 'Local body ' * 30)
    calls = _fallback(monkeypatch, json.dumps('never'))
    with core_bodies.budget(10 ** 6) as ledger:
        value = nav._resolved({'proposal': {**local, 'store': 'atlas'}}, tmp_path, nav._work())
    assert value['proposal'] == 'Local body ' * 30 and calls == [] and ledger['read_bytes'] == local['bytes']
