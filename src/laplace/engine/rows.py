"""rows.py — the front door's query layer (front door M1). No HTTP dependency.

One library, three callers (the survey's one-library law): front_door.py renders its
results as HTML fragments, ``python3 -m laplace.engine.rows`` serves the same answers at the
terminal, and any dispatched agent may import it. The UI must never hold logic the CLI
cannot reach — that is what keeps the dashboard honest with what the engine believes.

The filter grammar is the escalating single box (tiers 1–2 of the spec; tier 3's AST
expression is M4):

  tier 1   bare words            substring match over the serialized row
  tier 2   key:value  key:>N     predicates over flattened dotted paths;
           -key:value            ``-`` negates; ``*`` suffix matches prefixes;
           "quoted phrase"       quotes protect spaces; terms AND together

Malformed lines are skipped and COUNTED, never fatal — an append-only store acquires
bad lines and partial final writes, and a reader that halts on one goes dark exactly
when it is needed. Long field values are truncated two-tier: the structure survives
(``{truncated: true, bytes: N}``), the bulk is fetched on descend only.

Read-only: this module writes nothing, ever.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import shlex
from pathlib import Path
from typing import Any, Callable, Iterator

from laplace.engine import sources as _sources

#: two-tier read threshold — a scalar field longer than this is truncated in list
#: views and served whole only by /front/field (the 54 MB lesson, banked in the spec).
TRUNCATE_AT = 2048

#: hard cap on rows returned by any single scan call.
MAX_LIMIT = 500


# --------------------------------------------------------------------------- scanning

def scan(name: str, since: int = 0) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield ``(byte_offset, row)`` for every parseable line at or after ``since``.

    The offset is the line's START — stable forever in an append-only store, and the
    addressable fallback id for rows without one (catalogue s11). A partial final
    line (mid-write) is skipped silently; earlier malformed lines are skipped too and
    surfaced by :func:`scan_report`.
    """
    spec = _sources.get(name)
    if spec is None or not spec["scan"]:
        return
    try:
        fh = open(spec["abspath"], "rb")
    except OSError:
        return
    with fh:
        if since:
            try:
                size = Path(spec["abspath"]).stat().st_size
            except OSError:
                size = 0
            if since > size:   # rotation/truncation guard: restart from zero
                since = 0
            fh.seek(since)
        offset = fh.tell()
        for raw in fh:
            line_off = offset
            offset += len(raw)
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield line_off, row


def scan_report(name: str) -> dict[str, Any]:
    """Row/malformed counts for one source — the organ altitude's honesty line."""
    spec = _sources.get(name)
    if spec is None:
        return {"name": name, "error": "unknown source"}
    if not spec["scan"]:
        return {"name": name, "scanned": False}
    rows = malformed = 0
    partial_tail = False
    try:
        with open(spec["abspath"], "rb") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                parses = True
                try:
                    json.loads(raw)
                except ValueError:
                    parses = False
                if parses:
                    rows += 1
                elif raw.endswith(b"\n"):
                    malformed += 1
                else:
                    # a final line still mid-append is a moment, not a defect — it
                    # must not render a permanent-looking malformed count (the build
                    # wave's own test observation, folded in).
                    partial_tail = True
    except OSError:
        return {"name": name, "absent": True}
    return {"name": name, "rows": rows, "malformed": malformed,
            "partial_tail": partial_tail, "scanned": True}


def row_at(name: str, offset: int) -> dict[str, Any] | None:
    """The one row starting at ``offset`` — the O(1) descend seek."""
    spec = _sources.get(name)
    if spec is None:
        return None
    try:
        with open(spec["abspath"], "rb") as fh:
            fh.seek(offset)
            raw = fh.readline()
        row = json.loads(raw)
        return row if isinstance(row, dict) else None
    except (OSError, ValueError):
        return None


def find_by_field(
    name: str, field: str, value: str,
) -> tuple[int, dict[str, Any]] | None:
    """Newest row whose explicit identity field equals ``value``."""

    if not field:
        return None
    hit: tuple[int, dict[str, Any]] | None = None
    for off, row in scan(name):
        if str(row.get(field, "")) == value:
            hit = (off, row)
    return hit


def find_by_id(name: str, rid: str) -> tuple[int, dict[str, Any]] | None:
    """Newest row whose registered id field equals ``rid`` (append-only: latest wins)."""
    spec = _sources.get(name)
    if spec is None or not spec.get("id_field"):
        return None
    return find_by_field(name, str(spec["id_field"]), rid)


# --------------------------------------------------------------------------- flatten

