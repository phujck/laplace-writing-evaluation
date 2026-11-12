"""derivation_surface.py — the derivation face's doors (the aspiration-first organ,
drivable). His instruction: *"the interface incorporates both inspection and
interaction."*

The derivation organ (``pipeline/derivation_organ.py``) is the aspiration-first reach
instrument — the maximal true claim asserted as the boundary condition before
achievability is known, and the isnad chain from the substrate toward it, each link
``attested`` (a forged ``.tex`` derivation / a computation / a cite) or a named
``gap`` (the structured residual, not a retreat to a weaker claim). That organ is a
pure reader. This surface is its interaction half — the ``selection_surface`` idiom
(one module owns the writes; the scanner routes; every mutation is an append-only
ledger record, correctable retrospectively).

The routes:

* ``GET  /derivation/sheet?corpus=``            → :func:`read_sheet` (pure read; the
  aspiration + chain + reach, joined — the card he inspects). 400 no corpus, 404 no
  manuscript dir.
* ``GET  /derivation/fragment?corpus=&link=``   → the forged ``.tex`` text for one
  link, path-fenced to ``<md>/aspiration/derivations/`` (read-only; a traversal is
  403, an absent fragment 404).
* ``POST /derivation/rescope`` ``{corpus, by, armed, claim, reason?}`` — re-scope the
  aspiration by an appended revision. ``aspiration.json`` stays the latest-pointer;
  the prior record is appended to ``aspiration/aspiration_history.jsonl`` before the
  new claim overwrites the pointer (never edit-in-place without the history banked).
  Unattributed → 422; empty claim → 400; unarmed → the informed second click (the
  claim it would supersede); armed → the history-append + pointer-rewrite, atomic.
* ``POST /derivation/forge``  ``{corpus, link_id, by, armed}`` — bank a work-order for
  the next forging attempt on a ``gap`` link (the offer law: model-heavy banks,
  spawns nothing). An already-``attested`` link → 409 (contest it, don't re-forge);
  an unknown link → 404.
* ``POST /derivation/contest`` ``{corpus, link_id, by, armed, reason}`` — append a
  contest record to ``chain.jsonl``. The link's ``status`` is carried unchanged on the
  contest record, so last-wins reads are unaffected until a re-attestation lands; the
  contest rides as a later record (the retrospective-correction idiom). Empty reason →
  400 (a contest must state its grounds).

All doors: ``armed`` must be the JSON literal ``true`` (strict — a garbled armed value
reads as unarmed, the second click is the law); attributed always (422 otherwise);
typed refusals inline; a lock around every check-then-append (the scanner threads).
"""
from __future__ import annotations
from laplace.pipeline.derivation_organ import _CHAIN_REL, _DERIVATIONS_REL, read_sheet
from laplace.core.checkout import source_tree

import datetime as _dt
import json
import threading
from pathlib import Path
from typing import Any

#: the write doors' critical section — check-then-append must be atomic in-process
#: (the scanner is a ThreadingHTTPServer, exactly the selection desk's _RULE_LOCK).
_DERIVATION_LOCK = threading.Lock()

_JSON = "application/json; charset=utf-8"

_ASPIRATION_REL = "aspiration/aspiration.json"
_HISTORY_REL = "aspiration/aspiration_history.jsonl"
_WORK_ORDER_STORE = "corpus_friction/work_orders.jsonl"


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _repo_root() -> Path:
    return source_tree()


def _resolve_md(corpus: str, repo_root=None) -> Path | None:
    from laplace.pipeline import registry
    proj = registry.resolve(corpus, repo_root=repo_root)
    if proj is None or not proj.manuscript_dir:
        return None
    return proj.path(proj.manuscript_dir, repo_root or _repo_root())


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _read_json(p: Path) -> dict | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None




# ---------------------------------------------------------------------------
# THE READ — the aspiration + chain + reach, joined (view=mechanism: the organ's
# OWN readers, never a re-parse). Pure; both GET /derivation/sheet and
# pipeline_surface.read_organ("derivation") serve this ONE join.
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# GET /derivation/fragment — one forged .tex, path-fenced (read-only)
# ---------------------------------------------------------------------------

