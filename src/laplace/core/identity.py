"""Identity: the one decision of what makes two bytes, two values or two revisions the same.

  bytes_digest     "sha256:<hex>" of exact bytes (None for absent bytes)
  file_digest      bytes_digest of a file's current bytes, None when it cannot be read
  canonical_bytes  a value's canonical JSON bytes (sorted keys, compact separators, UTF-8 text, non-JSON values by str)
  canonical_digest "sha256:<hex>" of those bytes: the identity of structured meaning
  revision_matches an owner revision compared with a supplied one, accepting only equivalent SHA-256 spellings
  require_schema_version / UnsupportedSchemaVersion  the gate an owner applies before interpreting a record
  reference / reference_problems / reference_key  the neutral owner-qualified reference (REFERENCE_SCHEMA)

Owners keep their own published spellings; this module never rebases or normalizes a stored identity.

A reference names an object through the owner responsible for it: ``owner`` (the declared subsystem id), ``kind``
(the owner's object kind), ``identity`` (the owner's existing native identity, verbatim: a Work keeps its exact
``{namespace, id}`` pair), an optional selected ``version`` and optional ``legacy`` handles an older adapter needs.
It is a shape only: the owner resolves and admits it; holding a reference grants nothing.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path

_SHA256 = re.compile(r"(?:sha256:)?([0-9a-fA-F]{64})\Z")


def bytes_digest(data: bytes | None) -> str | None:
    return "sha256:" + hashlib.sha256(data).hexdigest() if data is not None else None


def file_digest(path: Path) -> str | None:
    """The identity of a file's current bytes, or None when it cannot be read."""
    try:
        return bytes_digest(Path(path).read_bytes())
    except OSError:
        return None


def canonical_bytes(value) -> bytes:
    """A value's canonical JSON bytes: sorted keys, compact separators, UTF-8 text, non-JSON values by str."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def canonical_digest(value) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def revision_matches(expected: object, actual: object) -> bool:
    """Accept equivalent SHA-256 spellings; opaque revisions stay exact.

    Normalization is enabled only when the actual owner revision is a complete
    SHA-256 digest. It does not strip arbitrary prefixes, infer another digest
    algorithm, substitute another owner's revision, or compare source text.
    """
    if not isinstance(expected, str) or not isinstance(actual, str):
        return False
    observed = _SHA256.fullmatch(actual)
    if observed is None:
        return expected == actual
    requested = _SHA256.fullmatch(expected)
    return requested is not None and requested[1].lower() == observed[1].lower()


class UnsupportedSchemaVersion(ValueError):
    pass


def require_schema_version(value, supported, *, owner: str, allow_untagged: bool = False):
    """Never normalize an explicitly unsupported or malformed declaration."""
    if not isinstance(value, Mapping):
        raise UnsupportedSchemaVersion(f'{owner} must be an object before its version can be interpreted.')
    if 'schema_version' not in value and allow_untagged:
        return None  # Deliberate owner-selected historical compatibility.
    declared = value.get('schema_version')
    versions = tuple(supported)
    if not isinstance(declared, str) or declared not in versions:
        legacy = '; untagged historical objects are supported' if allow_untagged else ''
        raise UnsupportedSchemaVersion(
            f'{owner} declares unsupported schema_version {declared!r}. Supported: '
            + ', '.join(versions) + legacy
            + '. Original bytes are not migrated; inspect the raw owner file/history with a bounded repository read.')
    return declared


REFERENCE_SCHEMA = 'laplace.reference/1'
_REFERENCE_KEYS = {'schema_version', 'owner', 'kind', 'identity', 'version', 'legacy'}


def reference(owner: str, kind: str, identity: Mapping, *, version: Mapping | None = None,
              legacy: Mapping | None = None) -> dict:
    """One owner-qualified reference; ``identity`` is the owner's native identity, never derived from a title or path."""
    value = {'schema_version': REFERENCE_SCHEMA, 'owner': owner, 'kind': kind, 'identity': dict(identity)}
    if version is not None:
        value['version'] = dict(version)
    if legacy is not None:
        value['legacy'] = dict(legacy)
    problems = reference_problems(value)
    if problems:
        raise ValueError('Malformed reference: ' + '; '.join(problems))
    return value


def reference_problems(value) -> list[str]:
    """The finite shape problems of a supplied reference (empty when it is well formed)."""
    if not isinstance(value, Mapping):
        return ['a reference is an object']
    problems = []
    if value.get('schema_version') != REFERENCE_SCHEMA:
        problems.append('schema_version is not ' + REFERENCE_SCHEMA)
    unknown = set(value) - _REFERENCE_KEYS
    if unknown:
        problems.append('unknown fields: ' + ', '.join(sorted(unknown)))
    for key in ('owner', 'kind'):
        if not isinstance(value.get(key), str) or not value.get(key):
            problems.append(key + ' is a non-empty string')
    identity = value.get('identity')
    if not isinstance(identity, Mapping) or not identity or any(
            not isinstance(item, str) or not item for item in identity.values()):
        problems.append('identity is a non-empty object of non-empty strings')
    for key in ('version', 'legacy'):
        if key in value and not isinstance(value[key], Mapping):
            problems.append(key + ' is an object')
    return problems


def reference_key(value: Mapping) -> str:
    """The identity of the referenced object (owner, kind, native identity), independent of version and legacy handles."""
    return canonical_digest({'owner': value['owner'], 'kind': value['kind'], 'identity': value['identity']})
