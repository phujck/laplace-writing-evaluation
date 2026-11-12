"""projection:display and view:plan (ACTUAL-C6-DETAIL-BYTES, 2026-10-14): the bounded human page of one
reader-plan section and the plan guard the plan-level editors read instead of the full structure."""
import json
import pytest

from laplace.manuscript import project_structure
from laplace.web import project_work_surface
from laplace.native import tools as writing_tools
from laplace.manuscript import reader_plan
from test_manuscript_structure import _section_fixture


def size(value):
    return len(json.dumps(value, ensure_ascii=False).encode())


def read(root, **scope):
    return writing_tools.execute(root, 'book', 'work', 'structure', scope)


def wide(root, paragraphs=20, members=17, text=('the reader is shown the mechanism in plain words and the consequence it has for the claim; ' * 3)):
    """A wide section: `members` short argument members and `paragraphs` populated rows (the live hold's shape)."""
    manuscript, _, plan = _section_fixture(root)
    plan['sections'][0]['nodes_in_order'] = ['concept:wide-member-%02d' % i for i in range(members)]
    (manuscript / 'projection_plan.json').write_text(json.dumps(plan))
    from laplace.research import corpus_ingest
    for ident in plan['sections'][0]['nodes_in_order']:
        corpus_ingest.rewire_add(root, 'book', {'kind': 'add-node', 'node': ident, 'node_kind': 'definition', 'essence': 'Independent bounded fixture ' + ident, 'by': 'fixture'})
    for index in range(paragraphs):
        create = read(root, view='detail', section_ids=['first'], projection='guard', subject='create')['create_action']
        writing_tools.execute(root, 'book', 'work', 'structure_change', {**create['payload'], 'changes': {
            'proposition': 'Proposition %d: %s' % (index, text), 'function': 'Function %d' % index, 'explanation': 'Explanation %d: %s' % (index, text),
            'qualification': 'Qualification %d: %s' % (index, text), 'from_previous': 'From %d: %s' % (index, text), 'to_next': 'To %d: %s' % (index, text)}})


