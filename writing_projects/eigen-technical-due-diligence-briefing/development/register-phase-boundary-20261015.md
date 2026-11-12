# Register sharing as an optimisation phase diagram

Author-requested extension of the shared-register example, 15 October 2026.
Origin: authored algebraic development of the already-read Self-Consistent Loss Geometries model. No thermodynamic limit or independent formal verification is asserted.

Let q,a,b be in R^2, a=(1,0), b=(cos theta,sin theta), 0<=theta<=pi. Each task has quadratic loss ||q-a||^2/2 or ||q-b||^2/2. The shared objective weights these by alpha and 1-alpha, adds gamma alpha(1-alpha)d^2 and 2 eta(alpha-1/2)^2, with d^2=2(1-cos theta), gamma>=0 and eta>0. A separated representation minimises both task losses and pays C_part>=0.

Completing the square gives q*=alpha a+(1-alpha)b. Put A(theta)=(1/2+gamma)d^2. The remaining shared objective is

A alpha(1-alpha)+2 eta(alpha-1/2)^2
= A/4+(2 eta-A)(alpha-1/2)^2.

Therefore balanced sharing alpha=1/2 minimises when A<2 eta. Suppression alpha=0 or 1 minimises when A>2 eta. At A=2 eta every alpha is degenerate. The global optimum with a partition choice is

L*=min{C_part,A(theta)/4,eta/2},
C_crit(theta)=min{(1/2+gamma)(1-cos theta)/2,eta/2}.

Splitting is strictly preferred for C_part<C_crit. Sharing is strictly preferred for C_part>C_crit, with its balanced/suppressed subregion as above. Equality gives tied representations. At generic crossings the minimum cost is continuous but kinked and the discrete optimal register choice switches. This is an optimisation phase boundary in a finite model, not a thermodynamic singularity or empirical training transition.

For gamma=1, eta=0.8, the sharing subregions meet at theta_att=acos(1-0.8/1.5)=1.0852782044993055, C_part=0.4. Below C_part=0.4, the split boundary is theta_split=acos(1-2 C_part/1.5), when the argument is in [-1,1]. At C_part=0.25 this gives 0.8410686705679301, the slice of the existing figure. Above 0.4, suppression provides a cheaper alternative to splitting for all large angles. The plateau matters: the fixed-register model can avoid conflict by abandoning an evaluator.

Figure: theta on the horizontal axis, C_part on the vertical axis. Three regions distinguish balanced sharing, separate registers, and shared register with one evaluator suppressed. Solid boundaries mark ties. A dashed C_part=0.25 slice links to the earlier loss curves. No region is labelled beneficial without the declared objective.

Documentary basis: reading/shared-register-and-prx-interpretation-20261015.md SHA77b50c6d0c9899d205f66afd614e127f162cb9f915af1239ad5d4a0a64f83299. Exact source editions and their numerical producer remain identified there. Existing dd:shared-register-crossing and its deterministic result are preserved.

Checks: the declared producer evaluates the analytic boundary, compares alpha-grid minimisation with the closed form at a finite set of angles, checks balanced/interior and suppressed/endpoint optima, and verifies equality at the slice crossing and meeting point. Numerical checks test the implemented finite model, not the general symbolic proof.
