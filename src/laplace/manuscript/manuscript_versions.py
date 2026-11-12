"""Manuscript version history as one join: snapshots, judge and harnessed rounds, releases and editor saves across a
project's manuscript and target roots, newest first and bounded. Moved out of the served shared_ui on 2026-10-21;
pure reads.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import time as _time

from laplace.core.checkout import repo_root as _repo_root
from laplace.core.observe import iso_utc as _iso, mtime as _mtime, relative as _rel
from laplace.pipeline.registry import MINTED_PDF_RE as _MINTED_PDF_RE


# ---- moved from laplace.web.shared_ui (2026-10-21, core native/physical closure)
_SEGMENT_RE = __import__("re").compile(r"^[A-Za-z0-9._-]+$")


_VERSIONS_MAX_BYTES = 16 * 1024


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T")


_DATE_IN_NAME_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


#: candidate_lock's SNAPSHOT.json ts form, ``2026-07-12_015849`` (see candidate_lock).
_LOCK_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})")


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _norm_ts(raw: Any) -> str | None:
    """Normalise every ts source to one comparable ``yyyy-mm-ddthh:MM:SS[Z]`` form so
    rows of different kinds sort together: ISO (finalize ``created``, state ts) rides
    as-is; candidate_lock's ``2026-07-12_015849`` and a date-in-a-name both lift to it."""
    if not raw:
        return None
    s = str(raw)
    if _ISO_RE.match(s):
        return s
    m = _LOCK_TS_RE.match(s)
    if m:
        return f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}Z"
    m = _DATE_IN_NAME_RE.search(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00Z"
    return s


def _date_ts(name: str) -> str | None:
    """A ts ONLY if a date is embedded in ``name`` — else None (so a nameless-date
    dir falls back to mtime, never sorts by its raw name string)."""
    m = _DATE_IN_NAME_RE.search(name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00Z" if m else None


def _snapshot_rows(md: Path, root: Path) -> tuple[list[dict], dict]:
    """The banked ``versions/`` snapshots. ts prefers a SNAPSHOT.json manifest (W3.2's
    writer), else a date embedded in the dir name, else the dir mtime — never fabricated."""
    vdir = md / "versions"
    present = vdir.is_dir()
    dirs = sorted((c for c in vdir.iterdir() if c.is_dir()), key=lambda d: d.name) if present else []
    rows: list[dict] = []
    for d in dirs:
        ts = None
        snap = d / "SNAPSHOT.json"
        if snap.is_file():
            man = _load_json(snap)
            if isinstance(man, dict):
                ts = man.get("ts") or man.get("created")
        ts = _norm_ts(ts) or _date_ts(d.name) or _iso(_mtime(d))
        # the OPENABLE artefacts inside the snapshot (so W2 can open a banked state,
        # not just name its dir): the frozen main.pdf/main.tex at the snapshot top or
        # one level into a whitepaper/ leg. A snapshot with none carries only its dir
        # (the rail renders that as an honest detail, never a dead viewer link).
        paths = [_rel(d, root)]
        for cand in (d / "main.pdf", d / "main.tex",
                     d / "whitepaper" / "main.pdf", d / "whitepaper" / "main.tex"):
            if cand.is_file():
                paths.append(_rel(cand, root))
        rows.append({"kind": "snapshot", "id": d.name, "ts": ts,
                     "label": d.name, "paths": paths, "state": "banked"})
    return rows, {"dir": _rel(vdir, root), "present": present,
                  "empty": present and not dirs}


def _round_ts(md: Path, n: int) -> str | None:
    for cand in (md / "rounds" / "harnessed" / f"mech_r{n}.json",
                 md / "rounds" / f"incumbent_r{n}"):
        if cand.exists():
            return _iso(_mtime(cand))
    return None


def _round_paths(md: Path, n: int, layout: str, root: Path) -> list[str]:
    """The evidence a round leaves on disk, both layouts — the mech record + the
    incumbent snapshot + the lock (harnessed), or the judge round record."""
    out: list[str] = []
    if layout == "harnessed":
        for cand in (md / "rounds" / "harnessed" / f"mech_r{n}.json",
                     md / "rounds" / f"incumbent_r{n}",
                     md / "rounds" / f"lock_r{n}.json"):
            if cand.exists():
                out.append(_rel(cand, root))
    elif layout == "judge_rounds":
        from laplace.pipeline.convergence_ledger import _round_int
        for jr in (md / "judge_rounds", md.parent / "judge_rounds"):
            if jr.is_dir():
                for f in sorted(jr.glob("*round*.json")):
                    if _round_int(f.name) == n:
                        out.append(_rel(f, root))
                break
    return out


def _round_rows(md: Path, root: Path) -> tuple[list[dict], dict]:
    """The fixedpoint rounds via the one assembler (both layouts). ``econ_only`` rounds
    ride labeled, never fabricated into a full round (the assembler's honesty carried
    through). ``state``: economics-only / locked / ``N open`` / recorded."""
    from laplace.pipeline import convergence_ledger as cl
    led = cl.assemble_ledger(str(md), root)
    layout = led.get("layout") or ""
    rows: list[dict] = []
    for r in led.get("rounds") or []:
        n = r.get("round")
        ts = _norm_ts(r.get("date")) or _round_ts(md, n)
        econ = bool(r.get("econ_only"))
        opn = r.get("open_findings")
        if econ:
            state = "economics-only"
        elif (md / "rounds" / f"lock_r{n}.json").is_file():
            state = "locked"
        elif opn is not None:
            state = f"{opn} open"
        else:
            state = "recorded"
        rows.append({"kind": "round", "id": f"r{n}", "ts": ts,
                     "label": f"round {n}" + (" (economics-only)" if econ else ""),
                     "paths": _round_paths(md, n, layout, root), "state": state})
    return rows, {"layout": layout, "present": bool(led.get("rounds"))}


def _release_rows(md: Path, root: Path) -> tuple[list[dict], dict]:
    """The release history: each ``bundle_r*.json`` (the release object proper), a
    finalize-only record when no bundle exists, and every minted named PDF at the
    manuscript top level not already bound above. ``state`` is the live release-state
    machine's ``current_state`` (the sidecar), so the row carries where the release sits."""
    reldir = md / "release"
    present = reldir.is_dir()
    rows: list[dict] = []
    state = None
    if (reldir / "state.json").is_file():
        try:
            from laplace.pipeline import release as R
            state = R.current_state(md)
        except Exception:
            state = None
    fin = _load_json(reldir / "finalize.json") if (reldir / "finalize.json").is_file() else None
    fin_title = (fin or {}).get("title") or (fin or {}).get("slug")
    seen_pdfs: set[str] = set()
    if present:
        for b in sorted(reldir.glob("bundle_r*.json")):
            man = _load_json(b) or {}
            paths = [_rel(b, root)]
            pdf = man.get("final_pdf_path")
            if pdf and (md / pdf).is_file():
                paths.append(_rel(md / pdf, root))
                seen_pdfs.add(pdf)
            rows.append({"kind": "release", "id": b.stem, "ts": _norm_ts(man.get("created")),
                         "label": fin_title or b.stem, "paths": paths,
                         "state": state or "bundled"})
    if fin and not rows:
        paths = [_rel(reldir / "finalize.json", root)]
        pdf = fin.get("pdf_path")
        if pdf and (md / pdf).is_file():
            paths.append(_rel(md / pdf, root))
            seen_pdfs.add(pdf)
        rows.append({"kind": "release", "id": fin.get("slug") or "finalize",
                     "ts": _norm_ts(fin.get("created")),
                     "label": fin.get("title") or fin.get("slug") or "finalize",
                     "paths": paths, "state": state or "finalized"})
    for pdf in sorted(md.glob("*.pdf")):
        if _MINTED_PDF_RE.match(pdf.name) and pdf.name not in seen_pdfs:
            rows.append({"kind": "release", "id": pdf.stem,
                         "ts": _norm_ts(pdf.name) or _iso(_mtime(pdf)),
                         "label": pdf.stem, "paths": [_rel(pdf, root)],
                         "state": state or "minted"})
    return rows, {"dir": _rel(reldir, root), "present": present}


def _editor_save_rows(md: Path, root: Path) -> tuple[list[dict], dict]:
    """The banked editor-saves (W8/J4) under ``<md>/editor_saves/``. Each
    ``<version_id>/`` dir carries a ``VERSION.json`` ``{ts, author, surface, file, sha}``
    (projection_viewer.bank_editor_save's writer). The row joins the one rail carrying
    BOTH the rail contract (``kind/id/ts/label/paths/state``) AND the W0.3 slot fields
    (``{ts, author, surface, version_id}``); ``paths[]`` carries the banked file so the
    row is diffable (tex on both sides) and restorable. ``info.dropped`` names how many
    saves the bounded store shed LOUDLY (read from the store index), never hidden."""
    sdir = md / "editor_saves"
    present = sdir.is_dir()
    from laplace.manuscript.projection_viewer import read_editor_save, _SEGMENT_RE, _EDITOR_SAVE_INDEX_FIELDS
    # The writer's index is occurrence authority, including same-second saves.
    # Directory spellings (-9 versus -12) and clocks cannot order occurrences.
    idx = _load_json(sdir / "index.json") if present else None
    saves = idx.get("saves") if isinstance(idx, dict) else None
    valid_index = (isinstance(saves, list) and all(isinstance(item, dict) and
                   isinstance(item.get("version_id"), str) and
                   _SEGMENT_RE.fullmatch(item['version_id']) and item['version_id'] not in {'.', '..'}
                   for item in saves) and
                   len({item["version_id"] for item in saves}) == len(saves))
    indexed = {item["version_id"]: (position, item) for position, item in enumerate(saves)} if valid_index else {}
    dirs = {c.name: c for c in sdir.iterdir() if c.is_dir()} if present else {}
    # Keep unindexed legacy/orphan metadata inspectable, with order unproved.
    names = list(reversed(list(indexed))) + sorted(set(dirs) - set(indexed), reverse=True)
    rows: list[dict] = []
    for name in names:
        d = sdir / name
        man = _load_json(d / "VERSION.json")
        position, occurrence = indexed.get(name, (None, {}))
        if not isinstance(man, dict):
            man = occurrence
        vid = man.get("version_id") or d.name
        ts = _norm_ts(man.get("ts")) or _date_ts(d.name) or _iso(_mtime(d))
        fname = man.get("file")
        paths = [_rel(d, root)]
        # A damaged manifest must not erase the indexed actor and let baseline
        # selection silently skip this recorded machine occurrence.
        author = occurrence.get("author") or man.get("author") or "author"
        surface = occurrence.get("surface") or man.get("surface") or "editor"
        try:
            observed = read_editor_save(md, str(vid), repo_root=root, read_body=False)
            source_binding = observed['source_binding'] if (
                occurrence.get('source_file') == man.get('source_file') and
                isinstance(occurrence.get('source_file'), str) and occurrence['source_file'] and
                type(occurrence.get('bytes')) is int and occurrence['bytes'] >= 0 and
                occurrence.get('bytes') == man.get('bytes')) else 'UNPROVED'
            if observed['saved_file'].is_file():
                paths.append(_rel(observed['saved_file'], root))
        except (OSError, ValueError):
            source_binding = "UNPROVED"
        order_proven = (position is not None and vid == name and all(
            key in occurrence and occurrence[key] == man.get(key)
            for key in _EDITOR_SAVE_INDEX_FIELDS))
        src = man.get("source") or "save"
        label = f"{surface} · {author}" + (" (restore)" if str(src).startswith("restore") else "")
        rows.append({"kind": "editor-save", "id": vid, "ts": ts, "label": label,
                     "paths": paths, "state": "saved", "source_file": occurrence.get("source_file"),
                     "source_binding":source_binding, "body_status":"NOT_OBSERVED",
                     "archive_order":position, "archive_order_proven":order_proven,
                     # the W0.3 slot fields, carried additively alongside the rail contract:
                     "author": author, "surface": surface, "version_id": vid, "source": src})
    dropped = (idx.get("dropped") if isinstance(idx, dict) else None) or []
    return rows, {"dir": _rel(sdir, root), "present": present,
                  "empty": present and not rows, "dropped": len(dropped)}


def _rounds_join(md: Path, td: Path, root: Path) -> tuple[list[dict], dict]:
    """The rounds across BOTH roots (the two-root repair): the judge_rounds layout
    lives under the manuscript dir, the harnessed layout under the resolved target
    dir. ``assemble_ledger`` picks ONE layout per dir, so we assemble each root and
    UNION them — for subset-sum-itqde the manuscript yields the judge rounds and the
    whitepaper yields the harnessed rounds, and both now appear (before, walking only
    the manuscript dir, the harnessed rounds were invisible). When the target IS the
    manuscript dir (most projects) the second assemble is skipped — no double count."""
    rows, info = _round_rows(md, root)
    layouts = [info["layout"]] if info["layout"] else []
    present = info["present"]
    if td is not None and td.resolve() != md.resolve():
        rows_td, info_td = _round_rows(td, root)
        rows += rows_td
        if info_td["layout"]:
            layouts.append(info_td["layout"])
        present = present or info_td["present"]
    layouts = list(dict.fromkeys(layouts))          # order-preserving de-dup
    return rows, {"layout": "+".join(layouts), "layouts": layouts, "present": present}


def _enforce_versions_budget(out: dict) -> None:
    """The byte half of the golden law, ENFORCED not asserted: shed the OLDEST rows
    (the list is newest-first) with a LOUD flag until the payload fits ≤16KB. ``counts``
    stay the plain discovered totals; ``omitted`` names what was dropped."""
    def _size(o: dict) -> int:
        return len(json.dumps(o, ensure_ascii=False).encode("utf-8"))
    while out["rows"] and _size(out) > _VERSIONS_MAX_BYTES:
        out["rows"].pop()
        out["omitted"] += 1
        out["truncated"] = True


def versions_join(md: Path, root: Path, target_dir: Path | None = None,
                  editor_store: Path | None = None) -> dict:
    """The JOIN over a project's TWO roots: snapshots + judge_rounds under the
    manuscript dir (``md``), harnessed rounds + release history under the resolved
    target dir (``target_dir``, defaulting to ``md`` when a project's target IS its
    manuscript dir). ONE ts-ordered (newest first) list. Declared empty on never-run;
    bounded to the golden law. Pure reads — the core the ``?corpus=`` endpoint wraps.

    The split is the two-root repair: for subset-sum-itqde the manuscript dir holds
    ``versions/`` + ``judge_rounds/`` while ``whitepaper/`` (the target) holds the
    harnessed rounds + the release + the minted PDFs. Walking one root missed the
    other half; walking both from the one resolved context unites them."""
    td = target_dir if target_dir is not None else md
    snaps, snap_info = _snapshot_rows(md, root)
    rounds, round_info = _rounds_join(md, td, root)
    rels, rel_info = _release_rows(td, root)
    esaves, esave_info = _editor_save_rows(editor_store or md, root)
    rows = snaps + rounds + rels + esaves
    # ts-ordered, NEWEST FIRST; a row with no derivable ts sorts to the honest tail.
    rows.sort(key=lambda r: (r.get("ts") or ""), reverse=True)
    any_source = (snap_info["present"] or round_info["present"]
                  or rel_info["present"] or esave_info["present"])
    counts = {"snapshot": len(snaps), "round": len(rounds),
              "release": len(rels), "total": len(rows)}
    # the editor-save count is ADDITIVE — present only when a project has banked one, so a
    # project without editor-saves stays byte-identical to before this kind existed.
    if esaves:
        counts["editor-save"] = len(esaves)
    out = {
        "dir": _rel(md, root),
        "rows": rows,
        "counts": counts,
        # never_run is the F10 distinction: no source EVER touched AND no rows. An
        # emptied versions dir is present-but-empty (see sources.snapshots), NOT never_run.
        "never_run": (not any_source) and (not rows),
        "sources": {"snapshots": snap_info, "rounds": round_info, "release": rel_info,
                    "editor_saves": esave_info},
        "budget": {"max_bytes": _VERSIONS_MAX_BYTES},
        "truncated": False,
        "omitted": 0,
        "generated_ts": _iso(_time.time()),
    }
    _enforce_versions_budget(out)
    return out


def versions_payload(corpus: str, repo_root: Path | None = None) -> dict | None:
    """The ``?corpus=`` join: resolve the corpus through the one server-canonical
    :func:`registry.project_context` to BOTH its roots (manuscript dir + resolved
    target dir), then join across them. ``None`` for an unknown (or path-shaped)
    corpus, or one with no manuscript dir on disk — a traversal name never reaches
    the filesystem (the registry fence)."""
    from laplace.pipeline import registry
    root = (repo_root or _repo_root()).resolve()
    ctx = registry.project_context(corpus, root)
    if ctx is None or ctx.manuscript_dir is None or not ctx.manuscript_dir.is_dir():
        return None
    result = {"corpus": corpus, **versions_join(ctx.manuscript_dir, root,
                                              target_dir=ctx.target_dir, editor_store=ctx.storage_dir)}
    from laplace.work.history import source_handle
    for row in result['rows']:
        source_file=next((path for path in row.get('paths',[]) if str(path).endswith('.tex')),None)
        if source_file and row.get('kind') in {'editor-save','snapshot'}:
            row['source_read']=source_handle(corpus,row['kind'],row['id'],source_file)
    _enforce_versions_budget(result)
    return result
