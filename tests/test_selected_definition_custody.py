"""Selected dispatch custody, public data only; no execution/provider or live root."""
import copy
import hashlib
import json
from pathlib import Path
import time
import pytest
from laplace.pipeline import workflow_definitions as D,workflow as W,workflow_definition_records as R
from laplace.work import owner_discovery as O
from laplace.projects import project_data as C,project_handover as H,library
from laplace.core.records import capture


@pytest.fixture(autouse=True)
def passive_catalogue(monkeypatch):
    from laplace.writing import provider_catalogue
    value={'schema_version':'laplace.provider-catalogue/1','observed_at':99999999999,'providers':[{'id':'codex','available':False,'models':[]}]}
    monkeypatch.setattr(provider_catalogue,'provider_catalogue',lambda *a,**k:copy.deepcopy(value))


def make_scene(root):
    root.mkdir(parents=True,exist_ok=True)
    (root/'registry_projects.json').write_text('{"projects":[]}')
    (root/'.laplace-cache').mkdir()
    (root/'.laplace-cache/writing-provider-catalogue.json').write_text(json.dumps({'schema_version':'laplace.provider-catalogue/1','observed_at':99999999999,'providers':[{'id':'codex','available':False,'models':[]}]}))
    assert library.create({'name':'book','title':'Public custody','kind':'general'},root)[0]==201
    versions=[];body={'schema_version':D.SCHEMA,'title':'Version1','description':'Public exact selected custody Ω','settings':{},'steps':[{'id':'one','title':'One','assignment':{'role':'builder','instructions':'Retain exact instructions without execution.','settings':{}}}],'edges':[]}
    for i in range(1,4):
        body=copy.deepcopy(body);body['title']='Version'+str(i)
        versions.append(D.save(root,O.project_scope('book','sdk'),{'request_id':'public-save-'+str(i),'expected_revision':versions[-1]['version'] if versions else None,
            **({'definition_id':versions[0]['definition_id']} if versions else {}),'definition':body}))
    return {'root':root,'versions':versions,'reference':versions[1]['reference'],'caller':O.owned_workspace('sdk')}


def capture_selected(s,**kwargs):return D.capture_export(s['root'],s['caller'],s['reference'],**kwargs)


def test_core_default_decode_and_strict_owner_blank_tail_and_duplicate_keys(tmp_path):
    p=tmp_path/'generic.jsonl';p.write_bytes(b'{"value":1}\nnot-json\n[]\n')
    class Tolerant(capture.CapturedLog):
        def _reset(self):self.rows=[]
        def _admit(self,row,*args):self.rows.append(row);return True
    idx=Tolerant(p).advance();assert idx.rows==[{'value':1}] and idx.malformed_rows==2
    s=make_scene(tmp_path/'public');path=s['root']/W.LEDGER
    with path.open('ab') as out:out.write(b'\n   \n')
    assert len(capture_selected(s)['package']['versions'])==2
    with path.open('ab') as out:out.write(b'{"record":"public-unrelated"')
    with pytest.raises(D.Refused,match='CUSTODY_UNAVAILABLE'):capture_selected(s)
    with path.open('ab') as out:out.write(b'}\n')
    assert len(capture_selected(s)['package']['versions'])==2
    with path.open('ab') as out:out.write(b'{"record":"x","record":"y"}\n')
    with pytest.raises(D.Refused,match='CUSTODY_UNAVAILABLE'):capture_selected(s)


def test_exact_old_prefix_raw_body_and_prepared_projection_skip_legacy_scans(tmp_path,monkeypatch):
    s=make_scene(tmp_path);versions=s['versions'];root=s['root']
    pin={'definition_id':versions[0]['definition_id'],'definition_revision':versions[1]['version'],'body_handle':'sha256:'+'1'*64,'public_extra':['exact','Ω']}
    W._bank(root,{'record':'workflow','phase':'declared','id':'WORKFLOW-public','run_path':'evidence/WORKFLOWS/WORKFLOW-public','definition_pin':pin})
    legacy=D._pins(root,versions[0]['definition_id'])
    monkeypatch.setattr(D,'_rows',lambda *a,**k:pytest.fail('full definition raw scan'))
    monkeypatch.setattr(D,'_pins',lambda *a,**k:pytest.fail('full preparation raw scan'))
    value=D.read(root,s['caller'],{'reference':s['reference']});assert value['currentness']=='HISTORICAL' and value['pins']['prepared']==legacy
    frame=capture_selected(s);assert [r['row']['definition_revision'] for r in frame['package']['versions']]==[v['version'] for v in versions[:2]]
    actual=(root/W.LEDGER).read_bytes().splitlines(keepends=True)
    for rel,line,raw,row in frame['rows']:
        assert raw==actual[line-1] and row==json.loads(raw)
        digest=row['body_handle'].removeprefix('sha256:');body=(root/'contract/writing_bodies'/digest[:2]/digest).read_bytes()
        assert W.digest(body)==row['body_handle'] and body==W.canonical(next(v['definition'] for v in frame['package']['versions'] if v['row']==row))
    assert D.read(root,s['caller'],{'reference':s['reference'],'facet':'export'})==frame['package']
    (root/'selected-proof.json').write_text(json.dumps({'package':frame['package'],'captured':frame['captured'],'stats':D._capture_stats(root),'prepared':value['pins']['prepared']},indent=2))


