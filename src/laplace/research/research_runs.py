"""RESEARCH RUNS (S1 B7): producer declarations, launch admission, supervised run status, cancel.

research_runner.py stays the supervisor and cleanup authority; this module admits and reads.
The launch token and run index are reserved BEFORE activation, a pending supervision hint is
durable, and nothing waits under the launch lock or starts a watcher.

  _producer / register_producer / _checked_args        declared executable producers.
  producer_dependencies / run_inputs_current           a producer's declared inputs and their digests.
  launch                                               admit (reserve token, index, pending hint), then
                                                       activate the supervisor.
  _run_status_uncached / _run_status / _project_run_status / _supervisor_active / _pending_job /
  _declared_run_home / _runs / active_runs             an exact issued run's identity, currentness,
                                                       cleanup and capability fields.
  run_status_explanation / _run_identity_labels        what a run status word means.
  cancel                                               request cancellation of one exact live run.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
import re
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_PRODUCERS = "research_producers.json"
_RUNS = "research_runs"
_PRODUCER_FLAGS = {"mode": "--mode", "args": "--args-json", "result": "--result"}


def producer_input_contract() -> dict:
    """The existing explicit producer forms; omitted inputs are not coverage."""
    producer = {'type': 'object',
     'required': ['id', 'executable', 'modes', 'allowed_args'],
     'properties': {'id': {'type': 'string'},
                    'executable': {'type': 'string'},
                    'scope': {'enum': ['project', 'manuscript']},
                    'modes': {'type': 'array', 'items': {'enum': ['smoke', 'full']}, 'minItems': 1},
                    'allowed_args': {'type': 'object',
                                     'required': [],
                                     'properties': {},
                                     'additionalProperties': True},
                    'dependencies': {'type': 'array',
                                     'items': {'type': 'string'},
                                     'description': 'Optional declared additional inputs; omission '
                                                    'records no declared dependency coverage.'},
                    'result_path': {'type': 'string'},
                    'timeout_seconds': {'type': 'integer'}},
     'additionalProperties': False}
    return {"anyOf":[producer,
        {"type":"object","required":["producer"],"properties":{"producer":producer},
         "additionalProperties":False}]}


def producer_execution_contract() -> dict:
    """The launch protocol, exposed to sessions before they author a producer."""
    return {"flags": dict(_PRODUCER_FLAGS),
            "cwd": "The declared scope's directory: project root for scope=project, selected manuscript directory otherwise.",
            "invocation": "Python files use the workspace Python; other executables run directly. All receive these three flags.",
            "imports": "The selected Python may use safe-path mode: cwd and the executable directory are not implicit import roots. Author one explicit in-scope bootstrap entry, then use qualified package imports. Declare that entry and every transitive project module in dependencies; PRESENT proves bytes, not importability. No directories are added automatically.",
            "mode": "smoke or full, explicitly selected from the registered modes",
            "args": "One JSON object containing only the registered allowed_args, not separate per-argument flags.",
            "result": "An absolute output path. Write the result JSON to this exact --result path and exit zero. Printing JSON or a path to stdout does not create the result.",
            "result_path": "Optional result_path is manuscript-relative even for project-scoped producers; {run_id} is expanded. Omit it for a unique supervised path.",
            "completion": "Read run_status and its terminal receipt. COMPLETE requires verified descendant cleanup as well as a new result and zero exit. Launch RUNNING is not terminal authority.",
            "supervision": "Linux procfs, subreaper and pidfd capabilities are required before admission. One detached guardian and supervisor survive caller exit; the survivor cleans the owned tree if one role dies. This is cooperative process ownership, not a security sandbox or protection against simultaneous loss of both owners.",
            "deadline": "timeout_seconds bounds execution; termination, reaping and verification share one additional maximum six-second cleanup attempt. Incomplete or unknown cleanup remains outstanding work.",
            "role_fields":_run_identity_labels(),
            "cleanup_paths":"For validated VERIFIED terminal cleanup: guardian publisher with matching guardian_verification means supervisor primary cleanup plus guardian secondary verification; guardian publisher without it means guardian takeover cleanup; supervisor publisher means survivor cleanup after guardian loss. Unverified, malformed or unsupported combinations have no established path. These labels do not establish success; cleanup.status, remaining and issues remain evidence. Legacy runs without the schema have unrecorded cleanup roles."}


def run_status_read(project: str, run_id: str, root=None) -> tuple[int, dict]:
    """One exact run's status for the HTTP door and the native operation: (status, value)."""
    if not project:
        return 400, {"error": "GET /research/run/status?project=&id= required"}
    if not _logical_run_id(run_id):return 400, {'error':'Select one logical Run ID, not a path.'}
    status_root = Path(root) if root else research_context.repo_root()
    item, manuscript = research_context.project(project, status_root)
    run = _project_run_status(item, manuscript, run_id, status_root) if manuscript else None
    if run and run.get('state')=='COMPLETE':
        from laplace.research import research_records
        run={**run,'record_result':research_records.run_record_actions(status_root,project,run)}
    return (200, run) if run else (404, {"error": "unknown run"})


def _run_identity_labels() -> dict:
    return {'pid':'Launch wrapper / guardian compatibility field, not the producer PID.',
            'supervisor_start_token':'Launch wrapper / guardian compatibility start field, not the supervisor role token.',
            'supervision.roles':'Canonical guardian and supervisor identities for this recorded run.',
            'publisher':'Recorded terminal publisher; not a current-process liveness observation.'}


