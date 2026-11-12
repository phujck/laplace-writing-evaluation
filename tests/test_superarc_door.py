"""The superarc door (B16a) — a NON-paper-shaped project surfacing through the one door.

The plain registration door is already proven (crank-2026-07-15). What is unproven, and
what this suite pins, is that a project whose graph is authored entirely as overlay
records — a stub ``main.tex``, a declared arc, native kinds that are NOT members of
``LOGICAL_KINDS`` — reaches the live viewer with ZERO engine code keyed on its name:

  (a) ``registry.conceptric_projects`` lists it, provenance ``registry-row``;
  (b) it is in ``registered_corpora(openable=True)`` — the roster ``/corpus/list`` serves;
  (c) ``resolve_corpus`` returns a path under the root (the ``main.tex`` gate is cleared);
  (d) ``corpus_network(...)["spine"]`` is non-empty and ordered by the DECLARED arc;
  (e) every declared edge lands in the network's edge_index — the dropped set is EMPTY,
      and named as empty rather than left unmeasured;
  (f) no engine module is KEYED on the name — §3's own honest form of the claim ("zero code
      keyed on the name superarc", not "zero code"): the ingestion/viewer path carries zero
      hits, and the campaign's organ package ``src/laplace/research/superarc/`` — science named for
      the SuperARC benchmark, which would exist with or without a registry row — is imported
      by nothing in that path, so it cannot be what makes the corpus surface.

Clauses (a)-(e) run twice: once against the live repo (the door as served) and once over a
hermetic tmp root carrying ONLY the registry row plus the scaffold, so the pass cannot be
an artefact of the repo's other rows. Membership is asserted on ``/corpus/list``, never on
marriage — the two are decoupled in both directions.

It also pins the latent serving bug this build fixed: ``/corpus/list`` filtered its
``corpora`` by ``openable=True`` while its ``default`` came from an UNFILTERED roster, so
the served default could name a corpus absent from the switcher and 404 on open.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.pipeline import registry

REPO = Path(__file__).resolve().parents[1]
NAME = "superarc"
PROJECT_DIR = REPO / "synthetics papers" / NAME
DECL = PROJECT_DIR / "conceptric_overlay.json"
LEDGER = REPO / "corpus_friction" / f"{NAME}.jsonl"
STUB_TEX = PROJECT_DIR / "manuscript" / "main.tex"
SOURCE_DOC = "DESIGN_2026-08-04_synthetics-genesis-superarc-strategy.md"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_overlay_conceptric", REPO / "scripts" / "build_overlay_conceptric.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BUILD = _load_builder()


@pytest.fixture(scope="module")
def decl() -> dict:
    return json.loads(DECL.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def records() -> list[dict]:
    assert LEDGER.is_file(), (
        f"corpus_friction/{NAME}.jsonl absent — run "
        f"scripts/build_overlay_conceptric.py --project {NAME}")
    return [json.loads(ln) for ln in LEDGER.read_text(encoding="utf-8").splitlines() if ln.strip()]


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """A hermetic root carrying ONLY superarc's row + scaffold: the registry row, the stub
    tex, the declaration, the ledger, and the design doc the refs point at."""
    row = next(r for r in json.loads((REPO / registry.DATA_PROJECTS_FILE)
                                     .read_text(encoding="utf-8"))["projects"]
               if r["name"] == NAME)
    (tmp_path / registry.DATA_PROJECTS_FILE).write_text(
        json.dumps({"projects": [row]}), encoding="utf-8")
    dest = tmp_path / "synthetics papers" / NAME / "manuscript"
    dest.mkdir(parents=True)
    shutil.copy2(STUB_TEX, dest / "main.tex")
    shutil.copy2(DECL, tmp_path / "synthetics papers" / NAME / DECL.name)
    (tmp_path / "corpus_friction").mkdir()
    shutil.copy2(LEDGER, tmp_path / "corpus_friction" / LEDGER.name)
    shutil.copy2(REPO / SOURCE_DOC, tmp_path / SOURCE_DOC)
    return tmp_path


# ---------------------------------------------------------------------------
# (a)-(e) — the door, over the hermetic root AND over the live repo
# ---------------------------------------------------------------------------

@pytest.fixture(params=["hermetic", "live"])
def door_root(request, tmp_repo: Path) -> Path:
    return tmp_repo if request.param == "hermetic" else REPO


def test_door_a_registry_lists_it_as_a_data_row(door_root: Path):
    rows = {r["name"]: r for r in registry.conceptric_projects(door_root)}
    assert NAME in rows, "the registry does not list superarc — it never reaches any surface"
    assert rows[NAME]["provenance"] == "registry-row"
    assert rows[NAME]["kind"] == "conceptric"
    assert rows[NAME]["tex_root"] == f"synthetics papers/{NAME}/manuscript"


def test_door_b_it_is_in_the_openable_roster(door_root: Path):
    # the roster /corpus/list serves: registered_corpora(rr, openable=True)
    assert NAME in ci.registered_corpora(door_root, openable=True)


def test_door_c_resolve_corpus_returns_a_root_under_the_repo(door_root: Path):
    p = ci.resolve_corpus(door_root, NAME)
    assert p is not None, "the main.tex gate rejected the stub — the corpus 404s on open"
    assert p.resolve().is_relative_to(Path(door_root).resolve())
    assert (p / "main.tex").is_file()


def test_door_d_the_spine_is_non_empty_and_follows_the_declared_arc(door_root: Path, decl):
    net = ci.corpus_network(ci.resolve_corpus(door_root, NAME), door_root, NAME)
    spine = net["spine"]
    declared = [b["node"] for b in decl["arc"]["beats"]]
    assert spine, "a silently empty spine on a green run is exactly how R1 survived"
    assert [b["id"] for b in spine] == declared
    assert [b["ord"] for b in spine] == list(range(len(declared))), "ord is the LIST INDEX"
    # the goal is deliberately OFF the beat list (dag_map emits DERIVATION_KINDS only,
    # which excludes goal), and the dashboard scaffold's goal beat is superseded away.
    assert not any(net["nodes"][b["id"]].get("kind") == "goal" for b in spine)
    assert [n for n, v in net["nodes"].items() if v.get("kind") == "goal"] == [decl["goal"]["id"]]


def test_door_e_every_declared_edge_lands_the_dropped_set_is_empty(door_root: Path, decl):
    net = ci.corpus_network(ci.resolve_corpus(door_root, NAME), door_root, NAME)
    ei = net.get("edge_index", {})
    dropped = [f"{e['node']}->{e['target']}" for e in decl["edges"]
               if e["target"] not in ei.get(e["node"], [])]
    assert dropped == [], f"declared edges dropped by the read layer: {dropped}"
    assert len(decl["edges"]) > 0
    # typed edges land on their declared axis, not only as a bare referent
    for e in decl["edges"]:
        if e.get("axis"):
            assert f"{e['axis']}::{e['target']}" in ei[e["node"]]


# the campaign's own organ package: SuperARC-the-benchmark's science (BDM, phi, the bin
# classifier, the sequence executor, the submission gate). It shares a name with the corpus
# because the corpus TRACKS that campaign, not because either is wired to the other — so it is
# excluded from the name-hit sweep and pinned by the import fence below instead.
ORGANS = REPO / "src" / "laplace" / "research" / "superarc"


def test_door_f_no_engine_code_is_keyed_on_the_name():
    hits = [f"{p.relative_to(REPO)}:{i}"
            for p in sorted((REPO / "src").rglob("*"))
            if p.is_file() and p.suffix in {".py", ".js", ".mjs", ".html", ".css", ".json"}
            and ORGANS not in p.parents
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
            if NAME in ln.lower()]
    assert hits == [], f"per-project engine code for {NAME}: {hits}"


def test_door_f2_the_organ_package_is_not_on_the_ingestion_path():
    """The exclusion above is only honest if the organs are unreachable from the code that
    surfaces the corpus: nothing outside the package may import it."""
    importers = [f"{p.relative_to(REPO)}:{i}"
                 for p in sorted((REPO / "src").rglob("*.py"))
                 if ORGANS not in p.parents
                 for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if f"laplace.research.{NAME}" in ln or f"from .{NAME}" in ln or f"import {NAME}" in ln]
    assert importers == [], f"the ingestion path reaches the organ package: {importers}"


# ---------------------------------------------------------------------------
# the overlay form — legal kinds, the taxonomy untouched, a rebuildable ledger
# ---------------------------------------------------------------------------

def test_node_kinds_are_legal_and_the_taxonomy_is_untouched(records, decl):
    adds = [r for r in records if r["kind"] == "add-node"]
    assert adds, "no add-node records on the ledger"
    for r in adds:
        assert r["node_kind"] in ci.LOGICAL_KINDS, r["node"]
    # the campaign's NATIVE kinds stay out of LOGICAL_KINDS: DERIVATION_KINDS and
    # PROVENANCE_EXEMPT derive from that tuple, so widening it moves every project's
    # gap counts and provenance scores.
    natives = set(decl["kind_map"]) - {"goal"}
    assert natives and not (natives & set(ci.LOGICAL_KINDS))


def test_the_native_kind_survives_on_the_projection_slot(decl):
    net = ci.corpus_network(ci.resolve_corpus(REPO, NAME), REPO, NAME)
    for n in [decl["goal"], *decl["nodes"]]:
        proj = net["nodes"][n["id"]].get("projection") or {}
        assert proj.get("native_kind") == n["kind"], n["id"]
        assert proj.get("term"), n["id"]          # /corpus/spine renders this handle


def test_the_ledger_is_a_rebuild_of_the_declaration(records):
    ledger, text, census = BUILD.emit(REPO, NAME)
    assert ledger == LEDGER
    assert text == LEDGER.read_text(encoding="utf-8"), (
        "the ledger drifted from its declaration — re-run "
        f"scripts/build_overlay_conceptric.py --project {NAME}")
    assert census["spine_beats"] > 0 and census["n_edges"] > 0
    # the builder owns its own block only: the dashboard's birth records survive a rebuild
    assert any(r.get("by") == "dashboard-new-project" for r in records)


def test_every_node_carries_a_resolvable_source_ref(records):
    for r in (x for x in records if x["kind"] == "add-node" and x.get("by") == BUILD.BUILD_TAG):
        assert r.get("ref"), r["node"]
        BUILD._check_ref(r["ref"], r["node"], REPO)     # raises on a dead file/line span


@pytest.mark.parametrize("mutate, needle", [
    (lambda d: d["arc"].update(beats=[]), "no beats"),
    (lambda d: d["arc"]["beats"].append({"node": "phase:nowhere"}), "does not build"),
    (lambda d: d["arc"]["beats"].append({"node": "phase:runs"}), "declared twice"),
    (lambda d: d["nodes"][0].update(kind="unmapped-kind"), "not in kind_map"),
    (lambda d: d["kind_map"].update(phase="phase"), "outside LOGICAL_KINDS"),
    (lambda d: d["nodes"][0].update(parent="node:nowhere"), "unknown node"),
    (lambda d: d["edges"][0].update(target="node:nowhere"), "not a declared node"),
    (lambda d: d["nodes"][0].update(ref=f"{SOURCE_DOC}:999999"), "outside"),
])
def test_the_builder_hard_fails_rather_than_pouring_a_broken_graph(decl, mutate, needle):
    d = json.loads(json.dumps(decl))
    mutate(d)
    with pytest.raises(BUILD.DeclarationError) as e:
        BUILD.validate(d, REPO)
    assert needle in str(e.value)


# ---------------------------------------------------------------------------
# /corpus/list — the served pair, and the default-vs-openable fix
# ---------------------------------------------------------------------------

def _corpus_list(root: Path) -> dict:
    """Exactly what scanner's /corpus/list serves, built from the same two functions."""
    return {"corpora": ci.registered_corpora(root, openable=True),
            "default": ci.default_corpus(root)}


