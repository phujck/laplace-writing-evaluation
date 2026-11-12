"""Writing's body-custody POLICY over the core body mechanics (laplace.core.bodies).

Core owns the reference contract, codec, retention, bounded reads, resolution, the invocation-local budget and the
degradation diagnostic. This module decides only what is Writing's: which fields of which journal rows are bodies
(the tables below), the store they live in (Atlas BlobStore at contract/writing_bodies, through
laplace.representation.writing_representation), the explicit legacy fallback for a reference into another store, and how a
provider reply's metadata resolves (its outer body only, nested observation handles kept lazy). References are
stored before the journal append; failures retain exact inline data with bounded diagnostics. Strict reads refuse
unavailable/corrupt/unsupported references; tolerant reads retain evidence. Proposal sealing, producer metadata,
journal/fold/cache and jobs remain upstream. Importing this leaf selects no state or runtime.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from typing import Any, Mapping
from laplace.core import bodies as core_bodies

#: where Writing's bodies live, as a reference's ``store`` field names it (relative to the repository root)
STORE = "contract/writing_bodies"
_CUSTODY_MIN_BYTES = 8192
_CUSTODY_FIELDS = {
    "writing-tool-read": ("research_raw",),
    "writing-tool-read-baseline": ("research_raw",),
    "writing-turn": ("dependencies","consumed","orientation","queued_requests"),
    "writing-turn-context-baseline": ("dependencies","consumed"),
    "writing-proposal": ("proposal",),
    "writing-reply": ("proposal","provider_issues","usage_facts","delivery_receipt"),
    "writing-application": ("edits","receipts"),
    # `payload` is what makes a recorded write replayable (writing_tools.py banks it
    # beside `outcome`); it is also the biggest thing a write row can carry, so it is
    # bounded here by the same content-addressed body store as every other large field.
    "writing-tool-action": ("outcome","payload"),
    "writing-tool-failure": ("payload","error","recovery"),
    # THE WRITE-AHEAD ROW.  `before`/`after` are whole artifact texts: 13.6 MB of the
    # author's 46 MB talk ledger, 29.5 per cent, in 235 rows (measured
    # 2026-10-03, evidence/WRITING_CONSOLIDATION_2026-10-03/wave1/storage-latency/
    # probes/talk_census.py).  The write-ahead guarantee is unchanged because the body
    # is put in the store BEFORE the row that references it is appended, so a kill
    # between the two can only lose the reference, never the text.
    "writing-artifact": ("before","after"),
}
#: Fields banked by reference at ANY size, because the ROW itself must carry no part of
#: them.  A write's `payload` can hold the artifact text the author stored and a private
#: reason the provider gave (asserted by tests/test_writing_controller.py:1572: the
#: action row is a small, non-secret projection), while replaying that write needs the
#: request exactly.  A handle satisfies both: the row stays a projection, the request
#: stays recoverable, and two identical requests share one body.  `_CUSTODY_MIN_BYTES`
#: still governs every other field -- this is a declared invariant about two fields, not
#: a size rule anyone tunes.  `writing-tool-failure.payload` joined it in the whole
#: synthesis: it is the same request under a different outcome, and it is the field whose
#: BOUNDEDNESS the conformance gate reads per transport
#: (evidence/WRITING_CONSOLIDATION_2026-10-03/harness2/conformance.py:656), so a bound that
#: depended on the request's size answered that question differently on two rows of one
#: kind.  The hand-rolled 16,000-character truncation this replaces is deleted in
#: `writing_tools.bank_failure`.
_CUSTODY_ALWAYS = {("writing-tool-read","research_raw"),
                   ("writing-tool-read-baseline","research_raw"),
                   ("writing-tool-action", "payload"),
                   ("writing-tool-failure", "payload")}
#: Fields whose large LEAF values are themselves the unit of custody, so that ONE TEXT IS
#: ONE BODY.  A write's request carries the artifact text under `content` and the
#: write-ahead row carries the same text under `after`; both are custody fields, so until
#: this declaration one 40,001-character `store_artifact` put TWO bodies of the one text
#: under two digests -- 82,694 durable bytes against the base's 42,120, 1.96x, measured
#: 2026-10-03 (evidence/WRITING_CONSOLIDATION_2026-10-03/wave1/synth-context-storage/
#: probes/body_cost.py).  Substituting the leaf FIRST makes both references address the one
#: body the store already holds: `encode` of a text is the same bytes whichever
#: field the text arrived in, so the second reference writes nothing.  Only these two
#: fields are request-shaped containers of someone else's text; every other custody field
#: is still put whole, so no other row's shape moves.
_CUSTODY_LEAVES = {("writing-tool-action", "payload"), ("writing-tool-failure", "payload")}
#: ONE TEXT IS ONE BODY AT EVERY SIZE (WRITING-CONSOLIDATION-W1, the whole synthesis).
#: `_CUSTODY_LEAVES` above made the two references address one body only ABOVE
#: `_CUSTODY_MIN_BYTES`; below it BOTH stayed inline and the write's text was durably
#: stored twice -- 1.71x for a 4,000-character write and 1.83x at 8,000, against 1.019x at
#: 40,000 (measured on the merged head, evidence/WRITING_CONSOLIDATION_2026-10-03/wave1/
#: synth-whole/body_cost_by_size.before.log; 72 of the author's 235 write-ahead rows, 30.6
#: per cent, hold an `after` under it).  The text appears at exactly these coordinates:
#: the write-ahead row's two fields, and the named leaves of the replayable request.  They
#: are substituted by the one rule that is not a size knob -- WHENEVER THE REFERENCE IS
#: SMALLER THAN THE TEXT IT REPLACES.  Below that size a second copy is the cheaper durable
#: representation of the two, so what duplication remains is bounded by the size of a
#: reference and the row is never larger than it would be with one.
_CUSTODY_TEXT_FIELDS = {("writing-artifact","before"), ("writing-artifact","after")}
_CUSTODY_TEXT_LEAVES = {("writing-tool-action","payload"): ("content","before","after"),
                        ("writing-tool-failure","payload"): ("content","before","after")}

#: The size of one custody reference, COMPUTED from the schema it writes rather than
#: chosen, so that "is a handle worth writing here?" has an answer no one tunes.
_CUSTODY_REFERENCE_BYTES = core_bodies.reference_bytes(STORE)


def store(root: Path):
    """The repository's body store: writing.representation.body_store, the one Writing entry to Atlas custody."""
    from laplace.representation import writing_representation as representation
    return representation.body_store(root)


