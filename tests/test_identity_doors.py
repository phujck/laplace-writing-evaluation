"""The proofs identity_doors owes: one gate, one digest, one cure, on every caller path.

Run from this worktree:

    scripts/laplace-python -m pytest -q tests/test_identity_doors.py \
        --basetemp=/tmp/pytest-identity-tokens -p no:cacheprovider

Three of these read the real tree rather than a fixture, and they FAIL rather than skip if it
is missing: `synthetics-foundations` is tracked at HEAD (`git ls-files -- 'synthetics
papers/synthetics-foundations' | wc -l` -> 971), so every worktree carries it.  A test that
skips is not evidence, and the three that matter most here are exactly the ones that tie a
published token to the owner's own value.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

TREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TREE / "src"))

from laplace.core import grammar as g                      # noqa: E402
from laplace.core import identity_doors as d               # noqa: E402

PROJECT = "synthetics-foundations"

# The four response formatters a refusal can leave through, and the doors they serve.  A path
# missing from this list is a path that serves a sentence without a cure, which is the defect
# `retry_instruction` was (synthesis.md §1.10: it reached 2 of 4).
CALLER_PATHS = (
    ("src/laplace/native/tools.py", "the tool door, the MCP adapter and the provider adapter"),
    ("src/laplace/web/project_work_surface.py", "HTTP /work/structure/change, /work/writing-style/*"),
    # S1 B4: the /authoring/* refusal is rendered by the HTTP door authoring_surface.handle delegates to.
    ("src/laplace/web/authoring_http.py", "HTTP /authoring/section-change, /authoring/chapter"),
    ("src/laplace/projects/library.py", "HTTP /projects/metadata"),
)

# The owners this lane converted, and the site the friction report named in each.  Every one of
# them compared an identity by hand; none of them may still do so.
CONVERTED = {
    "src/laplace/manuscript/project_structure.py": 3,
    "src/laplace/research/concepts.py": 3,
    "src/laplace/manuscript/manuscript_structure.py": 3,
    "src/laplace/manuscript/review_surface.py": 1,
    "src/laplace/projects/library.py": 1,
    "src/laplace/manuscript/project_protocol.py": 1,
    "src/laplace/manuscript/writing_style.py": 3,
    "src/laplace/research/research_records.py": 1,   # S1 B7: the research record gate moved with its owner
    # The door whose refusal already named the READ a guard comes from (GRAMMAR.md §4: "the
    # right idea, in the wrong place") now names the HOME as well, at both its compares.
    "src/laplace/research/visuals_surface.py": 2,
}


def _text(relative: str) -> str:
    return (TREE / relative).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1. One gate.
# --------------------------------------------------------------------------- #
def test_no_converted_owner_still_compares_an_identity_by_hand():
    """The closure property: every home a door checks goes through the one comparison.

    `revision_matches` was the hand comparison; a converted owner that still calls it has a
    second comparison, and two comparisons is the 20-names defect with a new spelling.
    """
    offenders = {}
    for relative in CONVERTED:
        hits = []
        for index, line in enumerate(_text(relative).splitlines()):
            code = line.split("#", 1)[0]       # a comment may QUOTE the call it replaced
            if "revision_matches(" in code:
                hits.append(index + 1)
        if hits:
            offenders[relative] = hits
    assert offenders == {}, offenders


def test_every_converted_owner_calls_the_gate_as_often_as_the_report_counted_sites():
    counted = {}
    for relative in CONVERTED:
        source = _text(relative)
        # A door and the precondition inside its writer's lock may share one local wrapper
        # (concepts_surface's `_gate`), which is the point: one comparison, called twice.
        counted[relative] = source.count("identity_doors.gate(") + source.count("_gate(live)")
    short = {name: (found, CONVERTED[name]) for name, found in counted.items()
             if found < CONVERTED[name]}
    assert short == {}, short


def test_the_concept_precondition_is_the_same_gate_as_its_door():
    """review_surface.py:1253-1257 against :1394-1397 is what two rosters cost; the door and
    the precondition inside `rewire_add`'s lock call ONE function here."""
    source = _text("src/laplace/research/concepts.py")
    assert source.count("def _gate(live)") == 1
    assert source.count("_gate(current)") == 1
    assert source.count("_gate(live)") - source.count("def _gate(live)") == 1


