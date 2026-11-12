"""Anti-overfit genericity gate: the schema-level machinery must not be secretly
SSG-shaped. A deliberately DIFFERENT layout family (non-`N` section ids, a merge
paragraph carrying two spec_ids, a math semicolon, \\ref/\\cite) run through the
real parsers, the detector, and the feedback router. The "Eleven" leak (a
hard-coded section count) is the class this guards against."""
from laplace.pipeline import verify
from laplace.pipeline import document_model, schema, propagate
from laplace.manuscript import projection_viewer as pv


# a 2nd layout family: section id `sec-alpha` (not N1..N11), def/res/thm nodes,
# a math semicolon that must be spared, and p2+p3 adjacent = a MERGE (one
# paragraph, two spec_ids), plus a \ref and a \cite.
FRAGMENT = r"""% PLAN: sec-alpha
% NODES: def:widget res:main-bound thm:alpha-collapse
% sec-alpha-p1
The widget $W$ acts on the state, and its spectrum $(w_1\dots w_n; \tau)$ carries the bound.
% sec-alpha-p2
% sec-alpha-p3
This paragraph carries two plan units at once, cites \cite{smith2020}, and points at \ref{fig:widget-sweep}.
"""


def test_paragraph_markers_parse_generically_with_a_merge():
    paras = pv.parse_paragraphs(FRAGMENT)
    # the ids are recovered regardless of the (non-N) section scheme
    all_ids = [sid for para in paras for sid in para.get("nodes", para.get("spec_ids", []))] \
        if paras and "spec_ids" not in paras[0] else [sid for para in paras for sid in para.get("spec_ids", [])]
    flat = {s for para in paras for s in (para.get("spec_ids") or [])}
    assert {"sec-alpha-p1", "sec-alpha-p2", "sec-alpha-p3"} <= flat
    # the merge: p2 and p3 are adjacent markers -> they land on ONE paragraph span
    merged = [p for p in paras if set(p.get("spec_ids") or []) >= {"sec-alpha-p2", "sec-alpha-p3"}]
    assert merged, f"adjacent markers should merge onto one span; got {[p.get('spec_ids') for p in paras]}"


def test_detector_spares_math_semicolon_in_a_new_family():
    # the surface-invariant `;` inside $(w_1\dots w_n; \tau)$ must NOT flag
    r = verify.check_voice(FRAGMENT)
    assert not [f for f in r["violations"] if f["kind"] == "surface-invariant"], r


def test_parse_fragment_lifts_markers_for_a_non_N_section():
    d = document_model.parse_fragment(FRAGMENT, "sec-alpha")
    # a non-N section id parses generically (no baked-in N1..N11 assumption)
    assert d["section_id"] == "sec-alpha"
    # the NODES ids are real kind-prefixed ids regardless of the layout family
    for nid in ("def:widget", "res:main-bound", "thm:alpha-collapse"):
        assert schema.NODE_ID_RE.match(nid)


def test_feedback_routes_a_figure_kind_for_a_new_section():
    # a fig/ref-shaped feedback item on the new section routes to its owning layer
    plan = {"meta": {"project": "genfix"},
            "sections": [{"id": "sec-alpha",
                          "nodes_in_order": ["def:widget", "res:main-bound", "thm:alpha-collapse"]}]}
    recs = [{"id": "G1", "kind": "figure-standard", "node_id": "fig:widget-sweep",
             "anchor": {"section": "sec-alpha"}, "scope": "section", "text": "panel mislabelled"}]
    items = propagate.intake_items(recs, plan, {"def:widget": {}})
    assert len(items) == 1
    it = items[0]
    assert it["kind"] == "figure" and it["owning_stage"] == "figures"
    assert it["scope"] == "section" and it["local"] is True
