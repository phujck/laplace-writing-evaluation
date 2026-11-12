"""F29 — build_conceptric term-grounding widened to derivation-step sources.

The term-grounding loop grounded def terms only from claim nodes and result
shells (kind=="node"). F29 widens the SOURCE set to irf:/thm:/ds: nodes (IRFs,
theorems, derivation steps), same lowercase-term-in-text test over label + meta
text/summary, same 'draws' edge, add() deduping.

All fixtures are mini substrate+blueprint markdown under tmp_path — no live
corpus, no edge-baseline movement.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_BUILD = (_REPO / "src" / "laplace" / "pipeline" / "canon" / "skills"
          / "conceptric_coherence" / "scripts" / "build_conceptric.py")


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


bc = _load(_BUILD)


def _write(tmp_path: Path, substrate: str, blueprint: str) -> tuple[str, str]:
    sp = tmp_path / "substrate.md"
    bp = tmp_path / "blueprint.md"
    sp.write_text(substrate, encoding="utf-8")
    bp.write_text(blueprint, encoding="utf-8")
    return str(sp), str(bp)


def _draws(graph: dict, src: str, dst: str) -> list[dict]:
    return [e for e in graph["edges"]
            if e["src"] == src and e["dst"] == dst and e["rel"] == "draws"]


# The def node supplies the term "widget"; irf/thm/ds nodes name it in label or
# summary; ds:step-silent names nothing groundable; ds:dup-widget names it twice.
_SUBSTRATE = """# Substrate: F29 fixture

## def:widget | widget: a small reusable thing | kind:def
summary: defines the widget term

## irf:bound | IRF one | kind:intermediate-result
summary: this bound constrains the widget under load

## thm:identity | Theorem naming widget | kind:theorem
summary: an exact identity

## ds:step-widget | Derivation step | kind:derivation-step
summary: substituting the widget into the recurrence

## ds:step-silent | Derivation step | kind:derivation-step
summary: this step mentions nothing groundable

## ds:dup-widget | Derivation step | kind:derivation-step
summary: widget here and again widget there
"""

_BLUEPRINT_MIN = "- thesis: F29 fixture spine\n"


def test_irf_node_grounds_via_summary(tmp_path):
    """(a) an irf: node whose text names a def term -> edge appears."""
    sp, bp = _write(tmp_path, _SUBSTRATE, _BLUEPRINT_MIN)
    g = bc.build(sp, bp)
    assert _draws(g, "irf:bound", "def:widget"), "irf: source did not ground the term"


def test_thm_and_ds_nodes_ground(tmp_path):
    """(b) a thm: node (term in label) and a ds: node (term in summary) ground."""
    sp, bp = _write(tmp_path, _SUBSTRATE, _BLUEPRINT_MIN)
    g = bc.build(sp, bp)
    assert _draws(g, "thm:identity", "def:widget"), "thm: source (label) did not ground"
    assert _draws(g, "ds:step-widget", "def:widget"), "ds: source (summary) did not ground"


def test_node_not_naming_term_has_no_edge(tmp_path):
    """(c) a deriv node that does not name the term -> no edge."""
    sp, bp = _write(tmp_path, _SUBSTRATE, _BLUEPRINT_MIN)
    g = bc.build(sp, bp)
    assert not _draws(g, "ds:step-silent", "def:widget"), "silent node grounded spuriously"


def test_dedup_two_mentions_one_edge(tmp_path):
    """(e) the same (source, def) pair from two mentions -> exactly one edge."""
    sp, bp = _write(tmp_path, _SUBSTRATE, _BLUEPRINT_MIN)
    g = bc.build(sp, bp)
    assert len(_draws(g, "ds:dup-widget", "def:widget")) == 1, "dedup failed"


# (d) pre-existing claim/shell behavior is byte-identical: with NO irf/thm/ds
# nodes present, the widened code path must add ZERO edges. Fixture has only a
# def node, a result shell (kind==node), and a blueprint claim — the classic
# two sources — all naming the term.
_SUBSTRATE_NODERIV = """# Substrate: F29 no-deriv fixture

## def:widget | widget: a small reusable thing | kind:def
summary: defines the widget term

## res:shell | Result shell | kind:node
summary: the widget bounds this result
"""

_BLUEPRINT_CLAIM = """- thesis: no-deriv spine

