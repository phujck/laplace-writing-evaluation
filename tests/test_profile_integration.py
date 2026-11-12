"""Exact HTTP/native/profile queue joins over the existing tiny owner fixture."""
import json

import pytest

from laplace.core import grammar
from laplace.web import project_work_surface
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.manuscript import proposal_navigation
from laplace.work import history as author_history
from laplace.manuscript import profiles
from laplace.writing import records
from test_profile_candidates import fixture, architecture_content


def native(root, payload, *, write=False, mode='work'):
    request=profiles.handle('book',payload,write=write)['native_request']
    return writing_tools.call(root,'book',mode,request,turn_id='WT-profile-test')


def test_native_generated_candidate_and_http_apply_are_one_actual_owner_object(tmp_path):
    fixture(tmp_path)
    read=native(tmp_path,{'family':'architecture','scope':'workspace','view':'summary'})
    assert read.get('ok'),read
    value=read['owner_response'];base=grammar.to_owner_payload(value['propose_action']['native_request']['payload'])
    generated=native(tmp_path,{**base,'change':{'content':architecture_content()},'reason':'Explicit structural form suggestion.'},write=True)
    assert generated.get('ok'),generated
    candidate=generated['owner_response'];ref=candidate['candidate_ref']
    assert candidate['author']['kind']=='agent' and candidate['author']['turn_id']=='WT-profile-test'
    status,_,raw=project_work_surface.handle('/work/profiles/change',{},'POST',json.dumps(candidate['apply_action']['payload']).encode(),tmp_path)
    result=json.loads(raw);assert status==200,result
    assert result['candidate_ref']==ref and result['application_id']
    inspect=native(tmp_path,{'view':'candidate','candidate_ref':ref})
    assert inspect.get('ok'),inspect
    assert inspect['owner_response']['currentness']=='APPLIED_CURRENT'
    current=native(tmp_path,{'family':'architecture','scope':'workspace','view':'summary'})['owner_response']
    assert not current['confirm_action']['permitted']
    queue=proposal_navigation.read(tmp_path,'book',{'view':'queue'})
    assert queue['count']==0 and queue['pagination']['candidate_total']==0
    catalogue=profiles.inspect(None,{'family':'architecture','scope':'workspace','view':'candidates'},tmp_path)
    assert len(catalogue['candidates'])==1 and catalogue['candidates'][0]['custody_project']=='book'
    assert catalogue['coverage']['profile_bodies_loaded']==0


@pytest.mark.parametrize('scope',['workspace','project'])
def test_existing_voice_concepts_route_to_candidates_without_changing_direct_writer(tmp_path,scope):
    fixture(tmp_path)
    current=native(tmp_path,{'family':'voice','scope':scope,'view':'summary'})
    assert current.get('ok'),current
    value=current['owner_response'];base=grammar.to_owner_payload(value['propose_action']['native_request']['payload'])
    change={'content':'# Scoped shared voice\nExplain mechanisms.\n'} if scope=='workspace' else {'guidance':'This project only.'}
    proposed=native(tmp_path,{**base,'change':change,'reason':'Scoped preference.'},write=True)
    assert proposed.get('ok'),proposed
    applied=native(tmp_path,{'action':'apply','candidate_ref':proposed['owner_response']['candidate_ref']},write=True)
    assert applied.get('ok'),applied
    assert applied['owner_response']['application_id']


@pytest.mark.parametrize('count',[20,2000])
def test_actual_native_profile_envelope_parts_are_bounded(tmp_path,count):
    fixture(tmp_path)
    current=native(tmp_path,{'family':'voice','scope':'workspace','view':'summary'})['owner_response']
    base=grammar.to_owner_payload(current['propose_action']['native_request']['payload'])
    proposed=native(tmp_path,{**base,'change':{'content':'# Voice\n'+('Concrete résumé.\n'*count)},'reason':'Bounded profile.'},write=True)
    assert proposed.get('ok'),proposed
    assert len(json.dumps(proposed,ensure_ascii=False,indent=2).encode())<16000
    ref=proposed['owner_response']['candidate_ref'];part=native(tmp_path,{'view':'candidate','candidate_ref':ref,'part':'proposed'})
    assert part.get('ok'),part
    assert len(json.dumps(part,ensure_ascii=False,indent=2).encode())<16000


def test_global_context_picker_reads_registry_metadata_and_activity_classifies_preferences(tmp_path,monkeypatch):
    fixture(tmp_path)
    from laplace.manuscript import manuscript_source
    with monkeypatch.context() as bounded:
        bounded.setattr(manuscript_source,'resolve',lambda *a,**kw:pytest.fail('Context picker hydrated manuscript source'))
        result=writing_projects.app_settings(tmp_path,view='profile-contexts')
    assert [row['name'] for row in result['projects']]==['book','other']
    assert result['source_bodies_loaded'] is False
    current=profiles.inspect('book',{'family':'architecture','scope':'workspace'},tmp_path)
    base={key:value for key,value in current['propose_action']['payload'].items() if key!='project'}
    candidate=profiles.change('book',{**base,'change':{'content':architecture_content()},'reason':'Scoped settings.'},tmp_path)
    applied=profiles.change('book',{'action':'apply','candidate_ref':candidate['candidate_ref']},tmp_path)
    history=author_history.history('book',{'limit':50},tmp_path)
    rows=history['items']
    profile_rows=[row for row in rows if row['category']=='settings']
    assert profile_rows and all(row['category']!='manuscript' for row in profile_rows)
    assert any(row['summary']=='Profile preference applied' for row in profile_rows)


