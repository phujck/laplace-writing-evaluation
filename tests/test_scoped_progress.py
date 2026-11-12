"""Scoped progress (laplace.core.scoped) and the owners that consume it, on public synthetic fixtures.

An operation needs only its authority and the current basis its effect consumes. A consulted derived
observation that moved (an absent PDF, a changed build view) becomes a typed local review obligation on
the result; wrong source, wrong authority and changed consumed evidence still refuse.
"""
import hashlib
import json

import pytest

from laplace.manuscript import manuscript_proposals as proposals
from laplace.work import project_work, project_work_review
from laplace.projects import artifacts
from laplace.writing.records._bank import bank as _bank
from laplace.writing.records._fold import _proposal_digest
from laplace.native import tools as writing_tools
from laplace.core import scoped as core_scoped
from laplace.writing import reads as read_contract
from test_proposal_lifecycle import RAW, clear, decide, setup  # noqa: F401  (clear is the shared autouse cache fixture)
from test_writing_controller import _bind_rewrite_fixture


# -- the core rule -------------------------------------------------------------------------------

def test_roles_refuse_only_what_the_effect_consumes_and_carry_consulted_change_as_a_local_obligation():
    rows = [core_scoped.observation('selected-source', 'target', expected='a', observed='a'),
            core_scoped.observation('pdf-witness', 'consulted', expected='p', observed=None),
            core_scoped.observation('page-view', 'consulted', expected='v1', observed='v2')]
    judged = core_scoped.judge(rows)
    assert judged['admitted'] and [o['kind'] for o in judged['obligations']] == ['CONSULTED_INPUT_UNAVAILABLE', 'CONSULTED_INPUT_CHANGED']
    assert judged['semantic_currentness'] == 'REVIEW_REQUIRED'
    for role in ('authority', 'target', 'consumed'):
        refused = core_scoped.judge([core_scoped.observation('x', role, expected='a', observed='b')])
        assert not refused['admitted'] and not refused['obligations']
    with pytest.raises(ValueError):
        core_scoped.observation('x', 'everything', expected='a', observed='a')


def test_obligations_are_stable_once_each_and_never_close_on_themselves():
    one = core_scoped.obligation('REVIEW', 'Review it.', subject='s', basis='b')
    again = core_scoped.obligation('REVIEW', 'Review it.', subject='s', basis='b')
    assert one['id'] == again['id'] and core_scoped.merge([one], [again]) == [one]
    assert core_scoped.closure_admissible(one, ['OBL-other']) and not core_scoped.closure_admissible(one, [one['id']])
    assert core_scoped.grade(obligations=[one]) == 'APPLIED_REVIEW_PENDING' and core_scoped.grade() == 'APPLIED'
    assert core_scoped.grade(complete=False) == 'INCOMPLETE' and core_scoped.grade(refused=True) == 'REFUSED'


def test_aggregation_carries_consumed_children_only_and_keeps_an_independent_failure_local():
    children = [{'id': 'consumed-pending', 'grade': 'APPLIED_REVIEW_PENDING', 'consumed': True},
                {'id': 'consumed-done', 'grade': 'APPLIED', 'consumed': True},
                {'id': 'neighbour', 'grade': 'REFUSED', 'consumed': False}]
    parent = core_scoped.aggregate(children)
    assert parent == {'grade': 'APPLIED_REVIEW_PENDING', 'by': ['consumed-pending'], 'independent_children': ['neighbour']}
    assert core_scoped.aggregate([{**children[2], 'consumed': True}])['grade'] == 'REFUSED'


def test_the_read_contract_names_derived_document_observations_as_consulted():
    assert read_contract.read_role('document', {}) == 'consulted'
    assert read_contract.read_role('document', {'target_kind': 'derived'}) == 'consulted'
    assert read_contract.read_role('document', {'view': 'template'}) == 'consumed'
    for operation in ('source', 'read_artifact', 'concept', 'references', 'logical_plan', 'visuals', 'writing_style'):
        assert read_contract.read_role(operation, {}) == 'consumed'


