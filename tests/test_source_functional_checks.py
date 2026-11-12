"""Source check owner: admitted read-only dependencies and the registered runtime (Root aef8df7c).

Public, no-provider owner controls over the existing development_source check: a real bubblewrap sandbox run imports an
admitted read-only helper with the serving root's registered interpreter; tampered, missing, symlinked, undeclared and
escaping inputs, an unregistered or drifted runtime and Source apply to a dependency all refuse; legacy /usr profiles keep
their shape; a deadline kills and cleans up. Positive runs need the host sandbox and skip ONLY when the owner itself
reports it unavailable. This is not Root's later ordinary app Source workflow acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from laplace.work import development_source as D, project_work as W
from test_source_use_joins import source  # noqa: F401  (the public Source fixture)

HUMAN = {'origin': 'human'}
HELPER = 'def answer():\n    return 42\n'
FUNCTIONAL = '''import json, os, platform, sys
sys.path.insert(0, "support")
import helper_lib
out = {"helper": helper_lib.answer(), "version": platform.python_version(), "executable": os.path.realpath(sys.executable)}
for label, path in (("dependency", "support/helper_lib.py"), ("input", "src/functional_check.py"),
                    ("runtime", os.path.join(sys.prefix, "laplace-check-probe"))):
    try:
        with open(path, "a") as handle:
            handle.write("x")
        out[label] = "writable"
    except OSError:
        out[label] = "refused"
with open(os.path.join(os.environ["LAPLACE_CHECK_OUTPUT"], "scratch.txt"), "w") as handle:
    handle.write("ok")
out["scratch"] = "writable"
print(json.dumps(out, sort_keys=True))
'''
SLEEPER = 'import time\ntime.sleep(60)\n'


def register_runtime(root, *, python=None, expected=None):
    """The existing laplace.core.runtime declaration of the serving root (never LAPLACE_PYTHON or a caller path)."""
    (root / 'runtime_profiles.toml').write_text('[lifecycle]\npython = %s\nexpected_python = %s\n' % (
        json.dumps(str(Path(python or sys.executable).resolve())), json.dumps(expected or platform.python_version())))


def functional(s, *, request='public-functional-1', script=FUNCTIONAL, dependencies=None, timeout_s=60, **over):
    checkout = s['checkout']
    (checkout / 'support').mkdir(exist_ok=True)
    helper = checkout / 'support/helper_lib.py'
    if not helper.exists() and not helper.is_symlink():
        helper.write_text(HELPER)
    (checkout / 'src/functional_check.py').write_text(script)
    register_runtime(s['root'])
    profile = {'executable': 'python', 'runtime': 'registered-python', 'args': ['-I', 'src/functional_check.py'],
               'inputs': ['src/functional_check.py'], 'timeout_s': timeout_s,
               'dependencies': {'support/helper_lib.py': D._pin(helper)} if dependencies is None else dependencies, **over}
    if not profile['dependencies']:
        del profile['dependencies']
    payload = copy.deepcopy(s['payload'])
    payload.update(request_id=request, expected_work_revision=W._task_revision(W._tasks('public', s['root'])['work']),
                   checks={'functional': profile})
    return D.grant(s['root'], 'public', payload, HUMAN)['grant'], payload


def sandbox_or_skip(root):
    launcher = D.isolation_launcher()
    reason = D.enforcement_available(launcher) or D.mount_policy_problem(root, launcher)
    if reason:
        pytest.skip('the owner reports the host sandbox unavailable: ' + reason)


def no_launch(monkeypatch):
    monkeypatch.setattr(D, 'enforcement_available', lambda *_: None)
    monkeypatch.setattr(D, 'mount_policy_problem', lambda *_: None)
    monkeypatch.setattr(D.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('the profile must not launch'))


def test_registered_runtime_imports_an_admitted_readonly_helper_in_the_real_sandbox(source):
    s = source
    grant, payload = functional(s)
    row = grant['checks']['functional']
    admission = row['runtime_admission']
    assert row['runtime'] == 'registered-python' and admission['executable'] == str(Path(sys.executable).resolve())
    assert admission['declaration'] == 'runtime_profiles.toml#lifecycle.python' and admission['identity'].startswith('sha256:')
    assert row['dependencies'] == {'support/helper_lib.py': D._pin(s['checkout'] / 'support/helper_lib.py')}
    assert 'support/helper_lib.py' not in grant['paths'] and D.grant(s['root'], 'public', payload, HUMAN)['reused']
    sandbox_or_skip(s['root'])
    result = D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional'}, HUMAN)
    check = result['check']
    assert result['ok'] and check['state'] == 'COMPLETE', check
    observed = json.loads(check['stdout_tail'].strip().splitlines()[-1])
    assert observed == {'helper': 42, 'version': platform.python_version(), 'executable': admission['executable'],
                        'dependency': 'refused', 'input': 'refused', 'runtime': 'refused', 'scratch': 'writable'}
    assert check['runtime']['identity'] == admission['identity'] and check['runtime']['kind'] == 'registered-python'
    assert check['dependencies'] == [{'path': 'support/helper_lib.py', 'sha256': row['dependencies']['support/helper_lib.py'],
                                      'role': 'read-only-dependency'}]
    assert (s['checkout'] / 'support/helper_lib.py').read_text() == HELPER
    assert not (Path(check['output_root']) / 'input').exists()   # staged code and dependencies cleaned up


def test_undeclared_helper_fails_inside_the_sandbox_and_is_never_skipped(source):
    s = source
    grant, _payload = functional(s, request='public-functional-undeclared', dependencies={})
    assert 'dependencies' not in grant['checks']['functional']
    sandbox_or_skip(s['root'])
    check = D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional'}, HUMAN)['check']
    assert check['state'] == 'FAILED' and check['exit_code'] != 0 and 'helper_lib' in check['stdout_tail']
    assert not check.get('dependencies')


@pytest.mark.parametrize('case', ['tampered', 'missing', 'symlink'])
def test_changed_missing_or_symlinked_dependency_refuses_before_launch(source, monkeypatch, case):
    s = source
    grant, _payload = functional(s, request='public-functional-' + case)
    helper = s['checkout'] / 'support/helper_lib.py'
    if case == 'tampered':
        helper.write_text('def answer():\n    return 41\n')
    if case == 'missing':
        helper.unlink()
    if case == 'symlink':
        real = s['checkout'] / 'support/real_helper.py'
        real.write_text(HELPER)
        helper.unlink()
        helper.symlink_to(real)
    no_launch(monkeypatch)
    check = D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional'}, HUMAN)['check']
    assert check['state'] == 'REFUSED' and 'read-only check dependency refused' in check['reason'] and 'Nothing ran' in check['reason']
    assert not (Path(check['output_root']) / 'input').exists()


def test_grant_refuses_unregistered_runtime_host_paths_and_escaping_or_writable_dependencies(source):
    s = source
    functional(s, request='public-functional-baseline')
    ledger = W._ledger(s['root']).read_bytes()
    helper = s['checkout'] / 'support/helper_lib.py'
    (s['checkout'] / 'support/linked.py').symlink_to(helper)
    pin = D._pin(helper)
    cases = [
        {'executable': '/usr/bin/python3'},                                     # a host path is never registered-runtime authority
        {'runtime': 'system', 'executable': str(Path(sys.executable).resolve()) if not str(Path(sys.executable).resolve()).startswith('/usr/') else '/opt/absent/python3'},
        {'dependencies': {'../escape.py': pin}},
        {'dependencies': {'src/answer.py': D._pin(s['checkout'] / 'src/answer.py')}},   # a writable grant path
        {'dependencies': {'support/helper_lib.py': 'sha256:' + '0' * 64}},
        {'dependencies': {'support/linked.py': pin}},
        {'dependencies': {'.git/config': pin}},
    ]
    for index, over in enumerate(cases):
        with pytest.raises(ValueError):
            functional(s, request='public-functional-bad-%d' % index, **over)
        assert W._ledger(s['root']).read_bytes() == ledger, over
    (s['root'] / 'runtime_profiles.toml').unlink()
    payload = copy.deepcopy(s['payload'])
    payload.update(request_id='public-functional-unregistered', expected_work_revision=W._task_revision(W._tasks('public', s['root'])['work']),
                   checks={'functional': {'executable': 'python', 'runtime': 'registered-python', 'args': ['-I', 'src/functional_check.py'],
                                          'inputs': ['src/functional_check.py']}})
    with pytest.raises(ValueError, match='no registered runtime'):
        D.grant(s['root'], 'public', payload, HUMAN)
    assert W._ledger(s['root']).read_bytes() == ledger


def test_registered_runtime_drift_refuses_before_launch(source, monkeypatch):
    s = source
    grant, _payload = functional(s, request='public-functional-drift')
    register_runtime(s['root'], expected='0.0.0')
    no_launch(monkeypatch)
    check = D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional'}, HUMAN)['check']
    assert check['state'] == 'REFUSED' and 'registered runtime changed since the grant' in check['reason']


def test_source_apply_and_read_of_a_readonly_dependency_still_refuse(source):
    s = source
    grant, _payload = functional(s, request='public-functional-apply')
    helper = s['checkout'] / 'support/helper_lib.py'
    with pytest.raises(ValueError, match='outside the grant'):
        D.candidate(s['root'], 'public', {'grant_id': grant['id'], 'files': [
            {'path': 'support/helper_lib.py', 'before_sha256': D._pin(helper), 'content': 'def answer():\n    return 0\n'}]}, s['door'])
    with pytest.raises(ValueError, match='outside the grant'):
        D.read(s['root'], 'public', {'grant_id': grant['id'], 'path': 'support/helper_lib.py'}, s['door'])
    assert helper.read_text() == HELPER


def test_legacy_system_profiles_keep_shape_identity_and_argv(source):
    s = source
    legacy = s['grant']['checks']['bounded']
    assert not {'runtime', 'runtime_admission', 'dependencies'} & set(legacy)
    assert D.grant(s['root'], 'public', s['payload'], HUMAN)['reused']
    argv = D._isolation_argv(Path('/usr/bin/bwrap'), Path('/stage'), legacy)
    assert argv[-3:] == ['/usr/bin/python3', '-I', 'evaluator.py'] and argv[argv.index('PATH') + 1] == '/usr/bin'
    runtime = {'prefix': '/opt/registered/python', 'executable': '/opt/registered/python/bin/python3.14'}
    registered = D._isolation_argv(Path('/usr/bin/bwrap'), Path('/stage'), {**legacy, 'executable': 'python'}, runtime)
    bind = registered.index('/opt/registered/python')
    assert registered[bind - 1] == '--ro-bind' and registered[bind + 1] == '/opt/registered/python'
    assert registered[registered.index('PATH') + 1] == '/opt/registered/python/bin:/usr/bin'
    assert registered[-3] == runtime['executable'] and '--bind' not in registered
    from jsonschema import Draft202012Validator
    profile = {'executable': 'python', 'runtime': 'registered-python', 'args': [], 'inputs': ['src/*.py'],
               'dependencies': {'support/helper_lib.py': 'sha256:' + 'a' * 64}}
    validator = Draft202012Validator(D.contract())
    assert not list(validator.iter_errors({'action': 'grant', 'checks': {'x': profile}}))
    assert list(validator.iter_errors({'action': 'grant', 'checks': {'x': {**profile, 'runtime': 'home-python'}}}))
    assert list(validator.iter_errors({'action': 'grant', 'checks': {'x': {**profile, 'dependencies': {'a.py': 'bad'}}}}))


def test_deadline_kills_and_cleans_a_registered_runtime_check(source):
    s = source
    grant, _payload = functional(s, request='public-functional-deadline', script=SLEEPER, dependencies={}, timeout_s=2)
    sandbox_or_skip(s['root'])
    check = D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional'}, HUMAN)['check']
    assert check['state'] == 'TIMEOUT' and check['wall_ms'] < 20000
    assert not (Path(check['output_root']) / 'input').exists()


SENTINEL = 'NEUTRAL = "pinned neutral input sentinel"\n'
NEUTRAL = '''import json, os
out = {"cwd": os.getcwd(), "relative": open("src/sentinel_input.py").read(), "absolute": open("/input/src/sentinel_input.py").read(),
       "scratch": os.environ["LAPLACE_CHECK_OUTPUT"], "home": os.environ["HOME"]}
for label, path in (("new_relative", "x"), ("new_absolute", "/input/y"), ("existing", "src/sentinel_input.py")):
    try:
        with open(path, "a") as handle:
            handle.write("x")
        out[label] = "writable"
    except OSError as exc:
        out[label] = "errno%%d" %% exc.errno
for label, path in (("mkdir_relative", "made.d"), ("mkdir_absolute", "/input/made2.d")):
    try:
        os.mkdir(path)
        out[label] = "made"
    except OSError as exc:
        out[label] = "errno%%d" %% exc.errno
out["former_root"] = os.path.lexists(%(root)r)
out["former_checks"] = os.path.lexists(%(checks)r)
print(json.dumps(out, sort_keys=True))
'''


def test_neutral_input_namespace_reads_pinned_inputs_at_input_cwd_and_hides_the_host_stage(source):
    """Root neutral-stage cause (DK-7bf59081): a Main-owned check bound its exact host stage at the same absolute path, which
    the runtime fixture's Main protection refuses. The owner now binds the verified host stage read-only at the fixed
    neutral /input and runs there: a pinned sentinel input is readable relative and absolute, writes and mkdir there refuse,
    the former host root and stage are absent inside the sandbox, scratch/HOME stay /tmp, and host custody is unchanged."""
    s = source
    root = Path(s['root']).resolve()
    checks = (root / 'contract' / 'development_checks').resolve()
    (s['checkout'] / 'src/sentinel_input.py').write_text(SENTINEL)
    script = NEUTRAL % {'root': str(root), 'checks': str(checks)}
    grant, _payload = functional(s, request='public-functional-neutral', script=script, dependencies={},
                                 inputs=['src/functional_check.py', 'src/sentinel_input.py'])
    sandbox_or_skip(s['root'])
    result = D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional'}, HUMAN)
    check = result['check']
    assert result['ok'] and check['state'] == 'COMPLETE', check
    observed = json.loads(check['stdout_tail'].strip().splitlines()[-1])
    assert observed['cwd'] == '/input' and observed['relative'] == SENTINEL and observed['absolute'] == SENTINEL, observed
    assert all(observed[key].startswith('errno') for key in ('new_relative', 'new_absolute', 'existing', 'mkdir_relative', 'mkdir_absolute')), observed
    assert observed['former_root'] is False and observed['former_checks'] is False, observed   # the old host path is not in the namespace
    assert observed['scratch'] == '/tmp' and observed['home'] == '/tmp'
    pins = {item['path']: item['sha256'] for item in check['inputs']}
    assert pins['src/sentinel_input.py'] == D._pin(s['checkout'] / 'src/sentinel_input.py')
    output = Path(check['output_root'])
    assert output.parent == checks and (output / 'stdout.txt').read_bytes().decode() == check['stdout_tail']   # host custody unchanged
    mount = check['isolation']['input_mount']
    assert mount['sandbox_path'] == '/input' and mount['cwd'] == '/input' and mount['host_stage'] == str(output / 'input')
    assert any(entry.startswith('/input') for entry in check['isolation']['read_only']) and check['stage_cleanup']['state'] == 'REMOVED'
    assert not (output / 'input').exists() and (s['checkout'] / 'src/sentinel_input.py').read_text() == SENTINEL


def test_a_main_shaped_host_stage_is_bound_only_at_the_neutral_input_with_unchanged_argv():
    """Argv composition for both legacy and registered profiles: a Main-shaped host stage appears ONLY as the read-only bind
    source; destination and working directory are the fixed neutral /input; the opaque caller argv, the executable, the
    environment and the budgets are unchanged and no host directory is writable."""
    stage = Path('/home/author/laplace/main/contract/development_checks/DK-0123456789abcdef01234567/input')
    legacy = {'executable': '/usr/bin/python3', 'args': ['-I', 'evaluator.py', '--opaque=/abs/kept'], 'scratch_bytes': 8 * D.SCRATCH_PAGE,
              'timeout_s': 30, 'memory_bytes': 256 * 1024 ** 2, 'max_processes': 4}
    runtime = {'prefix': '/opt/registered/python', 'executable': '/opt/registered/python/bin/python3.14'}
    for argv, executable in ((D._isolation_argv(Path('/usr/bin/bwrap'), stage, legacy), '/usr/bin/python3'),
                             (D._isolation_argv(Path('/usr/bin/bwrap'), stage, {**legacy, 'executable': 'python'}, runtime), runtime['executable'])):
        assert argv.count(str(stage)) == 1, argv
        at = argv.index(str(stage))
        assert argv[at - 1] == '--ro-bind' and argv[at + 1] == '/input'
        assert argv[argv.index('--chdir') + 1] == '/input' and argv.count('--chdir') == 1
        assert argv[-4:] == [executable, '-I', 'evaluator.py', '--opaque=/abs/kept'] and '--bind' not in argv
        assert argv[argv.index('HOME') + 1] == '/tmp' and argv[argv.index('LAPLACE_CHECK_OUTPUT') + 1] == '/tmp'
        assert argv[argv.index('--tmpfs', argv.index('--size')) + 1] == '/tmp' and argv.index('/input') > argv.index('--size')


def test_the_policy_probe_refuses_the_former_host_stage_bind(source, monkeypatch):
    """The existing real policy probe shares the check's argv composition and verifies the neutral namespace: the old
    same-path stage bind (the failing oracle) is reported as not enforced, with its cwd and the present former stage."""
    s = source
    sandbox_or_skip(s['root'])
    real = D._isolation_argv

    def former(launcher, stage, profile, runtime=None):
        argv = real(launcher, stage, profile, runtime)
        argv[argv.index('/input')] = str(stage)
        argv[argv.index('--chdir') + 1] = str(stage)
        return argv
    monkeypatch.setattr(D, '_POLICY_VERIFIED', {})
    monkeypatch.setattr(D, '_isolation_argv', former)
    problem = D.mount_policy_problem(s['root'], D.isolation_launcher())
    assert problem and 'not enforced' in problem and '"former_stage": "present"' in problem and '"cwd"' in problem, problem
    monkeypatch.setattr(D, '_isolation_argv', real)
    monkeypatch.setattr(D, '_POLICY_VERIFIED', {})
    assert D.mount_policy_problem(s['root'], D.isolation_launcher()) is None
    assert not (Path(s['root']) / 'contract' / 'development_checks' / '.policy-probe' / str(os.getpid())).exists()


def test_a_failed_policy_sentinel_write_is_typed_unavailable_launches_nothing_and_removes_the_probe_stage(source, monkeypatch):
    """Root sentinel-cleanup correction: the probe's fallible sentinel preparation is inside the existing exception/finally
    boundary. An actual OSError writing it yields the typed 'could not be verified' refusal (check UNAVAILABLE, nothing ran),
    launches no subprocess, caches nothing and leaves no host probe stage."""
    s = source
    grant, _payload = functional(s, request='public-functional-sentinel-oserror')
    sandbox_or_skip(s['root'])
    probe = (Path(s['root']) / 'contract' / 'development_checks' / '.policy-probe' / str(os.getpid())).resolve()
    real_write = Path.write_text

    def failing(self, *args, **kwargs):
        if self.name == D.POLICY_SENTINEL_NAME:
            raise OSError(28, 'forced sentinel write failure')
        return real_write(self, *args, **kwargs)
    launches = []
    monkeypatch.setattr(Path, 'write_text', failing)
    monkeypatch.setattr(D.subprocess, 'run', lambda *a, **k: launches.append(a) or pytest.fail('the probe must not launch'))
    monkeypatch.setattr(D.subprocess, 'Popen', lambda *a, **k: launches.append(a) or pytest.fail('the profile must not launch'))
    monkeypatch.setattr(D, '_POLICY_VERIFIED', {})
    problem = D.mount_policy_problem(s['root'], D.isolation_launcher())
    assert problem and 'could not be verified' in problem and 'forced sentinel write failure' in problem, problem
    assert launches == [] and not probe.exists() and D._POLICY_VERIFIED == {}
    check = D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional'}, HUMAN)['check']
    assert check['state'] == 'UNAVAILABLE' and 'forced sentinel write failure' in check['reason'] and check.get('exit_code') is None, check
    assert launches == [] and not probe.exists() and check['stage_cleanup']['state'] in ('REMOVED', 'ABSENT')
    assert not (Path(check['output_root']) / 'input').exists()


def test_review_preflight_is_bounded_and_offers_but_never_observes_context(source):
    """Root review-preflight need: the owner reports which inputs lack selected context or leave changed spans uncovered,
    without bodies, and offers a bounded scaffold (changed spans + head windows) that is explicitly not a read."""
    s = source
    changed = D.candidate(s['root'], 'public', {'grant_id': s['grant']['id'], 'files': [{'path': 'src/answer.py',
        'before_sha256': D._pin(s['checkout'] / 'src/answer.py'), 'edits': [{'old': 'unique old', 'new': 'new chosen'}]}]}, s['door'])
    D.apply(s['root'], 'public', {'candidate_id': changed['candidate_id']}, s['door'])
    request = {'work_id': 'work', 'grant_id': s['grant']['id'], 'candidate_id': changed['candidate_id'],
               'paths': ['src/answer.py', 'evaluator.py', 'guide.md']}
    bare = D.review_preflight(s['root'], 'public', request, s['door'])
    assert bare['schema_version'] == D.REVIEW_PREFLIGHT_SCHEMA and bare['state'] == 'INCOMPLETE'
    assert set(bare['incomplete']) == {'src/answer.py', 'evaluator.py', 'guide.md'}
    rows = {row['path']: row for row in bare['inputs']}
    assert rows['src/answer.py']['changed'] and 'NO_SELECTED_CONTEXT' in rows['guide.md']['reasons']
    assert 'text' not in json.dumps(bare['inputs'])   # bounded: no bodies or reads
    scaffold = bare['scaffold']
    assert scaffold['offered_not_observed'] and scaffold['within_bound'] and {w['path'] for w in scaffold['windows']} == set(request['paths'])
    offered = D.review_preflight(s['root'], 'public', {**request, 'source_context': {'windows': scaffold['windows']}}, s['door'])
    assert offered['state'] == 'COMPLETE' and not offered['incomplete']
    with pytest.raises(ValueError):
        D.review_preflight(s['root'], 'public', {**request, 'paths': ['src/absent.py']}, s['door'])
    assert D.handle(s['root'], 'public', {'action': 'review-preflight', **request}, s['door'])['state'] == 'INCOMPLETE'


def manifest_of(checkout, *paths):
    return {'schema': D.DEPENDENCY_MANIFEST_SCHEMA, 'members': [{'path': p, 'sha256': D._pin(checkout / p)} for p in paths]}


def test_pinned_dependency_manifest_beyond_the_inline_map_is_validated_once_and_staged_readonly(source):
    """Root closure decision: a pinned manifest (here 80 members, beyond the 64-entry inline convenience map) is resolved
    once at grant, recorded immutably with digest, member count and bytes, and staged member by member read-only."""
    s = source
    checkout = s['checkout']
    (checkout / 'support').mkdir(exist_ok=True)
    names = ['support/mod_%03d.py' % i for i in range(80)]
    for name in names:
        (checkout / name).write_text('VALUE = %r\n' % name)
    grant, _payload = functional(s, request='public-functional-manifest', dependencies={}, dependency_manifest=manifest_of(checkout, *names))
    recorded = grant['checks']['functional']['dependency_manifest']
    assert recorded['members_total'] == 80 and recorded['source'] == 'inline' and recorded['digest'].startswith('sha256:')
    assert recorded['bytes_total'] == sum((checkout / n).stat().st_size for n in names)
    stage = s['root'] / 'stage-probe'
    stage.mkdir()
    _task, row = D._find_grant(s['root'], 'public', grant['id'])
    pins, problems = D._stage_dependencies(s['root'], checkout, row, row['checks']['functional'], stage)
    assert not problems and len(pins) == 80 and {p['role'] for p in pins} == {'manifest-member'}
    assert all(oct((stage / n).stat().st_mode)[-3:] == '444' for n in names)


@pytest.mark.parametrize('case', ['tampered', 'missing', 'writable', 'escape', 'duplicate', 'conflict', 'bad-schema'])
def test_dependency_manifest_refuses_bad_members_at_grant_and_records_nothing(source, case):
    s = source
    checkout = s['checkout']
    (checkout / 'support').mkdir(exist_ok=True)
    (checkout / 'support/a.py').write_text('A = 1\n')
    manifest = manifest_of(checkout, 'support/a.py')
    deps = None
    if case == 'tampered':
        manifest['members'][0]['sha256'] = 'sha256:' + '0' * 64
    if case == 'missing':
        manifest['members'].append({'path': 'support/absent.py', 'sha256': 'sha256:' + '1' * 64})
    if case == 'writable':
        manifest['members'].append({'path': 'src/answer.py', 'sha256': D._pin(checkout / 'src/answer.py')})
    if case == 'escape':
        manifest['members'].append({'path': '../outside.py', 'sha256': 'sha256:' + '1' * 64})
    if case == 'duplicate':
        manifest['members'].append(dict(manifest['members'][0]))
    if case == 'conflict':
        (checkout / 'support/helper_lib.py').write_text(HELPER)
        manifest['members'].append({'path': 'support/helper_lib.py', 'sha256': 'sha256:' + '2' * 64})
    if case == 'bad-schema':
        manifest['schema'] = 'laplace.unknown/1'
    functional(s, request='public-functional-manifest-baseline-' + case)
    ledger = W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError):
        functional(s, request='public-functional-manifest-' + case, dependencies=deps, dependency_manifest=manifest)
    assert W._ledger(s['root']).read_bytes() == ledger


def test_dependency_manifest_bounds_and_check_time_tamper_refuse_before_launch(source, monkeypatch):
    s = source
    checkout = s['checkout']
    (checkout / 'support').mkdir(exist_ok=True)
    for name in ('support/a.py', 'support/b.py', 'support/c.py'):
        (checkout / name).write_text('X = 1\n')
    manifest = manifest_of(checkout, 'support/a.py', 'support/b.py', 'support/c.py')
    monkeypatch.setattr(D, 'MAX_DEPENDENCY_MANIFEST_MEMBERS', 2)
    with pytest.raises(ValueError, match='above the bound'):
        functional(s, request='public-functional-manifest-count', dependencies={}, dependency_manifest=manifest)
    monkeypatch.setattr(D, 'MAX_DEPENDENCY_MANIFEST_MEMBERS', 4096)
    monkeypatch.setattr(D, 'MAX_DEPENDENCY_CLOSURE_BYTES', 4)
    with pytest.raises(ValueError, match='bytes, above the bound'):
        functional(s, request='public-functional-manifest-bytes', dependencies={}, dependency_manifest=manifest)
    monkeypatch.setattr(D, 'MAX_DEPENDENCY_CLOSURE_BYTES', 256 * 1024 ** 2)
    grant, _payload = functional(s, request='public-functional-manifest-tamper', dependencies={}, dependency_manifest=manifest)
    (checkout / 'support/b.py').write_text('X = 2\n')
    no_launch(monkeypatch)
    check = D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional'}, HUMAN)['check']
    assert check['state'] == 'REFUSED' and 'support/b.py' in check['reason'] and 'Nothing ran' in check['reason']
    assert check['dependency_closure']['coverage'] == 'INCOMPLETE' and check['dependency_closure']['problems_total'] == 1


def test_dependency_manifest_from_a_pinned_project_artifact_and_a_wrong_pin_refuses(source):
    from laplace.projects import artifacts
    s = source
    checkout = s['checkout']
    (checkout / 'support').mkdir(exist_ok=True)
    (checkout / 'support/helper_lib.py').write_text(HELPER)
    body = json.dumps(manifest_of(checkout, 'support/helper_lib.py'))
    stored = artifacts.store(s['root'], 'public', {'path': 'closures/functional.json', 'before': None, 'content': body,
                                                   'reason': 'Public closure manifest fixture.'}, 'WT-parent')
    ident = stored.get('id') or stored.get('record_id')
    digest = 'sha256:' + hashlib.sha256(body.encode()).hexdigest()
    grant, _payload = functional(s, request='public-functional-manifest-artifact', dependencies={},
                                 dependency_manifest={'artifact_id': ident, 'expected_sha256': digest})
    recorded = grant['checks']['functional']['dependency_manifest']
    assert recorded['source'] == 'artifact:%s@%s' % (ident, digest) and recorded['members_total'] == 1
    with pytest.raises(ValueError, match='stated bytes'):
        functional(s, request='public-functional-manifest-artifact-bad', dependencies={},
                   dependency_manifest={'artifact_id': ident, 'expected_sha256': 'sha256:' + '0' * 64})


def test_manifest_closure_imports_the_helper_in_the_real_sandbox_with_reported_coverage(source):
    s = source
    checkout = s['checkout']
    (checkout / 'support').mkdir(exist_ok=True)
    (checkout / 'support/helper_lib.py').write_text(HELPER)
    grant, _payload = functional(s, request='public-functional-manifest-sandbox', dependencies={},
                                 dependency_manifest=manifest_of(checkout, 'support/helper_lib.py'))
    sandbox_or_skip(s['root'])
    check = D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional'}, HUMAN)['check']
    assert check['state'] == 'COMPLETE', check
    observed = json.loads(check['stdout_tail'].strip().splitlines()[-1])
    assert observed['helper'] == 42 and observed['dependency'] == 'refused'
    closure = check['dependency_closure']
    assert closure['coverage'] == 'COMPLETE' and closure['staged_members'] == closure['members_total'] == 1
    assert closure['digest'] == grant['checks']['functional']['dependency_manifest']['digest'] and not check.get('dependencies')
    assert not (Path(check['output_root']) / 'input').exists()
    assert check['stage_cleanup']['state'] == 'REMOVED' and 'process group is empty' in check['stage_cleanup']['proof']


# ---------------------------------------------------------------- staging cleanup on every terminal path (Root seq 8)

def fake_launch(monkeypatch, code):
    """No host sandbox needed: the owner's own Popen/registration/settle path runs a plain interpreter child."""
    monkeypatch.setattr(D, 'enforcement_available', lambda *_: None)
    monkeypatch.setattr(D, 'mount_policy_problem', lambda *_: None)
    monkeypatch.setattr(D, '_isolation_argv', lambda *_a, **_k: [sys.executable, '-I', '-c', code])


