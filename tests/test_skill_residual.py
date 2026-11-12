"""The query-conditioned skill residual: the registered definition, held in place by tests.

Every number the fitness swap is read off comes out of these pure parts - the query
construction, the name blinding, the rank statistic, and (in the join) the threshold-to-rank
mapping. The registered definition is
``evidence/FITNESS_SWAP_REPLAY_2026-08-20/query_conditioned/definition.md``; these tests are
what stops it drifting silently after the fact. Nothing here loads a model or a network.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from laplace.engine import skill_residual as sr

ROOT = Path(__file__).resolve().parents[1]
QC = ROOT / "evidence/FITNESS_SWAP_REPLAY_2026-08-20/query_conditioned"


SKILL_TEXT = """---
name: widget_forge
description: "[EXPERIMENTAL] Forge a widget from a blueprint when the assembly has no widget of the required class."
consistency:
  - canon://x | supports | y
---
# widget_forge

## Purpose
The assembly stalls whenever a required widget class is absent from the shelf and nobody notices.
Short.

## When to run it
- Run it when the blueprint names a widget class the shelf cannot supply from stock.
- tiny
- Run it again after any blueprint revision that introduces a new widget class entirely.

## Backing
- This section must never contribute a query because its heading is not a trigger heading.
"""


def test_description_strips_status_tag_and_quotes():
    desc = sr.description_of(SKILL_TEXT)
    assert desc is not None
    assert desc.startswith("Forge a widget from a blueprint")
    assert "EXPERIMENTAL" not in desc and '"' not in desc


def test_trigger_items_take_only_trigger_headings_and_drop_fragments():
    items = sr.trigger_items(SKILL_TEXT)
    assert len(items) == sr.TRIGGER_ITEMS
    assert all(len(i) >= sr.MIN_ITEM_CHARS for i in items)
    assert not any("never contribute a query" in i for i in items), "Backing is not a trigger heading"
    assert any(i.startswith("The assembly stalls") for i in items), "Purpose is a trigger heading"
    assert not any(i == "tiny" for i in items)


def test_name_blinding_removes_snake_and_spaced_forms():
    blinded = sr.name_blind("The Widget Forge forges: widget_forge is the widget_forge.", "widget_forge")
    assert "widget_forge" not in blinded.lower()
    assert "widget forge" not in blinded.lower()


def test_build_queries_is_capped_and_blinded(tmp_path):
    (tmp_path / "src/laplace/pipeline/canon/skills/widget_forge").mkdir(parents=True)
    (tmp_path / "src/laplace/pipeline/canon/skills/widget_forge/SKILL.md").write_text(SKILL_TEXT)
    qs = sr.build_queries(tmp_path, "widget_forge",
                          "src/laplace/pipeline/canon/skills/widget_forge/SKILL.md")
    assert len(qs) == sr.Q_MAX
    assert qs[0]["source"] == "description"
    assert [q["source"] for q in qs[1:]] == ["trigger"] * (sr.Q_MAX - 1)
    assert all("widget_forge" not in q["text"].lower() for q in qs)
    assert all(len(q["text"]) <= sr.TEXT_CAP for q in qs)


def test_reciprocal_rank_and_residual_are_the_registered_statistic():
    assert sr.reciprocal_rank(1) == 1.0
    assert sr.reciprocal_rank(4) == 0.25
    assert sr.reciprocal_rank(None) == 0.0, "absence is the strongest residual, never a drop"
    assert sr.residual([1, 1]) == pytest.approx(0.0)
    assert sr.residual([None, None]) == pytest.approx(1.0)
    assert sr.residual([2, None]) == pytest.approx(0.75)


def test_residual_refuses_an_empty_query_set():
    with pytest.raises(ValueError):
        sr.residual([])


def test_rank_of_reads_the_router_answer_list():
    files = [{"file": "a"}, {"file": "b"}, {"file": "c"}]
    assert sr.rank_of(files, "a") == 1
    assert sr.rank_of(files, "c") == 3
    assert sr.rank_of(files, "z") is None


def test_proposals_sink_redirects_and_restores():
    from laplace.representation import embed_router
    before = embed_router.PROPOSALS_FILE
    with sr.proposals_sink("/tmp/laplace-test-sink.jsonl"):
        assert embed_router.PROPOSALS_FILE.endswith("laplace-test-sink.jsonl")
    assert embed_router.PROPOSALS_FILE == before


def test_the_instrument_is_blind_to_the_lifecycle_ledger():
    """The blind protocol is structural, not a promise: the instrument has no DATA PATH to the
    answer. Prose may name the ledger (the module explains why the archive is in scope); code
    may not open it, import it, or name its file."""
    import ast

    source = Path(sr.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = (node.body or [None])[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported |= {f"{node.module}.{a.name}" for a in node.names}
    for forbidden in ("laplace.engine.assess", "laplace.engine.dreamer", "yaml"):
        assert forbidden not in imported, f"the instrument imports {forbidden!r}"
    # no string the CODE uses (docstrings are prose, and explain the blindness) may reach the
    # ledger: not its file, not its directory, not any yaml at all
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            low = node.value.lower()
            if low.endswith((".yaml", ".yml")) or "lifecycle" in low:
                pytest.fail(f"the instrument carries a path into the answer: {node.value!r}")


def test_candidate_population_covers_the_archive():
    names = dict(sr.candidate_skills(ROOT))
    assert len(names) >= 50
    assert any("_archive" in path for path in names.values()), "archived skills stay in scope"


# --- the join's mapping (definition.md 6) ----------------------------------------------

def _join_module():
    spec = importlib.util.spec_from_file_location("join_replay", QC / "join_replay.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_swap_preserves_the_incumbent_margin_and_flips_in_pairs():
    join = _join_module()
    pop = [{"skill": s, "banked": b, "at": "t"} for s, b in
           [("a", "PROMOTE"), ("b", "PROMOTE"), ("c", "DEPRECATE"), ("d", "DEPRECATE")]]
    # residual order d > c > b > a: the swap promotes d and c, demotes a and b -> 4 flips
    res = join.swap(pop, {"a": 0.1, "b": 0.2, "c": 0.8, "d": 0.9})
    assert res["m_promote"] == 2
    assert res["flips"] == 4
    assert res["flips"] % 2 == 0
    assert res["reachable_flip_values"] == [0, 2, 4]
    assert res["meets_bar"] is True


def test_swap_agreeing_with_the_incumbent_flips_nothing():
    join = _join_module()
    pop = [{"skill": s, "banked": b, "at": "t"} for s, b in
           [("a", "PROMOTE"), ("b", "DEPRECATE")]]
    res = join.swap(pop, {"a": 0.9, "b": 0.1})
    assert res["flips"] == 0 and res["meets_bar"] is False


def test_a_tie_straddling_the_cut_is_reported_not_resolved_by_alphabet():
    join = _join_module()
    pop = [{"skill": s, "banked": b, "at": "t"} for s, b in
           [("a", "PROMOTE"), ("b", "DEPRECATE")]]
    res = join.swap(pop, {"a": 0.5, "b": 0.5})
    assert res["ambiguities"], "an alphabetical tie-break must never decide a flip silently"


def test_the_classification_audit_catches_a_silence_read_that_ends_in_core():
    join = _join_module()
    rows = [{"skill": "s", "at": "t", "from": "experimental", "to": "core",
             "reason": "offered 12x, never used - but the read was a name-binding artifact"}]
    flags = join.audit(rows)
    assert len(flags) == 1 and flags[0]["honest_class"] == "correction"


def test_the_registered_definition_predates_the_rows():
    """Prereg discipline, checked mechanically: the definition file exists, and if the rows
    exist they came after it."""
    definition = QC / "definition.md"
    assert definition.is_file(), "the definition is the prereg; it is not optional"
    rows = QC / "rows_qc.json"
    if rows.is_file():
        assert definition.stat().st_mtime <= rows.stat().st_mtime
        payload = json.loads(rows.read_text(encoding="utf-8"))
        assert payload["definition"].endswith("definition.md")
