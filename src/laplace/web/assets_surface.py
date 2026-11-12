"""the asset surface (W7) — every derivation and every figure an ADDRESSABLE OBJECT, at ``/assets``.

The failure record's debt paid. The author asked, repeatedly, for a surface where a
derivation or a figure is an **object of work**: fine-grained assessment (find against
the *step* or the *panel*, never only the whole asset), banked edits, manifest-only
regen. It was designed 2026-07-14, parked outside the repo, and never built while waves
sealed green (``ARMING_2026-07-14 §0g P7`` + the failure record). Wave 0 shipped the
STORE (``pipeline/asset_model.py`` — ``enumerate_assets`` works today over both
conventions); this wave ships the SURFACE over it.

Pure handler module, the scanner-dispatch contract (mirrors ``artefact`` / ``desk`` /
``pipeline_surface``): the scanner owns the HTTP server and dispatches ``/assets*`` here
via :func:`handle`. This module NEVER starts a server and owns NO write machinery of its
own — the assess door banks through the one finding writer
(``manuscript_bridge.feedback_add``, the same one the artefact tray uses), and the regen
door banks a work-order through the ``storyboard.bank_work_order`` IDIOM (the same
``corpus_friction/work_orders.jsonl`` store the desk reads). The ruled default holds:
regeneration is MANIFEST-ONLY — the button says *banked*, the server spends no tokens.

The routes (GET reads + two thin POST doors):

  * ``GET  /assets``          — the surface page (``assets.html``, served here like /artefact).
  * ``GET  /assets/list``     — the two suites as strata: ``enumerate_assets`` serialised to
                                compact per-asset CARD summaries (the full detail rides
                                ``/assets/object``). Plain per project (subset-sum's
                                py-figures + WK-derivations, eigenengine's tikz + ``[]``).
  * ``GET  /assets/object``   — ONE asset (its full ``AssetObject`` + its anchors + its
                                history) + the resolved deep-links + the render availability.
  * ``GET  /assets/render``   — the rendered figure bytes (fenced: the file must be a
                                ``rendered`` sibling of some asset in the corpus).
  * ``POST /assets/assess``   — bank a finding ANCHORED to the STEP or PANEL, through the one
                                finding writer (``manuscript_bridge.feedback_add``); the asset
                                anchor rides the ``anchor.asset`` block (additive, no schema break).
  * ``POST /assets/regen``    — bank a MANIFEST-ONLY work-order (the ``bank_work_order`` idiom):
                                exactly one ``kind=work-order`` row into ``work_orders.jsonl``;
                                spawns nothing, spends no tokens.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

_HTML = Path(__file__).resolve().parent / "assets.html"
_JSON = "application/json; charset=utf-8"

#: repo-relative work-order store (the SAME file the desk reads; the bank_work_order idiom).
_WORK_ORDER_STORE = "corpus_friction/work_orders.jsonl"

#: the desk's work-orders stratum — where a banked regen order surfaces for a later session
#: to carry. The regen message's order id and the consequences zone both door here.
_DESK_ORDERS_HREF = "/desk?class=work-orders"

#: content types for a rendered figure served through /assets/render. A ``.pdf`` render is
#: served too, but the client shows it as a DOOR (not an inline <img>) — honest.
_RENDER_CTYPES = {
    ".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
    ".pdf": "application/pdf",
}
#: extensions a figure card can show INLINE as an <img>; a .pdf render can only be a door.
_IMAGE_EXTS = (".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif")

#: the asset history is bounded (Law I): a finding wall never rides this read.
_HISTORY_CAP = 40


def _repo_root() -> Path:
    from laplace.core.checkout import repo_root as rr   # the serving checkout's owner (the server module held the same object under an old name)
    return rr()


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, default)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else default
    return (v or default).strip()


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _resolve_corpus(corpus: str, root: Path) -> str:
    """The corpus a bare ``/assets`` opens on: the named one, else the active project
    (the same rule /artefact uses — never a fabricated default)."""
    if corpus:
        return corpus
    try:
        from laplace.pipeline import registry
        return registry.default_project(root)
    except Exception:  # noqa: BLE001 — a resolver hiccup degrades to no default, never a crash
        return ""


# ---------------------------------------------------------------------------
# DEEP-LINKS — the up-conjugate (design §5): the spine-location doors ride
# ``ladder``'s ONE href-composition, the SAME callables the six-rung panel and the
# desk deep-links use. Parity, not a mirror: the concept rung (a supported node →
# /conceptric) and the prose rung (a landing → /artefact at its node) are byte-
# identical to ``ladder.doors_for`` for the same target — a drift here fails the
# parity walk. Only the producer-EDIT door (a ``file=`` open, no ladder rung) stays
# local; it is a TOOLS door, not one of the four deep-link rungs.
# ---------------------------------------------------------------------------
from laplace.web import ladder as _ladder


def _conceptric_href(node: str) -> str:
    """Where a supported node argues — the ladder CONCEPT rung's door (parity)."""
    return _ladder._conceptric_door(node) if node else ""