def check_row(s, ident):
    return [row for row in D.rows(W._tasks('public', s['root'])['work'], 'check') if row['id'] == ident][-1]


def run_check(s, grant, **extra):
    return D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': 'functional', **extra}, HUMAN)['check']


def test_early_unavailable_removes_the_stage_and_records_the_outcome(source, monkeypatch):
    s = source
    grant, _payload = functional(s, request='public-functional-cleanup-unavailable')
    monkeypatch.setattr(D, 'enforcement_available', lambda *_: 'no sandbox in this fixture')
    monkeypatch.setattr(D.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('the profile must not launch'))
    check = run_check(s, grant)
    assert check['state'] == 'UNAVAILABLE'
    assert check['stage_cleanup'] == {'state': 'REMOVED', 'proof': 'no check process was launched'}
    assert not (Path(check['output_root']) / 'input').exists()
    assert check_row(s, check['id'])['stage_cleanup']['state'] == 'REMOVED'


def test_candidate_drift_refusal_removes_the_stage(source, monkeypatch):
    s = source
    grant, _payload = functional(s, request='public-functional-cleanup-drift')
    answer = s['checkout'] / 'src/answer.py'
    cand = D.candidate(s['root'], 'public', {'grant_id': grant['id'], 'name': 'cleanup-drift', 'files': [
        {'path': 'src/answer.py', 'before_sha256': D._pin(answer), 'content': 'ANSWER = 0\n'}]}, s['door'])
    no_launch(monkeypatch)
    check = run_check(s, grant, candidate_id=cand['candidate_id'])
    assert check['state'] == 'REFUSED' and 'differ from the candidate postimages' in check['reason']
    assert check['stage_cleanup']['state'] == 'REMOVED' and not (Path(check['output_root']) / 'input').exists()


