#!/usr/bin/env python
"""THE ONE PER-RUN ECONOMICS ARTIFACT — per-agent tokens + duration, made legible.

Leg A bite A5 (PLAN_2026-07-12 §2). THE RUN (2026-07-10, 1.61M subagent tokens /
74.5 min / 22 agents) had ILLEGIBLE per-agent economics: the workflow journal
carried no per-agent usage, so "it feels expensive" was the only datum. This is
the named plumbing defect that made the cost autopsy in
``CALIBRATION_2026-07-10_h-second-pass.md`` §2 a coarse guess rather than a table.

This reader closes that gap AFTER the fact, at the most robust seam: it walks a
finished run's transcript directory — the ``journal.jsonl`` the workflow harness
writes (one line per ``agent()`` invocation, carrying the opts: label / phase /
model / effort / agentType / the agent id) plus the per-agent SDK transcript
files (``agent-<id>.jsonl``, the Claude Agent SDK message stream) — and emits ONE
per-run economics artifact: a table of agent label/phase, tokens, duration, model,
with per-phase yield/cost rollups and run totals. Nothing here dispatches an agent
or touches the loop; it reads what the run already banked to disk.

WHERE THE USAGE LIVES (the data path, reconstructed from the SDK message format
and the harness opts — no in-repo run artifact survived THE RUN to read):

  * PER-AGENT USAGE — in each ``agent-<id>.jsonl`` transcript. The SDK emits an
    ``assistant`` message per model turn carrying ``message.usage`` with
    ``input_tokens`` / ``output_tokens`` / ``cache_creation_input_tokens`` /
    ``cache_read_input_tokens``, and a terminal ``result`` message carrying
    cumulative ``usage``, ``duration_ms`` and (when priced) ``total_cost_usd``.
    We prefer the ``result`` cumulative when present; else we SUM the assistant
    turns. Either way the per-agent number is recoverable from the transcript.
  * PER-AGENT LABEL / PHASE / MODEL — in ``journal.jsonl``. The loop hands
    ``agent(prompt, {label, phase, model, effort, agentType})`` to the harness;
    the harness banks those opts plus the agent id into the journal line. The
    transcript alone knows tokens but not which STAGE spent them; the journal
    alone knows the stage but (before this bite) not the tokens. The artifact is
    the JOIN — journal metadata ⋈ transcript usage, keyed on the agent id.

WHERE IT WAS LOST: nowhere did anything JOIN the two and total by stage. The
workflow scripts consume only the schema'd return value of ``agent()``; usage and
duration fall on the floor. This reader is that missing join + rollup.

ROBUSTNESS (the format is reconstructed, so read tolerantly):
  * Journal field spellings vary — accept ``agent_id``/``id``/``uuid``,
    ``phase``/``stage``, ``model``/``model_id``, ``duration_ms``/``started_at``+
    ``ended_at``, and an inline ``usage`` block if the harness ever records one.
  * Transcript-only runs (no journal): enumerate ``agent-*.jsonl`` directly; label
    from the filename, phase unknown.
  * Journal-only usage (harness banked usage inline, no transcript): use it.
  * A missing/short/garbled transcript is a per-agent WARNING (source="none"),
    never a crash — a partial artifact beats no artifact.

GENERIC: the run directory is an ARGUMENT. No project name is hardcoded; the same
command reads the SSG run, a paper_operatorial_loss run, or a synthetics sibling.

Usage:
    python scripts/workflow_economics.py <run_transcript_dir> [--out <dir>]
                                         [--json-only | --md-only] [--quiet]

    <run_transcript_dir>  the harness transcript directory for ONE run: contains
                          journal.jsonl and/or agent-<id>.jsonl files.
    --out <dir>           where to write economics.json / economics.md
                          (default: the run dir itself).
    --json-only/--md-only emit just one artifact (default: both).
    --quiet               suppress the stdout summary line.

Exit contract:
  * 0   — artifact(s) written (even if some agents had no recoverable usage; those
          are counted and flagged, not fatal).
  * 2   — the run directory does not exist, or holds neither a journal nor any
          agent-*.jsonl transcript (nothing to read).

The calibration-note step consumes ``economics.json`` (or embeds the markdown from
``render_calibration_economics``): the per-stage yield/cost table lands in the
note's Economics section instead of a coarse prose guess.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Model price table (USD per 1M tokens), used ONLY to ESTIMATE cost when a
# transcript carries no total_cost_usd. Keyed by family substring so both the
# dials short names ("opus"/"sonnet"/"haiku") and full ids ("claude-opus-4-8")
# resolve. Cache-read priced at ~0.1x input, cache-write at ~1.25x input (the
# standard ephemeral economics). An unknown model yields cost=None (never a lie).
# ---------------------------------------------------------------------------
_PRICES = {
    # family substring : (input_per_mtok, output_per_mtok)
    "fable": (10.0, 50.0),
    "mythos": (10.0, 50.0),
    "opus": (5.0, 25.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
}
#: workflow phases in pipeline order; unknown phases sort after, alphabetically.
_PHASE_ORDER = ["Build", "Weld", "Converge", "Finalize", "Revalidate"]

#: a per-round phase label the fixedpoint loop stamps — ``mech_r<n>`` / ``judge_r<n>``.
#: The round-keyed adapter (``render_rounds_economics``) rolls such a phase's cost into
#: round key ``"<n>"``; every other phase is run overhead and rolls into key ``"0"``.
_ROUND_FROM_PHASE = re.compile(r"^(?:mech|judge)_r(\d+)$")

_ID_FROM_NAME = re.compile(r"^agent-(.+)\.jsonl$")

#: a version-scheme prefix on a journal agent id, e.g. ``v2:<sha>`` / ``sess:<sha>``.
#: THE RUN's journal keyed agents by the versioned id while the transcript FILES are
#: named by the bare (often truncated) id, so the id-keyed JOIN missed every row:
#: 45 agents surfaced vs 15 real (30 phantom zero-usage rows) and every row was
#: unlabelled. Stripping the scheme lets ``v2:<sha>`` join ``agent-<sha>.jsonl``.
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9_]*:")
#: the shortest id overlap we will trust for a prefix/suffix (sha-truncation) join —
#: long enough that two distinct agents never collide on it.
_MIN_ID_OVERLAP = 8


def _norm_agent_key(aid) -> str:
    """Normalise an agent id for the journal<->transcript join: strip a version
    scheme prefix (``v2:<sha>`` -> ``<sha>``) and surrounding whitespace."""
    if not aid:
        return ""
    return _SCHEME_RE.sub("", str(aid).strip())


def _ids_match(a: str, b: str) -> bool:
    """Whether two NORMALISED agent ids denote the same agent: equal, or one is a
    prefix/suffix of the other of at least ``_MIN_ID_OVERLAP`` chars (the journal id
    carries a full sha while the transcript file may carry a truncation, or vice
    versa)."""
    if not a or not b:
        return False
    if a == b:
        return True
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)
    if len(lo) < _MIN_ID_OVERLAP:
        return False
    return hi.startswith(lo) or hi.endswith(lo)


def _agent_ids(rec: dict) -> list:
    """Every agent-id spelling present on a journal record (raw AND scheme-stripped),
    de-duplicated in preference order.

    F1 phantom-drop (judge, 2026-07-10): the harness journal keys agents by
    ``agentId`` and ``key`` (``v2:<sha>``), which this reader did NOT read — so the
    journal<->transcript join found nothing, every journal row became a zero-usage
    PHANTOM, and 30 phantoms swamped the 15 real agents. Reading ``agentId``/``key``
    (raw + scheme-stripped) lets the harness journal join its transcripts; the
    started/result twins are then collapsed in ``collect_agents`` (one row per
    agent), so the phantom rows never surface."""
    out: list = []
    for k in ("agent_id", "id", "uuid", "session_id", "sessionId", "agentId", "key"):
        v = rec.get(k) if isinstance(rec, dict) else None
        if v:
            for cand in (str(v), _norm_agent_key(v)):
                if cand and cand not in out:
                    out.append(cand)
    return out


# ---------------------------------------------------------------------------
# small tolerant helpers
# ---------------------------------------------------------------------------
def _first(d: dict, *keys, default=None):
    """First present, non-None value among several candidate key spellings."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def _read_jsonl(path: Path) -> list:
    """Parse a .jsonl file, skipping blank/garbled lines (robust to a truncated
    tail — a crashed run leaves a half-written final line)."""
    out = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except (ValueError, TypeError):
            continue
    return out


