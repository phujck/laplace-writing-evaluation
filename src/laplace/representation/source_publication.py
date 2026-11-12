"""Selected Source contributions to the active worktree publication.

The current artifact family, operation journal and keeper remain the owners. A
contribution carries its parent facts; it is never a complete-world recapture.
"""
from __future__ import annotations

import copy
import json
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from laplace.core.identity import canonical_bytes, canonical_digest

SCHEMA = 'laplace.current-publication/1'
MODE = 'selected-source-contribution'
TIMING = '.reembed_timing.jsonl'
MAX_TIMING_RECORD = 16*1024*1024  # Existing bound, applied per record; no whole-history cap.
ACT = 'source-publication'
BRANCH = 'operational://declared-source'
PIN = {'type':'string','pattern':'^sha256:[0-9a-f]{64}$'}
_LOCKS = {}
MAX_REQUEST_BYTES = 512 * 1024
OPERATOR_DOORS = ('sdk', 'http', 'publication-cli')
ACTION_FIELDS = {
    'prepare': ('action', 'inputs'),
    'commit': ('action', 'request_id', 'prepared', 'expected_publication_basis'),
    'request': ('action', 'request_id'),
    'recover': ('action', 'request_id'),
    'object': ('action', 'reference', 'selection', 'segments', 'node_id', 'content_handle', 'semantic_handle', 'publication_handle'),
}


def contract():
    return {'type':'object','additionalProperties':False,'required':['action'],
        'properties':{'action':{'enum':list(ACTION_FIELDS)},
            'request_id':{'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.:-]{7,159}$'},
            'inputs':{'type':'array','minItems':1,'maxItems':16,'items':{'type':'object'}},
            'prepared':{'type':'object'},'expected_publication_basis':PIN,
            'reference':{'type':'object'},'selection':{'type':'object'},
            'segments':{'type':'array','minItems':1,'maxItems':1,'items':{'type':'string'}},
            'node_id':{'type':'string','pattern':'^OP-SOURCE-[0-9a-f]{64}$'},
            'content_handle':PIN,'semantic_handle':PIN,'publication_handle':PIN}}


