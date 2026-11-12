"""One typed read descent for every stable handle the engine serves.

Routing and resolution are deliberately separate.  A semantic or spectral router may choose a
handle, but it is not allowed to reinterpret that handle when the reader descends.  ``kind`` is
therefore mandatory: a sha256 body handle, a blueprint content version, and a source digest can
have the same lexical shape without having the same resolver or authority.

This module is a registry over existing canonical readers.  Resolution remains read-only over its
source and makes no open/closed/delivered judgement.  Each call and return now emit the already-
declared ``reconstruction.moved`` / ``reconstruction.materialized`` pair into the canonical Atlas;
that append-only observation is exposed in the result and never hidden as a source transition.
Compatibility verbs delegate here; they are not additional resolution paths.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Callable

from laplace.representation import atlas_bridge
from laplace.engine import rows, sources
from laplace.manuscript import source_anchor
from laplace.pipeline.canon import get_canon

SCHEMA = "laplace.typed-descent/1"
CONTENT_SCHEMA = "laplace.bounded-content/1"
DEFAULT_CONTENT_BUDGET = 12_000
KINDS = (
    "atlas-custody",
    "atlas-object",
    "blueprint",
    "campaign-stage",
    "canon",
    "fabric-message",
    "ledger-row",
    "repository-file",
    "session-memory",
    "semantic-fold-object",
    "source-anchor",
    "source-contract",
    "current-publication-object",
    "canonical-work",
)

_PATH_SUFFIXES = frozenset({
    ".c", ".cc", ".cpp", ".css", ".csv", ".go", ".h", ".html", ".java",
    ".js", ".json", ".jsonl", ".md", ".mjs", ".py", ".rs", ".sh", ".svg",
    ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
})
_ATLAS_OBJECT_PREFIXES = frozenset({
    "acknowledgement", "boundary", "content", "context", "event",
    "filesystem-observation", "join", "lease", "message-migration-supersession",
    "message-preserve-fork", "message-supersession", "reconstruction", "region",
    "region-lease", "representation", "revision-act", "revision-node", "seat",
    "session", "source", "subscription", "watch-checkpoint", "watcher",
})


class DescentRefused(ValueError):
    """The requested typed reference did not resolve exactly."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.details = details


def refusal_result(kind: str, reference: str, exc: DescentRefused) -> dict[str, Any]:
    """Structured public form of a typed refusal, shared by CLI and MCP."""
    return {
        "schema_version": SCHEMA,
        "kind": kind,
        "reference": reference,
        "refused": True,
        "error": str(exc),
        **exc.details,
    }


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def normalize_target(
    reference: str,
    *,
    explicit_kind: str | None = None,
    source: str = "",
    fold: str = "",
) -> dict[str, str] | None:
    """One exact target grammar shared by CLI, turns, profiles and dispatch.

    Bare hashes deliberately remain ambiguous.  Semantic-fold handles require the stable outer
    kind plus their exact fold receipt; located records retain their own declared inner kind.
    """

    raw = str(reference or "").strip()
    if not raw:
        return None
    if explicit_kind:
        kind = str(explicit_kind).strip()
        if kind not in KINDS:
            raise DescentRefused(f"unknown descent kind {kind!r}")
        if kind == "semantic-fold-object" and not str(fold).startswith("sha256:"):
            raise DescentRefused("semantic-fold-object requires an exact fold receipt handle")
        return {"kind": kind, "reference": raw, "source": str(source or ""), "fold": str(fold or "")}
    if raw.startswith("memory://"):
        kind, resolved_source = "session-memory", ""
    elif raw.startswith("work://"):
        # namespace-qualified canonical Work only; a bare WORK- id stays unresolved (never a WO row or kernel node)
        kind, resolved_source = "canonical-work", ""
    elif raw.startswith("WO-"):
        kind, resolved_source = "ledger-row", "work_orders"
    elif raw.startswith(("ATLAS-", "CAMP-")):
        kind, resolved_source = "campaign-stage", ""
    elif raw.startswith("M-"):
        kind, resolved_source = "ledger-row", "methods"
    elif raw.startswith("PRM-"):
        kind, resolved_source = "ledger-row", "promises"
    elif raw.startswith(("TALK-", "ROUTED-", "REPLY-", "BIND-")):
        kind, resolved_source = "ledger-row", "talk"
    elif raw.startswith(("INV-", "s0inv-")):
        kind, resolved_source = "ledger-row", "atlas_inventory"
    elif raw.startswith("OP-") or raw.startswith("operational://"):
        kind, resolved_source = "ledger-row", "semantic_operational_sources"
    elif raw.startswith("message:"):
        kind, resolved_source = "fabric-message", ""
    elif raw.startswith("canon://"):
        kind, resolved_source = "canon", ""
    elif raw.startswith(("design-clause:", "design-subject:", "design:")):
        kind, resolved_source = "blueprint", ""
    else:
        prefix, separator, suffix = raw.partition(":")
        path = Path(raw)
        if separator and prefix in _ATLAS_OBJECT_PREFIXES and suffix and not any(
            character.isspace() for character in raw
        ):
            kind, resolved_source = "atlas-object", ""
        elif (
            not raw.startswith(("canon://", "message:"))
            and (
                path.is_absolute() or "/" in raw or "\\" in raw or raw.startswith(".")
                or path.suffix.lower() in _PATH_SUFFIXES
            )
        ):
            kind, resolved_source = "repository-file", ""
        else:
            return None
    return {"kind": kind, "reference": raw, "source": resolved_source, "fold": ""}


