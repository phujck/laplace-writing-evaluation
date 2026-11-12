from __future__ import annotations

import builtins
import copy

from laplace.engine import front_coordination


def _evidence(index: int, label: str) -> dict:
    return {
        "handle": f"sha256:{index:064x}",
        "label": label,
        "kind": "observation",
        "continuation": {"focus": label.casefold().replace(" ", "-")},
    }


def _profile(*, consumption: bool = True) -> dict:
    profile_handle = "sha256:" + "a" * 64
    fold_handle = "sha256:" + "b" * 64
    derivation_handle = "sha256:" + "c" * 64
    profile = {
        "schema_version": front_coordination.PROFILE_SCHEMA,
        "shared": True,
        "profile_handle": profile_handle,
        "fold": {
            "schema_version": front_coordination.FOLD_SCHEMA,
            "fold_handle": fold_handle,
            "derivation_handle": derivation_handle,
            "historical_source_status": front_coordination.HISTORICAL_SOURCE_STATUS,
            "current_phase": "inertial-phase",
            "phases": [
                {
                    "phase": "flat-instability",
                    "condition": "coordination structure is insufficient",
                    "signals": ["peer conflict", "lost ownership"],
                    "evidence": [_evidence(1, "Flat phase observation")],
                    "continuation": {"phase": "flat-instability", "offset": 1},
                },
                {
                    "phase": "viable-modular-band",
                    "condition": "the minimum sufficient hierarchy is operating",
                    "signals": ["bounded parallelism", "local correction"],
                    "evidence": [_evidence(2, "Viable band observation")],
                    "continuation": {"phase": "viable-modular-band", "offset": 1},
                },
                {
                    "phase": "inertial-phase",
                    "condition": "coordination layers cost more than they protect",
                    "signals": ["serial gates", "high control effort"],
                    "evidence": [_evidence(3, "Inertial phase observation")],
                    "continuation": {"phase": "inertial-phase", "offset": 1},
                },
            ],
            "measures": {
                "serial_gate_latency": {
                    "status": "MEASURED", "value": 18.4, "unit": "seconds",
                    "evidence": [_evidence(4, "Decision-to-act trace")],
                    "continuation": {"metric": "serial_gate_latency"},
                },
                "control_effort": {
                    "status": "MEASURED", "value": 7, "unit": "interventions",
                    "evidence": [_evidence(5, "Control interventions")],
                    "continuation": {"metric": "control_effort"},
                },
                "signal_loss": {
                    "status": "MEASURED", "value": 2, "unit": "dropped-signals",
                    "evidence": [_evidence(6, "Signal-loss census")],
                    "continuation": {"metric": "signal_loss"},
                },
                "protective_yield": {
                    "status": "MEASURED", "value": 0.23, "unit": "prevented-defects-per-cost",
                    "evidence": [_evidence(7, "Protective-yield comparison")],
                    "continuation": {"metric": "protective_yield"},
                },
            },
            "scaffold_retirement": {
                "rows": [{
                    "handle": "sha256:" + "d" * 64,
                    "label": "Repeated local review gate",
                    "owner": "Superego",
                    "state": "ACTIVE",
                    "protective_yield": {"value": 0.1, "unit": "defects-per-cycle"},
                    "added_latency": {"value": 11, "unit": "seconds"},
                    "signal_loss": {"value": 1, "unit": "meaning-breaks"},
                    "control_effort": {"value": 3, "unit": "interventions"},
                    "retirement_predicate": "retire after two reversible local corrections pass",
                    "evidence": [_evidence(8, "Scaffold account")],
                    "continuation": {"scaffold": "repeated-local-review"},
                }],
                "evidence": [_evidence(9, "Scaffold retirement census")],
                "continuation": {"scaffolds": "next"},
            },
        },
        "non_blocking": True,
        "authority_effect": "none",
    }
    if consumption:
        profile["operational_consumption"] = {
            "schema_version": front_coordination.CONSUMPTION_SCHEMA,
            "status": "CONSUMED",
            "receipt_handle": "sha256:" + "e" * 64,
            "profile_handle": profile_handle,
            "fold_handle": fold_handle,
            "derivation_handle": derivation_handle,
            "observed_at": "2026-08-28T12:00:00Z",
        }
    return profile


def test_current_projection_carries_three_phases_measures_and_exact_descent() -> None:
    face = front_coordination.project(_profile())
    assert face["schema_version"] == front_coordination.PROJECTION_SCHEMA
    assert face["status"] == "CURRENT"
    assert face["current_phase"] == "inertial-phase"
    assert [row["phase"] for row in face["phase_bands"]] == [
        "flat-instability", "viable-modular-band", "inertial-phase",
    ]
    assert [row["active"] for row in face["phase_bands"]] == [False, False, True]
    assert face["measures"]["serial_gate_latency"] == {
        "label": "Serial-gate latency",
        "status": "CURRENT",
        "value": 18.4,
        "unit": "seconds",
        "evidence": [_evidence(4, "Decision-to-act trace")],
        "continuation": {"metric": "serial_gate_latency"},
    }
    assert face["measures"]["control_effort"]["value"] == 7
    assert face["measures"]["signal_loss"]["value"] == 2
    assert face["measures"]["protective_yield"]["value"] == 0.23
    assert face["operational_consumption"]["status"] == "CURRENT"
    assert face["exact_descent"]["consumption_receipt"] == "sha256:" + "e" * 64
    assert "sha256:" + f"{4:064x}" in face["exact_descent"]["evidence_handles"]
    assert face["coordination_phase_handle"] == front_coordination.canonical_handle({
        key: value for key, value in face.items()
        if key != "coordination_phase_handle"
    })


