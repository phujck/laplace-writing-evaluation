"""The DESIGN conceptric, enforced (PRM-20260721-design-conceptric).

The interface-overhaul design is authored as a conceptric-class object — a corpus
friction ledger (``corpus_friction/design-interface.jsonl``) that reconstructs through
the SAME house down-operators the /conceptric surface serves (corpus_ingest.corpus_network
-> conceptric.dag_map / neighborhood). This suite pins:

  * the store parses in the house shape (typed rewire records, plus the unified
    friction channel riding the same spine; add-node kinds are LOGICAL_KINDS; the
    network reconstructs);
  * every edge endpoint resolves to a real node;
  * every node carries a source ref (file+lines) — the refs-only house law;
  * the builder is idempotent (two runs -> a byte-identical ledger);
  * the census matches the design doc (10 principles, the acts, the open interface
    promises) and the RED clause count is self-consistent with the live sources.

RED is a LIVE contract attribute: a wave flips a marker green on delivery, so the red
clause count MOVES during the overhaul. The suite therefore asserts the clause count
equals a fresh recompute from the sources (never a frozen number) — the conceptric is
rebuilt when the sources move, by design.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "corpus_friction" / "design-interface.jsonl"
TEX_ROOT = REPO / "design_conceptric" / "manuscript"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_design_conceptric", REPO / "scripts" / "build_design_conceptric.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BUILD = _load_builder()


@pytest.fixture(scope="module")
def records() -> list[dict]:
    assert LEDGER.is_file(), (
        "corpus_friction/design-interface.jsonl absent — run "
        "scripts/build_design_conceptric.py")
    out = []
    for ln in LEDGER.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            out.append(json.loads(ln))
    return out


@pytest.fixture(scope="module")
def build_records() -> list[dict]:
    recs, _census = BUILD.build_records(REPO)
    return recs


@pytest.fixture(scope="module")
def build_block(records) -> list[dict]:
    """The BUILDER'S OWN rows on the on-disk ledger, and only those.

    The ledger is no longer builder-only: ``corpus_ingest.rewire_add`` is a sanctioned door and
    lanes deposit through it (the 2026-08-20 campaign-requirements block is 157 rows with its own
    node kinds and its own edge relations). The builder's invariants — the design doc's counts,
    the five typed relations, the ref-on-every-node law — are properties of what the BUILDER
    emits, so they are asserted against its block; a foreign row is held to the door's schema
    instead (test_store_is_typed_rewire_records, test_foreign_rows_carry_their_source).
    Scoring a door deposit as builder output is the same category error the builder's own
    order bug was (WO-20260820-rewire-append-drifts-the-builder), one layer up."""
    return [r for r in records if r.get("by") == BUILD.BUILD_TAG]


@pytest.fixture(scope="module")
def census() -> dict:
    _recs, c = BUILD.build_records(REPO)
    return c


@pytest.fixture(scope="module")
def net():
    import sys
    sys.path.insert(0, str(REPO / "src"))
    from laplace.research import corpus_ingest as ci
    return ci.corpus_network(TEX_ROOT, repo_root=REPO, name=BUILD.CORPUS)


# ---------------------------------------------------------------------------
# the store parses in the house shape
# ---------------------------------------------------------------------------

def test_store_is_typed_rewire_records(records):
    """The builder's own block is add-node/add-edge only. The ledger ALSO carries
    the unified friction channel (schema.FRICTION_KINDS: an engine ``friction``, an
    author ``fork``) — one spine, class told by ``kind``, deposited through
    corpus_ingest.friction_add and preserved by the builder's ``emit`` (every row
    whose ``by`` is not BUILD_TAG is kept, on the side of the rebuilt block it was
    written on — see ``split_foreign``). So the admitted
    set is derived from the schema, not frozen at the two build kinds; friction rows
    are held to the write gate's shape instead."""
    from laplace.research import corpus_ingest as ci
    from laplace.pipeline.schema import FRICTION_KINDS

    from laplace.pipeline.schema import REWIRE_KINDS
    build_kinds = {r["kind"] for r in records if r["kind"] not in FRICTION_KINDS}
    # the set is the SCHEMA'S (the docstring's own law): the ledger now legitimately
    # carries set-spine (the proposed spine), edit-essence (the mutable rename) and
    # any other sanctioned-door kind - frozen-at-two was the drift, not the deposit.
    assert build_kinds <= set(REWIRE_KINDS), (
        f"unexpected record kinds: {build_kinds - set(REWIRE_KINDS)}")
    for r in records:
        assert r.get("node"), f"record with no node: {r}"
        if r["kind"] in FRICTION_KINDS:
            # friction_add's required fields — a raw append would admit any dict
            assert r.get("owning_layer"), f"{r['id']}: friction row with no owning_layer"
            assert r.get("status"), f"{r['id']}: friction row with no status"
            chain = r.get("chain")
            assert chain is None or (
                isinstance(chain, list) and chain
                and all(isinstance(f, str) and f.strip() for f in chain)), (
                f"{r['id']}: chain is not a non-empty list of non-empty strings")
        if r["kind"] == "add-node":
            assert r["node_kind"] in ci.LOGICAL_KINDS, (
                f"{r['node']}: node_kind {r['node_kind']!r} not in LOGICAL_KINDS "
                "(the add-node gate's taxonomy)")


