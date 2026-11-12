"""frames.py - THE NODE FRAME, computed from the TRANSPORTED FIELD DECODER (ruling R-2).

``augmented_grade_execution.md``:78-84, "Bridge to geometric query frames", verbatim: "A hidden
source-state column is not an embedding-space basis vector. Within a node the transported
field-decoder rows determine the represented field directions. QR/SVD of those decoder rows can
supply an ordinary orthonormal embedding-space frame, with the decoder map retained explicitly.
The constant field row divided by sqrt(node mass) is its conditional mean." That is exactly what
this module computes, for every node of a graded tree, in one batched call per UP round:

    mu   [N, d]    the node's conditional mean field  = (constant decoder row) / sqrt(mass)
    V    [r_n, d]  orthonormal field directions       = SVD of the node's register decoder rows
    lam  [r_n]     the energy on each direction       = s^2 / mass
    eps  [N]       the tail energy the frame leaves   (the fourth typed quantity, kept apart)
    R    [N]       the coordinate radius              max over members of ||V^T (x - mu)||
    r    [N]       the residual radius                max over members of ||(I - VV^T)(x - mu)||

``(mu, V, lam, eps, R, r)`` is ``numerics/common.py:201-214``'s C5 object and
``numerics/gpu_cluster.py:93-123``'s ``frames_gpu`` tuple, and the semantics kept here are that
function's: BATCHED BY SIZE CLASS, never one node at a time. What is NOT lifted is its input: it
frames a list of item index arrays over a second tree, and ruling R-2 refuses a second tree -
"leaf_bounds and search_batched take a per-leaf frame TABLE, not a tree", so the table is built
against the GRADED tree's own nodes and from the decoder V that already travels with them.

R and r are what the certified bound needs and they are the one part the decoder rows cannot
supply by themselves, because they are extrema over MEMBERS and not moments. ``section
execution``'s own rule is followed: "If propagated from child frames, carry the omitted child
contribution and use a proved bound." Each child is a ball of centre mu_c and radius
rho_c = sqrt(R_c^2 + r_c^2) about its own members, so for any member x of child c

    ||V_p^T (x - mu_p)||        <= ||V_p^T (mu_c - mu_p)|| + rho_c
    ||(I - V_p V_p^T)(x - mu_p)|| <= ||(I - V_p V_p^T)(mu_c - mu_p)|| + rho_c

and R_p, r_p are the maxima of the right-hand sides over the node's children. At the first UP
round the children ARE the tagged rows, rho_c = 0, and both lines are EQUALITIES - so the leaf
frames are exact and the bound above them is a proved over-estimate whose tightness this packet
measures rather than assumes. C7's certificate ``<v, q> <= <mu, q> + R ||V^T q|| + r ||q||``
therefore holds at every node, which is what the DOWN read prunes with.

Complexity: O(sum over rounds of (children * d * r)) device work in resource blocks; one batched
SVD per width class per round (widths are bounded by the declared register rank cap, so there
are at most cap + 1 classes). Peak: one block of children by d. No node is a Python object and
no N x N object is formed anywhere.
"""

from __future__ import annotations

import json
import os
import struct
import zlib
from dataclasses import dataclass
from typing import Any

import torch

from .blocks import DENSE_SHARE_BYTES

__all__ = ["NodeFrames", "FrameAccumulator", "certified_upper", "frame_coordinates",
           "serialise_frames", "deserialise_frames", "persist_frames", "load_frames"]

_MAGIC = b"ATLASFRM"


