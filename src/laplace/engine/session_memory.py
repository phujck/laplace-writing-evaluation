"""Resolve session memory from revisions in the existing ruling ledger.

The records hold content; provider files are views. Reads do not write, spawn a
model, acquire session custody, or infer that old observations are current facts.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree, state_root

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import sqlite3
from datetime import datetime, timezone
from typing import Any

STORE = "proxy_verdicts.jsonl"
SCHEMA = "laplace.session-memory/1"
KINDS = {"law", "preference", "procedure", "historical"}
AUTHOR_KINDS = {"author-law", "author-ruling", "author-instruction", "author-steer", "his-steer-verbatim"}

# THE PROGRAMME COORDINATE (Eigen continuity, Root e716/e2f6, A_bridges_kernel). One explicitly authored, stable
# procedure record may carry an optional typed ``programme`` field naming WHICH canonical Work is the current programme.
# It is selection only: exactly {kind, namespace, work_id}. Goal, lifecycle, review, account, actor and next action stay
# with the Work/Source/Writing owners and are read fresh through the delegated canonical-work descent; nothing here caches
# them, and the record grants no Scope, capability or Source authority. Bare Work ids are never promoted into kernel nodes.
PROGRAMME_KEY = "procedure/eigen-programme"
PROGRAMME_KIND = "canonical-work"
PROGRAMME_FIELDS = ("kind", "namespace", "work_id")
PROGRAMME_SCHEMA = "laplace.session-memory-programme/1"
WORK_SCHEME = "work://"
_PROGRAMME_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}")
PROGRAMME_AUTHORITY = ("Selection only: this authored procedure names which canonical Work is the current programme. The Work owner "
                       "holds its goal, lifecycle, review and next action; the actual caller Scope is admitted before any Work "
                       "lookup, and person/engine context never grants authority.")


def validate_programme(value: Any) -> dict:
    """The closed typed coordinate: exactly {kind: canonical-work, namespace, work_id}; no mutable Work state."""
    if not isinstance(value, dict) or set(value) != set(PROGRAMME_FIELDS):
        raise ValueError("a programme coordinate is exactly {kind, namespace, work_id}: it selects canonical Work and "
                         "carries no status, account, actor, grant or next action")
    if value["kind"] != PROGRAMME_KIND:
        raise ValueError("a programme coordinate has kind canonical-work")
    for field in ("namespace", "work_id"):
        if not isinstance(value[field], str) or not _PROGRAMME_IDENT.fullmatch(value[field]):
            raise ValueError(f"programme {field} is an exact identifier of 1-160 characters [A-Za-z0-9._-]")
    return {"kind": PROGRAMME_KIND, "namespace": value["namespace"], "work_id": value["work_id"]}


def programme_uri(value: dict) -> str:
    """The namespace-qualified typed descent reference of one coordinate."""
    ref = validate_programme(value)
    return f"{WORK_SCHEME}{ref['namespace']}/{ref['work_id']}"


def parse_work_uri(reference: Any) -> dict:
    """``work://<namespace>/<work_id>`` to its coordinate; any other spelling (a bare WORK id included) refuses."""
    if not isinstance(reference, str) or not reference.startswith(WORK_SCHEME):
        raise ValueError("a canonical Work reference is work://<namespace>/<work_id>; a bare Work id is not a kernel node")
    namespace, separator, work_id = reference[len(WORK_SCHEME):].partition("/")
    if not separator:
        raise ValueError("a canonical Work reference names its namespace and Work: work://<namespace>/<work_id>")
    return validate_programme({"kind": PROGRAMME_KIND, "namespace": namespace, "work_id": work_id})


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _cache_path(root: Path) -> Path:
    base = state_root()
    return base / ("session-memory-" + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12] + ".sqlite3")


