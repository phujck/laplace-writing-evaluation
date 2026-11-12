"""R9 Caption-blind — plumbing tests (hermetic, no live LLM).

builder ≠ judge: these exercise the WIRING (the seal, the pack, verdict parsing, the
pour, the file+exit-code transport, the roster registration), never the read QUALITY
(that needs a real vision read at candidate-lock + Gerard). The vision judgment is
STUBBED — a hand-written raw reply drives parse + pour — exactly as A1's fixture drove
the sealed reader wiring without a model.
"""
from pathlib import Path

import json

import pytest

from laplace.pipeline import ledger
from laplace.pipeline import readers as R
from laplace.pipeline.readers import caption_blind as CB
from laplace.pipeline.readers import verdict_io
from laplace.pipeline.schema import WORK_KINDS, WORK_TO_LAYER


# A synthetic manuscript: a rich figure (claim + evidence-per-panel + limitation in
# the caption) and a BARE figure whose caption is provenance-only. The body carries a
# sentinel that must NEVER reach the caption-blind payload.
_CB_FIXTURE = r"""
\documentclass{article}
\begin{document}
\section{Foundations}
BODYSENTINEL the operator formalism is developed at length in the body prose here,
far from the figure the blind reader is allowed to see.
\begin{figure}
\includegraphics{recon}
\caption{Reconstruction error $\varepsilon(\tau)$ versus depth for the spectral
method: panel (a) the measured error on random instances, panel (b) the exact
resolvent bound. Shown only for $n \le 100$, where the expansion converges.}
\label{fig:good}
\end{figure}
\begin{figure}
\includegraphics{raw}
\caption{Run 3, seed 42.}
\label{fig:bare}
\end{figure}
\end{document}
"""


def _tex(tmp_path: Path) -> Path:
    f = tmp_path / "m.tex"
    f.write_text(_CB_FIXTURE)
    return f


def _mock_insp():
    """A minimal Inspection carrying the two figure crops R9 pairs with captions —
    labels match the fixture so the pack can join crop→caption."""
    from laplace.pipeline import visual_gate as vg
    insp = vg.Inspection(pdf="x.pdf", n_pages=2, dpi=150, out_dir="/tmp")
    insp.views = {
        "figure_crops": [
            {"label": "fig:good", "page": 2, "path": "/tmp/fig-good.png"},
            {"label": "fig:bare", "page": 2, "path": "/tmp/fig-bare.png"},
        ],
    }
    insp.overfull = []
    return insp


# --- registration: R9 is on the roster and routes through the existing schema -----

def test_r9_registered_and_routes_to_figures():
    r = R.READERS["R9"]
    assert r.organ == "rasteriser" and r.runnable_now is False
    assert r.cadence.read == "candidate_lock" and r.cadence.floor is None
    assert r.panel_label == "caption_blind"
    assert r.dimension == "reader_reconstruction"
    # its three owned kinds all route to the figures stage (figure-standard-kind)
    for k in r.owned_kinds:
        rk = R.READER_FINDING_KINDS[k]
        assert rk.reader == "R9"
        assert rk.work_kind in WORK_KINDS and rk.work_kind == "figure"
        assert WORK_TO_LAYER[rk.work_kind] == "figures" == rk.owning_stage
    # the two roster invariants still hold with R9 added
    assert R.verify_single_ownership()["ok"]
    assert R.verify_kind_partition()["ok"]


# --- the seal is genuinely BLIND: caption+image bytes only ------------------------

def test_seal_is_tight_no_body_or_provenance(tmp_path):
    p = CB.pack_caption_blind(_mock_insp(), _tex(tmp_path))
    # the captions ARE present, paired with their labels
    assert "Reconstruction error" in p["sealed_input"]
    assert "Run 3, seed 42." in p["sealed_input"]
    assert "[fig:good]" in p["sealed_input"] and "[fig:bare]" in p["sealed_input"]
    # the BODY is physically absent from BOTH the sealed input and the prompt
    assert "BODYSENTINEL" not in p["sealed_input"]
    assert "BODYSENTINEL" not in p["prompt"]
    assert "operator formalism" not in p["prompt"]
    # the seal holds, and the images (the crop bytes' references) rode along
    assert p["seal_check"]["ok"], p["seal_check"]["leaks"]
    assert [i["path"] for i in p["images"]] == ["/tmp/fig-good.png", "/tmp/fig-bare.png"]
    assert p["allowed_kinds"] == list(R.READERS["R9"].owned_kinds)