## intro | Introduction | ring:core
- claim: the widget governs the result | status:draft
"""


def test_no_deriv_nodes_adds_zero_edges(tmp_path):
    """(d) claim + shell still ground; the widening contributes nothing when no
    irf/thm/ds source exists (every def-grounding edge originates from a claim or
    a result shell, never a deriv source)."""
    sp, bp = _write(tmp_path, _SUBSTRATE_NODERIV, _BLUEPRINT_CLAIM)
    g = bc.build(sp, bp)
    nodes = {n["id"]: n for n in g["nodes"]}

    # pre-existing behavior intact
    assert _draws(g, "res:shell", "def:widget"), "result shell grounding regressed"
    claim_edges = [e for e in g["edges"]
                   if e["rel"] == "draws" and e["dst"] == "def:widget"
                   and nodes.get(e["src"], {}).get("kind") == "claim"]
    assert claim_edges, "claim grounding regressed"

    # the widening added nothing: no def-grounding edge originates from a deriv
    # source (by id-prefix OR by logical kind).
    for e in g["edges"]:
        if e["rel"] == "draws" and e["dst"] == "def:widget":
            src = nodes.get(e["src"], {})
            assert not bc._is_deriv_source(src), f"widening added edge from {e['src']}"


def test_prefix_wins_and_kind_fallback():
    """Verified source-kind rule: id prefix is authoritative (prefix wins); the
    logical kind is the fallback."""
    assert bc._is_deriv_source({"id": "irf:x", "kind": "node"})          # prefix wins over kind
    assert bc._is_deriv_source({"id": "thm:x", "kind": "claim"})
    assert bc._is_deriv_source({"id": "ds:x", "kind": "whatever"})
    assert bc._is_deriv_source({"id": "step_3", "kind": "derivation-step"})  # kind fallback
    assert bc._is_deriv_source({"id": "y", "kind": "theorem"})
    assert not bc._is_deriv_source({"id": "claim:z", "kind": "claim"})
    assert not bc._is_deriv_source({"id": "res:w", "kind": "node"})


# ---------------------------------------------------------------------------
# F29, second half — the fuzzy/stemmed DRAFTED layer (author-ruled HYBRID:
# exact auto, fuzzy DRAFTED). "carries" stems to "carry" but does NOT contain
# it as a substring, so it exercises the stemmed-only path; "SSGS"/"SSG" are
# the acronym-guard pair (FALQON-class vocabulary).
# ---------------------------------------------------------------------------

_SUBSTRATE_FUZZY = """# Substrate: F29 fuzzy fixture

## def:carry | carry: to transport a bound across a step | kind:def
summary: defines this term

## def:orphanterm | orphanterm: a term nobody names | kind:def
summary: defines a term no node mentions

## def:ssgs | SSGS: the acronym family | kind:def
summary: defines the acronym term

## irf:exact | IRF with an exact mention of carry | kind:intermediate-result
summary: an exact hit

## ds:stemmed | Derivation step | kind:derivation-step
summary: the recurrence carries the bound

## ds:both | Derivation step with carry in the label | kind:derivation-step
summary: it carries the same thing

## irf:up | this label holds carry | kind:node
summary: it carries forward

