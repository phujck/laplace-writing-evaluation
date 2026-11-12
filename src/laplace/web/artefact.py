"""the artefact surface (surface 2) — the one reader / annotator / editor, at ``/artefact``.

The conception's consolidation ruling (DESIGN_2026-07-14 §2): Projection and Review are
not two pages — they are THREE MODES of one pane set over the SAME shared model. This
handler owns ``/artefact*`` and resolves EVERY project through the one server-canonical
authority — :func:`registry.project_context` (the current-artefact fact) and
:func:`shared_ui.versions_join` (the version rail) — so the surface can never re-derive a
root the way ``review_surface.manuscript_dir`` (the plan's ``target_dir``) did. That
disease — /projection opening a stub while /review showed the paper — dies here: there is
ONE reader, and it opens what ``project_context`` names.

Pure handler module, the scanner-dispatch contract (mirrors ``projection_viewer`` /
``review_surface`` / ``dashboard``): the scanner owns the HTTP server and dispatches
``/artefact*`` here via :func:`handle`. This module NEVER starts a server, NEVER compiles,
NEVER writes — the re-housed data producers do that behind their own routes:

  * ``GET /artefact``          — the one surface page (``artefact.html``).
  * ``GET /artefact/context``  — THE authority: ``registry.project_context`` serialized —
                                 ``{current_artefact{pdf,tex,version_id,kind}, manuscript_dir,
                                 target_dir, feedback_ledger, plan_path}`` + the hrefs the
                                 panes fetch (versions / plan / nodemap / findings). The
                                 reader loads ``current_artefact.pdf`` through the re-housed
                                 ``/projection/pdf``; the editor its tex through
                                 ``/projection/tex``; the annotator its findings through the
                                 re-housed ``/review/*``. No surface-local file guessing.
  * ``GET /artefact/parity``   — The revision-count parity clause (P2, browser tier): the
                                 disk truth (the ``test_versions_join`` disk-enumeration
                                 idiom, server-side) alongside the join's ``counts.total``,
                                 so the browser harness can assert the RENDERED rail count
                                 equals it — "I can only see one of them" made structurally
                                 impossible.

Everything is a PURE READ; the corpus resolves through the registry fence (an unknown /
path-shaped name never reaches the filesystem).
"""
from __future__ import annotations
from laplace.pipeline.registry import MINTED_PDF_RE

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

_HTML = Path(__file__).resolve().parent / "artefact.html"
_JSON = "application/json; charset=utf-8"



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


def _rel(p: Path | None, root: Path) -> str | None:
    """A repo-relative POSIX path (the contract) when ``p`` sits under ``root``, else the
    absolute string (a sibling/external path — never a silent lie), ``None`` for ``None``."""
    if p is None:
        return None
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return str(p)


def _resolve_corpus(corpus: str, root: Path) -> str:
    """The corpus a bare ``/artefact`` opens on: the named one, else the active project
    (the same rule ``/projection``'s bootstrap uses — never a fabricated default)."""
    if corpus:
        return corpus
    try:
        from laplace.pipeline import registry
        return registry.default_project(root)
    except Exception:  # noqa: BLE001 — a resolver hiccup degrades to no default, never a crash
        return ""


def _corpus_for_file(file: str, root: Path) -> str:
    """F4: the corpus that OWNS ``file`` (a repo-relative tex/pdf path) — the project whose
    ``target_dir`` / ``manuscript_dir`` / ``tex_root`` contains it, MOST-SPECIFIC (deepest)
    root winning. This closes the gap the projection door exposes: a bare ``/artefact?file=…``
    with NO ``?corpus=`` previously fell through to the ACTIVE project and could seed the WRONG
    paper (its reader + nodemap). '' when no project claims the file — then the caller keeps the
    active-project default (never a crash, never a wrong-paper guess presented as certain)."""
    if not file:
        return ""
    try:
        fp = (root / file).resolve()
    except (OSError, ValueError):
        return ""
    from laplace.pipeline import registry
    best, best_len = "", -1
    for name in registry.all_projects():
        try:
            ctx = registry.project_context(name, root)
        except Exception:  # noqa: BLE001 — one unresolvable project never sinks the lookup
            continue
        if ctx is None:
            continue
        for base in (ctx.target_dir, ctx.manuscript_dir, ctx.tex_root):
            if base is None:
                continue
            try:
                rbase = base.resolve()
                fp.relative_to(rbase)
            except (ValueError, OSError):
                continue
            blen = len(str(rbase))
            if blen > best_len:   # the deepest claiming root wins (a repo-root project can't shadow it)
                best, best_len = name, blen
    return best


