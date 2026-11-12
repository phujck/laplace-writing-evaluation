"""Actual disposable TeX outputs must agree with the existing build receipt."""
import json
import os
import shutil
import time
from pathlib import Path

import pytest
from laplace.manuscript import projection_viewer as pv, tex_dependencies
from laplace.research import literature_support
from laplace.core import checkout


class Lock:
    def release(self):
        pass


def build(root, tex):
    pv._recompile_worker(tex, tex.relative_to(root).as_posix(), '', 'test', Lock(), root)
    return pv.recompile_status(tex.relative_to(root).as_posix(), repo_root=root)


@pytest.fixture
def compiled(tmp_path, monkeypatch):
    if not shutil.which('latexmk'):
        pytest.skip('real latexmk unavailable')
    tex = tmp_path / 'main.tex'
    (tmp_path / 'parts').mkdir()
    tex.write_text(r'''\documentclass{article}
\begin{document}
\include{parts/chapter}
\bibliographystyle{plain}
\bibliography{refs}
\end{document}
''')
    (tmp_path / 'parts/chapter.tex').write_text(r'An actual cited sentence \cite{FixtureSource}.' + '\n')
    (tmp_path / 'refs.bib').write_text('@book{FixtureSource,title={Actual fixture},author={Author, Fixture},year={2026}}\n')
    row = build(tmp_path, tex)
    assert row['fresh'], row
    return tmp_path, tex


def test_actual_output_replace_delete_and_same_stat_bytes_are_not_current(compiled):
    root, tex = compiled
    paths = ['main.pdf', 'main.aux', 'main.bbl', 'parts/chapter.aux', 'main.synctex.gz', 'main.fls']
    pins = pv._read_recompile_status(tex)['outputs']['files']
    assert set(paths) <= set(pins)
    assert pins['main.synctex'] is None
    for name in paths:
        path = root / name
        saved, stamp = path.read_bytes(), path.stat()
        # Same size and restored mtime still cannot authenticate different bytes.
        path.write_bytes(b'X' * len(saved))
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        status = pv.recompile_status('main.tex', repo_root=root)
        assert not status['fresh'] and name in status['output_changes'], (name, status)
        observed = literature_support.bibliography_observation('fixture', root, {'root': 'main.tex'})
        assert not observed['current'] and not observed['rendered_keys']
        path.unlink()
        assert name in pv.recompile_status('main.tex', repo_root=root)['output_changes']
        path.write_bytes(saved)
        # Restoring proven bytes recovers proof; no new receipt is fabricated.
        # Map mtime must still be >= PDF mtime for existing viewer semantics.
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        assert pv.recompile_status('main.tex', repo_root=root)['fresh']


def test_missing_output_marker_rejects_invented_bibliography_key(compiled):
    root, tex = compiled
    # Existing pins cannot bless post-build aux/bbl content or an alternate map.
    (root / 'main.aux').write_text('\\bibcite{InventedAfterBuild}{1}\n')
    (root / 'main.bbl').write_text('\\bibitem{InventedAfterBuild}Uncompiled\n')
    (root / 'main.synctex').write_text('invented alternate map')
    row = literature_support.bibliography_observation('fixture', root, {'root': 'main.tex'})
    assert row['observed_keys'] == ['InventedAfterBuild']
    assert not row['current'] and row['rendered_keys'] == []
    assert 'main.synctex' in row['changed_outputs']


def test_bibliography_proof_covers_parsed_bytes_even_when_files_are_restored(compiled,monkeypatch):
    root,tex=compiled;aux=root/'main.aux';bbl=root/'main.bbl'
    original_aux,original_bbl=aux.read_bytes(),bbl.read_bytes()
    aux.write_text('\\bibcite{TransientUncompiled}{1}\n')
    bbl.write_text('\\bibitem{TransientUncompiled}Not produced by the build.\n')
    current_status=pv.recompile_status
    def restore_then_verify(*args,**kwargs):
        aux.write_bytes(original_aux);bbl.write_bytes(original_bbl)
        return current_status(*args,**kwargs)
    monkeypatch.setattr(pv,'recompile_status',restore_then_verify)
    observed=literature_support.bibliography_observation('fixture',root,{'root':'main.tex'})
    assert not observed['current'] and not observed['rendered_keys']
    assert observed['observed_keys']==['TransientUncompiled']
    assert observed['output_proof']=='READ_CHANGED'
    assert {'main.aux','main.bbl'}<=set(observed['changed_outputs'])
    assert aux.read_bytes()==original_aux and bbl.read_bytes()==original_bbl


