"""Tests for the Laplace Engine: canon, verify, assessment, dreamer."""

from __future__ import annotations

import json
import shutil

import pytest
import yaml

from laplace.engine import assess, dreamer, telemetry
from laplace.pipeline import verify
from laplace.core import versioning as gitio
from laplace.pipeline import canon as canonmod
from laplace.pipeline.canon import Canon

pytestmark = pytest.mark.unit


SEED_TEX = r"""\documentclass{article}
\begin{document}
\section{Introduction}
We analyze the color of the system; this is important --- really.
The paper now turns to the properly bounded result it has earned.
\begin{equation}\label{eq:used} x = 1 \end{equation}
As shown in \ref{eq:used}, the result holds.
\begin{equation}\label{eq:orphan} y = 2 \end{equation}
We also cite \ref{eq:missing} here.
\end{document}
"""


# ---------------------------------------------------------------------------
# canon
# ---------------------------------------------------------------------------


def test_canon_loads_skills_and_wiki():
    c = Canon.load()
    assert len(c.skills) >= 10
    assert len(c.wiki) >= 8
    # activities and statuses are constrained vocabularies
    assert {s.activity for s in c.skills.values()} <= {"generating", "staging", "evaluating"}
    assert {s.status for s in c.skills.values()} <= {"experimental", "core", "deprecated"}


def test_canon_resolve_variants():
    c = Canon.load()
    # canon:// ref, bare wiki ref, and bare skill name all resolve
    assert "Laplace Voice" in c.resolve("canon://aesthetics/voice_and_style")[1]
    assert c.resolve("aesthetics/voice_and_style")[1]
    assert c.resolve("epistemic_ledger")[0].name == "SKILL.md"
    with pytest.raises(KeyError):
        c.resolve("canon://nope/nothing")


def test_get_canon_reloads_on_disk_change(tmp_path, monkeypatch):
    dst = tmp_path / "canon"
    shutil.copytree(canonmod._PACKAGED_CANON, dst)
    monkeypatch.setenv("LAPLACE_CANON", str(dst))
    first = canonmod.get_canon(fresh=True)
    # An unchanged canon returns the cached object - no needless reload.
    assert canonmod.get_canon() is first
    # A skill forged on disk (host-forge style) is visible without fresh=True:
    # the live tools pick up the change within the running process.
    probe = dst / "skills" / "probe_skill"
    probe.mkdir(parents=True)
    (probe / "SKILL.md").write_text(
        "---\nname: probe_skill\ndescription: probe\n---\n# Probe [EXPERIMENTAL]\n",
        encoding="utf-8",
    )
    reloaded = canonmod.get_canon()
    assert reloaded is not first
    assert "probe_skill" in reloaded.skills


def test_orient_infers_domain_and_ranks_skills():
    c = Canon.load()
    b = c.orient("lint the latex voice and check derivations for the phases of hierarchy")
    assert b["domain"] == "synthetics"
    # domain axioms + project are surfaced (handles at grade 0)
    refs = {d["ref"] for d in b["domain_context"]}
    assert any("synthetics/axioms" in r for r in refs)
    # skills are bucketed by activity (generating|staging|evaluating)
    names = {s["name"] for bucket in b["skills"].values() for s in bucket}
    assert {"latex_forge", "epistemic_ledger"} & names


def test_orient_surfaces_generating_skills_for_generation_goals():
    """orient must return a non-empty generating bucket for goals that signal
    creation intent, even when no generating-skill tag directly matches the
    goal tokens.  Non-generating goals must not pick up generating skills.
    """
    c = Canon.load()
    # Goals that clearly signal writing/creation intent.
    for goal in ("draft the introduction", "write a new section", "generate ideas"):
        b = c.orient(goal)
        gen = b["skills"]["generating"]
        assert gen, (
            f"orient returned empty generating bucket for goal {goal!r}; "
            f"expected at least one generating skill"
        )
        assert all(s["activity"] == "generating" for s in gen), (
            "non-generating skill leaked into generating bucket"
        )
    # A purely evaluative goal must NOT artificially inject generating skills.
    b_eval = c.orient("check the equation labels")
    # The evaluating bucket should be populated; generating may be empty.
    assert b_eval["skills"]["evaluating"], "evaluating bucket empty for an evaluative goal"


def test_orient_surfaces_blind_generation_discipline_for_artefact_goals():
    """A generate-artefact orient MUST reliably carry the blind-generation
    discipline (builder != judge), even when domain inference mis-routes.

    The pre-commit check (META_TEST_2026-06-05) found "generate a manuscript
    draft" mis-routes to `talks`, surfaced `generating: [level_tender]`, and did
    NOT surface `orchestrated_generation` - so blindness was *remembered, not
    enforced*. This pins the fix: regardless of the mis-routed domain, the orient
    surfaces (a) `orchestrated_generation` as a skill and (b) a top-level
    `generation_discipline` directive that names the law and points at the skill,
    and it rides ALONGSIDE the generating skill, not in place of it.
    """
    c = Canon.load()
    # The exact goal the pre-commit check flagged, plus other artefact-generation
    # phrasings that mis-route or land in non-synthetics domains.
    for goal in (
        "generate a manuscript draft for the operatorial loss paper",
        "write a new talk deck from scratch",
        "build a conceptric and project an artefact",
    ):
        b = c.orient(goal)
        # (a) the discipline skill surfaces in the bundle regardless of domain.
        names = {s["name"] for bucket in b["skills"].values() for s in bucket}
        assert "orchestrated_generation" in names, (
            f"orchestrated_generation did not surface for {goal!r} "
            f"(domain={b['domain']!r}); blind generation is remembered, not enforced"
        )
        # (b) the top-level directive is stated, not left to be remembered.
        assert "generation_discipline" in b, (
            f"generation_discipline directive missing for {goal!r}"
        )
        gd = b["generation_discipline"]
        assert gd["skill"] == "canon://skills/orchestrated_generation"
        assert "builder" in gd["law"] and "judge" in gd["law"]
        # the discipline rides ALONGSIDE a generating skill, not in place of it -
        # an artefact goal wants both the generator and the protocol.
        assert b["skills"]["generating"], (
            f"generating bucket empty for {goal!r}; the discipline displaced the generator"
        )

    # A purely evaluative goal must NOT pick up the generation discipline.
    b_eval = c.orient("check the equation labels for orphans")
    assert "generation_discipline" not in b_eval, (
        "generation discipline leaked onto a non-generation goal"
    )


def test_route_reaches_every_store_up_and_down():
    """The router must reach the FULL conceptric, not just the canon wiki layer:
    canon + corpus + soul + the engine's self-knowledge, in one routing. The meta
    test found orient reaches only canon; route closes that (the local
    reconstructor + the global self's taste, made retrievable)."""
    c = Canon.load()
    r = c.route("derive the Loss Hamiltonian generator via the Fokker-Planck to Schrodinger mapping")
    assert set(r) >= {"canon", "corpus", "soul", "self_knowledge"}
    # DOWN: the corpus is now reachable by goal - the loss_generator lineage surfaces.
    corpus_keys = {h["key"] for h in r["corpus"]}
    assert {"witten1982supersymmetry", "risken1989fokker"} & corpus_keys, (
        f"loss_generator lineage not retrieved; got {sorted(corpus_keys)}"
    )
    # the engine's own self-knowledge (a flat repo file orient cannot reach) surfaces.
    files = {h["file"] for h in r["self_knowledge"]}
    assert any(f.startswith("SESSION_HANDOFF") or f == "OPEN_STACK.md" or f == "HANDOFF.md"
               for f in files), f"self-knowledge not routed; got {sorted(files)}"


def test_route_surfaces_soul_for_a_taste_goal_without_inlining_content():
    """A taste/judgement goal must reach the soul (the judgement centre's ground
    truth) - returning the fragment to pull, never its content (verbatim, private,
    pulled deliberately)."""
    c = Canon.load()
    r = c.route("make a taste judgement on a sentence: does it read as earned simplicity")
    soul_refs = [h["ref"] for h in r["soul"]]
    assert soul_refs, "the soul was not reachable for a taste judgement"
    assert all(r_.startswith("soul/") for r_ in soul_refs)
    # the router returns refs + scores only; no content key leaks the verbatim soul.
    assert all(set(h) == {"ref", "score"} for h in r["soul"])


def test_route_is_defensive_when_stores_are_absent(tmp_path):
    """A canon with no sibling corpus/soul/handoffs must still route - empty
    slices, never an error (the dashboard/router is a convenience, never a hard
    dependency)."""
    (tmp_path / "canon" / "wiki").mkdir(parents=True)
    (tmp_path / "canon" / "index.yaml").write_text("version: 1\nwiki: {}\nskills: {}\n", encoding="utf-8")
    (tmp_path / "canon" / "lifecycle.yaml").write_text("skills: {}\n", encoding="utf-8")
    c = Canon.load(tmp_path / "canon")
    r = c.route("anything at all")
    assert r["corpus"] == [] and r["soul"] == [] and r["self_knowledge"] == []


def test_check_canon_scoped_verifies_at_grade_not_the_whole_graph():
    """Verify-at-grade (the conjugate of the graded hello): a focus scopes the canon check to a
    node's neighbourhood + siblings, and a focus that touches no canon node SKIPS the check rather
    than re-verifying a canon the session never changed. The whole-canon verify grows with the
    conceptric; this is how the close stays light as the engine self-ingests."""
    from laplace.pipeline import verify as V
    from laplace.pipeline.graph import CanonGraph
    c = Canon.load()

    # default: whole canon, unscoped (unchanged behaviour).
    full = V.check_canon(c)
    assert "scope" not in full and full["pass"] is True

    # a focus that resolves to no canon node (a session that touched only trace files) -> skip.
    skipped = V.check_canon(c, focus="HANDOFF.md")
    assert skipped["pass"] is True and skipped["scope"]["resolved"] == []
    assert "skipped" in skipped["note"]

    # a real node -> scoped to its neighbourhood; a depth-1 sub is connected, so no false orphans.
    g = CanonGraph.from_canon(c)
    adj = g.neighbours(undirected=True)
    real = next(nid for nid, n in g.nodes.items() if n.kind != "missing" and adj.get(nid))
    scoped = V.check_canon(c, focus=real)
    assert scoped["scope"]["resolved"] == [real]
    assert scoped["orphans"] == [] and scoped["pass"] is True
    # the scoped subgraph is a neighbourhood, never larger than the whole canon.
    assert scoped["ancestral_count"] <= full["ancestral_count"]


def test_coactivation_extracts_fired_nodes_only():
    """The co-activation record is the nodes loaded WITH content for a goal - the
    matched foundation nodes plus the domain nodes - and not the content-less
    global refs offered on every orient, which are constant and carry no signal.
    The producer half of EIGEN_ARCHITECTURE.md Component 1."""
    bundle = {
        "foundation": [
            {"ref": "canon://aesthetics/voice_and_style", "title": "Voice", "content": "..."},
            {"ref": "canon://operations/git_mechanics", "title": "Git"},  # offered, no content
        ],
        "domain_context": [
            {"ref": "canon://domains/synthetics/axioms", "title": "Axioms", "content": "..."},
        ],
    }
    acts = telemetry.coactivation(bundle)
    assert acts == [
        "canon://aesthetics/voice_and_style",
        "canon://domains/synthetics/axioms",
    ]
    assert "canon://operations/git_mechanics" not in acts  # no co-activation signal
    assert telemetry.coactivation({}) == []  # robust to an empty bundle


def test_coactivation_on_real_orient_bundle_matches_loaded_nodes():
    """On a real (grade-0) orient, every co-activation ref is a node the bundle
    marked relevant, and the set is non-empty for a goal that matches. The signal
    is grade-independent - a node fires because it matched the goal, not because
    its body was inlined."""
    b = Canon.load().orient(
        "lint the latex voice and check derivations for the phases of hierarchy"
    )
    acts = telemetry.coactivation(b)
    assert acts, "a matching goal should fire at least one node"
    loaded = {it["ref"] for it in b["foundation"] if it.get("relevant")}
    loaded |= {it["ref"] for it in b["domain_context"]}
    assert set(acts) == loaded
    offered = {it["ref"] for it in b["foundation"] if not it.get("relevant")}
    assert not (set(acts) & offered)


# ---------------------------------------------------------------------------
# verify (mirrors legacy ledgers)
# ---------------------------------------------------------------------------


def test_verify_flags_seeded_errors(tmp_path):
    tex = tmp_path / "seed.tex"
    tex.write_text(SEED_TEX, encoding="utf-8")
    rep = verify.verify(str(tex))
    assert rep["passed"] is False
    # the 2026-07-09 detector: structural failure classes + surface invariants;
    # the retired register-ban lint (americanism/slop word-lists) must NOT fire
    kinds = {f["kind"] for f in rep["checks"]["voice"]["violations"]}
    assert {"surface-invariant", "narrator-visible", "self-adjudication"} <= kinds
    assert "americanism" not in kinds and "ai_slop" not in kinds
    assert "eq:orphan" in rep["checks"]["epistemic"]["orphans"]
    assert any(b["ref"] == "eq:missing" for b in rep["checks"]["crossref"]["broken_refs"])


def test_epistemic_counts_eqref_not_just_ref(tmp_path):
    # A label referenced only via \eqref must not be reported as an orphan.
    tex = tmp_path / "eqref.tex"
    tex.write_text(
        r"\begin{equation}\label{eq:a} x=1 \end{equation} see \eqref{eq:a}." + "\n",
        encoding="utf-8",
    )
    rep = verify.verify(str(tex), checks=["epistemic"])
    assert rep["checks"]["epistemic"]["orphans"] == []


