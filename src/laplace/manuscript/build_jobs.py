"""Addressed controls for the existing compiler mutex and status sidecar.

No scheduler or second job ledger: process birth identities and cancellation
requests travel on projection_viewer's existing per-root status record.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlencode
import uuid

_LOCAL = threading.local()
ACTIVE = {'running', 'cancelling'}


class BuildCancelled(Exception):
    pass


class JobRefused(ValueError):
    def __init__(self, message, project):
        from laplace.manuscript import build_targets
        super().__init__(message)
        self.details = {'code':'BUILD_JOB_REFUSED', 'project':project,
            'next_reads':[{'operation':'document','payload':{},'http':{'method':'GET',
                'url':'/authoring/document?'+urlencode({'project':project})}},
                build_targets.read_handle(project)],
            'recovery':'Inspect the current document/build owner. No process was selected by a caller PID or an unproved path.'}


def error_details(error):
    for _ in range(8):
        if isinstance(error,JobRefused):return dict(error.details)
        if error is None:break
        error=error.__cause__ or error.__context__
    return {}


def schema():
    from laplace.manuscript.build_targets import target_schema
    fields = {key:{'type':'string','minLength':1} for key in ('id','root','target_kind','selection_identity','input_revision')}
    fields.update(project={'type':'string'}, schema_version={'const':'laplace.build-job/1'},
        id={'type':'string','pattern':'^BLD-[0-9a-f]{32}$'}, target_kind={'enum':['manuscript','derived','candidate','publication-edition']},
        build_target=target_schema())
    for key in ('selection_identity','input_revision'):
        fields[key]={'type':'string','pattern':'^sha256:[0-9a-f]{64}$'}
    return {'type':'object','required':[key for key in fields if key!='build_target'],
        'properties':fields,'additionalProperties':False,
        'allOf':[{'if':{'properties':{'target_kind':{'enum':['derived','candidate','publication-edition']}}},'then':{'required':['build_target']},
                  'else':{'not':{'required':['build_target']}}},
                 *[{'if':{'properties':{'target_kind':{'const':kind}}},
                     'then':{'properties':{'build_target':{'properties':{'kind':{'const':kind}}}}}}
                   for kind in ('derived','candidate','publication-edition')]]}


SELECTORS=('prepare','build_target','build_job','action')


def _operation_rules(read):
    """THE build operation rule: one request is exactly one of selected-source build/status, an issued
    build_target, an exact build_job (status, or action:cancel) or, for build only, an edition prepare.
    Presence decides, never truthiness, so a null or malformed second selector still refuses."""
    if read:
        return [{'not':{'required':['build_target','build_job']}}]
    # Publication-edition preparation is the build owner's explicit pre-build action: it writes
    # only that edition's derived wrapper under its definition guard, and is never combined.
    return [{'not':{'anyOf':[{'required':['build_target','build_job']},{'required':['prepare','build_target']},
                             {'required':['prepare','build_job']},{'required':['prepare','action']}]}},
            {'if':{'required':['action'],'properties':{'action':{'const':'cancel'}}},
             'then':{'required':['build_job'],'not':{'required':['build_target']}},
             'else':{'not':{'required':['build_job']}}}]


def request_schema(*, read=False):
    from laplace.manuscript.build_targets import target_schema
    properties={'build_target':target_schema(),'build_job':schema()}
    if not read:
        from laplace.manuscript.publication_editions import prepare_schema
        properties['prepare']=prepare_schema()
        properties['action']={'enum':['start','cancel']}
    return {'type':'object','required':[],'properties':properties,'additionalProperties':False,'allOf':_operation_rules(read)}


def admit(payload, project, *, read=False, query=False):
    """THE admitted build operation for the native and HTTP doors, before any branch read or effect.

    The selectors present (key presence, never truthiness) must satisfy the one operation rule, and
    every present target or job selector must decode, through its own owner decoder and declared
    schema, to its exact issued object; otherwise the request refuses and nothing is resolved,
    cancelled, prepared or compiled. Only an HTTP query (``query=True``) carries them as JSON text,
    which is how owner-issued status reads encode them; a body carries the object. Returns
    {'operation': prepare|job|target|selected, 'build_job'|'build_target': the normalized object}.
    Callers dispatch from this result alone; no selector is decoded again, so a supplied target can
    never fall back to the selected manuscript."""
    from jsonschema import Draft202012Validator
    from laplace.manuscript import build_targets
    from laplace.manuscript.publication_editions import prepare_schema
    present={key:payload[key] for key in SELECTORS if key in payload}
    carried={'type':'string' if query else 'object'}
    properties={'build_target':carried,'build_job':carried}
    if not read:
        properties.update(prepare=prepare_schema(),action={'enum':['start','cancel']})
    rule={'type':'object','properties':properties,'additionalProperties':False,'allOf':_operation_rules(read)}
    problem=next(Draft202012Validator(rule).iter_errors(present),None)
    if problem is not None:
        raise JobRefused('One build operation per request (prepare, build_target, build_job/action or the selected source); '
                         'nothing was cancelled, prepared or started: '+problem.message,project)
    if 'prepare' in present:
        return {'operation':'prepare'}
    if 'build_job' in present:
        return {'operation':'job','build_job':decode(present['build_job'],project)}
    if 'build_target' in present:
        target=build_targets.decode(present['build_target'],project=project)
        problem=next(Draft202012Validator(build_targets.target_schema()).iter_errors(target),None) if isinstance(target,dict) else 'no object'
        if problem is not None:
            raise build_targets.TargetRefused('The supplied build_target is not an owner-issued target; nothing was built and the '
                                              'selected manuscript was not substituted.',project)
        return {'operation':'target','build_target':target}
    return {'operation':'selected'}


def issue(scope, root):
    from laplace.manuscript import manuscript_source, tex_dependencies
    target = scope.get('build_target')
    source = scope.get('source') or {}
    inputs = tex_dependencies.snapshot(scope['root'],root,use_recorder=False) if not target else {}
    return {'schema_version':'laplace.build-job/1','id':'BLD-'+uuid.uuid4().hex,
        'project':scope.get('corpus',''),'root':scope['root'].relative_to(root).as_posix(),
        'target_kind':target['kind'] if target else 'manuscript',
        'selection_identity':target['selection_identity'] if target else manuscript_source.selection_identity(source,scope.get('corpus','')),
        'input_revision':target['input_revision'] if target else 'sha256:'+hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        **({'build_target':target} if target else {})}


def same_basis(left, right):
    return {k:v for k,v in left.items() if k!='id'} == {k:v for k,v in right.items() if k!='id'}


def contained_platform():
    return os.name=='posix'


def capability(row=None):
    row=row or {}
    available=contained_platform() and not row.get('cleanup_unproved') and not _unproved_group(row)
    unproved=bool(row.get('cleanup_unproved')) or _unproved_group(row)
    reason=None if available else ('Compiler process-tree cleanup is unproved. No process will be signalled; replacement for this root stays blocked. Inspect the exact job and settle the toolchain through its external owner before a supported recovery can verify cleanup.'
        if unproved else 'Compiler process-tree cancellation is unavailable on this platform; ordinary Build remains available.')
    return {'available':available,'reason':reason}


def handles(job, row=None):
    payload={'build_job':job}
    cancellation=capability(row)
    return {'build_job':job,
        'cancellation':cancellation,
        'cleanup_unproved':bool((row or {}).get('cleanup_unproved')) or _unproved_group(row or {}),
        'job_status_read':{'operation':'build_status','payload':payload,'http':{'method':'GET',
            'url':'/authoring/build?'+urlencode({'project':job['project'],'build_job':json.dumps(job,sort_keys=True,separators=(',',':'))})}},
        **({'cancel_action':{'operation':'build','payload':{'action':'cancel',**payload},
            'http':{'method':'POST','route':'/authoring/build'},'project':job['project']}} if cancellation['available'] else {})}


def source_observation(project, root, *, root_tex, selection_identity, files):
    """THE build observation of ONE recorded source effect, from the existing per-root status sidecar (no ledger).

    A build shows the effect only when its issued laplace.build-job/1 names this project, the effect's manuscript root
    and its admitted selection_identity, AND its recorded dependency snapshot names every effect file with exactly that
    file's observed after digest. Only the sidecar's current successful job and its retained last successful build are
    examined; never a nearest or latest PDF. Freshness against today's bytes stays the separate issued job_status_read
    (job_basis_current, fresh). An absent, superseded or unprovable match is explicit with the build owner's next read.
    files: the effect's exact file receipts [{path, observed_after_sha256[, observation_error]}]."""
    from laplace.manuscript import build_targets, projection_viewer as compiler
    root = Path(root).resolve()
    next_read = build_targets.read_handle(project)

    def absent(state, reason):
        return {'state': state, 'reason': reason, 'next_read': next_read}
    relative = Path(root_tex) if isinstance(root_tex, str) and root_tex else None
    if relative is None or relative.is_absolute() or '..' in relative.parts or relative.suffix.lower() != '.tex':
        return absent('UNAVAILABLE', 'The applied source names no exact repository-relative manuscript root.')
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        return absent('UNAVAILABLE', 'The applied manuscript root escapes its repository.')
    wanted = {}
    for row in files if isinstance(files, list) else ():
        digest = row.get('observed_after_sha256') if isinstance(row, dict) else None
        if not isinstance(row, dict) or not isinstance(row.get('path'), str) or not isinstance(digest, str) or 'observation_error' in row:
            return absent('UNAVAILABLE', 'The source effect lacks an observed after digest for every file.')
        wanted[row['path']] = digest.removeprefix('sha256:')
    if not wanted:
        return absent('UNAVAILABLE', 'The source effect names no observed file.')
    if not isinstance(selection_identity, str) or not selection_identity:
        return absent('UNAVAILABLE', 'The source effect carries no admitted selection_identity, so no build can be matched to it.')
    try:
        with control(path):
            row = compiler._read_recompile_status(path)
    except Exception as error:
        return absent('UNAVAILABLE', 'The build status of this root is unavailable: ' + str(error)[:200])
    candidates = []
    if row.get('ok') is True and isinstance(row.get('dependencies'), dict):
        candidates.append(('current', row.get('build_job'), row['dependencies']))
    last = row.get('last_successful_build')
    if isinstance(last, dict) and isinstance(last.get('dependencies'), dict):
        candidates.append(('last_successful', last.get('build_job'), last['dependencies']))
    other_bytes = False
    for role, job, dependencies in candidates:
        if not all(dependencies.get(name) == digest for name, digest in wanted.items()):
            other_bytes = other_bytes or all(name in dependencies for name in wanted)
            continue
        try:
            job = decode(job, project)
        except JobRefused:
            return {'state': 'BUILT_UNADDRESSED', 'observation': role, 'next_read': next_read,
                    'reason': 'A successful build recorded these exact after-pins but carries no issued build job; its status cannot be addressed.'}
        if job['root'] != relative.as_posix() or job['selection_identity'] != selection_identity:
            continue   # another selection or root is not this applied source
        return {'state': 'BUILT', 'observation': role, 'build_job': job, 'job_status_read': handles(job)['job_status_read'],
                'matched_files': sorted(wanted),
                'basis': 'Recorded build dependencies equal the effect observed after-pins under the same selection; '
                         'read job_status_read for current freshness. A build is not review or scientific acceptance.'}
    if other_bytes:
        return absent('NOT_BUILT', 'Recorded builds of this root saw other bytes for the applied files (an earlier or later source); none shows this application.')
    return absent('NOT_BUILT', 'No recorded successful build of this root and selection shows the applied after-pins.')