# -- a source repair despite an absent derived PDF and a stale view --------------------------------

def _repair_with_document_witness(root, monkeypatch):
    md, turn, changes, _ = setup(root)
    calls = _bind_rewrite_fixture(monkeypatch, md)
    pdf = md / 'main.pdf'
    pdf.write_bytes(b'%PDF-1.4 synthetic derived output\n')
    writing_tools.execute(root, 'fixture', 'revise', 'document', {}, turn_id=turn)
    raw = {'answer': 'Repair the source; the PDF is regenerated afterwards.', 'edits': changes}
    _bank(root, {'record': 'writing-proposal', 'id': 'PROP-repair', 'turn_id': turn, 'project': 'fixture', 'proposal': raw})
    version = proposals.preview(root, 'fixture', turn, _proposal_digest(raw))['proposal_version']
    return md, turn, changes, calls, pdf, version


def test_an_absent_derived_pdf_does_not_block_the_source_repair_and_becomes_a_local_obligation(tmp_path, monkeypatch):
    md, turn, changes, calls, pdf, version = _repair_with_document_witness(tmp_path, monkeypatch)
    pdf.unlink()  # the derived witness the repair will regenerate is now absent
    row = proposals.preview(tmp_path, 'fixture', turn, version)['edits'][0]
    assert row['basis_currentness'] == 'CURRENT' and 'accept' in row['allowed_actions']
    applied = decide(tmp_path, turn, row, version)['application']
    assert len(calls) == 1 and applied['result_grade'] == 'APPLIED_REVIEW_PENDING'
    [obligation] = applied['review_obligations']
    assert obligation['kind'] == 'CONSULTED_INPUT_CHANGED' and obligation['schema'] == core_scoped.OBLIGATION_SCHEMA
    assert applied['validation_basis']['semantic_currentness'] == 'REVIEW_REQUIRED'
    # Idempotent continuation: repeating the decided effect applies nothing twice (a replay or a refusal).
    after = (md / 'main.tex').read_bytes()
    try:
        again = decide(tmp_path, turn, row, version)
    except ValueError:
        again = None
    assert len(calls) == 1 and (md / 'main.tex').read_bytes() == after
    assert again is None or (again.get('application') or {}).get('id') in (None, applied['id'])
    # The independent neighbour edit stays actionable and carries the same one obligation, not a reset.
    neighbour = next(r for r in proposals.preview(tmp_path, 'fixture', turn, version)['edits'] if r['edit_id'] == proposals.edit_id(changes[1]))
    assert neighbour['basis_currentness'] == 'CURRENT' and 'accept' in neighbour['allowed_actions']
    second = decide(tmp_path, turn, neighbour, version)['application']
    assert len(calls) == 2 and [o['id'] for o in second['review_obligations']] == [obligation['id']]


def test_a_changed_unrelated_view_of_the_derived_output_is_review_not_refusal(tmp_path, monkeypatch):
    md, turn, changes, calls, pdf, version = _repair_with_document_witness(tmp_path, monkeypatch)
    pdf.write_bytes(b'%PDF-1.4 a later unrelated build\n')
    row = proposals.preview(tmp_path, 'fixture', turn, version)['edits'][0]
    applied = decide(tmp_path, turn, row, version)['application']
    assert len(calls) == 1 and applied['review_obligations'][0]['kind'] == 'CONSULTED_INPUT_CHANGED'


def test_the_wrong_current_source_still_refuses_with_the_derived_witness_absent(tmp_path, monkeypatch):
    md, turn, changes, calls, pdf, version = _repair_with_document_witness(tmp_path, monkeypatch)
    pdf.unlink()
    row = proposals.preview(tmp_path, 'fixture', turn, version)['edits'][0]
    (md / 'main.tex').write_text(RAW.replace('First premise.', 'An external rewrite.'))
    before = (md / 'main.tex').read_bytes()
    blocked = proposals.preview(tmp_path, 'fixture', turn, version)['edits'][0]
    assert blocked['lifecycle'] == 'blocked'
    with pytest.raises(ValueError):
        decide(tmp_path, turn, row, version)
    assert not calls and (md / 'main.tex').read_bytes() == before


