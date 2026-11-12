"""Retained public originals -> existing Literature, no upload or network/provider."""
import json,hashlib,copy,os,shutil,base64
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from laplace.research import literature as lit,references_surface as refs,literature_support as support
from laplace.projects import artifacts
from laplace.writing import records

# Byte-exact public originals/ART receipts reused from accepted intake verification-006/003.
PUBLIC_ORIGINALS={'text': {'record': {'record': 'writing-artifact', 'id': 'ART-11ff3bdde32d068ae22acc596dd25c4f', 'project': 'p', 'path': 'p/.artifacts/originals/text/6af757e33f710a5c78659f549136ca94a3b4e65e3f1593e7c37fe89e656c13ad.txt', 'artifact_path': '.artifacts/originals/text/6af757e33f710a5c78659f549136ca94a3b4e65e3f1593e7c37fe89e656c13ad.txt', 'scope': 'project', 'sha256': '6af757e33f710a5c78659f549136ca94a3b4e65e3f1593e7c37fe89e656c13ad', 'before': None, 'before_sha256': None, 'original_metadata': {'schema_version': 'laplace.artifact-original/1', 'media_type': 'text/plain; charset=utf-8', 'bytes': 22, 'display_name': 'Public original.txt', 'immutable': True}, 'reason': 'Retained immutable local document original', 'ts': '2026-10-26T03:39:43.831Z'}, 'base64': 'UHVibGljIGNsb3NlZCBjb250cmFjdA=='}, 'pdf': {'record': {'record': 'writing-artifact', 'id': 'ART-6fed88b7c577e3c176a22051d51405e6', 'project': 'p', 'path': 'p/.artifacts/originals/pdf/3b2f99311ffae511324f9355803ca270b13b821a7dd90848cb3d90660b170ba4.pdf', 'artifact_path': '.artifacts/originals/pdf/3b2f99311ffae511324f9355803ca270b13b821a7dd90848cb3d90660b170ba4.pdf', 'scope': 'project', 'sha256': '3b2f99311ffae511324f9355803ca270b13b821a7dd90848cb3d90660b170ba4', 'before': None, 'before_sha256': None, 'original_metadata': {'schema_version': 'laplace.artifact-original/1', 'media_type': 'application/pdf', 'bytes': 609, 'display_name': 'Public original.pdf', 'immutable': True}, 'reason': 'Retained immutable local document original', 'ts': '2026-10-26T03:30:05.631Z'}, 'base64': 'JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCAzMDAgMzAwXSAvUmVzb3VyY2VzIDw8IC9Gb250IDw8IC9GMSA0IDAgUiA+PiA+PiAvQ29udGVudHMgNSAwIFIgPj4KZW5kb2JqCjQgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9CYXNlRm9udCAvSGVsdmV0aWNhID4+CmVuZG9iago1IDAgb2JqCjw8IC9MZW5ndGggNjUgPj4Kc3RyZWFtCkJUIC9GMSAxMiBUZiAzMCAyNTAgVGQgKFB1YmxpYyBQREYgZXhhY3QgY2FuYXJ5IGVuZG1hcmtlci4pIFRqIEVUCmVuZHN0cmVhbQplbmRvYmoKeHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDA5IDAwMDAwIG4gCjAwMDAwMDAwNTggMDAwMDAgbiAKMDAwMDAwMDExNSAwMDAwMCBuIAowMDAwMDAwMjQxIDAwMDAwIG4gCjAwMDAwMDAzMTEgMDAwMDAgbiAKdHJhaWxlcgo8PCAvU2l6ZSA2IC9Sb290IDEgMCBSID4+CnN0YXJ0eHJlZgo0MjYKJSVFT0YK'}}

def retain(name,value):
    if os.environ.get('RETAINED_LITERATURE_EVIDENCE'):
        d=Path(os.environ['RETAINED_LITERATURE_EVIDENCE']);d.mkdir(parents=True,exist_ok=True)
        (d/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


def tree(root,*,bibliography=False,manuscript=True):
    (root/'p/manuscript').mkdir(parents=True)
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'project','project_dir':'p','manifest':{'writing':{'kind':'general'}}}]}))
    (root/'profiles').mkdir();(root/'profiles/writing_sources.json').write_text('{"repositories":{}}')
    if manuscript:
        (root/'p/manuscript/main.tex').write_text('\\documentclass{article}\n\\begin{document}\nPublic controlled fixture.\n'+('\\bibliography{sources}\n' if bibliography else '')+'\\end{document}\n')
    if bibliography:(root/'p/manuscript/sources.bib').write_text('@book{Unrelated,title={Keep exact human bytes}}\n')
    return root


