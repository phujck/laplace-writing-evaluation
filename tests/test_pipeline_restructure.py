"""The restructure operator's GOLDEN MASTER — a living golden of the LATEST
restructure event.

The golden pins three banked artifacts to each other: the pre-apply freeze
(``manuscript/archive/restructure_preboard_<stamp>/projection_plan.json``), the
banked target arc (``evolutions/.../target_arc.json`` — rulings as declarative
operator inputs), and the restructure's committed output. ``plan_from_arc``
must regrow that output from the frozen pre-state exactly. The output is the
AUTHORED BASE of the plan-write ledger (``projection_plan.base.json``) once the
storyboard has snapshotted one: post-restructure board ops (stage C structural
resolution among them) reduce over the base into the live
``projection_plan.json``, so the live file legitimately drifts from the arc
output while the base stays the frozen event. Each properly frozen restructure
re-bakes this golden by construction; earlier events (the 2026-07-08
general-first restructure, whose transcribed arc lived inline here) remain in
git history.

Current event: the 2026-07-09 NF figure-architecture swap (identity seeding;
figure placement from fresh fig:nf* mints' section_refs + figure_overrides;
section node lists unchanged except NA2 dropping its retired figure entries).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.pipeline import restructure
from laplace.pipeline.schema import section_nodes

REPO = Path(__file__).resolve().parents[1]
MS = REPO / "synthetics papers" / "subset-sum-itqde" / "manuscript"
SNAP = MS / "archive" / "restructure_preboard_2026-07-09_032111"

#: The banked arc IS the golden input (rulings as declarative operator data).
GOLDEN_ARC = json.loads(
    (MS / "evolutions" / "judgement_reprojection_2026-07-08" / "target_arc.json")
    .read_text(encoding="utf-8"))

#: A pure literal for the spine_payloads unit test (the 2026-07-08 spine order;
#: the payload builder is exercised against data, independent of the live arc,
#: whose current event leaves the spine untouched and declares no spine block).
_SPINE_ORDER = [
    "res:itqde-spectral-readout", "thm:fourier-reconstruction-identity",
    "thm:staircase-cumulant-identities", "res:lambda-sweep-reuse",
    "res:ancilla-interferometric-front-end", "res:native-hamiltonian-execution",
    "res:two-barriers-separated", "res:subset-sum-spectral-encoding",
    "thm:hardy-littlewood-collapse", "res:perturbative-rescue",
    "res:degeneracy-cartography-single-family", "res:operationally-dense-target-window",
    "res:window-verdict", "res:sensing-grade-structural", "res:planted-trade-family",
]

@pytest.fixture(scope="module")
def pre_plan() -> dict:
    return json.loads((SNAP / "projection_plan.json").read_text(encoding="utf-8"))


#: The byte-frozen committed output of the current event (git d7a26fa, the
#: 2026-07-09 NF figure-architecture landing — the plan as the restructure apply
#: committed it, BEFORE any post-restructure board op). This is the durable golden
#: expected: plan_from_arc(pre_plan, GOLDEN_ARC, net) must regrow it exactly.
GOLDEN_COMMITTED = REPO / "tests" / "fixtures" / "restructure_golden" / "committed_plan.json"


@pytest.fixture(scope="module")
def committed_plan() -> dict:
    """The restructure's committed output — read ONLY from the byte-frozen golden
    fixture (``tests/fixtures/restructure_golden/committed_plan.json``).

    History: this fixture once *preferred* the plan-write ledger base
    (``projection_plan.base.json``) when present, on the premise that the base was
    gitignored runtime cache, never committed. That premise is DEAD. Since the
    surfacing audit (ed93aec, 2026-07-10 — ``.gitignore`` declares the base the
    C-hinge's committed PROVENANCE, canon that must survive a clone, NOT an ignore
    pattern) and the SSG desk-ruling respine snapshot (85527b4, 2026-07-13),
    ``projection_plan.base.json`` is committed canon and is byte-identical to the
    drifted live ``projection_plan.json`` (N2 = 14 nodes, the respine set; not the
    9-node frozen arc output). It is therefore exactly the "drifted live plan" this
    golden must NEVER compare against — the same reason the earlier
    ``else the live projection_plan.json`` fallback was already dropped. So the base
    preference is removed and the golden reads the frozen fixture only, hermetic
    against runtime C-hinge drift. ``plan_from_arc`` still reproduces this frozen
    fixture (its logic + arc + pre-plan snapshot are all pinned to the 2026-07-09 NF
    event), so no re-freeze is needed; base.json stays intact as canon. See
    PV-20260714-golden-drift."""
    return json.loads(GOLDEN_COMMITTED.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def net() -> dict:
    troot = ci.resolve_corpus(REPO, "subset-sum-itqde")
    return ci.corpus_network(troot, repo_root=REPO, name="subset-sum-itqde")


# ---------------------------------------------------------------------------
# (a)+(b) the golden master: pre-op snapshot + arc → the committed plan
# ---------------------------------------------------------------------------

def test_golden_arc_reproduces_committed_plan(pre_plan, committed_plan, net):
    new_plan = restructure.plan_from_arc(pre_plan, GOLDEN_ARC, net)
    got = {s["id"]: s for s in new_plan["sections"]}
    want = {s["id"]: s for s in committed_plan["sections"]}
    # granular first, so a regression names its axis
    assert [s["id"] for s in new_plan["sections"]] == [s["id"] for s in committed_plan["sections"]]
    for sid in want:
        assert got[sid]["title"] == want[sid]["title"], sid
        assert set(got[sid]["nodes_in_order"]) == set(want[sid]["nodes_in_order"]), sid
        assert sorted(got[sid]["refs"]) == sorted(want[sid]["refs"]), sid
        assert set(got[sid]["figures"]) == set(want[sid]["figures"]), sid
        assert got[sid]["beats"] == want[sid]["beats"], sid
    assert new_plan["appendices"] == committed_plan["appendices"]
    # the capstone: FULL dict equality on everything the RESTRUCTURE produced.
    # The committed plan's meta has since gained the typed policy fields via the
    # sanctioned set-meta migration (essence_hygiene_2026-07-08) - policy layered
    # AFTER the restructure, not arc data - so those keys are compared excluded
    # and their post-migration truth asserted explicitly.
    MIGRATED_META = {"workflow_modes", "postures", "voice_refs", "gate_refs",
                     "builder_contract", "voice"}
    got_meta = {k: v for k, v in new_plan["meta"].items() if k not in MIGRATED_META}
    want_meta = {k: v for k, v in committed_plan["meta"].items() if k not in MIGRATED_META}
    assert got_meta == want_meta
    assert committed_plan["meta"].get("workflow_modes")            # migration landed
    assert committed_plan["meta"].get("builder_contract") is None  # wall nulled
    assert dict(new_plan, meta=got_meta) == dict(committed_plan, meta=want_meta)


def test_golden_node_order_reproduces_exactly(pre_plan, committed_plan, net):
    # stronger than the declared membership invariant: the first-seen document
    # order rule regrows the committed per-section sequences byte-for-byte
    new_plan = restructure.plan_from_arc(pre_plan, GOLDEN_ARC, net)
    for got, want in zip(new_plan["sections"], committed_plan["sections"]):
        assert got["nodes_in_order"] == want["nodes_in_order"], got["id"]


def test_golden_conservation(pre_plan, net):
    new_plan = restructure.plan_from_arc(pre_plan, GOLDEN_ARC, net)

    def content(plan):
        return {n for s in plan["sections"] + plan.get("appendices", [])
                for n in section_nodes(s) if not n.startswith("fig:")}

    landed: list[str] = []
    for s in new_plan["sections"]:
        landed.extend(s["nodes_in_order"])
    assert len(landed) == len(set(landed))            # exactly one home each
    assert content(new_plan) == content(pre_plan)     # zero strays, zero inventions
    # the figure swap is exactly the documented NF event: seven mints in,
    # twelve retired projections out (fig:f5-dp-price carried; NA2 untouched)
    old_figs = {f for s in pre_plan["sections"] for f in s.get("figures") or []}
    new_figs = {f for s in new_plan["sections"] for f in s.get("figures") or []}
    assert new_figs - old_figs == {f"fig:nf{k}" for k in range(1, 8)}
    assert "fig:f5-dp-price" in (new_figs & old_figs)
    assert len(old_figs - new_figs) == 12


def test_golden_spine_payloads():
    # pure-function unit: the payload builder against a literal spine block
    # (the live arc's current event leaves the spine untouched and carries none)
    literal = {"sections": [], "spine": {
        "order": _SPINE_ORDER, "unset": ["goal:perturbation-assisted-itqde"]}}
    payloads = restructure.spine_payloads(literal)
    sets = [p for p in payloads if p["kind"] == "set-spine"]
    unsets = [p for p in payloads if p["kind"] == "unset-spine"]
    assert [p["node"] for p in sets] == _SPINE_ORDER
    assert [p["ord"] for p in sets] == list(range(15))
    assert all("narrative" not in p for p in sets)     # omitted → preserved on fold
    assert [p["node"] for p in unsets] == ["goal:perturbation-assisted-itqde"]
    assert all(p["by"] == "restructure" for p in payloads)
    assert restructure.spine_payloads(GOLDEN_ARC) == []   # this event: no spine ops


# ---------------------------------------------------------------------------
# (c) conservation on a synthetic merge+split fixture
# ---------------------------------------------------------------------------

def _synth_plan() -> dict:
    return {
        "meta": {"target_dir": "wp"},
        "sections": [
            {"id": "A", "title": "Alpha", "job": "", "notes": "", "refs": ["r1"],
             "beats": ["res:a1"], "nodes_in_order": ["res:a1", "def:a2", "def:shared"],
             "figures": ["fig:fa"]},
            {"id": "B", "title": "Beta", "job": "", "notes": "", "refs": ["r2"],
             "beats": [], "nodes_in_order": ["def:shared", "res:b1"], "figures": []},
            {"id": "C", "title": "Gamma", "job": "", "notes": "", "refs": ["r3", "r4"],
             "beats": ["res:c1"], "nodes_in_order": ["res:c1", "def:c2", "def:c3"],
             "figures": ["fig:fc"]},
        ],
        "appendices": [
            {"id": "A1", "title": "Appx", "job": "", "notes": "", "refs": ["r9"],
             "beats": [], "nodes_in_order": ["def:shared", "thm:app1"], "figures": []},
        ],
    }


def _synth_arc() -> dict:
    return {
        "sections": [
            {"id": "M", "title": "Merged", "seed_from": ["A", "B"]},
            {"id": "X", "title": "Xray", "seed_from": ["C"]},
            {"id": "Y", "title": "Yankee", "seed_from": ["C"]},   # declared split
        ],
        "overrides": {"res:c1": "X", "def:c2": "Y"},
        "figure_overrides": {"fig:fc": "X", "fig:new": "Y"},
        "park": ["def:c3"],
    }


def test_synthetic_merge_split_conservation():
    plan = _synth_plan()
    new_plan = restructure.plan_from_arc(plan, _synth_arc(), {})
    by_id = {s["id"]: s for s in new_plan["sections"]}
    # merge: A+B pooled, the duplicate def:shared collapses to its first home
    assert by_id["M"]["nodes_in_order"] == ["res:a1", "def:a2", "def:shared", "res:b1"]
    # split: C's nodes land only by explicit ruling; the park is honoured
    assert by_id["X"]["nodes_in_order"] == ["res:c1"]
    assert by_id["Y"]["nodes_in_order"] == ["def:c2"]
    landed = [n for s in new_plan["sections"] for n in s["nodes_in_order"]]
    assert len(landed) == len(set(landed))
    old_unique = {n for s in plan["sections"] for n in section_nodes(s)}
    assert old_unique - set(landed) == {"def:c3"}      # parked, nothing else astray
    # out-of-scope realm untouched: the appendix keeps its own def:shared
    assert new_plan["appendices"] == plan["appendices"]


def test_synthetic_split_without_ruling_refuses_listing_strays():
    arc = _synth_arc()
    del arc["overrides"]["def:c2"]
    arc["park"] = []
    with pytest.raises(ValueError) as e:
        restructure.plan_from_arc(_synth_plan(), arc, {})
    msg = str(e.value)
    assert "def:c2" in msg and "def:c3" in msg and "stray" in msg


def test_synthetic_override_park_contradiction_refuses():
    arc = _synth_arc()
    arc["park"] = ["def:c3", "res:c1"]                 # res:c1 also overridden → X
    with pytest.raises(ValueError, match="both overridden and parked"):
        restructure.plan_from_arc(_synth_plan(), arc, {})


def test_synthetic_refs_carry_forward():
    arc = _synth_arc()
    arc["refs"] = {"carry": {"Y": ["B"]}, "overrides": {"r4": "M"}}
    new_plan = restructure.plan_from_arc(_synth_plan(), arc, {})
    by_id = {s["id"]: s for s in new_plan["sections"]}
    # plurality: A and B both pool into M; C's live votes tie X/Y and the first
    # occurrence wins (res:c1 → X), so C's pool lands in X — minus the r4 override
    assert by_id["M"]["refs"] == ["r1", "r2", "r4"]
    assert by_id["X"]["refs"] == ["r3"]
    assert by_id["Y"]["refs"] == ["r2"]                # carried from old B
    assert new_plan["appendices"][0]["refs"] == ["r9"]  # out of scope: untouched


def test_synthetic_figures_follow():
    new_plan = restructure.plan_from_arc(_synth_plan(), _synth_arc(), {})
    by_id = {s["id"]: s for s in new_plan["sections"]}
    assert by_id["M"]["figures"] == ["fig:fa"]         # follows A's default → M
    assert by_id["X"]["figures"] == ["fig:fc"]         # explicit override
    assert by_id["Y"]["figures"] == ["fig:new"]        # a mint, appended by ruling
    # a split parent's figure with no ruling must refuse, never vanish
    arc = _synth_arc()
    del arc["figure_overrides"]["fig:fc"]
    with pytest.raises(ValueError, match="fig:fc"):
        restructure.plan_from_arc(_synth_plan(), arc, {})
    # ...unless it is parked deliberately
    arc["park"] = ["def:c3", "fig:fc"]
    dropped = restructure.plan_from_arc(_synth_plan(), arc, {})
    assert all("fig:fc" not in s["figures"] for s in dropped["sections"])


def test_synthetic_beats_default_carry():
    new_plan = restructure.plan_from_arc(_synth_plan(), _synth_arc(), {})
    by_id = {s["id"]: s for s in new_plan["sections"]}
    # omitted beats → the old beats (document order) that landed in the section
    assert by_id["M"]["beats"] == ["res:a1"]
    assert by_id["X"]["beats"] == ["res:c1"]
    assert by_id["Y"]["beats"] == []


def test_unknown_override_fenced_only_when_net_given():
    arc = _synth_arc()
    arc["overrides"]["def:nope"] = "M"
    # with a net: a ruling naming a non-node is a typo, refused
    fake_net = {"nodes": {n: {} for sec in _synth_plan()["sections"] + _synth_plan()["appendices"]
                          for n in section_nodes(sec)}}
    fake_net["nodes"].update({n: {} for n in _synth_arc()["overrides"]})
    with pytest.raises(ValueError, match="def:nope"):
        restructure.plan_from_arc(_synth_plan(), arc, fake_net)
    # without a net the key is merely out of scope: inert, tolerated (seed semantics)
    new_plan = restructure.plan_from_arc(_synth_plan(), arc, {})
    assert all("def:nope" not in s["nodes_in_order"] for s in new_plan["sections"])


# ---------------------------------------------------------------------------
# C3.1 serves carry-through + the respine-wrapped contribution_rank round-trip
# ---------------------------------------------------------------------------

#: the 2026-07-22 respine envelope: rank list under ``value`` + ratified ruling.
_WRAPPED_RANK = {
    "value": ["the class thesis", "D1 (link-a, derived): a derived step",
              "D2 (link-b, derived): another step"],
    "projection_ruling": {"verb": "respine", "intent": "PI-20260721-142526-161107",
                          "note": "ratified", "applied_by": "gerard"}}


def test_plan_from_arc_preserves_respine_wrapped_rank_byte_intact():
    """Invariant (iii): a ``{value, projection_ruling}`` contribution_rank survives
    the restructure round-trip BYTE-INTACT — including projection_ruling — when the
    arc carries no meta of its own (plan_from_arc deep-copies; nothing normalises
    the store to a bare list)."""
    plan = _synth_plan()
    plan["meta"]["contribution_rank"] = copy.deepcopy(_WRAPPED_RANK)
    new_plan = restructure.plan_from_arc(plan, _synth_arc(), {})
    got = new_plan["meta"]["contribution_rank"]
    assert got == _WRAPPED_RANK                       # byte-intact, wrapper preserved
    assert isinstance(got, dict) and "projection_ruling" in got
    assert got["projection_ruling"]["note"] == "ratified"


def test_plan_from_arc_carries_serves_from_arc_sections():
    """FIX 2(a): an arc section MAY declare ``serves`` (the contribution it earns);
    plan_from_arc carries it onto the built section verbatim, like ``spec``. A
    section that omits serves stays without it (no default is invented)."""
    assert "serves" in restructure.TARGET_ARC_SECTION_FIELDS
    arc = _synth_arc()
    arc["sections"][0]["serves"] = [1]                # M earns the thesis
    arc["sections"][1]["serves"] = ["c0ffee01", 2]    # X earns a content-id + a rank
    # Y (sections[2]) declares nothing
    new_plan = restructure.plan_from_arc(_synth_plan(), arc, {})
    by_id = {s["id"]: s for s in new_plan["sections"]}
    assert by_id["M"]["serves"] == [1]
    assert by_id["X"]["serves"] == ["c0ffee01", 2]
    assert "serves" not in by_id["Y"]                 # omitted → absent, not defaulted


# ---------------------------------------------------------------------------
# the shepherd's actual target arc + serves map -> check_serves 15/15 once the
# respine-wrapped contribution_rank is readable (the full-chain integration).
# ---------------------------------------------------------------------------

def _load_plan_validator():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "validate_projection_plan", REPO / "scripts" / "validate_projection_plan.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: A2_serves_repair_design.md, by section id -> the contribution(s) it earns, as
#: 1-based rank numbers (thesis = 1; D_k = rank k+1). intro/bg are the added shells.
_SHEPHERD_SERVES = {
    "abstract": [1], "intro": [1], "bg": [1], "s1": [1],
    "s2": [2], "s3": [11], "s4": [2, 3, 4, 5], "s5": [5, 11], "s6": [12],
    "s7": [11], "s8": [6, 7, 8], "s9": [9, 12],
    "appendix_a": [1], "appendix_b": [1], "appendix_c": [1]}


def test_shepherd_arc_with_serves_validates_15_of_15_check_serves():
    """The full chain: the shepherd's diagnostic arc (intro+bg → 15 sections) + the
    A2 serves map, applied against paper_falqon's CURRENT plan whose
    contribution_rank is the respine-wrapped ``{value, projection_ruling}``. Once
    that shape is readable, check_serves resolves every section (15/15) and
    check_contribution_rank clears — the respine's ruling untouched. The plan on
    disk is post-A3, so this now also pins re-application as a fixed point: the same
    arc over the realized plan reproduces it node-for-node."""
    falqon = (REPO / "paper_falqon" / "manuscript" / "projection_plan.json")
    arc_p = (REPO / "paper_falqon" / "manuscript" / "reprojection" / "rounds"
             / "A2_meta_shape_diagnostic_arc.json")
    if not (falqon.is_file() and arc_p.is_file()):
        pytest.skip("paper_falqon plan / A2 diagnostic arc not on disk")
    plan = json.loads(falqon.read_text(encoding="utf-8"))
    # the plan must actually carry the wrapped shape for this test to mean anything
    rank = (plan.get("meta") or {}).get("contribution_rank")
    if not (isinstance(rank, dict) and "value" in rank):
        pytest.skip("paper_falqon rank is no longer the respine-wrapped shape")

    arc = json.loads(arc_p.read_text(encoding="utf-8"))
    arc.pop("meta", None)                             # keep the plan's wrapped rank
    # The A2 arc was authored BEFORE round A3 applied it: at A2 time the plan had no
    # intro/bg, so those two arc sections are shells carrying seed_from []. A3 then
    # created them and populated their nodes_in_order with the 9 teaching nodes
    # (support:intro-b1..b6, def:bg-b1..b3 — A3_realization_evidence.md), so the plan
    # on disk is now POST-realization. Re-applying the arc to it therefore needs each
    # shell to claim the section it created; plan_from_arc never guesses a home, so an
    # unclaimed old section's nodes are strays and the build refuses (by design).
    # Seeding an id-matched section from itself is identity re-homing: the 9 nodes land
    # back exactly where A3 put them, which is what makes the round-trip idempotent.
    old_ids = {s["id"] for realm in ("sections", "appendices")
               for s in (plan.get(realm) or [])}
    for realm in ("sections", "appendices"):
        for sec in arc.get(realm) or []:
            if not sec.get("seed_from") and sec["id"] in old_ids:
                sec["seed_from"] = [sec["id"]]
            if sec["id"] in _SHEPHERD_SERVES:
                sec["serves"] = _SHEPHERD_SERVES[sec["id"]]

    new_plan = restructure.plan_from_arc(plan, arc, {})   # net-free: arc has no overrides/park
    assert len(new_plan["sections"]) + len(new_plan["appendices"]) == 15
    # nothing was dropped on the way through: every node the live plan holds comes out
    # the far side in the same section (the identity re-homing above, checked not assumed)
    by_id = {s["id"]: s for s in new_plan["sections"] + new_plan["appendices"]}
    for realm in ("sections", "appendices"):
        for old in plan.get(realm) or []:
            assert by_id[old["id"]]["nodes_in_order"] == (old.get("nodes_in_order") or []), \
                f"{old['id']}: nodes moved or were dropped in the round-trip"

    v = _load_plan_validator()
    meta = new_plan["meta"]
    assert v.check_contribution_rank(meta) == []          # the wrapped thesis is readable
    defects, served, unserved = v.check_serves(new_plan, meta)
    assert defects == [], defects                         # every ref resolves
    assert served == 15 and unserved == 0                 # 15/15 — the 0/15 defect repaired
    # non-lossy: the respine ruling rode the whole round-trip untouched
    assert meta["contribution_rank"]["projection_ruling"] == \
        plan["meta"]["contribution_rank"]["projection_ruling"]


# ---------------------------------------------------------------------------
# prose bundles — re-integration input from the OLD fragments (pure read)
# ---------------------------------------------------------------------------

def test_prose_bundles_from_old_fragments(tmp_path):
    wp = tmp_path / "wp"
    wp.mkdir()
    (wp / "OLD1.tex").write_text(
        "% PLAN:OLD1\n% NODES: res:a1\nAlpha prose one.\n\n"
        "% NODES: def:a2, res:a1\nShared span prose.\n", encoding="utf-8")
    (wp / "OLD2.tex").write_text(
        "% PLAN:OLD2\n% NODES: res:b1\nBeta prose.\n", encoding="utf-8")
    old_plan = {"meta": {"target_dir": "wp"}, "sections": [
        {"id": "OLD1", "nodes_in_order": ["res:a1", "def:a2"]},
        {"id": "OLD2", "nodes_in_order": ["res:b1"]}], "appendices": []}
    new_plan = {"sections": [
        {"id": "NEW1", "nodes_in_order": ["res:b1", "res:a1"]},
        {"id": "NEW2", "nodes_in_order": ["def:a2"]}], "appendices": []}
    bundles = restructure.prose_bundles("subset-sum-itqde", old_plan, new_plan,
                                        repo_root=tmp_path)
    n1 = bundles["NEW1"]
    assert [(b["node"], b["old_section"]) for b in n1] == [
        ("res:b1", "OLD2"), ("res:a1", "OLD1"), ("res:a1", "OLD1")]
    assert n1[0]["tex_span"] == "Beta prose."
    assert n1[1]["tex_span"] == "Alpha prose one."
    assert n1[2]["tex_span"] == "Shared span prose."   # span dedupe is per section
    assert bundles["NEW2"] == [{"node": "def:a2", "old_section": "OLD1",
                                "tex_span": "Shared span prose."}]
    assert all("% NODES" not in b["tex_span"] for b in n1)


# ---------------------------------------------------------------------------
# (d) dry-run touches nothing real
# ---------------------------------------------------------------------------

def _identity_arc(plan: dict) -> dict:
    return {
        "sections": [{"id": s["id"], "title": s.get("title"),
                      "seed_from": [s["id"]], "beats": list(s.get("beats") or []),
                      "job": s.get("job") or ""} for s in plan.get("sections") or []],
        "refs": {"carry": {s["id"]: [s["id"]] for s in plan.get("sections") or []}},
    }


def test_execute_dry_run_never_writes(committed_plan):
    plan_path = MS / "projection_plan.json"
    l1_path = REPO / "corpus_friction" / "subset-sum-itqde.jsonl"
    before_plan, before_l1 = plan_path.read_bytes(), l1_path.read_bytes()
    before_listing = sorted(p.name for p in MS.iterdir())
    report = restructure.execute("subset-sum-itqde",
                                 _identity_arc(committed_plan), dry_run=True)
    assert report["ok"] and report["applied"] is False
    assert plan_path.read_bytes() == before_plan
    assert l1_path.read_bytes() == before_l1
    # nothing minted, nothing modified beside the plan. The L2 sidecars
    # (base/friction, gitignored) legitimately EXIST once any plan_write has run
    # in this tree (the set-meta migration ran one); purity here means the
    # dry-run did not create or grow anything - the listing is unchanged.
    assert sorted(p.name for p in MS.iterdir()) == before_listing
    # the report is the full dry surface
    for key in ("new_plan", "validation", "dirty", "spine_payloads", "prose_bundles"):
        assert key in report
    assert report["validation"].get("pass") is True
    assert "validator_error" not in report["validation"]
    # an identity restructure is all-cheap: no section's node-set moved
    assert all(d["class"] == "cheap" for d in report["dirty"]["sections"])
    assert report["dirty"]["removed_sections"] == []


def test_execute_refuses_a_stray_arc_without_writing():
    plan_path = MS / "projection_plan.json"
    before = plan_path.read_bytes()
    # one body section claiming nothing: every node strays, the operator refuses
    report = restructure.execute(
        "subset-sum-itqde", {"sections": [{"id": "Z1", "title": "Z", "seed_from": []}]},
        dry_run=True)
    assert report["ok"] is False and "stray" in report["error"]
    assert plan_path.read_bytes() == before
