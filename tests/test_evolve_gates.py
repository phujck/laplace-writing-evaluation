"""BITE B10 — the seven gates hard-block an evolution apply.

Author ruling (binding): ALL SEVEN build-completion gates
(canon://operations/gate_registry) must pass against the POST-evolution state
for an apply to land. There is NO override flag — the CLI grows no ``--force``.

Every fixture here is a SYNTHETIC scratch corpus built entirely under ``tmp_path``:
a stub ``main.tex`` plus a friction ledger that authors a tiny ALL-GREEN
conceptric as overlay deposits (the PDF-sourced convention). The scratch name is
registered as a registry data row under tmp_path and the tex-tree ``_repo_root``
is monkeypatched, so nothing touches
a canonical tree — in particular NOT ``synthetics papers/subset-sum-itqde`` (a
live pipeline run mutates it). The gates read the tex from the scratch root and
the rewiring OVERLAY from the evolution's rehearsal root — the B10 apply path.
"""
from __future__ import annotations

import io
import json
import runpy
import sys
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.web import scanner
from laplace.pipeline import verify as vf
from laplace.pipeline import evolve, registry

REPO = Path(__file__).resolve().parents[1]
NAME = "scratch_b10"
STUB_MAIN = "\\documentclass{article}\n\\begin{document}\n\\end{document}\n"

# The clean baseline conceptric, authored as friction-ledger overlay deposits.
# def:widget (a term), ref:source (literature), sup:widget-role (bridges to it),
# res:main (the spine beat, draws from def:widget + the role, so it reaches
# literature within 2 hops and is described by the level below), fig:widget-schema
# (a reproducible schematic). res:main also carries edges to the container leaves
# (paper://, references) so connectivity has zero orphans and topology is one
# connected component — the atomise base leaves are otherwise structural islands.
CLEAN_LEDGER = [
    dict(kind="add-node", node="def:widget", node_kind="definition",
         essence="A widget is the atomic unit of the scratch conceptric.", parent="paper://"),
    dict(kind="set-projection", node="def:widget",
         value={"latex_label": "def:widget", "term": "widget"}),
    dict(kind="add-node", node="ref:source", node_kind="citation",
         essence="Foundational reference for the scratch corpus.", parent="references"),
    dict(kind="set-projection", node="ref:source", value={"latex_label": "ref:source"}),
    dict(kind="add-node", node="sup:widget-role", node_kind="support",
         essence="Role node positioning the widget result against the literature.",
         parent="paper://", target="ref:source"),
    dict(kind="add-node", node="res:main", node_kind="result",
         essence="The main result establishing widget behaviour.",
         parent="paper://", target="def:widget"),
    dict(kind="add-edge", node="res:main", target="sup:widget-role"),
    dict(kind="add-edge", node="res:main", target="paper://"),
    dict(kind="add-edge", node="res:main", target="references"),
    dict(kind="set-projection", node="res:main",
         value={"latex_label": "res:main", "section_ref": "res:main"}),
    dict(kind="set-spine", node="res:main", ord=0, narrative="the sole beat"),
    dict(kind="add-node", node="fig:widget-schema", node_kind="support",
         essence="Schematic of the widget pipeline.", parent="paper://", target="res:main"),
    dict(kind="set-projection", node="fig:widget-schema",
         value={"latex_label": "fig:widget-schema", "section_ref": "res:main",
                "provenance": {"kind": "schematic", "generator": "scratch_fig.py",
                               "reproduce": "run scratch_fig.py"}}),
]

META = {"project": NAME, "from_version": {"name": "v1"}, "to_version": {"name": "v2"},
        "contract": "canon://skills/conceptric_evolution"}


def _mint_contract(**mint) -> dict:
    return {"meta": dict(META), "mints": [mint]}


