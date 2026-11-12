"""Exact source, archive, feedback and follow identities without model/build work."""
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from laplace.manuscript import projection_viewer as pv, review_surface as rv, manuscript_source
from laplace.work import history as author_history
from laplace.manuscript import manuscript_versions
from laplace.pipeline import registry


def fixture(root, monkeypatch):
    md=root/'project/manuscript';md.mkdir(parents=True)
    (md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nCurrent source words.\n\\end{document}\n')
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'book','project_dir':'project','tex_root':'project/manuscript'}]}))
    monkeypatch.setattr(pv,'_repo_root',lambda:root)
    monkeypatch.setattr(rv,'_repo_root',lambda:root)
    monkeypatch.setattr(pv,'_recompile_status_path',lambda path:root/'controlled-build.status.json')
    monkeypatch.setattr(pv,'_recompile_lock_path',lambda path:root/'controlled-build.lock')
    return md


def save(root,path,data,actor='author',guard=None):
    expected=guard or 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
    status,_type,raw=pv.handle('/projection/tex',{'file':[path.relative_to(root).as_posix()],
        'corpus':['book'],'expected_selection':[manuscript_source.selection_identity(manuscript_source.resolve('book',root))],'bank':['editor'],'author':[actor],'surface':['edit'],'expected_source_digest':[expected]},'POST',data)
    return status,json.loads(raw)


def test_unchanged_save_ack_only_across_rotating_files_actors_and_over_retention(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch)
    paths=[md/f'fragment-{index}.tex' for index in range(40)]
    for path in paths:path.write_bytes(b'Unchanged source.\r\n')
    main=md/'main.tex';main.write_text(main.read_text().replace('\\end{document}', ''.join('\\input{'+p.stem+'}\n' for p in paths)+'\\end{document}'))
    before={p:(p.stat().st_ino,p.stat().st_mtime_ns,p.read_bytes()) for p in paths}
    for actor in ('author','eigen:fixture'):
        for path in paths:
            status,result=save(tmp_path,path,path.read_bytes(),actor)
            assert status==200 and result['changed'] is False and result['source_committed']
            assert not result['banked'] and not result['exemplar']['banked']
            assert 'version_id' not in result
    assert not (md/'editor_saves').exists() and not (md/'feedback').exists()
    assert not (md/'whitepaper').exists()
    assert before=={p:(p.stat().st_ino,p.stat().st_mtime_ns,p.read_bytes()) for p in paths}
    # No-change matching after bytes cannot bypass an uninspected/stale guard.
    status,result=save(tmp_path,paths[0],paths[0].read_bytes(),guard='sha256:'+'0'*64)
    assert status==409 and result['reason']=='source-revision-conflict'


def test_actual_changes_and_explicit_restore_remain_distinct_occurrences(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch);path=md/'main.tex';original=path.read_bytes()
    changed=original.replace(b'Current source words.',b'Changed source words.')
    one_status,one=save(tmp_path,path,changed);two_status,two=save(tmp_path,path,original)
    assert one_status==two_status==200 and one['changed'] and two['changed']
    assert one['version_id']!=two['version_id'] and one['exemplar']['exemplar_id']!=two['exemplar']['exemplar_id']
    current=md/'feedback/feedback.jsonl';pipeline=md/'whitepaper/feedback/feedback.jsonl'
    rows=[json.loads(line) for line in current.read_text().splitlines()]
    assert len(rows)==2 and not pipeline.exists()
    assert rows[0]['hunks']==[{'start':3,'end':3,'before':['Current source words.'],'after':['Changed source words.']}]
    assert rows[0]['baseline']['kind']=='guarded-save-preimage'
    assert 'author\'s hand' not in rows[0]['text']
    # Existing explicit archive and restore occurrences still mint, even equal bodies.
    archived=pv.bank_editor_save(md,path,original,author='author',surface='explicit-archive')
    restored=pv.restore_editor_save('book',str(path),archived['version_id'],pv._source_observation(path)['expected_source_digest'],manuscript_source.selection_identity(manuscript_source.resolve('book',tmp_path)))
    assert restored['ok'] and restored['version_id']!=archived['version_id']
    assert len(pv._load_saves_index(md)['saves'])==4


