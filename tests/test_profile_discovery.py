"""Absent architecture discovery is the same contract its real writer consumes."""
import json
import pytest
from jsonschema import Draft202012Validator
from laplace.native import declarations as writing_declarations
from laplace.pipeline import narrative
from laplace.manuscript import profiles
from test_profile_candidates import fixture


def test_absent_architecture_read_help_example_and_real_writer_share_document_contract(tmp_path):
    fixture(tmp_path)
    current=profiles.inspect('book',{'family':'architecture','scope':'workspace','view':'content'},tmp_path)
    contract=current['content_contract']
    assert current['status']=='ABSENT' and current['content']==''
    assert contract==narrative.architecture_content_contract()
    example=writing_declarations.generated_example('profile_change')
    document=narrative.architecture_document(example['change']['content'])
    Draft202012Validator(contract['document_schema']).validate(document)
    assert document==contract['example']
    candidate=profiles.change('book',{**example,'guards':current['propose_action']['payload']['guards']},tmp_path)
    assert candidate['candidate_ref'] and candidate['currentness']=='CURRENT'


@pytest.mark.parametrize('change',[{}, {'guidance':'Opaque architecture preference.'}, {'narrative_arc':'Opaque summary.'}])
def test_architecture_declaration_refuses_wrong_family_shapes_before_writer(change):
    payload={'action':'propose','family':'architecture','scope':'workspace','change':change,
        'reason':'Synthetic shape check.','guards':{'profile_input_revision':'sha256:'+'0'*64}}
    assert list(Draft202012Validator(profiles.change_contract()).iter_errors(payload))


def test_architecture_content_error_routes_back_to_the_public_contract():
    with pytest.raises(ValueError,match='content_contract') as error:
        narrative.architecture_document('narrative_arc: Missing profile envelope.')
    assert json.dumps(narrative.architecture_content_contract()['example']) in str(error.value)


def test_profile_terminal_text_part_declares_end_without_claiming_whole_body():
    text='Résumé "quoted"\n'*20
    first=profiles._part(text,0,64)
    last=profiles._part(text,first['coverage']['end'],profiles.MAX_PART_BYTES)
    assert first['coverage']['has_more'] and not first['coverage']['at_end']
    assert last['coverage']['at_end'] and not last['coverage']['has_more'] and not last['coverage']['complete']
    assert first['content']+last['content']==text
    assert len(json.dumps(first['content'],ensure_ascii=False).encode())<=64
    assert 'coverage.complete means the whole text' in last['read_instruction']


def test_delivery_palette_comes_from_actual_section_selector_without_widening_custom_fields():
    delivery=narrative.architecture_delivery_contract()
    profile={row['id']:{'summary':'A scoped preference.','ref':row['id'],'confirmed_his':False}
             for row in delivery['section_fields']}
    profile['result_precedence']={'summary':'A whole-paper preference.','ref':'custom','confirmed_his':False}
    for label,position,job,derivations in [('Opening',0,'Introduce',False),('Body',1,'',False),('Closing',2,'Conclude',False),('Derivations',1,'Derive',True)]:
        actual=narrative.architecture_brief_for_section(profile,position,3,job,derivations)['fields']
        assert set(actual)=={row['id'] for row in delivery['section_fields'] if label in row['contexts']}
    assert narrative.architecture_document(json.dumps({'profile':{'result_precedence':{'summary':'Still valid.'}}}))
