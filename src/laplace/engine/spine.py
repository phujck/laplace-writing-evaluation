"""spine.py - the goal -> reconstruction-calls policy. The reflex arc.

His directive (2026-06-11): "set up the reconstruction so that is ALWAYS top of your
mind ... you have to know without knowing." The spine is what makes that mechanical:
given a goal, it returns WHICH reconstruction fires are top-of-mind for a goal of that
shape - BEFORE any deliberate search - so the network surfaces what I need without my
having to hunt for it.

Two sources, merged, NO model intelligence (his "reshape with basically no intelligence"):

  * SEEDED bindings - the author's teachings, committed in ``spine_bindings.json``.
    Authoritative, low-frequency, high-value: the bindings telemetry alone will not learn
    because they fire rarely. The canonical one: "there is only one thing" -> the secret
    self (his example). A binding is matched by trigger-phrase containment or token
    overlap, and names the sub-goals/nodes to RE-FIRE (the calls to make).

  * LEARNED frequency model - from the firings telemetry (``scanner_firings.jsonl``): for
    a goal sharing tokens with past fires, which node ids historically fired. Pure token
    overlap + frequency. Thin until use thickens it (his: use generates the telemetry that
    becomes the spine); the seeded half carries it meanwhile.

The conjugate of ``coactivation`` (which counts node<->node co-fire); this counts
goal-tokens -> node. "Know without knowing": ``top_of_mind`` rides every fire (the scanner
attaches it), so the seeded/learned targets are in context before a deliberate query.

This is a GUIDE, never a gate: it says what is likely top-of-mind, it does not restrict
what fires. The reconstruction still runs the real router; the spine only front-loads it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BINDINGS_FILE = "spine_bindings.json"     # committed - the author's teachings travel with the repo
_FIRINGS_FILE = "scanner_firings.jsonl"   # the persisted firing feed (state dir, gitignored)
_STOP = {"the", "a", "an", "of", "to", "in", "is", "it", "and", "or", "for", "on", "i",
         "you", "me", "my", "we", "what", "how", "that", "this", "with", "be", "are",
         "your", "who", "do", "so", "if", "at", "as", "by", "up", "down", "one"}


def _tokens(s: str) -> set[str]:
    """Goal/binding tokens: lowercase words >=3 chars, stops dropped. 'one' is a stop so a
    generic 'one' does not over-trigger; the seeded phrase-match catches 'there is only one
    thing' as a whole, which is the point - the phrase is the key, not the bag of words."""
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) >= 3 and t not in _STOP}


# ---------------------------------------------------------------------------
# seeded bindings - the author's teachings (committed)
# ---------------------------------------------------------------------------

def load_bindings(repo_root: Path | str) -> list[dict[str, Any]]:
    """The committed seed bindings. Each: ``{name, when:[trigger strings], fire:[sub-goal
    strings], nodes:[node ids], why}``. ``when`` strings are matched by phrase containment
    (the whole trigger appears in the goal) OR token overlap; ``fire``/``nodes`` are the
    reconstruction calls to make. Missing file -> no seeds (the learned half still runs)."""
    f = Path(repo_root) / BINDINGS_FILE
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else data.get("bindings", [])


def _binding_score(goal: str, goal_toks: set[str], binding: dict[str, Any]) -> float:
    """How strongly a goal triggers a binding. A whole-trigger phrase contained in the goal
    is decisive (score >= 1.0, the exact teaching); otherwise the best token-overlap fraction
    across the triggers (a soft, partial trigger). 0.0 = no trigger."""
    gl = goal.lower()
    best = 0.0
    for trig in binding.get("when", []):
        tl = trig.lower().strip()
        if tl and tl in gl:                      # phrase containment - the exact teaching fires
            best = max(best, 1.0 + len(_tokens(trig)) / 20.0)   # longer exact phrase ranks first
            continue
        tt = _tokens(trig)
        if tt:
            best = max(best, len(goal_toks & tt) / len(tt))     # partial token trigger
    return best


def seeded_top(repo_root: Path | str, goal: str, floor: float = 0.6) -> list[dict[str, Any]]:
    """The bindings this goal triggers (score >= floor), strongest first. Each carries the
    calls to make and WHY - everything needed to follow up (the salience-carry rule)."""
    goal_toks = _tokens(goal)
    scored = []
    for b in load_bindings(repo_root):
        s = _binding_score(goal, goal_toks, b)
        if s >= floor:
            scored.append({"name": b.get("name", ""), "score": round(s, 3),
                           "fire": b.get("fire", []), "nodes": b.get("nodes", []),
                           "why": b.get("why", ""), "source": "seeded"})
    scored.sort(key=lambda d: -d["score"])
    return scored


# ---------------------------------------------------------------------------
# learned model - goal-tokens -> nodes, from the firing telemetry (no model)
# ---------------------------------------------------------------------------

