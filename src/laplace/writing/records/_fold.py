"""Derived session/turn folds; append and live execution remain upstream."""
from __future__ import annotations
import hashlib,json,threading
from pathlib import Path
from typing import Any,Mapping
from laplace.representation.writing_bodies import resolve_fields as resolve_custody_fields
_LOCK = threading.RLock()


_CACHE: dict[str, dict] = {}


_STORE = "contract/talk.jsonl"


def _seal_proposal_basis(turn:dict,record_id:str|None) -> dict:
    """Copy the inputs at this journal position, never later session baselines."""
    value={'context_id':turn.get('context_id'),
        'turn_basis_record_id':turn.get('context_basis_record_id') or turn.get('id')}
    value['read_ids']=list(dict.fromkeys(read.get('id') for read in (turn.get('tool_reads') or {}).values() if read.get('id')))
    value['read_receipts_sha256']=_read_basis_digest(turn.get('tool_reads') or {})
    return json.loads(json.dumps({'schema_version':'laplace.proposal-basis/1',
        'record_id':record_id,**value}))


def _read_basis_digest(reads:dict) -> str:
    return _proposal_digest([{**{key:read.get(key) for key in
        ('id','operation','payload','output_sha256','source_scope')},
        **({'consumption':read['consumption']} if 'consumption' in read else {})} for read in reads.values()])


def _project_proposal_basis(turn:dict,row:dict) -> dict:
    basis=row.get('proposal_basis') or _seal_proposal_basis(turn,row.get('id'))
    # Existing journal bodies are shared in memory. The persisted seal carries
    # receipt IDs and scoped dependency metadata, never copied read bodies.
    return {**basis,**{key:turn.get(key) for key in ('dependencies','document','selection')},
        'tool_reads':{key:read for key,read in (turn.get('tool_reads') or {}).items()
        if read.get('id') in set(basis.get('read_ids') or [])}}


def _candidate_version(proposal:dict,basis:dict) -> str:
    """Authored bytes plus immutable observed inputs identify one candidate."""
    return _proposal_digest({'proposal_content_sha256':_proposal_digest(proposal),
        'consumed_basis':{key:basis.get(key) for key in ('context_id','turn_basis_record_id','read_ids','read_receipts_sha256')}})


def _record_proposal_candidate(turn:dict,row:dict) -> None:
    proposal=row['proposal'];version=row.get('proposal_instance_version') or _proposal_digest(proposal)
    basis=_project_proposal_basis(turn,row)
    previous=(turn.get('proposal_bases') or {}).get(version)
    if previous and _candidate_version(proposal,previous)!=_candidate_version(proposal,basis):
        # Pre-instance legacy rows cannot distinguish renewed identical text.
        # Retain the old evidence and expose ambiguity; never renew authority.
        previous['ambiguous_legacy_basis']=True
    else:turn.setdefault('proposal_bases',{}).setdefault(version,basis)
    versions=turn.setdefault('proposal_versions',{})
    retained=versions.get(version)
    if (isinstance(retained,dict) and retained.get('schema_version')=='laplace.proposal-metadata/1'
            and proposal.get('schema_version')!='laplace.proposal-metadata/1'
            and _proposal_digest(proposal)==retained.get('content_sha256')):
        # A selected exact carrier may follow an earlier metadata-only carrier
        # of the same sealed instance. Promote only its verified body, keeping
        # that immutable instance/basis; identity projections cannot mask it.
        versions[version]=proposal
    else:versions.setdefault(version,proposal)


def _canonical_read_payload(operation: str, payload: Mapping[str, Any] | None) -> dict:
    """Identity-only normalization for equivalent historical read spellings."""
    value=dict(payload or {})
    if operation=="repository":
        # Repository read defines omitted offset as zero and omitted PDF
        # page_count as one. Keep the exact stored payload for replay/display,
        # but let a later equivalent call supersede its older spelling.
        if value.get("offset") in (None,0):value.pop("offset",None)
        if value.get("page_count") in (None,1):value.pop("page_count",None)
    return value


