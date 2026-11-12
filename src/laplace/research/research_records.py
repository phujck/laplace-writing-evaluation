"""RESEARCH RECORDS (S1 B7): guarded record renewal, dependency snapshots and their currentness.

The record lifecycle only: it never admits or runs a producer (writing.research_runs does).

  _records / _record_container / _record_revision   the one records file and an exact record's revision.
  _dependencies / _dependency_specs / _snapshot / _currentness / _renewal_history
                                                    a record's declared inputs, their observed digests,
                                                    CURRENT/STALE/UNKNOWN, and its renewal chain.
  _valid_record / record / _record_locked           the guarded record door: validate, renew the exact
                                                    predecessor, publish once with owned changes.
  reconcile                                         the guarded reconciliation of recorded paths.
"""
from __future__ import annotations

import json
import time
import uuid
import copy
import re
from urllib.parse import urlencode
from laplace.core.identity import require_schema_version
from laplace.core import identity as core_identity, receipts as core_receipts
from laplace.research import research_context

RESEARCH_RECORDS_SCHEMA = "laplace.research-records/1"
_RECORDS = "research_records.json"
_RECORD_PATH_SCOPES = ("config_scope", "source_scope", "result_scope", "data_scope")


def record_input_contract() -> dict:
    """The existing record owner accepts canonical wrapper or flat legacy data."""
    record = {'type': 'object',
     'required': ['kind', 'id'],
     'properties': {'kind': {'enum': ['experiment', 'result', 'figure_binding']},
                    'id': {'type': 'string'},
                    'scope': {'enum': ['project', 'manuscript']},
                    'config': {'type': 'string'},
                    'data': {'type': 'array', 'items': {'type': 'string'}},
                    'source': {'type': 'string'},
                    'result': {'type': 'string'},
                    'run_id': {'type': 'string'},
                    'result_id': {'type': 'string'},
                    'figure_id': {'type': 'string'},
                    'figure_ids': {'type': 'array', 'items': {'type': 'string'}},
                    'evidence_for': {'type': 'array', 'items': {'type': 'string'}},
                    'title': {'type': 'string'},
                    'question': {'type': 'string'},
                    'summary': {'type': 'string'},
                    'limitations': {'type': ['string', 'array'], 'items': {'type': 'string'}},
                    'measures': {'type': 'array',
                                 'items': {'type': 'object',
                                           'required': ['label', 'key'],
                                           'properties': {'label': {'type': 'string'},
                                                          'key': {'type': 'string'},
                                                          'unit': {'type': 'string'}},
                                           'additionalProperties': False}},
                    'artifacts': {'type': 'array',
                                  'items': {'type': 'object',
                                            'required': ['path'],
                                            'properties': {'path': {'type': 'string'},
                                                           'label': {'type': 'string'},
                                                           'caption': {'type': 'string'},
                                                           'scope': {'enum': ['project', 'manuscript']},
                                                           'visual_id': {'type': 'string'}},
                                            'additionalProperties': False}}},
     'additionalProperties': False}
    record['properties'].update({key:{'enum':['manuscript','project']} for key in _RECORD_PATH_SCOPES})
    record['properties']['consumed_bases']={'type':'array','maxItems':80,'items':{'type':'object','required':['reference','basis'],'properties':{'reference':{'type':'object'},'basis':{'type':'string'}},'additionalProperties':False}}
    guard = {"expected_revision":{"type":"string"}}
    return {"description":"Guards bind the selected existing result record, not a collection. Creation uses no nonempty expected guard; renewal requires its current identity.","anyOf":[
        {"type":"object","required":["record"],
         "properties":{"record":record,**guard,"request_id":{"type":"string","pattern":"^[A-Za-z0-9_.:-]{8,160}$"}},"additionalProperties":False},
        {**record,"properties":{**record["properties"],**guard}}]}
from pathlib import Path
from typing import Any, Mapping


def _record_revision(record: dict) -> str:
    content = {key: value for key, value in record.items() if key != "revision"}
    return "sha256:" + research_observation._object_digest(content)


def _dependencies(record: dict) -> list[str]:
    """The closed dependency vocabulary.  Free prose never becomes a path."""
    values: list[str] = []
    for field in ("config", "source", "result"):
        value = record.get(field)
        if isinstance(value, str):
            values.append(value)
    data = record.get("data")
    if isinstance(data, list):
        values.extend(value for value in data if isinstance(value, str))
    return list(dict.fromkeys(values))


def dependency_rows(record: dict) -> list[tuple[str, str, str]]:
    """THE declared dependency scope of a record: (field, path, scope) for config/source/result and each data path,
    each field taking its own ``<field>_scope`` and old records inheriting ``record.scope``. Currentness and the
    displayed evidence files both read scope here, so a project-scoped input is never shown as a missing
    manuscript file."""
    default = record.get("scope", "manuscript")
    rows: list[tuple[str, str, str]] = []
    for field in ("config", "source", "result"):
        value = record.get(field)
        if isinstance(value, str):
            rows.append((field, value, record.get(field + "_scope", default)))
    if isinstance(record.get("data"), list):
        rows.extend(("data", value, record.get("data_scope", default))
                    for value in record["data"] if isinstance(value, str))
    return rows


