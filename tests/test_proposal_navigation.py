import json
import pytest
from laplace.manuscript import proposal_navigation as nav, manuscript_proposals as owner, proposal_preflight
from laplace.web import authoring as surface
from laplace.work import author_history_metrics as metrics
from laplace.native import tools as writing_tools
from laplace.writing import session_reads
from laplace.writing import records as writing_records
from laplace.writing.records import _fold
from laplace.writing.records import _bank as records_bank
from laplace.writing import mutation_attribution
from laplace.core import checkout
from test_proposal_lifecycle import setup

@pytest.fixture(autouse=True)
def clear():
    _fold._CACHE.clear();metrics._INDEXES.clear()
    yield
    _fold._CACHE.clear();metrics._INDEXES.clear()


def test_existing_generic_read_and_http_same_owner_queue_and_exact_child(tmp_path,monkeypatch):
    md,tid,edits,context=setup(tmp_path)
    old=owner.preview(tmp_path,'fixture',tid)
    monkeypatch.setattr(session_reads,'_records',lambda *a,**k:pytest.fail('whole history'))
    queue=nav.read(tmp_path,'fixture',{'limit':1})
    assert queue['proposals'] and queue['pagination']['examined']==1
    root_handle=nav.handle('fixture',{'limit':1})['native_request']
    native=writing_tools.call(tmp_path,'fixture','review',root_handle)
    assert native['outcome']=='read' and native['owner_response']['proposals']==queue['proposals']
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    status,_,raw=surface.handle('/authoring/proposals',{'project':['fixture'],'limit':['1']},'GET',b'')
    assert status==200 and json.loads(raw)['proposals']==queue['proposals']
    selected=queue['proposals'][0]['read_handle']['native_request']
    detail=writing_tools.call(tmp_path,'fixture','review',selected)['owner_response']
    assert detail['proposal_version']==old['proposal_version']
    assert [(row['edit_id'],row['status'],row['allowed_actions']) for row in detail['edits']]==[(row['edit_id'],row['status'],row['allowed_actions']) for row in old['edits']]
    assert 'before' not in detail['edits'][0] and detail['coverage']['whole_history_loaded'] is False
    child=writing_tools.call(tmp_path,'fixture','review',detail['edits'][0]['read_handle']['native_request'])['owner_response']
    assert len(child['edits'])==1 and child['edits'][0]['edit_id']==owner.edit_id(edits[0])
    part=writing_tools.call(tmp_path,'fixture','review',child['edits'][0]['text_reads']['original']['native_request'])['owner_response']
    assert part['content']==edits[0]['before'] and part['coverage']['complete']


def test_native_advertised_schema_and_returned_handles_share_canonical_scope(tmp_path):
    from jsonschema import Draft202012Validator
    from laplace.native import declarations as writing_declarations
    setup(tmp_path)
    home=next(row for row in writing_declarations.native_homes('fixture','proposal@paragraph')
              if row['owner_read']['operation']=='authoring/proposals')
    schema=home['payload'];validate=Draft202012Validator(schema)
    assert schema==nav.contract() and not list(validate.iter_errors(home['native_request']['payload']))
    queue=writing_tools.call(tmp_path,'fixture','review',home['native_request'])['owner_response']
    handle=queue['proposals'][0]['read_handle']['native_request']
    assert not list(validate.iter_errors(handle['payload']))
    detail=writing_tools.call(tmp_path,'fixture','review',handle)['owner_response']
    edit=detail['edits'][0]['read_handle']['native_request']
    assert not list(validate.iter_errors(edit['payload']))
    child=writing_tools.call(tmp_path,'fixture','review',edit)['owner_response']
    assert writing_tools.call(tmp_path,'fixture','review',child['edits'][0]['text_reads']['original']['native_request'])['owner_response']['content']
    basis=nav.handle('fixture',{**handle['payload'],'view':'basis'})['native_request']
    assert not list(validate.iter_errors(basis['payload']))
    assert writing_tools.call(tmp_path,'fixture','review',basis)['outcome']=='read'
    for invalid in ({**handle['payload'],'limit':2},{'unknown':'field'}):
        assert list(validate.iter_errors(invalid))
        with pytest.raises(ValueError):nav.read(tmp_path,'fixture',invalid)
    refused=writing_tools.call(tmp_path,'fixture','review',{**handle,'target':'another-project'})
    assert refused['ok'] is False and 'owner_response' not in refused


