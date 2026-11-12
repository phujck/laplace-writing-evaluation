"""Bodies: content-addressed public body references, their codec, retention, bounded reads and resolution.

  REFERENCE_SCHEMA         the public body-reference wire contract, laplace.writing-public-body-ref/1 (a historical
                           name kept exactly: every banked reference carries it)
  is_reference / require_reference / validate_references
                           recognition (tolerant of a mis-spelled family), the exact version gate, and the gate at
                           any depth of ordinary JSON
  encode                   a body's bytes: core.identity.canonical_bytes, so one text is one body whichever field
                           carried it
  reference / reference_bytes
                           a reference's shape, and its own encoded size (computed, never tuned)
  retain / retain_leaves   put a value, or every large leaf of a container, through an owner's put; a failed put
                           keeps the value inline and records a bounded diagnostic
  read_bytes / resolve     read one reference with its declared size charged first, and resolve references at
                           every depth, keeping unavailable ones with a typed error
  budget / active_budget / charge / BudgetExceeded
                           the invocation-local byte budget every body read at every depth charges; absent by default
  operation / degradation / current_operation / record_failure
                           the invocation-local diagnostic of failed retention (laplace.writing-custody-degradation/1)

The owner supplies the policy: which store (a concrete object with put/get/has), its name in references, what a
non-local reference may fall back to, which fields of which rows are bodies. Writing's policy is laplace.representation.writing_bodies,
over Atlas BlobStore at contract/writing_bodies (laplace.representation.writing_representation). Nothing here imports a domain,
selects a store or root, or has an import-time effect.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from laplace.core.identity import canonical_bytes, require_schema_version

REFERENCE_SCHEMA = "laplace.writing-public-body-ref/1"
_REFERENCE_FAMILY = REFERENCE_SCHEMA.rsplit("/", 1)[0]
ENCODING = "application/json"
DEGRADATION_SCHEMA = "laplace.writing-custody-degradation/1"

encode = canonical_bytes


def is_reference(value) -> bool:
    if not isinstance(value, Mapping):
        return False
    tag = value.get("schema_version")
    # Recognition may catch malformed spelling, but the version gate below
    # still compares the original exact declaration; it never normalizes it.
    marker = tag.strip().casefold() if isinstance(tag, str) else ""
    return marker == _REFERENCE_FAMILY or marker.startswith(_REFERENCE_FAMILY + "/")


def require_reference(value):
    return require_schema_version(value, (REFERENCE_SCHEMA,), owner="Saved writing public-body reference")


def validate_references(value) -> None:
    """Validate only this reserved family at any depth, preserving ordinary JSON."""
    if isinstance(value, Mapping):
        if is_reference(value):
            require_reference(value)
        else:
            for child in value.values():
                validate_references(child)
    elif isinstance(value, list):
        for child in value:
            validate_references(child)


def reference(handle: str, store: str, size: int) -> dict:
    return {"schema_version": REFERENCE_SCHEMA, "content_handle": handle, "store": store, "bytes": size, "encoding": ENCODING}


def reference_bytes(store: str) -> int:
    """The encoded size of one reference into ``store``: below it, a second inline copy is the cheaper durable form."""
    return len(encode(reference("sha256:" + "0" * 64, store, 0)))


# ---------------------------------------------------------------- invocation-local budget and diagnostics

_BUDGET = ContextVar("laplace_body_budget", default=None)
_OPERATION = ContextVar("laplace_body_operation", default=None)


class BudgetExceeded(ValueError):
    """A read that would take an invocation past its declared byte budget; raised BEFORE the bytes are read."""


@contextmanager
def budget(limit=None):
    """Yield this invocation's ledger {limit, spent, reads, read_bytes}: ``limit`` None observes only. A nested call
    joins the active ledger, so one invocation has one budget whatever owner it passes through."""
    current = _BUDGET.get()
    if current is not None:
        yield current
        return
    ledger = {"limit": limit, "spent": 0, "reads": 0, "read_bytes": 0}
    token = _BUDGET.set(ledger)
    try:
        yield ledger
    finally:
        _BUDGET.reset(token)


def active_budget():
    """The ledger of the invocation in progress, or None."""
    return _BUDGET.get()


def charge(ledger, size, what):
    """Count ``size`` bytes against the ledger, refusing first when the budget cannot hold them."""
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError("custody reference size is malformed")
    if ledger["limit"] is not None and ledger["spent"] + size > ledger["limit"]:
        raise BudgetExceeded("Reading %s (%d bytes) would exceed this invocation's %d-byte budget (%d spent)."
                             % (what, size, ledger["limit"], ledger["spent"]))
    ledger["spent"] += size


def degradation():
    return {"schema_version": DEGRADATION_SCHEMA, "status": "INLINE_RETAINED", "failed_attempts": 0,
            "inline_bytes": 0, "identities": [], "identities_omitted": 0}


@contextmanager
def operation():
    """Collect only this invocation's bounded diagnostics, including nested owners."""
    current = _OPERATION.get()
    if current is not None:
        yield current
        return
    diagnostic = degradation()
    token = _OPERATION.set(diagnostic)
    try:
        yield diagnostic
    finally:
        _OPERATION.reset(token)


def current_operation():
    """The diagnostic of the invocation in progress, or None."""
    return _OPERATION.get()