def decode(value, project):
    from jsonschema import Draft202012Validator
    if isinstance(value,str):
        try:value=json.loads(value)
        except ValueError as error:raise JobRefused('build_job must encode its exact issued object.',project) from error
    error=next(Draft202012Validator(schema()).iter_errors(value),None)
    if error or value.get('project')!=project:
        raise JobRefused('The build job is malformed or belongs to another project.',project)
    if value.get('build_target') and any(value.get(key)!=value['build_target'].get(key) for key in ('project','root','selection_identity','input_revision')):
        raise JobRefused('The job identity crosses its exact issued target.',project)
    return value


def path_for(job, project, root):
    job=decode(job,project)
    path=(root/job['root']).resolve()
    if Path(job['root']).is_absolute() or '..' in Path(job['root']).parts or not path.is_relative_to(root) or path.suffix.lower()!='.tex':
        raise JobRefused('The build job root escapes its owner.',project)
    return path


def control(root_tex):
    from filelock import FileLock
    from laplace.manuscript import projection_viewer as compiler
    return FileLock(str(compiler._recompile_status_path(root_tex))+'.control.lock',timeout=10)


def matched(job, project, root):
    from laplace.manuscript import projection_viewer as compiler
    path=path_for(job,project,root)
    row=compiler._read_recompile_status(path)
    if row.get('build_job')!=job:
        raise JobRefused('This exact build job is missing or was superseded; no current job was adopted.',project)
    return path,row