@dataclass(slots=True)
class NodeFrames:
    """The per-NODE frame table: the object ``leaf_bounds``/``search_batched`` are functions of.

    Ragged by construction (a node's rank is the rank the acceptance tests bought it), so the
    directions live in one [total, d] table with a per-node pointer - never a padded [N, d, rmax]
    cube, which at 57k leaf cells and d = 384 is half a gigabyte of mostly zeros.
    """

    mu: torch.Tensor               # float64 [N, d]
    ptr: torch.Tensor              # int64 [N + 1] into ``dirs``/``lam``
    dirs: torch.Tensor             # float64 [total, d] orthonormal rows, per node
    lam: torch.Tensor              # float64 [total]
    eps: torch.Tensor              # float64 [N] energy the frame leaves unrepresented
    radius: torch.Tensor           # float64 [N] R
    residual_radius: torch.Tensor  # float64 [N] r
    mass: torch.Tensor             # float64 [N]
    grade: torch.Tensor            # int64 [N] the UP round that minted the frame, -1 if none
    exact: torch.Tensor            # bool [N] True where R and r are member extrema, not bounds
    dim: int

    def __len__(self) -> int:
        return int(self.mu.shape[0])

    def rank(self) -> torch.Tensor:
        return self.ptr[1:] - self.ptr[:-1]

    def receipt(self) -> dict[str, Any]:
        framed = self.grade >= 0
        return {
            "nodes": len(self), "nodes_with_a_frame": int(framed.sum()),
            "dim": self.dim, "directions_total": int(self.dirs.shape[0]),
            "rank_mean": float(self.rank()[framed].to(torch.float64).mean()) if bool(
                framed.any()) else 0.0,
            "rank_max": int(self.rank().max()) if len(self) else 0,
            "exact_frames": int(self.exact.sum()),
            "radius_mean": float(self.radius[framed].mean()) if bool(framed.any()) else 0.0,
            "residual_radius_mean": float(self.residual_radius[framed].mean()) if bool(
                framed.any()) else 0.0,
            "device_bytes": int(sum(t.numel() * t.element_size() for t in
                                    (self.mu, self.dirs, self.lam, self.eps, self.radius,
                                     self.residual_radius, self.mass))),
            "object": "(mu, V, lam, eps, R, r) per node - numerics/common.py:201-214's C5 tuple",
        }


