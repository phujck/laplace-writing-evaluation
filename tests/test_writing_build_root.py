"""The native MCP process must build its bound workspace without root monkeypatches."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from laplace.manuscript import projection_viewer as pv


@pytest.mark.skipif(not shutil.which('latexmk'), reason='real TeX toolchain unavailable')
def test_fresh_process_build_uses_bound_workspace_and_keeps_dependency_scope(tmp_path):
    root = tmp_path / 'unrelated-workspace'
    manuscript = root / 'book/manuscript'
    manuscript.mkdir(parents=True)
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [{
        'name': 'independent-book', 'project_dir': 'book', 'tex_root': 'book/manuscript'}]}))
    (manuscript / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n'
        '\\input{chapter}\n\\end{document}\n')
    chapter = manuscript / 'chapter.tex'
    chapter.write_text('This document belongs to the explicitly selected workspace.\n')
    code = '''
import json,sys,time
from pathlib import Path
from laplace.native import tools as writing_tools
root=Path(sys.argv[1])
started=writing_tools.execute(root,'independent-book','work','build',{})
assert started['status']=='started', started
deadline=time.monotonic()+30
while time.monotonic()<deadline:
    state=writing_tools.execute(root,'independent-book','work','build_status',{})
    if state['state'] in ('done','error'):break
    time.sleep(.05)
assert state['ok'] and state['fresh'], state
assert state['pdf']=='book/manuscript/main.pdf', state
chapter=root/'book/manuscript/chapter.tex'
chapter.write_text(chapter.read_text()+'The dependency changed.\\n')
changed=writing_tools.execute(root,'independent-book','work','build_status',{})
assert not changed['fresh'], changed
assert 'book/manuscript/chapter.tex' in changed['dependency_changes'], changed
print(json.dumps({'built':state,'changed':changed}))
'''
    env = dict(os.environ, LAPLACE_STATE=str(tmp_path / 'state'))
    run = subprocess.run([sys.executable, '-c', code, str(root)],
                         cwd=Path(__file__).resolve().parents[1], env=env,
                         capture_output=True, text=True, timeout=45)
    assert run.returncode == 0, run.stdout + run.stderr
    assert (manuscript / 'main.pdf').read_bytes().startswith(b'%PDF')
    result = json.loads(run.stdout.splitlines()[-1])
    assert result['built']['state'] == 'done'
    assert pv._safe_path('../main.tex', root) is None


def test_partial_pdf_from_failed_compiler_is_not_success(tmp_path, monkeypatch):
    tex = tmp_path / 'main.tex'
    tex.write_text('\\documentclass{article}\n\\begin{document}\\badcommand\\end{document}')
    def fail(*args, **kwargs):
        tex.with_suffix('.pdf').write_bytes(b'%PDF partial')
        tex.with_suffix('.synctex.gz').write_bytes(b'partial')
        return False, '! Undefined control sequence: badcommand'
    monkeypatch.setattr(pv, '_run', fail)
    monkeypatch.setattr(pv, '_pdflatex_sequence', fail)
    result = pv.compile_tex('main.tex', repo_root=tmp_path)
    assert not result['ok']
    assert result['pdf'] is None
    assert 'Undefined control sequence' in result['log_tail']
