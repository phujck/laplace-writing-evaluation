"""G1 (2026-10-15): a scoped, explicit, observation-only acknowledgement of reader inputs.

An unchanged authored subject (section contract or paragraph unit) may renew the observation of inputs the
author explicitly names, each at the pin the owner observes now, through the existing typed
section_contract / paragraph_plan upsert under the same plan, artifact and subject guards. Nothing else is
renewed; nothing authored changes; one bounded writing-reader-publication row is the durable receipt."""
import hashlib
import json

import pytest

from laplace.web import authoring as authoring_surface, project_work_surface
from laplace.manuscript import project_structure, storyboard
from laplace.native import tools as writing_tools
from laplace.writing import records
from laplace.writing.records import _fold as records_fold
from laplace.manuscript import reader_plan
from laplace.writing import records
from laplace.core import checkout
from test_reader_plan_owner import _section_fixture


def test_missing_visual_acknowledgement_and_old_null_history_remain_unqualified(tmp_path):
    from test_reader_plan_owner import _rendered_reader_plot
    manuscript,_,_=_section_fixture(tmp_path)
    change(tmp_path,detail(tmp_path)['paragraph_plan']['create_action'],changes={
        'function':'Explain','proposition':'Inspect the named visual.','input_nodes':[],
        'figure_anchor':'reader-plot'})
    row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    # Preserve an actual old-format null observation as historical input, not a
    # fabricated qualified visual. Reads must neither renew nor rewrite it.
    historical=json.loads(json.dumps(row['reader_basis']))
    historical['inputs']['figures:reader-plot']=reader_plan.fingerprint(None)
    historical['unobserved_inputs']=[]
    metadata={'path':historical['path'],'subjects':{row['paragraph_id']:historical},'reserved_ids':[]}
    records.bank(tmp_path,{'record':'writing-reader-publication','id':'RPUB-old-null',
                          'project':'book','reader_metadata':metadata})
    retained=publications(tmp_path)[-1]
    for door in ['native','http']:
        row=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
        assert row['input_currentness']['status']!='CURRENT' and row['diagnostics']
        pin=row['reader_basis']['inputs']['figures:reader-plot']
        before=len(publications(tmp_path))
        payload={**row['edit_action']['payload'],'changes':{},'input_observations':{'figures:reader-plot':pin}}
        if door=='native':
            with pytest.raises(ValueError,match='INPUT_UNRESOLVED'):
                writing_tools.execute(tmp_path,'book','work','structure_change',payload)
        else:
            code,_,raw=project_work_surface.handle('/work/structure/change',{},'POST',
                json.dumps({'project':'book',**payload}).encode(),repo_root=tmp_path)
            assert code>=400 and 'INPUT_UNRESOLVED' in raw.decode()
        assert len(publications(tmp_path))==before
    _rendered_reader_plot(tmp_path,manuscript)
    repaired=detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    change(tmp_path,repaired['edit_action'],changes={},input_observations=repaired['reader_basis']['inputs'])
    assert detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]['input_currentness']['status']=='CURRENT'
    assert next(r for r in publications(tmp_path) if r['id']=='RPUB-old-null')==retained


def detail(root, **scope):
    return project_structure.read('book', {'view': 'detail', 'section_ids': ['first'], **scope}, root)['sections'][0]


def change(root, action, **extra):
    return writing_tools.execute(root, 'book', 'work', 'structure_change', {**action['payload'], **extra})


def publications(root):
    path = root / records_fold._STORE
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []
    return [row for row in rows if row.get('record') == 'writing-reader-publication']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unobserved_contract(root, keys=('new-a',)):
    """A saved section contract whose newly declared citations were never observed."""
    from laplace.pipeline import registry
    record=registry.resolve('book',repo_root=root)
    manuscript=record.path(record.manuscript_dir,root)
    main=manuscript/'Fixture-Book.tex'
    if r'\bibliography{reader-observations}' not in main.read_text():
        main.write_text(main.read_text()+'\n'+r'\bibliography{reader-observations}'+'\n')
    bib=manuscript/'reader-observations.bib'
    text=bib.read_text() if bib.exists() else ''
    for key in keys:
        if '{'+key+',' not in text:text+='@article{'+key+', title={An actual observed fixture entry}}\n'
    bib.write_text(text)
    change(root, detail(root)['reader_transition']['edit_action'], changes={'entry_state': 'Knows the question'})
    result = change(root, detail(root)['reader_transition']['edit_action'], changes={'citations': list(keys)})
    assert result['input_currentness']['status'] == 'UNOBSERVED'
    return detail(root)['reader_transition']


