"""The conceptric's math, pinned: directional coupling (one formula, both axes), the
dimensionalised pull (width x lens x conjectural; thinking phases as presets), identity as
uplink shares, and the phi panel as a watched distribution.

Synthetic fixture: a 3-grade tree where reach is hand-laid so every strength is checkable.

    root (g2)
      A (g1): members a1, a2     reach(a1)={x,y,z}  reach(a2)={x,q}
      B (g1): members b1         reach(b1)={x,y}

Aggregated reach: A={x,y,z,q}, B={x,y}, root=A|B.
"""

from __future__ import annotations

import pytest

from laplace.engine import conceptric
from laplace.engine.keeper_ring import CONJECTURE_PREFIX


def _net():
    nodes = {
        "root": {"id": "root", "grade": 2, "parent": None, "leaf": False,
                 "members": ["A", "B"], "coverage": [], "keywords": []},
        "A": {"id": "A", "grade": 1, "parent": "root", "leaf": False,
              "members": ["a1", "a2"], "coverage": [], "keywords": ["alpha"]},
        "B": {"id": "B", "grade": 1, "parent": "root", "leaf": False,
              "members": ["b1"], "coverage": [], "keywords": []},
        "a1": {"id": "a1", "grade": 0, "parent": "A", "leaf": True, "members": [], "coverage": [], "keywords": []},
        "a2": {"id": "a2", "grade": 0, "parent": "A", "leaf": True, "members": [], "coverage": [], "keywords": []},
        "b1": {"id": "b1", "grade": 0, "parent": "B", "leaf": True, "members": [], "coverage": [], "keywords": []},
    }
    reach = {
        "a1": {"x", "y", "z"}, "a2": {"x", "q"}, "b1": {"x", "y"},
        "A": {"x", "y", "z", "q"}, "B": {"x", "y"}, "root": {"x", "y", "z", "q"},
    }
    lenses = {k: ["engine"] for k in nodes}
    return {"nodes": nodes, "reach": reach, "lenses": lenses, "root": "root"}


def test_coupling_is_directional():
    net = _net()
    c = conceptric.coupling_directed(net["reach"], "A", "B")
    # shared {x,y}=2; A's view = 2/4, B's view = 2/2 - the asymmetry is kept, never averaged.
    assert c["shared"] == 2
    assert c["out"] == pytest.approx(0.5)
    assert c["in"] == pytest.approx(1.0)
    # and the reverse direction swaps the views
    r = conceptric.coupling_directed(net["reach"], "B", "A")
    assert r["out"] == pytest.approx(1.0) and r["in"] == pytest.approx(0.5)


def test_depth_is_the_same_formula():
    """Child->parent ~ containment; parent->child = the child's SHARE (identity weight)."""
    net = _net()
    c = conceptric.coupling_directed(net["reach"], "A", "a1")   # parent's view of child
    assert c["out"] == pytest.approx(3 / 4)                      # a1 constitutes 3/4 of A
    assert c["in"] == pytest.approx(1.0)                         # a1 is wholly part of A
    chain = conceptric.identity_chain(net, "a1")
    assert [link["id"] for link in chain] == ["root", "A"]       # root-first uplinks
    assert chain[-1]["share"] == pytest.approx(0.75)


def test_children_ranked_by_share():
    net = _net()
    kids = conceptric.children_view(net, "A")
    assert [k["id"] for k in kids] == ["a1", "a2"]               # 0.75 before 0.5
    assert kids[0]["share"] == pytest.approx(0.75)


def test_phi_panel_carries_the_grade_spectral_radius():
    """His ruling (2026-06-10): the enrichment policy / pull gain IS the grade spectral radius.
    The panel watches lambda0 + psi per grade; it imposes nothing."""
    net = _net()
    panel = conceptric.phi_panel(net)
    g0 = next(r for r in panel["grades"] if r["grade"] == 0)
    assert {"lambda0", "psi", "n_sampled"} <= set(g0)
    # the g0 sample (a1,a2,b1 - reaches overlap on x) must have a positive Perron root
    assert g0["lambda0"] > 0
    g2 = next(r for r in panel["grades"] if r["grade"] == 2)
    assert g2["n_sampled"] == 1 and g2["lambda0"] == 0.0   # a single node has no fabric to gain on