def _session_display_title(text):
    """Existing conversation catalogue display label; not an analytics content body."""
    return " ".join(str(text or "Conversation").split())[:90]


def _empty_projection(state: dict) -> None:
    state.update(offset=0, sessions={}, turns={}, orders={}, sequence=0,
                 artifact_records={}, artifact_ambiguities=set(), read_receipts={}, recovery_ambiguities=set())


def _records(root: Path) -> dict:
    """Index new journal suffixes once, not the entire history on each UI read.

    JOURNAL GENERATION (M5 S3): the projection is reused only for the journal generation it was folded from.
    The generation is the existing metadata index's own observation of this file (its device/inode, size,
    timestamps and fixed prefix windows; _index.MetadataIndex.advance mints a new generation object only on
    a reset), so a journal that disappeared, was replaced, truncated, or recreated at the same path with an
    equal or larger size is folded afresh, while an ordinary append keeps the same generation and reads only
    the new suffix. No second token or cache is kept here; a stale fold can never seal a new proposal basis.
    """
    from . import _index as metadata
    path = root / _STORE
    with _LOCK:
        state = _CACHE.setdefault(str(path), {"offset": 0, "sessions": {}, "turns": {},
                                                   "orders": {}, "sequence": 0,
                                                   "artifact_records": {},
                                                   "artifact_ambiguities": set(), "read_receipts": {}})
        # A live process may already hold the pre-artifact-index cache at EOF.
        # Rebuild that projection once; otherwise old ART receipts would remain
        # invisible until restart even though subsequent rows were indexed.
        if "artifact_records" not in state or "artifact_ambiguities" not in state or "read_receipts" not in state:
            _empty_projection(state)
        state.setdefault("orders",{});state.setdefault("sequence",0)
        if not path.exists():
            # a journal that disappeared leaves nothing to reuse: its old projection is not this root's state
            if state["offset"] or state["turns"] or state["sessions"]:_empty_projection(state)
            state["generation"]=None
            return state
        generation = metadata.index(root, _STORE)._generation
        if state.get("generation") is not generation or path.stat().st_size < state["offset"]:
            _empty_projection(state)
            state["generation"]=generation
        with path.open("rb") as stream:
            stream.seek(state["offset"])
            while True:
                before = stream.tell()
                line = stream.readline()
                if not line or not line.endswith(b"\n"):
                    state["offset"] = before
                    break
                state["offset"] = stream.tell()
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                _fold_record(state,row,root)
        return state