@pytest.fixture
def scratch(tmp_path, monkeypatch, register_project):
    """A synthetic all-green scratch corpus under ``tmp_path``. Yields the repo
    root; the friction ledger + tex tree live beneath it, registered through the
    fixture door so no canonical tree is read or written."""
    (tmp_path / "tex").mkdir()
    (tmp_path / "tex" / "main.tex").write_text(STUB_MAIN, encoding="utf-8")
    (tmp_path / "corpus_friction").mkdir()
    ledger = tmp_path / "corpus_friction" / f"{NAME}.jsonl"
    ledger.write_text("".join(json.dumps(r) + "\n" for r in CLEAN_LEDGER), encoding="utf-8")

    register_project(tmp_path, NAME, tex_root="tex")                 # registry data row
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)      # gates' tex tree
    monkeypatch.setattr(registry, "_repo_root", lambda: tmp_path)     # CLI default apply root
    ci._CORPUS_CACHE.clear()
    yield tmp_path
    ci._CORPUS_CACHE.clear()


def _write_evo(root: Path, name: str, contract: dict) -> Path:
    d = root / "synthetics papers" / NAME / "manuscript" / "evolutions" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "evolution_plan.json").write_text(json.dumps(contract), encoding="utf-8")
    return d


def _live(ledger: Path) -> set[str]:
    from laplace.research.corpus_ingest import friction_current
    recs = [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]
    return {r["node"] for r in friction_current(recs)}


# ---------------------------------------------------------------------------
# the baseline is genuinely all-green (so a refusal below is the plant, not noise)
# ---------------------------------------------------------------------------

def test_scratch_baseline_all_seven_green(scratch):
    root = scratch
    for _name, fn_name in evolve.GATE_CHECKS:
        res = getattr(vf, fn_name)(NAME, root=root)
        assert res["pass"] is True, f"{fn_name} not green on the clean baseline: {res}"


# ---------------------------------------------------------------------------
# (c) one clean contract -> all seven ok in gates.json, apply lands, round-trip exact
# ---------------------------------------------------------------------------

def test_clean_contract_all_green_apply_lands(scratch):
    root = scratch
    ledger = root / "corpus_friction" / f"{NAME}.jsonl"
    before = _live(ledger)
    evo = _write_evo(root, "clean_mint", _mint_contract(
        id="def:gadget", kind="definition", essence_seed="A gadget composes widgets.",
        projection_seed={"latex_label": "def:gadget", "term": "gadget",
                         "section_ref": "res:main"},
        edges=[{"target": "def:widget"}]))

    verdict = evolve.gated_apply(NAME, evo, repo_root=root)

    assert verdict["applied"] is True
    assert verdict["round_trip_exact"] is True
    assert verdict["failed_gates"] == []
    assert all(g["ok"] for g in verdict["gates"].values())
    assert set(verdict["gates"]) == {n for n, _ in evolve.GATE_CHECKS}   # all seven present
    # the apply landed on the real ledger: the live set gained exactly the mint
    assert _live(ledger) - before == {"def:gadget"}
    # gates.json banked with the all-green verdict
    gj = json.loads((evo / "gates.json").read_text())
    assert gj["applied"] is True and gj["added"] == ["def:gadget"]
    assert all(g["ok"] for g in gj["gates"].values())


# ---------------------------------------------------------------------------
# (a) an edge to a NONEXISTENT node -> topology/connectivity blocks; repo untouched
# ---------------------------------------------------------------------------

def test_dangling_edge_blocks_and_leaves_ledger_byte_identical(scratch):
    root = scratch
    ledger = root / "corpus_friction" / f"{NAME}.jsonl"
    before_bytes = ledger.read_bytes()
    evo = _write_evo(root, "dangling", _mint_contract(
        id="res:ghosted", kind="result", essence_seed="Derives from a node that does not exist.",
        projection_seed={"latex_label": "res:ghosted", "section_ref": "res:main"},
        edges=[{"target": "def:does-not-exist"}]))

    with pytest.raises(evolve.EvolveError) as ei:
        evolve.gated_apply(NAME, evo, repo_root=root)
    assert "topology" in str(ei.value)

    # the repo/fixture ledger is byte-unchanged — the apply never ran
    assert ledger.read_bytes() == before_bytes
    # the verdict travels as a file, naming the failure and its target
    gj = json.loads((evo / "gates.json").read_text())
    assert gj["applied"] is False
    assert "topology" in gj["failed_gates"]
    dangles = gj["gates"]["topology"]["detail"]["dangling"]
    assert any(d["target"] == "def:does-not-exist" for d in dangles)