@pytest.mark.parametrize('bad', ['duplicate','request-reuse','body-missing','body-corrupt','missing-prefix','row-changed','nonobject','malformed'])
def test_selected_custody_refuses_exact_adversaries(tmp_path,bad):
    s=make_scene(tmp_path);root=s['root'];path=root/W.LEDGER;chosen=capture_selected(s)
    rows=path.read_bytes().splitlines(keepends=True)
    if bad=='duplicate':
        with path.open('ab') as out:out.write(chosen['rows'][0][2])
    elif bad=='request-reuse':
        target=chosen['rows'][1];row=copy.deepcopy(target[3]);row['request_id']=chosen['rows'][0][3]['request_id'];row['receipt']['request_id']=row['request_id']
        rows[target[1]-1]=W.canonical(row)+b'\n';path.write_bytes(b''.join(rows))
    elif bad=='body-missing':
        h=chosen['rows'][0][3]['body_handle'].removeprefix('sha256:');(root/'contract/writing_bodies'/h[:2]/h).unlink()
    elif bad=='body-corrupt':
        h=chosen['rows'][0][3]['body_handle'].removeprefix('sha256:');p=root/'contract/writing_bodies'/h[:2]/h;p.write_bytes(b'x'*p.stat().st_size)
    elif bad=='missing-prefix':
        rows.pop(chosen['rows'][0][1]-1);path.write_bytes(b''.join(rows))
        with pytest.raises(D.Refused,match='INVALID_EXPORT_CHAIN'):D.read(root,s['caller'],{'reference':s['reference']})
    elif bad=='row-changed':
        frame=R.select(root,s['caller'],{'reference':s['reference']});meta=frame['prefix'][0]
        # Same byte length and an appended row defeat any claim of full-prefix
        # anchor proof. The selected raw hash itself must still reject.
        b=path.read_bytes();needle=b'public-save-1';path.write_bytes(b.replace(needle,b'public-save-X',1))
        with pytest.raises(D.Refused,match='ROW_CHANGED'):R.raw(frame,meta)
        return
    else:
        with path.open('ab') as out:out.write(b'[]\n' if bad=='nonobject' else b'not-json\n')
    with pytest.raises(D.Refused):capture_selected(s)