def run_status_explanation(job: Any, receipt: Any = None, *, receipt_error: str | None = None) -> dict:
    """Pure labels over the observed job/receipt; no copied identities or effects.

    A path label explains a supported retained proof shape. It cannot establish
    cleanup, current process liveness, result provenance or scientific success.
    """
    evidence='Labels explain recorded roles only. Read cleanup.status, remaining and issues for cleanup evidence; execution and result currentness remain separate.'
    unknown={'identity_fields':{},'cleanup_path':{'label':'Cleanup path unestablished',
             'description':'No supported, validated terminal cleanup path is established.'},
             'evidence':evidence}
    if not isinstance(job,dict) or receipt is not None and not isinstance(receipt,dict):return unknown
    supervision=job.get('supervision')
    schema=supervision.get('schema_version') if isinstance(supervision,dict) else None
    receipt_schema=receipt.get('supervision_schema') if isinstance(receipt,dict) else None
    if supervision is None and receipt_schema is None:
        return {'identity_fields':{'pid':'Legacy launch-process field; cleanup role unrecorded.',
                    'supervisor_start_token':'Legacy launch-process start field; cleanup role unrecorded.',
                    'supervision.roles':'Canonical cleanup roles were not recorded under a recognized schema.',
                    'publisher':'No recognized terminal publisher role is established.'},
                'cleanup_path':{'label':'Legacy cleanup path unrecorded',
                    'description':'Do not retrospectively classify a legacy launch process as guardian or supervisor.'},
                'evidence':evidence}
    if schema!='laplace.research-supervision/1' and receipt_schema!='laplace.research-supervision/1':return unknown
    result={**unknown,'identity_fields':_run_identity_labels()}
    if supervision is not None and (not isinstance(supervision,dict)
            or supervision.get('schema_version')!='laplace.research-supervision/1'
            or not isinstance(supervision.get('roles'),dict)):
        return result
    if receipt_error:return result
    if receipt is None or receipt=={}:
        if job.get('state')=='RUNNING':
            result['cleanup_path']={'label':'Cleanup path pending','description':'No terminal cleanup receipt has been observed.'}
        return result
    from laplace.research.research_runner import validated_receipt
    try:validated_receipt(job,receipt)
    except ValueError:return result
    if receipt['supervision']['phase']!='TERMINAL':
        result['cleanup_path']={'label':'Cleanup path pending','description':'The recorded supervision phase is not terminal.'}
        return result
    cleanup=receipt['cleanup']
    # In an unsuccessful secondary check, the runner may retain that check as
    # primary cleanup with no guardian_verification. Absence then proves no path.
    if cleanup.get('status')!='VERIFIED':return result
    role=receipt['publisher']['role']
    if 'guardian_verification' in cleanup:
        secondary=cleanup['guardian_verification']
        valid=(isinstance(secondary,dict) and secondary.get('status')=='VERIFIED'
               and secondary.get('remaining')==[] and secondary.get('issues')==[]
               and isinstance(cleanup.get('deadline_monotonic'),(int,float))
               and not isinstance(cleanup.get('deadline_monotonic'),bool)
               and isinstance(secondary.get('deadline_monotonic'),(int,float))
               and not isinstance(secondary.get('deadline_monotonic'),bool)
               and secondary.get('deadline_monotonic')==cleanup['deadline_monotonic']
               and cleanup['deadline_monotonic']==receipt['supervision'].get('cleanup_deadline_monotonic')
               and secondary.get('budget_seconds')==cleanup.get('budget_seconds')==6.)
        if not valid or role!='guardian':return result
        path={'label':'Supervisor cleanup; guardian verification',
              'description':'The supervisor recorded primary cleanup, then the guardian recorded the separate matching secondary verification.'}
    elif role=='guardian':
        path={'label':'Guardian takeover cleanup',
              'description':'The guardian published its primary cleanup without a separate guardian_verification in this validated verified receipt.'}
    elif role=='supervisor':
        path={'label':'Supervisor survivor cleanup after guardian loss',
              'description':'The supervisor is the recorded survivor publisher after guardian loss; the compatibility fields still name the original guardian.'}
    else:return result
    return {**result,'cleanup_path':path}


def producer_dependencies(base: Path, producer: dict) -> list[dict]:
    """Explicit input/code files, relative to the producer's declared scope."""
    paths = producer.get("dependencies", [])
    if not isinstance(paths, list) or any(not isinstance(p, str) or not p for p in paths):
        raise ValueError("producer dependencies must be a list of relative file paths")
    return [research_observation._relative_digest(base, path) for path in dict.fromkeys(paths)]


def run_inputs_current(job: dict, *, _digest_cache: dict | None = None) -> bool:
    expected = job.get("provenance", {}).get("dependencies")
    if expected is None:  # Older receipts did not pin these inputs.
        return True
    base = Path(job["producer_base"])
    return expected == [research_observation._relative_digest(base, row["path"],_cache=_digest_cache) for row in expected]


def _logical_run_id(value) -> bool:
    return isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}',value))


def _run_job_path(home: Path, ident: str) -> Path | None:
    """Only one logical job in the actual research_runs metadata family."""
    if not _logical_run_id(ident):return None
    path=research_context.inside(home,f'{_RUNS}/{ident}.json')
    expected=(home/_RUNS).resolve()
    return path if path is not None and path.parent==expected and path.parent.name==_RUNS and path.name==ident+'.json' else None


def _result_target(manuscript: Path, job: dict) -> Path:
    """The recorded relative/absolute result must identify one owned target.

    Manuscript here is the located job's Research home, including an explicitly
    relocated export. Never use the whole repository as a fallback result fence.
    """
    raw=job.get('result_path');absolute=job.get('result_absolute')
    if (not isinstance(raw,str) or not raw or Path(raw).is_absolute() or '..' in Path(raw).parts
            or not isinstance(absolute,str) or not absolute):
        raise ValueError('Run result requires exact relative and absolute owner coordinates.')
    selected=research_context.inside(manuscript,raw)
    captured=research_context.inside(manuscript,absolute)
    if selected is None or captured is None or selected!=captured:
        raise ValueError('Run result coordinates disagree or escape the located Research home.')
    return selected