def fragment(corpus: str, link: str) -> tuple[int, dict]:
    """The forged ``.tex`` text for one link, fenced to ``<md>/aspiration/derivations/``.
    A path-shaped ``link`` that escapes the fence is refused 403; an absent fragment
    404. Read-only — never a write, never a compile."""
    link = (link or "").strip()
    if not link:
        return 400, {"ok": False, "error": "link required"}
    md = _resolve_md(corpus)
    if md is None:
        return 404, {"ok": False, "error": f"no manuscript dir for corpus {corpus!r}"}
    base = (md / _DERIVATIONS_REL).resolve()
    target = (base / f"{link}.tex").resolve()
    try:
        target.relative_to(base)             # containment: checked, never assumed
    except ValueError:
        return 403, {"ok": False, "error": f"link {link!r} escapes the derivations fence"}
    if not target.is_file():
        return 404, {"ok": False, "link": link, "present": False,
                     "error": f"no forged fragment for link {link!r} "
                              "(an unforged gap has no .tex)"}
    try:
        tex = target.read_text(encoding="utf-8")
    except OSError as e:
        return 500, {"ok": False, "error": f"fragment unreadable: {e}"}
    return 200, {"ok": True, "link": link, "present": True, "tex": tex}


# ---------------------------------------------------------------------------
# POST /derivation/rescope — re-scope the boundary claim by appended revision
# ---------------------------------------------------------------------------