def test_display_is_a_bounded_page_of_the_same_owner_with_lazy_exact_calls(tmp_path):
    wide(tmp_path)
    detail = read(tmp_path, view='detail', section_ids=['first'])
    display = read(tmp_path, view='detail', section_ids=['first'], projection='display')
    assert display['schema_version'] == reader_plan.DISPLAY_SCHEMA and display['projection'] == 'display'
    assert size(detail) > 300_000 and size(display) <= 12_000, (size(detail), size(display))
    section = display['sections'][0]
    rows = section['paragraph_plan']['paragraphs']['items']
    assert len(rows) == reader_plan.DISPLAY_PAGE_ROWS and section['paragraph_plan']['paragraphs']['total'] == 20
    # list rows: the proposition (clipped, named as clipped), the authored fields beyond it, the standing and the doors; no call, no basis
    row = rows[0]
    assert row['clipped'] == ['proposition'] and row['proposition'].endswith('…') and set(row['authored']) == {'explanation', 'qualification', 'from_previous', 'to_next'}
    assert 'edit_action' not in row and 'reader_basis' not in row and 'links' not in row and 'diagnostics' not in row
    assert set(row['doors']) == {'edit', 'remove', 'review', 'split', 'merge'} and row['identity_status'] == 'STABLE'
    assert 'read_handle' not in row and section['paragraph_plan']['paragraphs']['row_read']['payload'] == {'view': 'detail', 'section_ids': ['first'], 'projection': 'display', 'paragraph_id': '<paragraph_id>'}
    # the section's calls are doors too; the member page is display rows with the owner's cut
    assert set(section['doors']) == {'link_source', 'prepare_work'} and 'clearing_action' not in section
    assert len(section['nodes']) == reader_plan.DISPLAY_MEMBER_ROWS and section['members']['total'] == 17 and section['members']['next_read']['payload']['projection'] == 'display'
    assert section['reader_transition']['doors'] == {'edit': True, 'review': True} and 'edit_action' not in section['reader_transition']
    assert section['paragraph_plan']['doors'] == {'create': True, 'reorder': True}
    # the exact continuation is the owner's paragraph cut under the display projection
    nxt = section['paragraph_plan']['paragraphs']['next_read']['payload']
    assert nxt['paragraph_offset'] == 6 and nxt['paragraph_as_of'] == section['paragraph_plan']['revision'] and nxt['projection'] == 'display'
    page2 = read(tmp_path, **nxt)
    assert [r['paragraph_id'] for r in page2['sections'][0]['paragraph_plan']['paragraphs']['items']] == [r['paragraph_id'] for r in detail['sections'][0]['paragraph_plan']['paragraphs']['items'][6:12]]
    assert size(page2) <= 12_000
    # one paragraph named: the whole row, unclipped, with its inputs and its subject read; still bounded
    whole = read(tmp_path, view='detail', section_ids=['first'], paragraph_id=row['paragraph_id'], projection='display')
    one = whole['sections'][0]['paragraph_plan']['paragraphs']['items'][0]
    assert one['paragraph_id'] == row['paragraph_id'] and 'clipped' not in one and one['explanation'].startswith('Explanation 0')
    assert one['links_total'] == 17 and len(one['links']) == reader_plan.DISPLAY_INPUT_ROWS and one['subject_read']['payload']['subject'] == 'paragraph'
    assert size(whole) < 20_000
    # HTTP serves the same projection through the same owner
    code, _, raw = project_work_surface.handle('/work/structure', {'project': ['book'], 'view': ['detail'], 'section_ids': ['["first"]'], 'projection': ['display']}, 'GET', b'', repo_root=tmp_path)
    assert code == 200 and json.loads(raw) == read(tmp_path, view='detail', section_ids=['first'], projection='display')
    # the displayed scope's observation: the page's reader subjects as ONE compact ref that refuses a
    # send exactly when the whole bases would (a changed subject, a changed input)
    from laplace.manuscript import bindings
    observation = display['structure_observation']
    ref = observation['reader_subjects'][0]
    assert len(observation['reader_subjects']) == 1 and ref['schema_version'] == reader_plan.SUBJECTS_REF_SCHEMA
    assert ref['subject_ids'] == ['first', *[r['paragraph_id'] for r in rows]] and size(observation) < 1_200
    assert bindings.validate_observation('book', tmp_path, observation) == observation
    whole_observation = detail['structure_observation']
    assert bindings.validate_observation('book', tmp_path, whole_observation) == whole_observation
    contract = read(tmp_path, view='detail', section_ids=['first'], projection='guard')['reader_transition']['edit_action']
    writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**contract['payload'], 'changes': {'entry_state': 'Changed after display'}})
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        bindings.validate_observation('book', tmp_path, observation)
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        bindings.validate_observation('book', tmp_path, whole_observation)
    fresh = read(tmp_path, view='detail', section_ids=['first'], projection='display')['structure_observation']
    assert bindings.validate_observation('book', tmp_path, fresh) == fresh and fresh['reader_subjects'][0]['digest'] != ref['digest']
    with pytest.raises(ValueError, match='malformed|another project'):
        bindings.validate_observation('book', tmp_path, {**fresh, 'reader_subjects': [{**fresh['reader_subjects'][0], 'project': 'other'}]})
    # the plan guard and the full read are named; nothing minted
    assert display['plan_read']['payload'] == {'view': 'plan'} and display['full_guard_read']['payload'] == {'view': 'plan'} and display['full_read']['payload'] == {'view': 'detail', 'section_ids': ['first']}
    assert display['authority'] == detail['authority']
    # the display's revision is the scoped detail owner's own digest of the page it projects
    assert isinstance(display['revision'], str) and display['revision'].startswith('sha256:')
    with pytest.raises(ValueError, match='too long|exactly one'):
        read(tmp_path, view='detail', section_ids=['first', 'second'], projection='display')
    with pytest.raises(ValueError, match='exactly one'):
        project_structure.read('book', {'view': 'detail', 'section_ids': ['first', 'second'], 'projection': 'display'}, tmp_path)
    with pytest.raises(ValueError, match='no subject'):
        read(tmp_path, view='detail', section_ids=['first'], projection='display', subject='contract')


