"""W-BIRTH — the birth stage hardened: a New Project scaffold lands ON the ladder.

The birth clause (``contract/surfaces/dashboard.yaml::birth-lands-on-the-ladder``, bar
mechanical): a fresh scaffold born through the New Project door carries SEEDED with its
goal prompt minted as the goal node, its demand queues populated BEFORE any compile
exists, resolves through ``registry.project_context``, opens on ``/conceptric`` with no
dead end, and NEVER retro-ladders a released paper (the backfill law holds).

These are the in-process proofs; the live-server / browser proof (POST /dashboard/new →
GET the doors → the SEEDED card) is the ``j6_new_project`` playwright walk. Every write
here lands in an isolated ``tmp_path`` root — the real repo is never touched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.web import dashboard
from laplace.projects import project_creation
from laplace.pipeline import demand, growth, registry

REPO = Path(__file__).resolve().parents[1]


def _born(tmp: Path, name: str = "born-probe", goal: str | None = None):
    """Create a scaffold through the real door in an isolated root; assert the 201."""
    status, out = project_creation.create_project(name, "conceptric", root=tmp, goal=goal)
    assert status == 201 and out["ok"], out
    return out


# ============================================================ SEEDED + queues

def test_birth_seeds_the_sidecar_at_seeded(tmp_path):
    _born(tmp_path)
    gs = growth.growth_state(tmp_path, "born-probe")
    assert gs["present"] is True and gs["state"] == "SEEDED" and gs["goal_version"] == 1
    # the sidecar file itself carries the birth queues (the audit ran once, at birth).
    side = json.loads((tmp_path / "corpus_friction" / "born-probe.growth.json").read_text())
    assert side["state"] == "SEEDED" and side.get("queues")


def test_birth_populates_the_demand_queues_before_any_compile(tmp_path):
    _born(tmp_path)
    gs = growth.growth_state(tmp_path, "born-probe")
    q = gs.get("queues")
    assert q, "the birth queues are the mechanical conjunct of birth-lands-on-the-ladder"
    # every demand of the FORM object is walked into its friction queue (token-free, no net).
    assert q["n_demands"] == len(demand.DEMANDS)
    assert set(q["friction"]) == set(demand.FRICTION_TYPES)
    assert sum(q["counts"].values()) == len(demand.DEMANDS)
    # NO compiled substrate exists yet — the birth queue is the pre-compile FORM skeleton,
    # and its vocabulary never reads 'passed' (a birth queue is all-owed by construction).
    assert q["audit"] == "registry-skeleton"
    stances = {row["stance"] for rows in q["friction"].values() for row in rows}
    assert stances <= {"pre-compile", "judged-pending"} and "passed" not in stances


def test_birth_queues_partition_the_registry_by_friction(tmp_path):
    _born(tmp_path)
    q = growth.growth_state(tmp_path, "born-probe")["queues"]
    seen = {row["demand_id"] for rows in q["friction"].values() for row in rows}
    assert seen == {d["id"] for d in demand.DEMANDS}


# ============================================================ the goal node

def test_birth_mints_the_goal_node_marked_machine_scaffolded(tmp_path):
    out = _born(tmp_path, goal="run measurement-driven iteration coherently")
    assert out["goal_node"] == "goal:scaffold-born-probe" and out["goal_scaffolded"] is True
    rows = [json.loads(l) for l in
            (tmp_path / "corpus_friction" / "born-probe.jsonl").read_text().splitlines() if l.strip()]
    # the SEED row is still first (the ledger's genesis marker), the goal is an add-node.
    assert rows[0]["kind"] == "seed"
    goal = next(r for r in rows if r.get("kind") == "add-node" and r.get("node_kind") == "goal")
    # the authored prompt is the essence, MARKED machine-scaffolded (never his authored goal).
    assert "run measurement-driven iteration coherently" in goal["essence"]
    assert "scaffolded goal" in goal["essence"] and goal["by"] == "dashboard-new-project"


def test_goal_essence_defaults_to_the_humanised_name(tmp_path):
    _born(tmp_path, name="a-clever-paper")
    rows = [json.loads(l) for l in
            (tmp_path / "corpus_friction" / "a-clever-paper.jsonl").read_text().splitlines() if l.strip()]
    goal = next(r for r in rows if r.get("node_kind") == "goal")
    assert "a clever paper" in goal["essence"] and "scaffolded goal" in goal["essence"]


def test_goal_node_shows_in_the_conceptric_on_the_spine_no_gaps(tmp_path):
    _born(tmp_path)
    troot = ci.resolve_corpus(tmp_path, "born-probe")
    assert troot is not None, "the main.tex stub makes the scaffold resolve (no dead end)"
    net = ci.corpus_network(troot, repo_root=tmp_path, name="born-probe")
    goal_ids = [nid for nid in net["nodes"] if nid.startswith("goal:")]
    assert goal_ids == ["goal:scaffold-born-probe"]
    # on the apex spine, so the goal-only net has no spine-unreachable orphan and no gap.
    assert "goal:scaffold-born-probe" in {s["id"] for s in net.get("spine", [])}
    assert ci.gaps(net) == []


# ============================================================ project_context resolves

def test_project_context_resolves_the_scaffold(tmp_path, monkeypatch):
    # registry.resolve reads the module repo root; point it at the isolated root so the
    # scaffold's data row resolves (the openability guarantee rides project_context).
    monkeypatch.setattr(registry, "_repo_root", lambda: tmp_path)
    _born(tmp_path)
    ctx = registry.project_context("born-probe", tmp_path)
    assert ctx is not None and ctx.name == "born-probe" and ctx.kind == "conceptric"
    # honest: no compile exists, so no artefact pdf resolves (never a fabricated door).
    assert (ctx.current_artefact or {}).get("pdf") is None


def test_scaffold_main_tex_is_source_not_a_compile(tmp_path):
    _born(tmp_path)
    main_tex = tmp_path / "synthetics papers" / "born-probe" / "manuscript" / "main.tex"
    assert main_tex.is_file()
    # a SOURCE stub — no PDF artefact is produced at birth (before any compile exists).
    target = tmp_path / "synthetics papers" / "born-probe" / "manuscript" / "whitepaper"
    assert not (target / "release").exists()


# ============================================================ no retro-laddering

def test_birth_does_not_retro_ladder_a_released_paper(tmp_path, monkeypatch):
    # a released paper with no sidecar renders a plain pre-ladder null — never a fake SEEDED,
    # and never carries the birth queues (queues are surfaced only on the present branch).
    gs = growth.growth_state(REPO, "paper_falqon")
    assert gs["present"] is False and gs["state"] is None and gs["pre_ladder"] is True
    assert gs.get("queues") is None
    # birthing a fresh scaffold in an isolated root does not touch the released paper.
    _born(tmp_path, name="fresh-one")
    gs2 = growth.growth_state(REPO, "paper_falqon")
    assert gs2["pre_ladder"] is True and gs2.get("state") is None


def test_a_never_seeded_project_is_not_on_the_ladder(tmp_path):
    gs = growth.growth_state(tmp_path, "no-such-scaffold")
    assert gs["present"] is False and gs["pre_ladder"] is False and gs.get("queues") is None


# ============================================================ idempotent back-fill

def test_reseed_is_idempotent_and_backfills_missing_queues(tmp_path):
    _born(tmp_path)
    sidecar = tmp_path / "corpus_friction" / "born-probe.growth.json"
    side = json.loads(sidecar.read_text())
    # simulate a legacy sidecar written before the birth-queue conjunct landed.
    side.pop("queues", None)
    sidecar.write_text(json.dumps(side))
    # seed() again: state is untouched (idempotent), the queues are back-filled additively.
    out = growth.seed(tmp_path, "born-probe")
    assert out["state"] == "SEEDED" and out.get("queues")
    assert growth.growth_state(tmp_path, "born-probe")["queues"]
