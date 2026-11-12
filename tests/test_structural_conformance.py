"""Scoped tests for the PRE-PROJECTION CONFORMANCE PASS
(src/laplace/pipeline/structural_conformance.py).

Three things are proven:

  * **op-vocabulary fidelity** — every candidate verb is a projection-intent op
    (``evolution_consumer._VERB_TO_PROPOSED_OP``) and every ``proposed_op`` is a
    real storyboard plan op (``schema.PLAN_OP_KINDS``); nothing is invented;
  * **manifest shape** — the fusion frame + bank contract (the SAME
    ``author_proxy.bank_ruling`` path) + the EXISTING apply bridge are all present
    and self-describing; every candidate stamps ``provenance="conjectured"``;
  * **the boom guard** — the read leg is LEDGER-INERT: ``proxy_verdicts.jsonl`` and
    the project feedback ledger are byte-unchanged across the read (it applies
    nothing, banks nothing).

The two store-served tests run against the real repo (corpus_stores + the vendored
embed backend) and skip cleanly where either is absent; the dial-off and boom-guard
tests are self-contained.
"""
import json
from pathlib import Path

import pytest

from laplace.engine import author_proxy
from laplace.pipeline import schema
from laplace.pipeline import structural_conformance as sc
from laplace.pipeline.dials import defaults
from laplace.pipeline.evolution_consumer import _VERB_TO_PROPOSED_OP

REPO = Path(__file__).resolve().parents[1]
CORPUS = "paper_falqon"


def _stores_ready() -> bool:
    for store in ("section_architecture", "spine_chain"):
        if not (REPO / "corpus_stores" / store / "gate_verdict.json").is_file():
            return False
    try:
        from laplace.representation.embed_router import get_backend
        return get_backend() is not None
    except Exception:
        return False


def _enabled_dials() -> dict:
    d = defaults()
    d["stores"]["section_architecture"]["enabled"] = True
    d["stores"]["spine_chain"]["enabled"] = True
    return d


needs_stores = pytest.mark.skipif(
    not _stores_ready(),
    reason="requires corpus_stores + the vendored embed backend")


# ---------------------------------------------------------- op-vocabulary fidelity
@needs_stores
def test_manifest_op_vocabulary_fidelity(tmp_path):
    m = sc.build_conformance_manifest(
        CORPUS, dials=_enabled_dials(), out_path=tmp_path / "m.json")
    assert m["packets"], "the enabled falqon read must flag at least one section"
    for p in m["packets"]:
        c = p["candidate"]
        # the verb is a real projection-intent op verb
        assert c["verb"] in _VERB_TO_PROPOSED_OP, c["verb"]
        # the proposed_op is the SECTION mapping of that verb, a real plan op
        assert c["proposed_op"] == _VERB_TO_PROPOSED_OP[c["verb"]]["section"]
        assert c["proposed_op"] in schema.PLAN_OP_KINDS, c["proposed_op"]
        assert c["object_kind"] == "section"
        assert c["object_key"], "a candidate must name its section"
        # the honesty law: the candidate is a conjecture and carries its signal
        assert c["provenance"] == "conjectured"
        assert "arch_cos" in c["signal"] and "arch_floor" in c["signal"]


# ---------------------------------------------------------- manifest shape + fusion
@needs_stores
def test_manifest_shape_frame_bank_and_apply_bridge(tmp_path):
    m = sc.build_conformance_manifest(
        CORPUS, dials=_enabled_dials(), out_path=tmp_path / "m.json")
    assert m["kind"] == "structural-conformance"
    assert m["corpus"] == CORPUS
    assert m["count"] == len(m["packets"])
    assert m["read_only"] is True

    # the SAME judge, the SAME bank path (the fusion): bank_contract → bank_ruling
    assert m["bank_contract"]["function"] == "laplace.engine.author_proxy.bank_ruling"
    assert (m["bank_contract"]["required_keys"]
            == list(author_proxy.REQUIRED_KEYS))
    # NO new apply mechanism — the EXISTING Fork-8 bridge is named
    assert (m["apply_bridge"]["function"]
            == "laplace.pipeline.evolution_consumer.apply_plan_proposals")

    # the shared frame IS the fusion organ, and for a structural manifest question
    # its third input (FORM-EXEMPLARS) is present and served
    fe = m["frame"]["form_exemplars"]
    assert fe["structural"] is True
    assert fe["served_count"] == 2, "both structural stores should serve the frame"

    # each packet carries its own retrieved evidence + the bank contract
    for p in m["packets"]:
        assert "section_architecture" in p["evidence"]
        assert "spine_chain" in p["evidence"]
        assert p["bank"] is sc.STRUCTURAL_BANK_CONTRACT or p["bank"]["function"] == (
            "laplace.engine.author_proxy.bank_ruling")

    # the manifest was actually written to disk (the deliverable is emitted)
    assert (tmp_path / "m.json").is_file()
    on_disk = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
    assert on_disk["count"] == m["count"]