def test_the_gate_is_the_only_place_this_layer_digests_anything():
    """No second digest, anywhere in this module.

    A recomputed digest that differed from the owner's would pass this suite and fail
    differential replay, so the module may compute a digest in exactly one function, only for a
    recipe-B home, and only with grammar's own `digest_bytes`.
    """
    source = _text("src/laplace/core/identity_doors.py")
    assert "import hashlib" not in source and "hashlib." not in source
    assert "digest_canonical_json" not in source
    assert source.count("g.digest_bytes(") == 1
    body = source.split("def _token(")[1].split("\ndef ")[0]
    assert "g.digest_bytes(" in body, "the one digest is inside _token and nowhere else"


# --------------------------------------------------------------------------- #
# 2. One shim per old name, each with an expiry.
# --------------------------------------------------------------------------- #
def test_every_door_resolves_every_old_name_to_a_home_in_the_alphabet():
    """And a door with NO old name says so, with its reason, instead of being empty.

    An empty `guard_to_home` is where this layer is going --- the twenty-name census reaches
    zero when every door takes `expected` and nothing else --- but it is also exactly what a
    forgotten table looks like. So emptiness is admissible only when `NO_OLD_NAME` records
    why that door never had one, which is a sentence a reader can check against the door.
    """
    for key, shim in d.DOORS.items():
        assert shim.guard_to_home or key in d.NO_OLD_NAME, key
        if not shim.guard_to_home:
            assert len(d.NO_OLD_NAME[key]) > 40, key      # a reason, not a shrug
        for guard, home in shim.guard_to_home.items():
            for one in str(home).split("|"):
                assert one in g.HOME_KINDS, (key, guard, one)
    assert set(d.NO_OLD_NAME) <= set(d.DOORS)             # no reason for a door that is gone


def test_every_shim_carries_a_date_and_the_parity_run_that_deletes_it():
    for key, shim in d.DOORS.items():
        assert re.search(r"\b20\d\d-\d\d-\d\d\b", shim.expiry), key
        assert "parity" in shim.expiry.lower(), key
    with pytest.raises(ValueError):
        g.Shim(old_operation="x", old_verb="y", verb="change", concept="plan@plan",
               guard_to_home={"expected_revision": "plan"}, expiry="")


def test_an_old_name_is_spoken_in_the_shim_table_and_nowhere_else_in_this_module():
    """The only place an old guard name appears in identity_doors is DOORS."""
    source = _text("src/laplace/core/identity_doors.py")
    table = source.split("DOORS: dict[str, g.Shim] = {}")[1].split("# ----")[0]
    for name in ("expected_revision", "base_revision", "mutation_revision",
                 "expected_source_digest", "expected_plan_revision"):
        assert source.count('"%s"' % name) == table.count('"%s"' % name), name


# --------------------------------------------------------------------------- #
# 3. One cure, and it is in the comparison.
# --------------------------------------------------------------------------- #
def test_a_stale_identity_is_refused_with_the_current_token_and_the_retry():
    with pytest.raises(d.IdentityRefused) as caught:
        d.gate("structure_change", supplied={"expected_revision": "b" * 64},
               homes=[("plan", "p", "sha256:" + "a" * 64)], required=["expected_revision"],
               said="structure revision conflict; read the current plan state first")
    refused = caught.value.refused
    assert refused["kind"] == "identity-stale"
    assert refused["homes"][0]["home"] == "plan:p"
    assert refused["homes"][0]["current_token"] == "rev:plan:p:" + "a" * 64
    assert refused["needed"]["expected"] == ["rev:plan:p:" + "a" * 64]
    # the shim translates the resolver back, so an OLD caller also gets a value, not a sentence
    assert refused["needed_old_names"] == {"expected_revision": "a" * 64}
    # and the owner's own sentence is untouched, so replay compares the same refusal
    assert str(caught.value) == "structure revision conflict; read the current plan state first"


def test_a_missing_guard_is_refused_with_the_value_that_would_have_been_accepted():
    """The 18 recorded `missing-guard-field` refusals get a value instead of a sentence."""
    with pytest.raises(d.IdentityRefused) as caught:
        d.gate("structure_change", supplied={}, homes=[("plan", "p", "a" * 64)],
               required=["expected_revision"], said="structure revision conflict")
    refused = caught.value.refused
    assert refused["kind"] == "shape" and refused["needed"]["missing"] == ["expected_revision"]
    assert refused["needed"]["expected"] == ["rev:plan:p:" + "a" * 64]


def test_require_names_every_stale_home_not_only_the_first():
    """`bind_results` named the home it checked first and cost one writer 8 refusals."""
    with pytest.raises(d.IdentityRefused) as caught:
        d.gate("structure_change bind_results",
               supplied={"expected_revision": "c" * 64, "expected_concept_revision": "d" * 64},
               homes=[("plan", "p", "a" * 64), ("concept-network", "p", "b" * 64)],
               said="concept revision conflict")
    homes = sorted(row["home"] for row in caught.value.refused["homes"])
    assert homes == ["concept-network:p", "plan:p"]
    assert len(caught.value.refused["needed"]["expected"]) == 2