def flatten(row: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Dotted-path projection of a nested row (``phases.metric_redistill``); lists
    stay whole (matched by substring), depth-capped so a pathological row cannot
    recurse the reader.

    A truncation marker (:func:`truncate_row`'s ``{truncated, bytes, head}``) is a
    LEAF, never a branch: exploding it into ``text.truncated``/``text.bytes`` left
    ``flat["text"]`` empty, so a large present value rendered exactly like an absent
    one — the confusion the two-tier read exists to prevent (the review's finding,
    2026-08-24).
    """
    out: dict[str, Any] = {}
    for k, v in row.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and not v.get("truncated") and prefix.count(".") < 4:
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


# --------------------------------------------------------------------------- filtering

def _term_predicate(term: str) -> Callable[[dict[str, Any], str], bool]:
    """Compile one grammar term. ``row_text`` is the serialized row (tier 1)."""
    negate = term.startswith("-") and ":" in term
    if negate:
        term = term[1:]
    if ":" in term:
        key, _, val = term.partition(":")

        def structured(row: dict[str, Any], row_text: str) -> bool:
            flat = flatten(row)
            have = flat.get(key)
            if have is None:
                ok = False
            elif val.startswith(">") or val.startswith("<"):
                try:
                    n, h = float(val[1:]), float(have)  # type: ignore[arg-type]
                    ok = h > n if val[0] == ">" else h < n
                except (TypeError, ValueError):
                    ok = False
            elif val.endswith("*"):
                ok = str(have).lower().startswith(val[:-1].lower())
            else:
                ok = val.lower() in str(have).lower()
            return not ok if negate else ok

        return structured

    def bare(row: dict[str, Any], row_text: str) -> bool:
        return term.lower() in row_text

    return bare


#: the one derived view: the account organ's OWN open work-order set. A substring
#: `status:open` matches every row that ever carried the word — 298 of them — while
#: the brief's number is the close-matched ledger (41). A number and the rows behind
#: its link must have ONE producer, so this predicate asks the account itself.
ACCOUNT_OPEN = "open:account"
ACCOUNT_OPEN_SOURCE = "work_orders"


def _account_open_ids() -> set[str]:
    from laplace.engine import wake
    root = source_tree()
    return {str(r["id"]) for r in
            (wake.account(root).get("work_orders", {}).get("open_rows") or [])
            if r.get("id")}


def _compile_for(name: str, expr: str) -> tuple[Callable[[dict[str, Any]], bool], str]:
    """``compile_filter`` plus the derived views a bare grammar cannot express. The
    special term is honoured for its OWN source only — anywhere else it stays an
    ordinary tier-2 term, so the grammar keeps one meaning per expression."""
    derived = _derived_id_set(name, (expr or "").strip())
    if derived is None:
        return compile_filter(expr)
    ids, said = derived
    id_field = (_sources.get(name) or {}).get("id_field") or "id"

    def predicate(row: dict[str, Any]) -> bool:
        return str(row.get(id_field, "")) in ids

    return predicate, f"{said} ({len(ids)} ids)"


def _derived_id_set(name: str, expr: str) -> tuple[set[str], str] | None:
    """A NUMBER AND ITS DOOR MUST COME FROM ONE PRODUCER.

    Measured on his live board: four seat tiles rendered counts from
    wake.account_seat and linked to #explore/work_orders/open:<seat>, which this grammar
    had no term for — so it fell through to the generic field predicate, looked for a
    field literally named "open", found none, and rendered "0 of 1265" WITH NO ERROR.
    Separately "5 promises" linked to status:open and landed on "37 of 346": three
    numbers for one quantity on one page.

    The cure is not more filter grammar. It is that a surface which renders a count from
    an organ links to THAT ORGAN'S OWN ID SET, never to a hand-built expression that
    guesses at how the grammar might reproduce it. ACCOUNT_OPEN already proved the shape;
    this generalises it instead of adding a second one.
    """
    from laplace.engine import wake
    root = source_tree()
    if expr == ACCOUNT_OPEN and name == ACCOUNT_OPEN_SOURCE:
        return _account_open_ids(), "the account's open set"
    if name == "promises" and expr in ("status:open", "open:account"):
        acct = wake.account(root)
        return ({str(r["id"]) for r in (acct.get("promises", {}).get("open_rows") or [])
                 if r.get("id")}, "the account's open promises")
    if name == "work_orders" and expr.startswith(("open:", "seat:")):
        seat = expr.split(":", 1)[1].strip()
        if not seat or seat == "account":
            return None
        try:
            c = wake.account_seat(seat, root)["counts"]
        except Exception:  # noqa: BLE001 - an unknown seat is not a silent empty set
            return None
        return (set((c.get("by_store") or {}).get("work_orders", {}).get("ids") or []),
                f"the open rows attributed to {seat} — {c.get('typed', 0)} by a typed "
                f"owner/owed_by field, the rest by a PROSE MATCH this engine guessed")
    return None


def compile_filter(expr: str) -> tuple[Callable[[dict[str, Any]], bool], str]:
    """Compile a tier-1/2 expression into one predicate plus the parsed-interpretation
    sentence the surface echoes under the box (the grammar is learned by using it)."""
    expr = (expr or "").strip()
    if not expr:
        return (lambda row: True), "all rows"
    try:
        terms = shlex.split(expr)
    except ValueError:
        terms = expr.split()
    preds = [_term_predicate(t) for t in terms if t]
    words = []
    for t in terms:
        if ":" in t:
            neg = t.startswith("-")
            k, _, v = (t[1:] if neg else t).partition(":")
            words.append(f"{k} {'not ' if neg else ''}matching {v}")
        else:
            words.append(f"text contains “{t}”")

    def predicate(row: dict[str, Any]) -> bool:
        row_text = json.dumps(row).lower()
        return all(p(row, row_text) for p in preds)

    return predicate, " AND ".join(words)


# --------------------------------------------------------------------------- queries

def query(name: str, expr: str = "", limit: int = 50,
          newest_first: bool = True) -> dict[str, Any]:
    """Filtered rows with offsets, truncated two-tier, newest first by default."""
    spec = _sources.get(name)
    if spec is None:
        return {"error": f"unknown source {name!r}", "rows": []}
    if not spec["scan"]:
        return {"error": f"source {name!r} is metadata-only (never scanned inline)",
                "rows": [], "source": name}
    limit = max(1, min(int(limit or 50), MAX_LIMIT))
    try:
        predicate, parsed = _compile_for(name, expr)
    except Exception as e:  # noqa: BLE001 — a derived view's organ serves its error
        return {"error": f"filter {expr!r} could not resolve: {type(e).__name__}: {e}",
                "rows": [], "source": name}
    matched: list[dict[str, Any]] = []
    total = kept = 0
    for off, row in scan(name):
        total += 1
        if not predicate(row):
            continue
        kept += 1
        matched.append({"offset": off, "row": row})
    if newest_first:
        matched.reverse()
    page = matched[:limit]
    for m in page:
        m["row"] = truncate_row(m["row"])
    return {"source": name, "path": spec["path"], "parsed": parsed,
            "total": total, "matched": kept, "shown": len(page), "rows": page,
            "columns": spec["columns"], "id_field": spec.get("id_field")}


def truncate_row(row: dict[str, Any]) -> dict[str, Any]:
    """Two-tier read: any scalar over TRUNCATE_AT survives as its structure only."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, str) and len(v) > TRUNCATE_AT:
            out[k] = {"truncated": True, "bytes": len(v), "head": v[:200]}
        elif isinstance(v, dict):
            out[k] = truncate_row(v)
        else:
            out[k] = v
    return out


def facets(name: str, expr: str = "", top: int = 8) -> dict[str, Any]:
    """Top-K value counts per registry facet field over the CURRENT filtered set —
    the clickable rail; every count is recomputed from rows at call time."""
    spec = _sources.get(name)
    if spec is None or not spec["scan"]:
        return {"facets": {}}
    try:
        predicate, _ = _compile_for(name, expr)
    except Exception as e:  # noqa: BLE001 — the rail counts the SAME set the table shows
        return {"source": name, "facets": {},
                "error": f"{type(e).__name__}: {e}"}
    counts: dict[str, dict[str, int]] = {f: {} for f in spec["facets"]}
    for _off, row in scan(name):
        if not predicate(row):
            continue
        flat = flatten(row)
        for f in spec["facets"]:
            v = flat.get(f)
            if v is None:
                continue
            key = str(v)[:60]
            counts[f][key] = counts[f].get(key, 0) + 1
    return {"source": name, "facets": {
        f: sorted(vals.items(), key=lambda kv: -kv[1])[:top]
        for f, vals in counts.items() if vals}}


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="front-door rows — the same query layer the dashboard serves")
    p.add_argument("--source", required=True, choices=sorted(_sources.SOURCES))
    p.add_argument("--where", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--format", choices=["json", "md"], default="md")
    a = p.parse_args(argv)
    res = query(a.source, a.where, a.limit)
    if a.format == "json":
        print(json.dumps(res, indent=1))
        return 0
    print(f"### {a.source} — {res.get('matched', 0)} matched of {res.get('total', 0)} "
          f"({res.get('parsed', '')})  [source: {res.get('path', '')}]")
    cols = res.get("columns") or []
    for m in res.get("rows", []):
        flat = flatten(m["row"])
        cells = [str(flat.get(c, ""))[:64] for c in cols]
        print(f"- @{m['offset']} | " + " | ".join(cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
