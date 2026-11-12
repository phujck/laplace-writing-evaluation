"""Private captured metadata for workflow definitions in their existing dispatch log.

Core supplies capture/reset/selected-row hashing; pipeline.workflow supplies the
strict decoder and definition/pin meaning. This expendable, process-local index
contains no saved definition bodies and grants no caller authority.
"""
from __future__ import annotations
import collections
import copy
import json
from pathlib import Path
import threading
from laplace.core.records import capture
from laplace.core import identity
from laplace.pipeline import workflow as W
from laplace.work import owner_discovery as O

_LOCK=threading.RLock()
_INDEXES=collections.OrderedDict()


def _D():
    from laplace.pipeline import workflow_definitions
    return workflow_definitions


def _path(root):
    root=Path(root).resolve();path=root
    for name in Path(W.LEDGER).parts:
        path=path/name
        if path.is_symlink():raise _D().Refused('DEFINITION_CUSTODY_UNAVAILABLE')
    if path.exists() and not path.is_file():raise _D().Refused('DEFINITION_CUSTODY_UNAVAILABLE')
    return path


class _Index(capture.CapturedLog):
    def __init__(self,root):
        super().__init__(_path(root));self._reset()
        self.stats.update(selected_rows_read=0,selected_bytes_read=0,capture_body_reads=0,capture_body_bytes=0)
    def _reset(self):
        self.definitions=collections.defaultdict(list);self.by_scope=collections.defaultdict(lambda:collections.defaultdict(list));self.prepared=collections.defaultdict(list);self.request_decisions=collections.defaultdict(list)
        self.invalid_nonblank=0
    def _decode(self,raw):
        if not raw.strip():return None
        try:
            row=json.loads(raw,object_pairs_hook=W._unique)
            if not isinstance(row,dict):raise ValueError('not object')
            return row
        except (ValueError,UnicodeError,W.WorkflowRefused):
            self.invalid_nonblank+=1;return None
    def _admit(self,row,raw,offset,end):
        if getattr(self,'_row_limit',None) is not None and self.order>self._row_limit:
            raise _D().Refused('CAPTURE_RESOURCE_BOUND','Admitted capture row budget exhausted before indexing another row')
        meta={'offset':offset,'end':end,'order':self.order,'hash':capture.line_hash(raw)}
        if row.get('record')=='workflow-definition':
            try:_D()._valid_definition_record(row)
            except (ValueError,TypeError,KeyError):self.invalid_nonblank+=1;return False
            item={**meta,'row':copy.deepcopy(row)}
            self.definitions[row['definition_id']].append(item)
            scope=row['scope'];self.by_scope[(scope['kind'],scope.get('namespace'))][row['definition_id']].append(item)
        elif row.get('record')=='workflow-request-decision':
            from laplace.pipeline import workflow_operations as operations
            try:operations.validate_decision(row)
            except (ValueError,TypeError,KeyError):self.invalid_nonblank+=1;return False
            self.request_decisions[row['request_id']].append({**meta,'row':copy.deepcopy(row)})
        elif row.get('record')=='workflow' and row.get('phase')=='declared' and isinstance(row.get('definition_pin'),dict):
            ident=row['definition_pin'].get('definition_id')
            if isinstance(ident,str):
                self.prepared[ident].append({**meta,'id':row.get('id'),'definition_id':ident})
        return True


def _index(root,*,capture_max_bytes=None,metadata_max_rows=None):
    root=Path(root).resolve();path=_path(root);key=str(root)
    if capture_max_bytes is not None and path.exists() and path.stat().st_size>capture_max_bytes:
        raise _D().Refused('CAPTURE_RESOURCE_BOUND','Dispatch capture exceeds admitted bytes')
    value=_INDEXES.pop(key,None) or _Index(root)
    if metadata_max_rows is not None and value.order>metadata_max_rows:
        _INDEXES[key]=value
        raise _D().Refused('CAPTURE_RESOURCE_BOUND','Captured rows exceed admitted metadata budget')
    value._row_limit=metadata_max_rows
    try:value.advance()
    except (OSError,ValueError,W.WorkflowRefused) as exc:
        value.identity=None
        if isinstance(exc,_D().Refused):raise
        raise _D().Refused('DEFINITION_CUSTODY_UNAVAILABLE') from exc
    finally:value._row_limit=None
    _INDEXES[key]=value
    while len(_INDEXES)>4:_INDEXES.popitem(last=False)
    # The generic malformed counter also counts blank lines. Our strict owner
    # tracks invalid NONBLANK records separately, preserving its legacy policy.
    if value.source_status!='AVAILABLE' or value.invalid_nonblank or value.offset!=path.stat().st_size:
        raise _D().Refused('DEFINITION_CUSTODY_UNAVAILABLE','Incomplete, malformed or absent dispatch custody')
    return value


