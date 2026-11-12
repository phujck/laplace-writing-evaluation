"""Exact, read-only author-ruling custody for the Aisthesis carrier.

The durable ruling is an external source object, not configuration copied into the
carrier.  ``load_exact`` admits only the pinned bytes and ``project`` derives a
human-facing, content-addressed face from that custody object without opening a
store or performing a lifecycle act.  Exact source bytes and filesystem location
are available only at Audit grade; the content handle remains present as a
machine-facing currentness input and must not be rendered at rest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SOURCE_SCHEMA = "laplace.author-development-ruling/1"
CUSTODY_SCHEMA = "laplace.author-ruling-exact-custody/1"
PROJECTION_SCHEMA = "laplace.aisthesis-author-ruling/1"
CURRENTNESS_SCHEMA = "laplace.aisthesis-author-ruling-currentness/1"
TIMELINE_CONTRACT_SCHEMA = "laplace.aisthesis-product-delta-causal-timeline/1"
PUBLICATION_CUT_SOURCE_SCHEMA = "laplace.design-amendment/1"
PUBLICATION_CUT_POLICY_SCHEMA = "laplace.aisthesis-publication-cut-policy/1"

RULING_ID = "RUL-20260828-post-publication-semantic-lifecycle-regularization"
EXPECTED_CONTENT_HANDLE = (
    "sha256:2e268460ae1a7ecb66d45aad3e9069f1adc7e1870ea894825b32f8b8754e539a"
)
EXPECTED_BYTE_COUNT = 4_625
DEFAULT_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "POST-PUBLICATION-SEMANTIC-LIFECYCLE-REGULARIZATION-RULING.json"
)
PUBLICATION_CUT_ID = "AMEND-20260828-bounded-publication-cut-and-open-world-successors"
PUBLICATION_CUT_CONTENT_HANDLE = (
    "sha256:ac569da593c4802b55fce3ccca945326e0d60561c08c9654d0aaaef328c9870a"
)
PUBLICATION_CUT_BYTE_COUNT = 2_413
PUBLICATION_CUT_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "AMEND-SUPEREGO-DESIGN-PUBLICATION-CUT-LAW.json"
)
FROZEN_DESIGN_CONTENT_HANDLE = (
    "sha256:defd086c388e347c7ecfc081f8fa714d26cc11ad56e03c1f461a11634cec8f7f"
)

_GRADES = ("far", "mid", "near", "audit")
_TIMELINE_KINDS: tuple[tuple[str, str], ...] = (
    ("productive-work", "Productive work"),
    ("waiting", "Waiting"),
    ("reconstruction", "Reconstruction"),
    ("review", "Review"),
    ("refusal", "Refusal"),
    ("rework", "Rework"),
    ("unique-fault-catch", "Unique fault catch"),
    ("expected-observed-divergence", "Expected versus observed divergence"),
)


class AuthorRulingRefusal(RuntimeError):
    """A typed refusal to admit or project an author-ruling source."""

    def __init__(self, code: str, detail: str, **evidence: Any) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.evidence = evidence

    def as_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": "laplace.author-ruling-refusal/1",
            "status": "REFUSED",
            "code": self.code,
            "detail": self.detail,
            "evidence": _copy_json(self.evidence),
            "authority_effect": "none",
        }
        result["refusal_handle"] = canonical_handle(result)
        return result


@dataclass(frozen=True)
class ExactAuthorRuling:
    """Immutable bytes admitted under one expected digest and schema."""

    source_path: str
    raw_bytes: bytes
    content_handle: str
    byte_count: int
    expected_content_handle: str
    expected_byte_count: int

    @property
    def document(self) -> dict[str, Any]:
        # The returned object is a fresh parse, so callers cannot mutate custody.
        value = _decode_document(self.raw_bytes)
        _validate_document(value)
        return value

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": CUSTODY_SCHEMA,
            "status": "EXACT",
            "source_path": self.source_path,
            "content_handle": self.content_handle,
            "byte_count": self.byte_count,
            "source_schema": SOURCE_SCHEMA,
            "ruling_id": RULING_ID,
            "read_only": True,
            "authority_effect": "none",
        }


@dataclass(frozen=True)
class ExactPublicationCutLaw:
    """Immutable publication-cut amendment admitted under exact custody."""

    source_path: str
    raw_bytes: bytes
    content_handle: str
    byte_count: int
    expected_content_handle: str
    expected_byte_count: int

    @property
    def document(self) -> dict[str, Any]:
        value = _decode_publication_cut(self.raw_bytes)
        _validate_publication_cut(value)
        return value

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": CUSTODY_SCHEMA,
            "status": "EXACT",
            "source_path": self.source_path,
            "content_handle": self.content_handle,
            "byte_count": self.byte_count,
            "source_schema": PUBLICATION_CUT_SOURCE_SCHEMA,
            "amendment_id": PUBLICATION_CUT_ID,
            "target_design_handle": FROZEN_DESIGN_CONTENT_HANDLE,
            "read_only": True,
            "authority_effect": "none",
        }


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_handle(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _copy_json(value: Any) -> Any:
    return json.loads(_canonical_bytes(value))


def _handle_like(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value[7:], 16)
    except ValueError:
        return False
    return True


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _decode_document(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_ENCODING_REFUSED",
            "the exact ruling bytes are not UTF-8",
            offset=exc.start,
        ) from exc
    try:
        value = json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {token}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_JSON_REFUSED",
            "the exact ruling bytes are not strict JSON",
            error=str(exc),
        ) from exc
    if not isinstance(value, dict):
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_SHAPE_REFUSED",
            "the ruling root must be an object",
            observed_type=type(value).__name__,
        )
    return value


def _decode_publication_cut(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_ENCODING_REFUSED",
            "the exact publication-cut bytes are not UTF-8",
            offset=exc.start,
        ) from exc
    try:
        value = json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {token}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_JSON_REFUSED",
            "the exact publication-cut bytes are not strict JSON",
            error=str(exc),
        ) from exc
    if not isinstance(value, dict):
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_SHAPE_REFUSED",
            "the publication-cut root must be an object",
            observed_type=type(value).__name__,
        )
    return value


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_sequence(value: Any) -> bool:
    return _sequence(value) and bool(value) and all(_nonempty_text(item) for item in value)


def _validate_document(document: Mapping[str, Any]) -> None:
    if document.get("schema_version") != SOURCE_SCHEMA:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_SCHEMA_REFUSED",
            "the source does not carry the author-development-ruling schema",
            expected=SOURCE_SCHEMA,
            observed=document.get("schema_version"),
        )
    if document.get("id") != RULING_ID:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_ID_REFUSED",
            "the source is not the post-publication regularization ruling",
            expected=RULING_ID,
            observed=document.get("id"),
        )
    for field in ("authored_at", "author", "status", "priority", "purpose"):
        if not _nonempty_text(document.get(field)):
            raise AuthorRulingRefusal(
                "AUTHOR_RULING_FIELD_REFUSED",
                f"the ruling requires a non-empty {field}",
                field=field,
            )
    for field in ("rulings", "publication_order", "preserve"):
        if not _text_sequence(document.get(field)):
            raise AuthorRulingRefusal(
                "AUTHOR_RULING_FIELD_REFUSED",
                f"the ruling requires a non-empty text sequence at {field}",
                field=field,
            )
    cadence = document.get("cadence_boundary")
    if not isinstance(cadence, Mapping):
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_CADENCE_REFUSED",
            "cadence_boundary must be an object",
        )
    if not isinstance(cadence.get("babysitting_required"), bool):
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_CADENCE_REFUSED",
            "cadence_boundary.babysitting_required must be boolean",
        )
    for field in ("review_shape", "forbidden_regression"):
        if not _nonempty_text(cadence.get(field)):
            raise AuthorRulingRefusal(
                "AUTHOR_RULING_CADENCE_REFUSED",
                f"cadence_boundary requires {field}",
                field=field,
            )
    outside = document.get("outside_view_acceptance")
    if not isinstance(outside, Mapping):
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_OUTSIDE_VIEW_REFUSED",
            "outside_view_acceptance must be an object",
        )
    for field in ("premise", "measure", "success", "submerge_rule", "observability"):
        if not _nonempty_text(outside.get(field)):
            raise AuthorRulingRefusal(
                "AUTHOR_RULING_OUTSIDE_VIEW_REFUSED",
                f"outside_view_acceptance requires {field}",
                field=field,
            )


def _validate_publication_cut(document: Mapping[str, Any]) -> None:
    if document.get("schema_version") != PUBLICATION_CUT_SOURCE_SCHEMA:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_SCHEMA_REFUSED",
            "the source does not carry the design-amendment schema",
            expected=PUBLICATION_CUT_SOURCE_SCHEMA,
            observed=document.get("schema_version"),
        )
    if document.get("id") != PUBLICATION_CUT_ID:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_ID_REFUSED",
            "the source is not the bounded publication-cut amendment",
            expected=PUBLICATION_CUT_ID,
            observed=document.get("id"),
        )
    for field in (
        "status",
        "author",
        "premise",
        "closure_law",
        "design_custody_law",
        "epistemic_posture",
        "cadence_effect",
    ):
        if not _nonempty_text(document.get(field)):
            raise AuthorRulingRefusal(
                "PUBLICATION_CUT_FIELD_REFUSED",
                f"the publication-cut law requires a non-empty {field}",
                field=field,
            )
    for field in ("current_cut_blockers", "successor_residuals"):
        if not _text_sequence(document.get(field)):
            raise AuthorRulingRefusal(
                "PUBLICATION_CUT_FIELD_REFUSED",
                f"the publication-cut law requires a non-empty text sequence at {field}",
                field=field,
            )
    target = document.get("target_design")
    if not isinstance(target, Mapping):
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_TARGET_REFUSED",
            "target_design must be an object",
        )
    supplied_handle = target.get("sha256")
    if isinstance(supplied_handle, str) and not supplied_handle.startswith("sha256:"):
        supplied_handle = "sha256:" + supplied_handle
    if supplied_handle != FROZEN_DESIGN_CONTENT_HANDLE:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_TARGET_REFUSED",
            "the amendment does not target the frozen design coordinate",
            expected=FROZEN_DESIGN_CONTENT_HANDLE,
            observed=supplied_handle,
        )
    if target.get("status") != "FROZEN-IMPLEMENTATION-COORDINATE":
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_TARGET_REFUSED",
            "the target design is not frozen for implementation",
            observed=target.get("status"),
        )
    if not _nonempty_text(target.get("path")):
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_TARGET_REFUSED",
            "the frozen target requires its source path",
        )
    if not isinstance(target.get("bytes"), int) or target["bytes"] < 0:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_TARGET_REFUSED",
            "the frozen target requires its exact byte count",
            observed=target.get("bytes"),
        )


def load_exact(
    path: str | Path = DEFAULT_PATH,
    *,
    expected_content_handle: str = EXPECTED_CONTENT_HANDLE,
    expected_byte_count: int = EXPECTED_BYTE_COUNT,
) -> ExactAuthorRuling:
    """Read and admit one ruling only when its raw bytes match exact custody."""

    if not _handle_like(expected_content_handle):
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_EXPECTATION_REFUSED",
            "the expected content handle is malformed",
            expected_content_handle=expected_content_handle,
        )
    if not isinstance(expected_byte_count, int) or expected_byte_count < 0:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_EXPECTATION_REFUSED",
            "the expected byte count must be a non-negative integer",
            expected_byte_count=expected_byte_count,
        )
    source = Path(path).expanduser().resolve()
    try:
        raw = source.read_bytes()
    except FileNotFoundError as exc:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_MISSING",
            "the durable author-ruling artifact is absent",
            source_path=str(source),
        ) from exc
    except OSError as exc:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_READ_REFUSED",
            "the durable author-ruling artifact could not be read",
            source_path=str(source),
            error=str(exc),
        ) from exc

    observed_handle = "sha256:" + hashlib.sha256(raw).hexdigest()
    if len(raw) != expected_byte_count:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_SIZE_REFUSED",
            "the durable author-ruling byte count moved",
            source_path=str(source),
            expected_content_handle=expected_content_handle,
            expected_byte_count=expected_byte_count,
            observed_byte_count=len(raw),
            observed_content_handle=observed_handle,
        )
    if observed_handle != expected_content_handle:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_DIGEST_REFUSED",
            "the durable author-ruling digest moved",
            source_path=str(source),
            expected_content_handle=expected_content_handle,
            observed_content_handle=observed_handle,
        )

    document = _decode_document(raw)
    _validate_document(document)
    return ExactAuthorRuling(
        source_path=str(source),
        raw_bytes=raw,
        content_handle=observed_handle,
        byte_count=len(raw),
        expected_content_handle=expected_content_handle,
        expected_byte_count=expected_byte_count,
    )


def load_publication_cut_law(
    path: str | Path = PUBLICATION_CUT_PATH,
    *,
    expected_content_handle: str = PUBLICATION_CUT_CONTENT_HANDLE,
    expected_byte_count: int = PUBLICATION_CUT_BYTE_COUNT,
) -> ExactPublicationCutLaw:
    """Admit the immutable publication-cut amendment under exact raw-byte custody."""

    if not _handle_like(expected_content_handle):
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_EXPECTATION_REFUSED",
            "the expected publication-cut content handle is malformed",
            expected_content_handle=expected_content_handle,
        )
    if not isinstance(expected_byte_count, int) or expected_byte_count < 0:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_EXPECTATION_REFUSED",
            "the expected publication-cut byte count must be a non-negative integer",
            expected_byte_count=expected_byte_count,
        )
    source = Path(path).expanduser().resolve()
    try:
        raw = source.read_bytes()
    except FileNotFoundError as exc:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_MISSING",
            "the immutable publication-cut amendment is absent",
            source_path=str(source),
        ) from exc
    except OSError as exc:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_READ_REFUSED",
            "the immutable publication-cut amendment could not be read",
            source_path=str(source),
            error=str(exc),
        ) from exc

    observed_handle = "sha256:" + hashlib.sha256(raw).hexdigest()
    if len(raw) != expected_byte_count:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_SIZE_REFUSED",
            "the immutable publication-cut byte count moved",
            source_path=str(source),
            expected_content_handle=expected_content_handle,
            expected_byte_count=expected_byte_count,
            observed_byte_count=len(raw),
            observed_content_handle=observed_handle,
        )
    if observed_handle != expected_content_handle:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_DIGEST_REFUSED",
            "the immutable publication-cut digest moved",
            source_path=str(source),
            expected_content_handle=expected_content_handle,
            observed_content_handle=observed_handle,
        )

    document = _decode_publication_cut(raw)
    _validate_publication_cut(document)
    return ExactPublicationCutLaw(
        source_path=str(source),
        raw_bytes=raw,
        content_handle=observed_handle,
        byte_count=len(raw),
        expected_content_handle=expected_content_handle,
        expected_byte_count=expected_byte_count,
    )


def _publication_cut_policy(
    custody: ExactPublicationCutLaw | None,
    *,
    grade: str,
) -> dict[str, Any]:
    if custody is None:
        face = {
            "schema_version": PUBLICATION_CUT_POLICY_SCHEMA,
            "status": "UNKNOWN",
            "content_handle": None,
            "target_design_handle": None,
            "human_summary": {
                "title": "Bounded publication cut",
                "disposition": "UNKNOWN",
                "reason": "exact publication-cut custody is absent",
            },
            "current_cut_blockers": [],
            "owned_successor_residuals": [],
            "classification": {
                "default_for_new_compatible_insight": "UNKNOWN",
                "blocks_current_cut_only_on_explicit_contradiction": None,
            },
            "exact_descent": {
                "status": "UNKNOWN",
                "missing_dependency": "exact publication-cut custody",
            },
            "read_only": True,
            "authority_effect": "none",
        }
        face["policy_handle"] = canonical_handle(face)
        return face
    if not isinstance(custody, ExactPublicationCutLaw):
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_CUSTODY_REFUSED",
            "publication-cut projection requires exact custody",
            observed_type=type(custody).__name__,
        )
    if custody.content_handle != custody.expected_content_handle:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_CUSTODY_REFUSED",
            "the admitted publication-cut handle mismatches its expectation",
            expected=custody.expected_content_handle,
            observed=custody.content_handle,
        )
    if custody.byte_count != custody.expected_byte_count or len(custody.raw_bytes) != custody.byte_count:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_CUSTODY_REFUSED",
            "the admitted publication-cut byte-count preimage is inconsistent",
            expected=custody.expected_byte_count,
            observed=len(custody.raw_bytes),
        )
    observed_handle = "sha256:" + hashlib.sha256(custody.raw_bytes).hexdigest()
    if observed_handle != custody.content_handle:
        raise AuthorRulingRefusal(
            "PUBLICATION_CUT_CUSTODY_REFUSED",
            "the publication-cut raw bytes moved after admission",
            expected=custody.content_handle,
            observed=observed_handle,
        )

    document = custody.document
    target = document["target_design"]
    active = document["status"] == "ACTIVE-SEPARATE-AMENDMENT"
    face = {
        "schema_version": PUBLICATION_CUT_POLICY_SCHEMA,
        "status": "CURRENT" if active else "STALE",
        # Machine-only shown/currentness inputs; never resting human copy.
        "content_handle": custody.content_handle,
        "target_design_handle": FROZEN_DESIGN_CONTENT_HANDLE,
        "human_summary": {
            "title": "Bounded publication cut",
            "disposition": "RUNNABLE-CUT" if active else "STALE",
            "premise": document["premise"],
            "closure_law": document["closure_law"],
            "cadence_effect": document["cadence_effect"],
        },
        "source_provenance": {
            "kind": "immutable design amendment",
            "amendment_id": document["id"],
            "author": document["author"],
            "source_status": document["status"],
            "custody": "EXACT-DIGEST-VERIFIED",
            "byte_count": custody.byte_count,
            "target_status": target["status"],
            "target_byte_count": target["bytes"],
        },
        "current_cut_blockers": _copy_json(document["current_cut_blockers"]),
        "owned_successor_residuals": _copy_json(document["successor_residuals"]),
        "classification": {
            "default_for_new_compatible_insight": "OWNED-SUCCESSOR-RESIDUAL",
            "blocks_current_cut_only_on_explicit_contradiction": True,
            "design_custody_law": document["design_custody_law"],
            "epistemic_posture": document["epistemic_posture"],
        },
        "exact_descent": (
            {
                "status": "COMPLETE",
                "source_path": custody.source_path,
                "content_handle": custody.content_handle,
                "byte_count": custody.byte_count,
                "target_design_path": target["path"],
                "target_design_handle": FROZEN_DESIGN_CONTENT_HANDLE,
                "document": _copy_json(document),
            }
            if grade == "audit"
            else {
                "status": "AVAILABLE-AT-AUDIT",
                "grade_required": "audit",
            }
        ),
        "read_only": True,
        "authority_effect": "none",
    }
    face["policy_handle"] = canonical_handle(face)
    return face


def _timeline_contract(outside: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the required observable categories without fabricating observations."""

    return {
        "schema_version": TIMELINE_CONTRACT_SCHEMA,
        "status": "UNKNOWN",
        "human_label": "Product delta and coordination cost",
        "premise": outside["premise"],
        "measure": outside["measure"],
        "success": outside["success"],
        "submerge_rule": outside["submerge_rule"],
        "required_event_kinds": [
            {"kind": kind, "label": label} for kind, label in _TIMELINE_KINDS
        ],
        "events": [],
        "comparison": {
            "status": "UNKNOWN",
            "product_delta": None,
            "coordination_cost": None,
            "ratio": None,
            "expected": None,
            "observed": None,
        },
        "missing_dependency": (
            "an exact shared operational causal-timeline observation and consumption receipt"
        ),
        "authority_effect": "none",
    }


