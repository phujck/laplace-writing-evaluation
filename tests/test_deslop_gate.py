"""Scoped tests for scripts/deslop_gate.py — the structural deslop gate, first consumer
of the growth adjudicator.

Fixture-driven: synthetic slop text exercises each detector (public-jargon,
oracle-shape, antithesis-density); a synthetic conceptric ledger drives an end-to-end
scan → packet → manifest; and allowlist-decay is proven to re-flag a term once its
``decays`` date has passed. The gate only reports and writes a manifest — it never
edits, and its consumed adjudications bank with ``kind:"growth"``.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "deslop_gate", ROOT / "scripts" / "deslop_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dg = _load_gate()
from laplace.engine import author_proxy
from laplace.pipeline import growth_adjudicator as ga


def _repo(tmp_path: Path) -> Path:
    """A minimal proxy-frame repo so adjudicate_growth can assemble a frame."""
    repo = tmp_path / "repo"
    (repo / "profiles").mkdir(parents=True)
    (repo / "EIGEN_AUTHOR.md").write_text(
        "# author\n- earned simplicity not slogan slop (his, 2026-06-08)\n",
        encoding="utf-8")
    (repo / "OPEN_STACK.md").write_text("# open stack\n", encoding="utf-8")
    return repo


# ----------------------------------------------------------------- the detectors
def test_detect_jargon_hits_seed_terms():
    hits = dg.detect_jargon(
        "We leverage a seamless paradigm to unlock synergy.",
        list(dg._SEED_JARGON), allowset=set())
    assert "leverage" in hits and "seamless" in hits and "paradigm" in hits
    assert "unlock" in hits and "synergy" in hits


def test_detect_oracle_flags_ungrounded_absolute():
    grounded = "At L=500 the wall clock is 77.9 d at 1 factory."   # numerals → grounded
    ungrounded = "Safety as it is practised is always theatre and can only forbid."
    assert dg.detect_oracle(grounded) == []
    assert dg.detect_oracle(ungrounded)                            # absolute + claim verb


def test_detect_oracle_exempts_citation_edge():
    s = "A network overwrites what it knew, the fault named decades ago [CITE]."
    assert dg.detect_oracle(s) == []


def test_detect_antithesis_shapes():
    count, density, ex = dg.detect_antithesis(
        "They are not three problems but one. It is structure, not slogan.")
    assert count >= 2
    assert density > 0
    assert ex


# ----------------------------------------------------------------- allowlist decay
def test_allowlist_decay_reflags_after_expiry(tmp_path):
    lexicon = {"jargon": ["leverage"],
               "allowlist": [{"term": "leverage", "decays": "2026-08-01"}]}
    text = "we leverage the platform"

    # unexpired (today before decays) → suppressed, no hit
    active = dg._active_allowset(lexicon, today="2026-07-12")
    assert dg.detect_jargon(text, ["leverage"], active) == []

    # expired (today past decays) → re-flagged
    active_expired = dg._active_allowset(lexicon, today="2026-09-01")
    assert dg.detect_jargon(text, ["leverage"], active_expired) == ["leverage"]


def test_load_lexicon_seeds_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    lex = dg.load_lexicon(repo)
    assert (repo / dg.DESLOP_LEXICON_NAME).is_file()
    assert "leverage" in lex["jargon"]
    assert lex["allowlist"] == []


def test_scan_honours_written_allowlist(tmp_path):
    repo = _repo(tmp_path)
    (repo / dg.DESLOP_LEXICON_NAME).write_text(json.dumps({
        "jargon": ["leverage"],
        "allowlist": [{"term": "leverage", "decays": "2099-01-01"}],
    }), encoding="utf-8")
    units = [{"where": "n1", "text": "we leverage the seamless platform"}]
    # 'leverage' allowlisted-unexpired → not a jargon tell (and 'seamless' not in this
    # written jargon list) → no public-jargon candidate from this unit
    cands = dg.scan(repo, units, corpus_name=None, today="2026-07-12",
                    antithesis_min=2, density_min=0.5)
    assert all("public-jargon" not in c["tells"] for c in cands)


# ----------------------------------------------------------------- end to end
def _ledger(tmp_path: Path) -> Path:
    rows = [
        {"node": "d_slop", "essence": "We leverage a seamless paradigm to unlock synergy."},
        {"node": "d_oracle", "essence": "Safety as practised is always theatre and can only forbid."},
        {"node": "d_anti", "essence": "They are not three problems but one; structure, not slogan."},
        {"node": "d_clean", "essence": "The lattice has 30 sites encoded on 60 logical qubits [CITE]."},
    ]
    p = tmp_path / "concept.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_units_from_ledger_reads_essences(tmp_path):
    units = dg.units_from_ledger(_ledger(tmp_path))
    assert len(units) == 4
    assert units[0]["where"] == "d_slop"


def test_scan_detects_each_tell_and_spares_clean(tmp_path):
    repo = _repo(tmp_path)
    units = dg.units_from_ledger(_ledger(tmp_path))
    cands = dg.scan(repo, units, corpus_name=None, today="2026-07-12",
                    antithesis_min=1, density_min=0.4)
    tells = {c["where"]: set(c["tells"]) for c in cands}
    assert "public-jargon" in tells["d_slop"]
    assert "oracle-shape" in tells["d_oracle"]
    assert "antithesis-density" in tells["d_anti"]
    assert "d_clean" not in tells                    # grounded essence spared


def test_candidate_to_packet_is_growth_shaped(tmp_path):
    repo = _repo(tmp_path)
    units = dg.units_from_ledger(_ledger(tmp_path))
    cands = dg.scan(repo, units, None, "2026-07-12", 1, 0.4)
    packet = dg.candidate_to_packet(repo, cands[0], "conceptric[test]")
    assert set(packet) == {"frame", "decision", "bank"}
    assert packet["decision"]["kind"] == "deslop-keep-kill-rewrite"
    assert packet["decision"]["candidates"] == ["KEEP", "KILL", "REWRITE"]
    assert packet["bank"]["kind"] == "growth"


def test_main_writes_manifest_and_reports(tmp_path, capsys):
    repo = _repo(tmp_path)
    ledger = _ledger(repo)
    manifest = repo / "m.json"
    rc = dg.main(["--ledger", str(ledger), "--root", str(repo),
                  "--manifest", str(manifest), "--today", "2026-07-12",
                  "--antithesis-min", "1", "--density-min", "0.4"])
    assert rc == 0                                    # advisory: always 0
    out = capsys.readouterr().out
    assert "VERDICT=WARN" in out                      # candidates found
    assert manifest.is_file()
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["kind"] == "growth-adjudication"
    assert m["count"] >= 3


def test_consumed_adjudication_banks_growth(tmp_path):
    """The gate surfaces; a consumer that rules banks with kind:'growth'."""
    repo = _repo(tmp_path)
    units = dg.units_from_ledger(_ledger(tmp_path))
    cands = dg.scan(repo, units, None, "2026-07-12", 1, 0.4)
    packet = dg.candidate_to_packet(repo, cands[0], "conceptric[test]")
    # a stand-in judge produces a ruling for the packet's question
    ruling = {
        "id": author_proxy.make_ruling_id("deslop-test"),
        "date": "2026-07-12", "question": packet["frame"]["question"],
        "ruling": "REWRITE", "evidence": ["public-jargon x3"],
        "confidence": "HIGH", "supersedes": [], "unlocks": "essence rewrite",
        "contested": None,
    }
    ga.bank_growth_ruling(repo, ruling)
    verdicts = author_proxy.load_verdicts(repo)
    assert verdicts[-1]["kind"] == "growth"


# ----------------------------------------------------- the manifest-frame hoist (0a)
def test_candidate_to_lite_packet_is_frameless(tmp_path):
    repo = _repo(tmp_path)
    units = dg.units_from_ledger(_ledger(tmp_path))
    cands = dg.scan(repo, units, None, "2026-07-12", 1, 0.4)
    packet = dg.candidate_to_lite_packet(cands[0], "conceptric[test]")
    assert set(packet) == {"decision", "bank"}          # no frame — hoisted to manifest
    assert packet["decision"]["kind"] == "deslop-keep-kill-rewrite"
    assert "DESLOP" in packet["decision"]["question"]   # its own task statement travels
    assert packet["bank"]["kind"] == "growth"


def test_main_manifest_hoists_one_frame(tmp_path):
    repo = _repo(tmp_path)
    ledger = _ledger(repo)
    manifest = repo / "m.json"
    rc = dg.main(["--ledger", str(ledger), "--root", str(repo),
                  "--manifest", str(manifest), "--today", "2026-07-12",
                  "--antithesis-min", "1", "--density-min", "0.4"])
    assert rc == 0
    m = json.loads(manifest.read_text(encoding="utf-8"))
    # ONE hoisted, wave-level frame; every packet frame-less
    assert m["schema"] == 2
    assert "frame" in m and m["frame"]["question"].startswith("DESLOP wave over")
    assert m["count"] >= 3
    assert all("frame" not in p for p in m["packets"])
    assert all(set(p) == {"decision", "bank"} for p in m["packets"])


# ------------------------------------------------------ the allowlist writer (0b)
def _keep_ruling(terms: list[str], slug: str = "deslop-keep") -> dict:
    """A banked growth KEEP ruling echoing the judge's kept terms (top-level shape)."""
    return {
        "id": author_proxy.make_ruling_id(slug),
        "date": "2026-07-12",
        "question": "DESLOP — keep/kill/rewrite 'harness'?",
        "ruling": "KEEP",
        "evidence": ["genuinely his register, not slop"],
        "confidence": "GENUINELY-HIS",
        "supersedes": [], "unlocks": "the term stays in his voice", "contested": None,
        "terms_kept": terms,
    }


