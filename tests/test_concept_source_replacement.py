"""Canonical locator repair uses the existing rewire owner and preserves science."""
import copy,hashlib,json,threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from laplace.research import concepts as cs, corpus_ingest, mathematical_records
from laplace.native import tools as writing_tools
from laplace.writing import operations
from test_concepts_surface import _nested_fixture,_change


def setup(root):
    manuscript=_nested_fixture(root)
    sources=root/'sources';sources.mkdir()
    source=sources/'original.tex'
    source.write_text('Source header.\n\\begin{lemma}\\label{lem:source}\nFor every x, x=x.\n\\end{lemma}\n\\begin{proof}Reflexivity.\\end{proof}\n')
    (root/'profiles').mkdir();(root/'profiles/writing_sources.json').write_text(json.dumps({'repositories':{'papers':'sources'}}))
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    old='papers:original.tex#sha256='+digest
    # Historical malformed row: new creation now rejects this checksum fragment.
    from laplace.pipeline.ledger import append_jsonl
    append_jsonl(corpus_ingest._rewire_path(root,'graph',ensure_dir=True),{'id':'RW-historical-source','kind':'add-node','node':'lemma:repair','node_kind':'lemma','essence':'A provisional fixture lemma.','ref':old,'status':'open','by':'historical-fixture'})
    _change(root,operation='set_mathematics',node='lemma:repair',value={'statement_tex':'x=x','domain':'A stated fixture domain','assumptions':[],'proof':{'text':'Authored fixture proof.'}})
    _change(root,operation='set_status',node='lemma:repair',value='exploratory')
    return source,digest,old


def repair(root,locators):
    return writing_tools.execute(root,'graph','work','concept_change',{'operation':'set_source','node':'lemma:repair',
        'base_revision':cs.state('graph','lemma:repair',root=root)['revision'],'value':locators})


def test_replacement_resolves_exact_source_and_preserves_meaning_proof_status_history(tmp_path):
    source,digest,old=setup(tmp_path)
    before=cs.state('graph','lemma:repair',root=tmp_path)
    assert '#sha256 fragment' in before['source_locations'][0]['error']
    locator={'repository':'papers','path':'original.tex','label':'lem:source','sha256':'sha256:'+digest}
    original=source.read_bytes()
    changed=repair(tmp_path,[locator]);after=cs.state('graph','lemma:repair',root=tmp_path)
    assert changed['record']['kind']=='set-source'
    assert after['focus']['summary']==before['focus']['summary']
    assert after['focus']['status']=='exploratory'
    assert after['mathematical_record']['authored']==before['mathematical_record']['authored']
    assert after['source_locations'][0]['status']=='READ'
    assert after['source_locations'][0]['sha256']==digest
    assert after['source_locations'][0]['line_start']==2
    assert after['content_revision']!=before['content_revision']
    assert source.read_bytes()==original
    event=next(row for row in cs.history('graph','lemma:repair',root=tmp_path)['history'] if row['operation']['id']==changed['record']['id'])
    assert event['subject']['changes']==[{'field':'source_refs','before':[old],'after':[locator]}]
    assert writing_tools.execute(tmp_path,'graph','work','concept',{'node':'lemma:repair'})['source_locations'][0]['status']=='READ'
    repair(tmp_path,[])
    cleared=cs.state('graph','lemma:repair',root=tmp_path)
    assert cleared['focus']['source']==[]
    assert cleared['mathematical_record']['authored']==before['mathematical_record']['authored']


def test_bounded_concept_context_carries_science_and_locators_once(tmp_path):
    _source,_digest,old=setup(tmp_path)
    full=cs.state('graph','lemma:repair',root=tmp_path)
    value=cs.context('graph','lemma:repair',root=tmp_path)
    encoded=json.dumps(value,ensure_ascii=False)

    assert value['revision']==full['revision']
    assert full['mutation_revision']==full['content_revision']
    assert value['mutation_revision']==full['content_revision']
    assert value['mathematical_record']['proof']['text']=='Authored fixture proof.'
    assert value['mathematical_record']['assumptions']==[]
    assert value['mathematical_record']['qualification']==full['mathematical_record']['qualification']
    assert 'mathematics' not in value['node']['projection']
    assert 'source' not in value['node']
    assert 'source_locations' not in value['mathematical_record']
    assert value['source_locations'][0]['reference']==old
    assert all('statement_tex' not in row and 'proof_text' not in row and 'content' not in row
               for row in value['source_locations'])
    assert value['read_routes']['source_body']['payload']['source_index']=='<source_index>'
    assert encoded.count('Authored fixture proof.')==1


