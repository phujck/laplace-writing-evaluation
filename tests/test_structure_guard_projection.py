"""projection:guard — the bounded reader-plan edit guard of one section, from the detail owner."""
import json
import pytest

from laplace.manuscript import project_structure
from laplace.web import project_work_surface
from laplace.native import tools as writing_tools
from laplace.writing import reads
from laplace.manuscript import reader_plan
from test_manuscript_structure import _section_fixture


def guard(root, sid='first', **scope):
    return writing_tools.execute(root, 'book', 'work', 'structure', {'view': 'detail', 'section_ids': [sid], 'projection': 'guard', **scope})


def size(value):
    return len(json.dumps(value, ensure_ascii=False).encode())


def test_guard_carries_exact_edit_guards_from_the_detail_owner_and_stays_bounded(tmp_path):
    _section_fixture(tmp_path)
    detail = project_structure.read('book', {'view': 'detail', 'section_ids': ['first']}, tmp_path)
    value = guard(tmp_path)
    assert value['schema_version'] == reader_plan.GUARD_SCHEMA and value['section_id'] == 'first'
    transition = detail['sections'][0]['reader_transition']
    # the same tokens the plain detail read published: nothing minted, no second store
    assert value['reader_transition']['edit_action']['payload'] == transition['edit_action']['payload']
    assert value['reader_transition']['edit_action']['payload']['expected_reader_basis'] == transition['reader_basis']
    assert value['reader_transition']['reader_basis'] == 'edit_action.payload.expected_reader_basis', 'one copy of each basis'
    assert value['authority'] == detail['authority']
    assert value['structure_observation'] == {k: v for k, v in detail['structure_observation'].items() if k != 'reader_subjects'}
    assert value['subject'] == 'contract' and 'create_action' not in value['paragraph_plan']
    assert value['subject_reads']['create']['subject'] == 'create' and value['subject_reads']['reorder']['subject'] == 'reorder'
    create = guard(tmp_path, subject='create')
    assert create['create_action']['payload'] == detail['sections'][0]['paragraph_plan']['create_action']['payload'] and 'reader_transition' not in create
    reorder = guard(tmp_path, subject='reorder')
    assert reorder['reorder_action']['payload'] == detail['sections'][0]['paragraph_plan']['reorder_action']['payload'] and 'paragraph' not in reorder
    assert {'expected_plan_revision', 'expected_contract_revision', 'expected_reader_basis'} <= set(value['reader_transition']['edit_action']['payload'])
    # the selected manuscript/file/heading binding travels whole
    assert value['section']['source'] == detail['sections'][0]['source']
    # the descriptors, members, support and history are named as omitted, with the plain detail handle
    assert 'fields' not in value['reader_transition']['edit_action'] and 'members' not in value['section']
    assert value['full_read']['payload'] == {'view': 'detail', 'section_ids': ['first']}
    assert size(value) < 12000 < size(detail)
    # HTTP serves the same projection through the same owner
    code, _, raw = project_work_surface.handle('/work/structure', {'project': ['book'], 'view': ['detail'], 'section_ids': ['["first"]'], 'projection': ['guard']}, 'GET', b'', repo_root=tmp_path)
    assert code == 200 and json.loads(raw) == value


def test_guard_edit_commits_and_a_stale_guard_still_refuses(tmp_path):
    _section_fixture(tmp_path)
    action = guard(tmp_path)['reader_transition']['edit_action']
    saved = writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**action['payload'], 'changes': {'entry_state': 'Knows the question'}})
    assert saved['plan_publication']['status'] == 'COMMITTED'
    after = guard(tmp_path)
    assert after['reader_transition']['fields']['entry_state'] == 'Knows the question'
    assert after['reader_transition']['input_currentness']['status'] == 'CURRENT'
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**action['payload'], 'changes': {'entry_state': 'Lost update'}})
    # the guard read's consulted substance is the authored content, not the tokens it carries
    before_digest = reads.read_output_digest('structure', after)
    assert before_digest == reads.read_output_digest('structure', guard(tmp_path))


