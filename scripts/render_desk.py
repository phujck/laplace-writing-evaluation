"""Render THE_DESK.md — what needs Gerard, ranked, from the ledgers. Never authored.

DESIGN_2026-08-20_the-conjugate-interface.md §6 v0: the desk is the interface's first
organ, built the day the buried-forks complaint was made. It reads FOUR stores and
writes ONE render-owned file; a hand edit to THE_DESK.md is drift the --check catches.

Stores read (never written):
  corpus_friction/open_stack_forks.jsonl   the author-fork stratum (red rows)
  corpus_friction/work_orders.jsonl        judgment-scored rows ({scored_by, the_question})
  contract/promises.jsonl                  open promises whose owner includes him
  evidence/SELF_AUDIT_2026-08-20/probe_sweep_0.json   probe-proposed strike-offs (if present)

Ranking default (his to overrule from the desk itself, the design's open-on-him):
oldest first within section — staleness is the scarce-attention default.

Pure: stdlib only, deterministic, no LLM, no network.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

# the ONE ledger reading-convention module (WO-20260820-ledger-semantics-hardening):
# repo/scripts/<this> -> repo/src on sys.path so the kind/status join helper imports
# whether or not the package is installed in the running interpreter.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from laplace.engine import engine_ledger  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "THE_DESK.md"

MARK = "<!-- RENDERED by scripts/render_desk.py — edit the stores, never this file -->"


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def _clip(s: str, n: int = 140) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def forks() -> list[str]:
    rows = _rows(ROOT / "corpus_friction" / "open_stack_forks.jsonl")
    live = [r for r in rows if "🔴" in str(r.get("status", "")) or str(r.get("status", "")).lower() in ("open", "red", "live")]
    live.sort(key=lambda r: str(r.get("opened", "")))
    out = []
    for r in live:
        ask = r.get("trigger") or r.get("context") or ""
        out.append(f"- **{r.get('id','?')}** (opened {r.get('opened','?')}) — {_clip(r.get('title',''))}\n  - the ask: {_clip(ask, 200)} `[corpus_friction/open_stack_forks.jsonl#{r.get('id','?')}]`")
    return out


def judgment_work_orders() -> list[str]:
    rows = _rows(ROOT / "corpus_friction" / "work_orders.jsonl")
    # latest stamp per target: scored_by/the_question may ride the row or an amendment
    stamp: dict[str, dict] = {}
    status: dict[str, str] = {}
    for r in rows:
        rid = r.get("id") or r.get("target")
        if not rid:
            continue
        if engine_ledger.is_work_order(r):
            status[rid] = r.get("status", "open")
        if "scored_by" in r or "the_question" in r:
            stamp.setdefault(rid, {}).update({k: r[k] for k in ("scored_by", "the_question", "asked_on") if k in r})
        if r.get("record") in ("resolution",) or r.get("kind") == "resolution":
            tgt = r.get("target") or r.get("consumes")
            if isinstance(tgt, str):
                status[tgt] = "resolved"
    out = []
    for rid, s in sorted(stamp.items()):
        if status.get(rid, "open") != "open":
            continue
        who = str(s.get("scored_by", ""))
        if "gerard" not in who.lower():
            continue
        q = s.get("the_question", "(question not stamped — a defect, flag it)")
        out.append(f"- **{rid}** — {_clip(q, 220)} `[corpus_friction/work_orders.jsonl#{rid}]`")
    return out


def promises_owed_his() -> list[str]:
    rows = _rows(ROOT / "contract" / "promises.jsonl")
    out = []
    for r in rows:
        if str(r.get("status", "")).lower() != "open":
            continue
        owner = str(r.get("owner", "")).lower()
        if not ("him" in owner or "gerard" in owner or "his" in owner):
            continue
        out.append(f"- **{r.get('id','?')}** — {_clip(r.get('ask') or r.get('what') or r.get('text') or '', 200)} `[contract/promises.jsonl#{r.get('id','?')}]`")
    return out


def strike_off_proposals() -> list[str]:
    p = ROOT / "evidence" / "SELF_AUDIT_2026-08-20" / "probe_sweep_0.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    props = data.get("proposed_strike_offs") or data.get("strike_offs") or []
    out = []
    for s in props:
        if isinstance(s, str):
            out.append(f"- {s} `[evidence/SELF_AUDIT_2026-08-20/probe_sweep_0.json]`")
        elif isinstance(s, dict):
            out.append(f"- **{s.get('id','?')}** — probe: {_clip(s.get('note') or s.get('evidence') or '', 160)} `[evidence/SELF_AUDIT_2026-08-20/probe_sweep_0.json]`")
    return out


def render() -> str:
    sections = [
        ("Author-forks (Stratum 1, live)", forks(),
         "each row blocks a named rung or want; the ask is quoted from the store"),
        ("Judgment-scored work orders (your one question each)", judgment_work_orders(),
         "rows stamped {scored_by: Gerard} at the 2026-08-20 audit; answering the question closes or advances the row"),
        ("Open promises owed by you", promises_owed_his(),
         "owner includes him — these wait on your act, not Eigen's"),
        ("Probe-proposed strike-offs awaiting ratification", strike_off_proposals(),
         "the sweep's evidence rides each row; one yes retires it"),
    ]
    lines = [MARK, "", "# THE DESK — what needs Gerard",
             "", f"Rendered {date.today().isoformat()} from the ledgers; ranking default: oldest first",
             "(staleness) — the rule is yours to overrule. Every line carries its row. Nothing here",
             "is authored; `scripts/render_desk.py --check` catches drift.", ""]
    for title, body, note in sections:
        lines.append(f"## {title}")
        lines.append(f"*{note}*")
        lines.append("")
        lines.extend(body if body else ["- (none — the section is honestly empty, not unrendered)"])
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists():
            print("THE_DESK.md missing — run scripts/render_desk.py --write")
            return 1
        # date line varies; compare modulo the rendered-date line
        strip = lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("Rendered "))
        if strip(OUT.read_text(encoding="utf-8")) != strip(text):
            print("THE_DESK.md drifted from the stores — re-render (scripts/render_desk.py --write)")
            return 1
        print("THE_DESK.md matches the stores")
        return 0
    # WRITE ONLY ON --write (2026-08-23): the old default wrote on ANY argv including
    # --help - a read-intent invocation mutating state, WO-20260821-mkdir-on-read-path's
    # sibling (observed live: a --help probe regenerated the drifted desk). Unknown args
    # refuse loudly; the error message its own usage line.
    if "--write" in sys.argv:
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)} ({len(text.splitlines())} lines)")
        return 0
    print("render_desk: refusing to write without --write "
          "(usage: render_desk.py --write | --check)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
