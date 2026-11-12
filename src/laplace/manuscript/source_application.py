"""THE PHYSICAL SOURCE APPLICATION TRANSACTION (S1 B3): a saved proposal's edits become source bytes once.

One transaction owner. The publication lock is records.proposal_write_lock; every caller (the /authoring door,
document_templates, reconciliation, profiles and manuscript_proposals) reaches these owners directly.

  apply_proposal           admit, lock, apply one saved proposal and finish its source changes.
  proposal_source_scope    the source/selection lease of one proposal (held across the whole transaction).
  _apply_proposal_locked   resolve the exact proposal version under the write lock, then the transaction.
  _apply_source_locked     the transaction itself, as named phases under the SAME leases (validate the
                           candidate and consumed basis -- writing.proposal_currentness -- plan the exact
                           originals and staged bytes, write with rollback, publish the application row,
                           rebase the turn's reads). A partial failure after the first write is rolled back
                           exactly or reported as a partial receipt; an application is recorded once.
  apply_revision / _rebase_current_turn_after_apply
                           the native apply_revision door and the context rebase after an application.
  validate_candidate       the closed candidate-family seam (reconciliation, document templates).

The journal is records.bank (custody publication); originals and hashes are never overwritten.
"""
from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from laplace.core import bodies as core_bodies
from laplace.representation import writing_bodies as bodies
from laplace.manuscript import source_effects
from laplace.writing import records as writing_records
from laplace.writing.records._fold import _proposal_digest, _proposal_effect_digest
from pathlib import Path


@contextmanager
def proposal_source_scope(root: Path, project: str, proposal: dict):
    """The selected TeX namespace observed by proposal preflight is its scope.

    Publication is outer; this source lease precedes fresh validation, staged
    duplicate-label checks, all writes/compensation and effect attribution.
    Invalid target paths remain the apply owner's refusals, never permissions
    conferred by this scope collector.
    """
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("read_only"):
        raise ValueError("This source is read-only. Create an editable project before applying revisions.")
    if not source.get("root") or not source.get("manuscript_dir"):
        raise ValueError("The manuscript is unavailable.")
    manuscript = (root / source['manuscript_dir']).resolve()
    def namespace():
        return {(root / name).resolve() for name in manuscript_source.traversal(source['root'], repo_root=root).get('files', [])}
    selected_paths = namespace()
    paths = set(selected_paths)
    for edit in proposal.get('edits') or []:
        file = Path(str(edit.get('file') or ''))
        if file.is_absolute() or '..' in file.parts:
            continue
        repo_file = (root / file).resolve()
        target = repo_file if repo_file.is_file() and repo_file.is_relative_to(manuscript) else (manuscript / file).resolve()
        if target.is_relative_to(manuscript) and target.suffix == '.tex' and target.parent.is_dir():
            paths.add(target)
    try:
        with manuscript_source.selection_mutation(project, root), manuscript_source.source_mutation(paths):
            current = manuscript_source.resolve(project, repo_root=root)
            if any(current.get(key) != source.get(key) for key in ('root', 'manuscript_dir', 'edition', 'read_only')) or namespace() != selected_paths:
                raise ValueError('Selected source namespace changed; request a fresh proposal.')
            yield source
    except manuscript_source.SourceLeaseError as exc:
        raise ValueError(str(exc)) from exc


def apply_proposal(root: Path, payload: dict) -> dict:
    """Apply one saved proposal: canonical presence admitted before any read, lock or effect, the transaction under the
    publication lock, then the source changes finished (the /authoring/apply door and the editor's apply)."""
    from laplace.core import identity_doors
    identity_doors.admit_expected(payload, "apply_proposal")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    changes = []
    with writing_records.proposal_write_lock(root):
        row = _apply_proposal_locked(root, payload, source_changes=changes)
    source_effects.finish_source_changes(root, row.get('project'), row, changes)
    return row


def _apply_proposal_locked(root: Path, payload: dict, *, source_changes: list | None = None, **kwargs) -> dict:
    """Existing publication owner delegates the complete physical transaction."""
    from laplace.manuscript.manuscript_proposals import select_version
    ident = str(payload.get('turn_id') or '')
    turn = kwargs.get('candidate_subject') or (kwargs.get('records_scope') or writing_records.fold_records(root))['turns'].get(ident)
    if not turn:
        raise ValueError('Unknown proposed revision.')
    if payload.get('proposal_version'):
        turn = select_version(turn, payload['proposal_version'])
    proposal = kwargs.get('proposal_override')
    if proposal is None:
        proposal = proposal_currentness.proposal_view(turn)['proposal'] or {}
    changes = source_changes if source_changes is not None else []
    with proposal_source_scope(root, turn['project'], proposal):
        row = _apply_source_locked(root, payload, source_changes=changes, **kwargs)
    # Public parents settle their selected-source attribution and publication
    # before explicitly invoking optional heading projection.
    if changes:
        row['plan_sync'] = {'status':'DEFERRED', 'reason':'parent publication has not settled'}
    return row


