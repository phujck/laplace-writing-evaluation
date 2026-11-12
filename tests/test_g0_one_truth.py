"""Scoped tests for the G0 wave (one truth, one lock): the authoritative project
list and its provenance labels, the data-row resolution the crank proved missing,
and the two traversal fences the adversarial close demanded — a data-row tex_root
must never escape the repo root, skipped at the merge AND refused at the resolve
choke point whatever the registry hands back.
"""
import json
from pathlib import Path

from laplace.research import corpus_ingest as ci
from laplace.pipeline import registry

REPO = Path(__file__).resolve().parents[1]


def _fakerepo(tmp_path, rows):
    (tmp_path / "registry_projects.json").write_text(
        json.dumps({"projects": rows}), encoding="utf-8")
    return tmp_path


# ------------------------------------------------------- the authoritative list
def test_one_list_with_provenance_on_the_real_repo():
    rows = {r["name"]: r for r in registry.conceptric_projects(REPO)}
    # the TWO provenance layers, each witnessed by a real member
    assert rows["crank-2026-07-15"]["provenance"] == "registry-row"
    assert rows["eigenengine"]["provenance"] == "hardcoded-block"
    assert rows["paper_falqon"]["provenance"] == "hardcoded-block"
    # non-conceptric layouts stay off the list, so resolve_corpus keeps its old
    # answers for them
    for absent in ("website", "ssg-disclosure", "paper_eigen"):
        assert absent not in rows


def test_the_finished_papers_enter_by_the_same_door_as_a_new_project():
    """The corpora-legacy layer is RETIRED (2026-08-04). The six finished papers the
    hardcoded dict used to define are data rows now — same names, same tex roots, the
    same route a project born through the New Project door takes. A middle layer that
    only code could write is the desync class the whole G0 wave exists to kill."""
    rows = {r["name"]: r for r in registry.conceptric_projects(REPO)}
    migrated = {
        "design-interface": "design_conceptric/manuscript",
        "law-of-laws": "synthetics papers/law-of-laws/manuscript/tex",
        "cost-of-complexity": "synthetics papers/cost-of-complexity/manuscript/tex",
        "qde": "synthetics papers/qde/manuscript/tex",
        "free-snacks": "synthetics papers/free-snacks/manuscript/tex",
        "subset-sum-itqde": "synthetics papers/subset-sum-itqde/manuscript/tex",
    }
    for name, tex_root in migrated.items():
        assert rows[name]["provenance"] == "registry-row", name
        assert rows[name]["tex_root"] == tex_root, name
    # no row anywhere carries the retired label
    assert {r["provenance"] for r in rows.values()} == {"registry-row", "hardcoded-block"}
    # and the shared-corpus child still points at the parent substrate (the literal
    # that was read off the dict, now inlined in the hand-authored block)
    assert registry.resolve("ssg-disclosure").tex_root == migrated["subset-sum-itqde"]


# ------------------------------------------------------- the degraded registry
def test_degraded_registry_serves_an_empty_roster_not_a_stale_one(monkeypatch, caplog):
    """A registry read that RAISES yields an EMPTY roster and a "" default, logged —
    never a stale hardcoded list. There is no second corpus list left to fall back to,
    and rebuilding one would rebuild the desync; the serving path degrades (an empty
    switcher, an honest log) instead of dying or lying."""
    def _boom(repo_root=None):
        raise RuntimeError("registry read failed")
    monkeypatch.setattr(registry, "conceptric_projects", _boom)
    with caplog.at_level("ERROR"):
        assert ci.registered_corpora(REPO) == []
        assert ci.registered_corpora(REPO, openable=True) == []
        assert ci.default_corpus(REPO) == ""
    assert any("registry read failed" in r.message or "roster unavailable" in r.message
               for r in caplog.records), "a failed registry read must be LOUD"


def test_empty_roster_yields_no_default_rather_than_a_magic_name(tmp_path, monkeypatch):
    """An EMPTY (not failed) roster returns "" too. The old code returned the first key
    of the hardcoded dict here, so a root registering nothing still served a name its
    own switcher never offered."""
    monkeypatch.setattr(registry, "conceptric_projects", lambda repo_root=None: [])
    assert ci.registered_corpora(tmp_path) == []
    assert ci.default_corpus(tmp_path) == ""
    # and the context read stays honest rather than raising on the empty name
    assert ci.project_context(tmp_path)["main_tex"] is None


def test_data_row_project_resolves_inside_the_repo():
    # the crank finding, retired: a dashboard-scaffolded project resolves through
    # the same door as the finished papers
    root = ci.resolve_corpus(REPO, "crank-2026-07-15")
    assert root is not None
    assert root.resolve().is_relative_to(REPO.resolve())
    # the old answers stay the old answers
    assert ci.resolve_corpus(REPO, "no-such-project") is None
    assert ci.resolve_corpus(REPO, "../../etc") is None


# ------------------------------------------------------- the two fences
def test_merge_fence_skips_path_shaped_rows(tmp_path):
    fake = _fakerepo(tmp_path, [
        {"name": "good", "kind": "conceptric", "tex_root": "synthetics papers/good/manuscript"},
        {"name": "evil-rel", "kind": "conceptric", "tex_root": "../escape-rel"},
        {"name": "evil-abs", "kind": "conceptric", "tex_root": str(tmp_path.parent / "escape-abs")},
        {"name": "../evil-name", "kind": "conceptric", "tex_root": "synthetics papers/x/manuscript"},
    ])
    names = {r["name"] for r in registry.conceptric_projects(fake)}
    assert "good" in names
    assert "evil-rel" not in names
    assert "evil-abs" not in names
    assert "../evil-name" not in names


def test_resolve_containment_belt_refuses_an_escaping_root(tmp_path, monkeypatch):
    # even if a poisoned row somehow slipped the merge fence, the resolve choke
    # point refuses any root outside repo_root - plant an escape target WITH a
    # main.tex so only the containment belt can be what stops it
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "main.tex").write_text("% escape target", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        registry, "conceptric_projects",
        lambda root=None: [
            {"name": "evil-rel", "kind": "conceptric", "tex_root": "../outside",
             "provenance": "registry-row"},
            {"name": "evil-abs", "kind": "conceptric", "tex_root": str(outside),
             "provenance": "registry-row"},
        ])
    assert ci.resolve_corpus(repo, "evil-rel") is None
    assert ci.resolve_corpus(repo, "evil-abs") is None