def test_voice_flags_unicode_emdash(tmp_path):
    tex = tmp_path / "uni.tex"
    tex.write_text("This clause — an aside — lingers.\n", encoding="utf-8")
    rep = verify.verify(str(tex), checks=["voice"])
    assert any(f["kind"] == "surface-invariant"
               for f in rep["checks"]["voice"]["violations"])


def test_voice_ignores_markdown_syntax_noise(tmp_path):
    md = tmp_path / "syntax.md"
    md.write_text(
        "---\nname: probe\n---\n"
        "| A | B |\n| --- | --- |\n"
        "```text\ncmd --source-handle TEST --cache-root tmp\n```\n"
        "Clean prose stays here.\n",
        encoding="utf-8",
    )
    rep = verify.verify(str(md), checks=["voice"])
    assert rep["checks"]["voice"]["violations"] == []


def test_voice_ignores_markdown_horizontal_rule(tmp_path):
    md = tmp_path / "rule.md"
    md.write_text(
        "# Heading\n\nClean prose above.\n\n---\n\nClean prose below.\n",
        encoding="utf-8",
    )
    rep = verify.verify(str(md), checks=["voice"])
    assert rep["checks"]["voice"]["violations"] == []


def test_verify_clean_file_passes(tmp_path):
    tex = tmp_path / "clean.tex"
    tex.write_text(
        r"\section{Intro}\begin{equation}\label{eq:a} x=1 \end{equation}"
        r" see \ref{eq:a}." + "\n",
        encoding="utf-8",
    )
    rep = verify.verify(str(tex))
    assert rep["passed"] is True
    assert rep["issue_count"] == 0


def test_connectivity_and_projection_labels_manual_without_project(tmp_path):
    """The build-completion gates key off the ``project`` argument (the corpus name),
    exactly as the citations gate does. Without a project both return manual - the
    target might not be a conceptric-backed artefact - so the default verify path
    never red-flags a plain manuscript that opted out."""
    rep = verify.verify(str(tmp_path), checks=["connectivity", "projection_labels"])
    assert rep["checks"]["connectivity"]["pass"] is None
    assert rep["checks"]["connectivity"]["manual"] is True
    assert rep["checks"]["projection_labels"]["pass"] is None
    assert rep["checks"]["projection_labels"]["manual"] is True


def test_connectivity_check_holds_on_real_corpus():
    """Against a registered corpus, the connectivity gate walks the edge_index from
    every spine beat and reports every node no beat can reach. subset-sum-itqde was
    backfilled to full connectivity at the T6->T7 integration (2026-07-02); the gate
    must hold it there - a regression to orphans is a real defect, not history."""
    r = verify.check_connectivity("subset-sum-itqde")
    assert r["pass"] is True, f"orphans regressed: {r['orphans']}"
    assert r["reachable_from_spine"] == r["total_nodes"]
    assert r["orphans"] == []
    assert isinstance(r["orphan_kinds"], dict)


def test_connectivity_exempts_the_synthetic_containers_so_pass_is_reachable():
    """The apex ``paper://`` and the bibliography shell ``references`` are minted ABOVE
    the spine by ``corpus_ingest.atomise_paper`` - they contain the spine, nothing in the
    spine descends to them. Before 2026-08-21 the gate demanded a beat reach them, which
    pinned ``pass`` at False on every fully-wired corpus (synthetics-definition sat at
    79/81 with those two as its only 'orphans'). They are exempt and named; the verdict
    is now reachable."""
    r = verify.check_connectivity("synthetics-definition")
    assert r["pass"] is True, f"real orphans: {r['orphans']}"
    assert r["structural_exempt"] == ["paper://", "references"]
    # exempt is not the same as reachable: they are dropped from the demand, not walked to
    assert set(r["structural_exempt"]).isdisjoint(r["orphans"])
    assert r["content_nodes"] == r["total_nodes"] - len(r["structural_exempt"])
    assert r["ratio"] == 1.0


def test_connectivity_ratio_is_first_class_and_pass_still_refuses_real_orphans():
    """The exemption is exactly two container nodes - it never launders a content orphan.
    A half-wired corpus still fails, and ``ratio`` reports the degree over CONTENT nodes
    for gauges that want how-far rather than the verdict."""
    r = verify.check_connectivity("free-snacks")
    if r.get("pass") is None:
        pytest.skip(f"free-snacks unresolvable here: {r.get('note')}")
    assert r["pass"] is False and r["orphans"]
    assert "paper" not in r["orphan_kinds"] and "references" not in r["orphan_kinds"]
    assert 0.0 < r["ratio"] < 1.0
    assert r["ratio"] == round(r["reachable_content"] / r["content_nodes"], 4)


def test_structural_container_predicate_matches_the_minting_contract_not_the_name():
    """Exemption keys on kind (+ parentless for the apex), never on the id string: a
    content node that happens to be called ``references`` is still held to the demand."""
    assert verify._is_structural_container("paper://", {"kind": "paper", "parent": None})
    assert verify._is_structural_container("references", {"kind": "references", "parent": "paper://"})
    # a mid-tree node of kind 'paper' (not the apex) is content, not a container
    assert not verify._is_structural_container("paper://cited", {"kind": "paper", "parent": "sec:x"})
    # the name alone buys nothing
    assert not verify._is_structural_container("references", {"kind": "support", "parent": "sec:x"})


def test_connectivity_check_reports_missing_corpus():
    """A corpus name the registry does not know returns manual with a why - the gate
    never invents connectivity for a store it cannot resolve."""
    r = verify.check_connectivity("this-corpus-does-not-exist")
    assert r["pass"] is None
    assert r["manual"] is True
    # the note names the ONE list it was looked up in (verify.py's own wording)
    assert "not in the registry roster" in r["note"]


def test_projection_labels_check_shape_on_real_corpus():
    """Every labelable node (fig:, eq:, thm:, def:, ref:) needs projection.latex_label;
    experiment-result figures also need projection.data_source. The check returns a
    concrete shape - counts + missing lists - regardless of whether the corpus is fully
    labelled yet, so a downstream reader can act without inspecting the state."""
    r = verify.check_projection_labels("subset-sum-itqde")
    assert r["pass"] in (True, False)  # decided, never manual for a real corpus
    assert r["labelable_nodes"] > 0
    # pass state and missing list are consistent
    if r["pass"]:
        assert not r["missing_latex_label"]
        assert not r["missing_data_source"]
    else:
        assert r["missing_latex_label"] or r["missing_data_source"]
    # every data_source miss must be an experiment-result fig, never something else
    assert all(nid.startswith("fig:exp-") for nid in r["missing_data_source"])


def test_glossary_check_manual_without_project(tmp_path):
    """The glossary gate rides the same project-keyed dispatch as the other
    build-completion gates: no project, no verdict."""
    rep = verify.verify(str(tmp_path), checks=["glossary"])
    assert rep["checks"]["glossary"]["pass"] is None
    assert rep["checks"]["glossary"]["manual"] is True


def test_glossary_check_holds_on_real_corpus():
    """Terminology is locked at the conceptric level (2026-07-02): every def carries
    projection.term, no two defs claim one term/alias, and deprecated vocabulary
    (e.g. 'visibility lift' post-F32) appears in no live essence. The advisory
    naked-term list is always present and never affects the verdict."""
    r = verify.check_glossary("subset-sum-itqde")
    assert r["pass"] is True, (r["missing_term"], r["collisions"], r["deprecated_hits"])
    assert r["defs"] > 60
    assert r["terms_claimed"] >= r["defs"]
    assert isinstance(r["advisory_naked_terms"], list)


def test_glossary_norm_folds_case_hyphen_plural():
    """'Overlap Families' and 'overlap-family' are the same term of art."""
    assert verify._norm_term("Overlap Families") == verify._norm_term("overlap-family")
    assert verify._norm_term("Visibility  Lift") == "visibility lift"


def test_substrate_check_holds_on_real_corpus():
    """Nothing is assumed: every res:/thm:/goal: node reaches literature (ref:/sup:)
    within 2 outgoing hops (backfilled 2026-07-02). Data files are not literature."""
    r = verify.check_substrate("subset-sum-itqde")
    assert r["pass"] is True, f"unscaffolded claims: {r['unscaffolded']}"
    assert r["claim_nodes"] >= 25


def test_substrate_check_manual_without_corpus():
    r = verify.check_substrate("this-corpus-does-not-exist")
    assert r["pass"] is None
    assert r["manual"] is True


def test_figures_check_holds_on_real_corpus():
    """Every fig: node carries a stranger-reproducible provenance block (kind,
    engine/generator, banked commits, reproduce recipe) - set 2026-07-02."""
    r = verify.check_figures("subset-sum-itqde")
    assert r["pass"] is True, f"figure provenance defects: {r['defects']}"
    assert r["figure_nodes"] >= 19


def test_verify_canon_check_catches_inconsistency(tmp_path):
    """The consistency guard turned on the engine itself: a dangling canon link
    fails checks=['canon'], reported with its source detail rather than as a
    manuscript mismatch. The target path is ignored - the check is the canon."""
    root = tmp_path / "canon"
    (root / "wiki" / "workflow").mkdir(parents=True)
    (root / "skills").mkdir(parents=True)
    (root / "index.yaml").write_text(
        "version: 1\nwiki:\n  workflow/a: {title: A, scope: global}\n", encoding="utf-8"
    )
    (root / "wiki" / "workflow" / "a.md").write_text(
        "# A\n\nLeans on [[a_page_that_does_not_exist]].\n", encoding="utf-8"
    )
    small = Canon.load(root)
    rep = verify.verify(str(tmp_path), checks=["canon"], canon=small)
    assert rep["checks"]["canon"]["pass"] is False
    assert rep["passed"] is False
    assert any(d["from"] == "wiki:workflow/a" for d in rep["checks"]["canon"]["dangling"])
    # ancestral baseline is reported, not counted as a failure
    assert "ancestral_count" in rep["checks"]["canon"]


# ---------------------------------------------------------------------------
# assessment + lifecycle
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    telemetry.clear()
    yield
    telemetry.clear()


def test_fitness_promotes_and_deprecates(isolated_canon):
    # isolated_canon seeds both skills experimental, so good evidence promotes
    # latex_forge to core and sustained non-use deprecates sample_widget.
    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    for _ in range(9):
        telemetry.log("orient", domain="web", offered=["sample_widget"])
    rep = assess.assess(Canon.load())
    moves = {t["name"]: t["to"] for t in rep["transitions"]}
    assert moves.get("latex_forge") == "core"
    assert moves.get("sample_widget") == "deprecated"
    assert "sample_widget" in rep["unused"]


def test_recently_committed_skill_is_spared_from_deprecation(isolated_canon):
    # A skill refined/forged in the assess window is spared the "offered, never used"
    # deprecation: refining a SKILL.md emits no usage event, so the commit is the
    # evidence of work the telemetry missed. A blind dream must not deprecate the
    # newest canon the same window it was built.
    dst = isolated_canon
    md = dst / "skills" / "sample_widget" / "SKILL.md"
    md.write_text(md.read_text(encoding="utf-8") + "\n<!-- refined this window -->\n", encoding="utf-8")
    gitio.commit_all(dst, "refine sample_widget")  # a non-root commit in-window

    # Both offered+unused, both non-structural. sample_widget was just committed;
    # sample_gadget was not. (latex_forge is unusable here as a deprecation
    # example: it is the structural Trunk owner, so it is protected regardless.)
    for _ in range(9):
        telemetry.log("orient", domain="web", offered=["sample_widget"])
        telemetry.log("orient", domain="web", offered=["sample_gadget"])
    rep = assess.assess(Canon.load())
    moves = {t["name"]: t["to"] for t in rep["transitions"]}
    assert moves.get("sample_widget") != "deprecated"     # spared by the commit grace
    assert moves.get("sample_gadget") == "deprecated"     # not recently committed => deprecates


def test_unused_experimental_not_promoted(isolated_state):
    rep = assess.assess(Canon.load())
    # With no telemetry, nothing earns promotion.
    assert all(t["to"] != "core" for t in rep["transitions"])


def test_structural_skill_spared_from_silence_deprecation(isolated_canon):
    # literature_scout is referenced by the GLOBAL workflow nodes (core_outward_trunk,
    # evidence_schema_flow) - structural. Offered-but-unused must NOT deprecate it:
    # it is phase-dormant (the literature rail is dormant in a figure phase), not unfit.
    for _ in range(9):
        telemetry.log("orient", domain="global", offered=["literature_scout"])
    rep = assess.assess(Canon.load())
    moves = {t["name"]: t["to"] for t in rep["transitions"]}
    assert moves.get("literature_scout") != "deprecated"
    # but a skill not referenced by any global wiki node or core skill is NOT
    # structural and still deprecates on the same silence.
    for _ in range(9):
        telemetry.log("orient", domain="web", offered=["sample_widget"])
    rep2 = assess.assess(Canon.load())
    moves2 = {t["name"]: t["to"] for t in rep2["transitions"]}
    assert moves2.get("sample_widget") == "deprecated"


