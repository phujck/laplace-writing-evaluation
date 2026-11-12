"""Real template candidate/source/build joins over tiny isolated documents."""
import copy
import json
from pathlib import Path
import pytest

from laplace.manuscript import manuscript_source
from laplace.projects import library as writing_projects
from laplace.writing import records as writing_records
from laplace.manuscript import document_templates as owner
from laplace.writing import records


@pytest.fixture
def case(tmp_path,monkeypatch):
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES',str(tmp_path/'workspaces'))
    status,value=writing_projects.create({'name':'template-book','title':'Template Fixture','kind':'book'},tmp_path)
    assert status==201,value
    source=manuscript_source.resolve('template-book',repo_root=tmp_path,include_candidates=False)
    path=tmp_path/source['root']
    path.write_text('\\documentclass{article}\n\\newcommand{\\kept}{Preserved definition}\n\\title{Exact title}\n\\begin{document}\n\\maketitle\nBody stays \\kept.\n\\end{document}\n')
    return tmp_path,path


def request(case,*,draft=False):
    root,path=case;source=manuscript_source.resolve('template-book',repo_root=root,include_candidates=False)
    content=path.read_text().replace('\\documentclass{article}','\\documentclass[11pt]{article}')
    return {'action':'prepare','source_edits':[{'file':source['root'],'content':content}],
        'guards':{'expected_selection':manuscript_source.selection_identity(source,'template-book'),
            'source_guards':{source['root']:owner.pin(path.read_bytes())}},'reason':'Preserve body and inspect typography',
        **({'draft_basis':{'file':source['root'],'revision':'draft-1'}} if draft else {})}


def prepared(case,*,draft=False):
    return owner.change('template-book',request(case,draft=draft),case[0],actor={'kind':'human'})


def test_saved_and_draft_preparation_are_immutable_nonmutating_and_reuse_custody(case,monkeypatch):
    root,path=case;before=path.read_bytes()
    from laplace.pipeline import authoring
    monkeypatch.setattr(authoring,'load',lambda *a,**k:pytest.fail('Unrelated legacy authoring history hydrated'))
    first=prepared(case);again=prepared(case)
    assert first['candidate_ref']==again['candidate_ref']
    assert path.read_bytes()==before and not (root/'.laplace-cache/writing-style').exists()
    assert first['currentness']['status']=='CURRENT' and first['build_action'] and first['build_status_read']
    assert first['apply_action'] is None and first['semantic_currentness']=='NOT_ASSERTED'
    draft=prepared(case,draft=True)
    assert draft['included_draft']=={'file':path.relative_to(root).as_posix(),'revision':'draft-1',
        'input_content_sha256':owner.pin(request(case)['source_edits'][0]['content'])}
    assert draft['candidate_ref']!=first['candidate_ref']
    assert len(records.index(root).template_candidates_by_project['template-book'])==2
    assert all(row.get('turn_id') is None for row in records.index(root).template_candidates_by_project['template-book'])
    changed=copy.deepcopy(first['candidate_ref']);changed['version']='sha256:'+'0'*64
    with pytest.raises(ValueError,match='exact immutable'):owner.candidate('template-book',changed,root)


def test_bounded_native_edits_match_whole_snapshot_without_copying_body(case):
    root,path=case;full=request(case)
    bounded={key:value for key,value in full.items() if key!='source_edits'}
    bounded['edits']=[{'file':path.relative_to(root).as_posix(),'line_start':1,'line_end':1,
        'before':'\\documentclass{article}','after':'\\documentclass[11pt]{article}'}]
    first=owner.change('template-book',bounded,root)
    second=prepared(case)
    assert first['candidate_ref']==second['candidate_ref']
    proposal=owner._application_proposal(owner.candidate('template-book',first['candidate_ref'],root)['proposal'])
    assert len(proposal['edits'])==1 and proposal['edits'][0]['line_end']==1
    assert 'Body stays' not in proposal['edits'][0]['after']


def test_original_parts_survive_source_drift_and_refuse_changed_target_or_byte_boundaries(case):
    root,path=case;value=prepared(case);ref=value['candidate_ref'];before=path.read_bytes()
    path.write_bytes(before.replace(b'Body stays',b'Later body stays'))
    later=owner.inspect('template-book',{'view':'template','candidate_ref':ref},root)
    assert later['currentness']['status']=='CHANGED_INPUT'
    payload=value['source_changes'][0]['reads']['original']['payload'];payload.pop('project')
    part=owner.inspect('template-book',payload,root)
    assert part['content']==before.decode() and part['coverage']['complete']
    with pytest.raises(ValueError,match='owner-issued changed-file'):
        owner.inspect('template-book',{**payload,'file':'other.tex'},root)
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        owner.change('template-book',request((root,path))|{'guards':request((root,path))['guards']|{'source_guards':{path.relative_to(root).as_posix():owner.pin(before)}}},root)


