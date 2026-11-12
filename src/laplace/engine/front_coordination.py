"""Pure hierarchy-phase projection for the Aisthesis carrier.

The derivation checkpoint defines this boundary but is deliberately not read here.
The caller supplies one shared, Ego-produced operational profile/fold observation.
This module normalizes that observation for a human-facing carrier without opening a
store, deriving a phase from private heuristics, or acquiring any authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

PROFILE_SCHEMA = "laplace.hierarchy-phase-operational-profile/1"
FOLD_SCHEMA = "laplace.hierarchy-phase-operational-fold/1"
CONSUMPTION_SCHEMA = "laplace.hierarchy-phase-consumption/1"
PROJECTION_SCHEMA = "laplace.aisthesis-coordination-phase/1"

HISTORICAL_SOURCE_STATUS = "SUPERSEDED-AND-QUARANTINED-REFERENCE"
PHASES: tuple[tuple[str, str], ...] = (
    ("flat-instability", "Flat instability"),
    ("viable-modular-band", "Viable modular band"),
    ("inertial-phase", "Inertial phase"),
)
MEASURES: tuple[tuple[str, str], ...] = (
    ("serial_gate_latency", "Serial-gate latency"),
    ("control_effort", "Control effort"),
    ("signal_loss", "Signal loss"),
    ("protective_yield", "Protective yield"),
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_handle(value: Any) -> str:
    """Return the content handle used by the carrier shown-state preimage."""

    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _copy_json(value: Any) -> Any:
    return json.loads(_canonical_bytes(value))


def _sha256_handle(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value[7:], 16)
    except ValueError:
        return False
    return True


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _measurement(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _omission(
    code: str,
    boundary: str,
    reason: str,
    continuation: Any = None,
) -> dict[str, Any]:
    row = {
        "schema_version": "laplace.aisthesis-coordination-omission/1",
        "code": code,
        "boundary": boundary,
        "reason": reason,
        "continuation": _copy_json(continuation),
    }
    row["omission_handle"] = canonical_handle(row)
    return row


def _evidence(
    value: Any,
    *,
    boundary: str,
    omissions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Normalize exact descent rows without treating labels as evidence."""

    if not _sequence(value):
        omissions.append(_omission(
            "COORDINATION_EVIDENCE_ABSENT",
            boundary,
            "the operational fold did not supply an evidence sequence",
            "laplace.hierarchy-phase-operational-fold/1",
        ))
        return [], False
    rows: list[dict[str, Any]] = []
    valid = True
    for index, supplied in enumerate(value):
        if not isinstance(supplied, Mapping):
            valid = False
            omissions.append(_omission(
                "COORDINATION_EVIDENCE_MALFORMED",
                f"{boundary}/evidence/{index}",
                "an evidence row is not an object",
                None,
            ))
            continue
        handle = supplied.get("handle")
        label = supplied.get("label")
        kind = supplied.get("kind")
        if not _sha256_handle(handle) or not isinstance(label, str) or not label.strip():
            valid = False
            omissions.append(_omission(
                "COORDINATION_EVIDENCE_MALFORMED",
                f"{boundary}/evidence/{index}",
                "evidence requires an exact sha256 handle and a human label",
                supplied.get("continuation"),
            ))
            continue
        rows.append({
            "handle": handle,
            "label": label.strip(),
            "kind": str(kind or "evidence"),
            "continuation": _copy_json(supplied.get("continuation")),
        })
    if not rows:
        valid = False
        omissions.append(_omission(
            "COORDINATION_EVIDENCE_EMPTY",
            boundary,
            "the operational claim has no exact descent witness",
            "laplace.hierarchy-phase-operational-fold/1",
        ))
    return rows, valid


def _unknown_phase_bands() -> list[dict[str, Any]]:
    return [
        {
            "phase": phase,
            "label": label,
            "status": "UNKNOWN",
            "active": None,
            "condition": None,
            "signals": [],
            "evidence": [],
            "continuation": None,
        }
        for phase, label in PHASES
    ]