def test_network_reconstructs_in_house_shape(net):
    from laplace.research import corpus_ingest as ci
    assert net["nodes"], "the corpus network reconstructed no nodes"
    assert net["root"] == "paper://"
    m = ci.dag_map(net)
    assert m["nodes"] and m["edges"], "the derivation DAG is empty"
    # every design node is provenance-clean: no confabulation gaps (the postulates/
    # support are exempt, the results carry a derives-from edge).
    assert m["n_gaps"] == 0, f"unexpected derivation gaps: {ci.gaps(net)}"


# ---------------------------------------------------------------------------
# every edge endpoint exists · every node carries a source ref
# ---------------------------------------------------------------------------

def test_every_edge_endpoint_is_a_real_node(records):
    node_ids = {r["node"] for r in records if r["kind"] == "add-node"} | {"paper://", "references"}
    for e in (r for r in records if r["kind"] == "add-edge"):
        assert e["node"] in node_ids, f"edge from unknown node {e['node']}"
        assert e["target"] in node_ids, f"edge to unknown node {e['target']}"
        assert e.get("value"), f"edge {e['node']}->{e['target']} has no typed relation"


def test_every_node_carries_a_source_ref(build_block):
    for r in (x for x in build_block if x["kind"] == "add-node"):
        assert r.get("ref"), f"{r['node']}: no source ref (file+lines)"
        assert ":" in r["ref"] or "#" in r["ref"], (
            f"{r['node']}: ref {r['ref']!r} is not a file+lines / file#id locator")
        # refs-only: the ref also rides the essence so the RENDERED node shows it
        assert "src:" in (r.get("essence") or ""), f"{r['node']}: essence drops the src ref"


def test_every_builder_ref_names_content_not_an_offset(build_block):
    """WHAT A REF STORES (2026-08-21). Every source here grows by insertion — a promise row
    appended, a principle added above another, a clause moving down its yaml — so a stored
    LINE NUMBER made each of those an edit to every ref below it: the ledger drifted, --check
    went red, and a set of nodes nobody had touched reported as changed. The builder still
    LOCATES (that is unchanged, and a needle it cannot find is now refused rather than
    emitted as `<file>:0`), but it stores the located CONTENT: `<path>:@<digest>`. The two
    id-locator refs (`<path>#<id>`) were already content-keyed and stay as they are.

    This clause is what stops the offset coming back: it resolves every ref against the tree,
    so a ref whose prose was rewritten fails here too."""
    from laplace.manuscript import source_anchor as sa
    for r in (x for x in build_block if x["kind"] == "add-node"):
        ref = r["ref"]
        if "#" in ref and ":" not in ref:
            assert (REPO / ref.split("#", 1)[0]).is_file(), f"{r['node']}: {ref}"
            continue
        path, locator = sa.parse_ref(ref)
        assert sa.is_content_anchor(locator), (
            f"{r['node']} stores the offset {locator!r} into {path} — a line number drifts "
            f"on any insertion above it; store the content (_anchor)")
        sa.resolve(ref, REPO)      # raises if the anchored prose is gone or ambiguous


