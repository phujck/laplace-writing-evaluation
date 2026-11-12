"""THE RETRIEVAL WIRE (DESIGN_2026-07-15_the-stage-stores §4), hermetically.

Every test builds a tmp stage-store from the deterministic offline
``HashBackend`` (no model, no network) — the store's ``embeddings.json`` and the
query embed through the SAME backend, so cosine is meaningful and the whole suite
runs offline and deterministic. The laws under test:

  * disabled store -> ``None`` (the inert default; a real-store call at the shipped
    all-off dials returns None, so a narrative packet is unchanged);
  * enabled + gate-passed -> the FORM-EXEMPLAR envelope, FORM fields ONLY, with NO
    ``embed_text`` (his real prose) anywhere in the output;
  * enabled + gate-FAILED (or absent) -> a LOUD REFUSAL (``SystemExit``): the dial
    cannot override the gate;
  * defective rows are never retrieved (even when they would rank first);
  * deterministic for a fixed store + query.
"""
import json
from pathlib import Path

import pytest

from laplace.representation.embed_router import HashBackend
from laplace.pipeline import dials as dials_mod
from laplace.pipeline import stage_retrieval as sr

# distinctive REAL-PROSE strings — the retrieval basis (embed_text). They live in
# the fixture rows' prose and (crucially) NEVER in _index.json, so if any appears
# in a rendered envelope, form/content typing has been breached.
_PROSE = {
    "PP-x-p01": "We introduce a constructive mapping from nonunitary dynamics to unitary operations here.",
    "PP-x-p02": "The friction kernel enters the path integral and the classical limit recovers KvN exactly.",
    "PP-x-p03": "We conclude with a discussion of thermodynamic generalisations and future directions.",
    "PP-x-p04": "This paragraph was spliced by the chunker and carries no reliable role assignment at all.",
}


def _form(role, norm, prop, math="none"):
    return {"role": role, "normalized_role": norm, "connective_prev": "opens-section",
            "connective_next": "closes-section", "proposition_shape": prop,
            "detail_level": "sketch", "length_band": [400, 600],
            "carries_math": math, "carries_figure": "none",
            # extra fields that MUST NOT be surfaced (not on the whitelist):
            "char_count": 512, "paragraph_span": [1, 1], "length_band_read": [400, 600]}


def _make_store(root: Path, *, passed: bool | None, backend: HashBackend,
                store: str = "paragraph_plan") -> Path:
    """Write a tmp stage-store (_index.json + embeddings.json [+ gate_verdict.json])
    from ``backend``. ``passed=None`` writes NO gate verdict (absent-gate case)."""
    d = root / "corpus_stores" / store
    d.mkdir(parents=True, exist_ok=True)

    rows = [
        {"row_id": "PP-x-p01", "form": _form("state-the-approach", "state-contribution", "states-a-method"),
         "provenance": {"paper_id": "itqde", "span_ref": {"section_label": "sec:intro"}}},
        {"row_id": "PP-x-p02", "form": _form("derive-the-limit", "derive", "recovers-a-limit", "one-display"),
         "provenance": {"paper_id": "cif", "span_ref": {"section_label": "sec:classical"}}},
        {"row_id": "PP-x-p03", "form": _form("close-the-paper", "future-work", "previews-extensions"),
         "provenance": {"paper_id": "itqde", "span_ref": {"section_label": "sec:conc"}}},
        # a DEFECTIVE row (chunker splice) — null form, never a candidate:
        {"row_id": "PP-x-p04", "defective": True,
         "form": _form(None, None, None), "provenance": {"paper_id": "cif", "span_ref": {"section_label": None}}},
    ]
    index = {"schema": "stage-store/0.2", "store": store,
             "defective_rows": [{"row_id": "PP-x-p04", "paper_id": "cif", "reason": "spliced-by-chunker"}],
             "row_count": len(rows), "rows": rows}
    (d / "_index.json").write_text(json.dumps(index), encoding="utf-8")

    ids = [r["row_id"] for r in rows]
    vecs = backend.embed([_PROSE[i] for i in ids])
    (d / "embeddings.json").write_text(json.dumps(
        {"backend": backend.name, "dim": backend.dim,
         "items": {i: v for i, v in zip(ids, vecs)}}), encoding="utf-8")

    if passed is not None:
        (d / "gate_verdict.json").write_text(json.dumps(
            {"schema": "paragraph-plan-gate-verdict/0.2",
             "gate": {"passed": passed, "score": 0.69, "baseline": 0.68, "mode": "auc"}}),
            encoding="utf-8")
    return d


@pytest.fixture()
def backend():
    return HashBackend()


@pytest.fixture(autouse=True)
def _use_hash_backend(monkeypatch, backend):
    """The query embeds through the SAME offline backend the fixture store used."""
    monkeypatch.setattr(sr, "get_backend", lambda: backend)