def test_project_context_resolves_explicit_root_and_separates_feedback_scopes(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch)
    # No patch to registry's default root: supplied root must own the lookup.
    context=registry.project_context('book',tmp_path)
    assert context.feedback_ledger==md/'feedback/feedback.jsonl'
    assert context.pipeline_feedback_ledger==md/'whitepaper/feedback/feedback.jsonl'
    assert registry.resolve('book',tmp_path).feedback_ledger=='project/manuscript/whitepaper/feedback/feedback.jsonl'
    assert rv._exemplar_ledger('book',tmp_path)==context.feedback_ledger
    assert registry.project_context('../book',tmp_path) is None


def test_read_only_source_uses_existing_engine_storage_fence(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch);data=json.loads((tmp_path/'registry_projects.json').read_text())
    data['projects'][0]['manifest']={'document':{'root':'project/manuscript/main.tex','read_only':True,'state_dir':'engine-state/book'}}
    (tmp_path/'registry_projects.json').write_text(json.dumps(data))
    context=registry.project_context('book',tmp_path)
    assert context.feedback_ledger==tmp_path/'engine-state/book/feedback/feedback.jsonl'
    assert context.storage_dir==tmp_path/'engine-state/book'
    data['projects'][0]['manifest']['document']['state_dir']='../outside'
    (tmp_path/'registry_projects.json').write_text(json.dumps(data))
    assert registry.project_context('book',tmp_path).feedback_ledger is None


def test_exact_saved_identity_shared_by_rail_detail_restore_and_legacy_unproved(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch);(md/'nested').mkdir();path=md/'nested/main.tex';path.write_bytes(b'Exact nested source.')
    man=pv.bank_editor_save(md,path,path.read_bytes(),author='actual-saver',surface='editor')
    rows,_=manuscript_versions._editor_save_rows(md,tmp_path);assert rows[0]['source_binding']=='BOUND' and rows[0]['body_status']=='NOT_OBSERVED'
    items,records,_=author_history._editor_save_items('book',tmp_path)
    item=items[0];row=records[man['version_id']]
    detail=author_history._detail('editor-save',row,item,tmp_path)
    assert next(h for h in detail['hashes'] if h['label']=='Current manuscript file')['status']=='current'
    (md/'main.tex').write_bytes(b'Different same-basename source.')
    path.write_bytes(b'Current changed nested source.')
    assert next(h for h in author_history._detail('editor-save',row,item,tmp_path)['hashes'] if h['label']=='Current manuscript file')['status']=='changed'
    assert not pv.restore_editor_save('book',str(md/'main.tex'),man['version_id'],pv._source_observation(md/'main.tex')['expected_source_digest']).get('ok')
    manifest_path=md/'editor_saves'/man['version_id']/'VERSION.json';legacy=json.loads(manifest_path.read_text());legacy.pop('source_file');manifest_path.write_text(json.dumps(legacy))
    index=pv._load_saves_index(md);index['saves'][0].pop('source_file');index['saves'][0].pop('bytes');pv._write_saves_index(md,index)
    assert pv.read_editor_save(md,man['version_id'])['source_binding']=='UNPROVED'
    assert pv.restore_editor_save('book',str(path),man['version_id'],pv._source_observation(path)['expected_source_digest'])['reason']=='saved-source-target-unproved'


def test_concurrent_exemplar_ids_mint_inside_existing_feedback_append_lock(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch);path=md/'main.tex';start=threading.Barrier(2)
    def bank(index):
        start.wait()
        return rv.bank_exemplar('book',path.relative_to(tmp_path).as_posix(),author='author',root=tmp_path,
            before=b'Original.',after=('Changed '+str(index)+'.').encode())
    with ThreadPoolExecutor(2) as pool:
        one=pool.submit(bank,1);two=pool.submit(bank,2);results=[one.result(),two.result()]
    assert all(row['banked'] for row in results) and len({r['exemplar_id'] for r in results})==2


