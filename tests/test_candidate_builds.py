"""Real candidate staging/compiler/proof joins in tiny declared roots/state."""
import json
from pathlib import Path
import time

import pytest

from laplace.manuscript import manuscript_source, projection_viewer as compiler
from laplace.manuscript import document_templates as templates, build_targets, build_jobs


@pytest.fixture
def candidate_case(tmp_path,monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE',str(tmp_path/'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES',str(tmp_path/'workspaces'))
    manuscript=tmp_path/'book/manuscript';manuscript.mkdir(parents=True)
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}Original.\\end{document}\n')
    (manuscript/'manuscript_spec.json').write_text(json.dumps({'manuscript':{'genre':'article'}}))
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'book','project_dir':'book',
        'tex_root':'book/manuscript','manifest':{'document':{'root':'book/manuscript/main.tex'}}}]}))
    source=manuscript_source.resolve('book',repo_root=tmp_path,include_candidates=False)
    path=tmp_path/source['root']
    path.write_text('\\documentclass{custom}\n\\begin{document}\nOriginal \\fixtureword.\n\\end{document}\n')
    (path.parent/'custom.cls').write_text('\\NeedsTeXFormat{LaTeX2e}\n\\ProvidesClass{custom}\n\\LoadClass{article}\n\\RequirePackage{support}\n')
    (path.parent/'support.sty').write_text('\\ProvidesPackage{support}\n\\newcommand{\\fixtureword}{fixture}\n')
    original=path.read_bytes();selection=manuscript_source.selection_identity(source,'book')
    value=templates.change('book',{'action':'prepare','source_edits':[{'file':source['root'],'content':path.read_text().replace('Original','Reviewed')}],
        'guards':{'expected_selection':selection,'source_guards':{source['root']:templates.pin(original)}},'reason':'Synthetic source-only template preview.'},tmp_path)
    body=templates.candidate('book',value['candidate_ref'],tmp_path)['proposal']
    yield tmp_path,path,original,value,body


def settle(root,job):
    end=time.monotonic()+20
    while time.monotonic()<end:
        row=build_jobs.status(job,'book',root)
        if not row['running'] and row['state'] not in build_jobs.ACTIVE and row.get('preview_publication')!='PENDING':return row
        time.sleep(.02)
    pytest.fail('Candidate fixture build did not settle.')


def start(case):
    root,_,_,value,_=case;target=value['build_action']['payload']['build_target']
    code,result=compiler.recompile(target['root'],'book','author',repo_root=root,build_target=target)
    assert code==200,result
    return result,settle(root,result['build_job'])