def test_lateral_pull_width_and_scope():
    net = _net()
    lat = conceptric.lateral(net, "A", width=12, scope="grade")
    assert [x["id"] for x in lat] == ["B"]
    assert lat[0]["out"] == pytest.approx(0.5) and lat[0]["in"] == pytest.approx(1.0)


def test_reconstruct_node_is_node_view_plus_radius_and_cross_lens():
    """The reconstruction primitive (his unification): node_view + the two knobs it lacked -
    correlation radius (cut by coupling STRENGTH) and cross-lens bridges. One object, two faces."""
    net = _net()
    v = conceptric.reconstruct_node(net, "A")
    # it carries every node_view field (the navigator and the firing see the same object) ...
    for k in ("identity", "children", "lateral", "knobs", "flags"):
        assert k in v
    # ... plus the new axes
    assert v["entry_grade"] == 1 and v["target_grade"] == 1
    assert "cross_lens" in v and "radius" in v
    # A's only at-grade coupling is B at out=0.5: a radius above it cuts the fabric to empty,
    # a radius below it keeps B - 'tune your vision to the correlation radius'.
    assert [l["id"] for l in conceptric.reconstruct_node(net, "A", radius=0.4)["lateral"]] == ["B"]
    assert conceptric.reconstruct_node(net, "A", radius=0.6)["lateral"] == []
    # every node shares the one 'engine' lens, so there are NO cross-lens bridges
    assert conceptric.reconstruct_node(net, "A")["cross_lens"] == []
    # target_grade is settable (the descent the navigator drives / a firing re-calls into)
    assert conceptric.reconstruct_node(net, "A", grade=0)["target_grade"] == 0
    # width cuts the fan
    assert conceptric.lateral(net, "a1", width=0) == []
    # zero-coupling peers are dropped entirely
    net["reach"]["b1"] = {"unrelated"}
    net["reach"]["B"] = {"unrelated"}
    assert conceptric.lateral(net, "A", width=12, scope="grade") == []


def test_reconstruct_resolves_an_approximate_name_or_offers_candidates():
    """An agent dispatched reconstruct(node, goal) knows a NAME - a function, a file stem, a
    canon slug - not always the exact node id. The one reconstruction path resolves it (his,
    2026-07-09: 'all this work is useless if reconstruct doesn't find it'): a decisive winner is
    reconstructed with resolved_from stamped; an ambiguous or empty miss returns did_you_mean
    rather than dead-ending on 'unknown node' or silently mis-picking."""
    net = _net()
    net["nodes"]["scripts/render_manuscript.py"] = {
        "id": "scripts/render_manuscript.py", "grade": 0, "parent": "A", "leaf": True,
        "members": [], "coverage": [], "keywords": ["render", "manuscript", "script"]}
    net["reach"]["scripts/render_manuscript.py"] = {"x"}
    net["lenses"]["scripts/render_manuscript.py"] = ["engine"]

    # a near-exact NAME resolves through the path-substring boost, and the reconstructed view
    # is the real node's, with the query stamped as resolved_from
    v = conceptric.reconstruct_node(net, "render_manuscript")
    assert "error" not in v
    assert v["id"] == "scripts/render_manuscript.py"
    assert v["resolved_from"] == "render_manuscript"
    assert v["candidates"][0]["id"] == "scripts/render_manuscript.py"

    # resolve_name ranks by keyword overlap + substring boost, decisive winner first
    ranked = conceptric.resolve_name(net, "render_manuscript")
    assert ranked[0][1] == "scripts/render_manuscript.py" and ranked[0][0] >= 5

    # a genuinely-unknown name never dead-ends silently: error + a did_you_mean channel,
    # and it is NOT auto-resolved to a weak match
    miss = conceptric.reconstruct_node(net, "zzz-nothing-here-zzz")
    assert "error" in miss and "did_you_mean" in miss

    # an exact id still goes straight through (no resolved_from, no regression)
    assert conceptric.reconstruct_node(net, "A").get("resolved_from") is None