def _known(row):
    from laplace.writing.child_hosts import _process_matches
    return [item for item in row.get('owned_processes',[]) if _process_matches(item)]


def _group_occupants(row):
    group=row.get('process_group') or {}
    if os.name!='posix' or not isinstance(group,dict) or not group.get('id') or group.get('session')!=group['id']:return []
    import psutil
    occupants=[]
    for process in psutil.process_iter():
        try:
            if (os.getpgid(process.pid)==group['id'] and os.getsid(process.pid)==group['session']
                    and process.status()!=psutil.STATUS_ZOMBIE):occupants.append(process.pid)
        except (OSError,psutil.Error):pass
    return occupants


def _group_witness(row):
    from laplace.writing.child_hosts import _process_identity
    group=row.get('process_group') or {}
    if os.name!='posix' or not isinstance(group,dict) or not group.get('id'):return False
    leader=_process_identity(group['id'])
    if leader and leader!=group.get('leader'):return False
    for identity in _known(row):
        try:
            if os.getpgid(identity['pid'])==group['id'] and os.getsid(identity['pid'])==group.get('session'):return True
        except OSError:pass
    return False


def _unproved_group(row):
    return bool(_group_occupants(row)) and not _group_witness(row)


def _members(row):
    """Group membership is useful only with a live recorded-birth witness."""
    from laplace.writing.child_hosts import _process_matches, _process_identity
    identities=_known(row)
    if _group_witness(row):
        for pid in _group_occupants(row):
            identity=_process_identity(pid)
            if identity and _process_matches(identity) and identity not in identities:identities.append(identity)
    return identities


