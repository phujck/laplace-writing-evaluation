"""The development-source / Work-recipient join after the causal correction and the residual closure (2026-10-20): one
integrated witness through the real native, admission and control paths, and finite adverse controls for the five
contract groups (authority, effect recovery, check scope/budgets/cancellation, event-wide delivery with the once-only
parent return, canonical cut-pinned projection).

Participants are app-owned and deterministic (the shared `tree` fixture arms the test guard, binds the deterministic
provider at the runtime lookup and keeps child turns in this process). No real model, provider, science or canonical
project is touched; the fixture checkout is a disposable git repository committed through dulwich with hooks cleared.

Witness: the human/admin door binds the reviewer and issues the ROOT grant to the exact parent session (a native turn
cannot) -> the parent's turn delegates a subset to the worker it opened -> the worker reads the exact pin, prepares,
applies and checks the candidate under the scratch-only sandbox -> the parent's turn hands off the pinned file and
submits the obligation with an approved parent return -> the reviewer session reads the grant as the admitted
evaluator and records ACCEPT -> the terminal path appends RESULT and, the parent being idle, ADMITS one continuation
turn in the same parent session without any external send -> a delivery submitted from that continuation is refused
further depth -> the shared projection's acceptance is canonical and its pages are cut-pinned.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path

import pytest

import runtime_guard
from laplace.work import project_work
from laplace.web import project_work_surface
from laplace.writing import provider as writing_provider
from laplace.native import tools as writing_tools
from laplace.work import development_source, work_delivery
from laplace.writing import turn_admission, turn_control, turn_jobs
from laplace.writing import records as writing_records
from test_writing_dispatch import _StubTurn, _parent_turn, tree  # noqa: F401

P = 'book'
BASE_A = 'def answer():\n    return 41\n'
NEW_A = 'def answer():\n    return 42\n'
BUDGET = 65536
PAGE = development_source.SCRATCH_PAGE
CHECK = ('import json, os, socket, sys\n'
         'out = os.environ["LAPLACE_CHECK_OUTPUT"]\n'
         'text = open("src/a.py").read()\n'
         'assert "return 42" in text, text\n'
         'scoped = not os.path.exists("README.md") and not os.path.exists("src/secret.pem") and not os.path.exists(".git")\n'
         'home_absent = not os.path.exists("/home"); etc_absent = not os.path.exists("/etc/passwd")\n'
         'try:\n    open("src/a.py", "a").write("x"); input_writable = True\nexcept OSError:\n    input_writable = False\n'
         'try:\n    socket.create_connection(("1.1.1.1", 53), timeout=1); network = True\nexcept OSError:\n    network = False\n'
         'open(os.path.join(out, "result.json"), "w").write(json.dumps({"ok": True, "pid": os.getpid()}))\n'
         'scratch_only = os.path.samefile(out, "/tmp") and int(os.environ["LAPLACE_CHECK_SCRATCH_BYTES"]) > 0\n'
         'print(json.dumps({"scoped": scoped, "home_absent": home_absent, "etc_absent": etc_absent, "input_writable": input_writable, "network": network,\n'
         '                  "scratch_only": scratch_only, "env": sorted(os.environ), "pid": os.getpid()}))\n'
         'sys.exit(0 if (scoped and home_absent and etc_absent and not input_writable and not network and scratch_only) else 3)\n')
ESCAPE = 'open("src/a.py", "a").write("escaped")\nprint("wrote into the input")\n'
SLEEP = 'import time\ntime.sleep(30)\n'
HOG = 'x = bytearray(600 * 1024 * 1024)\nprint("allocated")\n'
FORKS = ('import os\nok = 0\nfor i in range(20):\n    try:\n        pid = os.fork()\n        if pid == 0:\n            os._exit(0)\n        ok += 1\n'
         '    except BlockingIOError:\n        break\nprint("forks", ok)\n')
BIGFILE = 'import os\nopen(os.path.join(os.environ["LAPLACE_CHECK_OUTPUT"], "big"), "wb").write(b"x" * 200000)\nprint("wrote big")\n'
# the whole write policy (J-R3-R1-DEV): a tiny unbuffered attempt on every exposed mount, device semantics, the scratch quota
MOUNTS = ('import json, os\n'
          'def put(path, data):\n    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)\n    try:\n        os.write(fd, data)\n    finally:\n        os.close(fd)\n'
          'out = {}\n'
          'for label, path in [("root", "/x"), ("dev", "/dev/x"), ("usr", "/usr/x"), ("proc", "/proc/x"), ("stage", "x"), ("tmp", "/tmp/x")]:\n'
          '    try:\n        put(path, b"x" * 768); out[label] = "writable"\n    except OSError as e:\n        out[label] = "errno%d" % e.errno\n'
          '    try:\n        os.mkdir(path + ".d"); out[label + ".dir"] = "mkdir"\n    except OSError as e:\n        out[label + ".dir"] = "errno%d" % e.errno\n'
          'try:\n    put("/dev/null", b"x" * 8192); out["devnull"] = "ok"\nexcept OSError as e:\n    out["devnull"] = "errno%d" % e.errno\n'
          'out["urandom"] = len(os.urandom(4))\n'
          'written = 0\n'
          'try:\n    for i in range(3):\n        put("/tmp/part%d" % i, b"x" * 768); written += 768\n    out["quota"] = "unbounded"\n'
          'except OSError as e:\n    out["quota"] = "errno%d after %d" % (e.errno, written)\n'
          'out["mounts"] = sorted(line.split()[1] for line in open("/proc/self/mounts"))\n'
          'out["cwd"] = os.getcwd()\n'
          'out["input"] = open("src/a.py").read()\n'
          'print(json.dumps(out))\n')
# Sol's J-R3-R1 witness shape: a few small files, the aggregate printed as they land, no stress
DURING = ('import json, os, time\nout = os.environ["LAPLACE_CHECK_OUTPUT"]\ntotal = 0\n'
          'for i in range(3):\n    with open(os.path.join(out, "part%d" % i), "wb") as f:\n        f.write(b"x" * 768)\n    total += 768\n'
          '    print(json.dumps({"during_output_bytes": total}), flush=True)\ntime.sleep(0.2)\nprint("all three written")\n')


def _sha(text: str) -> str:
    return 'sha256:' + hashlib.sha256(text.encode()).hexdigest()


def _commit(devsrc: Path, relatives: list, message: bytes) -> str:
    """One commit through dulwich's repository API with its shell hooks cleared: pure Python, no git or hook subprocess."""
    from dulwich.repo import Repo
    repo = Repo(str(devsrc)) if (devsrc / '.git').exists() else Repo.init(str(devsrc))
    repo.hooks.clear()
    worktree = repo.get_worktree()
    worktree.stage([rel.encode() for rel in relatives])
    sha = worktree.commit(message, committer=b'fixture <fixture@example.invalid>', author=b'fixture <fixture@example.invalid>', no_verify=True)
    repo.close()
    return sha.decode()


def _checkout(root: Path) -> Path:
    devsrc = root / 'devsrc'
    (devsrc / 'src').mkdir(parents=True)
    (devsrc / 'src' / 'a.py').write_text(BASE_A)
    (devsrc / 'src' / 'secret.pem').write_text('not for grants\n')
    (devsrc / 'README.md').write_text('fixture checkout\n')
    _commit(devsrc, ['src/a.py', 'README.md', 'src/secret.pem'], b'base')
    (root / 'profiles').mkdir(exist_ok=True)
    (root / 'profiles' / 'writing_sources.json').write_text(json.dumps({'repositories': {'devsrc': 'devsrc'}}))
    return devsrc


def _work(root: Path, ident: str = 'dev') -> None:
    project_work.task(P, {'id': ident, 'title': 'Answer 42', 'goal': 'Make answer() return 42 and prove it with the unit check',
                          'review_obligations': [{'id': 'source', 'scope': 'source', 'label': 'Source review', 'inputs': ['devsrc/src/a.py']}]}, root)


def _guard(root: Path, ident: str = 'dev') -> str:
    return project_work._task_revision(project_work._tasks(P, root)[ident])


def _profile(program: str, **extra) -> dict:
    return {'executable': '/usr/bin/python3', 'args': ['-I', '-c', program], 'inputs': ['src/*.py'], 'timeout_s': 30, 'max_output_bytes': BUDGET,
            'scratch_bytes': 16 * PAGE, 'memory_bytes': 256 * 1024 * 1024, 'max_processes': 4, **extra}


def _grant_payload(root: Path, parent_session: str, evaluator: str, **extra) -> dict:
    return {'action': 'grant', 'request_id': 'grant-dev-1', 'work_id': 'dev', 'expected_work_revision': _guard(root), 'repository': 'devsrc', 'paths': ['src/*.py'],
            'operations': ['read', 'candidate', 'apply', 'check'], 'lifetime_s': 3600, 'parent_session_id': parent_session, 'evaluator': evaluator,
            'checks': {'unit': _profile(CHECK), 'escape': _profile(ESCAPE), 'sleep': _profile(SLEEP), 'hog': _profile(HOG), 'forks': _profile(FORKS),
                       'bigfile': _profile(BIGFILE), 'during': _profile(DURING, scratch_bytes=2 * PAGE), 'mounts': _profile(MOUNTS, scratch_bytes=2 * PAGE)}, **extra}


def _human_door(root: Path, path: str, payload: dict) -> dict:
    """The authenticated human/admin owner boundary: the Work HTTP surface's handler, called in-process (no server)."""
    code, _ctype, body = project_work_surface.handle(path, {}, 'POST', json.dumps({**payload, 'project': P}).encode(), repo_root=root)
    value = json.loads(body)
    if code != 200:
        raise ValueError(value.get('error') or str(value))
    return value


def _native(root: Path, turn_id: str, operation: str, payload: dict, mode: str = 'work') -> dict:
    return writing_tools.execute(root, P, mode, operation, payload, turn_id=turn_id)


def _task(root: Path, ident: str = 'dev') -> dict:
    return project_work._tasks(P, root)[ident]


def _development(root: Path) -> dict:
    return development_source.facet(_task(root), root, limit=64) or {}


class _StoppableStub(_StubTurn):
    """The deterministic provider honouring Stop as the real one does: a turn whose job was interrupted while it ran ends
    with the interrupted status (the stub itself only records calls)."""

    def run(self, prompt):
        result = super().run(prompt)
        job = turn_jobs._JOBS.get(self.turn_id) or {}
        return {**result, 'status': 'interrupted', 'error': 'interrupted'} if job.get('interrupt_requested') else result


class _Once(list):
    """A stub instruction list consumed by exactly one turn (the stub reads the session's list on every turn)."""
    def __init__(self, items=(), delay: float = 0.0):
        super().__init__(items)
        self.delay = delay

    def __iter__(self):
        if self.delay:
            time.sleep(self.delay)
        items = list(super().__iter__())
        self.clear()
        return iter(items)


def _run_turn(root: Path, session_id: str, instructions: list, text: str, request_id: str, mode: str = 'work') -> dict:
    _StubTurn.instructions[session_id] = _Once(instructions)
    started = turn_admission.start_turn(root, {'project': P, 'session_id': session_id, 'mode': mode, 'text': text, 'request_id': request_id})
    _wait_done(started['turn_id'])
    return started


def _wait_done(turn_id: str, timeout: float = 30.0) -> None:
    """The job's own terminal flag: set after the reply, the delivery settlement and the host completion. It is not a sender's
    publication: turn_execution._finish sets it before the parent-return callback it then runs (see _wait_published)."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        job = turn_jobs._JOBS.get(turn_id)
        if job and job.get('done'):
            return
        time.sleep(0.02)
    raise AssertionError('turn %s did not finish in %.0fs' % (turn_id, timeout))


def _wait_turn(root: Path, request_id: str, timeout: float = 30.0) -> dict:
    """A turn admitted by an owner (not by this test) is found by its stable request id and awaited."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        for turn in writing_records.fold_records(root)['turns'].values():
            if turn.get('request_id') == request_id:
                _wait_done(turn['id'], timeout)
                return turn
        time.sleep(0.05)
    raise AssertionError('no turn with request id %s in %.0fs' % (request_id, timeout))


def _publication(root: Path, event_id: str) -> dict | None:
    """The delivery owner's durable CONTINUED publication of this event's own CONT-<event> request, or None. A pure read."""
    latest = work_delivery._history(_task(root), event_id)[-1]
    turn = latest.get('continuation_turn') or {}
    return latest if latest['state'] == 'CONTINUED' and turn.get('request_id') == 'CONT-' + event_id else None


def _wait_published(root: Path, event_id: str, continuation_turn_id: str, *, parent_turn_id: str | None = None,
                    reviewer_turn_id: str | None = None, timeout: float = 30.0) -> dict:
    """Await the SENDER's publication, not the continuation turn's terminality. A return turn's job.done can precede the
    CONTINUED append of the callback that admitted it, so this waits for that exact durable owner row of the SAME continuation
    turn under one finite deadline. On timeout it fails with the owner's durable states and the parent, reviewer and
    continuation callback custody. It only reads: no recover, no write."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        row = _publication(root, event_id)
        if row is not None:
            assert row['continuation_turn']['turn_id'] == continuation_turn_id, (row['continuation_turn'], continuation_turn_id)
            return row
        time.sleep(0.02)
    history = work_delivery._history(_task(root), event_id)
    custody = {name: {key: (turn_jobs._JOBS.get(ident) or {}).get(key) for key in ('done', 'continuation_admission_error', 'delivery_settlement_error')}
               for name, ident in (('parent', parent_turn_id), ('reviewer', reviewer_turn_id), ('continuation', continuation_turn_id)) if ident}
    turns = [(t['id'], t.get('session_id')) for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == 'CONT-' + event_id]
    raise AssertionError('delivery %s: no durable CONTINUED for CONT-%s (turn %s) within %.1fs. Owner states %s, last %s reason %r. '
                         'Continuation turns %s. Callback custody %s.' % (event_id, event_id, continuation_turn_id, timeout,
                                                                        [row['state'] for row in history], history[-1]['state'],
                                                                        history[-1].get('reason'), turns, custody))


def _reviewer_instructions(monkeypatch, opened: list, instructions, delay: float = 0.0):
    """The app-owned reviewer's session opens inside the delivery: its deterministic instructions are keyed as it opens."""
    original = turn_admission.new_session

    def new_session(*args, **kwargs):
        session = original(*args, **kwargs)
        if kwargs.get('role') == 'review' or (len(args) > 5 and args[5] == 'review'):
            opened.append(session['id'])
            _StubTurn.instructions[session['id']] = _Once(instructions(session['id']) if callable(instructions) else list(instructions), delay=delay)
        return session
    monkeypatch.setattr(turn_admission, 'new_session', new_session)


