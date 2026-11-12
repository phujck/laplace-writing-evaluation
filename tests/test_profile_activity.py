"""Reached profile application labels from real candidate/decision owners."""
from laplace.work import history as author_history
from laplace.manuscript import profiles
from test_profile_candidates import fixture, propose


def applied_voice(root):
    fixture(root)
    candidate=propose(root,'voice','project',{'guidance':'State the key result first.'})
    return profiles.change('book',{'action':'apply','candidate_ref':candidate['candidate_ref']},root)


def test_voice_decision_target_uses_exact_candidate_family_without_body_hydration(tmp_path,monkeypatch):
    applied_voice(tmp_path)
    from laplace.representation import writing_bodies as bodies
    monkeypatch.setattr(bodies,'read_bytes',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('Activity hydrated a profile body')))
    items=author_history.history('book',{},tmp_path)['items']
    decision=next(row for row in items if row['summary']=='Profile preference decision')
    assert decision['targets'][0]['label']=='Voice preferences'


def test_completed_profile_application_keeps_its_start_as_historical_recorded_event(tmp_path):
    applied=applied_voice(tmp_path)
    items=author_history.history('book',{},tmp_path)['items']
    completed=next(row for row in items if row['id']=='activity:journal:'+applied['application_id'])
    started=next(row for row in items if row['summary']=='Profile application started')
    assert (started['status'],completed['status'],completed['summary'])==('recorded','applied','Profile preference applied')
