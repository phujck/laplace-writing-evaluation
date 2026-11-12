"""Real Work/Concept/guide checkpoints inside the one custody/runtime server stage.

The stage/daemon and mechanical observations belong to test_engine_custody_runtime.
This helper starts nothing and changes no implementation source. Fixture input
bytes enter a project through its existing import owner; statuses and proposal
basis decisions always come from canonical production owners.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlencode


class EngineeringHTTPScenario:
    project = 'engine-http'
    claim = 'res:retention-and-projection'
    work = 'WORK-engine-http-custody'
    guide_path = 'BACKGROUND.md'
    source_paths = ('src/atlas/store.py', 'src/atlas/ids.py',
                    'src/laplace/web/authoring.py', 'src/laplace/representation/atlas_bridge.py',
                    'src/laplace/native/tools.py', 'src/laplace/work/author_history_metrics.py',
                    'src/laplace/desktop/writing_app.py', 'src/laplace/web/scanner.py',
                    'src/laplace/core/runtime.py', 'src/laplace/web/writing_server.py',
                    'runtime_profiles.toml', 'scripts/laplace-python', 'scripts/laplace_python.py',
                    'src/laplace/manuscript/proposal_preflight.py', 'src/laplace/manuscript/manuscript_proposals.py',
                    'src/laplace/manuscript/manuscript_source.py', 'src/laplace/manuscript/review_surface.py',
                    'src/laplace/pipeline/authoring.py', 'src/laplace/web/shared_ui.py',
                    'src/atlas/errors.py', 'src/laplace/core/bodies.py', 'src/laplace/core/perimeter.py',
                    'src/laplace/core/__init__.py', 'src/laplace/core/identity.py', 'src/laplace/core/records/__init__.py',
                    'src/laplace/core/records/journal.py', 'src/laplace/core/checkout.py')
    test_paths = ('tests/test_engine_custody_runtime.py','tests/test_writing_controller.py',
                  'tests/engine_mutation_http.py','tests/test_writing_eval_manifest.py')
    baseline_scope = 'Healthy body custody and read integrity; corrupt-existing duplicate put remains a known hole.'
    candidate_scope = 'Body custody only: corrupt-existing duplicate put refuses and Writing retains exact public text inline.'

    def __init__(self, root, request, run):
        self.root = Path(root)
        self.request = request
        self.run = run
        self.calls = []
        self.observations = {}
        self.p0 = self.c0 = self.p1 = self.c1 = None
        self.guide_text = '[Current custody observation](/concepts/state?' + urlencode(
            {'project': self.project, 'node': self.claim}) + ')\n'

    def _http(self, method, path, payload=None, expected=(200,)):
        started = time.perf_counter()
        status, value = self.request(method, path, payload)
        self.calls.append({'method': method, 'route': path.split('?')[0], 'status': status,
                           'seconds': time.perf_counter()-started,
                           'delivered_bytes': len(json.dumps(value, default=str).encode())})
        assert status in expected, (method, path, status, value)
        return value

    def _native(self, operation, payload, turn=None):
        arguments = repr(json.dumps({'operation': operation, 'payload': payload, 'turn': turn}))
        return self.run(f'''import json
from pathlib import Path
from laplace.native import tools as writing_tools
root=Path({str(self.root)!r});a=json.loads({arguments})
value=writing_tools.execute(root,{self.project!r},'work',a['operation'],a['payload'],turn_id=a['turn'])
print(json.dumps(value,default=str))
''')

    def _concept(self, focus=True):
        return self._http('GET', '/concepts/state?' + urlencode({'project': self.project, **({'node': self.claim} if focus else {})}))

    def _change(self, operation, **values):
        current = self._concept()
        return self._http('POST', '/concepts/change', {
            'project': self.project, 'node': self.claim, 'operation': operation,
            'base_revision': current['revision'], 'by': 'author', **values})

    def _work(self):
        return self._http('GET', '/work/state?' + urlencode({
            'project': self.project, 'view': 'detail', 'id': self.work, 'limit': 1}))

    def _guide(self):
        return self._native('project_guidance', {'path': self.guide_path})

    def _artifact(self):
        return self._native('read_artifact', {'path': self.guide_path, 'scope': 'project'})

    def _pin(self, relative):
        target = self.root / relative
        assert target.is_file(), relative
        return {'path': relative, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}

    def _store(self, relative, value, *, before=None):
        content = value if isinstance(value, str) else json.dumps(value, sort_keys=True, indent=2) + '\n'
        return self._native('store_artifact', {'path': relative, 'scope': 'project',
            'before': before, 'content': content, 'reason': 'Controlled source-to-consumer fixture observation'})

    def _source_locator(self):
        lines = (self.root / self.source_paths[0]).read_text().splitlines()
        start = next(i+1 for i, line in enumerate(lines) if line == 'class BlobStore:')
        end = next(i for i, line in enumerate(lines) if line == 'class CompressedHive:')
        return {**self._pin(self.source_paths[0]), 'line_start': start, 'line_end': end}

    def _scope(self, statement):
        self._change('set_source', value=[self._source_locator()])
        self._change('edit_node', value=statement)
        return self._concept()['source_support']['meaning_revision']

    def _verify_observation(self, observation, *, candidate):
        assert isinstance(observation, dict), observation
        assert observation.get('inline') is candidate, observation
        assert observation.get('corruption_preserved') is True, observation
        if candidate:
            assert observation.get('diagnostic', {}).get('status') == 'INLINE_RETAINED', observation
        else:
            assert observation.get('diagnostic') is None, observation
        checks = observation.get('checks')
        assert checks and all(isinstance(check, dict) and set(check) == {'name', 'passed'}
                              and check['passed'] is True for check in checks), observation
        return checks

    def _complete(self, observation, meaning, scope, label, *, candidate, validation_relative=None,validation_before=None):
        checks = self._verify_observation(observation, candidate=candidate)
        result_relative = f'evidence/mechanical-{label}.json'
        stored = self._store(result_relative, observation)
        result_path = str((self.root / stored['path']).relative_to(self.root))
        inputs = [{**self._pin(path),'role':'source'} for path in self.source_paths] + [{**self._pin(path),'role':'test'} for path in self.test_paths]
        validation = {'schema_version': 'laplace.engineering-validation/1',
            'claim_id': self.claim, 'meaning_revision': meaning, 'covered_scope': scope,
            'inputs': inputs, 'outcome': 'PASS', 'checks': checks,
            'result_evidence': self._pin(result_path)}
        receipt = self._store(validation_relative or f'evidence/validation-{label}.json',validation,before=validation_before)
        receipt_path = str((self.root / receipt['path']).relative_to(self.root))
        detail = self._work()
        self._http('POST', '/work/transition', {
            'project': self.project, **detail['allowed_actions']['task_status']['payload'],
            'status': 'done', 'evidence': [pin['path'] for pin in inputs] + [result_path, receipt_path]})
        completed = self._work()['task']
        assert completed['status'] == 'done' and completed['currentness']['status'] == 'CURRENT', completed
        binding = {'work_id': self.work, 'completion_revision': completed['completion_revision'],
                   'meaning_revision': meaning, 'covered_scope': scope, 'validation_path': receipt_path}
        self.observations[label] = {'P': meaning, 'C': completed['completion_revision'],
            'inputs': inputs, 'validation': self._pin(receipt_path), 'result': self._pin(result_path),
            'scope': scope, 'checks': checks}
        return binding

    def _adopt(self, binding):
        adopted = self._change('set_projection', value={'engineering_support': [binding]})['state']
        support = adopted['source_support']['engineering_support']
        assert support['status'] == 'CURRENT', support
        assert support['meaning_revision'] == binding['meaning_revision'], support
        assert self._work()['task']['completion_revision'] == binding['completion_revision']
        return adopted

    def _read_digests(self):
        guide = self._guide(); artifact = self._artifact()
        digests = self.run(f'''import json
from laplace.native import tools as writing_tools
values=json.loads({json.dumps({'guide':guide,'artifact':artifact})!r})
print(json.dumps({{'guide':writing_tools.read_output_digest('project_guidance',values['guide']),
 'artifact':writing_tools.read_output_digest('read_artifact',values['artifact'])}}))
''')
        return guide, artifact, digests

    def _native_claim_cost(self):
        """Instrument actual file IO, never owner/status/provider logic."""
        return self.run(f'''import json,time
from pathlib import Path
from laplace.native import tools as writing_tools
root=Path({str(self.root)!r});target=(root/{self.source_paths[0]!r}).resolve();original=Path.open;opens=[]
def observed_open(path,*args,**kwargs):
 if path.resolve()==target:opens.append(str(path))
 return original(path,*args,**kwargs)
Path.open=observed_open
started=time.perf_counter()
try:value=writing_tools.execute(root,{self.project!r},'work','concept',{{'node':{self.claim!r}}})
finally:Path.open=original
assert len(opens)==1,opens
print(json.dumps({{'source_opens':len(opens),'source_bytes':target.stat().st_size,
 'seconds':time.perf_counter()-started,'delivered_bytes':len(json.dumps(value).encode()),
 'engineering_status':value['source_support']['engineering_support']['status']}}))
''')

    def _seed_consumed_candidate(self):
        """Bank controlled authored records through owners; launch no provider."""
        return self.run(f'''import json
from pathlib import Path
from laplace.web import authoring as c; from laplace.manuscript import manuscript_source, proposal_preflight, manuscript_proposals; from laplace.native import tools as writing_tools
from laplace.pipeline import authoring
root=Path({str(self.root)!r});project={self.project!r};turn='WT-engine-http-consumed';session='WS-engine-http-consumed'
source=manuscript_source.resolve(project,repo_root=root)
selection={{'files':['main.tex'],'line_start':3,'line_end':3}}
context=authoring.build_context(project,selection,repo_root=root)
c._bank(root,{{'record':'writing-session','id':session,'project':project,'provider':'codex','model':'fixture','effort':'low'}})
c._bank(root,{{'record':'writing-turn','id':turn,'session_id':session,'project':project,'mode':'revise','text':'Controlled no-provider proposal',
 'selection':selection,'context_id':context['context_id'],'dependencies':context['dependencies'],'document':context['document']}})
guide=writing_tools.execute(root,project,'work','project_guidance',{{'path':{self.guide_path!r}}},turn_id=turn)
artifact=writing_tools.execute(root,project,'work','read_artifact',{{'path':{self.guide_path!r},'scope':'project'}},turn_id=turn)
text=(root/source['root']).read_text();before=text.splitlines()[2]
edit={{'file':'main.tex','line_start':3,'line_end':3,'before':before,'after':'Controlled candidate prose.','reason':'Fixture only',
 'source_anchor':proposal_preflight.source_anchor(text,3,3)}}
proposal={{'answer':'Controlled authored fixture candidate, no model call','edits':[edit]}}
c._bank(root,{{'record':'writing-reply','id':'WR-engine-http-consumed','turn_id':turn,'session_id':session,'project':project,'status':'completed','proposal':proposal}})
current=c._records(root)['turns'][turn];version=manuscript_proposals.proposal_version(current)[0]
basis=c._proposal_validation_basis(root,current,version,proposal)
print(json.dumps({{'turn_id':turn,'proposal_version':version,'basis':basis,
 'guide_digest':writing_tools.read_output_digest('project_guidance',guide),
 'artifact_digest':writing_tools.read_output_digest('read_artifact',artifact)}}))
''')

    def _proposal_basis(self):
        return self.run(f'''import json
from pathlib import Path
from laplace.web import authoring as c; from laplace.manuscript import manuscript_proposals
root=Path({str(self.root)!r});turn=c._records(root)['turns'][{self.consumed['turn_id']!r}]
version={self.consumed['proposal_version']!r};proposal=manuscript_proposals.saved_proposals(turn)[version]
print(json.dumps(c._proposal_validation_basis(root,turn,version,proposal)))
''')

    def baseline(self, observation):
        self._verify_observation(observation, candidate=False)
        seed = self.run(f'''import json
from pathlib import Path
from laplace.projects import library as writing_projects; from laplace.manuscript import manuscript_source
root=Path({str(self.root)!r});path=root/'scenario-input/main.tex';path.parent.mkdir(parents=True,exist_ok=True)
path.write_text('\\\\documentclass{{article}}\\n\\\\begin{{document}}\\nControlled baseline prose.\\n\\\\end{{document}}\\n')
status,value=writing_projects.import_source({{'name':{self.project!r},'title':'Controlled engineering HTTP fixture','root':'scenario-input/main.tex','editable':True}},root)
assert status==201,value
print(json.dumps(manuscript_source.resolve({self.project!r},repo_root=root)))
''')
        self.source_document = self.root / seed['root']
        self.before_document = self.source_document.read_bytes()
        self._http('POST', '/concepts/change', {'project': self.project, 'operation': 'add_node',
            'node': self.claim, 'node_kind': 'result', 'essence': 'Controlled body custody observation only.',
            'base_revision': self._concept(False)['revision'], 'by': 'author'})
        self.p0 = self._scope('Healthy body identity/dedup and corrupt-read refusal are observed. '
            'Known hole: duplicate put over corrupt existing bytes may emit an unsafe handle. '
            'Safety of that existing-put case is not established at this baseline.')
        self._store(self.guide_path, self.guide_text)
        catalogue = self._native('project_guidance', {})
        self._native('project_guidance_change', {'operation': 'configure',
            'expected_catalog_revision': catalogue['catalog_revision'],
            'guides': [{'path': self.guide_path, 'role': 'background'}]})
        self._http('POST', '/work/task', {'project': self.project, 'id': self.work,
            'title': 'Observe actual body-custody source behavior', 'kind': 'engineering',
            'goal': 'Observe only the exact custody clause with actual baseline/candidate source and test/result pins.'}, expected=(201,))
        binding = self._complete(observation, self.p0, self.baseline_scope, 'baseline',candidate=False)
        self.c0 = binding['completion_revision']; self._adopt(binding)
        guide, artifact, first = self._read_digests()
        assert guide['engineering_support']['status'] == artifact['engineering_support']['status'] == 'CURRENT'
        _, _, repeated = self._read_digests(); assert repeated == first
        self.reads0 = first
        self.consumed = self._seed_consumed_candidate()
        assert self.consumed['basis']['currentness'] == 'CURRENT', self.consumed
        assert self._proposal_basis()['currentness'] == 'CURRENT'
        self.observations['baseline']['unchanged_read_reused'] = True
        self.observations['baseline']['consumed_read_digests'] = first
        self.observations['baseline']['actual_native_claim_cost'] = self._native_claim_cost()

    def source_changed(self):
        work = self._work()['task']; claim = self._concept()
        assert work['status'] == 'blocked' and work['currentness']['kind'] == 'EVIDENCE_CHANGED', work
        assert claim['source_support']['engineering_support']['status'] == 'REVIEW_REQUIRED', claim
        guide, artifact, changed = self._read_digests()
        assert guide['content'] == self.guide_text and artifact['content'] == self.guide_text
        assert guide['engineering_support']['status'] == artifact['engineering_support']['status'] == 'REVIEW_REQUIRED'
        assert changed['guide'] != self.reads0['guide'] and changed['artifact'] != self.reads0['artifact'], changed
        basis = self._proposal_basis(); assert basis['currentness'] != 'CURRENT', basis
        response = self._http('POST', '/authoring/apply', {
            'turn_id': self.consumed['turn_id'], 'proposal_version': self.consumed['proposal_version']}, expected=(409,422))
        assert isinstance(response.get('consumed_read_recovery'),dict), response
        assert self.source_document.read_bytes() == self.before_document
        self.observations['source_changed'] = {'work_status':work['status'],'work_reason':work['currentness']['kind'],
            'claim_support':claim['source_support']['engineering_support']['status'],
            'guide_support':guide['engineering_support']['status'],'same_guide_bytes':True,
            'observed_read_digests':changed,'proposal_basis':basis['currentness'],
            'apply_refused':True,'document_unchanged':True,'refusal_code':response.get('code')}

    def candidate(self, observation):
        # The thunk is essential: P1 precedes the actual candidate checks.
        assert callable(observation), 'Candidate observations must run after live locators/P1 are set'
        self.p1 = self._scope('Observed body custody only: healthy duplicate put retains one content identity; '
            'corrupt existing duplicate put refuses and Writing preserves exact public text inline. '
            'This establishes no broad history, projection, scientific or constant-cost guarantee.')
        actual = observation(); self._verify_observation(actual, candidate=True)
        binding = self._complete(actual, self.p1, self.candidate_scope, 'candidate',candidate=True)
        self.c1 = binding['completion_revision']; assert self.c1 != self.c0 and self.p1 != self.p0
        self._adopt(binding)
        guide, artifact, first = self._read_digests()
        assert guide['content'] == self.guide_text
        assert guide['engineering_support']['status'] == artifact['engineering_support']['status'] == 'CURRENT'
        _, _, repeated = self._read_digests(); assert repeated == first
        assert self._concept()['source_support']['meaning_revision'] == self.p1
        assert self._work()['task']['completion_revision'] == self.c1
        assert self._proposal_basis()['currentness'] != 'CURRENT'  # old C0/P0 is never silently renewed
        self.observations['candidate']['stable_adoption'] = True
        self.observations['candidate']['unchanged_read_reused'] = True
        self.observations['candidate']['old_consumed_proposal_still_stale'] = True
        self.observations['candidate']['actual_native_claim_cost'] = self._native_claim_cost()

    def revalidate_existing(self, observation):
        """Renew the stable receipt through ordinary guarded owner/adoption handles."""
        assert callable(observation), 'Revalidation requires fresh actual observations'
        before=self._concept();old=self._work()['task']
        self.p1=before['source_support']['meaning_revision'];self.c0=old['completion_revision']
        self.p0=self.p1
        bindings=before['source_support']['engineering_support']['bindings']
        assert len(bindings)==1 and bindings[0]['work_id']==self.work
        validation_path=bindings[0]['validation_path']
        old_pin=next(pin for pin in old['evidence_receipts'] if pin['path']==validation_path)
        relative=Path(validation_path).relative_to('writing_projects/'+self.project).as_posix()
        current=self._native('read_artifact',{'path':relative,'scope':'project'})
        old_body=current['content'];old_sha=hashlib.sha256(old_body.encode()).hexdigest()
        assert old_sha==old_pin['sha256'].removeprefix('sha256:')
        material=self._native('materials',{'limit':50})
        record=next(row for row in material['materials'] if row['path']==relative and row['scope']=='project')
        historical_id=record['id'];recovery='owner-record/custody'
        historical_handle={'view':'record','id':'activity:journal:'+historical_id}
        # This exact indexed owner row resolves retained before/after custody.
        # read_artifact(id=ART) instead follows the current path and cannot prove
        # immutable recovery after the stable validation receipt is replaced.
        historical=self._native('author_history',historical_handle,turn='WT-engine-http-consumed')
        assert historical['record_kind']=='writing-artifact'
        assert historical['record']['id']==historical_id
        recovered=historical['record']['after']
        assert hashlib.sha256(recovered.encode()).hexdigest()==old_sha
        recovery_before=historical['read_receipt']
        assert recovery_before['payload']['id']==historical_handle['id']
        actual=observation();self._verify_observation(actual,candidate=True)
        label='candidate-revalidated-'+str(time.time_ns())
        binding=self._complete(actual,self.p1,self.candidate_scope,label,candidate=True,
            validation_relative=relative,validation_before=old_body)
        self.c1=binding['completion_revision'];assert self.c1!=self.c0
        renewal=self._concept();support=renewal['source_support']['engineering_support']
        assert support['bindings'][0]['status']=='ACK_REQUIRED',support
        handle=support['adoption_handle']
        assert handle['operation']=='concept_change'
        adopted=self._http(handle['http']['method'],handle['http']['url'],handle['payload'])['state']
        assert adopted['source_support']['engineering_support']['status']=='CURRENT'
        assert adopted['source_support']['meaning_revision']==self.p1
        assert self._work()['task']['completion_revision']==self.c1
        guide,artifact,first=self._read_digests();_,_,second=self._read_digests()
        assert first==second and guide['content']==self.guide_text
        assert guide['engineering_support']['status']==artifact['engineering_support']['status']=='CURRENT'
        # The old ART owner record recovers retained bytes; id-read of the current
        # path is deliberately not presented as immutable historical recovery.
        historical=self._native('author_history',historical_handle,turn='WT-engine-http-consumed')
        assert historical['record']['id']==historical_id
        assert hashlib.sha256(historical['record']['after'].encode()).hexdigest()==old_sha
        recovery_after=historical['read_receipt']
        assert recovery_after['payload']['id']==historical_handle['id']
        self.observations[label].update(stable_adoption=True,previous_completion=self.c0,
            old_validation_recovery={'id':historical_id,'sha256':old_sha,'basis':recovery,
                'handle':historical_handle,'before_read_receipt':recovery_before,
                'after_read_receipt':recovery_after},
            stable_validation_path=validation_path,ordinary_adoption_handle_used=True,
            actual_native_claim_cost=self._native_claim_cost())
        return self.summary()

    def summary(self):
        return {'project':self.project,'claim':self.claim,'work':self.work,
            'observations':self.observations,'http_calls':len(self.calls),
            'http_seconds':sum(row['seconds'] for row in self.calls),
            'http_delivered_bytes':sum(row['delivered_bytes'] for row in self.calls),
            'model_calls':0,'extra_source_stages':0,'source_mutation_by_helper':False,
            'limits':'Controlled actual owner/server fixture; no provider or parent acceptance.'}
