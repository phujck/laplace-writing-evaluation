# D4b v1 - Finite-horizon actuation with explicit terminal constraints

Author-origin mathematical development, saved BEFORE numerical checks. Independent-science-d4b PENDING. Formal verification NOT_CHECKED.
Work WORK-040fb19d62c44132809c9f0e0efcbd33. Original parent WS-f989d076ce2a4ce0aab628e6712f800b, turn WT-c89b25f118e94ddca03762c1a8e12e28.
No original manuscript/script/figure or accepted D1/D4a/D2 bytes are changed.

## T1. The task must precede its cost

Take integer L>=1, integer H>=0, state x_t in R^L, scalar input u_t, and t=0,...,H-1:
x_(t+1)=A x_t+B u_t, A=a I+c S, B=g e1.
S has ones on its first subdiagonal, S^L=0. We call e_L the top and e1 the base. The shift is a=0. The persistent variant has a!=0, with a=1 allowing accumulated local state. Neither a=0 nor a=.5 is a chain of unit integrators. We make no stabilisability/maintenance claim by naming a persistent model.

Choose x0, a terminal horizon, a target and an SPD input metric R_H BEFORE optimising. Chronological u=(u0,...,u_(H-1)) gives
x_H=A^H x0+C_H u,
C_H=[A^(H-1)B,...,AB,B].
For a full-state target x_star the required defect is q=x_star-A^H x0. For the scalar top-output target y_H=ell x_H=delta with ell=e_L^T, the required defect is d=delta-ell A^H x0. Other terminal components are free in the output task. For a fair nested comparison use x_star=delta e_L and x0=0. A target of all ones is a DIFFERENT full-vector task, even though its top is also one.

Effort is J=u^T R_H u. Uniform per-update weight R_H=w I, w>0, is used for horizon comparisons. With state units Z shared across levels, input units U, a and c dimensionless, g has units Z/U and w effort-units/U^2. J and E0=w delta^2/g^2 have the declared effort units, not necessarily Joules. There is no sampling-interval factor unless a continuous-time/discretisation model supplies one. A top-output rescaling ell->h ell also changes target-coordinate interpretation. A state-coordinate change T must transform A,B,ell,x0 and x_star consistently. Merely rescaling a coefficient while holding physical targets/metric fixed is a different task.

All finite main controls below are dimensionless illustrative coordinates, zero initial state and unit target, not calibrated thermodynamic heat, entropy, maintenance or physical intervention cost.

## T2. Reachability and impulse response

By the binomial expansion of commuting aI and cS, for j>=0,
v_j=A^j B=g sum_(i=0)^min(j,L-1) binom(j,i) a^(j-i)c^i e_(i+1).
Polynomial conventions include 0^0=1. For the top,
h_j=ell v_j=0 for j<L-1,
h_j=g c^(L-1) binom(j,L-1) a^(j-L+1) for j>=L-1.
Thus v_j=c^j g e_(j+1) for a=0,j<L, and zero for j>=L.

If g!=0 and c!=0, the first min(H,L) power columns are triangular, with nonzero successive diagonal entries g c^j. They span exactly the first H coordinates for H<L and all L coordinates for H>=L. Hence rank C_H=min(H,L). Ordering columns chronologically reverses their display but not rank. For H<L a full target is reachable iff its defect q has zero entries after component H. For H>=L every full-state defect is reachable. The top-output nonzero defect is unreachable for H<L and reachable for H>=L.

At H=0 the map has no input columns and x_H=x0. Only zero defect is reachable, with the empty control and zero effort. If g=0 all defects except zero are unreachable. If c=0,g!=0,H>=1, only the base can be controlled (rank1), so the top for L>1 cannot be moved from zero. L=1 remains a scalar controllable system when g!=0,H>=1, independent of c. These cases must not be smuggled into an inverse formula.

## T3. Weighted minimum effort, including singular cases

Let M=C_H for a full defect b=q, or M=ell C_H for a scalar defect b=d. First test b in range(M). If not, the exact constrained problem is INFEASIBLE and its extended minimum is +infinity. A pseudoinverse applied to an unreachable target only minimises residual in a different least-squares problem. For example, at H=L-1 and zero initial state the missing top direction has W^+ e_L=0. The number e_L^T W^+ e_L=0 is NOT the energy required to hit the nonzero top target.

