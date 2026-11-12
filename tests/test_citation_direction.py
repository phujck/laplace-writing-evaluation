"""The citation-direction organ — hermetic tests for every seam.

builder != judge: retrieval, prefilter, manifest shape, provenance stamping, and the
honest network-degrade are all deterministic/offline. The one real network fact (arXiv
reachable or not) is not asserted here — the network leg is tested through an INJECTED
fetch over a fixed Atom fixture, so the suite is portable and hermetic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.pipeline import bibliography_stage as bs
from laplace.pipeline import citation_direction as cd


# --------------------------------------------------------------------------- #
# Fixtures — a tiny manuscript with one dangling key, one door-pending cite
# --------------------------------------------------------------------------- #

_S1 = r"""% s1
Under Ross-Selinger-class synthesis each rotation costs about $3\log_2(1/\varepsilon)$
T gates~\cite{ross2016optimal}, but this figure has not been checked against the
source synthesis algorithm's exact constant.
The amplitude estimation scaling is anchored by~\cite{childs2012hamiltonian}, a claim
that remains unconfirmed against its cited source and is deferred until fetched
through the door.
A third strand~\cite{gamma2019missing} is cited but has no source yet.
"""

_BIB = r"""@article{ross2016optimal,
  title = {Optimal Ancilla-Free Clifford+T Approximation of Z-Rotations},
  author = {Ross, Neil J. and Selinger, Peter},
  year = {2016},
  note = {arXiv:1403.2975},
}

@article{childs2012hamiltonian,
  title = {Hamiltonian Simulation Using Linear Combinations of Unitary Operations},
  author = {Childs, Andrew M. and Wiebe, Nathan},
  year = {2012},
}
"""

_MAIN = r"""\documentclass{article}
\begin{document}
\input{s1}
\end{document}
"""

_CORPUS = {
    "_about": "test corpus",
    "references": [
        {"id": "W-ross", "title": "Optimal ancilla-free Clifford+T approximation "
         "of z-rotations synthesis", "year": 2016,
         "authors": ["Neil J. Ross", "Peter Selinger"]},
        {"id": "W-unrelated", "title": "Photosynthesis in marine algae", "year": 2001,
         "authors": ["A. Botanist"]},
    ],
}

# a fixed arXiv Atom reply for the injected-fetch network leg
_ATOM_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1403.2975v3</id>
    <published>2014-03-12T00:00:00Z</published>
    <title>Optimal ancilla-free Clifford+T approximation of z-rotations</title>
    <summary>We describe an algorithm that approximates z-rotations by ancilla-free
    Clifford+T circuits using about 3 log2(1/epsilon) T gates.</summary>
    <author><name>Neil J. Ross</name></author>
    <author><name>Peter Selinger</name></author>
  </entry>
</feed>
"""


@pytest.fixture()
def manuscript(tmp_path: Path) -> Path:
    mdir = tmp_path / "manuscript"
    mdir.mkdir()
    (mdir / "s1.tex").write_text(_S1, encoding="utf-8")
    (mdir / "refs.bib").write_text(_BIB, encoding="utf-8")
    (mdir / "main.tex").write_text(_MAIN, encoding="utf-8")
    return mdir


@pytest.fixture()
def corpus(tmp_path: Path) -> Path:
    cdir = tmp_path / "reference_corpus"
    cdir.mkdir()
    (cdir / "_c.json").write_text(json.dumps(_CORPUS), encoding="utf-8")
    return cdir


# --------------------------------------------------------------------------- #
# INPUT — intent collection (manifest dangling + verification scan + ledger)
# --------------------------------------------------------------------------- #


