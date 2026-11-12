"""Cold ordinary-import/source or installed witness; no provider or live state."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import parse_qs,urlsplit


def witness(prefix, order):
    prefix=Path(prefix).resolve();sys.path.insert(0,str(prefix))
    started=time.perf_counter()
    modules=[importlib.import_module(name) for name in order]
    from laplace.projects import artifacts
    from laplace.native import tools as writing_tools
    from laplace.work import history as author_history
    from laplace.web import research_surface, project_work_surface
    origins={module.__name__:str(Path(module.__file__).resolve()) for module in
             [*modules,artifacts,writing_tools,author_history,research_surface,project_work_surface]}
    assert all(Path(path).is_relative_to(prefix) for path in origins.values()),origins
    assert artifacts is importlib.import_module('laplace.projects.artifacts')
    with tempfile.TemporaryDirectory(prefix='laplace-artifact-witness-A-') as raw:
        root=Path(raw);project=root/'selected project';manuscript=project/'manuscript'
        manuscript.mkdir(parents=True);(root/'contract').mkdir()
        (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}Fixture.\\end{document}\n')
        (root/'registry_projects.json').write_text(json.dumps({'projects':[{
            'name':'p','kind':'conceptric','project_dir':'selected project',
            'tex_root':'selected project/manuscript/main.tex'}]}))
        initial='Retained α observation.\n'*40;updated='Current β observation.\n'
        saved=writing_tools.execute(root,'p','work','store_artifact',{
            'path':'result notes/record.md','scope':'project','before':None,'content':initial,'reason':'Owned installed-consumer witness'})
        read=writing_tools.execute(root,'p','review','read_artifact',{'id':saved['id'],'limit':260})
        parts=[read['content']]
        while not read['complete']:
            read=writing_tools.execute(root,'p','review',**read['read_handle']);parts.append(read['content'])
        assert ''.join(parts)==initial
        query=parse_qs(urlsplit(saved['human_read']['url']).query)
        status,_,body=research_surface.handle('/research/artifact',query,'GET',b'',repo_root=root)
        assert status==200 and body==initial.encode()
        revised=writing_tools.execute(root,'p','work','store_artifact',{
            **saved['update_handle']['payload'],'content':updated,'reason':'Owned guarded update witness'})
        assert research_surface.handle('/research/artifact',query,'GET',b'',repo_root=root)[0]==409
        current=artifacts.read(root,'p',{'id':saved['id']})
        assert current['content']==updated and current['recorded_revision']==saved['revision']
        historical=author_history.record('p','activity:journal:'+saved['id'],root)
        assert historical['record']['after']==initial and historical['record']['id']==saved['id']
        raw_record=next(json.loads(line) for line in (root/'contract/talk.jsonl').read_text().splitlines()
                        if json.loads(line).get('id')==saved['id'])
        assert isinstance(raw_record['after'],dict),'fixture did not exercise existing body custody'
        catalogue=project_work_surface.materials('p',repo_root=root)
        assert len(catalogue['materials'])==1 and catalogue['materials'][0]['id']==revised['id']
        try:writing_tools.execute(root,'p','review','store_artifact',{
            'path':'forbidden.md','before':None,'content':'No permission','reason':'Owned permission-negative witness'})
        except ValueError as error:
            assert str(error)=='Independent review can save findings and tasks; reviewed artifacts stay unchanged.',str(error)
        else:raise AssertionError('Review permission widened')
        assert not (project/'forbidden.md').exists()
        fixture_bytes=sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
    return {'origins':origins,'safe_path':sys.flags.safe_path,'checks':[
        'ordinary imports','single owner identity','native guarded store','UTF-8 continuation',
        'pinned HTTP human read','stale link refusal','current ART read distinct from history',
        'historical exact record with existing custody','metadata catalogue','review refusal'],
        'source_files':{name:hashlib.sha256(Path(path).read_bytes()).hexdigest() for name,path in origins.items()},
        'fixture_bytes':fixture_bytes,'fixture_cleaned':True,'seconds':time.perf_counter()-started}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prefix',required=True)
    parser.add_argument('--reverse',action='store_true');args=parser.parse_args()
    order=['laplace.projects.artifacts','laplace.native.tools','laplace.web.authoring',
           'laplace.work.history','laplace.web.project_work_surface','laplace.web.research_surface']
    print(json.dumps(witness(args.prefix,list(reversed(order)) if args.reverse else order)))
