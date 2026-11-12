"""Unit tests for the Laplace canon graph projector (graph.py)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from laplace.pipeline.canon import Canon
from laplace.pipeline.graph import CanonGraph, Edge, Node, render

pytestmark = pytest.mark.unit


@pytest.fixture
def linked_canon(tmp_path: Path) -> Canon:
    """A small canon with a known link topology.

    Pages and links exercise every edge kind: a structural domain->axioms edge,
    a wiki->wiki ``[[tail]]`` link, a wiki->skill ``canon://`` link, a
    skill->skill link, a wiki->agent ``canon://agents`` link, and one broken
    link.
    """
    root = tmp_path / "canon"
    (root / "wiki" / "aesthetics").mkdir(parents=True)
    (root / "wiki" / "author").mkdir(parents=True)
    (root / "wiki" / "domains" / "synthetics").mkdir(parents=True)
    (root / "agents").mkdir(parents=True)
    for sk in ("epistemic_ledger", "result_foundry", "lonely_skill"):
        (root / "skills" / sk).mkdir(parents=True)

    (root / "index.yaml").write_text(
        textwrap.dedent(
            """\
            version: 1
            wiki:
              aesthetics/voice_and_style: {title: The Laplace Voice, scope: global, tags: [voice]}
              author/the_author: {title: The Author, scope: global, tags: [author]}
            domains:
              synthetics:
                axioms: domains/synthetics/axioms
                tags: [synthetics]
            skills:
              epistemic_ledger: {description: ledger, activity: evaluating, status: core, tags: [latex]}
              result_foundry: {description: foundry, activity: staging, status: experimental, tags: [core]}
              lonely_skill: {description: nobody links here, activity: staging, status: deprecated, tags: []}
            """
        ),
        encoding="utf-8",
    )
    (root / "lifecycle.yaml").write_text("skills: {}\n", encoding="utf-8")
    (root / "agents" / "the_dreamer.yaml").write_text(
        "name: the_dreamer\nrole: Metacognitive R&R node\n", encoding="utf-8"
    )

    # voice -> author via [[tail]]; voice -> epistemic_ledger and -> agent via canon://.
    (root / "wiki" / "aesthetics" / "voice_and_style.md").write_text(
        "# The Laplace Voice\n\nShared with [[the_author]], proofed by "
        "canon://skills/epistemic_ledger, refined by canon://agents/the_dreamer.yaml.\n",
        encoding="utf-8",
    )
    (root / "wiki" / "author" / "the_author.md").write_text(
        "# The Author\n\nThe method counterpart to the voice.\n", encoding="utf-8"
    )
    (root / "wiki" / "domains" / "synthetics" / "axioms.md").write_text(
        "# Axioms\n\nGenerality first.\n", encoding="utf-8"
    )
    # skill -> skill link, plus a broken link to a page that does not exist.
    (root / "skills" / "epistemic_ledger" / "SKILL.md").write_text(
        "---\ndescription: ledger\n---\n\nPairs with [[result_foundry]] and "
        "[[a_page_that_does_not_exist]].\n",
        encoding="utf-8",
    )
    (root / "skills" / "result_foundry" / "SKILL.md").write_text(
        "---\ndescription: foundry\n---\n\nThe innermost ring.\n", encoding="utf-8"
    )
    (root / "skills" / "lonely_skill" / "SKILL.md").write_text(
        "---\ndescription: nobody links here\n---\n\nIsolated.\n", encoding="utf-8"
    )
    return Canon.load(root)


def _edge(g: CanonGraph, src: str, dst: str) -> bool:
    return any(e.src == src and e.dst == dst and e.rel != "dangling" for e in g.edges)


def test_nodes_cover_wiki_skills_domains_agents(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    assert "wiki:aesthetics/voice_and_style" in g.nodes
    assert "skill:epistemic_ledger" in g.nodes
    assert "domain:synthetics" in g.nodes
    assert "agent:the_dreamer" in g.nodes


def test_tail_wikilink_resolves(linked_canon: Canon):
    """A ``[[the_author]]`` link resolves to the full ref by its path tail - the
    exact case the harness display kept garbling, asserted as a hard bit."""
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    assert _edge(g, "wiki:aesthetics/voice_and_style", "wiki:author/the_author")
    assert "missing:the_author" not in g.nodes


def test_canon_uri_link_resolves_to_skill(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    assert _edge(g, "wiki:aesthetics/voice_and_style", "skill:epistemic_ledger")


def test_canon_uri_skill_ref_with_SKILL_md_suffix_resolves(linked_canon: Canon, tmp_path: Path):
    """A canon://skills/<name>/SKILL.md reference must resolve to skill:<name>, not dangle.

    Both the short form (canon://skills/<name>) and the fully-qualified form
    (canon://skills/<name>/SKILL.md) must produce the same resolved edge.
    """
    # Rewrite the voice page to use the /SKILL.md form.
    voice_md = linked_canon.root / "wiki" / "aesthetics" / "voice_and_style.md"
    voice_md.write_text(
        "# The Laplace Voice\n\nProofed by "
        "canon://skills/epistemic_ledger/SKILL.md and by "
        "canon://skills/result_foundry/SKILL.md.\n",
        encoding="utf-8",
    )
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    assert _edge(g, "wiki:aesthetics/voice_and_style", "skill:epistemic_ledger"), (
        "canon://skills/epistemic_ledger/SKILL.md did not resolve to skill:epistemic_ledger"
    )
    assert _edge(g, "wiki:aesthetics/voice_and_style", "skill:result_foundry"), (
        "canon://skills/result_foundry/SKILL.md did not resolve to skill:result_foundry"
    )
    dangling_targets = {d["to"] for d in g.health()["dangling"]}
    assert "epistemic_ledger/SKILL" not in dangling_targets
    assert "result_foundry/SKILL" not in dangling_targets


def test_canon_uri_link_resolves_to_agent(linked_canon: Canon):
    """canon://agents/the_dreamer.yaml is a real edge, not a dangling target."""
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    assert _edge(g, "wiki:aesthetics/voice_and_style", "agent:the_dreamer")
    assert not any(d["to"] == "agents/the_dreamer.yaml" for d in g.health()["dangling"])


def test_structural_domain_edges(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    assert _edge(g, "domain:synthetics", "wiki:domains/synthetics/axioms")


def test_broken_link_becomes_dangling_with_provenance(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    h = g.health()
    assert "missing:a_page_that_does_not_exist" in g.nodes
    bad = next(d for d in h["dangling"] if d["to"] == "a_page_that_does_not_exist")
    assert "[[a_page_that_does_not_exist]]" in bad["evidence"]


def test_template_placeholder_is_not_dangling(linked_canon: Canon, tmp_path: Path):
    """A prose placeholder like canon://domains/.../projects/<project> is a
    template, not a broken link - it must not pollute the health report."""
    sk = linked_canon.skills["result_foundry"]
    sk.skill_md.write_text(
        "---\ndescription: foundry\n---\n\nWrites to "
        "`canon://domains/.../projects/<project>` on close.\n",
        encoding="utf-8",
    )
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    assert not any("..." in d["to"] or "<" in d["to"] for d in g.health()["dangling"])


def test_orphan_detection(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    h = g.health()
    assert "skill:lonely_skill" in h["orphans"]
    assert "wiki:author/the_author" not in h["orphans"]


def test_dead_wood_not_flagged_unless_linked(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    assert g.health()["dead_wood_linked"] == []


# --- provenance: the "ancestor" baseline and recorded generated_by -----------


@pytest.fixture
def provenance_canon(tmp_path: Path) -> Canon:
    """A canon exercising the three provenance tiers: an un-attributed node
    (ancestor), a forged skill the lifecycle attributes to the dreamer, and a
    node a manifest ``source:`` overrides."""
    root = tmp_path / "canon"
    for sk in ("inherited_skill", "forged_skill", "scouted_skill"):
        (root / "skills" / sk).mkdir(parents=True)
    (root / "wiki" / "aesthetics").mkdir(parents=True)
    (root / "index.yaml").write_text(
        textwrap.dedent(
            """\
            version: 1
            wiki:
              aesthetics/voice_and_style: {title: The Laplace Voice, scope: global, tags: [voice]}
            skills:
              inherited_skill: {description: baseline, activity: staging, status: core}
              forged_skill: {description: forged, activity: staging, status: experimental}
              scouted_skill: {description: scouted, activity: staging, status: experimental, source: literature}
            """
        ),
        encoding="utf-8",
    )
    # The dreamer's forge trail attributes forged_skill; inherited_skill has none.
    (root / "lifecycle.yaml").write_text(
        textwrap.dedent(
            """\
            skills:
              forged_skill:
                status: experimental
                forged: '2026-06-01T00:00:00+00:00'
                generated_by: dreamer
            """
        ),
        encoding="utf-8",
    )
    (root / "wiki" / "aesthetics" / "voice_and_style.md").write_text(
        "# The Laplace Voice\n\nProofed by canon://skills/inherited_skill.\n", encoding="utf-8"
    )
    for sk in ("inherited_skill", "forged_skill", "scouted_skill"):
        (root / "skills" / sk / "SKILL.md").write_text(
            f"---\ndescription: {sk}\n---\n\nLinks to [[voice_and_style]].\n", encoding="utf-8"
        )
    return Canon.load(root)


def test_unattributed_nodes_default_to_ancestor(provenance_canon: Canon):
    g = CanonGraph.from_canon(provenance_canon, with_fitness=False)
    assert g.nodes["skill:inherited_skill"].source == "ancestor"
    assert g.nodes["wiki:aesthetics/voice_and_style"].source == "ancestor"


def test_forged_skill_attributed_to_dreamer_not_ancestor(provenance_canon: Canon):
    """A skill the lifecycle records as forged carries its recorded door, so it
    leaves the inherited baseline."""
    g = CanonGraph.from_canon(provenance_canon, with_fitness=False)
    assert g.nodes["skill:forged_skill"].source == "dreamer"


def test_manifest_source_overrides_default(provenance_canon: Canon):
    g = CanonGraph.from_canon(provenance_canon, with_fitness=False)
    assert g.nodes["skill:scouted_skill"].source == "literature"


def test_ancestor_is_not_on_the_unsourced_frontier(provenance_canon: Canon):
    """Ancestor is a real source, so the inherited canon never clogs the frontier;
    it surfaces as a separate cohort to audit on conflict."""
    h = CanonGraph.from_canon(provenance_canon, with_fitness=False).health()
    assert h["frontier"]["unsourced"] == []
    assert "skill:inherited_skill" in h["ancestral"]
    assert "skill:forged_skill" not in h["ancestral"]


def test_genuinely_empty_source_is_flagged_unsourced():
    """A node an engine writer produced without stamping (empty source, not
    ancestor) is the real defect the frontier exists to catch."""
    g = CanonGraph()
    g.nodes["skill:stamped"] = Node(id="skill:stamped", kind="skill", label="stamped", group="staging", source="dreamer")
    g.nodes["skill:unstamped"] = Node(id="skill:unstamped", kind="skill", label="unstamped", group="staging", source="")
    g.edges.append(Edge("skill:stamped", "skill:unstamped", "links_to"))
    h = g.health()
    assert "skill:unstamped" in h["frontier"]["unsourced"]
    assert "skill:stamped" not in h["frontier"]["unsourced"]


# --- the cluster hierarchy: a coarse node stands in for its subgraph ----------


@pytest.fixture
def nested_canon(tmp_path: Path) -> Canon:
    """A canon with a coarse wiki node (``corpus/index``) standing in for two
    interior pages, plus a domain with an axioms page. Exercises the
    ``contains`` hierarchy the viewer descends to read the canon scale-local."""
    root = tmp_path / "canon"
    (root / "wiki" / "corpus").mkdir(parents=True)
    (root / "wiki" / "domains" / "synthetics").mkdir(parents=True)
    (root / "index.yaml").write_text(
        textwrap.dedent(
            """\
            version: 1
            wiki:
              corpus/index: {title: Corpus, scope: global, tags: [corpus]}
              corpus/registers: {title: Registers, scope: global, tags: [register]}
              corpus/source_map: {title: Source Map, scope: global, tags: [sources]}
            domains:
              synthetics:
                axioms: domains/synthetics/axioms
                tags: [synthetics]
            skills: {}
            """
        ),
        encoding="utf-8",
    )
    (root / "lifecycle.yaml").write_text("skills: {}\n", encoding="utf-8")
    (root / "wiki" / "corpus" / "index.md").write_text("# Corpus\n\nThe cluster.\n", encoding="utf-8")
    (root / "wiki" / "corpus" / "registers.md").write_text("# Registers\n\nInterior.\n", encoding="utf-8")
    (root / "wiki" / "corpus" / "source_map.md").write_text("# Source Map\n\nInterior.\n", encoding="utf-8")
    (root / "wiki" / "domains" / "synthetics" / "axioms.md").write_text("# Axioms\n\nThe axioms.\n", encoding="utf-8")
    return Canon.load(root)


def test_canon_carries_parent_hierarchy_into_nodes(nested_canon: Canon):
    """An interior wiki node carries its coarse parent; the coarse node is
    flagged. This is the scale-local drill data the viewer reads."""
    g = CanonGraph.from_canon(nested_canon, with_fitness=False)
    reg = g.nodes["wiki:corpus/registers"]
    assert reg.meta["parent"] == "wiki:corpus/index"
    idx = g.nodes["wiki:corpus/index"]
    assert idx.meta["parent"] is None and idx.meta["coarse"] is True


def test_canon_emits_contains_edges_for_descent(nested_canon: Canon):
    """A coarse wiki node ``contains`` its interior, and a domain ``contains``
    its axioms - the relation every viewer descends, one model, every source."""
    g = CanonGraph.from_canon(nested_canon, with_fitness=False)
    contains = {(e.src, e.dst) for e in g.edges if e.rel == "contains"}
    assert ("wiki:corpus/index", "wiki:corpus/registers") in contains
    assert ("wiki:corpus/index", "wiki:corpus/source_map") in contains
    assert ("domain:synthetics", "wiki:domains/synthetics/axioms") in contains


# --- the contradicts guard: typed inconsistency, with teeth ------------------


def _contradiction_graph() -> CanonGraph:
    """Two coherent nodes plus a typed ``contradicts`` edge between them - the
    inconsistency the consistency guard exists to catch."""
    g = CanonGraph()
    g.nodes["wiki:a"] = Node(id="wiki:a", kind="wiki", label="A", group="workflow", source="dreamer")
    g.nodes["wiki:b"] = Node(id="wiki:b", kind="wiki", label="B", group="workflow", source="ancestor")
    g.edges.append(Edge("wiki:a", "wiki:b", "contradicts", evidence="A asserts not-B"))
    return g


def test_contradicts_edge_fails_health_and_is_listed():
    h = _contradiction_graph().health()
    assert h["pass"] is False
    assert len(h["contradictions"]) == 1
    c = h["contradictions"][0]
    assert c["from"] == "wiki:a" and c["to"] == "wiki:b"
    assert c["evidence"] == "A asserts not-B"


def test_contradiction_flags_ancestor_implication():
    """The audit trigger: a contradiction reports which inherited nodes it
    implicates, since the ad-hoc baseline is what to scrutinise first."""
    c = _contradiction_graph().health()["contradictions"][0]
    assert c["ancestor_implicated"] == ["wiki:b"]  # b is ancestor, a is dreamer


def test_coherent_graph_has_no_contradictions():
    """No contradicts edge -> empty list, and the guard does not fail on its own
    account (a coherent theory has nothing for it to catch)."""
    g = CanonGraph()
    g.nodes["wiki:a"] = Node(id="wiki:a", kind="wiki", label="A", group="workflow", source="dreamer")
    g.nodes["wiki:b"] = Node(id="wiki:b", kind="wiki", label="B", group="workflow", source="dreamer")
    g.edges.append(Edge("wiki:a", "wiki:b", "links_to"))
    h = g.health()
    assert h["contradictions"] == []


# --- the consistency frontmatter annotation: canon prose declares a conflict --


def _canon_with_consistency(tmp_path: Path, a_frontmatter: str) -> Canon:
    """A two-page canon where page ``a`` carries the given frontmatter (and a
    prose link to ``b`` so ``b`` is never incidentally orphaned), and page ``b``
    is the target of ``a``'s consistency annotation."""
    root = tmp_path / "canon"
    (root / "wiki" / "aesthetics").mkdir(parents=True)
    (root / "index.yaml").write_text(
        textwrap.dedent(
            """\
            version: 1
            wiki:
              aesthetics/a: {title: A, scope: global, tags: [x]}
              aesthetics/b: {title: B, scope: global, tags: [x]}
            domains: {}
            skills: {}
            """
        ),
        encoding="utf-8",
    )
    (root / "lifecycle.yaml").write_text("skills: {}\n", encoding="utf-8")
    (root / "wiki" / "aesthetics" / "a.md").write_text(
        a_frontmatter + "# A\n\nThe first claim. See [[b]].\n", encoding="utf-8"
    )
    (root / "wiki" / "aesthetics" / "b.md").write_text(
        "# B\n\nThe second claim.\n", encoding="utf-8"
    )
    return Canon.load(root)


def test_canon_consistency_frontmatter_emits_contradicts_edge(tmp_path: Path):
    """A wiki node's ``consistency: ... | contradicts | ...`` frontmatter projects
    into a typed edge the health guard surfaces - the canon's own prose can now
    declare an axiom-level conflict, not only the substrate seed. The contradicts
    edge coexists with the prose ``[[b]]`` link (distinct relations)."""
    canon = _canon_with_consistency(
        tmp_path,
        '---\nconsistency:\n  - "aesthetics/b | contradicts | A asserts not-B"\n---\n',
    )
    g = CanonGraph.from_canon(canon, with_fitness=False)
    contra = [e for e in g.edges if e.rel == "contradicts"]
    assert len(contra) == 1
    assert contra[0].src == "wiki:aesthetics/a"
    assert contra[0].dst == "wiki:aesthetics/b"
    assert contra[0].evidence == "A asserts not-B"
    assert contra[0].source == "canon"
    assert _edge(g, "wiki:aesthetics/a", "wiki:aesthetics/b")  # the [[b]] link survives too
    h = g.health()
    assert h["pass"] is False
    assert any(
        c["from"] == "wiki:aesthetics/a" and c["to"] == "wiki:aesthetics/b"
        for c in h["contradictions"]
    )


def test_canon_consistency_supports_by_tail_keeps_health(tmp_path: Path):
    """A ``supports`` annotation given as a single string and a bare tail resolves
    to a typed peer edge, and must not trip the contradiction guard."""
    canon = _canon_with_consistency(
        tmp_path, '---\nconsistency: "b | supports | A builds on B"\n---\n'
    )
    g = CanonGraph.from_canon(canon, with_fitness=False)
    assert any(
        e.rel == "supports" and e.src == "wiki:aesthetics/a" and e.dst == "wiki:aesthetics/b"
        for e in g.edges
    )
    assert g.health()["contradictions"] == []


def test_canon_consistency_dangling_ref_is_visible(tmp_path: Path):
    """A consistency ref to a non-existent node becomes a ``dangling`` edge, not a
    silent drop - a broken annotation is surfaced like a broken link."""
    canon = _canon_with_consistency(
        tmp_path,
        '---\nconsistency:\n  - "aesthetics/ghost | contradicts | conflicts with nothing real"\n---\n',
    )
    g = CanonGraph.from_canon(canon, with_fitness=False)
    dangling = [
        e for e in g.edges if e.rel == "dangling" and e.src == "wiki:aesthetics/a"
    ]
    assert len(dangling) == 1
    h = g.health()
    assert h["pass"] is False
    assert any(d["from"] == "wiki:aesthetics/a" for d in h["dangling"])


def test_focus_subgraph_is_bounded(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    sub = g.focus("wiki:aesthetics/voice_and_style", depth=1)
    assert "wiki:author/the_author" in sub.nodes
    assert "skill:lonely_skill" not in sub.nodes


def test_mermaid_render_is_wellformed(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    m = g.to_mermaid()
    assert m.startswith("graph ")
    assert "classDef" in m
    assert "skill_dead" in m  # the deprecated skill gets the dead-wood class


def test_canvas_render_is_valid_jsoncanvas(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    canvas = g.to_canvas()
    assert isinstance(canvas["nodes"], list) and canvas["nodes"]
    for n in canvas["nodes"]:
        assert {"id", "type", "x", "y", "width", "height"} <= set(n)
    json.loads(json.dumps(canvas))  # round-trips, it is written verbatim


def test_json_render_round_trips(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=False)
    s = json.dumps(g.to_json())
    assert json.loads(s)["health"]["node_count"] >= 6


def test_render_focus_unknown_node_reports_closest(linked_canon: Canon, monkeypatch):
    import laplace.pipeline.graph as gmod

    monkeypatch.setattr(gmod, "get_canon", lambda *a, **k: linked_canon)
    res = render("mermaid", focus="no_such_node")
    assert "error" in res and "closest" in res


def test_fitness_weighting_is_defensive(linked_canon: Canon):
    g = CanonGraph.from_canon(linked_canon, with_fitness=True)
    for n in g.nodes.values():
        assert 0.0 <= n.weight <= 1.0


# --- manuscript projection: the same graph object, a different source --------


@pytest.fixture
def manuscript(tmp_path: Path) -> Path:
    p = tmp_path / "main.tex"
    p.write_text(
        textwrap.dedent(
            r"""
            \section{Introduction}
            We motivate the work and point ahead to \ref{fig:overview}.
            \section{Main Result}
            The core identity is
            \begin{equation}\label{eq:core} E = mc^2. \end{equation}
            \begin{figure}
              \includegraphics{overview.png}
              \caption{An overview of the construction.}
              \label{fig:overview}
            \end{figure}
            \section{Discussion}
            Equation \eqref{eq:core} closes the argument, see also \ref{eq:ghost}.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return p


def test_manuscript_builds_section_figure_equation_nodes(manuscript: Path):
    g = CanonGraph.from_manuscript(manuscript)
    kinds = {n.kind for n in g.nodes.values()}
    assert {"section", "figure", "equation"} <= kinds


def test_figure_env_carries_its_includegraphics_path(manuscript: Path):
    """A figure float records the image it draws (\\includegraphics) in
    ``meta.file`` so a viewer can render the real asset, not just the caption."""
    g = CanonGraph.from_manuscript(manuscript)
    fig = g.nodes["fig:fig_overview"]
    assert fig.meta.get("file") == "overview.png"


def test_manuscript_section_sequence_and_containment(manuscript: Path):
    g = CanonGraph.from_manuscript(manuscript)
    rels = {(e.src.split(":")[0], e.rel, e.dst.split(":")[0]) for e in g.edges}
    assert ("sec", "precedes", "sec") in rels
    assert ("sec", "contains", "eq") in rels
    assert ("sec", "contains", "fig") in rels


def test_manuscript_cross_reference_edges(manuscript: Path):
    g = CanonGraph.from_manuscript(manuscript)
    assert any(e.rel == "references" and e.dst == "eq:eq_core" for e in g.edges)


def test_manuscript_broken_ref_is_dangling(manuscript: Path):
    g = CanonGraph.from_manuscript(manuscript)
    assert any(d["to"] == "eq:ghost" for d in g.health()["dangling"])


def test_manuscript_renders_through_same_projections(manuscript: Path):
    g = CanonGraph.from_manuscript(manuscript)
    assert g.to_mermaid().startswith("graph ")
    assert g.to_canvas()["nodes"]
    json.loads(json.dumps(g.to_json()))


def test_core_outward_ring_classification(manuscript: Path):
    g = CanonGraph.from_manuscript(manuscript)
    groups = {n.label: n.group for n in g.nodes.values() if n.kind == "section"}
    assert groups["Main Result"] == "ring_core"
    assert groups["Introduction"] == "ring_outer"


def test_real_canon_renders_and_reports_health():
    """Smoke test against the live packaged canon - it must build and self-report."""
    g = CanonGraph.from_canon(with_fitness=False)
    h = g.health()
    assert h["node_count"] > 30
    assert g.to_mermaid().startswith("graph ")
    assert isinstance(h["components"], int)


# --- the both-ways audit: provenance-down + draws-up --------------------------


@pytest.fixture
def both_ways_canon(tmp_path: Path) -> Canon:
    """A canon exercising both pointers of the both-ways audit. ``earned`` carries
    an ``earned_by`` occurrence (provenance-down present) and links out (anchored);
    ``baseline`` is plain ancestor with no out-edge (unearned + unanchored);
    ``staleprov`` names an occurrence that does not exist on disk."""
    root = tmp_path / "canon"
    (root / "wiki" / "engine").mkdir(parents=True)
    for sk in ("earned", "baseline", "staleprov"):
        (root / "skills" / sk).mkdir(parents=True)
    (root / "index.yaml").write_text(
        textwrap.dedent(
            """\
            version: 1
            wiki:
              engine/anchor: {title: Anchor, scope: global, tags: [engine]}
            skills:
              earned: {description: e, activity: staging, status: core, tags: []}
              baseline: {description: b, activity: staging, status: core, tags: []}
              staleprov: {description: s, activity: staging, status: core, tags: []}
            """
        ),
        encoding="utf-8",
    )
    (root / "lifecycle.yaml").write_text("skills: {}\n", encoding="utf-8")
    (root / "wiki" / "engine" / "anchor.md").write_text("# Anchor\n\nA target.\n", encoding="utf-8")
    # 'earned' has a real occurrence (the index.yaml itself exists) and an out-link.
    (root / "skills" / "earned" / "SKILL.md").write_text(
        "---\ndescription: e\nearned_by:\n  - index.yaml | the occurrence that earned it\n---\n\n"
        "Rests on [[anchor]].\n",
        encoding="utf-8",
    )
    (root / "skills" / "baseline" / "SKILL.md").write_text(
        "---\ndescription: b\n---\n\nNo provenance, no out-link.\n", encoding="utf-8"
    )
    (root / "skills" / "staleprov" / "SKILL.md").write_text(
        "---\ndescription: s\nearned_by:\n  - GONE_2099.md | points at a deleted artifact\n---\n\n"
        "Rests on [[anchor]].\n",
        encoding="utf-8",
    )
    return Canon.load(root)


def test_earned_by_provides_provenance_down(both_ways_canon: Canon):
    """An ``earned_by`` occurrence counts as provenance-down even when the coarse
    ``source`` door is still the pre-provenance ``ancestor``."""
    g = CanonGraph.from_canon(both_ways_canon, with_fitness=False)
    a = g.audit_both_ways()
    unearned = {r["id"] for r in a["unearned"]}
    assert "skill:earned" not in unearned  # earned_by upgrades it
    assert "skill:baseline" in unearned    # plain ancestor, no occurrence


def test_unanchored_is_the_draws_up_frontier(both_ways_canon: Canon):
    """A node with no out-edge and no parent is unanchored; one that links up is not."""
    g = CanonGraph.from_canon(both_ways_canon, with_fitness=False)
    a = g.audit_both_ways()
    unanchored = {r["id"] for r in a["unanchored"]}
    assert "skill:baseline" in unanchored
    assert "skill:earned" not in unanchored  # it links to the anchor


def test_both_ways_closed_node_is_neither_frontier(both_ways_canon: Canon):
    g = CanonGraph.from_canon(both_ways_canon, with_fitness=False)
    a = g.audit_both_ways()
    assert a["both_ways_count"] >= 1  # at least 'earned' is closed both ways


def test_stale_provenance_flags_missing_occurrence(both_ways_canon: Canon, tmp_path: Path):
    """When checked against a root, an ``earned_by`` naming a non-existent artifact
    is surfaced - the down-pointer's peer of a dangling link."""
    g = CanonGraph.from_canon(both_ways_canon, with_fitness=False)
    a = g.audit_both_ways(occurrence_root=tmp_path / "canon")
    stale = {r["id"] for r in a["stale_provenance"]}
    assert "skill:staleprov" in stale
    assert "skill:earned" not in stale  # index.yaml exists under that root


def test_live_canon_both_ways_audit_runs_and_has_earned_nodes():
    """The packaged canon must run the audit and show the demonstrated provenance
    wiring (the engine-self nodes given an ``earned_by`` occurrence)."""
    g = CanonGraph.from_canon(with_fitness=False)
    a = g.audit_both_ways()
    assert a["node_count"] > 30
    assert a["earned_count"] >= 7  # the grounded engine-self cluster, at minimum
    assert a["both_ways_count"] >= 1


def test_json_summary_triggers_on_large_graph_not_small(tmp_path: Path):
    """summary=True on a small canon graph returns full lists (no trigger);
    on an artificially large graph it returns kind/rel counts and a sample.
    This mirrors the real use case: the canon stays full, a large manuscript
    manuscript gets bounded output.
    """
    from laplace.pipeline.graph import CanonGraph, Node, Edge

    # Build a graph that exceeds the threshold.
    big = CanonGraph()
    for i in range(CanonGraph._SUMMARY_THRESHOLD + 5):
        nid = f"section:sec_{i}"
        big.nodes[nid] = Node(id=nid, kind="section", label=f"Section {i}", group="section")
    for i in range(CanonGraph._SUMMARY_THRESHOLD + 4):
        big.edges.append(
            Edge(f"section:sec_{i}", f"section:sec_{i + 1}", "precedes")
        )

    j = big.to_json(summary=True)
    assert j.get("summary") is True, "large graph must trigger summary mode"
    assert "kind_counts" in j
    assert "rel_counts" in j
    assert "node_sample" in j
    assert len(j["node_sample"]) <= 20
    assert "health" in j
    assert "nodes" not in j, "full node list must be absent in summary mode"
    assert "edges" not in j, "full edge list must be absent in summary mode"

    # The small canon graph must never trigger summary even when requested.
    from laplace.pipeline.canon import Canon
    small_canon = Canon.load()
    sg = CanonGraph.from_canon(small_canon, with_fitness=False)
    assert len(sg.nodes) <= CanonGraph._SUMMARY_THRESHOLD, (
        "packaged canon grew past the summary threshold - adjust _SUMMARY_THRESHOLD"
    )
    js = sg.to_json(summary=True)
    assert "nodes" in js, "small graph must return full lists even when summary=True"
    assert js.get("summary") is not True


# --- the interlock layer: claims, citations, and the figure forms -----------


@pytest.fixture
def rich_manuscript(tmp_path: Path) -> Path:
    """A manuscript exercising every interlock node kind: a claim that leans on
    an equation and a citation, section- and claim-level cites, a figure env, a
    bare TikZ schematic, and a back-reference to the claim."""
    p = tmp_path / "rich.tex"
    p.write_text(
        textwrap.dedent(
            r"""
            \section{Introduction}
            Background, citing \cite{shannon1948,jaynes1957}. See \ref{fig:loop}.
            \section{Main Result}
            \begin{equation}\label{eq:core} F = U - TS. \end{equation}
            \begin{result}[Closure]\label{res:closure}
            The closure identity \eqref{eq:core} holds, following \citet{zwanzig1961}.
            \end{result}
            \begin{figure}
              \includegraphics{loop.pdf}
              \caption{The adaptive loop.}
              \label{fig:loop}
            \end{figure}
            A bare schematic:
            \begin{tikzpicture}\label{fig:bare} \draw (0,0)--(1,1); \end{tikzpicture}
            \section{Discussion}
            We refer back to \ref{res:closure} and cite \cite{shannon1948}.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return p


def test_claim_node_with_optional_name(rich_manuscript: Path):
    g = CanonGraph.from_manuscript(rich_manuscript)
    claims = {n.id: n for n in g.nodes.values() if n.kind == "claim"}
    assert "claim:res_closure" in claims
    assert claims["claim:res_closure"].label == "Closure"
    assert claims["claim:res_closure"].meta["env"] == "result"


def test_claim_contained_and_supported_by_equation(rich_manuscript: Path):
    """A claim belongs to its section and points at the equation it invokes -
    the claim->evidence edge the interlock graph exists to make visible."""
    g = CanonGraph.from_manuscript(rich_manuscript)
    assert _edge(g, "sec:main_result", "claim:res_closure")  # contains
    assert any(
        e.src == "claim:res_closure" and e.dst == "eq:eq_core" and e.rel == "supported_by"
        for e in g.edges
    )


def test_citations_are_nodes_with_section_and_claim_edges(rich_manuscript: Path):
    g = CanonGraph.from_manuscript(rich_manuscript)
    cites = {n.id for n in g.nodes.values() if n.kind == "citation"}
    assert {"cite:shannon1948", "cite:jaynes1957", "cite:zwanzig1961"} <= cites
    # section -> citation (intro cites shannon) and claim -> citation (the \citet
    # inside the result env is attributed to the claim, not just its section).
    assert any(e.src == "sec:introduction" and e.dst == "cite:shannon1948" and e.rel == "cites" for e in g.edges)
    assert any(e.src == "claim:res_closure" and e.dst == "cite:zwanzig1961" and e.rel == "cites" for e in g.edges)


def test_bare_tikz_is_a_figure_but_includegraphics_in_env_is_not_doubled(rich_manuscript: Path):
    g = CanonGraph.from_manuscript(rich_manuscript)
    figs = {n.id: n for n in g.nodes.values() if n.kind == "figure"}
    assert figs["fig:fig_bare"].meta.get("tikz") is True  # bare TikZ became a figure
    assert "fig:fig_loop" in figs  # the figure env
    # the \includegraphics inside that env must not spawn a second figure node
    assert not any(n.endswith("loop_pdf") for n in figs)


def test_backreference_to_claim_resolves(rich_manuscript: Path):
    """A \\ref to a claim's label is a real reference edge, never a dangling one."""
    g = CanonGraph.from_manuscript(rich_manuscript)
    assert _edge(g, "sec:discussion", "claim:res_closure")
    assert not any(d["to"] == "res:closure" for d in g.health()["dangling"])


def test_input_order_beats_sorted_filenames(tmp_path: Path):
    """Pointed at a root file, sections follow \\input order - the case a
    sorted-glob directory merge would get backwards."""
    root = tmp_path / "main.tex"
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "zeta.tex").write_text(r"\section{Zeta Section}" + "\n", encoding="utf-8")
    (tmp_path / "parts" / "alpha.tex").write_text(r"\section{Alpha Section}" + "\n", encoding="utf-8")
    root.write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\input{parts/zeta}\n\\input{parts/alpha}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    g = CanonGraph.from_manuscript(root)
    order = {n.label: n.meta["order"] for n in g.nodes.values() if n.kind == "section"}
    assert order["Zeta Section"] == 0 and order["Alpha Section"] == 1
    assert _edge(g, "sec:zeta_section", "sec:alpha_section")  # precedes


def test_rich_manuscript_renders_through_all_projections(rich_manuscript: Path):
    g = CanonGraph.from_manuscript(rich_manuscript)
    m = g.to_mermaid()
    assert m.startswith("graph ")
    assert "g_claim" in m and "g_citation" in m  # the new groups get classDefs
    json.loads(json.dumps(g.to_json()))
    assert g.to_canvas()["nodes"]


def test_table_float_is_a_figure_node(tmp_path: Path):
    """A \\begin{table} is a labelled float - it becomes a figure node so a
    \\ref{tab:...} resolves instead of dangling."""
    p = tmp_path / "t.tex"
    p.write_text(
        textwrap.dedent(
            r"""
            \section{Results}
            \begin{table}
              \caption{Closure loss by regime.}
              \label{tab:loss}
            \end{table}
            As Table \ref{tab:loss} shows, it converges.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    g = CanonGraph.from_manuscript(p)
    tab = g.nodes.get("fig:tab_loss")
    assert tab is not None and tab.kind == "figure" and tab.meta["float"] == "table"
    assert _edge(g, "sec:results", "fig:tab_loss")  # both contains and references
    assert g.health()["dangling"] == []


# --- semantic-prefix equations: a numbered equation that is ALSO a claim ------


@pytest.fixture
def semantic_manuscript(tmp_path: Path) -> Path:
    """A manuscript that numbers its display equations with SEMANTIC epistemic
    prefixes (def:/thm:/...) rather than a bare eq: - the SSG whitepaper's
    convention, with zero \\newtheorem. Each such numbered equation is both an
    equation node (it carries a body) and a claim node (the prefix names the
    assertion). A control eq: equation keeps the base path honest."""
    p = tmp_path / "sem.tex"
    p.write_text(
        textwrap.dedent(
            r"""
            \section{Definitions}
            The Hamiltonian is
            \begin{equation}\label{def:hamiltonian} H = \sum_i Z_i. \end{equation}
            \section{Result}
            The closure theorem, following \cite{zwanzig1961}, states
            \begin{equation}\label{thm:closure}
              \langle H \rangle = 0 \text{ using } \eqref{def:hamiltonian}. \cite{jaynes1957}
            \end{equation}
            A plain numbered equation keeps the eq: path alive:
            \begin{equation}\label{eq:aux} x = y. \end{equation}
            \section{Discussion}
            We invoke \ref{thm:closure} and \eqref{def:hamiltonian} again.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return p


def test_semantic_prefix_equation_makes_both_equation_and_claim(semantic_manuscript: Path):
    g = CanonGraph.from_manuscript(semantic_manuscript)
    # the numbered def:/thm: equations are equation nodes (they carry LaTeX) ...
    assert g.nodes["eq:def_hamiltonian"].kind == "equation"
    assert g.nodes["eq:thm_closure"].kind == "equation"
    # ... AND claim nodes; the label is stored byte-for-byte, never rewritten.
    assert g.nodes["claim:def_hamiltonian"].kind == "claim"
    assert g.nodes["claim:def_hamiltonian"].label == "def:hamiltonian"
    assert g.nodes["claim:def_hamiltonian"].meta["role"] == "def"
    # the base eq: path is untouched: a bare eq: equation is an equation, not a claim.
    assert g.nodes["eq:eq_aux"].kind == "equation"
    assert "claim:eq_aux" not in g.nodes


def test_semantic_prefix_nodes_carry_reading_order(semantic_manuscript: Path):
    """A2: every eq/claim node carries a source-order position (its \\input-order
    offset) so a later phase can detect 'referenced before introduced'."""
    g = CanonGraph.from_manuscript(semantic_manuscript)
    ro = {n.id: n.meta.get("reading_order") for n in g.nodes.values()
          if n.kind in ("equation", "claim")}
    assert all(v is not None for v in ro.values())
    # monotone in reading order: def before thm before the aux eq.
    assert ro["eq:def_hamiltonian"] < ro["eq:thm_closure"] < ro["eq:eq_aux"]
    # an equation and its twin claim share the environment's position.
    assert ro["eq:def_hamiltonian"] == ro["claim:def_hamiltonian"]


def test_semantic_claim_supported_by_and_cites_edges(semantic_manuscript: Path):
    """The claim->supported_by->equation and claim->cites apparatus fires for a
    semantic-prefixed equation exactly as for a theorem-env claim."""
    g = CanonGraph.from_manuscript(semantic_manuscript)
    # the claim is supported_by its own equation ...
    assert any(e.src == "claim:thm_closure" and e.dst == "eq:thm_closure"
               and e.rel == "supported_by" for e in g.edges)
    # ... and by the equation it \eqrefs.
    assert any(e.src == "claim:thm_closure" and e.dst == "eq:def_hamiltonian"
               and e.rel == "supported_by" for e in g.edges)
    # a \cite inside the equation env is attributed to the claim, not just its section.
    assert any(e.src == "claim:thm_closure" and e.dst == "cite:jaynes1957"
               and e.rel == "cites" for e in g.edges)
    # the section contains both the equation and its twin claim.
    assert _edge(g, "sec:result", "eq:thm_closure")
    assert _edge(g, "sec:result", "claim:thm_closure")


def test_semantic_prefix_ref_resolves_not_dangling(semantic_manuscript: Path):
    """A \\ref/\\eqref to a semantic label resolves to the real equation node
    instead of dangling as 'missing' - the interlock the widened gate restores."""
    g = CanonGraph.from_manuscript(semantic_manuscript)
    assert not any(d["to"] in ("thm:closure", "def:hamiltonian")
                   for d in g.health()["dangling"])
    assert _edge(g, "sec:discussion", "eq:thm_closure")
    assert _edge(g, "sec:discussion", "eq:def_hamiltonian")


_LAW_OF_LAWS = Path(
    r"C:\Users\gerar\VScodeProjects\physics_paper_orchestra"
    r"\law-of-laws\manuscript\tex_v5\main.tex"
)


@pytest.mark.skipif(not _LAW_OF_LAWS.exists(), reason="orchestra manuscript not present on this machine")
def test_real_manuscript_interlock_builds():
    """Smoke test against a live orchestra manuscript - it must build a rich
    interlock graph and honour \\input reading order."""
    g = CanonGraph.from_manuscript(_LAW_OF_LAWS)
    kinds = {n.kind for n in g.nodes.values()}
    assert {"section", "figure", "equation", "citation"} <= kinds
    order = {n.label: n.meta["order"] for n in g.nodes.values() if n.kind == "section"}
    scaling = next(o for lbl, o in order.items() if "scaling" in lbl.lower())
    discussion = next(o for lbl, o in order.items() if lbl.strip().lower() == "discussion")
    assert scaling < discussion  # \input order; a sorted-glob merge would reverse this
    assert g.to_mermaid().startswith("graph ")
    json.loads(json.dumps(g.to_json()))
    assert g.health()["node_count"] > 30
