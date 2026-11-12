"""BITE B1 — the MACHINE-ADJUDICATION organ (verdicts as files).

The author's binding ruling (2026-07-10): the machine may CONFIRM or DISMISS
every deferred finding class; every verdict is an ``actor:"machine"`` stamped,
fingerprinted, revocable ledger record on the one feedback door; anything the
Tier-1 rules cannot decide ESCALATES to a referee. This module is the library
(unit-testable, no filesystem side-channels beyond the append-only ledger):

  * :func:`rule_verdicts` — the Tier-1 deterministic rules. Each rule returns
    ``(verdict, reason)`` or ``None`` (undecidable → residue). A ``dismiss`` on a
    kind outside ``may_dismiss`` is DOWNGRADED to ``escalate`` (the dial's
    class-grain permission, enforced here, not believed).
  * :func:`bank_all` / :func:`bank_verdict` — verdict → ledger record via the
    EXISTING makers (:func:`adjudicate.make_confirmation` /
    :func:`suppress.make_suppression` / :func:`adjudicate.make_defer`), each
    carrying the additive top-level ``fingerprint`` = content fingerprint of the
    node's text, so a later material edit makes the ruling stale exactly as a
    human suppression goes stale. After banking, a per-kind machine-dismissal
    count at/above the calibration threshold deposits a
    :func:`adjudicate.make_calibration_intent` meta-signal (the CHECK, not the
    instance, may be miscalibrated — author-gated evidence only).
  * :func:`parse_and_bank` — the file+exit-code transport law: validates a
    referee's verdicts against the round's ``residue.json``, banks them, writes
    ``verdicts.json`` beside the residue, and **exits nonzero** if any residue
    item lacks a verdict (an incomplete referee pass fails the round loudly).

The division of labour with :mod:`adjudicate` / :mod:`suppress` is deliberate:
this module NEVER invents a record kind. It maps a verdict onto the existing
makers and stamps ``actor="machine"`` (an existing parameter on all three), plus
the additive ``fingerprint`` field. The route (``fixedpoint_route.py``) already
reads ``adjudicate.confirmed_ids`` (a confirmed finding rides through class-grain
deferral) and ``suppress.load_suppressions`` (a dismissed finding is dropped
before a token is spent) — so a machine verdict steers dispatch through the
SAME seams a human verdict does, no new consumer required.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from laplace.pipeline import adjudicate, ledger, suppress

#: the three verdicts a rule / referee may return.
VALID_VERDICTS = ("confirm", "dismiss", "escalate")

#: cross-reference commands whose target lands an equation in its lifecycle.
_XREF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|vref|pageref)\{([^}]*)\}")
#: citation commands (mirrors laplace.pipeline.graph._CITE_RE — the one cite grammar).
_CITE_RE = re.compile(
    r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear|autocite|textcite|parencite)"
    r"\*?(?:\[[^\]]*\])*\{([^}]+)\}")
#: characters that continue a LaTeX label token — a bounded match must not sit
#: inside a longer label (``eq:a`` must not match inside ``eq:ab``).
_LABEL_CHARS = r"A-Za-z0-9:_\-"


def _strip_comments(text: str) -> str:
    """A comment is not prose. The rules judge the CURRENT prose, and
    ``content_fingerprint`` already normalises comments away — evaluating over
    raw text while fingerprinting over stripped text was an internal
    inconsistency that produced false dismissals from ``% see \\eqref{...}``
    mentions. One grammar: reuse suppress's comment stripper."""
    return suppress._COMMENT_RE.sub("", text)


# ---------------------------------------------------------------------------
# small extractors — tolerant of the raw-gate and the mech-routed finding shapes
# ---------------------------------------------------------------------------

def _finding_node(f: Mapping[str, Any]) -> str:
    """The node a finding is anchored to (reuse suppress's tolerant reader so a
    machine suppression keys on the SAME node the finding does)."""
    return suppress._finding_node(dict(f))


