"""THE BYTE LAYER of a Writing export, standard library only (Work5 recovery, 2026-10-20; boundary correction W5-R1/R2).

What an export DECLARES about itself (release/export-manifest.json, release/source-manifest.json, the project registry,
the repository configuration, the package declarations) and what its bytes ARE: present, changed, missing, outside the
root, not a regular file, or malformed; the journal's row kinds and import boundaries; the Work ledger's rows. Nothing
here imports the application (laplace, atlas) or writes anything, so a candidate whose kernel cannot start is still
inspectable with these functions.

ONE ADMISSION BOUNDARY (`Fence`). Every candidate coordinate, fixed or declared, is admitted the same way before any
open, stat or hash: the relative path has no `..` and is not absolute, no component is a symbolic link, the resolved path
stays inside the resolved root, and the target is a regular file. A refused coordinate is a finite, named fact in the
report (`refused`) and is never read: a symlink pointing outside the export contributes nothing, not even a byte count.
The only path admitted from outside the root is an explicitly supplied accepted copy of the export manifest
(`admit_external`): a separately admitted regular file, not a filesystem authority.

ONE READ RESULT CONTRACT (`file_identity`, `read_json`, `_lines`). Admission proves a path's shape and type, not that its
bytes can be read: the open, the streaming hash, the size and the JSON parse each return a typed finite problem
(`unreadable: PermissionError`, `malformed: ...`) instead of raising, and every consumer here (manifests, declared rows,
workspace inputs, the ledgers, the accepted copy, the checker's own identity) carries that problem into the report, where
the caller's one verdict consumes it. Only the expected I/O and parse failures are caught at that boundary; nothing is
swallowed around an unfenced open. `sha` keeps raising for callers outside this layer that want it to.

SHAPES BEFORE CONSUMPTION. The export manifest must carry a supported schema and its required fields with their types;
rows, registries, configurations and journal lines are type-checked before any `len`, iteration or key read. A wrong
shape is a malformed fact with a bounded diagnostic; it never escapes as a traceback and never becomes a guess.

TRUST. A manifest found inside a candidate is the candidate's own claim. "Declared bytes consistent" means the files
match the manifest they travel with; it is not acceptance. Acceptance identity comes from OUTSIDE the candidate: the
sha256 of the accepted export manifest, or an accepted copy of that file, supplied by the reviewer or Root. `trust`
validates the digest shape, reads the copy through its own admission, requires the two to agree when both are given,
refuses a copy that lies inside the candidate, and reports every problem; the caller's final verdict consumes those
problems. There is no fallback from a requested, failed anchor to the unanchored description.

Two consumers share this one layer: the full verifier (scripts/verify_writing_evaluation.py), which adds the
application's own semantics and therefore needs a working kernel, and the read-only inspector
(scripts/inspect_writing_export.py), which needs none.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

EXPORT_MANIFEST = 'release/export-manifest.json'
SOURCE_MANIFEST = 'release/source-manifest.json'
JOURNAL = 'contract/talk.jsonl'
WORK_LEDGER = 'corpus_friction/work_orders.jsonl'
REGISTRY = 'registry_projects.json'
REPOSITORIES = 'profiles/writing_sources.json'
PORTABILITY = 'writing-portability.json'
WORKSPACE_INPUTS = (REGISTRY, REPOSITORIES, PORTABILITY)
PACKAGE_DECLARATIONS = ('pyproject.toml', 'atlas/pyproject.toml')
SUPPORTED_EXPORT_SCHEMAS = ('laplace.writing-evaluation-export/1', 'laplace.writing-evaluation-export/2')
DIGEST = re.compile(r'^sha256:[0-9a-f]{64}$')
#: the journal row kinds the fold owner (laplace.writing.records._fold) reads; anything else is reported as unsupported here
KNOWN_RECORDS = frozenset({
    'writing-session', 'writing-session-import', 'writing-session-settings', 'writing-binding', 'writing-turn', 'writing-reply',
    'writing-tool-read', 'writing-tool-call', 'writing-tool-failure', 'writing-application', 'writing-native-file-change',
    'writing-turn-context-baseline', 'writing-artifact', 'writing-correction', 'writing-proposal-basis', 'writing-context',
    'writing-steering', 'writing-host', 'writing-dispatch', 'writing-note'})
LIST_LIMIT = 40
_MAX_JSON_BYTES = 64 * 1024 * 1024   # a declared JSON document larger than this is reported, not parsed


def sha(path) -> str:
    """The streaming digest; raises on I/O failure (the full verifier's own error handling wants that). The inspector's
    consumers use `file_identity`, the result form of the same read."""
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return 'sha256:' + h.hexdigest()


def file_identity(path) -> tuple[dict | None, str | None]:
    """({'sha256', 'bytes'}, None) for an admitted regular file whose bytes were streamed; (None, problem) when the open,
    the read or the stat fails: the one read result every consumer in this layer uses after admission."""
    try:
        digest = sha(path)
        return {'sha256': digest, 'bytes': Path(path).stat().st_size}, None
    except OSError as exc:
        return None, 'unreadable: ' + exc.__class__.__name__


def digest_shape_problem(value) -> str | None:
    if not isinstance(value, str):
        return 'a digest is a string'
    if not DIGEST.match(value):
        return 'a digest is sha256: followed by 64 lowercase hex characters'
    return None


# ------------------------------------------------------------------------------------------------ the admission boundary

class Fence:
    """Admits candidate coordinates under one root; refusals are returned, never raised, and nothing refused is opened."""

    def __init__(self, root):
        self.root = Path(root)
        try:
            self.resolved = self.root.resolve(strict=True)
        except OSError as exc:
            raise ValueError('the inspected root is not readable: %s' % exc)
        if not self.resolved.is_dir():
            raise ValueError('the inspected root is not a directory')
        self.refused: list[dict] = []

    def admit(self, relative) -> tuple[Path | None, str | None]:
        """(path, None) for an admitted regular file; (None, problem) otherwise. The problem names the coordinate and the rule."""
        problem = self._problem(relative)
        if problem:
            if problem != 'missing':   # absence is each consumer's own fact (optional inputs exist); a refusal is a present, inadmissible coordinate
                self.refused.append({'path': str(relative), 'problem': problem})
            return None, problem
        return self.root / relative, None

    def _problem(self, relative) -> str | None:
        if not isinstance(relative, str) or not relative or len(relative) > 4096:
            return 'coordinate is not a non-empty path string'
        pure = Path(relative)
        if pure.is_absolute() or '..' in pure.parts or not pure.parts:
            return 'coordinate is absolute or climbs out of the root'
        walk = self.root
        for part in pure.parts:
            walk = walk / part
            try:
                info = os.lstat(walk)
            except FileNotFoundError:
                return 'missing'
            except OSError as exc:
                return 'unreadable: %s' % exc.__class__.__name__
            if stat.S_ISLNK(info.st_mode):
                return 'a component is a symbolic link; the inspection follows none'
        try:
            resolved = walk.resolve(strict=True)
        except OSError:
            return 'unreadable'
        if not resolved.is_relative_to(self.resolved):
            return 'resolves outside the inspected root'
        if not stat.S_ISREG(info.st_mode):
            return 'not a regular file'
        return None


def admit_external(path) -> tuple[Path | None, str | None]:
    """An explicitly supplied file from outside the candidate (the accepted manifest copy): regular file, no symlink."""
    try:
        candidate = Path(path)
        info = os.lstat(candidate)
    except (OSError, TypeError, ValueError) as exc:
        return None, 'the supplied accepted copy is not readable: %s' % exc.__class__.__name__
    if stat.S_ISLNK(info.st_mode):
        return None, 'the supplied accepted copy is a symbolic link; the inspection follows none'
    if not stat.S_ISREG(info.st_mode):
        return None, 'the supplied accepted copy is not a regular file'
    return candidate, None


def read_json(path: Path):
    """(value, problem) for an admitted regular file: an I/O failure is `unreadable: <error>`, a parse failure `malformed: ...`;
    nothing here raises."""
    try:
        if path.stat().st_size > _MAX_JSON_BYTES:
            return None, 'malformed: larger than the %d-byte JSON ceiling' % _MAX_JSON_BYTES
        raw = path.read_bytes()
    except OSError as exc:
        return None, 'unreadable: ' + exc.__class__.__name__
    try:
        return json.loads(raw.decode('utf-8')), None
    except (ValueError, UnicodeDecodeError) as exc:
        return None, 'malformed: ' + exc.__class__.__name__ + ': ' + str(exc)[:120]


_read_json = read_json


def _is_str(value) -> bool:
    return isinstance(value, str) and bool(value)


# ------------------------------------------------------------------------------------------------ declared coordinates

def manifest_shape_problems(report) -> list[str]:
    """Why a value is not a supported export manifest; empty when it is."""
    if not isinstance(report, dict):
        return ['the export manifest is not an object']
    problems = []
    if report.get('schema') not in SUPPORTED_EXPORT_SCHEMAS:
        problems.append('unsupported export schema: %r' % (report.get('schema'),))
    if digest_shape_problem(report.get('source_manifest_sha256')):
        problems.append('source_manifest_sha256 is missing or not a digest')
    if not _is_str(report.get('project')):
        problems.append('project is missing or not a string')
    projects = report.get('projects')
    if not isinstance(projects, list) or not projects or not all(_is_str(p) for p in projects):
        problems.append('projects is missing or not a non-empty list of strings')
    for key in ('copied_files', 'derived_files'):
        rows = report.get(key)
        if not isinstance(rows, list):
            problems.append('%s is missing or not a list' % key)
            continue
        bad = sum(1 for row in rows if not (isinstance(row, dict) and _is_str(row.get('path')) and not digest_shape_problem(row.get('sha256'))
                                            and (row.get('bytes') is None or (isinstance(row.get('bytes'), int) and not isinstance(row.get('bytes'), bool) and row['bytes'] >= 0))))
        if bad:
            problems.append('%s has %d rows without a string path, a digest and an optional non-negative byte count' % (key, bad))
    return problems


def declared_manifest(fence: Fence) -> dict:
    """The export manifest as the candidate declares it, admitted and shape-checked, with its own identity and the source manifest's."""
    out = {'path': EXPORT_MANIFEST, 'present': False, 'problem': None, 'sha256': None, 'report': None, 'declared': None,
           'source_manifest': {'path': SOURCE_MANIFEST, 'present': False, 'sha256': None, 'declared_sha256': None, 'identity_match': False}}
    path, problem = fence.admit(EXPORT_MANIFEST)
    if problem:
        out['problem'] = problem
        return out
    out['present'] = True
    identity, problem = file_identity(path)
    if problem:
        out['problem'] = problem
        return out
    out['sha256'] = identity['sha256']
    report, problem = read_json(path)
    if problem:
        out['problem'] = problem
        return out
    shape = manifest_shape_problems(report)
    if shape:
        out['problem'] = 'malformed: ' + '; '.join(shape)
        out['schema'] = report.get('schema') if isinstance(report, dict) else None
        return out
    out['report'] = report
    out['declared'] = {key: report.get(key) for key in ('schema', 'created', 'project', 'projects', 'status', 'imported_sessions', 'source_manifest_sha256')}
    out['declared']['copied_files'] = len(report['copied_files'])
    out['declared']['derived_files'] = len(report['derived_files'])
    out['source_manifest']['declared_sha256'] = report['source_manifest_sha256']
    source_path, problem = fence.admit(SOURCE_MANIFEST)
    if problem:
        out['source_manifest']['problem'] = problem
        return out
    out['source_manifest']['present'] = True
    identity, problem = file_identity(source_path)
    if problem:
        out['source_manifest']['problem'] = problem
        return out
    out['source_manifest']['sha256'] = identity['sha256']
    out['source_manifest']['identity_match'] = identity['sha256'] == report['source_manifest_sha256']
    return out


def declared_files(fence: Fence, report: dict) -> dict:
    """Every file a shape-valid export manifest declares, against the admitted bytes now under the root."""
    rows = {'declared': 0, 'present': 0, 'changed': [], 'missing': [], 'refused': [], 'size_differs': [], 'malformed_rows': 0}
    for row in list(report.get('copied_files') or []) + list(report.get('derived_files') or []):
        if not (isinstance(row, dict) and _is_str(row.get('path')) and not digest_shape_problem(row.get('sha256'))):
            rows['malformed_rows'] += 1
            continue
        rows['declared'] += 1
        path, problem = fence.admit(row['path'])
        identity = None
        if not problem:
            identity, problem = file_identity(path)
        if problem == 'missing':
            rows['missing'].append(row['path'])
        elif problem:
            rows['refused'].append({'path': row['path'], 'problem': problem})
        elif identity['sha256'] != row['sha256']:
            rows['changed'].append(row['path'])
        else:
            rows['present'] += 1
            if isinstance(row.get('bytes'), int) and not isinstance(row.get('bytes'), bool) and row['bytes'] != identity['bytes']:
                rows['size_differs'].append(row['path'])
    for key in ('changed', 'missing', 'refused', 'size_differs'):
        rows[key + '_count'] = len(rows[key])
        rows[key] = rows[key][:LIST_LIMIT]
    rows['consistent'] = not (rows['changed_count'] or rows['missing_count'] or rows['refused_count'] or rows['size_differs_count'] or rows['malformed_rows'])
    return rows


def repository_scope(root, fence: Fence | None = None):
    """The configured source repositories and whether each lives inside the export (the verifier's original check), admitted
    and shape-checked: (rows, failures)."""
    fence = fence or Fence(root)
    path, problem = fence.admit(REPOSITORIES)
    if problem:
        return [], [{'reason': 'repository configuration ' + problem, 'path': REPOSITORIES}]
    config, problem = read_json(path)
    if problem:
        return [], [{'reason': 'repository configuration ' + problem, 'path': REPOSITORIES}]
    repositories = config.get('repositories') if isinstance(config, dict) else None
    if not isinstance(repositories, dict) or not all(_is_str(k) and _is_str(v) for k, v in repositories.items()):
        return [], [{'reason': 'repository configuration malformed: repositories must be an object of id -> path strings', 'path': REPOSITORIES}]
    rows, failures = [], []
    for ident, raw in repositories.items():
        value = Path(raw)
        resolved = (fence.resolved / value).resolve() if not value.is_absolute() else value.resolve()
        inside = resolved.is_relative_to(fence.resolved)
        available = inside and resolved.is_dir()
        optional = ident == 'supplementary'
        rows.append({'id': ident, 'declared': raw, 'inside_export': inside, 'available': available, 'optional': optional})
        if not inside:
            failures.append({'reason': 'external source repository', 'id': ident, 'declared': raw})
        elif not available and not optional:
            failures.append({'reason': 'required source repository missing', 'id': ident, 'declared': raw})
    return rows, failures


def workspace_inputs(fence: Fence) -> dict:
    out = {}
    for rel in WORKSPACE_INPUTS + PACKAGE_DECLARATIONS:
        path, problem = fence.admit(rel)
        if problem:
            out[rel] = {'present': problem != 'missing', 'problem': None if problem == 'missing' else problem}
            continue
        identity, problem = file_identity(path)
        if problem:
            out[rel] = {'present': True, 'problem': problem}
            continue
        entry = {'present': True, 'sha256': identity['sha256'], 'bytes': identity['bytes'], 'problem': None}
        if rel.endswith('.json'):
            value, problem = read_json(path)
            if problem:
                entry['problem'] = problem
            elif rel == REGISTRY:
                projects = value.get('projects') if isinstance(value, dict) else value
                if not isinstance(projects, list):
                    entry['problem'] = 'malformed: projects must be a list'
                else:
                    names = [p.get('name') for p in projects if isinstance(p, dict)]
                    if len(names) != len(projects) or not all(_is_str(n) for n in names):
                        entry['problem'] = 'malformed: every registry row is an object with a string name'
                    entry['projects'] = [n for n in names if _is_str(n)][:LIST_LIMIT]
            elif rel == PORTABILITY:
                if not isinstance(value, dict):
                    entry['problem'] = 'malformed: not an object'
                else:
                    entry['schema'] = value.get('schema') if _is_str(value.get('schema')) else None
                    entry['source_manifest_sha256'] = value.get('source_manifest_sha256') if not digest_shape_problem(value.get('source_manifest_sha256')) else None
            elif rel == REPOSITORIES:
                repositories = value.get('repositories') if isinstance(value, dict) else None
                if not isinstance(repositories, dict):
                    entry['problem'] = 'malformed: repositories must be an object'
        out[rel] = entry
    return out


def _lines(path: Path):
    """JSON lines of an admitted regular file: (row, None) or (None, problem) per line; an unreadable file yields one
    `unreadable: <error>` problem; a closed stream, never a raise."""
    try:
        with path.open('r', encoding='utf-8', errors='replace') as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    yield None, 'not JSON'
                    continue
                yield (row, None) if isinstance(row, dict) else (None, 'not an object')
    except OSError as exc:
        yield None, 'unreadable: ' + exc.__class__.__name__


def journal_summary(fence: Fence) -> dict:
    """The journal's rows by kind, its sessions, the import boundaries and the native bindings, read as plain JSON lines."""
    out = {'path': JOURNAL, 'present': False, 'problem': None, 'rows': 0, 'malformed_lines': 0, 'malformed_rows': [], 'kinds': {}, 'unsupported_kinds': {},
           'sessions': [], 'sessions_total': 0, 'turns': 0, 'import_boundaries': [], 'native_bindings': [], 'projects': []}
    path, problem = fence.admit(JOURNAL)
    if problem:
        out['problem'] = problem
        return out
    out['present'] = True
    sessions, projects = {}, set()
    for row, problem in _lines(path):
        if problem:
            if problem.startswith('unreadable'):
                out['problem'] = problem
                break
            out['malformed_lines'] += 1
            continue
        out['rows'] += 1
        kind = row.get('record') if _is_str(row.get('record')) else '(no record)'   # a legacy/foreign row is an unknown kind, reported, never interpreted
        out['kinds'][kind] = out['kinds'].get(kind, 0) + 1
        if kind not in KNOWN_RECORDS:
            out['unsupported_kinds'][kind] = out['unsupported_kinds'].get(kind, 0) + 1
            continue
        if _is_str(row.get('project')):
            projects.add(row['project'])
        ident, session_id = row.get('id'), row.get('session_id')
        if kind == 'writing-session':
            if not _is_str(ident):
                out['malformed_rows'].append({'line': out['rows'], 'record': kind, 'problem': 'id is not a non-empty string'})
                continue
            sessions[ident] = {'id': ident, 'project': row.get('project') if _is_str(row.get('project')) else None,
                               'provider': row.get('provider') if _is_str(row.get('provider')) else None, 'imported': False, 'bound': False}
        elif kind == 'writing-session-import':
            if not _is_str(session_id):
                out['malformed_rows'].append({'line': out['rows'], 'record': kind, 'problem': 'session_id is not a non-empty string'})
                continue
            out['import_boundaries'].append({'session_id': session_id, 'source_manifest_sha256': row.get('source_manifest_sha256') if not digest_shape_problem(row.get('source_manifest_sha256')) else None})
            if session_id in sessions:
                sessions[session_id]['imported'] = True
                sessions[session_id]['bound'] = False
        elif kind == 'writing-binding':
            if _is_str(session_id) and session_id in sessions and _is_str(row.get('native_id')):
                sessions[session_id]['bound'] = True
                out['native_bindings'].append({'session_id': session_id, 'native_id': '<present>'})
        elif kind == 'writing-turn':
            if not _is_str(ident):
                out['malformed_rows'].append({'line': out['rows'], 'record': kind, 'problem': 'id is not a non-empty string'})
                continue
            out['turns'] += 1
    out['sessions'] = list(sessions.values())[:LIST_LIMIT]
    out['sessions_total'] = len(sessions)
    out['projects'] = sorted(projects)
    out['import_boundaries'] = out['import_boundaries'][:LIST_LIMIT]
    out['native_bindings'] = out['native_bindings'][:LIST_LIMIT]
    out['malformed_rows_count'] = len(out['malformed_rows'])
    out['malformed_rows'] = out['malformed_rows'][:LIST_LIMIT]
    return out


def work_summary(fence: Fence) -> dict:
    """The Work ledger's rows by kind and the Work ids they name."""
    out = {'path': WORK_LEDGER, 'present': False, 'problem': None, 'rows': 0, 'malformed_lines': 0, 'malformed_rows_count': 0, 'kinds': {}, 'work_ids': [], 'work_ids_total': 0, 'phase_kinds': {}}
    path, problem = fence.admit(WORK_LEDGER)
    if problem:
        out['problem'] = problem
        return out
    out['present'] = True
    ids = set()
    for row, problem in _lines(path):
        if problem:
            if problem.startswith('unreadable'):
                out['problem'] = problem
                break
            out['malformed_lines'] += 1
            continue
        out['rows'] += 1
        kind = row.get('record') if _is_str(row.get('record')) else '(no record)'   # a legacy/foreign row is an unknown kind, reported, never interpreted
        out['kinds'][kind] = out['kinds'].get(kind, 0) + 1
        if kind == 'project-work':
            if _is_str(row.get('id')):
                ids.add(row['id'])
            else:
                out['malformed_rows_count'] += 1
        if kind == 'project-work-phase':
            phase = row.get('phase') if _is_str(row.get('phase')) else row.get('kind') if _is_str(row.get('kind')) else '?'
            out['phase_kinds'][phase] = out['phase_kinds'].get(phase, 0) + 1
    out['work_ids'] = sorted(ids)[:LIST_LIMIT]
    out['work_ids_total'] = len(ids)
    return out


# ------------------------------------------------------------------------------------------------ trust

def trust(fence: Fence, manifest: dict, *, accepted_manifest_sha256=None, accepted_manifest_path=None) -> dict:
    """Declared self-consistency and external acceptance identity, kept apart; every problem with a requested anchor is
    reported here and consumed by the caller's verdict (no requested anchor is ever quietly dropped)."""
    requested = accepted_manifest_sha256 is not None or accepted_manifest_path is not None
    problems: list[str] = []
    expected = None
    if accepted_manifest_sha256 is not None:
        shape = digest_shape_problem(accepted_manifest_sha256)
        if shape:
            problems.append('the supplied accepted digest is malformed: ' + shape)
        else:
            expected = accepted_manifest_sha256
    copy = None
    if accepted_manifest_path is not None:
        path, problem = admit_external(accepted_manifest_path)
        if problem:
            problems.append(problem)
        else:
            try:
                inside = path.resolve(strict=True).is_relative_to(fence.resolved)
            except OSError:
                inside = False
            if inside:
                problems.append('the supplied accepted copy lies inside the candidate: a same-candidate copy is not external authority')
            else:
                identity, problem = file_identity(path)
                if problem:
                    problems.append('the supplied accepted copy could not be read: ' + problem)
                else:
                    copy_sha = identity['sha256']
                    value, problem = read_json(path)
                    shape = manifest_shape_problems(value) if not problem else [problem]
                    if shape:
                        problems.append('the supplied accepted copy is not a supported export manifest: ' + '; '.join(shape))
                    else:
                        copy = {'path': str(path), 'sha256': copy_sha, 'project': value.get('project'), 'created': value.get('created')}
                        if expected and copy_sha != expected:
                            problems.append('the supplied accepted digest and the supplied accepted copy disagree (conflicting anchors)')
                        elif expected is None:
                            expected = copy_sha
    anchor = None
    if requested:
        anchor = {'requested': True, 'digest': accepted_manifest_sha256, 'copy': copy, 'expected': expected if not problems else None}
    candidate = manifest.get('sha256')
    match = None
    if requested and not problems:
        match = bool(candidate) and candidate == expected
    return {'requested': requested, 'candidate_manifest_sha256': candidate, 'external_anchor': anchor, 'problems': problems,
            'accepted_identity_match': match,
            'mode': 'anchored' if requested and not problems else 'anchor-failed' if requested else 'unanchored-self-description',
            'statement': ('No external anchor was supplied: every coordinate in this report is the candidate\'s own claim about itself; '
                          'declared-bytes consistency is not acceptance.' if not requested else
                          'An external anchor was requested but could not be used; this report establishes no acceptance identity.' if problems else
                          'The external anchor is the accepted export manifest identity; a candidate that rewrote its own manifest can be '
                          'self-consistent and still fail this match, and cannot certify itself.')}
