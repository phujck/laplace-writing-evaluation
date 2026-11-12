"""Work consumer seam controls; real Source admission is exercised after owner composition.

These tests stub only the published Source helper interface, never claim Source grants/effects.
The actual Work/native/HTTP phase/standing code executes against public temporary data.
"""
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from laplace.work import project_work as W, project_work_review as R, development_source as D
from laplace.web import project_work_surface as HTTP
from test_work_review_lifecycle import root, guard, native, post, sha, P

SELECTION={'grant_id':'DG-public','candidate_id':'DC-public'}

@pytest.fixture
def source(root,monkeypatch):
    checkout=root/'configured';checkout.mkdir()
    paths=['src/a.py','src/b.py','docs/guide.md']
    for name in paths:
        p=checkout/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('configured '+name+'\n')
    pins={name:sha(checkout,name) for name in paths}
    basis={'schema_version':'laplace.development-review-basis/1','project':P,'work_id':'parent',**SELECTION,
           'effect_id':'DE-public','repository':'source-public','checkout_identity':'sha256:'+'a'*64,'base':'public-base','pins':copy.deepcopy(pins)}
    calls=[];state={'expired':False,'identity':'CURRENT'}
    def prepare(repo,project,work,selection,provided,*,door):
        calls.append(('prepare',copy.deepcopy(provided),copy.deepcopy(door)))
        assert (repo,project,work,selection)==(root,P,'parent',SELECTION)
        if state['expired']:raise ValueError('expired write grant')
        if provided!=pins:raise ValueError('Source supplied pins differ')
        return copy.deepcopy(basis)
    def validate(repo,project,work,held,*,consumed_pins=None,door=None,read_context=None):
        # The published Source helper signature (development_source.validate_review_basis) includes read_context.
        calls.append(('validate',copy.deepcopy(consumed_pins),copy.deepcopy(door)))
        if door and door.get('turn_id') not in {'WT-prod','WT-rev'}:raise ValueError('Not actual Source holder/evaluator')
        if held!=basis:return {'status':'UNKNOWN','reason':'Malformed recorded Source identity','observed_pins':{}}
        if state['identity']!='CURRENT':return {'status':state['identity'],'reason':'Configured source unavailable or retargeted','observed_pins':{}}
        selected=held['pins'] if consumed_pins is None else consumed_pins
        if any(held['pins'].get(name)!=pin for name,pin in selected.items()):raise ValueError('Consumed pins are not an identical subset')
        observed={name:sha(checkout,name) if (checkout/name).is_file() else None for name in selected}
        return {'status':'UNKNOWN' if None in observed.values() else 'CHANGED' if observed!=selected else 'CURRENT',
                'reason':'Exact configured Source pin observation','observed_pins':observed}
    monkeypatch.setattr(D,'prepare_review_basis',prepare,raising=False);monkeypatch.setattr(D,'validate_review_basis',validate,raising=False)
    return {'root':root,'checkout':checkout,'pins':pins,'basis':basis,'calls':calls,'state':state}


def hand(source,request='source-hand-off-1',**kw):
    return native(source['root'],'WT-prod',{'id':'parent','phase':'handoff','request_id':request,'expected_work_revision':guard(source['root']),
                  'source_basis':SELECTION,'pins':source['pins'],'obligations':['source','guide'],**kw})

def review(source,h,obligation='source',turn='WT-rev',request='source-review-1',**kw):
    return native(source['root'],turn,{'id':'parent','phase':'review','request_id':request,'expected_work_revision':guard(source['root']),
                  'handoff_id':h['phase']['id'],'obligation_id':obligation,'verdict':'ACCEPT',**kw},mode='review')