def test_changed_consumed_evidence_beside_an_absent_pdf_still_refuses(tmp_path, monkeypatch):
    md, turn, changes, calls, pdf, version = _repair_with_document_witness(tmp_path, monkeypatch)
    artifact = artifacts.project_root(tmp_path, 'fixture') / 'claim-evidence.txt'
    artifact.write_text('Original controlled evidence.')
    writing_tools.execute(tmp_path, 'fixture', 'revise', 'read_artifact', {'path': 'claim-evidence.txt', 'scope': 'project'}, turn_id=turn)
    raw = {'answer': 'Rests on the evidence and observed the PDF.', 'edits': changes}
    _bank(tmp_path, {'record': 'writing-proposal', 'id': 'PROP-evidence-and-pdf', 'turn_id': turn, 'project': 'fixture', 'proposal': raw})
    version = proposals.preview(tmp_path, 'fixture', turn, _proposal_digest(raw))['proposal_version']
    pdf.unlink()
    artifact.write_text('Changed experimental conclusion.')
    blocked = proposals.preview(tmp_path, 'fixture', turn, version)['edits'][0]
    assert blocked['basis_currentness'] == 'STALE' and 'read_artifact' in blocked['error']
    with pytest.raises(ValueError):
        decide(tmp_path, turn, blocked, version)
    assert not calls


# -- Work: containment is not consumption ----------------------------------------------------------

def _legacy_scope(work_revision, parent_scope):
    scope = {'work': work_revision, 'parent_scope': parent_scope}
    return 'sha256:' + hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _tasks(programme_kind):
    return {'ROOT': {'id': 'ROOT', 'title': 'Organisation', 'goal': 'Root constraint.', 'task_kind': 'execution'},
            'PROG': {'id': 'PROG', 'title': 'Programme', 'goal': 'Broad goal v1.', 'task_kind': programme_kind, 'parent_work_id': 'ROOT'},
            'CHILD': {'id': 'CHILD', 'title': 'Accepted reading', 'goal': 'Read one paper.', 'task_kind': 'execution', 'parent_work_id': 'PROG'},
            'NEIGHBOUR': {'id': 'NEIGHBOUR', 'title': 'Neighbour', 'goal': 'Independent.', 'task_kind': 'execution', 'parent_work_id': 'ROOT'}}


def test_a_programme_goal_change_keeps_child_scope_but_a_consumed_ancestor_change_restales_it():
    tasks = _tasks(project_work.PROGRAMME)
    child = project_work._work_basis(tasks, 'CHILD')[0]['scope_revision']
    review = project_work_review.intent_digest(tasks['CHILD'], tasks)
    widened = {**tasks, 'PROG': {**tasks['PROG'], 'goal': 'Broad goal v2, now including everything.'}}
    assert project_work._work_basis(widened, 'CHILD')[0]['scope_revision'] == child
    assert project_work_review.intent_digest(widened['CHILD'], widened) == review
    # What the programme itself consumes (its parent) is still consumed by what it contains.
    constrained = {**tasks, 'ROOT': {**tasks['ROOT'], 'goal': 'Root constraint changed.'}}
    assert project_work._work_basis(constrained, 'CHILD')[0]['scope_revision'] != child
    assert project_work._work_basis(constrained, 'NEIGHBOUR')[0]['scope_revision'] != project_work._work_basis(tasks, 'NEIGHBOUR')[0]['scope_revision']
    # The programme's own scope still moves with its own goal.
    assert project_work._work_basis(widened, 'PROG')[0]['scope_revision'] != project_work._work_basis(tasks, 'PROG')[0]['scope_revision']