def test_absent_profile_is_unknown_not_a_synthetic_phase() -> None:
    face = front_coordination.project(None)
    assert face["status"] == "UNKNOWN"
    assert face["current_phase"] == "UNKNOWN"
    assert face["reported_phase"] is None
    assert all(row["status"] == "UNKNOWN" and row["active"] is None
               for row in face["phase_bands"])
    assert any(row["code"] == "COORDINATION_PROFILE_ABSENT" for row in face["omissions"])


def test_missing_consumption_receipt_keeps_claimed_values_but_marks_them_unknown() -> None:
    face = front_coordination.project(_profile(consumption=False))
    assert face["status"] == "UNKNOWN"
    assert face["current_phase"] == "UNKNOWN"
    assert face["reported_phase"] == "inertial-phase"
    assert face["measures"]["serial_gate_latency"]["value"] == 18.4
    assert face["measures"]["serial_gate_latency"]["status"] == "UNKNOWN"
    assert face["operational_consumption"] == {
        "status": "UNKNOWN", "receipt_handle": None, "observed_at": None,
    }
    assert any(row["code"] == "OPERATIONAL_CONSUMPTION_RECEIPT_ABSENT"
               for row in face["omissions"])


def test_forged_consumption_binding_refuses_currentness() -> None:
    profile = _profile()
    profile["operational_consumption"]["fold_handle"] = "sha256:" + "f" * 64
    face = front_coordination.project(profile)
    assert face["status"] == "REFUSED"
    assert face["current_phase"] == "UNKNOWN"
    assert face["operational_consumption"]["receipt_handle"] is None
    assert any(row["code"] == "OPERATIONAL_CONSUMPTION_RECEIPT_REFUSED"
               for row in face["omissions"])


def test_missing_measure_evidence_cannot_be_current() -> None:
    profile = _profile()
    profile["fold"]["measures"]["signal_loss"]["evidence"] = []
    face = front_coordination.project(profile)
    assert face["status"] == "UNKNOWN"
    assert face["current_phase"] == "UNKNOWN"
    assert face["measures"]["signal_loss"]["status"] == "UNKNOWN"
    assert any(row["code"] == "COORDINATION_EVIDENCE_EMPTY" for row in face["omissions"])


def test_exact_three_phase_coverage_is_required_without_threshold_inference() -> None:
    profile = _profile()
    profile["fold"]["phases"] = profile["fold"]["phases"][1:]
    face = front_coordination.project(profile)
    assert face["status"] == "UNKNOWN"
    assert face["current_phase"] == "UNKNOWN"
    flat = face["phase_bands"][0]
    assert flat["phase"] == "flat-instability"
    assert flat["condition"] is None
    assert any(row["code"] == "COORDINATION_PHASE_ABSENT" for row in face["omissions"])


def test_historical_synthetics_source_cannot_be_reintroduced_as_current_law() -> None:
    profile = _profile()
    profile["fold"]["historical_source_status"] = "CURRENT-LAW"
    face = front_coordination.project(profile)
    assert face["status"] != "CURRENT"
    assert face["source"]["historical_source_is_current_law"] is False
    assert any(row["code"] == "HISTORICAL_PHASE_SOURCE_NOT_QUARANTINED"
               for row in face["omissions"])


def test_scaffold_account_preserves_retirement_predicate_and_costs() -> None:
    face = front_coordination.project(_profile())
    retirement = face["scaffold_retirement"]
    assert retirement["status"] == "CURRENT"
    assert retirement["active"] == 1
    assert retirement["submerged"] == 0
    assert retirement["retired"] == 0
    row = retirement["rows"][0]
    assert row["owner"] == "Superego"
    assert row["protective_yield"] == {"value": 0.1, "unit": "defects-per-cycle"}
    assert row["added_latency"] == {"value": 11, "unit": "seconds"}
    assert row["retirement_predicate"].startswith("retire after")
    assert row["continuation"] == {"scaffold": "repeated-local-review"}


def test_projection_is_pure_read_only_and_does_not_mutate_input(monkeypatch) -> None:
    profile = _profile()
    before = copy.deepcopy(profile)

    def forbidden_open(*_args, **_kwargs):
        raise AssertionError("coordination projection attempted filesystem access")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    face = front_coordination.project(profile)
    assert profile == before
    assert face["authority"] == {
        "read_only": True,
        "authority_effect": "none",
        "writes": [],
        "second_truth_store": "forbidden",
    }


def test_nonfinite_or_authority_bearing_profiles_refuse() -> None:
    nonfinite = _profile()
    nonfinite["fold"]["measures"]["control_effort"]["value"] = float("nan")
    assert front_coordination.project(nonfinite)["status"] == "REFUSED"

    authority = _profile()
    authority["authority_effect"] = "bind"
    assert front_coordination.project(authority)["status"] == "REFUSED"
