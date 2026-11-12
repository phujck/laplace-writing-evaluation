import json
import time
import pytest
from pathlib import Path

from laplace.web import research_surface as rs
from laplace.research import research_records
from laplace.research import research_catalogue
from laplace.research import research_runs
from laplace.research import research_observation
from laplace.research import research_runs   # the owners the code paths read (research family R1)
from laplace.pipeline import figure_runner as fr, visual_production as vp


def test_project_artifact_inspection_pages_searches_and_confines_real_paths(tmp_path):
    manuscript = _project(tmp_path)
    numerics = manuscript.parent / 'numerics'
    numerics.mkdir()
    source = numerics / 'large.json'
    source.write_text('évidence\n' + 'x' * 13000 + '\n"measured.score": 42\n')
    query = {'project':['fixture'], 'scope':['project'], 'path':['numerics/large.json'], 'format':['json']}
    status, _, raw = rs.handle('/research/artifact', query, 'GET', b'', repo_root=tmp_path)
    first = json.loads(raw)
    assert status == 200 and first['next_offset'] == 12000
    _, _, raw = rs.handle('/research/artifact', {**query, 'offset':['12000']}, 'GET', b'', repo_root=tmp_path)
    second = json.loads(raw)
    assert first['content'] + second['content'] == source.read_text()
    assert first['sha256'] == second['sha256']
    _, _, raw = rs.handle('/research/artifact', {**query, 'q':['measured.score']}, 'GET', b'', repo_root=tmp_path)
    assert json.loads(raw)['content'] == '3: "measured.score": 42'
    for path in ('../../outside.json', '../registry_projects.json'):
        assert rs.handle('/research/artifact', {**query, 'path':[path]}, 'GET', b'', repo_root=tmp_path)[0] == 404
    assert rs.handle('/research/artifact', {**query, 'scope':['unknown']}, 'GET', b'', repo_root=tmp_path)[0] == 422


