# The ground state survives in the scaled mean-force Hamiltonian

A first derivation and finite-bath control, prepared by Root at the author's request. This note supplies exact identities and a controlled small-coupling route; it does not claim the general continuum spin–boson problem has been solved.

## The information that survives cooling

Let the reduced equilibrium state be
\[
\rho_S(\beta)=\frac{\operatorname{Tr}_B e^{-\beta H_{SB}}}{\operatorname{Tr}_{SB}e^{-\beta H_{SB}}},\qquad
K_S(\beta)=-\log\rho_S(\beta).
\]
The mean-force definition implies the exact relation
\[
\beta\left(H_{\rm MF}-\frac{\operatorname{Tr}H_{\rm MF}}{d}I\right)
=K_S-\frac{\operatorname{Tr}K_S}{d}I.
\]
The omitted scalar fixes the free-energy reference and has no effect on the normalized state.

Suppose the global ground state is unique and its reduced state \(\rho_0\) is full rank. If \(\rho_S(\beta)\to\rho_0\), continuity of the matrix logarithm gives
\[
\beta H_{\rm MF}^{\rm tf}(\beta)\longrightarrow[-\log\rho_0]^{\rm tf}.
\]
Thus the non-scalar mean-force Hamiltonian goes to zero as temperature, while its dimensionless product with inverse temperature retains the entire reduced ground state. Taking the limiting Hamiltonian first discards precisely that information. For a finite gapped global system the convergence of the state is exponentially fast; a gapless continuum requires its own convergence analysis. Rank-deficient limiting states require a separate support analysis.

For a qubit, write \(\rho_0=(I+\mathbf r_0\cdot\boldsymbol\sigma)/2\). Then
\[
H_{\rm MF}^{\rm tf}(\beta)
\sim-\frac{\operatorname{arctanh}|\mathbf r_0|}{\beta}
\widehat{\mathbf r}_0\cdot\boldsymbol\sigma.
\]
The splitting shrinks as \(1/\beta\); the occupations remain unequal and generally mixed. This is a concrete covariance between temperature and the effective energy scale, even at fixed physical system–bath coupling.

## A matched path that can be calculated

Take one oscillator, with \(\omega_b>\omega_q>0\),
\[
H=\frac{\omega_q}{2}\sigma_z+\omega_b b^\dagger b+g\sigma_x(b+b^\dagger).
\]
At small coupling, first-order ground-state perturbation adds
\(-g|\uparrow,1\rangle/(\omega_q+\omega_b)\) to \(|\downarrow,0\rangle\). Tracing the oscillator gives
\[
p_\uparrow(0,g)=\frac{g^2}{(\omega_q+\omega_b)^2}+O(g^4).
\]
At low temperature the leading thermal and virtual contributions are
\[
p_\uparrow(\beta,g)\simeq e^{-\beta\omega_q}+\frac{g^2}{(\omega_q+\omega_b)^2}.
\]
A useful joint path is
\[
g(\beta)=\kappa(\omega_q+\omega_b)e^{-\beta\omega_q/2}.
\]
Along it, the leading prediction is
\[
p_\uparrow e^{\beta\omega_q}\longrightarrow1+\kappa^2.
\]
Both terms survive in this scaled observable. The unscaled state still approaches the uncoupled spin ground state along these particular paths: a path-dependent scaled response is not, by itself, a family of different limiting ground states.

In the diagonal interaction-picture representation,
\[
\frac{p_\uparrow}{p_\downarrow}=e^{-\beta\omega_q+2\Delta_z}.
\]
The same matched approximation therefore yields
\[
\Delta_z\simeq\frac12\log(1+x),\qquad
x=\frac{g^2e^{\beta\omega_q}}{(\omega_q+\omega_b)^2}.
\]
Its expansion \(x/2-x^2/4+\cdots\) illustrates why finite operator closure need not mean coefficient termination. Resumming the scalar logarithm produces the cancellation against the bare Gibbs scale that retains ground-state dressing. This is an asymptotic candidate to extend and bound, not the exact all-coupling influence exponent.

