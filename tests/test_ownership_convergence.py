"""The reached owner/adapter movement preserves the existing public wire contract."""
import builtins
import copy
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from jsonschema import Draft202012Validator
from laplace.research import literature as L
from laplace.writing.schemas import SCHEMAS
from laplace.writing.operations import OwnerError, _execute_owner_http
from laplace.native.tools import _effect_error_details

BEFORE=json.loads((Path(__file__).parent/'fixtures/ownership-convergence/literature-import-before.json').read_text())


def test_import_schema_and_representative_wire_results_equal_pre_move_contract():
    assert L.import_contract()==SCHEMAS['literature_import']==BEFORE['schema']
    validator=Draft202012Validator(L.import_contract())
    for case in BEFORE['validation']:
        assert validator.is_valid(case['input'])==case['valid']
        if 'original' in case['input']:assert L.retained_import_validation(case['input'])==case['owner_rejection']
    detached=L.import_contract();detached['oneOf'][0]['properties']['metadata']['properties']['title']['type']='null'
    assert L.import_contract()==SCHEMAS['literature_import']==BEFORE['schema']


def test_domain_validation_and_disposition_need_no_authoring_import():
    actual=builtins.__import__
    def bounded(name,*a,**k):
        if name in {'laplace.writing.schemas','laplace.writing.operations'}:raise AssertionError('Research imported its adapter: '+name)
        return actual(name,*a,**k)
    with patch('builtins.__import__',side_effect=bounded):
        rejected=L.retained_import_validation(BEFORE['validation'][3]['input'])
        projected=L.retained_import_error_details(L.RetainedImportRejected(rejected))
        assert projected==BEFORE['projected_errors'][0]
        assert L.retained_import_disposition(rejected)==projected
        projected['disposition']['reason_code']='caller mutation'
        assert rejected['disposition']['reason_code']=='INVALID_RETAINED_IMPORT'
        assert L.retained_import_disposition({'error':'unknown','effect':'unknown'})=={}
        assert L.retained_import_disposition({'error':'partial','partial':True})=={}


def test_native_unwraps_its_owner_error_and_preserves_domain_and_nonterminal_results(tmp_path):
    rejected=BEFORE['validation'][3]['owner_rejection']
    errors=[L.RetainedImportRejected(rejected),OwnerError(rejected),OwnerError({'error':'Unknown','effect':'unknown'}),OwnerError({'error':'Partial','partial':{'bibliography':'public'}}),ValueError('REJECTED_BEFORE_EFFECTS')]
    assert [_effect_error_details(error) for error in errors]==BEFORE['projected_errors']
    assert L.retained_import_error_details(errors[1])=={},'The domain does not unwrap an adapter error'
    # The real existing HTTP adapter constructs its own OwnerError from the owner reply.
    payload=copy.deepcopy(BEFORE['validation'][4]['input'])
    with pytest.raises(OwnerError) as caught:_execute_owner_http(tmp_path,'p','work','literature_import',payload,None)
    expected=L.retained_import_disposition(BEFORE['validation'][4]['owner_rejection'])
    assert _effect_error_details(caught.value)==expected
