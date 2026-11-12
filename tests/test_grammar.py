"""Proofs the grammar module owes.

Run (from the laplace tree, which is also the tree whose owners the real-home tests read):

    scripts/laplace-python -m pytest -q \
      evidence/WRITING_RECONCILIATION_2026-10-02/grammar/test_grammar.py \
      --basetemp=/tmp/pytest-grammar -p no:cacheprovider
"""
from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
# The grammar's own files (map_verbs.py, mapping.csv, GRAMMAR.md, obtain_census.py).  INSTALL
# step 1 copies them into the worktree and step 3 rewrites this one line to point here, so a
# lane's suite reads NOTHING from the live evidence tree: an edit in the grammar directory is
# a diff at install time, never a silently changed test result in ten lanes at once.
GRAMMAR_DIR = HERE / "grammar_spec"
TREE = Path(__file__).resolve().parents[1]
# The project the real-home proofs read.  Its registry row and its 971 corpus files are
# tracked at HEAD (`git ls-files -- 'synthetics papers/synthetics-foundations' | wc -l`), so
# every git worktree carries it and these proofs do not vacate.  `writing-system-friction-report`
# (round 1's choice) is untracked, which is why three load-bearing tests skipped in a worktree.
PROJECT = "synthetics-foundations"
# The commit the grammar's file:line citations are coordinates IN.  A line number is a
# coordinate in one tree, and the campaign base is the tree the grammar was written against
# (`706a8204`, the commit every lane branches from).  Resolving a citation against the
# LANE's tree makes the two proofs below fail in every lane that edits a cited owner --- and
# worse, it would forbid the campaign's own work: the identity lane's whole job is to DELETE
# the hand comparison `review_surface.py:1860` cites, so a proof demanding that line still
# hold `current != before` demands the cure be absent.  Measured on this merged tree:
# `concepts_surface.py:752` -> :761 (the mint moved, the code is the same), and
# `review_surface.py:1860`'s hand comparison is gone, replaced by `identity_doors.gate`.
# So these two proofs read the base blob out of git, and they still fail --- as they must ---
# when a citation is wrong about the tree it names.
CAMPAIGN_BASE = "706a8204"
# And the cost, stated: resolving a citation against a frozen blob makes the two proofs below
# proofs ABOUT 706a8204.  They go red when a citation in grammar.py is wrong about the tree it
# names; they CANNOT go red when the live code moves, so the merged tree's own coordinates are
# checked by nothing here --- `tools/door_citations.py` and
# tests/test_generated_contract.py::test_every_typed_door_is_an_attributable_coordinate_in_the_campaign_base
# check those, and `help` renders a typed coordinate as `<file>:<line>@706a8204` so a caller is
# never sent to a line in the tree they hold.  This is a shim, so it carries a shim's expiry
# (:400: "a shim with no expiry is the mapping file this grammar refuses").
CAMPAIGN_BASE_EXPIRY = ("retire when Rule.door and HOME_KINDS.source resolve by anchor rather "
                        "than by line, on WRITING-RECONCILIATION replay parity; "
                        "review 2026-11-01")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from laplace.core import grammar as g  # noqa: E402
from laplace.native import declarations as writing_declarations  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_text(rel: str) -> str:
    """One `src/laplace` file's text at CAMPAIGN_BASE, read out of git, not from disk."""
    import subprocess                                             # noqa: PLC0415
    done = subprocess.run(["git", "-C", str(TREE), "show",
                           "%s:src/laplace/%s" % (CAMPAIGN_BASE, rel)],
                          capture_output=True)
    assert done.returncode == 0, (
        "cannot read src/laplace/%s at %s: %s. These proofs resolve the grammar's citations "
        "against the campaign base, so the suite must run inside a checkout that has it."
        % (rel, CAMPAIGN_BASE, done.stderr.decode("utf-8", "replace")[:200]))
    return done.stdout.decode("utf-8", "replace")


def _tree_project() -> str:
    """The tree must carry the project these proofs read.  A missing project is a FAILURE,
    not a skip: a suite that vacates its parity evidence is worse than a red one."""
    registry = TREE / "registry_projects.json"
    assert registry.is_file(), (
        "%s has no registry_projects.json, so no owner read can resolve a project. Install "
        "this suite into a git worktree of the laplace tree." % TREE)
    rows = json.loads(registry.read_text())["projects"]
    assert any(r.get("name") == PROJECT for r in rows), (
        "%s is not registered in %s. These proofs read a project that is tracked at HEAD; "
        "if the registry row was removed, point PROJECT at another tracked project and say "
        "so." % (PROJECT, TREE))
    sys.path.insert(0, str(TREE / "src"))
    return PROJECT


HEX = "a" * 64
HEX2 = "b" * 64


# --------------------------------------------------------------------------- tokens
def test_every_home_kind_round_trips_including_ids_with_colons():
    """mint -> str -> parse is the identity for every declared home kind.

    A real node id contains colons (`def:task-relative-representation`), so a token is
    parsed from both ends.  A token split on every colon would silently truncate the
    busiest home in the system.
    """
    for kind in g.HOME_KINDS:
        for home_id in ("", "project-x", "def:task-relative-representation",
                        "synthetics papers/p/manuscript/chapters/chapter-01.tex",
                        "a:b:c:d"):
            token = g.mint(kind, home_id, HEX)
            back = g.parse(str(token))
            assert back == token, (kind, home_id)
            assert back.kind == kind and back.home_id == home_id
            assert str(token).startswith("rev:%s:" % kind)


def test_owner_spelling_is_normalised_not_refused():
    assert g.mint("plan", "p", "sha256:" + HEX).digest == HEX
    assert g.mint("plan", "p", HEX.upper()).digest == HEX
    assert g.matches(g.mint("plan", "p", "sha256:" + HEX),
                     g.mint("plan", "p", HEX))


def test_a_token_is_refused_when_it_is_not_one():
    with pytest.raises(ValueError):
        g.parse("sha256:" + HEX)
    with pytest.raises(ValueError):
        g.parse("rev:plan:p")
    with pytest.raises(ValueError):
        g.mint("plan", "p", "not-a-digest")
    with pytest.raises(ValueError):
        g.mint("Plan:State", "p", HEX)
    with pytest.raises(ValueError):
        g.mint("no-such-home", "p", HEX)


