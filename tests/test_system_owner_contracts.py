"""System owner contracts (stream A, 2026-11-02) through the actual owners on public fixtures.

Original cases (research/system-integration-20261102/A/original-cases-8ac5e44791b4.json): an external
website project's "." home claimed every comment ledger in the engine checkout; retained PDF reads with the
exact issued id and pin were refused through the native door; visual briefs learned one required field per
refusal and were told about another kind's fields. The countercases stay refused: foreign, symlinked, nested,
ambiguous, truncated and stale identities. Set SYSTEM_OWNER_EVIDENCE to retain the observed owner values,
including FEEDBACK_ORIGIN_VECTOR for the human-research UI stream. Nothing here is a scientific claim.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from laplace.core import identity_doors
from laplace.pipeline import authoring, correction_origin, registry

TEX = b'\\documentclass{article}\n\\begin{document}\nA bounded claim needs its stated assumption.\n\\end{document}\n'
QUOTE = b'A bounded claim needs its stated assumption.'


def retain(name, value):
    target = os.environ.get('SYSTEM_OWNER_EVIDENCE')
    if target:
        folder = Path(target)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (name + '.json')).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n')


def topology(root, *, nested=True, website=True):
    """A registered conceptric project, a clean second project, an optional nested registered home and the
    compatibility website row, whose sibling clone exists beside this checkout exactly as on the host."""
    root.mkdir(parents=True)
    rows = [{'name': 'p', 'kind': 'conceptric', 'project_dir': 'p', 'tex_root': 'p/manuscript'},
            {'name': 'q', 'kind': 'conceptric', 'project_dir': 'q', 'tex_root': 'q/manuscript'}]
    if nested:
        rows.append({'name': 'inner', 'kind': 'conceptric', 'project_dir': 'p/inner',
                     'tex_root': 'p/inner/manuscript'})
    for row in rows:
        manuscript = root / row['tex_root']
        manuscript.mkdir(parents=True)
        (manuscript / 'main.tex').write_bytes(TEX)
    (root / 'registry_projects.json').write_text(json.dumps({'projects': rows}))
    if website:
        (root.parent / 'phujck.github.io').mkdir()
    return root


def prepared(root, project, request_id):
    expected = list(identity_doors.identities(('prose', project + '::main.tex:3-3', QUOTE)).values())
    body = {'anchor': {'file': 'main.tex', 'line_start': 3, 'line_end': 3, 'quote': 'A bounded claim'},
            'expected': expected, 'request_id': request_id}
    ready = authoring.prepare_correction(project, copy.deepcopy(body), root)
    payload = {'project': project, 'request_id': request_id, 'text': 'Which assumption bounds this claim?',
               'kind': 'note', 'scope': 'passage', 'by': 'author',
               **{key: ready[key] for key in ('anchor', 'source_basis', 'base_revision')}}
    return body, ready, payload


def test_external_website_dot_home_no_longer_claims_engine_project_comments(tmp_path):
    root = topology(tmp_path / 'checkout')
    website = registry.resolve('website', repo_root=root)
    assert website is not None and website.kind == 'site' and website.project_dir == '.'
    # The original collision: joined to the engine root, the website's "." home named the whole checkout.
    assert (root / website.project_dir).resolve() == root.resolve()
    assert website.content_homes(root) == ((root.parent / 'phujck.github.io').resolve(),)
    ledger = correction_origin.canonical_ledger(root, 'p')
    assert ledger == 'p/manuscript/feedback/feedback.jsonl'
    assert registry.content_owners(root / ledger, root) == ('p',)
    with pytest.raises(ValueError, match='external repository'):
        registry.comment_feedback_home('website', root)
    _body, _ready, payload = prepared(root, 'p', 'owner-contract-website-1')
    saved = authoring.bank_correction('p', payload, root)
    assert saved['effect'] == 'RECORDED' and saved['origin_ref']['ledger'] == ledger
    context = registry.project_context('p', root)
    assert context.comment_feedback_ledger == root.resolve() / ledger
    assert context.pipeline_feedback_ledger != context.comment_feedback_ledger
    retain('website-collision', {'website_homes': [str(path) for path in website.content_homes(root)],
                                 'ledger': ledger, 'saved': saved})


def test_nested_registered_home_owns_its_subtree_and_equal_homes_refuse(tmp_path):
    root = topology(tmp_path / 'checkout')
    inner = correction_origin.canonical_ledger(root, 'inner')
    assert inner == 'p/inner/manuscript/feedback/feedback.jsonl'
    assert registry.content_owners(root / inner, root) == ('inner',)
    with pytest.raises(ValueError, match='claimed by another'):
        correction_origin._ledger(root, 'p', inner)
    data = json.loads((root / 'registry_projects.json').read_text())
    data['projects'].append({'name': 'twin', 'kind': 'conceptric', 'project_dir': 'p', 'tex_root': 'p/manuscript'})
    (root / 'registry_projects.json').write_text(json.dumps(data))
    assert registry.content_owners(root / 'p/manuscript/feedback/feedback.jsonl', root) == ('p', 'twin')
    with pytest.raises(ValueError, match='claimed by another'):
        correction_origin.canonical_ledger(root, 'p')


def test_symlinked_foreign_and_escaping_custody_is_refused_without_effect(tmp_path):
    root = topology(tmp_path / 'checkout')
    _body, _ready, payload = prepared(root, 'p', 'owner-contract-link-1')
    foreign = root / 'q/manuscript/feedback'
    foreign.mkdir(parents=True)
    (root / 'p/manuscript/feedback').symlink_to(foreign, target_is_directory=True)
    with pytest.raises(ValueError, match='symbolic link'):
        authoring.bank_correction('p', payload, root)
    assert not (foreign / 'feedback.jsonl').exists()
    for ledger, said in (('q/manuscript/feedback/feedback.jsonl', 'claimed by another'),
                         ('elsewhere/feedback/feedback.jsonl', 'does not belong'),
                         ('../p/manuscript/feedback/feedback.jsonl', 'project-relative'),
                         ('p/manuscript/notes/feedback.jsonl', 'outside canonical')):
        with pytest.raises(ValueError, match=said):
            correction_origin._ledger(root, 'p', ledger)


def test_feedback_origin_vector_save_lookup_reopen_stale_and_settled(tmp_path):
    root = topology(tmp_path / 'checkout')
    body, ready, payload = prepared(root, 'p', 'owner-contract-vector-1')
    home = payload['source_basis']['ledger']
    lookup_before = authoring.correction_request('p', payload['request_id'], root, ledger=home)
    assert lookup_before['effect'] == 'NONE' and lookup_before['receipt'] is None
    saved = authoring.bank_correction('p', payload, root)
    assert authoring.bank_correction('p', payload, root) == saved, 'an exact replay is the same saved comment'
    lookup = authoring.correction_request('p', payload['request_id'], root, ledger=home)
    assert lookup['effect'] == 'RECORDED' and lookup['receipt']['origin_ref'] == saved['origin_ref']
    reopened = authoring.correction_origin('p', saved['origin_ref'], root)
    assert reopened['currentness']['state'] == 'CURRENT'
    source = root / 'p/manuscript/main.tex'
    source.write_bytes(TEX.replace(QUOTE, b'A revised bounded claim keeps its assumption explicit.'))
    stale = authoring.correction_origin('p', saved['origin_ref'], root)
    assert stale['currentness']['state'] == 'CHANGED' and stale['origin_ref'] == saved['origin_ref']
    second = {**payload, 'request_id': 'owner-contract-vector-2', 'text': 'A second question kept as a draft.'}
    with pytest.raises(ValueError, match='Raw source changed'):
        authoring.bank_correction('p', second, root)
    settle_body = {'project': 'p', 'request_id': second['request_id'], 'ledger': home,
                   'submission': copy.deepcopy(second)}
    settled = authoring.settle_correction('p', settle_body, root)
    assert settled['effect'] == 'NOT_ADMITTED' and settled['terminal'] and settled['receipt'] is None
    assert authoring.bank_correction('p', second, root) == settled, 'a settled request never saves later'
    unknown = authoring.correction_request('p', 'owner-contract-vector-3', root,
                                           ledger='p/manuscript/old-edition/feedback/feedback.jsonl')
    assert unknown['effect'] == 'UNKNOWN', 'a caller locator cannot authorize project-wide absence'
    rows = [json.loads(line) for line in (root / home).read_text().splitlines()]
    assert sum('comment' in row for row in rows) == 1
    assert sum(row.get('record') == correction_origin.SETTLEMENT_RECORD for row in rows) == 1
    retain('FEEDBACK_ORIGIN_VECTOR', {
        'schema': 'laplace.feedback-origin-vector/1',
        'producer': 'tests/test_system_owner_contracts.py::test_feedback_origin_vector_save_lookup_reopen_stale_and_settled',
        'project': 'p', 'prepare_body': body, 'prepared': ready, 'payload': payload,
        'lookup_before': lookup_before, 'saved': saved, 'lookup': lookup, 'reopened': reopened,
        'stale': stale, 'settle_body': settle_body, 'settled': settled, 'unknown': unknown})


def pdf_bytes(text=b'Public PDF exact canary endmarker.'):
    """One-page public PDF with a Type1 text stream (the construction tests/test_material_intake.py uses)."""
    parts = [b'%PDF-1.4\n']
    offsets = [0]
    stream = b'BT /F1 12 Tf 30 250 Td (' + text + b') Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    for number, obj in enumerate(objects, 1):
        offsets.append(sum(map(len, parts)))
        parts.append(str(number).encode() + b' 0 obj\n' + obj + b'\nendobj\n')
    start = sum(map(len, parts))
    parts.append(b'xref\n0 6\n0000000000 65535 f \n')
    parts.extend(('%010d 00000 n \n' % offset).encode() for offset in offsets[1:])
    parts.append(b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(start).encode() + b'\n%%EOF\n')
    return b''.join(parts)


def intake_topology(root):
    root.mkdir(parents=True)
    rows = [{'name': name, 'kind': 'project', 'project_dir': name, 'manifest': {'writing': {'kind': 'other'}}}
            for name in ('p', 'q')]
    for row in rows:
        (root / row['project_dir']).mkdir()
    (root / 'registry_projects.json').write_text(json.dumps({'projects': rows}))
    return root


def upload(root, project, raw, request_id, pdf=True):
    from laplace.projects import library, material_intake
    wire = {'request_id': request_id, 'display_name': 'Public original.pdf' if pdf else 'Public original.txt',
            'media_type': 'application/pdf' if pdf else 'text/plain; charset=utf-8', 'declared_size': len(raw),
            'expected_sha256': hashlib.sha256(raw).hexdigest(), 'attach_material': False,
            'expected_revision': library.metadata(project, root)['revision']}
    return material_intake.upload(root, project, wire, raw)


def test_retained_pdf_handles_roundtrip_through_native_door_and_bad_identities_refuse(tmp_path):
    from laplace.native import tools
    from laplace.projects import artifacts
    root = intake_topology(tmp_path / 'checkout')
    raw = pdf_bytes()
    saved = upload(root, 'p', raw, 'owner-contract-pdf-1')
    original = saved['original']
    ident, sha = original['artifact_id'], hashlib.sha256(raw).hexdigest()
    issued = original['material_read']['read_payload']
    assert issued == {'id': ident, 'expected_sha256': sha}
    # The original refused shapes (TOOLFAIL-e1e5031c, -022fc9b3, -ee0ee3d0, -d7032cc5, -bb0ae4de) with this fixture's ids.
    shapes = [dict(issued), {**issued, 'limit': 40000}, {**issued, 'limit': 16000, 'offset': 0},
              {**issued, 'page': 1}, {**issued, 'limit': 16000, 'page': 1, 'page_count': 1},
              {'id': ident, 'expected_sha256': 'sha256:' + sha, 'page': 1, 'page_count': 2},
              dict(original['text_read']['payload'])]
    observed = []
    for shape in shapes:
        result = tools.execute(root, 'p', 'work', 'read_artifact', copy.deepcopy(shape))
        assert result['revision'] == sha and result['material_read']['artifact_id'] == ident
        assert result['material_read']['read_payload']['expected_sha256'] == sha
        assert 'project' not in result['material_read']['read_payload']
        again = tools.execute(root, 'p', 'work', 'read_artifact', copy.deepcopy(result['page_read']['payload']))
        assert again['revision'] == sha
        observed.append({'shape': shape, 'material_read': result['material_read'],
                         'extraction_state': result.get('extraction_state'), 'page_read': result['page_read']})
    with pytest.raises(ValueError, match='another project'):
        artifacts.read(root, 'p', {**issued, 'project': 'q'})
    with pytest.raises(ValueError):
        tools.execute(root, 'p', 'work', 'read_artifact', {**issued, 'project': 'q'})
    with pytest.raises(ValueError, match='Unknown artifact id'):
        tools.execute(root, 'p', 'work', 'read_artifact', {'id': ident[:12]})
    with pytest.raises(ValueError, match='conflict'):
        tools.execute(root, 'p', 'work', 'read_artifact', {'id': ident, 'expected_sha256': '0' * 64})
    other = upload(root, 'q', pdf_bytes(b'Second clean project canary.'), 'owner-contract-pdf-q')
    with pytest.raises(ValueError):
        tools.execute(root, 'p', 'work', 'read_artifact', {'id': other['original']['artifact_id']})
    retain('retained-pdf-handles', {'issued': issued, 'observed': observed})


def test_text_artifact_byte_selectors_and_material_pointer_roundtrip_through_native_door(tmp_path):
    from laplace.native import tools
    from laplace.projects import artifacts, material_intake
    root = intake_topology(tmp_path / 'checkout')
    stored = artifacts.store(root, 'p', {'path': 'notes/unicode.txt', 'before': None,
                                         'content': 'α🧪 exact', 'reason': 'public fixture'})
    first = tools.execute(root, 'p', 'work', 'read_artifact', {'id': stored['id'], 'offset': 0, 'limit': 1})
    assert first['content'] == 'α' and first['next_offset'] == 2
    assert first['material_read']['read_payload'] == {'id': stored['id'], 'offset': 0, 'limit': 1,
                                                      'expected_sha256': stored['revision']}
    assert material_intake.validate_reading(root, 'p', first['material_read']) == first['material_read']
    second = tools.execute(root, 'p', 'work', 'read_artifact', copy.deepcopy(first['read_handle']['payload']))
    assert second['content'] == '🧪'
    with pytest.raises(ValueError):
        material_intake.validate_reading(root, 'q', first['material_read'])


def test_visual_refusal_names_every_missing_field_for_the_chosen_kind_with_validator_template(tmp_path):
    from laplace.native import declarations, tools
    from laplace.pipeline import visual_production as vp
    deployed = vp.authoring_contract()
    template = declarations.visual_create_template()
    assert set(template['kinds']) == set(deployed['variants'])
    for name, row in template['kinds'].items():
        assert row['required'] == deployed['variants'][name]['required']
        assert row['payload'] == deployed['examples'][name] and vp.validate(row['payload']['spec']) is None
    assert declarations.owner_template('visual_create') == template and declarations.owner_template('source') == {}
    # TOOLFAIL-d074d6f3: an artifact brief with a stray top-level action was told plot's source_data was missing.
    bad = {'action': 'create', 'spec': {'id': 'panel', 'kind': 'artifact', 'title': 'Panel', 'question': 'What?',
                                        'caption': 'Caption.', 'run_id': 'run-public', 'artifact_id': 'panel'}}
    with pytest.raises(declarations.PayloadAdmissionError) as refused:
        declarations.validate_owner_payload('visual_create', bad, project='p')
    said = str(refused.value)
    assert said.startswith('Payload rejected') and 'unsupported action' in said and 'source_data' not in said
    response = refused.value.response()
    assert list(response['template']['kinds']) == ['artifact'] and response['refused']['unsupported'] == ['action']
    # TOOLFAIL-ee60598f..: a brief without kind receives every kind's complete template in one refusal.
    with pytest.raises(declarations.PayloadAdmissionError) as refused:
        declarations.validate_owner_payload('visual_create', {'spec': {'id': 'x', 'caption': 'c'}}, project='p')
    assert str(refused.value).startswith('Payload rejected at spec.kind')
    assert set(refused.value.response()['template']['kinds']) == set(deployed['variants'])
    with pytest.raises(declarations.PayloadAdmissionError) as refused:
        declarations.validate_owner_payload('visual_create', {'spec': {'id': 'x', 'kind': 'plot', 'caption': 'c'}},
                                            project='p')
    assert refused.value.missing == ['spec.question', 'spec.series', 'spec.source_data', 'spec.title', 'spec.x']
    with pytest.raises(declarations.PayloadAdmissionError, match='only for a same-ID edit'):
        declarations.validate_owner_payload('visual_create', {'expected_revision': None,
                                            'spec': copy.deepcopy(deployed['examples']['plot']['spec'])}, project='p')
    for name, example in deployed['examples'].items():
        declarations.validate_owner_payload('visual_create', copy.deepcopy(example), project='p')
    root = intake_topology(tmp_path / 'checkout')
    action = tools.execute(root, 'p', 'work', 'help', {'operation': 'visual_create'})['action']
    sections = (action.get('sections') or {}).get('chars', {})
    published = action.get('template') or (tools.execute(root, 'p', 'work', 'help', {
        'operation': 'visual_create', 'section': 'template'})['action']['value'] if 'template' in sections else None)
    compact = declarations.visual_create_template(payloads=False)
    assert published == compact
    assert all(row['required'] == template['kinds'][name]['required'] and row['example'] == name
               for name, row in compact['kinds'].items()), 'help names each example instead of repeating it'
    retain('visual-template', {'template': template, 'refusal': response})


def test_native_declarations_consume_owner_factories_and_keep_continuity_request_fields():
    from laplace.native import declarations
    from laplace.writing.schemas import SCHEMAS
    for operation in ('project', 'development_source', 'work_delivery', 'read_artifact'):
        assert declarations.DECLARATIONS[operation].payload == SCHEMAS[operation]
    intent = 'CI-' + '0123456789abcdef01234567'   # a structurally valid isolated identifier: CI- plus 24 hex
    payload = {'view': 'continuity', 'id': 'WORK-public', 'request': {'part': 'completion', 'intent_id': intent}}
    declarations.validate_owner_payload('project', payload, project='p')
    assert payload['request'] == {'part': 'completion', 'intent_id': intent}, 'nothing is dropped'
    with pytest.raises(declarations.PayloadAdmissionError):
        declarations.validate_owner_payload('project', {**payload, 'project': 'q'}, project='p')
    with pytest.raises(declarations.PayloadAdmissionError):
        declarations.validate_owner_payload('project', {**payload, 'request': {'part': 'completion',
                                                        'intent_id': 'INTENT-public'}}, project='p')


def session_family(root, project='p', sid='WS-family', tid='WT-family'):
    """An ordinary conversation through the journal owner: a session, its admitted turn, the saved reply and one
    tool failure. Callers then bank the configure upsert: the same session ID, unchanged identity, new settings."""
    from laplace.writing import records
    identity = {'record': 'writing-session', 'id': sid, 'project': project, 'role': 'author'}
    records.bank(root, {**identity, 'provider': 'codex', 'model': 'fixture-a', 'effort': 'low'})
    records.bank(root, {'record': 'writing-turn', 'id': tid, 'session_id': sid, 'project': project, 'mode': 'work',
                        'text': 'Which assumption bounds the claim?'})
    records.bank(root, {'record': 'writing-reply', 'id': 'WR-family', 'turn_id': tid, 'session_id': sid,
                        'project': project, 'display_text': 'The stated boundary assumption bounds it.'})
    records.bank(root, {'record': 'writing-tool-failure', 'id': 'TOOLFAIL-family', 'turn_id': tid,
                        'project': project, 'operation': 'read_artifact', 'error': 'Unknown artifact id.'})
    return identity


def saved_reply(root, project='p', sid='WS-family', tid='WT-family', **extra):
    from laplace.writing import session_reads
    return session_reads.public_message(root, {'project': project, 'session_id': sid, 'turn_id': tid,
                                               'part': 'reply', **extra})


def test_legitimate_session_versions_keep_exact_reply_failures_and_current_settings(tmp_path):
    from laplace.writing import records
    from laplace.writing.records import _failures
    root = tmp_path / 'checkout'
    root.mkdir()
    identity = session_family(root)
    before = saved_reply(root)
    assert before['state'] == 'AVAILABLE' and before['content'] == 'The stated boundary assumption bounds it.'
    records.bank(root, {**identity, 'provider': 'codex', 'model': 'fixture-b', 'effort': 'high'})
    after = saved_reply(root)
    assert after['basis'] == before['basis'] and after['session_row_sha256'] == before['session_row_sha256']
    assert saved_reply(root, expected_basis=before['basis'])['content'] == before['content']
    records.bank(root, {**identity, 'provider': 'claude', 'model': 'fixture-c', 'effort': 'medium'})
    third = saved_reply(root, expected_basis=before['basis'])
    assert third['basis'] == before['basis'], 'a settings version is not evidence of the saved reply'
    state = _failures.selected_failure_records(root, 'p', 'WT-family')
    assert state['sessions']['WS-family']['model'] == 'fixture-c', 'runtime readers see the current settings'
    assert [row['id'] for row in state['turns']['WT-family']['tool_failures']] == ['TOOLFAIL-family']
    retain('session-family-reply', {'before_upsert': before, 'after_two_upserts': third})


def test_session_family_pins_are_explicit_and_stale_current_pins_refuse(tmp_path):
    from laplace.writing import records, session_reads
    from laplace.writing.records import _index
    root = tmp_path / 'checkout'
    root.mkdir()
    identity = session_family(root)
    records.bank(root, {**identity, 'provider': 'codex', 'model': 'fixture-b', 'effort': 'high'})
    with records.index_lock:
        idx = records.index(root)
        hashes = [row['_hash'] for row in sorted(idx.by_id['WS-family'], key=lambda row: row['_order'])]
        current = _index.resolve_record_family(idx, 'p', 'WS-family', kind='writing-session',
                                               expected_row_sha256=hashes[-1])
        retained = _index.resolve_record_family(idx, 'p', 'WS-family', kind='writing-session',
                                                retained_row_sha256=hashes[0])
        assert current['version']['selection'] == 'current' and current['raw']['model'] == 'fixture-b'
        assert retained['version']['selection'] == 'retained' and not retained['version']['is_current']
        assert retained['raw']['model'] == 'fixture-a' and current['version']['versions_total'] == 2
        with pytest.raises(ValueError, match='changed since discovery'):
            _index.resolve_record_family(idx, 'p', 'WS-family', expected_row_sha256=hashes[0])
        with pytest.raises(ValueError, match='not one recorded version'):
            _index.resolve_record_family(idx, 'p', 'WS-family', retained_row_sha256='0' * 64)
        with pytest.raises(ValueError, match='name only one'):
            _index.resolve_record_family(idx, 'p', 'WS-family', expected_row_sha256=hashes[-1],
                                         retained_row_sha256=hashes[0])
    with pytest.raises(session_reads.MessagePartRefusal):
        saved_reply(root, expected_basis='sha256:' + '0' * 64)


@pytest.mark.parametrize('case', ['contradictory-family', 'foreign-same-id', 'duplicate-turn', 'duplicate-reply'])
def test_session_family_countercases_refuse_in_the_public_and_failure_readers(tmp_path, case):
    from laplace.writing import records
    from laplace.writing.records import _failures
    root = tmp_path / 'checkout'
    root.mkdir()
    identity = session_family(root)
    records.bank(root, {**identity, 'provider': 'codex', 'model': 'fixture-b', 'effort': 'high'})
    if case == 'contradictory-family':
        records.bank(root, {**identity, 'role': 'review', 'model': 'fixture-c'})
    elif case == 'foreign-same-id':
        records.bank(root, {**identity, 'project': 'q', 'model': 'fixture-c'})
    elif case == 'duplicate-turn':
        records.bank(root, {'record': 'writing-turn', 'id': 'WT-family', 'session_id': 'WS-family', 'project': 'p',
                            'mode': 'work', 'text': 'A second admission under the same identity.'})
    else:
        records.bank(root, {'record': 'writing-reply', 'id': 'WR-family', 'turn_id': 'WT-family',
                            'session_id': 'WS-family', 'project': 'p', 'display_text': 'A different answer.'})
    with pytest.raises(ValueError):
        saved_reply(root)
    if case != 'duplicate-reply':
        with pytest.raises(ValueError):
            _failures.selected_failure_records(root, 'p', 'WT-family')


def test_dispatch_selection_folds_current_child_settings_after_family_validation(tmp_path):
    from laplace.writing import records
    from laplace.writing.records import _fold
    root = tmp_path / 'checkout'
    root.mkdir()
    session_family(root)
    child = {'record': 'writing-session', 'id': 'WS-child', 'project': 'p', 'role': 'worker',
             'dispatch_id': 'DISPATCH-family', 'packet': 'P1'}
    records.bank(root, {**child, 'provider': 'codex', 'model': 'child-a', 'effort': 'low'})
    records.bank(root, {'record': 'writing-turn', 'id': 'WT-child', 'session_id': 'WS-child', 'project': 'p',
                        'mode': 'work', 'dispatch_id': 'DISPATCH-family', 'parent_turn_id': 'WT-family',
                        'text': 'Packet P1.'})
    records.bank(root, {**child, 'provider': 'codex', 'model': 'child-b', 'effort': 'high'})
    records.bank(root, {'record': 'writing-session-settings', 'id': 'WSS-child', 'session_id': 'WS-child',
                        'project': 'p', 'provider': 'codex', 'model': 'child-c', 'effort': 'medium'})
    state, _lookup = _fold._dispatch_records(root, 'p', 'DISPATCH-family')
    assert state['sessions']['WS-child']['model'] == 'child-c', 'every version, then settings, in journal order'
    assert state['turns']['WT-child']['dispatch_id'] == 'DISPATCH-family'
    records.bank(root, {**child, 'packet': 'P2', 'provider': 'codex', 'model': 'child-d', 'effort': 'low'})
    with pytest.raises(ValueError):
        _fold._dispatch_records(root, 'p', 'DISPATCH-family')