def test_an_ordinary_parent_is_consumed_whole_with_legacy_hashes_unchanged():
    tasks = _tasks('execution')
    root_scope = _legacy_scope(project_work._task_revision(tasks['ROOT']), None)
    prog_scope = _legacy_scope(project_work._task_revision(tasks['PROG']), root_scope)
    child_scope = _legacy_scope(project_work._task_revision(tasks['CHILD']), prog_scope)
    assert project_work._work_basis(tasks, 'CHILD')[0]['scope_revision'] == child_scope
    widened = {**tasks, 'PROG': {**tasks['PROG'], 'goal': 'Broad goal v2.'}}
    assert project_work._work_basis(widened, 'CHILD')[0]['scope_revision'] != child_scope
    assert project_work_review.intent_digest(widened['CHILD'], widened) != project_work_review.intent_digest(tasks['CHILD'], tasks)


# -- a JSON-record read witness: volatile parse timing versus consumed meaning ---------------------

def test_an_unchanged_json_record_read_keeps_its_digest_when_only_parse_timing_differs(tmp_path, monkeypatch):
    from laplace.core import json_record
    md, turn, changes, _ = setup(tmp_path)
    artifact = artifacts.project_root(tmp_path, 'fixture') / 'metadata.json'
    artifact.write_text(json.dumps({'sources': [{'id': 'S1', 'title': 'Synthetic source'}], 'selected': 'S1'}))
    import itertools
    clock = iter(itertools.chain([0.0, 0.001, 10.0, 10.250], itertools.count(20.0, 0.5)))
    monkeypatch.setattr(json_record.time, 'perf_counter', lambda: next(clock))
    payload = {'path': 'metadata.json', 'scope': 'project', 'pointer': '/selected'}
    first = writing_tools.execute(tmp_path, 'fixture', 'revise', 'read_artifact', payload, turn_id=turn)
    second = writing_tools.execute(tmp_path, 'fixture', 'revise', 'read_artifact', payload, turn_id=turn)
    assert first['json_record']['parse']['parse_ms'] != second['json_record']['parse']['parse_ms']
    assert read_contract.read_output_digest('read_artifact', first) == read_contract.read_output_digest('read_artifact', second)
    artifact.write_text(json.dumps({'sources': [{'id': 'S1', 'title': 'Synthetic source'}], 'selected': 'S2'}))
    changed = writing_tools.execute(tmp_path, 'fixture', 'revise', 'read_artifact', payload, turn_id=turn)
    assert read_contract.read_output_digest('read_artifact', changed) != read_contract.read_output_digest('read_artifact', first)


# -- bounded reader state keeps the premises its next read consumes ---------------------------------

def test_a_bounded_reader_state_keeps_named_requirements_its_next_need_refers_to():
    from laplace.pipeline.writing_organ.reader import ReadRun, compile_reader_prompt
    from laplace.pipeline.writing_organ.schema import ReaderState
    requirements = {f'REQ-{name}': f'Synthetic requirement {name}.' for name in ('alpha', 'beta', 'gamma', 'delta', 'epsilon')}
    state = ReaderState(established=dict(requirements))
    run = ReadRun(state=state)
    # Later stretches add many unrelated holdings and repeat one generic non-claim.
    for index in range(6):
        run.absorb(f'stretch-{index}', 'synthetic text', {
            'findings': [], 'sentence_functions': [],
            'newly_defined': {f'term-{index}-{n}': 'filler meaning' for n in range(8)},
            'updated_summary': 'Nothing here is certified. ' * 40 + f'Stretch {index} explained one mechanism.',
            'new_open_questions': ['How does the architecture satisfy REQ-alpha, REQ-beta, REQ-gamma, REQ-delta and REQ-epsilon?'],
            'next_need': 'the crosswalk from REQ-alpha to REQ-epsilon onto architecture components'}, 'reader')
    held = {**run.state.defined, **run.state.established}
    assert len(held) <= ReaderState.MAX_HELD and all(name in run.state.established for name in requirements)
    assert run.state.missing_premises(list(requirements)) == []
    assert run.state.summary.count('Nothing here is certified.') == 1 and 'Stretch 5 explained one mechanism.' in run.state.summary
    rendered = run.state.render()
    assert 'What you need next: the crosswalk' in rendered and all(name in rendered for name in requirements)
    # The progressive read sees the state and only this stretch, registered to its audience.
    prompt = compile_reader_prompt(run.state, 'stretch-6', 'ONLY THIS STRETCH.', audience='business plan for a technical buyer')
    assert 'reader of a business plan for a technical buyer' in prompt and 'ONLY THIS STRETCH.' in prompt and 'stretch-7' not in prompt