def test_artifact_reader_serves_formal_source_and_vector_figures(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / 'Proof.lean').write_text('theorem answer : 2 * 2 = 4 := by decide\n')
    (manuscript / 'figure.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    (manuscript / 'diagram.tikz').write_text('\\begin{tikzpicture}\\node {A};\\end{tikzpicture}\n')
    (manuscript / 'lean-toolchain').write_text('leanprover/lean4:v4.19.0\n')

    lean = rs.handle('/research/artifact', {
        'project': ['fixture'], 'scope': ['manuscript'], 'path': ['Proof.lean'],
        'format': ['json']}, 'GET', b'', repo_root=tmp_path)
    svg = rs.handle('/research/artifact', {
        'project': ['fixture'], 'scope': ['manuscript'], 'path': ['figure.svg']},
        'GET', b'', repo_root=tmp_path)
    tikz = rs.handle('/research/artifact', {
        'project': ['fixture'], 'scope': ['manuscript'], 'path': ['diagram.tikz'],
        'format': ['json']}, 'GET', b'', repo_root=tmp_path)
    toolchain = rs.handle('/research/artifact', {
        'project': ['fixture'], 'scope': ['manuscript'], 'path': ['lean-toolchain'],
        'format': ['json']}, 'GET', b'', repo_root=tmp_path)

    assert lean[0] == 200 and 'theorem answer' in json.loads(lean[2])['content']
    assert svg[0] == 200 and svg[1] == 'image/svg+xml; charset=utf-8'
    assert tikz[0] == 200 and 'tikzpicture' in json.loads(tikz[2])['content']
    assert toolchain[0] == 200 and 'leanprover/lean4:v4.19.0' in json.loads(toolchain[2])['content']


def test_npz_artifact_projects_bounded_array_metadata_values_and_download(tmp_path):
    import numpy as np
    manuscript=_project(tmp_path);project=manuscript.parent
    archive=project/'arrays.npz'
    np.savez(archive,small=np.asarray([1.5,2.5],dtype=np.float32),
             matrix=np.zeros((40,3),dtype=np.int16))
    query={'project':['fixture'],'scope':['project'],'path':['arrays.npz'],'format':['json']}
    status,_,raw=rs.handle('/research/artifact',query,'GET',b'',repo_root=tmp_path)
    value=json.loads(raw)
    assert status==200 and value['kind']=='numpy-archive' and value['download_available'] is True
    assert [(row['name'],row['shape'],row['dtype']) for row in value['arrays']]==[
        ('small',[2],'float32'),('matrix',[40,3],'int16')]
    assert value['arrays'][0]['values']==[1.5,2.5]
    assert value['arrays'][1]['sample_values']==[0,0,0,0,0,0,0,0]
    assert 'Full values omitted' in value['arrays'][1]['values_note']
    assert 'small · shape 2 · float32' in value['content']
    downloaded=rs.handle('/research/artifact',{**query,'download':['1']},'GET',b'',repo_root=tmp_path)
    assert downloaded[0]==200 and downloaded[1]=='application/octet-stream'
    assert downloaded[2]==archive.read_bytes()


def test_npz_preview_serializes_complex_nonfinite_strings_bytes_and_structures_without_pickle(tmp_path):
    import numpy as np
    manuscript=_project(tmp_path);archive=manuscript.parent/'typed.npz'
    structured=np.asarray([(1.25,b'ok')],dtype=[('weight','<f4'),('tag','S2')])
    np.savez(archive,
        complex_values=np.asarray([[1+2j,-3+0.5j]],dtype=np.complex128),
        nonfinite=np.asarray([np.nan,np.inf,-np.inf],dtype=np.float64),
        strings=np.asarray(['alpha','β']),
        bytes_values=np.asarray([b'abc',b'\xff']),
        structured=structured,
        objects=np.asarray([{'unsafe':True}],dtype=object))
    status,_,raw=rs.handle('/research/artifact',{'project':['fixture'],'scope':['project'],
        'path':['typed.npz'],'format':['json']},'GET',b'',repo_root=tmp_path)
    value=json.loads(raw);rows={row['name']:row for row in value['arrays']}
    assert status==200
    assert rows['complex_values']['values']==[[{'real':1.0,'imag':2.0},{'real':-3.0,'imag':0.5}]]
    assert rows['nonfinite']['values']==['NaN','+Infinity','-Infinity']
    assert rows['strings']['values']==['alpha','β']
    assert rows['bytes_values']['values']==['abc',{'bytes_hex':'ff'}]
    assert rows['structured']['values']==[{'weight':1.25,'tag':'ok'}]
    assert 'values' not in rows['objects'] and rows['objects']['values_note']=='Object values are not loaded.'


def test_run_tracks_inputs_and_imported_code_before_and_after_execution(tmp_path):
    manuscript = _project(tmp_path)
    producer = manuscript / 'producer.py'
    helper = manuscript / 'helper.py'
    helper.write_text('FACTOR = 2\n')
    producer.write_text(
        'import argparse,json,sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).parent))\nfrom helper import FACTOR\n'
        "p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()\n"
        "Path(a.result).write_text(json.dumps({'value':sum(json.loads(Path('data.json').read_text()))*FACTOR}))\n"
        "if json.loads(a.args_json).get('change_input'): Path('data.json').write_text('[9]')\n")
    spec = {'id':'dependent', 'executable':'producer.py', 'modes':['smoke'],
            'allowed_args':{'change_input':'bool'}, 'dependencies':['helper.py','data.json']}
    assert research_runs.register_producer('fixture', spec, tmp_path)[0] == 201

    def run(args):
        status, out = research_runs.launch('fixture', {'producer_id':'dependent','mode':'smoke','args':args}, tmp_path)
        assert status == 202, out
        for _ in range(160):
            current = research_runs._run_status(manuscript, out['run']['id'])
            if current['state'] != 'RUNNING': return current
            time.sleep(.025)
        raise AssertionError('runner did not finish')

    done = run({})
    assert done['state'] == 'COMPLETE'
    assert json.loads(Path(done['result_absolute']).read_text())['value'] == 12
    status, recorded = research_records.record('fixture', {'kind':'result', 'id':'result:dependent',
        'run_id':done['id'], 'result':done['result_path'], 'summary':'Measured output.'}, tmp_path)
    assert status == 201, recorded
    presented = research_catalogue.state_payload('fixture', tmp_path)['results'][0]
    assert presented['producer']['executable'] == 'producer.py'
    assert presented['producer']['dependencies'] == ['helper.py', 'data.json']
    assert {key:presented['evidence_files'][0][key] for key in ('role','path','scope')} == {
        'role':'Code', 'path':'producer.py', 'scope':'manuscript'}
    assert any(row['role'] == 'Producer input' and row['path'] == 'helper.py'
               for row in presented['evidence_files'])
    assert {row['role'] for row in presented['evidence_files']} >= {
        'Recorded output', 'Run log', 'Run errors'}
    helper.write_text('FACTOR = 3\n')
    assert research_runs._run_status(manuscript, done['id'])['state'] == 'STALE'
    helper.write_text('FACTOR = 2\n')
    (manuscript / 'data.json').write_text('[9]')
    assert research_runs._run_status(manuscript, done['id'])['state'] == 'STALE'
    (manuscript / 'data.json').write_text('[1, 2, 3]')
    changed_during_run = run({'change_input':True})
    assert changed_during_run['state'] == 'STALE'
    assert 'during execution' in changed_during_run['reason']
    helper.unlink()
    assert research_runs.launch('fixture', {'producer_id':'dependent','mode':'smoke','args':{}}, tmp_path)[0] == 422
    assert research_runs.register_producer('fixture', {**spec,'dependencies':['../../outside.json']}, tmp_path)[0] == 422


def test_research_catalogue_is_summary_first_and_exact_result_is_lazy(tmp_path):
    manuscript=_project(tmp_path);(manuscript/'result.json').write_text('{"score":2.5}')
    status,created=research_records.record('fixture',{'kind':'result','id':'result:catalogue',
        'result':'result.json','title':'Catalogue result','question':'What changed?',
        'summary':'A bounded finding.','limitations':'Fixture only.',
        'measures':[{'label':'Score','key':'score'}]},tmp_path)
    assert status==201,created
    full=rs.handle('/research/state',{'project':['fixture']},'GET',b'',repo_root=tmp_path)
    summary=rs.handle('/research/state',{'project':['fixture'],'view':['summary']},'GET',b'',repo_root=tmp_path)
    full_value,summary_value=json.loads(full[2]),json.loads(summary[2])
    row=summary_value['results'][0]
    assert summary_value['schema_version']=='laplace.research-catalogue/1'
    assert row['next_read']=={'operation':'research','payload':{'view':'result','id':'result:catalogue'}}
    assert 'evidence_files' not in row and 'measurements' not in row
    assert len(summary[2])<len(full[2])
    detail=rs.handle('/research/result',{'project':['fixture'],'id':['result:catalogue']},
                     'GET',b'',repo_root=tmp_path)
    exact=json.loads(detail[2])
    assert exact['exact'] is True and exact['result']['revision']==row['revision']
    assert exact['result']['measurements']==[{'label':'Score','key':'score','value':2.5}]
    assert rs.handle('/research/result',{'project':['fixture'],'id':['missing']},
                     'GET',b'',repo_root=tmp_path)[0]==404


def test_human_measurements_follow_exact_result_keys_and_report_staleness(tmp_path):
    manuscript = _project(tmp_path)
    result = manuscript / 'result.json'
    result.write_text('{"score.flat": 2.5, "checks": {"count": 127}}')
    status, _ = research_records.record('fixture', {'kind':'result','id':'result:readable','result':'result.json',
        'summary':'A bounded observation, not a proof.',
        'measures':[{'label':'Score','key':'score.flat'},{'label':'Checked','key':'checks.count'}]},tmp_path)
    assert status == 201
    shown = research_catalogue.state_payload('fixture',tmp_path)['results'][0]
    assert [m['value'] for m in shown['measurements']] == [2.5,127]
    assert shown['currentness'] == 'CURRENT'
    assert 'match' in shown['currentness_reason']
    assert [{key:row[key] for key in ('role','path','scope')} for row in shown['evidence_files']] == [
        {'role': 'Recorded output', 'path': 'result.json', 'scope': 'manuscript'}]
    assert shown['evidence_files'][0]['availability']=='PRESENT'
    assert shown['evidence_files'][0]['identity'].startswith('sha256:')
    assert shown['current_dependencies'][0]['sha256'] == shown['provenance']['dependencies'][0]['sha256']
    result.write_text('{"score.flat": 3.5, "checks": {"count": 128}}')
    shown = research_catalogue.state_payload('fixture',tmp_path)['results'][0]
    assert shown['currentness'] == 'STALE'
    assert 'changed' in shown['currentness_reason']
    assert shown['current_dependencies'][0]['sha256'] != shown['provenance']['dependencies'][0]['sha256']
    assert [m['value'] for m in shown['measurements']] == [3.5,128]


def test_result_with_explicit_missing_dependency_is_actionable_before_storage(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"score": 1}\n')
    status, refused = research_records.record('fixture', {'kind': 'result', 'id': 'result:missing-source',
        'source': 'missing.py', 'result': 'result.json'}, tmp_path)
    assert status == 422
    assert refused['error'] == 'result dependency is missing or outside its declared scope'
    assert next(row for row in refused['dependencies'] if row['path'] == 'missing.py')['status'] == 'MISSING'
    assert not (manuscript / 'research_records.json').exists()


def test_result_usage_projects_existing_concept_and_manuscript_bindings(tmp_path, monkeypatch):
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"score": 2.5}')
    status, created = research_records.record('fixture', {
        'kind': 'result', 'id': 'result:visible', 'result': 'result.json'}, tmp_path)
    assert status == 201

    monkeypatch.setattr('laplace.manuscript.project_structure.state', lambda project, root: {
        'sections': [{
            'id': 'methods', 'title': 'Methods', 'kind': 'section', 'number': '2',
            'order': 1, 'parent_id': None, 'node_ids': ['claim:visible'], 'beat_ids': [],
            'source': {'source_files': ['manuscript/methods.tex']},
        }],
        'logical_objects': [{
            'id': 'claim:visible', 'label': 'The measured claim', 'kind': 'result',
            'status': 'live', 'summary': 'The exact claim text.',
            'result_bindings': [{'id': 'result:visible',
                                 'revision': created['record']['revision']}],
        }],
    })

    shown = research_catalogue.state_payload('fixture', tmp_path)['results'][0]

    assert shown['usage'] == [{
        'concept': {'id': 'claim:visible', 'label': 'The measured claim',
                    'kind': 'result', 'status': 'live', 'summary': 'The exact claim text.'},
        'binding_revision': created['record']['revision'],
        'manuscript_locations': [{
            'id': 'methods', 'title': 'Methods', 'kind': 'section', 'number': '2',
            'order': 1, 'parent_id': None,
            'source_files': ['manuscript/methods.tex'],
        }],
    }]