def _put(root: Path):
    return lambda raw: store(root).put(raw)


def retain_leaves(root: Path, value: Any, texts: tuple[str,...] = (), key: str | None = None,
                    *, diagnostic=None) -> Any:
    """Put every large leaf of a request in Writing's body store (core.bodies.retain_leaves under this policy).

    Walking the container first means the artifact text a write asked for addresses the SAME body as the
    write-ahead row's `after`; `texts` names the leaves that ARE that artifact text (`_CUSTODY_TEXT_LEAVES`).
    """
    return core_bodies.retain_leaves(_put(root), STORE, value, texts, key, min_bytes=_CUSTODY_MIN_BYTES,
                                     diagnostic=diagnostic)


def prepare_row(root: Path, row: Mapping[str,Any]) -> dict:
    """Validate and retain a row; producer metadata decoration remains upstream."""
    core_bodies.validate_references(row)
    return _encode_row(root, row)


def _encode_row(root: Path, row: Mapping[str,Any]) -> dict:
    """Retain a row already version-checked by the producer preparation seam."""
    stored=dict(row);kind=str(stored.get("record") or "")
    diagnostic = core_bodies.degradation()
    action_context = (kind == 'writing-turn' and isinstance(stored.get('workspace_context'), Mapping)
                      and 'workflow_action' in stored['workspace_context'])
    # One exact admitted snapshot, at every size. Ordinary contexts retain their
    # existing row shape; summaries/indexes do not hydrate this action body.
    fields = (*_CUSTODY_FIELDS.get(kind,()), *(('workspace_context',) if action_context else ()))
    for field in fields:
        value=stored.get(field)
        if value is None or isinstance(value,Mapping) and value.get("schema_version")==core_bodies.REFERENCE_SCHEMA:continue
        if (kind,field) in _CUSTODY_LEAVES:
            value=stored[field]=retain_leaves(root,value,_CUSTODY_TEXT_LEAVES.get((kind,field),()),diagnostic=diagnostic)
        raw=core_bodies.encode(value)
        floor=_CUSTODY_REFERENCE_BYTES if (kind,field) in _CUSTODY_TEXT_FIELDS else _CUSTODY_MIN_BYTES
        if len(raw)<=floor and (kind,field) not in _CUSTODY_ALWAYS and not (action_context and field == 'workspace_context'):continue
        held=core_bodies.retain(_put(root),STORE,raw,diagnostic)
        if held is not None:   # else the full inline body is the fail-safe durable representation
            stored[field]=held
    # Final action receipt describes the whole invocation; other rows describe
    # their own fallback. Both are small observations, without failing payloads.
    if kind == "writing-tool-action" and core_bodies.current_operation() is not None:
        diagnostic = core_bodies.current_operation()
    if diagnostic["failed_attempts"]:
        stored["custody_degradation"] = json.loads(json.dumps(diagnostic))
    return stored


