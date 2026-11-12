"""The convergence ledger — a read-only assembler over a project's round history.

Walks the round records a fixedpoint loop banks (``rounds/harnessed/mech_r*.json``
with its ``detect_pre/post_r*.json`` and ``lock_r*.json`` siblings, or the older
``judge_rounds/*round*.json`` layout) in round order and reports, per round, how the
loop MOVED: the open-findings delta, each gate's value and whether it flipped from the
previous round, and the round's cost when an ``economics.json`` sits beside the rounds
(absent -> "never captured", tolerant). Pure read: it opens files, never writes.

It also surfaces econ-only rounds — costs banked in ``economics.json`` for round
ordinals with no mech/detect record — labeled as such, never fabricated into a round.

Public API:
    assemble_ledger(project_or_dir, repo_root=None) -> dict
    to_markdown(ledger) -> str
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from laplace.pipeline import registry

_NEVER = "never captured"


def _round_int(name: str) -> int:
    """Round ordinal from a record filename (``mech_r7.json``, ``*_round7.json``,
    ``detect_post_r7.json``) — the integer, so r10 sorts after r2."""
    m = re.search(r"(?:round|_r)(\d+)", name)
    return int(m.group(1)) if m else -1


def _load(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resolve_dir(project_or_dir: str | Path,
                 repo_root: Path | None = None) -> Optional[Path]:
    """A manuscript dir from a registry project name (preferred — a bare name that is
    also a cwd-relative dir must still route to its registered manuscript leg) or an
    on-disk path."""
    proj = registry.resolve(str(project_or_dir))
    if proj is not None and proj.manuscript_dir:
        md = proj.path(proj.manuscript_dir, repo_root)
        if md is not None and md.is_dir():
            return md
    p = Path(project_or_dir)
    if p.is_dir():
        return p
    return None


def _economics(md: Path) -> Optional[dict]:
    """The economics record beside the rounds, if any. Two shapes tolerated: a flat
    ``{"<round>": cost}`` map or a ``{"rounds": {...}}`` wrapper."""
    for cand in (md / "rounds" / "economics.json", md / "economics.json"):
        data = _load(cand) if cand.is_file() else None
        if isinstance(data, dict):
            return data.get("rounds") if isinstance(data.get("rounds"), dict) else data
    return None


def _cost_for(econ: Optional[dict], rnd: int) -> Any:
    if not econ:
        return _NEVER
    for key in (str(rnd), rnd):
        if key in econ:
            return econ[key]
    return _NEVER


def _open_findings(judge: Optional[dict], detects: dict[str, dict]) -> Optional[int]:
    """Open-findings count for a round: the detect record's deduped count is authored
    truth (post preferred over pre); else fall back to the judge round's total panel
    flags."""
    for phase in ("post", "pre"):
        rec = detects.get(phase)
        if rec and isinstance(rec.get("open_findings_n"), int):
            return rec["open_findings_n"]
    if judge:
        return sum(len(p.get("flags") or []) for p in (judge.get("panel") or []))
    return None


def _transition(cur: Any, prev: Any, seen_prev: bool) -> dict:
    return {"value": cur, "from": prev if seen_prev else None,
            "changed": bool(seen_prev and prev != cur)}


def assemble_ledger(project_or_dir: str | Path,
                    repo_root: Path | None = None) -> dict:
    """Assemble the convergence ledger for a project (name or manuscript dir). Returns
    ``{"project", "dir", "layout", "rounds": [...]}``; an unresolvable project yields
    ``{"error": ...}``. Read-only."""
    md = _resolve_dir(project_or_dir, repo_root)
    if md is None:
        return {"error": f"no manuscript dir for {str(project_or_dir)!r}"}

    harnessed = md / "rounds" / "harnessed"
    judge_dir = md / "judge_rounds"

    # judge round per round, plus the detect sidecars (harnessed layout only)
    judges: dict[int, dict] = {}
    detects: dict[int, dict[str, dict]] = {}
    layout = ""
    if harnessed.is_dir():
        layout = "harnessed"
        for f in harnessed.glob("mech_r*.json"):
            data = _load(f)
            if isinstance(data, dict):
                judges[_round_int(f.name)] = data
        for phase in ("pre", "post"):
            for f in harnessed.glob(f"detect_{phase}_r*.json"):
                data = _load(f)
                if isinstance(data, dict):
                    detects.setdefault(_round_int(f.name), {})[phase] = data
    if not judges and judge_dir.is_dir():
        layout = "judge_rounds"
        for f in judge_dir.glob("*round*.json"):
            data = _load(f)
            if isinstance(data, dict):
                rnd = data.get("round")
                judges[int(rnd) if isinstance(rnd, int) else _round_int(f.name)] = data

    econ = _economics(md)
    # Orphaned economics rounds: integer-parseable econ keys with no mech/detect
    # round record — cost was banked but no round was ever captured. Non-integer
    # keys (e.g. "total") are skipped silently, never guessed into a phantom round.
    econ_only: set[int] = set()
    if econ:
        for k in econ:
            try:
                ki = int(k)
            except (TypeError, ValueError):
                continue
            if ki not in judges and ki not in detects:
                econ_only.add(ki)

    rounds: list[dict] = []
    prev_hard: dict = {}
    prev_soft: dict = {}
    prev_panels: dict = {}
    prev_open: Optional[int] = None
    seen_prev = False

    for rnd in sorted(set(judges) | set(detects) | econ_only):
        judge = judges.get(rnd)
        contract = (judge or {}).get("contract") or {}
        hard = contract.get("hard") or {}
        soft = contract.get("soft") or {}
        panels = {p.get("label"): p.get("clean")
                  for p in ((judge or {}).get("panel") or []) if p.get("label")}

        opn = _open_findings(judge, detects.get(rnd, {}))
        delta = (opn - prev_open) if (opn is not None and prev_open is not None) else None

        gates = {
            "hard": {d: _transition(v, prev_hard.get(d), seen_prev and d in prev_hard)
                     for d, v in hard.items()},
            "soft": {d: _transition(v, prev_soft.get(d), seen_prev and d in prev_soft)
                     for d, v in soft.items()},
            "panels": {lab: _transition(v, prev_panels.get(lab),
                                        seen_prev and lab in prev_panels)
                       for lab, v in panels.items()},
        }

        rec = {
            "round": rnd,
            "date": (judge or {}).get("date"),
            "open_findings": opn,
            "findings_delta": delta,
            "gates": gates,
            "cost": _cost_for(econ, rnd),
        }
        if rnd in econ_only:
            # labeled honesty — key absent on joined rounds, so existing consumers
            # see byte-identical entries; present only when the round is orphaned.
            rec["econ_only"] = True
        rounds.append(rec)

        if hard:
            prev_hard = hard
        if soft:
            prev_soft = soft
        if panels:
            prev_panels = panels
        if opn is not None:
            prev_open = opn
        seen_prev = True

    return {"project": str(project_or_dir), "dir": str(md),
            "layout": layout, "rounds": rounds}


def _fmt_delta(d: Optional[int]) -> str:
    if d is None:
        return "—"
    return f"{d:+d}" if d else "0"


def to_markdown(ledger: dict) -> str:
    """Render an assembled ledger to a compact markdown report."""
    if "error" in ledger:
        return f"# convergence ledger\n\n**error:** {ledger['error']}\n"
    lines = [f"# convergence ledger — {ledger.get('project')}",
             "",
             f"_dir: {ledger.get('dir')} · layout: {ledger.get('layout') or 'none'}_",
             ""]
    rounds = ledger.get("rounds") or []
    if not rounds:
        lines.append("_no round records found_")
        return "\n".join(lines) + "\n"
    for r in rounds:
        opn = r.get("open_findings")
        lines.append(f"## round {r['round']}"
                     + (f"  ({r['date']})" if r.get("date") else "")
                     + (" — economics-only (cost banked, no mech/detect round record)"
                        if r.get("econ_only") else ""))
        lines.append(f"- open findings: {opn if opn is not None else '—'} "
                     f"(Δ {_fmt_delta(r.get('findings_delta'))})")
        lines.append(f"- cost: {r.get('cost')}")
        flipped = [f"{d}={t['value']}"
                   for grp in ("hard", "soft", "panels")
                   for d, t in (r["gates"].get(grp) or {}).items() if t["changed"]]
        lines.append("- gate flips: " + (", ".join(flipped) if flipped else "none"))
        lines.append("")
    return "\n".join(lines) + "\n"
