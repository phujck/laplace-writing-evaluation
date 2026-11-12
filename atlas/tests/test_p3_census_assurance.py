"""P3 census assurance (atlas.p3.door-census/3, retained-lineage/2) over labelled synthetic metadata (M5 S3).

The retained legacy front-door fixture is extended, for its first question only, with a synthetic joint-section
read. Every binding names three metadata FILES written here (a record manifest, a gold selection, paid row
identities) that the reader reads and checks by digest. All identities are invented for these controls; none is an
original source posting, gold selection or scientific observation. A cell is PROVED only against an explicitly
passed SYNTHETIC registry of "retained originals"; with the real registry the same complete binding stays UNPROVED
(supplied, not original). No numerical run, ingestion or device import occurs.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from test_front_receipt_protocol import legacy, rechain, stage  # noqa: F401  (the retained fixture)
from atlas.front.receipts import ReceiptProtocolError, question_budget_evidence

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('p3_door_census', ROOT / 'evidence/ATLAS_PROGRAMME/waves/P3-the-read/door_census.py')
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)

ROW, OTHER = 'sha256:' + 'a' * 64, 'sha256:' + 'c' * 64
ITEM, ELSEWHERE = 'sha256:' + 'b' * 64, 'sha256:' + 'e' * 64
IDENTITY = {'row_kind': 'turn', 'content_handle': ITEM, 'start': 100, 'end': 510}
HANDLE = {'row_id': ROW, 'global_ordinal': 3221, 'bytes': 410, **IDENTITY}
SHA = 'sha256:' + 'f' * 64


def _sha(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _counts(supply, budget, rows=1, size=410):
    return {'supply': supply, 'byte_budget': budget, 'rows_supplied': rows, 'bytes_supplied': size, 'rows_needed': rows, 'bytes_needed': size}


def _joint(rows=1, size=410, handles=(HANDLE,), ordinal=3221):
    return {'evidence_by_budget': {'4096': {'partial': _counts('partial', 4096, rows, size), 'whole': _counts('whole', 4096, rows, size)}},
            'handles': [dict(row, global_ordinal=ordinal) for row in handles], 'supplied_global_rows': [ordinal] * len(handles)}


def _receipt(legacy, joint):
    run = copy.deepcopy(legacy)
    run['dataset'] = 'longmem'
    stage(run, 'read')['payload']['questions'][0]['joint_section_read'] = joint
    run['questions'] = copy.deepcopy(stage(run, 'read')['payload']['questions'])
    rechain(run)
    return {'record': 'atlas.front-door-run/1', 'datasets': {'longmem': run}}


def _qid(receipt):
    return stage(receipt['datasets']['longmem'], 'read')['payload']['questions'][0]['qid']


class Binding:
    """Writes the three metadata files and the binding for one receipt identity into a directory."""

    def __init__(self, directory, identity, qid):
        self.dir, self.identity, self.qid = Path(directory), dict(identity), qid
        self.items = [ITEM]
        self.gold = {'schema': census.GOLD, 'evaluator_version': 'synthetic-evaluator/1', 'dataset_id': identity['dataset_id'],
                     'rows': {qid: [{'row_id': ROW, **IDENTITY}]}}
        self.paid = {'schema': census.PAID, 'receipt': {'sha256': identity['sha256'], 'terminal_address': identity['terminal_address']},
                     'rows': {qid: {'4096': {'supply': 'partial', 'order': 'supply', 'complete': True, 'rows': [{'row_id': ROW, 'bytes': 410, **IDENTITY}]}}}}
        self.override = {}

    def files(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        manifest = ''.join(json.dumps({'schema_version': census.MANIFEST_ROW, 'item_content_hash': item, 'dataset_id': self.identity['dataset_id'],
                                       'global_base': index * 10, 'rows': 10}) + '\n' for index, item in enumerate(self.items))
        bodies = {'source_manifest': ('manifest.jsonl', manifest.encode()), 'gold_selection': ('gold.json', json.dumps(self.gold).encode()),
                  'paid_identities': ('paid.json', json.dumps(self.paid).encode())}
        refs = {}
        for kind, (name, raw) in bodies.items():
            (self.dir / name).write_bytes(raw)
            refs[kind] = {'path': name, 'sha256': _sha(raw)}
        binding = {'schema': census.LINEAGE, 'receipt': dict(self.identity), **refs, **self.override}
        return binding

    def write(self, name='lineage.json'):
        binding = self.files()
        (self.dir / name).write_text(json.dumps(binding))
        return self.dir / name, binding

    def registry(self, binding):
        return {kind: frozenset({binding[kind]['sha256']}) for kind in census.KINDS}


def _census(receipt, binding, directory, retained=None, sha=SHA):
    return census.census_of_run(receipt, binding=binding, binding_dir=directory, receipt_sha256=sha, retained=retained)


def _first(result):
    return result['per_question'][0]['budgets'][0]


@pytest.fixture
def case(legacy, tmp_path):
    receipt = _receipt(legacy, _joint())
    identity = census.census_of_run(receipt, receipt_sha256=SHA)['receipt']
    return receipt, Binding(tmp_path / 'meta', identity, _qid(receipt)), tmp_path / 'meta'


def test_a_complete_binding_proves_only_against_retained_originals_and_otherwise_is_supplied_consistency(case):
    receipt, made, directory = case
    binding = made.files()
    proved = _first(_census(receipt, binding, directory, retained=made.registry(binding)))
    assert proved['status'] == 'PROVED_MEMBER' and proved['codes'] == [] and proved['paid_rows'] == 1
    supplied = _first(_census(receipt, binding, directory))
    assert supplied['status'] == 'UNPROVED' and supplied['supplied_consistent'] is True and supplied['supplied_answer'] == 'MEMBER'
    assert set(supplied['codes']) == {'ORIGINAL_UNPINNED:source_manifest', 'ORIGINAL_UNPINNED:gold_selection', 'ORIGINAL_UNPINNED:paid_identities'}


def test_no_binding_keeps_every_cell_unproved_with_reasons_and_no_top_level_reach(case):
    receipt, _, _ = case
    result = census.census_of_run(receipt)
    assert result['status'] == 'UNPROVED' and result['required_work'] == census.REQUIRED_WORK
    assert not any(name in result for name in ('reach_fraction', 'rows_got', 'rows_needed'))
    assert set(_first(result)['codes']) == {'PAID_IDENTITIES_ABSENT', 'GOLD_MAPPING_ABSENT'}


def test_an_invented_paid_row_and_a_gold_row_without_its_identity_never_prove(case):
    """Sol S3-A1 control 1: paid=[invented], gold=[{row_id, content_handle}] only."""
    receipt, made, directory = case
    made.gold['rows'][made.qid] = [{'row_id': OTHER, 'content_handle': ITEM}]
    made.paid['rows'][made.qid]['4096']['rows'] = [{'row_id': OTHER, 'bytes': 410, **IDENTITY}]
    binding = made.files()
    result = _census(receipt, binding, directory, retained=made.registry(binding))
    assert result['lineage']['receipt_codes'] == ['GOLD_SELECTION_MALFORMED'] and 'missing row_kind' in result['lineage']['reasons'][0]
    assert _first(result)['status'] == 'UNPROVED'
    made.gold['rows'][made.qid] = [{'row_id': OTHER, **IDENTITY}]
    binding = made.files()
    cell = _first(_census(receipt, binding, directory, retained=made.registry(binding)))
    assert cell['status'] == 'UNPROVED' and {'PAID_OMITS_RETAINED_HANDLE', 'PAID_HANDLE_SET_DISAGREES'} <= set(cell['codes'])


def test_a_malformed_retained_handle_is_a_typed_refusal_not_a_crash(legacy, tmp_path):
    """Sol S3-A1 control 2: the retained joint handle's row_id is {} with every key present."""
    bad = _receipt(legacy, _joint(handles=({**HANDLE, 'row_id': {}},)))
    with pytest.raises(ReceiptProtocolError, match='row_id is not a canonical digest'):
        question_budget_evidence(stage(bad['datasets']['longmem'], 'read')['payload']['questions'][0])
    identity = census.census_of_run(bad, receipt_sha256=SHA)['receipt']
    made = Binding(tmp_path / 'meta', identity, _qid(bad))
    binding = made.files()
    first = _census(bad, binding, tmp_path / 'meta', retained=made.registry(binding))['per_question'][0]
    assert first['status'] == 'UNPROVED' and first['codes'] == ['BUDGET_EVIDENCE_UNREADABLE']
    for wrong in ({'bytes': 409}, {'start': 510}, {'row_kind': ''}, {'content_handle': 'sha256:short'}, {'global_ordinal': True}):
        joint = _joint()
        joint['handles'][0].update(wrong)
        with pytest.raises(ReceiptProtocolError):
            question_budget_evidence({'qid': 'q', 'joint_section_read': joint})


