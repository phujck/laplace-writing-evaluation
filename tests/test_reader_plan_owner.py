"""Reader state uses existing artifacts and scoped subject/input observations."""
import json
import pytest

from laplace.manuscript import project_structure
from laplace.native import tools as writing_tools
from laplace.manuscript import reader_plan
from test_manuscript_structure import _section_fixture as _source_section_fixture


@pytest.mark.parametrize('original_artifacts',[
    'malformed-result','malformed-artifacts','malformed-row','malformed-id'])
def test_supervised_artifact_original_malformed_result_is_unqualified(tmp_path,original_artifacts):
    import hashlib
    from laplace.pipeline import visual_production as vp
    from laplace.research import research_records
    manuscript,base,run=_native_supervised_reader_artifact(
        tmp_path,original_artifacts=original_artifacts,render=False)
    output=manuscript/run['result_path']
    raw=output.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==run['result_sha256']
    assert writing_tools.execute(tmp_path,'book','work','run_status',{'id':run['id']})['state']=='COMPLETE'
    assert research_records.result_bindings(manuscript,['result:artifact'],base)['status']=='CURRENT'
    with pytest.raises(ValueError,match='malformed supervised run result'):
        writing_tools.execute(tmp_path,'book','work','visual_render',{'id':'native-artifact'})
    observed=vp.reader_inputs(manuscript,['native-artifact'],base)['native-artifact']
    assert observed['status']=='UNRESOLVED'
    assert any('malformed supervised run result' in issue for issue in observed['problems'])
    change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],changes={
        'function':'Explain','proposition':'Do not qualify a malformed original result.',
        'input_nodes':[],'figure_anchor':'native-artifact'})
    row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    assert row['diagnostics'] and row['input_currentness']['status']!='CURRENT'
    assert reader_plan.compare_basis('book',tmp_path,row['reader_basis'])['status']!='CURRENT'
    assert output.read_bytes()==raw


@pytest.mark.parametrize('original_artifacts',['unique','duplicate'])
def test_supervised_artifact_original_identity_before_completion(tmp_path,original_artifacts):
    """Unlike post-completion tampering, these bytes are the actual run output."""
    import hashlib
    from pathlib import Path
    from laplace.pipeline import visual_production as vp
    from laplace.research import research_records
    manuscript,base,run=_native_supervised_reader_artifact(
        tmp_path,original_artifacts=original_artifacts,render=False)
    output=manuscript/run['result_path']
    raw=output.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==run['result_sha256']
    result=json.loads(raw)
    panels=[row for row in result['artifacts'] if row['id']=='panel']
    assert len(panels)==(2 if original_artifacts=='duplicate' else 1)
    if original_artifacts=='duplicate':
        paths=[Path(row['pdf']).resolve() for row in panels]
        assert all(path.is_relative_to(base.resolve()) and path.is_file() for path in paths)
        assert len({hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})==2
    # The real run/result owners admitted the original bytes. This is not a
    # fabricated COMPLETE result or a manually repaired completion digest.
    current=writing_tools.execute(tmp_path,'book','work','run_status',{'id':run['id']})
    assert current['state']=='COMPLETE',current
    assert research_records.result_bindings(manuscript,['result:artifact'],base)['status']=='CURRENT'
    if original_artifacts=='duplicate':
        with pytest.raises(ValueError,match='ambiguous'):
            writing_tools.execute(tmp_path,'book','work','visual_render',{'id':'native-artifact'})
        spec=vp.load(manuscript)['specs'][0]
        assert not spec.get('render')
        observed=vp.reader_inputs(manuscript,['native-artifact'],base)['native-artifact']
        assert observed['status']=='UNRESOLVED'
        assert any('ambiguous' in message for message in observed['problems'])
    else:
        writing_tools.execute(tmp_path,'book','work','visual_render',{'id':'native-artifact'})
        assert vp.reader_inputs(manuscript,['native-artifact'],base)['native-artifact']['status']=='CURRENT'
    change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],changes={
        'function':'Explain','proposition':'Inspect the exact original artifact identity.',
        'input_nodes':[],'figure_anchor':'native-artifact'})
    row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    if original_artifacts=='duplicate':
        assert row['diagnostics'] and row['input_currentness']['status']!='CURRENT'
        assert reader_plan.compare_basis('book',tmp_path,row['reader_basis'])['status']!='CURRENT'
        with pytest.raises(ValueError,match='INPUT_UNRESOLVED'):
            change(tmp_path,row['edit_action'],changes={},input_observations=row['reader_basis']['inputs'])
        assert not reader_plan.subjects_ref_current('book',tmp_path,reader_plan.subjects_ref([row['reader_basis']]))
    else:
        change(tmp_path,row['edit_action'],changes={},input_observations=row['reader_basis']['inputs'])
        row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
        assert not row['diagnostics'] and row['input_currentness']['status']=='CURRENT'
    assert output.read_bytes()==raw
    assert writing_tools.execute(tmp_path,'book','work','run_status',{'id':run['id']})['state']=='COMPLETE'


def _native_supervised_reader_artifact(root, *, original_artifacts='unique', render=True):
    import time
    from laplace.pipeline import registry
    manuscript,_,_=_section_fixture(root)
    record=registry.resolve('book',repo_root=root)
    base=record.path(record.project_dir,root)
    (base/'artifact-producer.py').write_text(
        "import argparse,json\nfrom pathlib import Path\nimport matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
        "p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()\n"
        "out=Path(a.result).with_suffix('');fig,ax=plt.subplots();ax.plot([0,1],[1,2]);files={}\n"
        "for fmt in ('pdf','svg','png'):\n target=out.with_suffix('.'+fmt);fig.savefig(target);files[fmt]=str(target.resolve())\n"
        "rows=[{'id':'panel',**files}]\n"
        "if "+repr(original_artifacts)+"=='duplicate':\n"
        " ax.plot([0,1],[2,0]);other={}\n"
        " for fmt in ('pdf','svg','png'):\n"
        "  target=out.parent/(out.name+'-other.'+fmt);fig.savefig(target);other[fmt]=str(target.resolve())\n"
        " rows.append({'id':'panel',**other})\n"
        "payload={'artifacts':rows};shape="+repr(original_artifacts)+"\n"
        "if shape=='malformed-result':payload=rows\n"
        "elif shape=='malformed-artifacts':payload={'artifacts':{'panel':files}}\n"
        "elif shape=='malformed-row':payload={'artifacts':[None]}\n"
        "elif shape=='malformed-id':payload={'artifacts':[{'id':None,**files}]}\n"
        "plt.close(fig);Path(a.result).write_text(json.dumps(payload))\n")
    writing_tools.execute(root,'book','work','research_producer',{
        'id':'artifact-measurement','scope':'project','executable':'artifact-producer.py',
        'modes':['smoke'],'allowed_args':{},'dependencies':[]})
    launched=writing_tools.execute(root,'book','work','experiment_run',{
        'producer_id':'artifact-measurement','mode':'smoke','args':{}})
    for _ in range(400):
        run=writing_tools.execute(root,'book','work','run_status',{'id':launched['run']['id']})
        if run['state']!='RUNNING':break
        time.sleep(.025)
    from pathlib import Path
    assert run['state']=='COMPLETE',json.dumps({'state':run['state'],'exit_code':run.get('exit_code'),
        'reason':run.get('reason'),'stderr':Path(run['stderr_path']).read_text()[-8000:]})
    writing_tools.execute(root,'book','work','research_record',{
        'kind':'result','id':'result:artifact','run_id':run['id'],'result':run['result_path'],
        'question':'What does this controlled native producer draw?','summary':'An illustrative slope.'})
    writing_tools.execute(root,'book','work','visual_create',{'spec':{
        'id':'native-artifact','kind':'artifact','title':'Native controlled artifact',
        'question':'What drawing did this actual run produce?','caption':'A controlled fixture, not external evidence.',
        'run_id':run['id'],'artifact_id':'panel','result_ids':['result:artifact']}})
    if render:writing_tools.execute(root,'book','work','visual_render',{'id':'native-artifact'})
    return manuscript,base,run


