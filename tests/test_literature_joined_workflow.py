"""Joined source/claim/placement/currentness regressions on fresh project owners."""
import io,json,shutil,time
from pathlib import Path
import pytest
from laplace.projects import library as writing_projects
from laplace.native import tools
from laplace.manuscript import manuscript_source, project_structure, projection_viewer, review_surface
from laplace.research import concepts, literature, literature_support
from laplace.writing import operations
from laplace.writing import records as writing_records
from laplace.representation import writing_bodies
from laplace.pipeline import authoring


def execute(root,operation,payload,turn=None):
    if operation=='literature_bind' and 'claim_revision' not in payload:
        payload={**payload,'claim_revision':literature_support.meaning_revision('joined',payload['claim_id'],root)}
    return tools.execute(root,'joined','work',operation,payload,turn_id=turn)


def project(root,monkeypatch):
    from laplace.manuscript import storyboard
    monkeypatch.setattr(storyboard,'_repo_root',lambda:root)
    monkeypatch.setattr(review_surface,'_repo_root',lambda:root)
    monkeypatch.setattr(projection_viewer,'_repo_root',lambda:root)
    status,out=writing_projects.create({'name':'joined','title':'Source workflow fixture','kind':'paper','purpose':'Disposable source integration check.','audience':'Test reader'},root)
    assert status==201,out
    source=manuscript_source.resolve('joined',repo_root=root);manuscript=root/source['manuscript_dir']
    for ident,title in [('result:first','The first controlled claim'),('result:second','A distinct claim in another section')]:
        state=concepts.state('joined',root=root)
        execute(root,'concept_change',{'operation':'add_node','node':ident,'node_kind':'result','essence':title,'base_revision':state['revision']})
    (manuscript/'chapters/chapter-01.tex').write_text('\\section{First claim}\nFirst passage.\n\n\\section{Second claim}\nSecond passage.\n')
    current=execute(root,'structure',{})
    if current.get('sections'):
        pytest.fail('Fresh creation unexpectedly carried a pre-existing reader plan.')
    execute(root,'structure_change',{'operation':'initialize','expected_revision':current['revision'],
        'expected_source_revision':current['selected_source']['revision'],
        'sections':[{'id':'first','title':'First claim','kind':'section','file':'chapters/chapter-01.tex'},
                    {'id':'second','title':'Second claim','kind':'section','file':'chapters/chapter-01.tex'}]})
    for section,node in [('first','result:first'),('second','result:second')]:
        current=execute(root,'structure',{})
        execute(root,'structure_change',{'operation':'plan','expected_revision':current['revision'],
            'op':{'kind':'set-nodes','section':section,'order':[node]}})
    original=root/'original-source.txt';original.write_text('The first controlled claim holds only under the stated conditions.\nNo unrestricted generalisation is established.\n')
    imported=execute(root,'literature_import',{'metadata':{'title':'Controlled source','creators':['Fixture Author'],'year':'2026','item_type':'unpublished'},
        'provenance':{'description':'Explicit disposable test source','path':str(original)},'citekey':'FixtureSource'})
    return manuscript,source,imported['association']['key'],original


def bind(root,key,claim='result:first',turn=None):
    read=execute(root,'reference_text',{'key':key,'limit':1000},turn)
    return execute(root,'literature_bind',{'key':key,'claim_id':claim,'relation':'supports','rationale':'Supports the limited controlled statement only.',
        'reading_status':'partial','reading_id':read['reading_receipt']['id'],
        'evidence':{'locator':read['reading_receipt']['locator'],'excerpt':'only under the stated conditions'}},turn)


def bind_heading(root,section_id,heading_before,turn=None,**override):
    """Bind one reader-plan section to its exact CURRENT heading through the guarded owner (plan, selection and
    source-digest guards from fresh reads). Without it a section is FILE_ONLY and no citation is attributed."""
    outline=execute(root,'structure',{'view':'outline'},turn);summary=execute(root,'structure',{'view':'summary'},turn)
    heading=next(row for row in outline['headings']['items'] if row['heading_before']==heading_before)
    payload={'operation':'bind_source','section_id':section_id,'file':heading['file'],'line':heading['line'],
        'heading_before':heading['heading_before'],'expected_plan_revision':summary['authority']['plan_revision'],
        'expected_selection':outline['selected_source']['selection_identity'],
        'expected_source_digest':outline['sources'][heading['file']]['source_digest'],**override}
    return execute(root,'structure_change',payload,turn)