def test_asserted_digests_without_the_named_bodies_or_with_altered_bodies_refuse(case):
    """Sol S3-A1 control 3: unrelated valid-length digests, and bodies altered after naming."""
    receipt, made, directory = case
    binding = made.files()
    asserted = {**binding, 'source_manifest': {**binding['source_manifest'], 'sha256': 'sha256:' + '1' * 64},
                'gold_selection': {**binding['gold_selection'], 'sha256': 'sha256:' + '4' * 64}}
    result = _census(receipt, asserted, directory, retained={kind: frozenset({asserted[kind]['sha256']}) for kind in census.KINDS})
    assert set(result['lineage']['receipt_codes']) == {'SOURCE_MANIFEST_DIGEST_MISMATCH', 'GOLD_SELECTION_DIGEST_MISMATCH'}
    assert _first(result)['status'] == 'UNPROVED'
    (directory / 'gold.json').write_text(json.dumps({**made.gold, 'evaluator_version': 'altered'}))
    assert 'GOLD_SELECTION_DIGEST_MISMATCH' in _census(receipt, binding, directory, retained=made.registry(binding))['lineage']['receipt_codes']
    (directory / 'manifest.jsonl').unlink()
    assert 'SOURCE_MANIFEST_ABSENT' in _census(receipt, binding, directory)['lineage']['receipt_codes']