def test_refused_ownership_kills_then_proves_the_group_gone_before_cleanup(source, monkeypatch):
    s = source
    grant, _payload = functional(s, request='public-functional-cleanup-register')
    fake_launch(monkeypatch, 'import time; time.sleep(30)')

    def refuse(_process):
        raise ValueError('the host no longer owns this turn')
    monkeypatch.setattr(D, '_turn_control', lambda *_a: (lambda: False, lambda: None, refuse, lambda: False))
    started = time.monotonic()
    check = run_check(s, grant)
    assert check['state'] == 'CANCELLED' and 'refused ownership' in check['reason']
    assert time.monotonic() - started < 20
    assert check['stage_cleanup']['state'] == 'REMOVED' and 'process group is empty' in check['stage_cleanup']['proof']
    assert not (Path(check['output_root']) / 'input').exists()


def test_timeout_without_the_host_sandbox_kills_proves_and_keeps_stdout(source, monkeypatch):
    s = source
    grant, _payload = functional(s, request='public-functional-cleanup-timeout', dependencies={}, timeout_s=2)
    fake_launch(monkeypatch, 'import time; print("started", flush=True); time.sleep(60)')
    check = run_check(s, grant)
    assert check['state'] == 'TIMEOUT'
    assert check['stage_cleanup']['state'] == 'REMOVED' and 'process group is empty' in check['stage_cleanup']['proof']
    assert (Path(check['output_root']) / 'stdout.txt').exists() and not (Path(check['output_root']) / 'input').exists()


