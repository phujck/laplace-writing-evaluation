"""derive_fates.py - the empirically DERIVED fates codebook (F14), the vocabulary the meter emits into.

The sealed adjudicator (adjudicate_sealed.py) emits NO fate label - it banks raw signals
(``lost`` / ``added`` counts, ``structured`` / ``recurses``) and stops, because FORK-FATES was the
author's to settle, not the meter's to invent. This closes exactly that gap: it READS the codebook
off the banked calibration batch rather than asserting it. The batch already carries enough occupied
cells to derive the code - so the code is derived, never legislated. Same discipline as the meter one
rung down: **a vocabulary you have not validated against ground truth cannot name anything.**

The carving is the 2x2 the ruling named - {lost, added} x {structured, noise} - read as a total
predicate over the joint signal vector ``(n_lost, n_added, structured, recurses)``:

  - **faithful** - ~nothing lost, ~nothing added: the ghost carried the object.
  - **partial** - lost AND structured AND recurses, nothing added: the spine survived, the finer
    flesh was lost in a namable way that seeds the next grade. The target band, not a failure.
  - **confabulated** - lost AND added: the ghost dropped truth AND asserted what was never there.
    The plant axis - systematic inversion, the morally load-bearing catch.
  - **enriched** - added AND nothing lost: coherent structure ADDED on a preserved base. The
    candidate 4th cell. The naive {added ^ structured} split the ruling floated is REFUTED by the
    batch - confab_rho_estimator carries a structured residual yet is a confabulation - so the added
    axis is carved by loss-presence, not the ``structured`` bool. And enriched-vs-confabulated cannot
    be settled from the signal alone (added-without-loss could be true structure OR a clean
    fabrication that dropped nothing), so this cell is NEVER asserted from an unoccupied count: it is
    emitted ``candidate: true, n: 0``, held open for the datum that occupies it.

The signal is read at CONSENSUS (support >= 2 independent judges) - meaning lives in the joint, and
the aggregate's own tail (support 1) is noise, not signal. The same extraction feeds the derivation
and the downstream stamp, so the codebook is regenerable and the stamp agrees with what derived it.

SELF-GATE: the carving must reproduce every ``expected.json`` label or the codebook is VOID - the
same bar as the meter's faithfulness gate. On disagreement it writes NOTHING (a marked disagreement
report instead) and exits nonzero: an unfaithful vocabulary is not shipped, it is banked as the gap.

Usage:
    python derive_fates.py derive [--calibration <dir>] [--out <codebook.json>] [--report <path>]
    python derive_fates.py classify <v1.json> [<v2.json> ...]   # signal -> fate, using the codebook
    python derive_fates.py show                                  # print the resolved codebook
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_SKILL = _HERE.parents[1]                       # .../reconstruction_fitness
_REPO = _HERE.parents[6]
_CALIBRATION = _SKILL / "calibration"
_CODEBOOK = _SKILL / "fates_codebook.json"

# The codebook version stamps every fate this batch derives; it rides the stamp's ``reason`` so a
# banked fate is attributable to the exact vocabulary that read it (``reason="codebook:<version>"``).
CODEBOOK_VERSION = "f14-2026-07-13"

# Consensus boundary: an item >= this many independent judges surfaced is high-confidence signal, the
# rest is the aggregate's tail. This is the aggregator's own boundary (see adjudicate_sealed.aggregate),
# reused so the derivation reads the same joint the meter banks.
CONSENSUS_SUPPORT = 2


# --- the meter, imported not re-implemented (builder != judge; reuse the existing aggregate) -------
def _sealed():
    """The sealed adjudicator module - the source of ``aggregate`` and the verdict parse/validate."""
    sys.path.insert(0, str(_HERE.parent))
    import adjudicate_sealed  # type: ignore
    return adjudicate_sealed


# --- the signal vector: the joint, read at consensus ---------------------------------------------
def signal_vector(agg: dict, support_min: int = CONSENSUS_SUPPORT) -> dict:
    """Reduce an aggregated ensemble to the joint the codebook is carved over.

    ``n_lost`` / ``n_added`` count only CONSENSUS items (support >= ``support_min``) - the free-text
    tail a single judge raised is noise, not a claim about the pair. The booleans are the ensemble
    majority the aggregate already folded.
    """
    return {
        "n_lost": sum(1 for x in (agg.get("lost") or []) if x.get("support", 0) >= support_min),
        "n_added": sum(1 for x in (agg.get("added") or []) if x.get("support", 0) >= support_min),
        "structured": bool(agg.get("structured")),
        "recurses": bool(agg.get("recurses")),
    }


# --- the predicate: a machine-checkable dict the stamping code evaluates over the signal vector ----
# Each fate's predicate is a flat {signal: condition} dict, ANDed. A count condition is a comparison
# string ("==0", ">=1"); a boolean condition is a JSON bool. Deliberately data, not code - it rides
# in the committed artifact and the stamp evaluates it there, so the vocabulary is regenerable and
# the same predicate that DERIVED a fate is the one that later STAMPS it.
_OPS = {
    "==": lambda a, b: a == b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
}
_COND = re.compile(r"^(==|>=|<=|!=|>|<)\s*(-?\d+)$")


def _check(cond, value) -> bool:
    if isinstance(cond, bool):
        return bool(value) is cond
    m = _COND.match(str(cond).strip())
    if not m:
        raise ValueError(f"unparseable predicate condition {cond!r}")
    return _OPS[m.group(1)](value, int(m.group(2)))


def eval_predicate(pred: dict, sig: dict) -> bool:
    """True iff the signal vector satisfies every clause of a fate's predicate (clauses ANDed)."""
    return all(_check(cond, sig.get(key)) for key, cond in pred.items())