def _eq_label(f: Mapping[str, Any]) -> str:
    """The equation label an ``eq-unused`` finding rules on. The gate emits
    ``where = "<slug>:<rawlabel>"`` and the mech router lifts the rawlabel into
    ``node_id`` — a raw eq label carries a role prefix (``res:``/``thm:``/
    ``eq:``/``def:``), so ``node_id`` (no leading slug) is the label as-is;
    ``where`` needs its leading ``slug:`` stripped."""
    v = f.get("label")
    if v:
        return str(v).strip()
    node = str(f.get("node_id") or "").strip()
    if node:
        return node
    where = str(f.get("where") or (f.get("anchor") or {}).get("where") or "").strip()
    if where.count(":") >= 2:                 # slug:role:name -> role:name
        return where.split(":", 1)[1]
    return where


def _cite_key(f: Mapping[str, Any]) -> str:
    """The citation key a ``citation-first-use`` finding rules on. A cite key
    carries no colon, so a colonless ``node_id`` IS the key; otherwise strip the
    leading ``slug:`` from ``where``."""
    v = f.get("key")
    if v:
        return str(v).strip()
    node = str(f.get("node_id") or "").strip()
    if node and ":" not in node:
        return node
    where = str(f.get("where") or (f.get("anchor") or {}).get("where") or "").strip()
    if ":" in where:
        return where.split(":", 1)[1].strip()
    return node or where


def _bounded(label: str) -> re.Pattern:
    return re.compile(r"(?<![" + _LABEL_CHARS + r"])" + re.escape(label)
                      + r"(?![" + _LABEL_CHARS + r"])")


def _boxed_terminal(text: str, label: str) -> bool:
    """Whether the equation's OWN sub-equation carries a ``\\boxed`` — the
    named/terminal-result tell (it earns its number by being the stated
    payload, not dead numbering). Scoped to the label's own line of a
    multi-line environment (``align`` rows split on ``\\\\``): a ``\\boxed``
    on a *different* row must not launder its neighbours' numbering."""
    m = re.search(r"\\label\{" + re.escape(label) + r"\}", text)
    if not m:
        return False
    start = text.rfind("\\begin", 0, m.start())
    end = text.find("\\end", m.end())
    seg_start = start if start != -1 else max(0, m.start() - 200)
    seg = text[seg_start:end] if end != -1 else text[seg_start: m.end() + 200]
    # the label's own row: bracket by the nearest \\ separators inside the env
    pos = m.start() - seg_start
    row_start = seg.rfind("\\\\", 0, pos)
    row_end = seg.find("\\\\", pos)
    row = seg[(row_start + 2 if row_start != -1 else 0):
              (row_end if row_end != -1 else len(seg))]
    return "\\boxed" in row


# ---------------------------------------------------------------------------
# the Tier-1 rules — each returns (verdict, reason) or None (undecidable)
# ---------------------------------------------------------------------------

def rule_eq_unused(f: Mapping[str, Any], node_text: str) -> tuple[str, str] | None:
    """``eq-unused``: a numbered equation the panel flagged as never referenced.

    On the CURRENT prose: DISMISS if the label is now ``\\ref``/``\\eqref``'d
    anywhere, OR the equation is a ``\\boxed`` terminal result, OR the label name
    appears verbatim outside its own ``\\label{}`` (named/interpreted). CONFIRM if
    the label appears NOWHERE but its own ``\\label`` (genuine orphan numbering).
    Undecidable (→ residue) when the label cannot be extracted, or the equation's
    ``\\label`` is not present in the gathered prose (nothing to judge against)."""
    label = _eq_label(f)
    if not label:
        return None
    node_text = _strip_comments(node_text)
    defs = re.findall(r"\\label\{" + re.escape(label) + r"\}", node_text)
    if not defs:
        return None                            # cannot locate the equation → escalate
    for m in _XREF_RE.finditer(node_text):
        if label in (k.strip() for k in m.group(1).split(",")):
            return ("dismiss",
                    f"equation {label!r} is \\ref'd/\\eqref'd in the current prose "
                    "— its lifecycle is satisfied, not orphaned")
    if _boxed_terminal(node_text, label):
        return ("dismiss",
                f"equation {label!r} is a \\boxed terminal result — it earns its "
                "number as the stated payload")
    occ = len(_bounded(label).findall(node_text))
    if occ > len(defs):
        return ("dismiss",
                f"label {label!r} is named outside its \\label definition "
                f"({occ - len(defs)} other mention(s)) — referenced/interpreted")
    return ("confirm",
            f"equation {label!r} is numbered but appears nowhere outside its own "
            "\\label — orphaned numbering, confirm the finding")