def test_no_observations_or_an_empty_map_is_a_proved_no_op(tmp_path):
    manuscript, _, _ = _section_fixture(tmp_path)
    current = _unobserved_contract(tmp_path)
    before, rows = digest(manuscript / 'section_contracts.json'), len(publications(tmp_path))
    for extra in ({}, {'input_observations': {}}):
        result = change(tmp_path, current['edit_action'], changes={}, **extra)
        assert result['changed'] is False and result['plan_publication']['status'] == 'UNCHANGED'
        assert 'observation' not in result
    assert len(publications(tmp_path)) == rows and digest(manuscript / 'section_contracts.json') == before
    assert detail(tmp_path)['reader_transition']['input_currentness']['status'] == 'UNOBSERVED'


def test_contract_unobserved_to_current_only_for_the_explicitly_inspected_key(tmp_path):
    manuscript, _, _ = _section_fixture(tmp_path)
    current = _unobserved_contract(tmp_path, keys=('new-a', 'new-b'))
    action = current['edit_action']
    pins = action['payload']['expected_reader_basis']['inputs']
    before, rows = digest(manuscript / 'section_contracts.json'), len(publications(tmp_path))
    first = change(tmp_path, action, changes={}, input_observations={'citation:new-a': pins['citation:new-a']})
    assert first['changed'] is False and first['content_changed'] is False
    assert first['observation']['disposition'] == 'RECORDED' and first['observation']['acknowledged_inputs'] == ['citation:new-a']
    assert first['observation_publication'] == {**first['observation_publication'], 'status': 'COMMITTED', 'ledger_append_count': 1}
    assert first['input_currentness']['status'] == 'UNOBSERVED' and first['input_currentness']['unobserved_inputs'] == ['citation:new-b']
    assert digest(manuscript / 'section_contracts.json') == before          # authored bytes unchanged
    rows_after = publications(tmp_path)
    assert len(rows_after) == rows + 1
    receipt = rows_after[-1]
    assert receipt['id'] == first['observation']['receipt'] and 'artifact_id' not in receipt   # metadata only, no ART
    assert receipt['reader_metadata']['observation']['acknowledged_inputs'] == ['citation:new-a']
    # the second key is still unacknowledged; acknowledging it explicitly makes the subject CURRENT
    action = detail(tmp_path)['reader_transition']['edit_action']
    second = change(tmp_path, action, changes={}, input_observations={'citation:new-b': pins['citation:new-b']})
    assert second['input_currentness']['status'] == 'CURRENT'
    assert detail(tmp_path)['reader_transition']['input_currentness']['status'] == 'CURRENT'
    assert digest(manuscript / 'section_contracts.json') == before
    # an identical repeat appends nothing
    again = change(tmp_path, detail(tmp_path)['reader_transition']['edit_action'], changes={},
                   input_observations={'citation:new-b': pins['citation:new-b']})
    assert again['observation']['disposition'] == 'ALREADY_RECORDED' and again['observation']['receipt'] is None
    assert len(publications(tmp_path)) == rows + 2


def test_paragraph_stale_neighbor_is_acknowledged_without_text_or_order_change_and_a_moved_neighbor_refuses(tmp_path):
    manuscript, _, _ = _section_fixture(tmp_path)
    for text in ('Introduce the receipt', 'Use the preceding receipt'):
        change(tmp_path, detail(tmp_path)['paragraph_plan']['create_action'], changes={'proposition': text})
    first, second = detail(tmp_path)['paragraph_plan']['paragraphs']['items']
    change(tmp_path, second['edit_action'], changes={'proposition': 'Use the preceding receipt, revised'})
    first = detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    assert first['input_currentness']['status'] == 'STALE' and 'reader-neighbors' in first['input_currentness']['changed_inputs']
    narrative = next((manuscript / 'narrative').glob('*.json'))
    before, rows = digest(narrative), len(publications(tmp_path))
    pin = first['edit_action']['payload']['expected_reader_basis']['inputs']['reader-neighbors']
    # the neighbour moves after inspection: the inspected pin is no longer current, nothing is appended
    neighbour = detail(tmp_path)['paragraph_plan']['paragraphs']['items'][1]
    change(tmp_path, neighbour['edit_action'], changes={'proposition': 'Moved after inspection'})
    moved_bytes, moved_rows = digest(narrative), len(publications(tmp_path))
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        change(tmp_path, first['edit_action'], changes={}, input_observations={'reader-neighbors': pin})
    assert len(publications(tmp_path)) == moved_rows and digest(narrative) == moved_bytes
    # re-read, inspect the current neighbour pin, acknowledge it
    first = detail(tmp_path)['paragraph_plan']['paragraphs']['items'][0]
    pin = first['edit_action']['payload']['expected_reader_basis']['inputs']['reader-neighbors']
    result = change(tmp_path, first['edit_action'], changes={}, input_observations={'reader-neighbors': pin})
    assert result['observation']['disposition'] == 'RECORDED' and result['input_currentness']['status'] == 'CURRENT'
    after = detail(tmp_path)['paragraph_plan']['paragraphs']['items']
    assert [row['paragraph_id'] for row in after] == [first['paragraph_id'], neighbour['paragraph_id']]
    assert after[0]['proposition'] == 'Introduce the receipt' and digest(narrative) == moved_bytes
    assert after[0]['input_currentness']['status'] == 'CURRENT'
    assert len(publications(tmp_path)) == moved_rows + 1
    assert before != moved_bytes and rows < moved_rows