# ---------------------------------------------------------------------------
# (b) a mint with NO essence / NO term -> the coherence / glossary gate blocks
# ---------------------------------------------------------------------------

def test_essenceless_coarse_node_blocks_coherence(scratch):
    root = scratch
    evo = _write_evo(root, "essenceless", _mint_contract(
        id="res:empty", kind="result", essence_seed="",
        projection_seed={"latex_label": "res:empty", "section_ref": "res:main"},
        edges=[]))
    with pytest.raises(evolve.EvolveError):
        evolve.gated_apply(NAME, evo, repo_root=root)
    gj = json.loads((evo / "gates.json").read_text())
    assert gj["gates"]["coherence"]["ok"] is False
    assert "res:empty" in gj["gates"]["coherence"]["detail"]["under_described"]


def test_termless_def_blocks_glossary(scratch):
    root = scratch
    evo = _write_evo(root, "termless", _mint_contract(
        id="def:termless", kind="definition", essence_seed="Has essence but no term.",
        projection_seed={"latex_label": "def:termless", "section_ref": "res:main"},
        edges=[{"target": "def:widget"}]))
    with pytest.raises(evolve.EvolveError) as ei:
        evolve.gated_apply(NAME, evo, repo_root=root)
    assert "glossary" in str(ei.value)
    gj = json.loads((evo / "gates.json").read_text())
    assert gj["gates"]["glossary"]["ok"] is False
    assert "def:termless" in gj["gates"]["glossary"]["detail"]["missing_term"]


# ---------------------------------------------------------------------------
# (d) SUSPECT THE GREENS — a planted failure fires EACH of the seven gates
# ---------------------------------------------------------------------------
# Each contract is crafted to trip exactly its target gate against the clean
# baseline, so no gate can be a silent no-op-to-green (topology and coherence
# co-fire on a bare coarse node — a real coupling — so coherence rides its own
# essence-less plant above; the rest isolate to one gate).

_PLANTED = {
    "topology": _mint_contract(
        id="def:dang", kind="definition", essence_seed="def with a dangling edge.",
        projection_seed={"latex_label": "def:dang", "term": "dang-term", "section_ref": "res:main"},
        edges=[{"target": "def:ghost"}]),
    "connectivity": _mint_contract(
        id="def:orphan", kind="definition", essence_seed="unreachable def.",
        projection_seed={"latex_label": "def:orphan", "term": "orphan-term"},
        edges=[{"target": "def:widget"}]),
    "projection_labels": _mint_contract(
        id="def:nolabel", kind="definition", essence_seed="a def missing its label.",
        projection_seed={"term": "nolabel-term", "section_ref": "res:main"},
        edges=[{"target": "def:widget"}]),
    "glossary": _mint_contract(
        id="def:noterm2", kind="definition", essence_seed="a def missing its term.",
        projection_seed={"latex_label": "def:noterm2", "section_ref": "res:main"},
        edges=[{"target": "def:widget"}]),
    "substrate": _mint_contract(
        id="res:isolated", kind="result", essence_seed="a result with no scaffold.",
        projection_seed={"latex_label": "res:isolated", "section_ref": "res:main"},
        edges=[{"target": "def:widget"}]),
    "figures": _mint_contract(
        id="fig:noprov", kind="support", essence_seed="a figure lacking provenance.",
        projection_seed={"latex_label": "fig:noprov", "section_ref": "res:main"},
        edges=[{"target": "res:main"}]),
    "coherence": _mint_contract(
        id="res:barren", kind="result", essence_seed="",
        projection_seed={"latex_label": "res:barren", "section_ref": "res:main"},
        edges=[]),
}


@pytest.mark.parametrize("gate", list(_PLANTED))
def test_each_gate_fires_on_its_planted_failure(scratch, gate):
    root = scratch
    ledger = root / "corpus_friction" / f"{NAME}.jsonl"
    before = ledger.read_bytes()
    evo = _write_evo(root, f"plant_{gate}", _PLANTED[gate])
    with pytest.raises(evolve.EvolveError):
        evolve.gated_apply(NAME, evo, repo_root=root)
    gj = json.loads((evo / "gates.json").read_text())
    assert gate in gj["failed_gates"], f"{gate} did not fire: {gj['failed_gates']}"
    assert gj["gates"][gate]["ok"] is False
    assert ledger.read_bytes() == before          # every refusal leaves the repo untouched