def test_visual_specs_reverse_project_to_their_explicit_result(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"score": 2.5}')
    status, created = research_records.record('fixture', {
        'kind': 'result', 'id': 'result:visible', 'result': 'result.json'}, tmp_path)
    assert status == 201
    spec = {
        'id': 'score-figure', 'title': 'Score figure', 'question': 'What is the score?',
        'kind': 'diagram', 'caption': 'The declared score.',
        'nodes': [{'id': 'score', 'label': 'Score'}], 'edges': [],
        'result_ids': ['result:visible'],
    }
    (manuscript / 'manuscript_spec.json').write_text(json.dumps({'figure_specs': [spec]}))

    shown = research_catalogue.state_payload('fixture', tmp_path)['results'][0]

    assert shown['linked_visuals'] == [{
        'visual_id': 'score-figure', 'path': 'score-figure.pdf',
        'label': 'Score figure', 'caption': 'The declared score.',
        'kind': 'diagram', 'source_data': None, 'source': None, 'input_scope':'project',
        'status': 'UNRENDERED', 'evidence_binding_status': 'UNRENDERED',
        'presentation_status': 'UNRENDERED', 'metadata_changes': [],
        'input_files': [],
        'changed_dependencies': [], 'basis_changes': [],
        'rendered': False, 'render': None,
        'result_revision': created['record']['revision'],
        'result_currentness': 'CURRENT',
    }]

    observed = vp.provenance(manuscript, spec, tmp_path / 'fixture')
    output = manuscript / 'figures' / 'generated' / 'score-figure.pdf'
    output.parent.mkdir(parents=True)
    output.write_bytes(b'%PDF-ui-fixture')
    spec['render'] = {'outputs': ['figures/generated/score-figure.pdf'],
                      'output_digests': {'figures/generated/score-figure.pdf':
                          __import__('hashlib').sha256(output.read_bytes()).hexdigest()},
                      'input_digest': observed['input_digest'],
                      'drawing_input_digest': observed['input_digest'],
                      'drawing_inputs': observed['drawing_inputs'],
                      'research_bindings': observed['research_bindings'],
                      'presentation_metadata': observed['presentation_metadata'],
                      'style_version': observed['style_version']}
    (manuscript / 'manuscript_spec.json').write_text(json.dumps({'figure_specs': [spec]}))
    assert research_catalogue.state_payload('fixture', tmp_path)['results'][0]['linked_visuals'][0]['status'] == 'CURRENT'

    (manuscript / 'result.json').write_text('{"score": 3.5}')
    renewed_status, renewed = research_records.record('fixture', {
        'record': {'kind': 'result', 'id': 'result:visible', 'result': 'result.json'},
        'expected_revision': created['record']['revision']}, tmp_path)
    assert renewed_status == 200
    linked = research_catalogue.state_payload('fixture', tmp_path)['results'][0]['linked_visuals'][0]
    assert linked['status'] == 'CURRENT'
    assert linked['evidence_binding_status'] == 'CHANGED'
    assert linked['changed_dependencies'] == []
    assert linked['basis_changes'][0]['id'] == 'result:visible'
    assert linked['result_revision'] == renewed['record']['revision']
    assert linked['result_currentness'] == 'CURRENT'


def test_declared_result_figure_artifact_participates_in_currentness(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"score": 1}')
    figure = manuscript / 'figure.pdf'
    figure.write_bytes(b'%PDF-recorded')
    status, _created = research_records.record('fixture', {
        'kind': 'result', 'id': 'result:figure', 'result': 'result.json',
        'artifacts': [{'path': 'figure.pdf', 'label': 'Recorded figure'}]}, tmp_path)
    assert status == 201
    shown = research_catalogue.state_payload('fixture', tmp_path)['results'][0]
    assert shown['currentness'] == 'CURRENT'
    assert next(dep for dep in shown['current_dependencies'] if dep['path'] == 'figure.pdf')['scope'] == 'manuscript'

    figure.write_bytes(b'%PDF-changed')
    shown = research_catalogue.state_payload('fixture', tmp_path)['results'][0]

    assert shown['currentness'] == 'STALE'
    assert 'artifact' in shown['currentness_reason']


def test_canonical_downstream_visual_artifact_does_not_poison_result_basis(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"score": 1}')
    figure = manuscript / 'figures' / 'generated' / 'derived.pdf'
    figure.parent.mkdir(parents=True);figure.write_bytes(b'%PDF-derived-v1')
    spec = {'id':'derived','title':'Derived view','question':'What does the result show?',
            'kind':'diagram','caption':'A downstream depiction.',
            'nodes':[{'id':'score','label':'Score'}],'edges':[],
            'result_ids':['result:derived']}
    (manuscript / 'manuscript_spec.json').write_text(json.dumps({'figure_specs':[spec]}))
    status, created = research_records.record('fixture', {'kind':'result','id':'result:derived',
        'result':'result.json','artifacts':[{'path':'figures/generated/derived.pdf',
            'label':'Derived view','visual_id':'derived'}]}, tmp_path)
    assert status==201
    # Simulate a legacy receipt which pinned the downstream presentation byte.
    store=json.loads((manuscript/'research_records.json').read_text())
    store['records'][0]['provenance']['dependencies'].append({
        **research_observation._relative_digest(manuscript,'figures/generated/derived.pdf'),'scope':'manuscript'})
    (manuscript/'research_records.json').write_text(json.dumps(store))
    from laplace.pipeline import visual_production as vp
    observed=vp.provenance(manuscript,spec,tmp_path/'fixture')
    spec['render']={'outputs':['figures/generated/derived.pdf'],
        'output_digests':{'figures/generated/derived.pdf':__import__('hashlib').sha256(figure.read_bytes()).hexdigest()},
        'input_digest':observed['input_digest'],'drawing_input_digest':observed['input_digest'],
        'drawing_inputs':observed['drawing_inputs'],'research_bindings':observed['research_bindings'],
        'presentation_metadata':observed['presentation_metadata'],'style_version':observed['style_version']}
    (manuscript/'manuscript_spec.json').write_text(json.dumps({'figure_specs':[spec]}))
    stored_before=(manuscript/'research_records.json').read_bytes()

    figure.write_bytes(b'%PDF-derived-v2')
    shown=research_catalogue.state_payload('fixture',tmp_path)['results'][0]

    assert shown['currentness']=='CURRENT'
    assert shown['revision']==created['record']['revision']
    assert shown['dependency_coverage']['retired_derived_presentation_pins'][0]['path']=='figures/generated/derived.pdf'
    assert shown['linked_visuals'][0]['status']=='STALE'
    assert shown['linked_visuals'][0]['result_currentness']=='CURRENT'
    assert (manuscript/'research_records.json').read_bytes()==stored_before