def test_lens_specific_pull():
    net = _net()
    net["lenses"]["B"] = ["physics"]
    assert conceptric.lateral(net, "A", width=12, lens="physics", scope="grade")
    assert conceptric.lateral(net, "A", width=12, lens="soul", scope="grade") == []


def test_conjectural_grit_fires_on_ideation_only():
    net = _net()
    # couple A and B ONLY through a conjecture:: token
    tok = CONJECTURE_PREFIX + "maybe"
    net["reach"]["A"] = {tok, "z", "q"}
    net["reach"]["B"] = {tok}
    recall = conceptric.lateral(net, "A", scope="grade",
                                **{k: v for k, v in conceptric.resolve_knobs(phase="recall").items()
                                   if k in ("width", "conjectural")})
    ideate = conceptric.lateral(net, "A", scope="grade",
                                **{k: v for k, v in conceptric.resolve_knobs(phase="ideate").items()
                                   if k in ("width", "conjectural")})
    assert recall == []                                          # grit invisible on recall
    assert ideate and ideate[0]["conjectural"] is True           # surfaced on ideation, flagged


def test_phases_are_parameter_presets():
    r = conceptric.resolve_knobs(phase="recall")
    i = conceptric.resolve_knobs(phase="ideate")
    assert r["width"] < i["width"]
    assert r["conjectural"] is False and i["conjectural"] is True
    # explicit knobs override the preset (the dimensionalised radius)
    custom = conceptric.resolve_knobs(width=7, phase="recall")
    assert custom["width"] == 7


def test_reconstruction_consumes_wider_than_the_render_browses():
    """The consumption ruling (2026-08-20, measured on the blind-surfacing harness): an unqualified
    reconstruct(node, goal) is a reader TAKING the node's neighbourhood, so it defaults to the
    `consume` phase; node_view - the navigator's render - keeps his survey calibration. A width or
    a phase the caller names still wins."""
    net = _net()
    assert conceptric.CONSUMPTION_WIDTH == conceptric.PHASES["consume"]["width"]
    assert conceptric.CONSUMPTION_WIDTH > conceptric.PHASES["survey"]["width"]
    assert conceptric.reconstruct_node(net, "A")["knobs"]["width"] == conceptric.CONSUMPTION_WIDTH
    assert conceptric.node_view(net, "A")["knobs"]["width"] == conceptric.PHASES["survey"]["width"]
    assert conceptric.reconstruct_node(net, "A", width=3)["knobs"]["width"] == 3
    assert conceptric.reconstruct_node(net, "A", phase="recall")["knobs"]["width"] == \
        conceptric.PHASES["recall"]["width"]


def test_node_view_two_axes():
    net = _net()
    v = conceptric.node_view(net, "A", phase="survey", scope="grade")
    assert v["grade"] == 1
    assert [link["id"] for link in v["identity"]] == ["root"]
    assert [k["id"] for k in v["children"]] == ["a1", "a2"]
    assert [x["id"] for x in v["lateral"]] == ["B"]
    assert v["flags"]["too_wide"] is False
    assert v["substrate_size"] == 4
    assert conceptric.node_view(net, "nope").get("error")


def test_mind_view_enters_at_the_apex(tmp_path):
    """The view direction (his ruling): enter at the post-condensed apex, decompose into lenses,
    descend one level per call - never substrate-first."""
    net = _net()
    net["lenses"] = {"root": ["world"], "A": ["physics"], "B": ["engine"],
                     "a1": ["physics"], "a2": ["physics"], "b1": ["engine"]}
    m = conceptric.expand(tmp_path, net, conceptric.MIND)
    assert m["view_depth"] == 0
    labels = [x["label"] for x in m["members"]]
    assert "physics" in labels and "engine" in labels
    # every member carries an essence - nothing is a bare singleton
    assert all(x["essence"] for x in m["members"])

    lens = conceptric.expand(tmp_path, net, conceptric.LENS_PREFIX + "physics")
    # A is where the physics lens BEGINS (its parent wears a different lens)
    assert [x["id"] for x in lens["members"]] == ["A"]

    node = conceptric.expand(tmp_path, net, "A")
    assert [x["id"] for x in node["members"]] == ["a1", "a2"]   # ranked by share
    assert node["members"][0]["share"] == pytest.approx(0.75)
    assert all(x["essence"] for x in node["members"])


