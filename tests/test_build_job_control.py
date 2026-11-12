"""Exact compiler controls prove real owned-process cleanup and safe retry."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

import psutil
import pytest

from laplace.web import authoring as authoring_surface
from laplace.manuscript import manuscript_source, projection_viewer as compiler, storyboard
from laplace.native import tools as writing_tools
from laplace.manuscript import build_jobs, build_targets
from laplace.core import checkout
from test_derived_build_target import _derived_sources


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE',str(tmp_path/'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES',str(tmp_path/'workspaces'))
    plan,_,derived=_derived_sources(tmp_path)
    source=manuscript_source.resolve('book',repo_root=tmp_path)
    canonical=tmp_path/source['root']
    canonical.write_text('\\documentclass{article}\n\\begin{document}\n\\input{part}\n\\end{document}\n')
    (canonical.parent/'part.tex').write_text('Canonical tiny passage.\n')
    monkeypatch.setattr(compiler,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(storyboard,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    yield tmp_path,canonical,derived/'main.tex',plan
    shutil.rmtree(tmp_path,ignore_errors=True)


def settled(root,job):
    until=time.monotonic()+20
    while time.monotonic()<until:
        row=build_jobs.status(job,'book',root)
        if not row['running'] and row['state'] not in build_jobs.ACTIVE:return row
        time.sleep(.02)
    pytest.fail('owned fixture build did not settle')


def live(pid):
    try:return psutil.Process(pid).is_running() and psutil.Process(pid).status()!=psutil.STATUS_ZOMBIE
    except psutil.Error:return False


@pytest.mark.parametrize('kind',['manuscript','derived'])
def test_real_owned_group_cancel_retains_pdf_and_next_real_build_succeeds(project,monkeypatch,kind):
    root,canonical,derived,plan=project
    if not compiler._latexmk_bin() or not compiler._synctex_bin():pytest.skip('installed TeX toolchain unavailable')
    tex=derived if kind=='derived' else canonical
    def payload():return {'build_target':build_targets.issue('book',root)} if kind=='derived' else {}
    first=writing_tools.execute(root,'book','work','build',payload())
    assert settled(root,first['build_job'])['fresh']
    assert writing_tools.execute(root,'book','work','build',{'action':'cancel','build_job':first['build_job']})['cancel_outcome']=='already_terminal'
    previous=tex.with_suffix('.pdf').read_bytes()
    unrelated=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],cwd=root)
    original=compiler._run
    marker=tex.parent/'fixture-processes.json'
    program=r'''
import json,os,pathlib,signal,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
def stop(*args):
 child.terminate()
 child.wait(timeout=5)
 sys.exit(1)
signal.signal(signal.SIGTERM,stop)
pathlib.Path('main.pdf' if pathlib.Path('main.tex').exists() else 'Fixture-Book.pdf').write_bytes(b'partial owned output')
pathlib.Path('fixture-processes.json').write_text(json.dumps({'parent':os.getpid(),'child':child.pid}))
time.sleep(60)
'''
    monkeypatch.setattr(compiler,'_run',lambda cmd,cwd,timeout:original([sys.executable,'-c',program],cwd,timeout))
    try:
        start=writing_tools.execute(root,'book','work','build',payload())
        job=start['build_job']
        until=time.monotonic()+5
        while not marker.is_file() and time.monotonic()<until:time.sleep(.02)
        assert marker.is_file()
        pids=json.loads(marker.read_text())
        assert all(live(pid) for pid in pids.values())
        coalesced=writing_tools.execute(root,'book','work','build',payload())
        assert coalesced['coalesced'] and coalesced['build_job']==job
        # A different current basis cannot silently coalesce or disable old-job cancellation.
        if kind=='derived':plan.write_text(plan.read_text()+' ')
        else:(tex.parent/'part.tex').write_text('Changed while the old job is running.\n')
        status=writing_tools.execute(root,'book','work','build_status',{'build_job':job})
        assert status['running'] and not status['job_basis_current'] and status['build_job']==job
        with pytest.raises(ValueError,match='another input basis'):
            writing_tools.execute(root,'book','work','build',payload())
        url=urlsplit(status['job_status_read']['http']['url'])
        code,_,raw=authoring_surface.handle(url.path,parse_qs(url.query),'GET',b'')
        assert code==200 and json.loads(raw)['build_job']==job
        action=status['cancel_action']['payload']
        code,_,raw=authoring_surface.handle('/authoring/build',{},'POST',json.dumps({'project':'book',**action}).encode())
        assert code==200 and json.loads(raw)['cancel_outcome']=='requested'
        terminal=settled(root,job)
        assert terminal['state']=='cancelled' and not terminal['fresh'] and not terminal['owned_processes_active']
        assert not any(live(pid) for pid in pids.values()) and live(unrelated.pid)
        assert tex.with_suffix('.pdf').read_bytes()==previous
        assert terminal['last_successful_build']['build_job']==first['build_job']
        assert writing_tools.execute(root,'book','work','build',action)['cancel_outcome']=='already_terminal'
        monkeypatch.setattr(compiler,'_run',original)
        again=writing_tools.execute(root,'book','work','build',payload())
        assert again['build_job']['id']!=job['id'] and settled(root,again['build_job'])['fresh']
        with pytest.raises(build_jobs.JobRefused,match='superseded'):
            build_jobs.status(job,'book',root)
    finally:
        unrelated.terminate();unrelated.wait(timeout=5)
        # Failure cleanup stays bound to this fixture's exact issued owner.
        if 'job' in locals():
            try:build_jobs.cancel(job,'book',root)
            except build_jobs.JobRefused:pass


def test_preserve_pdf_requires_the_exact_primary_output_key(project):
    root,_,tex,_=project
    pdf=tex.with_suffix('.pdf');pdf.write_bytes(b'other recorded PDF bytes')
    digest=compiler._output_sha256(pdf)
    prior={'ok':True,'pdf':'different.pdf','outputs':{'files':{'different.pdf':digest}}}
    assert build_jobs.preserve_pdf(tex,prior,root) is None
    prior['outputs']['files'][pdf.relative_to(root).as_posix()]=digest
    assert build_jobs.preserve_pdf(tex,prior,root)==pdf.read_bytes()


def test_cancel_before_terminal_publication_wins_and_stopping_refuses_retry(project,monkeypatch):
    root,_,tex,_=project
    entered=threading.Event();finish=threading.Event()
    def compile_owned(*args,**kwargs):
        entered.set();assert finish.wait(5)
        return {'ok':True,'pdf':'derived/main.pdf','outputs':{},'log_tail':'controlled completion'}
    monkeypatch.setattr(compiler,'compile_tex',compile_owned)
    monkeypatch.setattr(compiler,'_latexmk_bin',lambda:sys.executable)
    target=build_targets.issue('book',root)
    start=writing_tools.execute(root,'book','work','build',{'build_target':target})
    assert entered.wait(5)
    job=start['build_job']
    try:
        cancel=build_jobs.cancel(job,'book',root)
        assert cancel['state']=='cancelling' and cancel['running']
        code,row=compiler.recompile(target['root'],'book','author',repo_root=root,build_target=target)
        assert code==409 and row['build_job']==job
    finally:finish.set()
    assert settled(root,job)['state']=='cancelled'


def test_missing_crossed_and_path_shaped_jobs_never_signal(project,monkeypatch):
    root,_,tex,_=project
    scope=compiler._compile_scope(tex,corpus='book',repo_root=root,build_target=build_targets.issue('book',root))
    job=build_jobs.issue(scope,root)
    monkeypatch.setattr(build_jobs,'_stop',lambda *args:pytest.fail('unproved process selected'))
    for bad in (job,{**job,'project':'other'},{**job,'root':'../outside.tex'}):
        with pytest.raises(build_jobs.JobRefused):build_jobs.cancel(bad,'book',root)
    code,_,raw=authoring_surface.handle('/authoring/build',{},'POST',json.dumps({'project':'book','action':'cancel','build_job':job}).encode())
    assert code==409 and json.loads(raw)['code']=='BUILD_JOB_REFUSED'


def test_abandoned_owned_process_requires_exact_recovery_before_new_launch(project,monkeypatch):
    root,_,tex,_=project
    target=build_targets.issue('book',root)
    scope=compiler._compile_scope(tex,corpus='book',repo_root=root,build_target=target)
    job=build_jobs.issue(scope,root)
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],cwd=root,start_new_session=os.name=='posix')
    from laplace.writing.child_hosts import _process_identity
    identity=_process_identity(process.pid)
    compiler._write_recompile_status(tex,{'state':'running','ok':None,'build_job':job,
        'owned_processes':[identity],
        'process_group':{'id':process.pid,'session':process.pid,'leader':identity} if os.name=='posix' else None})
    try:
        code,row=compiler.recompile(target['root'],'book','author',repo_root=root,build_target=target)
        assert code==409 and row['build_job']==job
        # Removing the configured toolchain must not remove the existing Stop handle.
        monkeypatch.setattr(compiler,'_latexmk_bin',lambda:None)
        status=compiler.recompile_status(target['root'],repo_root=root,corpus='book',build_target=target)
        assert status['running'] and status['cancel_action']['payload']['build_job']==job
        recovered=build_jobs.cancel(job,'book',root)
        assert recovered['cancel_outcome']=='recovered' and recovered['state']=='cancelled'
        assert not live(process.pid)
    finally:
        if process.poll() is None:process.kill()
        process.wait(timeout=5)


def test_pinned_status_and_supersession_serialize_without_crossed_job_state(project,monkeypatch):
    root,_,tex,_=project
    scope=compiler._compile_scope(tex,corpus='book',repo_root=root,build_target=build_targets.issue('book',root))
    old=build_jobs.issue(scope,root);new=build_jobs.issue(scope,root)
    compiler._write_recompile_status(tex,{'state':'done','ok':True,'build_job':old})
    entered=threading.Event();release=threading.Event();replaced=threading.Event();results=[]
    original=compiler.recompile_status
    def delayed(*args,**kwargs):
        entered.set();assert release.wait(5)
        return original(*args,**kwargs)
    monkeypatch.setattr(compiler,'recompile_status',delayed)
    reader=threading.Thread(target=lambda:results.append(build_jobs.status(old,'book',root)))
    def replace():
        with build_jobs.control(tex):
            compiler._write_recompile_status(tex,{'state':'running','ok':None,'build_job':new})
            replaced.set()
    reader.start();assert entered.wait(5)
    writer=threading.Thread(target=replace);writer.start()
    assert not replaced.wait(.05)
    release.set();reader.join(5);writer.join(5)
    assert replaced.is_set() and results[0]['build_job']==old and results[0]['state']=='done'
    with pytest.raises(build_jobs.JobRefused,match='superseded'):build_jobs.status(old,'book',root)


def test_wrong_birth_identity_never_terminates_reused_or_unrelated_pid(project):
    root,_,tex,_=project
    job=build_jobs.issue(compiler._compile_scope(tex,corpus='book',repo_root=root,
        build_target=build_targets.issue('book',root)),root)
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],cwd=root)
    from laplace.writing.child_hosts import _process_identity
    identity=_process_identity(process.pid)
    compiler._write_recompile_status(tex,{'state':'running','build_job':job,
        'owned_processes':[{**identity,'created_at':identity['created_at']-10}]})
    try:
        assert build_jobs.cancel(job,'book',root)['state']=='cancelled'
        assert live(process.pid)
    finally:process.terminate();process.wait(timeout=5)


def test_failed_canonical_build_keeps_actual_chapter_source_manifest(project,monkeypatch):
    root,_,_,_=project
    # Restore this fixture's real book include tree; a failed compiler recorder
    # cannot make the physically included chapter disappear from the editor.
    source=manuscript_source.resolve('book',repo_root=root)
    selected=root/source['root']
    selected.write_text('\\documentclass{book}\n\\begin{document}\n\\input{chapters/chapter-01}\n\\end{document}\n')
    from laplace.manuscript import document
    chapter='synthetics papers/book/manuscript/chapters/chapter-01.tex'
    before=document.current('book',root)
    assert chapter in {row['file'] for row in before['files']}
    monkeypatch.setattr(compiler,'compile_tex',lambda *a,**k:{'ok':False,'log_tail':'fixture compiler error','pdf':None,'outputs':None})
    monkeypatch.setattr(compiler,'_latexmk_bin',lambda:sys.executable)
    job=writing_tools.execute(root,'book','work','build',{})['build_job']
    assert settled(root,job)['state']=='error'
    (selected.with_suffix('.fls')).write_text('INPUT missing.tex\n')
    after=document.current('book',root)
    assert after['status']=='FAILED' and chapter in {row['file'] for row in after['files']}


def test_unpublished_job_never_starts_compiler(project,monkeypatch):
    root,_,tex,_=project
    target=build_targets.issue('book',root)
    monkeypatch.setattr(compiler,'_latexmk_bin',lambda:sys.executable)
    monkeypatch.setattr(compiler,'_write_recompile_status',lambda *args:None)
    monkeypatch.setattr(compiler,'compile_tex',lambda *a,**k:pytest.fail('unpublished compiler launched'))
    code,row=compiler.recompile(target['root'],'book','author',repo_root=root,build_target=target)
    assert code==409 and 'durably published' in row['reason']
    assert not compiler._recompile_running(tex)


@pytest.mark.skipif(os.name!='posix',reason='POSIX session ownership adversary')
@pytest.mark.parametrize('recorded_child_witness',[False,True])
def test_dead_leader_group_requires_live_recorded_birth_witness(project,recorded_child_witness):
    root,_,tex,_=project
    target=build_targets.issue('book',root)
    job=build_jobs.issue(compiler._compile_scope(tex,corpus='book',repo_root=root,build_target=target),root)
    program='import subprocess,sys; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); print(p.pid,flush=True)'
    parent=subprocess.Popen([sys.executable,'-c',program],cwd=root,start_new_session=True,stdout=subprocess.PIPE,text=True)
    raw,_=parent.communicate(timeout=5)
    child=int(raw.strip())
    from laplace.writing.child_hosts import _process_identity
    child_birth=_process_identity(child)
    stale_leader={'pid':parent.pid,'created_at':0.0}
    row={'state':'running','build_job':job,'owned_processes':[stale_leader,*([child_birth] if recorded_child_witness else [])],
        'process_group':{'id':parent.pid,'session':parent.pid,'leader':stale_leader}}
    compiler._write_recompile_status(tex,row)
    before=compiler._recompile_status_path(tex).read_bytes()
    try:
        assert live(child)
        assert compiler.recompile(target['root'],'book','author',repo_root=root,build_target=target)[0]==409
        if recorded_child_witness:
            assert build_jobs.capability(row)['available']
            assert build_jobs.cancel(job,'book',root)['state']=='cancelled'
            assert not live(child)
        else:
            assert not build_jobs._members(row) and not build_jobs.capability(row)['available']
            with pytest.raises(build_jobs.JobRefused,match='cleanup is unproved'):
                build_jobs.cancel(job,'book',root)
            assert compiler._recompile_status_path(tex).read_bytes()==before and live(child)
            status=build_jobs.status(job,'book',root)
            assert status['replacement_blocked'] and not status['owned_processes_active']
            assert 'cancel_action' not in status and not status['cancellation']['available'] and status['cleanup_unproved']
    finally:
        try:psutil.Process(child).kill()
        except psutil.Error:pass


def test_unavailable_platform_preserves_build_but_cancel_refuses_before_mutation(project,monkeypatch):
    root,_,tex,_=project
    monkeypatch.setattr(build_jobs,'contained_platform',lambda:False)
    monkeypatch.setattr(compiler,'_latexmk_bin',lambda:sys.executable)
    monkeypatch.setattr(compiler,'compile_tex',lambda *a,**k:{'ok':False,'pdf':None,'outputs':None,'log_tail':'ordinary controlled failed build'})
    target=build_targets.issue('book',root)
    started=writing_tools.execute(root,'book','work','build',{'build_target':target})
    assert started['status']=='started' and not started['cancellation']['available']
    assert 'cancel_action' not in started
    job=started['build_job'];assert settled(root,job)['state']=='error'
    before=compiler._recompile_status_path(tex).read_bytes()
    monkeypatch.setattr(build_jobs,'_stop',lambda *a:pytest.fail('unavailable cancellation signalled a process'))
    with pytest.raises(build_jobs.JobRefused,match='unavailable on this platform'):
        writing_tools.execute(root,'book','work','build',{'action':'cancel','build_job':job})
    code,_,raw=authoring_surface.handle('/authoring/build',{},'POST',json.dumps({'project':'book','action':'cancel','build_job':job}).encode())
    assert code==409 and json.loads(raw)['code']=='CANCELLATION_UNAVAILABLE'
    assert compiler._recompile_status_path(tex).read_bytes()==before


def test_unproved_cleanup_blocks_replacement_even_without_live_known_pid(project):
    root,_,tex,_=project
    target=build_targets.issue('book',root)
    job=build_jobs.issue(compiler._compile_scope(tex,corpus='book',repo_root=root,build_target=target),root)
    compiler._write_recompile_status(tex,{'state':'error','ok':False,'build_job':job,'cleanup_unproved':True})
    status=build_jobs.status(job,'book',root)
    assert status['replacement_blocked'] and not status['cancellation']['available']
    assert compiler.recompile(target['root'],'book','author',repo_root=root,build_target=target)[0]==409
