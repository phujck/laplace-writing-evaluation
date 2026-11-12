"""Published visual examples cross the real writer gateway and canonical owners."""
import copy
import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
import threading

import jsonschema
import pytest

from laplace.research import visuals_surface
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools, declarations as writing_declarations
from laplace.research import research_runs
from laplace.research import research_observation
from laplace.research import research_catalogue
from laplace.writing import operations
from laplace.pipeline import registry, visual_production as vp


def project(root):
    status, created = writing_projects.create({'name':'visual-lab','title':'Visual Lab','kind':'paper'}, root)
    assert status == 201, created
    record = registry.resolve('visual-lab', repo_root=root)
    base = record.path(record.project_dir, root)
    manuscript = record.path(record.manuscript_dir, root)
    (base/'data').mkdir()
    (base/'data/observations.csv').write_text('input,response\n1,2\n2,4\n')
    (manuscript/'observation.json').write_text('{"slope":2,"qualification":"fixture only"}\n')
    writing_tools.execute(root,'visual-lab','work','research_record',{
        'kind':'result','id':'result:observation','result':'observation.json',
        'summary':'Synthetic fixture observation only; no empirical inference.'})
    return base, manuscript, created


def call(root, operation, payload):
    return writing_tools.execute(root,'visual-lab','work',operation,payload)


def help_for(root, operation):
    """The complete help a consumer assembles: the default plus every moved value through its exact
    declared section read (D2 help sections; `examples` is one of them)."""
    action = call(root,'help',{'operation':operation})['action']
    for name in (action.get('sections') or {}).get('chars', {}):
        action[name] = call(root,'help',{'operation':operation,'section':name})['action']['value']
    return action


@pytest.mark.parametrize(('transport', 'wrong_kind'), [
    ('named', False), ('verb', False), ('legacy-to-verb', False),
    ('named', True), ('verb', True),
])
def test_visual_identity_scope_survives_every_public_writer_path(tmp_path, transport, wrong_kind):
    from laplace.core import grammar as g
    from laplace.native import verbs
    _base, manuscript, created = project(tmp_path)
    spec = copy.deepcopy(help_for(tmp_path, 'visual_create')['examples']['plot'])
    saved = call(tmp_path, 'visual_create', spec)
    ident = saved['spec']['id']
    call(tmp_path, 'visual_render', {'id': ident})
    file = created['source']['root']
    source = call(tmp_path, 'source', {'files': [file]})
    token = next(g.parse(value) for value in source['sources'][0]['identities'].values()
                 if g.parse(value).kind == 'source-file')
    payload = {'id': ident, 'file': file}
    route = verbs.route_for_operation('visual_place', payload)
    target = verbs.target_for('visual-lab', route.concept, payload)
    expected = str(g.mint('visual-spec', target, token.digest)) if wrong_kind else str(token)
    before = {p: p.read_bytes() if p.exists() else None for p in
              [tmp_path / file, manuscript / 'manuscript_spec.json', manuscript / 'figure_manifest.json']}
    if transport == 'named':
        try:
            result = call(tmp_path, 'visual_place', {**payload, 'expected': [expected]})
        except operations.OwnerError as error:
            result = {'ok': False, **error.details}
        except writing_declarations.PayloadAdmissionError as error:
            result = error.response()
    elif transport == 'verb':
        result = writing_tools.request(tmp_path, 'visual-lab', 'work', g.Request(
            verb=route.verb, concept=route.concept, target=target,
            expected=(expected,), payload=payload))
    else:
        _route, request = verbs.from_owner_call('visual_place',
            {**payload, 'base_revision': token.digest}, project='visual-lab', root=tmp_path)
        result = writing_tools.request(tmp_path, 'visual-lab', 'work', request)
    if wrong_kind:
        assert result.get('ok') is False, result
        assert result['refused']['kind'] == 'shape'
        assert 'home not declared' in result['error']
        assert {p: p.read_bytes() if p.exists() else None for p in before} == before
    else:
        assert result.get('ok') is not False, result
        assert (tmp_path / file).read_bytes() != before[tmp_path / file]
        assert ('\\label{fig:' + ident + '}') in (tmp_path / file).read_text()