def _handoff_payload(root: Path, request_id: str, pin: str, **extra) -> dict:
    return {'id': 'dev', 'phase': 'handoff', 'request_id': request_id, 'expected_work_revision': _guard(root), 'obligations': ['source'],
            'object': {'kind': 'source', 'checkpoint': 'devsrc', **extra}, 'pins': {'devsrc/src/a.py': pin}}


def _handoff(root: Path, parent: str, request_id: str, pin: str, **extra) -> str:
    return _native(root, parent, 'work_review', _handoff_payload(root, request_id, pin, **extra))['phase']['id']


def _bind(root: Path, parent: str | None = None, **extra) -> dict:
    payload = {'action': 'bind', 'work_id': 'dev', 'expected_work_revision': _guard(root), 'kind': 'app-owned', 'provider': 'claude', 'model': 'haiku', 'effort': 'low', **extra}
    return (_native(root, parent, 'work_delivery', payload) if parent else work_delivery.bind(root, P, payload, {'origin': 'human'}))['binding']


def _submit_payload(root: Path, handoff_id: str, binding_id: str, **extra) -> dict:
    return {'action': 'submit', 'work_id': 'dev', 'expected_work_revision': _guard(root), 'handoff_id': handoff_id, 'obligation_id': 'source',
            'recipient_binding_id': binding_id, **extra}


def _submit(root: Path, handoff_id: str, binding_id: str, parent: str | None = None, **extra) -> dict:
    payload = _submit_payload(root, handoff_id, binding_id, **extra)
    return _native(root, parent, 'work_delivery', payload) if parent else work_delivery.submit(root, P, payload, {'origin': 'human'})


def _turns_of(root: Path, session_id: str) -> list[dict]:
    return [t for t in writing_records.fold_records(root)['turns'].values() if t.get('session_id') == session_id]


@pytest.fixture
def harness(tree, monkeypatch):
    root = tree
    _checkout(root)
    _work(root)
    parent_session, parent_turn = _parent_turn(root)
    bwrap = shutil.which('bwrap')
    if not bwrap:
        pytest.skip('no isolation launcher (bwrap) on this host: the check is UNAVAILABLE by contract, see test_a_check_is_unavailable_before_launch_when_enforcement_is_missing')
    runtime_guard.allow_executable(monkeypatch, bwrap)
    monkeypatch.setattr(_StubTurn, 'interrupt', lambda self: None, raising=False)   # the real Stop door calls the provider's interrupt
    monkeypatch.setattr(writing_provider, 'WritingTurn', _StoppableStub)             # the runtime lookup the turn makes
    runtime_guard.assert_stub_bound()
    return root, parent_session, parent_turn


# ---------------------------------------------------------------------------------------------- the real MCP adapter process

def _adapter(root: Path, turn_id: str, bwrap: str):
    """The ACTUAL native adapter a Claude provider launches (`python -m laplace.native.tools --turn-id`), as its own
    process: contained by the runtime guard at boot, allowed only the interpreter and the exact isolation launcher."""
    import subprocess, sys
    runtime = root / 'adapter-runtime'
    runtime.mkdir(exist_ok=True)
    (runtime / 'sitecustomize.py').write_text(runtime_guard.BOOTSTRAP + "runtime_guard.ALLOWED_EXECUTABLES.add(os.environ['LAPLACE_TEST_BWRAP'])\n")
    source = Path(writing_tools.__file__).resolve().parents[2]
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(map(str, [runtime, source, Path(__file__).resolve().parent])),
           'LAPLACE_TEST_BWRAP': os.path.realpath(bwrap), 'LAPLACE_TEST_PROCESS': '1'}
    process = subprocess.Popen([sys.executable, '-m', 'laplace.native.tools', '--root', str(root), '--project', P, '--mode', 'work',
                                '--turn-id', turn_id], cwd=str(root), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}) + '\n'); process.stdin.flush()
    assert json.loads(process.stdout.readline())['id'] == 1
    return process


def _adapter_send(process, ident: int, operation: str, payload: dict) -> None:
    process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                                    'params': {'name': 'laplace_project', 'arguments': {'operation': operation, 'payload': payload}}}) + '\n')
    process.stdin.flush()


def _adapter_result(process) -> dict:
    reply = json.loads(process.stdout.readline())
    return json.loads(reply['result']['content'][0]['text'])


def _hosted_parent(root: Path, parent_session: str, parent: str, provider) -> dict:
    """THIS test process is the parent's stable host (as the app is); the adapter is a different process of that turn."""
    from laplace.writing import child_hosts
    identity = child_hosts._process_identity(provider.pid)
    child_hosts._begin_child_execution(root, parent_session, {'state': 'RUNNING', 'turn_id': parent, 'session_id': parent_session, 'project': P,
        'host': child_hosts._process_identity(), 'provider_process': identity, 'provider_processes': [identity],
        'provider_phase': 'inference', 'provider_inference_started': True})
    return child_hosts._child_execution_record(root, parent_session)


def _quick_grant(root: Path, parent_session: str) -> dict:
    return development_source.grant(root, P, _grant_payload(root, parent_session, _bind(root)['id'], request_id='grant-aux-1',
        checks={'quick': _profile('print("auxiliary owner ok")'), 'sleep': _profile(SLEEP)}), {'origin': 'human'})['grant']


def _sleeper():
    import subprocess, sys
    return subprocess.Popen([sys.executable, '-S', '-c', 'import time;time.sleep(60)'], start_new_session=True)


def test_cross_process_native_check_registers_an_auxiliary_owner_without_touching_provider_facts(harness):
    """The reached failure: a Claude native check runs in the MCP adapter, a different process from the turn's host, and
    the strict provider registrar refused it (CANCELLED). It now completes as an auxiliary of the exact generation."""
    from laplace.writing import child_hosts
    root, parent_session, parent = harness
    grant = _quick_grant(root, parent_session)
    provider = _sleeper()
    adapter = None
    try:
        before = _hosted_parent(root, parent_session, parent, provider)
        adapter = _adapter(root, parent, shutil.which('bwrap'))
        _adapter_send(adapter, 2, 'development_source', {'action': 'check', 'grant_id': grant['id'], 'name': 'quick'})
        check = _adapter_result(adapter)['check']
        adapter.stdin.close(); adapter.wait(timeout=10)
        assert check['state'] == 'COMPLETE' and check['exit_code'] == 0 and 'auxiliary owner ok' in check['stdout_tail'], check
        row = child_hosts._child_execution_record(root, parent_session)
        [entry] = row['auxiliary_processes']
        assert entry['registrant']['pid'] == adapter.pid != os.getpid() == row['host']['pid'] and entry['phase'] == 'development-check'
        assert {key: row[key] for key in ('provider_process', 'provider_processes', 'provider_phase', 'provider_inference_started', 'host', 'turn_id')} == \
               {key: before[key] for key in ('provider_process', 'provider_processes', 'provider_phase', 'provider_inference_started', 'host', 'turn_id')}
        assert not child_hosts._process_matches(entry), 'the owner reaped its own check'
    finally:
        if adapter and adapter.poll() is None:adapter.kill(); adapter.wait(timeout=5)
        provider.kill(); provider.wait(timeout=5)


@pytest.mark.parametrize('control', ['generation', 'revoke', 'stop'])
def test_held_cross_process_check_stops_only_its_own_auxiliary_on_generation_revoke_or_stop(harness, control):
    from laplace.writing import child_hosts
    root, parent_session, parent = harness
    grant = _quick_grant(root, parent_session)
    provider, unrelated = _sleeper(), _sleeper()
    adapter = None
    try:
        _hosted_parent(root, parent_session, parent, provider)
        adapter = _adapter(root, parent, shutil.which('bwrap'))
        _adapter_send(adapter, 2, 'development_source', {'action': 'check', 'grant_id': grant['id'], 'name': 'sleep'})
        deadline = time.perf_counter() + 20
        while not child_hosts._child_execution_record(root, parent_session).get('auxiliary_processes'):
            assert time.perf_counter() < deadline and adapter.poll() is None, 'the held check never registered'
            time.sleep(0.05)
        [entry] = child_hosts._child_execution_record(root, parent_session)['auxiliary_processes']
        assert child_hosts._process_matches(entry)
        if control == 'generation':
            child_hosts._begin_child_execution(root, parent_session, {'state': 'RUNNING', 'turn_id': 'WT-newer', 'session_id': parent_session,
                'project': P, 'host': child_hosts._process_identity(), 'provider_processes': []})
            newer = child_hosts._child_execution_record(root, parent_session)
        elif control == 'revoke':
            development_source.revoke(root, P, {'action': 'revoke', 'grant_id': grant['id'], 'reason': 'withdrawn mid-check'}, {'origin': 'human'})
        else:
            turn_control.interrupt_turn(root, {'turn_id': parent, 'project': P})
        check = _adapter_result(adapter)['check']
        adapter.stdin.close(); adapter.wait(timeout=10)
        assert check['state'] == 'CANCELLED' and check['wall_ms'] < 15000, check
        assert not child_hosts._process_matches(entry), 'the exact auxiliary is gone'
        assert unrelated.poll() is None, 'an unregistered process is never touched'
        if control == 'generation':
            assert child_hosts._child_execution_record(root, parent_session) == newer and 'auxiliary_processes' not in newer
            assert provider.poll() is None, "the newer turn's processes are untouched"
    finally:
        if adapter and adapter.poll() is None:adapter.kill(); adapter.wait(timeout=5)
        for process in (provider, unrelated):
            if process.poll() is None:process.kill()
            process.wait(timeout=5)


def test_local_selected_turn_stop_terminates_its_adapter_auxiliary_before_the_turn_ends(harness, monkeypatch):
    """The LOCAL Stop branch (the job lives in this host): the turn's check runs in its MCP adapter, so neither the job
    flag nor the provider interrupt reaches it. Stop must end that exact auxiliary by birth identity at once, while the
    turn itself is still finishing, and touch no other generation's auxiliary or any unregistered process."""
    from laplace.writing import child_hosts
    root, parent_session, parent = harness
    grant = _quick_grant(root, parent_session)
    interrupted, release = threading.Event(), threading.Event()

    class Held:
        def __init__(self, *args, **kwargs):
            self.inference_started, self.native_id = True, None
        def run(self, prompt):
            assert release.wait(60)
            return {'status': 'interrupted', 'text': ''}
        def interrupt(self):
            interrupted.set()
            return {}
    monkeypatch.setattr(writing_provider, 'WritingTurn', Held)
    other, unrelated = _sleeper(), _sleeper()
    adapter = None
    started = turn_admission.start_turn(root, {'project': P, 'session_id': parent_session, 'mode': 'work', 'text': 'hold while a check runs', 'request_id': 'local-stop-1'})
    turn_id = started['turn_id']
    try:
        deadline = time.perf_counter() + 10
        while (turn_jobs._JOBS.get(turn_id) or {}).get('provider') is None:
            assert time.perf_counter() < deadline; time.sleep(0.02)
        sibling = turn_admission.new_session(root, P, 'claude', 'haiku', 'low')
        child_hosts._begin_child_execution(root, sibling['id'], {'state': 'RUNNING', 'turn_id': 'WT-other-generation', 'session_id': sibling['id'],
            'project': P, 'host': child_hosts._process_identity(), 'provider_processes': []})
        foreign = child_hosts._register_auxiliary_process(root, child_hosts.auxiliary_generation(root, sibling['id'], 'WT-other-generation'), other, 'development-check')
        sibling_before = child_hosts._child_execution_record(root, sibling['id'])
        adapter = _adapter(root, turn_id, shutil.which('bwrap'))
        _adapter_send(adapter, 2, 'development_source', {'action': 'check', 'grant_id': grant['id'], 'name': 'sleep'})
        while not child_hosts._child_execution_record(root, parent_session).get('auxiliary_processes'):
            assert time.perf_counter() < deadline + 20 and adapter.poll() is None, 'the held check never registered'
            time.sleep(0.05)
        [entry] = child_hosts._child_execution_record(root, parent_session)['auxiliary_processes']
        assert child_hosts._process_matches(entry) and entry['registrant']['pid'] == adapter.pid
        stopped = turn_control.interrupt_turn(root, {'turn_id': turn_id, 'project': P})
        assert stopped['turn_ids'] == [turn_id] and interrupted.is_set()
        gone = time.perf_counter() + 5
        while child_hosts._process_matches(entry):
            assert time.perf_counter() < gone, 'local Stop left the turn auxiliary running until a later status transition'
            time.sleep(0.05)
        assert not turn_jobs._JOBS[turn_id]['done'], 'the auxiliary ended by Stop itself, not by the turn finishing'
        check = _adapter_result(adapter)['check']
        assert check['state'] == 'CANCELLED', check
        assert child_hosts._process_matches(foreign) and unrelated.poll() is None
        assert child_hosts._child_execution_record(root, sibling['id']) == sibling_before
    finally:
        release.set()
        _wait_done(turn_id)
        if adapter and adapter.poll() is None:adapter.kill(); adapter.wait(timeout=5)
        for process in (other, unrelated):
            if process.poll() is None:process.kill()
            process.wait(timeout=5)