def _read_state(root: Path) -> tuple[dict, dict]:
    path = root / STORE
    stat = path.stat() if path.exists() else None
    stamp = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns] if stat else [0] * 5
    processor = digest(Path(__file__).read_bytes())
    state = {"entries": {}, "sources": {}, "unreconciled_rulings": {}, "initialized": False}
    offset, reused = 0, False
    cache = _cache_path(root)
    if cache.is_file():
        try:
            with sqlite3.connect(f"file:{cache}?mode=ro", uri=True) as connection:
                meta = json.loads(connection.execute("SELECT value FROM metadata WHERE key='head'").fetchone()[0])
                same = meta["stamp"] == stamp
                appended = (meta["stamp"][:2] == stamp[:2] and stamp[2] > meta["offset"])
                if meta["processor"] == processor and (same or appended):
                    anchor_ok = same
                    if not same:
                        with path.open("rb") as stream:
                            stream.seek(max(0, meta["offset"] - 4096))
                            anchor = stream.read(min(4096, meta["offset"]))
                        anchor_ok = digest(anchor) == meta["anchor"]
                    if anchor_ok:
                        state.update(meta["state"])
                        state["entries"] = {key: json.loads(value) for key, value in connection.execute("SELECT key,value FROM entries")}
                        state["sources"] = {key: json.loads(value) for key, value in connection.execute("SELECT key,value FROM sources")}
                        state["unreconciled_rulings"] = {key: json.loads(value) for key, value in connection.execute("SELECT key,value FROM pending")}
                        offset, reused = meta["offset"], True
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError):
            state = {"entries": {}, "sources": {}, "unreconciled_rulings": {}, "initialized": False}
            offset, reused = 0, False
    before_entries, before_sources = dict(state["entries"]), dict(state["sources"])
    before_pending = dict(state["unreconciled_rulings"])
    pending = state["unreconciled_rulings"]
    raw = b""
    if stat:
        with path.open("rb") as stream:
            stream.seek(offset)
            raw = stream.read()
    position = offset
    for line in raw.splitlines(keepends=True):
        if not line.strip():
            position += len(line)
            continue
        row = json.loads(line, object_pairs_hook=_unique)
        if not isinstance(row, dict):
            raise ValueError(f"{STORE}@{position}: expected a record")
        batch = row.get("session_memory")
        if batch is None:
            if state["initialized"] and row.get("kind") in AUTHOR_KINDS:
                pending[str(row.get("id", position))] = str(row.get("ruling") or row.get("text") or "")
            position += len(line)
            continue
        if batch.get("schema_version") != SCHEMA:
            raise ValueError(f"invalid/duplicate memory revision at {position}")
        state["initialized"] = True
        for handle, source in batch.get("sources", {}).items():
            if digest(source["content"].encode()) != handle:
                raise ValueError(f"memory source digest mismatch: {handle}")
            # Keep only a locator in the derived index; canonical source bytes occur once.
            token = json.dumps(source["content"], ensure_ascii=False).encode()
            start = line.find(token)
            if start < 0:
                raise ValueError("source text has no exact JSON-string locator")
            state["sources"].setdefault(handle, {"offset": position + start, "length": len(token),
                                                "path": source.get("path"), "record": row["id"]})
        for item in batch["changes"]:
            key = item["key"]
            previous = state["entries"].get(key)
            if item.get("previous") != (previous["version"] if previous else None):
                raise ValueError(f"memory revision conflict: {key}")
            if item["kind"] not in KINDS or item["status"] not in {"active", "historical", "retired"}:
                raise ValueError(f"invalid memory classification: {key}")
            if item.get("source_handle") and item["source_handle"] not in state["sources"]:
                raise ValueError(f"missing memory source: {key}")
            state["entries"][key] = {**item, "version": digest(canonical(item)), "record": row["id"]}
        for rid in batch.get("acknowledged_rulings", []):
            pending.pop(rid, None)
        position += len(line)
    if stat:
        after = path.stat()
        if [after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns] != stamp:
            raise ValueError("ruling ledger moved during memory reconstruction; retry")
    state.update(schema_version=SCHEMA, ledger=STORE,
                 status="REVIEW_REQUIRED" if pending else "CURRENT" if state["initialized"] else "ABSENT",
                 generation=digest(canonical({key: row["version"] for key, row in state["entries"].items() if row["status"] == "active"})),
                 read_cost={"history_bytes": stamp[2], "delta_bytes_read": len(raw), "index_reused": reused})
    anchor_handle = meta["anchor"] if reused and not raw else digest(b"")
    if stat and (not reused or raw):
        with path.open("rb") as stream:
            stream.seek(max(0, position - 4096))
            anchor_handle = digest(stream.read(min(4096, position)))
    metadata = {"stamp": stamp, "offset": position, "anchor": anchor_handle, "processor": processor,
                "generation": state["generation"],
                "state": {key: state[key] for key in ("initialized",)}}
    return state, {"metadata": metadata, "reused": reused, "before_entries": before_entries, "before_sources": before_sources, "before_pending": before_pending}


