"""W0.2 — one project context. A bare surface (no ?corpus=/?dir=) opens on the
ACTIVE PROJECT, persisted in the gitignored ``.cockpit.json`` (active_corpus),
never an empty shell.

The load-bearing invariants, all FAIL-CLOSED:
  * ``active_corpus`` reads the persisted value and never raises on a corrupt or
    absent cockpit (the serving path must not 500 on local state);
  * ``default_corpus`` prefers the persisted project, validates it against the
    real roster, and degrades cleanly to the newest-ledger default otherwise;
  * ``project_context`` server-derives the main tex and is honest (never a
    fabricated path) on an unknown corpus;
  * bare ``/review`` resolves the persisted corpus, not None;
  * the cockpit WRITE is additive-merge — a corpus switch never clobbers his
    other keys.

Every test is HERMETIC: a tmp cockpit under a tmp root, never the repo's own
``.cockpit.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    # the explicit session override must never leak in and mask the persisted /
    # derived resolution the tests exercise.
    monkeypatch.delenv("LAPLACE_ACTIVE_PROJECT", raising=False)


def _a_corpus(root: Path) -> str:
    """A corpus name registered UNDER ``root`` (never a hardcoded guess). The roster
    ``default_corpus`` validates a persisted value against is the root's OWN registry,
    so a hermetic test must register the name it persists."""
    return _hermetic_roster(root, "alpha", "beta")[0]


def _hermetic_roster(root: Path, *names: str) -> list[str]:
    """Declare ``names`` as this tmp root's OWN registry rows, in order, and return
    them. A hermetic root carries only the hand-authored blocks otherwise: the
    hardcoded corpus dict that used to register the finished papers for EVERY root
    retired 2026-08-04, so a test choosing between corpora under tmp_path must
    declare the corpora it is choosing between."""
    (root / "registry_projects.json").write_text(json.dumps({"projects": [
        {"name": n, "kind": "conceptric",
         "tex_root": f"synthetics papers/{n}/manuscript"} for n in names]}),
        encoding="utf-8")
    return list(names)


# ---------------------------------------------------------------------------
# active_corpus — the persisted read, fail-closed
# ---------------------------------------------------------------------------

def test_active_corpus_reads_persisted(tmp_path: Path):
    name = _a_corpus(tmp_path)
    (tmp_path / ".cockpit.json").write_text(
        json.dumps({"active_corpus": name}), encoding="utf-8")
    assert ci.active_corpus(tmp_path) == name


def test_active_corpus_missing_file_is_empty(tmp_path: Path):
    assert ci.active_corpus(tmp_path) == ""


def test_active_corpus_corrupt_file_never_raises(tmp_path: Path):
    (tmp_path / ".cockpit.json").write_text("not json {{{", encoding="utf-8")
    assert ci.active_corpus(tmp_path) == ""


def test_active_corpus_none_root_is_empty():
    assert ci.active_corpus(None) == ""


def test_active_corpus_wrong_type_never_raises(tmp_path: Path):
    # a cockpit whose active_corpus is not a string must not crash the reader.
    (tmp_path / ".cockpit.json").write_text(
        json.dumps({"active_corpus": ["eigenengine"]}), encoding="utf-8")
    assert ci.active_corpus(tmp_path) == ""


# ---------------------------------------------------------------------------
# default_corpus — persisted wins, validated, fail-closed
# ---------------------------------------------------------------------------

def _seed_ledger(root: Path, name: str) -> None:
    d = root / "corpus_friction"
    d.mkdir(exist_ok=True)
    (d / f"{name}.jsonl").write_text("{}\n", encoding="utf-8")


def test_default_corpus_prefers_persisted_over_newest(tmp_path: Path):
    names = _hermetic_roster(tmp_path, "alpha", "beta")
    persisted, newest = names[0], names[-1]
    assert persisted != newest
    _seed_ledger(tmp_path, newest)  # newest ledger points elsewhere
    (tmp_path / ".cockpit.json").write_text(
        json.dumps({"active_corpus": persisted}), encoding="utf-8")
    assert ci.default_corpus(tmp_path) == persisted


def test_default_corpus_ignores_foreign_persisted(tmp_path: Path):
    # a persisted value that is not a real corpus fails closed onto the derived
    # default (the newest ledger), never returned blindly.
    newest = _hermetic_roster(tmp_path, "alpha", "beta")[-1]
    _seed_ledger(tmp_path, newest)
    (tmp_path / ".cockpit.json").write_text(
        json.dumps({"active_corpus": "not-a-real-corpus"}), encoding="utf-8")
    assert ci.default_corpus(tmp_path) == newest


def test_default_corpus_corrupt_cockpit_falls_back(tmp_path: Path):
    newest = _hermetic_roster(tmp_path, "alpha", "beta")[-1]
    _seed_ledger(tmp_path, newest)
    (tmp_path / ".cockpit.json").write_text("}{ broken", encoding="utf-8")
    assert ci.default_corpus(tmp_path) == newest


def test_default_corpus_always_returns_a_real_corpus(tmp_path: Path):
    # empty root, no cockpit, no ledgers: still a registered corpus, never "".
    # An empty root registers nothing of its own, so the roster is the hand-authored
    # blocks - the point stands: whatever comes back is ON the roster it was taken from.
    roster = ci.registered_corpora(tmp_path)
    assert roster and ci.default_corpus(tmp_path) in roster


# ---------------------------------------------------------------------------
# project_context — server-derived tex, honest fallback
# ---------------------------------------------------------------------------

def test_project_context_resolves_main_tex_real_repo():
    rr = Path(__file__).resolve().parents[1]
    ctx = ci.project_context(rr)  # the active project on this repo
    # the ROSTER, the one door: the active project is whichever corpus is being
    # worked, and a project born through the New Project door (a registry data row)
    # is a registered corpus exactly like a finished paper.
    assert ctx["corpus"] in ci.registered_corpora(rr, openable=True)
    assert ctx["main_tex"] is not None
    assert ctx["main_tex"].endswith("main.tex")
    assert ctx["source"] == "main-tex"
    # the derived path is real and inside the repo.
    assert (rr / ctx["main_tex"]).is_file()


def test_project_context_unknown_corpus_is_honest(tmp_path: Path):
    ctx = ci.project_context(tmp_path, "no-such-corpus")
    assert ctx["main_tex"] is None
    assert ctx["source"] == "unknown-corpus"
    assert ctx["corpus"] == "no-such-corpus"


# ---------------------------------------------------------------------------
# bare /review resolves the persisted corpus (not None)
# ---------------------------------------------------------------------------

def test_review_bare_resolve_uses_persisted_corpus(tmp_path: Path, monkeypatch):
    from laplace.manuscript import review_surface as rv
    from laplace.web import review_http

    name = _a_corpus(tmp_path)
    (tmp_path / ".cockpit.json").write_text(
        json.dumps({"active_corpus": name}), encoding="utf-8")
    monkeypatch.setattr(rv, "_repo_root", lambda: tmp_path)

    seen: dict = {}

    def _spy(corpus="", dir_param=""):
        seen["corpus"] = corpus
        seen["dir"] = dir_param
        return tmp_path  # a real dir stands in for the manuscript dir

    monkeypatch.setattr(rv, "manuscript_dir", _spy)

    md, corpus, dir_param = rv._resolve({})  # a BARE query
    assert md is not None                    # never an empty shell
    assert corpus == name                    # the persisted active project
    assert seen["corpus"] == name


def test_review_bare_does_not_override_explicit_corpus(tmp_path: Path, monkeypatch):
    from laplace.manuscript import review_surface as rv
    from laplace.web import review_http

    (tmp_path / ".cockpit.json").write_text(
        json.dumps({"active_corpus": _a_corpus(tmp_path)}), encoding="utf-8")
    monkeypatch.setattr(rv, "_repo_root", lambda: tmp_path)
    seen: dict = {}
    monkeypatch.setattr(rv, "manuscript_dir",
                        lambda corpus="", dir_param="": seen.update(
                            corpus=corpus) or tmp_path)
    rv._resolve({"corpus": ["explicit-one"]})
    assert seen["corpus"] == "explicit-one"  # an explicit param is untouched


def test_review_context_route_returns_active_project():
    from laplace.manuscript import review_surface as rv
    from laplace.web import review_http

    status, ctype, body = review_http.handle("/review/context", {}, "GET", b"")
    assert status == 200
    ctx = json.loads(body)
    assert ctx["corpus"] in ci.registered_corpora(Path(__file__).resolve().parents[1],
                                                  openable=True)


# ---------------------------------------------------------------------------
# /projection/context — the bare-route bootstrap
# ---------------------------------------------------------------------------

def test_projection_context_route_returns_active_project():
    from laplace.manuscript import projection_viewer as pv

    status, ctype, body = pv.handle("/projection/context", {}, "GET", b"")
    assert status == 200
    ctx = json.loads(body)
    assert ctx["corpus"] in ci.registered_corpora(Path(__file__).resolve().parents[1],
                                                  openable=True)
    assert ctx["main_tex"] is not None


# W5: the bare-/guide persisted-active-project clause retired with the /guide explainer
# (the desk cockpit at /desk is a GLOBAL worklist, not project-scoped, so it selects no
# project). The cross-surface active-project law stays proven by
# tests/test_interface_weld.py::test_weld_smoke_c2_context_carries_cross_surface (bare
# /review + ci.project_context both read the persisted active_corpus).


# ---------------------------------------------------------------------------
# the cockpit WRITE is additive-merge — a corpus switch keeps his other keys
# ---------------------------------------------------------------------------

def test_cockpit_write_is_additive_merge(tmp_path: Path, monkeypatch):
    from laplace.web import scanner

    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)

    # his pre-existing knobs
    scanner.cockpit_state({"tour_seen": True, "panel_layout": "wide"})
    # a corpus switch
    scanner.cockpit_state({"active_corpus": _a_corpus(tmp_path)})

    on_disk = json.loads((tmp_path / scanner.COCKPIT_FILE).read_text(encoding="utf-8"))
    assert on_disk["active_corpus"] == _a_corpus(tmp_path)
    assert on_disk["tour_seen"] is True        # survived the switch
    assert on_disk["panel_layout"] == "wide"   # survived the switch


def test_cockpit_switch_is_read_back_by_default_corpus(tmp_path: Path, monkeypatch):
    # the round trip the surfaces rely on: a persisted switch is what a later bare
    # view resolves.
    from laplace.web import scanner

    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    name = _a_corpus(tmp_path)
    scanner.cockpit_state({"active_corpus": name})
    assert ci.active_corpus(tmp_path) == name
    assert ci.default_corpus(tmp_path) == name
