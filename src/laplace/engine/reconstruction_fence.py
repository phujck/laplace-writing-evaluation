"""reconstruction_fence.py — the pre-build probe: does the record already hold this?

A session that reauthors work the record already holds is a reconstruction failure, and
until now it left no trace: the miss surfaced as the author's irritation at the end,
never as a row a later run could count. This module is the advisory first stage of the
fence ratified 2026-08-12 (``WO-20260812-reconstruction-fence``). Given the intent of a
piece of work about to be authored or dispatched, it searches the banked record and
returns the rows that may already hold that work, as typed rows with refs.

Advisory means advisory. Nothing here blocks a dispatch, raises into its caller, or
changes a compiled prompt's bytes. The probe attaches its answer to the dispatch record
and, when the caller supplies a stamp, banks a row to
``corpus_friction/fence_probes.jsonl``. Promotion to a blocking gate is a separate
decision the work-order ties to a measured bar; the measurement is
:func:`false_negative_report`, which cross-references banked probes against the
work-orders the close-time landing sweep later flagged as landed.

The legs — the record this reads:

  * ``corpus_friction/work_orders.jsonl`` — every work-order row, with its note and
    resolution rows folded into the row's text, so a probe matches the discussion of an
    order as well as its original wording. Each hit carries the order's status, because
    a hit on a resolved order means the work is done and a hit on an open one means it
    is banked and waiting.
  * ``HANDOFF.md`` and ``OPEN_STACK.md`` — sliced at markdown headings. A hit's ref is
    the section slice (``HANDOFF.md#L19-L45``), which is a node form
    ``scripts/reconstruct_node.py`` resolves.
  * ``.self_graded.json`` — the graded tree, keyword sets only, sealed nodes dropped.
    Off by default: the store is large enough that loading it on every dispatch would
    cost more than the advisory answer is worth, so a caller asks for it.

Retrieval is lexical and says so. The scoring is
:mod:`laplace.engine.ruling_recall`'s — content tokens, a document-frequency ceiling for
distinctiveness, set cosine, a floor of two shared distinctive tokens — imported rather
than reauthored, since reauthoring a working retrieval is the failure class this module
exists to catch. Distinctiveness is computed per leg: each leg has its own house
vocabulary, and a token that is ubiquitous in the work-order ledger is not thereby
ubiquitous in the graded tree.

There is no semantic leg here. When the embedding model is unimportable the probe does
not quietly answer as though it had searched by meaning: every result carries
``retrieval`` and ``semantic_leg``, and :func:`render` prints both, so a null answer can
be read as "the lexical path found nothing" rather than "the record holds nothing". This
matters for the promotion bar, since a probe over a store it cannot search answers
"not done" and licenses exactly the reauthoring it exists to prevent.

No clock reads. Every timestamp enters through an explicit ``stamp``; a caller with no
stamp gets a probe result and banks nothing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

# The scoring, imported from the module that already carries it (the return leg's
# retrieval): content tokens, the distinctiveness ceiling, set cosine, the shared-token
# floor. One implementation, two stores.
from laplace.engine import engine_ledger
from laplace.engine.ruling_recall import _SCORE_FLOOR as SCORE_FLOOR
from laplace.engine.ruling_recall import _distinctive as distinctive_tokens
from laplace.engine.ruling_recall import _similarity as similarity
from laplace.engine.ruling_recall import _tokens as content_tokens

WORK_ORDERS = "corpus_friction/work_orders.jsonl"
HANDOFF = "HANDOFF.md"
OPEN_STACK = "OPEN_STACK.md"
GRADED_TREE = ".self_graded.json"
LEDGER = "corpus_friction/fence_probes.jsonl"

PROBE_SCHEMA = "fence.probe/1"
VERDICT_SCHEMA = "fence.verdict/1"
RATE_SCHEMA = "fence.rate/1"

TOOL = "reconstruction_fence"
TOOL_VERSION = "1"

#: the named heuristic, carried in every provenance block so a reader knows how the rows
#: in front of them were chosen.
HEURISTIC = "distinctive-lexical set-cosine, per leg, score-ranked"

#: the module whose absence means there is no semantic leg.
SEMANTIC_MODULE = "fastembed"

#: the legs read by default. The graded tree is opt-in (see the module docstring).
DEFAULT_LEGS = ("work_orders", "handoff", "open_stack")
ALL_LEGS = DEFAULT_LEGS + ("graded_tree",)

#: how many rows a probe returns. Bounded like every other channel: the relevant slice
#: with refs, never the ledger.
DEFAULT_CAP = 5

#: the bound on a hit's quote and on the intent recorded in a banked row.
QUOTE_CAP = 240
INTENT_CAP = 400

#: the verdicts a judgement row may carry. A hit the author later confirms was real work
#: already banked is a true catch; a hit that named something unrelated is a false alarm.
VERDICTS = ("true-catch", "false-alarm", "unclear")

_STAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$")

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*\S)\s*$")

#: parsed sources and their token indexes, keyed by path and invalidated by (mtime,
#: size). A dispatch loop compiles many items against one record; re-reading and
#: re-tokenising the ledger for each would make the advisory call cost more than the
#: answer it gives.
_CACHE: dict[str, tuple[tuple[int, int], Any]] = {}


class FenceError(Exception):
    """A refused call: a bad stamp, an unknown leg, an unknown verdict."""


# --------------------------------------------------------------------- reading
def _cached(path: Path, build, tag: str = "raw"):
    try:
        st = os.stat(path)
    except OSError:
        return build(path)
    key = (st.st_mtime_ns, st.st_size)
    slot = f"{tag}:{path}"
    hit = _CACHE.get(slot)
    if hit is not None and hit[0] == key:
        return hit[1]
    value = build(path)
    _CACHE[slot] = (key, value)
    return value


def _read_jsonl(path: Path) -> list[dict]:
    """Every parseable row of a jsonl store. A corrupt line is skipped: an append-only
    ledger with one bad write must still be readable."""
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _bounded(text: str, cap: int) -> str:
    return " ".join(str(text or "").split())[:cap]


# ----------------------------------------------------------------------- legs
def _work_order_docs(root: Path) -> list[dict[str, Any]]:
    """Every work-order as one document: its own fields plus the note and resolution
    rows that name it. Status comes from :mod:`laplace.manuscript.storyboard`, the module that owns
    the definition of an open order; when that import fails the status reads ``unknown``
    rather than being recomputed here from a second, drifting copy of the rule."""
    from laplace.manuscript import storyboard
    from laplace.pipeline.ledger import integrity_projection

    rows, diagnostics = storyboard.load_work_orders_diagnosed(root)
    if diagnostics:
        integrity = integrity_projection(diagnostics, cap=0)
        raise FenceError(
            f"{WORK_ORDERS} wounded; reconstruction would be a lower bound "
            f"({integrity['residual_count']} residual(s), "
            f"{integrity['residual_handle']})")
    orders = [r for r in rows if engine_ledger.is_work_order(r) and r.get("id")]
    attached: dict[str, list[str]] = {}
    for r in rows:
        target = str(r.get("target") or r.get("supersedes") or "")
        if not target:
            continue
        body = r.get("text") or r.get("note") or r.get("reason") or ""
        if body:
            attached.setdefault(target, []).append(str(body))

    status_of: dict[str, str] = {}
    status_source = "storyboard.open_work_orders"
    try:
        from laplace.manuscript import storyboard
        open_ids = {str(r.get("id")) for r in storyboard.open_work_orders(rows)}
        done_ids = {str(r.get("id")) for r in storyboard.consumed_work_orders(rows)}
        for o in orders:
            oid = str(o.get("id"))
            status_of[oid] = ("open" if oid in open_ids
                              else "resolved" if oid in done_ids else "retired")
    except Exception:  # noqa: BLE001 - advisory: a status the probe cannot resolve is
        status_source = "unavailable"  # reported as unknown, never guessed at locally

    docs = []
    for o in orders:
        oid = str(o.get("id"))
        text = " ".join(str(o.get(k) or "") for k in
                        ("action", "what", "why", "corpus", "requested_by"))
        text = text + " " + " ".join(attached.get(oid, []))
        docs.append({
            "leg": "work_orders",
            "id": oid,
            "ref": f"{WORK_ORDERS}#{oid}",
            "status": status_of.get(oid, "unknown"),
            "status_source": status_source,
            "title": _bounded(o.get("action") or "", 80),
            "quote": _bounded(o.get("what") or o.get("action") or "", QUOTE_CAP),
            "text": text,
            "attached_rows": len(attached.get(oid, [])),
        })
    return docs


def _markdown_docs(root: Path, rel: str, leg: str) -> list[dict[str, Any]]:
    """A markdown surface sliced at its headings. Each slice is one document; its ref is
    the line-span node form, so a hit is descended with ``reconstruct_node.py``."""
    def build(path: Path) -> list[tuple[str, int, int, str]]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return []
        lines = text.splitlines()
        marks: list[tuple[int, str]] = []
        for i, ln in enumerate(lines, start=1):
            m = _HEADING_RE.match(ln)
            if m:
                marks.append((i, m.group(1)))
        if not marks:
            return [("", 1, len(lines), "\n".join(lines))]
        slices = []
        for n, (start, title) in enumerate(marks):
            end = marks[n + 1][0] - 1 if n + 1 < len(marks) else len(lines)
            slices.append((title, start, end, "\n".join(lines[start - 1:end])))
        return slices

    out = []
    for title, start, end, body in _cached(root / rel, build):
        out.append({
            "leg": leg,
            "id": f"{rel}#L{start}-L{end}",
            "ref": f"{rel}#L{start}-L{end}",
            "status": "record",
            "status_source": "markdown slice",
            "title": _bounded(title, 80),
            "quote": _bounded(body, QUOTE_CAP),
            "text": f"{title} {body}",
            "attached_rows": 0,
        })
    return out


def _graded_tree_docs(root: Path) -> list[dict[str, Any]]:
    """The graded tree's nodes as documents: id, essence and keywords, which is what the
    lexical ring routes on. Sealed nodes are dropped whole — the seal holds by
    construction, and a sealed node answers no question about whether work was done."""
    def build(path: Path) -> list[dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(data, dict):
            return []
        docs = []
        for nid, node in data.items():
            if not isinstance(node, dict) or node.get("sealed"):
                continue
            kws = node.get("keywords") or []
            essence = node.get("essence") or ""
            docs.append({
                "leg": "graded_tree",
                "id": str(nid),
                "ref": str(nid),
                "status": f"grade {node.get('grade')}",
                "status_source": GRADED_TREE,
                "title": _bounded(str(nid), 80),
                "quote": _bounded(str(essence), QUOTE_CAP),
                "text": f"{nid} {essence} " + " ".join(str(k) for k in kws),
                "attached_rows": 0,
            })
        return docs
    return _cached(root / GRADED_TREE, build)


#: the file each leg is read from, which is also what invalidates its cached index.
_LEG_SOURCE = {"work_orders": WORK_ORDERS, "handoff": HANDOFF,
               "open_stack": OPEN_STACK, "graded_tree": GRADED_TREE}


def _leg_docs(root: Path, leg: str) -> list[dict[str, Any]]:
    if leg == "work_orders":
        return _work_order_docs(root)
    if leg == "handoff":
        return _markdown_docs(root, HANDOFF, "handoff")
    if leg == "open_stack":
        return _markdown_docs(root, OPEN_STACK, "open_stack")
    if leg == "graded_tree":
        return _graded_tree_docs(root)
    raise FenceError(f"unknown leg {leg!r}; one of {ALL_LEGS}")


def _leg_index(root: Path, leg: str):
    """A leg's documents with their token sets and its distinctive vocabulary, cached
    against the source file. Distinctiveness is per leg: a token that is house vocabulary
    in the work-order ledger is not thereby house vocabulary in the graded tree, and
    pooling the legs would let the largest one set the bar for all of them."""
    if leg not in _LEG_SOURCE:
        raise FenceError(f"unknown leg {leg!r}; one of {ALL_LEGS}")

    def build(_path: Path):
        docs = _leg_docs(root, leg)
        toksets = [content_tokens(d["text"]) for d in docs]
        return docs, toksets, distinctive_tokens(toksets)
    return _cached(root / _LEG_SOURCE[leg], build, tag="index")


# ------------------------------------------------------------------ the probe
def embedder_state() -> dict[str, Any]:
    """Whether a semantic leg could run at all. The probe reports this on every result:
    a lexical answer read as a semantic one is the failure the fence's own dependency
    flag names."""
    try:
        present = importlib.util.find_spec(SEMANTIC_MODULE) is not None
    except (ImportError, ValueError):
        present = False
    return {
        "module": SEMANTIC_MODULE,
        "present": present,
        "note": (f"{SEMANTIC_MODULE} is importable, but this probe does not use it: the "
                 "lexical path is the only one implemented here" if present else
                 f"{SEMANTIC_MODULE} is not importable in this environment, so no "
                 "semantic retrieval ran and no result here reflects one"),
    }


def probe(repo_root: Path | str, intent: str, *, cap: int = DEFAULT_CAP,
          legs: Iterable[str] | None = None) -> dict[str, Any]:
    """Search the banked record for rows that may already hold ``intent``.

    ``intent`` is whatever names the work about to be authored: a goal line, a dispatch
    target plus its goal, a work-order's own text. Returns ``{"rows", "provenance"}``.
    ``rows`` is bounded by ``cap`` and may be empty, in which case the provenance still
    states what was read, which leg it came from, and that the retrieval was lexical.

    Deterministic: no model call, no embedding, no clock, no network. The same intent
    against the same record returns the same rows.
    """
    root = Path(repo_root)
    names = tuple(legs) if legs is not None else DEFAULT_LEGS
    text = " ".join(str(intent or "").split())
    intent_tokens = content_tokens(text)

    scored: list[tuple[float, str, str, dict[str, Any], list[str]]] = []
    leg_prov: list[dict[str, Any]] = []
    for leg in names:
        docs, toksets, distinctive = _leg_index(root, leg)
        ctx = intent_tokens & distinctive
        matched = 0
        for doc, toks in zip(docs, toksets, strict=True):
            shared = sorted(ctx & toks)
            if len(shared) < SCORE_FLOOR:
                continue
            matched += 1
            scored.append((similarity(len(shared), len(ctx), len(toks)),
                           doc["leg"], doc["id"], doc, shared))
        leg_prov.append({"leg": leg, "documents": len(docs),
                         "distinctive_tokens": len(distinctive),
                         "intent_tokens_in_leg": len(ctx), "matched": matched})

    scored.sort(key=lambda s: (-round(s[0], 6), s[1], s[2]))
    rows = [{
        "leg": doc["leg"],
        "id": doc["id"],
        "ref": doc["ref"],
        "status": doc["status"],
        "title": doc["title"],
        "quote": doc["quote"],
        "score": round(sim, 4),
        "shared": shared[:8],
        "why": (f"{len(shared)} distinctive tokens shared with the intent "
                f"({doc['leg']}, status {doc['status']})"),
    } for sim, _leg, _id, doc, shared in scored[:max(0, cap)]]

    emb = embedder_state()
    provenance = {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "heuristic": HEURISTIC,
        "retrieval": "lexical",
        "semantic_leg": emb["note"],
        "embedder": emb,
        "legs": leg_prov,
        "documents": sum(p["documents"] for p in leg_prov),
        "matched": len(scored),
        "returned": len(rows),
        "cap": cap,
        "score_floor": SCORE_FLOOR,
        "intent_tokens": len(intent_tokens),
        "intent_chars": len(text),
        "legs_skipped": [leg for leg in ALL_LEGS if leg not in names],
    }
    return {"rows": rows, "provenance": provenance}


def render(result: dict[str, Any], intent: str = "") -> str:
    """A probe result as text: the rows with their refs, or the absence stated against
    what was read. The retrieval path is printed either way, so a reader can tell an
    empty record from an unsearched one."""
    p = result["provenance"]
    head = [f"reconstruction fence — {p['retrieval']} retrieval — {p['heuristic']}"]
    if intent:
        head.append(f"intent: {_bounded(intent, INTENT_CAP)}")
    head.append("semantic leg: " + p["semantic_leg"])
    head.append("legs read: " + ", ".join(
        f"{leg['leg']} ({leg['documents']} docs, {leg['matched']} matched)"
        for leg in p["legs"]))
    if p["legs_skipped"]:
        head.append("legs not read: " + ", ".join(p["legs_skipped"]))
    if not result["rows"]:
        head.append(f"no row of the {p['documents']} read shares {p['score_floor']} "
                    "distinctive tokens with this intent. The lexical path found "
                    "nothing; that is not proof the record is empty.")
        return "\n".join(head)
    head.append(f"{p['matched']} row(s) may already hold this work "
                f"(showing {p['returned']}):")
    for r in result["rows"]:
        head.append(f"  [{r['score']:.4f}] {r['id']}  ({r['leg']}, {r['status']})")
        if r["title"]:
            head.append(f"      {r['title']}")
        head.append(f"      {r['quote']}")
        head.append(f"      shared: {', '.join(r['shared'])}  ->  {r['ref']}")
    return "\n".join(head)


# ---------------------------------------------------------------- the ledger
def _check_stamp(stamp: str) -> str:
    if not stamp or not _STAMP_RE.match(str(stamp)):
        raise FenceError(f"stamp must be ISO 8601, got {stamp!r}")
    return str(stamp)


def _compact(stamp: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", stamp)


def ledger_rows(repo_root: Path | str) -> list[dict]:
    """Every row banked to the probe ledger, in file order."""
    return _read_jsonl(Path(repo_root) / LEDGER)


def _next_id(rows: list[dict], prefix: str, stamp: str) -> str:
    head = f"{prefix}-{_compact(stamp)}-"
    return f"{head}{sum(1 for r in rows if str(r.get('id', '')).startswith(head)) + 1:02d}"


def _append(repo_root: Path | str, row: dict[str, Any]) -> dict[str, Any]:
    path = Path(repo_root) / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


def bank(repo_root: Path | str, record: dict[str, Any], *, stamp: str) -> dict[str, Any]:
    """Append one probe as a typed row. The stamp is required and never read from a
    clock: a row dated by the machine's idea of now would disagree with the session that
    minted it."""
    stamp = _check_stamp(stamp)
    row = dict(record)
    row.update({
        "schema": PROBE_SCHEMA,
        "kind": "fence-probe",
        "id": _next_id(ledger_rows(repo_root), "FP", stamp),
        "stamp": stamp,
    })
    row.setdefault("verdict", "unjudged")
    return _append(repo_root, row)


def advise(repo_root: Path | str, intent: str, *, site: str, stamp: str | None = None,
           cap: int = DEFAULT_CAP, legs: Iterable[str] | None = None) -> dict[str, Any]:
    """The call at the authoring or dispatch moment: probe, and bank the result when a
    stamp is given.

    Returns the probe record whether or not it was banked, with ``banked`` naming the row
    id or stating why there is none. A caller with no stamp gets the advisory answer and
    writes nothing, which is what keeps a test run or a dry compile from filling the
    ledger with rows nobody will ever judge.

    This never raises for a caller: an unreadable record produces a record carrying
    ``error`` instead of an exception, because an advisory channel that can break its
    caller is a gate wearing the wrong name.
    """
    try:
        result = probe(repo_root, intent, cap=cap, legs=legs)
    except Exception as e:  # noqa: BLE001 - advisory: report, never propagate
        return {"schema": PROBE_SCHEMA, "kind": "fence-probe", "site": site,
                "intent": _bounded(intent, INTENT_CAP), "hits": [],
                "retrieval": "lexical", "error": f"{type(e).__name__}: {e}",
                "banked": "no row: the probe did not complete"}
    record = {
        "schema": PROBE_SCHEMA,
        "kind": "fence-probe",
        "site": site,
        "intent": _bounded(intent, INTENT_CAP),
        "retrieval": result["provenance"]["retrieval"],
        "semantic_leg": result["provenance"]["semantic_leg"],
        "hits": result["rows"],
        "provenance": result["provenance"],
        "verdict": "unjudged",
    }
    if stamp is None:
        record["banked"] = "no row: no stamp supplied, so nothing was written"
        return record
    try:
        banked = bank(repo_root, record, stamp=stamp)
    except (FenceError, OSError) as e:
        record["banked"] = f"no row: {e}"
        return record
    return banked


def judge(repo_root: Path | str, probe_id: str, verdict: str, *, by: str, stamp: str,
          hit: str = "", note: str = "") -> dict[str, Any]:
    """Bank the author's later reading of a probe row: was the hit a real catch?

    Append-only, like every other correction channel here: the probe row stays as it was
    written and the judgement travels beside it. These rows carry the precision side of
    the promotion bar, while :func:`false_negative_report` carries the recall side.
    """
    stamp = _check_stamp(stamp)
    if verdict not in VERDICTS:
        raise FenceError(f"verdict must be one of {VERDICTS}, got {verdict!r}")
    rows = ledger_rows(repo_root)
    known = {str(r.get("id")) for r in rows if r.get("schema") == PROBE_SCHEMA}
    if probe_id not in known:
        raise FenceError(f"no banked probe {probe_id!r} in {LEDGER}")
    return _append(repo_root, {
        "schema": VERDICT_SCHEMA,
        "kind": "fence-verdict",
        "id": _next_id(rows, "FV", stamp),
        "target": probe_id,
        "hit": hit,
        "verdict": verdict,
        "by": by,
        "note": _bounded(note, QUOTE_CAP),
        "stamp": stamp,
    })


# ------------------------------------------------- the promotion measurement
def false_negative_report(repo_root: Path | str, landed: Iterable[str], *,
                          stamp: str | None = None) -> dict[str, Any]:
    """The recall side of the promotion bar: of the work-orders that turned out to have
    landed, how many did a probe name at the authoring moment?

    ``landed`` is the list of work-order ids the close-time landing sweep flagged
    (``scripts/close_checklist.py``, the ``landing_sweep`` row). They are passed in
    rather than recomputed: that sweep reads the clock and the git log, and this
    measurement stays a pure function of its inputs so a bar can be re-derived from the
    ledger at any later date.

    A landed order that no banked probe ever named is a false negative — the fence was
    running and stayed silent while the work was reauthored. The rate is ``missed /
    landed``, and it is ``None`` when nothing landed, since a rate over an empty
    denominator would read as a perfect score.
    """
    rows = ledger_rows(repo_root)
    probes = [r for r in rows if r.get("schema") == PROBE_SCHEMA]
    verdicts = [r for r in rows if r.get("schema") == VERDICT_SCHEMA]
    surfaced: dict[str, list[str]] = {}
    for p in probes:
        for h in p.get("hits") or []:
            surfaced.setdefault(str(h.get("id")), []).append(str(p.get("id")))

    landed_ids = [str(x) for x in landed if str(x).strip()]
    caught = [{"id": i, "by_probes": surfaced[i]} for i in landed_ids if i in surfaced]
    missed = [i for i in landed_ids if i not in surfaced]
    rate = round(len(missed) / len(landed_ids), 4) if landed_ids else None
    counts = {v: sum(1 for r in verdicts if r.get("verdict") == v) for v in VERDICTS}
    report = {
        "schema": RATE_SCHEMA,
        "kind": "fence-rate",
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "probes_banked": len(probes),
        "probes_with_hits": sum(1 for p in probes if p.get("hits")),
        "landed": landed_ids,
        "caught": caught,
        "missed": missed,
        "false_negative_rate": rate,
        "rate_note": ("no landing-sweep catch to measure against; the rate is undefined, "
                      "not zero" if rate is None else
                      f"{len(missed)} of {len(landed_ids)} landed work-order(s) were never "
                      "named by a banked probe"),
        "judged": counts,
        "source": ("landed ids are supplied by the caller from the close-time landing "
                   "sweep (scripts/close_checklist.py, the landing_sweep row)"),
    }
    if stamp is not None:
        report["stamp"] = _check_stamp(stamp)
        report["id"] = _next_id(rows, "FR", report["stamp"])
        _append(repo_root, report)
    return report
