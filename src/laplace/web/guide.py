"""the structural guide (W-guide) — what the engine and the interface do, served at ``/guide``.

His ask, 2026-07-21 (PRM-20260721-structural-guide, banked in contract/promises.jsonl):
"you've never supplied a proper guide for what either you or the interface is doing at a
structural level, and certainly not made it easily available on the interface!" And the
amended three-questions bar: the third question is **"what will this do?"** — prospective,
per verb, before the click: what it writes, what it costs, its PSU class.

This surface is written for a STRANGER: a collaborator who has never seen this repository.
It states plain mechanics once, defines every coined term on first use, and never leans on
insider names. It has THREE things to show, in one page:

  a. What the engine is — the pipeline at a structural level (corpus -> concept graph ->
     narrative plan -> staged build -> converge -> finalize -> release), and the words a
     reader needs (project, generation, debt, work order, the desk). Authored here as data
     (``ENGINE_ACCOUNT``) and rendered by guide-panes.mjs; the truth is reconstructed from
     TECHNICAL_GUIDE.md, PIPELINE_GUIDE.md and the code, then RE-REGISTERED for a human who
     has never read those files.
  b. What each surface does — one section per served surface, rendered FROM the contract
     yamls (``contract/surfaces/*.yaml``). This is the keystone: documentation renders from
     the SAME machine-checked data the suite enforces, so it cannot drift. Each surface
     names its purpose, the stores/routes it reads, and its verbs — each verb answering
     "what will this do" via its ``does`` line (what it writes, its cost, its PSU class).
  d. The session story + the promises ledger — how work actually happens (sessions wake
     from the banked record; work runs as dispatched waves; heavy work banks a work order;
     decisions that need the author land on the desk; every close banks a handoff), and the
     open rows of ``contract/promises.jsonl`` rendered plainly, both directions.

PSU class, defined once (it recurs on every verb): "PSU" is the author's shorthand for the
power-supply / compute budget of the box the engine runs on. A verb is **local-safe** when
firing it runs here and now and spends no model tokens; **model-heavy** when firing it BANKS
a work-order instead — the server spawns nothing and spends nothing, and a later remote
session runs it. Read-only surfaces have no verbs at all.

Pure handler module, the scanner-dispatch contract (mirrors ``analytics`` / ``assets``): the
scanner owns the HTTP server and dispatches ``/guide*`` here via :func:`handle`. This module
NEVER starts a server and NEVER writes — it is GET-only (a write is refused 405). It reads
the roster (:func:`shared_ui.views_roster`), the contract yamls, and the promise ledger.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

_HTML = Path(__file__).resolve().parent / "guide.html"
_JSON = "application/json; charset=utf-8"


def _repo_root() -> Path:
    from laplace.core.checkout import repo_root as rr   # the serving checkout's owner (the server module held the same object under an old name)
    return rr()


def _contract_dir(root: Path | None = None) -> Path:
    return (root or _repo_root()) / "contract"


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, default)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else default
    return (v or default).strip()


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# (a) THE STRUCTURAL ACCOUNT — authored for a stranger, reconstructed from the guides
# and the code, then re-registered here as data guide-panes.mjs renders. Prose only; no
# module paths above the fold, no insider names without a definition.
# ═══════════════════════════════════════════════════════════════════════════

#: The pipeline, stage by stage. Each stage: an id, a title, the one plain sentence of what
#: it does, and (where useful) what it costs. This is the map a stranger reads once.
ENGINE_ACCOUNT: dict[str, Any] = {
    "one_thing": (
        "The engine holds one thing and runs one operation on it. The one thing is a "
        "graded concept graph: a hierarchy of nodes shaped like a pyramid — a few coarse "
        "nodes at the top, many fine nodes at the bottom, each node one scale of an idea. "
        "The one operation is a top-down DESCENT through that pyramid. Run the descent to "
        "READ and you rebuild only what a goal needs from the coarse map down (never "
        "holding the whole) — that is reconstruction. Run it in REVERSE to WRITE and you "
        "project an artefact; wherever the projection can't close, it leaks FRICTION — the "
        "missing piece. Feeding friction back up regrows the graph. Understanding is paid "
        "once, when the graph is folded; every read and write after is a cheap mechanical "
        "render of what was already folded."
    ),
    "pipeline": [
        {"id": "corpus", "title": "corpus",
         "what": "The raw material — the notes, results, and sources a paper is built from. "
                 "Ingested and folded into the concept graph.",
         "cost": "one-time fold"},
        {"id": "conceptric", "title": "concept graph (the conceptric)",
         "what": "The folded graph itself: nodes at grades from coarse (the goal, the spine) "
                 "down to fine (the atoms), each with its derivation edges. You walk it on "
                 "the Conceptric surface.",
         "cost": "read-time is cheap"},
        {"id": "storyboard", "title": "narrative plan (the storyboard)",
         "what": "The plan for the manuscript's spine — which sections in which order, each "
                 "carrying the nodes it must express. This is structure, not prose yet.",
         "cost": "local, token-free to edit"},
        {"id": "staged_build", "title": "staged build",
         "what": "The plan projected into prose. Narrative planners lay out each section, "
                 "prose realisers write it, and a weld pass smooths the seams into one voice. "
                 "This is the expensive language-model leg.",
         "cost": "model-heavy (banked as a work order)"},
        {"id": "converge", "title": "converge (the fixing loop)",
         "what": "The draft recurred against an acceptance contract: a mechanical panel finds "
                 "flaws every round, a fixer routes each to the stage that owns it, and a "
                 "candidate only replaces the incumbent if it strictly improves. It stops at a "
                 "fixed point — re-projecting changes nothing — not at exhaustion.",
         "cost": "model-heavy (banked)"},
        {"id": "finalize", "title": "finalize",
         "what": "The converged draft is named as a real object (a titled PDF, never "
                 "'main.pdf'), its title checked, its bytes frozen.",
         "cost": "local"},
        {"id": "release", "title": "release bundle",
         "what": "A manifest of content hashes over every byte the release depends on, plus "
                 "the frozen evidence. Once it passes, nothing may modify the source or PDF. "
                 "The machine stops here — accepting the paper is the author's call.",
         "cost": "local"},
    ],
    #: The words a reader needs, defined from zero.
    "glossary": [
        {"term": "project", "def":
            "One paper (or paper-like object) the engine is building — its corpus, its "
            "concept graph, its plan, its versions, and its release state, all under one name."},
        {"term": "generation", "def":
            "One pass of writing: the concept graph projected forward into an artefact. A "
            "project goes through many generations as it converges."},
        {"term": "debt", "def":
            "The friction a project still carries — the flaws the fixing loop has found and "
            "not yet closed. Debt going down over rounds is the shape of convergence."},
        {"term": "work order", "def":
            "A banked request for expensive (model-heavy) work. Instead of spending tokens on "
            "this box now, the engine writes a work order; a later remote session picks it up "
            "and runs it. This is how heavy work never stalls the author's machine."},
        {"term": "the desk", "def":
            "The author's worklist. The engine sorts decisions by TYPE — what it can do alone "
            "versus what genuinely needs the AUTHOR (a fork it cannot rule, a draft to ratify, "
            "a work order to consume) — and every author-owned decision lands on the desk, "
            "each ruled in place with its full context."},
        {"term": "PSU class", "def":
            "The compute cost of firing a verb. local-safe = runs here now, no model tokens. "
            "model-heavy = banks a work order, spends nothing now, runs on a later remote "
            "session. A read-only surface has no verbs at all."},
    ],
}

#: (d) THE SESSION STORY — how work actually happens, for a stranger. Plain, once.
SESSION_STORY: list[dict[str, str]] = [
    {"title": "a session wakes from the banked record",
     "body": "The engine does not keep a running memory between sessions. Each session "
             "RECONSTRUCTS itself from what the last one wrote to disk — the handoff, the "
             "diary, the standing law. Continuity is reconstruction, not a saved brain."},
    {"title": "work runs as dispatched waves",
     "body": "Big work is not done by one long thread. An orchestrator splits it into "
             "packets and dispatches each to a worker agent that reconstructs just its "
             "corner of the graph, does its piece, and hands back a clean digest. The "
             "orchestrator holds the map; the workers hold the bodies."},
    {"title": "heavy work banks a work order instead of spinning the author's box",
     "body": "Anything model-heavy is BANKED as a work order rather than run on the spot. "
             "The button says 'banked'; the server spends nothing; a later remote session "
             "runs it. This is the offer law — nothing expensive fires without the author "
             "choosing it, and it never stalls his machine."},
    {"title": "decisions that need the author land on the desk",
     "body": "When the engine hits something only the author can rule — a fork, a draft to "
             "ratify, a finding to confirm — it does not guess. It banks the decision to the "
             "desk, whole, with its full context and live verbs, and moves on."},
    {"title": "every close banks a handoff",
     "body": "At the end of a session the engine folds what it learned back into the graph "
             "and writes a dated handoff, so the next wake reconstructs from current "
             "structure. Nothing done in a session is invisible to the next one."},
]


# ═══════════════════════════════════════════════════════════════════════════
# (b) THE SURFACE CENSUS — rendered FROM the contract yamls, joined to the roster.
# The keystone: this renders from the SAME data the suite enforces, so it cannot drift.
# ═══════════════════════════════════════════════════════════════════════════

def _load_yaml(path: Path) -> dict:
    """Load one contract yaml. Raises on malformed yaml (the guide fails loud, never
    renders a silent lie); an absent file returns ``{}`` so a rostered surface with no
    yaml yet renders plainly 'not declared'."""
    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def render_surface_yaml(path: Path) -> dict:
    """Render ONE contract yaml to the guide's surface payload shape, tolerating every
    field being absent or shaped differently — a verb may carry name, class, route, state,
    and does in any combination, and a sparse yaml renders without its missing fields. Every
    surface now declares a ``does`` per verb (the desk/pipeline seam is backfilled), but the
    renderer still degrades cleanly if one is absent. Never raises on a well-formed yaml."""
    doc = _load_yaml(path)
    verbs_out = []
    for v in doc.get("verbs") or []:
        if not isinstance(v, dict):
            continue
        verbs_out.append({
            # a verb's name: desk.yaml uses class+name; my yamls use name. Render both.
            "name": v.get("name") or "",
            "class": v.get("class") or "",
            "route": v.get("route") or "",
            "state": v.get("state") or "",
            # "does" is the "what will this do" line; every surface now declares one, but the
            # renderer still degrades cleanly if a future verb lands without it.
            "does": v.get("does") or "",
        })
    return {
        "surface": doc.get("surface") or path.stem,
        "purpose": doc.get("purpose") or "",
        "reads": [str(r) for r in (doc.get("reads") or [])],
        "verbs": verbs_out,
        "counts": doc.get("counts") or None,
        "declared": bool(doc),                # False = no yaml on disk for this surface
    }


def surface_contract(surface_id: str, root: Path | None = None) -> dict | None:
    """One surface's rendered contract, joined to its roster row (title, path, in_roster).
    ``None`` when neither a roster row nor a yaml exists for the id."""
    root = (root or _repo_root())
    from laplace.web import shared_ui
    roster = {v["id"]: v for v in shared_ui.views_roster().get("views", [])}
    row = roster.get(surface_id)
    ypath = _contract_dir(root) / "surfaces" / f"{surface_id}.yaml"
    if row is None and not ypath.is_file():
        return None
    out = render_surface_yaml(ypath)
    out["id"] = surface_id
    out["in_roster"] = row is not None
    out["title"] = (row or {}).get("title") or (out["surface"] or surface_id).title()
    out["path"] = (row or {}).get("path") or f"/{surface_id}"
    out["group"] = (row or {}).get("group") or ""
    # the roster's own one-line purpose is the fallback when a yaml has none yet.
    if not out["purpose"]:
        out["purpose"] = (row or {}).get("purpose") or ""
    return out


def surfaces_census(root: Path | None = None) -> list[dict]:
    """Every served surface, one entry, rendered from its yaml + roster row. The roster is
    the census (its rows are the navigable surfaces); a yaml that exists WITHOUT a roster
    row (``map`` — a view of the engine, deliberately off the nav) rides too, flagged
    ``in_roster: false``, so nothing served is silently dropped."""
    root = (root or _repo_root())
    from laplace.web import shared_ui
    ids: list[str] = [v["id"] for v in shared_ui.views_roster().get("views", [])]
    seen = set(ids)
    sdir = _contract_dir(root) / "surfaces"
    if sdir.is_dir():
        for p in sorted(sdir.glob("*.yaml")):
            if p.stem not in seen:
                ids.append(p.stem)
                seen.add(p.stem)
    out = []
    for sid in ids:
        c = surface_contract(sid, root)
        if c is not None:
            out.append(c)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# (d) THE PROMISES LEDGER — the OPEN rows, rendered honestly, both directions.
# ═══════════════════════════════════════════════════════════════════════════

def promises_render(root: Path | None = None) -> dict:
    """The promise ledger's OPEN rows, both directions. A row without a ``direction`` field
    is Eigen's promise to the author (``dir: "eigen"``); ``direction: "his"`` is the
    author's to Eigen (``dir: "his"``). Read-only; every open row rides, none is hidden."""
    root = (root or _repo_root())
    ledger = _contract_dir(root) / "promises.jsonl"
    open_rows: list[dict] = []
    counts = {"open": 0, "eigen": 0, "his": 0}
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("status") != "open":
                continue
            direction = "his" if r.get("direction") == "his" else "eigen"
            open_rows.append({
                "id": r.get("id") or "", "date": r.get("date") or "",
                "ask": r.get("ask") or "", "owner": r.get("owner") or "",
                "dir": direction, "refs": r.get("refs") or [],
            })
            counts["open"] += 1
            counts[direction] += 1
    return {"open": open_rows, "counts": counts}


