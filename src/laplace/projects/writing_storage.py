"""Read existing Writing stores; remove only verified empty orphan provider cwd dirs.

This is a projection, not a retention ledger. Source, versions, conversation rows,
evidence and content bodies are never cleanup candidates.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import hashlib
import shutil
from pathlib import Path

import psutil
from filelock import FileLock
from laplace.writing import operating as writing_operating

PROTECTED = ["source", "saved versions", "conversation and journal", "evidence",
             "saved bodies", "nonempty provider workspaces", "recorded sessions", "discovery",
             "execution receipts and controls"]
_HANDLE = re.compile(r'"content_handle"\s*:\s*"sha256:([0-9a-f]{64})"')


def _size(path: Path) -> int:
    """Logical bytes, without following directory or file symlinks outside the owner."""
    if path.is_symlink():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    if path.is_dir():
        for directory, dirs, files in os.walk(path, followlinks=False):
            base = Path(directory)
            dirs[:] = [name for name in dirs if not (base / name).is_symlink()]
            total += sum((base / name).stat().st_size for name in files
                         if not (base / name).is_symlink())
    return total


def _rows(path: Path):
    if path.exists():
        with path.open('rb') as stream:
            for raw in stream:
                if raw.strip():
                    # Unknown reachability is a refusal, never a skipped orphan row.
                    row = json.loads(raw)
                    if not isinstance(row, dict):
                        raise ValueError('Storage ledger row is not an object')
                    yield row, len(raw)


def _scan(project: str, root: Path):
    from laplace.pipeline import registry
    registered = registry.resolve(project, repo_root=root)
    if registered is None:
        raise ValueError('Storage requires a registered project')
    protected = {writing_operating.DISCOVERY_SESSION}
    sessions = set()
    handles = set()
    counts = {key: 0 for key in ('conversation', 'journal', 'work')}
    for name, relative in (('conversation', 'contract/talk.jsonl'),
                           ('journal', 'contract/journal.jsonl'),
                           ('work', 'corpus_friction/work_orders.jsonl')):
        for row, size in _rows(root / relative):
            # Every recorded session reference protects its cwd, across all projects
            # and row kinds; incomplete/session-start rows protect it too.
            session = row.get('session_id')
            if row.get('record') == 'writing-session':
                session = session or row.get('id')
            if session:
                protected.add(writing_operating.session_workspace_name(str(session)))
            if row.get('project') == project:
                counts[name] += size
                if session:
                    sessions.add(writing_operating.session_workspace_name(str(session)))
                handles.update(_HANDLE.findall(json.dumps(row)))
    location = registered.project_dir or registered.manuscript_dir or registered.tex_root
    owned = registered.path(location, root) if location else None
    own_bytes = _size(owned) if owned else 0
    versions = sum(_size(Path(directory) / 'editor_saves')
                   for directory, dirs, _ in os.walk(owned, followlinks=False)
                   if 'editor_saves' in dirs) if owned and owned.is_dir() else 0
    counts.update(saved_bodies=sum(_size(root / 'contract/writing_bodies' / h[:2] / h)
                                   for h in handles), own_files=own_bytes,
                  saved_versions=versions)
    return counts, protected, sessions


def _workspaces():
    base = writing_operating.session_workspace_root()
    return base, [p for p in base.iterdir() if p.is_dir() and not p.is_symlink()] if base.is_dir() else []


def _execution_bytes(root: Path, sessions: set[str]) -> int:
    """Stat retained host/control history at its existing owner; do not read controls or prune."""
    from laplace.writing import child_hosts
    directory = child_hosts._host_directory(root)
    total = 0
    for session in sessions:
        try:
            receipt = child_hosts._host_path(root, session)
        except ValueError:
            continue  # legacy non-host session identity has no controller namespace
        # Host JSON, cancellation, lock/temporary residue and .controls mailbox
        # are all retained history of this session. The dotted boundary avoids
        # attributing another session with a shared textual prefix.
        if directory.is_dir():
            total += sum(_size(path) for path in directory.glob(receipt.stem + '.*'))
            total += _size(directory / 'finished' / receipt.name)
    return total


def inspect(project: str, root: Path | str) -> dict:
    root = Path(root).resolve()
    counts, protected, sessions = _scan(project, root)
    _, paths = _workspaces()
    counts['session_workspaces'] = sum(_size(path) for path in paths if path.name in sessions)
    counts['execution_history'] = _execution_bytes(root, sessions)
    from laplace.pipeline import pathsafe
    counts['candidate_cache'] = _size(root / '.laplace-cache/writing-style' /
                                      pathsafe.encode_sid_for_path(project) / 'candidates')
    orphans = [p for p in paths if p.name not in protected]
    empty = sum(not any(path.iterdir()) for path in orphans)
    active, unknown = _process_cwds()
    return {'schema_version': 'laplace.writing-storage/1', 'project': project,
            'measured_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'bytes': counts, 'saved_versions_in_own_files': True,
            'cleanup': {'scope': 'empty orphan session workspaces across this runtime',
                        'empty_orphans': empty, 'nonempty_orphans': len(orphans) - empty,
                        'available': not unknown,
                        'unavailable_reason': ('Current-user process cwd/identity is unknown' if unknown else None),
                        'unknown_process_ids': unknown,
                        'active_orphans': sum(any(cwd == path or path in cwd.parents for cwd in active)
                                              for path in orphans),
                        'confirmed_act': 'storage_prune', 'protected': PROTECTED},
            'limitations': 'Logical bytes; symlinks excluded. Shared bodies are counted per reference owner. '
                           'No historical growth baseline is written; nonempty provider data is retained.'}


def _process_cwds() -> tuple[list[Path], list[int]]:
    """Writing providers inherit this user's identity; other users aren't this owner.

    Matching/unknown identities with unreadable cwd remain a refusal. No process
    name or command guess classifies a same-user background service as safe.
    """
    active, unknown = [], []
    own_uid = os.getuid() if hasattr(os, 'getuid') else None
    own_user = psutil.Process().username() if own_uid is None else None
    for process in psutil.process_iter():
        try:
            if own_uid is not None:
                if process.uids().real != own_uid:
                    continue
            elif process.username().casefold() != own_user.casefold():
                continue
            identity = process.create_time()
            if process.status() == psutil.STATUS_ZOMBIE:
                continue
            cwd = process.cwd()
            if not cwd or psutil.Process(process.pid).create_time() != identity:
                unknown.append(process.pid)
            else:
                active.append(Path(cwd).resolve())
        except psutil.NoSuchProcess:
            continue
        except (psutil.AccessDenied, OSError, NotImplementedError):
            unknown.append(process.pid)
    return active, unknown


def prune(project: str, payload: dict, root: Path | str) -> dict:
    if 'candidate_ref' in payload:
        return _prune_candidate(project,payload,Path(root).resolve())
    if payload.get('confirm') is not True:
        raise ValueError('Confirm removal of empty orphan session workspaces with confirm=true')
    if set(payload) - {'project', 'confirm'}:
        raise ValueError('Storage cleanup accepts no paths or additional cleanup categories')
    from laplace.core.records import journal
    root = Path(root).resolve()
    base = writing_operating.session_workspace_root()
    from laplace.engine.telemetry import state_dir
    legacy = (state_dir() / writing_operating.PROCESS_WORKSPACES).resolve()
    if base == root or (root in base.parents and base != legacy):
        raise ValueError('Storage cleanup refuses project/source/evidence directories as workspace roots')
    base.mkdir(parents=True, exist_ok=True)
    with FileLock(str(base / '.cleanup.lock'), timeout=10):
        _, protected, _ = _scan(project, root)
        active, unknown = _process_cwds()
        if unknown:
            raise ValueError('Storage cleanup unavailable: current-user process cwd/identity unavailable for PIDs ' +
                             ','.join(map(str, unknown)))
        _, paths = _workspaces()
        candidates = [path for path in paths if path.name not in protected
                      and not any(path.iterdir())
                      and not any(cwd == path or path in cwd.parents for cwd in active)]
        act = journal.act_begin('writing-storage-prune', ['remove empty orphan workspaces'],
                                root=root, project=project,
                                workspace_root=str(base), candidates=[p.name for p in candidates])
        removed = []
        try:
            for path in candidates:
                # rmdir is the final concurrent-writer guard: any new file preserves
                # the workspace. Never recurse, unlink a symlink or remove contents.
                try:
                    path.rmdir()
                except OSError:
                    continue
                removed.append(path.name)
            journal.act_end(act, 'DONE', root=root,
                            summary=json.dumps({'removed': removed, 'logical_bytes': 0}))
        except BaseException:
            journal.act_end(act, 'FAILED', root=root,
                            summary=json.dumps({'removed': removed, 'logical_bytes': 0}))
            raise
    return {'project': project, 'act_id': act, 'removed': removed, 'logical_bytes': 0,
            'protected': PROTECTED}


def _candidate_cache_owner(project, ref, root):
    from laplace.manuscript import build_targets, document_templates
    proposal=document_templates.candidate(project,ref,root)['proposal']
    target=build_targets.candidate_target(project,ref,proposal,root)
    directory=build_targets._candidate_home(target,proposal,root).parent
    build_targets._private_path(root,directory.relative_to(root))
    return proposal,target,directory


def _cache_measure(directory):
    """Bounded generated-cache stats; no source, ledger or PDF body hydration."""
    rows=[]
    if directory.exists():
        for base,dirs,files in os.walk(directory,followlinks=False):
            for name in sorted(dirs+files):
                path=Path(base)/name
                if path.is_symlink():raise ValueError('Candidate cleanup refuses symlinks in generated cache.')
                stat=path.stat()
                rows.append([path.relative_to(directory).as_posix(),path.is_dir(),stat.st_size,
                             stat.st_ino,stat.st_mtime_ns,stat.st_ctime_ns])
    rows.sort()
    revision='sha256:'+hashlib.sha256(json.dumps([directory.exists(),rows],separators=(',',':')).encode()).hexdigest()
    return {'cache_revision':revision,'files':sum(not row[1] for row in rows),
            'logical_bytes':sum(row[2] for row in rows if not row[1]),'available':directory.exists()}


def candidate_cache(project, ref, root):
    """Exact disposable subject; opening a candidate never stages its source."""
    root=Path(root).resolve()
    _,target,directory=_candidate_cache_owner(project,ref,root)
    measured=_cache_measure(directory)
    payload={'candidate_ref':ref,'guards':{'cache_revision':measured['cache_revision']},'confirm':True}
    return {'schema_version':'laplace.template-candidate-cache/1','project':project,'candidate_ref':ref,
        **measured,'scope':'Private candidate source copies, compiler auxiliaries and retained PDF caches only',
        'protected':['canonical source','immutable candidate','terminal build ART','retained input CAS'],
        'effect':'Existing preview outputs become unavailable. Explicit Build can prepare private inputs again.',
        'prune_action':{'operation':'storage_prune','project':project,'payload':payload,
            'http':{'method':'POST','route':'/work/storage/prune'}}}


def _prune_candidate(project, payload, root):
    from laplace.manuscript import projection_viewer as compiler
    from laplace.core.records import journal
    from laplace.manuscript import build_jobs, build_targets
    from filelock import Timeout
    if (payload.get('confirm') is not True or set(payload)-{'project','confirm','candidate_ref','guards'}
            or set(payload.get('guards') or {})!={'cache_revision'}):
        raise ValueError('Candidate cache cleanup requires its exact candidate_ref and guards.cache_revision with confirm=true.')
    proposal,target,directory=_candidate_cache_owner(project,payload['candidate_ref'],root)
    source=root/target['root']
    mutex=FileLock(str(compiler._recompile_lock_path(source)),timeout=0,thread_local=False)
    Path(mutex.lock_file).parent.mkdir(parents=True,exist_ok=True)
    try:mutex.acquire()
    except Timeout:raise ValueError('Candidate cache is busy with its owned compiler; inspect/cancel the exact build first.') from None
    try:
        with build_jobs.control(source),FileLock(str(build_targets.candidate_stage_lock_path(target,proposal,root)),timeout=0):
            row=compiler._read_recompile_status(source)
            if build_jobs.processes_active(row) or row.get('cleanup_unproved') or row.get('state') in build_jobs.ACTIVE:
                raise ValueError('Candidate compiler cleanup is unproved; no cache was removed.')
            measured=_cache_measure(directory)
            if measured['cache_revision']!=payload['guards']['cache_revision']:
                raise ValueError('CHANGED_INPUT: candidate cache changed since inspection; inspect its cleanup action again.')
            act=journal.act_begin('writing-template-cache-prune',['remove exact generated candidate cache'],
                root=root,project=project,candidate_ref=payload['candidate_ref'],logical_bytes=measured['logical_bytes'])
            try:
                if directory.exists():shutil.rmtree(directory)
                journal.act_end(act,'DONE',root=root,summary=json.dumps(measured))
            except BaseException:
                journal.act_end(act,'FAILED',root=root,summary='Exact generated candidate cache cleanup failed.')
                raise
            return {'project':project,'candidate_ref':payload['candidate_ref'],'act_id':act,
                    'removed':measured['available'],'logical_bytes':measured['logical_bytes'],
                    'preview_state':'UNAVAILABLE','canonical_source_changed':False,
                    'protected':['canonical source','immutable candidate','terminal build ART','retained input CAS']}
    except Timeout:raise ValueError('Candidate staging is busy; no cache was removed.') from None
    finally:mutex.release()