@pytest.mark.parametrize('damage',['result','source-output','duplicate-artifact','missing-run'])
def test_actual_supervised_artifact_reader_retains_failed_bytes(tmp_path,damage):
    from laplace.pipeline import visual_production as vp
    manuscript,base,run=_native_supervised_reader_artifact(tmp_path)
    change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],changes={
        'function':'Explain','proposition':'Inspect the actual supervised output.','input_nodes':[],
        'figure_anchor':'native-artifact'})
    def row():return detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    basis=row()['reader_basis']
    assert reader_plan.compare_basis('book',tmp_path,basis)['status']=='CURRENT'
    result=manuscript/run['result_path']
    value=json.loads(result.read_text())
    if damage=='missing-run':
        (manuscript/'research_runs'/(run['id']+'.json')).unlink()
        assert row()['diagnostics']
        assert reader_plan.compare_basis('book',tmp_path,basis)['status']!='CURRENT'
        return
    cuts=[]
    for number in [1,2]:
        if damage=='source-output':
            from pathlib import Path
            path=Path(value['artifacts'][0]['pdf'])
            path.write_bytes(path.read_bytes()+b'\nmutation '+str(number).encode())
        elif damage=='duplicate-artifact':
            value['artifacts'].append({**value['artifacts'][0],'note':str(number)})
            result.write_text(json.dumps(value))
        else:
            value['changed_interpretation']=number
            result.write_text(json.dumps(value))
        current=row()
        cuts.append(current['reader_basis']['inputs']['figures:native-artifact'])
        assert current['diagnostics']
        assert reader_plan.compare_basis('book',tmp_path,basis)['status']!='CURRENT'
    assert len(set(cuts))==2


@pytest.mark.parametrize('damage',['interpretation','result-bytes','producer-bytes','run-missing'])
def test_native_research_visual_scientific_inputs_keep_observing_while_stale(tmp_path,damage):
    import time
    from laplace.pipeline import visual_production as vp,registry
    manuscript,_,_=_section_fixture(tmp_path)
    record=registry.resolve('book',repo_root=tmp_path)
    base=record.path(record.project_dir,tmp_path)
    (base/'data.csv').write_text('x,y\n1,2\n2,4\n')
    (base/'producer.py').write_text(
        "import argparse,json\nfrom pathlib import Path\n"
        "p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()\n"
        "Path(a.result).write_text(json.dumps({'slope':2,'unit':'m/s'}))\n")
    writing_tools.execute(tmp_path,'book','work','research_producer',{
        'id':'measurement','scope':'project','executable':'producer.py','modes':['smoke'],
        'allowed_args':{},'dependencies':['data.csv']})
    launched=writing_tools.execute(tmp_path,'book','work','experiment_run',{
        'producer_id':'measurement','mode':'smoke','args':{}})
    for _ in range(160):
        run=writing_tools.execute(tmp_path,'book','work','run_status',{'id':launched['run']['id']})
        if run['state']!='RUNNING':break
        time.sleep(.025)
    assert run['state']=='COMPLETE',run
    saved=writing_tools.execute(tmp_path,'book','work','research_record',{
        'kind':'result','id':'result:measurement','run_id':run['id'],'result':run['result_path'],
        'question':'What does this controlled fixture calculate?','summary':'A slope of two.'})
    spec={'id':'measured-reader','title':'Controlled measured input','question':'What does the fixture show?',
        'caption':'A controlled fixture, not scientific acceptance.','kind':'plot',
        'source_data':'data.csv','x':'x','series':['y'],'result_ids':['result:measurement']}
    writing_tools.execute(tmp_path,'book','work','visual_create',{'spec':spec})
    writing_tools.execute(tmp_path,'book','work','visual_render',{'id':spec['id']})
    def section():
        return project_structure.read('book',{'view':'detail','section_ids':['first']},tmp_path)['sections'][0]
    change(tmp_path,section()['paragraph_plan']['create_action'],changes={
        'function':'Explain','proposition':'Use the controlled result.','input_nodes':[],
        'figure_anchor':spec['id']})
    def row():return section()['paragraph_plan']['paragraphs']['items'][0]
    basis=row()['reader_basis']
    comparison=reader_plan.compare_basis('book',tmp_path,basis)
    assert comparison['status']=='CURRENT', json.dumps({'comparison':comparison,'basis':basis,'links':row()['links']})
    assert not row()['diagnostics']
    cuts=[]
    if damage=='run-missing':
        path=manuscript/'research_runs'/('run-'+run['id'].removeprefix('run-')+'.json')
        assert path.is_file()
        path.unlink()
        assert row()['diagnostics']
        assert reader_plan.compare_basis('book',tmp_path,basis)['status']!='CURRENT'
        return
    for number in [1,2]:
        if damage=='interpretation':
            saved=writing_tools.execute(tmp_path,'book','work','research_record',{
                'record':{'kind':'result','id':'result:measurement','summary':'Changed interpretation '+str(number)},
                'expected_revision':saved['record']['revision']})
        elif damage=='result-bytes':
            path=manuscript/run['result_path']
            path.write_text(json.dumps({'slope':number+2,'unit':'m/s'}))
        else:
            path=base/'producer.py'
            path.write_text(path.read_text()+'\n# changed scientific model '+str(number)+'\n')
        current=row()
        cuts.append(current['reader_basis']['inputs']['figures:'+spec['id']])
        assert current['diagnostics']
        assert reader_plan.compare_basis('book',tmp_path,basis)['status']!='CURRENT'
        assert vp.provenance(manuscript,vp.load(manuscript)['specs'][0],base)['drawing_freshness']=='CURRENT'
    assert len(set(cuts))==2


def _section_fixture(root):
    # The source helper declares concept:first but does not create it. Tests of
    # qualified observations need an actual canonical premise, not equal nulls.
    from laplace.research import corpus_ingest
    value=_source_section_fixture(root)
    result=corpus_ingest.rewire_add(root,'book',{'kind':'add-node','node':'concept:first',
        'node_kind':'definition','essence':'An authored fixture premise.','by':'fixture'})
    assert not result.get('error'), result
    return value


@pytest.mark.parametrize('damage',['unrendered','duplicate','malformed','null-list','missing-data','missing-output','ambiguous-json','incomplete-output-receipt'])
def test_actual_canonical_visual_damage_is_unqualified(tmp_path,damage):
    from laplace.pipeline import visual_production as vp
    manuscript,_,_=_section_fixture(tmp_path)
    data=_rendered_reader_plot(tmp_path,manuscript,render=damage!='unrendered')
    path=manuscript/'manuscript_spec.json'
    value=json.loads(path.read_text())
    spec=value['figure_specs'][0]
    if damage=='duplicate':value['figure_specs'].append(dict(spec))
    elif damage=='malformed':value['figure_specs'].append(None)
    elif damage=='null-list':value['figure_specs']=None
    elif damage=='missing-data':data.unlink()
    elif damage=='missing-output':(manuscript/spec['render']['outputs'][0]).unlink()
    elif damage=='incomplete-output-receipt':
        pdf=next(p for p in spec['render']['outputs'] if p.endswith('.pdf'))
        spec['render']['outputs']=[pdf]
        spec['render']['output_digests']={pdf:spec['render']['output_digests'][pdf]}
    if damage=='ambiguous-json':
        path.write_text('{"figure_specs":[],"figure_specs":'+json.dumps([spec])+'}')
    else:path.write_text(json.dumps(value))
    observed=vp.reader_inputs(manuscript,['reader-plot'],data.parent)['reader-plot']
    assert observed['status']=='UNRESOLVED' and observed['problems']
    change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],
        changes={'function':'Explain','proposition':'Inspect an unavailable input.',
                 'input_nodes':[],'figure_anchor':'reader-plot'})
    row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    assert row['diagnostics'] and row['reader_basis']['unobserved_inputs']==['figures:reader-plot']
    with pytest.raises(ValueError,match='INPUT_UNRESOLVED'):
        change(tmp_path,row['edit_action'],changes={},
               input_observations={'figures:reader-plot':row['reader_basis']['inputs']['figures:reader-plot']})


