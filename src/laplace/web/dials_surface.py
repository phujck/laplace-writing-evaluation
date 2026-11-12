"""the dials conjugate — the one WRITE path for the pipeline calibration overlay.

``dials.py`` is the READ surface: code defaults (``_DEFAULTS``) overlaid by the
versioned ``profiles/pipeline/dials-v1.yaml``. This module is its conjugate — the
single sanctioned way that overlay is EDITED from a browser, built on the
storyboard idiom (``storyboard.plan_write``): append-only ops folded over an
immutable base, validate-before-persist, atomic replace, round-trip proof.

The stance (the one that keeps the file plain): the reduce base is the parsed
OVERLAY — the YAML subset a human hand-wrote — NOT the merged dials. So

    load_dials  ==  defaults() ⊕ overlay

A ``set-leaf`` op MATERIALISES an absent leaf into the overlay; a ``reset-leaf``
op DELETES it (and prunes the now-empty parent dicts) so the code default in
``dials._DEFAULTS`` rules again. Two op kinds, nothing else:

    {"kind": "set-leaf",   "path": "loop.max_rounds", "value": 6}
    {"kind": "reset-leaf", "path": "routing.defer_kinds"}

Every write banks the base once (a byte-copy of the hand-written YAML is archived,
header preserved), stamps the op, gates it BEFORE touching disk (known kind; the
dotted path resolves to a non-dict leaf in ``dials.defaults()``; ``version`` is
refused; the value passes the type/enum/bounds gate), then reduces, dumps a
candidate, re-loads it through ``dials.load_dials`` as the persist gate, appends
to the friction ledger, and atomically replaces the profile. A reject touches
NOTHING. dial documentation lives in ``dials.py`` ``_DEFAULTS``; this module owns
only the write mechanics, never the meaning of a dial.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import datetime as _dt
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

import yaml

from laplace.pipeline import dials
from laplace.pipeline import ledger as _ledger

#: repo root = src/laplace/web/dials_surface.py -> parents[2] (mirrors dials._REPO_ROOT).
_REPO_ROOT = source_tree()

#: writes are serialised in-process (the scanner is a threading server): ensure
#: base + stamp + gate + reduce + persist is one critical section.
_DIALS_LOCK = threading.Lock()

_JSON = "application/json; charset=utf-8"
_DEFAULT_PROFILE = "dials-v1.yaml"

# the banner the managed (rewritten) YAML carries, so a reader knows the file is
# reduced, not hand-edited, and where to look for what a dial means.
_BANNER = (
    "# managed by /dials — reduced from {name}.base.json + {name}.friction.jsonl\n"
    "# dial documentation lives in dials.py _DEFAULTS; edit through the surface, "
    "not by hand.\n"
)




# ---------------------------------------------------------------------------
# the enum tables — what the CONSUMING code actually accepts (evidence in the
# module's return payload), never a guess. A leaf absent here is type-checked
# only (e.g. drift.page_count_change stays a free str until the author names
# alternatives; machine_adjudication.referee names a role, no closed set).
# ---------------------------------------------------------------------------

_LEAF_ENUMS: dict[str, set[str]] = {
    # schema.MODEL_RANK = ("haiku","sonnet","opus"); dials defaults draw from it.
    "roles.*.model": {"opus", "sonnet", "haiku"},
    # the three effort tiers used throughout (schema.WORKER_MODEL, the workflows).
    "roles.*.effort": {"high", "medium", "low"},
    # B17: the python leg's FLOOR tier, drawn from the same MODEL_RANK. The
    # default is None (inert) — reset-leaf is the only route back to inert, so a
    # pin can never be half-cleared into a typo.
    "dispatch.model_pin": {"opus", "sonnet", "haiku"},
    # dials.py:68 "harnessed|loop"; project-harnessed.js:114 reads loop.fix_mode.
    "loop.fix_mode": {"harnessed", "loop"},
    # dials.py:83 "auto|always|never"; project-fixedpoint.js:97 reads loop.weld.
    "loop.weld": {"auto", "always", "never"},
    # dials.py:96 "off|descaffold"; dials.final_layer_mode reads loop.final_layer.
    "loop.final_layer": {"off", "descaffold"},
    # dials.py:161 "auto|section" (section = kill-switch to today's grain).
    "regen_grain.mode": {"auto", "section"},
    # dials.py evolution group: the ratify door shape (evolution_surface reads it).
    "evolution.ratify_mode": {"per-item", "bulk-arm"},
    # dials.py selection group: which DRAFT selection-rule file the sheet reads
    # (selection_sheet.read_selection resolves profiles/selection/<value>.yaml).
    # draft-psi-v2 (2026-07-21) adds the REACH GATE (gate_reach) — a NEW versioned
    # file, never an edit of v1; the DEFAULT dial stays draft-psi-v1 (flipping the
    # live default is his/the orchestrator's word, never a browser dial-nudge).
    "selection.draft_psi": {"draft-psi-v1", "draft-psi-v2"},
}

#: numeric leaves that must be >= 1 (a zero round budget / pass cap / vote count
#: is a nonsense calibration).
_MIN_ONE = frozenset({
    "loop.max_rounds",
    "loop.harnessed.max_passes",
    "loop.verify_votes",
})

#: thresholds / counts / geometric floors — non-negative.
_MIN_ZERO = frozenset({
    "loop.weld_global_dirty_threshold",
    "loop.harnessed.second_pass_open_threshold",
    "drift.page_change_warn",
    "routing.dismissal_recalibrate_threshold",
    "machine_adjudication.calibration_threshold",
    "mech.overfull_floor_pt",
})


def _defaults() -> dict[str, Any]:
    """A fresh deep copy of the code defaults — the schema every gate reads."""
    return dials.defaults()


# ---------------------------------------------------------------------------
# profile / sidecar resolution (allowlist-fenced)
# ---------------------------------------------------------------------------

def _base_path(profile_path: Path, name: str) -> Path:
    return profile_path.with_name(name + ".base.json")


def _ledger_path(profile_path: Path, name: str) -> Path:
    return profile_path.with_name(name + ".friction.jsonl")


def _candidate_path(profile_path: Path, name: str) -> Path:
    return profile_path.with_name(name + ".candidate")


# ---------------------------------------------------------------------------
# the overlay: parse, base banking, dotted-path walks
# ---------------------------------------------------------------------------

def _parse_overlay(profile_path: Path) -> dict[str, Any]:
    """The hand-written YAML subset as a dict (``{}`` for an empty/absent file)."""
    if not profile_path.is_file():
        return {}
    loaded = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(
            f"dials profile {profile_path} must be a mapping, "
            f"got {type(loaded).__name__}")
    return loaded


def _read_base(profile_path: Path, name: str) -> dict[str, Any]:
    """The immutable base overlay, READ-only: the banked ``<name>.base.json`` when
    present, else the current parsed YAML (no banking — a read never mints a base)."""
    bp = _base_path(profile_path, name)
    if bp.is_file():
        try:
            return json.loads(bp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return _parse_overlay(profile_path)


def _ensure_base(profile_path: Path, name: str) -> dict[str, Any]:
    """Bank the immutable base on FIRST write: snapshot the parsed overlay to
    ``<name>.base.json`` and archive a byte-copy of the original hand-written YAML
    (header preserved) under ``profiles/pipeline/archive/``. Returns the base."""
    bp = _base_path(profile_path, name)
    if not bp.is_file():
        overlay = _parse_overlay(profile_path)
        bp.write_text(json.dumps(overlay, ensure_ascii=False, indent=1),
                      encoding="utf-8")
        # a one-time byte-copy of the pre-board YAML: coarse rollback + the
        # hand-written header survives even if the ledger is later lost.
        if profile_path.is_file():
            arch = profile_path.parent / "archive"
            try:
                arch.mkdir(exist_ok=True)
                stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
                (arch / f"{name}.preboard_{stamp}.yaml").write_bytes(
                    profile_path.read_bytes())
            except OSError:
                pass
    return _read_base(profile_path, name)


def _get_path(d: Any, path: str) -> tuple[bool, Any]:
    """``(found, value)`` for a dotted path in a nested dict."""
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _is_leaf_path(path: str) -> bool:
    """The dotted path resolves to a NON-DICT leaf in ``dials.defaults()`` (lists
    are leaves)."""
    found, v = _get_path(_defaults(), path)
    return found and not isinstance(v, dict)


# ---------------------------------------------------------------------------
# the fold — what an op MEANS (honours ledger.reduce: skip, never raise)
# ---------------------------------------------------------------------------

def _apply_op(overlay: dict[str, Any], op: dict) -> None:
    """Fold one op into the overlay IN PLACE. Unknown/malformed ops are SKIPPED
    (the ledger.reduce contract) so one bad record never poisons the reduction.

    ``set-leaf`` walks/creates intermediate dicts only along paths that are dicts
    in ``defaults()`` and only sets a non-dict leaf; ``reset-leaf`` deletes the
    leaf if present, then prunes now-empty parent dicts."""
    kind = op.get("kind")
    path = op.get("path")
    if kind not in ("set-leaf", "reset-leaf") or not isinstance(path, str) or not path:
        return
    parts = path.split(".")
    defs = _defaults()

    if kind == "set-leaf":
        if "value" not in op:
            return
        dref: Any = defs
        cur = overlay
        for p in parts[:-1]:
            # only descend where defaults says this is a dict-shaped path
            if not isinstance(dref, dict) or p not in dref or not isinstance(dref[p], dict):
                return
            dref = dref[p]
            nxt = cur.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[p] = nxt
            cur = nxt
        last = parts[-1]
        if not isinstance(dref, dict) or last not in dref or isinstance(dref[last], dict):
            return  # the final key must be a non-dict leaf in defaults
        cur[last] = op["value"]
        return

    # reset-leaf
    stack: list[tuple[dict, str]] = []
    cur = overlay
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return
        stack.append((cur, p))
        cur = cur[p]
    last = parts[-1]
    if not isinstance(cur, dict) or last not in cur:
        return  # absent-leaf reset is a no-op
    del cur[last]
    for parent, key in reversed(stack):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            del parent[key]
        else:
            break


def reduce_overlay(base: dict[str, Any], ops: list[dict]) -> dict[str, Any]:
    """The current overlay = the immutable base with the ledger folded over it, in
    order. Pure (a deep copy is mutated; the base is never touched). Mechanics live
    in the one ledger engine; the fold stays here in :func:`_apply_op`."""
    return _ledger.reduce(base, ops, _apply_op)


# ---------------------------------------------------------------------------
# the validation gate — type family, then enum, then numeric bounds
# ---------------------------------------------------------------------------

def _enum_key(path: str) -> str | None:
    """The ``_LEAF_ENUMS`` key governing this path (roles.<name>.model/effort
    collapse to a wildcard), or ``None`` if the leaf carries no closed set."""
    m = re.fullmatch(r"roles\.[^.]+\.(model|effort)", path)
    if m:
        return f"roles.*.{m.group(1)}"
    return path if path in _LEAF_ENUMS else None


def _type_reason(path: str, default: Any, value: Any) -> str | None:
    """Generic type-family check against the default leaf. bool is checked BEFORE
    int (bool is an int subtype); a list default demands a list, and a list-of-str
    default demands list-of-str."""
    if isinstance(default, bool):
        if not isinstance(value, bool):
            return f"{path}: expected bool, got {type(value).__name__}"
    elif isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            got = "bool" if isinstance(value, bool) else type(value).__name__
            return f"{path}: expected int, got {got}"
    elif isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            got = "bool" if isinstance(value, bool) else type(value).__name__
            return f"{path}: expected number, got {got}"
    elif isinstance(default, str):
        if not isinstance(value, str):
            return f"{path}: expected str, got {type(value).__name__}"
    elif isinstance(default, list):
        if not isinstance(value, list):
            return f"{path}: expected list, got {type(value).__name__}"
        if all(isinstance(x, str) for x in default) and not all(
                isinstance(x, str) for x in value):
            return f"{path}: expected a list of str"
    return None


def _bounds_reason(path: str, value: Any) -> str | None:
    """Numeric bounds for the leaves the pipeline cannot run outside of."""
    if path in _MIN_ONE and value < 1:
        return f"{path}: must be >= 1"
    if path in _MIN_ZERO and value < 0:
        return f"{path}: must be >= 0"
    if path == "regen_grain.paragraph_max_fraction" and not (0 < value <= 1):
        return f"{path}: must be in (0, 1]"
    return None


def _check_leaf(path: str, value: Any) -> str | None:
    """``None`` if ``value`` is an admissible setting for the leaf at ``path``, else
    a human reason. Type family first, then the enum table, then numeric bounds."""
    found, default = _get_path(_defaults(), path)
    if not found:
        return f"unknown dial path {path!r} — not in dials.defaults()"
    if isinstance(default, dict):
        return f"{path!r} is a dict, not a settable leaf"
    r = _type_reason(path, default, value)
    if r:
        return r
    ek = _enum_key(path)
    if ek and value not in _LEAF_ENUMS[ek]:
        return f"{path}: {value!r} not one of {sorted(_LEAF_ENUMS[ek])}"
    return _bounds_reason(path, value)


def _gate(op: dict) -> str | None:
    """The pre-persist gate over a stamped op: known kind; a dotted path that
    resolves to a non-dict leaf; ``version`` refused; and (for set-leaf) the value
    passes :func:`_check_leaf`. ``None`` == admit; a string == the named reject."""
    kind = op.get("kind")
    if kind not in ("set-leaf", "reset-leaf"):
        return f"unknown op kind {kind!r} — expected set-leaf|reset-leaf"
    path = op.get("path")
    if not isinstance(path, str) or not path:
        return "op missing a dotted 'path'"
    if path == "version":
        return ("refusing to set 'version' — minting a calibration generation is "
                "the author's act (a new dials-vN.yaml), never a browser edit")
    if not _is_leaf_path(path):
        return (f"unknown dial path {path!r} — not a non-dict leaf in "
                "dials.defaults()")
    if kind == "set-leaf":
        if "value" not in op:
            return "set-leaf missing 'value'"
        return _check_leaf(path, op["value"])
    return None


# ---------------------------------------------------------------------------
# op stamping + round-trip proof
# ---------------------------------------------------------------------------

def _stamp(op: dict) -> dict:
    """Return a copy of the op stamped with a UTC iso ``ts``. The actor law
    (orchestrator ruling 2026-07-22): ``by`` is NOT defaulted here — his name is
    never a default. An automated drive that omits the actor once forged his hand
    in the friction ledger; the actor is a required, caller-supplied field, gated at
    the ``/dials/op`` door (422 when absent, the desk's ``/desk/act`` law exactly).
    A pre-stamped ``by`` (the confirmed act, or a run's own identity) rides through
    untouched; nothing is invented here."""
    return {**op,
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}


def _round_trip(op: dict, merged: dict, reduced: dict) -> dict:
    """Prove the fresh load reflects the op. For set-leaf the effective value must
    equal the request and its source must be the overlay; for reset-leaf the
    effective value must equal the code default AND the path must be ABSENT from the
    reduced overlay (the default rules again)."""
    path = op["path"]
    if op["kind"] == "set-leaf":
        requested = op["value"]
        found, effective = _get_path(merged, path)
        source = "overlay" if _get_path(reduced, path)[0] else "default"
        return {"path": path, "requested": requested, "effective": effective,
                "source": source,
                "ok": bool(found and effective == requested and source == "overlay")}
    # reset-leaf: the code default now rules
    default_val = _get_path(_defaults(), path)[1]
    found, effective = _get_path(merged, path)
    in_overlay = _get_path(reduced, path)[0]
    return {"path": path, "requested": default_val, "effective": effective,
            "source": "default",
            "ok": bool(found and effective == default_val and not in_overlay)}


def _write_managed_yaml(candidate: Path, name: str, reduced: dict) -> None:
    """Dump the reduced overlay to the candidate with the managed banner on top."""
    body = yaml.safe_dump(reduced, sort_keys=False, allow_unicode=True,
                          default_flow_style=False)
    candidate.write_text(_BANNER.format(name=name) + body, encoding="utf-8")


# ---------------------------------------------------------------------------
# the public write path
# ---------------------------------------------------------------------------

def dials_write(profile: str, op: dict) -> dict:
    """Append one calibration op, reduce over the immutable base, gate, and — only
    when it survives every gate — atomically replace the profile YAML. On a reject
    NOTHING is touched (no ledger append, the YAML byte-identical, no candidate
    left behind). Returns the round-trip proof on success.
    """
    with _DIALS_LOCK:
        name = profile
        profile_path = dials.profile_path(name)          # allowlist / traversal fence
        if not profile_path.is_file():
            return {"ok": False, "error": f"profile {name!r} not found on disk"}

        base = _ensure_base(profile_path, name)      # banks base + archive once
        op = _stamp(op)

        reason = _gate(op)                            # pre-persist gate
        if reason is not None:
            return {"ok": False, "rejected": True, "error": reason}

        ledger_path = _ledger_path(profile_path, name)
        ops = _ledger.read_jsonl(ledger_path) + [op]
        reduced = reduce_overlay(base, ops)

        candidate = _candidate_path(profile_path, name)
        _write_managed_yaml(candidate, name, reduced)
        # the REUSED persist gate: the real loader validates the candidate against
        # the defaults schema exactly as a live run would; its message is ours.
        try:
            dials.load_dials(candidate)
        except ValueError as e:
            candidate.unlink(missing_ok=True)
            return {"ok": False, "rejected": True,
                    "error": f"loader rejected the reduced overlay: {e}"}

        _ledger.append_jsonl(ledger_path, op)
        os.replace(candidate, profile_path)          # atomic

        fresh = dials.load_dials(profile_path)        # round-trip proof
        rt = _round_trip(op, fresh, reduced)
        return {"ok": rt["ok"], "round_trip": rt, "merged": fresh, "overlay": reduced}


def dials_undo(profile: str) -> dict:
    """Drop the last ledger op and re-reduce — undo is truncate + replay (the
    storyboard ``plan_undo`` idiom), gated and atomically replaced like a write."""
    with _DIALS_LOCK:
        name = profile
        profile_path = dials.profile_path(name)
        if not profile_path.is_file():
            return {"ok": False, "error": f"profile {name!r} not found on disk"}
        ledger_path = _ledger_path(profile_path, name)
        base = _ensure_base(profile_path, name)
        ops = _ledger.read_jsonl(ledger_path)
        if not ops:
            return {"ok": False, "error": "nothing to undo"}
        ops = ops[:-1]
        reduced = reduce_overlay(base, ops)

        candidate = _candidate_path(profile_path, name)
        _write_managed_yaml(candidate, name, reduced)
        try:
            dials.load_dials(candidate)
        except ValueError as e:
            candidate.unlink(missing_ok=True)
            return {"ok": False, "error": f"loader rejected the reduced overlay: {e}"}

        ledger_path.write_text(
            "".join(json.dumps(o, ensure_ascii=False) + "\n" for o in ops),
            encoding="utf-8")
        os.replace(candidate, profile_path)
    return {**dials_state(profile), "ok": True, "undone": True}


def _runflip_path(profile_path: Path, name: str) -> Path:
    return profile_path.with_name(name + ".runflip.json")


def _read_runflip(profile_path: Path, name: str) -> dict | None:
    p = _runflip_path(profile_path, name)
    if not p.is_file():
        return None
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) else None
    except (OSError, ValueError):
        return None


def dials_run_flip(profile: str, ops: list[dict], run_id: str) -> dict:
    """A RUN's temporary dial flip as a TRANSACTION — the crash-safe replacement
    for flip-in-run / restore-in-``finally`` (the voiced-run hazard: a session-
    resume kill before the ``finally`` restore leg left the GLOBAL live profile
    flipped, dials restored BY HAND — SESSION_HANDOFF_2026-07-18 §hazards, the
    consolidation's C06/C14).

    The intent record (``<name>.runflip.json``: run_id + the ledger length before)
    banks BEFORE any op applies, so after a kill at ANY point
    :func:`dials_run_restore` mechanically pops the ledger back to the banked
    mark — no byte snapshot, no hand repair, the ledger/YAML invariant intact.
    A rejected op refuses-and-reverts the whole flip (gate honesty). A pending
    unrestored flip refuses a new one (restore first — the recovery door)."""
    name = profile
    profile_path = dials.profile_path(name)
    if not profile_path.is_file():
        return {"ok": False, "error": f"profile {name!r} not found on disk"}
    pending = _read_runflip(profile_path, name)
    if pending is not None:
        return {"ok": False, "error": (
            f"a run-flip is already pending (run {pending.get('run_id')!r}, armed "
            f"{pending.get('armed_at')!r}) — restore it first (POST /dials/run-restore)"),
            "pending_runflip": pending}
    ledger_path = _ledger_path(profile_path, name)
    rec = {"run_id": str(run_id), "armed_at": _stamp({})["ts"],
           "profile": name,
           "ledger_len_before": len(_ledger.read_jsonl(ledger_path)),
           "ops": ops}
    _runflip_path(profile_path, name).write_text(
        json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    applied = 0
    for op in ops:
        # THE ACTOR LAW: a run's temporary flip is attributed to the RUN, never
        # defaulted to his name. A pre-stamped ``by`` (a run that named itself) rides
        # through; otherwise the run_id IS the identity ("run:<id>") — a probe that
        # identifies itself, per the orchestrator ruling.
        flip_op = dict(op)
        if not (isinstance(flip_op.get("by"), str) and flip_op["by"].strip()):
            flip_op["by"] = f"run:{run_id}"
        res = dials_write(name, flip_op)
        if not res.get("ok"):
            restore = dials_run_restore(name)
            return {"ok": False, "rejected": True,
                    "error": f"op {applied + 1}/{len(ops)} refused: "
                             f"{res.get('error')} — flip reverted whole "
                             f"({restore.get('restored', 0)} op(s) undone)",
                    "refused_op": op}
        applied += 1
    return {"ok": True, "run_id": str(run_id), "applied": applied,
            "restore": "POST /dials/run-restore (idempotent, crash-safe)"}


def dials_run_restore(profile: str) -> dict:
    """Restore the profile to its banked pre-flip mark — IDEMPOTENT and callable
    from anywhere (the run's own tail, a recovery wake, the /dials surface): pop
    ledger ops until the length matches ``ledger_len_before``, then clear the
    intent record. No record = nothing pending = a clean no-op."""
    name = profile
    profile_path = dials.profile_path(name)
    rec = _read_runflip(profile_path, name)
    if rec is None:
        return {"ok": True, "restored": 0, "pending": False}
    ledger_path = _ledger_path(profile_path, name)
    target = int(rec.get("ledger_len_before") or 0)
    restored = 0
    while len(_ledger.read_jsonl(ledger_path)) > target:
        res = dials_undo(name)
        if not res.get("ok"):
            return {"ok": False, "restored": restored,
                    "error": f"undo failed mid-restore: {res.get('error')}",
                    "pending_runflip": rec}
        restored += 1
    _runflip_path(profile_path, name).unlink(missing_ok=True)
    return {"ok": True, "restored": restored, "run_id": rec.get("run_id"),
            "pending": False}


def dials_state(profile: str) -> dict:
    """The read surface for the editor: the code defaults, the current reduced
    overlay, the merged effective dials, the ledger tail, and whether a base has
    been banked. Pure read — never mints a sidecar."""
    name = profile
    profile_path = dials.profile_path(name)
    base = _read_base(profile_path, name)
    ledger_path = _ledger_path(profile_path, name)
    ops = _ledger.read_jsonl(ledger_path)
    reduced = reduce_overlay(base, ops)
    merged = dials.load_dials(profile_path) if profile_path.is_file() else _defaults()
    return {
        "profile": name,
        "defaults": _defaults(),
        "overlay": reduced,
        "merged": merged,
        "ops": ops[-50:],
        "base_present": _base_path(profile_path, name).is_file(),
        # an unrestored run-flip surfaces on EVERY state read — the recovery door
        # is visible wherever the dials are (never a silent hand-repair hazard)
        "pending_runflip": _read_runflip(profile_path, name),
    }


# ---------------------------------------------------------------------------
# the HTTP handler (analytics/storyboard contract)
# ---------------------------------------------------------------------------

def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, default)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else default
    return (v or default).strip()


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/dials*`` write/state request. Returns (status, content_type,
    body), or ``None`` when the path is not ours so the scanner can 404 (the
    ``GET /dials`` page itself is a later wiring packet — unowned here).

      * ``GET  /dials/state?profile=`` -> :func:`dials_state`
      * ``POST /dials/op``   {profile?, kind, path, value?} -> :func:`dials_write`
      * ``POST /dials/undo`` {profile?} -> :func:`dials_undo`
    """
    if not path.startswith("/dials/"):
        return None
    method = (method or "GET").upper()

    if path == "/dials/state" and method == "GET":
        profile = _q1(query, "profile") or _DEFAULT_PROFILE
        try:
            return _json_resp(200, dials_state(profile))
        except dials.DialsProfileError as e:
            return _json_resp(400, {"error": str(e)})

    if path == "/dials/op" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        if not isinstance(payload, dict):
            return _json_resp(400, {"error": "op body must be an object"})
        # THE ACTOR LAW (orchestrator ruling 2026-07-22) — the same guard as the
        # desk's /desk/act and the superego's actor guard: a dial edit is
        # actor-attributed and this door defaults NOWHERE. An unattributed request
        # (an audit drive, a walk, a probe that never named itself) must never write
        # — and his name is never a default. Callers on his surfaces pass him
        # explicitly on his confirmed act; probes/walks pass their own identity.
        by = (payload.get("by") or "").strip() if isinstance(payload.get("by"), str) else ""
        if not by:
            return _json_resp(422, {"error": "by (explicit actor) is required: a dial "
                                    "edit is actor-attributed and this door defaults "
                                    "nowhere — an unattributed request must never write, "
                                    "and his name is never a default (a probe/walk must "
                                    "identify itself)"})
        profile = payload.get("profile") or _q1(query, "profile") or _DEFAULT_PROFILE
        op = {k: v for k, v in payload.items() if k != "profile"}
        op["by"] = by
        try:
            res = dials_write(profile, op)
        except dials.DialsProfileError as e:
            return _json_resp(400, {"error": str(e)})
        return _json_resp(200 if res.get("ok") else 422, res)

    if path == "/dials/undo" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            payload = {}
        profile = (payload.get("profile") if isinstance(payload, dict) else None) \
            or _q1(query, "profile") or _DEFAULT_PROFILE
        try:
            res = dials_undo(profile)
        except dials.DialsProfileError as e:
            return _json_resp(400, {"error": str(e)})
        return _json_resp(200 if res.get("ok") else 400, res)

    if path == "/dials/run-flip" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        if not isinstance(payload, dict) or not isinstance(payload.get("ops"), list):
            return _json_resp(400, {"error": "body must be {profile?, run_id, ops: [...]}"})
        profile = payload.get("profile") or _q1(query, "profile") or _DEFAULT_PROFILE
        try:
            res = dials_run_flip(profile, payload["ops"],
                                 str(payload.get("run_id") or "unnamed-run"))
        except dials.DialsProfileError as e:
            return _json_resp(400, {"error": str(e)})
        return _json_resp(200 if res.get("ok") else 409, res)

    if path == "/dials/run-restore" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            payload = {}
        profile = (payload.get("profile") if isinstance(payload, dict) else None) \
            or _q1(query, "profile") or _DEFAULT_PROFILE
        try:
            res = dials_run_restore(profile)
        except dials.DialsProfileError as e:
            return _json_resp(400, {"error": str(e)})
        return _json_resp(200 if res.get("ok") else 500, res)

    return None