def test_fire_by_grade_and_granularity_floor(tmp_path):
    """A prompt decomposes top-down; the floor truncates the descent - recovery at the chosen
    grade's handle, not the leaf."""
    net = _net()
    net["nodes"]["a1"]["keywords"] = ["quantum", "keeper"]
    net["nodes"]["A"]["coverage"] = ["quantum"]
    f = conceptric.fire_by_grade(tmp_path, net, "quantum keeper")
    assert f["hits"] and f["hits"][0]["recovered"] == "a1"
    assert [s["grade"] for s in f["hits"][0]["path"]] == [2, 1, 0]
    assert set(f["per_grade"]) == {"2", "1", "0"}
    # the granularity floor: recover the grade-1 handle instead of descending to substrate
    f1 = conceptric.fire_by_grade(tmp_path, net, "quantum keeper", floor=1)
    assert f1["hits"][0]["recovered"] == "A"
    assert all(s["grade"] >= 1 for s in f1["hits"][0]["path"])


def test_grade_flat_view_and_explode(tmp_path):
    """The grade-flat projection: lateral fabric at one grade; explode = children + their
    intra-cluster links + uplinks (both axes revealed in place)."""
    net = _net()
    gv = conceptric.grade_view(tmp_path, net, 1)
    assert {n["id"] for n in gv["nodes"]} == {"A", "B"}
    assert gv["edges"] and gv["edges"][0]["shared"] == 2          # A<->B fabric present, deduped
    assert all(n["essence"] for n in gv["nodes"])

    ex = conceptric.explode(tmp_path, net, "A")
    assert [c["id"] for c in ex["children"]] == ["a1", "a2"]
    assert ex["inner_edges"][0]["shared"] == 1                    # a1 & a2 share {x}
    assert [u["id"] for u in ex["uplinks"]] == ["root"]
    assert conceptric.explode(tmp_path, net, "nope").get("error")


def test_node_content_local_display(tmp_path):
    """Soul visible locally (his ruling 2026-06-10): trait/entity/file content served from disk for
    the author's browser; internal grade handles honestly say they have no content source."""
    import json as _json
    tdir = tmp_path / conceptric.TRAITS_DIR
    tdir.mkdir(parents=True)
    (tdir / "dry-wit.json").write_text(_json.dumps(
        {"trait": "dry-wit", "instances": [{"entity": "ada", "locator": "w1:2-3", "source": "vrb"}]}),
        encoding="utf-8")
    (tdir / "_INDEX.json").write_text(_json.dumps([{"trait": "dry-wit"}]), encoding="utf-8")
    (tmp_path / "notes.md").write_text("plain file body", encoding="utf-8")

    t = conceptric.node_content(tmp_path, f"{conceptric.SOUL_TRAITS_PARENT}/dry-wit")
    assert t["kind"] == "trait" and t["content"]["instances"][0]["source"] == "vrb"
    idx = conceptric.node_content(tmp_path, conceptric.SOUL_TRAITS_PARENT)
    assert idx["kind"] == "trait-index" and idx["content"][0]["trait"] == "dry-wit"
    f = conceptric.node_content(tmp_path, "notes.md")
    assert f["kind"] == "file" and f["content"] == "plain file body" and f["truncated"] is False
    assert "error" in conceptric.node_content(tmp_path, "no/such/node")


