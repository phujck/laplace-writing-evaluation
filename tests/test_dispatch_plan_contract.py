"""Current help must produce a real finite plan, not an opaque plan:{} hint."""
import copy
import shutil

import pytest
from jsonschema import Draft202012Validator

from laplace.work import project_work
from laplace.native import declarations as writing_declarations, tools as writing_tools
from laplace.writing import provider as writing_provider
from laplace.writing import records as writing_records
from laplace.writing import dispatch_execution
from laplace.writing.records import _fold as records_fold
from laplace.writing import turn_jobs
from laplace.writing import turn_admission
from laplace.writing import provider as writing_provider
from test_manuscript_structure import _section_fixture
from test_writing_dispatch import CATALOGUE


@pytest.fixture
def parent(tmp_path,monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE',str(tmp_path/'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES',str(tmp_path/'workspaces'))
    _section_fixture(tmp_path)
    monkeypatch.setattr(writing_provider, 'capabilities',lambda *a,**k:CATALOGUE)
    monkeypatch.setattr(writing_provider,'capabilities',lambda *a,**k:CATALOGUE)
    monkeypatch.setattr(turn_admission, 'new_session',lambda *a,**k:pytest.fail('session effect'))
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-parent','project':'book',
        'provider':'claude','model':'haiku','effort':'low','role':'author'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-parent','session_id':'WS-parent',
        'project':'book','mode':'work','text':'Prepare a bounded scoped execution.'})
    yield tmp_path
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    shutil.rmtree(tmp_path,ignore_errors=True)


def example():
    return writing_declarations.help_payload('dispatch_plan',permitted=True,with_tokens=False)['example']['plan']


def test_owner_help_example_passes_actual_carrier_and_settings_admission(parent):
    plan = example()
    assert Draft202012Validator(project_work.dispatch_plan_contract()).is_valid(plan)
    assert len(plan['packets'])==2 and [row['role'] for row in plan['packets']]==['worker','judge']
    result = dispatch_execution.launch_dispatch(parent,'book','WT-parent',{'plan':plan},validate_only=True)
    assert result['carrier_spec_stages']==['develop','review','parent-consumes']
    help_value = writing_declarations.help_payload('dispatch_plan',permitted=True,with_tokens=False)
    assert 'input' in help_value['sections']['chars'], help_value['sections']   # compact help: the schema is a sectioned read, advertised by size
    schema_section = writing_declarations.help_payload('dispatch_plan',permitted=True,with_tokens=False,section='input')
    packet = schema_section['value']['properties']['plan']['properties']['packets']['items']
    assert packet['required']==['packet','role','brief','return_path']
    assert not project_work._tasks('book',parent)


@pytest.mark.parametrize('mutation',['label_alias','synthesis_child','invented_model'])
def test_actual_failed_plan_misuses_refuse_before_any_effect(parent,mutation):
    plan = copy.deepcopy(example())
    if mutation=='label_alias':
        for row in plan['packets']:
            row['label']=row.pop('packet')
        expected='packet'
    elif mutation=='synthesis_child':
        plan['fan_out_max']=3
        plan['packets'].append({'packet':'synthesise','role':'synthesis','brief':'Synthesize results.',
                                'return_path':'development/synthesis.json'})
        expected='worker.*judge'
    else:
        plan['packets'][0]['model']='claude-3-5-haiku-20241022'
        expected='advertised|Unknown|available'
    with pytest.raises(ValueError,match=expected):
        dispatch_execution.launch_dispatch(parent,'book','WT-parent',{'plan':plan},validate_only=True)
    assert not project_work._tasks('book',parent)


def test_native_settings_exposes_exact_advertised_child_choices(parent):
    result = writing_tools.execute(parent,'book','work','session_settings',{},turn_id='WT-parent')
    assert result['providers']==CATALOGUE['providers']
    assert result['session']['model']=='haiku'
    plan = example()
    for row in plan['packets']:
        row.update(provider='claude',model='haiku',effort='low')
    assert dispatch_execution.launch_dispatch(parent,'book','WT-parent',{'plan':plan},validate_only=True)['validated']