def test_section_and_structure_subjects_carry_the_display_doors_calls_and_choices_open_one_editor_read(tmp_path):
    wide(tmp_path, paragraphs=4)
    detail = read(tmp_path, view='detail', section_ids=['first'])['sections'][0]
    section = read(tmp_path, view='detail', section_ids=['first'], projection='guard', subject='section')
    assert section['subject'] == 'section' and section['section_calls']['clearing_action'] == detail['clearing_action']
    assert section['section_calls']['prepare_action'] == detail['prepare_action']
    assert section['section_calls']['review_action']['payload'] == detail['reader_transition']['review_action']['payload']
    assert 'reader_transition' not in section and size(section) < 12_000
    row = detail['paragraph_plan']['paragraphs']['items'][0]
    structure = read(tmp_path, view='detail', section_ids=['first'], projection='guard', subject='structure', paragraph_id=row['paragraph_id'])
    assert structure['paragraph']['review_action']['payload'] == row['review_action']['payload']
    assert structure['paragraph']['restructure_actions']['split']['payload'] == row['restructure_actions']['split']['payload']
    assert 'edit_action' not in structure['paragraph'] and size(structure) < 12_000
    with pytest.raises(ValueError, match='needs paragraph_id'):
        read(tmp_path, view='detail', section_ids=['first'], projection='guard', subject='structure')
    # the accepted four subjects are unchanged by default (no descriptors); edit_choices adds them once
    contract = read(tmp_path, view='detail', section_ids=['first'], projection='guard')
    assert 'fields' not in contract['reader_transition']['edit_action'] and 'review_action' not in contract['reader_transition']
    assert contract['reader_transition']['choices_read']['payload'] == {'view': 'detail', 'section_ids': ['first'], 'subject': 'contract', 'edit_choices': True, 'projection': 'guard'}
    with_choices = read(tmp_path, **contract['reader_transition']['choices_read']['payload'])
    assert with_choices['reader_transition']['edit_action']['fields'] == detail['reader_transition']['edit_action']['fields']
    assert with_choices['reader_transition']['edit_action']['payload'] == contract['reader_transition']['edit_action']['payload'], 'the same guard, with its descriptors'
    paragraph = read(tmp_path, view='detail', section_ids=['first'], projection='guard', subject='paragraph', paragraph_id=row['paragraph_id'], edit_choices=True)
    assert paragraph['paragraph']['edit_action']['fields'] == row['edit_action']['fields'] and 'fields' not in paragraph['paragraph']['remove_action']
    create = read(tmp_path, view='detail', section_ids=['first'], projection='guard', subject='create', edit_choices=True)
    assert create['create_action']['fields'] == detail['paragraph_plan']['create_action']['fields']
    # an edit sent with the guard acquired this way commits, and a stale one refuses
    saved = writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**with_choices['reader_transition']['edit_action']['payload'], 'changes': {'entry_state': 'Knows the question'}})
    assert saved['plan_publication']['status'] == 'COMMITTED'
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**with_choices['reader_transition']['edit_action']['payload'], 'changes': {'entry_state': 'Lost update'}})