def test_source_wire_is_handoff_only_and_legacy_repository_label_does_not_select_checkout(source):
    s=source;h=hand(s);assert h['phase']['source_basis']==s['basis'];assert h['phase']['pins']==s['pins']
    supplied={'id':'parent','phase':'review','request_id':'review-with-foreign-field','expected_work_revision':guard(s['root']),
              'handoff_id':h['phase']['id'],'obligation_id':'source','verdict':'ACCEPT','source_basis':SELECTION}
    before=W._ledger(s['root']).read_bytes();code,body=post(s['root'],supplied);assert code>=400 and body['error'];assert W._ledger(s['root']).read_bytes()==before
    # The historical label remains metadata and therefore cannot make configured pins canonical.
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        native(s['root'],'WT-prod',{'id':'parent','phase':'handoff','request_id':'legacy-label-control','expected_work_revision':guard(s['root']),
                                   'object':{'repository':'source-public'},'pins':s['pins']})
    assert W._ledger(s['root']).read_bytes()==before


def test_reviews_use_exact_source_subset_and_pure_currentness_never_canonical_fallback(source,monkeypatch):
    s=source;h=hand(s);result=review(s,h);row=result['phase'];assert row['source_basis']==h['phase']['source_basis']
    assert row['pins']=={key:s['pins'][key] for key in ['src/a.py','src/b.py']};assert row['independence']=='INDEPENDENT'
    s['checkout'].joinpath('docs/guide.md').write_text('unrelated guide update')
    assert R.decision(row,W._tasks(P,s['root'])['parent']['review_obligations'][0],s['root'])['satisfied']
    s['checkout'].joinpath('src/a.py').write_text('changed consumed source')
    assert R.decision(row,W._tasks(P,s['root'])['parent']['review_obligations'][0],s['root'])['currentness']=='STALE'
    s['checkout'].joinpath('src/a.py').unlink()
    assert R.decision(row,W._tasks(P,s['root'])['parent']['review_obligations'][0],s['root'])['currentness']=='UNKNOWN'
    s['state']['identity']='CHANGED'
    assert R.decision(row,W._tasks(P,s['root'])['parent']['review_obligations'][0],s['root'])['currentness']=='STALE'
    malformed={**row,'source_basis':None};monkeypatch.setattr(R,'_file_digest',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Source basis fell back to canonical bytes')))
    assert R.decision(malformed,W._tasks(P,s['root'])['parent']['review_obligations'][0],s['root'])['currentness']=='UNKNOWN'


def test_expired_write_authority_does_not_erase_handoff_replay_or_historical_review(source):
    s=source;h=hand(s);s['state']['expired']=True
    repeated=hand(s);assert repeated['status']=='REUSED';assert len([x for x in s['calls'] if x[0]=='prepare'])==1
    result=review(s,h);row=result['phase'];assert row['pins'] and row['source_basis']==h['phase']['source_basis']
    assert R.decision(row,W._tasks(P,s['root'])['parent']['review_obligations'][0],s['root'])['satisfied']
    # Currentness consumes no caller door; admission did prove the actual review door.
    assert any(x[0]=='validate' and x[2]=={'origin':'native','turn_id':'WT-rev'} for x in s['calls'])
    assert s['calls'][-1][2] is None
    before=W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError,match='Not actual Source holder'):
        review(s,h,turn='WT-prod-2',request='not-source-evaluator')
    assert W._ledger(s['root']).read_bytes()==before
    with pytest.raises(ValueError,match='expired'):
        hand(s,request='new-expired-handoff')


def test_source_coverage_and_supplied_review_pins_are_exact_and_returned_basis_detached(source):
    s=source;before=W._ledger(s['root']).read_bytes()
    # Covered inputs must all be present, even if owner candidate validation itself passes.
    missing={**s['basis'],'pins':{'src/a.py':s['pins']['src/a.py']}}
    import unittest.mock
    with unittest.mock.patch.object(D,'prepare_review_basis',return_value=missing):
        with pytest.raises(ValueError,match='pins every declared input'):
            hand(s)
    assert W._ledger(s['root']).read_bytes()==before
    h=hand(s);h['phase']['source_basis']['pins']['src/a.py']='caller mutation'
    held=W._tasks(P,s['root'])['parent']['phases'][0];assert held['source_basis']['pins']==s['pins']
    with pytest.raises(ValueError,match='exactly the handed-off'):
        review(s,{'phase':held},pins={'docs/guide.md':s['pins']['docs/guide.md']})


