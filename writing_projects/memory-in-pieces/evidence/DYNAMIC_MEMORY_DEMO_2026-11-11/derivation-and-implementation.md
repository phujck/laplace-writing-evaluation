# Dynamic Memory - witnessed updates and selective query propagation

Author-origin derivation with executable finite checks. FORMAL_NOT_CHECKED.
Independent scientific and reader judgement remain pending. No manuscript source was edited.

## Exact finite domain

Fix factor order A then B. More generally, take a finite ordered categorical empirical law p with positive integer source weights, including an explicit unknown category when one is present. Prefixes are identified only when their NORMALISED suffix laws agree. Each state a at cut g has deterministic successor delta_g(a,x) and reduced rational probability t_g(a,x), summing to one over its supported symbols. This is the conditional-state quotient implemented by gpu_state.build_state, not a claim that arbitrary preparations or source filters share that quotient.

For 0<=f_g(x)<=1 set
  M_g^f[b,a] = sum_{x:delta_g(a,x)=b} t_g(a,x) f_g(x).
Its columns sum to at most one, with equality for unfiltered steps. Starting at the one-dimensional root with mass1, expanding every supported path gives
  1^T M_{d-1}^f ... M_0^f = sum_x p(x) product_g f_g(x_g).
The exact adjoint recurrence is
  m_g(a)=sum_x t_g(a,x) f_g(x) m_{g+1}(delta_g(a,x)), m_d=1.
Thus forward mass, backwards conditional messages and the direct empirical expectation coincide. All-ones suffixes have message1. This is the actual gpu_state.contract recurrence, although that implementation evaluates rational transitions in float32/64. Its certified mass and integer_contraction primitive-multiplier/overflow domains must not be replaced by a claim that ordinary floating contraction is exact integer arithmetic. The new standard-library fixture uses Fraction, not a new run of the CUDA algorithms.

An explicit auxiliary channel has Kraus operators
  K_(b,a,x)=sqrt(t_g(a,x) f_g(x)) |b><a|.
Their completeness sum is diagonal with entries sum_x t f. The map is CP and trace-nonincreasing for these positive filters, trace-preserving when unfiltered. On diagonal populations it reproduces M. A conditional answer divides numerator by conditioning mass only when that denominator is positive. This normalisation is nonlinear. Denominator zero means UNDEFINED. Signed or greater-than-one factors remain valid observable contractions but do not in general define these trace-nonincreasing instruments.

Computational factor order is not elapsed physical time. Source edits change the empirical law and can split or merge continuations. The transition table must then be updated, not reused as a universal channel on a new initial correlation structure.

## Amplitude environment and supported gauge

Raw amplitude matrices A_x[b,a]=sqrt(t_g(a,x)) have deterministic edges but generally nonorthogonal suffix environments. The initial laws (.8,.2) and (.2,.8) yield
  sum_x A_x^dagger A_x = Z = [[1,.8],[.8,1]],
not I. CP alone does not establish trace preservation in that raw label basis.

Let Z_g=sum_x A_x^dagger Z_(g+1) A_x be the actual suffix Gram environment. On its support, define B_x=Z_(g+1)^(1/2) A_x Z_g^(-1/2). Then
  sum_x B_x^dagger B_x = projector_onto_support(Z_g).
It is I only on the supported quotient. Null directions require the support/pseudoinverse, not an arbitrary inverse. With compatible boundary preparation and the same environments, the gauge cancels between successive factors and preserves the joint outcome probabilities. Multiplying B_x by sqrt(f_g(x)) gives a selective instrument on that support.

The checked run verifies the raw .8 off-diagonal counterexample, the nonsingular two-state environment gauge, its joint probabilities and a singular prequotient support projector at float64 tolerance1e-12. These are small explicit fixtures, not a generic quantum dynamical theorem or formal proof checker.

## Distinct continuous propagator