@dataclass
class _Transaction:
    """One exact candidate's application, threaded through the phases below under the caller's leases.

    The first block is the caller's keyword facts, unchanged; the rest is filled in phase order."""
    root: Path
    payload: dict
    proposal_override: dict | None
    allow_active: bool
    allow_multiple: bool
    proposal_digest: str | None
    request_digest: str | None
    effect_digest: str | None
    application_origin: str
    human_reviewed: bool
    candidate_version: str | None
    candidate_edit_ids: list | None
    source_changes: list | None
    candidate_subject: dict | None
    records_scope: dict | None
    ident: str = ''
    records: dict | None = None
    turn: dict | None = None
    proposal: dict | None = None
    immutable: dict | None = None
    edits: list = field(default_factory=list)
    project: str = ''
    application_before: dict | None = None
    source: dict | None = None
    validation_basis: dict | None = None
    md: Path | None = None
    originals: dict = field(default_factory=dict)
    staged: dict = field(default_factory=dict)
    original_formats: dict = field(default_factory=dict)


def _apply_source_locked(root: Path, payload: dict, *, proposal_override: dict | None = None,
                           allow_active: bool = False, allow_multiple: bool = False,
                           proposal_digest: str | None = None,
                           request_digest: str | None = None,
                           effect_digest: str | None = None,
                           application_origin: str = "author", human_reviewed: bool = False,
                           candidate_version:str|None=None,candidate_edit_ids:list|None=None,
                           source_changes: list | None = None, candidate_subject: dict | None = None,
                           records_scope:dict|None=None) -> dict:
    """The transaction: admit the exact candidate, then its source; plan every byte; write; publish once.

    Every refusal is raised before the first source write. After it, a failure is compensated through
    the same versioned rewrite door and reported in the one application row."""
    tx = _Transaction(root, payload, proposal_override, allow_active, allow_multiple, proposal_digest,
                      request_digest, effect_digest, application_origin, human_reviewed, candidate_version,
                      candidate_edit_ids, source_changes, candidate_subject, records_scope)
    reused = _admit_candidate(tx)
    if reused is not None:
        return reused
    _admit_source(tx)
    _normalize_remaining_unit(tx)
    _stage_source(tx)
    actor, writer_by, writer_note = _application_actor(tx)
    complete, receipts, rollbacks = _write_with_rollback(tx, writer_by, writer_note)
    row, advance_context = _application_row(tx, actor, complete, receipts, rollbacks)
    return _publish_application(tx, row, complete, advance_context)