def test_a_state_precondition_refuses_with_a_read_rather_than_a_token():
    """`record`'s gate is a third home's STATE; a fresher token cannot cure it."""
    refused = d.state_not_reached("run_id is not complete and current", home="run:p::r1",
                                  state="RUNNING", reached="COMPLETE",
                                  read="run_status {id} -> state").refused
    assert refused["kind"] == "state-not-reached"
    assert refused["needed"] == {"read": "run_status {id} -> state", "until": "COMPLETE"}
    assert "expected" not in refused["needed"]


def test_one_name_with_two_legal_homes_accepts_either_and_serves_both():
    """`expected_plan_revision` passes on the `plan` home OR the `plan-file` home."""
    for value in ("a" * 64, "b" * 64):
        d.gate("section_change plan", supplied={"expected_plan_revision": value},
               homes=[("plan", "p", "a" * 64), ("plan-file", "p", "b" * 64)],
               required=["expected_plan_revision"], said="projection plan changed")
    with pytest.raises(d.IdentityRefused) as caught:
        d.gate("section_change plan", supplied={"expected_plan_revision": "c" * 64},
               homes=[("plan", "p", "a" * 64), ("plan-file", "p", "b" * 64)],
               required=["expected_plan_revision"], said="projection plan changed")
    assert len(caught.value.refused["needed"]["expected"]) == 2


def test_a_counter_in_an_identity_field_is_refused_by_name():
    """One token form.  An integer is refused with the home that mints over bytes instead."""
    with pytest.raises(d.IdentityRefused) as caught:
        d.gate("structure_change", supplied={"expected_revision": 3},
               homes=[("plan", "p", "a" * 64)], required=["expected_revision"],
               said="structure revision conflict")
    assert caught.value.refused["kind"] == "shape"
    assert "authoring.json" in caught.value.refused["said"]


def test_the_grammars_own_field_replaces_every_old_name():
    d.gate("structure_change", supplied={"expected": ["rev:plan:p:" + "a" * 64]},
           homes=[("plan", "p", "a" * 64)], required=["expected_revision"], said="x")
    with pytest.raises(d.IdentityRefused):
        d.gate("structure_change", supplied={"expected": ["rev:plan:p:" + "b" * 64]},
               homes=[("plan", "p", "a" * 64)], required=["expected_revision"], said="x")
    with pytest.raises(d.IdentityRefused):          # not a token at all
        d.gate("structure_change", supplied={"expected": ["a" * 64]},
               homes=[("plan", "p", "a" * 64)], required=["expected_revision"], said="x")


def test_an_empty_span_still_applies():
    """`before` is CONTENT, so "" is a value, not an absence: editing a blank line applies."""
    d.gate("apply_revision", supplied={"before": ""},
           homes=[("prose", "p::f.tex:1-1", b"")], required=["before"],
           bytes_guards=["before"], said="stale")
    with pytest.raises(d.IdentityRefused):
        d.gate("apply_revision", supplied={"before": ""},
               homes=[("prose", "p::f.tex:1-1", b"text")], required=["before"],
               bytes_guards=["before"], said="stale")


# --------------------------------------------------------------------------- #
# 4. On EVERY caller path.
# --------------------------------------------------------------------------- #
def test_every_caller_path_splices_the_refusal():
    for relative, why in CALLER_PATHS:
        assert "identity_doors.body(" in _text(relative), (relative, why)


# A site that SETS or READS the deleted field: `"retry_instruction":`, `[...]`, `get(...)`,
# `(..., )` or `.retry_instruction`.  The first version of this guard searched `src/laplace`
# ONLY, and a live test that READ the field (tests/test_writing_failure_recovery.py:53) went on
# failing invisibly to it -- a guard that cannot see the half of the tree where the consumers
# live is not a guard.  It now scans `tests/` as well.
RETRY_USE = re.compile(r"""["']retry_instruction["']\s*[:\]\),]|\.retry_instruction\b""")