def test_node_local_guard_ignores_unrelated_edits_but_refuses_same_node_and_source_changes(tmp_path):
    source,digest,_old=setup(tmp_path)
    _change(tmp_path,operation='add_node',node='support:unrelated',node_kind='support',
            essence='Unrelated support')
    local=cs.context('graph','lemma:repair',root=tmp_path)['mutation_revision']
    _change(tmp_path,operation='edit_node',node='support:unrelated',value='Changed elsewhere')
    locator={'repository':'papers','path':'original.tex','label':'lem:source','sha256':digest}

    status,saved=cs.change({'project':'graph','operation':'set_source','node':'lemma:repair',
        'mutation_revision':local,'value':[locator]},root=tmp_path)
    assert status==200,saved

    stale=cs.context('graph','lemma:repair',root=tmp_path)['mutation_revision']
    _change(tmp_path,operation='edit_node',node='lemma:repair',value='Relevant meaning changed')
    before=corpus_ingest.rewire_list(tmp_path,'graph')
    status,conflict=cs.change({'project':'graph','operation':'set_source','node':'lemma:repair',
        'mutation_revision':stale,'value':[locator]},root=tmp_path)
    assert status==409 and conflict['error']=='mutation revision conflict'
    assert conflict['mutation_revision']==cs.context('graph','lemma:repair',root=tmp_path)['mutation_revision']
    assert corpus_ingest.rewire_list(tmp_path,'graph')==before

    source_guard=cs.context('graph','lemma:repair',root=tmp_path)['mutation_revision']
    source.write_text(source.read_text().replace('Reflexivity.','Source changed.'))
    before=corpus_ingest.rewire_list(tmp_path,'graph')
    status,conflict=cs.change({'project':'graph','operation':'edit_node','node':'lemma:repair',
        'mutation_revision':source_guard,'value':'Must not land over changed source'},root=tmp_path)
    assert status==409 and conflict['mutation_revision']!=source_guard
    assert corpus_ingest.rewire_list(tmp_path,'graph')==before


def test_node_local_guard_includes_direct_prerequisite_content(tmp_path):
    setup(tmp_path)
    _change(tmp_path,operation='add_node',node='def:required',node_kind='definition',
            essence='Required definition')
    _change(tmp_path,operation='add_edge',node='lemma:repair',target='def:required',
            rel='prerequisite',rationale='The lemma requires this definition.')
    value=cs.context('graph','lemma:repair',root=tmp_path)
    assert value['prerequisites'][0]['id']=='def:required'
    guard=value['mutation_revision']
    _change(tmp_path,operation='edit_node',node='def:required',value='Changed required definition')
    before=corpus_ingest.rewire_list(tmp_path,'graph')

    status,conflict=cs.change({'project':'graph','operation':'edit_node','node':'lemma:repair',
        'mutation_revision':guard,'value':'Must reread prerequisite'},root=tmp_path)

    assert status==409 and conflict['mutation_revision']!=guard
    assert corpus_ingest.rewire_list(tmp_path,'graph')==before


def test_same_node_concurrent_mutations_recheck_guard_inside_append_lock(tmp_path,monkeypatch):
    setup(tmp_path)
    guard=cs.context('graph','lemma:repair',root=tmp_path)['mutation_revision']
    original=corpus_ingest.rewire_add;barrier=threading.Barrier(2)
    def synchronized(*args,**kwargs):
        barrier.wait(timeout=5)
        return original(*args,**kwargs)
    monkeypatch.setattr(corpus_ingest,'rewire_add',synchronized)
    payload=lambda text:{'project':'graph','operation':'edit_node','node':'lemma:repair',
                         'mutation_revision':guard,'value':text}

    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda text:cs.change(payload(text),root=tmp_path),('First','Second')))

    assert sorted(status for status,_ in results)==[200,409]
    assert sum(row.get('kind')=='edit-essence' and row.get('value') in {'First','Second'}
               for row in corpus_ingest.rewire_list(tmp_path,'graph'))==1


