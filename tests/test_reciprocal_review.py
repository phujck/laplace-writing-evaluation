"""Reciprocal review: two writer/reviewer pairs under one research run policy, and a review
beside other running steps under the app-dispatch profile.

Public controlled owners on a temporary root; deterministic stand-in replies through the
actual preparation, admission, delivery, review and Work owners. No provider inference,
network or paid run.
"""
import copy
import hashlib
import json
import os
import re

import pytest

from laplace.pipeline import workflow_definitions as D, workflow_operations as F
from laplace.work import owner_discovery as O
from test_research_workflow_runs import run_root, start_run, finish  # noqa: F401  (fixture reused for the one-pair golden)


def step(sid, title, role, settings=None):
    return {'id': sid, 'title': title, 'parent_id': None, 'assignment': {'role': role, 'instructions': 'Do ' + title + '.', 'settings': settings or {}},
            'inputs': [], 'outputs': [], 'targets': []}


def reciprocal(policy=None, settings=None):
    """The Design view's 'Make these two review each other' result on a research definition."""
    review = {'input_policy': 'evidence-packet'}
    return {'schema_version': D.SCHEMA, 'title': 'Two drafts that review each other', 'description': '', 'layout': {},
        'settings': settings or {'provider': 'codex', 'model': 'public-model', 'effort': 'low'},
        'run_policy': policy or {'profile': D.RESEARCH_POLICY, 'max_iterations': 2, 'runtime_seconds': 300, 'advance': 'automatic-review', 'apply': 'human'},
        'steps': [step('a', 'Draft A', 'builder'), step('ra', 'Review of Draft A', 'adversary', review),
                  step('b', 'Draft B', 'builder'), step('rb', 'Review of Draft B', 'adversary', review)],
        'edges': [{'id': 'a-ra', 'from': 'a', 'to': 'ra', 'kind': 'control'}, {'id': 'ra-a', 'from': 'ra', 'to': 'a', 'kind': 'feedback'},
                  {'id': 'b-rb', 'from': 'b', 'to': 'rb', 'kind': 'control'}, {'id': 'rb-b', 'from': 'rb', 'to': 'b', 'kind': 'feedback'}]}


def codes(body, ids=None):
    result = F._preview(body, {'step_ids': ids or [s['id'] for s in body['steps']]})
    return result['support'], [(i['code'], i.get('step_id')) for i in result['issues']]


# ---- P1 admission (pure owner preview) ------------------------------------------------

def test_preview_admits_disjoint_pairs_and_names_the_step_of_each_refusal():
    body = reciprocal()
    assert codes(body) == ('SUPPORTED_CONFIGURATION', [])
    assert codes(D.starter_definition()) == ('SUPPORTED_CONFIGURATION', []), 'the one-pair starter is unchanged'
    crossing = copy.deepcopy(body); crossing['edges'].append({'id': 'ra-b', 'from': 'ra', 'to': 'b', 'kind': 'feedback'})
    assert codes(crossing) == ('REFUSED_CONFIGURATION', [('RESEARCH_EDGE_CROSSES_PAIRS', 'b')])
    swapped = copy.deepcopy(body); swapped['edges'][2]['to'] = 'ra'   # b -> ra: ra now has two writers, rb none, so no pair forms
    assert codes(swapped) == ('REFUSED_CONFIGURATION', [('RESEARCH_STEP_UNPAIRED', s) for s in ('a', 'ra', 'b', 'rb')]), 'no arrow joins two pairs here'
    loose = copy.deepcopy(body); loose['edges'] = [e for e in loose['edges'] if e['id'] != 'b-rb']
    assert codes(loose) == ('REFUSED_CONFIGURATION', [('DRAFT_REVIEW_EDGE_REQUIRED', 'b')]), 'rb answers only b, so the one cure is the arrow b -> rb'
    # unequal counts, and writers with no reviewer, say each writer needs its own reviewer (true for any number of pairs);
    # no writer and no reviewer at all keeps the original code; another role is named
    assert codes(body, ['a', 'ra', 'b']) == ('REFUSED_CONFIGURATION', [('RESEARCH_REVIEWER_PER_WRITER', None)])
    assert codes(body, ['a', 'b']) == ('REFUSED_CONFIGURATION', [('RESEARCH_REVIEWER_PER_WRITER', None)])
    other = copy.deepcopy(body); other['steps'].append(step('note', 'Notes', 'researcher'))
    assert codes(other, ['a', 'ra', 'note']) == ('REFUSED_CONFIGURATION', [('UNSUPPORTED_ROLE', 'note')])
    v2 = reciprocal({'profile': D.RESEARCH_POLICY_V2, 'max_iterations': 2, 'max_admissions': 8, 'deadline_seconds': 3000, 'runtime_seconds': 300,
                     'advance': 'automatic-review', 'apply': 'human', 'continuation_criteria': 'c', 'exit_criteria': 'e'})
    assert codes(v2) == ('REFUSED_CONFIGURATION', [('EXTENDED_POLICY_REQUIRES_PARENT_SYNTHESIS', None)])
    v2['steps'].append(step('syn', 'Synthesis', 'synthesis'))
    v2['edges'] += [{'id': 'ra-syn', 'from': 'ra', 'to': 'syn', 'kind': 'control'}, {'id': 'rb-syn', 'from': 'rb', 'to': 'syn', 'kind': 'control'}]
    assert codes(v2) == ('SUPPORTED_CONFIGURATION', []), 'one synthesis reading every pair'
    v2['edges'][-1]['kind'] = 'data'
    assert codes(v2)[1] == [('UNSUPPORTED_SYNTHESIS_INPUT', 'syn')]


