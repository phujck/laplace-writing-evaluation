"""The optional package boundary, tested in fresh source/installed interpreters.

These controls exercise real ordinary imports, public grading/front adapters,
preserved implementations and source observations. They do not certify a whole
FrontDoor/GPU run, the persisted tree or historical scientific results.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"   # laplace and atlas share the one source home (R2)
COSTS = {}


def probe(code, package=SOURCE, *, input_text=None):
    prefix = "import sys;sys.path.insert(0,sys.argv[1]);\n"
    result = subprocess.run([sys.executable, "-I", "-B", "-c", prefix + code, str(package)],
        input=input_text, capture_output=True, text=True, cwd=package.parent, timeout=30)
    assert result.returncode == 0, result.stderr[-4000:]
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    scratch = tmp_path_factory.mktemp("atlas-installed")
    prefix = scratch / "prefix"
    generated = [ROOT / "atlas/build", ROOT / "src/atlas.egg-info"]
    existing = {path: path.exists() for path in generated}
    started = time.perf_counter()
    result = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
        "--no-index", "--no-deps", "--no-build-isolation", "--no-cache-dir",
        "--target", str(prefix), str(ROOT / "atlas")], capture_output=True, text=True,
        timeout=90)
    assert result.returncode == 0, result.stderr[-4000:]
    COSTS["install_seconds"] = time.perf_counter() - started
    COSTS["installed_bytes"] = sum(p.stat().st_size for p in prefix.rglob("*") if p.is_file())
    try:
        yield prefix
    finally:
        COSTS["owned_scratch_bytes"] = sum(p.stat().st_size for p in scratch.rglob("*") if p.is_file())
        shutil.rmtree(scratch)
        removed = []
        for path in generated:
            if not existing[path] and path.exists():
                removed.append({"path": str(path), "bytes": sum(
                    p.stat().st_size for p in path.rglob("*") if p.is_file())})
                shutil.rmtree(path)
        COSTS["source_build_outputs_cleaned"] = removed
        COSTS["installed_prefix_cleaned"] = not scratch.exists()
        print("ATLAS_PACKAGE_COST " + json.dumps(COSTS, sort_keys=True))


def test_original_function_and_class_asts_are_preserved():
    from atlas.reconstruction._provenance import MODULES
    assert len(MODULES) == 14
    total = 0
    for name, record in MODULES.items():
        tree = ast.parse((SOURCE / "atlas/reconstruction" / (name + ".py")).read_text())
        actual = {node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                  for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        assert actual == record["function_class_ast"], name
        algorithm = ast.Module(body=[n for n in tree.body
            if not isinstance(n, (ast.Import, ast.ImportFrom))], type_ignores=[])
        assert hashlib.sha256(ast.dump(algorithm, include_attributes=False).encode()).hexdigest() == record["preserved_module_ast"], name
        total += len(actual)
    assert total == 220


@pytest.mark.parametrize("order", [("query_plan", "query_obligations"), ("query_obligations", "query_plan")])
def test_source_import_order_has_one_owner_and_ignores_bare_modules(order):
    result = probe('''
import json,types,time
sys.modules['query_plan']=types.ModuleType('query_plan')
before=list(sys.path);start=time.perf_counter()
from atlas.lifted import load,receipt,require_current
for name in ORDER:load(name)
qp=load('query_plan');qo=load('query_obligations')
cold=time.perf_counter()-start;start=time.perf_counter();assert load('query_plan') is qp
warm=time.perf_counter()-start
basis=receipt(['query_plan','query_obligations'],observe_current=False)
checked=require_current(basis)
assert qo.v1 is qp and qp.TextSpan.__module__=='atlas.reconstruction.query_plan'
assert list(sys.path)==before and sys.modules['query_plan'].__dict__.get('TextSpan') is None
assert not any(n=='laplace' or n.startswith('laplace.') for n in sys.modules)
print(json.dumps({'same_owner':True,'cold_seconds':cold,'warm_seconds':warm,
 'hash_work':checked['hash_work'],'first_adapter_hash_work':basis['first_adapter_hash_work'],
 'receipt_bytes':len(json.dumps(basis).encode())}))
'''.replace("ORDER", repr(order)))
    COSTS["source_" + order[0]] = result


def test_direct_import_has_unknown_first_adapter_basis():
    result = probe('''
import json
from atlas.reconstruction import query_plan
from atlas.lifted import load,receipt,require_current,LiftSourceChanged
assert load('query_plan') is query_plan
try:require_current(receipt(['query_plan'],observe_current=False))
except LiftSourceChanged as e:
 assert e.result['status']=='UNPROVED' and 'query_plan.py' in e.affected_paths[0]
 print(json.dumps({'unknown_refused':True}))
else:raise AssertionError('pre-import must not gain a fabricated start basis')
''')
    assert result["unknown_refused"]


def test_prior_process_receipt_cannot_prove_an_unknown_current_import():
    previous = probe('''
import json
from atlas.lifted import load,receipt
load('query_plan');print(json.dumps(receipt(['query_plan'],observe_current=False)))
''')
    result = probe('''
import json
from atlas.reconstruction import query_plan
from atlas.lifted import load,require_current,LiftSourceChanged
load('query_plan');basis=json.loads(sys.stdin.read())
try:require_current(basis)
except LiftSourceChanged as e:assert e.result['status']=='UNPROVED'
else:raise AssertionError('a historical OBSERVED receipt cannot prove unknown live import')
print(json.dumps({'unknown_live_refused':True}))
''', input_text=json.dumps(previous))
    assert result["unknown_live_refused"]


def test_timers_are_diagnostics_and_stable_basis_keeps_real_work_and_identity():
    result = probe('''
import copy,json
from atlas.lifted import load,receipt,require_current,stable_basis
load('query_plan');r=receipt(['query_plan'],observe_current=False);c=require_current(r)
changed=copy.deepcopy(r);changed['diagnostics']={'hash_work_seconds':999}
assert stable_basis(r)==stable_basis(changed)
assert require_current(stable_basis(r))['status']=='CURRENT'
assert stable_basis(c)['hash_work']['files']==3
assert 'seconds' not in r['hash_work'] and 'seconds' not in r['first_adapter_hash_work']
assert all('hash_seconds' not in row['first_adapter'] for row in r['modules'])
for field in ('status','sha256','bytes','path','loaded_bytes_asserted'):
 altered=copy.deepcopy(r);altered['modules'][0]['first_adapter'][field]='changed'
 assert stable_basis(altered)!=stable_basis(r)
bad=copy.deepcopy(r);bad['schema_version']='other/1'
try:stable_basis(bad)
except ValueError:pass
else:raise AssertionError('only this producer schema can use projection')
print(json.dumps({'stable_timers':True,'semantic_fields_retained':True}))
''')
    assert result["semantic_fields_retained"]


def test_consumed_basis_rejects_forged_identity_observations_and_duplicate_rows():
    result = probe('''
import copy,json
from atlas.lifted import load,receipt,check_current,stable_basis
load('query_plan');original=stable_basis(receipt(['query_plan'],observe_current=False))
mutations=[('api',lambda r:r.update(api_version='wrong-api')),
 ('qualified',lambda r:r['modules'][0].update(qualified_name='another.package.module')),
 ('origin',lambda r:r['modules'][0].update(origin='/different/edition/query_plan.py')),
 ('path',lambda r:r['modules'][0]['first_adapter'].update(path='/different/source.py')),
 ('bytes',lambda r:r['modules'][0]['first_adapter'].update(bytes=1)),
 ('proof',lambda r:r['modules'][0]['first_adapter'].update(loaded_bytes_asserted=True)),
 ('duplicate',lambda r:r['modules'].insert(0,{**r['modules'][0],'first_adapter':{**r['modules'][0]['first_adapter'],'sha256':'sha256:'+'0'*64}})),
 ('requested_duplicate',lambda r:r['requested'].append('query_plan')),
 ('bad_hash',lambda r:r['modules'][0]['first_adapter'].update(sha256='sha256:bad')),
 ('byte_bool',lambda r:r['modules'][0]['first_adapter'].update(bytes=True))]
rejected=[]
for name,change in mutations:
 r=copy.deepcopy(original);change(r)
 try:check_current(r)
 except ValueError:rejected.append(name)
 else:raise AssertionError('malformed consumed basis accepted '+name)
r=copy.deepcopy(original);r['modules'][0]['first_adapter']['bytes']=1;r['first_adapter_hash_work']['bytes']=1+r['provenance_map']['first_adapter']['bytes']+r['package_initializer']['first_adapter']['bytes']
try:check_current(r)
except ValueError:rejected.append('coherent_forged_byte_counts')
else:raise AssertionError('source hash cannot silently accept wrong byte count')
assert check_current(original)['status']=='CURRENT'
print(json.dumps({'rejected':rejected}))
''')
    assert len(result["rejected"]) == 11


def test_concurrent_first_load_settlement_cannot_poison_observed_basis():
    result = probe('''
import json,threading,time
import atlas.lifted as owner
original=owner.importlib.import_module;imported=threading.Event();release=threading.Event();second_started=threading.Event();results=[];errors=[]
def controlled(name):
 m=original(name)
 if name=='atlas.reconstruction.query_plan' and threading.current_thread().name=='first':
  imported.set();assert release.wait(3)
 return m
owner.importlib.import_module=controlled
def run():
 try:results.append(owner.load('query_plan'))
 except BaseException as e:errors.append(str(e))
first=threading.Thread(target=run,name='first');first.start();assert imported.wait(3)
def second_run():
 second_started.set();run()
second=threading.Thread(target=second_run,name='second');second.start();assert second_started.wait(3)
time.sleep(.02);assert second.is_alive();release.set();first.join(3);second.join(3)
owner.importlib.import_module=original
assert not errors and len(results)==2 and results[0] is results[1]
basis=owner.receipt(['query_plan'],observe_current=False)
assert basis['modules'][0]['first_adapter']['status']=='OBSERVED'
assert owner.require_current(basis)['status']=='CURRENT'
print(json.dumps({'concurrent_same_owner':True,'observed_basis_preserved':True}))
''')
    assert result["observed_basis_preserved"]


def test_package_initializer_change_is_a_required_source_input(installed):
    result = probe('''
import json
from pathlib import Path
from atlas.lifted import load,receipt,require_current,LiftSourceChanged
load('query_plan');basis=receipt(['query_plan'],observe_current=False)
path=Path(sys.argv[1])/'atlas/reconstruction/__init__.py';original=path.read_bytes()
assert basis['package_initializer']['first_adapter']['path']==str(path)
try:
 path.write_bytes(original+b'\\n# namespace recipe change\\n')
 try:require_current(basis)
 except LiftSourceChanged as e:assert str(path) in e.affected_paths
 else:raise AssertionError('executed initializer is a required source input')
finally:path.write_bytes(original)
assert require_current(basis)['status']=='CURRENT'
print(json.dumps({'initializer_covered':True}))
''', installed)
    assert result["initializer_covered"]


def test_core_plan_and_metadata_are_light_without_optional_dependencies():
    result = probe('''
import importlib.abc,json
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'torch','triton','cupy','regex'}:
   raise ModuleNotFoundError('deliberately absent '+fullname,name=fullname)
sys.meta_path.insert(0,Block())
import atlas,atlas.store,atlas.snapshot
from atlas.lifted import load,receipt,LiftUnavailable
load('query_plan');load('query_obligations');load('context_budget')
assert receipt(['query_plan'],observe_current=False)['api_version']=='atlas.reconstruction/1'
for name,dependency in [('gpu_budget','torch'),('memory_packing','regex')]:
 try:load(name)
 except LiftUnavailable as e:assert dependency in str(e)
 else:raise AssertionError('missing optional extra must refuse')
assert not any(name in sys.modules for name in ('torch','triton','cupy','regex'))
assert 'atlas.reconstruction.gpu_budget' not in sys.modules
print(json.dumps({'core_plan_light':True,'named_optional_absence':True}))
''')
    assert result["core_plan_light"]


def test_grading_public_consumers_share_the_canonical_objects():
    result = probe('''
import json
from atlas.grading.lifted import section_calculus,section_block_operator,lift_receipt,forbidden_import_check
from atlas.lifted import load,require_current
calc=section_calculus();block=section_block_operator()
assert calc is load('section_calculus') and block is load('section_block_operator')
assert block.resolve_gpu_budget is load('gpu_budget').resolve_gpu_budget
basis=lift_receipt(observe_current=False);current=require_current(basis)
assert current['status']=='CURRENT' and len(basis['closure'])==3
assert forbidden_import_check()['verdict']=='clean'
assert all(n not in sys.modules for n in ('section_calculus','section_block_operator','gpu_budget'))
print(json.dumps({'grading_same_owner':True,'hash_work':current['hash_work']}))
''')
    COSTS["grading"] = result


def test_preserved_budget_numeric_and_named_device_refusal():
    result = probe('''
import json,torch
from atlas.lifted import load
b=load('gpu_budget')
budget=b.compute_gpu_budget(resident_bytes=100,free_bytes=900,total_device_bytes=1000,
 reserved_bytes=50,allocated_bytes=20,minimum_headroom_bytes=100,headroom_fraction=.1)
assert budget.max_bytes==930 and budget.source=='dynamic_cuda_mem_get_info'
explicit=b.resolve_gpu_budget('cpu',max_bytes=321,resident_bytes=20)
assert explicit.max_bytes==321 and explicit.source=='explicit'
try:b.resolve_gpu_budget('cpu')
except TypeError as e:assert str(e)=='dynamic GPU budget requires a CUDA device'
else:raise AssertionError('no silent device fallback')
try:load('section_calculus')._cuda_float(torch.ones(1),'input')
except TypeError as e:assert str(e)=='input must be a floating CUDA tensor'
else:raise AssertionError('CPU cannot masquerade as CUDA')
print(json.dumps({'integer_budget':930,'explicit_budget':321,'device_refusal':True,
 'gpu_operation':False}))
''')
    assert result["integer_budget"] == 930


def test_installed_selection_and_provenance_with_research_sibling_present(installed):
    result = probe('''
import json
from pathlib import Path
from atlas.lifted import load,receipt,require_current
qp=load('query_plan');qo=load('query_obligations');basis=receipt(['query_plan','query_obligations'],observe_current=False)
assert qo.v1 is qp and all(Path(sys.modules['atlas.reconstruction.'+n].__file__).is_relative_to(Path(sys.argv[1])) for n in basis['closure'])
assert Path(sys.modules['atlas.reconstruction._provenance'].__file__).is_relative_to(Path(sys.argv[1]))
assert require_current(basis)['status']=='CURRENT'
print(json.dumps({'origins':{n:sys.modules['atlas.reconstruction.'+n].__file__ for n in basis['closure']},
 'provenance_packaged':True,'first_adapter_hash_work':basis['first_adapter_hash_work']}))
''', installed)
    assert (ROOT / "synthetics papers/corpus-as-a-state/reconstruction/extension/query_plan.py").exists()
    COSTS["installed"] = result


def test_source_and_installed_preserved_explicit_budget_agree(installed):
    code = '''
import json
from atlas.lifted import load
b=load('gpu_budget')
result=b.resolve_gpu_budget('cpu',max_bytes=321,resident_bytes=20)
print(json.dumps(result.receipt()))
'''
    source = probe(code)
    selected = probe(code, installed)
    assert selected == source == {"max_bytes": 321, "source": "explicit",
        "resident_bytes": 20, "free_bytes": None, "reusable_pool_bytes": None,
        "total_device_bytes": None, "headroom_bytes": None}


def test_failed_selected_import_cleans_partial_module_and_retries(installed):
    path = installed / "atlas/reconstruction/context_budget.py"
    original = path.read_bytes()
    try:
        path.write_bytes(original.replace(b"from __future__ import annotations\n",
            b"from __future__ import annotations\n_PARTIAL = 1\nraise RuntimeError('selected broken implementation')\n", 1))
        result = probe('''
import json
from pathlib import Path
from atlas.lifted import load,LiftIncompatible,receipt,require_current
try:load('context_budget')
except LiftIncompatible as e:assert isinstance(e.__cause__,RuntimeError)
else:raise AssertionError('selected broken package cannot be masked by research')
assert 'atlas.reconstruction.context_budget' not in sys.modules
path=Path(sys.argv[1])/'atlas/reconstruction/context_budget.py'
raw=path.read_bytes();path.write_bytes(raw.replace(b"_PARTIAL = 1\\nraise RuntimeError('selected broken implementation')\\n",b'',1))
m=load('context_budget');assert require_current(receipt(['context_budget'],observe_current=False))['status']=='CURRENT'
print(json.dumps({'cleanup_and_retry':True}))
''', installed)
        assert result["cleanup_and_retry"]
    finally:
        path.write_bytes(original)


def test_unknown_qualified_preload_is_not_a_selected_implementation():
    result = probe('''
import json,types
sys.modules['atlas.reconstruction.context_budget']=types.ModuleType('atlas.reconstruction.context_budget')
from atlas.lifted import load,LiftIncompatible
try:load('context_budget')
except LiftIncompatible as e:assert 'ORIGIN-MISMATCH' in str(e)
else:raise AssertionError('foreign qualified object cannot become source proof')
print(json.dumps({'foreign_refused':True}))
''')
    assert result["foreign_refused"]


def test_retained_basis_refuses_source_and_provenance_changes_not_unrelated_history(installed):
    result = probe('''
import hashlib,json,marshal,time
from pathlib import Path
from atlas.lifted import load,receipt,require_current,LiftSourceChanged
m=load('context_budget');basis=receipt(['context_budget'],observe_current=False)
assert require_current(basis)['status']=='CURRENT'
code=hashlib.sha256(marshal.dumps(m.canonical.__code__)).hexdigest()
path=Path(m.__file__);original=path.read_bytes()
try:
 path.write_bytes(original.replace(b'return json.dumps(',b"return 'CANDIDATE:' + json.dumps(",1))
 try:require_current(basis)
 except LiftSourceChanged as e:assert e.result['status']=='CHANGED' and str(path) in e.affected_paths
 else:raise AssertionError('changed current source must refuse')
 assert load('context_budget') is m and hashlib.sha256(marshal.dumps(m.canonical.__code__)).hexdigest()==code
 assert m.canonical({'x':1})=='{"x":1}'
 import subprocess
 fresh_code="import sys;sys.path.insert(0,sys.argv[1]);from atlas.lifted import load,receipt,require_current;import hashlib,json,marshal;m=load('context_budget');r=receipt(['context_budget'],observe_current=False);print(json.dumps({'value':m.canonical({'x':1}),'code':hashlib.sha256(marshal.dumps(m.canonical.__code__)).hexdigest(),'current':require_current(r)['status'],'source':r['modules'][0]['first_adapter']['sha256']}))"
 fresh=subprocess.run([sys.executable,'-I','-B','-c',fresh_code,sys.argv[1]],capture_output=True,text=True,timeout=10)
 assert fresh.returncode==0,fresh.stderr
 new=json.loads(fresh.stdout);assert new['value']=='CANDIDATE:{"x":1}' and new['current']=='CURRENT'
 assert new['code']!=code and new['source']!=basis['modules'][0]['first_adapter']['sha256']
 assert basis['modules'][0]['first_adapter']['loaded_bytes_asserted'] is False
finally:path.write_bytes(original)
assert require_current(basis)['status']=='CURRENT'
meta=Path(sys.modules['atlas.reconstruction._provenance'].__file__);raw=meta.read_bytes()
try:
 meta.write_bytes(raw+b'\\n# provenance-only generation change\\n')
 try:require_current(basis)
 except LiftSourceChanged as e:assert str(meta) in e.affected_paths
 else:raise AssertionError('provenance source is a declared input')
finally:meta.write_bytes(raw)
history=Path(sys.argv[1]).parent/'unrelated-history.json';history.write_text('{}')
assert require_current(basis)['status']=='CURRENT';history.unlink()
print(json.dumps({'source_refused':True,'old_loaded_symbol_preserved':True,
 'historical_basis_readable':True,'fresh_changed_symbol_observed':True,
 'provenance_only_refused':True,'unrelated_history_current':True}))
''', installed)
    COSTS["mutation"] = result


def test_legacy_adapters_reference_canonical_private_functions():
    result = probe('''
import importlib.util,json
from pathlib import Path
from atlas.lifted import load
root=Path(ROOT_PATH)
path=root/'synthetics papers/corpus-as-a-state/reconstruction/extension/query_plan.py'
spec=importlib.util.spec_from_file_location('historical_query_plan_driver',path)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
assert module.compile_query is load('query_plan').compile_query
assert module._claim is load('query_plan')._claim
assert callable(module.replay_original_112)
assert 'news_projection' not in sys.modules
print(json.dumps({'same_compiler':True,'private_entrypoint_preserved':True,'legacy_replay_not_eager':True}))
'''.replace("ROOT_PATH", repr(str(ROOT))))
    assert result["private_entrypoint_preserved"]
