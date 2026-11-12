"""BITE B1 — the machine-adjudication organ (verdicts as files).

Unit tests for the Tier-1 rules, the verdict→record banking (existing makers,
actor="machine", fingerprinted), the file+exit-code transport law of
``parse_and_bank``, and the may_dismiss class-grain permission. Plus one driver
test that runs ``fixedpoint_adjudicate.py`` as the real workflow surface (the
planted-failure idiom) and confirms a machine confirmation exempts a deferred
finding at the route.
"""
from __future__ import annotations

import json

import pytest

import planted_fixture as pf
from laplace.pipeline import machine_adjudicate as MA
from laplace.pipeline import suppress as S
from laplace.pipeline import adjudicate as ADJ
from laplace.pipeline.ledger import read_jsonl

pytestmark = pytest.mark.unit


# a truly-unreferenced numbered equation (no \ref/\eqref, not boxed, name absent
# from prose) — the orphan the panel flags eq-unused.
_TEX_ORPHAN = r"""\section{Method}
Plain prose that never names the relation.
\begin{equation}\label{res:orphan-eq}
E = m c^2 .
\end{equation}
The relation states the mass energy equivalence in words alone.
"""

# the SAME equation, now \eqref'd by name in the prose — lifecycle satisfied.
_TEX_REFERENCED = r"""\section{Method}
\begin{equation}\label{res:used-eq}
E = m c^2 .
\end{equation}
The estimate in \eqref{res:used-eq} governs the reader's bound.
"""


# ---------------------------------------------------------------------------
# (a) a truly-unreferenced equation -> the rule CONFIRMS
# ---------------------------------------------------------------------------

def test_unreferenced_equation_confirms():
    f = {"id": "FB-a", "kind": "eq-unused", "node_id": "res:orphan-eq",
         "section": "N1"}
    decided, residue = MA.rule_verdicts([f], _TEX_ORPHAN, may_dismiss=["eq-unused"])
    assert residue == []
    assert len(decided) == 1
    assert decided[0]["verdict"] == "confirm"
    assert "orphan" in decided[0]["reason"].lower()


# ---------------------------------------------------------------------------
# (b) an equation referenced by name -> DISMISS; suppression fingerprint holds
# ---------------------------------------------------------------------------

def test_referenced_equation_dismisses_with_fingerprint(tmp_path):
    f = {"id": "FB-b", "kind": "eq-unused", "node_id": "res:used-eq",
         "section": "N1"}
    decided, residue = MA.rule_verdicts([f], _TEX_REFERENCED,
                                        may_dismiss=["eq-unused"])
    assert residue == []
    assert decided[0]["verdict"] == "dismiss"

    fb = tmp_path / "feedback.jsonl"
    rec = MA.bank_verdict(fb, decided[0], _TEX_REFERENCED, round=1, project="P")
    # banked via the EXISTING suppression maker, stamped actor="machine".
    assert S.is_suppression(rec)
    assert rec["source"] == "machine"
    assert rec["provenance"]["actor"] == "machine"
    # the additive top-level fingerprint == content_fingerprint(node text).
    assert rec["fingerprint"] == S.content_fingerprint(_TEX_REFERENCED)
    # and it rode the ONE door (append-only ledger).
    banked = [r for r in read_jsonl(fb) if S.is_suppression(r)]
    assert len(banked) == 1


# ---------------------------------------------------------------------------
# (c) an undecidable finding -> residue (not decided)
# ---------------------------------------------------------------------------

def test_undecidable_goes_to_residue():
    # the label the finding names is NOT present in the gathered prose -> the
    # rule cannot judge it -> residue (escalates to the referee).
    ghost = {"id": "FB-c1", "kind": "eq-unused", "node_id": "res:ghost",
             "section": "N1"}
    # a deferred kind with NO Tier-1 rule at all -> also residue.
    norule = {"id": "FB-c2", "kind": "eq-uninterpreted", "node_id": "eq:x",
              "section": "N1"}
    decided, residue = MA.rule_verdicts([ghost, norule], _TEX_ORPHAN,
                                        may_dismiss=["eq-unused", "eq-uninterpreted"])
    assert decided == []
    assert {r["id"] for r in residue} == {"FB-c1", "FB-c2"}


# ---------------------------------------------------------------------------
# (d) a planted residue with one missing verdict -> parse_and_bank exits nonzero
# ---------------------------------------------------------------------------