def processes_active(row):
    return bool(_members(row)) or _unproved_group(row)


def _stop(row):
    from laplace.writing.child_hosts import _terminate_owned_process
    # The existing process owner checks birth identity again immediately before
    # termination, including recursive descendants. Never signal an arbitrary PID.
    for identity in reversed(_members(row)):_terminate_owned_process(identity)
    return not processes_active(row)


def _observe_descendants(root_tex, job):
    from laplace.manuscript import projection_viewer as compiler
    from laplace.writing.child_hosts import _process_matches, _process_identity
    import psutil
    with control(root_tex):
        row=compiler._read_recompile_status(root_tex)
        if row.get('build_job')!=job:return
        observed=list(row.get('owned_processes',[]))
        for identity in list(observed):
            if not _process_matches(identity):continue
            try:
                for child in psutil.Process(identity['pid']).children(recursive=True):
                    found=_process_identity(child.pid)
                    if found and found not in observed:observed.append(found)
            except psutil.Error:pass
        if observed!=row.get('owned_processes',[]):
            row['owned_processes']=observed
            compiler._write_recompile_status(root_tex,row)


@contextlib.contextmanager
def bind(root_tex, job, repo_root=None):
    _LOCAL.owner=(root_tex,job,repo_root)
    try:yield
    finally:_LOCAL.owner=None