def test_normal_exit_removes_the_stage_with_process_proof_and_keeps_results(source, monkeypatch):
    s = source
    grant, _payload = functional(s, request='public-functional-cleanup-normal')
    fake_launch(monkeypatch, 'print("ok")')
    check = run_check(s, grant)
    assert check['state'] == 'COMPLETE' and check['stdout_tail'].strip() == 'ok'
    assert check['stage_cleanup'] == {'state': 'REMOVED', 'proof': 'the launcher exited (0) and its process group is empty'}
    assert (Path(check['output_root']) / 'stdout.txt').read_text().strip() == 'ok'
    assert check['inputs'] and check_row(s, check['id'])['stage_cleanup']['state'] == 'REMOVED'


def test_a_failed_stage_removal_is_reported_and_retained_never_ignored(source, monkeypatch):
    s = source
    grant, _payload = functional(s, request='public-functional-cleanup-failed')
    fake_launch(monkeypatch, 'print("ok")')
    real = D.shutil.rmtree

    def refuse(path, *args, **kwargs):
        if Path(path).name == 'input' and not kwargs.get('ignore_errors'):
            raise PermissionError(13, 'fixture refuses removal', str(path))
        return real(path, *args, **kwargs)
    monkeypatch.setattr(D.shutil, 'rmtree', refuse)
    check = run_check(s, grant)
    assert check['state'] == 'COMPLETE'
    cleanup = check['stage_cleanup']
    assert cleanup['state'] == 'FAILED' and 'fixture refuses removal' in cleanup['error'] and cleanup['retained'] is True
    assert (Path(check['output_root']) / 'input' / 'src/functional_check.py').exists()
    assert check_row(s, check['id'])['stage_cleanup']['state'] == 'FAILED'