def test_plan_guard_citation_names_executable_supplied_argument():
    import ast
    from laplace.native import declarations as writing_declarations
    door=writing_declarations.HTTP_DECLARATIONS['authoring/section-change'].rules[0].door
    source=__import__('laplace.manuscript.manuscript_structure',fromlist=['__file__'])
    tree=ast.parse(open(source.__file__).read())
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_check_plan_guard')
    call=next(node for node in ast.walk(function) if isinstance(node,ast.Call)
              and isinstance(node.func,ast.Attribute) and node.func.attr=='gate')
    supplied=next(keyword for keyword in call.keywords if keyword.arg=='supplied')
    assert int(door.rsplit(':',1)[1])==supplied.lineno
    assert isinstance(supplied.value,ast.Dict)


def test_metadata_identity_cannot_be_preflighted_or_rendered(tmp_path):
    md,tid,edits,context=setup(tmp_path)
    summary=owner.identity_proposal(owner.proposal_metadata({'answer':'x','edits':edits}))
    with pytest.raises(ValueError,match='read-only'):proposal_preflight.preflight(tmp_path,'fixture',{},summary)
    with pytest.raises(ValueError):owner.identity_proposal({**owner.proposal_metadata({'edits':edits}),'effect_sha256':'wrong'})


def test_selected_candidate_hydrates_exact_baseline_payloads_without_queue_hydration(tmp_path,monkeypatch):
    md,tid,edits,context=setup(tmp_path)
    for ident,path in [('READBASE-a','first.md'),('READBASE-b','second.md')]:
        writing_records.bank(tmp_path,{'record':'writing-tool-read-baseline','id':ident,
            'turn_id':tid,'project':'fixture','operation':'read_artifact',
            'payload':{'path':path},'output_sha256':'sha256:'+('a' if ident.endswith('a') else 'b')*64})
    sealed=writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-with-baselines',
        'turn_id':tid,'project':'fixture','proposal':{'answer':'Selected basis.','edits':edits}})
    idx=metrics.index(tmp_path);calls=[];original=nav._raw
    def raw(index,meta):calls.append(meta['id']);return original(index,meta)
    monkeypatch.setattr(nav,'_raw',raw)
    nav.read(tmp_path,'fixture',{})
    assert 'READBASE-a' not in calls and 'READBASE-b' not in calls
    calls.clear();basis=sealed['proposal_basis']
    required={tid,sealed['id'],basis.get('turn_basis_record_id'),*basis['read_ids']}
    records,_=nav._records(idx,'fixture',required)
    projected=records['turns'][tid]['proposal_bases'][sealed['proposal_instance_version']]
    assert set(basis['read_ids'])=={read['id'] for read in projected['tool_reads'].values()}
    assert _fold._read_basis_digest(projected['tool_reads'])==basis['read_receipts_sha256']
    assert calls.count('READBASE-a')==calls.count('READBASE-b')==1
    assert {read['payload']['path'] for read in projected['tool_reads'].values()
            if read['id'].startswith('READBASE-')}=={'first.md','second.md'}


