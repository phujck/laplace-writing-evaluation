"""The P3 report builder consumes only a named, pinned atlas.p3.door-census/3 artifact (M5 S3).

Artifacts are produced by the real census reader over the labelled synthetic receipt of
test_p3_census_assurance (no original metadata, no numerical run). The builder is run against an empty temporary
wave directory, so every historical presence key is false and nothing historical is read or written.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from test_front_receipt_protocol import legacy  # noqa: F401  (the retained fixture)
from test_p3_census_assurance import SHA, Binding, _joint, _qid, _receipt, census

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('p3_build_report', ROOT / 'evidence/ATLAS_PROGRAMME/waves/P3-the-read/build_p3_report.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def _artifact(path, value):
    raw = (json.dumps(value) + '\n').encode() if not isinstance(value, bytes) else value
    path.write_bytes(raw)
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _run(tmp_path, capsys, monkeypatch, *args):
    (tmp_path / 'wave').mkdir(exist_ok=True)
    def refuse(*a, **k):
        pytest.fail('the report builder attempted a write')
    for name in ('write_text', 'write_bytes', 'mkdir', 'unlink'):
        monkeypatch.setattr(Path, name, refuse)
    try:
        code = builder.main(['--wave', str(tmp_path / 'wave'), *args])
    finally:
        monkeypatch.undo()
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def receipts(legacy, tmp_path):
    receipt = _receipt(legacy, _joint())
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt))
    digest = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
    identity = census.census_of_run(receipt, receipt_sha256=digest)['receipt']
    return path, Binding(tmp_path / 'meta', identity, _qid(receipt))


def test_an_unproved_artifact_is_consumed_with_every_cell_reason_and_the_absent_receipt_named(receipts, tmp_path, capsys, monkeypatch):
    path, _ = receipts
    value = census.assurance([str(path), str(tmp_path / 'door-cold-10.json')])
    pin = _artifact(tmp_path / 'census.json', value)
    code, out = _run(tmp_path, capsys, monkeypatch, '--census', str(tmp_path / 'census.json'), '--census-sha256', pin)
    assurance = out['door_census_assurance']
    assert code == 0 and assurance['consumed'] and assurance['status'] == 'UNPROVED'
    assert assurance['identity'] == {'path': str(tmp_path / 'census.json'), 'sha256': pin, 'record': 'atlas.p3.door-census/3'}
    bound, absent = assurance['receipts']
    assert absent['codes'] == ['RECEIPT_ABSENT_AT_DECLARED_PATH'] and absent['cells'] == []
    first = bound['cells'][0]
    assert first['budget'] == 4096 and first['status'] == 'UNPROVED' and set(first['codes']) == {'PAID_IDENTITIES_ABSENT', 'GOLD_MAPPING_ABSENT'}
    assert assurance['counts']['absent_receipts'] == 1 and assurance['counts']['proved'] == 0
    assert set(out['presence']) == {'census', 'before', 'arms', 'lens_before', 'lens_after', 'door', 'door_census', 'profile',
                                    'build_profile', 'warm', 'report'} and out['presence']['door_census'] is False


def test_a_supplied_binding_shows_its_answer_but_stays_unproved(receipts, tmp_path, capsys, monkeypatch):
    path, made = receipts
    lineage, _ = made.write()
    pin = _artifact(tmp_path / 'census.json', census.assurance([str(path)], [str(lineage)]))
    code, out = _run(tmp_path, capsys, monkeypatch, '--census', str(tmp_path / 'census.json'), '--census-sha256', pin)
    cell = out['door_census_assurance']['receipts'][0]['cells'][0]
    assert code == 0 and cell['status'] == 'UNPROVED' and cell['supplied_answer'] == 'MEMBER'
    assert 'ORIGINAL_UNPINNED:gold_selection' in cell['codes']


def test_a_complete_artifact_is_consumed_as_proved_per_cell(legacy, tmp_path, capsys, monkeypatch):
    import copy
    from test_front_receipt_protocol import rechain, stage
    run = copy.deepcopy(legacy)
    run['dataset'] = 'longmem'
    questions = stage(run, 'read')['payload']['questions']
    for question in questions:                    # every question carries the same labelled synthetic joint read
        question['joint_section_read'] = _joint()
    run['questions'] = copy.deepcopy(questions)
    rechain(run)
    receipt = {'record': 'atlas.front-door-run/1', 'datasets': {'longmem': run}}
    path = tmp_path / 'complete.json'
    path.write_text(json.dumps(receipt))
    digest = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
    identity = census.census_of_run(receipt, receipt_sha256=digest)['receipt']
    made = Binding(tmp_path / 'meta', identity, questions[0]['qid'])
    for question in questions[1:]:
        made.gold['rows'][question['qid']] = made.gold['rows'][made.qid]
        made.paid['rows'][question['qid']] = made.paid['rows'][made.qid]
    lineage, binding = made.write()
    value = census.assurance([str(path)], [str(lineage)], retained=made.registry(binding))
    assert value['status'] == 'PROVED', value['receipts'][0]['issues']
    pin = _artifact(tmp_path / 'census.json', value)
    code, out = _run(tmp_path, capsys, monkeypatch, '--census', str(tmp_path / 'census.json'), '--census-sha256', pin)
    assurance = out['door_census_assurance']
    assert code == 0 and assurance['status'] == 'PROVED' and assurance['counts'] == {
        'receipts': 1, 'absent_receipts': 0, 'cells': len(questions), 'proved': len(questions), 'unproved': 0}
    assert all(cell['status'] == 'PROVED_MEMBER' for cell in assurance['receipts'][0]['cells'])


@pytest.mark.parametrize('case,code', [
    ('unnamed', 'ASSURANCE_NOT_NAMED'), ('absent', 'ASSURANCE_ABSENT_AT_DECLARED_PATH'), ('unpinned', 'ASSURANCE_PIN_MISSING'),
    ('altered', 'ASSURANCE_DIGEST_MISMATCH'), ('not-json', 'ASSURANCE_MALFORMED'), ('missing-fields', 'ASSURANCE_MALFORMED'),
    ('bad-cell', 'ASSURANCE_MALFORMED'), ('historical', 'ASSURANCE_VERSION_HISTORICAL'), ('unknown', 'ASSURANCE_VERSION_UNKNOWN'),
    ('inconsistent', 'ASSURANCE_STATUS_INCONSISTENT')])
def test_every_unusable_artifact_is_refused_with_its_code(receipts, tmp_path, capsys, monkeypatch, case, code):
    path, _ = receipts
    good = census.assurance([str(path)])
    target = tmp_path / 'census.json'
    values = {'not-json': b'{"record": ', 'missing-fields': {'record': 'atlas.p3.door-census/3', 'status': 'UNPROVED'},
              'historical': {'record': 'atlas.p3.door-census/2', 'status': 'UNPROVED'}, 'unknown': {'record': 'atlas.p3.door-census/9'},
              'inconsistent': {**good, 'status': 'PROVED'}}
    if case == 'bad-cell':
        bad = json.loads(json.dumps(good))
        bad['receipts'][0]['per_question'][0]['budgets'][0]['status'] = 'PROBABLY'
        values['bad-cell'] = bad
    pin = _artifact(target, values.get(case, good))
    args = {'unnamed': [], 'absent': ['--census', str(tmp_path / 'nowhere.json'), '--census-sha256', pin],
            'unpinned': ['--census', str(target)], 'altered': ['--census', str(target), '--census-sha256', 'sha256:' + '0' * 64]}
    status, out = _run(tmp_path, capsys, monkeypatch, *args.get(case, ['--census', str(target), '--census-sha256', pin]))
    assurance = out['door_census_assurance']
    assert status == 2 and assurance['consumed'] is False and assurance['status'] == 'UNPROVED' and assurance['codes'] == [code]


# --- S3-A2-R1 (M5 assurance-and-recovery, 2026-10-15): nested shapes and per-receipt status before consumption ---

def _complete_value(legacy, tmp_path):
    """A complete PROVED /3 assurance over the labelled synthetic receipt (as the complete-artifact control)."""
    import copy
    from test_front_receipt_protocol import rechain, stage
    run = copy.deepcopy(legacy)
    run['dataset'] = 'longmem'
    questions = stage(run, 'read')['payload']['questions']
    for question in questions:
        question['joint_section_read'] = _joint()
    run['questions'] = copy.deepcopy(questions)
    rechain(run)
    receipt = {'record': 'atlas.front-door-run/1', 'datasets': {'longmem': run}}
    path = tmp_path / 'complete.json'
    path.write_text(json.dumps(receipt))
    identity = census.census_of_run(receipt, receipt_sha256='sha256:' + hashlib.sha256(path.read_bytes()).hexdigest())['receipt']
    made = Binding(tmp_path / 'meta', identity, questions[0]['qid'])
    for question in questions[1:]:
        made.gold['rows'][question['qid']] = made.gold['rows'][made.qid]
        made.paid['rows'][question['qid']] = made.paid['rows'][made.qid]
    lineage, binding = made.write()
    return path, lineage, made.registry(binding)


def _consume(tmp_path, capsys, monkeypatch, value):
    pin = _artifact(tmp_path / 'census.json', value)
    return _run(tmp_path, capsys, monkeypatch, '--census', str(tmp_path / 'census.json'), '--census-sha256', pin)


def test_a_receipt_claiming_proved_over_an_unproved_cell_is_refused(receipts, tmp_path, capsys, monkeypatch):
    """Sol's input: top UNPROVED, one receipt PROVED, its one cell UNPROVED/GOLD_MAPPING_ABSENT."""
    path, _ = receipts
    value = census.assurance([str(path)])
    value['receipts'][0]['status'] = 'PROVED'
    value['receipts'][0]['per_question'][0]['budgets'][0].update(status='UNPROVED', codes=['GOLD_MAPPING_ABSENT'])
    code, out = _consume(tmp_path, capsys, monkeypatch, value)
    assurance = out['door_census_assurance']
    assert code == 2 and assurance['consumed'] is False and assurance['codes'] == ['ASSURANCE_RECEIPT_STATUS_INCONSISTENT']
    assert assurance['where'] == 'receipts[0]'


