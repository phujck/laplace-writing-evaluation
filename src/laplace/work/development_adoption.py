"""ADOPTION of a development lane into the live tree (wave 13, dev-route packet 5; wave10/incorporation.md 'Adoption', D5;
ruling D6 in wave10/orchestrator_rulings.json). The only owner that writes the live tree from a lane, and only on the
author's click at the human door (POST /work/development, project_work_surface); a native turn is refused.

  preview   read-only on the Work ledger and the live tree, no lock: the lane's diff by file (scripts/** and profiles/**
            flagged), the latest check of each profile on the lane and whether its staged pins equal the lane files now, the
            failing names of each such check that do not fail when the same profile and files run on a lean scratch copy of
            live HEAD (the newly failing names), the proof that the diff applies to that copy, the reviews that will read STALE,
            and the publication inputs the close carries that pin a changed file (work.source_kernel through the close carry's
            own function). The scratch copy is removed before the preview returns. The preview writes nothing anywhere: its
            id and digest are the sha256 of the facts Adopt depends on, and Adopt re-derives those facts under its locks.
  adopt     project_work.dispatch_lock then source_publication.publication_lock, both non-blocking (ruling D6: Adopt refuses
            rather than waits); the preview's facts re-derived under the locks and their digest compared with the one the
            offer named (refused on any difference); a PREPARED adoption on the lane row carrying those facts; `git apply --index`; one local commit A with a
            Work-Id trailer (never pushed); the adoption COMMITTED with A and the lane ADOPTED; its grants revoked; its worktree
            removed. A retry after a crash finds A by its Adoption-Id trailer and finishes.
  adoption  the lane's adoption as recorded, and the review owner's current standing of the reviews it named.

The adoption is recorded ON the lane's own holder row (development-lane, id lane:<work-id>, the latest row wins): the row
gains an `adoption` object, PREPARED while the lane is still ACTIVE, then COMMITTED with the commit when the row turns
ADOPTED. No second record says a lane was adopted. After Adopt, review currentness of that lane's basis is anchored on A
(anchor(), called by development_source.validate_review_basis): current while A is live HEAD or its ancestor and the
reviewed files are unchanged; the live root is read there through the owner's fence and is never written by a grant,
apply or check.
"""
from __future__ import annotations

import copy
import datetime as dt
import fnmatch
import hashlib
import json
import os
import signal
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from laplace.work import development_source as D

ACTIONS = ('preview', 'adoption', 'adopt')
SCHEMA = 'laplace.development-adoption/1'
TRAILER, ADOPTION_TRAILER = 'Work-Id', 'Adoption-Id'
#: Orchestrator decision 3 (NODE.w13): a lane may write tool code and profiles; the preview flags those files.
FLAGGED = ('scripts/**', 'profiles/**')
#: The terminal check states whose failing names are evidence (development_source TERMINAL_CHECK_STATES minus the states
#: in which the runner did not finish its own output).
EVIDENCE_STATES = ('COMPLETE', 'FAILED')


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def contract() -> dict:
    string = {'type': 'string'}
    return {'schema_version': 'laplace.development-adoption-contract/1', 'type': 'object', 'required': ['action', 'work_id'], 'additionalProperties': False,
            'properties': {'project': string, 'action': {'enum': list(ACTIONS)}, 'work_id': string, 'session_id': string, 'branch': string,
                           'preview_id': {'type': 'string', 'pattern': '^DP-[0-9a-f]{24}$'},
                           'preview_sha256': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}},
            'description': 'preview (work_id[, session_id]): read-only; what Adopt would move. adoption (work_id): the recorded adoption and '
                           'its reviews\' standing. adopt (human door only: work_id, branch, preview_id, preview_sha256, exactly as the preview '
                           'offer carries them): one local commit of the lane diff in the live tree with a Work-Id trailer; never pushed.'}


class Refused(ValueError):
    """An adoption refusal: its sentence is shown beside the control pressed (R9); nothing moved."""


# ------------------------------------------------------------------------------------------------ reading the lane

def _task(root: Path, project: str, work_id: str) -> dict:
    from laplace.work import project_work
    task = project_work._tasks(project, root).get(work_id)
    if task is None:
        raise ValueError('Name an existing Work id of this project.')
    return task


def _run(args, cwd=None, env=None, data=None, timeout=120) -> subprocess.CompletedProcess:
    import shutil
    git = shutil.which('git')
    if not git:
        raise Refused('git is not available on this host.')
    return subprocess.run([git, *args], cwd=cwd, env=env, input=data, capture_output=True, timeout=timeout)


def _git_ok(args, cwd=None, env=None, data=None) -> bytes:
    done = _run(args, cwd=cwd, env=env, data=data)
    if done.returncode != 0:
        raise Refused('git %s failed: %s' % (args[0], (done.stderr or done.stdout).decode('utf-8', 'replace').strip()[-300:]))
    return done.stdout