def _dependency_specs(record: dict) -> list[tuple[str, str]]:
    """Dependency paths with field-specific scope (dependency_rows)."""
    return list(dict.fromkeys((path, scope) for _field, path, scope in dependency_rows(record)))


def _snapshot(manuscript: Path, record: dict, project_root: Path | None = None, *,
              digest_cache: dict | None = None,
              visual_specs: list[dict] | None = None) -> list[dict]:
    default_scope = record.get("scope", "manuscript")
    specs = _dependency_specs(record)
    observations = []
    for path, scope in specs:
        base = project_root if scope == "project" else manuscript
        observation = research_observation._relative_digest(base or manuscript, path,_cache=digest_cache)
        if scope != default_scope:
            observation["scope"] = scope
        observations.append(observation)
    deps = [path for path, _scope in specs]
    seen = {(scope, path) for path, scope in specs}
    derived_presentations = research_presentation._derived_presentation_artifacts(manuscript, record,visual_specs=visual_specs)
    for artifact in record.get('artifacts') or []:
        if not isinstance(artifact, dict) or not isinstance(artifact.get('path'), str):
            continue
        scope = artifact.get('scope', record.get('scope', 'manuscript'))
        identity = (scope, artifact['path'])
        if identity in derived_presentations:
            continue
        if identity in seen:
            continue
        seen.add(identity)
        artifact_base = project_root if scope == 'project' else manuscript
        observation = research_observation._relative_digest(artifact_base or manuscript, artifact['path'],_cache=digest_cache)
        observation['scope'] = scope
        observations.append(observation)
    if record.get("evidence_for") and "figure_manifest.json" not in deps:
        observations.append(research_observation._relative_digest(manuscript, "figure_manifest.json",_cache=digest_cache))
    return observations


def _currentness(manuscript: Path, records: list[dict], project_root: Path | None = None, *,
                 digest_cache: dict | None = None,
                 visual_specs: list[dict] | None = None) -> dict:
    """Compare pinned identities; expanded observation coverage is not a change.

    Older snapshots did not include displayed artifacts. Those bytes have no
    historical attestation. UNTRACKED deliberately remains non-current until
    an explicit reconciliation observes them and preserves the prior receipt.
    """
    checked = []; status = 'CURRENT'
    reason = 'all explicitly declared dependencies match their recorded identities'
    ranks = {'CURRENT':0, 'UNKNOWN':1, 'UNTRACKED':2, 'STALE':3}
    for record in records:
        prior = (record.get('provenance') or {}).get('dependencies')
        now = _snapshot(manuscript, record, project_root,digest_cache=digest_cache,
                        visual_specs=visual_specs)
        default_scope = record.get('scope', 'manuscript')
        def identity(obs):
            scope = obs.get('scope') or ('manuscript' if obs.get('path') == 'figure_manifest.json'
                and record.get('evidence_for') and 'figure_manifest.json' not in _dependencies(record) else default_scope)
            return scope, obs.get('path')
        old = {identity(obs):obs for obs in prior or [] if isinstance(obs,dict)} if isinstance(prior,list) else {}
        current = {identity(obs):obs for obs in now}
        derived_presentations = research_presentation._derived_presentation_artifacts(
            manuscript, record,visual_specs=visual_specs)
        newly = [obs for key,obs in current.items() if key not in old]
        removed = [obs for key,obs in old.items() if key not in current]
        retired_presentations = [obs for key,obs in old.items()
                                 if key not in current and key in derived_presentations]
        removed = [obs for obs in removed if identity(obs) not in derived_presentations]
        changed = [{'before':obs,'now':current.get(key)} for key,obs in old.items()
            if key in current and any(obs.get(field) != current[key].get(field) for field in ('status','sha256','bytes'))]
        pinned_missing = [obs for key,obs in current.items() if key in old and obs.get('status') != 'PRESENT']
        local_status, local_reason = 'CURRENT', 'all pinned dependencies match'
        if changed or removed or pinned_missing:
            local_status, local_reason = 'STALE', 'a pinned source, config, data, result, artifact, or explicit figure-evidence manifest changed or is missing'
        elif not isinstance(prior,list):
            local_status, local_reason = 'UNKNOWN', 'record has no dependency snapshot'
        elif newly:
            local_status, local_reason = 'UNTRACKED', 'declared dependency coverage expanded; newly observed artifact bytes have no historical verification'
        elif not isinstance(prior,list):
            local_status, local_reason = 'UNKNOWN', 'record has no dependency snapshot'
        elif not now and not record.get('run_id'):
            local_status, local_reason = 'UNKNOWN', 'a declaration has no bound source, data, output or run'
        coverage = {'snapshot_schema':(record.get('provenance') or {}).get('snapshot_schema','legacy'),
                    'newly_untracked':newly, 'changed_pins':changed, 'removed_pins':removed,
                    'retired_derived_presentation_pins':retired_presentations,
                    'historical_verification':'NOT_ESTABLISHED_FOR_NEW_COVERAGE' if newly else 'PINNED_DEPENDENCIES_ONLY'}
        checked.append({'record_id':record.get('id'),'dependencies':now,'status':local_status,'reason':local_reason,'coverage':coverage})
        if ranks[local_status] > ranks[status]: status, reason = local_status, local_reason
    if not records: status, reason = 'UNKNOWN', 'no experiment or result records are declared'
    return {'status':status,'reason':reason,'records':checked}