def test_corpus_list_serves_superarc_and_a_default_that_is_in_the_list(monkeypatch):
    monkeypatch.delenv("LAPLACE_ACTIVE_PROJECT", raising=False)
    served = _corpus_list(REPO)
    assert NAME in served["corpora"]
    assert served["default"] in served["corpora"], (
        "the served default is absent from the switcher and 404s on open")


def test_the_default_never_names_an_unopenable_corpus(tmp_path: Path, monkeypatch):
    """The latent bug, pinned: the newest-ledger candidate has no main.tex, so it is
    absent from the roster /corpus/list serves — the default must skip it."""
    monkeypatch.delenv("LAPLACE_ACTIVE_PROJECT", raising=False)
    (tmp_path / registry.DATA_PROJECTS_FILE).write_text(json.dumps({"projects": [
        {"name": "openable-one", "tex_root": "synthetics papers/openable-one/manuscript"},
        {"name": "ghost", "tex_root": "synthetics papers/ghost/manuscript"}]}), encoding="utf-8")
    ms = tmp_path / "synthetics papers" / "openable-one" / "manuscript"
    ms.mkdir(parents=True)
    (ms / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    fr = tmp_path / "corpus_friction"
    fr.mkdir()
    (fr / "ghost.jsonl").write_text("{}\n", encoding="utf-8")     # the newest ledger

    served = _corpus_list(tmp_path)
    assert served["corpora"] == ["openable-one"]
    assert served["default"] == "openable-one"
    # the same fence on the PERSISTED value: a stale cockpit pointing at the ghost
    (tmp_path / ".cockpit.json").write_text(json.dumps({"active_corpus": "ghost"}),
                                            encoding="utf-8")
    assert ci.default_corpus(tmp_path) == "openable-one"
    # and on the env override
    monkeypatch.setenv("LAPLACE_ACTIVE_PROJECT", "ghost")
    assert ci.default_corpus(tmp_path) == "openable-one"


def test_an_empty_openable_roster_degrades_to_a_name_not_a_dead_switch(tmp_path: Path,
                                                                      monkeypatch):
    """Nothing openable under this root: with an empty switcher every default 404s
    anyway, so the roster degrades to the registry names rather than to ''."""
    monkeypatch.delenv("LAPLACE_ACTIVE_PROJECT", raising=False)
    assert ci.registered_corpora(tmp_path, openable=True) == []
    assert ci.default_corpus(tmp_path) in ci.registered_corpora(tmp_path)