def _lane_grants(task: dict, row: dict) -> dict:
    return {grant['id']: grant for grant in D._latest_per_id(D.rows(task, 'grant')) if grant.get('repository') == row['id']}


def _effects(task: dict, grants: dict) -> list:
    return [effect for effect in D._latest_per_id(D.rows(task, 'effect')) if effect.get('grant_id') in grants]


def _base_pin(lane: Path, base: str, path: str):
    done = _run(['-C', str(lane), 'show', '%s:%s' % (base, path)])
    return ('sha256:' + hashlib.sha256(done.stdout).hexdigest()) if done.returncode == 0 else None


def _changed_in_lane(lane: Path) -> set:
    raw = _git_ok(['-C', str(lane), 'status', '--porcelain=v1', '-z', '--untracked-files=all'])
    items, changed = raw.split(b'\0'), set()
    skip = False
    for item in items:
        if skip:
            changed.add(item.decode()); skip = False; continue
        if len(item) > 3:
            changed.add(item[3:].decode())
            skip = item[:1] in (b'R', b'C')
    return changed


def _patch(lane: Path, base: str, paths: list) -> tuple[bytes, dict]:
    """The lane's change of exactly these paths against its base as one binary patch, built in a temporary index so the
    lane's own index is never touched; with the added/removed line counts git states per file."""
    with tempfile.TemporaryDirectory(prefix='laplace-adopt-index-') as tmp:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        _git_ok(['-C', str(lane), 'read-tree', base], env=env)
        _git_ok(['-C', str(lane), 'update-index', '--add', '--remove', '--', *paths], env=env)
        patch = _git_ok(['-C', str(lane), 'diff', '--cached', '--binary', '--full-index', base, '--', *paths], env=env)
        stats = {}
        for line in _git_ok(['-C', str(lane), 'diff', '--cached', '--numstat', base, '--', *paths], env=env).decode().splitlines():
            added, removed, path = line.split('\t', 2)
            stats[path] = {'added': None if added == '-' else int(added), 'removed': None if removed == '-' else int(removed)}
    return patch, stats


def _diff(task: dict, row: dict) -> dict:
    """The files Adopt would move: every file a COMMITTED development effect of this lane wrote, as it is in the lane now
    against its base. A lane file that changed with no effect recording it is reported, and Adopt refuses it."""
    lane, base = Path(row['checkout']), row['base']
    grants = _lane_grants(task, row)
    effects = _effects(task, grants)
    recorded = {item['path'] for effect in effects if effect.get('state') == 'COMMITTED' for item in effect.get('files') or ()}
    unfinished = sorted(effect['id'] for effect in effects if effect.get('state') != 'COMMITTED')
    changed = _changed_in_lane(lane)
    files = []
    for path in sorted(recorded | changed):
        before, after = _base_pin(lane, base, path), D._pin(lane / path)
        if before == after:
            continue
        files.append({'path': path, 'before_sha256': before, 'after_sha256': after,
                      'change': 'added' if before is None else 'deleted' if after is None else 'modified',
                      'flagged': any(fnmatch.fnmatchcase(path, pattern) for pattern in FLAGGED)})
    patch, stats = _patch(lane, base, [item['path'] for item in files]) if files else (b'', {})
    for item in files:
        item.update(stats.get(item['path']) or {'added': None, 'removed': None})
    return {'files': files, 'patch': patch, 'unrecorded': sorted(changed - recorded), 'unfinished_effects': unfinished}


# ------------------------------------------------------------------------------------------------ checks and newly failing

def _all_failing(parser, raw: bytes) -> list:
    """Every failing name the runner printed, read with the owner's own patterns and directive rule (development_source
    _failing); the comparison needs the whole list, which the status row caps at MAX_FAILING_NAMES for its line."""
    text = raw.decode('utf-8', errors='replace')
    if parser == 'tap':
        names = [m.group(2) for m in D._TAP_FAILURE.finditer(text) if (m.group(3) or '').upper() not in ('TODO', 'SKIP')]
    elif parser == 'pytest':
        names = D._PYTEST_FAILURE.findall(text)
    else:
        return []
    return list(dict.fromkeys(names))


def _checks(task: dict, row: dict, files: list) -> list:
    """The latest check of each profile on this lane's grants, and whether it is CURRENT for the diff: every input it staged
    equals the lane file now and every changed file its profile reads was staged."""
    lane, grants = Path(row['checkout']), _lane_grants(task, row)
    latest = {}
    for check in D.rows(task, 'check'):
        if check.get('grant_id') in grants:
            latest[check['name']] = check
    out = []
    for name, check in sorted(latest.items()):
        profile = (grants[check['grant_id']].get('checks') or {}).get(name) or {}
        staged = {item['path']: item['sha256'] for item in check.get('inputs') or ()}
        moved = sorted(path for path, pin in staged.items() if D._pin(lane / path) != pin)
        reads = [item['path'] for item in files if item['after_sha256'] and any(fnmatch.fnmatchcase(item['path'], g) for g in profile.get('inputs') or ())]
        missing = sorted(path for path in reads if path not in staged)
        out.append({'id': check['id'], 'name': name, 'grant_id': check['grant_id'], 'state': check.get('state'), 'ts': check.get('ts'),
                    'targets': check.get('targets') or [], 'failing_total': check.get('failing_total'), 'failing_complete': check.get('failing_complete'),
                    'current': bool(staged) and not moved and not missing, 'moved': moved[:8], 'moved_total': len(moved), 'not_staged': missing[:8],
                    '_row': check, '_profile': profile, '_grant': grants[check['grant_id']]})
    return out