def test_missing_or_unbound_baseline_never_claims_whole_file_authorship(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(manuscript_versions,'versions_payload',lambda *a:{'rows':[{'kind':'round','id':'old','paths':['archive/main.tex']}]})
    result=rv.hand_hunks('book','project/manuscript/main.tex',tmp_path)
    assert not result['attributed'] and not result['whole_file'] and result['hunks']==[]
    assert not rv.bank_exemplar('book','project/manuscript/main.tex',author='author',root=tmp_path)['banked']


def test_follow_uses_exact_producer_inputs_map_outputs_not_source_mtime(tmp_path,monkeypatch):
    from laplace.manuscript import tex_dependencies
    md=fixture(tmp_path,monkeypatch);tex=md/'main.tex';pdf=tex.with_suffix('.pdf');syn=tex.with_suffix('.synctex.gz')
    pdf.write_bytes(b'Controlled PDF output');syn.write_bytes(b'Controlled SyncTeX output')
    now=time.time();os.utime(pdf,(now-10,now-10));os.utime(syn,(now-9,now-9))
    outputs=pv._build_output_snapshot(tex,tmp_path,producer=False)
    receipt={'state':'done','ok':True,'dependencies':tex_dependencies.snapshot(tex,tmp_path),'outputs':outputs}
    pv._write_recompile_status(tex,receipt)
    os.utime(tex,(now,now))
    assert pv.recompile_status(tex.relative_to(tmp_path).as_posix(),repo_root=tmp_path)['fresh']
    assert pv._follow_fresh(pdf,tex)==(True,'')
    syn.write_bytes(b'Different current map.')
    assert not pv._follow_fresh(pdf,tex)[0]
    syn.write_bytes(b'Controlled SyncTeX output')
    tex.write_bytes(tex.read_bytes().replace(b'Current',b'Changed'))
    assert not pv._follow_fresh(pdf,tex)[0]
    # A PDF-only/legacy receipt cannot certify a map, even with convenient mtimes.
    pv._write_recompile_status(tex,{'state':'done','ok':True,'dependencies':tex_dependencies.snapshot(tex,tmp_path),
        'outputs':{'version':1,'root':tex.relative_to(tmp_path).as_posix(),'files':{pdf.relative_to(tmp_path).as_posix():pv._output_sha256(pdf)}}})
    assert not pv._follow_fresh(pdf,tex)[0]


def test_machine_baseline_uses_recorded_occurrences_not_same_second_directory_sort(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch);path=md/'main.tex'
    monkeypatch.setattr(pv.observe,'now_iso',lambda:'2026-10-08T01:01:01Z')
    original=pv.time.strftime
    monkeypatch.setattr(pv.time,'strftime',lambda fmt,*args:'2026-10-08_010101' if fmt=='%Y-%m-%d_%H%M%S' else original(fmt,*args))
    saves=[]
    for number in range(1,13):
        data=f'Machine occurrence {number}.\n'.encode();path.write_bytes(data)
        saves.append(pv.bank_editor_save(md,path,data,author='eigen:fixture',surface='machine'))
    assert saves[-1]['version_id'].endswith('-12')
    rows,_=manuscript_versions._editor_save_rows(md,tmp_path)
    assert rows[0]['id']==saves[-1]['version_id']
    hand=rv.hand_hunks('book',path.relative_to(tmp_path).as_posix(),tmp_path)
    assert hand['attributed'] and hand['baseline']['id']==saves[-1]['version_id'] and not hand['hunks']
    assert not rv.bank_exemplar('book',path.relative_to(tmp_path).as_posix(),author='author',root=tmp_path)['banked']


@pytest.mark.parametrize('damage',['corrupt-body','missing-body','duplicate-index','changed-manifest','changed-actor','changed-target'])
def test_newest_applicable_invalid_baseline_is_unproved_not_older_success(tmp_path,monkeypatch,damage):
    md=fixture(tmp_path,monkeypatch);path=md/'main.tex'
    old=pv.bank_editor_save(md,path,b'Older machine source.\n',author='eigen:fixture',surface='machine')
    newest=b'Newest machine source.\n';path.write_bytes(newest)
    saved=pv.bank_editor_save(md,path,newest,author='eigen:fixture',surface='machine')
    directory=md/'editor_saves'/saved['version_id']
    if damage=='corrupt-body':(directory/path.name).write_bytes(b'Corrupted newest body.')
    elif damage=='missing-body':(directory/path.name).unlink()
    elif damage=='duplicate-index':
        index=pv._load_saves_index(md);index['saves'].append(dict(index['saves'][-1]));pv._write_saves_index(md,index)
    elif damage=='changed-manifest':
        manifest=json.loads((directory/'VERSION.json').read_text());manifest['sha']=old['sha'];(directory/'VERSION.json').write_text(json.dumps(manifest))
    elif damage=='changed-actor':
        manifest=json.loads((directory/'VERSION.json').read_text());manifest['author']='author';(directory/'VERSION.json').write_text(json.dumps(manifest))
    else:
        (md/'other').mkdir();(md/'other/main.tex').write_bytes(b'Unrelated fenced source.')
        manifest=json.loads((directory/'VERSION.json').read_text());manifest['source_file']='project/manuscript/other/main.tex';(directory/'VERSION.json').write_text(json.dumps(manifest))
        with pytest.raises(ValueError,match='occurrence identity'):
            pv.read_editor_save(md,saved['version_id'])
        other=md/'other/main.tex';other_before=other.read_bytes()
        refused=pv.restore_editor_save('book',str(other),saved['version_id'],pv._source_observation(other)['expected_source_digest'])
        assert refused['status']==409 and refused['reason']=='saved-source-identity-unproved' and other.read_bytes()==other_before
    before={str(p):p.read_bytes() for p in md.rglob('*') if p.is_file()}
    hand=rv.hand_hunks('book',path.relative_to(tmp_path).as_posix(),tmp_path)
    assert hand['ok'] and not hand['attributed'] and hand['baseline'] is None and hand['hunks']==[]
    assert not rv.bank_exemplar('book',path.relative_to(tmp_path).as_posix(),author='author',root=tmp_path)['banked']
    assert before=={str(p):p.read_bytes() for p in md.rglob('*') if p.is_file()}


def test_baseline_filters_unrelated_archive_metadata_before_opening_body(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch);target=md/'main.tex';other=md/'other.tex';other.write_bytes(b'Other machine source.')
    selected=pv.bank_editor_save(md,target,target.read_bytes(),author='eigen:fixture',surface='machine')
    unrelated=pv.bank_editor_save(md,other,other.read_bytes(),author='eigen:fixture',surface='machine')
    # Even a corrupt unrelated body does not obstruct or get read for target attribution.
    (md/'editor_saves'/unrelated['version_id']/other.name).write_bytes(b'Corrupt unrelated bytes.')
    read=pv.read_editor_save;body_reads=[]
    def observe(md,vid,**kwargs):
        if kwargs.get('read_body',True):body_reads.append(vid)
        return read(md,vid,**kwargs)
    monkeypatch.setattr(pv,'read_editor_save',observe)
    hand=rv.hand_hunks('book',target.relative_to(tmp_path).as_posix(),tmp_path)
    assert hand['attributed'] and not hand['hunks'] and body_reads==[selected['version_id']]


def test_incomplete_rail_cannot_assert_latest_baseline(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch);target=md/'main.tex'
    pv.bank_editor_save(md,target,target.read_bytes(),author='eigen:fixture',surface='machine')
    rows,_=manuscript_versions._editor_save_rows(md,tmp_path)
    monkeypatch.setattr(manuscript_versions,'versions_payload',lambda *a:{'rows':rows,'truncated':True})
    hand=rv.hand_hunks('book',target.relative_to(tmp_path).as_posix(),tmp_path)
    assert not hand['attributed'] and hand['hunks']==[] and 'incomplete' in hand['note']


def test_historical_index_without_target_pin_is_preserved_unproved_until_new_occurrence(tmp_path,monkeypatch):
    md=fixture(tmp_path,monkeypatch);target=md/'main.tex'
    saved=pv.bank_editor_save(md,target,target.read_bytes(),author='eigen:fixture',surface='machine')
    index=pv._load_saves_index(md);index['saves'][-1].pop('source_file');index['saves'][-1].pop('bytes');pv._write_saves_index(md,index)
    retained=(md/'editor_saves/index.json').read_bytes()
    assert not rv.hand_hunks('book',target.relative_to(tmp_path).as_posix(),tmp_path)['attributed']
    assert (md/'editor_saves/index.json').read_bytes()==retained
    current=pv.bank_editor_save(md,target,target.read_bytes(),author='eigen:fixture',surface='machine')
    hand=rv.hand_hunks('book',target.relative_to(tmp_path).as_posix(),tmp_path)
    assert hand['attributed'] and hand['baseline']['id']==current['version_id'] and not hand['hunks']
    assert 'source_file' not in pv._load_saves_index(md)['saves'][0]