def page_sentence(row):
    """The page's one wording of an issue row (issueText: the owner's message first, else the code's sentence)."""
    text = open(os.path.join(os.path.dirname(__file__), '..', 'src/laplace/web/static_shared/workspace-workflow-operation.mjs')).read()
    if row.get('message'): return row['message']
    found = re.search(row['code'] + r":'([^']*)'", text)
    return found.group(1) if found else None


def one_pair():
    body = reciprocal(); body['steps'] = body['steps'][:2]; body['edges'] = body['edges'][:2]
    return body


def pairs(n):
    body = reciprocal(); body['steps'] = []; body['edges'] = []
    for i in range(n):
        w, r = 'w%d' % i, 'r%d' % i
        body['steps'] += [step(w, 'Draft %d' % i, 'builder'), step(r, 'Review %d' % i, 'adversary', {'input_policy': 'evidence-packet'})]
        body['edges'] += [{'id': w + '-' + r, 'from': w, 'to': r, 'kind': 'control'}, {'id': r + '-' + w, 'from': r, 'to': w, 'kind': 'feedback'}]
    return body


def test_one_pair_refusals_keep_the_base_code_and_crossing_is_said_only_of_two_pairs():
    """Judge r1 A1-A5, A8: an arrow is said to join different pairs only when its two ends are in different pairs."""
    other = 'These connections are not supported by this review profile.'
    crosses = 'This arrow joins different writer and reviewer pairs. Each reviewer reads and answers only its own writer.'
    a1 = one_pair(); a1['edges'].append({'id': 'a-ra-data', 'from': 'a', 'to': 'ra', 'kind': 'data'})
    a3 = one_pair(); a3['edges'].append({'id': 'a-ra-fb', 'from': 'a', 'to': 'ra', 'kind': 'feedback'})
    a4 = one_pair(); a4['steps'].append(step('x', 'Notes', 'builder')); a4['edges'].append({'id': 'x-a', 'from': 'x', 'to': 'a', 'kind': 'data'})
    for body, ids in ((a1, None), (a3, None), (a4, ['a', 'ra'])):
        result = F._preview(body, {'step_ids': ids or [s['id'] for s in body['steps']]})
        assert result['issues'] == [{'code': 'UNSUPPORTED_RESEARCH_TOPOLOGY'}], 'the base\'s code and row, unchanged for one pair'
        assert page_sentence(result['issues'][0]) == other
    a5 = pairs(2); a5['edges'].append({'id': 'r0-w1', 'from': 'r0', 'to': 'w1', 'kind': 'feedback'})
    a8 = pairs(2); a8['edges'].append({'id': 'w0-w1', 'from': 'w0', 'to': 'w1', 'kind': 'control'})
    for body, edge in ((a5, 'r0-w1'), (a8, 'w0-w1')):
        result = F._preview(body, {'step_ids': [s['id'] for s in body['steps']]})
        assert result['issues'] == [{'code': 'RESEARCH_EDGE_CROSSES_PAIRS', 'edge_id': edge, 'step_id': 'w1'}]
        assert page_sentence(result['issues'][0]) == crosses
    rows = F._preview(pairs(2), {'step_ids': ['w0', 'w1']})['issues']
    assert rows == [{'code': 'RESEARCH_REVIEWER_PER_WRITER'}] and page_sentence(rows[0]) == 'Each writer needs exactly one reviewer of its own, and each reviewer one writer.'


def test_one_pair_duplicate_arrows_are_admitted_as_at_the_base():
    """Judge r1 A2: the base admitted any number of draft and feedback arrows within its one pair; so does every pair."""
    dup = one_pair(); dup['edges'] += [{'id': 'ra-a-2', 'from': 'ra', 'to': 'a', 'kind': 'feedback'}, {'id': 'a-ra-2', 'from': 'a', 'to': 'ra', 'kind': 'control'}]
    assert codes(dup) == ('SUPPORTED_CONFIGURATION', [])
    two = reciprocal(); two['edges'].append({'id': 'rb-b-2', 'from': 'rb', 'to': 'b', 'kind': 'feedback'})
    assert codes(two) == ('SUPPORTED_CONFIGURATION', [])
    # a writer with only a feedback arrow from its reviewer is told to draw the draft arrow, as at the base
    back = one_pair(); back['edges'] = back['edges'][1:]
    assert codes(back) == ('REFUSED_CONFIGURATION', [('DRAFT_REVIEW_EDGE_REQUIRED', 'a')])


def test_pairs_per_run_comes_from_the_plan_and_prepare_contracts():
    """Judge r1 A6/A7: the preview admits no more pairs than one prepared run carries; the bound is read from the
    dispatch plan contract (packets, fan-out) and the prepare request contract (selected steps), never a literal."""
    from laplace.work import project_work as W
    plan = W.dispatch_plan_contract()['properties']
    request = next(c for c in D.native_change_contract()['oneOf'] if c['properties'].get('action', {}).get('const') == 'prepare')
    limit = min(plan['packets']['maxItems'], plan['fan_out_max']['maximum'], request['properties']['step_ids']['maxItems'])
    assert F.research_pairs_per_run() == limit // 2 == 4 and F.research_pairs_per_run(['syn']) == (limit - 1) // 2 == 3
    assert codes(pairs(4)) == ('SUPPORTED_CONFIGURATION', [])
    rows = F._preview(pairs(5), {'step_ids': [s['id'] for s in pairs(5)['steps']]})['issues']
    assert [r['code'] for r in rows] == ['RESEARCH_PAIRS_PER_RUN'] and rows[0]['max_pairs'] == 4
    assert page_sentence(rows[0]) == 'One run takes at most 4 writer and reviewer pairs; this selection has 5.'
    v2 = {'profile': D.RESEARCH_POLICY_V2, 'max_iterations': 2, 'max_admissions': 8, 'deadline_seconds': 3000, 'runtime_seconds': 300,
          'advance': 'automatic-review', 'apply': 'human', 'continuation_criteria': 'c', 'exit_criteria': 'e'}
    for n, support in ((3, 'SUPPORTED_CONFIGURATION'), (4, 'REFUSED_CONFIGURATION')):
        body = pairs(n); body['run_policy'] = v2; body['steps'].append(step('syn', 'Synthesis', 'synthesis'))
        body['edges'] += [{'id': 'r%d-syn' % i, 'from': 'r%d' % i, 'to': 'syn', 'kind': 'control'} for i in range(n)]
        result = F._preview(body, {'step_ids': [s['id'] for s in body['steps']]})
        assert result['support'] == support, n
    assert page_sentence(result['issues'][0]) == 'One run takes at most 3 writer and reviewer pairs beside its synthesis; this selection has 4.'
    assert page_sentence({'code': 'RESEARCH_PAIRS_PER_RUN'}) == 'This selection has more writer and reviewer pairs than one run takes.'