def test_local_stop_refuses_a_later_adapter_check_and_never_poisons_the_next_turn(harness, monkeypatch):
    """Independent HOLD runtime-local-stop-002: after a LOCAL selected-turn Stop, while the job is still finishing, a NEW
    native check of that turn admitted by its separate MCP adapter must not run. The shared stop fact is the existing
    exact-turn cancel marker, qualified by generation and removed with the stopped turn, so the session's next turn (and
    every other session) is not cancelled by it."""
    from laplace.writing import child_hosts
    root, parent_session, parent = harness
    grant = _quick_grant(root, parent_session)
    releases, interrupts = [threading.Event(), threading.Event()], []

    class Held:
        count = 0
        def __init__(self, *args, **kwargs):
            self.inference_started, self.native_id = True, None
            self.release = releases[Held.count]; Held.count += 1
        def run(self, prompt):
            assert self.release.wait(60)
            return {'status': 'interrupted' if interrupts else 'completed', 'text': ''}
        def interrupt(self):
            interrupts.append(True)
            return {}
    monkeypatch.setattr(writing_provider, 'WritingTurn', Held)
    marker_path = child_hosts._host_path(root, parent_session).with_suffix('.cancel.json')
    sibling = turn_admission.new_session(root, P, 'claude', 'haiku', 'low')
    turns, adapters = [], []

    def held_turn(request_id):
        started = turn_admission.start_turn(root, {'project': P, 'session_id': parent_session, 'mode': 'work', 'text': 'hold', 'request_id': request_id})
        turns.append(started['turn_id'])
        deadline = time.perf_counter() + 10
        while (turn_jobs._JOBS.get(started['turn_id']) or {}).get('provider') is None:
            assert time.perf_counter() < deadline; time.sleep(0.02)
        return started['turn_id']

    def adapter_check(turn_id):
        adapter = _adapter(root, turn_id, shutil.which('bwrap')); adapters.append(adapter)
        _adapter_send(adapter, 2, 'development_source', {'action': 'check', 'grant_id': grant['id'], 'name': 'quick'})
        check = _adapter_result(adapter)['check']
        adapter.stdin.close(); adapter.wait(timeout=10)
        return check
    try:
        stopped_turn = held_turn('local-stop-later-1')
        turn_control.interrupt_turn(root, {'turn_id': stopped_turn, 'project': P})
        assert interrupts and not turn_jobs._JOBS[stopped_turn]['done']
        marker = child_hosts._read_host(marker_path)
        assert marker['turn_id'] == stopped_turn and marker['host'] == child_hosts._process_identity() and marker['scope'] == 'selected-turn'
        late = adapter_check(stopped_turn)
        assert late['state'] == 'CANCELLED' and late.get('exit_code') is None, late
        assert 'auxiliary_processes' not in child_hosts._child_execution_record(root, parent_session), 'nothing was launched or registered'
        assert not child_hosts._host_path(root, sibling['id']).with_suffix('.cancel.json').exists()
        # the stopped turn ends; its marker STAYS (no timing cleanup is an authority fence) and still names only that
        # generation, so the session's NEXT turn runs its check normally
        releases[0].set(); _wait_done(stopped_turn)
        assert child_hosts._read_host(marker_path) == marker
        interrupts.clear()
        newer = held_turn('local-stop-later-2')
        fresh = adapter_check(newer)
        assert fresh['state'] == 'COMPLETE' and fresh['exit_code'] == 0, fresh
    finally:
        for release in releases:release.set()
        for turn_id in turns:_wait_done(turn_id)
        for adapter in adapters:
            if adapter.poll() is None:adapter.kill(); adapter.wait(timeout=5)


def test_cancel_marker_applies_to_its_own_generation_only_and_malformed_custody_stops(harness):
    """Independent HOLD runtime-stale-stop-001 and its neighbours, through the ACTUAL adapter: the session's shared Stop
    marker stops a check only for the turn (and recorded host) it names; another session's marker, an older turn's or a
    dead host's marker never stop the current generation; a malformed marker is protective; a current Stop arriving while
    a stale marker is present still cancels the running check and ends its exact auxiliary."""
    from laplace.writing import child_hosts
    root, parent_session, parent = harness
    grant = _quick_grant(root, parent_session)
    provider = _sleeper()
    adapters = []
    marker_path = child_hosts._host_path(root, parent_session).with_suffix('.cancel.json')

    def check(name='quick'):
        adapter = _adapter(root, parent, shutil.which('bwrap')); adapters.append(adapter)
        _adapter_send(adapter, 2, 'development_source', {'action': 'check', 'grant_id': grant['id'], 'name': name})
        return adapter
    def result(adapter):
        value = _adapter_result(adapter)['check']
        adapter.stdin.close(); adapter.wait(timeout=10)
        return value
    try:
        current = _hosted_parent(root, parent_session, parent, provider)['host']
        sibling = turn_admission.new_session(root, P, 'claude', 'haiku', 'low')
        child_hosts._write_host(child_hosts._host_path(root, sibling['id']).with_suffix('.cancel.json'), {'turn_id': parent, 'requested_at': 1.0})
        outcomes = {'other-session': result(check())}
        for label, marker in [('older-turn-dead-host', {'turn_id': 'WT-previous-generation', 'host': {'pid': 999999999, 'created_at': -1.0}, 'requested_at': 1.0, 'scope': 'selected-turn'}),
                              ('older-turn-this-host', {'turn_id': 'WT-previous-generation', 'host': current, 'requested_at': 1.0, 'scope': 'selected-turn'})]:
            child_hosts._write_host(marker_path, marker)
            outcomes[label] = result(check())
        assert all(value['state'] == 'COMPLETE' and value['exit_code'] == 0 for value in outcomes.values()), \
            {label: (value['state'], value.get('reason')) for label, value in outcomes.items()}
        registered = len(child_hosts._child_execution_record(root, parent_session).get('auxiliary_processes') or [])
        assert registered == len(outcomes)
        for label, write in [('malformed', lambda: marker_path.write_text('not a marker')),
                             ('no-turn', lambda: child_hosts._write_host(marker_path, {'requested_at': 1.0})),
                             ('current-turn-remote-shape', lambda: child_hosts._write_host(marker_path, {'turn_id': parent, 'requested_at': 1.0})),
                             ('current-turn-this-host', lambda: child_hosts._write_host(marker_path, {'turn_id': parent, 'host': current, 'requested_at': 1.0})),
                             ('current-turn-ambiguous-host', lambda: child_hosts._write_host(marker_path, {'turn_id': parent, 'host': {'pid': 999999999, 'created_at': -1.0}, 'requested_at': 1.0}))]:
            write()
            value = result(check())
            assert value['state'] == 'CANCELLED' and value.get('exit_code') is None, (label, value)
        assert len(child_hosts._child_execution_record(root, parent_session)['auxiliary_processes']) == registered, 'protective refusals launched nothing'
        # the generation race: a stale marker is present while a held check runs; the current Stop then replaces it
        child_hosts._write_host(marker_path, {'turn_id': 'WT-previous-generation', 'host': {'pid': 999999999, 'created_at': -1.0}, 'requested_at': 1.0})
        held = check('sleep')
        deadline = time.perf_counter() + 20
        while len(child_hosts._child_execution_record(root, parent_session)['auxiliary_processes']) == registered:
            assert time.perf_counter() < deadline and held.poll() is None, 'the held check never registered under a stale marker'
            time.sleep(0.05)
        entry = child_hosts._child_execution_record(root, parent_session)['auxiliary_processes'][-1]
        assert child_hosts._process_matches(entry)
        turn_control.interrupt_turn(root, {'turn_id': parent, 'project': P})
        assert child_hosts._read_host(marker_path)['turn_id'] == parent
        stopped = result(held)
        assert stopped['state'] == 'CANCELLED' and not child_hosts._process_matches(entry), stopped
    finally:
        for adapter in adapters:
            if adapter.poll() is None:adapter.kill(); adapter.wait(timeout=5)
        if provider.poll() is None:provider.kill()
        provider.wait(timeout=5)


def test_native_check_without_a_live_hosted_generation_is_refused_before_launch(harness):
    from laplace.writing import child_hosts
    root, parent_session, parent = harness
    grant = _quick_grant(root, parent_session)
    run = lambda: development_source.check(root, P, {'action': 'check', 'grant_id': grant['id'], 'name': 'quick'}, {'origin': 'native', 'turn_id': parent})['check']
    absent = run()   # WT-parent is an admitted turn with no execution record
    assert absent['state'] == 'CANCELLED' and 'no live hosted execution' in absent['reason'] and absent.get('exit_code') is None
    # a reused pid (alive, different birth time) is not the recorded host
    child_hosts._begin_child_execution(root, parent_session, {'state': 'RUNNING', 'turn_id': parent, 'session_id': parent_session, 'project': P,
        'host': {'pid': os.getpid(), 'created_at': -1.0}, 'provider_processes': []})
    reused = run()
    assert reused['state'] == 'CANCELLED' and 'no live hosted execution' in reused['reason'] and reused.get('exit_code') is None
    assert 'auxiliary_processes' not in child_hosts._child_execution_record(root, parent_session)


# ---------------------------------------------------------------------------------------------- Source review transport

SOURCE_REVIEW_PATHS = ['src/laplace/pipeline/workflow_definition_records.py', 'src/laplace/pipeline/workflow_definitions.py',
                       'src/laplace/pipeline/workflow_operations.py', 'src/laplace/work/project_work.py', 'src/laplace/work/work_delivery.py',
                       'src/laplace/writing/dispatch_parent.py', 'src/laplace/writing/workflow_dispatch.py',
                       'src/laplace/writing/workflow_progression.py', 'tests/test_workflow_operations.py']


def test_source_review_request_carries_every_initial_read_as_its_native_call_within_the_message_limit(monkeypatch):
    """The first Source review delivery failed admission: its 86 bounded initial reads repeated each read's HTTP and human
    carriers (the same URL twice) beside the native call, so the request exceeded the 100000-character turn limit. The
    request now carries each read as its exact window plus its native operation/payload: every read, every window and
    every full pin kept, nothing selected away, the immutable plan untouched and still inspectable."""
    import copy as copylib
    from laplace.work import development_source
    project, repository = 'writing-system-architecture', 'laplace-workflow-operation-opus-20261030'
    pins = {path: 'sha256:' + hashlib.sha256(path.encode()).hexdigest() for path in SOURCE_REVIEW_PATHS}
    counts = [3, 6, 11, 18, 4, 9, 8, 21, 6]   # 86 reads, uneven like a real plan
    inputs = []
    for path, count in zip(SOURCE_REVIEW_PATHS, counts):
        reads = [{'path': path, 'offset': n * 6000, 'chars': 6000, 'stop_before_offset': count * 6000 - 17,
                  'read': development_source._plan_read_handle(project, repository, path, pins[path], n * 6000, 6000)} for n in range(count)]
        inputs.append({'path': path, 'verified_edits': {'edits': []}, 'initial_reads': reads,
                       'requested_context': [{'id': 'window-1', 'line_start': 1, 'line_end': 900, 'path': path}],
                       'selected_context': [], 'uninspected_extents': [], 'uncovered_edit_ids': []})
    planned = {'state': 'COMPLETE', 'plan_id': 'DRP-' + '4' * 64, 'inputs': inputs}
    original = copylib.deepcopy(planned)
    monkeypatch.setattr(development_source, 'review_plan_for_inputs', lambda plan, consumed: planned)
    task = {'id': 'WORK-transport', 'project': project, 'title': 'Transport', 'goal': 'Review the exact candidate',
            'review_obligations': [{'id': 'owner-source', 'scope': 'source', 'label': 'Independent review', 'inputs': SOURCE_REVIEW_PATHS}]}
    basis = {'repository': repository, 'base': 'f' * 40, 'grant_id': 'DG-transport', 'candidate_id': 'DC-transport', 'effect_id': 'DE-transport'}
    plan = {'candidate_files': [{'path': path, 'before_sha256': pins[path], 'after_sha256': pins[path], 'changed': False} for path in SOURCE_REVIEW_PATHS]}
    handoff = {'id': 'PHASE-transport', 'pins': pins, 'source_basis': basis, 'source_review_plan': plan}
    intent = {'id': 'WD-transport', 'obligation_id': 'owner-source', 'handoff_id': 'PHASE-transport', 'work_scope_revision': 'sha256:' + '9' * 64,
              'recipient': {'effect': 'independent-review'}, 'source_basis': basis, 'source_review_plan': copylib.deepcopy(plan)}
    intent_before = copylib.deepcopy(intent)
    text = work_delivery._request_text(task, intent, handoff)
    every = [read for item in original['inputs'] for read in item['initial_reads']]
    assert len(every) == 86
    full_line = len(json.dumps(every, sort_keys=True))
    assert full_line > 100000, 'the fixture reproduces the failing scale: the full read DTOs alone exceed the limit'
    assert len(text) <= 100000, len(text)
    [line] = [row for row in text.split('\n') if row.startswith('Bounded initial reads')]
    carried = json.loads(line[line.index('full input pin): ') + len('full input pin): '):])
    assert carried == [work_delivery.native_initial_read(read) for read in every]
    for sent, read in zip(carried, every):
        assert set(sent) == {'path', 'offset', 'chars', 'stop_before_offset', 'operation', 'payload'}
        assert sent['payload'] == read['read']['payload'] and sent['operation'] == read['read']['operation'] == 'repository'
        assert (sent['path'], sent['offset'], sent['chars'], sent['stop_before_offset']) == (read['path'], read['offset'], read['chars'], read['stop_before_offset'])
        assert sent['payload']['expected_sha256'] == pins[read['path']] and sent['payload']['limit'] == read['chars']
    assert 'human_read' not in line and '/projects/material-references' not in line
    # nothing else of the request is dropped, and the immutable plan and intent are unchanged
    for path in SOURCE_REVIEW_PATHS:
        # 0864: the owner-authored legacy render is per-path 'Latest-delta verified edits in' plus 'Context and coverage for'
        rows = text.split('\n')
        [edits] = [row for row in rows if row.startswith('Latest-delta verified edits in ' + path + ': ')]
        [context] = [row for row in rows if row.startswith('Context and coverage for ' + path + ': ')]
        item = next(i for i in original['inputs'] if i['path'] == path)
        assert json.loads(edits[len('Latest-delta verified edits in ' + path + ': '):]) == item['verified_edits']['edits']
        assert json.loads(context[len('Context and coverage for ' + path + ': '):]) == {key: item.get(key) for key in (
            'requested_context', 'selected_context', 'uninspected_extents', 'uncovered_edit_ids', 'uncovered_hunk_ids')}
        assert len(text.encode('utf-8')) <= work_delivery.MAX_REVIEW_REQUEST_BYTES   # the actual UTF-8 request ceiling
    assert 'Each initial read carries its full input pin' in text and 'Exact qualified handoff read: ' in text
    assert planned == original and intent == intent_before
    assert all('http' in read['read'] and 'human_read' in read['read'] for read in every), 'the plan still holds every carrier'


