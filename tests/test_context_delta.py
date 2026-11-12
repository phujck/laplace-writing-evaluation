"""The one context delta, and the altitude the delivery is a function of.

Guarantee B of the writing consolidation campaign
(evidence/WRITING_CONSOLIDATION_2026-10-03/CAMPAIGN.md): context once, then deltas, over
EVERY part, keyed on what the conversation already holds, with nothing unreachable.

Everything here lives below ``tmp_path``: no provider process is launched, the live app
on 127.0.0.1:8771 is never contacted, and no registered project is read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.web import authoring as controller
from laplace.writing import turn_context
from laplace.writing import records as writing_records
from laplace.writing import turn_admission
from laplace.writing import turn_jobs
from laplace.writing.records import _fold as records_fold
from laplace.manuscript import manuscript_source
from laplace.writing import operating as writing_operating
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.writing import reads
from laplace.writing import operations
from laplace.writing import provider as writing_provider
from laplace.pipeline import authoring

CHAPTER = "\n".join(
    ["\\documentclass{book}", "\\begin{document}", "\\chapter{Finite description}"]
    + [f"Paragraph line {index} of the authored prose." for index in range(1, 61)]
    + ["\\end{document}", ""])


@pytest.fixture(autouse=True)
def _clear_controller_process_state():
    """Process state, INCLUDING the provider capability cache.

    `capabilities()` memoises per repository root for ten minutes in module globals
    (src/laplace/writing_provider.py:315), and a turn driven here fills it for a tmp_path
    that no longer exists.  A later module's claude delivery then reads an advertised
    context window out of this module's cache and gains a result key -- which is how running
    this file before tests/test_session_contract.py broke three of its comparisons.
    """
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    writing_provider._CAP_CACHE = None
    writing_provider._CAP_CACHE_ROOT = None
    yield
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    writing_provider._CAP_CACHE = None
    writing_provider._CAP_CACHE_ROOT = None


def _project(root: Path, name: str = "delta") -> Path:
    (root / "contract").mkdir(parents=True, exist_ok=True)
    source = root / "sources" / name
    source.mkdir(parents=True)
    (source / "main.tex").write_text(CHAPTER, encoding="utf-8")
    status, result = writing_projects.import_source(
        {"name": name, "title": name.title(), "root": f"sources/{name}/main.tex",
         "editable": True}, root)
    assert status == 201, result
    manuscript_source.resolve(name, repo_root=root)
    return source


def _tokens(context: dict) -> dict:
    return {part["key"]: part["token"] for part in context["parts"]}


def _paragraph(root: Path, name: str = "delta") -> dict:
    return authoring.build_context(
        name, {"files": ["main.tex"], "line_start": 5, "line_end": 7}, repo_root=root,
        include_guidance=False)


# --------------------------------------------------------------------------- #
# the three cases the campaign's packet brief names
# --------------------------------------------------------------------------- #
def test_nothing_changed_withholds_only_parts_with_executable_reads(tmp_path):
    _project(tmp_path)
    first = _paragraph(tmp_path)
    second = _paragraph(tmp_path)
    delivery = turn_context.without_already_delivered(second["parts"], _tokens(first))
    assert [row["part"] for row in delivery["withheld"]] == [
        part["key"] for part in second["parts"] if part["read"] is not None]
    assert writing_operating.DELTA_HEADER in delivery["prompt"]
    for part in second["parts"]:
        assert (part["text"] not in delivery["prompt"]) == (part["read"] is not None), part["key"]
    assert delivery["withheld_chars"] == sum(
        part["chars"] for part in second["parts"] if part["read"] is not None)


def test_an_unchanged_turn_costs_less_than_the_delivery_it_replaces(tmp_path):
    """The saving is real at the altitude that carries real prose, not just asserted."""
    _project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 5, "line_end": 60}
    context = authoring.build_context("delta", selection, repo_root=tmp_path,
                                      include_guidance=False)
    delivery = turn_context.without_already_delivered(context["parts"], _tokens(context))
    assert delivery["withheld_chars"] > 2 * delivery["sent_chars"], (
        delivery["withheld_chars"], delivery["sent_chars"])


def test_one_changed_paragraph_re_delivers_only_its_part(tmp_path):
    _project(tmp_path)
    first = _paragraph(tmp_path)
    held = _tokens(first)
    target = tmp_path / "sources" / "delta" / "main.tex"
    lines = target.read_text().split("\n")
    lines[5] = lines[5] + " One sentence was added by the test."
    target.write_text("\n".join(lines))
    second = _paragraph(tmp_path)
    delivery = turn_context.without_already_delivered(second["parts"], held)
    resent = [part["key"] for part in second["parts"]
              if part["key"] not in {row["part"] for row in delivery["withheld"]}]
    assert resent == ["preamble", next(key for key in resent if key.startswith("numbered_source:"))]
    assert "One sentence was added by the test." in delivery["prompt"]
    withheld = {row["part"] for row in delivery["withheld"]}
    assert {"framing", "sustained_argument"} <= withheld and "preamble" not in withheld


def test_a_new_session_is_given_everything_once(tmp_path):
    _project(tmp_path)
    context = _paragraph(tmp_path)
    delivery = turn_context.without_already_delivered(context["parts"], {})
    assert delivery["withheld"] == []
    assert delivery["prompt"] == context["prompt"]
    # ... and the baseline it banks makes the next turn pay nothing for the same parts.
    again = turn_context.without_already_delivered(context["parts"], delivery["held"])
    assert len(again["withheld"]) == sum(part["read"] is not None for part in context["parts"])
    assert all(part["text"] in again["prompt"] for part in context["parts"] if part["read"] is None)


# --------------------------------------------------------------------------- #
# the information rule, and the altitude
# --------------------------------------------------------------------------- #
def test_every_withheld_part_names_a_deployed_read(tmp_path):
    _project(tmp_path)
    context = _paragraph(tmp_path)
    delivery = turn_context.without_already_delivered(context["parts"], _tokens(context))
    assert delivery["withheld"]
    for row in delivery["withheld"]:
        assert row["read"], row
        assert row["read"]["operation"] in reads.READS, row
        # Public validation, not registry membership: every emitted request runs.
        writing_tools.execute(tmp_path, "delta", "work", row["read"]["operation"],
                              row["read"]["payload"], None)
    # One block, one grammar: header, prose, then the payload under `already_delivered`.
    assert writing_operating.DELTA_HEADER in delivery["prompt"]
    block=delivery["prompt"].split(writing_operating.DELTA_HEADER,1)[1]
    payload = json.loads(block.split("\n")[2])
    assert payload["already_delivered"][0]["part"] == delivery["withheld"][0]["part"]
    assert payload["already_delivered"] == delivery["delta"]["already_delivered"]


def test_author_instructions_use_the_existing_exact_history_read(tmp_path):
    _project(tmp_path)
    first=_paragraph(tmp_path)
    correction=authoring.bank_correction("delta",{"base_revision":first["revision"],
        "text":"Keep this exact author qualification.","kind":"factual","scope":"project"},
        repo_root=tmp_path)["correction"]
    context=_paragraph(tmp_path)
    comments=next(part for part in context["parts"] if part["key"]=="author_comments")
    delivery=turn_context.without_already_delivered(context["parts"],_tokens(context))
    row=next(row for row in delivery["withheld"] if row["part"]=="author_comments")
    assert row["read"]=={"operation":"author_history","payload":{"view":"corrections"}}
    value=writing_tools.execute(tmp_path,"delta","work",row["read"]["operation"],
                                row["read"]["payload"],None)
    assert correction["id"] in json.dumps(value)
    assert comments["text"] not in delivery["prompt"]


def test_unrouteable_multi_record_parts_stay_in_band():
    keys=("preamble","applied_edits","glossary",
          "canonical_structure","direct_prerequisites","mathematical_record",
          "section_notes","local_source_refs")
    parts=[{"key":key,"text":"exact "+key,"chars":len("exact "+key),
            "token":"token-"+key,"read":authoring.delivery_part_read(key)} for key in keys]
    delivery=turn_context.without_already_delivered(
        parts,{part["key"]:part["token"] for part in parts})
    assert delivery["withheld"]==[]
    assert all(part["text"] in delivery["prompt"] for part in parts)


def test_per_file_and_project_instruction_reads_are_concrete():
    assert authoring.delivery_part_read("numbered_source:sources/book/main.tex")=={
        "operation":"source","payload":{"files":["sources/book/main.tex"]}}
    assert authoring.delivery_part_read("boundary_prose:sources/book/prior.tex")=={
        "operation":"source","payload":{"files":["sources/book/prior.tex"]}}
    assert authoring.delivery_part_read("project_instructions:CURRENT.md")=={
        "operation":"project_guidance","payload":{"path":"CURRENT.md"}}
    for key in ("bibliography_ids","attached_source_notes"):
        assert authoring.delivery_part_read(key)=={
            "operation":"references_attached","payload":{}}


def test_existing_operating_body_reads_still_execute_publicly(tmp_path):
    _project(tmp_path)
    brief=writing_operating.build("delta","work",tmp_path)
    parts=writing_operating.body_parts(brief)
    assert len(parts)==4 and all(part["read"] for part in parts)
    for part in parts:
        route=part["read"]
        writing_tools.execute(tmp_path,"delta","work",route["operation"],route["payload"],None)


def test_live_reference_search_and_attached_collection_are_distinct(tmp_path):
    _project(tmp_path)
    help_row=writing_tools.execute(tmp_path,"delta","work","help",{"operation":"references"},None)
    action=help_row["action"]
    assert action["input"]["required"]==["q"]
    assert "configured reference library" in action["does"]
    assert "references_attached" in action["does"]
    with pytest.raises(operations.OwnerError,match="q= is required"):
        writing_tools.execute(tmp_path,"delta","work","references",{},None)
    attached=writing_tools.execute(tmp_path,"delta","work","references_attached",{},None)
    assert attached=={"project":"delta","associations":[]}


def test_delivery_is_a_function_of_the_altitude_asked_for(tmp_path):
    _project(tmp_path)
    sizes = {}
    for altitude, selection in (
            ("passage", {"files": ["main.tex"], "line_start": 5, "line_end": 7}),
            ("section", {"section_ids": ["sec:one"]}),
            ("chapter", {"files": ["main.tex"]})):
        context = authoring.build_context("delta", selection, repo_root=tmp_path,
                                          include_guidance=False)
        assert context["altitude"] == altitude, (altitude, context["altitude"])
        sizes[altitude] = {part["key"]: part["chars"] for part in context["parts"]}
    assert (sizes["passage"].get("canonical_structure", 0)
            <= sizes["section"].get("canonical_structure", 0)
            <= sizes["chapter"].get("canonical_structure", 0))
    assert authoring.delivery_altitude({"files": ["a.tex", "b.tex"]}) == "manuscript"


def _structure() -> dict:
    """A structure with every key the projection scopes, each big enough to see."""
    def section(ident: str, parent: str | None, nodes: int) -> dict:
        return {"id": ident, "title": "Title " + ident, "kind": "section", "parent_id": parent,
                "depth": 1, "number": "1.1", "order": 1, "ancestor_ids": [parent] if parent else [],
                "child_ids": [], "job": "J" * 300, "notes": "N" * 300, "refs": ["smith2020a"],
                "node_ids": [f"result:{ident}-{index}" for index in range(nodes)], "beat_ids": [],
                "nodes": [{"id": f"result:{ident}-{index}", "label": "L" * 50,
                           "summary": "S" * 400, "kind": "result"} for index in range(nodes)],
                "beats": [],
                "source": {"section_id": ident, "source_files": [f"{ident}.tex"],
                           "status": "MATCHED", "plan_title": "Title " + ident,
                           "source_titles": ["Title " + ident], "source_label": "section:" + ident}}
    return {"eligible_for_authoring": True,
            "sections": [section("sec:one", "chapter-01", 3)],
            "boundaries": [section("sec:two", "chapter-01", 2)],
            "children": [section("sec:three", "sec:one", 1)],
            "ancestors": [section("chapter-01", None, 0)],
            "outline": [{"id": "chapter-01", "title": "One", "kind": "chapter",
                         "parent_id": None, "number": "1", "job": "J" * 300,
                         "child_ids": ["sec:one"]}],
            "edges": [{"source": "result:sec:one-0", "target": "result:sec:two-0",
                       "rel": "prerequisite", "rationale": "R" * 200}],
            "evidence": [{"node_id": "result:sec:one-0", "id": "RUN-1", "revision": "r1",
                          "interpretation": "I" * 300}],
            "gaps": [{"id": "sec:one", "why": "W" * 200}],
            "scoped_history": [{"id": "RW-1", "kind": "add-node", "node": "result:sec:one-0",
                                "rationale": "R" * 200}],
            "source_support": [{"node": "result:sec:one-0", "citations": ["smith2020a"],
                                "qualification": "Q" * 300}],
            "selected_node_ids": [], "selected_nodes": [], "direct_dependencies": [],
            "focus": None}


@pytest.mark.parametrize("altitude", ["paragraph", "section", "chapter", "manuscript"])
def test_the_scoped_structure_names_the_read_for_every_key_it_reduced(altitude):
    canonical = authoring._prompt_structure_projection(_structure(), altitude)
    assert canonical["altitude"] == altitude
    for key, row in (canonical.get("scoped_out_of_this_altitude") or {}).items():
        assert row["read"]["operation"] in reads.READS, (key, row)
        assert row["rows"] >= 1
    # The selected section keeps every canonical member ID; the bodies are one read away.
    selected = canonical["sections"][0]
    assert selected["node_ids"] == [f"result:sec:one-{index}" for index in range(3)]
    assert all("summary" not in node for node in selected["nodes"])
    assert not any(key in selected for key in ("job", "notes", "refs"))
    assert canonical["evidence"]["total"] == 1       # published once, as its own part
    routes=canonical["section_bodies"]["bodies_available_via"]
    assert {row["operation"] for row in routes}>={"references_attached","literature_uses"}
    assert not any(row["operation"]=="references" for row in routes)
    literature=next(row for row in routes if row["operation"]=="literature_uses")
    assert literature["payload"]=={"claim_id":"<claim_id from this projection>"}
    source_support=(canonical.get("scoped_out_of_this_altitude") or {}).get("source_support")
    if source_support:
        assert source_support["read"]["payload"]=={"claim_id":"<claim_id>"}


def test_the_structure_projection_shrinks_monotonically_with_the_altitude():
    sizes = {altitude: len(json.dumps(authoring._prompt_structure_projection(
                 _structure(), altitude), ensure_ascii=False))
             for altitude in ("paragraph", "section", "chapter", "manuscript")}
    assert sizes["paragraph"] < sizes["section"] < sizes["chapter"], sizes
    # chapter and manuscript carry the same structure; only the label differs.
    assert sizes["manuscript"] - sizes["chapter"] == len("manuscript") - len("chapter"), sizes


def test_there_is_exactly_one_delta_mechanism_in_the_tree():
    """The superseded ones are deleted, not parked beside the new one."""
    # the turn owner is the facade plus its writing.turn_* domain modules (S1 B1/B2); read them as one tree
    owner = Path(controller.__file__)
    surface = "".join(path.read_text() for path in [owner, *sorted((owner.parent / "writing").glob("turn_*.py"))])
    builder = Path(authoring.__file__).read_text()
    assert "_without_unchanged_science" not in surface.replace(
        "`_without_unchanged_science`", "")           # only the docstring may name it
    assert "def _argument_delta" not in surface
    assert surface.count("def without_already_delivered") == 1
    assert surface.count("without_already_delivered(") == 4   # the definition and its 3 callers
    assert builder.count("def _prompt_parts") == 1


def test_an_applied_edit_the_session_did_not_make_re_delivers_its_part(tmp_path):
    """The baseline is what the conversation HOLDS, so an outside change is re-delivered.

    The decision this pins: `_refresh_owned_context` advances `context_parts` because the
    session itself caused the change and its own tool result carried it - the same law
    `refresh_turn_read_baselines` already applies to a read's digest. Every OTHER path
    leaves the baseline alone, so a change the session did not make still arrives.
    """
    _project(tmp_path)
    first = _paragraph(tmp_path)
    held = _tokens(first)
    target = tmp_path / "sources" / "delta" / "main.tex"
    target.write_text(target.read_text().replace("Paragraph line 3", "Rewritten by the author"))
    second = _paragraph(tmp_path)
    delivery = turn_context.without_already_delivered(second["parts"], held)
    assert "Rewritten by the author" in delivery["prompt"]
    assert not any(row["part"].startswith("numbered_source:") for row in delivery["withheld"])


def test_help_generates_the_concept_asked_for_instead_of_the_whole_catalogue(tmp_path):
    _project(tmp_path)
    whole = writing_tools.execute(tmp_path, "delta", "work", "help", {}, None)
    assert whole["concepts"], "a bare help must say which concepts exist"
    concept = whole["concepts"][0]["concept"]
    one = writing_tools.execute(tmp_path, "delta", "work", "help", {"concept": concept}, None)
    assert one["requested_concept"] == concept
    assert {row["concept"] for row in one["catalogue"]} == {concept}
    assert len(json.dumps(one)) < len(json.dumps(whole))
    with pytest.raises(ValueError):
        writing_tools.execute(tmp_path, "delta", "work", "help", {"concept": "not-a-concept"}, None)
    for malformed in (None, "", [], {}):
        with pytest.raises(ValueError):
            writing_tools.execute(tmp_path, "delta", "work", "help", {"concept": malformed}, None)


# --------------------------------------------------------------------------- #
# ONE policy: the contract's delivery rule and the context delta are one channel
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_the_one_delta_rides_the_user_turn_on_both_transports(tmp_path, monkeypatch, provider):
    """The synthesis's own guarantee, asserted where it can regress.

    A resumed session is given its brief delta AND its context delta in ONE block, in the
    channel both transports carry verbatim (the user turn), produced by the one producer the
    contract names.  Before this, the brief half rode `CHANGED PROJECT ORIENTATION SINCE THE
    LAST TURN` and the delivery half rode `ALREADY DELIVERED IN THIS CONVERSATION`, and the
    project body the transport withholds on a resume was named by neither.
    """
    _project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 5, "line_end": 7}
    initial = _paragraph(tmp_path)
    brief = writing_operating.build("delta", "work", tmp_path)
    session_id = f"WS-one-delta-{provider}"
    writing_records.bank(tmp_path, {"record": "writing-session", "id": session_id,
                                "project": "delta", "provider": provider, "model": "m",
                                "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-binding", "id": f"WB-one-delta-{provider}",
                                "session_id": session_id, "native_id": f"native-{provider}",
                                "model": "m",
                                "tool_contract_digest": brief["tool_contract_digest"]})
    # the previous turn of THIS conversation: its part baseline (the context delta's
    # baseline) and its orientation with one guidance revision behind (the brief delta's).
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": f"WT-one-delta-{provider}",
                                "session_id": session_id, "project": "delta", "mode": "work",
                                "dependencies": initial["dependencies"],
                                "context_parts": {**_tokens(initial),
                                    **{p['key']: p['token'] for p in writing_operating.body_parts(brief)},
                                    "operating_brief.project_protocol": "older"},
                                "orientation": {**turn_context._orientation_snapshot(brief),
                                                "project_protocol": {"revision": "older"}}})
    writing_records.bank(tmp_path, {"record": "writing-reply", "id": f"WR-one-delta-{provider}",
                                "turn_id": f"WT-one-delta-{provider}", "session_id": session_id,
                                "project": "delta", "status": "completed", "text": "Earlier saved reply."})
    prompts, native_ids = [], []

    class Provider:
        def __init__(self, *args, **kwargs): native_ids.append(args[4])
        def run(self, prompt):
            prompts.append(prompt)
            return {"status": "completed", "text": "done", "turn_id": f"native-turn-{provider}"}

    monkeypatch.setattr(writing_provider, "WritingTurn", Provider)
    started = turn_admission.start_turn(tmp_path, {"project": "delta", "session_id": session_id,
                                               "mode": "work", "selection": selection,
                                               "text": "Continue."})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)

    assert native_ids == [f"native-{provider}"]
    turn_text = prompts[0]
    # ONE block, not two, and the retired headers are nowhere.
    assert turn_text.count(writing_operating.DELTA_HEADER) == 1
    assert "ALREADY DELIVERED IN THIS CONVERSATION" not in turn_text
    assert "CHANGED PROJECT ORIENTATION SINCE THE LAST TURN" not in turn_text
    payload = json.loads(turn_text.split(writing_operating.DELTA_HEADER, 1)[1].split("\n")[2])
    # BOTH halves, in the one block: the parts this conversation holds (each naming its
    # read), the project body the transport withholds on a resumed process, and the moved
    # guidance.
    held = {row["part"] for row in payload["already_delivered"]}
    assert "framing" in held and "sustained_argument" in held
    body_keys = {part['key'] for part in writing_operating.body_parts(brief)}
    assert body_keys - {"operating_brief.project_protocol"} <= held
    assert "operating_brief.project_protocol" not in held
    assert "project_protocol" in payload["changed"]
    for row in payload["already_delivered"]:
        if row["part"] != "preamble":
            assert row["read"], row
    # and the channel is the user turn on BOTH transports: the instruction slot of a
    # resumed process carries no delta and no body.
    blocks = writing_operating.process_instructions(
        writing_operating.build("delta", "work", tmp_path), provider, resumed=True)
    # the BLOCK, not the header: the kernel declares the contract, delta channel included
    # (`session_policy()['instructions']['delta']['header']`), and declaring a channel is
    # not delivering through it.
    block_opening = writing_operating.DELTA_HEADER + "\n" + writing_operating.DELTA_PROSE
    assert block_opening in turn_text
    assert block_opening not in blocks["session_slot"]
    assert block_opening not in blocks["turn_prefix"]
    assert blocks["body_delivered"] is False
    assert writing_operating.BODY_HEADER not in blocks["turn_prefix"]
    assert writing_operating.FRAME_HEADER in blocks["turn_prefix"]


def test_passage_scope_does_not_infer_containment_from_tex_formatting(tmp_path):
    _project(tmp_path)
    for end in (7, 28, 60):
        selection = {"files": ["main.tex"], "line_start": 5, "line_end": end}
        context = authoring.build_context("delta", selection, repo_root=tmp_path,
                                         include_guidance=False)
        assert context["altitude"] == "passage"
        selected = next(part for part in context["parts"] if part["key"].startswith("numbered_source:"))
        assert selected["chars"] > 0
    assert authoring.delivery_altitude({"quote": "same prose " * 50}) == "passage"
    assert authoring.delivery_altitude({"quote": "same prose\n" * 50}) == "passage"
    assert authoring.delivery_altitude({"section_ids": ["sec:one"]}) == "section"
    assert authoring.delivery_altitude({"node_id": "claim:one"}) == "section"


def test_same_selected_prose_reformatted_across_twenty_four_lines_has_same_scope(tmp_path):
    source = _project(tmp_path)
    words = ["word" + str(index) for index in range(50)]
    contexts = []
    for body in (" ".join(words), "\n".join(words)):
        (source / "main.tex").write_text("\\documentclass{book}\n\\begin{document}\n"
                                        + body + "\n\\end{document}\n")
        context = authoring.build_context("delta", {
            "files": ["main.tex"], "line_start": 3,
            "line_end": 3 + body.count("\n")}, repo_root=tmp_path,
            include_guidance=False)
        assert context["altitude"] == "passage"
        for word in words:
            assert word in context["prompt"]
        contexts.append(context)
    # Physical source identities change honestly; scope and preservation of authored
    # content stay stable, without claiming a paragraph or section containment relation.
    assert contexts[0]["altitude"] == contexts[1]["altitude"]