def record_failure(diagnostic, raw: bytes, error: BaseException) -> None:
    """Count one failed retention on ``diagnostic`` and the invocation's: a sanitized reason and digest only, never
    the payload, at most eight identities each."""
    reason = getattr(error, "reason", type(error).__name__)
    if not isinstance(reason, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", reason):
        reason = type(error).__name__[:80]
    identity = {"reason": reason}
    detail = getattr(error, "detail", {})
    key = detail.get("key") if isinstance(detail, dict) else None
    if isinstance(key, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", key):
        identity["content_handle"] = key
    current = _OPERATION.get()
    targets = (diagnostic,) if diagnostic is current else (diagnostic, current)
    for target in targets:
        if target is None:
            continue
        target["failed_attempts"] += 1
        target["inline_bytes"] += len(raw)
        if identity not in target["identities"]:
            if len(target["identities"]) < 8:
                target["identities"].append(identity)
            else:
                target["identities_omitted"] += 1


# ---------------------------------------------------------------- retention

def retain(put: Callable[[bytes], str], store: str, raw: bytes, diagnostic) -> dict | None:
    """Put ``raw`` and return its reference; on any failure record it and return None (the caller keeps it inline)."""
    try:
        handle = put(raw)
    except Exception as error:
        record_failure(diagnostic, raw, error)
        return None
    return reference(handle, store, len(raw))


def retain_leaves(put: Callable[[bytes], str], store: str, value: Any, texts: tuple[str, ...] = (), key: str | None = None,
                  *, min_bytes: int, diagnostic=None) -> Any:
    """Put every large leaf of a container through ``put``, in place.

    The unit of retention is the thing that is large: a text, not the dict that carries it, so one text is one body
    whichever container carried it. ``texts`` names the leaves that ARE such a text; they are retained whenever a
    reference is smaller than the text. Any other leaf is retained above ``min_bytes``. Existing references pass
    through after their version gate.
    """
    if isinstance(value, Mapping):
        if is_reference(value):
            require_reference(value)
            return value
        return {name: retain_leaves(put, store, item, texts, name, min_bytes=min_bytes, diagnostic=diagnostic)
                for name, item in value.items()}
    if isinstance(value, list):
        return [retain_leaves(put, store, item, texts, key, min_bytes=min_bytes, diagnostic=diagnostic) for item in value]
    if not isinstance(value, str):
        return value
    raw = encode(value)
    if len(raw) <= (reference_bytes(store) if key in texts else min_bytes):
        return value
    held = retain(put, store, raw, diagnostic)
    return value if held is None else held   # the full inline leaf is the fail-safe durable representation


# ---------------------------------------------------------------- bounded reads and resolution

def read_bytes(value: Mapping[str, Any], local: Callable[[], Any] | None, *, store: str,
               fallback: Callable[[str], bytes] | None = None,
               local_required: str = "a local store is required to read this body") -> bytes:
    """Read one reference's exact bytes.

    The declared size is charged to the active budget before anything is read, and a budgeted read passes that size
    as the store's bound. A reference into ``store`` reads ``local()``; any other reads ``local()`` when it holds the
    handle, else ``fallback(handle)``, which a finite budget refuses before calling (it cannot be read within a
    bound). The bytes read must match the declared size.
    """
    require_reference(value)
    handle = value.get("content_handle")
    ledger = _BUDGET.get()
    if ledger is not None:
        charge(ledger, value.get("bytes"), "custody body " + str(handle)[:24])
    # only a budgeted read passes the bound, so a default read is the unchanged call (an installed store may predate it)
    bounded = {"max_bytes": value.get("bytes")} if ledger is not None else {}
    if value.get("store") == store:
        if local is None:
            raise ValueError(local_required)
        raw = local().get(str(handle), **bounded)
    else:
        held = local() if local is not None else None
        if held is not None and held.has(str(handle)):
            raw = held.get(str(handle), **bounded)
        else:
            if ledger is not None and ledger["limit"] is not None:
                raise BudgetExceeded("Custody body %s is not in this repository's body store; its nonlocal fallback "
                                     "cannot be read within this invocation's %d-byte budget, so it is refused before "
                                     "any of it is read." % (str(handle)[:24], ledger["limit"]))
            if fallback is None:
                raise ValueError("custody body %s is not in the local store and has no fallback" % str(handle)[:24])
            raw = fallback(str(handle))
    if len(raw) != value.get("bytes"):
        raise ValueError("custody byte count mismatch")
    if ledger is not None:
        ledger["reads"] += 1
        ledger["read_bytes"] += len(raw)
    return raw


def resolve(value: Any, read: Callable[[Mapping[str, Any]], bytes], errors: list, field: str) -> Any:
    """Resolve references at EVERY depth (a retained leaf may sit inside a retained container). An unavailable,
    corrupt or unsupported reference stays in place with a typed error; a budget refusal stops the invocation."""
    if isinstance(value, Mapping):
        if is_reference(value):
            try:
                require_reference(value)
                return resolve(json.loads(read(value)), read, errors, field)
            except BudgetExceeded:
                raise
            except Exception as exc:
                errors.append({"field": field, "content_handle": value.get("content_handle"), "error": str(exc)})
                return value
        return {key: resolve(item, read, errors, field) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, read, errors, field) for item in value]
    return value
