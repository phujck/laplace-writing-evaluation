"""Explicit packaging intent is not inferred project/scientific completion."""
import json

import pytest

from test_writing_eval_manifest import fixture, write, m
from test_writing_evaluation_export import exporter, verifier


def unbuilt(root, project='second'):
    for name in ('main.pdf', 'figure_manifest.json'):
        (root / f'projects/{project}/text/{name}').unlink()


def test_snapshot_is_explicit_and_does_not_create_outputs(tmp_path):
    fixture(tmp_path); unbuilt(tmp_path)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='incomplete'):
        m.build_many(tmp_path, ['first', 'second'])
    result = m.build_many(tmp_path, ['first', 'second'], intents={'second': 'current-project-snapshot'})
    assert result['project_intents'] == {'first': 'completed-manuscript', 'second': 'current-project-snapshot'}
    local = result['project_manifests']['second']
    assert set(local['required_project_files']) == {'source', 'plan', 'references', 'research_records'}
    outputs = local['project_closure']['generated_outputs']
    assert all(row['presence'] == 'ABSENT' and row['currentness'] == 'UNVERIFIED' for row in outputs.values())
    assert local['project_closure']['observed_lifecycle']['pipeline_state'] == 'NEVER_RUN'
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


@pytest.mark.parametrize('intents', [
    ['other=current-project-snapshot'], ['second=unknown'],
    ['second=current-project-snapshot', 'second=completed-manuscript'], ['second'],
])
def test_intent_admission_precedes_history_work(tmp_path, monkeypatch, intents):
    fixture(tmp_path)
    monkeypatch.setattr(m, '_rows', lambda *a: pytest.fail('history scanned before intent admission'))
    with pytest.raises(ValueError): m.build_many(tmp_path, ['first', 'second'], intents=intents)


@pytest.mark.parametrize('name', ['main.tex', 'projection_plan.json', 'references.json', 'research_records.json'])
def test_snapshot_keeps_required_source_and_record_closure(tmp_path, name):
    fixture(tmp_path); unbuilt(tmp_path)
    (tmp_path / 'projects/second/text' / name).unlink()
    with pytest.raises(ValueError): m.build(tmp_path, 'second', intent='current-project-snapshot')


@pytest.mark.parametrize('name,value', [
    ('figure_manifest.json', {'placed': [{'artefact': 'absent.pdf'}]}),
    ('figure_manifest.json', {'placed': 'malformed'}),
    ('figure_manifest.json', []),
    ('compile.json', {'pdf': 'main.pdf', 'status': 'CURRENT'}),
    ('compile.json', []),
    ('research_records.json', {'records': [{'result_path': 'main.pdf'}]}),
])
def test_snapshot_never_makes_required_or_malformed_output_optional(tmp_path, name, value):
    fixture(tmp_path); unbuilt(tmp_path)
    write(tmp_path, 'projects/second/text/' + name, value)
    with pytest.raises(ValueError): m.build(tmp_path, 'second', intent='current-project-snapshot')


def test_snapshot_rejects_missing_declared_graphic(tmp_path):
    fixture(tmp_path); unbuilt(tmp_path)
    write(tmp_path, 'projects/second/text/main.tex', r'\includegraphics{absent}')
    with pytest.raises(ValueError, match='graphic output'):
        m.build(tmp_path, 'second', intent='current-project-snapshot')


def test_present_pdf_is_pinned_without_inherited_currentness(tmp_path, monkeypatch):
    fixture(tmp_path)
    # A file is not build validation, and inventory must not reach user telemetry.
    from laplace.engine import telemetry
    monkeypatch.setattr(telemetry, 'state_dir', lambda *a, **k: pytest.fail('inherited telemetry'))
    local = m.build(tmp_path, 'second', intent='current-project-snapshot')
    output = local['project_closure']['generated_outputs']['build_pdf']
    assert output['presence'] == 'PRESENT' and output['currentness'] == 'UNVERIFIED'
    assert local['required_project_files']['build_pdf']['sha256'] == m._sha(b'second pdf')


def test_export_roundtrip_and_intent_disagreement(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root); unbuilt(root)
    target = tmp_path / 'export'
    report = exporter.export_projects(root, target, ['second'], intents={'second': 'current-project-snapshot'})
    assert report['project_intents'] == {'second': 'current-project-snapshot'}
    verified = verifier.verify(target)
    assert verified['ok'], verified['failures']
    assert not (target / 'projects/second/text/main.pdf').exists()
    path = target / 'release/export-manifest.json'
    report['project_intents']['second'] = 'completed-manuscript'
    path.write_text(json.dumps(report))
    assert any('intent mismatch' in row['reason'] for row in verifier.verify(target)['failures'])


def test_legacy_manifest_remains_strict(tmp_path):
    root=tmp_path/'source'; root.mkdir(); fixture(root)
    target=tmp_path/'export'; report=exporter.export(root,target,'second')
    path=target/'release/source-manifest.json'; selection=json.loads(path.read_text())
    for key in ('project_intent','project_closure'): selection.pop(key)
    path.write_text(json.dumps(selection))
    report.pop('project_intents'); report['source_manifest_sha256']=verifier.sha(path)
    (target/'release/export-manifest.json').write_text(json.dumps(report))
    assert verifier.verify(target)['ok']
    (target/'projects/second/text/main.pdf').unlink()
    assert any('incomplete' in row['reason'] for row in verifier.verify(target)['failures'])


