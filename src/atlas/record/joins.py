"""joins.py - the two vectorised joins rung (a) needs, and neither of them is a similarity.

B.7 admits two families of rung-(a) relation: those the container's grammar states outright
(containment, order, declared links) and those whose "EXTRACTOR is a declared pure function of
declared fields with no learned parameter and no statistical component". Building the second
family is a JOIN, and a join written as a Python double loop is the per-row loop the charter
rejects. These two functions are that join, done on device.

``anchor_expand``     from a row's argument surface to every row the anchor index resolves that
                      surface to. This is the toy's walk rule ("emit an edge to every row that
                      names one of r's arguments") and it is a CSR gather, not a scan.
``typed_field_pairs`` all ordered pairs of rows sharing a declared key column, expanded exactly
                      (no cap, no sampling) with repeat_interleave and arange, then filtered by
                      declared field equalities and a declared order. This is how ``corrects``
                      is derived from claim_id, polarity and ordinal with nothing learned.

Both refuse the shape B.17 forbids: neither ever forms a same-kind projection of an incidence.
``anchor_expand`` returns row->row edges through a NAMED surface, and the surface is a column of
the source row, not a third node whose bipartite incidence is being squared.

Complexity: ``anchor_expand`` O(k + total df) for k sources; ``typed_field_pairs``
O(N log N + P) where P is the exact number of same-key ordered pairs, which is reported.
"""

from __future__ import annotations

import torch

from .anchor_index import AnchorIndex

__all__ = ["anchor_expand", "typed_field_pairs", "gather_ranges"]


def gather_ranges(starts: torch.Tensor, lengths: torch.Tensor) -> tuple[torch.Tensor,
                                                                        torch.Tensor]:
    """Flatten k variable-length ranges into (flat index, owner) without a Python loop.

    The one primitive both joins stand on: given ``starts[i]`` and ``lengths[i]``, produce the
    concatenation of ``range(starts[i], starts[i]+lengths[i])`` and, alongside it, which i each
    element came from. Complexity: O(sum(lengths)).
    """
    total = int(lengths.sum())
    device = starts.device
    if total == 0:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty
    offsets = torch.zeros(lengths.numel() + 1, dtype=torch.int64, device=device)
    torch.cumsum(lengths, dim=0, out=offsets[1:])
    slot = torch.arange(total, dtype=torch.int64, device=device)
    owner = torch.searchsorted(offsets[1:], slot, right=True)
    flat = starts.index_select(0, owner) + (slot - offsets.index_select(0, owner))
    return flat, owner


def anchor_expand(index: AnchorIndex, source_rows: torch.Tensor,
                  surface_ordinals: torch.Tensor, *, drop_self_loops: bool = True
                  ) -> tuple[torch.Tensor, torch.Tensor]:
    """Edges from each source row to every row its named surface resolves to.

    ``surface_ordinals[i]`` is the anchor-vocabulary ordinal of the surface ``source_rows[i]``
    names. Returns (src, dst) int64 tensors in source-major, ascending-target order - the order
    the postings already have, so the layout is free.
    """
    device = index.device
    if source_rows.numel() == 0:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty
    starts = index.indptr.index_select(0, surface_ordinals).to(torch.int64)
    stops = index.indptr.index_select(0, surface_ordinals + 1).to(torch.int64)
    flat, owner = gather_ranges(starts, stops - starts)
    if flat.numel() == 0:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty
    src = source_rows.index_select(0, owner)
    dst = index.indices.index_select(0, flat).to(torch.int64)
    if drop_self_loops:
        keep = src != dst
        src, dst = src[keep], dst[keep]
    return src, dst


def typed_field_pairs(key: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Every ORDERED pair (i, j), i != j, of row indices sharing the same key value.

    Exact, never sampled: the number of pairs is ``sum_g g*(g-1)`` over the key's groups and all
    of them are produced. A key whose groups are large will produce many pairs - that is a
    property of the DECLARED key, and it is reported (``pairs``) rather than silently capped,
    because a cap here would be a hidden literal deciding which relations exist.
    """
    device = key.device
    n = key.numel()
    if n == 0:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty
    order = torch.argsort(key, stable=True)
    sorted_key = key.index_select(0, order)
    group_id = torch.zeros(n, dtype=torch.int64, device=device)
    if n > 1:
        group_id[1:] = (sorted_key[1:] != sorted_key[:-1]).to(torch.int64)
    group_id = torch.cumsum(group_id, dim=0)
    groups = int(group_id[-1]) + 1
    size = torch.bincount(group_id, minlength=groups)
    start = torch.zeros(groups + 1, dtype=torch.int64, device=device)
    torch.cumsum(size, dim=0, out=start[1:])
    pair_counts = size * (size - 1)
    if int(pair_counts.sum()) == 0:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty
    # Enumerate the g*(g-1) ordered pairs of each group as a flat index p, then split it into
    # (row within group, column within group) with a divmod - no loop over groups.
    flat, owner = gather_ranges(torch.zeros_like(pair_counts), pair_counts)
    width = (size - 1).index_select(0, owner)
    left = torch.div(flat, width, rounding_mode="floor")
    right = flat - left * width
    right = right + (right >= left).to(torch.int64)          # skip the diagonal
    base = start.index_select(0, owner)
    return order.index_select(0, base + left), order.index_select(0, base + right)
