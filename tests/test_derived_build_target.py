"""Current target admission and recorded PDF custody use the same build owner."""
import hashlib
import json
import shutil
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from laplace.web import authoring as authoring_surface
from laplace.manuscript import projection_viewer as compiler, storyboard
from laplace.native import tools as writing_tools
from laplace.manuscript import build_targets
from laplace.core import checkout
from test_manuscript_structure import _section_fixture


def _derived_sources(tmp_path):
    manuscript,canonical,_ = _section_fixture(tmp_path)
    plan_path = manuscript/'projection_plan.json'
    plan = json.loads(plan_path.read_text())
    plan['meta']['target_dir'] = 'derived'
    plan_path.write_text(json.dumps(plan))
    output = tmp_path/'derived'
    output.mkdir()
    (output/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n\\input{part}\n\\end{document}\n')
    (output/'part.tex').write_text('Derived passage.\n')
    return plan_path,canonical,output


@pytest.fixture
def derived(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE',str(tmp_path/'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES',str(tmp_path/'workspaces'))
    plan_path,canonical,output = _derived_sources(tmp_path)
    monkeypatch.setattr(compiler,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(storyboard,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    monkeypatch.setattr(compiler,'_latexmk_bin',lambda:'/fixture/latexmk')
    monkeypatch.setattr(compiler,'_synctex_fresh',lambda pdf:True)
    outcome = {'ok':True}
    def compile_owned(file, *, repo_root, _prior_status, _scope):
        assert _scope['corpus']=='book'
        assert _scope['build_target']['root']=='derived/main.tex'
        if outcome['ok']:
            (output/'main.pdf').write_bytes(b'%PDF-1.4\nfixture exact derived output\n')
            (output/'main.synctex').write_text('fixture map')
            return {'ok':True,'pdf':'derived/main.pdf','log_tail':'fixture success',
                    'outputs':compiler._build_output_snapshot(output/'main.tex',tmp_path)}
        return {'ok':False,'pdf':None,'log_tail':'fixture deliberate compile failure','outputs':None}
    monkeypatch.setattr(compiler,'compile_tex',compile_owned)
    yield tmp_path,plan_path,canonical,outcome
    shutil.rmtree(tmp_path,ignore_errors=True)


def settle(root,target):
    end = time.monotonic()+3
    while time.monotonic()<end:
        value = compiler.recompile_status(target['root'],repo_root=root,corpus='book',build_target=target)
        if not value['running']:
            return value
        time.sleep(.01)
    pytest.fail('fixture compile did not settle')


def test_issued_target_closes_registered_derived_compile_and_exact_pdf_read(derived):
    root,_,canonical,_ = derived
    before = canonical.read_bytes()
    target = build_targets.issue('book',root)
    with pytest.raises(compiler.CompileRootRefused,match='not a proved member'):
        compiler._compile_scope(root/target['root'],corpus='book',repo_root=root)
    start = writing_tools.execute(root,'book','work','build',{'build_target':target})
    assert start['build_target']==target and start['corpus']=='book'
    assert settle(root,target)['fresh']
    status_read=writing_tools.execute(root,'book','work','build_status',{'build_target':target})
    assert status_read['project']=='book' and status_read['build_target']==target
    view = writing_tools.execute(root,'book','work','document',{'target_kind':'derived'})
    assert view['build_target']==target and view['status']=='READY'
    assert view['pdf_read']['build_target']==target and view['pdf_read']['current']
    url = urlsplit(view['pdf_read']['http']['url'])
    status,mime,raw = compiler.handle(url.path,parse_qs(url.query),'GET',b'')
    assert (status,mime)==(200,'application/pdf')
    assert 'sha256:'+hashlib.sha256(raw).hexdigest()==view['pdf_read']['content_revision']
    assert canonical.read_bytes()==before


@pytest.mark.parametrize('change',['plan','source','crossed'])
def test_changed_or_crossed_target_refuses_before_compiler_effect(derived, monkeypatch, change):
    root,plan_path,_,_ = derived
    target = build_targets.issue('book',root)
    if change=='plan':
        plan_path.write_text(plan_path.read_text()+' ')
    elif change=='source':
        (root/'derived/part.tex').write_text('Concurrent derived input edit.\n')
    else:
        target = {**target,'project':'other'}
    monkeypatch.setattr(compiler,'compile_tex',lambda *a,**k:pytest.fail('compiler started'))
    with pytest.raises(build_targets.TargetRefused):
        writing_tools.execute(root,'book','work','build',{'build_target':target})
    assert not compiler._recompile_status_path(root/'derived/main.tex').exists()


def test_failed_attempt_retains_exact_successful_pdf_and_old_input_basis(derived):
    root,_,_,outcome = derived
    first = build_targets.issue('book',root)
    compiler.recompile(first['root'],'book','author',repo_root=root,build_target=first)
    settle(root,first)
    old = build_targets.read('book',root)['pdf_read']
    (root/'derived/part.tex').write_text('Now has a deliberate compiler error.\n')
    target = build_targets.issue('book',root)
    assert target['input_revision']!=first['input_revision']
    outcome['ok'] = False
    compiler.recompile(target['root'],'book','author',repo_root=root,build_target=target)
    assert settle(root,target)['ok'] is False
    view = build_targets.read('book',root)
    assert view['status']=='FAILED' and not view['pdf_read']['current']
    assert view['pdf_read']['http']['url']==old['http']['url']
    assert not view['recorded_output']['inputs_current']
    url = urlsplit(old['http']['url'])
    assert compiler.handle(url.path,parse_qs(url.query),'GET',b'')[0]==200
    (root/'derived/main.pdf').write_bytes(b'changed after inspection')
    status,_,raw = compiler.handle(url.path,parse_qs(url.query),'GET',b'')
    assert status==409 and 'not served' in json.loads(raw)['error']


def test_legacy_storyboard_compile_and_native_http_use_same_issued_target(derived, monkeypatch):
    root,_,_,_ = derived
    target = build_targets.issue('book',root)
    called = []
    def admit(file,project,by,**kwargs):
        called.append((file,project,kwargs['build_target']))
        return 200,{'status':'started','build_target':kwargs['build_target']}
    monkeypatch.setattr(compiler,'recompile',admit)
    status,reply = storyboard.run_launch('book','projection-compile','author',armed=True)
    assert status==200 and reply['build_target']==target
    payload = {'project':'book','build_target':target}
    assert authoring_surface.handle('/authoring/build',{},'POST',json.dumps(payload).encode())[0]==200
    writing_tools.execute(root,'book','work','build',{'build_target':target})
    assert called==[('derived/main.tex','book',target)]*3


def test_no_declared_derived_output_is_a_separate_unavailable_read(derived):
    root,plan_path,_,_ = derived
    plan = json.loads(plan_path.read_text())
    plan['meta'].pop('target_dir')
    plan_path.write_text(json.dumps(plan))
    result = writing_tools.execute(root,'book','work','document',{'target_kind':'derived'})
    assert result['status']=='UNAVAILABLE' and 'pdf_read' not in result
    assert result['reason_code']=='NOT_CONFIGURED'
    canonical = writing_tools.execute(root,'book','work','document',{})
    assert canonical['selected_source']['status']=='resolved'


def test_new_recorder_discovery_is_not_an_authored_target_change(derived):
    root,_,_,_ = derived
    target = build_targets.issue('book',root)
    (root/'derived/main.fls').write_text('INPUT main.tex\nINPUT part.tex\n')
    assert build_targets.issue('book',root)==target


def test_missing_declared_output_is_neutral_but_invalid_plan_is_not(derived):
    root,plan_path,_,_=derived
    (root/'derived/main.tex').unlink()
    assert build_targets.read('book',root)['reason_code']=='NOT_PREPARED'
    plan_path.write_text('{invalid plan bytes')
    assert build_targets.read('book',root)['reason_code']=='INVALID_TARGET'


@pytest.mark.parametrize('kind',['paper','book'])
def test_actual_app_created_source_only_scaffold_has_neutral_unprepared_output(derived,kind):
    from laplace.projects import library as writing_projects
    root,_,_,_=derived
    code,value=writing_projects.create({'name':'empty-'+kind,'title':'Empty '+kind,'kind':kind},root)
    assert code==201,value
    assert storyboard._load_plan('empty-'+kind,root)[1]['meta']['target_dir']
    result=build_targets.read('empty-'+kind,root)
    assert result['status']=='UNAVAILABLE' and result['reason_code']=='NOT_CONFIGURED'
    declared=storyboard._load_plan('empty-'+kind,root)[1]['meta']['target_dir']
    (root/declared).mkdir(parents=True,exist_ok=True)
    (root/declared/'main.tex').write_text('Scaffold with no reader sections, including unresolved inputs.\n\\input{not-present}\n')
    assert build_targets.read('empty-'+kind,root)['reason_code']=='NOT_CONFIGURED'
    canonical=writing_tools.execute(root,'empty-'+kind,'work','document',{})
    assert canonical['selected_source']['status']=='resolved'