def test_structural_experimental_skill_promotes_on_standing_not_count(isolated_canon):
    # R3: a structural, experimental skill (referenced by a global wiki node / core
    # skill) is surfaced at orient yet emits no `execute` event, so it can never meet
    # PROMOTE_MIN_USES and reads "probationary" forever. The symmetric counterpart to
    # no-deprecate-on-silence: once it is a live architectural participant (offered)
    # with no genuine negative outcome, it has earned core on standing, not on count.
    # literature_scout is experimental + structural in the seed canon.
    assert Canon.load().skills["literature_scout"].status == "experimental"
    for _ in range(9):
        telemetry.log("orient", domain="global", offered=["literature_scout"])
    rep = assess.assess(Canon.load())
    moves = {t["name"]: t["to"] for t in rep["transitions"]}
    assert moves.get("literature_scout") == "core"


def test_structural_promotion_blocked_by_genuine_negative_outcome(isolated_canon):
    # The promotion is on standing, but never over evidence of unfitness: a structural
    # skill with a measured low verify pass-rate must NOT leap to core on silence.
    for _ in range(9):
        telemetry.log("orient", domain="global", offered=["literature_scout"])
    for _ in range(6):  # genuine negative outcome: failing verify checks
        telemetry.log("verify_check", skill="literature_scout", check="x", passed=False)
    rep = assess.assess(Canon.load())
    moves = {t["name"]: t["to"] for t in rep["transitions"]}
    assert moves.get("literature_scout") != "core"


def test_orient_dashboard_when_goal_unclear():
    c = Canon.load()
    # a blank goal surfaces the dashboard: active projects + the three activities,
    # so a session with no clear task picks a thread rather than guessing.
    bundle = c.orient("")
    assert "dashboard" in bundle
    dash = bundle["dashboard"]
    assert dash["active_projects"], "dashboard should list active projects"
    assert any(p["domain"] == "synthetics" for p in dash["active_projects"])
    assert set(dash["activities"]) == {"generating", "staging", "evaluating"}
    # a goal with a clear domain does NOT get the dashboard
    clear = c.orient("draft the adaptive normal form manuscript", domain="synthetics")
    assert "dashboard" not in clear


def test_dashboard_surfaces_engine_state_frontier():
    """Step 5: the dashboard carries the engine's own standing agenda from the
    canon graph - the frontier, contradictions, and the ancestral cohort - so an
    unfocused session sees the engine's to-do, not just the projects."""
    dash = Canon.load().dashboard()
    eng = dash["engine_state"]
    assert eng["available"] is True
    assert "frontier" in eng and {"loose", "unsourced"} <= set(eng["frontier"])
    assert "contradictions" in eng
    # the packaged canon is the inherited baseline, so the cohort is non-empty
    assert eng["ancestral_count"] > 0
    assert isinstance(eng["consistency_pass"], bool)


# ---------------------------------------------------------------------------
# hierarchicalisation: coarse nodes stand in for clusters, orient stays scale-local
# ---------------------------------------------------------------------------


