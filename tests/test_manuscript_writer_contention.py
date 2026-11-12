"""Real source owners contend and compensate under the same physical scope."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading
import json

import pytest

from laplace.web import authoring as authoring_surface
from laplace.manuscript import blocks as manuscript_blocks, manuscript_source, review_surface
from laplace.writing import records as writing_records
from laplace.manuscript import source_effects
from laplace.manuscript import source_application
from laplace.writing import session_reads
from laplace.writing.records import _fold as records_fold
from laplace.writing import records as writing_records
from laplace.manuscript import source_application
from laplace.manuscript import manuscript_structure
from laplace.core import checkout
from test_manuscript_blocks import _fixture as block_fixture, _digest
from test_manuscript_structure import _section_fixture
from test_writing_controller import _import_project, _seed_revision, _apply_fixture


def _observe_wait(monkeypatch, target):
    original = manuscript_source.source_mutation
    worker = []
    waiting = threading.Event()
    @contextmanager
    def observe(paths, **kwargs):
        paths = tuple(paths)
        if worker and threading.get_ident() == worker[0] and target in paths:
            waiting.set()
        with original(paths, **kwargs) as lease:
            yield lease
    monkeypatch.setattr(manuscript_source, 'source_mutation', observe)
    selection_scope = manuscript_source.selection_mutation
    @contextmanager
    def observe_selection(*args, **kwargs):
        if worker and threading.get_ident() == worker[0]:waiting.set()
        with selection_scope(*args, **kwargs):yield
    monkeypatch.setattr(manuscript_source, 'selection_mutation', observe_selection)
    return worker, waiting


def _rewrite(manuscript, project, file, before, after, line=1):
    return review_surface.adjudicate(manuscript, project, {'verb':'rewrite', 'by':'other-author',
        'file':file, 'line_start':line, 'line_end':line, 'before':before, 'after':after,
        'expected_selection':manuscript_source.observation(project,review_surface._repo_root())['selection_identity']})


def test_proposal_file_effect_and_ordinary_disjoint_write_preserve_both(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path, files={'main.tex':
        '\\documentclass{article}\n\\begin{document}\nFirst paragraph.\nSecond paragraph.\n\\end{document}\n'})
    turn = _seed_revision(tmp_path, 'fixture', [{'file':'main.tex','line_start':3,'line_end':3,
        'before':'First paragraph.','after':'Accepted first paragraph.','reason':'requested'}])
    monkeypatch.setattr(review_surface, '_repo_root', lambda:tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = review_surface._adjudicate
    def pause(*args, **kwargs):
        if args[2].get('by') == 'author:accepted-model':
            entered.set()
            assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(review_surface, '_adjudicate', pause)
    worker, waiting = _observe_wait(monkeypatch, manuscript/'main.tex')
    def other():
        worker.append(threading.get_ident())
        return _rewrite(manuscript,'fixture','main.tex','Second paragraph.','Other author paragraph.',4)
    with ThreadPoolExecutor(2) as pool:
        applied = pool.submit(_apply_fixture, tmp_path, {'turn_id':turn})
        assert entered.wait(2)
        second = pool.submit(other)
        assert waiting.wait(1) and not second.done()
        release.set()
        assert applied.result(timeout=4)['complete']
        assert second.result(timeout=4)['applied']
    assert 'Accepted first paragraph.\nOther author paragraph.' in (manuscript/'main.tex').read_text()


def test_raw_source_save_waits_for_proposal_then_refuses_its_old_basis(tmp_path, monkeypatch):
    from laplace.manuscript import projection_viewer
    manuscript, _ = _import_project(tmp_path)
    target = manuscript/'main.tex'
    observed = projection_viewer._source_observation(target)
    turn = _seed_revision(tmp_path, 'fixture', [{'file':'main.tex','line_start':3,'line_end':3,
        'before':'Original prose.','after':'Accepted source.','reason':'requested'}])
    monkeypatch.setattr(review_surface, '_repo_root', lambda:tmp_path)
    monkeypatch.setattr(projection_viewer, '_repo_root', lambda:tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = review_surface._adjudicate
    def pause(*args, **kwargs):
        if args[2].get('by') == 'author:accepted-model':
            entered.set()
            assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(review_surface, '_adjudicate', pause)
    worker, waiting = _observe_wait(monkeypatch, target)
    selection_scope = manuscript_source.selection_mutation
    @contextmanager
    def observe_selection(*args, **kwargs):
        if worker and threading.get_ident() == worker[0]:waiting.set()
        with selection_scope(*args, **kwargs):yield
    monkeypatch.setattr(manuscript_source, 'selection_mutation', observe_selection)
    selection = manuscript_source.selection_identity(manuscript_source.resolve('fixture', tmp_path))
    def raw_save():
        worker.append(threading.get_ident())
        return projection_viewer.handle('/projection/tex', {
            'file':[target.relative_to(tmp_path).as_posix()],
            'expected_source_digest':[observed['expected_source_digest']], 'corpus':['fixture'], 'expected_selection':[selection], 'author':['fixture']}, 'POST',
            observed['content'].replace('Original prose.', 'Unreviewed raw draft.').encode())
    with ThreadPoolExecutor(2) as pool:
        accepted = pool.submit(_apply_fixture, tmp_path, {'turn_id':turn})
        assert entered.wait(2)
        raw = pool.submit(raw_save)
        assert waiting.wait(1) and not raw.done()
        release.set()
        assert accepted.result(timeout=4)['complete']
        status, _, body = raw.result(timeout=4)
    assert status == 409 and json.loads(body)['reason'] == 'source-revision-conflict'
    assert target.read_text() == observed['content'].replace('Original prose.', 'Accepted source.')


def test_block_multifile_compensation_finishes_before_waiting_source_writer(tmp_path, monkeypatch):
    manuscript, figure = block_fixture(tmp_path)
    monkeypatch.setattr(review_surface, '_repo_root', lambda:tmp_path)
    origin, destination = manuscript/'chapter.tex', manuscript/'other.tex'
    entered, release = threading.Event(), threading.Event()
    original = manuscript_blocks._rewrite
    def fail(manuscript, project, path, before, after, note):
        if path == origin and note.startswith('Move'):
            assert figure in destination.read_text()
            entered.set()
            assert release.wait(3)
            raise ValueError('controlled origin failure')
        return original(manuscript,project,path,before,after,note)
    monkeypatch.setattr(manuscript_blocks, '_rewrite', fail)
    request = {'operation':'move','block':{'file':'chapter.tex','line_start':2,'line_end':7,
        'before':figure,'expected_source_digest':_digest(origin)},
        'destination':{'file':'other.tex','line':1,'before':'Other anchor.','expected_source_digest':_digest(destination)}}
    worker, waiting = _observe_wait(monkeypatch, destination)
    def other():
        worker.append(threading.get_ident())
        return _rewrite(manuscript,'blocks','other.tex','Other anchor.','Other author anchor.')
    with ThreadPoolExecutor(2) as pool:
        moved = pool.submit(manuscript_blocks.change, tmp_path,'blocks',request)
        assert entered.wait(2)
        second = pool.submit(other)
        assert waiting.wait(1) and not second.done()
        release.set()
        with pytest.raises(ValueError, match='controlled origin'):
            moved.result(timeout=4)
        assert second.result(timeout=4)['applied']
    assert figure in origin.read_text() and figure not in destination.read_text()
    assert destination.read_text() == 'Other author anchor.\n'


def test_structure_required_plan_failure_compensates_before_ordinary_writer(tmp_path, monkeypatch):
    manuscript, chapter, _ = _section_fixture(tmp_path)
    monkeypatch.setattr(review_surface, '_repo_root', lambda:tmp_path)
    state = manuscript_structure._structure_state('book',tmp_path)
    entered, release = threading.Event(), threading.Event()
    def refuse(*args, **kwargs):
        assert '\\chapter{First}' not in chapter.read_text()
        entered.set()
        assert release.wait(3)
        return {'applied':False,'error':'controlled plan failure'}
    monkeypatch.setattr(manuscript_structure, '_plan_write', refuse)
    request = {'operation':'delete','section_id':'first','source_file':chapter.relative_to(tmp_path).as_posix(),
        'expected_source_digest':_digest(chapter),'expected_plan_revision':state['revision']}
    worker, waiting = _observe_wait(monkeypatch, chapter)
    def other():
        worker.append(threading.get_ident())
        return _rewrite(manuscript,'book','chapters/chapter-01.tex','First body.','Other author body.',2)
    with ThreadPoolExecutor(2) as pool:
        deletion = pool.submit(manuscript_structure.change, 'book',request,tmp_path)
        assert entered.wait(2)
        second = pool.submit(other)
        assert waiting.wait(1) and not second.done()
        release.set()
        with pytest.raises(ValueError, match='controlled plan failure'):
            deletion.result(timeout=4)
        assert second.result(timeout=4)['applied']
    assert chapter.read_text().startswith('\\chapter{First}\nOther author body.')


def test_publication_wait_does_not_hold_global_cache_mutex(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def holder():
        with writing_records.proposal_write_lock(tmp_path):
            entered.set()
            assert release.wait(2)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(holder)
        assert entered.wait(1)
        try:
            acquired = records_fold._LOCK.acquire(timeout=.1)
            assert acquired
            records_fold._LOCK.release()
        finally:
            release.set()
        first.result(timeout=2)


def test_proposal_namespace_growth_during_wait_refuses_before_any_effect(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    main = manuscript/'main.tex'
    turn = _seed_revision(tmp_path,'fixture',[{'file':'main.tex','line_start':3,'line_end':3,
        'before':'Original prose.','after':'Proposed prose.','reason':'requested'}])
    (manuscript/'later.tex').write_text('Later independent source.\n')
    worker, waiting = _observe_wait(monkeypatch, main)
    def apply():
        worker.append(threading.get_ident())
        return _apply_fixture(tmp_path,{'turn_id':turn})
    with ThreadPoolExecutor(1) as pool:
        with manuscript_source.source_mutation([main]):
            future = pool.submit(apply)
            assert waiting.wait(2)
            main.write_text(main.read_text().replace('\\end{document}', '\\input{later}\n\\end{document}'))
            observed = main.read_bytes()
        with pytest.raises(ValueError, match='namespace changed'):
            future.result(timeout=3)
    assert main.read_bytes() == observed
    assert not (session_reads._records(tmp_path)['turns'][turn].get('applications') or [])


@pytest.mark.parametrize('rollback_fails', [False, True])
def test_raised_second_owner_failure_records_compensation_or_actual_partial_outcome(tmp_path, monkeypatch, rollback_fails):
    manuscript, _ = _import_project(tmp_path, files={'main.tex':
        '\\documentclass{article}\n\\begin{document}\n\\input{a}\n\\input{b}\n\\end{document}\n',
        'a.tex':'Old A.\n','b.tex':'Old B.\n'})
    turn = _seed_revision(tmp_path,'fixture',[
        {'file':'a.tex','line_start':1,'line_end':1,'before':'Old A.','after':'New A.','reason':'requested'},
        {'file':'b.tex','line_start':1,'line_end':1,'before':'Old B.','after':'New B.','reason':'requested'}])
    monkeypatch.setattr(review_surface, '_repo_root', lambda:tmp_path)
    original = review_surface._adjudicate
    def fail(*args, **kwargs):
        payload=args[2]
        assert manuscript_source.source_mutation_active()
        if payload['file']=='b.tex' or rollback_fails and payload.get('note','').startswith('Rollback'):
            raise OSError('controlled source owner failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(review_surface,'_adjudicate',fail)
    result = _apply_fixture(tmp_path,{'turn_id':turn})
    assert not result['complete'] and result['rolled_back'] is (not rollback_fails)
    assert result['receipts'][0]['banked'] and result['receipts'][1]['reason']=='source-owner-failed'
    assert result['receipts'][1]['source_effect']=='UNPROVED'
    assert len(result['rollbacks'])==1
    assert (manuscript/'a.tex').read_text()==('New A.\n' if rollback_fails else 'Old A.\n')
    assert (manuscript/'b.tex').read_text()=='Old B.\n'
    applications=source_effects.applications(session_reads._records(tmp_path)['turns'][turn])
    assert len(applications)==1 and not applications[0]['complete']
    assert applications[0]['rolled_back'] is (not rollback_fails)
    assert result['source_effect']['state']==('PARTIAL' if rollback_fails else 'ROLLED_BACK')
    assert result['source_effect']['complete'] is False


def _bank_failure_fixture(tmp_path, monkeypatch, after=False):
    manuscript, _ = _import_project(tmp_path)
    proposal={'edits':[{'file':'main.tex','line_start':3,'line_end':3,
        'before':'Original prose.','after':'Applied despite bookkeeping failure.','reason':'requested'}]}
    turn=_seed_revision(tmp_path,'fixture',proposal['edits'], selection={'files':['main.tex']})
    monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    original=writing_records.bank
    def failed(root,row):
        if row.get('record')=='writing-application':
            if after:original(root,row)
            raise OSError('controlled application publication failure')
        return original(root,row)
    monkeypatch.setattr(writing_records,'bank',failed)   # the owner (records) and the facade alias
    return manuscript,turn,proposal


@pytest.mark.parametrize('after', [False,True])
def test_actual_http_application_publication_failure_requires_exact_record_recovery(tmp_path, monkeypatch, after):
    manuscript,turn,_=_bank_failure_fixture(tmp_path,monkeypatch,after)
    from laplace.manuscript.manuscript_proposals import proposal_version
    version=proposal_version(session_reads._records(tmp_path)['turns'][turn])[0]
    status,_type,raw=authoring_surface.handle('/authoring/apply',{},'POST',json.dumps({
        'project':'fixture','turn_id':turn,'proposal_version':version}).encode())
    assert status==200
    result=json.loads(raw)
    assert 'Applied despite bookkeeping failure.' in (manuscript/'main.tex').read_text()
    assert result['application_tracking']['status']==('RECOVERED' if after else 'UNPROVED')
    assert result['complete'] is after
    if after:
        assert result['id'].startswith('WA-')
    else:
        assert 'id' not in result and result['source_applied']
        assert result['receipts'][0]['row_id'].startswith('FB-')
        assert 'do not repeat' in result['warning']


def test_native_projection_preserves_source_facts_and_no_parent_application_ack(tmp_path, monkeypatch):
    manuscript,turn,proposal=_bank_failure_fixture(tmp_path,monkeypatch)
    from laplace.native import tools as writing_tools
    raw=writing_tools.execute(tmp_path,'fixture','work','apply_revision',proposal,turn_id=turn)
    assert raw.get('id') is None and not raw['complete'] and raw['source_applied']
    result=raw
    assert 'application_id' not in result and result['complete'] is False
    assert result['source_applied'] and result['application_tracking']['status']=='UNPROVED'
    assert result['source_effect']['state']=='COMMITTED' and not result['source_effect']['complete']
    assert result['source_effect']['files'][0]['observed_after_sha256']==result['source_effect']['files'][0]['after_sha256']
    assert result['status']=='SOURCE_APPLIED_TRACKING_UNPROVED'
    assert result['source_receipts'][0]['row_id'].startswith('FB-')
    assert result['next_read']['payload']=={'view':'record', 'id':'activity:feedback:'+result['source_receipts'][0]['row_id']}
    recovered=writing_tools.execute(tmp_path,'fixture','work',result['next_read']['operation'],
                                   result['next_read']['payload'],turn_id=turn)
    assert recovered['record']['id']==result['source_receipts'][0]['row_id']
    assert recovered['record_kind']=='author-rewrite' and recovered['project']=='fixture'
    assert 'do not repeat' in result['warning']
    assert 'Applied despite bookkeeping failure.' in (manuscript/'main.tex').read_text()


def test_selected_decision_does_not_accept_or_advance_siblings_from_unrecorded_application(tmp_path, monkeypatch):
    manuscript,turn,_=_bank_failure_fixture(tmp_path,monkeypatch)
    from laplace.manuscript import manuscript_proposals
    before=manuscript_proposals.preview(tmp_path,'fixture',turn)
    result=manuscript_proposals.decide(tmp_path,'fixture',{'turn_id':turn,'proposal_version':before['proposal_version'],
        'edit_id':before['edits'][0]['edit_id'],'decision':'accept'})
    assert result['source_applied'] and result['reviewable'] is False
    assert not result['application']['complete'] and 'id' not in result['application']
    retained=session_reads._records(tmp_path)['turns'][turn]
    assert not retained.get('proposal_decisions') and not retained.get('proposal_anchor_records')
    assert not source_effects.applications(retained)
    assert 'Applied despite bookkeeping failure.' in (manuscript/'main.tex').read_text()


def test_recorded_application_ack_survives_failed_context_maintenance(tmp_path, monkeypatch):
    manuscript,_=_import_project(tmp_path)
    proposal={'edits':[{'file':'main.tex','line_start':3,'line_end':3,'before':'Original prose.',
                       'after':'Actual recorded source.','reason':'requested'}]}
    turn=_seed_revision(tmp_path,'fixture',proposal['edits'], selection={'files':['main.tex']})
    monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path)
    def failed(*args):raise OSError('controlled context refresh failure')
    monkeypatch.setattr(source_application,'_rebase_current_turn_after_apply',failed)   # the owner
    result=source_application.apply_revision(tmp_path,'fixture',turn,proposal)
    assert result['id'].startswith('WA-') and result['complete']
    assert result['context_rebase']['status']=='UNPROVED' and not result['context_rebase']['advanced']
    assert 'do not repeat' in result['warning']
    recorded=source_effects.applications(session_reads._records(tmp_path)['turns'][turn])[-1]
    assert recorded['complete'] and recorded['context_rebase']['status']=='REQUESTED'
    assert not recorded['context_rebase']['advanced']


@pytest.mark.parametrize('unrecorded', [False,True])
def test_post_effect_preview_failure_retains_minimal_exact_outcome_without_new_rows(tmp_path,monkeypatch,unrecorded):
    manuscript,turn,_=_bank_failure_fixture(tmp_path,monkeypatch,after=not unrecorded)
    from laplace.manuscript import manuscript_proposals
    before=manuscript_proposals.preview(tmp_path,'fixture',turn)
    original=manuscript_proposals.preview
    def failed(*args,**kwargs):
        if 'Applied despite bookkeeping failure.' in (manuscript/'main.tex').read_text():
            raise OSError('controlled post-effect comparison failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(manuscript_proposals,'preview',failed)
    result=manuscript_proposals.decide(tmp_path,'fixture',{'turn_id':turn,'proposal_version':before['proposal_version'],
        'edit_id':before['edits'][0]['edit_id'],'decision':'accept'})
    assert result['project']=='fixture' and result['turn_id']==turn and result['proposal_version']==before['proposal_version']
    assert result['preview_unavailable'] and result['reviewable'] is False
    assert 'edits' not in result and 'identities' not in result and 'remaining' not in result
    assert 'do not repeat' in result['warning']
    if unrecorded:
        assert result['source_effect_retained'] and not result['application']['complete'] and 'id' not in result['application']
    else:
        assert result['application']['complete'] and result['application']['id'].startswith('WA-')
    assert 'Applied despite bookkeeping failure.' in (manuscript/'main.tex').read_text()


def test_recorded_application_survives_decision_metadata_failure_without_fabricated_decision(tmp_path,monkeypatch):
    manuscript,turn,_=_bank_failure_fixture(tmp_path,monkeypatch,after=True)
    from laplace.manuscript import manuscript_proposals
    before=manuscript_proposals.preview(tmp_path,'fixture',turn)
    original=writing_records.bank
    def failed(root,row):
        if row.get('record')=='writing-proposal-decision':raise OSError('controlled decision publication failure')
        return original(root,row)
    monkeypatch.setattr(writing_records,'bank',failed)   # the owner (records) and the facade alias
    result=manuscript_proposals.decide(tmp_path,'fixture',{'turn_id':turn,'proposal_version':before['proposal_version'],
        'edit_id':before['edits'][0]['edit_id'],'decision':'accept'})
    assert result['application']['complete'] and result['application']['id'].startswith('WA-')
    assert 'decision' not in result and result['application_maintenance_unproved']
    assert not result['reviewable'] and 'do not repeat' in result['warning']
