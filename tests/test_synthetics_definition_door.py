"""The synthetics-definition door — the DEFINITION of synthetics, served as a conceptric.

The object is the definition, not the campaign that produced it: two rigorous halves, the
fused word, the half-built join, the one missing equation, the graded findings including the
three withdrawn ones, and the declared open ports. It reaches the live viewer through the
ENCODED-DOORS path (ruling R3, ``evidence/SYNTHETICS_DEFINITION_2026-08-13_derived-rulings.md``):
a registry data row, an ~8-line stub ``main.tex``, and a conceptric_overlay.json COMPILED from
the banked root documents — no ``dashboard.create_project``, no hand-authored declaration, and
zero engine code keyed on the name.

The clauses were PRE-REGISTERED before the graph was built:

  (a) the registry lists it as a data row, kind conceptric;
  (b) it is in ``registered_corpora(openable=True)`` — the roster ``/corpus/list`` serves;
  (c) ``resolve_corpus`` returns a path (the ``main.tex`` gate is cleared by the stub);
  (d) the spine is non-empty and ordered exactly as THE_STORY's seven parts (ruling R4),
      re-derived from THE_STORY here rather than trusted from the declaration;
  (e) node + edge accounting: every declared node and edge lands, the dropped set is NAMED
      as empty, and the two EXTRA nodes are named as the stub's own base leaves;
  (f) no engine module is keyed on the name;
  (g) every declared ref resolves to a file and a span that exist (ruling R5: local
      carriers only — the anchors into the absent physics corpus are a typed residue NODE,
      never a minted ref);
  (h) the compiler is byte-stable: a fresh compile equals what is on disk, twice — and
      byte-stability means CONTENT-stability, because every stored ref is a content anchor
      (``<path>:@<digest>``) rather than a line number. Strengthened 2026-08-21 after this
      clause went red twice in one day on line shifts inside root documents: an offset is a
      property of the file, so an insertion anywhere above a ref rewrote it and reported an
      unrelated upstream edit as a defect here. The located-never-typed floor is unchanged
      and re-measured (h1c); what moved is that the artefact now changes only when the prose
      it points at changes;
  (i) every claims-derived node carries an authored ``epistemic_status`` in its projection
      (ruling R6 — the five-value claims.json vocabulary and THE_STORY's tier words ride the
      projection slot; no new axis is minted for them);
  (j) synthetics-genesis is clean under ``registry.truth_layer_check`` (ruling R11);
  (k) NO node essence carries a verbatim run of 12 words or more from THE_STORY — added
      after review measured the first build leaking his prose (nine essences were elisions
      of single Story paragraphs, the worst 78% verbatim in the Story's own order). The
      privacy clause is that the graph POINTS at his text and never carries it, and 35/35
      green did not catch the breach because no clause measured it. It is measured here on
      the emitted declaration AND enforced in the compiler at a tighter limit
      (``MAX_VERBATIM_RUN``), so the leak cannot return through a later edit.

Clauses (a)-(e) run twice: once against the live repo, once over a hermetic tmp root carrying
ONLY this project's row and scaffold, so a pass cannot be an artefact of the repo's other rows.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.manuscript import source_anchor as sa
from laplace.pipeline import registry, schema

REPO = Path(__file__).resolve().parents[1]
NAME = "synthetics-definition"
PROJECT_DIR = REPO / "synthetics papers" / NAME
DECL = PROJECT_DIR / "conceptric_overlay.json"
LEDGER = REPO / "corpus_friction" / f"{NAME}.jsonl"
STUB_TEX = PROJECT_DIR / "manuscript" / "main.tex"
STORY = REPO / "synthetics papers" / "synthetics-genesis" / "THE_STORY_OF_SYNTHETICS.md"

#: the ONLY nodes the network may carry beyond the declaration: the stub ``main.tex``'s own
#: atomised base leaves. Named here so "the accounting balances" is a measurement, not a
#: shrug — anything else appearing is a regression, not a rounding error.
BASE_LEAVES = {"paper://", "references"}


def _load(script: str):
    spec = importlib.util.spec_from_file_location(script, REPO / "scripts" / f"{script}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BUILD = _load("build_overlay_conceptric")
COMPILE = _load("compile_synthetics_definition_overlay")


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
    """A hermetic root carrying ONLY this project's registry row + scaffold."""
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
    return tmp_path