def _refusal(profile: Any, reason: str) -> dict[str, Any]:
    omissions = [_omission(
        "COORDINATION_PROFILE_REFUSED",
        "Coordination phase/shared operational profile",
        reason,
        PROFILE_SCHEMA,
    )]
    face = {
        "schema_version": PROJECTION_SCHEMA,
        "status": "REFUSED",
        "current_phase": "UNKNOWN",
        "reported_phase": None,
        "phase_bands": _unknown_phase_bands(),
        "measures": {
            name: {
                "label": label,
                "status": "UNKNOWN",
                "value": None,
                "unit": None,
                "evidence": [],
                "continuation": None,
            }
            for name, label in MEASURES
        },
        "scaffold_retirement": {
            "status": "UNKNOWN",
            "active": None,
            "submerged": None,
            "retired": None,
            "rows": [],
            "evidence": [],
            "continuation": None,
        },
        "source": {
            "profile_schema": profile.get("schema_version") if isinstance(profile, Mapping) else None,
            "profile_handle": profile.get("profile_handle") if isinstance(profile, Mapping) else None,
            "fold_handle": None,
            "derivation_handle": None,
            "historical_source_status": None,
            "historical_source_is_current_law": False,
        },
        "operational_consumption": {
            "status": "UNKNOWN",
            "receipt_handle": None,
            "observed_at": None,
        },
        "exact_descent": {
            "derivation_handle": None,
            "profile_handle": None,
            "fold_handle": None,
            "consumption_receipt": None,
            "evidence_handles": [],
            "continuations": [],
        },
        "omissions": omissions,
        "authority": {
            "read_only": True,
            "authority_effect": "none",
            "writes": [],
            "second_truth_store": "forbidden",
        },
    }
    face["coordination_phase_handle"] = canonical_handle(face)
    return face


