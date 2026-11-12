"""PROPOSAL CURRENTNESS (S1 B3): is a saved candidate's consumed basis still the current one?

Immutable checks the application transaction (writing.source_application) runs inside its current leases,
on every attempt (a plan is never reusable authority):

  _proposal_validation_basis   the candidate's consumed reads, applications and source facts, each compared
                               with today's owner observation: CURRENT, STALE or UNKNOWN, with the exact
                               reason; a refusal is ProposalBasisRefused carrying proposal_refusal_details.
  read_currentness_observation / consumed_read_recovery
                               one consumed read's currentness, and the exact read that recovers it.
  _source_text_facts / _source_preimage_bytes / _owner_rewrite_receipt
                               the source-text facts an edit's preimage is checked against.

Never refreshes or re-mints a basis: original owner-issued values are compared, not replaced.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any
from laplace.writing import records as writing_records
from laplace.manuscript import source_effects
from laplace.writing import turn_jobs
from laplace.writing.records._fold import _proposal_digest, _proposal_effect_digest, _read_basis_digest
from pathlib import Path


def _owner_rewrite_receipt(result:dict) -> dict:
    """Keep the review owner's existing receipt projection, never its full record."""
    owner=result.get("receipt")
    if isinstance(owner,dict):return dict(owner)
    applied=result.get("applied") if isinstance(result.get("applied"),dict) else {}
    record=result.get("record") if isinstance(result.get("record"),dict) else {}
    receipt={"banked":bool(record.get("id") or result.get("ok") and applied),
        "pending":bool(result.get("pending")),
        "row_id":record.get("id"),"version_id":result.get("version_id"),
        "file":applied.get("file") or result.get("file"),"lines":applied.get("lines")}
    for key in ("error","reason","refused","source_effect"):
        if result.get(key) is not None:receipt[key]=result[key]
    return receipt


def _source_text_facts(raw:bytes) -> tuple[str,dict]:
    """Keep physical UTF-8 bytes distinct from universal-newline source text."""
    text=raw.decode('utf-8')
    canonical=text.replace('\r\n','\n').replace('\r','\n')
    runs=[]
    for match in re.finditer(r'\r\n|\r|\n',text):
        ending=match.group()
        if runs and runs[-1][0]==ending:runs[-1][1]+=1
        else:runs.append([ending,1])
    return canonical,{'schema_version':'laplace.source-text-bytes/1','encoding':'utf-8',
        'byte_sha256':'sha256:'+hashlib.sha256(raw).hexdigest(),
        'text_sha256':'sha256:'+hashlib.sha256(canonical.encode()).hexdigest(),
        'newline_runs':runs}


def _source_preimage_bytes(canonical:str,format:dict|None) -> bytes:
    """Restore a recorded per-ending layout; do not guess a global newline."""
    if format is None:return canonical.encode('utf-8')  # legacy LF-only proof
    if format.get('schema_version')!='laplace.source-text-bytes/1' or format.get('encoding')!='utf-8':
        raise ValueError('Unknown source byte format')
    runs=format.get('newline_runs')
    if not isinstance(runs,list):raise ValueError('Missing source newline layout')
    for run in runs:
        if (not isinstance(run,list) or len(run)!=2 or run[0] not in ('\n','\r\n','\r')
            or isinstance(run[1],bool) or not isinstance(run[1],int) or run[1]<1):
            raise ValueError('Invalid source newline layout')
    if sum(run[1] for run in runs)!=canonical.count('\n'):
        raise ValueError('Source newline layout does not match the inverse')
    endings=(ending for ending,count in runs for _ in range(count))
    return re.sub('\n',lambda _:next(endings),canonical).encode('utf-8')


class ProposalBasisRefused(ValueError):
    """Observed consumed-input refusal, carrying diagnostic reads, never authority."""
    def __init__(self,basis:dict):
        super().__init__(basis.get('reason') or 'The consumed proposal basis is not current.')
        self.details={'consumed_read_recovery':basis['consumed_read_recovery']} if basis.get('consumed_read_recovery') else {}


def proposal_refusal_details(error:BaseException)->dict:
    """Preserve the owner's observations through native/HTTP exception wrappers."""
    for _ in range(8):
        details=getattr(error,'details',None)
        if isinstance(details,dict) and isinstance(details.get('consumed_read_recovery'),dict):
            return {'consumed_read_recovery':details['consumed_read_recovery']}
        error=error.__cause__ or error.__context__
        if error is None:break
    return {}


def read_currentness_observation(read:dict,value,current_digest,state:str)->dict:
    """One changed-read observation: the digests, and WHERE the read moved when its receipt
    retained a basis index (2026-10-14). The replayed value is compared and dropped; nothing
    is adopted, renewed or rebased."""
    from laplace.writing import operations
    from laplace.writing import reads as read_contract
    operation=str(read.get('operation'))
    row={'read_id':read.get('id'),'operation':operation,'currentness':state,
        'consumed_output_sha256':read_contract.consumed_digest(read),'observed_output_sha256':current_digest,
        'comparison_schema':(read['consumption'].get('schema_version','unknown')
            if isinstance(read.get('consumption'),dict) else 'legacy-output'),
        'selector_basis':'raw owner diagnostics, not the semantic comparison guard'}
    changes=read_contract.basis_changes(read.get('basis_index'),
        read_contract.read_basis_index(operation,value) if value is not None else {}) if read.get('basis_index') else None
    if changes is not None:
        row['changed_selectors']=changes
        inspect=read_contract.bounded_inspect_reads(operation,read.get('payload') or {},changes)
        if inspect:row['inspect_reads']=inspect
    else:
        row['changed_selectors']=None
        row['selector_note']='no basis index was retained on this receipt (read banked before 2026-10-14 or by a path without one)'
    return row


