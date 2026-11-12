"""Read projections of project_work and the existing workflow carrier; no stored state.

Ownership
  Every reader of Work (HTTP ``/work/state``, native ``project``) comes through
  ``read``. Truth stays in ``project_work``; this module chooses what one view
  delivers and how pages continue.

Views and their projections
  summary  the navigation list: ``tasks`` rows in the LIST projection (below),
           owner ``counts``, ``pagination``, ``read_cut``, ``registered`` and
           ``ready_total`` on every page; the project envelope (``framing``,
           ``form``, ``style``, ``project_protocol``, ``ready_ids``, ``next``)
           only on the first page: ``ready_ids`` names the first ``limit`` ready
           Work by id and ``next`` is the first of them as one LIST row, so no
           ready row is delivered twice. A continuation page (``offset`` > 0)
           carries ``continuation: true`` instead of the envelope. The native
           door adds ``review_read`` to every page.
  detail   one Work in the FULL projection with blockers, allowed actions,
           acceptance, parent, paged children/dependants (DETAIL_PAGE rows per
           page unless ``limit`` says otherwise; ``next_read`` continues under
           the same ``as_of`` cut) and evidence reads.
  graph    declared containment/prerequisite topology; ``nodes`` use the GRAPH
           projection (below), paged with the same cut as summary.
  queue    session requests in the FULL projection (authored text and anchor).
  roots    the navigator's first read: root Work (campaigns and unfiled Work) with grade, purpose,
           qualified standing and complete subtree rollups, paged (NAV_PAGE), plus the first
           attention page; see project_work_navigation.
  branch   one Work as a parent: its row, action/context descriptor, breadcrumbs and its directly
           contained Work in prerequisite-respecting authored order, paged, each with needs and
           the narrow parallel qualification.
  attention  every Work whose standing needs attention (including done with non-current
           acceptance), paged, each with a short containment path.
  group    ``group`` (required here, refused with any other view) names one qualified group; every Work in it at
           any depth, paged as attention is, with the attention envelope plus ``group``. The roots ``counts``
           carry ``groups``: every Work counted once by its group, non-zero groups only.
  observe  the observer token and change hint (no Work rows); see project_work_navigation.
  history  one Work's recorded specification rows (names and what changed), standing changes and review
           phases, paged under the read cut.
  discovery  owner discovery (work.owner_discovery) confined to the selected project: ``request`` is that owner's
           contract (facet describe | discover | inspect | resolve).
  continuity  one selected Work's goal, original standing facets, production, prepared completion readiness, review
           and delivery standing and one owner-issued next action (project_work_continuity); actual caller Scope first.
  namespaces / workflows / full as before.
  The detail view also carries ``standing``, ``activity`` (qualified observations), a ``requires``
  page (declared prerequisites with standing), ``action_context``, ``reference`` and ``observe_basis``.
  ``allowed_actions`` is computed once per read (``_actions``) and is the one carrier of each action's handle,
  guard, admitted statuses/refusals (project_work.disposition_policy) and review-phase preparation.

LIST projection (``_public(detail=False)``)
  identity (id, qualified_id, title, task_kind, origin, ts), structure
  (parent_work_id, depends_on, section_ids, child_count), standing (status,
  recorded_status, blocked_by, blocked_reason, containment_issue, compact
  lifecycle/readiness/current_acceptance facets, currentness status+kind) and
  ``read_handle``, the owner-read qualification of the detail. No revision pin
  rides at list altitude: every guarded action (message target, task edit,
  disposition) takes its pins from the FULL projection's allowed actions or
  task fields, which detail and queue deliver. Goal text, evidence paths,
  receipts, completion bases, revision identities, facet reasons and the
  duplicate ``evidence_currentness`` object live in the FULL projection only.
  Measured on the large real project the mean serialised LIST row is about
  1.26 KB (read_handle 285 B, qualified_id 68 B, facets about 220 B, identity,
  structure and standing the rest); the design amendment sets 1.3 KB as the
  line for this project. A row names how many Work it contains (child_count),
  never their ids: a parent of fifty carried a 1.5 KB id array (M5 D, Root
  measured 2500 B for that one row); the ids are the detail's paged children.

GRAPH projection (``_graph_node``)
  what a typed topology paints and its standing chip reads: id, title,
  task_kind, status, containment_issue and the compact lifecycle, readiness
  and current_acceptance facets (a cycle or containment problem is also a
  page ``diagnostics`` row; full currentness is the node's detail). Structure travels once, as the
  page's typed ``edges``; a node's exact read is the page's one ``node_read``
  route (the detail view of that id), not a handle copied onto every node.
  Fifty LIST nodes served 55 KB against the 30 KB graph budget (M5 D).

Ownership of returned objects
  Rows come from ``project_work._tasks`` as deep copies, so a page (HTTP or
  native) never aliases the owner's cache; mutating a returned list or dict
  cannot change a later read.

Blockers (detail)
  Each blocker names its ``subject`` with ``title`` and ``standing`` when the
  subject is Work in this namespace, a ``relation`` kind, an id-free
  ``sentence`` and ``next_actions`` each carrying a ``kind``
  (``inspect-prerequisite`` | ``read-basis`` | ``prepare``). Human and native
  readers print the same fields; neither derives a title from an id.

Currentness
  ``read_cut`` hashes the project's folded records plus every row's effective
  status and currentness; a continuation whose ``as_of`` no longer matches is
  refused with the exact next reads. The ledger fold itself comes from
  ``project_work``'s stat-identity cache, so a page costs O(rows) without
  reparsing the ledger file.
"""
from __future__ import annotations
from laplace.projects import artifacts
import collections
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlencode

from laplace.work import project_work as work


