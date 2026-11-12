"""The claim auditor: every displayed equation and derivation middle gets its own check.

A check is a function returning (passed, detail). Checks are registered against claim ids
so the claim graph can point at them. The first two checks are the R2 errata the authors
caught by hand: the auditor must catch both cold (its Gate-1 bench) before it is trusted.

Run: python3 -m laplace.pipeline.writing_organ.auditor
"""

from __future__ import annotations

import numpy as np

CHECKS: dict[str, callable] = {}


def check(check_id: str):
    def register(fn):
        CHECKS[check_id] = fn
        return fn
    return register


def _kron_chain(ops: list[np.ndarray]) -> np.ndarray:
    out = ops[0]
    for op in ops[1:]:
        out = np.kron(out, op)
    return out


SX = np.array([[0, 1], [1, 0]], dtype=complex)
SY = np.array([[0, -1j], [1j, 0]], dtype=complex)
SZ = np.array([[1, 0], [0, -1]], dtype=complex)
I2 = np.eye(2, dtype=complex)


def _sum_sigma_x(m_qubits: int) -> np.ndarray:
    total = np.zeros((2 ** m_qubits, 2 ** m_qubits), dtype=complex)
    for m in range(m_qubits):
        ops = [I2] * m_qubits
        ops[m] = SX
        total += _kron_chain(ops)
    return total


@check("norm-sum-sigma-x")
def check_norm_sum_sigma_x():
    """R2 p.5 claims ||sum_m sigma_x^m|| = 2M. Truth: M. The 2 belongs to the gap
    derivative |d(e_a - e_b)/dx| <= 2*M*beta, so g <= 2M*beta survives with the
    corrected middle step."""
    for m_qubits in (1, 2, 3):
        norm = float(np.linalg.norm(_sum_sigma_x(m_qubits), ord=2))
        if not np.isclose(norm, m_qubits, atol=1e-10):
            return False, f"norm at M={m_qubits} is {norm:.6f}, expected M={m_qubits}"
        if np.isclose(norm, 2 * m_qubits, atol=1e-10):
            return False, f"norm at M={m_qubits} matches the printed 2M - printed text would be right"
    return True, "||sum sigma_x|| = M for M=1,2,3; printed 2M is wrong; g <= 2M*beta survives via the gap"


def _random_pure_two_qubit(rng: np.random.Generator) -> np.ndarray:
    psi = rng.normal(size=4) + 1j * rng.normal(size=4)
    return psi / np.linalg.norm(psi)


def _concurrence(psi: np.ndarray) -> float:
    yy = np.kron(SY, SY)
    return float(abs(psi.conj() @ yy @ psi.conj()))


@check("purity-concurrence")
def check_purity_concurrence():
    """R2 Eq.(10) second line prints Tr rho_1^2 = (1+C^2)/2. Truth: 1 - C^2/2.
    The headline sum rule sum <sigma>^2 = 2 - 2C^2 is consistent only with the
    corrected line: sum = 2(Tr rho_1^2 + Tr rho_2^2) - 2 = 4(1 - C^2/2) - 2."""
    rng = np.random.default_rng(7)
    for _ in range(200):
        psi = _random_pure_two_qubit(rng)
        rho = np.outer(psi, psi.conj())
        rho1 = np.trace(rho.reshape(2, 2, 2, 2), axis1=1, axis2=3)
        purity = float(np.real(np.trace(rho1 @ rho1)))
        c = _concurrence(psi)
        power = 0.0
        for m in range(2):
            for pauli in (SX, SY, SZ):
                ops = [I2, I2]
                ops[m] = pauli
                power += float(np.real(psi.conj() @ _kron_chain(ops) @ psi)) ** 2
        if not np.isclose(purity, 1 - c ** 2 / 2, atol=1e-10):
            return False, f"Tr rho_1^2 = {purity:.8f} vs corrected 1 - C^2/2 = {1 - c**2/2:.8f}"
        if np.isclose(purity, (1 + c ** 2) / 2, atol=1e-10) and not np.isclose(c ** 2, 1 - c ** 2, atol=1e-8):
            return False, "printed (1+C^2)/2 matched - printed text would be right"
        if not np.isclose(power, 2 - 2 * c ** 2, atol=1e-10):
            return False, f"sum rule violated: {power:.8f} vs {2 - 2*c**2:.8f}"
    return True, ("200 random pure states: Tr rho_1^2 = 1 - C^2/2 exact; printed (1+C^2)/2 wrong; "
                  "headline sum rule 2-2C^2 consistent only with the corrected line")


def run_all() -> dict[str, tuple[bool, str]]:
    return {check_id: fn() for check_id, fn in CHECKS.items()}


def main() -> int:
    results = run_all()
    failed = 0
    for check_id, (passed, detail) in results.items():
        print(f"{'PASS' if passed else 'FAIL'} {check_id}: {detail}")
        failed += 0 if passed else 1
    print(f"{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