def source_contract():
    """Owner-authored meaning of the existing publisher; pure, stable, no live kernel read."""
    from laplace.work import source_contracts as SC, source_kernel as K
    here='src/laplace/representation/source_publication.py'
    segments={
        'purpose': {'question':'What can this publication change?',
            'meaning':'Add explicitly retained Source meaning to a compatible active publication, preserving unrelated retained facts and authority. No whole-world capture or authored checkpoint close.'},
        'admission': {'request':contract(),'action_fields':{k:list(v) for k,v in ACTION_FIELDS.items()},
            'replay':'The same completed request returns its original outcome before mutable input admission; changed intent refuses.'},
        'inputs': {'request':K.publication_request_contract(),'packet':K.publication_packet_contract(),
            'version_required':True,'custody':['namespace','work_id','handoff_id','obligation_id'],
            'source':'Actual retained Work bodies/context and handed raw pins; caller leaf bodies are never accepted.',
            'merge':'Equal entries deduplicate; conflicting logical contents refuse. Unselected packet entries retain their original bases.'},
        'composition': {'steps':['prepare','admit','stage','publish','request','recover','object','ordinary-carry'],
            'selected_changes':['selected Source leaves','declared collection/root ancestors','graded index','embedding cache','timing receipt'],
            'artifact_family':{'reader':'laplace.representation.embedding_health.publication_artifacts','declaration':'runtime_profiles.toml#publication'},
            'ordinary':'The existing full/incremental publisher separately validates and reconsumes the explicit selected packet under the same publication lock.'},
        'recovery': {'outcomes':{'NONE':'Nonterminal: no admitted original request.','UNKNOWN':'Unresolved original request; preserve it.','REJECTED':'Terminal original failure.','RECORDED':'Original completed outcome; current availability is separate.'},
            'guards':['actual same-root journal-bound backup/stage pins','live owner left alone','only own partial publication can roll back','newer or foreign artifacts/timing refuse','no new-ID retry or invented rollback']},
        'authority': {'operator':{'scope':'owned-workspace','doors':list(OPERATOR_DOORS),'actions':['prepare','commit','request','recover']},
            'object':'Actual caller Scope must admit the selected namespace.',
            'not_authority':['Source grant','native/project turn','Work obligation','read handle','JSON door or scope string'],
            'source_change':'Separate human-issued Source grant, qualified review and Root adoption remain required.'},
        'currentness': {'schema':SCHEMA,'selected_mode':MODE,'ordinary_mode':'ordinary-full-deposit',
            'separate':['current declaration','handed semantic version','current raw source pins','consumer review','original request outcome','active publication','metric/sidecar basis','authored checkpoint'],
            'unselected':'Carried historical facts/authority/bases are not renewed; retained metric and sidecar are not refit by selected publication.',
            'loaded_code':'Current disk pins do not prove loaded Python code identity.',
            'states':{'CURRENT':'Every pinned file still has its retained bytes and the declaration is still in its retained module (declaring_source.path).',
                'CARRIED':'Pinned bytes moved or the declaration moved to another module, but the consumed segment basis and leaf context are unchanged; the leaf keeps its retained pins, content and identity.',
                'STALE':'Pinned bytes moved or the declaration moved to another module, and the current declaration differs in the consumed segment or its leaf context; the retained leaf is published, labelled.',
                'UNKNOWN':'A pinned file, the declaration or a qualified checkout cannot be read for meaning; the retained leaf is published, labelled.'},
            'state_owner':'work.source_kernel gives every selected row one state. Fresh selection admits CURRENT and CARRIED only; the ordinary close publishes STALE and UNKNOWN rows as retained history.',
            'raw_pins':'Pinned file hashes are provenance of the consumed meaning; a row refuses on bytes only where bytes were consumed.',
            'receipt':'The ordinary publication receipt records source_currentness {node_id: {state, moved [{path, retained_sha256, observed_sha256}], changed_segments, reason, by}}; the close receipt and the wake show the four counts.'},
        'descent': {'kind':'current-publication-object','identity':['publication_handle','node_id','content_handle','semantic_handle','reference','selection','segments'],
            'facts':'Exact active artifact/content/custody proof reads retained facts independently of current raw-source admission.',
            'unavailable':'Older unavailable publication bytes refuse; no current-tree substitution or retired-F fallback.',
            'retained_source':'The separate source-contract descent preserves exact retained meaning and its own Scope.'},
        'budgets': {'request_canonical_bytes':MAX_REQUEST_BYTES,'timing_record_bytes':MAX_TIMING_RECORD,
            'selection_groups':K.MAX_SELECTIONS,'segments_per_selection':16,'source_pins':K.MAX_PINS,
            'source_packet_bytes':K.MAX_BYTES,'retained_context_bytes':SC.MAX_BUDGET,
            'history':'Every timing record including its final newline is validated with bounded memory; history I/O remains linear.'}}
    relations=[{'consumer':'kernel.declared-source','relation':'projects','segments':list(segments),'location':'src/laplace/engine/source_kernel_input.py'}]
    for consumer,relation,names,location in [
        ('representation.source_publication.request','implements',['admission','authority','budgets'],here),
        ('representation.source_publication.commit','implements',['inputs','composition','recovery','authority','currentness','budgets'],here),
        ('representation.source_publication','contains',['composition'],here),
        ('sdk.source_publication','projects',['admission','authority','recovery'],'src/laplace/sdk.py'),
        ('cli.reembed.source_publication','projects',['admission','authority','recovery'],'scripts/reembed.py'),
        ('engine.source_kernel_input','consumes',['inputs','currentness'],'src/laplace/engine/source_kernel_input.py'),
        ('engine.keeper.semantic_input_frame','consumes',['inputs','composition'],'src/laplace/engine/keeper.py'),
        ('work.source_kernel.recover','consumes',['descent','authority','currentness'],'src/laplace/work/source_kernel.py'),
        ('engine.descent.current_publication_object','consumes',['descent','authority'],'src/laplace/engine/descent.py'),
        ('web.source_inspector','projects',['purpose','descent','currentness','authority'],'src/laplace/web/static_shared/workspace-source-inspector.mjs'),
        ('tests.source_publication_self_description','evaluates',list(segments),'tests/test_source_publication_self_description.py'),
        ('docs.source_kernel_bridge','explains',['purpose','composition','recovery','authority','currentness','descent'],'docs/source-kernel-bridge.md'),
        ('engine.close_beats','projects',['currentness'],'src/laplace/engine/close_beats.py')]:
        relations.append({'consumer':consumer,'relation':relation,'segments':names,'location':location})
    primitives=[
        ('prepare','source_publication.prepare','selected retained input','none','Trusted operator; exact input and current parent basis.'),
        ('admit','source_publication.commit','original request','journal act after pre-effect checks','Replay first; shared lock; runtime; parent/input revalidation.'),
        ('stage','source_publication._snapshot/_stage_file + keeper.write_skeleton','own staged artifacts','backup/staged files','Exact before-image and bounded timing prefix.'),
        ('publish','source_publication.publish_staged','selected publication','rename then verify','Expected artifacts and unchanged timing.'),
        ('request','source_publication.inspect_request','original outcome','none','Exact request/intent; current standing separate.'),
        ('recover','source_publication.recover','own interrupted request','explicit owned rollback','Live owner/foreign bytes preserved; exact backup/parent.'),
        ('object','source_publication.read_object -> source_kernel.published_facts','exact published facts','none','Actual Scope and publication/node/content/semantic/custody.'),
        ('ordinary-carry','reembed.main -> source_kernel_input.input_frame -> keeper.semantic_input_frame','explicit selection packet','existing ordinary publisher','Same exclusion; original device/metric/close policy.')]
    steps=[dict(zip(('id','primitive','object','effect','guard'),row)) for row in primitives]
    segments['composition']['steps']=steps
    return SC.validate(SC.detached({'schema':SC.SCHEMA,'owner':'domain.representation','operation':'source_publication',
        'purpose':{'text':'Publish selected retained Source meaning and recover its exact facts without renewing unrelated authority.',
            'assumptions':['An active compatible parent must exist.','Selection, review, publication and authored closure are distinct.'],
            'authored_by':'source_publication owner under root-kernel-self-description-implementation-20261028'},
        'segments':segments,'relations':relations,
        'steps':steps,
        'authority':segments['authority'],'recovery':segments['recovery']}))


def _operator(scope):
    if scope.kind != 'owned-workspace' or scope.door not in OPERATOR_DOORS:
        raise ValueError('SOURCE_PUBLICATION_TRUSTED_OPERATOR_ONLY')


@contextmanager
def publication_lock(root):
    """The same root-qualified exclusion used by ordinary and selected publication."""
    from filelock import FileLock
    path = Path(root).resolve()/'contract/.current-publication.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    lock = _LOCKS.setdefault(str(path),FileLock(str(path),timeout=20))
    with lock:yield


def _pin(path):
    import hashlib
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return 'sha256:'+h.hexdigest()


def artifact_rows(root):
    from laplace.representation.embedding_health import publication_artifacts
    root=Path(root).resolve();rows={}
    for item in publication_artifacts(root):
        path=root/item['path']
        if path.is_symlink():raise ValueError('PUBLICATION_ARTIFACT_SYMLINK')
        if not path.exists():
            if item['required']:raise ValueError('PUBLICATION_BASE_INCOMPLETE: '+item['path'])
            rows[item['path']]=None
        elif not path.is_file():raise ValueError('PUBLICATION_ARTIFACT_NOT_FILE')
        else:rows[item['path']]=_pin(path)
    return rows


def _json(path,max_bytes=256*1024*1024):
    if path.is_symlink() or path.stat().st_size>max_bytes:raise ValueError('PUBLICATION_INPUT_BOUND')
    value=json.loads(path.read_bytes())
    if not isinstance(value,dict):raise ValueError('PUBLICATION_OBJECT_REQUIRED')
    return value