def test_an_owner_error_after_staging_still_settles_and_retains_the_row(source, monkeypatch):
    s = source
    grant, _payload = functional(s, request='public-functional-cleanup-error')
    no_launch(monkeypatch)
    with pytest.raises(ValueError):
        run_check(s, grant, candidate_id='DC-' + '0' * 24)
    row = D.rows(W._tasks('public', s['root'])['work'], 'check')[-1]
    assert row['state'] == 'REFUSED' and 'nothing ran' in row['reason'] and row['stage_cleanup']['state'] == 'REMOVED'
    assert not (Path(row['output_root']) / 'input').exists()


def test_settle_retains_the_stage_while_any_group_member_lives(tmp_path):
    stage = tmp_path / 'input'
    stage.mkdir()
    (stage / 'x.py').write_text('x = 1\n')
    leader = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(30)'], start_new_session=True)
    try:
        assert D._settle_stage(stage, leader)['state'] == 'RETAINED' and stage.exists()
    finally:
        os.killpg(leader.pid, signal.SIGKILL)
        leader.wait()
    parent = subprocess.Popen(['/bin/sh', '-c', 'sleep 30 & exit 0'], start_new_session=True)
    parent.wait()
    try:
        held = D._settle_stage(stage, parent)
        assert held['state'] == 'RETAINED' and 'still alive' in held['reason'] and stage.exists()
    finally:
        os.killpg(parent.pid, signal.SIGKILL)
    removed = D._settle_stage(stage, parent)
    assert removed['state'] == 'REMOVED' and not stage.exists()