def _artefact_href(corpus: str, node: str = "", file: str = "") -> str:
    """A deep-link into the one reader/editor. A LANDING (``node``, no file) rides the
    ladder PROSE rung's door (parity with the panel + the desk). The producer-EDIT open
    (``file=``) has no ladder rung — it composes locally (version-banking is W8, the door
    says so plainly)."""
    if file:
        href = f"/artefact?corpus={quote(corpus, safe='')}"
        href += f"&file={quote(str(file), safe='')}"
        return href
    return _ladder._artefact_door(corpus, node)


# ---------------------------------------------------------------------------
# THE CARD SUMMARY (the roster read): compact — identity + facts + counts, never the
# full step/landing bodies (those ride /assets/object). Keeps /assets/list bounded.
# ---------------------------------------------------------------------------
def _pick_render(rendered: list[str]) -> tuple[str | None, str | None]:
    """Choose the render to show in the CONTEXT zone: a raster/svg first (inline <img>),
    else a pdf (a download door), else ``(None, None)`` — declared absence (tikz-unrendered)."""
    for r in rendered:
        if r.lower().endswith(_IMAGE_EXTS):
            return r, "image"
    for r in rendered:
        if r.lower().endswith(".pdf"):
            return r, "pdf"
    return (rendered[0], "other") if rendered else (None, None)


def _card(a, corpus: str) -> dict:
    """One asset as a compact CARD summary (identity: mono id + producer chip; facts:
    inputs, nodes supported, landings). The cockpit detail rides /assets/object."""
    render, render_kind = _pick_render(a.rendered)
    return {
        "id": a.id,
        "kind": a.kind,
        "project": corpus,
        "producer": {"type": a.producer.type, "path": a.producer.path},
        "node_id": a.node_id,
        "inputs_n": len(a.inputs),
        "nodes_supported": list(a.nodes_supported)[:8],
        "nodes_n": len(a.nodes_supported),
        "landings_n": len(a.landings),
        "steps_n": len(a.steps),
        "panels_n": len(a.panels),
        "has_render": bool(a.rendered),
        "render": render,
        "render_kind": render_kind,
        "status": a.status,
        "claim": a.claim,
    }


def list_payload(corpus: str, root: Path | None = None) -> dict | None:
    """THE ROSTER read: the two suites (figures / derivations) as strata of asset CARDs,
    plain per project. ``None`` for an unknown project (no declared/derived asset roots)."""
    root = (root or _repo_root()).resolve()
    corpus = _resolve_corpus(corpus, root)
    if not corpus:
        return None
    from laplace.pipeline import asset_model as am
    roots = am.asset_roots(corpus)
    if roots is None:
        return None
    assets = am.enumerate_assets(corpus)
    figures = [_card(a, corpus) for a in assets if a.kind == "figure"]
    derivations = [_card(a, corpus) for a in assets if a.kind == "derivation"]
    n_steps = sum(c["steps_n"] for c in derivations)
    n_landings = sum(c["landings_n"] for c in figures)
    return {
        "corpus": corpus,
        "strata": [
            {"id": "figures", "label": "figures", "count": len(figures),
             "producer": roots.figure_producer,
             "note": f"{roots.figure_producer} producers · {n_landings} nodemap landing(s)"},
            {"id": "derivations", "label": "derivations", "count": len(derivations),
             "declared": bool(roots.derivations),
             "note": (f"{n_steps} step anchor(s)" if roots.derivations
                      else "no derivation walks declared — honestly empty")},
        ],
        "figures": figures,
        "derivations": derivations,
        "counts": {"figures": len(figures), "derivations": len(derivations),
                   "steps": n_steps, "landings": n_landings, "total": len(assets)},
        "nodemap": bool(roots.nodemap),
    }