def test_prepare_admits_and_refuses_the_same_set_as_the_preview(pair_root):
    """Judge r1 B1-B3 through the actual owners: four pairs prepare; five are refused by compile_plan with the preview's
    code (the prepare request contract holds at most eight selected steps, so the door refuses ten ids before compiling);
    a one-pair duplicate feedback arrow prepares as at the base; a data arrow in one pair keeps the base's code and sentence."""
    from laplace.writing import workflow_progression as P
    s = pair_root
    four = pairs(4); ids = [x['id'] for x in four['steps']]
    assert s['prepare'](four, 'probe-four', ids=ids).startswith('WORK-')
    five = pairs(5); ids = [x['id'] for x in five['steps']]
    caller = D.native_caller(s['root'], 'book', 'work', s['parent']['turn_id'])
    with pytest.raises(D.Refused) as refused:
        P.compile_plan(s['root'], caller, {}, five, {'step_ids': ids}, None)
    assert refused.value.details == {'code': 'RESEARCH_PAIRS_PER_RUN', 'max_pairs': 4, 'pairs': 5}
    assert str(refused.value) == 'RESEARCH_PAIRS_PER_RUN: One run takes at most 4 writer and reviewer pairs; this selection has 5.'
    with pytest.raises(D.Refused) as refused:
        s['prepare'](five, 'probe-five', ids=ids, fan_out=8)
    assert refused.value.details == {'code': 'INVALID_APP_PREPARATION'}, 'the request contract refuses ten selected steps first'
    dup = one_pair(); dup['edges'].append({'id': 'ra-a-2', 'from': 'ra', 'to': 'a', 'kind': 'feedback'})
    assert s['prepare'](dup, 'probe-dup', ids=['a', 'ra']).startswith('WORK-')
    data = one_pair(); data['edges'].append({'id': 'a-ra-data', 'from': 'a', 'to': 'ra', 'kind': 'data'})
    with pytest.raises(D.Refused) as refused:
        s['prepare'](data, 'probe-data', ids=['a', 'ra'])
    assert str(refused.value) == 'UNSUPPORTED_RESEARCH_TOPOLOGY: Only draft→review and bounded review→revision are executable here.'


def test_every_new_issue_code_has_one_sentence_in_the_page_map():
    text = open(os.path.join(os.path.dirname(__file__), '..', 'src/laplace/web/static_shared/workspace-workflow-operation.mjs')).read()
    line = next(row for row in text.splitlines() if row.startswith('export const issueText='))
    for code in ('RESEARCH_EDGE_CROSSES_PAIRS', 'RESEARCH_STEP_UNPAIRED', 'RESEARCH_REVIEWER_PER_WRITER', 'RESEARCH_PAIRS_PER_RUN', 'UNSUPPORTED_SYNTHESIS_INPUT',
                 'EXTENDED_POLICY_REQUIRES_PARENT_SYNTHESIS', 'CONTEXT_REQUIRES_EVIDENCE_PACKET_PROFILE'):
        assert line.count(code + ':') == 1, code


def beside():
    """Two builders; each review reads only its own builder, so a review runs beside the other builder."""
    return {'schema_version': D.SCHEMA, 'title': 'Draft, compare, each checked', 'description': '', 'layout': {},
        'settings': {'provider': 'codex', 'model': 'fixture-model', 'effort': 'low'},
        'steps': [step('draft', 'Write the summary', 'builder'), step('compare', 'Compare both weeks', 'builder'),
                  step('check', 'Check the summary', 'adversary'), step('check2', 'Check the comparison', 'adversary')],
        'edges': [{'id': 'draft-check', 'from': 'draft', 'to': 'check', 'kind': 'control'},
                  {'id': 'compare-check2', 'from': 'compare', 'to': 'check2', 'kind': 'control'}]}


def test_app_dispatch_preview_admits_a_review_of_its_own_builders_and_still_refuses_feedback():
    assert codes(beside()) == ('SUPPORTED_CONFIGURATION', [])
    looped = beside(); looped['edges'].append({'id': 'back', 'from': 'check', 'to': 'draft', 'kind': 'feedback'})
    assert ('UNSUPPORTED_CLOSED_CONTROL_INPUT', None) in codes(looped)[1], 'feedback edges stay refused on the app-dispatch path'
    judged = beside(); judged['edges'].append({'id': 'j', 'from': 'check', 'to': 'check2', 'kind': 'control'})
    assert ('UNSUPPORTED_CARRIER_DEPENDENCIES', 'check2') in codes(judged)[1], 'a review reads builders only'
    fed = beside(); fed['edges'].append({'id': 'w', 'from': 'draft', 'to': 'compare', 'kind': 'control'})
    assert ('UNSUPPORTED_CARRIER_DEPENDENCIES', 'compare') in codes(fed)[1], 'a builder has no inputs'


