"""The custody/runtime half of the source-to-consumer loop, with owned fixtures.

The observer process is harness-specific. Production health observes covered disk
startup inputs and never claims to fingerprint an individual loaded Atlas symbol.
"""
from __future__ import annotations
from laplace.representation import writing_bodies as bodies

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import tracemalloc
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from laplace.desktop import writing_app
from laplace.native import tools as writing_tools
from laplace.core import bodies as core_bodies
from laplace.writing.records import _bank as records_bank
from laplace.writing import session_reads
from test_writing_controller import _import_project
from test_writing_eval_manifest import fixture as export_fixture

ROOT = Path(__file__).resolve().parents[1]
BASE = "d6f24add165bde159310867d72d7249b1de32116"


def test_corrupt_duplicate_is_inline_visible_in_existing_receipt_and_reader(tmp_path):
    _import_project(tmp_path, editable=False)
    content = "public retained text\n" * 1500
    raw = core_bodies.encode(content)
    store = bodies.store(tmp_path)
    key = store.put(raw)
    store.key_path(key).write_bytes(b"corrupt retained evidence")
    result = writing_tools.execute(tmp_path, "fixture", "work", "store_artifact",
        {"path":"research/retained.md", "before":None, "content":content,"reason":"Owned custody fixture"}, turn_id="WT-runtime")
    observed = result["custody_degradation"]
    assert observed["status"] == "INLINE_RETAINED"
    assert observed["inline_bytes"] >= len(raw)
    assert observed["identities"] == [{"reason":"store-blob-hash-mismatch", "content_handle":key}]
    assert content not in json.dumps(observed)
    assert result["action_receipt"]["custody_degradation"] == observed
    rows = [json.loads(line) for line in (tmp_path/"contract/talk.jsonl").read_text().splitlines()]
    artifact = next(row for row in rows if row["record"] == "writing-artifact")
    assert artifact["after"] == content
    assert bodies.resolve_fields(artifact,tmp_path)["after"] == content
    assert rows[-1]["custody_degradation"] == observed
    read = writing_tools.execute(tmp_path,"fixture","work","read_artifact",{"id":result["id"]})
    assert read["custody_degradation"]["status"] == "INLINE_RETAINED"
    assert store.key_path(key).read_bytes() == b"corrupt retained evidence"
    # Operation state never leaks into the next invocation.
    healthy = writing_tools.execute(tmp_path,"fixture","work","store_artifact",
        {"path":"research/healthy.md","before":None,"content":"healthy","reason":"Owned custody fixture"})
    assert "custody_degradation" not in healthy


