"""laplace.core.records.lineage — THE ONE WALKER over a row graph: ancestors, descendants, neighborhood.

Why (2026-08-24, the edge grammar's other half): the engine's stores have always
been a graph and never had a walker. Rows pointed at each other from the first
week — ``target``, ``supersedes``, ``consumes``, ``packet`` — but each pointer
invented its own field name, so the MEANING of every link lived in whichever
reader happened to know that store's dialect. :func:`laplace.core.records.journal.validate_edges`
gave the engine a typed way to SAY a link; this module is the only thing that
READS them, and it reads a scope's old dialects at the same time so the graph is
whole from the first call rather than whole in a year once every row is re-banked.

One read pass, both directions. Every ``*.jsonl`` in the scope's store directories
(and its named root stores) is parsed once into an id table; the forward index
(what a row points AT) and the reverse index (what points at IT) are built from
that same table, so ``descendants`` costs nothing beyond ``ancestors``. Rows with
no ``id`` are not nodes (the journal's act/step/bank ledger is act-shaped, not
row-shaped); a malformed line is skipped and counted, never fatal.

WHAT IS SHARED AND WHAT A SCOPE SAYS. The walk, the closed ``REL`` vocabulary,
declared ``edges`` claims and retrofit edge rows are this module's. Which stores
form a graph and which untyped legacy fields imply which rel is the owning
domain's: a :class:`Scope` (the engine's is ``laplace.engine.engine_ledger.ROW_GRAPH``,
which also documents its legacy map and serves the CLI).

Declared edges (``edges``, banked through ``journal.bank_row``) are CLAIMS: they
are always walked, resolved or dangling, and a dangling one shows as unresolved
rather than vanishing. Inferred legacy links are INFERENCES over untyped
free-text fields, so they are only made when the value actually resolves to a
row id this index knows. That is the whole difference in one line: a claim is
shown because someone made it; an inference is shown because it checks out.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from laplace.core import checkout
from laplace.core.records.journal import REL
from laplace.core.records.rows import read_rows

#: THE RETROFIT ROW SHAPE (2026-08-24). ``bank_row(edges=...)`` can only type the
#: links of a row being written NOW; the engine's history is append-only, so the
#: links of rows already banked have no home on those rows. An EDGE ROW is that
#: home: a first-class row carrying ``{record: "edge", from, rel, to}``, whose
#: SOURCE is the ``from`` row rather than the edge row itself. Read here on exactly
#: the same terms as a declared ``edges`` claim - always walked, resolved or
#: dangling - because it IS one, banked beside the row instead of inside it. Where
#: an edge row states THE SAME RELATION a legacy field already implies -- same
#: source, same rel, same target -- the edge row wins and the inference is
#: dropped: one claim, one display.
#:
#: The dedup is deliberately rel-level, not pair-level. Two rows can stand in two
#: relations at once and the stores say so out loud: a resolution row carrying
#: ``supersedes`` beside a retrofit ``resolves`` edge is making two true statements
#: about one pair, and collapsing them would delete the one the ROW itself made.
#: The cost is the other way round: where a retrofit edge types a pair SHARPER than
#: a generic ``evidence`` entry did (``raised-by`` beside ``grounds``), the walk
#: shows that pair twice, once sharp and once weak. Read as-is that is honest --
#: both were said -- and narrowing it is a vocabulary question (a rel precedence
#: order), not a reader bug to patch here.
EDGE_RECORD = "edge"


@dataclass(frozen=True)
class Scope:
    """Which stores form one row graph, and the legacy dialect its untyped fields speak.

    ``store_dirs``  directories under the root whose every ``*.jsonl`` is a row store
    ``root_stores``  stores at the root, named one by one (the root itself is never globbed)
    ``legacy_target_by_kind``  ``target``'s implied rel, keyed by the row's record/kind
    ``legacy_fields``  fields whose own name states the rel, on any row kind
    """
    name: str
    store_dirs: tuple[str, ...]
    root_stores: tuple[str, ...] = ()
    legacy_target_by_kind: Mapping[str, str] = field(default_factory=dict)
    legacy_fields: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for rel in (*self.legacy_target_by_kind.values(), *self.legacy_fields.values()):
            if rel not in REL:
                raise ValueError(f"scope {self.name!r}: legacy rel {rel!r} is not in the closed vocabulary")

    def where(self) -> str:
        return " or ".join(f"{d}/" for d in self.store_dirs) or "this scope"


#: fields tried, in order, for a row's one-line label.
_LABEL_FIELDS = ("title", "claim", "verdict", "text", "what", "why", "note",
                 "summary", "essence", "disposition", "status")

_MAX_TARGET_LEN = 200


def _repo_root(root: Path | str | None = None) -> Path:
    return Path(root) if root else checkout.repo_root()


def _kind(row: dict[str, Any]) -> str:
    for f in ("record", "kind", "type"):
        v = row.get(f)
        if isinstance(v, str) and v:
            return v
    return ""


def _label(row: dict[str, Any]) -> str:
    for f in _LABEL_FIELDS:
        v = row.get(f)
        if isinstance(v, str) and v.strip():
            s = " ".join(v.split())
            return s if len(s) <= 110 else s[:107] + "..."
    return ""


def _id_shaped(v: Any) -> bool:
    """Could this value be a row id at all? Prose fails on whitespace."""
    return (isinstance(v, str) and bool(v.strip()) and len(v) <= _MAX_TARGET_LEN
            and not any(c.isspace() for c in v))


def _candidates(v: Any) -> Iterable[str]:
    """A legacy field's values: a string, or a list of them. Nested junk is ignored."""
    if _id_shaped(v):
        yield v  # type: ignore[misc]
    elif isinstance(v, (list, tuple)):
        for item in v:
            if _id_shaped(item):
                yield item


