"""residue.py - the typed remainder of an UP act: what the coarse object could not carry.

THE LAW THIS IMPLEMENTS, plainly, once. Consolidation is a surjection ``C`` from the fine layer
to the coarse one; the fibre ``C^{-1}(m)`` is what the coarse handle ``m`` erases. The obstruction
is ``O = C·G_mu - G_M·C`` (``corpus_friction/law-of-laws.jsonl``, ``eq:obstruction``): fine
evolution first, then consolidate, against consolidate first, then evolve in the coarse
generator - zero exactly when the square commutes. ``eq:obstruction-composition`` adds the part
that makes it worth banking: obstructions compose as a 1-COCYCLE across scales, so a descent's
failure accumulates like curvature and not like a scalar error. A per-grade remainder is
therefore not a diagnostic to be summed and forgotten; it is the single-step cochain, and it must
be typed, per grade and per axis, or the composite cannot be formed at all.

WHY IT EXISTS AT ALL. DOWN fails by MISSING, which is visible - the reconstruction is checkable
against a world that already exists. UP fails by VACUOUS RIGHTNESS, which is silent: a bad
consolidation reads fluently forever, and any signal derived from reconstruction success goes
constant exactly where DOWN works (``NOTE-20260821-the-up-challenge-articulated``; the closure
residual measured constant over all 54 skills). So UP gets no endogenous residual for free. This
store is the deliberate substitute: every UP act NAMES its remainder from a closed vocabulary at
the moment it discards something, rather than being scored afterwards by a proxy it can satisfy
without consolidating anything.

WHAT THIS MODULE IS NOT. It carries no threshold and no fitness verdict. Whether a magnitude is
acceptable - phi, the promote/deprecate bar - is HIS
(``WO-20260821-residual-thresholds-uncalibrated``, ``M-proxies-stay-in-jurisdiction``: choosing
the grade's metric IS the consolidation act, so the criterion is exogenous and taste-laden by
construction). It also does not compose the cocycle: the transport map between grades is not
declared, so the store banks the single-step obstructions and ``aggregate`` sums them WITHIN a
grade only. Composing across grades is a later act with a declared transport, not a sum this
reader is entitled to take.

THE VOCABULARY IS CLOSED. ``REMAINDER_KINDS`` is the whole of it, and ``build_row`` refuses
anything else. That is the point of typing: one failure vocabulary for both sides of the atlas
marriage, so the semantic fold's dropped cluster and a synthetic world's unrecovered generator
term are the same KIND of object and can be read against each other. A producer that needs a new
kind adds it here, once, with its unit - it never invents one at the call site.

THE STORE. ``.residue.jsonl`` at the repo root, append-only, one row per typed remainder, in the
shape of the sibling dot-store ledgers (``.closure_meter.jsonl``, ``.wire_verdicts.jsonl``): an
ISO-8601 UTC ``ts`` per row as a LABEL, with append order as the ordering. Rows travel; a banked
remainder is accumulated evidence about the engine's own consolidations, not a local instrument.

DEGRADE LOUD, NEVER FATAL. An UP act must never lose its answer because its bookkeeping could not
be written: ``bank`` catches everything and costs one stderr line. ``append_rows`` is the raising
form for callers that want the failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STORE_FILE = ".residue.jsonl"
SCHEMA = "residue/v1"
ENV_DISABLE = "LAPLACE_RESIDUE"   # "0"/"off"/"false"/"no" kills the banking outright

# How many ids ride a row. The count `n` is always exact; the id list is a HANDLE list, so a
# remainder covering ten thousand leaves does not turn one row into a megabyte. Truncation is
# stated in `detail.ids_truncated` rather than left for a reader to infer from a round number.
IDS_CAP = 32

# ---------------------------------------------------------------------------
# the closed vocabulary: kind -> (unit, what the magnitude means)
#
# General across grades and axes by construction - each kind names a way a coarse layer can fail
# to carry its fine layer, in terms no particular UP act owns. The semantic fold, a structural
# upfold, and a synthetic world's inverted generator all type their remainders from this list.
# ---------------------------------------------------------------------------
REMAINDER_KINDS: dict[str, tuple[str, str]] = {
    "uncarried_mass": (
        "cosine_distance",
        "The fibre's spread: how far the fine items sit from the coarse representative that now "
        "stands for them, summed over the items the act placed. The direct C-fibre residual - "
        "what the coarse handle does not reproduce about its own members."),
    "unplaced": (
        "items",
        "Fine items no coarse handle claimed. The act had no representation for them at all, so "
        "they hang from the layer above unconsolidated."),
    "dropped_handle": (
        "handles",
        "Coarse handles the act destroyed. Representation the coarse layer used to carry and no "
        "longer does - the erasure runs upward, not only downward."),
    "emptied_handle": (
        "handles",
        "Coarse handles that survive with no fine support: a label with nothing under it. The "
        "structural face of vacuous rightness - the coarse layer still reads fluently."),
    "overflow": (
        "items",
        "Fine items a coarse handle carries beyond the act's declared capacity, which the act "
        "could not resolve. The handle stands, but it is not a summary of what it holds."),
    "noncommutation": (
        "operator_norm",
        "A directly measured O = C·G_mu - G_M·C: consolidate-then-evolve against "
        "evolve-then-consolidate, in whatever norm the producer declares in `detail`. The "
        "obstruction proper, where an act has both generators in hand."),
    "degenerate": (
        "items",
        "The act returned its input: no coarsening happened, over this many items. UP's silent "
        "failure mode said out loud - reproduction without compression, which any success-derived "
        "signal scores as correct."),
    # --- grown 2026-08-23 (DP-A1, the two-seat design; the module's own law: a new kind
    # lands HERE, once, with its unit - never at a call site) -----------------------------
    "disagreement": (
        "k_delta",
        "The selector and its retained diagnostic named different structures over the same "
        "input (residual k vs silhouette k, |delta| as magnitude). The seam's own alarm "
        "class made a kind: absorbed disagreement is how a wrong selector rides silently. "
        "Found as a LANDMINE 2026-08-23 - the alarm call used a kind this vocabulary "
        "refused, so the first real disagreement would have crashed the fold mid-deposit."),
    "unresolved_edge": (
        "edges",
        "Wires neither axis claimed: a relation the weld carried into the coarse layer "
        "without a type, riding the fallback axis by default rather than by judgement."),
    "compression_loss": (
        "fraction (meter: DP-A2)",
        "Information the coarse essence/digest cannot rebuild about its own members - THE "
        "DIGEST CURE'S meter. The kind banks now; its magnitude semantics arrive with the "
        "digest design (DP-A2's declared dependency, S4) - until then producers bank it "
        "only where a defensible fraction exists, never a placeholder."),
}


class UnknownRemainder(ValueError):
    """A producer named a remainder kind outside ``REMAINDER_KINDS``.

    Raised, not coerced: an unknown kind is a producer inventing vocabulary at the call site,
    which is exactly what a closed vocabulary exists to prevent. The fix is to add the kind here
    with its unit, or to use the one that fits."""


def remainder_kinds() -> dict[str, tuple[str, str]]:
    """The closed vocabulary: ``{kind: (unit, meaning)}``. A copy - the store's is not editable."""
    return dict(REMAINDER_KINDS)