def stats(root):
    """Private diagnostics of already-observed work, not a read or completeness grant."""
    with _LOCK:
        value=_INDEXES.get(str(Path(root).resolve()))
        return {} if value is None else {**value.stats,'definition_rows':sum(map(len,value.definitions.values())),
            'prepared_rows':sum(map(len,value.prepared.values())),'invalid_nonblank':value.invalid_nonblank,
            'captured_bytes':value.offset,'source_status':value.source_status}


def _admit(caller):
    if not isinstance(caller,O.Scope) or caller.kind not in {'project','owned-workspace'}:
        raise _D().Refused('NOT_IN_SCOPE')


def _metas(idx,caller,ident,transfer_project):
    if caller.kind=='project':
        rows=list(idx.by_scope.get(('project',caller.namespace),{}).get(ident,()))
    elif transfer_project is not None:
        rows=sorted([*idx.by_scope.get(('project',transfer_project),{}).get(ident,()),
            *idx.by_scope.get(('owned-workspace',None),{}).get(ident,())],key=lambda m:m['order'])
    else:rows=list(idx.definitions.get(ident,()))
    if transfer_project is not None:
        rows=[m for m in rows if m['row']['scope'] in ({'kind':'project','namespace':transfer_project},{'kind':'owned-workspace'})]
    return rows


def _signature(metas):
    return [(m['order'],m['offset'],m['end'],m['hash']) for m in metas]


def _chain(prefix):
    previous=None;requests=set()
    for meta in prefix:
        row=meta['row']
        if row['previous_revision']!=previous or row['request_id'] in requests:raise _D().Refused('INVALID_EXPORT_CHAIN')
        previous=row['definition_revision'];requests.add(row['request_id'])


def select(root,caller,payload,*,transfer_project=None,detach=True,capture_max_bytes=None,metadata_max_rows=None):
    D=_D();_admit(caller)
    ident,version=D._selector(payload,strict=True) # closed identity before any index lookup
    if transfer_project is not None and not caller.admits(transfer_project):raise D.Refused('NOT_IN_SCOPE')
    with _LOCK:
        idx=_index(root,capture_max_bytes=capture_max_bytes,metadata_max_rows=metadata_max_rows);metas=_metas(idx,caller,ident,transfer_project)
        row,head,history=D._select([m['row'] for m in metas],caller,payload)
        chosen=next(m for m in metas if m['row'] is row)
        prefix=[m for m in metas if m['order']<=chosen['order']]
        counts=collections.Counter(m['row']['definition_revision'] for m in metas)
        if any(counts[m['row']['definition_revision']]!=1 for m in prefix):raise D.Refused('AMBIGUOUS_DEFINITION_VERSION')
        _chain(prefix)
        return {'root':Path(root).resolve(),'caller':caller,'payload':copy.deepcopy(payload),'transfer_project':transfer_project,
            'index':idx,'generation':idx._generation,'selected':copy.deepcopy(chosen) if detach else chosen,'head':copy.deepcopy(head),
            'history':copy.deepcopy(history) if detach else tuple(history),'prefix':copy.deepcopy(prefix) if detach else tuple(prefix),'signature':_signature(prefix),'pins':None}


def raw(frame,meta):
    D=_D();idx=frame['index']
    try:
        _,data=capture.read_captured_row(idx.path,meta['offset'],meta['end'],meta['hash'])
        row=json.loads(data,object_pairs_hook=W._unique)
    except (OSError,ValueError,UnicodeError,W.WorkflowRefused) as exc:
        with _LOCK:idx.identity=None
        raise D.Refused('SELECTED_DEFINITION_ROW_CHANGED') from exc
    with _LOCK:
        idx.stats['selected_rows_read']+=1;idx.stats['selected_bytes_read']+=len(data)
    if 'row' in meta:
        if row!=meta['row']:raise D.Refused('SELECTED_DEFINITION_ROW_CHANGED')
        D._valid_definition_record(row)
    elif row.get('record')!='workflow' or row.get('phase')!='declared' or row.get('id')!=meta['id'] or (row.get('definition_pin') or {}).get('definition_id')!=meta['definition_id']:
        raise D.Refused('SELECTED_DEFINITION_ROW_CHANGED')
    return row,data