def rule_citation_first_use(f: Mapping[str, Any], node_text: str) -> tuple[str, str] | None:
    """``citation-first-use``: a key whose first appearance was inside a cluster.

    On the CURRENT prose, find the key's FIRST ``\\cite`` in document order:
    DISMISS if that first occurrence already carries the key in a standalone /
    small cite (<3 keys — introduced at its own use); CONFIRM if the first
    occurrence is still a >=3-key cluster. Undecidable (→ residue) when the key
    cannot be extracted or is no longer cited anywhere."""
    key = _cite_key(f)
    if not key:
        return None
    node_text = _strip_comments(node_text)
    first: list[str] | None = None
    for m in _CITE_RE.finditer(node_text):
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        if key in keys:
            first = keys
            break
    if first is None:
        return None                            # not cited in current text → escalate
    if len(first) < 3:
        return ("dismiss",
                f"citation {key!r} is first introduced in a standalone cite of "
                f"{len(first)} key(s) — not cluster-buried")
    return ("confirm",
            f"citation {key!r} first appears inside a {len(first)}-key cluster "
            "— confirm the first-use debt")


#: kind -> Tier-1 rule. Add a rule here to teach the machine a new class; a kind
#: with no rule always lands in the referee residue.
RULES: dict[str, Callable[[Mapping[str, Any], str], "tuple[str, str] | None"]] = {
    "eq-unused": rule_eq_unused,
    "citation-first-use": rule_citation_first_use,
}


# ---------------------------------------------------------------------------
# the adjudicator — decide, then bank
# ---------------------------------------------------------------------------

def _apply_may_dismiss(kind: str, verdict: str, reason: str,
                       may_dismiss: Iterable[str] | None) -> tuple[str, str]:
    """The class-grain permission: a ``dismiss`` on a kind outside ``may_dismiss``
    is downgraded to ``escalate`` (the machine may only confirm/escalate it).
    ``may_dismiss=None`` means no restriction (every kind is dismissible)."""
    if verdict == "dismiss" and may_dismiss is not None and kind not in set(may_dismiss):
        return ("escalate",
                f"kind {kind!r} is not in may_dismiss — escalating rather than "
                f"dismissing (rule said: {reason})")
    return verdict, reason


def _decision(f: Mapping[str, Any], verdict: str, reason: str) -> dict[str, Any]:
    return {"finding_id": f.get("id"), "kind": f.get("kind"),
            "node_id": _finding_node(f), "section": f.get("section") or "",
            "verdict": verdict, "reason": reason}


def rule_verdicts(findings: Iterable[Mapping[str, Any]], node_text: str,
                  may_dismiss: Iterable[str] | None = None
                  ) -> tuple[list[dict], list[dict]]:
    """Run the Tier-1 rules over ``findings`` against ``node_text`` (the gathered
    prose). Returns ``(decided, residue)``: ``decided`` is the list of verdict
    dicts (``finding_id``/``kind``/``node_id``/``section``/``verdict``/``reason``);
    ``residue`` is the findings no rule could decide — the referee's queue."""
    decided: list[dict] = []
    residue: list[dict] = []
    for f in findings:
        kind = str(f.get("kind") or "")
        rule = RULES.get(kind)
        res = rule(f, node_text) if rule else None
        if res is None:
            residue.append(dict(f))
            continue
        verdict, reason = _apply_may_dismiss(kind, res[0], res[1], may_dismiss)
        decided.append(_decision(f, verdict, reason))
    return decided, residue


def _text_for(node_text_of: "str | Mapping[str, str] | Callable[[Mapping], str]",
              decision: Mapping[str, Any]) -> str:
    """The node text to fingerprint a decision against: a bare string (same for
    all), a mapping keyed by finding_id/node_id/section, or a callable."""
    if callable(node_text_of):
        return node_text_of(decision) or ""
    if isinstance(node_text_of, Mapping):
        for k in (decision.get("finding_id"), decision.get("node_id"),
                  decision.get("section")):
            if k and k in node_text_of:
                return node_text_of[k] or ""
        return ""
    return node_text_of or ""


