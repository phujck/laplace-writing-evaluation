"""BITE B2 — the mechanical panel honours machine adjudication.

Driven as the REAL script (``.claude/workflows/fixedpoint_mechround.py``) via the
planted-failure idiom (runpy in-process over a throwaway project). The property
under test: ``read_apparatus`` findings that have been machine-DISMISSED (a live
suppression) or ESCALATED (a live machine ``make_defer`` noted ``escalate: ...``)
no longer hold ``technical_support`` unclean, while a machine-CONFIRMED finding
still HOLDS (real open work). The counters ride the apparatus entry's flags as
the honesty trail. With an empty ledger the panel is byte-identical to pre-B2.

The apparatus/claims entries both feed the HARD ``technical_support`` dim
(``convergence.evaluate_round``: ``clean("claims") and hard_ok("apparatus")``), so
both must clear for lock — the tests assert both.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import planted_fixture as pf
from laplace.pipeline import adjudicate as ADJ
from laplace.pipeline import suppress as S
from laplace.pipeline.readers.apparatus import read_apparatus

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# a fixture of three orphan equations (three eq-unused apparatus findings, each
# anchored on its own \label so its ruling fingerprints against a real fragment)
# ---------------------------------------------------------------------------

_FRAGS = {
    "N1": (r"\section{Alpha}\label{sec:a}" "\n"
           "Plain prose about alpha for the reader here.\n"
           r"\begin{equation}\label{res:a}" "\nE=mc^2.\n" r"\end{equation}" "\n"),
    "N2": (r"\section{Beta}\label{sec:b}" "\n"
           "Plain prose about beta for the reader here.\n"
           r"\begin{equation}\label{res:b}" "\nF=ma.\n" r"\end{equation}" "\n"),
    "N3": (r"\section{Gamma}\label{sec:g}" "\n"
           "Plain prose about gamma for the reader here.\n"
           r"\begin{equation}\label{res:c}" "\np=mv.\n" r"\end{equation}" "\n"),
}


def _env(tmp_path, records):
    """Write the three-orphan manuscript + plan + ledger; return (md, fb, proj)."""
    md = tmp_path / "m"
    md.mkdir(parents=True, exist_ok=True)
    body = ("\\documentclass{article}\\begin{document}\n"
            + "".join(f"\\input{{{s}}}\n" for s in _FRAGS)
            + "\\end{document}\n")
    (md / "main.tex").write_text(body, encoding="utf-8")
    for stem, content in _FRAGS.items():
        (md / f"{stem}.tex").write_text(content, encoding="utf-8")
    pf.write_plan(md / "plan.json", list(_FRAGS))
    fb = pf.write_feedback(md / "feedback.jsonl", records)
    proj = pf.make_project(plan_path=md / "plan.json")
    return md, fb, proj


def _panel_entry(round_doc, label):
    return next(p for p in round_doc["panel"] if p["label"] == label)


def _fp(stem):
    """The content fingerprint of a fragment's CURRENT text — what a live (non-stale)
    ruling on that fragment's \\label must carry to match."""
    return S.content_fingerprint(_FRAGS[stem])


def _machine_suppression(node_id, stem, kind="eq-unused"):
    """A machine dismissal of ``kind`` on ``node_id``, fingerprinted (like
    machine_adjudicate.bank_verdict) against the CURRENT fragment text."""
    return S.make_suppression(node_id, kind, _FRAGS[stem], reason="rule dismissed",
                              actor="machine", round=1, project=pf.THROWAWAY,
                              section=stem)


def _machine_escalate(finding_id, node_id, stem, kind="eq-unused"):
    """A machine escalation (make_defer noted 'escalate: ...') carrying the additive
    top-level fingerprint machine_adjudicate.bank_verdict stamps."""
    rec = ADJ.make_defer(finding_id, node_id=node_id, kind=kind, section=stem,
                         note="escalate: undecidable by the tier-1 rule",
                         actor="machine", round=1, project=pf.THROWAWAY)
    rec["fingerprint"] = _fp(stem)
    return rec


def _machine_confirm(finding_id, node_id, stem, kind="eq-unused"):
    """A machine confirmation carrying the additive top-level fingerprint."""
    rec = ADJ.make_confirmation(finding_id, node_id=node_id, kind=kind, section=stem,
                                actor="machine", round=1, project=pf.THROWAWAY)
    rec["fingerprint"] = _fp(stem)
    return rec


def _run(md, fb, proj, monkeypatch):
    _s, doc = pf.run_mechround(str(md / "main.tex"), "-", str(md / "r.json"),
                               str(fb), str(md), monkeypatch, proj, round_no=1)
    return doc


def _counter(entry):
    """The single machine-adjudicated counter flag on an entry, or None."""
    hits = [f for f in entry["flags"] if "dismissed_n" in f]
    return hits[0] if hits else None


# ---------------------------------------------------------------------------
# (a) suppressed + escalated + confirmed -> UNCLEAN (the confirmation holds),
#     counters dismissed_n=1 escalated_n=1
# ---------------------------------------------------------------------------