def test_foreign_rows_carry_their_source(records):
    """The refs-only law holds at the DOOR too — a node deposited through
    ``corpus_ingest.rewire_add`` must still name where it came from.

    It may do so either way: as the ``ref`` FIELD (the builder's shape — admitted through the
    door only since WO-20260820-rewire-append-drifts-the-builder added ``ref`` to rewire_add's
    extras allowlist) or folded into the essence as ``src:``, which is what every one of the 75
    existing door-deposited nodes had to do while the field was being dropped. Both satisfy the
    law; neither is optional."""
    foreign = [r for r in records
               if r.get("by") != BUILD.BUILD_TAG and r["kind"] == "add-node"]
    for r in foreign:
        located = bool(r.get("ref")) or "src:" in (r.get("essence") or "")
        assert located, (
            f"{r['node']}: door-deposited node names no source — put it on the `ref` field "
            "(rewire_add carries it now) or fold it into the essence as src:")


def test_all_five_typed_edge_relations_present(build_block):
    """SCHEMA validity is invariant (no foreign relation ever appears); relation
    PRESENCE tracks the live sources. Four relations are always instanced given the
    design doc + the open-promise ledger (waves, acts, evidence, amendments all exist).
    clause-enforces-principle is DATA-GATED: the builder emits a clause node only for a
    RED (owed) clause, and RED is live — a wave flips its markers green on delivery, so
    the owed set legitimately reaches zero (W-desk cleared its count clauses mid-wave).
    So that relation is present IFF there are live RED clauses — never frozen as always-on,
    or the conceptric that 'stops rotting' would go red the moment the overhaul it tracks
    succeeds (P2: every number == its filter, including a count that filters to zero)."""
    valid = {"wave-delivers-promise", "clause-enforces-principle", "wave-fills-act",
             "evidence-substantiates-act", "amendment-amends-principle"}
    seen = {r["value"] for r in build_block if r["kind"] == "add-edge"}
    # schema: no relation outside the five typed kinds ever appears (always holds)
    assert seen <= valid, f"unexpected edge relations: {seen - valid}"
    # presence: the always-instanced four, plus clause-enforces-principle iff RED clauses
    expected = {"wave-delivers-promise", "wave-fills-act",
                "evidence-substantiates-act", "amendment-amends-principle"}
    if BUILD.parse_red_clauses(REPO):
        expected.add("clause-enforces-principle")
    assert expected <= seen, f"missing edge relations: {expected - seen}"


# ---------------------------------------------------------------------------
# refs-only law: promise nodes ref an id, never copy the body
# ---------------------------------------------------------------------------