def _run_status_uncached(manuscript: Path, run_id: str, *,
                         _digest_cache: dict | None = None) -> dict | None:
    path = _run_job_path(manuscript,run_id)
    if path is None:
        return None
    job, error = research_observation._read_object(path, {})
    if error or not job:
        return None
    if job.get('id')!=run_id:return {'id':run_id,'state':'UNAVAILABLE','reason':'Run metadata identity differs from its logical job name.'}
    from laplace.projects.writing_portability import relocate_run
    try:
        job = relocate_run(job, manuscript)
    except ValueError as exc:
        return {**job, 'state': 'UNAVAILABLE', 'reason': str(exc)}
    receipt, receipt_error = research_observation._read_object(path.parent/(path.stem+'.receipt.json'), {})
    job={**job,'status_explanation':run_status_explanation(job,receipt,receipt_error=receipt_error)}
    supervision = job.get('supervision')
    if supervision is not None and (not isinstance(supervision,dict)
            or supervision.get('schema_version')!='laplace.research-supervision/1'
            or not isinstance(supervision.get('roles'),dict)):
        return {**job,'state':'CLEANUP_UNRESOLVED','cleanup':{'status':'UNKNOWN'},
                'cleanup_unresolved':True,'reason':'job supervision metadata is malformed or unsupported'}
    supervision=supervision or {}
    if supervision.get('schema_version') == 'laplace.research-supervision/1':
        if receipt:
            from laplace.research.research_runner import validated_receipt
            try: validated_receipt(job,receipt)
            except ValueError as exc:
                receipt,receipt_error={},str(exc)
        if receipt_error:
            job.update(state='CLEANUP_UNRESOLVED',cleanup={'status':'UNKNOWN'},cleanup_unresolved=True,
                       reason='terminal/progress receipt unavailable: '+str(receipt_error))
            return job
    try:result_path=_result_target(manuscript,job)
    except ValueError as exc:return {**job,'state':'UNAVAILABLE','reason':str(exc)}
    if receipt:
        job.update(receipt)
        if (supervision.get('schema_version') == 'laplace.research-supervision/1'
                and (receipt.get('supervision') or {}).get('phase')=='TERMINAL'
                and (receipt.get('cleanup') or {}).get('status') != 'VERIFIED'):
            job.update(state='CLEANUP_UNRESOLVED', cleanup_unresolved=True)
        if job.get('state')=='COMPLETE' and research_observation._present(result_path):
            now=research_observation._digest(result_path);job['result_provenance']=now
            if now.get('sha256')!=receipt.get('result_sha256'): job['state']='STALE';job['reason']='result changed after successful receipt'
            producer_path = research_context.inside(Path(job.get('producer_base') or manuscript), str(job.get('producer_path') or ''))
            current_producer = research_observation._digest(producer_path) if producer_path is not None else {"status": "REFUSED"}
            current_producer["path"] = str(job.get('producer_path') or '')
            current_producer["scope"] = (job.get('provenance') or {}).get('producer', {}).get('scope', 'manuscript')
            declared, declaration_error = _producer(manuscript, str(job.get('producer_id') or ''))
            expected = job.get('provenance') or {}
            if current_producer != expected.get('producer'):
                job['state']='STALE';job['reason']='producer code changed after successful receipt'
            elif declaration_error or declared is None or research_observation._object_digest(declared) != expected.get('producer_config'):
                job['state']='STALE';job['reason']='producer declaration changed after successful receipt'
            elif not run_inputs_current(job,_digest_cache=_digest_cache):
                job['state']='STALE';job['reason']='declared input or imported code changed after execution'
        elif job.get('state')=='COMPLETE':
            job['state']='FAILED';job['reason']='successful receipt has no current result output'
    elif job.get("state") == "RUNNING":
        # process liveness and the deadline are LIVE facts: sampled now, true only now
        sampled = time.time()
        research_observation._note_live(run_id, {'pid': job.get('pid'), 'deadline_at': job.get('deadline_at'), 'sampled_at': sampled})
        if supervision.get('schema_version') == 'laplace.research-supervision/1':
            alive = _supervisor_active(job, path)
            job.update(cleanup={'status': 'PENDING' if alive else 'UNKNOWN'},
                       cleanup_unresolved=not alive,
                       reason='supervision/cleanup is outstanding' if alive else 'exact cleanup owners unavailable; cleanup is unresolved')
            job['deadline_exceeded'] = sampled > float(job.get('deadline_at', 0))
            return job
        if sampled > float(job.get("deadline_at", 0)):
            # The one-shot research_runner owns its child process group and durable
            # receipt. A passive state read must not kill only the supervisor and
            # orphan that separately-grouped child.
            job["deadline_exceeded"] = True
            job["reason"] = "deadline exceeded; supervisor cleanup receipt is pending"
        else:
            try:
                os.kill(int(job.get("pid")), 0)
            except (OSError, TypeError, ValueError):
                job["state"] = "FAILED"
                job["reason"] = "producer exited without its declared result"
    return job


def _run_status(manuscript: Path, run_id: str, *, _cache: dict | None = None,
                _digest_cache: dict | None = None) -> dict | None:
    key=(str(manuscript.resolve()),str(run_id))
    if _cache is not None and key in _cache:
        saved=_cache[key]
        return dict(saved) if isinstance(saved,dict) else None
    value=_run_status_uncached(manuscript,run_id,_digest_cache=_digest_cache)
    if _cache is not None:_cache[key]=dict(value) if isinstance(value,dict) else None
    return value


def _supervisor_active(job: dict, job_path: Path) -> bool:
    """Match a live supervisor to its durable job without trusting a reused PID."""
    supervision=job.get('supervision')
    if supervision is not None and not isinstance(supervision,dict):return False
    roles = (supervision or {}).get('roles')
    if isinstance(roles, dict) and roles:
        from laplace.research.research_runner import identity_state
        return any(identity_state(roles.get(role)) == 'LIVE' for role in ('guardian', 'supervisor'))
    pid = job.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        stat = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8")
        if stat.rsplit(")", 1)[1].strip().split()[0] == "Z":
            return False
    except (OSError, IndexError):
        return False
    expected_token = job.get("supervisor_start_token")
    if isinstance(expected_token, str) and expected_token:
        from laplace.representation.semantic_cadence import process_start_token
        return process_start_token(pid) == expected_token
    # Compatibility for jobs started before start-token receipts existed.  The
    # command line must still identify this exact supervisor and exact job file.
    try:
        argv = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    args = [item.decode("utf-8", errors="replace") for item in argv if item]
    return ("laplace.research.research_runner" in args and "--job" in args
            and str(job_path.resolve()) in args)


def _declared_run_home(item: Any, root: Path, selected: Path) -> Path:
    """Stable discovery home; manuscript selection is not a job ownership move."""
    declared = item.path(item.manuscript_dir, root) if item and item.manuscript_dir else None
    return (declared or selected).resolve() / _RUNS


def _pending_job(row: Any, root: Path) -> Path | None:
    if (not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']
            or not _logical_run_id(row.get('id'))
            or not isinstance(row.get('launch_token'), str) or not row['launch_token']
            or not isinstance(row.get('project'), str) or not row['project']
            or not isinstance(row.get('job_path'), str) or not 0 < len(row['job_path']) <= 4096):
        return None
    path = research_context.inside(root, row.get('job_path', ''))
    return path if (path and path.parent.name == _RUNS and path.name == row['id'] + '.json') else None


def _scoped_job_path(item, manuscript: Path, root: Path, locator: dict) -> Path | None:
    """A selected project's run locator cannot grant another project's files."""
    path=_pending_job(locator,root)
    if path is None or locator.get('project')!=item.name:return None
    homes=[manuscript.resolve()]
    for raw in (item.project_dir,item.manuscript_dir):
        if raw:
            base=item.path(raw,root)
            if base is not None:homes.append(base.resolve())
    return path if any(path.is_relative_to(base) for base in homes) else None


def _project_run_status(item: Any, manuscript: Path, run_id: str, root: Path) -> dict | None:
    """An active job retains its exact home across a selected-edition change."""
    def unavailable(reason):
        return {'id':run_id,'project':item.name,'state':'UNAVAILABLE','reason':reason,
                'status_explanation':run_status_explanation(None)}
    if not _logical_run_id(run_id):return unavailable('Select one logical Run ID, not a path.')
    index_path = _declared_run_home(item, root, manuscript) / 'index.json'
    index, error = research_observation._read_object(index_path, {})
    if not research_observation._present(index_path):
        legacy = _run_status(manuscript, run_id)
        if (not legacy or legacy.get('cleanup_unresolved')
                or (legacy.get('supervision') or {}).get('schema_version') != 'laplace.research-supervision/1'):
            return legacy  # old exact current-home rows never required this index
        error = 'owned run index is missing'
    if error:
        return unavailable('run locator index unavailable: '+str(error))
    handles = index.get('run_handles', {})
    if not isinstance(handles, dict):
        return unavailable('run locator map malformed')
    if run_id in handles:
        row = handles[run_id]
        path = _scoped_job_path(item,manuscript,root,row)
        if path is None or row.get('project') != item.name or row.get('id') != run_id:
            return unavailable('run locator identity mismatch')
        value = _run_status(path.parent.parent, run_id)
        if (value and value.get('launch_token') == row.get('launch_token')
                and value.get('project') == item.name and value.get('id') == run_id):
            return value
        return unavailable('exact located job missing or identity-mismatched')
    return _run_status(manuscript, run_id)  # explicit legacy current-home contract