def _scratch(live: Path, commit: str, roots: list, where: Path) -> Path:
    """A lean scratch copy of one live commit: exactly these top-level paths, unpacked from git archive (no worktree, no branch)."""
    present = set(_git_ok(['-C', str(live), 'ls-tree', '--name-only', commit]).decode().split('\n'))
    wanted = sorted({root for root in roots if root in present})
    target = where / 'live'
    target.mkdir()
    archive = _git_ok(['-C', str(live), 'archive', '--format=tar', commit, '--', *wanted])
    import io
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as tar:
        tar.extractall(target, filter='data')
    return target


def _base_run(root: Path, scratch: Path, check: dict, where: Path) -> dict:
    """The same profile and files as the lane check, run in the owner's isolated sandbox on the scratch copy of live HEAD
    (development_source staging, isolation argv, limits and stage settlement); no check row is written."""
    profile, grant = check['_profile'], check['_grant']
    launcher = D.isolation_launcher()
    reason = D.enforcement_available(launcher) or D.mount_policy_problem(root, launcher)
    if reason:
        return {'state': 'UNAVAILABLE', 'reason': reason}
    runtime = None
    if profile.get('runtime', 'system') == D.REGISTERED_RUNTIME:
        try:
            runtime = D.registered_runtime(root)
        except (ValueError, OSError) as exc:
            return {'state': 'UNAVAILABLE', 'reason': 'the registered runtime is unavailable: %s' % str(exc)[:200]}
        if runtime['identity'] != (profile.get('runtime_admission') or {}).get('identity'):
            return {'state': 'UNAVAILABLE', 'reason': 'the registered runtime changed since the lane grant'}
    run_dir = where / ('run-' + check['id'])
    stage = run_dir / 'input'
    stage.mkdir(parents=True)
    try:
        D._stage_inputs(root, scratch, grant, profile, stage)
        _deps, problems = D._stage_dependencies(root, scratch, grant, profile, stage)
    except ValueError as exc:
        problems = [str(exc)]
    if problems:
        D._settle_stage(stage)
        return {'state': 'UNAVAILABLE', 'reason': 'the live commit could not be staged like the lane: ' + '; '.join(problems)[:300]}
    argv = D._isolation_argv(launcher, stage, {**profile, 'args': [*profile['args'], *check['targets']]}, runtime)
    started = time.perf_counter()
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
                               cwd=str(run_dir), preexec_fn=D._limits(profile))
    state = None
    try:
        raw, _ = process.communicate(timeout=profile['timeout_s'])
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        raw, _ = process.communicate()
        state = 'TIMEOUT'
    D._settle_stage(stage, process)
    cut = len(raw) > profile['max_output_bytes']
    raw = raw[:profile['max_output_bytes']]
    state = state or ('FAILED' if cut else 'COMPLETE' if process.returncode == 0 else 'FAILED')
    names = _all_failing(profile.get('failures'), raw)
    return {'state': state, 'exit_code': process.returncode, 'wall_ms': int((time.perf_counter() - started) * 1000), 'failing_total': len(names),
            'failing_complete': not cut and state != 'TIMEOUT', 'names': names}


def _newly(check: dict, base: dict) -> dict:
    row = check['_row']
    if check['state'] not in EVIDENCE_STATES or check['failing_complete'] is False:
        return {'known': False, 'reason': 'this check did not finish its own output, so its failing names are not evidence'}
    if base.get('state') not in EVIDENCE_STATES or not base.get('failing_complete'):
        return {'known': False, 'reason': 'the same check on the live commit %s: %s' % ('could not run' if base.get('state') == 'UNAVAILABLE' else 'did not finish', base.get('reason') or base.get('state'))}
    path = Path(row.get('output_root') or '') / 'stdout.txt'
    raw = path.read_bytes() if path.is_file() else b''
    if 'sha256:' + hashlib.sha256(raw).hexdigest() != row.get('stdout_sha256'):
        return {'known': False, 'reason': 'the retained output of this check is not its recorded bytes'}
    lane_names, known = _all_failing(check['_profile'].get('failures'), raw), set(base['names'])
    newly = [name for name in lane_names if name not in known]
    return {'known': True, 'names': newly, 'total': len(newly), 'base_failing_total': base['failing_total'], 'lane_failing_total': len(lane_names)}