# The files allowed to NAME the field at all, each because it EXPLAINS the deletion.  This is
# an allowance for prose, never for use: `RETRY_USE` above is applied to these files too, so a
# listed file that started setting or reading the field still fails.  A file not listed here
# may not so much as mention it.
RETRY_NAME_EXPLAINED = {
    "src/laplace/native/tools.py": "the two comments at the sites that built it (:1069, :1190)",
    "src/laplace/web/project_work_surface.py": "the HTTP formatter's comment: it never arrived here",
    "src/laplace/core/grammar.py": "the grammar's own account of what `needed` replaces",
    "src/laplace/core/identity_doors.py": "this module's docstring, point 3",
    "tests/test_identity_doors.py": "this guard, and the two end-to-end proofs of its absence",
    "tests/grammar_spec/grammar.py": "the installed copy of grammar.py",
    "tests/test_writing_failure_recovery.py": "the live test that READ the field until this "
                                              "lane fixed it: it now asserts the absence and "
                                              "the resolver that replaced it",
    "tests/grammar_spec/GRAMMAR.md": "the specification's own measurement of the old field",
    "src/laplace/native/verbs.py": "`account`'s docstring, which cites the BASE line "
                                    "the field was set on (writing_tools.py:1056@706a8204) "
                                    "to say what `needed` replaces",
    "tests/test_routing.py": "the routing lane's citation table: its one row for this "
                             "name points at writing_tools.py:1249, the comment that "
                             "records the deletion, not at a setter",
}


def test_retry_instruction_is_deleted_from_the_tree():
    """Not deprecated: deleted.  It was a sentence on two of four paths.

    Two assertions, and the second is the one the first version of this test was missing.
    (1) No site in `src/laplace` OR in `tests` SETS or READS the field.
    (2) No file outside the explicit allowance above so much as names it, so a new mention
        has to be added to that list on purpose, with its reason.
    """
    used, named = [], []
    for base in ("src/laplace", "tests"):
        for path in sorted((TREE / base).rglob("*.py")) + sorted((TREE / base).rglob("*.md")):
            relative = path.relative_to(TREE).as_posix()
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
                code = line.split("#", 1)[0]
                # The one allowed line: the definition of the pattern itself, whose own
                # text `\.retry_instruction\b` matches it.  Named explicitly rather than
                # weakened -- weakening the pattern is how the first version of this
                # guard came to miss a live READER of the field.
                if code.lstrip().startswith("RETRY_USE"):
                    continue
                if RETRY_USE.search(code):
                    used.append("%s:%d  %s" % (relative, index + 1, line.strip()[:110]))
                if "retry_instruction" in line and relative not in RETRY_NAME_EXPLAINED:
                    named.append("%s:%d  %s" % (relative, index + 1, line.strip()[:110]))
    assert used == []
    assert named == []


def test_a_refusal_survives_being_wrapped():
    """`failure_response` and the HTTP adapters see the exception however it was re-raised."""
    try:
        try:
            d.gate("structure_change", supplied={"expected_revision": "b" * 64},
                   homes=[("plan", "p", "a" * 64)], required=["expected_revision"], said="s")
        except d.IdentityRefused as exc:
            raise ValueError("wrapped") from exc
    except ValueError as outer:
        spliced = d.body(outer, {"error": str(outer)})
    assert spliced["refused"]["homes"][0]["current_token"] == "rev:plan:p:" + "a" * 64


def test_an_identity_refusal_is_a_value_error_so_no_adapter_changed_behaviour():
    assert issubclass(d.IdentityRefused, ValueError)


def _fixture_project(tmp_path):
    """The owners' own structure fixture, so this proof is end to end rather than synthetic."""
    sys.path.insert(0, str(TREE / "tests"))
    import test_project_structure as owner_fixture
    owner_fixture._fixture(tmp_path)
    return "book"


def test_the_http_door_serves_the_cure_in_its_body(tmp_path):
    """`/work/structure/change` had `{"error": str(exc)}` and nothing else: `retry_instruction`
    was built in writing_tools.failure_response, which this adapter does not call."""
    project = _fixture_project(tmp_path)
    from laplace.web import project_work_surface
    from laplace.manuscript import project_structure
    current = project_structure.state(project, tmp_path)["revision"]
    status, _type, raw = project_work_surface.handle(
        "/work/structure/change", {}, "POST",
        json.dumps({"project": project, "operation": "reconcile",
                    "expected_revision": "f" * 64}).encode(), repo_root=tmp_path)
    body = json.loads(raw)
    assert status == 422 and body["error"] == (
        "structure revision conflict; read the current plan state first")
    assert body["refused"]["kind"] == "identity-stale"
    assert body["refused"]["homes"][0]["home"] == "plan:" + project
    assert body["refused"]["needed"]["expected"] == [
        str(g.mint("plan", project, current))]
    assert body["refused"]["needed_old_names"] == {
        "expected_revision": current.removeprefix("sha256:")}