def test_defaults_resolution_preserves_empty_canonical_and_qualified_legacy_inputs(case):
    from laplace.manuscript import document_style
    from laplace.pipeline import projection_spec
    root,path=case;home=path.parent
    legacy=home/'document_style.json';legacy.write_text(json.dumps({'visuals':{'font_size':13}}))
    specpath=projection_spec.spec_path('template-book',root)
    spec=json.loads(specpath.read_text()) if specpath.is_file() else {'manuscript':{}};spec.setdefault('manuscript',{}).pop('presentation',None);specpath.write_text(json.dumps(spec))
    fallback=document_style.defaults_status('template-book',root)
    assert fallback['effective_origin']=='legacy-read-only-fallback' and fallback['values']['visuals']['font_size']==13
    spec['manuscript']['presentation']={};specpath.write_text(json.dumps(spec))
    canonical=document_style.defaults_status('template-book',root)
    assert canonical['values']=={} and canonical['legacy_conflict'] and canonical['effective_origin']=='canonical-spec'
    assert canonical['revision']!=fallback['revision']
    spec['manuscript']['presentation']=None;specpath.write_text(json.dumps(spec))
    with pytest.raises(ValueError,match='canonical presentation'):document_style.load('template-book',root)
    before=legacy.read_bytes()
    with pytest.raises(ValueError,match='two settings stores'):document_style.save('template-book',{},root)
    assert legacy.read_bytes()==before


def test_native_physical_owner_parts_avoid_legacy_history_and_pin_utf8_stream(case,monkeypatch):
    from laplace.native import tools as writing_tools
    from laplace.pipeline import authoring
    root,path=case;path.write_text(path.read_text().replace('Body stays',('α body '*1800)+'Body stays'))
    writing_records.bank(root,{'record':'writing-turn','id':'WT-template-read','project':'template-book','mode':'work'})
    monkeypatch.setattr(authoring,'_read',lambda *a,**k:pytest.fail('Legacy authoring history hydrated'))
    descriptor=owner.discovery('template-book',root)
    result=writing_tools.request(root,'template-book','work',descriptor['current_source_read']['native_request'],turn_id='WT-template-read')
    assert result.get('ok'),result
    value=result['owner_response'];assert len(json.dumps(result,ensure_ascii=False,indent=2).encode())<12000
    assert value['coverage']['has_more'] and not value['coverage']['complete'] and value['next_read']
    source_id=value['read_receipt']['id']
    assert records.selected_journal_fields('template-book',source_id,root,fields=['source_scope'])['source_scope'][0]['expected_source_digest']==owner.pin(path.read_bytes())
    path.write_text(path.read_text()+'% later drift\n')
    refused=writing_tools.request(root,'template-book','work',value['next_read']['native_request'],turn_id='WT-template-read')
    assert not refused.get('ok') and 'CHANGED_INPUT' in json.dumps(refused)


def build(case,value):
    import time
    from laplace.manuscript import projection_viewer as compiler
    from laplace.manuscript import build_jobs
    root,_=case;target=value['build_action']['payload']['build_target']
    code,started=compiler.recompile(target['root'],'template-book','author',repo_root=root,build_target=target)
    assert code==200,started
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        status=build_jobs.status(started['build_job'],'template-book',root)
        if not status['running'] and status.get('preview_publication')!='PENDING':break
        time.sleep(.02)
    else:pytest.fail('The isolated installed-toolchain candidate build did not settle.')
    assert status.get('ok') and status.get('preview_ref'),status
    return owner.inspect('template-book',{'view':'template','candidate_ref':value['candidate_ref'],
        'preview_ref':status['preview_ref']},root)