def _blocked_rows(count: int, width: int) -> int:
    """How many rows of a [rows, width] float64 expansion the declared dense share admits."""
    return max(1, min(max(count, 1), DENSE_SHARE_BYTES // max(8 * max(width, 1), 1)))


def _frames_of_one_round(out_owner: torch.Tensor, out_mode: torch.Tensor,
                         out_v: torch.Tensor, mass: torch.Tensor, parents: int
                         ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor,
                                    torch.Tensor]:
    """(mu, ptr, dirs, lam, eps) for every parent of ONE round, batched by width class.

    The parents' decoder rows are ragged only in the register rank, which the declared cap
    bounds, so ONE padded [P_w, w, d] batch per distinct width w runs the whole round's SVDs.
    """
    device = out_v.device
    d = int(out_v.shape[1])
    mu = torch.zeros((parents, d), dtype=torch.float64, device=device)
    constant = out_mode == 0
    mu.index_copy_(0, out_owner[constant],
                   out_v[constant].to(torch.float64)
                   / torch.sqrt(mass[out_owner[constant]]).clamp(min=1e-300)[:, None])
    register = ~constant
    width = torch.zeros(parents, dtype=torch.int64, device=device)
    if bool(register.any()):
        width.index_add_(0, out_owner[register],
                         torch.ones(int(register.sum()), dtype=torch.int64, device=device))
    ptr = torch.zeros(parents + 1, dtype=torch.int64, device=device)
    torch.cumsum(width, 0, out=ptr[1:])
    total = int(ptr[-1])
    dirs = torch.zeros((total, d), dtype=torch.float64, device=device)
    lam = torch.zeros(total, dtype=torch.float64, device=device)
    eps = torch.zeros(parents, dtype=torch.float64, device=device)
    if total == 0:
        return mu, ptr, dirs, lam, eps

    owner = out_owner[register]
    mode = out_mode[register]
    rows = out_v[register]
    widths = torch.unique(width[width > 0])
    for one in widths.tolist():  # loop-ok: the distinct REGISTER WIDTHS of the round - at most the declared rank cap + 1 classes, never a step per node
        group = torch.nonzero(width == one, as_tuple=False).flatten()
        if not group.numel():
            continue
        slot = torch.full((parents,), -1, dtype=torch.int64, device=device)
        slot[group] = torch.arange(int(group.numel()), dtype=torch.int64, device=device)
        take = slot[owner] >= 0
        batch = torch.zeros((int(group.numel()), one, d), dtype=torch.float64, device=device)
        batch[slot[owner[take]], mode[take] - 1] = rows[take].to(torch.float64)
        # the node's own mass whitens the decoder rows into field COORDINATES; the SVD of those
        # is the orthonormal embedding-space frame the bridge paragraph asks for
        scaled = batch / torch.sqrt(mass[group]).clamp(min=1e-300)[:, None, None]
        _, singular, right = torch.linalg.svd(scaled, full_matrices=False)
        keep = min(one, d)
        target = (ptr[group][:, None]
                  + torch.arange(keep, dtype=torch.int64, device=device)[None, :]).flatten()
        # keep == one: the register's decoder rows are at most the declared rank cap and the
        # field dimension is 384, so the SVD retains every row and ``eps`` - the energy a
        # TRUNCATED frame would leave - is exactly zero here. The energy the BUILD dropped is a
        # different typed quantity and stays where it is measured (RoundMeasurement's
        # demand_singular_tail); the four residuals are never fused under one word.
        dirs.index_copy_(0, target, right[:, :keep, :].reshape(-1, d))
        lam.index_copy_(0, target, singular[:, :keep].square().flatten())
        del batch, scaled, singular, right
    return mu, ptr, dirs, lam, eps


def _extents(child_mu: torch.Tensor, child_rho: torch.Tensor, parent_of_child: torch.Tensor,
             mu: torch.Tensor, ptr: torch.Tensor, dirs: torch.Tensor, parents: int
             ) -> tuple[torch.Tensor, torch.Tensor]:
    """R and r per parent from its children's balls. Exact when every rho is zero.

    Blocked over CHILDREN, and inside a block over the parent's direction slots (bounded by the
    declared rank cap). No [children, d, rank] cube is ever formed.
    """
    device = mu.device
    d = int(mu.shape[1])
    radius = torch.zeros(parents, dtype=torch.float64, device=device)
    residual = torch.zeros(parents, dtype=torch.float64, device=device)
    children = int(child_mu.shape[0])
    if not children:
        return radius, residual
    rank = (ptr[1:] - ptr[:-1])
    widest = int(rank.max()) if parents else 0
    block = _blocked_rows(children, 2 * d)
    for start in range(0, children, block):  # loop-ok: RESOURCE blocks of the round's children, bounded by the declared dense share
        stop = min(children, start + block)
        owner = parent_of_child[start:stop]
        delta = child_mu[start:stop].to(torch.float64) - mu.index_select(0, owner)
        square = delta.square().sum(1)
        along = torch.zeros(int(stop - start), dtype=torch.float64, device=device)
        for slot in range(widest):  # loop-ok: the direction SLOTS of the declared register - bounded by the rank cap, a closed declared set
            live = rank[owner] > slot
            if not bool(live.any()):
                continue
            row = dirs.index_select(0, (ptr[owner] + slot).clamp(max=max(int(dirs.shape[0]) - 1,
                                                                        0)))
            coordinate = torch.where(live, (delta * row).sum(1),
                                     torch.zeros_like(square))
            along = along + coordinate.square()
            del row, coordinate
        rho = child_rho[start:stop]
        radius.scatter_reduce_(0, owner, torch.sqrt(along.clamp(min=0.0)) + rho,
                               reduce="amax", include_self=True)
        residual.scatter_reduce_(0, owner,
                                 torch.sqrt((square - along).clamp(min=0.0)) + rho,
                                 reduce="amax", include_self=True)
        del delta, square, along
    return radius, residual


class FrameAccumulator:
    """The frame table, built ONE UP ROUND AT A TIME and never holding two rounds of V.

    MEASURED, and the reason this is a consumer and not a list: banking each round's
    transported decoder for a later pass keeps every grade's V alive at once. At 115k
    LongMemEval turns, d = 384 and a register of rank up to chi, the round-1 decoder alone is
    parents * (rank + 1) * 384 * 8 bytes, and the run died in ``_transport`` on a 3.68 GiB card
    with 3.46 GiB in use. Consuming the round leaves only the per-NODE results - mu, the
    directions, R, r - which are linear in the nodes and not in the coordinates.
    """

    __slots__ = ("nodes", "dim", "device", "mu", "width", "eps", "radius", "residual",
                 "mass", "grade", "exact", "parts", "child_mu", "child_rho", "rounds")

    def __init__(self, nodes: int, field: torch.Tensor) -> None:
        device = field.device
        self.nodes = nodes
        self.dim = int(field.shape[1])
        self.device = device
        self.mu = torch.zeros((nodes, self.dim), dtype=torch.float64, device=device)
        self.width = torch.zeros(nodes, dtype=torch.int64, device=device)
        self.eps = torch.zeros(nodes, dtype=torch.float64, device=device)
        self.radius = torch.zeros(nodes, dtype=torch.float64, device=device)
        self.residual = torch.zeros(nodes, dtype=torch.float64, device=device)
        self.mass = torch.zeros(nodes, dtype=torch.float64, device=device)
        self.grade = torch.full((nodes,), -1, dtype=torch.int64, device=device)
        self.exact = torch.zeros(nodes, dtype=torch.bool, device=device)
        self.parts: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]] = []
        self.child_mu = field.to(torch.float64)
        self.child_rho = torch.zeros(int(field.shape[0]), dtype=torch.float64, device=device)
        self.rounds = 0

    def consume(self, parent_node: torch.Tensor, parent_mass: torch.Tensor,
                parent_of_object: torch.Tensor, out_owner: torch.Tensor,
                out_mode: torch.Tensor, out_v: torch.Tensor) -> None:
        """One UP round's frames, from its transported decoder rows. O(parents * d * rank)."""
        parents = int(parent_node.numel())
        mass = parent_mass.to(torch.float64)
        mu_p, ptr_p, dirs_p, lam_p, eps_p = _frames_of_one_round(
            out_owner, out_mode, out_v, mass, parents)
        radius_p, residual_p = _extents(self.child_mu, self.child_rho, parent_of_object,
                                        mu_p, ptr_p, dirs_p, parents)
        self.mu.index_copy_(0, parent_node, mu_p)
        self.width.index_copy_(0, parent_node, ptr_p[1:] - ptr_p[:-1])
        self.eps.index_copy_(0, parent_node, eps_p)
        self.radius.index_copy_(0, parent_node, radius_p)
        self.residual.index_copy_(0, parent_node, residual_p)
        self.mass.index_copy_(0, parent_node, mass)
        self.grade.index_copy_(0, parent_node, torch.full_like(parent_node, self.rounds))
        self.exact.index_copy_(0, parent_node,
                               torch.full_like(parent_node, self.rounds == 0,
                                               dtype=torch.bool))
        self.parts.append((parent_node, ptr_p, dirs_p, lam_p))
        self.child_mu = mu_p
        self.child_rho = torch.sqrt(radius_p.square() + residual_p.square())
        self.rounds += 1

    def finish(self) -> NodeFrames:
        """The ragged direction table, assembled once from the rounds' own pieces."""
        ptr = torch.zeros(self.nodes + 1, dtype=torch.int64, device=self.device)
        torch.cumsum(self.width, 0, out=ptr[1:])
        total = int(ptr[-1])
        dirs = torch.zeros((total, self.dim), dtype=torch.float64, device=self.device)
        lam = torch.zeros(total, dtype=torch.float64, device=self.device)
        for parent_node, ptr_p, dirs_p, lam_p in self.parts:  # loop-ok: one step per UP ROUND
            widths = ptr_p[1:] - ptr_p[:-1]
            if not int(widths.sum()):
                continue
            owner = torch.repeat_interleave(
                torch.arange(int(parent_node.numel()), dtype=torch.int64, device=self.device),
                widths)
            slot = (torch.arange(int(widths.sum()), dtype=torch.int64, device=self.device)
                    - torch.repeat_interleave(ptr_p[:-1], widths))
            dirs.index_copy_(0, ptr[parent_node[owner]] + slot, dirs_p)
            lam.index_copy_(0, ptr[parent_node[owner]] + slot, lam_p)
        self.parts.clear()
        return NodeFrames(mu=self.mu, ptr=ptr, dirs=dirs, lam=lam, eps=self.eps,
                          radius=self.radius, residual_radius=self.residual, mass=self.mass,
                          grade=self.grade, exact=self.exact, dim=self.dim)