def test_work_jsonl_unicode_physical_record_boundaries():
    """The owner's _fold_rows splits records only at physical LF; NEL/LS/PS inside JSON strings stay content.

    Self-contained on purpose: it parses and executes the actual _fold_rows definition from the owner source without
    importing Laplace, so the mechanical parser_predicate_only profile can run it. The tests below exercise the real
    module and a fresh process. Separator characters are generated with chr() at runtime; diagnostics are ASCII.
    """
    import ast, json, pathlib
    source=pathlib.Path(__file__).resolve().parents[1]/'src'/'laplace'/'work'/'project_work.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    defs=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_fold_rows']
    assert len(defs)==1,'owner _fold_rows definition absent or duplicated'
    ns={'json':json};exec(compile(ast.Module(body=defs,type_ignores=[]),str(source),'exec'),ns);fold_rows=ns['_fold_rows']
    nel,ls,ps=chr(0x85),chr(0x2028),chr(0x2029)
    show=lambda value:json.dumps(value,ensure_ascii=True)
    expected=[{'record':'project-work','id':'WORK-1','title':'a'+nel+'b'},
              {'record':'project-work-phase','work_id':'WORK-1','body':ls+'x'+ps+'y'+ls},
              {'record':'project-work','id':'WORK-2','title':nel+ls+ps}]
    physical=[json.dumps(row,ensure_ascii=False) for row in expected]
    assert all(c in ''.join(physical) for c in (nel,ls,ps)),'fixture must carry literal separators inside JSON strings'
    variants={'lf':'\n'.join(physical)+'\n','crlf':'\r\n'.join(physical)+'\r\n',
              'blank':'\n\n'+physical[0]+'\n \t\n'+physical[1]+'\r\n\r\n'+physical[2]}
    for name,text in variants.items():
        try:   # the former text.splitlines() boundary must actually fail on this fixture
            [json.loads(x) for x in text.splitlines() if x.strip()]
        except ValueError:
            pass
        else:
            raise AssertionError('fixture does not discriminate splitlines boundaries: '+name)
        rows=fold_rows(text)
        assert len(rows)==3 and rows==expected,name+': '+show(rows)+' != '+show(expected)
    malformed={'truncated':physical[0]+'\n'+physical[1][:-2]+'\n'+physical[2]+'\n',
               'string-split-by-lf':physical[0]+'\n{"record": "project-work", "title": "a\nb"}\n',
               'trailing-garbage':physical[0]+' x\n'}
    for name,text in malformed.items():
        try:
            fold_rows(text)
        except ValueError:
            continue
        raise AssertionError('malformed physical record accepted: '+name)


def _unicode_ledger_rows():
    nel,ls,ps=chr(0x85),chr(0x2028),chr(0x2029)
    project='p-jsonl-unicode'
    return project,[
        {'record':'project-work','project':project,'id':'WORK-u1','title':'alpha'+nel+'one','status':'open','ts':'2026-11-03T00:00:00Z'},
        {'record':'project-work-phase','project':project,'work_id':'WORK-u1','kind':'development-candidate','id':'DC-u1','body':'line'+ls+'sep'+ps+'end'},
        {'record':'project-work','project':project,'id':'WORK-u2','title':'beta'+ls,'status':'ready','ts':'2026-11-03T00:00:01Z'},
        {'record':'project-work','project':'p-jsonl-other','id':'WORK-u1','title':'other'+ps,'status':'open','ts':'2026-11-03T00:00:02Z'},
        {'record':'project-work','project':project,'id':'WORK-u1','status':'in-progress','ts':'2026-11-03T00:00:03Z'}]