@pytest.mark.parametrize('fault', ['unknown-key', 'wrong-pin', 'malformed-pin', 'subject-revision', 'subject-id',
                                   'section', 'project', 'artifact-guard', 'plan-guard'])
def test_wrong_or_stale_guards_and_observations_refuse_without_effect(tmp_path, fault):
    manuscript, _, _ = _section_fixture(tmp_path)
    current = _unobserved_contract(tmp_path)
    payload = json.loads(json.dumps(current['edit_action']['payload']))
    pin = payload['expected_reader_basis']['inputs']['citation:new-a']
    observations = {'citation:new-a': pin}
    if fault == 'unknown-key': observations = {'citation:never-declared': pin}
    if fault == 'wrong-pin': observations = {'citation:new-a': 'sha256:' + '0' * 64}
    if fault == 'malformed-pin': observations = {'citation:new-a': 'not-a-pin'}
    if fault == 'subject-revision': payload['expected_reader_basis']['subject_revision'] = 'sha256:' + '1' * 64
    if fault == 'subject-id': payload['expected_reader_basis']['subject_id'] = 'second'
    if fault == 'section': payload['expected_reader_basis']['section_id'] = 'second'
    if fault == 'project': payload['expected_reader_basis']['project'] = 'other'
    if fault == 'artifact-guard': payload['expected_contract_revision'] = 'sha256:' + '2' * 64
    if fault == 'plan-guard': payload['expected_plan_revision'] = 'sha256:' + '3' * 64
    before, rows = digest(manuscript / 'section_contracts.json'), len(publications(tmp_path))
    with pytest.raises(ValueError):
        writing_tools.execute(tmp_path, 'book', 'work', 'structure_change',
                              {**payload, 'changes': {}, 'input_observations': observations})
    assert len(publications(tmp_path)) == rows and digest(manuscript / 'section_contracts.json') == before
    assert detail(tmp_path)['reader_transition']['input_currentness']['status'] == 'UNOBSERVED'


def test_native_and_http_reach_the_same_owner_and_a_failed_bank_is_truthful(tmp_path, monkeypatch):
    manuscript, _, _ = _section_fixture(tmp_path)
    current = _unobserved_contract(tmp_path)
    payload = current['edit_action']['payload']
    pin = payload['expected_reader_basis']['inputs']['citation:new-a']
    original = records.bank
    def refuse_reader_rows(root, row, *args, **kwargs):
        if row.get('record') == 'writing-reader-publication':
            raise OSError('fixture journal unavailable')
        return original(root, row, *args, **kwargs)
    rows = len(publications(tmp_path))
    with monkeypatch.context() as patch:
        patch.setattr(records, 'bank', refuse_reader_rows)
        patch.setattr(records, "bank", refuse_reader_rows)   # the owner reader_plan calls directly; scoped like the facade alias
        with pytest.raises(storyboard.PlanPublicationFailure) as caught:
            reader_plan.change('book', {**payload, 'changes': {}, 'input_observations': {'citation:new-a': pin}}, tmp_path)
    assert caught.value.details['plan_publication']['status'] == 'UNPROVED' and caught.value.details['plan_publication']['complete'] is False
    assert len(publications(tmp_path)) == rows
    code, _, raw = project_work_surface.handle('/work/structure/change', {}, 'POST', json.dumps(
        {'project': 'book', **payload, 'changes': {}, 'input_observations': {'citation:new-a': pin}}).encode(), repo_root=tmp_path)
    body = json.loads(raw)
    assert code == 200 and body['observation']['disposition'] == 'RECORDED' and body['changed'] is False
    native = change(tmp_path, detail(tmp_path)['reader_transition']['edit_action'], changes={},
                    input_observations={'citation:new-a': pin})
    assert native['observation']['disposition'] == 'ALREADY_RECORDED'
    assert set(native) == set(body)