def test_placement_guard_failure_returns_exact_source_field_route_and_recovers(tmp_path):
    _base, manuscript, created = project(tmp_path)
    spec = copy.deepcopy(help_for(tmp_path, 'visual_create')['examples']['plot'])
    saved = call(tmp_path, 'visual_create', spec)
    ident = saved['spec']['id']
    call(tmp_path, 'visual_render', {'id': ident})
    file = created['source']['root']
    source = call(tmp_path, 'source', {'files': [file]})
    wrong = {'id': ident, 'file': file, 'expected_source_revision': source['source_revision']}
    before = (tmp_path / file).read_bytes()
    with pytest.raises(operations.OwnerError) as error:
        call(tmp_path, 'visual_place', wrong)
    failure = writing_tools.failure_response(tmp_path, 'visual-lab', 'work', 'visual_place', wrong, error.value)
    assert failure['recovery']['guard_fields']['expected_source_revision'] == 'source.document.revision'
    assert failure['source_revision'] == source['document']['revision']
    assert (tmp_path / file).read_bytes() == before
    fresh = call(tmp_path, **failure['recovery']['read'])
    placed = call(tmp_path, 'visual_place', {'id': ident, 'file': file,
        'expected_source_revision': fresh['document']['revision'],
        # `raw_file_sha256` was deleted: a second name for `sha256`, the one name the
        # `source-file` home keeps.  The refusal's guard_fields now names that one.
        'base_revision': fresh['sources'][0]['sha256']})
    assert placed['repo_file'] == file
    assert ('\\label{fig:' + ident + '}') in (tmp_path / file).read_text()


def supervised_artifact_run(base,manuscript):
    run_id='run-supervised-figure';runs=manuscript/'research_runs';runs.mkdir(exist_ok=True)
    root=next(path for path in (base,*base.parents) if (path/'registry_projects.json').is_file())
    producer=base/'numerics/figures.py';producer.parent.mkdir();producer.write_text('print("fixture")\n')
    writing_tools.execute(root,'visual-lab','work','research_producer',{
        'id':'figure-producer','executable':'numerics/figures.py','scope':'project',
        'modes':['full'],'allowed_args':{},'dependencies':[],'timeout_seconds':30})
    data=runs/(run_id+'-data');data.mkdir()
    sources={}
    for suffix,content in (('pdf',b'%PDF-supervised'),('svg',b'<svg>supervised</svg>'),
                           ('png',b'PNG-supervised')):
        path=data/('panel.'+suffix);path.write_bytes(content);sources[suffix]=path
    result=runs/(run_id+'.result.json')
    result.write_text(json.dumps({'artifacts':[{'id':'panel',**{key:str(path) for key,path in sources.items()}}]}))
    digest=hashlib.sha256(result.read_bytes()).hexdigest()
    declared,_error=research_runs._producer(manuscript,'figure-producer')
    producer_identity=research_observation._digest(producer)
    producer_identity.update(path='numerics/figures.py',scope='project')
    (runs/(run_id+'.json')).write_text(json.dumps({'id':run_id,'state':'RUNNING','producer_id':'figure-producer',
        'producer_path':'numerics/figures.py','producer_base':str(base),
        'result_path':'research_runs/'+result.name,'result_absolute':str(result),
        'provenance':{'producer':producer_identity,'dependencies':[],
                      'producer_config':research_observation._object_digest(declared)}}))
    (runs/(run_id+'.receipt.json')).write_text(json.dumps({'state':'COMPLETE','exit_code':0,
        'result_sha256':digest,'finished_at':1.0}))
    return run_id,sources


def test_all_visual_examples_match_published_schema_and_owner_requirements(tmp_path):
    # visual_create has five variants, so help serves the variant INDEX and one variant on
    # request; each owner-published example is validated against ITS variant's schema.
    contract=help_for(tmp_path,'visual_create')
    assert 'input' not in contract
    assert set(contract['examples'])<=set(contract['variants'])
    for name,payload in contract['examples'].items():
        schema=call(tmp_path,'help',{'operation':'visual_create','variant':name})['action']['input']
        jsonschema.validate(payload,schema)
        assert vp.validate(payload['spec']) is None
        if name=='tikz':assert vp._tikz_snippet(tmp_path,payload['spec'])[0]==payload['spec']['tikz']
    for operation in ('visual_render','visual_place'):
        detail=help_for(tmp_path,operation)
        jsonschema.validate(detail['example'],detail['input'])
        # `preconditions` is now `rules`: every clause attached to the field it constrains,
        # with the file:line that enforces it.
        assert detail['rules'] and detail['outputs'] and detail['recoverable_errors']


