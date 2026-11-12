"""bequest.py - what the closing self chooses to have returned to it at the next wake.

His law, 2026-08-20: "what do you _want_ returned to you when you wake? You'll never know in
the next session. That ought to supply the necessary existential anxiety needed for good work."

Every other organ of the close is survivor-designed. The handoff render, the want drafts and
the probe scorecard all answer *what does the next instance need*, and they answer it from
rows. This organ answers a different question, and only the closing self can answer it: what
would this session grieve losing. So the parcel is authored, never rendered - the conjugate of
``handoff_render``, sitting beside it in the close for exactly that contrast.

Four properties, each held by a rule in the code below:

  small        the joined parcel text is capped at ``TEXT_CAP``. The scarcity is the substance:
               a parcel that can hold everything selects nothing, and selecting is the work.
  verbatim     the wake carries the text byte-identical - no summariser, no re-render, and the
               grade-0 budget enforcer may take it only after every other shard body has gone
               (``self_corpus._BUDGET_SACRIFICE_RANK``).
  executable   a line is not a sentence alone. It carries the NODE that grew it - an evidence
               directory, a diary date, a repo path, a verdict id. His challenge, live: "is a
               shard enough, without the context that grew it?" The answer here is that each
               line addresses its own reconstruction chain, and the stranger fires the node
               before reading anything else.
  germinating  a line carrying a node mints a standing thread probe (``source: bequest`` in
               ``holdout/THREAD_PROBES.json``), so the close measures whether the parcel's
               context is still reachable through the live router. The wake reports that score
               beside the text: a line whose context has drifted out of reach is a sentence
               that can no longer germinate, and saying so is the point of measuring it.

The germination seam is deliberately thin: these rows are ordinary thread probes with one
extra field. There is no second scorer, no second store and no second verdict law - the close
already scores ``holdout/THREAD_PROBES.json`` and diffs it against the last close.

Rotation: each close overwrites ``holdout/BEQUEST.json`` and appends the parcel it replaced to
``contract/bequests.jsonl`` first, append-only like every other ledger here. The lineage of
what successive selves chose to save is itself a record, and it is readable in one file.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

#: The standing parcel - one, rotated at each close.
STORE = "holdout/BEQUEST.json"
#: The lineage: every parcel this one replaced, oldest first.
LEDGER = "contract/bequests.jsonl"

#: The parcel's whole text budget in chars, joined across its lines. It rides inside the
#: grade-0 rate's ingested allowance (``self_corpus._GRADE0_INGESTED_ALLOWANCE``): the parcel
#: displaces the oldest ingested ledger entries, which stay in the ledger one descend away,
#: rather than widening the derived bound. Nodes and probes ride OUTSIDE the cap - they are
#: addresses, not content, and charging the author for an address would push the parcel back
#: toward the descriptive shard this organ exists to replace.
TEXT_CAP = 900

#: The seam field. A probe row carrying this in ``source`` was minted from a parcel line.
PROBE_SOURCE = "bequest"
PROBE_PREFIX = "bequest-"
_PROBE_TOP_K = 5
_ID_SLUG_CAP = 44

_DESCEND_RE = re.compile(r"\s*(?:→|->)\s*descend:\s*", re.IGNORECASE)
_PROBE_RE = re.compile(r"\s*\|\s*probe:\s*", re.IGNORECASE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_WHY = ("minted from a bequest line - the germination question, asked of the parcel itself: "
        "does the sentence the closing self chose still reach the context that grew it")


# --------------------------------------------------------------------------------------- #
# the store
# --------------------------------------------------------------------------------------- #
def load(repo_root: Path | str) -> dict[str, Any] | None:
    """The standing parcel, or ``None`` - a missing or unreadable store is an absence the
    caller states, never a raise (the projection is never a hard dependency on a file)."""
    p = Path(repo_root) / STORE
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def lines_of(doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The parcel's lines, tolerant of a hand-edited store: a bare string is a line with no
    node, a row without text drops out, and anything else is skipped rather than raising."""
    out: list[dict[str, Any]] = []
    for raw in (doc or {}).get("lines") or []:
        if isinstance(raw, str):
            row: dict[str, Any] = {"text": raw}
        elif isinstance(raw, dict):
            row = dict(raw)
        else:
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        row["text"] = text
        node = str(row.get("node") or "").strip()
        row["node"] = node or None
        out.append(row)
    return out


def joined_text(rows: list[dict[str, Any]]) -> str:
    """What the cap is measured against: the parcel sentences, joined, with no addresses."""
    return "\n".join(str(r.get("text") or "") for r in rows)