def contract():
    from laplace.work import project_work_navigation as nav
    from laplace.work.review_evidence import contract as evidence_contract
    from laplace.work.project_work_evidence import contract as provenance_contract
    from laplace.work.project_work_continuity import contract as continuity_contract
    from laplace.pipeline.workflow_definition_history import request_contract as history_contract, FACETS as history_facets
    from laplace.pipeline.workflow_operations import read_contract as operation_contract, FACETS as operation_facets
    return {'type':'object','properties':{
        'view':{'enum':['summary','detail','graph','full','namespaces','workflows','queue','review','roots','branch','attention','group','observe','history','discovery','workflow-definitions','sealed-text-reader','catalogue','planning','planning-request','review-evidence','provenance','continuity']},'request':{'type':'object'},
        'id':{'type':'string'},'parent_work_id':{'type':'string'},'namespace':{'type':'string'},
        'phase_id':{'type':'string'},'obligation_id':{'type':'string','minLength':1},'phase_revision':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'},
        'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':100},
        'q':{'type':'string','maxLength':300},'lifecycle':{'type':'string','maxLength':64},
        'currentness':{'type':'string','maxLength':64},'readiness':{'type':'string','maxLength':64},
        'planning_filter':{'enum':['deferred','not-deferred','planned','unplanned']},'lifecycle_group':{'enum':['unfinished']},'request_id':{'type':'string','minLength':8,'maxLength':96},
        'as_of':{'type':'string'},'run_id':{'type':'string'},'since':{'type':'string','maxLength':80},
        'group':{'enum':list(nav.GROUPS)}},'additionalProperties':False,
        'allOf':[{'if':{'properties':{'view':{'const':'group'}},'required':['view']},'then':{'required':['group']},
                  'else':{'not':{'required':['group']}}},
                 {'if':{'properties':{'view':{'const':'review-evidence'}},'required':['view']},
                  'then':{'properties':{'request':evidence_contract()},'required':['id']}},
                 {'if':{'properties':{'view':{'const':'provenance'}},'required':['view']},
                  'then':{'properties':{'request':provenance_contract()},'required':['id']}},
                 {'if':{'properties':{'view':{'const':'continuity'}},'required':['view']},
                  'then':{'properties':{'request':continuity_contract()},'required':['id']}},
                 {'if':{'properties':{'view':{'const':'workflow-definitions'},'request':{'properties':{'facet':{'enum':list(history_facets)}},'required':['facet']}},'required':['view','request']},
                  'then':{'properties':{'request':history_contract()}}},
                 {'if':{'properties':{'view':{'const':'workflow-definitions'},'request':{'properties':{'facet':{'enum':list(operation_facets)}},'required':['facet']}},'required':['view','request']},
                  'then':{'properties':{'request':operation_contract()}}}]}


def delivery_profile(payload):
    """The bounded delivery profile this owner declares (writing.delivery.PROFILE_OWNERS): the navigation pages (roots,
    branch, attention, group) are bounded to the retained page line; detail, history, full and the other views keep their
    declared contracts and are not bounded by the shared delivery."""
    from laplace.work import project_work_navigation as nav
    bounded=payload.get('view') in {'roots', 'branch', 'attention','group','review-evidence','provenance','continuity'} or \
        payload.get('view')=='review' and bool(payload.get('phase_id'))   # a phase read is a bounded header or exact pages
    if payload.get('view')=='workflow-definitions':
        from laplace.pipeline.workflow_definition_history import FACETS
        from laplace.pipeline.workflow_operations import FACETS as OPERATION_FACETS
        bounded=(payload.get('request') or {}).get('facet') in (*FACETS, *OPERATION_FACETS)
    return {'bound': nav.CAP, 'owner': 'project_work_navigation'} if bounded else None


def handle(project, payload):
    fields={**({'project':project} if project else {}),**payload}
    return {'operation':'project','payload':{**({'namespace':project} if project else {}),**payload},
            'http':{'method':'GET','url':'/work/state?'+urlencode({key:json.dumps(value,separators=(',',':'),ensure_ascii=False) if key=='request' and isinstance(value,dict) else value for key,value in fields.items()})}}


def _hash(value):
    return 'sha256:'+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def _snapshot(root):
    # The owner's stat-identity fold; read-only rows, never mutated here.
    return work._rows(root)


def read_snapshot(project,root,*,read_context,resolve=True):
    """One private detached task snapshot for one pure aggregate request.

    The supplied dict belongs to its caller request. It is never a permission
    carrier, returned as wire data, or passed into mutation/admission.
    """
    from laplace.work import project_work_navigation as nav
    if not isinstance(read_context,dict):raise TypeError('A pure read context is an internal dict.')
    root=work._root(root);key=('work-read-snapshot',str(root),project)
    if key not in read_context:
        raw=work._tasks(project,root)
        read_context[key]={'raw':raw,'ledger_revision':nav.records_revision(raw)}
        metrics=read_context.setdefault(('read-metrics',str(root)),{})
        metrics['task_snapshots']=metrics.get('task_snapshots',0)+1
    result=read_context[key]
    if resolve and 'resolved' not in result:
        resolved=work._resolved_tasks(result['raw'],root,read_context=read_context)
        result.update(resolved=resolved,by_id={row['id']:row for row in resolved})
        result['cut']=_hash({'project':project,'ledger':result['ledger_revision'],
            'proofs':[(row['id'],row['status'],row['currentness'],_review_standing(row)) for row in resolved]})
    return result


def _raw(rows,project):
    tasks={}
    for row in rows:
        if row.get('project')==project and row.get('record') in {'project-work','project-work-transition'}:
            ident=row.get('task_id') or row.get('id')
            if ident:tasks[ident]={**tasks.get(ident,{}),**row}
    return tasks


def _registered(root):
    path=root/'registry_projects.json'
    data=json.loads(path.read_bytes()) if path.exists() else {'projects':[]}
    return {row['name'] for row in data.get('projects') or [] if isinstance(row,dict) and isinstance(row.get('name'),str)}


LIST_KEYS=('id','title','task_kind','status','recorded_status','parent_work_id','depends_on','section_ids',
           'blocked_by','blocked_reason','containment_issue','origin','ts','obligation_id','planning','planning_revision')
FULL_KEYS=('reader_basis','prepared_storyboard','goal','anchor','work_revision','work_scope_revision','work_status_revision','dependency_revision','currentness','evidence_currentness',
           'logical_target','completion_support','evidence','evidence_receipts','completion_work_basis','completion_dependency_basis','completion_revision','summary',
           'followup_origin','review')   # review_obligations (with every declared input) is served by view:review; the in-harness join's
                                          # development/deliveries facets are projected by the detail branch alone (bounded, one Work)


def _public(row,project,*,detail=False):
    """LIST (navigation) or FULL (focused) projection of one resolved Work row; see module doc."""
    if detail:
        item={key:row.get(key) for key in LIST_KEYS+FULL_KEYS+('lifecycle','current_acceptance','readiness') if key in row}
    else:
        item={key:row.get(key) for key in LIST_KEYS if key in row}
        life=row.get('lifecycle') or {};ready=row.get('readiness') or {};acceptance=row.get('current_acceptance') or {};currency=row.get('currentness') or {}
        item['lifecycle']={key:life.get(key) for key in ('status','completed','closed') if key in life}
        item['readiness']={key:ready.get(key) for key in ('status','blocked_by') if key in ready}
        item['current_acceptance']={key:acceptance.get(key) for key in ('status','review_required','kind') if key in acceptance}
        item['currentness']={key:currency.get(key) for key in ('status','kind') if key in currency}
        if row.get('review'):   # review-managed Work only: counts, never bodies (legacy rows unchanged)
            review=row['review'];item['review']={'remaining':len(review['remaining']),'obligations':len(review['obligations']),
                'next':(review.get('next') or {}).get('kind'),'pending_joins':len(review['pending_joins'])}
    item['qualified_id']=project+'::'+str(row['id'])
    item['read_handle']=handle(project,{'view':'detail','id':row['id']})
    from laplace.work.review_evidence import handle as evidence_handle
    item['review_evidence_read']=evidence_handle(project,row['id'])
    if detail:
        # Focused Work issues its provenance and evidence-choice reads. A LIST row stays a bounded navigation row (the
        # owner's per-row budget): its read_handle reaches the detail carrying both, and task_status actions issue
        # evidence_choices_read. Repeating two detail handles on every LIST row broke that budget (1,619 > 1,300 B).
        from laplace.work.project_work_evidence import handle as provenance_handle
        item['provenance_read']=provenance_handle(project,row['id'])
        item['evidence_choices_read']=provenance_handle(project,row['id'],{'demand':'choices'})
    return item