def _admit_candidate(tx: _Transaction) -> dict | None:
    """Phase 1: the exact saved candidate and its edit identity. Returns a finished identical application."""
    from laplace.manuscript import proposal_preflight
    from laplace.manuscript.manuscript_proposals import decisions, edit_id, proposal_version, saved_proposals, select_version
    root, payload = tx.root, tx.payload
    tx.ident = ident = str(payload.get("turn_id") or payload.get('candidate_id') or "")
    tx.records = ({'turns':{}} if tx.candidate_subject is not None else tx.records_scope if tx.records_scope is not None
                  else writing_records.fold_records(root))
    turn = tx.candidate_subject or tx.records["turns"].get(ident)
    if not turn:
        raise ValueError("Unknown proposed revision.")
    if turn.get("custody_errors"):
        raise ValueError("This revision's saved public body is unavailable or corrupt. Inspect its exact History record before retrying.")
    if payload.get('project') and payload['project'] != turn['project']:
        raise ValueError('This proposed revision belongs to another project.')
    job = turn_jobs._JOBS.get(ident)
    if job and not job['done'] and not tx.allow_active:
        raise ValueError('The writer is still working on this turn. Stop it or wait for its result before applying the saved proposal.')
    if not tx.allow_active and not tx.human_reviewed and not payload.get('proposal_version') and not payload.get('expected'):
        raise ValueError('Refresh the saved revision and supply its exact proposal_version before applying it.')
    if payload.get('proposal_version'):
        turn=select_version(turn,payload['proposal_version'])
    tx.turn = turn
    reply = turn.get("reply") or {}
    validation = reply.get("proposal_validation")
    if tx.proposal_override is None and isinstance(validation, dict) and validation.get("valid") is False:
        reason = "; ".join(str(item) for item in validation.get("errors") or [])
        raise ValueError("This proposal has invalid source addressing"
                         + (": " + reason if reason else "")
                         + ". Request a corrected proposal; nothing was applied.")
    proposal = tx.proposal_override if tx.proposal_override is not None else proposal_currentness.proposal_view(turn)['proposal'] or {}
    tx.proposal = proposal
    tx.proposal_digest = tx.proposal_digest or _proposal_digest(proposal)
    tx.effect_digest = tx.effect_digest or _proposal_effect_digest(proposal)
    tx.candidate_version = candidate_version = tx.candidate_version or proposal_version(turn)[0]
    if payload.get('proposal_version') and payload['proposal_version']!=candidate_version:
        raise ValueError('Select the exact owner proposal_version; authored-content aliases cannot authorize an application.')
    tx.immutable = saved_proposals(turn).get(candidate_version)
    if tx.immutable is None:
        raise ValueError("The exact saved candidate is unavailable. Request a fresh proposal.")
    for edit in list(proposal.get('edits') or []) + list(tx.immutable.get('edits') or []):
        anchor=edit.get('source_anchor')
        if anchor is not None:
            version_error=proposal_preflight.source_anchor_version_error(anchor)
            if version_error:raise ValueError(version_error)
    tx.candidate_edit_ids = edit_ids = tx.candidate_edit_ids or [edit_id(edit) for edit in proposal.get('edits') or []]
    # Exact candidate identity is required before mutation or terminal reuse.
    if payload.get("expected"):
        from laplace.core import identity_doors
        identity_doors.gate(
            "apply_proposal", supplied=payload,
            homes=[("proposal", "%s::%s" % (turn["project"], ident), candidate_version)],
            said="this proposed revision changed since you read it")
    previous=next((app for app in reversed(source_effects.applications(turn))
        if app.get('candidate_version')==candidate_version and set(app.get('candidate_edit_ids') or [])==set(edit_ids)),None)
    if previous and previous.get('complete'):
        return {'reused':True,'current_source_state':source_effects.application_source_state(root,previous),**previous}
    if previous:raise ValueError('This exact candidate application did not finish. Inspect its retained application history.')
    choices=decisions(turn,candidate_version)
    if edit_ids and all(ident in choices for ident in edit_ids):
        if all(choices[ident].get('decision')=='accepted' for ident in edit_ids):
            completed=next((app for app in reversed(source_effects.applications(turn))
                if app.get('complete') and app.get('candidate_version')==candidate_version),None)
            if completed:return {'reused':True,'terminal_state':'applied',
                'current_source_state':source_effects.application_source_state(root,completed),**completed}
        raise ValueError('This exact candidate was already decided. Inspect its retained history; it cannot be applied again.')
    edits = [dict(edit) for edit in proposal.get("edits") or []]
    tx.edits = [{**edit,**{key:value.replace('\r\n','\n').replace('\r','\n') for key in ('before','after')
                if isinstance(value:=edit.get(key),str)}} for edit in edits]
    if not tx.edits:
        raise ValueError("This turn has no source-addressed edits to apply.")
    return None


def _admit_source(tx: _Transaction) -> None:
    """Phase 2: the selected source, its pre-application snapshot and the candidate's current basis."""
    from laplace.pipeline import authoring  # noqa: F401  (imported here before the source snapshot, as before)
    from laplace.research import corpus_ingest
    from laplace.manuscript import manuscript_source
    root, turn = tx.root, tx.turn
    tx.project = project = turn["project"]
    if tx.payload.get('project') and tx.payload['project'] != project:
        raise ValueError('This proposed revision belongs to another project.')
    tx.application_before={"mutation_project":project,"mutation_files":mutation_attribution._mutation_file_snapshot(root,project),
                           "mutation_rewire_records":corpus_ingest.rewire_list(root,project)}
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("read_only"):
        raise ValueError("This source is read-only. Create an editable project before applying revisions.")
    expected_document = turn.get("document") or {}
    if any(expected_document.get(key) is not None and expected_document[key]!=source.get(key)
           for key in ("root","manuscript_dir","edition")):
        raise ValueError("The selected manuscript edition changed. Request a fresh revision.")
    if tx.candidate_subject is not None:
        validation_basis=validate_candidate(root,project,tx.candidate_subject,source=source)
    else:validation_basis=proposal_currentness._proposal_validation_basis(root,turn,tx.candidate_version,tx.immutable,
                                                                           source=source,records=tx.records)
    if validation_basis['currentness']!='CURRENT':
        raise proposal_currentness.ProposalBasisRefused(validation_basis)
    md = (root / source['manuscript_dir']).resolve() if source.get('manuscript_dir') else None
    if md is None or not md.is_relative_to(root.resolve()) or not md.is_dir():
        raise ValueError("The manuscript is unavailable.")
    tx.source, tx.validation_basis, tx.md = source, validation_basis, md