# ═══════════════════════════════════════════════════════════════════════════
# THE FULL PAYLOAD + the HTTP handler.
# ═══════════════════════════════════════════════════════════════════════════

def full_payload(root: Path | None = None) -> dict:
    """Everything the guide page renders in one read: the structural account, the surface
    census (from the yamls), the session story, and the open promises."""
    root = (root or _repo_root())
    return {
        "engine": ENGINE_ACCOUNT,
        "surfaces": surfaces_census(root),
        "session_story": SESSION_STORY,
        "promises": promises_render(root),
    }


def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/guide*`` request. Returns (status, content_type, body) or ``None`` when
    the path is not ours (the scanner falls through). GET-only — a write is refused 405."""
    if path != "/guide" and not path.startswith("/guide/"):
        return None
    method = (method or "GET").upper()
    if method != "GET":
        return _json_resp(405, {"error": f"{method} not allowed — /guide is read-only"})
    root = _repo_root()

    if path == "/guide":
        if not _HTML.is_file():
            return _json_resp(500, {"error": "guide.html missing on disk"})
        return 200, "text/html; charset=utf-8", _HTML.read_bytes()

    if path == "/guide/data":
        try:
            sid = _q1(query, "surface")
            if sid:
                # the shell's "?" panel asks for ONE surface's contract.
                out = surface_contract(sid, root)
                if out is None:
                    return _json_resp(404, {"error": f"no surface {sid!r} in the roster or contracts"})
                return _json_resp(200, out)
            return _json_resp(200, full_payload(root))
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"guide assembly failed: {e}"})

    return _json_resp(404, {"error": f"no guide route {path!r}"})