def consumed_read_recovery(turn:dict,basis:dict,observations:list[dict],*,context_reasons=())->dict:
    """Bounded exact read descriptors from this check, referencing existing receipts.

    No owner read, journal write, baseline advancement or mutation token is made
    here. Oversized payloads lead to their retained exact record, not a wider read.
    """
    by_id={r.get('id'):r for r in (basis.get('tool_reads') or {}).values()}
    reported=[];next_reads=[];inspect_reads=[];budget=6000
    for observed in observations:
        ident=observed.get('read_id');read=by_id.get(ident) or {}
        detail={'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+str(ident)}}
        call={'operation':read.get('operation') or observed['operation'],
              'payload':{k:v for k,v in (read.get('payload') or {}).items() if k!='project'}}
        oversized=len(json.dumps(call,ensure_ascii=False,default=str))>1600
        if oversized:call=detail
        row={**observed,'read_detail':detail,'payload_omitted':oversized}
        size=len(json.dumps({'observation':row,'read':call},ensure_ascii=False,default=str))
        if len(reported)>=8 or size>budget:continue
        reported.append(row);budget-=size
        if call not in next_reads:next_reads.append(call)
        for read in observed.get('inspect_reads') or []:
            if read not in inspect_reads and read not in next_reads:inspect_reads.append(read)
    record=basis.get('record_id') or turn['id']
    from laplace.manuscript.proposal_navigation import handle
    page=handle(turn.get('project') or '',{'id':turn['id'],'record_id':record,'view':'changed-reads'}) if turn.get('project') and basis.get('record_id') else None
    return {'schema_version':'laplace.consumed-read-recovery/1','proposal_record_id':record,
        'observed_changed_read_count':len(observations),'changed_read_families':list(dict.fromkeys(r['operation'] for r in observations)),
        'changed_reads':reported,'next_reads':next_reads,'inspect_reads':inspect_reads[:8],'changed_reads_omitted':len(observations)-len(reported),
        'basis_detail':{'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+record}},
        'context_reasons':list(context_reasons),'changed_reads_page':page,
        'note':('Observations belong to this refusal check. changed_reads lists the first of them within this response\'s '
                'bound; changed_reads_omitted counts the rest, and changed_reads_page reads every changed consulted read '
                'in bounded pages. changed_selectors names where each moved and inspect_reads are bounded current reads '
                'to judge it. Only the exact consulted read in next_reads renews its witness; no read adopts, approves or '
                'rebases changed evidence.')}


# Bounds of one changed-read page. A page observes EVERY consulted read of the candidate (at most PAGE_CONSULTED_MAX,
# else the page is refused): that full observation is the page's observation cut. It returns at most `limit` rows of
# the cut's changed reads, within PAGE_BYTES of row UTF-8 and PAGE_RESPONSE_BYTES of whole-response UTF-8.
PAGE_BYTES, PAGE_RESPONSE_BYTES, PAGE_ROWS, PAGE_CONSULTED_MAX = 6000, 12000, 8, 2048
ROW_BYTES = 4000
CURSOR_SCHEMA = 'laplace.changed-read-cursor/2'


def _page_cut(turn, version, basis, reads, source, observed) -> str:
    """The observation cut a traversal is pinned to: the project, turn, candidate version, consumed basis, consulted
    read sequence, selected source revision AND what this observation saw for every consulted read (current digest,
    UNAVAILABLE or not-replayed). Any change to any consulted evidence gives another cut."""
    return 'sha256:'+hashlib.sha256(json.dumps({'project':turn.get('project'),'turn':turn['id'],'version':version,
        'record':basis.get('record_id'),'receipts':basis.get('read_receipts_sha256'),'reads':[read.get('id') for read in reads],
        'source':source.get('revision'),'observed':observed},sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _page_cursor(cut, position) -> str:
    from laplace.core.records import capture
    return capture.encode_token({'schema':CURSOR_SCHEMA,'cut':cut,'position':position})


def _page_position(cursor, cut, total) -> int:
    from laplace.core.records import capture
    try:
        value=capture.decode_token(cursor)
    except (ValueError,TypeError,UnicodeError) as exc:
        raise ValueError('The changed-read cursor is malformed; start again from the first page.') from exc
    if not isinstance(value,dict) or set(value)!={'schema','cut','position'} or value['schema']!=CURSOR_SCHEMA:
        raise ValueError('The changed-read cursor is malformed; start again from the first page.')
    if value['cut']!=cut:
        raise ValueError('The consulted evidence, candidate, basis or source revision changed since this traversal started '
                         '(another observation cut); its earlier pages are not a complete observation. Start again from the first page.')
    position=value['position']
    if not isinstance(position,int) or isinstance(position,bool) or not 0<position<=total:
        raise ValueError('The changed-read cursor position is outside this observation\'s changed reads; start again from the first page.')
    return position


def _size(value) -> int:
    return len(json.dumps(value,ensure_ascii=False,default=str).encode())


def _page_row(observed, read):
    """One bounded row (at most ROW_BYTES): the observation, its exact retained receipt handle, and the exact renewing
    read only when its payload is small; selectors, inspect reads and the payload give way to the receipt detail."""
    detail={'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+str(observed.get('read_id'))}}
    call={'operation':read.get('operation') or observed['operation'],
          'payload':{k:v for k,v in (read.get('payload') or {}).items() if k!='project'}}
    row={key:observed.get(key) for key in ('read_id','operation','currentness','consumed_output_sha256','observed_output_sha256')}
    row['read_detail']=detail
    row['renew']=call if _size(call)<=1600 else None
    row['payload_omitted']=row['renew'] is None
    selectors=observed.get('changed_selectors')
    if isinstance(selectors,dict):   # the judgement fields; the constant note and the per-side budget detail stay out
        selectors={**{key:value for key,value in selectors.items() if key not in ('coverage','note')},
                   'complete':bool((selectors.get('coverage') or {}).get('complete'))}
    if selectors is not None and _size(selectors)>1200:
        row['changed_selectors']=None;row['selectors_omitted']=len(selectors) if isinstance(selectors,(list,dict)) else 1
    else:row['changed_selectors']=selectors
    if observed.get('selector_note'):row['selector_note']=str(observed['selector_note'])[:300]
    inspect=[item for item in observed.get('inspect_reads') or [] if _size(item)<=800][:2]
    if inspect:row['inspect_reads']=inspect
    for key in ('inspect_reads','changed_selectors','renew'):   # a long read id or digest cannot exceed the row bound
        if _size(row)<=ROW_BYTES:break
        row.pop(key,None)
        if key=='renew':row['renew']=None;row['payload_omitted']=True
    return row


def changed_read_page(root:Path,turn:dict,version:str,proposal:dict,*,records,cursor:str|None=None,limit:int=PAGE_ROWS,coverage=None)->dict:
    """One bounded page of the candidate's changed consulted reads, for ONE observation cut.

    Read-only diagnostics (CR-R1): nothing is banked, no witness is renewed and nothing is approved or applied. Every
    page observes all of the candidate's consulted reads once, in the seal's consulted order; the observation cut
    hashes the candidate, basis, consulted sequence, source revision and everything observed. A continuation is
    served only when this page's observation has the same cut, so a complete traversal is exact for one stated cut;
    any evidence change between pages refuses the continuation, and nothing earlier is called complete.
    """
    from laplace.manuscript.proposal_navigation import handle
    project=turn.get('project') or ''
    head={'schema_version':'laplace.changed-consulted-reads/2','project':project,'turn_id':turn['id'],'proposal_version':version}
    try:
        basis, reads, source, _observed, virtual, _transitions = _read_scope(root, turn, version, proposal, None, records)
    except _BasisNotCurrent as refused:
        return {**head,'status':'REFUSED','currentness':refused.state,'reason':refused.reason,'observation':None,
                'changed_reads':[],'complete':False,'next':None,**({'coverage':{**coverage,'evidence_replays':0}} if coverage else {}),
                'note':'The candidate was refused before any consulted read was observed: nothing was observed and nothing is complete.'}
    if len(reads)>PAGE_CONSULTED_MAX:
        raise ValueError('This candidate consulted %d reads; a changed-read page observes at most %d. Use the refusal summary '
                         'and each consulted receipt, then request a fresh proposal.' % (len(reads),PAGE_CONSULTED_MAX))
    tokens,changed=[],[]
    for read in reads:
        observed=_observe_read(root,turn,read,virtual,tokens)
        if observed is not None:changed.append((observed,read))
    cut=_page_cut(turn,version,basis,reads,source,[[read.get('id'),token] for read,token in zip(reads,tokens)])
    start=_page_position(cursor,cut,len(changed)) if cursor else 0
    record=basis.get('record_id')
    rows,position=[],start
    while position<len(changed) and len(rows)<limit:
        rows.append(_page_row(*changed[position]));position+=1
        if len(rows)>1 and sum(map(_size,rows))>PAGE_BYTES:rows.pop();position-=1;break

    def page():
        following=handle(project,{'id':turn['id'],'record_id':record,'proposal_version':version,'view':'changed-reads',
            'cursor':_page_cursor(cut,position),'limit':limit}) if position<len(changed) else None
        return {**head,'status':'OBSERVED','record_id':record,'source_revision':source.get('revision'),
            'observation':{'cut':cut,'consulted':len(reads),'replayed':sum(token!='not-replayed' for token in tokens),'changed':len(changed)},
            'changed':{'from':start,'to':position,'of':len(changed)},
            'changed_reads':rows,'page_bytes':sum(map(_size,rows)),'complete':following is None,'next':following,
            'basis_detail':{'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+str(record)}},
            **({'coverage':{**coverage,'evidence_replays':sum(token!='not-replayed' for token in tokens)}} if coverage else {}),
            'note':('Read-only diagnostics for one observation cut (every consulted read observed when this page was read). '
                    'A continuation is served only while the evidence still gives the same cut. No witness is renewed, no '
                    'baseline is banked and nothing is approved or applied; renew re-reads one read for later candidates only.')}
    measured=lambda: {**page(),'response_bytes':99999}   # the field itself is counted, at its widest
    value=measured()
    while len(rows)>1 and _size(value)>PAGE_RESPONSE_BYTES:   # the whole response (HTTP body bytes), not only its rows
        rows.pop();position-=1;value=measured()
    while _size(value)!=value['response_bytes']:   # the exact body size, its own digits included (a fixed point)
        value['response_bytes']=_size(value)
    return value


class _BasisNotCurrent(Exception):
    """A phase's refusal: the exact reason and currentness the basis check returns (never raised out of it)."""
    def __init__(self, reason: str, state: str = 'STALE'):
        super().__init__(reason)
        self.reason, self.state = reason, state


def _not_current(reason: str, state: str = 'STALE') -> dict:
    return {'currentness':state,'reason':reason,'transition_ids':[]}


class _SourceObservation:
    """This check's own source reads: one byte read per file, and the pins the candidate consumed per file."""
    def __init__(self, root: Path, md: Path):
        self.root, self.md = root, md
        self.goals, self.file_facts = {}, {}

    def fact(self, path):
        if path not in self.file_facts:
            physical=path.read_bytes();raw,facts=_source_text_facts(physical)
            self.file_facts[path]=(raw,facts['text_sha256'].removeprefix('sha256:'),physical)
        return self.file_facts[path]

    def goal(self, file, digest, domain='canonical'):
        from laplace.manuscript import proposal_preflight
        path=proposal_preflight._resolve(self.root,self.md,str(file or ''))
        if path is None or not isinstance(digest,str):return False
        digest=digest.removeprefix('sha256:')
        if domain in self.goals.get(path,{}) and self.goals[path][domain]!=digest:return False
        self.goals.setdefault(path,{})[domain]=digest
        return True


def _read_scope(root, turn, version, proposal, source, records):
    """The phases before the consulted reads are observed (receipts, edition, source pins, siblings, owned inverse);
    shared by the whole check and the bounded changed-read pages, so both judge the same candidate the same way."""
    basis, reads = _consumed_receipts(root, turn, version, proposal, records)
    from laplace.manuscript import manuscript_source
    source=source if source is not None else manuscript_source.resolve(turn['project'],repo_root=root)
    expected=basis.get('document') or {}
    if any(expected.get(key) is not None and expected[key]!=source.get(key)
           for key in ('root','manuscript_dir','edition')):
        raise _BasisNotCurrent('The candidate selected edition changed. Request a fresh proposal.')
    observed = _SourceObservation(root, (root/str(source.get('manuscript_dir') or '')).resolve())
    _consumed_source_pins(observed, proposal, reads)
    apps = _accepted_siblings(observed, turn, version, proposal)
    virtual, transitions = _owned_inverse(observed, turn, apps)
    return basis, reads, source, observed, virtual, transitions


def _proposal_validation_basis(root:Path,turn:dict,version:str,proposal:dict,*,source:dict|None=None,records=None) -> dict:
    """Validate immutable inputs, carrying only exact same-candidate source writes.

    Inverses exist solely in this read. Producer receipts and context rows are
    never rebased here. Unknown legacy inputs cannot grant mutation authority.
    Phases, in order: the consumed receipts, the consumed source pins, accepted sibling transitions,
    the exact owned inverse to the consumed source, the context receipt, then every consulted read.

    Scoped progress (laplace.core.scoped): source pins, edition, receipts and context are the target and
    consumed basis and refuse when they move. Each replayed read takes its role from the read contract
    (writing.reads.read_role): a changed consumed read refuses as before; a changed or unavailable read that
    only observed derived output (the document's build/PDF state) is a local review obligation on the result,
    so a source repair is never blocked by the derived witness it will regenerate.
    """
    from laplace.core import scoped as core_scoped
    from laplace.writing import reads as read_contract
    try:
        basis, reads, source, observed, virtual, transitions = _read_scope(root, turn, version, proposal, source, records)
        context_id, reasons = _context_reasons(root, turn, basis, source, observed, virtual)
        observations = _changed_reads(root, turn, reads, virtual)
    except _BasisNotCurrent as refused:
        return _not_current(refused.reason, refused.state)
    roles = {read.get('id'): read_contract.read_role(str(read.get('operation') or ''), read.get('payload')) for read in reads}
    judged = core_scoped.judge([core_scoped.observation(row['read_id'], roles.get(row['read_id'], 'consumed'),
        expected=row['consumed_output_sha256'], observed=row['observed_output_sha256'] if row['currentness'] == 'CHANGED' else None,
        detail={'operation': row['operation']}) for row in observations])
    changed = [row for row in observations if roles.get(row['read_id'], 'consumed') != 'consulted']
    if reasons or changed:
        from laplace.writing import operations
        from laplace.writing import reads as read_contract
        reason=(read_contract.stale_evidence_message(changed) if changed
            else 'The consumed argument, evidence or corrections changed: '+', '.join(reasons)+'. Request a fresh proposal.')
        return {**_not_current(reason),'consumed_read_recovery':consumed_read_recovery(turn,basis,changed,context_reasons=reasons)}
    return {'currentness':'CURRENT','reason':None,'record_id':basis.get('record_id'),
            'context_id':context_id,'read_ids':[r.get('id') for r in reads],
            'transition_ids':transitions,'proposal_version':version,
            'review_obligations':judged['obligations'],'semantic_currentness':judged['semantic_currentness']}


def _consumed_receipts(root, turn, version, proposal, records) -> tuple[dict, list]:
    """The candidate's saved basis and the exact reads it consulted; legacy or partial bases are UNKNOWN."""
    basis=(turn.get('proposal_bases') or {}).get(version)
    if not isinstance(basis,dict):
        raise _BasisNotCurrent('The saved candidate input basis is unavailable. Request a fresh proposal.','UNKNOWN')
    if basis.get('ambiguous_legacy_basis'):
        raise _BasisNotCurrent('Identical legacy proposal text has ambiguous consumed input bases. Request a fresh proposal.','UNKNOWN')
    consumed={**turn,**basis}
    records=records if records is not None else writing_records.fold_records(root)
    from laplace.manuscript.manuscript_proposals import consumed_alternatives
    if consumed_alternatives(turn,version,records):
        raise _BasisNotCurrent('An accepted overlapping version consumed this candidate source basis. Request a fresh proposal.')
    if set(basis.get('read_ids') or [])!={row.get('id') for row in (basis.get('tool_reads') or {}).values()}:
        raise _BasisNotCurrent('A consumed read receipt is unavailable. Request a fresh proposal.','UNKNOWN')
    receipts=records.get('read_receipts') or {}
    if any((receipts.get(ident) or {}).get('ambiguous') for ident in basis.get('read_ids') or []):
        # the fold marks an id that more than one journal row carries; which one was consumed is not decidable
        raise _BasisNotCurrent('A consumed read receipt identity is carried by more than one journal row. Request a fresh proposal.','UNKNOWN')
    if basis.get('read_receipts_sha256')!=_read_basis_digest(basis.get('tool_reads') or {}):
        raise _BasisNotCurrent('The consumed read receipt identities disagree. Request a fresh proposal.','UNKNOWN')
    reads=mutation_attribution._proposal_consulted_reads(consumed,proposal.get('edits') or [])
    if not basis.get('context_id'):
        raise _BasisNotCurrent('The saved candidate has no retained scientific context receipt. Request a fresh proposal.','UNKNOWN')
    return basis, reads


def _consumed_source_pins(observed: _SourceObservation, proposal, reads) -> None:
    """Every source version the candidate consumed (anchors, then source reads) must agree per file."""
    for edit in proposal.get('edits') or []:
        anchor=edit.get('source_anchor') or {}
        if anchor.get('sha256') and not observed.goal(edit.get('file'),anchor['sha256']):
            raise _BasisNotCurrent('The candidate source pins disagree. Request a fresh proposal.','UNKNOWN')
    for read in reads:
        if read.get('operation')=='source':
            for scope in read.get('source_scope') or []:
                pin=scope.get('expected_source_digest')
                if pin and not observed.goal(scope.get('file'),pin,'physical'):
                    raise _BasisNotCurrent('The candidate consumed incompatible source versions. Request a fresh proposal.')


def _accepted_siblings(observed: _SourceObservation, turn, version, proposal) -> list:
    """This version's completed applications; each accepted sibling's exact postimage must still exist."""
    from laplace.manuscript import proposal_preflight
    from laplace.manuscript.manuscript_proposals import decisions, edit_id
    root, md = observed.root, observed.md
    # A derived anchor is not a replacement consumed basis. Its exact current
    # postimage must still exist, including after an undo or external rewrite.
    chosen=decisions(turn,version)
    active_ids={edit_id(e) for e in proposal.get('edits') or [] if edit_id(e) not in chosen}
    latest={row['edit_id']:row for row in turn.get('proposal_anchor_records') or []
            if row.get('proposal_version')==version and row.get('edit_id') in active_ids}
    apps=[app for app in source_effects.applications(turn) if app.get('complete') and app.get('candidate_version')==version]
    originals={edit_id(edit):edit for edit in proposal.get('edits') or []}
    for app in apps:
        if app.get('approval_mode')!='author-edited-current-source-rewrite':continue
        ids=app.get('candidate_edit_ids') or [];applied=source_effects.applied_edits(turn,app)
        if len(ids)!=len(applied) or any(ident not in originals or
            _source_text_facts(str(originals[ident].get('after') or '').encode())[0]!=
            _source_text_facts(str(actual.get('after') or '').encode())[0]
            for ident,actual in zip(ids,applied)):
            raise _BasisNotCurrent('An author-edited rewrite changed this candidate consumed source. The shared basis does not '
                                   'prove remaining edits independent; request a fresh proposal.')
    for row in latest.values():
        member=next((e for e in proposal['edits'] if edit_id(e)==row['edit_id']),None)
        path=proposal_preflight._resolve(root,md,str((member or {}).get('file') or ''))
        if path is None or observed.fact(path)[1]!=(row.get('source_anchor') or {}).get('sha256'):
            raise _BasisNotCurrent('The accepted sibling source transition was undone or changed externally. Request a fresh proposal.')
        cause=next((app for app in apps if app.get('id')==row.get('caused_by')),None)
        pins=[pin for pin in ((cause or {}).get('owned_changes') or {}).get('files') or []
              if pin.get('path')==path.relative_to(root).as_posix()]
        if len(pins)!=1 or 'sha256:'+hashlib.sha256(observed.fact(path)[2]).hexdigest()!=pins[0].get('after_sha256'):
            raise _BasisNotCurrent('The accepted sibling physical postimage changed. Request a fresh proposal.')
    return apps


def _owned_inverse(observed: _SourceObservation, turn, apps) -> tuple[dict, list]:
    """Undo only this candidate's own exact owned applications, newest first, until each consumed pin matches.

    Returns the virtual consumed text per file (in this read only) and the applications inverted."""
    root, md = observed.root, observed.md
    virtual, transitions = {}, []
    for path,wanted in observed.goals.items():
        try:raw,current_digest,physical=observed.fact(path)
        except OSError:raise _BasisNotCurrent('A consumed source file is unavailable.')
        digest=lambda value:hashlib.sha256(value.encode()).hexdigest()
        matches=lambda: (wanted.get('canonical') in (None,digest(raw))
            and wanted.get('physical') in (None,hashlib.sha256(physical).hexdigest()))
        if matches():continue
        relative=path.relative_to(root).as_posix();file=path.relative_to(md).as_posix()
        for app in reversed(apps):
            pins=[pin for pin in (app.get('owned_changes') or {}).get('files') or [] if pin.get('path')==relative]
            if not pins:continue
            pin=pins[0]
            if ('sha256:'+hashlib.sha256(physical).hexdigest()!=pin.get('after_sha256')
                or 'sha256:'+digest(raw)!=pin.get('after_source_text_sha256',pin.get('after_sha256'))):
                raise _BasisNotCurrent('The accepted source history is not an exact owned chain. Request a fresh proposal.')
            members=sorted([e for e in source_effects.applied_edits(turn,app) if e.get('file')==file],key=lambda e:e['line_start'])
            if not members:raise _BasisNotCurrent('The accepted source inverse is unavailable.','UNKNOWN')
            shifted=[];delta=0
            for e in members:
                e={**e,'before':_source_text_facts(e['before'].encode())[0],
                    'after':_source_text_facts(e['after'].encode())[0]}
                lo=e['line_start']+delta;hi=lo+len(e['after'].split('\n'))-1
                shifted.append((lo,hi,e));delta+=e['after'].count('\n')-e['before'].count('\n')
            lines=raw.split('\n')
            for lo,hi,e in reversed(shifted):
                if '\n'.join(lines[lo-1:hi])!=e['after']:raise _BasisNotCurrent('The accepted source inverse is unproven.')
                lines[lo-1:hi]=e['before'].split('\n')
            raw='\n'.join(lines)
            if 'sha256:'+digest(raw)!=pin.get('before_source_text_sha256',pin.get('before_sha256')):
                raise _BasisNotCurrent('The accepted canonical source preimage is unproven.')
            try:physical=_source_preimage_bytes(raw,pin.get('before_source_format'))
            except (ValueError,UnicodeError):raise _BasisNotCurrent('The accepted source byte format is unproven.')
            if 'sha256:'+hashlib.sha256(physical).hexdigest()!=pin.get('before_sha256'):
                raise _BasisNotCurrent('The accepted physical preimage hash is unproven.')
            if app['id'] not in transitions:transitions.append(app['id'])
            if matches():break
        if not matches():raise _BasisNotCurrent('The consumed source changed outside this candidate. Request a fresh proposal.')
        virtual[path]=physical.decode('utf-8')
    return virtual, transitions


def _context_reasons(root, turn, basis, source, observed: _SourceObservation, virtual) -> tuple[str, list]:
    """The consumed context receipt's stale reasons, less those the exact owned inverse explains."""
    from laplace.pipeline import authoring
    context_id=basis.get('context_id');reasons=[]
    if context_id:
        observation={}
        context=authoring.inspect(turn['project'],basis.get('selection'),repo_root=root,context_id=context_id,
            _source_observation=observation)
        if (context.get('staleness_scope') or {}).get('receipts_checked')!=1:
            raise _BasisNotCurrent('The consumed context receipt is unavailable. Request a fresh proposal.','UNKNOWN')
        reasons=[reason for row in context.get('stale') or [] if row.get('context_id')==context_id for reason in row.get('reasons') or []]
        if virtual and not (basis.get('dependencies') or {}).get('source_dependencies'):
            # Empty scoped dependencies retain the original whole-traversal
            # recipe. Prove it with the exact owned inverse, not a fresh token.
            observed_document=observation.get('document') or {}
            if any(source.get(key)!=observed_document.get(key) for key in ('root','manuscript_dir','edition')):
                raise _BasisNotCurrent('The selected edition changed during validation. Read the exact candidate again.')
            traversal=observation.get('traversal') or {};projected=[];seen=set()
            postimages={path:(hashlib.sha256(observed.file_facts[path][2]).hexdigest(),observed.file_facts[path][2].decode('utf-8'))
                for path in virtual}
            for row in traversal.get('sources') or []:
                path=(root/str(row.get('file') or '')).resolve()
                if path in virtual:
                    if (row.get('sha256'),row.get('text'))!=postimages[path]:
                        raise _BasisNotCurrent('The owned source postimage changed during validation. Read the exact candidate again.')
                    seen.add(path);row={**row,'text':virtual[path]}
                projected.append(row)
            retained=(basis.get('dependencies') or {}).get('source_revision')
            if seen!=set(virtual):
                raise _BasisNotCurrent('The owned source occurrence is unavailable in this validation observation.')
            if ('source-revision-changed' in reasons and isinstance(retained,str)
                    and authoring._revision({'sources':projected})==retained):
                reasons.remove('source-revision-changed')
        for reason in list(reasons):
            if not reason.startswith('source-revision-changed:'):continue
            name=reason.partition(':')[2];path=(root/name).resolve()
            deps=[dep for dep in (basis.get('dependencies') or {}).get('source_dependencies') or [] if dep.get('file')==name]
            if path in virtual and deps and all(authoring._dependency_current(dep,
                {'sources':[{'file':name,'order':dep.get('order'),'text':virtual[path]}]})==dep.get('digest') for dep in deps):
                reasons.remove(reason)
    return context_id, reasons


def _changed_reads(root, turn, reads, virtual) -> list:
    """Replay every consulted read once and compare its digest; a read the owned inverse explains is current."""
    return [row for row in (_observe_read(root, turn, read, virtual) for read in reads) if row is not None]


def _observe_read(root, turn, read, virtual, tokens=None):
    """One consulted read replayed and compared: its observation when changed or unavailable, else None.
    ``tokens`` (optional) receives what this observation saw, for an observation cut: the current digest,
    UNAVAILABLE, or why the read was not replayed."""
    from laplace.writing import operations
    from laplace.writing import reads as read_contract
    note=tokens.append if tokens is not None else (lambda value: None)
    operation=read.get('operation');payload=read.get('payload') or {}
    if read_contract.effect(operation, payload) != 'read':
        raise _BasisNotCurrent('A consumed receipt is not a read operation. Request a fresh proposal.','UNKNOWN')
    if operation in mutation_attribution._TRANSIENT_APPLY_READS or mutation_attribution._historical_activity_read(operation,payload):
        note('not-replayed');return None
    try:
        value=operations.replay_read(root,turn['project'],turn.get('mode','discuss'),read,turn['id'])
        current_digest=read_contract.comparison_digest(operation,value,read,root=root)
        same=current_digest==read_contract.consumed_digest(read)
        state='UNAVAILABLE' if isinstance(value,dict) and value.get('exists') is False else 'CHANGED'
    except (ValueError,OSError) as error:
        same=False;current_digest=None;state='UNAVAILABLE';value=None
    note(current_digest if state!='UNAVAILABLE' or current_digest else 'UNAVAILABLE')
    if same:return None
    scopes=read.get('source_scope') or []
    physical=operation=='source' and not any(payload.get(key) for key in ('node_id','node_ids','section_ids','sections','ids'))
    if physical and scopes and all(scope.get('expected_source_digest') and
        (root/str(scope.get('file') or '')).resolve() in virtual and
        'sha256:'+hashlib.sha256(virtual[(root/scope['file']).resolve()].encode()).hexdigest()==scope['expected_source_digest']
        for scope in scopes):return None
    return read_currentness_observation(read,value if same is False and current_digest is not None else None,current_digest,state)


# ------------------------------------------------------------------------------- the proposal view and its history
# What state a saved candidate is in (ready, applied, partial, superseded...) given its decisions, applications and the
# live job registry, and which earlier applications historically matched its effect (moved from the facade, family 1).
# The view is the one projection every reader of a proposal uses.

def _same_application_edition(first: dict, second: dict) -> bool:
    left, right = first.get("document"), second.get("document")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return (all(left.get(key) is not None and left.get(key) == right.get(key)
                for key in ("root", "manuscript_dir"))
            and left.get("edition") == right.get("edition"))


def _effect_pairs(proposal: dict) -> list[tuple[str, str, str]]:
    from laplace.manuscript.manuscript_proposals import text_identity
    return sorted((str(edit.get("file") or ""), text_identity(edit,"before"), text_identity(edit,"after"))
                  for edit in proposal.get("edits") or [] if isinstance(edit, dict))


def applications_for_effect(records: dict, turn: dict, proposal: dict) -> list[dict]:
    """Historical effect-match diagnostics, never candidate acceptance authority.

    A later exact inverse application is treated as an explicit revert, so the
    old proposal remains reviewable. Matching these fields does not bind another
    candidate's consumed basis or prove its current postimage.
    """
    effect = _proposal_effect_digest(proposal)
    matches = []
    all_apps = []
    for other in records.get("turns", {}).values():
        if other.get("id") == turn.get("id") or other.get("project") != turn.get("project"):
            continue
        if not _same_application_edition(turn, other):
            continue
        for application in source_effects.applications(other):
            if application.get("complete"):
                all_apps.append((other, application))
                if application.get("edit_sha256") == effect:
                    matches.append((other, application))
    wanted = _effect_pairs(proposal)
    out = []
    for other, application in matches:
        applied_at = str(application.get("ts") or "")
        reverted = any(str(candidate.get("ts") or "") > applied_at
                       and _effect_pairs({"edits": candidate.get("edits") or []}) ==
                       sorted((file, after, before) for file, before, after in wanted)
                       for _other, candidate in all_apps)
        if not reverted:
            out.append({"id": application.get("id"), "turn_id": other.get("id"),
                        "project": other.get("project"), "origin": application.get("origin")})
    return out


def _same_edit_occurrence(first:Mapping[str,Any],second:Mapping[str,Any],*,same_after:bool=True)->bool:
    from laplace.manuscript.manuscript_proposals import text_identity
    first_effect=(str(first.get("file") or ""),text_identity(first,"before"))
    second_effect=(str(second.get("file") or ""),text_identity(second,"before"))
    if first_effect!=second_effect or same_after and text_identity(first,"after")!=text_identity(second,"after"):return False
    left,right=first.get("source_anchor"),second.get("source_anchor")
    if isinstance(left,Mapping) and isinstance(right,Mapping):return dict(left)==dict(right)
    return (first.get("line_start"),first.get("line_end"))==(
            second.get("line_start"),second.get("line_end"))


def _cross_turn_edit_applications(records:dict,turn:dict)->list[tuple[str,dict,dict,dict]]:
    all_apps=[]
    for other in records.get("turns",{}).values():
        if other.get("id")==turn.get("id") or other.get("project")!=turn.get("project"):continue
        if not _same_application_edition(turn,other):continue
        for application in source_effects.applications(other):
            if application.get("complete"):
                for edit in source_effects.applied_edits(other,application):
                    all_apps.append((str(application.get("ts") or ""),other,application,edit))
    return all_apps


def applications_for_edits(records: dict, turn: dict, proposal: dict) -> dict[str,list[dict]]:
    """Exact cross-turn fulfillment per edit, preserving partial proposal intent."""
    from laplace.manuscript.manuscript_proposals import edit_id, text_identity
    all_apps=_cross_turn_edit_applications(records,turn)
    result={}
    for edit in proposal.get("edits") or []:
        if not isinstance(edit,dict):continue
        key=(str(edit.get("file") or ""),text_identity(edit,"before"),text_identity(edit,"after"))
        matches=[row for row in all_apps if _same_edit_occurrence(edit,row[3])]
        live=[]
        for stamp,other,application,_applied in matches:
            inverse=any(later>stamp and (str(candidate.get("file") or ""),
                text_identity(candidate,"before"),text_identity(candidate,"after"))==
                (key[0],key[2],key[1]) for later,_o,_a,candidate in all_apps)
            if not inverse:live.append({"id":application.get("id"),"turn_id":other.get("id"),
                "project":other.get("project"),"origin":application.get("origin")})
        if live:result[edit_id(edit)]=live
    return result


def refinements_for_edits(records:dict,turn:dict,proposal:dict)->dict[str,list[dict]]:
    """Later same-preimage applications with different after bytes; never auto-fulfill."""
    from laplace.manuscript.manuscript_proposals import edit_id, text_identity
    all_apps=_cross_turn_edit_applications(records,turn);result={}
    for edit in proposal.get("edits") or []:
        if not isinstance(edit,dict):continue
        matches=[]
        for _stamp,other,application,applied in all_apps:
            if (_same_edit_occurrence(edit,applied,same_after=False)
                    and text_identity(edit,"after")!=text_identity(applied,"after")):
                matches.append({"id":application.get("id"),"turn_id":other.get("id"),
                    "project":other.get("project"),"origin":application.get("origin"),
                    "applied_edit":dict(applied)})
        if matches:result[edit_id(edit)]=matches
    return result


def proposal_view(turn: dict, *, records: dict | None = None, proposal: dict | None = None,
                  version:str|None=None) -> dict:
    from laplace.manuscript.manuscript_proposals import proposal_version, select_version, saved_proposals
    if version:turn=select_version(turn,version)
    elif proposal is not None:
        exact=[key for key,value in saved_proposals(turn).items() if value is proposal]
        if len(exact)==1:turn=select_version(turn,exact[0])
    raw=proposal if proposal is not None else ((turn.get('reply') or {}).get('proposal') or turn.get('pending_proposal'))
    view={**_proposal_view(turn,records=records,proposal=proposal),
          'proposal_version':proposal_version(turn)[0] if isinstance(raw,dict) else None}
    if records is not None and isinstance(raw,dict) and raw.get('edits'):
        view['historical_application_matches']={
            'effect':applications_for_effect(records,turn,raw),
            'edits':applications_for_edits(records,turn,raw),
            'qualification':'Historical source-effect matches, not this candidate acceptance or current-source proof.'}
    return view


def _proposal_view(turn: dict, *, records: dict | None = None, proposal: dict | None = None) -> dict:
    """Project the existing proposal rows without inventing a final reply.

    A tool can bank a proposal before its provider replies. The journal owns
    both that draft and any final reply; all readers use this same projection.
    """
    reply = turn.get('reply') or {}
    final = reply.get('proposal')
    if proposal is None:
        proposal = (turn.get('pending_proposal') if turn.get('_selected_proposal_version')
                    else final if isinstance(final, dict) else turn.get('pending_proposal'))
    if not isinstance(proposal, dict) or not proposal.get('edits'):
        return {'proposal': None, 'proposal_state': None}
    from laplace.manuscript.manuscript_proposals import decisions, edit_id
    proposal_ids = {edit_id(edit) for edit in proposal['edits']}
    from laplace.manuscript.manuscript_proposals import proposal_version
    instance_version=proposal_version(turn)[0]
    choices = {ident: row for ident, row in decisions(turn,instance_version).items() if ident in proposal_ids}
    if records is not None:
        from laplace.manuscript.manuscript_proposals import consumed_alternatives
        for ident,consumption in consumed_alternatives(turn,instance_version,records).items():
            choices.setdefault(ident,{'decision':'consumed-alternative','consumption':consumption})
    if choices:
        pending = [edit for edit in proposal['edits'] if edit_id(edit) not in choices]
        if pending:
            return {'proposal': {**proposal, 'edits': pending}, 'proposal_state': 'ready'}
        state = ('resolved-into-successor' if any(row['decision']=='resolved-into-successor' for row in choices.values())
                 else 'consumed-alternative' if all(row['decision']=='consumed-alternative' for row in choices.values())
                 else 'superseded' if all(row['decision']=='superseded' for row in choices.values())
                 else 'applied' if any(row['decision'] in {'accepted','superseded'} for row in choices.values()) else 'rejected')
        return {'proposal': None if state=='applied-elsewhere' else proposal,
                'proposal_state': state,
                **({'applied_elsewhere':[item for row in choices.values()
                                         for item in row.get('applications') or []]}
                   if state=='applied-elsewhere' else {})}
    with turn_jobs._LOCK:
        job = turn_jobs._JOBS.get(turn['id'])
        active = bool(job and not job['done'])
    proposal_digest = _proposal_digest(proposal)
    application = next((row for row in reversed(source_effects.applications(turn))
                        if row.get('candidate_version') == instance_version and
                           set(row.get('candidate_edit_ids') or []) == proposal_ids
                        # Legacy explicit content-version linkage stays readable;
                        # it cannot settle a newly sealed input-qualified version.
                        or not row.get('candidate_version') and instance_version==proposal_digest
                           and row.get('proposal_sha256')==instance_version), {})
    state = ('applied' if application.get('complete') else 'partial-application' if application
             else 'ready' if active or isinstance(final, dict) or reply.get('status')=='completed'
             else 'saved-without-final-reply')
    return {'proposal': proposal, 'proposal_state': state}


from laplace.writing import mutation_attribution  # noqa: E402  (cycle-safe: imported last)