def _normalize_remaining_unit(tx: _Transaction) -> None:
    """Phase 3: a partly decided candidate's remaining exact unit, re-addressed without a preview."""
    root, turn, md = tx.root, tx.turn, tx.md
    derived=(turn.get('proposal_anchors_by_version') or {}).get(tx.candidate_version) or {}
    if tx.proposal_override is None and any(member in derived for member in tx.candidate_edit_ids):
        # Normalize the remaining exact unit without rendering a preview. Its
        # scientific basis was checked above; qualified anchors carry only known
        # source transformations, never a guessed old numeric location.
        from laplace.manuscript import proposal_preflight
        from laplace.manuscript.manuscript_proposals import edit_id, original_proposal
        anchored={edit_id(edit):edit for edit in original_proposal(turn).get('edits') or []}
        remaining=[anchored[member] for member in tx.candidate_edit_ids if member in anchored]
        if len(remaining)!=len(tx.candidate_edit_ids):raise ValueError('An exact remaining candidate component is unavailable.')
        addressed_files={}
        for edit in remaining:
            path=proposal_preflight._resolve(root,md,str(edit.get('file') or ''))
            if path is None:raise ValueError('A remaining candidate source is unavailable.')
            if path not in addressed_files:addressed_files[path]=path.read_text(encoding='utf-8')
            if proposal_preflight.proven_current_span(addressed_files[path],edit,turn=turn,root=root,path=path) is None:
                raise ValueError('The remaining candidate source scope is unproven; request a fresh source-centered proposal.')
        addressing_turn={**turn,'selection':{'files':list(dict.fromkeys(edit['file'] for edit in remaining))},
                         'dependencies':{},'tool_reads':{}}
        checked=proposal_preflight.preflight(root,tx.project,addressing_turn,
            {'answer':tx.proposal.get('answer',''),'edits':remaining},relocate_unanchored=False)
        if not checked['valid']:
            raise ValueError('The remaining candidate source addressing is unproven: '+'; '.join(checked['errors']))
        tx.edits=[dict(edit) for edit in checked['proposal']['edits']]


def _stage_source(tx: _Transaction) -> None:
    """Phase 4: every exact original and staged file, refused as a whole before any source change."""
    from laplace.manuscript import manuscript_source, proposal_basis, proposal_preflight
    from laplace.manuscript import review_surface as review
    root, md, source, project, edits = tx.root, tx.md, tx.source, tx.project, tx.edits
    originals, staged, original_formats = tx.originals, tx.staged, tx.original_formats
    # Validate the entire proposal before any source change. Apply bottom-up so
    # several non-overlapping edits to one file keep their original line spans.
    spans = {}
    selected_paths = {(root/name).resolve() for name in manuscript_source.traversal(source['root'], root).get('files', [])}
    for edit in edits:
        file = str(edit.get("file") or "")
        if Path(file).is_absolute() or ".." in Path(file).parts:
            raise ValueError("Edits must use a normal relative manuscript path.")
        repo_file = (root / file).resolve()
        if repo_file.is_file() and repo_file.is_relative_to(md.resolve()):
            file = repo_file.relative_to(md.resolve()).as_posix()
            edit["file"] = file
        fp = (md / file).resolve()
        if not fp.is_relative_to(md.resolve()) or fp.suffix != ".tex" or not fp.is_file():
            raise ValueError("An edit names a file outside the selected manuscript.")
        manuscript_source.source_access(project, fp, root, writable=True,
            expected_selection=manuscript_source.selection_identity(source, project), source=source, selected_paths=selected_paths)
        lo, hi = int(edit["line_start"]), int(edit["line_end"])
        if lo < 1 or hi < lo:
            raise ValueError("Invalid source span.")
        if fp not in originals:
            raw,original_formats[fp]=proposal_currentness._source_text_facts(fp.read_bytes())
        else:raw=originals[fp]
        originals[fp] = raw
        lines = raw.split("\n")
        if hi > len(lines) or "\n".join(lines[lo-1:hi]) != edit["before"]:
            raise ValueError("The source changed since this proposal. Ask for an updated revision; nothing was applied.")
        proven=proposal_preflight.proven_current_span(raw,edit,turn=tx.turn,root=root,path=fp)
        if proven!=(lo,hi):
            raise ValueError("The proposal's current source scope is unproven or changed. Request a fresh source-centered proposal; nothing was applied.")
        if edit.get('develops') or edit.get('evidence_refs'):
            basis=proposal_basis.assess(root,project,edit)
            if basis['errors'] and tx.candidate_subject is None:
                raise ValueError('The proposal scientific basis changed: '+'; '.join(basis['errors'])+'. Nothing was applied.')
        for a, b in spans.setdefault(file, []):
            if lo <= b and hi >= a:
                raise ValueError("The proposal contains overlapping edits; nothing was applied.")
        spans[file].append((lo, hi))
    # Refusals such as marker mutation must be found across the entire change,
    # before the first source file is touched.
    for file in spans:
        fp = (md / file).resolve()
        lines = originals[fp].split("\n")
        for edit in sorted((e for e in edits if e["file"] == file), key=lambda e: -e["line_start"]):
            lines[edit["line_start"] - 1:edit["line_end"]] = edit["after"].split("\n")
        staged[fp] = "\n".join(lines)
        integrity=proposal_preflight.staged_integrity_errors(originals[fp],staged[fp],
            is_root=fp==(root/str(source.get('root') or '')).resolve())
        if integrity:raise ValueError('; '.join(integrity)+'. Nothing was applied.')
        if review._STRUCT_LINE_RE.findall(originals[fp]) != review._STRUCT_LINE_RE.findall(staged[fp]):
            raise ValueError("The proposal changes protected provenance markers. Nothing was applied.")
    namespace=dict(originals)
    for name in manuscript_source.traversal(root/source['root'],repo_root=root).get('files') or []:
        path=(root/name).resolve()
        if path not in namespace and path.is_relative_to(md) and path.suffix=='.tex' and path.is_file():
            namespace[path]=path.read_text(encoding='utf-8')
    duplicate_errors=proposal_preflight.duplicate_label_errors(namespace,{**namespace,**staged})
    if duplicate_errors:raise ValueError('; '.join(duplicate_errors)+'. Nothing was applied.')