def _timing_rows(path):
    """Validate the entire JSONL history with bounded per-record memory."""
    path=Path(path)
    if not path.exists():return
    if path.is_symlink():raise ValueError('PUBLICATION_RECEIPT_SYMLINK')
    with path.open('rb') as stream:
        while raw:=stream.readline(MAX_TIMING_RECORD+1):
            if len(raw)>MAX_TIMING_RECORD:raise ValueError('PUBLICATION_RECEIPT_BOUND')
            if not raw.endswith(b'\n'):raise ValueError('PUBLICATION_RECEIPT_INCOMPLETE')
            if not raw.strip():continue
            try:value=json.loads(raw)
            except (ValueError,UnicodeError) as exc:raise ValueError('PUBLICATION_RECEIPT_MALFORMED') from exc
            if not isinstance(value,dict):raise ValueError('PUBLICATION_RECEIPT_MALFORMED')
            yield value


def _timings(root):
    return _timing_rows(Path(root)/TIMING)


def _journal(root):
    path=Path(root)/'contract/journal.jsonl'
    if not path.exists():return []
    # Existing act custody only; no body/history store or alias ledger.
    values=[]
    with path.open('rb') as stream:
        for raw in stream:
            if not raw.endswith(b'\n'):raise ValueError('PUBLICATION_JOURNAL_INCOMPLETE')
            if raw.strip():
                row=json.loads(raw)
                if not isinstance(row,dict):raise ValueError('PUBLICATION_JOURNAL_MALFORMED')
                if row.get('record') in {'act','act_end','step'}:values.append(row)
    return values


def _verify_receipt(timing,receipt,journal):
    if receipt.get('schema_version')!=SCHEMA:raise ValueError('PUBLICATION_RECEIPT_SCHEMA')
    if canonical_digest({k:v for k,v in receipt.items() if k!='publication_handle'})!=receipt.get('publication_handle'):
        raise ValueError('PUBLICATION_RECEIPT_CORRUPT')
    acts=[r for r in journal if r.get('record')=='act' and r.get('act_id')==timing.get('act_id')]
    if len(acts)!=1:raise ValueError('PUBLICATION_OWNER_ACT_UNAVAILABLE')
    act=acts[0]
    if receipt.get('mode')==MODE:
        if not _operation(act) or receipt.get('act_id')!=act['act_id'] or receipt.get('request_id')!=act.get('request_id') or receipt.get('intent')!=act.get('intent'):
            raise ValueError('PUBLICATION_OTHER_OWNER_ACT')
        completed=[r for r in journal if r.get('record')=='step' and r.get('act_id')==act['act_id'] and r.get('index')==0 and r.get('name')=='stage' and r.get('phase')=='done' and r.get('ok') is True]
        if len(completed)!=1 or json.loads(completed[0].get('detail','{}')).get('publication_handle')!=receipt['publication_handle']:
            raise ValueError('PUBLICATION_STAGED_RECEIPT_UNAVAILABLE')
    elif receipt.get('mode')=='ordinary-full-deposit':
        owner=receipt.get('owner_receipt') or {}
        ends=[r for r in journal if r.get('record')=='act_end' and r.get('act_id')==act['act_id']]
        if owner.get('act_id')!=act['act_id'] or len(ends)!=1 or ends[0].get('status')!='pass':raise ValueError('PUBLICATION_OWNER_COMPLETION_UNAVAILABLE')
        from laplace.representation.embedding_health import _validate_deposit_receipt
        _validate_deposit_receipt(owner)
    else:raise ValueError('PUBLICATION_RECEIPT_MODE')


def current(root):
    """Verify actual current artifacts and owner receipt, never the retired F refs."""
    root=Path(root).resolve();artifacts=artifact_rows(root);timings=_timings(root)
    from laplace.representation import embedding_health as H
    from laplace.engine import meaning_upfold
    _index,matrix=meaning_upfold.read_sidecar(root)
    if matrix is None:raise ValueError('PUBLICATION_BASE_VECTOR_PAIR_UNAVAILABLE')
    journal=_journal(root);ends_by_act={}
    for row in journal:
        if row.get('record')=='act_end':ends_by_act.setdefault(row.get('act_id'),[]).append(row)
    selected=None
    # Keep the newest eligible receipt only, but consume/validate every record:
    # a malformed or incomplete tail is never hidden by an earlier match.
    for timing in timings:
        ends=ends_by_act.get(timing.get('act_id'),[])
        if len(ends)==1 and ends[0].get('status')=='fail':continue
        if timing.get('publication') or (timing.get('act')=='deposit' and len(ends)==1 and ends[0].get('status')=='pass'):
            selected=timing
    if selected is not None:
        receipt=selected.get('publication')
        if receipt:
            if not isinstance(receipt,dict):raise ValueError('PUBLICATION_RECEIPT_MALFORMED')
            _verify_receipt(selected,receipt,journal)
            if receipt.get('artifacts')==artifacts:return copy.deepcopy(receipt)
            raise ValueError('PUBLICATION_ARTIFACTS_CHANGED')
        H._validate_deposit_receipt(selected)
        # Legacy current deposits did not pin all artifacts in their timing row.
        body={'schema_version':SCHEMA,'mode':'retained-legacy-deposit',
            'owner_receipt':selected,'artifacts':artifacts,'source_kernel_inputs':None,
            'qualification':'Actual completed deposit receipt and captured current artifact set; legacy receipt did not itself attest every artifact hash.'}
        return {**body,'publication_handle':canonical_digest(body)}
    raise ValueError('PUBLICATION_BASE_OWNER_RECEIPT_UNAVAILABLE')


def selections(root):
    """Current publication selection custody; absence is not a broad capture request."""
    if not (Path(root)/TIMING).exists():return None
    present=False
    for row in _timings(root):
        if (row.get('publication') or {}).get('source_kernel_inputs'):present=True
    if not present:return None
    return current(root).get('source_kernel_inputs')


