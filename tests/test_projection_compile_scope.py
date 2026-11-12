"""Selected-root membership and real nested-source mapping; no provider/state copies."""
import json
import shutil
import time
from pathlib import Path

import pytest

from laplace.manuscript import manuscript_source, projection_viewer as pv


def fixture(root, monkeypatch):
    md=root/'project/manuscript';(md/'chapters').mkdir(parents=True)
    main=md/'main.tex';chapter=md/'chapters/chapter-01.tex'
    main.write_text('\\documentclass{article}\n\\begin{document}\n\\input{chapters/chapter-01}\n\\end{document}\n')
    chapter.write_text('% PLAN:chapter\n% NODES: claim:chapter\n\\section{Nested chapter}\nFirst paragraph of the selected chapter.\n\nA distinctive second paragraph for the cursor mapping.\n')
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'book','project_dir':'project',
        'tex_root':'project/manuscript','manifest':{'document':{'root':'project/manuscript/main.tex'}}}]}))
    monkeypatch.setattr(pv,'_repo_root',lambda:root)
    monkeypatch.setattr(pv,'_recompile_status_path',lambda path:root/(path.stem+'.build.status.json'))
    monkeypatch.setattr(pv,'_recompile_lock_path',lambda path:root/(path.stem+'.build.lock'))
    return main,chapter


def test_addressed_scope_resolves_and_traverses_once_without_unrelated_candidate_discovery(tmp_path,monkeypatch):
    main,chapter=fixture(tmp_path,monkeypatch)
    (main.parent/'unrelated.tex').write_text('\\documentclass{article}\n\\begin{document}Unrelated.\\end{document}')
    counts={'resolve':0,'traversal':0};resolve=manuscript_source.resolve;traverse=manuscript_source.traversal
    monkeypatch.setattr(manuscript_source,'_candidate_rows',lambda *a:pytest.fail('no candidate discovery for addressed read'))
    def selected(*a,**k):counts['resolve']+=1;return resolve(*a,**k)
    def tree(*a,**k):counts['traversal']+=1;return traverse(*a,**k)
    monkeypatch.setattr(manuscript_source,'resolve',selected);monkeypatch.setattr(manuscript_source,'traversal',tree)
    out=pv.doc_model(chapter.relative_to(tmp_path).as_posix(),corpus='book',compile_root=main.relative_to(tmp_path).as_posix())
    assert out['root']==main.relative_to(tmp_path).as_posix() and counts=={'resolve':1,'traversal':1}
    assert {row['file'] for row in out['files']}=={main.relative_to(tmp_path).as_posix(),chapter.relative_to(tmp_path).as_posix()}


@pytest.mark.parametrize('declaration',['explicit','saved','registered','target'])
def test_addressed_selection_preserves_declared_project_shapes_without_discovery(tmp_path,monkeypatch,declaration):
    main,chapter=fixture(tmp_path,monkeypatch);registry=json.loads((tmp_path/'registry_projects.json').read_text());project=registry['projects'][0]
    if declaration!='explicit':project['manifest']={}
    if declaration=='saved':
        (main.parent/'document_selection.json').write_text(json.dumps({'root':main.relative_to(tmp_path).as_posix()}))
    elif declaration=='target':
        target=main.parent/'whitepaper';(target/'chapters').mkdir(parents=True)
        (target/'main.tex').write_text(main.read_text());(target/'chapters/chapter-01.tex').write_text(chapter.read_text())
        main,chapter=target/'main.tex',target/'chapters/chapter-01.tex'
    (tmp_path/'registry_projects.json').write_text(json.dumps(registry))
    monkeypatch.setattr(manuscript_source,'_candidate_rows',lambda *a:pytest.fail('no addressed discovery'))
    selected=manuscript_source.resolve('book',tmp_path,include_candidates=False)
    assert selected['status']=='resolved' and selected['root']==main.relative_to(tmp_path).as_posix()
    assert pv.resolve_root(chapter,corpus='book',repo_root=tmp_path)==main


def test_discovered_legacy_root_requires_explicit_existing_selection_for_addressed_reads(tmp_path,monkeypatch):
    main,chapter=fixture(tmp_path,monkeypatch);other=main.with_name('paper.tex');main.rename(other)
    data=json.loads((tmp_path/'registry_projects.json').read_text());data['projects'][0]['manifest']={};(tmp_path/'registry_projects.json').write_text(json.dumps(data))
    full=manuscript_source.resolve('book',tmp_path);assert full['root']==other.relative_to(tmp_path).as_posix()
    with pytest.raises(pv.CompileRootRefused,match='unambiguous declared'):
        pv.resolve_root(chapter,corpus='book',repo_root=tmp_path)
    manuscript_source.select('book',other.relative_to(tmp_path).as_posix(),repo_root=tmp_path)
    assert pv.resolve_root(chapter,corpus='book',repo_root=tmp_path)==other