def test_status_says_recorded_active_and_zero_active_are_not_admissibility_or_idleness(source):
    s = source
    result = D.handle(s['root'], 'public', {'action': 'status', 'work_id': 'work'}, HUMAN)
    notes = ' '.join(result['status_notes'])
    assert 'not current admissibility' in notes and 'not proof that the provider process or session is idle' in notes


def test_retained_check_output_is_a_scoped_pinned_paged_read_after_stage_removal(source, monkeypatch):
    """Root goal item 3: a terminal check's retained stdout is reached through the owner-issued output read, not a host
    output_root. Pages are raw retained bytes that never split UTF-8, bounded by the escaped content so each whole page
    envelope fits the project line; they reassemble to the recorded SHA after stage removal and grant revocation.
    Stale/foreign/out-of-range/changed/purged cases refuse; reading records nothing; empty output has no NEXT loop."""
    s = source
    grant, _payload = functional(s, request='public-functional-output-read', max_output_bytes=131072)
    fake_launch(monkeypatch, 'import sys\nsys.stdout.write((chr(233)+chr(34)+chr(92)+" line"+chr(10))*3000)\n')
    check = run_check(s, grant)
    assert check['state'] == 'COMPLETE' and check['stage_cleanup']['state'] == 'REMOVED'
    raw = (Path(check['output_root']) / 'stdout.txt').read_bytes()
    assert len(raw) == 30000 and check['output_read']['payload'] == {'action': 'status', 'work_id': 'work', 'check_id': check['id'],
                                                                     'expected_sha256': check['stdout_sha256'], 'offset': 0}
    D.handle(s['root'], 'public', {'action': 'revoke', 'grant_id': grant['id']}, HUMAN)   # expired write authority hides no history
    before = W._ledger(s['root']).read_bytes()
    handle, collected, pages = check['output_read'], b'', 0
    while handle is not None:
        page = D.handle(s['root'], 'public', handle['payload'], HUMAN)
        assert page['offset'] == len(collected) and page['stdout_sha256'] == check['stdout_sha256'] and page['encoding'] == 'UTF-8'
        assert page['units'].startswith('raw retained stdout bytes') and not page['producer_output_truncated']
        assert len(json.dumps(page).encode('utf-8')) <= 30000 and page['end_offset'] > page['offset']
        collected += page['content'].encode('utf-8'); handle = page['next_read']; pages += 1
    assert pages > 2 and page['eof'] and collected == raw and 'sha256:' + hashlib.sha256(collected).hexdigest() == check['stdout_sha256']
    assert W._ledger(s['root']).read_bytes() == before
    # The same issued typed view through the actual native tool door and the HTTP door of the existing status read.
    from laplace.native import tools
    from laplace.web import project_work_surface
    first = D.handle(s['root'], 'public', check['output_read']['payload'], HUMAN)
    native = tools.execute(s['root'], 'public', 'work', 'development_source', check['output_read']['payload'], turn_id='WT-parent')
    code, _, body = project_work_surface.handle('/work/development', {}, 'POST', json.dumps(check['output_read']['http']['payload']).encode(), s['root'])
    assert code == 200 and native['content'] == first['content'] == json.loads(body)['content']
    assert native['next_read'] == first['next_read'] and native['stdout_sha256'] == check['stdout_sha256']
    assert not (native.get('delivery_bound') or {}).get('exceeded')
    # The shared delivery owner bounds this view: its profile is declared and a smaller planned line shrinks the WHOLE page.
    from laplace.writing import delivery
    assert delivery.profile('development_source', check['output_read']['payload'])['bound'] >= 16000
    with delivery.planned(line=4000) as plan:
        small = D.handle(s['root'], 'public', check['output_read']['payload'], HUMAN)
    assert delivery.emitted(small) <= 4000 and small['next_read'] and 0 < small['end_offset'] < first['end_offset']
    assert plan['projection'] == {'output': {'check_id': check['id'], 'offset': 0, 'end_offset': small['end_offset']}}
    plain = D.handle(s['root'], 'public', {'action': 'status', 'work_id': 'work'}, HUMAN)
    assert 'content' not in plain and 'status_notes' in plain   # the ordinary status read is unchanged
    payload = check['output_read']['payload']
    ledger = W._ledger(s['root']).read_bytes()
    for bad, code_, field in (({'expected_sha256': 'sha256:' + '0' * 64}, 'STALE_PIN', 'expected_sha256'),
                              ({'offset': len(raw) + 1}, 'PAST_END', 'offset'), ({'offset': 1}, 'UTF8_BOUNDARY', 'offset')):
        for door, details in refusal_doors(s, {**payload, **bad}).items():
            assert details['code'] == code_ and details['field'] == field, (door, details)
            assert details['restart_read']['payload'] == payload and details['next_reads'][0]['payload'] == payload, door
            assert '{' not in details['error'], door
    for bad in ({'check_id': 'DK-' + '0' * 24}, {'work_id': 'absent'}):
        for door, details in refusal_doors(s, {**payload, **bad}).items():
            assert 'unknown or foreign' in details['error'] and 'restart_read' not in details and 'custody' not in details, (door, details)
            assert not any((read or {}).get('operation') == 'development_source' for read in details.get('next_reads') or []), door
    (Path(check['output_root']) / 'stdout.txt').write_bytes(raw + b'x')
    changed = refusal_doors(s, payload)
    (Path(check['output_root']) / 'stdout.txt').unlink()
    purged = refusal_doors(s, payload)
    for door, details in [*changed.items(), *purged.items()]:
        assert details['code'] == 'UNAVAILABLE' and details['state'] == 'UNAVAILABLE' and details['recovery'] is None, (door, details)
        assert details['restart_read'] is None and details['expected'] == check['stdout_sha256'], door
        assert not [read for read in details.get('next_reads') or [] if check['id'] in json.dumps(read)], door   # no read issued
        assert details['custody']['stdout_sha256'] == check['stdout_sha256'] and details['custody']['producer_output_truncated'] is False
        assert details['custody']['stage_cleanup']['state'] == 'REMOVED' and '{' not in details['error'], door
    assert 'changed since' in changed['owner']['error'] and 'purged or missing' in purged['owner']['error']
    assert W._ledger(s['root']).read_bytes() == ledger   # refusals record nothing in the Work ledger
    # Default status stays a bounded semantic page with many real retained checks: issued output reads and recorded
    # cleanup per row, an exact cut-pinned next page, and the whole page inside the shared line.
    for index in range(9):
        fake_launch(monkeypatch, 'print("retained %d")\n' % index)
        run_check(s, functional(s, request='public-functional-output-many-%d' % index)[0])
    status = D.handle(s['root'], 'public', {'action': 'status', 'work_id': 'work'}, HUMAN)
    page = status['development']['checks'] if 'development' in status else status['checks']
    assert len(json.dumps(status).encode('utf-8')) <= 30000 and page['total'] >= 10 and page['next_read'] is not None
    assert all(row['stage_cleanup'] in {'REMOVED', 'RETAINED', 'FAILED', 'UNKNOWN', 'ABSENT'} for row in page['items'])
    assert all('stdout_tail' not in row and 'inputs' not in row for row in page['items'])
    issued = [row['output_read'] for row in page['items'] if 'output_read' in row]
    assert issued and all(D.handle(s['root'], 'public', handle['payload'], HUMAN)['stdout_sha256'] == handle['payload']['expected_sha256'] for handle in issued)
    assert delivery.profile('development_source', {'action': 'status', 'work_id': 'work'})['bound'] >= 16000
    other, _payload = functional(s, request='public-functional-output-empty')
    fake_launch(monkeypatch, 'pass\n')
    empty = run_check(s, other)
    page = D.handle(s['root'], 'public', empty['output_read']['payload'], HUMAN)
    assert page['content'] == '' and page['eof'] and page['next_read'] is None and page['retained_bytes'] == 0