def test_plan_guard_is_the_full_reads_token_without_the_hydrated_structure(tmp_path):
    wide(tmp_path, paragraphs=2)
    full = read(tmp_path, view='full')
    plan = read(tmp_path, view='plan')
    assert plan['schema_version'] == reader_plan.PLAN_SCHEMA and plan['revision'] == full['revision'] and plan['authority'] == full['authority']
    assert plan['plan_collections'] == full['plan_collections'] and [row['id'] for row in plan['sections']] == [row['id'] for row in full['sections']]
    assert plan['sections'][0]['nodes'] == [{'id': node['id'], 'missing': bool(node.get('missing'))} for node in full['sections'][0]['nodes']]
    assert [beat['id'] for beat in plan['spine']] == [beat['id'] for beat in full['spine']]
    assert all(key not in plan for key in ('nodes', 'edges', 'evidence', 'logical_objects', 'source_outline')) and size(plan) < size(full)
    # a plan mutation sent with the plan guard's revision commits; the full read's token is the same home
    result = writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {'operation': 'plan', 'expected_revision': plan['revision'],
                                                                                    'ops': [{'kind': 'retitle', 'section': 'first', 'title': 'First, retitled'}]})
    assert result['applied'] is True and read(tmp_path, view='plan')['sections'][0]['title'] == 'First, retitled'
    with pytest.raises(ValueError):
        writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {'operation': 'plan', 'expected_revision': plan['revision'],
                                                                             'ops': [{'kind': 'retitle', 'section': 'first', 'title': 'Stale'}]})
    code, _, raw = project_work_surface.handle('/work/structure', {'project': ['book'], 'view': ['plan']}, 'GET', b'', repo_root=tmp_path)
    assert code == 200 and json.loads(raw)['revision'] == read(tmp_path, view='full')['revision']
    with pytest.raises(ValueError, match='section_ids'):
        read(tmp_path, view='plan', section_ids=['first'])
    with pytest.raises(ValueError, match='no scope'):
        project_structure.read('book', {'view': 'plan', 'section_ids': ['first']}, tmp_path)


# ---- repair H1 (2026-10-14): serialized bytes, not characters; native and HTTP agree; one editor read ----
@pytest.mark.parametrize('label,text', [('ascii', 'x' * 300), ('cjk', '中' * 300), ('quoted', '"key": "value", ' * 25)])
def test_display_and_default_guard_stay_under_the_page_budget_in_serialized_utf8_over_native_and_http(tmp_path, label, text):
    """Sol's reproducer: 20 rows / 17 members with 300-unit fields of ASCII, CJK and quoted-JSON text. Row
    clips are serialized-byte caps (ensure_ascii=False, the form the HTTP surface now sends) so the display
    page and the default contract guard stay under 12,000 B whatever the script; the whole-row read is explicit
    and names its own scope."""
    wide(tmp_path, text=text)
    display = read(tmp_path, view='detail', section_ids=['first'], projection='display')
    code, _, raw = project_work_surface.handle('/work/structure', {'project': ['book'], 'view': ['detail'], 'section_ids': ['["first"]'], 'projection': ['display']}, 'GET', b'', repo_root=tmp_path)
    assert code == 200 and len(raw) == size(display) <= 12_000, (label, size(display), len(raw))
    assert json.loads(raw) == display and '\\u' not in raw.decode('utf-8')[:200] or label != 'cjk'
    rows = display['sections'][0]['paragraph_plan']['paragraphs']['items']
    assert len(rows) == reader_plan.DISPLAY_PAGE_ROWS and all(reader_plan._serialized_bytes(row['proposition']) <= reader_plan.DISPLAY_TEXT_CLIP for row in rows)
    assert all(row['clipped'] == ['proposition'] and row['proposition'].endswith('…') for row in rows), 'every long proposition is clipped and says so'
    page2 = read(tmp_path, **display['sections'][0]['paragraph_plan']['paragraphs']['next_read']['payload'])
    assert size(page2) <= 12_000
    guard = read(tmp_path, view='detail', section_ids=['first'], projection='guard')
    code, _, raw_guard = project_work_surface.handle('/work/structure', {'project': ['book'], 'view': ['detail'], 'section_ids': ['["first"]'], 'projection': ['guard']}, 'GET', b'', repo_root=tmp_path)
    assert len(raw_guard) == size(guard) <= 12_000, (label, size(guard), len(raw_guard))
    assert all(reader_plan._serialized_bytes(row['proposition']) <= reader_plan.GUARD_ROW_CLIP for row in guard['paragraph_plan']['paragraphs']['items'])
    whole = read(tmp_path, view='detail', section_ids=['first'], paragraph_id=rows[0]['paragraph_id'], projection='display')
    one = whole['sections'][0]['paragraph_plan']['paragraphs']['items'][0]
    assert one['proposition'] == 'Proposition 0: ' + text and 'clipped' not in one and whole['scope'].startswith('whole row'), 'the whole row is unclipped and names its scope'
    assert 'scope' not in display, 'the page read carries no scope sentence (its scope is the schema)'
    # the clip never splits a character or an escape sequence
    assert reader_plan._clip('中' * 100, 10) == '中' * 2 + '…' and reader_plan._clip('a"b"c"d', 6) == 'a"…' and reader_plan._clip('short', 150) == 'short'