def test_mixed_valid_proved_and_unproved_receipts_are_consumed_as_recorded(legacy, tmp_path, capsys, monkeypatch):
    path, lineage, retained = _complete_value(legacy, tmp_path)
    value = census.assurance([str(path), str(tmp_path / 'absent-receipt.json')], [str(lineage)], retained=retained)
    assert [entry['status'] for entry in value['receipts']] == ['PROVED', 'UNPROVED'] and value['status'] == 'UNPROVED'
    code, out = _consume(tmp_path, capsys, monkeypatch, value)
    assurance = out['door_census_assurance']
    assert code == 0 and assurance['consumed'] and assurance['status'] == 'UNPROVED'
    assert [r['status'] for r in assurance['receipts']] == ['PROVED', 'UNPROVED'] and assurance['receipts'][1]['cells'] == []
    assert assurance['counts']['absent_receipts'] == 1 and assurance['counts']['unproved'] == 0


@pytest.mark.parametrize('case,change', [
    ('proved cell with a refusal code', lambda cell: cell.update(status='PROVED_MEMBER', codes=['GOLD_MAPPING_ABSENT'])),
    ('unproved cell without a code', lambda cell: cell.update(status='UNPROVED', codes=[])),
    ('supplied answer on a proved cell', lambda cell: cell.update(status='PROVED_MEMBER', codes=[], supplied_consistent=True, supplied_answer='MEMBER')),
    ('supplied answer beside a non-original code', lambda cell: cell.update(status='UNPROVED', codes=['GOLD_MAPPING_ABSENT'],
                                                                             supplied_consistent=True, supplied_answer='MEMBER')),
])
def test_contradictory_cell_status_and_codes_are_refused(receipts, tmp_path, capsys, monkeypatch, case, change):
    path, _ = receipts
    value = census.assurance([str(path)])
    change(value['receipts'][0]['per_question'][0]['budgets'][0])
    code, out = _consume(tmp_path, capsys, monkeypatch, value)
    assurance = out['door_census_assurance']
    assert code == 2 and assurance['codes'] == ['ASSURANCE_CELL_STATUS_INCONSISTENT'], case
    assert assurance['where'] == 'receipts[0].per_question[0].budgets[0]'


