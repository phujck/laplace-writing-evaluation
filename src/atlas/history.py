"""The canonical typed history of the one Atlas conceptric.

Every seat, lifecycle change, reconstruction, join and corpus act is an ``AtlasEvent`` in one
append-only stream. Handles are lawful boundaries. Movement is multi-directional and names its
operator, grade axis, provenance and residual. A fibre change is impossible without an explicit
``TransportReceipt``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Mapping

from .errors import SchemaFieldMissing, SchemaVersionMismatch, StateTransitionRefused
from .ids import chash


class SeatRole(str, Enum):
    EGO = "ego"
    SUPEREGO = "superego"
    SENSORIUM = "sensorium"
    AUTHOR = "author"
    SYSTEM = "system"
    PROVIDER = "provider"


class EventKind(str, Enum):
    LIFECYCLE = "lifecycle.transition"
    SEAT = "seat.transition"
    SEAT_JOIN = "seat.joined"
    SEAT_OCCUPANCY_BINDING = "seat.occupancy-bound"
    REGION_CHECKOUT = "region.checked-out"
    REGION_CHECKIN = "region.checked-in"
    REGION_PUBLICATION_PREPARED = "region.publication-prepared"
    REGION_PUBLICATION_SIGNED = "region.publication-signed"
    REGION_PUBLICATION_AUTHORIZED = "region.publication-authorized"
    REGION_PUBLICATION_FINALIZED = "region.publication-finalized"
    ASSUMPTION = "assumption.selected"
    GRADE_AXIS = "grade-axis.declared"
    MOVE = "reconstruction.moved"
    JOIN = "conjugate.joined"
    TRANSPORT = "fibre.transported"
    MATERIALIZATION = "reconstruction.materialized"
    CORPUS_ACT = "corpus.acted"
    PROJECTION = "projection.rendered"
    DECISION = "decision.recorded"
    PROMOTION = "state.promoted"
    PROLONGATION = "state.prolonged"
    ROLLBACK = "state.rolled-back"
    REPL = "repl.evaluated"
    OBSERVATION = "sensorium.observed"
    MESSAGE = "seat.message-sent"
    MESSAGE_PULL = "seat.messages-pulled"
    MESSAGE_ACK = "seat.message-acknowledged"
    MESSAGE_PRESERVE_FORK = "seat.message-fork-preserved"
    MESSAGE_SUPERSESSION = "seat.message-superseded"
    MESSAGE_MIGRATION_SUPERSESSION = "seat.message-migration-superseded"
    MESSAGE_EXPIRY = "seat.message-expired"
    REVISION = "source.revised"
    PERMISSION_REQUEST = "permission.requested"
    PERMISSION_DECISION = "permission.decided"
    OBJECT = "object.declared"
    EDGE = "edge.declared"
    WATCHER = "watcher.registered"
    WATCH_CHECKPOINT = "watcher.checkpointed"


class LifecyclePhase(str, Enum):
    SLEEPING = "sleeping"
    AWAKE = "awake"
    SEWING_UP = "sewing-up"


class LifecycleAction(str, Enum):
    WAKE = "wake"
    COLD_WAKE = "cold-wake"
    SEW_UP = "sew-up"
    SLEEP = "sleep"


class SeatStatus(str, Enum):
    ACTIVE = "active"
    RELAYING = "relaying"
    CLOSED = "closed"


class SeatAction(str, Enum):
    FOUND = "found"
    RELAY = "relay"
    ACTIVATE = "activate"
    CLOSE = "close"


class LeaseDeclarationKind(str, Enum):
    NATIVE = "native"
    JOURNAL_BOOTSTRAP = "journal-bootstrap"


class LeaseCheckinOutcome(str, Enum):
    COMMITTED = "committed"
    NOOP = "noop"
    ABANDONED = "abandoned"
    FAILED = "failed"


class MoveDirection(str, Enum):
    DOWN = "down"
    UP = "up"
    LATERAL = "lateral"
    CONJUGATE = "conjugate"
    TRANSPORT = "transport"
    LINEAGE = "lineage"
    OUTWARD = "outward"


class ResidualStatus(str, Enum):
    WITHIN_BOUND = "within_bound"
    EXCEEDS_BOUND = "exceeds_bound"
    UNKNOWN = "unknown"


class ActPhase(str, Enum):
    READ = "read"
    PREVIEW = "preview"
    COMMIT = "commit"
    ROLLBACK = "rollback"


class Validity(str, Enum):
    VALID = "valid"
    STALE = "stale"
    REFUSED = "refused"
    PREVIEW = "preview-only"


class DeliveryState(str, Enum):
    QUEUED = "queued"
    PULLED = "pulled"
    DELIVERED = "delivered"
    REFUSED = "refused"
    QUARANTINED = "quarantined"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class AcknowledgementDisposition(str, Enum):
    ACCEPTED = "accepted"
    REFUSED = "refused"


class PermissionOutcome(str, Enum):
    GRANTED = "granted"
    DENIED = "denied"


class WatchSourceKind(str, Enum):
    CONCEPTRIC_EVENTS = "conceptric-events"
    FILESYSTEM_PATH = "filesystem-path"


class WatchStatus(str, Enum):
    ARMED = "armed"
    FIRED = "fired"
    EXPIRED = "expired"
    ERROR = "error"


class ReplOperation(str, Enum):
    FOCUS = "focus"
    DECLARE_ASSUMPTION = "declare-assumption"
    SWITCH_ASSUMPTION = "switch-assumption"
    MOVE = "move"
    RECONSTRUCT = "reconstruct"
    INSPECT_SEMANTIC = "inspect-semantic"
    INSPECT_SPECTRAL = "inspect-spectral"
    JOIN = "join"
    TRANSPORT = "transport"
    COMPARE = "compare"
    DIFF = "diff"
    EXPLAIN = "explain-provenance"
    PIN = "pin"
    MATERIALIZE = "materialize"
    BRANCH = "branch"
    CHECKPOINT = "checkpoint"
    ACT_PREVIEW = "act-preview"
    ACT_COMMIT = "act-commit"
    ACT_ROLLBACK = "act-rollback"


def _validate_live_authority_projection(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Strictly validate the checksummed live projection and all derivable roots."""

    expected = (
        "schema_version",
        "active_context",
        "seat_occupancy",
        "seat_occupancy_root",
        "provider_sessions",
        "provider_session_root",
        "recipient_mail",
        "region_leases",
        "region_lease_root",
        "development_review_root",
        "seat_mail_frontier_root",
        "retired_generation_membership",
        "unresolved_obligation_handles",
        "synthetics_genesis_handles",
    )
    _require_exact(raw, expected, "live authority projection")
    if raw.get("schema_version") != "atlas.live-authority-projection/1":
        raise ValueError("live authority projection schema is unknown")
    occupancy = raw["seat_occupancy"]
    providers = raw["provider_sessions"]
    recipients = raw["recipient_mail"]
    leases = raw["region_leases"]
    if not all(isinstance(value, Mapping) for value in (occupancy, providers, recipients, leases)):
        raise ValueError("live authority projection accumulators must be mappings")
    derived_providers: dict[str, dict[str, Any]] = {}
    for seat_id, row in sorted(occupancy.items()):
        if not isinstance(seat_id, str) or not isinstance(row, Mapping):
            raise ValueError("seat occupancy accumulator contains an invalid row")
        binding = row.get("binding")
        if row.get("routing_authority") is True and isinstance(binding, Mapping):
            provider_ref = binding.get("provider_session_ref")
            if not isinstance(provider_ref, str) or not provider_ref:
                raise ValueError("routing occupancy omits its provider session")
            derived_providers.setdefault(provider_ref, {})[seat_id] = dict(row)
    root_pairs = (
        (
            "seat_occupancy_root",
            chash(
                {
                    "schema_version": "atlas.seat-occupancy-accumulator/1",
                    "occupancy": occupancy,
                }
            ),
        ),
        (
            "provider_session_root",
            chash(
                {
                    "schema_version": "atlas.provider-session-accumulator/1",
                    "providers": providers,
                }
            ),
        ),
        (
            "region_lease_root",
            chash(
                {
                    "schema_version": "atlas.region-lease-accumulator/1",
                    "leases": leases,
                }
            ),
        ),
        (
            "seat_mail_frontier_root",
            chash(
                {
                    "schema_version": "atlas.seat-mail-frontier-root/1",
                    "recipients": recipients,
                }
            ),
        ),
    )
    if dict(providers) != derived_providers:
        raise ValueError("provider accumulator disagrees with seat occupancy")
    for field_name, expected_root in root_pairs:
        if raw.get(field_name) != expected_root:
            raise ValueError(f"live authority projection {field_name} does not verify")
    retired = raw["retired_generation_membership"]
    if not isinstance(retired, Mapping):
        raise ValueError("retired generation membership must be a mapping")
    _require_exact(
        retired,
        ("schema_version", "algorithm", "bits_hex", "root"),
        "retired generation membership",
    )
    if (
        retired.get("schema_version") != "atlas.retired-generation-membership/1"
        or retired.get("algorithm") != "refusal-safe-bloom-2048x4"
        or not isinstance(retired.get("bits_hex"), str)
        or len(str(retired.get("bits_hex"))) != 512
        or retired.get("root")
        != chash(
            {
                "schema_version": "atlas.retired-generation-membership/1",
                "bits_hex": retired.get("bits_hex"),
            }
        )
    ):
        raise ValueError("retired generation membership does not verify")
    for field_name in (
        "development_review_root",
        "seat_occupancy_root",
        "provider_session_root",
        "region_lease_root",
        "seat_mail_frontier_root",
    ):
        if not isinstance(raw.get(field_name), str) or not str(raw[field_name]).startswith(
            "sha256:"
        ):
            raise ValueError(f"live authority projection {field_name} must be a sha256 handle")
    for field_name in ("unresolved_obligation_handles", "synthetics_genesis_handles"):
        value = raw[field_name]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"live authority projection {field_name} must be a string list")
    return dict(raw)


