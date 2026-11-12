"""Append-only, content-addressed engine dial sets (laplace.dial-set/1).

The hash covers the canonical record except dial_set_id and journal transport
metadata (ts). Missing or corrupt state refuses; readers never fall back to genesis.
LAPLACE_DIALS_ROOT or --root isolates both the store and its journal receipts.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import argparse
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Literal, TypedDict

SCHEMA = "laplace.dial-set/1"
STORE = "contract/dials.jsonl"
GENESIS = "GENESIS"
SCOPES = ("engine-fold", "engine-metric", "engine-triggers", "atlas-export")


class Dial(TypedDict, total=False):
    value: int | float | bool | str
    kind: Literal["int", "float", "bool", "str"]
    range: list[int | float | None]
    choices: list[int | float | bool | str]
    unit: str
    owner: Literal["his", "engine"]
    why: str
    source: str
    admitted_by: str


class DialSet(TypedDict):
    schema_version: str
    dial_set_id: str
    parent_dial_set: str
    scope: str
    dials: dict[str, Dial]


class DialRefusal(ValueError):
    """A missing, malformed, or invalid dial record; never a default value."""
    code = "DIAL-SET-REFUSED"


_cache: dict[Path, tuple[tuple[int, ...], dict[str, DialSet]]] = {}


def _root(root: Path | str | None = None) -> Path:
    return Path(root or os.environ.get("LAPLACE_DIALS_ROOT") or
                source_tree()).resolve()


def _hash(row: dict[str, Any]) -> str:
    body = {k: row[k] for k in ("schema_version", "parent_dial_set", "scope", "dials")}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _pairs(pairs):
    out = {}
    for key, val in pairs:
        if key in out:
            raise DialRefusal(f"duplicate key: {key}")
        out[key] = val
    return out


def _validate(row: dict[str, Any], *, check_hash: bool = True) -> None:
    if not isinstance(row, dict) or row.get("schema_version") != SCHEMA:
        raise DialRefusal("unknown dial-set schema")
    if set(row) - {"schema_version", "dial_set_id", "parent_dial_set", "scope", "dials", "ts"}:
        raise DialRefusal("unknown dial-set fields")
    if row.get("scope") not in SCOPES or not isinstance(row.get("parent_dial_set"), str):
        raise DialRefusal("invalid scope or parent")
    ds = row.get("dials")
    if not isinstance(ds, dict) or not ds:
        raise DialRefusal("empty dial set")
    for name, dial in ds.items():
        if not isinstance(dial, dict):
            raise DialRefusal(f"{name}: expected a dial record")
        kind, val = dial.get("kind"), dial.get("value")
        types = {"int": int, "float": float, "bool": bool, "str": str}
        if kind not in types or type(val) is not types[kind]:
            raise DialRefusal(f"{name}: value must have kind {kind}")
        if kind == "float" and not math.isfinite(val):
            raise DialRefusal(f"{name}: non-finite value")
        if dial.get("owner") not in ("his", "engine"):
            raise DialRefusal(f"{name}: invalid owner")
        for field in ("unit", "why", "source", "admitted_by"):
            if not isinstance(dial.get(field), str) or not dial[field].strip():
                raise DialRefusal(f"{name}: missing {field}")
        if ("range" in dial) == ("choices" in dial):
            raise DialRefusal(f"{name}: exactly one of range or choices required")
        if "choices" in dial:
            choices = dial["choices"]
            if not isinstance(choices, list) or not choices or any(type(c) is not types[kind] for c in choices):
                raise DialRefusal(f"{name}: invalid choices")
            if val not in choices:
                raise DialRefusal(f"{name}: outside choices")
        else:
            bounds = dial["range"]
            if kind not in ("int", "float") or not isinstance(bounds, list) or len(bounds) != 2:
                raise DialRefusal(f"{name}: invalid range")
            lo, hi = bounds
            if any(b is not None and (type(b) not in (int, float) or not math.isfinite(b)) for b in bounds):
                raise DialRefusal(f"{name}: invalid bounds")
            if lo is not None and hi is not None and lo > hi:
                raise DialRefusal(f"{name}: reversed range")
            if (lo is not None and val < lo) or (hi is not None and val > hi):
                raise DialRefusal(f"{name}: outside range {bounds}")
    if row["scope"] == "engine-fold":
        if ds["silhouette_k_min"]["value"] > ds["branch_max"]["value"]:
            raise DialRefusal("silhouette_k_min exceeds branch_max")
    if check_hash and row.get("dial_set_id") != _hash(row):
        raise DialRefusal("content hash mismatch")


def _read_validated(root=None) -> dict[str, DialSet]:
    """Private cache view. Callers must not expose or mutate the returned mapping."""
    path = _root(root) / STORE
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {}
    stamp = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if path in _cache and _cache[path][0] == stamp:
        return _cache[path][1]
    latest = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line, object_pairs_hook=_pairs)
            _validate(row)
            scope = row["scope"]
            parent = latest[scope]["dial_set_id"] if scope in latest else GENESIS
            if row["parent_dial_set"] != parent:
                raise DialRefusal("broken parent chain")
            latest[scope] = row
        except (ValueError, KeyError, TypeError) as exc:
            raise DialRefusal(f"{path}:{n}: {exc}") from exc
    _cache[path] = (stamp, latest)
    return latest


def _read(root=None) -> dict[str, DialSet]:
    """Detached all-scope view, preserving the existing reader's mutation isolation."""
    return deepcopy(_read_validated(root))