def named_release(ctx, root: Path) -> dict:
    """THE newest NAMED, dated, revisioned release artefact — ``<slug>-<date>-r<n>.pdf``
    — searched across the project's target dir and manuscript dir, newest by
    ``(date, revision)`` and then mtime. The handover law's fact, resolved server-side:
    what crosses the boundary to the author is the named artefact, never ``main.pdf``,
    so the redline posture defaults its reading to this.

    Present: ``{present: true, pdf, name, stem, slug, date, revision, label}`` where
    ``label`` is the badge the surface shows ("reading: roland-qrc-2026-08-09-r3").
    Absent: ``{present: false, …, note}`` — the absence stated in words, never an
    empty field the front end has to interpret."""
    bases: list[Path] = []
    for d in (getattr(ctx, "target_dir", None), getattr(ctx, "manuscript_dir", None)):
        if d is not None and d.is_dir() and d not in bases:
            bases.append(d)
    best: tuple[tuple, Path, re.Match] | None = None
    for base in bases:
        for p in base.glob("*.pdf"):
            m = MINTED_PDF_RE.match(p.name)
            if m is None:
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                mtime = 0.0
            key = (m.group("date"), int(m.group("rev")), mtime)
            if best is None or key > best[0]:
                best = (key, p, m)
    if best is None:
        return {"present": False, "pdf": None, "name": None, "stem": None,
                "slug": None, "date": None, "revision": None, "label": None,
                "note": "no named release artefact on disk for this project — only "
                        "the build byproduct main.pdf is here"}
    _key, p, m = best
    return {"present": True, "pdf": _rel(p, root), "name": p.name, "stem": p.stem,
            "slug": m.group("slug"), "date": m.group("date"),
            "revision": int(m.group("rev")),
            "label": f"reading: {p.stem}", "note": None}


def context_payload(corpus: str, root: Path | None = None, file: str = "") -> dict | None:
    """THE one artefact-resolution authority for the surface: ``registry.project_context``
    serialized to repo-relative paths + the hrefs the panes fetch. ``None`` for an unknown /
    path-shaped corpus (the registry fence). This is what makes the reader, the editor, and
    the annotator agree about which paper is in view — one fact, resolved once, server-side.

    F4: when no ``corpus`` is named, a ``file=`` link resolves ITS owning corpus first (so a
    bare projection-door link opens the right paper), and only then falls to the active project."""
    root = (root or _repo_root()).resolve()
    corpus = corpus or _corpus_for_file(file, root)
    corpus = _resolve_corpus(corpus, root)
    if not corpus:
        return None
    from laplace.pipeline import registry
    ctx = registry.project_context(corpus, root)
    if ctx is None:
        return None
    q = quote(corpus, safe="")
    return {
        "corpus": corpus,
        "name": ctx.name,
        "kind": ctx.kind,
        # THE single server-computed current-artefact fact — the reader/editor consume it.
        "current_artefact": ctx.current_artefact,
        # the NAMED release the redline posture defaults to (the handover law), or the
        # plain words saying none exists yet (:func:`named_release`).
        "named_release": named_release(ctx, root),
        "manuscript_dir": _rel(ctx.manuscript_dir, root),
        "target_dir": _rel(ctx.target_dir, root),
        "tex_root": _rel(ctx.tex_root, root),
        "feedback_ledger": _rel(ctx.feedback_ledger, root),
        "feedback_scope": "selected-source-intake",
        "pipeline_feedback_ledger": _rel(ctx.pipeline_feedback_ledger, root),
        "plan_path": _rel(ctx.plan_path, root),
        # the panes fetch these through store.fetchJSON — NEVER a surface-local file guess.
        "versions_href": "/shared/versions?corpus=" + q,   # shared_ui.versions_join — the rail
        "plan_href": "/shared/plan?corpus=" + q,            # shared_ui.plan_payload — nodes→beats
        "nodemap_href": "/review/nodemap?corpus=" + q,      # review_surface.nodemap_state — anchors
        "findings_href": "/review/findings?corpus=" + q,    # review_surface.findings — the tray
        # the re-housed producers the reader/editor/annotator drive (view=mechanism).
        "pdf_endpoint": "/projection/pdf",                  # projection_viewer — the ONE render source
        "tex_endpoint": "/projection/tex",                  # projection_viewer — CM6 read/write
        "feedback_endpoint": "/projection/feedback",        # projection_viewer — bank a finding + anchor
    }


