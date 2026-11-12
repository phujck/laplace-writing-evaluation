"""Cold subprocess checks of runtime selection and source isolation, without lifecycle acts."""
from __future__ import annotations
from laplace.core import checkout

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cold_checkout(tmp_path):
    root = tmp_path / 'cold'
    for name in ('scripts/laplace-python', 'scripts/laplace_python.py',
                 'src/laplace/core/runtime.py', 'runtime_profiles.toml'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    for relative in ('src/laplace', 'src/atlas'):
        folder = root / relative
        folder.mkdir(parents=True, exist_ok=True)
        (folder / '__init__.py').write_text('CHECKOUT = "cold"\n')
    return root


def run(root, *args, **updates):
    env = {**os.environ, 'LAPLACE_PYTHON': sys.executable,
           'LAPLACE_RUNTIME_SCRATCH': str(root / 'tmp'),
           'LAPLACE_STATE': str(root / 'state'), **updates}
    return subprocess.run([str(root / 'scripts/laplace-python'), *args], cwd=root,
                          env=env, capture_output=True, text=True, timeout=10)


def test_cold_source_wins_over_poisoned_pythonpath_and_survives_child(cold_checkout, tmp_path):
    poison = tmp_path / 'poison'
    for package in ('laplace', 'atlas'):
        folder = poison / package
        folder.mkdir(parents=True)
        (folder / '__init__.py').write_text('raise RuntimeError("wrong checkout imported")\n')
    probe = ('import json,sys,laplace,atlas; '
             'print(json.dumps({"laplace":laplace.__file__,"atlas":atlas.__file__, '
             '"python":sys.executable,"no_user_site":bool(sys.flags.no_user_site)}))')
    command = ("import subprocess,sys; " + probe + "; "
               "print(subprocess.check_output([sys.executable,'-c'," + repr(probe) + "],text=True).strip())")
    result = run(cold_checkout, '-c', command, PYTHONPATH=str(poison), PYTHONHOME=str(poison))
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 2
    for row in rows:
        assert Path(row['laplace']).is_relative_to(cold_checkout / 'src')
        assert Path(row['atlas']).is_relative_to(cold_checkout / 'src/atlas')
        assert Path(row['python']).resolve() == Path(sys.executable).resolve()
        assert row['no_user_site'] is True
    assert not (cold_checkout / 'state').exists()


def test_script_and_module_arguments_survive(cold_checkout):
    module = cold_checkout / 'src' / 'argument_probe.py'
    module.write_text('import json,sys; print(json.dumps(sys.argv[1:]))\n')
    for invocation in ((str(module),), ('-m', 'argument_probe')):
        result = run(cold_checkout, *invocation, 'space here', '--literal')
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == ['space here', '--literal']


def test_missing_override_refuses_without_fallback(cold_checkout):
    result = run(cold_checkout, '-c', 'raise AssertionError("executed")',
                 LAPLACE_PYTHON=str(cold_checkout / 'absent-python'))
    assert result.returncode == 2
    assert 'unavailable' in result.stderr
    assert not (cold_checkout / 'state').exists()


def test_unselected_interpreter_refuses_before_work(cold_checkout):
    policy = cold_checkout / 'src/laplace/core/runtime.py'
    command = (f'import runpy; p=runpy.run_path({str(policy)!r}); '
               f'p["require_runtime"]({str(cold_checkout)!r})')
    result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', command],
                            capture_output=True, text=True, timeout=10,
                            env={**os.environ, 'LAPLACE_PYTHON': sys.executable})
    assert result.returncode != 0
    assert 'scripts/laplace-python' in result.stderr
    assert not (cold_checkout / 'state').exists()


def test_application_error_keeps_its_traceback(cold_checkout):
    result = run(cold_checkout, '-c', 'raise RuntimeError("application failed")')
    assert result.returncode != 0
    assert 'RuntimeError: application failed' in result.stderr
    assert 'LAPLACE RUNTIME REFUSED' not in result.stderr


def test_runtime_preserves_platform_temp_unless_explicitly_selected(cold_checkout, tmp_path):
    platform_temp = tmp_path / 'platform-temp'
    platform_temp.mkdir()
    probe = ('import json,tempfile,os; print(json.dumps({"temp":tempfile.gettempdir(),'
             '"env":[os.environ.get(k) for k in ("TMPDIR","TMP","TEMP")]}))')
    result = run(cold_checkout, '-c', probe, LAPLACE_RUNTIME_SCRATCH='',
                 TMPDIR=str(platform_temp), TMP=str(platform_temp), TEMP=str(platform_temp))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['temp'] == str(platform_temp)
    assert not (cold_checkout / 'tmp').exists()

    # Explicit fixtures retain their existing override semantics on all three
    # platform environment keys, including for spawned child interpreters.
    result = run(cold_checkout, '-c', probe, TMPDIR=str(platform_temp))
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)
    assert row['temp'] == str(cold_checkout / 'tmp')
    assert row['env'] == [str(cold_checkout / 'tmp')] * 3