def test_completed_supervised_run_artifact_is_adopted_hashed_bound_and_placed_without_redraw(tmp_path):
    base,manuscript,created=project(tmp_path);run_id,sources=supervised_artifact_run(base,manuscript)
    template=help_for(tmp_path,'visual_create')['examples']['artifact']['spec']
    spec={**template,'id':'adopted-panel','run_id':run_id,'artifact_id':'panel',
          'caption':'Current bytes named by the supervised fixture run.',
          'result_ids':['result:observation']}

    saved=call(tmp_path,'visual_create',{'spec':spec})
    assert saved['readiness']=='SPECIFIED' and 'render' not in saved['spec']
    assert not (manuscript/'figures/generated/adopted-panel.pdf').exists()
    rendered=call(tmp_path,'visual_render',{'id':'adopted-panel'})
    receipt=rendered['render']
    assert receipt['renderer']=='supervised-run-artifact'
    assert receipt['source_provenance']['run_id']==run_id
    assert receipt['source_provenance']['result_sha256']
    assert receipt['source_provenance']['source_paths']['pdf'].endswith('panel.pdf')
    assert receipt['source_provenance']['historical_output_verification']=='NOT_ESTABLISHED'
    for fmt,source in sources.items():
        target=manuscript/('figures/generated/adopted-panel.'+fmt)
        assert target.read_bytes()==source.read_bytes()
    row=next(row for row in call(tmp_path,'visuals',{})['specs'] if row['id']=='adopted-panel')
    assert row['currentness']['drawing_freshness']=='CURRENT'
    assert row['currentness']['evidence_binding_status']=='CURRENT'
    manifest=json.loads((manuscript/'figure_manifest.json').read_text())['placed'][0]
    assert manifest['source_kind']=='supervised-run-artifact'
    assert manifest['result_ids']==['result:observation']

    placed=call(tmp_path,'visual_place',{'id':'adopted-panel','file':created['source']['root']})
    assert placed['repo_file']==created['source']['root']
    assert '\\caption{'+spec['caption']+'}' in (tmp_path/created['source']['root']).read_text()

    sources['svg'].write_bytes(b'<svg>changed after adoption</svg>')
    stale=next(row for row in call(tmp_path,'visuals',{})['specs'] if row['id']=='adopted-panel')
    assert stale['currentness']['drawing_freshness']=='STALE'
    assert any(change['kind']=='supervised_run' for change in stale['currentness']['changed_dependencies'])
    query={'project':['visual-lab'],'id':['adopted-panel'],'format':['pdf']}
    assert visuals_surface.handle('/visuals/asset',query,'GET',b'',repo_root=tmp_path)[0]==409
    status,mime,body=visuals_surface.handle('/visuals/asset',{**query,'inspect':['1']},'GET',b'',repo_root=tmp_path)
    assert status==200 and mime=='application/pdf' and body==b'%PDF-supervised'
    with pytest.raises(ValueError,match='basis needs review'):
        call(tmp_path,'visual_place',{'id':'adopted-panel','file':created['source']['root']})