def test_legacy_list_precedence_and_array_choices_without_migration(tmp_path):
    from laplace.pipeline import visual_production as vp
    manuscript,_,_=_section_fixture(tmp_path)
    data=_rendered_reader_plot(tmp_path,manuscript)
    _rendered_reader_plot(tmp_path,manuscript,'other')
    path=manuscript/'manuscript_spec.json'
    canonical=json.loads(path.read_text());specs=canonical.pop('figure_specs')
    path.write_text(json.dumps(canonical))
    legacy=manuscript/'visual_specs.json'
    legacy.write_text(json.dumps({'specs':specs}))
    before=legacy.read_bytes()
    assert vp.reader_inputs(manuscript,['reader-plot'],data.parent)['reader-plot']['status']=='CURRENT'
    assert legacy.read_bytes()==before and 'figure_specs' not in json.loads(path.read_text())
    canonical['figure_specs']=[];path.write_text(json.dumps(canonical))
    assert vp.reader_inputs(manuscript,['reader-plot'],data.parent)['reader-plot']['status']=='UNRESOLVED'
    canonical['figure_specs']=specs;path.write_text(json.dumps(canonical))
    action=detail(tmp_path)['reader_transition']['edit_action']
    change(tmp_path,action,changes={'function':'Explain','question_answered':'Which figures?',
        'entry_state':'Knows the axes','exit_state':'Can compare','figures':['reader-plot','other']})
    view=detail(tmp_path,edit_choices=True)['reader_transition']
    assert {k for k in view['reader_basis']['inputs'] if k.startswith('figures:')}=={'figures:reader-plot','figures:other'}
    field=next(f for f in view['edit_action']['fields'] if f['name']=='figures')
    assert {c['value'] for c in field['choices']}=={'reader-plot','other'}
    assert not view['diagnostics']


def test_visual_scientific_inputs_change_but_placement_prose_and_other_assets_do_not(tmp_path):
    from laplace.pipeline import visual_production as vp
    manuscript,chapter,_=_section_fixture(tmp_path)
    data=_rendered_reader_plot(tmp_path,manuscript)
    change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],
        changes={'function':'Explain','proposition':'Inspect the exact visual.','input_nodes':[],
                 'figure_anchor':'reader-plot'})
    row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    # Deliberately observe the newly introduced real input.
    change(tmp_path,row['edit_action'],changes={},input_observations=row['reader_basis']['inputs'])
    basis=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]['reader_basis']
    _rendered_reader_plot(tmp_path,manuscript,'unrelated')
    assert reader_plan.compare_basis('book',tmp_path,basis)['status']=='CURRENT'
    writing_tools.execute(tmp_path,'book','work','visual_place',{'id':'reader-plot',
        'file':chapter.relative_to(tmp_path).as_posix(),'after_line':2})
    chapter.write_text(chapter.read_text()+'\nLater prose does not change a drawing input.\n')
    assert reader_plan.compare_basis('book',tmp_path,basis)['status']=='CURRENT'
    old=vp.load(manuscript)['specs']
    selected=next(s for s in old if s['id']=='reader-plot')
    writing_tools.execute(tmp_path,'book','work','visual_create',{'spec':{'id':'reader-plot',
        'caption':'A changed explanatory caption.'},'expected_revision':vp.digest(selected)})
    assert reader_plan.compare_basis('book',tmp_path,basis)['status']!='CURRENT'
    writing_tools.execute(tmp_path,'book','work','visual_render',{'id':'reader-plot'})
    basis=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]['reader_basis']
    cuts=[]
    for value in [3,4]:
        data.write_text('x,y\n0,1\n1,'+str(value)+'\n')
        current=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
        cuts.append(current['reader_basis']['inputs']['figures:reader-plot'])
        assert current['diagnostics']
    assert len(set(cuts))==2


@pytest.mark.parametrize('changes,key',[({'input_nodes':['concept:unknown']},'concept:concept:unknown'),
    ({'citations':['Unknown']},'citation:Unknown'),({'equation_anchor':'unknown'},'equations:unknown')])
def test_declared_unknown_inputs_do_not_qualify_empty_hash(tmp_path,changes,key):
    _section_fixture(tmp_path)
    change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],
        changes={'function':'Explain','proposition':'A missing input.','input_nodes':[],**changes})
    row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    assert key in row['reader_basis']['unobserved_inputs'] and row['diagnostics']
    assert reader_plan.compare_basis('book',tmp_path,row['reader_basis'])['status']!='CURRENT'


def _rendered_reader_plot(root, manuscript, ident='reader-plot', *, render=True):
    """Real canonical visual owner and renderer, no shadow figures dictionary."""
    from laplace.pipeline import registry
    record=registry.resolve('book',repo_root=root)
    base=record.path(record.project_dir,root)
    data=base/'reader-values.csv'
    data.write_text('x,y\n0,1\n1,2\n')
    spec={'id':ident,'kind':'plot','title':'Illustrative reader input',
          'question':'How does the illustrative value change?',
          'caption':'Illustrative fixture data, not an empirical result.',
          'source_data':'reader-values.csv','x':'x','series':['y']}
    writing_tools.execute(root,'book','work','visual_create',{'spec':spec})
    if render:writing_tools.execute(root,'book','work','visual_render',{'id':ident})
    return data


def test_canonical_visual_reader_pin_choices_and_unplaced_bytes(tmp_path):
    from laplace.pipeline import visual_production
    manuscript,_,_=_section_fixture(tmp_path)
    data=_rendered_reader_plot(tmp_path,manuscript)
    change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],
           changes={'function':'Explain','proposition':'Use this illustrative plot.',
                    'input_nodes':[],'figure_anchor':'reader-plot'})
    row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    assert row['reader_basis']['inputs']['figures:reader-plot']!=reader_plan.fingerprint(None)
    assert any(link['kind']=='visual' and link['status']=='CURRENT' for link in row['links'])
    assert not row['diagnostics']
    choices=detail(tmp_path,edit_choices=True)['paragraph_plan']['paragraphs']['items'][0]['edit_action']['fields']
    field=next(f for f in choices if f['name']=='figure_anchor')
    assert [c['value'] for c in field['choices']]==['reader-plot']
    assert field['choices'][0]['read']['payload']=={'id':'reader-plot'}
    basis=row['reader_basis']
    assert reader_plan.compare_basis('book',tmp_path,basis)['status']=='CURRENT'
    assert detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]['reader_basis']==basis
    spec=visual_production.load(manuscript)['specs'][0]
    assert not spec.get('section')
    output=manuscript/spec['render']['outputs'][0]
    output.write_bytes(output.read_bytes()+b'\nfirst byte mutation')
    first=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    output.write_bytes(output.read_bytes()+b'\nsecond byte mutation')
    second=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    assert first['reader_basis']['inputs']!=second['reader_basis']['inputs']
    assert first['diagnostics'] and second['diagnostics']
    assert reader_plan.compare_basis('book',tmp_path,basis)['status']!='CURRENT'


@pytest.mark.parametrize('anchor',['unknown','reader-plot, other'])
def test_unresolved_visual_never_qualifies_equal_subject_refs(tmp_path,anchor):
    _section_fixture(tmp_path)
    change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],
           changes={'function':'Explain','proposition':'A missing visual.',
                    'input_nodes':[],'figure_anchor':anchor})
    row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    assert row['diagnostics']
    assert row['reader_basis']['unobserved_inputs']==['figures:'+anchor]
    assert reader_plan.compare_basis('book',tmp_path,row['reader_basis'])['status']!='CURRENT'
    ref=reader_plan.subjects_ref([row['reader_basis']])
    assert not reader_plan.subjects_ref_current('book',tmp_path,ref)


def detail(root, **scope):
    return project_structure.read('book', {'view': 'detail', 'section_ids': ['first'], **scope}, root)['sections'][0]


def change(root, action, **extra):
    return writing_tools.execute(root, 'book', 'work', 'structure_change', {**action['payload'], **extra})