def test_the_old_unbounded_state_would_have_lost_named_requirements_under_a_bound():
    from laplace.pipeline.writing_organ.schema import ReaderState
    state = ReaderState(established={f'REQ-{n}': 'r' for n in range(5)}, defined={f'term-{n}': 't' for n in range(60)},
                        open_questions=['Map REQ-0 and REQ-4 onto the design.'])
    state.enforce_bounds()
    assert set(state.established) == {f'REQ-{n}' for n in range(5)} and len(state.defined) + len(state.established) == ReaderState.MAX_HELD
    assert 'term-0' not in state.defined and 'term-59' in state.defined  # oldest unreferenced symbols go first


# -- the writer and judge instructions are delivered, fresh and on resume --------------------------

def test_scoped_progress_and_claim_placement_rules_reach_fresh_kernels_and_resumed_deltas(tmp_path):
    from laplace.writing import operating as writing_operating
    from test_writing_operating import _project
    _project(tmp_path)
    brief = writing_operating.build('book', 'work', tmp_path)
    review = writing_operating.build('book', 'review', tmp_path) if 'review' in writing_operating.ROLES else brief
    for transport in ('claude', 'codex'):
        kernel = writing_operating.kernel(brief, transport)
        assert 'Scoped progress: an action needs only its authority' in kernel
        assert 'Write connected movements' in kernel and 'not a new universal ban' in kernel
    assert 'Diagnose the consequential gaps a reader would hit' in writing_operating.frame(review)
    # A session that started under the previous rules receives exactly the changed rules as its delta.
    previous = {**brief, 'shared_rules_revision': writing_operating.digest(writing_operating.RULES[:-2]), 'rules': writing_operating.RULES[:-2]}
    delta = writing_operating.orientation_delta(previous, brief)
    assert delta['changed'] and delta['guidance']['shared_rules_revision'] == brief['shared_rules_revision']
    assert delta['guidance']['rules'][-2].startswith('Scoped progress')
    assert 'shared_rules_revision' not in writing_operating.orientation_delta(brief, brief)['guidance']


# -- SP-R1: distinct diagnostics keep distinct obligations; the same one is recorded once -----------

def test_distinct_reasons_on_one_subject_are_distinct_obligations_and_a_repeat_is_one():
    a = core_scoped.obligation('SEMANTIC_REVIEW_REQUIRED', 'Required evidence A is absent.', subject='candidate-C')
    b = core_scoped.obligation('SEMANTIC_REVIEW_REQUIRED', 'Required evidence B is absent.', subject='candidate-C')
    assert a['id'] != b['id'] and len(core_scoped.merge([a, b], [dict(a)])) == 2
    keyed = [core_scoped.obligation('K', reason, subject='s', key='stable') for reason in ('first wording', 'second wording')]
    assert keyed[0]['id'] == keyed[1]['id']  # an explicit stable diagnostic key, not wording, decides identity


