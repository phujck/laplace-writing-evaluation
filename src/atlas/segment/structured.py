"""structured.py - JSON by key path, JSONL by row window, YAML by column-zero key scan.

The rule this file exists to enforce (design §5): a structured source never becomes a raw byte
head. The measured failure it answers is the ``_INDEX.json`` poisoning - the digest experiment
where taking the first N bytes of a structured file moved its carrier rank from 88 to 855,
because the head of a JSON file is punctuation and the first key, not what the file is about.
So a JSON object is cut at its MEMBERS, addressed by key path, and every object that becomes a
coarse node over its members also emits a KEY-INVENTORY span: a non-leaf span over the object's
range whose ``meta`` carries the member names. The coarse node's handle is therefore the
object's keys, never a slice of its bytes.

JSON is read by a byte scanner rather than ``json.loads`` because spans are byte ranges into the
immutable source and a parsed object has thrown those offsets away. The scanner tracks string
and escape state and container depth, jumping between structural characters instead of walking
every byte, so a 19 MB store costs a pass over its punctuation rather than over its floats.

YAML, stated plainly: pyyaml is NOT an atlas runtime dependency (numpy is the only one), so
there is no parser here. YAML gets a bounded line-based scan - document separators and keys at
COLUMN ZERO - which is honest structure-awareness without a parser and keeps YAML out of the
raw fallback. Nested structure below column zero is NOT addressed, and every YAML file that has
any is counted in a ``segmentation-miss/yaml-nested-structure`` event, so the size of what this
bound costs is a measured number rather than a footnote. A real parser is deferred until that
number says it is worth a dependency.
"""

from __future__ import annotations

import re

from .base import (
    Heading,
    RawSpan,
    SegmentResult,
    finalize,
    split_block,
    structural_spans,
    tokens_to_bytes,
)

LEAF_KIND = "json_member"
PARENT_OBJECT_KIND = "json_object"
PARENT_ARRAY_KIND = "json_array"

#: Below this depth of nesting the scanner stops descending and splits at line boundaries. A
#: bound, not a silent one: crossing it writes a miss event naming the node and the key path.
MAX_DEPTH = 12

#: Key inventories are capped so one 100k-key object does not put 100k strings in one row. The
#: full member count is always recorded; only the name list is truncated, and it says so.
MAX_INVENTORY_KEYS = 200

_STRUCT_RE = re.compile(rb'["{}\[\],]')
_WS = b" \t\r\n"


def _skip_ws(data: bytes, i: int, end: int) -> int:
    while i < end and data[i] in _WS:
        i += 1
    return i


def _skip_string(data: bytes, i: int, end: int) -> int:
    """``i`` is the opening quote. Returns the index just past the closing quote."""
    j = i + 1
    while True:
        k = data.find(b'"', j, end)
        if k == -1:
            return end
        back = k - 1
        slashes = 0
        while back > i and data[back] == 0x5C:
            slashes += 1
            back -= 1
        if slashes % 2 == 0:
            return k + 1
        j = k + 1


def _member_cuts(data: bytes, open_idx: int, end: int) -> tuple[list[int], list[str], str]:
    """Scan one container. Returns (member start offsets, keys, "object"|"array").

    The first cut is ``open_idx + 1``; each later cut is the byte after a comma at this
    container's own depth. Keys are collected only for objects and only at depth zero.
    """
    kind = "object" if data[open_idx:open_idx + 1] == b"{" else "array"
    is_obj = kind == "object"
    cuts = [open_idx + 1]
    keys: list[str] = []
    depth = 0
    expect_key = is_obj
    pos = open_idx + 1
    while pos < end:
        m = _STRUCT_RE.search(data, pos, end)
        if m is None:
            break
        at = m.start()
        ch = data[at]
        if ch == 0x22:                                   # a string: jump past it
            nxt = _skip_string(data, at, end)
            if is_obj and depth == 0 and expect_key:
                keys.append(data[at + 1:nxt - 1].decode("utf-8", errors="replace")[:200])
                expect_key = False
            pos = nxt
            continue
        if ch in (0x7B, 0x5B):                           # { [
            depth += 1
            pos = at + 1
            continue
        if ch in (0x7D, 0x5D):                           # } ]
            if depth == 0:
                return cuts, keys, kind
            depth -= 1
            pos = at + 1
            continue
        if ch == 0x2C and depth == 0:                    # a member boundary
            cuts.append(at + 1)
            expect_key = is_obj
            pos = at + 1
            continue
        pos = at + 1
    return cuts, keys, kind