def _standing(row):
    """Compact owner standing of a Work subject for a blocker; same facets as a LIST row."""
    life=row.get('lifecycle') or {};ready=row.get('readiness') or {};acceptance=row.get('current_acceptance') or {}
    return {'status':row.get('status'),'recorded_status':row.get('recorded_status'),
            'lifecycle':{key:life.get(key) for key in ('status','completed','closed') if key in life},
            'readiness':{key:ready.get(key) for key in ('status',) if key in ready},
            'current_acceptance':{key:acceptance.get(key) for key in ('status','review_required') if key in acceptance}}


def _declared(operation):
    from laplace.native import declarations as writing_declarations
    declaration=writing_declarations.DECLARATIONS.get(operation)
    return (list(declaration.effects),declaration.does) if declaration is not None else ([],'')


def _actions(row,project,mode,*,by_id=None,root=None,read_context=None):
    """THE allowed actions of one Work, computed once per read (repair1 WI-R1): the canonical handle and guard (payload),
    authority, the owner's disposition decision (project_work.disposition_policy: statuses and refused, also what
    _transition enforces), each review phase's preparation (project_work_review.preparation, from the one PHASE_SPEC),
    declared effects and recovery. Native readers, the human editor/recorder and action_context all consume this one
    object; nothing else decides which standing or phase is admissible or what a phase needs. ``by_id`` (the resolved
    rows of this read) makes completion eligibility exact; without it the policy says it is static."""
    from laplace.work import project_work_review
    own=handle(project,{'view':'detail','id':row['id']})
    change={'id':row['id'],'expected_work_revision':row['work_revision']}
    status={'id':row['id'],'expected_work_scope_revision':row['work_scope_revision'],
            'expected_dependency_revision':row['dependency_revision'],'expected_work_status_revision':row['work_status_revision']}
    policy=work.disposition_policy(row,by_id,root,project=project,read_context=read_context)
    def common(operation):
        effects,does=_declared(operation)
        return {'operation':operation,'project':project,'native_context':{'project':project,'requires_selected_namespace':True},
                'authority':{'native':'the admitted writing turn of this project; its role decides permitted','human':'the author at the HTTP door'},
                'effects':effects,'does':does,
                'recovery':{'refusal':'CHANGED_INPUT carries the exact next_reads; re-read, compare this basis, then act again.','reads':[own]}}
    actions={'task':{**common('task'),'permitted':True,'payload':change,'http':{'method':'POST','url':'/work/task'},
                    'requires':'Author changed fields using this exact specification guard; omitted fields retain their meaning.'},
            'task_status':{**common('task_status'),'permitted':mode!='review' and row.get('work_scope_revision') is not None,'payload':status,
                    'http':{'method':'POST','url':'/work/transition'},'statuses':[x for x in policy['statuses'] if x!='verified'],
                    'refused':policy['refused'],'policy_scope':policy['scope'],
                    'requires':'Choose explicit standing. Done requires current prerequisites and completion evidence; held work must be explicitly resumed.'}}
    from laplace.work import backlog
    actions['planning']=backlog.action(project,row,permitted=mode!='review')
    from laplace.work.review_setup import read_handle as setup_read
    actions['review_setup']={'permitted':True,**setup_read(project,{'action':'review-setup','work_id':row['id']})}
    from laplace.work.project_work_evidence import handle as evidence_choices
    actions['task_status']['evidence_choices_read']=evidence_choices(project,row['id'],{'demand':'choices'})
    if row.get('review_obligations'):
        # the one lifecycle write: handoff/review/synthesis/followup with this exact specification guard (project_work_review)
        phases=project_work_review.role_phases(mode)
        actions['work_review']={**common('work_review'),'permitted':True,
            'payload':{'id':row['id'],'expected_work_revision':row['work_revision']},'phases':phases,'http':{'method':'POST','url':'/work/review'},
            'preparation':project_work_review.preparation(row.get('review'),phases,row['work_revision']),
            'requires':'Name phase and a stable request_id. A handoff or self-assessment never satisfies an obligation; nothing is launched.'}
    return actions


def _clear_description(kind,clear):
    # Display guidance and the machine clearing condition travel from this owner
    # together; callers do not reconstruct it from status labels or project names.
    descriptions={
        'RECORDED_HOLD':'Inspect the hold, then explicitly choose Ready or In progress. Completion still requires the authored criterion and current evidence.',
        'CONTAINMENT_UNAVAILABLE':'Inspect the missing or cyclic parent, then edit this task with its exact specification guard to select a valid parent.',
        'WORK_SCOPE_CHANGED':'Inspect the changed task or containing goal, satisfy the current criterion, then explicitly record a new guarded completion.',
        'DEPENDENCY_BASIS_CHANGED':'Inspect the changed prerequisite acceptance, satisfy this task on that basis, then explicitly record a new guarded completion.',
        'DEPENDENCY_PROOF_MISSING':"Inspect the historical result and today's prerequisite proofs, then explicitly re-complete on the current guarded basis. The old acceptance remains unverified.",
        'LITERATURE_SCOPE_CHANGED':'Inspect the old and current scoped coverage. If the current scope is ready and satisfies the authored criterion, explicitly re-complete it on that basis.',
        'DISPATCH_REVIEW_COVERAGE_NOT_CURRENT':'Inspect exact child returns and independent review coverage. Completion requires successful typed returns and accepted current coverage for every worker.',
        'EVIDENCE_CHANGED':'Inspect the changed evidence and old receipt. Explicit completion requires the current evidence to satisfy the authored criterion and a new guarded receipt.',
        'EVIDENCE_MISSING':'Restore or deliberately replace the exact missing evidence, inspect it, then explicitly record a guarded completion.',
        'EVIDENCE_PROOF_MISSING':'Inspect the historical result and current evidence; explicit re-completion must retain valid exact digest receipts.',
        'EVIDENCE_PROOF_MALFORMED':'Inspect the historical result and current evidence; explicit re-completion must retain valid exact digest receipts.',
        'PREREQUISITE_CYCLE':'Inspect the exact prerequisite cycle, then edit dependencies with the current specification guard to remove it.'}
    if kind in {'PREREQUISITE_UNAVAILABLE','PREREQUISITE_NOT_COMPLETE'}:
        return 'Inspect prerequisite '+str(clear.get('work_id'))+', then satisfy its authored criterion and complete it on current evidence. Cancelled or withdrawn work does not satisfy it.'
    return descriptions.get(kind,'Inspect the named owner and satisfy the authored criterion before explicitly recording a guarded completion.')