def _snapshot(root,names,act_id):
    root=Path(root);folder=root/('.reembed-rollback-'+act_id);folder.mkdir();(folder/'artifacts').mkdir()
    records={}
    import shutil
    for name in names:
        path=root/name
        if path.exists():
            info=path.stat();shutil.copy2(path,folder/'artifacts'/name)
            captured=_pin(folder/'artifacts'/name)
            if captured!=_pin(path):raise ValueError('PUBLICATION_SNAPSHOT_CHANGED')
            records[name]={'present':True,'sha256':captured,'mode':stat.S_IMODE(info.st_mode),
                'atime_ns':info.st_atime_ns,'mtime_ns':info.st_mtime_ns}
        else:records[name]={'present':False}
    (folder/'manifest.json').write_bytes(canonical_bytes({'schema_version':'laplace.publication-backup/1','root':str(root.resolve()),'artifacts':records})+b'\n')
    return folder


def publish_staged(staged,verify_before_last=None,*,before_files=None):
    """Existing rename/rollback seam; caller holds the common publication boundary."""
    before={};replaced=[];terminal=False;before_files=before_files or {}
    for path in staged:
        if path.exists():
            s=path.stat();before[path]=(before_files[path] if path in before_files else path.read_bytes(),stat.S_IMODE(s.st_mode),s.st_atime_ns,s.st_mtime_ns)
        else:before[path]=None
    try:
        for index,(path,temporary) in enumerate(staged.items()):
            if verify_before_last is not None and index==len(staged)-1:verify_before_last()
            os.replace(temporary,path);replaced.append(path)
        terminal=True
    except BaseException:
        for path in reversed(replaced):
            old=before[path]
            if old is None:path.unlink(missing_ok=True);continue
            raw,mode,atime,mtime=old;temporary=path.with_name(path.name+'.publication-restore')
            if isinstance(raw,Path):
                import shutil
                with raw.open('rb') as source,temporary.open('wb') as output:shutil.copyfileobj(source,output,1024*1024)
            else:temporary.write_bytes(raw)
            os.chmod(temporary,mode);os.replace(temporary,path);os.utime(path,ns=(atime,mtime))
        terminal=True
        raise
    finally:
        if terminal:
            for temporary in staged.values():temporary.unlink(missing_ok=True)


def _operation(row):
    return row.get('act')==ACT or (row.get('publication_operation')==ACT and row.get('act')==ACT+'-'+canonical_digest(row.get('request_id'))[7:19])


def _request_rows(root,request_id):
    acts=[row for row in _journal(root) if row.get('record')=='act' and _operation(row) and row.get('request_id')==request_id]
    if len(acts)>1:raise ValueError('PUBLICATION_REQUEST_CUSTODY_AMBIGUOUS')
    return acts


def inspect_request(root,scope,request_id):
    _operator(scope);acts=_request_rows(root,request_id)
    if not acts:return {'state':'NONE','terminal':False,'request_id':request_id}
    act=acts[0]
    found=None;matches=0
    for row in _timings(root):
        receipt=row.get('publication') or {}
        if not isinstance(receipt,dict):raise ValueError('PUBLICATION_RECEIPT_MALFORMED')
        if receipt.get('request_id')==request_id:
            matches+=1
            if found is None:found=receipt
    if matches>1:raise ValueError('PUBLICATION_REQUEST_CUSTODY_AMBIGUOUS')
    if found is not None:
        receipt=found
        _verify_receipt({'act_id':act['act_id']},receipt,_journal(root))
        if receipt.get('intent')!=act['intent']:raise ValueError('PUBLICATION_REQUEST_CORRUPT')
        try:active=current(root);is_current=active['publication_handle']==receipt['publication_handle']
        except (ValueError,OSError,RuntimeError):is_current=False
        return {'state':'RECORDED','terminal':True,'request_id':request_id,'intent':act['intent'],
            'publication':receipt,'current':is_current,
            'qualification':'Original operation outcome; current artifact availability is inspected separately.'}
    ends=[row for row in _journal(root) if row.get('record')=='act_end' and row.get('act_id')==act['act_id']]
    if len(ends)==1 and ends[0].get('status')=='fail':
        return {'state':'REJECTED','terminal':True,'request_id':request_id,'intent':act['intent'],'reason':ends[0].get('summary')}
    return {'state':'UNKNOWN','terminal':False,'request_id':request_id,'intent':act['intent'],'act_id':act['act_id'],
        'reason':'Retained operation has no proven terminal publication; preserve original request and recover, never publish another request.'}


def assert_no_pending(root):
    from laplace.work.owner_discovery import owned_workspace
    ids={r['request_id'] for r in _journal(root) if r.get('record')=='act' and _operation(r)}
    for ident in ids:
        if inspect_request(root,owned_workspace('sdk'),ident)['state']=='UNKNOWN':raise ValueError('PUBLICATION_UNRESOLVED_OPERATION: '+ident)


def _stage(path,raw,act_id):
    temporary=path.with_name(path.name+'.'+act_id+'.stage')
    with temporary.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return temporary