@pytest.fixture(params=["hermetic", "live"])
def door_root(request, tmp_repo: Path) -> Path:
    return tmp_repo if request.param == "hermetic" else REPO


def _net(root: Path):
    return ci.corpus_network(ci.resolve_corpus(root, NAME), root, NAME)


# ---------------------------------------------------------------------------
# (a)-(e) — the door
# ---------------------------------------------------------------------------

def test_a_registry_lists_it_as_a_conceptric_data_row(door_root: Path):
    rows = {r["name"]: r for r in registry.conceptric_projects(door_root)}
    assert NAME in rows, "the registry does not list it — it never reaches any surface"
    assert rows[NAME]["kind"] == "conceptric"
    assert rows[NAME]["provenance"] == "registry-row", (
        "the encoded-doors path is a DATA row; a hardcoded block would be engine code "
        "keyed on this project")
    assert rows[NAME]["tex_root"] == f"synthetics papers/{NAME}/manuscript"


def test_b_it_is_in_the_openable_roster(door_root: Path):
    assert NAME in ci.registered_corpora(door_root, openable=True)


def test_c_resolve_corpus_returns_a_root_under_the_repo(door_root: Path):
    p = ci.resolve_corpus(door_root, NAME)
    assert p is not None, "the main.tex gate rejected the stub — the corpus 404s on open"
    assert p.resolve().is_relative_to(Path(door_root).resolve())
    assert (p / "main.tex").is_file()


def test_d_the_spine_is_the_storys_seven_parts_in_its_own_order(door_root: Path, decl):
    """Ruling R4: the arc is THE_STORY's part order, beats at part level. The expected order
    is re-derived from THE_STORY here — if the Story is re-sectioned, this fails rather than
    agreeing with a stale declaration."""
    story_parts = [(int(m.group(1)), m.group(2).strip())
                   for m in (re.match(r"^## (\d)\. (.+)$", ln)
                             for ln in STORY.read_text(encoding="utf-8").splitlines())
                   if m]
    assert [n for n, _ in story_parts] == [1, 2, 3, 4, 5, 6, 7]

    spine = _net(door_root)["spine"]
    assert spine, "a silently empty spine on a green run is exactly how R1 survived"
    declared = [b["node"] for b in decl["arc"]["beats"]]
    assert [b["id"] for b in spine] == declared
    assert [b["ord"] for b in spine] == list(range(len(declared))), "ord is the LIST INDEX"
    # each beat declares which Story part it carries, and they line up 1..7 in file order
    carried = [b["story_part"] for b in decl["arc"]["beats"]]
    assert len(carried) == len(story_parts)
    for (n, title), label in zip(story_parts, carried):
        assert label.startswith(f"{n}. {title}"), (label, n, title)
    # the goal is deliberately OFF the beat list and is the corpus's only goal node
    net = _net(door_root)
    assert not any(net["nodes"][b["id"]].get("kind") == "goal" for b in spine)
    assert [n for n, v in net["nodes"].items() if v.get("kind") == "goal"] == [decl["goal"]["id"]]


def test_e_node_and_edge_accounting_against_a_named_dropped_set(door_root: Path, decl):
    net = _net(door_root)
    declared_nodes = {decl["goal"]["id"]} | {n["id"] for n in decl["nodes"]}
    missing = sorted(declared_nodes - set(net["nodes"]))
    assert missing == [], f"declared nodes the read layer dropped: {missing}"
    extra = set(net["nodes"]) - declared_nodes
    assert extra == BASE_LEAVES, (
        f"unaccounted nodes in the network: {sorted(extra - BASE_LEAVES)} "
        f"(missing base leaves: {sorted(BASE_LEAVES - extra)})")

    ei = net.get("edge_index", {})
    dropped = [f"{e['node']}->{e['target']}" for e in decl["edges"]
               if e["target"] not in ei.get(e["node"], [])]
    assert dropped == [], f"declared edges dropped by the read layer: {dropped}"
    assert len(decl["edges"]) > 0
    for e in decl["edges"]:
        if e.get("axis"):
            # the typed token is minted through the ONE home (schema.token_for), so the
            # test cannot drift from the wire; `derives` is the untyped family and keeps
            # the human-confirmed token.
            token = (schema.token_for("derives", e["target"], mode="confirmed")
                     if e["axis"] == "derives"
                     else schema.token_for(e["axis"], e["target"]))
            assert token in ei[e["node"]], (e, token)


