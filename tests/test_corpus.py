"""Unit tests for the exogenous-substrate ware: the global corpus store, its
conceptric projection (``CanonGraph.from_corpus``), and the corpus_librarian
backing scripts (check / cluster_guide / ingest)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from laplace.pipeline.graph import CanonGraph, _parse_bib, render

pytestmark = pytest.mark.unit

_SKILLS = Path(__file__).resolve().parents[1] / "src" / "laplace" / "pipeline" / "canon" / "skills" / "corpus_librarian" / "scripts"
_REPO = Path(__file__).resolve().parents[1]


def _load(script: str):
    """Import a corpus_librarian backing script as a module by path."""
    path = _SKILLS / script
    spec = importlib.util.spec_from_file_location(f"_corpus_{script[:-3]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# A two-project fixture, so the cross-project coupling is exercised even though
# the live store carries one project. `shared2026key` is cited by BOTH projects.
TWO_PROJECT_BIB = textwrap.dedent(
    """\
    @article{alpha2020first,
      author = {Alpha, Ada}, title = {A first result}, year = {2020},
      tldr = {x}, claim = {Alpha holds.}, status = {established},
      cluster = {clusterA}, keywords = {k1},
      provenance = {project_one}, added = {2026-06-04}, scout = {eigen}}

    @article{beta2021bridge,
      author = {Beta, Ben}, title = {A bridging result}, year = {2021},
      tldr = {x}, claim = {Beta bridges.}, status = {borrowed},
      cluster = {clusterA, clusterB}, keywords = {k2},
      provenance = {project_one}, added = {2026-06-04}, scout = {eigen}}

    @article{shared2026key,
      author = {Gamma, Gail}, title = {The shared keystone}, year = {2026},
      tldr = {x}, claim = {Gamma is shared.}, status = {unverified},
      cluster = {clusterB}, keywords = {k3},
      provenance = {project_one, project_two}, added = {2026-06-04}, scout = {eigen}}

    @article{delta2019other,
      author = {Delta, Dee}, title = {A second-project result}, year = {2019},
      tldr = {x}, claim = {Delta stands alone.}, status = {provisional},
      cluster = {clusterC}, keywords = {k4},
      provenance = {project_two}, added = {2026-06-04}, scout = {eigen}}
    """
)


# --------------------------------------------------------------------------
# The committed seed store
# --------------------------------------------------------------------------
def test_seed_corpus_is_well_formed():
    """The committed corpus/corpus.bib passes the librarian's own validator."""
    check = _load("check_corpus.py")
    rc = check.check(str(_REPO / "corpus" / "corpus.bib"))
    assert rc == 0, "the seed corpus must be well-formed (check_corpus clean)"


def test_seed_keys_well_formed_and_refsbib_papers_converge():
    """Every seed citekey is on the deterministic pattern, and the papers that
    came from the project refs.bib reproduce their exact key - otherwise two
    projects ingesting the same paper would not converge on one record."""
    ingest = _load("ingest_refs.py")
    check = _load("check_corpus.py")
    seed_keys = {k for k, _ in _parse_bib((_REPO / "corpus" / "corpus.bib").read_text(encoding="utf-8"))}
    off_pattern = [k for k in seed_keys if not check.CITEKEY.match(k)]
    assert not off_pattern, f"seed keys off the deterministic pattern: {off_pattern}"
    # The refs.bib papers that are seeded must reproduce exactly (no divergent key).
    src = ingest.parse_records(ingest.read_safe(str(_REPO / "paper_operatorial_loss" / "manuscript" / "refs.bib")))
    regenerated = {ingest.citekey(f) for _k, _et, f in src}
    overlap = regenerated & seed_keys
    assert len(overlap) >= 20, f"refs.bib-sourced seed papers should converge; overlap={len(overlap)}"


def test_caron_author_folds_without_stray_letter():
    """A LaTeX caron author ({\\v Z}unkovi{\\v c}) must not glue a stray 'v'."""
    ingest = _load("ingest_refs.py")
    key = ingest.citekey({"author": "{\\v Z}unkovi{\\v c}, Bojan",
                          "title": "Grokking phase transitions", "year": "2024"})
    assert key == "zunkovic2024grokking"