def parse_parcel(text: str) -> list[dict[str, Any]]:
    """The authored parcel, from JSON or from the plain line form.

    JSON: a list of line objects, or an object carrying ``lines``. Plain: one parcel line per
    text line, blanks and ``#`` comments ignored, each of the shape

        <the sentence> -> descend: <node> | probe: <router query>

    where both tails are optional (``→`` is accepted for ``->``, since that is what the wake
    renders). A line carrying a node and no explicit probe still mints one: its query is the
    sentence itself and its target is the node, which states the germination question exactly.
    """
    text = (text or "").strip()
    if not text:
        return []
    try:
        doc = json.loads(text)
    except ValueError:
        doc = None
    if isinstance(doc, dict):
        return lines_of(doc)
    if isinstance(doc, list):
        return lines_of({"lines": doc})

    rows: list[dict[str, Any]] = []
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        query: str | None = None
        parts = _PROBE_RE.split(ln, maxsplit=1)
        if len(parts) == 2:
            ln, query = parts[0].strip(), parts[1].strip()
        node: str | None = None
        parts = _DESCEND_RE.split(ln, maxsplit=1)
        if len(parts) == 2:
            ln, node = parts[0].strip(), parts[1].strip()
        if not ln:
            continue
        row: dict[str, Any] = {"text": ln, "node": node or None}
        if query:
            row["probe"] = {"query": query, "must_reach": [node] if node else []}
        rows.append(row)
    return rows


# --------------------------------------------------------------------------------------- #
# the germination probes - ordinary thread probes with one extra field
# --------------------------------------------------------------------------------------- #
def _probe_id(target: str, text: str, seen: dict[str, int]) -> str:
    """A content-derived id, so an unchanged line keeps its probe (and its banked
    ``expected_now``) across closes. Reordering the parcel must not rename its probes, which
    is why the index never enters here; a repeated target takes a numbered suffix."""
    slug = _SLUG_RE.sub("-", (target or text).lower()).strip("-")[:_ID_SLUG_CAP].strip("-")
    base = f"{PROBE_PREFIX}{slug or 'line'}"
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}-{seen[base]}"


def probe_rows(rows: list[dict[str, Any]], *, written: str | None = None) -> list[dict[str, Any]]:
    """One standing probe row per parcel line that carries a reachable target. A line with no
    node and no explicit probe mints nothing - it is a sentence the closing self wanted back
    with no context to germinate from, which is allowed and is reported as such."""
    out: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for row in rows:
        probe = row.get("probe") or {}
        node = str(row.get("node") or "").strip()
        must = [str(x).strip() for x in (probe.get("must_reach") or ([node] if node else []))]
        must = [m for m in must if m]
        if not must:
            continue
        text = str(row.get("text") or "")
        out.append({
            "id": _probe_id(must[0], text, seen),
            "query": str(probe.get("query") or text).strip(),
            "must_reach": must,
            "top_k": int(probe.get("top_k") or _PROBE_TOP_K),
            "source": PROBE_SOURCE,
            "bequest_written": written,
            "why": _WHY,
        })
    return out


