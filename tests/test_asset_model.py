"""The asset model (P7) — every derivation and every figure an addressable object.

These tests run the real ``enumerate_assets`` over the two conventions on disk:
the ``synthetics papers/`` layout (subset-sum-itqde: ``.py`` generators + rendered
siblings for figures, ``WK-*.tex`` derivation walks) and the ``eigenengine``
layout (hand-tikz ``fig_*.tex``, NO derivations). Each project's tests skip
cleanly when its tree is absent, so a thin checkout never hard-fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.pipeline import asset_model as am
from laplace.pipeline.asset_model import (
    AssetObject, Landing, PanelAnchor, Producer, StepAnchor, enumerate_assets,
)

REPO = Path(__file__).resolve().parents[1]


def _project_present(name: str) -> bool:
    roots = am.asset_roots(name)
    if roots is None:
        return False
    for g in roots.figures + roots.derivations:
        base = g.split("*", 1)[0].rstrip("/")
        if base and (REPO / base).exists():
            return True
    return False


# --------------------------------------------------------------------------- #
# Schema unit tests — no filesystem needed.
# --------------------------------------------------------------------------- #

def test_producer_validates_type():
    with pytest.raises(ValueError):
        Producer(type="bogus")
    assert Producer("none").path is None
    assert Producer("py-script", "x/y.py").path == "x/y.py"


def test_asset_object_validates_kind():
    with pytest.raises(ValueError):
        AssetObject(id="x", kind="bogus", project="p")


def test_schema_round_trips_to_json():
    obj = AssetObject(
        id="figure:F1_staircase", kind="figure", project="subset-sum-itqde",
        producer=Producer("py-script", "a/b/F1_staircase.py"),
        inputs=["a/b/data.csv"], nodes_supported=["def:hamiltonian-h0"],
        landings=[Landing(file="main.pdf", page=2,
                          bbox={"x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0},
                          kind="float", measured=True, source="nodemap")],
        panels=[PanelAnchor(id="a", var="ax_L")],
        rendered=["a/b/F1_staircase.png"],
        source_path="a/b/F1_staircase.py", node_id="fig:f1-staircase",
    )
    s = obj.to_json()
    back = AssetObject.from_json(s)
    # structural equality via the dict form (dataclasses compare cleanly)
    assert back.to_dict() == obj.to_dict()
    # and it is genuine JSON
    assert json.loads(s)["kind"] == "figure"


def test_derivation_round_trips_with_steps():
    obj = AssetObject(
        id="derivation:WK-042", kind="derivation", project="subset-sum-itqde",
        producer=Producer("tex-inline", "a/b/WK-042.tex"),
        nodes_supported=["thm:natural-parameters-cumulants"],
        steps=[StepAnchor(id="eq:kappa1", kind="equation", label="eq:kappa1",
                          line_start=20, line_end=23),
               StepAnchor(id="WK-042#eq2", kind="align", line_start=30, line_end=34)],
        source_path="a/b/WK-042.tex",
    )
    back = AssetObject.from_json(obj.to_json())
    assert back.to_dict() == obj.to_dict()
    assert len(back.steps) == 2 and back.steps[0].label == "eq:kappa1"


def test_asset_roots_convention_declares_both_layouts():
    ss = am.asset_roots("subset-sum-itqde")
    assert ss is not None and ss.figure_producer == "auto"
    eig = am.asset_roots("eigenengine")
    assert eig is not None and eig.figure_producer == "hand-tikz"
    # eigenengine declares NO derivation roots — honest, first-class
    assert eig.derivations == ()


def test_unknown_project_is_empty_not_error():
    assert enumerate_assets("no-such-project-xyz") == []


# --------------------------------------------------------------------------- #
# subset-sum-itqde: py-script figures + WK derivation walks with step anchors.
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _project_present("subset-sum-itqde"),
                    reason="subset-sum-itqde tree absent")
def test_subset_sum_has_py_script_figure_with_real_producer():
    assets = enumerate_assets("subset-sum-itqde")
    figs = [a for a in assets if a.kind == "figure"]
    py_figs = [a for a in figs if a.producer.type == "py-script"]
    assert py_figs, "expected >=1 py-script figure in subset-sum-itqde"
    # the producer path must exist on disk (filesystem-first, verifiable)
    a = py_figs[0]
    assert a.producer.path is not None
    assert (REPO / a.producer.path).is_file(), a.producer.path
    # a py-script figure is only admitted when it has a rendered sibling
    assert a.rendered, "a py-script figure must carry its rendered output(s)"
    for r in a.rendered:
        assert (REPO / r).is_file(), r


@pytest.mark.skipif(not _project_present("subset-sum-itqde"),
                    reason="subset-sum-itqde tree absent")
def test_subset_sum_has_derivation_with_step_anchor():
    assets = enumerate_assets("subset-sum-itqde")
    ders = [a for a in assets if a.kind == "derivation"]
    assert ders, "expected >=1 derivation walk in subset-sum-itqde"
    stepped = [a for a in ders if a.steps]
    assert stepped, "expected >=1 derivation with >=1 step anchor"
    a = stepped[0]
    assert (REPO / a.producer.path).is_file()
    assert a.producer.type == "tex-inline"
    # every step is a concrete anchor with a line range
    for st in a.steps:
        assert st.id
        assert st.line_start is not None and st.line_end is not None
        assert st.line_end >= st.line_start


@pytest.mark.skipif(not _project_present("subset-sum-itqde"),
                    reason="subset-sum-itqde tree absent")
def test_subset_sum_ledger_enrichment_when_present():
    # when the friction ledger is on disk, at least one figure links to its
    # conceptric node (nodes_supported) and at least one carries data inputs.
    assets = enumerate_assets("subset-sum-itqde")
    figs = [a for a in assets if a.kind == "figure"]
    if (REPO / "corpus_friction" / "subset-sum-itqde.jsonl").is_file():
        assert any(a.nodes_supported for a in figs), \
            "ledger present but no figure linked to conceptric nodes"


# --------------------------------------------------------------------------- #
# eigenengine: hand-tikz figures, NO derivations (honest), nodemap landings.
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _project_present("eigenengine"),
                    reason="eigenengine tree absent")
def test_eigenengine_has_hand_tikz_figure():
    assets = enumerate_assets("eigenengine")
    figs = [a for a in assets if a.kind == "figure"]
    tikz = [a for a in figs if a.producer.type == "hand-tikz"]
    assert tikz, "expected >=1 hand-tikz figure in eigenengine"
    a = tikz[0]
    assert a.producer.path is not None and (REPO / a.producer.path).is_file()


@pytest.mark.skipif(not _project_present("eigenengine"),
                    reason="eigenengine tree absent")
def test_eigenengine_derivations_empty_honestly():
    assets = enumerate_assets("eigenengine")
    ders = [a for a in assets if a.kind == "derivation"]
    assert ders == [], "eigenengine has no derivation walks — must be honestly empty"


# --------------------------------------------------------------------------- #
# THE INSTRUCTIVE EMPTY BRIEF (assets_surface) — an empty corpus states WHY it is
# empty and WHERE its assets will land, keyed on real project state (never-run vs
# built-but-unmanifested). The reason lives in the prose, not only in a tooltip.
# --------------------------------------------------------------------------- #

def test_empty_brief_never_run_states_reason_and_path():
    """paper_eigen enumerates to zero and its figures dir is absent on disk (never-run):
    the composed glance must name the reason (pipeline not built) AND the surfacing path,
    and carry an ask — never a bare '… carries 0 assets.'."""
    from laplace.web import assets_surface as asf
    bp = asf.brief_payload("paper_eigen")
    if bp is None or bp["counts"]["total"] != 0:
        pytest.skip("paper_eigen not present / not empty in this checkout")
    roots = am.asset_roots("paper_eigen")
    if (REPO / roots.figures[0]).is_dir():
        pytest.skip("paper_eigen figures dir exists — not the never-run state")
    glance = bp["brief"]["glance"].lower()
    assert "no assets yet" in glance and "not built" in glance, (
        "the empty glance must state the reason (pipeline not built), not just the count: " + glance)
    assert roots.figures[0].lower() in glance, (
        "the empty glance must name the figures path so the state is instructive: " + glance)
    assert bp["brief"]["ask"], "an empty corpus must still carry the one instructive ask"


def test_empty_brief_built_state_distinguished_from_never_run():
    """When the asset SOURCE dirs already exist on disk but nothing enumerates, the brief
    reads the 'built but unmanifested' reason — distinct wording from never-run — via the
    real disk-state classifier. Driven directly over _compose_brief with a roots whose
    figures glob points at an existing (asset-empty) repo dir."""
    from laplace.web import assets_surface as asf
    from laplace.pipeline.asset_model import AssetRoots
    existing = "tests"  # a real dir with no figure producers → 'built', not 'never-run'
    assert (REPO / existing).is_dir()
    roots = AssetRoots(figures=(existing,), derivations=(), figure_producer="auto", nodemap=None)
    glance, ask = asf._compose_brief("paper_eigen", [], [], [], roots=roots, root=REPO)
    assert "no assets yet" in glance.lower()
    assert "on disk" in glance.lower() and "manifest" in glance.lower(), (
        "the built-but-unmanifested glance must say the tree is on disk / unmanifested: " + glance)
    assert existing in glance, "the built glance must name the source path: " + glance
    assert ask, "the built empty state must still carry an ask"
    # and the never-run branch is genuinely different wording (the states are distinguished)
    roots_nr = AssetRoots(figures=("no/such/dir/anywhere",), derivations=(),
                          figure_producer="auto", nodemap=None)
    glance_nr, _ = asf._compose_brief("paper_eigen", [], [], [], roots=roots_nr, root=REPO)
    assert "not built" in glance_nr.lower() and "on disk" not in glance_nr.lower(), (
        "never-run must read distinctly from built-but-unmanifested: " + glance_nr)


@pytest.mark.skipif(not _project_present("eigenengine"),
                    reason="eigenengine tree absent")
def test_eigenengine_nodemap_landings_wired_when_present():
    # eigenengine ships a main.nodemap.json; at least one figure should carry a
    # measured/inferred landing off it.
    roots = am.asset_roots("eigenengine")
    if roots.nodemap and (REPO / roots.nodemap).is_file():
        assets = enumerate_assets("eigenengine")
        figs = [a for a in assets if a.kind == "figure"]
        landed = [a for a in figs if a.landings]
        assert landed, "nodemap present but no figure carries a landing"
        ld = landed[0].landings[0]
        assert ld.page is not None
        assert ld.source == "nodemap"