# --------------------------------------------------------------------------
# from_corpus: the connector
# --------------------------------------------------------------------------
def test_from_corpus_seed_is_connected():
    g = CanonGraph.from_corpus(str(_REPO / "corpus" / "corpus.bib"))
    kinds = {n.kind for n in g.nodes.values()}
    assert {"reference", "cluster", "project"} <= kinds
    h = g.health()
    assert h["components"] == 1, "the seed corpus should be one connected component"
    assert not h["dangling"]
    assert not h["orphans"]


def test_from_corpus_computes_cross_cluster_coupling(tmp_path: Path):
    """A bridging reference (two clusters) induces a cluster<->cluster 'shares'
    edge, weighted by the shared references."""
    bib = tmp_path / "c.bib"
    bib.write_text(TWO_PROJECT_BIB, encoding="utf-8")
    g = CanonGraph.from_corpus(str(bib))
    shares = {(e.src, e.dst): e.count for e in g.edges if e.rel == "shares"}
    # beta2021bridge sits in clusterA AND clusterB -> they couple.
    assert ("cluster:clustera", "cluster:clusterb") in shares


def test_from_corpus_computes_cross_project_coupling(tmp_path: Path):
    """Two projects citing the same reference induce a project<->project 'shares'
    edge - the cross-project coupling the store exists to make visible."""
    bib = tmp_path / "c.bib"
    bib.write_text(TWO_PROJECT_BIB, encoding="utf-8")
    g = CanonGraph.from_corpus(str(bib))
    shares = {(e.src, e.dst) for e in g.edges if e.rel == "shares"}
    assert ("project:project_one", "project:project_two") in shares


def test_from_corpus_status_drives_link_state(tmp_path: Path):
    """Trust status maps to the learning-state link the frontier reads:
    unverified -> loose, established -> closed."""
    bib = tmp_path / "c.bib"
    bib.write_text(TWO_PROJECT_BIB, encoding="utf-8")
    g = CanonGraph.from_corpus(str(bib))
    assert g.nodes["ref:shared2026key"].link == "loose"      # unverified
    assert g.nodes["ref:alpha2020first"].link == "closed"    # established
    # the loose (untrusted) reference surfaces on the health frontier.
    assert "ref:shared2026key" in g.health()["frontier"]["loose"]


def test_render_corpus_source(tmp_path: Path):
    bib = tmp_path / "c.bib"
    bib.write_text(TWO_PROJECT_BIB, encoding="utf-8")
    res = render("json", corpus=str(bib))
    assert "error" not in res
    assert res["stats"]["nodes"] > 0


def test_render_corpus_missing_path():
    res = render("json", corpus="/no/such/corpus.bib")
    assert "error" in res


# --------------------------------------------------------------------------
# cluster_guide: the synthesis
# --------------------------------------------------------------------------
def test_cluster_guide_respects_trust_boundary(tmp_path: Path, capsys):
    guide = _load("cluster_guide.py")
    bib = tmp_path / "c.bib"
    bib.write_text(TWO_PROJECT_BIB, encoding="utf-8")
    rc = guide.guide(str(bib), "clusterA", project="project_one")
    out = capsys.readouterr().out
    assert rc == 0
    # alpha is established -> settled; beta is borrowed -> a candidate, never settled.
    assert "established: 1" in out
    assert "alpha2020first" in out
    # the novelty boundary names what project_one has not cited in the cluster.
    assert "Novelty boundary" in out


def test_cluster_guide_empty_cluster_is_a_finding(tmp_path: Path, capsys):
    guide = _load("cluster_guide.py")
    bib = tmp_path / "c.bib"
    bib.write_text(TWO_PROJECT_BIB, encoding="utf-8")
    rc = guide.guide(str(bib), "nonexistent_cluster")
    out = capsys.readouterr().out
    assert rc == 1
    assert "empty" in out.lower()


# --------------------------------------------------------------------------
# ingest_refs: the bulk builder
# --------------------------------------------------------------------------
def test_ingest_generates_records_without_fabricating_claims(tmp_path: Path):
    """Ingest converts a refs.bib into corpus records, stamping provenance and
    leaving the claim an explicit TODO - never invented."""
    ingest = _load("ingest_refs.py")
    src = tmp_path / "refs.bib"
    src.write_text(
        "@article{Foo2020Bar,\n author = {Foo, Fay}, title = {On the Bar mechanism},\n"
        " year = {2020}, doi = {10.1/x}}\n",
        encoding="utf-8",
    )
    target = tmp_path / "corpus.bib"
    rc = ingest.ingest(str(src), str(target), project="proj_x", scout="eigen",
                       dry_run=False, update_provenance=False)
    assert rc == 0
    text = target.read_text(encoding="utf-8")
    assert "@article{foo2020bar," in text          # deterministic key (stopword 'On' skipped)
    assert "TODO" in text                          # claim not fabricated
    assert "status     = {unverified}" in text
    assert "provenance = {proj_x}" in text