## ds:acronym | Derivation step | kind:derivation-step
summary: one SSG instance appears here
"""


@pytest.fixture()
def fuzzy_graph(tmp_path):
    sp, bp = _write(tmp_path, _SUBSTRATE_FUZZY, _BLUEPRINT_MIN)
    return bc.build(sp, bp)


def test_exact_hit_stays_conceptric(fuzzy_graph):
    """(a) an exact substring hit emits the auto edge, source unchanged."""
    es = _draws(fuzzy_graph, "irf:exact", "def:carry")
    assert len(es) == 1
    assert es[0]["source"] == "conceptric"
    assert "matched_term" not in es[0]


def test_stemmed_only_hit_is_drafted(fuzzy_graph):
    """(b) 'carries' (no exact substring 'carry') grounds via the stemmer and
    is marked conceptric-drafted with the matched term riding."""
    es = _draws(fuzzy_graph, "ds:stemmed", "def:carry")
    assert len(es) == 1
    assert es[0]["source"] == "conceptric-drafted"
    assert es[0]["matched_term"] == "carry"


def test_no_hit_stays_orphan(fuzzy_graph):
    """(c) a def no node names — exactly or stemmed — stays a def-orphan."""
    assert not any(e["dst"] == "def:orphanterm" and e["rel"] == "draws"
                   for e in fuzzy_graph["edges"])
    assert "def:orphanterm" in fuzzy_graph["health"]["connectivity"]["def_orphans"]


def test_exact_over_fuzzy_dedup(fuzzy_graph):
    """(d) exact always wins dedup. Same-pass: a node whose text carries both
    the exact term and a stemmable variant emits ONE edge, source=conceptric.
    Cross-pass: irf:up (kind node -> shell pass drafts from its summary
    'carries'; deriv pass then hits 'carry' exactly in the label) ends
    upgraded to conceptric — the exact edge suppresses the drafted duplicate."""
    es = _draws(fuzzy_graph, "ds:both", "def:carry")
    assert len(es) == 1
    assert es[0]["source"] == "conceptric"
    assert "matched_term" not in es[0]

    es = _draws(fuzzy_graph, "irf:up", "def:carry")
    assert len(es) == 1
    assert es[0]["source"] == "conceptric"
    assert "matched_term" not in es[0]


def test_acronym_term_never_fuzzy_matches(fuzzy_graph):
    """(f) a short all-caps term (SSGS) must not fuzzy-match by stemming:
    text 'SSG' would rescue def:ssgs if the acronym guard were absent."""
    assert not _draws(fuzzy_graph, "ds:acronym", "def:ssgs")
    assert "def:ssgs" in fuzzy_graph["health"]["connectivity"]["def_orphans"]


def test_stemmer_deterministic_and_guarded():
    """The ~15-line stemmer: plural/verbal suffixes stripped, acronyms and
    short tokens passed through lowercased-unstemmed."""
    assert bc._stem_token("widgets") == "widget"
    assert bc._stem_token("carries") == "carry"
    assert bc._stem_token("damping") == "damp"
    assert bc._stem_token("damped") == "damp"
    assert bc._stem_token("classes") == "class"
    assert bc._stem_token("class") == "class"    # 'ss' ending never stripped
    assert bc._stem_token("studies") == "study"  # ies -> y (the non-prefix stem)
    # acronym guard: len<=3 OR no lowercase letter -> never stemmed
    assert bc._stem_token("SSG") == "ssg"
    assert bc._stem_token("AE") == "ae"
    assert bc._stem_token("SSGS") == "ssgs"      # all-caps, len>3: still guarded
    assert bc._stem_token("FALQON") == "falqon"
    assert not bc._stemmable("SSG")
    assert not bc._stemmable("AEs".upper())
    assert bc._stemmable("widgets")


# (e) drafted-only rescue: the ONLY grounding of def:carry is the stemmed hit,
# so the def is rescued (not an orphan) but the rescue is reported for review.
_SUBSTRATE_RESCUE = """# Substrate: F29 drafted-rescue fixture

## def:carry | carry: to transport a bound | kind:def
summary: defines this term

## ds:stemmed | Derivation step | kind:derivation-step
summary: the recurrence carries the bound
"""


def test_drafted_only_rescue_reported(tmp_path):
    """(e) a def-orphan rescued ONLY by drafted edges is not silently healthy:
    it leaves def_orphans but every rescuing edge rides in drafted_rescues."""
    sp, bp = _write(tmp_path, _SUBSTRATE_RESCUE, _BLUEPRINT_MIN)
    g = bc.build(sp, bp)
    conn = g["health"]["connectivity"]
    assert "def:carry" not in conn["def_orphans"]          # drafted counts as rescue
    assert conn["drafted_rescues"] == [
        {"src": "ds:stemmed", "dst": "def:carry", "matched_term": "carry"}]
    assert conn["drafted_edge_count"] == 1


def test_exact_rescue_not_in_drafted_rescues(fuzzy_graph):
    """A def with at least one exact grounding never appears in
    drafted_rescues, however many drafted edges also reach it."""
    conn = fuzzy_graph["health"]["connectivity"]
    assert all(r["dst"] != "def:carry" for r in conn["drafted_rescues"])
    assert "def:carry" not in conn["def_orphans"]
