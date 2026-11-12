from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
from pathlib import Path
import pytest

from laplace.web import scanner, shared_ui, writing_server
from laplace.projects import library as writing_projects
from laplace.pipeline import authoring


@pytest.fixture(autouse=True)
def isolated_portable_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', '')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path.parent / 'portable-data'))


def test_server_bind_does_not_depend_on_reverse_dns(monkeypatch):
    def unavailable(*args):raise AssertionError("reverse DNS must not gate local startup")
    monkeypatch.setattr(socket,"getfqdn",unavailable)
    server=scanner._EngineServer(("127.0.0.1",0),scanner.make_handler())
    try:
        assert server.server_name=="127.0.0.1" and server.server_port>0
    finally:server.server_close()


def test_explicit_browser_server_root_is_checkout_bound(tmp_path,monkeypatch):
    monkeypatch.setenv("LAPLACE_REPO_ROOT",str(tmp_path))
    assert scanner._repo_root()==tmp_path.resolve()
    calls=[]
    monkeypatch.setattr(scanner,"serve",lambda port,host,*,writing,repo_root:
                        calls.append((port,host,writing,repo_root)))
    assert scanner.main(["--writing","--repo-root",str(tmp_path),
                         "--host","127.0.0.1","--port","18771"])==0
    assert calls==[(18771,"127.0.0.1",True,tmp_path)]


def test_packaged_writing_assets_are_complete():
    snapshot=shared_ui.capture_asset_snapshot()
    assert snapshot.identity["assets"]>=len(shared_ui._ASSETS)
    assert snapshot.identity["templates"]==2
    assert all(data for data in snapshot.assets.values())
    package_data=Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"*.html"' in package_data and '"static_shared/**/*"' in package_data


def test_browser_project_authoring_uses_cross_platform_lock(tmp_path):
    status,result=writing_projects.create({"name":"portable-book","title":"Portable Book",
        "kind":"book","purpose":"Exercise browser-only owners.","audience":"tester"},tmp_path)
    assert status==201,result
    current=authoring.load("portable-book",tmp_path)
    saved=authoring.save("portable-book",{"base_revision":current["revision"],
        "argument":"A checkout-bound argument."},tmp_path)
    assert saved["argument"]=="A checkout-bound argument."
    assert (tmp_path/result["source"]["manuscript_dir"]/"authoring.json").is_file()


def test_authoring_reads_do_not_write_to_read_only_checkout(tmp_path):
    status,result=writing_projects.create({"name":"read-only-book","title":"Read-only Book",
        "kind":"book","purpose":"Inspect an exported project.","audience":"tester"},tmp_path)
    assert status==201,result
    manuscript=tmp_path/result["source"]["manuscript_dir"]
    lock=manuscript/".authoring.lock"
    if lock.exists():lock.unlink()
    manuscript.chmod(0o555)
    try:
        full=authoring.load("read-only-book",tmp_path)
        summary=authoring.summary("read-only-book",tmp_path)
        assert full["revision"]==summary["revision"]
        assert not lock.exists()
    finally:
        manuscript.chmod(0o755)


def test_authoring_reader_observes_old_or_new_atomic_snapshot(tmp_path):
    status,result=writing_projects.create({"name":"atomic-book","title":"Atomic Book",
        "kind":"book","purpose":"Exercise atomic reads.","audience":"tester"},tmp_path)
    assert status==201,result
    path=tmp_path/result["source"]["manuscript_dir"]/"authoring.json"
    base=json.loads(path.read_text())
    old={**base,"revision":101,"argument":"old complete snapshot"}
    new={**base,"revision":102,"argument":"new complete snapshot"}
    path.write_text(json.dumps(old))
    failures=[]
    def replace_many():
        try:
            for index in range(100):
                value=new if index%2 else old
                authoring._write(path,value)
        except Exception as exc:failures.append(exc)
    writer=threading.Thread(target=replace_many);writer.start()
    observed=[]
    while writer.is_alive():
        state=authoring.load("atomic-book",tmp_path)
        observed.append((state["revision"],state["argument"]))
    writer.join()
    assert not failures and observed
    assert set(observed)<={(101,"old complete snapshot"),(102,"new complete snapshot")}


def test_portable_entry_binds_repo_and_isolated_state(tmp_path,monkeypatch):
    (tmp_path/"registry_projects.json").write_text('{"projects":[]}')
    (tmp_path/"profiles").mkdir()
    monkeypatch.delenv("LAPLACE_STATE",raising=False)
    root,state=writing_server.configure(tmp_path)
    assert root==tmp_path.resolve() and state==tmp_path/".laplace-state"
    assert state.is_dir()
    assert os.environ["LAPLACE_REPO_ROOT"]==str(root)
    assert os.environ["LAPLACE_STATE"]==str(state)
    assert ".mcp-gerard" not in str(state)