def _project(tmp_path: Path) -> Path:
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "fixture", "kind": "conceptric", "project_dir": "fixture",
        "tex_root": "fixture/manuscript",
    }]}), encoding="utf-8")
    manuscript = tmp_path / "fixture" / "manuscript"
    manuscript.mkdir(parents=True)
    (manuscript / "config.json").write_text('{"seed": 7}', encoding="utf-8")
    (manuscript / "data.json").write_text('[1, 2, 3]', encoding="utf-8")
    (manuscript / "source.py").write_text('SOURCE = 1\n', encoding="utf-8")
    (manuscript / "figure_manifest.json").write_text(json.dumps({"placed": [{
        "asset_id": "figure:fixture", "label": "fig:fixture", "promise": "fixture-plot",
        "generator": "fixture", "artefact": "figures/fixture.pdf", "matched": True,
    }]}), encoding="utf-8")
    return manuscript


def test_records_link_declared_inputs_to_results_and_invalidate_live(tmp_path):
    manuscript = _project(tmp_path)
    status, _ = research_records.record("fixture", {"kind": "experiment", "id": "experiment:one",
                                        "config": "config.json", "data": ["data.json"],
                                        "source": "source.py", "figure_ids": ["figure:fixture"]}, tmp_path)
    assert status == 201
    (manuscript / "result.json").write_text('{"score": 1}', encoding="utf-8")
    status, _ = research_records.record("fixture", {"kind": "result", "id": "result:one",
                                        "result": "result.json"}, tmp_path)
    assert status == 201
    status, _ = research_records.record("fixture", {"kind": "figure_binding", "id": "bind:one",
                                        "figure_id": "figure:fixture", "result_id": "result:one"}, tmp_path)
    assert status == 201
    state = research_catalogue.state_payload("fixture", tmp_path)
    assert state["currentness"]["status"] == "CURRENT"
    assert {edge["kind"] for edge in state["invalidation"]} >= {
        "declared-input", "result-depicted-by-figure", "explicit-binding"}
    assert state["figures"][0]["id"] == "figure:fixture"

    baselines = {
        "config.json": '{"seed": 7}', "data.json": '[1, 2, 3]', "source.py": "SOURCE = 1\n",
    }
    for name, original in baselines.items():
        (manuscript / name).write_text(original + "\nchanged", encoding="utf-8")
        stale = research_catalogue.state_payload("fixture", tmp_path)
        assert stale["currentness"]["status"] == "STALE", name
        assert "changed" in stale["currentness"]["reason"]
        (manuscript / name).write_text(original, encoding="utf-8")

    manifest = manuscript / "figure_manifest.json"
    original_manifest = manifest.read_text()
    manifest.write_text(original_manifest + "\n")
    assert research_catalogue.state_payload("fixture", tmp_path)["currentness"]["status"] == "CURRENT"
    manifest.write_text(original_manifest)
    status, _ = research_records.record("fixture", {"kind": "experiment", "id": "experiment:image-evidence",
                                       "evidence_for": ["figure:fixture"]}, tmp_path)
    assert status == 201
    manifest.write_text(original_manifest + "\n")
    explicit = research_catalogue.state_payload("fixture", tmp_path)
    assert explicit["currentness"]["status"] == "STALE"
    assert "explicit-figure-evidence" in {edge["kind"] for edge in explicit["invalidation"]}


def test_stable_result_id_requires_expected_revision_and_renews_currentness_with_history(tmp_path):
    manuscript = _project(tmp_path)
    result_file = manuscript / "result.json"
    result_file.write_text('{"score": 1}\n')
    created_status, created = research_records.record("fixture", {
        "kind": "result", "id": "result:stable", "result": "result.json"}, tmp_path)
    assert created_status == 201
    old_revision = created["record"]["revision"]
    next_step=created['next_step']
    assert next_step['write']['operation']=='structure_change'
    assert next_step['write']['payload']['operation']=='bind_results'
    assert next_step['write']['payload']['results']==[{
        'id':'result:stable','revision':old_revision}]
    assert next_step['write']['payload']['node']=='<intended canonical claim id>'
    assert 'Do not infer' in next_step['safeguard']
    assert research_catalogue.state_payload("fixture", tmp_path)["currentness"]["status"] == "CURRENT"

    result_file.write_text('{"score": 2}\n')
    assert research_catalogue.state_payload("fixture", tmp_path)["currentness"]["status"] == "STALE"
    refused_status, refused = research_records.record("fixture", {
        "kind": "result", "id": "result:stable", "result": "result.json"}, tmp_path)
    assert refused_status == 409 and refused["current_revision"] == old_revision
    renewed_status, renewed = research_records.record("fixture", {
        "record": {"kind": "result", "id": "result:stable", "result": "result.json"},
        "expected_revision": old_revision}, tmp_path)

    assert renewed_status == 200 and renewed["renewed"] is True
    assert renewed["record"]["revision"] != old_revision
    state = research_catalogue.state_payload("fixture", tmp_path)
    assert state["currentness"]["status"] == "CURRENT"
    assert [row["id"] for row in state["results"]] == ["result:stable"]
    assert state['results'][0]['renewal_history'][0]['revision'] == old_revision
    assert state['results'][0]['renewal_history'][0]['replaced_by'] == renewed['record']['revision']
    stored = json.loads((manuscript / "research_records.json").read_text())
    assert len(stored["records"]) == 1 and len(stored["history"]) == 1
    assert stored["history"][0]["record"]["revision"] == old_revision
    journal = [json.loads(line) for line in (tmp_path / "contract" / "talk.jsonl").read_text().splitlines()]
    renewal = next(row for row in journal if row.get("record") == "research-record-renewal")
    assert renewal["before"]["revision"] == old_revision
    assert renewal["after"]["revision"] == renewed["record"]["revision"]


def test_declared_producer_runs_only_smoke_or_full_and_has_result_provenance(tmp_path):
    manuscript = _project(tmp_path)
    producer = manuscript / "producer.py"
    producer.write_text(
        "import argparse, json\n"
        "p=argparse.ArgumentParser(); p.add_argument('--mode'); p.add_argument('--args-json'); p.add_argument('--result')\n"
        "a=p.parse_args(); open(a.result, 'w').write(json.dumps({'mode':a.mode, 'args':json.loads(a.args_json)}))\n",
        encoding="utf-8")
    (manuscript / "research_producers.json").write_text(json.dumps({"producers": [{
        "id": "fixture-producer", "executable": "producer.py", "modes": ["smoke", "full"],
        "allowed_args": {"count": "int"}, "result_path": "research_runs/{run_id}.result.json",
    }]}), encoding="utf-8")
    status, refusal = research_runs.launch("fixture", {"producer_id": "fixture-producer", "mode": "all", "args": {}}, tmp_path)
    assert status == 422 and "mode" in refusal["error"]
    status, launched = research_runs.launch("fixture", {"producer_id": "fixture-producer", "mode": "smoke",
                                                "args": {"count": 2}}, tmp_path)
    assert status == 202
    from laplace.native.contracts import exact_contract
    protocol = exact_contract('research_producer', permitted=True)['execution_protocol']
    argv = launched['run']['producer_argv']
    assert argv[-6::2] == [protocol['flags'][key] for key in ('mode', 'args', 'result')]
    assert json.loads(argv[-3]) == {'count': 2}
    assert Path(argv[-1]).is_absolute()
    run_id = launched["run"]["id"]
    for _ in range(40):
        current = research_runs._run_status(manuscript, run_id)
        if current and current["state"] == "COMPLETE":
            break
        time.sleep(0.025)
    assert current["state"] == "COMPLETE"
    assert current["result_provenance"]["sha256"]


