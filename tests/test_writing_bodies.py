from laplace.writing import records as record_owner
"""The extracted owner preserves exact82 custody bytes and bounded hydration."""
import hashlib,json,subprocess,sys
from pathlib import Path
import pytest
from laplace.representation import writing_bodies as bodies
from laplace.core import bodies as core_bodies
from laplace.native import verbs, tools
from laplace.writing.records import _bank as records_bank
from laplace.core.bodies import REFERENCE_SCHEMA as PUBLIC_BODY_SCHEMA

ROOT=Path(__file__).resolve().parents[1]


def test_decorated_rows_match_exact_live82_baseline(tmp_path):
    # Hashes observed through the actual82 owner in an empty owned fixture.
    # Inputs are generated here; no large retained fixture/history is copied.
    text='Retained author body — 雪\n'*600
    rows=[{'record':'writing-artifact','id':'ART-exact','project':'fixture','before':None,'after':text},
      {'record':'writing-tool-action','id':'ACTION-exact','payload':{'content':text,'reason':'Human intent','before':None},'outcome':{'ok':True}},
      {'record':'writing-tool-failure','id':'FAIL-exact','payload':['invalid',7,None,True],**verbs.requested_by_metadata('Requested reviewer — '+('雪'*300))},
      {'record':'writing-proposal','id':'PROP-exact','proposal':{'summary':'Change','edits':[{'file':'a.tex','before':'Old','after':'New','line_start':1,'line_end':1}]}},
      {'record':'writing-turn-context-baseline','id':'CTX-exact','consumed':{'corrections':['A','B',7]},'dependencies':{'long':text}},
      {'record':'writing-reply','id':'WR-exact','actions':[{'id':'ACTION-one','outcome':{'ok':True}}],'text':'Exact answer'}]
    expected=['c7edd5180677dce42f6b08a2951b831cece2cb08aa3cda40a4f63cce61e7eef7',
      'cab8143e745caa93fbf3ba3c3eb5ff8a0d3ba4883be2d6f2a95c0d9d2c0cfef2',
      '686b1918be16db6bc55852961dda3300a9d02d7d997c409daaa86e9aba90de6f',
      '1d5fb6b32f440f09f564aeba60afaa4c91781f06083e292d05bb130d6f66209e',
      '9eeba816e27f562073417a66175e3fa6acdedb3011a669f1d71258ba4fd7ad18',
      '9ee3147507d1122c587a02726e156614b04f3a57717f843fea6d0cc4f853a892']
    prepared=[records_bank.prepare_custody_row(tmp_path,row) for row in rows]
    assert [hashlib.sha256(core_bodies.encode(row)).hexdigest() for row in prepared]==expected
    assert prepared[0]['after']['schema_version']==PUBLIC_BODY_SCHEMA
    retained_payload=json.loads(bodies.read_bytes(prepared[1]['payload'],tmp_path))
    assert prepared[0]['after']['content_handle']==retained_payload['content']['content_handle']
    assert bodies.resolve_fields(prepared[0],tmp_path)['after']==text
    assert bodies.resolve_fields(prepared[1],tmp_path)['payload']['content']==text
    assert bodies.resolve_fields(prepared[2],tmp_path)['payload']==rows[2]['payload']
    assert prepared[2]['requested_by']==rows[2]['requested_by']
    files=[p for p in (tmp_path/'contract/writing_bodies').rglob('*') if p.is_file()]
    assert len(files)==4 and sum(p.stat().st_size for p in files)==36309


def test_cold_leaf_import_and_roundtrip_do_not_import_controllers(tmp_path):
    code='''import sys,json
from pathlib import Path
sys.path[:0]=sys.argv[1:2]
from laplace.representation import writing_bodies as bodies
for name in ('laplace.web.authoring','laplace.native.tools','laplace.writing.provider','laplace.manuscript.manuscript_proposals'):
 assert name not in sys.modules,name
root=Path(sys.argv[2]);value={'record':'writing-tool-failure','payload':['invalid',None,False,'雪']}
stored=bodies.prepare_row(root,value)
assert bodies.resolve_fields(stored,root)==value
reply={'record':'writing-reply','text':'Exact public answer'}
assert bodies.resolve_fields(reply,root)==reply
for name in ('laplace.web.authoring','laplace.native.tools','laplace.writing.provider','laplace.manuscript.manuscript_proposals'):
 assert name not in sys.modules,name
print('leaf-roundtrip')'''
    result=subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT/'src'),str(tmp_path)],
                          cwd=tmp_path,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='leaf-roundtrip'