def _requested(root_tex, job):
    from laplace.manuscript import projection_viewer as compiler
    row=compiler._read_recompile_status(root_tex)
    if row.get('build_job')!=job:raise BuildCancelled('Build ownership changed; no further compiler pass was launched.')
    return row.get('state')=='cancelling'


def run(cmd, cwd, timeout):
    """Owned background invocation; synchronous legacy callers keep their runner."""
    owner=getattr(_LOCAL,'owner',None)
    if not owner:return None
    from laplace.manuscript import projection_viewer as compiler
    from laplace.writing.child_hosts import _process_identity
    root_tex,job,repo_root=owner
    environment=None
    if job.get('target_kind')=='candidate':
        from laplace.manuscript import build_targets
        if repo_root is None:
            repo_root=root_tex
            for _ in Path(job['root']).parts:repo_root=repo_root.parent
        environment=build_targets.compiler_environment(root_tex,job,repo_root)
        if cmd[0]==compiler._latexmk_bin() or Path(cmd[0]).name.lower().startswith('latexmk'):cmd=[cmd[0],'-norc','-no-shell-escape',*cmd[1:]]
        elif cmd[0]==compiler._pdflatex_bin() or Path(cmd[0]).name.lower().startswith(('pdflatex','xelatex','lualatex')):cmd=[cmd[0],'-no-shell-escape',*cmd[1:]]
    with control(root_tex):
        if _requested(root_tex,job):raise BuildCancelled('Build cancelled before the next compiler pass.')
        process=subprocess.Popen(cmd,cwd=str(cwd),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env=environment,
            encoding='utf-8',errors='replace',start_new_session=os.name=='posix',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        identity=_process_identity(process.pid)
        if not identity and process.poll() is None:
            # Popen itself owns this fresh handle. Refuse to continue an
            # unrecordable process rather than leave PID-only recovery evidence.
            if os.name=='posix':
                import signal
                os.killpg(process.pid,signal.SIGKILL)
            else:process.kill()
            process.communicate(timeout=5)
            raise OSError('Compiler process birth identity could not be recorded.')
        row=compiler._read_recompile_status(root_tex)
        row.update(owned_processes=[identity] if identity else [],
            process_group={'id':process.pid,'session':process.pid,'leader':identity} if os.name=='posix' else None)
        if job.get('target_kind')=='candidate':
            row.setdefault('compiler_invocations',[]).append({'command':list(cmd),
                'environment':{key:environment[key] for key in ('TEXINPUTS','BIBINPUTS','BSTINPUTS','openin_any','openout_any','shell_escape','SOURCE_DATE_EPOCH','FORCE_SOURCE_DATE') if key in environment}})
        compiler._write_recompile_status(root_tex,row)
    deadline=time.monotonic()+timeout
    try:
        while True:
            cancelled=_requested(root_tex,job)
            if cancelled or time.monotonic()>=deadline:
                row=compiler._read_recompile_status(root_tex)
                if not _stop(row):raise BuildCancelled('Owned compiler cleanup is incomplete; retry remains blocked.')
                process.communicate(timeout=5)
                if cancelled:raise BuildCancelled('Build cancelled; owned compiler processes were reaped.')
                if os.name!='posix':
                    with control(root_tex):
                        row=compiler._read_recompile_status(root_tex)
                        row['cleanup_unproved']=True
                        compiler._write_recompile_status(root_tex,row)
                return False,'TIMEOUT: owned compiler process tree was stopped.'
            try:
                stdout,stderr=process.communicate(timeout=.1)
                return process.returncode==0,(stdout or '')+'\n'+(stderr or '')
            except subprocess.TimeoutExpired:_observe_descendants(root_tex,job)
    finally:
        latest=compiler._read_recompile_status(root_tex)
        if os.name=='posix' and latest.get('build_job')==job and processes_active(latest):
            _stop(latest)
        if process.poll() is None:
            _stop({'owned_processes':[identity] if identity else [],
                'process_group':{'id':process.pid,'session':process.pid,'leader':identity} if os.name=='posix' else None})
            process.communicate(timeout=5)
        if process.poll() is not None:
            with control(root_tex):
                row=compiler._read_recompile_status(root_tex)
                if row.get('build_job')==job and not processes_active(row):
                    row.update(owned_processes=[],process_group=None)
                    compiler._write_recompile_status(root_tex,row)


def status(job, project, root):
    path=path_for(job,project,root)
    with control(path):
        return _status_locked(job,project,root)


def _status_locked(job, project, root):
    from laplace.manuscript import projection_viewer as compiler
    path=path_for(job,project,root)
    if job['target_kind']=='candidate' and compiler._read_recompile_status(path).get('build_job')!=job:
        from laplace.manuscript import build_targets
        return build_targets.candidate_job_status(job,project,root)
    path,row=matched(job,project,root)
    scope={'root':path,'source':None,'corpus':project,'compile_root':job['root']}
    value=compiler.recompile_status(job['root'],repo_root=root,corpus=project,_scope=scope,
        build_target=job.get('build_target'))
    try:
        current=compiler._compile_scope(path,corpus=project,repo_root=root,build_target=job.get('build_target'))
        basis_current=same_basis(job,issue(current,root))
    except ValueError:basis_current=False
    active=processes_active(row)
    running=row.get('state') in ACTIVE and (compiler._recompile_running(path) or active)
    preview_fields={key:row[key] for key in ('preview_ref','build_receipt_id','preview_publication','preview_error','preview_diagnostics') if key in row}
    if job['target_kind']=='candidate' and preview_fields.get('preview_ref'):
        from laplace.manuscript import build_targets
        try:build_targets.inspect_preview(project,job['build_target']['candidate_ref'],preview_fields['preview_ref'],root)
        except (ValueError,OSError) as error:
            preview_fields.update(preview_ref=None,preview_error=str(error),preview_state='UNAVAILABLE')
    return {**value,**handles(job,row),'project':project,'corpus':project,'state':row.get('state','idle'),
        'running':running,'ok':row.get('ok'),'log_tail':row.get('log_tail',''),
        'fresh':value.get('fresh') is True and basis_current,'job_basis_current':basis_current,
        'last_successful_build':row.get('last_successful_build'),'owned_processes_active':bool(_members(row)),
        **preview_fields,
        'replacement_blocked':active or bool(row.get('cleanup_unproved')),
        **({'reason':capability(row)['reason']} if row.get('cleanup_unproved') or _unproved_group(row) else {})}


def cancel(job, project, root):
    from laplace.manuscript import projection_viewer as compiler
    path=path_for(job,project,root)
    with control(path):
        if job['target_kind']=='candidate' and compiler._read_recompile_status(path).get('build_job')!=job:
            from laplace.manuscript import build_targets
            return {**build_targets.candidate_job_status(job,project,root),'cancel_outcome':'already_terminal'}
        _,row=matched(job,project,root)
        cancellation=capability(row)
        if not cancellation['available']:
            error=JobRefused(cancellation['reason'],project)
            error.details.update(code='CANCELLATION_UNAVAILABLE',next_reads=[handles(job,row)['job_status_read']])
            raise error
        active=processes_active(row)
        running=compiler._recompile_running(path)
        if row.get('state') not in ACTIVE and not active:
            return {**_status_locked(job,project,root),'cancel_outcome':'already_terminal'}
        row.update(state='cancelling',cancel_requested=time.time())
        compiler._write_recompile_status(path,row)
        if running:return {**_status_locked(job,project,root),'cancel_outcome':'requested'}
    if not running:
        # Recovery of a lost host uses the recorded process birth/group owner,
        # never a PID supplied by the caller. No new build is launched here.
        stopped=_stop(row)
        with control(path):
            _,latest=matched(job,project,root)
            if stopped:
                latest.update(state='cancelled',ok=False,finished=time.time(),
                    log_tail='Cancellation recovered the abandoned owned compiler process tree.',
                    owned_processes=[],process_group=None)
                compiler._write_recompile_status(path,latest)
            return {**_status_locked(job,project,root),'cancel_outcome':'recovered' if stopped else 'requested'}


def previous_success(prior):
    if prior.get('ok'):
        return {key:prior[key] for key in ('outputs','dependencies','pdf','build_job','finished') if key in prior}
    return prior.get('last_successful_build')


def preserve_pdf(root_tex, prior, repo_root):
    """Keep only the exact bytes proved by the previous successful producer."""
    from laplace.manuscript import projection_viewer as compiler
    record=previous_success(prior) or {}
    pdf=root_tex.with_suffix('.pdf')
    recorded=(record.get('outputs') or {}).get('files',{})
    expected=recorded.get(root_tex.with_suffix('.pdf').relative_to(repo_root).as_posix())
    if pdf.is_file() and isinstance(expected,str) and expected.removeprefix('sha256:')==compiler._output_sha256(pdf).removeprefix('sha256:'):
        return pdf.read_bytes()
    return None


def finish(root_tex, job, row, retained_pdf, *, repo_root=None):
    from laplace.manuscript import projection_viewer as compiler
    with control(root_tex):
        latest=compiler._read_recompile_status(root_tex)
        if latest.get('build_job')!=job:raise BuildCancelled('Build ownership changed before terminal publication.')
        active=processes_active(latest)
        if os.name!='posix' and active:latest['cleanup_unproved']=True
        if latest.get('cleanup_unproved'):
            row.update(state='error',ok=False,cleanup_unproved=True,owned_processes=latest.get('owned_processes',[]),
                log_tail='Compiler cleanup is unproved; replacement is blocked for this root. '+str(capability(latest)['reason']))
        elif latest.get('state')=='cancelling' or row.get('state')=='cancelled' or active:
            row.update(state='cancelling' if active else 'cancelled',ok=False,outputs=None,
                log_tail='Cancellation requested; owned processes remain active.' if active else
                    'Build cancelled; owned compiler processes were reaped. Previous verified PDF retained when available.',
                cancel_requested=latest.get('cancel_requested'),
                owned_processes=latest.get('owned_processes',[]) if active else [],
                process_group=latest.get('process_group') if active else None)
            if not active and retained_pdf is not None:root_tex.with_suffix('.pdf').write_bytes(retained_pdf)
            row['last_successful_derived']=latest.get('last_successful_derived')
            row['last_successful_build']=latest.get('last_successful_build')
        row['build_job']=job
        if job.get('target_kind')=='candidate':row['compiler_invocations']=latest.get('compiler_invocations',[])
        observation=None
        if job.get('target_kind')=='candidate':
            from laplace.manuscript import build_targets
            try:
                observation=build_targets.observe_candidate_build(root_tex,job,row,repo_root)
                row['preview_publication']='PENDING'
            except Exception as error:
                row.update(preview_publication='UNPROVED',preview_error=str(error))
        compiler._write_recompile_status(root_tex,row)
    if observation is not None:
        try:proof=build_targets.retain_candidate_observation(observation,repo_root)
        except Exception as error:proof={'preview_publication':'UNPUBLISHED','preview_error':str(error)}
        else:proof['preview_publication']='RECORDED'
        with control(root_tex):
            latest=compiler._read_recompile_status(root_tex)
            if latest.get('build_job')==job:compiler._write_recompile_status(root_tex,{**latest,**proof})