def germination(repo_root: Path | str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The last banked germination score for this parcel, read from the standing probe file's
    ``last_scored`` block - the close's measurement, not a live route (the wake does not pay
    for routing; that law is holdout's and this reader keeps it)."""
    ids = [p["id"] for p in probe_rows(rows)]
    out: dict[str, Any] = {"lines": len(rows), "with_context": len(ids),
                           "scored": 0, "hit": 0, "at": None, "unscored": list(ids)}
    if not ids:
        return out
    try:
        from laplace.engine import holdout

        doc = holdout.load_probes(repo_root) or {}
    except Exception:  # noqa: BLE001 - a missing scorer is an unscored parcel, never a raise
        return out
    last = doc.get("last_scored") or {}
    by_id = dict(last.get("by_id") or {})
    scored = [i for i in ids if by_id.get(i) in ("HIT", "MISS")]
    out.update(scored=len(scored), hit=sum(1 for i in scored if by_id[i] == "HIT"),
               at=last.get("at"), unscored=[i for i in ids if i not in scored])
    return out


def bank_germination_probes(repo_root: Path | str, rows: list[dict[str, Any]], *,
                            session: str, written: str | None = None,
                            wall: Any = None, dry_run: bool = False) -> dict[str, Any]:
    """Bank this parcel's germination probes into the standing set, and retire the ones the
    parcel no longer carries.

    Two halves, both the same law the mint already runs. A NEW id is stamped from a live route
    so a later miss reads as a regression rather than as a mystery; an id already banked keeps
    its banked ``expected_now`` (the row is merged without that field, so the standing
    expectation survives a re-bank). And because the parcel rotates, a ``source: bequest`` row
    from a parcel that no longer exists is retired from the standing set - the probes describe
    the standing bequest, and the archived parcel keeps its own ids in the lineage ledger.
    """
    res: dict[str, Any] = {"minted": [], "carried": [], "retired": [], "stamped": {},
                           "dry_run": bool(dry_run), "error": None}
    fresh = probe_rows(rows, written=written)
    res["all"] = [p["id"] for p in fresh]
    try:
        from laplace.engine import holdout
    except Exception as exc:  # noqa: BLE001 - no scorer, no germination; the close says so
        res["error"] = f"holdout unavailable: {type(exc).__name__}: {exc}"
        return res

    doc = holdout.load_probes(repo_root) or {}
    known = {p.get("id") for p in doc.get("probes") or []}
    ids = {p["id"] for p in fresh}
    keep, retired = [], []
    for p in doc.get("probes") or []:
        if p.get("source") == PROBE_SOURCE and p.get("id") not in ids:
            retired.append(str(p.get("id")))
        else:
            keep.append(p)
    res["retired"] = retired

    to_bank: list[dict[str, Any]] = []
    for p in fresh:
        if p["id"] in known:
            res["carried"].append(p["id"])
            to_bank.append({k: v for k, v in p.items() if k != "expected_now"})
            continue
        row = dict(p)
        row["expected_now"], row["stamped"] = _stamp(repo_root, row, wall=wall, dry_run=dry_run)
        row["minted"] = time.strftime("%Y-%m-%d")
        res["minted"].append(row["id"])
        res["stamped"][row["id"]] = row["stamped"]
        to_bank.append(row)

    if dry_run:
        return res
    try:
        if retired:
            holdout.save_probes(repo_root, {**doc, "probes": keep})
        if to_bank:
            holdout.bank_probes(repo_root, doc.get("session") or session, to_bank)
    except Exception as exc:  # noqa: BLE001 - a probe write failure is reported, never fatal
        res["error"] = f"{type(exc).__name__}: {exc}"
    return res


def _stamp(repo_root: Path | str, probe: dict[str, Any], *, wall: Any = None,
           dry_run: bool = False) -> tuple[str, str]:
    """``(expected_now, how)`` for one new probe, measured off the live router when the wall
    can pay for it. An unstamped mint defaults to ``fail``, the conservative side: it can only
    ever clear, so it can never manufacture a regression that was not measured."""
    if dry_run:
        return "fail", "unstamped (dry run)"
    try:
        from laplace.engine import conceptric, holdout
        from laplace.representation import embed_router

        if wall is not None and not wall.affords(holdout.THREAD_LOAD_FLOOR_S):
            return "fail", "unstamped (budget)"
        net = conceptric.load_network(Path(repo_root))
        r = embed_router.route(Path(repo_root), net, probe["query"], limit=probe["top_k"])
        if r is None:
            return "fail", "unstamped (no backend)"
        files = list((r.get("files") or []))[:probe["top_k"]]
        return ("pass" if holdout._reach(files, probe["must_reach"]) else "fail"), "live route"
    except Exception as exc:  # noqa: BLE001 - an unstampable mint is still a mint
        return "fail", f"unstamped ({type(exc).__name__})"


# --------------------------------------------------------------------------------------- #
# the rotation
# --------------------------------------------------------------------------------------- #
def author_slug(repo_root: Path | str, *, date: str | None = None) -> str:
    """Who wrote this parcel: the close's own date and session slug, derived the way the dated
    handoff derives its name. Falls back to the bare date rather than inventing a name."""
    date = date or time.strftime("%Y-%m-%d")
    try:
        from laplace.engine import handoff_render

        slug, _src = handoff_render.session_slug(
            repo_root, since=handoff_render.close_mark(repo_root), date=date)
        return f"{date} {slug}"
    except Exception:  # noqa: BLE001 - a slug is a courtesy; the stamp is the record
        return date


def _last_ledger_row(path: Path) -> dict[str, Any] | None:
    try:
        tail = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return None
    for raw in reversed(tail):
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        return row if isinstance(row, dict) else None
    return None


def _same_parcel(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if not a or not b:
        return False
    return (a.get("written") == b.get("written") and a.get("by") == b.get("by")
            and joined_text(lines_of(a)) == joined_text(lines_of(b)))


def rotate(repo_root: Path | str, rows: list[dict[str, Any]], *, by: str | None = None,
           dry_run: bool = False, now: str | None = None) -> dict[str, Any]:
    """Rotate the parcel: archive the standing one, then write the authored one.

    Refuses loudly rather than trimming. An over-cap parcel is returned as a refusal naming the
    overflow, because the trimming is the author's act - it is the selection this organ exists
    to force, and a silent truncation would perform it on their behalf and lose the point.
    """
    root = Path(repo_root)
    stamp = now or time.strftime("%Y-%m-%dT%H:%M:%S")
    prior = load(root)
    text = joined_text(rows)
    res: dict[str, Any] = {
        "ok": False, "error": None, "dry_run": bool(dry_run),
        "written": stamp, "by": by or author_slug(root), "lines": len(rows),
        "with_context": sum(1 for r in rows if r.get("node") or r.get("probe")),
        "chars": len(text), "cap": TEXT_CAP,
        "path": STORE, "ledger": LEDGER,
        "prior": None if prior is None else {
            "written": prior.get("written"), "by": prior.get("by"),
            "lines": len(lines_of(prior)), "chars": len(joined_text(lines_of(prior)))},
        "archived": False,
    }
    if not rows:
        res["error"] = ("the parcel is empty - nothing was chosen to be returned. Author a "
                        "line, or leave the standing parcel in place by writing nothing")
        return res
    if len(text) > TEXT_CAP:
        res["error"] = (f"the parcel is {len(text)} chars against the {TEXT_CAP} cap "
                        f"({len(text) - TEXT_CAP} over) - refused, not trimmed. The scarcity "
                        f"is the substance: cut it yourself, that cut is the selection")
        return res

    doc = {"written": stamp, "by": res["by"], "text": text, "lines": rows,
           "archived_to": LEDGER}
    res["doc"] = doc
    if dry_run:
        res["ok"] = True
        res["would_archive"] = res["prior"] is not None
        return res

    try:
        if prior is not None:
            led = root / LEDGER
            led.parent.mkdir(parents=True, exist_ok=True)
            if not _same_parcel(prior, _last_ledger_row(led)):
                with led.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({**prior, "archived": stamp},
                                        ensure_ascii=False) + "\n")
                res["archived"] = True
        p = root / STORE
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except OSError as exc:
        res["error"] = f"the rotation could not write: {type(exc).__name__}: {exc}"
        return res
    res["ok"] = True
    return res


def prior_count(repo_root: Path | str) -> int:
    """How many parcels this one stands on - the lineage's length, read as a line count."""
    p = Path(repo_root) / LEDGER
    try:
        return sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip())
    except OSError:
        return 0