def seed_original(root,*,pdf=False):
    # Retain exact already-public fixture receipt/bytes; no upload or environment path dependency.
    fixture=PUBLIC_ORIGINALS['pdf' if pdf else 'text'];row=copy.deepcopy(fixture['record']);raw=base64.b64decode(fixture['base64'])
    assert hashlib.sha256(raw).hexdigest()==row['sha256']
    target=root/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    records.bank(root,row)
    return {'artifact_id':row['id'],'expected_sha256':'sha256:'+row['sha256']},raw


def wire(original,title='Explicit public source',citekey='PublicRetained'):
    return {'original':copy.deepcopy(original),'metadata':{'title':title,'creators':['Public Fixture Author'],'year':'2026','item_type':'unpublished'},
        'provenance':{'description':'Reused exact public intake fixture original; explicit metadata only.'},'citekey':citekey}


def get(root,handle):
    from urllib.parse import urlsplit,parse_qs
    u=urlsplit(handle['http']['url']);status,_,body=refs.handle(u.path,parse_qs(u.query),'GET',b'',repo_root=root)
    assert status==200,body
    return json.loads(body)


def test_source_optional_metadata_identity_replay_concurrency_and_differing_input(tmp_path):
    root=tree(tmp_path,manuscript=False);original,raw=seed_original(root)
    prepared=lit.retained_source('p',original,root);assert prepared['support']['permitted'] and prepared['standing']['state']=='NONE'
    assert not (root/'p/manuscript/references.json').exists()
    payload=wire(original)
    with ThreadPoolExecutor(2) as pool:replies=list(pool.map(lambda _:lit.import_reference('p',payload,root),range(2)))
    assert sorted(code for code,_ in replies)==[200,201]
    saved=lit.retained_source('p',original,root);assert saved['standing']['state']=='RECORDED'
    assert saved['standing']['bibliography']['state']=='PENDING' and not (root/'p/manuscript/main.tex').exists()
    rows=refs._load_associations(root/'p/manuscript');assert len(rows)==1 and not rows[0].get('reading_observations') and not rows[0].get('claim_id')
    before=(root/'p/manuscript/references.json').read_bytes();code,other=lit.import_reference('p',wire(original,'Different submitted metadata','OtherKey'),root)
    assert code==200 and other['reused'] and not other['submitted_matches_saved']['metadata'] and not other['submitted_matches_saved']['citekey']
    assert (root/'p/manuscript/references.json').read_bytes()==before
    assert other['association']['citekey']=='PublicRetained' and other['association']['metadata']['title']=='Explicit public source'
    assert rows[0]['metadata']['provenance']['original']==dict(project='p',**original) and 'path' not in rows[0]['metadata']['provenance']
    retain('source-optional-replay',{'prepared':prepared,'replies':replies,'saved':saved,'different':other})


def test_actual_http_native_source_text_and_literal_bibliography(tmp_path):
    root=tree(tmp_path,bibliography=True);original,raw=seed_original(root)
    from laplace.native import tools
    prepared=tools.execute(root,'p','review','reference_source',{'original':original})
    assert prepared['standing']['state']=='NONE'
    action=prepared['actions']['import'];payload={**action['payload'],**wire(original)}
    status,_,body=refs.handle('/references/literature-import',{},'POST',json.dumps(payload).encode(),repo_root=root);saved=json.loads(body)
    assert status==201 and saved['metadata_saved'] and saved['bibliography']['state']=='ATTACHED'
    bib=root/'p/manuscript/sources.bib';assert bib.read_text().startswith('@book{Unrelated,title={Keep exact human bytes}}\n')
    assert bib.read_text().count('laplace_key')==1
    reconciled=get(root,saved['read']);info=get(root,reconciled['source_read']);assert info['original']==dict(project='p',**original)
    observed=get(root,reconciled['text_read']);assert observed['text']==raw.decode() and observed['reading_receipt']['original']==dict(project='p',**original)
    assert observed['reading_receipt']['source_sha256']==original['expected_sha256']
    again=tools.execute(root,'p','review','reference_text',observed['page_read']['payload']);assert again['text']==observed['text']
    with pytest.raises(ValueError):tools.execute(root,'p','review','literature_import',wire(original))
    retain('http-native-reading',{'prepared':prepared,'saved':saved,'reconciled':reconciled,'source':info,'observation':observed,'native_page':again})