def test_unrelated_fragment_missing_scope_and_changed_selection_refuse_without_guessed_root(tmp_path,monkeypatch):
    main,chapter=fixture(tmp_path,monkeypatch);unrelated=main.parent/'chapters/unrelated.tex';unrelated.write_text('Not included.')
    with pytest.raises(pv.CompileRootRefused,match='requires'):
        pv.resolve_root(chapter,repo_root=tmp_path)
    with pytest.raises(pv.CompileRootRefused,match='not a proved member'):
        pv.resolve_root(unrelated,corpus='book',repo_root=tmp_path)
    registry=json.loads((tmp_path/'registry_projects.json').read_text());alternate=main.parent/'alternate.tex';alternate.write_text(main.read_text())
    registry['projects'][0]['manifest']['document']['root']=alternate.relative_to(tmp_path).as_posix();(tmp_path/'registry_projects.json').write_text(json.dumps(registry))
    status,_,raw=pv.handle('/projection/doc',{'file':[main.relative_to(tmp_path).as_posix()],
        'corpus':['book'],'compile_root':[main.relative_to(tmp_path).as_posix()]},'GET',b'')
    assert status==409 and json.loads(raw)['reason']=='compile-root-selection-changed'
    assert pv.resolve_root(main,repo_root=tmp_path)==main  # explicitly unqualified standalone remains supported


@pytest.mark.parametrize('route',['/projection/pdf','/projection/pdfinfo'])
def test_qualified_pdf_cannot_bypass_changed_root_but_unqualified_history_stays_explicit(tmp_path,monkeypatch,route):
    main,chapter=fixture(tmp_path,monkeypatch);pdf=main.with_suffix('.pdf');pdf.write_bytes(b'Exact old PDF bytes')
    registry=json.loads((tmp_path/'registry_projects.json').read_text());alternate=main.with_name('alternate.tex');alternate.write_text(main.read_text())
    registry['projects'][0]['manifest']['document']['root']=alternate.relative_to(tmp_path).as_posix();(tmp_path/'registry_projects.json').write_text(json.dumps(registry))
    args={'file':[pdf.relative_to(tmp_path).as_posix()],'corpus':['book'],'compile_root':[main.relative_to(tmp_path).as_posix()]}
    code,_,body=pv.handle(route,args,'GET',b'')
    assert code==409 and json.loads(body)['reason']=='compile-root-selection-changed'
    code,_,body=pv.handle(route,{'file':args['file']},'GET',b'')
    assert code==200
    if route.endswith('pdf'):assert body==b'Exact old PDF bytes'
    else:assert json.loads(body)['ok'] and not json.loads(body)['synctex_fresh']


def test_projection_http_citation_resolves_actual_delegated_branch_not_public_decoy(tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('projection_citation',Path(__file__).resolve().parents[1]/'tools/writing_verbs/reanchor_http_routes.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=tmp_path/'src/laplace/manuscript/projection_viewer.py';path.parent.mkdir(parents=True)
    row={'name':'projection/pdf','route':'/projection/pdf','method':'GET','site':'src/laplace/projection_viewer.py:999','holds':'"/projection/pdf"'}
    body='def handle(path,query,method,body):\n    return _handle(path,query,method,body)\ndef _handle(path,query,method,body):\n    if path == "/projection/pdf" and method == "GET": pass\n'
    path.write_text(body);assert module.resolve_site(tmp_path,row).endswith(':4')
    path.write_text('# shifted\n'+body);assert module.resolve_site(tmp_path,row).endswith(':5')
    path.write_text(body.replace('return _handle','return another_owner'))
    with pytest.raises(AssertionError,match='uniquely delegate'):module.resolve_site(tmp_path,row)


@pytest.mark.skipif(not shutil.which('latexmk') or not shutil.which('synctex'),reason='local TeX toolchain unavailable')
def test_real_nested_chapter_compiles_root_and_maps_both_directions(tmp_path,monkeypatch):
    main,chapter=fixture(tmp_path,monkeypatch);file=chapter.relative_to(tmp_path).as_posix();root=main.relative_to(tmp_path).as_posix()
    code,queued=pv.recompile(file,'book','test',repo_root=tmp_path,compile_root=root)
    assert code==200 and queued['status']=='started'
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        status=pv.recompile_status(file,repo_root=tmp_path,corpus='book',compile_root=root)
        if not status['running']:break
        time.sleep(.02)
    assert status['ok'] and status['fresh'],status
    assert main.with_suffix('.pdf').is_file() and not chapter.with_suffix('.pdf').exists()
    followed=pv.follow_status(file,corpus='book',compile_root=root);assert followed['fresh'],followed
    placed=pv.synctex_locate(file,'',6,corpus='book',compile_root=root);assert 'error' not in placed,placed
    recovered=pv.synctex_anchor(file,placed['page'],placed['x'],placed['y'],corpus='book',compile_root=root)
    assert recovered['file']==file and abs(recovered['line']-6)<=2,recovered
    chapter.write_text(chapter.read_text()+'Changed after compilation.\n')
    assert not pv.follow_status(file,corpus='book',compile_root=root)['fresh']
    assert pv.synctex_locate(file,'',6,corpus='book',compile_root=root)['stale']