def test_scope_and_selector_before_lookup_and_foreign_before_raw(tmp_path,monkeypatch):
    s=make_scene(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(R,'_index',lambda *a:pytest.fail('lookup before scope/selector'))
        for caller,ref in [(None,s['reference']),(s['caller'],{'owner':'wrong','kind':'workflow-definition','identity':{'id':'x'}})]:
            with pytest.raises(D.Refused):D.capture_export(tmp_path,caller,ref)
    with monkeypatch.context() as m:
        m.setattr(R,'raw',lambda *a:pytest.fail('foreign raw row'))
        m.setattr(D,'_body',lambda *a:pytest.fail('foreign body'))
        with pytest.raises(D.Refused,match='NOT_IN_SCOPE'):D.capture_export(tmp_path,O.project_scope('foreign','native'),s['reference'])
        with pytest.raises(D.Refused,match='NOT_IN_SCOPE'):D.capture_export(tmp_path,s['caller'],s['reference'],transfer_project='foreign')
    with pytest.raises(C.ManifestError,match='duplicated'):C.collect_definitions(tmp_path,'book',references=[s['reference'],s['versions'][0]['reference']],caller=s['caller'])


def test_prefix_bound_before_body_and_replacement_reset(tmp_path,monkeypatch):
    s=make_scene(tmp_path);last=s['versions'][-1]
    for i in range(4,34):
        body=copy.deepcopy(last['definition']);body['title']='Version'+str(i)
        last=D.save(tmp_path,O.project_scope('book','sdk'),{'request_id':'public-save-'+str(i),'definition_id':last['definition_id'],'expected_revision':last['version'],'definition':body})
    assert len(capture_selected(s)['package']['versions'])==2
    with monkeypatch.context() as m:
        m.setattr(D,'_body',lambda *a:pytest.fail('body before prefix limit'))
        with pytest.raises(D.Refused,match='EXPORT_BOUND'):D.capture_export(tmp_path,s['caller'],last['reference'])
    held=R.select(tmp_path,s['caller'],{'reference':s['reference']});path=tmp_path/W.LEDGER;replacement=path.with_name('public-replacement.jsonl');replacement.write_bytes(path.read_bytes());replacement.replace(path)
    with pytest.raises(D.Refused,match='CUT_CHANGED'):R.finish(held)
    assert len(capture_selected(s)['package']['versions'])==2


def test_large_unrelated_dispatch_capture_selected_export_and_offline_recipient(tmp_path,monkeypatch):
    s=make_scene(tmp_path/'origin');root=s['root'];caller=s['caller']
    from laplace.work import object_facets as F
    # Actual explicit inspected old-version input and normal handover custody.
    object_=F.request(root,caller,{'facet':'object','reference':s['reference']})
    path=root/W.LEDGER;line=json.dumps({'record':'public-unrelated','padding':'x'*700}).encode()+b'\n'
    with path.open('ab') as out:
        for _ in range(100_005):out.write(line)
    assert path.stat().st_size>64*1024*1024
    legacy=H._bounded_rows
    monkeypatch.setattr(H,'_bounded_rows',lambda r,p:pytest.fail('whole dispatch scan') if p==W.LEDGER else legacy(r,p))
    monkeypatch.setattr(D,'_rows',lambda *a:pytest.fail('whole definition list'))
    monkeypatch.setattr(D,'_pins',lambda *a:pytest.fail('whole preparation scan'))
    before=D._capture_stats(root);started=time.monotonic()
    prepared=H.object_request(root,caller,{'action':'prepare','project':'book','request_id':'large-public-selection','entries':[{'class':'included','reference':s['reference'],'expected_basis':object_['basis'],'permit_export':True}],
        'max_files':100,'max_rows':100,'max_bytes':5_000_000},door={'origin':'sdk'})
    cold=D._capture_stats(root);warm=D.read(root,caller,{'reference':s['reference']});after_warm=D._capture_stats(root)
    assert after_warm['bytes_read']==cold['bytes_read']
    with path.open('ab') as out:out.write(b'{"record":"public-unrelated","append":true}\n')
    selected=capture_selected(s);after_append=D._capture_stats(root)
    assert after_append['scans']==cold['scans'] and after_append['bytes_read']-after_warm['bytes_read']<1024
    destination=tmp_path/'recipient'
    exported=H.object_request(root,caller,{'action':'export','project':'book','reference':prepared['reference'],'expected_basis':prepared['basis'],'destination':str(destination)},door={'origin':'sdk'})
    final=D._capture_stats(root);elapsed=time.monotonic()-started
    root.rename(tmp_path/'origin-offline')
    reopened=D.read(destination,O.project_scope('book','sdk'),{'reference':s['reference'],'facet':'export'})
    assert reopened==selected['package'] and len(reopened['versions'])==2
    assert D.read(destination,O.project_scope('book','sdk'),{'reference':s['reference']})['currentness']=='CURRENT'
    (tmp_path/'large-proof.json').write_text(json.dumps({'journal_bytes':(tmp_path/'origin-offline'/W.LEDGER).stat().st_size,'unrelated_rows':100005,'stats_before':before,'stats_cold':cold,'stats_warm':after_warm,'stats_append':after_append,'stats_final':final,'elapsed_seconds':elapsed,'origin_head':s['versions'][-1]['version'],'selected':s['reference'],'exported':exported,'recipient_package':reopened},indent=2))


def test_empty_definitions_no_lookup_and_byte_budget_before_body(tmp_path,monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(R,'_index',lambda *a:pytest.fail('empty selection lookup'))
        assert C.collect_definitions(tmp_path,'book',references=[])==([],[],[])
    s=make_scene(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(D,'_body',lambda *a:pytest.fail('body before package byte admission'))
        with pytest.raises(D.Refused,match='EXPORT_BOUND'):capture_selected(s,max_bytes=10)
    proof=capture_selected(s)
    assert proof['package']['versions'][0]['row']['previous_revision'] is None


def test_project_metadata_lookup_uses_admitted_partition(tmp_path,monkeypatch):
    s=make_scene(tmp_path);capture_selected(s)
    idx=R._INDEXES[str(tmp_path.resolve())]
    class ForbiddenGlobal(dict):
        def get(self,*a):pytest.fail('project read looked through global definition IDs')
    monkeypatch.setattr(idx,'definitions',ForbiddenGlobal(idx.definitions))
    local=D.read(tmp_path,O.project_scope('book','native'),{'reference':s['reference']})
    assert local['definition_id']==s['versions'][0]['definition_id']
    with pytest.raises(D.Refused,match='NOT_IN_SCOPE'):D.read(tmp_path,O.project_scope('foreign','native'),{'reference':s['reference']})