def test_parse_and_bank_exits_nonzero_on_missing_verdict(tmp_path):
    residue_dir = tmp_path / "rounds" / "adjudicate_r1"
    residue_dir.mkdir(parents=True)
    residue_path = residue_dir / "residue.json"
    residue_path.write_text(json.dumps({
        "round": 1, "project": "P", "may_dismiss": ["eq-unused"],
        "calibration_threshold": 5,
        "items": [
            {"finding_id": "FB-d1", "kind": "eq-unused", "node_id": "eq:a",
             "section": "N1", "node_text": "t"},
            {"finding_id": "FB-d2", "kind": "eq-unused", "node_id": "eq:b",
             "section": "N1", "node_text": "t"},
        ]}), encoding="utf-8")
    fb = tmp_path / "feedback.jsonl"
    # only ONE of the two items carries a verdict -> incomplete -> nonzero exit.
    verdicts = json.dumps([{"finding_id": "FB-d1", "verdict": "confirm",
                            "reason": "real"}])
    with pytest.raises(SystemExit) as ei:
        MA.parse_and_bank(residue_path, verdicts, fb)
    assert ei.value.code != 0
    # the transport law: NO verdicts.json on a failed pass (absent => step failed).
    assert not (residue_dir / "verdicts.json").exists()
    # atomic: nothing banked on an incomplete pass.
    assert read_jsonl(fb) == []


def test_parse_and_bank_banks_and_writes_on_complete(tmp_path):
    residue_dir = tmp_path / "rounds" / "adjudicate_r1"
    residue_dir.mkdir(parents=True)
    residue_path = residue_dir / "residue.json"
    residue_path.write_text(json.dumps({
        "round": 1, "project": "P", "may_dismiss": ["eq-unused"],
        "calibration_threshold": 5,
        "items": [{"finding_id": "FB-e1", "kind": "eq-unused", "node_id": "eq:a",
                   "section": "N1", "node_text": "some node text"}]}),
        encoding="utf-8")
    fb = tmp_path / "feedback.jsonl"
    res = MA.parse_and_bank(
        residue_path,
        json.dumps([{"finding_id": "FB-e1", "verdict": "confirm", "reason": "real"}]),
        fb)
    assert res["ok"] and res["banked"] == 1
    assert (residue_dir / "verdicts.json").exists()
    recs = read_jsonl(fb)
    assert any(r.get("record") == ADJ.CONFIRM and r.get("source") == "machine"
               for r in recs)


# ---------------------------------------------------------------------------
# (e) a kind OUTSIDE may_dismiss cannot be dismissed by Tier-1 (-> escalate)
# ---------------------------------------------------------------------------

def test_kind_outside_may_dismiss_cannot_be_dismissed():
    # this finding's rule WOULD dismiss (referenced eq), but eq-unused is not in
    # may_dismiss -> the verdict is downgraded to escalate, never a dismissal.
    f = {"id": "FB-e", "kind": "eq-unused", "node_id": "res:used-eq",
         "section": "N1"}
    decided, residue = MA.rule_verdicts([f], _TEX_REFERENCED,
                                        may_dismiss=["citation-first-use"])
    assert decided[0]["verdict"] == "escalate"
    assert "may_dismiss" in decided[0]["reason"]

    # and the write gate re-enforces it: banking a dismiss on a barred kind lands
    # a DEFER (escalate), never a suppression.
    import tempfile
    from pathlib import Path
    fb = Path(tempfile.mkdtemp()) / "feedback.jsonl"
    MA.bank_all(fb, [{"finding_id": "FB-e", "kind": "eq-unused", "node_id": "x",
                      "section": "N1", "verdict": "dismiss", "reason": "r"}],
                "text", may_dismiss=["citation-first-use"])
    recs = read_jsonl(fb)
    assert not any(S.is_suppression(r) for r in recs)
    assert any(r.get("record") == ADJ.DEFER for r in recs)


# ---------------------------------------------------------------------------
# the meta-signal: N machine-dismissals of a kind this run -> a calibration intent
# ---------------------------------------------------------------------------