def test_original_scope_hash_closed_input_and_unavailable_home(tmp_path):
    root=tree(tmp_path,manuscript=False);original,raw=seed_original(root)
    for bad in [{**original,'path':'/private'},{**original,'expected_sha256':'f'*64}]:
        with pytest.raises(ValueError):lit.retained_source('p',bad,root)
    with pytest.raises(ValueError):lit.retained_source('another',original,root)
    code,refused=lit.import_reference('p',{**wire(original),'doi':'10.1234/no-network'},root);assert code==422
    code,refused=lit.import_reference('p',{**wire(original),'provenance':{'description':'Do not mix','path':'private'}},root);assert code==422
    missing=root/'p/manuscript';missing.rmdir()
    unready=lit.retained_source('p',original,root);assert not unready['support']['permitted']
    assert not missing.exists() and unready['source']['original_read']
    retain('scope-unavailable',unready)


def test_partial_bibliography_fact_survives_pure_reconcile_and_retry(tmp_path,monkeypatch):
    root=tree(tmp_path,bibliography=True);original,raw=seed_original(root);actual=lit._materialize
    def interrupted(*a,**k):raise OSError('Public injected bibliography interruption before effect')
    monkeypatch.setattr(lit,'_materialize',interrupted)
    code,result=lit.import_reference('p',wire(original),root)
    assert code==201 and result['metadata_saved'] and result['partial']
    observed=lit.retained_source('p',original,root);assert observed['standing']['state']=='RECORDED' and observed['standing']['bibliography_follow_through']['state']=='PARTIAL'
    monkeypatch.setattr(lit,'_materialize',actual)
    code,finished=lit.import_reference('p',wire(original),root);assert code==200 and finished['bibliography']['state']=='ATTACHED'
    before=(root/'p/manuscript/sources.bib').read_bytes();lit.import_reference('p',wire(original),root)
    assert (root/'p/manuscript/sources.bib').read_bytes()==before
    retain('partial-reconcile',{'partial':result,'pure':observed,'finished':finished})


def test_citation_collision_is_not_false_bibliography_identity_or_source_merge(tmp_path):
    root=tree(tmp_path,bibliography=True);original,raw=seed_original(root);before=(root/'p/manuscript/sources.bib').read_bytes()
    code,result=lit.import_reference('p',wire(original,citekey='Unrelated'),root)
    assert code==201 and result['metadata_saved'] and result['bibliography']['state']=='CONFLICT'
    assert result['partial'] and (root/'p/manuscript/sources.bib').read_bytes()==before
    assert result['retained_source']['standing']['bibliography_follow_through']['state']=='PARTIAL'
    retain('citation-collision',result)


def test_typed_original_and_observed_receipt_survive_fresh_project_home(tmp_path):
    root=tree(tmp_path/'old',bibliography=True);original,raw=seed_original(root);_,saved=lit.import_reference('p',wire(original),root)
    observed=get(root,saved['retained_source']['text_read']);receipt=observed['reading_receipt']
    # Simulate a separately admitted public project relocation, never migrate author data.
    fresh=tmp_path/'fresh';fresh.mkdir();shutil.copytree(root/'p',fresh/'moved-project');shutil.copytree(root/'contract',fresh/'contract')
    (fresh/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'project','project_dir':'moved-project','manifest':{'writing':{'kind':'general'}}}]}))
    shutil.rmtree(root)
    current=lit.retained_source('p',original,fresh);assert current['standing']['key']==saved['association']['key']
    source,path=lit.source_info('p',current['standing']['key'],fresh);assert path.is_relative_to(fresh/'moved-project') and path.read_bytes()==raw
    assert support.receipt_current(receipt,project='p',root=fresh) and support.source_receipt_current('p',current['standing']['association'],receipt,fresh)
    reread=get(fresh,current['text_read']);assert reread['text']==observed['text']
    retain('relocated-original',{'saved':saved,'receipt':receipt,'current':current,'source':source,'reread':reread})


