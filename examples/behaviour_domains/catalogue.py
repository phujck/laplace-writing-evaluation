"""Current owner declarations and case joins, not behavioural acceptance.
Does not replace or mutate release/behaviour-coverage.json.
"""
from __future__ import annotations
import ast
import dataclasses
import importlib.util
import json
from pathlib import Path
from .core import PROJECT

CASES = {
    "core":{"anchor":"core","module":"core","evidence":["core-project-import","core-work-read","core-artifact-read","core-sdk-describe"]},
    "reader":{"anchor":"reader","module":"reader","evidence":["reader-final-detail","reader-native-contract","reader-http-adapter"]},
    "research":{"anchor":"research","module":"research","evidence":["research-terminal-run","research-currentness","research-stale-currentness","research-current-terminal-run"]},
    "literature":{"anchor":"literature","module":"literature","evidence":["literature-original","literature-read","literature-bind","literature-scope"]},
    "source":{"anchor":"source","module":"source","evidence":["source-read","source-delete","source-inverse-read","source-undo","source-reopen"]},
    "http":{"anchor":"http","module":"http","evidence":["http-health","http-source-save","http-source-reopen","http-work-edit"]},
    "atlas":{"anchor":"atlas","module":"atlas","evidence":["atlas-jsonl","atlas-events","atlas-query","atlas-history","atlas-snapshot","atlas-span"]},
}
PREFIX_CASES = {
    "tasks":"core","work":"core","owners":"core","projects":"core",
    "argument":"core","reader-plan":"reader","research":"research",
    "material":"core","literature":"literature","literature-library":"literature",
    "history":"source","source":"source","writing":"http","manuscript":"source",
}
def run(root,rec):
    from laplace.native import tools, verbs
    controls=rec.call("catalogue-help-controls",tools.execute,root,PROJECT,"work","help",{"concept":"controls"})
    http=rec.call("catalogue-help-http",tools.execute,root,PROJECT,"work","help",{"door":"http"})
    areas=rec.call("catalogue-help-areas",tools.execute,root,PROJECT,"work","help",{"concept":"areas"})
    spec=importlib.util.find_spec("laplace.native.declared")
    path=Path(spec.origin)
    tree=ast.parse(path.read_text(encoding="utf-8"))
    operations=[node.args[0].value for node in ast.walk(tree)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
        and node.func.id=="declare" and node.args and isinstance(node.args[0],ast.Constant)]
    assert len(operations)==len(set(operations))
    routes=[dataclasses.asdict(row) for row in verbs.ROUTES]
    rec.save("catalogue-native-routes",{"origin":str(Path(verbs.__file__).resolve()),
        "sha256":rec.digest(Path(verbs.__file__)),"routes":routes})
    grouped={}
    for control in controls["controls"]:
        prefix=control["id"].split(":")[0]
        grouped.setdefault(prefix,[]).append(control)
    census_path=rec.candidate_root/"release"/"behaviour-coverage.json"
    if not census_path.is_file():
        raise ValueError("The declared behaviour-coverage map is required beside these examples")
    census=json.loads(census_path.read_text())
    examples={row["id"]:row for row in census["examples"]}
    mapped={row["id"].split(":")[0]:row["examples"][0] for row in census["human_controls"]}
    joins=[]
    for prefix,rows in grouped.items():
        planned=examples[mapped[prefix]]
        case=CASES.get(PREFIX_CASES.get(prefix,"")) or {
            "anchor":planned["id"],"recipe":"docs/behaviours/"+prefix+".md",
            "command":planned["command"],"app_route":planned["app_route"],
            "prerequisites":planned["prerequisites"],"record_anchors":planned["records"],"evidence":[]}
        evidence=[]
        for name in (case or {}).get("evidence",[]):
            file=rec.root/"evidence"/(name+".json")
            if file.is_file():
                evidence.append({"path":str(file.relative_to(rec.root)),"sha256":rec.digest(file)})
        joins.append({"prefix":prefix,"count":len(rows),
            "case":case,"case_document":"docs/behaviours/"+prefix+".md",
            "available_evidence":evidence,
            "behaviour_status":"CASE_OUTPUT_AVAILABLE_NOT_UI_VERIFIED" if evidence else "RUNNABLE_PREREQUISITE_RECIPE_NOT_EXECUTION",
            "controls":[{"id":row["id"],"view":row["view"],"renders_in":row.get("renders_in"),
                         "does":row.get("does")} for row in rows],
            "qualification":"Owner declaration read is not execution of every control or variant in this group."})
    rec.save("catalogue-case-joins",joins)
    rec.save("catalogue-operations",{"operations":operations,"declared_origin":str(path),
        "sha256":rec.digest(path),"status":"CATALOGUED_NOT_EXECUTED"})
    return {"status":"EXECUTED","native_operation_count":len(operations),
        "native_route_count":len(routes),"control_count":len(controls["controls"]),
        "control_prefix_groups":len(grouped),
        "qualification":"Counts are actual runtime declarations. Only the declaration reads were executed here. Join evidence is named and pinned, not promoted to PASS or full UI coverage.",
        "canonical_census":"Coordinator retains release/behaviour-coverage.json unchanged",
        "cases":"evidence/catalogue-case-joins.json"}