def test_drifted_build_forces_all_rules_and_repairs_real_outputs(compiled, monkeypatch):
    root, tex = compiled
    for name in ['main.pdf', 'main.bbl', 'parts/chapter.aux', 'main.synctex.gz']:
        (root / name).write_bytes(b'Uncompiled replacement')
    calls = []
    run = pv._run
    def observe(args, *rest):
        calls.append(args)
        return run(args, *rest)
    monkeypatch.setattr(pv, '_run', observe)
    row = build(root, tex)
    assert row['fresh'], row
    assert '-g' in calls[0]
    assert (root / 'main.pdf').read_bytes().startswith(b'%PDF')
    bib = literature_support.bibliography_observation('fixture', root, {'root': 'main.tex'})
    assert bib['current'] and bib['rendered_keys'] == ['FixtureSource']


def test_verified_unchanged_http_rebuild_retains_real_incremental_noop(compiled, monkeypatch):
    root, tex = compiled
    stamp = (root / 'main.pdf').stat().st_mtime_ns
    calls = []
    run = pv._run
    monkeypatch.setattr(pv, '_run', lambda args, *rest: (calls.append(args), run(args, *rest))[1])
    code, _ = pv.recompile('main.tex', '', 'test', repo_root=root)
    assert code == 200
    for _ in range(200):
        row = pv.recompile_status('main.tex', repo_root=root)
        if row['state'] != 'running':
            break
        time.sleep(.05)
    assert row['fresh'], row
    assert '-g' not in calls[0]
    assert (root / 'main.pdf').stat().st_mtime_ns == stamp
    assert 'nothing to do' in row['log_tail'].lower()


def test_legacy_receipt_requires_actual_rebuild_without_status_mutation(compiled, monkeypatch):
    root, tex = compiled
    receipt = pv._read_recompile_status(tex)
    receipt.pop('outputs')
    pv._write_recompile_status(tex, receipt)
    path = pv._recompile_status_path(tex)
    before, stamp = path.read_bytes(), path.stat().st_mtime_ns
    row = pv.recompile_status('main.tex', repo_root=root)
    assert not row['fresh'] and row['output_proof'] == 'LEGACY_UNVERIFIED'
    assert not literature_support.bibliography_observation('fixture', root, {'root': 'main.tex'})['current']
    assert path.read_bytes() == before and path.stat().st_mtime_ns == stamp
    run, calls = pv._run, []
    monkeypatch.setattr(pv, '_run', lambda args, *rest: (calls.append(args), run(args, *rest))[1])
    assert build(root, tex)['fresh']
    assert '-g' in calls[0]


def test_failed_compile_cannot_authenticate_retained_or_partial_outputs(compiled):
    root, tex = compiled
    tex.write_text(tex.read_text().replace('\\end{document}', '\\undefinedFixtureCommand\n\\end{document}'))
    row = build(root, tex)
    assert row['state'] == 'error' and not row['fresh'] and row['ok'] is False
    assert 'Undefined control sequence' in row['log_tail']
    assert pv._read_recompile_status(tex)['outputs'] is None
    assert not literature_support.bibliography_observation('fixture', root, {'root': 'main.tex'})['current']


def test_forced_noop_cannot_repin_recent_unverified_artifact(compiled, monkeypatch):
    root, tex = compiled
    (root / 'main.pdf').write_bytes(b'Uncompiled current-mtime PDF')
    monkeypatch.setattr(pv, '_run', lambda *_: (True, 'Nothing to do; all targets are up-to-date'))
    row = build(root, tex)
    assert row['ok'] is False and not row['fresh']