@pytest.mark.parametrize('kind',['plot','diagram'])
def test_documented_create_render_place_update_preserves_science_and_consumers(tmp_path,kind):
    if kind=='diagram' and not shutil.which('dot'):pytest.skip('Graphviz unavailable')
    base, manuscript, created = project(tmp_path)
    contract=help_for(tmp_path,'visual_create')
    payload=copy.deepcopy(contract['examples'][kind])
    # The exact runnable example first, then the declared optional evidence join.
    saved=call(tmp_path,'visual_create',payload)
    assert saved['spec']==payload['spec']
    bound=call(tmp_path,'visual_create',{'expected_revision':saved['spec_revision'],
        'spec':{'id':saved['spec']['id'],'result_ids':['result:observation']}})
    ident=bound['spec']['id']
    rendered=call(tmp_path,'visual_render',{'id':ident})
    assert rendered['readiness']=='GENERATED'
    assert all((manuscript/path).is_file() for path in rendered['render']['outputs'])
    file=created['source']['root']
    placed=call(tmp_path,'visual_place',{'id':ident,'file':file})
    assert placed['repo_file']==file
    original_source=(tmp_path/file).read_text()
    assert '\\label{fig:'+ident+'}' in original_source
    row=next(row for row in call(tmp_path,'visuals',{})['specs'] if row['id']==ident)
    assert row['placement_caption']['status']=='MATCHES'
    assert row['currentness']['evidence_binding_status']=='CURRENT'
    before_manifest=json.loads((manuscript/'figure_manifest.json').read_text())['placed'][0]
    assert before_manifest['result_ids']==['result:observation']
    updated=call(tmp_path,'visual_create',{'expected_revision':row['spec_revision'],
        'spec':{'id':ident,'caption':'Revised fixture caption; no empirical claim.'}})
    for field in ('question','title','result_ids','section','section_repo_file','render'):
        assert updated['spec'][field]==row[field]
    fresh=call(tmp_path,'visuals',{})['specs'][0]
    assert fresh['currentness']['drawing_freshness']=='CURRENT'
    assert fresh['currentness']['presentation_status']=='CHANGED'
    assert fresh['placement_caption']['status']=='DIFFERS'
    assert updated['placement_caption']['next_read']['payload']['files']==[file]
    assert (tmp_path/file).read_text()==original_source  # brief edits cannot silently change authored prose
    canonical=manuscript/'manuscript_spec.json'
    exact=canonical.read_bytes()
    for guard in ({},{'expected_revision':row['spec_revision']}):
        error = ValueError if guard else writing_declarations.PayloadAdmissionError
        message = 'revision conflict' if guard else 'Payload rejected'
        with pytest.raises(error,match=message):
            call(tmp_path,'visual_create',{**guard,'spec':{'id':ident,'caption':'Stale overwrite'}})
        assert canonical.read_bytes()==exact
    refreshed=call(tmp_path,'visual_render',{'id':ident})
    assert refreshed['render']['reused'] is True
    assert refreshed['placement_caption']['status']=='DIFFERS'
    read=call(tmp_path,**{'operation':'source','payload':refreshed['placement_caption']['next_read']['payload']})
    assert read  # route returned by the owner is accepted by the real writer gateway
    manifest=json.loads((manuscript/'figure_manifest.json').read_text())['placed'][0]
    assert manifest['result_ids']==['result:observation']
    assert manifest['caption']==updated['spec']['caption']
    assert manifest['placed_repo_file']==file
    research=research_catalogue.state_payload('visual-lab',tmp_path)
    assert ident in json.dumps(research) and 'result:observation' in json.dumps(research)
    # Retaining an old render receipt must not bless changed data/graph inputs.
    current=call(tmp_path,'visuals',{})['specs'][0]
    change=({'y_label':'Changed axis'} if kind=='plot' else {'nodes':[{'id':'claim','label':'Changed claim'},{'id':'assumption'}]})
    call(tmp_path,'visual_create',{'expected_revision':current['spec_revision'],'spec':{'id':ident,**change}})
    stale=call(tmp_path,'visuals',{})['specs'][0]
    assert stale['currentness']['drawing_freshness']=='STALE'
    with pytest.raises(ValueError,match='basis needs review'):
        call(tmp_path,'visual_place',{'id':ident,'file':file})


def test_recovery_selects_the_actual_renderer_and_legacy_read_is_nonmutating(tmp_path):
    _base,manuscript,_created=project(tmp_path)
    bad={'spec':{'id':'broken','kind':'diagram','title':'Missing fields'}}
    with pytest.raises(ValueError) as error:call(tmp_path,'visual_create',bad)
    response=writing_tools.failure_response(tmp_path,'visual-lab','work','visual_create',bad,error.value)
    contract=response['contract']
    # ONE name for the chosen variant; `selected_kind` and `selected_suboperation` were
    # two names for it. For visual_create the variant IS the renderer kind.
    assert contract['selected_variant']=='diagram'
    assert {'question','caption','nodes','edges'} <= set(contract['input']['properties']['spec']['required'])
    jsonschema.validate(contract['example'],contract['input'])
    call(tmp_path,'visual_create',contract['example'])
    canonical=manuscript/'manuscript_spec.json'
    before=canonical.read_bytes()
    first=call(tmp_path,'visuals',{})['specs'][0]
    second=call(tmp_path,'visuals',{})['specs'][0]
    assert first['spec_revision']==second['spec_revision']
    assert canonical.read_bytes()==before
    # A legacy compatibility input also acquires its revision without migration.
    data=json.loads(before);data.pop('figure_specs');canonical.write_text(json.dumps(data))
    (manuscript/'visual_specs.json').write_text(json.dumps({'specs':[contract['example']['spec']]}))
    before=canonical.read_bytes()
    legacy=call(tmp_path,'visuals',{})['specs'][0]
    assert legacy['spec_revision']==vp.digest(contract['example']['spec'])
    assert canonical.read_bytes()==before
    updated=call(tmp_path,'visual_create',{'expected_revision':legacy['spec_revision'],
        'spec':{'id':legacy['id'],'caption':'An explicit legacy update.'}})
    assert updated['spec']['question']==legacy['question']