# ---------------------------------------------------------------------------
# THE COMPOSED BRIEF (W-ASSETS): the resting altitude of the asset instrument in the one
# engine. Composed server-side over the SAME ``enumerate_assets`` read the roster reads —
# one truth, never a client re-derivation. It says what this project carries (the real
# counts by kind, never a hardcoded figure), which are landed in the artefact and which
# demonstrate a claim (honest words), and AT MOST ONE ask (the single most consequential
# next step). A project of 41 assets and a project of 2 figures compose through the SAME
# machinery — the brief names the enumeration, it never names a figure.
# ---------------------------------------------------------------------------
def _dir_on_disk(glob_expr: str, root: Path) -> bool:
    """Does an asset-source glob resolve to a real directory on disk? A bare dir is a
    plain ``is_dir`` check; a wildcard glob matches when ANY expansion is a directory."""
    if any(ch in glob_expr for ch in "*?["):
        return any(p.is_dir() for p in root.glob(glob_expr))
    return (root / glob_expr).is_dir()


def _empty_reason(roots, root: Path) -> tuple[str, str]:
    """Why an enumerated corpus is empty — keyed on REAL disk state, never a guess. Returns
    ``(state, figures_path)``: ``state`` is ``"built"`` when the asset SOURCE dirs already
    exist on disk (the manuscript tree is present but nothing renders/manifests yet) or
    ``"never-run"`` when none do (the manuscript pipeline has not built this corpus). The
    ``figures_path`` is the repo-relative location where its figures will surface, named in
    the brief so the empty state is instructive, not a dead end (the fallback law: absence
    stated with its reason)."""
    fig_path = roots.figures[0] if roots.figures else ""
    on_disk = any(_dir_on_disk(g, root) for g in (roots.figures + roots.derivations))
    return ("built" if on_disk else "never-run"), fig_path


def _compose_brief(corpus: str, figures: list, derivations: list, assets: list,
                   roots=None, root: Path | None = None) -> tuple[str, str]:
    """Compose the (glance, ask) for the resting brief from the enumeration — plain words,
    the real numbers, at most one ask. Every count is the enumerated truth; nothing is
    hardcoded and no unknown is fabricated. On an EMPTY corpus the glance states WHY it is
    empty and WHERE its assets will land, keyed on the real project state (never-run vs
    built-but-unmanifested) — the reason lives in the prose, not only in a tooltip."""
    total = len(assets)
    nf, nd = len(figures), len(derivations)
    landed = sum(1 for a in assets if a.landings)
    demonstrates = sum(1 for a in assets if a.demonstrates)
    # ── THE EMPTY BRIEF (fallback law): the reason + the path, in place, keyed on disk state ──
    if total == 0:
        state, fig_path = _empty_reason(roots, root or _repo_root()) if roots is not None else ("never-run", "")
        where = f", surfacing under {fig_path}" if fig_path else ""
        if state == "built":
            glance = (f"{corpus} carries no assets yet — the manuscript tree is on disk but nothing "
                      f"is manifested: no rendered figure producer or derivation walk enumerates{where}. "
                      f"Each becomes an addressable object here the moment the pipeline renders it.")
            ask = ("rebuild the manuscript pipeline so its producers render — figures and derivations "
                   "appear here the moment they do.")
        else:
            glance = (f"{corpus} carries no assets yet — the manuscript pipeline has not built this "
                      f"corpus. Every figure and derivation becomes an addressable object here once it "
                      f"has{where}.")
            ask = ("build the manuscript pipeline — figures and derivations appear here the moment it "
                   "produces them.")
        return glance, ask
    # the kinds clause — the real counts by kind (the roster is generated per enumerated asset)
    kinds = []
    if nf:
        kinds.append(f"{nf} figure" + ("" if nf == 1 else "s"))
    if nd:
        kinds.append(f"{nd} derivation" + ("" if nd == 1 else "s"))
    kinds_clause = " and ".join(kinds) if kinds else "no assets"
    head = (f"{corpus} carries {total} asset" + ("" if total == 1 else "s") +
            f" — {kinds_clause}.")
    landed_clause = (f"{landed} land in the artefact" if landed
                     else "none land in the artefact yet")
    demo_clause = (f"{demonstrates} demonstrate a claim" if demonstrates
                   else "none demonstrate a claim yet")
    glance = f"{head} {landed_clause}; {demo_clause}."
    # AT MOST ONE ask — the single most consequential pointer, honestly derived (never a wall).
    if demonstrates == 0:
        ask = ("not one asset is bound to a claim yet — open an asset to anchor a finding "
               "at its step or panel.")
    elif landed < total:
        ask = f"{total - landed} of {total} assets have no reader landing yet."
    else:
        ask = ""
    return glance, ask