def unit_of(kind: str) -> str:
    """The unit ``magnitude`` is counted in for ``kind``. Raises ``UnknownRemainder``."""
    try:
        return REMAINDER_KINDS[kind][0]
    except KeyError:
        raise UnknownRemainder(
            f"{kind!r} is not a remainder kind. The vocabulary is closed: "
            f"{', '.join(sorted(REMAINDER_KINDS))}") from None


def enabled() -> bool:
    """The banking kill-switch. On by default; ``LAPLACE_RESIDUE=0`` turns it off."""
    return os.environ.get(ENV_DISABLE, "").strip().lower() not in ("0", "off", "false", "no")


def _now() -> str:
    """Wall-clock UTC to the second - the sibling ledgers' stamp. A label, not the order."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_act_id(up_act: str) -> str:
    """One id for one UP act, so every remainder that act banked reads back as one cochain.

    The act, not the row, is the unit the cocycle is bookkept over: a single fold discards along
    several kinds at several grades, and those rows are one obstruction seen from several sides."""
    return f"{up_act}:{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# the row
# ---------------------------------------------------------------------------

def build_row(up_act: str, kind: str, magnitude: float, *, axis: str,
              grade: int | None = None, n: int | None = None, chi: int | None = None,
              ids: Iterable[str] = (), act_id: str | None = None,
              consumer: str = "noise",
              detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """One typed remainder. Raises ``UnknownRemainder`` on a kind outside the vocabulary.

    ``grade`` is the scale the remainder arose at, in the producer's own numbering, and is NULL
    for an act-level remainder that spans grades rather than sitting at one (an assignment step
    over a whole layer). Null means "the act as a whole", never zero and never unknown.

    ``axis`` is the fibre coordinate of ``upfold(grade, axis)`` - which section of the map this
    act folded along (``semantic``, ``structural``, …). It is required: a remainder with no axis
    cannot be read against another axis's, which is the whole reason the upfold is fibred.

    ``chi`` is the bond dimension the act's representation ran at - the number of retained
    directions behind any magnitude that depends on a representation (uncarried_mass above all).
    A residual read at chi<=2 saturates and one at chi>=64 counts boundaries
    (WO-20260821-residual-saturates-at-low-chi), so a consumer using magnitudes as a fitness
    signal must know the chi they were measured at or it is reading a coarseness rule. Null means
    the act had no representational truncation (a pure assignment), never unknown.

    ``consumer`` is the STRUCTURE side of the row (DP-A1 S1, 2026-08-23): the NAMED CALL that
    would consume this remainder - a descent, a retry, a bench re-score, a dreamer verb - or the
    literal ``"noise"`` when no consumer can be named. A structured remainder seeds the next
    grade; noise is the real loss; the reader's ``noise_fraction`` is this field aggregated. A
    feeling is not a consumer; a call is."""
    unit = unit_of(kind)
    id_list = list(ids)
    count = len(id_list) if n is None else int(n)
    row: dict[str, Any] = {
        "schema": SCHEMA,
        "ts": _now(),
        "act_id": act_id or new_act_id(up_act),
        "up_act": up_act,
        "axis": axis,
        "grade": None if grade is None else int(grade),
        "kind": kind,
        "unit": unit,
        "chi": None if chi is None else int(chi),
        "magnitude": float(magnitude),
        "n": count,
        "ids": id_list[:IDS_CAP],
        "consumer": str(consumer),
    }
    det = dict(detail or {})
    if len(id_list) > IDS_CAP:
        det["ids_truncated"] = len(id_list)
    row["detail"] = det
    return row


# ---------------------------------------------------------------------------
# the accumulator - one act's remainders, banked in one append
# ---------------------------------------------------------------------------

class ResidueLedger:
    """Collect an UP act's typed remainders, then bank them in ONE append.

    A producer that appended per remainder would open the store once per discarded cluster, which
    is both slower and a worse record: the rows of one act belong together under one ``act_id``.
    ``add`` validates the kind at the call site (so a bad kind fails where it was written, not at
    the flush), holds the row in memory, and costs a list append."""

    def __init__(self, up_act: str, *, axis: str, act_id: str | None = None,
                 chi: int | None = None) -> None:
        self.up_act = up_act
        self.axis = axis
        self.chi = chi   # the act's representation bond dimension; see build_row's chi note
        self.act_id = act_id or new_act_id(up_act)
        self.rows: list[dict[str, Any]] = []

    def add(self, kind: str, magnitude: float, *, grade: int | None = None,
            n: int | None = None, chi: int | None = None, ids: Iterable[str] = (),
            consumer: str = "noise", **detail: Any) -> dict[str, Any]:
        row = build_row(self.up_act, kind, magnitude, axis=self.axis, grade=grade, n=n,
                        chi=chi if chi is not None else self.chi,
                        ids=ids, act_id=self.act_id, consumer=consumer, detail=detail)
        self.rows.append(row)
        return row

    def bank(self, repo_root: Path | str) -> Path | None:
        """Append this act's rows. Never raises - see ``bank`` below. No rows, no write."""
        return bank(repo_root, self.rows)


