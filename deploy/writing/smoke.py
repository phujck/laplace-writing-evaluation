"""Read-only smoke for a running container Writing server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

base=os.environ.get("LAPLACE_SMOKE_URL","http://127.0.0.1:8771")
def get(path):
    with urlopen(base+path,timeout=10) as response:
        if response.status!=200:raise RuntimeError(f"{path}: HTTP {response.status}")
        return json.load(response)

def mcp(workspace, project, *arguments):
    calls=[{"jsonrpc":"2.0","id":1,"method":"initialize"}]
    for ident,argument in enumerate(arguments,2):
        calls.append({"jsonrpc":"2.0","id":ident,"method":"tools/call","params":{
            "name":"laplace_project","arguments":argument}})
    result=subprocess.run([sys.executable,"-m","laplace.native.tools",
        "--root",str(workspace),"--project",project,"--mode","work"],
        input="".join(json.dumps(call)+"\n" for call in calls),text=True,
        capture_output=True,timeout=30,cwd=workspace)
    if result.returncode:raise RuntimeError(result.stderr[-2000:] or "installed tool exited")
    rows=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if len(rows)!=len(calls):raise RuntimeError("installed tool returned incomplete JSON-RPC")
    outputs=[]
    for row in rows[1:]:
        if row.get("error"):raise RuntimeError("installed tool JSON-RPC error: "+str(row["error"]))
        value=row.get("result") or {}
        if value.get("isError"):raise RuntimeError("installed tool refused: "+str(value))
        content=value.get("content") or []
        text=next((item.get("text") for item in content if item.get("type")=="text"),None)
        if not isinstance(text,str):raise RuntimeError("installed tool returned no text content")
        outputs.append(json.loads(text))
    return outputs


def verify_history_custody(workspace, get, projects):
    """Compare one original public row through the existing records/body owners.

    Provider metadata deliberately retains nested observation handles. The
    owner resolves required bodies and validates metadata; this smoke does not
    recursively hydrate metadata or infer errors from words in saved prose.
    """
    from laplace.work import history as author_history
    from laplace.core import bodies as core_bodies
    from laplace.writing import records
    workspace=Path(workspace); selected=None
    with records.index_lock:
        idx=records.index(workspace)
        for meta in idx.rows:
            if (meta.get("project") not in projects or not meta.get("id") or
                    not (meta.get("turn_id") or meta.get("record")=="writing-turn")):
                continue
            raw=records.raw_indexed_record(idx,meta)
            # The public owner owns strict resolution, original-row projection,
            # supporting namespace checks and ambiguous identity refusal.
            expected=author_history.record(meta["project"],"activity:journal:"+meta["id"],workspace)
            resolved=expected["record"]
            fields=[key for key in raw if key in resolved and
                    core_bodies.encode(raw[key])!=core_bodies.encode(resolved[key])]
            if fields:
                selected=(meta["project"],meta["id"],raw.get("turn_id") or raw["id"],expected,fields)
                break
    if selected is None:raise RuntimeError("exported history has no required content-addressed public body")
    project,ident,turn_id,expected,fields=selected
    served=get("/authoring/history?"+urlencode({"project":project,"view":"record",
                                               "id":"activity:journal:"+ident}))
    if (served.get("project")!=project or served.get("record_kind")!=expected["record_kind"] or
            not isinstance(served.get("record"),dict) or
            core_bodies.encode(served["record"])!=core_bodies.encode(expected["record"])):
        raise RuntimeError("served original history row/body differs from selected owner bytes")
    if (any(served.get(key) for key in ("_custody_errors","custody_errors","storage_errors")) or
            served["record"].get("_custody_errors")):
        raise RuntimeError("selected original history has custody errors")
    return {"history_record":ident,"history_turn":turn_id,"history_body_fields":fields,
            "history_resolved_row_bytes":len(core_bodies.encode(expected["record"]))}


def main():
    health=get("/authoring/health")
    projects=get("/authoring/projects").get("projects") or []
    if not projects:raise RuntimeError("exported workspace has no writing projects")
    project=str(projects[0]["id"])
    document=get("/walk/doc?"+urlencode({"corpus":project}))
    workspace=Path(os.environ.get("LAPLACE_WORKSPACE_ROOT","/workspace"))

    help_source,interface=mcp(workspace,project,
        {"operation":"help","payload":{"operation":"source"}},
        {"operation":"repository","payload":{"action":"interface","repository":"laplace","limit":1}})
    if help_source.get("requested_operation")!="source":raise RuntimeError("installed help did not resolve source")
    sources=interface.get("sources") or []
    if not sources:raise RuntimeError("installed interface projection returned no exact source")
    source=sources[0]
    read,=mcp(workspace,project,{"operation":"repository","payload":source["read"]["payload"]})
    if read.get("source",{}).get("sha256")!=source.get("sha256") or not read.get("content"):
        raise RuntimeError("installed interface source did not round-trip through repository read")
    custody=verify_history_custody(workspace,get,{str(row["id"]) for row in projects})
    print(json.dumps({"runtime":health.get("runtime"),"assets":(health.get("frontend_bundle") or {}).get("assets"),
                      "project":project,"document_status":document.get("status") or document.get("source_status") or "served",
                      **custody,"help_operation":help_source.get("requested_operation"),
                      "interface_source":source.get("path"),"interface_sha256":source.get("sha256")},sort_keys=True))


if __name__=="__main__":
    main()
