"""UP and DOWN — the paired promotion/prolongation operators of the graded conceptric.

UP is mathematical coarsening, not deposit placement (the codex amendment on the claude
UpAct/1 proposal, 2026-08-24): a coarse node derives ATOMICALLY, from the same children,
both of its faces — the semantic human face and the retained spectral frame — with typed
membership, provenance, and a MEASURED truncation residual. A residual that is high or
unmeasurable forces DOWN: the act may not call itself sufficient, and every coarse node
carries the exact child handles descent needs. DOWN is the paired prolongation under the
same declared metric: exact children back, plus the frame's reconstruction of any child
and the round-trip residual that prices it.

Refusals, by construction rather than convention:
  - chi (retained rank) and phi (the residual dial) are DECLARED inputs; there is no
    default and no silent optimum — omitting them is a refused act, not a chosen one.
  - the adjoint is claimed per (assumption, fibre, metric_version) only; nothing here
    asserts UP/DOWN are adjoint across fibres.
  - the kernel claims REPRESENTATION sufficiency only (truncation within phi, no
    degenerate cut). Goal/source-chain closure is a different typed residual, measured by
    the caller on declared planted probes — spectral energy never licenses it (the
    acceptance-boundary audit, 2026-08-24; the selector migration's proxy-saturation law).

This module is PURE: no filesystem, no clock, no store — deterministic functions over
typed values, so idempotence is content-addressed identity and the caller (the pen that
owns the event history) banks results through the one door. Operational wrapping —
dirtied-ancestor enumeration, runtime/device receipts, causality — is the accepted
claude-seat UpAct/1 layer and stays with the caller.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .errors import StateTransitionRefused
from .ids import chash

SCHEMA_UP = "atlas.up-act/1"
SCHEMA_DOWN = "atlas.down-act/1"
SCHEMA_NODE = "atlas.coarse-node/1"


def _require(condition: bool, message: str, **fields: object) -> None:
    if not condition:
        raise StateTransitionRefused(message, **{k: str(v) for k, v in fields.items()})


@dataclass(frozen=True)
class ChildLeaf:
    """One child entering a promotion: content-addressed text plus its vector."""

    handle: str                      # content address of the child's bytes
    text: str                        # the semantic face material (already digestible-grade)
    vector: tuple[float, ...]        # the child's embedding under metric_version

    def __post_init__(self) -> None:
        _require(bool(self.handle.strip()), "child handle must be non-empty")
        _require(len(self.vector) > 0, "child vector must be non-empty", handle=self.handle)


@dataclass(frozen=True)
class UpInputs:
    """Everything UP is REQUIRED to declare. No field has a default that chooses for you."""

    assumption: str
    fibre: str
    axis: str                        # the grade axis this promotion climbs
    from_grade: str | int            # children's coordinate on the axis
    to_grade: str | int              # the coarse node's coordinate (must differ)
    metric_version: str              # embedder/operator identity — pinned, never inferred
    grade_contract_id: str           # the NAMED GradeAxisContract the history adapter resolves
    chi: int                         # retained spectral rank — DECLARED, never optimised here
    phi: float                      # residual dial: truncation share above this forces descent
    coarse_to_fine: tuple[str | int, ...]   # the NAMED axis order — the contract UP is proven against
    children: tuple[ChildLeaf, ...]

    def __post_init__(self) -> None:
        for name in ("assumption", "fibre", "axis", "metric_version"):
            _require(bool(str(getattr(self, name)).strip()), f"{name} must be declared")
        _require(bool(self.grade_contract_id.strip()),
                 "a named grade-axis contract must be declared (grade_contract_id)")
        _require(len(self.coarse_to_fine) >= 2 and len(set(self.coarse_to_fine)) == len(self.coarse_to_fine),
                 "axis order must be a declared sequence of distinct coordinates", axis=self.axis)
        _require(self.from_grade in self.coarse_to_fine and self.to_grade in self.coarse_to_fine,
                 "axis order must contain both grade coordinates", axis=self.axis)
        _require(self.from_grade != self.to_grade,
                 "promotion must change the grade coordinate", axis=self.axis)
        _require(self.coarse_to_fine.index(self.from_grade) > self.coarse_to_fine.index(self.to_grade),
                 "promotion must go from finer to coarser on the declared axis "
                 "(a mislabeled DOWN is refused, never accepted as UP)", axis=self.axis)
        _require(self.chi >= 1, "chi must be a declared positive retained rank")
        _require(0.0 < self.phi <= 1.0, "phi must be a declared dial in (0, 1]")
        _require(len(self.children) >= 1, "promotion needs at least one child")
        dims = {len(c.vector) for c in self.children}
        _require(len(dims) == 1, "children must share one vector dimension",
                 dims=sorted(dims))
        handles = [c.handle for c in self.children]
        _require(len(set(handles)) == len(handles), "child handles must be unique")


@dataclass(frozen=True)
class SpectralFrame:
    """The retained rank-chi frame over the children, with its truncation priced."""

    basis: tuple[tuple[float, ...], ...]   # chi_kept rows, each a unit vector in metric space
    weights: tuple[float, ...]             # singular values kept, descending
    chi_declared: int
    chi_kept: int                          # min(chi_declared, rank available) — never padded
    truncation_residual: float             # share of spectral energy NOT captured, in [0, 1]
    degenerate_cut: bool                   # True when the cut fell inside a tied singular pair
    coordinates: tuple[tuple[float, ...], ...] = ()   # member-aligned chi_kept loadings — the
                                           # RETAINED STATE prolongation reconstructs from


@dataclass(frozen=True)
class CoarseNode:
    """One node at the coarser grade: both faces, from the same children, atomically."""

    schema_version: str = field(init=False, default=SCHEMA_NODE)
    node_handle: str = ""
    semantic_face: str = ""                       # the human face — mechanical, provenance-bearing
    semantic_sources: tuple[str, ...] = ()        # child handles the face's spans came from
    frame: SpectralFrame | None = None
    member_handles: tuple[str, ...] = ()          # typed membership: every child, exactly
    centroid: tuple[float, ...] = ()


@dataclass(frozen=True)
class UpResult:
    schema_version: str = field(init=False, default=SCHEMA_UP)
    act_handle: str = ""
    inputs_handle: str = ""
    node: CoarseNode | None = None
    residual_value: float = 0.0             # SPECTRAL truncation residual — representation only
    residual_within_phi: bool = False
    representation_sufficient: bool = False  # truncation within phi AND no degenerate cut —
                                             # says NOTHING about retrieval/goal closure
    goal_closure: str = field(init=False, default=(
        "unmeasured — closure residual on declared planted probes is the CALLER'S act; "
        "spectral energy never licenses goal sufficiency (the proxy-saturation law)"))
    forced_descent: str | None = None       # the continuation DOWN when representation fails
    adjoint_scope: str = ""                 # the ONLY scope any adjoint claim covers


@dataclass(frozen=True)
class DownResult:
    schema_version: str = field(init=False, default=SCHEMA_DOWN)
    act_handle: str = ""
    node_handle: str = ""
    child_handles: tuple[str, ...] = ()     # exact — descent's ground truth
    reconstructions: Mapping[str, tuple[float, ...]] = field(default_factory=dict)
    verified: bool = False                  # True only when COMPLETE originals were supplied
    round_trip_residual: float | None = None   # measured mean relative error, or None —
                                            # unmeasured NEVER masquerades as exact


# --------------------------------------------------------------------------- linear algebra
# Deliberately dependency-light: dense Gram-based decomposition, exact for the small child
# fan-outs a single promotion sees (the fold recurses; no promotion is corpus-sized). A GPU
# or sparse path is a caller-level substitution measured on the same contract, never a
# silent branch here.

def _transpose(m: Sequence[Sequence[float]]) -> list[list[float]]:
    return [list(col) for col in zip(*m, strict=True)]


def _matmul(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> list[list[float]]:
    bt = _transpose(b)
    return [[sum(x * y for x, y in zip(row, col, strict=True)) for col in bt] for row in a]


def _sym_eig(g: list[list[float]], sweeps: int = 64) -> tuple[list[float], list[list[float]]]:
    """Jacobi eigendecomposition of a small symmetric matrix — deterministic, no imports."""
    if os.environ.get("LAPLACE_REQUIRE_GPU") == "1":
        from .runtime import preload_cuda_libraries
        preload_cuda_libraries()
        try:
            import cupy as cp
            values, vectors = cp.linalg.eigh(cp.asarray(g, dtype=cp.float64))
            values = cp.asnumpy(values)[::-1]
            vectors = cp.asnumpy(vectors)[:, ::-1].T
            # Eigenvector signs are arbitrary; fix them before content addressing.
            for row in vectors:
                pivot = max(range(len(row)), key=lambda i: abs(row[i]))
                if row[pivot] < 0:
                    row *= -1
            return [max(float(v), 0.0) for v in values], vectors.tolist()
        except Exception as exc:
            raise StateTransitionRefused("GPU_REQUIRED: UP eigensolve unavailable") from exc
    n = len(g)
    a = [row[:] for row in g]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(sweeps):
        off = max((abs(a[i][j]), i, j) for i in range(n) for j in range(n) if i != j) \
            if n > 1 else (0.0, 0, 0)
        if off[0] < 1e-12:
            break
        _, p, q = off
        app, aqq, apq = a[p][p], a[q][q], a[p][q]
        theta = 0.5 * math.atan2(2.0 * apq, aqq - app) if aqq != app or apq else math.pi / 4
        c, s = math.cos(theta), math.sin(theta)
        for k in range(n):
            akp, akq = a[k][p], a[k][q]
            a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
        for k in range(n):
            apk, aqk = a[p][k], a[q][k]
            a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
        for k in range(n):
            vkp, vkq = v[k][p], v[k][q]
            v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    eigs = [(a[i][i], [v[k][i] for k in range(n)]) for i in range(n)]
    eigs.sort(key=lambda e: -e[0])
    return [max(e[0], 0.0) for e in eigs], [e[1] for e in eigs]


# --------------------------------------------------------------------------- the operators

def _semantic_face(children: Sequence[ChildLeaf], centroid: Sequence[float],
                   max_spans: int = 3) -> tuple[str, tuple[str, ...]]:
    """The human face at S1-minimum: centroid-nearest EXEMPLAR SPANS, verbatim, with their
    child handles as provenance. Mechanical and deterministic — an abstractive face is a
    judged upgrade that must beat this on the same gates, never a silent substitution."""
    def cos(u: Sequence[float], w: Sequence[float]) -> float:
        nu = math.sqrt(sum(x * x for x in u)) or 1.0
        nw = math.sqrt(sum(x * x for x in w)) or 1.0
        return sum(x * y for x, y in zip(u, w, strict=True)) / (nu * nw)

    ranked = sorted(children, key=lambda c: (-cos(c.vector, centroid), c.handle))
    kept = ranked[:max_spans]
    face = " · ".join(c.text.strip().replace("\n", " ")[:240] for c in kept)
    return face, tuple(c.handle for c in kept)


def up(inputs: UpInputs) -> UpResult:
    """Promote children to one coarse node: both faces from the same children, atomically,
    with the truncation priced and insufficiency forcing descent."""
    vecs = [list(c.vector) for c in inputs.children]
    n, dim = len(vecs), len(vecs[0])
    centroid = tuple(sum(v[d] for v in vecs) / n for d in range(dim))
    centred = [[v[d] - centroid[d] for d in range(dim)] for v in vecs]

    # Gram-side spectrum (n x n): eigenvalues are squared singular values of the child matrix.
    gram = _matmul(centred, _transpose(centred))
    eigvals, eigvecs = _sym_eig([row[:] for row in gram])
    total_energy = sum(eigvals)
    rank = sum(1 for e in eigvals if e > 1e-12 * (eigvals[0] if eigvals else 1.0))
    chi_kept = min(inputs.chi, rank) if rank else 0
    kept_energy = sum(eigvals[:chi_kept])
    residual = 0.0 if total_energy <= 1e-30 else max(0.0, 1.0 - kept_energy / total_energy)

    # A cut inside a tied pair is DECLARED, never smoothed: the retained frame is then
    # basis-dependent and the degeneracy is the reader's to see (the lens/degenerate case).
    degenerate = bool(
        0 < chi_kept < rank
        and total_energy > 1e-30
        and abs(eigvals[chi_kept - 1] - eigvals[chi_kept]) <= 1e-9 * max(eigvals[0], 1e-30)
    )

    basis: list[tuple[float, ...]] = []
    weights: list[float] = []
    for k in range(chi_kept):
        sv = math.sqrt(eigvals[k])
        if sv <= 1e-15:
            break
        row = [sum(eigvecs[k][i] * centred[i][d] for i in range(n)) / sv for d in range(dim)]
        norm = math.sqrt(sum(x * x for x in row)) or 1.0
        basis.append(tuple(x / norm for x in row))
        weights.append(sv)

    face, face_sources = _semantic_face(inputs.children, centroid)
    # the retained state: each member's loadings in the kept basis — what DOWN prolongs from
    coords = tuple(
        tuple(sum(x * b for x, b in zip(centred[i], row, strict=True)) for row in basis)
        for i in range(n)
    )
    frame = SpectralFrame(
        basis=tuple(basis), weights=tuple(weights),
        chi_declared=inputs.chi, chi_kept=len(basis),
        truncation_residual=residual, degenerate_cut=degenerate,
        coordinates=coords,
    )
    # identity binds the COMPLETE canonical payload: a handle with different content behind
    # it, or a different retained state, can never share an identity (the audit's defect 2)
    inputs_handle = chash({
        "schema": SCHEMA_UP, "assumption": inputs.assumption, "fibre": inputs.fibre,
        "axis": inputs.axis, "grade_contract": inputs.grade_contract_id,
        "order": list(inputs.coarse_to_fine),
        "from": inputs.from_grade, "to": inputs.to_grade,
        "metric": inputs.metric_version, "chi": inputs.chi, "phi": inputs.phi,
        "children": [chash({"handle": c.handle, "text": c.text,
                            "vector": [round(x, 12) for x in c.vector]})
                     for c in inputs.children],
    })
    node_handle = chash({
        "schema": SCHEMA_NODE, "inputs": inputs_handle,
        "face": face, "face_sources": list(face_sources),
        "members": [c.handle for c in inputs.children],
        "centroid": [round(x, 12) for x in centroid],
        "frame": {"weights": [round(w, 10) for w in weights],
                  "basis": [[round(x, 10) for x in row] for row in basis],
                  "coordinates": [[round(x, 10) for x in row] for row in coords],
                  "chi_kept": len(basis), "residual": round(residual, 12),
                  "degenerate": degenerate},
    })
    node = CoarseNode(
        node_handle=node_handle, semantic_face=face, semantic_sources=face_sources,
        frame=frame, member_handles=tuple(c.handle for c in inputs.children),
        centroid=centroid,
    )
    within = residual <= inputs.phi
    # a cut inside a tied block is basis-unstable: it can NEVER be sufficient (defect 3) —
    # the continuation names the cure (raise chi past the block, or retain it whole).
    # REPRESENTATION sufficiency only: goal/source-chain closure is measured by the caller
    # on declared planted probes (the acceptance-boundary audit) — never by spectral energy.
    sufficient = within and not degenerate
    if sufficient:
        continuation = None
    elif degenerate:
        continuation = (f"down(node={node_handle}) — chi={inputs.chi} cuts a tied singular "
                        f"block: raise chi to cover the degenerate block (or retain it "
                        f"whole); the retained frame is basis-unstable until then")
    else:
        continuation = (f"down(node={node_handle}) — truncation residual {residual:.4f} "
                        f"> phi {inputs.phi}")
    return UpResult(
        act_handle=chash({"up": inputs_handle, "node": node_handle}),
        inputs_handle=inputs_handle,
        node=node,
        residual_value=residual,
        residual_within_phi=within,
        representation_sufficient=sufficient,
        forced_descent=continuation,
        adjoint_scope=f"({inputs.assumption} | {inputs.fibre} | {inputs.metric_version})",
    )


def down(node: CoarseNode, *, children: Mapping[str, ChildLeaf] | None = None) -> DownResult:
    """Prolong FROM THE RETAINED STATE: centroid + basis + stored member coordinates are the
    whole reconstruction (the audit's defect 1) — descent needs no originals. ``children``,
    when supplied, plays exactly one role: VERIFICATION — the round-trip residual is measured
    against them, and a partial resolution is refused rather than silently part-verified."""
    _require(node.frame is not None, "down needs a framed node", node=node.node_handle)
    frame = node.frame
    _require(len(frame.coordinates) == len(node.member_handles),
             "frame coordinates must align with membership", node=node.node_handle)
    if children is not None:
        missing = [h for h in node.member_handles if h not in children]
        _require(not missing, "descent refused: unresolved member handles", missing=missing[:5])

    recon: dict[str, tuple[float, ...]] = {}
    errs: list[float] = []
    for i, h in enumerate(node.member_handles):
        approx = [0.0] * len(node.centroid)
        for coef, row in zip(frame.coordinates[i], frame.basis, strict=True):
            for d, b in enumerate(row):
                approx[d] += coef * b
        recon[h] = tuple(a + m for a, m in zip(approx, node.centroid, strict=True))
        if children is not None:
            child = children[h]
            centred = [x - m for x, m in zip(child.vector, node.centroid, strict=True)]
            num = math.sqrt(sum((x - y) ** 2 for x, y in zip(child.vector, recon[h], strict=True)))
            den = math.sqrt(sum(x * x for x in centred)) or 1.0
            errs.append(num / den)
    verified = children is not None
    return DownResult(
        act_handle=chash({"down": node.node_handle, "members": list(node.member_handles),
                          "verified": verified}),
        node_handle=node.node_handle,
        child_handles=node.member_handles,
        reconstructions=recon,
        verified=verified,
        round_trip_residual=(sum(errs) / len(errs)) if verified and errs else
                            (0.0 if verified else None),
    )