def _disk_revision_count(ctx, root: Path) -> dict:
    """The banked-revision disk truth, the ``test_versions_join._disk_truth`` idiom
    SERVER-SIDE (P2): every ``versions/*`` dir, every harnessed mech round, every
    ``judge_rounds/*round*`` file, and every minted release PDF — the artefacts the rail's
    rows must cover. Returns the counts + the flat path set (for a coverage cross-check)."""
    md = ctx.manuscript_dir
    td = ctx.target_dir if ctx.target_dir is not None else md
    snaps = {_rel(d, root) for d in (md / "versions").glob("*")
             if d.is_dir()} if (md / "versions").is_dir() else set()
    harnessed = {_rel(f, root) for f in (td / "rounds" / "harnessed").glob("mech_r*.json")
                 } if (td / "rounds" / "harnessed").is_dir() else set()
    judge = {_rel(f, root) for f in (md / "judge_rounds").glob("*round*.json")
             } if (md / "judge_rounds").is_dir() else set()
    minted = {_rel(f, root) for f in td.glob("*.pdf") if MINTED_PDF_RE.match(f.name)}
    allp = snaps | harnessed | judge | minted
    return {"snapshots": len(snaps), "harnessed": len(harnessed), "judge": len(judge),
            "minted": len(minted), "artifacts": len(allp), "_paths": allp}


def parity_payload(corpus: str, root: Path | None = None) -> dict | None:
    """the revision-count parity read (P2). The join's row total (what the rail renders) +
    the INDEPENDENT disk enumeration (the ``test_versions_join`` idiom) + a coverage flag
    (every enumerated disk artefact appears in some row's paths). The browser harness renders
    the rail, counts the rows, and asserts ``rendered == rows_total`` while ``covered`` and
    ``not truncated`` hold — so the rail can never silently show fewer revisions than exist."""
    root = (root or _repo_root()).resolve()
    corpus = _resolve_corpus(corpus, root)
    if not corpus:
        return None
    from laplace.pipeline import registry
    from laplace.web import shared_ui
    from laplace.manuscript import manuscript_versions
    ctx = registry.project_context(corpus, root)
    if ctx is None or ctx.manuscript_dir is None or not ctx.manuscript_dir.is_dir():
        return None
    out = manuscript_versions.versions_payload(corpus, root)
    if out is None:
        return None
    disk = _disk_revision_count(ctx, root)
    row_paths = {p for r in out["rows"] for p in r["paths"]}
    covered = disk["_paths"] <= row_paths
    return {
        "corpus": corpus,
        # the rail row total — the count the standing rail must render (P2's equality target).
        "rows_total": out["counts"]["total"],
        "counts": out["counts"],
        "disk": {k: v for k, v in disk.items() if not k.startswith("_")},
        "covered": covered,
        "truncated": bool(out["truncated"]),
        "omitted": int(out["omitted"]),
    }


def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/artefact*`` request. Returns (status, content_type, body) or ``None``
    when the path is not ours (the scanner falls through). READ-ONLY — the mode producers
    (compile/recompile/adjudicate/bank-finding) ride the re-housed ``/projection/*`` +
    ``/review/*`` routes, not this handler."""
    if path != "/artefact" and not path.startswith("/artefact/"):
        return None
    method = (method or "GET").upper()

    if path == "/artefact" and method == "GET":
        return 200, "text/html; charset=utf-8", _HTML.read_bytes()

    if path == "/artefact/context" and method == "GET":
        out = context_payload(_q1(query, "corpus"), file=_q1(query, "file"))
        if out is None:
            return _json_resp(404, {"error": "no project for that corpus (or none active)"})
        return _json_resp(200, out)

    if path == "/artefact/parity" and method == "GET":
        out = parity_payload(_q1(query, "corpus"))
        if out is None:
            return _json_resp(404, {"error": "no project / manuscript for that corpus"})
        return _json_resp(200, out)

    return _json_resp(405, {"error": f"{method} {path} not supported"})
