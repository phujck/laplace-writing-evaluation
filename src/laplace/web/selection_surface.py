"""selection_surface.py — the selection desk's doors (heredity's ratify stage).

The F23 readiness verdict named the missing organ: variation ready, heredity ready,
selection missing. The rule (ψ) and the threshold (φ) belong to the author; the fitness
panel is the readings he rules them against. This surface is the ruling as a lawful
door — the ``evolution_surface`` idiom (one module owns the writes; the scanner routes;
every mutation is an append-only ledger record, correctable retrospectively).

The routes:

* ``GET  /selection/sheet?corpus=``  → :func:`selection_sheet.read_selection` (pure
  read; the sheet the author rules against). 400 with no corpus, 404 with no
  manuscript dir.
* ``POST /selection/rule`` ``{corpus, generation_id, verdict, by, armed, reason?}`` —
  the author's attributed verdict on one heredity generation as a door. ``verdict`` ∈
  ``{promote, hold, retire}`` (else 400); unattributed → 422; a generation not in the
  ledger → 404; an existing live selection-ruling on that generation → 409 (contest it
  by appending a later record, never by mutating this one); unarmed → 200
  ``{ok:false, needs_arming:true, ...}`` (the informed second click — the draft it
  would override, the readings it rests on); armed → append one
  :func:`adjudicate.make_selection_ruling` record to ``<md>/feedback/feedback.jsonl``.

Record-only. Unlike the evolution desk's ratify door, this surface applies nothing and
mutates no artifact — a selection ruling is the author's verdict banked against a
generation id, and heredity's promote/retire mechanics read it later. ``overrode_draft``
is computed server-side (the author's verdict against the live draft), never taken from
the client.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import threading
from pathlib import Path
from typing import Any

#: the rule door's critical section — check-then-append must be atomic in-process
#: (the scanner is a ThreadingHTTPServer; see rule()).
_RULE_LOCK = threading.Lock()

_JSON = "application/json; charset=utf-8"

_VERDICTS = ("promote", "hold", "retire")


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _repo_root() -> Path:
    return source_tree()


def _resolve_md(corpus: str) -> Path | None:
    from laplace.pipeline import registry
    proj = registry.resolve(corpus)
    if proj is None or not proj.manuscript_dir:
        return None
    return proj.path(proj.manuscript_dir, _repo_root())


def _generation_row(md: Path, corpus: str, generation_id: str) -> dict | None:
    """The scored generation row from ``<md>/generations.jsonl`` (P2's heredity
    ledger). Read via :func:`generation_ledger.read_generations` when the module is
    importable, else a tolerant direct jsonl read — the interface is frozen but the
    module lands in parallel, so degrade gracefully. ``None`` when absent."""
    rows: list[dict] = []
    try:
        from laplace.pipeline import generation_ledger as gl
        rows = list(gl.read_generations(md) or [])
    except Exception:
        try:
            from laplace.pipeline.ledger import read_jsonl
            rows = read_jsonl(md / "generations.jsonl")
        except Exception:
            rows = []
    return next((r for r in rows if str(r.get("id") or "") == generation_id), None)


def _draft_preview(corpus: str, generation_id: str) -> tuple[str, str, dict | None]:
    """The live DRAFT verdict + the rule version + the SHEET's computed row for one
    generation, read off ``selection_sheet.read_selection``'s REAL payload shape:
    the per-generation ``draft_verdict`` is a dict (``{"verdict", "gates", ...}``)
    and the version sits at ``rule["version"]`` (the 2026-07-21 verifier caught the
    door coded against a shape the sheet never emits — ``overrode_draft`` banked
    wrong on every ruling). Returns ``(draft_verdict, rule_version, sheet_row)``;
    degrades to ``("", "", None)`` when the sheet module is absent or the
    generation is not on it — a ruling can still be banked (the author's verdict
    stands with or without a draft to contrast)."""
    try:
        from laplace.pipeline import selection_sheet as ss
        sheet = ss.read_selection(corpus) or {}
        rule_version = str(((sheet.get("rule") or {}).get("version")) or "")
        for arm in (sheet.get("generations") or []):
            if str(arm.get("id") or "") == generation_id:
                dv = arm.get("draft_verdict")
                verdict = str((dv or {}).get("verdict") or "") if isinstance(dv, dict) \
                    else str(dv or "")
                return verdict, rule_version, arm
        return "", rule_version, None
    except Exception:
        return "", "", None


def _readings_digest(row: dict, sheet_row: dict | None = None) -> dict:
    """The scored generation's readings for the banked record. The sheet's computed
    row is the one source of truth when present (it derives debt from the dated
    refs and freeze from the verdict file — the raw generation row carries only
    refs, never numbers); the raw row's nested ``r10.clean`` is the fallback when
    the sheet is absent."""
    if sheet_row:
        fz = sheet_row.get("freeze")
        r10s = sheet_row.get("r10")
        return {"debt": [sheet_row.get("debt_before"), sheet_row.get("debt_after")],
                "freeze_pass": (fz or {}).get("pass") if isinstance(fz, dict) else None,
                "r10_clean": (r10s or {}).get("clean") if isinstance(r10s, dict)
                             else None}
    r10 = row["r10"].get("clean") if isinstance(row.get("r10"), dict) else None
    return {"debt": [None, None], "freeze_pass": None, "r10_clean": r10}


def _has_selection_ruling(md: Path, generation_id: str) -> bool:
    """A LIVE selection-ruling already banked on this generation (a later ruling
    supersedes it, so :func:`adjudicate.live` lets a contest re-open)."""
    from laplace.pipeline.ledger import read_jsonl
    from laplace.pipeline import adjudicate as adj
    ledger = md / "feedback" / "feedback.jsonl"
    if not ledger.is_file():
        return False
    for r in adj.live(read_jsonl(ledger)):
        if (r.get("record") == adj.SELECTION_RULING
                and str(r.get("generation_id") or r.get("target") or "") == generation_id):
            return True
    return False


def rule(corpus: str, generation_id: str, verdict: str, by: str, *,
         armed: bool = False, reason: str = "") -> tuple[int, dict]:
    """The author's attributed verdict on one generation — record-only. See the module
    doc for the door contract. On the armed write ``overrode_draft`` is the verdict
    against the live draft (computed here, never trusted from the client)."""
    verdict = (verdict or "").strip()
    if verdict not in _VERDICTS:
        return 400, {"ok": False, "error": f"verdict must be one of {list(_VERDICTS)}"}
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False, "error": "by required (a selection ruling is his word — attributed, always)"}
    md = _resolve_md(corpus)
    if md is None:
        return 404, {"ok": False, "error": f"no manuscript dir for corpus {corpus!r}"}
    row = _generation_row(md, corpus, generation_id)
    if row is None:
        return 404, {"ok": False, "error": f"no scored generation {generation_id!r} in the ledger"}
    draft_verdict, rule_version, sheet_row = _draft_preview(corpus, generation_id)
    digest = _readings_digest(row, sheet_row)
    if not armed:
        if _has_selection_ruling(md, generation_id):
            return 409, {"ok": False, "error": (f"generation {generation_id!r} already carries a "
                                                "selection ruling — contest it by appending a later "
                                                "record, never by mutating this one")}
        return 200, {"ok": False, "needs_arming": True, "generation_id": generation_id,
                     "verdict": verdict, "draft_verdict": draft_verdict,
                     "readings_digest": digest,
                     "what": (f"banks your {verdict!r} ruling on generation {generation_id!r} "
                              "(record-only — mutates no artifact) — "
                              're-POST with "armed": true')}
    overrode = bool(draft_verdict and verdict != draft_verdict)
    from laplace.pipeline import adjudicate as adj
    from laplace.pipeline.ledger import append_jsonl
    # One critical section around check-then-append (the dials_surface _DIALS_LOCK
    # idiom): the scanner threads requests, and a lockless duplicate guard was
    # proven racy (24 parallel armed calls banked up to 24 "one-per-generation"
    # rulings — the 2026-07-21 verifier). The lock is in-process, which is the
    # scanner's whole concurrency story.
    with _RULE_LOCK:
        if _has_selection_ruling(md, generation_id):
            return 409, {"ok": False, "error": (f"generation {generation_id!r} already carries a "
                                                "selection ruling — contest it by appending a later "
                                                "record, never by mutating this one")}
        rec = adj.make_selection_ruling(
            generation_id, verdict=verdict, draft_verdict=draft_verdict,
            overrode_draft=overrode, rule_version=rule_version, readings_digest=digest,
            reason=reason, actor=by, project=corpus)
        append_jsonl(md / "feedback" / "feedback.jsonl", rec)
    return 200, {"ok": True, "generation_id": generation_id, "verdict": verdict,
                 "overrode_draft": overrode, "draft_verdict": draft_verdict,
                 "rule_version": rule_version, "readings_digest": digest,
                 "id": rec["id"]}


def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/selection/*`` request; ``None`` = not ours (scanner 404s)."""
    if not path.startswith("/selection/"):
        return None
    method = (method or "GET").upper()

    def _q1(key: str, default: str = "") -> str:
        v = query.get(key)
        if isinstance(v, list):
            v = v[0] if v else ""
        return (v or default).strip()

    if path == "/selection/sheet" and method == "GET":
        corpus = _q1("corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        md = _resolve_md(corpus)
        if md is None:
            return _json_resp(404, {"error": f"no manuscript dir for corpus {corpus!r}"})
        try:
            from laplace.pipeline import selection_sheet as ss
            payload = ss.read_selection(corpus)
        except Exception:
            payload = {"present": False, "corpus": corpus,
                       "degraded": "selection_sheet unavailable"}
        return _json_resp(200, payload)

    if path == "/selection/rule" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        if not isinstance(payload, dict):
            return _json_resp(400, {"error": "body must be an object"})
        corpus = payload.get("corpus") or _q1("corpus")
        generation_id = str(payload.get("generation_id") or "")
        if not corpus or not generation_id:
            return _json_resp(400, {"error": "corpus and generation_id required"})
        st, obj = rule(corpus, generation_id, str(payload.get("verdict") or ""),
                       str(payload.get("by") or ""),
                       # STRICT arming (fail-closed on malformed input): only the JSON
                       # literal true arms — "yes"/"false"/1 do NOT (the truthy-coerce
                       # idiom elsewhere predates this door; the second click is the law
                       # here, so a garbled armed value must read as unarmed).
                       armed=payload.get("armed") is True,
                       reason=str(payload.get("reason") or ""))
        return _json_resp(st, obj)

    return None