def test_binding_reaches_canonical_objects_and_use_is_section_specific(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    first=bind(tmp_path,key);second=bind(tmp_path,key,'result:second')
    assert first['canonical_source']==second['canonical_source']
    focused=execute(tmp_path,'concept',{'node':'result:first'})
    assert focused['source_support']['sources'][0]['qualification']=='PASSAGE_OBSERVED'
    logical=execute(tmp_path,'logical_plan',{'node':'result:first'})
    assert any(relation['target']==first['canonical_source'] for relation in logical['selected']['support'])
    chapter=manuscript/'chapters/chapter-01.tex'
    chapter.write_text('\\section{First claim}\nFirst passage \\cite{FixtureSource}.\n\n\\section{Second claim}\n% \\cite{FixtureSource}\nSecond passage.\n')
    # M5 S3: before an exact binding both sections are FILE_ONLY, so the active citation is not attributed to
    # any claim (no title or file coincidence counts). A stale source digest refuses the binding.
    unbound=execute(tmp_path,'literature_scope',{'node':'result:first'})
    assert unbound['claims'][0]['sources'][0]['manuscript_uses']==[]
    with pytest.raises(ValueError):
        bind_heading(tmp_path,'first','\\section{First claim}',expected_source_digest='sha256:'+'0'*64)
    for section,heading in (('first','\\section{First claim}'),('second','\\section{Second claim}')):
        assert bind_heading(tmp_path,section,heading)['binding']['precision']=='EXACT_HEADING'
    one=execute(tmp_path,'literature_scope',{'node':'result:first'})
    two=execute(tmp_path,'literature_scope',{'node':'result:second'})
    assert len(one['claims'][0]['sources'][0]['manuscript_uses'])==1
    assert two['claims'][0]['sources'][0]['manuscript_uses']==[]
    assert any(gap['kind']=='not-yet-cited' for gap in two['gaps'])
    original.write_text('The source changed its conclusion.')
    assert execute(tmp_path,'concept',{'node':'result:first'})['source_support']['sources'][0]['qualification']=='STALE'


def test_failed_canonical_half_stays_pending_and_same_bind_repairs(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    from laplace.research import corpus_ingest
    read=execute(tmp_path,'reference_text',{'key':key})
    original_add=corpus_ingest.rewire_add
    def fail_edge(root,project,payload):
        return {'error':'isolated edge failure'} if payload['kind']=='add-edge' else original_add(root,project,payload)
    monkeypatch.setattr(corpus_ingest,'rewire_add',fail_edge)
    with pytest.raises(ValueError,match='isolated edge failure'):bind(tmp_path,key)
    rows=json.loads((manuscript/'references.json').read_text())['associations']
    assert next(row for row in rows if row.get('claim_id')=='result:first')['binding_state']=='PENDING_CANONICAL'
    monkeypatch.setattr(corpus_ingest,'rewire_add',original_add)
    fixed=bind(tmp_path,key)
    assert fixed['association']['binding_state']=='BOUND'
    nodes=literature_support.network('joined',tmp_path)['nodes']
    assert len([ident for ident,node in nodes.items() if node.get('kind')=='citation'])==1


def seed_turn(root,source,selection,ident='WT-literature'):
    context=authoring.build_context('joined',selection,repo_root=root)
    writing_records.bank(root,{'record':'writing-session','id':'WS-literature','project':'joined','provider':'codex','model':'fixture','effort':'low'})
    writing_records.bank(root,{'record':'writing-turn','id':ident,'session_id':'WS-literature','project':'joined','mode':'work','selection':selection,
        'context_id':context['context_id'],'dependencies':context['dependencies'],'document':context['document'],'text':'Read and cite the source.'})
    return ident


@pytest.mark.skipif(shutil.which('latexmk') is None,reason='latexmk unavailable')
def test_same_turn_source_to_claim_to_citation_and_real_compiled_bibliography(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    selection={'files':['chapters/chapter-01.tex'],'line_start':2,'line_end':2}
    turn=seed_turn(tmp_path,source,selection)
    execute(tmp_path,'logical_plan',{'node':'result:first'},turn)
    execute(tmp_path,'references_attached',{},turn)
    execute(tmp_path,'source',selection,turn)
    bound=bind(tmp_path,key,turn=turn)
    assert bound['action_receipt']['refreshed_read_baselines']>=1
    applied=execute(tmp_path,'apply_revision',{'edits':[{'file':'chapters/chapter-01.tex','line_start':2,'line_end':2,
        'before':'First passage.','after':'First passage \\cite{FixtureSource}.','reason':'Cite the inspected supporting source.'}]},turn)
    assert applied['complete'],applied
    # M5 S3: bind both sections to their exact headings in the POST-application source (an earlier anchor is not
    # assumed to survive the edit); only then can the cited first claim be ready for completion.
    for section,heading in (('first','\\section{First claim}'),('second','\\section{Second claim}')):
        assert bind_heading(tmp_path,section,heading)['binding']['precision']=='EXACT_HEADING'
    execute(tmp_path,'build',{})
    for _ in range(100):
        build=execute(tmp_path,'build_status',{})
        if not build.get('running'):break
        time.sleep(.1)
    assert build.get('ok') and build.get('fresh'),build
    scope=execute(tmp_path,'literature_scope',{'node':'result:first'})
    assert scope['ready_for_completion'],scope['gaps']
    assert 'FixtureSource' in scope['bibliography']['rendered_keys']
    assert Path(scope['bibliography']['pdf']).is_file()


def test_bind_receipt_does_not_bless_external_source_change_during_owner_write(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    selection={'files':['chapters/chapter-01.tex'],'line_start':2,'line_end':2}
    turn=seed_turn(tmp_path,source,selection,'WT-during-source')
    execute(tmp_path,'logical_plan',{'node':'result:first'},turn)
    execute(tmp_path,'source',selection,turn)
    from laplace.research import literature
    original_bind=literature.bind;chapter=manuscript/'chapters/chapter-01.tex'
    def bind_with_external_change(*args,**kwargs):
        result=original_bind(*args,**kwargs)
        chapter.write_text(chapter.read_text().replace('First passage.','Externally changed passage.'))
        return result
    monkeypatch.setattr(literature,'bind',bind_with_external_change)

    bound=bind(tmp_path,key,turn=turn)

    attribution=bound['action_receipt']['mutation_attribution']
    assert attribution['exact'] is False and 'unowned canonical files changed' in attribution['reason']
    assert bound['action_receipt']['context_refreshed'] is False
    with pytest.raises(ValueError,match='(invalid source addressing|source changed|argument, evidence|Consulted project evidence changed)'):
        execute(tmp_path,'apply_revision',{'edits':[{'file':'chapters/chapter-01.tex','line_start':2,'line_end':2,
            'before':'First passage.','after':'First passage \\cite{FixtureSource}.','reason':'Cite source.'}]},turn)


def test_bind_receipt_does_not_bless_external_correction_during_owner_write(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    selection={'files':['chapters/chapter-01.tex'],'line_start':2,'line_end':2}
    turn=seed_turn(tmp_path,source,selection,'WT-during-correction')
    execute(tmp_path,'logical_plan',{'node':'result:first'},turn)
    execute(tmp_path,'source',selection,turn)
    from laplace.research import literature
    original_bind=literature.bind
    def bind_with_external_correction(*args,**kwargs):
        result=original_bind(*args,**kwargs)
        authoring.bank_correction('joined',{'text':'External author correction.','kind':'factual',
            'scope':'passage','anchor':{'file':'chapters/chapter-01.tex','line_start':2,'line_end':2}},repo_root=tmp_path)
        return result
    monkeypatch.setattr(literature,'bind',bind_with_external_correction)

    bound=bind(tmp_path,key,turn=turn)

    assert bound['action_receipt']['mutation_attribution']['exact'] is True
    assert bound['action_receipt']['context_refreshed'] is False
    with pytest.raises(ValueError,match='correction-unconsumed'):
        execute(tmp_path,'apply_revision',{'edits':[{'file':'chapters/chapter-01.tex','line_start':2,'line_end':2,
            'before':'First passage.','after':'First passage \\cite{FixtureSource}.','reason':'Cite source.'}]},turn)


def test_bind_receipt_does_not_bless_external_scientific_result_change(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    from laplace.research import corpus_ingest, literature
    from laplace.research import research_records
    result_file=manuscript/'measure.json';result_file.write_text('{"score":1}')
    status,record=research_records.record('joined',{'kind':'result','id':'result:owned',
        'result':'measure.json'},tmp_path);assert status==201
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'set-projection','node':'result:first',
        'value':{'result_bindings':[{'id':'result:owned','revision':record['record']['revision']}]}}).get('ok')
    selection={'files':['chapters/chapter-01.tex'],'line_start':2,'line_end':2}
    turn=seed_turn(tmp_path,source,selection,'WT-during-science')
    execute(tmp_path,'logical_plan',{'node':'result:first'},turn)
    execute(tmp_path,'research',{},turn)
    original_bind=literature.bind
    def bind_with_external_result(*args,**kwargs):
        result=original_bind(*args,**kwargs);result_file.write_text('{"score":2}');return result
    monkeypatch.setattr(literature,'bind',bind_with_external_result)

    bound=bind(tmp_path,key,turn=turn)

    attribution=bound['action_receipt']['mutation_attribution']
    assert attribution['exact'] is False and 'measure.json' in attribution['reason']
    assert bound['action_receipt']['context_refreshed'] is False
    with pytest.raises(ValueError,match='(argument, evidence|Consulted project evidence changed)'):
        execute(tmp_path,'apply_revision',{'edits':[{'file':'chapters/chapter-01.tex','line_start':2,'line_end':2,
            'before':'First passage.','after':'First passage \\cite{FixtureSource}.','reason':'Cite source.'}]},turn)


def _admit(root,project,turn,session):
    """An explicit synthetic admitted session and its one bound project turn, through the owner (the
    RD-RECOVERY-ADAPTERS pattern): failure custody exists only for a uniquely admitted project turn."""
    writing_records.bank(root,{'record':'writing-session','id':session,'project':project,'provider':'codex','model':'fixture','effort':'low'})
    writing_records.bank(root,{'record':'writing-turn','id':turn,'session_id':session,'project':project,'mode':'work'})


def _mcp_missing_operation(root,monkeypatch,payload):
    stream=io.StringIO('\n'.join(json.dumps(row) for row in [{'id':1,'method':'initialize'},{'id':2,'method':'tools/call','params':{'name':'laplace_project','arguments':{'operation':'missing-operation','payload':payload}}}])+'\n')
    output=io.StringIO();monkeypatch.setattr('sys.stdin',stream);monkeypatch.setattr('sys.stdout',output)
    tools.main(['--root',str(root),'--project','joined','--turn-id','WT-failed'])
    responses=[json.loads(line) for line in output.getvalue().splitlines()]
    path=root/'contract/talk.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []
    return responses,[row for row in rows if row.get('record')=='writing-tool-failure']


def test_mcp_operation_failure_is_receipted_once(tmp_path,monkeypatch):
    # M5 S3: the turn is explicitly admitted (the original fixture never banked one, and an unadmitted turn
    # correctly gets no custody row). The unknown operation stays refused; ONE canonical failure row keeps
    # the literal attempt, and the reply names it with its exact lazy read.
    _admit(tmp_path,'joined','WT-failed','WS-failed')
    attempt={'test':'failure','literal':'标题 "quoted" \\ \u0007'}
    responses,failures=_mcp_missing_operation(tmp_path,monkeypatch,attempt)
    assert responses[0]['result']['serverInfo']['name']=='laplace-project' and responses[1]['result']['isError']
    assert len(failures)==1 and failures[0]['operation']=='missing-operation' and failures[0]['turn_id']=='WT-failed'
    assert failures[0]['project']=='joined'
    assert writing_bodies.resolve_fields(failures[0],tmp_path)['payload']==attempt,'the literal attempt is retained'
    recovery=json.loads(responses[1]['result']['content'][0]['text'])
    assert recovery['failure_receipt']['row_id']==failures[0]['id']
    assert recovery['failure_read']=={'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+failures[0]['id']}}


@pytest.mark.parametrize('case',['unadmitted','wrong-project','duplicate'])
def test_mcp_operation_failure_never_borrows_custody(tmp_path,monkeypatch,case):
    if case=='wrong-project':_admit(tmp_path,'other','WT-failed','WS-failed')
    if case=='duplicate':
        _admit(tmp_path,'joined','WT-failed','WS-failed')
        writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-failed','session_id':'WS-failed','project':'joined','mode':'work'})
    journal=tmp_path/'contract/talk.jsonl'
    before=journal.read_bytes() if journal.is_file() else None
    responses,failures=_mcp_missing_operation(tmp_path,monkeypatch,{'test':'failure'})
    recovery=json.loads(responses[1]['result']['content'][0]['text'])
    assert responses[1]['result']['isError'] and failures==[]
    if case=='wrong-project':
        # Source admission refuses the foreign actual turn BEFORE failure
        # custody. This exact denial is not an arbitrary missing-field waiver.
        assert recovery=={'ok':False,
            'error':'Source execution refused: actual project turn unavailable',
            'source_allowance':{'state':'UNKNOWN','stop_reason':'actual project turn unavailable'}}
        assert journal.read_bytes()==before
        rows=[json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
        assert rows and all(row.get('project')=='other' for row in rows)
        assert all(row.get('record') in {'writing-session','writing-turn'} for row in rows)
        # Exact reply has no custody/body/reference key or borrowed turn proof.
        assert 'failure_receipt' not in recovery and 'source_basis' not in recovery
    else:
        assert recovery['failure_receipt']['row_id'] is None and 'unavailable' in recovery['failure_receipt']['note'].lower()


def test_scope_rejects_stale_own_result_and_recognises_declared_assumptions(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    from laplace.research import corpus_ingest
    from laplace.research import research_records
    (manuscript/'measure.json').write_text('{"n": 1}')
    _,record=research_records.record('joined',{'kind':'result','id':'run:own','result':'measure.json'},tmp_path)
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'set-projection','node':'result:first','value':{'result_bindings':[{'id':'run:own','revision':record['record']['revision']}]}}).get('ok')
    current=literature_support.for_node('joined','result:first',tmp_path)
    assert current['own_evidence'][0]['currentness']=='CURRENT'
    (manuscript/'measure.json').write_text('{"n": 2}')
    stale=literature_support.for_node('joined','result:first',tmp_path)
    assert any(gap['kind']=='own-evidence-stale' for gap in stale['gaps'])
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'add-node','node':'postulate:own','node_kind':'postulate','essence':'Assume a bounded domain.'}).get('ok')
    assumed=literature_support.for_node('joined','postulate:own',tmp_path)
    assert assumed['declared_role']=='DECLARED_ASSUMPTION' and not any(gap['kind']=='unsupported' for gap in assumed['gaps'])


def test_fetch_different_bytes_cannot_rebase_a_previously_read_source_body(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    turn=seed_turn(tmp_path,source,{'files':['chapters/chapter-01.tex'],'line_start':2,'line_end':2},'WT-fetch')
    execute(tmp_path,'source',{'files':['chapters/chapter-01.tex']},turn)
    previous=execute(tmp_path,'reference_text',{'key':key},turn)
    before=json.loads((manuscript/'references.json').read_text())
    operations._execute(tmp_path,'joined','work','reference_text',{'key':key})
    assert json.loads((manuscript/'references.json').read_text())==before
    monkeypatch.setattr(literature,'_download',lambda url:(b'A different accessible full text, with a different conclusion.\n','text/plain',url))
    execute(tmp_path,'reference_fetch',{'key':key,'url':'https://example.org/fulltext.txt'},turn)
    proposal={'edits':[{'file':'chapters/chapter-01.tex','line_start':2,'line_end':2,'before':'First passage.',
                       'after':'First passage \\cite{FixtureSource}.','reason':'Place an inspected citation.'}]}
    with pytest.raises(ValueError,match='(Consulted project evidence changed|argument, evidence)'):
        execute(tmp_path,'apply_revision',proposal,turn)
    current=execute(tmp_path,'reference_text',{'key':key},turn)
    assert current['reading_receipt']['source_sha256']!=previous['reading_receipt']['source_sha256']
    assert 'different conclusion' in current['text']


@pytest.mark.parametrize('projection_error',[None,OSError,ValueError])
def test_import_before_bibliography_and_one_bind_materializes_existing_owner(tmp_path,monkeypatch,projection_error):
    from laplace.research import references_surface, literature
    from laplace.manuscript import manuscript_source, review_surface
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    main=tmp_path/source['root'];main.write_text(main.read_text().replace('\\bibliography{refs}',''))
    materialize = literature._materialize_locked
    mirror = review_surface.mirror_source_changes
    def leased(*args, **kwargs):
        assert manuscript_source.source_mutation_active()
        with manuscript_source.source_mutation([main, manuscript/'refs.bib']):
            pass
        return materialize(*args, **kwargs)
    def released(*args, **kwargs):
        assert not manuscript_source.source_mutation_active()
        if projection_error:raise projection_error('controlled optional projection failure')
        return mirror(*args, **kwargs)
    monkeypatch.setattr(literature, '_materialize_locked', leased)
    monkeypatch.setattr(review_surface, 'mirror_source_changes', released)
    second=tmp_path/'second.txt';second.write_text('The second source provides a bounded supporting statement.\n')
    imported=execute(tmp_path,'literature_import',{'metadata':{'title':'Second source','creators':['Another Author'],'year':'2026'},
        'provenance':{'description':'Second explicit fixture source','path':str(second)},'citekey':'SecondSource'})
    assert imported['association']['bibliography_state']=='PENDING'
    read=execute(tmp_path,'reference_text',{'key':imported['association']['key']})
    linked=execute(tmp_path,'literature_bind',{'key':imported['association']['key'],'claim_id':'result:first','relation':'supports','rationale':'A bounded supporting statement.',
        'reading_status':'partial','reading_id':read['reading_receipt']['id'],'evidence':{'locator':read['reading_receipt']['locator']}})
    assert linked['association']['bibliography_state']=='ATTACHED' and 'manuscript' in linked['effects']
    assert linked['source_effect']['state']=='COMMITTED' and linked['source_effect']['complete']
    for handle in linked['source_effect']['impact']['reads']:
        execute(tmp_path, handle['operation'], handle['payload'])
    assert '\\bibliography{refs}' in main.read_text()
    assert 'SecondSource' in (manuscript/'refs.bib').read_text()
    if projection_error:assert linked['plan_sync']['status']=='UNPROVED' and linked['plan_sync']['source_effect_retained']


# Acquired canonical sources must join through the same native owner, not a
# pre-created citation or an arbitrary same-byte location.
def _acquired_canonical(root, monkeypatch):
    from laplace.research import corpus_ingest
    manuscript, source, _, original = project(root, monkeypatch)
    key = 'ref:acquired-fixture'
    assert corpus_ingest.rewire_add(root, 'joined', {
        'kind':'add-node', 'node':key, 'node_kind':'citation',
        'essence':'A canonical source without an original local body.'}).get('ok')
    data = b'The first controlled claim holds only under the stated conditions.\nNo unrestricted generalisation is established.\n'
    monkeypatch.setattr(literature, '_download', lambda url:(data, 'text/plain', url))
    fetched = execute(root, 'reference_fetch', {'key':key, 'url':'https://example.invalid/synthetic.txt'})
    info = execute(root, 'reference_source', {'key':key})
    assert info['provider'] == 'canonical' and info['sources'] == []
    assert info['currentness'] == 'CURRENT'
    assert info['path'] == fetched['source_text']['path']
    read = execute(root, 'reference_text', {'key':key, 'limit':1000})
    return manuscript, key, info, read


def _bind_observed(root, key, read, **extra):
    return execute(root, 'literature_bind', {
        'key':key, 'claim_id':'result:first', 'relation':'supports',
        'rationale':'Only the controlled statement is used.', 'reading_status':'partial',
        'reading_id':read['reading_receipt']['id'],
        'evidence':{'locator':read['reading_receipt']['locator'],
                    'excerpt':'only under the stated conditions'}, **extra})


def test_canonical_join_acquired_native_read_bind_and_qualified_consumers(tmp_path, monkeypatch):
    manuscript, key, info, read = _acquired_canonical(tmp_path, monkeypatch)
    result = _bind_observed(tmp_path, key, read)
    assert result['association']['binding_state'] == 'BOUND'
    assert result['association']['reading_receipt'] == read['reading_receipt']
    assert result['support']['sources'][0]['qualification'] == 'PASSAGE_OBSERVED'
    assert execute(tmp_path,'concept',{'node':'result:first'})['source_support']['sources'][0]['qualification'] == 'PASSAGE_OBSERVED'
    assert execute(tmp_path,'literature_uses',{'claim_id':'result:first'})['uses'][0]['source_qualification'] == 'PASSAGE_OBSERVED'
    scope = execute(tmp_path,'literature_scope',{'node':'result:first'})
    assert scope['claims'][0]['sources'][0]['qualification'] == 'PASSAGE_OBSERVED'
    repeated = _bind_observed(tmp_path, key, read)
    assert repeated['canonical_source'] == result['canonical_source']
    net = literature_support.network('joined', tmp_path)
    assert len([r for r in net['relations'] if r.get('source')=='result:first'
                and r.get('target')==result['canonical_source']]) == 1
    # Publication is not scientific verification.
    assert result['support']['independent_verification'] == 'NOT_ASSERTED'


def test_canonical_join_same_bytes_not_registered_and_identity_hash_guards(tmp_path, monkeypatch):
    from laplace.research import mathematical_records as mr, corpus_ingest
    _, key, info, read = _acquired_canonical(tmp_path, monkeypatch)
    copy = tmp_path/'unregistered-copy.txt'
    copy.write_bytes(Path(info['path']).read_bytes())
    ref = {'reference_key':key,'path':str(copy),'sha256':info['sha256']}
    with pytest.raises(ValueError,match='registered source location'):
        mr.validate_bibliographic_reference('joined', ref, tmp_path)
    refused = corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'add-node','node':'cite:illicit',
        'node_kind':'citation','essence':'Must refuse','ref':ref})
    assert 'registered source location' in refused['error']
    assert 'cite:illicit' not in literature_support.network('joined',tmp_path)['nodes']
    with pytest.raises(ValueError,match='SHA-256 changed'):
        mr.validate_bibliographic_reference('joined',
            {'reference_key':key,'path':info['path'],'sha256':'0'*64},tmp_path)
    with pytest.raises(ValueError,match='existing reference identity'):
        mr.validate_bibliographic_reference('joined',
            {'reference_key':'ref:absent','path':info['path'],'sha256':info['sha256']},tmp_path)


@pytest.mark.parametrize('change',['source','claim','reading','text-proof'])
def test_canonical_join_old_source_claim_or_receipt_refuses(tmp_path, monkeypatch, change):
    from laplace.research import references_surface as rs
    manuscript, key, info, read = _acquired_canonical(tmp_path,monkeypatch)
    old_claim = literature_support.meaning_revision('joined','result:first',tmp_path)
    extra = {'claim_revision':old_claim}
    if change == 'source':
        Path(info['path']).write_text('A changed conclusion.\n')
    elif change == 'claim':
        state=concepts.state('joined',root=tmp_path)
        execute(tmp_path,'concept_change',{'operation':'edit_node','node':'result:first',
            'base_revision':state['revision'],'value':'A different stronger statement.'})
    elif change == 'reading':
        extra['reading_id']='READ-absent'
    else:
        rows=rs._load_associations(manuscript)
        for row in rows:
            for receipt in row.get('reading_observations') or []:
                if receipt['id']==read['reading_receipt']['id']:
                    receipt['text_sha256']='sha256:'+'0'*64
        rs._write_associations(manuscript,rows)
    with pytest.raises(ValueError,match='(current source passage|claim meaning changed|reading proof)'):
        _bind_observed(tmp_path,key,read,**extra)


def test_canonical_join_bound_support_reopens_on_acquired_or_claim_change(tmp_path, monkeypatch):
    _, key, info, read = _acquired_canonical(tmp_path,monkeypatch)
    linked=_bind_observed(tmp_path,key,read)
    assert linked['support']['sources'][0]['qualification']=='PASSAGE_OBSERVED'
    state=concepts.state('joined',root=tmp_path)
    execute(tmp_path,'concept_change',{'operation':'edit_node','node':'result:first',
        'base_revision':state['revision'],'value':'A different statement.'})
    assert literature_support.for_node('joined','result:first',tmp_path)['sources'][0]['qualification']=='CLAIM_CHANGED'
    Path(info['path']).write_text('Changed retained source bytes.\n')
    assert literature_support.for_node('joined','result:first',tmp_path)['sources'][0]['qualification']=='STALE'


def test_canonical_join_valid_alternative_survives_missing_default(tmp_path, monkeypatch):
    from laplace.research import mathematical_records as mr, corpus_ingest
    project(tmp_path,monkeypatch)
    first=tmp_path/'canonical-first.txt'; second=tmp_path/'canonical-second.txt'
    for file in (first,second):file.write_text('A bounded registered alternative.\n')
    key='ref:alternatives'
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'add-node','node':key,
        'node_kind':'citation','essence':'Registered alternatives','ref':[
            {'path':str(p.relative_to(tmp_path)),'line_start':1,'line_end':1}
            for p in (first,second)]}).get('ok')
    first.unlink()
    with pytest.raises(ValueError):literature.source_info('joined',key,tmp_path)
    ref={'reference_key':key,'path':str(second),'sha256':literature.rs._sha256_file(second)}
    mr.validate_bibliographic_reference('joined',ref,tmp_path)
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'add-node','node':'cite:valid-alternative',
        'node_kind':'citation','essence':'Use actual alternative','ref':ref}).get('ok')
    observed=execute(tmp_path,'reference_text',{'key':key,'source_index':1,'limit':1000})
    status,out=literature.bind('joined',{'key':key,'claim_id':'result:second',
        'claim_revision':literature_support.meaning_revision('joined','result:second',tmp_path),
        'relation':'method','rationale':'An original canonical alternative.',
        'reading_status':'partial','reading_id':observed['reading_receipt']['id'],
        'evidence':{'locator':observed['reading_receipt']['locator']}},tmp_path)
    assert status==200,out
    assert out['support']['sources'][0]['qualification']=='PASSAGE_OBSERVED'