# ---------------------------------------------------------------------------
# (f) — no engine code keyed on the name
# ---------------------------------------------------------------------------

def test_f_no_engine_code_is_keyed_on_the_name():
    hits = [f"{p.relative_to(REPO)}:{i}"
            for p in sorted((REPO / "src").rglob("*"))
            if p.is_file() and p.suffix in {".py", ".js", ".mjs", ".html", ".css", ".json"}
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
            if NAME in ln.lower()]
    assert hits == [], f"per-project engine code for {NAME}: {hits}"


# ---------------------------------------------------------------------------
# (g) — every declared ref resolves, to a LOCAL carrier
# ---------------------------------------------------------------------------

def test_g_every_declared_ref_resolves_to_a_local_carrier(decl):
    for n in [decl["goal"], *decl["nodes"]]:
        assert n.get("ref"), n["id"]
        BUILD._check_ref(n["ref"], n["id"], REPO)      # raises on a dead file / line span
        path = n["ref"].rsplit(":", 1)[0]
        assert not path.startswith("/"), (
            f"{n['id']} refs an absolute path — ruling R5 admits local carriers only")


def test_g2_the_external_corpus_enters_as_a_residue_node_not_as_refs(decl):
    """Ruling R5's SHAPE: 588/643 residue anchors and 4/24 claim anchors point into a
    physics corpus outside this repo, and they enter as ONE typed residue node rather than
    as minted refs — a ref into a tree this repo does not contain breaks on any machine
    without it.

    R5's factual half was re-measured on 2026-08-13 once the corpus was mounted here, and
    the commit leg closed on 2026-08-14 after a deepening fetch
    (`synthetics papers/synthetics-definition/experiments/RESULTS_anchor_reverification.md`
    carries both runs): 667/667 anchors verify byte-for-byte and all 15 recorded commits
    resolve. This test pins the shape, which is unchanged, and the surviving residue,
    which narrowed to anchor survival under corpus MOTION (never observed — the census ran
    against a static tree). It does NOT pin retired wording: asserting the corpus is
    'ABSENT' or the provenance 'undecidable' would now be asserting falsehoods."""
    residue = next(n for n in decl["nodes"] if n["id"] == "res:external-anchor-residue")
    e = residue["essence"]
    assert "/home/user/physics_paper_orchestra" in e
    assert "DECLARED RESIDUE, not evidence" in e
    assert (residue.get("projection") or {}).get("epistemic_status") == "declared-residue"
    # the measured half names its run (contact law) and its results carrier
    assert "experiments/verify_anchors.py" in e
    assert "RESULTS_anchor_reverification.md" in e
    # the surviving residue is stated, not asserted away
    assert "667 of 667 verify byte-for-byte" in e
    assert "15 of 15 recorded commits" in e
    assert "deepening" in e and "fetch" in e
    # the narrowed residue is stated, not asserted away
    assert "MOTION" in e
    # and no node anywhere refs into the corpus, mounted or not
    for n in [decl["goal"], *decl["nodes"]]:
        assert "physics_paper_orchestra" not in n["ref"], n["id"]


# ---------------------------------------------------------------------------
# (h) — the compiler is byte-stable, and the ledger is a rebuild of its output
# ---------------------------------------------------------------------------

def test_h_the_compiler_is_byte_stable():
    first, _ = COMPILE.build(REPO)
    second, _ = COMPILE.build(REPO)
    assert first == second, "two compiles of the same tree disagree — the compiler is not pure"
    for rel, text in first.items():
        on_disk = PROJECT_DIR / rel
        assert on_disk.is_file(), rel
        assert on_disk.read_text(encoding="utf-8") == text, (
            f"{rel} drifted from its compiler — re-run scripts/{COMPILE.PRODUCER.split('/')[-1]}")