def _application_actor(tx: _Transaction) -> tuple[dict, str, str]:
    """Who applies: the actor recorded on the row and the rewrite door's `by` and note."""
    ident, application_origin, candidate_subject = tx.ident, tx.application_origin, tx.candidate_subject
    if tx.human_reviewed or application_origin == "author":
        application_actor = {"label": "author", "kind": "human",
                             "basis": "explicit manuscript review" if tx.human_reviewed else "explicit saved-proposal application"}
        writer_by, writer_note = "author:accepted-model", "Author accepted connected writing revision " + ident
        if application_origin=='author-rewrite':
            application_actor['basis']='author-edited current-source rewrite derived from saved candidate'
            writer_by,writer_note='author:rewrite','Author rewrote the current source after inspecting candidate '+ident
    elif application_origin == "current-turn-tool":
        settings = tx.turn.get("provider_settings") if isinstance(tx.turn.get("provider_settings"), dict) else {}
        application_actor = {"label": "eigen:session", "kind": "agent",
                             "provider": settings.get("provider"), "model": settings.get("model"),
                             "basis": "current-turn tool execution"}
        writer_by, writer_note = "eigen:session", "Agent applied connected writing revision " + ident
    else:
        application_actor = {"label": None, "kind": "unknown",
                             "basis": "application origin does not identify an executor"}
        writer_by, writer_note = "author", "Applied connected writing revision " + ident
    if candidate_subject is not None:
        template = candidate_subject.get('candidate_kind')=='document-template'
        application_actor={key:value for key,value in candidate_subject['application_actor'].items() if value is not None}
        application_actor['basis']=('explicit document-template candidate application' if template
                                    else 'explicit current-source candidate application')
        writer_by='eigen:session' if application_actor.get('kind')=='agent' else 'author:rewrite'
        writer_note=('Applied document template candidate ' if template else 'Applied current-source reconciliation candidate ')+ident
    return application_actor, writer_by, writer_note


def _write_with_rollback(tx: _Transaction, writer_by: str, writer_note: str) -> tuple[bool, list, list]:
    """Phase 5: one versioned rewrite per staged file; an incomplete transaction is compensated in reverse."""
    from laplace.manuscript import manuscript_source
    from laplace.manuscript import review_surface as review
    root, md, source, project, edits, ident = tx.root, tx.md, tx.source, tx.project, tx.edits, tx.ident
    originals, staged, source_changes = tx.originals, tx.staged, tx.source_changes
    receipts=[]
    written=[];failed=False
    for fp in staged:
        file=fp.relative_to(md).as_posix()
        members=[edit for edit in edits if edit["file"]==file]
        lo=min(int(edit["line_start"]) for edit in members)
        hi=max(int(edit["line_end"]) for edit in members)
        before="\n".join(originals[fp].split("\n")[lo-1:hi])
        delta=sum(len(str(edit["after"]).split("\n"))
                  -(int(edit["line_end"])-int(edit["line_start"])+1)
                  for edit in members)
        after="\n".join(staged[fp].split("\n")[lo-1:hi+delta])
        try:
            result=review.adjudicate(md,project,{"file":file,
                "expected_selection":manuscript_source.selection_identity(source, project),
                "line_start":lo,"line_end":hi,"before":before,"after":after,
                "verb":"rewrite","by":writer_by,"note":writer_note,"scope":"sentence"}, source_changes=source_changes, repo_root=root)
        except (OSError, ValueError) as exc:
            result = {'ok':False, 'error':str(exc), 'reason':'source-owner-failed',
                      'file':file, 'source_effect':'UNPROVED'}
        receipts.append(proposal_currentness._owner_rewrite_receipt(result))
        if result.get("error") or result.get("pending") or not result.get("ok"):
            failed=True;break
        written.append({"file":file,"line_start":lo,"line_end":hi,
                        "before":before,"after":after})
    complete = not failed and len(written)==len(staged)
    rollbacks = []
    if not complete:
        # Compensate through the same versioned rewrite door; never truncate
        # ledgers or overwrite a concurrent edit to the source.
        for applied in reversed(written):
            post_lines=applied["after"].split("\n")
            try:
                rollback = review.adjudicate(md, project, {"file":applied["file"],
                    "expected_selection":manuscript_source.selection_identity(source, project),
                    "line_start":applied["line_start"],
                    "line_end":applied["line_start"]+len(post_lines)-1,
                    "before":applied["after"],"after":applied["before"],
                    "verb": "rewrite", "by": "author",
                    "note": "Rollback of incomplete connected revision " + ident, "scope": "sentence"}, source_changes=source_changes, repo_root=root)
            except (OSError, ValueError) as exc:
                rollback = {'ok':False, 'error':str(exc), 'reason':'source-owner-failed',
                            'file':applied['file'], 'source_effect':'UNPROVED'}
            rollbacks.append(proposal_currentness._owner_rewrite_receipt(rollback))
    return complete, receipts, rollbacks