def test_guard_pages_paragraph_rows_and_each_subject_read_carries_one_exact_call(tmp_path):
    _section_fixture(tmp_path)
    for text in ('One', 'Two', 'Three'):
        create = guard(tmp_path, subject='create')['create_action']
        writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**create['payload'], 'changes': {'proposition': text}})
    page = guard(tmp_path, paragraph_limit=2)['paragraph_plan']['paragraphs']
    assert page['total'] == 3 and len(page['items']) == 2 and page['next_read']['payload']['projection'] == 'guard' and page['next_read']['payload']['subject'] == 'contract'
    assert page['items'][0]['proposition'] == 'One' and 'edit_action' not in page['items'][0], 'rows are identity rows; the call is on the subject read'
    one = guard(tmp_path, subject='paragraph', paragraph_id=page['items'][0]['paragraph_id'])
    assert one['subject'] == 'paragraph' and one['paragraph']['proposition'] == 'One'
    assert {'expected_narrative_revision', 'expected_reader_basis', 'paragraph_id'} <= set(one['paragraph']['edit_action']['payload']) and one['paragraph']['remove_action']['payload']['action'] == 'remove'
    assert 'reader_transition' not in one and 'create_action' not in one
    detail = project_structure.read('book', {'view': 'detail', 'section_ids': ['first'], 'paragraph_id': one['paragraph']['paragraph_id']}, tmp_path)
    assert one['paragraph']['edit_action']['payload'] == detail['sections'][0]['paragraph_plan']['paragraphs']['items'][0]['edit_action']['payload']
    rest = guard(tmp_path, **{k: v for k, v in page['next_read']['payload'].items() if k not in {'view', 'section_ids', 'projection'}})
    assert [row['proposition'] for row in rest['paragraph_plan']['paragraphs']['items']] == ['Three']
    writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', guard(tmp_path, subject='paragraph', paragraph_id=page['items'][1]['paragraph_id'])['paragraph']['remove_action']['payload'])
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        guard(tmp_path, **{k: v for k, v in page['next_read']['payload'].items() if k not in {'view', 'section_ids', 'projection'}})
    with pytest.raises(ValueError, match='absent'):
        guard(tmp_path, subject='paragraph', paragraph_id=page['items'][1]['paragraph_id'])


def test_every_useful_guard_read_stays_under_the_native_ceiling_on_a_wide_populated_chapter(tmp_path):
    """Sol N1 reproducer: 17 short members, four populated paragraphs, measured at every stage."""
    from laplace.research import corpus_ingest
    manuscript, _, plan = _section_fixture(tmp_path)
    plan['sections'][0]['nodes_in_order'] = ['concept:wide-member-%02d' % i for i in range(17)]
    (manuscript / 'projection_plan.json').write_text(json.dumps(plan))
    for ident in plan['sections'][0]['nodes_in_order']:
        corpus_ingest.rewire_add(tmp_path, 'book', {'kind': 'add-node', 'node': ident, 'node_kind': 'definition', 'essence': 'Independent bounded fixture ' + ident, 'by': 'fixture'})
    measured = {}
    for count in range(5):
        contract = guard(tmp_path); page = guard(tmp_path, paragraph_limit=4); create = guard(tmp_path, subject='create'); reorder = guard(tmp_path, subject='reorder')
        rows = page['paragraph_plan']['paragraphs']['items']
        units = [guard(tmp_path, subject='paragraph', paragraph_id=row['paragraph_id']) for row in rows]
        measured[count] = {'contract': size(contract), 'page4': size(page), 'create': size(create), 'reorder': size(reorder), 'paragraph_max': max([size(u) for u in units] or [0]), 'rows': len(rows)}
        assert len(rows) == count
        for label, bytes_ in measured[count].items():
            if label != 'rows':
                assert bytes_ < 12000, (count, label, bytes_)
        assert all(u['paragraph']['edit_action']['payload']['expected_reader_basis']['inputs'] for u in units), 'the exact basis travels whole'
        if count < 4:
            writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**create['create_action']['payload'], 'changes': {'proposition': 'A useful short paragraph %d.' % count}})
    assert measured[4]['rows'] == 4


def test_guard_needs_exactly_one_section_and_a_known_projection(tmp_path):
    _section_fixture(tmp_path)
    with pytest.raises(ValueError, match='exactly one'):
        guard(tmp_path, section_ids=['first', 'second'])
    with pytest.raises(ValueError):
        writing_tools.execute(tmp_path, 'book', 'work', 'structure', {'view': 'detail', 'section_ids': ['first'], 'projection': 'everything'})
    with pytest.raises(ValueError, match='needs paragraph_id'):
        guard(tmp_path, subject='paragraph')
    with pytest.raises(ValueError, match='projection:guard'):
        writing_tools.execute(tmp_path, 'book', 'work', 'structure', {'view': 'detail', 'section_ids': ['first'], 'subject': 'create'})