def test_promise_nodes_are_refs_only(records, build_records):
    from laplace.research import corpus_ingest as ci
    # the promise bodies (the `ask` text) must NOT appear verbatim in any node essence
    rr = REPO
    # promises.jsonl carries MIXED record shapes — promise rows (keyed by "id") and control
    # rows the orchestrator banks against them (e.g. {"record":"defer","target":"PRM-…"}) that
    # carry no "id". A promise row is exactly one with an "id"; skip the control rows.
    proms = {r["id"]: r for r in
             (json.loads(l) for l in (rr / "contract" / "promises.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip())
             if "id" in r}
    prom_nodes = [r for r in records if r["kind"] == "add-node"
                  and r["node"].startswith("PRM-")]
    assert prom_nodes, "no promise nodes in the store"
    for r in prom_nodes:
        body = proms[r["node"]]["ask"]
        assert body[:40] not in (r.get("essence") or ""), (
            f"{r['node']}: promise body copied into the node — refs-only law breached")


# ---------------------------------------------------------------------------
# the builder is idempotent — "running it twice changes nothing"
# ---------------------------------------------------------------------------

def test_builder_is_deterministic():
    """Two fresh builds are byte-identical (stable ids, fixed ts, fixed emit order).
    This is the idempotency property that never churns; the on-disk staleness gate is
    the separate --check path (scripts/build_design_conceptric.py --check), left to the
    seam because the contract sources move under a live multi-leg wave."""
    text_a, _ = BUILD.emit(REPO)
    text_b, _ = BUILD.emit(REPO)
    assert text_a == text_b, "two builds differ — not deterministic"


def test_door_append_does_not_drift_the_builder(build_records):
    """A deposit through the SANCTIONED door does not put the ledger into drift.

    ``corpus_ingest.rewire_add`` appends at end-of-file (the one locked append), so its row
    lands AFTER the build block; ``emit`` used to re-emit every foreign row ahead of the block,
    so a legitimate deposit made ``--check`` red until the builder was re-run — caught live by
    the growth-entry lane (WO-20260820-rewire-append-drifts-the-builder). The cure is
    ``split_foreign``: a foreign row is preserved on the side of the block it was written on.
    This runs the accept probe IN MEMORY — the real ledger is read, never written."""
    on_disk = LEDGER.read_text(encoding="utf-8")
    deposit = json.dumps({
        "id": "RW-PROBE-000000", "ts": "2026-08-20T00:00:00", "kind": "add-node",
        "node": "PROBE-door-append", "target": None, "value": None, "by": "probe:door-append",
        "status": "open", "parent": "goal:design-interface", "node_kind": "derivation-step",
        "essence": "a synthetic door deposit", "ref": "tests/test_design_conceptric.py",
    }, ensure_ascii=False) + "\n"

    before, after = BUILD.split_foreign(on_disk + deposit)
    assert "PROBE-door-append" in [r["node"] for r in after], (
        "the appended door row was not recognised as sitting after the build block")
    assert BUILD._serialise(before + build_records + after) == on_disk + deposit, (
        "a door deposit still drifts the builder — --check would go red on a legitimate append")

    # and the untouched ledger stays byte-exact: the cure must not have moved anything else
    b0, a0 = BUILD.split_foreign(on_disk)
    assert BUILD._serialise(b0 + build_records + a0) == on_disk, (
        "the on-disk ledger no longer matches a fresh build — run "
        "scripts/build_design_conceptric.py")


# ---------------------------------------------------------------------------
# the census matches the design doc — read off the STORED artifact for the
# stable types (design doc + promise owners don't churn during the wave)
# ---------------------------------------------------------------------------

def test_census_matches_design_doc(build_block):
    """The DESIGN-DOC-sourced counts are frozen (the doc is the fixed spine — its
    principles, acts, dated amendments and evidence entries don't churn while the wave
    runs). The open INTERFACE promise count is LIVE — it is sourced from
    contract/promises.jsonl, which grows as sibling legs bank their promises mid-wave
    (W-register/W-reaper appended two). So the promise census, exactly like the sibling
    RED-clause census, tracks a FRESH parse of the live ledger — never a frozen number,
    or the conceptric authored to 'stop rotting' rots the instant its ledger grows (P2:
    one truth, every number == its filter)."""
    add = [r for r in build_block if r["kind"] == "add-node"]
    n_principles = sum(1 for r in add if r["node_kind"] == "postulate")
    n_amendments = sum(1 for r in add if r["node_kind"] == "definition")
    n_acts = sum(1 for r in add if r.get("parent") == "cluster:acts")
    n_promises = sum(1 for r in add if r["node"].startswith("PRM-"))
    n_evidence = sum(1 for r in add if r.get("parent") == "cluster:evidence")
    # the 10 principles P1-P10 — the fixed spine of the design
    assert n_principles == 10, f"principles {n_principles}"
    # the acts: KEYSTONE + ACT 0-7 = 9
    assert n_acts == 9, f"acts {n_acts}"
    # tonight's dated amendments — LIVE: a principle gains a dated amendment line as it
    # is refined mid-wave (P1's third-question correction, P8's register law, P10's
    # no-clip law, ...), so like the promise/clause census this tracks a fresh parse of
    # the design doc, never a frozen number.
    fresh_amendments = [p for p in BUILD.parse_principles(BUILD._read(REPO, BUILD.DESIGN_DOC))
                        if p["amend_date"]]
    assert n_amendments == len(fresh_amendments), (
        f"stored amendments {n_amendments} != fresh parse {len(fresh_amendments)} "
        "— ledger stale, run scripts/build_design_conceptric.py")
    # the open INTERFACE promises — LIVE: equals a fresh parse of contract/promises.jsonl
    # (the stored ledger must reflect the live source; a stale ledger fails here, which is
    # the anti-rot signal that the builder needs re-running — the mandated re-sync).
    fresh_promises = BUILD.parse_open_interface_promises(REPO)
    assert n_promises == len(fresh_promises), (
        f"stored open interface promises {n_promises} != fresh parse {len(fresh_promises)} "
        "— ledger stale, run scripts/build_design_conceptric.py")
    # the evidence entries E1-E7 (+ E4b)
    assert n_evidence == 8, f"evidence {n_evidence}"


def test_red_clause_census_is_internally_consistent(census):
    """The RED clause census is LIVE — a wave flips a marker green on delivery, so the
    count MOVES during the overhaul (at authoring the design named 22; W-desk flipped
    its verb + count + structural markers green mid-wave, so a fresh read is lower). The
    builder's census must equal a fresh recompute of the same source parse (the wiring
    is honest), and every emitted clause node must ref a real contract/surfaces file —
    the conceptric tracks the sources by construction, never a frozen number."""
    fresh = BUILD.parse_red_clauses(REPO)
    assert census["n_red_clauses"] == len(fresh), (
        f"census {census['n_red_clauses']} != fresh parse {len(fresh)} — census wiring drifted")
    for c in fresh:
        rel = c["ref"].split(":")[0]
        assert (REPO / rel).is_file(), f"clause {c['id']} refs a missing file {rel}"


def test_stored_clause_nodes_ref_the_contract(records):
    """Whatever red clauses the store currently holds, each refs a real surfaces yaml
    and enforces a real principle node (structural validity, robust to the live count)."""
    principle_ids = {r["node"] for r in records
                     if r["kind"] == "add-node" and r["node_kind"] == "postulate"}
    clause_nodes = [r for r in records
                    if r["kind"] == "add-node" and r["node"].startswith("clause:")]
    enforces = {e["node"]: e["target"] for e in records
                if r_ok(e) and e["value"] == "clause-enforces-principle"}
    for c in clause_nodes:
        assert "contract/surfaces/" in c["ref"], f"{c['node']}: ref not into surfaces"
        assert enforces.get(c["node"]) in principle_ids, (
            f"{c['node']}: clause-enforces-principle edge missing or dangling")


def test_every_open_interface_promise_has_a_delivers_edge(records, build_records):
    prom_nodes = [r["node"] for r in records if r["kind"] == "add-node"
                  and r["node"].startswith("PRM-")]
    delivered = {e["node"] for e in records
                 if r_ok(e) and e["value"] == "wave-delivers-promise"}
    for p in prom_nodes:
        assert p in delivered, f"{p}: no wave-delivers-promise edge"


def r_ok(e: dict) -> bool:
    return e["kind"] == "add-edge"