def test_partial_accept_retirement_uses_existing_owner_and_pinned_queue_cut(tmp_path,monkeypatch):
    from test_proposal_lifecycle import decide,_bind_rewrite_fixture
    md,tid,edits,context=setup(tmp_path);_bind_rewrite_fixture(monkeypatch,md)
    first=nav.read(tmp_path,'fixture',{'limit':1})
    exact=first['proposals'][0]['read_handle']['native_request']['payload']
    parent=nav.read(tmp_path,'fixture',exact)
    child=nav.read(tmp_path,'fixture',parent['edits'][0]['read_handle']['native_request']['payload'])
    assert parent['remaining']==2 and parent['read_scope']['kind']=='candidate'
    assert child['remaining']==1 and child['read_scope']['kind']=='selected-edit'
    preview=owner.preview(tmp_path,'fixture',tid)
    accepted=decide(tmp_path,tid,preview['edits'][0],preview['proposal_version'])
    current=nav.read(tmp_path,'fixture',{})
    assert current['proposals'][0]['edit_count']==1
    assert nav.read(tmp_path,'fixture',exact)['remaining']==1
    detail=nav.read(tmp_path,'fixture',first['proposals'][0]['read_handle']['native_request']['payload'])
    baseline=owner.preview(tmp_path,'fixture',tid,preview['proposal_version'])
    assert [(row['status'],row['allowed_actions']) for row in detail['edits']]==[(row['status'],row['allowed_actions']) for row in baseline['edits']]
    for edit in baseline['edits']:
        if edit['status']=='pending':decide(tmp_path,tid,edit,baseline['proposal_version'],'reject')
    assert nav.read(tmp_path,'fixture',{})['proposals']==[]
    assert nav.read(tmp_path,'fixture',exact)['remaining']==0
    history=nav.read(tmp_path,'fixture',{'view':'history'})
    assert history['proposals'] and all(not row['allowed_actions'] for row in history['proposals'])


def test_legacy_cas_queue_inspects_only_requested_page_no_whole_history(tmp_path,monkeypatch):
    from laplace.core.records import journal
    md,tid,edits,context=setup(tmp_path)
    for number in range(28):
        turn='WT-legacy-'+str(number)
        journal.bank_row('contract/talk.jsonl',{'record':'writing-turn','id':turn,'project':'fixture','session_id':'WS-legacy'},root=tmp_path)
        body={'answer':'A private long historical narrative. '*1000,'edits':edits}
        row=records_bank.prepare_custody_row(tmp_path,{'record':'writing-reply','id':'WR-legacy-'+str(number),'project':'fixture','turn_id':turn,'proposal':body})
        row.pop('proposal_projection',None) # Exact retained pre-header representation.
        journal.bank_row('contract/talk.jsonl',row,root=tmp_path)
    monkeypatch.setattr(session_reads,'_records',lambda *a,**k:pytest.fail('whole history'))
    calls=[];read_body=nav._body
    monkeypatch.setattr(nav,'_body',lambda *a,**k:(calls.append(a[1]['id']),read_body(*a,**k))[1])
    result=nav.read(tmp_path,'fixture',{'limit':2})
    assert len(calls)==2 and result['pagination']['examined']==2
    assert result['pagination']['remaining_candidates']>=26
    assert 'private long' not in json.dumps(result)
    assert result['pagination']['next_read']
    calls.clear();again=nav.read(tmp_path,'fixture',{'limit':2})
    assert calls==[] and again['proposals']==result['proposals']


@pytest.mark.parametrize('query',[{'view':'basis'},{'view':'edit'},{'proposal_version':'x'},
    {'id':'WT','view':'queue'},{'id':'WT','cursor':'x'},{'id':'WT','as_of':'x'},
    {'id':'WT','session_id':'S'},{'id':'WT','work_id':'W'},{'id':'WT','file':'main.tex'},
    {'limit':1.5},{'limit':True},{'id':'WT','turn_id':'other'}])
def test_unsupported_or_wrong_typed_selectors_refuse_before_owner_io(tmp_path,query,monkeypatch):
    from laplace.pipeline import registry
    monkeypatch.setattr(registry,'resolve',lambda *a,**k:pytest.fail('invalid selector performed owner I/O'))
    with pytest.raises(ValueError):nav.read(tmp_path,'fixture',query)