def project(
    custody: ExactAuthorRuling,
    *,
    publication_cut: ExactPublicationCutLaw | None = None,
    grade: str = "mid",
) -> dict[str, Any]:
    """Derive one deterministic carrier face from an exact custody object."""

    if not isinstance(custody, ExactAuthorRuling):
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_CUSTODY_REFUSED",
            "projection requires ExactAuthorRuling custody, not an unverified mapping",
            observed_type=type(custody).__name__,
        )
    if grade not in _GRADES:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_GRADE_REFUSED",
            "representation grade must be far, mid, near or audit",
            observed=grade,
        )
    if custody.content_handle != custody.expected_content_handle:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_CUSTODY_REFUSED",
            "the admitted content handle no longer matches its expectation",
            expected=custody.expected_content_handle,
            observed=custody.content_handle,
        )
    if custody.byte_count != custody.expected_byte_count or len(custody.raw_bytes) != custody.byte_count:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_CUSTODY_REFUSED",
            "the admitted byte-count preimage is inconsistent",
            expected=custody.expected_byte_count,
            observed=len(custody.raw_bytes),
        )
    observed_handle = "sha256:" + hashlib.sha256(custody.raw_bytes).hexdigest()
    if observed_handle != custody.content_handle:
        raise AuthorRulingRefusal(
            "AUTHOR_RULING_CUSTODY_REFUSED",
            "the admitted raw bytes no longer match the content handle",
            expected=custody.content_handle,
            observed=observed_handle,
        )

    document = custody.document
    active = document["status"] == "ACTIVE"
    outside = document["outside_view_acceptance"]
    cadence = document["cadence_boundary"]
    publication_policy = _publication_cut_policy(publication_cut, grade=grade)
    face: dict[str, Any] = {
        "schema_version": PROJECTION_SCHEMA,
        "status": "CURRENT" if active else "STALE",
        # Machine-facing identity for parent model/shown preimages. Renderers must not
        # print it outside the Audit descent below.
        "content_handle": custody.content_handle,
        "source_handles": {
            "author_ruling": custody.content_handle,
            "publication_cut_law": (
                publication_cut.content_handle if publication_cut is not None else None
            ),
        },
        "human_summary": {
            "title": "Post-publication semantic and lifecycle regularization",
            "purpose": document["purpose"],
            "priority": document["priority"],
            "state": document["status"],
            "next_publication_priority": document["publication_order"][0],
            "direction_count": len(document["rulings"]),
            "outside_view": outside["premise"],
            "operating_rule": outside["success"],
        },
        "source_provenance": {
            "kind": "durable author ruling",
            "ruling_id": document["id"],
            "author": document["author"],
            "authored_at": document["authored_at"],
            "priority": document["priority"],
            "source_status": document["status"],
            "custody": "EXACT-DIGEST-VERIFIED",
            "byte_count": custody.byte_count,
        },
        "currentness": {
            "schema_version": CURRENTNESS_SCHEMA,
            "status": "CURRENT" if active else "STALE",
            "reason": (
                "the exact pinned ruling is ACTIVE"
                if active
                else "the exact pinned ruling is not ACTIVE"
            ),
            "source_status": document["status"],
        },
        "publication_order": _copy_json(document["publication_order"]),
        "cadence": {
            "babysitting_required": cadence["babysitting_required"],
            "review_shape": cadence["review_shape"],
            "forbidden_regression": cadence["forbidden_regression"],
        },
        "outside_view_acceptance": {
            "premise": outside["premise"],
            "measure": outside["measure"],
            "success": outside["success"],
            "submerge_rule": outside["submerge_rule"],
            "observability": outside["observability"],
            "causal_timeline": _timeline_contract(outside),
        },
        "publication_cut_policy": publication_policy,
        "preserve": _copy_json(document["preserve"]),
        "representation": {
            "grade": grade,
            "exact_source_visible": grade == "audit",
        },
        "exact_descent": (
            {
                "status": "COMPLETE",
                "source_path": custody.source_path,
                "content_handle": custody.content_handle,
                "byte_count": custody.byte_count,
                "source_schema": document["schema_version"],
                "document": _copy_json(document),
            }
            if grade == "audit"
            else {
                "status": "AVAILABLE-AT-AUDIT",
                "grade_required": "audit",
            }
        ),
        "read_only": True,
        "authority_effect": "none",
    }
    face["projection_handle"] = canonical_handle(face)
    return face