def test_seal_catches_body_and_provenance_leaks():
    # a section heading smuggled into a caption-only payload is CAUGHT (body leak)
    body = CB.caption_blind_seal({"sealed_input": r"a caption \section{Methods} here",
                                  "prompt": ""})
    assert not body["ok"]
    assert any(l["where"] == "body-leak" for l in body["leaks"])
    # a provenance/spec sentinel is caught via the shared sealed-reader seal surface
    prov = CB.caption_blind_seal({"sealed_input": "caption with %<sid>-p3 provenance",
                                  "prompt": "POLICY: ..."})
    assert not prov["ok"]
    assert {l["sentinel"] for l in prov["leaks"]} >= {"%<sid>", "POLICY"}


# --- PASS case: a self-sufficient figure yields NO finding ------------------------

def test_pass_case_identifiable_figure_is_clean():
    raw = json.dumps([{
        "where": "fig:good", "identifiable": True,
        "claim": "the spectral method reconstructs the spectrum within the stated error",
        "evidence": ["measurement", "proof"],
        "limitation": "holds only for n <= 100",
    }])
    findings = CB.parse_caption_blind_verdict(raw)
    assert findings == []                                   # PASS — nothing to pour
    rec = verdict_io.build_verdict("R9", None, findings)
    assert rec["clean"] is True and rec["findings_n"] == 0
    assert rec["label"] == "caption_blind"                  # label single-sourced from roster


# --- FAIL case: a provenance-only caption fails all three facets -------------------

def test_fail_case_parses_three_missing_facets():
    raw = json.dumps([{
        "where": "fig:bare", "identifiable": False,
        "claim": "unclear", "evidence": [], "limitation": "unclear",
        "caption": "Run 3, seed 42.",
    }])
    findings = CB.parse_caption_blind_verdict(raw)
    assert {f["kind"] for f in findings} == {
        "caption-blind-claim", "caption-blind-evidence", "caption-blind-limitation"}
    for f in findings:
        assert f["reader"] == "R9"
        assert f["owning_stage"] == "figures"               # figure-routed
        assert f["dimension"] == "reader_reconstruction"
        assert f["identifiable"] is False


def test_fail_case_pours_through_the_hardened_door(tmp_path):
    tex = _tex(tmp_path)
    raw = json.dumps([{
        "where": "fig:bare", "identifiable": False,
        "claim": "unclear", "evidence": [], "limitation": "unclear",
        "caption": "Run 3, seed 42.",
    }])
    findings = CB.parse_caption_blind_verdict(raw)
    feedback = tmp_path / "feedback.jsonl"
    secs = CB.section_by_label(tex)
    expected_sec = secs["fig:bare"]
    assert expected_sec, "the fixture figure must resolve to a section anchor"

    res = CB.pour_caption_blind(feedback, findings, project="ssg", sections=secs)
    assert res["poured"] == 3 and res["refused"] == 0

    recs = ledger.read_jsonl(feedback)
    assert len(recs) == 3
    for r in recs:
        assert r["id"], "every poured finding carries a mandatory id"
        assert r["section"] == expected_sec                 # section anchor stamped
        assert r["anchor"]["section"] == expected_sec
        assert r["source"] == "R9"

    # idempotent: re-pouring the same FAILED figure deposits no double-live rows
    res2 = CB.pour_caption_blind(feedback, findings, project="ssg", sections=secs)
    assert res2["poured"] == 0 and res2["idempotent"] == 3
    assert len(ledger.read_jsonl(feedback)) == 3


def test_pour_refuses_a_sectionless_finding(tmp_path):
    # the door refuses (records, never raises) a finding with no locatable section
    raw = json.dumps([{"where": "fig:orphan", "identifiable": False,
                       "claim": "unclear", "evidence": ["measurement"],
                       "limitation": "n <= 100"}])
    findings = CB.parse_caption_blind_verdict(raw)      # one finding: claim only
    feedback = tmp_path / "feedback.jsonl"
    res = CB.pour_caption_blind(feedback, findings, project="ssg")  # no section anywhere
    assert res["refused"] == 1 and res["poured"] == 0
    assert res["refusals"] and "section" in res["refusals"][0]


# --- the file+exit-code transport dispatches the R9 organ -------------------------