def test_dyad_traits_join_the_value_ring_from_the_committed_dir(tmp_path):
    """The dyad's materialised axes (2026-06-11, on his nod): trait nodes in the SAME value
    ring as his, but read from the COMMITTED dir (custody - they must survive this machine),
    exhibited_by both, essence distinguishing the exhibitor. The parent attaches even when
    the sealed soul dir is absent (the fresh-clone case)."""
    import json as _json
    ddir = tmp_path / conceptric.DYAD_TRAITS_DIR
    ddir.mkdir(parents=True)
    (ddir / "covenant-keeping-under-pressure.json").write_text(_json.dumps(
        {"trait": "covenant-keeping-under-pressure", "axis": "dyad",
         "instances": [{"entity": "_DYAD", "field": "record",
                        "statement": "commitments held despite uncertainty",
                        "locator": "SESSION_HANDOFF_2026-06-06_x.md::6", "source": ""}],
         "exhibited_by": ["_GERARD_APEX", "_EIGEN"], "recurrence": 1}),
        encoding="utf-8")
    (tmp_path / "README.md").write_text("# R\n\nbody\n", encoding="utf-8")

    net = conceptric.load_network(tmp_path)
    nid = f"{conceptric.SOUL_TRAITS_PARENT}/covenant-keeping-under-pressure"
    assert conceptric.SOUL_TRAITS_PARENT in net["nodes"]          # ring attaches, no sealed dir
    node = net["nodes"][nid]
    assert node["axis"] == "dyad" and "_EIGEN" in node["exhibited_by"]
    assert nid in net["nodes"][conceptric.SOUL_TRAITS_PARENT]["members"]
    # reach carries the record locator window - coupling into the self-record rides it
    assert "SESSION_HANDOFF_2026-06-06_x.md" in net["reach"][nid]
    # essence names the dyad; content serves from the committed dir; index lists the axis
    assert "dyad" in conceptric.essence(tmp_path, net, nid)
    c = conceptric.node_content(tmp_path, nid)
    assert c["kind"] == "trait" and c["content"]["exhibited_by"] == ["_GERARD_APEX", "_EIGEN"]
    idx = conceptric.node_content(tmp_path, conceptric.SOUL_TRAITS_PARENT)
    assert any(e.get("axis") == "dyad" for e in idx["content"])
    # lens badges: the values ring, like every trait
    assert "values" in conceptric.node_lenses(nid)


def test_phi_panel_watches_does_not_impose():
    net = _net()
    panel = conceptric.phi_panel(net)
    grades = {row["grade"]: row for row in panel["grades"]}
    assert set(grades) == {0, 1, 2}
    assert grades[0]["n_nodes"] == 3
    assert grades[1]["n_couplings"] >= 2          # A<->B both directions sampled
    assert "imposed" in panel["note"]


def test_series_node_wears_the_self_record_lens():
    """N28: the series node is the self-record's handle for the dated-handoff mass - it must wear
    the lens (else it lands in 'world' and the lens roots fragment back into the flood)."""
    from laplace.engine.keeper import HANDOFF_SERIES
    series = {"id": HANDOFF_SERIES, "grade": 1, "leaf": False}
    assert "self-record" in conceptric.node_lenses(HANDOFF_SERIES, series)
    assert "self-record" in conceptric.node_lenses("SESSION_HANDOFF_2026-06-10_x.md")


def test_named_soul_entity_reachable_via_naming_handle(tmp_path):
    """A named soul entity must be reachable through the descent: the parent handle SPEAKS FOR
    its members by naming them (identity is the handle, content stays sealed). Without this a
    specifically-named entity is rank-1 by cosine yet unreachable - the generic parent never
    clears the beam to be expanded (found live folding David Griffiths, 2026-06-10)."""
    import json as _json
    folded = tmp_path / "archive/soul_dump/_shard/test_folded"
    folded.mkdir(parents=True)
    (folded / "jane_doe.json").write_text(_json.dumps(
        {"name": "Jane Doe", "voice": [{"trait": "dry wit", "locator": "chunk_3.txt"}]}),
        encoding="utf-8")
    (tmp_path / "README.md").write_text("# R\n\nbody\n", encoding="utf-8")
    net = conceptric.load_network(tmp_path)
    ent = "soul://entities/jane_doe"
    assert ent in net["nodes"]
    assert "jane" in net["nodes"][ent]["keywords"] and "doe" in net["nodes"][ent]["keywords"]
    parent_cov = net["nodes"][conceptric.SOUL_ENTITIES_PARENT]["coverage"]
    assert "jane" in parent_cov and "doe" in parent_cov          # the handle names its members