# ------------------------------------------------------------------------------------------------ what moves with it

def _reviews_after(root: Path, project: str, row: dict, files: list) -> list:
    """Reviews whose Source basis is read in the live tree after this adoption (this lane's, or an already ADOPTED lane's)
    and that consumed a changed file at another version than the one this adoption writes: they will read STALE."""
    from laplace.work import project_work
    after = {item['path']: item['after_sha256'] for item in files}
    out = []
    for task in project_work._tasks(project, root).values():
        for review in task.get('phases') or ():
            basis = review.get('source_basis') if review.get('phase') == 'review' else None
            if not basis or not str(basis.get('repository', '')).startswith(D.LANE_PREFIX):
                continue
            other = D.lane_row(task) if basis['repository'] == D.LANE_PREFIX + str(task['id']) else None
            if basis['repository'] != row['id'] and not (other and other['state'] == 'ADOPTED'):
                continue
            differs = sorted(path for path, pin in (review.get('pins') or {}).items() if path in after and after[path] != pin)
            if differs:
                out.append({'review_id': review['id'], 'work_id': task['id'], 'work_title': task.get('title'), 'obligation_id': review.get('obligation_id'),
                            'verdict': review.get('verdict'), 'files': differs[:8],
                            'reason': 'it reviewed %s at another version than this adoption writes' % ', '.join(differs[:3])})
    return out


def _carry_preview(root: Path, files: list) -> dict:
    """The publication inputs the ordinary close carries, from the close carry's own function (source_kernel_input
    close_inputs), with the inputs that pin a changed file. Their state after the reload is not stated here: the kernel
    compares meaning only in the loaded live tree (ruling D8), so the close states it after the new code is loaded."""
    from laplace.representation import source_publication as SP
    from laplace.engine import source_kernel_input as SKI
    touched = {item['path'] for item in files}
    try:
        inputs = SP.selections(root)
        if not inputs:
            return {'read': 'source_kernel_input.close_inputs', 'inputs_total': 0, 'inputs': [],
                    'note': 'This root records no publication inputs, so the close carries none.'}
        carry = SKI.close_inputs(root, inputs, SP.current(root))
    except (ValueError, OSError) as exc:
        return {'read': 'source_kernel_input.close_inputs', 'unavailable': str(exc)[:300]}
    rows = []
    for lid, state in sorted(carry['currentness'].items()):
        projection = carry['leaves'].get(lid) or {}
        try:
            pins = json.loads(projection['exact_descent']['reference'])['source_inputs']
        except (KeyError, TypeError, ValueError):
            pins = []
        paths = sorted({item.get('path') for item in pins if isinstance(item, dict)} & touched)
        if paths:
            rows.append({'node_id': lid, 'today': state.get('state'), 'today_reason': state.get('reason'), 'changed_files': paths})
    return {'read': 'source_kernel_input.close_inputs', 'inputs_total': len(carry['currentness']), 'inputs': rows,
            'note': 'The close re-reads these after the reload; meaning is compared only in the loaded live tree.'}


# ------------------------------------------------------------------------------------------------ preview

def _live_problems(live: Path, row: dict, files: list) -> list:
    from laplace.core import checkout as serving
    problems = []
    if Path(row['source_checkout']).resolve() != serving.source_tree().resolve():
        problems.append('The lane was cut from %s, and the app now runs from %s: Adopt refuses. Discard this lane and cut a new one.'
                        % (row['source_checkout'], serving.source_tree()))
        return problems
    head = D._base(live)
    if head != row['base']:
        problems.append('The live tree has moved to %s since the lane was cut from %s: Adopt refuses. Discard this lane and cut a new one from the current commit.'
                        % (head[:7], row['base'][:7]))
        return problems
    paths = [item['path'] for item in files]
    if paths:
        dirty = _git_ok(['-C', str(live), 'status', '--porcelain=v1', '--untracked-files=all', '--', *paths]).decode().strip()
        if dirty:
            problems.append('These files have uncommitted changes in the live tree: %s. Adopt refuses; commit or set them aside first.'
                            % ', '.join(line[3:] for line in dirty.splitlines()[:4]))
    return problems


def _active_turns() -> int:
    from laplace.writing import turn_jobs
    return turn_jobs.active_turn_count()