def test_zero_exit_without_result_explains_output_protocol(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / 'no_result.py').write_text('print("result.json")\n')
    status, declared = research_runs.register_producer('fixture', {'id':'no-result',
        'executable':'no_result.py','modes':['smoke'],'allowed_args':{},'dependencies':[],
        'timeout_seconds':5}, tmp_path)
    assert status == 201
    status, launched = research_runs.launch('fixture', {'producer_id':'no-result','mode':'smoke'}, tmp_path)
    assert status == 202
    for _ in range(80):
        current = research_runs._run_status(manuscript, launched['run']['id'])
        if current and current['state'] != 'RUNNING': break
        time.sleep(.025)
    assert current['state'] == 'FAILED' and current['exit_code'] == 0
    assert '--result' in current['reason'] and 'stdout is only a log' in current['reason']


def test_figure_spec_is_an_explicit_identity_declaration(tmp_path):
    manuscript = tmp_path / "manuscript"
    manuscript.mkdir()
    (manuscript / "s1.tex").write_text("the witness-scaling plot", encoding="utf-8")
    script = tmp_path / "producer.py"
    script.write_text('"""fig_witness - witness scaling"""\ndef fig_witness(): pass\n', encoding="utf-8")
    manifest = fr.run(manuscript, script, figure_specs=[{
        "output": "fig_witness", "section": "s1.tex", "label": "fig:declared",
        "asset_id": "figure:declared",
    }])
    assert manifest["placed"][0]["asset_id"] == "figure:declared"
    assert manifest["figure_specs"][0]["label"] == "fig:declared"


def test_result_file_without_successful_exit_is_failed(tmp_path, monkeypatch):
    manuscript = _project(tmp_path); producer = manuscript / "bad.py"
    producer.write_text("import argparse; p=argparse.ArgumentParser(); p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args();open(a.result,'w').write('{}');raise SystemExit(3)", encoding="utf-8")
    (manuscript / "research_producers.json").write_text(json.dumps({"producers":[{"id":"bad","executable":"bad.py","modes":["smoke"],"allowed_args":{},"timeout_seconds":5}]}),encoding="utf-8")
    status,out=research_runs.launch('fixture',{'producer_id':'bad','mode':'smoke','args':{}},tmp_path);assert status==202
    import time
    for _ in range(80):
        got=research_runs._run_status(manuscript,out['run']['id'])
        if got and got['state']!='RUNNING':break
        time.sleep(.025)
    assert got['state']=='FAILED' and got['exit_code']==3


def test_active_runs_tracks_live_owned_supervisor_until_receipt(tmp_path):
    manuscript = _project(tmp_path)
    producer = manuscript / "slow.py"
    producer.write_text(
        "import argparse,json,time\n"
        "p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');"
        "p.add_argument('--result');a=p.parse_args()\n"
        "time.sleep(.35)\n"
        "open(a.result,'w').write(json.dumps({'done':True}))\n",
        encoding="utf-8")
    (manuscript / "research_producers.json").write_text(json.dumps({"producers": [{
        "id": "slow", "executable": "slow.py", "modes": ["smoke"],
        "allowed_args": {}, "timeout_seconds": 5,
    }]}), encoding="utf-8")

    status, launched = research_runs.launch("fixture", {"producer_id": "slow", "mode": "smoke",
                                               "args": {}}, tmp_path)
    assert status == 202
    active = research_runs.active_runs(tmp_path)
    assert [(row["id"], row["project"]) for row in active] == [
        (launched["run"]["id"], "fixture")]
    for _ in range(100):
        if not research_runs.active_runs(tmp_path):
            break
        time.sleep(.025)
    assert research_runs.active_runs(tmp_path) == []
    assert research_runs._run_status(manuscript, launched["run"]["id"])["state"] == "COMPLETE"


def test_runner_timeout_reaps_sigterm_ignoring_child(tmp_path):
    import subprocess, sys, time
    runs=tmp_path/'runs';runs.mkdir(); result=tmp_path/'result.json'; job=runs/'job.json'
    child="import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(20)"
    job.write_text(json.dumps({'result_absolute':str(result),'producer_argv':[sys.executable,'-c',child],
      'cwd':str(tmp_path),'timeout_seconds':1,'deadline_at':time.time()+.2,'stdout_path':str(runs/'o.log'),'stderr_path':str(runs/'e.log'),'cancel_path':str(runs/'cancel')}))
    subprocess.run([sys.executable,'-m','laplace.research.research_runner','--job',str(job)],check=True,timeout=8)
    receipt=json.loads((runs/'job.receipt.json').read_text())
    assert receipt['state']=='TIMED_OUT'