def test_dispatch_dependencies_honour_a_declared_judge_input_and_refuse_anything_else():
    from laplace.work import project_work as W
    packets = [{'packet': 'w1', 'role': 'worker'}, {'packet': 'w2', 'role': 'worker'}, {'packet': 'j1', 'role': 'judge', 'depends_on': ['w1']},
               {'packet': 'j2', 'role': 'judge'}]
    assert W.dispatch_dependencies(packets, 'j1') == ['w1'] and W.dispatch_dependencies(packets, 'j2') == ['w1', 'w2']
    for wrong in (['j2'], ['w1', 'w1'], [], ['later']):
        bad = copy.deepcopy(packets); bad[2]['depends_on'] = wrong
        with pytest.raises(ValueError, match='earlier worker'):W.dispatch_dependencies(bad, 'j1')
    worker = copy.deepcopy(packets); worker[1]['depends_on'] = ['w1']
    with pytest.raises(ValueError, match='earlier worker'):W.dispatch_dependencies(worker, 'w2')
    from jsonschema import Draft202012Validator
    plan = {'schema_version': 'laplace.dispatch-plan/1', 'fan_out_max': 4, 'packets': [
        {**p, 'scope': 'project', 'brief': 'b', 'return_path': p['packet'] + '.json'} for p in packets]}
    assert not list(Draft202012Validator(W.dispatch_plan_contract()).iter_errors(plan))


@pytest.fixture
def app_root(tmp_path, monkeypatch, register_project):
    import runtime_guard
    from laplace.writing import records, child_hosts, provider, provider_catalogue
    runtime_guard.arm(monkeypatch)
    monkeypatch.delenv('LAPLACE_CUSTODY_LIVE', raising=False)
    register_project(tmp_path, 'book')
    catalogue = {'providers': [{'id': 'codex', 'available': True, 'models': [{'id': 'fixture-model', 'default_effort': 'low', 'efforts': ['low']}]}]}
    monkeypatch.setattr(provider, 'capabilities', lambda *a, **k: catalogue)
    monkeypatch.setattr(provider_catalogue, 'provider_catalogue', lambda *a: catalogue)
    records.bank(tmp_path, {'record': 'writing-session', 'id': 'WS-parent', 'project': 'book', 'role': 'author', 'provider': 'codex'})
    records.bank(tmp_path, {'record': 'writing-turn', 'id': 'prepare-turn', 'session_id': 'WS-parent', 'project': 'book', 'mode': 'work'})
    child_hosts._begin_child_execution(tmp_path, 'WS-parent', {'state': 'RUNNING', 'turn_id': 'prepare-turn',
        'project': 'book', 'session_id': 'WS-parent', 'host': child_hosts._process_identity()})
    return tmp_path, D.native_caller(tmp_path, 'book', 'work', 'prepare-turn')


def test_app_dispatch_prepares_each_review_with_its_own_builders(app_root):
    from laplace.writing import workflow_dispatch as A
    from laplace.work import project_work as W
    root, caller = app_root
    saved = D.save(root, O.project_scope('book', 'sdk'), {'request_id': 'save-beside', 'expected_revision': None, 'definition': beside()})
    prepared = D.prepare(root, caller, {'profile': D.APP_PROFILE, 'request_id': 'prepare-beside', 'reference': saved['reference'],
        'step_ids': ['draft', 'compare', 'check', 'check2'], 'goal': 'Each result checked independently.', 'fan_out_max': 4})
    task = W._tasks('book', root)[prepared['work']['id']]
    plan, pin, _ = A._checked(root, 'book', task)
    by = {pin['step_packets'][sid]: sid for sid in pin['step_ids']}
    packets = {by[p['packet']]: p for p in plan['packets']}
    assert [by[p['packet']] for p in plan['packets']] == ['draft', 'compare', 'check', 'check2']
    assert packets['check']['depends_on'] == [pin['step_packets']['draft']] and packets['check2']['depends_on'] == [pin['step_packets']['compare']]
    assert 'depends_on' not in packets['draft'] and 'depends_on' not in packets['compare']
    # the run read's prepared dependencies (what the river draws arrows from) follow the declared inputs
    view = W.dispatch_view(task, 'book', root)
    assert A._prepared_dependencies(pin, view['dependencies'])['edges'] == [
        {'prerequisite_step_id': 'draft', 'dependent_step_id': 'check'}, {'prerequisite_step_id': 'compare', 'dependent_step_id': 'check2'}]
    # a review of every earlier builder keeps the original packet: no depends_on is written
    every = beside(); every['steps'] = every['steps'][:3]
    every['edges'] = [{'id': 'd', 'from': 'draft', 'to': 'check', 'kind': 'control'}, {'id': 'c', 'from': 'compare', 'to': 'check', 'kind': 'control'}]
    saved = D.save(root, O.project_scope('book', 'sdk'), {'request_id': 'save-every', 'expected_revision': None, 'definition': every})
    other = D.prepare(root, caller, {'profile': D.APP_PROFILE, 'request_id': 'prepare-every', 'reference': saved['reference'],
        'step_ids': ['draft', 'compare', 'check'], 'goal': 'One check of both.', 'fan_out_max': 3})
    plan2, _, _ = A._checked(root, 'book', W._tasks('book', root)[other['work']['id']])
    assert all('depends_on' not in p for p in plan2['packets'])
    # an unreviewed builder is still refused by the carrier's own validator
    lone = beside(); lone['steps'] = lone['steps'][:3]; lone['edges'] = lone['edges'][:1]
    saved = D.save(root, O.project_scope('book', 'sdk'), {'request_id': 'save-lone', 'expected_revision': None, 'definition': lone})
    with pytest.raises(Exception, match='UNREVIEWED-BUILDER'):
        D.prepare(root, caller, {'profile': D.APP_PROFILE, 'request_id': 'prepare-lone', 'reference': saved['reference'],
            'step_ids': ['draft', 'compare', 'check'], 'goal': 'Refused.', 'fan_out_max': 3})