def test_snapshot_does_not_relax_public_body_closure(tmp_path):
    root=tmp_path/'source'; root.mkdir(); fixture(root); unbuilt(root, 'first')
    body=next((root/'contract/writing_bodies').glob('*/*')); body.unlink()
    with pytest.raises(ValueError, match='body closure'):
        exporter.export(root, tmp_path/'out', 'first', intents={'first':'current-project-snapshot'})


def test_snapshot_does_not_relax_present_asset_fence(tmp_path):
    fixture(tmp_path); unbuilt(tmp_path)
    write(tmp_path, 'outside.pdf', 'not in manuscript')
    write(tmp_path, 'projects/second/text/figure_manifest.json',
          {'placed':[{'artefact':'../../../outside.pdf'}]})
    with pytest.raises(ValueError, match='figure artefact'):
        m.build(tmp_path, 'second', intent='current-project-snapshot')


def test_verifier_rejects_different_source_selection(tmp_path):
    root=tmp_path/'source'; root.mkdir(); fixture(root)
    target=tmp_path/'out'; report=exporter.export(root,target,'second')
    path=target/'release/source-manifest.json'; selection=json.loads(path.read_text())
    selection['projects']=['second','unselected']
    path.write_text(json.dumps(selection))
    report['source_manifest_sha256']=verifier.sha(path)
    (target/'release/export-manifest.json').write_text(json.dumps(report))
    assert any('selection mismatch' in row['reason'] for row in verifier.verify(target)['failures'])


@pytest.mark.parametrize('coordinate', [
    {'owner':'artifact','project':'second','scope':'project','path':'text/main.pdf'},
    {'owner':'artifact','project':'second','scope':'manuscript','path':'main.pdf'},
    {'scope':'manuscript','path':'projects/second/text/main.pdf'},
])
def test_current_required_coordinates_resolve_same_absent_target(tmp_path, coordinate):
    fixture(tmp_path); unbuilt(tmp_path)
    write(tmp_path, 'projects/second/text/research_records.json', {'records':[{'artifact':coordinate}]})
    with pytest.raises(ValueError, match='absent generated output'):
        m.build_many(tmp_path,['first','second'],intents={'second':'current-project-snapshot'})


@pytest.mark.parametrize('scope,path', [('project','text/main.pdf'),('manuscript','main.pdf')])
def test_other_selected_project_same_basename_is_not_conflated(tmp_path,scope,path):
    fixture(tmp_path); unbuilt(tmp_path)
    write(tmp_path,'projects/second/text/research_records.json',{'records':[{'artifact':
          {'owner':'artifact','project':'first','scope':scope,'path':path}}]})
    result=m.build_many(tmp_path,['first','second'],intents={'second':'current-project-snapshot'})
    assert result['project_manifests']['second']['project_closure']['generated_outputs']['build_pdf']['presence']=='ABSENT'


@pytest.mark.parametrize('coordinate', [
    {'owner':'artifact','project':'first','scope':'manuscript','path':'main.pdf'},
    {'owner':'artifact','project':'unknown','scope':'manuscript','path':'main.pdf'},
    {'owner':'artifact','project':'second','scope':'repository','path':'projects/second/text/main.pdf'},
    {'owner':'artifact','project':'second','scope':'project','path':'../first/text/main.pdf'},
    {'owner':'artifact','project':'second','scope':'project','path':'/tmp/main.pdf'},
    {'owner':'unknown','project':'second','scope':'project','path':'text/main.pdf'},
])
def test_unselected_unknown_or_escaping_current_reference_refuses(tmp_path,coordinate):
    fixture(tmp_path); unbuilt(tmp_path)
    write(tmp_path,'projects/second/text/research_records.json',{'records':[{'artifact':coordinate}]})
    with pytest.raises(ValueError): m.build(tmp_path,'second',intent='current-project-snapshot')


def test_retained_absence_and_history_are_not_current_required_bindings(tmp_path):
    fixture(tmp_path); unbuilt(tmp_path)
    old={'owner':'artifact','project':'second','scope':'project','path':'text/main.pdf','exists':False}
    write(tmp_path,'projects/second/text/research_records.json',
          {'records':[{'provenance':{'dependencies':[old]},'read_receipt':old}],
           'history':[{'record':{'artifact':old}}]})
    result=m.build(tmp_path,'second',intent='current-project-snapshot')
    assert result['project_closure']['generated_outputs']['build_pdf']['presence']=='ABSENT'


def test_current_coordinate_resolution_stays_metadata_only(tmp_path,monkeypatch):
    fixture(tmp_path); unbuilt(tmp_path)
    write(tmp_path,'projects/second/text/research_records.json',{'records':[{'artifact':
          {'owner':'artifact','project':'first','scope':'project','path':'text/main.pdf'}}]})
    from laplace.projects import artifacts
    from laplace.writing import records
    monkeypatch.setattr(artifacts,'read',lambda *a,**k:pytest.fail('body read'))
    monkeypatch.setattr(records,'fold_records',lambda *a,**k:pytest.fail('journal fold'))
    m.build_many(tmp_path,['first','second'],intents={'second':'current-project-snapshot'})


def test_cross_project_current_binding_roundtrip_uses_export_selection(tmp_path):
    root=tmp_path/'source'; root.mkdir(); fixture(root); unbuilt(root)
    write(root,'projects/first/text/references.json',{'associations':[]})
    write(root,'projects/second/text/research_records.json',{'records':[{'artifact':
          {'owner':'artifact','project':'first','scope':'manuscript','path':'main.pdf'}}]})
    target=tmp_path/'out'
    exporter.export_projects(root,target,['first','second'],intents={'second':'current-project-snapshot'})
    result=verifier.verify(target)
    assert result['ok'],result['failures']