def test_matches_is_exact_on_the_home():
    a = g.mint("plan", "p", HEX)
    b = g.mint("concept-network", "p", HEX)
    c = g.mint("plan", "q", HEX)
    assert not g.matches(a, b), "two homes with the same digest are not the same home"
    assert not g.matches(a, c)
    assert not g.matches(a, g.mint("plan", "p", HEX2))


# ------------------------------------------------------- identity(): the single mint
def test_two_reads_of_an_unchanged_byte_home_mint_equal_tokens(tmp_path):
    path = tmp_path / "chapter-01.tex"
    path.write_text("\\section{One}\nbody\n", encoding="utf-8")
    home = g.Home("source-file", path.name)
    first = g.identity(home, root=tmp_path)
    second = g.identity(home, root=tmp_path)
    assert first == second
    assert first.digest == g.digest_bytes(path.read_bytes())
    path.write_text("\\section{One}\nbody two\n", encoding="utf-8")
    assert g.identity(home, root=tmp_path) != first, "a changed home must move its token"


def test_recipe_j_is_reproducible_from_the_value_alone():
    value = {"section": "intro", "order": 1, "claim": "c:1"}
    home = g.Home("claim-position", "intro::c:1")
    assert g.identity(home, value=value) == g.identity(home, value=dict(reversed(list(value.items()))))
    assert g.identity(home, value=value).digest == g.digest_canonical_json(value)


def test_the_token_has_exactly_one_digest_form():
    """(d) `pipeline/authoring.py:93-94` numbers the authoring state with a monotone
    integer, compares it at :398-399 and increments it at :434.  Round 1 answered that by
    admitting a second token form, `n<integer>`.  One home per fact and ONE token form:
    the `authoring-state` home mints over the bytes that counter counts (its project's
    `authoring.json`, `_STATE_NAME` at :24, resolved at :63-86), so a counter is not a
    token digest and nothing in the module or the document offers a second form."""
    with pytest.raises(ValueError) as caught:
        g.mint("authoring-state", "p", 141)
    assert "one form" in str(caught.value) and "authoring.json" in str(caught.value)
    for refused in ("n141", "rev:authoring-state:p:n141"):
        with pytest.raises(ValueError):
            g.mint("authoring-state", "p", refused) if ":" not in refused else g.parse(refused)
    with pytest.raises(ValueError):
        g.mint("authoring-state", "p", True)
    assert g.HOME_KINDS["authoring-state"].recipe == "B"
    # the one second form is gone from the module AND from the document it is argued in
    for path in (GRAMMAR_DIR / "grammar.py", GRAMMAR_DIR / "GRAMMAR.md"):
        assert "n<integer>" not in path.read_text(encoding="utf-8"), path.name
    # three aliases, one home: pipeline/authoring.py:386-392
    for alias in ("base_revision", "expected_revision", "revision"):
        assert "authoring-state" in g.GUARD_NAMES[alias], alias


def test_the_counter_home_mints_over_the_bytes_the_counter_counts():
    """The real tree: the token is a sha256 of the file the counter lives in and counts,
    obtained through the owner's own path resolver (pipeline/authoring._state_path)."""
    from laplace.pipeline import authoring as owner
    project = _tree_project()
    home = g.Home("authoring-state", project)
    first = g.identity(home, project=project, root=TREE)
    assert first == g.identity(home, project=project, root=TREE)
    assert len(first.digest) == 64 and not first.digest.startswith("n")
    path, _source = owner._state_path(project, TREE)
    assert path.name == "authoring.json"
    assert first.digest == g.digest_bytes(path.read_bytes())
    # the counter the owner keeps is still the owner's, and still serves the refusal
    assert isinstance(owner.load(project, TREE)["revision"], int)


def test_a_writer_can_mint_the_token_of_bytes_it_has_not_yet_written():
    staged = b"\\section{Two}\n"
    token = g.identity(g.Home("source-file", "chapters/chapter-02.tex"), bytes_=staged)
    assert token.digest == g.digest_bytes(staged)


def test_two_reads_of_an_unchanged_owner_home_mint_equal_tokens():
    """The real tree.  An owner-projection home's token is the owner's own value, read
    twice, with nothing recomputed in this layer."""
    project = _tree_project()
    home = g.Home("concept-network", project)
    first = g.identity(home, project=project, root=TREE)
    second = g.identity(home, project=project, root=TREE)
    assert first == second
    assert len(first.digest) == 64
    plan = g.identity(g.Home("plan", project), project=project, root=TREE)
    assert plan == g.identity(g.Home("plan", project), project=project, root=TREE)
    assert plan.digest != first.digest, "two homes, two values"


def test_the_measured_collapse_three_guard_names_one_home():
    """`base_revision` (concept_change), `base_revision` (logical_plan_change) and
    `expected_concept_revision` (structure_change bind_results) are ONE home.

    concepts_surface.state() MINTS it at :123 and publishes it at :136; logical_plan()
    mints and publishes it at :752; both call the same `_revision(nodes, relations, rows)`
    (concepts_surface.py:20-22) over the same `_network` snapshot, so the three guards
    compare one value.  The audit read them as different homes; the code says one.
    Measured in grammar/home_census.json.

    (Round 1 of this packet cited :130 and :747 for the two mints.  Both were wrong, on
    this packet's largest single claim; `grep -n '_revision(nodes'
    src/laplace/research/concepts.py` gives 123, 223, 752.)
    """
    project = _tree_project()
    from laplace.research import concepts as concepts_surface
    assert concepts_surface.state(project, root=TREE) is not None, (
        "%s publishes no concept state in %s" % (project, TREE))
    state = concepts_surface.state(project, root=TREE)
    plan = concepts_surface.logical_plan(project, root=TREE)
    assert state["revision"] == plan["revision"]
    token = g.mint("concept-network", project, state["revision"])
    assert g.matches(token, g.mint("concept-network", project, plan["revision"]))
    assert g.GUARD_NAMES["expected_concept_revision"] == ("concept-network",)
    assert "concept-network" in g.GUARD_NAMES["base_revision"]
    # and the node's own content is a DIFFERENT home, under its own two names
    assert state["content_revision"] != state["revision"]
    assert g.GUARD_NAMES["mutation_revision"] == ("concept-node",)