def test_project_scope_record_and_run_follow_project_root_and_code_currentness(tmp_path):
    manuscript = _project(tmp_path)
    project = tmp_path / "fixture"
    numerics = project / "numerics"
    numerics.mkdir()
    data = numerics / "data.json"
    data.write_text('{"value":1}\n')
    status, record = research_records.record("fixture", {"kind": "experiment", "id": "experiment:project",
                                            "scope": "project", "data": ["numerics/data.json"]}, tmp_path)
    assert status == 201 and record["record"]["provenance"]["scope"] == "project"
    assert research_catalogue.state_payload("fixture", tmp_path)["currentness"]["status"] == "CURRENT"
    data.write_text('{"value":2}\n')
    assert research_catalogue.state_payload("fixture", tmp_path)["currentness"]["status"] == "STALE"
    data.write_text('{"value":1}\n')

    producer = numerics / "producer.py"
    producer_source = (
        "import argparse,json\n"
        "p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()\n"
        "open(a.result,'w').write(json.dumps({'cwd':'project','values':[{'x':-2,'y':-3},{'x':-1,'y':-1},{'x':0,'y':1},{'x':1,'y':3},{'x':2,'y':5}]}))\n")
    producer.write_text(producer_source)
    status, declared = research_runs.register_producer("fixture", {"id": "project-producer",
        "scope": "project", "executable": "numerics/producer.py", "modes": ["smoke"],
        "allowed_args": {}}, root=tmp_path)
    assert status == 201, declared
    status, launched = research_runs.launch("fixture", {"producer_id": "project-producer",
                                              "mode": "smoke", "args": {}}, tmp_path)
    assert status == 202 and launched["run"]["cwd"] == str(project)
    run_id = launched["run"]["id"]
    for _ in range(80):
        current = research_runs._run_status(manuscript, run_id)
        if current and current["state"] != "RUNNING": break
        time.sleep(.025)
    assert current["state"] == "COMPLETE"
    producer.write_text(producer_source + "# changed\n")
    assert research_runs._run_status(manuscript, run_id)["state"] == "STALE"
    status, result_record = research_records.record("fixture", {"kind": "result", "id": "result:project-run",
                                                   "run_id": run_id,
                                                   "result": current["result_path"]}, tmp_path)
    assert status == 409 and "not complete and current" in result_record["error"]
    producer.write_text(producer_source)
    assert research_runs._run_status(manuscript, run_id)["state"] == "COMPLETE"
    status, result_record = research_records.record("fixture", {"kind": "result", "id": "result:project-run",
        "run_id": run_id, "source": "numerics/producer.py", "result": current["result_path"],
        "measures": [{"key": "values", "label": "Calibration values"}]}, tmp_path)
    assert status == 201, result_record
    stored = result_record["record"]
    assert stored["source_scope"] == "project" and stored["result_scope"] == "manuscript"
    assert next(row for row in stored["provenance"]["dependencies"]
                if row["path"] == "numerics/producer.py")["status"] == "PRESENT"
    state = research_catalogue.state_payload("fixture", tmp_path)
    assert state["currentness"]["status"] == "CURRENT"
    assert state["results"][0]["measurements"][0]["value"] == [
        {"x": -2, "y": -3}, {"x": -1, "y": -1}, {"x": 0, "y": 1},
        {"x": 1, "y": 3}, {"x": 2, "y": 5}]
    assert research_records.result_bindings(manuscript, ["result:project-run"], project)["status"] == "CURRENT"
    declarations = json.loads((manuscript / "research_producers.json").read_text())
    declarations["producers"][0]["description"] = "changed declaration"
    (manuscript / "research_producers.json").write_text(json.dumps(declarations))
    changed = research_runs._run_status(manuscript, run_id)
    assert changed["state"] == "STALE" and "declaration changed" in changed["reason"]
    assert research_catalogue.state_payload("fixture", tmp_path)["currentness"]["status"] == "STALE"


def test_run_status_read_is_passive_and_cancel_requires_live_writable_run(tmp_path, monkeypatch):
    manuscript = _project(tmp_path)
    runs = manuscript / "research_runs"; runs.mkdir()
    expired = {"id": "run-expired", "state": "RUNNING", "pid": 999999,
               "deadline_at": time.time()-1, "result_path": "research_runs/result.json",
               "result_absolute": str(runs/'result.json')}
    (runs / "run-expired.json").write_text(json.dumps(expired))
    monkeypatch.setattr(research_runs.os, "killpg", lambda *args: (_ for _ in ()).throw(AssertionError("read killed process")))
    observed = research_runs._run_status(manuscript, "run-expired")
    assert observed["state"] == "RUNNING" and observed["deadline_exceeded"] is True

    unknown = rs.handle('/research/cancel', {}, 'POST',
                        b'{"project":"fixture","id":"missing"}', repo_root=tmp_path)
    assert unknown[0] == 404


def test_text_artifact_download_returns_all_scoped_bytes_without_preview_truncation(tmp_path):
    import hashlib
    manuscript = _project(tmp_path)
    data = ('name,value\r\n' + '"quoted, name","line one\nline two"\r\n' * 4000).encode()
    target = manuscript / 'measurements.csv'
    target.write_bytes(data)
    query = {'project':['fixture'], 'scope':['manuscript'], 'path':['measurements.csv']}
    status, _, raw = rs.handle('/research/artifact', {**query, 'format':['json'], 'limit':['65536']}, 'GET', b'', repo_root=tmp_path)
    preview = json.loads(raw)
    assert status == 200 and len(preview['content']) == 65536
    assert preview['next_offset'] == 65536 and preview['download_available'] is True
    downloaded = rs.handle('/research/artifact', {**query, 'download':['1']}, 'GET', b'', repo_root=tmp_path)
    assert downloaded[0] == 200 and downloaded[1] == 'application/octet-stream'
    assert len(downloaded[2]) > 65536
    assert hashlib.sha256(downloaded[2]).digest() == hashlib.sha256(data).digest()
    assert rs.handle('/research/artifact', {**query, 'download':['1'], 'path':['../../outside.csv']}, 'GET', b'', repo_root=tmp_path)[0] == 404
    # Source-code inspection remains a text page, never a tabular projection.
    code = manuscript / 'producer.py'
    code.write_text('print("value,other")\n')
    _, _, raw = rs.handle('/research/artifact', {**query, 'path':['producer.py'], 'format':['json']}, 'GET', b'', repo_root=tmp_path)
    assert json.loads(raw)['content'] == code.read_text()