def test_actual_preview_apply_images_and_native_metadata_are_exact_and_body_preserving(case,monkeypatch):
    import base64,hashlib
    from laplace.projects import writing_sources
    from laplace.web import project_work_surface
    root,path=case;before=path.read_bytes();value=build(case,prepared(case,draft=True));proof=value['apply_action']['payload']['preview_ref']
    image=owner.inspect('template-book',{'view':'template','candidate_ref':value['candidate_ref'],'preview_ref':proof,'part':'preview-image','page':1},root)
    png=base64.b64decode(image['_image_content'][0]['data'])
    assert png.startswith(b'\x89PNG') and image['image_sha256']=='sha256:'+hashlib.sha256(png).hexdigest()
    for provider in ('codex','claude'):
        blocks=writing_sources.content_items({'ok':True,'owner_response':image},provider)
        assert len(blocks)==2 and '_image_content' not in blocks[0]['text']
        raw=blocks[1]['imageUrl'].split(',',1)[1] if provider=='codex' else blocks[1]['data']
        assert base64.b64decode(raw)==png
    query={'project':['template-book'],'candidate_ref':[json.dumps(value['candidate_ref'])],'preview_ref':[json.dumps(proof)],'format':['png'],'page':['1']}
    code,mime,human_png=project_work_surface.handle('/work/style/pdf',query,'GET',repo_root=root)
    assert (code,mime)==(200,'image/png') and human_png==png
    compact=owner.native_projection(value)
    assert compact['candidate_ref']==value['candidate_ref'] and compact['preview_image_read']['native_request']==value['preview_image_read']['native_request']
    assert image['apply_action']['native_request']==value['apply_action']['native_request']
    assert 'apply_action' not in compact and 'PNG media' in compact['native_instruction']
    assert len(json.dumps(compact,ensure_ascii=False,indent=2).encode())<14000
    from laplace.pipeline import authoring
    monkeypatch.setattr(authoring,'load',lambda *a,**k:pytest.fail('Template apply hydrated legacy authoring state'))
    answer=owner.change('template-book',{key:item for key,item in value['apply_action']['payload'].items() if key!='project'},root)
    assert answer['complete'] and answer['source_effect']['state']=='COMMITTED',answer
    assert path.read_bytes()==before.replace(b'\\documentclass{article}',b'\\documentclass[11pt]{article}')
    assert answer['included_draft']==value['included_draft'] and answer['current_document_read'] and answer['applied_source_reads']
    app=records.selected_journal_fields('template-book',answer['application_recording']['application_id'],root,fields=['candidate_id','turn_id','actor','approval_mode'])
    assert app['candidate_id']==value['candidate_ref']['id'] and app.get('turn_id') is None and app['actor']['kind']=='human' and app['approval_mode']=='document-template'


def test_unpublished_wa_recovers_only_durable_observation_without_source_replay(case,monkeypatch):
    root,path=case;value=build(case,prepared(case));bank=writing_records.bank
    with monkeypatch.context() as outage:
        def fail(root,row,**kwargs):
            if row.get('record')=='writing-application':raise OSError('Synthetic WA publication outage')
            return bank(root,row,**kwargs)
        outage.setattr(writing_records,'bank',fail)   # the owner and the facade alias
        partial=owner.change('template-book',{key:item for key,item in value['apply_action']['payload'].items() if key!='project'},root)
    assert partial['source_effect']['state']=='COMMITTED' and partial['application_recording']['status']=='UNPUBLISHED',partial
    assert not partial['application_recording'].get('application_id') and partial['recovery_action']
    assert not records.index(root).by_id.get(partial['application_recording']['allocated_application_id'])
    path.write_bytes(path.read_bytes()+b'% Later independent source edit.\n');saved=path.read_bytes()
    from laplace.manuscript import review_surface
    monkeypatch.setattr(review_surface,'adjudicate',lambda *a,**k:pytest.fail('Metadata recovery replayed source'))
    answer=owner.change('template-book',{key:item for key,item in partial['recovery_action']['payload'].items() if key!='project'},root)
    assert answer['metadata_only'] and answer['complete'] and answer['application_recording']['status']=='RECORDED'
    assert path.read_bytes()==saved and answer['source_currentness']=='HISTORICAL_RETAINED_EFFECT'


def test_reopen_missing_effect_observation_never_issues_fictitious_recovery(case):
    root,path=case;value=prepared(case);ref=value['candidate_ref']
    writing_records.bank(root,{'record':'writing-proposal-decision','id':'DEC-'+'1'*32,'project':'template-book',
        'candidate_id':ref['id'],'candidate_kind':'document-template','proposal_version':ref['version'],
        'decision':'template-application-start','actor':{'kind':'human'},'preview_ref':{}})
    reopened=owner.inspect('template-book',{'view':'template','candidate_ref':ref},root)
    assert reopened['application_recording']['status']=='UNKNOWN' and not reopened.get('recovery_action') and reopened['recording_gap']