def _record_container(manuscript: Path, default=None) -> tuple[dict, str | None]:
    path = manuscript / _RECORDS
    payload, error = research_observation._read_object(path, default or {'records': [], 'history': []})
    if error:return payload, error
    try:require_schema_version(payload, (RESEARCH_RECORDS_SCHEMA,), owner=f'Research record container {path}', allow_untagged=True)
    except ValueError as exc:return {}, str(exc)
    return payload, None


def _records(manuscript: Path) -> tuple[list[dict], str | None]:
    payload, error = _record_container(manuscript, {"records": []})
    rows = payload.get("records")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return [], error or "records must be an array of objects"
    latest: dict[str, dict] = {}
    anonymous: list[dict] = []
    for row in rows:
        if isinstance(row.get("id"), str) and row.get("id"):
            latest[row["id"]] = row
        else:
            anonymous.append(row)
    return anonymous + list(latest.values()), error


def _renewal_history(manuscript: Path) -> dict[str, list[dict]]:
    """Bounded human projection of the canonical retained record history."""
    payload, error = _record_container(manuscript, {'history': []})
    if error or not isinstance(payload.get('history'), list):
        return {}
    by_id: dict[str, list[dict]] = {}
    for item in payload['history'][-100:]:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str):
            continue
        prior = item.get('record') if isinstance(item.get('record'), dict) else {}
        by_id.setdefault(item['id'], []).append({
            'revision': item.get('revision') or prior.get('revision'),
            'replaced_by': item.get('replaced_by'),
            'archived_at': item.get('archived_at'),
            'recorded_at': (prior.get('provenance') or {}).get('recorded_at'),
            'question': prior.get('question'), 'summary': prior.get('summary'),
            'limitations': prior.get('limitations'),
            'dependencies': list((prior.get('provenance') or {}).get('dependencies') or []),
        })
    return {key: rows[-10:] for key, rows in by_id.items()}