def _write_ledger(root,rows,newline='\n',blank=False):
    text=newline.join(json.dumps(row,ensure_ascii=False) for row in rows)+newline
    if blank:text=newline+text.replace(newline,newline+' \t'+newline,1)+newline
    path=W._ledger(root);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(text.encode('utf-8'))
    return path


def test_work_jsonl_unicode_rows_reconstruct_through_owner_and_fresh_process(tmp_path):
    project,rows=_unicode_ledger_rows();nel,ls,ps=chr(0x85),chr(0x2028),chr(0x2029)
    path=_write_ledger(tmp_path,rows);before=path.read_bytes()
    assert all(c.encode('utf-8') in before for c in (nel,ls,ps)) and before.count(b'\n')==len(rows)
    assert list(W._rows(tmp_path))==rows
    tasks=W._tasks(project,tmp_path)
    assert sorted(tasks)==['WORK-u1','WORK-u2']
    assert tasks['WORK-u1']['title']=='alpha'+nel+'one' and tasks['WORK-u1']['status']=='in-progress'
    assert tasks['WORK-u1']['development']==(rows[1],) and tasks['WORK-u2']['title']=='beta'+ls
    assert W._tasks('p-jsonl-other',tmp_path)['WORK-u1']['title']=='other'+ps
    assert path.read_bytes()==before
    # A fresh interpreter importing the same owner module reconstructs the same records from the same bytes.
    src=str(Path(W.__file__).resolve().parents[2])
    code=('import json,sys\nfrom laplace.work import project_work as W\n'
          'print(json.dumps({"rows":list(W._rows(sys.argv[1])),"tasks":W._tasks(sys.argv[2],sys.argv[1])},ensure_ascii=True))\n')
    env={**os.environ,'PYTHONPATH':os.pathsep.join(p for p in (src,os.environ.get('PYTHONPATH','')) if p),'PYTHONDONTWRITEBYTECODE':'1'}
    done=subprocess.run([sys.executable,'-c',code,str(tmp_path),project],capture_output=True,text=True,encoding='ascii',
                        errors='backslashreplace',env=env,cwd=str(tmp_path),timeout=60)
    assert done.returncode==0,ascii(done.stderr[-2000:])
    fresh=json.loads(done.stdout)
    assert fresh['rows']==rows and fresh['tasks']==json.loads(json.dumps(tasks,ensure_ascii=True))
    assert fresh['tasks']['WORK-u1']['title']=='alpha'+nel+'one' and fresh['tasks']['WORK-u1']['development']==[rows[1]]
    assert path.read_bytes()==before


@pytest.mark.parametrize('newline,blank',[('\n',True),('\r\n',False),('\r\n',True)])
def test_work_jsonl_crlf_and_blank_lines_keep_every_unicode_record(tmp_path,newline,blank):
    project,rows=_unicode_ledger_rows()
    path=_write_ledger(tmp_path,rows,newline=newline,blank=blank);before=path.read_bytes()
    assert list(W._rows(tmp_path))==rows
    tasks=W._tasks(project,tmp_path)
    assert tasks['WORK-u1']['development']==(rows[1],) and tasks['WORK-u1']['status']=='in-progress'
    assert path.read_bytes()==before


@pytest.mark.parametrize('damage',['truncated-record','string-split-by-physical-lf','trailing-garbage'])
def test_work_jsonl_malformed_physical_record_is_refused_not_dropped(tmp_path,damage):
    project,rows=_unicode_ledger_rows()
    physical=[json.dumps(row,ensure_ascii=False) for row in rows]
    if damage=='truncated-record':physical[1]=physical[1][:-2]
    elif damage=='string-split-by-physical-lf':physical[2]=physical[2].replace('beta','be\nta')
    else:physical[3]=physical[3]+' x'
    path=W._ledger(tmp_path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(('\n'.join(physical)+'\n').encode('utf-8'));before=path.read_bytes()
    with pytest.raises(json.JSONDecodeError):
        W._tasks(project,tmp_path)
    assert W.fold_cache_state(tmp_path) is None and path.read_bytes()==before