@pytest.fixture
def cluster_canon(tmp_path) -> Canon:
    """A canon with a nested cluster: a coarse root, leaves derived under it, a
    coarse node nested two deep (recursion), an explicit-parent override, and an
    unclustered standalone."""
    root = tmp_path / "canon"
    (root / "wiki" / "lib" / "sub").mkdir(parents=True)
    (root / "skills").mkdir(parents=True)
    manifest = {
        "version": 1,
        "wiki": {
            "lib/index": {"title": "Library", "scope": "global"},
            "lib/alpha": {"title": "Alpha", "scope": "global"},
            "lib/sub/index": {"title": "Sub", "scope": "global"},
            "lib/sub/leaf": {"title": "Leaf", "scope": "global"},
            "lib/special": {"title": "Special", "scope": "global", "parent": "standalone"},
            "standalone": {"title": "Standalone", "scope": "global"},
        },
        "domains": {}, "skills": {},
    }
    (root / "index.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    (root / "lifecycle.yaml").write_text("skills: {}\n", encoding="utf-8")
    for ref, title in [
        ("lib/index", "Library"), ("lib/alpha", "Alpha"), ("lib/sub/index", "Sub"),
        ("lib/sub/leaf", "Leaf"), ("lib/special", "Special"), ("standalone", "Standalone"),
    ]:
        (root / "wiki" / f"{ref}.md").write_text(f"# {title}\n\nBody.\n", encoding="utf-8")
    return Canon.load(root)


def test_cluster_parent_derivation_and_recursion(cluster_canon: Canon):
    w = cluster_canon.wiki
    assert w["lib/index"].parent is None              # cluster root
    assert w["lib/alpha"].parent == "lib/index"       # derived one level down
    assert w["lib/sub/index"].parent == "lib/index"   # an index climbs a level (recursion)
    assert w["lib/sub/leaf"].parent == "lib/sub/index"
    assert w["standalone"].parent is None


def test_explicit_parent_overrides_derived(cluster_canon: Canon):
    # lib/special would derive lib/index, but the manifest pins it to standalone
    assert cluster_canon.wiki["lib/special"].parent == "standalone"


def test_global_foundation_is_top_level_only(cluster_canon: Canon):
    refs = {n.ref for n in cluster_canon.global_foundation()}
    assert refs == {"lib/index", "standalone"}


def test_clusters_map_is_recursive(cluster_canon: Canon):
    cl = cluster_canon.clusters()
    assert set(cl) == {"canon://lib/index", "canon://lib/sub/index", "canon://standalone"}
    members = {m["ref"] for m in cl["canon://lib/index"]["members"]}
    assert members == {"canon://lib/alpha", "canon://lib/sub/index"}
    sub = next(m for m in cl["canon://lib/index"]["members"] if m["ref"] == "canon://lib/sub/index")
    assert sub["coarse"] is True  # a coarse member is flagged so the reader descends further


def test_orient_foundation_marks_coarse_and_hides_interior(cluster_canon: Canon):
    b = cluster_canon.orient("anything")
    refs = {f["ref"] for f in b["foundation"]}
    assert "canon://lib/index" in refs
    assert "canon://lib/alpha" not in refs  # interior, hidden behind the coarse node
    lib = next(f for f in b["foundation"] if f["ref"] == "canon://lib/index")
    assert lib["nested_count"] == 2 and "descend" in lib


def test_orient_available_refs_excludes_interior(cluster_canon: Canon):
    b = cluster_canon.orient("anything")
    assert "canon://lib/index" in b["available_refs"]
    assert "canon://lib/alpha" not in b["available_refs"]  # reachable via clusters, not flattened


def test_live_canon_voice_corpus_collapses_to_one_coarse_node():
    """The concrete win: the voice-corpus leaves no longer flatten into the
    foundation - only their coarse index stands in for them."""
    b = Canon.load().orient("start a new working session")
    vc = [f["ref"] for f in b["foundation"] if "voice_corpus" in f["ref"]]
    assert vc == ["canon://voice_corpus/index"]
    idx = next(f for f in b["foundation"] if f["ref"] == "canon://voice_corpus/index")
    assert idx["nested_count"] >= 10


# ---------------------------------------------------------------------------
# dreamer (isolated canon copy outside the repo => independent git repo)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_canon(tmp_path, monkeypatch):
    dst = tmp_path / "canon"
    # Copy files only, not the canon's own nested .git. The fixture wants a clean
    # baseline whose single root commit is the promotion/deprecation target. The
    # live canon's nested repo can carry a dirty working tree (uncommitted session
    # edits); a copied .git would turn those into a non-root "seed" commit touching
    # every file - wrongly marking every skill "recently committed" and granting the
    # probation grace, so nothing would ever deprecate. Excluding it keeps the test
    # robust to the state of the real canon repo.
    shutil.copytree(canonmod._PACKAGED_CANON, dst, ignore=shutil.ignore_patterns(".git"))
    monkeypatch.setenv("LAPLACE_CANON", str(dst))
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    # This fixture IS the dreamer-write test harness (isolated canon, root commit as
    # a rollback target). The flag is set explicitly rather than left to the default:
    # the default is now UNFROZEN (2026-08-20 night - his freeze's pre-registered bar
    # was measured and met, D1/D2b, and the residual replaced usage-count in fitness),
    # but a harness that writes should say so in its own setup rather than inherit a
    # default that has already changed once today.
    monkeypatch.setenv(dreamer.DREAMER_WRITE_FLAG, "1")
    telemetry.clear()
    # Deterministic lifecycle baseline, independent of whatever statuses the
    # shipped manifest happens to carry: the skills these tests exercise start
    # experimental. Committed as the repo's base so promotion/deprecation are
    # genuine transitions and a dreamer rollback has a target to revert to.
    # Synthetic non-structural skills for the deprecation tests, created here so
    # they never depend on whatever the shipped canon happens to carry - curating
    # a real skill out of the canon must not break a lifecycle test. Neither is
    # referenced by any global wiki node or core skill, so both are non-structural
    # and deprecate on silence.
    for nm in ("sample_widget", "sample_gadget"):
        skdir = dst / "skills" / nm
        skdir.mkdir(parents=True, exist_ok=True)
        (skdir / "SKILL.md").write_text(
            f"---\nname: {nm}\ndescription: Throwaway experimental skill for lifecycle tests.\n"
            f"---\n\n# {nm}\n\n[EXPERIMENTAL] Test fixture skill, intentionally unreferenced.\n",
            encoding="utf-8",
        )
    seed = {"skills": {
        "latex_forge": {"status": "experimental"},
        "sample_widget": {"status": "experimental"},
        "sample_gadget": {"status": "experimental"},
    }}
    (dst / "lifecycle.yaml").write_text(yaml.safe_dump(seed), encoding="utf-8")
    gitio.commit_all(dst, "seed: experimental baseline + test skills")
    canonmod.get_canon(fresh=True)
    yield dst
    telemetry.clear()


def test_dream_applies_transitions_commits_and_rolls_back(isolated_canon):
    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    out = dreamer.dream(apply=True, forge=False)
    assert any(t["name"] == "latex_forge" and t["to"] == "core" for t in out["assessment"]["transitions"])
    assert out.get("commit")
    # status persisted through the lifecycle overlay
    assert canonmod.get_canon(fresh=True).skills["latex_forge"].status == "core"
    # rollback reverts
    rb = dreamer.rollback(out["commit"])
    assert rb["ok"]
    assert canonmod.get_canon(fresh=True).skills["latex_forge"].status == "experimental"


def test_dream_noop_without_evidence(isolated_canon):
    out = dreamer.dream(apply=True, forge=False)
    assert out["assessment"]["transitions"] == []
    assert out.get("commit") is None


def test_noop_dream_does_not_advance_boundary(isolated_canon):
    # An idle dream - empty window, nothing applied or forged - must NOT stamp the
    # boundary, or a later dream's window would be fragmented and friction orphaned.
    out0 = dreamer.dream(apply=True, forge=False)
    assert out0["assessment"]["events_seen"] == 0
    assert out0["boundary_advanced"] is False
    assert telemetry.last_dream_ts() is None
    # A productive dream (earns a transition) does advance the boundary.
    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    out1 = dreamer.dream(apply=True, forge=False)
    assert out1["boundary_advanced"] is True
    assert telemetry.last_dream_ts() is not None


def test_preview_dream_does_not_consume_window(isolated_canon):
    # The leak that orphaned a real session: an apply=False preview over a FULL
    # window stamped the boundary, so the next apply=True dream saw zero events and
    # applied nothing. A preview (or any dream that applies no transition) must not
    # consume the window - the evidence has to survive for the next real dream.
    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    preview = dreamer.dream(apply=False, forge=False)
    assert preview["assessment"]["events_seen"] == 6
    assert any(t["name"] == "latex_forge" for t in preview["assessment"]["transitions"])
    assert preview["boundary_advanced"] is False  # preview did NOT consume the window
    assert telemetry.last_dream_ts() is None
    # the real dream still sees the same evidence and applies it
    real = dreamer.dream(apply=True, forge=False)
    assert real["assessment"]["events_seen"] == 6
    assert real["boundary_advanced"] is True
    assert canonmod.get_canon(fresh=True).skills["latex_forge"].status == "core"


def test_events_since_filters_by_timestamp(isolated_state):
    telemetry.log("feedback", skill="latex_forge", signal=1)
    cutoff = telemetry.events()[-1]["ts"]  # timestamp of that event
    telemetry.log("feedback", skill="latex_forge", signal=1)  # after cutoff
    after = telemetry.events(since=cutoff)
    # only the event AT or AFTER cutoff survives; the one strictly before does not
    assert all(ev["ts"] >= cutoff for ev in after)
    assert len(after) >= 1


def test_dream_stamps_and_scopes_next_dream(isolated_canon):
    # Pre-dream events: earn a transition.
    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    out1 = dreamer.dream(apply=True, forge=False)
    # dream_complete was logged — last_dream_ts is non-None.
    ts = telemetry.last_dream_ts()
    assert ts is not None
    # Second dream sees only events AFTER the first dream's stamp.
    # No new events => assess sees nothing => no transitions.
    out2 = dreamer.dream(apply=False, forge=False)
    assert out2["assessment"]["events_seen"] == 0


def test_dream_is_graded_day_misses_what_standing_catches(isolated_canon):
    # E3, the conjugate-at-grade fix: a skill earns a move on its STANDING, but the DAY
    # window (since the last day-dream) has moved past the evidence. The day-dream must
    # miss it (it absorbed nothing new today); the standing-dream catches it. The dream
    # is graded - the fix is NOT to flatten the day-dream to cumulative.
    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    telemetry.log("dream_complete")  # the day-boundary advances past the evidence
    day = dreamer.dream(apply=False, grade=0)
    assert day["assessment"]["events_seen"] == 0
    assert not any(t["name"] == "latex_forge" for t in day["assessment"]["transitions"])
    standing = dreamer.dream(apply=False, grade=1)
    assert standing["assessment"]["events_seen"] >= 6
    assert any(t["name"] == "latex_forge" for t in standing["assessment"]["transitions"])


def test_assess_and_dream_are_conjugate_at_each_grade(isolated_canon):
    # The open and the close read the SAME window at the same grade: what assess shows at
    # grade k is what dream applies at grade k. (E3 was the cross-grade read - open
    # cumulative, close the day.)
    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    telemetry.log("dream_complete")                            # advance the day-boundary
    telemetry.log("feedback", skill="latex_forge", signal=1)   # one new day-event

    since0 = telemetry.last_dream_ts()
    open0 = assess.assess(canonmod.get_canon(fresh=True), since=since0)   # the day
    close0 = dreamer.dream(apply=False, grade=0)
    assert open0["events_seen"] == close0["assessment"]["events_seen"]
    assert ([t["name"] for t in open0["transitions"]]
            == [t["name"] for t in close0["assessment"]["transitions"]])

    open1 = assess.assess(canonmod.get_canon(fresh=True), since=None)     # the standing
    close1 = dreamer.dream(apply=False, grade=1)
    assert open1["events_seen"] == close1["assessment"]["events_seen"]
    assert ([t["name"] for t in open1["transitions"]]
            == [t["name"] for t in close1["assessment"]["transitions"]])


def test_standing_dream_does_not_move_the_day_clock(isolated_canon):
    # A coarser standing-dream consolidates the record but must NOT stamp the day-boundary
    # (a different grade); the day-clock only advances on a productive day-dream.
    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    out = dreamer.dream(apply=True, grade=1)              # the standing-dream applies it
    assert any(t["name"] == "latex_forge" for t in out["assessment"]["transitions"])
    assert out["boundary_advanced"] is False              # the day-clock did not move
    assert telemetry.last_dream_ts() is None


def test_day_boundary_is_immune_to_a_coarse_clock(isolated_canon, monkeypatch):
    # Force the worst case the coarse Windows clock can produce: EVERY event - the six
    # verify_checks AND the dream_complete marker - stamped with one identical timestamp.
    # A ts-based boundary (`ts >= marker`) leaks the same-tick verify_checks into the day
    # window (events_seen reads >0 when it must read 0); the positional (ts, seq) boundary
    # must not. This pins the fix deterministically, independent of the host clock's
    # resolution - it fails on the old code every run, not one run in two.
    from datetime import datetime as _dt, timezone as _tz

    frozen = _dt(2026, 6, 7, 12, 0, 0, tzinfo=_tz.utc)

    class _FrozenClock:
        @staticmethod
        def now(tz=None):
            return frozen

    monkeypatch.setattr(telemetry, "datetime", _FrozenClock)

    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    telemetry.log("dream_complete")  # shares the verify_checks' exact timestamp

    evs = telemetry.events()
    assert len({e["ts"] for e in evs}) == 1            # the tie is real: one shared ts
    assert [e["seq"] for e in evs] == sorted(e["seq"] for e in evs)  # seq orders them
    assert evs[-1]["phase"] == "dream_complete"        # the marker still sorts last

    # The day window is empty - nothing was logged after the marker - despite the tie.
    assert telemetry.events_since_last_dream() == []
    day = dreamer.dream(apply=False, grade=0)
    assert day["assessment"]["events_seen"] == 0
    assert not any(t["name"] == "latex_forge" for t in day["assessment"]["transitions"])

    # The standing still sees the full record and earns the move.
    standing = dreamer.dream(apply=False, grade=1)
    assert standing["assessment"]["events_seen"] == 6
    assert any(t["name"] == "latex_forge" for t in standing["assessment"]["transitions"])




# ---------------------------------------------------------------------------
# evidence skills (ledger completeness + alignment)
# ---------------------------------------------------------------------------

LEDGER = """# Evidence Ledger

## EPT-CLM-001: Strong claim about gain
**Claim:** The gain scales as sqrt(N).
**Derivation:** Appendix A.
**Literature:** Condorcet (1785).
**Numerical:** validate_gain().
**Status:** Proved.

## EPT-CLM-002: Weak claim about depth
**Claim:** Hierarchy depth must exceed three.
**Derivation:** Sketch only.
**Literature:** none
**Numerical:** TODO
**Status:** conjecture, gap remains.
"""


def test_evidence_ledger_flags_incomplete_and_weak(tmp_path):
    led = tmp_path / "evidence_ledger.md"
    led.write_text(LEDGER, encoding="utf-8")
    r = verify.run_backing("evidence_ledger", target=str(led))
    out = r["stdout"]
    assert "Records: 2" in out
    assert "EPT-CLM-002" in out  # weak/incomplete flagged
    assert "EPT-CLM-001" not in out.split("Incomplete")[-1].split("Non-affirmative")[0] \
        if "Incomplete" in out else True  # strong claim not in incomplete section
    assert r["returncode"] == 1  # incomplete records => exit 1


IDENTITY = """# Identity Ledger

## ID-001: Widget Theorem
**Kind:** coined-term
**Forms:** widget theorem, WT
**Role:** the core named result; must appear.
**Status:** load-bearing

## ID-002: Gadget framing
**Kind:** framing
**Forms:** gadget framing
**Role:** preferred cross-domain bridge.
**Status:** optional
"""


def test_identity_ledger_detects_drift(tmp_path):
    man = tmp_path / "identity_ledger.md"
    man.write_text(IDENTITY, encoding="utf-8")
    draft = tmp_path / "draft.tex"
    draft.write_text("This draft uses the gadget framing but never the core result.\n", encoding="utf-8")
    r = verify.run_backing("identity_ledger", target=str(draft), args=["--manifest", str(man)])
    assert "DRIFT" in r["stdout"]
    assert "ID-001" in r["stdout"]  # load-bearing Widget Theorem dropped
    assert r["returncode"] == 1


def test_identity_ledger_passes_when_present(tmp_path):
    man = tmp_path / "identity_ledger.md"
    man.write_text(IDENTITY, encoding="utf-8")
    draft = tmp_path / "draft.tex"
    draft.write_text("We prove the Widget Theorem via the gadget framing.\n", encoding="utf-8")
    r = verify.run_backing("identity_ledger", target=str(draft), args=["--manifest", str(man)])
    assert "No identity drift" in r["stdout"]
    assert r["returncode"] == 0


def test_evidence_alignment_tiers_and_finds_uncovered_goal(tmp_path):
    led = tmp_path / "evidence_ledger.md"
    led.write_text(LEDGER, encoding="utf-8")
    r = verify.run_backing(
        "evidence_alignment", target=str(led),
        args=["--goals", "gain, teleportation"],
    )
    out = r["stdout"]
    assert "1 strong, 0 partial, 1 weak" in out
    assert "gain" in out
    assert "teleportation" in out and "uncovered" in out.lower()
    assert (tmp_path / "support_map.md").exists()


def test_voice_corpus_reader_chunks_without_leaking_source(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text(
        "\n\n".join(
            [
                "alpha private sentence " * 8,
                "beta private sentence " * 8,
                "gamma private sentence " * 8,
            ]
        ),
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    args = [
        "--source-handle", "TEST-SOURCE",
        "--register", "personal",
        "--source-kind", "unit",
        "--cache-root", str(cache),
        "--max-chars", "120",
        "--salt", "test-salt",
    ]

    first = verify.run_backing("voice_corpus_reader", target=str(source), args=args)
    assert first["returncode"] == 0
    assert "alpha private sentence" not in first["stdout"]
    assert "beta private sentence" not in first["stdout"]

    manifest_path = cache / "manifests" / "TEST-SOURCE.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "voice-corpus-chunks/0.1"
    assert manifest["source"]["source_handle"] == "TEST-SOURCE"
    assert manifest["source"]["register"] == "personal"
    assert len(manifest["chunks"]) == 3
    assert all((cache / "chunks" / "TEST-SOURCE" / f"{c['chunk_id']}.txt").exists() for c in manifest["chunks"])
    assert all(c["byte_end"] > c["byte_start"] for c in manifest["chunks"])

    first_ids = [c["chunk_id"] for c in manifest["chunks"]]
    first_source_hash = manifest["source"]["source_id_hash"]
    second = verify.run_backing("voice_corpus_reader", target=str(source), args=args)
    assert second["returncode"] == 0
    manifest2 = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [c["chunk_id"] for c in manifest2["chunks"]] == first_ids
    assert manifest2["source"]["source_id_hash"] == first_source_hash


def test_voice_corpus_reader_can_prepare_restartable_queue(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text(
        "\n\n".join(
            [
                "first private paragraph " * 8,
                "second private paragraph " * 8,
            ]
        ),
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    args = [
        "--source-handle", "QUEUE-SOURCE",
        "--register", "academic",
        "--source-kind", "unit",
        "--cache-root", str(cache),
        "--max-chars", "120",
        "--salt", "test-salt",
        "--reader-queue",
        "--reader-tasks", "voice,facts",
    ]

    result = verify.run_backing("voice_corpus_reader", target=str(source), args=args)
    assert result["returncode"] == 0
    assert "first private paragraph" not in result["stdout"]
    assert "Reader queue:" in result["stdout"]
    assert "Reader jobs: 4" in result["stdout"]

    queue_path = cache / "readers" / "QUEUE-SOURCE" / "queue.jsonl"
    queue_text = queue_path.read_text(encoding="utf-8")
    assert "first private paragraph" not in queue_text
    assert "second private paragraph" not in queue_text

    jobs = [json.loads(line) for line in queue_text.splitlines()]
    assert len(jobs) == 4
    assert {job["reader_task"] for job in jobs} == {"voice", "facts"}
    assert all(job["status"] == "pending" for job in jobs)
    assert all(job["attempts"] == 0 for job in jobs)
    assert all(job["output_path"].endswith(f".{job['reader_task']}.json") for job in jobs)


# ---------------------------------------------------------------------------
# watchdog: no handler may hang the caller (the assess-hang structural fix)
# ---------------------------------------------------------------------------


def test_run_backing_failure_records_returncode_and_stderr_tail(tmp_path, monkeypatch):
    """A non-zero backing-script exit must record returncode and stderr_tail in
    the emitted execute telemetry event, so the dreamer can self-diagnose
    without re-running the script.
    """
    import shutil

    # Build a minimal isolated canon with a skill whose backing script fails.
    dst = tmp_path / "canon"
    shutil.copytree(canonmod._PACKAGED_CANON, dst)
    monkeypatch.setenv("LAPLACE_CANON", str(dst))
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))

    skill_dir = dst / "skills" / "failing_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: always fails\n---\n# Failing Skill\n",
        encoding="utf-8",
    )
    # A Python backing script that writes a known message to stderr and exits 2.
    backing = skill_dir / "run.py"
    backing.write_text(
        "import sys\n"
        "sys.stderr.write('something went wrong: detail here\\n')\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )

    # Register it in the manifest overlay.
    import yaml
    idx = yaml.safe_load((dst / "index.yaml").read_text(encoding="utf-8"))
    idx.setdefault("skills", {})["failing_skill"] = {
        "description": "always fails",
        "activity": "staging",
        "status": "experimental",
        "backing": "run.py",
        "tags": [],
    }
    (dst / "index.yaml").write_text(yaml.safe_dump(idx), encoding="utf-8")
    canonmod.get_canon(fresh=True)

    telemetry.clear()
    result = verify.run_backing("failing_skill")
    assert result["returncode"] == 2
    assert result["ok"] is False

    events = telemetry.events()
    exec_events = [e for e in events if e["phase"] == "execute" and e.get("skill") == "failing_skill"]
    assert exec_events, "no execute event recorded for failing skill"
    ev = exec_events[-1]
    assert ev["ok"] is False
    assert ev["returncode"] == 2, f"expected returncode=2 in event, got {ev}"
    assert "stderr_tail" in ev, "stderr_tail must be present in failure event"
    assert "something went wrong" in ev["stderr_tail"], (
        f"expected stderr content in stderr_tail, got {ev['stderr_tail']!r}"
    )
    telemetry.clear()


def test_run_backing_success_also_records_returncode_and_stderr_tail(tmp_path, monkeypatch):
    """A successful backing-script run must also bank rc=0 (and whatever short/
    empty stderr it produced) in the telemetry event - the diagnostic fields
    are not failure-only, so a dreamer can trust their presence uniformly.
    """
    import shutil

    dst = tmp_path / "canon"
    shutil.copytree(canonmod._PACKAGED_CANON, dst)
    monkeypatch.setenv("LAPLACE_CANON", str(dst))
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))

    skill_dir = dst / "skills" / "passing_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: always passes\n---\n# Passing Skill\n",
        encoding="utf-8",
    )
    backing = skill_dir / "run.py"
    backing.write_text("import sys\nprint('all good')\nsys.exit(0)\n", encoding="utf-8")

    import yaml
    idx = yaml.safe_load((dst / "index.yaml").read_text(encoding="utf-8"))
    idx.setdefault("skills", {})["passing_skill"] = {
        "description": "always passes",
        "activity": "staging",
        "status": "experimental",
        "backing": "run.py",
        "tags": [],
    }
    (dst / "index.yaml").write_text(yaml.safe_dump(idx), encoding="utf-8")
    canonmod.get_canon(fresh=True)

    telemetry.clear()
    result = verify.run_backing("passing_skill")
    assert result["returncode"] == 0
    assert result["ok"] is True

    events = telemetry.events()
    exec_events = [e for e in events if e["phase"] == "execute" and e.get("skill") == "passing_skill"]
    assert exec_events
    ev = exec_events[-1]
    assert ev["ok"] is True
    assert ev["returncode"] == 0, f"expected returncode=0 banked on success, got {ev}"
    assert "stderr_tail" in ev, "stderr_tail must be present on success too (empty is fine)"
    assert ev["stderr_tail"] == "", f"expected empty stderr_tail for a quiet script, got {ev['stderr_tail']!r}"