class _OutstandingRuns:
    """One active_runs read: each exact job inspected once; nothing is signalled or rewritten."""

    def __init__(self):
        self.active, self.seen = [], set()

    def unresolved(self, project, run_id, reason, path=None):
        self.active.append({'id': run_id, 'project': project, 'state': 'CLEANUP_UNRESOLVED',
                            'cleanup': {'status': 'UNKNOWN'}, 'reason': reason,
                            'job_path': str(path) if path else None})

    def inspect(self, path, hint=None):
        key = str(path)
        if key in self.seen: return
        self.seen.add(key)
        job, error = research_observation._read_object(path, {}, max_bytes=1024*1024)
        project = (hint or {}).get('project') or job.get('project') or ''
        run_id = (hint or {}).get('id') or path.stem
        if (error or not job or (hint and (job.get('id') != run_id
                or job.get('project') != project or job.get('launch_token') != hint.get('launch_token')))):
            self.unresolved(project, run_id, 'pending job is missing, corrupt or identity-mismatched', path)
            return
        supervision=job.get('supervision')
        if (supervision is not None and (not isinstance(supervision,dict)
                or supervision.get('schema_version')!='laplace.research-supervision/1'
                or not isinstance(supervision.get('roles'),dict))
                or hint and supervision is None):
            self.unresolved(project,run_id,'job supervision metadata is malformed or unsupported',path)
            return
        receipt, error = research_observation._read_object(path.with_name(path.stem + '.receipt.json'), {}, max_bytes=1024*1024)
        new = (job.get('supervision') or {}).get('schema_version') == 'laplace.research-supervision/1'
        if new or hint:
            if receipt:
                from laplace.research.research_runner import validated_receipt
                try: validated_receipt(job,receipt)
                except ValueError as exc:
                    error=str(exc);receipt={}
            if (not error and (receipt.get('supervision') or {}).get('phase')=='TERMINAL'
                    and (receipt.get('cleanup') or {}).get('status')=='VERIFIED'):
                return
            observed={**job,**receipt}
            alive=_supervisor_active(observed,path)
            self.active.append({'id':run_id,'project':project,'pid':job.get('pid'),
                           'deadline_at':job.get('deadline_at'),'job_path':key,
                           'state':'RUNNING' if alive and not error and receipt.get('state','RUNNING')=='RUNNING' else 'CLEANUP_UNRESOLVED',
                           'cleanup':receipt.get('cleanup') or {'status':'PENDING' if alive and not error else 'UNKNOWN'},
                           'reason':'owned execution/cleanup pending' if alive and not error else
                                    'exact owner/terminal cleanup proof unavailable; inspect run_status'})
        elif not receipt and job.get('state') == 'RUNNING' and _supervisor_active(job, path):
            self.active.append({'id': run_id, 'project': project, 'pid': job.get('pid'),
                                'deadline_at': job.get('deadline_at'), 'reason': 'legacy live supervisor'})


def active_runs(root: Path | str | None = None) -> list[dict[str, Any]]:
    """Outstanding ownership, including dead-owner unresolved cleanup.

    Existing declared run indices contain compact pending exact job handles,
    never historical result bodies. Hints survive wrapper loss and manuscript
    selection changes. Exact jobs/receipts/identity observations remain authority.
    Legacy live-wrapper discovery is retained; old terminal rows are not scanned
    or retrospectively made blocking. This read never signals or rewrites.
    """
    from laplace.pipeline import registry
    repo = Path(root or research_context.repo_root()).resolve()
    runs = _OutstandingRuns()
    for name, item in registry.all_projects(repo_root=repo).items():
        if not item.manuscript_dir or item.kind == 'site': continue
        _inspect_pending_index(runs, name, item, repo)
    _inspect_legacy_runners(runs, repo)
    runs.active.sort(key=lambda row: (row['project'], row['id']))
    return runs.active


def _inspect_pending_index(runs: _OutstandingRuns, name: str, item, repo: Path) -> None:
    """One project's declared run index: every pending exact handle, or why the index is unresolved."""
    home = _declared_run_home(item, repo, repo)
    if not home.is_dir(): return
    index, error = research_observation._read_object(home / 'index.json', {}, max_bytes=8*1024*1024)
    if error or not index:
        runs.unresolved(name, 'index', 'owned run index missing or corrupt', home / 'index.json')
        return
    pending = index.get('pending_supervision', [])
    if not isinstance(pending, list) or len(pending) > 128:
        runs.unresolved(name, 'index', 'pending supervision index is malformed or exceeds admission bound', home / 'index.json')
        return
    if any(_pending_job(row,repo) is None for row in pending):
        runs.unresolved(name,'index','pending supervision handle is malformed',home/'index.json')
        return
    ids = [row['id'] for row in pending]
    if len(ids)!=len(set(ids)):
        runs.unresolved(name, 'index', 'pending supervision has conflicting duplicate identities', home / 'index.json')
        return
    handles = index.get('run_handles', {})
    for row in pending:
        path = _pending_job(row, repo)
        if (path is None or row.get('project') != name or not isinstance(handles,dict)
                or handles.get(row.get('id')) != row):
            runs.unresolved(name, 'index', 'pending job handle is malformed or outside its project', home / 'index.json')
        else: runs.inspect(path, row)


def _inspect_legacy_runners(runs: _OutstandingRuns, repo: Path) -> None:
    # Compatibility discovery only, once per health observation; never per tree
    # cleanup poll. New jobs remain discoverable through indices without this.
    try: processes = list(Path('/proc').iterdir())
    except OSError: processes = ()
    for process in processes:
        if not process.name.isdigit(): continue
        try:
            argv = [x.decode(errors='replace') for x in (process / 'cmdline').read_bytes().split(b'\0') if x]
            if 'laplace.research.research_runner' not in argv or '--job' not in argv: continue
            path = Path(argv[argv.index('--job') + 1]).resolve()
            path.relative_to(repo)
            if path.parent.name == _RUNS and path.suffix == '.json': runs.inspect(path)
        except (OSError, ValueError, IndexError): continue