def _blockers(row,by_id,project,mode,actions=None):
    """Why this Work waits, in owner words: subject title and standing, relation kind,
    an id-free sentence, the exact message, and next actions each carrying a kind."""
    result=[];actions=actions or _actions(row,project,mode)
    own=handle(project,{'view':'detail','id':row['id']})
    subject={'owner':'project_work','project':project,'id':row['id'],
             'qualified_id':project+'::'+row['id'],'revision':row['work_scope_revision'],
             'title':row.get('title'),'standing':_standing(row)}
    def add(kind,message,*,target=None,currency=None,reads=None,clear=None,next_actions=None,relation='completion-proof',sentence=None):
        currency=currency or {}
        clear=dict(clear or {});clear['description']=_clear_description(kind,clear)
        result.append({'kind':kind,'relation':relation,'message':message,'sentence':sentence or message,'subject':target or subject,
            'consumed_revision':currency.get('consumed_revision'),'observed_revision':currency.get('observed_revision'),
            'read_handles':reads or [own],'next_actions':next_actions or [],'clear_when':clear or {}})
    for ident in row.get('depends_on') or []:
        required=by_id.get(ident)
        if required and required['status'] in {'done','verified'}:continue
        target={'owner':'project_work','project':project,'id':ident,'qualified_id':project+'::'+ident,
                'revision':required.get('work_scope_revision') if required else None,
                'title':required.get('title') if required else None,'standing':_standing(required) if required else None}
        read=handle(project,{'view':'detail','id':ident})
        add('PREREQUISITE_UNAVAILABLE' if required is None else 'PREREQUISITE_NOT_COMPLETE',
            'Prerequisite '+ident+' is '+(required['status'] if required else 'unavailable')+'.',target=target,relation='prerequisite',
            sentence=('Waiting on '+str(required.get('title') or 'a prerequisite')+', which is '+str(required['status']).replace('-',' ')+'.') if required
                     else 'Waiting on a prerequisite that is not available in this namespace.',
            reads=[read] if required else [own],clear={'owner':'project_work','work_id':ident,'effective_status_in':['done','verified'],'requires_current_proof':True},
            next_actions=[{**read,'kind':'inspect-prerequisite','permitted':True,'purpose':'Inspect the exact prerequisite and its authored criterion'}] if required else [])
        consumed=next((r.get('completion_revision') for r in row.get('completion_dependency_basis') or [] if r.get('work_id')==ident),None)
        result[-1]['consumed_revision']=consumed
        result[-1]['observed_revision']=required.get('completion_revision') if required else None
        if required:result[-1]['prerequisite_currentness']=required.get('currentness')
    if row.get('recorded_status')=='blocked':
        reason=row.get('blocked_reason')
        add('RECORDED_HOLD',reason or 'Historical held work has no recorded explanation. Inspect its history before an explicit disposition.',relation='hold',
            sentence=('Held: '+reason) if reason else 'Held by its recorded standing without a recorded explanation.',
            clear={'owner':'project_work','predicate':'explicit_guarded_ready_or_resume_disposition'},
            next_actions=[{**actions['task_status'],'kind':'prepare','payload':{**actions['task_status']['payload'],'status':'ready'},
                           'purpose':'Prepare an explicit disposition after inspecting the hold'}])
    if row.get('containment_issue'):
        add('CONTAINMENT_UNAVAILABLE',row['containment_issue'],relation='containment',sentence='Its containing goal is unavailable or cyclic.',
            clear={'owner':'project_work','predicate':'valid_acyclic_parent_scope'},
            next_actions=[{**actions['task'],'kind':'prepare','purpose':'Correct an unavailable or cyclic parent using the exact work guard'}])
    combined=row.get('currentness') or {}
    for currency in combined.get('diagnoses') or [combined]:
        if currency.get('status') not in {'STALE','UNKNOWN'}:continue
        reads=[own]
        if currency.get('kind')=='LITERATURE_SCOPE_CHANGED':
            reads.insert(0,{'operation':'literature_scope','payload':{'task_id':row['id']},
                'http':{'method':'GET','url':'/projects/literature/scope?'+urlencode({'project':project,'task_id':row['id']})}})
        add(currency.get('kind') or 'COMPLETION_PROOF_NOT_CURRENT',currency.get('reason') or 'Completion proof is not current.',currency=currency,reads=reads,
            relation='completion-proof',
            clear={'owner':'project_work','predicate':'explicit_completion_on_inspected_current_basis','goal':row.get('goal'),
                   'scientific_verification':False},next_actions=[{**reads[0],'kind':'read-basis','permitted':True,'purpose':'Inspect consumed/current proof; do not silently refresh or reaccept'}])
        if 'done' in actions['task_status']['statuses']:
            result[-1]['next_actions'].append({**actions['task_status'],'kind':'prepare',
                'payload':{**actions['task_status']['payload'],'status':'done',**({'evidence':row['evidence']} if row.get('evidence') else {})},
                'purpose':'Prepare an explicit completion on the inspected current basis; satisfy the authored criterion and provide exact current evidence.'})
        if currency.get('kind')=='PREREQUISITE_CYCLE':
            result[-1]['clear_when'].update(predicate='acyclic_authored_prerequisites')
            result[-1]['next_actions'].append({**actions['task'],'kind':'prepare','purpose':'Prepare a guarded correction to the exact prerequisite cycle.'})
        if currency.get('kind')=='DEPENDENCY_PROOF_MISSING':
            result[-1].update(legacy=True,basis_status='UNPINNED_LEGACY',
                observed_revision_scope='Current prerequisites only; not a historical consumed pin')
            result[-1]['clear_when'].update(predicate='explicit_guarded_recompletion_with_current_prerequisite_pins',
                historical_consumed_basis='unavailable; never reconstructed from current prerequisites',
                historical_completion_record='preserved unchanged')
        if currency.get('path'):result[-1]['subject']={**subject,'owner':'completion-evidence','path':currency['path']}
        if currency.get('ready_for_completion') is not None:result[-1]['current_coverage_ready']=currency['ready_for_completion']
        if currency.get('legacy_diff_available') is False:result[-1]['historical_diff']='UNAVAILABLE: earlier receipt retained only a composite revision'
        for key in ('consumed_dependencies','observed_dependencies','review_state','uncovered_workers','gaps'):
            if key in currency:result[-1][key]=currency[key]
    return result


