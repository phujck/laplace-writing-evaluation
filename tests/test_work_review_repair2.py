"""Work review lifecycle repair2 (Sol recheck of repair1, 2026-10-16): the five residual controls.

WR-R1-R1 the public evidence perimeter is the declared superset of the export's runtime/cache/secret fences;
WR-R2-R1 a review re-establishes complete coverage of the CURRENT obligation by its handoff;
WR-R3-R1 a landed follow-up child that no longer matches its requested correction is never joined as it;
WR-R4-R1 deliberate full reads hand out caller-owned phase rows.
(WR-R4-R1 human admission/continuation and WR-R5-R1 adoption focus: tests/work_review_repair2_frontend.test.mjs.)
Disposable synthetic fixtures only; no real private file is read.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from laplace.work import project_work as work, project_work_review as review
from laplace.core import perimeter
from test_work_review_lifecycle import P, guard, handoff, native, reviewed, root, sha, state  # noqa: F401

TREE = Path(__file__).parents[1]


# ---------------------------------------------------------------------------------------------- WR-R1-R1

@pytest.mark.parametrize('rel', ['.research_previews/example.json', 'proj/.research_previews/p.png', '__pycache__/m.cpython-314.pyc',
                                 'node_modules/pkg/index.js', '.venv/lib/site.py', '.pytest_cache/v/cache', '.mypy_cache/x.json',
                                 '.ruff_cache/x', '.lake/build/x', 'src/compiled.pyc', 'proj/run.lock', 'keys/server.pem'])
def test_declared_runtime_cache_and_secret_coordinates_refuse_before_hashing(root, monkeypatch, rel):
    (root / rel).parent.mkdir(parents=True, exist_ok=True); (root / rel).write_text('synthetic runtime bytes')
    hashed = []
    real = review._file_digest
    monkeypatch.setattr(review, '_file_digest', lambda base, path, *a, **k: (hashed.append(path), real(base, path, *a, **k))[1])
    with pytest.raises(Exception, match='PRIVATE_OR_UNOWNED'):
        handoff(root, evidence=[{'path': rel, 'sha256': 'sha256:' + '0' * 64}])
    assert rel not in hashed, 'refused before hashing'


def test_authored_data_results_evidence_and_dependency_locks_remain_public(root):
    for rel in ('evidence/public.md', 'data/results/run.json', 'uv.lock'):
        (root / rel).parent.mkdir(parents=True, exist_ok=True); (root / rel).write_text('authored ' + rel)
    done = handoff(root, evidence=[{'path': rel, 'sha256': sha(root, rel)} for rel in ('evidence/public.md', 'data/results/run.json', 'uv.lock')])
    assert [row['path'] for row in done['phase']['evidence']] == ['evidence/public.md', 'data/results/run.json', 'uv.lock']


def test_the_public_perimeter_covers_every_namespace_the_export_fences():
    spec = importlib.util.spec_from_file_location('writing_eval_manifest_r2', TREE / 'scripts/writing_eval_manifest.py')
    manifest = importlib.util.module_from_spec(spec); spec.loader.exec_module(manifest)
    public = perimeter.PRIVATE_NAMESPACES | perimeter.RUNTIME_NAMESPACES
    assert manifest.PRIVATE | manifest.CACHES <= public
    assert manifest.SECRET_NAMES <= perimeter.SECRET_NAMES
    for name in ('a/.env', 'a/.env.local', 'a/x.pem', 'a/x.key', 'a/x.pyc', 'a/run.lock'):
        assert manifest._excluded(Path(name)) and perimeter._not_public(Path(name).parts), name
    assert not perimeter._not_public(Path('uv.lock').parts) and not manifest._excluded(Path('uv.lock'))


# ---------------------------------------------------------------------------------------------- WR-R2-R1

def _edit_inputs(root, inputs):
    obligations = copy.deepcopy(work._tasks(P, root)['parent']['review_obligations'])
    obligations[0]['inputs'] = inputs
    work.task(P, {'id': 'parent', 'review_obligations': obligations, 'expected_work_revision': guard(root)}, root)


def _row(root, ident='source'):
    return next(item for item in state(root, view='detail', id='parent')[1]['task']['review']['obligations'] if item['id'] == ident)


@pytest.mark.parametrize('change', ['add', 'replace'])
def test_an_input_added_after_the_handoff_refuses_review_of_the_old_handoff(root, change):
    first = handoff(root)
    (root / 'src/c.py').write_text('c = 3\n')
    _edit_inputs(root, ['src/a.py', 'src/b.py', 'src/c.py'] if change == 'add' else ['src/a.py', 'src/c.py'])
    with pytest.raises(Exception, match=r'does not pin the current declared input\(s\) of this obligation: src/c\.py'):
        reviewed(root, first['phase']['id'], 'source')
    row = _row(root)
    assert row['satisfied'] is False and row['status'] == 'AWAITING_REVIEW'


def test_a_removed_input_keeps_the_old_handoff_reviewable_over_the_remaining_inputs(root):
    first = handoff(root)
    _edit_inputs(root, ['src/a.py'])
    done = reviewed(root, first['phase']['id'], 'source')
    assert done['phase']['pins'] == {'src/a.py': sha(root, 'src/a.py')}
    assert _row(root)['currentness'] == 'CURRENT'


def test_a_fresh_covering_handoff_is_reviewable_and_each_relevant_file_stales_it_while_disjoint_reviews_stay(root):
    first = handoff(root)
    reviewed(root, first['phase']['id'], 'guide')
    (root / 'src/c.py').write_text('c = 3\n')
    _edit_inputs(root, ['src/a.py', 'src/b.py', 'src/c.py'])
    fresh = handoff(root, request='req-handoff-covering', pins={rel: sha(root, rel) for rel in ('src/a.py', 'src/b.py', 'src/c.py', 'docs/guide.md')})
    done = reviewed(root, fresh['phase']['id'], 'source', request='req-review-covering')
    assert set(done['phase']['pins']) == {'src/a.py', 'src/b.py', 'src/c.py'}
    assert _row(root)['currentness'] == 'CURRENT' and _row(root, 'guide')['currentness'] == 'CURRENT', 'the disjoint review stays'
    for rel in ('src/a.py', 'src/b.py', 'src/c.py'):
        before = (root / rel).read_text()
        (root / rel).write_text(before + '# changed\n')
        assert _row(root)['currentness'] == 'STALE', rel
        (root / rel).write_text(before)
    assert _row(root)['currentness'] == 'CURRENT'


def test_a_review_whose_pins_miss_a_current_input_is_never_current(root):
    obligation = {'id': 'source', 'scope': 'source', 'label': 'Source review', 'inputs': ['src/a.py', 'src/c.py']}
    recorded = {'obligation_digest': review._digest(obligation), 'intent_digest': 'sha256:x', 'pins': {'src/a.py': sha(root, 'src/a.py')}}
    assert review._currentness(recorded, obligation, root, {}, None)['status'] == 'UNKNOWN'


# ---------------------------------------------------------------------------------------------- WR-R3-R1

def _pending_child(root, monkeypatch, request_id='req-landed'):
    request = {'id': 'parent', 'phase': 'followup', 'request_id': request_id, 'expected_work_revision': guard(root),
               'finding': 'F1', 'closure': 'required', 'child': {'title': 'Correction', 'goal': 'Original required correction'}}
    real = work._task
    def failing(project, payload, repo_root=None, **kw):
        if payload.get('id') == 'parent':
            raise OSError('synthetic join failure')
        return real(project, payload, repo_root, **kw)
    monkeypatch.setattr(work, '_task', failing)
    first = native(root, 'WT-prod', request)
    monkeypatch.setattr(work, '_task', real)
    assert first['status'] == 'PENDING_JOIN'
    return request, first['child_id']


@pytest.mark.parametrize('field,value', [('goal', 'Different correction authored later'), ('title', 'Renamed'), ('kind', 'research')])
def test_a_landed_child_changed_while_pending_is_kept_and_never_joined_as_the_requested_correction(root, monkeypatch, field, value):
    request, child = _pending_child(root, monkeypatch)
    before = work._tasks(P, root)[child]
    work.task(P, {'id': child, field: value, 'expected_work_revision': work._task_revision(before)}, root)
    edited = work._ledger(root).read_bytes()
    with pytest.raises(work.WorkConflict, match=r'no longer matches the requested correction \(%s changed\)' % ('kind' if field == 'kind' else field)):
        native(root, 'WT-prod', request)
    assert work._ledger(root).read_bytes() == edited, 'nothing appended: no join, no completion row, no rollback'
    parent = work._tasks(P, root)['parent']
    assert not any(item.get('closure_work_id') == child for item in parent['review_obligations'])
    assert work._tasks(P, root)[child][{'kind': 'task_kind'}.get(field, field)] == value, 'the child is kept as authored'


def test_an_unchanged_landed_child_recovers_once_with_original_and_recovering_identities(root, monkeypatch):
    request, child = _pending_child(root, monkeypatch)
    recovered = native(root, 'WT-rev', request)
    assert recovered['status'] == 'RECOVERED' and recovered['joined'] is True and recovered['child_created'] is False
    assert recovered['phase']['actor']['turn_id'] == 'WT-prod' and recovered['phase']['recovered_by']['turn_id'] == 'WT-rev'
    assert native(root, 'WT-prod', request)['status'] == 'REUSED'


def test_a_new_request_for_the_same_finding_cannot_claim_a_conflicting_child_was_delivered(root):
    first = native(root, 'WT-prod', {'id': 'parent', 'phase': 'followup', 'request_id': 'req-first-spec', 'expected_work_revision': guard(root),
                                     'finding': 'F9', 'closure': 'required', 'child': {'title': 'Correction', 'goal': 'First specification'}})
    assert first['status'] == 'JOINED'
    with pytest.raises(work.WorkConflict, match=r'no longer matches the requested correction \(goal changed\)'):
        native(root, 'WT-prod', {'id': 'parent', 'phase': 'followup', 'request_id': 'req-second-spec', 'expected_work_revision': guard(root),
                                 'finding': 'F9', 'closure': 'required', 'child': {'title': 'Correction', 'goal': 'A conflicting specification'}})
    assert work._tasks(P, root)[first['child_id']]['goal'] == 'First specification'


# ---------------------------------------------------------------------------------------------- WR-R4-R1

def test_direct_and_composed_full_reads_hand_out_caller_owned_phase_rows(root):
    first = handoff(root)
    phase_id = first['phase']['id']
    original = state(root, view='review', id='parent', phase_id=phase_id)[1]
    cut = state(root, view='detail', id='parent')[1]['read_cut']['revision']
    ledger = work._ledger(root).read_bytes()
    for served in (work.state(P, root), work.read(P, {'view': 'full'}, root)):
        row = next(item for item in served['tasks'] if item['id'] == 'parent')['phases'][0]
        row['summary'] = 'TAMPERED THROUGH PUBLIC FULL VIEW'; row['pins'].clear(); row['actor']['actor'] = 'TAMPERED'
    again = state(root, view='review', id='parent', phase_id=phase_id)[1]
    assert again['phase'] == original['phase'], 'exact original phase bytes, pins and actor'
    assert state(root, view='detail', id='parent')[1]['read_cut']['revision'] == cut and work._ledger(root).read_bytes() == ledger
    assert handoff(root)['status'] == 'REUSED', 'the idempotent replay still compares the untouched original'