def test_conflicting_bindings_for_one_receipt_refuse_in_either_order_and_duplicates_are_idempotent(case, tmp_path):
    """Sol S3-A1 control 4: two lineage files name the same receipt file digest; a pays ROW, b pays OTHER."""
    receipt, _, _ = case
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt))
    digest = _sha(path.read_bytes())
    identity = census.census_of_run(receipt, receipt_sha256=digest)['receipt']
    a = Binding(tmp_path / 'a', identity, _qid(receipt))
    b = Binding(tmp_path / 'b', identity, _qid(receipt))
    b.paid['rows'][b.qid]['4096']['rows'] = [{'row_id': OTHER, 'bytes': 410, **IDENTITY}]
    first, _ = a.write()
    second, _ = b.write()
    results = [census.assurance([str(path)], [str(x), str(y)]) for x, y in ((first, second), (second, first))]
    cells = [result['receipts'][0]['per_question'][0]['budgets'][0] for result in results]
    assert cells[0] == cells[1] and cells[0]['codes'] == ['LINEAGE_CONFLICT'] and cells[0]['status'] == 'UNPROVED'
    copy_dir = tmp_path / 'a-copy'
    copy_dir.mkdir()
    for name in ('manifest.jsonl', 'gold.json', 'paid.json', 'lineage.json'):
        (copy_dir / name).write_bytes((tmp_path / 'a' / name).read_bytes())
    same = census.assurance([str(path)], [str(first), str(copy_dir / 'lineage.json')])['receipts'][0]['per_question'][0]['budgets'][0]
    assert same['status'] == 'UNPROVED' and same['supplied_answer'] == 'MEMBER', 'identical evidence is idempotent, not a conflict'


def test_the_same_extraction_law_with_a_different_source_posting_refuses(case):
    receipt, made, directory = case
    made.items = [ELSEWHERE]
    binding = made.files()
    cell = _first(_census(receipt, binding, directory, retained=made.registry(binding)))
    assert cell['status'] == 'UNPROVED'
    assert {'RECEIPT_HANDLE_OUTSIDE_SOURCE_POSTING', 'GOLD_OUTSIDE_SOURCE_POSTING', 'PAID_OUTSIDE_SOURCE_POSTING'} <= set(cell['codes'])