def _gate(diff: dict, checks: list, live_problems: list, applies) -> list:
    """Every reason Adopt is refused for this preview, as sentences beside the Adopt button. Only the checks are required:
    an independent review is advisory (orchestrator decision 1)."""
    out = list(live_problems)
    if not diff['files']:
        out.append('The lane holds no change against its base; there is nothing to adopt.')
    if diff['unrecorded']:
        out.append('These lane files changed with no development effect recording them: %s. Adopt moves only recorded changes.' % ', '.join(diff['unrecorded'][:4]))
    if diff['unfinished_effects']:
        out.append('An apply in the lane did not finish (%s); every effect must be committed first.' % ', '.join(diff['unfinished_effects'][:3]))
    if not checks:
        out.append('No check has run on this lane. Run at least one check profile first.')
    for check in checks:
        if not check['current']:
            out.append('The lane files changed after the %s check; run it again.' % check['name'])
        elif not check['newly'].get('known'):
            out.append('Newly failing names of %s are not known: %s.' % (check['name'], check['newly']['reason']))
        elif check['newly']['total']:
            out.append('%s has %d newly failing test%s; Adopt refuses while a check is newly failing.' % (check['name'], check['newly']['total'], '' if check['newly']['total'] == 1 else 's'))
    if applies is not True and applies is not None:
        out.append('The lane diff does not apply to the live commit: %s' % applies)
    return out


def _public_check(check: dict) -> dict:
    return {key: value for key, value in check.items() if not key.startswith('_')}


def _observe(root: Path, project: str, task: dict, row: dict) -> tuple[dict, dict, str]:
    """What Adopt would move, observed now: (the preview as shown, the facts Adopt depends on, their sha256). Nothing is
    written: the scratch copy lives in a temporary directory removed before this returns. preview() shows it; Adopt calls it
    again under its locks and refuses unless the facts' digest equals the one its offer named, so no retained copy of a
    preview exists to outlive the lane (judge wave13b adopt r1, 'preview-holder')."""
    started, live = time.perf_counter(), Path(row['source_checkout'])
    diff = _diff(task, row)
    checks = _checks(task, row, diff['files'])
    live_problems = _live_problems(live, row, diff['files'])
    applies, scratch_note, base_runs = None, None, {}
    if not live_problems and diff['files']:
        with tempfile.TemporaryDirectory(prefix='laplace-adopt-scratch-') as tmp:
            where = Path(tmp)
            roots = sorted({pattern.split('/')[0] for check in checks for pattern in check['_profile'].get('inputs') or ()} |
                           {path.split('/')[0] for check in checks for path in (check['_profile'].get('dependencies') or {})} |
                           {item['path'].split('/')[0] for item in diff['files']})
            scratch = _scratch(live, row['base'], roots, where)
            size = D._tree_bytes(scratch)
            for check in checks:
                if check['current']:
                    base_runs[check['id']] = _base_run(root, scratch, check, where)
            (where / 'lane.patch').write_bytes(diff['patch'])
            env = {**os.environ, 'GIT_CEILING_DIRECTORIES': str(where)}
            done = _run(['apply', '--whitespace=nowarn', str(where / 'lane.patch')], cwd=str(scratch), env=env)
            applies = True if done.returncode == 0 else (done.stderr or done.stdout).decode('utf-8', 'replace').strip()[-300:]
            scratch_note = {'commit': row['base'], 'bytes': size, 'paths': roots}
        scratch_note['removed'] = not Path(tmp).exists()
    for check in checks:
        base = base_runs.get(check['id'])
        check['base'] = None if base is None else {key: value for key, value in base.items() if key != 'names'}
        check['newly'] = {'known': False, 'reason': 'no run on the live commit (the check is not current or the live tree moved)'} if base is None else _newly(check, base)
    refusals = _gate(diff, checks, live_problems, applies)
    reviews = _reviews_after(root, project, row, diff['files'])
    live_head = D._base(live)
    facts = {'schema_version': SCHEMA, 'project': project, 'work_id': task['id'], 'lane': {key: row[key] for key in ('id', 'branch', 'base', 'checkout')},
             'live_head': live_head, 'files': [{key: item[key] for key in ('path', 'before_sha256', 'after_sha256')} for item in diff['files']],
             'patch_sha256': 'sha256:' + hashlib.sha256(diff['patch']).hexdigest(), 'checks': {c['id']: c['name'] for c in checks if c['current']},
             'base_failing': {cid: run.get('names') for cid, run in base_runs.items()}, 'reviews': [item['review_id'] for item in reviews],
             'refusals': refusals}
    digest = 'sha256:' + hashlib.sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    shown = {'id': 'DP-' + digest[len('sha256:'):][:24], 'observed_at': _now(), 'work': {'id': task['id'], 'title': task.get('title')},
             'lane': facts['lane'], 'live_head': live_head, 'live_root': str(live),
             'files': [{key: item[key] for key in ('path', 'change', 'flagged', 'added', 'removed', 'before_sha256', 'after_sha256')} for item in diff['files']],
             'checks': [_public_check(check) for check in checks], 'applies': applies, 'scratch': scratch_note,
             'reviews_stale': reviews, 'carry': _carry_preview(root, diff['files']), 'wall_ms': int((time.perf_counter() - started) * 1000),
             'active_turns': _active_turns()}
    return shown, facts, digest


