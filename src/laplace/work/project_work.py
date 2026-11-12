"""Dependency-aware project work backed by the existing work-order ledger.

Ownership
  This module owns Work truth for every project: the append-only ledger
  ``corpus_friction/work_orders.jsonl`` (rows ``project-work`` and
  ``project-work-transition``), the per-project fold of those rows into the
  latest task specification, prerequisite/containment/evidence currentness,
  guarded authoring (``task``) and guarded standing changes (``transition``).
  ``project_work_views`` projects this truth for readers (summary/detail/graph);
  ``project_work_surface`` is the HTTP door; ``writing_tools`` is the native door.

Public contract
  ``_tasks(project, root)`` returns the folded specifications for one project
  as deep copies (every nested list and dict); callers may annotate or mutate
  their copy, never the fold. Copying costs O(fold size) per call.
  ``_resolved_tasks`` adds effective status, blockers, currentness and the four
  revision identities consumers pin in guarded mutations. ``state``/``summary``
  are the full Python envelopes used by pipeline and authoring owners; HTTP and
  native readers go through ``project_work_views.read``.

Currentness and cache identity
  The ledger fold is cached per ledger path and keyed by the file's stat
  identity ``(inode, size, mtime_ns, ctime_ns)``. A hit costs O(rows) copying
  instead of parsing the whole JSONL (4.2 MB on the large real project); any
  other writer, including another process, changes the stat identity and forces
  a refold. Two writes landing inside one timestamp tick with identical size and
  inode would not be told apart; the owner's own appends always change the size.
  Evidence digests are cached by resolved path and the same stat identity, so a
  repeated read stats each evidence file instead of rehashing its bytes; a
  changed file is rehashed and its changed digest is reported as before. Nothing
  else is cached across requests: dispatch, literature and reader-plan owners are
  observed on every read because their truth lives outside this ledger.

Retained memory (finite, documented)
  A fold entry retains the parsed rows plus one fold per project that actually
  has rows (an absent namespace retains nothing). Measured resident retention
  is about 2.2 times the ledger bytes (9.1 MB for the 4.2 MB real ledger); the
  caps below are expressed in ledger bytes, a proxy, so the resident bound is
  about 2.2 times ``FOLD_CACHE_MAX_LEDGER_BYTES`` plus the project folds, not a
  strict resident-memory cap. ``FOLD_CACHE_MAX_LEDGER_BYTES`` caps the sum of
  ledger bytes whose folds are retained (least recently used ledgers are evicted
  first) and ``FOLD_CACHE_MAX_ENTRIES`` caps the number of ledgers; a single
  ledger larger than the byte cap is never cached and is parsed on every read,
  complete and untruncated; a reader that needs its rows and a project fold together
  takes both from one capture (``_captured``), and the navigation token and activity
  caches memoize only on the retained entry (``_retained``), so they never hold an
  unretained ledger. ``DIGEST_CACHE_MAX_ENTRIES`` caps the digest cache
  (least recently used first; about 550 B per entry). Eviction only costs a
  later re-read; it never changes a result.

Publication under a threaded server
  Entries are immutable once published: a refold or an append builds new row and
  fold objects and swaps them in with one assignment under ``_CACHE_LOCK``, so a
  reader iterating a published list never observes a mutation, and two in-process
  writers cannot lose each other's cache update. ``_tasks`` returns deep copies
  (every nested list and dict), so a caller or a page projection may annotate or
  mutate what it received without reaching the fold.

Mutation cost (documented, not hidden)
  ``_append`` writes one row, but the owner receipt (``laplace.core.receipts``) hashes
  the ledger bytes before and after the write and the journal stamps the row:
  CPU/read cost is O(ledger bytes) per mutation while retained storage grows by
  exactly one row. After a successful append the fold cache is republished
  (a new row tuple of length rows + 1, O(rows) to build, and the project fold
  with the merged task) when the pre-write stat identity matched the published
  entry; otherwise the entry is dropped and the next read refolds. The
  republication is therefore O(rows) per append, far below the O(ledger bytes)
  receipt hashing beside it, and it is not O(1).

Errors and recovery
  ``WorkConflict`` carries the exact changed-input cure (expected/observed and
  the next owner reads); adapters forward it without re-reading.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

from laplace.core import scoped as core_scoped
from laplace.writing import records as writing_records
from laplace.projects import artifacts
import datetime as dt, hashlib, json, re, threading, uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Mapping

STATUSES={"open","ready","blocked","in-progress","done","verified","cancelled","withdrawn"}
def _root(root=None): return Path(root).resolve() if root else source_tree()
def _ledger(root): return _root(root)/"corpus_friction"/"work_orders.jsonl"

# Ledger fold cache: {ledger path: {'stamp': stat identity, 'rows': (...), 'by_project': {project: {id: task}}}}.
# Entries are published whole and never mutated; see the module docstring (cache identity,
# retained memory, publication). Most recently used last.
_FOLD_CACHE: "OrderedDict[Path, dict[str, Any]]" = OrderedDict()
_CACHE_LOCK=threading.RLock()
FOLD_CACHE_MAX_ENTRIES=4
# Raised from 64 MiB on 2026-11-05. The real ledger reached 111 MB, and an unretained ledger is parsed whole by
# every owner call: one summary read parsed it 17 times (19.6 s; 0.22 s once retained). Revisit as the ledger
# nears this size, or once large phase payloads no longer live in the ledger.
FOLD_CACHE_MAX_LEDGER_BYTES=512*1024*1024  # sum of cached ledger bytes; retention is about 2.2x this
DIGEST_CACHE_MAX_ENTRIES=4096              # about 550 B each, so about 2.3 MB at the cap
_WORK_RECORDS={"project-work","project-work-transition","project-work-phase"}

def _stamp(path):
 """Stat identity of one file: (inode, size, mtime_ns, ctime_ns); None when it does not exist."""
 try: st=path.stat()
 except FileNotFoundError: return None
 return (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

def _fold_rows(text):
 """Parse JSONL rows, splitting records only at the physical LF character.

 ``str.splitlines`` also breaks at NEL (U+0085), LINE SEPARATOR (U+2028) and PARAGRAPH SEPARATOR
 (U+2029), which JSON permits unescaped inside strings, so it cut valid records apart. A CRLF row keeps
 its CR, which json.loads accepts as trailing JSON whitespace; whitespace-only lines are skipped as
 before; a malformed physical record still raises.
 """
 return [json.loads(x) for x in text.split("\n") if x.strip()]

def _deep(value):
 """Copy every nested list and dict; scalars are shared (immutable)."""
 if isinstance(value,dict): return {key:_deep(item) for key,item in value.items()}
 if isinstance(value,list): return [_deep(item) for item in value]
 return value

def _project_fold(rows,project):
 latest={}
 for r in rows:
  if r.get("project")==project and r.get("record") in _WORK_RECORDS: _merge_task(latest,r)
 return latest

def _publish(path,entry):
 """Install one immutable entry, evicting least recently used ledgers past the caps."""
 with _CACHE_LOCK:
  _FOLD_CACHE.pop(path,None)
  if entry['stamp'][1]>FOLD_CACHE_MAX_LEDGER_BYTES:return entry   # oversize: served, never retained
  _FOLD_CACHE[path]=entry
  while len(_FOLD_CACHE)>FOLD_CACHE_MAX_ENTRIES or sum(item['stamp'][1] for item in _FOLD_CACHE.values())>FOLD_CACHE_MAX_LEDGER_BYTES:
   oldest=next(iter(_FOLD_CACHE))
   if oldest==path:break
   _FOLD_CACHE.pop(oldest)
  return entry

def _fold(root):
 """The published ledger fold for this root, refolded when the stat identity changed."""
 p=_ledger(root);stamp=_stamp(p)
 if stamp is None:
  with _CACHE_LOCK:_FOLD_CACHE.pop(p,None)
  return {'stamp':None,'rows':(),'by_project':{}}
 with _CACHE_LOCK:
  entry=_FOLD_CACHE.get(p)
  if entry is not None and entry['stamp']==stamp:
   _FOLD_CACHE.move_to_end(p);return entry
 # Parse outside the lock; a competing refold of the same stamp publishes an equal entry.
 entry={'stamp':stamp,'rows':tuple(_fold_rows(p.read_text(encoding="utf8"))),'by_project':{}}
 return _publish(p,entry)

#: phase-record rows that are NOT review phases attach beside them (in-harness join, 2026-10-20): the development
#: source rows (writing.development_source) and the recipient/delivery rows (writing.work_delivery); same append-only
#: read-only tuple discipline as `phases`, never merged into the specification
_ATTACHED_KINDS={"development-grant":"development","development-candidate":"development","development-effect":"development",
                 "development-check":"development","recipient-binding":"deliveries","work-delivery":"deliveries",
                 # the Work's development lane (development_source.lane, wave 13): its one holder row, beside the grants
                 "development-lane":"development",
                 "work-delivery-policy":"deliveries","work-delivery-route":"deliveries",
                 # explicit human terminal of one exact original route/policy request (work.feedback_route.settle)
                 "work-delivery-request-settlement":"deliveries",
                 # prepared Source completion (project_work_continuity): Source custody beside the grant rows it qualifies
                 "source-completion-intent":"development","source-completion-proof":"development",
                 "source-completion-continue":"development"}
_ATTACHED_KEYS=("phases","planning_history",*sorted(set(_ATTACHED_KINDS.values())))

def _merge_task(latest,r):
 if r.get("record")=="project-work-phase" and r.get("kind")=="work-planning":
  ident=r.get("work_id")
  if ident in latest:
   current=latest[ident];updated={**current,"planning_history":(*(current.get("planning_history") or ()),r)}
   if r.get("effect")=="RECORDED":updated.update(planning=_deep(r["planning"]),planning_revision=r["planning_revision"])
   latest[ident]=updated
  return
 if r.get("record")=="project-work-phase":
  # Review-lifecycle phases (project_work_review) are a per-Work append-only tuple of the ledger's own read-only
  # rows, never merged into the specification and never copied by _tasks (repair1 WR-R4: reads that count or
  # project phases must not copy every phase body).
  ident=r.get("work_id");key=_ATTACHED_KINDS.get(r.get("kind"),"phases")
  if ident in latest:current=latest[ident];latest[ident]={**current,key:(*(current.get(key) or ()),r)}
  return
 ident=r.get("task_id") or r.get("id")
 if ident: latest[ident]={**latest.get(ident,{}),**r}

def _rows(root):
 """Every ledger row as an immutable sequence of read-only dicts (never mutate them)."""
 return _fold(root)['rows']

def _tasks(project, root):
 """Latest specification per Work id for one project, as deep copies the caller owns.

 Only a non-empty fold is retained, so a request for an absent namespace (any string an
 HTTP caller sends) costs one pass over the rows and retains nothing; the first append
 that creates the namespace changes the ledger stamp and is folded on the next read.
 The deep copy costs O(fold size) per call, which is why list pages are the caller's
 to keep, not the owner's.
 """
 _,fold=_captured(project,root)
 return {ident:_copy_task(row) for ident,row in fold.items()}


def _captured(project,root,entry=None):
 """One captured ledger fold and the project fold derived from it in the same owner call: ``(entry, fold)``.

 ``fold`` is the owner's read-only per-project mapping (``{}`` for an absent or empty namespace); never
 mutate it or its rows (``_tasks`` is the caller-owned copy). Pass ``entry`` to derive from a fold the
 caller already captured. A ledger above ``FOLD_CACHE_MAX_LEDGER_BYTES`` is served by a request-local
 entry that is deliberately not retained, so a second ``_fold`` call is a new parse whose ``by_project``
 is empty: a reader that needs rows and a project fold together reuses this pair, never a second lookup,
 or a valid Work would read as absent.
 """
 entry=_fold(root) if entry is None else entry
 fold=entry['by_project'].get(project)
 if fold is None:
  fold=_project_fold(entry['rows'],project)
  if fold:
   with _CACHE_LOCK:
    # Copy-on-write: readers holding the old mapping never see it change.
    entry['by_project']={**entry['by_project'],project:fold}
 return entry,fold


def _retained(root,entry):
 """Whether ``entry`` is the fold this owner currently retains for root's ledger. A secondary cache
 (navigation token, activity) memoizes on an entry's objects only then; otherwise it computes from
 the request's capture and keeps nothing, so it never holds what this owner declined to retain."""
 with _CACHE_LOCK:return _FOLD_CACHE.get(_ledger(root)) is entry


def _copy_task(row):
 """A caller-owned copy of one Work's specification; its review phases stay the fold's read-only tuple."""
 return {key:(value if key in _ATTACHED_KEYS else _deep(value)) for key,value in row.items()}

def fold_cache_state(root):
 """Observable cache facts for tests and documentation; never used for truth."""
 with _CACHE_LOCK:
  entry=_FOLD_CACHE.get(_ledger(root))
  return None if entry is None else {'stamp':entry['stamp'],'rows':len(entry['rows']),'projects':sorted(entry['by_project']),
                                     'entries':len(_FOLD_CACHE),'cached_ledger_bytes':sum(item['stamp'][1] for item in _FOLD_CACHE.values())}

class WorkConflict(ValueError):
 """The owner comparison retains its exact cure; adapters must not re-read it."""
 def __init__(self,message,project,ident,*,expected=None,observed=None,field='as_of'):
  super().__init__(message)
  from laplace.work.project_work_views import handle
  self.details={'code':'CHANGED_INPUT','expected':expected,'observed':observed,'field':field,
      'next_reads':[handle(project,{'view':'detail','id':ident})] if ident else
                   [handle(project,{'view':'summary'})],
      'project':project,'work_id':ident}