# --------------------------------------------------------------------- require()
def test_require_passes_when_every_token_is_current():
    homes = [g.mint("plan", "p", HEX), g.mint("concept-network", "p", HEX2)]
    g.require([str(t) for t in homes], homes)


def test_require_refuses_with_a_resolver_that_is_sufficient():
    sent = g.mint("plan", "p", HEX)
    current = g.mint("plan", "p", HEX2)
    with pytest.raises(g.Refused) as caught:
        g.require([sent], [current])
    refusal = caught.value.refusal
    body = caught.value.response()
    assert body["ok"] is False
    assert body["refused"]["kind"] == "identity-stale"
    assert body["refused"]["homes"][0]["home"] == "plan:p"
    assert body["refused"]["homes"][0]["current_token"] == str(current)
    assert body["refused"]["homes"][0]["read"], "a refusal names the read, not only the field"
    # `needed` IS the cure: retry with it and nothing else.
    g.require(refusal.needed["expected"], [current])


def test_require_names_every_stale_home_not_only_the_first():
    """bind_results requires expected_revision AND expected_concept_revision and the
    refusal names only the one checked first; one writer paid 8 refusals learning that
    (synthesis.md §1.1, project_structure.py:766-767 then :852-855)."""
    sent = [g.mint("plan", "p", HEX), g.mint("concept-network", "p", HEX)]
    current = [g.mint("plan", "p", HEX2), g.mint("concept-network", "p", HEX2)]
    with pytest.raises(g.Refused) as caught:
        g.require([str(t) for t in sent], current)
    homes = {row["home"] for row in caught.value.refusal.homes}
    assert homes == {"plan:p", "concept-network:p"}
    g.require(caught.value.refusal.needed["expected"], current)


def test_require_distinguishes_an_unknown_home_from_a_stale_one():
    with pytest.raises(g.Refused) as caught:
        g.require([str(g.mint("visual-spec", "nope", HEX))],
                  [g.mint("plan", "p", HEX)])
    assert caught.value.refusal.kind == "unknown-home"
    assert caught.value.refusal.homes[0]["current_token"] is None
    assert caught.value.refusal.needed["unresolved"] == ["visual-spec:nope"]


# ---------------------------------------------------------------------- the request
def test_a_concept_may_not_add_a_verb():
    with pytest.raises(ValueError) as caught:
        g.Request(verb="reconcile", concept="plan@plan", target="p")
    assert "verb must be one of" in str(caught.value)
    assert len(g.VERBS) == 9


def test_a_payload_may_not_restate_a_request_field_or_speak_a_guard_name():
    with pytest.raises(ValueError):
        g.Request(verb="change", concept="plan-section@section", target="s",
                  payload={"verb": "change"})
    with pytest.raises(ValueError) as caught:
        g.Request(verb="bind", concept="result@claim", target="c",
                  payload={"expected_concept_revision": HEX})
    assert "old guard name" in str(caught.value)


def test_the_request_shape_is_the_same_six_keys_for_every_verb():
    assert g.Request.FIXED == ("verb", "concept", "target", "expected", "payload", "by")
    for verb in g.VERBS:
        # the option set is closed, so the concept comes from the declared pairs of THIS
        # verb, not from a string: nine verbs, nine real concepts, one request shape
        concept = sorted(c for v, c in g.VERB_CONCEPTS if v == verb)[0]
        request = g.Request(verb=verb, concept=concept, target="intro",
                            expected=(str(g.mint("plan", "p", HEX)),),
                            payload={"title": "Introduction"}, by="eigen")
        assert request.altitude == g.concept_altitude(concept)
        assert request.object == g.concept_object(concept)
        assert request.object in g.HOME_KINDS
        assert len(request.tokens()) == 1


def test_an_unknown_altitude_is_refused():
    with pytest.raises(ValueError):
        g.Request(verb="read", concept="plan-section@sentence", target="s")
    with pytest.raises(ValueError):
        g.Request(verb="read", concept="plan-section", target="s")


# ---------------------------------------------------------- receipt and refusal shapes
def test_the_receipt_distinguishes_applied_from_banked_in_the_status():
    """review_surface.py:1876 returns {ok: true, pending: true, applied: null}; the two
    outcomes differ in a field name, not a status (synthesis.md §1.4), and four
    pending-rewrite rows are still open because of it."""
    request = g.Request(verb="change", concept="prose@paragraph", target="f.tex:10-20",
                        expected=(str(g.mint("source-file", "f.tex", HEX)),),
                        payload={"anchor_text": "exact bytes"}, by="eigen")
    applied = g.Receipt.for_(request, "applied", affected=[g.Affected(
        home="source-file:f.tex", before=str(g.mint("source-file", "f.tex", HEX)),
        after=str(g.mint("source-file", "f.tex", HEX2)))])
    banked = g.Receipt.for_(request, "banked")
    assert applied.response()["outcome"] == "applied"
    assert banked.response()["outcome"] == "banked"
    assert applied.ok and banked.ok
    assert set(applied.response()) == {"ok", "outcome", "affected", "receipt_id",
                                       "banked_row", "next"}
    assert applied.response()["affected"][0]["before"] != applied.response()["affected"][0]["after"]
    with pytest.raises(ValueError):
        g.Receipt(outcome="pending")


def test_the_banked_row_carries_the_verb_and_the_altitude():
    """writing_tools.py:959-971 and :1000-1006 bank the operation name only, so the
    altitude of a completed act is not recoverable without re-parsing the payload."""
    request = g.Request(verb="place", concept="claim-position@section", target="intro::c1")
    row = g.Receipt.for_(request, "applied").banked_row
    assert row["verb"] == "place" and row["concept"] == "claim-position@section"
    assert row["altitude"] == "section" and row["target"] == "intro::c1"


def test_a_created_home_has_no_before_and_a_deleted_home_has_no_after():
    token = str(g.mint("note", "n1", HEX))
    created = g.Affected(home="note:n1", before=None, after=token)
    deleted = g.Affected(home="note:n1", before=token, after=None)
    assert created.before is None and deleted.after is None