@dataclass(frozen=True)
class AuthorityCheckpoint:
    """One checksummed, replaceable authority epoch beside the canonical ledger.

    The append-only event rows remain the complete history.  This record is the compact proof
    from which live readers start; its digest detects accidental corruption.  A process with local
    write access can forge this adjacent record and digest, so independent stopped-writer replay
    remains the authority verifier until a later event/CAS-bound epoch closes that residual.
    """

    SCHEMA_VERSION = "atlas.authority-checkpoint/1"

    cursor: int
    head_event_id: str | None
    head_record_digest: str
    implementation_digest: str
    environment_root: str
    dirty_paths_root: str
    authority: Mapping[str, Any]

    def __post_init__(self) -> None:
        if isinstance(self.cursor, bool) or not isinstance(self.cursor, int) or self.cursor < 0:
            raise ValueError("authority checkpoint cursor must be a non-negative integer")
        for field_name in (
            "head_record_digest",
            "implementation_digest",
            "environment_root",
            "dirty_paths_root",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.startswith("sha256:"):
                raise ValueError(f"authority checkpoint {field_name} must be a sha256 handle")
        if self.cursor == 0 and self.head_event_id is not None:
            raise ValueError("genesis authority checkpoint cannot name a head event")
        if self.cursor > 0 and not self.head_event_id:
            raise ValueError("non-genesis authority checkpoint requires a head event")
        if not isinstance(self.authority, Mapping):
            raise ValueError("authority checkpoint authority must be a mapping")
        _validate_live_authority_projection(self.authority)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "cursor": self.cursor,
            "head_event_id": self.head_event_id,
            "head_record_digest": self.head_record_digest,
            "implementation_digest": self.implementation_digest,
            "environment_root": self.environment_root,
            "dirty_paths_root": self.dirty_paths_root,
            "authority": dict(self.authority),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AuthorityCheckpoint":
        _check_version(raw, cls.SCHEMA_VERSION, "authority checkpoint")
        _require_exact(
            raw,
            (
                "schema_version",
                "cursor",
                "head_event_id",
                "head_record_digest",
                "implementation_digest",
                "environment_root",
                "dirty_paths_root",
                "authority",
            ),
            "authority checkpoint",
        )
        cursor = raw["cursor"]
        if isinstance(cursor, bool) or not isinstance(cursor, int):
            raise ValueError("authority checkpoint cursor must be an exact JSON integer")
        head_event_id = raw["head_event_id"]
        if head_event_id is not None and (
            not isinstance(head_event_id, str) or not head_event_id
        ):
            raise ValueError("authority checkpoint head_event_id must be null or a string")
        for field_name in (
            "head_record_digest",
            "implementation_digest",
            "environment_root",
            "dirty_paths_root",
        ):
            if not isinstance(raw[field_name], str):
                raise ValueError(f"authority checkpoint {field_name} must be an exact JSON string")
        authority = raw["authority"]
        if not isinstance(authority, Mapping):
            raise ValueError("authority checkpoint authority must be a mapping")
        return cls(
            cursor=cursor,
            head_event_id=head_event_id,
            head_record_digest=raw["head_record_digest"],
            implementation_digest=raw["implementation_digest"],
            environment_root=raw["environment_root"],
            dirty_paths_root=raw["dirty_paths_root"],
            authority=dict(authority),
        )
def _check_version(raw: Mapping[str, Any], expected: str, where: str) -> None:
    if raw.get("schema_version") != expected:
        raise SchemaVersionMismatch(
            f"{where} carries an unknown schema version",
            expected=expected,
            got=raw.get("schema_version"),
        )


def _require_exact(raw: Mapping[str, Any], keys: tuple[str, ...], where: str) -> None:
    expected = {"schema_version", *keys}
    missing = sorted(expected - set(raw))
    extra = sorted(set(raw) - expected)
    if missing or extra:
        raise SchemaFieldMissing(
            f"{where} fields do not match its schema",
            fields=missing,
            unexpected=extra,
        )


def _nonempty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise StateTransitionRefused("history field must be non-empty", field=field)


def _coordinate(value: str | int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise StateTransitionRefused("grade coordinate must be a string or integer", field=field)
    if isinstance(value, str) and not value.strip():
        raise StateTransitionRefused("grade coordinate cannot be empty", field=field)


def _timestamp(value: str, field: str) -> None:
    _nonempty(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StateTransitionRefused("timestamp must be ISO-8601", field=field) from exc
    if parsed.tzinfo is None:
        raise StateTransitionRefused("timestamp must carry a timezone", field=field)


def _region_path(value: str, field: str = "region") -> None:
    _nonempty(value, field)
    if value.startswith(("/", "\\")) or "\\" in value or value.endswith("/"):
        raise StateTransitionRefused(
            "authority region must be a canonical repository-relative path", field=field
        )
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise StateTransitionRefused(
            "authority region cannot contain empty or traversing path segments", field=field
        )
    if any(character in value for character in ("*", "?", "[", "]", "\x00")):
        raise StateTransitionRefused(
            "authority region is an exact path prefix, not a glob", field=field
        )
    if parts[0] in {".git", "soul"}:
        raise StateTransitionRefused(
            "authority region names a repository root that no delegated seat may mutate",
            field=field,
            root=parts[0],
        )


def validate_authority_region(value: str, field: str = "region") -> None:
    """Public outer-door validator sharing the history model's exact path law."""

    _region_path(value, field)


@dataclass(frozen=True)
class DeviceFallback:
    SCHEMA_VERSION: ClassVar[str] = "device-fallback/1"

    from_device: str
    to_device: str
    reason: str
    acknowledged: bool

    def __post_init__(self) -> None:
        for name, value in (
            ("from_device", self.from_device),
            ("to_device", self.to_device),
            ("reason", self.reason),
        ):
            _nonempty(value, name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "from": self.from_device,
            "to": self.to_device,
            "reason": self.reason,
            "acknowledged": self.acknowledged,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DeviceFallback":
        _check_version(raw, cls.SCHEMA_VERSION, "DeviceFallback")
        _require_exact(raw, ("from", "to", "reason", "acknowledged"), "DeviceFallback")
        return cls(
            from_device=raw["from"],
            to_device=raw["to"],
            reason=raw["reason"],
            acknowledged=raw["acknowledged"],
        )


@dataclass(frozen=True)
class DeviceReceipt:
    SCHEMA_VERSION: ClassVar[str] = "device-receipt/1"

    requested: str
    selected: str
    available: tuple[str, ...]
    utilization: Mapping[str, float | None]
    fallbacks: tuple[DeviceFallback, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.requested, "requested")
        _nonempty(self.selected, "selected")
        if not self.available or any(not item for item in self.available):
            raise StateTransitionRefused("device availability must be explicit")
        if self.selected not in self.available:
            raise StateTransitionRefused(
                "selected device was not observed available", selected=self.selected
            )
        if self.requested != self.selected and not self.fallbacks:
            raise StateTransitionRefused("device fallback requires a receipt")
        if any(not fallback.acknowledged for fallback in self.fallbacks):
            raise StateTransitionRefused("unacknowledged device fallback cannot be banked")
        for name, value in self.utilization.items():
            _nonempty(name, "utilization device")
            if value is not None and not 0 <= value <= 100:
                raise StateTransitionRefused(
                    "device utilization must be a percentage", device=name, value=value
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "requested": self.requested,
            "selected": self.selected,
            "available": list(self.available),
            "utilization": dict(self.utilization),
            "fallbacks": [item.to_dict() for item in self.fallbacks],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DeviceReceipt":
        _check_version(raw, cls.SCHEMA_VERSION, "DeviceReceipt")
        _require_exact(
            raw,
            ("requested", "selected", "available", "utilization", "fallbacks"),
            "DeviceReceipt",
        )
        return cls(
            requested=raw["requested"],
            selected=raw["selected"],
            available=tuple(raw["available"]),
            utilization=dict(raw["utilization"]),
            fallbacks=tuple(DeviceFallback.from_dict(item) for item in raw["fallbacks"]),
        )


@dataclass(frozen=True)
class RuntimeReceipt:
    SCHEMA_VERSION: ClassVar[str] = "runtime-receipt/1"

    receipt_id: str
    observed_at: str
    executable: str
    expected_executable: str
    implementation: str
    version: str
    prefix: str
    base_prefix: str
    repo_root: str
    repo_venv_refused: bool
    device: DeviceReceipt

    def __post_init__(self) -> None:
        for name, value in (
            ("receipt_id", self.receipt_id),
            ("observed_at", self.observed_at),
            ("executable", self.executable),
            ("expected_executable", self.expected_executable),
            ("implementation", self.implementation),
            ("version", self.version),
            ("prefix", self.prefix),
            ("base_prefix", self.base_prefix),
            ("repo_root", self.repo_root),
        ):
            _nonempty(value, name)
        if not self.repo_venv_refused:
            raise StateTransitionRefused("canonical runtime did not attest repo .venv refusal")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "receipt_id": self.receipt_id,
            "observed_at": self.observed_at,
            "executable": self.executable,
            "expected_executable": self.expected_executable,
            "implementation": self.implementation,
            "version": self.version,
            "prefix": self.prefix,
            "base_prefix": self.base_prefix,
            "repo_root": self.repo_root,
            "repo_venv_refused": self.repo_venv_refused,
            "device": self.device.to_dict(),
        }

    def identity_dict(self) -> dict[str, Any]:
        raw = self.to_dict()
        raw.pop("receipt_id")
        raw.pop("observed_at")
        return raw

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RuntimeReceipt":
        _check_version(raw, cls.SCHEMA_VERSION, "RuntimeReceipt")
        keys = (
            "receipt_id",
            "observed_at",
            "executable",
            "expected_executable",
            "implementation",
            "version",
            "prefix",
            "base_prefix",
            "repo_root",
            "repo_venv_refused",
            "device",
        )
        _require_exact(raw, keys, "RuntimeReceipt")
        return cls(
            receipt_id=raw["receipt_id"],
            observed_at=raw["observed_at"],
            executable=raw["executable"],
            expected_executable=raw["expected_executable"],
            implementation=raw["implementation"],
            version=raw["version"],
            prefix=raw["prefix"],
            base_prefix=raw["base_prefix"],
            repo_root=raw["repo_root"],
            repo_venv_refused=raw["repo_venv_refused"],
            device=DeviceReceipt.from_dict(raw["device"]),
        )


@dataclass(frozen=True)
class ProducerRef:
    SCHEMA_VERSION: ClassVar[str] = "producer-ref/1"

    provider: str
    model: str
    mode: str

    def __post_init__(self) -> None:
        for name, value in (
            ("provider", self.provider),
            ("model", self.model),
            ("mode", self.mode),
        ):
            _nonempty(value, name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "provider": self.provider,
            "model": self.model,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ProducerRef":
        _check_version(raw, cls.SCHEMA_VERSION, "ProducerRef")
        _require_exact(raw, ("provider", "model", "mode"), "ProducerRef")
        return cls(provider=raw["provider"], model=raw["model"], mode=raw["mode"])


@dataclass(frozen=True)
class SourceRef:
    SCHEMA_VERSION: ClassVar[str] = "source-ref/1"

    source_id: str
    digest: str
    locator: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.source_id, "source_id")
        _nonempty(self.digest, "digest")
        if self.locator is not None:
            _nonempty(self.locator, "locator")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "source_id": self.source_id,
            "digest": self.digest,
            "locator": self.locator,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SourceRef":
        _check_version(raw, cls.SCHEMA_VERSION, "SourceRef")
        _require_exact(raw, ("source_id", "digest", "locator"), "SourceRef")
        return cls(source_id=raw["source_id"], digest=raw["digest"], locator=raw["locator"])


@dataclass(frozen=True)
class Residual:
    SCHEMA_VERSION: ClassVar[str] = "residual/1"

    status: ResidualStatus
    value: float | None
    threshold: float | None
    unit: str
    note: str

    def __post_init__(self) -> None:
        _nonempty(self.unit, "unit")
        _nonempty(self.note, "note")
        measured = self.status != ResidualStatus.UNKNOWN
        if measured != (self.value is not None and self.threshold is not None):
            raise StateTransitionRefused("residual measurement fields contradict status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "status": self.status.value,
            "value": self.value,
            "threshold": self.threshold,
            "unit": self.unit,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Residual":
        _check_version(raw, cls.SCHEMA_VERSION, "Residual")
        _require_exact(raw, ("status", "value", "threshold", "unit", "note"), "Residual")
        return cls(
            status=ResidualStatus(raw["status"]),
            value=raw["value"],
            threshold=raw["threshold"],
            unit=raw["unit"],
            note=raw["note"],
        )


@dataclass(frozen=True)
class BoundaryRef:
    SCHEMA_VERSION: ClassVar[str] = "boundary-ref/1"

    handle: str
    node_id: str
    assumption: str
    fibre: str

    def __post_init__(self) -> None:
        for name, value in (
            ("handle", self.handle),
            ("node_id", self.node_id),
            ("assumption", self.assumption),
            ("fibre", self.fibre),
        ):
            _nonempty(value, name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "handle": self.handle,
            "node_id": self.node_id,
            "assumption": self.assumption,
            "fibre": self.fibre,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "BoundaryRef":
        _check_version(raw, cls.SCHEMA_VERSION, "BoundaryRef")
        _require_exact(raw, ("handle", "node_id", "assumption", "fibre"), "BoundaryRef")
        return cls(
            handle=raw["handle"],
            node_id=raw["node_id"],
            assumption=raw["assumption"],
            fibre=raw["fibre"],
        )


@dataclass(frozen=True)
class GradeAxisContract:
    """A named, finite coarse-to-fine ordering that makes grade direction checkable."""

    SCHEMA_VERSION: ClassVar[str] = "grade-axis-contract/1"

    contract_id: str
    axis: str
    coarse_to_fine: tuple[str | int, ...]

    def __post_init__(self) -> None:
        _nonempty(self.contract_id, "contract_id")
        _nonempty(self.axis, "axis")
        if len(self.coarse_to_fine) < 2:
            raise StateTransitionRefused(
                "grade-axis contract requires at least two ordered coordinates"
            )
        for coordinate in self.coarse_to_fine:
            _coordinate(coordinate, "coarse_to_fine")
        if len(set(self.coarse_to_fine)) != len(self.coarse_to_fine):
            raise StateTransitionRefused("grade-axis coordinates must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "contract_id": self.contract_id,
            "axis": self.axis,
            "coarse_to_fine": list(self.coarse_to_fine),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GradeAxisContract":
        _check_version(raw, cls.SCHEMA_VERSION, "GradeAxisContract")
        _require_exact(
            raw,
            ("contract_id", "axis", "coarse_to_fine"),
            "GradeAxisContract",
        )
        return cls(
            contract_id=raw["contract_id"],
            axis=raw["axis"],
            coarse_to_fine=tuple(raw["coarse_to_fine"]),
        )


@dataclass(frozen=True)
class GradeAxis:
    SCHEMA_VERSION: ClassVar[str] = "grade-axis/1"

    contract_id: str
    axis: str
    from_coordinate: str | int
    to_coordinate: str | int

    def __post_init__(self) -> None:
        _nonempty(self.contract_id, "contract_id")
        _nonempty(self.axis, "axis")
        _coordinate(self.from_coordinate, "from_coordinate")
        _coordinate(self.to_coordinate, "to_coordinate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "contract_id": self.contract_id,
            "axis": self.axis,
            "from": self.from_coordinate,
            "to": self.to_coordinate,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GradeAxis":
        _check_version(raw, cls.SCHEMA_VERSION, "GradeAxis")
        _require_exact(raw, ("contract_id", "axis", "from", "to"), "GradeAxis")
        return cls(
            contract_id=raw["contract_id"],
            axis=raw["axis"],
            from_coordinate=raw["from"],
            to_coordinate=raw["to"],
        )


@dataclass(frozen=True)
class ConceptricObject:
    """One resolvable item in the conceptric, independent of its storage encoding.

    ``object_id`` is the stable address used by edges. ``content_handle`` is the immutable
    version/content digest at that address. Meaning remains fibre-local: contextual objects
    declare assumption and fibre together, while substrate objects (bytes and logical seats)
    may be global and acquire meaning through their edges.
    """

    SCHEMA_VERSION: ClassVar[str] = "conceptric-object/1"

    object_id: str
    kind: str
    content_handle: str
    assumption: str | None
    fibre: str | None
    grade_contract_id: str
    grade_coordinate: str | int
    provenance: tuple[SourceRef, ...]
    attributes: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name, value in (
            ("object_id", self.object_id),
            ("kind", self.kind),
            ("content_handle", self.content_handle),
            ("grade_contract_id", self.grade_contract_id),
        ):
            _nonempty(value, name)
        if (self.assumption is None) != (self.fibre is None):
            raise StateTransitionRefused("object assumption and fibre are declared together")
        if self.assumption is not None:
            _nonempty(self.assumption, "assumption")
            assert self.fibre is not None
            _nonempty(self.fibre, "fibre")
        _coordinate(self.grade_coordinate, "grade_coordinate")
        if not self.provenance:
            raise StateTransitionRefused("conceptric object requires provenance")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "object_id": self.object_id,
            "kind": self.kind,
            "content_handle": self.content_handle,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "grade_contract_id": self.grade_contract_id,
            "grade_coordinate": self.grade_coordinate,
            "provenance": [item.to_dict() for item in self.provenance],
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ConceptricObject":
        _check_version(raw, cls.SCHEMA_VERSION, "ConceptricObject")
        _require_exact(
            raw,
            (
                "object_id",
                "kind",
                "content_handle",
                "assumption",
                "fibre",
                "grade_contract_id",
                "grade_coordinate",
                "provenance",
                "attributes",
            ),
            "ConceptricObject",
        )
        return cls(
            object_id=raw["object_id"],
            kind=raw["kind"],
            content_handle=raw["content_handle"],
            assumption=raw["assumption"],
            fibre=raw["fibre"],
            grade_contract_id=raw["grade_contract_id"],
            grade_coordinate=raw["grade_coordinate"],
            provenance=tuple(SourceRef.from_dict(item) for item in raw["provenance"]),
            attributes=dict(raw["attributes"]),
        )


@dataclass(frozen=True)
class ConceptricEdge:
    """A first-class, graded and fibre-aware edge whose endpoints must resolve."""

    SCHEMA_VERSION: ClassVar[str] = "conceptric-edge/1"

    edge_id: str
    relation: str
    source_object_id: str
    target_object_id: str
    direction: MoveDirection
    assumption: str | None
    fibre: str | None
    operator: str
    grade_axis: GradeAxis
    provenance: tuple[SourceRef, ...]
    residual: Residual
    generation_handle: str
    transport_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("edge_id", self.edge_id),
            ("relation", self.relation),
            ("source_object_id", self.source_object_id),
            ("target_object_id", self.target_object_id),
            ("operator", self.operator),
            ("generation_handle", self.generation_handle),
        ):
            _nonempty(value, name)
        if (self.assumption is None) != (self.fibre is None):
            raise StateTransitionRefused("edge assumption and fibre are declared together")
        if self.assumption is not None:
            _nonempty(self.assumption, "assumption")
            assert self.fibre is not None
            _nonempty(self.fibre, "fibre")
        if not self.provenance:
            raise StateTransitionRefused("conceptric edge requires provenance")
        if self.direction == MoveDirection.TRANSPORT and not self.transport_id:
            raise StateTransitionRefused("transport edge requires a transport id")
        if self.direction != MoveDirection.TRANSPORT and self.transport_id is not None:
            raise StateTransitionRefused("only transport edge may cite transport")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "edge_id": self.edge_id,
            "relation": self.relation,
            "source_object_id": self.source_object_id,
            "target_object_id": self.target_object_id,
            "direction": self.direction.value,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "operator": self.operator,
            "grade_axis": self.grade_axis.to_dict(),
            "provenance": [item.to_dict() for item in self.provenance],
            "residual": self.residual.to_dict(),
            "generation_handle": self.generation_handle,
            "transport_id": self.transport_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ConceptricEdge":
        _check_version(raw, cls.SCHEMA_VERSION, "ConceptricEdge")
        _require_exact(
            raw,
            (
                "edge_id",
                "relation",
                "source_object_id",
                "target_object_id",
                "direction",
                "assumption",
                "fibre",
                "operator",
                "grade_axis",
                "provenance",
                "residual",
                "generation_handle",
                "transport_id",
            ),
            "ConceptricEdge",
        )
        return cls(
            edge_id=raw["edge_id"],
            relation=raw["relation"],
            source_object_id=raw["source_object_id"],
            target_object_id=raw["target_object_id"],
            direction=MoveDirection(raw["direction"]),
            assumption=raw["assumption"],
            fibre=raw["fibre"],
            operator=raw["operator"],
            grade_axis=GradeAxis.from_dict(raw["grade_axis"]),
            provenance=tuple(SourceRef.from_dict(item) for item in raw["provenance"]),
            residual=Residual.from_dict(raw["residual"]),
            generation_handle=raw["generation_handle"],
            transport_id=raw["transport_id"],
        )


@dataclass(frozen=True)
class TransportReceipt:
    SCHEMA_VERSION: ClassVar[str] = "transport-receipt/1"

    transport_id: str
    from_assumption: str
    to_assumption: str
    from_fibre: str
    to_fibre: str
    operator: str
    loss_or_obstruction: str
    declared: bool = True

    def __post_init__(self) -> None:
        for name, value in (
            ("transport_id", self.transport_id),
            ("from_assumption", self.from_assumption),
            ("to_assumption", self.to_assumption),
            ("from_fibre", self.from_fibre),
            ("to_fibre", self.to_fibre),
            ("operator", self.operator),
            ("loss_or_obstruction", self.loss_or_obstruction),
        ):
            _nonempty(value, name)
        if not self.declared:
            raise StateTransitionRefused("undeclared fibre transport cannot be banked")
        if self.from_assumption == self.to_assumption and self.from_fibre == self.to_fibre:
            raise StateTransitionRefused("transport must change assumption or fibre")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "id": self.transport_id,
            "from_assumption": self.from_assumption,
            "to_assumption": self.to_assumption,
            "from_fibre": self.from_fibre,
            "to_fibre": self.to_fibre,
            "operator": self.operator,
            "loss_or_obstruction": self.loss_or_obstruction,
            "declared": self.declared,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TransportReceipt":
        _check_version(raw, cls.SCHEMA_VERSION, "TransportReceipt")
        keys = (
            "id",
            "from_assumption",
            "to_assumption",
            "from_fibre",
            "to_fibre",
            "operator",
            "loss_or_obstruction",
            "declared",
        )
        _require_exact(raw, keys, "TransportReceipt")
        return cls(
            transport_id=raw["id"],
            from_assumption=raw["from_assumption"],
            to_assumption=raw["to_assumption"],
            from_fibre=raw["from_fibre"],
            to_fibre=raw["to_fibre"],
            operator=raw["operator"],
            loss_or_obstruction=raw["loss_or_obstruction"],
            declared=raw["declared"],
        )


@dataclass(frozen=True)
class Movement:
    SCHEMA_VERSION: ClassVar[str] = "movement/1"

    movement_id: str
    direction: MoveDirection
    goal: str
    operator: str
    source: BoundaryRef
    target: BoundaryRef
    grade_axis: GradeAxis
    provenance: tuple[SourceRef, ...]
    residual: Residual
    sufficient: bool
    continuation: str | None
    transport_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("movement_id", self.movement_id),
            ("goal", self.goal),
            ("operator", self.operator),
        ):
            _nonempty(value, name)
        if not self.provenance:
            raise StateTransitionRefused("every movement must carry provenance")
        crosses = (
            self.source.assumption != self.target.assumption
            or self.source.fibre != self.target.fibre
        )
        if crosses and self.direction != MoveDirection.TRANSPORT:
            raise StateTransitionRefused("cross-fibre movement requires explicit transport")
        if self.direction == MoveDirection.TRANSPORT and not self.transport_id:
            raise StateTransitionRefused("transport movement requires a transport id")
        if self.direction != MoveDirection.TRANSPORT and self.transport_id is not None:
            raise StateTransitionRefused("only transport movement may cite transport")
        if self.direction == MoveDirection.CONJUGATE and self.source.node_id != self.target.node_id:
            raise StateTransitionRefused("conjugate movement must preserve node identity")
        if self.sufficient and self.residual.status != ResidualStatus.WITHIN_BOUND:
            raise StateTransitionRefused(
                "movement may claim sufficiency only over a measured within-bound residual"
            )
        if not self.sufficient and not self.continuation:
            raise StateTransitionRefused("insufficient movement must name its continuation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "id": self.movement_id,
            "direction": self.direction.value,
            "goal": self.goal,
            "operator": self.operator,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "grade_axis": self.grade_axis.to_dict(),
            "provenance": [item.to_dict() for item in self.provenance],
            "residual": self.residual.to_dict(),
            "sufficient": self.sufficient,
            "continuation": self.continuation,
            "transport_id": self.transport_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Movement":
        _check_version(raw, cls.SCHEMA_VERSION, "Movement")
        keys = (
            "id",
            "direction",
            "goal",
            "operator",
            "source",
            "target",
            "grade_axis",
            "provenance",
            "residual",
            "sufficient",
            "continuation",
            "transport_id",
        )
        _require_exact(raw, keys, "Movement")
        return cls(
            movement_id=raw["id"],
            direction=MoveDirection(raw["direction"]),
            goal=raw["goal"],
            operator=raw["operator"],
            source=BoundaryRef.from_dict(raw["source"]),
            target=BoundaryRef.from_dict(raw["target"]),
            grade_axis=GradeAxis.from_dict(raw["grade_axis"]),
            provenance=tuple(SourceRef.from_dict(item) for item in raw["provenance"]),
            residual=Residual.from_dict(raw["residual"]),
            sufficient=raw["sufficient"],
            continuation=raw["continuation"],
            transport_id=raw["transport_id"],
        )


@dataclass(frozen=True)
class JoinReceipt:
    SCHEMA_VERSION: ClassVar[str] = "join-receipt/2"
    LEGACY_SCHEMA_VERSION: ClassVar[str] = "join-receipt/1"

    join_id: str
    node_id: str
    assumption: str
    fibre: str
    operator: str
    semantic_handle: str
    spectral_handle: str
    provenance: tuple[SourceRef, ...]
    residual: Residual
    semantic_object_id: str | None = None
    spectral_object_id: str | None = None
    up_act_handle: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("join_id", self.join_id),
            ("node_id", self.node_id),
            ("assumption", self.assumption),
            ("fibre", self.fibre),
            ("operator", self.operator),
            ("semantic_handle", self.semantic_handle),
            ("spectral_handle", self.spectral_handle),
        ):
            _nonempty(value, name)
        if not self.provenance:
            raise StateTransitionRefused("join requires source-bearing provenance")
        strict_refs = (
            self.semantic_object_id,
            self.spectral_object_id,
            self.up_act_handle,
        )
        if any(value is not None for value in strict_refs):
            if not all(isinstance(value, str) and value.strip() for value in strict_refs):
                raise StateTransitionRefused(
                    "strict join must bind both resolved face objects and one UP act"
                )
            if self.join_id != derived_join_id(
                self.node_id,
                self.assumption,
                self.fibre,
                str(self.semantic_object_id),
                str(self.spectral_object_id),
                str(self.up_act_handle),
            ):
                raise StateTransitionRefused(
                    "strict join id is not derived from its exact UP faces"
                )

    @property
    def strict(self) -> bool:
        return self.up_act_handle is not None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": (self.SCHEMA_VERSION if self.strict else self.LEGACY_SCHEMA_VERSION),
            "id": self.join_id,
            "node_id": self.node_id,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "operator": self.operator,
            "semantic_handle": self.semantic_handle,
            "spectral_handle": self.spectral_handle,
            "provenance": [item.to_dict() for item in self.provenance],
            "residual": self.residual.to_dict(),
        }
        if self.strict:
            result.update(
                {
                    "semantic_object_id": self.semantic_object_id,
                    "spectral_object_id": self.spectral_object_id,
                    "up_act_handle": self.up_act_handle,
                }
            )
        return result

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "JoinReceipt":
        version = raw.get("schema_version")
        if version not in {cls.LEGACY_SCHEMA_VERSION, cls.SCHEMA_VERSION}:
            raise SchemaVersionMismatch(
                "JoinReceipt carries an unknown schema version",
                expected=cls.SCHEMA_VERSION,
                got=version,
            )
        keys = [
            "id",
            "node_id",
            "assumption",
            "fibre",
            "operator",
            "semantic_handle",
            "spectral_handle",
            "provenance",
            "residual",
        ]
        if version == cls.SCHEMA_VERSION:
            keys.extend(("semantic_object_id", "spectral_object_id", "up_act_handle"))
        _require_exact(raw, tuple(keys), "JoinReceipt")
        return cls(
            join_id=raw["id"],
            node_id=raw["node_id"],
            assumption=raw["assumption"],
            fibre=raw["fibre"],
            operator=raw["operator"],
            semantic_handle=raw["semantic_handle"],
            spectral_handle=raw["spectral_handle"],
            provenance=tuple(SourceRef.from_dict(item) for item in raw["provenance"]),
            residual=Residual.from_dict(raw["residual"]),
            semantic_object_id=raw.get("semantic_object_id"),
            spectral_object_id=raw.get("spectral_object_id"),
            up_act_handle=raw.get("up_act_handle"),
        )


def derived_join_id(
    node_id: str,
    assumption: str,
    fibre: str,
    semantic_object_id: str,
    spectral_object_id: str,
    up_act_handle: str,
) -> str:
    """Content-address one strict conjugate join over an already-banked UP act."""

    return chash(
        {
            "node_id": node_id,
            "assumption": assumption,
            "fibre": fibre,
            "semantic_object_id": semantic_object_id,
            "spectral_object_id": spectral_object_id,
            "up_act_handle": up_act_handle,
        }
    )


@dataclass(frozen=True)
class LifecycleTransition:
    SCHEMA_VERSION: ClassVar[str] = "lifecycle-transition/1"

    action: LifecycleAction
    from_phase: LifecyclePhase
    to_phase: LifecyclePhase
    receipt_id: str

    def __post_init__(self) -> None:
        _nonempty(self.receipt_id, "receipt_id")
        expected = {
            LifecycleAction.WAKE: (LifecyclePhase.SLEEPING, LifecyclePhase.AWAKE),
            LifecycleAction.COLD_WAKE: (LifecyclePhase.SLEEPING, LifecyclePhase.AWAKE),
            LifecycleAction.SEW_UP: (LifecyclePhase.AWAKE, LifecyclePhase.SEWING_UP),
            LifecycleAction.SLEEP: (LifecyclePhase.SEWING_UP, LifecyclePhase.SLEEPING),
        }[self.action]
        if (self.from_phase, self.to_phase) != expected:
            raise StateTransitionRefused(
                "lifecycle action carries impossible endpoints", action=self.action.value
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "action": self.action.value,
            "from": self.from_phase.value,
            "to": self.to_phase.value,
            "receipt_id": self.receipt_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "LifecycleTransition":
        _check_version(raw, cls.SCHEMA_VERSION, "LifecycleTransition")
        _require_exact(raw, ("action", "from", "to", "receipt_id"), "LifecycleTransition")
        return cls(
            action=LifecycleAction(raw["action"]),
            from_phase=LifecyclePhase(raw["from"]),
            to_phase=LifecyclePhase(raw["to"]),
            receipt_id=raw["receipt_id"],
        )


@dataclass(frozen=True)
class SeatTransition:
    SCHEMA_VERSION: ClassVar[str] = "seat-transition/1"

    seat_id: str
    role: SeatRole
    action: SeatAction
    from_status: SeatStatus | None
    to_status: SeatStatus
    charter_ref: str
    holder_ref: str

    def __post_init__(self) -> None:
        _nonempty(self.seat_id, "seat_id")
        _nonempty(self.charter_ref, "charter_ref")
        _nonempty(self.holder_ref, "holder_ref")
        allowed = {
            SeatAction.FOUND: (None, SeatStatus.ACTIVE),
            SeatAction.RELAY: (SeatStatus.ACTIVE, SeatStatus.RELAYING),
            SeatAction.ACTIVATE: (SeatStatus.RELAYING, SeatStatus.ACTIVE),
        }
        if self.action == SeatAction.CLOSE:
            if self.from_status not in {SeatStatus.ACTIVE, SeatStatus.RELAYING}:
                raise StateTransitionRefused("only a live seat can close")
            if self.to_status != SeatStatus.CLOSED:
                raise StateTransitionRefused("close must enter the closed state")
        elif (self.from_status, self.to_status) != allowed[self.action]:
            raise StateTransitionRefused("seat action carries impossible endpoints")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "seat_id": self.seat_id,
            "role": self.role.value,
            "action": self.action.value,
            "from": None if self.from_status is None else self.from_status.value,
            "to": self.to_status.value,
            "charter_ref": self.charter_ref,
            "holder_ref": self.holder_ref,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SeatTransition":
        _check_version(raw, cls.SCHEMA_VERSION, "SeatTransition")
        keys = ("seat_id", "role", "action", "from", "to", "charter_ref", "holder_ref")
        _require_exact(raw, keys, "SeatTransition")
        return cls(
            seat_id=raw["seat_id"],
            role=SeatRole(raw["role"]),
            action=SeatAction(raw["action"]),
            from_status=None if raw["from"] is None else SeatStatus(raw["from"]),
            to_status=SeatStatus(raw["to"]),
            charter_ref=raw["charter_ref"],
            holder_ref=raw["holder_ref"],
        )


@dataclass(frozen=True)
class SeatJoinReceipt:
    """One provider session's proved, observational binding to a logical chair.

    Registration and occupancy are deliberately separate.  The registered role and
    holder are copied from the materialized seat at the instant of the join so a
    claimed function or provider-session mismatch remains visible instead of being
    silently normalised.  This receipt does not itself authorize message routing.
    """

    SCHEMA_VERSION: ClassVar[str] = "seat-join-receipt/2"
    LEGACY_V1_SCHEMA_VERSION: ClassVar[str] = "seat-join-receipt/1"

    seat_id: str
    holder_ref: str
    function: SeatRole
    registered_role: SeatRole
    registered_holder_ref: str
    mail_state: str
    information_proof_handle: str
    information_cursor: int
    delivered_message_ids: tuple[str, ...]
    reconstruction_event_ids: tuple[str, ...]
    defects: tuple[str, ...] = ()
    provider_identity_generation: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("seat_id", self.seat_id),
            ("holder_ref", self.holder_ref),
            ("registered_holder_ref", self.registered_holder_ref),
            ("information_proof_handle", self.information_proof_handle),
        ):
            _nonempty(value, name)
        if self.mail_state != "MAIL_READY":
            raise StateTransitionRefused("a seat join requires a MAIL_READY information proof")
        if (
            isinstance(self.information_cursor, bool)
            or not isinstance(self.information_cursor, int)
            or self.information_cursor < 0
        ):
            raise StateTransitionRefused("seat join information cursor must be non-negative")
        for field, values in (
            ("delivered_message_ids", self.delivered_message_ids),
            ("reconstruction_event_ids", self.reconstruction_event_ids),
            ("defects", self.defects),
        ):
            if len(set(values)) != len(values):
                raise StateTransitionRefused(
                    "seat join evidence cannot contain duplicates", field=field
                )
            for value in values:
                _nonempty(value, field)
        if self.provider_identity_generation is not None:
            _nonempty(
                self.provider_identity_generation,
                "provider_identity_generation",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "seat_id": self.seat_id,
            "holder_ref": self.holder_ref,
            "function": self.function.value,
            "registered_role": self.registered_role.value,
            "registered_holder_ref": self.registered_holder_ref,
            "mail_state": self.mail_state,
            "information_proof_handle": self.information_proof_handle,
            "information_cursor": self.information_cursor,
            "delivered_message_ids": list(self.delivered_message_ids),
            "reconstruction_event_ids": list(self.reconstruction_event_ids),
            "defects": list(self.defects),
            "provider_identity_generation": self.provider_identity_generation,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SeatJoinReceipt":
        keys = (
            "seat_id",
            "holder_ref",
            "function",
            "registered_role",
            "registered_holder_ref",
            "mail_state",
            "information_proof_handle",
            "information_cursor",
            "delivered_message_ids",
            "reconstruction_event_ids",
            "defects",
            "provider_identity_generation",
        )
        version = raw.get("schema_version")
        if version == cls.SCHEMA_VERSION:
            _require_exact(raw, keys, "SeatJoinReceipt")
        elif version == cls.LEGACY_V1_SCHEMA_VERSION:
            _require_exact(raw, keys[:-1], "SeatJoinReceipt legacy v1")
        else:
            raise StateTransitionRefused(
                "unsupported schema version",
                expected=cls.SCHEMA_VERSION,
                got=version,
                object="SeatJoinReceipt",
            )
        return cls(
            seat_id=raw["seat_id"],
            holder_ref=raw["holder_ref"],
            function=SeatRole(raw["function"]),
            registered_role=SeatRole(raw["registered_role"]),
            registered_holder_ref=raw["registered_holder_ref"],
            mail_state=raw["mail_state"],
            information_proof_handle=raw["information_proof_handle"],
            information_cursor=raw["information_cursor"],
            delivered_message_ids=tuple(raw["delivered_message_ids"]),
            reconstruction_event_ids=tuple(raw["reconstruction_event_ids"]),
            defects=tuple(raw["defects"]),
            provider_identity_generation=raw.get("provider_identity_generation"),
        )


@dataclass(frozen=True)
class SeatOccupancyBinding:
    """A registered logical chair authorizes one provider-session occupant.

    A ``SeatJoinReceipt`` proves that a task reconstructed its startup mail.  It is
    deliberately observational.  This second receipt is the authority-bearing
    conjugate: the logical principal remains the registered holder, while the exact
    provider task/session is derived from the watcher-backed startup proof.  The
    binding is current only while it remains the latest binding for the latest join;
    a later join supersedes it mechanically.
    """

    SCHEMA_VERSION: ClassVar[str] = "seat-occupancy-binding/4"
    LEGACY_V3_SCHEMA_VERSION: ClassVar[str] = "seat-occupancy-binding/3"
    LEGACY_V2_SCHEMA_VERSION: ClassVar[str] = "seat-occupancy-binding/2"
    LEGACY_V1_SCHEMA_VERSION: ClassVar[str] = "seat-occupancy-binding/1"

    seat_id: str
    registered_seat_event_id: str
    join_event_id: str
    registered_principal_ref: str
    provider_session_ref: str
    function: SeatRole
    provider_identity_proof_handle: str
    provider_identity_generation: str | None = None
    predecessor_binding_event_id: str | None = None
    retired_provider_identity_generation: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("seat_id", self.seat_id),
            ("registered_seat_event_id", self.registered_seat_event_id),
            ("join_event_id", self.join_event_id),
            ("registered_principal_ref", self.registered_principal_ref),
            ("provider_session_ref", self.provider_session_ref),
            ("provider_identity_proof_handle", self.provider_identity_proof_handle),
        ):
            _nonempty(value, name)
        if self.provider_identity_generation is not None:
            _nonempty(self.provider_identity_generation, "provider_identity_generation")
        renewal_fields = (
            self.predecessor_binding_event_id,
            self.retired_provider_identity_generation,
        )
        if any(value is not None for value in renewal_fields) and not all(
            value is not None for value in renewal_fields
        ):
            raise StateTransitionRefused(
                "seat binding renewal must name both predecessor binding and retired generation"
            )
        if self.predecessor_binding_event_id is not None:
            _nonempty(self.predecessor_binding_event_id, "predecessor_binding_event_id")
            assert self.retired_provider_identity_generation is not None
            _nonempty(
                self.retired_provider_identity_generation,
                "retired_provider_identity_generation",
            )
            if self.provider_identity_generation is None:
                raise StateTransitionRefused(
                    "seat binding renewal requires the successor provider generation"
                )
            if self.provider_identity_generation == self.retired_provider_identity_generation:
                raise StateTransitionRefused(
                    "seat binding renewal must advance the provider generation"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "seat_id": self.seat_id,
            "registered_seat_event_id": self.registered_seat_event_id,
            "join_event_id": self.join_event_id,
            "registered_principal_ref": self.registered_principal_ref,
            "provider_session_ref": self.provider_session_ref,
            "function": self.function.value,
            "provider_identity_proof_handle": self.provider_identity_proof_handle,
            "provider_identity_generation": self.provider_identity_generation,
            "predecessor_binding_event_id": self.predecessor_binding_event_id,
            "retired_provider_identity_generation": (self.retired_provider_identity_generation),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SeatOccupancyBinding":
        version = raw.get("schema_version")
        keys = (
            "seat_id",
            "registered_seat_event_id",
            "join_event_id",
            "registered_principal_ref",
            "provider_session_ref",
            "function",
            "provider_identity_proof_handle",
            "provider_identity_generation",
            "predecessor_binding_event_id",
            "retired_provider_identity_generation",
        )
        if version in {cls.SCHEMA_VERSION, cls.LEGACY_V3_SCHEMA_VERSION}:
            _require_exact(raw, keys, "SeatOccupancyBinding")
        elif version == cls.LEGACY_V2_SCHEMA_VERSION:
            _require_exact(raw, keys[:-3], "SeatOccupancyBinding legacy v2")
        elif version == cls.LEGACY_V1_SCHEMA_VERSION:
            _require_exact(
                raw,
                (
                    "binding_id",
                    *keys[:-4],
                    "provider",
                    "provider_identity_kind",
                    "provider_identity_proof_handle",
                    "validity",
                ),
                "SeatOccupancyBinding legacy v1",
            )
        else:
            raise StateTransitionRefused(
                "unsupported schema version",
                expected=cls.SCHEMA_VERSION,
                got=version,
                object="SeatOccupancyBinding",
            )
        return cls(
            seat_id=raw["seat_id"],
            registered_seat_event_id=raw["registered_seat_event_id"],
            join_event_id=raw["join_event_id"],
            registered_principal_ref=raw["registered_principal_ref"],
            provider_session_ref=raw["provider_session_ref"],
            function=SeatRole(raw["function"]),
            provider_identity_proof_handle=raw["provider_identity_proof_handle"],
            provider_identity_generation=raw.get("provider_identity_generation"),
            predecessor_binding_event_id=raw.get("predecessor_binding_event_id"),
            retired_provider_identity_generation=raw.get("retired_provider_identity_generation"),
        )


@dataclass(frozen=True)
class BootstrapCrutch:
    """The gap a bootstrap lease snapshot covers and the trigger that kills it."""

    SCHEMA_VERSION: ClassVar[str] = "bootstrap-crutch/1"
    RETIREMENT_PREFIX: ClassVar[str] = "native-successful-checkins>="

    crutch_id: str
    what: str
    why_now: str
    must_become: str
    retirement_trigger: str
    owner: str

    def __post_init__(self) -> None:
        for name, value in (
            ("crutch_id", self.crutch_id),
            ("what", self.what),
            ("why_now", self.why_now),
            ("must_become", self.must_become),
            ("retirement_trigger", self.retirement_trigger),
            ("owner", self.owner),
        ):
            _nonempty(value, name)
        threshold = self.retirement_trigger.removeprefix(self.RETIREMENT_PREFIX)
        if (
            not self.retirement_trigger.startswith(self.RETIREMENT_PREFIX)
            or not threshold.isdigit()
            or int(threshold) < 1
        ):
            raise StateTransitionRefused(
                "bootstrap crutch retirement trigger must be mechanically evaluable",
                expected=f"{self.RETIREMENT_PREFIX}<positive integer>",
            )

    @property
    def required_native_checkins(self) -> int:
        return int(self.retirement_trigger.removeprefix(self.RETIREMENT_PREFIX))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "crutch_id": self.crutch_id,
            "what": self.what,
            "why_now": self.why_now,
            "must_become": self.must_become,
            "retirement_trigger": self.retirement_trigger,
            "owner": self.owner,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "BootstrapCrutch":
        _check_version(raw, cls.SCHEMA_VERSION, "BootstrapCrutch")
        keys = (
            "crutch_id",
            "what",
            "why_now",
            "must_become",
            "retirement_trigger",
            "owner",
        )
        _require_exact(raw, keys, "BootstrapCrutch")
        return cls(**{key: raw[key] for key in keys})


@dataclass(frozen=True)
class RegionCheckout:
    """One exact holder's time-bounded write authority over repository path prefixes."""

    SCHEMA_VERSION: ClassVar[str] = "region-checkout/1"

    lease_id: str
    act_id: str
    seat_id: str
    holder_ref: str
    function: SeatRole
    regions: tuple[str, ...]
    base_git_head: str
    expires_at: str
    declaration_kind: LeaseDeclarationKind
    declaration_ref: str
    preexisting_dirty_paths: tuple[str, ...] = ()
    bootstrap_crutch: BootstrapCrutch | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("lease_id", self.lease_id),
            ("act_id", self.act_id),
            ("seat_id", self.seat_id),
            ("holder_ref", self.holder_ref),
            ("base_git_head", self.base_git_head),
            ("declaration_ref", self.declaration_ref),
        ):
            _nonempty(value, name)
        if not self.regions or len(set(self.regions)) != len(self.regions):
            raise StateTransitionRefused(
                "region checkout requires a non-empty duplicate-free scope"
            )
        for region in self.regions:
            _region_path(region)
        if len(set(self.preexisting_dirty_paths)) != len(self.preexisting_dirty_paths):
            raise StateTransitionRefused(
                "bootstrap checkout dirty-path snapshot cannot contain duplicates"
            )
        for path in self.preexisting_dirty_paths:
            _region_path(path, "preexisting_dirty_paths")
            if not any(path == region or path.startswith(region + "/") for region in self.regions):
                raise StateTransitionRefused(
                    "bootstrap dirty-path snapshot escapes its declared regions", path=path
                )
        _timestamp(self.expires_at, "expires_at")
        if self.declaration_kind == LeaseDeclarationKind.JOURNAL_BOOTSTRAP:
            if self.bootstrap_crutch is None:
                raise StateTransitionRefused(
                    "journal-bootstrap checkout must declare the crutch at introduction"
                )
        elif self.bootstrap_crutch is not None:
            raise StateTransitionRefused("native checkout cannot smuggle a bootstrap crutch")
        elif self.preexisting_dirty_paths:
            raise StateTransitionRefused("native checkout cannot launder pre-existing dirty paths")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "lease_id": self.lease_id,
            "act_id": self.act_id,
            "seat_id": self.seat_id,
            "holder_ref": self.holder_ref,
            "function": self.function.value,
            "regions": list(self.regions),
            "base_git_head": self.base_git_head,
            "expires_at": self.expires_at,
            "declaration_kind": self.declaration_kind.value,
            "declaration_ref": self.declaration_ref,
            "preexisting_dirty_paths": list(self.preexisting_dirty_paths),
            "bootstrap_crutch": (
                None if self.bootstrap_crutch is None else self.bootstrap_crutch.to_dict()
            ),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RegionCheckout":
        _check_version(raw, cls.SCHEMA_VERSION, "RegionCheckout")
        keys = (
            "lease_id",
            "act_id",
            "seat_id",
            "holder_ref",
            "function",
            "regions",
            "base_git_head",
            "expires_at",
            "declaration_kind",
            "declaration_ref",
            "preexisting_dirty_paths",
            "bootstrap_crutch",
        )
        _require_exact(raw, keys, "RegionCheckout")
        crutch = raw["bootstrap_crutch"]
        return cls(
            lease_id=raw["lease_id"],
            act_id=raw["act_id"],
            seat_id=raw["seat_id"],
            holder_ref=raw["holder_ref"],
            function=SeatRole(raw["function"]),
            regions=tuple(raw["regions"]),
            base_git_head=raw["base_git_head"],
            expires_at=raw["expires_at"],
            declaration_kind=LeaseDeclarationKind(raw["declaration_kind"]),
            declaration_ref=raw["declaration_ref"],
            preexisting_dirty_paths=tuple(raw["preexisting_dirty_paths"]),
            bootstrap_crutch=(None if crutch is None else BootstrapCrutch.from_dict(crutch)),
        )


@dataclass(frozen=True)
class RegionCheckin:
    """The exact Git/worktree evidence that closes one region checkout."""

    SCHEMA_VERSION: ClassVar[str] = "region-checkin/1"

    lease_id: str
    seat_id: str
    holder_ref: str
    function: SeatRole
    outcome: LeaseCheckinOutcome
    base_git_head: str
    result_git_head: str
    committed_paths: tuple[str, ...]
    dirty_paths: tuple[str, ...]
    evidence: Mapping[str, str]

    def __post_init__(self) -> None:
        for name, value in (
            ("lease_id", self.lease_id),
            ("seat_id", self.seat_id),
            ("holder_ref", self.holder_ref),
            ("base_git_head", self.base_git_head),
            ("result_git_head", self.result_git_head),
        ):
            _nonempty(value, name)
        for field, paths in (
            ("committed_paths", self.committed_paths),
            ("dirty_paths", self.dirty_paths),
        ):
            if len(set(paths)) != len(paths):
                raise StateTransitionRefused(
                    "region checkin path evidence cannot contain duplicates", field=field
                )
            for path in paths:
                _region_path(path, field)
        if not self.evidence or any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, str)
            or not value.strip()
            for key, value in self.evidence.items()
        ):
            raise StateTransitionRefused("region checkin must carry named exact evidence")
        if self.outcome == LeaseCheckinOutcome.COMMITTED:
            if not self.committed_paths or self.base_git_head == self.result_git_head:
                raise StateTransitionRefused(
                    "committed checkin requires changed Git head and committed paths"
                )
            if self.dirty_paths:
                raise StateTransitionRefused(
                    "committed checkin cannot leave dirty paths in its region"
                )
        if self.outcome == LeaseCheckinOutcome.NOOP:
            if self.committed_paths or self.dirty_paths:
                raise StateTransitionRefused(
                    "noop checkin must leave its leased regions uncommitted and clean"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "lease_id": self.lease_id,
            "seat_id": self.seat_id,
            "holder_ref": self.holder_ref,
            "function": self.function.value,
            "outcome": self.outcome.value,
            "base_git_head": self.base_git_head,
            "result_git_head": self.result_git_head,
            "committed_paths": list(self.committed_paths),
            "dirty_paths": list(self.dirty_paths),
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RegionCheckin":
        _check_version(raw, cls.SCHEMA_VERSION, "RegionCheckin")
        keys = (
            "lease_id",
            "seat_id",
            "holder_ref",
            "function",
            "outcome",
            "base_git_head",
            "result_git_head",
            "committed_paths",
            "dirty_paths",
            "evidence",
        )
        _require_exact(raw, keys, "RegionCheckin")
        return cls(
            lease_id=raw["lease_id"],
            seat_id=raw["seat_id"],
            holder_ref=raw["holder_ref"],
            function=SeatRole(raw["function"]),
            outcome=LeaseCheckinOutcome(raw["outcome"]),
            base_git_head=raw["base_git_head"],
            result_git_head=raw["result_git_head"],
            committed_paths=tuple(raw["committed_paths"]),
            dirty_paths=tuple(raw["dirty_paths"]),
            evidence=dict(raw["evidence"]),
        )


def _publication_handle(value: str, field: str) -> None:
    _nonempty(value, field)
    if not value.startswith("sha256:") or len(value) != 71:
        raise StateTransitionRefused(
            "publication custody field must be an exact sha256 handle", field=field
        )


def _publication_oid(value: str, field: str) -> None:
    _nonempty(value, field)
    if len(value) not in {40, 64} or any(character not in "0123456789abcdef" for character in value):
        raise StateTransitionRefused(
            "publication Git object must be a full lowercase object id", field=field
        )


def region_publication_affected_frontier_root(
    affected_roots: Mapping[str, str],
) -> str:
    """Return the canonical frontier root for one exact typed affected-root map."""

    return chash(
        {
            "schema_version": "laplace.region-publication-affected-frontier/1",
            "affected_roots": dict(sorted(affected_roots.items())),
        }
    )


def region_forward_closure_finalized_projection(
    *,
    lease_id: str,
    seat_id: str,
    holder_ref: str,
    function: SeatRole,
    base_ref: str,
    expected_old: str,
    result_git_head: str,
    candidate_tree: str,
    patch_handle: str,
    custody_handle: str,
    affected_frontier_root: str,
) -> dict[str, str]:
    """Build the one non-recursive payload projection reserved before finalization."""

    return {
        "schema_version": RegionForwardClosure.PAYLOAD_SCHEMA_VERSION,
        "lease_id": lease_id,
        "seat_id": seat_id,
        "holder_ref": holder_ref,
        "function": function.value,
        "base_ref": base_ref,
        "expected_old": expected_old,
        "result_git_head": result_git_head,
        "candidate_tree": candidate_tree,
        "patch_handle": patch_handle,
        "custody_handle": custody_handle,
        "affected_frontier_root": affected_frontier_root,
    }


@dataclass(frozen=True)
class RegionForwardClosure:
    """A content-addressed reservation for one exact publication final transition."""

    SCHEMA_VERSION: ClassVar[str] = "laplace.region-forward-closure/1"
    PAYLOAD_SCHEMA_VERSION: ClassVar[str] = (
        "laplace.region-forward-closure-finalized-projection/1"
    )
    PREDICATE_SCHEMA_VERSION: ClassVar[str] = "laplace.region-forward-closure-predicate/1"
    ALLOWED_TRANSITION_KIND: ClassVar[str] = EventKind.REGION_PUBLICATION_FINALIZED.value
    RELATED_HEAD_PREDICATE: ClassVar[str] = "AUTHORIZED-EVENT-IS-CURRENT-HEAD"
    SUCCESSOR_PREDICATE: ClassVar[str] = (
        "FINALIZED-CANDIDATE-IS-HEAD-AND-AFFECTED-ROOTS-MATCH"
    )
    predecessor_event_id: str
    predecessor_frontier_root: str
    finalized_projection_digest: str
    affected_roots: Mapping[str, str]
    expires_at: str
    forward_closure_root: str

    def __post_init__(self) -> None:
        _publication_handle(self.predecessor_event_id, "predecessor_event_id")
        _publication_handle(self.predecessor_frontier_root, "predecessor_frontier_root")
        _publication_handle(self.finalized_projection_digest, "finalized_projection_digest")
        roots = dict(self.affected_roots)
        if not roots:
            raise StateTransitionRefused("forward closure requires affected typed roots")
        for root_type, root in roots.items():
            if (
                not root_type
                or root_type != root_type.casefold()
                or any(
                    character not in "abcdefghijklmnopqrstuvwxyz0123456789._:-"
                    for character in root_type
                )
            ):
                raise StateTransitionRefused(
                    "publication affected root type is not canonical", root_type=root_type
                )
            _publication_handle(root, "affected_root")
        expected_frontier = region_publication_affected_frontier_root(roots)
        if self.predecessor_frontier_root != expected_frontier:
            raise StateTransitionRefused(
                "forward closure affected-root frontier does not verify"
            )
        _timestamp(self.expires_at, "expires_at")
        _publication_handle(self.forward_closure_root, "forward_closure_root")
        if self.forward_closure_root != chash(
            {**self.identity_dict(), "predicate_digest": self.predicate_digest}
        ):
            raise StateTransitionRefused("forward closure root does not verify")

    def predicate_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.PREDICATE_SCHEMA_VERSION,
            "predecessor_event_id": self.predecessor_event_id,
            "predecessor_frontier_root": self.predecessor_frontier_root,
            "allowed_transition_kind": self.ALLOWED_TRANSITION_KIND,
            "finalized_projection_digest": self.finalized_projection_digest,
            "affected_roots": dict(sorted(self.affected_roots.items())),
            "expires_at": self.expires_at,
            "related_head_predicate": self.RELATED_HEAD_PREDICATE,
            "successor_predicate": self.SUCCESSOR_PREDICATE,
        }

    @property
    def predicate_digest(self) -> str:
        return chash(self.predicate_dict())

    def identity_dict(self) -> dict[str, Any]:
        return {
            **self.predicate_dict(),
            "schema_version": self.SCHEMA_VERSION,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity_dict(),
            "predicate_digest": self.predicate_digest,
            "forward_closure_root": self.forward_closure_root,
        }

    @classmethod
    def reserve(
        cls,
        *,
        predecessor_event_id: str,
        affected_roots: Mapping[str, str],
        expires_at: str,
        finalized_projection_digest: str,
    ) -> "RegionForwardClosure":
        roots = {str(root_type): str(root) for root_type, root in affected_roots.items()}
        frontier = region_publication_affected_frontier_root(roots)
        provisional = {
            "predecessor_event_id": predecessor_event_id,
            "predecessor_frontier_root": frontier,
            "finalized_projection_digest": finalized_projection_digest,
            "affected_roots": roots,
            "expires_at": expires_at,
        }
        predicate = {
            "schema_version": cls.PREDICATE_SCHEMA_VERSION,
            "predecessor_event_id": predecessor_event_id,
            "predecessor_frontier_root": frontier,
            "allowed_transition_kind": cls.ALLOWED_TRANSITION_KIND,
            "finalized_projection_digest": finalized_projection_digest,
            "affected_roots": dict(sorted(roots.items())),
            "expires_at": expires_at,
            "related_head_predicate": cls.RELATED_HEAD_PREDICATE,
            "successor_predicate": cls.SUCCESSOR_PREDICATE,
        }
        predicate_digest = chash(predicate)
        identity = {
            "schema_version": cls.SCHEMA_VERSION,
            **{key: value for key, value in predicate.items() if key != "schema_version"},
        }
        return cls(
            **provisional,
            forward_closure_root=chash({**identity, "predicate_digest": predicate_digest}),
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RegionForwardClosure":
        keys = (
            "predecessor_event_id",
            "predecessor_frontier_root",
            "allowed_transition_kind",
            "finalized_projection_digest",
            "affected_roots",
            "expires_at",
            "related_head_predicate",
            "successor_predicate",
            "predicate_digest",
            "forward_closure_root",
        )
        _check_version(raw, cls.SCHEMA_VERSION, "RegionForwardClosure")
        _require_exact(raw, keys, "RegionForwardClosure")
        hook = cls(
            predecessor_event_id=raw["predecessor_event_id"],
            predecessor_frontier_root=raw["predecessor_frontier_root"],
            finalized_projection_digest=raw["finalized_projection_digest"],
            affected_roots=dict(raw["affected_roots"]),
            expires_at=raw["expires_at"],
            forward_closure_root=raw["forward_closure_root"],
        )
        if (
            raw["allowed_transition_kind"] != cls.ALLOWED_TRANSITION_KIND
            or raw["related_head_predicate"] != cls.RELATED_HEAD_PREDICATE
            or raw["successor_predicate"] != cls.SUCCESSOR_PREDICATE
            or raw["predicate_digest"] != hook.predicate_digest
        ):
            raise StateTransitionRefused("forward closure predicate does not verify")
        return hook


def region_forward_closure_consumption_root(
    *,
    forward_closure_root: str,
    authorized_event_id: str,
    finalized_projection_digest: str,
) -> str:
    """Bind one hook to the authorization head consumed by FINALIZED."""

    return chash(
        {
            "schema_version": "laplace.region-forward-closure-consumption/1",
            "forward_closure_root": forward_closure_root,
            "authorized_event_id": authorized_event_id,
            "finalized_projection_digest": finalized_projection_digest,
        }
    )


@dataclass(frozen=True)
class RegionPublicationPrepared:
    """Durable unreachable candidate and the exact authority needed to recover it."""

    SCHEMA_VERSION: ClassVar[str] = "region-publication-prepared/3"

    publication_id: str
    lease_id: str
    seat_id: str
    holder_ref: str
    function: SeatRole
    checkout_event_id: str
    binding_event_id: str
    provider_identity_generation: str
    candidate_commit: str
    candidate_tree: str
    committed_paths: tuple[str, ...]
    patch_handle: str
    custody_handle: str
    affected_frontier_root: str
    rehearsal_evidence_root: str
    forward_closure: RegionForwardClosure
    forward_closure_root: str
    base_ref: str
    expected_old: str
    private_index_recipe: Mapping[str, Any]
    recovery_root: str
    message: str
    evidence: Mapping[str, str]

    def __post_init__(self) -> None:
        for name, value in (
            ("publication_id", self.publication_id),
            ("lease_id", self.lease_id),
            ("seat_id", self.seat_id),
            ("holder_ref", self.holder_ref),
            ("checkout_event_id", self.checkout_event_id),
            ("binding_event_id", self.binding_event_id),
            ("provider_identity_generation", self.provider_identity_generation),
            ("base_ref", self.base_ref),
            ("message", self.message),
        ):
            _nonempty(value, name)
        _publication_oid(self.candidate_commit, "candidate_commit")
        _publication_oid(self.candidate_tree, "candidate_tree")
        _publication_oid(self.expected_old, "expected_old")
        for field, value in (
            ("patch_handle", self.patch_handle),
            ("custody_handle", self.custody_handle),
            ("affected_frontier_root", self.affected_frontier_root),
            ("rehearsal_evidence_root", self.rehearsal_evidence_root),
            ("forward_closure_root", self.forward_closure_root),
            ("recovery_root", self.recovery_root),
        ):
            _publication_handle(value, field)
        if self.forward_closure_root != self.forward_closure.forward_closure_root:
            raise StateTransitionRefused(
                "prepared publication forward closure root mismatches its typed hook"
            )
        if not self.committed_paths or len(set(self.committed_paths)) != len(
            self.committed_paths
        ):
            raise StateTransitionRefused(
                "prepared publication requires duplicate-free committed paths"
            )
        for path in self.committed_paths:
            _region_path(path, "committed_paths")
        recipe = dict(self.private_index_recipe)
        if recipe.get("schema_version") != "laplace.private-git-index-recipe/1":
            raise StateTransitionRefused("prepared publication private-index recipe is unknown")
        if recipe.get("index_scope") != "ephemeral-private":
            raise StateTransitionRefused("prepared publication may not name the main Git index")
        if not self.evidence or any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, str)
            or not value.strip()
            for key, value in self.evidence.items()
        ):
            raise StateTransitionRefused("prepared publication requires named exact evidence")

    def identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "lease_id": self.lease_id,
            "seat_id": self.seat_id,
            "holder_ref": self.holder_ref,
            "function": self.function.value,
            "checkout_event_id": self.checkout_event_id,
            "binding_event_id": self.binding_event_id,
            "provider_identity_generation": self.provider_identity_generation,
            "candidate_commit": self.candidate_commit,
            "candidate_tree": self.candidate_tree,
            "committed_paths": list(self.committed_paths),
            "patch_handle": self.patch_handle,
            "custody_handle": self.custody_handle,
            "affected_frontier_root": self.affected_frontier_root,
            "rehearsal_evidence_root": self.rehearsal_evidence_root,
            "forward_closure": self.forward_closure.to_dict(),
            "forward_closure_root": self.forward_closure_root,
            "base_ref": self.base_ref,
            "expected_old": self.expected_old,
            "private_index_recipe": dict(self.private_index_recipe),
            "message": self.message,
            "evidence": dict(self.evidence),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity_dict(),
            "publication_id": self.publication_id,
            "recovery_root": self.recovery_root,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RegionPublicationPrepared":
        keys = (
            "publication_id",
            "lease_id",
            "seat_id",
            "holder_ref",
            "function",
            "checkout_event_id",
            "binding_event_id",
            "provider_identity_generation",
            "candidate_commit",
            "candidate_tree",
            "committed_paths",
            "patch_handle",
            "custody_handle",
            "affected_frontier_root",
            "rehearsal_evidence_root",
            "forward_closure",
            "forward_closure_root",
            "base_ref",
            "expected_old",
            "private_index_recipe",
            "recovery_root",
            "message",
            "evidence",
        )
        _check_version(raw, cls.SCHEMA_VERSION, "RegionPublicationPrepared")
        _require_exact(raw, keys, "RegionPublicationPrepared")
        return cls(
            publication_id=raw["publication_id"],
            lease_id=raw["lease_id"],
            seat_id=raw["seat_id"],
            holder_ref=raw["holder_ref"],
            function=SeatRole(raw["function"]),
            checkout_event_id=raw["checkout_event_id"],
            binding_event_id=raw["binding_event_id"],
            provider_identity_generation=raw["provider_identity_generation"],
            candidate_commit=raw["candidate_commit"],
            candidate_tree=raw["candidate_tree"],
            committed_paths=tuple(raw["committed_paths"]),
            patch_handle=raw["patch_handle"],
            custody_handle=raw["custody_handle"],
            affected_frontier_root=raw["affected_frontier_root"],
            rehearsal_evidence_root=raw["rehearsal_evidence_root"],
            forward_closure=RegionForwardClosure.from_dict(raw["forward_closure"]),
            forward_closure_root=raw["forward_closure_root"],
            base_ref=raw["base_ref"],
            expected_old=raw["expected_old"],
            private_index_recipe=dict(raw["private_index_recipe"]),
            recovery_root=raw["recovery_root"],
            message=raw["message"],
            evidence=dict(raw["evidence"]),
        )


@dataclass(frozen=True)
class RegionPublicationSignoff:
    """One current role's exact PASS over a frozen local-ref publication."""

    SCHEMA_VERSION: ClassVar[str] = "laplace.region-publication-signed/1"

    publication_id: str
    lease_id: str
    prepared_event_id: str
    recovery_root: str
    candidate_commit: str
    candidate_tree: str
    patch_handle: str
    custody_handle: str
    affected_frontier_root: str
    rehearsal_evidence_root: str
    forward_closure_root: str
    signer_seat_id: str
    signer_holder_ref: str
    signer_function: SeatRole
    signer_join_event_id: str
    signer_binding_event_id: str
    signer_provider_identity_generation: str
    role_profile_handle: str
    reconstruction_handle: str
    predicate_result: str
    predicate_domain: str
    expires_at: str
    consumed_signoff_event_ids: tuple[str, ...]
    signoff_root: str

    def __post_init__(self) -> None:
        for name, value in (
            ("publication_id", self.publication_id),
            ("lease_id", self.lease_id),
            ("prepared_event_id", self.prepared_event_id),
            ("signer_seat_id", self.signer_seat_id),
            ("signer_holder_ref", self.signer_holder_ref),
            ("predicate_domain", self.predicate_domain),
        ):
            _nonempty(value, name)
        _publication_oid(self.candidate_commit, "candidate_commit")
        _publication_oid(self.candidate_tree, "candidate_tree")
        for field, value in (
            ("recovery_root", self.recovery_root),
            ("patch_handle", self.patch_handle),
            ("custody_handle", self.custody_handle),
            ("affected_frontier_root", self.affected_frontier_root),
            ("rehearsal_evidence_root", self.rehearsal_evidence_root),
            ("forward_closure_root", self.forward_closure_root),
            ("signer_join_event_id", self.signer_join_event_id),
            ("signer_binding_event_id", self.signer_binding_event_id),
            (
                "signer_provider_identity_generation",
                self.signer_provider_identity_generation,
            ),
            ("role_profile_handle", self.role_profile_handle),
            ("reconstruction_handle", self.reconstruction_handle),
            ("signoff_root", self.signoff_root),
        ):
            _publication_handle(value, field)
        expected_domain = {
            SeatRole.EGO: "ego",
            SeatRole.SENSORIUM: "aisthesis",
            SeatRole.SUPEREGO: "superego",
        }.get(self.signer_function)
        if expected_domain is None or self.predicate_domain != expected_domain:
            raise StateTransitionRefused(
                "publication signoff predicate domain mismatches its canonical function"
            )
        if self.predicate_result != "PASS":
            raise StateTransitionRefused("publication signoff predicate must be PASS")
        _timestamp(self.expires_at, "expires_at")
        if len(set(self.consumed_signoff_event_ids)) != len(
            self.consumed_signoff_event_ids
        ):
            raise StateTransitionRefused("publication signoff consumption cannot repeat")
        for event_id in self.consumed_signoff_event_ids:
            _publication_handle(event_id, "consumed_signoff_event_id")
        if self.signer_function == SeatRole.SUPEREGO:
            if len(self.consumed_signoff_event_ids) != 2:
                raise StateTransitionRefused(
                    "Superego publication signoff must consume Ego and Aisthesis"
                )
        elif self.consumed_signoff_event_ids:
            raise StateTransitionRefused(
                "only Superego publication signoff consumes prior signoffs"
            )
        if self.signoff_root != chash(self.identity_dict()):
            raise StateTransitionRefused("publication signoff root does not verify")

    def identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "publication_id": self.publication_id,
            "lease_id": self.lease_id,
            "prepared_event_id": self.prepared_event_id,
            "recovery_root": self.recovery_root,
            "candidate_commit": self.candidate_commit,
            "candidate_tree": self.candidate_tree,
            "patch_handle": self.patch_handle,
            "custody_handle": self.custody_handle,
            "affected_frontier_root": self.affected_frontier_root,
            "rehearsal_evidence_root": self.rehearsal_evidence_root,
            "forward_closure_root": self.forward_closure_root,
            "signer_seat_id": self.signer_seat_id,
            "signer_holder_ref": self.signer_holder_ref,
            "signer_function": self.signer_function.value,
            "signer_join_event_id": self.signer_join_event_id,
            "signer_binding_event_id": self.signer_binding_event_id,
            "signer_provider_identity_generation": (
                self.signer_provider_identity_generation
            ),
            "role_profile_handle": self.role_profile_handle,
            "reconstruction_handle": self.reconstruction_handle,
            "predicate_result": self.predicate_result,
            "predicate_domain": self.predicate_domain,
            "expires_at": self.expires_at,
            "consumed_signoff_event_ids": list(self.consumed_signoff_event_ids),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity_dict(), "signoff_root": self.signoff_root}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RegionPublicationSignoff":
        keys = (
            "publication_id",
            "lease_id",
            "prepared_event_id",
            "recovery_root",
            "candidate_commit",
            "candidate_tree",
            "patch_handle",
            "custody_handle",
            "affected_frontier_root",
            "rehearsal_evidence_root",
            "forward_closure_root",
            "signer_seat_id",
            "signer_holder_ref",
            "signer_function",
            "signer_join_event_id",
            "signer_binding_event_id",
            "signer_provider_identity_generation",
            "role_profile_handle",
            "reconstruction_handle",
            "predicate_result",
            "predicate_domain",
            "expires_at",
            "consumed_signoff_event_ids",
            "signoff_root",
        )
        _check_version(raw, cls.SCHEMA_VERSION, "RegionPublicationSignoff")
        _require_exact(raw, keys, "RegionPublicationSignoff")
        return cls(
            **{
                key: (
                    SeatRole(raw[key])
                    if key == "signer_function"
                    else tuple(raw[key])
                    if key == "consumed_signoff_event_ids"
                    else raw[key]
                )
                for key in keys
            }
        )


@dataclass(frozen=True)
class RegionPublicationAuthorization:
    """A durable permission for exactly one update-ref compare-and-swap."""

    SCHEMA_VERSION: ClassVar[str] = "region-publication-authorization/2"

    publication_id: str
    lease_id: str
    prepared_event_id: str
    recovery_root: str
    base_ref: str
    expected_old: str
    candidate_commit: str
    affected_frontier_root: str
    rehearsal_evidence_root: str
    forward_closure_root: str
    signoff_event_ids: tuple[str, ...]
    signoff_roots: tuple[str, ...]
    expires_at: str
    cas_permission: str
    authorization_root: str

    def __post_init__(self) -> None:
        for name, value in (
            ("publication_id", self.publication_id),
            ("lease_id", self.lease_id),
            ("prepared_event_id", self.prepared_event_id),
            ("base_ref", self.base_ref),
        ):
            _nonempty(value, name)
        _publication_handle(self.recovery_root, "recovery_root")
        _publication_handle(self.authorization_root, "authorization_root")
        for field, value in (
            ("affected_frontier_root", self.affected_frontier_root),
            ("rehearsal_evidence_root", self.rehearsal_evidence_root),
            ("forward_closure_root", self.forward_closure_root),
        ):
            _publication_handle(value, field)
        if len(self.signoff_event_ids) != 3 or len(set(self.signoff_event_ids)) != 3:
            raise StateTransitionRefused("publication authorization requires three signoffs")
        if len(self.signoff_roots) != 3 or len(set(self.signoff_roots)) != 3:
            raise StateTransitionRefused("publication authorization requires three receipt roots")
        for value in (*self.signoff_event_ids, *self.signoff_roots):
            _publication_handle(value, "publication_signoff")
        _timestamp(self.expires_at, "expires_at")
        _publication_oid(self.expected_old, "expected_old")
        _publication_oid(self.candidate_commit, "candidate_commit")
        if self.cas_permission != "UPDATE-REF-ONCE":
            raise StateTransitionRefused("publication authorization is not exact one-CAS")

    def identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "publication_id": self.publication_id,
            "lease_id": self.lease_id,
            "prepared_event_id": self.prepared_event_id,
            "recovery_root": self.recovery_root,
            "base_ref": self.base_ref,
            "expected_old": self.expected_old,
            "candidate_commit": self.candidate_commit,
            "affected_frontier_root": self.affected_frontier_root,
            "rehearsal_evidence_root": self.rehearsal_evidence_root,
            "forward_closure_root": self.forward_closure_root,
            "signoff_event_ids": list(self.signoff_event_ids),
            "signoff_roots": list(self.signoff_roots),
            "expires_at": self.expires_at,
            "cas_permission": self.cas_permission,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity_dict(), "authorization_root": self.authorization_root}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RegionPublicationAuthorization":
        keys = (
            "publication_id",
            "lease_id",
            "prepared_event_id",
            "recovery_root",
            "base_ref",
            "expected_old",
            "candidate_commit",
            "affected_frontier_root",
            "rehearsal_evidence_root",
            "forward_closure_root",
            "signoff_event_ids",
            "signoff_roots",
            "expires_at",
            "cas_permission",
            "authorization_root",
        )
        _check_version(raw, cls.SCHEMA_VERSION, "RegionPublicationAuthorization")
        _require_exact(raw, keys, "RegionPublicationAuthorization")
        return cls(
            **{
                key: tuple(raw[key]) if key in {"signoff_event_ids", "signoff_roots"} else raw[key]
                for key in keys
            }
        )