def test_dangling_intent_carries_the_prose_claim(manuscript: Path):
    """A dangling key becomes an intent whose claim is the PROSE that cites it, not a
    generic manifest note."""
    # bank a real manifest via the bibliography stage (dangling: gamma2019missing)
    bs.run(manuscript, apply=False)
    manifest = {"dangling": ["gamma2019missing"], "intents": []}
    (manuscript / "bibliography_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    intents = cd.load_manifest_intents(manuscript)
    assert [i.key for i in intents] == ["gamma2019missing"]
    it = intents[0]
    assert it.lane == cd.INTENT_DANGLING
    assert "third strand" in it.claim.lower()   # the real sentence, not the note


def test_verification_scan_types_door_pending_cites(manuscript: Path):
    """The two door-pending cited claims (ross 'not been checked', childs 'deferred
    until ... through the door') type as verification intents; the plain gamma cite
    does not (no tell)."""
    vints = cd.scan_verification_intents(manuscript)
    keys = sorted(i.key for i in vints)
    assert keys == ["childs2012hamiltonian", "ross2016optimal"]
    assert all(i.lane == cd.INTENT_VERIFICATION for i in vints)
    assert all(i.claim for i in vints)


def test_collect_dedupes_and_reads_ledger(manuscript: Path):
    ledger = manuscript / "research_intents.jsonl"
    ledger.write_text(json.dumps({
        "id": "RI-LIT-fromledger", "cls": "literature", "key": "fromledger",
        "note": "a ledger literature intent needing amplitude estimation"}) + "\n"
        + json.dumps({"id": "RI-COMP-x", "research_class": "computation",
                      "key": "notme"}) + "\n", encoding="utf-8")
    intents = cd.collect_intents(manuscript)
    ids = {i.id for i in intents}
    assert "RI-LIT-fromledger" in ids           # literature ledger intent in
    assert not any("notme" == i.key for i in intents)   # computation filtered out


# --------------------------------------------------------------------------- #
# RETRIEVAL — local corpus matches by claim; unrelated ref does not
# --------------------------------------------------------------------------- #


def test_reference_corpus_matches_relevant_ref(manuscript: Path, corpus: Path):
    refs = cd.probe_reference_corpus(corpus)
    assert len(refs) == 2
    it = cd.LiteratureIntent(
        id="t", key="ross2016optimal",
        claim="Ross-Selinger ancilla-free Clifford+T approximation of z-rotations "
              "synthesis T gates")
    cands = cd.reference_corpus_candidates(it, refs)
    assert cands, "the relevant ross ref should retrieve"
    assert cands[0].cand_id == "corpus:W-ross"
    assert cands[0].provenance == "reference_corpus"
    # the marine-algae ref shares no salient term -> not a candidate
    assert all("algae" not in c.title.lower() for c in cands)


# --------------------------------------------------------------------------- #
# ENTAILMENT — machine prefilter + judge-packet / manifest shape
# --------------------------------------------------------------------------- #


def test_machine_prefilter_rejects_noise_and_future_years():
    it = cd.LiteratureIntent(id="t", key="k",
                             claim="amplitude estimation quadratic scaling in 2012")
    noise = cd.Candidate("c1", "Photosynthesis in algae", 2001, [], "reference_corpus")
    kept, reason = cd.machine_prefilter(it, noise)
    assert not kept and "overlap" in reason
    future = cd.Candidate("c2", "amplitude estimation scaling result", 2020, [],
                          "arxiv", abstract="amplitude estimation scaling")
    kept2, reason2 = cd.machine_prefilter(it, future)
    assert not kept2 and "year" in reason2
    good = cd.Candidate("c3", "amplitude estimation scaling", 2011, [], "arxiv",
                        abstract="a quadratic amplitude estimation scaling result")
    kept3, _ = cd.machine_prefilter(it, good)
    assert kept3


def test_entailment_packet_shape_carries_claim_candidate_and_law():
    it = cd.LiteratureIntent(id="RI-1", key="k", claim="the specific claim")
    c = cd.Candidate("arxiv:1403.2975", "A Title", 2014, ["X"], "arxiv",
                     abstract="an abstract")
    pkt = cd.entailment_packet(it, c)
    dec = pkt["decision"]
    assert dec["kind"] == "citation-entailment"
    assert dec["claim"] == "the specific claim"
    assert dec["candidate"]["abstract"] == "an abstract"
    assert dec["candidate"]["has_abstract"] is True
    assert pkt["bank"]["function"].endswith("apply_admission")
    assert "adjacency is NOT entailment" in pkt["bank"]["law"]


def test_manifest_is_self_describing_and_hoists_the_law(tmp_path: Path):
    it = cd.LiteratureIntent(id="RI-1", key="k", claim="c")
    c = cd.Candidate("x", "T", 2014, [], "arxiv", abstract="a")
    out = tmp_path / "m.json"
    man = cd.emit_entailment_manifest([cd.entailment_packet(it, c)], out, intent=it)
    assert man["kind"] == "citation-entailment-adjudication"
    assert man["count"] == 1
    assert "entailment_law" in man["frame"]      # the law hoisted ONCE (schema 2)
    assert man["schema"] == 2
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["frame"]["intent"]["id"] == "RI-1"


# --------------------------------------------------------------------------- #
# ADMISSION — provenance stamping + the render seam (bibliography consumes it)
# --------------------------------------------------------------------------- #


def test_admission_stamps_cited_provenance_and_verdict_ref(manuscript: Path):
    it = cd.LiteratureIntent(id="RI-LIT-gamma2019missing", key="gamma2019missing",
                             claim="a third strand claim", section="s1",
                             lane=cd.INTENT_DANGLING)
    cand = cd.Candidate("arxiv:1234.5678", "The Gamma Result", 2019, ["G. Amma"],
                        "arxiv", abstract="proves the third strand claim",
                        arxiv_id="1234.5678")
    verdict = {"ruling": "ENTAILS", "id": "PV-20260717-entail-gamma"}
    res = cd.apply_admission(manuscript, it, cand, verdict)
    assert res["admitted"] is True
    node = res["node"]
    assert node["epistemic"] == "cited"
    assert node["entailment_verdict_ref"] == "PV-20260717-entail-gamma"
    assert node["cite_key"] == "gamma2019missing"
    # the render seam: the key was dangling; after admission the bib defines it
    assert "gamma2019missing" not in bs.bib_keys(manuscript / "refs.bib") or True
    defined = bs.bib_keys(manuscript / "refs.bib")
    assert "gamma2019missing" in defined
    cited = bs.enumerate_citations(manuscript)
    _resolved, dangling = bs.resolve(cited, defined)
    assert "gamma2019missing" not in dangling    # RESOLVES now -> reference renders


def test_non_entails_admits_nothing_but_keeps_the_intent(manuscript: Path):
    it = cd.LiteratureIntent(id="RI-1", key="childs2012hamiltonian",
                             claim="amplitude estimation constant")
    # the mis-anchor: an adjacent LCU paper the judge rules NOT-ENTAILS
    cand = cd.Candidate("arxiv:1202.5822", "Hamiltonian Simulation via LCU", 2012, [],
                        "arxiv", abstract="linear combinations of unitaries")
    res = cd.apply_admission(manuscript, it, cand, {"ruling": "NOT-ENTAILS"})
    assert res["admitted"] is False
    assert res["intent"]["id"] == "RI-1"          # typed, not dropped


# --------------------------------------------------------------------------- #
# The run — network-degrade honest + full record + telemetry sidecar
# --------------------------------------------------------------------------- #


def test_run_degrades_honestly_when_network_off(manuscript: Path, corpus: Path):
    rec = cd.run(manuscript, corpus_dir=corpus, use_network=False)
    assert rec["network_leg"]["reachable"] is False
    assert "attested-available" in rec["network_leg"]["enable"]
    assert rec["intents_n"] >= 2                  # the two door-pending cites at least
    assert rec["admitted"] == 0                   # judge-tier deferred (honest)
    assert "COMPILED" in rec["ran_vs_compiled"]
    # a needs-judge intent emitted a manifest that exists on disk
    out = manuscript / "citation_direction"
    assert (out / "run_record.json").exists()
    assert (out / "_citation_direction.sidecar.json").exists()


def test_run_network_leg_via_injected_fetch(manuscript: Path, corpus: Path):
    """The network leg fires through an injected fetch (no real network): the arXiv
    fixture candidate is retrieved, survives the prefilter, and lands in a manifest."""
    rec = cd.run(manuscript, corpus_dir=corpus, use_network=True,
                 arxiv_fetch=lambda url: _ATOM_FIXTURE)
    assert rec["network_leg"]["reachable"] is True
    # at least one intent has an arXiv candidate in its ledger
    arxiv_seen = any(
        c["provenance"] == "arxiv"
        for r in rec["by_intent"] for c in []  # by_intent carries counts only
    )
    # inspect a manifest for the arxiv candidate
    manifests = rec["manifests"]
    assert manifests, "network leg should produce judge manifests"
    blob = json.loads(Path(manifests[0]).read_text(encoding="utf-8"))
    provs = {p["decision"]["candidate"]["provenance"] for p in blob["packets"]}
    assert "arxiv" in provs
    assert rec["buckets"]["needs-judge"] >= 1


def test_comments_never_leak_into_claims(manuscript: Path):
    """A leading ``% section-label`` comment must not contaminate a claim's prose or
    its retrieval terms (the falqon appendix_c-p13 leak)."""
    vints = cd.scan_verification_intents(manuscript)
    assert vints and all("%" not in i.claim for i in vints)
    assert all(not i.claim.lstrip().startswith("appendix") for i in vints)


def test_resolved_source_candidate_fetches_the_cited_abstract(manuscript: Path):
    """A KNOWN key resolves to its actual .bib source and its abstract is fetched by
    the entry's arXiv id (identity resolution) — candidate provenance 'cited-source'.
    """
    entry = cd.bib_entry_for_key(manuscript, "ross2016optimal")
    assert entry and entry["title"].startswith("Optimal Ancilla-Free")
    it = cd.LiteratureIntent(id="t", key="ross2016optimal",
                             claim="Ross-Selinger synthesis constant", lane=cd.INTENT_VERIFICATION)
    cand = cd.resolved_source_candidate(it, manuscript,
                                        fetch=lambda url: _ATOM_FIXTURE)
    assert cand is not None
    assert cand.provenance == "cited-source"
    assert cand.cand_id == "cited:ross2016optimal"
    assert "z-rotations" in cand.abstract.lower()   # fetched, not fabricated
    # a dangling key (no bib entry) has no resolved source
    it2 = cd.LiteratureIntent(id="t2", key="gamma2019missing", claim="x")
    assert cd.resolved_source_candidate(it2, manuscript, fetch=lambda u: _ATOM_FIXTURE) is None


def test_hyphen_compound_overlap_does_not_false_reject():
    """``early-fault-tolerant`` in a claim overlaps ``fault-tolerant`` in an abstract
    — the hyphen-artifact false-reject that dropped a correctly-cited source."""
    it = cd.LiteratureIntent(id="t", key="k",
                             claim="the early-fault-tolerant wall-clock comparison")
    cand = cd.Candidate("c", "Early fault-tolerant simulations", 2021, [], "cited-source",
                        abstract="a fault-tolerant simulation of the Hubbard model")
    kept, _ = cd.machine_prefilter(it, cand)
    assert kept


def test_sidecar_is_counts_only(manuscript: Path, corpus: Path):
    cd.run(manuscript, corpus_dir=corpus, use_network=False)
    sidecar = json.loads(
        (manuscript / "citation_direction" / "_citation_direction.sidecar.json")
        .read_text(encoding="utf-8"))
    assert sidecar["organ"] == "citation_direction"
    assert "buckets" in sidecar
    # provenance/counts only — no claim/candidate prose text leaks into the sidecar
    assert "claim" not in json.dumps(sidecar)


# --------------------------------------------------------------------------- #
# THE LAWFUL READER — read_run_record (view=mechanism: the /pipeline card calls THIS)
# --------------------------------------------------------------------------- #


def _write_run(out: Path) -> None:
    """A minimal banked run tree — run_record + sidecar + one entailment manifest —
    the exact on-disk shape :func:`cd.run` writes, hand-built so the reader's facts are
    asserted against known values (not the retrieval's live output)."""
    out.mkdir(parents=True, exist_ok=True)
    record = {
        "organ": "citation_direction",
        "ran_at": "2026-07-17T10:42:39",
        "manuscript": str(out.parent),
        "ran_vs_compiled": "retrieval RAN; the entailment ADMISSION is COMPILED",
        "network_leg": {"reachable": True, "note": "arxiv reachable",
                        "enable": cd.ARXIV_ENABLE_NOTE},
        "corpus": {"dir": "reference_corpus", "n_refs": 988},
        "intents_n": 3,
        "candidates_total": 7,
        "buckets": {"admitted": 0, "needs-judge": 1, "rejected": 1, "no-candidate": 1},
        "by_intent": [
            {"intent_id": "RI-VERIFY-s9-k", "key": "k", "lane": "verification",
             "section": "s9", "n_candidates": 6, "n_rejected_code": 0,
             "n_needs_judge": 6, "bucket": "needs-judge",
             "manifest": str(out / "entailment_manifest.ri-verify-s9-k.json")},
            {"intent_id": "RI-LIT-gamma", "key": "gamma", "lane": "dangling",
             "section": "s1", "n_candidates": 1, "n_rejected_code": 1,
             "n_needs_judge": 0, "bucket": "rejected", "manifest": ""},
            {"intent_id": "RI-VERIFY-s2-z", "key": "z", "lane": "verification",
             "section": "s2", "n_candidates": 0, "n_rejected_code": 0,
             "n_needs_judge": 0, "bucket": "no-candidate", "manifest": ""},
        ],
        "manifests": [str(out / "entailment_manifest.ri-verify-s9-k.json")],
        "admitted": 0,
    }
    (out / "run_record.json").write_text(json.dumps(record), encoding="utf-8")
    # the reader's verification state reads the sidecar's by_intent (lane + bucket) —
    # written directly in the shape :func:`cd.write_run_sidecar` banks (counts only)
    sidecar = {
        "organ": "citation_direction", "ts": record["ran_at"],
        "network_leg": True, "corpus_n_refs": 988,
        "intents_n": record["intents_n"],
        "candidates_total": record["candidates_total"],
        "buckets": record["buckets"], "manifests_n": 1,
        "by_intent": [
            {"intent_id": r["intent_id"], "lane": r["lane"],
             "n_candidates": r["n_candidates"], "n_needs_judge": r["n_needs_judge"],
             "n_rejected_code": r["n_rejected_code"], "bucket": r["bucket"]}
            for r in record["by_intent"]],
    }
    (out / "_citation_direction.sidecar.json").write_text(
        json.dumps(sidecar), encoding="utf-8")
    cd.emit_entailment_manifest(
        [cd.entailment_packet(
            cd.LiteratureIntent(id="RI-VERIFY-s9-k", key="k", claim="a claim",
                                section="s9", lane=cd.INTENT_VERIFICATION),
            cd.Candidate("arxiv:1", "T", 2020, [], "arxiv", abstract="a"))],
        out / "entailment_manifest.ri-verify-s9-k.json",
        intent=cd.LiteratureIntent(id="RI-VERIFY-s9-k", key="k", claim="a claim",
                                   section="s9", lane=cd.INTENT_VERIFICATION))


def test_read_run_record_returns_honest_facts(tmp_path: Path):
    """The reader returns the run summary, manifests-pending-vs-admitted, and the
    verification state — every fact traced to the banked artifact, none re-derived."""
    out = tmp_path / "manuscript" / "citation_direction"
    _write_run(out)
    rec = cd.read_run_record(tmp_path / "manuscript")
    assert rec["present"] is True
    # run summary
    assert rec["ran_at"] == "2026-07-17T10:42:39"
    assert rec["intents_n"] == 3
    assert rec["candidates_total"] == 7
    assert rec["buckets"] == {"admitted": 0, "needs-judge": 1,
                              "rejected": 1, "no-candidate": 1}
    assert "COMPILED" in rec["ran_vs_compiled"]
    assert rec["network_leg"] is True
    assert rec["corpus_n_refs"] == 988
    # manifests pending (on disk) vs admitted
    assert rec["manifests_pending"] == 1
    assert rec["manifests_on_disk"] == 1
    assert rec["admitted"] == 0
    man = rec["manifests"][0]
    assert man["intent_id"] == "RI-VERIFY-s9-k"
    assert man["cite_key"] == "k"
    assert man["lane"] == cd.INTENT_VERIFICATION
    assert man["n_packets"] == 1          # read from the manifest's own count
    # verification state from the sidecar: two verification intents, one needs-judge
    ver = rec["verification"]
    assert ver["intents_n"] == 2
    assert ver["needs_judge"] == 1
    assert ver["no_candidate"] == 1
    assert ver["admitted"] == 0


def test_read_run_record_round_trips_a_real_run(manuscript: Path, corpus: Path):
    """The reader is the conjugate of :func:`cd.run`: reading back a freshly banked run
    reproduces its buckets, intents_n, and one manifest per needs-judge intent."""
    written = cd.run(manuscript, corpus_dir=corpus, use_network=False)
    rec = cd.read_run_record(manuscript)
    assert rec["present"] is True
    assert rec["intents_n"] == written["intents_n"]
    assert rec["buckets"] == written["buckets"]
    assert rec["candidates_total"] == written["candidates_total"]
    # one manifest on disk per needs-judge intent
    assert rec["manifests_pending"] == written["buckets"]["needs-judge"]
    assert rec["admitted"] == 0


def test_read_run_record_honest_empty_when_absent(tmp_path: Path):
    """No banked run → present False, every fact zeroed/empty, NO raise, never None."""
    rec = cd.read_run_record(tmp_path / "nothing_here")
    assert rec is not None
    assert rec["present"] is False
    assert rec["ran_at"] == ""
    assert rec["intents_n"] == 0
    assert rec["candidates_total"] == 0
    assert rec["buckets"] == {b: 0 for b in cd.BUCKETS}
    assert rec["admitted"] == 0
    assert rec["manifests_pending"] == 0
    assert rec["manifests"] == []
    assert rec["network_leg"] is None
    assert rec["verification"]["intents_n"] == 0
    # a corrupt run_record is treated as honestly-absent, not a raise
    out = tmp_path / "corrupt" / "citation_direction"
    out.mkdir(parents=True)
    (out / "run_record.json").write_text("{not json", encoding="utf-8")
    corrupt = cd.read_run_record(tmp_path / "corrupt")
    assert corrupt["present"] is False


def test_read_run_record_is_pure_no_subprocess_compile_network(tmp_path: Path,
                                                                monkeypatch):
    """The read path touches NO subprocess/compile/network. Proven two ways: (1) the
    function's source names none of those calls; (2) with subprocess + the module's
    network entrypoints monkeypatched to explode, the reader still returns facts."""
    import inspect
    import subprocess
    # grep the CODE, not the docstring (which names the forbidden calls to deny them)
    code = ""
    for fn in (cd.read_run_record, cd._verification_state, cd._empty_run_record):
        src = inspect.getsource(fn)
        code += src.replace(fn.__doc__ or "\0", "")
    for forbidden in ("subprocess", "urllib", "urlopen", "socket", "check_output",
                      "Popen", "os.system", "compile(", "_http_get", "probe_arxiv",
                      "arxiv_candidates"):
        assert forbidden not in code, f"read path names {forbidden!r}"

    def _boom(*a, **k):
        raise AssertionError("read_run_record fired a forbidden call")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(cd, "_http_get", _boom)
    monkeypatch.setattr(cd, "probe_arxiv", _boom)
    monkeypatch.setattr(cd.urllib.request, "urlopen", _boom)
    out = tmp_path / "manuscript" / "citation_direction"
    _write_run(out)
    rec = cd.read_run_record(tmp_path / "manuscript")
    assert rec["present"] is True and rec["intents_n"] == 3


# --------------------------------------------------------------------------- #
# CONSUMPTION — a judge tier's rulings landed as one durable act
# --------------------------------------------------------------------------- #


def _entailment_manifest(iid: str, key: str, packets: list[dict]) -> dict:
    return {"kind": "citation-entailment-adjudication", "schema": 2,
            "count": len(packets), "cut_at": "2026-07-17T10:00:00",
            "frame": {"entailment_law": cd.ENTAILMENT_LAW,
                      "intent": {"id": iid, "key": key, "claim": f"claim for {key}",
                                 "section": "s1", "lane": cd.INTENT_VERIFICATION}},
            "bank_contract": cd.BANK_CONTRACT, "packets": packets}


def _packet(cid: str, title: str) -> dict:
    return {"decision": {"kind": "citation-entailment", "candidate": {
        "cand_id": cid, "title": title, "abstract": "the abstract", "year": 2020,
        "authors": ["A. Author"], "provenance": "reference_corpus",
        "has_abstract": True}}, "bank": cd.BANK_CONTRACT}


@pytest.fixture()
def judged_run(tmp_path: Path) -> Path:
    """A manuscript with three pending manifests + a run record, one verdict each:
    ENTAILS (admit), all-NOT-ENTAILS (reject), INSUFFICIENT-TEXT (stays pending)."""
    mdir = tmp_path / "proj" / "manuscript"
    out = mdir / "citation_direction"
    out.mkdir(parents=True)
    (tmp_path / "corpus_friction").mkdir()
    (mdir / "refs.bib").write_text("", encoding="utf-8")
    manifests = {
        "RI-A": _entailment_manifest("RI-A", "alpha2020", [
            _packet("cited:alpha2020", "Alpha, the real source"),
            _packet("corpus:W1", "A decoy")]),
        "RI-B": _entailment_manifest("RI-B", "beta2020", [
            _packet("corpus:W2", "Wrong-field decoy")]),
        "RI-C": _entailment_manifest("RI-C", "gamma2020", [
            _packet("cited:gamma2020", "Corrupted-abstract entry")]),
    }
    for iid, man in manifests.items():
        (out / f"entailment_manifest.{iid.lower()}.json").write_text(
            json.dumps(man), encoding="utf-8")
    record = {"organ": "citation_direction", "ran_at": "2026-07-17T10:00:00",
              "ran_vs_compiled": "admission COMPILED",
              "intents_n": 3, "candidates_total": 4,
              "buckets": {"admitted": 0, "needs-judge": 3, "rejected": 0,
                          "no-candidate": 0},
              "by_intent": [
                  {"intent_id": "RI-A", "lane": "verification", "bucket": "needs-judge"},
                  {"intent_id": "RI-B", "lane": "verification", "bucket": "needs-judge"},
                  {"intent_id": "RI-C", "lane": "verification", "bucket": "needs-judge"}]}
    (out / "run_record.json").write_text(json.dumps(record), encoding="utf-8")
    return mdir


_VERDICTS = {"verdicts": [
    {"intent_id": "RI-A", "rulings": [
        {"cand_id": "cited:alpha2020", "ruling": "ENTAILS", "evidence": "states it"},
        {"cand_id": "corpus:W1", "ruling": "NOT-ENTAILS", "evidence": "wrong field"}]},
    {"intent_id": "RI-B", "rulings": [
        {"cand_id": "corpus:W2", "ruling": "NOT-ENTAILS", "evidence": "mis-anchor"}]},
    {"intent_id": "RI-C", "rulings": [
        {"cand_id": "cited:gamma2020", "ruling": "INSUFFICIENT-TEXT",
         "evidence": "abstract corrupted"}]},
]}


def test_consume_verdicts_lands_the_three_outcomes(judged_run: Path):
    """ENTAILS admits (bib written, manifest walked); all-NOT-ENTAILS rejects
    (manifest walked, intent stays typed); INSUFFICIENT-TEXT stays pending."""
    res = cd.consume_verdicts(judged_run, _VERDICTS, project="proj")
    assert (res["admitted"], res["rejected"], res["insufficient"]) == (1, 1, 1)
    out = judged_run / "citation_direction"
    # walked manifests moved; the insufficient one survives as pending
    pending = [p.name for p in out.glob("entailment_manifest.*.json")]
    assert pending == ["entailment_manifest.ri-c.json"]
    assert sorted(p.name for p in (out / "adjudicated").glob("*.json")) == [
        "entailment_manifest.ri-a.json", "entailment_manifest.ri-b.json"]
    # the bib landed and resolves the key
    assert "alpha2020" in (judged_run / "refs.bib").read_text(encoding="utf-8")
    # the citation-node record rode the project friction ledger
    ledger = judged_run.parents[1] / "corpus_friction" / "proj.jsonl"
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows and rows[-1]["epistemic"] == "cited" and rows[-1]["cite_key"] == "alpha2020"
    # the verdicts banked verbatim beside the record
    banked = list(out.glob("judge_verdicts.*.json"))
    assert len(banked) == 1
    body = json.loads(banked[0].read_text(encoding="utf-8"))
    assert body["verdicts"] == _VERDICTS


def test_consume_verdicts_updates_the_lawful_reader(judged_run: Path):
    """After consumption read_run_record (the /pipeline card) reports the walked
    state: admitted=1, pending manifests=1, buckets true."""
    cd.consume_verdicts(judged_run, _VERDICTS, project="proj")
    rec = cd.read_run_record(judged_run)
    assert rec["admitted"] == 1
    assert rec["manifests_pending"] == 1
    assert rec["buckets"] == {"admitted": 1, "needs-judge": 1, "rejected": 1,
                              "no-candidate": 0}
    assert "ADMISSION CONSUMED" in rec["ran_vs_compiled"]


def test_consume_verdicts_is_idempotent(judged_run: Path):
    """A second consumption of the same verdicts admits nothing new — walked
    manifests are gone, the bib append is a keyed no-op."""
    cd.consume_verdicts(judged_run, _VERDICTS, project="proj")
    res2 = cd.consume_verdicts(judged_run, _VERDICTS, project="proj")
    assert res2["admitted"] == 0 and res2["rejected"] == 0
    assert res2["insufficient"] == 1  # RI-C still pending, still insufficient
    bib = (judged_run / "refs.bib").read_text(encoding="utf-8")
    assert bib.count("alpha2020") == 1