def test_ui_roundtrip_preserves_owner_receipts_and_binding_clear_is_explicit(tmp_path):
    _base,manuscript,_created=project(tmp_path)
    payload=help_for(tmp_path,'visual_create')['examples']['plot']
    saved=call(tmp_path,'visual_create',{'spec':{**payload['spec'],'result_ids':['result:observation']}})
    ident=saved['spec']['id']
    call(tmp_path,'visual_render',{'id':ident})
    row=call(tmp_path,'visuals',{})['specs'][0]
    changed=call(tmp_path,'visual_create',{'spec':{**row,'question':'A revised explicit question?'},
        'expected_revision':row['spec_revision']})
    assert changed['spec']['result_ids']==['result:observation']
    assert changed['spec']['render']==row['render']
    assert not {'spec_revision','currentness','input_scope','render_freshness'} & set(changed['spec'])
    before=(manuscript/'manuscript_spec.json').read_bytes()
    with pytest.raises(ValueError,match='owner-managed'):
        call(tmp_path,'visual_create',{'spec':{'id':ident,'render':{'outputs':['invented.pdf']}},
            'expected_revision':changed['spec_revision']})
    assert (manuscript/'manuscript_spec.json').read_bytes()==before
    cleared=call(tmp_path,'visual_create',{'spec':{'id':ident,'result_ids':[]},
        'expected_revision':changed['spec_revision']})
    assert cleared['spec']['result_ids']==[]


def test_generated_drawing_does_not_hide_missing_scientific_binding(tmp_path):
    _base,_manuscript,created=project(tmp_path)
    payload=help_for(tmp_path,'visual_create')['examples']['plot']
    saved=call(tmp_path,'visual_create',{'spec':{**payload['spec'],'result_ids':['result:missing']}})
    call(tmp_path,'visual_render',{'id':saved['spec']['id']})
    row=call(tmp_path,'visuals',{})['specs'][0]
    assert row['currentness']['drawing_freshness']=='CURRENT'
    assert row['currentness']['evidence_binding_status']=='STALE'
    with pytest.raises(ValueError,match='basis needs review'):
        call(tmp_path,'visual_place',{'id':row['id'],'file':created['source']['root']})