def test_existing_contract_shape_guarded_publication_and_scoped_currentness(tmp_path):
    manuscript, _, _ = _section_fixture(tmp_path)
    selected = detail(tmp_path)
    assert selected['reader_transition']['status'] == 'NOT_DECLARED'
    action = selected['reader_transition']['edit_action']
    saved = change(tmp_path, action, changes={'entry_state': 'Knows the question', 'exit_state': 'Understands the argument'})
    assert saved['plan_publication']['status'] == 'COMMITTED'
    assert saved['revision'].startswith('sha256:')
    contracts = json.loads((manuscript / 'section_contracts.json').read_text())
    assert contracts['sections']['first']['entry_state'] == 'Knows the question'
    assert detail(tmp_path)['reader_transition']['input_currentness']['status'] == 'CURRENT'
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        change(tmp_path, action, changes={'entry_state': 'Lost update'})


def test_paragraph_id_survives_reorder_and_retirement(tmp_path):
    _section_fixture(tmp_path)
    action = detail(tmp_path)['paragraph_plan']['create_action']
    ident = action['payload']['paragraph_id']
    change(tmp_path, action, changes={'proposition': 'First planned proposition'})
    view = detail(tmp_path)['paragraph_plan']
    assert view['paragraphs']['items'][0]['paragraph_id'] == ident
    change(tmp_path, view['paragraphs']['items'][0]['remove_action'])
    fresh = detail(tmp_path)['paragraph_plan']['create_action']
    assert fresh['payload']['paragraph_id'] != ident
    change(tmp_path, fresh, changes={'proposition': 'New independent unit'})
    with pytest.raises(ValueError, match='absent'):
        detail(tmp_path, paragraph_id=ident)


def test_colon_path_and_failed_publish_reserves_id(tmp_path, monkeypatch):
    from pathlib import Path
    from laplace.manuscript import storyboard
    from laplace.pipeline import narrative
    manuscript, _, _ = _section_fixture(tmp_path)
    path = manuscript / 'projection_plan.json'
    plan = json.loads(path.read_text())
    plan['sections'][0]['id'] = 'sec:intro'
    for row in plan['sections']:
        if row.get('parent_id') == 'first': row['parent_id'] = 'sec:intro'
    path.write_text(json.dumps(plan))
    def selected():
        return project_structure.read('book', {'view':'detail','section_ids':['sec:intro']}, tmp_path)['sections'][0]
    action = selected()['paragraph_plan']['create_action']
    retired = action['payload']['paragraph_id']
    original = Path.replace
    def fail_publication(path, target):
        if str(target).endswith('sec_intro.json'): raise OSError('fixture publication failure')
        return original(path, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'replace', fail_publication)
        with pytest.raises(storyboard.PlanPublicationFailure) as caught:
            change(tmp_path, action, changes={'proposition':'First attempt'})
    assert caught.value.details['plan_publication']['status'] == 'COMPENSATED'
    assert not list(manuscript.rglob('*.pending'))
    fresh = selected()['paragraph_plan']['create_action']
    assert fresh['payload']['paragraph_id'] != retired
    change(tmp_path, fresh, changes={'proposition':'New attempt'})
    assert narrative.load_section('book', 'sec:intro', tmp_path)['paragraphs'][0]['paragraph_id'] == fresh['payload']['paragraph_id']
    assert not (manuscript / 'narrative' / 'sec:intro.json').exists()


def test_reader_review_preserves_sibling_standing_and_reopens_changed_subject(tmp_path):
    from laplace.work import project_work
    manuscript, _, _ = _section_fixture(tmp_path)
    change(tmp_path, detail(tmp_path)['reader_transition']['edit_action'], changes={'entry_state':'Original entry'})
    view = detail(tmp_path)['reader_transition']
    task = writing_tools.execute(tmp_path, 'book', 'work', 'task', view['review_action']['payload'])
    assert task['read_handle']['operation'] == 'project'
    evidence = tmp_path / 'review-evidence.md'
    evidence.write_text('Reviewed the exact reader transition.')
    recorded = {'id':'fixture-review','project':'book','status':'done','task_kind':'reader-review',
        'reader_basis':view['reader_basis'],'evidence_receipts':project_work._evidence_receipts(tmp_path,['review-evidence.md'])}
    assert project_work._completion_currentness(recorded,tmp_path)['status']=='CURRENT'
    sibling = project_structure.read('book', {'view':'detail','section_ids':['second']},tmp_path)['sections'][0]
    change(tmp_path,sibling['reader_transition']['edit_action'],changes={'entry_state':'Unrelated sibling'})
    assert project_work._completion_currentness(recorded,tmp_path)['status']=='CURRENT'
    change(tmp_path,detail(tmp_path)['reader_transition']['edit_action'],changes={'entry_state':'Changed entry'})
    stale=project_work._completion_currentness(recorded,tmp_path)
    assert stale['status']=='STALE' and 'authored-subject' in stale['changed_inputs']


def test_shown_reader_subject_observation_refuses_stale_send(tmp_path):
    from laplace.manuscript import bindings
    _section_fixture(tmp_path)
    initial=project_structure.read('book', {'view':'detail','section_ids':['first']},tmp_path)
    shown=initial['structure_observation']
    assert shown['source_files']
    assert bindings.validate_observation('book',tmp_path,shown)==shown
    change(tmp_path,initial['sections'][0]['reader_transition']['edit_action'],changes={'entry_state':'New authored entry'})
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        bindings.validate_observation('book',tmp_path,shown)


def test_reorder_reopens_adjacent_reader_expectation_without_rewriting_text(tmp_path):
    _section_fixture(tmp_path)
    for text in ('Introduce the receipt', 'Use the preceding receipt', 'A later result', 'An independent coda'):
        change(tmp_path, detail(tmp_path)['paragraph_plan']['create_action'], changes={'proposition':text,'from_previous':'Use previous understanding'})
    before=detail(tmp_path)['paragraph_plan']
    ids=before['reorder_action']['payload']['order']
    held=[row['reader_basis'] for row in before['paragraphs']['items']]
    action=before['reorder_action']
    change(tmp_path,action,order=[ids[1],ids[0],ids[2],ids[3]])
    after=detail(tmp_path)['paragraph_plan']['paragraphs']['items']
    assert [row['paragraph_id'] for row in after]==[ids[1],ids[0],ids[2],ids[3]]
    assert after[0]['from_previous']=='Use previous understanding'
    assert all(reader_plan.compare_basis('book',tmp_path,basis)['status']=='STALE' for basis in held[:3])
    assert reader_plan.compare_basis('book',tmp_path,held[3])['status']=='CURRENT'
    assert 'reader-neighbors' in after[0]['input_currentness']['changed_inputs']


def test_native_generic_recipe_and_http_use_same_owner(tmp_path):
    from laplace.native import verbs as writing_verbs
    from laplace.web import project_work_surface, authoring as authoring_surface
    _section_fixture(tmp_path)
    action=detail(tmp_path)['reader_transition']['edit_action']
    payload={**action['payload'],'changes':{'entry_state':'Observed through native recipe'}}
    route, request=writing_verbs.from_owner_call('structure_change',payload,project='book',root=tmp_path)
    assert route.concept=='artifact@section'
    saved=writing_tools.request(tmp_path,'book','work',request)
    assert saved['owner_response']['plan_publication']['complete'] is True
    action=detail(tmp_path)['reader_transition']['edit_action']
    response=project_work_surface.handle('/work/structure/change',{},'POST',json.dumps({
        'project':'book',**action['payload'],'changes':{'exit_state':'Understands the native/human join'}}).encode(),repo_root=tmp_path)
    assert response[0]==200
    receipt=json.loads(response[2])
    assert receipt['consumed_revision']==action['payload']['expected_contract_revision']
    assert receipt['operation']=='section_contract'
    with pytest.raises(ValueError,match='structure_change'):
        writing_tools.execute(tmp_path,'book','work','store_artifact',{
            'scope':'project','path':'manuscript/section_contracts.json','content':'{}','before':None,'reason':'Attempt typed owner bypass'})