def test_the_refusal_shape_carries_the_resolver():
    refusal = g.Refusal(kind="identity-stale",
                        homes=({"home": "plan:p",
                                "current_token": str(g.mint("plan", "p", HEX2))},),
                        needed={"expected": [str(g.mint("plan", "p", HEX2))]},
                        said="plan:p moved")
    body = refusal.response()
    assert set(body) == {"ok", "refused"}
    assert set(body["refused"]) == {"kind", "homes", "needed", "said"}
    assert body["refused"]["needed"]["expected"]
    with pytest.raises(ValueError):
        g.Refusal(kind="revision conflict")


# ------------------------------------------------------------------------- the shim
def test_a_shim_rewrites_an_old_name_and_translates_its_refusal_back():
    shim = g.SHIMS[("structure_change", "operation=bind_results")]
    request = shim.to_request({"project": "p", "operation": "bind_results",
                               "expected_revision": HEX,
                               "expected_concept_revision": HEX2,
                               "bindings": [{"id": "r1"}]}, target="node:1", by="eigen")
    assert request.verb == "bind" and request.concept == "result@claim"
    assert request.payload == {"bindings": [{"id": "r1"}]}
    kinds = {g.parse(t).kind for t in request.expected}
    assert kinds == {"plan", "concept-network"}
    current = [g.mint("plan", "node:1", HEX2),
               g.mint("concept-network", "node:1", HEX)]
    with pytest.raises(g.Refused) as caught:
        g.require(request.expected, current)
    old = shim.from_refusal(caught.value.refusal)
    assert old == {"expected_revision": HEX2, "expected_concept_revision": HEX}
    assert shim.expiry, "a shim with no expiry is the mapping file this grammar refuses"


# ------------------------------------------------------------------ the mapping table
def test_the_mapping_covers_every_audited_verb_and_invents_none():
    mv = _load("map_verbs", GRAMMAR_DIR / "map_verbs.py")
    rows = mv.rows()
    leaf = [r for r in rows if r["level"] == "leaf"]
    nested = [r for r in rows if r["level"] == "nested"]
    assert len(leaf) == 131, "the audit published 131 leaf verbs"
    assert len(nested) == 21, "and 21 sub-verbs one level down"
    assert len([r for r in rows if r["level"] == "status"]) == 3, (
        "and one leaf verb, note_status, is split by the three-valued payload enum its "
        "door enforces (writing_contracts.py:439)")
    # S2 settings-three-ways (2026-10-05): +2 (session_settings, session_settings_change),
    # the tool door's own settings read/change, added after the verb audit the same way
    # `repository action=interface` was.  S3 dispatch-build (2026-10-06): +5, the in-app
    # dispatch door's five operations, all at the one concept task@project.
    assert len([r for r in rows if r["level"] == "extension"]) == 16
    assert {r["verb"] for r in rows} <= set(g.VERBS)
    assert {r["verb"] for r in rows} == set(g.VERBS), "every verb is reached by real work"
    for row in rows:
        assert g.concept_object(row["concept"]) in g.HOME_KINDS, row
        g.concept_altitude(row["concept"])
    for homes in set(mv.GUARD_HOME.values()):
        for home in homes.split("|"):      # one name may accept two homes, both legal
            assert home in g.HOME_KINDS, home
    # every guard name a home declares must be reachable from some audited door
    audited = {guard for _op, guard in mv.GUARD_HOME} | {guard for _op, guard in mv.NOT_A_GUARD}
    for name in g.GUARD_NAMES:
        assert name in audited, "%s is declared on a home but no audited door asks for it" % name


def test_note_status_can_retire_a_note_and_reopen_one():
    """(e) `note_status` sets open | resolved | dismissed (writing_contracts.py:439,
    enforced at pipeline/authoring.py:1191-1192).  §3 removes `comment` from the alphabet
    on the argument that a status-setter is not a `delete` and that the nine verbs give
    the retiring door; round 1 mapped the whole operation to `delete`, so the grammar
    could retire a note and not reopen one --- half the defect, in the row that implements
    the cure."""
    mv = _load("map_verbs", GRAMMAR_DIR / "map_verbs.py")
    split = {r["old_verb"]: (r["verb"], r["concept"], r["because"])
             for r in mv.rows() if r["level"] == "status"}
    assert set(split) == {"status=open", "status=resolved", "status=dismissed"}
    assert split["status=resolved"][:2] == ("delete", "note@claim")
    assert split["status=dismissed"][:2] == ("delete", "note@claim")
    assert split["status=open"][:2] == ("change", "note@claim")
    for discriminator, (_verb, _concept, because) in split.items():
        assert "authoring.py" in because or "writing_contracts.py" in because, discriminator
    for pair in (("change", "note@claim"), ("delete", "note@claim"),
                 ("create", "note@claim")):
        assert pair in g.VERB_CONCEPTS, pair
        assert g.Request(verb=pair[0], concept=pair[1], target="p").verb == pair[0]
    # §3's argument and the rows that implement it say the same thing
    prose = (GRAMMAR_DIR / "GRAMMAR.md").read_text(encoding="utf-8")
    assert "`change note@claim` reopens" in prose
    assert '{"enum": ["open", "resolved", "dismissed"]}' in prose
    for status in ("open", "resolved", "dismissed"):
        assert "`status=%s`" % status in prose, status


def test_the_rendered_table_matches_the_rows():
    mv = _load("map_verbs", GRAMMAR_DIR / "map_verbs.py")
    rendered = (GRAMMAR_DIR / "GRAMMAR.md").read_text(encoding="utf-8")
    assert mv.BEGIN in rendered and mv.END in rendered
    body = rendered.split(mv.BEGIN, 1)[1].split(mv.END, 1)[0]
    rows = mv.rows()
    # header + separator + one line per row
    assert body.count("\n|") - 2 == len(rows), "the render is stale; re-run map_verbs.py"
    home_body = rendered.split(mv.HOME_BEGIN, 1)[1].split(mv.HOME_END, 1)[0]
    assert home_body.count("\n|") - 2 == len(g.HOME_KINDS), "re-run map_verbs.py"
    assert "`%s` / `%s`" % (rows[0]["operation"], rows[0]["old_verb"]) in body
    csv_rows = list(csv.DictReader((GRAMMAR_DIR / "mapping.csv").open()))
    assert len(csv_rows) == len(rows)


def test_every_home_kind_states_one_mint_rule_and_one_read():
    for kind, home in g.HOME_KINDS.items():
        assert home.bytes, kind
        assert home.source, kind
        assert home.recipe in {"B", "J", "O"}, kind
        assert home.id_is, kind
        if home.guards_today:
            assert home.read, "a guarded home must name the read its token comes from"