SEG = 'é"\\ \U0001F600'   # Unicode, a JSON-escaped quote and backslash, a line separator and an astral character


def refusal_doors(s, payload):
    """One refused status view through the owner, the native tool door and the HTTP door: each door's typed body."""
    from laplace.native import tools
    from laplace.web import project_work_surface
    with pytest.raises(ValueError) as caught:
        D.handle(s['root'], 'public', payload, HUMAN)
    out = {'owner': {'error': str(caught.value), **(getattr(caught.value, 'details', None) or {})}}
    try:
        native = tools.execute(s['root'], 'public', 'work', 'development_source', payload, turn_id='WT-parent')
    except Exception as exc:   # an escaped refusal is formatted by the one native failure owner
        native = tools.tool_failure(s['root'], 'public', 'work', 'development_source', payload, exc, turn_id='WT-parent')
    assert native.get('ok') is False and not (native.get('delivery_bound') or {}).get('exceeded'), native
    code, _, body = project_work_surface.handle('/work/development', {}, 'POST', json.dumps({'project': 'public', **payload}).encode(), s['root'])
    assert code in (409, 422) and len(body) <= 30000, (code, body[:300])
    return {**out, 'native': native, 'http': json.loads(body)}


def test_status_fits_the_whole_encoded_response_with_exact_continuations_and_row_descent(source, monkeypatch):
    """HOLD F1: maximal real rows (64 escaped-Unicode grant paths, 8 long check profiles, a 32-file candidate and its
    effect, 16 checks) at the default and limit 64. Every page's WHOLE encoding fits the line through the owner, native
    and HTTP doors; traversal reaches exactly the retained identities once; replay is stable; a changed cut and a changed
    row refuse with their restarts; a maximal singleton descends to its exact paged row. No rows are capped, no fields
    hidden, no text clipped and no budget raised."""
    from laplace.native import tools
    from laplace.web import project_work_surface
    from laplace.writing import delivery
    s = source
    dirs = ['%s%02d' % (SEG * 20, index) for index in range(61)]
    for name in dirs:
        (s['checkout'] / 'src' / name).mkdir(parents=True)
    (s['checkout'] / 'src/functional_check.py').write_text('print(1)\n')
    register_runtime(s['root'])
    names = ['functional-%d-%s' % (index, SEG * 60) for index in range(8)]
    profile = {'executable': 'python', 'runtime': 'registered-python', 'args': ['-I', 'src/functional_check.py'],
               'inputs': ['src/functional_check.py'], 'timeout_s': 60}
    payload = copy.deepcopy(s['payload'])
    payload.update(request_id='public-maximal-status', expected_work_revision=W._task_revision(W._tasks('public', s['root'])['work']),
                   paths=['src/*.py', 'evaluator.py', 'guide.md'] + ['src/%s/*' % name for name in dirs], checks={name: profile for name in names})
    assert len(payload['paths']) == 64
    grant = D.grant(s['root'], 'public', payload, HUMAN)['grant']
    files = [{'path': 'src/%s/%s.txt' % (name, SEG * 20), 'before_sha256': None, 'content': 'x\n'} for name in dirs[:32]]
    made = D.candidate(s['root'], 'public', {'grant_id': grant['id'], 'files': files}, s['door'])
    D.apply(s['root'], 'public', {'candidate_id': made['candidate_id']}, s['door'])
    fake_launch(monkeypatch, 'print("maximal")\n')
    for index in range(16):
        D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': names[index % 8]}, HUMAN)
    expected = D._status_items(W._tasks('public', s['root'])['work'])
    assert len(expected['checks']) >= 16 and all(D._encoded(expected[part][0]) > 30000 for part in ('grants', 'candidates', 'effects'))
    # The SDK reaches Source rows only through the real Work detail read (laplace.sdk.work_read, no Source facade): its
    # embedded development facet is the same owner-fitted page, bounded, cut-pinned and descending to exact rows.
    from laplace import sdk

    def development_of(value):
        if isinstance(value, dict):
            if {'cut', 'grants', 'candidates', 'effects', 'checks'} <= set(value):
                return value
            value = list(value.values())
        if isinstance(value, list):
            for item in value:
                found = development_of(item)
                if found is not None:
                    return found
        return None
    embedded = development_of(sdk.work_read({'namespace': 'public', 'view': 'detail', 'id': 'work'}, root=s['root']))
    assert embedded is not None and D._encoded(embedded) <= D.FACET_INLINE_BYTES
    for part in D.STATUS_PARTS:
        shown = embedded[part]
        assert shown['total'] == len(expected[part]) and [row['id'] for row in shown['items']] == [row['id'] for row in expected[part]][:len(shown['items'])]
        for row in shown['items']:
            if row.get('expanded') is False:
                assert D.handle(s['root'], 'public', row['detail_read']['payload'], HUMAN)['row_sha256'] == row['row_sha256']
    assert embedded['checks']['next_read']['payload']['cut'] == embedded['cut']

    def owner(request):
        page = D.handle(s['root'], 'public', request, HUMAN)
        assert D._encoded(page) <= 30000
        return page

    def native(request):
        page = tools.execute(s['root'], 'public', 'work', 'development_source', request, turn_id='WT-parent')
        assert delivery.emitted(page) <= 30000 and not (page.get('delivery_bound') or {}).get('exceeded'), page.get('error')
        return page

    def http(request):
        code, _, body = project_work_surface.handle('/work/development', {}, 'POST', json.dumps({'project': 'public', **request}).encode(), s['root'])
        assert code == 200 and len(body) <= 30000, (code, len(body), body[:300])
        return json.loads(body)

    def traverse(read, first):
        seen, pages, request = {part: [] for part in D.STATUS_PARTS}, [], first
        while request is not None:
            page = read(request)
            development = page['development']
            following = {json.dumps(development[part]['next_read'], sort_keys=True) for part in D.STATUS_PARTS if development[part]['next_read']}
            assert len(following) <= 1   # one shared continuation for every part
            for part in D.STATUS_PARTS:
                seen[part] += [row['id'] for row in development[part]['items']]
            pages.append(page)
            request = json.loads(following.pop())['payload'] if following else None
        assert seen == {part: [row['id'] for row in expected[part]] for part in D.STATUS_PARTS}   # each identity once, none omitted
        return pages

    for limit in (None, 64):
        first = {'action': 'status', 'work_id': 'work', **({'limit': limit} if limit else {})}
        for read in (owner, native, http):
            assert len(traverse(read, first)) > 1
    pages = traverse(owner, {'action': 'status', 'work_id': 'work', 'limit': 64})
    top = pages[0]['development']
    assert top['checks']['requested_limit'] == 64 and top['checks']['limit'] < 64   # a smaller truthful page, not a capped list
    headers = [(part, row) for page in pages for part in D.STATUS_PARTS for row in page['development'][part]['items'] if row.get('expanded') is False]
    assert {part for part, _row in headers} >= {'grants', 'candidates', 'effects'}
    for part, header in headers:
        full = next(row for row in expected[part] if row['id'] == header['id'])
        for read in (owner, native, http):
            text, request = '', header['detail_read']['payload']
            while request is not None:
                body = read(request)
                assert body['offset'] == len(text) and body['row_sha256'] == header['row_sha256'] and body['end_offset'] > body['offset']
                text += body['content']; request = (body['next_read'] or {}).get('payload')
            assert text == D._row_text(full) and D._row_sha(full) == header['row_sha256']
    assert owner({'action': 'status', 'work_id': 'work', 'limit': 64}) == pages[0]   # stable replay at the same cut
    with delivery.planned(line=12000) as plan:
        small = D.handle(s['root'], 'public', {'action': 'status', 'work_id': 'work', 'limit': 64}, HUMAN)
    assert D._encoded(small) <= 12000 and plan['projection']['status']['limit'] <= top['checks']['limit']
    stale = top['checks']['next_read']['payload']
    D.check(s['root'], 'public', {'grant_id': grant['id'], 'name': names[0]}, HUMAN)   # one more retained row moves the cut
    for door, details in refusal_doors(s, stale).items():
        assert details['field'] == 'cut' and details['restart_read']['payload'] == {'action': 'status', 'work_id': 'work', 'limit': 64}, (door, details)
        assert details['next_reads'][0]['payload'] == details['restart_read']['payload'], door   # the owner restart leads every door
    grant_header = next(row for part, row in headers if part == 'grants')
    D.handle(s['root'], 'public', {'action': 'revoke', 'grant_id': grant['id']}, HUMAN)   # the grant row itself changes
    for door, details in refusal_doors(s, grant_header['detail_read']['payload']).items():
        assert details['code'] == 'STALE_PIN' and details['restart_read']['payload']['row_id'] == grant['id'], (door, details)
        assert details['restart_read']['payload']['expected_sha256'] != grant_header['row_sha256'] and '{' not in details['error'], door