def _price_for(model: "str | None"):
    """(input, output) $/Mtok for a model name/id, matched by family substring."""
    if not model:
        return None
    m = str(model).lower()
    for fam, price in _PRICES.items():
        if fam in m:
            return price
    return None


def _usage_zero() -> dict:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def _usage_add(acc: dict, u: dict) -> None:
    for k in _usage_zero():
        acc[k] += int(_first(u, k, default=0) or 0)


def _usage_total(u: dict) -> int:
    """Gross token throughput — input + output + both cache legs. This is the
    'subagent tokens' number the calibration autopsy reports."""
    return sum(int(u.get(k, 0) or 0) for k in _usage_zero())


# ---------------------------------------------------------------------------
# transcript reading — one agent-<id>.jsonl
# ---------------------------------------------------------------------------
def usage_from_transcript(path: Path) -> dict:
    """Derive one agent's usage + duration + model from its SDK transcript.

    Prefers a terminal ``result`` message's cumulative usage/duration/cost; falls
    back to summing ``assistant`` turns and deriving duration from message
    timestamps. Returns {usage, duration_ms, model, cost_usd, turns, source}.
    ``source`` is 'result' | 'assistant-sum' | 'none'.
    """
    msgs = _read_jsonl(path)
    result = _usage_zero()
    out = {
        "usage": result,
        "duration_ms": None,
        "model": None,
        "cost_usd": None,
        "turns": 0,
        "source": "none",
    }
    if not msgs:
        return out

    # --- terminal result message (cumulative, authoritative when present) ------
    for m in msgs:
        if isinstance(m, dict) and m.get("type") == "result":
            u = _first(m, "usage", default=None)
            if isinstance(u, dict):
                _usage_add(result, u)
                out["source"] = "result"
            out["duration_ms"] = _first(m, "duration_ms", "durationMs")
            out["cost_usd"] = _first(m, "total_cost_usd", "cost_usd", "totalCostUsd")
            out["turns"] = _first(m, "num_turns", "numTurns", default=0) or 0
            # model may only be on assistant turns — fall through to scan below
            break

    # --- assistant turns: the sum fallback, and the model/timestamp scan -------
    assistant_sum = _usage_zero()
    n_assistant = 0
    first_ts = last_ts = None
    for m in msgs:
        if not isinstance(m, dict):
            continue
        ts = _parse_ts(_first(m, "timestamp", "ts", "time"))
        if ts is not None:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)
        if m.get("type") == "assistant":
            inner = m.get("message") if isinstance(m.get("message"), dict) else m
            if out["model"] is None:
                out["model"] = _first(inner, "model", "model_id")
            u = _first(inner, "usage", default=None)
            if isinstance(u, dict):
                _usage_add(assistant_sum, u)
                n_assistant += 1

    if out["source"] != "result" and n_assistant:
        out["usage"] = assistant_sum
        out["source"] = "assistant-sum"
        out["turns"] = out["turns"] or n_assistant
    if out["duration_ms"] is None and first_ts is not None and last_ts is not None:
        out["duration_ms"] = max(0, int((last_ts - first_ts) * 1000))
    return out


