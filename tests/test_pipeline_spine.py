"""The pipeline spine (P1 of the infra deep-dive): one schema, one registry, one
ledger engine. These tests are the parity proof that the delegation rewire
changed no behaviour, plus the contract of the new freeze/transaction mechanics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.web import shared_ui
from laplace.manuscript import storyboard
from laplace.pipeline import registry
from laplace.pipeline import ledger, registry, schema, structural


# ---------------------------------------------------------------------------
# schema — the one source, consumed (not copied) by both engines
# ---------------------------------------------------------------------------

def test_schema_is_the_engines_vocabulary():
    # identity, not equality: the engines import the schema's objects
    assert ci._REWIRE_KINDS is schema.REWIRE_KINDS
    assert storyboard._OP_KINDS == schema.PLAN_OP_KINDS
    assert storyboard._CHEAP_OPS is schema.CHEAP_OPS
    assert storyboard._clean_ids is schema.clean_ids
    assert schema.CHEAP_OPS.isdisjoint(schema.EXPENSIVE_OPS)


def test_clean_ids_filters_support_namespaces_and_prose():
    ids = {"def:x", "res:y-z", "fig:panel", "ref:key", "not an id", "Goal:x"}
    assert schema.clean_ids(ids) == {"def:x", "res:y-z"}


def test_proj_of_reads_both_shapes():
    assert schema.proj_of({"projection": {"retired": True}}) == {"retired": True}
    assert schema.proj_of({"meta": {"projection": {"term": "t"}}}) == {"term": "t"}
    assert schema.proj_of({}) == {}


def test_bib_entries_balanced_braces():
    bib = "@article{a1,\n title={Nested {Braces} Here},\n}\n@misc{b2,\n note={x},\n}"
    ent = schema.bib_entries(bib)
    assert set(ent) == {"a1", "b2"}
    assert ent["a1"].count("{") == ent["a1"].count("}")
    assert schema.bib_keys(bib) == {"a1", "b2"}


def test_brief_channel_fences_round_trip():
    text = (schema.fence(schema.BRIEF_CHANNEL_POLICY, "configure, never echo")
            + "\n\n"
            + schema.fence(schema.BRIEF_CHANNEL_OBJECT, "the content itself"))
    ch = schema.parse_channels(text)
    assert ch == {"POLICY": "configure, never echo", "OBJECT": "the content itself"}
    # a legacy unfenced brief parses to {} - the transition reader's signal
    assert schema.parse_channels("# Builder brief - S1\nplain text") == {}


def test_feedback_kinds_route_to_work_kinds():
    # every work target named by KIND_TO_WORK is a declared work kind
    for kind, work in schema.KIND_TO_WORK.items():
        assert work is None or work in schema.WORK_KINDS
    # the live ledger's dominant kind routes to derivation work
    assert schema.KIND_TO_WORK["missing-derivation"] == "derive"


# ---------------------------------------------------------------------------
# registry — one door, three layout families, fenced
# ---------------------------------------------------------------------------

def test_registry_resolves_the_conceptric_convention_on_disk():
    p = registry.resolve("subset-sum-itqde")
    assert p is not None and p.kind == "conceptric"
    rr = Path(".").resolve()
    for rel in (p.ledger, p.plan_path, p.manuscript_dir, p.glossary,
                p.evolutions_dir, p.feedback_ledger):
        assert (rr / rel).exists(), rel
    assert p.resolved_target_dir(rr).name == "whitepaper"


def test_registry_covers_every_corpus_plus_override_layouts():
    projects = registry.all_projects()
    # every conceptric the one door lists is a full Project record - there is no
    # second corpus list to fall out of sync with (the hardcoded dict retired
    # 2026-08-04; its six surviving keys are registry_projects.json data rows).
    rows = {r["name"] for r in registry.conceptric_projects(Path("."))}
    assert rows <= set(projects)
    assert {"design-interface", "law-of-laws", "cost-of-complexity", "qde",
            "free-snacks", "subset-sum-itqde"} <= rows
    pe = registry.resolve("paper_eigen")
    assert pe.kind == "loop" and Path(pe.loop_dir).name == "_loop"
    assert pe.plan(Path(".")) is None          # no projection plan: no fake path
    ee = registry.resolve("eigenengine")
    assert ee.kind == "conceptric" and (Path(".") / ee.manuscript_dir).is_dir()
    disc = registry.resolve("ssg-disclosure")
    assert disc.kind == "tex" and (Path(".") / disc.project_dir).is_dir()


def test_registry_resolves_eigenengine_conceptric_manuscript():
    # eigenengine: kind FLIPPED "tex" -> "conceptric" (2026-07-12), the mechanical mirror of
    # the paper_falqon flip directly below (F, 2026-07-11), under N53's tightened mandate whose
    # named trigger ("the growth gate opens... falqon proves the chain end-to-end first") fired.
    # The compiled conceptric (109 nodes / 221 edges, hand-built extraction — see
    # conceptric_health.json) was poured through the rewire door into its L1 ledger
    # (scripts/pour_conceptric.py) and "eigenengine" -> "eigenengine/manuscript" became its
    # registered tex root, so resolve_corpus/corpus_network reconstruct the real graph
    # for every conceptric-kind consumer. Same assertions as the falqon test below, over eigenengine's own paths.
    from laplace.research import corpus_ingest as ci
    ee = registry.resolve("eigenengine")
    assert ee is not None and ee.kind == "conceptric"
    rr = Path(".").resolve()
    assert ci.resolve_corpus(rr, "eigenengine") == rr / "eigenengine/manuscript"
    assert ee.resolved_target_dir(rr) == rr / "eigenengine/manuscript"
    assert ee.resolved_target_dir(rr).is_dir()
    assert (ee.resolved_target_dir(rr) / "main.tex").is_file()
    assert (rr / ee.bib).is_file()
    assert (rr / ee.tex_root / "main.tex").is_file()   # tex_root is the regen source
    assert (rr / ee.ledger).is_file()                  # its own L1 friction ledger
    assert (rr / ee.feedback_ledger).is_file()         # the live intake door
    assert ee.plan_path == "eigenengine/manuscript/projection_plan.json"


def test_registry_resolves_paper_falqon_tex_manuscript():
    # the FALQON replication substrate. F (2026-07-11): kind FLIPPED "tex" ->
    # "conceptric" once the growth gate opened — the compiled conceptric (91
    # nodes / 140 edges) was poured through the rewire door into its L1 ledger
    # (scripts/pour_conceptric.py) and "paper_falqon" -> "paper_falqon/manuscript"
    # became its registered tex root, so resolve_corpus/corpus_network reconstruct the real graph
    # for every conceptric-kind consumer. The honestly-owned chain fields stay
    # registered: its own L1 ledger, the tex root that regenerates the latexmk
    # artifacts, the live feedback ledger, and the synthetics-convention
    # plan/briefs/versions/evolutions paths under manuscript/.
    from laplace.research import corpus_ingest as ci
    fq = registry.resolve("paper_falqon")
    assert fq is not None and fq.kind == "conceptric"
    rr = Path(".").resolve()
    # the gate's new guarantee: resolve_corpus returns the registered tex root
    assert ci.resolve_corpus(rr, "paper_falqon") == rr / "paper_falqon/manuscript"
    assert fq.resolved_target_dir(rr) == rr / "paper_falqon/manuscript"
    assert fq.resolved_target_dir(rr).is_dir()
    assert (fq.resolved_target_dir(rr) / "main.tex").is_file()
    assert (rr / fq.bib).is_file()
    assert (rr / fq.tex_root / "main.tex").is_file()   # tex_root is the regen source
    assert (rr / fq.ledger).is_file()                  # its own L1 friction ledger
    assert (rr / fq.feedback_ledger).is_file()         # the live intake door
    assert fq.plan_path == "paper_falqon/manuscript/projection_plan.json"
    assert fq.briefs_dir == "paper_falqon/manuscript/briefs"
    assert fq.versions_dir == "paper_falqon/manuscript/versions"
    assert fq.evolutions_dir == "paper_falqon/manuscript/evolutions"
    assert fq.glossary == ""                           # none exists — not faked


def test_registry_fences_unknown_and_traversal_names():
    assert registry.resolve("no-such-project") is None
    assert registry.resolve("../soul") is None
    assert registry.resolve("") is None


def test_project_rejects_unknown_kind():
    # RW-...-400014: kind was free text validated nowhere; a typo now raises
    # at construction instead of routing silently to no backend.
    with pytest.raises(ValueError, match="slides"):
        registry.Project(name="x", kind="slides")


def test_project_accepts_every_known_kind():
    for k in sorted(registry.KINDS):
        assert registry.Project(name="x", kind=k).kind == k


def test_project_path_resolves_existing_sibling(tmp_path):
    # RW-...-553836: a rel starting with '../' names a project living BESIDE
    # the repo root, not under it - resolved against the repo root's PARENT
    # (the session root holding sibling clones).
    root = tmp_path / "repo"
    root.mkdir()
    sibling = tmp_path / "phujck.github.io"
    sibling.mkdir()
    p = registry.Project(name="website", kind="site")
    assert p.path("../phujck.github.io", root) == sibling.resolve()


def test_project_path_raises_on_missing_sibling(tmp_path):
    # never silently return a non-existent sibling path - raise loud, naming
    # what was tried.
    root = tmp_path / "repo"
    root.mkdir()
    p = registry.Project(name="website", kind="site")
    with pytest.raises(FileNotFoundError, match="phujck.github.io"):
        p.path("../phujck.github.io", root)


def test_plan_path_for_delegates_with_same_semantics():
    p = registry.plan_path_for("subset-sum-itqde")
    assert p is not None and p.is_file() and p.name == "projection_plan.json"
    assert registry.plan_path_for("paper_eigen") is None     # registered, plan-less
    assert registry.plan_path_for("../soul") is None
    assert registry.plan_path_for("unknown") is None


# ---------------------------------------------------------------------------
# ledger — mechanics parity + the new freeze/transaction contract
# ---------------------------------------------------------------------------

def test_read_jsonl_tolerates_poison_lines(tmp_path):
    lp = tmp_path / "l.jsonl"
    lp.write_text('{"a": 1}\nnot json\n\n{"b": 2}\n', encoding="utf-8")
    assert ledger.read_jsonl(lp) == [{"a": 1}, {"b": 2}]
    assert ledger.read_jsonl(tmp_path / "absent.jsonl") == []


def test_append_then_read_round_trip(tmp_path):
    lp = tmp_path / "sub" / "l.jsonl"          # parent auto-created
    ledger.append_jsonl(lp, {"kind": "add-node", "node": "def:x"})
    ledger.append_jsonl(lp, {"kind": "edit-essence", "node": "def:x", "value": "e"})
    assert [r["kind"] for r in ledger.read_jsonl(lp)] == ["add-node", "edit-essence"]


def test_reduce_parity_with_storyboard_fold():
    base = {"sections": [
        {"id": "S1", "title": "One", "nodes_in_order": ["def:a", "def:b"], "beats": []},
        {"id": "S2", "title": "Two", "nodes_in_order": ["res:c"], "beats": []},
    ], "appendices": []}
    ops = [
        {"kind": "retitle", "section": "S1", "title": "One'"},
        {"kind": "move-node", "node": "def:b", "from": "S1", "to": "S2", "index": 0},
        {"kind": "toggle-beat", "section": "S2", "node": "res:c", "on": True},
        {"kind": "bogus-op", "section": "S1"},                    # skipped, not fatal
    ]
    reduced = storyboard.reduce_plan(base, ops)
    assert reduced["sections"][0]["title"] == "One'"
    assert reduced["sections"][0]["nodes_in_order"] == ["def:a"]
    assert reduced["sections"][1]["nodes_in_order"] == ["def:b", "res:c"]
    assert reduced["sections"][1]["beats"] == ["res:c"]
    # purity: the base was never touched
    assert base["sections"][0]["title"] == "One"
    # and the generic engine gives the identical result with the same fold
    again = ledger.reduce(base, ops, storyboard._apply_op)
    assert again == reduced


def test_transaction_commits_with_journal(tmp_path):
    l1, l2 = tmp_path / "l1.jsonl", tmp_path / "l2.jsonl"
    ledger.append_jsonl(l1, {"kind": "add-node", "node": "def:x"})
    with ledger.transaction(l1, l2, by="test-op", note="dual write"):
        ledger.append_jsonl(l1, {"kind": "edit-essence", "node": "def:x", "value": "e"})
        ledger.append_jsonl(l2, {"kind": "retitle", "section": "S1", "title": "T"})
    r1, r2 = ledger.read_jsonl(l1), ledger.read_jsonl(l2)
    assert [r["kind"] for r in r1] == ["add-node", "edit-essence", "txn"]
    assert [r["kind"] for r in r2] == ["retitle", "txn"]
    assert r1[-1]["by"] == "test-op" and r1[-1]["from_byte"] > 0
    # the journal is invisible to the reducers (unknown kinds pass through)
    assert all(rec["node"] == "def:x" for rec in ci.friction_current(r1))


def test_transaction_abort_truncates_only_its_own_suffix(tmp_path):
    l1, l2 = tmp_path / "l1.jsonl", tmp_path / "l2.jsonl"
    ledger.append_jsonl(l1, {"kind": "add-node", "node": "def:keep"})
    before = l1.read_bytes()
    with pytest.raises(RuntimeError):
        with ledger.transaction(l1, l2, by="test-op"):
            ledger.append_jsonl(l1, {"kind": "delete-node", "node": "def:keep"})
            ledger.append_jsonl(l2, {"kind": "retitle", "section": "S1", "title": "T"})
            raise RuntimeError("mid-transaction failure")
    assert l1.read_bytes() == before          # human record intact, suffix gone
    assert not l2.exists()                    # created by the txn: removed whole


def test_freeze_snapshots_with_manifest(tmp_path):
    src = tmp_path / "plan.json"
    src.write_text('{"sections": []}', encoding="utf-8")
    dest = ledger.freeze([src, tmp_path / "missing.jsonl"],
                         tmp_path / "archive", label="preop")
    man = json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))
    assert (dest / "plan.json").is_file()
    assert man["files"][str(src)]["bytes"] == src.stat().st_size
    assert man["files"][str(tmp_path / "missing.jsonl")] == {"missing": True}


# ---------------------------------------------------------------------------
# structural gate — the directional/symmetric semantics refinement (§6.3)
# ---------------------------------------------------------------------------

def test_gate_symmetric_edges_are_advisory_and_sanctioned_forwards_named():
    # The live eigenengine gate: 4 draws forward-refs pre-noted in the plan's
    # meta.sanctioned_forward downgrade to `sanctioned`; 2 `shares` forward-refs
    # (a SYMMETRIC co-occurrence kind) downgrade to `advisory`. Neither fails.
    r = structural.gate("eigenengine")
    assert r["pass"] is True and not r["issues"]

    # symmetric (shares) -> advisory, visible, never pass/fail; carries the rel
    assert len(r["advisories"]) == 2
    assert all(a["rel"] in structural.SYMMETRIC_EDGE_KINDS for a in r["advisories"])
    assert {a["where"] for a in r["advisories"]} == {
        "c_coupling_free", "c_generation_reverse"}

    # sanctioned draws forward-refs -> sanctioned, counted, each carrying its why
    assert len(r["sanctioned"]) == 4
    assert {(s["where"], s["target"]) for s in r["sanctioned"]} == {
        ("c_one_claim", "d_base_apex"), ("c_one_claim", "d_coupling"),
        ("c_one_claim", "d_citation_free"), ("c_ops_used", "d_coupling")}
    assert all(s["why"] for s in r["sanctioned"])   # no silent drop: the record is visible


def test_gate_unsanctioned_directional_forward_ref_still_fails(monkeypatch):
    # Strip the sanction list: the 4 `draws` forward-refs are DIRECTIONAL
    # ("A draws on B" requires B first) and now unsanctioned, so define-before-use
    # bites and the gate FAILS. The 2 `shares` stay advisory — a symmetric kind is
    # never a dependency regardless of sanctioning. This is the single fixture that
    # proves both "a draws-violation still FAILS" and "an unsanctioned draws
    # forward-ref still FAILS".
    orig = registry.Project.read_plan

    def stripped(self, repo_root=None):
        plan = orig(self, repo_root)
        if plan and (plan.get("meta") or {}).get("sanctioned_forward"):
            import copy
            plan = copy.deepcopy(plan)
            plan["meta"]["sanctioned_forward"] = []
        return plan

    monkeypatch.setattr(registry.Project, "read_plan", stripped)
    r = structural.gate("eigenengine")
    assert r["pass"] is False
    # exactly the 4 directional draws pairs are now failures; shares unaffected
    assert len(r["issues"]) == 4
    assert {i["where"] for i in r["issues"]} == {"c_one_claim", "c_ops_used"}
    assert len(r["advisories"]) == 2            # symmetric downgrade independent of sanction
    assert not r["sanctioned"]


def test_gate_edge_kind_constants_partition_directional_and_symmetric():
    # the semantics rule is encoded as named constants, and the two kinds are
    # disjoint (a relation is either a dependency or a co-occurrence, never both)
    assert "draws" in structural.DIRECTIONAL_EDGE_KINDS
    assert "shares" in structural.SYMMETRIC_EDGE_KINDS
    assert structural.DIRECTIONAL_EDGE_KINDS.isdisjoint(structural.SYMMETRIC_EDGE_KINDS)
    # evidential kinds are a third, disjoint class: evidence pointers, never
    # expository dependencies (first bearer: paper_roland_qrc)
    assert "validated_by" in structural.EVIDENTIAL_EDGE_KINDS
    assert structural.EVIDENTIAL_EDGE_KINDS.isdisjoint(
        structural.DIRECTIONAL_EDGE_KINDS | structural.SYMMETRIC_EDGE_KINDS)


def test_gate_evidential_edges_advisory_and_sanctioned_repool_visible():
    # The live paper_roland_qrc gate: claims validated_by reproduction nodes
    # pooled in the protocols appendix (document-last) downgrade to advisory
    # (evidence is not expository substrate); the plan's sanctioned RQ-CLM-052
    # repooling (stated in the discussion, derived in appendix_chi) is recorded
    # as sanctioned, not a duplicate-introduction failure.
    r = structural.gate("paper_roland_qrc")
    assert r["pass"] is True and not r["issues"]
    evid = [a for a in r["advisories"] if a.get("rel") in structural.EVIDENTIAL_EDGE_KINDS]
    # The bound is DERIVED from the plan, never a remembered number. The 2026-08-09
    # R3 restructure (7 -> 9 sections) pulled the reproduction nodes forward into the
    # body sections that cite them, so most claim->evidence edges stopped pointing
    # forward. Derivation against the restructured plan: conceptric_v1.json carries 42
    # `validated_by` edges, 41 with both endpoints planned; under the 9-section order
    # 27 are same-section and 11 point backwards (both compliant, never reported),
    # leaving exactly 3 forward -> 3 evidential advisories. The old `>= 40` was an
    # exact, marginless snapshot of the superseded 7-section ordering. Kept as a floor
    # (not `==`) so a newly added evidence edge does not fail the suite on arrival.
    assert len(evid) >= 3 and all("evidential" in a["advisory"] for a in evid)
    # Filtered on the appendix_chi target, not on the node alone: the 2026-08-19
    # migration clean-line archived the R3 leftovers into meta.sanctioned_forward
    # wholesale, and RQ-CLM-052 now also carries an archived sec:r2_discussion
    # repooling. This assertion is about the AUTHORED appendix_chi row surviving.
    repool = [s for s in r["sanctioned"]
              if s.get("node") == "RQ-CLM-052" and s.get("where") == "appendix_chi"]
    assert len(repool) == 1 and repool[0]["why"]


def test_registry_resolves_website_site_project():
    # THE WEBSITE (F6, ruled 2026-07-11): a sibling-repo project, kind="site".
    # external_root routes CONTENT paths into the sibling clone; the friction
    # ledger stays ENGINE-side (the _ENGINE_SIDE rule) so the drain never leaves
    # home. feedback_ledger deliberately empty (no drain delegation).
    w = registry.resolve("website")
    assert w is not None and w.kind == "site"
    assert w.external_root == "../phujck.github.io"
    rr = Path(".").resolve()
    # content resolves under the sibling repo...
    site_root = w.path(w.project_dir, rr)
    assert site_root.resolve() == (rr / "../phujck.github.io").resolve()
    # ...but the ledger resolves ENGINE-side, whichever accessor a consumer uses
    assert w.path(w.ledger, rr) == rr / "corpus_friction/website.jsonl"
    assert (rr / w.ledger) == rr / "corpus_friction/website.jsonl"
    assert w.feedback_ledger == ""     # no delegation; the demo intake is separate
    # site projects never enter the conceptric consumers' gated branch
    assert w.kind != "conceptric"


def test_website_friction_round_trip(tmp_path):
    # the typed door mints corpus_friction/website.jsonl with zero code change
    # (_rewire_path keys the ledger per name), and the drain digests THAT ledger.
    from laplace.research import corpus_ingest as ci2
    from laplace.pipeline import friction_consumer

    rec = ci2.friction_add(tmp_path, "website", {
        "kind": "friction", "node": "planted: shell drift on planted.html",
        "value": "planted round-trip fixture",
        "owning_layer": "shell", "by": "eigen",
        "chain": ["website-session 2026-07-11", "B1", "round-trip test"],
    })
    assert rec.get("ok"), rec
    led = tmp_path / "corpus_friction" / "website.jsonl"
    assert led.is_file()
    out = friction_consumer.drain(tmp_path, ledger_path=led)
    digest = friction_consumer.digest_path(led)
    assert digest.is_file(), (out, list(led.parent.iterdir()))
    assert "planted" in led.read_text(encoding="utf-8")
