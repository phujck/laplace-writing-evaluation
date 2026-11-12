"""Job-scoped Linux supervision, not a daemon or a security sandbox.

A guardian forks one supervisor; both become subreapers before admission. The
survivor owns cleanup if either role dies. Only the workload tree is signalled,
using pidfds plus boot/start identities. The execution cutoff keeps its public
meaning; all termination/reaping shares one additional six-second deadline.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time

def process_start_token(pid=None):
    # The existing identity owner imports fcntl. Unsupported platforms must
    # reach named admission refusal before importing that Linux implementation.
    if sys.platform != 'linux': return None
    from laplace.representation.semantic_cadence import process_start_token as observed_token
    return observed_token(pid)

SCHEMA = "laplace.research-supervision/1"
CLEANUP_SECONDS = 6.0
_POLL = .05
_MAX_TREE = 4096
_STOP = False


def capability() -> dict:
    """Admission probe only; prctl is applied in each fresh one-shot owner."""
    missing = []
    if sys.platform != "linux" or not Path('/proc/self/task').is_dir():
        missing.append('Linux procfs/subreaper support')
    if (not hasattr(os,'fork') or not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal')
            or not hasattr(os,'waitid') or not hasattr(os,'WNOWAIT')):
        missing.append('fork, pidfd signalling and identity-observed reaping')
    if not process_start_token():
        missing.append('boot/start process identity')
    if not missing:
        try:
            fd = os.pidfd_open(os.getpid())
            try:
                signal.pidfd_send_signal(fd, 0)
            finally:
                os.close(fd)
            value = ctypes.c_int()
            if ctypes.CDLL(None, use_errno=True).prctl(37, ctypes.byref(value), 0, 0, 0):
                missing.append('PR_GET_CHILD_SUBREAPER')
        except (OSError, AttributeError):
            missing.append('available pidfd/prctl kernel capability')
    return {'status': 'AVAILABLE' if not missing else 'UNAVAILABLE',
            'platform': sys.platform, 'missing': missing}


def _setup() -> dict:
    if capability()['status'] != 'AVAILABLE':
        raise RuntimeError('research supervision requires Linux subreaper, procfs and pidfd capabilities')
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0):
        raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER failed')
    global _STOP
    _STOP = False
    def stop(_sig, _frame):
        global _STOP
        _STOP = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    identity = _identity(os.getpid())
    if not identity:
        raise RuntimeError('cleanup owner identity unavailable')
    return identity


def _identity(pid: int) -> dict | None:
    token = process_start_token(pid)
    return {'pid': pid, 'start_token': token} if token else None


def identity_state(identity: dict | None) -> str:
    """Strict identity observation; UNKNOWN is never permission to signal."""
    if (not isinstance(identity, dict) or type(identity.get('pid')) is not int
            or identity['pid'] <= 0 or not isinstance(identity.get('start_token'), str)
            or not identity['start_token']):
        return 'UNKNOWN'
    path = Path('/proc') / str(identity['pid'])
    try:
        state = (path / 'stat').read_text().rsplit(')', 1)[1].split()[0]
    except FileNotFoundError:
        return 'DEAD'
    except (OSError, IndexError):
        return 'UNKNOWN'
    token = process_start_token(identity['pid'])
    if not token:
        return 'UNKNOWN'
    if token != identity['start_token']:
        return 'DEAD'  # the original identity is gone; never signal its replacement
    return 'DEAD' if state == 'Z' else 'LIVE'


def _signal(identity: dict, sig: int) -> bool:
    """The pidfd pins the signalled task across the second identity observation."""
    if identity_state(identity) != 'LIVE':
        return False
    try:
        fd = os.pidfd_open(identity['pid'])
        try:
            if identity_state(identity) != 'LIVE':
                return False
            signal.pidfd_send_signal(fd, sig)
            return True
        finally:
            os.close(fd)
    except ProcessLookupError:
        return False


def atomic_json(path: Path, value: dict) -> None:
    """One private sibling; readers see either complete metadata observation."""
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        try: os.unlink(name)
        except FileNotFoundError: pass


def _read(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('job metadata must be an object')
    return value


def _lock(job: Path, timeout=.5):
    from filelock import FileLock
    return FileLock(str(job.parent / '.launch.lock'), timeout=timeout)


_PHASES = {'READY': 1, 'ACTIVE': 2, 'CLEANUP': 3, 'TERMINAL': 4}
_RECEIPT_FIELDS = {'supervision_schema','launch_token','state','cleanup','supervision',
    'execution_deadline_monotonic','producer_identity','result_before_mtime_ns',
    'execution_state','exit_code','reason','causes','result_sha256','finished_at',
    'supervision_error','publisher','roles','cleanup_limit_seconds'}


def validated_receipt(job: dict, receipt: dict) -> dict:
    """Fixed producer projection: runtime metadata cannot replace launch identity."""
    if not isinstance(job,dict):
        raise ValueError('immutable launch job must be an object')
    job_supervision=job.get('supervision')
    if job_supervision is not None and (not isinstance(job_supervision,dict)
            or job_supervision.get('schema_version')!=SCHEMA
            or not isinstance(job_supervision.get('roles'),dict)):
        raise ValueError('immutable job supervision is malformed or unsupported')
    if (not isinstance(receipt,dict) or set(receipt)-_RECEIPT_FIELDS
            or receipt.get('supervision_schema') != SCHEMA
            or receipt.get('launch_token') != job.get('launch_token')):
        raise ValueError('supervision receipt does not bind the immutable launch job')
    supervision=receipt.get('supervision')
    if not isinstance(supervision,dict) or supervision.get('schema_version')!=SCHEMA:
        raise ValueError('supervision receipt has no declared lifecycle')
    if (set(supervision)-{'schema_version','phase','roles','cleanup_limit_seconds',
                          'cleanup_deadline_monotonic','cleanup_started_at'}
            or supervision.get('cleanup_limit_seconds')!=CLEANUP_SECONDS):
        raise ValueError('supervision receipt has unsupported lifecycle fields/budget')
    execution=job.get('execution_deadline_monotonic')
    if execution is not None and (not isinstance(execution,(int,float)) or isinstance(execution,bool)
            or not math.isfinite(execution) or execution<=0):
        raise ValueError('immutable execution deadline is malformed')
    if execution is not None and receipt.get('execution_deadline_monotonic')!=execution:
        raise ValueError('progress contradicts the immutable execution deadline')
    retained=supervision.get('cleanup_deadline_monotonic')
    if retained is not None and (not isinstance(retained,(int,float)) or isinstance(retained,bool)
            or not math.isfinite(retained) or retained<=0
            or execution is not None and retained>execution+CLEANUP_SECONDS):
        raise ValueError('cleanup deadline contradicts the admitted execution bound')
    phase=supervision.get('phase');roles=supervision.get('roles')
    if not isinstance(phase,str) or phase not in _PHASES or not isinstance(roles,dict) or set(roles)!={'guardian','supervisor'}:
        raise ValueError('supervision receipt has invalid role/phase identities')
    for identity in roles.values():
        if (not isinstance(identity,dict) or set(identity)!={'pid','start_token'}
                or type(identity.get('pid')) is not int or identity['pid']<=0
                or not isinstance(identity.get('start_token'),str) or not identity['start_token']):
            raise ValueError('supervision role requires exact PID/start identity')
    if roles['guardian']['pid']==roles['supervisor']['pid']:
        raise ValueError('cleanup owners must have distinct identities')
    if job.get('pid') is not None and (job['pid']!=roles['guardian']['pid']
            or job.get('supervisor_start_token')!=roles['guardian']['start_token']):
        raise ValueError('receipt guardian contradicts acknowledged launch identity')
    cleanup=receipt.get('cleanup')
    if (not isinstance(cleanup,dict) or not isinstance(cleanup.get('status'),str)
            or cleanup['status'] not in {'PENDING','VERIFIED','INCOMPLETE','UNKNOWN'}):
        raise ValueError('supervision receipt cleanup is unavailable')
    if phase=='TERMINAL':
        publisher=receipt.get('publisher')
        if not isinstance(publisher,dict):
            raise ValueError('terminal publisher must be an object')
        role=publisher.get('role')
        state=receipt.get('state')
        if (not isinstance(role,str) or role not in roles or {k:v for k,v in publisher.items() if k!='role'}!=roles[role]
                or receipt.get('roles')!=roles or not isinstance(state,str) or state not in
                    {'COMPLETE','FAILED','STALE','CANCELLED','TIMED_OUT','CLEANUP_UNRESOLVED'}):
            raise ValueError('terminal receipt has invalid publisher/outcome binding')
        if cleanup['status']=='VERIFIED' and (cleanup.get('remaining')!=[] or cleanup.get('issues')!=[]):
            raise ValueError('verified cleanup contradicts remaining/unknown ownership')
        if receipt['state']=='COMPLETE' and cleanup['status']!='VERIFIED':
            raise ValueError('COMPLETE requires verified cleanup')
    elif receipt.get('state')!='RUNNING' or cleanup['status']!='PENDING':
        raise ValueError('nonterminal progress cannot claim a terminal outcome')
    return receipt


def _runtime_cut(job: Path, original: dict) -> tuple[dict,dict]:
    base=_read(job)
    if base.get('launch_token')!=original.get('launch_token'):
        raise ValueError('research job identity changed')
    path=job.with_name(job.stem+'.receipt.json')
    progress=validated_receipt(base,_read(path)) if path.exists() else {}
    return base,progress


def _update(job: Path, original: dict, values: dict) -> dict:
    """Monotonic progress in the EXISTING receipt; launch bytes stay immutable."""
    with _lock(job):
        base,progress=_runtime_cut(job,original)
        prior=(progress.get('supervision') or {}).get('phase')
        if prior=='TERMINAL':
            raise ValueError('late progress cannot overwrite terminal receipt')
        supervision={**(progress.get('supervision') or {}),**values.get('supervision',{})}
        phase=supervision.get('phase')
        if phase=='READY' and prior=='CLEANUP':
            return {**base,**progress}  # cutoff won setup; never activate/downgrade
        if phase not in _PHASES or (prior and _PHASES[phase]<_PHASES[prior]):
            raise ValueError('supervision progress cannot move backwards')
        progress={**progress,**values,'supervision':supervision,
                  'supervision_schema':SCHEMA,'launch_token':base['launch_token'],
                  'state':'RUNNING','cleanup':{'status':'PENDING'}}
        validated_receipt(base,progress)
        atomic_json(job.with_name(job.stem+'.receipt.json'),progress)
        return {**base,**progress}


class _Channel:
    def __init__(self, sock: socket.socket):
        self.sock, self.buffer, self.closed = sock, b'', False
        # An unresponsive live peer must not turn cleanup publication into an
        # unbounded pipe wait. Physical cleanup retains its own shared deadline.
        self.sock.settimeout(.25)

    def send(self, value: dict):
        self.sock.sendall(json.dumps(value).encode() + b'\n')

    def receive(self, timeout=0.) -> list[dict]:
        if self.closed or not select.select([self.sock], [], [], timeout)[0]:
            return []
        data = self.sock.recv(65536)
        if not data:
            self.closed = True
            return []
        self.buffer += data
        if len(self.buffer) > 2 * 1024 * 1024:
            raise ValueError('supervision message exceeds bound')
        rows = []
        while b'\n' in self.buffer:
            row, self.buffer = self.buffer.split(b'\n', 1)
            rows.append(json.loads(row))
        return rows

    def close(self):
        self.sock.close()


class _Tree:
    """Only this one-shot owner's children/adoptions, never all-/proc polling."""
    def __init__(self, exclude=()):
        self.exclude = tuple(exclude)
        self.known: dict[tuple, dict] = {}
        self.exits: dict[tuple[int,str], int] = {}
        self.issues: list[str] = []
        self.metrics = {'tree_visits': 0, 'identity_observations': 0,
                        'signals': 0, 'reaped': 0, 'max_owned': 0}

    def scan(self) -> list[dict]:
        owner = _identity(os.getpid())
        if not owner:
            self.issues.append('cleanup owner identity unavailable')
            return []
        queue, seen, live = [owner], set(), []
        while queue:
            parent = queue.pop()
            pid = parent['pid']
            if pid in seen: continue
            seen.add(pid)
            if identity_state(parent) != 'LIVE': continue
            if len(seen) > _MAX_TREE:
                self.issues.append('owned tree exceeded observation bound')
                break
            self.metrics['tree_visits'] += 1
            try:
                tasks = list((Path('/proc') / str(pid) / 'task').iterdir())
            except FileNotFoundError:
                continue
            except OSError:
                self.issues.append('owned task children unavailable')
                continue
            children = set()
            for task in tasks:
                try:
                    children.update(int(x) for x in (task / 'children').read_text().split())
                except FileNotFoundError: pass
                except (OSError, ValueError): self.issues.append('owned task children unreadable')
            # A parent can exit/reuse its PID during this read. Discard that
            # cut rather than adopting an unrelated replacement's children;
            # genuine orphans appear under our subreaper on the next pass.
            if identity_state(parent) != 'LIVE': continue
            for child in children:
                self.metrics['identity_observations'] += 1
                ident = _identity(child)
                try:
                    parent_now=int((Path('/proc')/str(child)/'stat').read_text().rsplit(')',1)[1].split()[1])
                except FileNotFoundError: continue
                except (OSError,ValueError,IndexError):
                    self.issues.append('child-parent ownership observation unavailable')
                    continue
                if not ident or _identity(child)!=ident:
                    # Never turn an old children-list PID into a new process's
                    # identity. A linked but unobservable child keeps proof open.
                    if parent_now in (pid,owner['pid']):
                        self.issues.append('linked child identity unavailable or changed')
                    continue
                linked=(parent_now==pid and identity_state(parent)=='LIVE')
                adopted=(parent_now==owner['pid'] and identity_state(owner)=='LIVE')
                if not (linked or adopted): continue
                if ident in self.exclude: continue
                if len(self.known) >= _MAX_TREE and (child, ident['start_token']) not in self.known:
                    self.issues.append('owned identity retention exceeded bound')
                    continue
                self.known[(child, ident['start_token'])] = ident
                queue.append(ident)
                if identity_state(ident) == 'LIVE': live.append(ident)
        self.metrics['max_owned'] = max(self.metrics['max_owned'], len(self.known))
        return live

    def reap(self):
        while True:
            try:
                observed=os.waitid(os.P_ALL,0,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if observed is None or not observed.si_pid:return
                # WNOWAIT keeps this exact zombie PID occupied until our wait;
                # a later reused PID cannot donate its status to the producer.
                identity=_identity(observed.si_pid)
                pid,status=os.waitpid(observed.si_pid,os.WNOHANG)
            except ChildProcessError:return
            if not pid:return
            if identity:
                self.exits[(pid,identity['start_token'])]=os.waitstatus_to_exitcode(status)
            else:
                self.issues.append('reaped child start identity unavailable')
            self.metrics['reaped']+=1

    def cleanup(self, deadline: float) -> dict:
        started, term_at, sent = time.monotonic(), min(time.monotonic()+3.,deadline-3.), set()
        empty_passes = 0
        while True:
            self.reap()
            live = self.scan()
            # A previously seen child may have reparented while its parent died.
            for ident in self.known.values():
                state = identity_state(ident)
                if state == 'LIVE' and ident not in live: live.append(ident)
                elif state == 'UNKNOWN': self.issues.append('owned identity became unobservable')
            now = time.monotonic()
            if not live:
                empty_passes += 1
                if empty_passes >= 2: break
            else:
                empty_passes = 0
            if now >= deadline: break
            sig = signal.SIGKILL if now >= term_at else signal.SIGTERM
            for ident in live:
                key = (ident['pid'], ident['start_token'], sig)
                if key in sent: continue
                try:
                    if _signal(ident, sig): self.metrics['signals'] += 1
                except OSError as exc:
                    self.issues.append('owned signal failed: ' + str(exc.errno))
                sent.add(key)
            time.sleep(min(_POLL, max(0., deadline - time.monotonic())))
        self.reap()
        remaining = [ident for ident in self.known.values() if identity_state(ident) != 'DEAD']
        self.scan()  # include final adoptions/late forks in the verification cut
        remaining = [ident for ident in self.known.values() if identity_state(ident) != 'DEAD']
        issues = list(dict.fromkeys(self.issues))
        return {'status': 'INCOMPLETE' if remaining else 'UNKNOWN' if issues else 'VERIFIED',
                'remaining': remaining, 'issues': issues, 'observed_count': len(self.known),
                'metrics': dict(self.metrics), 'seconds': time.monotonic() - started,
                'deadline_monotonic': deadline, 'budget_seconds': CLEANUP_SECONDS}


def _cleanup_deadline(job: Path, d: dict, execution_deadline: float) -> float:
    candidate=min(time.monotonic()+CLEANUP_SECONDS,execution_deadline+CLEANUP_SECONDS)
    retained=(d.get('supervision') or {}).get('cleanup_deadline_monotonic')
    if retained is not None:candidate=min(candidate,float(retained))
    try:
        with _lock(job):
            base,progress=_runtime_cut(job,d)
            if (progress.get('supervision') or {}).get('phase')=='TERMINAL':
                raise ValueError('terminal cleanup cannot restart')
            retained=(progress.get('supervision') or {}).get('cleanup_deadline_monotonic')
            deadline=min(candidate,float(retained)) if retained is not None else candidate
            supervision={**progress.get('supervision',{}),'phase':'CLEANUP',
                         'cleanup_deadline_monotonic':deadline}
            supervision.setdefault('cleanup_started_at',time.time())
            progress={**progress,'supervision':supervision,'supervision_schema':SCHEMA,
                      'launch_token':base['launch_token'],'state':'RUNNING','cleanup':{'status':'PENDING'}}
            validated_receipt(base,progress)
            atomic_json(job.with_name(job.stem+'.receipt.json'),progress)
            d['supervision']=supervision
        return deadline
    except (OSError,ValueError,TimeoutError) as exc:
        d.setdefault('metadata_issues',[]).append(str(exc))
        return candidate


def _producer_exit(captured: int | None, identity: dict | None, exits: dict) -> int | None:
    """A captured producer code wins; another start at its PID is not evidence."""
    if captured is not None:return captured
    return exits.get((identity['pid'],identity['start_token'])) if identity else None


def _requested_causes(d: dict) -> list[str]:
    causes=[]
    if Path(d['cancel_path']).exists():causes.append('cancelled')
    if time.monotonic()>=d['execution_deadline_monotonic']:causes.append('timeout')
    if _STOP:causes.append('owner-terminated')
    return causes


def _execution_receipt(d: dict, code: int | None, before, causes: list[str], cleanup: dict) -> dict:
    from laplace.research.research_runs import run_inputs_current
    result = Path(d['result_absolute'])
    after = result.stat().st_mtime_ns if result.is_file() else None
    checksum = hashlib.sha256(result.read_bytes()).hexdigest() if not causes and code == 0 and result.is_file() and before != after else None
    priority = ['cancelled', 'timeout', 'guardian-lost', 'supervisor-lost', 'supervisor-unresponsive', 'owner-terminated', 'setup-failed', 'inputs-stale']
    causes = list(dict.fromkeys(causes))
    reason = next((x for x in priority if x in causes), None)
    state = ('CANCELLED' if reason == 'cancelled' else 'TIMED_OUT' if reason == 'timeout'
             else 'STALE' if reason == 'inputs-stale' else 'FAILED' if reason else 'COMPLETE' if checksum else 'FAILED')
    if not reason:
        reason = 'producer exited' if checksum else ('producer exited zero but did not create or change the requested --result file; stdout is only a log' if code == 0 else 'producer exited without a successful result')
    if d.get('metadata_issues'):
        cleanup.update(status='UNKNOWN', issues=cleanup['issues'] + d['metadata_issues'])
    if state == 'COMPLETE' and not run_inputs_current(d):
        state, reason = 'STALE', 'declared inputs changed during execution'
    return {'supervision_schema': SCHEMA, 'launch_token': d.get('launch_token'),
            'state': state if cleanup['status'] == 'VERIFIED' else 'CLEANUP_UNRESOLVED',
            'execution_state': state, 'exit_code': code, 'reason': reason,
            'causes': causes, 'result_sha256': checksum, 'cleanup': cleanup,
            'finished_at': time.time()}


def _publish(job: Path, d: dict, receipt: dict, role: str, identity: dict, other: dict | None):
    """Guardian is publisher; exact-dead guardian permits survivor fallback."""
    with _lock(job):
        base,progress=_runtime_cut(job,d)
        roles=(progress.get('supervision') or {}).get('roles') or {}
        if roles.get(role)!=identity or identity_state(identity)!='LIVE':
            raise ValueError('terminal publisher does not match admitted job owner')
        if role!='guardian' and identity_state(other)!='DEAD':
            raise ValueError('fallback publisher requires exact other-owner death')
        if (progress.get('supervision') or {}).get('phase')=='TERMINAL':
            return  # guardian published before dying/losing its ACK; never rewrite it
        receipt={**receipt,'publisher':{'role':role,**identity},'roles':roles,
                 'cleanup_limit_seconds':CLEANUP_SECONDS,
                 'supervision':{**progress['supervision'],'phase':'TERMINAL'},
                 'execution_deadline_monotonic':progress.get('execution_deadline_monotonic')}
        if progress.get('producer_identity'):
            receipt['producer_identity']=progress['producer_identity']
        validated_receipt(base,receipt)
        atomic_json(job.with_name(job.stem+'.receipt.json'),receipt)
    # The explicit launch owner prunes exact verified hints on its NEXT index
    # write. Async pruning here would invalidate launch's exact before/after
    # index proof. Retained hints are resolved against this terminal receipt by
    # passive health; run_handles remain historical locators, never copied state.


def _supervisor(job: Path, d: dict, channel: _Channel, guardian: dict):
    me = _setup()
    # Register both strict identities before signalling readiness. If the
    # guardian dies during setup, this survivor can still publish an empty cut.
    d=_update(job,d,{'execution_deadline_monotonic':d['execution_deadline_monotonic'],
        'supervision':{'schema_version':SCHEMA,'phase':'READY',
                       'roles':{'guardian':guardian,'supervisor':me},
                       'cleanup_limit_seconds':CLEANUP_SECONDS}})
    try: channel.send({'kind': 'ready', 'identity': me})
    except OSError: channel.closed = True
    stop_at = min(time.monotonic() + 5., d['execution_deadline_monotonic'])
    activated = False
    while time.monotonic() < stop_at:
        for row in channel.receive(_POLL):
            if row.get('kind') == 'activate' and row.get('guardian') == guardian and row.get('supervisor') == me:
                activated = True
        if activated or channel.closed or _STOP: break
    tree = _Tree()
    before = Path(d['result_absolute']).stat().st_mtime_ns if Path(d['result_absolute']).is_file() else None
    proc, code, causes = None, None, []
    try:
        from laplace.research.research_runs import run_inputs_current
        causes.extend(_requested_causes(d))
        if channel.closed or identity_state(guardian)!='LIVE':causes.append('guardian-lost')
        elif not activated and not causes:causes.append('setup-failed')
        if causes: pass
        elif not run_inputs_current(d): causes.append('inputs-stale')
        else:
            with open(d['stdout_path'], 'ab') as out, open(d['stderr_path'], 'ab') as err:
                proc = subprocess.Popen(d['producer_argv'], cwd=d['cwd'], stdout=out, stderr=err,
                                        start_new_session=True)
            ident = _identity(proc.pid)
            if not ident: raise RuntimeError('producer identity unavailable')
            d = _update(job, d, {'producer_identity': ident, 'result_before_mtime_ns': before})
            channel.send({'kind': 'producer', 'identity': ident})
            while proc.poll() is None:
                for row in channel.receive(0.):
                    if row.get('kind')=='cleanup-request':
                        d.setdefault('supervision',{})['cleanup_deadline_monotonic']=row['deadline_monotonic']
                        causes.extend(row.get('causes') or [])
                causes.extend(_requested_causes(d))
                if channel.closed or identity_state(guardian) != 'LIVE': causes.append('guardian-lost')
                if _STOP: causes.append('owner-terminated')
                if causes: break
                time.sleep(_POLL)
            code = proc.poll()
    except BaseException as exc:
        causes.append('setup-failed')
        d['supervision_error'] = str(exc)
    finally:
        deadline = _cleanup_deadline(job, d, d['execution_deadline_monotonic'])
        try: channel.send({'kind':'cleanup-start', 'deadline_monotonic':deadline})
        except OSError: channel.closed = True
        cleanup = tree.cleanup(deadline)
        if proc is not None:
            code=_producer_exit(code,ident,tree.exits)
            # proc.poll() after another wait could invent zero on ECHILD; only
            # a captured code or an identity-bound waited status is evidence.
        receipt = _execution_receipt(d, code, before, causes, cleanup)
        if d.get('supervision_error'): receipt['supervision_error'] = d['supervision_error']
        if identity_state(guardian) == 'LIVE' and not channel.closed:
            try: channel.send({'kind': 'settled', 'receipt': receipt})
            except OSError: channel.closed = True
        # Keep a survivor until the normal publisher acknowledges durable state.
        while identity_state(guardian) == 'LIVE' and not channel.closed:
            if time.monotonic() >= deadline-1.:
                # Our workload is already settled. Bound an unavailable normal
                # publisher without ever killing the sole cleanup owner.
                _signal(guardian, signal.SIGKILL)
                while identity_state(guardian)=='LIVE' and time.monotonic()<deadline:
                    time.sleep(_POLL)
                break
            if any(row.get('kind') == 'published' for row in channel.receive(_POLL)):
                return
        _publish(job, d, receipt, 'supervisor', me, guardian)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    job = Path(args.job).resolve()
    d = _read(job)
    # Direct legacy runner fixtures get the same two-owner protocol. Real launch
    # has already registered an exact pending hint before this process exists.
    if not d.get('launch_token') or 'execution_deadline_monotonic' not in d:
        with _lock(job):
            d=_read(job)
            d.setdefault('launch_token',os.urandom(16).hex())
            d.setdefault('id',job.stem)
            d.setdefault('execution_deadline_monotonic',time.monotonic()+max(0.,float(d['deadline_at'])-time.time()))
            atomic_json(job,d)
    d.setdefault('id',job.stem)
    guardian = _setup()
    left, right = socket.socketpair()
    supervisor_pid = os.fork()
    if supervisor_pid == 0:
        left.close()
        try:
            _supervisor(job, d, _Channel(right), guardian)
        finally:
            right.close()
        os._exit(0)
    right.close()
    channel = _Channel(left)
    supervisor, receipt = None, None
    stop_at = min(time.monotonic() + 5., d['execution_deadline_monotonic'])
    while time.monotonic() < stop_at:
        for row in channel.receive(_POLL):
            if row.get('kind') == 'ready': supervisor = row.get('identity')
        if supervisor or channel.closed: break
    ready = supervisor is not None
    if supervisor is None:
        # We still own the pre-activation child and must not lose its cleanup.
        supervisor = _identity(supervisor_pid)
    if supervisor is None or supervisor.get('pid') != supervisor_pid:
        raise RuntimeError('supervisor readiness identity unavailable')
    # A lost/late readiness cut still records exact roles for survivor cleanup;
    # only an explicit READY message admits the ACTIVE phase/producer.
    d=_update(job,d,{'execution_deadline_monotonic':d['execution_deadline_monotonic'],
        'supervision':{'schema_version':SCHEMA,'phase':'ACTIVE' if ready and not _STOP else 'CLEANUP',
                       'roles':{'guardian':guardian,'supervisor':supervisor},
                       'cleanup_limit_seconds':CLEANUP_SECONDS}})
    try:
        if ready and not _STOP and identity_state(supervisor) == 'LIVE':
            channel.send({'kind': 'activate', 'guardian': guardian, 'supervisor': supervisor})
        else:
            _signal(supervisor, signal.SIGTERM)
    except OSError: channel.closed = True
    cleanup_deadline=None
    stop_causes=[]
    while True:
        for row in channel.receive(_POLL):
            if row.get('kind')=='settled':receipt=row.get('receipt')
            elif row.get('kind')=='cleanup-start':
                cleanup_deadline=row['deadline_monotonic']
                d.setdefault('supervision',{})['cleanup_deadline_monotonic']=cleanup_deadline
        stop_causes=list(dict.fromkeys(stop_causes+_requested_causes(d)))
        if receipt is not None:break
        if stop_causes and cleanup_deadline is None:
            cleanup_deadline=_cleanup_deadline(job,d,d['execution_deadline_monotonic'])
            try:channel.send({'kind':'cleanup-request','deadline_monotonic':cleanup_deadline,'causes':stop_causes})
            except OSError:channel.closed=True
            _signal(supervisor,signal.SIGTERM)
        if channel.closed or identity_state(supervisor)!='LIVE':break
        if cleanup_deadline is not None and time.monotonic()>=cleanup_deadline-2.:
            # Reserve escalation/reaping time inside the common budget. LIVE
            # alone is not responsiveness (e.g. SIGSTOP); do not wait forever.
            _signal(supervisor,signal.SIGKILL)
            stop_causes.append('supervisor-unresponsive')
            break
    if receipt is None:
        tree = _Tree()
        deadline = _cleanup_deadline(job, d, d['execution_deadline_monotonic'])
        cleanup = tree.cleanup(deadline)
        try:
            base,progress=_runtime_cut(job,d)
            observed={**base,**progress}
        except (OSError, ValueError): observed = d
        producer = (observed.get('producer_identity') or {}).get('pid')
        producer_identity=observed.get('producer_identity') or {}
        code=_producer_exit(None,producer_identity or None,tree.exits)
        receipt = _execution_receipt(d,code,observed.get('result_before_mtime_ns'),
                                     stop_causes+_requested_causes(d)+['supervisor-lost'],cleanup)
    else:
        # Supervisor has proved its workload empty; verify that this subreaper
        # has no escaped adoptions either, without signalling the live owner.
        tree = _Tree(exclude=(supervisor,))
        cleanup = tree.cleanup(float(receipt['cleanup']['deadline_monotonic']))
        if cleanup['status'] != 'VERIFIED':
            receipt = {**receipt, 'state': 'CLEANUP_UNRESOLVED', 'cleanup': cleanup}
        else:
            receipt['cleanup']['guardian_verification'] = cleanup
    _publish(job, d, receipt, 'guardian', guardian, supervisor)
    try: channel.send({'kind': 'published'})
    except OSError: pass
    channel.close()
    # Only the exact cleanup owner remains, with no authority to activate work
    # after TERMINAL. Never turn its reap into an unbounded post-deadline wait.
    while True:
        try: reaped,_=os.waitpid(supervisor_pid,os.WNOHANG)
        except ChildProcessError: break
        if reaped: break
        if time.monotonic()>=float(receipt['cleanup']['deadline_monotonic']):
            _signal(supervisor,signal.SIGKILL)
            try: os.waitpid(supervisor_pid,os.WNOHANG)
            except ChildProcessError: pass
            break
        time.sleep(_POLL)



if __name__ == '__main__':
    main()
