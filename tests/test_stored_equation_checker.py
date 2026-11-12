"""The stored-equation checker: it catches SD-2's class and stays quiet elsewhere.

WO-20260820-atom-equation-defects asked for a checker for self-referential and
dimensionally-incoherent stored equations. These tests pin both directions —
it fires on the measured defect string, and it does NOT fire on the ordinary
relations that live all over concept_corpus/atoms/ (a checker that cries wolf
on `rho(t) = <rho_hat(t)>` would never be run twice).
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
CHECKER = REPO / "concept_corpus" / "atoms" / "_check_stored_equations.py"


def _load():
    spec = importlib.util.spec_from_file_location("stored_equation_checker", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


checker = _load()


# The exact string that stood in concept_corpus/atoms/single-atom-computing-hhg-2023.md
# before the repair (SD-2): J defined as an integral over the filtered |J|^2.
SD2_ORIGINAL = (
    "- **fourier-response-dipole-acceleration** — The atomic response "
    "J_α(ω) = ∫ dω |χ_α(ω)|² |J_α(ω)|² is computed as the Fourier transform "
    "of dipole acceleration."
)

# The repaired line.
SD2_REPAIRED = (
    "- **fourier-response-dipole-acceleration** — The atomic response is the "
    "Fourier transform of the dipole acceleration, J(ω) = F_{t→ω}[ d⟨p⟩/dt ]."
)


def test_sd2_original_is_flagged_self_referential():
    kinds = {d.kind for d in checker.check_text(SD2_ORIGINAL, "sd2")}
    assert "SELF_REFERENTIAL" in kinds


def test_sd2_original_is_flagged_bound_variable_escape():
    kinds = {d.kind for d in checker.check_text(SD2_ORIGINAL, "sd2")}
    assert "BOUND_VAR_ESCAPE" in kinds


def test_sd2_repaired_is_clean():
    assert checker.check_text(SD2_REPAIRED, "sd2-fixed") == []


@pytest.mark.parametrize(
    "line",
    [
        # averaging relation: rho and rho-hat are different objects
        "yielding ρ(t) = ⟨ρ̂(t)⟩_r.",
        # same head, different arguments — a boundary condition, not a definition
        "the condition ρ(0,-p) = ρ(0,p) from self-adjointness.",
        # a proportionality between two distinct symbols
        "assuming f_λ(q) = c_λ f(q) reduces the correlations.",
        # a scaling law, self-consistent and fine
        "such that γ(τ) = c²(τ)γ, showing identical scaling.",
        # a legitimate integral whose result does not carry the bound variable
        "the intensity I_x = ∫ dω |χ(ω)|² |J(ω)|².",
    ],
)
def test_ordinary_relations_are_not_flagged(line):
    assert checker.check_text(line, "ordinary") == []


def test_bound_variable_escape_is_detected_after_renaming():
    # same defect, head renamed: the dimensional tell survives
    line = "the response S(k) = ∫ dk g(k) h(k) is stored."
    kinds = {d.kind for d in checker.check_text(line, "renamed")}
    assert "BOUND_VAR_ESCAPE" in kinds


def test_eq_ok_marker_suppresses():
    line = SD2_ORIGINAL + "  <!-- eq-ok: recursive -->"
    assert checker.check_text(line, "marked") == []


def test_live_atom_store_is_clean():
    """The store as committed must pass — this is the standing regression."""
    defects = []
    for path in checker.default_paths():
        defects.extend(checker.check_file(path))
    assert defects == [], "\n".join(d.render() for d in defects)