# ------------------------------------------------- identity(): the declared partition
@pytest.mark.parametrize("with_provenance", [False, True])
def test_the_declared_obtain_partition_is_what_really_happens(tmp_path, monkeypatch, with_provenance):
    """`MINT_STATUS` says, per home kind, whether `identity(home)` can obtain a token from
    the home alone.  This runs all 58 against a real project and compares.

    Round 1 of this packet declared one minting rule per kind in a Markdown table while
    `identity()` raised NotImplementedError for 34 of 59 --- a description beside a check.
    The cure is two-sided: 17 more reads wired, and this test, so the declaration cannot
    drift from the behaviour again.
    """
    project = _tree_project()
    # Exercise both declared states explicitly. A full checkout carries an author
    # provenance ledger that a sparse checkout may omit; neither should decide
    # which branch of this identity proof happens to run.
    from laplace.manuscript import writing_style
    provenance = tmp_path / "evidence" / "voice.json"
    provenance.parent.mkdir()
    if with_provenance:
        provenance.write_text(json.dumps({"read": [], "purpose": "Identity fixture"}))
    monkeypatch.setattr(writing_style, "_provenance_path",
                        lambda root, profile_path, content: (provenance, tmp_path))
    oc = _load("obtain_census", GRAMMAR_DIR / "obtain_census.py")
    result = oc.census(project, TREE)
    assert result["mismatch"] == [], result["mismatch"]
    minted = {kind for kind, _ in result["minted"]}
    unwired = {kind for kind, _ in result["unwired"]}
    absent = {kind: why for kind, why in result["absent"]}
    # Every declared read either minted from this tracked project or names the exact
    # fixture capability that is absent. Every caller-value home remains unwired. This
    # is the bidirectional partition; a threshold could fall while hiding which home did.
    assert minted | set(absent) == set(g.OBTAINABLE)
    assert minted.isdisjoint(absent)
    assert unwired == set(g.CALLER_VALUE)
    expected_absent = {"relation", "reference"} | (set() if with_provenance else {"style-provenance"})
    assert set(absent) == expected_absent, absent
    assert "0 rows" in absent["relation"]
    assert "published no associations" in absent["reference"]
    if with_provenance:
        assert "style-provenance" in minted
        import hashlib
        expected = g.mint("style-provenance", project, hashlib.sha256(provenance.read_bytes()).hexdigest())
        assert dict(result["minted"])["style-provenance"] == str(expected)
        assert writing_style.state(project, repo_root=TREE)["provenance"]["status"] == "RECORDED"
    else:
        assert "published no provenance.revision" in absent["style-provenance"]
        assert writing_style.state(project, repo_root=TREE)["provenance"]["status"] == "MISSING"
    assert len(g.OBTAINABLE) == 41 and len(g.CALLER_VALUE) == 18, (
        len(g.OBTAINABLE), len(g.CALLER_VALUE))
    assert len(g.OBTAINABLE) + len(g.CALLER_VALUE) == len(g.HOME_KINDS) == 60


def test_every_home_that_needs_a_caller_value_says_what_would_close_it():
    """A lane must be able to tell from the SPEC which homes it can obtain a token for, and
    for the others what exactly is missing.  No `closes` sentence, no residual."""
    for kind in g.CALLER_VALUE:
        home = g.HOME_KINDS[kind]
        assert home.closes.strip(), kind
        assert len(home.closes) > 60, (kind, home.closes)
    for kind in g.OBTAINABLE:
        assert not g.HOME_KINDS[kind].closes, (
            "%s is obtainable, so it must not carry a `what would close it`" % kind)
    rendered = (GRAMMAR_DIR / "GRAMMAR.md").read_text(encoding="utf-8")
    mv = _load("map_verbs", GRAMMAR_DIR / "map_verbs.py")
    body = rendered.split(mv.OBTAIN_BEGIN, 1)[1].split(mv.OBTAIN_END, 1)[0]
    assert body.count("\n|") - 2 == len(g.CALLER_VALUE), "re-run map_verbs.py"
    for kind in g.CALLER_VALUE:
        assert "| `%s` |" % kind in body, kind


def test_the_declared_owner_reads_agree_with_the_declared_recipes():
    for kind, spec in g.OWNER_READS.items():
        assert kind in g.HOME_KINDS, kind
        assert spec.form == g.HOME_KINDS[kind].recipe, (kind, spec.form)
        assert spec.args in g._CALLS, (kind, spec.args)
        assert spec.module.startswith("laplace."), kind
    wired_bytes = {k for k, h in g.HOME_KINDS.items()
                   if h.recipe == "B" and k in g.OWNER_READS}
    # A byte home is read from disk.  The home id is normally the path; for the one home
    # whose owner numbers it with a counter instead of publishing a digest, the owner's own
    # resolver names the file and the digest is still of that file's exact bytes.
    assert wired_bytes == {"authoring-state"}, wired_bytes
    assert g.OWNER_READS["authoring-state"].form == "B"
    assert "authoring.json" in g.HOME_KINDS["authoring-state"].bytes


def test_the_recipe_counts_this_module_states_are_the_counts_it_has():
    counts = {r: sum(1 for h in g.HOME_KINDS.values() if h.recipe == r) for r in "BJO"}
    assert counts == {"B": 12, "J": 23, "O": 25}, counts
    assert sum(counts.values()) == len(g.HOME_KINDS) == 60
    assert g.__doc__ is not None and "25 homes)" in g.__doc__ and "23 recipe-J" in g.__doc__
    assert not [h for h in g.HOME_KINDS.values() if h.recipe not in {"B", "J", "O"}]