def preview(root: Path, project: str, payload: dict, door: dict) -> dict:
    task = _task(root, project, str(payload['work_id']))
    row = D.lane_row(task)
    if row is None or row['state'] != 'ACTIVE':
        raise Refused('Work %s has no active lane to preview%s.' % (task['id'], '' if row is None else ' (its lane is %s)' % row['state'].lower()))
    shown, facts, digest = _observe(root, project, task, row)
    refusals = facts['refusals']
    offer = {'action': 'adopt', 'refused': refusals,
             'request': None if refusals else {'action': 'adopt', 'work_id': task['id'], 'branch': row['branch'], 'preview_id': shown['id'], 'preview_sha256': digest}}
    return {'preview': shown, 'offers': [offer]}


# ------------------------------------------------------------------------------------------------ adopt

def _publication_free(root: Path) -> bool:
    """Ruling D6: the owner's publication_lock waits 20 s; Adopt refuses at once instead. This probes the owner's own lock
    file (source_publication.publication_lock: <root>/contract/.current-publication.lock) without waiting, then releases it;
    Adopt then takes the owner's lock itself. tests/test_development_adoption.py holds the owner's lock and sees the refusal."""
    from filelock import FileLock, Timeout
    probe = FileLock(str(Path(root).resolve() / 'contract/.current-publication.lock'), timeout=0)
    try:
        probe.acquire(timeout=0)
    except Timeout:
        return False
    probe.release()
    return True


LOCK_REFUSAL = {'dispatch': 'Another development action holds the Work dispatch lock right now: Adopt refuses rather than waits. Press Adopt again in a moment.',
                'publication': 'A close (sew up) is publishing right now and holds the publication lock: Adopt refuses rather than waits. Press Adopt again when the close has finished.'}


def adopt(root: Path, project: str, payload: dict, door: dict) -> dict:
    from filelock import Timeout
    from laplace.representation import source_publication as SP
    from laplace.work import project_work
    if door.get('origin') != 'human':
        raise Refused('Adopt is pressed only by the author at the human door (POST /work/development); a native turn is refused.')
    for key in ('branch', 'preview_id', 'preview_sha256'):
        if not payload.get(key):
            raise Refused('Adopt sends the request its preview offered (branch, preview_id, preview_sha256); preview again.')
    lock = project_work.dispatch_lock(root)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise Refused(LOCK_REFUSAL['dispatch']) from None
    try:
        if not _publication_free(root):
            raise Refused(LOCK_REFUSAL['publication'])
        try:
            with SP.publication_lock(root):
                return _adopt_locked(root, project, payload, door)
        except Timeout:
            raise Refused(LOCK_REFUSAL['publication']) from None
    finally:
        lock.release()


def _commit_by_trailer(live: Path, base: str, adoption_id: str):
    out = _git_ok(['-C', str(live), 'log', '--format=%H%x1f%P%x1f%(trailers:key=' + ADOPTION_TRAILER + ',valueonly,separator=%x2c)', base + '..HEAD']).decode()
    for line in out.splitlines():
        sha, parents, ids = (line.split('\x1f') + ['', ''])[:3]
        if adoption_id in [item.strip() for item in ids.split(',')]:
            return {'commit': sha, 'parent': parents.split(' ')[0]}
    return None