def test_supported_architecture_json_transport_applies_with_bounded_real_profile_bytes(tmp_path):
    import yaml
    from laplace.pipeline import narrative
    fixture(tmp_path)
    data={'profile':{f'field_{index}':{'summary':'"'*7000} for index in range(8)}}
    assert len(yaml.safe_dump(data).encode())<narrative.MAX_ARCHITECTURE_BYTES
    assert len(json.dumps(data).encode())>narrative.MAX_ARCHITECTURE_BYTES
    before=profiles.inspect('book',{'family':'architecture','scope':'workspace'},tmp_path)
    base={key:value for key,value in before['propose_action']['payload'].items() if key!='project'}
    candidate=profiles.change('book',{**base,'change':{'content':json.dumps(data)},'reason':'Exact supported typed transport.'},tmp_path)
    applied=profiles.change('book',{'action':'apply','candidate_ref':candidate['candidate_ref']},tmp_path)
    assert applied['application_id'] and narrative.architecture_status(tmp_path)['status']=='AVAILABLE'
    assert (tmp_path/narrative.ARCHITECTURE_PROFILE_PATH).stat().st_size<narrative.MAX_ARCHITECTURE_BYTES


def test_shared_voice_current_profile_pin_uses_exact_crlf_bytes(tmp_path):
    from laplace.manuscript import writing_style
    _,path=fixture(tmp_path)
    path.write_bytes(b'# Voice\r\nKeep this profile precise.\r\n')
    inspected=writing_style.inspect('book',{'view':'profile'},tmp_path)
    assert inspected['profile_revision']==writing_style._file_digest(path)
    result=writing_style.update_profile('book',{'profile':writing_style.DEFAULT_PROFILE,
        'content':'# New voice\r\nRead the mechanism.\r\n','basis':'author_preference',
        'provenance_kind':'structured-author-edit','reason':'My direct preference.',
        'expected_profile_revision':inspected['profile_revision']},tmp_path)
    assert result['profile_revision']==writing_style._file_digest(path)
    # HTTP routing metadata is consumed by the adapter, never by the family validator.


def test_actual_apply_changes_next_session_context_without_personal_confirmation(tmp_path):
    from laplace.writing import operating as writing_operating
    from laplace.pipeline import authoring, narrative
    fixture(tmp_path)
    before=writing_operating.build('book','work',tmp_path)
    current=native(tmp_path,{'family':'voice','scope':'workspace'})['owner_response']
    base=grammar.to_owner_payload(current['propose_action']['native_request']['payload'])
    candidate=native(tmp_path,{**base,'change':{'content':'# Voice\n## Current runtime prompt\nExplain the mechanism before the equation.\n'},'reason':'Use the concrete mechanism.'},write=True)['owner_response']
    status,_,raw=project_work_surface.handle('/work/profiles/change',{},'POST',json.dumps(candidate['apply_action']['payload']).encode(),tmp_path)
    assert status==200,json.loads(raw)
    architecture=profiles.inspect('book',{'family':'architecture','scope':'workspace'},tmp_path)
    base={key:value for key,value in architecture['propose_action']['payload'].items() if key!='project'}
    candidate=profiles.change('book',{**base,'change':{'content':architecture_content('Open with the applied concrete question.')},'reason':'Prefer this explanatory order.'},tmp_path)
    status,_,raw=project_work_surface.handle('/work/profiles/change',{},'POST',json.dumps(candidate['apply_action']['payload']).encode(),tmp_path)
    assert status==200,json.loads(raw)
    after=writing_operating.build('book','work',tmp_path)
    assert after['writing_style']['profile_revision']!=before['writing_style']['profile_revision']
    assert 'Explain the mechanism before the equation.' in after['writing_style']['content']
    actual_context,_=authoring._writing_style('book',tmp_path)
    assert actual_context['profile_revision']==after['writing_style']['profile_revision']
    assert 'Explain the mechanism before the equation.' in actual_context['content']
    assert after['architecture_prior']['status']=='AVAILABLE'
    section=narrative.architecture_brief_for_section(narrative.architecture_profile(tmp_path),0,3,'Introduce the mechanism',False)
    assert section['fields']['introduction_shape']['summary']=='Open with the applied concrete question.'
    assert not section['fields']['introduction_shape']['confirmed_his']
    assert section['his_corrections']==[],'confirmation changes personal attribution; it does not gate applied preferences'