def _runs(manuscript: Path, records: list[dict], *, run_cache: dict | None = None,
          digest_cache: dict | None = None) -> list[dict]:
    # A result record may name a run.  This is a bounded explicit lookup, never
    # a directory enumeration on a read path.
    ids = [row.get("run_id") for row in records if isinstance(row.get("run_id"), str)]
    return [run for run_id in dict.fromkeys(ids)
            if (run := _run_status(manuscript,run_id,_cache=run_cache,
                                   _digest_cache=digest_cache))]


def _producer(manuscript: Path, producer_id: str) -> tuple[dict | None, str | None]:
    config, error = research_observation._read_object(manuscript / _PRODUCERS, {"producers": []})
    if error:
        return None, error
    for row in config.get("producers") or []:
        if isinstance(row, dict) and row.get("id") == producer_id:
            return row, None
    return None, "producer is not declared"


def register_producer(project:str,payload:dict,root:Path|None=None)->tuple[int,dict]:
 from filelock import FileLock
 from laplace.core.receipts import bundle, file_receipt
 root=(root or research_context.repo_root()).resolve(); item,manuscript=research_context.project(project,root)
 if not manuscript:return 404,{'error':'unknown project'}
 p=payload.get('producer',payload)
 if not isinstance(p,dict) or not isinstance(p.get('id'),str) or not isinstance(p.get('executable'),str):return 422,{'error':'id and executable required'}
 from laplace.manuscript import manuscript_source
 if manuscript_source.resolve(project,repo_root=root).get('read_only'):return 403,{'error':'source is read-only'}
 scope=p.get('scope','manuscript');base=research_context.project_root(item,root) if scope=='project' else manuscript
 if base is None:return 422,{'error':'project scope requires a declared project directory'}
 exe=research_context.inside(base,p['executable'])
 if scope not in {'project','manuscript'} or exe is None or not exe.is_file():return 422,{'error':'declared executable must stay in its declared scope'}
 if not isinstance(p.get('modes'),list) or not p['modes'] or not set(p['modes'])<= {'smoke','full'}:return 422,{'error':'modes must declare smoke and/or full'}
 try: inputs=producer_dependencies(base,p)
 except ValueError as exc:return 422,{'error':str(exc)}
 if any(row.get('status')!='PRESENT' for row in inputs):return 422,{'error':'producer dependencies must be existing files inside its declared scope','dependencies':inputs}
 t=manuscript/_PRODUCERS
 manuscript.mkdir(parents=True,exist_ok=True)
 with FileLock(str(t)+'.lock',timeout=15):
  before=t.read_bytes() if t.is_file() else None
  config,error=research_observation._read_object(t,{'producers':[]})
  if error:return 409,{'error':error}
  prior=next((x for x in config.get('producers',[]) if isinstance(x,dict) and x.get('id')==p['id']),None)
  rows=[x for x in config.get('producers',[]) if not isinstance(x,dict) or x.get('id')!=p['id']]
  p=dict(p);p['scope']=scope;rows.append(p);config['producers']=rows
  intended=json.dumps(config,indent=2).encode('utf-8')
  tmp=t.with_suffix('.tmp');tmp.write_bytes(intended);tmp.replace(t)
  owned=bundle(files=[file_receipt(root,t,before,intended)],objects=[{
      'owner':'research-producer','id':p['id'],
      'before_revision':research_observation._object_digest(prior) if prior is not None else None,
      'after_revision':research_observation._object_digest(p)}],views=['research'])
 return 201,{'producer':p,'owned_changes':owned}


def _checked_args(producer: dict, supplied: Any, mode: str) -> tuple[dict | None, str | None]:
    modes = producer.get("modes")
    allowed_modes = set(modes if isinstance(modes, list) else (modes or {}).keys())
    if mode not in allowed_modes:
        return None, "mode must be explicitly declared by this producer"
    if not isinstance(supplied, dict):
        return None, "args must be an object"
    schema = producer.get("allowed_args") or {}
    if not isinstance(schema, dict) or set(supplied) - set(schema):
        return None, "args contains an undeclared field"
    checks = {"str": str, "int": int, "float": (int, float), "bool": bool}
    for key, value in supplied.items():
        expected = checks.get(schema[key]) if isinstance(schema[key], str) else None
        if expected is None or not isinstance(value, expected) or (schema[key] == "int" and isinstance(value, bool)):
            return None, f"args.{key} does not match declared type {schema[key]!r}"
    return supplied, None


class _LaunchRefused(Exception):
    """A launch door refusal: the exact (status, body) the door returns."""
    def __init__(self, status: int, body: dict):
        super().__init__(body.get("error"))
        self.status, self.body = status, body


@dataclass
class LaunchAdmission:
    """One admitted run: its job and pending supervision handle are durable before activation."""
    root: Path
    base: Path
    runs_dir: Path
    job: dict
    job_path: Path
    index_path: Path
    stdout: Path
    stderr: Path
    job_before: bytes | None
    index_before: bytes | None
    index_intended: bytes


def launch(project: str, payload: dict, root: Path | None = None) -> tuple[int, dict]:
    """Admit (declared producer, inputs, token and index reservation), then activate the supervisor."""
    root = (root or research_context.repo_root()).resolve()
    item, manuscript = research_context.project(project, root)
    if manuscript is None:
        return 404, {"error": f"unknown project {project!r}"}
    if 'request_id' in payload:
        from filelock import FileLock
        try:run_id,intent = _request_identity(project,payload)
        except ValueError as error:return 422,{'error':str(error)}
        home=_declared_run_home(item,root,manuscript);home.mkdir(parents=True,exist_ok=True)
        with FileLock(str(home/('.request-'+run_id+'.lock')),timeout=15):
            existing=_project_run_status(item,manuscript,run_id,root)
            if existing is not None:
                if existing.get('request_id')!=payload['request_id'] or existing.get('request_intent')!=intent:
                    return 409,{'error':'Existing Research request intent is different or custody is unavailable; no new run admitted.',
                                'id':run_id,'state':'UNKNOWN' if existing.get('request_intent') is None else 'CONFLICT'}
                return 200,{'ok':True,'reused':True,'run':existing,'note':'Existing exact request observed; no activation or admission repeated.'}
            if (manuscript/_RUNS/(run_id+'.json')).exists():
                return 409,{'error':'Existing exact request bytes are unavailable; do not repeat activation.','id':run_id,'state':'UNKNOWN'}
            try:admission=admit_launch(root,project,payload,item,manuscript)
            except _LaunchRefused as refused:return refused.status,refused.body
            return activate(admission)
    try:
        admission = admit_launch(root, project, payload, item, manuscript)
    except _LaunchRefused as refused:
        return refused.status, refused.body
    return activate(admission)