def bank_verdict(feedback_path: "str | Path", decision: Mapping[str, Any],
                 node_text: str, *, round: int = 0, project: str = "",
                 actor: str = "machine") -> dict:
    """Map ONE verdict onto the existing record maker and append it to the one
    feedback ledger, stamping ``actor`` and the additive top-level
    ``fingerprint`` (content fingerprint of ``node_text``). Confirm → a
    confirmation (route exempts it from class-grain deferral); dismiss → a
    fingerprinted suppression (dropped before a token is spent, stale on edit);
    escalate → a per-instance defer noted ``escalate: <why>``."""
    verdict = decision.get("verdict")
    kind = str(decision.get("kind") or "")
    fid = str(decision.get("finding_id") or decision.get("target") or "")
    node_id = str(decision.get("node_id") or "")
    section = str(decision.get("section") or "")
    reason = str(decision.get("reason") or "")
    fp = suppress.content_fingerprint(node_text or "")
    if verdict == "confirm":
        rec = adjudicate.make_confirmation(fid, node_id=node_id, kind=kind,
                                           section=section, actor=actor,
                                           round=round, project=project)
    elif verdict == "dismiss":
        rec = suppress.make_suppression(node_id or section, kind, node_text or "",
                                        reason=reason, actor=actor, round=round,
                                        project=project, section=section)
    elif verdict == "escalate":
        rec = adjudicate.make_defer(fid, node_id=node_id, kind=kind,
                                    section=section, note="escalate: " + reason,
                                    actor=actor, round=round, project=project)
    else:
        raise ValueError(f"unknown verdict {verdict!r}; expected one of {VALID_VERDICTS}")
    rec["fingerprint"] = fp                    # additive (dismiss already carries it)
    ledger.append_jsonl(feedback_path, rec)
    return rec


def _bank_calibration(feedback_path: "str | Path", dismiss_counts: Mapping[str, int],
                      threshold: int, *, round: int, project: str, actor: str,
                      existing_records: Iterable[dict] | None) -> list[dict]:
    """The meta-signal: a per-kind machine-dismissal count at/above ``threshold``
    this run deposits a kind-level calibration intent (skipped if the kind already
    carries a live one — no re-offer)."""
    out: list[dict] = []
    if not threshold:
        return out
    already = adjudicate.calibrated_kinds(existing_records or [])
    for kind, n in sorted(dismiss_counts.items()):
        if n >= threshold and kind not in already:
            rec = adjudicate.make_calibration_intent(
                kind, dismissal_count=n, actor=actor, round=round, project=project,
                note=f"machine dismissed {n} instance(s) this run (>= {threshold})")
            ledger.append_jsonl(feedback_path, rec)
            out.append(rec)
    return out


def bank_all(feedback_path: "str | Path", decisions: Iterable[Mapping[str, Any]],
             node_text_of: "str | Mapping[str, str] | Callable[[Mapping], str]",
             *, round: int = 0, project: str = "", actor: str = "machine",
             may_dismiss: Iterable[str] | None = None,
             calibration_threshold: int = 5,
             existing_records: Iterable[dict] | None = None) -> dict:
    """Bank a batch of verdicts (re-enforcing ``may_dismiss`` at the write gate,
    defence in depth), then deposit any calibration meta-signals. Returns
    ``{banked, calibration, dismiss_counts}``."""
    banked: list[dict] = []
    dismiss_counts: dict[str, int] = {}
    for d in decisions:
        verdict, reason = _apply_may_dismiss(str(d.get("kind") or ""),
                                             str(d.get("verdict") or ""),
                                             str(d.get("reason") or ""), may_dismiss)
        d2 = {**d, "verdict": verdict, "reason": reason}
        rec = bank_verdict(feedback_path, d2, _text_for(node_text_of, d2),
                           round=round, project=project, actor=actor)
        banked.append(rec)
        if verdict == "dismiss":
            k = str(d2.get("kind") or "")
            dismiss_counts[k] = dismiss_counts.get(k, 0) + 1
    calibration = _bank_calibration(feedback_path, dismiss_counts,
                                    calibration_threshold, round=round,
                                    project=project, actor=actor,
                                    existing_records=existing_records)
    return {"banked": banked, "calibration": calibration,
            "dismiss_counts": dismiss_counts}


# ---------------------------------------------------------------------------
# the file+exit-code transport law — referee verdicts in, ledger records out
# ---------------------------------------------------------------------------