def test_ingest_dedupes_by_deterministic_key(tmp_path: Path):
    """Re-ingesting the same record adds nothing - two ingests converge."""
    ingest = _load("ingest_refs.py")
    src = tmp_path / "refs.bib"
    src.write_text(
        "@article{Foo2020Bar,\n author = {Foo, Fay}, title = {On the Bar mechanism}, year = {2020}}\n",
        encoding="utf-8",
    )
    target = tmp_path / "corpus.bib"
    ingest.ingest(str(src), str(target), "proj_x", "eigen", False, False)
    n_after_first = target.read_text(encoding="utf-8").count("@article")
    ingest.ingest(str(src), str(target), "proj_x", "eigen", False, False)
    n_after_second = target.read_text(encoding="utf-8").count("@article")
    assert n_after_first == n_after_second == 1


def test_ingested_corpus_is_parseable_by_the_conceptric(tmp_path: Path):
    """The store ingest writes must round-trip through from_corpus."""
    ingest = _load("ingest_refs.py")
    src = tmp_path / "refs.bib"
    src.write_text(
        "@article{Foo2020Bar,\n author = {Foo, Fay}, title = {On the Bar mechanism}, year = {2020}}\n",
        encoding="utf-8",
    )
    target = tmp_path / "corpus.bib"
    ingest.ingest(str(src), str(target), "proj_x", "eigen", False, False)
    g = CanonGraph.from_corpus(str(target))
    assert "ref:foo2020bar" in g.nodes
    assert g.nodes["ref:foo2020bar"].link == "loose"  # unverified ingest


# --------------------------------------------------------------------------
# v2: the conceptric hierarchy + typed semantic relations
# --------------------------------------------------------------------------
RELATIONS_BIB = textwrap.dedent(
    """\
    @article{alpha2020first,
      author = {Alpha, Ada}, title = {A first result}, year = {2020},
      tldr = {x}, claim = {Alpha holds.}, summary = {Alpha did a thing accurately.},
      status = {established}, cluster = {clusterA}, keywords = {k1},
      relations = {extends:beta2021bridge | alpha extends beta into a new regime},
      provenance = {project_one}, added = {2026-06-04}, scout = {eigen}}

    @article{beta2021bridge,
      author = {Beta, Ben}, title = {A bridging result}, year = {2021},
      tldr = {x}, claim = {Beta bridges.}, summary = {Beta bridged two ideas.},
      status = {borrowed}, cluster = {clusterA}, keywords = {k2},
      relations = {contests:nonexistent2099key | beta disputes a ghost},
      provenance = {project_one}, added = {2026-06-04}, scout = {eigen}}
    """
)


def test_from_corpus_builds_theme_hierarchy():
    """The seed corpus nests: theme -> cluster -> reference (a conceptric)."""
    g = CanonGraph.from_corpus(str(_REPO / "corpus" / "corpus.bib"))
    kinds = {n.kind for n in g.nodes.values()}
    assert "theme" in kinds and "cluster" in kinds
    # every cluster under a theme is reached by a theme 'contains' edge.
    theme_clusters = {e.dst for e in g.edges if e.rel == "contains" and e.src.startswith("theme:")}
    assert theme_clusters, "themes must contain clusters"
    # the author's lineage is its own top-level theme.
    assert any(n.kind == "theme" and "author" in n.label.lower() for n in g.nodes.values())


def test_from_corpus_projects_typed_semantic_relations(tmp_path: Path):
    bib = tmp_path / "c.bib"
    bib.write_text(RELATIONS_BIB, encoding="utf-8")
    g = CanonGraph.from_corpus(str(bib))
    extends = [e for e in g.edges if e.rel == "extends"]
    assert any(e.src == "ref:alpha2020first" and e.dst == "ref:beta2021bridge" for e in extends)
    # the description rides on the edge as evidence; rank rides in count.
    e = next(e for e in extends if e.src == "ref:alpha2020first")
    assert "new regime" in e.evidence and e.count == 1