def finish(frame,*,check_head=False):
    D=_D()
    with _LOCK:
        idx=_index(frame['root'])
        if idx is not frame['index'] or idx._generation is not frame['generation']:raise D.Refused('SELECTED_DEFINITION_CUT_CHANGED')
        metas=_metas(idx,frame['caller'],frame['selected']['row']['definition_id'],frame['transfer_project'])
        prefix=[m for m in metas if m['order']<=frame['selected']['order']]
        counts=collections.Counter(m['row']['definition_revision'] for m in metas)
        if _signature(prefix)!=frame['signature'] or any(counts[m['row']['definition_revision']]!=1 for m in prefix):raise D.Refused('SELECTED_DEFINITION_CUT_CHANGED')
        if check_head and (not metas or metas[-1]['row']!=frame['head']):raise D.Refused('SELECTED_DEFINITION_CUT_CHANGED')
        if frame['pins'] is not None and _signature(idx.prepared.get(frame['selected']['row']['definition_id'],()))!=frame['pins']:
            raise D.Refused('SELECTED_DEFINITION_CUT_CHANGED')


def body(frame,row,*,with_raw=False):
    value=_D()._body(frame['root'],row,with_raw=True) if with_raw else _D()._body(frame['root'],row)
    with _LOCK:
        frame['index'].stats['capture_body_reads']+=1;frame['index'].stats['capture_body_bytes']+=len(W.canonical(value[0] if with_raw else value))
    return value


def pins(frame):
    ident=frame['selected']['row']['definition_id']
    with _LOCK:
        idx=_index(frame['root'])
        if idx is not frame['index'] or idx._generation is not frame['generation']:raise _D().Refused('SELECTED_DEFINITION_CUT_CHANGED')
        metas=copy.deepcopy(idx.prepared.get(ident,()));frame['pins']=_signature(metas)
    result=[]
    for meta in metas:
        row,_=raw(frame,meta)
        result.append({'run_id':row['id'],'run_path':row['run_path'],'definition_pin':copy.deepcopy(row['definition_pin']),
            'status':'DECLARED','activity':'UNKNOWN; inspect existing run owner'})
    return result


def export(root,caller,reference,*,max_rows=None,max_bytes=None,transfer_project=None):
    D=_D();_admit(caller)
    if any(v is not None and (type(v) is not int or v<0) for v in (max_rows,max_bytes)):raise D.Refused('INVALID_EXPORT_BUDGET')
    frame=select(root,caller,{'reference':reference},transfer_project=transfer_project);prefix=frame['prefix']
    if len(prefix)>32 or max_rows is not None and len(prefix)>max_rows:
        raise D.Refused('EXPORT_BOUND','Exact complete selected prefix exceeds row budget')
    if max_bytes is not None and sum(m['end']-m['offset'] for m in prefix)>max_bytes:raise D.Refused('EXPORT_BOUND')
    # Validate the entire metadata prefix BEFORE opening any saved body. Do not
    # cherry-pick a branch whose predecessors happen to form a convenient chain.
    # Saved bodies are canonical JSON. Their actual file sizes plus the exact
    # package scaffold bound fanout before any body opens; digest/revision and
    # canonical-package checks below remain the authority, not these stat facts.
    body_bytes=0
    for meta in prefix:
        digest=meta['row']['body_handle'].removeprefix('sha256:');path=Path(root).resolve()
        for part in ('contract','writing_bodies',digest[:2],digest):
            path=path/part
            if path.is_symlink():raise D.Refused('UNAVAILABLE_VERSION')
        try:size=path.stat().st_size
        except OSError as exc:raise D.Refused('UNAVAILABLE_VERSION') from exc
        if not path.is_file() or size>D.MAX_BODY:raise D.Refused('UNAVAILABLE_VERSION')
        body_bytes+=size
    scaffold={'schema_version':'laplace.workflow-definition-export/1','definition_id':frame['selected']['row']['definition_id'],
        'versions':[{'row':m['row'],'definition':{}} for m in prefix]}
    if len(W.canonical(scaffold))-2*len(prefix)+body_bytes>min(1_000_000,max_bytes if max_bytes is not None else 1_000_000):raise D.Refused('EXPORT_BOUND')
    versions=[];rows=[]
    for meta in prefix:
        row,data=raw(frame,meta);versions.append({'row':row,'definition':body(frame,row)})
        rows.append((W.LEDGER,meta['order'],data,row))
        if len(W.canonical({'schema_version':'laplace.workflow-definition-export/1','definition_id':row['definition_id'],'versions':versions}))>min(1_000_000,max_bytes if max_bytes is not None else 1_000_000):raise D.Refused('EXPORT_BOUND')
    package=D.validate_export({'schema_version':'laplace.workflow-definition-export/1','definition_id':frame['selected']['row']['definition_id'],'versions':versions})
    finish(frame)
    captured=[{key:copy.deepcopy(meta[key]) for key in ('offset','end','order','hash','row')} for meta in prefix]
    return {'package':package,'rows':rows,'captured':captured,
        'selected_basis':identity.canonical_digest({'scope':caller.public(),'transfer_project':transfer_project,'reference':reference,'rows':frame['signature']}),'stats':stats(root)}
