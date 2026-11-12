"""The accepted common contract (laplace.core.scoped) at the real app boundary: native verb door and HTTP route.

A manuscript source repair whose turn consulted the derived document view (its PDF now absent) is applied through
the existing owners and returns one typed pending-review obligation; the independent neighbour edit carries the
same obligation, a repeated decision applies nothing twice, and a wrong current source or changed consumed
evidence still refuses at both doors. Public synthetic fixture only; no provider or model.

Upper boundary only: _bind_rewrite_fixture replaces review_surface.adjudicate with a line-edit double, so these
cases prove the native/HTTP doors, currentness and projections, not the inner writer. The real inner writer
(adjudicate, feedback, editor-save, owned receipt) is witnessed in tests/test_core_app_effect_witness.py.
"""
import json

import pytest

from laplace.web import authoring as authoring_surface
from laplace.manuscript import manuscript_proposals as proposals
from laplace.native import tools as writing_tools
from laplace.projects import artifacts
from laplace.writing.records._bank import bank as _bank
from laplace.writing.records._fold import _proposal_digest
from test_proposal_lifecycle import RAW, clear, setup  # noqa: F401  (clear is the shared autouse cache fixture)
from test_writing_controller import _bind_rewrite_fixture


def _case(root, monkeypatch, *, evidence=False):
    from laplace.core import checkout
    monkeypatch.setattr(checkout, 'repo_root', lambda: root)   # the HTTP door serves this fixture checkout
    md, turn, changes, _ = setup(root)
    calls = _bind_rewrite_fixture(monkeypatch, md)
    (md / 'main.pdf').write_bytes(b'%PDF-1.4 synthetic derived output\n')
    writing_tools.execute(root, 'fixture', 'revise', 'document', {}, turn_id=turn)
    if evidence:
        (artifacts.project_root(root, 'fixture') / 'claim-evidence.txt').write_text('Original controlled evidence.')
        writing_tools.execute(root, 'fixture', 'revise', 'read_artifact', {'path': 'claim-evidence.txt', 'scope': 'project'}, turn_id=turn)
    raw = {'answer': 'Repair the source; the PDF is regenerated afterwards.', 'edits': changes}
    _bank(root, {'record': 'writing-proposal', 'id': 'PROP-boundary', 'turn_id': turn, 'project': 'fixture', 'proposal': raw})
    version = proposals.preview(root, 'fixture', turn, _proposal_digest(raw))['proposal_version']
    (md / 'main.pdf').unlink()   # the derived witness the repair will regenerate is now absent
    return md, turn, changes, calls, version


def _selector(turn, version, edit):
    return {'turn_id': turn, 'proposal_version': version, 'edit_id': proposals.edit_id(edit), 'decision': 'accept'}


def _native(root, turn, payload):
    return writing_tools.request(root, 'fixture', 'revise', {'verb': 'delete', 'concept': 'proposal@paragraph', 'target': '',
                                                            'expected': [], 'payload': payload, 'by': ''}, turn_id=turn)


def _http(payload):
    status, _, body = authoring_surface.handle('/authoring/proposal-decision', {}, 'POST', json.dumps({'project': 'fixture', **payload}).encode())
    return status, json.loads(body)


def test_native_and_http_doors_apply_a_scoped_repair_once_with_one_typed_pending_review(tmp_path, monkeypatch):
    md, turn, changes, calls, version = _case(tmp_path, monkeypatch)
    native = _native(tmp_path, turn, _selector(turn, version, changes[0]))
    assert native['ok'] and native['outcome'] == 'applied' and len(calls) == 1
    reply = native['owner_response']   # the native door's bounded owner reply
    assert reply['application']['complete'] and reply['application']['result_grade'] == 'APPLIED_REVIEW_PENDING'
    assert reply['review_obligation_count'] == 1
    [obligation] = reply['review_obligations']
    assert obligation['kind'] == 'CONSULTED_INPUT_CHANGED' and obligation['schema'] == 'laplace.scoped-obligation/1'
    after = (md / 'main.tex').read_bytes()
    # Continuation through either door applies nothing twice.
    replay = _native(tmp_path, turn, _selector(turn, version, changes[0]))
    replayed = (replay.get('owner_response') or {}).get('application') or {}
    assert not replay['ok'] or replayed.get('id') in (None, reply['application']['id'])  # a replay, never a second effect
    status, again = _http(_selector(turn, version, changes[0]))
    assert status >= 400 or (again.get('application') or {}).get('id') in (None, reply['application']['id'])
    assert len(calls) == 1 and (md / 'main.tex').read_bytes() == after
    # The independent neighbour edit is applied through HTTP and carries the same one obligation.
    status, second = _http(_selector(turn, version, changes[1]))
    assert status == 200 and len(calls) == 2, second
    assert second['application']['result_grade'] == 'APPLIED_REVIEW_PENDING'
    assert [row['id'] for row in second['application']['review_obligations']] == [obligation['id']]


@pytest.mark.parametrize('door', ['native', 'http'])
def test_a_wrong_current_source_refuses_at_each_door_with_the_derived_witness_absent(tmp_path, monkeypatch, door):
    md, turn, changes, calls, version = _case(tmp_path, monkeypatch)
    (md / 'main.tex').write_text(RAW.replace('First premise.', 'An external rewrite.'))
    before = (md / 'main.tex').read_bytes()
    if door == 'native':
        refused = _native(tmp_path, turn, _selector(turn, version, changes[0]))
        assert not refused['ok'] and refused['refused']['said']
    else:
        status, body = _http(_selector(turn, version, changes[0]))
        assert status >= 400 and 'project' not in body.get('error', '').lower(), body
    assert not calls and (md / 'main.tex').read_bytes() == before


@pytest.mark.parametrize('door', ['native', 'http'])
def test_changed_consumed_evidence_refuses_at_each_door(tmp_path, monkeypatch, door):
    md, turn, changes, calls, version = _case(tmp_path, monkeypatch, evidence=True)
    (artifacts.project_root(tmp_path, 'fixture') / 'claim-evidence.txt').write_text('Changed experimental conclusion.')
    if door == 'native':
        refused = _native(tmp_path, turn, _selector(turn, version, changes[0]))
        assert not refused['ok'] and refused['refused']['said']
    else:
        status, body = _http(_selector(turn, version, changes[0]))
        assert status >= 400 and 'read_artifact' in json.dumps(body), body
    assert not calls and (md / 'main.tex').read_text() == RAW