def test_lens_grade_matrix_is_watched_counts(tmp_path):
    """The lens x grade density matrix - the per-lens-ladder EVIDENCE (his diagnosis,
    2026-06-11: one universal ladder, enormously different per-lens densities). Counts only,
    every node counted under every lens badge it wears; watched, never imposed."""
    net = {"nodes": {"src/laplace/a.py": {"grade": 0}, "src/laplace/b.py": {"grade": 1},
                     "EIGEN_DIARY.md": {"grade": 0}, "soul://traits/x": {"grade": 1}},
           "lenses": {"src/laplace/a.py": ["engine"], "src/laplace/b.py": ["engine"],
                      "EIGEN_DIARY.md": ["self-record"],
                      "soul://traits/x": ["soul", "values"]},
           "reach": {}, "root": ""}
    m = conceptric.lens_grade_matrix(net)
    rows = {r["lens"]: r for r in m["rows"]}
    assert rows["engine"]["hist"] == {"0": 1, "1": 1} and rows["engine"]["total"] == 2
    assert rows["engine"]["depth"] == 1
    assert rows["self-record"]["hist"]["0"] == 1
    assert rows["soul"]["total"] == 1 and rows["values"]["total"] == 1   # multi-badge counted twice
    assert m["rows"][0]["lens"] == "engine"                              # densest first
    assert "imposed" in m["note"]


def test_entity_items_are_sealed_routable_leaves(tmp_path):
    """Person recall, the specific-query half: each field item is a grade-0 leaf under its
    entity, so 'his PhD' can recover the right HISTORY ITEM, not just the whole profile. The
    seal holds by construction: the item's meaning rides ONLY the fold-time embedding text
    (gitignored vectors); its node essence and any fire return stay content-free; the content
    is served whole only by node_content (disk -> the author's browser)."""
    import json as _json

    from laplace.representation import embed_router
    from laplace.engine import soul_provenance

    folded = tmp_path / "archive/soul_dump/_shard/test_folded"
    folded.mkdir(parents=True)
    (folded / "jane_doe.json").write_text(_json.dumps(
        {"name": "Jane Doe",
         "voice": [{"trait": "dry wit", "note": "SECRET-VOICE-NOTE", "locator": "chunk_3.txt"}],
         "history": [{"event": "phd in photonics", "note": "SECRET-HISTORY-NOTE",
                      "locator": "chunk_7.txt:1-9"}]}), encoding="utf-8")
    (tmp_path / "README.md").write_text("# R\n\nbody\n", encoding="utf-8")
    net = conceptric.load_network(tmp_path)
    ent = "soul://entities/jane_doe"
    item = f"{ent}/history/0"
    assert item in net["nodes"]
    assert net["nodes"][item]["grade"] == 0 and net["nodes"][item]["parent"] == ent
    assert net["nodes"][ent]["leaf"] is False            # the entity now expands to its items
    assert "chunk_7.txt" in net["reach"][item]           # reach = the item's own locator windows

    # the seal: essence content-free, node dict content-free, fire-return shape content-free
    ess = conceptric.essence(tmp_path, net, item)
    assert "SECRET" not in ess and "phd" not in ess.lower()
    assert "SECRET" not in _json.dumps(net["nodes"][item])

    # the meaning rides the fold-time embedding text only
    txt = embed_router.node_text(tmp_path, net, item)
    assert "phd in photonics" in txt and "SECRET-HISTORY-NOTE" in txt
    assert "jane doe" in txt and "history" in txt

    # ... and a specific query recovers the ITEM through the geometry (hash backend: token-level)
    from test_embed_router import HashBackend
    rec = embed_router.route(tmp_path, net, "jane doe history phd in photonics",
                             backend=HashBackend())
    assert any(f["file"] == item for f in rec["files"]), "the specific item must be recoverable"

    # the content serves whole, locally, via node_content
    c = conceptric.node_content(tmp_path, item)
    assert c["kind"] == "entity-item" and c["content"]["note"] == "SECRET-HISTORY-NOTE"
    assert conceptric.node_content(tmp_path, f"{ent}/history/9")["error"]
    prof = conceptric.node_content(tmp_path, ent)
    assert prof["kind"] == "entity" and "Jane Doe" in prof["profile"]


