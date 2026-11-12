"""The UI and native tool read the same bounded owner history without writes."""
import hashlib
import json
import pytest
from laplace.web import authoring as authoring_surface
from laplace.native import contracts as writing_contracts
from laplace.writing import operations
from laplace.core import checkout
from test_author_history import _fixture


def test_activity_http_and_native_tool_share_exact_owner_projection(tmp_path,monkeypatch):
    _fixture(tmp_path)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    before={str(path.relative_to(tmp_path)):hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.rglob('*') if path.is_file()}
    # The HTTP query carries text ('20'); the native payload is typed by the owner schema (integer 20).
    payload={'view':'activity','category':'manuscript','limit':20}
    status,_,raw=authoring_surface.handle('/authoring/history',{'project':['book'],**{k:[str(v)] for k,v in payload.items()}},'GET',b'')
    assert status==200
    listed=json.loads(raw)
    native=operations._execute(tmp_path,'book','work','author_history',payload)
    assert listed==native
    with pytest.raises(ValueError,match="consumed selectors: '20' is not of type 'integer'"):   # a native string limit is malformed, never coerced
        operations._execute(tmp_path,'book','work','author_history',{**payload,'limit':'20'})
    assert listed['items'] and len(listed['items'])<=20
    ident=next(row['id'] for row in listed['items'] if row['owner']=='editor-save')
    status,_,raw=authoring_surface.handle('/authoring/history',{'project':['book'],'view':['activity'],'id':[ident]},'GET',b'')
    assert status==200
    detail=json.loads(raw)
    assert detail==operations._execute(tmp_path,'book','work','author_history',{'view':'activity','id':ident})
    assert detail['hashes']
    after={str(path.relative_to(tmp_path)):hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.rglob('*') if path.is_file()}
    assert after==before


def test_default_correction_read_remains_compatible_and_activity_ids_are_project_fenced(tmp_path,monkeypatch):
    _fixture(tmp_path);monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    result=operations._execute(tmp_path,'book','work','author_history',{'id':'AC-one'})
    assert result['item']['id']=='AC-one'
    status,_,raw=authoring_surface.handle('/authoring/history',{'project':['unknown'],'view':['activity'],'id':['activity:authoring:AC-one']},'GET',b'')
    assert status!=200
    assert 'error' in json.loads(raw)
    with pytest.raises(ValueError,match='view must'):
        operations._execute(tmp_path,'book','work','author_history',{'view':'misspelled'})
    # The hand-written example is gone; the declaration carries the same facts as
    # typed rules, and `does` is the summary's first clause.
    from laplace.native import declarations as writing_declarations
    declaration=writing_declarations.DECLARATIONS['author_history']
    assert declaration.effects==()
    assert declaration.verb=='read' and declaration.concept.endswith('@project')
    assert 'scientific validity' in ' '.join(rule.says for rule in declaration.rules)
    # author_history requires nothing, so the example comes from its one-of rule: the
    # first branch of the choice the door actually enforces, not a literal.
    example=writing_declarations.generated_example('author_history')
    assert set(example)<={'view','id'} and example['view'] in ('corrections','activity')