def test_the_same_count_with_a_different_paid_row_is_a_different_answer(legacy, tmp_path):
    bounded = _receipt(legacy, _joint(handles=()))           # the receipt retained none of its one supplied row
    identity = census.census_of_run(bounded, receipt_sha256=SHA)['receipt']
    answers = []
    for row in (ROW, OTHER):
        made = Binding(tmp_path / row[-4:], identity, _qid(bounded))
        made.paid['rows'][made.qid]['4096']['rows'] = [{'row_id': row, 'bytes': 410, **IDENTITY}]
        binding = made.files()
        answers.append(_first(_census(bounded, binding, made.dir, retained=made.registry(binding)))['status'])
    assert answers == ['PROVED_MEMBER', 'PROVED_NOT_MEMBER']


def test_reordered_ordinals_keep_the_answer_and_ordinal_only_gold_stays_unproved(legacy, tmp_path):
    moved = _receipt(legacy, _joint(ordinal=17))
    identity = census.census_of_run(moved, receipt_sha256=SHA)['receipt']
    made = Binding(tmp_path / 'meta', identity, _qid(moved))
    binding = made.files()
    assert _first(_census(moved, binding, made.dir, retained=made.registry(binding)))['status'] == 'PROVED_MEMBER'
    made.gold['rows'][made.qid] = [{'global_ordinal': 17}]
    binding = made.files()
    assert _census(moved, binding, made.dir, retained=made.registry(binding))['lineage']['receipt_codes'] == ['GOLD_ORDINAL_ONLY']


def test_incomplete_or_miscounted_paid_sets_never_prove_and_a_complete_empty_set_is_known(legacy, tmp_path):
    many = _receipt(legacy, _joint(rows=40, size=16000))
    identity = census.census_of_run(many, receipt_sha256=SHA)['receipt']
    made = Binding(tmp_path / 'many', identity, _qid(many))
    binding = made.files()
    cell = _first(_census(many, binding, made.dir, retained=made.registry(binding)))
    assert cell['status'] == 'UNPROVED' and {'PAID_COUNT_DISAGREES', 'PAID_BYTES_DISAGREE'} <= set(cell['codes'])
    made = Binding(tmp_path / 'flag', census.census_of_run(_receipt(legacy, _joint()), receipt_sha256=SHA)['receipt'], _qid(many))
    made.paid['rows'][made.qid]['4096']['complete'] = False
    binding = made.files()
    assert 'PAID_IDENTITIES_INCOMPLETE' in _first(_census(_receipt(legacy, _joint()), binding, made.dir, retained=made.registry(binding)))['codes']
    empty = _receipt(legacy, _joint(rows=0, size=0, handles=()))
    identity = census.census_of_run(empty, receipt_sha256=SHA)['receipt']
    made = Binding(tmp_path / 'empty', identity, _qid(empty))
    made.paid['rows'][made.qid]['4096']['rows'] = []
    binding = made.files()
    assert _first(_census(empty, binding, made.dir, retained=made.registry(binding)))['status'] == 'PROVED_NOT_MEMBER'
    del made.paid['rows'][made.qid]
    binding = made.files()
    cell = _first(_census(empty, binding, made.dir, retained=made.registry(binding)))
    assert cell['status'] == 'UNPROVED' and 'PAID_IDENTITIES_ABSENT' in cell['codes'], 'missing coverage is not an empty set'


