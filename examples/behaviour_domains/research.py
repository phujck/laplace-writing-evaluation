"""A deterministic producer/run/result plus a separately optional actual plot."""
from __future__ import annotations
import importlib.util
import time
from pathlib import Path
from .core import PROJECT

PRODUCER = '''import argparse, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--mode", choices=["smoke"], required=True)
p.add_argument("--args-json", required=True)
p.add_argument("--result", required=True)
a=p.parse_args()
assert json.loads(a.args_json)=={}
values=[1,2,3]
Path(a.result).write_text(json.dumps({"values":values,"sum":sum(values),"count":len(values),
    "qualification":"Deterministic arithmetic example, not empirical or scientific validation."})+"\\n")
'''

def run(root, rec):
    from laplace.native import tools
    from laplace.pipeline import registry, visual_production
    from laplace.manuscript import manuscript_source
    from laplace.research import research_records
    def call(name, op, payload):
        return rec.call("research-"+name, tools.execute, root, PROJECT, "work", op, payload)
    def save(path, content):
        return call("artifact-"+path.replace("/","-"), "store_artifact", {
            "path":path,"scope":"project","before":None,"content":content,
            "reason":"Explicit local deterministic example input."})
    script = save("examples/sequence_producer.py", PRODUCER)
    data = save("examples/sequence.csv", "x,y\n1,1\n2,3\n3,6\n")
    declaration = call("producer", "research_producer", {
        "id":"example-sequence","scope":"project",
        "executable":"examples/sequence_producer.py","modes":["smoke"],
        "allowed_args":{},"dependencies":[],"timeout_seconds":30})
    launched = call("launch", "experiment_run", {
        "producer_id":"example-sequence","mode":"smoke","args":{}})
    deadline = time.monotonic()+60
    while True:
        run = tools.execute(root, PROJECT, "work", "run_status", {"id":launched["run"]["id"]})
        if run["state"] != "RUNNING" or time.monotonic() >= deadline:
            break
        time.sleep(.05)
    rec.save("research-terminal-run", run)
    assert run["state"] == "COMPLETE", run
    assert run.get("exit_code") in (None, 0), run
    recorded = call("record-result", "research_record", {
        "kind":"result","id":"result:sequence","run_id":run["id"],"result":run["result_path"],
        "question":"What does this exact local integer sum return?",
        "summary":"The authored input 1, 2, 3 has sum 6. This is a workflow fixture, not new science."})
    source = manuscript_source.resolve(PROJECT, repo_root=root)
    manuscript = root/source["manuscript_dir"]
    registered = registry.resolve(PROJECT, repo_root=root)
    base = registered.path(registered.project_dir, root)
    current = rec.call("research-currentness", research_records.result_bindings,
                      manuscript, ["result:sequence"], base)
    assert current["status"] == "CURRENT", current
    # A valid owner artifact update changes producer provenance. It must not
    # re-certify the old completed run or mutate its result bytes.
    read = call("read-producer", "read_artifact", script["read_handle"]["payload"])
    changed = call("change-producer", "store_artifact", {
        **read["update_handle"]["payload"],
        "content":PRODUCER+"\n# An explicit subsequent authored generation.\n",
        "reason":"Exercise producer-source currentness without altering the original run."})
    stale = rec.call("research-stale-currentness", research_records.result_bindings,
                    manuscript, ["result:sequence"], base)
    assert stale["status"] != "CURRENT", stale
    # Re-run the current generation and retain a distinct, honestly current result.
    second = call("launch-current", "experiment_run", {
        "producer_id":"example-sequence","mode":"smoke","args":{}})
    deadline = time.monotonic()+60
    while True:
        second_run=tools.execute(root,PROJECT,"work","run_status",{"id":second["run"]["id"]})
        if second_run["state"]!="RUNNING" or time.monotonic()>=deadline:break
        time.sleep(.05)
    rec.save("research-current-terminal-run",second_run)
    assert second_run["state"]=="COMPLETE",second_run
    call("record-current-result","research_record",{
        "kind":"result","id":"result:sequence-current","run_id":second_run["id"],
        "result":second_run["result_path"],"question":"What does the current authored generation return?",
        "summary":"Sum 6 on the same fixed three integers. Provenance and interpretation remain separate."})
    visual = {"status":"UNAVAILABLE_OPTIONAL","reason":"matplotlib is not installed in this runtime"}
    if importlib.util.find_spec("matplotlib") is not None:
        spec={"id":"sequence-plot","kind":"plot","title":"Cumulative sum of the example input",
            "question":"Where does the total of six come from?",
            "caption":"Cumulative sums of the authored integers 1, 2, 3. A workflow illustration, not measured data.",
            "source_data":"examples/sequence.csv","x":"x","series":["y"],
            "result_ids":["result:sequence-current"]}
        call("visual-create","visual_create",{"spec":spec})
        rendered=call("visual-render","visual_render",{"id":"sequence-plot"})
        call("visual-place","visual_place",{"id":"sequence-plot","file":"S1.tex","after_line":2})
        visual={"status":"EXECUTED","render":rendered}
    return {"status":"EXECUTED", "first_run_id":run["id"],
        "current_run_id":second_run["id"], "first_result_currentness":stale,
        "producer_artifact":changed["id"], "data_artifact":data["id"], "visual":visual,
        "tex_pdf":"NOT_YET_EXERCISED: separate declared TeX capability and output delivery required"}