def test_exact_bib_entry_read_and_only_consumed_citation_invalidates(tmp_path):
    from laplace.manuscript import manuscript_source
    manuscript, source, _=_section_fixture(tmp_path)
    main=manuscript/'Fixture-Book.tex'
    main.write_text(main.read_text()+ '\n\\bibliography{references}\n')
    bib=manuscript/'references.bib'
    bib.write_text('@article{Alpha, title={Read this}}\n@article{Beta, title={Other work}}\n')
    change(tmp_path,detail(tmp_path)['reader_transition']['edit_action'],changes={'citations':['Alpha']})
    basis=detail(tmp_path)['reader_transition']['reader_basis']
    link=next(row['read'] for row in detail(tmp_path)['reader_transition']['links'] if row['kind']=='literature')
    entry=writing_tools.execute(tmp_path,'book','work',link['operation'],link['payload'])
    assert entry['status']=='AVAILABLE' and 'Read this' in entry['entries'][0]['content']
    bib.write_text(bib.read_text().replace('Other work','Unrelated changed work'))
    assert reader_plan.compare_basis('book',tmp_path,basis)['status']=='CURRENT'
    bib.write_text(bib.read_text().replace('Read this','Changed consumed support'))
    assert reader_plan.compare_basis('book',tmp_path,basis)['changed_inputs']==['citation:Alpha']


def test_display_does_not_load_unused_input_catalogues_and_choices_are_explicit(tmp_path, monkeypatch):
    from laplace.research import references_surface
    from laplace.pipeline import projection_spec
    _section_fixture(tmp_path)
    calls=[]
    bib=references_surface._bibliography_names
    ledger=projection_spec.effective_equation_ledger
    monkeypatch.setattr(references_surface,'_bibliography_names',lambda *args:(calls.append('bibliography'),bib(*args))[1])
    monkeypatch.setattr(projection_spec,'effective_equation_ledger',lambda *args:(calls.append('equations'),ledger(*args))[1])
    selected=detail(tmp_path)
    assert calls==[]
    read=selected['reader_transition']['edit_action']['choices_read']
    current=project_structure.read('book',read['payload'],tmp_path)['sections'][0]
    assert calls==['bibliography','equations']
    assert current['reader_transition']['edit_action']['payload']==selected['reader_transition']['edit_action']['payload']


def test_safe_text_save_retains_original_profile_basis_and_unobserved_new_input(tmp_path):
    _section_fixture(tmp_path)
    profiles=tmp_path/'profiles';profiles.mkdir()
    profile=profiles/'author_architecture.yaml'
    profile.write_text('profile:\n  narrative_arc:\n    summary: Explain the mechanism.\n  conclusion_posture:\n    summary: State implications.\n')
    shown=detail(tmp_path)['reader_transition']['edit_action']
    profile.write_text(profile.read_text().replace('Explain the mechanism.','Start with the main question.'))
    result=change(tmp_path,shown,changes={'entry_state':'Safe authored edit on displayed inputs'})
    assert result['plan_publication']['complete'] is True
    assert result['input_currentness']['status']=='STALE'
    assert result['input_currentness']['changed_inputs']==['architecture']
    current=detail(tmp_path)['reader_transition']
    assert current['input_currentness']['status']=='STALE'
    result=change(tmp_path,current['edit_action'],changes={'citations':['new-unobserved-key']})
    assert result['input_currentness']['status']=='UNOBSERVED'
    assert result['input_currentness']['unobserved_inputs']==['citation:new-unobserved-key']


def test_disjoint_profile_field_does_not_stale_observed_section(tmp_path):
    _section_fixture(tmp_path)
    profiles=tmp_path/'profiles';profiles.mkdir()
    profile=profiles/'author_architecture.yaml'
    profile.write_text('profile:\n  narrative_arc:\n    summary: Explain the mechanism.\n  conclusion_posture:\n    summary: State implications.\n')
    shown=detail(tmp_path)['reader_transition']['edit_action']
    profile.write_text(profile.read_text().replace('State implications.','A different conclusion posture.'))
    result=change(tmp_path,shown,changes={'entry_state':'Unrelated profile field moved'})
    assert result['input_currentness']['status']=='CURRENT'


def _imported_reader(root, shape='mip', readonly=False):
    from laplace.projects import library
    from laplace.manuscript import manuscript_source
    relative = ('synthetics papers/corpus-as-a-state/reconstruction/output/pdf/v2.1'
                if shape=='mip' else 'synthetics papers/relational-frontend/paper')
    manuscript=root/relative
    manuscript.mkdir(parents=True)
    source=manuscript/'main.tex'
    source.write_text('\\documentclass{book}\n\\begin{document}\n\\chapter{First}\nFirst body.\n\\end{document}\n')
    code,value=library.import_source({'name':'book','title':'Imported shape',
        'root':source.relative_to(root).as_posix(),'editable':not readonly},root)
    assert code==201,value
    selected=manuscript_source.resolve('book',repo_root=root)
    assert selected['read_only'] is readonly
    assert not manuscript.is_relative_to(root/'writing_projects/book')
    current=writing_tools.execute(root,'book','work','structure',{})
    assert not current.get('sections')
    count=21 if shape=='mip' else 1
    result=writing_tools.execute(root,'book','work','structure_change',{
        'operation':'initialize','expected_revision':current['revision'],
        'expected_source_revision':current['selected_source']['revision'],
        'sections':[{'id':'first' if i==0 else 'extra-'+str(i),'title':'First' if i==0 else 'Extra '+str(i),
                     'kind':'chapter','file':'main.tex'} for i in range(count)]})
    assert result
    if not readonly:
        outline=writing_tools.execute(root,'book','work','structure',{'view':'outline'})
        summary=writing_tools.execute(root,'book','work','structure',{'view':'summary'})
        heading=next(h for h in outline['headings']['items'] if h['heading_before']=='\\chapter{First}')
        writing_tools.execute(root,'book','work','structure_change',{'operation':'bind_source',
            'section_id':'first','file':heading['file'],'line':heading['line'],
            'heading_before':heading['heading_before'],'expected_plan_revision':summary['authority']['plan_revision'],
            'expected_selection':outline['selected_source']['selection_identity'],
            'expected_source_digest':outline['sources'][heading['file']]['source_digest']})
    return manuscript,source


@pytest.mark.parametrize('shape',['mip','rf'])
def test_imported_reader_native_publication_scope_paragraphs_and_cold_read(tmp_path,shape):
    import os,subprocess,sys
    from pathlib import Path
    from laplace.projects import artifacts
    manuscript,source=_imported_reader(tmp_path,shape)
    action=detail(tmp_path)['reader_transition']['edit_action']
    original_path=action['payload']['expected_reader_basis']['path']
    saved=change(tmp_path,action,changes={'function':'Motivate the construction','question_answered':'What survives?',
        'entry_state':'Knows the example','exit_state':'Can use the construction'})
    assert saved['scope']=='manuscript' and saved['artifact_path']=='section_contracts.json'
    assert saved['path']==(manuscript/'section_contracts.json').relative_to(tmp_path).as_posix()
    assert saved['reader_basis']['path']==original_path
    assert saved['plan_publication']['complete']
    observed=artifacts.read(tmp_path,'book',{'id':saved['id']})
    assert observed['scope']=='manuscript' and observed['update_handle'] is None
    ids=[]
    for proposition in ['State the question','Explain its consequence']:
        created=change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],
            changes={'function':'Explain','proposition':proposition})
        ids.append(created['paragraph_id'])
        assert created['scope']=='manuscript'
    view=detail(tmp_path)['paragraph_plan']
    change(tmp_path,view['paragraphs']['items'][0]['edit_action'],changes={'explanation':'A controlled explanation.'})
    view=detail(tmp_path)['paragraph_plan']
    changed=change(tmp_path,view['reorder_action'],order=list(reversed(ids)))
    assert changed['reader_basis']['path']==(manuscript/'narrative/first.json').relative_to(tmp_path).as_posix()
    final=detail(tmp_path)
    assert [p['paragraph_id'] for p in final['paragraph_plan']['paragraphs']['items']]==list(reversed(ids))
    assert final['source']['precision']=='EXACT_HEADING'
    # A new process reloads custody and the typed owner, not just an in-process cache.
    script="import sys,json;from pathlib import Path;sys.path[:0]=json.loads(sys.argv[1]);from laplace.manuscript import project_structure;from laplace.projects import artifacts;r=Path(sys.argv[2]);d=project_structure.read('book',{'view':'detail','section_ids':['first']},r)['sections'][0];a=artifacts.read(r,'book',{'id':sys.argv[3]});print(json.dumps({'ids':[x['paragraph_id'] for x in d['paragraph_plan']['paragraphs']['items']],'scope':a['scope'],'path':a['path'],'basis':d['reader_transition']['reader_basis']['path']}))"
    checkout=Path(__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-I','-B','-c',script,json.dumps([str(checkout/'src')]),
        str(tmp_path),saved['id']],capture_output=True,text=True,env={**os.environ,'LAPLACE_STATE':str(tmp_path/'cold-state')})
    assert run.returncode==0,run.stderr
    cold=json.loads(run.stdout)
    assert cold=={'ids':list(reversed(ids)),'scope':'manuscript','path':saved['path'],'basis':original_path}
    with pytest.raises(ValueError,match='structure_change'):
        writing_tools.execute(tmp_path,'book','work','store_artifact',{'path':'section_contracts.json',
            'scope':'manuscript','content':'{}','before':None,'reason':'Typed bypass must refuse'})