# ---- P2/P3 execution of two pairs -------------------------------------------------------

@pytest.fixture
def pair_root(tmp_path, monkeypatch):
    from test_writing_operating import _project
    from laplace.writing import provider, provider_catalogue, turn_execution as X, turn_admission as T
    from laplace.work import project_work as W, work_delivery as WD, object_facets
    manuscript = _project(tmp_path)
    catalogue = {'providers': [{'id': 'codex', 'available': True, 'models': [
        {'id': 'public-model', 'supports_effort': True, 'efforts': ['low']}, {'id': 'other-model', 'supports_effort': True, 'efforts': ['low']}]}]}
    monkeypatch.setattr(provider, 'capabilities', lambda *a, **k: copy.deepcopy(catalogue))
    monkeypatch.setattr(provider_catalogue, 'provider_catalogue', lambda *a, **k: copy.deepcopy(catalogue))
    monkeypatch.setattr(provider, 'context_window_advertised', lambda *a, **k: None)
    launches = []; monkeypatch.setattr(X, 'start', launches.append)
    parent = T.start_turn(tmp_path, {'project': 'book', 'mode': 'work', 'provider': 'codex', 'model': 'public-model', 'effort': 'low',
        'text': 'Prepare two drafts that review each other.', 'request_id': 'pair-author', 'selection': {'files': ['main.tex']}})
    reference = object_facets.ref('domain.projects', 'source-file', project='book', path='main.tex', scope='manuscript')
    entry = object_facets.request(tmp_path, O.project_scope('book', 'sdk'), {'facet': 'object', 'reference': reference, 'section': 'body', 'offset': 0, 'limit': 4000})['input_descriptor']
    caller = D.native_caller(tmp_path, 'book', 'work', parent['turn_id'])

    def prepare(body, request, ids=('a', 'ra', 'b', 'rb'), fan_out=None):
        saved = D.save(tmp_path, O.project_scope('book', 'sdk'), {'request_id': 'save-' + request, 'expected_revision': None, 'definition': body})
        prepared = D.prepare(tmp_path, caller, {'profile': D.APP_PROFILE, 'request_id': request, 'reference': saved['reference'],
            'step_ids': list(ids), 'goal': 'Two reviewed proposals, awaiting human manuscript Apply.', 'fan_out_max': fan_out or len(ids),
            'inputs': [entry], 'selection': {'files': ['main.tex']}})
        return prepared['work']['id']

    def bind(work, name, effect, model='public-model'):
        return WD.handle(tmp_path, 'book', {'action': 'workflow-bind', 'request_id': 'approve-' + name + '-' + model, 'work_id': work,
            'expected_work_revision': W._task_revision(W._tasks('book', tmp_path)[work]), 'kind': 'app-owned', 'effect': effect,
            'provider': 'codex', 'model': model, 'effort': 'low'}, {'origin': 'human'})['binding']['id']

    def start(work, recipients, request='pair-start'):
        from laplace.writing import workflow_progression as P
        return WD.handle(tmp_path, 'book', {'action': 'workflow-start', 'work_id': work, 'request_id': request,
            'expected_run_revision': P.view(tmp_path, 'book', work)['revision'], 'recipients': recipients}, {'origin': 'native', 'turn_id': parent['turn_id']})
    yield {'root': tmp_path, 'manuscript': manuscript, 'launches': launches, 'prepare': prepare, 'bind': bind, 'start': start, 'parent': parent}
    for launch in launches:
        if not launch.job.get('done'):X._finish(launch, {'status': 'interrupted'})


def proposal(after):
    return {'answer': 'Scoped proposal.', 'edits': [{'file': 'main.tex', 'line_start': 3, 'line_end': 3, 'before': 'Original prose.', 'after': after, 'reason': 'Clarity.'}]}


def judged(verdict, *findings):
    return {'status': 'completed', 'text': json.dumps({'verdict': verdict, 'findings': [{'id': f, 'summary': 'Finding ' + f + '.'} for f in findings]})}


def by_step(launches, step_id):
    return [l for l in launches if (l.workflow_execution or {}).get('step_id') == step_id]