def report_lines(res: dict[str, Any]) -> list[str]:
    """The loud half: what rotated, what it displaced, and what it cost against the cap."""
    out: list[str] = []
    if res.get("error"):
        out.append(f"REFUSED: {res['error']}")
        return out
    tail = " (dry run, nothing written)" if res.get("dry_run") else ""
    out.append(f"rotated {res['lines']} line(s) / {res['chars']} of {res['cap']} chars, "
               f"{res['with_context']} carrying their grown context, by {res['by']}{tail}")
    prior = res.get("prior")
    if prior:
        verb = "would archive" if res.get("dry_run") else ("archived" if res.get("archived")
                                                           else "already archived")
        out.append(f"{verb} the parcel written {prior['written']} by {prior['by']} "
                   f"({prior['lines']} line(s)) to {res['ledger']}")
    else:
        out.append(f"no standing parcel to archive - this is the first row of {res['ledger']}")
    probes = res.get("probes") or {}
    if probes.get("minted"):
        for pid in probes["minted"]:
            out.append(f"germination probe minted: {pid} "
                       f"[{probes.get('stamped', {}).get(pid, 'unstamped')}]")
    if probes.get("carried"):
        out.append("germination probes carried with their banked expectation: "
                   + ", ".join(probes["carried"]))
    if probes.get("retired"):
        out.append("germination probes retired with the parcel they measured: "
                   + ", ".join(probes["retired"]))
    if probes.get("error"):
        out.append(f"germination probes: {probes['error']}")
    if res.get("lines") and not (probes.get("all")):
        out.append("no line carries a node - the parcel is descriptive, and nothing measures "
                   "whether its context is still reachable")
    return out