def test_diagnostics_are_bounded_and_deduplicated_without_payloads(tmp_path, monkeypatch):
    class Failure(Exception):
        reason = "store-blob-hash-mismatch"
        def __init__(self, key): self.detail = {"key":key}
    class RefusedStore:
        def put(self, raw): raise Failure("sha256:"+hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(bodies,"store",lambda root:RefusedStore())
    value = {"items":[str(index)*9000 for index in range(20)]}
    row = records_bank.prepare_custody_row(tmp_path,{"record":"writing-tool-action","payload":value})
    diagnostic=row["custody_degradation"]
    assert len(diagnostic["identities"]) == 8
    assert diagnostic["identities_omitted"] > 0
    assert len(json.dumps(diagnostic)) < 1600
    assert "9999999999" not in json.dumps(diagnostic)
    assert bodies.resolve_fields(row,tmp_path)["payload"] == value


def test_duplicate_verification_memory_and_growth(tmp_path, capsys):
    from laplace.representation import atlas_bridge
    rows=[]
    for size in (1024, 2*1024*1024):
        data=b"x"*size;store=atlas_bridge.BlobStore(tmp_path/str(size));key=store.put(data)
        path=store.key_path(key);before=path.stat()
        tracemalloc.start();start=time.perf_counter()
        for _ in range(20): assert store.put(data)==key
        elapsed=time.perf_counter()-start;peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
        assert path.stat().st_mtime_ns==before.st_mtime_ns
        assert path.stat().st_ino==before.st_ino
        assert peak < 350000  # bounded chunks, independent of 2MB body size
        rows.append({"bytes":size,"repeats":20,"seconds":elapsed,"peak_allocated_bytes":peak,
                     "input_hash_bytes":20*size,"stored_compare_bytes":20*size,
                     "retained_growth_bytes":0,"new_blob_files":0})
    print("CUSTODY_COST "+json.dumps(rows))


def _copy(root, relative):
    source=ROOT/relative;target=root/relative
    if not source.exists():return
    target.parent.mkdir(parents=True,exist_ok=True)
    if source.is_dir():
        shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    else:shutil.copy2(source,target)


# Real source/declared package inputs only. No Git, env, semantic state or real history. The
# engineering scenario pins its declared test files as validation inputs, so they are staged from
# that one declaration (tests/engine_mutation_http.py EngineeringHTTPScenario.test_paths).
_PACKAGE_INPUTS = ('src/laplace','src/atlas','profiles','tests/grammar_spec',
                   'tools/writing_verbs','scripts/laplace-python','scripts/laplace_python.py',
                   'runtime_profiles.toml','pyproject.toml','README.md','atlas/pyproject.toml','atlas/README.md',
                   'scripts/writing_eval_manifest.py','scripts/export_writing_evaluation.py',
                   'scripts/verify_writing_evaluation.py','docs/writing-evaluation-release.md',
                   'docs/writing-evaluator-readme.md','docs/writing-container.md','docs/writing-registry.md',
                   'docs/writing-engine-walkthrough.md','docs/writing-agent-start.md','deploy/writing')


def _staged_inputs():
    from engine_mutation_http import EngineeringHTTPScenario
    return _PACKAGE_INPUTS + tuple(EngineeringHTTPScenario.test_paths)


def _stage(root):
    root.mkdir();export_fixture(root)
    shutil.rmtree(root/'src')
    for relative in _staged_inputs():
        _copy(root,relative)
    # Fixture's external research placeholder must not enter this owned package closure.
    (root/'projects/first/text/references.json').write_text('{"sources":[]}')
    return root


def test_the_staged_closure_carries_every_pin_the_engineering_scenario_declares():
    """Setup proof without the installed loop: every source and test file the scenario pins as a
    validation input exists here and is inside the staged closure, so `_pin` cannot fail on a
    missing input after staging. Nothing is copied or started."""
    from engine_mutation_http import EngineeringHTTPScenario
    staged = _staged_inputs()
    declared = tuple(EngineeringHTTPScenario.source_paths) + tuple(EngineeringHTTPScenario.test_paths)
    inventory = {}
    for relative in declared:
        assert (ROOT / relative).is_file(), relative
        assert any(relative == entry or relative.startswith(entry.rstrip('/') + '/') for entry in staged), relative
        inventory[relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    assert len(inventory) == len(declared) == len(set(declared))
    assert len(staged) == len(set(staged))


def _env(root):
    env=dict(os.environ)
    for key in ['LAPLACE_CUSTODY_LIVE','LAPLACE_PYTHON','LAPLACE_WRITING_EXPECTED_SOURCE',
                'LAPLACE_RUNTIME_SCRATCH','LAPLACE_REQUIRE_GPU','LAPLACE_WRITING_EXPECTED_SELECTION','LAPLACE_WRITING_STATE']:
        env.pop(key,None)
    env.update(LAPLACE_REPO_ROOT=str(root),LAPLACE_STATE=str(root/'runtime-state'),
               LAPLACE_SESSION_WORKSPACES=str(root/'provider-workspaces'),
               LAPLACE_FALLBACK_LOG=str(root/'fallback.jsonl'))
    return env


def _run(root, *args, timeout=60):
    result=subprocess.run([str(root/'scripts/laplace-python'),*args],cwd=root,
        env=_env(root),capture_output=True,text=True,timeout=timeout)
    assert result.returncode==0,(result.stdout[-2000:],result.stderr[-2000:])
    return result.stdout


_OBSERVER = r'''
import json,sys,hashlib,marshal
from pathlib import Path
from laplace.web import authoring as c; from laplace.representation import atlas_bridge, custody_mode; from laplace.desktop import writing_app
root=Path(sys.argv[1]);store=c._writing_body_store(root)
print(json.dumps({'code':hashlib.sha256(marshal.dumps(atlas_bridge.BlobStore.put.__code__)).hexdigest(),
 'origin':sys.modules['atlas.store'].__file__,'source':writing_app.source_identity(root),'custody_off':custody_mode.is_off(root)}),flush=True)
for line in sys.stdin:
 if line.strip()=='quit':break
 text='public loop witness '*1500;raw=c._public_body_bytes(text)
 key=store.put(raw) if not store.key_path('sha256:'+hashlib.sha256(raw).hexdigest()).exists() else 'sha256:'+hashlib.sha256(raw).hexdigest()
 store.key_path(key).write_bytes(b'isolated corrupt evidence')
 result=c._prepare_custody_row(root,{'record':'writing-artifact','after':text})
 try:store.get(key);get_refused=False
 except Exception as error:get_refused=getattr(error,'reason','')=='store-blob-hash-mismatch'
 healthy=store.put(b'healthy dedup control');stat=store.key_path(healthy).stat();again=store.put(b'healthy dedup control')
 print(json.dumps({'inline':result['after']==text,'diagnostic':result.get('custody_degradation'),
  'get_corrupt_refusal':get_refused,'healthy_duplicate_no_rewrite':again==healthy and store.key_path(healthy).stat().st_mtime_ns==stat.st_mtime_ns,
  'corruption_preserved':store.key_path(key).read_bytes()==b'isolated corrupt evidence'}),flush=True)
'''


def _observer(root):
    p=subprocess.Popen([str(root/'scripts/laplace-python'),'-c',_OBSERVER,str(root)],
        cwd=root,env=_env(root),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    first=json.loads(p.stdout.readline())
    assert first['custody_off'] is True
    assert Path(first['origin']).is_relative_to(root/'src/atlas')
    return p,first


def _observe(p):
    p.stdin.write('probe\n');p.stdin.flush()
    return json.loads(p.stdout.readline())


def _close(p):
    if p is None:return
    p.stdin.write('quit\n');p.stdin.flush();p.wait(timeout=5)
    assert p.returncode==0,p.stderr.read()


def _module(root, name):
    spec=importlib.util.spec_from_file_location(name,root/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_normal_source_process_generation_export_and_installed_loop(tmp_path,monkeypatch,tmp_path_factory):
    if os.environ.get("LAPLACE_RETAIN_MUTATION_STAGE") == "1":
        # Explicit root-owned acceptance fixture: preserve this one stage for the
        # subsequent real pilot, with no source relocation or second source tree.
        tmp_path=tmp_path_factory.mktemp("engine-mutation-retained")
    costs={};start=time.perf_counter();root=_stage(tmp_path/'source')
    monkeypatch.setenv('LAPLACE_REPO_ROOT',str(root))
    costs['source_stage_seconds']=time.perf_counter()-start
    costs['source_stage_bytes']=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    source=root/'src/atlas/store.py';candidate=source.read_bytes()
    baseline=subprocess.check_output(['git','show',f'{BASE}:atlas/src/atlas/store.py'],cwd=ROOT)
    source.write_bytes(baseline)
    receipt=tmp_path/'managed.json'
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    def service(action):
        return json.loads(_run(root,'-m','laplace.desktop.writing_app','--repo-root',str(root),
            '--state',str(receipt),'--host','127.0.0.1','--port',str(port),action))
    observer=None;fresh=None
    def request(method,path,payload=None):
        raw=json.dumps(payload).encode() if payload is not None else None
        req=Request(f'http://127.0.0.1:{port}'+path,data=raw,method=method,
            headers={'Content-Type':'application/json','X-Laplace-Writing':'1'})
        try:
            with urlopen(req,timeout=15) as response:return response.status,json.load(response)
        except HTTPError as error:return error.code,json.load(error)
    def run(code):return json.loads(_run(root,'-c',code))
    scenario=None
    try:
        observer,old=_observer(root);base_effect=_observe(observer)
        assert base_effect['inline'] is False and base_effect['diagnostic'] is None
        start=time.perf_counter();first=service('--no-open');costs['start_seconds']=time.perf_counter()-start
        assert first['health']['source_start']['loaded_code_asserted'] is False
        assert first['record']['source_start']==first['health']['source_start']
        assert first['source_identity']==old['source']
        pid=first['record']['pid']
        costs['selection_controls']=_selection_controls(root,run,receipt,port)
        pid=costs['selection_controls']['pid_preserved']
        base_http=_http_apply_witness(root,request,run,'base')
        base_observation={**base_effect,**base_http,'selected_symbol':old,'source_start':first['health']['source_start'],
            'checks':[{'name':'healthy_duplicate_no_rewrite','passed':base_effect['healthy_duplicate_no_rewrite']},
                      {'name':'get_corrupt_refusal','passed':base_effect['get_corrupt_refusal']},
                      {'name':'known_existing_put_hole_observed','passed':not base_http['inline']}]}
        helper=ROOT/'tests/engine_mutation_http.py'
        if helper.exists():
            from engine_mutation_http import EngineeringHTTPScenario
            scenario=EngineeringHTTPScenario(root,request,run)
            scenario.baseline(base_observation)
        costs['baseline_http']=base_http
        start=time.perf_counter()
        for _ in range(3):assert service('--status')['status']=='running'
        costs['warm_status_3_seconds']=time.perf_counter()-start
        # Neither generator recipe nor unrelated synthetic history is a runtime input.
        generator=root/'tools/writing_verbs/gen_routes.py'
        generated=root/'src/laplace/native/verbs.py';generated_before=generated.read_bytes()
        _run(root,'tools/writing_verbs/gen_routes.py','--tree',str(root))
        generated_before=generated.read_bytes()
        generator_before=generator.read_bytes();generator.write_bytes(generator_before+b'\n# recipe-only control\n')
        _run(root,'tools/writing_verbs/gen_routes.py','--tree',str(root),'--check')
        assert generated.read_bytes()==generated_before
        assert hashlib.sha256(generator.read_bytes()).hexdigest()!=hashlib.sha256(generator_before).hexdigest()
        # Route regeneration may first change dispatch line pins for this branch.
        # Establish it before the source mutation and do one explicit owner update.
        if service('--status')['status']!='running':first=service('--update');pid=first['record']['pid']
        with (root/'contract/talk.jsonl').open('a') as f:f.write(json.dumps({'record':'unscoped','id':'CONTROL','project':'unrelated','text':'unrelated'})+'\n')
        assert service('--status')['status']=='running'
        exporter=_module(root,'export_writing_evaluation');verifier=_module(root,'verify_writing_evaluation')
        start=time.perf_counter();exporter.export_projects(root,tmp_path/'export-base',['first'])
        costs['export_base_seconds']=time.perf_counter()-start
        costs['export_base_bytes']=sum(p.stat().st_size for p in (tmp_path/'export-base').rglob('*') if p.is_file())
        verified=verifier.verify(tmp_path/'export-base');assert verified['ok'],verified.get('failures',verified)
        source.write_bytes(candidate)
        if scenario is not None:scenario.source_changed()
        state=service('--status');assert state['status']=='stale-source'
        assert state['record']['pid']==pid
        assert service('--reconnect')['disposition']=='reused-current-runtime'
        assert _observe(observer)['inline'] is False  # old loaded method, changed disk
        # Bad Atlas code cannot retire the exact healthy process.
        source.write_bytes(candidate+b'\nif :\n')
        invalid=service('--update');assert invalid['disposition']=='update-unavailable'
        assert invalid['record']['pid']==pid
        source.write_bytes(candidate)
        start=time.perf_counter();second=service('--update');costs['update_seconds']=time.perf_counter()-start
        assert second['record']['pid']!=pid and service('--status')['status']=='running'
        fresh,new=_observer(root);changed=_observe(fresh)
        assert changed['inline'] is True and changed['diagnostic']['status']=='INLINE_RETAINED'
        assert old['code']!=new['code'] and changed['corruption_preserved'] is True
        def observe_candidate():
            candidate_http=_http_apply_witness(root,request,run,'candidate')
            costs['candidate_http']=candidate_http
            return {**changed,**candidate_http,'selected_symbol':new,'source_start':second['health']['source_start'],
                'checks':[{'name':'valid_duplicate_no_rewrite','passed':changed['healthy_duplicate_no_rewrite']},
                          {'name':'get_corrupt_refusal','passed':changed['get_corrupt_refusal']},
                          {'name':'actual_http_corrupt_duplicate_inline','passed':candidate_http['inline']},
                          {'name':'actual_http_source_postimage','passed':candidate_http['source_postimage']}]}
        if scenario is not None:
            scenario.candidate(observe_candidate)
            costs['engineering_http']=scenario.summary()
        else:observe_candidate()
        exported=tmp_path/'export-base';exported_source=exported/'src/atlas/store.py'
        exported_source.write_bytes(candidate)
        assert any(row.get('path')=='src/atlas/store.py' for row in verifier.verify(exported)['failures'])
        start=time.perf_counter();exporter.export_projects(root,tmp_path/'export-candidate',['first'])
        costs['export_candidate_seconds']=time.perf_counter()-start
        costs['export_candidate_bytes']=sum(p.stat().st_size for p in (tmp_path/'export-candidate').rglob('*') if p.is_file())
        assert verifier.verify(tmp_path/'export-candidate')['ok']
        assert not (tmp_path/'export-candidate/scripts/laplace-python').exists()
        # Build/install from exported source, without dependencies/network or a second runtime env.
        prefix=tmp_path/'installed';start=time.perf_counter()
        install=subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps',
            '--no-build-isolation','--no-cache-dir','--target',str(prefix),str(tmp_path/'export-candidate/atlas'),
            str(tmp_path/'export-candidate')],cwd=tmp_path,env=_env(root),capture_output=True,text=True,timeout=90)
        assert install.returncode==0,install.stderr[-2000:]
        costs['install_seconds']=time.perf_counter()-start
        code='import sys;sys.path.insert(0,sys.argv.pop(1));from laplace.web.writing_server import configure;configure(sys.argv[1]);'+_OBSERVER
        installed=subprocess.Popen([sys.executable,'-I','-B','-c',code,str(prefix),str(tmp_path/'export-candidate')],
            cwd=tmp_path,env=_env(tmp_path/'export-candidate'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True)
        try:
            installed_first=json.loads(installed.stdout.readline())
            assert Path(installed_first['origin']).is_relative_to(prefix)
            assert _observe(installed)['inline'] is True
        finally:_close(installed)
        costs['installed_bytes']=sum(p.stat().st_size for p in prefix.rglob('*') if p.is_file())
        costs.update(base_corrupt_existing='UNSAFE_HANDLE',candidate_corrupt_existing='INLINE_RETAINED',
            loaded_symbol_old=old['code'],loaded_symbol_new=new['code'],
            covered_source_files=second['health']['source_start']['files'],
            covered_source_hash_bytes=second['health']['source_start']['bytes'],
            production_hook='none; observer is separate harness process',fixture_history='synthetic only')
    finally:
        _close(observer);_close(fresh)
        if receipt.exists():service('--stop')
        with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',port))!=0
    costs['owned_processes_cleaned']=True
    if os.environ.get('LAPLACE_RETAIN_MUTATION_STAGE')=='1':
        costs['retained_stage']={'root':str(root),'receipt':str(receipt),'runtime_state':str(root/'runtime-state'),
            'session_workspaces':str(root/'provider-workspaces'),'bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file())}
        for name in ('export-base','export-candidate','installed'):
            owned=tmp_path/name
            if owned.exists():shutil.rmtree(owned)
        costs['obsolete_exports_and_install_cleaned']=True
    print('RUNTIME_LOOP_COST '+json.dumps(costs,sort_keys=True))


def _generator_module():
    spec=importlib.util.spec_from_file_location('custody_routes_generator',ROOT/'tools/writing_verbs/gen_routes.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_selector_default_anchor_survives_shift_and_refuses_nearby_match(tmp_path,monkeypatch):
    generator=_generator_module()
    monkeypatch.setattr(generator,'DEFAULTS',{('pipeline','view'):('summary','src/laplace/writing_tools.py:999','spelled')})
    path=tmp_path/'src/laplace/native/tools.py';path.parent.mkdir(parents=True)
    body="def _execute(operation,payload):\n    if operation == 'pipeline':\n        view = payload.get('view') or 'summary'\n    if operation == 'unrelated':\n        view = payload.get('view') or 'summary'\n"
    path.write_text(body)
    assert generator.check_defaults(tmp_path)[('pipeline','view')][1].endswith(':3')
    path.write_text('\n# harmless insertion\n'+body)
    assert generator.check_defaults(tmp_path)[('pipeline','view')][1].endswith(':5')
    path.write_text(body.replace("or 'summary'","or 'changed'",1))
    with pytest.raises(AssertionError,match='missing/ambiguous or changed'):generator.check_defaults(tmp_path)
    path.write_text(body.replace("view = payload.get('view') or 'summary'", "view = payload.get('view') or 'summary'\n        again = payload.get('view') or 'summary'",1))
    with pytest.raises(AssertionError,match='missing/ambiguous or changed'):generator.check_defaults(tmp_path)


def test_selector_else_default_uses_only_exact_routes_entry(tmp_path,monkeypatch):
    generator=_generator_module()
    monkeypatch.setattr(generator,'DEFAULTS',{('research','view'):('summary','src/laplace/writing_tools.py:999','else-branch:result')})
    monkeypatch.setattr(generator,'_DEFAULT_FUNCTIONS',{})   # this test is the routes-table rule; the live research default is an owner function (R1)
    path=tmp_path/'src/laplace/native/tools.py';path.parent.mkdir(parents=True)
    body="def _execute(operation,payload):\n    routes={'research': ('owner','yes' if payload.get('view')=='result' else 'no','GET'),\n            'other':('owner','yes' if payload.get('view')=='result' else 'no','GET')}\n"
    path.write_text(body)
    assert generator.check_defaults(tmp_path)[('research','view')][1].endswith(':2')
    path.write_text(body.replace("payload.get('view')=='result'","payload.get('view')=='changed'",1))
    with pytest.raises(AssertionError,match='missing/ambiguous or changed'):generator.check_defaults(tmp_path)


def test_http_anchor_is_scoped_unique_and_shift_safe(tmp_path):
    generator=_generator_module()
    row={'name':'authoring/build','route':'/authoring/build','method':'GET',
         'site':'src/laplace/authoring_surface.py:999','holds':'"/authoring/build"'}
    path=tmp_path/'src/laplace/web/authoring.py';path.parent.mkdir(parents=True)
    body='def nearby():\n    if method == "GET" and path == "/authoring/build": pass\ndef handle(path,method):\n    if method == "POST" and path == "/authoring/build": pass\n    if method == "GET" and path == "/authoring/build": pass\n'
    path.write_text(body)
    assert generator.resolve_site(tmp_path,row).endswith(':5')
    path.write_text('# shifted\n'+body)
    assert generator.resolve_site(tmp_path,row).endswith(':6')
    left,right=body.rsplit('"/authoring/build"',1)
    path.write_text(left+'"/unrelated"'+right)
    with pytest.raises(AssertionError,match='missing/ambiguous'):generator.resolve_site(tmp_path,row)
    path.write_text(body+'    if method == "GET" and path == "/authoring/build": pass\n')
    with pytest.raises(AssertionError,match='missing/ambiguous'):generator.resolve_site(tmp_path,row)


def test_http_prefix_guard_must_be_inside_actual_post_prefix_scope(tmp_path):
    generator=_generator_module()
    row={'name':'http-door','route':'*','method':'POST','site':'src/laplace/scanner.py:999','holds':'X-Laplace-Writing'}
    path=tmp_path/'src/laplace/web/scanner.py';path.parent.mkdir(parents=True)
    outside='def make_handler():\n    class Handler:\n        def do_POST(self):\n            if self.headers.get("X-Laplace-Writing") != "1": pass\n'
    path.write_text(outside)
    with pytest.raises(AssertionError,match='missing/ambiguous'):generator.resolve_site(tmp_path,row)
    inside=outside.replace('            if self.headers', '            if u.path.startswith(("/authoring/", "/work/")):\n                if self.headers')
    path.write_text(inside)
    assert generator.resolve_site(tmp_path,row).endswith(':5')
    path.write_text(inside+'                if self.headers.get("X-Laplace-Writing") != "1": pass\n')
    with pytest.raises(AssertionError,match='missing/ambiguous'):generator.resolve_site(tmp_path,row)


@pytest.mark.parametrize('selected',['present','missing','broken','namespace'])
def test_bridge_honors_selection_or_true_unavailability(tmp_path, selected):
    """One source home (core consolidation R2): src holds laplace AND atlas, and the bridge adds no path of its own.

    present    the source tree on the path selects atlas from src/atlas.
    missing    a tree carrying laplace only: atlas is truly unavailable and the bridge refuses (ModuleNotFoundError);
               no sibling checkout is consulted.
    broken     a selected atlas whose import raises is reported as broken, never masked by another tree.
    namespace  a namespace-only selected atlas with no regular atlas anywhere: refused, not masked."""
    import yaml
    # A fresh no-site interpreter has precisely this existing dependency available,
    # rather than inheriting installed Atlas or cloning a runtime environment.
    deps=tmp_path/'deps';deps.mkdir();(deps/'yaml').symlink_to(Path(yaml.__file__).parent,target_is_directory=True)
    explicit=tmp_path/'selected';explicit.mkdir()
    if selected=='broken':
        (explicit/'atlas').mkdir();(explicit/'atlas/__init__.py').write_text('raise RuntimeError("selected Atlas is broken")')
    elif selected=='namespace':(explicit/'atlas').mkdir()
    # the source tree: the real one (laplace and atlas) or a laplace-only shadow of it
    if selected=='present':source=ROOT/'src'
    else:
        source=tmp_path/'laplace-only';source.mkdir();(source/'laplace').symlink_to(ROOT/'src/laplace',target_is_directory=True)
    env=_env(tmp_path);env['LAPLACE_REPO_ROOT']=str(tmp_path/'no-sibling')   # a checkout root with no atlas anywhere under it
    code=r'''
import sys,json,importlib.util
sys.path[:0]=sys.argv[1:]
before=importlib.util.find_spec('atlas')
try:
 from laplace.representation import atlas_bridge
 import atlas
 result={'ok':True,'origin':atlas.__file__,'before_available':before is not None,'paths':list(sys.path)}
except Exception as error:
 result={'ok':False,'error':type(error).__name__,'message':str(error),'before_available':before is not None,'paths':list(sys.path)}
print(json.dumps(result))
'''
    r=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(explicit),str(source),str(deps)],
        cwd=tmp_path,env=env,capture_output=True,text=True,timeout=15)
    assert r.returncode==0,r.stderr
    result=json.loads(r.stdout)
    assert not any(p.endswith('atlas/src') for p in result['paths']),'the bridge inserted a sibling tree'
    if selected=='present':
        assert result['ok'] and result['before_available']
        assert Path(result['origin']).is_relative_to(ROOT/'src/atlas')
    else:
        assert not result['ok']
        assert result['before_available']==(selected in {'broken','namespace'})
        if selected=='broken':assert 'selected Atlas is broken' in result['message']
        else:assert result['error']=='ModuleNotFoundError'


def test_full_owner_fallback_repetition_and_read_receipt_growth(tmp_path):
    _import_project(tmp_path,editable=False)
    text='public repetition '*1500;raw=core_bodies.encode(text)
    store=bodies.store(tmp_path);key=store.put(raw)
    store.key_path(key).write_bytes(b'corrupt fixture only')
    ledger=tmp_path/'contract/talk.jsonl'
    initial=ledger.stat().st_size if ledger.exists() else 0
    start=time.perf_counter();result=None;before=None
    for _ in range(3):
        result=writing_tools.execute(tmp_path,'fixture','work','store_artifact',
            {'path':'research/repeated.md','before':before,'content':text,'reason':'Owned custody fixture'},turn_id='WT-repeat')
        assert result['custody_degradation']['status']=='INLINE_RETAINED'
        before=text
    writes_seconds=time.perf_counter()-start;after_write=ledger.stat().st_size
    start=time.perf_counter();delivered=0
    for _ in range(3):
        read=writing_tools.execute(tmp_path,'fixture','work','read_artifact',{'id':result['id']},turn_id='WT-repeat')
        delivered+=len(json.dumps(read,ensure_ascii=False).encode())
    reads_seconds=time.perf_counter()-start;after_read=ledger.stat().st_size
    assert after_read-after_write < 6000  # provenance rows, never replayed body copies
    assert store.key_path(key).read_bytes()==b'corrupt fixture only'
    observations={'write_repeats':3,'write_seconds':writes_seconds,'read_repeats':3,
        'read_seconds':reads_seconds,'body_bytes':len(raw),'write_retained_growth_bytes':after_write-initial,
        'read_receipt_growth_bytes':after_read-after_write,'delivered_read_bytes':delivered,
        'corrupt_evidence_preserved':True,'diagnostic_bytes':len(json.dumps(result['custody_degradation']).encode())}
    print('OWNER_CUSTODY_COST '+json.dumps(observations,sort_keys=True))


def test_real_application_returns_its_saved_inline_degradation(tmp_path):
    from test_writing_controller import _seed_revision,_apply_fixture
    _,source=_import_project(tmp_path)
    after='Applied public prose. '*1000
    turn_id=_seed_revision(tmp_path,'fixture',[{'file':'main.tex','line_start':3,'line_end':3,
        'before':'Original prose.','after':after}],selection={'files':['main.tex']},suffix='runtime-apply')
    turn=session_reads._records(tmp_path)['turns'][turn_id]
    edits=turn['reply']['proposal']['edits']
    store=bodies.store(tmp_path);key=store.put(core_bodies.encode(edits))
    store.key_path(key).write_bytes(b'isolated corrupted application edits')
    result=_apply_fixture(tmp_path,{'turn_id':turn_id})
    assert result['complete'] is True,result
    assert result['custody_degradation']['status']=='INLINE_RETAINED'
    assert result['custody_degradation']['identities'][0]['content_handle']==key
    assert after in (tmp_path/source['manuscript_dir']/'main.tex').read_text()
    stored=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines() if 'writing-application' in line][-1]
    assert isinstance(stored['edits'],list) and stored['edits'][0]['after']==after


_HTTP_SEED = r'''
import sys,json,hashlib
from pathlib import Path
sys.path.insert(2,str(Path.cwd()/'tests'))
from test_writing_controller import _import_project,_seed_revision
from laplace.web import authoring as c; from laplace.manuscript import proposal_preflight, manuscript_proposals
root=Path.cwd();phase=sys.argv[1];project='http-custody-candidate' if phase.startswith('renewed-') else 'http-custody-'+phase
if phase.startswith('renewed-'):
 from laplace.manuscript import manuscript_source
 source=manuscript_source.resolve(project,repo_root=root)
 before=(root/source['manuscript_dir']/'main.tex').read_text().splitlines()[2]
 after=('Actual renewed daemon revision '+phase+'. ')*700
else:
 _,source=_import_project(root,project)
 before='Original prose.'
 after='Actual daemon public revision. '*1000
turn_id=_seed_revision(root,project,[{'file':'main.tex','line_start':3,'line_end':3,
 'before':before,'after':after}],selection={'files':['main.tex']},suffix='http-'+phase)
turn=c._records(root)['turns'][turn_id];proposal=turn['reply']['proposal']
checked=proposal_preflight.preflight(root,project,turn,proposal)
assert checked['valid'],checked['errors']
# The exact saved candidate carries the same normalized source edit and guard.
assert checked['proposal']['edits']==proposal['edits']
raw=c._public_body_bytes(proposal['edits']);store=c._writing_body_store(root)
key='sha256:'+hashlib.sha256(raw).hexdigest()
if not store.key_path(key).exists():assert store.put(raw)==key
store.key_path(key).write_bytes(b'corrupt daemon application fixture')
version=manuscript_proposals.proposal_version(turn)[0]
print(json.dumps({'project':project,'turn_id':turn_id,'proposal_version':version,'cas_key':key,
 'source_path':source['manuscript_dir']+'/main.tex','after_sha256':hashlib.sha256(after.encode()).hexdigest(),
 'preflight_valid':checked['valid'],'edits_bytes':len(raw)}))
'''


def _http_apply_witness(root,request,run,phase):
    seeded=json.loads(_run(root,'-c',_HTTP_SEED,phase))
    start=time.perf_counter()
    status,result=request('POST','/authoring/apply',{'project':seeded['project'],
        'turn_id':seeded['turn_id'],'proposal_version':seeded['proposal_version']})
    assert status==200 and result.get('complete') is True,(status,result)
    elapsed=time.perf_counter()-start
    status,session=request('GET','/authoring/session?id=WS-http-'+phase+'&view=summary')
    assert status==200,(status,session)
    rows=[json.loads(line) for line in (root/'contract/talk.jsonl').read_text().splitlines()]
    stored=next(row for row in reversed(rows) if row.get('id')==result['id'])
    path=root/seeded['source_path'];postimage=path.read_text().splitlines()[2]
    key=seeded['cas_key'].removeprefix('sha256:')
    retained=root/'contract/writing_bodies'/key[:2]/key
    observed={'inline':isinstance(stored['edits'],list),'diagnostic':result.get('custody_degradation'),
        'corruption_preserved':retained.read_bytes()==b'corrupt daemon application fixture',
        'source_postimage':hashlib.sha256(postimage.encode()).hexdigest()==seeded['after_sha256'],
        'preflight_valid':seeded['preflight_valid'],'application_id':result['id'],
        'http_status':status,'seconds':elapsed,'edits_bytes':seeded['edits_bytes'],
        'http_delivered_bytes':len(json.dumps(result,ensure_ascii=False).encode()),
        'history_storage_error_count':sum(len(turn.get('storage_errors') or []) for turn in session['turns']),
        'result_sha256':'sha256:'+hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    assert observed['source_postimage'] and observed['corruption_preserved']
    if phase=='base':
        assert not observed['inline'] and observed['diagnostic'] is None
        assert observed['history_storage_error_count']>0
    else:
        assert observed['inline'] and observed['diagnostic']['status']=='INLINE_RETAINED'
        assert observed['history_storage_error_count']==0
    return observed


_SELECTION_CONTROLS = r'''
import json,os
from pathlib import Path
from laplace.desktop import writing_app as a
from laplace.core import runtime as p
root=Path.cwd();receipt=Path(%(receipt)r);port=%(port)d
base=a.status(root=root,state=receipt,port=port);pid=base['record']['pid']
profile=root/'runtime_profiles.toml';original=profile.read_text()
recipe=root/'scripts/laplace-python';recipe_bytes=recipe.read_bytes()
source=root/'src/laplace/__init__.py';source_bytes=source.read_bytes()
atlas=root/'src/atlas/__init__.py';atlas_bytes=atlas.read_bytes()
override=os.environ.get('LAPLACE_PYTHON')
checks=[];probe_observations=[]
actual_probe=a._validate_managed_runtime
def counted_probe(*args,**kwargs):
 observed=actual_probe(*args,**kwargs);probe_observations.append({'recipe_bytes':observed['recipe_bytes']});return observed
a._validate_managed_runtime=counted_probe
def status():return a.status(root=root,state=receipt,port=port)
def preserve(name):
 result=a.ensure_server(root=root,state=receipt,port=port)
 assert result.get('disposition')=='update-unavailable',result
 assert a.health(port=port)['pid']==pid
 checks.append({'name':name,'passed':True})
try:
 first=p.selection_basis(root)['identity'];profile.write_text(original+'\n# semantic-only formatting control\n')
 assert p.selection_basis(root)['identity']==first and status()['status']=='running'
 checks.append({'name':'profile_format_semantically_unchanged','passed':True});profile.write_text(original)
 recipe.write_bytes(recipe_bytes+b'\n# changed launch recipe\n')
 assert status()['runtime_selection_changed']
 assert a.ensure_server(root=root,state=receipt,port=port,allow_update=False)['record']['pid']==pid
 checks.append({'name':'launcher_recipe_change_observed_without_passive_restart','passed':True});recipe.write_bytes(recipe_bytes)
 alternate=root/'alternate-python';alternate.symlink_to(p.lifecycle_python(root))
 os.environ['LAPLACE_PYTHON']=str(alternate)
 assert status()['runtime_selection_changed']
 assert a.ensure_server(root=root,state=receipt,port=port,allow_update=False)['record']['pid']==pid
 checks.append({'name':'explicit_interpreter_override_observed','passed':True})
 probe_before=len(probe_observations)
 selected=a.ensure_server(root=root,state=receipt,port=port)
 assert len(probe_observations)-probe_before==1
 assert selected.get('started') and selected['record']['pid']!=pid,selected
 assert selected['record']['runtime_selection_start']['selected']==str(alternate)
 assert selected['health']['runtime_start']['executable']==str(alternate.resolve())
 pid=selected['record']['pid']
 checks.append({'name':'explicit_override_actual_managed_launch','passed':True})
 broken=root/'wrong-runtime';broken.write_text('#!/bin/sh\nexit 17\n');broken.chmod(0o755)
 os.environ['LAPLACE_PYTHON']=str(broken);preserve('executable_wrong_runtime_preserves_owned_daemon')
 os.environ.pop('LAPLACE_PYTHON',None)
 profile.write_text(original.replace('python = "'+p.runtime_profile(root)['python']+'"','python = "'+str(root/'missing-python')+'"',1))
 preserve('missing_selected_runtime_preserves_owned_daemon')
 profile.write_text('not valid toml [');preserve('invalid_policy_preserves_owned_daemon')
 profile.unlink();preserve('missing_policy_preserves_owned_daemon')
 profile.write_text(original)
 if override is None:os.environ.pop('LAPLACE_PYTHON',None)
 else:os.environ['LAPLACE_PYTHON']=override
 source.write_bytes(source_bytes+b'\nimport missing_engine_runtime_fixture_import\n')
 preserve('actual_required_import_failure_preserves_owned_daemon')
 source.write_bytes(source_bytes)
 atlas.write_bytes(atlas_bytes+b'\nraise RuntimeError("fixture selected Atlas incompatible")\n')
 preserve('explicit_required_atlas_import_failure_preserves_owned_daemon')
finally:
 profile.write_text(original);recipe.write_bytes(recipe_bytes);source.write_bytes(source_bytes);atlas.write_bytes(atlas_bytes)
 if override is None:os.environ.pop('LAPLACE_PYTHON',None)
 else:os.environ['LAPLACE_PYTHON']=override
restored=a.ensure_server(root=root,state=receipt,port=port)
if restored.get('started'):pid=restored['record']['pid']
assert status()['status']=='running' and status()['record']['pid']==pid
print(json.dumps({'checks':checks,'pid_preserved':pid,'restored_current':True,
 'selection_start':status()['record']['runtime_selection_start'],'actual_runtime':status()['health']['runtime_start'],
 'validation_probe_calls':status()['record']['runtime_selection_expected']['validation_probe_calls'],
 'actual_successful_probe_count':len(probe_observations),'probe_recipe_bytes':sum(x['recipe_bytes'] for x in probe_observations)}))
'''


def _selection_controls(root,run,receipt,port):
    return run(_SELECTION_CONTROLS % {'receipt':str(receipt),'port':port})


def test_portable_settings_observe_without_profile_or_toml_parser(tmp_path,monkeypatch):
    import builtins
    from laplace.projects import library as writing_projects
    from laplace.core import runtime as runtime_policy
    original=builtins.__import__
    def without_toml(name,*args,**kwargs):
        if name=='tomllib':raise ModuleNotFoundError('simulated Python without tomllib')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',without_toml)
    observed=writing_projects.app_settings(tmp_path,view='runtime')
    assert observed['configured']=={} and observed['revision'] is None
    assert observed['observed']['version']
    assert observed['diagnostic']=='No runtime declaration exists in this workspace'
    (tmp_path/'runtime_profiles.toml').write_text('[lifecycle]\npython="unused"\nexpected_python="unused"\n')
    declared=runtime_policy.configuration(tmp_path)
    assert declared['declared']=={} and declared['revision']
    assert 'parser unavailable' in declared['diagnostic']
    observed=writing_projects.app_settings(tmp_path,view='runtime')
    assert observed['configured']=={} and 'parser unavailable' in observed['diagnostic']


def exercise_managed_asset_preservation(root: Path, receipt: Path, port: int) -> dict:
    """On an explicitly supplied existing stage, hold the exact daemon on bad JS.

    The caller owns staging/revalidation. No new source tree, endpoint, server or
    parser is created here; production capture validates the reachable closure.
    """
    root=Path(root);receipt=Path(receipt)
    original_receipt=receipt.read_bytes();record=json.loads(original_receipt)
    assert writing_app._start_tick(record['pid'])==record['start_tick']
    health_url=f'http://127.0.0.1:{port}/authoring/health'
    asset_url=f'http://127.0.0.1:{port}/shared/writing-artifact.mjs'
    with urlopen(health_url,timeout=5) as response:health=json.load(response)
    assert health['pid']==record['pid']
    with urlopen(asset_url,timeout=5) as response:captured=response.read()
    path=root/'src/laplace/web/static_shared/writing-artifact.mjs';original=path.read_bytes()
    assert b"./engineering-support.mjs" in original
    changed=original.replace(b"./engineering-support.mjs",b"./missing-engine-custody-asset.mjs",1)
    start=time.perf_counter()
    try:
        path.write_bytes(changed)
        refused=json.loads(_run(root,'-m','laplace.desktop.writing_app','--repo-root',str(root),
            '--state',str(receipt),'--host','127.0.0.1','--port',str(port),'--update'))
        assert refused['disposition']=='update-unavailable' and not refused['started'],refused
        assert receipt.read_bytes()==original_receipt
        with urlopen(health_url,timeout=5) as response:after=json.load(response)
        assert after['pid']==record['pid']
        with urlopen(asset_url,timeout=5) as response:still_captured=response.read()
        assert captured==still_captured
    finally:path.write_bytes(original)
    return {'check':'broken_reachable_asset_preserves_exact_owned_daemon','passed':True,
        'pid':record['pid'],'start_tick':record['start_tick'],'receipt_unchanged':True,
        'captured_asset_sha256':'sha256:'+hashlib.sha256(captured).hexdigest(),
        'captured_asset_bytes':len(captured),'source_restored_sha256':'sha256:'+hashlib.sha256(original).hexdigest(),
        'seconds':time.perf_counter()-start,'disposition':refused['disposition']}


def reobserve_existing_custody_runtime_stage(root: Path, receipt: Path, port: int) -> dict:
    """Renew the necessary candidate observation in one explicitly retained stage.

    Root owns staging/restart and the helper's existing Work/adoption semantics.
    This retains historical C1 and appends only compact new evidence; it never
    recreates the project, baseline, environment, source tree or exported package.
    """
    from engine_mutation_http import EngineeringHTTPScenario
    root=Path(root);receipt=Path(receipt)
    def request(method,path,payload=None):
        raw=json.dumps(payload).encode() if payload is not None else None
        req=Request(f'http://127.0.0.1:{port}'+path,data=raw,method=method,
                    headers={'Content-Type':'application/json','X-Laplace-Writing':'1'})
        try:
            with urlopen(req,timeout=15) as response:return response.status,json.load(response)
        except HTTPError as error:return error.code,json.load(error)
    def run(code):return json.loads(_run(root,'-c',code))
    asset=exercise_managed_asset_preservation(root,receipt,port)
    scenario=EngineeringHTTPScenario(root,request,run)
    def observe():
        phase='renewed-'+str(time.time_ns())
        observed=_http_apply_witness(root,request,run,phase)
        probe=None
        try:
            probe,symbol=_observer(root);put=_observe(probe)
            assert put['inline'] and put['diagnostic']['status']=='INLINE_RETAINED'
        finally:_close(probe)
        status,health=request('GET','/authoring/health');assert status==200
        return {**put,**observed,'selected_symbol':symbol,'source_start':health['source_start'],
            'checks':[{'name':'candidate_actual_http_guarded_source_rewrite','passed':observed['source_postimage']},
                      {'name':'candidate_actual_http_exact_inline_recovery','passed':observed['inline']},
                      {'name':'existing_corruption_preserved','passed':observed['corruption_preserved']},
                      {'name':'valid_duplicate_no_rewrite','passed':put['healthy_duplicate_no_rewrite']},
                      {'name':'named_get_corrupt_refusal','passed':put['get_corrupt_refusal']},
                      {'name':'pre_retirement_reachable_asset_refusal','passed':asset['passed']}]}
    scenario.revalidate_existing(observe)
    return {'asset_control':asset,'engineering_http':scenario.summary(),'extra_source_stages':0,
            'baseline_repeated':False,'provider_calls':0,'old_history_preserved':True}