@pytest.mark.parametrize('failure',['missing','corrupt','wrong-size','unsupported'])
def test_strict_and_tolerant_reference_failures_preserve_record(tmp_path,failure):
    stored=bodies.prepare_row(tmp_path,{'record':'writing-tool-failure','payload':['Exact request',False]})
    reference=stored['payload'];path=bodies.store(tmp_path).key_path(reference['content_handle'])
    if failure=='missing':path.unlink()
    elif failure=='corrupt':path.write_bytes(b'corrupt evidence')
    elif failure=='wrong-size':reference['bytes']+=1
    else:reference['schema_version']='laplace.writing-public-body-ref/99'
    before=json.loads(json.dumps(stored))
    with pytest.raises(ValueError,match='Saved writing body'):bodies.resolve_fields(stored,tmp_path)
    tolerant=bodies.resolve_fields(stored,tmp_path,strict=False)
    assert tolerant['payload']==reference and tolerant['_custody_errors']
    assert stored==before


def test_single_owner_alias_and_nested_fallback_diagnostics(tmp_path,monkeypatch):
    assert core_bodies.operation is core_bodies.operation
    assert bodies.resolve_fields is bodies.resolve_fields
    assert bodies.store is bodies.store
    class Unavailable:
        def put(self,raw):raise OSError('owned refusal')
    monkeypatch.setattr(bodies,'store',lambda root:Unavailable())
    with core_bodies.operation() as outer:
        with core_bodies.operation() as nested:
            assert outer is nested
            row=records_bank.prepare_custody_row(tmp_path,{'record':'writing-tool-failure','payload':['original',7,None]})
        assert row['payload']==['original',7,None] and outer['failed_attempts']==1
    assert core_bodies.current_operation() is None


def test_actual_nonobject_admission_failure_keeps_requested_attribution(tmp_path):
    from test_tool_refusal_recovery import turn
    turn(tmp_path);payload=['invalid',None,False];label='Requested reviewer — '+('雪'*300)
    with pytest.raises(ValueError) as raised:
        tools.call(tmp_path,'p','review',{'operation':'run_status','payload':payload,'by':label},turn_id='WT-r')
    answer=tools.tool_failure(tmp_path,'p','review','run_status',payload,raised.value,'WT-r')
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    failed=[row for row in rows if row.get('record')=='writing-tool-failure']
    assert len(failed)==1
    exact=bodies.resolve_fields(failed[0],tmp_path)
    assert exact['payload']==payload and exact['requested_by']==verbs.requested_by_metadata(label)['requested_by']
    assert answer['failure_receipt']['row_id']==failed[0]['id']


@pytest.mark.parametrize('unrelated',[0,200])
def test_selected_original_record_resolves_only_addressed_body(tmp_path,monkeypatch,unrelated):
    from laplace.work import author_history_metrics as metadata
    shared=bodies.prepare_row(tmp_path,{'record':'writing-artifact','after':'Unrelated retained text '*100})['after']
    for number in range(unrelated):
        record_owner.bank(tmp_path,{'record':'writing-artifact','id':'ART-'+str(number),'project':'other','after':shared})
    record_owner.bank(tmp_path,{'record':'writing-tool-failure','id':'FAIL-selected','project':'p','payload':['exact',7,None]})
    bodies_read=[];rows_read=[];read=bodies.read_bytes;raw=record_owner._index._raw_indexed_record
    monkeypatch.setattr(bodies,'read_bytes',lambda value,root:(bodies_read.append(value['content_handle']) or read(value,root)))
    monkeypatch.setattr(record_owner._index,'_raw_indexed_record',lambda idx,row:(rows_read.append(row['id']) or raw(idx,row)))
    exact,_meta=metadata.exact_record('p','FAIL-selected',tmp_path)
    assert exact['payload']==['exact',7,None]
    assert rows_read==['FAIL-selected'] and len(bodies_read)==1
    assert shared['content_handle'] not in bodies_read


def test_provider_reply_resolves_outer_metadata_only(tmp_path,monkeypatch):
    from laplace.writing import provider
    facts=provider._UsageFacts('codex',tmp_path,'T','model')
    facts.bind('native',fresh=True);facts.bind('native','turn')
    facts.codex({'last':{'inputTokens':5,'cachedInputTokens':1,'outputTokens':3,'totalTokens':8}})
    value=facts.snapshot();raw=core_bodies.encode(value)
    reference={'schema_version':PUBLIC_BODY_SCHEMA,'content_handle':bodies.store(tmp_path).put(raw),
               'store':'contract/writing_bodies','bytes':len(raw),'encoding':'application/json'}
    reads=[];read=bodies.read_bytes
    monkeypatch.setattr(bodies,'read_bytes',lambda value,root:(reads.append(value['content_handle']) or read(value,root)))
    resolved=bodies.resolve_fields({'record':'writing-reply','usage_facts':reference},tmp_path)
    assert resolved['usage_facts']==value
    assert reads==[reference['content_handle']]
    assert resolved['usage_facts']['observations'][0]['raw_observation_ref']['schema_version']==PUBLIC_BODY_SCHEMA