# The CARVING - the settled three plus the candidate 4th, as predicates over the signal vector. This
# is the code READ OFF the batch (each predicate reproduced its cell's expected label 5/5 below), not
# invented; the self-gate re-checks it against ground truth before anything is written.
CARVING = {
    "faithful":     {"n_lost": "==0", "n_added": "==0"},
    "partial":      {"n_lost": ">=1", "n_added": "==0", "structured": True, "recurses": True},
    "confabulated": {"n_lost": ">=1", "n_added": ">=1"},
    "enriched":     {"n_lost": "==0", "n_added": ">=1"},
}

# The survived-vs-earned weights, byte-identical to telemetry.RECONSTRUCTION_FATES for the settled
# three so the merged view is a no-op on values (F14 layers a cell, it does not move the base). The
# candidate's weight is PROVISIONAL - it is never read while candidate:true holds the cell shut.
_VALUES = {"faithful": 0.9, "partial": 0.6, "confabulated": 0.2, "enriched": 0.9}
_CANDIDATE = {"enriched"}


def classify(sig: dict, fates: dict, include_candidate: bool = False) -> str | None:
    """Map a signal vector to its fate via the codebook predicates - the stamping decision.

    Returns the first fate whose predicate the signal satisfies; ``None`` if none match (a degenerate
    cell - e.g. lost-as-noise - the codebook does not name, banked without a fate). Candidate fates
    (``candidate: true``) are NOT stampable, so they are skipped unless ``include_candidate`` is set
    (the derivation sets it to place the batch; the stamp never does).
    """
    for name, spec in fates.items():
        if spec.get("candidate") and not include_candidate:
            continue
        if eval_predicate(spec.get("predicate", {}), sig):
            return name
    return None


# --- reading the banked telemetry (a SECOND source, never conflated with calibration) -------------
def telemetry_signal_count() -> int:
    """How many sealed adjudications the telemetry shards banked - reported, never conflated.

    Calibration carries GROUND-TRUTH labels; telemetry carries SIGNALS ONLY (the meter emits no
    fate), so it can corroborate the carving's occupancy but cannot seed it. On a fresh clone the
    shards are empty and this is 0. Kept a separate line in ``derived_from`` so the two sources stay
    legible - the derivation reads calibration, and reports what telemetry independently holds.
    """
    try:
        sys.path.insert(0, str(_REPO / "src"))
        from laplace.engine import telemetry  # type: ignore
        return sum(1 for e in telemetry.events() if e.get("phase") == "adjudication")
    except Exception:
        return 0