def test_review_pins_stay_exact_and_a_refusal_states_totals_and_every_category(harness):
    """Exact handed-off pin comparison is unchanged (13 of 13 accepted; omitted, extra or changed refused); the refusal
    now says expected and supplied totals and the full count of missing, extra and different pins, with a preview of at
    most six names each, which is a display bound, never an input limit."""
    from laplace.work import project_work_review
    root, parent_session, parent = harness
    project_work.task(P, {'id': 'pins13', 'title': 'Thirteen inputs', 'goal': 'Review all thirteen handed-off files',
                          'review_obligations': [{'id': 'all', 'scope': 'source', 'label': 'All inputs', 'inputs': []}]}, root)
    files = ['devsrc/src/f%02d.py' % n for n in range(13)]
    for n, rel in enumerate(files):
        (root / rel).write_text('VALUE = %d\n' % n)
    pins = {rel: _sha((root / rel).read_text()) for rel in files}
    handoff = _native(root, parent, 'work_review', {'id': 'pins13', 'phase': 'handoff', 'request_id': 'handoff-pins13', 'expected_work_revision': _guard(root, 'pins13'),
                                                     'obligations': ['all'], 'object': {'kind': 'source', 'checkpoint': 'devsrc'}, 'pins': pins})['phase']['id']

    def review(supplied, request_id):
        return _native(root, parent, 'work_review', {'id': 'pins13', 'phase': 'review', 'request_id': request_id, 'expected_work_revision': _guard(root, 'pins13'),
                                                     'handoff_id': handoff, 'obligation_id': 'all', 'verdict': 'HOLD', 'pins': supplied})
    cases = {
        'omitted': ({k: v for k, v in pins.items() if k != files[12]}, ['supplied 12', 'missing 1 (devsrc/src/f12.py)', 'extra 0', 'different digest 0']),
        'extra': ({**pins, 'devsrc/src/a.py': _sha(BASE_A)}, ['supplied 14', 'missing 0', 'extra 1 (devsrc/src/a.py)', 'different digest 0']),
        'eight-missing': ({k: pins[k] for k in files[:5]}, ['supplied 5', 'missing 8 (first 6: devsrc/src/f05.py', 'devsrc/src/f10.py)', 'extra 0']),
    }
    for label, (supplied, expected_parts) in cases.items():
        with pytest.raises(ValueError) as refused:
            review(supplied, 'review-pins13-' + label)
        message = str(refused.value)
        assert 'Expected 13 handed-off pin(s)' in message and all(part in message for part in expected_parts), (label, message)
        assert 'devsrc/src/f11.py' not in message if label == 'eight-missing' else True, 'the preview shows six of eight, and says so'
    # a file changed since the handoff: its current pin is a DIFFERENT digest, refused as such (never renewed)
    (root / files[3]).write_text('VALUE = 333\n')
    current = {**pins, files[3]: _sha('VALUE = 333\n')}
    with pytest.raises(ValueError, match=r'supplied 13: missing 0; extra 0; different digest 1 \(devsrc/src/f03\.py\)'):
        review(current, 'review-pins13-changed')
    (root / files[3]).write_text('VALUE = 3\n')
    recorded = review(pins, 'review-pins13-exact')
    assert recorded['phase']['phase'] == 'review' and recorded['phase']['pins'] == pins
    assert project_work_review.PIN_PREVIEW == 6


# ---------------------------------------------------------------------------------------------- the witness

def test_human_root_grant_delegated_worker_review_and_automatic_idle_parent_continuation_form_one_chain(harness, monkeypatch):
    root, parent_session, parent = harness
    rows_before = len(project_work._rows(root))
    # 1. the human/admin door binds the independent reviewer and issues the ROOT grant to the exact parent session; a native
    #    turn, author role or not, cannot issue it
    binding = _human_door(root, '/work/delivery', {'action': 'bind', 'work_id': 'dev', 'expected_work_revision': _guard(root), 'kind': 'app-owned',
                                             'provider': 'claude', 'model': 'haiku', 'effort': 'low', 'label': 'independent source reviewer'})['binding']
    assert binding['state'] == 'APPROVED' and binding['expires_at']
    with pytest.raises(ValueError, match='human/admin owner boundary'):
        _native(root, parent, 'development_source', _grant_payload(root, parent_session, binding['id']))
    granted = _human_door(root, '/work/development', _grant_payload(root, parent_session, binding['id']))
    grant = granted['grant']
    assert grant['state'] == 'ACTIVE' and grant['parent_session_id'] == parent_session and grant['evaluator'] == binding['id'] and grant['grantor']['kind'] == 'human'
    replay = _human_door(root, '/work/development', _grant_payload(root, parent_session, binding['id']))
    assert replay['reused'] is True and replay['grant']['id'] == grant['id'] and replay['grant']['expires_at'] == grant['expires_at']
    # 2. the parent's own turn opens nothing by itself: the worker session exists, and the parent delegates a SUBSET to it
    worker = turn_admission.new_session(root, P, 'claude', 'haiku', 'low')
    _run_turn(root, parent_session, [('development_source', {'action': 'delegate', 'grant_id': grant['id'], 'session_id': worker['id'],
                                                             'operations': ['read', 'candidate', 'apply', 'check'], 'paths': ['src/*.py']})],
              'Delegate the worker', 'parent-delegate-1')
    assert _StubTurn.observed[-1]['tool_failures'] == [], _StubTurn.observed[-1]['tool_failures']
    assert _development(root)['grants']['items'][0]['delegates'] == {worker['id']: {'operations': ['apply', 'candidate', 'check', 'read'], 'paths': ['src/*.py']}}
    # 3. the delegate worker reads the exact pin and prepares the candidate (turn 1), applies and checks it against its own pins (turn 2)
    _run_turn(root, worker['id'], [('development_source', {'action': 'read', 'grant_id': grant['id'], 'path': 'src/a.py'}),
                                   ('development_source', {'action': 'candidate', 'grant_id': grant['id'],
                                                           'files': [{'path': 'src/a.py', 'before_sha256': _sha(BASE_A), 'content': NEW_A}]})],
              'Prepare the candidate', 'worker-1')
    first = _StubTurn.observed[-1]
    assert first['tool_failures'] == [] and [c['operation'] for c in first['calls']] == ['development_source', 'development_source']
    candidate_id = _development(root)['candidates']['items'][0]['id']
    _run_turn(root, worker['id'], [('development_source', {'action': 'apply', 'candidate_id': candidate_id}),
                                   ('development_source', {'action': 'check', 'grant_id': grant['id'], 'name': 'unit', 'candidate_id': candidate_id})],
              'Apply and check', 'worker-2')
    second = _StubTurn.observed[-1]
    assert second['tool_failures'] == [], second['tool_failures']
    facet = _development(root)
    effect, check = facet['effects']['items'][0], facet['checks']['items'][0]
    assert effect['state'] == 'COMMITTED' and effect['files'] == [('src/a.py', 'COMMITTED')] and (root / 'devsrc' / 'src' / 'a.py').read_text() == NEW_A
    effect_rows = [r for r in _task(root)['development'] if r.get('kind') == 'development-effect']
    assert [r['state'] for r in effect_rows] == ['PREPARED', 'COMMITTED'] and effect_rows[1]['actor']['session_id'] == worker['id']
    assert check['state'] == 'COMPLETE' and check['exit_code'] == 0 and check['wall_ms'] < 30000 and check['scratch_bytes'] == 16 * PAGE, check
    check_row = [r for r in _task(root)['development'] if r.get('kind') == 'development-check'][-1]
    report = json.loads(check_row['stdout_tail'].strip().splitlines()[-1])
    assert report['scoped'] and report['home_absent'] and report['etc_absent'] and not report['input_writable'] and not report['network'] and report['scratch_only']
    assert set(report['env']) <= {'PATH', 'HOME', 'LAPLACE_CHECK_OUTPUT', 'LAPLACE_CHECK_SCRATCH_BYTES', 'PYTHONDONTWRITEBYTECODE', 'LC_ALL', 'LC_CTYPE', 'PWD'}, report['env']
    assert check_row['inputs'] == [{'path': 'src/a.py', 'sha256': _sha(NEW_A)}] and check_row['candidate_id'] == candidate_id
    assert [p.name for p in Path(check_row['output_root']).iterdir()] == ['stdout.txt'], 'only the bounded stdout is published on the host'
    assert check_row['isolation']['writable'] == ['/tmp (isolated tmpfs, %d bytes; no host mount)' % (16 * PAGE)] and check_row['retained_bytes'] == check_row['stdout_bytes']
    assert check_row['isolation']['policy_verified'] is True and check_row['isolation']['read_only'][0] == '/'
    # 4. the parent's turn hands off the exact pinned file and submits with the approved parent return; the reviewer (delayed
    #    past the parent's turn) reads the grant as the admitted evaluator and records ACCEPT under its own identity
    review_guard = _guard(root)
    opened = []
    _reviewer_instructions(monkeypatch, opened, lambda _sid: [('development_source', {'action': 'read', 'grant_id': grant['id'], 'path': 'src/a.py'}),
                                                              ('work_review', {'id': 'dev', 'phase': 'review', 'request_id': 'review-dev-1', 'expected_work_revision': review_guard,
                                                                               'handoff_id': [r['id'] for r in _task(root)['phases'] if r.get('phase') == 'handoff'][-1],
                                                                               'obligation_id': 'source', 'verdict': 'ACCEPT'})], delay=1.5)
    constructions_before = len(_StubTurn.observed)
    handoff_id = _handoff(root, parent, 'handoff-dev-1', _sha(NEW_A), base=grant['base'][:12])
    _run_turn(root, parent_session, [('work_delivery', _submit_payload(root, handoff_id, binding['id'], parent_return={'admit_idle': True, 'max_attempts': 1, 'max_depth': 1}))],
              'Submit for independent review', 'parent-submit-1')
    assert _StubTurn.observed[-1]['tool_failures'] == [], _StubTurn.observed[-1]['tool_failures']
    event_id = [r for r in _task(root)['deliveries'] if r.get('kind') == 'work-delivery'][-1]['id']
    assert len(opened) == 1
    # the parent's submitting turn is terminal and the session idle BEFORE the reviewer ends: nothing but the owners run from here
    parent_turns_before = len(_turns_of(root, parent_session))
    # the parent's next instructions are what its continuation turn will do: hand off again and submit again (the depth control)
    _StubTurn.instructions[parent_session] = _Once([('work_review', _handoff_payload(root, 'handoff-dev-2', _sha(NEW_A), base=grant['base'][:12], aggregate='sha256:' + '7' * 64))])
    reviewer_turn = _wait_turn(root, event_id)
    reviewer_row = next(row for row in _StubTurn.observed if row['turn_id'] == reviewer_turn['id'])
    assert reviewer_row['tool_failures'] == [] and [c['operation'] for c in reviewer_row['calls']] == ['development_source', 'work_review'], reviewer_row
    # 5. AUTOMATIC admission: the owner admitted one continuation turn in the SAME parent session (request CONT-<event>), no external send
    continuation = _wait_turn(root, 'CONT-' + event_id)
    assert continuation['session_id'] == parent_session and continuation['mode'] == 'work'
    status = _native(root, parent, 'work_delivery', {'action': 'status', 'event_id': event_id})['event']
    assert status['state'] == 'CONTINUED' and status['admitted']['recipient_ack'] == 'TERMINAL' and status['result']['status'] == 'completed'
    assert status['parent_return']['state'] == 'CONTINUED' and status['parent_return']['continuation_turn']['turn_id'] == continuation['id']
    assert status['parent_return']['cost'] == {'provider': 'claude', 'model': 'opus', 'effort': 'high'} and 'pending_parent' not in status['facts']
    acceptance = status['acceptance']
    assert acceptance['status'] == 'ACCEPTED' and acceptance['currentness'] == 'CURRENT' and acceptance['by_this_delivery'] is True and acceptance['satisfied'] is True
    assert acceptance['independence'] == 'INDEPENDENT' and acceptance['reviewer'] == 'claude:haiku' and 'accepted' not in status and 'recovery' not in status
    cr = status['continuation_work_id']
    assert continuation['queued_work_ids'] == [cr] and event_id in continuation['text'] and 'ACCEPTED (CURRENT)' in continuation['text']
    assert _task(root, cr)['task_kind'] == 'session-request' and _task(root, cr)['logical_target']['parent_session_id'] == parent_session
    assert len(_turns_of(root, parent_session)) == parent_turns_before + 1, 'exactly one continuation turn, in the same session'
    assert len(opened) == 1 and len([t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == 'CONT-' + event_id]) == 1
    # 6. depth: the continuation turn's own handoff happened; a delivery submitted FROM the continuation is one level deeper and is
    #    refused further return (max_depth 1): no third parent turn, the result retained for inspection
    assert _StubTurn.observed[-1]['tool_failures'] == [] and [c['operation'] for c in _StubTurn.observed[-1]['calls']] == ['work_review']
    handoff2 = [r['id'] for r in _task(root)['phases'] if r.get('phase') == 'handoff'][-1]
    assert handoff2 != handoff_id
    opened_before = len(opened)
    _StubTurn.instructions[parent_session] = _Once([])
    deeper = _native(root, continuation['id'], 'work_delivery', _submit_payload(root, handoff2, binding['id'], parent_return={'admit_idle': True, 'max_attempts': 1, 'max_depth': 1}))['event']
    assert deeper['continuation']['depth'] == 1 and len(opened) == opened_before + 1
    _wait_turn(root, deeper['id'])
    time.sleep(0.3)
    refused = _native(root, parent, 'work_delivery', {'action': 'status', 'event_id': deeper['id']})['event']
    assert refused['state'] == 'PARENT_REFUSED' and 'max_depth' in refused['reason'] and refused['parent_return']['continuation_turn'] is None
    assert len(_turns_of(root, parent_session)) == parent_turns_before + 1, 'depth exhausted: no further parent turn was admitted'
    # 7. one shared projection with cut-pinned pages; duplicate submit reused; the acceptance goes STALE with the file
    detail = _native(root, parent, 'project', {'view': 'detail', 'id': 'dev'})
    task = detail['task']
    assert task['deliveries']['events'][0]['id'] == deeper['id'] and task['deliveries']['events'][1]['acceptance']['status'] == 'ACCEPTED' and task['deliveries']['cut']
    assert task['development']['effects']['items'][0]['state'] == 'COMMITTED' and task['development']['checks']['items'][0]['state'] == 'COMPLETE'
    again = _submit(root, handoff_id, binding['id'], parent)
    assert again['reused'] is True and again['event']['id'] == event_id and len(opened) == opened_before + 1
    assert len(_StubTurn.observed) == constructions_before + 4 and (root / 'devsrc' / 'src' / 'a.py').read_text() == NEW_A
    (root / 'devsrc' / 'src' / 'a.py').write_text(NEW_A + '# moved\n')
    stale = _native(root, parent, 'work_delivery', {'action': 'status', 'event_id': event_id})['event']['acceptance']
    assert stale['status'] == 'ACCEPTED' and stale['currentness'] == 'STALE' and stale['satisfied'] is False and 'changed' in stale['currentness_reason']
    rows = project_work._rows(root)
    measurements = {'provider_constructions': len(_StubTurn.observed), 'ledger_rows_appended': len(rows) - rows_before,
                    'check_wall_ms': check['wall_ms'], 'check_stdout_bytes': check['stdout_bytes'], 'review_sessions_opened': len(opened),
                    'parent_turns_total': len(_turns_of(root, parent_session)), 'continuation_text_chars': len(continuation['text']),
                    'detail_json_bytes': len(json.dumps(detail, ensure_ascii=False).encode()), 'event_json_bytes': len(json.dumps(status, ensure_ascii=False).encode())}
    assert measurements['check_stdout_bytes'] < 4096 and measurements['event_json_bytes'] < 8192
    target = os.environ.get('LAPLACE_WITNESS_MEASUREMENTS')
    (Path(target) if target else root / 'measurements.json').write_text(json.dumps(measurements, indent=1))