def test_default_contract_guard_stays_bounded_as_authoring_grows_and_create_reorder_hydrate_no_rows(tmp_path, monkeypatch):
    """Sol N1-default: the owner default page is 20 rows (12.6-13.3 KB at 16-20 rows on the 17-member
    chapter); the contract subject reads GUARD_PAGE_ROWS by default and continues exactly, and
    create/reorder enrich no paragraph row at all (measured at the owner, not inferred from output)."""
    from laplace.research import corpus_ingest
    manuscript, _, plan = _section_fixture(tmp_path)
    plan['sections'][0]['nodes_in_order'] = ['concept:wide-member-%02d' % i for i in range(17)]
    (manuscript / 'projection_plan.json').write_text(json.dumps(plan))
    for ident in plan['sections'][0]['nodes_in_order']:
        corpus_ingest.rewire_add(tmp_path, 'book', {'kind': 'add-node', 'node': ident, 'node_kind': 'definition', 'essence': 'Independent bounded fixture ' + ident, 'by': 'fixture'})
    hydrated = []
    original = reader_plan.source_occurrences
    monkeypatch.setattr(reader_plan, 'source_occurrences', lambda project, root, ids, **kw: hydrated.append(set(ids)) or original(project, root, ids, **kw))
    def rows_hydrated(**scope):
        del hydrated[:]
        value = guard(tmp_path, **scope)
        return value, sum(len(ids) for ids in hydrated)
    for count in range(21):
        if count in (0, 4, 8, 12, 16, 20):
            default, default_rows = rows_hydrated()
            page = default['paragraph_plan']['paragraphs']
            assert size(default) < 12000 and page['limit'] == reader_plan.GUARD_PAGE_ROWS and len(page['items']) == min(count, 4) == default_rows, (count, size(default))
            if count > 4:
                assert page['next_read']['payload']['subject'] == 'contract' and page['next_read']['payload']['paragraph_as_of'] and page['next_read']['payload']['paragraph_limit'] == 4
            create, create_rows = rows_hydrated(subject='create'); reorder, reorder_rows = rows_hydrated(subject='reorder')
            assert create_rows == 0 and reorder_rows == 0, 'create/reorder enrich no paragraph row'
            assert size(create) < 12000 and size(reorder) < 12000
            assert len(reorder['reorder_action']['payload']['order']) == count == len(reorder['reorder_action']['order_choices']), 'the complete order still travels'
            explicit, explicit_rows = rows_hydrated(paragraph_limit=2)
            assert len(explicit['paragraph_plan']['paragraphs']['items']) == min(count, 2) == explicit_rows, 'an explicit page is honoured'
        if count < 20:
            action = guard(tmp_path, subject='create')['create_action']
            writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**action['payload'], 'changes': {'proposition': 'A useful short paragraph %02d.' % count}})
    # the default page continues exactly through the whole plan under the same cut
    seen = []; value = guard(tmp_path)
    while True:
        seen += [row['paragraph_id'] for row in value['paragraph_plan']['paragraphs']['items']]
        handle = value['paragraph_plan']['paragraphs']['next_read']
        if not handle: break
        value = guard(tmp_path, **{k: v for k, v in handle['payload'].items() if k not in {'view', 'section_ids', 'projection'}})
    assert len(seen) == 20 == len(set(seen))
    # the create call equals the plain detail owner's, so no parallel token store exists
    detail = project_structure.read('book', {'view': 'detail', 'section_ids': ['first'], 'paragraph_limit': 1}, tmp_path)
    assert guard(tmp_path, subject='create')['create_action']['payload'] == detail['sections'][0]['paragraph_plan']['create_action']['payload']
    assert guard(tmp_path, subject='reorder')['reorder_action']['payload'] == detail['sections'][0]['paragraph_plan']['reorder_action']['payload']