For SPD R_H set F=M R_H^(-1/2). If b is reachable, the least Euclidean-norm v subject to Fv=b is F^+b. Writing u=R_H^(-1/2)v gives the unique weighted minimum
u_star=R_H^(-1) M^T (M R_H^(-1) M^T)^+ b,
J_min=b^T (M R_H^(-1) M^T)^+ b.
Proof: F^+b is perpendicular to ker(F). Every other feasible v differs by a kernel vector, so Pythagoras increases its squared norm unless that vector is zero. The identity F^+=F^T(FF^T)^+ gives the displayed expressions. Positive definiteness of R makes the minimiser unique even when the output Gramian is singular. For b=0 the optimum is always u=0,J=0. For H=0 use the empty-control convention, not a nonexistent positive-size R inverse.

For uniform w, define W_H=C_H C_H^T=sum_(j=0)^(H-1) v_j v_j^T. The scalar-output minimum, when d!=0 and V_H=ell W_H ell^T>0, is w d^2/V_H and u_star=d C_H^T ell^T/V_H. A full reachable defect costs w q^T W_H^+ q. Inverting ONLY ell W_H ell^T does not solve the full-state task in general.

The scalar task is a relaxation of the full task if ell x_star=delta and the same x0,horizon/metric are used. Therefore J_output<=J_full when full reachability holds. Equality occurs iff the unique scalar optimum also meets the full target, not never and not always.

## T4. What the nilpotent R5 shift actually establishes

For a=0,g!=0,c!=0,x0=0,
W_H=g^2 diag(1,c^2,...,c^(2(min(H,L)-1)),0,...,0).
For nonzero scalar delta, H<L is unreachable. For H>=L only u_(H-L) reaches the top at H. Thus
J_output=E0 c^(-2(L-1)), E0=w delta^2/g^2,
with that single input delta/(g c^(L-1)) and every other input zero.
For the full target delta e_L, the same input has ALL other terminal components zero. Consequently full/top costs coincide exactly in this special case. For a general full vector q, H>=L,
J_full=(w/g^2) sum_(i=1)^L q_i^2 c^(-2(i-1)).
Additional nonzero components add a task, not a disagreement between methods. Once H>=L the shift Gramian saturates, so extra time does not reduce either of these zero-initial-state terminal costs.

R5_check.py cascade_A directly builds this shift. top_reachability computes its top Gramian entry. energy_via_control_law actually compares to a FULL pure-apex target, which agrees with top-only here because of the diagonal Gramian. It checks residual>1e-8 before returning a finite cost. Its comment describes chronological columns but implementation stacks ascending powers [B,AB,...], so a returned ascending-power control would need reversal before chronological simulation. Rank and squared norm are unchanged by that permutation, so this discrepancy does not invalidate that shift-cost comparison. Our new checks use chronological columns and explicitly simulate the control.

A terminal pulse at one selected H is not sustained reconfiguration. After inputs stop, a shift state disappears in at most L further steps. For a=1, the free A dynamics can retain or propagate state, but a terminal constraint alone proves no tracking, maintenance or robust persistent mandate.

## T5. Persistent chains and horizon benefit

For g c!=0,x0=0,nonzero delta,uniform w,
V_H=g^2 c^(2(L-1)) sum_(j=L-1)^(H-1) binom(j,L-1)^2 a^(2(j-L+1))
for H>=L. At H=L this sum is one, so the output-only cost equals the shift cost regardless of a. Its optimum generally leaves lower components nonzero if a!=0 and L>1. Full pure-apex constraints may therefore cost more.
For a!=0 every additional summand for H>=L is positive, so the top-only minimum decreases STRICTLY with each extra update, under these exact assumptions. It is constant after L when a=0. This is not a statement about nonzero x0, whose required defect changes with horizon, or arbitrary nonuniform time weights.

For full-state targets at zero initial state and uniform w, W_(H+1)=W_H+v_H v_H^T. For H>=L the chain Gramian is positive definite. Sherman-Morrison gives
J_H-J_(H+1)=w (q^T W_H^(-1) v_H)^2/(1+v_H^T W_H^(-1)v_H)>=0.
There is a strict improvement iff that numerator is nonzero. Do not claim strict improvement for every full-state q. Before full rank, a target reachable at H remains reachable at H+1 for zero x0, because range(W_H) grows. Its minimum cannot increase: in chronological terms prepend a zero input to the old control, leaving x_H's target contribution at H+1 unchanged. The same argument covers singular reachable cases, with uniform cost.

A rational nonzero equality example is L2,a1,c1/2,g=w=1,H2->3,q=(6,1). W2=[[2,1/2],[1/2,1/4]], W2^(-1)v2=(-1,6), so q^T W2^(-1)v2=0. Both full-state costs are20. This target is deliberately a different full-vector task from q=e2.
A contrast with the SAME unit top target: L2,a1,c1/2,g=w=1,H2 has J_output=4,J_full(e2)=8. At H3 they are4/5 and2 respectively. At H4 they are2/7 and4/5. This explicit calculation is an analytic prediction to test, not a desired-output constant to paste into the producer.