def test_two_pairs_prepare_run_and_each_reviewer_gates_only_its_own_writer(pair_root):
    from laplace.writing import workflow_progression as P, workflow_dispatch as A
    from laplace.work import project_work as W, work_delivery as WD
    s = pair_root; root = s['root']; work = s['prepare'](reciprocal(), 'pair-prepare')
    plan, pin, _ = A._checked(root, 'book', W._tasks('book', root)[work])
    spec = pin['research_workflow']
    assert spec['pairs'] == [{'writer': 'a', 'reviewer': 'ra'}, {'writer': 'b', 'reviewer': 'rb'}] and 'writer' not in spec
    packets = {p['packet']: p for p in plan['packets']}
    assert len(packets) == 4 and len({p['return_path'] for p in plan['packets']}) == 4, 'two pairs share no packet or return path'
    assert packets[pin['step_packets']['ra']]['depends_on'] == [pin['step_packets']['a']] and packets[pin['step_packets']['rb']]['depends_on'] == [pin['step_packets']['b']]
    obligations = [o['id'] for o in W._tasks('book', root)[work]['review_obligations']]
    assert obligations == ['independent-draft-review-a', 'independent-draft-review-b']
    recipients = {'writer': s['bind'](work, 'writer', 'proposal-writer'), 'reviewer': s['bind'](work, 'reviewer', 'independent-review')}
    s['start'](work, recipients)
    # every running pair's pending step is admitted: both writers start at once
    assert [l.workflow_execution['step_id'] for l in s['launches'][1:]] == ['a', 'b']
    view = P.view(root, 'book', work)
    assert view['state'] == 'RUNNING' and view['iteration'] == 1 and [p['next'] for p in view['pairs']] == ['writer', 'writer']
    assert {a['step_id'] for a in view['attempts']} == {'a', 'b'} and len({a['event_id'] for a in view['attempts']}) == 2
    assert view['prepared_dependencies']['edges'] == [{'prerequisite_step_id': 'a', 'dependent_step_id': 'ra'}, {'prerequisite_step_id': 'b', 'dependent_step_id': 'rb'}]
    finish(by_step(s['launches'], 'a')[-1], {'status': 'completed', 'text': 'A.', 'proposal': proposal('Draft A one.')})
    assert by_step(s['launches'], 'ra') and not by_step(s['launches'], 'rb'), 'A\'s reviewer starts beside B\'s running writer'
    finish(by_step(s['launches'], 'b')[-1], {'status': 'completed', 'text': 'B.', 'proposal': proposal('Draft B one.')})
    ra, rb = by_step(s['launches'], 'ra')[-1], by_step(s['launches'], 'rb')[-1]
    assert ra.workflow_execution['proposal']['turn_id'] == by_step(s['launches'], 'a')[-1].turn_id
    assert rb.workflow_execution['proposal']['turn_id'] == by_step(s['launches'], 'b')[-1].turn_id, 'each reviewer reads only its own writer'
    finish(rb, judged('ACCEPT'))
    view = P.view(root, 'book', work); lanes = {p['writer']: p for p in view['pairs']}
    assert lanes['b']['exit'] == 'AWAITING_HUMAN_APPLY' and lanes['a']['next'] == 'reviewer' and view['state'] == 'RUNNING'
    assert len(by_step(s['launches'], 'a')) == 1, 'B\'s ACCEPT neither stops nor restarts A'
    finish(ra, judged('REVISE', 'cutoff'))
    assert len(by_step(s['launches'], 'a')) == 2 and len(by_step(s['launches'], 'b')) == 1, 'A\'s REVISE reopens only A'
    view = P.view(root, 'book', work); lanes = {p['writer']: p for p in view['pairs']}
    assert lanes['a']['iteration'] == 2 and lanes['a']['judgement']['verdict'] == 'REVISE' and lanes['b']['judgement']['verdict'] == 'ACCEPT'
    assert view['iteration'] == 2 and lanes['b']['iteration'] == 1, 'the run\'s round is the furthest pair\'s; each pair keeps its own'
    finish(by_step(s['launches'], 'a')[-1], {'status': 'completed', 'text': 'A2.', 'proposal': proposal('Draft A two.')})
    finish(by_step(s['launches'], 'ra')[-1], judged('ACCEPT'))
    view = P.view(root, 'book', work)
    assert view['state'] == 'AWAITING_HUMAN_APPLY' and len(view['attempts']) == 6 and len({a['event_id'] for a in view['attempts']}) == 6
    lanes = {p['writer']: p for p in view['pairs']}
    assert lanes['a']['proposal']['handoff_id'] != lanes['b']['proposal']['handoff_id'], 'two pairs share no handoff'
    assert {lanes[w]['obligation_id'] for w in lanes} == {'independent-draft-review-a', 'independent-draft-review-b'}
    accepted = WD.handle(root, 'book', {'action': 'workflow-accept-boundary', 'work_id': work, 'request_id': 'pair-boundary',
        'expected_run_revision': view['revision']}, {'origin': 'human'})
    assert accepted['actions']['human_apply_a']['permitted'] and accepted['actions']['human_apply_b']['permitted']
    assert accepted['actions']['human_apply_a']['http']['payload']['turn_id'] != accepted['actions']['human_apply_b']['http']['payload']['turn_id']
    (root / 'two-pair-run.json').write_text(json.dumps({'plan': plan, 'view': accepted}, indent=1, default=str))


def test_a_pairs_revision_rounds_count_against_the_same_run_policy_bounds(pair_root):
    from laplace.writing import workflow_progression as P
    s = pair_root; root = s['root']; work = s['prepare'](reciprocal(), 'pair-bounds')
    s['start'](work, {'writer': s['bind'](work, 'writer', 'proposal-writer'), 'reviewer': s['bind'](work, 'reviewer', 'independent-review')})
    for round_ in (1, 2):
        finish(by_step(s['launches'], 'a')[-1], {'status': 'completed', 'text': 'A.', 'proposal': proposal('A ' + str(round_))})
        if round_ == 1:
            finish(by_step(s['launches'], 'b')[-1], {'status': 'completed', 'text': 'B.', 'proposal': proposal('B')})
            finish(by_step(s['launches'], 'rb')[-1], judged('ACCEPT'))
        finish(by_step(s['launches'], 'ra')[-1], judged('REVISE', 'x' + str(round_)))
    view = P.view(root, 'book', work); lanes = {p['writer']: p for p in view['pairs']}
    assert lanes['a']['exit'] == 'LIMIT_REACHED' and lanes['a']['iteration'] == 2, 'max_iterations 2 bounds this pair as it bounds one pair'
    assert lanes['b']['exit'] == 'AWAITING_HUMAN_APPLY' and view['state'] == 'LIMIT_REACHED'
    assert len(by_step(s['launches'], 'a')) == 2 and len(by_step(s['launches'], 'b')) == 1