def test_from_corpus_dangling_relation_is_visible(tmp_path: Path):
    """A relation to a key not in the store becomes a dangling edge, like a broken link."""
    bib = tmp_path / "c.bib"
    bib.write_text(RELATIONS_BIB, encoding="utf-8")
    g = CanonGraph.from_corpus(str(bib))
    dangling = [e for e in g.edges if e.rel == "dangling"]
    assert any(e.src == "ref:beta2021bridge" for e in dangling)


def test_author_corpus_bridges_to_project():
    """The author's closure paper carries both provenances, coupling the lineage
    project to the active project."""
    g = CanonGraph.from_corpus(str(_REPO / "corpus" / "corpus.bib"))
    pshares = {(e.src, e.dst) for e in g.edges if e.rel == "shares" and e.src.startswith("project:")}
    assert ("project:author_corpus", "project:paper_operatorial_loss") in pshares or \
           ("project:paper_operatorial_loss", "project:author_corpus") in pshares


# --------------------------------------------------------------------------
# check_corpus v2: relation + summary + cluster validation
# --------------------------------------------------------------------------
def test_check_corpus_requires_summary(tmp_path: Path):
    check = _load("check_corpus.py")
    bib = tmp_path / "c.bib"
    bib.write_text(
        "@article{foo2020bar,\n author = {Foo, F}, title = {T}, year = {2020},\n"
        " tldr = {x}, claim = {y}, status = {unverified}, added = {2026-06-04}, scout = {eigen}}\n",
        encoding="utf-8",
    )
    assert check.check(str(bib)) == 1  # missing summary -> incomplete -> fails


def test_check_corpus_flags_bad_relation(tmp_path: Path, capsys):
    check = _load("check_corpus.py")
    bib = tmp_path / "c.bib"
    bib.write_text(
        "@article{foo2020bar,\n author = {Foo, F}, title = {T}, year = {2020}, tldr = {x},\n"
        " claim = {y}, summary = {s}, status = {unverified}, added = {2026-06-04}, scout = {eigen},\n"
        " relations = {bogus_type:foo2020bar | self; extends:ghost2099none | dangling}}\n",
        encoding="utf-8",
    )
    rc = check.check(str(bib))
    out = capsys.readouterr().out
    assert rc == 1
    assert "unknown type" in out.lower()
    assert "not in the store" in out.lower()


# --------------------------------------------------------------------------
# citation discipline: the surfacing rule
# --------------------------------------------------------------------------
def test_citation_check_flags_naked_reliance(tmp_path: Path):
    from laplace.pipeline.verify import check_corpus_citations
    corpus = tmp_path / "corpus.bib"
    corpus.write_text(
        "@article{smith2020alpha,\n author = {Smith, S}, title = {Alpha}, year = {2020},\n"
        " note = {arXiv:2001.00001}, tldr = {x}, claim = {c}, summary = {s},\n"
        " status = {borrowed}, cluster = {k}, provenance = {proj}, added = {2026-06-04}, scout = {eigen}}\n"
        "@article{jones2021beta,\n author = {Jones, J}, title = {Beta}, year = {2021},\n"
        " note = {arXiv:2101.00002}, tldr = {x}, claim = {c}, summary = {s},\n"
        " status = {borrowed}, cluster = {k}, provenance = {proj}, added = {2026-06-04}, scout = {eigen}}\n",
        encoding="utf-8",
    )
    man = tmp_path / "paper"
    man.mkdir()
    (man / "refs.bib").write_text(
        "@article{Smith2020,\n author={Smith, S}, title={Alpha}, year={2020}, note={arXiv:2001.00001}}\n"
        "@article{Jones2021,\n author={Jones, J}, title={Beta}, year={2021}, note={arXiv:2101.00002}}\n",
        encoding="utf-8",
    )
    # The manuscript cites Smith (by its refs.bib key) but relies on Jones uncited.
    (man / "main.tex").write_text(
        "\\section{Intro}\nWe build on \\cite{Smith2020} but lean on Jones silently.\n",
        encoding="utf-8",
    )
    r = check_corpus_citations(str(man / "main.tex"), str(corpus), "proj")
    assert r["relied_on"] == 2
    assert r["surfaced"] == 1
    assert r["pass"] is False
    assert {n["ref"] for n in r["naked_reliances"]} == {"jones2021beta"}