def test_the_tool_door_serves_the_cure_and_no_retry_instruction(tmp_path):
    """The path `failure_response` formats, which is the MCP adapter's and the provider
    adapter's. The sentence is unchanged and the field that replaced `retry_instruction` is the
    resolver the comparison produced."""
    project = _fixture_project(tmp_path)
    from laplace.manuscript import project_structure
    from laplace.native import tools as writing_tools
    current = project_structure.state(project, tmp_path)["revision"]
    payload = {"operation": "reconcile", "expected_revision": "f" * 64}
    with pytest.raises(ValueError) as caught:
        writing_tools.execute(tmp_path, project, "work", "structure_change", payload)
    body = writing_tools.failure_response(tmp_path, project, "work", "structure_change",
                                          payload, caught.value)
    assert "retry_instruction" not in body
    assert body["error"] == "structure revision conflict; read the current plan state first"
    assert body["refused"]["needed"]["expected"] == [str(g.mint("plan", project, current))]
    # the fourth path has no body at all: `execute` RAISES, and the resolver travels on the
    # exception, which is why it is a typed exception and not a formatted string
    assert d.refusal_of(caught.value).refused["needed"]["expected"] == [
        str(g.mint("plan", project, current))]


# --------------------------------------------------------------------------- #
# 5. The real tree: a published token IS the owner's own value.
# --------------------------------------------------------------------------- #
def _registered() -> bool:
    rows = json.loads((TREE / "registry_projects.json").read_text(encoding="utf-8"))
    return any(row.get("name") == PROJECT for row in rows.get("projects", []))


def test_the_tracked_project_is_present_so_these_proofs_cannot_vacate():
    assert _registered(), (
        "%s is tracked at HEAD and must be in this worktree's registry; a skipped proof is "
        "not evidence" % PROJECT)


def test_the_structure_read_publishes_the_plan_home_as_the_token_grammar_mints():
    from laplace.manuscript import project_structure
    read = project_structure.overview(PROJECT, TREE)
    tokens = read["identities"]
    assert ("plan:" + PROJECT) in tokens
    assert tokens["plan:" + PROJECT] == str(
        g.identity(g.Home("plan", PROJECT), project=PROJECT, root=TREE))
    # and the two names this read used to carry for one value are gone
    assert "structure_revision" not in read
    assert "source_revision" not in (read.get("authority") or {})


@pytest.fixture
def book(tmp_path):
    """The owners' disposable structure project (concepts, three source files, BOTH plan homes).

    The token proofs below once read the tracked synthetics-foundations tree; its live state is not a
    fixture (a sparse or exported worktree need not carry its concept network or both plan homes), so
    they run end to end on this project instead. The three proofs above still read the real tree."""
    return _fixture_project(tmp_path), tmp_path


def test_the_concept_read_publishes_both_of_its_homes_as_tokens(book):
    from laplace.research import concepts as concepts_surface
    project, root = book
    read = concepts_surface.state(project, root=root)
    tokens = read["identities"]
    assert tokens["concept-network:" + project] == str(
        g.identity(g.Home("concept-network", project), project=project, root=root))
    node = [key for key in tokens if key.startswith("concept-node:")]
    assert node, tokens
    assert tokens[node[0]] == "rev:%s:%s" % (node[0], read["content_revision"])


def test_an_optional_guard_stays_optional_and_an_empty_one_still_refuses():
    """`visual_place`'s two guards are optional at HEAD: absent or null skips the compare, and
    any other value -- including "" -- is compared and refused.  The gate reproduces both halves,
    because a guard that silently became optional would be a door changing its mind."""
    d.gate("visual_place", supplied={}, homes=[("source-file", "p::f.tex", "a" * 64)],
           required=[], said="source revision conflict")
    with pytest.raises(d.IdentityRefused) as caught:
        d.gate("visual_place", supplied={"base_revision": ""},
               homes=[("source-file", "p::f.tex", "a" * 64)],
               required=["base_revision"], said="source revision conflict")
    assert caught.value.refused["needed"]["expected"] == ["rev:source-file:p::f.tex:" + "a" * 64]
    assert str(caught.value) == "source revision conflict"


def test_the_source_read_publishes_three_homes_and_no_duplicate_names(book):
    from laplace.pipeline import authoring
    project, root = book
    read = authoring.inspect(project, {"section_ids": ["N1"]}, root)
    tokens = read["identities"]
    assert tokens["selected-edition:" + project].startswith("rev:selected-edition:")
    assert tokens["source-traversal:" + project] == str(
        g.mint("source-traversal", project, read["source_revision"]))
    # the two homes one letter apart are two different values, and the token says which
    assert tokens["selected-edition:" + project] != tokens["source-traversal:" + project]
    assert read["sources"], "the selected section reads at least one source file"
    retained = {row["field"] for row in d.RETAINED}
    assert "source.sources[].raw_file_sha256" in retained   # the one asked-for name, dated
    for row in read["sources"]:
        # `full_text_sha256` is deleted; `raw_file_sha256` is only the registered shim of `sha256`
        assert "full_text_sha256" not in row and row["raw_file_sha256"] == row["sha256"]
        home = "source-file:%s::%s" % (project, row["file"])
        assert row["identities"][home] == "rev:%s:%s" % (home, row["sha256"])