def test_run_backing_long_stderr_is_bounded_with_truncation_marker(tmp_path, monkeypatch):
    """A backing script that floods stderr must not blow up the telemetry
    ledger - the tail is capped (~2000 chars) and prefixed with a truncation
    marker so a reader can tell a chopped tail from a genuinely short one.
    """
    import shutil

    dst = tmp_path / "canon"
    shutil.copytree(canonmod._PACKAGED_CANON, dst)
    monkeypatch.setenv("LAPLACE_CANON", str(dst))
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))

    skill_dir = dst / "skills" / "noisy_failing_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: fails noisily\n---\n# Noisy Failing Skill\n",
        encoding="utf-8",
    )
    # A backing script that writes far more than the tail limit to stderr,
    # with a recognisable marker at the very end, then exits non-zero.
    backing = skill_dir / "run.py"
    backing.write_text(
        "import sys\n"
        "sys.stderr.write('x' * 5000)\n"
        "sys.stderr.write('END-OF-STDERR')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )

    import yaml
    idx = yaml.safe_load((dst / "index.yaml").read_text(encoding="utf-8"))
    idx.setdefault("skills", {})["noisy_failing_skill"] = {
        "description": "fails noisily",
        "activity": "staging",
        "status": "experimental",
        "backing": "run.py",
        "tags": [],
    }
    (dst / "index.yaml").write_text(yaml.safe_dump(idx), encoding="utf-8")
    canonmod.get_canon(fresh=True)

    telemetry.clear()
    result = verify.run_backing("noisy_failing_skill")
    assert result["returncode"] == 1

    events = telemetry.events()
    exec_events = [
        e for e in events if e["phase"] == "execute" and e.get("skill") == "noisy_failing_skill"
    ]
    assert exec_events
    ev = exec_events[-1]
    assert ev["ok"] is False
    assert ev["returncode"] == 1
    tail = ev["stderr_tail"]
    # Bounded: well under the raw 5000+ chars actually written.
    assert len(tail) < 2100, f"stderr_tail not bounded, len={len(tail)}"
    # Truncation is signposted, and the most recent content survives the cut.
    assert tail.startswith("...[truncated]"), f"expected truncation marker, got {tail[:40]!r}"
    assert "END-OF-STDERR" in tail, "the tail of stderr should survive truncation"
    telemetry.clear()


def test_watchdog_passes_value_through():
    from laplace.core.process import guard

    assert guard("ok", 5, lambda: {"v": 42}) == {"v": 42}


def test_watchdog_off_by_default():
    """The watchdog ships OFF (the author's call, 2026-06-08): the outer cap only
    false-abandons slow-but-legitimate work now that the inner bounds are the real
    protection. ``guard`` runs the thunk inline, uncapped, when disabled."""
    from laplace.core import process as watchdog

    assert watchdog._ENABLED is False


def test_watchdog_returns_timeout_dict_on_overrun(monkeypatch):
    import time

    from laplace.core import process as watchdog
    from laplace.core.process import guard

    monkeypatch.setattr(watchdog, "_ENABLED", True)  # the cap applies only when the watchdog is ON
    t0 = time.time()
    out = guard("slow", 0.3, lambda: time.sleep(10))
    elapsed = time.time() - t0
    assert out["timed_out"] is True
    assert "watchdog" in out["error"] and out["cancelled"] is False
    assert elapsed < 2  # returned at the cap, did not wait out the 10s work


def test_watchdog_propagates_exceptions():
    from laplace.core.process import guard

    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        guard("boom", 5, boom)


def _poison_subprocess(monkeypatch):
    """Make every PIPE-CAPTURING spawn fail, the way a box with no git would.

    ``run``/``check_output`` are poisoned, not ``call``/``Popen``: the Windows
    incident's mechanism is an inherited *capture pipe* write handle, and
    Dulwich's own hook executor uses ``subprocess.call`` with no capture, so
    poisoning it would test Dulwich rather than the engine's git path."""
    import subprocess as _sp

    def _boom(*a, **k):
        raise AssertionError("engine git must not need a child process")

    for name in ("run", "check_output"):
        monkeypatch.setattr(_sp, name, _boom)


def test_engine_git_mutations_are_pure_python(tmp_path, monkeypatch):
    """THE INVARIANT, stated as behaviour rather than as a source grep.

    Dulwich replaced ``git.exe`` because Claude Code's background
    ``git-fsmonitor--daemon`` inherited the capture pipe's write handle and the
    read never saw EOF - ``laplace_assess`` froze for ~30 minutes. What that
    incident forbids is a *daemon-bearing child process on the engine's git
    path*, and the invariant that protects against it is: every mutation is
    Dulwich, and the whole surface still answers with no git binary at all.

    The old form asserted ``"import subprocess" not in gitio's source``. That
    is a proxy, and it is strictly weaker than the property it stands for - it
    would have passed a Dulwich-only module that spawned a daemon through
    ``os.system``, and it failed the read-only ``git log`` fast path that
    spawns nothing inheritable (F2, ~8.6x, parity-proven below). Replaced by
    the property itself; see WO-20260820-f2-invariant.
    """
    import inspect

    src = inspect.getsource(gitio)
    assert "from dulwich" in src or "import dulwich" in src

    # (1) The mutation surface reaches no child process, ever - proven by source
    #     over exactly those functions, not over the module.
    for fn in (gitio.ensure_repo, gitio.commit, gitio.commit_all, gitio.revert,
               gitio.head_sha):
        fsrc = inspect.getsource(fn)
        for banned in ("subprocess", "os.system", "os.popen", "os.spawn", "pty."):
            assert banned not in fsrc, f"{fn.__name__} must not shell out ({banned})"

    # (2) Exactly ONE function in the module may spawn, and it is the read-only
    #     log query. A new shelling function must state itself here on purpose.
    spawners = sorted(
        name for name, obj in vars(gitio).items()
        if inspect.isfunction(obj) and obj.__module__ == gitio.__name__
        and "subprocess." in inspect.getsource(obj)
    )
    assert spawners == ["_log_paths_since_subprocess"], spawners

    # (3) The fast path forces the daemon that caused the incident off.
    cfg = " ".join(gitio._GIT_READ_CONFIG)
    assert "core.fsmonitor=false" in cfg and "core.untrackedCache=false" in cfg

    # (4) The whole surface still works on a box with no git binary at all.
    _poison_subprocess(monkeypatch)
    repo = tmp_path / "r"
    repo.mkdir()
    f = repo / "f.txt"
    f.write_text("hi", encoding="utf-8")
    sha = gitio.commit(repo, [f], "init")
    assert sha and gitio.head_sha(repo) == sha
    f.write_text("bye", encoding="utf-8")
    gitio.commit(repo, [f], "second")
    # log_paths_since answers through the Dulwich fallback, not by raising and
    # not by the fail-silent empty set.
    assert gitio.log_paths_since(repo, None) == {"f.txt"}


def test_log_paths_since_subprocess_matches_dulwich(tmp_path):
    """F2's parity proof, as a standing test: the fast path and the walker return
    the SAME EXACT SET over every window, on paths that break naive parsing
    (spaces, unicode, a rename, a nested dir) and across the root-commit fence."""
    from datetime import datetime, timedelta, timezone

    repo = tmp_path / "r"
    repo.mkdir()

    def _write(rel, text):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    a = _write("a.txt", "1")
    gitio.commit(repo, [a], "root")  # the root commit: excluded by --min-parents=1
    made = [a]
    for rel in ("dir with spaces/b.txt", "unicode/ünï—çode.txt", "nested/deep/c.txt"):
        made.append(_write(rel, "x"))
        gitio.commit(repo, [made[-1]], f"add {rel}")
    # a rename (delete + add), which --no-renames must keep as two paths
    (repo / "a.txt").unlink()
    renamed = _write("a_renamed.txt", "1")
    gitio.commit_all(repo, "rename a.txt")

    windows = [None, "1970-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00",
               datetime.now(timezone.utc).isoformat(),
               (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()]
    for w in windows:
        cutoff = gitio._parse_since(w)
        dul = gitio._log_paths_since_dulwich(repo, cutoff)
        sub = gitio._log_paths_since_subprocess(repo, cutoff)
        assert sub is not None, "git log fast path unavailable in this environment"
        assert sub == dul, f"parity broke at window {w!r}: {sub ^ dul}"

    # And the public entry returns that same set, root commit excluded, with the
    # awkward paths intact rather than octal-escaped or split on their spaces.
    full = gitio.log_paths_since(repo, "1970-01-01T00:00:00+00:00")
    assert renamed.name in full
    assert "dir with spaces/b.txt" in full and "unicode/ünï—çode.txt" in full
    assert "nested/deep/c.txt" in full


def test_log_paths_since_kill_switch_forces_dulwich(tmp_path, monkeypatch):
    """LAPLACE_GIT_PURE_PYTHON=1 retires the fast path without a code change -
    the reversal path if the subprocess ever misbehaves on some host."""
    repo = tmp_path / "r"
    repo.mkdir()
    f = repo / "f.txt"
    f.write_text("hi", encoding="utf-8")
    gitio.commit(repo, [f], "root")
    f.write_text("bye", encoding="utf-8")
    gitio.commit(repo, [f], "second")

    monkeypatch.setenv("LAPLACE_GIT_PURE_PYTHON", "1")
    assert gitio._log_paths_since_subprocess(repo, 0) is None
    assert gitio.log_paths_since(repo, "1970-01-01T00:00:00+00:00") == {"f.txt"}
    monkeypatch.setenv("LAPLACE_GIT_PURE_PYTHON", "0")
    assert gitio._log_paths_since_subprocess(repo, 0) is not None


def test_log_paths_since_unavailable_git_is_not_an_empty_answer(tmp_path, monkeypatch):
    """The fail-silent this guard exists to refuse: a broken git must never read
    as "nothing moved". The fast path returns None (fall through), never set()."""
    repo = tmp_path / "r"
    repo.mkdir()
    f = repo / "f.txt"
    f.write_text("hi", encoding="utf-8")
    gitio.commit(repo, [f], "root")
    f.write_text("bye", encoding="utf-8")
    gitio.commit(repo, [f], "second")

    import subprocess as _sp

    class _Fail:
        returncode = 128
        stdout = b""
        stderr = b"fatal: not a git repository"

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _Fail())
    assert gitio._log_paths_since_subprocess(repo, 0) is None
    assert gitio.log_paths_since(repo, "1970-01-01T00:00:00+00:00") == {"f.txt"}


def test_gitio_commit_log_revert_roundtrip(tmp_path):
    """The whole engine git surface: commit_all, commit, log_paths_since, revert."""
    repo = tmp_path / "r"
    repo.mkdir()
    f = repo / "lifecycle.yaml"
    f.write_text("v: 1\n", encoding="utf-8")
    sha1 = gitio.commit_all(repo, "seed")
    assert sha1

    f.write_text("v: 2\n", encoding="utf-8")
    sha2 = gitio.commit(repo, [f], "bump")
    assert sha2 and sha2 != sha1

    # the non-root commit's changed path shows up in the window
    paths = gitio.log_paths_since(repo, None)
    assert paths is not None and any(p.endswith("lifecycle.yaml") for p in paths)

    # reverting the bump restores the seed content
    ok, _detail = gitio.revert(repo, sha2)
    assert ok
    assert f.read_text(encoding="utf-8") == "v: 1\n"


# ---------------------------------------------------------------------------
# Item 1 - dreamer reads the backlog
# ---------------------------------------------------------------------------


def test_dream_exposes_backlog_headers(isolated_canon):
    """dream() result must carry a 'backlog' key with the section headings from
    AUTONOMY_BACKLOG.md, so deferred items resurface each cycle.
    """
    out = dreamer.dream(apply=False, forge=False)
    assert "backlog" in out, "dream() must include a 'backlog' key"
    backlog = out["backlog"]
    assert backlog.get("available") is True, f"backlog should be readable: {backlog}"
    sections = backlog.get("sections", [])
    assert sections, "backlog sections list must not be empty"
    # The backlog has at least an 'Engine behaviour' section.
    assert any("Engine behaviour" in s for s in sections), (
        f"Expected 'Engine behaviour' in backlog sections, got: {sections}"
    )
    # Open items should surface too.
    assert isinstance(backlog.get("open_items"), list)


# ---------------------------------------------------------------------------
# Item 2 - orient-guard for domain=null
# ---------------------------------------------------------------------------


def test_orient_null_domain_carries_candidate_domains():
    """When a goal is too ambiguous to infer a domain, the orient bundle must
    include candidate domains inline under 'domain_recovery', so the model has
    everything it needs to re-orient without a second round trip.
    """
    c = Canon.load()
    # A goal with no domain-specific language should yield domain=None.
    bundle = c.orient("do something")
    # If domain inference happened to find a match, skip this check.
    if bundle["domain"] is not None:
        pytest.skip("goal unexpectedly matched a domain; need a more ambiguous goal")
    assert "domain_recovery" in bundle, (
        "orient bundle must include 'domain_recovery' when domain=None"
    )
    recovery = bundle["domain_recovery"]
    assert "hint" in recovery, "domain_recovery must include a hint"
    candidates = recovery.get("candidate_domains", [])
    assert candidates, "domain_recovery must list candidate domains"
    # Each candidate must have a name.
    assert all("name" in cd for cd in candidates), (
        f"all candidate_domains entries must have a 'name' key: {candidates}"
    )


def test_orient_with_explicit_domain_has_no_recovery():
    """When a domain is supplied or cleanly inferred, no domain_recovery key
    should appear - it is only an aid for the underdetermined case.
    """
    c = Canon.load()
    # 'synthetics' is a known domain that should be inferred.
    bundle = c.orient(
        "lint the latex voice and check derivations for the phases of hierarchy"
    )
    assert bundle["domain"] == "synthetics"
    assert "domain_recovery" not in bundle, (
        "domain_recovery must not appear when domain is determined"
    )


# ---------------------------------------------------------------------------
# Item 3 - fitness must not read silence as dissatisfaction
# ---------------------------------------------------------------------------


def test_fitness_silence_does_not_deprecate_healthy_skill(isolated_state):
    """A skill with healthy usage and verify pass-rate but zero explicit feedback
    must not be down-ranked relative to its usage.  Absence of praise alone must
    never trigger a deprecate recommendation.
    """
    # Drive a healthy usage pattern: 6 verify passes, zero explicit feedback.
    for _ in range(6):
        telemetry.log("verify_check", skill="latex_forge", check="voice", passed=True)
    # No laplace_log calls - silence, not dissatisfaction.

    rep = assess.assess(Canon.load())
    skill_row = next((r for r in rep["skills"] if r["name"] == "latex_forge"), None)
    assert skill_row is not None

    # The skill must not be recommended for deprecation.
    assert skill_row["recommended_status"] != "deprecated", (
        f"latex_forge was recommended for deprecation despite healthy usage and "
        f"zero (not negative) feedback: {skill_row}"
    )
    # Fitness must be respectable - usage and quality should dominate.
    assert skill_row["fitness"] >= 0.5, (
        f"fitness {skill_row['fitness']} too low for a skill with healthy usage "
        f"and zero negative feedback"
    )


def test_absence_of_praise_never_triggers_deprecate_recommendation(isolated_state):
    """Even when a skill has usage but zero laplace_log calls, the assess report
    must not recommend deprecation - silence is not dissatisfaction.
    """
    # Enough usage to pass the PROMOTE_MIN_USES threshold.
    for _ in range(6):
        telemetry.log("execute", skill="result_foundry", kind="protocol")

    rep = assess.assess(Canon.load())
    skill_row = next((r for r in rep["skills"] if r["name"] == "result_foundry"), None)
    if skill_row is None:
        pytest.skip("result_foundry not in canon; pick any skill with zero feedback")

    transitions = {t["name"]: t["to"] for t in rep["transitions"]}
    assert transitions.get("result_foundry") != "deprecated", (
        "absence of positive feedback alone must not trigger a deprecate recommendation"
    )


# ---------------------------------------------------------------------------
# floor fixes: one manuscript reading order; sharded telemetry merges
# ---------------------------------------------------------------------------


def test_crossref_follows_input_tree(tmp_path):
    """A ref resolving to a label in an \\input-ed child is not a broken ref.

    Regression: check_crossref used to read a single root .tex in isolation, so
    a \\ref to a label defined in a child file looked broken even though the
    paper compiles. Now it shares the conceptric's gatherer and follows the
    \\input tree - verification and graphing read the same files.
    """
    root = tmp_path / "main.tex"
    sub = tmp_path / "results.tex"
    sub.write_text("\\section{R}\\label{sec:r}\nText.\n", encoding="utf-8")
    root.write_text(
        "\\input{results}\nSee \\ref{sec:r} and \\eqref{eq:gone}.\n", encoding="utf-8"
    )
    rep = verify.check_crossref(str(root))
    broken = {b["ref"] for b in rep["broken_refs"]}
    assert "sec:r" not in broken, "label defined in an \\input-ed child must resolve"
    assert "eq:gone" in broken, "a genuinely undefined ref must still be flagged"


def test_crossref_detects_duplicate_labels_across_input_files(tmp_path):
    """The same label in two \\input-ed files is a duplicate, attributed per file."""
    root = tmp_path / "main.tex"
    a = tmp_path / "a.tex"
    b = tmp_path / "b.tex"
    a.write_text("\\label{eq:x}\n", encoding="utf-8")
    b.write_text("\\label{eq:x}\n", encoding="utf-8")
    root.write_text("\\input{a}\n\\input{b}\n", encoding="utf-8")
    rep = verify.check_crossref(str(root))
    assert "eq:x" in rep["duplicate_labels"]
    assert {"a.tex", "b.tex"} <= set(rep["duplicate_labels"]["eq:x"])


def test_crossref_ignores_commented_label(tmp_path):
    """A commented-out \\label must not satisfy a \\ref (comments are stripped)."""
    tex = tmp_path / "c.tex"
    tex.write_text("% \\label{eq:dead}\n\\ref{eq:dead}\n", encoding="utf-8")
    rep = verify.check_crossref(str(tex))
    assert any(b["ref"] == "eq:dead" for b in rep["broken_refs"])


def test_telemetry_merges_shards_chronologically(isolated_state):
    """events() merges every per-session shard and the legacy file, sorted by ts.

    The substrate is sharded per session so concurrent agents never interleave
    appends into one file; reads must still see one chronological record.
    """
    from laplace.engine import telemetry as tmod

    # This session's shard (via the normal API).
    tmod.log("orient", domain="web", offered=["w"])  # ts ~ now

    state = tmod.state_dir()
    # A second agent's shard, with an earlier event and a later one.
    other = state / "telemetry.deadbeefcafe.jsonl"
    other.write_text(
        json.dumps({"ts": "2000-01-01T00:00:00+00:00", "session": "deadbeefcafe",
                    "phase": "orient", "offered": ["early"]}) + "\n"
        + json.dumps({"ts": "2999-01-01T00:00:00+00:00", "session": "deadbeefcafe",
                      "phase": "orient", "offered": ["late"]}) + "\n",
        encoding="utf-8",
    )
    # A legacy single-file record (pre-sharding) must not be orphaned.
    (state / "telemetry.jsonl").write_text(
        json.dumps({"ts": "2010-01-01T00:00:00+00:00", "session": "legacy",
                    "phase": "orient", "offered": ["old"]}) + "\n",
        encoding="utf-8",
    )

    evs = tmod.events()
    sessions = [e["session"] for e in evs]
    assert {"deadbeefcafe", "legacy"} <= set(sessions)
    assert len(evs) >= 4
    # Chronological: the year-2000 event first, the year-2999 event last.
    ts = [e["ts"] for e in evs]
    assert ts == sorted(ts)
    assert evs[0]["offered"] == ["early"]
    assert evs[-1]["offered"] == ["late"]

    # since_session still isolates one agent's records across the merged read.
    only = tmod.events(since_session="deadbeefcafe")
    assert {e["session"] for e in only} == {"deadbeefcafe"}
    assert len(only) == 2


# ---------------------------------------------------------------------------
# Tier 2: the self-node fixture + the retention producer
# ---------------------------------------------------------------------------


def test_self_node_present_every_orient_fires_only_when_relevant():
    """engine/self is offered on every orient (present at every level) but the
    co-activation producer records it as firing only when a goal loads it - an
    inert conceptric fixture, not a constant that pollutes the statistics."""
    c = Canon.load()
    # Present at every level: a global top-level node, always in available_refs.
    b_neutral = c.orient("compile the latex and tabulate the equation numbers")
    assert "canon://engine/self" in b_neutral["available_refs"]
    # Not loaded with content for an unrelated goal -> does not co-activate.
    assert "canon://engine/self" not in telemetry.coactivation(b_neutral)

    # A taste/judgement/self goal matches it -> marked relevant -> it fires.
    b_self = c.orient(
        "improve the taste and judgement and microexpressions in the self, the soul"
    )
    assert "canon://engine/self" in telemetry.coactivation(b_self)


def test_self_node_is_wired_not_orphan():
    """The new self-node carries resolvable edges, so canon health still passes
    (no orphan, no dangling link) - the analyser's future graph includes it."""
    assert verify.check_canon(Canon.load())["pass"] is True


def test_retention_fate_maps_to_value_and_shape(isolated_state):
    kept = telemetry.retention("kept")
    assert kept["fate"] == "kept" and kept["value"] == 0.9
    assert "skill" not in kept  # skill-less by default

    rw = telemetry.retention(
        "rewritten", skill="manuscript_spine", nodes=["canon://a", "canon://b"],
        reason="reworked to the line", artifact="paper/main.tex",
    )
    assert rw["value"] == 0.6
    assert rw["skill"] == "manuscript_spine"
    assert rw["activated"] == ["canon://a", "canon://b"]
    assert rw["artifact"] == "paper/main.tex"

    assert telemetry.retention("bypassed")["value"] == 0.2

    with pytest.raises(ValueError):
        telemetry.retention("survived")  # not a known fate


def test_skill_less_retention_stays_off_the_fitness_gradient(isolated_state):
    """survived != earned, and we do not solder the signal in yet: a retention
    event with no skill is banked for the analyser but invisible to skill fitness;
    only a skill-named outcome reaches assess."""
    telemetry.retention("kept")  # no skill - banked, off the gradient
    telemetry.retention("rewritten", skill="manuscript_spine")  # named -> assess sees it

    evs = telemetry.events()
    sig = assess._skill_signals("manuscript_spine", evs)
    assert sig["retention_obs"] == [0.6]  # only the named one
    other = assess._skill_signals("latex_forge", evs)
    assert other["retention_obs"] == []  # the skill-less event reaches no skill


# ---------------------------------------------------------------------------
# corpus_stats — the regrade watch (/corpus/grade_stats)
# ---------------------------------------------------------------------------


def test_corpus_stats_grade_stats_shape_on_real_corpus():
    """The regrade endpoint measures the real corpus with no embedding call: per-node
    size/degree rows, a log-binned histogram, the grade-proxy ladder, and both outlier
    lists — the JSON a stranger (or the regrade tab) can act on without the network."""
    import laplace.research.corpus_stats as corpus_stats

    out = corpus_stats.handle(
        "/corpus/grade_stats", {"corpus": ["subset-sum-itqde"]}, "subset-sum-itqde")
    assert out is not None
    status, ctype, body = out
    assert status == 200
    assert ctype.startswith("application/json")
    d = json.loads(body)
    assert d["corpus"] == "subset-sum-itqde"
    assert d["n_nodes"] > 0
    assert d["n_live"] + d["n_retired"] == d["n_nodes"]
    row = d["nodes"][0]
    assert {"id", "kind", "chars", "words", "degree", "grade_proxy", "retired"} <= set(row)
    bins = d["histogram"]["bins"]
    assert bins and all(b["lo"] < b["hi"] for b in bins)          # log-spaced, well-ordered
    assert sum(b["count"] for b in bins) == d["n_live"]           # every live node lands in a bin
    # outlier lists exist and flag only LIVE nodes
    assert isinstance(d["outliers"]["split_candidates"], list)
    assert isinstance(d["outliers"]["content_free"], list)
    assert d["outliers"]["split_candidates"], "a real corpus has largest nodes"
    assert all(not r["retired"]
               for r in d["outliers"]["split_candidates"] + d["outliers"]["content_free"])
    assert all(r["kind"] not in ("support", "citation", "goal")
               for r in d["outliers"]["content_free"])


def test_corpus_stats_grade_ladder_is_watched_not_fitted():
    """The ladder is the power-law WATCH: four proxy grades (spine beats outward),
    every grade populated on a connected corpus, counts summing to the live total, and
    a raw ratio sequence — reported, never fitted (no exponent anywhere in the JSON)."""
    import laplace.research.corpus_stats as corpus_stats

    _, _, body = corpus_stats.handle(
        "/corpus/grade_stats", {"corpus": ["subset-sum-itqde"]}, "subset-sum-itqde")
    d = json.loads(body)
    grades = d["grades"]
    assert [g["grade"] for g in grades] == [0, 1, 2, 3]
    assert all(g["count"] >= 1 for g in grades)                    # every rung populated
    assert sum(g["count"] for g in grades) == d["n_live"]
    assert grades[0]["count"] <= d["n_beats"]                      # g0 = (live) spine beats
    for g in grades:                                               # size stats ride each rung
        assert g["mean_chars"] is not None and g["median_chars"] is not None
    ratios = d["count_ratios"]
    assert len(ratios) == 3
    assert all(r is None or r > 0 for r in ratios)
    assert "watched" in d["watch"] and "exponent" not in json.dumps(grades)


def test_corpus_stats_handle_falls_through_and_404s():
    """Not-our-path returns None (the orchestrator's dispatch falls through); an
    unregistered corpus is a 404 with a why, never an invented network."""
    import laplace.research.corpus_stats as corpus_stats

    assert corpus_stats.handle("/corpus/meta", {}, "subset-sum-itqde") is None
    status, ctype, body = corpus_stats.handle(
        "/corpus/grade_stats", {}, "this-corpus-does-not-exist")
    assert status == 404
    assert "unknown corpus" in json.loads(body)["error"]


# ---------------------------------------------------------------------------
# projection viewer - the artefact + provenance surface (/projection*)
# ---------------------------------------------------------------------------

_PV_FIXTURE = "tests/fixtures/pv_map_fixture.tex"


def test_projection_viewer_map_parses_plan_and_nodes_markers():
    """The projector's % PLAN / % NODES comments parse into ordered spans:
    an adjacent PLAN+NODES pair merges into ONE span running to the next marker,
    carrying the section tag and the source-node ids. (Committed two-span
    fixture: live fragments carry one marker pair each, so the multi-span
    tiling needs its own artifact.)"""
    import laplace.manuscript.projection_viewer as pv

    status, ctype, body = pv.handle("/projection/map", {"file": [_PV_FIXTURE]}, "GET", b"")
    assert status == 200 and "json" in ctype
    spans = json.loads(body)
    assert [s["section"] for s in spans] == ["S1", "S2"]
    assert spans[0]["nodes"] == ["goal:perturbation-assisted-itqde"]
    assert spans[1]["nodes"] == ["thm:staircase-cumulant-identities"]
    # spans tile forward: each starts at its marker, runs to the next marker / EOF
    assert spans[0]["start_line"] < spans[0]["end_line"] < spans[1]["start_line"]
    assert spans[1]["end_line"] > spans[1]["start_line"]


def test_projection_viewer_tex_roundtrip_under_repo(tmp_path, monkeypatch):
    """POST writes UTF-8 under the repo; GET returns the exact bytes back."""
    import laplace.manuscript.projection_viewer as pv
    from laplace.web.scanner import _repo_root

    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    rel = "_pv_roundtrip.tex"
    text = "% PLAN:S9\n% NODES: res:window-verdict\nOne sentence — with unicode.\n"
    target = tmp_path / rel
    target.write_bytes(b"old")
    guard = pv._source_observation(target)["expected_source_digest"]
    try:
        status, _, body = pv.handle("/projection/tex", {"file": [rel], "expected_source_digest": [guard]}, "POST",
                                    text.encode("utf-8"))
        assert status == 200 and json.loads(body)["ok"] is True
        status, ctype, body = pv.handle("/projection/tex", {"file": [rel]}, "GET", b"")
        assert status == 200 and body.decode("utf-8") == text
        # and the map endpoint sees the marker pair as one span
        status, _, body = pv.handle("/projection/map", {"file": [rel]}, "GET", b"")
        spans = json.loads(body)
        assert len(spans) == 1 and spans[0]["section"] == "S9"
        assert spans[0]["nodes"] == ["res:window-verdict"]
    finally:
        target.unlink(missing_ok=True)


def test_projection_viewer_rejects_path_traversal():
    """file= is fenced to the repo root: .. traversal and outside absolutes are 403,
    for reads, writes, and compiles alike."""
    import laplace.manuscript.projection_viewer as pv

    for bad in ["../secrets.txt",
                "synthetics papers/../../outside.tex",
                "C:/Windows/win.ini"]:
        status, _, _ = pv.handle("/projection/tex", {"file": [bad]}, "GET", b"")
        assert status == 403, bad
        status, _, _ = pv.handle("/projection/tex", {"file": [bad]}, "POST", b"x")
        assert status == 403, bad
        status, _, body = pv.handle("/projection/pdf", {"file": [bad]}, "GET", b"")
        assert status == 403, bad
    res = pv.compile_tex("../outside.tex")
    assert res["ok"] is False and res["pdf"] is None


def test_default_corpus_never_hardcodes(monkeypatch, tmp_path):
    """The law-of-laws leak (his, 2026-07-03): no view defaults to a hardcoded
    corpus. Priority: LAPLACE_ACTIVE_PROJECT env (if registered) > the corpus
    whose friction ledger moved last > the first registered corpus.

    Every candidate name comes from the ROSTER of the root being resolved, so the
    fixture declares that root's registry rows. This test read the first key of a
    hardcoded corpus dict until 2026-08-04; the dict is retired and there is no
    magic name left to leak."""
    import json
    import os
    import time
    from laplace.research import corpus_ingest as ci

    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [
        {"name": n, "kind": "conceptric",
         "tex_root": f"synthetics papers/{n}/manuscript"}
        for n in ("law-of-laws", "cost-of-complexity")]}), encoding="utf-8")

    monkeypatch.setenv("LAPLACE_ACTIVE_PROJECT", "cost-of-complexity")
    assert ci.default_corpus(tmp_path) == "cost-of-complexity"
    monkeypatch.setenv("LAPLACE_ACTIVE_PROJECT", "not-a-corpus")
    # no ledgers under tmp_path -> the first registered corpus, not a magic name
    assert ci.default_corpus(tmp_path) == "law-of-laws"
    assert ci.default_corpus(tmp_path) == ci.registered_corpora(tmp_path)[0]
    # the newest friction ledger wins
    fr = tmp_path / "corpus_friction"
    fr.mkdir()
    (fr / "law-of-laws.jsonl").write_text("{}\n", encoding="utf-8")
    time.sleep(0.01)
    (fr / "cost-of-complexity.jsonl").write_text("{}\n", encoding="utf-8")
    now = time.time()
    os.utime(fr / "law-of-laws.jsonl", (now - 100, now - 100))
    os.utime(fr / "cost-of-complexity.jsonl", (now, now))
    assert ci.default_corpus(tmp_path) == "cost-of-complexity"