# ---------------------------------------------------------------------------
# (d, complement) call-recording: all seven gates are actually INVOKED against the
# rehearsal (temp) root — no gate can silently no-op to green off the LIVE repo
# ---------------------------------------------------------------------------

def test_all_seven_gates_invoked_on_the_rehearsal_root(scratch, monkeypatch):
    root = scratch
    seen: dict[str, tuple] = {}    # gate -> (root, evolved-ledger-existed-at-call-time)

    def _record(name, fn):
        def wrapper(corpus, root=None):
            existed = bool(root) and (Path(root) / "corpus_friction" / f"{NAME}.jsonl").is_file()
            seen[name] = (root, existed)
            return fn(corpus, root=root)
        return wrapper

    for gate_name, fn_name in evolve.GATE_CHECKS:
        monkeypatch.setattr(vf, fn_name, _record(gate_name, getattr(vf, fn_name)))

    evo = _write_evo(root, "clean_probe", _mint_contract(
        id="def:probe", kind="definition", essence_seed="probe.",
        projection_seed={"latex_label": "def:probe", "term": "probe-term",
                         "section_ref": "res:main"},
        edges=[{"target": "def:widget"}]))
    evolve.gated_apply(NAME, evo, repo_root=root)

    # every one of the seven was invoked, and each against a private rehearsal
    # temp dir carrying the evolved ledger — NOT the live repo root
    assert set(seen) == {n for n, _ in evolve.GATE_CHECKS}
    for gate_name, (used_root, existed) in seen.items():
        assert used_root is not None, f"{gate_name} ran against the live repo, not the rehearsal"
        assert Path(used_root) != root, f"{gate_name} ran against the live repo root"
        assert existed, f"{gate_name} did not see the evolved ledger under its root"


# ---------------------------------------------------------------------------
# the rehearsal exposes the evolved state; the default self-cleans
# ---------------------------------------------------------------------------

def test_keep_rehearsal_exposes_evolved_ledger_and_default_cleans_up(scratch):
    root = scratch
    evo = _write_evo(root, "rehearse", _mint_contract(
        id="def:gadget", kind="definition", essence_seed="A gadget.",
        projection_seed={"latex_label": "def:gadget", "term": "gadget", "section_ref": "res:main"},
        edges=[{"target": "def:widget"}]))

    kept = evolve.execute(NAME, evo, dry_run=True, repo_root=root, keep_rehearsal=True)
    rehearsal_root = Path(kept["rehearsal_root"])
    evolved = rehearsal_root / "corpus_friction" / f"{NAME}.jsonl"
    assert evolved.is_file()
    assert "def:gadget" in _live(evolved)                 # the POST state is inspectable
    assert "def:gadget" not in _live(root / "corpus_friction" / f"{NAME}.jsonl")  # live untouched
    import shutil
    shutil.rmtree(rehearsal_root, ignore_errors=True)

    # the default (no keep_rehearsal) removes its temp root and exposes no path
    plain = evolve.execute(NAME, evo, dry_run=True, repo_root=root)
    assert "rehearsal_root" not in plain


# ---------------------------------------------------------------------------
# (e) the CLI: --apply on a failing contract exits nonzero, names the gate; no --force
# ---------------------------------------------------------------------------

def test_cli_apply_refuses_names_gate(scratch, monkeypatch):
    root = scratch
    evo = _write_evo(root, "cli_fail", _mint_contract(
        id="def:noterm3", kind="definition", essence_seed="cli plant.",
        projection_seed={"latex_label": "def:noterm3", "section_ref": "res:main"},
        edges=[{"target": "def:widget"}]))

    script = str(REPO / "scripts" / "evolve.py")
    saved = sys.argv
    sys.argv = [script, NAME, str(evo), "--apply"]
    buf = io.StringIO()
    try:
        with redirect_stderr(buf), pytest.raises(SystemExit) as ei:
            runpy.run_path(script, run_name="__main__")
    finally:
        sys.argv = saved
    assert ei.value.code == 1                              # nonzero exit on refusal
    err = buf.getvalue()
    assert "glossary" in err                               # the failing gate on stderr
    assert json.loads((evo / "gates.json").read_text())["applied"] is False