def test_the_gate_accepts_the_token_the_structure_read_published():
    """End to end, on the real project: read the token, present it, and the door agrees."""
    from laplace.manuscript import project_structure
    token = project_structure.overview(PROJECT, TREE)["identities"]["plan:" + PROJECT]
    d.gate("structure_change", supplied={"expected": [token]},
           homes=[("plan", PROJECT,
                   project_structure.state(PROJECT, TREE)["revision"])],
           required=["expected_revision"], said="structure revision conflict")


# --------------------------------------------------------------------------- #
# 6. `expected` is reachable through the DOOR, not only through the gate.
#
# A gate handed a dict synthesised from one key (`supplied={guard: value}`) can never see
# `expected`: `gate`'s `raw_expected = supplied.get("expected")` is empty on every such call,
# so opening a door's payload schema to the token field buys a caller nothing.  Six of the
# nineteen converted sites did that.  These proofs are behavioural, on a real payload.
# --------------------------------------------------------------------------- #
GATE_SITES = (
    ("src/laplace/research/concepts.py", 2), ("src/laplace/manuscript/project_structure.py", 3),
    ("src/laplace/manuscript/manuscript_structure.py", 3), ("src/laplace/manuscript/project_protocol.py", 1),
    # writing_projects' material-reference door (6f6d0400c) gates the same project-metadata
    # home with the caller's own payload, beside the title door.
    # visual_place's raw-source door (9a9bdd077) gates the target source-file with the payload too.
    ("src/laplace/projects/library.py", 2), ("src/laplace/research/visuals_surface.py", 3),
    # S1 B7 moved the research record gate, unchanged, into its record owner.
    ("src/laplace/manuscript/writing_style.py", 3), ("src/laplace/research/research_records.py", 1),
    # The editor's doors (WRITING-CONSOLIDATION-W1): review_surface gained the comment door's
    # gate beside the rewrite door's, and three owners that compared nothing now compare a
    # token. They are listed here rather than exempted, because the thing this proof fences
    # --- a gate that cannot see `expected` --- is exactly the mistake a new site makes, and
    # `manuscript_blocks` made it on the first pass (`supplied=edit`, one edit of many).
    ("src/laplace/manuscript/review_surface.py", 2),
    ("src/laplace/manuscript/blocks.py", 1),
    # S1 B3 moved the apply-proposal gate, unchanged, with its transaction out of authoring_surface.
    ("src/laplace/manuscript/source_application.py", 1),
    ("src/laplace/manuscript/manuscript_proposals.py", 1),
)


def test_no_gate_is_handed_a_payload_it_synthesised_from_one_key():
    """Every `supplied=` is the caller\'s own payload, so every door can read `expected`.

    The pattern this forbids is `supplied={"expected_revision": expected}`: a one-key dict
    built at the call site.  `{**payload, "name": coerced}` is allowed and is the shape two
    sites need (a value that arrived nested, and one this door coerces), because the caller\'s
    own keys are still there.
    """
    bad, found = [], 0
    for relative, expect in GATE_SITES:
        text = _text(relative)
        sites = text.split("identity_doors.gate(")[1:]
        assert len(sites) == expect, (relative, len(sites), expect)
        for tail in sites:
            found += 1
            argument = tail.split("supplied=", 1)[1]
            cut = min(index for index in (argument.find(","), argument.find("\n"),
                                          len(argument)) if index >= 0)
            argument = argument[:cut].strip()
            if not (argument == "payload" or argument.startswith("{**payload")):
                bad.append("%s  supplied=%s" % (relative, argument[:70]))
    assert found == 23
    assert bad == []