def test_container_profiles_do_not_copy_project_or_host_auth():
    dockerfile=Path("deploy/writing/Dockerfile").read_text(encoding="utf-8")
    compose=Path("deploy/writing/compose.yaml").read_text(encoding="utf-8")
    ignore=Path("deploy/writing/Dockerfile.dockerignore").read_text(encoding="utf-8")
    assert "COPY registry_projects.json" not in dockerfile and "COPY contract" not in dockerfile
    assert "CODEX_NPM_SPEC" in dockerfile and "CLAUDE_NPM_SPEC" in dockerfile
    assert "FROM node:22-bookworm-slim AS node22" in dockerfile
    assert "@openai/codex@0.160.1" in dockerfile
    assert "@anthropic-ai/claude-code@2.1.304" in dockerfile
    assert "${LAPLACE_WORKSPACE:?" in compose
    assert "codex-auth:/home/laplace/.codex" in compose
    assert "claude-auth:/home/laplace/.claude" in compose
    assert "~/.codex" not in compose and "~/.claude" not in compose
    assert ignore.startswith("**\n") and "!src/**" in ignore and "!atlas/pyproject.toml" in ignore and "atlas/src" not in ignore


def test_real_foreground_server_health_assets_and_project_route(tmp_path):
    (tmp_path/"profiles").mkdir()
    status,result=writing_projects.create({"name":"http-book","title":"HTTP Book",
        "kind":"book","purpose":"Portable server smoke.","audience":"tester"},tmp_path)
    assert status==201,result
    status,second=writing_projects.create({"name":"http-second","title":"HTTP Second",
        "kind":"book","purpose":"Second selectable example.","audience":"tester"},tmp_path)
    assert status==201,second
    with socket.socket() as probe:
        probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
    env=dict(os.environ);env.pop("LAPLACE_STATE",None);env.pop("LAPLACE_REPO_ROOT",None)
    log_path=tmp_path/"server.log"
    log=log_path.open("w",encoding="utf-8")
    bootstrap=("import faulthandler,runpy; "
               "faulthandler.dump_traceback_later(5,repeat=True); "
               "runpy.run_module('laplace.web.writing_server',run_name='__main__')")
    process=subprocess.Popen([sys.executable,"-c",bootstrap,
        "--root",str(tmp_path),"--host","127.0.0.1","--port",str(port)],
        cwd=tmp_path,env=env,stdout=log,stderr=subprocess.STDOUT,text=True)
    try:
        deadline=time.monotonic()+15;health=None;last_error=None
        while time.monotonic()<deadline:
            try:
                with urlopen(f"http://127.0.0.1:{port}/authoring/health",timeout=1) as response:
                    health=json.load(response)
                break
            except Exception as exc:
                last_error=repr(exc)
                if process.poll() is not None:break
                time.sleep(.05)
        if health is None:
            print(log_path.read_text(encoding="utf-8"),flush=True)
        assert health is not None,{"last_error":last_error,"exit":process.poll()}
        assert health["runtime"]=="writing" and health["frontend_bundle"]["assets"]>=70
        with urlopen(f"http://127.0.0.1:{port}/authoring/projects",timeout=3) as response:
            projects=json.load(response)
        assert projects["projects"]==[
            {"id":"http-book","name":"HTTP Book"},
            {"id":"http-second","name":"HTTP Second"}]
        with urlopen(f"http://127.0.0.1:{port}/walk/doc?corpus=http-book",timeout=3) as response:
            document=json.load(response)
        assert document["corpus"]=="http-book" and document["source_status"]=="resolved"
        with urlopen(f"http://127.0.0.1:{port}/walk/doc?corpus=http-second",timeout=3) as response:
            second_document=json.load(response)
        assert second_document["corpus"]=="http-second" and second_document["source_status"]=="resolved"
        from urllib.request import Request
        request=Request(f"http://127.0.0.1:{port}/projects/create",
            data=json.dumps({"name":"http-created","title":"Created through HTTP",
                             "kind":"book","purpose":"Cross-platform mutation smoke.",
                             "audience":"tester"}).encode(),
            headers={"Content-Type":"application/json","X-Laplace-Writing":"1"},method="POST")
        with urlopen(request,timeout=5) as response:
            assert response.status==201
            created=json.load(response)
        assert (tmp_path/created["source"]["manuscript_dir"]).is_dir()
        assert (tmp_path/".laplace-state").is_dir()
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        log.close()


def test_snapshot_writer_waits_for_a_short_lived_reader(tmp_path):
    path=tmp_path/"authoring.json"
    before=authoring._blank("book");before["argument"]="old"
    after={**before,"argument":"new"}
    authoring._write(path,before);started=threading.Event();failures=[]
    def publish():
        started.set()
        try:authoring._write(path,after)
        except Exception as exc:failures.append(exc)
    with path.open(encoding="utf-8") as reader:
        writer=threading.Thread(target=publish);writer.start();assert started.wait(2)
        time.sleep(.03)
        assert json.load(reader)["argument"]=="old"
    writer.join(3)
    assert not writer.is_alive() and not failures
    assert json.loads(path.read_text(encoding="utf-8"))["argument"]=="new"


def test_failed_snapshot_publish_keeps_previous_bytes_and_cleans_temporary(tmp_path,monkeypatch):
    path=tmp_path/"authoring.json";before=authoring._blank("book")
    authoring._write(path,before);raw=path.read_bytes()
    def denied(*args):raise PermissionError("permanent write refusal")
    monkeypatch.setattr(authoring.os,"replace",denied)
    import pytest
    with pytest.raises(PermissionError):authoring._write(path,{**before,"argument":"changed"})
    assert path.read_bytes()==raw and not list(tmp_path.glob(".authoring-*.json"))