def test_actual_observed_passage_then_meaning_guarded_existing_claim(tmp_path):
    root=tree(tmp_path,bibliography=True);original,raw=seed_original(root);_,saved=lit.import_reference('p',wire(original),root)
    from laplace.research import corpus_ingest as ci
    # Existing concept-corpus owner requires an explicitly supported project, not a fabricated claim in the general metadata-only fixture.
    registry=json.loads((root/'registry_projects.json').read_text());registry['projects'][0].update(kind='conceptric',tex_root='p/manuscript');(root/'registry_projects.json').write_text(json.dumps(registry))
    net=ci.corpus_network(ci.resolve_corpus(root,'p'),repo_root=root,name='p')
    made=ci.rewire_add(root,'p',{'kind':'add-node','node':'claim:public','node_kind':'result','essence':'This controlled sample contains the word Public.','parent':net.get('root'),'by':'public-fixture'})
    assert made.get('ok'),made
    key=saved['association']['key'];observed=lit.observe_read('p',key,root,limit=1000)
    payload={'key':key,'claim_id':'claim:public','claim_revision':support.meaning_revision('p','claim:public',root),
        'relation':'supports','rationale':'The returned supplied fixture passage contains this word; no independent scientific verification.',
        'reading_status':'partial','reading_id':observed['reading_receipt']['id'],'evidence':{'locator':observed['reading_receipt']['locator'],'excerpt':'Public'}}
    code,bound=lit.bind('p',payload,root);assert code==200 and bound['association']['binding_state']=='BOUND',bound
    from laplace.research import concepts
    qualification=support.for_node('p','claim:public',root)
    assert qualification['sources'][0]['qualification']=='PASSAGE_OBSERVED'
    stale={**payload,'claim_revision':'sha256:'+'f'*64};code,error=lit.bind('p',stale,root);assert code==409
    retain('actual-claim-passage',{'claim':made,'observation':observed,'bound':bound,'qualification':qualification,'stale_refusal':error})


def test_legacy_manual_and_stubbed_doi_modes_remain_existing_owners(tmp_path,monkeypatch):
    root=tree(tmp_path,bibliography=True);path=root/'manual.txt';path.write_text('Public old manual source')
    code,manual=lit.import_reference('p',{'metadata':{'title':'Manual retained behavior'},'provenance':{'description':'Existing path mode','path':str(path)},'citekey':'LegacyManual'},root)
    assert code==201 and manual['association']['metadata']['provenance']['path']==str(path)
    calls=[]
    def lookup(value):
        calls.append(value);return {'provider':'crossref','item':{'key':'doi:10.1234/public','doi':'10.1234/public','title':'Explicit stubbed metadata','version':'v1','modified':''}}
    monkeypatch.setattr(lit,'lookup',lookup)
    code,doi=lit.import_reference('p',{'doi':'10.1234/public','citekey':'LegacyDOI'},root)
    assert code==201 and calls==['10.1234/public'] and doi['association']['key']=='doi:10.1234/public'
    retain('legacy-modes',{'manual':manual,'doi':doi,'qualification':'DOI metadata seam stubbed; no external lookup.'})


def test_existing_pdf_original_handle_and_actual_text_observation(tmp_path):
    root=tree(tmp_path,manuscript=False);original,raw=seed_original(root,pdf=True)
    code,saved=lit.import_reference('p',wire(original,citekey='PublicPDF'),root);assert code==201
    prepared=get(root,saved['read']);info=get(root,prepared['source_read'])
    assert info['sha256']==original['expected_sha256'] and info['original']==dict(project='p',**original)
    from urllib.parse import urlsplit,parse_qs
    u=urlsplit(prepared['source_read']['http']['url']);query=parse_qs(u.query);query['format']=['pdf']
    status,headers,body=refs.handle(u.path,query,'GET',b'',repo_root=root)
    assert status==200 and body==raw and headers=='application/pdf'
    text=get(root,prepared['text_read']);assert 'Public' in text['text'] and text['reading_receipt']['original']==dict(project='p',**original)
    assert text['reading_receipt']['source_sha256']==original['expected_sha256']
    retain('actual-pdf-source',{'saved':saved,'prepared':prepared,'source':info,'observation':text,'raw_sha256':hashlib.sha256(body).hexdigest(),'qualification':'Existing real pdftotext owner on reused 609-byte public PDF; no visual or scientific qualification.'})


