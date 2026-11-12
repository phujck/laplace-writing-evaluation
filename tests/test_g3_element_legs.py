"""G3 — the element legs. The three legs of the growth-stage arming's element base,
each landed as the typed edge (minted through schema.token_for), the epistemic write
through the one home (schema.canonical_status), and its tests:

  1. LITERATURE — the picker mint carries its claim (add-node born supports edge);
     admission stops discarding the proven link (the entailed-claim supports edge +
     the set-status write through the one home, with an honest unresolved marker).
  2. RESULTS — _VALREF reaches falqon's readings:*/ledger:* pointers WITH a
     dereference check into numerics/*.json; claim->validation mints validates-axis
     tokens; the registry gains the evidence_store door.
  3. DEMONSTRATIONS — a figure's link to the result it demonstrates is a typed
     demonstrates-axis edge, the fig: gate widened where safe, exposed on the asset.

Every new edge is minted through schema.token_for; every epistemic write folds
through schema.canonical_status; the subset-sum-itqde build is proven inert by the
G1 round-trip (nothing moves until a new writer runs).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.pipeline import citation_direction as cd
from laplace.pipeline import gap_ledger as GL
from laplace.pipeline import asset_model as am
from laplace.pipeline import registry
from laplace.pipeline import schema

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import ingest_synthetic as ing  # noqa: E402


def _mini_corpus(tmp_path: Path) -> Path:
    """A minimal atomisable paper: main.tex -> one section with one equation."""
    tex = tmp_path / "tex"
    tex.mkdir()
    (tex / "main.tex").write_text(r"\input{s1}", encoding="utf-8")
    (tex / "s1.tex").write_text(
        "\\section{Intro}\\label{sec:intro}\n"
        "\\begin{equation}\\label{eq:one} a=b \\end{equation}\n",
        encoding="utf-8")
    return tex


# ============================================================ 1. LITERATURE

def test_add_node_born_supports_edge_is_typed(tmp_path):
    """1a — a citation minted from a node-scoped search: an add-node carrying an
    ``axis`` types its BORN edge, so a ref: node lands WITH a supports edge to its
    originating claim node (minted through the one home)."""
    tex = _mini_corpus(tmp_path)
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "ref:someKey2020",
                                  "node_kind": "citation", "parent": "references",
                                  "target": "eq:one", "axis": "supports"})
    net = ci.corpus_network(tex, tmp_path, "c")
    row = net["edge_index"]["ref:someKey2020"]
    assert "eq:one" in row                                # the plain referent
    assert "supports::eq:one" in row                      # the TYPED supports edge
    assert schema.parse_edge_token("supports::eq:one") == {"axis": "supports",
                                                           "target": "eq:one"}


def test_add_node_untyped_born_edge_is_byte_identical(tmp_path):
    """1a — no axis on the add-node keeps the human-confirmed derives token, exactly
    the prior wire (an existing add-node never moves)."""
    tex = _mini_corpus(tmp_path)
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "res:x",
                                  "node_kind": "result", "essence": "r",
                                  "parent": "sec:intro", "target": "eq:one"})
    net = ci.corpus_network(tex, tmp_path, "c")
    row = net["edge_index"]["res:x"]
    assert "confirmed::eq:one" in row
    assert not any(t.startswith("supports::") for t in row)


def test_rewire_add_threads_axis_on_add_node(tmp_path):
    r = ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "ref:k",
                                      "node_kind": "citation", "parent": "references",
                                      "target": "eq:one", "axis": "supports"})
    assert r.get("ok") and r["record"]["axis"] == "supports"


def test_resolve_claim_node_from_gap_ledger_intent_else_none():
    """1b — a gap-ledger literature intent rides its originating node; a
    manuscript-scanned intent carries no conceptric node id (honestly None)."""
    ledger = cd.LiteratureIntent(id="RI-1", key="res:foo", claim="c",
                                 claim_node="res:foo")
    assert cd.resolve_claim_node(ledger) == "res:foo"
    scanned = cd.LiteratureIntent(id="RI-2", key="gamma2019", claim="c", section="s1")
    assert cd.resolve_claim_node(scanned) is None
    # a bare section stem / non-node where never resolves
    assert cd.resolve_claim_node(
        cd.LiteratureIntent(id="RI-3", key="k", claim="c", claim_node="s5")) is None


def test_load_ledger_intents_threads_claim_node(tmp_path):
    """1b — the research-intent ledger's ``node`` (the gap's ``where``) threads onto
    ``claim_node`` when it is a real conceptric node id, else stays empty."""
    mdir = tmp_path / "m"
    mdir.mkdir()
    ledger = mdir / "research_intents.jsonl"
    ledger.write_text(
        json.dumps({"id": "RI-LIT-a", "research_class": "literature", "key": "a",
                    "issue": "ungrounded claim", "node": "res:foo"}) + "\n"
        + json.dumps({"id": "RI-LIT-b", "cls": "literature", "key": "b",
                      "note": "no node id", "node": "source-vs-projection"}) + "\n",
        encoding="utf-8")
    intents = {i.id: i for i in cd.load_ledger_intents(ledger)}
    assert intents["RI-LIT-a"].claim_node == "res:foo"
    assert intents["RI-LIT-b"].claim_node == ""          # sentinel is not a node


def test_admission_writes_the_supports_edge_and_status_through_one_home(tmp_path):
    """1b/1c — admission no longer discards the proven link: a resolvable claim node
    yields a supports-axis add-edge (token minted through the one home, verdict ref
    carried) AND a set-status op carrying the CANONICAL enum value (cited->imported)."""
    mdir = tmp_path / "m"
    mdir.mkdir()
    (mdir / "refs.bib").write_text("", encoding="utf-8")
    it = cd.LiteratureIntent(id="RI-LIT-res:foo", key="alpha2020",
                             claim="the grounded claim", claim_node="res:foo")
    cand = cd.Candidate("arxiv:1", "Alpha", 2019, ["A"], "arxiv", abstract="proves it")
    res = cd.apply_admission(mdir, it, cand,
                             {"ruling": "ENTAILS", "id": "PV-1"})
    assert res["admitted"] is True
    # the supports edge — typed, minted through token_for, carrying the verdict
    se = res["support_edge"]
    assert se["kind"] == "add-edge" and se["axis"] == "supports"
    assert se["node"] == "ref:alpha2020" and se["target"] == "res:foo"
    assert se["token"] == schema.token_for("supports", "res:foo") == "supports::res:foo"
    assert se["entailment_verdict_ref"] == "PV-1"
    assert res["entailed_claim"] == "res:foo"
    # the epistemic stamp writes through the one home: cited -> imported (canonical)
    st = res["status_edge"]
    assert st["kind"] == "set-status" and st["node"] == "ref:alpha2020"
    assert st["value"] == "imported" == schema.canonical_status("cited")
    # the node record STILL carries its private epistemic field (unchanged) + the
    # resolved entailed-claim marker
    assert res["node"]["epistemic"] == "cited"
    assert res["node"]["entailed_claim"] == "res:foo"


def test_admission_banks_honest_unresolved_marker_never_a_silent_drop(tmp_path):
    """1b — where the entailed claim cannot be resolved to a node, the citation node
    banks the honest ``unresolved`` marker and no supports edge is fabricated."""
    mdir = tmp_path / "m"
    mdir.mkdir()
    (mdir / "refs.bib").write_text("", encoding="utf-8")
    it = cd.LiteratureIntent(id="RI-1", key="gamma2019", claim="a claim", section="s1")
    cand = cd.Candidate("arxiv:2", "Gamma", 2019, ["G"], "arxiv", abstract="x")
    res = cd.apply_admission(mdir, it, cand, {"ruling": "ENTAILS", "id": "PV-2"})
    assert res["admitted"] is True
    assert res["support_edge"] is None                    # no fabricated edge
    assert res["entailed_claim"] == "unresolved"
    assert res["node"]["entailed_claim"] == "unresolved"  # marked, never dropped
    # the epistemic write still fires (it does not depend on claim resolution)
    assert res["status_edge"]["value"] == "imported"


def test_supports_edge_record_applies_as_a_typed_edge(tmp_path):
    """1b integration — the admission's supports add-edge record, landed on the
    friction ledger, mints supports::<claim> on the citation node at build time
    (through apply_overlay's one-home mint)."""
    tex = _mini_corpus(tmp_path)
    # a claim node + a citation node, then the supports edge admission would emit
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "res:foo",
                                  "node_kind": "result", "essence": "r",
                                  "parent": "sec:intro"})
    ci.rewire_add(tmp_path, "c", {"kind": "add-node", "node": "ref:alpha2020",
                                  "node_kind": "citation", "parent": "references"})
    ci.rewire_add(tmp_path, "c", {"kind": "add-edge", "node": "ref:alpha2020",
                                  "target": "res:foo", "axis": "supports"})
    net = ci.corpus_network(tex, tmp_path, "c")
    assert "supports::res:foo" in net["edge_index"]["ref:alpha2020"]


