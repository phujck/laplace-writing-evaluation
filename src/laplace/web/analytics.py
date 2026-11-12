"""The analytics dashboard — a read-only cross-project convergence rollup.

The honesty north star: a project that never ran renders "never run", NEVER an
empty chart implying zero findings; a round with no economics record renders
"never captured", never a fabricated 0. No number on this surface is invented —
every figure is either read from a banked round record or named absent.

One READ-ONLY sibling of ``/altitude`` / ``/storyboard`` / ``/review``:

  * ``GET /analytics``            — the dashboard page (reads its own data).
  * ``GET /analytics/data``       — all-projects rollup: per project the release
                                    state (NEVER_RUN plain), harnessed round
                                    count, the newest round's hard/soft contract
                                    snapshot, and a cost total (or "never
                                    captured").
  * ``GET /analytics/data?project=<name>`` — the full per-round series for one
                                    project, straight from the P7 assembler
                                    (``convergence_ledger.assemble_ledger``): the
                                    single source of truth, called at request
                                    time, never re-derived and never cached.

The loop interrogation surface (ARMING_2026-07-16 · TRAJECTORY SURFACE) — the rebuilt
face reads the banked LOOP_TRAJECTORY records through :mod:`laplace.engine.loop_trajectory` (the
reader organ; this module only routes to it):

  * ``GET /analytics/loop``               — the board: rounds as cards (the finding
                                    derivative visible), the census row, the top doors.
  * ``GET /analytics/loop/round?n=<N>``   — one round's full drill: classes, reader
                                    exemplars, lens retrieval sidecars, before/after
                                    semantic loci, intents, basins, gate, rulings joined
                                    with contest doors, the GENUINELY-HIS residue.

GET only — no write verbs live here; a substrate hiccup is a 500, never a crash.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
from pathlib import Path
from typing import Any

from laplace.engine import loop_trajectory
from laplace.web import shared_ui
from laplace.pipeline import project_state, registry
from laplace.pipeline.convergence_ledger import assemble_ledger

_HTML = Path(__file__).resolve().parent / "analytics.html"
_NEVER = "never captured"


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key)
    if isinstance(v, list):
        return v[0] if v else default
    return v if v is not None else default


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, "application/json; charset=utf-8", json.dumps(obj).encode("utf-8")


def _cost_rollup(rounds: list[dict]) -> dict:
    """Sum the numeric round costs; when none are captured, name it absent (never a
    fabricated 0). ``captured_rounds`` (joined mech/detect rounds) and
    ``econ_only_rounds`` (costs banked with no round record) ride alongside so the page
    can say "N=0" and label banked-but-orphaned cost plainly."""
    nums = [r for r in rounds
            if isinstance(r.get("cost"), (int, float)) and not isinstance(r.get("cost"), bool)]
    if not nums:
        return {"status": _NEVER, "captured_rounds": 0, "econ_only_rounds": 0, "total": None}
    captured = sum(1 for r in nums if not r.get("econ_only"))
    econ_only = sum(1 for r in nums if r.get("econ_only"))
    return {"status": "captured", "captured_rounds": captured,
            "econ_only_rounds": econ_only, "total": sum(r["cost"] for r in nums)}


def _snapshot(rounds: list[dict], grp: str) -> dict:
    """The newest round's contract values for a gate group (hard/soft) — dim -> value.
    Empty when the project has no rounds (plain: never a zero-filled shell)."""
    if not rounds:
        return {}
    last = rounds[-1]
    return {d: t["value"] for d, t in (last["gates"].get(grp) or {}).items()}


def _fallback_rows(repo_root: Path | None) -> list[dict]:
    """The roster when ``registry.project_states`` is absent: all_projects joined to
    ``release.current_state`` (NEVER_RUN when the state sidecar has never been written)."""
    from laplace.pipeline import release
    rows: list[dict] = []
    for name, proj in registry.all_projects().items():
        md = proj.path(proj.manuscript_dir, repo_root) if proj.manuscript_dir else None
        state, rounds_n = "NEVER_RUN", 0
        if md is not None:
            if (md / "release" / "state.json").is_file():
                try:
                    state = release.current_state(md)
                except Exception:
                    state = "STAGED"
            harnessed = md / "rounds" / "harnessed"
            if harnessed.is_dir():
                rounds_n = sum(1 for _ in harnessed.glob("mech_r*.json"))
        rows.append({"name": name, "kind": proj.kind, "state": state, "rounds_n": rounds_n})
    return rows


def _rollup(repo_root: Path | None) -> dict:
    """The cross-project rollup. Roster from ``registry.project_states`` (feature-detected,
    NEVER_RUN preserved); each round-bearing project enriched from the assembler."""
    if hasattr(registry, "project_states"):
        rows = registry.project_states(repo_root)
    else:
        rows = _fallback_rows(repo_root)

    root = Path(repo_root).resolve() if repo_root is not None \
        else source_tree()
    out: list[dict] = []
    for row in rows:
        name = row.get("name")
        rounds_n = int(row.get("rounds_n") or 0)
        hard: dict = {}
        soft: dict = {}
        cost = {"status": _NEVER, "captured_rounds": 0, "econ_only_rounds": 0, "total": None}
        rounds: list[dict] = []
        if rounds_n:
            led = assemble_ledger(name, repo_root)
            rounds = led.get("rounds") or []
            hard = _snapshot(rounds, "hard")
            soft = _snapshot(rounds, "soft")
            cost = _cost_rollup(rounds)
        # ACT 1 (item 3) — JOIN the ONE truth-layer verdict, so a NEVER_RUN-stated project
        # that has minted a release (paper_falqon, ssg-disclosure) reads its true position
        # ("pre-release · GEN-3") here EXACTLY as the dashboard card and the L1 pill do,
        # never a bare "NEVER_RUN" the dashboard already contradicts. rounds_n stays the
        # registry count both surfaces read, so the numbers agree by construction.
        try:
            verdict = project_state.project_verdict(root, name)
        except Exception:  # a verdict hiccup never breaks the rollup — the row degrades to raw state
            verdict = None
        gen = (verdict or {}).get("generations", {}).get("gen") if verdict else None
        art = (verdict or {}).get("artefact") if verdict else None
        out.append({
            "name": name,
            "kind": row.get("kind"),
            "state": row.get("state"),
            "position": shared_ui.position_words(verdict),
            "generation": gen,
            "minted": ((art or {}).get("minted_at") or "")[:10] if art else "",
            "rounds_n": rounds_n,
            # W1.2 THE CONTRADICTION CELL, SPLIT: the single "rounds" number
            # conflated two DIFFERENT read-models — the registry's glob/state count
            # (``claimed``) and the P7 assembler's actual round records (``ledger``,
            # split into real ``captured`` + orphaned ``econ_only``). When they
            # disagree (eigenengine "rounds=5" vs {1,2,3}+econ-only-6 on disk) the
            # page must SHOW the split, not one contradictory figure. This is the
            # structural surfacing; W3.1 kills the divergence at source (versions JOIN).
            "rounds_split": {
                "claimed": rounds_n,
                "ledger": len(rounds),
                "captured": cost["captured_rounds"],
                "econ_only": cost["econ_only_rounds"],
                "contradiction": bool(rounds_n != len(rounds)),
            },
            "hard": hard,
            "soft": soft,
            "cost": cost,
        })
    return {"projects": out}


def handle(path: str, query: dict, method: str, body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/analytics*`` request. Returns (status, content_type, body) or None
    when the path is not ours (the scanner falls through). READ-ONLY: GET only."""
    if path != "/analytics" and not path.startswith("/analytics/"):
        return None
    method = (method or "GET").upper()
    if method != "GET":
        return _json_resp(405, {"error": f"{method} not allowed — /analytics is read-only"})

    if path == "/analytics":
        if not _HTML.is_file():
            return _json_resp(500, {"error": "analytics.html missing on disk"})
        return 200, "text/html; charset=utf-8", _HTML.read_bytes()

    if path == "/analytics/data":
        project = _q1(query, "project")
        try:
            if project:
                out = assemble_ledger(project)
                if "error" in out:
                    return _json_resp(404, out)
                return _json_resp(200, out)
            return _json_resp(200, _rollup(None))
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"analytics assembly failed: {e}"})

    # THE LOOP INTERROGATION SURFACE — the board and one round's drill, both read from the
    # banked LOOP_TRAJECTORY records via the reader organ (never re-derived here).
    if path == "/analytics/loop":
        try:
            return _json_resp(200, loop_trajectory.board())
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"loop board assembly failed: {e}"})

    if path == "/analytics/loop/round":
        raw = _q1(query, "n")
        try:
            rnd = int(raw)
        except (TypeError, ValueError):
            return _json_resp(400, {"error": f"round query 'n' must be an integer, got {raw!r}"})
        try:
            out = loop_trajectory.round_detail(None, rnd)
            if "error" in out:
                return _json_resp(404, out)
            return _json_resp(200, out)
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"loop round assembly failed: {e}"})

    return _json_resp(404, {"error": f"no analytics route {path!r}"})