def _adopt_locked(root: Path, project: str, payload: dict, door: dict) -> dict:
    from laplace.representation import source_publication as SP
    from laplace.work import project_work
    task = _task(root, project, str(payload['work_id']))
    row = D.lane_row(task)
    if row is None:
        raise Refused('Work %s has no lane.' % task['id'])
    if row.get('branch') != payload['branch']:
        raise Refused('The lane of this Work is now %s, not %s; read again and preview.' % (row.get('branch'), payload['branch']))
    if row['state'] == 'ADOPTED':
        return {'ok': True, 'already': 'ADOPTED', **adoption(root, project, {'work_id': task['id']}, door)}
    if row['state'] != 'ACTIVE':
        raise Refused('The lane is %s; only an active lane is adopted.' % row['state'].lower())
    live = Path(row['source_checkout'])
    pending = row.get('adoption') if (row.get('adoption') or {}).get('state') == 'PREPARED' else None
    found = _commit_by_trailer(live, row['base'], pending['id']) if pending else None
    if found is None:
        if pending is None:
            # Under both locks: observe again what the preview showed and Adopt only the same facts (nothing was retained).
            _shown, facts, digest = _observe(root, project, task, row)
            if facts['refusals']:
                raise Refused('Adopt refuses: ' + ' '.join(facts['refusals']))
            if digest != payload['preview_sha256'] or 'DP-' + digest[len('sha256:'):][:24] != payload['preview_id']:
                raise Refused('What Adopt would move is no longer what the preview showed (the lane, a check or the live tree changed); preview again.')
            diff = _diff(task, row)
            applied_already = False
        else:
            # A retry after a crash between PREPARED and the commit: the PREPARED row carries the facts verified under the locks.
            diff = _diff(task, row)
            shown = [{key: item[key] for key in ('path', 'before_sha256', 'after_sha256')} for item in diff['files']]
            if shown != pending['files'] or 'sha256:' + hashlib.sha256(diff['patch']).hexdigest() != pending['patch_sha256']:
                raise Refused('The lane changed since its adoption was prepared; preview again.')
            applied_already = all(D._pin(live / item['path']) == item['after_sha256'] for item in diff['files'])
            problems = [] if applied_already else _live_problems(live, row, diff['files'])
            if problems:
                raise Refused(' '.join(problems))
        if _active_turns():
            raise Refused('A turn is running in this app; Adopt changes the code it runs. Stop it or let it finish, then press Adopt again.')
        try:
            SP.assert_no_pending(root)
        except ValueError as exc:
            raise Refused('A publication operation is unresolved (%s): Adopt refuses until the close has settled it.' % str(exc)[:200]) from None
        actor = D._actor(root, project, payload, door)
        if pending is None:
            pending = {'id': 'DA-' + hashlib.sha256(json.dumps([task['id'], row['branch'], facts['patch_sha256'], _now()]).encode()).hexdigest()[:24],
                       'state': 'PREPARED', 'base': row['base'], 'branch': row['branch'], 'preview_id': payload['preview_id'], 'preview_sha256': digest,
                       'files': facts['files'], 'patch_sha256': facts['patch_sha256'], 'checks': facts['checks'],
                       'base_failing': facts['base_failing'], 'reviews': facts['reviews'], 'prepared_at': _now(), 'actor': actor}
            project_work._append(root, {**row, 'ts': _now(), 'adoption': pending})
        found = _apply_and_commit(root, live, task, row, pending, diff, applied_already)
    if found['parent'] != row['base']:
        raise Refused('The commit carrying Adoption-Id %s does not sit on the lane base; nothing more is recorded.' % pending['id'])
    revoked = []
    for grant in _lane_grants(task, row).values():
        if grant.get('state') == 'ACTIVE':
            D.revoke(root, project, {'grant_id': grant['id'], 'reason': 'lane adopted as %s' % found['commit'][:12]}, door)
            revoked.append(grant['id'])
    removal = D._remove_lane(row)
    final = {**{k: v for k, v in row.items() if k != 'adoption'}, 'state': 'ADOPTED', 'ts': _now(), 'adopted_at': _now(), 'revoked_grants': revoked, 'removal': removal,
             'adoption': {**pending, 'state': 'COMMITTED', 'commit': found['commit'], 'committed_at': _now()}}
    project_work._append(root, final)
    return {'ok': True, **adoption(root, project, {'work_id': task['id']}, door)}


def _apply_and_commit(root: Path, live: Path, task: dict, row: dict, pending: dict, diff: dict, applied_already: bool) -> dict:
    from laplace.work import project_work
    paths = [item['path'] for item in diff['files']]
    with tempfile.TemporaryDirectory(prefix='laplace-adopt-') as tmp:
        patch = Path(tmp) / 'lane.patch'
        patch.write_bytes(diff['patch'])
        if not applied_already:
            check = _run(['-C', str(live), 'apply', '--index', '--check', str(patch)])
            if check.returncode != 0:
                reason = (check.stderr or check.stdout).decode('utf-8', 'replace').strip()[-300:]
                project_work._append(root, {**row, 'ts': _now(), 'adoption': {**pending, 'state': 'REFUSED', 'reason': reason, 'refused_at': _now()}})
                raise Refused('The lane diff does not apply to the live tree; nothing moved: ' + reason)
            _git_ok(['-C', str(live), 'apply', '--index', str(patch)])
        message = Path(tmp) / 'message'
        message.write_text('Adopt development lane %s for %s\n\n%d file%s from the lane cut at %s, applied on the author\'s Adopt.\n\n%s: %s\n%s: %s\n'
                           % (row['branch'], task.get('title') or task['id'], len(paths), '' if len(paths) == 1 else 's', row['base'][:12],
                              TRAILER, task['id'], ADOPTION_TRAILER, pending['id']))
        done = _run(['-C', str(live), 'commit', '--quiet', '--only', '-F', str(message), '--', *paths])
        if done.returncode != 0:
            reason = (done.stderr or done.stdout).decode('utf-8', 'replace').strip()[-300:]
            undone = _run(['-C', str(live), 'apply', '--index', '-R', str(patch)])
            project_work._append(root, {**row, 'ts': _now(), 'adoption': {**pending, 'state': 'ROLLED_BACK' if undone.returncode == 0 else 'PARTIAL',
                                                                          'reason': reason, 'refused_at': _now()}})
            raise Refused('The local commit failed and the change was %s: %s' % ('taken back out of the live tree' if undone.returncode == 0 else 'NOT taken back (see git status)', reason))
    found = _commit_by_trailer(live, row['base'], pending['id'])
    if found is None:
        raise Refused('The commit was made but its Adoption-Id trailer is not found from the lane base; nothing more is recorded.')
    return found