# ---- repair2 R2 (2026-10-14): POPULATED contracts and paragraphs keep the display and every default subject
# read under 12,000 B (native == HTTP) for ASCII, CJK, quoted and control-character text; the editor read
# carries the exact complete values; nothing on a call or its guards is clipped
@pytest.mark.parametrize('label,text', [('ascii', 'x' * 300), ('cjk', '中' * 300), ('quoted', '"key": "value", ' * 25), ('control', 'a\u0001b\tc\\d' * 50)])
def test_populated_contract_and_paragraphs_keep_display_and_default_subjects_under_the_page_budget(tmp_path, label, text):
    from laplace.manuscript import reader_plan as rp
    wide(tmp_path, text=text)
    call = read(tmp_path, view='detail', section_ids=['first'], projection='guard')['reader_transition']['edit_action']
    saved = writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**call['payload'], 'changes': {key: text for key in rp.CONTRACT_STRINGS}})
    assert saved['plan_publication']['status'] == 'COMMITTED'
    detail = read(tmp_path, view='detail', section_ids=['first'])['sections'][0]
    q = {'project': ['book'], 'view': ['detail'], 'section_ids': ['["first"]']}
    def both(**extra):
        native = read(tmp_path, view='detail', section_ids=['first'], **extra)
        code, _, raw = project_work_surface.handle('/work/structure', {**q, **{k: [str(v).lower() if isinstance(v, bool) else str(v)] for k, v in extra.items()}}, 'GET', b'', repo_root=tmp_path)
        assert code == 200 and len(raw) == size(native), (label, extra, len(raw), size(native))
        return native
    display = both(projection='display')
    pid = display['sections'][0]['paragraph_plan']['paragraphs']['items'][0]['paragraph_id']
    contract = both(projection='guard')
    paragraph = both(projection='guard', subject='paragraph', paragraph_id=pid)
    for name, value in (('display', display), ('contract guard', contract), ('paragraph guard', paragraph),
                        ('create guard', both(projection='guard', subject='create')), ('reorder guard', both(projection='guard', subject='reorder')),
                        ('section guard', both(projection='guard', subject='section')), ('structure guard', both(projection='guard', subject='structure', paragraph_id=pid))):
        assert size(value) <= 12_000, (label, name, size(value))
    # display-only carriers are clipped and say so; the calls and guards are exact
    transition = display['sections'][0]['reader_transition']
    assert set(transition['clipped']) == set(rp.CONTRACT_STRINGS) and transition['values_read']['payload']['edit_choices'] is True
    assert set(contract['reader_transition']['clipped']) == set(rp.CONTRACT_STRINGS)
    assert all(rp._serialized_bytes(v) <= rp.GUARD_TEXT_CLIP for v in contract['reader_transition']['fields'].values() if isinstance(v, str))
    assert contract['reader_transition']['edit_action']['payload'] == detail['reader_transition']['edit_action']['payload'], 'the call and its guards are not clipped'
    row = next(r for r in detail['paragraph_plan']['paragraphs']['items'] if r['paragraph_id'] == pid)
    assert paragraph['paragraph']['edit_action']['payload'] == row['edit_action']['payload'] and paragraph['paragraph']['remove_action']['payload'] == row['remove_action']['payload']
    assert set(paragraph['paragraph']['clipped']) >= {'proposition', 'explanation', 'qualification', 'from_previous', 'to_next'}
    # the editor read carries the exact complete values (and is the explicit, larger editor scope)
    editor = read(tmp_path, view='detail', section_ids=['first'], projection='guard', edit_choices=True)['reader_transition']['edit_action']
    assert editor['values'] == detail['reader_transition']['edit_action']['values'] and editor['values']['entry_state'] == text
    peditor = read(tmp_path, view='detail', section_ids=['first'], projection='guard', subject='paragraph', paragraph_id=pid, edit_choices=True)['paragraph']
    assert peditor['edit_action']['values'] == row['edit_action']['values'] and 'clipped' not in peditor and peditor['proposition'] == row['proposition']
    # an untouched editor sends no change; clearing an existing field is a change the owner applies
    cleared = writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**editor['payload'], 'changes': {'permitted_recap': ''}})
    assert cleared['plan_publication']['status'] == 'COMMITTED'
    assert read(tmp_path, view='detail', section_ids=['first'], projection='guard', edit_choices=True)['reader_transition']['edit_action']['values']['permitted_recap'] == ''