def _judged_manuscript(tmp_path: Path, claim_node: str) -> Path:
    """A manuscript with one pending entailment manifest whose intent carries
    ``claim_node``, plus the corpus_friction dir the consumer writes to."""
    mdir = tmp_path / "proj" / "manuscript"
    out = mdir / "citation_direction"
    out.mkdir(parents=True)
    (tmp_path / "proj").parent  # noqa
    (tmp_path / "corpus_friction").mkdir()
    (mdir / "refs.bib").write_text("", encoding="utf-8")
    packet = {"decision": {"kind": "citation-entailment", "candidate": {
        "cand_id": "cited:alpha2020", "title": "Alpha", "abstract": "proves it",
        "year": 2019, "authors": ["A"], "provenance": "cited-source",
        "has_abstract": True}}, "bank": cd.BANK_CONTRACT}
    man = {"kind": "citation-entailment-adjudication", "schema": 2, "count": 1,
           "cut_at": "2026-07-22T10:00:00",
           "frame": {"entailment_law": cd.ENTAILMENT_LAW,
                     "intent": {"id": "RI-A", "key": "alpha2020",
                                "claim": "the grounded claim", "section": "s1",
                                "lane": cd.INTENT_DANGLING, "claim_node": claim_node}},
           "bank_contract": cd.BANK_CONTRACT, "packets": [packet]}
    (out / "entailment_manifest.ri-a.json").write_text(json.dumps(man), encoding="utf-8")
    (out / "run_record.json").write_text(json.dumps({
        "organ": "citation_direction", "ran_at": "2026-07-22T10:00:00",
        "intents_n": 1, "candidates_total": 1,
        "buckets": {"admitted": 0, "needs-judge": 1, "rejected": 0, "no-candidate": 0},
        "by_intent": [{"intent_id": "RI-A", "lane": "dangling", "bucket": "needs-judge"}]}),
        encoding="utf-8")
    return mdir