class Index:
    """The one-pass row graph: id table + forward and reverse edge indexes.

    ``forward[id]``  edges this row declares/implies, source -> target.
    ``reverse[id]``  edges other rows point AT this one.
    Both hold the same edge dicts: ``{source, rel, target, target_id, via}``,
    where ``via`` is ``"edges"`` for a declared claim and ``"legacy:<field>"``
    for an inference.
    """

    def __init__(self, scope: Scope) -> None:
        self.scope = scope
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.forward: dict[str, list[dict[str, Any]]] = {}
        self.reverse: dict[str, list[dict[str, Any]]] = {}
        self.stores_read: list[str] = []
        self.rows_read = 0
        self.rows_unparseable = 0
        self.edges_declared = 0
        self.edges_legacy = 0

    # ---------------------------------------------------------------- reading

    def read(self, root: Path | str | None = None) -> "Index":
        r = _repo_root(root)
        parsed: list[dict[str, Any]] = []
        stores: list[tuple[str, Path]] = []
        for d in self.scope.store_dirs:
            base = r / d
            if base.is_dir():
                stores += [(f"{d}/{p.name}", p) for p in sorted(base.glob("*.jsonl"))]
        stores += [(name, r / name) for name in self.scope.root_stores if (r / name).is_file()]
        for rel_path, path in stores:
            self.stores_read.append(rel_path)
            rows, malformed = read_rows(path, errors="replace")
            self.rows_unparseable += malformed
            for row in rows:
                self.rows_read += 1
                rid = row.get("id")
                if not isinstance(rid, str) or not rid.strip():
                    continue              # act/step/bank ledger lines: not row-shaped
                ref = {"id": rid, "store": rel_path, "record": _kind(row),
                       "label": _label(row), "row": row}
                self.rows.setdefault(rid, []).append(ref)
                parsed.append(ref)
        # ONE insertion point, so the meters cannot drift from the index: an edge is
        # counted where it is INDEXED, never where it is read. (A meter that counts a
        # link the walk then drops is the first lie a reader believes, because it is
        # the only number on the render.)
        claimed: set[tuple[str, str, str]] = set()

        def insert(edge: dict[str, Any]) -> None:
            key = (edge["source"], edge["rel"], edge["target_id"])
            if key in claimed:
                return          # an append-only store restates a claim; the same id in
                                # two stores states it twice. One link, one display.
            claimed.add(key)
            self.forward.setdefault(edge["source"], []).append(edge)
            self.reverse.setdefault(edge["target_id"], []).append(edge)
            if edge["via"] == "edges" or edge["via"].startswith("edge-row:"):
                self.edges_declared += 1
            else:
                self.edges_legacy += 1

        # pass one: the retrofit store's edge rows. They come first so a link
        # someone stated OUT LOUD wins over the same link merely inferred below.
        edge_rows: set[int] = set()
        for ref in parsed:
            edge = self._edge_row(ref)
            if edge is None:
                continue
            edge_rows.add(id(ref))
            insert(edge)
        for ref in parsed:                # same pass over the same table: no second read
            if id(ref) in edge_rows:
                continue                  # an edge row is a link, not a node with links
            for edge in self._edges_of(ref):
                insert(edge)
        return self

    def _edge_row(self, ref: dict[str, Any]) -> dict[str, Any] | None:
        """A retrofit edge row read as the link it is: source is ``from``, not the row."""
        row = ref["row"]
        if _kind(row) != EDGE_RECORD:
            return None
        src, rel, tgt = row.get("from"), row.get("rel"), row.get("to")
        if not (_id_shaped(src) and isinstance(rel, str) and rel in REL and _id_shaped(tgt)):
            return None                   # a malformed edge row is skipped, never fatal
        source, tid = self._bare(src), self._bare(tgt)  # type: ignore[arg-type]
        if source == tid:
            return None                   # a self-link is noise
        return {"source": source, "rel": rel, "target": tgt,
                "target_id": tid, "via": f"edge-row:{ref['id']}"}

    # ---------------------------------------------------------------- edges

    def _edges_of(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        row, src = ref["row"], ref["id"]
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add(rel: str, target: str, via: str) -> None:
            tid = self._bare(target)
            key = (rel, tid)
            if tid == src or key in seen:
                return                    # a self-link is noise; a duplicate is one claim
            seen.add(key)
            out.append({"source": src, "rel": rel, "target": target,
                        "target_id": tid, "via": via})

        declared = row.get("edges")
        if isinstance(declared, list):
            for e in declared:
                if (isinstance(e, dict) and isinstance(e.get("rel"), str)
                        and e["rel"] in REL and _id_shaped(e.get("target"))):
                    add(e["rel"], e["target"], "edges")

        kind = _kind(row)
        legacy: list[tuple[str, str, Any]] = []
        by_kind = self.scope.legacy_target_by_kind
        if kind in by_kind and "target" in row:
            legacy.append(("target", by_kind[kind], row["target"]))
        for name, rel in self.scope.legacy_fields.items():
            if name in row:
                legacy.append((name, rel, row[name]))
        for name, rel, value in legacy:
            for cand in _candidates(value):
                if self._resolves(cand):   # the guard: an inference must check out
                    add(rel, cand, f"legacy:{name}")
        return out

    # ---------------------------------------------------------------- lookup

    @staticmethod
    def _bare(target: str) -> str:
        return target.partition("#")[2] if "#" in target else target

    def _resolves(self, target: str) -> bool:
        return bool(self.refs(target))

    def refs(self, target: str) -> list[dict[str, Any]]:
        """Every row matching a target, honouring a ``store.jsonl#id`` qualifier."""
        store, _, rid = target.partition("#") if "#" in target else ("", "", target)
        found = self.rows.get(rid, [])
        if store:
            found = [f for f in found if Path(f["store"]).name == Path(store).name]
        return found

    def node(self, row_id: str) -> dict[str, Any]:
        """The id's public face: where it lives, what kind it is, what it says."""
        found = self.refs(row_id)
        bare = self._bare(row_id)
        if not found:
            return {"id": bare, "found": False, "stores": [], "record": None, "label": None}
        n = {"id": bare, "found": True, "stores": [f["store"] for f in found],
             "record": found[0]["record"], "label": found[0]["label"]}
        if len(found) > 1:
            n["ambiguous"] = True         # the same id in two stores: say so, never pick silently
        return n

    # ---------------------------------------------------------------- walking

    def _walk(self, row_id: str, index: dict[str, list[dict[str, Any]]],
              key: str, depth: int | None, path: tuple[str, ...]) -> dict[str, Any]:
        # the qualifier must survive the WALK, not just the lookup: `bare` addresses the
        # indexes (which are keyed on the id alone), `row_id` addresses the ROW, and a
        # store-qualified edge that resolved to one store must not widen back to both.
        bare = self._bare(row_id)
        node = self.node(row_id)
        node["children"] = []
        if bare in path:
            node["cycle"] = True          # the store is append-only, not acyclic
            return node
        if depth is not None and depth <= 0:
            node["truncated"] = bool(index.get(bare))
            return node
        for edge in index.get(bare, []):
            child = self._walk(edge[key], index, key,
                               None if depth is None else depth - 1, path + (bare,))
            child["rel"] = edge["rel"]
            child["via"] = edge["via"]
            node["children"].append(child)
        node["children"].sort(key=lambda c: (c["rel"], c["id"]))
        return node


_CACHE: dict[tuple[str, str], Index] = {}


def index(root: Path | str | None = None, *, scope: Scope, refresh: bool = False) -> Index:
    """The read-once index for this scope and root. ``refresh=True`` re-reads from disk."""
    key = (scope.name, str(_repo_root(root)))
    if refresh or key not in _CACHE or _CACHE[key].scope != scope:
        _CACHE[key] = Index(scope).read(root)
    return _CACHE[key]


def _given(idx: Index | None, root: Path | str | None, scope: Scope | None) -> Index:
    if idx is not None:
        return idx
    if scope is None:
        raise ValueError("a walk needs its index or the scope that names its stores")
    return index(root, scope=scope)


def ancestors(row_id: str, *, depth: int | None = None, root: Path | str | None = None,
              scope: Scope | None = None, idx: Index | None = None) -> dict[str, Any]:
    """What this row stands on: follow its outgoing edges, transitively."""
    idx = _given(idx, root, scope)
    return idx._walk(row_id, idx.forward, "target", depth, ())


def descendants(row_id: str, *, depth: int | None = None, root: Path | str | None = None,
                scope: Scope | None = None, idx: Index | None = None) -> dict[str, Any]:
    """What stands on this row: follow the reverse index, transitively."""
    idx = _given(idx, root, scope)
    return idx._walk(row_id, idx.reverse, "source", depth, ())


def neighborhood(row_id: str, depth: int = 1, *, root: Path | str | None = None,
                 scope: Scope | None = None, idx: Index | None = None) -> dict[str, Any]:
    """Both directions to ``depth``, plus the row's own face and the index's meter."""
    idx = _given(idx, root, scope)
    return {
        "row": idx.node(row_id),
        "depth": depth,
        "ancestors": ancestors(row_id, depth=depth, idx=idx),
        "descendants": descendants(row_id, depth=depth, idx=idx),
        "index": {"stores": len(idx.stores_read), "rows": idx.rows_read,
                  "ids": len(idx.rows), "unparseable": idx.rows_unparseable,
                  "edges_declared": idx.edges_declared, "edges_legacy": idx.edges_legacy},
    }


# ------------------------------------------------------------------ rendering

def _render(node: dict[str, Any], out: list[str], prefix: str = "", last: bool = True,
            top: bool = True) -> None:
    if top:
        head = f"{node['id']}"
    else:
        mark = "`- " if last else "|- "
        head = f"{prefix}{mark}[{node.get('rel', '?')}] {node['id']}"
    bits = []
    if not node.get("found"):
        bits.append("UNRESOLVED")
    else:
        if node.get("record"):
            bits.append(node["record"])
        if node.get("stores"):
            bits.append(Path(node["stores"][0]).name)
        if node.get("ambiguous"):
            bits.append("AMBIGUOUS")
    if node.get("cycle"):
        bits.append("cycle")
    if node.get("truncated"):
        bits.append("...depth")
    via = node.get("via")
    if via and via != "edges":
        bits.append(via)
    out.append(head + (f"  ({', '.join(bits)})" if bits else ""))
    if node.get("label"):
        pad = prefix + ("   " if last else "|  ") if not top else "  "
        out.append(f"{pad}  {node['label']}")
    kids = node.get("children", [])
    for i, child in enumerate(kids):
        is_last = i == len(kids) - 1
        child_prefix = prefix if top else prefix + ("   " if last else "|  ")
        _render(child, out, child_prefix, is_last, top=False)


def render(neigh: dict[str, Any], *, where: str = "this scope") -> str:
    out: list[str] = []
    row = neigh["row"]
    out.append(f"ROW  {row['id']}"
               + (f"  [{', '.join(row['stores'])}]  {row['record']}" if row["found"]
                  else f"  (UNRESOLVED — no row with this id in {where})"))
    if row.get("label"):
        out.append(f"     {row['label']}")
    out.append("")
    out.append(f"ANCESTORS (what it stands on) — depth {neigh['depth']}")
    anc = neigh["ancestors"]
    if anc.get("children"):
        _render(anc, out)
    else:
        out.append("  (none)")
    out.append("")
    out.append(f"DESCENDANTS (what stands on it) — depth {neigh['depth']}")
    des = neigh["descendants"]
    if des.get("children"):
        _render(des, out)
    else:
        out.append("  (none)")
    m = neigh["index"]
    out.append("")
    out.append(f"index: {m['rows']} rows / {m['ids']} ids across {m['stores']} stores; "
               f"{m['edges_declared']} declared + {m['edges_legacy']} legacy edges; "
               f"{m['unparseable']} unparseable lines")
    return "\n".join(out)
