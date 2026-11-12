"""Work review lifecycle repair3 (Sol recheck of repair2, 2026-10-16, WR-R3-R2): a follow-up conflict KNOWN before
publication refuses with nothing written. A new request whose same-finding child already exists with a different
specification publishes no PENDING phase, creates no child or join and leaves its request id unconsumed; genuine
partial operations keep their durable PENDING recovery (tests/test_work_review_repair1.py, repair2). Synthetic only.
"""
from __future__ import annotations

from laplace.work import project_work as work
from test_work_review_lifecycle import P, guard, native, root  # noqa: F401


def _request(root, request_id, goal):
    return {'id': 'parent', 'phase': 'followup', 'request_id': request_id, 'expected_work_revision': guard(root),
            'finding': 'F9', 'closure': 'required', 'child': {'title': 'Correction', 'goal': goal}}


def _pending(root):
    return work.read(P, {'view': 'detail', 'id': 'parent'}, root)['task']['review']['pending_joins']


def test_a_known_conflicting_child_refuses_before_any_pending_phase_and_leaves_its_request_unconsumed(root):
    import pytest
    first = native(root, 'WT-prod', _request(root, 'req-first-spec', 'First specification'))
    assert first['status'] == 'JOINED'
    child = work._tasks(P, root)[first['child_id']]
    ledger, phases = work._ledger(root).read_bytes(), len(work._tasks(P, root)['parent']['phases'])
    with pytest.raises(work.WorkConflict, match=r'no longer matches the requested correction \(goal changed\)'):
        native(root, 'WT-prod', _request(root, 'req-second-spec', 'A conflicting specification'))
    assert work._ledger(root).read_bytes() == ledger, 'no PENDING phase, child, join or completion was written'
    assert _pending(root) == [] and len(work._tasks(P, root)['parent']['phases']) == phases
    assert work._tasks(P, root)[child['id']] == child, 'the existing child is untouched'
    assert sum(bool(row.get('followup_origin')) for row in work._tasks(P, root).values()) == 1
    # the refused request id was never consumed: corrected, it records normally; a new valid request leaves no ghost
    corrected = native(root, 'WT-prod', _request(root, 'req-second-spec', 'First specification'))
    assert corrected['status'] == 'JOINED' and corrected['phase']['request_id'] == 'req-second-spec'
    fresh = native(root, 'WT-prod', _request(root, 'req-third-spec', 'First specification'))
    assert fresh['status'] == 'JOINED' and _pending(root) == []
    assert work.read(P, {'view': 'detail', 'id': 'parent'}, root)['task']['review']['next']['kind'] != 'recover-join'