def test_a_failed_writer_stops_only_its_pair_and_the_run_ends_partial(pair_root):
    from laplace.writing import workflow_progression as P
    s = pair_root; root = s['root']; work = s['prepare'](reciprocal(), 'pair-partial')
    s['start'](work, {'writer': s['bind'](work, 'writer', 'proposal-writer'), 'reviewer': s['bind'](work, 'reviewer', 'independent-review')})
    finish(by_step(s['launches'], 'a')[-1], {'status': 'failed', 'text': 'Provider error.'})
    view = P.view(root, 'book', work); lanes = {p['writer']: p for p in view['pairs']}
    assert lanes['a']['exit'] == 'PARTIAL' and lanes['b']['next'] == 'writer' and view['state'] == 'RUNNING'
    finish(by_step(s['launches'], 'b')[-1], {'status': 'completed', 'text': 'B.', 'proposal': proposal('B')})
    finish(by_step(s['launches'], 'rb')[-1], judged('ACCEPT'))
    view = P.view(root, 'book', work)
    assert view['state'] == 'PARTIAL' and not view['actions']['resume']['permitted']


def test_different_pair_settings_need_a_recipient_per_step_and_readdress_one_step(pair_root):
    from laplace.writing import workflow_progression as P
    from laplace.work import work_delivery as WD
    s = pair_root; root = s['root']; body = reciprocal()
    body['steps'][2]['assignment']['settings'] = {'model': 'other-model'}   # Draft B runs on another model
    work = s['prepare'](body, 'pair-settings')
    view = P.view(root, 'book', work)
    assert {'bind_writer', 'bind_reviewer', 'bind_b'} <= set(view['actions']) and 'bind_rb' not in view['actions']
    writer, reviewer, other = s['bind'](work, 'writer', 'proposal-writer'), s['bind'](work, 'reviewer', 'independent-review'), s['bind'](work, 'writer', 'proposal-writer', 'other-model')
    with pytest.raises(ValueError, match='settings'):s['start'](work, {'writer': writer, 'reviewer': reviewer}, 'pair-settings-one')
    s['start'](work, {'writer': writer, 'reviewer': reviewer, 'b': other}, 'pair-settings-steps')
    b = by_step(s['launches'], 'b')[-1]
    assert b.workflow_execution['prepared_settings']['values']['model'] == 'other-model'
    view = P.view(root, 'book', work)
    assert 'b' in view['actions']['readdress']['fields'][0]['choices']
    with pytest.raises(ValueError, match='settings'):
        WD.handle(root, 'book', {'action': 'workflow-readdress', 'work_id': work, 'request_id': 'pair-readdress-bad', 'expected_run_revision': view['revision'],
            'recipient': 'b', 'recipient_binding_id': writer}, {'origin': 'human'})
    done = WD.handle(root, 'book', {'action': 'workflow-readdress', 'work_id': work, 'request_id': 'pair-readdress', 'expected_run_revision': view['revision'],
        'recipient': 'b', 'recipient_binding_id': other}, {'origin': 'human'})
    assert done['state'] == 'RUNNING'


def test_synthesis_requirements_cover_every_pairs_returns():
    state = {'attempts': [{'event_id': 'WD-1'}, {'event_id': 'WD-2'}], 'pairs': {
        'a': {'proposal': {'id': 'ART-a', 'sha256': 'sha256:' + 'a' * 64}, 'judgement': {'turn_id': 'T-ra', 'verdict': 'ACCEPT', 'findings': []},
              'loop_history': [{'proposal': {'id': 'ART-a0', 'sha256': 'sha256:' + 'c' * 64}, 'judgement': {'turn_id': 'T-ra0', 'verdict': 'REVISE', 'findings': [{'id': 'f'}]}}]},
        'b': {'proposal': {'id': 'ART-b', 'sha256': 'sha256:' + 'b' * 64}, 'judgement': {'turn_id': 'T-rb', 'verdict': 'REVISE', 'findings': [{'id': 'g'}]}}}}
    required = F.synthesis_requirements(state, {'research_workflow': {'input_packet': {'id': 'ART-in', 'sha256': 'sha256:' + 'd' * 64}}})
    assert {(r['kind'], r['id']) for r in required} == {('input-packet', 'ART-in'), ('attempt-result', 'WD-1'), ('attempt-result', 'WD-2'),
        ('proposal', 'ART-a0'), ('judgement', 'T-ra0'), ('proposal', 'ART-a'), ('judgement', 'T-ra'), ('proposal', 'ART-b'), ('judgement', 'T-rb')}
    assert {r['id'] for r in F.synthesis_inputs(state, None, None)} >= {'ART-a', 'ART-b', 'T-ra', 'T-rb', 'T-ra0'}