def test_cli_grows_no_force_flag():
    src = (REPO / "scripts" / "evolve.py").read_text(encoding="utf-8")
    # strip the module docstring (which explains WHY there is no --force) and
    # assert the executable body defines no force flag / override of any spelling
    body = src.split('"""', 2)[-1]
    assert "--force" not in body
    assert "force" not in body.lower()
    assert '"--apply"' in body                    # the one apply flag, gated
    assert '"--force"' not in body                # and no override flag beside it


# ---------------------------------------------------------------------------
# the judge's cache-collision probe, banked: two same-process gated_apply calls
# with same-length overlays must never read each other's network
# ---------------------------------------------------------------------------

def test_second_in_process_gated_apply_never_reads_stale_network(scratch):
    """First rehearsal (dangling, refused) must not poison the second (clean):
    the corpus-network cache key carries the overlay's IDENTITY, not its
    length — a stale collision wrongly refused a clean evolution (and could,
    in the narrower chain, wrongly PASS a broken one)."""
    root = scratch
    ledger = root / "corpus_friction" / f"{NAME}.jsonl"

    evo_bad = _write_evo(root, "cache_bad", _mint_contract(
        id="res:ghosted", kind="result", essence_seed="Derives from a ghost.",
        projection_seed={"latex_label": "res:ghosted", "section_ref": "res:main"},
        edges=[{"target": "def:does-not-exist"}]))
    with pytest.raises(evolve.EvolveError):
        evolve.gated_apply(NAME, evo_bad, repo_root=root)

    # SAME process, NO cache clear — the clean evolution (same overlay length
    # class) must be judged on ITS OWN rehearsal network and land.
    before = _live(ledger)
    evo_ok = _write_evo(root, "cache_ok", _mint_contract(
        id="def:gadget2", kind="definition", essence_seed="A second gadget.",
        projection_seed={"latex_label": "def:gadget2", "term": "gadget-two",
                         "section_ref": "res:main"},
        edges=[{"target": "def:widget"}]))
    verdict = evolve.gated_apply(NAME, evo_ok, repo_root=root)
    assert verdict["applied"] is True and verdict["failed_gates"] == []
    assert _live(ledger) - before == {"def:gadget2"}


def test_topology_delta_inherited_debt_does_not_block(monkeypatch):
    """First real refusal (2026-07-10), banked at unit grain: pre-existing
    multi-component debt must not hold a non-worsening evolution hostage;
    the topology gate passes on the DELTA. A worsening delta still blocks."""
    from laplace.pipeline import verify as vf

    calls = {"n": 0}
    def fake_topology(project, root=None):
        calls["n"] += 1
        if root is None:            # the LIVE baseline: inherited debt
            return {"pass": False, "dangling": [], "components": 8}
        return {"pass": False, "dangling": [], "components": 8}   # post: unchanged
    def green(project, root=None):
        return {"pass": True}

    for name, fn in evolve.GATE_CHECKS:
        monkeypatch.setattr(vf, fn, fake_topology if name == "topology" else green)
    report = evolve.pre_apply_gates("any", "/tmp/rehearsal-root")
    assert report["topology"]["ok"] is True                 # delta: not worsened
    assert report["topology"]["detail"]["baseline"]["components"] == 8
    assert "DELTA" in report["topology"]["detail"]["note"]

    # a WORSENING post (9 components, or new dangling) still blocks hard
    def worse_topology(project, root=None):
        if root is None:
            return {"pass": False, "dangling": [], "components": 8}
        return {"pass": False, "dangling": ["def:ghost"], "components": 9}
    monkeypatch.setattr(vf, dict(evolve.GATE_CHECKS)["topology"], worse_topology)
    report2 = evolve.pre_apply_gates("any", "/tmp/rehearsal-root")
    assert report2["topology"]["ok"] is False