def _enabled(store="paragraph_plan"):
    return {"stores": {store: {"enabled": True}}}


def _disabled(store="paragraph_plan"):
    return {"stores": {store: {"enabled": False}}}


# --------------------------------------------------------------------------- #
# disabled -> None (inert default), and the packet is unchanged
# --------------------------------------------------------------------------- #
def test_disabled_store_returns_none(tmp_path, backend):
    _make_store(tmp_path, passed=True, backend=backend)
    out = sr.build_form_channel("paragraph_plan", "a constructive mapping",
                                dials=_disabled(), root=tmp_path)
    assert out is None


def test_absent_store_dial_returns_none(tmp_path, backend):
    # a store with no dial entry at all is treated as disabled (silent no-op)
    _make_store(tmp_path, passed=True, backend=backend)
    out = sr.build_form_channel("paragraph_plan", "a constructive mapping",
                                dials={"stores": {}}, root=tmp_path)
    assert out is None


def test_shipped_dials_serve_paragraph_plan_and_leave_the_rest_inert(tmp_path):
    # the shipped law since his 2026-07-16 yes: paragraph_plan is ON (gate-passed,
    # watched in use — 13/13 falqon compiles sidecar-banked); the other four stores
    # ship OFF and a real-store call returns None (byte-inert, the standing default).
    d = dials_mod.load_dials()
    # the ON half is asserted at the dial boundary only — the real serve is proven
    # where the real backend lives (the lens-run evidence + the dispatch capture test);
    # re-embedding here would drag the production backend into a unit test.
    assert d["stores"]["paragraph_plan"] == {"enabled": True}
    repo_root = Path(__file__).resolve().parents[1]
    for store in ("section_architecture", "spine_chain", "derivation_walk"):
        assert d["stores"][store] == {"enabled": False}
        assert sr.build_form_channel(store, "any query text", dials=d,
                                     root=repo_root) is None


# --------------------------------------------------------------------------- #
# enabled + gate-passed -> the envelope, FORM only, no embed_text
# --------------------------------------------------------------------------- #
def test_enabled_gate_passed_renders_envelope(tmp_path, backend):
    _make_store(tmp_path, passed=True, backend=backend)
    out = sr.build_form_channel("paragraph_plan", _PROSE["PP-x-p01"],
                                dials=_enabled(), root=tmp_path)
    assert out is not None
    assert out.startswith("<!-- FORM-EXEMPLARS -->")
    assert out.rstrip().endswith("<!-- /FORM-EXEMPLARS -->")
    assert sr.FORM_LAW in out                     # the one-line law header
    assert "contamination fault" in out           # the form-never-content preamble
    # FORM fields present:
    assert "normalized_role" in out and "proposition_shape" in out
    assert "length_band" in out and "carries_math" in out
    # provenance present:
    assert "paper_id" in out and "section_label" in out


def test_no_embed_text_anywhere(tmp_path, backend):
    # the load-bearing guarantee: his real prose is NEVER fenced into the prompt.
    _make_store(tmp_path, passed=True, backend=backend)
    out = sr.build_form_channel("paragraph_plan", _PROSE["PP-x-p01"],
                                dials=_enabled(), root=tmp_path)
    for rid, prose in _PROSE.items():
        assert prose not in out, f"LEAK: embed_text of {rid} surfaced"
    # the literal key must not appear either, and no off-whitelist form field:
    assert "embed_text" not in out
    for off in ("char_count", "paragraph_span", "length_band_read"):
        assert off not in out, f"off-whitelist form field surfaced: {off}"


def test_only_whitelist_keys_surfaced(tmp_path, backend):
    _make_store(tmp_path, passed=True, backend=backend)
    out = sr.build_form_channel("paragraph_plan", _PROSE["PP-x-p02"],
                                dials=_enabled(), root=tmp_path)
    body = out.split("\n", 2)[2]            # past the fence + header line
    payload = json.loads(body[body.index("["): body.rindex("]") + 1])
    for ex in payload:
        assert set(ex) == {"row_id", "paper_id", "section_label", "cos", "form"}
        assert set(ex["form"]) == set(sr._FORM_KEYS)


# --------------------------------------------------------------------------- #
# enabled + gate-FAILED / absent -> LOUD REFUSAL (raises SystemExit)
# --------------------------------------------------------------------------- #
def test_enabled_gate_failed_refuses_loud(tmp_path, backend):
    _make_store(tmp_path, passed=False, backend=backend)
    with pytest.raises(SystemExit) as ei:
        sr.build_form_channel("paragraph_plan", "a query", dials=_enabled(),
                              root=tmp_path)
    assert "gate" in str(ei.value).lower()
    assert "cannot override" in str(ei.value)