# ---------------------------------------------- guards name the door that compares them
def test_every_declared_guard_names_the_door_that_compares_it():
    """A guard name on a home is a claim that some door compares that name against that
    home.  Either the audit's verb matrix attributes it (map_verbs.GUARD_HOME) or the home
    carries the file:line of the comparison, which this test opens and reads.

    This is what round 1 lacked: `visual` declared `expected_source_revision` while both
    doors that compare that name compare the SELECTED EDITION, and the coverage test only
    checked that each guard NAME was audited, never that its home was ever compared.
    """
    mv = _load("map_verbs", GRAMMAR_DIR / "map_verbs.py")
    attributed = {(guard, home)
                  for (_op, guard), value in mv.GUARD_HOME.items()
                  for home in value.split("|")}
    for kind, home in g.HOME_KINDS.items():
        for guard in home.guards_today:
            doors = [d for d in home.guard_doors if d.split("=", 1)[0] == guard]
            assert (guard, kind) in attributed or doors, (
                "%s declares the guard %r and no audited door attributes it to this home: "
                "either drop the guard or cite the door that compares it" % (kind, guard))
            for door in doors:
                cited = door.split("=", 1)[1]
                match = re.search(r"([a-z_]+(?:/[a-z_]+)?\.py):(\d+)", cited)
                assert match, (kind, guard, cited)
                # the coordinate names CAMPAIGN_BASE (the coordinate law): the cited file is read there, where it
                # exists under this relative path even after the 2026-10-21 physical-home move relocated it
                lines = _base_text(match.group(1)).split("\n")
                number = int(match.group(2))
                assert 0 < number <= len(lines), (kind, guard, number, len(lines))
                window = "\n".join(lines[max(0, number - 2):number + 1])
                assert guard in window or "!=" in window or "==" in window, (
                    kind, guard, number, window)


def test_one_set_of_bytes_has_exactly_one_home_kind():
    """(c) Round 1 had two kinds over one read --- `plan` and a `plan`-state alias, both
    minted by `identity()`, both reproducible, and `require` answered a present and
    byte-identically unchanged home with `unknown-home` and an empty `needed`, i.e. a
    refusal that lied and carried no cure.  The alias blessing (`same_value_as`) is gone
    with it, and this is the check that keeps it gone: no two home kinds declare the same
    owner read, so a second kind cannot be minted over one set of bytes."""
    assert not hasattr(g.HOME_KINDS["plan"], "same_value_as")
    seen: dict[tuple, str] = {}
    for kind, spec in g.OWNER_READS.items():
        key = (spec.module, spec.func, spec.path, spec.by_id, spec.payload)
        assert key not in seen, (
            "%s and %s declare the same owner read %r: one set of bytes, two home kinds, "
            "which is the defect this grammar exists to end" % (kind, seen.get(key), key))
        seen[key] = kind
    # the one home the plan doors compare, and the bytes column says what the read returns
    assert g.GUARD_NAMES["expected_revision"][:1] == ("plan",)
    assert "plan" in g.GUARD_NAMES["expected_plan_revision"]
    assert "{authority, sections, gaps}" in g.HOME_KINDS["plan"].bytes
    assert "NOT the whole projection_plan.json" in g.HOME_KINDS["plan"].bytes
    assert g.GUARD_NAMES["expected_source_revision"] == ("selected-edition",)


def test_no_door_compares_a_recipe_j_home():
    """(a) §1's parity claim, as a check instead of a sentence.  A recipe-J token is a
    digest no owner publishes, so a replay has nothing to compare it against; if a door
    guarded such a home, §9's harness lane would be citing a false claim.  Round 1 of this
    packet declared `supersedes` --- the id of a note, not an identity --- on the recipe-J
    `note` home while §1 said no J home carried a guard."""
    offenders = [(name, home) for name, homes in g.GUARD_NAMES.items() for home in homes
                 if g.HOME_KINDS[home].recipe == "J"]
    assert not offenders, (
        "these guards name a recipe-J home, whose digest no owner publishes: %r. Either "
        "the home is not J, or the field is payload content and not an identity" % offenders)
    assert g.HOME_KINDS["note"].recipe == "J" and g.HOME_KINDS["note"].guards_today == ()
    assert "supersedes" not in g.GUARD_NAMES


def test_the_two_guard_tables_agree_both_ways():
    """(b) `grammar.GUARD_NAMES` (from the homes) and `map_verbs.GUARD_HOME` (from the
    audit) are the two tables every later lane builds from, and round 1 shipped
    `base_revision` in three homes in one and two in the other: a dispatch lane honouring
    the mapping would have put a sha256 of a note row in `expected:[]` for a door that
    compares the authoring counter."""
    mv = _load("map_verbs", GRAMMAR_DIR / "map_verbs.py")
    for (op, guard), value in mv.GUARD_HOME.items():
        for home in value.split("|"):
            assert home in g.GUARD_NAMES.get(guard, ()), (
                "the mapping gives %s/%s the home %r, which that home does not declare "
                "as a guard of its own" % (op, guard, home))
    attributed = {(guard, home) for (_op, guard), value in mv.GUARD_HOME.items()
                  for home in value.split("|")}
    for guard, homes in g.GUARD_NAMES.items():
        for home in homes:
            doors = [d for d in g.HOME_KINDS[home].guard_doors
                     if d.split("=", 1)[0] == guard]
            assert (guard, home) in attributed or doors, (guard, home)
    assert mv.GUARD_HOME[("note_status", "base_revision")] == "authoring-state"
    assert ("note_status", "base_revision") not in mv.NOT_A_GUARD


def test_the_cited_lines_are_the_lines_they_claim():
    """A bounded citation sweep against CAMPAIGN_BASE, the tree these coordinates name.
    Round 1's two line numbers on the headline claim were both wrong, and a reader
    re-deriving the collapse checks them first.

    The mechanism's own expiry is gated here rather than in a test of its own, because
    `test_the_install_block_copies_every_file_the_proofs_read` checks INSTALL's promised test
    count against this file and a lane may not edit the grammar packet's GRAMMAR.md."""
    # the base-resolution shim passes the gate the grammar puts on every other shim
    assert re.search(r"20\d\d-\d\d-\d\d", CAMPAIGN_BASE_EXPIRY)
    assert "parity" in CAMPAIGN_BASE_EXPIRY.lower()
    def line(rel: str, number: int) -> str:
        return _base_text(rel).split("\n")[number - 1]
    assert "_revision(nodes,rels,rows)" in line("concepts_surface.py", 123)
    assert '"revision":_revision(nodes,relations,rows)' in line("concepts_surface.py", 752)
    # the round-1 judgement asked for :1859 here; `grep -n 'current != before'` says
    # :1860 in the live tree, in a worktree and in the HEAD blob.  The test states the
    # measured line, so a future reader cannot be sent to the wrong one again.
    assert "current != before" in line("review_surface.py", 1860)
    assert "def _revision" in line("pipeline/authoring.py", 439)
    assert "expected_source_revision" in line("visuals_surface.py", 349)
    assert "expected_source_revision" in line("project_structure.py", 777)
    assert "read_text" in line("manuscript_blocks.py", 166)
    # and every file:line any home cites exists and is in range
    for kind, home in g.HOME_KINDS.items():
        for rel, number in re.findall(r"([a-z_]+(?:/[a-z_]+)?\.py):(\d+)", home.source):
            if not (TREE / "src" / "laplace" / rel).is_file():
                continue                   # a module named without a src/laplace file
            total = len(_base_text(rel).split("\n"))
            assert 0 < int(number) <= total, (kind, rel, number, total)