def test_cold_legacy_exact_version_uses_only_selected_turn_bodies(tmp_path,monkeypatch):
    from laplace.core.records import journal
    md,tid,edits,context=setup(tmp_path)
    version=owner.preview(tmp_path,'fixture',tid)['proposal_version']
    journal_path=tmp_path/'contract/talk.jsonl'
    rows=[json.loads(line) for line in journal_path.read_text().splitlines()]
    for row in rows:
        if row.get('turn_id')==tid and isinstance(row.get('proposal'),dict):row.pop('proposal_projection',None)
    journal_path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    metrics._INDEXES.clear()
    monkeypatch.setattr(session_reads,'_records',lambda *a,**k:pytest.fail('whole history'))
    detail=nav.read(tmp_path,'fixture',{'id':tid,'proposal_version':version,'view':'summary'})
    assert detail['proposal_version']==version and len(detail['edits'])==2


def test_inspection_read_receipt_is_navigation_not_source_authority(tmp_path):
    from laplace.core.records import journal
    from test_source_semantic_contract import fixture
    md,path=fixture(tmp_path)
    old={'file':'Main.tex','line_start':3,'line_end':3,'before':'Original prose.','after':'Proposed prose.','reason':'Clarify'}
    source=session_reads._records(tmp_path)['turns']['T']
    journal.bank_row('contract/talk.jsonl',{'record':'writing-turn','id':'NO-SOURCE','session_id':'S','project':'alias','mode':'work','selection':{},'dependencies':{},'document':source['document']},root=tmp_path)
    # Existing queue inspection banks one ordinary read receipt, no baseline/source scope.
    result=writing_tools.call(tmp_path,'alias','work',nav.handle('alias',{})['native_request'],turn_id='NO-SOURCE')
    row=result['owner_response']['read_receipt'];assert row['operation']=='authoring/proposals'
    observed=session_reads._records(tmp_path)['turns']['NO-SOURCE']
    assert mutation_attribution._proposal_consulted_reads(observed,[old])==[]
    assert proposal_preflight._scope(observed,tmp_path,md,'alias')=={}
    before=path.read_bytes()
    refused=proposal_preflight.preflight(tmp_path,'alias',observed,{'edits':[old]})
    assert not refused['valid'] and path.read_bytes()==before
    writing_tools.execute(tmp_path,'alias','work','source',{'files':['Main.tex']},turn_id='NO-SOURCE')
    current=session_reads._records(tmp_path)['turns']['NO-SOURCE']
    assert proposal_preflight.preflight(tmp_path,'alias',current,{'edits':[old]})['valid']


@pytest.mark.parametrize('view',['summary','edit','basis','preview'])
def test_foreign_edit_identity_refuses_in_selected_version(tmp_path,view):
    md,tid,edits,context=setup(tmp_path)
    queue=nav.read(tmp_path,'fixture',{})
    payload=queue['proposals'][0]['read_handle']['native_request']['payload']
    with pytest.raises(ValueError,match='Exact selected edit'):
        nav.read(tmp_path,'fixture',{**payload,'edit_id':'EDIT-foreign','view':view})


def test_selected_human_preview_handle_preserves_exact_child_and_rendered_proposal(tmp_path):
    md,tid,edits,context=setup(tmp_path)
    payload=nav.read(tmp_path,'fixture',{})['proposals'][0]['read_handle']['native_request']['payload']
    summary=nav.read(tmp_path,'fixture',payload)
    handle=summary['edits'][0]['preview_read']
    assert handle['native_request']['payload']=={**summary['edits'][0]['read_handle']['native_request']['payload'],'view':'preview'}
    preview=nav.read(tmp_path,'fixture',handle['native_request']['payload'])
    assert len(preview['edits'])==1 and preview['edits'][0]['after_blocks']
    plain=nav.read(tmp_path,'fixture',summary['edits'][0]['read_handle']['native_request']['payload'])
    assert 'after_blocks' not in plain['edits'][0]