def _request_identity(project,payload):
    from laplace.core.identity import canonical_digest
    request=payload.get('request_id')
    if not isinstance(request,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{8,160}',request):
        raise ValueError('Research request_id is one stable 8–160 character identity.')
    value={key:payload.get(key) for key in ('producer_id','mode','args','runtime_seconds')}
    return 'run-'+canonical_digest([project,request])[7:23],canonical_digest(value)


def inspect_request(project: str, payload: dict, root: Path | None = None) -> dict:
    """Pure exact-request observation in the existing run/index custody.

    NONE permits only an explicit identical request. It does not certify that an
    unobserved process never existed or authorize a different request identity.
    """
    root = (root or research_context.repo_root()).resolve()
    run_id, intent = _request_identity(project, payload)
    def observed(value):
        return {**value, 'request_id':payload['request_id'], 'intent_digest':intent,
                'original_request':copy.deepcopy(payload), 'read':request_read(project,payload),
                **({'run_read':{'native':{'operation':'run_status','payload':{'id':run_id}},
                    'http':{'method':'GET','url':'/research/run/status?'+_query({'project':project,'id':run_id})}}}
                   if value['effect']=='RECORDED' else {})}
    item, manuscript = research_context.project(project, root)
    if manuscript is None:
        return observed({'effect': 'UNKNOWN', 'id': run_id, 'reason': 'Original Research home is unavailable.'})
    existing = _project_run_status(item, manuscript, run_id, root)
    if existing is not None:
        if existing.get('request_id') != payload['request_id'] or existing.get('request_intent') != intent:
            return observed({'effect': 'UNKNOWN' if existing.get('request_intent') is None else 'CONFLICT',
                    'id': run_id, 'reason': 'Original run intent/custody cannot be matched.'})
        return observed({'effect': 'RECORDED', 'id': run_id, 'run': existing})
    if (manuscript / _RUNS / (run_id + '.json')).exists():
        return observed({'effect': 'UNKNOWN', 'id': run_id, 'reason': 'Original run record cannot be read.'})
    return observed({'effect': 'NONE', 'id': run_id})


def _query(values):
    from urllib.parse import urlencode
    return urlencode(values)


def request_read(project, payload):
    """Exact pure original launch request; its identity is not a second launch."""
    return {'native':{'operation':'run_status','payload':{'request':copy.deepcopy(payload)}},
            'http':{'method':'GET','url':'/research/run/request?'+_query({'project':project,
                'request':json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False)})}}


def producer_launch_action(project, producer):
    """Project existing registered producer fields into an explicit held action."""
    modes=producer.get('modes') or [];timeout=producer.get('timeout_seconds',900)
    payload={'producer_id':producer['id'],'request_id':'research-'+uuid.uuid4().hex,'args':{}}
    if len(modes)==1:payload['mode']=modes[0]
    fields=[{'name':'mode','label':'Run mode','type':'select','required':True,'choices':list(modes)}]
    types={'str':'text','int':'integer','float':'number','bool':'boolean'}
    for key,kind in (producer.get('allowed_args') or {}).items():
        fields.append({'name':'args.'+key,'label':key,'type':types.get(kind,'unsupported'),'required':False})
    fields.append({'name':'runtime_seconds','label':'Maximum execution seconds','type':'integer',
        'required':False,'minimum':1,'maximum':timeout})
    supported=type(timeout) is int and 1<=timeout<=3600 and all(f['type']!='unsupported' for f in fields)
    return {'id':'run-'+producer['id'],'title':'Run '+(producer.get('title') or producer['id']),
        'permitted':supported,'fields':fields,
        'http':{'method':'POST','url':'/research/run?'+_query({'project':project}),'payload':payload},
        'native':{'operation':'experiment_run','payload':copy.deepcopy(payload)},
        'request_read':{'http':{'method':'GET','url':'/research/run/request?'+_query({'project':project})},
            'query_field':'request','value':'exact original launch payload as JSON; never replace pending fields'},
        'new_decision_read':{'native':{'operation':'research','payload':{'view':'summary'}},
            'http':{'method':'GET','url':'/research/state?'+_query({'project':project,'view':'summary'})}},
        'meaning':'One explicit stable launch request. NONE permits only an explicit identical retry; UNKNOWN/CONFLICT remain unresolved. Run completion and scientific judgement are separate.'}


def admit_launch(root: Path, project: str, payload: dict, item, manuscript: Path) -> LaunchAdmission:
    """The declared producer and its inputs, the run job, then the pending reservation under the lock."""
    producer, mode, args, base, path, dependencies = _launch_producer(root, project, payload, item, manuscript)
    run_id = _request_identity(project,payload)[0] if 'request_id' in payload else f"run-{uuid.uuid4().hex[:16]}"
    result_rel = str(producer.get("result_path", f"{_RUNS}/{run_id}.result.json")).replace("{run_id}", run_id)
    result = research_context.inside(manuscript, result_rel)
    if result is None:
        raise _LaunchRefused(422, {"error": "declared result_path escapes project"})
    timeout = producer.get("timeout_seconds", 900)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
        raise _LaunchRefused(422, {"error": "producer timeout_seconds must be an integer from 1 to 3600"})
    if 'runtime_seconds' in payload:
        requested = payload['runtime_seconds']
        if type(requested) is not int or not 1 <= requested <= timeout:
            raise _LaunchRefused(422, {'error':'Requested runtime must be a positive exact integer no greater than the producer timeout; no ceiling was dropped.'})
        timeout = requested
    from laplace.research.research_runner import capability, SCHEMA
    support = capability()
    if support['status'] != 'AVAILABLE':
        raise _LaunchRefused(503, {'error': 'research supervision capability unavailable; producer was not started',
                                   'supervision_capability': support})
    runs_dir = manuscript / _RUNS
    index_home = _declared_run_home(item, root, manuscript)
    if not runs_dir.resolve().is_relative_to(root) or not index_home.is_relative_to(root):
        raise _LaunchRefused(422, {'error': 'supervised run metadata must remain within the registered checkout'})
    runs_dir.mkdir(parents=True, exist_ok=True)
    index_home.mkdir(parents=True, exist_ok=True)
    result.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(path)] if path.suffix == ".py" else [str(path)]
    argv += [_PRODUCER_FLAGS["mode"], mode, _PRODUCER_FLAGS["args"], json.dumps(args, sort_keys=True),
             _PRODUCER_FLAGS["result"], str(result)]
    stdout = runs_dir / f"{run_id}.stdout.log"
    stderr = runs_dir / f"{run_id}.stderr.log"
    executable = producer.get("executable")
    producer_observation = research_observation._digest(path)
    producer_observation["path"] = str(executable)
    producer_observation["scope"] = producer.get("scope", "manuscript")
    job = {"id": run_id, "state": "RUNNING", "launch_token": uuid.uuid4().hex,
           **({'request_id':payload['request_id'],'request_intent':_request_identity(project,payload)[1]} if 'request_id' in payload else {}),
           "supervision_index_path": str(index_home / 'index.json'),
           "supervision": {"schema_version": SCHEMA, "roles": {}, "cleanup_limit_seconds": 6.0}, "project": project,
           "producer_id": payload.get("producer_id"),
           "mode": mode, "args": args, "started_at": time.time(),
           "deadline_at": time.time() + timeout, "timeout_seconds": timeout,
           "execution_deadline_monotonic":time.monotonic()+timeout,
           "result_path": result.relative_to(manuscript).as_posix(),
           "result_absolute":str(result),"cwd":str(base),"producer_argv":argv,
           "producer_base":str(base),"producer_path":str(executable),
           "stdout_path":str(stdout),"stderr_path":str(stderr),"cancel_path":str(runs_dir/f"{run_id}.cancel"),
           "provenance": {"producer": producer_observation,
                          "producer_config": research_observation._object_digest(producer),
                          "dependencies": dependencies}}
    job_before, index_before, index_intended = _reserve_launch(root, project, job, runs_dir / f"{run_id}.json",
                                                               index_home)
    return LaunchAdmission(root, base, runs_dir, job, runs_dir / f"{run_id}.json", index_home / 'index.json',
                           stdout, stderr, job_before, index_before, index_intended)