def frame_coordinates(frames: NodeFrames, node: torch.Tensor, vectors: torch.Tensor
                      ) -> tuple[torch.Tensor, torch.Tensor]:
    """The coordinates of ``vectors`` in THEIR OWN node's frame, and the residual norm.

    This is the re-score the winnowing read does INSIDE a node: the node's conditional mean is
    removed - the shared direction, which is what every member of an accepted node has in common
    and therefore what no member is distinguished by - and what is left is read in the node's own
    register. Returns (coordinates [n, rmax] zero-padded, residual norm [n]).

    Complexity: O(n d rmax) device, in resource blocks. No per-item Python.
    """
    device = frames.mu.device
    rank = frames.rank()
    widest = max(int(rank[node].max()), 1) if node.numel() else 1
    n = int(node.numel())
    coordinates = torch.zeros((n, widest), dtype=torch.float64, device=device)
    residual = torch.zeros(n, dtype=torch.float64, device=device)
    if not n:
        return coordinates, residual
    d = frames.dim
    block = _blocked_rows(n, 2 * d)
    for start in range(0, n, block):  # loop-ok: RESOURCE blocks of the scored rows
        stop = min(n, start + block)
        owner = node[start:stop]
        delta = vectors[start:stop].to(torch.float64) - frames.mu.index_select(0, owner)
        square = delta.square().sum(1)
        along = torch.zeros(int(stop - start), dtype=torch.float64, device=device)
        for slot in range(widest):  # loop-ok: the declared register's direction slots
            live = rank[owner] > slot
            if not bool(live.any()):
                continue
            row = frames.dirs.index_select(
                0, (frames.ptr[owner] + slot).clamp(max=max(int(frames.dirs.shape[0]) - 1, 0)))
            value = torch.where(live, (delta * row).sum(1), torch.zeros_like(square))
            coordinates[start:stop, slot] = value
            along = along + value.square()
            del row, value
        residual[start:stop] = torch.sqrt((square - along).clamp(min=0.0))
        del delta, square, along
    return coordinates, residual


