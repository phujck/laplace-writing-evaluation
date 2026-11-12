"""The physical source owner serializes cooperating effects, not model work."""
import gc
import threading
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from laplace.manuscript import manuscript_source as source


def test_canonical_complete_set_reentrant_subset_and_live_registry(tmp_path):
    a, b = tmp_path / 'a.tex', tmp_path / 'b.tex'
    alias = tmp_path / 'alias.tex'
    alias.symlink_to(a)
    with source.source_mutation([b, alias, a]) as lease:
        assert lease.paths == (a, b) and lease.outermost
        assert source.source_mutation_active()
        with source.source_mutation([alias]) as nested:
            assert nested.paths == (a,) and not nested.outermost
        with pytest.raises(source.SourceLeaseError, match='cannot grow'):
            with source.source_mutation([tmp_path / 'c.tex']):
                pass
    assert not source.source_mutation_active()
    gc.collect()
    assert str(a) not in source._SOURCE_LOCKS and str(b) not in source._SOURCE_LOCKS
    assert not a.exists()  # admission of a new target is still the caller's job


def test_platform_lock_normalization_does_not_rewrite_source_coordinates(tmp_path, monkeypatch):
    target = tmp_path / 'Chapter-ONE.tex'
    target.write_text('Original source.')
    # Exercise the key-normalization contract on this POSIX fixture without
    # pretending the actual filesystem has Windows alias/case semantics.
    monkeypatch.setattr(source.os.path, 'normcase', lambda value: value.lower())
    with source.source_mutation([target]) as lease:
        assert lease.paths == (target,)
        assert lease.paths[0].read_text() == 'Original source.'
        with source.source_mutation([target]) as nested:
            assert nested.paths == (target,) and not nested.outermost


def test_opposite_multi_file_order_finishes_without_deadlock(tmp_path):
    paths = [tmp_path / 'a.tex', tmp_path / 'b.tex']
    barrier = threading.Barrier(2)
    order = []
    def mutate(index):
        barrier.wait(timeout=2)
        with source.source_mutation(paths if index == 0 else paths[::-1], timeout=1):
            order.append(('enter', index))
            time.sleep(.02)
            order.append(('exit', index))
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(mutate, i) for i in range(2)]
        for future in futures:
            future.result(timeout=2)
    assert order[0][0] == 'enter' and order[1] == ('exit', order[0][1])


def test_total_deadline_releases_partial_set(tmp_path):
    a, b, c = [tmp_path / (name + '.tex') for name in 'abc']
    entered = threading.Event()
    release = threading.Event()
    def hold():
        with source.source_mutation([b, c]):
            entered.set()
            assert release.wait(2)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(hold)
        assert entered.wait(1)
        start = time.monotonic()
        try:
            with pytest.raises(source.SourceLeaseTimeout):
                with source.source_mutation([a, b, c], timeout=.08):
                    pytest.fail('partial set must not be yielded')
            assert time.monotonic() - start < .3
            # Another thread can immediately acquire the earlier partial member.
            with ThreadPoolExecutor(1) as other:
                def acquire():
                    with source.source_mutation([a], timeout=0):
                        return True
                assert other.submit(acquire).result(timeout=1)
        finally:
            release.set()
        future.result(timeout=1)


def test_different_files_progress_while_same_file_waits(tmp_path):
    a, b = tmp_path / 'a.tex', tmp_path / 'other-project.tex'
    entered = threading.Event()
    release = threading.Event()
    def hold():
        with source.source_mutation([a]):
            entered.set()
            assert release.wait(2)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(hold)
        assert entered.wait(1)
        def other():
            with source.source_mutation([b], timeout=0):
                return True
        assert pool.submit(other).result(timeout=1)
        with pytest.raises(source.SourceLeaseTimeout):
            with source.source_mutation([a], timeout=0):
                pass
        release.set()
        first.result(timeout=1)


def test_cross_process_lease_uses_normal_launcher_and_export_ignores_sidecar(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    target = tmp_path / 'main.tex'
    code = """from laplace.manuscript.manuscript_source import source_mutation, SourceLeaseTimeout
import sys
try:
    with source_mutation([sys.argv[1]], timeout=.05):
        raise AssertionError('another process entered held physical source')
except SourceLeaseTimeout:
    print('REFUSED')
"""
    with source.source_mutation([target]):
        result = subprocess.run([str(repo / 'scripts/laplace-python'), '-c', code, str(target)],
                                cwd=repo, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'REFUSED'
    import importlib.util
    spec = importlib.util.spec_from_file_location('lease_export_inventory', repo / 'scripts/writing_eval_manifest.py')
    inventory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inventory)
    assert inventory._excluded(Path('.main.tex.source.lock'))
    assert not inventory._excluded(Path('main.tex'))


@pytest.mark.parametrize('timeout', [-1, float('inf'), float('nan'), True])
def test_unbounded_or_invalid_deadline_refused(tmp_path, timeout):
    with pytest.raises(ValueError):
        with source.source_mutation([tmp_path / 'a.tex'], timeout=timeout):
            pass


def test_source_stage_is_private_exact_bytes_and_preserves_mode(tmp_path, monkeypatch):
    import os
    import stat
    target = tmp_path / 'main.tex'
    target.write_bytes(b'Original\r\nsource.\r\n')
    target.chmod(0o640)
    intended = 'Changed Ω\r\nsource.\r\n'.encode()
    with source.source_mutation([target]):
        staged = source.stage_source(target, intended)
        assert target.read_bytes() == b'Original\r\nsource.\r\n'
        assert staged.read_bytes() == intended
        assert stat.S_IMODE(staged.stat().st_mode) == stat.S_IMODE(target.stat().st_mode)
        staged.replace(target)
    assert target.read_bytes() == intended
    original = target.read_bytes()
    def failed_sync(*args):
        raise OSError('controlled staging failure')
    monkeypatch.setattr(os, 'fsync', failed_sync)
    with pytest.raises(OSError, match='controlled staging'):
        source.stage_source(target, b'Unpublished bytes')
    assert target.read_bytes() == original
    assert not list(tmp_path.glob('.main.tex.*.pending'))
