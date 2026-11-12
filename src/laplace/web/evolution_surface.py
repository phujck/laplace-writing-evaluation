"""evolution_surface.py — the evolution desk's doors (the ratify queue, drivable).

His two challenges made structural (2026-07-19, in-chat): *"how am I supposed to
know what I'm ratifying?"* and *"generally I need the context of what I said."*
Until tonight the loop's judgment stage — his ratification of drafted evolution
contracts — lived in RATIFY.md files and chat. This surface is that stage as a
lawful set of doors, the ``dials_surface`` idiom (one module owns the writes; the
scanner routes; every mutation is an append-only ledger record, correctable
retrospectively).

The routes:

* ``GET  /evolution/queue?corpus=``  → :func:`evolution_consumer.read_ratify_queue`
  (pure read; the card payload).
* ``POST /evolution/ratify``  ``{corpus, intent_id, by, armed}`` — the author's
  attributed ratification as a door: fires ``evolve.execute(dry_run=False)`` on the
  drafted contract, then banks the revocation + ratified-operation pair (the
  RATIFY.md close-the-loop step, mechanised). ``armed:true`` required (it mutates the
  corpus ledger — the run_launch arm idiom); unattributed → 422; an un-drafted or
  non-open intent → 404/409; a failed apply banks nothing and reports what failed.
* ``POST /evolution/hold``    ``{corpus, intent_id, by, note?}`` — the hold as a
  typed defer record (valid, not this run — the existing verb, exact semantics).
* ``POST /evolution/reject``  ``{corpus, intent_id, by, reason?}`` — a revocation
  without an apply; the intent retires as ruled-against, never silently dropped.
* ``POST /evolution/ratify-all`` ``{corpus, by, armed}`` — the bulk door, offered
  only under ``evolution.ratify_mode: bulk-arm`` (the dial, his 2026-07-21 ruling):
  one arm round-trip previews every open application; the armed re-POST applies each
  through the same transactional per-item path, banking the same per-item revocation
  + ratified-operation pair, and stops on the first failure reporting exactly what
  applied and what did not. Hold/reject stay per-item.

The law held structurally: the draft-only rule stands — this module contains the only
apply path, and it fires exclusively from an attributed, armed POST (the author's own
cockpit). The ``evolution.ratify_mode`` dial (rides the /dials door like any leaf)
changes the door shape only, never the law: bulk is one attributed ruling applied
item-by-item with per-item records, not a policy that ratifies for the author.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
from pathlib import Path
from typing import Any

_JSON = "application/json; charset=utf-8"


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


def _queue_row(md: Path, intent_id: str) -> dict | None:
    from laplace.pipeline import evolution_consumer as ec
    q = ec.read_ratify_queue(md)
    return next((r for r in q["queue"] if r["intent_id"] == intent_id), None)


def _elsewhere_counts(corpus: str) -> dict[str, int]:
    """Open-intent counts for every other registered project that has any — the
    empty panel's pointer elsewhere. A project whose queue cannot be read counts as
    absent (this is a courtesy read, never a gate)."""
    from laplace.pipeline import registry
    from laplace.pipeline import evolution_consumer as ec
    out: dict[str, int] = {}
    for name in registry.all_projects():
        if name == corpus:
            continue
        try:
            md = _resolve_md(name)
            if md is None:
                continue
            n = sum(1 for r in ec.read_ratify_queue(md)["queue"]
                    if r.get("status") == "open")
        except Exception:
            continue
        if n:
            out[name] = n
    return out


def _apply_one(md: Path, corpus: str, row: dict, by: str, *,
               door: str = "/evolution/ratify") -> tuple[bool, dict]:
    """The single apply leg (per-item and bulk share it byte-for-byte): fire
    ``evolve.execute`` transactionally on the drafted contract, and — only on a
    proven round trip — bank the per-item revocation + ratified-operation pair.
    Returns ``(ok, payload)``; a failed apply banks nothing."""
    from laplace.pipeline import evolve, adjudicate as adj
    from laplace.pipeline.ledger import append_jsonl
    intent_id = row["intent_id"]
    evo_dir = md / "evolution" / "evolutions" / row["dir"]
    rep = evolve.execute(corpus, evo_dir, dry_run=False, repo_root=_repo_root())
    if not (rep.get("ok") and rep.get("round_trip_exact")):
        return False, {"intent_id": intent_id, "error": "apply failed — nothing banked",
                       "report": {k: rep.get(k) for k in ("ok", "round_trip_exact",
                                                          "error", "reason")}}
    ledger = md / "feedback" / "feedback.jsonl"
    added = (rep.get("added") or [""])[0]
    append_jsonl(ledger, adj.make_intent_revocation(
        intent_id, reason=f"consumed by evolution (ratified at the desk by {by})",
        actor=by, project=corpus))
    append_jsonl(ledger, adj.make_ratified_operation(
        intent_id, outcome="applied", op_kind="add-node", object_kind="node",
        object_key=added, reason=f"ratified through {door}",
        corpus=corpus, actor=by, project=corpus))
    # Retention (P3): the apply is a doored "kept" — the author's ratified action
    # survived into the corpus, banked mechanically (source="door", not the session-
    # close hand-judgement). Telemetry never breaks an apply: the pair is already banked.
    try:
        from laplace.engine import telemetry as _tel
        _tel.retention(fate="kept", source="door",
                       artifact=f"{corpus}:{intent_id}",
                       reason=f"ratified through {door}")
    except Exception:
        pass
    return True, {"intent_id": intent_id, "applied": added,
                  "report": {"added": rep.get("added"), "removed": rep.get("removed")}}


def ratify(corpus: str, intent_id: str, by: str, *, armed: bool = False) -> tuple[int, dict]:
    """The author's attributed ratification as a door: apply the drafted contract,
    retire the intent."""
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False, "error": "by required (a ratification is his word — attributed, always)"}
    md = _resolve_md(corpus)
    if md is None:
        return 404, {"ok": False, "error": f"no manuscript dir for corpus {corpus!r}"}
    row = _queue_row(md, intent_id)
    if row is None:
        return 404, {"ok": False, "error": f"no drafted contract for intent {intent_id!r}"}
    if row["status"] != "open":
        return 409, {"ok": False, "error": f"intent {intent_id!r} is {row['status']!r}, not open"}
    if not armed:
        return 200, {"ok": False, "needs_arming": True, "intent_id": intent_id,
                     "what": ("applies the drafted evolution to the corpus ledger "
                              "(evolve.execute, transactional) and retires the intent — "
                              're-POST with "armed": true'),
                     "substance": row["substance"], "mint_ids": row["mint_ids"]}
    ok, payload = _apply_one(md, corpus, row, by)
    if not ok:
        return 422, {"ok": False, **payload}
    return 200, {"ok": True, **payload}


def _ratify_mode() -> str:
    """The desk's door shape from the live dials overlay (defaults ⊕ v1 profile);
    unreadable dials degrade to the strict per-item posture, never the bulk one."""
    try:
        from laplace.pipeline import dials
        mode = ((dials.load_dials().get("evolution") or {}).get("ratify_mode")
                or "per-item")
        return mode if mode in ("per-item", "bulk-arm") else "per-item"
    except Exception:
        return "per-item"


def ratify_all(corpus: str, by: str, *, armed: bool = False) -> tuple[int, dict]:
    """The bulk door: one attributed ruling applied item-by-item. Offered only under
    ``evolution.ratify_mode: bulk-arm``; the unarmed POST previews every open
    application (the informed second click); the armed POST applies each through
    :func:`_apply_one` and stops on the first failure — what applied is banked and
    reported, what did not is named, nothing partial is silent."""
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False, "error": "by required (a ratification is his word — attributed, always)"}
    if _ratify_mode() != "bulk-arm":
        return 409, {"ok": False, "error": ("the bulk door is closed — evolution.ratify_mode "
                                            "is 'per-item'; flip it through /dials to open "
                                            "'ratify all'")}
    md = _resolve_md(corpus)
    if md is None:
        return 404, {"ok": False, "error": f"no manuscript dir for corpus {corpus!r}"}
    from laplace.pipeline import evolution_consumer as ec
    open_rows = [r for r in ec.read_ratify_queue(md)["queue"] if r["status"] == "open"]
    if not open_rows:
        return 409, {"ok": False, "error": "nothing open to ratify"}
    if not armed:
        return 200, {"ok": False, "needs_arming": True, "count": len(open_rows),
                     "what": (f"applies ALL {len(open_rows)} open drafted evolutions to the "
                              "corpus ledger (evolve.execute per item, transactional, "
                              "stop on first failure) and retires each intent — "
                              're-POST with "armed": true'),
                     "preview": [{"intent_id": r["intent_id"], "substance": r["substance"],
                                  "mint_ids": r["mint_ids"]} for r in open_rows]}
    applied: list[dict] = []
    for row in open_rows:
        ok, payload = _apply_one(md, corpus, row, by, door="/evolution/ratify-all")
        if not ok:
            return 422, {"ok": False, "error": "bulk apply stopped at first failure",
                         "applied": applied, "failed": payload,
                         "remaining": [r["intent_id"] for r in open_rows
                                       if r["intent_id"] != payload["intent_id"]
                                       and r["intent_id"] not in
                                       {a["intent_id"] for a in applied}]}
        applied.append(payload)
    return 200, {"ok": True, "applied": applied, "count": len(applied)}


def hold(corpus: str, intent_id: str, by: str, note: str = "") -> tuple[int, dict]:
    """The hold: a typed defer — valid, not this run. Reversible by his later ruling."""
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False, "error": "by required"}
    md = _resolve_md(corpus)
    if md is None:
        return 404, {"ok": False, "error": f"no manuscript dir for corpus {corpus!r}"}
    row = _queue_row(md, intent_id)
    if row is None:
        return 404, {"ok": False, "error": f"no drafted contract for intent {intent_id!r}"}
    if row["status"] not in ("open",):
        return 409, {"ok": False, "error": f"intent {intent_id!r} is {row['status']!r}, not open"}
    from laplace.pipeline import adjudicate as adj
    from laplace.pipeline.ledger import append_jsonl
    append_jsonl(md / "feedback" / "feedback.jsonl",
                 adj.make_defer(intent_id, note=note or "held at the evolution desk",
                                actor=by, project=corpus))
    # Retention (P3): no retention call here — a hold is a typed defer (valid, not
    # this run), not a fate. The work neither survived into the corpus (kept) nor was
    # routed around (bypassed); it is deferred, still open to his later ruling.
    return 200, {"ok": True, "intent_id": intent_id, "status": "held"}


def reject(corpus: str, intent_id: str, by: str, reason: str = "") -> tuple[int, dict]:
    """A ruled-against retire: revocation without an apply — never a silent drop."""
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False, "error": "by required"}
    md = _resolve_md(corpus)
    if md is None:
        return 404, {"ok": False, "error": f"no manuscript dir for corpus {corpus!r}"}
    row = _queue_row(md, intent_id)
    if row is None:
        return 404, {"ok": False, "error": f"no drafted contract for intent {intent_id!r}"}
    if row["status"] != "open":
        return 409, {"ok": False, "error": f"intent {intent_id!r} is {row['status']!r}, not open"}
    from laplace.pipeline import adjudicate as adj
    from laplace.pipeline.ledger import append_jsonl
    append_jsonl(md / "feedback" / "feedback.jsonl",
                 adj.make_intent_revocation(
                     intent_id, actor=by, project=corpus,
                     reason=f"REJECTED at the evolution desk by {by}"
                            + (f": {reason}" if reason else "")))
    # Retention (P3): a reject is a doored "bypassed" — the drafted work was routed
    # around (ruled against, retired without an apply), the real loss the fate names.
    # Banked mechanically (source="door"); telemetry never breaks the reject.
    try:
        from laplace.engine import telemetry as _tel
        _tel.retention(fate="bypassed", source="door",
                       artifact=f"{corpus}:{intent_id}",
                       reason=reason or "rejected at the evolution desk")
    except Exception:
        pass
    return 200, {"ok": True, "intent_id": intent_id, "status": "rejected"}


def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/evolution/*`` request; ``None`` = not ours (scanner 404s)."""
    if not path.startswith("/evolution/"):
        return None
    method = (method or "GET").upper()

    def _q1(key: str, default: str = "") -> str:
        v = query.get(key)
        if isinstance(v, list):
            v = v[0] if v else ""
        return (v or default).strip()

    if path == "/evolution/queue" and method == "GET":
        corpus = _q1("corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        md = _resolve_md(corpus)
        if md is None:
            return _json_resp(404, {"error": f"no manuscript dir for corpus {corpus!r}"})
        from laplace.pipeline import evolution_consumer as ec
        payload = ec.read_ratify_queue(md, corpus)
        # the door shape (the card renders the bulk door only when the dial opens it)
        payload["ratify_mode"] = _ratify_mode()
        # ELSEWHERE (ergonomics, 2026-07-21): an empty panel must read as "wrong
        # corpus selected", never "dead feature" — so the payload names every OTHER
        # project with open intents. Pure jsonl reads (read_ratify_queue), no
        # embed/compile/network; board-paint stays pure-read.
        payload["elsewhere"] = _elsewhere_counts(corpus)
        return _json_resp(200, payload)

    if method == "POST" and path == "/evolution/ratify-all":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        if not isinstance(payload, dict):
            return _json_resp(400, {"error": "body must be an object"})
        corpus = payload.get("corpus") or _q1("corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        st, obj = ratify_all(corpus, str(payload.get("by") or ""),
                             armed=payload.get("armed") is True)
        return _json_resp(st, obj)

    if method == "POST" and path in ("/evolution/ratify", "/evolution/hold",
                                     "/evolution/reject"):
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        if not isinstance(payload, dict):
            return _json_resp(400, {"error": "body must be an object"})
        corpus = payload.get("corpus") or _q1("corpus")
        intent_id = str(payload.get("intent_id") or "")
        by = str(payload.get("by") or "")
        if not corpus or not intent_id:
            return _json_resp(400, {"error": "corpus and intent_id required"})
        if path.endswith("ratify"):
            # armed-is-True STRICTNESS (E4b): the truthy-coercion bug — bool("false")
            # is True, so a stray string armed a live ratify. The siblings
            # (selection/derivation surfaces) all gate on ``is True``; unify here.
            st, obj = ratify(corpus, intent_id, by, armed=payload.get("armed") is True)
        elif path.endswith("hold"):
            st, obj = hold(corpus, intent_id, by, note=str(payload.get("note") or ""))
        else:
            st, obj = reject(corpus, intent_id, by, reason=str(payload.get("reason") or ""))
        return _json_resp(st, obj)

    return None