@dataclass(frozen=True)
class RegionPublicationFinalized:
    """The durable acknowledgement of an authorized Git reference CAS."""

    SCHEMA_VERSION: ClassVar[str] = "region-publication-finalized/3"

    publication_id: str
    lease_id: str
    prepared_event_id: str
    authorized_event_id: str
    recovery_root: str
    authorization_root: str
    base_ref: str
    expected_old: str
    result_git_head: str
    candidate_tree: str
    patch_handle: str
    custody_handle: str
    affected_frontier_root: str
    forward_closure_root: str
    forward_closure_consumption_root: str
    signoff_roots: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, value in (
            ("publication_id", self.publication_id),
            ("lease_id", self.lease_id),
            ("prepared_event_id", self.prepared_event_id),
            ("authorized_event_id", self.authorized_event_id),
            ("base_ref", self.base_ref),
        ):
            _nonempty(value, name)
        for field, value in (
            ("recovery_root", self.recovery_root),
            ("authorization_root", self.authorization_root),
            ("patch_handle", self.patch_handle),
            ("custody_handle", self.custody_handle),
            ("affected_frontier_root", self.affected_frontier_root),
            ("forward_closure_root", self.forward_closure_root),
            (
                "forward_closure_consumption_root",
                self.forward_closure_consumption_root,
            ),
        ):
            _publication_handle(value, field)
        if len(self.signoff_roots) != 3:
            raise StateTransitionRefused("publication finalize requires the triad receipt roots")
        for value in self.signoff_roots:
            _publication_handle(value, "signoff_root")
        _publication_oid(self.expected_old, "expected_old")
        _publication_oid(self.result_git_head, "result_git_head")
        _publication_oid(self.candidate_tree, "candidate_tree")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "publication_id": self.publication_id,
            "lease_id": self.lease_id,
            "prepared_event_id": self.prepared_event_id,
            "authorized_event_id": self.authorized_event_id,
            "recovery_root": self.recovery_root,
            "authorization_root": self.authorization_root,
            "base_ref": self.base_ref,
            "expected_old": self.expected_old,
            "result_git_head": self.result_git_head,
            "candidate_tree": self.candidate_tree,
            "patch_handle": self.patch_handle,
            "custody_handle": self.custody_handle,
            "affected_frontier_root": self.affected_frontier_root,
            "forward_closure_root": self.forward_closure_root,
            "forward_closure_consumption_root": self.forward_closure_consumption_root,
            "signoff_roots": list(self.signoff_roots),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RegionPublicationFinalized":
        keys = (
            "publication_id",
            "lease_id",
            "prepared_event_id",
            "authorized_event_id",
            "recovery_root",
            "authorization_root",
            "base_ref",
            "expected_old",
            "result_git_head",
            "candidate_tree",
            "patch_handle",
            "custody_handle",
            "affected_frontier_root",
            "forward_closure_root",
            "forward_closure_consumption_root",
            "signoff_roots",
        )
        _check_version(raw, cls.SCHEMA_VERSION, "RegionPublicationFinalized")
        _require_exact(raw, keys, "RegionPublicationFinalized")
        return cls(
            **{
                key: tuple(raw[key]) if key == "signoff_roots" else raw[key]
                for key in keys
            }
        )