def test_reconciliation_keeps_each_distinct_basis_error_once_across_prepare_apply_and_retry(tmp_path, monkeypatch):
    from laplace.manuscript import proposal_basis
    from laplace.manuscript import reconciliation
    from test_human_reconciliation import current_candidate, prepared_case
    case = current_candidate.__wrapped__(tmp_path, monkeypatch)
    errors = ['Required evidence A is absent.', 'Required evidence B is absent.']
    observed = {'develops': [], 'evidence': [], 'automatic_section_concepts': []}
    monkeypatch.setattr(proposal_basis, 'assess', lambda *a, **k: {**observed, 'errors': list(errors)})
    prepared, payload = prepared_case(case)
    first = [row['id'] for row in prepared['review_obligations']]
    assert len(first) == 2 and len(set(first)) == 2 and [r['reason'] for r in prepared['review_obligations']] == errors
    errors.append('Required evidence C is absent.')  # a new unresolved reason appears by validation time
    applied = proposals.decide(tmp_path, 'fixture', payload)['application']
    ids = [row['id'] for row in applied['review_obligations']]
    assert applied['complete'] and ids[:2] == first and len(ids) == 3 and len(set(ids)) == 3
    again = reconciliation.apply_candidate(tmp_path, 'fixture', {'candidate_ref': applied['candidate_ref']})['application']
    assert again['reused'] and [row['id'] for row in again['review_obligations']] == ids


# -- SP-R2: a next read whose needed premises exceed the bound is refused with a finite continuation --

def _overflowing_run(count=45):
    from laplace.pipeline.writing_organ.reader import ReadRun
    from laplace.pipeline.writing_organ.schema import ReaderState
    names = [f'REQ-{n}' for n in range(count)]
    run = ReadRun(state=ReaderState(summary='Earlier useful understanding.'))
    run.absorb('stretch-0', 'synthetic', {'findings': [], 'sentence_functions': [],
        'newly_established': {name: 'Required premise ' + name + '.' for name in names},
        'new_open_questions': ['Which design element meets ' + ' '.join(names) + '?'],
        'updated_summary': 'Earlier useful understanding. The requirements were introduced.', 'next_need': 'the crosswalk'}, 'reader')
    return run, names


def test_needed_premises_beyond_the_bound_refuse_only_the_normal_next_read_and_continue_in_focused_parts():
    from laplace.pipeline.writing_organ.reader import ReaderContextInsufficient
    from laplace.pipeline.writing_organ.schema import ReaderState
    run, names = _overflowing_run()
    state = run.state
    assert len(state.defined) + len(state.established) == ReaderState.MAX_HELD
    assert state.insufficient == names[ReaderState.MAX_HELD:] and state.missing_premises(names) == names[ReaderState.MAX_HELD:]
    assert set(run.history['established']) == set(names[ReaderState.MAX_HELD:])  # evicted meaning kept as history
    assert 'could NOT hold' in state.render() and 'REQ-44' in state.render()
    with pytest.raises(ReaderContextInsufficient) as refused:
        run.prompt('stretch-1', 'NEXT STRETCH ONLY.')
    details = refused.value.details
    assert details['continuation']['batches'] == [names[:40], names[40:]] and details['obligation']['kind'] == 'READER_CONTEXT_INSUFFICIENT'
    # The same unresolved overflow is one obligation however many stretches pass; useful state is kept.
    run.absorb('stretch-1', 'synthetic', {'findings': [], 'sentence_functions': [], 'updated_summary': state.summary + ' A mechanism.'}, 'reader')
    assert [o['id'] for o in run.obligations] == [details['obligation']['id']] and 'A mechanism.' in run.state.summary
    for batch in details['continuation']['batches']:
        prompt = run.prompt('stretch-1', 'NEXT STRETCH ONLY.', focus=batch)
        held = [name for name in names if '[' + name + ']' in prompt]
        assert set(batch) <= set(held) and len(held) <= ReaderState.MAX_HELD and 'could NOT hold' not in prompt
        assert 'This read covers only' in prompt and 'NEXT STRETCH ONLY.' in prompt and 'stretch-2' not in prompt
    with pytest.raises(ValueError):
        run.prompt('stretch-1', 'x', focus=names[:5])  # only an issued batch is a continuation
    # Closing the question that needed them ends the insufficiency; the normal read is admitted again.
    run.absorb('stretch-2', 'synthetic', {'findings': [], 'sentence_functions': [], 'updated_summary': run.state.summary,
                                         'closed_questions': list(run.state.open_questions), 'next_need': 'the summary'}, 'reader')
    assert run.state.admission() == {'sufficient': True} and run.prompt('stretch-3', 'NEXT.')