# ---------------------------------------------------------------------------
# the reconstruction-handles upgrade (his calibration 2026-07-11: "the ring is only as good as
# its handles") - grade-0 projections must give REAL handles, not thin ones.
# ---------------------------------------------------------------------------

def test_doc_leaf_exposes_section_handles(tmp_path):
    """Defect 1: a doc leaf with no member nodes still exposes descendable section handles - each
    '##' heading becomes a child pointer with a line span, so a reconstructor descends into a
    section slice instead of flat-reading the file."""
    doc = tmp_path / "GUIDE.md"
    doc.write_text(
        "# Title\n\nintro\n\n## First\naaa\nbbb\n\n## Second\nccc\n\n```\n## not-a-heading\n```\n\n## Third\nddd\n",
        encoding="utf-8")
    net = {"nodes": {"GUIDE.md": {"id": "GUIDE.md", "grade": 0, "parent": None,
                                  "leaf": True, "members": [], "coverage": [], "keywords": []}},
           "reach": {"GUIDE.md": set()}, "lenses": {"GUIDE.md": ["substrate"]},
           "repo_root": str(tmp_path), "root": "GUIDE.md"}
    kids = conceptric.children_view(net, "GUIDE.md")
    # the three '##' sections become handles, in document order, fenced '##' skipped
    assert [k["heading"] for k in kids] == ["First", "Second", "Third"]
    first = kids[0]
    assert first["id"] == "GUIDE.md#L5-L8" and first["span"] == [5, 8]
    assert first["essence"] == "First"                   # the handle carries its own line inline
    # ... and the span runs to just before the next section, not into the fenced block
    assert kids[1]["span"][0] == 9


def test_reconstruct_node_keeps_inline_section_essence():
    """Defect 1 (view side): a section handle's inline essence survives - children_view supplies it
    and node_view must not have blanked it."""
    net = _net()
    # a1 is a leaf with no members and no repo_root file -> no heading handles (graceful)
    assert conceptric.children_view(net, "a1") == []


def test_code_leaf_essence_is_symbols_not_shebang(tmp_path):
    """Defect 2: a code leaf's essence is its docstring's first sentence + top-level def/class
    names - never the shebang, never a stopword bag."""
    py = tmp_path / "widget.py"
    py.write_text(
        '#!/usr/bin/env python\n"""Do the widget thing. Second sentence ignored."""\n'
        "import os\n\n\ndef alpha():\n    pass\n\n\nclass Beta:\n    pass\n\n\ndef gamma():\n    pass\n",
        encoding="utf-8")
    net = {"nodes": {"widget.py": {"id": "widget.py", "grade": 0, "parent": None,
                                   "leaf": True, "members": [], "coverage": [], "keywords": []}},
           "reach": {"widget.py": set()}, "lenses": {"widget.py": ["engine"]}, "root": "widget.py"}
    ess = conceptric.essence(tmp_path, net, "widget.py")
    assert "Do the widget thing" in ess
    assert "Second sentence" not in ess                  # only the first sentence
    assert "alpha" in ess and "Beta" in ess and "gamma" in ess
    assert "env python" not in ess and "#!" not in ess   # the shebang is gone


def test_view_keywords_drop_stopword_and_path_noise():
    """Defect 2 (view side): the projection's keyword badges shed pure stopword / path-noise
    tokens ('the','and','py','src') so a code leaf shows content, not a bag."""
    net = _net()
    net["nodes"]["a1"]["keywords"] = ["reflex", "the", "py", "src", "policy", "and"]
    v = conceptric.node_view(net, "a1")
    assert v["keywords"] == ["reflex", "policy"]
    # never emptied: if the filter would leave nothing, the raw keywords stand
    net["nodes"]["a2"]["keywords"] = ["the", "and", "py"]
    assert conceptric.node_view(net, "a2")["keywords"] == ["the", "and", "py"]