def currentness(
    served: Mapping[str, Any],
    custody: ExactAuthorRuling,
    *,
    publication_cut: ExactPublicationCutLaw | None = None,
) -> dict[str, Any]:
    """Rederive the complete face and compare it with a previously served one."""

    if not isinstance(served, Mapping) or served.get("schema_version") != PROJECTION_SCHEMA:
        result = {
            "schema_version": CURRENTNESS_SCHEMA,
            "status": "REFUSED",
            "reason": "the served author-ruling projection has the wrong schema",
            "mismatches": ["schema_version"],
            "authority_effect": "none",
        }
        result["currentness_handle"] = canonical_handle(result)
        return result
    grade = (served.get("representation") or {}).get("grade")
    try:
        rederived = project(custody, publication_cut=publication_cut, grade=grade)
    except AuthorRulingRefusal as exc:
        result = {
            "schema_version": CURRENTNESS_SCHEMA,
            "status": "REFUSED",
            "reason": exc.detail,
            "refusal_code": exc.code,
            "mismatches": ["source_custody"],
            "authority_effect": "none",
        }
        result["currentness_handle"] = canonical_handle(result)
        return result

    served_copy = _copy_json(served)
    supplied_projection_handle = served_copy.pop("projection_handle", None)
    served_integrity = canonical_handle(served_copy)
    expected_copy = _copy_json(rederived)
    expected_projection_handle = expected_copy.pop("projection_handle")
    mismatches: list[str] = []
    if supplied_projection_handle != served_integrity:
        mismatches.append("served_projection_integrity")
    if supplied_projection_handle != expected_projection_handle:
        mismatches.append("projection_handle")
    if served_copy != expected_copy:
        mismatches.append("projection_preimage")
    if served.get("content_handle") != custody.content_handle:
        mismatches.append("content_handle")

    status = "CURRENT" if not mismatches else "STALE"
    result = {
        "schema_version": CURRENTNESS_SCHEMA,
        "status": status,
        "reason": (
            "the complete author-ruling projection rederives exactly"
            if status == "CURRENT"
            else "the served author-ruling projection no longer rederives"
        ),
        "content_handle": custody.content_handle,
        "served_projection_handle": supplied_projection_handle,
        "rederived_projection_handle": expected_projection_handle,
        "mismatches": sorted(set(mismatches)),
        "authority_effect": "none",
    }
    result["currentness_handle"] = canonical_handle(result)
    return result


__all__ = [
    "AuthorRulingRefusal",
    "CURRENTNESS_SCHEMA",
    "DEFAULT_PATH",
    "EXPECTED_BYTE_COUNT",
    "EXPECTED_CONTENT_HANDLE",
    "ExactAuthorRuling",
    "ExactPublicationCutLaw",
    "FROZEN_DESIGN_CONTENT_HANDLE",
    "PROJECTION_SCHEMA",
    "PUBLICATION_CUT_BYTE_COUNT",
    "PUBLICATION_CUT_CONTENT_HANDLE",
    "PUBLICATION_CUT_ID",
    "PUBLICATION_CUT_PATH",
    "PUBLICATION_CUT_POLICY_SCHEMA",
    "PUBLICATION_CUT_SOURCE_SCHEMA",
    "RULING_ID",
    "SOURCE_SCHEMA",
    "TIMELINE_CONTRACT_SCHEMA",
    "canonical_handle",
    "currentness",
    "load_exact",
    "load_publication_cut_law",
    "project",
]