The supervised calculation compares the physical Gibbs partial trace with the independently traced lowest eigenvector at oscillator cutoffs32 and48. It checks the weak-coupling coefficient, three matched paths, and the scaled mean-force limit. The first temperature endpoint \(\beta\omega_q=30\) did not meet the prescribed state-error target for \(g/\omega_q=1\); that result is retained. A separate colder endpoint80 tests convergence without changing the target. The figure displays the curves through30 for readability.

## The exact Lorentz structure

Represent an unnormalised positive qubit operator by
\[
R=\tfrac12(x^0I+\mathbf x\cdot\boldsymbol\sigma),\qquad
4\det R=(x^0)^2-|\mathbf x|^2.
\]
For \(A\in SL(2,\mathbb C)\), the congruence \(R\mapsto ARA^\dagger\) preserves this determinant and acts as a proper Lorentz transformation on the associated four-vector. This is an established spinor correspondence; its application here is thermal recombination.

For \(H_Q=\omega_q\sigma_z/2\), the thermal factor is
\[
A=e^{-\beta H_Q/2}=e^{-\eta\sigma_z/2},\qquad\eta=\beta\omega_q/2.
\]
Direct multiplication gives
\[
x^{0\prime}=x^0\cosh\eta-x^z\sinh\eta,\quad
x^{z\prime}=x^z\cosh\eta-x^0\sinh\eta,
\]
with transverse coordinates unchanged. Normalising the trace gives
\[
r_z'=\frac{r_z-\tanh\eta}{1-r_z\tanh\eta},\qquad
\mathbf r_\perp'=\frac{\mathbf r_\perp}{\cosh\eta(1-r_z\tanh\eta)}.
\]
The nonlinear normalized map follows from a linear Lorentz action on the unnormalised cone.

When the global spin–bath ground state is pure, the eigenvalues of its reduced spin state are the squared Schmidt coefficients. Hence \(\det\rho_0=(1-|\mathbf r_0|^2)/4\) determines its entanglement entropy. Entanglement and this Lorentz-cone invariant are therefore linked exactly. Identifying correlations with physical spatial geometry still requires a construction relating multiple subsystems and their observables.

## Temperature and a clock

For a Gibbs state \(\rho=e^{-\beta H}/Z\), \(K=-\log\rho=\beta H+\log Z\). With the convention \(O(s)=e^{isK}Oe^{-isK}\), comparison with Heisenberg evolution gives \(t=\hbar\beta s\). Temperature fixes the conversion from dimensionless modular flow to physical time when the Gibbs generator is the physical Hamiltonian. The modular flow of a reduced mean-force state need not equal its actual dissipative real-time evolution.

Adding levels enlarges the positive-operator geometry. It does not by itself specify spacetime dynamics. The current N-level metric/term interpretation should be re-derived before assigning stress–energy, spatial or temporal meanings.

## Primary connections and next calculation

- Verstraete, Dehaene and De Moor, Local filtering operations on two qubits: https://arxiv.org/abs/quant-ph/0011111 (Lorentz/filter correspondence).
- Connes and Rovelli, thermal time hypothesis: https://arxiv.org/abs/gr-qc/9406019 (state-induced flow).
- Van Raamsdonk, Building up spacetime with quantum entanglement: https://arxiv.org/abs/1005.3035 (entanglement/connectivity in a quantum-gravity setting).
- Ryu and Takayanagi: https://arxiv.org/abs/hep-th/0603001 (entropy/area relation in AdS/CFT).

These primary connections are recorded for the literature pass; their abstracts were checked here, not their complete proofs.

The next substantive target is the corrected ordered influence logarithm for a general spectral density, with a uniform asymptotic control along the claimed dual path. Track the physical reduced state, auxiliary influence state and any symmetry-selected sector separately. The purpose is to extract a checkable constructive solution, not to replace the full problem by its easiest limit.