@needs_stores
def test_no_form_prose_leaks_into_evidence(tmp_path):
    """FORM never CONTENT: the served envelopes carry the whitelist form fields, never
    the ``embed_text`` prose (the retrieval wire's structural guarantee, re-asserted
    at this altitude)."""
    m = sc.build_conformance_manifest(
        CORPUS, dials=_enabled_dials(), out_path=tmp_path / "m.json")
    blob = json.dumps(m, ensure_ascii=False)
    assert "embed_text" not in blob


# ---------------------------------------------------------- dial-off is inert
def test_dial_off_is_behaviour_inert(tmp_path):
    """At the default (both store dials FALSE) the pass is inert: zero patches, every
    section unscored with the honest dial-off reason, and the frame carries no served
    form exemplars — exactly as the rest of the store wiring lands inert."""
    m = sc.build_conformance_manifest(
        CORPUS, dials=defaults(), out_path=tmp_path / "m.json")
    assert m["count"] == 0
    assert m["packets"] == []
    assert m["stores"]["section_architecture"].startswith("dial-off")
    assert m["stores"]["spine_chain"].startswith("dial-off")
    assert len(m["unscored"]) >= 1
    assert m["frame"]["form_exemplars"]["served_count"] == 0


# ---------------------------------------------------------- THE BOOM GUARD
def _snapshot(paths: list[Path]) -> dict[str, bytes | None]:
    return {str(p): (p.read_bytes() if p.is_file() else None) for p in paths}


@pytest.mark.parametrize("use_dials", ["off", "on"])
def test_read_only_writes_no_ledger(tmp_path, use_dials):
    """THE BOOM GUARD: the read leg banks NOTHING. Neither the proxy verdict ledger
    nor the project feedback ledger changes by a single byte across the read — on the
    inert (dial-off) path AND the served (dial-on) path. Skips the served path only if
    the stores/backend are absent; the ledger invariant is checked regardless."""
    if use_dials == "on" and not _stores_ready():
        pytest.skip("served path requires corpus_stores + embed backend")
    dials = _enabled_dials() if use_dials == "on" else defaults()

    ledgers = [
        REPO / "proxy_verdicts.jsonl",
        REPO / "paper_falqon" / "manuscript" / "feedback" / "feedback.jsonl",
    ]
    before = _snapshot(ledgers)
    sc.build_conformance_manifest(CORPUS, dials=dials, out_path=tmp_path / "m.json")
    after = _snapshot(ledgers)
    assert after == before, "the read leg must not write ANY ledger (boom guard)"


# ---------------------------------------------------------- THE LAWFUL READER
# read_manifest is the conjugate of build_conformance_manifest: the /pipeline
# structural-conformance card calls THIS (view=mechanism), never re-parses the
# artifact. Three proofs: honest facts from a constructed tmp tree, honest-empty
# when absent (present=False, no raise), and a pure read path (no subprocess /
# compile / network / writes).
def _write_manifest(mdir: Path, manifest: dict) -> Path:
    """Bank a manifest at the exact on-disk home the reader reads."""
    disp = mdir / "dispatches"
    disp.mkdir(parents=True, exist_ok=True)
    art = disp / "structural_conformance_manifest.json"
    art.write_text(json.dumps(manifest), encoding="utf-8")
    return art


def test_reader_returns_honest_facts_patched(tmp_path):
    """A patched manifest → present, patch_count == len(packets), verdict 'patched',
    and stores_fed names ONLY the served store (not the dial-off one)."""
    _write_manifest(tmp_path, {
        "kind": "structural-conformance", "corpus": "demo", "count": 2,
        "cut_at": "2026-07-17T12:00:00",
        "packets": [{"section": {"id": "s1"}}, {"section": {"id": "s2"}}],
        "conformant": [{"section": "s3"}, {"section": "s4"}, {"section": "s5"}],
        "unscored": [],
        "stores": {"section_architecture": "served: k=3",
                   "spine_chain": "dial-off (store not enabled)"},
    })
    r = sc.read_manifest(tmp_path)
    assert r["present"] is True
    assert r["patch_count"] == 2                      # == len(packets)
    assert r["verdict"] == "patched"
    assert r["corpus"] == "demo"
    assert r["cut_at"] == "2026-07-17T12:00:00"
    assert r["conformant"] == 3
    assert r["unscored"] == 0
    # WHICH stores fed it — only the one whose note is 'served'
    assert r["stores_fed"] == ["section_architecture"]
    assert r["stores"]["spine_chain"].startswith("dial-off")