# ------------------------------------------------------------------------------------------------ after: the anchor and the read

def anchor(root: Path, project: str, work_id: str, grant_row: dict) -> dict | None:
    """D5: the currentness anchor of an ADOPTED lane's review basis, or None for every other basis. The checkout is the live
    root the resolver gives for currentness; in_history says whether the adoption commit A is live HEAD or its ancestor;
    pin(path) reads one reviewed file of the live root through the owner's fence (shape, glob, git internals, credential
    names) and refuses a symlink, read-only. Grant, apply and check never resolve here and keep the protected-root refusal."""
    from laplace.work import project_work
    if not str(grant_row.get('repository', '')).startswith(D.LANE_PREFIX):
        return None
    row = D.lane_row(project_work._tasks(project, root).get(work_id))
    adoption_row = (row or {}).get('adoption') or {}
    if row is None or row['state'] != 'ADOPTED' or adoption_row.get('state') != 'COMMITTED' or grant_row['repository'] != row['id']:
        return None
    live = D.basis_checkout(root, project, work_id, grant_row['repository'], 'currentness')
    in_history = _run(['-C', str(live), 'merge-base', '--is-ancestor', adoption_row['commit'], 'HEAD']).returncode == 0

    def pin(raw):
        relative = Path(D._fenced(root, Path(grant_row['checkout']), grant_row, raw)).relative_to(Path(grant_row['checkout'])).as_posix()
        path = live / relative
        if path.resolve() != live.resolve() / relative:
            raise ValueError('%s crosses a symlink in the live tree; only real files are read.' % relative)
        return D._pin(path)
    return {'checkout': live, 'commit': adoption_row['commit'], 'in_history': in_history, 'pin': pin}


def _public_adoption(row: dict) -> dict | None:
    value = row.get('adoption') if row else None
    if not value:
        return None
    return {key: copy.deepcopy(value.get(key)) for key in ('id', 'state', 'commit', 'base', 'branch', 'files', 'prepared_at', 'committed_at', 'reason', 'preview_id')} | \
        {'trailer': {TRAILER: row['work_id'], ADOPTION_TRAILER: value.get('id')}}


def adoption(root: Path, project: str, payload: dict, door: dict) -> dict:
    """The lane's adoption as its row records it, the anchor's history standing, and the review owner's current standing
    (project_work_review.facet) of every review this adoption named in its preview."""
    from laplace.work import project_work, project_work_review
    task = _task(root, project, str(payload['work_id']))
    row = D.lane_row(task)
    value = _public_adoption(row)
    out = {'work': {'id': task['id'], 'title': task.get('title')}, 'lane': D._public_lane(task, row), 'adoption': value, 'observed_at': _now(),
           'read': 'development_adoption.adoption; review standing from project_work_review.facet'}
    if not value or value['state'] != 'COMMITTED':
        return out
    live = Path(row['source_checkout'])
    out['in_live_history'] = _run(['-C', str(live), 'merge-base', '--is-ancestor', value['commit'], 'HEAD']).returncode == 0
    named = set(row['adoption'].get('reviews') or ())
    tasks = project_work._tasks(project, root)
    standing = []
    for other in tasks.values():
        lane_reviews = {review['id'] for review in other.get('phases') or () if review.get('phase') == 'review'
                        and (review.get('source_basis') or {}).get('repository') == row['id']}
        wanted = named | lane_reviews
        if not wanted.intersection(review.get('id') for review in other.get('phases') or ()):
            continue
        facet = project_work_review.facet(other, root, tasks=tasks, project=project) or {}
        for entry in facet.get('obligations') or ():
            if entry.get('review_id') in wanted:
                standing.append({'review_id': entry['review_id'], 'work_id': other['id'], 'work_title': other.get('title'), 'obligation_id': entry.get('id'),
                                 'currentness': entry.get('currentness'), 'reason': entry.get('currentness_reason')})
    out['reviews'] = standing
    return out


def closeout(task: dict):
    """The closeout header's adoption field (project_work_continuity.closeout): the lane row's adoption, else NOT_RECORDED."""
    row = D.lane_row(task)
    value = (row or {}).get('adoption')
    if not value:
        return 'NOT_RECORDED'
    return {'state': value.get('state'), 'commit': value.get('commit'), 'branch': value.get('branch'), 'at': value.get('committed_at') or value.get('prepared_at'),
            'lane': row['state'], 'read': {'http': {'method': 'POST', 'path': '/work/development', 'payload': {'action': 'adoption', 'work_id': task['id']}}}}


# ------------------------------------------------------------------------------------------------ the door

def handle(root: Path, project: str, payload: dict, door: dict) -> dict:
    from laplace.core import admission
    admission.admit_owner_payload('development_adoption', payload, contract(), project=project)
    action = payload['action']
    if action == 'preview':
        return preview(root, project, payload, door)
    if action == 'adoption':
        return adoption(root, project, payload, door)
    return adopt(root, project, payload, door)