def _evidence_reads(row,project,root,*,read_context=None):
    result=[]
    receipts={r.get('path'):r.get('sha256') for r in row.get('evidence_receipts') or [] if isinstance(r,dict)}
    for path in row.get('evidence') or []:
        item={'owner':'completion-evidence','path':path,'consumed_revision':receipts.get(path)}
        try:
            context=work._work_artifact_context(root,project,read_context)
            base=artifacts.project_root(root,project,context=context)
            target=(root/path).resolve()
            if not target.is_relative_to(base):raise ValueError('Evidence is outside the registered project artifact owner scope.')
            relative=target.relative_to(base).as_posix()
            item['http']={'method':'GET','url':'/research/artifact?'+urlencode({'project':project,'scope':'project','path':relative,**({'expected_sha256':receipts[path]} if receipts.get(path) else {})})}
            item['owner_target']={'kind':'project-file','project':project,'scope':'project','path':relative,'expected_sha256':receipts.get(path)}
            item['available']=True
            try:
                if artifacts.resolve_path(root,project,relative,context=context)!=target:raise ValueError('Artifact identity differs.')
                item.update(operation='read_artifact',payload={'path':relative,'scope':'project'})
            except ValueError:
                item['native_capability_gap']='Use the evidence HTTP artifact reader or its canonical source owner; generic read_artifact does not cover this canonical file.'
        except ValueError:
            # This is a source observation, not a completion/currentness grant.
            # Repository ownership and material transport each remain with their owner.
            from laplace.projects import writing_sources, library as writing_projects
            try:
                target = writing_sources.target_for_path(root, path)
                item.update(writing_projects.material_read_handle(project, {
                    'view': 'preview', 'target': target, 'offset': 0, 'limit': 16000}))
                item.update(available=True,owner_target={'kind':'material-source','project':project,'target':target,'expected_sha256':receipts.get(path)})
            except (OSError, ValueError) as refusal:
                item.update(available=False,capability_gap=str(refusal),local_read={'path':path,'read_only':True})
        result.append(item)
    return result


DETAIL_PAGE=20   # default children/dependants page of one detail read (M5 D: never fifty eagerly)
LIST_PAGE=50
GRAPH_FACETS=(('lifecycle',('status','completed','closed')),('readiness',('status',)),
              ('current_acceptance',('status','review_required')))


def _graph_node(row):
    """GRAPH projection of one resolved Work row; see module doc."""
    node={key:row.get(key) for key in ('id','title','task_kind','status') if key in row}
    if row.get('containment_issue'):node['containment_issue']=row['containment_issue']
    for facet,keys in GRAPH_FACETS:
        value=row.get(facet) or {}
        node[facet]={key:value.get(key) for key in keys if key in value}
    return node


def _review_standing(row):
    review=row.get('review')
    if not review:return None
    return [review['remaining'],[(item['id'],item['status'],item['currentness']) for item in review['obligations']]]


PHASE_INLINE_BYTES=16000   # a phase read inlines its rows only within this escaped size; else header + body pages
PHASE_PAGE_CHARS=12000
PHASE_PAGE_JSON_BYTES=12000


def _phase_header(project,ident,row):
    """Bounded semantic header of ONE recorded phase row: what was recorded (phase, state, verdict, actor, independence,
    counts, coverage and the Source plan summary), never bodies. It is recorded standing, not current applicability."""
    head={key:value for key,value in _phase_summary(project,ident,row).items() if key!='read'}
    summary=row.get('summary') or ''
    head.update(summary=summary[:600],summary_truncated=len(summary)>600,finding_ids=[f.get('id') for f in (row.get('findings') or [])][:20])
    for key in ('request_id','consumes','obligations'):
        if row.get(key):head[key]=list(row[key])[:24] if isinstance(row[key],(list,tuple)) else row[key]
    if isinstance(row.get('source_basis'),dict):
        head['source_basis']={key:row['source_basis'].get(key) for key in ('grant_id','candidate_id','effect_id','repository','base') if key in row['source_basis']}
    if row.get('source_review_plan'):
        from laplace.work.project_work_review import source_plan_summary
        head['source_review_plan']=source_plan_summary(row['source_review_plan'])
    return head


def _phase_summary(project,ident,row,*,task=None,root=None,read_context=None):
    actor=row.get('actor') or {}
    return {'id':row.get('id'),'phase':row.get('phase'),'state':row.get('state'),'ts':row.get('ts'),
            **{key:row[key] for key in ('verdict','obligation_id','handoff_id','child_id','closure','independence') if row.get(key)},
            'actor':{key:actor[key] for key in ('actor','origin','verified') if key in actor},
            'findings':len(row.get('findings') or []),'pins':len(row.get('pins') or {}),'evidence':len(row.get('evidence') or []),
            'read':__import__('laplace.work.project_work_review',fromlist=['phase_read']).phase_read(task,root,row['id'],project=project,read_context=read_context) if task is not None else handle(project,{'view':'review','id':ident,'phase_id':row.get('id')})}