def test_http_declarations_derive_logical_queries_from_same_owner_without_shadow_schemas():
    from jsonschema import Draft202012Validator
    from laplace.web import writing_declared_http
    from laplace.native import declarations
    for name, preview in [('authoring/proposals', False), ('authoring/proposal-preview', True)]:
        schema = declarations.HTTP_DECLARATIONS[name].payload
        assert schema == nav.http_contract(preview=preview)
        Draft202012Validator.check_schema(schema)
    assert 'project' not in nav.contract()['properties']
    assert 'summary' not in nav.contract()['properties']


def test_declared_canonical_queue_and_exact_summary_edit_basis_handles_reach_actual_owner(tmp_path, monkeypatch):
    from urllib.parse import urlparse, parse_qs
    from jsonschema import validate
    from laplace.web import writing_declared_http
    from laplace.native import declarations
    md, tid, edits, context = setup(tmp_path)
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    def read(handle):
        path = urlparse(handle['http']['url'])
        logical = {'project': 'fixture', **handle['native_request']['payload']}
        declaration = declarations.HTTP_DECLARATIONS['authoring/proposal-preview' if path.path.endswith('preview') else 'authoring/proposals']
        validate(logical, declaration.payload)
        status, _, raw = surface.handle(path.path, parse_qs(path.query), 'GET', b'')
        assert status == 200, raw
        return json.loads(raw)
    queue = read(nav.handle('fixture', {'view': 'queue', 'limit': 1}))
    summary = read(queue['proposals'][0]['read_handle'])
    assert summary['turn_id'] == tid and summary['proposal_version'] == queue['proposals'][0]['proposal_version']
    child = read(summary['edits'][0]['read_handle'])
    assert len(child['edits']) == 1 and child['edits'][0]['before'] == edits[0]['before']
    basis = read(summary['edits'][0]['basis_read'])
    assert basis['turn_id'] == tid and basis['proposal_version'] == summary['proposal_version']


def test_declared_legacy_preview_identity_and_project_aliases_preserve_actual_defaults(tmp_path, monkeypatch):
    from jsonschema import validate
    md, tid, edits, context = setup(tmp_path)
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    for project_key, identity_key in [('project', 'id'), ('project', 'turn_id'), ('corpus', 'turn_id')]:
        logical = {project_key: 'fixture', identity_key: tid}
        validate(logical, nav.http_contract(preview=True))
        status, _, raw = surface.handle('/authoring/proposal-preview', {key: [value] for key, value in logical.items()}, 'GET', b'')
        assert status == 200, raw
        value = json.loads(raw)
        assert value['turn_id'] == tid and value['edits'][0]['before'] == edits[0]['before']
    validate({'project': 'fixture', 'summary': '1'}, nav.http_contract())
    status, _, raw = surface.handle('/authoring/proposals', {'project': ['fixture'], 'summary': ['1']}, 'GET', b'')
    assert status == 200 and json.loads(raw)['view'] == 'queue'


@pytest.mark.parametrize('extra', [{'cursor': 'other-cut'}, {'limit': 1}, {'view': 'queue'}, {'session_id': 'other'}])
def test_declared_exact_scope_conflicts_also_refuse_at_actual_read_owner(tmp_path, monkeypatch, extra):
    from jsonschema import Draft202012Validator
    md, tid, edits, context = setup(tmp_path)
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    logical = {'project': 'fixture', 'id': tid, **extra}
    assert list(Draft202012Validator(nav.http_contract(preview=True)).iter_errors(logical))
    status, _, raw = surface.handle('/authoring/proposal-preview', {key: [str(value)] for key, value in logical.items()}, 'GET', b'')
    assert status == 409 and json.loads(raw)['error']