## T6. Scaling and the static hierarchy are separate assumptions

Uniform target defect scaling b->s b scales J by s^2. Input gain g->h g at fixed physical input coordinates divides J by h^2. Uniform metric w->k w multiplies J by k. Reparameterising input as u_tilde=kappa u with g_tilde=g/kappa and w_tilde=w/kappa^2 leaves physical effort invariant. A similarity state change T, with A_tilde=TAT^-1,B_tilde=TB,ell_tilde=ell T^-1 and target/initial state multiplied by T, preserves the feasible controls and effort. These facts specify the metric and units, not a calibration of heat.

D4a's static law K(N,L)=K_ref(N/N_ref)^p d^(L-1) and actuation transmission c are different quantities. Their common L and any relation such as d=c^2 are ADDITIONAL modelling assumptions, not consequences of an RG label or reversal of majority compression. If independently justified static and actuator models share an admitted architecture, intersect strict static feasibility with reachable/budget-feasible actuation:
F(N)={architecture: K(N,architecture)<Kc, target defect reachable at H, J_min<=Emax}.
Use actual factorisation/admitted spans and exact-versus-proxy distinctions from accepted D4a. No universal scalar depth ceiling follows for persistent chains from the shift-only exponential law. Even for shift, the integer/log ceiling uses Emax/E0 and explicit c, whereas critical-size extraction uses reciprocal total gain exponent p. Shared notation cannot establish that the same eigenvalue prices both walls.

The inspected old 07_window.tex calls a shift a chain of integrators and promotes common-coupling/energetic/global-freeze claims. D4b establishes the precisely declared terminal tasks only. It does not revalidate R5_probe dynamics, universal thermodynamics, Holling/society mappings, physical majority aggregation or the old complete wedge narrative. Those are not rescued by the small algebra checks.

## Exact source basis

- laplace:synthetics papers/adaptive-normal-form/scripts/R5_check.py @ sha256:8e74a837901bbf9149e857980ffa9b05c070e78e795b159fb8c62110dfd6a445, lines1-189.
- laplace:synthetics papers/adaptive-normal-form/workflow/state/derivations/R5_derivation.md @ sha256:3d011ee8e78ec8c51a2631c1d8a8ea0a5f645a1c6b3403166b12e4915b2de179, lines1-54.
- laplace:synthetics papers/adaptive-normal-form/workflow/state/results/R5_inertial_window.md @ sha256:e4c8c3b6f2ac37b2781bad493e41357f3fe82d8b3eccf707c3bb25e4fe6f93ee, lines1-59.
- laplace:synthetics papers/adaptive-normal-form/manuscript/tex/sections/07_window.tex @ sha256:2c43fb39c421b4d0020ed480379a6f5dbc3161cb043096328be4d0cae814baf8, lines1-181.
- laplace:writing_projects/adaptive-normal-form-aek9/D4a/v1/03-conditional-resource-proof.md @ sha256:ca2425f9d2df11cc6fab4d6dbbbad3e714374ccbeb2d4adb7cf30ba096ca3951, lines1-51.
- laplace:writing_projects/adaptive-normal-form-aek9/D4a/v1/result-repair-report.json @ sha256:27a8e8776d0fb7cce90fbe1f12120ddcf6787fea56e7b83edbc3fa6eaa5b4e39, lines1-3592.
- laplace:synthetics papers/the-phases-of-hierarchy/manuscript/tex_v4/sections/D_cost_functions_inertia.tex @ sha256:3860f3b7bde9bdb6574a7185f07eca8fa0fa9300ebd3aac65a2629081e009200, lines1-78.

Passage authority: R5_check.py cascade_A/top_reachability/energy_via_control_law, original R5 Derivation/[REACH]/Symmetry filter and ledger Statement/Machine map, 07_window.tex sec:window/eq:emin/eq:Lambda/eq:window/eq:Nstar/fig:4 caption, Phases app:cost_functions Control Inertia, accepted D4a proof R1-R4 and report analytic_findings/resource. These bodies were actually read, not inferred from metadata. D4a report historical queue/status text is not current D2/D4a standing. Current closed owner standing is separate.

Status: author proofs and analytic predictions only. A small declared check will test finite cases, not provide independent or formal verification. All raw outputs and failures must remain, fresh independent-science-d4b covers ALL handoff pins (inputs=[]).