@pytest.mark.parametrize('edited_id',['visual-a','visual-b'])
def test_delayed_render_serializes_visual_edits_without_losing_other_owner_fields(tmp_path,monkeypatch,edited_id):
    from laplace.pipeline import projection_spec
    base,manuscript,created=project(tmp_path)
    template=help_for(tmp_path,'visual_create')['examples']['plot']['spec']
    for ident in ('visual-a','visual-b'):
        call(tmp_path,'visual_create',{'spec':{**template,'id':ident,'result_ids':['result:observation']}})
        call(tmp_path,'visual_render',{'id':ident})
        call(tmp_path,'visual_place',{'id':ident,'file':created['source']['root']})
    previous={row['id']:row for row in call(tmp_path,'visuals',{})['specs']}
    source_before=(tmp_path/created['source']['root']).read_bytes()
    (base/'data/observations.csv').write_text('input,response\n1,3\n2,6\n')
    entered=threading.Event();release=threading.Event();edit_started=threading.Event()
    original=vp._render
    def delayed(manuscript,spec):
        if spec['id']=='visual-a':
            entered.set()
            assert release.wait(10),'test did not release the renderer'
        return original(manuscript,spec)
    monkeypatch.setattr(vp,'_render',delayed)
    def edit():
        edit_started.set()
        return call(tmp_path,'visual_create',{'expected_revision':previous[edited_id]['spec_revision'],
            'spec':{'id':edited_id,'caption':'A concurrent authored caption.'}})
    with ThreadPoolExecutor(max_workers=2) as pool:
        rendering=pool.submit(call,tmp_path,'visual_render',{'id':'visual-a'})
        try:
            assert entered.wait(10)
            editing=pool.submit(edit)
            assert edit_started.wait(10)
            # The shared visual lock is held across generation and publication.
            from filelock import FileLock,Timeout
            with pytest.raises(Timeout):
                with FileLock(str(manuscript/'.visual-mutation.lock'),timeout=0):pass
            assert not editing.done()
            # The canonical spec owner can still commit unrelated metadata.
            projection_spec.update_file_with_receipt(manuscript/'manuscript_spec.json',
                lambda value:{**value,'concurrent_nonvisual':{'purpose':'Must survive visual publication'}})
        finally:release.set()
        rendered=rendering.result(timeout=10)
        if edited_id=='visual-a':
            with pytest.raises(ValueError,match='revision conflict'):editing.result(timeout=10)
        else:
            assert editing.result(timeout=10)['spec']['caption']=='A concurrent authored caption.'
    current={row['id']:row for row in call(tmp_path,'visuals',{})['specs']}
    assert current['visual-a']['render']['output_digests']==rendered['render']['output_digests']
    assert current['visual-a']['currentness']['drawing_freshness']=='CURRENT'
    for ident,row in current.items():
        assert row['result_ids']==['result:observation']
        assert row['section_repo_file']==previous[ident]['section_repo_file']
    assert current['visual-a']['caption']==previous['visual-a']['caption']
    assert current['visual-b']['caption']==('A concurrent authored caption.' if edited_id=='visual-b' else previous['visual-b']['caption'])
    assert (tmp_path/created['source']['root']).read_bytes()==source_before
    assert json.loads((manuscript/'manuscript_spec.json').read_text())['concurrent_nonvisual']['purpose']=='Must survive visual publication'


def test_guarded_update_cleans_legacy_read_fields_only_after_matching_actual_row(tmp_path):
    _base,manuscript,_created=project(tmp_path)
    template=help_for(tmp_path,'visual_create')['examples']['plot']['spec']
    call(tmp_path,'visual_create',{'spec':template})
    path=manuscript/'manuscript_spec.json';data=json.loads(path.read_text())
    row=data['figure_specs'][0]
    row.update(currentness={'status':'stale cached fiction'},render_freshness='STALE',
        input_scope='wrong',spec_revision='old cached revision',placement_caption={'status':'DIFFERS'},
        authored_limitation='Retain this scientific metadata')
    path.write_text(json.dumps(data))
    before=path.read_bytes();actual=vp.digest(row)
    with pytest.raises(ValueError,match='revision conflict'):
        call(tmp_path,'visual_create',{'expected_revision':'old cached revision','spec':{'id':row['id'],'caption':'Rejected'}})
    assert path.read_bytes()==before
    projected=call(tmp_path,'visuals',{})['specs'][0]
    assert projected['spec_revision']==actual
    updated=call(tmp_path,'visual_create',{'expected_revision':actual,'spec':{'id':row['id'],'caption':'Updated'}})
    assert not {'currentness','render_freshness','input_scope','spec_revision','placement_caption'} & set(updated['spec'])
    assert updated['spec']['authored_limitation']=='Retain this scientific metadata'