def test_alias_native_bibliography_join_with_actual_external_build_diagnostic(tmp_path,monkeypatch):
    """Owner join proof is separate from a real external TeX capability probe.
    The READONLY alias build test still asserts actual build success."""
    import warnings
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    read=execute(tmp_path,'reference_text',{'key':'FixtureSource','limit':1000})
    linked=_bind_observed(tmp_path,'FixtureSource',read)
    assert linked['association']['key']==key
    assert linked['association']['binding_state']=='BOUND'
    assert linked['support']['sources'][0]['qualification']=='PASSAGE_OBSERVED'
    entry=execute(tmp_path,'references_attached',{'citekey':'FixtureSource'})
    assert entry['status']=='AVAILABLE' and entry['entries'][0]['complete']
    for alias in (key,'FixtureSource',linked['canonical_source']):
        assert execute(tmp_path,'reference_source',{'key':alias})['key']==key
    chapter=manuscript/'chapters/chapter-01.tex'
    chapter.write_text(chapter.read_text().replace('First passage.','First passage \\cite{FixtureSource}.'))
    for sid,heading in [('first','\\section{First claim}'),('second','\\section{Second claim}')]:
        assert bind_heading(tmp_path,sid,heading)['binding']['precision']=='EXACT_HEADING'
    attributed=execute(tmp_path,'literature_scope',{'node':'result:first'})
    uses=attributed['claims'][0]['sources'][0]['manuscript_uses']
    assert len(uses)==1 and uses[0]['claim_ids']==['result:first']
    assert uses[0]['section_ids']==['first']
    assert not any(g['kind']=='not-yet-cited' for g in attributed['gaps'])
    assert execute(tmp_path,'literature_uses',{'claim_id':'result:second'})['uses']==[]
    started=execute(tmp_path,'build',{})
    for _ in range(150):
        status=execute(tmp_path,'build_status',{})
        if not status.get('running'):break
        time.sleep(.1)
    diagnostic={'owner_join':'BOUND_AND_PASSAGE_OBSERVED','bibliography_entry':'COMPLETE',
        'build_started':started,'actual_build_status':status,
        'qualification':'Actual external build observation, NOT an assertion of successful TeX execution.'}
    # The qualified profile retains stdout/warnings, while scratch is removed.
    # Do not skip or weaken the independent READONLY real compilation assertion.
    warnings.warn('LITERATURE_NATIVE_JOIN_AND_TEX_BOUNDARY '+json.dumps(diagnostic,ensure_ascii=False),UserWarning)
