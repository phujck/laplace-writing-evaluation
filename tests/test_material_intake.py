"""Bounded public byte intake through actual artifact/record/Material owners."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
from email.message import Message
from concurrent.futures import ThreadPoolExecutor
import pytest
from laplace.projects import material_intake as intake, artifacts, library
from laplace.writing import records


def retain(name,value):
    if os.environ.get('INTAKE_EVIDENCE'):
        p=Path(os.environ['INTAKE_EVIDENCE']);p.mkdir(exist_ok=True,parents=True)
        (p/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


def tree(root):
    (root/'p').mkdir(parents=True)
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'project','project_dir':'p','manifest':{'writing':{'kind':'other'}}}]}))
    return root


def metadata(root,raw,request='public-intake-1',pdf=False,attach=True):
    return {'request_id':request,'display_name':'Public original.pdf' if pdf else 'Public original.txt',
        'media_type':'application/pdf' if pdf else 'text/plain; charset=utf-8','declared_size':len(raw),
        'expected_sha256':hashlib.sha256(raw).hexdigest(),'attach_material':attach,'expected_revision':library.metadata('p',root)['revision']}


def pdf_bytes():
    parts=[b'%PDF-1.4\n'];offsets=[0]
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    text=b'BT /F1 12 Tf 30 250 Td (Public PDF exact canary endmarker.) Tj ET'
    objects.append(b'<< /Length '+str(len(text)).encode()+b' >>\nstream\n'+text+b'\nendstream')
    for i,obj in enumerate(objects,1):
        offsets.append(sum(map(len,parts)));parts.append(str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n')
    start=sum(map(len,parts));parts.append(b'xref\n0 6\n0000000000 65535 f \n')
    parts.extend(('%010d 00000 n \n'%n).encode() for n in offsets[1:])
    parts.append(b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n')
    return b''.join(parts)


def test_text_original_request_replay_content_reuse_and_removed_membership(tmp_path):
    root=tree(tmp_path);raw='Public α 🧪 transcript.\n'.encode();wire=metadata(root,raw)
    first=intake.upload(root,'p',wire,raw);assert first['state']=='RECORDED' and first['membership']['state']=='LINKED'
    before=(root/'contract/talk.jsonl').read_bytes();again=intake.upload(root,'p',wire,raw)
    assert again['replayed'] and again['original']==first['original'] and (root/'contract/talk.jsonl').read_bytes()==before
    target=first['original']['target'];read=artifacts.read(root,'p',first['original']['text_read']['payload'])
    assert read['content']==raw.decode() and read['update_handle'] is None
    with pytest.raises(ValueError,match='immutable'):artifacts.store(root,'p',{'path':target['path'],'before':raw.decode(),'content':'overwrite','reason':'test'})
    with pytest.raises(intake.IntakeRefusal,match='another exact'):intake.upload(root,'p',{**wire,'display_name':'Different'},raw)
    reused=intake.upload(root,'p',metadata(root,raw,'public-intake-2'),raw)
    assert reused['original']['artifact_id']==first['original']['artifact_id'] and reused['membership']['attribution']=='OBSERVED_STANDING'
    changed=b'Different bytes same filename';other=intake.upload(root,'p',metadata(root,changed,'public-intake-3'),changed)
    assert other['original']['artifact_id']!=first['original']['artifact_id']
    library.change_material_reference('p',{'action':'remove','id':first['membership']['reference']['id'],'expected_revision':library.metadata('p',root)['revision']},root)
    repeated=intake.upload(root,'p',wire,raw)
    assert repeated['state']=='RECORDED' and repeated['membership']['state']=='REMOVED'
    assert not repeated['membership']['current_present'] and 'link' not in repeated['actions']
    retain('text-replay',{'first':first,'reused':reused,'different':other,'removed_replay':repeated,'read':read})


def test_partial_registry_link_explicit_fresh_recovery_without_reupload(tmp_path,monkeypatch):
    root=tree(tmp_path);raw=b'Public partial';wire=metadata(root,raw)
    actual=library.change_material_reference
    def conflict(*a,**k):raise ValueError('Project metadata revision conflict; public fault injection.')
    monkeypatch.setattr(library,'change_material_reference',conflict)
    first=intake.upload(root,'p',wire,raw)
    assert first['state']=='PARTIAL' and first['original']['state']=='RETAINED' and first['membership']['state']=='PENDING'
    monkeypatch.setattr(library,'change_material_reference',actual)
    replay=intake.upload(root,'p',wire,raw);assert replay['state']=='PARTIAL' and not replay['membership']['current_present']
    action=replay['actions']['link'];assert action['inspect_destination']['payload']=={'view':'intake'}
    linked=intake.link(root,'p',{'request_id':wire['request_id'],'expected_revision':library.metadata('p',root)['revision']})
    assert linked['state']=='RECORDED' and linked['original']['artifact_id']==first['original']['artifact_id']
    retain('partial-link',{'retained':first,'pure':replay,'linked':linked})


def test_interrupted_art_receipt_and_concurrent_same_request(tmp_path,monkeypatch):
    root=tree(tmp_path);raw=b'Public interrupted';wire=metadata(root,raw,attach=False);bank=records.bank
    def interrupted(root,row,**kwargs):
        if row.get('record')=='writing-artifact':raise OSError('Public injected before ART bank')
        return bank(root,row,**kwargs)
    monkeypatch.setattr(records,'bank',interrupted)
    with pytest.raises(OSError):intake.upload(root,'p',wire,raw)
    partial=intake.status(root,'p',wire['request_id']);assert partial['state']=='PARTIAL' and partial['original']['state']=='RETAINED'
    assert partial['original']['artifact_publication']=='NOT_OBSERVED'
    monkeypatch.setattr(records,'bank',bank)
    with ThreadPoolExecutor(2) as pool:values=list(pool.map(lambda _:intake.upload(root,'p',wire,raw),range(2)))
    assert all(x['state']=='RECORDED' for x in values)
    idx=records.index(root);assert len([x for x in idx.by_project.get('p',[]) if x['record']=='writing-artifact'])==1
    retain('interrupted-concurrent',{'partial':partial,'completed':values})


def test_media_framing_size_hash_and_exact_scanner_admission(tmp_path,monkeypatch):
    root=tree(tmp_path);raw=b'Public UTF8';wire=metadata(root,raw)
    for bad in [b'bad',b'\xff'*len(raw)]:
        with pytest.raises(intake.IntakeRefusal):intake.upload(root,'p',wire,bad)
    for headers in [{},{'Content-Length':'-1'},{'Content-Length':'16000001'},{'Content-Length':'2','Transfer-Encoding':'chunked'}]:
        with pytest.raises(intake.IntakeRefusal):intake.read_upload_body(headers,io.BytesIO(b'x'))
    with pytest.raises(intake.IntakeRefusal):intake.read_upload_body({'Content-Length':'2'},io.BytesIO(b'x'))
    assert not (root/'contract/talk.jsonl').exists()
    from laplace.web import scanner
    monkeypatch.setattr(scanner,'_repo_root',lambda:root)
    from urllib.parse import urlencode
    Handler=scanner.make_handler()
    def call(path,body,header=True,content_type=None,length=None):
        h=Handler.__new__(Handler);h.path=path;h.client_address=('127.0.0.1',1234);h.request_version='HTTP/1.1';h.command='POST';h.requestline='POST '+path+' HTTP/1.1';h.wfile=io.BytesIO();h.rfile=io.BytesIO(body);h._headers_buffer=[];h._walk_cookie='';h.headers=Message()
        h.headers['Host']='localhost';h.headers['Content-Length']=str(len(body) if length is None else length)
        if header:h.headers['X-Laplace-Writing']='1'
        if content_type:h.headers['Content-Type']=content_type
        h.do_POST();head,data=h.wfile.getvalue().split(b'\r\n\r\n',1);return int(head.split()[1]),json.loads(data)
    url='/projects/material-intake/upload?'+urlencode({'project':'p','request':json.dumps(wire)})
    assert call(url,raw,header=False)[0]==403
    assert call(url,raw,content_type='application/pdf')[0]==422
    code,value=call(url,raw,content_type=wire['media_type']);assert code==200 and value['state']=='RECORDED'
    assert call('/projects/material-references',b'',length=2*1024*1024+1)[0]==413
    retain('scanner-raw',{'status':code,'result':value,'normal_json_cap_unchanged':True})


def test_real_pdf_text_page_material_pin_and_unavailable_extraction(tmp_path,monkeypatch):
    root=tree(tmp_path);raw=pdf_bytes();wire=metadata(root,raw,pdf=True)
    saved=intake.upload(root,'p',wire,raw);assert saved['state']=='RECORDED'
    from laplace.projects import writing_sources
    monkeypatch.setattr(writing_sources,'_tool',lambda name:'/usr/bin/'+name)
    text=artifacts.read(root,'p',saved['original']['text_read']['payload'])
    assert text['extraction_state']=='TEXT_EXTRACTED' and 'Public PDF exact canary endmarker.' in text['content']
    assert text['source']['sha256']==wire['expected_sha256'] and text['pdf_page_start']==1
    page=artifacts.read(root,'p',saved['original']['page_image_read']['payload'])
    assert page['extraction_state']=='RENDERED_PAGE' and page['_image_content'][0]['mime_type']=='image/png'
    material=library.material_references('p',root,view='source',id=saved['membership']['reference']['id'])
    assert material['currentness']=='CURRENT' and material['owner_result']['content']==text['content']
    monkeypatch.setattr(writing_sources,'_run',lambda argv:(_ for _ in ()).throw(ValueError('Public extraction failure seam')))
    failed=artifacts.read(root,'p',saved['original']['text_read']['payload']);assert failed['extraction_state']=='UNAVAILABLE'
    from urllib.parse import urlsplit,parse_qs
    handle=saved['original']['original_read'];u=urlsplit(handle['http']['url'])
    code,media,actual=intake.http(u.path,parse_qs(u.query),'GET',b'',root)
    assert code==200 and media=='application/pdf' and actual==raw
    (root/'p'/saved['original']['target']['path']).write_bytes(raw+b'changed')
    with pytest.raises(ValueError,match='conflict'):artifacts.read(root,'p',text['page_read']['payload'])
    retain('actual-pdf',{'saved':saved,'text':text,'page':{k:v for k,v in page.items() if k!='_image_content'},'material':material,'unavailable':failed})


def test_same_project_context_pointer_and_native_pure_read(tmp_path):
    root=tree(tmp_path);raw=b'Public selected reading';saved=intake.upload(root,'p',metadata(root,raw),raw)
    from laplace.writing import turn_context
    pointer=saved['original']['material_read'];chosen=turn_context._workspace_context(root,'p',{'surface':'sources','label':'Public reading','material_read':pointer})
    assert chosen['material_read']==pointer and 'Public selected reading' not in json.dumps(chosen)
    for bad in [{**pointer,'project':'other'},{**pointer,'sha256':'f'*64},{**pointer,'read_payload':{**pointer['read_payload'],'path':'private'}}]:
        with pytest.raises(ValueError):turn_context._workspace_context(root,'p',{'surface':'sources','material_read':bad})
    from laplace.native import tools
    observed=tools.execute(root,'p','review','material_references',{'view':'intake','request_id':saved['request_id']})
    assert observed['state']=='RECORDED'
    retain('context-native',{'selected':chosen,'status':observed})


def test_complete_project_handover_retains_original_and_request(tmp_path):
    root=tree(tmp_path/'source');raw=pdf_bytes();saved=intake.upload(root,'p',metadata(root,raw,pdf=True),raw)
    from laplace.projects import project_handover
    (root/'profiles').mkdir();(root/'profiles/writing_sources.json').write_text('{"repositories":{}}')
    plan=project_handover.plan(root,'p',max_files=100,max_rows=100,max_bytes=2000000)
    out=tmp_path/'handover';receipt=project_handover.export(root,out,plan)
    fresh=out
    # The existing exporter publishes a data-only workspace at its declared destination.
    retain('handover',{'plan':plan,'receipt':receipt})
    assert any(x['path']==str(Path('p')/saved['original']['target']['path']) for x in plan['files'])
    selected=[x for x in plan['rows'] if x.get('record')=='writing-material-intake']
    assert selected
    restored=intake.status(fresh,'p',saved['request_id'])
    assert restored['state']=='RECORDED' and restored['original']['artifact_id']==saved['original']['artifact_id']
    assert (fresh/'p'/saved['original']['target']['path']).read_bytes()==raw
    retain('handover-restored',restored)


def test_retained_bytes_recover_receipt_without_file_and_alias_cannot_edit(tmp_path,monkeypatch):
    root=tree(tmp_path);raw=b'Public retained';wire=metadata(root,raw,attach=False);bank=records.bank
    def fail(root,row,**kwargs):
        if row['record']=='writing-artifact':raise OSError('Public before receipt fault')
        return bank(root,row,**kwargs)
    monkeypatch.setattr(records,'bank',fail)
    with pytest.raises(OSError):intake.upload(root,'p',wire,raw)
    partial=intake.status(root,'p',wire['request_id']);assert partial['original']['state']=='RETAINED'
    assert 'link' in partial['actions'] and 'retry_upload' not in partial['actions']
    monkeypatch.setattr(records,'bank',bank)
    done=intake.link(root,'p',{'request_id':wire['request_id'],'expected_revision':library.metadata('p',root)['revision']})
    assert done['state']=='RECORDED' and done['membership']['state']=='NOT_REQUESTED'
    path='./'+done['original']['target']['path']
    with pytest.raises(ValueError,match='immutable'):artifacts.store(root,'p',{'path':path,'before':raw.decode(),'content':'bad','reason':'public alias test'})
    assert artifacts.read(root,'p',{'path':path})['update_handle'] is None
    retain('retained-receipt-recovery',{'partial':partial,'completed':done})


def test_large_pdf_raw_budget_and_compact_records_without_text_expansion(tmp_path):
    root=tree(tmp_path);raw=b'%PDF-1.4\n'+b'0'*(2*1024*1024)
    wire=metadata(root,raw,pdf=True,attach=False)
    from laplace.web import scanner
    from urllib.parse import urlencode
    import unittest.mock
    Handler=scanner.make_handler();h=Handler.__new__(Handler)
    h.path='/projects/material-intake/upload?'+urlencode({'project':'p','request':json.dumps(wire)})
    h.client_address=('127.0.0.1',1234);h.request_version='HTTP/1.1';h.command='POST';h.requestline='POST '+h.path+' HTTP/1.1';h.wfile=io.BytesIO();h.rfile=io.BytesIO(raw);h._headers_buffer=[];h._walk_cookie='';h.headers=Message()
    for key,value in {'Host':'localhost','Content-Length':str(len(raw)),'Content-Type':'application/pdf','X-Laplace-Writing':'1'}.items():h.headers[key]=value
    with unittest.mock.patch.object(scanner,'_repo_root',return_value=root):h.do_POST()
    head,body=h.wfile.getvalue().split(b'\r\n\r\n',1);value=json.loads(body)
    assert b' 200 ' in head.split(b'\r\n')[0] and value['state']=='RECORDED'
    assert len(body)<20_000 and (root/'contract/talk.jsonl').stat().st_size<20_000
    with pytest.raises(intake.IntakeRefusal):intake.upload(root,'p',{**wire,'request_id':'public-text-too-large','media_type':'text/plain; charset=utf-8'},raw)
    retain('raw-large-budget',{'bytes':len(raw),'response_bytes':len(body),'journal_bytes':(root/'contract/talk.jsonl').stat().st_size,'status':value})


def test_unknown_request_coverage_and_issued_http_native_contracts(tmp_path):
    root=tree(tmp_path);raw=b'Public closed contract';wire=metadata(root,raw)
    description=intake.describe(root,'p')
    from laplace.native import declarations
    from laplace.web import writing_declared_http
    declaration=declarations.HTTP_DECLARATIONS['projects/material-intake-upload']
    assert declaration.payload==intake.metadata_contract()
    from jsonschema import Draft202012Validator
    from laplace.writing.schemas import SCHEMAS
    assert Draft202012Validator(SCHEMAS['read_artifact']).is_valid({'id':'ART-public','page':1,'page_count':1,'view':'page'})
    saved=intake.upload(root,'p',wire,raw);catalogue=artifacts.catalogue(root,'p')['materials'][0]
    assert catalogue['display_name']==wire['display_name'] and catalogue['read_only'] and catalogue['update_handle'] is None
    assert catalogue['original_read']['http']['url']==saved['original']['original_read']['http']['url']
    from urllib.parse import urlsplit,parse_qs
    handle=saved['original']['original_read'];url=urlsplit(handle['http']['url'])
    code,media,body=intake.http(url.path,parse_qs(url.query),'GET',b'',root)
    assert code==200 and body==raw and media=='text/plain; charset=utf-8'
    page=library.material_references('p',root)['references'][0]
    assert page['display_name']==wire['display_name'] and page['original_read_only']
    from laplace import sdk
    assert sdk.material_intake_request('p',{'view':'status','request_id':wire['request_id']},root=root)['state']=='RECORDED'
    before=(root/'contract/talk.jsonl').read_bytes()
    other=metadata(root,b'other public','public-unknown-2')
    with (root/'contract/talk.jsonl').open('ab') as stream:stream.write(b'{incomplete')
    observed=intake.status(root,'p',other['request_id']);assert observed['state']=='UNKNOWN'
    with pytest.raises(intake.IntakeRefusal,match='incomplete coverage'):intake.upload(root,'p',other,b'other public')
    assert (root/'contract/talk.jsonl').read_bytes()==before+b'{incomplete'
    retain('issued-contracts',{'describe':description,'catalogue':catalogue,'status':saved,'unknown':observed})


def test_existing_text_artifact_and_repository_read_semantics_unchanged(tmp_path):
    root=tree(tmp_path);text='α public original text'
    saved=artifacts.store(root,'p',{'path':'legacy.txt','before':None,'content':text,'reason':'Public old route'})
    first=artifacts.read(root,'p',{'id':saved['id'],'offset':0,'limit':1})
    assert first['content']=='α' and first['next_offset']==2 and first['update_handle'] is not None
    (root/'profiles').mkdir();(root/'profiles/writing_sources.json').write_text(json.dumps({'repositories':{'public':'p'}}))
    from laplace.projects import writing_sources
    old=writing_sources.execute(root,{'action':'read','repository':'public','path':'legacy.txt','offset':0,'limit':1})
    assert old['content']=='α' and old['next_offset']==1 and old['source']['sha256']==hashlib.sha256(text.encode()).hexdigest()
    nxt=writing_sources.execute(root,old['read_handle']['payload']);assert nxt['content']==' '
    (root/'p/legacy.txt').write_text('changed')
    with pytest.raises(ValueError,match='conflict'):writing_sources.execute(root,old['page_read']['payload'])
    retain('unchanged-text-reads',{'artifact':first,'repository':old,'next':nxt})


def test_intake_http_text_paging_is_pinned_terminated_and_distinct_from_legacy(tmp_path):
    root=tree(tmp_path);raw=('Public α 🧪 exact reading.\n'*1900).encode();saved=intake.upload(root,'p',metadata(root,raw),raw)
    from urllib.parse import urlsplit,parse_qs
    def get(handle):
        u=urlsplit(handle['http']['url']);code,_,body=intake.http(u.path,parse_qs(u.query),'GET',b'',root)
        assert code==200,body
        return json.loads(body)
    first=get(saved['original']['text_read']);parts=[first['content']];pages=[first];page=first
    while page['read_handle'] is not None:
        assert page['read_handle']['payload']['expected_sha256']==saved['intent']['expected_sha256']
        page=get(page['read_handle']);pages.append(page);parts.append(page['content'])
    assert ''.join(parts).encode()==raw and page['complete'] and page['read_handle'] is None
    assert get(first['page_read'])['content']==first['content']
    assert 'expected_sha256' not in first['restart_read']['payload'] and get(first['restart_read'])['offset']==0
    legacy=artifacts.read(root,'p',page['page_read']['payload']);assert legacy['complete'] and legacy['read_handle'] is not None
    assert 'http' not in legacy['read_handle']
    (root/'p'/saved['original']['target']['path']).write_bytes(raw+b'changed')
    with pytest.raises(ValueError,match='conflict'):intake.read(root,'p',first['page_read']['payload'])
    retain('intake-http-text-pages',{'saved':saved,'pages':pages,'legacy_final':legacy})


def test_stale_initial_metadata_retains_original_partial_link_and_no_attach(tmp_path):
    root=tree(tmp_path);raw=b'Public stale destination basis';wire=metadata(root,raw,request='public-stale-link-1')
    no_attach=metadata(root,raw,request='public-stale-noattach-1',attach=False)
    changed=library.change_metadata('p',{'title':'Updated public display','expected_revision':wire['expected_revision']},root)
    assert library.metadata('p',root)['revision']!=wire['expected_revision']
    first=intake.upload(root,'p',wire,raw)
    assert first['state']=='PARTIAL' and first['original']['state']=='RETAINED' and first['original']['artifact_publication']=='RECORDED'
    assert first['intent']==wire and first['membership']['state']=='PENDING' and not first['membership']['current_present']
    assert 'link' in first['actions'] and 'retry_upload' not in first['actions']
    repeated=intake.upload(root,'p',wire,raw);assert repeated['state']=='PARTIAL' and repeated['replayed']
    recovered=intake.link(root,'p',{'request_id':wire['request_id'],'expected_revision':library.metadata('p',root)['revision']})
    assert recovered['state']=='RECORDED' and recovered['original']['artifact_id']==first['original']['artifact_id']
    independent=intake.upload(root,'p',no_attach,raw)
    assert independent['state']=='RECORDED' and independent['membership']['state']=='NOT_REQUESTED'
    assert independent['original']['artifact_id']==first['original']['artifact_id']
    # Actual same-project admitted home/coordinates are still required; no mutation migrates an old request.
    registry=root/'registry_projects.json';data=json.loads(registry.read_text());data['projects'][0]['project_dir']='other-home';(root/'other-home').mkdir();registry.write_text(json.dumps(data))
    changed_home=intake.status(root,'p',wire['request_id']);assert changed_home['state']=='UNKNOWN'
    assert 'no home migration' in changed_home['diagnostic']
    retain('stale-link-guard',{'wire':wire,'retained':first,'replayed':repeated,'linked':recovered,'no_attachment':independent,'changed_home':changed_home})