def _value_start(data: bytes, ta: int, tb: int, is_first: bool, is_obj: bool,
                 open_idx: int) -> int | None:
    """Where a member's VALUE begins, so the scanner knows whether to descend into it."""
    p = open_idx + 1 if is_first else ta
    p = _skip_ws(data, p, tb)
    if is_obj:
        if p >= tb or data[p] != 0x22:
            return None
        p = _skip_ws(data, _skip_string(data, p, tb), tb)
        if p >= tb or data[p] != 0x3A:
            return None
        p = _skip_ws(data, p + 1, tb)
    return p if p < tb else None


def _inventory(kind: str, keys: list[str], member_count: int) -> dict:
    meta: dict = {"container": kind, "member_count": member_count}
    if kind == "object":
        meta["keys"] = keys[:MAX_INVENTORY_KEYS]
        meta["keys_truncated"] = len(keys) > MAX_INVENTORY_KEYS
    return meta


class JsonSegmenter:
    """JSON by key path, with a key-inventory span for every object that becomes coarse."""

    segmenter_id = "structured-json/1"
    version = "seg/1"
    extensions = (".json",)

    def can_handle(self, path: str) -> bool:
        return path.lower().endswith(self.extensions)

    def segment(self, node_id: str, path: str, source_content_hash: str, data: bytes,
                target_tokens: int, hard_cap_tokens: int) -> SegmentResult:
        if not data:
            return SegmentResult()
        misses: list[dict] = []
        head = _skip_ws(data, 0, len(data))
        if head < len(data) and data[head:head + 1] in (b"{", b"["):
            raws = self._container(data, 0, len(data), head, (), 0, target_tokens,
                                   hard_cap_tokens, node_id, path, misses)
        else:
            misses.append({
                "node_id": node_id, "path": path, "segmenter_id": self.segmenter_id,
                "reason": "segmentation-miss/json-not-a-container", "detail": {},
            })
            raws = self._line_leaves(data, 0, len(data), (), target_tokens, hard_cap_tokens)
        result = finalize(node_id, source_content_hash, self.segmenter_id, self.version,
                          raws, hard_cap_tokens,
                          oversize_reason="json-member-has-no-line-break-under-cap")
        result.misses.extend(misses)
        return result

    @staticmethod
    def _line_leaves(data: bytes, a: int, b: int, trail: tuple[str, ...],
                     target_tokens: int, hard_cap_tokens: int) -> list[RawSpan]:
        tiles = split_block(data, a, b, tokens_to_bytes(target_tokens),
                            tokens_to_bytes(hard_cap_tokens), (b"\n",))
        return [RawSpan(x, y, True, LEAF_KIND, list(trail)) for x, y in tiles]

    def _container(self, data: bytes, a: int, b: int, open_idx: int, trail: tuple[str, ...],
                   depth: int, target_tokens: int, hard_cap_tokens: int, node_id: str,
                   path: str, misses: list[dict]) -> list[RawSpan]:
        """Spans tiling ``[a, b)``, where the container's bracket sits at ``open_idx``."""
        target_bytes = tokens_to_bytes(target_tokens)
        if b - a <= target_bytes:
            return [RawSpan(a, b, True, LEAF_KIND, list(trail))]
        if depth > MAX_DEPTH:
            misses.append({
                "node_id": node_id, "path": path, "segmenter_id": self.segmenter_id,
                "reason": "segmentation-miss/json-depth-bound",
                "detail": {"depth": depth, "key_path": list(trail)},
            })
            return self._line_leaves(data, a, b, trail, target_tokens, hard_cap_tokens)

        cuts, keys, kind = _member_cuts(data, open_idx, b)
        is_obj = kind == "object"
        inner = [c for c in cuts[1:] if a < c < b]
        bounds = [a] + inner + [b]
        units = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
        if is_obj and len(keys) != len(units):
            misses.append({
                "node_id": node_id, "path": path, "segmenter_id": self.segmenter_id,
                "reason": "segmentation-miss/json-key-count-mismatch",
                "detail": {"keys": len(keys), "members": len(units), "key_path": list(trail)},
            })
            keys = []
        labels = [keys[i] if (is_obj and i < len(keys)) else f"[{i}]" for i in range(len(units))]

        children: list[RawSpan] = []
        i = 0
        while i < len(units):
            j = i
            size = units[i][1] - units[i][0]
            while j + 1 < len(units) and size + (units[j + 1][1] - units[j + 1][0]) <= target_bytes:
                j += 1
                size += units[j][1] - units[j][0]
            ta, tb = units[i][0], units[j][1]
            if i == j and tb - ta > target_bytes:
                sub_trail = trail + (labels[i],)
                vs = _value_start(data, ta, tb, i == 0, is_obj, open_idx)
                if vs is not None and data[vs:vs + 1] in (b"{", b"["):
                    sub = self._container(data, ta, tb, vs, sub_trail, depth + 1, target_tokens,
                                          hard_cap_tokens, node_id, path, misses)
                else:
                    sub = self._line_leaves(data, ta, tb, sub_trail, target_tokens,
                                            hard_cap_tokens)
                    if len(sub) == 1 and (tb - ta) > tokens_to_bytes(hard_cap_tokens):
                        sub[0].meta["oversize_reason"] = "json-scalar-member-exceeds-cap"
                children.extend(sub)
            else:
                lab = [labels[i]] if i == j else []
                children.append(RawSpan(ta, tb, True, LEAF_KIND, list(trail) + lab))
            i = j + 1

        if len([c for c in children if c.is_leaf]) < 2:
            return children
        # A single-member wrapper (``{"data": {...}}``) descends into a child whose range is this
        # one; emitting a second span over the same bytes would mint the same span id twice.
        if (a, b) in {(c.start, c.end) for c in children}:
            return children
        parent_kind = PARENT_OBJECT_KIND if is_obj else PARENT_ARRAY_KIND
        parent = RawSpan(a, b, False, parent_kind, list(trail),
                         _inventory(kind, keys, len(units)))
        for child in children:
            if child.parent_range is None:
                child.parent_range = (a, b)
        return [parent] + children