# ------------------------------------------------------- the shim is gated, not described
def test_a_shim_cannot_be_built_without_an_expiry_a_verb_and_real_homes():
    ok = dict(old_operation="structure_change", old_verb="operation=bind_results",
              verb="bind", concept="result@claim",
              guard_to_home={"expected_revision": "plan"},
              expiry="retire on WRITING-RECONCILIATION replay parity; review 2026-11-01")
    assert g.Shim(**ok).expiry
    for bad, why in [
        ({"expiry": ""}, "an empty expiry"),
        ({"expiry": "never"}, "an expiry with no date and no parity run"),
        ({"expiry": "2026-11-01"}, "a date with no parity run"),
        ({"verb": "frobnicate"}, "a verb outside the nine"),
        ({"concept": "nope@nope"}, "an unknown altitude"),
        ({"concept": "totally-made-up@claim"}, "an object that is not a home kind"),
        ({"guard_to_home": {"expected_revision": "no-such-home"}}, "a home that is not one"),
        ({"old_operation": ""}, "no old operation to retire"),
    ]:
        with pytest.raises(ValueError):
            g.Shim(**{**ok, **bad})
    # the `a|b` spelling one door really accepts stays legal
    assert g.Shim(**{**ok, "guard_to_home": {"expected_plan_revision":
                                             "plan|plan-file"}}).expiry


def test_every_registered_shim_passes_its_own_gate():
    for key, shim in g.SHIMS.items():
        assert shim.verb in g.VERBS and key == (shim.old_operation, shim.old_verb)
        assert re.search(r"20\d\d-\d\d-\d\d", shim.expiry)
        assert "parity" in shim.expiry.lower()


# ------------------------------------------- the (verb, concept) option set is closed
def test_an_invented_concept_object_is_refused():
    with pytest.raises(ValueError) as caught:
        g.Request(verb="read", concept="totally-made-up-thing@claim", target="p")
    assert "home kinds" in str(caught.value)
    with pytest.raises(ValueError):          # a real home kind, an undeclared concept
        g.Request(verb="read", concept="turn@run", target="p")
    with pytest.raises(ValueError):          # a declared concept, an undeclared pair
        g.Request(verb="delete", concept="contract@project", target="p")


def test_the_closed_set_is_the_mapping_rows_and_a_lane_extends_it_on_the_record():
    mv = _load("map_verbs", GRAMMAR_DIR / "map_verbs.py")
    rows = mv.rows()
    assert g.CONCEPTS == {r["concept"] for r in rows}
    assert g.VERB_CONCEPTS == {(r["verb"], r["concept"]) for r in rows}
    # S2 settings-three-ways (2026-10-05): +1 pair (change, turn@project).
    # S3 dispatch-build (2026-10-06): +1 CONCEPT and +3 pairs.  task@project's object half is
    # `task`, already one of the 58 home kinds (grammar.py:466), and `project` is already an
    # altitude -- but task@project was not yet a concept of the generated set, so unlike S2
    # this moves BOTH numbers.  The pin is moved, never dropped: it is how a bare string is
    # caught, and it moved in the same commit as the five EXTENSIONS rows that caused it.
    assert len(g.CONCEPTS) == 68 and len(g.VERB_CONCEPTS) == 114
    for verb, concept in sorted(g.VERB_CONCEPTS)[:12]:
        assert g.Request(verb=verb, concept=concept, target="t").concept == concept
    # a lane adds a pair with the measurement that demands it, never a bare string
    with pytest.raises(ValueError):
        g.declare_pair("read", "turn@run", because="   ")
    try:
        g.declare_pair("read", "turn@run", because="the turn lane reads one turn's context")
        assert g.declared_pair("read", "turn@run")
        assert g.Request(verb="read", concept="turn@run", target="t").object == "turn"
    finally:
        g.ADDED_PAIRS.pop(("read", "turn@run"), None)


def test_the_coverage_counts_in_the_document_are_spliced_not_typed():
    mv = _load("map_verbs", GRAMMAR_DIR / "map_verbs.py")
    rendered = (GRAMMAR_DIR / "GRAMMAR.md").read_text(encoding="utf-8")
    body = rendered.split(mv.COUNT_BEGIN, 1)[1].split(mv.COUNT_END, 1)[0]
    assert body.strip() == mv.coverage_paragraph().strip(), "re-run map_verbs.py"
    counts = mv.coverage_counts()
    assert counts["guard_homes"] == len(
        {h for value in mv.GUARD_HOME.values() for h in value.split("|")})
    assert counts["obtainable"] == len(g.OBTAINABLE)
    # the hand-typed "19 home kinds reached by today's guards" of round 1 is gone
    assert "19 home kinds reached" not in rendered