def test_wrong_scope_versions_and_malformed_shapes_refuse_consistently(case, tmp_path):
    receipt, made, directory = case
    checks = [
        (lambda m: m.override.update(schema='atlas.p3.retained-lineage/1'), 'LINEAGE_SCHEMA_UNKNOWN'),
        (lambda m: m.identity.update(terminal_address='sha256:' + '0' * 64), 'LINEAGE_RECEIPT_MISMATCH:terminal_address'),
        (lambda m: m.identity.update(sha256=None), 'LINEAGE_RECEIPT_MISMATCH:sha256'),
        (lambda m: m.gold.update(dataset_id='another-dataset'), 'GOLD_SCOPE_MISMATCH'),
        (lambda m: m.paid['receipt'].update(sha256='sha256:' + '9' * 64), 'PAID_RECEIPT_SCOPE_MISMATCH'),
        (lambda m: m.paid['rows'][m.qid].update({'04096': m.paid['rows'][m.qid]['4096']}), 'PAID_IDENTITIES_MALFORMED'),
        (lambda m: m.paid['rows'][m.qid]['4096']['rows'][0].update(bytes=411), 'PAID_IDENTITIES_MALFORMED'),
    ]
    for index, (change, code) in enumerate(checks):
        fresh = Binding(tmp_path / str(index), made.identity, made.qid)
        change(fresh)
        binding = fresh.files()
        result = _census(receipt, binding, fresh.dir, retained=fresh.registry(binding))
        assert code in result['lineage']['receipt_codes'] and _first(result)['status'] == 'UNPROVED', code
    fresh = Binding(tmp_path / 'supply', made.identity, made.qid)
    fresh.paid['rows'][made.qid]['4096']['supply'] = 'whole'
    binding = fresh.files()
    assert 'PAID_SUPPLY_SCOPE_MISMATCH' in _first(_census(receipt, binding, fresh.dir, retained=fresh.registry(binding)))['codes']
    junk = tmp_path / 'junk.json'
    junk.write_text('[1, 2')
    report = census.assurance([], [str(junk)])
    assert report['lineage_inputs'] == [{'input': str(junk), 'status': 'REFUSED', 'codes': ['LINEAGE_UNREADABLE']}]


def test_a_flat_budget_shape_is_refused_not_coerced(legacy):
    flat = {'evidence_by_budget': {'4096': _counts('partial', 4096)}, 'handles': [HANDLE], 'supplied_global_rows': [3221]}
    with pytest.raises(ReceiptProtocolError, match='not coerced'):
        question_budget_evidence({'qid': 'q', 'joint_section_read': flat})
    assert census.census_of_run(_receipt(legacy, flat))['per_question'][0]['codes'] == ['BUDGET_EVIDENCE_UNREADABLE']


def test_the_cli_binds_by_file_digest_names_absent_paths_keeps_inputs_and_refuses_reuse(case, tmp_path):
    receipt, _, _ = case
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(receipt))
    identity = census.census_of_run(receipt, receipt_sha256=_sha(path.read_bytes()))['receipt']
    made = Binding(tmp_path / 'meta2', identity, _qid(receipt))
    lineage, _ = made.write()
    before = {file.name: file.read_bytes() for file in made.dir.iterdir()} | {'receipt': path.read_bytes()}
    out = tmp_path / 'assurance.json'
    code = census.main(['--receipt', str(path), '--receipt', str(tmp_path / 'absent.json'), '--lineage', str(lineage), '--out', str(out)])
    report = json.loads(out.read_text())
    assert code == 2 and report['status'] == 'UNPROVED'
    bound, missing = report['receipts']
    cell = bound['per_question'][0]['budgets'][0]
    assert cell['status'] == 'UNPROVED' and cell['supplied_answer'] == 'MEMBER', 'the real registry pins no supplied file'
    assert missing == {'input': str(tmp_path / 'absent.json'), 'status': 'UNPROVED', 'codes': ['RECEIPT_ABSENT_AT_DECLARED_PATH']}
    assert report['retained_originals']['gold_selection'] == [] and len(report['retained_originals']['source_manifest']) == 2
    assert ({file.name: file.read_bytes() for file in made.dir.iterdir()} | {'receipt': path.read_bytes()}) == before
    retained = out.read_bytes()
    assert census.main(['--receipt', str(path), '--out', str(out)]) == 2 and out.read_bytes() == retained


# --- S3-A1-R1 (M5 assurance-and-recovery, 2026-10-15): one full identity per stable row_id; pins validated first ---