def _stage_file(path,source,act_id,*,append=None,expected=None):
    """Copy an exact prior file and optional bounded final record, never a history-sized buffer."""
    import hashlib
    temporary=path.with_name(path.name+'.'+act_id+'.stage');digest=hashlib.sha256()
    try:
        with Path(source).open('rb') as original,temporary.open('xb') as output:
            while block:=original.read(1024*1024):output.write(block);digest.update(block)
            if expected is not None and 'sha256:'+digest.hexdigest()!=expected:raise ValueError('PUBLICATION_TIMING_CHANGED_DURING_STAGE')
            if append is not None:output.write(append)
            output.flush();os.fsync(output.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _history_plus_record(before,staged,record):
    """Byte-exact prefix and one canonical final row under the existing row bound."""
    tail=canonical_bytes(record)+b'\n'
    if len(tail)>MAX_TIMING_RECORD:raise ValueError('PUBLICATION_RECEIPT_BOUND')
    with Path(before).open('rb') as original,Path(staged).open('rb') as candidate:
        while block:=original.read(1024*1024):
            if candidate.read(len(block))!=block:raise ValueError('PUBLICATION_STAGED_RECEIPT_CHANGED')
        if candidate.read(MAX_TIMING_RECORD+1)!=tail:raise ValueError('PUBLICATION_STAGED_RECEIPT_CHANGED')


def _merge(base,leaves):
    from laplace.engine import keeper
    if '' not in base:raise ValueError('PUBLICATION_BASE_ROOT_UNAVAILABLE')
    built=keeper.build_tree(leaves,parent_of=lambda nid:BRANCH if nid in leaves else None,root_id=BRANCH)
    out=copy.deepcopy(base);changed=set(leaves)|{BRANCH,''}
    for ident in leaves:
        if ident in out and out[ident].get('kind')!='declared-source-contract':raise ValueError('PUBLICATION_NODE_COLLISION')
        out[ident]=built[ident]
    old=out.get(BRANCH)
    if old and old.get('parent') not in ('',None):raise ValueError('PUBLICATION_BRANCH_PARENT_CHANGED')
    members=sorted(set((old or {}).get('members',[]))|set(leaves))
    branch=copy.deepcopy(old or built[BRANCH]);kids=[out[n] for n in members]
    branch.update(members=members,parent='',leaf=False,grade=1+max(k['grade'] for k in kids),
        ascended=keeper.promote_keywords([k['keywords'] for k in kids]),sealed=False)
    branch['keywords']=branch['ascended']
    # A stable collection label avoids changing unrelated retained leaves' parent
    # text merely because a selected sibling was added. Membership/counts remain
    # actual keeper metadata, not an invented source fact.
    branch['essence']=(old or {}).get('essence') or 'Declared Source contract meaning'
    branch['coverage']=sorted(set(branch['keywords']).union(*(set(k.get('coverage',k['keywords'])) for k in kids)))
    out[BRANCH]=branch;root=out[''];root['members']=sorted(set(root.get('members',[]))|{BRANCH})
    root['coverage']=sorted(set(root.get('coverage',[]))|set(branch['coverage']));root['grade']=max(root['grade'],branch['grade']+1);root['leaf']=False
    if not keeper.local_faithfulness(out)['pass']:raise ValueError('PUBLICATION_KEEPER_FAITHFULNESS')
    if any(base[n]!=out[n] for n in base if n not in changed):raise ValueError('PUBLICATION_UNSELECTED_NODE_CHANGED')
    return out,sorted(changed)


def _embed(root,nodes,changed,cache):
    """Only selected/declared ancestor text; never ask an embedder to scan old sources."""
    from laplace.representation import embed_router as E
    backend=E.get_backend()
    if backend is None or not getattr(backend,'gpu',False) or 'CUDAExecutionProvider' not in getattr(backend,'providers',[]):raise ValueError('PUBLICATION_REQUIRED_GPU_UNAVAILABLE')
    if backend.name!=cache.get('backend'):raise ValueError('PUBLICATION_EMBEDDING_GEOMETRY_CHANGED')
    try:
        import numpy as np
        texts=[E.node_text(root,{'nodes':nodes,'lenses':{}},n,{}) for n in changed]
        vectors=backend.embed(texts);entries=copy.deepcopy(cache['nodes'])
        dimension=None
        if entries:dimension=len(E._dequantize_entry(next(iter(entries.values()))))
        for ident,text,vector in zip(changed,texts,vectors,strict=True):
            if dimension is not None and len(vector)!=dimension:raise ValueError('PUBLICATION_VECTOR_DIMENSION_CHANGED')
            if not np.isfinite(np.asarray(vector)).all():raise ValueError('PUBLICATION_VECTOR_NONFINITE')
            entries[ident]={'h':E._hash(backend.name,text),**E._quantize_vec(vector)}
        device={'backend':backend.name,'embedding_backend':'gpu','embedding_providers':list(backend.providers),'required':True,
            'selected_and_derived':len(changed),'unselected_entries':'Byte-identical carried values; no unrelated source text re-read or embedding.'}
        return {**cache,'nodes':entries},device
    finally:E.release_backend(backend)


def _input_frame(root,scope,prepared):
    from laplace.work import source_kernel as K
    return K.validate_publication_inputs(root,scope,prepared)


def prepare(root,scope,inputs):
    _operator(scope)
    from laplace.work import source_kernel as K
    item=K.prepare_publication_inputs(root,scope,inputs);parent=current(root)
    return {'schema_version':'laplace.source-publication-prepared/1','state':'PREPARED',
        'prepared':item['packet'],'expected_publication_basis':parent['publication_handle'],
        'parent':{'mode':parent['mode'],'publication_handle':parent['publication_handle']},
        'qualification':'Pure selected preparation. Commit is explicit; carried kernel is not recaptured or made current.'}


def commit(root,scope,payload):
    _operator(scope);root=Path(root).resolve();intent=canonical_digest(payload)
    with publication_lock(root):
        old=inspect_request(root,scope,payload['request_id'])
        if old['state']!='NONE':
            if old.get('intent')!=intent:raise ValueError('PUBLICATION_REQUEST_INTENT_CHANGED')
            return old
        from laplace.core.runtime import require_system_runtime
        require_system_runtime(Path(__file__).resolve().parents[3])
        assert_no_pending(root)
        parent=current(root)
        if parent['publication_handle']!=payload['expected_publication_basis']:raise ValueError('PUBLICATION_PARENT_CHANGED')
        selected=_input_frame(root,scope,payload['prepared']);frame=selected['frame']
        from laplace.work import source_kernel as K
        replaced={n for n,v in frame['leaves'].items() if parent.get('selected_content',{}).get(n)!=v['projection']}
        retained_inputs=K.merge_publication_inputs(root,scope,parent.get('source_kernel_inputs'),selected['packet'],replaced)
        nodes=_json(root/'.self_graded.json');cache=_json(root/'.self_embeddings.json')
        merged,changed=_merge(nodes,frame['leaves']);embedded,device=_embed(root,merged,changed,cache)
        # Preparation and model computation are still pre-effect. Revalidate all
        # exact bases under the same exclusion immediately before durable admission.
        if current(root)['publication_handle']!=parent['publication_handle']:raise ValueError('PUBLICATION_PARENT_CHANGED')
        if _input_frame(root,scope,payload['prepared'])['frame']!=frame:raise ValueError('PUBLICATION_INPUT_CHANGED')
        from laplace.core.records import journal
        from laplace.engine import keeper
        import shutil
        from laplace.representation.semantic_cadence import process_start_token
        act_id=journal.act_begin(ACT+'-'+canonical_digest(payload['request_id'])[7:19],['stage','publish'],root=root,publication_operation=ACT,request_id=payload['request_id'],intent=intent,process_start=process_start_token(),
            source_input_packet=payload['prepared'],parent_publication=parent['publication_handle'])
        touched=['.self_graded.json','SELF_GRADED_INDEX.md','.self_embeddings.json',TIMING]
        backup=None;staged={};terminal=False
        try:
            backup=_snapshot(root,touched,act_id)
            journal.step_begin(act_id,0,'stage',root=root)
            staged[root/'.self_graded.json']=_stage(root/'.self_graded.json',canonical_bytes(merged),act_id)
            staged[root/'.self_embeddings.json']=_stage(root/'.self_embeddings.json',canonical_bytes(embedded),act_id)
            skeleton=root/('SELF_GRADED_INDEX.md.'+act_id+'.stage')
            keeper.write_skeleton(root,merged,keeper.grade_stats(merged),destination=skeleton);staged[root/'SELF_GRADED_INDEX.md']=skeleton
            expected=dict(parent['artifacts'])
            for path,temporary in staged.items():expected[path.name]=_pin(temporary)
            # Retain owner packet in current keeper/publication custody. The next
            # ordinary full publication validates/reconsumes this explicit packet.
            receipt={'schema_version':SCHEMA,'mode':MODE,'request_id':payload['request_id'],'intent':intent,'act_id':act_id,
                'parent_basis':parent['publication_handle'],'retained_basis':parent.get('retained_basis') or parent['publication_handle'],
                'artifacts':expected,'source_kernel_inputs':retained_inputs,'selected_content':{**parent.get('selected_content',{}),**{n:v['projection'] for n,v in frame['leaves'].items()}},
                'derived_changes':{'nodes':changed,'artifacts':sorted(p.name for p in staged),'basis':'Selected leaves plus exact retained parent; no live unrelated source read.'},
                'coverage':{'kind':'selected-source-contribution','complete_world':False,'unselected':'Carried historical facts/authority/bases unchanged; currentness not renewed.'},
                'device':device,'metric':'Parent metric bytes/receipt carried, not refit or re-certified for new sources.'}
            receipt['publication_handle']=canonical_digest(receipt)
            timing={'act':ACT,'act_id':act_id,'ts':datetime.now(timezone.utc).isoformat(),'mode':MODE,'publication':receipt,
                'embedding_counts':{'embedded':len(changed),'total':len(embedded['nodes']),'deferred':0},'device':device}
            timing_before=_json(backup/'manifest.json')['artifacts'][TIMING]['sha256']
            tail=canonical_bytes(timing)+b'\n'
            if len(tail)>MAX_TIMING_RECORD:raise ValueError('PUBLICATION_RECEIPT_BOUND')
            staged[root/TIMING]=_stage_file(root/TIMING,root/TIMING,act_id,append=tail,expected=timing_before)
            if _json(staged[root/'.self_graded.json'])!=merged or _json(staged[root/'.self_embeddings.json'])!=embedded:raise ValueError('PUBLICATION_STAGE_CHANGED')
            if current(root)['publication_handle']!=parent['publication_handle']:raise ValueError('PUBLICATION_PARENT_CHANGED')
            _input_frame(root,scope,payload['prepared'])
            journal.step_done(act_id,0,'stage',root=root,ok=True,detail=json.dumps({
                'publication_handle':receipt['publication_handle'],'backup_pin':_pin(backup/'manifest.json')},sort_keys=True))
            journal.step_begin(act_id,1,'publish',root=root)
            def validate_artifacts():
                if artifact_rows(root)!=expected:raise ValueError('PUBLICATION_PARENT_CHANGED_DURING_RENAME')
                if _pin(root/TIMING)!=timing_before:raise ValueError('PUBLICATION_FOREIGN_TIMING_CUSTODY')
            publish_staged(staged,verify_before_last=validate_artifacts,before_files={root/TIMING:backup/'artifacts'/TIMING})
            actual=current(root)
            if actual['publication_handle']!=receipt['publication_handle']:raise ValueError('PUBLICATION_RESULT_MISMATCH')
            journal.step_done(act_id,1,'publish',root=root,ok=True)
            journal.act_end(act_id,'pass',root=root,summary='Scoped Source contribution '+receipt['publication_handle'])
            shutil.rmtree(backup);terminal=True
            return inspect_request(root,scope,payload['request_id'])
        except BaseException as error:
            # publish_staged restores its own partial renames. Errors after a
            # complete publication are reconciled from its durable actual receipt.
            try:
                result=inspect_request(root,scope,payload['request_id'])
                if result['state']=='RECORDED':
                    terminal=True
                    return result
                if current(root)['publication_handle']==parent['publication_handle']:
                    journal.act_end(act_id,'fail',root=root,summary=type(error).__name__+': '+str(error))
                    if backup is not None:shutil.rmtree(backup)
                    terminal=True
            except Exception:pass
            raise
        finally:
            if terminal:
                for temporary in staged.values():temporary.unlink(missing_ok=True)


def request(root,scope,payload):
    from jsonschema import Draft202012Validator
    if next(Draft202012Validator(contract()).iter_errors(payload),None):raise ValueError('SOURCE_PUBLICATION_INVALID_REQUEST')
    if len(canonical_bytes(payload))>MAX_REQUEST_BYTES:raise ValueError('SOURCE_PUBLICATION_REQUEST_BOUND')
    action=payload['action']
    allowed=set(ACTION_FIELDS[action])
    if set(payload)!=allowed:raise ValueError('SOURCE_PUBLICATION_INCOMPLETE_OR_EXTRA_FIELDS')
    if action=='prepare':return prepare(root,scope,payload['inputs'])
    if action=='commit':return commit(root,scope,payload)
    if action=='object':return read_object(root,scope,payload)
    if action=='recover':
        _operator(scope)
        return recover(root,scope,payload['request_id'])
    return inspect_request(root,scope,payload['request_id'])


def recover(root,scope,request_id):
    """Explicit original-attempt recovery; never overwrite a newer publication."""
    _operator(scope);root=Path(root).resolve()
    with publication_lock(root):
        prior=inspect_request(root,scope,request_id)
        if prior['state']!='UNKNOWN':return prior
        act=_request_rows(root,request_id)[0]
        from laplace.representation.semantic_cadence import _alive
        if _alive(act.get('pid'),act.get('process_start')):
            return {**prior,'reason':'Original owner process may still be executing; no recovery effect.'}
        backup=root/('.reembed-rollback-'+act['act_id'])
        if not (backup/'manifest.json').is_file():return {**prior,'reason':'Original backup unavailable; no invented rollback.'}
        manifest=_json(backup/'manifest.json')
        if manifest.get('root')!=str(root):raise ValueError('PUBLICATION_BACKUP_OTHER_ROOT')
        if manifest.get('schema_version')!='laplace.publication-backup/1' or set(manifest.get('artifacts',{}))!={'.self_graded.json','SELF_GRADED_INDEX.md','.self_embeddings.json',TIMING}:
            raise ValueError('PUBLICATION_BACKUP_GRAMMAR')
        completed=[r for r in _journal(root) if r.get('record')=='step' and r.get('act_id')==act['act_id'] and r.get('index')==0 and r.get('name')=='stage' and r.get('phase')=='done' and r.get('ok') is True]
        if len(completed)!=1:return {**prior,'reason':'No exact completed staging receipt; preserve unresolved attempt.'}
        binding=json.loads(completed[0].get('detail','{}'))
        if binding.get('backup_pin')!=_pin(backup/'manifest.json'):raise ValueError('PUBLICATION_BACKUP_CHANGED')
        stage=root/(TIMING+'.'+act['act_id']+'.stage')
        if not stage.is_file():return {**prior,'reason':'Intended publication marker unavailable; preserve unresolved attempt.'}
        last=None
        for row in _timing_rows(stage):last=row
        receipt=(last or {}).get('publication',{})
        if receipt.get('intent')!=act['intent'] or receipt.get('parent_basis')!=act['parent_publication']:raise ValueError('PUBLICATION_BACKUP_OTHER_INTENT')
        if canonical_digest({k:v for k,v in receipt.items() if k!='publication_handle'})!=receipt.get('publication_handle') or binding.get('publication_handle')!=receipt['publication_handle']:
            raise ValueError('PUBLICATION_STAGED_RECEIPT_CHANGED')
        _history_plus_record(backup/'artifacts'/TIMING,stage,last)
        try:
            observed=current(root)
            if observed['publication_handle']!=act['parent_publication']:raise ValueError('PUBLICATION_NEWER_THAN_ATTEMPT')
        except (OSError,RuntimeError):pass
        except ValueError as exc:
            if str(exc)=='PUBLICATION_NEWER_THAN_ATTEMPT':raise
        after=receipt['artifacts']
        for name,expected in after.items():
            path=root/name;actual=_pin(path) if path.is_file() else None
            before=manifest['artifacts'].get(name)
            if before is None:
                if actual!=expected:raise ValueError('PUBLICATION_UNRELATED_ARTIFACT_MOVED')
            elif actual not in {expected,before.get('sha256')}:
                raise ValueError('PUBLICATION_NOT_OWN_PARTIAL_STATE')
        for name,row in manifest['artifacts'].items():
            if row['present'] and _pin(backup/'artifacts'/name)!=row['sha256']:raise ValueError('PUBLICATION_BACKUP_CHANGED')
        if _pin(root/TIMING)!=manifest['artifacts'][TIMING]['sha256']:raise ValueError('PUBLICATION_FOREIGN_TIMING_CUSTODY')
        restored={}
        for name,row in manifest['artifacts'].items():
            path=root/name
            if row['present']:
                source=backup/'artifacts'/name
                if _pin(source)!=row['sha256']:raise ValueError('PUBLICATION_BACKUP_CHANGED')
                temporary=_stage_file(path,source,act['act_id']+'-recover',expected=row['sha256'])
                os.chmod(temporary,row['mode']);os.utime(temporary,ns=(row['atime_ns'],row['mtime_ns']));restored[path]=temporary
            elif path.exists():raise ValueError('PUBLICATION_UNEXPECTED_ABSENT_BASE')
        publish_staged(restored,before_files={root/TIMING:backup/'artifacts'/TIMING})
        if current(root)['publication_handle']!=act['parent_publication']:raise ValueError('PUBLICATION_RECOVERY_NOT_PARENT')
        from laplace.core.records import journal
        journal.act_end(act['act_id'],'fail',root=root,summary='Explicit recovery restored exact parent publication; no retry.')
        import shutil
        shutil.rmtree(backup)
        for name in manifest['artifacts']:(root/(name+'.'+act['act_id']+'.stage')).unlink(missing_ok=True)
        return inspect_request(root,scope,request_id)


def _summary(receipt,item):
    allowed=set(item['leaves'])|{BRANCH,''}
    return {'mode':receipt['mode'],'publication_handle':receipt['publication_handle'],
        'parent_basis':receipt.get('parent_basis'),'retained_basis':receipt.get('retained_basis'),
        'coverage':{'kind':'selected-source-proof','complete_world':False,'selected_namespace':item['selection']['namespace']},
        'derived_changes':{'nodes':[n for n in receipt.get('derived_changes',{}).get('nodes',[]) if n in allowed],
            'artifacts':receipt.get('derived_changes',{}).get('artifacts',[])},
        'qualification':'Published selected Source proof. Other sources follow the retained/ordinary publisher basis; this read renews no authority.'}


def counterparts(root,scope,item):
    """A private prepared item is required before any publication metadata lookup."""
    if not scope.admits(item['selection']['namespace']):raise ValueError('SOURCE_KERNEL_NOT_IN_SCOPE')
    try:
        receipt=current(root);tree=_json(Path(root)/'.self_graded.json');rows=[]
        for leaf in item['metadata']:
            projection=item['leaves'][leaf['id']]['projection']
            entries=(receipt.get('source_kernel_inputs') or {}).get('inputs',[])
            if not any(e['node_id']==leaf['id'] and e['request']['selection']==item['selection']
                    and e['request']['reference']==item['reference'] and e['request']['segments']==[leaf['segment']] for e in entries):
                raise ValueError('PUBLICATION_OTHER_SELECTED_CUSTODY')
            if tree.get(leaf['id'],{}).get('projection')!=projection or receipt.get('selected_content',{}).get(leaf['id'])!=projection:
                raise ValueError('PUBLICATION_SELECTED_NODE_UNAVAILABLE')
            target={'reference':item['reference'],'selection':item['selection'],'segments':[leaf['segment']],
                'node_id':leaf['id'],'content_handle':leaf['content_handle'],'semantic_handle':leaf['semantic_handle'],
                'publication_handle':receipt['publication_handle']}
            row={'id':leaf['id'],'content_handle':leaf['content_handle'],'semantic_handle':leaf['semantic_handle'],
                'publication_handle':receipt['publication_handle'],
                'read':{'kind':'current-publication-object','reference':json.dumps(target,sort_keys=True,separators=(',',':'))}}
            state=(item.get('currentness') or {}).get(leaf['id']) or {}
            if state.get('state')=='STALE':
                row['currentness']='retained edition; current declaration differs in '+', '.join(state.get('changed_segments') or [leaf['segment']])
            elif state.get('state')=='UNKNOWN':
                row['currentness']='retained edition; current meaning unknown: '+str(state.get('reason') or '')
            rows.append(row)
        return {'state':'PUBLISHED','publication':_summary(receipt,item),'counterparts':rows}
    except (ValueError,OSError,RuntimeError):
        return {'state':'UNRESOLVED','reason':'No exact active publication proves this selected Source content; no retired F or fuzzy fallback.'}


def read_object(root,scope,payload):
    """Read verified published facts, independently of today's Source admission."""
    selection=payload.get('selection') or {}
    if not scope.admits(selection.get('namespace')):raise ValueError('SOURCE_KERNEL_NOT_IN_SCOPE')
    receipt=current(root)
    if receipt['publication_handle']!=payload['publication_handle']:raise ValueError('PUBLICATION_HISTORICAL_BYTES_UNAVAILABLE')
    entries=(receipt.get('source_kernel_inputs') or {}).get('inputs',[])
    if not any(e['node_id']==payload['node_id'] and e['request']=={
            'reference':payload['reference'],'selection':selection,'segments':payload['segments']} for e in entries):
        raise ValueError('PUBLICATION_OTHER_SELECTED_CUSTODY')
    leaf=_json(Path(root)/'.self_graded.json').get(payload['node_id'])
    projection=(leaf or {}).get('projection') or {}
    if (not leaf or leaf.get('kind')!='declared-source-contract'
            or receipt.get('selected_content',{}).get(payload['node_id'])!=projection
            or projection.get('content_handle')!=payload['content_handle']):
        raise ValueError('PUBLICATION_OTHER_SELECTED_MEANING')
    semantic=canonical_digest({'schema_version':'laplace.semantic-leaf-evidence/1','node_id':payload['node_id'],
        'content_handle':payload['content_handle'],'exact_descent':projection.get('exact_descent')})
    if semantic!=payload['semantic_handle']:raise ValueError('PUBLICATION_OTHER_SELECTED_MEANING')
    from laplace.work import source_kernel as K
    content=K.published_facts(root,scope,{'reference':payload['reference'],'selection':selection,'segments':payload['segments']},projection)
    if canonical_digest(content)!=payload['content_handle']:raise ValueError('PUBLICATION_CONTENT_CHANGED')
    if content.get('segment')!=payload['segments'][0]:raise ValueError('PUBLICATION_OTHER_SELECTED_MEANING')
    item={'selection':selection,'leaves':{payload['node_id']:leaf}}
    return {'schema_version':'laplace.current-publication-object/1','state':'RECOVERED',
        'selection':copy.deepcopy(selection),'reference':copy.deepcopy(payload['reference']),'node_id':payload['node_id'],
        'content_handle':payload['content_handle'],'semantic_handle':semantic,
        'publication_handle':payload['publication_handle'],'publication':_summary(receipt,item),'facts':content,
        'qualification':'Exact published facts on their retained Source basis; current Source admission is separate. No Source review/adoption or authored checkpoint close.'}


def full_publication_receipt(root,owner_receipt,inputs,nodes,parent):
    """Current full publisher records the SAME active receipt family, not retired F.

    `inputs` is the selected packet, or the ordinary close's carry from
    source_kernel_input.close_inputs, whose per-row states (work.source_kernel) are recorded
    as source_currentness once the published leaves are shown to be the validated ones.
    """
    from laplace.engine import source_kernel_input
    inputs,currentness=source_kernel_input.published_currentness(inputs,nodes)
    body={'schema_version':SCHEMA,'mode':'ordinary-full-deposit',
        'owner_receipt':copy.deepcopy(owner_receipt),'artifacts':artifact_rows(root),
        'parent_basis':(parent or {}).get('publication_handle'),
        'retained_basis':None,'source_kernel_inputs':copy.deepcopy(inputs),
        'source_currentness':copy.deepcopy(currentness),
        'selected_content':{n:copy.deepcopy(row['projection']) for n,row in nodes.items()
            if row.get('kind')=='declared-source-contract' and isinstance(row.get('projection'),dict)},
        'derived_changes':{'nodes':[],'artifacts':[], 'basis':'Ordinary publisher/device/metric guards; this metadata is not a new authored close.'},
        'coverage':{'kind':'ordinary-full-deposit','source_subset_only':True},
        'qualification':'Actual active ordinary publication; selected Source receipts remain explicit. Authored checkpoint closure is separate.'}
    return {**body,'publication_handle':canonical_digest(body)}
