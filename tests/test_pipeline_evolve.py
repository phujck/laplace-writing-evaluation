"""Golden masters for the native ``evolve`` operator (pipeline.evolve).

The generality proof the mandate demands: BOTH banked contracts load as-is,
the pure planner reproduces the v2→v3 evolution's declared enumeration, and a
dry-run re-execution against the reconstructed PRE-evolution ledger lands on
exactly the banked POST-evolution live set — with the transaction truncating
back byte-exact when a round trip breaks.

The banked evolution dirs are a FROZEN AUDIT TRAIL: every test here reads
them; none writes. The real friction ledger is only ever read; every execution
runs against a temp copy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.research.corpus_ingest import friction_current
from laplace.pipeline import evolve, registry

REPO = Path(__file__).resolve().parents[1]
EVOS = REPO / "synthetics papers" / "subset-sum-itqde" / "manuscript" / "evolutions"
V2V3 = EVOS / "v2_to_v3_spectral_surfacing"
GENERAL = EVOS / "general_first_restructure_2026-07-08"
LEDGER = REPO / "corpus_friction" / "subset-sum-itqde.jsonl"


def _parse(lines):
    out = []
    for ln in lines:
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                pass
    return out


def _live_ids(lines) -> set[str]:
    return {r["node"] for r in friction_current(_parse(lines))}


@pytest.fixture(scope="module")
def ledger_lines():
    return LEDGER.read_text(encoding="utf-8").splitlines()


@pytest.fixture(scope="module")
def v3_boundaries(ledger_lines):
    """Locate the v2→v3 fold block instead of trusting line numbers: it starts
    at the first mint's add-node and runs to the end of the 2026-07-04-stamped
    records (the whole execution window, extras included). The banked boundary
    is lines 1697–1842 (1-based) — asserted so a shifted ledger fails loudly."""
    recs = _parse(ledger_lines)
    start = next(i for i, r in enumerate(recs)
                 if r.get("kind") == "add-node"
                 and r.get("node") == "def:spectral-signal")
    end = start
    while end < len(recs) and str(recs[end].get("ts", "")).startswith("2026-07-04"):
        end += 1
    assert start == 1696 and end == 1842, (
        f"v3 block moved: found [{start}:{end}], banked [1696:1842] (0-based)")
    return start, end


# ---------------------------------------------------------------------------
# (a) both banked contracts load, shapes recognised
# ---------------------------------------------------------------------------

def test_load_both_banked_contracts():
    sub = evolve.load_contract(V2V3)
    story = evolve.load_contract(GENERAL)

    assert "substrate" in sub["_shapes"]
    # the storyboard-led contract also mints, so it carries both shapes; its
    # arc lives in spine_reorder (not the schema's target_arc name) and its
    # rulings under the dated meta key — the loader takes the file as-is
    assert set(story["_shapes"]) == {"substrate", "storyboard"}

    for c in (sub, story):
        meta = c["meta"]
        assert meta["project"] == "subset-sum-itqde"
        assert meta["contract"] == "canon://skills/conceptric_evolution"
        assert meta["from_version"]["name"] and meta["to_version"]["name"]

    assert len(sub["mints"]) == 26 and len(sub["reshapes"]) == 11
    assert len(story["mints"]) == 1 and story["deprecations"] == []
    # field variations pinned: kind vs node_kind, dict-edges vs string-edges
    assert sub["mints"][0]["kind"] == "definition"
    assert story["mints"][0]["node_kind"] == "support"
    assert evolve._mint_edges(sub["mints"][1]) == ["def:probe-target-shift"]
    assert evolve._mint_edges(story["mints"][0])[0] == "thm:fourier-reconstruction-identity"


def test_load_rejects_shapeless_or_meta_less(tmp_path):
    d = tmp_path / "evo"
    d.mkdir()
    (d / "evolution_plan.json").write_text(json.dumps(
        {"meta": {"project": "p", "from_version": "a"}}), encoding="utf-8")
    with pytest.raises(evolve.EvolveError, match="meta missing"):
        evolve.load_contract(d)
    (d / "evolution_plan.json").write_text(json.dumps(
        {"meta": {"project": "p", "from_version": "a", "to_version": "b",
                  "contract": "c"}}), encoding="utf-8")
    with pytest.raises(evolve.EvolveError, match="no recognised evolution sections"):
        evolve.load_contract(d)


# ---------------------------------------------------------------------------
# (b) plan_records reproduces the contracts' own enumeration
# ---------------------------------------------------------------------------

def test_v2v3_plan_records_golden_master():
    contract = evolve.load_contract(V2V3)
    records = evolve.plan_records(contract)

    kinds: dict[str, int] = {}
    for r in records:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1

    # The CONTRACT's enumeration, which the historical fold (ledger lines
    # 1697–1842: 26 add-node, 86 set-projection, 23 add-edge, 11 edit-essence)
    # EXCEEDS with execution-time extras that are not in the contract:
    #   set-projection 29 vs 86 — the fold also carried 27 later re-placement
    #     section_refs, 29 latex_label backfills on ref: nodes, and 1 repeat
    #     of the deprecated_aliases record;
    #   add-edge 13 vs 23 — 25 of the 38 enumerated edges ride their mint's
    #     add-node.target (first-edge-at-birth, reproduced here), and the fold
    #     added 10 out-of-contract ref:free-snacks citation edges;
    #   edit-essence 3 vs 11 — only 3 reshapes carry their essence text in the
    #     contract; the other 8 texts were authored at execution time, which a
    #     pure planner must not invent.
    assert kinds == {"add-node": 26, "set-projection": 29,
                     "add-edge": 13, "edit-essence": 3}

    mint_ids = [m["id"] for m in contract["mints"]]
    assert [r["node"] for r in records if r["kind"] == "add-node"] == mint_ids

    # the full 38-edge enumeration is preserved: first edge on the birth
    # record, the rest as add-edge
    planned_edges = {(r["node"], r["target"]) for r in records
                     if r["kind"] == "add-edge"}
    planned_edges |= {(r["node"], r["target"]) for r in records
                      if r["kind"] == "add-node" and r.get("target")}
    contract_edges = {(m["id"], t) for m in contract["mints"]
                      for t in evolve._mint_edges(m)}
    assert len(contract_edges) == 38 and planned_edges == contract_edges

    # deprecate projections, keep nodes: the SSC retiral is a projection slot,
    # and NO contract path ever emits delete-node
    retire = [r for r in records if r["kind"] == "set-projection"
              and (r.get("value") or {}).get("retired") is True]
    assert [r["node"] for r in retire] == ["def:spectral-staircase-cartography"]
    assert not any(r["kind"] == "delete-node" for r in records)

    # the term-shaped deprecation lands on the successor's projection
    dep = [r for r in records if "deprecated_aliases" in (r.get("value") or {})]
    assert [r["node"] for r in dep] == ["def:spectral-surfacing"]
    assert "SSC" in dep[0]["value"]["deprecated_aliases"]

    # seeds carry the banked audit stamps
    seed = next(r for r in records if r["kind"] == "set-projection"
                and r["node"] == "def:spectral-signal")
    assert seed["value"]["evolution"] == "v2_to_v3_spectral_surfacing"
    assert seed["value"]["section_ref"] == "S1"
    assert "evolution_source" in seed["value"]


def test_general_first_plan_records():
    contract = evolve.load_contract(GENERAL)
    records = evolve.plan_records(contract)

    kinds: dict[str, int] = {}
    for r in records:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    # 1 mint (first edge at birth, 2 as add-edge) + the 15-beat arc + 1 unset.
    # The banked bespoke run wrote all 3 edges as add-edge and no birth target
    # — same substrate either way; the operator uses the one convention.
    assert kinds == {"add-node": 1, "set-projection": 1, "add-edge": 2,
                     "set-spine": 15, "unset-spine": 1}

    an = next(r for r in records if r["kind"] == "add-node")
    assert an["node"] == "fig:ssg-pipeline-orientation"
    assert an["node_kind"] == "support"
    assert an["target"] == "thm:fourier-reconstruction-identity"

    # no projection_seed in this shape: the seed is derived (label + the
    # contract's section_target + provenance)
    seed = next(r for r in records if r["kind"] == "set-projection")
    assert seed["value"]["latex_label"] == "fig:ssg-pipeline-orientation"
    assert seed["value"]["section_ref"] == "S1"
    assert seed["value"]["provenance"]["kind"] == "schematic"

    spine = [r for r in records if r["kind"] == "set-spine"]
    assert [r["ord"] for r in spine] == list(range(15))
    assert spine[0]["node"] == "res:itqde-spectral-readout"
    assert spine[-1]["node"] == "res:planted-trade-family"
    unset = [r for r in records if r["kind"] == "unset-spine"]
    assert [r["node"] for r in unset] == ["goal:perturbation-assisted-itqde"]

    # the plan side is an explicit deferred seam, never substrate records
    leg = evolve.plan_leg(contract, registry.resolve("subset-sum-itqde"))
    assert leg["direction"] == "storyboard-led"
    assert leg["action"] == "deferred-to-restructure"
    assert len(leg["handoff"]["target_arc"]) == 15


def test_node_shaped_deprecation_retires_never_deletes():
    # the skill's canonical deprecation kind (neither banked contract uses it)
    contract = {"meta": {"project": "p", "from_version": "a", "to_version": "b",
                         "contract": "c"},
                "deprecations": [{"id": "def:old-frame"}]}
    records = evolve.plan_records(contract)
    assert records == [{"kind": "set-projection", "node": "def:old-frame",
                        "value": {"retired": True}, "by": "evolve"}]


# ---------------------------------------------------------------------------
# (c) dry-run re-execution against the reconstructed PRE-evolution ledger
# ---------------------------------------------------------------------------

def test_execute_replays_v2v3_onto_banked_post_state(tmp_path, ledger_lines,
                                                     v3_boundaries):
    start, end = v3_boundaries
    pre_lines, post_lines = ledger_lines[:start], ledger_lines[:end]
    live_pre, live_post = _live_ids(pre_lines), _live_ids(post_lines)
    assert (len(live_pre), len(live_post)) == (376, 401)  # +26 mints, −1 retiral

    temp_root = tmp_path / "repo"
    l1 = temp_root / "corpus_friction" / "subset-sum-itqde.jsonl"
    l1.parent.mkdir(parents=True)
    l1.write_text("\n".join(pre_lines) + "\n", encoding="utf-8")
    real_bytes = LEDGER.stat().st_size

    report = evolve.execute("subset-sum-itqde", V2V3, dry_run=True,
                            repo_root=temp_root)

    assert report["ok"] and report["round_trip_exact"]
    assert not report["already_applied"]
    assert report["records"] == 71  # 26+29+13+3, the contract's enumeration
    assert (report["before_count"], report["after_count"]) == (376, 401)
    assert set(report["added"]) == {m["id"] for m in
                                    evolve.load_contract(V2V3)["mints"]}
    assert report["removed"] == ["def:spectral-staircase-cartography"]
    # the produced live set IS the banked post-evolution live set, exactly
    assert (live_pre - set(report["removed"])) | set(report["added"]) == live_post

    # dry-run law: neither the real ledger nor the given copy was touched
    assert LEDGER.stat().st_size == real_bytes
    assert l1.read_text(encoding="utf-8").splitlines() == pre_lines


# ---------------------------------------------------------------------------
# (d) a broken round trip truncates the ledger back byte-identical
# ---------------------------------------------------------------------------

def test_transaction_abort_leaves_ledger_byte_identical(tmp_path, ledger_lines,
                                                        v3_boundaries):
    start, _ = v3_boundaries
    temp_root = tmp_path / "repo"
    l1 = temp_root / "corpus_friction" / "subset-sum-itqde.jsonl"
    l1.parent.mkdir(parents=True)
    l1.write_text("\n".join(ledger_lines[:start]) + "\n", encoding="utf-8")
    before_bytes = l1.read_bytes()

    # a replay-shaped contract: it mints a node that is already live, so the
    # live-set delta cannot match its enumeration (fold by ledger, never replay)
    broken = tmp_path / "broken_evolution"
    broken.mkdir()
    (broken / "evolution_plan.json").write_text(json.dumps({
        "meta": {"project": "subset-sum-itqde", "from_version": {"name": "x"},
                 "to_version": {"name": "y"},
                 "contract": "canon://skills/conceptric_evolution"},
        "mints": [{"id": "def:staircase", "kind": "definition",
                   "essence_seed": "a duplicate mint", "edges": []}],
    }), encoding="utf-8")

    report = evolve.execute("subset-sum-itqde", broken, dry_run=False,
                            repo_root=temp_root)

    assert not report["ok"] and not report["round_trip_exact"]
    assert "round-trip mismatch" in report["error"]
    assert report["added"] == [] and report["removed"] == []
    assert l1.read_bytes() == before_bytes


# ---------------------------------------------------------------------------
# the verify surface (ready for the orchestrator to register as 'evolution')
# ---------------------------------------------------------------------------

def test_verify_check_shape_and_already_applied():
    # against the live repo the banked contract is already applied: the dry
    # run's round trip correctly refuses the replay, and the check stays green
    res = evolve.verify_check("subset-sum-itqde", V2V3)
    assert res["pass"] is True
    assert res["already_applied"] is True
    assert res["round_trip_exact"] is False
    assert res["evolution_dir"] == str(V2V3)

    assert evolve.verify_check("no-such-project")["pass"] is None