def test_consume_lands_status_and_supports_on_the_ledger_node_last(tmp_path):
    """1b/1c — consuming an ENTAILS verdict lands the set-status (imported) and the
    supports edge (to the resolved claim) on the friction ledger, with the
    citation-node record kept as the LAST row (the reader/friction invariant)."""
    mdir = _judged_manuscript(tmp_path, claim_node="res:foo")
    verdicts = {"verdicts": [{"intent_id": "RI-A", "rulings": [
        {"cand_id": "cited:alpha2020", "ruling": "ENTAILS", "evidence": "states it"}]}]}
    cd.consume_verdicts(mdir, verdicts, project="proj")
    ledger = tmp_path / "corpus_friction" / "proj.jsonl"
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
    kinds = [r.get("kind") for r in rows]
    assert "set-status" in kinds and "add-edge" in kinds
    status = next(r for r in rows if r.get("kind") == "set-status")
    support = next(r for r in rows if r.get("kind") == "add-edge")
    assert status["value"] == "imported"
    assert support["axis"] == "supports" and support["target"] == "res:foo"
    # the citation-node record is the LAST row (aux records land before it)
    assert rows[-1]["epistemic"] == "cited" and rows[-1]["cite_key"] == "alpha2020"
    assert rows[-1]["entailed_claim"] == "res:foo"