def test_concept_conflict_returns_current_guards_and_exact_help_prefers_local_revision(tmp_path):
    setup(tmp_path)
    current=cs.context('graph','lemma:repair',root=tmp_path)
    _change(tmp_path,operation='edit_node',node='lemma:repair',value='Changed before retry')
    payload={'operation':'edit_node','node':'lemma:repair',
             'mutation_revision':current['mutation_revision'],'value':'Stale edit'}
    with pytest.raises(operations.OwnerError) as caught:
        writing_tools.execute(tmp_path,'graph','work','concept_change',payload)
    details=caught.value.details
    assert details['error']=='mutation revision conflict'
    assert details['revision']==cs.state('graph',root=tmp_path)['revision']
    assert details['mutation_revision']==cs.context('graph','lemma:repair',root=tmp_path)['mutation_revision']
    recovery=writing_tools.failure_response(tmp_path,'graph','work','concept_change',payload,caught.value)
    assert recovery['mutation_revision']==details['mutation_revision']
    assert recovery['recovery']=={'operation':'concept','payload':{'node':'lemma:repair'}}
    help_value=writing_tools.execute(tmp_path,'graph','work','help',{'operation':'concept_change'})
    # The owner still publishes the guard; help no longer copies the owner's contract.
    from laplace.native import declarations as writing_declarations
    assert 'mutation_revision' in cs.operation_contract()['revision_guards']
    # The example is generated, so instead of a literal "COPY ... EXACTLY" the guard field
    # carries this project's live token, or the read that would obtain it.
    example=writing_declarations.generated_example('concept_change',variant='set_source',
                                                   project='graph',root=tmp_path)
    guard=example['mutation_revision']
    assert guard.startswith('rev:concept-node:') or 'concept {node}' in guard, guard
    row=next(r for r in help_value['action']['expected'] if r['home_kind']=='concept-node')
    assert row['read']=='concept {node} -> content_revision'


def test_global_guard_mistake_recovers_the_selected_node_not_the_project_root(tmp_path):
    setup(tmp_path)
    focused=cs.context('graph','lemma:repair',root=tmp_path)
    assert focused['content_revision']==focused['mutation_revision']
    payload={'project':'graph','operation':'edit_node','node':'lemma:repair',
             'base_revision':focused['mutation_revision'],'value':'Precisely corrected'}
    status,conflict=cs.change(payload,root=tmp_path)
    assert status==409
    assert conflict['mutation_revision']==focused['mutation_revision']
    payload.pop('base_revision');payload['mutation_revision']=conflict['mutation_revision']
    status,changed=cs.change(payload,root=tmp_path)
    assert status==200 and changed['state']['focus']['summary']=='Precisely corrected'


@pytest.mark.parametrize('locators,reason',[
    ([{'repository':'papers','path':'original.tex','line_start':2,'line_end':4,'sha256':'0'*64}],'SHA-256 changed'),
    ([{'repository':'papers','path':'original.tex','label':'sha256=bad'}],'#sha256 fragment'),
    ([{'repository':'papers','path':'original.tex','line_start':100,'line_end':101}],'outside the file'),
    ([{'repository':'papers','path':'original.tex'}],'real TeX label or exact'),
    ([{'repository':'papers','path':'original.tex','line_start':2}],'supplied together'),
    ([{'repository':'papers','path':'original.tex','line_start':2,'line_end':4,'checksum':'bad'}],'unknown fields'),
    (['papers:original.tex#sha256=bad'],'must be object'),
])
def test_invalid_repairs_do_not_append_or_guess_source(tmp_path,locators,reason):
    setup(tmp_path);before=corpus_ingest.rewire_list(tmp_path,'graph')
    with pytest.raises(ValueError,match=reason):repair(tmp_path,locators)
    assert corpus_ingest.rewire_list(tmp_path,'graph')==before