def test_nested_missing_aux_marker_and_cycle_are_bounded(compiled):
    root, tex = compiled
    (root / 'main.aux').write_text('\\@input{parts/missing.aux}\n\\@input{main.aux}\n')
    outputs = pv._build_output_snapshot(tex, root)
    assert outputs['files']['parts/missing.aux'] is None
    assert len(outputs['files']) < 20


def test_native_http_scope_share_output_currentness(tmp_path, monkeypatch):
    if not shutil.which('latexmk'):
        pytest.skip('real latexmk unavailable')
    from test_literature_joined_workflow import project, bind, execute
    from laplace.web import authoring as authoring_surface
    manuscript, source, key, _ = project(tmp_path, monkeypatch)
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    bind(tmp_path, key)
    chapter = manuscript / 'chapters/chapter-01.tex'
    chapter.write_text(chapter.read_text().replace('First passage.', 'First passage \\cite{FixtureSource}.'))
    tex = tmp_path / source['root']
    assert build(tmp_path, tex)['fresh']
    assert execute(tmp_path, 'literature_scope', {'node': 'result:first'})['ready_for_completion']
    for missing in [False, True]:
        (tex.with_suffix('.bbl').unlink() if missing else tex.with_suffix('.pdf').write_bytes(b'Foreign PDF'))
        native = execute(tmp_path, 'build_status', {})
        code, _, raw = authoring_surface.handle('/authoring/build', {'project': ['joined']}, 'GET', b'')
        http = json.loads(raw)
        scope = execute(tmp_path, 'literature_scope', {'node': 'result:first'})
        assert code == 200 and http['fresh'] == native['fresh'] == scope['bibliography']['current'] == False
        assert http['output_changes'] == native['output_changes'] == scope['bibliography']['changed_outputs']
        assert not scope['ready_for_completion']


def test_changed_inputs_keep_incremental_build_and_ungrounded_noop_forces_once(compiled, monkeypatch):
    root, tex = compiled
    chapter = root / 'parts/chapter.tex'
    chapter.write_text(chapter.read_text() + 'Changed authored source.\n')
    run, calls = pv._run, []
    def observe(args, *rest):
        calls.append(args)
        return run(args, *rest)
    monkeypatch.setattr(pv, '_run', observe)
    assert build(root, tex)['fresh']
    assert '-g' not in calls[0]
    chapter.write_text(chapter.read_text() + 'Another source change.\n')
    calls.clear()
    def stale_noop(args, *rest):
        calls.append(args)
        if len(calls) == 1:
            return True, 'Nothing to do; all targets are up-to-date'
        return run(args, *rest)
    monkeypatch.setattr(pv, '_run', stale_noop)
    assert build(root, tex)['fresh']
    assert '-g' not in calls[0] and '-g' in calls[1] and len(calls) == 2


def test_supplied_bibliography_input_is_pinned_but_not_deleted(tmp_path):
    if not shutil.which('latexmk'):
        pytest.skip('real latexmk unavailable')
    tex = tmp_path / 'main.tex'
    tex.write_text(r'\documentclass{article}\begin{document}\input{manual.bbl}\end{document}' + '\n')
    manual = tmp_path / 'manual.bbl'
    manual.write_text('A supplied bibliography passage.\n')
    assert build(tmp_path, tex)['fresh']
    receipt = pv._read_recompile_status(tex)['outputs']
    assert 'manual.bbl' in receipt['files'] and 'manual.bbl' not in receipt['generated']
    manual.write_text('An authored bibliography correction.\n')
    assert not pv.recompile_status('main.tex', repo_root=tmp_path)['fresh']
    assert build(tmp_path, tex)['fresh']
    assert manual.read_text() == 'An authored bibliography correction.\n'


def test_repair_unlinks_replaced_aux_alias_without_deleting_other_owner(compiled):
    root, tex = compiled
    aux = root / 'parts/chapter.aux'
    other = root / 'unrelated-owner.aux'
    other.write_text('Unrelated owner artifact retained.\n')
    aux.unlink()
    aux.symlink_to(other)
    assert not pv.recompile_status('main.tex', repo_root=root)['fresh']
    assert build(root, tex)['fresh']
    assert other.read_text() == 'Unrelated owner artifact retained.\n'
    assert not aux.is_symlink()