def _is_textual(media_type: str) -> bool:
    bare = media_type.split(";", 1)[0].strip().lower()
    return bare.startswith("text/") or bare in {
        "application/json",
        "application/jsonl",
        "application/ld+json",
        "application/xml",
        "application/yaml",
    }


def _bounded_projection(
    *,
    handle: str,
    content_handle: str,
    media_type: str,
    total_bytes: int,
    chunk: bytes,
    offset: int,
    budget: int,
) -> dict[str, Any]:
    """Project one exact byte object under a caller-declared response budget.

    The handle always names the whole object.  ``content`` is merely the current bounded
    window; every byte outside it is counted, and ``content_next_offset`` is an exact
    continuation rather than a fresh routing decision.  UTF-8 windows end only at a code-point
    boundary so concatenating successive windows recovers the original text exactly.
    """

    if offset < 0 or offset > total_bytes:
        raise DescentRefused(
            "content offset is outside the exact object",
            residue={
                "schema_version": "laplace.engine.descent-residue/1",
                "code": "OFFSET",
                "offset": offset,
                "content_bytes": total_bytes,
            },
        )
    before = offset
    if total_bytes == 0:
        return {
            "schema_version": CONTENT_SCHEMA,
            "handle": handle,
            "content": "",
            "content_status": "COMPLETE",
            "content_truncated": False,
            "content_omitted": 0,
            "content_omitted_before": 0,
            "content_omitted_after": 0,
            "content_offset": 0,
            "content_next_offset": None,
            "content_bytes": 0,
            "content_budget": budget,
            "content_handle": content_handle,
            "content_encoding": "utf-8" if _is_textual(media_type) else "base64",
        }
    if budget <= 0:
        return {
            "schema_version": CONTENT_SCHEMA,
            "handle": handle,
            "content": None,
            "content_status": "BUDGET",
            "content_truncated": True,
            "content_omitted": total_bytes,
            "content_omitted_before": before,
            "content_omitted_after": total_bytes - before,
            "content_offset": offset,
            "content_next_offset": offset,
            "content_bytes": total_bytes,
            "content_budget": budget,
            "content_handle": content_handle,
            "content_encoding": "utf-8" if _is_textual(media_type) else "base64",
            "content_residue": {
                "schema_version": "laplace.engine.descent-residue/1",
                "code": "BUDGET",
                "required_bytes": total_bytes - offset,
                "available_bytes": max(0, budget),
                "content_handle": content_handle,
            },
        }

    if not _is_textual(media_type) and not chunk and offset < total_bytes:
        return {
            "schema_version": CONTENT_SCHEMA,
            "handle": handle,
            "content": None,
            "content_status": "BUDGET",
            "content_truncated": True,
            "content_omitted": total_bytes,
            "content_omitted_before": before,
            "content_omitted_after": total_bytes - before,
            "content_offset": offset,
            "content_next_offset": offset,
            "content_bytes": total_bytes,
            "content_budget": budget,
            "content_handle": content_handle,
            "content_encoding": "base64",
            "content_residue": {
                "schema_version": "laplace.engine.descent-residue/1",
                "code": "BUDGET",
                "required_bytes": 4,
                "available_bytes": budget,
                "content_handle": content_handle,
                "why": "a binary content quantum needs four base64 response bytes",
            },
        }

    consumed = len(chunk)
    encoding = "base64"
    if _is_textual(media_type):
        try:
            content = chunk.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError as exc:
            # A bounded prefix may stop inside the final code point.  Cut at that exact
            # boundary and continue there next time; malformed content or a caller-chosen
            # mid-codepoint offset remains a typed refusal, never replacement characters.
            if exc.reason == "unexpected end of data" and exc.end == len(chunk):
                chunk = chunk[: exc.start]
                consumed = len(chunk)
                if not chunk:
                    return {
                        "schema_version": CONTENT_SCHEMA,
                        "handle": handle,
                        "content": None,
                        "content_status": "BUDGET",
                        "content_truncated": True,
                        "content_omitted": total_bytes,
                        "content_omitted_before": before,
                        "content_omitted_after": total_bytes - before,
                        "content_offset": offset,
                        "content_next_offset": offset,
                        "content_bytes": total_bytes,
                        "content_budget": budget,
                        "content_handle": content_handle,
                        "content_encoding": "utf-8",
                        "content_residue": {
                            "schema_version": "laplace.engine.descent-residue/1",
                            "code": "BUDGET",
                            "required_bytes": exc.end - exc.start,
                            "available_bytes": budget,
                            "content_handle": content_handle,
                        },
                    }
                content = chunk.decode("utf-8")
                encoding = "utf-8"
            else:
                raise DescentRefused(
                    "text content is not valid UTF-8 at the requested offset",
                    residue={
                        "schema_version": "laplace.engine.descent-residue/1",
                        "code": "CONTENT_INVALID",
                        "offset": offset,
                        "error_byte": offset + exc.start,
                    },
                ) from exc
    else:
        import base64

        content = base64.b64encode(chunk).decode("ascii")

    after = max(0, total_bytes - (offset + consumed))
    omitted = before + after
    if not omitted:
        status = "COMPLETE"
    elif after:
        status = "TRUNCATED"
    else:
        # This window reaches EOF but begins after byte zero.  Naming it TRUNCATED made
        # ``content_truncated`` mean both "a continuation exists" and "this is not the
        # whole object"; the obvious continuation loop then received True beside a null
        # next offset.  FINAL names the terminal partial window while omitted_before
        # preserves the exact prefix residue.
        status = "FINAL"
    return {
        "schema_version": CONTENT_SCHEMA,
        "handle": handle,
        "content": content,
        "content_status": status,
        "content_truncated": bool(after),
        "content_omitted": omitted,
        "content_omitted_before": before,
        "content_omitted_after": after,
        "content_offset": offset,
        "content_next_offset": offset + consumed if after else None,
        "content_bytes": total_bytes,
        "content_budget": budget,
        "content_handle": content_handle,
        "content_encoding": encoding,
    }