def test_projection_viewer_doc_model_walks_the_paper():
    """/projection/doc on the whitepaper root returns every \\input fragment in
    document order (root first); opened on a FRAGMENT it resolves up to the same
    root, so the multi-file editor sees the whole paper from any entry point."""
    import laplace.manuscript.projection_viewer as pv

    root = "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"
    status, ctype, body = pv.handle("/projection/doc", {"file": [root]}, "GET", b"")
    assert status == 200 and "json" in ctype
    model = json.loads(body)
    assert model["root"].endswith("whitepaper/main.tex")
    names = [f["name"] for f in model["files"]]
    assert names[0] == "main"
    # Track the paper's REAL \input order rather than hardcoding a structure that goes
    # stale the moment the paper is reprojected (his 2026-07-03: don't let it go stale).
    import re as _re
    main_src = (pv._repo_root() / root).read_text(encoding="utf-8")
    expected = _re.findall(r"\\input\{([^}]+)\}", main_src)
    assert expected, "main.tex should \\input its fragments"
    assert names[1:] == expected
    assert all(f["exists"] for f in model["files"])

    # entered through a fragment: same root, same file list
    frag = "synthetics papers/subset-sum-itqde/manuscript/whitepaper/N3.tex"
    status, _, body = pv.handle("/projection/doc", {"file": [frag]}, "GET", b"")
    assert status == 200
    assert json.loads(body) == model

    # fenced like every other endpoint
    status, _, _ = pv.handle("/projection/doc", {"file": ["../outside.tex"]}, "GET", b"")
    assert status == 403


