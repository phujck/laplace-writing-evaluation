"""Actual loopback app, guarded source Save and reopen on the generated project.
Transport setup is scoped from test_writing_portable_core.py, no test imports.
"""
from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from .core import PROJECT

def run(root,rec):
    from laplace.manuscript import manuscript_source
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    log=rec.root/"evidence"/"http-server.log"
    base="http://127.0.0.1:"+str(port)
    def request(path,payload=None,raw=None,header=True):
        data=raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        headers={"Content-Type":"text/plain; charset=utf-8" if raw is not None else "application/json"}
        if header:headers["X-Laplace-Writing"]="1"
        req=urllib.request.Request(base+path,data=data,method="POST" if data is not None else "GET",headers=headers)
        try:
            response=urllib.request.urlopen(req,timeout=20)
        except urllib.error.HTTPError as exc:
            response=exc
        with response:
            body=response.read()
            mime=response.headers.get("Content-Type","")
            return response.code,json.loads(body) if "json" in mime else {
                "bytes":len(body),"sha256":__import__("hashlib").sha256(body).hexdigest()}
    with log.open("w") as stream:
        server=subprocess.Popen([sys.executable,"-I","-B","-m","laplace.web.writing_server",
            "--root",str(root),"--state",str(rec.root/"state"),"--host","127.0.0.1","--port",str(port)],
            cwd=str(root),env=dict(os.environ),stdout=stream,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+60
            health=None
            code=None
            while time.monotonic()<deadline:
                try:
                    code,health=request("/authoring/health")
                    if code==200:break
                except (OSError,urllib.error.URLError):pass
                assert server.poll() is None,"Server stopped. Inspect evidence/http-server.log"
                time.sleep(.2)
            assert code==200 and isinstance(health,dict),health
            rec.save("http-health",health)
            for name,path in (("project","/project?workspace=writing&corpus="+PROJECT),
                              ("asset","/shared/workspace.mjs")):
                code,value=request(path)
                assert code==200,(code,value)
                rec.save("http-"+name,value)
            selected=manuscript_source.resolve(PROJECT,repo_root=root)
            file=(__import__("pathlib").Path(selected["manuscript_dir"])/"S1.tex").as_posix()
            source_path="/projection/tex?"+urllib.parse.urlencode({"corpus":PROJECT,"file":file,"view":"source"})
            code,observed=request(source_path)
            assert code==200,(code,observed)
            rec.save("http-source-before",observed)
            query={**observed["save_handle"]["query"],"author":"example-author"}
            original=observed["content"]
            revised=original+"\nA human-origin raw Save was exercised on this local example.\n"
            code,saved=request("/projection/tex?"+urllib.parse.urlencode(query),raw=revised.encode())
            rec.save("http-source-save",{"code":code,"value":saved})
            assert code==200 and saved["source_committed"],saved
            # Never repeat a committed but incomplete effect to repair maintenance.
            effect=saved.get("source_effect")
            assert effect and effect["complete"],saved
            code,refused=request("/projection/tex?"+urllib.parse.urlencode(query),raw=b"stale overwrite")
            assert code==409,(code,refused)
            rec.save("http-source-stale-refusal",refused)
            code,reopened=request(source_path)
            assert code==200 and reopened["content"]==revised,(code,reopened)
            rec.save("http-source-reopen",reopened)
            # Restore our authored initial text through a NEW exact current Save.
            restore_query={**reopened["save_handle"]["query"],"author":"example-author"}
            code,restored=request("/projection/tex?"+urllib.parse.urlencode(restore_query),raw=original.encode())
            rec.save("http-source-restore-save",{"code":code,"value":restored})
            assert code==200 and restored["source_committed"],restored
            code,last=request(source_path)
            assert code==200 and last["content"]==original
            # Work edit guard through the real HTTP transport.
            code,work=request("/work/state?"+urllib.parse.urlencode(
                {"project":PROJECT,"view":"detail","id":"WORK-example"}))
            assert code==200
            code,stale=request("/work/task",{"project":PROJECT,"id":"WORK-example",
                "title":"Inspect the local sequence","goal":"A stale edit must refuse",
                "expected_work_revision":"sha256:"+"0"*64})
            assert code==409,(code,stale)
            rec.save("http-work-stale-refusal",stale)
            code,edited=request("/work/task",{"project":PROJECT,"id":"WORK-example",
                "title":"Inspect the local sequence","goal":"Trace the authored sequence through owner records and a loopback Save.",
                "expected_work_revision":work["task"]["work_revision"]})
            assert code==201,(code,edited)
            rec.save("http-work-edit",edited)
            return {"status":"EXECUTED","source_file":file,
                "reopened_equal":last["content"]==original,"save":saved,"restored":restored,
                "qualification":"Real HTTP Save/readback and owner history. Not a browser keyboard/manual-Undo or rendered-page proof.",
                "server_log":"evidence/http-server.log"}
        finally:
            server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
