"""THE JOURNAL WRITE OWNER: how a writing row is banked (core consolidation, family 1).

``bank`` is the one append every writing owner uses: it validates and custody-encodes the row (``prepare_custody_row``),
seals a proposal's basis under ``proposal_write_lock`` and guards a context baseline under the turn's
``author_update_delivery_lock`` against a newer basis (``turn_context_basis``), then appends through ``journal.bank_row``.
The read side (index, exact rows, folds) is ``records._index``/``records._fold``; this module never imports a door,
a provider or the authoring facade. ``authoring_surface`` forwards these names outward for its remaining callers.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

from laplace.core import bodies as core_bodies
from laplace.core.records import journal
from laplace.representation import writing_bodies as bodies
from laplace.writing.records import _fold, _index
from laplace.core.identity import canonical_digest

#: one reentrant FileLock instance per checkout (publication) and per turn (update envelope); registries only
_APPLY_LOCKS: dict[str, object] = {}
_AUTHOR_UPDATE_LOCKS: dict[str, object] = {}


@contextmanager
def proposal_write_lock(root: Path):
    """Serialize saved-version publication and source decisions using one lock.

    Reuse the FileLock instance so banking a proposal from inside an apply
    transaction is reentrant, including the existing current-turn tool path.
    """
    from filelock import FileLock
    path = Path(root).resolve() / "contract" / ".writing-apply.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _fold._LOCK:
        lock = _APPLY_LOCKS.setdefault(str(path), FileLock(str(path)))
    # Never retain the global cache mutex while waiting for source or another
    # process. Publication still has its existing per-checkout FileLock owner.
    with lock:
        yield


@contextmanager
def author_update_delivery_lock(root: Path, turn_id: str):
    """Serialize selection and banking of one turn's update envelope.

    Native adapters can execute tools concurrently, and the stdio adapter can
    run in another process.  The journal append lock alone cannot make the
    preceding pending/attempted read atomic, so use a small per-turn lock for
    that complete decision.
    """
    from filelock import FileLock
    token = hashlib.sha256(str(turn_id).encode("utf-8")).hexdigest()[:20]
    path = Path(root).resolve() / "contract" / f".writing-author-updates-{token}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _AUTHOR_UPDATE_LOCKS.get(str(path))
    if lock is None:
        with _fold._LOCK:
            lock = _AUTHOR_UPDATE_LOCKS.setdefault(str(path), FileLock(str(path)))
    # The per-turn file lock, not the global cache mutex, spans preparation.
    # The global mutex protects only this existing registry's first creation.
    with lock:
        yield


def prepare_custody_row(root: Path, row: Mapping[str,Any]) -> dict:
    """Replace repeated large public bodies with verified Atlas custody handles."""
    core_bodies.validate_references(row)
    stored=dict(row);kind=str(stored.get("record") or "")
    from laplace.manuscript.manuscript_proposals import proposal_metadata, edit_metadata
    if kind in {'writing-turn','writing-turn-context-baseline'} and isinstance(stored.get('consumed'),dict) and isinstance(stored['consumed'].get('corrections'),list):
        stored['consumed_correction_ids']=[value for value in stored['consumed']['corrections'] if isinstance(value,str)]
    if kind in {"writing-proposal","writing-reply"} and isinstance(stored.get("proposal"),dict) and isinstance(stored["proposal"].get("edits"),list):
        stored["proposal_projection"] = proposal_metadata(stored["proposal"])
    if kind == "writing-application" and isinstance(stored.get("edits"),list):
        stored["edit_projection"] = [edit_metadata(edit) for edit in stored["edits"]]
    if kind=='writing-reply':
        from laplace.writing import operating as writing_operating
        writing_operating.validate_provider_metadata(stored)
        for field,projector in [('usage_facts',writing_operating.usage_facts_projection),
                                ('delivery_receipt',writing_operating.delivery_receipt_projection)]:
            value=stored.get(field)
            if isinstance(value,Mapping) and not core_bodies.is_reference(value):
                stored[field+'_projection']=projector(value)
    if kind=="writing-reply" and isinstance(stored.get("actions"),list):
        actions=stored.pop("actions");stored["actions_recorded_separately"]={
            "count":len(actions),"sha256":canonical_digest(actions)}
    return bodies._encode_row(root, stored)


def turn_context_basis(root: Path, project: str, turn_id: str) -> str:
    """Current context row identity from the existing indexed journal cut."""
    with _index._LOCK:
        idx=_index.index(root)
        rows=[row for row in idx.by_turn.get(turn_id,())
              if row['record']=='writing-turn-context-baseline' and idx.project(row)==project]
        return rows[-1]['id'] if rows else turn_id


def bank(root: Path, row: dict, *, expected_context_basis: str | None = None):
    if row.get('record') in {'writing-tool-read','writing-tool-action','writing-tool-failure'}:
        from laplace.writing import delivery
        invocation=delivery._invocation();holder=invocation.get('native') if invocation else None
        if holder and holder.source_admitted and holder.source_scope and row.get('turn_id')==holder.source_scope[2]:
            row={**row,'native_invocation_id':holder.native_invocation_id,'claim_id':holder.source_claim,
                 'commission_id':holder.source_attachment['commission_id'],
                 'allowance_revision':holder.source_attachment['allowance_revision']}

    # This existing per-turn delivery lock also owns baseline appends. Preparation
    # can release global admission while check+append remains coherent with ordinary
    # reads/native steering. Cached reentry does not reacquire the global mutex.
    if row.get('record')=='writing-turn-context-baseline' and row.get('turn_id'):
        with author_update_delivery_lock(root,str(row['turn_id'])):
            if expected_context_basis is not None and turn_context_basis(root,str(row.get('project') or ''),str(row['turn_id']))!=expected_context_basis:
                raise ValueError('The turn context changed during input preparation; newer attention was preserved.')
            stored=prepare_custody_row(root,row)
            return journal.bank_row(_fold._STORE,stored,root=root)

    (root / "contract").mkdir(parents=True, exist_ok=True)
    if row.get("record") in {"writing-proposal", "writing-reply"} and row.get('turn_id'):
        with proposal_write_lock(root):
            from laplace.writing import records as writing_records
            turn=writing_records.fold_records(root)['turns'].get(row.get('turn_id'))
            if isinstance(row.get('proposal'),dict) and turn:
                basis=_fold._seal_proposal_basis(turn,row.get('id'))
                if row['record']=='writing-reply' and row.get('project')==turn.get('project'):
                    emitted=row['proposal']
                    normalized={key:value for key,value in emitted.items() if key!='answer'}
                    basis_keys=('context_id','turn_basis_record_id','read_ids','read_receipts_sha256')
                    for version,candidate in reversed(list((turn.get('proposal_versions') or {}).items())):
                        previous=(turn.get('proposal_bases') or {}).get(version) or {}
                        if (normalized=={key:value for key,value in candidate.items() if key!='answer'}
                                and all(basis.get(key)==previous.get(key) for key in basis_keys)
                                and previous.get('record_id')
                                and version==_fold._candidate_version(candidate,previous)):
                            # A second transport carrier is not another authored candidate.
                            # Preserve its exact text and answer; only the proposal body uses
                            # the already-sealed identical edit/guard semantics. No old row changes.
                            row={**row,'proposal':candidate,'display_text':emitted.get('answer'),
                                 'proposal_carrier':{'kind':'terminal-repetition',
                                     'candidate_version':version,'candidate_record_id':previous['record_id'],
                                     'emitted_content_sha256':_fold._proposal_digest(emitted)}}
                            break
                row={**row,'proposal_basis':basis,
                    'proposal_instance_version':_fold._candidate_version(row['proposal'],basis),
                    'proposal_content_sha256':_fold._proposal_digest(row['proposal'])}
            stored=prepare_custody_row(root,row)
            return journal.bank_row(_fold._STORE, stored, root=root)
    stored=prepare_custody_row(root,row)
    return journal.bank_row(_fold._STORE, stored, root=root)