@pytest.mark.parametrize('pin_length',[38,39])
def test_malformed_proposed_pin_names_input_and_preserves_valid_authored_mathematics(tmp_path,pin_length):
    source,digest,_old=setup(tmp_path)
    locator={'repository':'papers','path':'original.tex','line_start':1,'line_end':2,'sha256':digest}
    authored=cs.state('graph','lemma:repair',root=tmp_path)['mathematical_record']['authored']
    _change(tmp_path,operation='set_mathematics',node='lemma:repair',value={**authored,'sources':[locator]})
    before=cs.state('graph','lemma:repair',root=tmp_path)
    history=corpus_ingest.rewire_list(tmp_path,'graph')
    original=source.read_bytes()
    with pytest.raises(ValueError) as caught:
        repair(tmp_path,[{**locator,'sha256':digest[:pin_length]}])
    message=str(caught.value)
    assert 'set_source.value[0].sha256' in message
    assert f'proposed pin length is {pin_length}' in message
    assert 'No existing record changed' in message
    assert 'mathematics.sources' not in message
    assert corpus_ingest.rewire_list(tmp_path,'graph')==history
    assert cs.state('graph','lemma:repair',root=tmp_path)['mathematical_record']['authored']==before['mathematical_record']['authored']
    assert source.read_bytes()==original


@pytest.mark.parametrize('operation,field',[('concept_change','ref'),('logical_plan_change','source_ref')])
def test_creation_pin_diagnostic_names_the_actual_caller_field(tmp_path,operation,field):
    _source,digest,_old=setup(tmp_path)
    locator={'repository':'papers','path':'original.tex','line_start':1,'line_end':2,'sha256':digest[:39]}
    if operation=='concept_change':
        payload={'operation':'add_node','node':'lemma:new','node_kind':'lemma','essence':'Unwritten fixture claim',
                 'base_revision':cs.state('graph',root=tmp_path)['revision']}
    else:
        payload={'operation':'add_object','node':'lemma:new','kind':'lemma','meaning':'Unwritten fixture claim',
                 'base_revision':cs.logical_plan('graph',root=tmp_path)['revision']}
    before=corpus_ingest.rewire_list(tmp_path,'graph')
    with pytest.raises(ValueError) as caught:
        writing_tools.execute(tmp_path,'graph','work',operation,{**payload,field:locator})
    assert f'{field}.sha256' in str(caught.value)
    assert 'proposed pin length is 39' in str(caught.value)
    assert 'No existing record changed' in str(caught.value)
    assert corpus_ingest.rewire_list(tmp_path,'graph')==before


def test_generic_concept_source_location_propagates_without_a_math_record(tmp_path):
    source,digest,old=setup(tmp_path)
    _change(tmp_path,operation='add_node',node='support:notes',node_kind='support',essence='Fixture source audit')
    current=cs.state('graph','support:notes',root=tmp_path)
    status,value=cs.change({'project':'graph','operation':'set_source','node':'support:notes','base_revision':current['revision'],
        'value':[{'repository':'papers','path':'original.tex','line_start':1,'line_end':1,'sha256':digest}]},root=tmp_path)
    assert status==200,value
    assert value['state']['source_locations'][0]['excerpt']=='Source header.\n'
    assert 'mathematical_record' not in value['state']


def test_direct_rewire_door_cannot_bypass_source_validation(tmp_path):
    setup(tmp_path)
    result=corpus_ingest.rewire_add(tmp_path,'graph',{'kind':'set-source','node':'lemma:repair','value':[{'path':'missing.tex','line_start':1,'line_end':2}]})
    assert result.get('error')