def _current_validated(scope: str, root: Path | str | None = None) -> DialSet:
    if scope not in SCOPES:
        raise DialRefusal(f"unknown scope: {scope}")
    rows = _read_validated(root)
    if scope not in rows:
        raise DialRefusal(f"missing {scope}; pour genesis through laplace.pipeline.dial_profiles")
    return rows[scope]


def current(scope: str, root: Path | str | None = None) -> DialSet:
    """Return only the requested scope, detached from the validated cache."""
    return deepcopy(_current_validated(scope, root))


def value(scope: str, name: str) -> Any:
    try:
        result = _current_validated(scope)["dials"][name]["value"]
    except KeyError as exc:
        raise DialRefusal(f"unknown dial {scope}/{name}") from exc
    # The validated schema currently admits only these immutable scalar types.
    # Preserve isolation if a later schema adds a mutable value type.
    return result if type(result) in (str, int, float, bool) else deepcopy(result)


def projection(full: bool = False) -> list[dict[str, Any]]:
    result = []
    for scope in SCOPES:
        try:
            row = current(scope)
            result.append(row if full else {
                "scope": scope, "dial_set_id": row["dial_set_id"],
                "n_dials": len(row["dials"]), "parent": row["parent_dial_set"],
                "descend": f"/usr/bin/python3 -m laplace.pipeline.dial_profiles --show {scope}",
            })
        except DialRefusal as exc:
            result.append({"scope": scope, "status": exc.code, "reason": str(exc)})
    return result


@contextmanager
def _locked(root):
    path = _root(root) / STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _bank(row, root):
    from laplace.core.records.journal import bank_row
    _validate(row, check_hash=False)
    row["dial_set_id"] = _hash(row)
    _validate(row)
    bank_row(STORE, row, root=_root(root))
    return current(row["scope"], root)