def resolve(root: Path | str) -> dict:
    """Read cached current records plus the appended suffix; never write on a read."""
    return _read_state(Path(root))[0]


def get_source(root: Path | str, handle: str) -> tuple[dict, dict]:
    root = Path(root)
    state = resolve(root)
    located = state["sources"][handle]
    with (root / STORE).open("rb") as stream:
        stream.seek(located["offset"])
        encoded = stream.read(located["length"])
    text = json.loads(encoded)
    if digest(text.encode()) != handle:
        raise ValueError("archived memory source bytes moved")
    return {"key": "source/" + handle.removeprefix("sha256:"), "kind": "historical-source",
            "status": "historical", "scope": "Exact imported source, not current operating instructions",
            "text": text, "version": handle, "record": located["record"], "original_path": located["path"]}, {
        "generation": state["generation"], "ledger": STORE,
        "read_cost": {**state["read_cost"], "source_bytes_read": len(encoded)}}


def get_entry(root: Path | str, key: str) -> tuple[dict, dict]:
    """An unchanged source resolves one indexed record without materializing the rest."""
    root = Path(root)
    if key.startswith("source/"):
        return get_source(root, "sha256:" + key.removeprefix("source/"))
    source = root / STORE
    cache = _cache_path(root)
    if source.is_file() and cache.is_file():
        stat = source.stat()
        stamp = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
        try:
            with sqlite3.connect(f"file:{cache}?mode=ro", uri=True) as connection:
                meta = json.loads(connection.execute("SELECT value FROM metadata WHERE key='head'").fetchone()[0])
                if meta["stamp"] == stamp and meta["processor"] == digest(Path(__file__).read_bytes()):
                    row = connection.execute("SELECT value FROM entries WHERE key=?", (key,)).fetchone()
                    if row is None:
                        raise KeyError(key)
                    entry = json.loads(row[0])
                    payload = {k:v for k,v in entry.items() if k not in {"record", "version"}}
                    if digest(canonical(payload)) != entry["version"]:
                        raise ValueError("derived memory record checksum mismatch")
                    return entry, {"generation": meta["generation"], "ledger": STORE,
                                   "read_cost": {"records_materialized": 1, "delta_bytes_read": 0, "index_reused": True}}
        except (sqlite3.Error, OSError, ValueError, TypeError):
            pass
    state = resolve(root)
    return state["entries"][key], {"generation": state["generation"], "ledger": STORE, "read_cost": state["read_cost"]}