def test_gap_ledger_epistemic_folds_through_the_one_home():
    """1c — a research intent's surfaced epistemic is ALWAYS a canonical enum member
    (the carrier can never drift from the enum); the gap's own record keeps the raw
    carrier as provenance."""
    findings = [
        {"kind": "promise-figure-absent", "where": "s7", "section": "s7", "issue": "f"},
        {"kind": "promise-citation-absent", "where": "s4", "section": "s4", "issue": "c"},
        {"kind": "source-motivation-lost", "where": "source-vs-projection",
         "issue": "m", "quote": "lost span"},
        {"kind": "float-orphan", "where": "s3", "section": "s3", "issue": "o"},
    ]
    gaps = GL.compile_gaps(findings)
    GL.probe_quarry(gaps, lambda g: 0.1)          # all substrate-absent
    GL.retype_substrate_absent(gaps)
    ris = {r["research_class"]: r for r in GL.to_research_intents(gaps, project="p")}
    # every surfaced epistemic is a canonical enum member
    for r in ris.values():
        assert r["epistemic"] in schema.EPISTEMIC_STATUSES
        assert schema.canonical_status(r["epistemic"]) == r["epistemic"]
    # the specific folds
    assert ris["literature"]["epistemic"] == "imported"        # cited -> imported
    assert ris["computation"]["epistemic"] == "computed"
    assert ris["novel"]["epistemic"] == "conjectured"
    assert ris["source-recoverable"]["epistemic"] == "exploratory"  # mined -> exploratory
    # the gap's raw carrier is preserved (the field-reading contract is untouched)
    assert ris["literature"]["gap"]["epistemic"] == "cited"
    assert ris["source-recoverable"]["gap"]["epistemic"] == "mined"


# ============================================================ 2. RESULTS

def test_valref_matches_the_three_pointer_families():
    block = ("ledger:lattice_x; readings:resource:headline[0].T_gates_per_layer (33900.0); "
             "readings:witness:cancellation.rows[0]; readings:resource:sweeps.layers[0..2]; "
             "validation/data/foo.json; bar_summary.csv")
    found = set(m for m in ing._VALREF.findall(block) if m)
    assert "ledger:lattice_x" in found
    assert "readings:resource:headline[0].T_gates_per_layer" in found   # annotation stripped
    assert "readings:witness:cancellation.rows[0]" in found
    assert "readings:resource:sweeps.layers[0..2]" in found
    assert "validation/data/foo.json" in found                          # legacy still matches
    assert "bar_summary.csv" in found


def test_deref_keypath_shapes_and_misses():
    root = {"headline": [{"depth": 339.0}], "ratios": {"x": 1.0},
            "sweeps": {"layers": [1, 2, 3]}, "flat": 0.0}
    assert ing._deref_keypath(root, "flat") is True
    assert ing._deref_keypath(root, "headline[0].depth") is True
    assert ing._deref_keypath(root, "ratios.x") is True
    assert ing._deref_keypath(root, "sweeps.layers[0..2]") is True      # inclusive range
    # misses -> dangling, never a raise
    assert ing._deref_keypath(root, "headline[9].depth") is False       # out of range
    assert ing._deref_keypath(root, "sweeps.layers[0..9]") is False     # range overruns
    assert ing._deref_keypath(root, "no_such_key") is False
    assert ing._deref_keypath(root, "flat.deeper") is False             # not a dict
    assert ing._deref_keypath(root, "ratios[0]") is False               # not a list