# ---------------------------------------------------------------------------------------------- J-R1 authority

def test_root_authority_is_human_issued_bound_to_the_parent_and_only_narrowed_by_delegation(harness):
    root, parent_session, parent = harness
    human = {'origin': 'human'}
    binding = _bind(root)
    # issuance: native turns (author role included) refuse; the evaluator and the parent session are required and checked
    stranger = turn_admission.new_session(root, P, 'claude', 'haiku', 'low')
    _run_turn(root, stranger['id'], [('development_source', _grant_payload(root, stranger['id'], binding['id'], request_id='stranger-bootstrap'))], 'bootstrap', 'stranger-boot')
    failures = _StubTurn.observed[-1]['tool_failures']
    assert len(failures) == 1 and 'human/admin owner boundary' in failures[0]['error'] and _development(root) == {}
    with pytest.raises(ValueError, match='requires evaluator'):
        development_source.grant(root, P, {k: v for k, v in _grant_payload(root, parent_session, binding['id']).items() if k != 'evaluator'}, human)
    with pytest.raises(ValueError, match='approved review binding'):
        development_source.grant(root, P, _grant_payload(root, parent_session, 'RB-000000000000000000000000'), human)
    reviewer = turn_admission.new_session(root, P, 'claude', 'haiku', 'low', role='review')
    with pytest.raises(ValueError, match='author-role session'):
        development_source.grant(root, P, _grant_payload(root, reviewer['id'], binding['id']), human)
    with pytest.raises(ValueError, match='names an existing session'):
        development_source.grant(root, P, _grant_payload(root, 'WS-00000000000000000000000000000000', binding['id']), human)
    for bad in ({'repository': 'missing'}, {'paths': ['../src/*.py']}, {'paths': ['.git/*']}, {'checks': {'x': _profile(CHECK, inputs=['README.md'])}}):
        with pytest.raises((ValueError, KeyError)):
            development_source.grant(root, P, {**_grant_payload(root, parent_session, binding['id']), **bad}, human)
    config = root / 'profiles' / 'writing_sources.json'
    config.write_text(json.dumps({'repositories': {'devsrc': 'devsrc', 'here': str(Path(__file__).resolve().parents[1]), 'whole': '.'}}))
    for repository in ('here', 'whole'):
        with pytest.raises(ValueError, match='never a development resource'):
            development_source.grant(root, P, {**_grant_payload(root, parent_session, binding['id']), 'repository': repository}, human)
    config.write_text(json.dumps({'repositories': {'devsrc': 'devsrc'}}))
    grant = development_source.grant(root, P, _grant_payload(root, parent_session, binding['id']), human)['grant']
    # delegation: only the parent (or the human door) delegates, only to an author session, only narrowing
    worker = turn_admission.new_session(root, P, 'claude', 'haiku', 'low')
    read = ('development_source', {'action': 'read', 'grant_id': grant['id'], 'path': 'src/a.py'})
    make = ('development_source', {'action': 'candidate', 'grant_id': grant['id'], 'files': [{'path': 'src/a.py', 'before_sha256': _sha(BASE_A), 'content': NEW_A}]})
    _run_turn(root, stranger['id'], [('development_source', {'action': 'delegate', 'grant_id': grant['id'], 'session_id': worker['id']}), read], 'a stranger delegates and reads', 'stranger-1')
    failures = _StubTurn.observed[-1]['tool_failures']
    assert len(failures) == 2 and 'authorised parent session' in failures[0]['error'] and 'neither the authorised parent session nor a delegate' in failures[1]['error']
    _run_turn(root, parent_session, [('development_source', {'action': 'delegate', 'grant_id': grant['id'], 'session_id': worker['id'], 'operations': ['read', 'revoke']}),
                                     ('development_source', {'action': 'delegate', 'grant_id': grant['id'], 'session_id': worker['id'], 'paths': ['README.md']}),
                                     ('development_source', {'action': 'delegate', 'grant_id': grant['id'], 'session_id': reviewer['id']}),
                                     ('development_source', {'action': 'delegate', 'grant_id': grant['id'], 'session_id': worker['id'], 'operations': ['read']})],
              'the parent delegates', 'parent-delegate-1')
    failures = _StubTurn.observed[-1]['tool_failures']
    assert len(failures) == 3 and all('only narrows' in f['error'] or 'author-role session' in f['error'] or 'is not one of' in f['error'] for f in failures), failures
    _run_turn(root, worker['id'], [read, make], 'the read-only delegate tries to write', 'worker-1')
    failures = _StubTurn.observed[-1]['tool_failures']
    assert len(failures) == 1 and 'outside the subset delegated' in failures[0]['error'] and _development(root)['candidates']['total'] == 0
    _run_turn(root, reviewer['id'], [read], 'a reviewer never admitted to this Work', 'reviewer-tries', mode='review')
    assert 'admitted evaluator session' in _StubTurn.observed[-1]['tool_failures'][0]['error']
    with pytest.raises(ValueError, match='authorised parent session'):
        _native(root, _StubTurn.observed[-2]['turn_id'], 'development_source', {'action': 'revoke', 'grant_id': grant['id']})
    # the fence, the registry re-resolution and the currentness refusals
    read_human = lambda path: development_source.read(root, P, {'action': 'read', 'grant_id': grant['id'], 'path': path}, human)
    assert read_human('src/a.py')['sha256'] == _sha(BASE_A)
    for path, why in (('src/secret.pem', 'credential'), ('README.md', 'permitted paths'), ('../other.py', 'checkout-relative'), ('.git/config', 'permitted paths|git internals')):
        with pytest.raises(ValueError, match=why):
            read_human(path)
    os.symlink(root / 'devsrc' / 'README.md', root / 'devsrc' / 'src' / 'link.py')
    with pytest.raises(ValueError, match='symlink'):
        read_human('src/link.py')
    shutil.copytree(root / 'devsrc', root / 'devsrc2', symlinks=True)
    config.write_text(json.dumps({'repositories': {'devsrc': 'devsrc2'}}))
    with pytest.raises(development_source.GrantRefused, match='now resolves to'):
        read_human('src/a.py')
    config.write_text(json.dumps({'repositories': {'devsrc': 'devsrc'}}))
    candidate = development_source.candidate(root, P, {'action': 'candidate', 'grant_id': grant['id'], 'files': [{'path': 'src/a.py', 'before_sha256': _sha(BASE_A), 'content': NEW_A}]}, human)
    project_work.task(P, {'id': 'dev', 'title': 'Answer 42', 'goal': 'A changed goal is a changed scope', 'expected_work_revision': _guard(root)}, root)
    with pytest.raises(development_source.GrantRefused, match='material scope changed'):
        development_source.apply(root, P, {'action': 'apply', 'candidate_id': candidate['candidate_id']}, human)
    assert (root / 'devsrc' / 'src' / 'a.py').read_text() == BASE_A
    fresh = development_source.grant(root, P, _grant_payload(root, parent_session, binding['id'], request_id='grant-dev-2'), human)['grant']
    (root / 'devsrc' / 'README.md').write_text('moved\n')
    _commit(root / 'devsrc', ['README.md'], b'moved')
    with pytest.raises(development_source.GrantRefused, match='base moved'):
        development_source.read(root, P, {'action': 'read', 'grant_id': fresh['id'], 'path': 'src/a.py'}, human)
    latest = development_source.grant(root, P, _grant_payload(root, parent_session, binding['id'], request_id='grant-dev-3'), human)['grant']
    development_source.revoke(root, P, {'action': 'revoke', 'grant_id': latest['id'], 'reason': 'withdrawn by the author'}, human)
    with pytest.raises(development_source.GrantRefused, match='REVOKED'):
        development_source.read(root, P, {'action': 'read', 'grant_id': latest['id'], 'path': 'src/a.py'}, human)


# ---------------------------------------------------------------------------------------------- J-R2 effect recovery

def test_apply_is_one_durable_transaction_that_recovers_the_same_request(harness, monkeypatch):
    root, parent_session, parent = harness
    human = {'origin': 'human'}
    binding = _bind(root)
    worker = turn_admission.new_session(root, P, 'claude', 'haiku', 'low')
    grant = development_source.grant(root, P, _grant_payload(root, parent_session, binding['id'], delegates=[worker['id']]), human)['grant']
    (root / 'devsrc' / 'src' / 'b.py').write_text('b = 1\n')
    files = lambda *items: [{'path': p, 'before_sha256': _sha(b), 'content': a} for p, b, a in items]
    # (a) the publish append dies after the bytes moved: the PREPARED row stands alone; the worker's retry recovers the same request
    first = development_source.candidate(root, P, {'action': 'candidate', 'grant_id': grant['id'], 'files': files(('src/a.py', BASE_A, NEW_A))}, human)
    real_append = project_work._append

    def die_on_publish(root_, row):
        if row.get('kind') == 'development-effect' and row.get('state') != 'PREPARED':
            raise RuntimeError('fixture: the process died after the write, before the publish row')
        return real_append(root_, row)
    monkeypatch.setattr(project_work, '_append', die_on_publish)
    with pytest.raises(RuntimeError, match='before the publish row'):
        development_source.apply(root, P, {'action': 'apply', 'candidate_id': first['candidate_id']}, human)
    monkeypatch.setattr(project_work, '_append', real_append)
    assert (root / 'devsrc' / 'src' / 'a.py').read_text() == NEW_A
    prepared = [r for r in _task(root)['development'] if r.get('kind') == 'development-effect']
    assert [r['state'] for r in prepared] == ['PREPARED'] and prepared[0]['files'][0]['before_sha256'] == _sha(BASE_A)
    _run_turn(root, worker['id'], [('development_source', {'action': 'apply', 'candidate_id': first['candidate_id']})], 'retry the apply', 'retry-1')
    assert _StubTurn.observed[-1]['tool_failures'] == []
    effect = _development(root)['effects']['items'][0]
    rows = [r for r in _task(root)['development'] if r.get('kind') == 'development-effect' and r['id'] == effect['id']]
    assert effect['state'] == 'COMMITTED' and effect['files'] == [('src/a.py', 'ALREADY_APPLIED')]
    assert rows[-1]['attempt'] == 2 and rows[-1]['actor'] == prepared[0]['actor'] and rows[-1]['recovered_by']['session_id'] == worker['id']
    assert development_source.apply(root, P, {'action': 'apply', 'candidate_id': first['candidate_id']}, human)['reused'] is True
    # (b) a cut before any byte moved, then someone else's edit: the retry says DIVERGED and overwrites nothing
    second = development_source.candidate(root, P, {'action': 'candidate', 'grant_id': grant['id'], 'files': files(('src/b.py', 'b = 1\n', 'b = 2\n'))}, human)
    from laplace.manuscript import manuscript_source
    real_lease = manuscript_source.source_mutation
    monkeypatch.setattr(manuscript_source, 'source_mutation', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('fixture: cut before the lease')))
    with pytest.raises(RuntimeError, match='before the lease'):
        development_source.apply(root, P, {'action': 'apply', 'candidate_id': second['candidate_id']}, human)
    monkeypatch.setattr(manuscript_source, 'source_mutation', real_lease)
    (root / 'devsrc' / 'src' / 'b.py').write_text('b = 3  # someone else\n')
    diverged = development_source.apply(root, P, {'action': 'apply', 'candidate_id': second['candidate_id']}, human)
    assert diverged['ok'] is False and diverged['effect']['state'] == 'DIVERGED' and diverged['effect']['attempt'] == 2
    assert (root / 'devsrc' / 'src' / 'b.py').read_text() == 'b = 3  # someone else\n'
    # (c) a second file fails mid-transaction: the first is compensated only because it still holds this operation's postimage
    (root / 'devsrc' / 'src' / 'b.py').write_text('b = 1\n')
    third = development_source.candidate(root, P, {'action': 'candidate', 'grant_id': grant['id'], 'files': files(('src/a.py', NEW_A, BASE_A), ('src/b.py', 'b = 1\n', 'b = 2\n'))}, human)
    from laplace.manuscript import source_effects
    real_replace = source_effects.replace

    def failing(path, data):
        if path.name == 'b.py':
            raise OSError('fixture: the second file cannot be written')
        return real_replace(path, data)
    monkeypatch.setattr(source_effects, 'replace', failing)
    result = development_source.apply(root, P, {'action': 'apply', 'candidate_id': third['candidate_id']}, human)
    monkeypatch.setattr(source_effects, 'replace', real_replace)
    effect = result['effect']
    assert result['ok'] is False and effect['state'] == 'ROLLED_BACK' and effect['failure']['path'] == 'src/b.py'
    assert [(f['path'], f['state']) for f in effect['files']] == [('src/a.py', 'ROLLED_BACK'), ('src/b.py', 'FAILED')]
    assert (root / 'devsrc' / 'src' / 'a.py').read_text() == NEW_A and (root / 'devsrc' / 'src' / 'b.py').read_text() == 'b = 1\n'
    assert effect['files'][0]['observed_after_sha256'] == _sha(NEW_A)