For a fixed finite reversible Markov generator G and positive stationary pi, L=W^(-1/2) G W^(1/2) is symmetric nonpositive. Fix isometry U, Q=I-UU^T, A=U^T L U, D=U^T L Q and L_Q=QLQ on Ran(Q). Eliminating omitted coordinates gives exactly
  z'(t)=A z(t)+D exp(t L_Q) eta(0)
       +integral_0^t D exp((t-s)L_Q) D^T z(s) ds.
The omitted initial-state term and memory kernel are part of this relation. Signed retained coordinates are not density matrices. The positive coarse propagator C exp(tG) R is stochastic for the declared preparation p(0)=R p_c(0), but need not be a semigroup. General correlated preparations add C exp(tG) eta_raw. This continuous calculation has different objects and a declared time/analysis-scale domain. No continuous4x4 numerical fixture was run in this bounded unit.

## Genuine incremental implementation

Every controlled group is an actual immutable text-document revision. The active source corpus changes its selected document contents, adds group02 and removes group01. Each accepted revision carries content hash and located assertion/count spans. Distinct group IDs contribute distinct weighted record batches. Reusing the same revision is idempotent. A conflicting group/document identity is refused rather than double-counted.

The producer retains source-to-fact/witness incidence, tuple counts and an UNMERGED prefix trie. An update retracts the old contribution and adds the new one. Only the affected tuple paths are copied. Their reduced rational outgoing laws and successor signatures are hash-consed. Active raw-prefix occurrences carry explicit reference counts, while archival canonical signatures/messages remain immutable and their retained memory is charged. Shared states can split without losing prefix provenance.

Affected ancestor-prefix message bindings are explicitly invalidated. Immutable canonical-message cache entries remain valid for their original state and can be reused if an exact signature recurs. No source-wide parse or quotient rebuild is called inside change(). Dictionary/child-pointer copying and signature slots are counted, not hidden.

A separate source catalogue follows the declared event protocol outside the engine. Fresh full rebuild reparses ALL active document files using an independent token parser, reconstructs conditional suffix laws, and checks every source/witness and prefix law. A third grammar path directly enumerates weighted rows. Each of16 fixed Boolean queries is checked against forward channel mass, backwards cached messages, full rebuild and direct integer/Fraction count. Nine states give144 query-state checks. Active refcounts, old-root immutability, removed witnesses, zero support, replay, merge/split and atomic overflow/group refusal are checked.

The original gpu_state.py explicitly supports immutable snapshot followed by FULL build_state. This new tiny path-copy producer does not modify it and is not evidence that the old implementation was already incremental.

## Scope and operation-count statement

For fixed factor order d and bounded cardinality c, one changed tuple touches at most d+1 unmerged prefix nodes. This producer copies/examines the child slots on those paths and hashes their rational transition signatures. With fixed Q queries it may invalidate up to Q bindings at each changed ancestor, then recompute through the affected dependency cone. Source parsing/hashing costs the changed byte length. Rational gcd/bit complexity and dictionary costs are not zero. If many tuples change, prefix/quotient effects or dependent observables can spread globally. This is not a universal constant or logarithmic update-cost claim.

Observed tiny-fixture metrics, oracle work, process CPU/RSS and archived cache growth are in the raw checked result. Timings include tracing and Python overhead and are not a scaling benchmark or measured superiority over the full rebuild. Optional larger replicas remain uncommissioned.

## Evidence and standing

The checked run is run-d2f6d3cff17f0fbe. Its exact result hash is
10f22f152572ec0141995aaceedaf82cf48dfe0e530814837883bb0ab09db35b.
The earlier run-ffd067439f493b83 is retained: its arithmetic passed, but its oracle source catalogue inherited the engine. oracle-correction.json records that limitation and the independently driven catalogue added before the checked run.

The checked recovered conditional values are4/5 ->3/4 ->3/5 ->3/4. Replay leaves3/4. A later continuation merge and split preserve that conditional while altering the other context. Removing its last positive numerator witness gives0, then removing all conditioning support gives UNDEFINED. The source weights and expected values were frozen before either execution.

These checks establish only this controlled finite implementation outcome, with an author-origin derivation awaiting independent review. They establish no new benchmark-reader accuracy, no scientific acceptance of the paper, no universal asymptotic gain and no external publication.