def _synth_fixture(tmp_path: Path) -> Path:
    """A minimal synthetic project with a numerics store: one claim with a resolving
    readings pointer and one dangling readings pointer."""
    proj = tmp_path / "synth"
    (proj / "inputs").mkdir(parents=True)
    (proj / "literature").mkdir()
    (proj / "numerics").mkdir()
    (proj / "literature" / "references.bib").write_text(
        "@article{x2020,\n title={T},\n year={2020},\n}\n", encoding="utf-8")
    (proj / "numerics" / "resource_readings.json").write_text(
        json.dumps({"headline": [{"depth": 339.0}]}), encoding="utf-8")
    (proj / "inputs" / "evidence_ledger.md").write_text(
        "| id | claim | source | status | note |\n"
        "|---|---|---|---|---|\n"
        "| CLM-001 | Depth is live. | readings:resource:headline[0].depth; "
        "readings:resource:headline[9].ghost | numerical_check | n |\n",
        encoding="utf-8")
    return proj


def test_build_partitions_live_validation_and_mints_validates_tokens(tmp_path):
    """2 — a resolving readings pointer is a LIVE claim->validation edge that mints a
    validates-axis token; a non-resolving one lands as a dangling-evidence row, never
    silently live."""
    proj = _synth_fixture(tmp_path)
    _regraded, edges = ing.build(proj, "synth")
    assert edges["claim_to_validation"]["CLM-001"] == [
        "readings:resource:headline[0].depth"]            # the live one only
    assert edges["dangling_evidence"]["CLM-001"] == [
        "readings:resource:headline[9].ghost"]            # the miss, surfaced
    tok = edges["validates"]["CLM-001"]
    assert tok == [schema.token_for("validates", "readings:resource:headline[0].depth")]
    assert schema.parse_edge_token(tok[0])["axis"] == "validates"


def test_registry_gains_evidence_store_door():
    """2 — the Project record carries an optional evidence_store; falqon registers its
    numerics dir; every other row defaults empty (additive, no behavior change)."""
    assert hasattr(registry.Project("x"), "evidence_store")
    assert registry.Project("x").evidence_store == ""
    projs = registry.all_projects()
    assert projs["paper_falqon"].evidence_store == "paper_falqon/numerics"
    assert projs["subset-sum-itqde"].evidence_store == ""   # unchanged rows stay empty


@pytest.mark.skipif(not (REPO / "paper_falqon" / "numerics" /
                         "resource_readings.json").is_file(),
                    reason="paper_falqon numerics absent")
def test_falqon_pour_yields_live_validates_edges():
    """2 — the real falqon ledger, whose readings:*/ledger:* pointers _VALREF could
    not reach before, now yields real claim->validation edges + validates tokens."""
    _regraded, edges = ing.build(REPO / "paper_falqon", "paper_falqon")
    n_val = sum(len(v) for v in edges["validates"].values())
    assert n_val > 0                                       # was 0 before this leg
    assert n_val == sum(len(v) for v in edges["claim_to_validation"].values())
    # every minted token is a real validates-axis edge
    for toks in edges["validates"].values():
        for t in toks:
            assert (schema.parse_edge_token(t) or {}).get("axis") == "validates"


# ============================================================ 3. DEMONSTRATIONS

def test_asset_object_round_trips_demonstrates():
    obj = am.AssetObject(
        id="figure:F1", kind="figure", project="p",
        nodes_supported=["res:x", "res:y"],
        demonstrates=["demonstrates::res:x"])
    back = am.AssetObject.from_json(obj.to_json())
    assert back.demonstrates == ["demonstrates::res:x"]
    assert back.to_dict() == obj.to_dict()