def test_reader_reads_empty_patch_manifest(tmp_path):
    """A dial-off (zero-candidate) manifest is PRESENT but verdict 'empty-patch' with
    no store fed — the honest inert shape build_conformance_manifest emits."""
    _write_manifest(tmp_path, {
        "kind": "structural-conformance", "corpus": "demo", "count": 0,
        "packets": [], "conformant": [],
        "unscored": [{"section": "s1", "reason": "dial-off (store not enabled)"}],
        "stores": {"section_architecture": "dial-off (store not enabled)",
                   "spine_chain": "dial-off (store not enabled)"},
    })
    r = sc.read_manifest(tmp_path)
    assert r["present"] is True
    assert r["patch_count"] == 0
    assert r["verdict"] == "empty-patch"
    assert r["stores_fed"] == []
    assert r["unscored"] == 1


def test_reader_honest_empty_when_absent(tmp_path):
    """No artifact → present False, verdict 'absent', every count zeroed, no raise."""
    r = sc.read_manifest(tmp_path)                   # no dispatches/ at all
    assert r["present"] is False
    assert r["verdict"] == "absent"
    assert r["patch_count"] == 0
    assert r["conformant"] == 0 and r["unscored"] == 0
    assert r["stores"] == {} and r["stores_fed"] == []


def test_reader_honest_empty_when_malformed(tmp_path):
    """An unreadable/malformed manifest → honest-empty, never a raise, never None."""
    _write_manifest(tmp_path, {})                    # overwrite with broken bytes below
    (tmp_path / "dispatches" / "structural_conformance_manifest.json").write_text(
        "{ not json", encoding="utf-8")
    r = sc.read_manifest(tmp_path)
    assert r is not None
    assert r["present"] is False
    assert r["patch_count"] == 0


def test_reader_read_path_is_pure(tmp_path, monkeypatch):
    """view=mechanism purity: read_manifest touches no subprocess/compile/network and
    writes nothing — proven three ways: a source grep, a monkeypatch that BOOMS on any
    subprocess/network reach, and a byte-snapshot of the tree across the read."""
    import ast
    import inspect
    import subprocess
    import urllib.request

    # (1) source grep — the reader's CODE (docstring/comments stripped via AST, so the
    # prose 'no subprocess…' is not a false hit) names no escape hatch
    def _code_only(fn) -> str:
        node = ast.parse(inspect.getsource(fn)).body[0]
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(getattr(node.body[0], "value", None), ast.Constant)):
            node.body = node.body[1:]            # drop the docstring
        return ast.unparse(node)                 # code only — comments gone too

    src = _code_only(sc.read_manifest) + _code_only(sc._absent_read)
    for forbidden in ("subprocess", "Popen", "check_output", "urllib", "requests",
                      "socket", "compile(", "write_text", "os.system", "mkdir"):
        assert forbidden not in src, forbidden

    # (2) monkeypatch — any subprocess/network reach raises; the read must not reach it
    def _boom(*a, **k):
        raise AssertionError("read path reached a subprocess/network call")
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    _write_manifest(tmp_path, {
        "corpus": "demo", "count": 1, "packets": [{"section": {"id": "s1"}}],
        "conformant": [], "unscored": [],
        "stores": {"section_architecture": "served: k=3"}})

    # (3) byte-snapshot the tree — the read mutates nothing
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    r_present = sc.read_manifest(tmp_path)
    r_absent = sc.read_manifest(tmp_path / "nowhere")
    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert r_present["present"] is True and r_absent["present"] is False
    assert after == before, "the read leg wrote to the tree"


def test_reader_matches_real_falqon_manifest():
    """view=mechanism against the REAL banked artifact: the reader's facts equal the
    manifest's own (patch_count == len(packets); stores_fed == the served stores)."""
    mdir = REPO / CORPUS / "manuscript"
    art = mdir / "dispatches" / "structural_conformance_manifest.json"
    if not art.is_file():
        pytest.skip("real falqon structural-conformance manifest absent")
    raw = json.loads(art.read_text(encoding="utf-8"))
    r = sc.read_manifest(mdir)
    assert r["present"] is True
    assert r["patch_count"] == len(raw.get("packets") or [])
    assert r["verdict"] == ("patched" if r["patch_count"] else "empty-patch")
    fed = [n for n, note in (raw.get("stores") or {}).items()
           if str(note).startswith("served")]
    assert sorted(r["stores_fed"]) == sorted(fed)
    assert r["conformant"] == len(raw.get("conformant") or [])