def _launch_producer(root: Path, project: str, payload: dict, item, manuscript: Path) -> tuple:
    """The declared producer, its explicit mode and args, its scoped executable and present inputs."""
    producer_id, mode = payload.get("producer_id"), payload.get("mode")
    if not isinstance(producer_id, str) or not isinstance(mode, str):
        raise _LaunchRefused(422, {"error": "producer_id and explicit mode ('smoke' or 'full') are required"})
    producer, issue = _producer(manuscript, producer_id)
    if issue or producer is None:
        raise _LaunchRefused(422, {"error": issue})
    args, issue = _checked_args(producer, payload.get("args", {}), mode)
    if issue:
        raise _LaunchRefused(422, {"error": issue})
    executable = producer.get("executable")
    from laplace.manuscript import manuscript_source
    if manuscript_source.resolve(project,repo_root=root).get('read_only'):
        raise _LaunchRefused(403, {'error':'source is read-only'})
    base = research_context.project_root(item,root) if producer.get('scope') == 'project' else manuscript
    if base is None:
        raise _LaunchRefused(422,{'error':'project scope requires a declared project directory'})
    path = research_context.inside(base, executable) if isinstance(executable, str) else None
    if path is None or not path.is_file():
        raise _LaunchRefused(422, {"error": "producer executable must be a declared project-relative file"})
    try:
        dependencies = producer_dependencies(base, producer)
    except ValueError as exc:
        raise _LaunchRefused(422, {"error": str(exc)})
    if any(row.get("status") != "PRESENT" for row in dependencies):
        raise _LaunchRefused(422, {"error": "a declared producer input is missing or outside its scope",
                                   "dependencies": dependencies})
    return producer, mode, args, base, path, dependencies


def _reserve_launch(root: Path, project: str, job: dict, job_path: Path, index_home: Path) -> tuple:
    """Publish the exact pending handle (index, run handle, pending supervision) before activation."""
    from filelock import FileLock
    from laplace.research.research_runner import atomic_json, validated_receipt
    run_id, index_path = job["id"], index_home/'index.json'
    # Publish the exact pending handle before a cleanup owner, much less a
    # producer, can activate. No readiness/execution wait holds this lock.
    with FileLock(str(index_home/'.launch.lock'),timeout=15):
        job_before=job_path.read_bytes() if job_path.is_file() else None
        index_before=index_path.read_bytes() if index_path.is_file() else None
        index,error=research_observation._read_object(index_path,{'runs':[]},max_bytes=8*1024*1024)
        if error:raise _LaunchRefused(409,{'error':error})
        pending_rows=index.get('pending_supervision', [])
        if (not isinstance(pending_rows,list) or len(pending_rows)>128
                or any(_pending_job(row,root) is None or row.get('project')!=project for row in pending_rows)):
            raise _LaunchRefused(409,{'error':'pending supervision index needs inspection before admitting another job'})
        retained=[]
        for row in pending_rows:
            prior_path=_pending_job(row,root)
            prior,prior_error=research_observation._read_object(prior_path,{},max_bytes=1024*1024)
            receipt,receipt_error=research_observation._read_object(prior_path.with_name(prior_path.stem+'.receipt.json'),{},
                                                                    max_bytes=1024*1024)
            try:
                if (prior_error or receipt_error or prior.get('id')!=row['id']
                        or prior.get('project')!=project or prior.get('launch_token')!=row['launch_token']):
                    raise ValueError('pending identity unavailable')
                validated_receipt(prior,receipt)
                clean=((receipt.get('supervision') or {}).get('phase')=='TERMINAL'
                       and (receipt.get('cleanup') or {}).get('status')=='VERIFIED')
            except ValueError: clean=False
            if not clean:retained.append(row)
        pending_rows=retained
        if len(pending_rows)>=128:
            raise _LaunchRefused(409,{'error':'pending supervision capacity is full; inspect unresolved cleanup'})
        index['runs']=list(dict.fromkeys((index.get('runs') or [])+[run_id]))
        handle={'id':run_id,'project':project,'job_path':job_path.relative_to(root).as_posix(),
                'launch_token':job['launch_token']}
        handles=index.get('run_handles', {})
        if not isinstance(handles,dict) or run_id in handles:
            raise _LaunchRefused(409,{'error':'run locator conflicts with existing index; inspect before retrying'})
        index['run_handles']={**handles,run_id:handle}
        index['pending_supervision']=[*pending_rows,handle]
        atomic_json(job_path,job)
        atomic_json(index_path,index)
        index_intended=index_path.read_bytes()
    return job_before, index_before, index_intended