class JsonlSegmenter:
    """JSONL by physical row: every governance row remains individually reachable."""

    segmenter_id = "structured-jsonl/1"
    version = "seg/1"
    extensions = (".jsonl",)

    def can_handle(self, path: str) -> bool:
        return path.lower().endswith(self.extensions)

    def segment(self, node_id: str, path: str, source_content_hash: str, data: bytes,
                target_tokens: int, hard_cap_tokens: int) -> SegmentResult:
        if not data:
            return SegmentResult()
        cap_bytes = tokens_to_bytes(hard_cap_tokens)
        starts = [0]
        pos = data.find(b"\n")
        while pos != -1:
            if pos + 1 < len(data):
                starts.append(pos + 1)
            pos = data.find(b"\n", pos + 1)
        row_of = {off: idx for idx, off in enumerate(starts)}

        raws: list[RawSpan] = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(data)
            row = row_of[start]
            meta = {"row_start": row, "row_end": row}
            if end - start > cap_bytes:
                # One record larger than the cap. A row is the structural unit of a jsonl file,
                # so it is named oversize rather than cut across a record boundary.
                meta["oversize_reason"] = "jsonl-row-exceeds-cap"
            raws.append(RawSpan(start, end, True, "jsonl_row", [], meta))
        return finalize(node_id, source_content_hash, self.segmenter_id, self.version,
                        raws, hard_cap_tokens, oversize_reason="jsonl-row-exceeds-cap")


_YAML_DOC_RE = re.compile(rb"(?m)^---[ \t]*$")
_YAML_KEY_RE = re.compile(rb"(?m)^([A-Za-z_][\w.\-]*)[ \t]*:")
_YAML_NESTED_RE = re.compile(rb"(?m)^[ \t]+[A-Za-z_\"'\-][\w.\-]*[ \t]*:")


class YamlSegmenter:
    """YAML by document separator and column-zero key. No parser; the bound is stated and counted."""

    segmenter_id = "structured-yaml/1"
    version = "seg/1"
    extensions = (".yaml", ".yml")

    def can_handle(self, path: str) -> bool:
        return path.lower().endswith(self.extensions)

    def segment(self, node_id: str, path: str, source_content_hash: str, data: bytes,
                target_tokens: int, hard_cap_tokens: int) -> SegmentResult:
        if not data:
            return SegmentResult()
        headings = [Heading(m.start(), 1, "---") for m in _YAML_DOC_RE.finditer(data)]
        headings += [
            Heading(m.start(), 2, m.group(1).decode("utf-8", errors="replace")[:120])
            for m in _YAML_KEY_RE.finditer(data)
        ]
        headings.sort(key=lambda h: h.offset)
        raws = structural_spans(data, 0, len(data), headings, target_tokens, hard_cap_tokens,
                                "yaml_block", "yaml_section", (b"\n\n", b"\n"))
        result = finalize(node_id, source_content_hash, self.segmenter_id, self.version,
                          raws, hard_cap_tokens,
                          oversize_reason="yaml-block-has-no-line-break-under-cap")
        if _YAML_NESTED_RE.search(data):
            result.misses.append({
                "node_id": node_id, "path": path, "segmenter_id": self.segmenter_id,
                "reason": "segmentation-miss/yaml-nested-structure",
                "detail": {"bound": "column-zero keys and document separators only"},
            })
        return result