def test_h1a_every_stored_ref_is_a_content_anchor_not_an_offset(decl):
    """WHAT BYTE-STABILITY MEANS HERE — strengthened after this clause went red twice in one
    day for a reason that had nothing to do with this project. The compiler LOCATES its
    anchors (that floor is unchanged and re-measured below) but must STORE the located
    CONTENT: a stored line number is a fact about the whole file, so inserting one line into
    a root document rewrote refs here and turned an unrelated upstream edit into a
    byte-stability failure. Every ref is therefore a ``<path>:@<digest>[+<n>]`` anchor, and
    (h) now means the artefact changes when the prose it points at changes and at no other
    time. A later edit that reintroduces an offset fails HERE, not two commits downstream."""
    for n in [decl["goal"], *decl["nodes"]]:
        path, locator = sa.parse_ref(n["ref"])
        assert sa.is_content_anchor(locator), (
            f"{n['id']} stores the offset {locator!r} into {path} — a line number drifts on "
            f"any insertion above it; store the content (Sources.ref_at / ref_of)")
        # and it still resolves: the anchored prose is present, and unique, right now
        sa.resolve(n["ref"], REPO)


def test_h1b_an_insertion_above_an_anchor_does_not_move_the_stored_ref(tmp_path):
    """The mechanism, measured end-to-end on the compiler's own store path rather than
    argued: take a real root document, push its anchored line down the file, and the ref the
    compiler would store is byte-identical while the DERIVED line number follows the prose."""
    rel = str(STORY.relative_to(REPO))
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    original = STORY.read_text(encoding="utf-8")
    needle = "As written, Synthetics is two rigorous halves"

    (tmp_path / rel).write_text(original, encoding="utf-8")
    before = COMPILE.Sources(tmp_path).ref_of(rel, needle)
    line_before = sa.resolve(before, tmp_path)[1]

    shifted = "a line inserted upstream\nand a second one\n" + original
    (tmp_path / rel).write_text(shifted, encoding="utf-8")
    after = COMPILE.Sources(tmp_path).ref_of(rel, needle)

    assert after == before, "a pure line shift changed the stored ref — the class is back"
    assert sa.resolve(after, tmp_path)[1] == line_before + 2, (
        "the ref survived but stopped pointing at its prose")


def test_h1c_the_compiler_refuses_to_store_an_anchor_whose_content_moved_away(tmp_path):
    """The floor, on the STORED form: rewrite the anchored line and the ref does not slide
    to a neighbour — it dies, and the compile dies with it."""
    rel = str(STORY.relative_to(REPO))
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_text(STORY.read_text(encoding="utf-8"), encoding="utf-8")
    ref = COMPILE.Sources(tmp_path).ref_of(rel, "As written, Synthetics is two rigorous halves")

    lines = (tmp_path / rel).read_text(encoding="utf-8").splitlines()
    i = next(i for i, ln in enumerate(lines) if "As written, Synthetics" in ln)
    lines[i] = lines[i] + " (edited)"
    (tmp_path / rel).write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(sa.AnchorError):
        sa.resolve(ref, tmp_path)


def test_h2_the_ledger_is_a_rebuild_of_the_declaration(records):
    ledger, text, census = BUILD.emit(REPO, NAME)
    assert ledger == LEDGER
    assert text == LEDGER.read_text(encoding="utf-8"), (
        "the ledger drifted from its declaration — re-run "
        f"scripts/build_overlay_conceptric.py --project {NAME}")
    assert census["spine_beats"] == 7 and census["n_edges"] > 0
    assert all(r.get("by") == BUILD.BUILD_TAG for r in records), (
        "this ledger has exactly one producer; a foreign record here means a second writer")