def _architecture(root, summary):
    """A synthetic workspace architecture prior: changes ONLY the consumed `architecture` input pin
    (no plan, contract artifact or authored-subject byte changes)."""
    (root / 'profiles').mkdir(exist_ok=True)
    (root / 'profiles' / 'author_architecture.yaml').write_text(
        'profile:\n  narrative_arc:\n    summary: ' + json.dumps(summary) + '\n', encoding='utf-8')


def _guards(root, manuscript):
    return (digest(manuscript / 'section_contracts.json'), detail(root)['reader_transition']['edit_action']['payload']['expected_plan_revision'])


def test_a_substantive_edit_keeps_the_original_input_basis_semantics(tmp_path):
    """The content-save rule is deliberately conservative: a substantive edit records the basis its action
    CONSUMED. A genuinely changed input therefore stays STALE with its original pin, and an observation sent
    beside the edit cannot launder it."""
    _section_fixture(tmp_path)
    _architecture(tmp_path, 'Open with the question.')
    change(tmp_path, detail(tmp_path)['reader_transition']['edit_action'], changes={'entry_state': 'Knows the question'})
    old = detail(tmp_path)['reader_transition']
    assert old['input_currentness']['status'] == 'CURRENT'
    consumed = old['edit_action']['payload']['expected_reader_basis']['inputs']['architecture']
    _architecture(tmp_path, 'Open with the answer instead.')
    fresh = detail(tmp_path)['reader_transition']['edit_action']['payload']['expected_reader_basis']['inputs']['architecture']
    assert fresh != consumed
    result = change(tmp_path, old['edit_action'], changes={'exit_state': 'A real authored change'},
                    input_observations={'architecture': fresh})
    assert result['changed'] is True and 'observation' not in result
    assert result['reader_basis']['inputs']['architecture'] == consumed          # the original consumed pin
    assert result['input_currentness']['status'] == 'STALE' and result['input_currentness']['changed_inputs'] == ['architecture']
    readback = detail(tmp_path)['reader_transition']['input_currentness']
    assert (readback['status'], readback['changed_inputs']) == ('STALE', ['architecture'])
    recorded = records.index(tmp_path).reader_subjects
    assert next(value for key, value in recorded.items() if key[-1] == 'first')['inputs']['architecture'] == consumed


def test_an_old_or_altered_expected_input_basis_refuses_the_observation_without_effect(tmp_path):
    """G1-R1: an observation is admitted only against the CURRENT input facts its action carries. A changed
    consumed input (no artifact change), or an expected identity map that is altered, missing a key or carries
    an extra one, refuses before any idempotency or append; a fresh exact basis then succeeds."""
    manuscript, _, _ = _section_fixture(tmp_path)
    _architecture(tmp_path, 'Open with the question.')
    _unobserved_contract(tmp_path)
    old = detail(tmp_path)['reader_transition']['edit_action']
    _architecture(tmp_path, 'Open with the answer instead.')
    fresh = detail(tmp_path)['reader_transition']['edit_action']
    pin = fresh['payload']['expected_reader_basis']['inputs']['architecture']
    assert pin != old['payload']['expected_reader_basis']['inputs']['architecture']
    guards, rows = _guards(tmp_path, manuscript), len(publications(tmp_path))
    with pytest.raises(ValueError, match='CHANGED_INPUT: expected_reader_basis.inputs'):
        change(tmp_path, old, changes={}, input_observations={'architecture': pin})
    assert len(publications(tmp_path)) == rows and _guards(tmp_path, manuscript) == guards
    # the fresh exact basis with ONE named key succeeds; the other unobserved citations keep their standing
    first = change(tmp_path, fresh, changes={}, input_observations={'architecture': pin})
    assert first['observation']['disposition'] == 'RECORDED'
    assert first['input_currentness']['status'] == 'UNOBSERVED'
    assert first['input_currentness']['unobserved_inputs'] == ['citation:new-a']
    rows = len(publications(tmp_path))

    def altered(edit):
        payload = json.loads(json.dumps(fresh['payload']))
        edit(payload['expected_reader_basis']['inputs'])
        return {'payload': payload}
    for fault in (lambda inputs: inputs.__setitem__('architecture', 'sha256:' + '0' * 64),
                  lambda inputs: inputs.pop('plan-section'),
                  lambda inputs: inputs.__setitem__('citation:ghost', 'sha256:' + '1' * 64)):
        # otherwise identical to a recorded observation (it would be ALREADY_RECORDED), still refused
        with pytest.raises(ValueError, match='CHANGED_INPUT: expected_reader_basis.inputs'):
            change(tmp_path, altered(fault), changes={}, input_observations={'architecture': pin})
    assert len(publications(tmp_path)) == rows and _guards(tmp_path, manuscript) == guards
    again = change(tmp_path, detail(tmp_path)['reader_transition']['edit_action'], changes={},
                   input_observations={'architecture': pin})
    assert again['observation']['disposition'] == 'ALREADY_RECORDED' and len(publications(tmp_path)) == rows