def test_imported_reader_wrong_basis_and_readonly_do_not_publish(tmp_path):
    manuscript,_=_imported_reader(tmp_path)
    action=detail(tmp_path)['reader_transition']['edit_action']
    basis={**action['payload']['expected_reader_basis'],'path':'writing_projects/book/section_contracts.json'}
    with pytest.raises(ValueError,match='original exact authored subject basis'):
        change(tmp_path,action,changes={'entry_state':'Wrong home'},expected_reader_basis=basis)
    assert not (manuscript/'section_contracts.json').exists()
    # Change selected policy after displaying an action, through a fixture registry
    # edit, not by granting ART authority to a client.
    registry=tmp_path/'registry_projects.json'
    value=json.loads(registry.read_text())
    value['projects'][0]['manifest']['document']['read_only']=True
    registry.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='(read-only|writable|Reader artifact)'):
        change(tmp_path,action,changes={'entry_state':'Must not write readonly source'})
    assert not (manuscript/'section_contracts.json').exists()


@pytest.mark.parametrize('escape',['workspace','selected-home'])
def test_imported_reader_symlink_escape_refuses(tmp_path,escape):
    manuscript,_=_imported_reader(tmp_path)
    other=(tmp_path.parent/(tmp_path.name+'-outside') if escape=='workspace' else tmp_path/'other-home')
    other.mkdir()
    target=other/'contracts.json'
    target.write_text('{"sections":{}}')
    (manuscript/'section_contracts.json').symlink_to(target)
    before=target.read_bytes()
    with pytest.raises(ValueError,match='(workspace|namespace|selected manuscript|artifact)'):
        change(tmp_path,detail(tmp_path)['reader_transition']['edit_action'],changes={'entry_state':'No escape'})
    assert target.read_bytes()==before


def test_imported_reader_legacy_lineage_coordinate_uses_same_scope(tmp_path):
    from laplace.projects import artifacts
    from laplace.pipeline import registry
    _imported_reader(tmp_path)
    path=registry.resolve('book',repo_root=tmp_path).stage_path('decisions',tmp_path)/'first.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    # Existing decisions loader accepts the stage's array format.
    path.write_text(json.dumps({'section_id':'first','decisions':[
        {'kind':'retain','spec_id':'first-p1','rationale':'Retained fixture decision'}]}))
    lineage=reader_plan.lineage('book',tmp_path,'first','first-p1')
    assert lineage['read']['payload']['scope']=='manuscript'
    read=artifacts.read(tmp_path,'book',lineage['read']['payload'])
    assert read['path']==path.relative_to(tmp_path).as_posix()


@pytest.mark.parametrize('source_state',['empty','missing'])
def test_project_contained_reader_planning_precedes_nonempty_manuscript(tmp_path,source_state):
    from laplace.manuscript import manuscript_source
    from laplace.projects import artifacts
    manuscript,_,_=_section_fixture(tmp_path)
    selected=manuscript_source.resolve('book',repo_root=tmp_path)
    source=tmp_path/selected['root']
    if source_state=='missing':
        source.unlink()
    else:
        source.write_text('\\documentclass{book}\n\\begin{document}\n\\end{document}\n')
    selected=manuscript_source.resolve('book',repo_root=tmp_path)
    assert selected['status'] in {'missing','empty'} and not selected['read_only'] and not selected['foreign']
    # Native detail/action/commit, not a private writer bypass. Planning may
    # precede prose, while programme completion retains its stronger readiness.
    view=detail(tmp_path)
    action=view['reader_transition']['edit_action']
    result=change(tmp_path,action,changes={'function':'Plan before prose','question_answered':'What should this explain?',
        'entry_state':'Knows the intended question','exit_state':'Can follow the planned construction'})
    assert result['scope']=='project' and result['artifact_path']=='manuscript/section_contracts.json'
    assert result['reader_basis']['path']==action['payload']['expected_reader_basis']['path']
    assert result['plan_publication']['status']=='COMMITTED' and result['plan_publication']['complete']
    assert artifacts.read(tmp_path,'book',{'id':result['id']})['scope']=='project'
    assert detail(tmp_path)['reader_transition']['status']=='DECLARED'
    paragraph=change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],
        changes={'function':'Explain','proposition':'A pre-prose planned proposition.'})
    assert paragraph['scope']=='project' and paragraph['plan_publication']['complete']
    row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    assert row['paragraph_id']==paragraph['paragraph_id']