def _decays(today: str, days: int = 90) -> str:
    import datetime as _dt
    return (_dt.date.fromisoformat(today) + _dt.timedelta(days=days)).isoformat()


def test_apply_keep_rulings_grows_allowlist(tmp_path):
    repo = _repo(tmp_path)
    ga.bank_growth_ruling(repo, _keep_ruling(["harness", "landscape"]))
    summary = dg.apply_keep_rulings(repo, today="2026-07-12", decay_days=90)

    assert summary["added"] == 2
    assert set(summary["terms"]) == {"harness", "landscape"}
    lex = json.loads((repo / dg.DESLOP_LEXICON_NAME).read_text(encoding="utf-8"))
    entries = {e["term"]: e for e in lex["allowlist"]}
    assert entries["harness"]["decays"] == _decays("2026-07-12")
    assert entries["harness"]["ruling_id"].startswith("PV-")
    # the jargon list is NEVER touched by the writer
    assert lex["jargon"] == list(dg._SEED_JARGON)


def test_apply_keep_rulings_reads_terms_under_decision(tmp_path):
    repo = _repo(tmp_path)
    rows = [{
        "kind": "growth", "id": "PV-x-1", "ruling": "KEEP",
        "decision": {"kind": "deslop-keep-kill-rewrite", "terms_kept": ["tapestry"]},
    }]
    summary = dg.apply_keep_rulings(repo, rulings=rows, today="2026-07-12")
    assert summary["added"] == 1 and summary["terms"] == ["tapestry"]