# ---------------------------------------------------------------------------
# the store - append-only, and never fatal
# ---------------------------------------------------------------------------

def store_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / STORE_FILE


def append_rows(repo_root: Path | str, rows: list[dict[str, Any]]) -> Path:
    """Append rows in one open. Raises on failure - ``bank`` is the seam that swallows it loudly."""
    path = store_path(repo_root)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def bank(repo_root: Path | str, rows: list[dict[str, Any]]) -> Path | None:
    """Append an act's rows. NEVER raises into the producer.

    An UP act's answer must not depend on its bookkeeping being writable, so every exception class
    is caught and costs one stderr line. Returns the path on success, None when disabled, when
    there was nothing to bank, or on a degrade."""
    if not enabled() or not rows:
        return None
    try:
        return append_rows(repo_root, rows)
    except Exception as exc:  # noqa: BLE001 - deliberate: bookkeeping must not cost an act its answer
        print(f"residue: DEGRADED, {len(rows)} row(s) not banked to {STORE_FILE} "
              f"({type(exc).__name__}: {exc}) - the UP act is unaffected", file=sys.stderr)
        return None


def read_rows(repo_root: Path | str, *, up_act: str | None = None,
              axis: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    """Read the banked rows in append order (which IS their order - see the module header).

    Unparseable lines are skipped with a stderr line rather than raising: a half-written tail row
    is the one thing an append-only ledger can leave behind, and it must not cost the whole store."""
    path = store_path(repo_root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            print(f"residue: skipping unparseable row {i} in {STORE_FILE} ({exc})", file=sys.stderr)
            continue
        if up_act is not None and row.get("up_act") != up_act:
            continue
        if axis is not None and row.get("axis") != axis:
            continue
        if kind is not None and row.get("kind") != kind:
            continue
        rows.append(row)
    return rows


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per ``(axis, grade, kind)``: how much remainder, over how many items, from how many acts.

    Magnitudes are summed WITHIN a cell only. Cells are not summed across grades: obstructions
    compose as a 1-cocycle under a transport this store does not declare, so adding a grade-1
    remainder to a grade-2 one would be arithmetic on a quantity that has no such sum. Sorted by
    axis, then grade (null last - it is act-level, not scale-zero), then kind."""
    cells: dict[tuple[str, Any, str], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("axis"), row.get("grade"), row.get("kind"))
        cell = cells.setdefault(key, {"axis": key[0], "grade": key[1], "kind": key[2],
                                      "unit": row.get("unit"), "rows": 0, "n": 0,
                                      "magnitude": 0.0, "acts": set()})
        cell["rows"] += 1
        cell["n"] += int(row.get("n") or 0)
        cell["magnitude"] += float(row.get("magnitude") or 0.0)
        cell["acts"].add(row.get("act_id"))
    out = []
    for cell in cells.values():
        cell["acts"] = len(cell["acts"])
        cell["magnitude"] = round(cell["magnitude"], 6)
        out.append(cell)
    out.sort(key=lambda c: (str(c["axis"]), c["grade"] is None, c["grade"] or 0, str(c["kind"])))
    return out


def typed_residue(repo_root: Path | str = ".") -> dict[str, Any]:
    """The CAMP-02 reader (DP-A1, both seats' design, 2026-08-23): WHERE + WHY + ALLOCATION,
    one call, offline, read-only - no bank path lives here by construction (builder≠judge in
    the organ layer: the seam writes, this reads).

    WHERE+WHY is ``aggregate`` over the banked rows. ALLOCATION (S2) is temporal and lives in
    this reader, never the enum: per (axis, grade, kind) cell, the per-act magnitude series in
    ts order answers the papers' stopping condition - a cell whose series stopped decreasing is
    CLOSED (stop spending dim there); one still decreasing DEMANDS-INVESTMENT (his D1 ruling:
    residual is an allocation signal, never a demotion signal); fewer than three acts is
    INSUFFICIENT-SERIES, said loudly rather than guessed. ``noise_fraction`` is S1's structure
    axis aggregated: the share of rows no consumer call could be named for - the real loss."""
    rows = read_rows(repo_root)
    cells: dict[tuple[str, Any, str], dict[str, list]] = {}
    for r in rows:
        key = (r.get("axis"), r.get("grade"), r.get("kind"))
        cell = cells.setdefault(key, {"acts": {}, "order": []})
        aid = r.get("act_id")
        if aid not in cell["acts"]:
            cell["acts"][aid] = 0.0
            cell["order"].append(aid)
        cell["acts"][aid] += float(r.get("magnitude") or 0.0)
    allocation = []
    for (axis, grade, kind), cell in sorted(cells.items(),
                                            key=lambda kv: (str(kv[0][0]), kv[0][1] is None,
                                                            kv[0][1] or 0, str(kv[0][2]))):
        series = [round(cell["acts"][a], 6) for a in cell["order"]]
        if len(series) < 3:
            verdict = "INSUFFICIENT-SERIES"
        elif series[-1] >= series[-2] and series[-2] >= series[-3]:
            verdict = "CLOSED"
        else:
            verdict = "DEMANDS-INVESTMENT"
        allocation.append({"axis": axis, "grade": grade, "kind": kind,
                           "acts": len(series), "series_tail": series[-4:],
                           "verdict": verdict})
    n_noise = sum(1 for r in rows if r.get("consumer", "noise") == "noise")
    return {
        "rows": len(rows),
        "where_why": aggregate(rows),
        "allocation": allocation,
        "noise_fraction": round(n_noise / len(rows), 4) if rows else None,
        "spec": "DP-A1 (both seats, 2026-08-23): kinds closed in REMAINDER_KINDS, unknown "
                "raises; consumer|noise per row (a call, never a feeling); allocation from "
                "per-act series - CLOSED / DEMANDS-INVESTMENT / INSUFFICIENT-SERIES; "
                "magnitudes never summed across grades (the cocycle law).",
    }


def main(argv: list[str] | None = None) -> int:
    """``python -m laplace.engine.residue`` - the aggregate over the banked rows, as JSON."""
    ap = argparse.ArgumentParser(description="read the typed UP residue store")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--up-act", default=None)
    ap.add_argument("--axis", default=None)
    ap.add_argument("--kind", default=None)
    ap.add_argument("--rows", action="store_true", help="print the rows, not the aggregate")
    args = ap.parse_args(argv)
    rows = read_rows(args.repo_root, up_act=args.up_act, axis=args.axis, kind=args.kind)
    print(json.dumps(rows if args.rows else aggregate(rows), indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