def _demo_ledger(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "corpus_friction"
    p.mkdir()
    f = p / "demo.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return f


def test_ledger_enrichment_types_demonstrates_and_widens_the_gate(tmp_path, monkeypatch):
    """3 — a fig->target edge typed axis=demonstrates mints a demonstrates token; an
    UNTYPED fig edge stays in nodes_supported only; the gate WIDENS past the hard
    fig: prefix for an explicit demonstrates edge; a non-demonstrates non-fig edge is
    untouched."""
    ledger = _demo_ledger(tmp_path, [
        {"kind": "add-edge", "node": "fig:demo", "target": "res:a", "axis": "demonstrates"},
        {"kind": "add-edge", "node": "fig:deco", "target": "res:b"},          # untyped
        {"kind": "add-edge", "node": "res:widefig", "target": "res:c", "axis": "demonstrates"},
        {"kind": "add-edge", "node": "res:plain", "target": "res:d"},         # ignored
    ])
    monkeypatch.setattr(am, "_ledger_path", lambda name: ledger)
    enr = am._load_ledger_enrichment("demo")
    supp, dem = enr["supported_by_node"], enr["demonstrated_by_node"]
    # the typed fig edge: in BOTH nodes_supported and the demonstrates map (as a token)
    assert supp["fig:demo"] == ["res:a"]
    assert dem["fig:demo"] == [schema.token_for("demonstrates", "res:a")]
    assert dem["fig:demo"] == ["demonstrates::res:a"]
    # the UNTYPED fig edge: nodes_supported only — a decorating link, not demonstrates
    assert supp["fig:deco"] == ["res:b"]
    assert "fig:deco" not in dem
    # WIDENED: a non-fig node explicitly typed demonstrates registers (a figure whose
    # id is not fig:-prefixed still records its demonstration)
    assert dem["res:widefig"] == ["demonstrates::res:c"]
    # a plain non-fig, non-demonstrates edge is untouched (not a figure)
    assert "res:plain" not in supp and "res:plain" not in dem


def test_discover_figures_exposes_demonstrates(tmp_path):
    """3 — a figure whose node carries demonstrates edges exposes them; the
    demonstrates list distinguishes it from a decorating figure."""
    figdir = tmp_path / "figs"
    figdir.mkdir()
    (figdir / "fig_demo.tex").write_text("\\begin{tikzpicture}\\end{tikzpicture}",
                                         encoding="utf-8")
    roots = am.AssetRoots(figures=(str(figdir),), figure_producer="hand-tikz")
    ledger = {"by_generator_basename": {},
              "supported_by_node": {"fig:demo": ["res:a"]},
              "demonstrated_by_node": {"fig:demo": ["demonstrates::res:a"]}}
    figs = am._discover_figures("demo", roots, {}, "", ledger)
    assert len(figs) == 1
    a = figs[0]
    assert a.node_id == "fig:demo"
    assert a.nodes_supported == ["res:a"]
    assert a.demonstrates == ["demonstrates::res:a"]       # a demonstrating figure
    assert schema.parse_edge_token(a.demonstrates[0])["axis"] == "demonstrates"


def test_demonstrates_tokens_all_mint_through_the_one_home(tmp_path, monkeypatch):
    ledger = _demo_ledger(tmp_path, [
        {"kind": "add-edge", "node": "fig:a", "target": "res:x", "axis": "demonstrates"},
        {"kind": "add-edge", "node": "fig:b", "target": "res:y", "axis": "demonstrates"},
    ])
    monkeypatch.setattr(am, "_ledger_path", lambda name: ledger)
    dem = am._load_ledger_enrichment("demo")["demonstrated_by_node"]
    for toks in dem.values():
        for t in toks:
            assert (schema.parse_edge_token(t) or {}).get("axis") == "demonstrates"