def _legacy(handle: str) -> bytes:
    from laplace.representation import writing_representation as representation
    return representation.legacy_custody_body(handle)   # the explicit legacy nonlocal read, through the entry


def read_bytes(value: Mapping[str,Any], root: Path | None) -> bytes:
    """One Writing body reference's exact bytes: this repository's store, else the explicit legacy fallback."""
    return core_bodies.read_bytes(value, (lambda: store(root)) if root is not None else None, store=STORE,
                                  fallback=_legacy, local_required="repository root is required for writing body custody")


def resolve_value(value: Any, root: Path | None, errors: list, field: str) -> Any:
    """Resolve handles at EVERY depth, because the large leaf is a unit of custody.

    `_CUSTODY_LEAVES` puts a request's own large text in the store before the field that
    contains it, so a resolved `payload` can still hold a handle one level down.  A reader
    that resolved only the top level would hand a replay the handle instead of the text,
    which is the one thing the field exists for.
    """
    return core_bodies.resolve(value, lambda ref: read_bytes(ref, root), errors, field)


def resolve_fields(row: Mapping[str,Any], root: Path | None = None, *, strict: bool = True) -> dict:
    resolved=dict(row);errors=[];kind=str(resolved.get("record") or "")
    for field,value in list(resolved.items()):
        reader_control = (
            kind=='writing-reader-input' and field=='input'
            or kind in {'writing-session','writing-turn','writing-reader-refusal'} and field=='reader_profile'
            or kind=='writing-reader-refusal' and field=='reader_refusal'
            or kind=='writing-turn' and isinstance(row.get('reader_profile'),Mapping)
               and row['reader_profile'].get('profile')=='laplace.sealed-text-reader/1'
               and field in {'consumed','dependencies'})
        if reader_control:
            try:
                # These are custody/continuation identities. Resolve only an
                # outer metadata wrapper, never the selected input it names.
                if core_bodies.is_reference(value) and not (kind=='writing-reader-input' and field=='input'):
                    value=json.loads(read_bytes(value,root))
                core_bodies.validate_references(value)
                resolved[field]=copy.deepcopy(value)
            except core_bodies.BudgetExceeded:raise
            except Exception as error:errors.append({'field':field,'error':str(error)})
        elif kind=='writing-reply' and field in ('usage_facts','delivery_receipt','usage_facts_projection','delivery_receipt_projection'):
            try:
                # Metadata contains typed observation references, not replay text leaves.
                # Resolve its outer body only, preserving exact nested handles for lazy reads.
                if core_bodies.is_reference(value):value=json.loads(read_bytes(value,root))
                core_bodies.validate_references(value)
                resolved[field]=value
            except core_bodies.BudgetExceeded:raise
            except Exception as error:errors.append({'field':field,'error':str(error)})
        elif isinstance(value,(Mapping,list)):
            resolved[field]=resolve_value(value,root,errors,field)
    if kind=='writing-reply':
        from laplace.writing import operating as writing_operating
        try:writing_operating.validate_provider_metadata(resolved)
        except ValueError as error:
            errors.append({'field':'provider_metadata','error':str(error)})
            # The raw ledger stays intact. Unsupported metadata is never interpreted
            # as current counts or parity by a tolerant history projection.
            for field in ('usage_facts','delivery_receipt','usage_facts_projection','delivery_receipt_projection'):
                resolved.pop(field,None)
    if errors:
        if strict:raise ValueError("Saved writing body is unavailable, corrupt or unsupported: "+"; ".join(row["field"]+": "+row["error"] for row in errors))
        resolved["_custody_errors"]=errors
    return resolved