def test_apply_keep_rulings_ignores_non_keep_and_non_growth(tmp_path):
    repo = _repo(tmp_path)
    rows = [
        {"kind": "growth", "id": "a", "ruling": "KILL", "terms_kept": ["leverage"]},
        {"kind": None, "id": "b", "ruling": "KEEP", "terms_kept": ["synergy"]},
        {"kind": "growth", "id": "c", "ruling": "KEEP", "terms_kept": []},
        {"kind": "growth", "id": "d", "ruling": "KEEP", "terms_kept": ["ok"],
         "decision": {"kind": "deepen-which-node"}},   # wrong decision kind → skip
    ]
    summary = dg.apply_keep_rulings(repo, rulings=rows, today="2026-07-12")
    assert summary["added"] == 0


def test_apply_keep_rulings_is_idempotent(tmp_path):
    repo = _repo(tmp_path)
    ga.bank_growth_ruling(repo, _keep_ruling(["harness"]))
    dg.apply_keep_rulings(repo, today="2026-07-12")
    summary2 = dg.apply_keep_rulings(repo, today="2026-07-12")   # second run
    assert summary2["added"] == 0
    assert summary2["skipped"] >= 1
    lex = json.loads((repo / dg.DESLOP_LEXICON_NAME).read_text(encoding="utf-8"))
    assert sum(1 for e in lex["allowlist"] if e["term"] == "harness") == 1


