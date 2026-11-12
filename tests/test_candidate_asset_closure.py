"""A style-candidate preview compiles its owned figure closure under the unchanged openin_any=p sandbox.

The canonical source names a generated figure through ``../figures/generated``. The ordinary canonical build
reads it; the candidate compiler refuses ``..`` names. Staging materializes only that owned asset at a
``..``-free alias inside the private compile directory and compiles an exact rewrite of the pinned TeX,
whose original stays pinned beside it. Public synthetic fixture only.
"""
import json
import struct
import time
import zlib

import pytest

from laplace.manuscript import manuscript_source, projection_viewer as compiler
from laplace.manuscript import build_jobs, build_targets, document_templates as templates

MAIN = ('\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\nOriginal.\n'
        '\\includegraphics[width=1cm]{../figures/generated/fig}\n\\includegraphics[width=1cm]{local}\n\\end{document}\n')


def _png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b''))


@pytest.fixture
def figure_case(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', str(tmp_path / 'workspaces'))
    monkeypatch.setattr(compiler, '_repo_root', lambda: tmp_path)
    manuscript = tmp_path / 'book/manuscript'
    manuscript.mkdir(parents=True)
    (tmp_path / 'book/figures/generated').mkdir(parents=True)
    (tmp_path / 'book/figures/generated/fig.png').write_bytes(_png())
    (manuscript / 'local.png').write_bytes(_png())
    (manuscript / 'main.tex').write_text(MAIN)
    (manuscript / 'manuscript_spec.json').write_text(json.dumps({'manuscript': {'genre': 'article'}}))
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [{'name': 'book', 'project_dir': 'book',
        'tex_root': 'book/manuscript', 'manifest': {'document': {'root': 'book/manuscript/main.tex'}}}]}))
    source = manuscript_source.resolve('book', repo_root=tmp_path, include_candidates=False)
    path = tmp_path / source['root']
    original = path.read_bytes()
    value = templates.change('book', {'action': 'prepare', 'source_edits': [{'file': source['root'], 'content': MAIN.replace('Original', 'Reviewed')}],
        'guards': {'expected_selection': manuscript_source.selection_identity(source, 'book'),
                   'source_guards': {source['root']: templates.pin(original)}}, 'reason': 'Synthetic figure preview.'}, tmp_path)
    body = templates.candidate('book', value['candidate_ref'], tmp_path)['proposal']
    yield tmp_path, source, path, original, value, body


def _settle_job(root, job):
    end = time.monotonic() + 60
    while time.monotonic() < end:
        row = build_jobs.status(job, 'book', root)
        if not row['running'] and row['state'] not in build_jobs.ACTIVE and row.get('preview_publication') != 'PENDING':
            return row
        time.sleep(.05)
    pytest.fail('fixture build did not settle')


def test_the_staged_rewrite_touches_only_parent_named_owned_graphics():
    plan = {'book/figures/generated/fig.png': 'laplace-closure-assets/abc.png'}
    text = MAIN + '\\includegraphics{../other/missing}\n'
    staged = build_targets.staged_text(text, 'book/manuscript', plan)
    assert '{laplace-closure-assets/abc}' in staged and '{local}' in staged and '{../other/missing}' in staged
    assert staged.replace('laplace-closure-assets/abc', '../figures/generated/fig') == text
    assert build_targets.staged_text(text, 'book/manuscript', {}) == text


@pytest.mark.skipif(not compiler._latexmk_bin(), reason='installed TeX toolchain required')
def test_canonical_build_and_candidate_preview_close_the_same_owned_figure_under_the_unchanged_sandbox(figure_case):
    root, source, path, original, value, body = figure_case
    closure = body['declaration_closure']
    assert closure['status'] == 'COMPLETE' and 'book/figures/generated/fig.png' in [m['path'] for m in closure['members']]
    code, _ = compiler.recompile(source['root'], 'book', 'author', repo_root=root, compile_root=source['root'], _selection=source)
    end = time.monotonic() + 60
    while compiler.recompile_status(source['root'], repo_root=root, corpus='book', compile_root=source['root'], _selection=source)['running'] and time.monotonic() < end:
        time.sleep(.05)
    canonical = compiler.recompile_status(source['root'], repo_root=root, corpus='book', compile_root=source['root'], _selection=source)
    assert code == 200 and canonical['ok'] and canonical['fresh']
    target = value['build_action']['payload']['build_target']
    code, started = compiler.recompile(target['root'], 'book', 'author', repo_root=root, build_target=target)
    assert code == 200, started
    row = _settle_job(root, started['build_job'])
    assert row['state'] == 'done' and row['ok'] and row['preview_publication'] == 'RECORDED', row.get('log_tail', '')[-800:]
    latest = build_targets.latest_preview('book', value['candidate_ref'], root)
    preview = build_targets.inspect_preview('book', value['candidate_ref'], latest['preview_ref'], root)
    observed = [item['path'] for item in preview['receipt']['observed_local_inputs']]
    invocations = preview['receipt']['toolchain']['invocations']
    assert invocations and all(call['environment']['openin_any'] == 'p' and call['environment']['openout_any'] == 'p' for call in invocations)
    assert preview['path'].read_bytes().startswith(b'%PDF') and not preview['current_input_changes']
    assert observed == sorted(observed) and any(name.startswith('book/manuscript/laplace-closure-assets/') for name in observed)
    assert path.read_bytes() == original and (root / 'book/figures/generated/fig.png').read_bytes() == _png()
    assert not list((root / 'book/manuscript').glob('laplace-closure-*'))  # nothing materialized in canonical source


def test_a_tampered_staged_alias_or_rewrite_refuses_until_restaged(figure_case):
    root, source, path, original, value, body = figure_case
    target = build_targets.stage_candidate('book', value['candidate_ref'], body, root)
    home = build_targets._candidate_home(target, body, root)
    compile_dir, plan = build_targets.staged_asset_plan(body)
    alias = home / compile_dir / plan['book/figures/generated/fig.png']
    staged_main = home / 'book/manuscript/main.tex'
    assert '../figures' not in staged_main.read_text() and (home / build_targets.STAGED_ORIGINALS / 'book/manuscript/main.tex').is_file()
    for victim, data in ((alias, b'not the owned figure'), (staged_main, b'\\documentclass{article}\\begin{document}tampered\\end{document}')):
        victim.chmod(0o644)
        victim.write_bytes(data)
        with pytest.raises(build_targets.TargetRefused, match='stage is unavailable or changed'):
            build_targets.verify_candidate_stage(target, 'book', root, proposal=body)
        build_targets.stage_candidate('book', value['candidate_ref'], body, root)
        assert build_targets.verify_candidate_stage(target, 'book', root, proposal=body) == root / target['root']
    assert path.read_bytes() == original


def test_a_graphic_escaping_the_repository_is_never_materialized(figure_case, tmp_path):
    root, source, path, original, value, body = figure_case
    escaping = MAIN.replace('../figures/generated/fig', '../../../outside/fig')
    prepared = templates.change('book', {'action': 'prepare', 'source_edits': [{'file': source['root'], 'content': escaping}],
        'guards': {'expected_selection': manuscript_source.selection_identity(source, 'book'),
                   'source_guards': {source['root']: templates.pin(original)}}, 'reason': 'Escaping figure.'}, root)
    body = templates.candidate('book', prepared['candidate_ref'], root)['proposal']
    closure = body['declaration_closure']
    assert closure['status'] == 'UNPROVED' and any(d['code'] == 'ESCAPING_DECLARATION' for d in closure['diagnostics'])
    assert build_targets.staged_asset_plan(body)[1] == {}