def test_citation_check_passes_when_all_surfaced(tmp_path: Path):
    from laplace.pipeline.verify import check_corpus_citations
    corpus = tmp_path / "corpus.bib"
    corpus.write_text(
        "@article{smith2020alpha,\n author = {Smith, S}, title = {Alpha}, year = {2020},\n"
        " note = {arXiv:2001.00001}, tldr = {x}, claim = {c}, summary = {s},\n"
        " status = {borrowed}, cluster = {k}, provenance = {proj}, added = {2026-06-04}, scout = {eigen}}\n",
        encoding="utf-8",
    )
    man = tmp_path / "paper"
    man.mkdir()
    (man / "refs.bib").write_text(
        "@article{Smith2020,\n author={Smith, S}, title={Alpha}, year={2020}, note={arXiv:2001.00001}}\n",
        encoding="utf-8",
    )
    (man / "main.tex").write_text("We build on \\cite{Smith2020}.\n", encoding="utf-8")
    r = check_corpus_citations(str(man / "main.tex"), str(corpus), "proj")
    assert r["pass"] is True and r["surfaced"] == 1


# --------------------------------------------------------------------------
# the corpus-citation gate rides in the DEFAULT verify run (R2)
# --------------------------------------------------------------------------
def test_citations_in_default_checks():
    # The gate is in the default path, not an opt-in a generating agent must remember.
    from laplace.pipeline import verify as _v
    assert "citations" in _v.DEFAULT_CHECKS


def test_default_verify_does_not_redflag_non_citing_artefact(tmp_path: Path):
    # With citations in DEFAULT_CHECKS but no corpus/project, the gate is manual
    # (pass=None) and must NOT fail an artefact that simply does not cite the corpus.
    from laplace.pipeline import verify as _v
    tex = tmp_path / "clean.tex"
    tex.write_text(
        r"\section{Intro}\begin{equation}\label{eq:a} x=1 \end{equation} see \ref{eq:a}." + "\n",
        encoding="utf-8",
    )
    rep = _v.verify(str(tex))  # default checks
    assert rep["checks"]["citations"]["pass"] is None
    assert rep["checks"]["citations"].get("manual") is True
    assert rep["passed"] is True  # the manual citation verdict is excluded from pass


def test_default_verify_enforces_citations_when_corpus_supplied(tmp_path: Path):
    # When corpus+project ARE supplied, the default run enforces and fails on a
    # naked reliance — the generation-time gate is armed without naming the check.
    from laplace.pipeline import verify as _v
    corpus = tmp_path / "corpus.bib"
    corpus.write_text(
        "@article{jones2021beta,\n author = {Jones, J}, title = {Beta}, year = {2021},\n"
        " note = {arXiv:2101.00002}, tldr = {x}, claim = {c}, summary = {s},\n"
        " status = {borrowed}, cluster = {k}, provenance = {proj}, added = {2026-06-04}, scout = {eigen}}\n",
        encoding="utf-8",
    )
    man = tmp_path / "paper"
    man.mkdir()
    (man / "refs.bib").write_text(
        "@article{Jones2021,\n author={Jones, J}, title={Beta}, year={2021}, note={arXiv:2101.00002}}\n",
        encoding="utf-8",
    )
    (man / "main.tex").write_text("\\section{Intro}\nWe lean on Jones silently.\n", encoding="utf-8")
    rep = _v.verify(str(man), corpus=str(corpus), project="proj")  # default checks
    assert rep["checks"]["citations"]["pass"] is False
    assert {n["ref"] for n in rep["checks"]["citations"]["naked_reliances"]} == {"jones2021beta"}
    assert rep["passed"] is False


# --------------------------------------------------------------------------
# CLI smoke (the scripts run as processes, as laplace_run invokes them)
# --------------------------------------------------------------------------
def test_corpus_map_renders_and_reports_gaps(capsys):
    cmap = _load("corpus_map.py")
    rc = cmap.build_map(str(_REPO / "corpus" / "corpus.bib"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "The conceptric" in out
    assert "Coverage worklist" in out
    # gaps-only mode prints the worklist without the full conceptric.
    cmap.build_map(str(_REPO / "corpus" / "corpus.bib"), gaps_only=True)
    out2 = capsys.readouterr().out
    assert "Coverage worklist" in out2 and "The conceptric" not in out2


def test_check_corpus_cli_on_seed():
    rc = subprocess.run(
        [sys.executable, str(_SKILLS / "check_corpus.py"), str(_REPO / "corpus" / "corpus.bib")],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0
    assert "well-formed" in rc.stdout