def test_source_replacement_stales_old_canonical_passage_and_does_not_refresh_it(tmp_path):
    from laplace.research import literature_support
    from laplace.writing import records as writing_records
    from laplace.writing import session_reads
    from laplace.pipeline import authoring
    source,digest,old=setup(tmp_path)
    other=source.with_name('replacement.tex');other.write_text('Different source content.\n')
    _change(tmp_path,operation='add_node',node='cite:source',node_kind='citation',essence='Fixture source',ref={'repository':'papers','path':'original.tex','line_start':1,'line_end':1})
    context=authoring.build_context('graph',{'files':['main.tex']},repo_root=tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-source','project':'graph','provider':'codex','model':'not-called','effort':'low'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-source','session_id':'WS-source','project':'graph','mode':'work','selection':{'files':['main.tex']},'context_id':context['context_id'],'dependencies':context['dependencies'],'document':context['document']})
    read=writing_tools.execute(tmp_path,'graph','work','reference_text',{'key':'cite:source'},'WT-source')
    record=session_reads._records(tmp_path)['turns']['WT-source']
    old_read=next(item for item in record['tool_reads'].values() if item['operation']=='reference_text')
    _change(tmp_path,operation='add_edge',node='lemma:repair',target='cite:source',rel='support',rationale='Fixture source')
    from laplace.research import literature, references_surface
    m=references_surface._manuscript('graph',tmp_path);rows=references_surface._load_associations(m)
    rows.append({**rows[0],'claim_id':'lemma:repair','binding_state':'BOUND','reading_receipt':read['reading_receipt'],'claim_revision':literature_support.meaning_revision('graph','lemma:repair',tmp_path)})
    references_surface._write_associations(m,rows)
    current=cs.state('graph','cite:source',root=tmp_path)
    writing_tools.execute(tmp_path,'graph','work','concept_change',{'operation':'set_source','node':'cite:source','base_revision':current['revision'],'value':[{'repository':'papers','path':'replacement.tex','line_start':1,'line_end':1}]},'WT-source')
    after=session_reads._records(tmp_path)['turns']['WT-source']
    kept=next(item for item in after['tool_reads'].values() if item['operation']=='reference_text')
    assert kept['output_sha256']==old_read['output_sha256']
    assert literature_support.for_node('graph','lemma:repair',tmp_path)['sources'][0]['qualification']=='STALE'


def test_optional_scientific_title_uses_existing_projection_owner(tmp_path):
    setup(tmp_path);before=cs.state('graph','lemma:repair',root=tmp_path)
    _change(tmp_path,operation='set_projection',node='lemma:repair',value={'title':'A bounded identity'})
    after=cs.state('graph','lemma:repair',root=tmp_path)
    assert after['focus']['title']=='A bounded identity'
    assert after['focus']['summary']==before['focus']['summary']
    assert after['mathematical_record']['authored']==before['mathematical_record']['authored']
    assert next(row for row in cs.catalog('graph',root=tmp_path)['items'] if row['id']=='lemma:repair')['title']=='A bounded identity'
    assert next(row for row in cs.logical_plan('graph',root=tmp_path)['objects'] if row['id']=='lemma:repair')['title']=='A bounded identity'


def test_creation_accepts_structured_sources_and_refuses_checksum_fragments(tmp_path):
    source,digest,old=setup(tmp_path)
    locator={'repository':'papers','path':'original.tex','line_start':2,'line_end':5,'sha256':digest}
    for ident,reference in [('result:structured',locator),('result:multiple',[locator])]:
        revision=cs.logical_plan('graph',root=tmp_path)['revision']
        status,result=cs.logical_plan_change({'project':'graph','operation':'add_object','base_revision':revision,'node':ident,'kind':'result','meaning':'A fixture interpretation.','source_ref':reference},root=tmp_path)
        assert status==200,result
        assert cs.state('graph',ident,root=tmp_path)['source_locations'][0]['status']=='READ'
    before=corpus_ingest.rewire_list(tmp_path,'graph')
    revision=cs.logical_plan('graph',root=tmp_path)['revision']
    status,result=cs.logical_plan_change({'project':'graph','operation':'add_object','base_revision':revision,'node':'result:bad-new','kind':'result','meaning':'Not written.','source_ref':old},root=tmp_path)
    assert status==422 and 'structured source_ref/ref' in result['error']
    assert corpus_ingest.rewire_list(tmp_path,'graph')==before
    current=cs.state('graph',root=tmp_path)
    status,result=cs.change({'project':'graph','operation':'add_node','node':'result:bad-digest','node_kind':'result','essence':'Not written.','base_revision':current['revision'],'ref':{**locator,'sha256':'0'*64}},root=tmp_path)
    assert status==422 and 'SHA-256 changed' in result['error']
    assert corpus_ingest.rewire_list(tmp_path,'graph')==before
    _change(tmp_path,operation='add_node',node='support:citation-id',node_kind='support',essence='Citation identity retained',ref='https://doi.org/10.1234/example')
    _change(tmp_path,operation='add_node',node='support:legacy-label',node_kind='support',essence='Legacy label retained',ref='papers:original.tex#lem:source')
    assert cs.state('graph','support:legacy-label',root=tmp_path)['source_locations'][0]['status']=='READ'