def test_delayed_placement_cannot_overwrite_a_concurrent_visual_edit(tmp_path,monkeypatch):
    _base,manuscript,created=project(tmp_path)
    template=help_for(tmp_path,'visual_create')['examples']['plot']['spec']
    for ident in ('visual-a','visual-b'):
        call(tmp_path,'visual_create',{'spec':{**template,'id':ident,'result_ids':['result:observation']}})
        call(tmp_path,'visual_render',{'id':ident})
    before={row['id']:row for row in call(tmp_path,'visuals',{})['specs']}
    entered=threading.Event();release=threading.Event();started=threading.Event()
    original=visuals_surface._placement_text
    def delayed(*args,**kwargs):
        entered.set();assert release.wait(10)
        return original(*args,**kwargs)
    monkeypatch.setattr(visuals_surface,'_placement_text',delayed)
    def edit_b():
        started.set()
        return call(tmp_path,'visual_create',{'expected_revision':before['visual-b']['spec_revision'],
            'spec':{'id':'visual-b','question':'A concurrent question that must survive placement.'}})
    with ThreadPoolExecutor(max_workers=2) as pool:
        placing=pool.submit(call,tmp_path,'visual_place',{'id':'visual-a','file':created['source']['root']})
        try:
            assert entered.wait(10)
            editing=pool.submit(edit_b);assert started.wait(10)
            assert not editing.done()
        finally:release.set()
        assert placing.result(timeout=10)['ok']
        editing.result(timeout=10)
    after={row['id']:row for row in call(tmp_path,'visuals',{})['specs']}
    assert after['visual-b']['question']=='A concurrent question that must survive placement.'
    assert after['visual-b']['result_ids']==['result:observation']
    assert after['visual-a']['section_repo_file']==created['source']['root']
    assert after['visual-a']['placement_caption']['status']=='MATCHES'
    assert '\\label{fig:visual-a}' in (tmp_path/created['source']['root']).read_text()
    with pytest.raises(ValueError,match='revision conflict'):
        call(tmp_path,'visual_create',{'expected_revision':before['visual-a']['spec_revision'],
            'spec':{'id':'visual-a','caption':'Stale pre-placement edit'}})


def test_rendering_one_legacy_visual_keeps_other_legacy_specs(tmp_path):
    _base,manuscript,_created=project(tmp_path)
    template=help_for(tmp_path,'visual_create')['examples']['plot']['spec']
    (manuscript/'visual_specs.json').write_text(json.dumps({'specs':[
        {**template,'id':'legacy-a'}, {**template,'id':'legacy-b','caption':'Retain legacy B'}]}))
    call(tmp_path,'visual_render',{'id':'legacy-a'})
    rows={row['id']:row for row in vp.load(manuscript)['specs']}
    assert set(rows)=={'legacy-a','legacy-b'}
    assert rows['legacy-b']['caption']=='Retain legacy B'


@pytest.mark.parametrize('projection_error',[None,OSError,ValueError])
def test_placement_holds_root_and_fragment_set_and_projects_only_after_release(tmp_path, monkeypatch, projection_error):
    from laplace.manuscript import manuscript_source, review_surface
    _base, manuscript, created = project(tmp_path)
    spec = copy.deepcopy(help_for(tmp_path, 'visual_create')['examples']['plot'])
    saved = call(tmp_path, 'visual_create', spec); ident = saved['spec']['id']
    call(tmp_path, 'visual_render', {'id':ident})
    root_file = tmp_path / created['source']['root']
    root_file.write_text(root_file.read_text().replace('amsmath,amssymb,graphicx,hyperref', 'amsmath,amssymb,hyperref'))
    target = manuscript / 'chapters' / 'chapter-01.tex'
    original = visuals_surface._review_rewrite
    original_mirror = review_surface.mirror_source_changes
    original_receipt = visuals_surface.file_receipt
    observed = []
    def rewrite(*args, **kwargs):
        assert manuscript_source.source_mutation_active()
        # Both files must have been declared before either write. A late scope
        # growth is refused by the actual shared primitive.
        with manuscript_source.source_mutation([root_file, target]):
            pass
        observed.append(args[2].resolve())
        return original(*args, **kwargs)
    def mirror(*args, **kwargs):
        assert not manuscript_source.source_mutation_active()
        if projection_error:raise projection_error('controlled optional projection failure')
        return original_mirror(*args, **kwargs)
    def receipt(root,path,*args,**kwargs):
        if path.suffix=='.tex':assert manuscript_source.source_mutation_active()
        return original_receipt(root,path,*args,**kwargs)
    monkeypatch.setattr(visuals_surface, '_review_rewrite', rewrite)
    monkeypatch.setattr(review_surface, 'mirror_source_changes', mirror)
    monkeypatch.setattr(visuals_surface, 'file_receipt', receipt)
    result = call(tmp_path, 'visual_place', {'id':ident,'file':target.relative_to(tmp_path).as_posix()})
    assert result['ok'] and set(observed) == {root_file.resolve(),target.resolve()}
    assert '\\usepackage{graphicx}' in root_file.read_text()
    assert '\\label{fig:'+ident+'}' in target.read_text()
    if projection_error:assert result['plan_sync']['status']=='UNPROVED' and result['plan_sync']['source_effect_retained']