def _application_row(tx: _Transaction, actor: dict, complete: bool, receipts: list, rollbacks: list) -> tuple[dict, bool]:
    """Phase 6: the one writing-application row, its owned changes, source effect and context-rebase request."""
    from laplace.manuscript import manuscript_source
    from laplace.manuscript import source_effects
    root, source, project, ident = tx.root, tx.source, tx.project, tx.ident
    candidate_subject, validation_basis, application_origin = tx.candidate_subject, tx.validation_basis, tx.application_origin
    candidate_version, candidate_edit_ids = tx.candidate_version, tx.candidate_edit_ids
    staged, originals, original_formats = tx.staged, tx.originals, tx.original_formats
    row = {"record": "writing-application", "id": "WA-" + uuid.uuid4().hex,
           **({'candidate_id':ident,'candidate_ref':candidate_subject['candidate_ref'],
               'origin_turn_id':candidate_subject.get('origin_turn_id'), 'candidate_kind':candidate_subject.get('candidate_kind')}
              if candidate_subject is not None else {'turn_id':ident}),
           "project": project, "document":{key:source.get(key) for key in ('root','manuscript_dir','edition')},
           "complete": complete, "receipts": receipts,
           "rollbacks": rollbacks,
           "proposal_sha256": tx.proposal_digest,
           "request_sha256": tx.request_digest or tx.proposal_digest,
           "edit_sha256": tx.effect_digest,
           "origin": application_origin,
           "candidate_version":candidate_version,"candidate_edit_ids":candidate_edit_ids,
           "validation_basis":validation_basis,
           **({'derived_from_candidate':candidate_subject['candidate_ref'],
               'approval_mode':'document-template' if candidate_subject.get('candidate_kind')=='document-template' else 'current-basis-resolution',
               'predecessor':candidate_subject.get('predecessor')}
              if candidate_subject is not None else
              {'derived_from_candidate':{'turn_id':ident,'proposal_version':candidate_version,
                'edit_ids':candidate_edit_ids},'approval_mode':'author-edited-current-source-rewrite'}
              if application_origin=='author-rewrite' else {'approval_mode':'generated-candidate'}),
           # Scoped progress: the effect's own grade and the local obligations its admission carried.
           'review_obligations':validation_basis.get('review_obligations',[]),
           'result_grade':core_scoped.grade(complete=complete,obligations=validation_basis.get('review_obligations')),
           "actor": {key:value for key,value in actor.items() if value is not None},
           "edits": tx.edits,
           "rolled_back": bool(rollbacks) and all(r.get("banked") and not r.get("pending")
                                                   and not r.get("error") for r in rollbacks)}
    if not complete:
        row['ok'] = False
        row['status'] = 'SOURCE_INCOMPLETE'
        row['warning'] = ('The source transaction did not complete. Inspect its exact rewrite and rollback receipts and current source '
                          'before another action; do not repeat an effect without reinspection.')
    owned_files=[]
    if complete:
        digest=lambda text:"sha256:"+hashlib.sha256(text.encode()).hexdigest()
        for fp,after in staged.items():
            owned_files.append({"scope":"repository","path":fp.relative_to(root).as_posix(),
                "before_sha256":original_formats[fp]['byte_sha256'],"after_sha256":digest(after),
                'before_source_text_sha256':original_formats[fp]['text_sha256'],
                'after_source_text_sha256':proposal_currentness._source_text_facts(after.encode())[1]['text_sha256'],
                'before_source_format':{key:original_formats[fp][key] for key in ('schema_version','encoding','newline_runs')},
                "observed_after_sha256":core_identity.file_digest(fp)})
    owned_changes={"schema_version":"laplace.owner-mutation/1","files":owned_files,
                   "objects":[],"rewire_records":[],"views":["manuscript","document"]}
    row["owned_changes"] = owned_changes
    effect_files = []
    for fp, after in staged.items():
        file_effect = source_effects.observed_file(root, fp, originals[fp].encode('utf-8'), after.encode('utf-8'))
        file_effect['before_sha256'] = original_formats[fp]['byte_sha256']
        effect_files.append(file_effect)
    row['source_effect'] = source_effects.receipt(project,
        manuscript_source.selection_identity(source, project), effect_files, complete=complete,
        required=[{'owner':'source-application', 'status':'COMPLETE' if complete else 'COMPENSATED' if row['rolled_back'] else 'FAILED'}])
    attribution_ok,attribution_reason=mutation_attribution._owned_changes_exact(root,tx.application_before,owned_changes)
    advance_context=complete and tx.allow_multiple and attribution_ok and not tx.human_reviewed
    row["context_rebase"]={"exact":attribution_ok,"advanced":False,
        "status":"REQUESTED" if advance_context else "NOT_REQUESTED",
        "reason":("An explicit current-source candidate leaves the originating turn's read baselines unchanged." if candidate_subject is not None
                  else "Human acceptance leaves the native session's read baselines unchanged." if tx.human_reviewed else attribution_reason)}
    return row, advance_context