def refresh_index(root: Path | str) -> dict:
    """Producer-side materialization: one current cache, keyed updates, no snapshot history."""
    root = Path(root)
    state, info = _read_state(root)
    if state["read_cost"]["index_reused"] and not state["read_cost"]["delta_bytes_read"]:
        return state["read_cost"]
    path = _cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        for table in ("metadata", "entries", "sources", "pending"):
            connection.execute(f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if not info["reused"]:
            connection.execute("DELETE FROM entries")
            connection.execute("DELETE FROM sources")
            connection.execute("DELETE FROM pending")
        for table in ("entries", "sources"):
            before = info["before_" + table] if info["reused"] else {}
            for key, value in state[table].items():
                if before.get(key) != value:
                    connection.execute(f"INSERT OR REPLACE INTO {table} VALUES (?,?)", (key, canonical(value).decode()))
        for key in set(info["before_pending"]) - set(state["unreconciled_rulings"]):
            connection.execute("DELETE FROM pending WHERE key=?", (key,))
        for key, value in state["unreconciled_rulings"].items():
            if not info["reused"] or info["before_pending"].get(key) != value:
                connection.execute("INSERT OR REPLACE INTO pending VALUES (?,?)", (key, canonical(value).decode()))
        connection.execute("INSERT OR REPLACE INTO metadata VALUES ('head',?)", (canonical(info["metadata"]).decode(),))
    return state["read_cost"]


def projection(root: Path | str, *, compact: bool = False) -> dict:
    state = resolve(root)
    active = [entry for entry in state["entries"].values() if entry["status"] == "active"]
    compact_laws = {}
    if compact:
        from laplace.engine.self_corpus import law_digest
        keys = [entry["key"] for entry in active if entry["kind"] == "law"]
        compact_laws = dict(zip(keys, law_digest(root)))
    items = []
    for entry in active:
        text = entry["text"]
        if compact:
            text = compact_laws.get(entry["key"]) or entry.get("summary") or text
        item = {key: entry[key] for key in ("key", "kind", "version", "record", "scope")}
        item.update(text=text, complete_text=text == entry["text"], reference="memory://" + entry["key"])
        if entry.get("programme") is not None:
            item["programme"] = entry["programme"]
        items.append(item)
    return {"schema_version": SCHEMA, "status": state["status"], "generation": state["generation"],
            "source": STORE, "entries": items, "historical_entries": len(state["entries"]) - len(active),
            "unreconciled_rulings": state["unreconciled_rulings"],
            "views": view_status(root, state), "read_cost": state["read_cost"], "read_only": True,
            "update": "scripts/laplace-python -m laplace.engine.session_memory apply < record.json",
            "reconstruct": "scripts/laplace-python scripts/reconstruct_node.py memory://<key> --lens <goal>"}


def brief(root: Path | str) -> dict:
    state = resolve(root)
    active = [item for item in state["entries"].values() if item["status"] == "active"]
    return {"status": state["status"], "generation": state["generation"], "source": STORE,
            "active_records": len(active), "views": view_status(root, state),
            "unreconciled_rulings": list(state["unreconciled_rulings"])[:8],
            "unreconciled_count": len(state["unreconciled_rulings"]),
            "read_cost": state["read_cost"], "descend": "scripts/laplace-python scripts/wake.py --memory"}


def law_lines(root: Path | str) -> list[str]:
    state = resolve(root)
    return [row["text"] for row in state["entries"].values()
            if row["kind"] == "law" and row["status"] == "active"]


def render_law(state: dict) -> str:
    rows = [row for row in state["entries"].values() if row["kind"] == "law" and row["status"] == "active"]
    lines = ["# Standing law", "", "Generated from revisions in `proxy_verdicts.jsonl`; update the records, not this view.",
             f"<!-- law generation: {digest(canonical([row['version'] for row in rows]))} -->", ""]
    for row in rows:
        lines += ["- " + row["text"], f"  <!-- {row['key']} {row['version']} -->"]
    return "\n".join(lines) + "\n"


def render_entry(state: dict) -> str:
    entry = state["entries"].get("session-entry")
    if not entry or entry["status"] != "active":
        raise ValueError("session-entry record is absent")
    return ("<!-- Generated session entry; edit the session-entry record through laplace.engine.session_memory. -->\n"
            + f"<!-- entry version: {entry['version']} -->\n\n" + entry["text"].rstrip() + "\n")


def expected_views(state: dict) -> dict[str, str]:
    if state["status"] == "ABSENT":
        return {}
    entry = render_entry(state)
    return {"STANDING_LAW.md": render_law(state), "AGENTS.md": entry, "CLAUDE.md": entry}


def view_status(root: Path | str, state: dict | None = None) -> dict:
    root = Path(root)
    state = state or resolve(root)
    return {name: "CURRENT" if (root / name).is_file() and (root / name).read_text() == text else "STALE"
            for name, text in expected_views(state).items()}


def render_views(root: Path | str) -> list[str]:
    root = Path(root)
    refresh_index(root)
    changed = []
    for name, text in expected_views(resolve(root)).items():
        path = root / name
        if path.exists() and path.read_text() == text:
            continue
        temporary = path.with_name(path.name + ".pending")
        temporary.write_text(text)
        temporary.replace(path)
        changed.append(name)
    return changed


def apply(root: Path | str, request: dict) -> dict:
    """Append actual changes once; preserve prior versions and render existing views."""
    from laplace.core.records import journal
    from laplace.pipeline.locking import store_lock
    root = Path(root).resolve()
    if not request.get("changes"):
        raise ValueError("an update contains changed records")
    with store_lock("session-memory-" + hashlib.sha256(str(root).encode()).hexdigest()[:12]):
        state = resolve(root)
        changes = []
        changed_keys = set()
        for proposed in request["changes"]:
            key = proposed["key"]
            if key in changed_keys:
                raise ValueError("combine changes to the same record in one update")
            changed_keys.add(key)
            prior = state["entries"].get(key)
            item = {k:v for k,v in (prior or {}).items() if k not in {"version", "record", "previous"}}
            item.update(proposed)
            if prior and "text" in proposed and proposed["text"] != prior["text"] and "summary" not in proposed:
                item.pop("summary", None)  # a text amendment invalidates its old summary
            if not isinstance(key, str) or not key or len(key) > 180 or any(c.isspace() for c in key):
                raise ValueError("memory keys must be short stable identifiers")
            if item.get("kind") not in KINDS or item.get("status", "active") not in {"active", "historical", "retired"}:
                raise ValueError("invalid memory classification")
            if not isinstance(item.get("text"), str) or not item["text"].strip() or not item.get("scope"):
                raise ValueError("memory content and scope are required")
            item.setdefault("status", "active")
            if item.get("programme") is None:
                item.pop("programme", None)
            else:
                if item["kind"] != "procedure":
                    raise ValueError("a programme coordinate belongs only to an explicitly authored procedure record")
                item["programme"] = validate_programme(item["programme"])
            prior = state["entries"].get(key)
            comparable = {k:v for k,v in (prior or {}).items() if k not in {"version", "record", "previous"}}
            if item == comparable:
                continue
            item["previous"] = prior["version"] if prior else None
            changes.append(item)
        if changes or request.get("acknowledged_rulings"):
            stamp = datetime.now(timezone.utc)
            batch = {"schema_version": SCHEMA, "changes": changes, "sources": request.get("sources", {}),
                     "acknowledged_rulings": request.get("acknowledged_rulings", [])}
            row = {"id": "PV-" + stamp.strftime("%Y%m%dT%H%M%SZ") + "-memory-" + digest(canonical(batch))[7:19],
                   "date": stamp.date().isoformat(), "kind": "author-instruction",
                   "ruling": request.get("basis") or "Update the named session memory records.", "source": request.get("source", "explicit session memory update"),
                   "session_memory": batch}
            # Validate the proposed event against the same reader before appending it.
            for handle, source in batch["sources"].items():
                if digest(source["content"].encode()) != handle:
                    raise ValueError("source bytes do not match their handle")
            known_sources = set(state["sources"]) | set(batch["sources"])
            if any(item.get("source_handle") and item["source_handle"] not in known_sources for item in changes):
                raise ValueError("memory source is absent")
            (root / "contract").mkdir(exist_ok=True)
            journal.bank_row(STORE, row, root=root)
        changed_views = render_views(root)
    return {"changed_records": len(changes), "changed_views": changed_views,
            "generation": resolve(root)["generation"]}


def programme(root: Path | str) -> dict:
    """The explicitly authored current-programme selection (``PROGRAMME_KEY``), read-only.

    States: ABSENT (no record), INACTIVE (historical/retired), UNSELECTED (procedure without a coordinate), INVALID
    (a recorded coordinate outside the closed shape; history is kept, nothing is guessed) and SELECTED.
    """
    base = {"schema_version": PROGRAMME_SCHEMA, "key": PROGRAMME_KEY, "authority": PROGRAMME_AUTHORITY}
    try:
        entry, state = get_entry(root, PROGRAMME_KEY)
    except KeyError:
        return {**base, "state": "ABSENT",
                "reason": "No explicitly authored procedure/eigen-programme record exists; no programme is inferred."}
    base["entry"] = {"version": entry.get("version"), "record": entry.get("record"), "kind": entry.get("kind"),
                     "status": entry.get("status"), "generation": state.get("generation")}
    if entry.get("status") != "active":
        return {**base, "state": "INACTIVE", "reason": "The programme procedure record is " + str(entry.get("status")) + "."}
    if entry.get("kind") != "procedure":
        return {**base, "state": "INVALID", "reason": "The programme record is not a procedure record."}
    raw = entry.get("programme")
    if raw is None:
        return {**base, "state": "UNSELECTED", "reason": "The procedure record carries no typed programme coordinate."}
    try:
        reference = validate_programme(raw)
    except ValueError as exc:
        return {**base, "state": "INVALID", "reason": str(exc)}
    return {**base, "state": "SELECTED", "reference": reference,
            "descent": {"kind": PROGRAMME_KIND, "reference": programme_uri(reference)}}


def source_contract() -> dict:
    """The declared stable meaning of the programme coordinate and its delegated canonical-Work reading.

    Shapes and owner routes only: no Work state, account, actor or next action is copied into this declaration.
    """
    here = "src/laplace/engine/session_memory.py"
    return {
        "schema": "laplace.source-contract/1", "owner": "engine.session_memory", "operation": "programme-continuity",
        "purpose": {"text": ("Reconstruct the current programme from Eigen records: one explicitly authored procedure record selects "
                              "a canonical Work coordinate; every door reads that Work's continuity through its owner under the "
                              "caller's actual Scope."),
                    "author": "A_bridges_kernel implementation, Root e716/e2f6 (unreviewed source declaration)",
                    "assumptions": ["Work owns goal, lifecycle, review and completion", "Source owns production and account authority",
                                    "Writing owns actual requests, turns and processes"]},
        "segments": {
            "pointer": {"record_key": PROGRAMME_KEY, "record_kind": "procedure", "field": "programme",
                        "shape": list(PROGRAMME_FIELDS), "kind": PROGRAMME_KIND, "identifier": _PROGRAMME_IDENT.pattern,
                        "excluded": ["status", "lifecycle", "account", "grant", "actor", "next_action", "capability"],
                        "states": ["ABSENT", "INACTIVE", "UNSELECTED", "INVALID", "SELECTED"]},
            "descent": {"kind": PROGRAMME_KIND, "reference": WORK_SCHEME + "<namespace>/<work_id>",
                        "owner": "laplace.work.project_work_views.read view continuity",
                        "scope": "actual owner_discovery.Scope admitted before Work lookup",
                        "bare_work_ids": "never promoted into kernel or legacy work-order rows"},
            "doors": {"sdk": ["laplace.sdk.programme", "laplace.sdk.work_continuity", "laplace.sdk.work_read", "laplace.sdk.work_action"],
                      "native": "project {view: continuity, id, request}", "http": "GET /work/state?view=continuity&id=...&request=...",
                      "wake": "programme glow (person and engine context share the coordinate)",
                      "actions": "owner-issued work_delivery continue / development_source proof, revalidated at the effect owner"},
        },
        "relations": [
            {"consumer": "engine.descent.canonical-work", "relation": "implements", "segments": ["descent"], "location": "src/laplace/engine/descent.py"},
            {"consumer": "engine.wake.programme", "relation": "consumes", "segments": ["pointer", "descent"], "location": "src/laplace/engine/wake.py"},
            {"consumer": "sdk.programme", "relation": "projects", "segments": ["pointer", "descent", "doors"], "location": "src/laplace/sdk.py"},
            {"consumer": "engine.session_memory.programme", "relation": "implements", "segments": ["pointer"], "location": here},
            {"consumer": "tests.eigen_continuity_reconstruction", "relation": "evaluates", "segments": ["pointer", "descent"],
             "location": "tests/test_eigen_continuity_reconstruction.py"},
            {"consumer": "tests.eigen_continuity_doors", "relation": "evaluates", "segments": ["doors"], "location": "tests/test_eigen_continuity_doors.py"},
        ],
        "steps": [{"id": "select", "primitive": "read", "object": "session-memory procedure record", "effect": "none"},
                  {"id": "descend", "primitive": "read", "object": "canonical Work continuity", "effect": "none",
                   "guard": "actual Scope before lookup"}],
        "authority": {"pointer": "explicit session_memory apply by an author/operator; selection only",
                      "publication": "explicit operator/SDK action; a native read never grants it"},
        "recovery": "An invalid or absent coordinate is reported, never guessed; prior memory versions remain in the ledger.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("show", "apply", "render", "check"), nargs="?", default="show")
    parser.add_argument("--key")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    root = source_tree()
    if args.command == "apply":
        out = apply(root, json.load(sys.stdin, object_pairs_hook=_unique))
    elif args.command == "render":
        out = {"changed": render_views(root)}
    elif args.command == "check":
        out = projection(root, compact=True)
    elif args.key:
        out = get_entry(root, args.key)[0]
    else:
        out = projection(root, compact=args.compact)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return int(args.command == "check" and (out["status"] != "CURRENT" or "STALE" in out["views"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