def _dispatch_records(root: Path, project: str, dispatch_id: str, *, read_context=None) -> tuple[dict, Any]:
    """One indexed metadata cut; exact dispatch children and required receipt fields.

    This read never enters the rich global fold. The existing index still pays
    its cold/suffix ledger scan, but proposal/context/action bodies outside the
    selected proof are neither resolved nor retained. Selection is request-local.
    """
    from . import _index as metadata
    root=Path(root).resolve();context={} if read_context is None else read_context
    key=('dispatch-metadata-cut',str(root),project)
    if key not in context:
        targets=context.get(('dispatch-work-scope',str(root),project),frozenset({dispatch_id}))
        context[key]=metadata._dispatch_metadata_cut(root,project,targets)
    idx=context[key]
    if dispatch_id not in idx.dispatch_ids:
        raise ValueError('Dispatch is outside this captured Work request; read a fresh selected scope.')
    admissions=list(idx.turns.values())
    state={'sessions':{},'turns':{},'orders':{},'sequence':0,
           'artifact_records':{},'artifact_ambiguities':set(),'read_receipts':{}}
    def unique(ident,kind):
        # THE canonical record-family resolution (B owner, records._index): legitimate writing-session versions
        # resolve to the current verified version; immutable duplicates, kind/project collisions and contradictory
        # session histories refuse. The ordered session/settings/binding fold below still applies every version.
        resolved=family(ident,kind)
        return None if resolved is None else resolved['meta']
    def family(ident,kind):
        # One canonical resolution returns the verified selected metadata and its detached verified raw row.
        try:return metadata.resolve_record_family(idx,project,ident,kind=kind)
        except metadata.AmbiguousRecord as error:
            raise ValueError('Selected dispatch '+kind+' identity is ambiguous.') from error
    checked=set()
    def checked_metadata(meta):
        if meta['_order'] not in checked:
            metadata._raw_indexed_record(idx,meta)
            checked.add(meta['_order'])
        return dict(meta)
    children=[row for row in admissions if row.get('dispatch_id')==dispatch_id]
    for child in children:
        if unique(child['id'],'writing-turn') is None:raise ValueError('Selected dispatch turn is unavailable.')
        sid=child.get('session_id');session=unique(sid,'writing-session')
        if session is None:raise ValueError('Selected dispatch session is unavailable.')
        session_rows=[row for row in idx.by_session.get(sid,()) if row['record'] in {'writing-session','writing-session-settings','writing-binding'}
                      and idx.project(row)==project]
        for row in session_rows:_fold_record(state,checked_metadata(row),root,resolve=False,order=row['_order'])
        _fold_record(state,checked_metadata(child),root,resolve=False,order=child['_order'])
        replies=[row for row in idx.by_turn.get(child['id'],()) if row['record']=='writing-reply' and idx.project(row)==project]
        for meta in replies:
            # Every consumed immutable reply passes THE canonical family rule (R1): a duplicate WR, or a WR colliding with
            # another kind in this project, refuses instead of letting the last folded row choose the settled status.
            if not meta.get('id') or unique(meta['id'],'writing-reply') is None:
                raise ValueError('Selected dispatch reply identity is unavailable.')
            raw=metadata._raw_indexed_record(idx,meta)
            # Only fields this projection consumes; no proposal/text/context CAS.
            row={key:raw[key] for key in ('id','record','project','turn_id','session_id','status','error','usage','ts') if key in raw}
            row=resolve_custody_fields(row,root,strict=True)
            _fold_record(state,row,root,resolve=False,order=meta['_order'])
    def lookup(receipt_id):
        if receipt_id in state['read_receipts']:return state
        resolved=family(receipt_id,'writing-tool-read')
        if resolved is None:return state
        meta=resolved['meta']
        actor=state['turns'].get(meta.get('turn_id'))
        if actor is None or actor.get('dispatch_id')!=dispatch_id:return state
        # The canonical family resolution already opened and verified this exact row on the captured cut, with its
        # supporting rows and identity checks. Consume that detached raw instead of opening the same row again.
        raw=resolved['raw']
        row={key:raw.get(key) for key in ('id','record','project','turn_id','operation','payload','output_sha256')}
        row=resolve_custody_fields(row,root,strict=True)
        state['read_receipts'][receipt_id]=row
        return state
    return state,lookup