def brief_payload(corpus: str, root: Path | None = None) -> dict | None:
    """THE BRIEF read: the composed resting altitude — a glance (what the project carries,
    by kind, landed + demonstrates honesty) + at most one ask, plus the per-kind counts the
    chips carry. Composed over the SAME ``enumerate_assets`` the roster reads (one truth).
    ``None`` for an unknown project (parity with :func:`list_payload`)."""
    root = (root or _repo_root()).resolve()
    corpus = _resolve_corpus(corpus, root)
    if not corpus:
        return None
    from laplace.pipeline import asset_model as am
    roots = am.asset_roots(corpus)
    if roots is None:
        return None
    assets = am.enumerate_assets(corpus)
    figures = [a for a in assets if a.kind == "figure"]
    derivations = [a for a in assets if a.kind == "derivation"]
    glance, ask = _compose_brief(corpus, figures, derivations, assets, roots=roots, root=root)
    return {
        "corpus": corpus,
        "brief": {"glance": glance, "ask": ask},
        "counts": {
            "total": len(assets),
            "figures": len(figures),
            "derivations": len(derivations),
            "landed": sum(1 for a in assets if a.landings),
            "demonstrates": sum(1 for a in assets if a.demonstrates),
            "steps": sum(len(a.steps) for a in derivations),
            "landings": sum(len(a.landings) for a in assets),
        },
        "nodemap": bool(roots.nodemap),
    }


# ---------------------------------------------------------------------------
# THE COCKPIT read: ONE asset + its anchors + its history + the resolved deep-links.
# ---------------------------------------------------------------------------
def _anchor_words(asset_kind: str, step_id: str | None, panel_id: str | None) -> str:
    """The worded anchor a finding row leads with — the panel / step it caught, or the
    whole asset. Composed once server-side; the client renders it verbatim."""
    if panel_id:
        return f"panel {panel_id}"
    if step_id:
        return f"step {step_id}"
    return "the whole figure" if asset_kind == "figure" else "the whole derivation"


def _finding_glance(asset_kind: str, kind: str, anchor_words: str, by: str) -> str:
    """One composed sentence framing a banked finding — its kind, where it lands, and who
    banked it. Minted server-side so the findings zone stays a verbatim renderer (the
    composed-prose law); the finding's own words ride the ``comment`` field beside it."""
    who = by or "an author"
    return f"a {kind} on {anchor_words}, banked by {who}"


def _asset_history(corpus: str, aid: str, akind: str, root: Path) -> list[dict]:
    """Every banked finding ANCHORED to this asset (its ``anchor.asset.asset_id``) — read
    from the SAME feedback ledger the artefact tray writes, most recent first so the just-
    banked one leads. Each row carries the worded anchor and a composed glance so the
    cockpit's FINDINGS zone renders the echo without reconstructing meaning. Declared empty
    when no ledger (the findings zone states the absence in place)."""
    from laplace.manuscript import review_surface as rs
    from laplace.manuscript import manuscript_bridge as mb
    md = rs.manuscript_dir(corpus, "")
    if md is None:
        return []
    ledger = md / "feedback" / "feedback.jsonl"
    if not ledger.is_file():
        return []
    project = rs._project_name(corpus, md)
    out: list[dict] = []
    for rec in mb.feedback_list(root, project, ledger=ledger).get("records", []):
        asset = (rec.get("anchor") or {}).get("asset") or {}
        if asset.get("asset_id") != aid:
            continue
        step_id = asset.get("step_id")
        panel_id = asset.get("panel_id")
        anchor_words = _anchor_words(akind, step_id, panel_id)
        by = rec.get("by") or ""
        kind = rec.get("kind") or "note"
        out.append({
            "id": rec.get("id"), "ts": rec.get("ts") or "",
            "date": (rec.get("ts") or "").split("T")[0],
            "kind": kind, "by": by,
            "comment": (rec.get("comment") or "")[:200],
            "step_id": step_id, "panel_id": panel_id,
            "anchor": anchor_words,
            "composed": _finding_glance(akind, kind, anchor_words, by),
            "status": rec.get("status") or "open",
        })
    # most recent first (the just-banked finding leads); bounded by the history cap.
    out.reverse()
    return out[:_HISTORY_CAP]