def test_identity_alias_ambiguity_stays_actual_owner_refusal_not_schema_equality_claim(tmp_path, monkeypatch):
    from jsonschema import validate
    md, tid, edits, context = setup(tmp_path)
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    logical = {'project': 'fixture', 'id': tid, 'turn_id': 'DIFFERENT'}
    # Standard JSON Schema types cannot compare dynamic aliases. The existing owner does.
    validate(logical, nav.http_contract(preview=True))
    status, _, raw = surface.handle('/authoring/proposal-preview', {key: [value] for key, value in logical.items()}, 'GET', b'')
    assert status == 409 and 'Conflicting turn identities' in json.loads(raw)['error']
    status, _, raw = surface.handle('/authoring/proposal-preview', {'project': ['fixture'], 'id': [tid], 'turn_id': [tid]}, 'GET', b'')
    assert status == 200, raw


def test_declared_owner_continuation_and_retained_cut_work_without_broadening_scope(tmp_path, monkeypatch):
    from urllib.parse import urlparse, parse_qs
    from jsonschema import validate
    md, tid, edits, context = setup(tmp_path)
    writing_records.bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-other',
        'turn_id': tid, 'project': 'fixture', 'proposal': {'answer': 'Another retained candidate.', 'edits': edits[:1]}})
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    first = nav.read(tmp_path, 'fixture', {'view': 'queue', 'limit': 1})
    continuation = first['pagination']['next_read']
    assert continuation
    validate({'project': 'fixture', **continuation['native_request']['payload']}, nav.http_contract())
    path = urlparse(continuation['http']['url'])
    query = parse_qs(path.query)
    status, _, raw = surface.handle(path.path, query, 'GET', b'')
    assert status == 200 and json.loads(raw)['as_of'] == first['as_of']
    retained = {'project': 'fixture', 'view': 'queue', 'as_of': first['as_of'], 'limit': 1}
    validate(retained, nav.http_contract())
    status, _, raw = surface.handle('/authoring/proposals', {key: [str(value)] for key, value in retained.items()}, 'GET', b'')
    assert status == 200 and json.loads(raw)['as_of'] == first['as_of']
    query['view'] = ['history']
    status, _, raw = surface.handle(path.path, query, 'GET', b'')
    assert status == 409, raw


@pytest.mark.parametrize('extra', [{'record_id': 'without-turn'}, {'view': 'edit', 'edit_id': 'without-turn'}])
def test_declared_collection_detail_without_identity_refuses_actual_owner(tmp_path, monkeypatch, extra):
    from jsonschema import Draft202012Validator
    md, tid, edits, context = setup(tmp_path)
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    logical = {'project': 'fixture', **extra}
    assert list(Draft202012Validator(nav.http_contract()).iter_errors(logical))
    status, _, raw = surface.handle('/authoring/proposals', {key: [value] for key, value in logical.items()}, 'GET', b'')
    assert status == 409 and json.loads(raw)['error']