def rescope(corpus: str, by: str, claim: str, *, armed: bool = False,
            reason: str = "", repo_root=None) -> tuple[int, dict]:
    """Re-scope the aspiration's maximal claim. ``aspiration.json`` stays the
    latest-pointer; the prior record is banked to ``aspiration_history.jsonl`` before
    the pointer is rewritten (never an edit-in-place without the history banked). The
    prior's ``reach_axes`` + ``demonstrandum`` carry forward (the boundary moved, the
    supporting structure is the best available until re-derived)."""
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False, "error": "by required (a re-scope is his word — attributed, always)"}
    claim = (claim or "").strip()
    if not claim:
        return 400, {"ok": False, "error": "claim required (the new boundary condition)"}
    md = _resolve_md(corpus, repo_root)
    if md is None:
        return 404, {"ok": False, "error": f"no manuscript dir for corpus {corpus!r}"}
    asp_path = md / _ASPIRATION_REL
    prior = _read_json(asp_path)
    prior_claim = (prior or {}).get("claim_maximal") or ""
    if not armed:
        return 200, {"ok": False, "needs_arming": True, "claim": claim,
                     "supersedes": prior_claim,
                     "what": ("re-scopes the boundary condition; banks the prior claim "
                              "to aspiration_history.jsonl, then rewrites the "
                              'aspiration.json pointer — re-POST with "armed": true')}
    now = _now()
    with _DERIVATION_LOCK:
        # re-read inside the lock so a concurrent re-scope can't drop a revision.
        prior = _read_json(asp_path)
        revision = int((prior or {}).get("revision") or 0) + 1
        if prior is not None:
            hist_rec = dict(prior)
            hist_rec["_superseded_at"] = now
            hist_rec["_superseded_by"] = by
            hist_rec["_superseded_reason"] = reason
            from laplace.pipeline.ledger import append_jsonl
            append_jsonl(md / _HISTORY_REL, hist_rec)
        new_rec = {
            "record": "aspiration",
            "claim_maximal": claim,
            "reach_axes": (prior or {}).get("reach_axes") or {},
            "demonstrandum": (prior or {}).get("demonstrandum") or [],
            "revision": revision,
            "banked_by": by,
            "reason": reason,
            "_rescoped_from": prior_claim,
            "ts": now,
        }
        asp_path.parent.mkdir(parents=True, exist_ok=True)
        asp_path.write_text(json.dumps(new_rec, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    return 200, {"ok": True, "revision": revision, "claim_maximal": claim,
                 "history_appended": prior is not None,
                 "note": ("re-scoped; the prior claim is banked to "
                          "aspiration_history.jsonl") if prior is not None
                 else "first aspiration banked (no prior to supersede)"}


# ---------------------------------------------------------------------------
# POST /derivation/forge — bank a work-order for the next forging attempt on a GAP
# ---------------------------------------------------------------------------

def _chain_link(md: Path, link_id: str) -> dict | None:
    from laplace.pipeline import derivation_organ as do
    return next((l for l in do.read_chain(md) if l["id"] == link_id), None)


def forge(corpus: str, link_id: str, by: str, *, armed: bool = False) -> tuple[int, dict]:
    """Bank one work-order for the next forging attempt on a ``gap`` link (the offer
    law: model-heavy banks, spends no tokens, spawns nothing — a later session forges
    the derivation). An already-``attested`` link is 409 (contest it, don't re-forge);
    an unknown link 404."""
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False, "error": "by required (a forge order is attributed, always)"}
    link_id = (link_id or "").strip()
    if not link_id:
        return 400, {"ok": False, "error": "link_id required"}
    md = _resolve_md(corpus)
    if md is None:
        return 404, {"ok": False, "error": f"no manuscript dir for corpus {corpus!r}"}
    link = _chain_link(md, link_id)
    if link is None:
        return 404, {"ok": False, "error": f"no chain link {link_id!r}"}
    if link["status"] == "attested":
        return 409, {"ok": False, "error": (f"link {link_id!r} is already attested — "
                                            "contest it by appending a later record, "
                                            "never re-forge an attested link")}
    brief = (f"forge the derivation for GAP link {link_id!r}: "
             f"{link['from']} -> {link['to']} ({link['kind']}). "
             f"{(link.get('why') or 'the named residual — attest it or name why it cannot be forged')}")
    if not armed:
        return 200, {"ok": False, "needs_arming": True, "link_id": link_id,
                     "from": link["from"], "to": link["to"], "kind": link["kind"],
                     "what": ("banks a model-heavy work-order for the next forging "
                              f"attempt on {link_id!r} (spends no tokens; a later "
                              'session runs it) — re-POST with "armed": true'),
                     "brief": brief}
    root = _repo_root()
    with _DERIVATION_LOCK:
        # re-check the gap inside the lock (a concurrent attestation could have landed).
        link = _chain_link(md, link_id)
        if link is None:
            return 404, {"ok": False, "error": f"no chain link {link_id!r}"}
        if link["status"] == "attested":
            return 409, {"ok": False, "error": (f"link {link_id!r} is already attested — "
                                                "contest it, never re-forge")}
        rec = {
            "id": _dt.datetime.now().strftime("WO-%Y%m%d-%H%M%S-%f"),
            "ts": _now(),
            "record": "work-order",
            "kind": "work-order",
            "action": "derivation-forge",
            "corpus": corpus,
            "link_id": link_id,
            "what": brief,
            "why": "banked from the derivation face — a gap arms its next forging attempt",
            "requested_by": by,
            "cost_class": "model-heavy",
            "status": "open",
        }
        from laplace.pipeline.ledger import append_jsonl
        append_jsonl(root / _WORK_ORDER_STORE, rec)
    return 200, {"ok": True, "cost_class": "model-heavy", "spawned": False,
                 "work_order": rec,
                 "note": ("banked a work-order — the server spends no tokens; a later "
                          "session forges the derivation")}


# ---------------------------------------------------------------------------
# POST /derivation/contest — append a contest record (status carried unchanged)
# ---------------------------------------------------------------------------

def contest(corpus: str, link_id: str, by: str, reason: str, *,
            armed: bool = False) -> tuple[int, dict]:
    """Append a contest record to ``chain.jsonl``. The link's ``status`` is carried
    unchanged on the contest record, so ``derivation_organ.read_chain``'s last-wins
    projection is unaffected until a re-attestation lands; the contest rides as a
    later record (the retrospective-correction idiom, the selection desk's exact
    shape). A contest must state its grounds — empty reason 400."""
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False, "error": "by required (a contest is attributed, always)"}
    link_id = (link_id or "").strip()
    if not link_id:
        return 400, {"ok": False, "error": "link_id required"}
    reason = (reason or "").strip()
    if not reason:
        return 400, {"ok": False, "error": "reason required (a contest must state its grounds)"}
    md = _resolve_md(corpus)
    if md is None:
        return 404, {"ok": False, "error": f"no manuscript dir for corpus {corpus!r}"}
    link = _chain_link(md, link_id)
    if link is None:
        return 404, {"ok": False, "error": f"no chain link {link_id!r}"}
    if not armed:
        return 200, {"ok": False, "needs_arming": True, "link_id": link_id,
                     "status": link["status"],
                     "what": (f"appends a contest to link {link_id!r} — its status "
                              f"({link['status']}) is carried UNCHANGED, so last-wins "
                              "reads stay put until a re-attestation lands — re-POST "
                              'with "armed": true')}
    now = _now()
    with _DERIVATION_LOCK:
        link = _chain_link(md, link_id)
        if link is None:
            return 404, {"ok": False, "error": f"no chain link {link_id!r}"}
        # build the contest from read_chain's clean projection: status/from/to/kind/
        # attestation carried verbatim so last-wins is byte-identical except for the
        # _contest marker + the later ts.
        rec = {
            "id": link_id,
            "from": link["from"], "to": link["to"], "kind": link["kind"],
            "status": link["status"],               # UNCHANGED — last-wins unaffected
            "attestation": link["attestation"],
            "ts": now,
            "_contest": {"by": by, "reason": reason, "at": now},
        }
        # the growth stamps ride the contest record too — a contest-after-growth must
        # not drop intent_id/node_id (last-wins would forget the conceptric join and
        # the mint leg would re-mint; G2b's flagged edge, carried here).
        for stamp in ("intent_id", "node_id"):
            if link.get(stamp):
                rec[stamp] = link[stamp]
        from laplace.pipeline.ledger import append_jsonl
        append_jsonl(md / _CHAIN_REL, rec)
    return 200, {"ok": True, "link_id": link_id, "status": link["status"],
                 "contested_by": by, "reason": reason,
                 "note": ("contest banked as a later record; the link's status is "
                          "unchanged until it is re-attested or re-forged")}