def activate(admission: LaunchAdmission) -> tuple[int, dict]:
    """Start the supervisor (research_runner) for an admitted job; its pending hint survives a failure."""
    from filelock import FileLock
    from laplace.core.receipts import bundle, file_receipt
    from laplace.research.research_runner import atomic_json
    root, job, job_path = admission.root, admission.job, admission.job_path
    # The runner self-registers strict identities before activation. A launcher
    # disappearing here cannot orphan an admitted workload or erase its hint.
    try:
        with admission.stdout.open('wb') as out, admission.stderr.open('wb') as err:
            process=subprocess.Popen([sys.executable,'-m','laplace.research.research_runner','--job',str(job_path)],cwd=admission.base,
                                     stdout=out,stderr=err,start_new_session=True)
        from laplace.representation.semantic_cadence import process_start_token
        with FileLock(str(admission.runs_dir/'.launch.lock'),timeout=15):
            observed,_=research_observation._read_object(job_path,{})
            # Do not overwrite the runner's richer handshake if it won the race.
            token=process_start_token(process.pid)
            if not observed.get('pid') and token:
                observed.update(pid=process.pid,supervisor_start_token=token)
                atomic_json(job_path,observed)
            job=observed
    except OSError as exc:
        return 503,{'error':'cleanup owner could not launch; pending supervision requires inspection',
                    'run':job,'reason':str(exc)}
    job_intended=job_path.read_bytes()
    owned=bundle(files=[file_receipt(root,admission.index_path,admission.index_before,admission.index_intended),
                        file_receipt(root,job_path,admission.job_before,job_intended)],objects=[{
        'owner':'research-run','id':admission.job['id'],'before_revision':None,
        'after_revision':research_observation._object_digest(job)}],views=['research-run-request'])
    return 202, {"ok": True, "run": job, "owned_changes":owned,
                 "effects":["research-run-request"],
                 "note":"Run accepted; read run_status for supervised completion and result provenance."}


def cancel(project: str, payload: dict, root: Path) -> tuple[int, dict]:
    """Request cancellation of one exact RUNNING run whose supervisor is verified live (writes one marker)."""
    from laplace.manuscript import manuscript_source
    if manuscript_source.resolve(project,repo_root=root).get('read_only'):return 403,{'error':'source is read-only'}
    item,manuscript=research_context.project(project,root);rid=payload.get('id')
    if not manuscript or not isinstance(rid,str):return 422,{'error':'project and id required'}
    run=_project_run_status(item,manuscript,rid,root)
    if run is None:return 404,{'error':'unknown run'}
    if run.get('state')!='RUNNING':return 409,{'error':'run is not active','state':run.get('state')}
    if ((run.get('supervision') or {}).get('schema_version') == 'laplace.research-supervision/1'
            and not _supervisor_active(run, Path(run.get('cancel_path','')).with_suffix('.json'))):
        return 409,{'error':'No verified live cleanup owner; cleanup remains unresolved. Inspect this exact run before retrying.', 'cleanup':run.get('cleanup')}
    marker=Path(run['cancel_path']) if run.get('cancel_path') else research_context.inside(manuscript,f'{_RUNS}/{rid}.cancel')
    if marker and not marker.resolve().is_relative_to(root.resolve()): marker=None
    if marker is None:return 422,{'error':'bad id'}
    from laplace.core.receipts import bundle, file_receipt
    before=marker.read_bytes() if marker.is_file() else None
    intended=b'cancelled'
    marker.write_bytes(intended)
    owned=bundle(files=[file_receipt(root,marker,before,intended)],objects=[{
        'owner':'research-run','id':rid,
        'before_revision':research_observation._object_digest({'state':'RUNNING'}),
        'after_revision':research_observation._object_digest({'state':'CANCEL_REQUESTED'})}],views=['research'])
    return 202,{'ok':True,'id':rid,'owned_changes':owned,
                'effects':['research-run-request'],
                'note':'Cancellation requested; read run_status for the supervised terminal state.'}


from laplace.research import research_observation  # noqa: E402  (cycle-safe: imported last)
from laplace.research import research_context  # noqa: E402


def evidence_candidates(root: Path, project: str) -> dict:
    """Declared run output choices, metadata only; no result/producer body reads.

    The composing reader admits the actual project Scope first. A candidate's
    recorded terminal pin is not fresh result verification: run_status remains
    the authoritative selected read and completion admission rechecks it.
    """
    from laplace.pipeline import registry
    from laplace.manuscript import manuscript_source
    root=Path(root).resolve();item=registry.resolve(project,repo_root=root)
    manuscript=manuscript_source.storage_home(project,root)
    if not item or manuscript is None:raise ValueError('Select a registered declared research home.')
    index_path=_declared_run_home(item,root,manuscript)/'index.json'
    index,error=research_observation._read_object(index_path,{},max_bytes=8*1024*1024)
    if error:return {'items':[],'coverage':'UNAVAILABLE','reason':error}
    handles=index.get('run_handles',{})
    if not isinstance(handles,dict):raise ValueError('Declared run locator map is malformed.')
    ids=index.get('runs',[])
    if not isinstance(ids,list) or any(not isinstance(value,str) or not value for value in ids):
        raise ValueError('Declared run identities are malformed.')
    result=[];issues=[];observed=[]
    for ident in dict.fromkeys([*ids,*handles]):
        try:
            if not _logical_run_id(ident):raise ValueError('Run ID is not a logical basename.')
            locator=handles.get(ident)
            if locator is not None:
                path=_scoped_job_path(item,manuscript,root,locator)
                if path is None or locator.get('project')!=project or locator.get('id')!=ident:
                    raise ValueError('Run locator belongs to another scope or identity.')
            else:path=_run_job_path(manuscript,ident)
            if path is None:raise ValueError('Run locator is outside its owner scope.')
            job,error=research_observation._read_object(path,{},max_bytes=1024*1024)
            if error or job.get('id')!=ident or job.get('project')!=project:
                raise ValueError('Selected run metadata is missing or foreign.')
            if locator and job.get('launch_token')!=locator.get('launch_token'):
                raise ValueError('Selected run launch identity changed.')
            receipt,error=research_observation._read_object(path.with_name(path.stem+'.receipt.json'),{},max_bytes=1024*1024)
            if error:raise ValueError(error)
            if job.get('supervision') is not None:
                from laplace.research.research_runner import validated_receipt
                validated_receipt(job,receipt)
            observed.append({'id':ident,'job':research_observation._object_digest(job),'receipt':research_observation._object_digest(receipt)})
            from laplace.projects.writing_portability import relocate_run
            located=relocate_run(job,path.parent.parent)
            target=_result_target(path.parent.parent,located)
            pin=receipt.get('result_sha256')
            if receipt.get('state')!='COMPLETE' or not re.fullmatch('[0-9a-f]{64}',str(pin)) or target is None or not target.is_file():continue
            result.append({'id':ident,'label':'Run '+ident+' result','owner':'research-run-output','state':'OFFERED',
                'evidence_value':target.relative_to(root).as_posix(),
                'support_item_reference':{'id':ident,'expected_sha256':pin},'support_manifest_eligibility':'NOT_AN_ARTIFACT_MANIFEST',
                'recorded_revision':pin,'currentness':'NOT_CHECKED',
                'read':{'operation':'run_status','payload':{'id':ident},'http':{'method':'GET','url':'/research/run/status?'+_query({'project':project,'id':ident})}}})
        except (ValueError,OSError) as error:issues.append({'id':ident,'reason':str(error)[:240]})
    return {'items':result,'observation':observed,'issues':issues,
            'coverage':'Declared run index only; legacy unindexed runs are not inferred. Output bytes were not read.'}