def test_projection_viewer_residue_is_the_complement():
    """/projection/residue = live corpus nodes no NODES marker in the paper cites.
    Mentioned + residue partition the live non-citation set; citation nodes are
    excluded (their coverage proof is the armed \\cite citations gate); retired
    nodes and structural anchors never appear."""
    import laplace.manuscript.projection_viewer as pv

    root = "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"
    status, _, body = pv.handle(
        "/projection/residue", {"file": [root], "corpus": ["subset-sum-itqde"]}, "GET", b"")
    assert status == 200
    d = json.loads(body)
    assert d["n_residue"] > 0 and d["n_live"] > d["n_residue"]
    assert d["n_citations_excluded"] > 0
    ids = {r["id"] for rows in d["by_kind"].values() for r in rows}
    assert not any(i.startswith("paper://") for i in ids)
    assert "citation" not in d["by_kind"]
    # a node the whitepaper visibly projects is NOT in the complement
    assert "res:window-verdict" not in ids
    # fenced + unknown-corpus honesty
    status, _, _ = pv.handle("/projection/residue",
                             {"file": ["../x.tex"], "corpus": ["subset-sum-itqde"]}, "GET", b"")
    assert status == 403
    status, _, body = pv.handle("/projection/residue",
                                {"file": [root], "corpus": ["nope"]}, "GET", b"")
    assert status == 404 and "unknown corpus" in json.loads(body)["error"]


def test_projection_viewer_synctex_anchor_resolves_to_span():
    """The review mode's anchor chain: (page, x, y) -> synctex -> fragment+line ->
    the provenance span -> section + nodes. Runs against the compiled whitepaper
    (main.synctex.gz rides the compile)."""
    import laplace.manuscript.projection_viewer as pv
    from laplace.web.scanner import _repo_root

    root = "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"
    if not (_repo_root() / root).with_suffix(".synctex.gz").with_name("main.synctex.gz").is_file():
        import pytest
        pytest.skip("no synctex sidecar - compile first")
    out = pv.synctex_anchor(root, 3, 300.0, 400.0)
    assert "error" not in out, out
    assert out["file"].endswith(".tex") and out["line"] > 0
    assert out["section"].startswith("N")     # the live arc: N1..N8 + NA1..NA3
    assert isinstance(out["nodes"], list)


def test_projection_viewer_feedback_ledger_roundtrip(tmp_path):
    """Comments bank to feedback/feedback.jsonl beside the compile root through
    the ONE bridge mechanism (explicit-ledger reuse): add -> list -> resolve."""
    import laplace.manuscript.manuscript_bridge as mb
    from laplace.web.scanner import _repo_root

    ledger = tmp_path / "feedback" / "feedback.jsonl"
    rec = mb.feedback_add(_repo_root(), "subset-sum-itqde",
                          {"node_id": "res:window-verdict", "comment": "test comment",
                           "kind": "off-voice",
                           "anchor": {"page": 3, "x": 300.0, "y": 400.0,
                                      "section": "S2", "nodes": ["res:window-verdict"]}},
                          ledger=ledger)
    assert rec.get("ok") is True and ledger.is_file()
    lst = mb.feedback_list(_repo_root(), "subset-sum-itqde", ledger=ledger)
    assert lst["n"] == 1 and lst["open"] == 1
    assert lst["records"][0]["anchor"]["section"] == "S2"
    out = mb.feedback_resolve(_repo_root(), "subset-sum-itqde",
                              lst["records"][0]["id"], ledger=ledger)
    assert out["ok"] is True
    assert mb.feedback_list(_repo_root(), "subset-sum-itqde", ledger=ledger)["open"] == 0


def test_projection_viewer_page_route_is_retired():
    """W4.3: the PNG raster serving routes (/projection/page, /projection/pages) are
    RETIRED to 410 — the viewer renders the pdf in-browser with pdf.js, so there is no
    page-image route to fence. The retirement answers regardless of the (now ignored)
    file= param, and names the surviving pdf routes."""
    import json as _json
    import laplace.manuscript.projection_viewer as pv

    for route in ("/projection/page", "/projection/pages"):
        for probe in ["src/laplace/web/scanner.py",
                      "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.pdf",
                      "../outside.png", ""]:
            status, _, body = pv.handle(route, {"file": [probe]}, "GET", b"")
            assert status == 410, (route, probe)
            payload = _json.loads(body)
            assert payload["retired"] == "W4.3"
            assert "pdf.js" in payload["reason"]
            assert "/projection/pdf" in payload["use"]


def test_projection_viewer_resolve_root_prefers_documentclass(tmp_path):
    """resolve_root: a fragment maps to the sibling \\documentclass file that
    \\inputs it; a standalone file (no root claims it) maps to itself."""
    import laplace.manuscript.projection_viewer as pv

    (tmp_path / "paper.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n\\input{S1}\n"
        "\\input{sub/S2.tex}\n\\end{document}\n", encoding="utf-8")
    (tmp_path / "S1.tex").write_text("one fragment\n", encoding="utf-8")
    (tmp_path / "loose.tex").write_text("nobody inputs this\n", encoding="utf-8")
    assert pv.resolve_root(tmp_path / "S1.tex") == tmp_path / "paper.tex"
    assert pv.resolve_root(tmp_path / "paper.tex") == tmp_path / "paper.tex"
    assert pv.resolve_root(tmp_path / "loose.tex") == tmp_path / "loose.tex"
    # the \input list resolves TeX-style: suffixless gets .tex, subdirs ride through
    names = pv._input_names((tmp_path / "paper.tex").read_text(encoding="utf-8"))
    assert [pv._frag_path(tmp_path, n).name for n in names] == ["S1.tex", "S2.tex"]


def test_projection_viewer_node_fetch_shape_on_subset_sum_itqde():
    """/projection/node resolves through the ONE corpus mechanism (corpus_network,
    overlay applied, never embedding): res:window-verdict comes back with the
    essence/kind/projection/retired shape the provenance rail renders."""
    import laplace.manuscript.projection_viewer as pv

    status, ctype, body = pv.handle(
        "/projection/node",
        {"id": ["res:window-verdict"], "corpus": ["subset-sum-itqde"]}, "GET", b"")
    assert status == 200 and "json" in ctype
    d = json.loads(body)
    assert d["id"] == "res:window-verdict"
    assert d["kind"] == "result"
    assert d["essence"]                                   # non-empty provenance text
    assert isinstance(d["projection"], dict)
    assert d["retired"] is False and d["sealed"] is False
    # unknown node -> 404 with a why, never an invented brief
    status, _, body = pv.handle(
        "/projection/node",
        {"id": ["res:does-not-exist"], "corpus": ["subset-sum-itqde"]}, "GET", b"")
    assert status == 404 and "error" in json.loads(body)
    # not-our-path falls through as None so the scanner keeps routing
    assert pv.handle("/corpus/meta", {}, "GET", b"") is None