def test_concept_change_accepts_the_token_its_schema_declares(tmp_path):
    """The door, not the gate: `concept_change` declares `expected` at concepts_surface.py:981
    and :1062, and before this it still refused a correct token because the call site handed the
    gate a one-key dict.  Case A (token) passes the guard; case C (neither) still refuses."""
    project = _fixture_project(tmp_path)
    from laplace.research import concepts as concepts_surface
    from laplace.native import tools as writing_tools
    token = concepts_surface.state(project, root=tmp_path)["identities"][
        "concept-network:" + project]
    edge = {"project": project, "operation": "add_edge", "node": "res:one",
            "target": "def:unplanned", "rel": "support"}

    # A -- the token alone is accepted and the edge is made.
    status, body = concepts_surface.change({**edge, "expected": [token]}, tmp_path)
    assert status in (200, 201), body
    assert "refused" not in body and "revision conflict" not in json.dumps(body)

    # C -- no identity at all is still refused by the door\'s own validator.
    status, body = concepts_surface.change(dict(edge), tmp_path)
    assert status == 422 and "requires" in body["error"] and "base_revision" in body["error"]

    # and a STALE token is still refused, with the current one in `needed`.
    status, body = concepts_surface.change(
        {**edge, "expected": ["rev:concept-network:%s:%s" % (project, "f" * 64)]}, tmp_path)
    assert status == 409
    current = concepts_surface.state(project, root=tmp_path)["identities"][
        "concept-network:" + project]
    assert body["refused"]["needed"]["expected"] == [current]
    assert "retry_instruction" not in body
    del writing_tools


def test_the_style_door_enters_its_comparison_for_a_token_too(tmp_path):
    """`writing_style.update_profile` only reached its provenance gate when the OLD name was
    present, so a caller sending the token skipped the comparison entirely.  `presents` is the
    one-line cure, and this is the behaviour it buys."""
    assert d.presents({"expected": ["rev:style-provenance:p:" + "a" * 64]}, "style-provenance")
    assert not d.presents({"expected": ["rev:style-profile:::x.md:" + "a" * 64]},
                          "style-provenance")
    # NOT a substring test.  The lane's docstring and report cited this call at
    # `writing_style.py:429`, which is the handle coverage/sha256 check in another function,
    # and a test that asks only "does this text occur in the file" cannot tell the two apart.
    # The cited lines are read: the `if` that would have skipped the gate, and the call.
    lines = _text("src/laplace/manuscript/writing_style.py").split("\n")
    assert "payload.get(\"expected_provenance_revision\") is not None" in lines[549], lines[549]
    assert "identity_doors.presents(payload, \"style-provenance\")" in lines[550], lines[550]
    assert "identity_doors.presents(" in lines[489], lines[489]
    assert [n for n, line in enumerate(lines, 1)
            if "identity_doors.presents(" in line] == [490, 551]


def test_the_two_home_plan_refusal_carries_an_old_name_a_caller_can_retry_with(book):
    """The defect this module exists to remove, in its last hiding place.

    `section_change`\'s plan guard has ONE name and TWO legal homes, so its refusal serves two
    current tokens.  `grammar.Shim.from_refusal` inverts `guard_to_home` with a dict
    comprehension, so for the piped spec `plan|plan-file` its only key is the literal string
    `"plan|plan-file"`: the refusal came back with no `needed_old_names` at all, on a door whose
    schema does not yet take `expected` -- two current tokens and no field to put either in.
    `old_names_of` resolves the piped spec; this drives the refusal and then retries with
    exactly what it returned, in BOTH spellings.
    """
    from laplace.manuscript import manuscript_structure as ms
    PROJECT, root = book
    state = ms._structure_state(PROJECT, root)
    assert state.get("revision") and (state.get("authority") or {}).get("plan_revision"), \
        "this proof needs a project with BOTH plan homes live"
    with pytest.raises(d.IdentityRefused) as caught:
        ms._check_plan_guard(state, {"expected_plan_revision": "f" * 64}, PROJECT)
    refused = caught.value.refused
    assert [row["home"] for row in refused["homes"]] == ["plan:" + PROJECT,
                                                         "plan-file:" + PROJECT]
    assert len(refused["needed"]["expected"]) == 2
    old = refused["needed_old_names"]
    assert set(old) == {"expected_plan_revision"}
    assert old["expected_plan_revision"] == g.parse(
        refused["needed"]["expected"][0]).digest
    # the two retries that must now work: the old name the refusal returned ...
    ms._check_plan_guard(state, dict(old), PROJECT)
    # ... and either token under the grammar\'s own field.
    for token in refused["needed"]["expected"]:
        ms._check_plan_guard(state, {"expected": [token]}, PROJECT)