def _parse_ts(v):
    """A message timestamp as epoch seconds (float), or None. Accepts ISO-8601
    strings and numeric epoch (s or ms)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        # ms if it looks like ms
        return float(v) / 1000.0 if v > 1e12 else float(v)
    if isinstance(v, str):
        s = v.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s).timestamp()
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# journal reading + the JOIN
# ---------------------------------------------------------------------------
def _journal_duration_ms(rec: dict):
    d = _first(rec, "duration_ms", "durationMs")
    if d is not None:
        try:
            return int(d)
        except (ValueError, TypeError):
            return None
    a = _parse_ts(_first(rec, "started_at", "start", "startedAt"))
    b = _parse_ts(_first(rec, "ended_at", "end", "endedAt"))
    if a is not None and b is not None:
        return max(0, int((b - a) * 1000))
    return None


def _index_transcripts(run_dir: Path) -> dict:
    """Every transcript indexed by its NORMALISED file id, so a scheme-prefixed or
    truncated journal id can still find it (the join fix)."""
    transcript_by_id: dict = {}
    for tp in sorted(run_dir.glob("agent-*.jsonl")):
        m = _ID_FROM_NAME.match(tp.name)
        if m:
            transcript_by_id.setdefault(_norm_agent_key(m.group(1)), tp)
    return transcript_by_id


def _transcript_by_ids(run_dir: Path, ids: list, transcript_by_id: dict) -> "Path | None":
    """The transcript for any of ``ids`` (exact file, normalised index, or a
    prefix/suffix sha-truncation match)."""
    for aid in ids:
        cand = run_dir / f"agent-{aid}.jsonl"
        if cand.exists():
            return cand
        norm = _norm_agent_key(aid)
        if norm in transcript_by_id:
            return transcript_by_id[norm]
        for tid in sorted(transcript_by_id):
            if _ids_match(norm, tid):
                return transcript_by_id[tid]
    return None


def _dispatch_agentids(journal: list) -> list:
    """Per unique agent, the full NORMALISED id-set (agentId AND the v2-stripped key
    — the transcript file may be named by either), in first-seen (dispatch) order.
    The harness banks started+result rows per agent, so an agent recurs; first-seen
    order is the dispatch order, which aligns 1:1 with this organ's own ``ag()``
    manifest ordinal (the F1 join key). Returns a list of id LISTS."""
    seen: set = set()
    order: list = []
    for rec in journal:
        if not isinstance(rec, dict):
            continue
        ids = [n for n in (_norm_agent_key(a) for a in _agent_ids(rec)) if n]
        if not ids or any(n in seen for n in ids):
            continue                       # the started/result twin of a seen agent
        seen.update(ids)
        order.append(ids)
    return order


def _transcript_prompt_sha(path: "Path | None") -> "str | None":
    """sha256 of a transcript's FIRST user-prompt text — the content key an organ can
    stamp into its stage manifest (``prompt_sha``) to bind an entry to its transcript
    without any id. Tolerant to the SDK's string- or block-content shapes."""
    if path is None:
        return None
    for m in _read_jsonl(path):
        if not (isinstance(m, dict) and m.get("type") == "user"):
            continue
        msg = m.get("message") if isinstance(m.get("message"), dict) else m
        content = msg.get("content") if isinstance(msg, dict) else None
        text = None
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = [b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
            text = "".join(parts) if parts else None
        elif isinstance(m.get("prompt"), str):
            text = m["prompt"]
        if text:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return None


def _collect_from_manifest(run_dir: Path, manifest: list, journal: list,
                           transcript_by_id: dict) -> list:
    """F1: the stage manifest is the CANONICAL agent list — one row per manifest
    entry, LABELLED from the manifest (the organ knows its own labels), usage JOINED
    from the transcript. No phantom rows (only manifest entries surface) and no
    unlabelled ``agent-<i>`` (every entry carries a label). The transcript join, in
    precedence: an explicit ``agent_id``/``prompt_sha`` on the entry; else the ORDINAL
    mapped through the journal's dispatch order to an agent id; else the ordinal into
    mtime-sorted transcripts (a journal-less run)."""
    dispatch = _dispatch_agentids(journal)
    mtime_sorted: list = []
    if not dispatch:
        mtime_sorted = sorted(run_dir.glob("agent-*.jsonl"),
                              key=lambda p: (p.stat().st_mtime, p.name))
    # precompute prompt_sha -> transcript only if any entry asks for it (cheap-skip).
    sha_index: dict = {}
    if any(isinstance(e, dict) and e.get("prompt_sha") for e in manifest):
        for tp in sorted(run_dir.glob("agent-*.jsonl")):
            s = _transcript_prompt_sha(tp)
            if s:
                sha_index.setdefault(s, tp)

    agents: list = []
    used_files: set = set()
    for i, entry in enumerate(manifest):
        if not isinstance(entry, dict):
            continue
        ordinal = entry.get("ordinal")
        if not isinstance(ordinal, int):
            ordinal = i
        aid = entry.get("agent_id") or entry.get("agentId") or entry.get("id")
        tpath = None
        if aid:
            tpath = _transcript_by_ids(run_dir, [str(aid), _norm_agent_key(aid)],
                                       transcript_by_id)
        if tpath is None and entry.get("prompt_sha"):
            tpath = sha_index.get(entry["prompt_sha"])
        joined_id = str(aid) if aid else None
        if tpath is None and dispatch and 0 <= ordinal < len(dispatch):
            joined_id = dispatch[ordinal][0]
            tpath = _transcript_by_ids(run_dir, dispatch[ordinal], transcript_by_id)
        if tpath is None and not dispatch and 0 <= ordinal < len(mtime_sorted):
            tpath = mtime_sorted[ordinal]
        tinfo = usage_from_transcript(tpath) if tpath else {
            "usage": _usage_zero(), "duration_ms": None, "model": None,
            "cost_usd": None, "turns": 0, "source": "none"}
        if tpath is not None:
            used_files.add(tpath.name)
        agents.append(_assemble(
            label=entry.get("label") or f"agent-{ordinal}",
            phase=entry.get("phase") or "",
            model=tinfo["model"] or entry.get("model"),
            agent_id=joined_id,
            tinfo=tinfo, j_duration=None))

    # transcripts the manifest never claimed (e.g. the manifest-writer + economics
    # bookkeepers, dispatched AFTER the manifest was serialized): the same orphan/
    # phantom law as the journal path — real usage is COUNTED (an honest run total,
    # label from the filename, phase ''), a zero-usage leftover is DROPPED (never a
    # phantom row).
    for tpath in sorted(run_dir.glob("agent-*.jsonl")):
        if tpath.name in used_files:
            continue
        m = _ID_FROM_NAME.match(tpath.name)
        aid = m.group(1) if m else tpath.stem
        tinfo = usage_from_transcript(tpath)
        if tinfo["source"] == "none" or _usage_total(tinfo["usage"]) == 0:
            continue
        agents.append(_assemble(
            label=aid, phase="", model=tinfo["model"], agent_id=aid,
            tinfo=tinfo, j_duration=None))
    return agents


def collect_agents(run_dir: Path, manifest: "list | None" = None) -> list:
    """Join journal metadata with transcript usage. Returns a list of per-agent
    dicts, in journal order (or filename order when there is no journal).

    F1: when a stage ``manifest`` is supplied (the organ's own ordinal->label/phase/
    model record), it is the canonical agent list and drives the join (labelled rows,
    no phantoms). Absent a manifest, the journal path runs — now hardened: the
    started/result twins the harness banks per agent are collapsed to ONE row (the
    ``agentId``/``key`` join reads both, so double-counting is dropped)."""
    journal = _read_jsonl(run_dir / "journal.jsonl")
    transcript_by_id = _index_transcripts(run_dir)

    if manifest:
        return _collect_from_manifest(run_dir, manifest, journal, transcript_by_id)

    used_files: set = set()
    agents: list = []
    seen_keys: set = set()

    for i, rec in enumerate(journal):
        if not isinstance(rec, dict):
            continue
        ids = _agent_ids(rec)
        norm_ids = [n for n in (_norm_agent_key(a) for a in ids) if n]
        # DEDUP: the harness banks started+result rows per agent (same agentId/key);
        # emit the FIRST, skip the twin — its transcript already carries cumulative
        # usage, so this is where the 30 phantom double-count rows are dropped.
        if any(n in seen_keys for n in norm_ids):
            continue
        tpath = None
        p = _first(rec, "transcript", "transcript_path", "transcriptPath")
        if p and (run_dir / Path(p).name).exists():
            tpath = run_dir / Path(p).name
        if tpath is None:
            tpath = _transcript_by_ids(run_dir, ids, transcript_by_id)
        tinfo = usage_from_transcript(tpath) if tpath else {
            "usage": _usage_zero(), "duration_ms": None, "model": None,
            "cost_usd": None, "turns": 0, "source": "none"}
        if tpath:
            used_files.add(tpath.name)
        # inline journal usage (if the harness ever banks it) is a fallback source
        j_usage = _first(rec, "usage", default=None)
        if tinfo["source"] == "none" and isinstance(j_usage, dict):
            u = _usage_zero()
            _usage_add(u, j_usage)
            tinfo["usage"] = u
            tinfo["source"] = "journal"
        # label/phase/model live top-level OR nested under an opts/options/meta block
        # (the harness bank shape varies); read tolerantly so a nested-opts journal is
        # not rendered as unlabelled `agent-<i>` rows.
        agents.append(_assemble(
            label=_meta(rec, "label", "name", default=f"agent-{i}"),
            phase=_meta(rec, "phase", "stage", default=""),
            model=tinfo["model"] or _meta(rec, "model", "model_id"),
            agent_id=_first(rec, "agent_id", "id", "uuid", "agentId", default=None),
            tinfo=tinfo,
            j_duration=_journal_duration_ms(rec),
        ))
        for n in norm_ids:
            seen_keys.add(n)

    # transcript files not named by any journal record (or a journal-less run). A
    # leftover with real usage is a deliberate ORPHAN (counted, phase=''); a leftover
    # with NO recoverable usage is a PHANTOM (the join already claimed every real
    # transcript) and is DROPPED — it must never inflate the agent count.
    for tpath in sorted(run_dir.glob("agent-*.jsonl")):
        if tpath.name in used_files:
            continue
        m = _ID_FROM_NAME.match(tpath.name)
        aid = m.group(1) if m else tpath.stem
        tinfo = usage_from_transcript(tpath)
        if tinfo["source"] == "none" or _usage_total(tinfo["usage"]) == 0:
            continue
        agents.append(_assemble(
            label=aid, phase="", model=tinfo["model"], agent_id=aid,
            tinfo=tinfo, j_duration=None))
    return agents


def _meta(rec: dict, *keys, default=None):
    """A journal field read top-level first, then from a nested opts/options/meta
    block — the harness banks the ``agent()`` opts either flat or nested."""
    v = _first(rec, *keys, default=None)
    if v is not None:
        return v
    for holder in ("opts", "options", "meta"):
        block = rec.get(holder) if isinstance(rec, dict) else None
        if isinstance(block, dict):
            v = _first(block, *keys, default=None)
            if v is not None:
                return v
    return default


def _assemble(*, label, phase, model, agent_id, tinfo, j_duration) -> dict:
    usage = tinfo["usage"]
    duration_ms = tinfo["duration_ms"] if tinfo["duration_ms"] is not None else j_duration
    cost = tinfo["cost_usd"]
    if cost is None:
        cost = _estimate_cost(model, usage)
        cost_source = "estimated" if cost is not None else "unknown"
    else:
        cost_source = "reported"
    row = {
        "label": label,
        "phase": phase or "",
        "model": model,
        "agent_id": agent_id,
        **usage,
        "total_tokens": _usage_total(usage),
        "duration_ms": duration_ms,
        "cost_usd": round(cost, 4) if cost is not None else None,
        "cost_source": cost_source,
        "usage_source": tinfo["source"],
        "turns": tinfo.get("turns", 0),
    }
    return row


def _estimate_cost(model, usage: dict):
    price = _price_for(model)
    if price is None:
        return None
    inp, outp = price
    # cache-read ~0.1x input; cache-write ~1.25x input (ephemeral standard).
    dollars = (
        usage["input_tokens"] * inp
        + usage["output_tokens"] * outp
        + usage["cache_creation_input_tokens"] * inp * 1.25
        + usage["cache_read_input_tokens"] * inp * 0.10
    ) / 1_000_000.0
    return dollars


# ---------------------------------------------------------------------------
# rollups
# ---------------------------------------------------------------------------
def _phase_sort_key(phase: str):
    if phase in _PHASE_ORDER:
        return (0, _PHASE_ORDER.index(phase), "")
    return (1, 0, phase or "~")  # unknown phases after, alphabetically; "" last


def summarize(run_dir: Path, agents: list) -> dict:
    by_phase: dict = {}
    totals = {**_usage_zero(), "agents": 0, "total_tokens": 0,
              "duration_ms": 0, "cost_usd": 0.0}
    any_cost = False
    for a in agents:
        ph = a["phase"] or "(unlabelled)"
        b = by_phase.setdefault(ph, {**_usage_zero(), "agents": 0,
                                      "total_tokens": 0, "duration_ms": 0,
                                      "cost_usd": 0.0})
        for k in _usage_zero():
            b[k] += a[k]
            totals[k] += a[k]
        b["agents"] += 1
        totals["agents"] += 1
        b["total_tokens"] += a["total_tokens"]
        totals["total_tokens"] += a["total_tokens"]
        if a["duration_ms"]:
            b["duration_ms"] += a["duration_ms"]
            totals["duration_ms"] += a["duration_ms"]
        if a["cost_usd"] is not None:
            b["cost_usd"] += a["cost_usd"]
            totals["cost_usd"] += a["cost_usd"]
            any_cost = True
    for b in list(by_phase.values()) + [totals]:
        b["cost_usd"] = round(b["cost_usd"], 4)
        b["duration_min"] = round(b["duration_ms"] / 60000.0, 2)
    if not any_cost:
        totals["cost_usd"] = None
        for b in by_phase.values():
            b["cost_usd"] = None
    return {
        "run_dir": str(run_dir),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agents": agents,
        "by_phase": by_phase,
        "totals": totals,
    }


# ---------------------------------------------------------------------------
# the round-keyed cost adapter (Fix 0d) — bridge to the convergence ledger
# ---------------------------------------------------------------------------
def _phase_round_key(phase: str) -> str:
    """The round ordinal a phase label names, as a string: ``mech_r<n>`` / ``judge_r<n>``
    -> ``"<n>"``; every other phase (the build/weld/finalize bookkeepers — run overhead)
    -> ``"0"``."""
    m = _ROUND_FROM_PHASE.match(phase or "")
    return m.group(1) if m else "0"


def render_rounds_economics(econ: dict) -> dict:
    """Roll the per-phase economics into a ROUND-keyed cost map for the convergence
    ledger's cost column.

    The ledger reader (``convergence_ledger._economics`` / ``_cost_for``) keys cost on the
    round ORDINAL, but this artifact's ``by_phase`` is keyed on the workflow PHASE label —
    so the ledger's per-round cost column reads "never captured" even once this economics
    rollup is written. This adapter bridges the two: a phase of shape ``mech_r<n>`` /
    ``judge_r<n>`` rolls into round key ``"<n>"``; every unmappable phase (run overhead)
    rolls into key ``"0"``, NAMED in the note so it is never silently dropped. Rounds with
    no transcript are never fabricated (only phases present in ``by_phase`` produce keys).
    The ``{"rounds": {...}}`` wrapper is a shape ``_economics`` already tolerates, so
    nothing on the reader side changes.
    """
    rounds: dict = {}
    have_cost: dict = {}
    overhead: list = []
    for phase, b in econ.get("by_phase", {}).items():
        key = _phase_round_key(phase)
        if key == "0" and phase not in overhead:
            overhead.append(phase)
        rounds.setdefault(key, 0.0)
        c = b.get("cost_usd")
        if c is not None:
            rounds[key] += c
            have_cost[key] = True
    # a round with transcripts but no recoverable cost stays present as null (unknown),
    # never a fabricated zero; a costed round carries its summed dollars.
    rounds = {k: (round(v, 4) if have_cost.get(k) else None) for k, v in rounds.items()}
    note = ("cost rolled from by_phase; phase mech_r<n>/judge_r<n> -> round <n>. "
            + (f"key '0' = run overhead (phases: {', '.join(sorted(overhead))})."
               if overhead else "no run-overhead phases (no key '0')."))
    return {
        "rounds": rounds,
        "run": econ.get("totals", {}),
        "derived_from": econ.get("run_dir"),
        "note": note,
    }


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def _fmt_int(n) -> str:
    return f"{int(n):,}" if n is not None else "—"


def _fmt_dur(ms) -> str:
    if not ms:
        return "—"
    return f"{ms / 60000.0:.1f}m" if ms >= 60000 else f"{ms / 1000.0:.1f}s"


def _fmt_cost(c) -> str:
    return f"${c:,.2f}" if c is not None else "—"


def render_markdown(econ: dict) -> str:
    """The full per-run economics artifact as markdown (agent table + phase
    rollup + totals). Standalone document."""
    lines = [
        "# Workflow economics — per-agent tokens + duration",
        "",
        f"- run dir: `{econ['run_dir']}`",
        f"- generated: {econ['generated_at']}",
        f"- agents: {econ['totals']['agents']} · "
        f"tokens: {_fmt_int(econ['totals']['total_tokens'])} (cache-inclusive) · "
        f"output: {_fmt_int(econ['totals']['output_tokens'])} · "
        f"wall: {_fmt_dur(econ['totals']['duration_ms'])} · "
        f"cost: {_fmt_cost(econ['totals']['cost_usd'])}",
        "",
        "## Per agent",
        "",
        "| label | phase | model | tokens | in | out | cache | duration | cost | src |",
        "|---|---|---|--:|--:|--:|--:|--:|--:|:--|",
    ]
    for a in econ["agents"]:
        cache = a["cache_creation_input_tokens"] + a["cache_read_input_tokens"]
        lines.append(
            f"| {a['label']} | {a['phase'] or '—'} | {a['model'] or '—'} | "
            f"{_fmt_int(a['total_tokens'])} | {_fmt_int(a['input_tokens'])} | "
            f"{_fmt_int(a['output_tokens'])} | {_fmt_int(cache)} | "
            f"{_fmt_dur(a['duration_ms'])} | {_fmt_cost(a['cost_usd'])} | "
            f"{a['usage_source']} |")
    lines += ["", "## Per stage (yield/cost)", "", render_calibration_economics(econ)]
    return "\n".join(lines) + "\n"


def render_calibration_economics(econ: dict) -> str:
    """The per-STAGE yield/cost table for the calibration note's Economics section.

    This is the consumer seam: the calibration note embeds exactly this block, so
    'where the tokens went' is a table keyed on the pipeline stage instead of the
    coarse prose guess THE RUN's autopsy was forced into."""
    t = econ["totals"]
    lines = [
        "| stage | agents | tokens | in | out | duration | cost |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for ph in sorted(econ["by_phase"], key=_phase_sort_key):
        b = econ["by_phase"][ph]
        lines.append(
            f"| {ph} | {b['agents']} | {_fmt_int(b['total_tokens'])} | "
            f"{_fmt_int(b['input_tokens'])} | {_fmt_int(b['output_tokens'])} | "
            f"{_fmt_dur(b['duration_ms'])} | {_fmt_cost(b['cost_usd'])} |")
    lines.append(
        f"| **TOTAL** | **{t['agents']}** | **{_fmt_int(t['total_tokens'])}** | "
        f"**{_fmt_int(t['input_tokens'])}** | **{_fmt_int(t['output_tokens'])}** | "
        f"**{_fmt_dur(t['duration_ms'])}** | **{_fmt_cost(t['cost_usd'])}** |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def load_stage_manifest(run_dir: Path, manifest_path: "Path | None" = None) -> "list | None":
    """The F1 stage manifest (``[{ordinal,label,phase,model[,prompt_sha,agent_id]}]``),
    from an explicit ``--manifest`` path first, else auto-discovered as
    ``agents_manifest.json`` in the run dir. Returns the list, or None when absent /
    unreadable (the reader then falls back to today's journal behaviour). Accepts
    either a bare list or a ``{"agents": [...]}`` wrapper."""
    cand = manifest_path if manifest_path else (run_dir / "agents_manifest.json")
    if not cand or not Path(cand).is_file():
        return None
    try:
        data = json.loads(Path(cand).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        data = data.get("agents") or data.get("manifest")
    return data if isinstance(data, list) and data else None


def build_economics(run_dir: Path, manifest_path: "Path | None" = None) -> dict:
    """The public entry: run dir -> the economics dict (agents + rollups). A stage
    manifest (F1) is joined when present (explicit path or auto-discovered)."""
    manifest = load_stage_manifest(run_dir, manifest_path)
    return summarize(run_dir, collect_agents(run_dir, manifest=manifest))


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(
        description="Emit one per-run economics artifact (per-agent tokens + "
                    "duration) from a workflow run's transcript directory.")
    ap.add_argument("run_dir", help="the harness transcript dir for one run "
                    "(journal.jsonl and/or agent-<id>.jsonl)")
    ap.add_argument("--out", default=None, help="output dir (default: run dir)")
    ap.add_argument("--rounds-out", default=None, metavar="MANUSCRIPT_DIR",
                    help="a manuscript dir; ALSO write the round-keyed cost adapter to "
                    "<MANUSCRIPT_DIR>/rounds/economics.json (the shape the convergence "
                    "ledger's per-round cost column reads)")
    ap.add_argument("--manifest", default=None, help="the organ's stage manifest "
                    "(ordinal->label/phase/model) to join for per-stage labels; "
                    "default: auto-discover agents_manifest.json in the run dir")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--json-only", action="store_true")
    g.add_argument("--md-only", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv[1:])

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"workflow_economics: no such run directory: {run_dir}",
              file=sys.stderr)
        return 2
    has_journal = (run_dir / "journal.jsonl").exists()
    has_transcripts = any(run_dir.glob("agent-*.jsonl"))
    if not has_journal and not has_transcripts:
        print(f"workflow_economics: {run_dir} holds neither journal.jsonl nor any "
              f"agent-*.jsonl transcript — nothing to read.", file=sys.stderr)
        return 2

    econ = build_economics(run_dir, Path(args.manifest) if args.manifest else None)
    out_dir = Path(args.out) if args.out else run_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    if not args.md_only:
        p = out_dir / "economics.json"
        p.write_text(json.dumps(econ, indent=2) + "\n", encoding="utf-8")
        written.append(p)
    if not args.json_only:
        p = out_dir / "economics.md"
        p.write_text(render_markdown(econ), encoding="utf-8")
        written.append(p)
    if args.rounds_out:
        # Fix 0d: the round-keyed adapter for the convergence ledger, at the location
        # the ledger reads (<manuscript_dir>/rounds/economics.json).
        rp = Path(args.rounds_out) / "rounds" / "economics.json"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(render_rounds_economics(econ), indent=2) + "\n",
                      encoding="utf-8")
        written.append(rp)

    if not args.quiet:
        t = econ["totals"]
        none_src = sum(1 for a in econ["agents"] if a["usage_source"] == "none")
        warn = f" ({none_src} with no recoverable usage)" if none_src else ""
        print(
            f"workflow_economics: {t['agents']} agents · "
            f"{_fmt_int(t['total_tokens'])} tokens (cache-incl) · "
            f"{_fmt_int(t['output_tokens'])} output · {_fmt_dur(t['duration_ms'])} · "
            f"{_fmt_cost(t['cost_usd'])}{warn} -> "
            f"{', '.join(str(p) for p in written)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