def test_guard_admits_exactly_one_canonical_section_ids_entry_natively_over_http_and_in_the_declared_schema(tmp_path, monkeypatch):
    """Sol guard-selector-policy: the bounded subject policy is defined on the canonical section, so
    a guard selected by node_ids, node_id, files, the sections alias, two ids or a mixed scope is
    refused before any resolution or hydration, with the plain detail read as the route that
    resolves those selectors; ordinary unprojected detail keeps every selector."""
    from jsonschema import Draft202012Validator
    from laplace.research import corpus_ingest
    from laplace.native.declarations import PayloadAdmissionError
    manuscript, _, plan = _section_fixture(tmp_path)
    plan['sections'][0]['nodes_in_order'] = ['concept:wide-member-%02d' % i for i in range(17)]
    (manuscript / 'projection_plan.json').write_text(json.dumps(plan))
    for ident in plan['sections'][0]['nodes_in_order']:
        corpus_ingest.rewire_add(tmp_path, 'book', {'kind': 'add-node', 'node': ident, 'node_kind': 'definition', 'essence': 'Independent bounded fixture ' + ident, 'by': 'fixture'})
    for text in ('One', 'Two', 'Three', 'Four', 'Five'):
        create = guard(tmp_path, subject='create')['create_action']
        writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**create['payload'], 'changes': {'proposition': text}})
    pid = guard(tmp_path)['paragraph_plan']['paragraphs']['items'][0]['paragraph_id']
    hydrated = []
    original = reader_plan.source_occurrences
    monkeypatch.setattr(reader_plan, 'source_occurrences', lambda project, root, ids, **kw: hydrated.append(set(ids)) or original(project, root, ids, **kw))
    alternatives = {'node_ids': {'node_ids': ['concept:wide-member-00']}, 'node_id': {'node_id': 'concept:wide-member-00'},
                    'files': {'files': ['chapters/chapter-01.tex']}, 'two_sections': {'section_ids': ['first', 'second']},
                    'mixed': {'section_ids': ['first'], 'node_ids': ['concept:wide-member-00']}, 'alias': {'sections': ['first']}, 'none': {}}
    subjects = [{}, {'subject': 'contract'}, {'subject': 'create'}, {'subject': 'reorder'}, {'subject': 'paragraph', 'paragraph_id': pid}]
    for name, selector in alternatives.items():
        for subject in subjects:
            payload = {'view': 'detail', **selector, 'projection': 'guard', **subject}
            with pytest.raises(PayloadAdmissionError, match='exactly one canonical section_ids entry') as refused:
                writing_tools.execute(tmp_path, 'book', 'work', 'structure', payload)
            assert 'plain detail read' in str(refused.value) and 'section_ids:[that id]' in str(refused.value), 'the refusal carries the read route'
            with pytest.raises(ValueError, match='exactly one canonical section_ids entry'):
                project_structure.read('book', payload, tmp_path)   # the owner itself refuses too, before resolution
            # the declared native contract says the same (the schema, not only the runtime)
            assert next(Draft202012Validator(project_structure.read_contract()).iter_errors(payload), None) is not None, (name, subject)
            assert next(Draft202012Validator(project_structure.http_read_contract()).iter_errors({'project': 'book', **payload}), None) is not None, (name, subject)
        query = {'project': ['book'], 'view': ['detail'], 'projection': ['guard'], **{key: [json.dumps(value) if isinstance(value, list) else value] for key, value in selector.items()}}
        code, _, raw = project_work_surface.handle('/work/structure', query, 'GET', b'', repo_root=tmp_path)
        assert code == 422 and 'exactly one canonical section_ids entry' in json.loads(raw)['error'], name
    assert hydrated == [], 'no refused guard read hydrated a paragraph row or resolved a selector'
    # the route the refusal names: ordinary unprojected detail resolves node and file selectors to canonical ids ...
    by_node = project_structure.read('book', {'view': 'detail', 'node_ids': ['concept:wide-member-00']}, tmp_path)
    by_file = project_structure.read('book', {'view': 'detail', 'files': ['chapters/chapter-01.tex']}, tmp_path)
    assert [row['id'] for row in by_node['sections']] == ['first'] and 'first' in [row['id'] for row in by_file['sections']]
    assert next(Draft202012Validator(project_structure.read_contract()).iter_errors({'view': 'detail', 'node_ids': ['concept:wide-member-00']}), None) is None, 'unprojected node selection stays declared'
    assert next(Draft202012Validator(project_structure.read_contract()).iter_errors({'view': 'detail', 'files': ['chapters/chapter-01.tex'], 'line_start': 1, 'line_end': 3}), None) is None
    # ... and the canonical guard then applies the bounded policy unchanged
    del hydrated[:]
    canonical = guard(tmp_path, sid=by_node['sections'][0]['id'])
    assert canonical['section_id'] == 'first' and len(canonical['paragraph_plan']['paragraphs']['items']) == 4 == sum(len(ids) for ids in hydrated)
    del hydrated[:]
    create = guard(tmp_path, subject='create'); reorder = guard(tmp_path, subject='reorder')
    assert hydrated == [set()] * 2 or sum(len(ids) for ids in hydrated) == 0
    detail = project_structure.read('book', {'view': 'detail', 'section_ids': ['first'], 'paragraph_limit': 1}, tmp_path)
    assert create['create_action']['payload'] == detail['sections'][0]['paragraph_plan']['create_action']['payload']
    assert reorder['reorder_action']['payload'] == detail['sections'][0]['paragraph_plan']['reorder_action']['payload']
    assert next(Draft202012Validator(project_structure.read_contract()).iter_errors({'view': 'detail', 'section_ids': ['first'], 'projection': 'guard', 'subject': 'paragraph', 'paragraph_id': pid}), None) is None
    with pytest.raises(ValueError, match='not a current section'):
        guard(tmp_path, sid='no-such-section')