def test_grown_allowlist_suppresses_then_reflags_on_decay(tmp_path):
    repo = _repo(tmp_path)
    # seed the lexicon so 'harness' would otherwise flag as jargon
    (repo / dg.DESLOP_LEXICON_NAME).write_text(
        json.dumps({"jargon": ["harness"], "allowlist": []}), encoding="utf-8")
    units = [{"where": "n1", "text": "we harness the platform to harness more"}]

    # before the KEEP ruling lands: the term flags
    before = dg.scan(repo, units, None, "2026-07-12", 2, 0.5)
    assert any("public-jargon" in c["tells"] for c in before)

    ga.bank_growth_ruling(repo, _keep_ruling(["harness"]))
    dg.apply_keep_rulings(repo, today="2026-07-12", decay_days=90)  # decays 2026-10-10

    # unexpired: the grown entry suppresses the term
    assert all("public-jargon" not in c["tells"]
               for c in dg.scan(repo, units, None, "2026-07-12", 2, 0.5))
    # past decay: the entry has decayed → the term re-flags (contest path = decay)
    assert any("public-jargon" in c["tells"]
               for c in dg.scan(repo, units, None, "2026-12-01", 2, 0.5))


def test_main_apply_keeps_mode(tmp_path, capsys):
    repo = _repo(tmp_path)
    ga.bank_growth_ruling(repo, _keep_ruling(["harness"]))
    rc = dg.main(["--apply-keeps", "--root", str(repo), "--today", "2026-07-12"])
    assert rc == 0                                        # advisory: always 0
    out = capsys.readouterr().out
    assert "apply_keep_rulings" in out and "harness" in out
    lex = json.loads((repo / dg.DESLOP_LEXICON_NAME).read_text(encoding="utf-8"))
    assert any(e["term"] == "harness" for e in lex["allowlist"])


# ------------------------------------------ ruled-essence suppression (the dread metric)
# A gate that re-flags an already-adjudicated, unchanged essence forever makes every
# intervention cost again. Suppression holds those back; a changed essence flags anew.
_SLOP = "We leverage a seamless paradigm to unlock synergy."


def _growth_ruling(node, essence_prefix, verb="KEEP", corpus="eig",
                   rewrite_text=None, rid="PV-sup-1"):
    row = {"kind": "growth", "id": rid, "ruling": f"{verb}: ...",
           "decision": {"kind": "deslop-keep-kill-rewrite",
                        "subject": f"conceptric[{corpus}]:{node} :: {essence_prefix[:120]}"}}
    if rewrite_text is not None:
        row["rewrite_text"] = rewrite_text
    return row


