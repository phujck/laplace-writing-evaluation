import json
import shutil
import threading
import pytest

from laplace.pipeline import formal_verification as fv
from laplace.research import formal_surface
from laplace.research import research_records


def _project(tmp_path, source: str = "theorem answer : True := by trivial\n"):
    base = tmp_path / "synthetics papers" / "proof" / "manuscript"
    formal = base / "formal"
    formal.mkdir(parents=True)
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "proof", "tex_root": "synthetics papers/proof/manuscript",
    }]}))
    (formal / "Proof.lean").write_text(source)
    (formal / "lean-toolchain").write_text("leanprover/lean4:v4.34.1\n")
    (formal / "lake-manifest.json").write_text("{}\n")
    (formal / "results.json").write_text(json.dumps({"results": [{"id": "r1", "revision": "rev-1"}]}))
    (formal / "manifest.json").write_text(json.dumps({"lean_toolchain": "formal/lean-toolchain",
        "lake_manifest": "formal/lake-manifest.json", "results": "formal/results.json"}))
    return base


def test_missing_tool_is_explicit_not_green(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setattr(fv.shutil, "which", lambda _name: None)
    result = fv.check("proof", file="formal/Proof.lean", declaration="answer", result_id="r1",
                      result_revision="rev-1", repo_root=tmp_path)
    assert result["proof_status"] == "UNAVAILABLE"
    assert result["result"] == {"id": "r1", "revision": "rev-1", "handle": result["result"]["handle"]}
    file_row=result['owned_changes']['files'][0]
    assert file_row['path'].endswith('formal/check_receipts.json')
    assert file_row['after_sha256']==file_row['observed_after_sha256']
    assert len(fv._receipts(tmp_path / "synthetics papers" / "proof" / "manuscript")) == 1


def test_lakefile_presence_and_bytes_are_part_of_formal_pin(tmp_path):
    base=_project(tmp_path);manifest=fv._load(base/'formal/manifest.json')
    absent=fv._pin(base,manifest)
    assert absent['lakefiles']=={}
    (base/'lakefile.lean').write_text('import Lake\nopen Lake DSL\npackage proof\n')
    present=fv._pin(base,manifest)
    assert present['lakefiles']!=absent['lakefiles']
    assert list(present['lakefiles'])==['lakefile.lean']


def test_failed_compiler_receipt_returns_bounded_repair_diagnostics(tmp_path,monkeypatch):
    _project(tmp_path)
    monkeypatch.setattr(fv,'_tool_state',lambda root=None,lean_version=None:{
        'available':True,'command':'/fixture/lake','source':'fixture','reason':None})
    monkeypatch.setattr(fv,'_tool_version',lambda command,base:{'version':'4.34.1','output':'Lean 4.34.1'})
    class Result:
        def __init__(self,code,out='',err=''):self.returncode=code;self.stdout=out;self.stderr=err
    def run(command,**kwargs):
        return Result(0,'answer does not depend on any axioms') if '.axioms-' in command[-1] else Result(1,err='Proof.lean:1: type mismatch')
    monkeypatch.setattr(fv.subprocess,'run',run)
    receipt=fv.check('proof',file='formal/Proof.lean',declaration='answer',
                     result_id='r1',result_revision='rev-1',repo_root=tmp_path)
    assert receipt['proof_status']=='FAILED'
    assert receipt['compiler_diagnostics']=={
        'text':'Proof.lean:1: type mismatch','total_chars':27,'truncated':False}
    assert receipt['output_digest'].startswith('sha256:')


def test_sorry_and_revision_mismatch_are_refused_before_tool_execution(tmp_path, monkeypatch):
    _project(tmp_path, "theorem answer : True := by sorry\n")
    monkeypatch.setattr(fv.shutil, "which", lambda _name: None)
    rejected = fv.check("proof", file="formal/Proof.lean", declaration="answer", result_id="r1",
                        result_revision="rev-1", repo_root=tmp_path)
    assert rejected["proof_status"] == "REJECTED"
    try:
        fv.check("proof", file="formal/Proof.lean", declaration="answer", result_id="r1",
                 result_revision="old", repo_root=tmp_path)
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale result revision was accepted")


def test_canonical_research_record_binds_without_duplicate_formal_results(tmp_path, monkeypatch):
    base = _project(tmp_path)
    legacy = base / 'formal' / 'results.json'
    legacy.unlink()
    manifest_path = base / 'formal' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest.pop('results')
    manifest_path.write_text(json.dumps(manifest))
    result_path = base / 'result.json'
    result_path.write_text('{"score": 1}\n')
    status, created = research_records.record('proof', {
        'kind': 'result', 'id': 'r1', 'result': 'result.json',
        'summary': 'Canonical scientific result.'}, root=tmp_path)
    assert status == 201
    revision = created['record']['revision']
    monkeypatch.setattr(fv.shutil, 'which', lambda _name: None)

    checked = fv.check('proof', file='formal/Proof.lean', declaration='answer',
                       result_id='r1', result_revision=revision, repo_root=tmp_path)

    assert checked['proof_status'] == 'UNAVAILABLE'
    assert checked['result']['revision'] == revision
    assert not legacy.exists()
    result_path.write_text('{"score": 2}\n')
    assert fv.state('proof', repo_root=tmp_path)['proof_status'] == 'STALE'
    with pytest.raises(ValueError, match='stale'):
        fv.check('proof', file='formal/Proof.lean', declaration='answer',
                 result_id='r1', result_revision=revision, repo_root=tmp_path)


def test_state_marks_a_changed_checked_receipt_stale(tmp_path, monkeypatch):
    base = _project(tmp_path)
    monkeypatch.setattr(fv.shutil, "which", lambda _name: None)
    pin = fv._pin(base, fv._load(base / "formal" / "manifest.json"))
    fv._write_receipt(base, {"proof_status": "CHECKED", "file": "formal/Proof.lean",
                             "file_digest": "sha256:" + "0" * 64, "declaration": "answer",
                             "result": {"id": "r1", "revision": "rev-1"}, "pin": pin})
    state = fv.state("proof", repo_root=tmp_path)
    assert state["proof_status"] == "STALE"
    assert state["informal_alignment"] == "UNASSESSED"


def test_latest_fresh_recheck_restores_checked_while_retaining_stale_history(tmp_path, monkeypatch):
    base = _project(tmp_path)
    proof = base / "formal" / "Proof.lean"
    manifest = fv._load(base / "formal" / "manifest.json")
    pin = fv._pin(base, manifest)
    bound = fv._result(base, manifest, "r1", "rev-1")
    tool = {"available": True, "command": "/fixture/lake", "source": "fixture", "reason": None}
    monkeypatch.setattr(fv, "_tool_state", lambda root=None, lean_version=None: tool)
    monkeypatch.setattr(fv, "_tool_version", lambda command, root: {
        "version": pin["lean_version"], "output": "Lean " + pin["lean_version"]})

    fv._write_receipt(base, {"proof_status": "CHECKED", "file": "formal/Proof.lean",
        "file_digest": fv._sha(proof), "declaration": "answer", "result": bound, "pin": pin,
        "dependencies": {}, "tool_version_number": pin["lean_version"]})
    assert fv.state("proof", repo_root=tmp_path)["proof_status"] == "CHECKED"
    proof.write_text("theorem answer : True := by\n  trivial\n")
    assert fv.state("proof", repo_root=tmp_path)["proof_status"] == "STALE"

    fv._write_receipt(base, {"proof_status": "CHECKED", "file": "formal/Proof.lean",
        "file_digest": fv._sha(proof), "declaration": "answer", "result": bound, "pin": pin,
        "dependencies": {}, "tool_version_number": pin["lean_version"]})
    refreshed = fv.state("proof", repo_root=tmp_path)

    assert refreshed["proof_status"] == "CHECKED"
    assert len(refreshed["receipts"]) == 2
    assert refreshed["receipts"][0]["stale"] is True
    assert refreshed["receipts"][0]["superseded"] is True
    assert refreshed["receipts"][1]["stale"] is False
    assert refreshed["receipts"][1]["superseded"] is False


def test_unavailable_retry_preserves_checked_standing_but_failure_could_not_reproduce(tmp_path,monkeypatch):
    base=_project(tmp_path);proof=base/'formal/Proof.lean';manifest=fv._load(base/'formal/manifest.json')
    pin=fv._pin(base,manifest);bound=fv._result(base,manifest,'r1','rev-1')
    common={'file':'formal/Proof.lean','file_digest':fv._sha(proof),'declaration':'answer',
            'result':bound,'pin':pin,'dependencies':{},'tool_version_number':pin['lean_version']}
    fv._write_receipt(base,{**common,'id':'checked','proof_status':'CHECKED','checked_at':'2026-01-01T00:00:00Z'})
    fv._write_receipt(base,{**common,'id':'unavailable','proof_status':'UNAVAILABLE','reason':'runtime absent',
                            'checked_at':'2026-01-02T00:00:00Z'})
    monkeypatch.setattr(fv,'_tool_state',lambda root=None,lean_version=None:{
        'available':False,'command':None,'source':None,'reason':'runtime absent'})
    retained=fv.state('proof',repo_root=tmp_path)
    assert retained['proof_status']=='CHECKED'
    assert retained['reproduction_status']=='LATEST_ATTEMPT_UNAVAILABLE'
    assert retained['latest_attempt']['id']=='unavailable'
    assert retained['last_current_checked_receipt']['id']=='checked'
    assert [(row['id'],row['superseded']) for row in retained['receipts']]==[
        ('checked',False),('unavailable',False)]

    fv._write_receipt(base,{**common,'id':'failed','proof_status':'FAILED','reason':'compiler rejected',
                            'checked_at':'2026-01-03T00:00:00Z'})
    contradicted=fv.state('proof',repo_root=tmp_path)
    assert contradicted['proof_status']=='COULD_NOT_REPRODUCE'
    assert contradicted['reproduction_status']=='COULD_NOT_REPRODUCE'
    assert contradicted['latest_attempt']['id']=='failed'
    assert contradicted['last_current_checked_receipt']['id']=='checked'


def test_surface_requires_complete_bound_check_request():
    status, _, body = formal_surface.handle("/formal/check", {}, "POST", b'{"project":"proof"}')
    assert status == 422
    assert "result_revision" in json.loads(body)["error"]


def test_surface_counts_only_an_executing_formal_check(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def checking(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return {"proof_status": "CHECKED"}

    monkeypatch.setattr(formal_surface.formal, "check", checking)
    body = json.dumps({"project": "proof", "file": "formal/Proof.lean",
                       "declaration": "answer", "result_id": "r1",
                       "result_revision": "rev-1"}).encode()
    result = []
    thread = threading.Thread(target=lambda: result.append(
        formal_surface.handle("/formal/check", {}, "POST", body)))
    thread.start()
    assert entered.wait(1)
    assert formal_surface.active_checks() == 1
    release.set(); thread.join(2)
    assert not thread.is_alive()
    assert formal_surface.active_checks() == 0
    assert result[0][0] == 200

@pytest.mark.skipif(not (shutil.which('lake') or __import__('pathlib').Path('.laplace-tools/lean/v4.34.1/bin/lake').is_file()), reason='Lean unavailable')
def test_print_axioms_rejects_imported_custom_axiom(tmp_path, monkeypatch):
    base = _project(tmp_path, 'import formal.Cheat\ntheorem answer : True := cheat\n')
    (base / 'formal' / 'Cheat.lean').write_text('axiom cheat : True\n', encoding='utf-8')
    (base / 'lakefile.lean').write_text('import Lake\nopen Lake DSL\npackage test\nlean_lib formal\n', encoding='utf-8')
    local = __import__('pathlib').Path('.laplace-tools/lean/v4.34.1/bin/lake')
    if local.is_file(): monkeypatch.setenv('LAPLACE_LEAN_LAKE', str(local.resolve()))
    __import__('subprocess').run([str(local.resolve()), 'build', 'formal.Cheat'], cwd=base, check=True)
    result = fv.check('proof', file='formal/Proof.lean', declaration='answer', result_id='r1', result_revision='rev-1', repo_root=tmp_path)
    assert result['proof_status'] == 'REJECTED'
    assert 'cheat' in result['axioms_audit']['forbidden']


@pytest.mark.skipif(not __import__('pathlib').Path('.laplace-tools/lean/v4.34.1/bin/lake').is_file(), reason='pinned Lean unavailable')
def test_active_lean_version_must_equal_toolchain_pin(tmp_path, monkeypatch):
    base = _project(tmp_path)
    (base / 'formal' / 'lean-toolchain').write_text('leanprover/lean4:v0.0.1\n')
    local = __import__('pathlib').Path('.laplace-tools/lean/v4.34.1/bin/lake').resolve()
    monkeypatch.setenv('LAPLACE_LEAN_LAKE', str(local))

    result = fv.check('proof', file='formal/Proof.lean', declaration='answer',
                      result_id='r1', result_revision='rev-1', repo_root=tmp_path)

    assert result['proof_status'] == 'UNAVAILABLE'
    assert 'does not match pinned 0.0.1' in result['reason']


def test_unparseable_toolchain_pin_is_explicitly_unavailable(tmp_path):
    base = _project(tmp_path)
    (base / 'formal' / 'lean-toolchain').write_text('stable\n')

    checked = fv.check('proof', file='formal/Proof.lean', declaration='answer',
                       result_id='r1', result_revision='rev-1', repo_root=tmp_path)
    state = fv.state('proof', repo_root=tmp_path)

    assert checked['proof_status'] == 'UNAVAILABLE' and 'parseable' in checked['reason']
    assert state['proof_status'] == 'UNAVAILABLE' and 'parseable' in state['reason']


def test_formal_read_is_passive_and_explains_fresh_project_setup(tmp_path, monkeypatch):
    base = _project(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('A read must not execute Lake, Lean, or an installer')
    monkeypatch.setattr(fv.subprocess, 'run', forbidden)
    configured = fv.state('proof', repo_root=tmp_path)
    assert configured['runtime_check'] == 'NOT_RUN_ON_READ'
    (base / 'formal/manifest.json').unlink()
    unconfigured = fv.state('proof', repo_root=tmp_path)
    setup = unconfigured['setup']
    assert unconfigured['proof_status'] == 'UNCONFIGURED'
    assert setup['base_directory'] == str(base)
    assert setup['artifact_scope'] == 'manuscript'
    assert setup['manifest_template']['project_root'] == 'formal'
    assert setup['manifest_template']['approved_axioms'] == []
    assert setup['manifest_path'] == 'formal/manifest.json'
    assert any('proof_targets' in item for item in setup['requirements'])


def test_tool_discovery_selects_declared_version_without_running_candidates(tmp_path, monkeypatch):
    monkeypatch.delenv('LAPLACE_LEAN_LAKE', raising=False)
    monkeypatch.setattr(fv.shutil, 'which', lambda name: None)
    for version in ('4.10.0', '4.99.2'):
        binary = tmp_path / '.laplace-tools/lean' / ('v' + version) / 'bin/lake'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nexit 88\n')
        binary.chmod(0o755)
    assert fv._tool_state(tmp_path, '4.99.2')['command'].endswith('/v4.99.2/bin/lake')
    assert fv._tool_state(tmp_path, '4.10.0')['command'].endswith('/v4.10.0/bin/lake')
    assert not fv._tool_state(tmp_path, '4.20.0')['available']
    assert not fv._tool_state(tmp_path)['available']


@pytest.mark.skipif(not __import__('pathlib').Path('.laplace-tools/lean/v4.34.1/bin/lake').is_file(), reason='pinned Lean unavailable')
def test_changed_recursively_imported_local_source_stales_checked_receipt(tmp_path, monkeypatch):
    base = _project(tmp_path, 'import formal.Helper\ntheorem answer : True := helper\n')
    helper = base / 'formal' / 'Helper.lean'
    helper.write_text('theorem helper : True := by trivial\n', encoding='utf-8')
    (base / 'lakefile.lean').write_text('import Lake\nopen Lake DSL\npackage test\nlean_lib formal\n', encoding='utf-8')
    local = __import__('pathlib').Path('.laplace-tools/lean/v4.34.1/bin/lake').resolve()
    monkeypatch.setenv('LAPLACE_LEAN_LAKE', str(local))
    __import__('subprocess').run([str(local), 'build', 'formal.Helper'], cwd=base, check=True)

    checked = fv.check('proof', file='formal/Proof.lean', declaration='answer',
                       result_id='r1', result_revision='rev-1', repo_root=tmp_path)
    assert checked['proof_status'] == 'CHECKED'
    assert 'formal/Helper.lean' in checked['dependencies']

    helper.write_text('theorem helper : True := by\n  trivial\n', encoding='utf-8')
    state = fv.state('proof', repo_root=tmp_path)
    assert state['proof_status'] == 'STALE'
    assert state['receipts'][-1]['stale'] is True