def _standing_revision(task):
 value={key:task.get(key) for key in ('status','ts','blocked_reason','summary','completion_work_basis','completion_dependency_basis','evidence_receipts')}
 if task.get('completion_support') is not None:value['completion_support']=task['completion_support']
 return 'sha256:'+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def _completion_identity(task,tasks,cache):
 key=('completion-identity',task['id'])
 if key in cache:return cache[key]
 basis,issue=_work_basis(tasks,task['id'],cache=cache)
 # Acceptance occurrence is distinct from equal goal/output bytes. No bodies copied.
 value={key:task.get(key) for key in ('status','ts','completion_work_basis','evidence_receipts',
       'literature_scope_revision','dispatch_plan_sha256','completion_dependency_basis')}
 if task.get('completion_support') is not None:value['completion_support']=task['completion_support']
 value['scope_revision']=basis['scope_revision'];value['containment_issue']=issue
 cache[key]='sha256:'+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return cache[key]

def _dependency_basis(task,tasks,cache=None):
 cache={} if cache is None else cache
 return [{'work_id':ident,'completion_revision':_completion_identity(tasks[ident],tasks,cache)}
         for ident in task.get('depends_on') or [] if ident in tasks]

def _dependency_revision(task,tasks,cache=None):
 return 'sha256:'+hashlib.sha256(json.dumps(_dependency_basis(task,tasks,cache),sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _task_revision(task):
 """Identity of the work specification consumed by a turn, not its execution state."""
 keys=('id','title','goal','task_kind','parent_work_id','depends_on','section_ids','anchor','obligation_id','logical_target')
 value={key:task.get(key) for key in keys}
 # Opt-in review lifecycle fields join the identity only when authored (legacy hashes unchanged).
 for key in ('review_obligations','followup_origin'):
  if task.get(key) is not None:value[key]=task[key]
 # Preserve accepted legacy task/scope identities; absent optional state is not
 # a new specification field. Authored reader reviews still bind their basis.
 if task.get('reader_basis') is not None:value['reader_basis']=task['reader_basis']
 if task.get('prepared_storyboard') is not None:value['prepared_storyboard']=task['prepared_storyboard']
 if task.get('prepared_workflow') is not None:value['prepared_workflow']=task['prepared_workflow']
 for key in ('manuscript_programme','manuscript_stage'):
  if task.get(key) is not None:value[key]=task[key]
 return 'sha256:'+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _work_ancestors(tasks, ident):
 ancestors=[];seen={ident};parent=tasks.get(ident,{}).get('parent_work_id')
 while parent:
  if parent in seen:return list(reversed(ancestors)), 'Work containment has a cycle at '+str(parent)
  if parent not in tasks:return list(reversed(ancestors)), 'Parent work is unavailable: '+str(parent)
  row=tasks[parent];ancestors.append({'id':parent,'title':row.get('title',''),'goal':row.get('goal',''),
      'revision':_task_revision(row)})
  seen.add(parent);parent=row.get('parent_work_id')
 return list(reversed(ancestors)),None
#: A Work kind that contains other Work for navigation without its own title/goal being consumed by them.
PROGRAMME='programme'


def _work_basis(tasks, ident, *, cache=None):
 """Fold containing goals once; retain an immediate parent pin, not copied ancestry.

 A changed parent scope changes every descendant scope. The ledger retains the
 specifications, while a turn/result stores constant-size consumed identities.
 The cache belongs to one immutable task fold and never survives the read.

 Scoped progress (laplace.core.scoped): containment is not consumption. A parent of kind
 ``programme`` contains its children without its own title/goal becoming their consumed meaning;
 a child consumes the programme's identity and what the programme itself consumed from its own
 parent, so expanding a programme goal does not restale accepted children. Every other parent is
 consumed whole, exactly as before (legacy scope hashes unchanged).
 """
 cache={} if cache is None else cache
 trail=[];seen=set();cursor=ident;issue=None
 while cursor not in cache:
  if cursor in seen:
   issue='Work containment has a cycle at '+str(cursor);break
  if cursor not in tasks:
   issue='Parent work is unavailable: '+str(cursor);break
  seen.add(cursor);trail.append(cursor)
  parent=tasks[cursor].get('parent_work_id')
  if not parent:break
  cursor=parent
 for current in reversed(trail):
  row=tasks[current];parent=row.get('parent_work_id')
  parent_basis,parent_issue=cache.get(parent,(None,issue)) if parent else (None,None)
  problem=issue or parent_issue
  revision=_task_revision(row)
  scope={'work':revision,'parent_scope':parent_basis['scope_revision'] if parent_basis else None}
  if parent_basis and tasks[parent].get('task_kind')==PROGRAMME:
   above=parent_basis.get('parent') or {}
   outer=above.get('scope_revision') or above.get('consumed_revision')
   scope={'work':revision,'parent_scope':None,'container':{'work_id':parent,'consumed':core_scoped.consumed_digest({'outer':outer},['outer'])}}
  scope_revision=None if problem else 'sha256:'+hashlib.sha256(json.dumps(scope,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  cache[current]=({'work_id':current,'revision':revision,'scope_revision':scope_revision,
                   'parent':({'work_id':parent,'scope_revision':scope['parent_scope']} if 'container' not in scope else
                             {'work_id':parent,'scope_revision':None,'consumed':False,'consumed_revision':scope['container']['consumed']})
                            if parent else None},problem)
 return cache[ident]
def _completion_basis_current(recorded,tasks,ident,cache):
 current,issue=_work_basis(tasks,ident,cache=cache)
 if issue:return False,issue
 if 'ancestors' in recorded:
  # Early receipts retained the full chain. Keep them interpretable without
  # rehashing the same parent specifications for each completed descendant.
  ancestors=[];parent=tasks[ident].get('parent_work_id')
  while parent:
   basis,_=cache[parent];ancestors.append({'id':parent,'revision':basis['revision']})
   parent=tasks[parent].get('parent_work_id')
  current={'work_id':ident,'revision':current['revision'],'ancestors':list(reversed(ancestors))}
 return current==recorded,None
def _append(root,row,*,admit=None):
 from laplace.core.records.journal import bank_row
 from laplace.core.receipts import file_receipt, bundle
 from laplace.core.identity import bytes_digest as digest
 from filelock import FileLock
 base=_root(root);path=_ledger(root)
 (base/"contract").mkdir(parents=True,exist_ok=True);path.parent.mkdir(parents=True,exist_ok=True)
 with FileLock(str(path)+".lock",timeout=20):
  # an owner whose guard must hold at the write itself compares here, under this writer lock (owner_discovery.bind)
  if admit is not None:admit()
  # Pre-write stat identity: the cache may be advanced in place only if it still
  # describes exactly these bytes (no other writer slipped in before the lock).
  with _CACHE_LOCK:cached=_FOLD_CACHE.get(path)
  pre_stamp=_stamp(path)
  before=path.read_bytes() if path.is_file() else None
  stamped=bank_row(path,row,root=base)
  intended=(before or b"")+(json.dumps(stamped,ensure_ascii=False,default=str)+"\n").encode("utf-8")
  # Whole-ledger CPU/read cost by contract (laplace.core.receipts hashes before/after bytes);
  # retained storage grows by this one row only.
  receipt=bundle(files=[file_receipt(base,path,before,intended)],
      objects=[{"owner":"project-work","id":row["id"],"before_revision":digest(before),"after_revision":digest(intended)}],views=["project","pipeline"])
  post_stamp=_stamp(path)
  with _CACHE_LOCK:
   current=_FOLD_CACHE.get(path)
   if cached is not None and current is cached and cached['stamp']==pre_stamp and post_stamp is not None and post_stamp[1]==len(intended):
    # Republish: new row tuple and new per-project folds; the old entry stays intact
    # for any reader still iterating it.
    appended=json.loads(json.dumps(stamped,ensure_ascii=False,default=str))
    project=appended.get('project');folds=dict(cached['by_project'])
    if appended.get('record') in _WORK_RECORDS and project in folds:
     merged=dict(folds[project]);_merge_task(merged,appended);folds[project]=merged
    _publish(path,{'stamp':post_stamp,'rows':cached['rows']+(appended,),'by_project':folds})
   else:
    _FOLD_CACHE.pop(path,None)
 return {**row,"owned_changes":receipt,"effects":["project","pipeline"]}
_DISPATCH_LOCKS = {}

def dispatch_lock(root):
 from filelock import FileLock
 path = _root(root)/"contract"/"dispatch-launch.lock"
 path.parent.mkdir(parents=True,exist_ok=True)
 return _DISPATCH_LOCKS.setdefault(str(path), FileLock(str(path), timeout=30))

# Evidence digest cache: {resolved path: (stat identity, sha256, bytes)}, least recently
# used first, capped at DIGEST_CACHE_MAX_ENTRIES. A changed file changes its stat identity
# and is rehashed; an unchanged file costs one stat call; an evicted one costs one re-read.
_DIGEST_CACHE: "OrderedDict[Path, tuple[tuple, str, int]]" = OrderedDict()

def _digest_lookup(path,stamp):
 with _CACHE_LOCK:
  known=_DIGEST_CACHE.get(path)
  if known is None or stamp is None or known[0]!=stamp:return None
  _DIGEST_CACHE.move_to_end(path);return known

def _digest_remember(path,stamp,digest,size):
 with _CACHE_LOCK:
  _DIGEST_CACHE.pop(path,None);_DIGEST_CACHE[path]=(stamp,digest,size)
  while len(_DIGEST_CACHE)>DIGEST_CACHE_MAX_ENTRIES:_DIGEST_CACHE.popitem(last=False)

def _evidence_digest(path, cache=None):
 # One streaming read per distinct artifact in this projection; across requests
 # the stat-identity digest cache replaces the read when the bytes cannot have
 # changed. Changed completion evidence is still observed on the next read.
 if cache is not None and path in cache:return cache[path]
 from laplace.projects import writing_sources
 materialize=cache is not None and path in cache.get(('materialize-evidence',),set()) and path.stat().st_size<=65536
 stamp=_stamp(path);known=None if materialize else _digest_lookup(path,stamp)
 if known is not None:
  digest,size=known[1],known[2]
  if cache is not None:
   # Record the observation in the request state exactly as a streamed read would,
   # so currency scopes report this file without re-reading it.
   state=writing_sources.observation_state(cache)
   state['files'].setdefault(path,{'sha256':digest,'bytes':size,'raw':None})
   # Visits count the evidence once per read; bytes served by stat identity are
   # reported apart from bytes actually hashed (CPU), never folded into them.
   stats=cache.setdefault(('evidence-io',),{'visits':0,'bytes':0})
   stats['visits']+=1;stats['cached_bytes']=stats.get('cached_bytes',0)+size
   cache[path]=digest
  return digest
 observation=writing_sources.observe_bytes(path,cache,
                                            materialize=materialize)
 digest=observation['sha256'];size=observation['bytes']
 if stamp is not None and _stamp(path)==stamp:_digest_remember(path,stamp,digest,size)
 if materialize:cache[('evidence-body',path)]=observation['raw']
 if cache is not None:
  stats=cache.setdefault(('evidence-io',),{'visits':0,'bytes':0})
  stats['visits']+=1;stats['bytes']+=size
 if cache is not None:cache[path]=digest
 return digest
def _evidence_receipts(root, evidence):
 base=_root(root); receipts=[]
 if not isinstance(evidence,list) or not evidence: raise ValueError("done/verified requires evidence paths")
 for value in evidence:
  if not isinstance(value,str) or not value.strip(): raise ValueError("evidence paths must be non-empty strings")
  raw=Path(value.strip())
  if raw.is_absolute() or ".." in raw.parts: raise ValueError("evidence paths must stay inside the active project checkout")
  path=(base/raw).resolve()
  if not path.is_relative_to(base) or not path.is_file(): raise ValueError(f"evidence file does not exist: {value}")
  receipts.append({"path":path.relative_to(base).as_posix(),"sha256":_evidence_digest(path)})
 return receipts
def _evidence_currentness(task,root,*,digests=None,tasks=None,bases=None,read_context=None,core_only=False):
 """Keep absent historical prerequisite pins separate from observable current proof.

 Today's prerequisite identity is an observation, never a reconstruction of what
 an old acceptance consumed. An unpinned legacy acceptance remains unverified,
 while changed evidence keeps its own exact diagnosis and clearing route.
 """
 currency=_completion_currentness(task,root,digests=digests,tasks=tasks,bases=bases,read_context=read_context,core_only=core_only)
 legacy=(task.get('status') in {'done','verified'} and task.get('task_kind')!='session-request'
         and task.get('depends_on') and task.get('completion_dependency_basis') is None)
 if not legacy:return currency
 own_tasks=tasks if tasks is not None else _tasks(task['project'],root)
 missing={'status':'UNKNOWN','kind':'DEPENDENCY_PROOF_MISSING','legacy':True,'basis_status':'UNPINNED_LEGACY',
          'reason':'Historical completion did not retain exact consumed prerequisite acceptance identities; current prerequisites cannot establish what it consumed',
          'consumed_revision':None,'observed_revision':_dependency_revision(task,own_tasks,bases),
          'observed_revision_scope':'Current prerequisites only; not a historical consumed pin'}
 primary=currency if currency['status']!='CURRENT' else missing
 return {**primary,'dependency_basis_status':'UNPINNED_LEGACY','diagnoses':[currency,missing]}

def _completion_currentness(task,root,*,digests=None,tasks=None,bases=None,read_context=None,core_only=False):
 from laplace.writing import prepared_work
 problem=prepared_work._contract_problem(task)
 if problem:return {'status':'UNKNOWN','kind':'MANUSCRIPT_CONTRACT_INVALID','reason':problem}
 if task.get("task_kind")=="session-request" and task.get("status")=="done":
  return {"status":"CURRENT","reason":"session request completion is historical; later source edits do not reopen it","historical":True}
 if task.get("status") not in {"done","verified"}: return {"status":"NOT_REQUIRED","reason":"task is not complete"}
 if 'manuscript_stage' in task:
  from laplace.writing import prepared_work
  if task['manuscript_stage'].get('phase_id')=='judgement':
   from laplace.work import project_work_review
   problem=project_work_review.completion_problem(task,_root(root),tasks if tasks is not None else _tasks(task['project'],root))
   if problem:return {'status':'STALE','kind':'MANUSCRIPT_JUDGEMENT','reason':problem}
  observed=prepared_work.stage_currentness(task,tasks if tasks is not None else _tasks(task['project'],root),_root(root),read_context=read_context,require_qualified=True)
  if observed and observed['status']!='CURRENT':return observed
 if prepared_work._programme_opt_in(task):
  from laplace.writing import prepared_work
  try:problem=prepared_work.programme_outcome_problem(task,tasks if tasks is not None else _tasks(task['project'],root),_root(root))
  except (ValueError,OSError,KeyError) as error:problem=str(error)
  if problem:return {'status':'STALE','kind':'MANUSCRIPT_PROGRAMME_TERMINAL','reason':problem}
 if task.get('completion_work_basis') is not None:
  matches,issue=_completion_basis_current(task['completion_work_basis'],
      tasks if tasks is not None else _tasks(task['project'],root),task['id'],bases if bases is not None else {})
  if not matches:
   current,_=_work_basis(tasks if tasks is not None else _tasks(task['project'],root),task['id'],cache=bases)
   return {'status':'STALE','kind':'WORK_SCOPE_CHANGED','reason':issue or 'The completed work specification or containing goals changed',
           'consumed_revision':task['completion_work_basis'].get('scope_revision') or task['completion_work_basis'].get('revision'),
           'observed_revision':current['scope_revision']}
 if task.get('depends_on'):
  own_tasks=tasks if tasks is not None else _tasks(task['project'],root)
  recorded=task.get('completion_dependency_basis')
  observed=_dependency_basis(task,own_tasks,bases)
  if recorded is not None and recorded!=observed:
   return {'status':'STALE','kind':'DEPENDENCY_BASIS_CHANGED','reason':'A consumed prerequisite completion or scope changed; completing it again does not renew this work',
           'consumed_dependencies':recorded,'observed_dependencies':observed,
           'consumed_revision':'sha256:'+hashlib.sha256(json.dumps(recorded,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
           'observed_revision':_dependency_revision(task,own_tasks,bases)}
 if core_only and task.get('task_kind') in {'literature-acquisition','dispatch'}:
  return {'status':'UNKNOWN','kind':'OWNER_OBSERVATION_REQUIRED',
          'reason':'This prerequisite requires its scoped literature or dispatch owner; a core engineering observation cannot certify it.'}
 if task.get('task_kind')=='literature-acquisition':
  from laplace.research.literature_support import scope
  observed=scope(task['project'],_root(root),task_id=task['id'],read_context=read_context)
  if not observed['ready_for_completion'] or observed['revision']!=task.get('literature_scope_revision'):
   return {'status':'STALE','kind':'LITERATURE_SCOPE_CHANGED','reason':'The consumed literature coverage scope differs from the current owner observation',
           'consumed_revision':task.get('literature_scope_revision'),'observed_revision':observed['revision'],
           'ready_for_completion':observed['ready_for_completion'],'gaps':observed['gaps'],
           'legacy_diff_available':False}
 if task.get('task_kind')=='dispatch':
  cache=read_context if read_context is not None else {}
  key=('dispatch-view',task['id'])
  if key not in cache:cache[key]=dispatch_view(task,task['project'],root,read_context=cache)
  observed=cache[key] or {}
  if observed.get('execution_state')!='COMPLETE' or observed.get('review_state')!='ACCEPTED':
   return {'status':'UNKNOWN' if observed.get('review_state')=='UNVERIFIED' else 'STALE',
           'kind':'DISPATCH_REVIEW_COVERAGE_NOT_CURRENT','reason':'Dispatch completion no longer has current exact accepted per-worker review coverage',
           'review_state':observed.get('review_state'),'uncovered_workers':observed.get('uncovered_workers') or []}
 if task.get('reader_basis') is not None:
  from laplace.manuscript.reader_plan import compare_basis
  reader_cache = (read_context if read_context is not None else {}).setdefault('reader_basis_observations', {})
  reader_currentness=compare_basis(task['project'],_root(root),task['reader_basis'],cache=reader_cache)
  if reader_currentness['status']!='CURRENT':return reader_currentness
 receipts=task.get("evidence_receipts")
 if not isinstance(receipts,list) or not receipts:
  return {"status":"UNKNOWN","kind":"EVIDENCE_PROOF_MISSING","reason":"completion has no exact evidence digest receipts"}
 base=_root(root); checked=[]
 for receipt in receipts:
  if not isinstance(receipt,dict) or not isinstance(receipt.get("path"),str) or not isinstance(receipt.get("sha256"),str):
   return {"status":"UNKNOWN","kind":"EVIDENCE_PROOF_MALFORMED","reason":"completion carries a malformed evidence receipt"}
  raw=Path(receipt["path"]); path=(base/raw).resolve()
  if raw.is_absolute() or ".." in raw.parts or not path.is_relative_to(base) or not path.is_file():
   return {"status":"STALE","kind":"EVIDENCE_MISSING","path":receipt['path'],"consumed_revision":receipt['sha256'],"observed_revision":None,
           "reason":f"completion evidence is missing or outside the checkout: {receipt['path']}","checked":checked}
  digest=_evidence_digest(path,digests); checked.append({"path":receipt["path"],"sha256":digest})
  if digest!=receipt["sha256"]:
   return {"status":"STALE","kind":"EVIDENCE_CHANGED","path":receipt['path'],"consumed_revision":receipt['sha256'],"observed_revision":digest,
           "reason":f"completion evidence changed: {receipt['path']}","checked":checked}
 return {"status":"CURRENT","reason":"all completion evidence matches its recorded digest","checked":checked,
         "work_basis_status":"CURRENT" if task.get('completion_work_basis') is not None else "UNPINNED_LEGACY"}
def observe_core(project, work_ids, root=None, *, read_context=None, materialize_paths=()):
 """Observe only required work and its prerequisite/parent closure, without support facades.

 The request owns one raw ledger snapshot and digest cache. Engineering support
 must not enter the enriched work/literature/concept reader from this layer.
 Specialized prerequisites remain explicitly unknown here.
 """
 root=_root(root);context={} if read_context is None else read_context
 key=('core-work',str(root),project)
 if key not in context:
  context[key]={'tasks':_tasks(project,root),'digests':{},'required':set()}
 snapshot=context[key]
 from laplace.projects import writing_sources
 snapshot['digests'][('source-byte-observations',)]=writing_sources.observation_state(context)
 producers=snapshot.setdefault('producers',set());tasks=snapshot['tasks'];pending=list(dict.fromkeys(work_ids))
 snapshot['digests'].setdefault(('materialize-evidence',),set()).update(
     (root/relative).resolve() for relative in materialize_paths)
 while pending:
  ident=pending.pop()
  if ident in producers:continue
  producers.add(ident);snapshot['required'].add(ident);row=tasks.get(ident,{})
  pending.extend(row.get('depends_on') or [])
  ancestor=row.get('parent_work_id');seen={ident}
  while ancestor and ancestor not in seen:
   seen.add(ancestor);snapshot['required'].add(ancestor)
   ancestor=tasks.get(ancestor,{}).get('parent_work_id')
 selected={ident:tasks[ident] for ident in snapshot['required'] if ident in tasks}
 resolved={row['id']:row for row in _resolved_tasks(selected,root,core_only=True,read_context=context,digests=snapshot['digests'],completion_ids=producers)}
 io=snapshot['digests'].get(('evidence-io',),{})
 return {'tasks':{ident:resolved.get(ident) for ident in dict.fromkeys(work_ids)},
         'read_metrics':{'task_snapshots':1,'required_work_count':len(selected),
                         'unique_evidence_visits':io.get('visits',0),'hashed_bytes':io.get('bytes',0),
                         'digest_cache_bytes':io.get('cached_bytes',0),
                         'receipt_materialization_visits':snapshot['digests'].get(('evidence-materialization-io',),{}).get('visits',0),
                         'receipt_materialization_bytes':snapshot['digests'].get(('evidence-materialization-io',),{}).get('bytes',0)}}

def _read_facets(row):
 """Recorded lifecycle does not become a new job when its acceptance ages.

 Readiness remains the existing prerequisite/currentness gate. These facets are
 projections of that same owner result; no transition or acceptance is changed.
 """
 raw=row.get('recorded_status',row.get('status','open'));currency=row.get('currentness') or {}
 completed=raw in {'done','verified'};closed=raw in {'done','verified','cancelled','withdrawn','informational'}
 current=currency.get('status','UNKNOWN')
 effective=row.get('status');blockers=list(row.get('blocked_by') or [])
 acceptance=('NOT_REQUIRED' if not completed else 'CURRENT' if current=='CURRENT' else
             'REVIEW_REQUIRED' if current=='STALE' else 'UNKNOWN')
 acceptance_reason=currency.get('reason') or '';acceptance_kind=currency.get('kind')
 if completed and current=='CURRENT' and effective=='blocked':
  acceptance='REVIEW_REQUIRED'
  acceptance_kind='PREREQUISITE_ACCEPTANCE_NOT_CURRENT'
  acceptance_reason='Current completion eligibility is blocked by '+', '.join(blockers)+'. Own completion evidence still matches.'
 reason=row.get('blocked_reason') or acceptance_reason
 readiness=('CLOSED' if closed else 'BLOCKED' if effective=='blocked' else
            'IN_PROGRESS' if effective=='in-progress' else 'READY')
 return {'lifecycle':{'status':raw,'completed':completed,'closed':closed},
         'current_acceptance':{'status':acceptance,'currentness':current,'reason':acceptance_reason,
             'kind':acceptance_kind,'blocked_by':blockers,'review_required':completed and acceptance!='CURRENT'},
         'readiness':{'status':readiness,'blocked_by':blockers,'reason':reason,
             'satisfies_prerequisites':completed and effective in {'done','verified'} and current=='CURRENT'}}


def read_counts(rows):
 """Counts cover lifecycle/current acceptance separately, from one resolved cut."""
 from collections import Counter
 return {'total':len(rows),'by_status':dict(Counter(row['status'] for row in rows)),
         'recorded_lifecycle':dict(Counter(row['lifecycle']['status'] for row in rows)),
         'current_acceptance':dict(Counter(row['current_acceptance']['status'] for row in rows)),
         'pending':sum(not row['lifecycle']['closed'] for row in rows),
         'completed':sum(row['lifecycle']['completed'] for row in rows),
         'completed_review_required':sum(row['current_acceptance']['review_required'] for row in rows)}


def _resolved_tasks(tasks,root,*,read_context=None,core_only=False,digests=None,completion_ids=None,review_facets=True):
 """Iterative prerequisite fold; containing goals have their own compact basis."""
 memo={};bases={};read_context={} if read_context is None else read_context
 if digests is None:digests=read_context.setdefault(('work-evidence',str(_root(root))),{})
 from laplace.projects import writing_sources
 digests[('source-byte-observations',)]=writing_sources.observation_state(read_context)
 if not core_only:
  for project in {row.get('project') for row in tasks.values() if row.get('project')}:
   read_context.setdefault(('core-work',str(_root(root)),project),
       {'tasks':tasks,'digests':digests,'required':set()})
 # Close dispatch selection from this same work snapshot before any proof read.
 for project in {row.get('project') for row in tasks.values() if row.get('project')}:
  key=('dispatch-work-scope',str(_root(root)),project)
  requested={row['id'] for row in tasks.values() if row.get('project')==project and row.get('task_kind')=='dispatch'}
  read_context[key]=frozenset(set(read_context.get(key,()))|requested)
 visiting=set();cycles=set()
 for start in tasks:
  if start in memo:continue
  stack=[(start,False)]
  while stack:
   ident,closing=stack.pop()
   if ident in memo:continue
   task=tasks.get(ident)
   if task is None:continue
   if not closing:
    if ident in visiting:
     cycles.add(ident);continue
    visiting.add(ident);stack.append((ident,True))
    for dep in reversed(task.get('depends_on') or []):
     if dep in visiting:cycles.update((ident,dep))
     elif dep in tasks and dep not in memo:stack.append((dep,False))
    continue
   visiting.discard(ident)
   deps=list(task.get('depends_on') or [])
   blocked=[dep for dep in deps if memo.get(dep,{}).get('status') not in {'done','verified'}]
   raw_status=task.get('status','open')
   basis,containment_issue=_work_basis(tasks,ident,cache=bases)
   consumes_completion=completion_ids is None or ident in completion_ids
   currentness=(_evidence_currentness(task,root,digests=digests,tasks=tasks,bases=bases,read_context=read_context,core_only=core_only)
       if consumes_completion else {'status':'NOT_OBSERVED','kind':'CONTAINMENT_SCOPE_ONLY',
           'reason':'Containing goal contributes scope, not completion evidence consumption'})
   if currentness.get('kind')=='MANUSCRIPT_CONTRACT_INVALID':blocked.append('manuscript-contract')
   if consumes_completion and raw_status in {'done','verified'} and currentness['status']!='CURRENT':blocked.append('evidence')
   if ident in cycles:
    currentness={'status':'UNKNOWN','kind':'PREREQUISITE_CYCLE','reason':'Task prerequisite graph has a cycle'}
    blocked.append('cycle')
   if containment_issue:blocked.append('containment')
   if raw_status in {'cancelled','withdrawn','informational'}:status=raw_status
   elif blocked or raw_status=='blocked':status='blocked'
   elif raw_status in {'open','ready'}:status='ready'
   else:status=raw_status
   memo[ident]={**task,'id':ident,'status':status,'recorded_status':raw_status,
       'blocked_by':list(dict.fromkeys(blocked)),'evidence_currentness':currentness,'currentness':currentness,
       'work_revision':basis['revision'],'work_scope_revision':basis['scope_revision'],
       'dependency_revision':_dependency_revision(task,tasks,bases),'work_status_revision':_standing_revision(task),'completion_revision':_completion_identity(task,tasks,bases),'containment_issue':containment_issue}
   memo[ident].update(_read_facets(memo[ident]))
 from laplace.work import project_work_review
 for ident,row in memo.items():
  if review_facets and row.get('review_obligations'):row['review']=project_work_review.facet(row,_root(root),tasks=memo,digests=digests,read_context=read_context)
  # the development and delivery rows stay the ledger's own tuples here; their bounded facets are projected only by
  # the detail view (project_work_views), one Work at a time, never for every resolved row
 result=[memo[ident] for ident in tasks]
 if any("planning" in row for row in result):
  from laplace.work.backlog import preferred
  result=preferred(result)
 return result

def _work_artifact_context(root,project,read_context=None):
 """One actual source/path observation for this read; never a persistent cache."""
 root=_root(root);key=('work-artifact-context',str(root),project)
 if read_context is None:return artifacts.context(root,project)
 if key not in read_context:read_context[key]=artifacts.context(root,project)
 return read_context[key]


def _source_form(project,repo_root=None,*,source=None):
 """Compatibility for Work callers; the writing-style owner resolves inheritance."""
 from laplace.manuscript import writing_style
 value=writing_style.effective_genre(project,_root(repo_root),source=source,authored='')
 return value['effective'],{key:value[key] for key in ('origin','documentclass','source_revision')}

#: The two typed documents a child's own return artifact may be: an ordinary packet
#: return, or (for a judge packet) a judgement of another packet.  Read here, at the
#: SAME bytes `dispatch_view` already hashes for STALE/COMPLETE, to surface a verdict
#: with no second file read and no new stored field.

def _dispatch_schema_directory(root):
 from laplace.pipeline import workflow
 return workflow.packet_schema_directory(_root(root))


def _dispatch_pin_path(root,project,raw,*,artifact_only=False,context=None,repository=None):
 """One return pin's file. A pin may be repository-qualified ({repository, path}: the repository owner's coordinate,
 admitted exactly as repository.read admits it, writing_sources.qualified_file); an unqualified path is a project
 artifact, then manuscript source, then the one configured repository that owns it (the return contract's
 "absolute or repository-relative" input). An output (``artifact_only``) is always a project artifact."""
 from laplace.manuscript import manuscript_source
 if not isinstance(raw,str) or not raw.strip():raise ValueError("artifact path is empty")
 root=_root(root)
 if repository is not None:
  if artifact_only:raise ValueError("a repository-qualified pin cannot name a packet output; the output stays a project artifact")
  from laplace.projects import writing_sources
  return writing_sources.qualified_file(root,{"repository":repository,"path":raw})
 context=context if context is not None else artifacts.context(root,project)
 base=artifacts.project_root(root,project,context=context)
 path=Path(raw)
 if ".." in path.parts:raise ValueError("evidence path escapes its owner")
 if path.is_absolute():candidates=[path.resolve()]
 else:
  project_candidate,repository_candidate=(base/path).resolve(),(root/path).resolve()
  candidates=([repository_candidate,project_candidate] if repository_candidate.is_relative_to(base)
              else [project_candidate,repository_candidate])
 inside=[candidate for candidate in candidates if candidate.is_relative_to(base)]
 # an existing project artifact wins; a missing one is still the answer when no other owner holds the file
 for candidate in sorted(inside,key=lambda candidate:not candidate.exists()):
  if artifact_only:return artifacts.resolve_path(root,project,candidate.relative_to(base).as_posix(),context=context)
  if candidate.exists() or artifact_only:return candidate
 if not artifact_only:
  source=context["source"]
  manuscript=source.get("manuscript_dir")
  allowed=(root/str(manuscript)).resolve() if manuscript else None
  if allowed:
   for candidate in candidates:
    if candidate.is_relative_to(allowed):return candidate
  from laplace.projects import writing_sources
  try:target=writing_sources.target_for_path(root,raw)
  except ValueError:target=None
  if target is not None:return writing_sources.qualified_file(root,target)
  if inside:return inside[0]   # the project artifact that is missing: reported as missing, as before
 raise ValueError("evidence path is outside this project's artifact/source scope and no configured repository owns it")


def _dispatch_return_errors(document,item,packets,*,root,project,session_id=None,dispatch_id=None,turn_id=None,
                            _records_lookup=None,_artifact_context=None):
 """One shared versioned gate plus actual project/source completion standing."""
 from laplace.pipeline import workflow
 from laplace.core.identity import revision_matches
 role=item.get("role");family="laplace.packet-judgement/" if role=="judge" else "laplace.packet-return/"
 if not isinstance(document,dict) or not str(document.get("schema_version") or "").startswith(family):
  return ["return is not the declared role's typed document"]
 try:directory=_dispatch_schema_directory(root)
 except (OSError,ValueError):return ["canonical return schema registry is unavailable"]
 context=_artifact_context if _artifact_context is not None else _work_artifact_context(root,project)
 resolver=lambda raw,repository=None:_dispatch_pin_path(root,project,raw,context=context,repository=repository)
 output=document.get("output")
 output_value=output.get("path") if isinstance(output,dict) else output
 output_path=None;errors=[]
 complete=role in {"worker","parent"} and document.get("status")=="COMPLETE"
 if complete:
  try:
   output_path=_dispatch_pin_path(root,project,output_value,artifact_only=True,context=context)
   if not output_path.is_file():errors.append("output: claimed report artifact is missing")
   if item.get("output"):
    declared=item["output"].get("path") if isinstance(item["output"],dict) else item["output"]
    if output_path!=_dispatch_pin_path(root,project,declared,artifact_only=True,context=context):
     errors.append("output: claimed report differs from the packet's declared output")
  except (OSError,ValueError) as exc:errors.append("output: "+str(exc))
 base_read_verifier=workflow.packet_owner_read_verifier(root,_records_lookup=_records_lookup)
 def verify_read(observation,owner_document):
  try:
   records=(_records_lookup(observation.get('receipt_id')) if _records_lookup is not None
            else writing_records.fold_records(root))
  except (OSError,ValueError) as exc:return ['owner-read receipt unavailable: '+str(exc)]
  read=records.get("read_receipts",{}).get(observation.get("receipt_id")) or {}
  actor=records["turns"].get(read.get("turn_id")) or {}
  actor_session=records["sessions"].get(actor.get("session_id")) or {}
  if role=='parent':
   from laplace.writing.dispatch_parent import parent_actor
   if not parent_actor(item['parent_task'],records,actor.get('id')):
    return ['owner-read receipt is outside the original or explicitly recovered parent Work session']
  elif actor.get("project")!=project or actor.get("dispatch_id")!=dispatch_id:
   return ["owner-read receipt is outside this actual dispatch/project"]
  if str(owner_document.get("schema_version") or "").startswith("laplace.packet-judgement/"):
   if actor.get("session_id")!=session_id:return ["owner-read receipt is outside the actual judge session"]
   task=_tasks(project,root).get(dispatch_id) or {}
   if item.get('packet') in (task.get('dispatch_review_current') or {}) and actor.get('id')!=turn_id:
    return ['owner-read receipt is outside the selected judge attempt']
  elif role!='parent' and actor_session.get("packet")!=owner_document.get("packet"):
   return ["owner-read receipt is outside the actual worker packet"]
  return base_read_verifier(observation,owner_document)
 command_required=bool(item.get("requires_command_check")) or isinstance(item.get("check"),str) and bool(item["check"].strip())
 errors.extend(workflow.packet_return_problems(document,schema_directory=directory,
     expected_packet=item.get("packet") if role in {"worker","parent"} else None,
     allowed_roles={"synthesis"} if role=='parent' else {"build","continue"} if role=="worker" else None,
     requires_git_checkpoint=bool(item.get("requires_git_checkpoint")), resolve_pin=resolver,
     output_path=output_path,review_session_id=session_id if role=="judge" else None,
     requires_command_check=command_required,expected_check=item.get("check"),verify_owner_read=verify_read,
     require_current_inputs=True))
 if complete:
  check=document.get("scripted_check")
  if not isinstance(check,dict) or (check.get("kind","command")=="command" and check.get("exit_code")!=0):
   errors.append("return's scripted check failed")
  if isinstance(item.get("check"),str) and item["check"].strip() and check.get("command")!=item["check"]:
   errors.append("return's command differs from the declared check")
  for index,pin in enumerate(document.get("inputs") or []):
   if not isinstance(pin,dict):continue
   try:
    path=resolver(pin.get("path"),repository=pin.get("repository"))
    if not revision_matches(pin.get("sha256"),hashlib.sha256(path.read_bytes()).hexdigest()):
     errors.append("inputs/"+str(index)+": pinned readable input bytes changed")
   except (OSError,ValueError) as exc:errors.append("inputs/"+str(index)+": "+str(exc))
 if role=="judge":
  reviewed=packets.get(document.get("packet")) or {}
  if reviewed.get("role")!="worker":errors.append("judgement must identify a worker packet in this dispatch")
  elif document.get('packet') not in dispatch_dependencies(list(packets.values()),item.get('packet')):
   errors.append('judgement must identify a prior worker dependency of this judge')
  if document.get("accepted") is True and reviewed:
   try:
    returned=_dispatch_pin_path(root,project,reviewed.get("return_path"),artifact_only=True,context=context)
    target=document.get("judged") or {}
    declared_ref=target.get("return_artifact")
    if isinstance(declared_ref,dict) and returned!=resolver(declared_ref.get("path")):
     errors.append("judged return does not match the declared worker return path")
    builder=workflow._load(returned,workflow.MAX_RETURN)
    if builder.get("status")!="COMPLETE":errors.append("accepted judgement requires the current COMPLETE worker")
    errors.extend("judged worker: "+error for error in _dispatch_return_errors(
      builder,reviewed,packets,root=root,project=project,dispatch_id=dispatch_id,
      _records_lookup=_records_lookup,_artifact_context=context))
   except (OSError,ValueError,workflow.WorkflowRefused) as exc:errors.append("judged worker return unavailable: "+str(exc))
 return errors

def dispatch_plan_contract():
    """Executable app-plan shape shared by admission and current native help.

    The carrier still validates ordered review coverage and parent synthesis;
    this schema exposes the actual packet vocabulary rather than an opaque dict.
    """
    text = {'type': 'string', 'minLength': 1}
    packet_name = {'type': 'string', 'pattern': r'^[a-z0-9][a-z0-9-]{0,62}$'}
    packets_max = 8  # the plan's packets.maxItems below, named once; a judge's depends_on holds all but its own slot
    packet = {
        'type': 'object', 'required': ['packet', 'role', 'brief', 'return_path'],
        'additionalProperties': False,
        'properties': {
            'packet': packet_name,
            'role': {'enum': ['worker', 'judge']}, 'scope': {'const': 'project'},
            'brief': {'type': 'string', 'minLength': 1, 'maxLength': 100000},
            'return_path': text,
            'provider': {**text, 'description': 'Exact available provider id from session_settings.providers; omitted uses the parent provider.'},
            'model': {**text, 'description': 'Exact advertised model id from session_settings.providers, preserving any author-named child model; never invent a version alias. Omission uses the role tier.'},
            'effort': {**text, 'description': 'An effort advertised for the selected model; preserve the author-named value.'},
            'requires_git_checkpoint': {'type': 'boolean'},
            'requires_command_check': {'type': 'boolean'}, 'check': text,
            'output': {'oneOf': [text, {'type': 'object', 'required': ['path'],
                'properties': {'path': text}, 'additionalProperties': False}]},
            'depends_on': {'type': 'array', 'minItems': 1, 'maxItems': packets_max - 1, 'uniqueItems': True,
                'items': packet_name,
                'description': 'Judge only: the earlier worker packets this judge reviews. Omitted, a judge waits for every preceding worker.'},
        },
    }
    example = {
        'schema_version': 'laplace.dispatch-plan/1', 'fan_out_max': 2,
        'goal': 'Return a scoped report and independent judgement for the prepared Work.',
        'packets': [
            {'packet': 'develop', 'role': 'worker', 'scope': 'project',
             'return_path': 'development/develop-return.json',
             'brief': 'Read the exact prepared input artifact and current owner objects named by the parent. Write a scoped report artifact, then store the typed worker return using the injected return contract. Do not apply manuscript changes.'},
            {'packet': 'review', 'role': 'judge', 'scope': 'project',
             'return_path': 'development/review-return.json',
             'brief': 'Independently inspect the develop report and exact inputs after its typed return settles. Store the judgement for packet develop through the injected current review contract. Report concrete limitations; do not apply source changes.'},
        ],
    }
    return {
        'type': 'object', 'required': ['schema_version', 'fan_out_max', 'packets'],
        'additionalProperties': False,
        'properties': {
            'schema_version': {'const': 'laplace.dispatch-plan/1'},
            'fan_out_max': {'type': 'integer', 'minimum': 1, 'maximum': 8},
            'packets': {'type': 'array', 'minItems': 1, 'maxItems': packets_max, 'items': packet,
                'description': 'Ordered worker/judge packets. Every worker requires a later judge; a judge waits for the earlier workers its depends_on names, or for all preceding workers when it names none. Parent synthesis is automatic, not a synthesis child packet. A reviews field is unsupported.'},
            'deadline_seconds': {'type': 'integer', 'minimum': 1},
            'synthesis_return_path': {**text,'description':'Optional exact implicit parent-consumes laplace.packet-return/2 role:synthesis path. Required for connected observation; never a third child. Omission preserves legacy plan behavior.'},
            'wave': text, 'goal': text,
            'workflow_definition': {'type': 'object', 'description': 'Immutable owner-issued app workflow provenance; ordinary dispatch_plan cannot author it.'},
            'requires_git_checkpoint': {'type': 'boolean'},
            'requires_command_check': {'type': 'boolean'}, 'check_template': text,
        },
        'examples': [example],
    }

def dispatch_dependencies(packets,packet):
 """The carrier's ordered builder dependencies, shared by admission and reads.

 A judge's declared depends_on names the earlier workers it reviews; without it the
 judge waits for every preceding worker. A worker never declares dependencies."""
 prior=[]
 for item in packets:
  if not isinstance(item,dict):continue  # admission reports the malformed packet
  if item.get('packet')==packet:
   declared=item.get('depends_on')
   if declared is None:return prior if item.get('role')=='judge' else []
   if (item.get('role')!='judge' or not isinstance(declared,list) or not declared
       or len(set(declared))!=len(declared) or not set(declared)<=set(prior)):
    raise ValueError('A judge depends_on names only earlier worker packets, each once; a worker declares none.')
   return list(declared)
  if item.get('role')=='worker':prior.append(item['packet'])
 return []


def dispatch_dependency_state(task,project,packet,repo_root=None):
 """Readiness is settled validated evidence, never a file's mere existence."""
 view=dispatch_view(task,project,repo_root) or {}
 dependencies=view.get('dependencies',{}).get(packet,[])
 by_packet={row['packet']:row for row in view.get('children',[])}
 rows=[];waiting=False;blocked=False;failure_review=False
 for label in dependencies:
  child=by_packet.get(label) or {}
  active=(child.get('execution') or {}).get('state') in {'STARTING','WAITING','RUNNING'}
  settled=child.get('replied') and not active
  valid=bool(child.get('return_token')) and not child.get('return_errors') and child.get('state') not in {'STALE','INVALID-RETURN'}
  readable=settled and valid and child.get('reply_status') in {'completed','complete'} and bool(child.get('self_status')) and child.get('output_present')
  if readable:
   state='READY' if child['self_status']=='COMPLETE' else 'FAILURE-REVIEW'
   failure_review |= state=='FAILURE-REVIEW'
  elif active or not child:state='WAITING';waiting=True
  else:state='BLOCKED';blocked=True
  reason=('Worker has not settled its provider turn' if state=='WAITING' else
          '; '.join(child.get('return_errors') or []) or child.get('terminal_error') or child.get('state') or 'No settled readable worker return') if state in {'WAITING','BLOCKED'} else 'Settled validated '+str(child.get('self_status'))+' return'
  if state=='BLOCKED' and settled and valid and child.get('self_status') and not child.get('output_present'):
   reason='Settled worker retained no readable result output for the existing judgement contract'
  rows.append({'packet':label,'state':state,'reason':reason,'return_path':child.get('return_path'),
               'return_token':child.get('return_token'),'turn_id':child.get('turn_id'),
               'session_id':child.get('session_id'),
               'worker_status':child.get('self_status'),'errors':child.get('return_errors') or []})
 return {'state':'BLOCKED' if blocked else 'WAITING' if waiting else 'FAILURE-REVIEW' if failure_review else 'READY',
         'dependencies':rows}


def dispatch_attempts(task, records):
 """Select current packet turns from existing Work receipts; retain exact old turns."""
 from urllib.parse import urlencode
 grouped={}
 for turn in records['turns'].values():
  session=records['sessions'].get(turn.get('session_id')) or {}
  if turn.get('dispatch_id')==task['id'] and turn.get('project')==task['project']:
   grouped.setdefault(session.get('packet'),[]).append(turn)
 current=task.get('dispatch_review_current') or {};receipts=task.get('dispatch_review_continuations') or {}
 selected=[];pending=[];history={}
 for packet in set(grouped)|set(current):
  turns=grouped.get(packet,[]);receipt=receipts.get(current.get(packet)) if packet in current else None
  if packet in current:
   matches=[turn for turn in turns if receipt and turn['id']==receipt.get('planned_turn_id')
       and turn.get('request_id')==receipt.get('child_request_id') and turn.get('session_id')==receipt.get('session_id')
       and turn.get('parent_turn_id')==receipt.get('parent_turn_id')]
  else:matches=turns if len(turns)==1 else []
  chosen=matches[0] if len(matches)==1 else None
  if chosen:selected.append(chosen)
  elif packet in current or turns:
   pending.append({'packet':packet,'receipt':receipt,'reason':'No exact current attempt is observed' if receipt else 'Attempt selection is unavailable or ambiguous'})
  history[packet]=[{'session_id':turn['session_id'],'turn_id':turn['id'],
      'reply_status':(turn.get('reply') or {}).get('status'),
      'public_content_read':{'http':{'method':'GET','url':'/authoring/session-turn?'+urlencode({'project':task['project'],'id':turn['id'],'view':'turn'})},
          'native':{'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+turn['id']}}}}
      for turn in turns if chosen is None or turn['id']!=chosen['id']]
 return {'turns':selected,'pending':pending,'history':history}


def dispatch_view(task,project,repo_root=None,*,read_context=None,_include_parent=True):
 """The dispatch's own plan, packets, status, returns, verdicts and cost -- derived at
 read time from rows the app already banks, for the project-work pane.

 This is the ONE computation: `writing_tools.execute`'s `dispatch_status` operation
 (the model-facing reader) calls this same function, so a human pane and an agent's own
 tool read the identical truth and neither re-derives the other's arithmetic.

 Returns None for a task that is not a dispatch at all -- the one case this projection
 has nothing to say about.  A dispatch that is still 'open' (planned, not yet launched)
 returns normally with `children: []`: its plan file already exists (`dispatch_plan`
 writes it before the row is minted), and the empty loop below costs nothing extra."""
 if task.get("task_kind")!="dispatch":return None
 from laplace.writing import child_hosts
 root=_root(repo_root)
 # A packet's own `return_path` is PROJECT-relative (it is the path its own child
 # passes to its own `store_artifact`, scope project); the dispatch row's `evidence[0]`
 # (the PLAN) is REPO-relative (`writing_tools.py:687/708` returns `path.relative_to(root)`
 # for an artifact write). Two different bases for two different kinds of path, read
 # through the SAME resolver `dispatch_status` already uses, so this projection and that
 # tool agree on where a child's return actually lives.
 artifact_context=_work_artifact_context(root,project,read_context)
 project_dir=artifacts.project_root(root,project,context=artifact_context)
 plan_rel=str((task.get("evidence") or [""])[0] or "")
 plan_file=(root/plan_rel).resolve() if plan_rel else None
 if not plan_rel or not plan_file.is_file() or not plan_file.is_relative_to(root):
  return {"plan_artifact":plan_rel,"status":task.get("status"),"fan_out":0,"children":[],
          "verdicts":[],"cost":None,
          "note":"the dispatch's plan artifact is no longer at the path its row names"}
 try:plan=json.loads(plan_file.read_text(encoding="utf-8"))
 except (OSError,ValueError):
  return {"plan_artifact":plan_rel,"status":task.get("status"),"fan_out":0,"children":[],
          "verdicts":[],"cost":None,"execution_state":"FAILED","note":"dispatch plan is unreadable"}
 if not isinstance(plan,dict):
  return {"plan_artifact":plan_rel,"status":task.get("status"),"fan_out":0,"children":[],
          "verdicts":[],"cost":None,"execution_state":"FAILED","note":"dispatch plan is malformed"}
 records,lookup=writing_records.dispatch_records(root,project,task['id'],read_context=read_context)
 packets={str(item.get("packet")):{**item,"requires_git_checkpoint":item.get("requires_git_checkpoint",plan.get("requires_git_checkpoint",False)),
                                      "requires_command_check":item.get("requires_command_check",plan.get("requires_command_check",False)) or
                                          isinstance(plan.get("check_template"),str) and bool(plan["check_template"].strip())}
          for item in plan.get("packets") or []}
 receipts={row.get("path"):row.get("sha256") for row in task.get("evidence_receipts") or []
           if isinstance(row,dict)}
 children=[];verdicts=[]
 cost={"input_tokens":0,"output_tokens":0,"turns_replied":0,"turns_total":0}
 attempts=dispatch_attempts(task,records)
 for child in sorted(attempts['turns'],
                     key=lambda row:str(row.get("ts") or "")):
  session=records["sessions"].get(child.get("session_id")) or {}
  label=str(session.get("packet") or "")
  item=packets.get(label) or {}
  # This dispatch consumed this turn, not whichever conversation turn is newest.
  reply=child.get('reply') or None
  rel=str(item.get("return_path") or "")
  try:result=artifacts.resolve_path(root,project,rel,context=artifact_context) if rel else None
  except ValueError:result=None
  execution=child_hosts.child_execution(root,child["session_id"])
  if execution.get('turn_id')!=child['id']:
   # The sidecar is session-local and may now observe a later execution. Retain
   # exact saved turn standing; do not invent old process ownership or cleanup.
   execution={'state':'HISTORICAL' if reply else 'UNKNOWN','turn_id':child['id'],
              'observation':'saved-exact-turn-reply' if reply else 'exact-execution-unavailable',
              'result_status':(reply or {}).get('status'),'latest_session_turn_id':execution.get('turn_id')}
  document=None
  if result is None or not result.is_file():
   state_name=execution.get('state') if execution.get("state") in {"WAITING","BLOCKED"} else "RUNNING" if execution.get("state") in {"STARTING","RUNNING"} else "NO-RETURN"
   token=None
  else:
   content=result.read_bytes()
   token=hashlib.sha256(content).hexdigest()
   banked=receipts.get(str(result.relative_to(root)))
   state_name="STALE" if banked and banked!=token else "INVALID-RETURN"
   try:document=json.loads(content.decode("utf-8"))
   except (ValueError,UnicodeDecodeError):document=None
  return_errors=[]
  if token and state_name!="STALE":
   return_errors=_dispatch_return_errors(document,item,packets,root=root,project=project,session_id=child["session_id"],dispatch_id=task["id"],turn_id=child['id'],_records_lookup=lookup,_artifact_context=artifact_context)
   if not return_errors:
    standing=document.get("status") if isinstance(document,dict) else None
    state_name=(str(standing) if item.get("role")=="worker" and standing!="COMPLETE" else
                "COMPLETE" if reply else "RUNNING"
                if execution.get("state") in {"STARTING","RUNNING"} else "NO-REPLY")
  if execution.get('dependency_state')=='BLOCKED':state_name='BLOCKED'
  elif reply and reply.get("status") not in {"completed","complete"}:
   state_name="CANCELLED" if reply.get("status")=="interrupted" else "FAILED"
  elif execution.get("state") in {"FAILED","ORPHANED"}:state_name="FAILED"
  if task.get("dispatch_plan_sha256") and hashlib.sha256(plan_file.read_bytes()).hexdigest()!=task["dispatch_plan_sha256"]:
   state_name="STALE"
  verdict=None
  self_status=None
  if isinstance(document,dict):
   if str(document.get("schema_version") or "").startswith("laplace.packet-judgement/") and not return_errors and state_name=='COMPLETE':
    verdict={"packet":label,"judges":document.get("packet"),"accepted":document.get("accepted"),
             "round":document.get("round"),"max_rounds":document.get("max_rounds")}
    verdicts.append(verdict)
   elif str(document.get("schema_version") or "").startswith("laplace.packet-return/"):
    self_status=document.get("status")
  output_present=False
  if isinstance(document,dict) and document.get('output'):
   raw_output=document['output'].get('path') if isinstance(document['output'],dict) else document['output']
   try:output_present=_dispatch_pin_path(root,project,raw_output,artifact_only=True,context=artifact_context).is_file()
   except (OSError,ValueError):pass
  children.append({"packet":label,"session_id":child.get("session_id"),
                   "turn_id":child.get("id"),"parent_turn_id":child.get("parent_turn_id"),
                   "mode":child.get("mode"),"role":item.get("role"),
                   "return_path":rel,"return_exists":bool(token),"return_token":token,
                   "state":state_name,"self_status":self_status,"replied":bool(reply),"reply_status":(reply or {}).get('status'),
                   "terminal_error":(reply or {}).get('error'),"output_present":output_present,
                   "return_errors":return_errors,"execution":execution,
                   "remaining_work":document.get("remaining_work") if isinstance(document,dict) else None,
                   "continuation":document.get("continuation") if isinstance(document,dict) else None,
                   "provider_settings":child.get("provider_settings"),
                   "tier":session.get("tier"),"model_source":session.get("model_source"),
                   "verdict":verdict})
  children[-1]['review_exact']=bool(verdict and str((document or {}).get('schema_version') or '')=='laplace.packet-judgement/2'
                                  and isinstance(((document or {}).get('judged') or {}).get('return_artifact'),dict))
  from laplace.writing.dispatch_returns import child_diagnostics
  children[-1].update(child_diagnostics(root,project,children[-1]))
  if label in (task.get('dispatch_review_current') or {}):
   children[-1]['attempt_history']=attempts['history'].get(label,[])
   children[-1]['continuation']=(task.get('dispatch_review_continuations') or {}).get(task['dispatch_review_current'][label])
 for missing in attempts['pending']:
  receipt=missing['receipt'] or {};packet=missing['packet']
  children.append({'packet':packet,'session_id':receipt.get('session_id'),'turn_id':None,
      'role':packets.get(packet,{}).get('role'),'state':'NOT_STARTED' if receipt.get('phase')=='RESERVED' else 'UNKNOWN',
      'execution':{'state':'UNKNOWN','observation':'No exact current child turn is observed'},
      'binding':{'status':'UNAVAILABLE','reason':missing['reason']},'replied':False,'reply_status':None,
      'return_path':packets.get(packet,{}).get('return_path'),'return_exists':False,'return_token':None,
      'return_errors':[],'verdict':None,'continuation':receipt,'attempt_history':attempts['history'].get(packet,[])})
 # State selects one current attempt; paid/observed usage still includes retained attempts.
 for historical in records['turns'].values():
  if historical.get('dispatch_id')!=task['id'] or historical.get('project')!=project:continue
  cost['turns_total']+=1
  reply=historical.get('reply')
  if reply:
   cost['turns_replied']+=1;usage=reply.get('usage') or {}
   cost['input_tokens']+=int(usage.get('input') or usage.get('input_tokens') or 0)
   cost['output_tokens']+=int(usage.get('output') or usage.get('output_tokens') or 0)
 deadline=plan.get("deadline_seconds")
 exceeded=None
 if isinstance(deadline,int) and not isinstance(deadline,bool) and children:
  opened=[float((records["sessions"].get(row["session_id"]) or {}).get("created_at") or 0.0)
          for row in children]
  started=min([value for value in opened if value] or [0.0])
  exceeded=bool(started) and (dt.datetime.now(dt.timezone.utc).timestamp()-started)>deadline
 launched=task.get("dispatch_launch_state")
 continuing=bool(task.get('dispatch_review_current'))
 execution_state=("CANCELLED" if task.get("status")=="cancelled" else
                  "FAILED" if launched=="FAILED" and not continuing else
                  "STARTING" if launched=="STARTING" and child_hosts._process_matches(task.get("dispatch_launcher") or {}) else
                  "FAILED" if launched=="STARTING" else
                  "RUNNING" if any(row["state"]=="RUNNING" for row in children) else
                  "WAITING" if any(row["state"]=="WAITING" for row in children) else
                  "BLOCKED" if any(row["state"]=="BLOCKED" for row in children) else
                  "COMPLETE" if children and len(children)==len(packets) and all(row["state"]=="COMPLETE" for row in children) else
                  "FAILED" if launched else "PLANNED")
 if attempts['pending'] and task.get('status') not in {'cancelled','withdrawn'}:execution_state='UNKNOWN'
 workers=[label for label,item in packets.items() if item.get('role')=='worker']
 exact_reviewed={row['verdict']['judges'] for row in children if row.get('verdict') and row['verdict'].get('accepted') is True
                 and row.get('review_exact')}
 rejected={row['judges'] for row in verdicts if row.get('accepted') is False}
 accepted=exact_reviewed-rejected
 # Acceptance is per-worker validated current evidence, separate from terminal execution.
 uncovered=[label for label in workers if label not in accepted]
 legacy_acceptance=any(row.get('verdict') and row['verdict'].get('accepted') is True and not row.get('review_exact') for row in children)
 review_state='REJECTED' if rejected else 'ACCEPTED' if workers and not uncovered and execution_state=='COMPLETE' else 'UNVERIFIED' if legacy_acceptance and execution_state=='COMPLETE' else 'PENDING'
 result={"plan_artifact":plan_rel,"status":task.get("status"),"fan_out":len(children),
         "execution_state":execution_state,
         "dependencies":{label:dispatch_dependencies(plan.get('packets') or [],label) for label in packets},
         "review_state":review_state,"accepted_workers":sorted(accepted),"rejected_workers":sorted(rejected),"uncovered_workers":uncovered,
         "children":children,"verdicts":verdicts,"cost":cost,
         "deadline_seconds":deadline,"deadline_exceeded":exceeded}
 if _include_parent and task.get('dispatch_parent_observation'):
  from laplace.writing import dispatch_parent
  observed=dispatch_parent.recorded(root,project,task)
  if observed and observed.get('dispatch_id')==task['id']:
   result['parent_continuation']=dispatch_parent.public(root,project,observed,task=task,view=result)
 return result


def state(project,repo_root=None,*,lightweight=False,_tasks=None,_resolved=None,_read_context=None):
 from laplace.pipeline import authoring
 from laplace.manuscript import project_protocol
 from laplace.pipeline import projection_spec
 read_context={} if _read_context is None else _read_context
 tasks=globals()['_tasks'](project,repo_root) if _tasks is None else _tasks
 out=_resolved_tasks(tasks,repo_root,read_context=read_context) if _resolved is None else _resolved
 children={ident:[] for ident in tasks}
 for ident,row in tasks.items():
  if row.get('parent_work_id') in children:children[row['parent_work_id']].append(ident)
 for row in out:
  row['child_work_ids']=children[row['id']]
 # A launched dispatch's plan/packets/status/returns/verdicts/cost, read fresh for the
 # project-work pane (no poll: this runs once per explicit state load, same as every
 # other task field above).  Bounded to dispatch rows only -- the overwhelming majority
 # of tasks are not dispatches and pay nothing extra.
 for t in out:
  if t.get("task_kind")=="dispatch":
   t["dispatch"]=read_context.get(('dispatch-view',t['id'])) if ('dispatch-view',t['id']) in read_context else dispatch_view(t,project,repo_root,read_context=read_context)
 ready=[t for t in out if t["status"]=="ready"]
 # a deliberate full read hands out caller-owned phase rows (repair2 WR-R4-R1): the fold's tuple holds the shared
 # cache's own row dicts, which no public facade may expose; bounded summary/detail views never reach this copy
 for row in out:
  for key in _ATTACHED_KEYS:
   if isinstance(row.get(key),tuple):row[key]=[_deep(item) for item in row[key]]   # a facet dict already replaced the rows
 return {**project_envelope(project,repo_root,lightweight=lightweight,read_context=read_context),
         "tasks":out,"counts":read_counts(out),"ready":ready,"next":next((row for row in ready if not (row.get("planning") or {}).get("deferred")),None)}

def project_envelope(project,repo_root=None,*,lightweight=True,read_context=None):
 """The project facts a Work page carries once: framing, form, style and protocol.

 Delivered on the first summary page only (``project_work_views``); it never
 depends on the task fold, so continuation pages and graph/detail reads skip it.
 """
 from laplace.pipeline import authoring
 from laplace.manuscript import project_protocol
 from laplace.pipeline import projection_spec
 from laplace.manuscript import document_style
 read_context={} if read_context is None else read_context
 source=_work_artifact_context(repo_root,project,read_context)["source"]
 try: style=document_style.load(project,repo_root,_observed_source=source)
 except ValueError as error: style={'status':'UNAVAILABLE','reason':str(error),'effective_origin':'unavailable'}
 spec=projection_spec.load_spec(project,repo_root) or {};manuscript=spec.get("manuscript",{})
 authored=manuscript.get("genre") if isinstance(manuscript,dict) else None
 if isinstance(authored,str) and authored.strip():
  form=authored.strip();form_meta={"origin":"manuscript-spec","documentclass":None,"source_revision":None}
 else:
  form,form_meta=_source_form(project,repo_root,source=source)
 framing=(authoring.summary(project,repo_root,_source=source) if lightweight else authoring.load(project,repo_root))
 return {"project":project,"framing":framing,"form":form,
         "form_origin":form_meta["origin"],"form_source":form_meta,"style":style,
         "project_protocol":project_protocol.load(project,_root(repo_root),read_context=read_context)}

def summary(project,repo_root=None):
 """Keep the workspace envelope, omitting only authoring's historical bodies."""
 return state(project,repo_root,lightweight=True)

def read_contract():
 from laplace.work.project_work_views import contract
 return contract()

def read_snapshot(project,repo_root=None,*,read_context,resolve=True):
 """Private request-local read composition; no state survives its aggregate."""
 from laplace.work.project_work_views import read_snapshot as snapshot
 return snapshot(project,_root(repo_root),read_context=read_context,resolve=resolve)

def read(project,payload=None,repo_root=None,*,mode='human',read_context=None):
 from laplace.work.project_work_views import read as project_read
 return project_read(project,payload or {},_root(repo_root),mode=mode,read_context=read_context)
def framing(project,payload,repo_root=None):
 from laplace.pipeline import authoring
 current=authoring.load(project,repo_root)
 data={"base_revision":payload.get("base_revision",current["revision"]),"framing":{**current["framing"],**{k:payload[k] for k in ("purpose","audience","question") if k in payload}}}
 saved=authoring.save(project,data,repo_root)
 if "form" in payload:
  from laplace.pipeline import projection_spec
  path=projection_spec.spec_path(project,repo_root)
  if path:
   def update(spec):
    spec.setdefault("manuscript",{}).update({"genre":str(payload["form"]),"purpose":data["framing"]["purpose"],"target_reader":data["framing"]["audience"]})
    return spec
   projection_spec.update_file(path,update)
 return saved
def style(project,payload,repo_root=None):
 from laplace.manuscript import document_templates
 return document_templates.change(project,{key:value for key,value in payload.items() if key!='project'},_root(repo_root),actor={'kind':'human'})

def resolve_session_settings(provider_row,values,*,role='session',origin='named',strict=True):
 """ONE resolver for the app's model choice.

 role -> tier -> this provider's model (``schema.role_model``, the table at
 ``src/laplace/pipeline/schema.py`` ``TIERS``/``ROLE_TIER``), overridden by a model named on
 the turn or saved as the project's preference, and recorded with its SOURCE
 (``schema.MODEL_SOURCES``) and the tier the model belongs to (``schema.model_tier``, null
 for a model outside the table).  Both doors resolve here -- ``authoring_surface.new_session``
 through :func:`session_choice` with the passive catalogue, and
 :func:`validate_session_settings` with the live one -- so the default cannot be resolved two
 ways.  ``strict`` is the difference between them: the validating door refuses a model this
 installation does not advertise, the session-opening door records what its caller named
 (it never validated, and starting a conversation must not start a provider process)."""
 from laplace.writing import provider_catalogue as _passive   # the neutral owner: no provider service is imported to choose a model
 from laplace.pipeline import schema
 provider=str(values.get('provider') or provider_row.get('id') or '')
 token=str(values.get('model') or '')
 discovered=_passive.models_discovered(provider_row)
 if token:
  source='project-preference' if origin=='project-preference' else 'named'
  row=_passive.advertised_model(provider_row,token)
  if row is None and strict and discovered:raise ValueError('Choose an advertised model')
  model=row['id'] if row is not None else token
 else:
  default=schema.role_model(role,provider);source='tier-default'
  row=_passive.advertised_model(provider_row,default['model'])
  if row is None and strict and discovered:
   raise ValueError(f"{provider} does not advertise the {default['tier']} tier's model "
                    f"{default['model']!r}; refresh providers or name a model")
  model=row['id'] if row is not None else default['model']
 effort=values.get('effort') or schema.role_model(role,provider)['effort']
 if row is not None:
  # EFFORT TRUTH: a model that supports no effort is recorded as what was SENT -- no effort
  # flag (src/laplace/writing/provider.py `_claude`) -- not as the compatibility value
  # 'medium' this door used to write.  The live session row
  # WS-abc8cfa1d95c4828bc49aacbd93b81b8 in contract/talk.jsonl banks haiku with effort
  # 'medium' against a transport that sent nothing; the pane may still display Automatic.
  if row.get('supports_effort') is False:effort=None
  elif effort not in (row.get('efforts') or ()):raise ValueError('Choose a supported effort')
 elif effort not in ('low','medium','high','xhigh','max','ultra'):raise ValueError('Choose a supported effort')
 return {'provider':provider,'model':model,'effort':effort,'model_source':source,
         'tier':schema.model_tier(model,provider,(row or {}).get('resolved_model'))}

def validate_session_settings(payload, repo_root=None, *, role='session', origin='named'):
 """Validate a turn's settings against the LIVE catalogue and resolve what was left out."""
 from laplace.writing import provider as writing_provider
 values={key:payload.get(key) for key in ('provider','model','effort')}
 provider=next((p for p in writing_provider.capabilities(_root(repo_root),provider_id=values['provider'] or '')['providers'] if p['id']==values['provider'] and p['available']),None)
 if provider is None:raise ValueError('Provider is not available; refresh providers')
 return resolve_session_settings(provider,values,role=role,origin=origin)

def saved_preferences(project, repo_root=None):
 """The project's saved session preference, or {} -- the one store
 (``manuscript.session_preferences`` in the projection spec, written below)."""
 from laplace.pipeline import projection_spec
 try:spec=projection_spec.load_spec(project,_root(repo_root)) or {}
 except (ValueError,OSError,TypeError,AttributeError):return {}
 return ((spec.get('manuscript') or {}).get('session_preferences') or {}) if isinstance(spec,dict) else {}

#: The model-choice roles of a DISPATCHED child.  A child of these roles resolves at the role
#: table and NOWHERE else: see :func:`session_choice`.
DISPATCHED_ROLES=('worker','judge')

def session_choice(project, values, repo_root=None, role='session', *, include_provenance=False):
 """The settings a NEW in-app conversation starts with, resolved with no provider process
 started: a model named by the caller, else this project's saved preference, else the role's
 tier default.  The PASSIVE catalogue is the only one read here -- opening a view or starting
 a conversation must not start a provider process (``writing_provider.provider_catalogue``).

 A DISPATCHED CHILD IS THE ONE EXCEPTION, and it is the author's own model law: "the
 interfacing session runs at the highest tier; a dispatched worker never inherits it.  A
 model the user names for a task overrides this" (``STANDING_LAW.md`` model law).  The
 project's saved preference is a model named for the AUTHOR'S OWN CONVERSATIONS in this
 project, not for a dispatched task -- a packet names its child's model itself or names
 none (the dispatch CHOOSES either way) -- so a child of role ``worker`` or ``judge`` reads
 ``DISPATCHED_ROLES`` here and skips the preference entirely: its model is the packet's or
 ``schema.role_model``'s answer, ``model_source`` ``named`` or ``tier-default``.  Without this,
 a project whose author saved the apex as his preference would hand every dispatched worker
 the apex, which is the exact inheritance the law forbids."""
 from laplace.writing import provider_catalogue as _passive
 root=_root(repo_root);values=dict(values or {});authored=dict(values);origin='named';effort_origin='named-effort' if values.get('effort') else 'role-tier-default'
 if not values.get('model') and role not in DISPATCHED_ROLES:
  saved=saved_preferences(project,root)
  if saved.get('model') and saved.get('provider')==values.get('provider'):
   values['model']=saved['model'];origin='project-preference'
   if not values.get('effort'):
    values['effort']=saved.get('effort')
    if values.get('effort'):effort_origin='project-preference'
 catalogue=_passive.provider_catalogue(root)
 row=next((item for item in catalogue.get('providers') or [] if item.get('id')==values.get('provider')),
          {'id':values.get('provider'),'models':[]})
 result=resolve_session_settings(row,values,role=role,origin=origin,strict=False)
 if include_provenance:
  origins={'provider':'session-opening-provider','model':result['model_source'],'effort':'provider-capability-normalization' if result['effort'] is None else effort_origin}
  result['settings_provenance']={key:{'origin':origins[key],'value':result[key],'authored':authored.get(key),
    'resolved_input':values.get(key),'application_boundary':'future messages only',
    **({'normalization':'existing-provider-alias-or-effort-capability'} if values.get(key) not in (None,'') and values.get(key)!=result[key] else {})} for key in ('provider','model','effort')}
 return result

def session_preferences(project, payload=None, repo_root=None):
 from laplace.pipeline import projection_spec
 root=_root(repo_root);path=projection_spec.spec_path(project,root)
 if path is None:raise ValueError('Unknown project')
 if payload is not None:
  values=validate_session_settings(payload,root,origin='project-preference')
  def update(spec):
   manuscript=spec.setdefault('manuscript',{});previous=manuscript.get('session_preferences',{})
   if not isinstance(previous,dict):raise ValueError('Project preference custody is unsupported.')
   from laplace.writing.session_settings import _provenance
   manuscript['session_preferences']={**previous,**values,'settings_provenance':_provenance(previous,{key:payload[key] for key in ('provider','model','effort') if key in payload},values)}
   return spec
  projection_spec.update_file(path,update)
 from laplace.writing.session_settings import handle as settings_read
 return {'preferences':((projection_spec.load_spec(project,root) or {}).get('manuscript') or {}).get('session_preferences',{}),
         'settings_read':settings_read(project,{'action':'read','target':{'kind':'project-defaults'}})}
def _section_scopes(project,repo_root=None):
 try:
  from laplace.manuscript import project_structure
  structure=project_structure.state(project,repo_root)
  return {str(row.get("id")) for row in (structure.get("sections") or structure.get("source_outline") or []) if row.get("id")}
 except ValueError:
  from laplace.manuscript import manuscript_source
  source=manuscript_source.resolve(project,repo_root=_root(repo_root))
  if source.get("status")!="resolved" or not source.get("root"):return set()
  traversal=manuscript_source.traversal(source["root"],repo_root=_root(repo_root))
  return {Path(str(row.get("file") or "")).stem for row in traversal.get("sources",[]) if row.get("file")}

def _task_anchor(project, value, repo_root=None):
 if value in (None,{}): return {}
 if not isinstance(value,Mapping): raise ValueError("task anchor must be an object")
 allowed={"file","line_start","line_end","quote","section"}
 if set(value)-allowed: raise ValueError("task anchor contains unknown fields")
 anchor={key:value[key] for key in allowed if key in value and value[key] not in (None,"")}
 raw=anchor.get("file")
 if raw is not None:
  if not isinstance(raw,str) or not raw.strip(): raise ValueError("task anchor file must be a source path")
  path=Path(raw)
  if path.is_absolute() or ".." in path.parts: raise ValueError("task anchor file must stay inside the selected manuscript")
  from laplace.manuscript import manuscript_source
  root=_root(repo_root); source=manuscript_source.resolve(project,repo_root=root)
  md=(root/str(source.get("manuscript_dir") or "")).resolve()
  candidates=[(root/path).resolve(),(md/path).resolve()]
  target=next((item for item in candidates if item.is_file() and item.is_relative_to(md)),None)
  if target is None: raise ValueError("task anchor file is not in the selected manuscript")
  traversal=manuscript_source.traversal(source.get("root"),repo_root=root) if source.get("root") else {"sources":[]}
  selected={((root/str(row.get("file") or "")).resolve()) for row in traversal.get("sources",[]) if row.get("file")}
  if target not in selected: raise ValueError("task anchor file is not in the selected manuscript traversal")
  anchor["file"]=target.relative_to(md).as_posix()
  lines=target.read_text(encoding="utf-8",errors="replace").splitlines()
  for key in ("line_start","line_end"):
   if key in anchor and (not isinstance(anchor[key],int) or isinstance(anchor[key],bool) or anchor[key]<1 or anchor[key]>len(lines)):
    raise ValueError(f"task anchor {key} is outside its source file")
  if "line_start" in anchor and "line_end" in anchor and anchor["line_end"]<anchor["line_start"]:
   raise ValueError("task anchor line_end precedes line_start")
 elif "line_start" in anchor or "line_end" in anchor:
  raise ValueError("task anchor line bounds require a source file")
 if "quote" in anchor and (not isinstance(anchor["quote"],str) or len(anchor["quote"])>10_000):
  raise ValueError("task anchor quote must be bounded text")
 if "section" in anchor and (not isinstance(anchor["section"],str) or len(anchor["section"])>160):
  raise ValueError("task anchor section must be a bounded identifier")
 return anchor
def task(project,payload,repo_root=None,*,prepared_storyboard=None,prepared_workflow=None):
 if payload.get("action")=="planning":
  from laplace.work.backlog import change
  return change(project,payload,repo_root)
 with dispatch_lock(repo_root):
  return _task(project,payload,repo_root,prepared_storyboard=prepared_storyboard,prepared_workflow=prepared_workflow)
def _task(project,payload,repo_root=None,*,prepared_storyboard=None,prepared_workflow=None,followup_origin=None):
 # followup_origin is minted only by the review owner (project_work_review._followup), never read from a payload
 if 'followup_origin' in payload:raise ValueError('followup_origin is recorded by the review follow-up door, not authored.')
 ident=str(payload.get("id") or "WORK-"+uuid.uuid4().hex)
 rows=_tasks(project,repo_root); prior=rows.get(ident) or {}
 if prior and payload.get('expected_work_revision')!=_task_revision(prior):
  raise WorkConflict('Read the exact work specification before editing it.',project,ident,
      expected=payload.get('expected_work_revision'),observed=_task_revision(prior),field='expected_work_revision')
 title=str(payload.get("title",prior.get("title")) or "").strip()
 goal=str(payload.get("goal",prior.get("goal")) or "").strip()
 if not title or not goal: raise ValueError("task title and goal are required")
 deps=list(payload.get("depends_on",prior.get("depends_on") or []))
 if ident in deps or any(d not in rows for d in deps): raise ValueError("task dependencies must name existing tasks and cannot self-reference")
 def reaches(node,target):
  pending=[node];seen=set()
  while pending:
   cursor=pending.pop()
   if cursor==target:return True
   if cursor in seen:continue
   seen.add(cursor);pending.extend(rows.get(cursor,{}).get('depends_on') or [])
  return False
 if any(reaches(d,ident) for d in deps): raise ValueError("task dependency cycle")
 parent=payload.get('parent_work_id',prior.get('parent_work_id'))
 if parent=='':parent=None
 if parent is not None and (not isinstance(parent,str) or parent not in rows):
  raise ValueError('parent_work_id must name existing work in this project')
 candidate={**prior,'id':ident,'parent_work_id':parent}
 _ancestors,issue=_work_ancestors({**rows,ident:candidate},ident)
 if issue:raise ValueError(issue)
 section_ids=list(payload.get("section_ids",prior.get("section_ids") or []))
 if any(not isinstance(section,str) or section not in _section_scopes(project,repo_root) for section in section_ids):raise ValueError("task section_ids must name canonical plan sections or selected-source scopes")
 anchor=_task_anchor(project,payload.get("anchor",prior.get("anchor")),repo_root)
 row={"record":"project-work","kind":"work-order","id":ident,"task_id":ident,"project":project,"ts":dt.datetime.now(dt.timezone.utc).isoformat(),"title":title,"goal":goal,"task_kind":payload.get("kind",prior.get("task_kind","execution")),"depends_on":deps,"section_ids":section_ids,"anchor":anchor,"evidence":payload.get("evidence",prior.get("evidence") or []),"status":prior.get("status","open"),"origin":payload.get("origin") or payload.get("by") or prior.get("origin") or "author"}
 row['parent_work_id']=parent
 if prior.get('dispatch_synthesis_reservation'):
  row['dispatch_synthesis_reservation']=prior['dispatch_synthesis_reservation']
 elif not prior and row['task_kind']=='dispatch' and row['evidence']:
  from laplace.writing.dispatch_parent import reservation
  try:reserved=reservation(row,_root(repo_root),project)
  except (ValueError,OSError,AttributeError):reserved=None
  if reserved:row['dispatch_synthesis_reservation']=reserved
 if prepared_storyboard is not None:row['prepared_storyboard']=prepared_storyboard
 elif prior.get('prepared_storyboard') is not None:row['prepared_storyboard']=prior['prepared_storyboard']
 if prepared_workflow is not None:row['prepared_workflow']=prepared_workflow
 elif prior.get('prepared_workflow') is not None:row['prepared_workflow']=prior['prepared_workflow']
 if payload.get('reader_basis') is not None:
  from laplace.manuscript.reader_plan import observe_basis
  supplied=payload['reader_basis']
  if observe_basis(project,_root(repo_root),supplied)!=supplied:
   raise ValueError('CHANGED_INPUT: reader subject or inputs changed; inspect before preparing review work.')
  if row['task_kind']!='reader-review':raise ValueError('reader_basis belongs to reader-review work.')
 for key in ("obligation_id","logical_target","reader_basis"):
  if payload.get(key) is not None:row[key]=payload[key]
  elif prior.get(key) is not None:row[key]=prior[key]
 from laplace.work import project_work_review
 if payload.get('review_obligations') is not None:row['review_obligations']=project_work_review.obligations(payload['review_obligations'])
 elif prior.get('review_obligations') is not None:row['review_obligations']=prior['review_obligations']
 if prior.get('followup_origin') is not None:row['followup_origin']=prior['followup_origin']
 elif followup_origin is not None:row['followup_origin']=followup_origin
 # Opt-in manuscript contracts reuse this guarded writer and ledger only.
 from laplace.writing import prepared_work
 if prepared_work._programme_opt_in(row) or 'manuscript_programme' in prior or 'manuscript_stage' in prior or 'manuscript_programme' in rows.get(parent,{}):
  from laplace.writing import prepared_work
  row=prepared_work.bind_work_contract(project,_root(repo_root),row,prior,rows,payload)
 result=_append(repo_root,row)
 basis,_=_work_basis({**rows,ident:row},ident)
 from laplace.work.project_work_views import handle
 return {**result,'read_handle':handle(project,{'view':'detail','id':ident}),'work_revision':basis['revision'],'work_scope_revision':basis['scope_revision'],
         'dependency_revision':_dependency_revision(row,{**rows,ident:row})}
DISPOSITION_ORDER=('open','ready','blocked','in-progress','done','withdrawn','cancelled','verified')

def disposition_policy(row,effective,repo_root=None,*,project,read_context=None,held_check=True):
 """THE disposition decision of one Work: which explicit standings the owner admits now and why the others are refused.

 One definition for execution and preparation (repair1 WI-R1): ``_transition`` raises the refusal of the requested
 status, and ``project_work_views._actions`` publishes ``statuses`` and ``refused`` on the ``task_status`` action, which
 the native ``project`` detail and the human disposition form both consume. ``row`` is the resolved Work, ``effective``
 the resolved rows by id; without them (``effective=None``, a dispatch-parent continuation built inside the dispatch view)
 only the checks that need no resolution apply and ``scope`` says so. Literature-acquisition coverage is read once at
 execution, never per preview, and stays in ``_transition``.
 """
 refused={'verified':'verified requires a canonical independent task-verification receipt; no such receipt door is currently available'}
 kind=row.get('task_kind');recorded=row.get('recorded_status',row.get('status'))
 if kind not in {'session-request','dispatch'}:refused['cancelled']='only session-request and dispatch tasks can be cancelled'
 from laplace.writing import prepared_work
 done=prepared_work._contract_problem(row)
 if not done and held_check and recorded in {'blocked','withdrawn','cancelled'}:
  done='Held work requires an explicit ready/resume disposition before completion.'
 elif not done and effective is not None:
  if row.get('review_obligations'):
   from laplace.work import project_work_review
   done=project_work_review.completion_problem(row,_root(repo_root),effective)
  if not done and kind=='dispatch':
   cache=read_context if read_context is not None else {};key=('dispatch-view',row['id'])
   if key not in cache:cache[key]=dispatch_view(row,project,repo_root,read_context=cache)
   dispatch=cache[key] or {}
   if dispatch.get('execution_state')!='COMPLETE':done="Dispatch completion requires every child's successful typed return."
   elif dispatch.get('review_state')!='ACCEPTED':
    done='Dispatch completion requires accepted current per-worker review coverage; rejected or uncovered workers remain unresolved.'
  if not done and row.get('prepared_storyboard'):
   executions={other['id'] for other in effective.values()
       if other.get('parent_work_id')==row['id'] and other.get('task_kind')=='dispatch'
       and other.get('recorded_status',other.get('status')) not in {'withdrawn','cancelled'}}
   if not executions or not executions.issubset(set(row.get('depends_on') or [])):
    done='Prepared storyboard Work completes through its actual contained dispatch prerequisites; inspect/join execution before completion.'
  if not done and any(effective.get(d,{}).get('status') not in {'done','verified'} for d in row.get('depends_on') or []):
   done='blocked task cannot complete'
 if not done and row.get('completion_support'):
  from laplace.work import project_work_evidence
  try:
   checked=project_work_evidence.prepare_completion_support(_root(repo_root),project,row,row['completion_support']['reference'])
   if read_context is not None:read_context[('completion-support',row['id'])]=checked
  except (ValueError,OSError,KeyError) as error:done='Inspect or replace declared required evidence before completion: '+str(error)
 if not done and effective is not None:
  for dependency in row.get('depends_on') or ():
   prior=effective.get(dependency,{})
   if prior.get('completion_support'):
    from laplace.work import project_work_evidence
    try:project_work_evidence.prepare_completion_support(_root(repo_root),project,prior,prior['completion_support']['reference'])
    except (ValueError,OSError,KeyError) as error:
     done='Required evidence of prerequisite '+dependency+' is unavailable: '+str(error);break
 if not done and 'manuscript_stage' in row:
  from laplace.writing import prepared_work
  observed=prepared_work.stage_currentness(row,effective or {},_root(repo_root),read_context=read_context,require_qualified=True)
  if not observed or observed['status']!='CURRENT':done='Manuscript stage consumed cut is unqualified: '+str((observed or {}).get('reason'))
 if not done and prepared_work._programme_opt_in(row):
  from laplace.writing import prepared_work
  try:done=prepared_work.programme_outcome_problem(row,effective or {},_root(repo_root))
  except (ValueError,OSError,KeyError) as error:done='Manuscript terminal observation unavailable: '+str(error)
 if done:refused['done']=done
 return {'statuses':[status for status in DISPOSITION_ORDER if status not in refused],'refused':refused,
         'scope':'resolved' if effective is not None else 'static: completion eligibility is decided by the exact Work detail'}

def transition(project,payload,repo_root=None,*,dispatch_receipt=None):
 with dispatch_lock(repo_root):
  return _transition(project,payload,repo_root,dispatch_receipt=dispatch_receipt)

def _transition(project,payload,repo_root=None,*,dispatch_receipt=None):
 ident=str(payload.get("id") or ""); status=str(payload.get("status") or "")
 tasks=_tasks(project,repo_root)
 if ident not in tasks or status not in STATUSES: raise ValueError("unknown task or status")
 basis,_=_work_basis(tasks,ident)
 if dispatch_receipt is None:
  if payload.get('expected_work_scope_revision')!=basis['scope_revision']:
   raise WorkConflict('Read the exact work scope before changing its standing.',project,ident,
       expected=payload.get('expected_work_scope_revision'),observed=basis['scope_revision'],field='expected_work_scope_revision')
  if payload.get('expected_work_status_revision')!=_standing_revision(tasks[ident]):
   raise WorkConflict('Recorded work standing changed or was not inspected; no disposition was recorded.',project,ident,
       expected=payload.get('expected_work_status_revision'),observed=_standing_revision(tasks[ident]),field='expected_work_status_revision')
  if status=='done' and tasks[ident].get('depends_on') and payload.get('expected_dependency_revision')!=_dependency_revision(tasks[ident],tasks):
   raise WorkConflict('Prerequisite acceptance changed or was not inspected; no completion was recorded.',project,ident,
       expected=payload.get('expected_dependency_revision'),observed=_dependency_revision(tasks[ident],tasks),field='expected_dependency_revision')
 # the one disposition decision (disposition_policy), also published as allowed_actions.task_status statuses/refused
 context={};effective={row["id"]:row for row in _resolved_tasks(tasks,repo_root,read_context=context)}
 if 'completion_support' in payload:
  if status!='done':raise ValueError('Declared completion support belongs only to an explicit Done request.')
  from laplace.work import project_work_evidence
  project_work_evidence._validate(project_work_evidence.artifact_reference_contract(),payload['completion_support'])
  effective[ident]['completion_support']={'reference':payload['completion_support']}
 refusal=disposition_policy(effective[ident],effective,repo_root,project=project,read_context=context,
                            held_check=dispatch_receipt is None)['refused'].get(status)
 if refusal:raise ValueError(refusal)
 dispatch=context.get(('dispatch-view',ident)) or {}
 evidence=payload.get("evidence") or []
 from laplace.writing import dispatch_parent
 evidence,synthesis_attached=dispatch_parent.transition_evidence(tasks[ident],tasks,status,evidence,project,_root(repo_root))
 if tasks[ident].get('task_kind')=='dispatch' and synthesis_attached:
  evidence=list(dict.fromkeys(list((tasks[ident].get('evidence') or [])[:1])+evidence))
 if tasks[ident].get('task_kind')=='dispatch' and status=='done':
  # Preserve the existing plan home as evidence[0] and pin every consumed return.
  evidence=list(dict.fromkeys([dispatch['plan_artifact']]+[
      str(artifacts.resolve_path(_root(repo_root),project,row['return_path']).relative_to(_root(repo_root)))
      for row in dispatch['children']]+evidence))
 literature_coverage=None
 if tasks[ident].get('task_kind')=='literature-acquisition' and status=='done':
  from laplace.research.literature_support import scope
  literature_coverage=scope(project,_root(repo_root),task_id=ident)
  if not literature_coverage['ready_for_completion']:
   raise ValueError('Literature acquisition is not complete: '+json.dumps(literature_coverage['gaps'][:12],ensure_ascii=False))
  evidence=list(dict.fromkeys(evidence+literature_coverage['completion_evidence']))
 session_request=tasks[ident].get("task_kind")=="session-request"
 summary=str(payload.get("summary",payload.get("outcome","") ) or "").strip()
 completed_in_turn=str(payload.get("completed_in_turn") or "").strip()
 if session_request and status=="done":
  if not summary: raise ValueError("completed session-request requires an outcome summary")
  if len(summary)>10_000: raise ValueError("session-request outcome summary is too large")
  if not completed_in_turn: raise ValueError("completed session-request must name the current writing turn")
  from laplace.writing import child_hosts
  turn=writing_records.fold_records(_root(repo_root))["turns"].get(completed_in_turn)
  if not turn or turn.get("project")!=project: raise ValueError("completed_in_turn is not a writing turn for this project")
  receipts=[]
 else:
  receipts=_evidence_receipts(repo_root,evidence) if status in {"done","verified"} or synthesis_attached else []
 row={"record":"project-work-transition","kind":"work-order","id":ident,"task_id":ident,"project":project,"ts":dt.datetime.now(dt.timezone.utc).isoformat(),"status":status,"supersedes":tasks[ident].get("id")}
 if status=='blocked':row['blocked_reason']=summary or (dispatch_receipt or {}).get('dispatch_launch_error') or 'Recorded hold has no explanation; inspect the exact task history.'
 elif dispatch_receipt is None:row['blocked_reason']=None
 if status=='withdrawn' and not summary:raise ValueError('Withdrawal requires an authored disposition summary; it is not accepted completion.')
 if summary:row['summary']=summary
 # EVIDENCE IS OMITTED WHEN THE CALLER NAMES NONE, because `_tasks` above merges a task row
 # and its transitions KEY BY KEY (project_work.py:20): a transition that banked
 # `"evidence": []` therefore ERASED the task row's own evidence from the merged view, and a
 # door that reads an artifact path off the row -- `authoring_surface.launch_dispatch` reads
 # the dispatch's plan from `evidence[0]` -- then had nothing to read.  Every reader of a
 # `project-work-transition` row reads it through that merge (the only other mention in the
 # tree is the effects list at src/laplace/writing_declared.py:245), so an absent key is the
 # row saying nothing about evidence rather than saying there is none.
 if dispatch_receipt:row.update(dispatch_receipt)
 if evidence:row["evidence"]=evidence
 if receipts:row["evidence_receipts"]=receipts
 if status=='done' and effective[ident].get('completion_support'):
  checked=context.get(('completion-support',ident))
  if checked is None:raise ValueError('Declared support was not verified by the completion owner.')
  row['completion_support']=checked
 if status in {'done','verified'} and not session_request:
  basis,issue=_work_basis(tasks,ident)
  if issue:raise ValueError(issue)
  row['completion_work_basis']=basis
  row['completion_dependency_basis']=_dependency_basis(tasks[ident],tasks)
 if literature_coverage:
  row['literature_scope_revision']=literature_coverage['revision']
  row['literature_coverage']={'claims':literature_coverage['pagination']['total'],'source_revision':literature_coverage['source_revision'],'bibliography':literature_coverage['bibliography'],'qualification':'source/placement/citation coverage observed; scientific alignment remains authored'}
 if session_request and status=="done": row.update(summary=summary,completed_in_turn=completed_in_turn)
 result=_append(repo_root,row)
 if tasks[ident].get("task_kind")=="dispatch" and status=="cancelled":
  from laplace.writing import child_hosts
  for child in child_hosts.active_child_hosts(_root(repo_root)):
   if child.get("dispatch_id")==ident and child.get("project")==project and (child.get("state")=="ORPHANED" or not child.get("provider_inference_started")):
    child_hosts.terminate_child_processes(child)
 return result
def conflict_details(error):
 """Preserve an exact Work admission refusal through transport wrappers."""
 for _ in range(8):
  if isinstance(error,WorkConflict):return dict(error.details)
  if error is None:break
  error=error.__cause__ or error.__context__
 return {}

def context(project,task_id,repo_root=None,*,expected_work_scope_revision=None,
            expected_dependency_revision=None,require_observation=False):
 if not isinstance(task_id,str) or not task_id.strip():raise ValueError('work_id must be a nonempty exact Work identity.')
 tasks=_tasks(project,repo_root)
 raw=tasks.get(task_id)
 if raw is None:raise WorkConflict('The selected Work is unavailable; inspect this project before attaching it.',project,task_id)
 basis,issue=_work_basis(tasks,task_id)
 if require_observation:
  # A legacy work_id alone is a saved association, not evidence that the author
  # inspected today's goal or prerequisite acceptance. Keep old receipts intact;
  # require an explicit current observation only for a new authored delivery.
  for field,expected,observed in (
      ('expected_work_scope_revision',expected_work_scope_revision,basis['scope_revision']),
      ('expected_dependency_revision',expected_dependency_revision,_dependency_revision(raw,tasks))):
   if issue or expected is None or expected!=observed:
    raise WorkConflict('Inspect the exact Work and explicitly use its current scope before sending. The message and target were not submitted.',
        project,task_id,expected=expected,observed=observed,field=field)
 task={row["id"]:row for row in _resolved_tasks(tasks,repo_root)}.get(task_id)
 if not task: raise ValueError("unknown task")
 from laplace.writing import prepared_work
 problem=prepared_work._contract_problem(raw)
 if problem:raise WorkConflict(problem,project,task_id,field='manuscript_contract')
 if 'manuscript_stage' in task:
  observed=prepared_work.stage_currentness(raw,tasks,_root(repo_root))
  effective={row["id"]:row for row in _resolved_tasks(tasks,repo_root)}
  if not observed or observed['status']!='CURRENT' or any(not effective.get(dep,{}).get('readiness',{}).get('satisfies_prerequisites') for dep in raw.get('depends_on') or []):
   raise WorkConflict('Manuscript stage inputs or prerequisite acceptance are unqualified; inspect and explicitly reprepare before admission.',project,task_id,field='manuscript_stage')
 ancestors,issue=_work_ancestors(tasks,task_id)
 basis,_=_work_basis(tasks,task_id)
 parent_context='\n'.join(f"{row['id']}: {row['title']}. Goal: {row['goal']}." for row in ancestors)
 prefix=('Containing work, from project campaign to immediate parent (not prerequisites):\n'+parent_context+'\n\n') if ancestors else ''
 if issue:prefix+='Containment unavailable: '+issue+'\n'
 if task.get('prepared_storyboard'):
  prefix+='Prepared storyboard artifact (read its exact owner handle before execution): '+json.dumps(
      {'operation':'read_artifact','payload':{'id':task['prepared_storyboard']['artifact_id']},
       'expected_revision':task['prepared_storyboard']['revision']})+'\n'
 return {"work_id":task_id,"selection":task.get("section_ids") or [],"status":task.get("status"),
         **({'prepared_storyboard':task['prepared_storyboard']} if task.get('prepared_storyboard') else {}),
         "parent_work_id":task.get('parent_work_id'),"ancestors":ancestors,"containment_issue":issue,"work_basis":basis,
         "anchor":task.get("anchor") or {},"blocked_by":task.get("blocked_by") or [],"evidence_currentness":task.get("evidence_currentness"),
         "prompt":prefix+f"Continue project task {task_id}: {task.get('title','')}. Goal: {task.get('goal','')}. Kind: {task.get('task_kind','execution')}. Anchor: {task.get('anchor') or {}}. Effective status: {task.get('status')}. Blocked by: {task.get('blocked_by') or []}. Evidence: {task.get('evidence') or []}. Evidence currentness: {task.get('evidence_currentness')}."}