def test_enabled_gate_absent_refuses_loud(tmp_path, backend):
    _make_store(tmp_path, passed=None, backend=backend)      # no gate_verdict.json
    with pytest.raises(SystemExit) as ei:
        sr.build_form_channel("paragraph_plan", "a query", dials=_enabled(),
                              root=tmp_path)
    assert "absent" in str(ei.value)


# --------------------------------------------------------------------------- #
# defective rows are never retrieved (even ranked first)
# --------------------------------------------------------------------------- #
def test_defective_row_never_retrieved(tmp_path, backend):
    _make_store(tmp_path, passed=True, backend=backend)
    # query == the defective row's own prose: it would be the #1 cosine match if
    # it were a candidate. It must be absent; a non-defective row is returned.
    out = sr.build_form_channel("paragraph_plan", _PROSE["PP-x-p04"], k=3,
                                dials=_enabled(), root=tmp_path)
    assert "PP-x-p04" not in out
    body = out.split("\n", 2)[2]
    payload = json.loads(body[body.index("["): body.rindex("]") + 1])
    got = {ex["row_id"] for ex in payload}
    assert "PP-x-p04" not in got
    assert got <= {"PP-x-p01", "PP-x-p02", "PP-x-p03"}


# --------------------------------------------------------------------------- #
# determinism
# --------------------------------------------------------------------------- #
def test_deterministic_for_fixed_store_and_query(tmp_path, backend):
    _make_store(tmp_path, passed=True, backend=backend)
    a = sr.build_form_channel("paragraph_plan", _PROSE["PP-x-p02"],
                              dials=_enabled(), root=tmp_path)
    b = sr.build_form_channel("paragraph_plan", _PROSE["PP-x-p02"],
                              dials=_enabled(), root=tmp_path)
    assert a == b


# --------------------------------------------------------------------------- #
# GATE HARDENING (deliverable 1): gate.passed is not enough — a store whose
# refusal proof does NOT hold (or that is not wired in) is REFUSED, even with
# gate.passed=true. Both directions, against the REAL figure_caption verdict (its
# honest OUT) AND a planted verdict.
# --------------------------------------------------------------------------- #
_REPO = Path(__file__).resolve().parents[1]