def test_a_prefixed_token_round_trips_with_its_home_id_intact():
    """`parse` ate the owner's `sha256:` prefix INTO THE HOME ID.

    `rev:plan:proj:sha256:<hex>` returned home id `proj:sha256` - a home that does not
    exist - with the digest normalised correctly and nothing refused, so a refusal built
    from such a token named the wrong home: the misdirected resolver `needed` exists to
    prevent (round-2 finding (d) of the dispatch lane).  The segment before a 64-hex tail
    belongs to the digest, and `mint` reserves it so the rule is lossless both ways.
    """
    hexd = "b" * 64
    ids = ["proj",                                     # a whole-project home
           "",                                         # a home with no id
           "::style",                                  # not per project
           "proj::chapters/chapter-01.tex",            # a path
           "proj::def:task-relative-representation",   # a node id WITH colons
           "proj::blob:sha256:deadbeef",               # the prefix INSIDE the id
           "proj::notes:sha256-v2",                    # and as part of a segment
           "proj::SHA256"]                             # not the reserved spelling
    for home_id in ids:
        ours = g.mint("plan", home_id, hexd)
        owners = "rev:plan:%s:sha256:%s" % (home_id, hexd)
        for raw in (str(ours), owners):
            got = g.parse(raw)
            assert got.home_id == home_id, (raw, got.home_id)
            assert got.digest == hexd
            assert g.parse(str(got)) == got           # the round trip is closed
        assert g.matches(owners, str(ours))           # and one spelling matches the other
    # the reserved segment: no token may exist whose id ends in it, in either direction
    with pytest.raises(ValueError) as caught:
        g.mint("plan", "proj:sha256", hexd)
    assert "sha256" in str(caught.value) and "prefix" in str(caught.value)
    with pytest.raises(ValueError):
        g.mint("plan", "proj::sha256", hexd)
    # a prefixed token of a REAL home still resolves to that home, which is the point
    assert g.parse("rev:plan:proj:sha256:%s" % hexd).home == g.Home("plan", "proj")


def test_the_one_colliding_owner_key_has_one_declared_carrier():
    """`logical_plan_change connect` declares its own top-level `target`
    (writing_contracts.py:607) and `Request` refuses a payload key that restates a request
    field, so that route could not express its payload at all.  The grammar names which
    side wins ONCE, so four build lanes do not invent four spellings (finding (c))."""
    assert set(g.PAYLOAD_CARRIERS) == {"target", "by"}
    carrier, because = g.PAYLOAD_CARRIERS["target"]
    assert carrier == "edge_target" and g.carrier_for("target") == carrier
    assert g.owner_key_for(carrier) == "target" and g.owner_key_for("relation") is None
    assert "writing_contracts.py:607" in because
    for key, (name, reason) in g.PAYLOAD_CARRIERS.items():
        assert key in g.Request.FIXED                   # it collides with a request field
        assert name not in g.Request.FIXED              # the carrier does not
        assert name not in g.GUARD_NAMES                # and is not an old guard name
        assert reason.strip()
    owner_payload = {"operation": "connect", "source": "claim:result",
                     "target": "def:basis", "relation": "prerequisite"}
    with pytest.raises(ValueError) as caught:
        g.Request(verb="bind", concept="relation@relation", target="p::rel-1",
                  payload=owner_payload)
    assert "edge_target" in str(caught.value)           # the refusal names the carrier
    carried = g.to_payload(owner_payload)
    request = g.Request(verb="bind", concept="relation@relation", target="p::rel-1",
                        payload=carried)
    assert carried["edge_target"] == "def:basis" and "target" not in carried
    assert g.to_owner_payload(request.payload) == owner_payload   # the owner's own bytes
    with pytest.raises(ValueError):                     # never two spellings at once
        g.to_payload({"target": "a", "edge_target": "b"})
    # the document names the carrier and its reason, so a lane reading §5 learns it there
    prose = (GRAMMAR_DIR / "GRAMMAR.md").read_text(encoding="utf-8")
    assert "edge_target" in prose and "writing_contracts.py:607" in prose


def test_the_grammar_declares_which_doors_take_by():
    """`by` is a request field because a note could not record its writer, and the owners
    do four different things with it.  The grammar declares which, and `by_census.py`
    re-measures the declaration against the live owners (finding (e))."""
    _tree_project()
    census = _load("by_census", GRAMMAR_DIR / "by_census.py")
    report = census.census(TREE, GRAMMAR_DIR / "mapping.csv")
    assert report["disagreements"] == [], report["disagreements"]
    # S2 settings-three-ways (2026-10-05): +2 operations (session_settings,
    # session_settings_change).  S3 dispatch-build (2026-10-06): +5 dispatch operations.
    assert report["operations"] == 82
    # the four statuses, each with a citation, and `by` is NOT usable at an owner today
    assert set(report["by_status"].values()) <= set(writing_declarations.BY_STATUSES)
    assert report["counts"].get("declared", 0) == 0
    assert report["overwritten"] == ["concept_change", "logical_plan_change",
                                     "writing_style_change", "writing_style_profile_change"]
    assert writing_declarations.by_at("structure_change")[0] == "refused"
    assert writing_declarations.by_at("note")[0] == "dropped"               # the 140-notes defect itself
    for operation, (status, reason) in writing_declarations.BY_AT_DOORS.items():
        assert status in writing_declarations.BY_STATUSES
        assert census.cited_sites(reason), operation
    # and the document says it, so the contract lane reads it with the rest of §3
    prose = (GRAMMAR_DIR / "GRAMMAR.md").read_text(encoding="utf-8")
    assert "writing_tools.py:309" in prose and "eigen:session" in prose


def test_the_install_block_copies_every_file_the_proofs_read():
    """Round 2's INSTALL copied four of the five files this suite reads and promised a test
    count that was three short, so every build lane's first install failed on
    `FileNotFoundError: tests/grammar_spec/grammar.py` (finding (a)).  The promise is now
    checked against this file instead of typed beside it."""
    prose = (GRAMMAR_DIR / "GRAMMAR.md").read_text(encoding="utf-8")
    install = prose.split("## 8. INSTALL", 1)[1].split("\n## ", 1)[0]
    source = Path(__file__).read_text(encoding="utf-8")
    # a name only counts when it IS a file of the packet: this test's own regex literal
    # appears in `source` too, and the install cannot copy a regex.
    needs = {name for name in re.findall(r'GRAMMAR_DIR / "([^"]+)"', source)
             if (GRAMMAR_DIR / name).is_file()}
    assert "grammar.py" in needs                     # the file round 2 left behind
    assert len(needs) >= 5
    copied = set(re.findall(r"\$G/([A-Za-z0-9_.]+)", install))
    missing = sorted(needs - copied)
    assert not missing, ("INSTALL does not copy %r, which this suite reads from the "
                         "installed grammar_spec directory" % (missing,))
    assert "verb_matrix.csv" in install               # map_verbs.py's row source
    count = len(re.findall(r"^def test_", source, re.M))
    assert ("%d passed" % count) in install, (
        "INSTALL promises a different number than this suite's %d tests" % count)
