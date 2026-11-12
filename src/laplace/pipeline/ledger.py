"""The one ledger engine — append-only JSONL mechanics shared by both ledgers.

``storyboard.py`` grew a verbatim mirror of ``corpus_ingest``'s ledger IO (its
own read/append/reduce, admitted at storyboard.py's plan-ledger banner). This
module is the single implementation both delegate to. It owns MECHANICS only:
tolerant reads, appends, fold-reduction, the freeze snapshot, and the atomic
dual-ledger transaction. The FOLD FUNCTIONS — what an op means — stay where the
domain lives: ``corpus_ingest.apply_overlay``/``friction_current`` for L1,
``storyboard._apply_op`` for L2.

The transaction is the drift-killer: the two-ledger split (L1 substrate, L2
plan) drifts exactly when a script writes one ledger without its mirror. An
operator that appends to both inside one :func:`transaction` either lands whole
or truncates back to the recorded byte offsets — append-only stays true (a
rollback removes only the operator's own suffix, never a human record).
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from filelock import FileLock

PHYSICAL_STORE_INTEGRITY = "physical-store-integrity"
_RESIDUAL_STRING_CAP = 240


def is_physical_store_defect(diagnostic: dict) -> bool:
    """Typed class test shared by every completeness-sensitive consumer."""

    return diagnostic.get("integrity_class") == PHYSICAL_STORE_INTEGRITY


def _physical_diagnostic(**fields: Any) -> dict:
    return {"integrity_class": PHYSICAL_STORE_INTEGRITY, **fields}


def _bytes_handle(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# IO mechanics (the previously-duplicated pair)
# ---------------------------------------------------------------------------

def read_jsonl_diagnosed(path: Path | str, *, store: str | None = None,
                         required: bool = False
                         ) -> tuple[list[dict], list[dict]]:
    """Read one append-only JSONL store and retain every integrity residual.

    The rows are deliberately *partial* when one line is poisoned: read-only
    surfaces can still show the known lower-bound projection, but the returned
    diagnostics prevent them from presenting it as complete.  Mutation doors
    and gates consume the same diagnostics and can therefore fail closed.

    A missing store is the clean empty state used by projects that have not
    minted a ledger yet *unless* ``required`` names it as an established authority.
    Required absence and dangling symlinks are wounds, never empty accounts.  A path that
    exists but cannot be read is wounded.
    ``store`` supplies the stable logical name used by higher-level accounts;
    the physical path is retained beside it for exact repair.
    """
    p = Path(path)
    if not p.exists():
        if required:
            kind = "dangling symlink" if p.is_symlink() else "missing path"
            return [], [_physical_diagnostic(
                defect="store-unreadable", store=store or str(p), path=str(p),
                source_handle=None,
                error=f"required JSONL store does not exist ({kind})",
            )]
        return [], []
    label = store or str(p)
    if not p.is_file():
        return [], [_physical_diagnostic(
            defect="store-unreadable", store=label, path=str(p), source_handle=None,
            error="path exists but is not a file",
        )]
    try:
        source_bytes = p.read_bytes()
    except OSError as exc:
        return [], [_physical_diagnostic(
            defect="store-unreadable", store=label, path=str(p), source_handle=None,
            error=f"{type(exc).__name__}: {exc}",
        )]
    source_handle = _bytes_handle(source_bytes)
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeError as exc:
        return [], [_physical_diagnostic(
            defect="store-unreadable", store=label, path=str(p),
            source_handle=source_handle, source_handle_kind="exact-store-bytes",
            error=f"{type(exc).__name__}: {exc}",
        )]
    out: list[dict] = []
    diagnostics: list[dict] = []
    for lineno, raw_line in enumerate(text.splitlines(keepends=True), start=1):
        line = raw_line.strip()
        if line:
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as exc:
                diagnostics.append(_physical_diagnostic(
                    defect="unparseable-row", store=label,
                    path=str(p), line=lineno, id=f"line {lineno}",
                    source_handle=_bytes_handle(raw_line.encode("utf-8")),
                    source_handle_kind="exact-jsonl-line-bytes",
                    error=f"{type(exc).__name__}: {exc}",
                ))
                logging.getLogger(__name__).warning(
                    "read_jsonl: poisoned line %d in %s skipped", lineno, p)
                continue
            if not isinstance(decoded, dict):
                diagnostics.append(_physical_diagnostic(
                    defect="non-object-row", store=label,
                    path=str(p), line=lineno, id=f"line {lineno}",
                    source_handle=_bytes_handle(raw_line.encode("utf-8")),
                    source_handle_kind="exact-jsonl-line-bytes",
                    error=f"decoded {type(decoded).__name__}, expected JSON object",
                ))
                logging.getLogger(__name__).warning(
                    "read_jsonl: non-object line %d in %s skipped", lineno, p)
                continue
            out.append(decoded)
    return out, diagnostics


def integrity_projection(diagnostics: Iterable[dict], *, cap: int = 12) -> dict:
    """Bounded, fidelity-preserving surface form of typed integrity wounds.

    A pathological store may contain millions of damaged lines; copying every
    diagnostic into a first-paint or wake payload would let corruption defeat the
    interface's own bounds.  The projection therefore carries a deterministic
    prefix, the total/omitted counts, and a digest of the *whole* logical residual
    set.  Mutation code still consumes the unbounded internal list and fails closed.
    """
    rows = [dict(d) for d in diagnostics]
    n = len(rows)
    cap = max(0, int(cap))
    # ``path`` is repair context, not wound identity.  Hashing an absolute clone path
    # made byte-identical corruption acquire different residual handles on two seats.
    # The portable identity retains the logical store, exact source handle, row/field
    # coordinates and error class while replacing the physical path inside messages.
    portable_rows: list[dict] = []
    for raw in rows:
        identity = {k: v for k, v in raw.items() if k != "path"}
        physical_path = raw.get("path")
        if isinstance(physical_path, str) and physical_path:
            store = identity.get("store")
            if isinstance(store, str) and store == physical_path:
                identity["store"] = Path(store).name
            error = identity.get("error")
            if isinstance(error, str):
                identity["error"] = error.replace(physical_path, "$PATH")
        portable_rows.append(identity)
    encoded = json.dumps(portable_rows, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), default=str).encode("utf-8")
    surface_rows: list[dict] = []
    allowed = {
        "defect", "integrity_class", "store", "path", "line", "id", "error",
        "field", "source_handle", "source_handle_kind",
    }
    for raw in rows[:cap]:
        row: dict[str, Any] = {}
        for key in sorted(allowed.intersection(raw)):
            value = raw[key]
            if isinstance(value, str) and len(value) > _RESIDUAL_STRING_CAP:
                row[key] = value[:_RESIDUAL_STRING_CAP - 1] + "…"
                row[key + "_truncated"] = True
                row[key + "_sha256"] = _bytes_handle(value.encode("utf-8"))
            else:
                row[key] = value
        omitted_fields = len(set(raw) - allowed)
        if omitted_fields:
            row["fields_omitted"] = omitted_fields
        surface_rows.append(row)
    return {
        "cracked": bool(rows),
        "count_is_lower_bound": bool(rows),
        "residual_count": n,
        "residuals": surface_rows,
        "residuals_truncated": n > cap,
        "residuals_omitted": max(0, n - cap),
        "residual_handle": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "residual_handle_scope": (
            "complete typed diagnostics plus their declared source content handles; "
            "physical repair paths excluded so the name is clone-portable; physical "
            "absence has no source bytes"
        ),
    }


def read_jsonl_counted(path: Path | str, *, required: bool = False
                       ) -> tuple[list[dict], int]:
    """Compatibility projection of :func:`read_jsonl_diagnosed`.

    The count is the number of malformed physical rows (unparseable or a valid JSON
    non-object), preserving the compatibility contract. New integrity-sensitive callers consume the
    diagnosed form so an unreadable store cannot collapse to a clean zero.
    """
    records, diagnostics = read_jsonl_diagnosed(path, required=required)
    unreadable = next((d for d in diagnostics
                       if d.get("defect") == "store-unreadable"), None)
    if unreadable is not None:
        # Preserve the legacy contract: row-only callers have nowhere to carry
        # a physical read wound, so silence would be a false clean empty.  The
        # diagnosed API is the path for partial reads with explicit residuals.
        raise OSError(str(unreadable.get("error") or "JSONL store unreadable"))
    dropped = sum(1 for d in diagnostics if d.get("defect") != "store-unreadable")
    return records, dropped


def read_jsonl(path: Path | str, *, required: bool = False) -> list[dict]:
    """All records in an append-only ledger; bad lines are skipped, never fatal
    (one poisoned record must not take down the reduction)."""
    records, diagnostics = read_jsonl_diagnosed(path, required=required)
    unreadable = next((d for d in diagnostics
                       if d.get("defect") == "store-unreadable"), None)
    if unreadable is not None:
        raise OSError(str(unreadable.get("error") or "JSONL store unreadable"))
    return records


def finding_id(rec: dict) -> str:
    """The stable id for one finding/record — the SINGLE derivation the whole engine
    shares (``verdict_io._finding_id`` delegates here; the live view and the pour use
    it). Carries an ``id``/``fingerprint``/``finding_id`` the record already exposes;
    otherwise derives a content fingerprint over the routing-stable key
    (reader|kind|where|issue), reproducible round-to-round for unchanged content.

    Why it exists: a record poured with ``id: null`` is UNADDRESSABLE — the supersede
    mechanics reference a record by its id, so a null-id finding can never be retired
    (it is a permanent zombie in every live worklist). Assigning a deterministic id
    is what makes such a finding correctable; rejecting it would drop a real reader
    finding. So the engine's law is: every live finding HAS an id — repaired here when
    the pour left it null."""
    for k in ("id", "fingerprint", "finding_id"):
        v = rec.get(k)
        if v:
            return str(v)
    # lazy import: suppress imports THIS module (append_jsonl/read_jsonl), so a
    # module-level import would cycle. content_fingerprint is sha256-stable across
    # processes, so the derived id matches wherever the same content is read.
    from laplace.pipeline.suppress import content_fingerprint
    key = "|".join(str(rec.get(x, "")) for x in ("reader", "kind", "where", "issue"))
    return content_fingerprint(key)


def live_findings(records: list[dict],
                  panel_prefix: str = "mech-panel:") -> list[dict]:
    """The LIVE view of a findings ledger: every non-panel record, plus panel
    records from only the LATEST panel round present. The mechanical panel is a
    full re-scan each round - still-unfixed findings re-appear in the newest
    round's records, so older panel rounds are history; keeping them multiplies
    dispatch and pollutes every consumer's worklist view (measured 2026-07-10:
    27 caption regens for 9 captions after two rounds; a storyboard worklist of
    705 on a residue of 2). One definition, every consumer: the route fixer,
    propagate, the storyboard/review surfaces.

    Ids are MANDATORY at this boundary: a record surfacing with ``id: null`` is
    stamped its deterministic :func:`finding_id` (the read-side twin of the pour's
    id law). A null-id finding is unaddressable — it can never be superseded, so it
    would haunt every consumer's worklist forever; stamping it here makes the shared
    live view uniformly addressable (and lets an anchored re-pour supersede a legacy
    id-less original)."""
    def _round(rec: dict) -> int | None:
        src = str(rec.get("source", ""))
        if not src.startswith(panel_prefix):
            return None
        part = src[len(panel_prefix):]
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            elif digits:
                break
        return int(digits) if digits else None

    rounds = [r for r in (_round(rec) for rec in records) if r is not None]
    latest = max(rounds) if rounds else None
    out: list[dict] = []
    for rec in records:
        if _round(rec) is not None and _round(rec) != latest:
            continue
        if not rec.get("id"):
            rec = {**rec, "id": finding_id(rec)}       # repair id:null (never mutate the source)
        out.append(rec)
    return out


def append_jsonl(path: Path | str, record: dict, *,
                 precondition: Callable[[], dict | None] | None = None) -> dict | None:
    """Append one record. The ledgers are append-only by law; this is the only
    write shape the engine offers.

    The write is serialised across processes by a sidecar ``FileLock`` (``<path>
    .lock``, mirroring ``locking.canon_lock``'s shape). Concurrent appenders — the
    author's own editor plus a drained remote inbox, or N browser tabs on his
    offline Windows box — would otherwise interleave a half-written line and
    poison the ledger. The critical section is one ``write`` of one line, so
    contention clears in microseconds; the bounded ``timeout`` means a genuinely
    stuck lock raises ``filelock.Timeout`` instead of hanging forever.

    A canonical owner may supply a read-only ``precondition``.  It runs inside
    the same append lock immediately before bytes are written, closing the gap
    between an optimistic revision read and the authoritative append.  A
    returned object refuses the append and is returned to the owner unchanged.
    """
    # WO-20260821-composed-bypassed-at-bank: the organ that frames records for HIS reading
    # (composed.validate_composed) used to be bypassed by construction - never invoked on
    # this, the write shape every close uses. ADVISORY-LOUD, never blocking: an invalid
    # frame banks anyway (a mid-close bank must not die on a framing nit) but says so on
    # stderr, so the gap is a line in the log instead of a silence.
    if isinstance(record.get("composed"), dict):
        try:
            from laplace.pipeline.composed import validate_composed
            validate_composed(record["composed"])
        except ValueError as exc:
            import sys as _sys
            print(f"[ledger] COMPOSED INVALID (advisory - banked anyway, never blocks a "
                  f"mid-close bank): {exc}", file=_sys.stderr, flush=True)
        except Exception:  # noqa: BLE001 - the advisory must never be the failure
            pass
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(p) + ".lock", timeout=10):
        if precondition is not None:
            refusal=precondition()
            if refusal:return refusal
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return None


def pour_finding(path: Path | str, finding: dict, *, section: str | None = None,
                 project: str = "", source: str = "reader") -> dict:
    """The sanctioned reader→ledger write shape: ids MANDATORY, the section anchor
    STAMPED. This is the plain pour the shakedown reader bypassed (it appended raw
    reader findings with ``id: null`` and no anchor, which the live worklist then
    surfaced as unsupersedable, section-less ``None`` work items).

    - **id**: a finding arriving with ``id: null`` is REPAIRED — assigned its
      deterministic :func:`finding_id` (rejecting would drop a real finding, and the
      supersede mechanics need an id to ever retire it; a repaired-but-addressable
      finding is strictly better than a lost one).
    - **section**: stamped from the explicit ``section`` arg, the finding's own
      ``section``/``anchor.section``, or a LEADING ``N<k>`` location token in the
      finding's ``where`` (:func:`sealed.section_from_where`). A finding with no
      locatable section is REFUSED (``ValueError``) — a section-less pour is exactly
      the dishonesty this closes; the reader must anchor it first.
    - **idempotent** (bite-zero-judge, Leg A): the finding_id is DETERMINISTIC
      (content-derived when the finding carries no id), so re-pouring the same
      finding — a reader that re-fires the same round, a re-detect that re-surfaces
      an unfixed fault — would otherwise deposit a SECOND live record sharing the
      one id (a "double-live": two rows the supersede mechanics can never tell
      apart). So before appending, the ledger is scanned for a LIVE record already
      carrying this id (present, not superseded, not resolved); when one exists the
      pour is a NO-OP and the existing record is returned. A resolved/superseded
      prior with the same id does NOT block — a recurred fault re-opens plainly.

    Returns the stamped record (the freshly appended one, or the existing live twin
    on an idempotent no-op)."""
    rec = dict(finding)
    rec["id"] = finding_id(rec)
    sec = (section or rec.get("section")
           or (rec.get("anchor") or {}).get("section") or "").strip()
    if not sec:
        from laplace.pipeline.readers.sealed import section_from_where
        sec = section_from_where(rec.get("where") or "") or ""
    if not sec:
        raise ValueError(
            f"reader pour refused: finding {rec['id']!r} has no locatable section "
            "(no section, anchor.section, or leading N-token in `where`) — a "
            "section-less pour becomes an unroutable None-section work item; anchor "
            "it before pouring")
    rec["section"] = sec
    anchor = dict(rec.get("anchor") or {})
    anchor.setdefault("section", sec)
    rec["anchor"] = anchor
    if project:
        rec.setdefault("project", project)
    rec.setdefault("source", source)

    # idempotence: skip the append when a LIVE record with this id already exists.
    existing = read_jsonl(path)
    superseded = {r.get("supersedes") for r in existing if r.get("supersedes")}
    for r in existing:
        if (finding_id(r) == rec["id"]
                and r.get("id") not in superseded
                and (r.get("status") or "open") != "resolved"):
            return r                                # already live — no double-live

    append_jsonl(path, rec)
    return rec


def reduce(base: dict, ops: Iterable[dict], fold: Callable[[dict, dict], None]) -> dict:
    """The current state = the base with the ledger folded over it, in order.
    Pure: a deep copy is mutated, the base is never touched. ``fold(state, op)``
    mutates in place and must skip unknown/malformed ops rather than raise."""
    state = copy.deepcopy(base)
    for op in ops:
        fold(state, op)
    return state


# ---------------------------------------------------------------------------
# The freeze — must_exist_before_mutation, mechanised
# ---------------------------------------------------------------------------

def freeze(paths: Iterable[Path | str], archive_dir: Path | str,
           label: str = "freeze") -> Path:
    """Snapshot the given ledger/plan files into a stamped directory under
    ``archive_dir`` and return it. This is the `_preboard_snapshot` step the
    evolutions hand-ran, as one call. Missing files are recorded, not fatal."""
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    dest = Path(archive_dir) / f"{label}_{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"label": label, "stamp": stamp, "files": {}, "dropped_n": 0}
    for src in paths:
        sp = Path(src)
        if sp.is_file():
            # flatten the name; the manifest keeps the true origin
            target = dest / sp.name
            shutil.copy2(sp, target)
            # count (not re-read) the poisoned lines banked into this snapshot,
            # so a lossy freeze is visible in the metadata rather than silent
            _records, dropped = read_jsonl_counted(sp)
            manifest["files"][str(sp)] = {"copied_as": sp.name,
                                          "bytes": sp.stat().st_size,
                                          "dropped": dropped}
            manifest["dropped_n"] += dropped
        else:
            manifest["files"][str(sp)] = {"missing": True}
    (dest / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# The transaction — both ledgers or neither
# ---------------------------------------------------------------------------

class Transaction:
    """Scoped, append-only-safe rollback across one or more JSONL ledgers.

    On entry the byte offset of every managed file is recorded. If the body
    raises, every file is truncated back to its recorded offset (a file the
    transaction itself created is removed). On success a ``txn`` journal record
    is appended to each ledger that grew — reducers ignore unknown kinds, so the
    journal is a pure audit trail (the same pass-through class as the observed
    ``data``/``schematic`` records).
    """

    def __init__(self, *ledgers: Path | str, by: str = "pipeline",
                 note: str = "", journal: bool = True):
        self.ledgers = [Path(p) for p in ledgers]
        self.by, self.note, self.journal = by, note, journal
        self._marks: dict[Path, int | None] = {}

    def __enter__(self) -> "Transaction":
        for p in self.ledgers:
            self._marks[p] = p.stat().st_size if p.is_file() else None
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            for p, mark in self._marks.items():
                if mark is None:
                    p.unlink(missing_ok=True)          # we created it: remove
                elif p.is_file() and p.stat().st_size > mark:
                    with p.open("r+b") as fh:
                        fh.truncate(mark)              # only our suffix goes
            return False                               # re-raise
        if self.journal:
            for p, mark in self._marks.items():
                grew = p.is_file() and p.stat().st_size > (mark or 0)
                if grew:
                    append_jsonl(p, {
                        "id": _dt.datetime.now().strftime("TX-%Y%m%d-%H%M%S-%f"),
                        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
                        "kind": "txn", "by": self.by, "note": self.note,
                        "from_byte": mark or 0,
                    })
        return False


def transaction(*ledgers: Path | str, by: str = "pipeline", note: str = "",
                journal: bool = True) -> Transaction:
    """``with transaction(l1, l2, by="evolve", note="v2->v3"): ...`` — the only
    sanctioned way an operator writes both ledgers."""
    return Transaction(*ledgers, by=by, note=note, journal=journal)