def test_pdf_companion_links_use_verified_export_source_and_download_complete_archive(tmp_path):
    import hashlib
    from urllib.parse import parse_qs, urlsplit
    manuscript = _project(tmp_path)
    (manuscript / 'main.tex').write_text('Source')
    exports = manuscript / 'exports'; exports.mkdir()
    pdf = exports / 'edition.pdf'; pdf.write_bytes(b'%PDF retained bytes')
    notes = manuscript / 'notes.md'; notes.write_text('# Companion\n')
    archive = manuscript / 'source package.zip'; archive.write_bytes(b'PK' + b'payload' * 12000)
    receipt = {'project': 'fixture', 'exported_file': pdf.relative_to(tmp_path).as_posix(),
               'selected_source': {'root': (manuscript / 'main.tex').relative_to(tmp_path).as_posix()},
               'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest()}
    pdf.with_suffix('.json').write_text(json.dumps(receipt))
    query = {'project': ['fixture'], 'scope': ['project'], 'path': [str(pdf)], 'resolve': ['pdf-link']}
    def resolve(uri, **changes):
        status, _, body = rs.handle('/research/artifact', {**query, 'uri': [uri], **changes}, 'GET', b'', repo_root=tmp_path)
        return status, json.loads(body)
    status, link = resolve('source%20package.zip')
    assert status == 200 and link['basis'] == 'verified-export-source' and link['kind'] == 'download'
    destination = parse_qs(urlsplit(link['url']).query)
    status, media, data = rs.handle('/research/artifact', destination, 'GET', b'', repo_root=tmp_path)
    assert status == 200 and media == 'application/zip' and data == archive.read_bytes()
    assert hashlib.sha256(data).hexdigest() == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert resolve('notes.md#Derivation')[1]['fragment'] == 'Derivation'
    # A projection export URL carries a repository-relative identity.
    assert resolve('notes.md', path=[receipt['exported_file']])[0] == 200
    for uri in ('../../../../outside.md', 'file:///etc/passwd', '//outside/file.zip', '/etc/passwd', '..\\outside.md', 'notes.md?unexpected=1'):
        assert resolve(uri)[0] == 422
    outside = tmp_path / 'private.md'; outside.write_text('outside')
    (manuscript / 'linked.md').symlink_to(outside)
    assert resolve('linked.md')[0] == 422
    pdf.write_bytes(b'changed PDF')
    assert resolve('notes.md')[0] == 422
    pdf.with_suffix('.json').unlink()
    assert resolve('notes.md')[0] == 422


def test_ordinary_project_pdf_companions_keep_their_own_directory(tmp_path):
    manuscript = _project(tmp_path)
    pdf = manuscript / 'paper.pdf'; pdf.write_bytes(b'%PDF')
    (manuscript / 'notes.md').write_text('Notes')
    status, _, body = rs.handle('/research/artifact', {
        'project': ['fixture'], 'scope': ['manuscript'], 'path': ['paper.pdf'],
        'resolve': ['pdf-link'], 'uri': ['notes.md']}, 'GET', b'', repo_root=tmp_path)
    value = json.loads(body)
    assert status == 200 and value['basis'] == 'pdf-directory'
    assert value['kind'] == 'text' and value['path'].endswith('/notes.md')


def test_historical_pdf_companions_remain_current_files_and_zip_inclusion_requires_actual_pdf_bytes(tmp_path):
    import hashlib
    import zipfile
    manuscript = _project(tmp_path); exports = manuscript / 'exports'; exports.mkdir()
    pdf = exports / 'old-edition.pdf'; pdf.write_bytes(b'%PDF exact retained edition')
    receipt = {'project': 'fixture', 'exported_file': pdf.relative_to(tmp_path).as_posix(),
               'selected_source': {'root': (manuscript / 'main.tex').relative_to(tmp_path).as_posix()},
               'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest()}
    receipt_file = pdf.with_suffix('.json'); receipt_file.write_text(json.dumps(receipt)); recorded = receipt_file.read_bytes()
    notes = manuscript / 'notes.md'; notes.write_text('Earlier notes')
    package = manuscript / 'package.zip'
    def resolve(uri):
        status, _, raw = rs.handle('/research/artifact', {'project': ['fixture'], 'scope': ['project'],
            'path': [str(pdf)], 'resolve': ['pdf-link'], 'uri': [uri]}, 'GET', b'', repo_root=tmp_path)
        assert status == 200
        return json.loads(raw)
    first = resolve('notes.md'); notes.write_text('New notes written after the export')
    second = resolve('notes.md')
    for value in (first, second):
        assert value['companion_identity'] == 'CURRENT_PROJECT_FILE'
        assert value['edition_match'] == 'UNRECORDED'
        assert 'no companion snapshot' in value['basis_scope']
        assert 'match to this PDF edition has not been recorded' in value['notice']
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('manifest.json', json.dumps({'pdf_sha256': receipt['pdf_sha256']}))
        archive.writestr('book.pdf', b'%PDF wrong retained edition')
    assert resolve('package.zip')['edition_match'] == 'UNRECORDED', 'a manifest assertion is not byte evidence'
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('book.pdf', pdf.read_bytes())
        archive.writestr('notes.md', 'Different notes; PDF inclusion says nothing about these')
    matched = resolve('package.zip')
    assert matched['companion_identity'] == 'CURRENT_PROJECT_FILE'
    assert matched['edition_match'] == 'EXACT_PDF_INCLUDED'
    assert matched['inclusion']['member'] == 'book.pdf'
    assert matched['inclusion']['pdf_sha256'] == receipt['pdf_sha256']
    assert 'Other members and later file changes are unverified' in matched['notice']
    assert matched['inclusion']['inspection_only'] is True
    assert matched['inclusion']['download_binding'] == 'UNPINNED'
    assert resolve('notes.md')['edition_match'] == 'UNRECORDED', 'no inferred notes association'
    with zipfile.ZipFile(package, 'w') as archive:
        for n in range(17): archive.writestr(f'book-{n}.pdf', pdf.read_bytes())
    assert resolve('package.zip')['edition_match'] == 'UNRECORDED', 'bounded candidate inspection'
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('book.pdf', pdf.read_bytes())
        for n in range(2048): archive.writestr(f'item-{n}.txt', 'x')
    assert resolve('package.zip')['edition_match'] == 'UNRECORDED', 'bounded central-directory inspection'
    assert receipt_file.read_bytes() == recorded, 'historical export receipts are never retrofitted'


def test_source_companion_links_use_exact_current_tex_directory_without_requiring_a_pdf(tmp_path):
    manuscript=_project(tmp_path);source=manuscript/'main.tex';source.write_text(r'\href{notes.md}{Notes}')
    (manuscript/'notes.md').write_text('# Readable notes')
    query={'project':['fixture'],'scope':['project'],'path':[str(source)],'resolve':['source-link'],'uri':['notes.md']}
    status,_,raw=rs.handle('/research/artifact',query,'GET',b'',repo_root=tmp_path)
    value=json.loads(raw);assert status==200 and value['kind']=='text'
    assert value['basis']=='current-source-directory' and value['path'].endswith('/notes.md')
    assert not source.with_suffix('.pdf').exists()
    for uri in ('../../outside.md','file:///etc/passwd','//example.org/private'):
        assert rs.handle('/research/artifact',{**query,'uri':[uri]},'GET',b'',repo_root=tmp_path)[0]==422


# Owner-defined semantic consumption, not a read-time key-name blacklist.
def _consumption_project(root, manuscript=None):
    manuscript = manuscript or _project(root)
    manuscript.mkdir(parents=True, exist_ok=True)
    for name, text in {"source.py":"VALUE = 1\n","analysis.py":"ANALYSIS = 1\n","helper.py":"HELPER = 1\n",
                       "data.json":"[1,2]","config.json":'{"seed":7}',
                       "result.json":'{"score":1}'}.items():
        (manuscript/name).write_text(text)
    if not (manuscript/"main.tex").exists():
        (manuscript/"main.tex").write_text("\\documentclass{article}\n\\begin{document}Basis.\\end{document}\n")
    spec={"id":"basis","executable":"source.py","modes":["smoke"],
          "allowed_args":{"request_id":"str"},"dependencies":["helper.py","data.json","config.json"],
          "timeout_seconds":5}
    assert research_runs.register_producer("fixture",spec,root)[0]==201
    assert research_records.record("fixture",{"kind":"experiment","id":"basis:experiment",
        "source":"source.py","config":"config.json","data":["data.json"]},root)[0]==201
    assert research_records.record("fixture",{"kind":"result","id":"basis:result",
        "result":"result.json","source":"analysis.py","summary":"A fixture observation."},root)[0]==201
    runs=manuscript/"research_runs";runs.mkdir(exist_ok=True)
    (runs/"run-basis.json").write_text(json.dumps({"id":"run-basis","project":"fixture",
        "state":"FAILED","producer_id":"basis","mode":"smoke","args":{"request_id":"scientific-one"},
        "timeout_seconds":5,"deadline_at":1,"result_path":"result.json",
        "result_absolute":str(manuscript/"result.json")}))
    (runs/"index.json").write_text(json.dumps({"runs":["run-basis"]}))
    research_catalogue.state_cache_clear()
    return manuscript


def _summary(root):
    code, value=research_catalogue.state_read("fixture",root,view="summary")
    assert code==200
    return value


def test_summary_consumption_keeps_raw_actions_and_cache_observations(tmp_path):
    from laplace.writing import reads
    md=_consumption_project(tmp_path)
    first=_summary(tmp_path);second=_summary(tmp_path)
    assert first["read_basis"]["cache"]=="miss" and second["read_basis"]["cache"]=="hit"
    assert first!=second and first["index_stamp"]==second["index_stamp"]
    launch=lambda v:v["producers"][0]["launch_action"]
    assert launch(first)["native"]["payload"]==launch(first)["http"]["payload"]
    assert launch(first)["native"]["payload"]["request_id"]!=launch(second)["native"]["payload"]["request_id"]
    a=reads.record_read_basis("research",first,{"view":"summary"},project="fixture")
    b=reads.record_read_basis("research",second,{"view":"summary"},project="fixture")
    assert a["consumption"]["status"]=="AVAILABLE"
    assert a["consumption"]["semantic_sha256"]==b["consumption"]["semantic_sha256"]
    assert a["research_raw"]==first and b["research_raw"]==second
    assert a["consumption"]["raw_sha256"]!=b["consumption"]["raw_sha256"]
    assert reads.read_output_digest("research",first)!=reads.read_output_digest("research",second)
    before=json.dumps(first,sort_keys=True)
    research_catalogue.summary_consumption(first)
    assert json.dumps(first,sort_keys=True)==before, "projection must not mutate raw actions"


@pytest.mark.parametrize("change",["code","helper","input","result","config","declaration",
    "mode","runtime","actual-args","deadline","currentness","source","already-stale"])
def test_summary_consumption_detects_real_changes_without_a_successful_run(tmp_path,change):
    from laplace.writing import reads
    md=_consumption_project(tmp_path)
    if change=="already-stale":(md/"result.json").write_text('{"score":2}')
    first=_summary(tmp_path)
    before=reads.record_read_basis("research",first,{"view":"summary"},project="fixture")
    assert before["consumption"]["status"]=="AVAILABLE"
    files={"code":"source.py","helper":"helper.py","input":"data.json","result":"result.json",
           "config":"config.json","source":"analysis.py","already-stale":"result.json"}
    if change in files:
        p=md/files[change]
        p.write_text('{"score":3}' if p.suffix==".json" else p.read_text()+"\nchanged\n")
    elif change=="declaration":
        p=md/"research_producers.json";v=json.loads(p.read_text())
        v["producers"][0]["timeout_seconds"]=4;p.write_text(json.dumps(v))
    else:
        p=md/"research_runs/run-basis.json";v=json.loads(p.read_text())
        key={"mode":"mode","runtime":"timeout_seconds","actual-args":"args",
             "deadline":"deadline_at","currentness":"state"}[change]
        v[key]={"mode":"full","runtime":4,"actual-args":{"request_id":"scientific-two"},
                "deadline":2,"currentness":"CANCELLED"}[change]
        p.write_text(json.dumps(v))
    after=reads.record_read_basis("research",_summary(tmp_path),{"view":"summary"},project="fixture")
    assert after["consumption"]["status"]=="AVAILABLE"
    assert before["consumption"]["semantic_sha256"]!=after["consumption"]["semantic_sha256"]


@pytest.mark.parametrize("change",["mismatched-control","unknown-operation","incomplete","future-basis",
    "uncached","unknown-observation","missing-code"])
def test_summary_unsupported_or_unavailable_basis_never_becomes_current(tmp_path,change):
    import copy
    from laplace.writing import reads
    md=_consumption_project(tmp_path);value=_summary(tmp_path)
    if change=="missing-code":
        (md/"source.py").unlink();value=_summary(tmp_path)
    else:
        value=copy.deepcopy(value)
        if change=="mismatched-control":value["producers"][0]["launch_action"]["http"]["payload"]["request_id"]="research-"+"0"*32
        elif change=="unknown-operation":value["producers"][0]["launch_action"]["native"]["operation"]="other"
        elif change=="incomplete":value["consumption_basis"]["complete"]=False
        elif change=="future-basis":value["consumption_basis"]["schema_version"]="future"
        elif change=="uncached":value["read_basis"]["cache"]="uncached"
        else:value["read_basis"]["scientific_counter"]=7
    fields=reads.record_read_basis("research",value,{"view":"summary"},project="fixture")
    assert fields["consumption"]["status"]=="UNAVAILABLE"
    with pytest.raises(ValueError):
        reads.comparison_digest("research",value,{"operation":"research","payload":{"view":"summary","project":"fixture"},**fields},root=tmp_path)


def test_scientific_request_id_and_action_only_args_are_not_control_ids(tmp_path):
    import copy
    from laplace.writing import reads
    _consumption_project(tmp_path);first=_summary(tmp_path)
    before=research_catalogue.summary_consumption(first)
    for args in ({"request_id":"scientific-new"},{"count":8}):
        changed=copy.deepcopy(first)
        action=changed["producers"][0]["launch_action"]
        action["native"]["payload"]["args"]=dict(args);action["http"]["payload"]["args"]=dict(args)
        assert reads._consumption_hash(before)!=reads._consumption_hash(research_catalogue.summary_consumption(changed))



@pytest.mark.parametrize("changed_file",["zero-producer.py","zero-input.json"])
def test_literal_zero_run_producer_basis_detects_code_and_declared_input_changes(tmp_path,changed_file):
    from test_proposal_lifecycle import RAW
    from test_writing_controller import _seed_revision
    from laplace.native import tools as writing_tools
    from laplace.writing import operations, reads, session_reads
    md=_project(tmp_path)
    (md/"main.tex").write_text(RAW)
    (md/"zero-input.json").write_text('{"value":1}')
    (md/"zero-producer.py").write_text(
        "import argparse,json\nfrom pathlib import Path\n"
        "p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()\n"
        "Path(a.result).write_text(json.dumps({'value':1}))\n")
    spec={"id":"zero-run-producer","executable":"zero-producer.py","modes":["smoke"],
          "allowed_args":{},"dependencies":["zero-input.json"]}
    assert research_runs.register_producer("fixture",spec,tmp_path)[0]==201
    # No launch, synthetic FAILED run, run index or result record is created.
    turn=_seed_revision(tmp_path,"fixture",[],selection={"files":["main.tex"]},suffix="zero-run")
    research_catalogue.state_cache_clear()
    first=writing_tools.execute(tmp_path,"fixture","revise","research",{"view":"summary"},turn_id=turn)
    assert first["producer_runs"]==[] and first["results"]==[]
    assert not list((md/"research_runs").glob("*.json"))
    assert not (md/"research_runs/index.json").exists()
    read=next(r for r in session_reads._records(tmp_path)["turns"][turn]["tool_reads"].values()
              if r["operation"]=="research")
    assert read["consumption"]["status"]=="AVAILABLE"
    before=operations.replay_read(tmp_path,"fixture","revise",read,turn)
    assert reads.comparison_digest("research",before,read,root=tmp_path)==reads.consumed_digest(read)
    if changed_file.endswith(".py"):
        target=md/changed_file;target.write_text(target.read_text()+"# changed code bytes\n")
    else:
        (md/changed_file).write_text('{"value":2}')
    after=operations.replay_read(tmp_path,"fixture","revise",read,turn)
    assert after["producer_runs"]==[] and not list((md/"research_runs").glob("*.json"))
    assert after["consumption_basis"]["complete"] is True
    assert after["consumption_basis"]["provenance_sha256"]!=first["consumption_basis"]["provenance_sha256"]
    assert reads.comparison_digest("research",after,read,root=tmp_path)!=reads.consumed_digest(read)