def test_reply_and_readback_agree_when_a_consumed_input_disappears(tmp_path):
    """G1-R2: the reply and the exact readback come from one standing projection over retained AND current
    identities. Acknowledging only the plan section does not drop the removed concept pin to say CURRENT."""
    manuscript, _, plan = _section_fixture(tmp_path)
    change(tmp_path, detail(tmp_path)['reader_transition']['edit_action'], changes={'entry_state': 'Knows the question'})
    assert 'concept:concept:first' in detail(tmp_path)['reader_transition']['reader_basis']['inputs']
    plan['sections'][0]['nodes_in_order'] = []          # an external input-scope change: the concept is no longer consumed
    (manuscript / 'projection_plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=1) + '\n')
    current = detail(tmp_path)['reader_transition']
    assert current['input_currentness']['status'] == 'STALE'
    assert set(current['input_currentness']['changed_inputs']) == {'plan-section', 'concept:concept:first'}
    pin = current['edit_action']['payload']['expected_reader_basis']['inputs']['plan-section']
    before = digest(manuscript / 'section_contracts.json')
    reply = change(tmp_path, current['edit_action'], changes={}, input_observations={'plan-section': pin})
    readback = detail(tmp_path)['reader_transition']
    assert reply['observation']['disposition'] == 'RECORDED'
    for key in ('status', 'changed_inputs', 'unobserved_inputs'):
        assert reply['input_currentness'][key] == readback['input_currentness'][key], key
    assert reply['input_currentness']['status'] == 'STALE'
    assert reply['input_currentness']['changed_inputs'] == ['concept:concept:first']
    assert 'concept:concept:first' in reply['reader_basis']['inputs']            # retained, never dropped
    assert readback['review']['status'] == 'NOT_REVIEWED' and digest(manuscript / 'section_contracts.json') == before
    # a partial acknowledgement over retained unobserved inputs agrees the same way
    _unobserved_contract(tmp_path, keys=('cite-x', 'cite-y'))
    action = detail(tmp_path)['reader_transition']['edit_action']
    pins = action['payload']['expected_reader_basis']['inputs']
    reply = change(tmp_path, action, changes={}, input_observations={'citation:cite-x': pins['citation:cite-x']})
    readback = detail(tmp_path)['reader_transition']['input_currentness']
    assert (reply['input_currentness']['status'], reply['input_currentness']['unobserved_inputs']) == ('UNOBSERVED', ['citation:cite-y'])
    for key in ('status', 'changed_inputs', 'unobserved_inputs'):
        assert reply['input_currentness'][key] == readback[key], key


def test_the_observation_contract_is_one_help_section_natively_and_over_http(tmp_path, monkeypatch):
    """The reader-state contract names the observation rule (changes:{} + input_observations, the exact
    expected basis, metadata-only publication, idempotency, no review) through the same help section for
    the native and HTTP doors; default help does not inline it (the help cap stays)."""
    from urllib.parse import urlencode, parse_qs
    from laplace.native.declarations import help_payload
    _section_fixture(tmp_path)
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    native = writing_tools.execute(tmp_path, 'book', 'work', 'help',
                                   {'operation': 'structure_change', 'section': 'reader_state_contract'})
    code, _, raw = authoring_surface.handle('/authoring/help', parse_qs(urlencode(
        {'project': 'book', 'mode': 'work', 'operation': 'structure_change', 'section': 'reader_state_contract'})), 'GET', b'')
    assert code == 200
    served = json.loads(raw)['help']['action']['value']
    assert served == native['action']['value'] == reader_plan.contract()
    text = served['observation']
    for phrase in ('changes:{}', 'input_observations', 'expected_reader_basis.inputs', 'CHANGED_INPUT',
                   'writing-reader-publication', 'ALREADY_RECORDED', 'no-op', 'Not review'):
        assert phrase in text, phrase
    assert 'input_observations {input' not in json.dumps(help_payload('structure_change', permitted=True))
