"""The evolution consumer (pipeline.evolution_consumer) — DRAFT-ONLY.

Every test runs against tmp_path fixtures and a hand-built minimal net; none
reads a live manuscript tree. The dry-run rehearsal registers a throwaway
corpus (through the ``register_project`` fixture door — a registry data row under
tmp_path) whose ledger lives entirely under tmp_path, so execute() dry-runs
against a tiny copy and the real repo is never touched.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from laplace.pipeline import adjudicate as adj
from laplace.pipeline import evolution_consumer as consumer

FIXTURE_CORPUS = "consumer-fixture"


# ---------------------------------------------------------------------------
# a minimal graded net: p(0) <- a(1) <- s(2)
# ---------------------------------------------------------------------------

@pytest.fixture
def net() -> dict:
    return {
        "nodes": {
            "p": {"kind": "postulate", "essence": "a postulate"},
            "a": {"kind": "lemma", "essence": "a lemma"},
            "s": {"kind": "result", "essence": "a result"},
        },
        "edge_index": {"p": ["p"], "a": ["a", "p"], "s": ["s", "a"]},
        "postulates": {"p"},
        "spine": [],
        "reach": {}, "lenses": {}, "root": "p",
    }


import itertools as _itertools
_ID_SEQ = _itertools.count(1)


def _uid(prefix: str) -> str:
    """A collision-free record id for fixtures. :func:`adjudicate._rid` stamps
    the trailing segment with microseconds (``%f``), which COLLIDE under the
    Windows clock's granularity when records are built in a tight loop — two
    ``make_*_intent`` calls in the same tick share an id, and id-keyed
    retirement (``supersedes`` / dir-slug tail) then mis-fires. A monotonic
    sequence in that trailing segment keeps every fixture record distinct while
    preserving the real id shape the joins read (date isolated, tail unique)."""
    return f"{prefix}-20260714-000000-{next(_ID_SEQ):06d}"


def _intent(kind: str, node: str = "s", note: str = "some note") -> dict:
    return adj.make_conceptric_intent(node, kind, note=note, project=FIXTURE_CORPUS,
                                      rec_id=_uid("CI"))


def _ledger(records: list[dict]) -> list[dict]:
    return records


# ---------------------------------------------------------------------------
# open_intents — reuse of the substrate_queue matching
# ---------------------------------------------------------------------------

def test_open_intents_filters_superseded_and_kind():
    keep = _intent("essence-wrong")
    revoked = _intent("edge-missing")
    revoke = adj.make_intent_revocation(revoked["id"])
    calib = adj.make_calibration_intent("eq-unused")   # different record kind
    recs = _ledger([keep, revoked, revoke, calib])
    got = consumer.open_intents(recs)
    assert [r["id"] for r in got] == [keep["id"]]


# ---------------------------------------------------------------------------
# the projection-intent (plan-altitude) sibling: shape, live visibility, filter
# ---------------------------------------------------------------------------

def test_make_projection_intent_shape_and_live_visibility():
    pi = adj.make_projection_intent(
        "FB-9", "DEMOTE", object_kind="section", object_key="N7",
        note="fold into N6", finding_kind="novelty-overbroad", project=FIXTURE_CORPUS)
    assert pi["record"] == adj.PROJECTION_INTENT
    assert pi["target"] == "FB-9" and pi["scope"] == "plan"
    assert pi["verb"] == "DEMOTE" and pi["object"] == {"kind": "section", "sid": "N7"}
    assert pi["payload"] == {"note": "fold into N6", "finding_kind": "novelty-overbroad"}
    assert pi["status"] == "open" and pi["kind"] == adj.PROJECTION_INTENT
    # an out-of-vocabulary verb normalises to CUT (the safe default)
    assert adj.make_projection_intent("FB-9", "NUKE")["verb"] == "CUT"
    # live() visibility + supersession retires it exactly like its siblings
    assert [r["id"] for r in adj.live([pi])] == [pi["id"]]
    rev = adj.make_intent_revocation(pi["id"])
    assert adj.live([pi, rev]) and pi["id"] not in {r["id"] for r in adj.live([pi, rev])}


def test_open_projection_intents_filters_superseded_and_kind():
    keep = adj.make_projection_intent("FB-1", "CUT", object_kind="meta",
                                      object_key="scope", project=FIXTURE_CORPUS,
                                      rec_id=_uid("PI"))
    revoked = adj.make_projection_intent("FB-2", "SPLIT", object_kind="section",
                                         object_key="N3", project=FIXTURE_CORPUS,
                                         rec_id=_uid("PI"))
    revoke = adj.make_intent_revocation(revoked["id"])
    concept = _intent("essence-wrong")                 # a DIFFERENT record kind
    recs = _ledger([keep, revoked, revoke, concept])
    got = consumer.open_projection_intents(recs)
    assert [r["id"] for r in got] == [keep["id"]]
    # the conceptric reader never sees the projection-intents, and vice-versa
    assert [r["id"] for r in consumer.open_intents(recs)] == [concept["id"]]


def test_draft_plan_proposals_is_draft_only_markdown(tmp_path):
    intents = [
        adj.make_projection_intent("FB-1", "CUT", object_kind="meta",
                                   object_key="non_claims", note="drop the aside",
                                   finding_kind="novelty-overbroad",
                                   project=FIXTURE_CORPUS),
        adj.make_projection_intent("FB-2", "DEMOTE", object_kind="section",
                                   object_key="N7", project=FIXTURE_CORPUS),
    ]
    res = consumer.draft_plan_proposals(intents, FIXTURE_CORPUS, tmp_path)
    md = Path(res["path"])
    assert md.name == "PLAN_PROPOSALS.md" and md.is_file()
    body = md.read_text(encoding="utf-8")
    # the read side is a PREVIEW now; the apply side (apply_plan_proposals) is named,
    # and the draft-only supersede is scoped to the plan-altitude path (C3.5).
    assert "PREVIEW" in body and "apply_plan_proposals" in body
    assert "conceptric-intents" in body            # draft-only still holds for those
    assert "`CUT` meta:`non_claims`" in body and "`DEMOTE` section:`N7`" in body
    # each intent renders a PROPOSED plan op (advisory, awaiting adjudication)
    assert body.count("PROPOSED plan op:") == 2
    props = res["proposals"]
    assert {p["proposed_op"] for p in props} == {"set-meta", "reorder-sections"}
    # the empty queue still writes the sheet (absence never reads as a stale queue)
    empty = consumer.draft_plan_proposals([], FIXTURE_CORPUS, tmp_path / "e")
    assert Path(empty["path"]).is_file() and empty["proposals"] == []


# ---------------------------------------------------------------------------
# the mechanical grade rule (pure)
# ---------------------------------------------------------------------------

def test_mint_grade_modal_floor_ties_down():
    assert consumer.mint_grade([2, 2, 3]) == 2            # mode 2
    assert consumer.mint_grade([1, 3]) == 1              # tie → DOWN
    assert consumer.mint_grade([], default_grade=4) == 4  # no neighbours → default
    # floor: the mode can never fall below the minimum neighbour (mode ∈ set)
    assert consumer.mint_grade([0, 5, 5]) == 5


def test_min_live_grade_is_bounded_default(net):
    assert consumer.min_live_grade(net) == 0   # the postulate floor
    assert consumer.min_live_grade(None) == 0


# ---------------------------------------------------------------------------
# draft_contract → op templates + load_contract/plan_records round-trip
# ---------------------------------------------------------------------------

def test_essence_wrong_drafts_edit_essence(net, tmp_path):
    intent = _intent("essence-wrong", note="the true essence")
    res = consumer.draft_contract(intent, net, "unregistered", tmp_path,
                                  repo_root=tmp_path)
    assert not res["escalated"]
    evo = Path(res["evolution_dir"])
    # (a) load_contract parses it cold (fresh module import)
    ev = importlib.reload(importlib.import_module("laplace.pipeline.evolve"))
    contract = ev.load_contract(evo)
    # (b) plan_records produces the expected op kind
    records = ev.plan_records(contract)
    assert res["op_kinds"] == {"edit-essence": 1}
    assert [r["kind"] for r in records] == ["edit-essence"]
    assert records[0]["node"] == "s" and records[0]["value"] == "the true essence"
    assert (evo / "RATIFY.md").is_file()


def test_edge_missing_drafts_add_edge_from_note(net, tmp_path):
    intent = _intent("edge-missing", node="s", note="missing derives-from p")
    res = consumer.draft_contract(intent, net, "unregistered", tmp_path,
                                  repo_root=tmp_path)
    assert not res["escalated"]
    ev = importlib.import_module("laplace.pipeline.evolve")
    records = ev.plan_records(ev.load_contract(res["evolution_dir"]))
    assert res["op_kinds"] == {"add-edge": 1}
    assert (records[0]["node"], records[0]["target"]) == ("s", "p")


def test_content_missing_drafts_mint_and_grade(net, tmp_path):
    intent = _intent("content-missing", node="s", note="a bridging step")
    res = consumer.draft_contract(intent, net, "unregistered", tmp_path,
                                  repo_root=tmp_path)
    assert not res["escalated"]
    ev = importlib.import_module("laplace.pipeline.evolve")
    contract = ev.load_contract(res["evolution_dir"])
    records = ev.plan_records(contract)
    kinds = res["op_kinds"]
    # add-node + its set-projection seed (first edge rides the birth record)
    assert kinds == {"add-node": 1, "set-projection": 1}
    mint = contract["mints"][0]
    assert mint["edges"] == ["s"] and mint["node_kind"] == "derivation-step"
    # the grade rule: sole neighbour is s (grade 2) → mint grade 2
    assert res["grade"] == 2 and mint["grade"] == 2
    # advisory only — the grade key does not perturb the planned records
    assert not any("grade" in r for r in records)


def test_content_missing_mint_id_from_explicit_token(net):
    """Regression (bite-zero, CI-20260710-163703-732221): the mint id is the
    explicit ``mint <prefix>:<slug>`` token in the note — the author's RATIFIED
    identity — and the node_kind is read off the id prefix. The 2026-07-10 session
    instead slugged the WHOLE note under ``derivation:``, producing the mis-named
    ``derivation:r2-referee-first-live-fire-2026-07-10-intent-onl``. Feed the
    verbatim note and assert the identity now derives correctly."""
    note = ("R2 (referee, first live fire 2026-07-10, intent-only seal): the "
            "forward-stable/backward-ill-posed structure of Gaussian smoothing "
            "across scales — used verbatim as 'scale space' at "
            "irf:heat-kernel-scale-space (N3-p16, N8-p1) — is the founding result "
            "of linear scale-space theory (Witkin 1983; Koenderink 1984; "
            "Lindeberg), inherited from signal processing, and cited NOWHERE "
            "(confirmed absent from references.bib). content-missing: mint "
            "ref:scale-space-theory (Witkin/Koenderink/Lindeberg) and wire "
            "irf:heat-kernel-scale-space -> it, so the substrate carries the "
            "inheritance the prose uses.")
    intent = _intent("content-missing", node="irf:heat-kernel-scale-space",
                     note=note)
    sections, _detail = consumer._draft_sections(intent, net)
    mint = sections["mints"][0]
    assert mint["id"] == "ref:scale-space-theory"
    assert mint["node_kind"] == "citation"
    # the pure helper, exercised directly
    assert consumer._mint_id_and_kind(note, "irf:heat-kernel-scale-space") == (
        "ref:scale-space-theory", "citation")
    # the fallback preserves the prior behaviour when no explicit token is present
    assert consumer._mint_id_and_kind("a bridging step", "s") == (
        "derivation:a-bridging-step", "derivation-step")


# ---------------------------------------------------------------------------
# (e) unmapped intents → no contract, escalation listed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["other", "grade-wrong"])
def test_unmapped_intent_escalates(net, tmp_path, kind):
    intent = _intent(kind, note="whatever")
    res = consumer.draft_contract(intent, net, "unregistered", tmp_path,
                                  repo_root=tmp_path)
    assert res["escalated"] and "evolution_dir" not in res
    assert not (tmp_path / "evolutions").exists()


def test_edge_missing_without_target_escalates(net, tmp_path):
    intent = _intent("edge-missing", node="s", note="no node id here")
    res = consumer.draft_contract(intent, net, "unregistered", tmp_path,
                                  repo_root=tmp_path)
    assert res["escalated"] and "no derivable target" in res["reason"]


# ---------------------------------------------------------------------------
# (c) dry-run rehearsal round-trips exact on a minimal fixture corpus
# ---------------------------------------------------------------------------

@pytest.fixture
def registered_corpus(tmp_path, register_project):
    """Register a throwaway conceptric whose ledger lives under tmp_path, so
    evolve.execute dry-runs against a tiny copy and never reads the real repo."""
    register_project(tmp_path, FIXTURE_CORPUS)
    ledger = tmp_path / "corpus_friction" / f"{FIXTURE_CORPUS}.jsonl"
    ledger.parent.mkdir(parents=True)
    seed = [{"id": "RW-seed-1", "ts": "2026-07-10T00:00:00", "kind": "add-node",
             "node": "s", "node_kind": "result", "essence": "a result", "by": "t"},
            {"id": "RW-seed-2", "ts": "2026-07-10T00:00:01", "kind": "add-node",
             "node": "a", "node_kind": "lemma", "essence": "a lemma", "by": "t"}]
    ledger.write_text("\n".join(json.dumps(r) for r in seed) + "\n",
                      encoding="utf-8")
    return tmp_path


def test_dry_run_rehearsal_round_trips_exact(net, registered_corpus, tmp_path):
    repo_root = registered_corpus
    out = tmp_path / "out"
    intent = _intent("content-missing", node="s", note="a bridging step")
    res = consumer.draft_contract(intent, net, FIXTURE_CORPUS, out,
                                  repo_root=repo_root)
    assert not res["escalated"]
    assert res["rehearsal_ok"] is True

    # the ledger under tmp is untouched by the dry run (draft-only)
    ledger = repo_root / "corpus_friction" / f"{FIXTURE_CORPUS}.jsonl"
    before = ledger.read_bytes()
    ev = importlib.import_module("laplace.pipeline.evolve")
    rep = ev.execute(FIXTURE_CORPUS, res["evolution_dir"], repo_root=repo_root)
    assert rep["ok"] and rep["round_trip_exact"]
    assert rep["added"] == [consumer._draft_sections(intent, net)[0]["mints"][0]["id"]]
    assert ledger.read_bytes() == before

    # RATIFY.md carries the rehearsal + the post-apply supersede design
    ratify = (Path(res["evolution_dir"]) / "RATIFY.md").read_text(encoding="utf-8")
    assert "make_intent_revocation" in ratify
    assert intent["id"] in ratify
    assert "Gate PREVIEW" in ratify
    for gate in consumer.SEVEN_GATES:
        assert gate in ratify


# ---------------------------------------------------------------------------
# (f) structural draft-only guarantee: the source can never request an apply
# ---------------------------------------------------------------------------

def test_consumer_source_has_no_apply_path():
    src = Path(consumer.__file__).read_text(encoding="utf-8")
    assert "dry_run=False" not in src
    assert "dry_run=True" not in src          # never passes the flag at all
    assert "subprocess" not in src
    assert "os.system" not in src
    assert "--apply" not in src


def test_cli_source_has_no_apply_flag():
    cli = (Path(consumer.__file__).resolve().parents[3]
           / "scripts" / "consume_intents.py")
    src = cli.read_text(encoding="utf-8")
    assert "--apply" not in src
    assert "dry_run=False" not in src


# ---------------------------------------------------------------------------
# the batch driver over a feedback ledger
# ---------------------------------------------------------------------------

def test_consume_batches_drafted_and_escalated(net, tmp_path):
    md = tmp_path / "manuscript"
    fb = md / "feedback"
    fb.mkdir(parents=True)
    intents = [_intent("essence-wrong", note="fix me"),
               _intent("content-missing", node="s", note="add me"),
               _intent("other", note="dunno"),
               _intent("grade-wrong", node="s", note="regrade")]
    (fb / "feedback.jsonl").write_text(
        "\n".join(json.dumps(r) for r in intents) + "\n", encoding="utf-8")

    summary = consumer.consume(md, "unregistered", net, tmp_path / "out",
                               repo_root=tmp_path)
    assert len(summary["drafted"]) == 2
    assert len(summary["escalated"]) == 2
    assert {d["intent"] for d in summary["drafted"]} == {"essence-wrong",
                                                         "content-missing"}
    assert {e["intent"] for e in summary["escalated"]} == {"other", "grade-wrong"}


def test_same_kind_same_node_same_day_intents_never_collide(net, tmp_path):
    """The judge's overwrite probe, banked: two content-missing intents on the
    same node the same day must draft into DISTINCT dirs, and an existing
    contract dir is refused, never clobbered."""
    md = tmp_path / "manuscript"
    fb = md / "feedback"
    fb.mkdir(parents=True)
    intents = [_intent("content-missing", node="s", note="first gap"),
               _intent("content-missing", node="s", note="second gap")]
    (fb / "feedback.jsonl").write_text(
        "\n".join(json.dumps(r) for r in intents) + "\n", encoding="utf-8")

    summary = consumer.consume(md, "unregistered", net, tmp_path / "out",
                               repo_root=tmp_path)
    drafted = summary["drafted"]
    assert len(drafted) == 2
    dirs = {d["evolution_dir"] for d in drafted}
    assert len(dirs) == 2                                  # distinct dirs
    for d in dirs:
        assert (Path(d) / "evolution_plan.json").is_file() # both survive

    # refuse-to-clobber: re-consuming the same open intents escalates, bytes kept
    before = {d: (Path(d) / "evolution_plan.json").read_bytes() for d in dirs}
    summary2 = consumer.consume(md, "unregistered", net, tmp_path / "out",
                                repo_root=tmp_path)
    assert len(summary2["escalated"]) == 2 and summary2["drafted"] == []
    for d, raw in before.items():
        assert (Path(d) / "evolution_plan.json").read_bytes() == raw


# ---------------------------------------------------------------------------
# C3.5 — the APPLY BRIDGE (Fork 8 ruled: PV-20260713T221204Z-weld-apply-bridge)
# auto-derive-and-apply with retrospective ledger correction. Draft-only is
# EXPLICITLY SUPERSEDED for the projection-intent path only; conceptric-intents
# stay draft-only. FAIL-CLOSED: derivable => real plan.meta delta + revocation +
# delta record; un-derivable => zero mutation + still open + needs-author;
# idempotent re-run => no double-apply; unresolved object => refused.
# ---------------------------------------------------------------------------

APPLY_CORPUS = "apply-bridge-fixture"


@pytest.fixture
def plan_corpus(tmp_path, monkeypatch):
    """A registered-corpus stand-in: a real projection_plan.json under tmp, with
    shared_ui.plan_path_for pointed at it so the LIVE storyboard plan-ledger doors
    (plan_write / reduce / validate) run against tmp — never a real manuscript."""
    plan = {
        "meta": {"project": APPLY_CORPUS, "scope": "the original scope",
                 "weighting": "even across sections", "target_dir": ""},
        "sections": [{"id": "S1", "title": "Intro", "job": "open",
                      "nodes_in_order": ["a"], "beats": [], "figures": [], "refs": []}],
        "appendices": [],
    }
    p = tmp_path / "projection_plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    from laplace.web import shared_ui as su
    monkeypatch.setattr(su, "plan_path_for", lambda corpus: p)
    return p, tmp_path


def _fb_write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _read_ledger(path: Path) -> list[dict]:
    from laplace.pipeline.ledger import read_jsonl
    return read_jsonl(path)


def test_apply_bridge_applies_derivable_meta_and_retires_the_intent(plan_corpus, tmp_path):
    p, _ = plan_corpus
    fb = tmp_path / "feedback" / "feedback.jsonl"
    intent = adj.make_projection_intent("FB-w", "DEMOTE", object_kind="meta",
                                        object_key="weighting", note="lower it",
                                        finding_kind="emphasis-mismatch",
                                        project=APPLY_CORPUS, rec_id=_uid("PI"))
    _fb_write(fb, [intent])

    res = consumer.apply_plan_proposals(tmp_path, APPLY_CORPUS, by="gerard",
                                        feedback_path=fb)
    assert [a["intent"] for a in res["applied"]] == [intent["id"]]
    assert res["needs_author"] == []

    # (i) a REAL plan.meta delta visible via the storyboard reduce
    from laplace.manuscript import storyboard as sb
    plan = sb._load_plan(APPLY_CORPUS)[1]
    got = plan["meta"]["weighting"]
    assert isinstance(got, dict)
    assert got["value"] == "even across sections"            # prior preserved (non-lossy)
    assert got["projection_ruling"]["verb"] == "DEMOTE"
    assert got["projection_ruling"]["intent"] == intent["id"]

    # (ii) a revocation row + (iii) a delta-carrying ratified-operation record
    recs = _read_ledger(fb)
    revokes = [r for r in recs if r.get("record") == adj.INTENT_REVOKE
               and r.get("supersedes") == intent["id"]]
    ops = [r for r in recs if r.get("record") == adj.RATIFIED_OPERATION
           and r.get("target") == intent["id"]]
    assert len(revokes) == 1
    assert len(ops) == 1 and ops[0]["outcome"] == "applied"
    assert ops[0]["op_kind"] == "set-meta"
    assert ops[0]["delta"]["before"] == "even across sections"
    assert ops[0]["delta"]["after"] == got                   # genuine before/after

    # the intent is retired from the open queue (the revoke supersedes it)
    assert consumer.open_projection_intents(recs) == []


def test_apply_bridge_underivable_ops_apply_nothing_and_stay_open(plan_corpus, tmp_path):
    p, _ = plan_corpus
    before_bytes = p.read_bytes()
    fb = tmp_path / "feedback" / "feedback.jsonl"
    restart = adj.make_projection_intent("FB-r", "RESTART", object_kind="meta",
                                         object_key="scope", project=APPLY_CORPUS,
                                         rec_id=_uid("PI"))          # no mechanical transform
    split = adj.make_projection_intent("FB-s", "SPLIT", object_kind="section",
                                       object_key="S1", project=APPLY_CORPUS,
                                       rec_id=_uid("PI"))            # content judgment
    section = adj.make_projection_intent("FB-c", "CUT", object_kind="section",
                                         object_key="S1", project=APPLY_CORPUS,
                                         rec_id=_uid("PI"))          # section op needs author
    _fb_write(fb, [restart, split, section])

    res = consumer.apply_plan_proposals(tmp_path, APPLY_CORPUS, by="gerard",
                                        feedback_path=fb)
    assert res["applied"] == []
    na = {n["intent"]: n["reason"] for n in res["needs_author"]}
    assert set(na) == {restart["id"], split["id"], section["id"]}
    assert na[restart["id"]].startswith("no-mechanical-transform")
    assert na[split["id"]].startswith("no-mechanical-transform")
    assert na[section["id"]].startswith("content-judgment")

    # ZERO mutation: the plan file is byte-identical, no ledger side-effect on the plan
    assert p.read_bytes() == before_bytes

    recs = _read_ledger(fb)
    # each un-derivable intent is recorded needs-author and STAYS open
    na_recs = [r for r in recs if r.get("record") == adj.RATIFIED_OPERATION
               and r.get("outcome") == "needs-author"]
    assert {r["target"] for r in na_recs} == {restart["id"], split["id"], section["id"]}
    assert all(r.get("delta") is None for r in na_recs)
    still_open = {r["id"] for r in consumer.open_projection_intents(recs)}
    assert still_open == {restart["id"], split["id"], section["id"]}


@pytest.mark.parametrize("bad_plan", [
    {"meta": ["not", "a", "mapping"], "sections": []},      # meta not a mapping
    {"meta": {"project": APPLY_CORPUS}, "sections": [1, 2]},  # a non-dict section
])
def test_apply_bridge_fails_closed_on_a_structurally_defective_plan(
        plan_corpus, tmp_path, bad_plan):
    """A JSON-shaped but NOT plan-shaped live plan makes the C3.4 resolver door
    (`restart_reader._plan_target_namespaces`) RAISE. The apply bridge reuses that
    door, so the raise must be caught and degrade to EMPTY namespaces: nothing is
    applied to a plan the resolver cannot read, every intent stays open, and the
    ledger carries the loud `plan-unreadable` basis instead of an untyped
    AttributeError escaping and taking the whole apply run with it."""
    p, _ = plan_corpus
    p.write_text(json.dumps(bad_plan), encoding="utf-8")
    before_bytes = p.read_bytes()
    fb = tmp_path / "feedback" / "feedback.jsonl"
    intent = adj.make_projection_intent("FB-w", "DEMOTE", object_kind="meta",
                                        object_key="weighting", project=APPLY_CORPUS,
                                        rec_id=_uid("PI"))
    _fb_write(fb, [intent])

    res = consumer.apply_plan_proposals(tmp_path, APPLY_CORPUS, by="gerard",
                                        feedback_path=fb)   # must NOT raise
    assert res["applied"] == []
    from laplace.pipeline.readers import restart_reader as rr
    assert [n["intent"] for n in res["needs_author"]] == [intent["id"]]
    assert res["needs_author"][0]["reason"].startswith(rr.PLAN_UNREADABLE_BASIS)

    assert p.read_bytes() == before_bytes                    # ZERO mutation
    recs = _read_ledger(fb)
    na = [r for r in recs if r.get("record") == adj.RATIFIED_OPERATION
          and r.get("outcome") == "needs-author"]
    assert len(na) == 1 and na[0]["target"] == intent["id"]
    assert na[0]["delta"] is None
    assert na[0]["reason"].startswith(rr.PLAN_UNREADABLE_BASIS)
    # the intent is KEPT OPEN — no revocation was written
    assert [r["id"] for r in consumer.open_projection_intents(recs)] == [intent["id"]]
    assert not [r for r in recs if r.get("record") == adj.INTENT_REVOKE]


def test_apply_bridge_refuses_an_unresolved_object(plan_corpus, tmp_path):
    p, _ = plan_corpus
    before_bytes = p.read_bytes()
    fb = tmp_path / "feedback" / "feedback.jsonl"
    # object_key names no live plan.meta key AND no section id (C3.4 flag)
    ghost = adj.make_projection_intent("FB-g", "DEMOTE", object_kind="meta",
                                       object_key="no_such_meta_key",
                                       project=APPLY_CORPUS, rec_id=_uid("PI"))
    _fb_write(fb, [ghost])

    res = consumer.apply_plan_proposals(tmp_path, APPLY_CORPUS, by="gerard",
                                        feedback_path=fb)
    assert res["applied"] == []
    assert [n["reason"] for n in res["needs_author"]] == ["unresolved-object"]
    assert p.read_bytes() == before_bytes                    # refused → nothing applied
    recs = _read_ledger(fb)
    assert ghost["id"] in {r["id"] for r in consumer.open_projection_intents(recs)}


def test_apply_bridge_is_idempotent_on_rerun(plan_corpus, tmp_path):
    p, _ = plan_corpus
    fb = tmp_path / "feedback" / "feedback.jsonl"
    derivable = adj.make_projection_intent("FB-w", "REORDER", object_kind="meta",
                                           object_key="weighting", project=APPLY_CORPUS,
                                           rec_id=_uid("PI"))
    stuck = adj.make_projection_intent("FB-r", "RESTART", object_kind="meta",
                                       object_key="scope", project=APPLY_CORPUS,
                                       rec_id=_uid("PI"))
    _fb_write(fb, [derivable, stuck])

    r1 = consumer.apply_plan_proposals(tmp_path, APPLY_CORPUS, by="gerard",
                                       feedback_path=fb)
    assert [a["intent"] for a in r1["applied"]] == [derivable["id"]]
    from laplace.manuscript import storyboard as sb
    after_first = sb._load_plan(APPLY_CORPUS)[1]["meta"]["weighting"]

    r2 = consumer.apply_plan_proposals(tmp_path, APPLY_CORPUS, by="gerard",
                                       feedback_path=fb)
    # no double-apply: the revoked intent is gone from the open queue
    assert r2["applied"] == []
    after_second = sb._load_plan(APPLY_CORPUS)[1]["meta"]["weighting"]
    assert after_second == after_first                       # the meta key is not re-wrapped

    recs = _read_ledger(fb)
    revokes = [r for r in recs if r.get("record") == adj.INTENT_REVOKE
               and r.get("supersedes") == derivable["id"]]
    assert len(revokes) == 1                                 # retired exactly once
    ops = [r for r in recs if r.get("record") == adj.RATIFIED_OPERATION
           and r.get("target") == derivable["id"] and r.get("outcome") == "applied"]
    assert len(ops) == 1
    # the still-open un-derivable intent is NOT re-recorded (dedup by intent+reason)
    na = [r for r in recs if r.get("record") == adj.RATIFIED_OPERATION
          and r.get("target") == stuck["id"]]
    assert len(na) == 1


def test_conceptric_intents_stay_draft_only_and_supersede_is_named(plan_corpus, tmp_path, net):
    """The repeal is SCOPED: a conceptric-intent never reaches the apply bridge
    (apply_plan_proposals reads only projection-intents), and the three draft-only
    enshrinement sites now name the supersede with the PV id."""
    fb = tmp_path / "feedback" / "feedback.jsonl"
    concept = _intent("essence-wrong", note="still a draft")
    _fb_write(fb, [concept])
    res = consumer.apply_plan_proposals(tmp_path, APPLY_CORPUS, by="gerard",
                                        feedback_path=fb)
    assert res["applied"] == [] and res["needs_author"] == []   # conceptric ignored here
    # the conceptric-intent is untouched (still open for the DRAFT-ONLY contract path)
    assert [r["id"] for r in consumer.open_intents(_read_ledger(fb))] == [concept["id"]]

    # the supersede is named at the three enshrinement sites (grep the source)
    src = Path(consumer.__file__).read_text(encoding="utf-8")
    assert src.count("PV-20260713T221204Z-weld-apply-bridge") >= 3
    assert "fork-law amendment" in src and "conceptric-intents" in src
    # the conceptric draft-only guarantee still holds structurally
    assert "dry_run=False" not in src and "subprocess" not in src


# ---------------------------------------------------------------------------
# the mined substrate (the growth leg's quarry law, 2026-07-19): a source-delta
# intent carrying gap.quote seeds the mint's ESSENCE from the lost span — the
# conceptric grows from HIS text, and the RATIFY sheet shows the substance.
# ---------------------------------------------------------------------------


def test_content_missing_mint_essence_seeds_from_the_gap_quote(tmp_path):
    intent = _intent("content-missing", node="s", note="[ungrounded] linkage dropped")
    intent["gap"] = {"quote": "The lost argument move, verbatim from his draft.",
                     "gap_class": "ungrounded"}
    sections, detail = consumer._draft_sections(intent, None)
    mint = sections["mints"][0]
    assert mint["essence_seed"] == "The lost argument move, verbatim from his draft."
    assert detail["mined_substrate"] == mint["essence_seed"]
    assert "gap.quote" in detail["substrate_provenance"]


def test_content_missing_without_quote_falls_back_to_the_note():
    intent = _intent("content-missing", node="s", note="[ungrounded] linkage dropped")
    sections, detail = consumer._draft_sections(intent, None)
    assert sections["mints"][0]["essence_seed"] == "[ungrounded] linkage dropped"
    assert "mined_substrate" not in detail


def test_ratify_sheet_surfaces_the_mined_substrate():
    intent = _intent("content-missing", node="s", note="[ungrounded] linkage dropped")
    intent["gap"] = {"quote": "The lost span."}
    sections, detail = consumer._draft_sections(intent, None)
    md = consumer._ratify_md(intent, FIXTURE_CORPUS, {"mints": sections["mints"]},
                             [], detail, consumer._gate_preview(sections),
                             {"ok": None, "skipped": True, "reason": "test"})
    assert "Mined substrate" in md and "The lost span." in md


# ---------------------------------------------------------------------------
# the RATIFY-queue class repairs (his ruling 2026-07-19, "fix and ratify"):
# D1 — content-derived mint ids (a shared generic note must never collide a
# batch); D2 — an explicit section_target on the intent outranks derivation.
# ---------------------------------------------------------------------------


def test_mint_ids_derive_from_the_quote_never_collide():
    a = _intent("content-missing", node="s", note="[ungrounded] the source makes an argument MOVE")
    b = _intent("content-missing", node="s", note="[ungrounded] the source makes an argument MOVE")
    a["gap"] = {"quote": "Amplitude estimation at Heisenberg scaling reduces the shot overhead."}
    b["gap"] = {"quote": "The readout does not collapse the system register."}
    (sa, _), (sb, _) = consumer._draft_sections(a, None), consumer._draft_sections(b, None)
    ida, idb = sa["mints"][0]["id"], sb["mints"][0]["id"]
    assert ida != idb, "same generic note collided two mints (defect D1)"
    assert "amplitude" in ida and "readout" in idb


def test_explicit_mint_token_still_outranks_the_quote():
    a = _intent("content-missing", node="s", note="mint ref:his-named-id — [ungrounded] x")
    a["gap"] = {"quote": "Some substrate."}
    sections, _ = consumer._draft_sections(a, None)
    assert sections["mints"][0]["id"] == "ref:his-named-id"


def test_section_target_on_the_intent_outranks_derivation():
    a = _intent("content-missing", node="s", note="[ungrounded] x")
    a["gap"] = {"quote": "Some substrate."}
    a["section_target"] = "sec:s4"
    sections, detail = consumer._draft_sections(a, None)
    assert sections["mints"][0]["section_target"] == "sec:s4"
    assert detail["section_ref"] == "sec:s4"
