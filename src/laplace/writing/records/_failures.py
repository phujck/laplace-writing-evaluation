"""Selected saved-turn failure evidence over the existing journal index.

This request-local carrier is interpreted by session_reads' unchanged failure
policy. It never enters the rich fold/cache or hydrates action text leaves.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path

from laplace.core import bodies
from laplace.core.records import capture
from laplace.representation import writing_bodies
from . import _index
from ._fold import _fold_record


def _outer(root, value):
    """Decode required wrappers only; unavailable wrappers stay unavailable."""
    seen=set()
    while bodies.is_reference(value):
        key=(value.get('store'),value.get('content_handle'))
        if key in seen:return value
        seen.add(key)
        try:value=json.loads(writing_bodies.read_bytes(value,root))
        except bodies.BudgetExceeded:raise
        except Exception:return value
    return value


def _action(root, row):
    """Only the closed fields used by the existing related-action join."""
    result={key:copy.deepcopy(row[key]) for key in
        ('id','project','turn_id','operation','tool_name','tool_use_id','ts') if key in row}
    if 'error' in row:result['error']=_outer(root,row['error'])
    payload=_outer(root,row.get('payload'))
    result['payload']={}
    if isinstance(payload,Mapping):
        for key in ('file','node','id','key','path','run_id','url'):
            if key in payload:result['payload'][key]=_outer(root,payload[key])
        edits=_outer(root,payload.get('edits'))
        if isinstance(edits,list):
            result['payload']['edits']=[]
            for edit in edits:
                edit=_outer(root,edit)
                if isinstance(edit,Mapping):
                    result['payload']['edits'].append({key:_outer(root,edit[key])
                        for key in ('file','line_start','line_end') if key in edit})
    outcome=_outer(root,row.get('outcome'))
    result['outcome']=({key:_outer(root,outcome[key]) for key in ('ok','status') if key in outcome}
                       if isinstance(outcome,Mapping) else {})
    return result


def selected_failure_records(root:Path, project:str, ident:str) -> dict:
    """Verify and detach one selected turn's evidence at one current upper cut."""
    root=Path(root).resolve()
    with _index._LOCK:
        idx=_index.index(root);generation=idx._generation;upper=idx.order;end=idx.offset
        def original(key,kind):
            # THE canonical record-family resolution (B owner): legitimate writing-session versions resolve to the
            # current verified version; contradictions, kind/project collisions and immutable duplicates refuse.
            try:resolved=_index.resolve_record_family(idx,project,key,kind=kind)
            except _index.AmbiguousRecord as error:
                raise ValueError('The selected failure turn/session identity is missing or ambiguous.') from error
            if resolved is None and kind=='writing-turn':raise ValueError('Unknown writing turn.')
            # Immutable identities keep this reader's original fence: exactly one journal row in every project.
            if resolved is None or kind!=_index.SESSION_FAMILY and idx.journal_id_counts[str(key)]!=1:
                raise ValueError('The selected failure turn/session identity is missing or ambiguous.')
            return resolved['meta'],resolved['raw']
        turn_meta,turn=original(ident,'writing-turn')
        if turn.get('project')!=project:raise ValueError('Unknown writing turn.')
        sid=turn.get('session_id')
        _,session=original(sid,'writing-session')
        if session.get('project') not in (None,'',project):
            raise ValueError('The supporting journal row belongs to another project.')

        # Metadata-only actor chronology preserves the historical native-turn
        # reply fallback. A direct reply wins exactly where the rich fold would
        # assign it; only that final reply's provider issues need body custody.
        actor_rows={row['_order']:row for row in idx.by_session.get(sid,())
                    if row['record'] in {'writing-turn','writing-reply'}}
        for actor in list(actor_rows.values()):
            if actor['record']=='writing-turn':
                actor_rows.update({row['_order']:row for row in idx.by_turn.get(actor['id'],())
                                   if row['record']=='writing-reply'})
        actors={'sequence':0,'orders':{},'sessions':{},'turns':{},'read_receipts':{}}
        for meta in sorted(actor_rows.values(),key=lambda row:row['_order']):
            if meta['record']=='writing-reply' and meta.get('turn_id') not in actors['turns']:
                # A real earlier turn in another session is not the legacy
                # unmatched-native-ID fallback, even when this session has one.
                if any(row['record']=='writing-turn' and row['_order']<meta['_order']
                       for row in idx.by_id.get(meta.get('turn_id'),())):continue
            _fold_record(actors,copy.deepcopy(meta),root,resolve=False,order=meta['_order'])
        reply=(actors['turns'].get(ident) or {}).get('reply')
        source={key:turn.get(key) for key in ('id','project','session_id')}
        source.update(tool_failures=[],tool_actions=[],reply={})
        if reply:
            raw=_index._raw_indexed_record(idx,reply)
            # Validate the original actor rows influencing fallback selection,
            # without resolving their requests, replies or context bodies.
            for meta in actor_rows.values():_index._raw_indexed_record(idx,meta)
            projected=writing_bodies.resolve_fields({'provider_issues':raw.get('provider_issues')},root,strict=False)
            source['reply']={'provider_issues':projected.get('provider_issues')}
        state={'turns':{ident:source},'sessions':{sid:session},'orders':{},'read_receipts':{},
               'recovery_ambiguities':{key for key,count in idx.journal_id_counts.items() if count>1}}
        selected=[meta for meta in idx.by_turn.get(ident,())
                  if turn_meta['_order']<meta['_order']<=upper
                  and meta['record'] in {'writing-tool-failure','writing-tool-action','writing-tool-read'}]
        # Action/read bodies serve only a failure join. No failure means no join.
        has_failures=bool(source['reply'].get('provider_issues')) or any(
            meta['record']=='writing-tool-failure' for meta in selected)
        for meta in selected:
            kind=meta['record']
            if not has_failures and kind!='writing-tool-failure':continue
            raw=_index._raw_indexed_record(idx,meta)
            if kind=='writing-tool-failure':
                row=writing_bodies.resolve_fields(raw,root,strict=False)
                source['tool_failures'].append({**row,'_recovery_order':meta['_order']})
            elif kind=='writing-tool-action':
                if raw.get('project')!=project:continue
                source['tool_actions'].append({**_action(root,raw),'_recovery_order':meta['_order']})
            elif raw.get('id') and raw['id'] not in state['read_receipts']:
                if raw.get('project')!=project:continue
                row=writing_bodies.resolve_fields({key:raw.get(key) for key in
                    ('id','record','project','turn_id','operation','payload','output_sha256','ts')},root,strict=False)
                state['read_receipts'][row['id']]={**row,'_order':meta['_order']}
        # The index's own generation detection owns replacement/truncation. A
        # concurrent append may advance it, but this carrier retains its upper
        # cut and detached ambiguity/order facts, never those newer rows.
        idx.advance()
        if idx._generation is not generation or idx.source_status!='AVAILABLE' or idx.offset<end:
            _index._invalidate_index_cut(idx)
            raise capture.CapturedRowChanged('The selected failure journal cut changed; read it again.')
        return state