def test_h3_node_kinds_are_legal_and_the_taxonomy_is_untouched(records, decl):
    adds = [r for r in records if r["kind"] == "add-node"]
    assert adds
    for r in adds:
        assert r["node_kind"] in ci.LOGICAL_KINDS, r["node"]
    natives = set(decl["kind_map"])
    assert natives and not (natives & set(ci.LOGICAL_KINDS)), (
        "a native kind collides with LOGICAL_KINDS — DERIVATION_KINDS and PROVENANCE_EXEMPT "
        "derive from that tuple, so every project's gap counts would move")
    # ruling R7: kinds are REAL, not a blanket `support` — the findings are results, so the
    # provenance instruments have something to check rather than passing vacuously.
    logical = {r["node"]: r["node_kind"] for r in adds}
    assert all(logical[n["id"]] == "result" for n in decl["nodes"]
               if n["id"].startswith("res:"))
    assert not any(k == "support" for k in logical.values())


# ---------------------------------------------------------------------------
# (i) — the authored epistemic statuses ride the projection slot
# ---------------------------------------------------------------------------

CLAIMS_VOCAB = {"standing", "superseded", "withdrawn", "rival-win", "cut"}
STORY_TIERS = {"solid", "suggestive", "one-data-point", "withdrawn"}
LOCAL_TYPES = {"typed-failure", "declared-residue", "imported-warrant"}


def test_i_every_claims_derived_node_carries_an_epistemic_status(decl):
    claims = json.loads((REPO / "synthetics papers" / "synthetics-genesis" /
                         "projection" / "claims.json").read_text(encoding="utf-8"))
    status_of = {c["id"]: c["status"] for c in claims["claims"]}

    carriers = [n for n in [decl["goal"], *decl["nodes"]]
                if n["id"].startswith(("res:", "goal:"))]
    assert len(carriers) >= 26, "the findings ledger lost nodes"
    for n in carriers:
        proj = n.get("projection") or {}
        st = proj.get("epistemic_status")
        assert st, f"{n['id']} carries no epistemic_status — ruling R6"
        assert st in CLAIMS_VOCAB | STORY_TIERS | LOCAL_TYPES, (n["id"], st)
        assert proj.get("epistemic_status_source"), n["id"]
        if proj.get("claim_id"):
            cid = proj["claim_id"]
            assert cid in status_of, (n["id"], cid)
            assert proj["claim_status"] == status_of[cid], (
                f"{n['id']} carries a stale status for {cid}")

    # the three WITHDRAWN §3 findings are present and typed as such (ruling R6: the
    # withdrawals ship in the same list at the same standing as the wins)
    withdrawn = [n["id"] for n in decl["nodes"]
                 if (n.get("projection") or {}).get("epistemic_status") == "withdrawn"
                 and (n.get("projection") or {}).get("epistemic_status_source")
                 == "THE_STORY §3 tier word"]
    assert len(withdrawn) == 3, withdrawn


def test_i2_the_thirteen_graded_findings_all_landed(decl):
    """Every graded finding of THE_STORY §3, in section order, with the tier word the
    section itself puts in front of it."""
    tiers = {"Solid": "solid", "Suggestive": "suggestive",
             "One data point": "one-data-point", "Withdrawn": "withdrawn"}
    story = [tiers[m.group(1)] for m in
             (re.match(r"^\*\*(Solid|Suggestive|One data point|Withdrawn): ",
                       ln) for ln in STORY.read_text(encoding="utf-8").splitlines()) if m]
    assert len(story) == 13
    graded = sorted((n for n in decl["nodes"]
                     if (n.get("projection") or {}).get("epistemic_status_source")
                     == "THE_STORY §3 tier word"),
                    key=lambda n: n["projection"]["story_order"])
    assert [n["projection"]["story_order"] for n in graded] == list(range(1, 14))
    assert [n["projection"]["epistemic_status"] for n in graded] == story


def test_i3_the_n37_open_port_is_declared_open_and_untouched(decl):
    """Ruling R8: N37 enters as a declared open port. The node names the ask, the block and
    the trigger, and says in as many words that it does not answer or close the row."""
    n = next(x for x in decl["nodes"] if x["id"] == "def:response-function-synthetics")
    assert n["kind"] == "open-port"
    for needle in ("BLOCKED", "TRIGGER", "does not answer"):
        assert needle in n["essence"], needle
    assert n["ref"].startswith("OPEN_STACK.md:")