def test_verdict_io_dispatches_caption_blind_organ():
    raw = json.dumps([{"where": "fig:bare", "identifiable": False,
                       "claim": "unclear", "evidence": [], "limitation": "unclear"}])
    out = verdict_io.parse_reply("caption_blind", "R9", raw)
    assert len(out) == 3 and all(f["reader"] == "R9" for f in out)
    # garbage-is-FAILED is organ-agnostic: an empty reply carries no JSON list
    assert verdict_io.parse_reply("caption_blind", "R9", "") == []


def test_malformed_verdict_never_crashes():
    assert CB.parse_caption_blind_verdict("not json") == []
    assert CB.parse_caption_blind_verdict("") == []
    assert CB.parse_caption_blind_verdict("{}") == []


# --- the LIVE-FIRE dispatch transport (vision STUBBED) ----------------------------
# The harnessed lock stage's R9 rasteriser branch ends by piping the raw vision reply
# through the verdict_io 'caption_blind' organ (write CLI) — the verdict rides a FILE
# + an EXIT CODE, never an agent paraphrase. These drive that exact transport with a
# hand-written reply (the vision judgment is stubbed, as A1's fixture stubbed the
# sealed read), proving the dispatch the JS wires actually banks a verdict.

def test_r9_dispatch_verdict_file_and_exit_code_on_failed_figure(tmp_path):
    # a FAILED figure (provenance-only caption) -> unclean verdict FILE + EXIT 1.
    raw = json.dumps([{"where": "fig:bare", "identifiable": False,
                       "claim": "unclear", "evidence": [], "limitation": "unclear"}])
    lock_dir = tmp_path / "rounds" / "lock_r1"
    # main() reads the raw reply from stdin; drive it with a captured stdin.
    import io
    import sys
    saved = sys.stdin
    try:
        sys.stdin = io.StringIO(raw)
        rc = verdict_io.main(["write", "caption_blind", "R9", "caption_blind",
                              str(lock_dir)])
    finally:
        sys.stdin = saved
    assert rc == 1                                          # nonzero == unclean
    rec = json.loads((lock_dir / "R9_verdict.json").read_text(encoding="utf-8"))
    assert rec["label"] == "caption_blind"                  # single-sourced from roster
    assert rec["clean"] is False and rec["findings_n"] == 3
    assert len(rec["finding_ids"]) == 3


def test_r9_dispatch_verdict_clean_on_self_sufficient_figure(tmp_path):
    # a self-sufficient figure -> clean verdict FILE + EXIT 0.
    raw = json.dumps([{"where": "fig:good", "identifiable": True,
                       "claim": "the method reconstructs the spectrum within the error",
                       "evidence": ["measurement", "proof"], "limitation": "n <= 100"}])
    lock_dir = tmp_path / "rounds" / "lock_r1"
    import io
    import sys
    saved = sys.stdin
    try:
        sys.stdin = io.StringIO(raw)
        rc = verdict_io.main(["write", "caption_blind", "R9", "caption_blind",
                              str(lock_dir)])
    finally:
        sys.stdin = saved
    assert rc == 0                                          # zero == clean
    rec = json.loads((lock_dir / "R9_verdict.json").read_text(encoding="utf-8"))
    assert rec["clean"] is True and rec["findings_n"] == 0


def test_r9_dispatch_empty_reply_is_failed_not_clean(tmp_path):
    # honest gating: an empty/garbage reply (a missing PDF / broken read) reads as
    # FAILED, never a false clean — the silence-never-passes floor at the transport.
    lock_dir = tmp_path / "rounds" / "lock_r1"
    import io
    import sys
    saved = sys.stdin
    try:
        sys.stdin = io.StringIO("")
        rc = verdict_io.main(["write", "caption_blind", "R9", "caption_blind",
                              str(lock_dir)])
    finally:
        sys.stdin = saved
    assert rc == 1
    rec = json.loads((lock_dir / "R9_verdict.json").read_text(encoding="utf-8"))
    assert rec["clean"] is False and rec.get("failed") is True


def test_r9_is_in_the_lock_roster_dial():
    # the dials roster the harnessed lock stage reads MUST include R9 (the dispatch
    # branch only fires for a rostered lock reader).
    from laplace.pipeline import dials
    assert "R9" in dials.load_dials()["loop"]["lock"]["readers"]
    assert "R9" in dials.defaults()["loop"]["lock"]["readers"]