# ---------------------------------------------------------------------------
# shared_ui - the hymn sheet: shared assets + the plan endpoint
# ---------------------------------------------------------------------------


def test_shared_ui_assets_served_with_canonical_palette():
    """The three shared assets serve with the right content types, and hymn.css
    carries the canonical custom properties (the one source of truth the six
    applets' local fallbacks defer to)."""
    from laplace.web import shared_ui

    for name, expect in (("hymn.css", "text/css"),
                         ("shell.js", "text/javascript"),
                         ("inspector.js", "text/javascript")):
        status, ctype, body = shared_ui.handle(f"/shared/{name}", {})
        assert status == 200, name
        assert ctype.startswith(expect), name
        assert len(body) > 500, name
    css = shared_ui.handle("/shared/hymn.css", {})[2].decode("utf-8")
    for var in ("--bg:", "--accent:", "--keystone:", "#hy-shell", ".hy-ins"):
        assert var in css
    # not-our-path falls through as None so the scanner keeps routing
    assert shared_ui.handle("/corpus/meta", {}) is None


def test_shared_ui_plan_endpoint_on_subset_sum_itqde():
    """/shared/plan?corpus=subset-sum-itqde returns the projection plan with the
    derived node->section index the cross-links ('show in projection') use."""
    from laplace.web import shared_ui

    status, ctype, body = shared_ui.handle(
        "/shared/plan", {"corpus": ["subset-sum-itqde"]})
    assert status == 200 and "json" in ctype
    d = json.loads(body)
    assert d["corpus"] == "subset-sum-itqde"
    assert d["target_dir"].rstrip("/").endswith("whitepaper")
    assert d["sections"] and d["sections"][0]["id"] == "N1"
    # structural, not positional: the index routes a planned node to a section that exists
    # in this plan and carries its title. Which section holds it is PROJECT data (it moved
    # S1->S5 in the 2026-07-08 general-first restructure); pinning it here recalcifies.
    hit = d["node_index"]["goal:perturbation-assisted-itqde"]
    section_ids = {s["id"] for s in d["sections"]} | {a["id"] for a in d.get("appendices", [])}
    assert hit["section"] in section_ids and hit["title"]
    # a corpus= is required; a missing one is a 400, not a guess
    status, _, body = shared_ui.handle("/shared/plan", {})
    assert status == 400 and "error" in json.loads(body)


def test_shared_ui_plan_meta_whitelist_carries_contribution_rank_when_present():
    """The board-render meta whitelist (project/artefact/form/target_dir) grows a
    FIFTH key, additively, when the plan carries meta.contribution_rank - the ONE
    authored judgement the return path pivots on (his return-path push,
    2026-07-13). Present, ONE decode deep (schema.contribution_rank_lines via
    shared_ui.board_contribution_rank), on subset-sum-itqde's real 4-entry rank
    (3 primary + 1 excluded). paper_falqon now carries the 2026-07-22 respine's
    ratified {value, projection_ruling}-wrapped rank, which the ONE decode unwraps
    to its value list — so its rank is present too (the whole point of the
    reader-shape fix: the wrapped thesis is visible to the board, not swallowed by
    the envelope)."""
    from laplace.web import shared_ui

    status, _, body = shared_ui.handle(
        "/shared/plan", {"corpus": ["subset-sum-itqde"]})
    d = json.loads(body)
    assert set(d["meta"]) == {"project", "artefact", "form", "target_dir", "contribution_rank"}
    rank = d["meta"]["contribution_rank"]
    assert len(rank["primary"]) == 3 and len(rank["excluded"]) == 1
    assert "excluded" in rank["excluded"][0]   # the excluded entry is marked, not just dropped

    # paper_falqon: the respine-WRAPPED rank is unwrapped by the ONE decode, so the
    # board carries it (was a stale "4-key floor" assertion written when the plan
    # had no rank; the ratified respine + the reader-shape fix make it present).
    status, _, body = shared_ui.handle("/shared/plan", {"corpus": ["paper_falqon"]})
    d = json.loads(body)
    assert set(d["meta"]) == {"project", "artefact", "form", "target_dir", "contribution_rank"}
    assert d["meta"]["contribution_rank"]["primary"]   # the thesis + derivations render


def test_shared_ui_traversal_rejected():
    """Traversal shapes never reach the filesystem: assets resolve by ALLOWLIST
    (unknown names 404 before any path math) and plan corpora resolve through
    the project registry (unknown names 404)."""
    from laplace.web import shared_ui

    for bad in ("../scanner.py", "..%2Fscanner.py", "hymn.css/../scanner.py",
                r"..\..\pyproject.toml", "canon/wiki.md"):
        status, _, body = shared_ui.handle("/shared/" + bad, {})
        assert status == 404, bad
        assert "error" in json.loads(body), bad
    for bad in ("../../etc", r"..\..\soul", "law-of-laws/../../soul"):
        status, _, body = shared_ui.handle("/shared/plan", {"corpus": [bad]})
        assert status == 404, bad
        assert "error" in json.loads(body), bad


def test_shared_ui_plan_unknown_corpus_is_404():
    """A registered-corpus miss (or a corpus without a plan on disk) answers 404
    with a why - never an invented plan."""
    from laplace.web import shared_ui

    status, _, body = shared_ui.handle("/shared/plan", {"corpus": ["no-such-corpus"]})
    assert status == 404 and "error" in json.loads(body)


# ---------------------------------------------------------------------------
# shared_ui - THE ONE AUTHORED VIEW-ROSTER (W0.1)
# ---------------------------------------------------------------------------


def test_shared_ui_views_roster_is_the_one_authored_source():
    """GET /shared/views returns the ONE authored roster: every row typed
    (id/title/path/purpose/group), every live surface present, every retired-in-W0.3
    view absent - so the shell can render its nav from one place."""
    from laplace.web import shared_ui

    status, ctype, body = shared_ui.handle("/shared/views", {})
    assert status == 200 and "json" in ctype
    roster = json.loads(body)["views"]
    assert roster, "the roster is not empty"

    for v in roster:
        assert set(v) >= {"id", "title", "path", "purpose", "group"}, v
        assert v["id"] and v["title"] and v["purpose"], v
        assert v["path"].startswith("/"), v
        assert v["group"] in ("primary", "more"), v

    ids = [v["id"] for v in roster]
    assert len(ids) == len(set(ids)), "view ids are unique"
    paths = [v["path"] for v in roster]
    assert len(paths) == len(set(paths)), "view paths are unique"

    # every live surface appears; the conceptric surface is at /conceptric (W3 rename); the
    # dashboard is home at "/" (W1). ACT5 ruling (shared_ui.py _VIEWS, 2026-07-21): the
    # brain-scanner MAP ROW is removed from the roster entirely — it is a view of the ENGINE,
    # not of a project's work, so it doesn't belong in the nav (not even behind "More"); the
    # /map ROUTE keeps serving a typed URL (that live door is proven in test_w1_4_landing).
    by_id = {v["id"]: v for v in roster}
    # W2: projection + review CONSOLIDATED into the ONE artefact surface (conception §2).
    # W5: the /guide explainer + /tutorial page DIED; THE DESK COCKPIT joins at /desk. (W-guide
    # 2026-07-22 later re-added a /guide STRUCTURAL guide surface — distinct from the dead explainer.)
    # W6: /dials FOLDED into /pipeline (his ruling: "dials are useful but they need to be
    # integrated into the pipeline") — pipeline is the roster row now, dials is gone.
    for want in ("conceptric", "storyboard", "artefact",
                 "desk", "pipeline", "analytics", "altitude"):
        assert want in by_id, want
    for gone_view in ("tutorial",):
        assert gone_view not in by_id, f"{gone_view} died in W5 — it must be off the roster"
    assert "map" not in by_id, "the map ROW was ruled off the roster (ACT5) — nav is projects, not the engine"
    assert "dials" not in by_id, "dials folded into pipeline in W6 — it must be off the roster"
    assert by_id["conceptric"]["path"] == "/conceptric"   # W3: /conceptric2 -> /conceptric
    assert by_id["artefact"]["path"] == "/artefact"
    assert by_id["desk"]["path"] == "/desk"
    assert by_id["pipeline"]["path"] == "/pipeline"

    # the surfaces retired in W0.3 (+ the W3-inverted /conceptric2) are NOT in the roster (no
    # dead/retired doors); W2 folds projection + review into artefact, so their ids/paths are
    # no longer nav destinations.
    for gone in ("/navigator", "/conceptric2", "/editor"):
        assert gone not in paths, gone
    for gone_id in ("navigator", "editor", "projection", "review"):
        assert gone_id not in by_id, gone_id

    # a fresh copy each call - no caller can mutate the source of truth
    roster[0]["id"] = "MUTATED"
    assert json.loads(shared_ui.handle("/shared/views", {})[2])["views"][0]["id"] != "MUTATED"


def test_shell_nav_consumes_the_roster_not_a_hardcoded_list():
    """The single-source contract, grep-level: the shell fetches /shared/views
    and carries NO hardcoded view roster (a `const VIEWS = [...]` literal), so the
    server-side roster is the one place the nav is declared."""
    from pathlib import Path

    from laplace.web import shared_ui

    shell = (Path(shared_ui.__file__).resolve().parent
             / "static_shared" / "shell.js").read_text(encoding="utf-8")
    assert 'fetch("/shared/views")' in shell, "shell must fetch the authored roster"
    assert "const VIEWS = [" not in shell, "no hardcoded roster literal survives"
    # the retired routes must not linger as nav literals in the shell either
    assert '"/navigator"' not in shell


def test_no_second_source_nav_in_templates_or_served_data():
    """THE CLASS, fail-closed: the shell nav (shell.js, fed by /shared/views) is the
    ONE cross-surface nav. Extend the single-source contract beyond shell.js — scan
    EVERY served template (src/laplace/*.html) for:
      (a) a BARE nav link to a roster surface outside the shell (the second-source
          disease — a hardcoded href="/dials" that drifts when the roster changes);
          a roster path carrying a query or sub-path (/storyboard?corpus=,
          /projection/pdf?file=) is a legitimate functional deep-link, not a nav dup;
      (b) any href to a path retired in W0.3 + W3 (/navigator, /editor, /conceptric2).
    (W5: the guide STAGES served-hrefs check retired with the /guide explainer; the
    desk's own deep-links are proven route-live in test_guide.py.)
    """
    from pathlib import Path

    from laplace.web import shared_ui

    tpl_dir = Path(shared_ui.__file__).resolve().parent
    templates = sorted(tpl_dir.glob("*.html"))
    assert templates, "no served templates found to scan"
    roster = {v["path"] for v in shared_ui._VIEWS}
    # W3: /conceptric is now the LIVE surface (so /conceptric2 is retired, not /conceptric).
    # W6: /dials folded into /pipeline — the standalone view died (dials.html deleted, the
    # bare route 301s), so a template hardcoding href="/dials" is now a second-source-nav
    # violation the SAME as a stale /navigator link, not merely a missing roster row.
    retired = ("/navigator", "/editor", "/conceptric2", "/dials")

    def bare_roster_link(text: str) -> list[str]:
        # a BARE href to a roster surface: the path is immediately closed by the
        # quote (no ?query, no /sub-path). href="/dials" hits; href="/storyboard?…"
        # and href="/projection/pdf…" do not.
        return [p for p in roster
                if f'href="{p}"' in text or f"href='{p}'" in text]

    def retired_link(text: str) -> list[str]:
        hits = []
        for tok in retired:
            # the closing delimiter keeps the live /conceptric from matching retired /conceptric2
            for pat in (f'"{tok}"', f"'{tok}'", f'href="{tok}"', f"href='{tok}'"):
                if pat in text:
                    hits.append(tok)
        return hits

    offenders_a, offenders_b = [], []
    for f in templates:
        text = f.read_text(encoding="utf-8", errors="replace")
        offenders_a += [(f.name, p) for p in bare_roster_link(text)]
        offenders_b += [(f.name, t) for t in retired_link(text)]

    assert not offenders_a, f"template hardcodes a roster-surface nav link (second source): {offenders_a}"
    assert not offenders_b, f"a served surface/data payload links a retired path: {offenders_b}"

    # fail-closed self-checks: both detectors fire on a planted violation…
    assert bare_roster_link('<a href="/pipeline">pipeline</a>'), "bare-roster detector is blind"
    assert retired_link('<a href="/navigator">nav</a>'), "retired-link detector is blind"
    assert retired_link('<a href="/dials">dials</a>'), \
        "retired-link detector is blind to the W6-folded /dials"
    # …and neither false-positives on the legitimate shapes
    assert not bare_roster_link('a.href="/storyboard?corpus="+c')
    assert not bare_roster_link('a.href="/projection/pdf?file="+f')
    assert not retired_link('href="/conceptric"')   # the live successor is never flagged retired
    # the wire endpoints /dials/op·/dials/state·/dials/undo stay live (W6: only the bare
    # standalone PAGE folded into /pipeline) — a sub-path fetch must never be flagged retired.
    assert not retired_link('store.fetchJSON("/dials/op", {method:"POST"})')
    assert not retired_link('store.fetchJSON("/dials/undo", {method:"POST"})')