def bounded_content(
    *,
    handle: str,
    content: bytes | str,
    content_handle: str = "",
    media_type: str = "text/plain; charset=utf-8",
    budget: int = DEFAULT_CONTENT_BUDGET,
    offset: int = 0,
) -> dict[str, Any]:
    """Bound in-memory content with the same public contract used by file descent."""

    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    calculated = _sha256(raw)
    if content_handle and content_handle != calculated:
        raise DescentRefused(
            "supplied content handle does not name the exact bytes",
            residue={
                "schema_version": "laplace.engine.descent-residue/1",
                "code": "CONTENT_HANDLE_MISMATCH",
                "supplied_handle": content_handle,
                "calculated_handle": calculated,
            },
        )
    digest = content_handle or calculated
    raw_budget = budget if _is_textual(media_type) else (budget // 4) * 3
    chunk = raw[offset : offset + max(0, raw_budget)] if budget > 0 else b""
    return _bounded_projection(
        handle=handle,
        content_handle=digest,
        media_type=media_type,
        total_bytes=len(raw),
        chunk=chunk,
        offset=offset,
        budget=budget,
    )


def bounded_file_content(
    *,
    repo_root: Path | str,
    reference: str,
    budget: int = DEFAULT_CONTENT_BUDGET,
    offset: int = 0,
) -> dict[str, Any]:
    """Serve a repository file without loading an arbitrary-size object into memory."""

    root = Path(repo_root).resolve()
    path = (root / reference).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DescentRefused(
            "source path escapes the repository root",
            residue={"schema_version": "laplace.engine.descent-residue/1", "code": "SOURCE_REFUSED"},
        ) from exc
    if not path.is_file():
        raise DescentRefused(
            "source file does not resolve exactly",
            residue={"schema_version": "laplace.engine.descent-residue/1", "code": "NOT_FOUND"},
        )
    guessed, _encoding = mimetypes.guess_type(path.name)
    if path.suffix.lower() in {
        ".c",
        ".cc",
        ".cpp",
        ".css",
        ".csv",
        ".go",
        ".h",
        ".html",
        ".java",
        ".js",
        ".json",
        ".jsonl",
        ".md",
        ".mjs",
        ".py",
        ".rs",
        ".sh",
        ".svg",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }:
        media_type = guessed or "text/plain"
        if not media_type.startswith("text/") and media_type not in {
            "application/json",
            "application/xml",
        }:
            media_type = "text/plain"
        media_type += "; charset=utf-8"
    else:
        media_type = guessed or "application/octet-stream"
    raw_budget = budget if _is_textual(media_type) else (budget // 4) * 3

    digest = hashlib.sha256()
    with path.open("rb") as source_handle:
        while block := source_handle.read(1024 * 1024):
            digest.update(block)
        total = source_handle.tell()
        if offset < 0 or offset > total:
            chunk = b""
        else:
            source_handle.seek(offset)
            chunk = source_handle.read(max(0, raw_budget)) if budget > 0 else b""
    return {
        **_bounded_projection(
            handle=reference,
            content_handle="sha256:" + digest.hexdigest(),
            media_type=media_type,
            total_bytes=total,
            chunk=chunk,
            offset=offset,
            budget=budget,
        ),
        "media_type": media_type,
        "provenance": {"path": reference},
    }


def _base(
    kind: str,
    reference: str,
    value: Any,
    *,
    content_bytes: bytes,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "kind": kind,
        "reference": reference,
        "value": value,
        "read_only": True,
        "transition_claim": "none",
        "_content_bytes": content_bytes,
        **fields,
    }


def _canon(reference: str, _source: str) -> dict[str, Any]:
    ref = reference if reference.startswith("canon://") else f"canon://{reference}"
    try:
        path, content = get_canon().resolve(ref)
    except Exception as exc:  # the public door has one refusal vocabulary
        raise DescentRefused(f"canon reference does not resolve exactly: {reference}") from exc
    data = content.encode("utf-8")
    return _base(
        "canon",
        reference,
        content,
        content_bytes=data,
        content_handle=_sha256(data),
        media_type="text/markdown; charset=utf-8",
        provenance={"path": str(path)},
    )


def _fabric_message(reference: str, _source: str) -> dict[str, Any]:
    if not reference.startswith("message:"):
        raise DescentRefused("fabric-message references must start with 'message:'")
    result = atlas_bridge.message_body(message_id=reference)
    return _base(
        "fabric-message",
        reference,
        result["body"],
        content_bytes=result["body"].encode("utf-8"),
        content_handle=result["body_handle"],
        media_type=result.get("media_type", "text/plain; charset=utf-8"),
        provenance={"message_id": reference},
        storage_access=result.get("storage_access"),
        transition_claim=result.get("delivery_claim", "none"),
    )


def _atlas_custody(reference: str, _source: str) -> dict[str, Any]:
    result = atlas_bridge.custody_body(handle=reference)
    value = result.get("text")
    if value is None:
        value = {"base64": result["base64"]}
        import base64

        content_bytes = base64.b64decode(result["base64"])
    else:
        content_bytes = value.encode("utf-8")
    return _base(
        "atlas-custody",
        reference,
        value,
        content_bytes=content_bytes,
        content_handle=result["content_handle"],
        media_type=result["media_type"],
        provenance={"store": result["store"]},
    )


def _atlas_object_refusal_code(exc: Exception) -> str:
    detail = getattr(exc, "detail", {})
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        return detail["code"]
    message = str(exc).casefold()
    if "bounded verification window" in message:
        return "AUTHORITY_SUFFIX_LIMIT"
    if "moved" in message or "stale" in message or "fork" in message:
        return "MOVED"
    if "ambiguous" in message:
        return "AMBIGUOUS"
    if any(word in message for word in ("dirty", "corrupt", "digest", "contradict")):
        return "DIRTY"
    if "does not resolve" in message or "not found" in message or "absent" in message:
        return "NOT_FOUND"
    return "UNAVAILABLE"


def _atlas_object(reference: str, _source: str) -> dict[str, Any]:
    try:
        result = atlas_bridge.atlas_object(reference=reference)
    except Exception as exc:  # noqa: BLE001 - bridge owns the Atlas refusal hierarchy
        code = _atlas_object_refusal_code(exc)
        raise DescentRefused(
            "Atlas object does not resolve through current keyed authority",
            residue={
                "schema_version": "laplace.engine.descent-residue/1",
                "code": code,
                "reference": reference,
                "cause": str(exc),
            },
        ) from exc
    return _base(
        "atlas-object",
        reference,
        result["value"],
        content_bytes=result["content"].encode("utf-8"),
        content_handle=result["content_handle"],
        media_type=result["media_type"],
        provenance=result["provenance"],
        current_root=result["current_root"],
        current_root_components=result["current_root_components"],
        authority_root=result["authority_root"],
        authority_root_kind=result["authority_root_kind"],
        drift_token=result["drift_token"],
        current=result["current"],
        clean=result["clean"],
        authenticated=result["authenticated"],
        integrity_boundary=result["integrity_boundary"],
        authority_suffix_count=result["authority_suffix_count"],
        authority_suffix_limit=result["authority_suffix_limit"],
        read_metrics=result["read_metrics"],
        fidelity_boundary=result["fidelity_boundary"],
        storage_access="CURRENT C2a checkpoint plus one exact keyed row; no lifetime replay",
    )


def _blueprint(reference: str, _source: str) -> dict[str, Any]:
    result = atlas_bridge.blueprint_descent(reference=reference)
    moved = list(result.get("moved_source_roots") or [])
    # The selected completion owns its banked bytes. Worktree movement is advisory
    # for this read, as in atlas.blueprint; it never promotes them to the newer source.
    moved_encoded = json.dumps(
        moved, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    generation_current = result.get("generation_current") is True and not moved
    moved_fields = {
        "generation_current": generation_current,
        "source_currency": "CURRENT" if generation_current else "MOVED",
        "content_basis": result.get("content_basis", "completed-generation-banked-bytes"),
        "moved_source_root_count": len(moved),
        "moved_source_roots": moved[:24],
        "moved_source_roots_truncated": len(moved) > 24,
        "moved_source_roots_omitted": max(0, len(moved) - 24),
        "moved_source_roots_handle": _sha256(moved_encoded),
        "storage_access": result.get("storage_access"),
    }
    return _base(
        "blueprint",
        reference,
        result,
        content_bytes=str(result.get("text") or "").encode("utf-8"),
        # The Atlas content handle names the source object envelope. The public
        # byte-descent handle must name the returned text, a different identity.
        content_handle=_sha256(str(result.get("text") or "").encode("utf-8")),
        media_type="text/markdown; charset=utf-8",
        provenance={
            "generation_id": result["generation_id"],
            "object_content_handle": result["clause"]["content_handle"],
            "source_path": result["clause"]["source_path"],
            "source_hash": result["clause"]["source_hash"],
            "start": result["clause"]["start"],
            "end": result["clause"]["end"],
        },
        **moved_fields,
    )


def _row_from_source(
    reference: str,
    source: str,
    *,
    identity_field: str,
    kind: str,
) -> dict[str, Any]:
    spec = sources.get(source)
    if spec is None or not spec.get("scan"):
        raise DescentRefused(f"{kind} requires a scanned registered source")
    found = rows.find_by_field(source, identity_field, reference)
    if found is None:
        raise DescentRefused(f"{kind} does not resolve exactly: {source}/{reference}")
    offset, row = found
    path = Path(spec["abspath"])
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            raw = handle.readline()
    except OSError as exc:
        raise DescentRefused(f"ledger source became unreadable: {source}") from exc
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise DescentRefused("ledger row moved or became malformed during descent") from exc
    if parsed != row or str(row.get(identity_field, "")) != reference:
        raise DescentRefused(f"{kind} identity changed during descent")
    return _base(
        kind,
        reference,
        row,
        content_bytes=raw,
        content_handle=_sha256(raw),
        media_type="application/json",
        provenance={
            "source": source,
            "path": spec["path"],
            "byte_offset": offset,
            "byte_length": len(raw),
            "id_field": identity_field,
        },
        semantic_state_claim="none; consumers use the source's canonical projection",
    )


def _ledger_row(reference: str, source: str) -> dict[str, Any]:
    spec = sources.get(source)
    if spec is None or not spec.get("scan") or not spec.get("id_field"):
        raise DescentRefused("ledger-row requires a scanned registered source with an id field")
    return _row_from_source(
        reference,
        source,
        identity_field=str(spec["id_field"]),
        kind="ledger-row",
    )


def _campaign_stage(reference: str, _source: str) -> dict[str, Any]:
    """Resolve a stage definition by its stable ID, never a later gate row's stage field."""

    return _row_from_source(
        reference,
        "campaign",
        identity_field="id",
        kind="campaign-stage",
    )


def _source_anchor(reference: str, _source: str) -> dict[str, Any]:
    repo = source_tree()
    try:
        path, start, end = source_anchor.resolve(reference, repo)
        lines = source_anchor.read_lines(repo, path)
    except source_anchor.AnchorError as exc:
        raise DescentRefused(str(exc)) from exc
    text = "\n".join(lines[start - 1 : end])
    data = text.encode("utf-8")
    return _base(
        "source-anchor",
        reference,
        text,
        content_bytes=data,
        content_handle=_sha256(data),
        media_type="text/plain; charset=utf-8",
        provenance={"path": path, "line_start": start, "line_end": end},
    )


def _repository_file(reference: str, _source: str) -> dict[str, Any]:
    """Resolve one repository-relative path without consulting semantic geometry.

    ``descend`` materialises the bounded content window separately so an arbitrarily large exact
    source is not loaded merely to prove its identity.
    """

    repo = source_tree()
    if Path(reference).is_absolute():
        raise DescentRefused(
            "repository-file references must be repository-relative",
            residue={"schema_version": "laplace.engine.descent-residue/1", "code": "SOURCE_REFUSED"},
        )
    path = (repo / reference).resolve()
    try:
        path.relative_to(repo.resolve())
    except ValueError as exc:
        raise DescentRefused(
            "source path escapes the repository root",
            residue={"schema_version": "laplace.engine.descent-residue/1", "code": "SOURCE_REFUSED"},
        ) from exc
    if not path.is_file():
        raise DescentRefused(
            "repository file does not resolve exactly",
            residue={"schema_version": "laplace.engine.descent-residue/1", "code": "NOT_FOUND"},
        )
    return {
        "schema_version": SCHEMA,
        "kind": "repository-file",
        "reference": reference,
        # Compatibility with the pre-typed semantic source face.  Exact path routing is now
        # authoritative, but callers that rendered the old content-bearing grade-one result do
        # not need to guess that the returned object changed shape.
        "handle": reference,
        "target_grade": 1,
        "value": {"path": reference},
        "read_only": True,
        "transition_claim": "none",
        "provenance": {"path": reference, "resolution_mode": "exact-repository-file"},
    }


def _semantic_fold_object(reference: str, fold: str) -> dict[str, Any]:
    """Locate an exact accepted-fold object; its declared inner route supplies leaf bytes."""

    if not reference.startswith("sha256:") or not fold.startswith("sha256:"):
        raise DescentRefused(
            "semantic-fold-object requires exact object and fold receipt handles"
        )
    try:
        from laplace.representation.embedding_health import semantic_fold_down

        down = semantic_fold_down(
            source_tree(),
            semantic_handle=reference,
            receipt_handle=fold,
        )
    except Exception as exc:  # noqa: BLE001 - fold verifier owns the exact refusal details
        raise DescentRefused(
            "semantic fold object does not resolve exactly",
            residue={
                "schema_version": "laplace.engine.descent-residue/1",
                "code": "SEMANTIC_FOLD_REFUSED",
                "reference": reference,
                "fold": fold,
                "cause": f"{type(exc).__name__}: {exc}",
            },
        ) from exc
    selected = down["selected"]
    return {
        "schema_version": SCHEMA,
        "kind": "semantic-fold-object",
        "reference": reference,
        "fold_receipt_handle": fold,
        "semantic_down": down,
        "value": selected,
        "read_only": True,
        "transition_claim": "none",
        "provenance": {
            "fold_receipt_handle": fold,
            "descent_index_handle": down["index_handle"],
            "register_generation": down["register_generation"],
        },
        "_located": selected,
    }


def _current_publication_object(reference: str, source: str, *, scope=None) -> dict[str, Any]:
    from laplace.representation import source_publication
    from laplace.work import owner_discovery
    try:
        if source:raise ValueError('Current publication uses actual Scope, never a source-string override.')
        target=json.loads(reference)
        if not isinstance(target,dict) or len(reference)>32768:raise ValueError('Invalid current publication target.')
        actual=scope or owner_discovery.owned_workspace('engine-descent')
        value=source_publication.request(source_tree(),actual,{**target,'action':'object'})
        raw=source_publication.canonical_bytes(value['facts'])
        return _base('current-publication-object',reference,value['facts'],content_bytes=raw,
            content_handle=value['content_handle'],media_type='application/json',
            provenance={'scope':actual.public(),'publication':value['publication']},transition_claim='none')
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as exc:
        raise DescentRefused('Exact active publication object is unavailable') from exc


def _source_contract(reference: str, source: str, *, scope=None) -> dict[str, Any]:
    from laplace.work import source_kernel, owner_discovery
    try:
        target=json.loads(reference)
        actual=scope or owner_discovery.owned_workspace('engine-descent')
        if source:raise ValueError('Source-contract descent uses the actual supplied scope, never a source-string scope override.')
        value=source_kernel.descend(source_tree(),actual,target)
        raw=source_kernel.identity.canonical_bytes(value)
        return _base('source-contract',reference,value,content_bytes=raw,content_handle=_sha256(raw),media_type='application/json',
                     provenance={'scope':actual.public(),'retained_source_contract':target['reference']},transition_claim='none')
    except (ValueError,OSError,KeyError,TypeError) as exc:
        raise DescentRefused('Exact retained Source-contract meaning is unavailable') from exc


def _session_memory(reference: str, _source: str) -> dict[str, Any]:
    from laplace.engine.session_memory import get_entry
    root = source_tree()
    key = reference.removeprefix("memory://")
    try:
        entry, state = get_entry(root, key)
    except KeyError as exc:
        raise DescentRefused("session memory record does not exist", reference=reference) from exc
    source_text = entry["kind"] == "historical-source"
    raw = entry["text"].encode() if source_text else json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    extra: dict[str, Any] = {}
    if entry.get("kind") == "procedure" and entry.get("programme") is not None:
        from laplace.engine.session_memory import programme_uri
        try:
            # the typed next descent of an authored programme coordinate: the Work owner, not a cached copy of it
            extra["programme_descent"] = {"kind": "canonical-work", "reference": programme_uri(entry["programme"])}
        except ValueError as exc:
            extra["programme_refused"] = str(exc)
    return _base("session-memory", reference, entry, content_bytes=raw,
                 content_handle=_sha256(raw), media_type="text/markdown" if source_text else "application/json",
                 provenance={"ledger": state["ledger"], "record": entry["record"],
                             "version": entry["version"], "memory_generation": state["generation"], "read_cost": state["read_cost"]},
                 **extra)


def _work_target(reference: str) -> tuple[dict, dict]:
    """``work://<namespace>/<work_id>`` or ``{"work": "work://...", "request": {...}}`` to (coordinate, request)."""
    from laplace.engine.session_memory import parse_work_uri
    raw, request = reference, {"part": "summary"}
    if raw.startswith("{"):
        if len(raw) > 32768:
            raise ValueError("canonical Work target exceeds 32768 characters")
        target = json.loads(raw)
        if not isinstance(target, dict) or "work" not in target or set(target) - {"work", "request"}:
            raise ValueError("a canonical Work target is {work: work://<namespace>/<work_id>, request?}")
        raw = target["work"]
        if "request" in target:
            if not isinstance(target["request"], dict):
                raise ValueError("a canonical Work request is the continuity view's request object")
            request = target["request"]
    return parse_work_uri(raw), request


def work_continuity(root: Path | str, scope, reference: str) -> tuple[dict, dict]:
    """THE delegated canonical-Work continuity read shared by descent, wake and the SDK programme entry.

    The Work owner (project_work_views.read view continuity) admits the caller's actual Scope before any lookup;
    this adapter adds no rule, cache or action of its own.
    """
    from laplace.work import project_work_views
    coordinate, request = _work_target(str(reference))
    value = project_work_views.read(coordinate["namespace"], {"view": "continuity", "id": coordinate["work_id"], "request": request},
                                    root, mode="human", native_caller=scope)
    return coordinate, value


def _canonical_work(reference: str, source: str, *, scope=None) -> dict[str, Any]:
    from laplace.work import owner_discovery
    residue = {"schema_version": "laplace.engine.descent-residue/1", "reference": reference[:400]}
    if source:
        raise DescentRefused("Canonical Work descent uses the actual supplied Scope, never a source-string override",
                             residue={**residue, "code": "SOURCE_REFUSED"})
    try:
        coordinate, _request = _work_target(reference)
    except (ValueError, TypeError) as exc:
        raise DescentRefused("canonical Work reference is malformed", residue={**residue, "code": "MALFORMED", "cause": str(exc)[:400]}) from exc
    # No default authority: the caller's actual Scope is explicit, and this adapter refuses a foreign namespace itself
    # before the Work owner (which admits Scope again) is asked anything.
    if scope is None:
        raise DescentRefused("canonical-work descent requires the caller's explicit actual Scope",
                             residue={**residue, "code": "SCOPE_REQUIRED"})
    if not isinstance(scope, owner_discovery.Scope) or not scope.admits(coordinate["namespace"]):
        raise DescentRefused("Exact canonical Work continuity is outside the caller's actual Scope",
                             residue={**residue, "code": "SCOPE_REFUSED"})
    actual = scope
    try:
        coordinate, value = work_continuity(source_tree(), actual, reference)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        message = str(exc)
        lowered = message.casefold()
        details = getattr(exc, "details", None)
        # Scope is classified above from the typed Scope; a typed owner conflict keeps its own code. The remaining owner
        # refusals are plain ValueErrors whose absent-identity wording is the only distinction the owner exposes today.
        code = ("CHANGED" if isinstance(details, dict) and details.get("field") else
                "NOT_FOUND" if "unavailable" in lowered or "not recorded" in lowered else "REFUSED")
        follow = details.get("next_reads") if isinstance(details, dict) else None
        raise DescentRefused("Exact canonical Work continuity is unavailable",
                             residue={**residue, "code": code, "cause": message[:400], **({"next_reads": follow} if follow else {})}) from exc
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return _base("canonical-work", reference, value, content_bytes=raw, content_handle=_sha256(raw), media_type="application/json",
                 provenance={"scope": actual.public(), "work": coordinate, "owner": "laplace.work.project_work_continuity.read",
                             "view": "continuity"},
                 transition_claim="none",
                 semantic_state_claim="none; issued actions are offered options revalidated by their effect owner")



_REGISTRY: dict[str, Callable[[str, str], dict[str, Any]]] = {
    "atlas-custody": _atlas_custody,
    "atlas-object": _atlas_object,
    "blueprint": _blueprint,
    "campaign-stage": _campaign_stage,
    "canon": _canon,
    "fabric-message": _fabric_message,
    "ledger-row": _ledger_row,
    "repository-file": _repository_file,
    "session-memory": _session_memory,
    "semantic-fold-object": _semantic_fold_object,
    "source-anchor": _source_anchor,
    "source-contract": _source_contract,
    "current-publication-object": _current_publication_object,
    "canonical-work": _canonical_work,
}


def descend(
    *,
    kind: str,
    reference: str,
    source: str = "",
    fold: str = "",
    goal: str = "",
    seat_id: str = "",
    provider: str = "",
    model: str = "",
    correlation_id: str = "",
    content_budget: int = DEFAULT_CONTENT_BUDGET,
    content_offset: int = 0,
    record_telemetry: bool = False,
    read_scope=None,
) -> dict[str, Any]:
    """Resolve one typed reference, optionally banking causal call/return telemetry.

    Every successful read carries a bounded exact content window.  A caller can continue the
    same object with ``content_next_offset``; it never has to route again or accept a handle-only
    success.  A zero budget returns a typed BUDGET residue rather than silently dropping content.
    """

    resolver = _REGISTRY.get(str(kind).strip())
    if resolver is None:
        raise DescentRefused(f"unknown descent kind {kind!r}; choose one of {', '.join(KINDS)}")
    ref = str(reference).strip()
    if not ref:
        raise DescentRefused("descent reference is empty")
    src = str(source).strip()
    fold_handle = str(fold).strip()
    resolver_source = fold_handle if str(kind).strip() == "semantic-fold-object" else src
    if not record_telemetry:
        trace = {
            "schema_version": "laplace.engine.descent-trace/1",
            "status": "NOT_REQUESTED",
            "authority_write": "none",
        }
    else:
        try:
            trace = atlas_bridge.begin_typed_descent(
                kind=str(kind).strip(),
                reference=ref,
                source=src,
                goal=goal,
                seat_id=seat_id,
                provider=provider,
                model=model,
                correlation_id=correlation_id,
            )
        except Exception as exc:  # noqa: BLE001 - a read survives, but names dark telemetry
            trace = {
                "schema_version": "laplace.engine.descent-trace/1",
                "status": "UNAVAILABLE",
                "error": f"{type(exc).__name__}: {exc}",
            }
    try:
        result = (resolver(ref, resolver_source, scope=read_scope) if kind in {"source-contract","current-publication-object","canonical-work"} else resolver(ref, resolver_source))
        if str(kind).strip() == "repository-file":
            projection = bounded_file_content(
                repo_root=source_tree(),
                reference=ref,
                budget=int(content_budget),
                offset=int(content_offset),
            )
            projection["provenance"] = {
                **(result.get("provenance") or {}),
                **(projection.get("provenance") or {}),
            }
        elif str(kind).strip() == "semantic-fold-object":
            located = result.pop("_located")
            route = located.get("exact_descent")
            if located.get("kind") == "leaf":
                if not isinstance(route, dict):
                    raise DescentRefused(
                        "semantic fold leaf has no declared exact reconstruction route"
                    )
                nested = descend(
                    kind=str(route["kind"]),
                    reference=str(route["reference"]),
                    source=str(route.get("source") or ""),
                    fold=str(route.get("fold") or ""),
                    goal=goal,
                    seat_id=seat_id,
                    provider=provider,
                    model=model,
                    correlation_id=correlation_id,
                    content_budget=int(content_budget),
                    content_offset=int(content_offset),
                    record_telemetry=False,
                )
                projection = {
                    key: nested.get(key)
                    for key in (
                        "content", "content_status", "content_truncated", "content_omitted",
                        "content_omitted_before", "content_omitted_after", "content_offset",
                        "content_next_offset", "content_bytes", "content_budget",
                        "content_handle", "content_encoding", "content_residue",
                    )
                    if key in nested
                }
                projection["schema_version"] = nested["content_contract_schema"]
                result["located_source"] = {
                    "kind": route["kind"],
                    "reference": route["reference"],
                    "source": route.get("source") or "",
                    "content_handle": nested.get("content_handle"),
                    "content_status": nested.get("content_status"),
                }
            else:
                cluster_bytes = json.dumps(
                    result["semantic_down"], ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                projection = bounded_content(
                    handle=ref,
                    content=cluster_bytes,
                    content_handle=_sha256(cluster_bytes),
                    media_type="application/json",
                    budget=int(content_budget),
                    offset=int(content_offset),
                )
        else:
            raw_content = result.pop("_content_bytes")
            projection = bounded_content(
                handle=ref,
                content=raw_content,
                content_handle=str(result.get("content_handle") or ""),
                media_type=str(result.get("media_type") or "application/octet-stream"),
                budget=int(content_budget),
                offset=int(content_offset),
            )
        result["content_contract_schema"] = projection.pop("schema_version")
        result.update(projection)
        if result["content_status"] != "COMPLETE":
            # ``value`` was the historical unbounded face.  Keeping it beside a bounded
            # ``content`` field would make the budget decorative, so it is displaced loudly.
            result.pop("value", None)
            result["value_omitted"] = True
    except DescentRefused as exc:
        if trace.get("status") == "MOVED":
            refusal_handle = _sha256(
                json.dumps(
                    refusal_result(str(kind), ref, exc),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ).encode("utf-8")
            )
            try:
                trace = atlas_bridge.finish_typed_descent(
                    trace,
                    result_handle=refusal_handle,
                    provenance={"kind": kind, "reference": ref, "source": src},
                    refused=str(exc),
                )
            except Exception as telemetry_exc:  # noqa: BLE001 - refusal remains the truth
                trace = {
                    **{k: v for k, v in trace.items() if not str(k).startswith("_")},
                    "status": "UNAVAILABLE-AFTER-MOVE",
                    "error": f"{type(telemetry_exc).__name__}: {telemetry_exc}",
                }
        exc.details["telemetry"] = trace
        raise
    if trace.get("status") == "MOVED":
        try:
            trace = atlas_bridge.finish_typed_descent(
                trace,
                result_handle=str(
                    result.get("content_handle")
                    or _sha256(
                        json.dumps(result, ensure_ascii=False, sort_keys=True, default=str).encode(
                            "utf-8"
                        )
                    )
                ),
                provenance=result.get("provenance") or {},
            )
        except Exception as exc:  # noqa: BLE001 - result survives, telemetry failure is loud
            trace = {
                **{k: v for k, v in trace.items() if not str(k).startswith("_")},
                "status": "UNAVAILABLE-AFTER-MOVE",
                "error": f"{type(exc).__name__}: {exc}",
            }
    result["telemetry"] = trace
    result["read_only"] = not record_telemetry
    result["authority_write"] = (
        "none" if not record_telemetry else "reconstruction-call-return-telemetry"
    )
    result["transition_claim"] = (
        "none"
        if not record_telemetry
        else "reconstruction telemetry only; no delivery or semantic-currentness transition"
    )
    result["goal"] = str(goal)
    if str(kind).strip() == "atlas-object":
        receipt = {
            "schema_version": "laplace.dispatch-reconstruction-claim/1",
            "kind": result.get("kind"),
            "node": ref,
            "goal_utf8": str(goal),
            "content_status": result.get("content_status"),
            "content_handle": result.get("content_handle"),
            "read_only": result.get("read_only"),
            "transition_claim": result.get("transition_claim"),
            "authority_write": result.get("authority_write"),
            "current_root": result.get("current_root"),
            "authority_root": result.get("authority_root"),
            "drift_token": result.get("drift_token"),
            "integrity_boundary": result.get("integrity_boundary"),
        }
        receipt_bytes = json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        result["reconstruction_receipt"] = receipt
        result["reconstruction_receipt_handle"] = _sha256(receipt_bytes)
    return result