def _valid_record(record: dict) -> str | None:
    if record.get("kind") not in {"experiment", "result", "figure_binding"}:
        return "record.kind must be experiment, result, or figure_binding"
    if not isinstance(record.get("id"), str) or not record["id"].strip():
        return "record.id is required"
    if record.get("scope", "manuscript") not in {"manuscript", "project"}:
        return "record.scope must be manuscript or project"
    for field in _RECORD_PATH_SCOPES:
        if field in record and record[field] not in {"manuscript", "project"}:
            return f"record.{field} must be manuscript or project"
    for field in ("figure_ids", "evidence_for"):
        value = record.get(field, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            return f"record.{field} must be an array of identities"
    if record["kind"] == "figure_binding":
        if not isinstance(record.get("figure_id"), str) or not isinstance(record.get("result_id"), str):
            return "figure_binding requires explicit figure_id and result_id"
    for dependency in _dependencies(record):
        if Path(dependency).is_absolute() or ".." in Path(dependency).parts:
            return f"dependency escapes project: {dependency!r}"
    for field in ('measures', 'artifacts'):
        if not isinstance(record.get(field, []), list): return f'record.{field} must be a list'
    for measure in record.get('measures', []):
        if not isinstance(measure, dict) or not isinstance(measure.get('key'), str) or not isinstance(measure.get('label'), str):
            return 'each measure requires a label and result key'
    for artifact in record.get('artifacts', []):
        if not isinstance(artifact, dict) or not isinstance(artifact.get('path'), str):
            return 'each artifact requires a relative path'
        if Path(artifact['path']).is_absolute() or '..' in Path(artifact['path']).parts:
            return 'artifact path escapes project'
        if artifact.get('scope',record.get('scope','manuscript')) not in {'project','manuscript'}:
            return 'artifact scope must be project or manuscript'
    return None


def record(project: str, payload: dict, root: Path | None = None) -> tuple[int, dict]:
    from filelock import FileLock
    from laplace.core import identity_doors
    try: identity_doors.admit_expected(payload, "research_record", allow_empty=True)   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    except identity_doors.IdentityRefused as refused: return 409, identity_doors.refuse({"error": str(refused)}, refused)
    root = (root or research_context.repo_root()).resolve()
    _item, manuscript = research_context.project(project, root)
    if manuscript is None:
        return 404, {"error": f"unknown project {project!r}"}
    with FileLock(str(manuscript / ".research-records.lock"), timeout=15):
        return _record_locked(project, payload, root)


def record_request_contract():
    value=copy.deepcopy(record_input_contract()['anyOf'][0]);value['required']=['record','request_id']
    return value


def _request_identity(payload):
    request=payload.get('request_id');record=payload.get('record')
    if (not isinstance(request,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{8,160}',request)
            or not isinstance(record,dict) or not isinstance(record.get('id'),str)):
        raise ValueError('Exact canonical record wrapper and stable request_id are required.')
    return {'request_id':request,'intent_digest':core_identity.canonical_digest({k:v for k,v in payload.items() if k!='request_id'})}


def request_read(project,payload):
    return {'native':{'operation':'research','payload':{'view':'record-request','request':copy.deepcopy(payload)}},
        'http':{'method':'GET','url':'/research/record/request?'+urlencode({'project':project,
            'request':json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False)})}}


def inspect_request(project,payload,root=None):
    """Pure recorded-request custody, never fresh admission permission."""
    root=Path(root or research_context.repo_root()).resolve();receipt=_request_identity(payload)
    _,home=research_context.project(project,root)
    base={**receipt,'original_request':copy.deepcopy(payload),'read':request_read(project,payload)}
    if home is None:return {**base,'effect':'UNKNOWN','reason':'Original Research home unavailable.'}
    stored,error=_record_container(home,{'records':[],'history':[]})
    if (error or not isinstance(stored.get('records'),list) or any(not isinstance(r,dict) for r in stored.get('records',[]))
            or not isinstance(stored.get('history',[]),list)
            or any(not isinstance(r,dict) or not isinstance(r.get('record'),dict) for r in stored.get('history',[]))):
        return {**base,'effect':'UNKNOWN','reason':error or 'Original record/history custody unavailable.'}
    rows=[(r,False) for r in stored['records'] if isinstance(r,dict)]
    rows.extend((r['record'],True) for r in stored.get('history',[]) if isinstance(r,dict) and isinstance(r.get('record'),dict))
    if any('record_request' in r and (not isinstance(r['record_request'],dict)
            or set(r['record_request'])!={'request_id','intent_digest'}) for r,_ in rows):
        return {**base,'effect':'UNKNOWN','reason':'Retained request receipt shape is unavailable.'}
    matches=[(r,historical) for r,historical in rows if (r.get('record_request') or {}).get('request_id')==receipt['request_id']]
    if matches:
        if any(r['record_request']!=receipt for r,_ in matches):return {**base,'effect':'CONFLICT','reason':'Recorded request intent differs; no replacement submission.'}
        record,historical=matches[0]
        return {**base,'effect':'RECORDED','record':copy.deepcopy(record),'historical':historical,
            'current_read':{'native':{'operation':'research','payload':{'view':'result','id':record['id']}},
                'http':{'method':'GET','url':'/research/result?'+urlencode({'project':project,'id':record['id']})}}}
    if stored.get('history_dropped') and any(r.get('id')==payload['record']['id'] for r,_ in rows):
        return {**base,'effect':'UNKNOWN','reason':'Selected record request may be outside retained history; do not infer absence.'}
    return {**base,'effect':'NONE','meaning':'Nonterminal observation; explicit retry must preserve the identical original wrapper.'}


def result_action(root,project,run,*,prior=None):
    """An explicit human proposal, with actual run provenance admitted at Save."""
    ident=prior['id'] if prior else 'result-'+core_identity.canonical_digest([project,run['id']])[7:27]
    payload={'request_id':'record-'+uuid.uuid4().hex,'record':{'kind':'result','id':ident,'scope':'project','run_id':run['id'],
        'source':'','result':'','source_scope':(run.get('provenance') or {}).get('producer',{}).get('scope','manuscript'),
        'result_scope':'manuscript'}}
    if prior:payload['expected_revision']=prior.get('revision') or _record_revision(prior)
    return {'id':'record-'+ident,'title':'Revise '+(prior.get('title') or ident) if prior else 'Record result',
        'permitted':True,'fields':[{'name':'record.title','label':'Result title','type':'text','required':True},
            {'name':'record.summary','label':'What this result shows','type':'textarea','required':True},
            {'name':'record.limitations','label':'Assumptions and limitations','type':'textarea','required':True}],
        'http':{'method':'POST','url':'/research/record?'+urlencode({'project':project}),'payload':payload},
        'native':{'operation':'research_record','payload':copy.deepcopy(payload)},
        'request_read':{'http':{'method':'GET','url':'/research/record/request?'+urlencode({'project':project})},'query_field':'request'},
        'new_decision_read':{'native':{'operation':'run_status','payload':{'id':run['id']}},
            'http':{'method':'GET','url':'/research/run/status?'+urlencode({'project':project,'id':run['id']})}},
        'meaning':'Explicit canonical result record from the actual COMPLETE run. Its provenance/currentness is not scientific acceptance.'}


def run_record_actions(root,project,run):
    if run.get('state')!='COMPLETE':return None
    _,home=research_context.project(project,Path(root));rows,error=_records(home) if home else ([], 'Research home unavailable.')
    if error:return {'state':'UNAVAILABLE','reason':error}
    results=[r for r in rows if r.get('kind')=='result'];items=[]
    for prior in results[:20]:
        items.append({'reference':core_identity.reference('domain.research','research-record',{'project':project,'id':prior['id']}),
            'basis':prior.get('revision') or _record_revision(prior),'title':prior.get('title') or prior['id'],
            'action':result_action(root,project,run,prior=prior)})
    new_id='result-'+core_identity.canonical_digest([project,run['id']])[7:27]
    recorded=next((r for r in results if r['id']==new_id),None)
    return {'state':'AVAILABLE','new':result_action(root,project,run,prior=recorded),
        'existing':{'items':items,'coverage':{'known':len(results),'omitted':max(0,len(results)-len(items))}}}


class _RecordRefused(Exception):
    """A record door refusal: the exact (status, body) the door returns."""
    def __init__(self, status: int, body: dict):
        super().__init__(body.get("error"))
        self.status, self.body = status, body


def _record_locked(project: str, payload: dict, root: Path) -> tuple[int, dict]:
    """Under the records lock: the renewal candidate, its supervised run, admission, one publication."""
    root = (root or research_context.repo_root()).resolve()
    item, manuscript = research_context.project(project, root)
    if manuscript is None:
        return 404, {"error": f"unknown project {project!r}"}
    request=None
    if 'request_id' in payload:
        try:observed=inspect_request(project,payload,root);request=_request_identity(payload)
        except ValueError as error:return 422,{'error':str(error)}
        if observed['effect']=='RECORDED':return 200,{'ok':True,'replayed':True,**observed}
        if observed['effect']!='NONE':return 409,{'error':'Original record request is unresolved; inspect it before any new effect.',**observed}
    try:
        candidate, rows, prior, prior_revision, expected_revision = _renewal_candidate(project, payload, root, manuscript)
        candidate.pop('record_request',None)  # only this owner can issue request custody
        project_root = research_context.project_root(item, root) if item is not None else None
        if candidate.get("run_id"):
            _bind_supervised_run(project, manuscript, candidate)
        dependencies = _admit_record(project, manuscript, project_root, candidate, rows, root=root)
    except _RecordRefused as refused:
        return refused.status, refused.body
    if request:candidate['record_request']=request
    candidate["provenance"] = {"dependencies": dependencies, "scope": candidate["scope"],
                          "recorded_at": time.time(), "snapshot_schema":"laplace.research-dependencies/3"}
    candidate["revision"] = _record_revision(candidate)
    published = _publish_record(project, root, manuscript, candidate, rows, prior, prior_revision, expected_revision)
    if isinstance(published, tuple):
        return published
    response=_record_response(manuscript, project_root, candidate, prior, prior_revision, published)
    if request:response.update(effect='RECORDED',request_id=request['request_id'],intent_digest=request['intent_digest'],
        original_request=copy.deepcopy(payload),read=request_read(project,payload))
    return (200 if prior is not None else 201), response


def _renewal_candidate(project: str, payload: dict, root: Path, manuscript: Path) -> tuple[dict, list, dict | None, str | None, Any]:
    """The submitted record, merged over its exact predecessor only when the renewal guard matches."""
    from laplace.manuscript import manuscript_source
    if manuscript_source.resolve(project,repo_root=root).get('read_only'):
        raise _RecordRefused(403, {'error':'source is read-only'})
    candidate = payload.get("record", payload)
    if not isinstance(candidate, dict):
        raise _RecordRefused(422, {"error": "record must be an object"})
    candidate = dict(candidate)
    expected_revision = payload.get("expected_revision", candidate.pop("expected_revision", None))
    candidate.pop("provenance", None)
    candidate.pop("revision", None)
    rows, error = _records(manuscript)
    if error:
        raise _RecordRefused(409, {"error": error})
    prior = next((row for row in rows if row.get("id") == candidate.get("id")), None)
    prior_revision = (prior.get("revision") if prior else None) or (_record_revision(prior) if prior else None)
    if prior is None and (expected_revision is not None or payload.get("expected")):
        raise _RecordRefused(409, {"error": "expected guard names no existing selected record"})
    if prior is not None and prior.get("kind") != candidate.get("kind"):
        raise _RecordRefused(409, {"error": "a stable research id cannot change record kind"})
    if prior is not None:
        from laplace.core import identity_doors
        try:
            identity_doors.gate(
                # The payload, so `expected` reaches the gate -- with the old name's value
                # as this door resolved it, because `expected_revision` may have arrived
                # nested inside `record` (:1201) and the payload alone would lose it.
                "research_record", supplied={**payload,
                                             "expected_revision": expected_revision},
                homes=[("result", "%s::%s" % (project, candidate.get("id")), prior_revision)],
                required=["expected_revision"],
                said="record renewal requires the exact current expected_revision")
        except identity_doors.IdentityRefused as refused:
            raise _RecordRefused(409, identity_doors.refuse(
                {"error": "record renewal requires the exact current expected_revision",
                 "current_revision": prior_revision}, refused))
    if prior is not None:
        preserved = {key:value for key,value in prior.items() if key not in ('provenance','revision')}
        candidate = {**preserved, **candidate}
    if 'consumed_bases' in candidate:
        from laplace.research.object_context import checked_consumed
        try:candidate['consumed_bases']=checked_consumed(candidate['consumed_bases'],project)
        except ValueError as error:raise _RecordRefused(422,{'error':str(error)}) from None
    candidate.setdefault('scope', 'manuscript')
    return candidate, rows, prior, prior_revision, expected_revision


def _bind_supervised_run(project: str, manuscript: Path, candidate: dict) -> None:
    """A result naming a run takes that COMPLETE run's output and producer (a third home's state)."""
    run = research_runs._run_status(manuscript, str(candidate["run_id"]))
    if run is None:
        raise _RecordRefused(422, {"error": "run_id is unavailable; inspect run_status before recording the result"})
    if run.get("state") != "COMPLETE":
        # The ONE refusal kind a fresher identity cannot cure, and the reason `record` is
        # a verb of its own (GRAMMAR.md §3): the gate here is a THIRD home's STATE, not an
        # identity match, so `needed` must name a different read -- not a token.  Folding
        # this into `change` would make `needed` a lie in exactly one case.
        from laplace.core import identity_doors
        raise _RecordRefused(409, identity_doors.refuse(
            {"error": "run_id is not complete and current", "run": {
                key: run.get(key) for key in ("id", "state", "reason", "result_path")}},
            identity_doors.state_not_reached(
                "run_id is not complete and current",
                home="run:%s::%s" % (project, candidate.get("run_id")),
                state=str(run.get("state") or ""), reached="COMPLETE",
                read="run_status {id} -> state")))
    run_result = str(run.get("result_path") or "")
    if candidate.get("result") not in (None, "", run_result):
        raise _RecordRefused(422, {"error": "record.result differs from the supervised run output"})
    if run_result:
        candidate["result"] = run_result
        candidate["result_scope"] = "manuscript"
    producer_path = str(run.get("producer_path") or "")
    producer_scope = str((run.get("provenance") or {}).get("producer", {}).get("scope")
                         or "manuscript")
    if candidate.get("source") in (None, "", producer_path) and producer_path:
        candidate["source"] = producer_path
        if candidate.get("source_scope") not in (None, producer_scope):
            raise _RecordRefused(422, {"error": "record.source_scope contradicts the supervised run producer"})
        candidate["source_scope"] = producer_scope


def _admit_record(project: str, manuscript: Path, project_root, candidate: dict, rows: list, *, root=None) -> list:
    """Shape, binding targets and scopes, then the dependency snapshot a result must fully resolve."""
    issue = _valid_record(candidate)
    if issue: raise _RecordRefused(422, {'error': issue})
    if candidate.get('consumed_bases'):
        from laplace.research.object_context import validate_consumed
        if root is None:raise _RecordRefused(422,{'error':'Explicit input owner root is required.'})
        try:candidate['consumed_bases']=validate_consumed(root,project,candidate['consumed_bases'])
        except ValueError as error:raise _RecordRefused(409,{'error':str(error)}) from None
    if candidate.get('kind')=='figure_binding':
        if candidate.get('result_id') not in {r.get('id') for r in rows if r.get('kind')=='result'}:
            raise _RecordRefused(422,{'error':'figure_binding result_id must name an existing result'})
        figures={f.get('id') for f in research_presentation._manifest_figures(manuscript,project)}
        if candidate.get('figure_id') not in figures:
            raise _RecordRefused(422,{'error':'figure_binding figure_id must name an existing figure'})
    if candidate.get("scope") == "project" and project_root is None:
        raise _RecordRefused(422, {"error": "project-scoped record requires a declared project directory"})
    if project_root is None and any(scope == "project" for _path, scope in _dependency_specs(candidate)):
        raise _RecordRefused(422, {"error": "project-scoped dependency requires a declared project directory"})
    dependencies = _snapshot(manuscript, candidate, project_root)
    if candidate.get("kind") == "result" and any(
            row.get("status") in {"MISSING", "REFUSED"} for row in dependencies):
        raise _RecordRefused(422, {"error": "result dependency is missing or outside its declared scope",
                                   "dependencies": dependencies})
    return dependencies


def _publish_record(project: str, root: Path, manuscript: Path, candidate: dict, rows: list, prior: dict | None,
                    prior_revision, expected_revision) -> dict | tuple:
    """Archive the predecessor (journal row), replace the records file atomically; the owned changes."""
    manuscript.mkdir(parents=True, exist_ok=True)
    target = manuscript / _RECORDS
    before_bytes=target.read_bytes() if target.is_file() else None
    stored, error = _record_container(manuscript, {"records": [], "history": []})
    if error:return 422, {"error":error}
    history = list(stored.get("history") or []) if isinstance(stored.get("history"), list) else []
    prior_dropped = stored.get("history_dropped") if isinstance(stored.get("history_dropped"), int) else 0
    renewal_row=None
    if prior is not None:
        archived = {**prior, "revision": prior_revision}
        history.append({"id": candidate["id"], "archived_at": time.time(),
                        "revision": prior_revision, "replaced_by": candidate["revision"],
                        "record": archived})
        from laplace.core.records import journal
        (root / "contract").mkdir(parents=True, exist_ok=True)
        renewal_row={
            "record": "research-record-renewal",
            "id": "RESNEW-" + uuid.uuid4().hex,
            "project": project, "record_id": candidate["id"],
            "expected_revision": expected_revision,
            "before": archived, "after": candidate,
        }
        if not candidate.get('record_request'):journal.bank_row("contract/talk.jsonl",renewal_row,root=root)
        rows = [row for row in rows if row.get("id") != candidate["id"]]
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps({"schema_version": RESEARCH_RECORDS_SCHEMA,
                                "records": rows + [candidate], "history": history[-100:],
                                "history_dropped": max(0, len(history) - 100)
                                + prior_dropped},
                               indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(target)
    # Request-bound publication and its receipt are one existing canonical
    # replace. A later journal/projection failure is discovered as RECORDED,
    # rather than a misleading NONE after a pre-publication journal effect.
    if renewal_row and candidate.get('record_request'):
        journal.bank_row("contract/talk.jsonl",renewal_row,root=root)
    return {"schema_version":"laplace.owner-mutation/1",
            "files":[core_receipts.file_receipt(root,target,before_bytes,target.read_bytes())],
            "objects":[{"owner":"research","id":candidate["id"],
                        "before_revision":prior_revision,"after_revision":candidate["revision"]}],
            "rewire_records":[],"views":["research","pipeline"]}


def _record_response(manuscript: Path, project_root, candidate: dict, prior: dict | None, prior_revision,
                     owned: dict) -> dict:
    """The recorded record, its currentness, and the one next step that currentness allows."""
    currentness = _currentness(manuscript, [candidate], project_root or manuscript)
    response={"ok":True,"record":candidate,"renewed":prior is not None,
              "previous_revision":prior_revision,"currentness":currentness,
              "owned_changes":owned}
    if candidate.get("kind")=="result" and currentness["status"] == "CURRENT":
        response["next_step"]={"kind":"bind-result-to-claim","required_when":"this result supports a canonical claim",
            "result":{"id":candidate["id"],"revision":candidate["revision"]},
            "reads":[{"operation":"concept","payload":{"node":"<intended canonical claim id>"}},
                     {"operation":"structure","payload":{}}],
            "write":{"operation":"structure_change","payload":{"operation":"bind_results",
                "node":"<intended canonical claim id>","expected_concept_revision":"copy concept revision",
                "expected_revision":"copy structure.revision",
                "results":[{"id":candidate["id"],"revision":candidate["revision"]}]}},
            "safeguard":"Do not infer or auto-attach a claim from source_ref, paths, labels, or wording."}
    elif candidate.get("kind") == "result":
        response["next_step"] = {"kind": "repair-result-currentness",
            "read": {"operation": "research", "payload": {"view": "results", "id": candidate["id"]}},
            "safeguard": "A non-current result cannot be bound to a claim."}
    return response


def reconcile(project: str, payload: dict, root: Path | None = None) -> tuple[int, dict]:
    """Explicitly observe additional coverage without rewriting scientific content."""
    from filelock import FileLock
    root = (root or research_context.repo_root()).resolve()
    item, manuscript = research_context.project(project, root)
    if manuscript is None: return 404, {'error':'unknown project'}
    requested = payload.get('records')
    if not isinstance(requested,list) or not 1 <= len(requested) <= 200 or any(not isinstance(r,dict) or not r.get('id') or not r.get('expected_revision') for r in requested):
        return 422, {'error':'records must contain 1–200 id/expected_revision pairs'}
    if len({r['id'] for r in requested}) != len(requested):
        return 422, {'error':'record ids must be unique'}
    from laplace.manuscript import manuscript_source
    if manuscript_source.resolve(project,repo_root=root).get('read_only'):
        return 403, {'error':'source is read-only'}
    with FileLock(str(manuscript / '.research-records.lock'), timeout=15):
        rows, error = _records(manuscript)
        if error: return 409, {'error':error}
        project_root = research_context.project_root(item, root) or manuscript
        changes = []; unchanged = []
        for request in requested:
            prior = next((row for row in rows if row.get('id') == request['id']), None)
            if not prior: return 404, {'error':'record not found', 'id':request['id']}
            revision = prior.get('revision') or _record_revision(prior)
            if revision != request['expected_revision']:
                return 409, {'error':'expected_revision is stale','id':prior['id'],'current_revision':revision}
            observed = _currentness(manuscript,[prior],project_root)
            if observed['status'] == 'CURRENT':
                unchanged.append(prior['id']); continue
            if observed['status'] != 'UNTRACKED':
                return 409, {'error':'Only expanded untracked coverage can be reconciled; inspect changed evidence and renew explicitly','id':prior['id'],'currentness':observed}
            dependencies = observed['records'][0]['dependencies']
            if any(obs.get('status') != 'PRESENT' for obs in dependencies):
                return 409, {'error':'All newly observed dependencies must exist inside their declared scope','id':prior['id'],'currentness':observed}
            coverage = observed['records'][0]['coverage']; observed_at = time.time()
            candidate = json.loads(json.dumps(prior))
            candidate['provenance'] = {**(prior.get('provenance') or {}), 'dependencies':dependencies,
                'snapshot_schema':'laplace.research-dependencies/3',
                'coverage_reconciliation':{'observed_at':observed_at,'previous_revision':revision,
                    'newly_observed':coverage['newly_untracked'],'historical_verification':'NOT_ESTABLISHED',
                    'note':'These bytes were first pinned by this explicit reconciliation; scientific content is unchanged.'}}
            candidate['revision'] = _record_revision(candidate)
            changes.append({'before':prior,'after':candidate,'previous_revision':revision})
        if not changes: return 200, {'ok':True,'records':[],'unchanged':unchanged}
        target = manuscript / _RECORDS
        before_bytes=target.read_bytes() if target.is_file() else None
        stored, error = _record_container(manuscript, {'records':[], 'history':[]})
        if error: return 409, {'error':error}
        history = list(stored.get('history') or [])
        for change in changes:
            prior, candidate = change['before'], change['after']
            history.append({'id':prior['id'],'archived_at':time.time(),'revision':change['previous_revision'],
                            'replaced_by':candidate['revision'],'record':prior,'reason':'dependency-coverage-reconciliation'})
            rows = [candidate if row.get('id') == prior['id'] else row for row in rows]
        from laplace.core.records import journal
        (root/'contract').mkdir(parents=True,exist_ok=True)
        journal.bank_row('contract/talk.jsonl', {'record':'research-coverage-reconciliation','id':'RESCOV-'+uuid.uuid4().hex,
            'project':project,'changes':changes}, root=root)
        stored.update(schema_version=RESEARCH_RECORDS_SCHEMA,records=rows,history=history[-100:],
                      history_dropped=int(stored.get('history_dropped') or 0)+max(0,len(history)-100))
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(stored,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        temporary.replace(target)
        owned={"schema_version":"laplace.owner-mutation/1",
               "files":[core_receipts.file_receipt(root,target,before_bytes,target.read_bytes())],
               "objects":[{"owner":"research","id":change["after"]["id"],
                           "before_revision":change["previous_revision"],
                           "after_revision":change["after"]["revision"]} for change in changes],
               "rewire_records":[],"views":["research","proofs","visuals"]}
        return 200, {'ok':True,'records':[{'id':change['after']['id'],'previous_revision':change['previous_revision'],
            'revision':change['after']['revision'],'coverage_reconciliation':change['after']['provenance']['coverage_reconciliation']} for change in changes],
            'unchanged':unchanged,'owned_changes':owned,
            'note':'New dependency coverage observed now; no historical verification or scientific validity is asserted.'}


def result_bindings(manuscript: Path, result_ids: list[str],
                    project_root: Path | None = None, *,
                    records_snapshot: tuple[list[dict], str | None] | None = None,
                    currentness_snapshot: Mapping[str,dict] | None = None,
                    run_cache: dict | None = None,
                    digest_cache: dict | None = None,
                    visual_specs: list[dict] | None = None) -> dict:
    """Resolve only explicitly linked research results and their live revision.

    The Research record/currentness join: a binding's currentness is the record's (this owner), and a linked run
    must be COMPLETE (the run owner's status, asked explicitly). Neither dependency freshness nor a COMPLETE run is
    scientific validity; unresolved links and non-current results stay gaps."""
    rows, error = records_snapshot if records_snapshot is not None else _records(manuscript)
    by_id = {row.get("id"): row for row in rows if row.get("kind") == "result"}
    bindings, gaps = [], []
    if error:
        return {"status": "UNRESOLVED", "bindings": [], "gaps": [error]}
    for result_id in dict.fromkeys(result_ids):
        row = by_id.get(result_id)
        if row is None:
            gaps.append(f"linked research result is unresolved: {result_id}")
            continue
        currentness = ((currentness_snapshot or {}).get(str(result_id)) or
            _currentness(manuscript,[row],project_root or manuscript,
                         digest_cache=digest_cache,visual_specs=visual_specs))
        if row.get("run_id"):
            run = research_runs._run_status(manuscript,str(row["run_id"]),_cache=run_cache,
                              _digest_cache=digest_cache)
            if run is None or run.get("state") != "COMPLETE":
                currentness = {**currentness, "status": "STALE",
                               "reason": "the linked result run is not current"}
        revision = row.get("revision") or _record_revision(row)
        binding = {"id": result_id, "revision": revision,
                   "currentness": currentness["status"],
                   "reason": currentness["reason"],
                   "dependencies": currentness.get("records", [])}
        bindings.append(binding)
        if currentness["status"] != "CURRENT":
            gaps.append(f"linked research result is {currentness['status'].lower()}: {result_id}")
    return {"status": "CURRENT" if not gaps else "UNRESOLVED",
            "bindings": bindings, "gaps": gaps}


from laplace.research import research_observation  # noqa: E402  (cycle-safe: imported last)
from laplace.research import research_presentation  # noqa: E402  (cycle-safe: imported last)
from laplace.research import research_runs  # noqa: E402  (cycle-safe: imported last)