def test_v2_two_pairs_prepare_with_one_synthesis_and_share_the_run_wide_budget(pair_root):
    from laplace.writing import workflow_progression as P, workflow_dispatch as A
    from laplace.work import project_work as W
    s = pair_root; root = s['root']
    v2 = reciprocal({'profile': D.RESEARCH_POLICY_V2, 'max_iterations': 3, 'max_admissions': 4, 'deadline_seconds': 3000, 'runtime_seconds': 300,
                     'advance': 'automatic-review', 'apply': 'human', 'continuation_criteria': 'A finding remains.', 'exit_criteria': 'None remains.'})
    with pytest.raises(D.Refused, match='EXTENDED_POLICY_REQUIRES_PARENT_SYNTHESIS'):s['prepare'](copy.deepcopy(v2), 'pair-v2-none')
    v2['steps'].append(step('syn', 'Synthesis', 'synthesis'))
    v2['edges'] += [{'id': 'ra-syn', 'from': 'ra', 'to': 'syn', 'kind': 'control'}, {'id': 'rb-syn', 'from': 'rb', 'to': 'syn', 'kind': 'control'}]
    work = s['prepare'](v2, 'pair-v2', ids=('a', 'ra', 'b', 'rb', 'syn'))
    plan, pin, _ = A._checked(root, 'book', W._tasks('book', root)[work])
    assert pin['synthesis']['step_id'] == 'syn' and isinstance(plan['synthesis_return_path'], str)
    s['start'](work, {'writer': s['bind'](work, 'writer', 'proposal-writer'), 'reviewer': s['bind'](work, 'reviewer', 'independent-review')})
    finish(by_step(s['launches'], 'a')[-1], {'status': 'completed', 'text': 'A.', 'proposal': proposal('A')})
    finish(by_step(s['launches'], 'b')[-1], {'status': 'completed', 'text': 'B.', 'proposal': proposal('B')})
    # four admissions are the authored run-wide budget: both pairs' writers and reviewers spend it
    finish(by_step(s['launches'], 'ra')[-1], judged('REVISE', 'x'))
    view = P.view(root, 'book', work)
    assert view['state'] == 'RUNNING' and len(view['attempts']) == 4
    lanes = {p['writer']: p for p in view['pairs']}
    assert lanes['a']['exit'] == 'LIMIT_REACHED' and lanes['a']['loop_exit']['reason'] == 'ADMISSIONS_INSUFFICIENT_FOR_NEXT_ITERATION'
    finish(by_step(s['launches'], 'rb')[-1], judged('ACCEPT'))
    view = P.view(root, 'book', work)
    assert view['state'] == 'LIMIT_REACHED' and view['synthesis']['due']
    kinds = [i['kind'] for i in view['synthesis']['inputs']]
    assert kinds.count('proposal') == 2 and kinds.count('judgement') == 2 and kinds.count('attempt-result') == 4, 'the synthesis reads every pair'


# ---- golden: a one-pair definition is unchanged ----------------------------------------

def _normal(value, root):
    """Fresh identities, digests and times by order of first appearance; everything else exact."""
    text = json.dumps(value, sort_keys=True, ensure_ascii=False).replace(str(root), '<root>')
    seen = {}
    def name(match):
        return seen.setdefault(match.group(0), '<%d>' % len(seen))
    text = re.sub(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(\+00:00|Z)?', '<time>', text)
    return re.sub(r'[0-9a-f]{12,}', name, text)


# The digest the one-pair route produced at the base commit (ac7950831), computed by this same
# function with the base tree's own code: the plan, the pin, every recorded run row and every event intent.
GOLDEN = 'sha256:ca1f4e59b459204ceb4a4e7c0358670d833f5253cf77efeb1a82a032b5e27c11'


def test_one_pair_plan_packets_and_run_rows_are_identical_to_the_base(run_root):
    from laplace.writing import workflow_progression as P
    from laplace.work import project_work as W
    s = run_root; root = s['root']
    task, plan, pin, _artifact, _state = P._load(root, 'book', s['work'])
    start_run(s)
    def proposal_(after):
        return {'answer': 'Public scoped proposal.', 'edits': [{'file': 'main.tex', 'line_start': 3, 'line_end': 3,
            'before': 'Original prose.', 'after': after, 'reason': 'Clarify the selected passage.'}]}
    finish(s['launches'][-1], {'status': 'completed', 'text': 'Public writer result.', 'proposal': proposal_('Draft one.')})
    finish(s['launches'][-1], {'status': 'completed', 'text': json.dumps({'verdict': 'REVISE', 'findings': [{'id': 'cutoff', 'summary': 'State it.'}]})})
    finish(s['launches'][-1], {'status': 'completed', 'text': 'Public revised writer result.', 'proposal': proposal_('Revised prose.')})
    finish(s['launches'][-1], {'status': 'completed', 'text': json.dumps({'verdict': 'ACCEPT', 'findings': []})})
    task = W._tasks('book', root)[s['work']]
    from laplace.work import work_delivery as WDm  # noqa: F401
    _, Dl = P._owners()
    rows = [{k: v for k, v in r.items() if k not in {'ts'}} for r in P._phase_rows(task)]
    events = [Dl._history(task, a['event_id'])[0] for a in rows[-1]['run']['attempts']]
    document = {'plan': plan, 'pin': pin, 'review_obligations': task.get('review_obligations'), 'runs': [r['run'] for r in rows],
                'phase_requests': [(r['action'], r['request_id']) for r in rows], 'events': events}
    normal = _normal(document, root)
    if os.environ.get('RECIPROCAL_GOLDEN_OUT'):
        open(os.environ['RECIPROCAL_GOLDEN_OUT'], 'w').write(normal)
    assert 'sha256:' + hashlib.sha256(normal.encode()).hexdigest() == GOLDEN


def test_contract_limits_are_derived_from_their_owners():
    from laplace.pipeline import workflow_definitions as D, workflow_operations as operations
    from laplace.work import project_work as W, work_delivery
    recipients = work_delivery.contract()['properties']['recipients']['anyOf'][0]
    assert re.compile(recipients['propertyNames']['pattern']).fullmatch('step-1_a') and not re.compile(recipients['propertyNames']['pattern']).fullmatch('-x')
    assert recipients['propertyNames']['pattern'] == D.local_id_schema_pattern()
    assert all(bool(D.LOCAL_ID.fullmatch(s)) == bool(re.fullmatch(D.local_id_schema_pattern(), s)) for s in ('a', 'a_b-9', '-a', 'a' * 80, 'a' * 81, 'a b'))
    assert recipients['maxProperties'] == 2 * operations.research_pairs_per_run() + 2
    plan = W.dispatch_plan_contract()['properties']['packets']
    packet = plan['items']['properties']
    assert packet['depends_on']['items'] is packet['packet']
    assert packet['depends_on']['maxItems'] == plan['maxItems'] - 1