# ---------------------------------------------------------------------------
# the HTTP handler (GET reads + POST writes; the scanner routes /derivation/*)
# ---------------------------------------------------------------------------

def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/derivation/*`` request; ``None`` = not ours (scanner 404s)."""
    if not path.startswith("/derivation/"):
        return None
    method = (method or "GET").upper()

    def _q1(key: str, default: str = "") -> str:
        v = query.get(key)
        if isinstance(v, (list, tuple)):
            v = v[0] if v else ""
        return (v or default).strip()

    if path == "/derivation/sheet" and method == "GET":
        corpus = _q1("corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        md = _resolve_md(corpus)
        if md is None:
            return _json_resp(404, {"error": f"no manuscript dir for corpus {corpus!r}"})
        try:
            payload = read_sheet(md)
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"derivation sheet assembly failed: {e}"})
        payload = dict(payload)
        payload["corpus"] = corpus
        return _json_resp(200, payload)

    if path == "/derivation/fragment" and method == "GET":
        corpus = _q1("corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        st, obj = fragment(corpus, _q1("link"))
        return _json_resp(st, obj)

    def _post_body() -> dict | None:
        try:
            p = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return None
        return p if isinstance(p, dict) else None

    # STRICT arming (fail-closed): only the JSON literal true arms — "yes"/1/"true"
    # do NOT (the second click is the law at every write door here).
    if path == "/derivation/rescope" and method == "POST":
        p = _post_body()
        if p is None:
            return _json_resp(400, {"error": "bad json"})
        corpus = p.get("corpus") or _q1("corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        st, obj = rescope(corpus, str(p.get("by") or ""), str(p.get("claim") or ""),
                          armed=p.get("armed") is True, reason=str(p.get("reason") or ""))
        return _json_resp(st, obj)

    if path == "/derivation/forge" and method == "POST":
        p = _post_body()
        if p is None:
            return _json_resp(400, {"error": "bad json"})
        corpus = p.get("corpus") or _q1("corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        st, obj = forge(corpus, str(p.get("link_id") or ""), str(p.get("by") or ""),
                        armed=p.get("armed") is True)
        return _json_resp(st, obj)

    if path == "/derivation/contest" and method == "POST":
        p = _post_body()
        if p is None:
            return _json_resp(400, {"error": "bad json"})
        corpus = p.get("corpus") or _q1("corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        st, obj = contest(corpus, str(p.get("link_id") or ""), str(p.get("by") or ""),
                          str(p.get("reason") or ""), armed=p.get("armed") is True)
        return _json_resp(st, obj)

    return None