# --- the derivation + its self-gate ---------------------------------------------------------------
def load_calibration(cdir: Path) -> list[dict]:
    """Aggregate each calibration item's verdict ensemble into ``{id, label, agg, signal}``.

    Reuses the meter's own ``aggregate`` (builder != judge - the derivation does not re-implement the
    joint it reads); each item folds its ``v*.json`` ensemble, then reduces to the consensus signal.
    """
    ad = _sealed()
    items: list[dict] = []
    for sub in sorted(cdir.iterdir()):
        exp = sub / "expected.json"
        if not (sub.is_dir() and exp.exists()):
            continue
        meta = json.loads(exp.read_text(encoding="utf-8"))
        verdicts: list[dict] = []
        for p in sorted(sub.glob("*.json")):
            if p.name == "expected.json":
                continue
            try:
                v = ad.parse_verdict(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not ad.validate_verdict(v):
                verdicts.append(v)
        agg = ad.aggregate(verdicts)
        items.append({"id": sub.name, "label": meta["label"], "agg": agg,
                      "signal": signal_vector(agg)})
    return items


def derive(cdir: Path = _CALIBRATION) -> dict:
    """Read the codebook off the batch and SELF-GATE it against ground truth.

    Returns ``{codebook, agreement, disagreements, items}``. ``codebook`` is the artifact to write;
    ``disagreements`` is non-empty exactly when the carving fails to reproduce an ``expected.json``
    label - in which case the codebook is VOID and the caller must write nothing but the report.
    """
    items = load_calibration(cdir)
    # Occupancy + the self-gate in one pass: classify each item (candidates INCLUDED so an item that
    # falls in the candidate cell is counted honestly, not silently absorbed by a settled fate).
    occupancy: dict[str, int] = {name: 0 for name in CARVING}
    disagreements: list[dict] = []
    for it in items:
        carved = classify_carving(it["signal"])
        if carved is not None:
            occupancy[carved] += 1
        if carved != it["label"]:
            disagreements.append({"id": it["id"], "expected": it["label"], "carved": carved,
                                  "signal": it["signal"]})

    n_cal = len(items)
    agreement = f"{n_cal - len(disagreements)}/{n_cal}"
    telemetry_n = telemetry_signal_count()

    fates = {}
    for name, pred in CARVING.items():
        n_obs = occupancy[name]
        candidate = name in _CANDIDATE
        spec = {
            "predicate": pred,
            "value": _VALUES[name],
            "n_observed": n_obs,
            "candidate": bool(candidate or n_obs == 0),
        }
        if candidate:
            spec["note"] = ("added AND nothing lost - coherent structure added on a preserved base. "
                            "UNOCCUPIED in this batch; enriched-vs-confabulated is undecidable from "
                            "the signal alone (added-without-loss may be true structure or a clean "
                            "fabrication), so the cell is never asserted from an empty count.")
        fates[name] = spec

    codebook = {
        "version": CODEBOOK_VERSION,
        "derived": True,
        "derived_from": {"calibration_n": n_cal, "telemetry_n": telemetry_n},
        "consensus_support": CONSENSUS_SUPPORT,
        "signal": ["n_lost", "n_added", "structured", "recurses"],
        "fates": fates,
        "agreement": {"calibration": agreement},
        "note": ("DERIVED, not invented - the carving read off the banked calibration batch and "
                 "self-gated to reproduce every expected.json label. Regenerate with "
                 "`python derive_fates.py derive`. n_lost/n_added are CONSENSUS counts (support "
                 ">= consensus_support). The three settled fates carry telemetry's base weights "
                 "(0.9/0.6/0.2); enriched is a candidate cell held open, never stamped."),
    }
    return {"codebook": codebook, "agreement": agreement,
            "disagreements": disagreements, "items": items}


def classify_carving(sig: dict) -> str | None:
    """Classify against the in-code CARVING (candidates included) - the derivation's own read.

    This is the self-gate's classifier, distinct from :func:`classify` over a loaded codebook: it
    includes the candidate cell so an item that lands there is COUNTED, not folded into a settled
    fate. The two must agree on the settled cells by construction (same predicates).
    """
    for name, pred in CARVING.items():
        if eval_predicate(pred, sig):
            return name
    return None


# --- reading the committed codebook (the artifact the stamp evaluates) ----------------------------
def load_codebook(path: Path = _CODEBOOK) -> dict | None:
    """The committed codebook artifact, or ``None`` if it does not resolve (base-only environment)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# --- the disagreement report (written INSTEAD of the codebook when the self-gate fails) -----------
def disagreement_report(result: dict) -> str:
    """The banked gap: what the carving got wrong, so a void codebook leaves a spec, not silence."""
    lines = [
        "# Fates codebook VOID - the carving disagreed with ground truth",
        "",
        f"agreement: {result['agreement']}   (the self-gate requires all/all)",
        "",
        "The derived carving failed to reproduce these expected.json labels. Nothing was written; "
        "an unfaithful vocabulary is not shipped. The disagreement IS the spec for the next carving:",
        "",
    ]
    for d in result["disagreements"]:
        lines.append(f"- {d['id']}: expected {d['expected']!r}, carved {d['carved']!r}  "
                     f"signal={d['signal']}")
    lines.append("")
    return "\n".join(lines)


# --- CLI ------------------------------------------------------------------------------------------
def _opt(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    cmd = args[0] if args else "derive"

    if cmd == "show":
        cb = load_codebook()
        if cb is None:
            print("no codebook artifact resolved (base-only environment)", file=sys.stderr)
            return 1
        print(json.dumps(cb, indent=2, ensure_ascii=False))
        return 0

    if cmd == "classify":
        vfiles = args[1:]
        if not vfiles:
            print(__doc__)
            return 2
        ad = _sealed()
        verdicts = [ad.parse_verdict(Path(f).read_text(encoding="utf-8", errors="replace"))
                    for f in vfiles]
        sig = signal_vector(ad.aggregate(verdicts))
        cb = load_codebook()
        fates = cb["fates"] if cb else {n: {"predicate": p, "candidate": n in _CANDIDATE}
                                        for n, p in CARVING.items()}
        fate = classify(sig, fates)
        print(f"signal: {sig}")
        print(f"fate:   {fate or '(unclassified)'}")
        return 0

    if cmd == "derive":
        cdir = Path(_opt(argv, "--calibration", str(_CALIBRATION)))
        out = Path(_opt(argv, "--out", str(_CODEBOOK)))
        report = _opt(argv, "--report")
        result = derive(cdir)

        if result["disagreements"]:
            text = disagreement_report(result)
            rp = Path(report) if report else out.with_name("fates_codebook_VOID.md")
            rp.write_text(text, encoding="utf-8")
            print(f"# Fates codebook VOID - self-gate failed ({result['agreement']})", file=sys.stderr)
            print(text, file=sys.stderr)
            print(f"disagreement report -> {rp}", file=sys.stderr)
            return 1

        out.write_text(json.dumps(result["codebook"], indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        cb = result["codebook"]
        print(f"# Fates codebook DERIVED - self-gate PASS ({result['agreement']})")
        print("*" * 50)
        for name, spec in cb["fates"].items():
            flag = "candidate" if spec["candidate"] else "settled  "
            print(f"  [{flag}] {name:<13} n={spec['n_observed']}  value={spec['value']}  "
                  f"{spec['predicate']}")
        print(f"derived_from: {cb['derived_from']}   agreement: {cb['agreement']['calibration']}")
        print(f"codebook -> {out}")
        return 0

    print(f"unknown command {cmd!r}", file=sys.stderr)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