def test_bibliographic_provenance_is_distinct_from_text_selector_validation(tmp_path,monkeypatch):
    from test_literature_joined_workflow import project
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    reference={'reference_key':key,'path':str(original),'sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'locator':'characters 0–50'}
    mathematical_records.validate_created_source_reference('joined',reference,tmp_path)
    for invalid in ({**reference,'line_start':1}, {**reference,'mystery':True}, {**reference,'sha256':'0'*64}):
        with pytest.raises(ValueError):mathematical_records.validate_created_source_reference('joined',invalid,tmp_path)
    other=tmp_path/'unregistered.txt';other.write_text('This file does not belong to the reference identity.')
    with pytest.raises(ValueError,match='registered source location'):
        mathematical_records.validate_created_source_reference('joined',{**reference,'path':str(other),'sha256':hashlib.sha256(other.read_bytes()).hexdigest()},tmp_path)


def test_admitted_citation_source_replacement_preserves_identity_binding_and_compiled_use(tmp_path,monkeypatch):
    import shutil,time
    from test_literature_joined_workflow import project,execute,bind
    from laplace.research import references_surface, literature_support, literature
    if not shutil.which('latexmk'):pytest.skip('latexmk unavailable')
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    ident='cite:already-admitted';digest=hashlib.sha256(original.read_bytes()).hexdigest()
    reference={'reference_key':key,'citekey':'FixtureSource','path':str(original),'sha256':digest,'locator':'characters 0–50'}
    made=corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'add-node','node':ident,'node_kind':'citation','essence':'A registered original source','ref':reference})
    assert made.get('ok'),made
    execute(tmp_path,'literature_import',{'metadata':{'title':'Controlled source','creators':['Fixture Author'],'year':'2026','item_type':'unpublished'},
        'provenance':{'description':'Explicit existing-source mapping','path':str(original)},'canonical_id':ident})
    linked=bind(tmp_path,key);assert linked['canonical_source']==ident
    before=copy.deepcopy(references_surface._load_associations(manuscript))
    # The old admitted format could carry its identity only in ref. Preserve it
    # when replacing that locator, without migrating or altering its binding.
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'set-projection','node':ident,'value':{'bibliography':{}}}).get('ok')
    current=cs.state('joined',ident,root=tmp_path)
    changed=execute(tmp_path,'concept_change',{'operation':'set_source','node':ident,'base_revision':current['revision'],
        'value':[{'path':str(original.relative_to(tmp_path)),'line_start':1,'line_end':2,'sha256':digest}]})
    assert changed['ok']
    node=literature_support.network('joined',tmp_path)['nodes'][ident]
    assert node['projection']['bibliography']['reference_key']==key
    assert node['projection']['bibliography']['citekey']=='FixtureSource'
    assert references_surface._load_associations(manuscript)==before
    assert literature.resolve_item('joined',ident,tmp_path)[1]['key']==key
    support=literature_support.for_node('joined','result:first',tmp_path)['sources'][0]
    assert support['source_id']==ident and support['key']==key and support['citekey']=='FixtureSource'
    assert support['qualification']=='PASSAGE_OBSERVED'
    chapter=manuscript/'chapters/chapter-01.tex';chapter.write_text(chapter.read_text().replace('First passage.','First passage \\cite{FixtureSource}.'))
    execute(tmp_path,'build',{})
    for _ in range(150):
        state=execute(tmp_path,'build_status',{})
        if not state.get('running'):break
        time.sleep(.1)
    assert state.get('ok') and state.get('fresh'),state
    scope=execute(tmp_path,'literature_scope',{'node':'result:first'})
    assert scope['ready_for_completion'],scope['gaps']
    assert 'FixtureSource' in scope['bibliography']['rendered_keys']