def _load_json(pathlike: "str | Path") -> Any:
    return json.loads(Path(pathlike).read_text(encoding="utf-8"))


def _parse_verdicts(verdicts_json: Any) -> list[dict]:
    """Accept a list, a ``{"verdicts": [...]}`` object, a JSON string, or a path
    to either — the referee's reply may arrive in any of these shapes."""
    obj: Any
    if isinstance(verdicts_json, (list, dict)):
        obj = verdicts_json
    else:
        s = str(verdicts_json).strip()
        try:
            obj = json.loads(s)
        except Exception:
            p = Path(s)
            if p.is_file():
                obj = json.loads(p.read_text(encoding="utf-8"))
            else:
                raise
    if isinstance(obj, list):
        return [v for v in obj if isinstance(v, dict)]
    if isinstance(obj, dict):
        inner = obj.get("verdicts")
        if isinstance(inner, list):
            return [v for v in inner if isinstance(v, dict)]
        return [obj]
    return []


def parse_and_bank(residue_path: "str | Path", verdicts_json: Any,
                   feedback_path: "str | Path") -> dict:
    """Validate a referee's verdicts against the round's ``residue.json``, bank
    them, and write ``verdicts.json`` beside the residue. If ANY residue item
    lacks a well-formed verdict this **raises** ``SystemExit(3)`` and writes NO
    ``verdicts.json`` — the file+exit-code transport law: the JS reads
    ``verdicts.json`` from disk, so an absent file + nonzero exit fails the round
    (incomplete), never a silent partial bank."""
    residue = _load_json(residue_path)
    items = residue.get("items") or []
    round = int(residue.get("round") or 0)
    project = residue.get("project") or ""
    may_dismiss = residue.get("may_dismiss")
    threshold = int(residue.get("calibration_threshold") or 5)

    by_id: dict[str, dict] = {}
    for v in _parse_verdicts(verdicts_json):
        fid = str(v.get("finding_id") or v.get("id") or v.get("target") or "")
        if fid:
            by_id[fid] = v

    decisions: list[dict] = []
    node_texts: dict[str, str] = {}
    missing: list[str] = []
    for it in items:
        fid = str(it.get("finding_id") or it.get("id") or "")
        v = by_id.get(fid)
        if not v or v.get("verdict") not in VALID_VERDICTS:
            missing.append(fid)
            continue
        node_texts[fid] = it.get("node_text") or ""
        decisions.append({"finding_id": fid, "kind": it.get("kind"),
                          "node_id": it.get("node_id") or "",
                          "section": it.get("section") or "",
                          "verdict": v.get("verdict"),
                          "reason": v.get("reason") or "referee verdict"})

    if missing:
        msg = (f"parse_and_bank: {len(missing)} residue item(s) lack a verdict "
               f"— round INCOMPLETE, no verdicts.json written: {missing}")
        print("ADJUDICATE_ERROR:" + json.dumps({"missing": missing}))
        print(msg, file=sys.stderr)
        raise SystemExit(3)

    existing = ledger.read_jsonl(feedback_path)
    summary = bank_all(feedback_path, decisions, node_texts, round=round,
                       project=project, actor="machine", may_dismiss=may_dismiss,
                       calibration_threshold=threshold, existing_records=existing)
    result = {"ok": True, "banked": len(summary["banked"]),
              "calibration": len(summary["calibration"]),
              "dismiss_counts": summary["dismiss_counts"],
              "verdicts": [{"finding_id": d["finding_id"], "kind": d["kind"],
                            "verdict": d["verdict"]} for d in decisions]}
    Path(residue_path).with_name("verdicts.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ADJUDICATE_JSON:" + json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI — the referee pipes its verdicts through this (argv or stdin)
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: machine_adjudicate <residue.json> <feedback.jsonl> "
              "[verdicts_json | - for stdin]", file=sys.stderr)
        return 2
    residue_path, feedback_path = argv[1], argv[2]
    if len(argv) >= 4 and argv[3] != "-":
        verdicts_json: Any = argv[3]
    else:
        verdicts_json = sys.stdin.read()
    parse_and_bank(residue_path, verdicts_json, feedback_path)   # exits nonzero on gap
    return 0


if __name__ == "__main__":                     # pragma: no cover
    raise SystemExit(_main(sys.argv))