def test_i4_the_atlas_touchpoint_is_a_gated_spec_not_a_result(decl):
    """The two future experiments are named with their gate: atlas Phases 4-5 are absent."""
    n = next(x for x in decl["nodes"] if x["id"] == "technique:atlas-joint-experiments")
    assert n["kind"] == "experiment-spec"
    assert "A SPEC, NOT A RESULT" in n["essence"]
    assert "ABSENT" in n["essence"]
    # both carriers are REF'd, not merely listed: the spec node refs the design, and the
    # gate it is gated on refs the banked Phase-3 stop condition.
    refs = {x["id"]: x["ref"] for x in decl["nodes"]}
    assert refs["technique:atlas-joint-experiments"].startswith("DESIGN_2026-08-01_the-atlas.md:")
    gate = next(x for x in decl["nodes"] if x["id"] == "portal:atlas-phase3-stop")
    assert gate["ref"].startswith("evidence/ATLAS_PHASE3_2026-08-01_stop-condition.md:")
    assert "FIRED" in gate["essence"]
    for doc in ("DESIGN_2026-08-01_the-atlas.md",
                "evidence/ATLAS_PHASE3_2026-08-01_stop-condition.md"):
        assert (REPO / doc).is_file()
        assert doc in json.dumps(decl["source"]), doc


# ---------------------------------------------------------------------------
# (j) — the synthetics-genesis truth-layer conflict is cleared (ruling R11)
# ---------------------------------------------------------------------------

def test_j_synthetics_genesis_is_clean_under_the_truth_layer_check():
    rows = {r["name"]: r for r in registry.truth_layer_check(REPO)}
    assert "synthetics-genesis" not in rows, (
        "the manifest and the release machine still disagree about whether "
        f"synthetics-genesis has run: {rows.get('synthetics-genesis')}")


def test_j2_this_project_introduces_no_new_truth_layer_conflict():
    rows = {r["name"]: r for r in registry.truth_layer_check(REPO)}
    assert NAME not in rows, rows.get(NAME)


def test_j3_no_fake_release_state_was_written():
    """R11's hard floor: the conflict is never fixed by minting a release sidecar. Neither
    project has one, and this project's own STATE.json rides no release ladder."""
    from laplace.pipeline import release
    for proj in ("synthetics-genesis", NAME):
        base = REPO / "synthetics papers" / proj
        assert not (base / "release" / "state.json").exists()
        assert not (base / "manuscript" / "release" / "state.json").exists()
    doc = json.loads((PROJECT_DIR / "STATE.json").read_text(encoding="utf-8"))
    assert doc.get("state") is None
    assert doc.get("phase") not in release.STATES


def test_j4_the_genesis_row_carries_no_self_contradicting_note():
    """R11: the manifest_note that declared 'no display_name' four lines under the declared
    display_name is dropped; the display_name stays."""
    row = next(r for r in json.loads((REPO / registry.DATA_PROJECTS_FILE)
                                     .read_text(encoding="utf-8"))["projects"]
               if r["name"] == "synthetics-genesis")
    assert row["manifest"].get("display_name")
    assert "no display_name" not in (row.get("manifest_note") or "")