def certified_upper(frames: NodeFrames, node: torch.Tensor, query: torch.Tensor) -> torch.Tensor:
    """C7, verbatim: <v, q> <= <mu, q> + R ||V^T q|| + r ||q|| for every member v of the node.

    ``numerics/common.py:222-224``'s form, evaluated against the GRADED tree's own node table.
    One batched pass over the named nodes; no leaf is opened to compute it.
    """
    device = frames.mu.device
    q = query.to(torch.float64)
    rank = frames.rank()
    widest = max(int(rank[node].max()), 1) if node.numel() else 1
    mean_term = frames.mu.index_select(0, node) @ q
    along = torch.zeros(int(node.numel()), dtype=torch.float64, device=device)
    for slot in range(widest):  # loop-ok: the declared register's direction slots
        live = rank[node] > slot
        if not bool(live.any()):
            continue
        row = frames.dirs.index_select(
            0, (frames.ptr[node] + slot).clamp(max=max(int(frames.dirs.shape[0]) - 1, 0)))
        value = torch.where(live, row @ q, torch.zeros_like(along))
        along = along + value.square()
    return (mean_term + frames.radius.index_select(0, node) * torch.sqrt(along.clamp(min=0.0))
            + frames.residual_radius.index_select(0, node) * float(q.norm()))