@dataclass(frozen=True)
class AssumptionSelection:
    SCHEMA_VERSION: ClassVar[str] = "assumption-selection/1"

    assumption: str
    fibre: str
    confidence: float | None
    alternatives: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty(self.assumption, "assumption")
        _nonempty(self.fibre, "fibre")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise StateTransitionRefused("assumption confidence must be between zero and one")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "confidence": self.confidence,
            "alternatives": list(self.alternatives),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AssumptionSelection":
        _check_version(raw, cls.SCHEMA_VERSION, "AssumptionSelection")
        keys = ("assumption", "fibre", "confidence", "alternatives")
        _require_exact(raw, keys, "AssumptionSelection")
        return cls(
            assumption=raw["assumption"],
            fibre=raw["fibre"],
            confidence=raw["confidence"],
            alternatives=tuple(raw["alternatives"]),
        )


@dataclass(frozen=True)
class CorpusAct:
    SCHEMA_VERSION: ClassVar[str] = "corpus-act/1"

    act_id: str
    domain: str
    verb: str
    target: str
    phase: ActPhase
    inputs: Mapping[str, Any]
    outputs: Mapping[str, Any]
    transaction_id: str | None = None
    preview_event_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("act_id", self.act_id),
            ("domain", self.domain),
            ("verb", self.verb),
            ("target", self.target),
        ):
            _nonempty(value, name)
        if self.phase == ActPhase.READ:
            if self.transaction_id is not None or self.preview_event_id is not None:
                raise StateTransitionRefused("read act cannot enter a transaction")
        elif self.phase == ActPhase.PREVIEW:
            if not self.transaction_id or self.preview_event_id is not None:
                raise StateTransitionRefused("preview requires a transaction and no prior preview")
        elif not self.transaction_id or not self.preview_event_id:
            raise StateTransitionRefused("commit or rollback must cite its transaction preview")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "act_id": self.act_id,
            "domain": self.domain,
            "verb": self.verb,
            "target": self.target,
            "phase": self.phase.value,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "transaction_id": self.transaction_id,
            "preview_event_id": self.preview_event_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CorpusAct":
        _check_version(raw, cls.SCHEMA_VERSION, "CorpusAct")
        keys = (
            "act_id",
            "domain",
            "verb",
            "target",
            "phase",
            "inputs",
            "outputs",
            "transaction_id",
            "preview_event_id",
        )
        _require_exact(raw, keys, "CorpusAct")
        return cls(
            act_id=raw["act_id"],
            domain=raw["domain"],
            verb=raw["verb"],
            target=raw["target"],
            phase=ActPhase(raw["phase"]),
            inputs=dict(raw["inputs"]),
            outputs=dict(raw["outputs"]),
            transaction_id=raw["transaction_id"],
            preview_event_id=raw["preview_event_id"],
        )