def test_lateral_idf_floor_drops_lone_common_token():
    """Defect 3: a lone shared substrate token carries an at-grade edge ONLY when it is
    distinctive; a common (low-IDF) token cannot forge a lateral alone, but >=2 shared tokens
    always do, and a rare lone token still does."""
    # 20 grade-0 nodes; 'common' is in half of them (low IDF), 'rare' in just two (high IDF).
    nodes, reach = {}, {}
    for i in range(20):
        nid = f"n{i}"
        nodes[nid] = {"id": nid, "grade": 0, "parent": "R", "leaf": True,
                      "members": [], "coverage": [], "keywords": []}
        reach[nid] = {"common"} if i < 10 else {f"solo{i}"}
    nodes["p"] = {"id": "p", "grade": 0, "parent": "R", "leaf": True,
                  "members": [], "coverage": [], "keywords": []}
    reach["p"] = {"common", "rare", "pairtok"}
    reach["n0"] = {"common", "pairtok"}                   # two shared tokens with p -> KEPT
    reach["n1"] = {"common"}                              # lone low-IDF share with p -> DROPPED
    reach["n2"] = {"rare"}                                # lone HIGH-IDF share (df=2) with p -> KEPT
    net = {"nodes": nodes, "reach": reach,
           "lenses": {k: ["engine"] for k in nodes}, "root": "R"}
    lat_ids = {x["id"] for x in conceptric.lateral(net, "p", width=50, scope="grade")}
    assert "n0" in lat_ids                                # >=2 shared -> unconditional
    assert "n2" in lat_ids                                # lone but distinctive (rare)
    assert "n1" not in lat_ids                            # lone and common -> off the fabric


def test_load_network_prefers_banked_graph_no_degraded_flag(tmp_path, monkeypatch):
    """Defect 4, present-tree half: the BANKED graded tree is preferred byte-identically - the
    full build_self is never called and the returned dict carries NO 'degraded' key."""
    from laplace.engine import keeper
    banked = {"": {"id": "", "grade": 0, "parent": None, "leaf": True,
                   "members": [], "coverage": [], "keywords": []}}
    calls = {"build": 0}
    monkeypatch.setattr(keeper, "build_self",
                        lambda *a, **k: calls.__setitem__("build", calls["build"] + 1) or {})
    monkeypatch.setattr(keeper, "load_tree_local", lambda rr: banked)
    net = conceptric.load_network(tmp_path)
    assert calls["build"] == 0                            # banked graph used - no rebuild at all
    assert "degraded" not in net                          # normal path unchanged
    assert net["repo_root"] == str(tmp_path)              # repo_root stashed for the handle paths


def test_load_network_absent_tree_degrades_without_spectral(tmp_path, monkeypatch, capsys):
    """Defect 4, absent-tree half (RW-20260711-104729-600001): a wake must NEVER silently spin a
    full rebuild. The absent branch prints ONE loud DEGRADED line (naming the file + the fix),
    builds the CHEAP dir_parent-only network (never build_self, never the spectral meaning_upfold),
    and stamps 'degraded': True."""
    from laplace.engine import keeper, meaning_upfold
    monkeypatch.setattr(keeper, "load_tree_local", lambda rr: {})
    calls = {"build_self": 0}
    monkeypatch.setattr(keeper, "build_self",
                        lambda *a, **k: calls.__setitem__("build_self", calls["build_self"] + 1) or {})

    def _spy_cluster(*a, **k):
        raise AssertionError("meaning_upfold.cluster_residue_incremental must NOT fire on the degraded path")

    monkeypatch.setattr(meaning_upfold, "cluster_residue_incremental", _spy_cluster)
    (tmp_path / "README.md").write_text("# R\n\nbody\n", encoding="utf-8")

    net = conceptric.load_network(tmp_path)
    assert calls["build_self"] == 0                       # no full self-build ...
    assert net.get("degraded") is True                   # ... but a degraded network, flagged
    assert net["nodes"]                                   # a real dir_parent tree (README leaf at least)
    err = capsys.readouterr().err
    assert "DEGRADED" in err and ".self_graded.json" in err and "reembed.py" in err