def test_calibration_intent_on_threshold(tmp_path):
    fb = tmp_path / "feedback.jsonl"
    decisions = [{"finding_id": f"FB-{i}", "kind": "citation-first-use",
                  "node_id": f"k{i}", "section": "N1", "verdict": "dismiss",
                  "reason": "standalone"} for i in range(3)]
    out = MA.bank_all(fb, decisions, "node text", round=1, project="P",
                      may_dismiss=["citation-first-use"], calibration_threshold=3)
    assert out["dismiss_counts"]["citation-first-use"] == 3
    assert len(out["calibration"]) == 1
    cal = out["calibration"][0]
    assert cal["record"] == ADJ.CALIBRATION_INTENT
    assert cal["finding_kind"] == "citation-first-use"
    assert cal["provenance"]["actor"] == "machine"


# ---------------------------------------------------------------------------
# driver: the real workflow surface + the route exemption it enables
# ---------------------------------------------------------------------------

def _env(tmp_path, sections):
    env = tmp_path / "adj"
    env.mkdir(parents=True, exist_ok=True)
    body = ("\\documentclass{article}\\begin{document}\n"
            + "".join(f"\\input{{{s}}}\n" for s in sections)
            + "\\end{document}\n")
    (env / "main.tex").write_text(body, encoding="utf-8")
    return env


def _dials(tmp_path, may_dismiss, defer_kinds):
    d = tmp_path / "dials.yaml"
    d.write_text(
        "routing:\n  defer_kinds: [" + ", ".join(defer_kinds) + "]\n"
        "machine_adjudication:\n  enabled: true\n  calibration_threshold: 5\n"
        "  may_dismiss: [" + ", ".join(may_dismiss) + "]\n",
        encoding="utf-8")
    return str(d)


def test_workflow_confirms_orphan_and_route_dispatches_it(tmp_path, monkeypatch):
    # N1 carries a genuine orphan equation (eq-unused). The machine CONFIRMS it;
    # the confirmation then exempts it from the class-grain defer at the route.
    env = _env(tmp_path, ["N1"])
    (env / "N1.tex").write_text(_TEX_ORPHAN, encoding="utf-8")
    pf.write_plan(env / "plan.json", ["N1"])
    proj = pf.make_project(plan_path=env / "plan.json")
    # the mech-panel shape: node_id carries the raw label, section the fragment.
    finding = pf.finding("eq-unused", section="N1", node_id="res:orphan-eq",
                         where="N1:res:orphan-eq")
    fb = pf.write_feedback(env / "feedback.jsonl", [finding])
    dials = _dials(tmp_path, ["eq-unused"], ["eq-unused"])

    adj = pf.run_adjudicate(str(env / "main.tex"), str(fb), str(env), monkeypatch,
                            proj, dials_path=dials, round_no=1)
    assert adj["decided"] == 1 and adj["banked"] == 1 and adj["residue"] == 0

    recs = read_jsonl(fb)
    assert ADJ.confirmed_ids(recs) == {finding["id"]}
    conf = [r for r in recs if r.get("record") == ADJ.CONFIRM][0]
    assert conf["source"] == "machine" and conf.get("fingerprint")

    # the route now dispatches the confirmed orphan despite its deferred class.
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj,
                     dials_path=dials)
    assert r["deferred"] == 0
    assert "N1" in r["dirty_sections"]


def test_workflow_dismissal_is_applied_at_route(tmp_path, monkeypatch):
    # B1 + item-5: N1's equation is now \eqref'd -> the machine DISMISSES the
    # stale eq-unused, banks a suppression at label grain, and the route (with
    # \label-indexed node_text) actually APPLIES it: the finding is suppressed,
    # not kept.
    env = _env(tmp_path, ["N1"])
    (env / "N1.tex").write_text(_TEX_REFERENCED, encoding="utf-8")
    pf.write_plan(env / "plan.json", ["N1"])
    proj = pf.make_project(plan_path=env / "plan.json")
    finding = pf.finding("eq-unused", section="N1", node_id="res:used-eq",
                         where="N1:res:used-eq")
    fb = pf.write_feedback(env / "feedback.jsonl", [finding])
    dials = _dials(tmp_path, ["eq-unused"], ["eq-unused"])

    adj = pf.run_adjudicate(str(env / "main.tex"), str(fb), str(env), monkeypatch,
                            proj, dials_path=dials, round_no=1)
    assert adj["banked"] == 1
    supps = [r for r in read_jsonl(fb) if S.is_suppression(r)]
    assert supps and supps[0]["source"] == "machine"

    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj,
                     dials_path=dials)
    assert r["suppressed"] == 1        # the machine dismissal was APPLIED
    assert r["kept"] == 0
    assert "N1" not in r["dirty_sections"]


