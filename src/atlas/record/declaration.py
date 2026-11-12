"""declaration.py - the frozen dataset declaration (B.5) and provider obligations 5 and 6.

Everything the store is allowed to hold is named here before a byte is read: the closed column
list of each row kind, the type and PRODUCING RUNG of every field, the relation kinds with their
witness predicates, the field alias table and the surface set schema. The declaration then
freezes and carries its own content hash.

Why frozen matters, in the pack's words: an unfrozen column list "is a place to add a column
until a question compiles", and an unversioned alias table "is a mapping that can be edited
until a question compiles - the tuning door under a different name". So:

* every declaration object is a frozen dataclass; ``freeze()`` computes the hash and any later
  mutation raises ``DeclarationFrozen``;
* the hash covers the columns, types, rungs, vocabularies, relation kinds, alias rows and
  surface set - and nothing else. No clock, no generation id, no encoder (B.6).

The surface set schema (obligation 6) answers the question E.0 is blocked on: which surface
forms resolve to which node, per carrier kind, and who the declared principals of a transcript
are. It is the reason ``self`` reads as "I/we" in a user turn and as "you" in an assistant turn,
mechanically, instead of a guess that silently changes the node set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..ids import chash
from .columns import COLUMN_TYPES
from .errors import (ClosedColumnViolation, DeclarationFrozen, DeclarationRefused,
                     UnknownSurface)

__all__ = ["FieldSpec", "RowKindSpec", "RelationKindSpec", "AliasRow", "FieldAliasTable",
           "SurfaceSetSchema", "DatasetDeclaration", "RUNG_A", "RUNG_B", "RUNG_C",
           "SegmentationRecipe", "ContentAxisSpec", "ContentCarrier",
           "SEGMENTATION_RECIPE_GENERATION", "HARD_CAP_CEILING_TOKENS", "STORED_DTYPES"]

RUNG_A, RUNG_B, RUNG_C = 0, 1, 2          # B.11's producing_rung codes, in full.

#: The generation of the recipe this module knows how to read. A store written under another
#: generation refuses by name rather than being read under this one's rules - the same shape as
#: ``src/atlas/dataset.py:168-169``'s SEGMENTATION-GENERATION-UNKNOWN.
SEGMENTATION_RECIPE_GENERATION = "record-seg/1"

#: The largest hard cap any recipe may declare. NOT a taste and not a tuned size: it is the
#: token window of the encoders this campaign has on disk (512 for bge-small-en-v1.5,
#: multilingual-e5-small and qwen3-embedding-0.6b alike - ``synthetics papers/corpus-as-a-state/
#: numerics/common.py:26-29``), and a span past it is silently TRUNCATED by the encoder, which is
#: exactly the loss D.6's window-honesty clause exists to make loud. The old store path declares
#: the same ceiling for the same reason (``src/atlas/segment/__init__.py:30-33``,
#: ``src/atlas/dataset.py:170-171``). It is cross-checked against the AXIS's own encoder
#: window at build time (``record/content.py``), so a recipe that fits this ceiling but not the
#: declared encoder still refuses.
HARD_CAP_CEILING_TOKENS = 512

#: The stored forms D.7's quantisation ladder admits, with D.9's ``overhead(dtype)`` in bytes
#: per row per channel (row-scale bytes + eps bytes). ``int8`` is D.7's DEFAULT store.
STORED_DTYPES: Mapping[str, int] = {"f32": 0, "f16": 4, "int8": 8}


@dataclass(frozen=True, slots=True)
class SegmentationRecipe:
    """THE DECLARED LEAF SIZE (B.5), refusing an invalid dial by name.

    The record path carried only ``segmenter_id``/``seg_version`` - two strings that name WHICH
    segmenter and say nothing about how big a leaf is - while the old store path has declared the
    whole recipe, and refused it, since the pour door was written: a generation, a target and a
    hard cap with ``target <= hard_cap <= 512``, refused as SEGMENTATION-DIAL-INVALID
    (``src/atlas/dataset.py:167-171``). This is that recipe, on the record path, with the
    same three names, so the leaf size is a DECLARED ROW WITH PROVENANCE and never a literal
    inside an ingester.

    Complexity: O(1). It is part of the declaration's hashed field set only when it is declared.
    """

    generation: str
    target_tokens: int
    hard_cap_tokens: int
    segmenter_version: str
    declared_by: str = ""

    def __post_init__(self) -> None:
        if self.generation != SEGMENTATION_RECIPE_GENERATION:
            raise DeclarationRefused(
                "the segmentation recipe declares a generation this reader does not know",
                code="SEGMENTATION-GENERATION-UNKNOWN", declared=self.generation,
                known=SEGMENTATION_RECIPE_GENERATION)
        dials = (self.target_tokens, self.hard_cap_tokens)
        if not all(type(value) is int and value > 0 for value in dials) \
                or not self.target_tokens <= self.hard_cap_tokens <= HARD_CAP_CEILING_TOKENS:
            raise DeclarationRefused(
                "a segmentation dial is outside the declared recipe",
                code="SEGMENTATION-DIAL-INVALID", target_tokens=self.target_tokens,
                hard_cap_tokens=self.hard_cap_tokens, ceiling=HARD_CAP_CEILING_TOKENS)
        if not str(self.segmenter_version).strip():
            raise DeclarationRefused("the segmentation recipe declares no segmenter version",
                                     code="SEGMENTATION-VERSION-MISSING")

    def hashed(self) -> dict[str, Any]:
        return {"generation": self.generation, "target_tokens": self.target_tokens,
                "hard_cap_tokens": self.hard_cap_tokens,
                "segmenter_version": self.segmenter_version}


@dataclass(frozen=True, slots=True)
class ContentCarrier:
    """One content-bearing row kind of a dataset, and the declared column that holds its text.

    ``span_field`` is a declared ``span_ref`` column (LongMemEval's ``turn.content_span``,
    QASPER's ``paragraph.text_span``); ``""`` means the kind's own WITNESS span is the text.
    ``decoder`` names how those bytes become characters, so the mapping from a segment's
    character offsets back onto the blob is declared rather than sniffed: ``json_string`` for a
    JSON string node (quotes and escapes and all), ``utf8`` for raw bytes.
    """

    kind: str
    span_field: str = ""
    decoder: str = "utf8"


@dataclass(frozen=True, slots=True)
class ContentAxisSpec:
    """ONE DECLARED CONTENT AXIS: a vector channel over the leaves, named before a byte is read.

    D.5: "the store holds A vectors per span, where A is the number of declared vector CHANNELS,
    and A is fixed by fibre declarations, not by the encoder". D.1(i) admits the encoder as an
    OBSERVABLE of an authored channel and nothing else, so the axis names its encoder, its stored
    rank and its stored dtype, and the whole thing is a declared row the receipt can quote.

    S5 claim C11 is why this is a DECLARATION and not a setting: an axis that was not declared
    before the encoder ran cannot be recovered from the encoding afterwards, so the cost of the
    pass is paid per declared axis at ingestion (S4.tex:31) or the axis is lost permanently.

    ``tokens`` is the exact-lexical channel beside the vector one, on or off - the 'no tokens'
    ablation row of the reconciliation. It is not part of the encoder.
    """

    axis: str
    encoder_id: str
    dim: int
    dtype: str
    carriers: tuple[ContentCarrier, ...]
    tokens: bool = True
    recipe_version: str = "d6-span-bytes/1"
    why: str = ""

    def __post_init__(self) -> None:
        if not str(self.axis).strip() or not str(self.encoder_id).strip():
            raise DeclarationRefused("a content axis declares no name or no encoder",
                                     code="CONTENT-AXIS-INVALID", axis=self.axis,
                                     encoder_id=self.encoder_id)
        if isinstance(self.dim, bool) or type(self.dim) is not int or self.dim < 1:
            raise DeclarationRefused("a content axis declares a non-positive stored rank",
                                     code="CONTENT-AXIS-INVALID", axis=self.axis, dim=self.dim)
        if self.dtype not in STORED_DTYPES:
            raise DeclarationRefused(
                "a content axis declares a stored form outside D.7's quantisation ladder",
                code="CONTENT-AXIS-DTYPE-INVALID", axis=self.axis, dtype=self.dtype,
                ladder=sorted(STORED_DTYPES))
        if not self.carriers:
            raise DeclarationRefused("a content axis declares no content-bearing row kind",
                                     code="CONTENT-AXIS-WITHOUT-A-CARRIER", axis=self.axis)

    def bytes_per_span(self) -> int:
        """D.9's published storage function at this axis's declared (arity 1, rank, dtype).

        ``bytes_per_span = A * (r * bits(dtype)/8 + overhead(dtype) + 4*|R|)`` with A = 1 (one
        channel per axis, D.5) and |R| = 0 (no declared rank ladder is stored for a fixed-rank
        instrument; an MRL axis that declares one adds 4 bytes a rung here). Complexity: O(1).
        """
        width = {"f32": 4.0, "f16": 2.0, "int8": 1.0}[self.dtype]
        return int(self.dim * width) + STORED_DTYPES[self.dtype]

    def hashed(self) -> dict[str, Any]:
        return {"axis": self.axis, "encoder_id": self.encoder_id, "dim": self.dim,
                "dtype": self.dtype, "tokens": self.tokens,
                "recipe_version": self.recipe_version,
                "carriers": [{"kind": c.kind, "span_field": c.span_field,
                              "decoder": c.decoder} for c in self.carriers]}


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One declared column: its type, its vocabulary if coded, and the rung that produces it.

    B.5 puts the rung on the FIELD, not the kind, "because a row kind routinely has rung-(a)
    structural fields and rung-(b) extracted fields in the same row".
    """

    name: str
    type: str
    rung: int
    vocabulary: tuple[str, ...] | None = None
    doc: str = ""

    def hashed(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "rung": self.rung,
                "vocabulary": list(self.vocabulary) if self.vocabulary is not None else None}


@dataclass(frozen=True, slots=True)
class RowKindSpec:
    """One row kind and its CLOSED column list. ``time_field`` names the kind's typed time."""

    kind: str
    fields: tuple[FieldSpec, ...]
    time_field: str | None = None
    witness_predicate_id: str = ""
    anchor_fields: tuple[str, ...] = ()      # columns whose values are anchor surfaces
    doc: str = ""

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    def field(self, name: str) -> FieldSpec:
        for spec in self.fields:
            if spec.name == name:
                return spec
        raise ClosedColumnViolation("field outside the closed column list", kind=self.kind,
                                    field=name, columns=list(self.columns))

    def hashed(self) -> dict[str, Any]:
        return {"kind": self.kind, "fields": [f.hashed() for f in self.fields],
                "time_field": self.time_field,
                "witness_predicate_id": self.witness_predicate_id,
                "anchor_fields": list(self.anchor_fields)}


@dataclass(frozen=True, slots=True)
class RelationKindSpec:
    """One relation kind (B.5): its endpoints, its witness predicate, its rung, its symmetry.

    ``target_kinds`` is a tuple because B.3 admits a declared UNION of target kinds; a single
    target is a union of one, so there is no second code path for the common case.
    """

    kind: str
    source_kinds: tuple[str, ...]
    target_kinds: tuple[str, ...]
    witness_predicate_id: str
    rung: int
    symmetric: bool = False
    counted: bool = True
    doc: str = ""

    def hashed(self) -> dict[str, Any]:
        return {"kind": self.kind, "source_kinds": list(self.source_kinds),
                "target_kinds": list(self.target_kinds),
                "witness_predicate_id": self.witness_predicate_id, "rung": self.rung,
                "symmetric": self.symmetric, "counted": self.counted}


@dataclass(frozen=True, slots=True)
class AliasRow:
    """One row of the field alias table: a surface form and the typed target it resolves to."""

    surface: str
    target_kind: str        # 'row_field' | 'row_kind' | 'relation_kind'
    target_name: str        # e.g. 'subject=self', 'session', 'corrects'
    author: str
    declared_on: str
    scope: str = "*"        # a carrier kind, or '*' for every kind
    condition: str = ""     # a declared condition on the witnessing row, e.g. 'speaker=user'

    def hashed(self) -> dict[str, Any]:
        return {"surface": self.surface, "target_kind": self.target_kind,
                "target_name": self.target_name, "author": self.author,
                "declared_on": self.declared_on, "scope": self.scope,
                "condition": self.condition}


@dataclass(frozen=True, slots=True)
class FieldAliasTable:
    """Provider obligation 5: the versioned, hashed alias table C.2 and C.3 resolve through."""

    version: str
    rows: tuple[AliasRow, ...]

    def hashed(self) -> dict[str, Any]:
        return {"version": self.version, "rows": [r.hashed() for r in self.rows]}

    @property
    def sha256(self) -> str:
        return chash(self.hashed())

    def resolve(self, surface: str, *, scope: str = "*") -> tuple[AliasRow, ...]:
        """Every alias row matching this surface in this scope. Complexity: O(rows)."""
        return tuple(r for r in self.rows
                     if r.surface == surface and r.scope in ("*", scope))


@dataclass(frozen=True, slots=True)
class SurfaceSetSchema:
    """Provider obligation 6: which surfaces resolve to which node, per carrier kind.

    ``principal_surfaces`` is the piece E.0 refuses without: per carrier kind, a condition on the
    witnessing row (``'speaker=user'``) mapped to the surface forms that denote the declared
    principal in a row satisfying it. The engine does not guess who "I" is; the declaration says.
    """

    version: str
    anchor_columns: Mapping[str, tuple[str, ...]]          # row kind -> columns carrying surfaces
    principal_surfaces: Mapping[str, Mapping[str, tuple[str, ...]]] = field(default_factory=dict)
    must_appear_columns: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    principals: tuple[str, ...] = ()                       # the declared principal value(s)

    def hashed(self) -> dict[str, Any]:
        return {"version": self.version,
                "anchor_columns": {k: list(v) for k, v in sorted(self.anchor_columns.items())},
                "principal_surfaces": {k: {c: list(s) for c, s in sorted(v.items())}
                                       for k, v in sorted(self.principal_surfaces.items())},
                "must_appear_columns": {k: list(v)
                                        for k, v in sorted(self.must_appear_columns.items())},
                "principals": list(self.principals)}

    def surfaces_for_principal(self, kind: str, condition: str) -> tuple[str, ...]:
        by_kind = self.principal_surfaces.get(kind)
        if by_kind is None or condition not in by_kind:
            raise UnknownSurface("no declared principal surfaces", kind=kind,
                                 condition=condition)
        return by_kind[condition]


@dataclass(frozen=True, slots=True)
class DatasetDeclaration:
    """B.5's dataset declaration, frozen and content-addressed."""

    dataset_id: str
    row_kinds: tuple[RowKindSpec, ...]
    relation_kinds: tuple[RelationKindSpec, ...]
    alias_table: FieldAliasTable
    surface_set: SurfaceSetSchema
    segmenter_id: str
    seg_version: str
    blob_glob: str
    null_sentinel_rule: str = (
        "the minimum representable value of the column's integer dtype; INT32_MIN for int32, "
        "as declared by evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py:19-22")
    # THE TWO DECLARED OBJECTS THE LEAF NEEDS, AND THE ABLATION SWITCH ITSELF. Both default to
    # ABSENT, and an absent one adds NOTHING to ``hashed()`` - so a dataset that declares no
    # content axis has the same declaration hash, the same segment bytes and the same store it
    # had before this packet, bit for bit. That is not a convenience: without an OFF position
    # there is no ablation and lane F's identity audit cannot void an arm that equals dense
    # (charter: "any branch that makes an arm equal to its control").
    segmentation: "SegmentationRecipe | None" = None
    content_axes: tuple["ContentAxisSpec", ...] = ()

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for kind in self.row_kinds:
            if kind.kind in seen:
                raise ClosedColumnViolation("duplicate row kind", kind=kind.kind)
            seen.add(kind.kind)
            names: set[str] = set()
            for spec in kind.fields:
                if spec.type not in COLUMN_TYPES:
                    raise ClosedColumnViolation("unknown column type", kind=kind.kind,
                                                field=spec.name, type=spec.type)
                if spec.name in names:
                    raise ClosedColumnViolation("duplicate column", kind=kind.kind,
                                                field=spec.name)
                if spec.rung not in (RUNG_A, RUNG_B, RUNG_C):
                    raise ClosedColumnViolation("unknown producing rung", field=spec.name,
                                                rung=spec.rung)
                names.add(spec.name)
            if kind.time_field is not None and kind.time_field not in names:
                raise ClosedColumnViolation("time field outside the column list",
                                            kind=kind.kind, field=kind.time_field)
            for anchor in kind.anchor_fields:
                if anchor not in names:
                    raise ClosedColumnViolation("anchor field outside the column list",
                                                kind=kind.kind, field=anchor)
        for relation in self.relation_kinds:
            for endpoint in relation.source_kinds + relation.target_kinds:
                if endpoint not in seen:
                    raise ClosedColumnViolation("relation endpoint kind is not declared",
                                                relation=relation.kind, endpoint=endpoint)
        self._check_content_axes()

    def _check_content_axes(self) -> None:
        """Every declared axis resolves against THIS declaration, or refuses by name. O(axes)."""
        if not self.content_axes:
            return
        if self.segmentation is None:
            raise DeclarationRefused(
                "a content axis is declared with no segmentation recipe, so the leaf has no "
                "declared size", code="CONTENT-AXIS-WITHOUT-A-RECIPE",
                axes=[axis.axis for axis in self.content_axes])
        if self.segmentation.segmenter_version != self.seg_version:
            raise DeclarationRefused(
                "the segmentation recipe's version is not the declaration's seg_version, so a "
                "span id (B.1) and the recipe that cut it would disagree",
                code="SEGMENTATION-VERSION-MISMATCH",
                recipe=self.segmentation.segmenter_version, declaration=self.seg_version)
        names: set[str] = set()
        for axis in self.content_axes:
            if axis.axis in names:
                raise DeclarationRefused("two content axes share a name",
                                         code="CONTENT-AXIS-DUPLICATE", axis=axis.axis)
            names.add(axis.axis)
            for carrier in axis.carriers:
                spec = self.row_kind(carrier.kind)          # refuses an undeclared kind (B.5)
                if carrier.span_field and spec.field(carrier.span_field).type != "span_ref":
                    raise DeclarationRefused(
                        "a content carrier names a column that is not a span reference",
                        code="CONTENT-AXIS-CARRIER-INVALID", axis=axis.axis,
                        kind=carrier.kind, field=carrier.span_field)
                if carrier.decoder not in ("utf8", "json_string"):
                    raise DeclarationRefused(
                        "a content carrier names a decoder this reader does not declare",
                        code="CONTENT-AXIS-DECODER-UNKNOWN", axis=axis.axis,
                        decoder=carrier.decoder)

    def row_kind(self, kind: str) -> RowKindSpec:
        for spec in self.row_kinds:
            if spec.kind == kind:
                return spec
        raise ClosedColumnViolation("undeclared row kind", kind=kind,
                                    declared=[k.kind for k in self.row_kinds])

    def relation_kind(self, kind: str) -> RelationKindSpec:
        for spec in self.relation_kinds:
            if spec.kind == kind:
                return spec
        raise ClosedColumnViolation("undeclared relation kind", kind=kind,
                                    declared=[k.kind for k in self.relation_kinds])

    def hashed(self) -> dict[str, Any]:
        """The hashed field set. No clock, no generation (B.6).

        THE ENCODER IS STILL NOT IN A RECORD IDENTITY. B.6 and D.10 forbid a record id to be a
        function of an encoder's identity, and none is: this hash is the DECLARATION's, and what
        it carries of an axis is the declaration - which channel was asked for, at which rank, in
        which stored form. The span ids, the row ids and the blob handles underneath it are
        computed by ``spans.py``/``typed_row_store.py`` from bytes and offsets alone and do not
        see this field. What the axis's presence DOES change is B.28's per-item cache key (it is
        a function of this hash), and it must: an item whose segment holds no vectors is not the
        same item as one whose segment holds them, and a cache that could not tell them apart
        would hand back the wrong segment.

        An UNDECLARED axis and an undeclared recipe add no key at all, so a declaration made
        without them hashes exactly as it did before this packet existed.
        """
        out = {
            "dataset_id": self.dataset_id,
            "row_kinds": [k.hashed() for k in self.row_kinds],
            "relation_kinds": [r.hashed() for r in self.relation_kinds],
            "field_alias_table": self.alias_table.hashed(),
            "surface_set_schema": self.surface_set.hashed(),
            "segmenter_id": self.segmenter_id,
            "seg_version": self.seg_version,
            "blob_glob": self.blob_glob,
            "null_sentinel_rule": self.null_sentinel_rule,
        }
        if self.segmentation is not None:
            out["segmentation"] = self.segmentation.hashed()
        if self.content_axes:
            out["content_axes"] = [axis.hashed() for axis in self.content_axes]
        return out

    def axis(self, name: str) -> "ContentAxisSpec":
        for spec in self.content_axes:
            if spec.axis == name:
                return spec
        raise DeclarationRefused("undeclared content axis", code="CONTENT-AXIS-UNDECLARED",
                                 axis=name, declared=[a.axis for a in self.content_axes])

    @property
    def declaration_hash(self) -> str:
        """The declaration's own content hash (B.5). Complexity: O(size of the declaration)."""
        return chash(self.hashed())

    def amend(self, **_: Any) -> None:
        """There is no amendment. A declaration that can be edited is the tuning door (B.5)."""
        raise DeclarationFrozen("a dataset declaration does not change after it is declared",
                                dataset_id=self.dataset_id)