def test_private_stage_warm_reuse_is_read_only_to_canonical_and_has_no_canonical_links(candidate_case):
    root,path,original,value,body=candidate_case;target=build_targets.candidate_target('book',value['candidate_ref'],body,root)
    assert not (root/target['root']).exists(),'inspection cannot eagerly create a stage'
    build_targets.stage_candidate('book',value['candidate_ref'],body,root)
    home=build_targets._candidate_home(target,body,root)
    before={p.relative_to(home).as_posix():(p.stat().st_ino,p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()}
    build_targets.stage_candidate('book',value['candidate_ref'],body,root)
    after={p.relative_to(home).as_posix():(p.stat().st_ino,p.stat().st_mtime_ns) for p in home.rglob('*') if p.is_file()}
    assert before==after and len(before)==3 and path.read_bytes()==original
    assert (root/target['root']).stat().st_ino!=path.stat().st_ino
    assert not any(p.is_symlink() for p in home.rglob('*'))


def test_real_candidate_build_has_exact_immutable_art_pdf_and_original_selection(candidate_case):
    if not compiler._latexmk_bin():pytest.skip('No installed TeX toolchain')
    root,path,original,value,body=candidate_case;_,result=start(candidate_case)
    assert result['state']=='done' and result['ok'],result
    assert result.get('preview_ref'),result
    preview=result['preview_ref'];verified=build_targets.inspect_preview('book',value['candidate_ref'],preview,root)
    assert verified['path'].read_bytes().startswith(b'%PDF') and not verified['current_input_changes']
    assert verified['receipt']['declared_input_revision']==preview['build_job']['input_revision']
    assert verified['receipt']['observed_local_inputs'] and verified['receipt']['installed_inputs']
    assert preview['build_job']['target_kind']=='candidate'
    assert preview['build_job']['selection_identity']==body['selected_source']['selection_identity']
    assert path.read_bytes()==original and manuscript_source.resolve('book',repo_root=root)['root']==body['selected_source']['root']
    assert build_targets.latest_preview('book',value['candidate_ref'],root)['preview_ref']==preview


def test_old_reviewed_build_remains_exact_after_new_build_and_canonical_drift(candidate_case,monkeypatch):
    if not compiler._latexmk_bin():pytest.skip('No installed TeX toolchain')
    root,path,original,value,body=candidate_case
    monkeypatch.setenv('SOURCE_DATE_EPOCH','946684800');monkeypatch.setenv('FORCE_SOURCE_DATE','1')
    first_start,first=start(candidate_case);proof_a=first['preview_ref'];pdf_a=build_targets.inspect_preview('book',value['candidate_ref'],proof_a,root)['path'].read_bytes()
    # Only generated cache evidence is changed; the sealed proposed inputs stay exact.
    target=first_start['build_job']['build_target'];(root/target['root']).with_suffix('.synctex.gz').unlink()
    monkeypatch.setenv('SOURCE_DATE_EPOCH','978307200')
    _,second=start(candidate_case);proof_b=second['preview_ref']
    assert proof_a['build_job']['id']!=proof_b['build_job']['id'] and proof_a['build_receipt_id']!=proof_b['build_receipt_id']
    assert proof_a['output']['content_revision']!=proof_b['output']['content_revision']
    assert build_targets.inspect_preview('book',value['candidate_ref'],proof_a,root)['path'].read_bytes()==pdf_a
    old=build_jobs.status(first_start['build_job'],'book',root)
    assert old['historical'] and old['preview_ref']==proof_a and not old['running']
    assert old['cleanup_unproved'] is False and old['cancellation']['available'] is False and 'cancel_action' not in old
    path.write_text('A later canonical change.\n')
    (path.parent/'support.sty').write_text('Changed canonical package.\n')
    historical=build_targets.inspect_preview('book',value['candidate_ref'],proof_a,root)
    assert historical['path'].read_bytes()==pdf_a and historical['current_input_changes']
    (root/proof_a['output']['file']).unlink()
    with pytest.raises(ValueError,match='unavailable'):
        build_targets.inspect_preview('book',value['candidate_ref'],proof_a,root)


def test_explicit_cache_prune_is_exact_stale_guarded_and_rebuild_only_restages(candidate_case):
    from laplace.projects import writing_storage
    from laplace.writing import records
    if not compiler._latexmk_bin():pytest.skip('No installed TeX toolchain')
    root,path,original,value,body=candidate_case;ref=value['candidate_ref'];target=value['build_action']['payload']['build_target']
    idle=build_targets.candidate_status('book',target,root)
    assert idle['stage_state']=='NOT_PREPARED' and not (root/target['root']).exists()
    _,first=start(candidate_case);proof=first['preview_ref']
    before=writing_storage.candidate_cache('book',ref,root)
    extra=(root/target['root']).with_suffix('.cleanup-race');extra.write_text('New generated cache')
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        writing_storage.prune('book',before['prune_action']['payload'],root)
    exact=writing_storage.candidate_cache('book',ref,root)
    result=writing_storage.prune('book',exact['prune_action']['payload'],root)
    assert result['removed'] and result['logical_bytes']==exact['logical_bytes']>0
    assert path.read_bytes()==original and templates.candidate('book',ref,root)['proposal']==body
    assert records.selected_journal_fields('book',proof['build_receipt_id'],root,fields=['after'])['after']
    assert build_targets.candidate_status('book',target,root)['stage_state']=='NOT_PREPARED'
    assert not (root/target['root']).exists(),'status after eviction cannot restage'
    status=build_jobs.status(proof['build_job'],'book',root)
    assert status['preview_ref'] is None and status['preview_state']=='UNAVAILABLE'
    with pytest.raises(ValueError,match='unavailable'):build_targets.inspect_preview('book',ref,proof,root)
    _,second=start(candidate_case)
    assert second['preview_ref']['build_job']['id']!=proof['build_job']['id']
    assert (root/target['root']).exists() and path.read_bytes()==original


def test_owned_candidate_cancel_preserves_previous_exact_output_and_refuses_busy_prune(candidate_case,monkeypatch):
    import sys
    from laplace.projects import writing_storage
    if not compiler._latexmk_bin():pytest.skip('No installed TeX toolchain')
    root,path,original,value,_=candidate_case;_,first=start(candidate_case);proof=first['preview_ref']
    pdf=build_targets.inspect_preview('book',value['candidate_ref'],proof,root)['path'].read_bytes()
    run=compiler._run
    def sleeping_run(cmd,cwd,timeout):
        return run([sys.executable,'-c','import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); time.sleep(60)'],cwd,timeout)
    monkeypatch.setattr(compiler,'_run',sleeping_run)
    target=value['build_action']['payload']['build_target'];code,started=compiler.recompile(target['root'],'book','author',repo_root=root,build_target=target)
    assert code==200
    end=time.monotonic()+5
    while time.monotonic()<end:
        active=build_jobs.status(started['build_job'],'book',root)
        if active['owned_processes_active']:break
        time.sleep(.02)
    assert active['owned_processes_active']
    cache=writing_storage.candidate_cache('book',value['candidate_ref'],root)
    with pytest.raises(ValueError,match='busy'):
        writing_storage.prune('book',cache['prune_action']['payload'],root)
    build_jobs.cancel(started['build_job'],'book',root)
    terminal=settle(root,started['build_job'])
    assert terminal['state']=='cancelled' and not terminal['running'] and not terminal['replacement_blocked']
    assert not terminal.get('preview_ref') and terminal.get('build_receipt_id')
    assert build_targets.inspect_preview('book',value['candidate_ref'],proof,root)['path'].read_bytes()==pdf
    assert path.read_bytes()==original


def test_preview_requires_owner_terminal_receipt_and_private_recorded_inputs(candidate_case):
    import copy
    from laplace.projects import artifacts
    from laplace.writing import records
    if not compiler._latexmk_bin():pytest.skip('No installed TeX toolchain')
    root,path,_,value,body=candidate_case;_,terminal=start(candidate_case);proof=terminal['preview_ref']
    receipt=records.selected_journal_fields('book',proof['build_receipt_id'],root,fields=['after'])['after']
    fake=artifacts.store(root,'book',{'scope':'project','path':'work/fake-preview.json','before':None,
        'content':receipt,'reason':'Untrusted copied build receipt.'})
    forged=copy.deepcopy(proof);forged['build_receipt_id']=fake['id']
    with pytest.raises(ValueError,match='unproved'):build_targets.inspect_preview('book',value['candidate_ref'],forged,root)
    target=proof['build_job']['build_target'];private=root/target['root'];row=compiler._read_recompile_status(private)
    with private.with_suffix('.fls').open('a') as output:output.write('INPUT '+str(path)+'\n')
    observation=build_targets.observe_candidate_build(private,proof['build_job'],row,root)
    assert observation['output'] is None and any(issue['code']=='CANONICAL_INPUT_FALLBACK' for issue in observation['diagnostics'])
    assert build_targets.inspect_preview('book',value['candidate_ref'],proof,root)['output']==proof['output']


def test_failed_tex_retains_diagnostic_art_without_preview_and_missing_input_cas_refuses_old_proof(candidate_case):
    from laplace.representation import writing_bodies as bodies
    if not compiler._latexmk_bin():pytest.skip('No installed TeX toolchain')
    root,path,original,value,body=candidate_case;_,first=start(candidate_case);old=first['preview_ref']
    proposed=body['source_edits'][0]['after'].replace('Reviewed',r'\UndefinedSyntheticTemplateCommand')
    bad=templates.change('book',{'action':'prepare','source_edits':[{'file':body['selected_source']['root'],'content':proposed}],
        'guards':{'expected_selection':body['selected_source']['selection_identity'],
            'source_guards':{body['selected_source']['root']:templates.pin(original)}},'reason':'Synthetic compiler failure.'},root)
    target=bad['build_action']['payload']['build_target'];code,started=compiler.recompile(target['root'],'book','author',repo_root=root,build_target=target)
    assert code==200
    failed=settle(root,started['build_job'])
    assert failed['state']=='error' and not failed['ok'] and not failed.get('preview_ref') and failed['build_receipt_id']
    assert failed['log_tail'] and path.read_bytes()==original
    verified=build_targets.inspect_preview('book',value['candidate_ref'],old,root)
    blob=verified['receipt']['observed_local_inputs'][0]['content_handle'];bodies.store(root).key_path(blob).unlink()
    with pytest.raises(ValueError,match='Retained observed local input bytes are unavailable'):
        build_targets.inspect_preview('book',value['candidate_ref'],old,root)