# ------------------------------------------------------------------ persistence (the store's form)
def serialise_frames(frames: NodeFrames) -> bytes:
    """One blob: magic, an 8-byte header length, a JSON header, then the arrays in name order.

    The same deterministic packing ``tree.serialise_component`` uses, so the frame table is a
    content address in the same hive and a changed component re-mints exactly its own bytes.
    """
    arrays = {"mu": frames.mu, "ptr": frames.ptr, "dirs": frames.dirs, "lam": frames.lam,
              "eps": frames.eps, "radius": frames.radius,
              "residual_radius": frames.residual_radius, "mass": frames.mass,
              "grade": frames.grade, "exact": frames.exact}
    header = {"record": "atlas.grading.node-frames/1", "dim": frames.dim,
              "nodes": len(frames),
              "arrays": {name: {"dtype": str(tensor.dtype).replace("torch.", ""),
                                "shape": list(tensor.shape)}
                         for name, tensor in arrays.items()}}  # loop-ok: the table's fixed columns
    body = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    parts = [_MAGIC, struct.pack("<Q", len(body)), body]
    for name in sorted(arrays):  # loop-ok: the table's own fixed column list
        parts.append(arrays[name].detach().cpu().numpy().tobytes(order="C"))
    return b"".join(parts)


def deserialise_frames(blob: bytes, device: torch.device) -> NodeFrames:
    """Read a frame table back. No frame is recomputed: the bytes ARE the table."""
    import numpy as np

    if blob[:len(_MAGIC)] != _MAGIC:
        raise ValueError("PERSISTED-FRAMES-BAD-MAGIC")
    size = struct.unpack("<Q", blob[len(_MAGIC):len(_MAGIC) + 8])[0]
    start = len(_MAGIC) + 8
    header = json.loads(blob[start:start + size].decode("utf-8"))
    offset = start + size
    out: dict[str, torch.Tensor] = {}
    for name in sorted(header["arrays"]):  # loop-ok: the table's own fixed column list
        spec = header["arrays"][name]
        dtype = np.dtype(spec["dtype"])
        count = 1
        for extent in spec["shape"]:  # loop-ok: at most two dimensions
            count *= int(extent)
        raw = np.frombuffer(blob, dtype=dtype, count=count, offset=offset)
        offset += count * dtype.itemsize
        out[name] = torch.from_numpy(raw.reshape(spec["shape"]).copy()).to(device)
    return NodeFrames(mu=out["mu"], ptr=out["ptr"], dirs=out["dirs"], lam=out["lam"],
                      eps=out["eps"], radius=out["radius"],
                      residual_radius=out["residual_radius"], mass=out["mass"],
                      grade=out["grade"], exact=out["exact"], dim=int(header["dim"]))


def persist_frames(frames: NodeFrames, hive) -> dict[str, Any]:
    """Store the frame table in the verified compressed hive; return its manifest entry."""
    from ..store import hash_bytes

    blob = serialise_frames(frames)
    key = hash_bytes(blob)
    path = hive.key_path(key)
    already = path.is_file()
    if already:
        hive.get(key)                                             # verify, never bless
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + f".{os.getpid()}.part")
        with open(temporary, "wb") as handle:
            handle.write(zlib.compress(blob, level=9))
        os.replace(temporary, path)
    return {"record": "atlas.grading.node-frames.manifest/1", "key": key,
            "bytes": len(blob), "nodes": len(frames), "dim": frames.dim,
            "already_present": already}


def load_frames(hive, key: str, device: torch.device) -> NodeFrames:
    """Read a persisted frame table back out of the hive by its own content address."""
    return deserialise_frames(hive.get(key), device)