# ---------------------------------------------------------------------------------------------- J-R3 check scope, budgets, cancellation

def test_the_check_writes_only_into_its_bounded_scratch_under_os_budgets_and_stops_through_the_turn(harness):
    root, parent_session, parent = harness
    human = {'origin': 'human'}
    binding = _bind(root)
    worker = turn_admission.new_session(root, P, 'claude', 'haiku', 'low')
    # an unaligned or out-of-range scratch budget is refused at grant with its units, never rounded
    with pytest.raises(ValueError, match='whole multiple of the %d-byte page' % PAGE):
        development_source.grant(root, P, _grant_payload(root, parent_session, binding['id'], checks={'odd': _profile(DURING, scratch_bytes=PAGE + PAGE // 2)}), human)
    with pytest.raises(ValueError, match='scratch_bytes'):
        _human_door(root, '/work/development', _grant_payload(root, parent_session, binding['id'], checks={'tiny': _profile(DURING, scratch_bytes=1024)}))
    grant = development_source.grant(root, P, _grant_payload(root, parent_session, binding['id'], delegates=[worker['id']]), human)['grant']
    run = lambda name, **extra: development_source.check(root, P, {'action': 'check', 'grant_id': grant['id'], 'name': name, **extra}, human)['check']
    # the aggregate scratch budget holds DURING execution: two pages admit two files, the third write fails inside the run
    during = run('during')
    lines = [json.loads(line) for line in during['stdout_tail'].splitlines() if line.startswith('{')]
    assert during['state'] == 'FAILED' and 'No space left on device' in during['stdout_tail'] and 'all three written' not in during['stdout_tail'], during['stdout_tail']
    assert [row['during_output_bytes'] for row in lines] == [768, 1536] and during['scratch']['bytes'] == 2 * PAGE and during['scratch']['page_bytes'] == PAGE
    assert [p.name for p in Path(during['output_root']).iterdir()] == ['stdout.txt'] and during['retained_bytes'] == during['stdout_bytes']
    # the whole write policy: every exposed mount refuses a regular file and a directory except the bounded scratch; the device
    # nodes keep device semantics; the scratch reaches ENOSPC; no host path but the staged inputs is mounted
    mounts = run('mounts')
    policy = json.loads(mounts['stdout_tail'].strip().splitlines()[-1])
    assert mounts['state'] == 'COMPLETE', mounts['stdout_tail']
    assert {k: v for k, v in policy.items() if k in ('root', 'dev', 'usr', 'proc', 'stage')} == {k: 'errno30' for k in ('root', 'dev', 'usr', 'stage')} | {'proc': 'errno2'}, policy
    assert all(policy[k + '.dir'] != 'mkdir' for k in ('root', 'dev', 'usr', 'proc', 'stage')) and policy['tmp'] == 'writable' and policy['tmp.dir'] == 'mkdir'
    assert policy['devnull'] == 'ok' and policy['urandom'] == 4 and policy['quota'] == 'errno28 after 768', policy   # /tmp/x took the first page
    # the staged inputs are mounted at the fixed neutral /input (also the cwd), never at the host stage path
    assert set(policy['mounts']) == {'/', '/usr', '/proc', '/dev', '/dev/null', '/dev/zero', '/dev/urandom', '/dev/random', '/tmp', '/input'}, policy['mounts']
    host_stage = str((root / 'contract' / 'development_checks').resolve()) + '/' + mounts['id'] + '/input'
    assert host_stage not in policy['mounts'] and policy['cwd'] == '/input' and policy['input'] == BASE_A, policy
    assert mounts['isolation']['input_mount']['host_stage'] == host_stage and mounts['output_root'] == str(Path(host_stage).parent)
    escaped = run('escape')
    assert escaped['state'] == 'FAILED' and escaped['exit_code'] not in (0, None) and (root / 'devsrc' / 'src' / 'a.py').read_text() == BASE_A
    assert 'Permission denied' in escaped['stdout_tail'] or 'Read-only file system' in escaped['stdout_tail'], escaped['stdout_tail']
    hog = run('hog')
    assert hog['state'] == 'FAILED' and 'MemoryError' in hog['stdout_tail'], hog['stdout_tail']
    forks = run('forks')
    assert forks['state'] == 'COMPLETE' and int(forks['stdout_tail'].split()[-1]) < 10, forks['stdout_tail']
    big = run('bigfile')
    assert big['state'] == 'FAILED' and ('Errno 27' in big['stdout_tail'] or 'Errno 28' in big['stdout_tail']) and big['retained_bytes'] == big['stdout_bytes']
    candidate = development_source.candidate(root, P, {'action': 'candidate', 'grant_id': grant['id'], 'files': [{'path': 'src/a.py', 'before_sha256': _sha(BASE_A), 'content': NEW_A}]}, human)
    refused = run('unit', candidate_id=candidate['candidate_id'])
    assert refused['state'] == 'REFUSED' and 'differ from the candidate' in refused['reason'] and refused.get('exit_code') is None
    # cancellation through the REAL control path: the acting delegate turn is stopped while its check sleeps
    started = {}

    def stop_later():
        deadline = time.perf_counter() + 10
        while 'turn_id' not in started and time.perf_counter() < deadline:
            time.sleep(0.02)
        time.sleep(0.7)
        turn_control.interrupt_turn(root, {'turn_id': started['turn_id'], 'project': P})
    stopper = threading.Thread(target=stop_later, daemon=True)
    stopper.start()
    _StubTurn.instructions[worker['id']] = _Once([('development_source', {'action': 'check', 'grant_id': grant['id'], 'name': 'sleep'})])
    begun = turn_admission.start_turn(root, {'project': P, 'session_id': worker['id'], 'mode': 'work', 'text': 'run the sleeping check', 'request_id': 'sleep-1'})
    started['turn_id'] = begun['turn_id']
    _wait_done(begun['turn_id'])
    stopper.join(5)
    cancelled = _development(root)['checks']['items'][0]
    assert cancelled['name'] == 'sleep' and cancelled['state'] == 'CANCELLED' and cancelled['wall_ms'] < 10000, cancelled

    def revoke_later():
        time.sleep(0.7)
        development_source.revoke(root, P, {'action': 'revoke', 'grant_id': grant['id'], 'reason': 'withdrawn mid-check'}, human)
    revoker = threading.Thread(target=revoke_later, daemon=True)
    revoker.start()
    outcome = run('sleep')
    revoker.join(5)
    assert outcome['state'] == 'CANCELLED' and outcome['wall_ms'] < 10000


def test_a_check_is_unavailable_before_launch_when_enforcement_is_missing(tree, monkeypatch):
    root = tree
    _checkout(root); _work(root)
    parent_session, _parent = _parent_turn(root)
    grant = development_source.grant(root, P, _grant_payload(root, parent_session, _bind(root)['id']), {'origin': 'human'})['grant']
    run = lambda: development_source.check(root, P, {'action': 'check', 'grant_id': grant['id'], 'name': 'unit'}, {'origin': 'human'})['check']
    assert shutil.which('bwrap'), 'this control needs the launcher present so that the denial, not its absence, is what is proved'
    monkeypatch.setattr(development_source, '_POLICY_VERIFIED', {})   # this process may have verified the policy for another test's allowance
    denied = run()   # the test guard denies every launcher but the interpreter unless a test allows one: fail closed
    assert denied['state'] == 'UNAVAILABLE' and 'runtime guard' in (denied['reason'] or '') and 'mount policy' in denied['reason'] and (root / 'devsrc' / 'src' / 'a.py').read_text() == BASE_A
    monkeypatch.setattr(development_source, 'mount_policy_problem', lambda root_, launcher: 'the declared mount policy is not enforced on this host: {"/dev": "writable"}')
    assert 'not enforced' in run()['reason']
    monkeypatch.setattr(development_source, 'PRLIMIT', Path('/usr/bin/absent-prlimit'))
    assert 'process budget' in run()['reason']
    monkeypatch.setattr(development_source, 'isolation_launcher', lambda: None)
    assert 'never run bare' in run()['reason']
    assert all(r['state'] == 'UNAVAILABLE' and r.get('exit_code') is None for r in _development(root)['checks']['items'])


# ---------------------------------------------------------------------------------------------- J-R4 event-wide delivery and the parent return

def test_delivery_is_reserved_event_wide_revalidated_recovered_and_returned_to_the_parent_once(harness, monkeypatch):
    root, parent_session, parent = harness
    human = {'origin': 'human'}
    _work(root, 'other')
    handoff = _handoff(root, parent, 'handoff-dev-2', _sha(BASE_A))
    binding = _bind(root)
    foreign = work_delivery.bind(root, P, {'action': 'bind', 'work_id': 'other', 'expected_work_revision': _guard(root, 'other'), 'kind': 'app-owned',
                                           'provider': 'claude', 'model': 'haiku', 'effort': 'low'}, human)['binding']
    with pytest.raises(ValueError, match='approved recipient binding of this Work'):
        _submit(root, handoff, foreign['id'])
    with pytest.raises(ValueError, match='does not cover obligation'):
        _submit(root, handoff, binding['id'], obligation_id='guide')
    with pytest.raises(ValueError, match='cannot mint an external identity'):
        _bind(root, parent, kind='external', external={'actor': 'sol', 'evidence': 'evidence/none.md sha256:' + '0' * 64})
    real_time = time.time
    monkeypatch.setattr(work_delivery.time, 'time', lambda: real_time() - 7200)
    expired = _bind(root, lifetime_s=60, label='expired')
    monkeypatch.setattr(work_delivery.time, 'time', real_time)
    with pytest.raises(ValueError, match='expired'):
        _submit(root, handoff, expired['id'])
    external = work_delivery.bind(root, P, {'action': 'bind', 'work_id': 'dev', 'expected_work_revision': _guard(root), 'kind': 'external', 'label': 'Sol',
                                            'external': {'actor': 'sol-reviewer', 'profile': 'gpt-6.1-sol'}}, human)['binding']
    sessions_before = len(writing_records.fold_records(root)['sessions'])
    pending = _submit(root, handoff, external['id'])['event']
    assert pending['state'] == 'UNSUPPORTED' and 'attachment adapter' in pending['reason'] and 'recovery' not in pending
    assert len(writing_records.fold_records(root)['sessions']) == sessions_before
    opened = []
    _reviewer_instructions(monkeypatch, opened, [('work_delivery', {'action': 'status', 'work_id': 'dev'})])   # a reviewer that only reads
    # (a) the lost acknowledgement: admitted, but the retention append died; recovery finds the SAME turn by the event id
    real_append = project_work._append

    def crash_after_admission(root_, row):
        if row.get('kind') == 'work-delivery' and row.get('state') == 'ADMITTED':
            raise RuntimeError('fixture: the process died before the coordinates were retained')
        return real_append(root_, row)
    monkeypatch.setattr(project_work, '_append', crash_after_admission)
    with pytest.raises(RuntimeError, match='before the coordinates'):
        _submit(root, handoff, binding['id'])
    monkeypatch.setattr(project_work, '_append', real_append)
    events = [row for row in _task(root)['deliveries'] if row.get('kind') == 'work-delivery' and row.get('recipient', {}).get('id') == binding['id']]
    event_id = events[-1]['id']
    assert [row['state'] for row in events] == ['SUBMITTED', 'RESERVED', 'DELIVERED'] and len(opened) == 1
    # deterministic terminal-BEFORE-ADMITTED: the reviewer's own terminal hook found no ADMITTED row and settled nothing; its
    # exact saved reply is the fact recovery must publish (the recovered-before-terminal order is its own case below)
    [banked] = [t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == event_id]
    _wait_done(banked['id'])
    assert (writing_records.fold_records(root)['turns'][banked['id']].get('reply') or {}).get('status')
    assert [row['state'] for row in work_delivery._history(_task(root), event_id)][-1] == 'DELIVERED'
    recovered = work_delivery.recover(root, P, {'action': 'recover', 'event_id': event_id}, human)['event']
    admitted_rows = [row for row in work_delivery._history(_task(root), event_id) if row['state'] == 'ADMITTED']
    assert recovered['state'] == 'RESULT' and recovered['admitted']['turn_id'] == banked['id'] and recovered['admitted']['recipient_ack'] == 'TERMINAL'
    assert [(row.get('recovered'), row.get('request_id'), row.get('turn_id')) for row in admitted_rows] == [(True, event_id, banked['id'])]   # one recovered ADMITTED, then RESULT
    assert len(opened) == 1 and len([t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == event_id]) == 1
    _wait_done(recovered['admitted']['turn_id'])
    twice = work_delivery.recover(root, P, {'action': 'recover', 'event_id': event_id}, human)['event']
    assert twice['state'] == 'RESULT' and twice['admitted']['turn_id'] == recovered['admitted']['turn_id'] and twice['admitted']['recipient_ack'] == 'TERMINAL'
    assert twice['acceptance']['status'] == 'AWAITING_REVIEW' and twice['acceptance']['by_this_delivery'] is False and twice['continuation_work_id'] is None
    assert twice['parent_return']['state'] is None, 'a human-door submission has no parent: inspect-only'
    with pytest.raises(ValueError, match='Independent review can save findings|review-role turn'):
        _native(root, recovered['admitted']['turn_id'], 'work_delivery', {'action': 'recover', 'event_id': event_id}, mode='review')
    # (b) two consumers of one reserved event: the second waits on the event lock and finds the first's admission
    real_start = turn_admission.start_turn
    monkeypatch.setattr(turn_admission, 'start_turn', lambda *a, **k: (_ for _ in ()).throw(OSError('fixture: transport down')))
    handoff2 = _handoff(root, parent, 'handoff-dev-3', _sha(BASE_A), aggregate='sha256:' + '1' * 64)
    stuck = _submit(root, handoff2, binding['id'], max_attempts=3)['event']
    assert stuck['state'] == 'SUBMITTED' and stuck['attempts'] == 1 and 'transport down' in stuck['last_error'] and len(opened) == 2

    def slow_start(*args, **kwargs):
        time.sleep(1.0)
        return real_start(*args, **kwargs)
    monkeypatch.setattr(turn_admission, 'start_turn', slow_start)
    results = {}
    first = threading.Thread(target=lambda: results.update(a=work_delivery.recover(root, P, {'action': 'recover', 'event_id': stuck['id']}, human)['event']))
    first.start(); time.sleep(0.2)
    results['b'] = work_delivery.recover(root, P, {'action': 'recover', 'event_id': stuck['id']}, human)['event']
    first.join(30)
    assert results['a']['admitted']['turn_id'] == results['b']['admitted']['turn_id'] and len(opened) == 2
    assert len([t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == stuck['id']]) == 1
    _wait_done(results['a']['admitted']['turn_id'])
    monkeypatch.setattr(turn_admission, 'start_turn', real_start)
    # (c) the parent return when the submitting parent turn is STILL ACTIVE at the reviewer's end: pending (notification on the
    #     event, the row queued), then admitted ONCE by the parent's own terminal path; a duplicate settlement admits nothing more
    handoff3 = _handoff(root, parent, 'handoff-dev-4', _sha(BASE_A), aggregate='sha256:' + '2' * 64)
    # owner barrier (0864 determinism): the reviewer's terminal is awaited INSIDE the parent's own submit tool call, so the
    # parent turn is genuinely still active when the reviewer settles; nothing about the return itself is stubbed
    real_submit = work_delivery.submit

    def submit_then_await_reviewer(*args, **kwargs):
        value = real_submit(*args, **kwargs)
        reviewer = ((value.get('event') or {}).get('admitted') or {}).get('turn_id')
        if reviewer:
            _wait_done(reviewer)
        return value
    monkeypatch.setattr(work_delivery, 'submit', submit_then_await_reviewer)
    busy = _run_turn(root, parent_session, [('work_delivery', _submit_payload(root, handoff3, binding['id'], parent_return={'admit_idle': True, 'max_attempts': 1, 'max_depth': 1}))],
                     'submit while I keep working', 'parent-submit-busy')
    monkeypatch.setattr(work_delivery, 'submit', real_submit)
    assert _StubTurn.observed[-1]['tool_failures'] == []
    third = [r for r in _task(root)['deliveries'] if r.get('kind') == 'work-delivery'][-1]['id']
    reviewer3 = _wait_turn(root, third)
    continuation = _wait_turn(root, 'CONT-' + third)
    # the CONT turn's own done flag can precede the CONTINUED append of the parent's finish callback that admitted it: await
    # the delivery owner's durable publication of that SAME turn under the existing finite deadline, then assert as before
    published = _wait_published(root, third, continuation['id'], parent_turn_id=busy['turn_id'], reviewer_turn_id=reviewer3['id'])
    assert (published['continuation_turn']['session_id'], published['continuation_turn']['request_id']) == (parent_session, 'CONT-' + third)
    event = work_delivery.status(root, P, {'action': 'status', 'event_id': third}, human)['event']
    history = [row['state'] for row in _task(root)['deliveries'] if row.get('kind') == 'work-delivery' and row['id'] == third]
    assert history[-3:] == ['RESULT', 'PENDING_PARENT', 'CONTINUED'], history
    assert 'parent not admitted now' in next(r['reason'] for r in reversed(_task(root)['deliveries']) if r.get('id') == third and r['state'] == 'PENDING_PARENT')
    assert event['state'] == 'CONTINUED' and event['parent_return']['continuation_turn']['session_id'] == parent_session and continuation['session_id'] == parent_session
    assert len([t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == 'CONT-' + third]) == 1
    settled_again = work_delivery.settle_turn(root, P, event['admitted']['session_id'], event['admitted']['turn_id'], {'status': 'completed'})
    assert settled_again == [] and len([t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == 'CONT-' + third]) == 1
    # (d) revalidation at consumption: moved pins and a changed scope end the event as STALE; a stale scope also refuses the return
    monkeypatch.setattr(turn_admission, 'start_turn', lambda *a, **k: (_ for _ in ()).throw(OSError('fixture: transport down')))
    handoff4 = _handoff(root, parent, 'handoff-dev-5', _sha(BASE_A), aggregate='sha256:' + '3' * 64)
    fourth = _submit(root, handoff4, binding['id'])['event']
    (root / 'devsrc' / 'src' / 'a.py').write_text(BASE_A + '# edited after handoff\n')
    stale = work_delivery.recover(root, P, {'action': 'recover', 'event_id': fourth['id']}, human)['event']
    assert stale['state'] == 'STALE' and 'handed-off inputs changed' in stale['reason'] and 'recovery' not in stale
    (root / 'devsrc' / 'src' / 'a.py').write_text(BASE_A)
    handoff5 = _handoff(root, parent, 'handoff-dev-6', _sha(BASE_A), aggregate='sha256:' + '4' * 64)
    fifth = _submit(root, handoff5, binding['id'])['event']
    project_work.task(P, {'id': 'dev', 'title': 'Answer 42', 'goal': 'A changed goal is a changed scope', 'expected_work_revision': _guard(root)}, root)
    scoped = work_delivery.recover(root, P, {'action': 'recover', 'event_id': fifth['id']}, human)['event']
    assert scoped['state'] == 'STALE' and 'material scope changed' in scoped['reason']
    # (e) the finite budget: attempts exhausted end in UNCONFIRMED, with the reserved session reused and no turn opened
    handoff6 = _handoff(root, parent, 'handoff-dev-7', _sha(BASE_A), aggregate='sha256:' + '5' * 64)
    budget = _submit(root, handoff6, binding['id'], max_attempts=2)['event']
    sessions = len(opened)
    budget = work_delivery.recover(root, P, {'action': 'recover', 'event_id': budget['id']}, human)['event']
    assert budget['state'] == 'SUBMITTED' and budget['attempts'] == 2 and len(opened) == sessions
    budget = work_delivery.recover(root, P, {'action': 'recover', 'event_id': budget['id']}, human)['event']
    assert budget['state'] == 'UNCONFIRMED' and 'exhausted' in budget['reason'] and len(opened) == sessions and 'recovery' not in budget


# ---------------------------------------------------------------------------------------------- J-R5 cut-pinned pages

class _Gated(list):
    """A stub instruction list held at an owner barrier until the test releases it (deterministic ordering, no sleeps)."""
    def __init__(self, items, gate):
        super().__init__(items)
        self.gate = gate

    def __iter__(self):
        self.gate.wait(30)
        items = list(super().__iter__())
        self.clear()
        return iter(items)


def test_recovered_admission_before_terminal_and_repeated_concurrent_recovery_settle_one_result(harness, monkeypatch):
    """0864: an ordinary (non-Source, non-feedback) delivery whose ADMITTED retention was lost. Recovery publishes the SAME
    turn's ADMITTED while the reviewer is still held; the reviewer's own terminal hook then settles it; repeated and
    concurrent recovery converge on ONE RESULT for the same session and turn, never RESULT -> ADMITTED, no new turn."""
    root, parent_session, parent = harness
    human = {'origin': 'human'}
    handoff = _handoff(root, parent, 'handoff-dev-recover-1', _sha(BASE_A))
    binding = _bind(root)
    gate, opened = threading.Event(), []
    original = turn_admission.new_session

    def new_session(*args, **kwargs):
        session = original(*args, **kwargs)
        if kwargs.get('role') == 'review' or (len(args) > 5 and args[5] == 'review'):
            opened.append(session['id'])
            _StubTurn.instructions[session['id']] = _Gated([('work_delivery', {'action': 'status', 'work_id': 'dev'})], gate)
        return session
    monkeypatch.setattr(turn_admission, 'new_session', new_session)
    real_append = project_work._append

    def crash_after_admission(root_, row):
        if row.get('kind') == 'work-delivery' and row.get('state') == 'ADMITTED':
            raise RuntimeError('fixture: lost admission acknowledgement')
        return real_append(root_, row)
    monkeypatch.setattr(project_work, '_append', crash_after_admission)
    with pytest.raises(RuntimeError, match='lost admission acknowledgement'):
        _submit(root, handoff, binding['id'])
    monkeypatch.setattr(project_work, '_append', real_append)
    event_id = [row for row in _task(root)['deliveries'] if row.get('kind') == 'work-delivery' and row.get('recipient', {}).get('id') == binding['id']][-1]['id']
    turns = lambda: [t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == event_id]
    states = lambda: [row['state'] for row in work_delivery._history(_task(root), event_id)]
    [turn] = turns()
    first = work_delivery.recover(root, P, {'action': 'recover', 'event_id': event_id}, human)['event']
    assert first['state'] == 'ADMITTED' and first['admitted']['turn_id'] == turn['id'] and first['admitted']['recovered'] is True
    assert not (writing_records.fold_records(root)['turns'][turn['id']].get('reply') or {}).get('status')   # still held: nothing settled
    gate.set()
    _wait_done(turn['id'])
    assert (writing_records.fold_records(root)['turns'][turn['id']].get('reply') or {}).get('status')   # the exact saved terminal reply
    results = []
    workers = [threading.Thread(target=lambda: results.append(work_delivery.recover(root, P, {'action': 'recover', 'event_id': event_id}, human)['event']))
               for _ in range(3)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    assert len(results) == 3 and all(r['state'] == 'RESULT' and r['admitted']['turn_id'] == turn['id'] and r['admitted']['recipient_ack'] == 'TERMINAL'
                                     for r in results)
    history = states()
    assert history.count('RESULT') == 1 and history[-1] == 'RESULT' and history.count('ADMITTED') == 1
    assert history.index('ADMITTED') < history.index('RESULT') and len(turns()) == 1 and len(opened) == 1


def test_facet_pages_are_pinned_to_one_owner_cut_and_an_append_between_pages_restarts_the_series(harness):
    root, parent_session, parent = harness
    human = {'origin': 'human'}
    binding = _bind(root)
    for n in range(3):
        development_source.grant(root, P, _grant_payload(root, parent_session, binding['id'], request_id='grant-page-%d' % n), human)
    page1 = development_source.status(root, P, {'action': 'status', 'work_id': 'dev', 'limit': 2}, human)['development']
    ids1 = [row['id'] for row in page1['grants']['items']]
    nxt = page1['grants']['next_read']['payload']
    assert page1['grants']['total'] == 3 and len(ids1) == 2 and nxt['cut'] == page1['cut'] and nxt['offset'] == 2
    # an append between the pages: the old cut is refused with the exact restart; nothing is duplicated or skipped
    development_source.grant(root, P, _grant_payload(root, parent_session, binding['id'], request_id='grant-page-late'), human)
    with pytest.raises(project_work.WorkConflict) as refused:
        development_source.status(root, P, nxt, human)
    restart = refused.value.details['next_reads'][0]
    assert refused.value.details['field'] == 'cut' if 'field' in refused.value.details else True
    assert restart['operation'] == 'development_source' and 'cut' not in restart['payload'] and 'offset' not in restart['payload']
    fresh = development_source.status(root, P, restart['payload'], human)['development']
    ids_fresh = [row['id'] for row in fresh['grants']['items']]
    second = development_source.status(root, P, fresh['grants']['next_read']['payload'], human)['development']
    ids_second = [row['id'] for row in second['grants']['items']]
    assert fresh['grants']['total'] == 4 and len(set(ids_fresh) & set(ids_second)) == 0 and len(ids_fresh + ids_second) == 4
    assert second['grants']['next_read'] is None and second['cut'] == fresh['cut']
    # the canonical Work basis is part of the cut: a goal update invalidates an old page continuation, with no new row attached
    page_again = development_source.status(root, P, {'action': 'status', 'work_id': 'dev', 'limit': 2}, human)['development']
    project_work.task(P, {'id': 'dev', 'title': 'Answer 42', 'goal': 'The goal moved between pages', 'expected_work_revision': _guard(root)}, root)
    with pytest.raises(project_work.WorkConflict, match='changed between pages'):
        development_source.status(root, P, page_again['grants']['next_read']['payload'], human)
    assert development_source.status(root, P, {'action': 'status', 'work_id': 'dev', 'limit': 2}, human)['development']['cut'] != page_again['cut']
    # the delivery pages hold the same discipline, and their cut moves with the review standing the acceptance is read from
    handoff = _handoff(root, parent, 'handoff-page-1', _sha(BASE_A))
    for n in range(3):
        work_delivery.submit(root, P, _submit_payload(root, handoff, _bind(root, label='r%d' % n)['id']), human)
    page = work_delivery.status(root, P, {'action': 'status', 'work_id': 'dev', 'limit': 2}, human)['deliveries']
    assert page['events_total'] == 3 and page['next_read']['payload']['cut'] == page['cut']
    before = page['cut']
    _native(root, parent, 'work_review', {'id': 'dev', 'phase': 'review', 'request_id': 'review-page-1', 'expected_work_revision': _guard(root),
                                          'handoff_id': handoff, 'obligation_id': 'source', 'verdict': 'HOLD'})
    with pytest.raises(project_work.WorkConflict, match='changed between pages'):
        work_delivery.status(root, P, page['next_read']['payload'], human)
    moved = work_delivery.status(root, P, {'action': 'status', 'work_id': 'dev', 'limit': 2}, human)['deliveries']
    assert moved['cut'] != before and moved['events'][0]['acceptance']['status'] == 'HOLD'
    assert work_delivery.status(root, P, moved['next_read']['payload'], human)['deliveries']['events'][0]['id'] not in {e['id'] for e in moved['events']}
    project_work.task(P, {'id': 'dev', 'title': 'Answer 42', 'goal': 'The goal moved again between delivery pages', 'expected_work_revision': _guard(root)}, root)
    with pytest.raises(project_work.WorkConflict, match='changed between pages'):
        work_delivery.status(root, P, moved['next_read']['payload'], human)


# ---------------------------------------------------------------------------------------------- J-R4-R1-RETURN: Stop and the publication cut

def test_parent_return_honours_stop_and_recovers_the_same_admission_after_a_publication_cut(harness, monkeypatch):
    root, parent_session, parent = harness
    human = {'origin': 'human'}
    binding = _bind(root)
    grant = development_source.grant(root, P, _grant_payload(root, parent_session, binding['id']), human)['grant']
    opened = []
    _reviewer_instructions(monkeypatch, opened, [('work_delivery', {'action': 'status', 'work_id': 'dev'})], delay=3.0)
    # (a) Stop before the reviewer's result: the parent's turn submits with an approved route and keeps working (a sleeping
    #     check); the real Stop door interrupts it; the reviewer then ends; the return is REFUSED, never an automatic restart
    handoff = _handoff(root, parent, 'handoff-stop-1', _sha(BASE_A))
    _StubTurn.instructions[parent_session] = _Once([('work_delivery', _submit_payload(root, handoff, binding['id'], parent_return={'admit_idle': True, 'max_attempts': 1, 'max_depth': 1})),
                                                    ('development_source', {'action': 'check', 'grant_id': grant['id'], 'name': 'sleep'})])
    parent_turns_before = len(_turns_of(root, parent_session))
    started = turn_admission.start_turn(root, {'project': P, 'session_id': parent_session, 'mode': 'work', 'text': 'submit then keep working', 'request_id': 'parent-stop-1'})
    time.sleep(1.0)
    turn_control.interrupt_turn(root, {'turn_id': started['turn_id'], 'project': P})
    _wait_done(started['turn_id'])
    saved = writing_records.fold_records(root)['turns'][started['turn_id']]
    assert saved['reply']['status'] == 'interrupted', saved['reply']
    event_id = [r for r in _task(root)['deliveries'] if r.get('kind') == 'work-delivery'][-1]['id']
    assert len(opened) == 1
    _wait_turn(root, event_id)
    time.sleep(0.3)
    stopped = work_delivery.status(root, P, {'action': 'status', 'event_id': event_id}, human)['event']
    assert stopped['state'] == 'PARENT_REFUSED' and stopped['reason'].startswith('stopped:') and started['turn_id'] in stopped['reason']
    assert stopped['parent_return']['continuation_turn'] is None and 'recovery' not in stopped
    assert not [t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == 'CONT-' + event_id]
    again = work_delivery.recover(root, P, {'action': 'recover', 'event_id': event_id}, human)['event']
    assert again['state'] == 'PARENT_REFUSED' and again['reason'] == stopped['reason']
    assert len([r for r in _task(root)['deliveries'] if r.get('id') == event_id and r['state'] == 'PARENT_REFUSED']) == 1, 'the same refusal is not appended twice'
    assert len(_turns_of(root, parent_session)) == parent_turns_before + 1 and len(opened) == 1, (opened, [(k, v.get('role')) for k, v in writing_records.fold_records(root)['sessions'].items()])
    # (b) the admission is committed at the turn owner but the CONTINUED publication is cut: public recover of the SAME event
    #     finds that exact CONT request and publishes it; two concurrent recovers agree; no second session or turn
    handoff2 = _handoff(root, parent, 'handoff-cut-1', _sha(BASE_A), aggregate='sha256:' + '8' * 64)
    _run_turn(root, parent_session, [('work_delivery', _submit_payload(root, handoff2, binding['id'], parent_return={'admit_idle': True, 'max_attempts': 1, 'max_depth': 1}))],
              'submit and go idle', 'parent-cut-1')
    assert _StubTurn.observed[-1]['tool_failures'] == []
    event2 = [r for r in _task(root)['deliveries'] if r.get('kind') == 'work-delivery'][-1]['id']
    _StubTurn.instructions[parent_session] = _Once([])
    real_append = project_work._append
    cut_once = {'done': False}

    def cut_publication(root_, row):
        if row.get('kind') == 'work-delivery' and row.get('state') == 'CONTINUED' and not cut_once['done']:
            cut_once['done'] = True
            raise OSError('controlled CONTINUED publication failure')
        return real_append(root_, row)
    monkeypatch.setattr(project_work, '_append', cut_publication)
    reviewer2 = _wait_turn(root, event2)
    continuation = _wait_turn(root, 'CONT-' + event2)
    assert continuation['session_id'] == parent_session and cut_once['done']
    assert 'controlled CONTINUED publication failure' in (turn_jobs._JOBS[reviewer2['id']].get('delivery_settlement_error') or '')
    unpublished = work_delivery.status(root, P, {'action': 'status', 'event_id': event2}, human)['event']
    assert unpublished['state'] == 'RESULT' and unpublished['parent_return']['state'] is None and unpublished['recovery']['payload'] == {'action': 'recover', 'event_id': event2}
    monkeypatch.setattr(project_work, '_append', real_append)
    parent_turns_before = len(_turns_of(root, parent_session))
    results = {}
    first = threading.Thread(target=lambda: results.update(a=work_delivery.recover(root, P, {'action': 'recover', 'event_id': event2}, human)['event']))
    first.start()
    results['b'] = work_delivery.recover(root, P, {'action': 'recover', 'event_id': event2}, human)['event']
    first.join(30)
    for outcome in results.values():
        assert outcome['state'] == 'CONTINUED' and outcome['parent_return']['continuation_turn']['turn_id'] == continuation['id'] and 'recovery' not in outcome
        assert outcome['parent_return']['attempts'] == 1 and outcome['parent_return']['continuation_turn']['reused'] is True
    rows = [r for r in _task(root)['deliveries'] if r.get('id') == event2 and r['state'] == 'CONTINUED']
    assert len(rows) == 1 and rows[0]['recovered'] is True
    assert len(_turns_of(root, parent_session)) == parent_turns_before and len(opened) == 2
    assert len([t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == 'CONT-' + event2]) == 1


# ---------------------------------------------------------------------------------------------- Cae81: sender publication witness

def _gated_reviewer(monkeypatch, opened: list, gate) -> None:
    """The app-owned reviewer opens inside the delivery and is held at an owner barrier until the test releases it."""
    original = turn_admission.new_session

    def new_session(*args, **kwargs):
        session = original(*args, **kwargs)
        if kwargs.get('role') == 'review' or (len(args) > 5 and args[5] == 'review'):
            opened.append(session['id'])
            _StubTurn.instructions[session['id']] = _Gated([('work_delivery', {'action': 'status', 'work_id': 'dev'})], gate)
        return session
    monkeypatch.setattr(turn_admission, 'new_session', new_session)


def _idle_parent_submission(root: Path, parent_session: str, parent: str, binding: dict, request_id: str, aggregate: str):
    """The parent submits with an approved route and goes idle. Its later continuation turn runs no instructions."""
    handoff = _handoff(root, parent, 'handoff-' + request_id, _sha(BASE_A), aggregate=aggregate)
    submitted = _run_turn(root, parent_session, [('work_delivery', _submit_payload(root, handoff, binding['id'], parent_return={'admit_idle': True, 'max_attempts': 1, 'max_depth': 1}))],
                          'submit and go idle', request_id)
    assert _StubTurn.observed[-1]['tool_failures'] == []
    event_id = [r for r in _task(root)['deliveries'] if r.get('kind') == 'work-delivery'][-1]['id']
    reviewer = next(r for r in work_delivery._history(_task(root), event_id) if r['state'] == 'ADMITTED')['turn_id']
    _StubTurn.instructions[parent_session] = _Once([])
    return submitted, event_id, reviewer


def test_parent_return_publication_is_the_owner_append_not_the_continuation_turn_finishing(harness, monkeypatch):
    """Cae81: the sender is held at a barrier after its real CONT admission returns and before its real CONTINUED append (the
    window of the observed trace). That continuation turn is identified and finishes while the owner publication predicate
    stays false. Released, the same durable row appears once, for the same session, turn and request, through the automatic
    path (not recover), and a duplicate settlement adds nothing. A hold inside the append's own dispatch lock is a different
    boundary: it also blocks the continuation turn's completion, so it would not witness this order."""
    root, parent_session, parent = harness
    human = {'origin': 'human'}
    binding = _bind(root)
    gate, opened = threading.Event(), []
    _gated_reviewer(monkeypatch, opened, gate)
    real_start, real_append = turn_admission.start_turn, project_work._append
    held, release, appended = threading.Event(), threading.Event(), []

    def admit_then_hold(root_, request, *args, **kwargs):
        admitted = real_start(root_, request, *args, **kwargs)
        if str(request.get('request_id') or '').startswith('CONT-') and not held.is_set():
            held.set()   # the CONT turn is admitted and running; the sender has not yet appended CONTINUED
            assert release.wait(30), 'fixture: the held sender was never released'
        return admitted

    def witness_append(root_, row):
        value = real_append(root_, row)
        if row.get('kind') == 'work-delivery' and row.get('state') == 'CONTINUED':
            appended.append(row['id'])
        return value
    monkeypatch.setattr(turn_admission, 'start_turn', admit_then_hold)
    monkeypatch.setattr(project_work, '_append', witness_append)
    try:
        submitted, event_id, reviewer = _idle_parent_submission(root, parent_session, parent, binding, 'parent-held-1', 'sha256:' + 'a' * 64)
        gate.set()   # the reviewer ends now, with its submitting parent already idle
        assert held.wait(30), 'the delivery owner never admitted the CONT request'
        continuation = _wait_turn(root, 'CONT-' + event_id)   # identified and finished while the real append is still held
        assert continuation['session_id'] == parent_session and turn_jobs._JOBS[continuation['id']].get('done')
        assert _publication(root, event_id) is None and not appended
        assert [row['state'] for row in work_delivery._history(_task(root), event_id)][-1] == 'RESULT'
    finally:
        release.set()
    row = _wait_published(root, event_id, continuation['id'], parent_turn_id=submitted['turn_id'], reviewer_turn_id=reviewer)
    assert appended == [event_id] and not row.get('recovered')
    assert (row['continuation_turn']['session_id'], row['continuation_turn']['request_id']) == (parent_session, 'CONT-' + event_id)
    _wait_done(reviewer)
    history = [r['state'] for r in work_delivery._history(_task(root), event_id)]
    assert history[-2:] == ['RESULT', 'CONTINUED'] and history.count('RESULT') == 1 and history.count('CONTINUED') == 1, history
    event = work_delivery.status(root, P, {'action': 'status', 'event_id': event_id}, human)['event']
    assert event['state'] == 'CONTINUED' and event['parent_return']['continuation_turn']['turn_id'] == continuation['id'] and 'recovery' not in event
    assert work_delivery.settle_turn(root, P, event['admitted']['session_id'], event['admitted']['turn_id'], {'status': 'completed'}) == []
    assert [r['state'] for r in work_delivery._history(_task(root), event_id)] == history and len(opened) == 1
    assert len([t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == 'CONT-' + event_id]) == 1


def test_a_missing_parent_return_publication_fails_the_bounded_wait_with_exact_owner_and_callback_diagnostics(harness, monkeypatch):
    """Cae81 negative: the CONT turn exists and finishes but its CONTINUED publication fails. The bounded wait must not pass on
    the turn alone. It fails within its stated bound, names the exact event, request, turn, last durable owner state and the
    retained callback error, and writes nothing (no recover)."""
    root, parent_session, parent = harness
    human = {'origin': 'human'}
    binding = _bind(root)
    gate, opened = threading.Event(), []
    _gated_reviewer(monkeypatch, opened, gate)
    real_append = project_work._append
    dropped = []

    def drop_continued(root_, row):
        if row.get('kind') == 'work-delivery' and row.get('state') == 'CONTINUED':
            dropped.append(row['id'])
            raise OSError('controlled missing CONTINUED publication')
        return real_append(root_, row)
    monkeypatch.setattr(project_work, '_append', drop_continued)
    submitted, event_id, reviewer = _idle_parent_submission(root, parent_session, parent, binding, 'parent-missing-1', 'sha256:' + 'b' * 64)
    gate.set()
    continuation = _wait_turn(root, 'CONT-' + event_id)
    _wait_done(reviewer)
    rows = len(_task(root)['deliveries'])
    started = time.perf_counter()
    with pytest.raises(AssertionError) as missing:
        _wait_published(root, event_id, continuation['id'], parent_turn_id=submitted['turn_id'], reviewer_turn_id=reviewer, timeout=2.0)
    assert time.perf_counter() - started < 10.0
    text = str(missing.value)
    assert 'CONT-' + event_id in text and continuation['id'] in text and 'last RESULT' in text, text
    assert 'controlled missing CONTINUED publication' in text and "'parent'" in text and "'reviewer'" in text, text
    assert dropped == [event_id] and len(_task(root)['deliveries']) == rows and _publication(root, event_id) is None
    monkeypatch.setattr(project_work, '_append', real_append)
    unpublished = work_delivery.status(root, P, {'action': 'status', 'event_id': event_id}, human)['event']
    assert unpublished['state'] == 'RESULT' and unpublished['parent_return']['state'] is None
    assert unpublished['recovery']['payload'] == {'action': 'recover', 'event_id': event_id}
    assert len([t for t in writing_records.fold_records(root)['turns'].values() if t.get('request_id') == 'CONT-' + event_id]) == 1 and len(opened) == 1