def _fold_record(state, row, root, *, resolve=True, order=None):
    """The existing journal owner fold, also used by bounded selected-record reads."""
    if resolve:
        retained_raw=row.get("research_raw")
        row=resolve_custody_fields(row,root,strict=False)
        if row.get("record") in {"writing-tool-read","writing-tool-read-baseline"}:
            from laplace.core.bodies import is_reference
            if is_reference(retained_raw):
                # A warm hydrated dictionary proves content, not continued custody.
                # Preserve the original reference so every receipt-aware comparison
                # reopens the exact CAS body. Inline fallback remains genuinely inline.
                row["research_raw"]=retained_raw
    state["sequence"] += 1
    occurrence=order if order is not None else state['sequence']
    if row.get("id"):
        ident=str(row['id'])
        if ident in state['orders']:state.setdefault('recovery_ambiguities',set()).add(ident)
        state["orders"][ident]=occurrence
    kind = row.get("record")
    if kind in {'writing-tool-action','writing-tool-failure'}:
        # General orders intentionally retain latest-ID behavior for existing
        # consumers. Recovery instead needs the original immutable occurrence.
        row={**row,'_recovery_order':occurrence}
    if kind == "writing-artifact":
        key=(str(row.get("project") or ""),str(row.get("id") or ""))
        if all(key):
            metadata={field:row.get(field) for field in
                      ("id","project","path","artifact_path","scope","sha256","turn_id","ts","custody_degradation")
                      if row.get(field) is not None}
            if key in state["artifact_records"]:
                state["artifact_ambiguities"].add(key)
            else:
                state["artifact_records"][key]=metadata
    elif kind == "writing-session":
        state["sessions"][row["id"]] = row
    elif kind == "writing-session-import" and row.get("session_id") in state["sessions"]:
        saved = state["sessions"][row["session_id"]]
        saved.update(native_id=None, imported_history={
            "source_manifest_sha256": row.get("source_manifest_sha256"),
            "reason": "Imported project history; the next turn starts a new provider conversation."})
        saved.pop("tool_contract_digest", None)
        saved.pop("native_registration_signature", None)
        saved["pending_context"] = {"reason": "imported project history"}
    elif kind == "writing-session-settings" and row.get("session_id") in state["sessions"]:
        saved = state["sessions"][row["session_id"]]
        # `model_source` and `tier` are carried on every writing-session-settings
        # row a current door banks (`resolve_session_settings`'s return, spread
        # at the HTTP door `configure_session` and set explicitly in
        # `effort_as_sent`'s correction row) but were dropped HERE, so the ONE
        # row the three doors share kept the session-OPEN tier/source forever:
        # the session's live view never advanced past whatever new_session first
        # resolved, even after a provider/model change changed both. `if key in
        # row` keeps a pre-tier-defaults historical row (recorded before these two
        # keys existed) from folding a KeyError or a spurious None.
        saved.update({key: row[key] for key in
                     ("provider", "model", "effort", "settings_revision",
                      "model_source", "tier", "settings_provenance") if key in row})
        if row.get("provider_changed"):
            saved.update(native_id=None, pending_context={
                "reason": "provider changed", "previous_native_id": row.get("previous_native_id")})
    elif kind == "writing-binding" and row.get("session_id") in state["sessions"]:
        state["sessions"][row["session_id"]].update(native_id=row.get("native_id"),
            actual_model=row.get("model"))
        if row.get("tool_contract_digest"):
            state["sessions"][row["session_id"]]["tool_contract_digest"] = row["tool_contract_digest"]
        if row.get("native_registration_signature"):
            state["sessions"][row["session_id"]]["native_registration_signature"] = row["native_registration_signature"]
        if row.get("native_id"):
            state["sessions"][row["session_id"]].pop("pending_context", None)
            state["sessions"][row["session_id"]].pop("imported_history", None)
    elif kind == "writing-turn":
        state["turns"][row["id"]] = row
        saved_session = state["sessions"].get(row.get("session_id"))
        if saved_session is not None and not saved_session.get("title"):
            saved_session["title"] = _session_display_title(row.get("text"))
    elif kind in ("writing-reply", "writing-application", "writing-steer",
                  "writing-tool-read", "writing-tool-read-baseline", "writing-tool-action", "writing-proposal",
                  "writing-tool-failure", "writing-turn-context-baseline", "writing-proposal-decision", "writing-native-file-change", "writing-proposal-anchor",
                  "writing-author-update-delivery","writing-author-update-ack"):
        turn = state["turns"].get(row.get("turn_id"))
        if turn is None and kind == "writing-reply":
            # Old provider receipts accidentally used the provider's
            # native turn id. Sessions permit only one active turn;
            # recover its unmatched logical turn without rewriting history.
            candidates = [t for t in state["turns"].values()
                          if t.get("session_id") == row.get("session_id") and not t.get("reply")]
            if len(candidates) == 1:
                turn = candidates[0]
                row = {**row, "native_turn_id": row.get("turn_id"), "turn_id": turn["id"]}
        if turn is not None:
            if row.get("_custody_errors"):
                turn.setdefault("custody_errors",[]).extend(row["_custody_errors"])
            if kind == "writing-reply":
                if isinstance(row.get('proposal'),dict):
                    _record_proposal_candidate(turn,row)
                turn["reply"] = row
            elif kind == "writing-application":
                turn["application"] = row
                turn.setdefault("applications", []).append(row)
            elif kind == "writing-proposal-decision":
                turn.setdefault("proposal_decisions", []).append(row)
            elif kind == "writing-proposal-anchor":
                turn.setdefault('proposal_anchor_records',[]).append(row)
                turn.setdefault("proposal_anchors", {})[row["edit_id"]]=row["source_anchor"]
                version=row.get('proposal_version')
                if isinstance(version,str) and version:
                    turn.setdefault('proposal_anchors_by_version',{}).setdefault(version,{})[row['edit_id']]=row['source_anchor']
            elif kind == "writing-turn-context-baseline":
                turn['context_basis_record_id']=row.get('id')
                turn.update({key: row[key] for key in
                             ("context_id", "dependencies", "document", "consumed", "selection", "workspace_context", "science_context_digest", "context_parts") if key in row})
            elif kind in {"writing-tool-read", "writing-tool-read-baseline"}:
                if kind == "writing-tool-read" and row.get("id"):
                    if row['id'] in state['read_receipts']:
                        state['read_receipts'][row['id']]['ambiguous']=True
                    else:
                        state["read_receipts"][row["id"]] = {**{key:row.get(key) for key in
                            ("id","record","project","turn_id","operation","payload","output_sha256","ts")},
                            '_order':order if order is not None else state['sequence']}
                reads = [(row.get("payload") or {}, row.get("supersedes_read"))]
                reads.extend((alias.get("payload") or {}, alias.get("supersedes_read"))
                             for alias in row.get("payload_aliases") or []
                             if isinstance(alias, dict))
                for payload, supersedes in reads:
                    key = json.dumps([row["operation"],
                        _canonical_read_payload(str(row["operation"]),payload)],sort_keys=True)
                    projected = row if payload is row.get("payload") else {
                        **row, "payload": dict(payload),
                        "canonical_payload": dict(row.get("payload") or {}),
                        "supersedes_read": supersedes}
                    turn.setdefault("tool_reads", {})[key] = projected
            elif kind == "writing-tool-action":
                turn.setdefault("tool_actions", []).append(row)
            elif kind == "writing-tool-failure":
                turn.setdefault("tool_failures", []).append(row)
            elif kind == "writing-native-file-change":
                turn.setdefault("native_actions", []).append(row)
            elif kind == "writing-author-update-delivery":
                turn.setdefault("author_update_deliveries",[]).append(row)
            elif kind == "writing-author-update-ack":
                turn.setdefault("author_update_acks",{})[row["correction_id"]]=row
            elif kind == 'writing-proposal':
                turn['pending_proposal'] = row['proposal']
                turn['pending_proposal_version']=row.get('proposal_instance_version') or _proposal_digest(row['proposal'])
                _record_proposal_candidate(turn,row)
            else:
                turn.setdefault("steering", []).append(row)


def _proposal_digest(proposal: dict) -> str:
    from laplace.manuscript.manuscript_proposals import ProposalIdentity
    if isinstance(proposal,ProposalIdentity):return proposal["content_sha256"]
    return "sha256:" + hashlib.sha256(json.dumps(proposal, sort_keys=True, ensure_ascii=False,
                                                   separators=(",", ":")).encode()).hexdigest()



def _proposal_effect_digest(proposal: dict) -> str:
    """Identity of source effects, excluding a provider's narrative reply/reasons."""
    from laplace.manuscript.manuscript_proposals import ProposalIdentity
    if isinstance(proposal,ProposalIdentity):return proposal["effect_sha256"]
    edits = proposal.get("edits") if isinstance(proposal, dict) else None
    value = [{key: edit.get(key) for key in ("file", "line_start", "line_end", "before", "after")}
             for edit in edits if isinstance(edit, dict)] if isinstance(edits, list) else []
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                                   separators=(",", ":")).encode()).hexdigest()