def test_guard_refuses_the_presence_of_an_alternative_selector_key_even_when_empty_or_null(tmp_path, monkeypatch):
    """Sol guard-selector-policy-empty-presence: the policy is on key presence, as the declared
    schema and the human parser already enforce; files:[], node_ids:[], node_id:"", sections:[] and
    explicit nulls beside a canonical section_ids refuse at every door with the same read route,
    before any resolution or hydration; no door injects an absent key, so canonical requests pass."""
    from jsonschema import Draft202012Validator
    from laplace.native.declarations import PayloadAdmissionError
    _section_fixture(tmp_path)
    create = guard(tmp_path, subject='create')['create_action']
    writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**create['payload'], 'changes': {'proposition': 'One'}})
    pid = guard(tmp_path)['paragraph_plan']['paragraphs']['items'][0]['paragraph_id']
    hydrated = []
    original = reader_plan.source_occurrences
    monkeypatch.setattr(reader_plan, 'source_occurrences', lambda project, root, ids, **kw: hydrated.append(set(ids)) or original(project, root, ids, **kw))
    empties = [('files', []), ('node_ids', []), ('node_id', ''), ('sections', []), ('files', None), ('node_ids', None), ('node_id', None), ('sections', None)]
    subjects = [{}, {'subject': 'contract'}, {'subject': 'create'}, {'subject': 'reorder'}, {'subject': 'paragraph', 'paragraph_id': pid}]
    for key, value in empties:
        for subject in subjects:
            payload = {'view': 'detail', 'section_ids': ['first'], 'projection': 'guard', key: value, **subject}
            with pytest.raises(PayloadAdmissionError, match='exactly one canonical section_ids entry') as refused:
                writing_tools.execute(tmp_path, 'book', 'work', 'structure', payload)
            assert 'plain detail read' in str(refused.value) and ('present: ' + key) in str(refused.value), (key, value, subject)
            with pytest.raises(ValueError, match='exactly one canonical section_ids entry'):
                project_structure.read('book', payload, tmp_path)
            assert not Draft202012Validator(project_structure.read_contract()).is_valid(payload), (key, value, subject)
            assert not Draft202012Validator(project_structure.http_read_contract()).is_valid({'project': 'book', **payload})
        if value is not None:   # an HTTP query cannot carry null; it carries [] or ""
            query = {'project': ['book'], 'view': ['detail'], 'section_ids': ['["first"]'], 'projection': ['guard'], key: [json.dumps(value) if isinstance(value, list) else value]}
            code, _, raw = project_work_surface.handle('/work/structure', query, 'GET', b'', repo_root=tmp_path)
            assert code == 422 and 'exactly one canonical section_ids entry' in json.loads(raw)['error'] and ('present: ' + key) in json.loads(raw)['error'], key
    assert hydrated == [], 'no refused guard read hydrated or resolved anything'
    # canonical requests are not mistaken for mixed ones: no door injects an absent selector key
    for subject in subjects:
        value = writing_tools.execute(tmp_path, 'book', 'work', 'structure', {'view': 'detail', 'section_ids': ['first'], 'projection': 'guard', **subject})
        assert value['section_id'] == 'first' and value['subject'] == (subject.get('subject') or 'contract')
        query = {'project': ['book'], 'view': ['detail'], 'section_ids': ['["first"]'], 'projection': ['guard'], **{k: [v] for k, v in subject.items()}}
        code, _, raw = project_work_surface.handle('/work/structure', query, 'GET', b'', repo_root=tmp_path)
        assert code == 200 and json.loads(raw)['subject'] == value['subject'], subject
    assert guard(tmp_path)['paragraph_plan']['paragraphs']['limit'] == reader_plan.GUARD_PAGE_ROWS
    # ordinary unprojected detail keeps every selector, empty or not
    assert [row['id'] for row in project_structure.read('book', {'view': 'detail', 'section_ids': ['first'], 'files': []}, tmp_path)['sections']] == ['first']
    assert Draft202012Validator(project_structure.read_contract()).is_valid({'view': 'detail', 'section_ids': ['first'], 'node_ids': []})