def _asset_orders(corpus: str, aid: str, root: Path) -> list[dict]:
    """The regen work-orders banked for THIS asset (the ``bank_work_order`` idiom rows the
    regen door writes), most recent first — so the consequences zone can list what a regen
    has already ordered, each with a door onto the desk's work-orders stratum. Declared
    empty when the store carries none for this asset."""
    from laplace.pipeline.ledger import read_jsonl
    p = (root / _WORK_ORDER_STORE)
    if not p.is_file():
        return []
    out: list[dict] = []
    for rec in read_jsonl(p):
        if rec.get("kind") != "work-order" or rec.get("action") != "regen-asset":
            continue
        if rec.get("corpus") != corpus or rec.get("asset_id") != aid:
            continue
        out.append({
            "id": rec.get("id"), "ts": rec.get("ts") or "",
            "date": (rec.get("ts") or "").split("T")[0],
            "what": rec.get("what") or "",
            "status": rec.get("status") or "open",
            "requested_by": rec.get("requested_by") or "",
        })
    out.reverse()
    return out[:_HISTORY_CAP]


def object_payload(corpus: str, aid: str, root: Path | None = None) -> dict | None:
    """ONE asset's full cockpit read: the ``AssetObject`` (steps/panels/landings), its
    render availability, its banked-finding history, and the resolved deep-links (each
    landing → the reader at its node; each supported node → the conceptric). ``None`` when
    the project or the asset id does not resolve."""
    root = (root or _repo_root()).resolve()
    corpus = _resolve_corpus(corpus, root)
    if not corpus or not aid:
        return None
    from laplace.pipeline import asset_model as am
    a = next((x for x in am.enumerate_assets(corpus) if x.id == aid), None)
    if a is None:
        return None
    render, render_kind = _pick_render(a.rendered)
    landings = [{"file": l.file, "page": l.page, "kind": l.kind, "measured": l.measured,
                 "href": _artefact_href(corpus, a.node_id or "")} for l in a.landings]
    nodes = [{"id": n, "href": _conceptric_href(n)} for n in a.nodes_supported]
    # CONSEQUENCES (zone 2): what a regen would rebuild — honest when there is no producer.
    if a.producer.type == "none":
        regen_what = "no regen model — this asset has no named producer"
    else:
        rebuilds = (", ".join(a.rendered) if a.rendered
                    else ("the compiled walk" if a.kind == "derivation" else "its render"))
        regen_what = (f"re-runs {a.producer.type} {a.producer.path} → rebuilds {rebuilds}; "
                      f"{len(a.landings)} landing(s) re-anchor")
    return {
        "corpus": corpus,
        "asset": a.to_dict(),
        "render": render, "render_kind": render_kind,
        "render_href": (f"/assets/render?corpus={quote(corpus, safe='')}"
                        f"&file={quote(render, safe='')}") if render else None,
        "landings": landings,
        "nodes": nodes,
        "edit_href": _artefact_href(corpus, file=a.producer.path or ""),
        "regen_what": regen_what,
        "regenable": a.producer.type != "none",
        "history": _asset_history(corpus, aid, a.kind, root),
        "orders": _asset_orders(corpus, aid, root),
        "orders_href": _DESK_ORDERS_HREF,
    }