def test_imported_reader_readonly_transition_records_actual_owner_boundary(tmp_path,monkeypatch):
    """Published owner coordinates survive policy transition, never write authority."""
    from laplace.projects import artifacts
    from laplace.manuscript import manuscript_source
    from laplace.writing import records
    manuscript,source=_imported_reader(tmp_path)
    contract=change(tmp_path,detail(tmp_path)['reader_transition']['edit_action'],
        changes={'function':'Explain','question_answered':'What persists?','entry_state':'Knows the source',
                 'exit_state':'Can follow the construction'})
    paragraph=change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],
        changes={'function':'Explain','proposition':'Retain this exact logical unit.'})
    ident=paragraph['paragraph_id']
    decision=writing_tools.execute(tmp_path,'book','work','store_artifact',{
        'path':'decisions/first.json','scope':'manuscript','before':None,
        'content':json.dumps({'section_id':'first','decisions':[{
            'kind':'retain','spec_id':ident,'rationale':'Retain the exact fixture paragraph.'}]}),
        'reason':'Actual existing decisions artifact through its artifact owner.'})
    lineage=reader_plan.lineage('book',tmp_path,'first',ident)
    assert lineage['status']=='RECORDED' and len(lineage['items'])==1
    assert lineage['read']['payload']=={'path':'decisions/first.json','scope':'manuscript'}
    assert artifacts.read(tmp_path,'book',lineage['read']['payload'])['path']==decision['path']
    for saved in (contract,paragraph,decision):
        assert writing_tools.execute(tmp_path,'book','work','read_artifact',{'id':saved['id']})['scope']=='manuscript'
    held=detail(tmp_path)
    held_basis=held['reader_transition']['reader_basis']
    subject_key=('book',contract['reader_basis']['path'],'first')
    metadata=json.loads(json.dumps(records.index(tmp_path).reader_subjects[subject_key]))
    source_before=source.read_bytes()
    files={p:p.read_bytes() for p in (manuscript/'section_contracts.json',
        manuscript/'narrative/first.json',manuscript/'decisions/first.json')}
    context_before=artifacts.context(tmp_path,'book')
    # Only this synthetic declaration's read_only flag changes, not its homes,
    # source selection, IDs, ART scopes or bytes. Never a live project mutation.
    registry=tmp_path/'registry_projects.json'
    declared=json.loads(registry.read_text())
    declared['projects'][0]['manifest']['document']['read_only']=True
    registry.write_text(json.dumps(declared))
    selected=manuscript_source.resolve('book',repo_root=tmp_path)
    context_after=artifacts.context(tmp_path,'book')
    assert selected['read_only'] and selected['root']==source.relative_to(tmp_path).as_posix()
    assert context_after['base']==context_before['base']==tmp_path/'writing_projects/book'
    assert context_after['source']['storage_dir']=='writing_projects/book'
    observed=detail(tmp_path)
    assert observed['reader_transition']['status']=='DECLARED'
    assert observed['reader_transition']['reader_basis']==held_basis
    assert observed['paragraph_plan']['paragraphs']['items'][0]['paragraph_id']==ident
    assert records.index(tmp_path).reader_subjects[subject_key]==metadata
    # Read and identity opt in internally, with exact current byte pins.
    # Neither the request nor its old receipt grants write authority.
    for saved in (contract,paragraph,decision):
        for request in ({'id':saved['id']},{'path':saved['artifact_path'],'scope':'manuscript'}):
            request={**request,'expected_sha256':saved['revision']}
            read=writing_tools.execute(tmp_path,'book','work','read_artifact',request)
            assert read['scope']=='manuscript' and read['path']==saved['path']
            assert read['revision']==saved['revision'].removeprefix('sha256:') and read['read_only']
            assert read['update_handle'] is None
            observed_identity=artifacts.identity(tmp_path,'book',request)
            assert observed_identity['path']==saved['path'] and observed_identity['revision']==saved['revision'].removeprefix('sha256:')
            for owner in (artifacts.read,artifacts.identity):
                with pytest.raises(ValueError,match='(CHANGED_INPUT|changed|pin|identity)'):
                    owner(tmp_path,'book',{**request,'expected_sha256':'0'*64})
    catalogue=artifacts.catalogue(tmp_path,'book')
    assert catalogue['gaps']==[]
    assert {row['id'] for row in catalogue['materials']} >= {contract['id'],paragraph['id'],decision['id']}
    assert all(row['update_handle'] is None for row in catalogue['materials'] if row['scope']=='manuscript')
    evidence=artifacts.evidence_descriptor(tmp_path,'book',{'id':decision['id'],'expected_sha256':decision['revision']})[0]
    assert artifacts.read(tmp_path,'book',evidence['read']['payload'])['revision']==decision['revision']
    denied=reader_plan.lineage('book',tmp_path,'first',ident)
    # Default resolver MUST remain strict even if real read/identity callers
    # later gain an owner-internal opt-in. A caller cannot grant itself access.
    with pytest.raises(ValueError,match='manuscript source is read-only'):
        artifacts.resolve_path(tmp_path,'book','section_contracts.json','manuscript')
    with pytest.raises(ValueError,match='read-only'):
        change(tmp_path,observed['reader_transition']['edit_action'],changes={'entry_state':'Must refuse'})
    with pytest.raises(ValueError,match='read-only'):
        writing_tools.execute(tmp_path,'book','work','store_artifact',{
            'path':'decisions/second.json','scope':'manuscript','content':'{}','before':None,
            'reason':'Readonly writes must still refuse'})
    with pytest.raises(ValueError,match='inside the selected project'):
        writing_tools.execute(tmp_path,'book','work','read_artifact',{
            'path':'../../'+contract['path'],'scope':'project'})
    assert source.read_bytes()==source_before
    assert all(path.read_bytes()==raw for path,raw in files.items())
    assert denied['status']=='RECORDED' and len(denied['items'])==1
    assert denied['read']['payload']=={'path':'decisions/first.json','scope':'manuscript'}
    assert artifacts.read(tmp_path,'book',denied['read']['payload'])['revision']==decision['revision']
    # These use actual persisted owner receipts, not forged records or paths.
    for owner in (artifacts.read,artifacts.identity):
        with pytest.raises(ValueError,match='another project'):
            owner(tmp_path,'book',{'id':decision['id'],'project':'foreign'})
        with pytest.raises(ValueError,match='Unknown project'):
            owner(tmp_path,'unregistered',{'path':'decisions/first.json','scope':'manuscript'})
        with pytest.raises(ValueError,match='Unknown artifact'):
            owner(tmp_path,'book',{'id':'ART-'+'0'*32})
        with pytest.raises(ValueError,match='inside the selected project'):
            owner(tmp_path,'book',{'path':'../first.json','scope':'manuscript'})
        with pytest.raises(ValueError,match='inside the selected project'):
            owner(tmp_path,'book',{'path':str(manuscript/'decisions/first.json'),'scope':'manuscript'})
        with pytest.raises(ValueError,match='canonical-record operation'):
            owner(tmp_path,'book',{'path':'main.tex','scope':'manuscript'})
    with pytest.raises(ValueError,match="Additional properties are not allowed .*allow_read_only"):
        writing_tools.execute(tmp_path,'book','work','store_artifact',{
            'path':'decisions/second.json','scope':'manuscript','content':'{}','before':None,
            'allow_read_only':True,'reason':'A payload cannot opt into write permission'})
    with pytest.raises(ValueError,match='read-only'):
        artifacts.store(tmp_path,'book',{'path':'decisions/second.json','scope':'manuscript',
            'content':'{}','before':None,'allow_read_only':True,'reason':'Internal store remains strict'})
    # Canonical browser handles are consumed at the actual HTTP adapter, not
    # approximated with a second native read or unguarded filesystem open.
    from urllib.parse import urlsplit,parse_qs
    from laplace.web import research_artifact_read
    for saved in (contract,paragraph,decision):
        query=parse_qs(urlsplit(saved['human_read']['url']).query)
        status,media,body=research_artifact_read.read('book',query,'GET',repo_root=tmp_path)
        assert status==200 and body==(tmp_path/saved['path']).read_bytes()
        # Path-only canonical read exercises the adapter's other exact branch.
        path_query={key:value for key,value in query.items() if key!='artifact_id'}
        assert research_artifact_read.read('book',path_query,'GET',repo_root=tmp_path)[0]==200
        assert research_artifact_read.read('book',{**query,'expected_sha256':['0'*64]},
            'GET',repo_root=tmp_path)[0] in {409,422}
        assert research_artifact_read.read('book',{**query,'path':['../outside.json']},
            'GET',repo_root=tmp_path)[0]==422

    # Explicit synthetic actor declarations, as in the existing dispatch owner
    # tests. No provider/child is launched and no read receipt is manufactured.
    # Every consumption fact below comes from native execute and its real bank.
    from laplace.writing import dispatch_parent,dispatch_returns
    from laplace.work import project_work
    from test_dispatch_plan_contract import example
    from test_writing_dispatch import CATALOGUE
    from laplace.writing import provider as writing_provider
    monkeypatch.setattr(writing_provider,'capabilities',lambda *a,**k:CATALOGUE)
    records.bank(tmp_path,{'record':'writing-session','id':'WS-reader-flow',
        'project':'book','provider':'claude','model':'haiku','effort':'low','role':'author'})
    records.bank(tmp_path,{'record':'writing-turn','id':'WT-reader-flow',
        'session_id':'WS-reader-flow','project':'book','mode':'work'})
    plan=example()
    made=writing_tools.execute(tmp_path,'book','work','dispatch_plan',{
        'title':'Exact reader evidence consumption','goal':plan['goal'],
        'path':'development/reader-consumption.json','plan':plan},turn_id='WT-reader-flow')
    project_work.transition('book',{'id':made['dispatch_id'],'status':'in-progress'},tmp_path,
        dispatch_receipt={'dispatch_admitted':True,'dispatch_parent_turn_id':'WT-reader-flow'})
    task=project_work._tasks('book',tmp_path)[made['dispatch_id']]
    required=[{'path':decision['path'],'sha256':decision['revision']}]
    assert dispatch_parent.consumption_errors(task,'book',tmp_path,required,actor_turn_id='WT-reader-flow')
    consumed=writing_tools.execute(tmp_path,'book','work','read_artifact',{
        'id':decision['id'],'expected_sha256':decision['revision'],'limit':40000},turn_id='WT-reader-flow')
    check=dispatch_returns.owner_check(tmp_path,'book','WT-reader-flow',paths={tmp_path/decision['path']})
    assert check['state']=='PASSED' and check['receipt_id']==consumed['read_receipt']['id']
    assert dispatch_parent.consumption_errors(task,'book',tmp_path,required,actor_turn_id='WT-reader-flow')==[]
    assert dispatch_parent.consumption_errors(task,'book',tmp_path,
        [{**required[0],'sha256':'0'*64}],actor_turn_id='WT-reader-flow')
    listed=writing_tools.execute(tmp_path,'book','work','author_history',{'view':'activity','limit':50})
    targets=[target for item in listed['items'] for target in item.get('targets',[])]
    assert any(target.get('kind')=='artifact' and target.get('id')==decision['id']
        and target.get('file')==decision['path'] for target in targets)
    # Changed bytes invalidate actual consumed output/digest coverage, without
    # weakening the original receipt or renewing its scientific status.
    decision_path=tmp_path/decision['path']
    decision_bytes=decision_path.read_bytes()
    decision_path.write_bytes(decision_bytes+b' ')
    assert dispatch_parent.consumption_errors(task,'book',tmp_path,required,actor_turn_id='WT-reader-flow')
    decision_path.write_bytes(decision_bytes)

    # A physical symlink cannot borrow access outside the selected manuscript.
    outside=tmp_path/'unselected'
    outside.mkdir()
    (manuscript/'borrowed').symlink_to(outside,target_is_directory=True)
    for owner in (artifacts.read,artifacts.identity):
        with pytest.raises(ValueError,match='escapes the selected project'):
            owner(tmp_path,'book',{'path':'borrowed/anything.json','scope':'manuscript'})
    # Inspect the same source selection after only its directory moves outside
    # this workspace behind a symlink. Its artifacts must not become readable.
    relocated=tmp_path.parent/(tmp_path.name+'-source-outside')
    manuscript.rename(relocated)
    manuscript.symlink_to(relocated,target_is_directory=True)
    for owner in (artifacts.read,artifacts.identity):
        with pytest.raises(ValueError,match='(eligible selected manuscript|workspace|outside)'):
            owner(tmp_path,'book',{'id':decision['id'],'expected_sha256':decision['revision']})