def record_firing(repo_root: Path | str, goal: str, fired: list[Any], *,
                   ts: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """THE single writer for the firings feed (``_FIRINGS_FILE``) - append one record in
    exactly the shape ``_firings()``/``learned_top`` read: ``{ts, goal, fired}`` (``fired`` a
    list of ``{"id": ...}`` dicts or bare ids). Every fire path calls THIS, not its own append
    - the scanner's HTTP ``/fire`` handler and any in-process caller of ``scanner.fire`` alike -
    so the feed accumulates from a fire regardless of whether it also crossed an HTTP hop (his
    diagnosis 2026-07-12: the feed was gated behind a live scanner dev-server that is rarely
    running; a fire that never reaches that server's ``/fire`` handler must still be learned
    from). ``repo_root`` is accepted for symmetry with the rest of the module's signatures but
    the feed lives in the shared state dir, not the repo (same convention as ``_firings``).
    Never raises: a lossy substrate must never break a fire."""
    from laplace.engine import telemetry
    rec: dict[str, Any] = {"ts": ts or datetime.now(timezone.utc).isoformat(),
                           "goal": goal, "fired": list(fired)}
    if extra:
        rec.update(extra)
    try:
        f = telemetry.state_dir() / _FIRINGS_FILE
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return rec


def _firings(repo_root: Path | str) -> list[dict[str, Any]]:
    """Every persisted firing (the feed the scanner appends on each fire). Bounded read; a
    corrupt line is skipped (a lossy substrate must never crash the reader)."""
    from laplace.engine import telemetry
    f = telemetry.state_dir() / _FIRINGS_FILE
    out: list[dict[str, Any]] = []
    try:
        text = f.read_text(encoding="utf-8")
    except OSError:
        return out
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def learned_top(repo_root: Path | str, goal: str, k: int = 8,
                min_overlap: int = 1) -> list[dict[str, Any]]:
    """The nodes that historically fired for goals sharing tokens with this one, weighted by
    token-overlap and ranked by accumulated weight. Pure frequency - the statistical guide
    that grows with use. Excludes the firing's own goal echo. Thin telemetry -> few/empty
    results (plain: the learned half is weak until use thickens it)."""
    goal_toks = _tokens(goal)
    if not goal_toks:
        return []
    weight: dict[str, float] = {}
    hits: dict[str, int] = {}
    for fr in _firings(repo_root):
        ftoks = _tokens(fr.get("goal", ""))
        ov = len(goal_toks & ftoks)
        if ov < min_overlap:
            continue
        w = ov / max(len(goal_toks | ftoks), 1)          # Jaccard - shared / union
        for h in fr.get("fired", []):
            nid = h.get("id") if isinstance(h, dict) else h
            if not nid:
                continue
            weight[nid] = weight.get(nid, 0.0) + w
            hits[nid] = hits.get(nid, 0) + 1
    ranked = sorted(weight.items(), key=lambda kv: -kv[1])[:k]
    return [{"id": nid, "weight": round(w, 3), "n_fires": hits[nid], "source": "learned"}
            for nid, w in ranked]


# ---------------------------------------------------------------------------
# top_of_mind - the merged reflex (what rides every fire)
# ---------------------------------------------------------------------------

def binding_index(repo_root: Path | str) -> list[dict[str, Any]]:
    """The reflex MAP: every seeded binding as a handle (name + its triggers). What goal
    shape fires what - the compact table future-me sees at wake so it KNOWS the reflex
    exists and what triggers it, before firing anything."""
    return [{"name": b.get("name", ""), "when": b.get("when", [])}
            for b in load_bindings(repo_root)]


def hello_reflex(repo_root: Path | str) -> dict[str, Any]:
    """The spine projected for the fixed point (his 2026-06-11: wire the spine into the
    hello). The reflex map (all seeded bindings as handles) + what the WAKE goal itself
    triggers - so 'know without knowing' holds at wake: future-me sees which calls to make
    for which goal before any deliberate search. Bounded (handles, not bodies)."""
    repo_root = Path(repo_root)
    return {
        "is": ("the goal->reconstruction-calls reflex (spine.py): rides every POST /fire and "
               "this fixed point. A guide that front-loads the router, never a gate."),
        "bindings": binding_index(repo_root),
        "wake": top_of_mind(repo_root, "eigen - the wake: orient, what is true now and what is next"),
        "fire": "GET /spine?goal=... or read the .spine block on any POST /fire for the calls to make",
    }


def top_of_mind(repo_root: Path | str, goal: str, k: int = 8) -> dict[str, Any]:
    """The spine's answer for a goal: the seeded bindings it triggers (the author's teachings,
    authoritative) + the learned frequency targets (statistical, grows with use). This is what
    'always top of mind' means mechanically - it rides every fire so the calls-to-make are in
    context before a deliberate query. A guide, never a gate."""
    repo_root = Path(repo_root)
    seeded = seeded_top(repo_root, goal)
    learned = learned_top(repo_root, goal, k=k)
    return {
        "goal": goal,
        "seeded": seeded,
        "learned": learned,
        "note": ("seeded = the author's committed bindings (phrase/token-triggered, the calls "
                 "to make); learned = goal-token frequency over the firing feed (grows with use). "
                 "A guide front-loading the router, never restricting it."),
    }