@dataclass(frozen=True)
class SeatMessage:
    """A provider-neutral message envelope carried by the one Atlas history."""

    SCHEMA_VERSION: ClassVar[str] = "seat-message/1"

    message_id: str
    sender_seat_id: str
    recipient_seat_id: str
    message_type: str
    body_handle: str
    dependency_roots: Mapping[str, str]
    idempotency_key: str
    cursor: int
    expires_at: str

    def __post_init__(self) -> None:
        for name, value in (
            ("message_id", self.message_id),
            ("sender_seat_id", self.sender_seat_id),
            ("recipient_seat_id", self.recipient_seat_id),
            ("message_type", self.message_type),
            ("body_handle", self.body_handle),
            ("idempotency_key", self.idempotency_key),
        ):
            _nonempty(value, name)
        if self.sender_seat_id == self.recipient_seat_id:
            raise StateTransitionRefused("seat message must cross a logical-seat boundary")
        if not self.dependency_roots:
            raise StateTransitionRefused("seat message must bind its dependency roots")
        if isinstance(self.cursor, bool) or not isinstance(self.cursor, int) or self.cursor < 1:
            raise StateTransitionRefused("message cursor must be a positive integer")
        _timestamp(self.expires_at, "expires_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "message_id": self.message_id,
            "sender_seat_id": self.sender_seat_id,
            "recipient_seat_id": self.recipient_seat_id,
            "message_type": self.message_type,
            "body_handle": self.body_handle,
            "dependency_roots": dict(self.dependency_roots),
            "idempotency_key": self.idempotency_key,
            "cursor": self.cursor,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SeatMessage":
        _check_version(raw, cls.SCHEMA_VERSION, "SeatMessage")
        keys = (
            "message_id",
            "sender_seat_id",
            "recipient_seat_id",
            "message_type",
            "body_handle",
            "dependency_roots",
            "idempotency_key",
            "cursor",
            "expires_at",
        )
        _require_exact(raw, keys, "SeatMessage")
        return cls(
            message_id=raw["message_id"],
            sender_seat_id=raw["sender_seat_id"],
            recipient_seat_id=raw["recipient_seat_id"],
            message_type=raw["message_type"],
            body_handle=raw["body_handle"],
            dependency_roots=dict(raw["dependency_roots"]),
            idempotency_key=raw["idempotency_key"],
            cursor=raw["cursor"],
            expires_at=raw["expires_at"],
        )


@dataclass(frozen=True)
class MessagePull:
    SCHEMA_VERSION: ClassVar[str] = "message-pull/1"

    seat_id: str
    after_cursor: int
    result_cursor: int
    as_of: str
    message_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty(self.seat_id, "seat_id")
        for field, value in (
            ("after_cursor", self.after_cursor),
            ("result_cursor", self.result_cursor),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise StateTransitionRefused("message cursor cannot be negative", field=field)
        if self.result_cursor < self.after_cursor:
            raise StateTransitionRefused("pull cursor cannot move backward")
        if len(set(self.message_ids)) != len(self.message_ids):
            raise StateTransitionRefused("pull result cannot repeat a message")
        _timestamp(self.as_of, "as_of")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "seat_id": self.seat_id,
            "after_cursor": self.after_cursor,
            "result_cursor": self.result_cursor,
            "as_of": self.as_of,
            "message_ids": list(self.message_ids),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MessagePull":
        _check_version(raw, cls.SCHEMA_VERSION, "MessagePull")
        keys = ("seat_id", "after_cursor", "result_cursor", "as_of", "message_ids")
        _require_exact(raw, keys, "MessagePull")
        return cls(
            seat_id=raw["seat_id"],
            after_cursor=raw["after_cursor"],
            result_cursor=raw["result_cursor"],
            as_of=raw["as_of"],
            message_ids=tuple(raw["message_ids"]),
        )


@dataclass(frozen=True)
class MessageAcknowledgement:
    SCHEMA_VERSION: ClassVar[str] = "message-acknowledgement/1"

    message_id: str
    seat_id: str
    disposition: AcknowledgementDisposition
    reconstruction_handle: str | None
    reconstruction_event_id: str | None
    note: str

    def __post_init__(self) -> None:
        _nonempty(self.message_id, "message_id")
        _nonempty(self.seat_id, "seat_id")
        _nonempty(self.note, "note")
        if self.disposition == AcknowledgementDisposition.ACCEPTED:
            if not self.reconstruction_handle or not self.reconstruction_event_id:
                raise StateTransitionRefused(
                    "accepted acknowledgement must carry its reconstruction proof"
                )
        elif self.reconstruction_handle is not None or self.reconstruction_event_id is not None:
            raise StateTransitionRefused(
                "refused acknowledgement cannot masquerade as reconstructed delivery"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "message_id": self.message_id,
            "seat_id": self.seat_id,
            "disposition": self.disposition.value,
            "reconstruction_handle": self.reconstruction_handle,
            "reconstruction_event_id": self.reconstruction_event_id,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MessageAcknowledgement":
        _check_version(raw, cls.SCHEMA_VERSION, "MessageAcknowledgement")
        keys = (
            "message_id",
            "seat_id",
            "disposition",
            "reconstruction_handle",
            "reconstruction_event_id",
            "note",
        )
        _require_exact(raw, keys, "MessageAcknowledgement")
        return cls(
            message_id=raw["message_id"],
            seat_id=raw["seat_id"],
            disposition=AcknowledgementDisposition(raw["disposition"]),
            reconstruction_handle=raw["reconstruction_handle"],
            reconstruction_event_id=raw["reconstruction_event_id"],
            note=raw["note"],
        )


@dataclass(frozen=True)
class MessageExpiry:
    SCHEMA_VERSION: ClassVar[str] = "message-expiry/1"

    message_id: str
    as_of: str

    def __post_init__(self) -> None:
        _nonempty(self.message_id, "message_id")
        _timestamp(self.as_of, "as_of")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "message_id": self.message_id,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MessageExpiry":
        _check_version(raw, cls.SCHEMA_VERSION, "MessageExpiry")
        _require_exact(raw, ("message_id", "as_of"), "MessageExpiry")
        return cls(message_id=raw["message_id"], as_of=raw["as_of"])


@dataclass(frozen=True)
class MessageForkPreservation:
    """Quarantine one cross-fibre obligation without rewriting its delivery history."""

    SCHEMA_VERSION: ClassVar[str] = "message-fork-preservation/1"

    message_id: str
    original_sender_seat_id: str
    recipient_seat_id: str
    body_handle: str
    author_ruling_ref: str
    authority_event_id: str
    reason: str
    reopen_condition: str
    actor_provider_session_ref: str
    actor_provider_identity_proof_handle: str
    actor_provider_identity_generation: str

    def __post_init__(self) -> None:
        for field_name in (
            "message_id",
            "original_sender_seat_id",
            "recipient_seat_id",
            "body_handle",
            "author_ruling_ref",
            "authority_event_id",
            "reason",
            "reopen_condition",
            "actor_provider_session_ref",
            "actor_provider_identity_proof_handle",
            "actor_provider_identity_generation",
        ):
            _nonempty(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "message_id": self.message_id,
            "original_sender_seat_id": self.original_sender_seat_id,
            "recipient_seat_id": self.recipient_seat_id,
            "body_handle": self.body_handle,
            "author_ruling_ref": self.author_ruling_ref,
            "authority_event_id": self.authority_event_id,
            "reason": self.reason,
            "reopen_condition": self.reopen_condition,
            "actor_provider_session_ref": self.actor_provider_session_ref,
            "actor_provider_identity_proof_handle": (self.actor_provider_identity_proof_handle),
            "actor_provider_identity_generation": (self.actor_provider_identity_generation),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MessageForkPreservation":
        _check_version(raw, cls.SCHEMA_VERSION, "MessageForkPreservation")
        keys = (
            "message_id",
            "original_sender_seat_id",
            "recipient_seat_id",
            "body_handle",
            "author_ruling_ref",
            "authority_event_id",
            "reason",
            "reopen_condition",
            "actor_provider_session_ref",
            "actor_provider_identity_proof_handle",
            "actor_provider_identity_generation",
        )
        _require_exact(raw, keys, "MessageForkPreservation")
        return cls(**{key: raw[key] for key in keys})


@dataclass(frozen=True)
class MessageSupersession:
    """Retire one undelivered envelope after exact current-fibre replacements landed.

    Supersession is neither delivery nor expiry.  It preserves the historical message while
    making its present routing status terminal, and it binds the *current authenticated holder*
    of the sender seat to one or more replacement envelopes whose full delivery proofs already
    exist in the same history.  Older schemas remain decodable solely so their immutable history
    can replay across the lifecycle cutover; they are not current write authority.
    """

    SCHEMA_VERSION: ClassVar[str] = "message-supersession/3"
    LEGACY_V2_SCHEMA_VERSION: ClassVar[str] = "message-supersession/2"
    LEGACY_V1_SCHEMA_VERSION: ClassVar[str] = "message-supersession/1"

    message_id: str
    sender_seat_id: str
    replacement_message_ids: tuple[str, ...]
    note: str
    provider_session_ref: str | None = None
    provider_identity_proof_handle: str | None = None
    provider_identity_generation: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.message_id, "message_id")
        _nonempty(self.sender_seat_id, "sender_seat_id")
        _nonempty(self.note, "note")
        if not self.replacement_message_ids:
            raise StateTransitionRefused("message supersession requires a replacement")
        if len(set(self.replacement_message_ids)) != len(self.replacement_message_ids):
            raise StateTransitionRefused("message supersession cannot repeat a replacement")
        if self.message_id in self.replacement_message_ids:
            raise StateTransitionRefused("a message cannot supersede itself")
        for replacement_id in self.replacement_message_ids:
            _nonempty(replacement_id, "replacement_message_id")
        identity_fields = (
            self.provider_session_ref,
            self.provider_identity_proof_handle,
            self.provider_identity_generation,
        )
        if any(value is not None for value in identity_fields):
            if any(value is None for value in identity_fields):
                raise StateTransitionRefused(
                    "message supersession caller identity must be complete"
                )
            for field_name, value in zip(
                (
                    "provider_session_ref",
                    "provider_identity_proof_handle",
                    "provider_identity_generation",
                ),
                identity_fields,
                strict=True,
            ):
                assert value is not None
                _nonempty(value, field_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "message_id": self.message_id,
            "sender_seat_id": self.sender_seat_id,
            "replacement_message_ids": list(self.replacement_message_ids),
            "note": self.note,
            "provider_session_ref": self.provider_session_ref,
            "provider_identity_proof_handle": self.provider_identity_proof_handle,
            "provider_identity_generation": self.provider_identity_generation,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MessageSupersession":
        legacy_keys = (
            "message_id",
            "sender_seat_id",
            "replacement_message_ids",
            "note",
        )
        version = raw.get("schema_version")
        if version == cls.LEGACY_V1_SCHEMA_VERSION:
            _require_exact(raw, legacy_keys, "MessageSupersession")
            return cls(
                message_id=raw["message_id"],
                sender_seat_id=raw["sender_seat_id"],
                replacement_message_ids=tuple(raw["replacement_message_ids"]),
                note=raw["note"],
            )
        keys = (
            *legacy_keys,
            "provider_session_ref",
            "provider_identity_proof_handle",
            "provider_identity_generation",
        )
        if version not in {cls.LEGACY_V2_SCHEMA_VERSION, cls.SCHEMA_VERSION}:
            raise StateTransitionRefused(
                "unsupported schema version",
                expected=cls.SCHEMA_VERSION,
                got=version,
                object="MessageSupersession",
            )
        _require_exact(raw, keys, "MessageSupersession")
        parsed = cls(
            message_id=raw["message_id"],
            sender_seat_id=raw["sender_seat_id"],
            replacement_message_ids=tuple(raw["replacement_message_ids"]),
            note=raw["note"],
            provider_session_ref=raw["provider_session_ref"],
            provider_identity_proof_handle=raw["provider_identity_proof_handle"],
            provider_identity_generation=raw["provider_identity_generation"],
        )
        if version == cls.SCHEMA_VERSION and any(
            value is None
            for value in (
                parsed.provider_session_ref,
                parsed.provider_identity_proof_handle,
                parsed.provider_identity_generation,
            )
        ):
            raise StateTransitionRefused(
                "current message supersession requires complete caller identity"
            )
        return parsed


@dataclass(frozen=True)
class MessageMigrationRecoveryEntry:
    """One source-root-to-message proof in an atomic migration recovery bundle."""

    source_key: str
    message_id: str
    body_handle: str
    materialization_event_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("source_key", self.source_key),
            ("message_id", self.message_id),
            ("body_handle", self.body_handle),
            ("materialization_event_id", self.materialization_event_id),
        ):
            _nonempty(value, name)
        prefix, separator, index = self.source_key.partition("_")
        if prefix != "source" or separator != "_" or not index.isdigit() or int(index) < 1:
            raise StateTransitionRefused(
                "migration recovery source key must be source_N",
                source_key=self.source_key,
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "source_key": self.source_key,
            "message_id": self.message_id,
            "body_handle": self.body_handle,
            "materialization_event_id": self.materialization_event_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MessageMigrationRecoveryEntry":
        keys = (
            "source_key",
            "message_id",
            "body_handle",
            "materialization_event_id",
        )
        missing = sorted(set(keys) - set(raw))
        extra = sorted(set(raw) - set(keys))
        if missing or extra:
            raise SchemaFieldMissing(
                "MessageMigrationRecoveryEntry fields do not match its embedded schema",
                fields=missing,
                unexpected=extra,
            )
        return cls(**{key: raw[key] for key in keys})


@dataclass(frozen=True)
class MessageMigrationSupersession:
    """One atomic, author-commissioned recovery of a derived historical bundle.

    This is deliberately not ordinary sender supersession.  It records a current v2 Superego
    adjudication over historical sender authority invalidated by the lifecycle cutover.  The
    entries are derived from the delivered replacement's contiguous ``source_N`` roots and exact
    typed materializations; no historical message id is embedded in code or supplied freehand.
    """

    SCHEMA_VERSION: ClassVar[str] = "message-migration-supersession/1"
    MANIFEST_SCHEMA_VERSION: ClassVar[str] = "message-migration-recovery-manifest/1"
    COMMISSION_SCHEMA_VERSION: ClassVar[str] = "laplace.message-migration-recovery-commission/1"

    transition_id: str
    entries: tuple[MessageMigrationRecoveryEntry, ...]
    reconstruction_correlation: str
    replacement_message_id: str
    replacement_body_handle: str
    recovery_manifest_root: str
    lifecycle_cutover_event_id: str
    recovery_capsule_handle: str
    author_turn_handle: str
    commission_handle: str
    authority_message_id: str
    authority_body_handle: str
    authority_acknowledgement_event_id: str
    operator_seat_id: str
    operator_provider_session_ref: str
    operator_provider_identity_proof_handle: str
    operator_provider_identity_generation: str
    note: str

    def __post_init__(self) -> None:
        for name, value in (
            ("transition_id", self.transition_id),
            ("reconstruction_correlation", self.reconstruction_correlation),
            ("replacement_message_id", self.replacement_message_id),
            ("replacement_body_handle", self.replacement_body_handle),
            ("recovery_manifest_root", self.recovery_manifest_root),
            ("lifecycle_cutover_event_id", self.lifecycle_cutover_event_id),
            ("recovery_capsule_handle", self.recovery_capsule_handle),
            ("author_turn_handle", self.author_turn_handle),
            ("commission_handle", self.commission_handle),
            ("authority_message_id", self.authority_message_id),
            ("authority_body_handle", self.authority_body_handle),
            (
                "authority_acknowledgement_event_id",
                self.authority_acknowledgement_event_id,
            ),
            ("operator_seat_id", self.operator_seat_id),
            ("operator_provider_session_ref", self.operator_provider_session_ref),
            (
                "operator_provider_identity_proof_handle",
                self.operator_provider_identity_proof_handle,
            ),
            (
                "operator_provider_identity_generation",
                self.operator_provider_identity_generation,
            ),
            ("note", self.note),
        ):
            _nonempty(value, name)
        if not self.entries:
            raise StateTransitionRefused("message migration supersession requires a derived bundle")
        source_keys = tuple(entry.source_key for entry in self.entries)
        expected_keys = tuple(f"source_{index}" for index in range(1, len(self.entries) + 1))
        if source_keys != expected_keys:
            raise StateTransitionRefused(
                "migration recovery source keys must be unique, contiguous and ordered",
                expected=list(expected_keys),
                got=list(source_keys),
            )
        for field, values in (
            ("message_id", tuple(entry.message_id for entry in self.entries)),
            ("body_handle", tuple(entry.body_handle for entry in self.entries)),
            (
                "materialization_event_id",
                tuple(entry.materialization_event_id for entry in self.entries),
            ),
        ):
            if len(set(values)) != len(values):
                raise StateTransitionRefused(
                    "migration recovery entries must be bijective", field=field
                )
        if self.recovery_manifest_root != chash(self.manifest_dict()):
            raise StateTransitionRefused(
                "message migration recovery manifest root is contradictory"
            )
        if self.commission_handle != chash(self.commission_dict()):
            raise StateTransitionRefused(
                "message migration recovery commission handle is contradictory"
            )

    def manifest_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.MANIFEST_SCHEMA_VERSION,
            "replacement_message_id": self.replacement_message_id,
            "replacement_body_handle": self.replacement_body_handle,
            "reconstruction_correlation": self.reconstruction_correlation,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def commission_dict(self) -> dict[str, Any]:
        """The exact object Gerard must bank through the canonical front door."""

        return {
            "schema_version": self.COMMISSION_SCHEMA_VERSION,
            "authorized_act": self.SCHEMA_VERSION,
            "migration_root": self.recovery_capsule_handle,
            "replacement_message": self.replacement_message_id,
            "replacement_body": self.replacement_body_handle,
            "recovery_manifest": self.recovery_manifest_root,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "transition_id": self.transition_id,
            "entries": [entry.to_dict() for entry in self.entries],
            "reconstruction_correlation": self.reconstruction_correlation,
            "replacement_message_id": self.replacement_message_id,
            "replacement_body_handle": self.replacement_body_handle,
            "recovery_manifest_root": self.recovery_manifest_root,
            "lifecycle_cutover_event_id": self.lifecycle_cutover_event_id,
            "recovery_capsule_handle": self.recovery_capsule_handle,
            "author_turn_handle": self.author_turn_handle,
            "commission_handle": self.commission_handle,
            "authority_message_id": self.authority_message_id,
            "authority_body_handle": self.authority_body_handle,
            "authority_acknowledgement_event_id": (self.authority_acknowledgement_event_id),
            "operator_seat_id": self.operator_seat_id,
            "operator_provider_session_ref": self.operator_provider_session_ref,
            "operator_provider_identity_proof_handle": (
                self.operator_provider_identity_proof_handle
            ),
            "operator_provider_identity_generation": (self.operator_provider_identity_generation),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MessageMigrationSupersession":
        _check_version(raw, cls.SCHEMA_VERSION, "MessageMigrationSupersession")
        keys = (
            "transition_id",
            "entries",
            "reconstruction_correlation",
            "replacement_message_id",
            "replacement_body_handle",
            "recovery_manifest_root",
            "lifecycle_cutover_event_id",
            "recovery_capsule_handle",
            "author_turn_handle",
            "commission_handle",
            "authority_message_id",
            "authority_body_handle",
            "authority_acknowledgement_event_id",
            "operator_seat_id",
            "operator_provider_session_ref",
            "operator_provider_identity_proof_handle",
            "operator_provider_identity_generation",
            "note",
        )
        _require_exact(raw, keys, "MessageMigrationSupersession")
        return cls(
            transition_id=raw["transition_id"],
            entries=tuple(
                MessageMigrationRecoveryEntry.from_dict(entry) for entry in raw["entries"]
            ),
            reconstruction_correlation=raw["reconstruction_correlation"],
            replacement_message_id=raw["replacement_message_id"],
            replacement_body_handle=raw["replacement_body_handle"],
            recovery_manifest_root=raw["recovery_manifest_root"],
            lifecycle_cutover_event_id=raw["lifecycle_cutover_event_id"],
            recovery_capsule_handle=raw["recovery_capsule_handle"],
            author_turn_handle=raw["author_turn_handle"],
            commission_handle=raw["commission_handle"],
            authority_message_id=raw["authority_message_id"],
            authority_body_handle=raw["authority_body_handle"],
            authority_acknowledgement_event_id=raw["authority_acknowledgement_event_id"],
            operator_seat_id=raw["operator_seat_id"],
            operator_provider_session_ref=raw["operator_provider_session_ref"],
            operator_provider_identity_proof_handle=raw["operator_provider_identity_proof_handle"],
            operator_provider_identity_generation=raw["operator_provider_identity_generation"],
            note=raw["note"],
        )


@dataclass(frozen=True)
class RevisionAct:
    """One n-ary, fibre-local source revision.

    The act, rather than a pair of independently persisted forward/reverse edges, is
    authoritative.  A single record therefore represents replacement, split, merge, or a
    many-to-many reorganisation without pretending any of those operations is one-to-one.
    Currentness and reverse navigation are derived by the state fold.
    """

    SCHEMA_VERSION: ClassVar[str] = "revision-act/1"

    revision_id: str
    supersedes: tuple[str, ...]
    produces: tuple[str, ...]
    note: str

    def __post_init__(self) -> None:
        _nonempty(self.revision_id, "revision_id")
        _nonempty(self.note, "note")
        for field_name, values in (
            ("supersedes", self.supersedes),
            ("produces", self.produces),
        ):
            if not values:
                raise StateTransitionRefused(
                    "revision act requires non-empty endpoints", field=field_name
                )
            if len(set(values)) != len(values):
                raise StateTransitionRefused(
                    "revision act endpoints must be duplicate-free", field=field_name
                )
            for value in values:
                _nonempty(value, field_name)
        overlap = sorted(set(self.supersedes).intersection(self.produces))
        if overlap:
            raise StateTransitionRefused(
                "revision act cannot produce an endpoint it supersedes", endpoints=overlap
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "revision_id": self.revision_id,
            "supersedes": list(self.supersedes),
            "produces": list(self.produces),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RevisionAct":
        _check_version(raw, cls.SCHEMA_VERSION, "RevisionAct")
        keys = ("revision_id", "supersedes", "produces", "note")
        _require_exact(raw, keys, "RevisionAct")
        return cls(
            revision_id=raw["revision_id"],
            supersedes=tuple(raw["supersedes"]),
            produces=tuple(raw["produces"]),
            note=raw["note"],
        )


@dataclass(frozen=True)
class PermissionRequest:
    SCHEMA_VERSION: ClassVar[str] = "permission-request/1"

    request_id: str
    requester_seat_id: str
    permission: str
    target: str
    rationale: str
    expires_at: str

    def __post_init__(self) -> None:
        for name, value in (
            ("request_id", self.request_id),
            ("requester_seat_id", self.requester_seat_id),
            ("permission", self.permission),
            ("target", self.target),
            ("rationale", self.rationale),
        ):
            _nonempty(value, name)
        _timestamp(self.expires_at, "expires_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "request_id": self.request_id,
            "requester_seat_id": self.requester_seat_id,
            "permission": self.permission,
            "target": self.target,
            "rationale": self.rationale,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PermissionRequest":
        _check_version(raw, cls.SCHEMA_VERSION, "PermissionRequest")
        keys = (
            "request_id",
            "requester_seat_id",
            "permission",
            "target",
            "rationale",
            "expires_at",
        )
        _require_exact(raw, keys, "PermissionRequest")
        return cls(
            request_id=raw["request_id"],
            requester_seat_id=raw["requester_seat_id"],
            permission=raw["permission"],
            target=raw["target"],
            rationale=raw["rationale"],
            expires_at=raw["expires_at"],
        )


@dataclass(frozen=True)
class PermissionDecision:
    SCHEMA_VERSION: ClassVar[str] = "permission-decision/1"

    request_id: str
    decider_seat_id: str
    outcome: PermissionOutcome
    reason: str

    def __post_init__(self) -> None:
        _nonempty(self.request_id, "request_id")
        _nonempty(self.decider_seat_id, "decider_seat_id")
        _nonempty(self.reason, "reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "request_id": self.request_id,
            "decider_seat_id": self.decider_seat_id,
            "outcome": self.outcome.value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PermissionDecision":
        _check_version(raw, cls.SCHEMA_VERSION, "PermissionDecision")
        keys = ("request_id", "decider_seat_id", "outcome", "reason")
        _require_exact(raw, keys, "PermissionDecision")
        return cls(
            request_id=raw["request_id"],
            decider_seat_id=raw["decider_seat_id"],
            outcome=PermissionOutcome(raw["outcome"]),
            reason=raw["reason"],
        )


@dataclass(frozen=True)
class WatcherRegistration:
    """A durable cheap watcher; provider/model sessions remain replaceable seat holders."""

    SCHEMA_VERSION: ClassVar[str] = "watcher-registration/1"

    watcher_id: str
    created_by_seat_id: str
    target_seat_id: str
    source_kind: WatchSourceKind
    selector: Mapping[str, Any]
    message_type: str
    one_shot: bool
    poll_interval_seconds: float
    start_cursor: int
    expires_at: str

    def __post_init__(self) -> None:
        for name, value in (
            ("watcher_id", self.watcher_id),
            ("created_by_seat_id", self.created_by_seat_id),
            ("target_seat_id", self.target_seat_id),
            ("message_type", self.message_type),
        ):
            _nonempty(value, name)
        if not self.selector:
            raise StateTransitionRefused("watcher selector cannot be empty")
        if not isinstance(self.one_shot, bool):
            raise StateTransitionRefused("watcher one_shot must be boolean")
        if self.poll_interval_seconds < 0.25:
            raise StateTransitionRefused("watcher polling interval must be at least 0.25s")
        if self.start_cursor < 0:
            raise StateTransitionRefused("watcher start cursor cannot be negative")
        _timestamp(self.expires_at, "expires_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "watcher_id": self.watcher_id,
            "created_by_seat_id": self.created_by_seat_id,
            "target_seat_id": self.target_seat_id,
            "source_kind": self.source_kind.value,
            "selector": dict(self.selector),
            "message_type": self.message_type,
            "one_shot": self.one_shot,
            "poll_interval_seconds": self.poll_interval_seconds,
            "start_cursor": self.start_cursor,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "WatcherRegistration":
        _check_version(raw, cls.SCHEMA_VERSION, "WatcherRegistration")
        keys = (
            "watcher_id",
            "created_by_seat_id",
            "target_seat_id",
            "source_kind",
            "selector",
            "message_type",
            "one_shot",
            "poll_interval_seconds",
            "start_cursor",
            "expires_at",
        )
        _require_exact(raw, keys, "WatcherRegistration")
        return cls(
            watcher_id=raw["watcher_id"],
            created_by_seat_id=raw["created_by_seat_id"],
            target_seat_id=raw["target_seat_id"],
            source_kind=WatchSourceKind(raw["source_kind"]),
            selector=dict(raw["selector"]),
            message_type=raw["message_type"],
            one_shot=raw["one_shot"],
            poll_interval_seconds=float(raw["poll_interval_seconds"]),
            start_cursor=int(raw["start_cursor"]),
            expires_at=raw["expires_at"],
        )


@dataclass(frozen=True)
class WatchCheckpoint:
    SCHEMA_VERSION: ClassVar[str] = "watch-checkpoint/1"

    watcher_id: str
    after_cursor: int
    result_cursor: int
    matched_handles: tuple[str, ...]
    dispatch_message_ids: tuple[str, ...]
    observed_at: str
    status: WatchStatus
    note: str

    def __post_init__(self) -> None:
        _nonempty(self.watcher_id, "watcher_id")
        _nonempty(self.note, "note")
        if self.after_cursor < 0 or self.result_cursor < self.after_cursor:
            raise StateTransitionRefused("watcher checkpoint cursor is not monotonic")
        if len(set(self.matched_handles)) != len(self.matched_handles):
            raise StateTransitionRefused("watcher checkpoint repeats a matched handle")
        if len(set(self.dispatch_message_ids)) != len(self.dispatch_message_ids):
            raise StateTransitionRefused("watcher checkpoint repeats a dispatch message")
        if self.status == WatchStatus.FIRED and not self.matched_handles:
            raise StateTransitionRefused("fired watcher checkpoint requires a match")
        if self.status == WatchStatus.FIRED and not self.dispatch_message_ids:
            raise StateTransitionRefused("fired watcher checkpoint requires a dispatch")
        if self.status != WatchStatus.FIRED and self.dispatch_message_ids:
            raise StateTransitionRefused("only a fired watcher checkpoint may dispatch")
        if self.status == WatchStatus.ARMED and self.matched_handles:
            raise StateTransitionRefused("armed watcher checkpoint cannot hide a match")
        _timestamp(self.observed_at, "observed_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "watcher_id": self.watcher_id,
            "after_cursor": self.after_cursor,
            "result_cursor": self.result_cursor,
            "matched_handles": list(self.matched_handles),
            "dispatch_message_ids": list(self.dispatch_message_ids),
            "observed_at": self.observed_at,
            "status": self.status.value,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "WatchCheckpoint":
        _check_version(raw, cls.SCHEMA_VERSION, "WatchCheckpoint")
        keys = (
            "watcher_id",
            "after_cursor",
            "result_cursor",
            "matched_handles",
            "dispatch_message_ids",
            "observed_at",
            "status",
            "note",
        )
        _require_exact(raw, keys, "WatchCheckpoint")
        return cls(
            watcher_id=raw["watcher_id"],
            after_cursor=int(raw["after_cursor"]),
            result_cursor=int(raw["result_cursor"]),
            matched_handles=tuple(raw["matched_handles"]),
            dispatch_message_ids=tuple(raw["dispatch_message_ids"]),
            observed_at=raw["observed_at"],
            status=WatchStatus(raw["status"]),
            note=raw["note"],
        )


@dataclass(frozen=True)
class ReplEvaluation:
    """Provider-neutral evaluation shape for the persistent Atlas REPL protocol."""

    SCHEMA_VERSION: ClassVar[str] = "repl-evaluation/1"

    evaluation_id: str
    operation: ReplOperation
    input_handles: tuple[str, ...]
    dependency_roots: Mapping[str, str]
    arguments: Mapping[str, Any]
    output_handles: tuple[str, ...]
    branch_id: str
    checkpoint_id: str | None
    read_only: bool = True

    def __post_init__(self) -> None:
        _nonempty(self.evaluation_id, "evaluation_id")
        _nonempty(self.branch_id, "branch_id")
        if not self.input_handles or any(not handle for handle in self.input_handles):
            raise StateTransitionRefused("REPL evaluation must begin from at least one handle")
        if not self.dependency_roots:
            raise StateTransitionRefused("REPL evaluation must bind dependency roots")
        if self.checkpoint_id is not None:
            _nonempty(self.checkpoint_id, "checkpoint_id")
        stateful = {
            ReplOperation.DECLARE_ASSUMPTION,
            ReplOperation.SWITCH_ASSUMPTION,
            ReplOperation.PIN,
            ReplOperation.MATERIALIZE,
            ReplOperation.BRANCH,
            ReplOperation.CHECKPOINT,
            ReplOperation.ACT_PREVIEW,
            ReplOperation.ACT_COMMIT,
            ReplOperation.ACT_ROLLBACK,
        }
        if self.operation in stateful and self.read_only:
            raise StateTransitionRefused("stateful REPL operation cannot claim read-only execution")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "evaluation_id": self.evaluation_id,
            "operation": self.operation.value,
            "input_handles": list(self.input_handles),
            "dependency_roots": dict(self.dependency_roots),
            "arguments": dict(self.arguments),
            "output_handles": list(self.output_handles),
            "branch_id": self.branch_id,
            "checkpoint_id": self.checkpoint_id,
            "read_only": self.read_only,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ReplEvaluation":
        _check_version(raw, cls.SCHEMA_VERSION, "ReplEvaluation")
        keys = (
            "evaluation_id",
            "operation",
            "input_handles",
            "dependency_roots",
            "arguments",
            "output_handles",
            "branch_id",
            "checkpoint_id",
            "read_only",
        )
        _require_exact(raw, keys, "ReplEvaluation")
        return cls(
            evaluation_id=raw["evaluation_id"],
            operation=ReplOperation(raw["operation"]),
            input_handles=tuple(raw["input_handles"]),
            dependency_roots=dict(raw["dependency_roots"]),
            arguments=dict(raw["arguments"]),
            output_handles=tuple(raw["output_handles"]),
            branch_id=raw["branch_id"],
            checkpoint_id=raw["checkpoint_id"],
            read_only=raw["read_only"],
        )


@dataclass(frozen=True)
class MaterializedReconstruction:
    SCHEMA_VERSION: ClassVar[str] = "materialized-reconstruction/1"

    materialization_id: str
    goal: str
    assumption: str
    fibre: str
    retrieval_law: str
    corpus_roots: Mapping[str, str]
    start_handle: str
    movement_ids: tuple[str, ...]
    result_handles: tuple[str, ...]
    dependency_frontier: Mapping[str, str]
    residual: Residual
    coverage: float

    def __post_init__(self) -> None:
        for name, value in (
            ("materialization_id", self.materialization_id),
            ("goal", self.goal),
            ("assumption", self.assumption),
            ("fibre", self.fibre),
            ("retrieval_law", self.retrieval_law),
            ("start_handle", self.start_handle),
        ):
            _nonempty(value, name)
        if not self.corpus_roots or not self.dependency_frontier:
            raise StateTransitionRefused("materialization must bind corpus roots and dependencies")
        if not 0 <= self.coverage <= 1:
            raise StateTransitionRefused("materialization coverage must be between zero and one")

    @property
    def cache_key(self) -> str:
        return chash(
            {
                "goal": self.goal,
                "assumption": self.assumption,
                "fibre": self.fibre,
                "retrieval_law": self.retrieval_law,
                "corpus_roots": dict(sorted(self.corpus_roots.items())),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "materialization_id": self.materialization_id,
            "goal": self.goal,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "retrieval_law": self.retrieval_law,
            "corpus_roots": dict(self.corpus_roots),
            "start_handle": self.start_handle,
            "movement_ids": list(self.movement_ids),
            "result_handles": list(self.result_handles),
            "dependency_frontier": dict(self.dependency_frontier),
            "residual": self.residual.to_dict(),
            "coverage": self.coverage,
            "cache_key": self.cache_key,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MaterializedReconstruction":
        _check_version(raw, cls.SCHEMA_VERSION, "MaterializedReconstruction")
        keys = (
            "materialization_id",
            "goal",
            "assumption",
            "fibre",
            "retrieval_law",
            "corpus_roots",
            "start_handle",
            "movement_ids",
            "result_handles",
            "dependency_frontier",
            "residual",
            "coverage",
            "cache_key",
        )
        _require_exact(raw, keys, "MaterializedReconstruction")
        result = cls(
            materialization_id=raw["materialization_id"],
            goal=raw["goal"],
            assumption=raw["assumption"],
            fibre=raw["fibre"],
            retrieval_law=raw["retrieval_law"],
            corpus_roots=dict(raw["corpus_roots"]),
            start_handle=raw["start_handle"],
            movement_ids=tuple(raw["movement_ids"]),
            result_handles=tuple(raw["result_handles"]),
            dependency_frontier=dict(raw["dependency_frontier"]),
            residual=Residual.from_dict(raw["residual"]),
            coverage=raw["coverage"],
        )
        if raw["cache_key"] != result.cache_key:
            raise StateTransitionRefused("materialization cache key does not verify")
        return result


@dataclass(frozen=True)
class AtlasEvent:
    SCHEMA_VERSION: ClassVar[str] = "atlas-event/1"

    event_id: str
    occurred_at: str
    kind: EventKind
    producer: SeatRole
    actor: SeatRole
    subject: str
    assumption: str | None
    fibre: str | None
    correlation_id: str
    causation_ids: tuple[str, ...]
    provenance: tuple[SourceRef, ...]
    residual: Residual
    runtime: RuntimeReceipt
    producer_ref: ProducerRef
    validity: Validity
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name, value in (
            ("occurred_at", self.occurred_at),
            ("subject", self.subject),
            ("correlation_id", self.correlation_id),
        ):
            _nonempty(value, name)
        if (self.assumption is None) != (self.fibre is None):
            raise StateTransitionRefused("assumption and fibre are declared together")
        if self.assumption is not None:
            _nonempty(self.assumption, "assumption")
            assert self.fibre is not None
            _nonempty(self.fibre, "fibre")
        if not self.provenance:
            raise StateTransitionRefused("every event requires provenance")
        payload_schema = self.payload.get("schema_version")
        if not isinstance(payload_schema, str) or not payload_schema:
            raise StateTransitionRefused("every event payload must be explicitly versioned")
        if len(set(self.causation_ids)) != len(self.causation_ids):
            raise StateTransitionRefused("event causation ledger cannot repeat an event id")
        for cause in self.causation_ids:
            _nonempty(cause, "causation_id")

    def hashed_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "kind": self.kind.value,
            "producer": self.producer.value,
            "actor": self.actor.value,
            "subject": self.subject,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "correlation_id": self.correlation_id,
            "causation_ids": list(self.causation_ids),
            "provenance": [item.to_dict() for item in self.provenance],
            "residual": self.residual.to_dict(),
            "runtime": self.runtime.identity_dict(),
            "producer_ref": self.producer_ref.to_dict(),
            "validity": self.validity.value,
            "payload": dict(self.payload),
        }

    def computed_id(self) -> str:
        return chash(self.hashed_dict())

    def verify_id(self) -> None:
        expected = self.computed_id()
        if self.event_id != expected:
            raise StateTransitionRefused(
                "event id does not match canonical content", expected=expected, got=self.event_id
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "kind": self.kind.value,
            "producer": self.producer.value,
            "actor": self.actor.value,
            "subject": self.subject,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "correlation_id": self.correlation_id,
            "causation_ids": list(self.causation_ids),
            "provenance": [item.to_dict() for item in self.provenance],
            "residual": self.residual.to_dict(),
            "runtime": self.runtime.to_dict(),
            "producer_ref": self.producer_ref.to_dict(),
            "validity": self.validity.value,
            "payload": dict(self.payload),
        }

    @classmethod
    def create(cls, **fields: Any) -> "AtlasEvent":
        draft = cls(event_id="", **fields)
        return replace(draft, event_id=draft.computed_id())

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AtlasEvent":
        _check_version(raw, cls.SCHEMA_VERSION, "AtlasEvent")
        keys = (
            "event_id",
            "occurred_at",
            "kind",
            "producer",
            "actor",
            "subject",
            "assumption",
            "fibre",
            "correlation_id",
            "causation_ids",
            "provenance",
            "residual",
            "runtime",
            "producer_ref",
            "validity",
            "payload",
        )
        _require_exact(raw, keys, "AtlasEvent")
        event = cls(
            event_id=raw["event_id"],
            occurred_at=raw["occurred_at"],
            kind=EventKind(raw["kind"]),
            producer=SeatRole(raw["producer"]),
            actor=SeatRole(raw["actor"]),
            subject=raw["subject"],
            assumption=raw["assumption"],
            fibre=raw["fibre"],
            correlation_id=raw["correlation_id"],
            causation_ids=tuple(raw["causation_ids"]),
            provenance=tuple(SourceRef.from_dict(item) for item in raw["provenance"]),
            residual=Residual.from_dict(raw["residual"]),
            runtime=RuntimeReceipt.from_dict(raw["runtime"]),
            producer_ref=ProducerRef.from_dict(raw["producer_ref"]),
            validity=Validity(raw["validity"]),
            payload=dict(raw["payload"]),
        )
        event.verify_id()
        return event