def test_queue_labels_use_bounded_stored_turn_context_not_shared_conversation_title(tmp_path, monkeypatch):
    md, tid, edits, context = setup(tmp_path)
    old = session_reads._records(tmp_path)['turns'][tid]
    session_id = old['session_id']
    writing_records.bank(tmp_path, {'record': 'writing-session-title', 'id': 'TITLE-old',
        'project': 'fixture', 'session_id': session_id, 'title': 'Earlier paragraph conversation'})
    timestamps={}
    for name, label in [('title', 'Review the manuscript title'), ('paragraph', 'Review chapter introduction'), ('oversized', 'X'*300)]:
        ident = 'WT-label-'+name
        turn_row=writing_records.bank(tmp_path, {'record':'writing-turn','id':ident,'project':'fixture',
            'session_id':session_id,'workspace_context':{'surface':'manuscript','label':label},
            'ts':'2026-10-08T17:00:00Z','document':old['document']})
        timestamps[ident]=turn_row['ts']
        writing_records.bank(tmp_path, {'record':'writing-proposal','id':'PROP-label-'+name,
            'project':'fixture','turn_id':ident,'proposal':{'answer':'Retained proposal.','edits':edits}})
    metrics._INDEXES.clear()  # Actual cold lightweight metadata, no historical body hydration.
    monkeypatch.setattr(session_reads,'_records',lambda *a,**k:pytest.fail('whole history'))
    monkeypatch.setattr(nav,'_raw',lambda *a,**k:pytest.fail('queue opened historical body'))
    queue=nav.read(tmp_path,'fixture',{'view':'queue'})
    selected={row['id']:row for row in queue['proposals']}
    assert selected['WT-label-title']['proposal_label']=='Review the manuscript title'
    assert selected['WT-label-paragraph']['proposal_label']=='Review chapter introduction'
    assert selected['WT-label-title']['label_basis']=='stored-turn-context'
    assert selected['WT-label-title']['conversation_title']==selected['WT-label-paragraph']['conversation_title']
    assert len(selected['WT-label-oversized']['proposal_label'])==240
    assert selected['WT-label-oversized']['label_truncated'] is True
    assert selected['WT-label-title']['label_truncated'] is False
    assert selected['WT-label-title']['turn_ts']==timestamps['WT-label-title']


def test_a_proposal_read_never_waits_for_the_fold_lock_while_holding_the_index_lock(tmp_path, monkeypatch):
    """Live freeze 2026-10-20: the fold refresh (records._fold._records, under every rich session read) holds the
    journal fold lock and then takes the metadata index lock; a proposal read held the index lock and then took the
    fold lock (proposal_currentness.proposal_view, manuscript_proposals.preview). This thread plays the fold refresh:
    it holds the fold lock while a real proposal detail read runs, then asks for the index lock with a bound. With
    one order (fold before index) the reader asks for fold before it holds index, so the index lock stays free and
    both finish; with the old order the reader holds index while it waits for fold and the bounded acquire fails.
    Every wait is bounded, so the old order fails here instead of hanging."""
    import threading
    from laplace.writing import turn_jobs, records as writing_records
    from laplace.writing.records import _fold
    md, tid, edits, context = setup(tmp_path)
    assert nav.read(tmp_path, 'fixture', {'id': tid})['proposal_version']   # the fixture's own reads settle first
    index_lock, real = writing_records.index_lock, turn_jobs._LOCK
    requested, seen, results = threading.Event(), {}, {}

    class ObservedFold:
        """The same fold lock; it notes whether the reader already holds the index lock when it first asks for fold."""
        def acquire(self, blocking=True, timeout=-1):
            if threading.current_thread() is reader and 'index_held' not in seen:
                seen['index_held'] = index_lock._is_owned()
                requested.set()
            return real.acquire(blocking, timeout)

        def release(self):
            real.release()

        def __enter__(self):
            return self.acquire()

        def __exit__(self, *exc):
            real.release()

        def _is_owned(self):
            return real._is_owned()

    observed = ObservedFold()
    for module in (turn_jobs, _fold, surface, session_reads):
        monkeypatch.setattr(module, '_LOCK', observed)

    def run():
        try:
            results['detail'] = nav.read(tmp_path, 'fixture', {'id': tid})
        except Exception as exc:   # pragma: no cover - reported below
            results['error'] = exc

    reader = threading.Thread(target=run, daemon=True)
    with observed:
        reader.start()
        assert requested.wait(10), 'the proposal read never asked for the fold lock'
        index_free = index_lock.acquire(timeout=2)
        if index_free:
            index_lock.release()
    reader.join(30)
    assert not reader.is_alive() and 'error' not in results, results
    assert seen['index_held'] is False and index_free, 'the proposal read held the index lock while it waited for the fold lock'
    assert results['detail']['proposal_version']
