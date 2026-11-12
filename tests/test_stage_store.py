"""test_stage_store.py — the two demo lenses + the namespaced writer (design §1c, §2.2/§2.3, §3).

Hermetic and fast BY CONSTRUCTION: these tests build a tiny SYNTHETIC conceptric net by hand,
never the real ``corpus_ingest.build_corpus_network`` over real .tex (that is the demo driver's
job — ``scripts/demo_stage_stores.py``). What is under test here is the VIEW law and the
isolation law, both of which are pure functions of the net + the write API:

  * view rows carry node-traceable ``span_ref`` and his-real-prose ``embed_text`` (no invented
    text — every surfaced id is a real node, every embed_text is a net value);
  * the derivers are DETERMINISTIC over the same net (the property the seeded holdout gate rests
    on);
  * ``write_store`` namespacing is MECHANICAL — a writer writes only its own paper's JSONL, and a
    foreign-paper row is refused, not written (design §3: isolation is not trusted).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from laplace.pipeline import stage_store

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_stage0():
    """Load ``scripts/stage0_ancestor_inventory.py`` as a module (scripts/ is not a package),
    without polluting the import table — the stage-zero inventory logic under test."""
    path = _REPO_ROOT / "scripts" / "stage0_ancestor_inventory.py"
    spec = importlib.util.spec_from_file_location("stage0_ancestor_inventory", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# --------------------------------------------------------------------------- #
# a tiny synthetic conceptric net (NOT a real build — fast, hermetic)
# --------------------------------------------------------------------------- #
def _synthetic_net() -> dict:
    """A hand-built net in the shape ``build_corpus_network`` returns: two sections (one with
    two equations laddering base->step), a figure under the intro, containment via
    ``members``/``parent``, explicit edges in ``edge_index`` (a cross-section ``\\ref``, a
    ``\\ref{fig:demo}``, and an eq->eq dependency), plus the demo driver's enrichment
    (``section_prose`` / ``section_meta`` / ``source_file``)."""
    nodes = {
        "paper://": {"kind": "paper", "essence": "the paper", "parent": None, "leaf": False,
                     "members": ["sec:intro", "sec:method", "references"]},
        "references": {"kind": "references", "essence": "bib", "parent": "paper://",
                       "leaf": False, "members": []},
        "sec:intro": {"kind": "section", "essence": "Introduction \\label{sec:intro}",
                      "parent": "paper://", "leaf": False, "members": ["fig:demo"]},
        "sec:method": {"kind": "section", "essence": "The Method \\label{sec:method}",
                       "parent": "paper://", "leaf": False, "members": ["eq:base", "eq:step"]},
        "eq:base": {"kind": "equation", "essence": "a = b", "parent": "sec:method",
                    "leaf": True, "members": []},
        "eq:step": {"kind": "equation", "essence": "c = a + 1", "parent": "sec:method",
                    "leaf": True, "members": []},
        "fig:demo": {"kind": "figure", "parent": "sec:intro", "leaf": True, "members": [],
                     "essence": "Comparison of the two constructions over time, showing convergence."},
    }
    edge_index = {
        "sec:intro": ["sec:intro"],
        # method \ref's intro (a later->earlier ref) and \ref's the intro's figure
        "sec:method": ["sec:method", "sec:intro", "fig:demo"],
        "eq:base": ["eq:base"],
        "eq:step": ["eq:step", "eq:base", "sem::eq:base"],  # step derives from base (+ audit marker)
        "fig:demo": ["fig:demo"],
    }
    return {
        "nodes": nodes, "edge_index": edge_index, "postulates": set(), "spine": [],
        "ctx": {"eq:step": "We now derive the next step from the base equation."},
        "section_prose": {
            "sec:intro": "This is the real introduction prose, his own words about the topic.",
            "sec:method": "The method section prose describing the derivation in his voice.",
        },
        "section_meta": {
            "sec:intro": {"idx": 0, "title": "Introduction", "label": "sec:intro",
                          "char_start": 10, "char_end": 90, "para_count": 2},
            "sec:method": {"idx": 1, "title": "The Method", "label": "sec:method",
                           "char_start": 90, "char_end": 300, "para_count": 3},
        },
        "source_file": "voice_corpus/exemplars/synthetic/main.tex",
        "paper_id": "synthetic-paper",
    }


PAPER = "synthetic-paper"


# --------------------------------------------------------------------------- #
# the view law — node-traceable span_ref, real-prose embed_text, no invented text
# --------------------------------------------------------------------------- #
def test_section_rows_are_node_traceable_and_use_real_prose():
    net = _synthetic_net()
    rows = stage_store.derive_section_architecture(net, PAPER)
    assert len(rows) == 2                                  # one row per real section node
    node_ids = set(net["nodes"])
    prose_values = set(net["section_prose"].values())
    for r in rows:
        # the view law: every span_ref node id is a REAL conceptric node
        assert r["provenance"]["span_ref"]["node_ids"]
        for nid in r["provenance"]["span_ref"]["node_ids"]:
            assert nid in node_ids, f"span_ref names a non-node {nid!r}"
        # no free text invented: embed_text IS one of the net's own section-prose values
        assert r["embed_text"] in prose_values
        assert r["provenance"]["extraction_lens"] == "section_architecture"
        assert r["provenance"]["paper_id"] == PAPER


def test_section_form_fields_are_mechanical_and_residue_is_null():
    net = _synthetic_net()
    rows = {r["form"]["title"]: r for r in stage_store.derive_section_architecture(net, PAPER)}
    intro, method = rows["Introduction"], rows["The Method"]
    # mechanical position / carries / forward_reach / job proxy
    assert intro["form"]["position"] == "1-of-2"
    assert intro["form"]["job"] == "introduce"            # idx 0 -> introduce
    # sec:method \ref's sec:intro, and method is LATER -> intro is used by 1 later section
    assert intro["form"]["forward_reach"] == "used-by-1-later-sections"
    assert method["form"]["job"] == "method"              # title keyword
    assert method["form"]["carries"] == {"equations": 2, "figures": 0}
    assert method["form"]["para_count"] == 3
    # the model-read residue is emitted None, never fabricated
    assert intro["form"]["arc"] is None
    assert intro["form"]["question_class"] is None


def test_spine_rows_are_node_traceable_dag_paths():
    net = _synthetic_net()
    rows = stage_store.derive_spine_chain(net, PAPER)
    assert len(rows) == 1                                  # only eq:step has an eq-dependency
    r = rows[0]
    assert r["provenance"]["span_ref"]["node_ids"] == ["eq:step", "eq:base"]
    assert r["provenance"]["span_ref"]["section_node"] == "sec:method"
    assert r["form"]["ladder_move"] == "extend"           # a single dependency
    assert r["form"]["rung"] == 1 and r["form"]["depends_on_rung"] == 0
    # embed_text is node-derived (the ctx lead-in + the display LaTeX), his real content
    assert "derive the next step" in r["embed_text"]
    assert r["form"]["claim_class"] is None                # model residue
    # the audit marker sem::eq:base is NEVER surfaced as a dependency node id
    assert "sem::eq:base" not in r["provenance"]["span_ref"]["node_ids"]


# --------------------------------------------------------------------------- #
# LENS 3 — derivation-walk: one row per step on the eq-dependency walk (design §2.4)
# --------------------------------------------------------------------------- #
def test_derivation_walk_rows_are_node_traceable_dag_steps():
    net = _synthetic_net()
    rows = stage_store.derive_derivation_walk(net, PAPER)
    # the walk = eqs that stand on a rung OR are a prerequisite: eq:base (prereq) + eq:step (step)
    assert len(rows) == 2
    by_eq = {r["provenance"]["span_ref"]["node_ids"][0]: r for r in rows}
    base, step = by_eq["eq:base"], by_eq["eq:step"]

    # eq:base is the floor: no eq-dependency -> a mechanical "define" step, rung 0, no prereq
    assert base["form"]["step_kind"] == "define"
    assert base["form"]["rung"] == 0 and base["form"]["prereq_kind"] == "none"
    assert base["form"]["rung_span"] == [0, 0]
    assert base["provenance"]["span_ref"]["node_ids"] == ["eq:base"]
    assert base["provenance"]["span_ref"]["section_node"] == "sec:method"

    # eq:step derives from one prerequisite -> "advance", rung 1, span [0,1]; the prereq (eq:base)
    # has no deps of its own so it is a base-equation, not a prior-step
    assert step["form"]["step_kind"] == "advance"
    assert step["form"]["rung"] == 1 and step["form"]["of_rungs"] == 1
    assert step["form"]["rung_span"] == [0, 1]
    assert step["form"]["prereq_kind"] == "base-equation"
    assert step["form"]["n_prereqs"] == 1 and step["form"]["carries_eq"] is True
    # the view law: span_ref is the step node + its prerequisite node ids (no invented text)
    assert step["provenance"]["span_ref"]["node_ids"] == ["eq:step", "eq:base"]
    node_ids = set(net["nodes"])
    for nid in step["provenance"]["span_ref"]["node_ids"]:
        assert nid in node_ids
    # embed_text is node-derived (ctx lead-in + display LaTeX)
    assert "derive the next step" in step["embed_text"]
    # the audit marker is never surfaced as a dependency node id
    assert "sem::eq:base" not in step["provenance"]["span_ref"]["node_ids"]
    # the model-read residue is emitted None, never fabricated
    for f in ("granularity", "elision", "eq_env"):
        assert step["form"][f] is None
    assert step["provenance"]["extraction_lens"] == "derivation_walk"


# --------------------------------------------------------------------------- #
# LENS 4 — figure-caption: one row per figure node (design §2.5)
# --------------------------------------------------------------------------- #
def test_figure_caption_rows_are_node_traceable_and_mechanical():
    net = _synthetic_net()
    rows = stage_store.derive_figure_caption(net, PAPER)
    assert len(rows) == 1                                  # one figure node in the net
    r = rows[0]
    # the view law: span_ref names the real figure node, its section, and the referencing sections
    assert r["provenance"]["span_ref"]["node_ids"] == ["fig:demo"]
    assert r["provenance"]["span_ref"]["section_node"] == "sec:intro"
    assert r["provenance"]["span_ref"]["referenced_by"] == ["sec:method"]  # sec:method \ref's fig:demo
    for nid in [*r["provenance"]["span_ref"]["node_ids"], *r["provenance"]["span_ref"]["referenced_by"]]:
        assert nid in net["nodes"]
    # mechanical: caption presence/length + referenced-from-sections via the net's edges
    assert r["form"]["has_caption"] is True
    assert r["form"]["referenced_by_sections"] == 1
    assert r["form"]["ref_density"] == "referenced-by-1-sections"
    assert r["form"]["caption_size"] in ("terse", "standard", "expansive")
    assert r["form"]["caption_len"] == len(net["nodes"]["fig:demo"]["essence"])
    # embed_text is the figure's REAL caption prose (node-derived, no invented text)
    assert r["embed_text"] == net["nodes"]["fig:demo"]["essence"]
    # the model-read residue is emitted None, never fabricated
    for f in ("caption_move", "figure_role", "panels", "panel_labels"):
        assert r["form"][f] is None
    assert r["provenance"]["extraction_lens"] == "figure_caption"


# --------------------------------------------------------------------------- #
# determinism — same net -> byte-identical rows
# --------------------------------------------------------------------------- #
def test_derivers_are_deterministic():
    net_a, net_b = _synthetic_net(), _synthetic_net()
    assert (stage_store.derive_section_architecture(net_a, PAPER)
            == stage_store.derive_section_architecture(net_b, PAPER))
    assert (stage_store.derive_spine_chain(net_a, PAPER)
            == stage_store.derive_spine_chain(net_b, PAPER))
    assert (stage_store.derive_derivation_walk(net_a, PAPER)
            == stage_store.derive_derivation_walk(net_b, PAPER))
    assert (stage_store.derive_figure_caption(net_a, PAPER)
            == stage_store.derive_figure_caption(net_b, PAPER))
    # and stable across repeated calls on the SAME (dep_grade-mutated) net object
    net = _synthetic_net()
    for deriver in (stage_store.derive_spine_chain, stage_store.derive_derivation_walk,
                    stage_store.derive_figure_caption):
        assert deriver(net, PAPER) == deriver(net, PAPER)


# --------------------------------------------------------------------------- #
# the namespacing law — mechanical isolation, not trusted
# --------------------------------------------------------------------------- #
def test_write_store_namespacing_is_per_paper(tmp_path):
    net = _synthetic_net()
    rows_a = stage_store.derive_section_architecture(net, "paper-A")  # net paper_id is ignored;
    rows_b = stage_store.derive_section_architecture(net, "paper-B")  # provenance is stamped per call
    stage_store.write_store("section_architecture", "paper-A", rows_a, stores_root=tmp_path)
    store_dir = tmp_path / "section_architecture"
    assert (store_dir / "paper-A.jsonl").is_file()
    assert not (store_dir / "paper-B.jsonl").exists()     # A's write cannot touch B's file

    # B's write leaves A's file intact and BOTH land in the merged index (the fan-in)
    stage_store.write_store("section_architecture", "paper-B", rows_b, stores_root=tmp_path)
    assert (store_dir / "paper-A.jsonl").is_file() and (store_dir / "paper-B.jsonl").is_file()
    index = json.loads((store_dir / "_index.json").read_text())
    assert {p["paper_id"] for p in index["papers"]} == {"paper-A", "paper-B"}
    assert index["row_count"] == len(rows_a) + len(rows_b)
    assert all("embed_text" not in r for r in index["rows"])   # the index carries no his-prose


def test_write_store_refuses_foreign_paper_rows(tmp_path):
    """A row whose provenance.paper_id differs from the write's namespace is refused — the
    contamination is a filesystem impossibility, not a trust assumption (design §3)."""
    net = _synthetic_net()
    rows = stage_store.derive_section_architecture(net, "paper-A")
    with pytest.raises(ValueError, match="namespaced"):
        stage_store.write_store("section_architecture", "paper-B", rows, stores_root=tmp_path)
    # nothing was written for the mismatched namespace
    assert not (tmp_path / "section_architecture" / "paper-B.jsonl").exists()


# --------------------------------------------------------------------------- #
# STAGE ZERO — the ancestor import (design §1b): the inherited:: marker + namespacing
# --------------------------------------------------------------------------- #
def _inherited_rows(paper_id: str) -> list[dict]:
    """Two minimal paragraph_plan-shaped rows carrying NO extraction_lens yet — the import stamps
    the inherited marker. (A row with no provenance.paper_id is stamped to the write's namespace.)"""
    return [
        {"row_id": f"PP-{paper_id}-p1", "embed_text": "his real paragraph prose one.",
         "form": {"role": None}, "provenance": {"source_kind": "tex",
          "span_ref": {"file": "voice_corpus/exemplars/x/main.tex", "char_start": 0, "char_end": 30,
                       "paragraph_index": 1}}},
        {"row_id": f"PP-{paper_id}-p2", "embed_text": "his real paragraph prose two.",
         "form": {"role": None}, "provenance": {"source_kind": "tex",
          "span_ref": {"file": "voice_corpus/exemplars/x/main.tex", "char_start": 31, "char_end": 60,
                       "paragraph_index": 2}}},
    ]


def test_import_inherited_stamps_the_inherited_marker(tmp_path):
    """Every imported row carries provenance.extraction_lens = inherited::<source> — the sem::
    discipline applied to inheritance, so a salvaged row is forever distinguishable from a fresh
    lens read (design §1b step 2)."""
    rows = _inherited_rows("paper-A")
    stage_store.import_inherited("paragraph_plan", "paper-A", rows, "voice_corpus",
                                 stores_root=tmp_path)
    jsonl = tmp_path / "paragraph_plan" / "paper-A.jsonl"
    written = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(written) == 2
    for r in written:
        assert r["provenance"]["extraction_lens"] == "inherited::voice_corpus"
        assert r["provenance"]["extraction_lens"].startswith(stage_store.INHERITED_PREFIX)
        assert r["provenance"]["inherited_from"] == "voice_corpus"
        assert r["provenance"]["paper_id"] == "paper-A"          # stamped to the write's namespace
        assert stage_store.is_inherited(r)                        # never mistaken for a fresh read
        assert r["embed_text"]                                    # his real prose survives (the basis)
    # the marker is NEVER a plain lens name — an inherited row is not a paragraph_plan lens row
    assert all(r["provenance"]["extraction_lens"] != "paragraph_plan" for r in written)
    # the caller's rows were not mutated (import copies before stamping)
    assert "extraction_lens" not in rows[0]["provenance"]


def test_import_inherited_cannot_cross_paper_namespaces(tmp_path):
    """An import CANNOT cross paper namespaces: a row already tagged for paper-A, imported under
    namespace paper-B, is REFUSED (write_store raises), never written — the isolation law holds by
    construction, reused not re-implemented (design §3)."""
    rows = _inherited_rows("paper-A")
    for r in rows:                          # tag them for A explicitly
        r["provenance"]["paper_id"] = "paper-A"
    with pytest.raises(ValueError, match="namespaced"):
        stage_store.import_inherited("paragraph_plan", "paper-B", rows, "voice_corpus",
                                     stores_root=tmp_path)
    assert not (tmp_path / "paragraph_plan" / "paper-B.jsonl").exists()   # nothing written


# --------------------------------------------------------------------------- #
# STAGE ZERO — the inventory JSON is valid + covers all four ancestors x five stores
# --------------------------------------------------------------------------- #
def test_ancestor_inventory_covers_all_four_ancestors():
    """The stage-zero inventory verdicts EVERY (ancestor x store) cell mechanically: 4 ancestors x
    5 stores = 20 cells, each with a verdict in {import, leave, retire} and a reason (design §1b).
    build_inventory is read-only — it writes nothing."""
    stage0 = _load_stage0()
    inv = stage0.build_inventory(_REPO_ROOT)

    assert inv["schema"] == "stage0-ancestor-inventory/0.1"
    assert set(inv["ancestors"]) == {
        "life_corpus_distillates", "voice_corpus_passages",
        "collaborator_structurals", "reference_bib_substrate"}
    assert inv["stores"] == ["paragraph_plan", "section_architecture", "spine_chain",
                             "derivation_walk", "figure_caption"]
    # exactly 4 x 5 cells, each a valid typed verdict with the required keys
    assert len(inv["matrix"]) == 4 * 5
    seen = set()
    for cell in inv["matrix"]:
        assert {"ancestor", "store", "verdict", "supplies", "import_candidates", "reason"} <= set(cell)
        assert cell["verdict"] in {"import", "leave", "retire"}
        assert cell["reason"]
        seen.add((cell["ancestor"], cell["store"]))
    assert len(seen) == 20                                  # every cell present exactly once

    # the honest outcome the census predicts: voice->paragraph_plan is the ONE import; the
    # distillates/collaborators/bib are content/contrast/substrate -> leave; nothing dead -> no retire.
    imports = [c for c in inv["matrix"] if c["verdict"] == "import"]
    assert len(imports) == 1
    assert (imports[0]["ancestor"], imports[0]["store"]) == ("voice_corpus_passages", "paragraph_plan")
    assert imports[0]["import_candidates"] == 260
    assert all(c["verdict"] == "leave"
               for c in inv["matrix"] if c["ancestor"] == "life_corpus_distillates")
    assert not inv["proposed_retirements"]                  # nothing superseded-and-dead this stage


def test_ancestor_inventory_file_on_disk_is_valid_if_present():
    """If stage zero has been RUN (the committed artifact exists), the on-disk inventory JSON is
    valid and covers all four ancestors — the artifact matches the live logic."""
    path = stage_store.CORPUS_STORES / "ancestor_inventory.json"
    if not path.is_file():
        pytest.skip("ancestor_inventory.json not generated in this tree")
    inv = json.loads(path.read_text())
    assert inv["schema"] == "stage0-ancestor-inventory/0.1"
    assert len(inv["matrix"]) == 20
    assert set(inv["ancestors"]) == {
        "life_corpus_distillates", "voice_corpus_passages",
        "collaborator_structurals", "reference_bib_substrate"}
    # if imports were executed, every imported row is provenance-marked inherited::
    for imp in inv.get("imports_executed", []):
        assert imp["extraction_lens"].startswith("inherited::")


# --------------------------------------------------------------------------- #
# THE STORES KEEP THE MATH (WO-20260820-extraction-lens-keeps-math) — corpus guard
# --------------------------------------------------------------------------- #
def _repo_store(name):
    from pathlib import Path
    d = Path(__file__).resolve().parents[1] / "corpus_stores" / name
    return sorted(d.glob("*.jsonl")) if d.is_dir() else []


@pytest.mark.parametrize("store", ["section_architecture", "paragraph_plan"])
def test_stored_lenses_still_carry_the_math(store):
    """The standing guard on the repaired stores: the two lenses that USED to strip math must
    carry it. The bench's failure mode was silent — a mutilated row is still grammatical — so the
    only honest signal is whether math survives at all, per paper. A regression of the strip (or a
    re-mint through the default rendering) lights this up on the paper that lost it.

    The threshold is the work order's own accept probe: at most 5 of the corpus's papers may carry
    no math token at all (a genuinely math-free paper exists; twenty do not)."""
    import json
    import re

    files = _repo_store(store)
    if not files:
        pytest.skip(f"corpus_stores/{store} not present in this checkout")
    pattern = re.compile(r"\\[a-zA-Z]+|\d+\s*(eV|THz|ps|fs|nm|MV/cm)")
    bare = [f.stem for f in files
            if not any(pattern.search(json.loads(ln).get("embed_text", ""))
                       for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip())]
    assert len(bare) <= 5, f"{store}: {len(bare)} papers carry no math at all — {bare}"