def test_workflow_writes_residue_for_undecidable(tmp_path, monkeypatch):
    env = _env(tmp_path, ["N1"])
    (env / "N1.tex").write_text(_TEX_ORPHAN, encoding="utf-8")
    pf.write_plan(env / "plan.json", ["N1"])
    proj = pf.make_project(plan_path=env / "plan.json")
    # eq-uninterpreted has no Tier-1 rule -> residue -> residue.json for a referee.
    finding = pf.finding("eq-uninterpreted", section="N1", node_id="eq:x")
    fb = pf.write_feedback(env / "feedback.jsonl", [finding])
    dials = _dials(tmp_path, ["eq-uninterpreted"], ["eq-uninterpreted"])
    adj = pf.run_adjudicate(str(env / "main.tex"), str(fb), str(env), monkeypatch,
                            proj, dials_path=dials, round_no=1)
    assert adj["residue"] == 1 and adj["decided"] == 0
    residue_doc = json.loads((env / "rounds" / "adjudicate_r1" / "residue.json")
                             .read_text(encoding="utf-8"))
    assert residue_doc["items"][0]["finding_id"] == finding["id"]
    assert "may_dismiss" in residue_doc


# ---------------------------------------------------------------------------
# the judge's refutation probes, banked as regressions: a comment is not prose
# ---------------------------------------------------------------------------

_TEX_COMMENT_XREF = r"""\section{Method}
% see \eqref{res:ghost-eq} for the old derivation
\begin{equation}\label{res:ghost-eq}
E = m c^2 .
\end{equation}
Prose that never references the relation.
"""

_TEX_COMMENT_NAME = r"""\section{Method}
% res:ghost-name is discussed later
\begin{equation}\label{res:ghost-name}
E = m c^2 .
\end{equation}
Prose that never references the relation.
"""

_TEX_ALIGN_BOXED_OTHER = r"""\section{Method}
\begin{align}
\boxed{F = m a} \label{res:boxed-one} \\
E = m c^2 \label{res:plain-two}
\end{align}
Prose that discusses neither by name.
"""

_TEX_COMMENT_CITE = r"""\section{Method}
% \cite{ghostkey2001} was the old anchor
Prose that cites nothing at all.
"""


def test_comment_only_xref_does_not_dismiss():
    f = {"id": "FB-cx", "kind": "eq-unused", "node_id": "res:ghost-eq",
         "section": "N1"}
    decided, residue = MA.rule_verdicts([f], _TEX_COMMENT_XREF,
                                        may_dismiss=["eq-unused"])
    assert residue == []
    assert decided[0]["verdict"] == "confirm"      # a comment is not prose


def test_comment_only_name_mention_does_not_dismiss():
    f = {"id": "FB-cn", "kind": "eq-unused", "node_id": "res:ghost-name",
         "section": "N1"}
    decided, residue = MA.rule_verdicts([f], _TEX_COMMENT_NAME,
                                        may_dismiss=["eq-unused"])
    assert residue == []
    assert decided[0]["verdict"] == "confirm"


def test_boxed_on_other_align_row_does_not_launder_neighbour():
    f = {"id": "FB-bx", "kind": "eq-unused", "node_id": "res:plain-two",
         "section": "N1"}
    decided, residue = MA.rule_verdicts([f], _TEX_ALIGN_BOXED_OTHER,
                                        may_dismiss=["eq-unused"])
    assert residue == []
    assert decided[0]["verdict"] == "confirm"      # its own row carries no \boxed
    # while the row that IS boxed still dismisses
    g = {"id": "FB-bx2", "kind": "eq-unused", "node_id": "res:boxed-one",
         "section": "N1"}
    decided2, _ = MA.rule_verdicts([g], _TEX_ALIGN_BOXED_OTHER,
                                   may_dismiss=["eq-unused"])
    assert decided2[0]["verdict"] == "dismiss"


def test_comment_only_cite_goes_to_residue_not_dismiss():
    f = {"id": "FB-cc", "kind": "citation-first-use", "node_id": "ghostkey2001",
         "section": "N1"}
    decided, residue = MA.rule_verdicts([f], _TEX_COMMENT_CITE,
                                        may_dismiss=["citation-first-use"])
    assert decided == []
    assert len(residue) == 1                       # uncited in real prose -> referee