# ---------------------------------------------------------------------------
# the declaration's own hard fails (the builder refuses, it never pours a broken graph)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mutate, needle", [
    (lambda d: d["arc"].update(beats=[]), "no beats"),
    (lambda d: d["arc"]["beats"].append({"node": "def:nowhere"}), "does not build"),
    (lambda d: d["arc"]["beats"].append({"node": "def:the-join"}), "declared twice"),
    (lambda d: d["nodes"][0].update(kind="unmapped-kind"), "not in kind_map"),
    (lambda d: d["kind_map"].update(finding="finding"), "outside LOGICAL_KINDS"),
    (lambda d: d["nodes"][0].update(parent="def:nowhere"), "unknown node"),
    (lambda d: d["edges"][0].update(target="def:nowhere"), "not a declared node"),
    (lambda d: d["nodes"][0].update(ref="THE_STORY_OF_SYNTHETICS.md:999999"), "missing file"),
    # the content anchor's own hard fails: prose that is gone, and a locator that is neither
    (lambda d: d["nodes"][0].update(
        ref=f"{d['nodes'][0]['ref'].rsplit(':', 1)[0]}:@0123456789ab"), "no longer in this source"),
    (lambda d: d["nodes"][0].update(
        ref=f"{d['nodes'][0]['ref'].rsplit(':', 1)[0]}:@notadigest"), "is not"),
    (lambda d: d["nodes"][0].update(projection={"bad": {"nested": 1}}), "not a scalar"),
])
def test_the_builder_hard_fails_rather_than_pouring_a_broken_graph(decl, mutate, needle):
    d = json.loads(json.dumps(decl))
    mutate(d)
    with pytest.raises(BUILD.DeclarationError) as e:
        BUILD.validate(d, REPO)
    assert needle in str(e.value)


@pytest.mark.parametrize("bad_needle", ["a needle that is not in the Story"])
def test_the_compiler_refuses_an_anchor_it_cannot_locate(bad_needle):
    """The compiler's own hard floor: a ref is LOCATED, never typed. A moved source fails
    the compile instead of silently producing a graph pointing at the wrong prose."""
    src = COMPILE.Sources(REPO)
    with pytest.raises(COMPILE.CompileError):
        src.line_of("synthetics papers/synthetics-genesis/THE_STORY_OF_SYNTHETICS.md", bad_needle)
    with pytest.raises(COMPILE.CompileError):
        src.line_of("synthetics papers/synthetics-genesis/THE_STORY_OF_SYNTHETICS.md", "the")


# ---------------------------------------------------------------------------
# the price-pair sidecar (ruling R6)
# ---------------------------------------------------------------------------