def test_native_failure_formatter_keeps_exact_owner_recovery_reads_first_bounded_and_read_only(source):
    """Root 27-owner closure (native/tools.py): the REAL native failure formatter keeps the owner's typed next_reads first,
    exact and deduplicated within its existing bound; a generic per-operation suggestion only follows them; a
    write-shaped or oversized owner entry never becomes a next read; the typed restart_read is untouched. The adapter
    path (tools.execute) is exercised with real owner refusals in the retained-output and status tests above."""
    from laplace.native import tools
    s = source
    restart = D.output_handle('public', 'work', 'DK-' + 'a' * 24, 'sha256:' + 'b' * 64)
    status = {'operation': 'development_source', 'payload': {'action': 'status', 'work_id': 'work'}}
    write = {'operation': 'task', 'payload': {'title': 'not a read'}}
    huge = {'operation': 'development_source', 'payload': {'action': 'status', 'work_id': 'w' * 2000}}
    refusal = W.WorkConflict('typed owner refusal', 'public', 'work', expected='a', observed='b', field='expected_sha256')
    refusal.details.update(code='STALE_PIN', restart_read=restart, next_reads=[restart, restart, write, huge, status])
    payload = {'action': 'status', 'work_id': 'work', 'check_id': 'DK-' + 'a' * 24, 'expected_sha256': 'sha256:' + '0' * 64}
    out = tools.failure_response(s['root'], 'public', 'work', 'development_source', payload, refusal, 'WT-parent')
    listed = out['next_reads']
    assert listed[0] == restart and listed[1] == status and listed.count(restart) == 1, listed
    assert write not in listed and huge not in listed and out['restart_read'] == restart and out['code'] == 'STALE_PIN'
    assert {'operation': 'project', 'payload': {}} in listed[2:], listed   # the generic suggestion follows, never replaces
    assert out['recovery_reads_omitted']['count'] >= 1 and len(listed) <= 8
    # A refusal whose owner issues no recovery gains no Source read: the generic orientation read is not a restart.
    plain = W.WorkConflict('no recovery', 'public', 'work', expected='a', observed='b', field='stdout')
    plain.details.update(code='UNAVAILABLE', restart_read=None, next_reads=[])
    out = tools.failure_response(s['root'], 'public', 'work', 'development_source', payload, plain, 'WT-parent')
    assert out['restart_read'] is None and not [read for read in out.get('next_reads') or [] if read.get('operation') == 'development_source']
    # HOLD F2: when every owner entry filters out and no generic suggestion exists (operation project), or on the
    # unknown-operation early return, the owner's raw list never survives; only filtered, bounded read handles remain.
    raw = W.WorkConflict('raw owner reads', 'public', 'work', expected='a', observed='b', field='x')
    raw.details.update(next_reads=[write, {'operation': 'task', 'payload': {'title': 'x'}}, {'nonsense': True}])
    out = tools.failure_response(s['root'], 'public', 'work', 'project', {}, raw, 'WT-parent')
    assert out['next_reads'] == [], out.get('next_reads')
    mixed = W.WorkConflict('raw owner reads', 'public', 'work', expected='a', observed='b', field='x')
    mixed.details.update(next_reads=[write, restart, restart, huge, {'nonsense': True}])
    out = tools.failure_response(s['root'], 'public', 'work', 'not_a_declared_operation', {}, mixed, 'WT-parent')
    assert out['next_reads'] == [restart], out.get('next_reads')