# ---------------------------------------------------------------------------
# THE RENDER read: the rendered figure bytes. FENCED — the file must be a ``rendered``
# sibling of some asset in the corpus (never an arbitrary repo read).
# ---------------------------------------------------------------------------
def _render_bytes(corpus: str, file: str, root: Path) -> tuple[int, str, bytes]:
    root = (root or _repo_root()).resolve()
    corpus = _resolve_corpus(corpus, root)
    if not corpus or not file:
        return _json_resp(400, {"error": "corpus and file are required"})
    from laplace.pipeline import asset_model as am
    allowed = {r for a in am.enumerate_assets(corpus) for r in a.rendered}
    if file not in allowed:
        return _json_resp(404, {"error": "not a rendered asset of this corpus", "file": file})
    p = (root / file).resolve()
    try:
        p.relative_to(root)                       # containment fence (checked, not assumed)
    except ValueError:
        return _json_resp(403, {"error": "file escapes the repo root"})
    if not p.is_file():
        return _json_resp(404, {"error": "rendered file absent on disk", "file": file})
    ctype = _RENDER_CTYPES.get(p.suffix.lower(), "application/octet-stream")
    try:
        return 200, ctype, p.read_bytes()
    except OSError as e:
        return _json_resp(500, {"error": f"could not read the render: {e}"})


# ---------------------------------------------------------------------------
# THE ASSESS door: bank a finding ANCHORED to the STEP or PANEL, through the ONE finding
# writer. This module owns no writer — feedback_add is the same door the artefact tray uses.
# ---------------------------------------------------------------------------
def _assess(corpus: str, payload: dict, root: Path) -> tuple[int, str, bytes]:
    root = (root or _repo_root()).resolve()
    corpus = _resolve_corpus(corpus, root)
    # THE ACTOR LAW (W-HANDS): mirrors _regen below — the door never DEFAULTS the
    # writer; an unattributed assess finding is a 422, his name never a silent
    # default. (feedback_add's own by="eigen" fallback is for callers that already
    # name themselves — drain/sweep — never for an HTTP door taking live input.)
    by = (payload.get("by") or "").strip()
    if not by:
        return _json_resp(422, {"error": "by (explicit actor) is required: an assess finding "
                                "is attributed and this door defaults nowhere"})
    from laplace.manuscript import review_surface as rs
    md = rs.manuscript_dir(corpus, "")
    if md is None:
        return _json_resp(404, {"error": f"could not resolve the manuscript for {corpus!r}"})
    ledger = md / "feedback" / "feedback.jsonl"
    project = rs._project_name(corpus, md)
    # the asset anchor rides the anchor block (additive — the intake carries it verbatim).
    from laplace.manuscript import manuscript_bridge as mb
    out = mb.feedback_add(root, project, payload, ledger=ledger)
    return _json_resp(200 if "error" not in out else 400, out)


# ---------------------------------------------------------------------------
# THE REGEN door: bank a MANIFEST-ONLY work-order (the bank_work_order idiom). Exactly one
# ``kind=work-order`` row into ``work_orders.jsonl`` — spawns nothing, spends no tokens.
# THE RULED DEFAULT until he rules otherwise (design §3, the banked fork).
# ---------------------------------------------------------------------------
def bank_asset_regen(corpus: str, asset_id: str, producer: str, by: str,
                     root: Path | None = None) -> dict:
    """Bank EXACTLY ONE ``kind=work-order`` record for an asset regen and return it. The
    record shape is the storyboard ``bank_work_order`` idiom (same store, same fields), so
    it surfaces on the desk's work-orders stratum. The record IS the whole act — a later
    session runs it; the server spends no tokens."""
    from laplace.pipeline.ledger import append_jsonl
    root = (root or _repo_root()).resolve()
    rec = {
        "id": _dt.datetime.now().strftime("WO-%Y%m%d-%H%M%S-%f"),
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "record": "work-order",
        "kind": "work-order",
        "action": "regen-asset",
        "corpus": corpus,
        "asset_id": asset_id,
        "producer": producer,
        "what": f"regenerate {asset_id} from {producer or 'its producer'} (manifest-only)",
        "why": f"regen banked from the asset surface for {corpus!r}",
        "requested_by": by,
        "cost_class": "model-heavy",
        "status": "open",
    }
    # the composition layer: the same shared work-order compose helper.
    from laplace.pipeline import composed as _composed
    try:
        rec["composed"] = _composed.compose_work_order(
            wo_id=rec["id"], action="regen-asset", corpus=corpus, what=rec["what"],
            why=rec["why"], cost_class=rec["cost_class"],
            minted_by=by or "asset-surface", ts=rec["ts"])
    except ValueError:
        pass  # the fallback law
    append_jsonl(root / _WORK_ORDER_STORE, rec)
    return rec