def test_load_ruled_essences_basis_selection(tmp_path):
    """The basis keyed per ruling: a KEEP/KILL carries the subject's `` :: `` essence
    PREFIX; a REWRITE carries the full ``rewrite_text``; a foreign corpus is filtered."""
    repo = _repo(tmp_path)
    rulings = [
        _growth_ruling("n1", "kept head text", verb="KEEP", rid="a"),
        _growth_ruling("n2", "stale prefix ignored", verb="REWRITE",
                       rewrite_text="the full applied line", rid="b"),
        _growth_ruling("n3", "nope", verb="KEEP", corpus="other", rid="c"),
    ]
    ruled = dg.load_ruled_essences(repo, "eig", rulings=rulings)
    assert ruled == {"n1": "kept head text", "n2": "the full applied line"}


def test_load_ruled_essences_default_load_reads_the_ledger(tmp_path):
    """``rulings=None`` loads the repo's own proxy_verdicts.jsonl — the path the live
    gate runs (the explicit-rulings tests above never exercised the import it needs)."""
    repo = _repo(tmp_path)
    row = _growth_ruling("n1", "kept head text", verb="KEEP", rid="a")
    (repo / "proxy_verdicts.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8")
    ruled = dg.load_ruled_essences(repo, "eig")
    assert ruled == {"n1": "kept head text"}


def test_scan_suppresses_ruled_unchanged_essence_with_tally(tmp_path):
    repo = _repo(tmp_path)
    units = [{"where": "d_slop", "text": _SLOP}]
    rulings = [_growth_ruling("d_slop", _SLOP, verb="KEEP")]
    cands = dg.scan(repo, units, corpus_name="eig", today="2026-07-12",
                    antithesis_min=2, density_min=0.5, rulings=rulings)
    assert list(cands) == []                     # ruled + unchanged → not emitted
    assert cands.suppressed_ruled == 1           # counted next to candidates


def test_scan_suppresses_on_rewrite_basis(tmp_path):
    """A REWRITE's basis is its full rewrite_text (once applied, THAT is the essence) —
    the stale subject prefix does not matter."""
    repo = _repo(tmp_path)
    rewritten = _SLOP + " fully rewritten tail."
    units = [{"where": "d_slop", "text": rewritten}]
    rulings = [_growth_ruling("d_slop", "an entirely different stale prefix",
                              verb="REWRITE", rewrite_text=rewritten)]
    cands = dg.scan(repo, units, "eig", "2026-07-12", 2, 0.5, rulings=rulings)
    assert list(cands) == []
    assert cands.suppressed_ruled == 1


def test_scan_reflags_essence_changed_since_ruling(tmp_path):
    repo = _repo(tmp_path)
    ruled_head = "An older leverage-laden seamless line the proxy once ruled here."
    current = _SLOP + " now with a wholly different head."   # head differs from ruled
    units = [{"where": "d_slop", "text": current}]
    rulings = [_growth_ruling("d_slop", ruled_head, verb="KEEP")]
    cands = dg.scan(repo, units, "eig", "2026-07-12", 2, 0.5, rulings=rulings)
    assert any("public-jargon" in c["tells"] for c in cands)  # changed → flags again
    assert cands.suppressed_ruled == 0


def test_scan_no_growth_rulings_identical(tmp_path):
    """No growth ruling for the corpus → the scan is unchanged and the tally is 0."""
    repo = _repo(tmp_path)
    units = dg.units_from_ledger(_ledger(tmp_path))
    base = dg.scan(repo, units, corpus_name=None, today="2026-07-12",
                   antithesis_min=1, density_min=0.4)
    empty = dg.scan(repo, units, corpus_name="eig", today="2026-07-12",
                    antithesis_min=1, density_min=0.4, rulings=[])
    assert [c["where"] for c in base] == [c["where"] for c in empty]
    assert base.suppressed_ruled == 0 and empty.suppressed_ruled == 0
    assert isinstance(base, dg.ScanResult)