def test_paragraph_writes_through_the_action_owner_carry_exact_attribution_with_their_captured_narrative_preimage(tmp_path):
    """C7-C9 repair H5: a native section_contract / paragraph create, edit and reorder, each on a
    fresh guard, reports mutation_attribution.exact because the pre-write snapshot captured the
    selected section's own narrative file (and the contracts file) by the owner's path rule; a
    stale guard still refuses; no other narrative file is captured."""
    from laplace.writing import records as writing_records
    from laplace.writing import mutation_attribution
    from laplace.manuscript import reader_plan
    _section_fixture(tmp_path)
    writing_records.bank(tmp_path, {'record': 'writing-session', 'id': 'WS-h5', 'project': 'book', 'provider': 'codex', 'model': 'fixture', 'effort': 'low'})
    writing_records.bank(tmp_path, {'record': 'writing-turn', 'id': 'WT-h5', 'session_id': 'WS-h5', 'project': 'book', 'mode': 'work'})
    def write(payload):
        return writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', payload, turn_id='WT-h5')
    contracts_path, narrative_path = (path.relative_to(tmp_path).as_posix() for path in reader_plan._paths('book', tmp_path, 'first'))
    other_narrative = reader_plan._paths('book', tmp_path, 'second')[1].relative_to(tmp_path).as_posix()
    # section contract (contracts file)
    contract = guard(tmp_path)['reader_transition']['edit_action']
    saved = write({**contract['payload'], 'changes': {'entry_state': 'Knows the question'}})
    assert saved['action_receipt']['mutation_attribution']['exact'] is True, saved['action_receipt']['mutation_attribution']
    # paragraph create (the narrative file may be absent before the first unit: explicit null before)
    created = write({**guard(tmp_path, subject='create')['create_action']['payload'], 'changes': {'proposition': 'One'}})
    assert created['action_receipt']['mutation_attribution']['exact'] is True, created['action_receipt']['mutation_attribution']
    files = {row['path']: row for row in created['action_receipt']['owner_evidence']['files']}
    assert narrative_path in files and other_narrative not in files
    # paragraph edit and reorder: the narrative preimage now exists and must be captured exactly
    pid = guard(tmp_path)['paragraph_plan']['paragraphs']['items'][0]['paragraph_id']
    edit = guard(tmp_path, subject='paragraph', paragraph_id=pid)['paragraph']['edit_action']
    edited = write({**edit['payload'], 'changes': {'proposition': 'One, clarified'}})
    assert edited['action_receipt']['mutation_attribution']['exact'] is True, edited['action_receipt']['mutation_attribution']
    row = next(row for row in edited['action_receipt']['owner_evidence']['files'] if row['path'] == narrative_path)
    assert row['before_sha256'] and row['after_sha256'] == row['observed_after_sha256'] and row['before_sha256'] != row['after_sha256']
    write({**guard(tmp_path, subject='create')['create_action']['payload'], 'changes': {'proposition': 'Two'}})
    reorder = guard(tmp_path, subject='reorder')['reorder_action']
    order = list(reversed(reorder['payload']['order']))
    reordered = write({**reorder['payload'], 'order': order})
    assert reordered['action_receipt']['mutation_attribution']['exact'] is True, reordered['action_receipt']['mutation_attribution']
    assert [r['paragraph_id'] for r in guard(tmp_path, paragraph_limit=4)['paragraph_plan']['paragraphs']['items']] == order
    # the stale guard is still refused: the captured preimage weakens no guard
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        write({**edit['payload'], 'changes': {'proposition': 'Lost update'}})
    # the capture is the two owner files of the selected section, not a narrative scan
    snapshot = mutation_attribution._mutation_file_snapshot(tmp_path, 'book', 'structure_change', {'operation': 'paragraph_plan', 'section_id': 'first'})
    assert narrative_path in snapshot and contracts_path in snapshot and other_narrative not in snapshot
    assert 'section_id' not in mutation_attribution._mutation_file_snapshot(tmp_path, 'book', 'structure_change', {'operation': 'paragraph_plan', 'section_id': '../escape'})