def _publish_application(tx: _Transaction, row: dict, complete: bool, advance_context: bool) -> dict:
    """Phase 7: bank the row once (an exception recovers only this exact id), then rebase the turn's reads."""
    from laplace.manuscript import source_effects
    root, project = tx.root, tx.project
    try:
        saved = writing_records.bank(root, row)
    except (OSError, ValueError) as exc:
        # A publication exception is not evidence that the row did not land.
        # Recover only this exact attempted ID with all supplied owner facts,
        # never by source text, time or an equivalent candidate.
        recovered = []
        try:
            from laplace.writing import records as exact_records
            observed = exact_records.selected_journal_fields(project,row['id'],root,fields=list(row))
            recovered = [observed] if core_bodies.encode({key:observed.get(key) for key in row}) == core_bodies.encode(row) else []
        except (OSError, ValueError):
            pass
        if len(recovered) != 1:
            attempted_id = row.pop('id')
            row.pop('record', None)
            row['source_applied'] = complete
            row['source_effect_retained'] = complete
            row['ok'] = False
            row['complete'] = False
            row['status'] = 'SOURCE_APPLIED_TRACKING_UNPROVED' if complete else 'SOURCE_INCOMPLETE_TRACKING_UNPROVED'
            row['application_tracking'] = {'status':'UNPROVED', 'attempted_id':attempted_id, 'reason':str(exc)}
            row['source_effect']['complete'] = False
            row['source_effect']['follow_through']['required'].append({'owner':'application-tracking','status':'UNPROVED','reason':str(exc)})
            row.update(source_effects.application_compatibility(row['source_effect']))
            row['context_rebase']['advanced'] = False
            row['warning'] = ('Source changes applied; application tracking is unproved. ' if complete else
                              'The source transaction did not complete; inspect its rewrite and rollback receipts. ')
            row['warning'] += 'Inspect the exact source feedback receipts and current source; do not repeat the effect.'
            return row
        saved = recovered[0]
        row['application_tracking'] = {'status':'RECOVERED', 'id':row['id'], 'reason':str(exc)}
    if saved.get("custody_degradation"):
        row["custody_degradation"] = saved["custody_degradation"]
    if advance_context:
        try:
            _rebase_current_turn_after_apply(root, tx.turn)
            row['context_rebase'] = {**row['context_rebase'], 'advanced':True, 'status':'COMPLETED'}
        except (OSError, ValueError) as exc:
            row['context_rebase'] = {**row['context_rebase'], 'advanced':False, 'status':'UNPROVED', 'reason':str(exc)}
            row['warning'] = 'Application recorded; context refresh is unavailable. Reinspect source and context; do not repeat the effect.'
    return row