def test_the_five_premise_case_stays_a_normal_admitted_read():
    run, names = _overflowing_run(count=5)
    assert run.state.admission() == {'sufficient': True} and not run.obligations
    assert all('[' + name + ']' in run.prompt('stretch-1', 'NEXT.') for name in names)


# -- SP-R2 entry: one prepare/admit/render rule at every public reader entry --------------------------

def _fresh_overfull_state():
    from laplace.pipeline.writing_organ.schema import ReaderState
    names = [f'REQ-{n}' for n in range(45)]
    return ReaderState(established={name: 'Required premise ' + name + '.' for name in names},
                       open_questions=['Which design element meets ' + ' '.join(names) + '?'], summary='Useful prefix.'), names


def test_a_fresh_overfull_state_is_refused_at_direct_compile_and_render_does_not_discard_it():
    from laplace.pipeline.writing_organ.reader import ReaderContextInsufficient, compile_reader_prompt
    state, names = _fresh_overfull_state()
    with pytest.raises(ReaderContextInsufficient) as refused:
        compile_reader_prompt(state, 'stretch-0', 'NEXT ONLY.')
    assert refused.value.details['continuation']['batches'] == [names[:40], names[40:]]
    assert state.admission()['sufficient'] is False
    rendered = state.render()
    assert sum('[' + name + ']' in rendered for name in names) == 40 and 'could NOT hold' in rendered
    assert len(state.established) == 45 and not state.insufficient  # the caller's meanings are never discarded by an entry


def test_an_initial_run_archives_before_refusing_and_restores_every_focused_batch():
    from laplace.pipeline.writing_organ.reader import ReadRun, ReaderContextInsufficient
    state, names = _fresh_overfull_state()
    run = ReadRun(state=state)
    with pytest.raises(ReaderContextInsufficient) as refused:
        run.prompt('stretch-0', 'NEXT ONLY.')
    assert set(run.history['established']) == set(names[40:]) and len(run.state.established) == 40
    assert [o['id'] for o in run.obligations] == [refused.value.details['obligation']['id']]
    for batch in refused.value.details['continuation']['batches']:
        prompt = run.prompt('stretch-0', 'NEXT ONLY.', focus=batch)
        assert all('[' + name + '] Required premise ' + name + '.' in prompt for name in batch)
    assert 'Useful prefix.' in run.state.summary


def test_a_focused_read_without_restorable_history_is_refused_not_claimed():
    from laplace.pipeline.writing_organ.reader import ReadRun, ReaderContextInsufficient, compile_reader_prompt
    from laplace.pipeline.writing_organ.schema import ReaderState
    names = [f'REQ-{n}' for n in range(45)]
    bounded = ReaderState(established={name: 'Required premise.' for name in names[:40]}, insufficient=names[40:],
                          open_questions=['Which design element meets ' + ' '.join(names) + '?'])
    run = ReadRun(state=bounded)  # no history: the five meanings were never available to this run
    with pytest.raises(ReaderContextInsufficient) as normal:
        run.prompt('stretch-0', 'NEXT ONLY.')
    last = normal.value.details['continuation']['batches'][-1]
    assert last == names[40:]
    with pytest.raises(ReaderContextInsufficient) as focused:
        run.prompt('stretch-0', 'NEXT ONLY.', focus=last)
    details = focused.value.details
    assert details['missing'] == names[40:] and details['continuation'] == {'kind': 'restore-premises', 'missing': names[40:]}
    assert details['obligation']['key'] == 'focused-premises-unavailable'
    with pytest.raises(ValueError):
        run.prompt('stretch-0', 'NEXT ONLY.', focus=names[:3])  # an unissued focus is unsupported
    with pytest.raises(ReaderContextInsufficient):  # a directly asserted focus is checked the same way
        compile_reader_prompt(ReaderState(open_questions=['Map REQ-1.'], focus=['REQ-1']), 'x', 'NEXT ONLY.')