def test_trio_confirmation_holds_panel_unclean(tmp_path, monkeypatch):
    # res:c carries BOTH a confirmation and a suppression — the confirmation WINS
    # (held), and removing it (test b) lets the suppression dismiss it.
    records = [
        _machine_suppression("res:a", "N1"),                       # dismiss
        _machine_escalate("FB-b", "res:b", "N2"),                  # escalate
        _machine_confirm("FB-c", "res:c", "N3"),                   # confirm (holds)
        _machine_suppression("res:c", "N3"),                       # loses to confirm
    ]
    md, fb, proj = _env(tmp_path, records)
    doc = _run(md, fb, proj, monkeypatch)

    app = _panel_entry(doc, "apparatus")
    claims = _panel_entry(doc, "claims")
    assert app["clean"] is False          # the confirmed res:c still holds
    assert claims["clean"] is False       # both feed technical_support
    ctr = _counter(app)
    assert ctr is not None and ctr["issue"] == "machine-adjudicated"
    assert ctr["dismissed_n"] == 1 and ctr["escalated_n"] == 1
    # the held finding present as a real flag; the dismissed/escalated are NOT
    held = [f for f in app["flags"] if f.get("kind") == "eq-unused"]
    assert [f["where"] for f in held] == ["gamma:res:c"]


# ---------------------------------------------------------------------------
# (b) remove the confirmation -> the suppression on res:c takes over -> CLEAN,
#     the counters remain
# ---------------------------------------------------------------------------

def test_remove_confirmation_panel_clean_with_counters(tmp_path, monkeypatch):
    records = [
        _machine_suppression("res:a", "N1"),       # dismiss
        _machine_escalate("FB-b", "res:b", "N2"),  # escalate
        _machine_suppression("res:c", "N3"),       # dismiss (no confirmation now)
    ]
    md, fb, proj = _env(tmp_path, records)
    doc = _run(md, fb, proj, monkeypatch)

    app = _panel_entry(doc, "apparatus")
    claims = _panel_entry(doc, "claims")
    assert app["clean"] is True           # every finding adjudicated away
    assert claims["clean"] is True
    ctr = _counter(app)
    assert ctr is not None
    assert ctr["dismissed_n"] == 2 and ctr["escalated_n"] == 1
    # no eq-unused rides as a real (blocking) flag any more
    assert not [f for f in app["flags"] if f.get("kind") == "eq-unused"]
    # technical_support is a HARD dim; with claims+apparatus clean it must pass
    assert doc["contract"]["hard"]["technical_support"] is True


# ---------------------------------------------------------------------------
# (c) no-adjudication probe: an empty ledger is BYTE-IDENTICAL to the pre-B2
#     panel (deferred classes still block; no machine-adjudicated flag)
# ---------------------------------------------------------------------------

def test_empty_ledger_byte_identical(tmp_path, monkeypatch):
    md, fb, proj = _env(tmp_path, [])
    doc = _run(md, fb, proj, monkeypatch)

    app = _panel_entry(doc, "apparatus")
    claims = _panel_entry(doc, "claims")
    # the exact flags the UNMODIFIED logic produced: read_apparatus findings mapped
    expect_flags = [{"where": f.get("where", ""), "issue": f.get("issue", ""),
                     "kind": f.get("kind")}
                    for f in (read_apparatus(str(md / "main.tex"), None, proj.name)
                              .get("findings") or [])]
    assert app == {"label": "apparatus", "clean": False, "flags": expect_flags}
    assert claims == {"label": "claims", "clean": False, "flags": []}
    assert _counter(app) is None          # no honesty-trail flag when nothing ruled


# ---------------------------------------------------------------------------
# (d) staleness: a suppression whose fingerprint no longer matches the current
#     fragment does NOT dismiss — the finding is HELD
# ---------------------------------------------------------------------------

def test_stale_suppression_does_not_dismiss(tmp_path, monkeypatch):
    stale = _machine_suppression("res:a", "N1")
    stale["fingerprint"] = "deadbeefdeadbeef"        # no longer matches N1's content
    stale["provenance"]["fingerprint"] = "deadbeefdeadbeef"
    md, fb, proj = _env(tmp_path, [stale])
    doc = _run(md, fb, proj, monkeypatch)

    app = _panel_entry(doc, "apparatus")
    assert app["clean"] is False
    # res:a is HELD (stale never dismisses), and no counter is added (0 dismissals)
    held = [f["where"] for f in app["flags"] if f.get("kind") == "eq-unused"]
    assert "alpha:res:a" in held
    assert _counter(app) is None


def test_counter_flag_is_not_a_finding_downstream(tmp_path):
    """The judge's leak probe, banked: the machine-adjudicated counter flag must
    not surface as a phantom hard finding in G nor inflate n_flags."""
    import json as _json
    from laplace.manuscript import review_surface as RS

    counter = {"issue": "machine-adjudicated", "dismissed_n": 1, "escalated_n": 2}
    real = {"issue": "eq-unused", "where": "gamma:res:x", "kind": "eq-unused"}
    data = {"panel": [{"label": "apparatus", "clean": True, "flags": [counter]},
                      {"label": "claims", "clean": False, "flags": [real]}]}
    rd = tmp_path / "judge_rounds"
    rd.mkdir()
    (rd / "2026-07-10_round1.json").write_text(_json.dumps(data), encoding="utf-8")
    _, findings = RS._round_findings(tmp_path)
    assert all(f.get("issue") != "machine-adjudicated" for f in findings)
    assert any(f.get("issue") == "eq-unused" for f in findings)

    n = sum(len([f for f in (p or {}).get("flags") or []
                 if "dismissed_n" not in f]) for p in data["panel"])
    assert n == 1