# --------------------------------------------------------------------------- #
# round 3: the four defects an independent judge found, each with its own guard
# --------------------------------------------------------------------------- #
def test_the_browsers_structure_read_publishes_the_same_tokens_as_the_tool_door(book):
    """`GET /work/structure` is `state()`, not `overview()` -- and it had no tokens.

    The one structure read the live app's browser calls is served by
    `project_structure.state` (`project_work_surface.py:39`).  It published four identity
    values -- `revision`, `authority.plan_revision`, `authority.source_revision`,
    `selected_source.revision` -- and no `identities` block, so the brief's "every read
    returns its tokens" was unmet on exactly the read that matters, and three rows of the
    register named "the browser sending identities[...]" as what deletes them while the
    browser had no token to send.  Both reads now mint through ONE function, so this asserts
    equality rather than mere presence.
    """
    from laplace.manuscript import project_structure as ps
    PROJECT, root = book
    state = ps.state(PROJECT, root)
    overview = ps.overview(PROJECT, root)
    assert state["identities"], "the browser's own structure read publishes its tokens"
    assert state["identities"] == overview["identities"], \
        "one mint site: the two structure reads cannot publish different tokens"
    assert set(state["identities"]) == {"plan:" + PROJECT, "plan-file:" + PROJECT,
                                        "selected-edition:" + PROJECT}
    # the token for the `plan` home is the token OF the scalar still published beside it
    assert g.parse(state["identities"]["plan:" + PROJECT]).digest == \
        g.parse(str(d._token("plan", PROJECT, state["revision"]))).digest
    # and adding the block did not move the home it names: `revision` is digested before the
    # return dict is built, so the `plan` home's value is the same one the gate compares.
    ps.change  # the door that compares it exists; the gate's own proofs cover the comparison
    for row in ("revision", "authority", "selected_source"):
        assert row in state, "the shims stay published beside the tokens"
    assert "source_revision" in state["authority"], \
        "authority.source_revision is dropped from overview's PROJECTION only, never here"
    assert "source_revision" not in (overview.get("authority") or {})


def test_the_http_route_for_the_browsers_structure_read_serves_the_tokens(book):
    """The route, not just the function: `/work/structure` is a GET the live app makes."""
    from laplace.web import project_work_surface
    PROJECT, root = book
    code, kind, body = project_work_surface.handle(
        "/work/structure", {"project": [PROJECT]}, "GET", b"", repo_root=root)
    assert (code, kind) == (200, "application/json")
    result = json.loads(body.decode("utf-8"))
    assert result["identities"], "the HTTP read publishes the tokens the tool door publishes"
    assert set(result["identities"]) == {"plan:" + PROJECT, "plan-file:" + PROJECT,
                                         "selected-edition:" + PROJECT}


def test_every_retained_published_name_carries_the_grammars_expiry_and_a_live_site():
    """A retained published FIELD name is the other half of the shim rule, and had no gate.

    `Shim.__post_init__` refuses an old OPERATION name with no expiry.  Ten of the thirteen
    fields this lane retained were called shims in a code comment and carried no date
    anywhere.  `RETAINED` is the register; this is its gate, and it uses the grammar's OWN
    expiry rule rather than a second copy of it.
    """
    assert len(d.RETAINED) >= 13
    for row in d.RETAINED:
        # the expiry is legal by the grammar's own validator, not by a local regex
        sample = next(iter(d.DOORS.values()))
        g.Shim(old_operation=sample.old_operation, old_verb=sample.old_verb,
               verb=sample.verb, concept=sample.concept,
               guard_to_home=sample.guard_to_home, expiry=row["expiry"])
        assert row["home"] in g.HOME_KINDS, row
        assert row["kind"] in {"duplicate-name", "sole-name", "text-digest"}, row
        assert row["consumer"].strip() and row["deletes"].strip(), row
        sites = d.retained_sites(row, TREE)
        assert sites, "%s claims a publication site that no longer exists" % (row["field"],)
        for site in sites:
            assert site.startswith(row["file"] + ":")
    # one row per retained published name, no duplicates
    fields = [row["field"] for row in d.RETAINED]
    assert len(fields) == len(set(fields))


def test_the_docstring_citation_names_the_line_that_actually_calls_presents():
    """Defect C's CLASS: a file:line written in prose is a checked claim.

    The `presents` docstring cited `writing_style.py:429` -- the handle coverage check -- for a
    call that is at `:434`, and the lane's own guard could not catch it because it asserted
    only that the call's TEXT occurs somewhere in the file.
    """
    cited = re.search(r"``writing_style\.py:(\d+)``", d.presents.__doc__ or "")
    assert cited, "the docstring names its one door by file and line"
    lines = (TREE / "src/laplace/manuscript/writing_style.py").read_text(encoding="utf-8").splitlines()
    number = int(cited.group(1))
    assert "identity_doors.presents(" in lines[number - 1], \
        "writing_style.py:%d is %r, not the presents() call" % (number, lines[number - 1].strip())