@pytest.mark.parametrize('case,change,where', [
    ('receipt identity not a mapping', lambda v: v['receipts'][0].update(receipt='not-a-mapping'), 'receipts[0].receipt'),
    ('lineage a list', lambda v: v['receipts'][0].update(lineage=['x']), 'receipts[0].lineage'),
    ('lineage codes not text', lambda v: v['receipts'][0].update(lineage={'receipt_codes': [1]}), 'receipts[0].lineage'),
    ('per_question a mapping', lambda v: v['receipts'][0].update(per_question={'q': 1}), 'receipts[0].per_question'),
    ('budgets text', lambda v: v['receipts'][0]['per_question'][0].update(budgets='4096'), 'receipts[0].per_question[0].budgets'),
    ('cell codes text', lambda v: v['receipts'][0]['per_question'][0]['budgets'][0].update(codes='GOLD'), 'receipts[0].per_question[0].budgets[0]'),
    ('question qid a number', lambda v: v['receipts'][0]['per_question'][0].update(qid=7), 'receipts[0].per_question[0]'),
    ('receipt a list', lambda v: v['receipts'].__setitem__(0, []), 'receipts[0]'),
    ('receipt codes a mapping', lambda v: v['receipts'][0].update(codes={'a': 1}), 'receipts[0].codes'),
    ('receipts a mapping', lambda v: v.update(receipts={}), 'artifact'),
])
def test_wrong_nested_shapes_are_refused_with_their_location_never_a_crash(receipts, tmp_path, capsys, monkeypatch, case, change, where):
    path, _ = receipts
    value = census.assurance([str(path)])
    change(value)
    code, out = _consume(tmp_path, capsys, monkeypatch, value)
    assurance = out['door_census_assurance']
    assert code == 2 and assurance['consumed'] is False and assurance['codes'] == ['ASSURANCE_MALFORMED'], case
    assert assurance['where'] == where