def _plant_verdict(tmp_path, backend, verdict, store="paragraph_plan"):
    """A store whose gate_verdict.json is exactly ``verdict`` (any shape)."""
    d = _make_store(tmp_path, passed=None, backend=backend, store=store)  # no verdict
    (d / "gate_verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    return d


def test_gate_passed_honours_real_figure_caption_out():
    # figure_caption ships gate.passed=true with refusal_proof_holds=false — its
    # honest OUT. The hardened predicate must REFUSE it (the live hazard the scout
    # named), and _gate_refusal must name the honest reason.
    verdict = json.loads((_REPO / "corpus_stores" / "figure_caption"
                          / "gate_verdict.json").read_text(encoding="utf-8"))
    assert verdict["gate"]["passed"] is True            # gate itself passes
    assert verdict["refusal_proof_holds"] is False      # but the proof fails
    assert sr._gate_passed(verdict) is False
    assert "refusal_proof_holds=false" in sr._gate_refusal(verdict)


def test_gate_passed_honours_real_authorized_verdict():
    # the OTHER direction: an authorized store (real paragraph_plan verdict) has a
    # holding refusal proof and is served.
    verdict = json.loads((_REPO / "corpus_stores" / "paragraph_plan"
                          / "gate_verdict.json").read_text(encoding="utf-8"))
    assert verdict["refusal_proof_holds"] is True and verdict["wired_in"] is True
    assert sr._gate_passed(verdict) is True
    assert sr._gate_refusal(verdict) is None


def test_planted_refusal_proof_false_refused():
    v = {"gate": {"passed": True}, "refusal_proof_holds": False, "wired_in": True}
    assert sr._gate_passed(v) is False
    assert "refusal_proof_holds=false" in sr._gate_refusal(v)


def test_planted_wired_in_false_refused():
    v = {"gate": {"passed": True}, "refusal_proof_holds": True, "wired_in": False}
    assert sr._gate_passed(v) is False
    assert "wired_in=false" in sr._gate_refusal(v)


def test_absent_proof_fields_still_pass_on_gate_alone():
    # backward compatibility: a leaner verdict with NO proof fields is judged on its
    # gate alone (the existing fixtures + older stores keep working — only an
    # EXPLICIT false refuses).
    assert sr._gate_passed({"gate": {"passed": True}}) is True
    assert sr._gate_refusal({"gate": {"passed": True}}) is None


def test_flipped_figure_caption_refuses_loud(tmp_path, backend):
    # end-to-end: a dial-enabled store carrying refusal_proof_holds=false raises
    # SystemExit with the honest reason — figure_caption cannot be smuggled in.
    _plant_verdict(tmp_path, backend,
                   {"gate": {"passed": True}, "refusal_proof_holds": False})
    with pytest.raises(SystemExit) as ei:
        sr.build_form_channel("paragraph_plan", "a query", dials=_enabled(),
                              root=tmp_path)
    msg = str(ei.value)
    assert "refusal_proof_holds=false" in msg and "cannot override" in msg


def test_flipped_unwired_store_refuses_loud(tmp_path, backend):
    _plant_verdict(tmp_path, backend, {"gate": {"passed": True}, "wired_in": False})
    with pytest.raises(SystemExit) as ei:
        sr.build_form_channel("paragraph_plan", "a query", dials=_enabled(),
                              root=tmp_path)
    assert "wired_in=false" in str(ei.value)


# --------------------------------------------------------------------------- #
# THE FORM-CHANNEL SIDECAR (deliverable 2): a served envelope yields a durable
# audit record; a disabled store yields nothing to bank.
# --------------------------------------------------------------------------- #
def test_record_carries_provenance_and_digest_no_prose(tmp_path, backend):
    _make_store(tmp_path, passed=True, backend=backend)
    served = sr.build_form_channel_and_record(
        "paragraph_plan", _PROSE["PP-x-p01"], dials=_enabled(), root=tmp_path)
    assert served is not None
    envelope, record = served
    assert envelope.startswith("<!-- FORM-EXEMPLARS -->")
    assert record["store"] == "paragraph_plan" and record["k"] == 3
    assert record["query_digest"].startswith("sha256:")
    assert record["ts"].endswith("+00:00") or record["ts"].endswith("Z")
    assert record["n_exemplars"] == len(record["exemplars"]) >= 1
    for e in record["exemplars"]:
        assert set(e) == {"row_id", "cos"}          # provenance ONLY
    # the record must carry NO prose and NO form fields (safe to keep on disk):
    blob = json.dumps(record)
    for prose in _PROSE.values():
        assert prose not in blob
    assert "embed_text" not in blob and "normalized_role" not in blob


def test_disabled_store_record_is_none_nothing_to_bank(tmp_path, backend):
    _make_store(tmp_path, passed=True, backend=backend)
    assert sr.build_form_channel_and_record(
        "paragraph_plan", "q", dials=_disabled(), root=tmp_path) is None


def test_write_form_channel_sidecar_roundtrips(tmp_path, backend):
    _make_store(tmp_path, passed=True, backend=backend)
    served = sr.build_form_channel_and_record(
        "paragraph_plan", _PROSE["PP-x-p02"], dials=_enabled(), root=tmp_path)
    assert served is not None
    _, record = served
    p = tmp_path / "dispatches" / sr.sidecar_name("paragraph_plan", "N4")
    written = sr.write_form_channel_sidecar(p, record)
    assert written == p and p.is_file()
    assert p.name == "_form_retrieval.paragraph_plan.N4.json"
    assert json.loads(p.read_text(encoding="utf-8")) == record


# ---------------------------------------------------------------------------
# BLOCKER-A: the compile chain's per-run dials resolution (dispatch._resolve_dials)
# ---------------------------------------------------------------------------


def test_resolve_dials_threads_the_allowlisted_profile():
    from laplace.pipeline import dispatch as dp
    d = dp._resolve_dials("dials-v2.yaml")
    assert d is not None and d.get("version") == "dials-v2"
    # v2 arms exactly the four provable lenses; figure_caption stays OFF (its
    # refusal proof fails — a dial is a permission, never a proof)
    stores = {k: v.get("enabled") for k, v in (d.get("stores") or {}).items()}
    assert stores.get("paragraph_plan") is True
    assert stores.get("figure_caption") is False


def test_resolve_dials_none_is_inert_and_fence_holds():
    from laplace.pipeline import dials as ds
    from laplace.pipeline import dispatch as dp
    import pytest as _pytest
    assert dp._resolve_dials(None) is None
    with _pytest.raises(ds.DialsProfileError):
        dp._resolve_dials("../evil.yaml")


def test_inject_form_channel_passes_the_resolved_dials(monkeypatch, tmp_path):
    """The wire hop: an explicit dials dict reaches build_form_channel_and_record
    — the hop that used to re-default to load_dials() -> v1."""
    from laplace.pipeline import dispatch as dp
    from laplace.pipeline import stage_retrieval as sr
    seen = {}
    def spy(store, query_text, k=3, dials=None, root="."):
        seen["dials"] = dials
        return None
    monkeypatch.setattr(sr, "build_form_channel_and_record", spy)
    marker = {"version": "test-thread", "stores": {}}
    dp._inject_form_channel([], "paragraph_plan", "q", "sec:x", None, tmp_path,
                            dials=marker)
    assert seen["dials"] is marker