# every writing-tool call, reads included, appends its own 'writing-tool-read' record to the engine's call
# log (contract/journal.jsonl, contract/talk.jsonl); that log is the call record, not project data
CALL_LOG = {'contract/journal.jsonl', 'contract/talk.jsonl'}


def _tree_hashes(root):
    import hashlib
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and str(p.relative_to(root)) not in CALL_LOG}


# repair3 R2 (2026-10-14): a row whose only shown text is clipped (authored == []) and a clipped reader
# transition each have an owner continuation that returns the exact full text, read only.
def test_clipped_only_rows_and_a_clipped_transition_have_exact_read_only_full_continuations(tmp_path):
    _section_fixture(tmp_path)
    full = {'proposition': 'A complete authored proposition, kept whole. ' * 22, 'function': 'A complete authored function, “quoted” and 中文. ' * 22}
    for name, text in full.items():
        create = read(tmp_path, view='detail', section_ids=['first'], projection='guard', subject='create')['create_action']
        writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**create['payload'], 'changes': {name: text}})
    entry = 'A complete authored entry condition with a\nline break and "quotes". ' * 14
    call = read(tmp_path, view='detail', section_ids=['first'], projection='guard')['reader_transition']['edit_action']
    writing_tools.execute(tmp_path, 'book', 'work', 'structure_change', {**call['payload'], 'changes': {'entry_state': entry}})
    display = read(tmp_path, view='detail', section_ids=['first'], projection='display')
    section = display['sections'][0]
    rows = {name: next(r for r in section['paragraph_plan']['paragraphs']['items'] if r.get(name, '').startswith(text[:20])) for name, text in full.items()}
    row_read = section['paragraph_plan']['paragraphs']['row_read']
    transition = section['reader_transition']
    before = _tree_hashes(tmp_path)
    for name, row in rows.items():
        # clipped-only: nothing else authored, so the shortened text is the only reason to read on
        assert row['authored'] == [] and row['clipped'] == [name] and row[name] != full[name] and row[name].endswith('…')
        whole_payload = {**row_read['payload'], 'paragraph_id': row['paragraph_id']}
        assert set(whole_payload) == {'view', 'section_ids', 'projection', 'paragraph_id'}
        whole = read(tmp_path, **whole_payload)
        code, _, raw = project_work_surface.handle('/work/structure', {'project': ['book'], 'view': ['detail'], 'section_ids': ['["first"]'], 'projection': ['display'], 'paragraph_id': [row['paragraph_id']]}, 'GET', b'', repo_root=tmp_path)
        assert code == 200 and json.loads(raw) == whole
        item = whole['sections'][0]['paragraph_plan']['paragraphs']['items'][0]
        assert item['paragraph_id'] == row['paragraph_id'] and item[name] == full[name] and not item.get('clipped')
        assert whole['sections'][0]['paragraph_plan']['revision'] == section['paragraph_plan']['revision']
    # the transition: clipped on the page, exact on its values_read, same revisions, no write
    assert transition['clipped'] == ['entry_state'] and transition['fields']['entry_state'] != entry
    assert transition['values_read'] == {'operation': 'structure', 'payload': {'view': 'detail', 'section_ids': ['first'], 'subject': 'contract', 'projection': 'guard', 'edit_choices': True}}
    values = read(tmp_path, **transition['values_read']['payload'])
    owner = values['reader_transition']
    assert values['project'] == 'book' and values['section_id'] == 'first' and values['subject'] == 'contract' and owner['section_id'] == 'first'
    assert owner['edit_action']['values']['entry_state'] == entry
    assert (owner['revision'], owner['subject_revision']) == (transition['revision'], transition['subject_revision'])
    after = _tree_hashes(tmp_path)
    assert after == before and any(k.startswith('synthetics papers/book/manuscript/') for k in after), 'the full reads wrote no project file'