@pytest.mark.parametrize('failed_operation',['visual-spec','figure-manifest'])
@pytest.mark.parametrize('transport',['http-owner','named','typed'])
def test_placement_tracking_failure_preserves_exact_source_effect_without_success(tmp_path,monkeypatch,failed_operation,transport):
    from laplace.core import grammar as g
    from laplace.native import verbs as writing_verbs
    _base,manuscript,created=project(tmp_path)
    spec=copy.deepcopy(help_for(tmp_path,'visual_create')['examples']['plot'])
    ident=call(tmp_path,'visual_create',spec)['spec']['id']
    call(tmp_path,'visual_render',{'id':ident})
    file=created['source']['root'];target=tmp_path/file;before=target.read_bytes()
    def fail(*args,**kwargs):raise OSError('controlled '+failed_operation+' publication failure')
    if failed_operation=='visual-spec':monkeypatch.setattr(vp,'save',fail)
    else:monkeypatch.setattr(visuals_surface,'_manifest_placement',fail)
    payload={'project':'visual-lab','id':ident,'file':file}
    if transport=='http-owner':
        status,_,encoded=visuals_surface.handle('/visuals/place',{},'POST',json.dumps(payload).encode(),repo_root=tmp_path)
        assert status==409;result=json.loads(encoded)
    elif transport=='named':
        with pytest.raises(operations.OwnerError) as error:call(tmp_path,'visual_place',payload)
        result=error.value.details
    else:
        _route,request=writing_verbs.from_owner_call('visual_place',payload,project='visual-lab',root=tmp_path)
        result=writing_tools.request(tmp_path,'visual-lab','work',request)
        assert 'refused' not in result, 'post-effect tracking failure became pre-effect refusal'
    assert result['ok'] is False and result['source_effect_retained']
    assert result['source_effect']['state']=='COMMITTED' and not result['source_effect']['complete']
    assert result['source_effect']['follow_through']['required'][0]['status']=='UNPROVED'
    assert result['metadata_tracking']=='UNPROVED' and result['failed_operation']==failed_operation
    assert target.read_bytes()!=before and ('\\label{fig:'+ident+'}').encode() in target.read_bytes()
    physical=next(row for row in result['owned_changes']['files'] if row['path']==file)
    assert physical['after_sha256']==physical['observed_after_sha256']=='sha256:'+hashlib.sha256(target.read_bytes()).hexdigest()
    assert 'Do not repeat' in result['recovery']['note'] and 'placed_at' not in result
    from laplace.writing.schemas import SCHEMAS
    recovery=result['recovery']['read']
    jsonschema.validate(recovery['payload'],SCHEMAS[recovery['operation']])
    inspected=call(tmp_path,recovery['operation'],recovery['payload'])
    assert inspected and result['recovery']['asset_id']==ident
    if failed_operation=='visual-spec':assert not result['owned_changes']['objects']
    else:
        assert result['owned_changes']['objects']
        assert any(row['path'].endswith('manuscript_spec.json') for row in result['owned_changes']['files'])


def test_graphicx_commit_is_retained_when_later_placement_preparation_fails(tmp_path,monkeypatch):
    _base,manuscript,created=project(tmp_path)
    spec=copy.deepcopy(help_for(tmp_path,'visual_create')['examples']['plot'])
    ident=call(tmp_path,'visual_create',spec)['spec']['id']
    call(tmp_path,'visual_render',{'id':ident})
    target=tmp_path/created['source']['root']
    target.write_text(target.read_text().replace('amsmath,amssymb,graphicx,hyperref','amsmath,amssymb,hyperref'))
    def fail(*args,**kwargs):raise ValueError('controlled placement composition failure')
    monkeypatch.setattr(visuals_surface,'_placement_text',fail)
    status,_,encoded=visuals_surface.handle('/visuals/place',{},'POST',json.dumps({'project':'visual-lab','id':ident,'file':created['source']['root']}).encode(),repo_root=tmp_path)
    result=json.loads(encoded)
    assert status==422 and 'graphicx' in target.read_text()
    assert result['source_effect']['state']=='COMMITTED' and not result['source_effect']['complete']
    assert result['source_effect_retained'] and result['source_effect']['files']
