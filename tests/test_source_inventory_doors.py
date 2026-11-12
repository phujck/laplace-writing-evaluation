"""One actual shared Source inventory read across existing doors; no source effects."""
import copy,json
import pytest
from laplace import sdk
from laplace.native import tools
from laplace.web import project_work_surface as H
from laplace.work import owner_discovery as O,source_inventory as I
from test_source_owner_inventory import fixture


def _http(root,fields):
 from urllib.parse import parse_qs,urlsplit
 query=parse_qs(urlsplit(fields).query) if isinstance(fields,str) else {key:[json.dumps(value) if isinstance(value,dict) else str(value)] for key,value in fields.items()}
 code,_,raw=H.handle('/work/discovery',query,'GET',repo_root=root)
 return code,json.loads(raw),(raw.decode() if isinstance(raw,bytes) else raw)


def test_workspace_http_door_reads_one_declared_input_body_at_its_cut_and_refuses_every_other_caller(tmp_path):
 root,reference=fixture(tmp_path)
 code,inventory,_=_http(root,{'facet':'source-inventory','reference':reference,'projection':'inputs','limit':4})
 assert code==200 and inventory['items']
 row=next(item for item in inventory['items'] if (item.get('read') or {}).get('workspace_read'))
 assert 'native' not in row['read']['workspace_read']
 code,page,raw=_http(root,row['read']['workspace_read']['http']['url']);assert code==200
 assert page['facet']=='source-input' and page['input']['path']==row['path'] and page['input']['sha256']==row['sha256']
 assert page['cut']==inventory['basis'] and page['offset']==0 and page['content']
 assert (root/row['path']).read_text(encoding='utf-8').startswith(page['content'])
 assert str(root) not in raw and 'native' not in page['pagination']['page_read']
 # a role selection pages inside the same cut
 role=row['roles'][0]
 code,selected,_=_http(root,{'facet':'source-inventory','reference':reference,'projection':'inputs','role':role})
 assert code==200 and selected['basis']==inventory['basis'] and all(role in item['roles'] for item in selected['items'])
 # every other caller and every changed or undeclared selection refuses before any body
 request=page['pagination']['page_read']['request']
 for scope in (O.owned_workspace('sdk'),O.project_scope('public','native')):
  with pytest.raises(ValueError,match='SOURCE_INPUT_DOOR'):O.request(root,scope,request)
 with pytest.raises(ValueError,match='SOURCE_INPUT_UNDECLARED'):O.request(root,O.owned_workspace('http'),{**request,'path':'src/not_declared_here.py'})
 with pytest.raises(ValueError,match='CHANGED_INPUT'):O.request(root,O.owned_workspace('http'),{**request,'expected_sha256':'sha256:'+'0'*64})
 with pytest.raises(ValueError,match='CHANGED_INPUT'):O.request(root,O.owned_workspace('http'),{**request,'as_of':'sha256:'+'1'*64})
 with pytest.raises(ValueError,match='contract'):O.request(root,O.owned_workspace('http'),{**request,'project_lens':'public'})


def test_source_inventory_existing_sdk_native_http_closed_read_contract(tmp_path,monkeypatch):
 root,reference=fixture(tmp_path)
 payload={'facet':'source-inventory','reference':reference,'limit':2,'project_lens':'public'}
 sdk_read=sdk.source_inventory(reference,limit=2,project_lens='public',root=root)
 native=tools.execute(root,'public','work','project',{'view':'discovery','request':payload})
 query={'facet':['source-inventory'],'reference':[json.dumps(reference)],'limit':['2'],'project_lens':['public']}
 code,_,raw=H.handle('/work/discovery',query,'GET',repo_root=root);assert code==200
 human=json.loads(raw)
 assert sdk_read['items']==native['items']==human['items']
 assert sdk_read['basis']==native['basis']==human['basis']
 assert sdk_read['kernel']=={'state':'UNRESOLVED','reason_code':'NO_EXPLICIT_KERNEL_COUNTERPART','lookup_performed':False,'qualification':sdk_read['kernel']['qualification']}
 assert all('content' not in row and 'body' not in row for row in sdk_read['items'])
 calls=[];original=I.read
 def observed(*a,**kw):calls.append(1);return original(*a,**kw)
 monkeypatch.setattr(I,'read',observed)
 with pytest.raises(ValueError,match='contract'):O.request(root,O.owned_workspace('sdk'),{**payload,'budget':1000})
 assert not calls
 with pytest.raises(ValueError,match='unavailable'):tools.execute(root,'public','work','project',{'view':'discovery','request':{**payload,'project_lens':'not-admitted'}})
 (tmp_path/'doors-proof.json').write_text(json.dumps({'sdk':sdk_read,'native':native,'http':human,'closed_extra_before_owner':True},ensure_ascii=False,indent=2))