def populated_with_beats(root, text, sections=64, beats=13, paragraphs=22, members=17):
    """The release-measured shape (ACTUAL-C1011-DISPLAY-BYTES): a populated contract, `paragraphs` populated
    rows, `members` members of which `beats` are narrative beats, in a plan of `sections` sections."""
    wide(root, paragraphs=paragraphs, members=members, text=text)
    plan_path = root / 'synthetics papers' / 'book' / 'manuscript' / 'projection_plan.json'
    plan = json.loads(plan_path.read_text())
    plan['sections'] += [{'id': 'extra-%02d' % i, 'title': 'Extra %02d' % i, 'kind': 'section', 'parent_id': 'second', 'source_file': 'chapters/chapter-01.tex',
                          'job': 'support', 'notes': '', 'refs': [], 'beats': [], 'nodes_in_order': [], 'figures': []} for i in range(sections - len(plan['sections']))]
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + '\n')
    from laplace.research import corpus_ingest
    for index, ident in enumerate(plan['sections'][0]['nodes_in_order'][:beats]):
        corpus_ingest.rewire_add(root, 'book', {'kind': 'set-spine', 'node': ident, 'ord': index + 1, 'narrative': ('Beat %d: ' % index) + text, 'by': 'fixture'})
    call = read(root, view='detail', section_ids=['first'], projection='guard')['reader_transition']['edit_action']
    writing_tools.execute(root, 'book', 'work', 'structure_change', {**call['payload'], 'changes': {key: key + ': ' + text for key in reader_plan.CONTRACT_STRINGS}})
    return plan


def _http(root, **query):
    params = {'project': ['book'], **{key: [json.dumps(value) if isinstance(value, list) else str(value).lower() if isinstance(value, bool) else str(value)] for key, value in query.items()}}
    code, _, raw = project_work_surface.handle('/work/structure', params, 'GET', b'', repo_root=root)
    return code, raw