@pytest.mark.parametrize('raw',[[],None,{'associations':{}},{'associations':[None]},{'schema_version':'unknown/2','associations':[]}])
def test_retained_unknown_association_custody_preserves_existing_bytes(tmp_path,raw):
    root=tree(tmp_path,manuscript=False);original,_=seed_original(root)
    file=root/'p/manuscript/references.json';before=(json.dumps(raw)+'\n').encode();file.write_bytes(before)
    prepared=lit.retained_source('p',original,root)
    assert prepared['standing']['state']=='UNKNOWN' and not prepared['actions']['import']['permitted']
    code,result=lit.import_reference('p',wire(original),root)
    assert code==409 and not result['metadata_saved'] and result['retained_source']['standing']['state']=='UNKNOWN'
    assert file.read_bytes()==before
    retain('unsupported-'+hashlib.sha256(before).hexdigest()[:8],{'before':before.decode(),'prepared':prepared,'result':result,'after':file.read_text()})


@pytest.mark.parametrize('initial',[None,{}, {'associations':[]},{'schema_version':'laplace.references/1','associations':[]}])
def test_retained_supported_empty_and_absent_associations_still_import(tmp_path,initial):
    root=tree(tmp_path,manuscript=False);original,_=seed_original(root)
    file=root/'p/manuscript/references.json'
    if initial is not None:file.write_text(json.dumps(initial)+'\n')
    assert lit.retained_source('p',original,root)['standing']['state']=='NONE'
    code,saved=lit.import_reference('p',wire(original),root)
    assert code==201 and saved['metadata_saved']
    assert lit.retained_source('p',original,root)['standing']['state']=='RECORDED'


@pytest.mark.parametrize('change,reason',[
    ({'metadata':{'title':'Explicit title','item_type':''}},'INVALID_RETAINED_IMPORT'),
    ({'metadata':{'title':'   '}},'BLANK_REQUIRED_DETAILS'),
    ({'provenance':{'description':'   '}},'BLANK_REQUIRED_DETAILS')])
def test_retained_exact_validation_disposition_precedes_original_and_native_http_effects(tmp_path,monkeypatch,change,reason):
    root=tree(tmp_path,manuscript=False);original,_=seed_original(root);payload={**wire(original),**change}
    def forbidden(*a,**k):raise AssertionError('Original resolution must not run on this input rejection')
    monkeypatch.setattr(lit,'retained_original',forbidden)
    status,answer=lit.import_reference('p',payload,root)
    expected={'state':'REJECTED_BEFORE_EFFECTS','operation':'literature_import','reason_code':reason}
    assert status==422 and answer['disposition']==expected and answer['metadata_saved'] is False
    status,_,body=refs.handle('/references/literature-import',{},'POST',json.dumps({'project':'p',**payload}).encode(),repo_root=root)
    assert status==422 and json.loads(body)==answer
    from laplace.native import tools
    with pytest.raises(lit.RetainedImportRejected) as caught:tools.execute(root,'p','work','literature_import',payload)
    native=tools.failure_response(root,'p','work','literature_import',payload,caught.value)
    assert native['disposition']==expected and native['metadata_saved'] is False
    assert not (root/'p/manuscript/references.json').exists()
    retain('validation-'+reason+'-'+str(len(payload['metadata'].get('title',''))),{'payload':payload,'http':answer,'native':native})


def test_retained_generic_custody_refusal_and_partial_never_claim_input_rejection(tmp_path,monkeypatch):
    root=tree(tmp_path,bibliography=True);original,_=seed_original(root)
    file=root/'p/manuscript/references.json';file.write_text('[]\n')
    status,unknown=lit.import_reference('p',wire(original),root)
    assert status==409 and unknown['retained_source']['standing']['state']=='UNKNOWN' and 'disposition' not in unknown
    file.unlink()
    monkeypatch.setattr(lit,'_materialize',lambda *a,**k: (_ for _ in ()).throw(OSError('Public partial effect seam')))
    status,partial=lit.import_reference('p',wire(original),root)
    assert status==201 and partial['metadata_saved'] and partial['partial'] and 'disposition' not in partial
    assert not lit.retained_import_error_details(ValueError('422 invalid'))
    retain('nonterminal-validation-control',{'unknown':unknown,'partial':partial})
