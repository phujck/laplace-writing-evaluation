"""A cold, authored package-entry witness, not a participant experiment."""
import json
import sys
import time
from pathlib import Path

from laplace.web import research_surface
from laplace.research import research_runs


def test_safe_path_authored_entry_uses_qualified_transitive_dependencies(tmp_path,monkeypatch):
    manuscript=tmp_path/'book'/'manuscript';manuscript.mkdir(parents=True)
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{
        'name':'book','kind':'conceptric','project_dir':'book','tex_root':'book/manuscript',
        'manifest':{'document':{'root':'book/manuscript/main.tex'}}}]}))
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}Fixed fixture.\\end{document}\n')
    package=manuscript/'study';package.mkdir()
    (package/'__init__.py').write_text('')
    (package/'params.py').write_text('VALUE = 7\n')
    (package/'core.py').write_text('from study.params import VALUE\n')
    (manuscript/'entry.py').write_text(
        'import argparse,json,sys\nfrom pathlib import Path\n'
        'sys.path.insert(0,str(Path(__file__).resolve().parent))\n'
        'import study.core,study.params\n'
        "p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()\n"
        "Path(a.result).write_text(json.dumps({'value':study.core.VALUE,'safe_path':sys.flags.safe_path,'executable':sys.executable,'version':sys.version,'origins':[study.core.__file__,study.params.__file__]}))\n")
    shadow=tmp_path/'shadow'/'study';shadow.mkdir(parents=True)
    (shadow/'__init__.py').write_text('raise RuntimeError("ambient same-name package selected")')
    monkeypatch.setenv('PYTHONSAFEPATH','1')
    monkeypatch.setenv('PYTHONPATH',str(shadow.parent)+':'+str(Path(research_surface.__file__).parents[2]))
    spec={'id':'qualified','executable':'entry.py','scope':'manuscript','modes':['smoke'],
          'allowed_args':{},'dependencies':['study/__init__.py','study/core.py','study/params.py']}
    assert research_runs.register_producer('book',spec,tmp_path)[0]==201
    status,result=research_runs.launch('book',{'producer_id':'qualified','mode':'smoke','args':{}},tmp_path)
    assert status==202,result
    for _ in range(160):
        run=research_runs._run_status(manuscript,result['run']['id'])
        if run['state']!='RUNNING':break
        time.sleep(.025)
    assert run['state']=='COMPLETE',run
    observed=json.loads(Path(run['result_absolute']).read_text())
    assert observed['safe_path'] is True and observed['value']==7
    assert Path(observed['executable']).resolve()==Path(sys.executable).resolve()
    assert observed['origins']==[str(package/'core.py'),str(package/'params.py')]
    assert run['provenance']['producer']['path']=='entry.py'
    assert {row['path'] for row in run['provenance']['dependencies']}=={
        'study/__init__.py','study/core.py','study/params.py'}
    (package/'params.py').unlink()
    refused=research_runs.launch('book',{'producer_id':'qualified','mode':'smoke','args':{}},tmp_path)
    assert refused[0]==422 and 'input is missing' in refused[1]['error']
    assert json.loads((manuscript/'research_runs'/'index.json').read_text())['runs']==[run['id']]
