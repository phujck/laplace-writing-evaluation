"""Section and paragraph reader plans through issued guards, native and HTTP."""
from __future__ import annotations
import json
from .core import PROJECT

def run(root, rec):
    from laplace.native import tools, verbs
    from laplace.manuscript import project_structure
    from laplace.web import project_work_surface
    def call(name, op, payload):
        return rec.call("reader-"+name, tools.execute, root, PROJECT, "work", op, payload)
    current = call("structure", "structure", {})
    assert not current.get("sections"), "Requires a fresh core example"
    call("initialise", "structure_change", {"operation":"initialize",
        "expected_revision":current["revision"],
        "expected_source_revision":current["selected_source"]["revision"],
        "sections":[{"id":"setting","title":"Setting","kind":"section","file":"S1.tex"}]})
    current = call("plan-read", "structure", {})
    call("place-concept", "structure_change", {"operation":"plan",
        "expected_revision":current["revision"],
        "op":{"kind":"set-nodes","section":"setting","order":["def:sequence"]}})
    outline = call("outline", "structure", {"view":"outline"})
    summary = call("summary", "structure", {"view":"summary"})
    heading = next(h for h in outline["headings"]["items"] if h["heading_before"].startswith("\\section{Setting}"))
    binding = {"operation":"bind_source","section_id":"setting",
        "file":heading["file"],"line":heading["line"],
        "heading_before":heading["heading_before"],
        "expected_plan_revision":summary["authority"]["plan_revision"],
        "expected_selection":outline["selected_source"]["selection_identity"],
        "expected_source_digest":outline["sources"][heading["file"]]["source_digest"]}
    rec.refuses("reader-stale-heading", ValueError, tools.execute, root, PROJECT, "work",
        "structure_change", {**binding,"expected_source_digest":"sha256:"+"0"*64})
    call("bind-source", "structure_change", binding)
    def detail():
        return project_structure.read(PROJECT, {"view":"detail","section_ids":["setting"]}, root)["sections"][0]
    action = detail()["reader_transition"]["edit_action"]
    payload = {**action["payload"], "changes":{
        "entry_state":"Recognises the ordered input 1, 2, 3.",
        "exit_state":"Can locate the source and distinguish a calculation from its interpretation."}}
    route, request = verbs.from_owner_call("structure_change", payload, project=PROJECT, root=root)
    native = rec.call("reader-native-contract", tools.request, root, PROJECT, "work", request)
    assert native["owner_response"]["plan_publication"]["complete"] is True
    # Replaying the stale edit is a refusal, not another publication.
    rec.refuses("reader-stale-transition", ValueError, tools.execute, root, PROJECT, "work",
                "structure_change", payload)
    action = detail()["paragraph_plan"]["create_action"]
    created = call("paragraph-create", "structure_change", {**action["payload"],
        "changes":{"function":"Explain","proposition":"The input is an authored sequence, not an empirical sample.",
                   "input_nodes":["def:sequence"]}})
    # Exercise the same HTTP adapter used by the human form, without a new server.
    action = detail()["reader_transition"]["edit_action"]
    response = rec.call("reader-http-adapter", project_work_surface.handle,
        "/work/structure/change", {}, "POST", json.dumps({"project":PROJECT,
            **action["payload"], "changes":{"exit_state":"Can inspect the exact local sequence through the native or human route."}}).encode(),
        repo_root=root)
    assert response[0] == 200, response
    final = rec.call("reader-final-detail", detail)
    return {"status":"EXECUTED", "section_id":"setting",
        "paragraphs":final["paragraph_plan"]["paragraphs"]["items"],
        "native_concept":route.concept,
        "http_qualification":"Actual adapter, not a rendered browser or loopback HTTP transport test",
        "source_binding":binding, "scientific_review":"NOT_RUN"}