def _regen(corpus: str, payload: dict, root: Path) -> tuple[int, str, bytes]:
    root = (root or _repo_root()).resolve()
    corpus = _resolve_corpus(corpus, root)
    by = (payload.get("by") or "").strip()
    if not by:
        return _json_resp(422, {"error": "by (explicit actor) is required: a regen banks a "
                                "work-order and this door defaults nowhere"})
    asset_id = (payload.get("asset_id") or "").strip()
    if not asset_id:
        return _json_resp(422, {"error": "asset_id is required (the asset to regenerate)"})
    rec = bank_asset_regen(corpus, asset_id, (payload.get("producer") or "").strip(), by, root)
    return _json_resp(200, {
        "ok": True, "cost_class": "model-heavy", "spawned": False, "banked": True,
        "work_order": rec,
        "note": ("banked a manifest-only work-order — the server spends no tokens; a later "
                 "session runs it (THE RULED DEFAULT, design §3)")})


# ---------------------------------------------------------------------------
# the HTTP handler (the artefact / desk dispatch contract): GET reads + two POST doors.
# ---------------------------------------------------------------------------
def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/assets*`` request. Returns (status, content_type, body) or ``None`` when
    the path is not ours (the scanner falls through). GET reads + the two thin POST doors
    (assess / regen), each dispatching to an EXISTING writer — this module mints no ledger
    of its own."""
    if path != "/assets" and not path.startswith("/assets/"):
        return None
    method = (method or "GET").upper()
    root = _repo_root()

    if path == "/assets":
        if method == "GET":
            return 200, "text/html; charset=utf-8", _HTML.read_bytes()
        return _json_resp(405, {"error": f"{method} /assets not supported"})

    if path == "/assets/brief":
        if method != "GET":
            return _json_resp(405, {"error": f"{method} not allowed — /assets/brief is GET"})
        out = brief_payload(_q1(query, "corpus"), root)
        if out is None:
            return _json_resp(404, {"error": "no asset roots for that corpus (or none active)"})
        return _json_resp(200, out)

    if path == "/assets/list":
        if method != "GET":
            return _json_resp(405, {"error": f"{method} not allowed — /assets/list is GET"})
        out = list_payload(_q1(query, "corpus"), root)
        if out is None:
            return _json_resp(404, {"error": "no asset roots for that corpus (or none active)"})
        return _json_resp(200, out)

    if path == "/assets/object":
        if method != "GET":
            return _json_resp(405, {"error": f"{method} not allowed — /assets/object is GET"})
        out = object_payload(_q1(query, "corpus"), _q1(query, "id"), root)
        if out is None:
            return _json_resp(404, {"error": "no such asset for that corpus"})
        return _json_resp(200, out)

    if path == "/assets/render":
        if method != "GET":
            return _json_resp(405, {"error": f"{method} not allowed — /assets/render is GET"})
        return _render_bytes(_q1(query, "corpus"), _q1(query, "file"), root)

    if path == "/assets/assess":
        if method != "POST":
            return _json_resp(405, {"error": f"{method} not allowed — assess is POST /assets/assess"})
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        if not isinstance(payload, dict):
            return _json_resp(400, {"error": "body must be a json object"})
        payload.setdefault("project", _q1(query, "corpus"))
        return _assess(_q1(query, "corpus"), payload, root)

    if path == "/assets/regen":
        if method != "POST":
            return _json_resp(405, {"error": f"{method} not allowed — regen is POST /assets/regen"})
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        if not isinstance(payload, dict):
            return _json_resp(400, {"error": "body must be a json object"})
        return _regen(_q1(query, "corpus"), payload, root)

    return _json_resp(404, {"error": f"no assets route {path!r}"})