def apply_revision(root: Path, project: str, turn_id: str, payload: dict) -> dict:
    """Apply an explicitly requested exact revision from the active writing turn.

    This is the provider-tool path.  It uses the public proposal preflight and
    the identical versioned source rewrite door as the later human Apply route,
    but does not require the provider turn to have completed first.
    """
    from filelock import FileLock
    if not isinstance(payload, dict):
        raise ValueError("apply_revision payload must be an object.")
    if "proposal" in payload:
        unknown_wrapper=set(payload)-{"proposal","project"}
        if unknown_wrapper:
            raise ValueError("apply_revision wrapper accepts only proposal and project; unknown fields: "
                             +", ".join(sorted(unknown_wrapper))+". Lineage develops/evidence_refs belongs inside each "
                             "edits[] item, not the wrapper or proposal top level.")
        if not isinstance(payload["proposal"],dict):raise ValueError("apply_revision.proposal must be an object with edits[].")
    proposal = dict(payload.get("proposal", payload))
    # The dispatcher adds project routing metadata to every tool payload.  It is
    # not authored revision content and must not make the final provider reply
    # hash differ from the exact proposal that was already applied.
    proposal.pop("project", None)
    if not isinstance(proposal, dict) or not isinstance(proposal.get("edits"), list):
        raise ValueError("apply_revision requires proposal.edits.")
    request_digest = _proposal_digest(proposal)
    request_effect_digest = _proposal_effect_digest(proposal)
    changes = []
    with writing_records.proposal_write_lock(root):
        records = writing_records.fold_records(root)
        turn = records["turns"].get(turn_id)
        if not turn or turn.get("project") != project:
            raise ValueError("The current writing turn does not belong to this project.")
        prior_request = [row for row in source_effects.applications(turn)
            if row.get('request_sha256')==request_digest and row.get('complete')]
        for app in reversed(prior_request):
            pins=(app.get('owned_changes') or {}).get('files') or []
            if pins and all(core_identity.file_digest(root/pin['path'])==pin.get('after_sha256') for pin in pins):
                return {'reused':True,'current_source_state':'POSTIMAGE',**app}
        from laplace.manuscript import proposal_preflight
        validation = proposal_preflight.preflight(root, project, turn, proposal)
        if not validation["valid"]:
            reason = "; ".join(str(item) for item in validation.get("errors") or [])
            raise ValueError("This proposal has invalid source addressing"
                             + (": " + reason if reason else "") + ". Nothing was applied.")
        normalized = validation["proposal"]
        proposal_digest = _proposal_digest(normalized)
        effect_digest = _proposal_effect_digest(normalized)
        sealed=writing_records.bank(root, {"record": "writing-proposal", "id": "PROP-" + uuid.uuid4().hex,
                     "turn_id": turn_id, "project": project, "proposal": normalized,
                     "proposal_sha256": proposal_digest, "request_sha256": request_digest,
                     "edit_sha256": effect_digest,
                     "origin": "current-turn-tool"})
        application = _apply_proposal_locked(root, {"turn_id": turn_id, "project": project},
                                      proposal_override=normalized, allow_active=True,
                                      allow_multiple=True, proposal_digest=proposal_digest,
                                      request_digest=request_digest, effect_digest=effect_digest,
                                      application_origin="current-turn-tool",
                                      candidate_version=sealed["proposal_instance_version"], source_changes=changes)
    source_effects.finish_source_changes(root, project, application, changes)
    return application


def _rebase_current_turn_after_apply(root: Path, turn: dict) -> None:
    """Advance only this turn's source/context inputs after its own exact rewrite."""
    from laplace.pipeline import authoring
    from laplace.writing import operations
    from laplace.writing import reads as read_contract
    project, turn_id = turn["project"], turn["id"]
    context = authoring.build_context(project, turn.get("selection"), repo_root=root,
                                      include_guidance=False, include_orientation=False)
    # ONE SHAPE for this row kind.  Until this synthesis three of the four
    # `writing-turn-context-baseline` literals carried `context_parts` and this one did not,
    # while `_records` merges the kind field by field (:384), so after a session applied its
    # own proposal every other context input was current and the part tokens the delta keys
    # on were the pre-apply ones -- one kind, two shapes, on exactly the fact the delta
    # reads.  The direction of that error was safe (a stale token only re-sends a part) and
    # that is why no test caught it; it was still two shapes.  The advance is the same one
    # every other write takes (:2011): a part this turn moved is marked held, because the
    # session that applied the proposal is the session that wrote it.  Parts absent from
    # this build -- orientation is excluded here -- keep their previous token and are
    # re-sent, which is the safe direction kept deliberately.
    held = dict(turn.get("context_parts") or {})
    held.update({str(part.get("key")): part.get("token")
                 for part in context.get("parts") or [] if part.get("key")})
    writing_records.bank(root, {"record": "writing-turn-context-baseline", "id": "CTXBASE-" + uuid.uuid4().hex,
                 "turn_id": turn_id, "project": project, "context_id": context.get("context_id"),
                 "dependencies": context.get("dependencies"), "document": context.get("document"),
                 "consumed": context.get("consumed"),
                 "science_context_digest": context.get("science_context_digest"),
                 "context_parts": held,
                 "cause": "current-turn-apply"})
    candidates = []
    for read in (turn.get("tool_reads") or {}).values():
        if read.get("operation") != "source":
            continue
        try:
            current = operations.replay_read(root, project, turn.get("mode", "discuss"), read, turn_id)
        except (OSError, ValueError):
            continue
        digest = read_contract.read_output_digest("source", current)
        if digest == read.get("output_sha256"):
            continue
        candidates.append({"operation": "source",
                           "payload": dict(read.get("payload") or {}),
                           "output_sha256": digest,
                           "supersedes_read": read.get("id")})
    if candidates:
        turn_reads.bank_read_baseline_groups(
            root, turn_id, project, "apply_revision", candidates)


def validate_candidate(root, project, subject, *, source=None):
    family = subject.get('candidate_kind')
    if family == 'current-source-resolution':
        from laplace.manuscript.reconciliation import validate_candidate as validate
    elif family == 'document-template':
        from laplace.manuscript.document_templates import validate_candidate as validate
    else:
        raise ValueError('No source application owner admits this candidate family.')
    return validate(root, project, subject, source=source)



from laplace.core import identity as core_identity, scoped as core_scoped  # noqa: E402
from laplace.writing import mutation_attribution  # noqa: E402  (cycle-safe: imported last)
from laplace.manuscript import proposal_currentness  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_reads  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_jobs  # noqa: E402  (cycle-safe: imported last)