def _review_view(project,payload,raw,by_id,read_cut,cut,offset,limit,*,root=None,read_context=None):
    """THE EXACT REVIEW DOOR (repair1 WR-R4): one review-managed Work's phases, one obligation with every declared input
    and its history, or one phase's whole original rows (actor, basis, pins, evidence, findings, summary), under the
    same Work read cut. Native (project) and HTTP (/work/state) share it; nothing is copied unless delivered."""
    ident=payload.get('id');row=by_id.get(ident);spec=raw.get(ident) or {}
    if row is None or not spec.get('review_obligations'):raise ValueError('Exact review-managed work identity is unavailable in this namespace.')
    phases=spec.get('phases') or ()
    out={'project':project,'view':'review','work_id':ident,'read_cut':read_cut,
         'scope':'Exact recorded review lifecycle of one Work; deliberate reads, original bytes and identities.'}
    if payload.get('phase_id'):
        rows=[item for item in phases if item.get('id')==payload['phase_id']]
        if not rows:raise ValueError('This phase is not recorded on this Work.')
        revision=_hash(rows)
        if payload.get('phase_revision') and payload['phase_revision']!=revision:
            conflict=work.WorkConflict('This phase record changed since it was read.',project,ident,expected=payload['phase_revision'],observed=revision,field='phase_revision')
            current=handle(project,{'view':'review','id':ident,'phase_id':payload['phase_id'],'phase_revision':revision})
            conflict.details.update(kind='PHASE_CHANGED',current_read=current,next_reads=[current]);raise conflict
        full=[work._deep(item) for item in rows]
        header=[_phase_header(project,ident,item) for item in rows]
        if 'offset' not in payload and len(json.dumps(full).encode('utf-8'))<=PHASE_INLINE_BYTES:
            out['phase']={'id':payload['phase_id'],'revision':revision,'header':header,'rows':full,'rows_state':'EXPANDED'}
            return out
        # A large recorded phase (the 230 KB handoff case) is a bounded semantic header plus exact pages of its canonical
        # row JSON, pinned to this phase_revision. Stored rows are never rewritten or reserialized; NOT_EXPANDED is not empty.
        body=json.dumps(full,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        start=payload.get('offset',0)
        if start>len(body):
            raise ValueError('Phase body offset %d is beyond its %d characters; restart at offset 0 with the same phase_revision.' % (start,len(body)))
        end=min(len(body),start+PHASE_PAGE_CHARS)
        while end-start>1 and len(json.dumps(body[start:end]).encode('utf-8'))>PHASE_PAGE_JSON_BYTES:
            end=start+(end-start)*3//4
        page=lambda at:handle(project,{'view':'review','id':ident,'phase_id':payload['phase_id'],'phase_revision':revision,'offset':at})
        import hashlib
        out['phase']={'id':payload['phase_id'],'revision':revision,'header':header,'rows':None,'rows_state':'NOT_EXPANDED',
            'body':{'units':'Unicode characters of the canonical sorted-key compact JSON of the recorded rows','chars':len(body),
                    'sha256':'sha256:'+hashlib.sha256(body.encode('utf-8')).hexdigest(),'offset':start,'end_offset':end,
                    'content':body[start:end],'eof':end==len(body),'page_read':page(start),
                    'next_read':page(end) if end<len(body) else None,'restart_read':page(0),
                    'meaning':'Exact recorded rows in bounded transport pages; reassemble every page and parse it to recover them. '
                               'Recorded standing only: current applicability is the Work review facet decision.'}}
        return out
    if payload.get('obligation_id'):
        declared=next((item for item in spec['review_obligations'] if item.get('id')==payload['obligation_id']),None)
        if declared is None:raise ValueError('This obligation is not declared on this Work.')
        standing=next((item for item in (row.get('review') or {}).get('obligations') or [] if item['id']==declared['id']),{})
        out['obligation']={**work._deep(declared),'standing':{key:value for key,value in standing.items() if key!='read'}}
        history=[_phase_summary(project,ident,item,task=spec,root=root,read_context=read_context) for item in phases
                 if item.get('obligation_id')==declared['id'] or (item.get('phase')=='handoff' and declared['id'] in (item.get('obligations') or []))]
        out['history']=_page(history,offset,limit,project,payload,cut)
        return out
    out['phases']=_page([_phase_summary(project,ident,item,task=spec,root=root,read_context=read_context) for item in phases],offset,limit,project,payload,cut)
    return out


def _continuity_read(scope,project,ident):
    """The selected Work's issued continuity read (project_work_continuity.handle), only for the actual admitted caller
    Scope of this exact namespace. A missing, foreign or label-only caller gets no handle and no lookup authority."""
    from laplace.work.owner_discovery import Scope
    if not isinstance(scope,Scope) or not scope.admits(project):
        return None,'No actual admitted caller Scope for this namespace; no continuity read is issued.'
    from laplace.work.project_work_continuity import handle as continuity
    return {**continuity(project,ident,{'part':'summary'}),'scope':scope.public()},None


def _page(items,offset,limit,project,payload,cut):
    page=items[offset:offset+limit];next_offset=offset+len(page) if offset+len(page)<len(items) else None
    return {'items':page,'total':len(items),'offset':offset,'limit':limit,'next_offset':next_offset,
            'next_read':handle(project,{**payload,'offset':next_offset,'limit':limit,'as_of':cut}) if next_offset is not None else None}


def read(project,payload,root,*,mode='human',native_caller=None,read_context=None):
    from jsonschema import Draft202012Validator
    caller_project=project
    error=next(Draft202012Validator(contract()).iter_errors(payload),None)
    if error:raise ValueError('Work query does not match its owner contract: '+error.message)
    if payload.get('view') in {'workflow-definitions','sealed-text-reader'} and 'namespace' in payload:
        raise ValueError('Workflow definition scope comes from the bound project, never a namespace selector.')
    root=work._root(root);view=payload.get('view','summary');project=payload.get('namespace',project) if view!='catalogue' else '';payload={key:value for key,value in payload.items() if key!='namespace'} if view!='catalogue' else dict(payload);offset=payload.get('offset',0)
    from laplace.work import project_work_navigation as nav
    limit=payload.get('limit',DETAIL_PAGE if view in {'detail','history'} else nav.NAV_PAGE if view in {'roots','branch','attention','group'} else LIST_PAGE)
    if payload.get('since') is not None and view!='observe':raise ValueError('since belongs to the observe view.')
    if view=='workflows':return _workflows(root,payload)
    if view=='sealed-text-reader':
        from laplace.writing import sealed_reader
        if set(payload)-{'view','request'} or not project:raise ValueError('Reader reads require caller project and request only.')
        values=payload.get('request') or {}
        if values.get('project')!=project:raise ValueError('Reader request belongs to another project.')
        return sealed_reader.request(root,values)
    if view=='workflow-definitions':
        from laplace.pipeline import workflow_definitions
        from laplace.work import owner_discovery
        if set(payload)-{'view','request'} or not project:raise ValueError('Workflow definition reads require a selected project and request only.')
        return workflow_definitions.read(root,native_caller or owner_discovery.project_scope(project,'native'),payload.get('request') or {})
    if view=='discovery':
        # owner discovery (work.owner_discovery) confined to this project; ``request`` is that owner's own contract
        from laplace.work import owner_discovery
        if set(payload)-{'view','request'} or not project:raise ValueError('The discovery view takes only request, inside a selected project.')
        return owner_discovery.request(root,owner_discovery.project_scope(project,'http' if mode=='human' else 'native'),payload.get('request') or {},mode=mode)
    if view=='catalogue':
        from laplace.work.backlog import catalogue
        return catalogue(root,{**payload,**({'namespace':project} if project else {})},mode=mode,caller_project=caller_project)
    if view in {'planning','planning-request'} and mode!='human' and caller_project!=project:raise ValueError('Planning read is outside the actual native project scope.')
    if view=='planning':
        from laplace.work.backlog import inspect_planning
        if not project or not payload.get('id'):raise ValueError('Exact namespace/Work are required.')
        return inspect_planning(project,payload['id'],root,mode=mode)
    if view=='planning-request':
        from laplace.work.backlog import inspect_request
        if not project or not payload.get('id') or not payload.get('request_id'):raise ValueError('Exact namespace/Work/request are required.')
        return inspect_request(project,payload['id'],payload['request_id'],root,mode=mode,planning_permitted=mode=='human' or caller_project==project)
    if view=='provenance':
        from laplace.work import project_work_evidence
        if set(payload)-{'view','id','request'} or not project or not payload.get('id'):raise ValueError('Provenance needs exact namespace/Work/request only.')
        return project_work_evidence.read(root,native_caller,project,payload['id'],payload.get('request') or {})
    if view=='continuity':
        from laplace.work import project_work_continuity
        if set(payload)-{'view','id','request'} or not project or not payload.get('id'):raise ValueError('Continuity needs exact namespace/Work/request only.')
        return project_work_continuity.read(root,native_caller,project,payload['id'],payload.get('request') or {},mode=mode,read_context=read_context)
    if view=='review' and 'obligation_id' in payload and native_caller is not None:
        from laplace.work import owner_discovery
        if not isinstance(native_caller,owner_discovery.Scope) or not native_caller.admits(project):raise ValueError('Selected review evidence is outside the actual caller scope.')
    if view=='review-evidence' or view=='review' and 'phase_revision' in payload:
        from laplace.work import owner_discovery
        if not isinstance(native_caller,owner_discovery.Scope) or not native_caller.admits(project):raise ValueError('The guarded Work read requires its actual admitted caller scope.')
        if view=='review-evidence':
            from laplace.work import review_evidence
            if set(payload)-{'view','id','request'} or not project or not payload.get('id'):raise ValueError('Review evidence needs exact namespace/Work/request only.')
            return review_evidence.read(root,native_caller,project,payload['id'],payload.get('request') or {})
        if not payload.get('phase_id'):raise ValueError('A guarded phase read requires an exact phase identity.')
    rows=_snapshot(root)
    registered=_registered(root)
    if view=='namespaces':
        groups={}
        for row in rows:
            if row.get('record') in {'project-work','project-work-transition'} and row.get('project'):
                groups.setdefault(row['project'],{})[row.get('task_id') or row.get('id')]=row
        items=[{'id':name,'registered':name in registered,'work_count':len(group),
                'read_handle':handle(name,{'view':'summary'}),'registration_gap':None if name in registered else 'Existing work namespace has no registered project; no project was created or inferred.'} for name,group in sorted(groups.items())]
        ledger_revision=_hash(items)
        if payload.get('as_of') and payload['as_of']!=ledger_revision:
            refusal=work.WorkConflict('Work membership changed between pages.',project,'',expected=payload['as_of'],observed=ledger_revision)
            refusal.details['next_reads']=[handle('',{'view':'namespaces','limit':limit})]
            raise refusal
        return {'view':view,'scope':'workspace-work-membership','read_only':True,'read_cut':{'revision':ledger_revision,'scope':'Observed namespace membership and registration'},**_page(items,offset,limit,'',{'view':view},ledger_revision)}
    if not project:raise ValueError('Select an exact work namespace.')
    if view=='observe':
        # the observer token reads the owner fold and live activity only: no resolution, copies or rows
        return nav.observe(project,payload,root)
    # Deep copies from the owner: this read owns every nested list and dict it delivers.
    context={} if read_context is None else read_context
    snapshot=read_snapshot(project,root,read_context=context);raw=snapshot['raw'];resolved=snapshot['resolved']
    # A different project's append cannot change this project's consumed work
    # evidence or invalidate its page continuation. Hash the scoped owner fold.
    # phase bodies are identified by their row identities, never re-serialized for the cut (repair1 WR-R4)
    ledger_revision=snapshot['ledger_revision']
    by_id={row['id']:row for row in resolved};children=collections.defaultdict(list);dependants=collections.defaultdict(list)
    for row in resolved:
        if row.get('parent_work_id'):children[row['parent_work_id']].append(row['id'])
        for ident in row.get('depends_on') or []:dependants[ident].append(row['id'])
    # the review standing (remaining and each obligation's status/currentness) is part of what a page shows, so a
    # changed reviewed input moves the cut and refuses an old continuation (repair1 WR-R2)
    cut=snapshot['cut']
    if payload.get('as_of') and payload['as_of']!=cut:
        refusal=work.WorkConflict('Work evidence or membership changed; old pages were not mixed.',project,payload.get('id',''),expected=payload['as_of'],observed=cut)
        refusal.details['next_reads']=[handle(project,{key:value for key,value in payload.items() if key not in {'as_of','offset'}})]
        raise refusal
    read_cut={'revision':cut,'work_records_revision':ledger_revision,'currency_scope':'Existing selected-project work records, proof and prerequisite fold; files are observed, not an atomic OS snapshot.'}
    if view=='queue':
        # Filter the one work fold before paging. Queued requests retain their
        # authored text and passage locator without loading authoring history.
        queued=[row for row in resolved if row.get('task_kind')=='session-request']
        page=_page([_public(row,project,detail=True) for row in queued],offset,limit,project,payload,cut)
        for item in page['items']:item['allowed_actions']=_actions(by_id[item['id']],project,mode,by_id=by_id,root=root,read_context=context)
        return {'project':project,'view':view,'registered':project in registered,'read_cut':read_cut,
                'tasks':page.pop('items'),'pagination':page,
                'scope':'Existing session-request work only; full authored goal and exact passage anchor are preserved.'}
    if view=='review':
        return _review_view(project,payload,raw,by_id,read_cut,cut,offset,limit,root=root,read_context=context)
    if view in {'roots','branch','attention','group','detail','history'}:
        from laplace.work import project_work_activity
        index=nav.Index(resolved,children,dependants,project_work_activity.project_activity(project,root),
                        project=project,mode=mode,root=root,read_context=context,records=ledger_revision)
        if view=='roots':return nav.roots_view(index,project,payload,cut,read_cut,offset,limit)
        if view=='branch':return nav.branch_view(index,project,payload,cut,read_cut,offset,limit)
        if view=='history':return nav.history_view(index,project,payload,root,cut,read_cut,offset,limit)
        if view=='attention':
            envelope={'project':project,'view':'attention','read_cut':read_cut,'row_reads':nav.row_reads(project),
                      'scope':'Every Work whose qualified standing needs attention, including done Work whose acceptance is not current.'}
            return nav.attention_page(index,project,cut,offset,limit,wrap=lambda rows,page:{**envelope,'tasks':rows,'pagination':page})
        if view=='group':
            group=payload['group']
            envelope={'project':project,'view':'group','group':group,'read_cut':read_cut,'row_reads':nav.row_reads(project),
                      'scope':'Every Work whose qualified standing is in this group, at any depth of containment.'}
            return nav.group_page(index,project,cut,group,offset,limit,payload={'view':'group','group':group},
                                  wrap=lambda rows,page:{**envelope,'tasks':rows,'pagination':page})
    if view=='detail':
        ident=payload.get('id');row=by_id.get(ident)
        if row is None:raise ValueError('Exact work identity is unavailable in this namespace.')
        allowed=index.actions(ident)
        blocked=_blockers(row,by_id,project,mode,allowed);task=_public(row,project,detail=True)
        task['child_count']=len(children[ident])   # the ids are the paged `children` below
        task['standing']=index.standing(ident)
        activity=index.activity['by_work'].get(ident)
        task['activity']={**activity,'coverage':index.activity['coverage']} if activity else {'state':None,'observations':[],
            'qualification':'No in-app or attested external execution is observed for this Work.','coverage':index.activity['coverage']}
        if row.get('task_kind')=='dispatch':
            task['dispatch']=context.get(('dispatch-view',ident)) or work.dispatch_view(row,project,root,read_context=context)
        task['evidence_reads']=_evidence_reads(row,project,root,read_context=context)
        # the in-harness join's facets: bounded owner projections of the attached rows, computed for this one Work only
        if row.get('development'):
            from laplace.work import development_source
            task['development']=development_source.facet(row,root)
        if row.get('deliveries'):
            from laplace.work import work_delivery
            task['deliveries']=work_delivery.facet(row,root,read_context=context)
            from laplace.work import feedback_route
            task['feedback_routes']=feedback_route.status(root,project,{'work_id':row['id']},read_context=context)
        if row.get('prepared_storyboard'):
            from laplace.writing.prepared_work import observe, executions, run_action
            task['preparation']=observe(project,root,row['prepared_storyboard'])
            task['prepared_execution']=executions(project,root,row['id'])
            task['run_action']=run_action(project,task,task['preparation'],task['prepared_execution'])
        return {'project':project,'view':view,'registered':project in registered,'read_cut':read_cut,'task':task,
            'blockers':blocked,'allowed_actions':allowed,
            'acceptance':{'goal':row.get('goal'),'mechanical':['Current prerequisite standing','Exact consumed scope and completion evidence'],
                'scientific_verification':False,'parent_completion':'Containment alone is not a completion dependency; only authored prerequisites are enforced.'},
            'parent':_public(by_id[row['parent_work_id']],project) if row.get('parent_work_id') in by_id else None,
            'children':_page([nav.relation_row(index,x,project) for x in children[ident]],offset,limit,project,payload,cut),
            'dependants':_page([nav.relation_row(index,x,project) for x in dependants[ident]],offset,limit,project,payload,cut),
            # declared prerequisites with their standing; an unavailable one is named, never dropped
            'requires':_page([nav.relation_row(index,x,project) if x in by_id else {'id':x,'available':False,'qualified_id':project+'::'+x}
                              for x in dict.fromkeys(row.get('depends_on') or [])],offset,limit,project,payload,cut),
            'action_context':nav.action_context(index,ident,project,cut,allowed),
            'reference':nav.reference(index,ident,project,root),
            'observe_basis':index.observe_basis(selected=nav.records_revision({ident:raw[ident]})[7:19]),
            'read_handles':[handle(project,{'view':'detail','id':ident}),handle(project,{'view':'graph','parent_work_id':ident})],
            **dict(zip(('continuity_read','continuity_read_gap'),_continuity_read(native_caller,project,ident)))}
    if view=='graph':
        parent=payload.get('parent_work_id');scope=set(by_id)
        if parent:
            if parent not in by_id:raise ValueError('Campaign work identity is unavailable.')
            scope=set();pending=[parent]
            while pending:
                ident=pending.pop()
                if ident in scope:continue
                scope.add(ident);pending.extend(children[ident])
        ordered=[row for row in resolved if row['id'] in scope];page=ordered[offset:offset+limit];ids={row['id'] for row in page}
        edges=[];boundary=set()
        for row in page:
            if row.get('parent_work_id'):edges.append({'kind':'contains','source':row['parent_work_id'],'target':row['id']})
            edges.extend({'kind':'requires','source':row['id'],'target':dep} for dep in row.get('depends_on') or [])
            target=row.get('logical_target')
            if isinstance(target,dict) and target.get('node_id'):
                edges.append({'kind':'targets-logical-node','source':row['id'],'target':'logical::'+str(target['node_id']),
                              'owner':'conceptric','execution_prerequisite':False})
        for edge in edges:boundary.update(x for x in (edge['source'],edge['target']) if x not in ids)
        pagination=_page([_graph_node(row) for row in ordered],offset,limit,project,payload,cut)
        return {'project':project,'view':view,'read_cut':read_cut,'nodes':pagination.pop('items'),'edges':edges,
            'node_read':{'purpose':'Read one node exactly: the detail view of its id.','operation':'project',
                         'payload':{'namespace':project,'view':'detail'},'id_field':'id',
                         'http':{'method':'GET','url':'/work/state?'+urlencode({'project':project,'view':'detail'}),'id_param':'id'}},
            'boundaries':[{'id':x,'available':x in by_id,'read_handle':handle(project,{'view':'detail','id':x}) if x in by_id else None} for x in sorted(boundary)],
            'counts':{'nodes':len(ordered),'requires':sum(len(row.get('depends_on') or []) for row in ordered),'contains':sum(bool(row.get('parent_work_id')) for row in ordered)},
            'diagnostics':[{'id':row['id'],'issue':row.get('containment_issue') or row['currentness'].get('reason')} for row in ordered if row.get('containment_issue') or row['currentness'].get('kind')=='PREREQUISITE_CYCLE'],
            'pagination':pagination,'scope':'Declared task containment/prerequisites; no logical support or material edge was promoted to an execution prerequisite.'}
    if view=='full':return work.state(project,root)
    public=[_public(row,project) for row in resolved]
    for row in public:row['child_count']=len(children[row['id']])
    page=_page(public,offset,limit,project,payload,cut)
    counts=work.read_counts(resolved);ready_total=sum(row['status']=='ready' for row in resolved)
    if offset>0:
        # A continuation page carries rows, counts and the cut; the project envelope
        # (framing, form, style, protocol, ready, next) was delivered with page one and
        # is not repeated.
        return {'project':project,'view':'summary','registered':project in registered,'read_cut':read_cut,'continuation':True,
                'tasks':page.pop('items'),'pagination':page,'counts':counts,'ready_total':ready_total}
    # Page one carries the project envelope; the task fold is not re-annotated for it.
    envelope=work.project_envelope(project,root,read_context=context) if project in registered else {'project':project,'framing':{},'form':None,'style':{},'project_protocol':{},'registered':False,'registration_gap':'Existing work namespace has no registered project; no manuscript was inferred.'}
    envelope.update(view='summary',tasks=page.pop('items'),pagination=page,read_cut=read_cut,
        counts=counts,
        ready_ids=[row['id'] for row in resolved if row['status']=='ready'][:limit],
        ready_total=ready_total)
    # `next` is one LIST row (Home names and opens it); the rest of the ready set is ids only
    first=next((row for row in public if row['status']=='ready' and not (row.get('planning') or {}).get('deferred')),None)
    envelope['next']=first
    return envelope


def _workflows(root,payload):
    from laplace.pipeline import workflow
    ident=payload.get('run_id')
    if not ident:
        result=workflow.recent_workflows(root,limit=min(payload.get('limit',3),8))
        for item in result.get('workflows') or []:item['read_handle']=handle('',{'view':'workflows','run_id':item['run_id']})
        return {**result,'view':'workflows','scope':'Existing repository carrier; project membership is not inferred.','resume_permitted':False}
    if not re.fullmatch(r'WORKFLOW-\d{8}T\d{6}Z-[0-9a-f]{12}',ident):raise ValueError('Use an exact observed workflow identity.')
    directory=(root/'evidence'/'WORKFLOWS'/ident).resolve()
    if not directory.is_relative_to(root/'evidence'/'WORKFLOWS'):raise ValueError('Workflow is outside this declared root.')
    try:result=workflow.inspect_run(directory)
    except workflow.WorkflowRefused as error:
        result={'run_id':ident,'status':'REFUSED','accepted':False,'current_return_problems':[str(error)],
                'manifest':'PRESENT' if (directory/'run.json').is_file() else 'ABSENT',
                'acceptance_scope':'Existing carrier inspection refused; no current acceptance inferred.'}
    # Explicit detail verifies through the existing carrier; large returned reports
    # stay behind its exact artifact refs rather than riding an ordinary Work view.
    result={key:value for key,value in result.items() if key!='stages'}
    manifest=(directory/'run.json').is_file()
    return {**result,'view':'workflows','read_only':True,'resume_permitted':False,
            'activity':'UNKNOWN: recorded results do not identify a live process',
            'continuation':{'owner':'pipeline.workflow','execution':'existing external carrier only',
                'available':manifest,'gap':None if manifest else 'Legacy carrier has no engine manifest; a printed resume command is not an executable capability.'},
            'read_handle':handle('',payload)}