@pytest.mark.parametrize('label,text', [('ascii', 'x' * 300), ('cjk', '中' * 300), ('quoted', '"key": "value", ' * 25)])
def test_populated_section_with_narrative_beats_keeps_the_default_display_under_the_page_budget_with_lazy_beat_pages(tmp_path, label, text):
    populated_with_beats(tmp_path, text)
    display = read(tmp_path, view='detail', section_ids=['first'], projection='display')
    code, raw = _http(tmp_path, view='detail', section_ids=['first'], projection='display')
    assert code == 200 and json.loads(raw) == display and len(raw) == size(display) <= 12_000, (label, len(raw), size(display))
    section = display['sections'][0]
    rows = section['paragraph_plan']['paragraphs']
    assert len(rows['items']) == reader_plan.DISPLAY_PAGE_ROWS and rows['total'] == 22 and rows['next_read'], 'a useful six-row page with its continuation'
    assert section['members']['total'] == 17 and set(section['reader_transition']['clipped']) == set(reader_plan.CONTRACT_STRINGS)
    # the beats: the exact count and one read; member rows that are beats say so
    page = display['spine_page']
    assert 'spine' not in display and page['total'] == 13 and page['read']['payload'] == {'view': 'detail', 'section_ids': ['first'], 'projection': 'display', 'spine_offset': 0}
    assert page['row_read'] == {'operation': 'structure', 'payload': {'view': 'detail', 'node_id': '<id>'}}
    plain = read(tmp_path, view='detail', section_ids=['first'])
    beat_ids = [beat['id'] for beat in plain['spine']]
    assert len(beat_ids) == 13 and all(node.get('beat') is (True if node['id'] in beat_ids else None) for node in section['nodes'])
    # every beat page is bounded, native == HTTP, and together they are the section's complete beat order
    seen, handle = [], page['read']
    while handle:
        value = read(tmp_path, **handle['payload'])
        code, raw = _http(tmp_path, **handle['payload'])
        assert code == 200 and json.loads(raw) == value and len(raw) <= 4_000
        assert value['page'] == 'spine' and value['section_id'] == 'first' and 'sections' not in value
        assert value['structure_observation']['spine_revision'] == display['structure_observation']['spine_revision']
        seen += [beat['id'] for beat in value['spine']]
        handle = value['spine_page']['next_read']
    assert seen == beat_ids
    # a beat's whole narrative is on its row read
    beat = read(tmp_path, **{**page['row_read']['payload'], 'node_id': beat_ids[0]})
    assert next(row for row in beat['spine'] if row['id'] == beat_ids[0])['narrative'] == 'Beat 0: ' + text


def test_beat_pages_continue_exactly_fold_a_lone_remainder_and_refuse_misplaced_offsets(tmp_path, monkeypatch):
    populated_with_beats(tmp_path, 'short text', sections=8, beats=13, paragraphs=3)
    for rows, sizes in ((5, [5, 5, 3]), (6, [6, 7]), (13, [13])):
        monkeypatch.setattr(reader_plan, 'DISPLAY_SPINE_ROWS', rows)
        handle, got = read(tmp_path, view='detail', section_ids=['first'], projection='display')['spine_page']['read'], []
        while handle:
            value = read(tmp_path, **handle['payload'])
            assert value['spine_page']['limit'] == len(value['spine']) and value['spine_page']['total'] == 13
            got.append(len(value['spine'])); handle = value['spine_page']['next_read']
        assert got == sizes, (rows, got)
    for scope, message in (({'projection': 'display', 'spine_offset': 13}, 'spine_offset must be'), ({'projection': 'display', 'spine_offset': -1}, 'less than the minimum of 0'),
                           ({'projection': 'guard', 'spine_offset': 0}, 'projection:display only'), ({'spine_offset': 0}, 'projection:display only'),
                           ({'projection': 'display', 'spine_offset': 0, 'paragraph_id': 'first-p1'}, 'not both')):
        with pytest.raises(Exception, match=message):
            read(tmp_path, view='detail', section_ids=['first'], **scope)
        code, _ = _http(tmp_path, view='detail', section_ids=['first'], **scope)
        assert code in (400, 409, 422), (scope, code)