def genesis() -> list[DialSet]:
    """Migration evidence: values and source coordinates at 2f361faf, before removal.

    Ranges describe mathematical domains, not empirically tuned upper bounds.
    None is an unbounded end; no new operational cap is invented here.
    Later declared fields seed new stores and admit explicit successors only;
    they never rewrite an existing scope's banked identity.
    """
    rows = []
    def add(scope, specs):
        ds = {}
        for name, val, bounds, unit, source, why in specs:
            ds[name] = {"value": val, "kind": type(val).__name__, "range": bounds,
                        "unit": unit, "owner": "engine", "why": why,
                        "source": source, "admitted_by": "WO-20260914-the-dials-conceptric: genesis only"}
        row = {"schema_version": SCHEMA, "parent_dial_set": GENESIS, "scope": scope, "dials": ds}
        row["dial_set_id"] = _hash(row)
        rows.append(row)
    F = "src/laplace/engine/meaning_upfold.py:"
    M = "src/laplace/representation/metric_distill.py:"
    add("engine-fold", [
        ("leaf_max", 10, [1, None], "leaves", F+"67", "Stop splitting small clusters."),
        ("branch_max", 8, [2, None], "clusters", F+"68", "Upper silhouette candidate bound."),
        ("max_depth", 6, [0, None], "levels", F+"69", "Defensive recursion bound."),
        ("repair_sweep_per_deposit", 64, [0, None], "clusters", F+"1535", "Bound the largest-first incremental overflow repair sweep."),
        ("silhouette_k_min", 2, [2, None], "clusters", F+"654", "Lower silhouette candidate bound; silhouette needs at least two clusters."),
        ("spectral_gpu_min_n", 384, [1, None], "rows", F+"421", "Measured crossover to GPU spectral splits."),
        ("eigensolver_tolerance", 1e-5, [0.0, None], "residual", F+"647", "Convergence tolerance for cluster-local GPU eigensolver retries."),
        ("eigensolver_jitter", 1e-8, [0.0, None], "operator", F+"647", "Deterministic diagonal spread for the third GPU eigensolver attempt."),
        ("eigensolver_power_iterations", 256, [1, None], "iterations", F+"647", "Bound for the final GPU block-power recovery attempt."),
        ("kmeans_blas_threads", 6, [1, None], "threads", F+"455", "Measured thread cap for the k-means sweep."),
        ("kmeans_seed", 0, [0, 4294967295], "seed", F+"495", "Reproduce the incumbent random stream."),
        ("kmeans_n_init", 10, [1, None], "starts", F+"496", "Preserve incumbent k-means restarts."),
        ("selector_chi_top", 16, [1, None], "directions", F+"516", "Declared level-one selector budget."),
        ("selector_chi_deep", 8, [1, None], "directions", F+"517", "Declared deeper selector budget."),
        ("selector_beta", 0.10, [0.0, 1.0], "fraction", F+"518", "Selector visit fraction."),
        ("selector_queries", 512, [1, None], "queries", F+"519", "Selector sample budget."),
        ("selector_seed", 11, [0, None], "seed", F+"520", "Reproducible selector sample."),
    ])
    add("engine-metric", [
        ("margin", 0.2, [0.0, None], "score", M+"51", "Wired pair hinge margin."),
        ("lr", 0.05, [0.0, None], "step", M+"52", "SGD step size."),
        ("anchor", 0.05, [0.0, None], "weight", M+"53", "Pull toward identity per step."),
        ("epochs", 5, [1, None], "epochs", M+"54", "Training passes."),
        ("holdout", 0.1, [0.0, 1.0], "fraction", M+"55", "Positive pairs reserved for AUC."),
        ("neg_per_pos", 4, [1, None], "pairs", M+"56", "Negative samples per positive pair."),
        ("seed", 7, [0, None], "seed", M+"57", "Reproducible metric fit."),
        ("sample_neg", 64, [1, None], "attempts", M+"497", "Attempts to draw a non-positive negative."),
        ("replay_fraction", 0.02, [0.0, 1.0], "fraction", M+"pair_delta",
         "Cure-B: replay this fraction of unchanged positive pairs when the incremental training set changes."),
    ])
    add("engine-triggers", [
        ("minimum_leaf_multiple", 2, [1, None], "multiple", F+"856", "Minimum residue size as a multiple of leaf_max (also line 1334)."),
        ("full_fraction", 0.20, [0.0, 1.0], "fraction", F+"1373", "Lens drift and residue churn full-rebuild threshold (also line 1406)."),
    ])
    add("atlas-export", [
        ("sealed_ref_top_n", 20, [1, None], "nodes", "scripts/export_atlas_snapshot.py:474", "Per-node breakdown depth in the seal report."),
        ("sealed_ref_threshold", 100, [1, None], "references", "scripts/export_atlas_snapshot.py:473", "Measured gap between sealed-derived stores and ordinary nodes."),
    ])
    return rows


def pour_genesis(root=None) -> list[DialSet]:
    with _locked(root):
        existing = _read(root)
        for row in genesis():
            if row["scope"] not in existing:
                _bank(row, root)
        return [current(scope, root) for scope in SCOPES]


def set_value(scope: str, name: str, raw: str, *, by: str, why: str, root=None) -> DialSet:
    if not by.strip() or not why.strip():
        raise DialRefusal("a successor requires --by and --why")
    with _locked(root):
        row = current(scope, root)
        if name not in row["dials"]:
            # New schema entries join existing stores only by an explicit successor.
            schema = next(r for r in genesis() if r["scope"] == scope)["dials"]
            if name not in schema:
                raise DialRefusal(f"unknown dial {scope}/{name}")
            row["dials"][name] = deepcopy(schema[name])
        dial = row["dials"][name]
        try:
            val = raw if dial["kind"] == "str" else json.loads(raw)
        except ValueError as exc:
            raise DialRefusal(f"invalid value: {raw}") from exc
        if dial["kind"] == "float" and type(val) is int:
            val = float(val)
        row = {k: row[k] for k in ("schema_version", "scope", "dials", "dial_set_id")}
        row["parent_dial_set"] = row["dial_set_id"]
        dial["value"], dial["admitted_by"], dial["why"] = val, by, why
        return _bank(row, root)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--pour-genesis", action="store_true")
    modes.add_argument("--show", choices=SCOPES)
    modes.add_argument("--set", nargs=2, metavar=("SCOPE", "NAME=VALUE"))
    parser.add_argument("--by", default="")
    parser.add_argument("--why", default="")
    args = parser.parse_args(argv)
    try:
        if args.pour_genesis:
            result = [{"scope": row["scope"], "dial_set_id": row["dial_set_id"],
                       "n_dials": len(row["dials"]), "parent": row["parent_dial_set"]}
                      for row in pour_genesis(args.root)]
        elif args.show:
            result = current(args.show, args.root)
        else:
            scope, assignment = args.set
            if "=" not in assignment:
                raise DialRefusal("expected NAME=VALUE")
            name, raw = assignment.split("=", 1)
            result = set_value(scope, name, raw, by=args.by, why=args.why, root=args.root)
        print(json.dumps(result, sort_keys=True, indent=1))
        return 0
    except DialRefusal as exc:
        print(json.dumps({"status": exc.code, "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