SPAN = {'row_kind': 'turn', 'content_handle': ITEM, 'start': 200, 'end': 610}


@pytest.mark.parametrize('field,value', [('start', 200), ('row_kind', 'note'), ('content_handle', ELSEWHERE)])
@pytest.mark.parametrize('registry', ['default', 'synthetic'])
def test_one_row_id_naming_different_gold_and_paid_identities_never_proves(legacy, tmp_path, field, value, registry):
    """Sol's input: the receipt retained no handle; gold and paid name the same ROW with different spans/kind/content."""
    bounded = _receipt(legacy, _joint(handles=()))
    identity = census.census_of_run(bounded, receipt_sha256=SHA)['receipt']
    made = Binding(tmp_path / 'meta', identity, _qid(bounded))
    changed = {**IDENTITY, field: value, **({'end': 610} if field == 'start' else {})}
    made.items = [ITEM, ELSEWHERE]
    made.paid['rows'][made.qid]['4096']['rows'] = [{'row_id': ROW, 'bytes': 410, **changed}]
    binding = made.files()
    cell = _first(_census(bounded, binding, made.dir, retained=made.registry(binding) if registry == 'synthetic' else None))
    assert cell['status'] == 'UNPROVED' and 'ROW_IDENTITY_DISAGREES:gold/paid' in cell['codes']
    assert 'supplied_consistent' not in cell and 'supplied_answer' not in cell, 'a contradiction is not a supplied answer'


def test_a_disagreement_outside_the_bounded_retained_subset_is_still_refused(legacy, tmp_path):
    two = _receipt(legacy, _joint(rows=2, size=820))            # two supplied rows, one retained handle (ROW)
    identity = census.census_of_run(two, receipt_sha256=SHA)['receipt']
    made = Binding(tmp_path / 'meta', identity, _qid(two))
    made.gold['rows'][made.qid] = [{'row_id': OTHER, **SPAN}]
    made.paid['rows'][made.qid]['4096']['rows'] = [{'row_id': ROW, 'bytes': 410, **IDENTITY},
                                                   {'row_id': OTHER, 'bytes': 410, **{**SPAN, 'start': 300, 'end': 710}}]
    binding = made.files()
    cell = _first(_census(two, binding, made.dir, retained=made.registry(binding)))
    assert cell['status'] == 'UNPROVED' and cell['codes'] == ['ROW_IDENTITY_DISAGREES:gold/paid']
    made.paid['rows'][made.qid]['4096']['rows'][1] = {'row_id': OTHER, 'bytes': 410, **SPAN}   # consistent: proves
    binding = made.files()
    assert _first(_census(two, binding, made.dir, retained=made.registry(binding)))['status'] == 'PROVED_MEMBER'


def test_retained_handle_versus_gold_or_paid_disagreements_name_their_sources(case):
    receipt, made, directory = case
    made.gold['rows'][made.qid] = [{'row_id': ROW, **SPAN}]
    binding = made.files()
    cell = _first(_census(receipt, binding, directory, retained=made.registry(binding)))
    assert {'ROW_IDENTITY_DISAGREES:retained/gold', 'GOLD_HANDLE_DISAGREES'} <= set(cell['codes']) and cell['status'] == 'UNPROVED'


@pytest.mark.parametrize('pin', [{}, [], None, 7, 'not-a-pin', 'sha256:' + 'A' * 64, {'sha256': SHA}])
def test_a_malformed_lineage_receipt_pin_is_refused_before_grouping(case, tmp_path, pin):
    receipt, made, directory = case
    path, binding = made.write()
    bad = tmp_path / 'bad-lineage.json'
    bad.write_text(json.dumps({**binding, 'receipt': {**binding['receipt'], 'sha256': pin}}))
    result = census.assurance([], [str(bad), str(path)])
    assert result['lineage_inputs'][0] == {'input': str(bad), 'status': 'REFUSED', 'codes': ['LINEAGE_RECEIPT_PIN_MALFORMED']}
    assert result['lineage_inputs'][1]['status'] == 'READ', 'a valid lineage beside it is still read'
    assert result['status'] == 'UNPROVED' and result['receipts'] == []