def test_the_price_pair_sidecar_is_two_typed_prices_never_summed(decl):
    rows = [json.loads(ln) for ln in
            (PROJECT_DIR / "prices.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) == 2
    schema, birth = rows
    assert schema["kind"] == "schema" and schema["price_recipe_version"] == "v0-provisional"
    assert "NEVER SUMMED" in schema["_"]
    assert birth["event"] == "birth"
    assert set(birth["price_counting"]) >= {"nodes", "edges", "beats"}
    assert set(birth["price_authority"]) >= {"imported_literature_refs"}
    # the counting price is the graph it actually priced
    assert birth["price_counting"]["nodes"] == 1 + len(decl["nodes"])
    assert birth["price_counting"]["beats"] == len(decl["arc"]["beats"])
    # ... and `edges` is the count the READER gets, not the count the compiler wrote. The
    # emitter keys an edge on (node, target, AXIS), so two declared relations that rel_map
    # sends to one axis arrive as ONE edge. Billing the declared number would overstate the
    # counting price — a census defect in the one artefact whose subject IS the price of
    # counting. Both numbers are carried and the collapsing pairs are named.
    distinct = {(e["node"], e["target"], e["axis"]) for e in decl["edges"]}
    assert birth["price_counting"]["edges"] == len(distinct)
    assert birth["price_counting"]["edges_declared"] == len(decl["edges"])
    collapsed = birth["price_counting"]["edges_collapsed_by_axis"]
    assert len(decl["edges"]) - len(distinct) == len(collapsed), (
        f"the declared/served gap is {len(decl['edges']) - len(distinct)} but "
        f"{len(collapsed)} collapsing pairs are named")
    for line in collapsed:
        node, rest = line.split(" -> ", 1)
        target = rest.split(" [", 1)[0]
        assert sum(1 for e in decl["edges"]
                   if e["node"] == node and e["target"] == target) > 1, line


def test_the_counting_price_equals_the_edges_the_corpus_serves(door_root: Path, decl):
    """The census the price sidecar bills is the census the read layer hands back."""
    rows = [json.loads(ln) for ln in
            (PROJECT_DIR / "prices.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    birth = rows[1]
    ei = _net(door_root).get("edge_index", {})
    declared_nodes = {decl["goal"]["id"]} | {n["id"] for n in decl["nodes"]}
    # an edge_index entry lists, per node, the bare targets AND one TYPED token per served
    # edge; the typed tokens are the edges, one apiece.
    served = sum(len({tok for tok in toks if "::" in tok})
                 for node, toks in ei.items() if node in declared_nodes)
    assert birth["price_counting"]["edges"] == served, (
        f"the sidecar bills {birth['price_counting']['edges']} edges; the corpus serves "
        f"{served} out of the declaration's nodes")
    assert birth["price_authority"]["imported_literature_refs"] == sum(
        1 for n in decl["nodes"] if n["id"].startswith("ref:"))
    # no total: summing them would presuppose the exchange rate this project records as open
    for row in rows:
        assert "price_total" not in row and "total" not in row


# ---------------------------------------------------------------------------
# (k) — no essence may carry THE_STORY's prose
# ---------------------------------------------------------------------------
#: The threshold the review PRE-REGISTERED when it measured the leak. The compiler's own gate
#: sits tighter (``COMPILE.MAX_VERBATIM_RUN``); this clause is the independent floor, measured
#: on what was actually emitted rather than on what the compiler believes it emitted.
PREREGISTERED_RUN_LIMIT = 12


def _story_words() -> list[str]:
    return COMPILE._words(STORY.read_text(encoding="utf-8"))


def test_k_no_essence_carries_a_verbatim_run_of_his_prose(decl):
    """THE_STORY is his and stays in its own file: every node carries a ``<path>:<line>`` ref
    INTO it, and the essence beside that ref must be an authored description, not an elision
    of the paragraph it points at. Measured, because the first build asserted this in a
    docstring and shipped 37 essences carrying >=8-word runs."""
    words = _story_words()
    offenders = []
    for n in [decl["goal"], *decl["nodes"]]:
        run, span = COMPILE.longest_verbatim_run(n["essence"], words)
        if run >= PREREGISTERED_RUN_LIMIT:
            offenders.append(f"{n['id']}: {run}-word run {span!r}")
    assert offenders == [], "essences carrying THE_STORY's prose:\n  " + "\n  ".join(offenders)


def test_k2_the_ledger_carries_the_same_essences_the_declaration_declares(records, decl):
    """The leak is not confined to the declaration: the emitted add-node records carry the
    essence strings too, so anything sweeping ``corpus_friction/`` or the project dir carries
    whatever they carry. Pinning them equal makes clause (k) bind on both surfaces at once."""
    emitted = {r["node"]: r["essence"] for r in records if r.get("kind") == "add-node"}
    for n in decl["nodes"]:
        # the emitter appends the node's own source pointer to the essence it carries
        assert emitted.get(n["id"]) == f"{n['essence']} · src:{n['ref']}", n["id"]
    words = _story_words()
    for nid, essence in emitted.items():
        run, span = COMPILE.longest_verbatim_run(essence, words)
        assert run < PREREGISTERED_RUN_LIMIT, f"{nid}: {run}-word run {span!r} in the LEDGER"


def test_k3_the_compiler_refuses_an_essence_stitched_out_of_his_paragraph():
    """The mechanism, not just the state: plant a Story sentence as an essence and the
    compiler must hard-fail rather than emit it."""
    src = COMPILE.Sources(REPO)
    story_line = next(ln for ln in src.lines(str(STORY.relative_to(REPO)))
                      if "Paying debts down" in ln)
    planted = {"id": "res:planted-leak", "essence": story_line}
    with pytest.raises(COMPILE.CompileError) as exc:
        COMPILE.check_no_story_prose(src, planted, [])
    assert "verbatim run" in str(exc.value)
    # and the honest form of the same node passes
    COMPILE.check_no_story_prose(
        src, {"id": "res:planted-leak",
              "essence": "Retiring debt is the sole revision behaviour here that gets "
                         "cheaper the more it is repeated."}, [])


def test_k4_the_compilers_gate_is_tighter_than_the_pre_registered_clause():
    assert COMPILE.MAX_VERBATIM_RUN <= PREREGISTERED_RUN_LIMIT, (
        "the compiler must refuse strictly more than the door clause measures, or a "
        "regression lands in the artefact before any test sees it")