def project(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project one shared operational profile into a carrier-ready phase face.

    No thresholds are interpreted here.  The Ego-owned fold declares the observed
    phase and measurements; Aisthesis admits them only when an exact operational
    consumption receipt binds the same profile, fold and fresh derivation.
    """

    if profile is None:
        omissions = [_omission(
            "COORDINATION_PROFILE_ABSENT",
            "Coordination phase/shared operational profile",
            "the Ego-owned hierarchy phase profile/fold was not supplied",
            PROFILE_SCHEMA,
        )]
        face = _refusal({}, "profile absent")
        face["status"] = "UNKNOWN"
        face["omissions"] = omissions
        face["coordination_phase_handle"] = canonical_handle({
            key: value for key, value in face.items()
            if key != "coordination_phase_handle"
        })
        return face
    try:
        profile = _copy_json(profile)
    except (TypeError, ValueError, OverflowError):
        return _refusal(profile, "the operational profile is not canonical finite JSON")
    if profile.get("schema_version") != PROFILE_SCHEMA:
        return _refusal(profile, f"expected {PROFILE_SCHEMA}")
    if profile.get("shared") is not True:
        return _refusal(profile, "the operational profile is not the shared projection")
    if profile.get("non_blocking") is not True:
        return _refusal(profile, "the operational observation does not remain non-blocking")
    if profile.get("authority_effect") != "none":
        return _refusal(profile, "a read-only profile claims an authority effect")

    omissions: list[dict[str, Any]] = []
    profile_handle = profile.get("profile_handle")
    fold = profile.get("fold") if isinstance(profile.get("fold"), Mapping) else {}
    fold_handle = fold.get("fold_handle")
    derivation_handle = fold.get("derivation_handle")
    historical_status = fold.get("historical_source_status")

    structural_ok = True
    for okay, code, boundary, reason, continuation in (
        (_sha256_handle(profile_handle), "COORDINATION_PROFILE_HANDLE_ABSENT",
         "Coordination phase/profile handle", "profile handle is not exact", PROFILE_SCHEMA),
        (fold.get("schema_version") == FOLD_SCHEMA, "COORDINATION_FOLD_SCHEMA_REFUSED",
         "Coordination phase/fold", f"expected {FOLD_SCHEMA}", FOLD_SCHEMA),
        (_sha256_handle(fold_handle), "COORDINATION_FOLD_HANDLE_ABSENT",
         "Coordination phase/fold handle", "fold handle is not exact", FOLD_SCHEMA),
        (_sha256_handle(derivation_handle), "COORDINATION_DERIVATION_HANDLE_ABSENT",
         "Coordination phase/derivation", "fresh derivation handle is not exact", None),
        (historical_status == HISTORICAL_SOURCE_STATUS,
         "HISTORICAL_PHASE_SOURCE_NOT_QUARANTINED", "Coordination phase/source status",
         "historical Synthetics material must remain superseded and quarantined",
         HISTORICAL_SOURCE_STATUS),
    ):
        if not okay:
            structural_ok = False
            omissions.append(_omission(code, boundary, reason, continuation))

    supplied_phases = fold.get("phases")
    rows_by_phase: dict[str, Mapping[str, Any]] = {}
    if _sequence(supplied_phases):
        for index, supplied in enumerate(supplied_phases):
            if not isinstance(supplied, Mapping):
                structural_ok = False
                omissions.append(_omission(
                    "COORDINATION_PHASE_MALFORMED",
                    f"Coordination phase/bands/{index}",
                    "phase row is not an object",
                    FOLD_SCHEMA,
                ))
                continue
            phase = str(supplied.get("phase") or "")
            if phase not in dict(PHASES) or phase in rows_by_phase:
                structural_ok = False
                omissions.append(_omission(
                    "COORDINATION_PHASE_REFUSED",
                    f"Coordination phase/bands/{index}",
                    "phase id is unknown or duplicated",
                    list(dict(PHASES)),
                ))
                continue
            rows_by_phase[phase] = supplied
    else:
        structural_ok = False
        omissions.append(_omission(
            "COORDINATION_PHASES_ABSENT",
            "Coordination phase/bands",
            "fold did not supply the exact three phase bands",
            FOLD_SCHEMA,
        ))

    reported_phase = fold.get("current_phase")
    if reported_phase not in dict(PHASES):
        structural_ok = False
        omissions.append(_omission(
            "COORDINATION_CURRENT_PHASE_UNKNOWN",
            "Coordination phase/current",
            "fold current_phase is not one of the exact three phases",
            list(dict(PHASES)),
        ))

    phase_bands: list[dict[str, Any]] = []
    all_evidence_handles: list[str] = []
    continuations: list[Any] = []
    phase_evidence_ok = True
    for phase, label in PHASES:
        row = rows_by_phase.get(phase)
        if row is None:
            structural_ok = False
            phase_evidence_ok = False
            omissions.append(_omission(
                "COORDINATION_PHASE_ABSENT",
                f"Coordination phase/{label}",
                "the operational fold omitted a required phase band",
                FOLD_SCHEMA,
            ))
            phase_bands.append({
                "phase": phase,
                "label": label,
                "status": "UNKNOWN",
                "active": None,
                "condition": None,
                "signals": [],
                "evidence": [],
                "continuation": None,
            })
            continue
        evidence, evidence_ok = _evidence(
            row.get("evidence"), boundary=f"Coordination phase/{label}", omissions=omissions,
        )
        phase_evidence_ok = phase_evidence_ok and evidence_ok
        signals = row.get("signals")
        if not _sequence(signals) or not all(isinstance(item, str) and item for item in signals):
            structural_ok = False
            omissions.append(_omission(
                "COORDINATION_PHASE_SIGNALS_MALFORMED",
                f"Coordination phase/{label}",
                "phase signals must be an ordered sequence of human labels",
                row.get("continuation"),
            ))
            signals = []
        condition = row.get("condition")
        if not isinstance(condition, str) or not condition.strip():
            structural_ok = False
            omissions.append(_omission(
                "COORDINATION_PHASE_CONDITION_ABSENT",
                f"Coordination phase/{label}",
                "phase condition is absent",
                row.get("continuation"),
            ))
            condition = None
        continuation = _copy_json(row.get("continuation"))
        all_evidence_handles.extend(item["handle"] for item in evidence)
        if continuation is not None:
            continuations.append(continuation)
        phase_bands.append({
            "phase": phase,
            "label": label,
            "status": "PENDING",
            "active": None,
            "condition": condition,
            "signals": list(signals),
            "evidence": evidence,
            "continuation": continuation,
        })

    supplied_measures = fold.get("measures") if isinstance(fold.get("measures"), Mapping) else {}
    measures: dict[str, dict[str, Any]] = {}
    measures_ok = True
    for name, label in MEASURES:
        supplied = supplied_measures.get(name)
        if not isinstance(supplied, Mapping):
            measures_ok = False
            omissions.append(_omission(
                "COORDINATION_MEASURE_ABSENT",
                f"Coordination phase/{label}",
                "the operational fold omitted this required current measure",
                FOLD_SCHEMA,
            ))
            measures[name] = {
                "label": label, "status": "UNKNOWN", "value": None, "unit": None,
                "evidence": [], "continuation": None,
            }
            continue
        evidence, evidence_ok = _evidence(
            supplied.get("evidence"), boundary=f"Coordination phase/{label}", omissions=omissions,
        )
        value = supplied.get("value")
        unit = supplied.get("unit")
        measured = (
            str(supplied.get("status") or "").upper() == "MEASURED"
            and _measurement(value)
            and isinstance(unit, str)
            and bool(unit.strip())
            and evidence_ok
        )
        if not measured:
            measures_ok = False
            omissions.append(_omission(
                "COORDINATION_MEASURE_UNKNOWN",
                f"Coordination phase/{label}",
                "current measure requires a finite non-negative value, unit and exact evidence",
                supplied.get("continuation"),
            ))
        continuation = _copy_json(supplied.get("continuation"))
        all_evidence_handles.extend(item["handle"] for item in evidence)
        if continuation is not None:
            continuations.append(continuation)
        measures[name] = {
            "label": label,
            "status": "PENDING" if measured else "UNKNOWN",
            "value": value if _measurement(value) else None,
            "unit": unit.strip() if isinstance(unit, str) and unit.strip() else None,
            "evidence": evidence,
            "continuation": continuation,
        }

    retirement = (
        fold.get("scaffold_retirement")
        if isinstance(fold.get("scaffold_retirement"), Mapping) else {}
    )
    retirement_evidence, retirement_evidence_ok = _evidence(
        retirement.get("evidence"),
        boundary="Coordination phase/scaffold retirement",
        omissions=omissions,
    )
    supplied_scaffolds = retirement.get("rows")
    scaffold_rows: list[dict[str, Any]] = []
    scaffolds_ok = retirement_evidence_ok and _sequence(supplied_scaffolds)
    if not _sequence(supplied_scaffolds):
        omissions.append(_omission(
            "SCAFFOLD_RETIREMENT_ROWS_ABSENT",
            "Coordination phase/scaffold retirement",
            "the operational fold did not supply the scaffold account",
            retirement.get("continuation"),
        ))
        supplied_scaffolds = []
    for index, supplied in enumerate(supplied_scaffolds):
        if not isinstance(supplied, Mapping):
            scaffolds_ok = False
            omissions.append(_omission(
                "SCAFFOLD_ROW_MALFORMED",
                f"Coordination phase/scaffold retirement/{index}",
                "scaffold row is not an object",
                retirement.get("continuation"),
            ))
            continue
        evidence, evidence_ok = _evidence(
            supplied.get("evidence"),
            boundary=f"Coordination phase/scaffold retirement/{index}",
            omissions=omissions,
        )
        state = str(supplied.get("state") or "UNKNOWN").upper()
        predicate = supplied.get("retirement_predicate")
        handle = supplied.get("handle")
        row_ok = (
            _sha256_handle(handle)
            and isinstance(supplied.get("label"), str)
            and bool(supplied.get("label", "").strip())
            and isinstance(supplied.get("owner"), str)
            and bool(supplied.get("owner", "").strip())
            and state in {"ACTIVE", "SUBMERGED", "RETIRED"}
            and isinstance(predicate, str)
            and bool(predicate.strip())
            and evidence_ok
        )
        scaffolds_ok = scaffolds_ok and row_ok
        if not row_ok:
            omissions.append(_omission(
                "SCAFFOLD_ROW_UNKNOWN",
                f"Coordination phase/scaffold retirement/{index}",
                "scaffold account requires exact identity, owner, state, retirement predicate and evidence",
                supplied.get("continuation"),
            ))
        continuation = _copy_json(supplied.get("continuation"))
        all_evidence_handles.extend(item["handle"] for item in evidence)
        if continuation is not None:
            continuations.append(continuation)
        scaffold_rows.append({
            "handle": handle if _sha256_handle(handle) else None,
            "label": supplied.get("label"),
            "owner": supplied.get("owner"),
            "state": state if state in {"ACTIVE", "SUBMERGED", "RETIRED"} else "UNKNOWN",
            "protective_yield": _copy_json(supplied.get("protective_yield")),
            "added_latency": _copy_json(supplied.get("added_latency")),
            "signal_loss": _copy_json(supplied.get("signal_loss")),
            "control_effort": _copy_json(supplied.get("control_effort")),
            "retirement_predicate": predicate,
            "evidence": evidence,
            "continuation": continuation,
        })
    retirement_continuation = _copy_json(retirement.get("continuation"))
    all_evidence_handles.extend(item["handle"] for item in retirement_evidence)
    if retirement_continuation is not None:
        continuations.append(retirement_continuation)

    consumption = (
        profile.get("operational_consumption")
        if isinstance(profile.get("operational_consumption"), Mapping) else {}
    )
    receipt_handle = consumption.get("receipt_handle")
    receipt_present = bool(consumption)
    receipt_shape_ok = all((
        consumption.get("schema_version") == CONSUMPTION_SCHEMA,
        str(consumption.get("status") or "").upper() == "CONSUMED",
        _sha256_handle(receipt_handle),
        isinstance(consumption.get("observed_at"), str),
        bool(str(consumption.get("observed_at") or "").strip()),
    ))
    receipt_binding_ok = all((
        consumption.get("profile_handle") == profile_handle,
        consumption.get("fold_handle") == fold_handle,
        consumption.get("derivation_handle") == derivation_handle,
    ))
    if not receipt_present:
        omissions.append(_omission(
            "OPERATIONAL_CONSUMPTION_RECEIPT_ABSENT",
            "Coordination phase/current observation",
            "profile/fold has no successful operational consumption receipt",
            CONSUMPTION_SCHEMA,
        ))
    elif not receipt_shape_ok or not receipt_binding_ok:
        structural_ok = False
        omissions.append(_omission(
            "OPERATIONAL_CONSUMPTION_RECEIPT_REFUSED",
            "Coordination phase/current observation",
            "consumption receipt is malformed or does not bind the exact profile, fold and derivation",
            receipt_handle,
        ))

    complete_profile = structural_ok and phase_evidence_ok and measures_ok and scaffolds_ok
    current = complete_profile and receipt_shape_ok and receipt_binding_ok
    if current:
        status = "CURRENT"
        current_phase = reported_phase
    elif receipt_present and (not receipt_shape_ok or not receipt_binding_ok):
        status = "REFUSED"
        current_phase = "UNKNOWN"
    else:
        status = "UNKNOWN"
        current_phase = "UNKNOWN"

    for row in phase_bands:
        row["status"] = "CURRENT" if current else "UNKNOWN"
        row["active"] = row["phase"] == current_phase if current else None
    for row in measures.values():
        row["status"] = "CURRENT" if current and row["status"] == "PENDING" else "UNKNOWN"
    counts = {
        state.lower(): sum(row["state"] == state for row in scaffold_rows)
        for state in ("ACTIVE", "SUBMERGED", "RETIRED")
    }
    scaffold_retirement = {
        "status": "CURRENT" if current else "UNKNOWN",
        **counts,
        "rows": scaffold_rows,
        "evidence": retirement_evidence,
        "continuation": retirement_continuation,
    }

    face = {
        "schema_version": PROJECTION_SCHEMA,
        "status": status,
        "current_phase": current_phase,
        "reported_phase": reported_phase,
        "phase_bands": phase_bands,
        "measures": measures,
        "scaffold_retirement": scaffold_retirement,
        "source": {
            "profile_schema": profile.get("schema_version"),
            "profile_handle": profile_handle,
            "fold_handle": fold_handle,
            "derivation_handle": derivation_handle,
            "historical_source_status": historical_status,
            "historical_source_is_current_law": False,
        },
        "operational_consumption": {
            "status": "CURRENT" if current else "UNKNOWN",
            "receipt_handle": receipt_handle if receipt_shape_ok and receipt_binding_ok else None,
            "observed_at": consumption.get("observed_at") if receipt_shape_ok else None,
        },
        "exact_descent": {
            "derivation_handle": derivation_handle,
            "profile_handle": profile_handle,
            "fold_handle": fold_handle,
            "consumption_receipt": receipt_handle if receipt_shape_ok and receipt_binding_ok else None,
            "evidence_handles": list(dict.fromkeys(all_evidence_handles)),
            "continuations": continuations,
        },
        "omissions": omissions,
        "authority": {
            "read_only": True,
            "authority_effect": "none",
            "writes": [],
            "second_truth_store": "forbidden",
        },
    }
    face["coordination_phase_handle"] = canonical_handle(face)
    return face


__all__ = [
    "CONSUMPTION_SCHEMA",
    "FOLD_SCHEMA",
    "HISTORICAL_SOURCE_STATUS",
    "MEASURES",
    "PHASES",
    "PROFILE_SCHEMA",
    "PROJECTION_SCHEMA",
    "canonical_handle",
    "project",
]