@pytest.mark.parametrize('scope',['manuscript','project'])
def test_large_readonly_http_recovery_keeps_exact_owner_receipt_and_pin(tmp_path,scope):
    """A 413 is a bounded read refusal, not a licence to read newer bytes."""
    from urllib.parse import urlsplit,parse_qs
    from laplace.projects import artifacts
    from laplace.web import research_artifact_read
    from laplace.manuscript import manuscript_source
    manuscript,source=_imported_reader(tmp_path,shape='rf')
    project_home=tmp_path/'writing_projects/book'
    registry=tmp_path/'registry_projects.json'
    declared=json.loads(registry.read_text())
    # MS reads can retain THREE disjoint homes. Project-scoped ART publication
    # uses the project home while editable, so preserve that physical state
    # home for this scope rather than moving an artifact to manufacture proof.
    if scope=='manuscript':
        state=tmp_path/'reader-state/book'
        state.mkdir(parents=True)
        declared['projects'][0]['manifest']['document']['state_dir']='reader-state/book'
        registry.write_text(json.dumps(declared))
        assert not state.is_relative_to(project_home) and not manuscript.is_relative_to(state)
    else:
        state=project_home
    content=''.join('Reader evidence row '+str(i)+': retain this exact owner-published observation and its original byte identity.\n'
        for i in range(900))
    raw=content.encode()
    assert len(raw)>65536
    saved=writing_tools.execute(tmp_path,'book','work','store_artifact',{
        'path':'large-reader-evidence.txt','scope':scope,'before':None,'content':content,
        'reason':'Real owner large-text fixture, no scientific result or fabricated receipt.'})
    original_path=tmp_path/saved['path']
    assert original_path.read_bytes()==raw
    declared=json.loads(registry.read_text())
    declared['projects'][0]['manifest']['document']['read_only']=True
    registry.write_text(json.dumps(declared))
    selected=manuscript_source.resolve('book',repo_root=tmp_path)
    assert selected['storage_dir']==state.relative_to(tmp_path).as_posix()
    assert artifacts.context(tmp_path,'book')['base']==state
    assert selected['root']==source.relative_to(tmp_path).as_posix()
    canonical=parse_qs(urlsplit(saved['human_read']['url']).query)
    pinned_links=[]
    for by_id in (True,False):
        request=canonical if by_id else {k:v for k,v in canonical.items() if k!='artifact_id'}
        code,_,body=research_artifact_read.read('book',request,'GET',repo_root=tmp_path)
        assert code==413
        recovery=json.loads(body)
        for kind in ('next_read','download'):
            offered=recovery[kind]
            query=parse_qs(urlsplit(offered).query)
            # Exact controls must survive actual owner-generated recovery URLs.
            assert query['project']==['book'] and query['scope']==[scope]
            assert query['path']==[saved['artifact_path']]
            assert query.get('owner')==['writing-artifact']
            assert query.get('expected_sha256')==[saved['revision'].removeprefix('sha256:')]
            assert query.get('artifact_id')==([saved['id']] if by_id else None)
            pinned_links.append(query)
            status,_,observed=research_artifact_read.read('book',query,'GET',repo_root=tmp_path)
            assert status==200
            if kind=='download':
                assert observed==raw
            else:
                page=json.loads(observed)
                assembled=page['content']
                assert page['sha256']==saved['revision'].removeprefix('sha256:')
                while page['next_offset'] is not None:
                    status,_,observed=research_artifact_read.read('book',
                        {**query,'offset':[str(page['next_offset'])]},'GET',repo_root=tmp_path)
                    assert status==200
                    page=json.loads(observed);assembled+=page['content']
                assert assembled.encode()==raw
    # No implicit capability appears in a generic, unpinned legacy request.
    generic={'project':['book'],'scope':[scope],'path':[saved['artifact_path']]}
    code,_,body=research_artifact_read.read('book',generic,'GET',repo_root=tmp_path)
    if code==413:
        for key in ('next_read','download'):
            query=parse_qs(urlsplit(json.loads(body)[key]).query)
            assert not {'owner','artifact_id','expected_sha256'}.intersection(query)
    else:
        assert code==404  # truthful generic namespace absence, never an ART fallback
    with pytest.raises(ValueError,match='read-only'):
        artifacts.resolve_path(tmp_path,'book',saved['artifact_path'],'manuscript')
    with pytest.raises(ValueError,match='read-only'):
        artifacts.store(tmp_path,'book',{'path':'must-not-write.txt','scope':'manuscript',
            'before':None,'content':content,'reason':'No recovery link grants a write'})
    for bad in ({**canonical,'owner':['foreign-owner']},
                {**canonical,'path':['../unselected.txt']},
                {**canonical,'scope':['foreign-scope']}):
        assert research_artifact_read.read('book',bad,'GET',repo_root=tmp_path)[0]==422
    assert research_artifact_read.read('unknown',canonical,'GET',repo_root=tmp_path)[0]!=200
    original_path.write_bytes(raw+b'A later byte revision.\n')
    actual=artifacts.identity(tmp_path,'book',{'path':saved['artifact_path'],'scope':scope})['revision']
    for query in pinned_links:
        code,_,body=research_artifact_read.read('book',query,'GET',repo_root=tmp_path)
        assert code==409
        mismatch=json.loads(body)
        assert mismatch['expected_sha256']==saved['revision'].removeprefix('sha256:')
        assert mismatch['actual_sha256']==actual and actual!=mismatch['expected_sha256']
    # An unpinned canonical owner read remains explicitly current, not falsely
    # frozen to the historical receipt. No migration or fabricated old pin.
    current={k:v for k,v in canonical.items() if k not in {'artifact_id','expected_sha256'}}
    code,_,body=research_artifact_read.read('book',current,'GET',repo_root=tmp_path)
    assert code==413
    for key in ('next_read','download'):
        query=parse_qs(urlsplit(json.loads(body)[key]).query)
        assert query['owner']==['writing-artifact']
        assert not {'artifact_id','expected_sha256'}.intersection(query)
    assert original_path.read_bytes()==raw+b'A later byte revision.\n'
