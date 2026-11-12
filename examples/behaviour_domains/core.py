"""Project, authored claim, source/context and Work using real owners.
Adapted from the explicit-root setup in test_writing_portable_core.py.
Its synthetic session/reply banking is deliberately NOT copied.
"""
from __future__ import annotations
import json

PROJECT = "behaviour-example"

def run(root, rec):
    from laplace.projects import library
    from laplace.work import project_work
    from laplace.research import corpus_ingest
    from laplace.manuscript import manuscript_source
    from laplace.pipeline import authoring
    from laplace import sdk
    from laplace.native import tools
    src = root/"sources"/PROJECT
    src.mkdir(parents=True)
    (src/"main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "This example follows a locally authored sentence.\n"
        "\\input{S1}\n\\end{document}\n", encoding="utf-8")
    (src/"S1.tex").write_text(
        "\\section{Setting}\\label{sec:setting}\n"
        "The input sequence is 1, 2, 3.\n"
        "\\begin{equation}\n1 + 2 + 3 = 6 \\label{eq:sequence}\n"
        "\\end{equation}\n", encoding="utf-8")
    status, imported = rec.call("core-project-import", library.import_source,
        {"name": PROJECT, "title": "Behaviour example",
         "root": "sources/"+PROJECT+"/main.tex", "editable": True}, root)
    assert status == 201, imported
    for n, deposit in enumerate((
        {"kind":"add-node", "node":"def:sequence", "parent":"sec:setting",
         "node_kind":"definition", "essence":"An authored synthetic input sequence is the ordered list 1, 2, 3.", "by":"example-author"},
        {"kind":"set-projection", "node":"def:sequence",
         "value":{"term":"input sequence","aliases":[]}, "by":"example-author"})):
        result = rec.call("core-concept-"+str(n), corpus_ingest.rewire_add, root, PROJECT, deposit)
        assert not result.get("error"), result
    work = rec.call("core-work-create", project_work.task, PROJECT,
        {"id":"WORK-example", "title":"Inspect the local sequence",
         "goal":"Trace the authored sequence through owner records without a model."}, root)
    detail = rec.call("core-work-read", project_work.read, PROJECT,
                      {"view":"detail","id":"WORK-example"}, root)
    assert detail["task"]["id"] == "WORK-example"
    rec.refuses("core-work-stale-guard", ValueError, project_work.task, PROJECT,
        {"id":"WORK-example","title":"Inspect the local sequence","goal":"Must not overwrite",
         "expected_work_revision":"sha256:"+"0"*64}, root)
    note=rec.call("core-artifact-create", tools.execute, root, PROJECT, "work", "store_artifact",
        {"path":"examples/README.md","before":None,"content":"# Authored local example\\nNo provider has run.\\n",
         "reason":"A real owner-custodied example note."})
    read_note=rec.call("core-artifact-read",tools.execute,root,PROJECT,"work",**note["read_handle"])
    assert read_note["content"]=="# Authored local example\\nNo provider has run.\\n"
    rec.refuses("core-artifact-collision",ValueError,tools.execute,root,PROJECT,"work","store_artifact",
        {"path":"examples/README.md","before":None,"content":"collision","reason":"Deliberate negative control."})
    source = rec.call("core-source-resolve", manuscript_source.resolve,
                      PROJECT, repo_root=root)
    context = rec.call("core-context", authoring.build_context, PROJECT,
                       {"files":["S1.tex"]}, repo_root=root)
    discovery = rec.call("core-sdk-describe", sdk.describe, root=root)
    return {"status":"EXECUTED", "project":PROJECT, "source":source,
        "work_id":detail["task"]["id"], "work_revision":work.get("work_revision"),
        "context_id":context.get("context_id"),
        "browser": "Open this output's workspace with the installed Writing app. Select Behaviour example.",
        "proposal":"NOT_YET_EXERCISED: genuine retained turn or explicit human-origin proposal owner required. No fabricated provider journal.",
        "independent_review":"NOT_RUN", "source_mutation":"Only authored synthetic initial source files, no Main files touched",
        "records":"workspace/contract/talk.jsonl and the workspace's own Work/corpus records"}
