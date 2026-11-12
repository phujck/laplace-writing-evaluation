"""Project-scoped operations shared by live Codex tools and Claude's local MCP.

The model calls the same canonical producers as the scanner UI. Deployed operation
contracts describe exact inputs, role permissions, effects and recovery.
"""
from __future__ import annotations

from laplace.core import bodies as core_bodies
from laplace.writing import records as writing_records
# THE OWNERS THIS GATEWAY CONSUMES (core consolidation, family 2): the read contract and the one operation table, under
# their old names here for the gateway's own callers; neither owner imports this module.
from laplace.writing import operations as _operations, reads   # reads: the one action-level `effect` classification
from laplace.writing.reads import READS, WRITES, output_digest, read_output_digest, read_basis_index, stale_evidence_families, ACTION_VIEWS as _ACTION_VIEWS
from laplace.writing.operations import OwnerError, _read_extras, replay_read

import argparse
import hashlib
import contextlib
import json
from pathlib import Path
import sys
import uuid
from urllib.parse import urlencode

# Dynamic tools receive only a compact catalogue.  ``help`` carries the exact
# contract for one action, avoiding a whole-manual prompt injection per turn.
DESCRIPTION = ("Operate on this selected research project through canonical owners. "
               "One tool accepts either the six-key semantic request "
               "{verb,concept,target,expected,payload,by} or legacy {operation,payload}. "
               "Start with {operation:help,payload:{}} for concepts, then help with "
               "{concept:<returned concept>} and {operation:<returned operation>}. "
               "Exact help offers action.native.native_request when the existing resolver proves the route; "
               "use help context for exact returned identifiers, fill placeholders and use current expected tokens. "
               "Some legacy operations remain shim-only; use their exact help. "
               "Empty task or note calls are writes. Read source with returned file paths. "
               "Identity and role guards apply to both spellings.")
from laplace.core import grammar as _grammar
INPUT_SCHEMA = {"type": "object", "properties": {
    "operation": {"type": "string", "enum": sorted(READS | WRITES)},
    "verb": {"type": "string", "enum": list(_grammar.VERBS)},
    "concept": {"type": "string"}, "target": {"type": "string"},
    "expected": {"type": "array", "items": {"type": "string"}},
    "payload": {"type": "object", "additionalProperties": True},
    "by": {"type": "string", "description":"Requested attribution of a semantic request only; durably bounded on receipts, not actual actor or permission. Named payload.by remains declared owner data; the semantic codec carries that field as payload.owner_by."},
}, "oneOf": [
    {"required": ["operation", "payload"],
     "not": {"anyOf": [{"required": [key]} for key in
                        ("verb", "concept", "target", "expected", "by")]}},
    {"required": list(_grammar.Request.FIXED), "not": {"required": ["operation"]}},
], "additionalProperties": False}


def _effect_error_details(error):
    # Provider permission-denial receipts carry authored reason strings. They
    # have no exception cause chain or partial owner mutation to reconstruct.
    if not isinstance(error,BaseException):return {}
    from laplace.pipeline.workflow_definitions import native_error_details
    from laplace.manuscript.source_effects import error_details
    from laplace.manuscript.storyboard import plan_failure_details
    from laplace.writing.prepared_work import error_details as preparation_error_details
    from laplace.manuscript.build_targets import error_details as build_target_error_details
    from laplace.manuscript.build_jobs import error_details as build_job_error_details
    from laplace.manuscript.document_templates import error_details as template_error_details
    from laplace.writing.sealed_reader import error_details as reader_error_details
    from laplace.writing.session_reads import message_refusal_details
    from laplace.research.literature import retained_import_error_details, retained_import_disposition
    from laplace.writing.session_settings import error_details as settings_error_details
    return {**native_error_details(error), **plan_failure_details(error), **error_details(error), **preparation_error_details(error),
            **build_target_error_details(error), **build_job_error_details(error), **template_error_details(error),
            **reader_error_details(error), **message_refusal_details(error), **retained_import_error_details(error),
            **(retained_import_disposition(error.details) if isinstance(error,OwnerError) else {}), **settings_error_details(error)}


def specification() -> dict:
    return {"type": "function", "name": "laplace_project", "description": DESCRIPTION,
            "inputSchema": INPUT_SCHEMA}


def _native_entry(root, project, turn_id, intent, fn, incoming=None):
    from laplace.writing import delivery, source_execution
    from laplace.native.declarations import PayloadAdmissionError
    if incoming is None and delivery._invocation() is None and source_execution.for_turn(root,project,turn_id) is None:
        return fn()  # Preserve legacy direct request/execute delivery semantics.
    with delivery.invocation(incoming=incoming) as invocation:
        holder = invocation['native']; outer = holder.depth == 0
        holder.depth += 1
        admitted_here=False
        try:
            if outer:source_execution.claim_native(root, project, turn_id, holder, intent)
            admitted_here=True
            result = fn()
        except BaseException as error:
            if outer and admitted_here:
                source_execution.settle_native(root, holder, 'SETTLED_REFUSAL' if isinstance(error,(PayloadAdmissionError,source_execution.AllowanceRefused)) else 'SETTLED_ERROR')
            raise delivery.carry(error, invocation)
        finally:
            holder.depth -= 1
        if outer:
            source_execution.settle_native(root, holder, 'SETTLED_SUCCESS')
            if holder.source_attachment:
                result = {**result, 'source_allowance': source_execution.status(root, holder.source_attachment)}
                result = delivery.admit(result, (invocation['act'] or {}).get('profile'))
        return result


def call(root: Path, project: str, mode: str, fields: dict,
         turn_id: str | None = None, *, _incoming=None) -> dict:
    return _native_entry(root,project,turn_id,fields,
        lambda: _call_public_impl(root,project,mode,fields,turn_id),_incoming)


def _call_public_impl(root: Path, project: str, mode: str, fields: dict,
         turn_id: str | None = None) -> dict:
    """Both native transports consume the offered shape through the existing owners."""
    if turn_id:
        from laplace.writing.sealed_reader import require_not_reader
        require_not_reader(root,turn_id=turn_id)
    from jsonschema import Draft202012Validator
    error = next(Draft202012Validator(INPUT_SCHEMA).iter_errors(fields), None)
    if error is not None:
        from laplace.native.declarations import PayloadAdmissionError
        raise PayloadAdmissionError(str(fields.get("operation") or "") if isinstance(fields,dict) else "",
            "project tool arguments do not match the offered contract: " + error.message,
            requested_by=fields.get("by", "") if isinstance(fields,dict) and isinstance(fields.get("by", ""),str) else "")
    from laplace.writing import delivery
    with delivery.invocation() as invocation:
        try:
            return _call(root, project, mode, fields, turn_id, invocation)
        except Exception as error:
            # an ordinary owner exception leaves with the admitted act, so the transport's tool_failure finishes it
            raise delivery.carry(error, invocation)


def _call(root, project, mode, fields, turn_id, invocation):
    """One native call inside its delivery invocation (writing.delivery, step 0): both spellings reach the one dispatch,
    which records the admitted act; its profile carries the final policy through the additions and the admission."""
    from laplace.writing import delivery
    if "operation" in fields:
        result=execute(root, project, mode, fields["operation"], fields["payload"],turn_id=turn_id)
    else: result=request(root, project, mode, fields, turn_id=turn_id)
    if 'operation' in fields and result.get('schema_version')=='laplace.paragraph-restructure/1':
        from laplace.manuscript.reader_restructure import native_projection
        result=native_projection(result,fields['payload'],fields['payload'].get('read_id') or (result.get('read_receipt') or {}).get('id'))
    if result.get('schema_version')=='laplace.document-template-candidate/1':
        from laplace.manuscript.document_templates import native_projection
        result=native_projection(result)
    elif isinstance(result.get('owner_response'),dict) and result['owner_response'].get('schema_version')=='laplace.document-template-candidate/1':
        from laplace.manuscript.document_templates import native_projection
        result={**result,'owner_response':native_projection(result['owner_response'])}
    # the complete result after every addition passes the one final admission with the ACT's profile (step 5)
    bound=(invocation['act'] or {}).get('profile')
    return delivery.admit(_with_project_updates(root,project,turn_id,result,fields,bound=bound),bound)


def _with_project_updates(root,project,turn_id,result,fields=None,*,bound=None):
    if not turn_id or not isinstance(result,dict):return result
    from laplace.writing import delivery
    try:return _project_updates(root,project,turn_id,result,fields,**({'bound':bound} if bound else {}))
    except (ValueError,OSError) as error:
        return {**result,'update_delivery_unavailable':{'error':delivery.bounded_text(error),
            'basis':'Original tool outcome retained; no update delivery or acknowledgement inferred.'}}


def _project_updates(root,project,turn_id,result,fields=None,*,bound=None):
    """Construct prepared input publication; exact reading is a separate observation. In a bounded delivery each
    addition is decided before its effects (writing.delivery, step 3): author-update bodies that do not fit are offered
    as the owner's author_notice, the input publication is qualified by the space guard of turn_input_offer, and both
    offer only what the invocation's plan cut as eligible; a boundary without a plan (a refusal through tool_failure)
    offers freely under the same fits."""
    if not turn_id or not isinstance(result,dict):return result
    from laplace.writing import provider_updates
    from laplace.writing.provider_updates import turn_input_offer, acknowledge_turn_input
    from laplace.writing import delivery
    fields=fields or {};operation=fields.get('operation') or (result.get('owner') or {}).get('operation')
    value=result.get('owner_response',result)
    if not result.get('refused') and not result.get('ok') is False:
        if operation=='author_history':
            item=value.get('item') or value.get('record')
            if isinstance(item,dict) and item.get('id') and value.get('project')==project and isinstance(item.get('text'),str) and not item.get('text_truncated') and not item.get('_custody_errors'):
                provider_updates.acknowledge(root,project,turn_id,item['id'])
        if operation=='conversation_history':
            for row in value.get('items',[]):
                if row.get('control_id') and isinstance(row.get('payload'),dict):
                    read=acknowledge_turn_input(root,project,turn_id,row['control_id'])
                    if read:result={**result,'turn_input_read':read}
    # Preserve an already-constructed exact-read outcome if later publication fails.
    # A maintenance failure must not discard the message whose basis was advanced.
    cut=delivery.cut();reserved=delivery.reserved()
    # the reserved forms of the additions not yet decided; the input commits first (its effects are the turn's context
    # and frontier), then the author bodies are offered in what is left
    later=(reserved if reserved is not None else
           {'turn_input':provider_updates.pending_input_notice(root,project,turn_id)} if bound else {})
    for field,producer in [('turn_input',turn_input_offer),
                           ('author_updates',provider_updates.author_offer)]:
        try:
            eligible={'eligible':cut[field]} if cut is not None else {}
            if bound and field=='turn_input':
                offer=producer(root,project,turn_id,fits=lambda candidate,result=result:delivery.fits(result,field,candidate,bound,later),**eligible)
            else:
                offer=producer(root,project,turn_id,**eligible)
            if bound and field=='author_updates' and offer and not delivery.fits(result,field,offer,bound,later):
                offer=provider_updates.author_notice(offer)
            if offer:result={**result,field:offer}
            delivery.settle(field)
        except Exception as error:
            result={**result,'update_delivery_unavailable':_unavailable_answer(error,field)}
    return result


def _unavailable_answer(error,stage):
    """The bounded answer when an update producer fails: the exact outcome stays, nothing is inferred."""
    from laplace.writing import delivery
    return {'error':delivery.bounded_text(error),'stage':stage,
            'basis':'Existing tool/read outcome retained; no failed publication inferred.'}


# Compatibility names delegate to the one artifact owner; no path or custody policy lives here.


def help_response(root: Path, project: str, mode: str, payload: dict, *, turn_id=None) -> dict:
    """One current help validator/renderer, shared by native and human reads."""
    from laplace.native import declarations as writing_declarations
    if mode not in {"work", "review", "revise", "discuss"}:
        raise ValueError("Unknown writing role")
    if "project" in payload and payload["project"] != project:
        raise ValueError("Help project conflicts with its bound project")
    writing_declarations.validate_help_request(payload)
    # One help response, generated from the operation's own declaration, with this
    # project's live tokens in `expected`.  Two things this route used to do are
    # gone: `requested_payload_contract` returned the owner's schema a SECOND time
    # beside the copy inside `action` (75.3 per cent of help structure_change), and
    # a bare `help` fell back to the whole catalogue of 73 summaries, 13,194
    # characters, with no altitude between the required keys and everything
    # (evidence/WRITING_FRICTION_2026-10-01/wave1/context-economy.md, finding 4).
    from laplace.native import declarations as writing_declarations
    from laplace.writing import operating as writing_operating
    requested = payload.get("operation")
    if requested and requested not in READS | WRITES:
        raise ValueError("Unknown operation; help lists the deployed operations.")
    contract = writing_operating.tool_contract()
    scoped=None
    if mode=='review' and turn_id and (requested in {None,'store_artifact'} or payload.get('concept')=='artifact@project'):
        from laplace.writing.dispatch_returns import child_permission
        actor=writing_records.index(root).turns.get(turn_id) or {}
        if actor.get('dispatch_id'):scoped=child_permission(root,project,actor['session_id'],actor['dispatch_id'],turn_id=turn_id)
    permissions=set(contract['role_permissions'][mode])|({'store_artifact'} if scoped else set())
    route = payload.get("route")
    if route:
        return {"schema_version": writing_operating.VERSION, "digest": contract["digest"],
                "door": "http", "action": writing_declarations.http_help(
                    str(route), str(payload.get("method") or ""),
                    str(payload.get("http_operation") or ""))}
    if payload.get("door") == "http":
        return {"schema_version": writing_operating.VERSION, "digest": contract["digest"],
                "door": "http", "routes": writing_declarations.http_catalogue()}
    if requested:
        detail = writing_declarations.help_payload(
            requested, permitted=requested in permissions,
            project=project, root=root, variant=payload.get("variant"),
            payload=payload.get("context"), section=payload.get("section"))
        if payload.get("section"):   # one exact section (D2): no default-only additions below
            return {"schema_version": writing_operating.VERSION, "digest": contract["digest"],
                    "requested_operation": requested, "action": detail}
        if requested in {'dispatch_status','session_settings'}:
            detail={**detail,'direct_native':{'available':True,'arguments':{'operation':requested,
                'payload':payload.get('context') or detail.get('example') or {}}}}
        if scoped and requested=='store_artifact':
            from laplace.writing.dispatch_returns import publication_projection
            detail={**detail,**publication_projection(scoped),'example':scoped['payload']}
        if requested=='dispatch_status' and turn_id and (payload.get('context') or {}).get('id'):
            from laplace.work import project_work
            from laplace.writing import dispatch_parent
            task=project_work._tasks(project,root).get(payload['context']['id'])
            if task:
                selected=(payload.get('context') or {}).get('view','status')
                observed=dispatch_parent.native_status(task,project,root,turn_id=turn_id,selected=selected)
                detail={**detail,('return_schema' if selected=='return-schema' else 'return_contract'):
                    observed if selected=='return-schema' else observed.get('parent_return_contract')}
        return {"schema_version": writing_operating.VERSION, "digest": contract["digest"],
                "requested_operation": requested, "action": detail}
    # THE ALTITUDE between one act and all 73, said once in help_index: `help {concept}`
    # generates that concept's rows and a bare `help` says which concepts exist.
    return {"schema_version": writing_operating.VERSION, "digest": contract["digest"],
            "exact_actions_digest": contract["exact_actions_digest"],
            **writing_declarations.help_index(permissions,
                                              str(payload.get("concept") or ""),project=project),
            "acts_source": ("src/laplace/native/verbs.py ROUTES, generated from "
                            "tests/grammar_spec/mapping.csv and "
                            "tools/writing_verbs/http_routes.csv"),
            "http_door": {"operation": "help", "payload": {"door": "http"}},
            "read_one": {"operation": "help", "payload": {"operation": "<from one concept catalogue>"}}}


from laplace.native.declarations import interface_projection as _interface_projection  # noqa: E402
_operations.set_help_renderer(help_response, interface=_interface_projection)   # the door's contract renderings, injected into the operation table


# Capture possible source setup before binding, but refresh only actual owner effects.

def _action_summary(project: str, operation: str, payload: dict, result: dict) -> dict:
    """Small, non-secret projection of one producer's actual returned outcome."""
    identities, paths, revisions = [], [], {}

    def identity(value):
        if isinstance(value, (str, int)) and str(value):
            bounded = str(value)[:300]
            if bounded not in identities:
                identities.append(bounded)

    def path(value):
        if isinstance(value, str) and value and len(value) <= 1000 and value not in paths:
            paths.append(value)

    # Inspect targets are semantic objects first; receipt IDs remain audit data.
    for key in ("node", "source", "target", "task_id", "concept_id", "result_id", "figure_id", "declaration"):
        identity(payload.get(key))
    receipts=[]
    # A producer's top-level id is often the affected semantic artifact (for
    # example a style preview), even when it also doubles as its receipt handle.
    # Keep it inspectable in identities while the dedicated receipts field
    # preserves the newer receipt/semantic distinction.
    identity(result.get("id"))
    for key in ("id", "record_id", "receipt_id"):
        if result.get(key): receipts.append(str(result[key]))
    for key in ("task_id", "work_id", "run_id", "declaration"):
        identity(result.get(key))
    for nested in ("record", "producer", "spec", "run", "correction", "node", "association", "receipt"):
        value = result.get(nested)
        if isinstance(value, dict):
            identity(value.get("node") or value.get("target") or value.get("key") or value.get("task_id"))
            if value.get('id'): receipts.append(str(value['id']))
            for key in ("revision", "root_digest", "source_revision", "version"):
                if isinstance(value.get(key), (str, int, float, bool)):
                    revisions[key] = value[key][:500] if isinstance(value[key], str) else value[key]
            for key in ("file", "path", "result_path", "executable"):
                path(value.get(key))
    concept = result.get('concept')
    if isinstance(concept,dict):
        identity(concept.get('id'))
        revisions['concept_revision'] = concept.get('revision')
        revisions['concept_source_revision'] = concept.get('source_revision')
    if operation == 'research_reconcile':
        for record in result.get('records') or []:
            identity(record.get('id'))
            if record.get('id') and record.get('revision'): revisions[record['id']] = record['revision']
    for key in ("file", "root", "saved", "path", "exported_file", "receipt"):
        path(result.get(key))
    for key in ("path", "file", "source", "result", "executable"):
        path(payload.get(key))
    render = result.get("render")
    if isinstance(render, dict):
        for output in render.get("outputs") or []:
            path(output)
        identity(render.get("id"))
    affected = result.get("affected")
    if isinstance(affected, dict):
        for item in affected.get("identities") or []:
            identity(item)
        path(affected.get("plan_path"))
    for key in ("revision", "root_digest", "pdf_sha256", "source_revision", "previous_revision"):
        if isinstance(result.get(key), (str, int, float, bool)):
            revisions[key] = result[key][:500] if isinstance(result[key], str) else result[key]
    status = next((result.get(key) for key in
                   ("proof_status", "status", "state", "readiness")
                   if isinstance(result.get(key), (str, int, float, bool))), "SUCCEEDED")
    status = status[:120] if isinstance(status, str) else status
    views = list(result.get("effects") or _ACTION_VIEWS.get(operation, ["project"]))
    links = [{"label": "Project", "href": "/project?" + urlencode({
        "workspace": "writing", "corpus": project})}]
    if any(view in views for view in ("manuscript", "argument", "corrections")):
        links.append({"label": "Manuscript", "href": "/project?" + urlencode({"workspace":"writing","corpus": project,"view":"manuscript"})})
    if any(view in views for view in ("research", "visuals", "proofs")):
        links.append({"label": "Evidence", "href": "/project?" + urlencode({
            "workspace":"writing","corpus": project, "view": "research"})})
    if operation == "export_pdf" and isinstance(result.get("url"), str):
        links.append({"label": "Exported PDF", "href": result["url"]})
    if operation == "visual_render" and payload.get("id"):
        links.append({"label": "Rendered visual", "href": "/visuals/asset?" + urlencode({
            "project": project, "id": str(payload["id"]), "format": "pdf"})})
    summary = {"status": status, "views": views, "identities": identities[:16], "receipts": list(dict.fromkeys(receipts)),
               "paths": paths[:24], "revisions": revisions, "links": links[:5],
               "output_sha256": output_digest(result)}
    if operation=='style' and result.get('schema_version')=='laplace.document-template-candidate/1':
        summary.update(status='RECORDED' if result.get('metadata_only') else 'COMMITTED' if result.get('source_effect',{}).get('state')=='COMMITTED' else 'RETAINED',
            identities=[result['candidate_ref']['id']],next_read=result.get('read_handle'),
            metadata_only=bool(result.get('metadata_only')),application_recording=result.get('application_recording'),
            source_currentness=result.get('source_currentness'))
        summary['views']=['history'] if payload.get('action')=='prepare' or result.get('metadata_only') else ['manuscript','document','history']
    if result.get('schema_version')=='laplace.paragraph-restructure/1':
        summary['status']=('RECORDED' if result.get('complete') else 'RETAINED') if result.get('metadata_only') else 'COMMITTED' if result.get('complete') else 'SOURCE_COMMITTED_PENDING' if result.get('source_committed') else 'RETAINED'
        summary['next_read']=result.get('read_handle')
        summary['receipts']=list(dict.fromkeys([*summary['receipts'],result['receipt']['intent_artifact_id']]))
        if result.get('metadata_only'):
            summary['metadata_only']=True
            summary['source_currentness']=result.get('source_currentness')
            summary['current_observation']={key:result.get('current_observation',{}).get(key) for key in ('selection_identity','source_revision')}
    if operation == 'structure_change' and payload.get('operation') == 'prepare_work':
        summary['next_read'] = result.get('work_read')
        artifact = result.get('artifact') or {}
        if artifact.get('id'):
            summary['receipts'].append(artifact['id'])
        if artifact.get('human_read'):
            summary['human_read'] = artifact['human_read']
    if isinstance(result.get('source_effect'), dict):
        summary['source_effect'] = result['source_effect']
    if isinstance(result.get('plan_publication'), dict):
        summary['plan_publication'] = result['plan_publication']
    if result.get('maintenance_warnings'):
        summary['maintenance_warnings'] = result['maintenance_warnings']
    if operation == 'structure_change' and result.get('operation') in {'section_contract', 'paragraph_plan'}:
        summary['reader_change'] = {key: result.get(key) for key in
            ('operation', 'section_id', 'paragraph_id', 'consumed_revision', 'revision', 'subject_revision', 'record_id', 'read_handle', 'input_currentness')}
        summary['next_read'] = result.get('read_handle')
    if operation == 'apply_revision' and result.get('application_tracking'):
        summary.update(application_tracking=result['application_tracking'],
                       source_applied=bool(result.get('source_applied')),
                       source_effect_retained=bool(result.get('source_effect_retained')), warning=result.get('warning'))
    if operation=="store_artifact" and result.get("human_read"):
        summary["human_read"]=result["human_read"]
        summary["links"].append({"label":"Saved artifact","href":result["human_read"]["url"]})
    owned = result.get("owned_changes") if isinstance(result.get("owned_changes"), dict) else None
    if owned and owned.get("schema_version") == "laplace.owner-mutation/1":
        # Action rows need durable, bounded owner evidence.  Keep exact receipt
        # identities, not result bodies; History can lazily compare their bytes.
        files = [{key: row.get(key) for key in ("scope", "path", "before_sha256", "after_sha256", "observed_after_sha256")}
                 for row in owned.get("files") or [] if isinstance(row, dict) and isinstance(row.get("path"), str)][:16]
        objects = [{key: row.get(key) for key in ("owner", "id", "key", "claim_id", "record_id", "before_revision", "after_revision")}
                   for row in owned.get("objects") or [] if isinstance(row, dict) and row.get("id") is not None][:24]
        summary["owner_evidence"] = {"schema_version": "laplace.owner-evidence/1",
                                     "files": files, "objects": objects,
                                     "files_omitted": max(0, len(owned.get("files") or []) - len(files)),
                                     "objects_omitted": max(0, len(owned.get("objects") or []) - len(objects))}
    # Durable owner handle only; the workspace resolves guarded inverse edits
    # lazily from existing correction/section receipts, never from model text.
    undo_ref = result.get("undo_ref")
    if (operation in {"block_change", "section_change"} and isinstance(undo_ref, dict)
            and result.get("ok") is not False and result.get("complete") is not False
            and summary.get("status") == "SUCCEEDED"
            and undo_ref.get("kind") == {"block_change":"block", "section_change":"section"}[operation]
            and isinstance(undo_ref.get("id"), str) and 0 < len(undo_ref["id"]) <= 300
            and undo_ref.get("project", project) == project):
        summary["undo_ref"] = {"kind": undo_ref["kind"], "id": undo_ref["id"], "project": project}
    next_read = result.get("next_read")
    if isinstance(next_read,dict) and next_read.get("operation") == "source" and isinstance(next_read.get("payload"),dict):
        selection = next_read["payload"]
        files = selection.get("files")
        if isinstance(files,list) and files and len(files)<=8 and all(isinstance(path,str) and len(path)<=1000 for path in files):
            summary["next_read"] = {"operation":"source","payload":{"files":files,
                **{key:selection[key] for key in ("line_start","line_end") if isinstance(selection.get(key),int)}}}
    return summary


def _implicit_owned_changes(operation:str,result:dict):
    """Exact append receipts already returned by canonical conceptric writers."""
    if operation not in {"concept_change","logical_plan_change","structure_change"}:return None
    record=(result.get("writer_result") or {}).get("record") if operation=="structure_change" else result.get("record")
    if operation=="structure_change" and (not isinstance(record,dict) or record.get("kind")!="set-projection"):
        return None
    if not isinstance(record,dict) or not record.get("id"):return None
    return {"schema_version":"laplace.owner-mutation/1","files":[],
            "objects":[{"owner":"concepts","id":record.get("node"),
                        "record_id":record["id"],"before_revision":None,
                        "after_revision":"sha256:"+output_digest(record)}],
            "rewire_records":[record],"views":list(result.get("effects") or _ACTION_VIEWS.get(operation,()))}


def _compact_write_response(project:str,operation:str,payload:dict,result:dict) -> dict:
    """Provider-facing mutation receipt; canonical owners retain full bodies."""
    if result.get('schema_version')=='laplace.paragraph-restructure/1':
        from laplace.manuscript.reader_restructure import native_projection
        return native_projection(result,payload)
    forced={"apply_revision","framing","research_producer","experiment_run"}
    try:size=len(json.dumps(result,ensure_ascii=False,default=str).encode())
    except (TypeError,ValueError):size=0
    if operation not in forced and size<=16_000:return result
    if operation == 'workflow_definition_change':
        from laplace.pipeline.workflow_definitions import native_change_projection
        return {**native_change_projection(result), **({'action_receipt': result['action_receipt']} if 'action_receipt' in result else {})}
    action=result.get("action_receipt") if isinstance(result.get("action_receipt"),dict) else None
    summary=action or _action_summary(project,operation,payload,result)
    response={"ok":bool(result.get("ok",True)),"operation":operation,
              "status":summary.get("status") or result.get("status") or result.get("state") or "SUCCEEDED",
              "changed":{key:summary.get(key) for key in
                         ("views","identities","receipts","paths","revisions")},
              "full_response_omitted":True,
              "note":"Canonical owner state and full audit history are retained; use the exact returned read handle for detail."}
    if action:response["action_receipt"]={key:action.get(key) for key in
        ("id","status","views","identities","receipts","paths","revisions",
         "owner_evidence","mutation_attribution","refreshed_read_baselines",
         "context_refreshed", "source_effect", "plan_publication", "maintenance_warnings", "reader_change", "next_read") if key in action}
    if isinstance(result.get('source_effect'), dict):
        response['source_effect'] = result['source_effect']
    if isinstance(result.get('plan_publication'), dict):
        response['plan_publication'] = result['plan_publication']
        response['applied'] = bool(result.get('applied'))
        response['changed'] = result.get('changed')
    if result.get('maintenance_warnings'):
        response['maintenance_warnings'] = result['maintenance_warnings']
    if isinstance(result.get('detail_read'), dict):
        response['next_read'] = result['detail_read']
    if operation == 'structure_change' and payload.get('operation') == 'prepare_work':
        response.update({key:result[key] for key in (
            'work_id','work_read','task','preparation','execution','artifact','run_action',
            'provider_started','changed','reused') if key in result})
        response['next_read'] = result.get('work_read')
    if summary.get('reader_change'):
        response['reader_change'] = summary['reader_change']
        response['next_read'] = summary['reader_change']['read_handle']
    inverse_ref = result.get("undo_ref")
    if (operation in {"block_change", "section_change"} and isinstance(inverse_ref, dict)
            and summary.get("undo_ref") == {"kind":inverse_ref.get("kind"),
                "id":inverse_ref.get("id"), "project":inverse_ref.get("project",project)}
            and result.get("ok") is not False and result.get("complete") is not False
            and summary.get("status") == "SUCCEEDED"):
        from laplace.work.history import structural_undo_read
        response["undo_ref"] = summary["undo_ref"]
        if action:
            response["action_receipt"]["undo_ref"] = summary["undo_ref"]
        response["next_read"] = structural_undo_read(project,summary["undo_ref"])
    if operation=="apply_revision":
        application_id=str(result.get("id") or "")
        edits=result.get("edits") or []
        response.update(application_id=application_id or None,
            complete=bool(result.get("complete")),reused=bool(result.get("reused")),
            edit_count=len(edits),files=list(dict.fromkeys(str(row.get("file")) for row in edits
                if isinstance(row,dict) and row.get("file")))[:16],
            next_read={"operation":"author_history","payload":{
                "view":"record","id":"activity:journal:"+application_id}} if application_id else None)
        for key in ('source_applied', 'source_effect_retained', 'application_tracking', 'warning', 'context_rebase'):
            if key in result:
                response[key] = result[key]
        if not application_id:
            receipts = [{key:row.get(key) for key in ('row_id','version_id','file','lines')}
                        for row in result.get('receipts') or [] if isinstance(row,dict) and row.get('row_id')]
            response['source_receipts'] = receipts[:16]
            response['source_receipts_omitted'] = max(0, len(receipts)-16)
            if receipts:
                response['next_read'] = {'operation':'author_history','payload':{
                    'view':'record', 'id':'activity:feedback:'+receipts[0]['row_id']}}
    elif operation=="framing":
        response.update(project=result.get("project") or project,revision=result.get("revision"),
            argument_revision=result.get("argument_revision"),framing=result.get("framing"),
            next_read={"operation":"project","payload":{}})
    elif operation=="research_producer":
        producer=result.get("producer") if isinstance(result.get("producer"),dict) else {}
        response.update(producer={key:producer.get(key) for key in
            ("id","title","description","scope","executable","modes","revision") if key in producer},
            next_read={"operation":"research","payload":{}})
    elif operation=="experiment_run":
        run=result.get("run") if isinstance(result.get("run"),dict) else result
        run_id=run.get("id") or result.get("run_id")
        response.update(run={key:run.get(key) for key in
            ("id","producer_id","mode","state","deadline_at","result_path") if key in run},
            next_read={"operation":"run_status","payload":{"id":run_id}} if run_id else None)
    elif operation=="store_artifact":
        record=result.get("record") if isinstance(result.get("record"),dict) else {}
        path=result.get("path") or record.get("path") or payload.get("path")
        response.update(artifact={key:record.get(key) for key in ("id","path","sha256") if key in record},
            path=path,artifact_path=result.get("artifact_path"),scope=result.get("scope"),saved=result.get("saved"),revision=result.get("revision"),
            human_read=result.get("human_read"),link_instruction=result.get("link_instruction"),
            id=result.get("id") or result.get("record_id"),
            read_more=result.get("read_more") or result.get("read_handle"),
            update_handle=result.get("update_handle"),
            next_read=result.get("read_handle") or {"operation":"read_artifact","payload":{
                "path":payload.get("path"),"scope":payload.get("scope","project")}})
    return {key:value for key,value in response.items() if value is not None}


def _bank_talk_row(root: Path, row: dict) -> dict:
    """Append one writing row to ``contract/talk.jsonl`` through the seam that bounds it.

    ONE append for the WRITING DOORS' OWN MODULES, not for the repository: ``grep -c
    'journal[.]bank_row('`` over writing_tools.py, writing_provider.py and writing_projects.py
    counted 5 + 2 + 4 = 11 direct appends on base 87ece9da and counts 0 now.  Twenty-two
    remain elsewhere in src/laplace (manuscript_structure 8, front_door 4, writing_style 4,
    research_surface 2, project_structure, manuscript_blocks, document_style and
    references_surface 1 each); they are a named residual, not silently covered here.  FIVE
    sites in this module: :571 (the artifact write-ahead row), :1039 (the read row), :1080
    (the action row --- the one the storage lane exists for), :1112 (the turn row), and :1264
    inside ``bank_failure``, the ONE producer of the failure row for all three transports
    (``writing_provider.py:623``, ``writing_provider.py:905``, ``main``'s stdio receipt at
    :1597): three literals with two bounds became one producer with one bound.

    ``writing.records.bank`` (historically reached as ``authoring_surface._bank``) is the
    only banking path that applies ``_CUSTODY_FIELDS``
    -- it replaces a field whose JSON exceeds ``_CUSTODY_MIN_BYTES`` with a handle into the
    content-addressed body store that already exists (``contract/writing_bodies``), and
    every reader resolves those handles on its way in (``authoring_surface._records`` :244,
    ``author_history`` :1039, :1058).  The rows this module banked went straight to
    ``journal.bank_row`` instead, so the custody declaration for
    ``writing-tool-action``/``writing-tool-failure`` was dead for exactly the rows it
    named and the whole artifact text was inlined 235 times. Those counts describe
    the historical gateway migration. Artifact write-ahead rows now belong to
    writing.artifacts.store, and owner receipts (project metadata, drafts, material
    references, lifecycle) call writing.records.bank themselves; this gateway keeps
    tool reads/actions/failures and their existing bounds.
    """
    return writing_records.bank(Path(root), row)


def execute(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None = None, *, requested_by: str = "", _incoming=None) -> dict:
    return _native_entry(root,project,turn_id,{'operation':operation,'payload':payload},
        lambda: _execute_public_impl(root,project,mode,operation,payload,turn_id,requested_by=requested_by),_incoming)


def _execute_public_impl(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None = None, *, requested_by: str = "") -> dict:
    if turn_id:
        from laplace.writing.sealed_reader import require_not_reader
        require_not_reader(root,turn_id=turn_id)
    from laplace.representation import writing_bodies as bodies
    with core_bodies.operation() as diagnostic:
        result = _execute_operation(root, project, mode, operation, payload, turn_id, requested_by=requested_by)
        if diagnostic["failed_attempts"]:
            observed = json.loads(json.dumps(diagnostic))
            result = {**result, "custody_degradation":observed}
            if result.get("action_receipt"):
                result["action_receipt"] = {**result["action_receipt"], "custody_degradation":observed}
        from laplace.writing import delivery
        delivery.settle("custody_degradation")
        return result


def _execute_operation(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None = None, *, requested_by: str = "") -> dict:
    # ONE dispatch for every caller path.  `writing_verbs.classify` rewrites this call into
    # the grammar's request (verb x concept, GRAMMAR.md §3-§5) and rebuilds the owner call
    # from it; when the rebuild is the identical (operation, payload) pair -- checked here,
    # per call, not only in a test -- the rebuilt pair is what runs, so the dispatch is in
    # the causal path and not beside it.  When it is not identical the legacy pair runs
    # unchanged, so a gap in the route table can never change what an owner receives.
    from laplace.native import verbs as writing_verbs, declarations as writing_declarations
    try: writing_declarations.validate_owner_payload(operation, payload, project=project, requested_by=requested_by)
    except writing_declarations.PayloadAdmissionError as error:
        error.requested_by = requested_by
        raise
    act = writing_verbs.classify(operation, payload, project=project, by=requested_by, root=root)
    if act.exact and act.owner_call is not None:
        operation, payload = act.owner_call[0], dict(act.owner_call[1])
    from laplace.writing import source_execution
    source_execution.require_supported_spawn(root,project,turn_id,operation)
    pre_write_baseline = _capture_write_baseline(root, project, operation, payload, turn_id)
    from laplace.writing import delivery
    # THE ADMITTED ACT (writing.delivery, step 0): both spellings reach this one dispatch; the act carries its profile
    admitted = delivery.admit_act(operation, payload, **act.row)
    bound = admitted['profile'] if (is_read := reads.effect(operation, payload) == 'read') else None   # the one action-level classification
    # a bounded read fits the bound minus this door's exact metadata, the declared outer envelope and the largest form
    # of every late addition; the plan fixes the eligible-offer cut (step 2) and the owner records its projection
    envelope = delivery.envelope()
    plan_additions = _plan_additions(root, project, turn_id, operation, payload) if bound else {'cut': None, 'forms': {}}
    plan_additions['forms'] = {**plan_additions['forms'], **delivery.late_forms()}
    line = (bound['bound'] - delivery.inserted({}, {**_read_metadata(root, project, operation, payload, turn_id, act),
                                                    **plan_additions['forms']}) - delivery.wrapped(envelope)) if bound else None
    if bound:
        delivery.record_cut(plan_additions['cut'], plan_additions['forms'])
    with delivery.planned(line=line) as plan:
        result = (_operations._execute(root, project, mode, operation, payload, turn_id=turn_id, observe_reads=True)
                  if operation == 'reference_text' else _operations._execute(root, project, mode, operation, payload, turn_id=turn_id))
    if turn_id and is_read:
        result = _receipt_turn_read(root, project, operation, payload, turn_id, act, result, pre_write_baseline,
                                    projection=plan['projection'], bound=bound, later=plan_additions['forms'], envelope=envelope)
    elif turn_id:
        result = _receipt_turn_write(root, project, operation, payload, turn_id, act, result, pre_write_baseline)
    elif writing_verbs.bank_every_path():
        _bank_unbound_act(root, project, operation, payload, act, result)
    result = _compact_owner_state(operation, payload, result)
    if not is_read:
        result=_compact_write_response(project,operation,payload,result)
    return result


def _capture_write_baseline(root: Path, project: str, operation: str, payload: dict, turn_id: str | None):
    """Before a turn-bound write (and reference_text): the turn's affected reads and owner files."""
    pre_write_baseline = None
    if (turn_id and (reads.effect(operation, payload) == 'write' or operation == "reference_text")
            and operation not in {"apply_revision", "proposal_supersede", "style"}):
        from laplace.writing import turn_reads
        try:
            pre_write_baseline = turn_reads.capture_turn_read_baselines(
                root, project, turn_id, operation,payload)
        except ValueError:
            # Direct CLI/test calls can carry a receipt handle without a saved
            # turn. They have no baseline to advance after the mutation.
            pre_write_baseline = None
    return pre_write_baseline


def _read_receipt(read_row: dict, turn_id: str, session_id, project: str, operation: str) -> dict:
    """THE read receipt a turn-bound read carries (one composer: the delivered receipt and its pre-read measure)."""
    return {"id":read_row["id"],"turn_id":turn_id,"session_id":session_id,"project":project,
            "operation":operation,"payload":read_row["payload"],"output_sha256":read_row["output_sha256"],
            **({"requested_by":read_row["requested_by"]} if "requested_by" in read_row else {})}


def _read_metadata(root: Path, project: str, operation: str, payload: dict, turn_id: str | None, act) -> dict:
    """The mandatory metadata this door adds around a read's owner result, composed by the same functions that add it:
    the operation's read extras and, for a turn-bound read, its read_receipt with a fixed-length id ("READ-" and 32 hex)
    and digest (64 hex). writing.delivery measures it exactly; context refresh, custody and updates are later stages
    with their own admission (writing.delivery module text)."""
    added = dict(_read_extras(operation, project))
    if turn_id:
        # the same precedence as the delivered read row: id, then act.row, then payload and digest
        row = {"id": "READ-" + "0" * 32, **act.row, "payload": {**payload, "project": project}, "output_sha256": output_digest({})}
        session = (writing_records.index(root).turns.get(turn_id) or {}).get("session_id")
        added["read_receipt"] = _read_receipt(row, turn_id, session, project, operation)
    return added


def _plan_additions(root: Path, project: str, turn_id: str | None, operation: str, payload: dict) -> dict:
    """THE PLAN of a bounded act (writing.delivery, step 2): {'cut', 'forms'}. ``forms`` is the largest bounded form of
    each late addition this result may have to carry, by result field, from each owner's own composer and without
    effects: the deferred context refresh, the author-update offer without bodies, the largest of the input owner's
    deferred notice and failure answers, the custody diagnostic without identities and the update-unavailable answer.
    ``cut`` fixes which mutable offers belong to this delivery: the correction ids and the input control observed now.
    The page is selected beside the forms, so every stage after the receipt falls back to a reserved form without
    shrinking the receipted projection, and offers arriving after the cut wait for the next boundary."""
    from laplace.writing import provider_updates
    from laplace.writing import delivery, turn_reads
    forms = {'custody_degradation': _custody_form()}
    cut = None
    if turn_id:
        offer = provider_updates.author_offer(root, project, turn_id, bank=False)
        pending = provider_updates.pending_input(root, project, turn_id)
        cut = {'author_updates': [] if offer is None else list(offer['correction_ids']),
               'turn_input': () if pending is None else pending['eligible']}
        forms.update({'context_refresh': turn_reads.pending_refresh_notice(root, project, turn_id, operation, payload),
                      'author_updates': provider_updates.author_notice(offer),
                      'turn_input': None if pending is None else max(pending['forms'], key=delivery.emitted),
                      'update_delivery_unavailable': _unavailable_form()})
    return {'cut': cut, 'forms': {field: value for field, value in forms.items() if value is not None}}


def _custody_form() -> dict:
    """The largest custody diagnostic a bounded result carries after admission projects its identity list
    (core.bodies.degradation; counts and byte totals below ten digits)."""
    from laplace.representation import writing_bodies as bodies
    from laplace.writing import delivery
    full = {**core_bodies.degradation(), 'failed_attempts': 10 ** 10 - 1, 'inline_bytes': 10 ** 10 - 1, 'identities_omitted': 10 ** 10 - 1,
            'identities': [{'reason': 'x' * 80, 'content_handle': 'sha256:' + '0' * 64}] * 8}
    return delivery._project_custody({'custody_degradation': full}, [])['custody_degradation']


def _unavailable_form() -> dict:
    """The largest update-delivery-unavailable answer (one per result, its error text bounded)."""
    from laplace.writing import delivery
    return max([_unavailable_answer('x' * 500, 'author_updates'),
                {'error': 'x' * 500, 'basis': 'Original tool outcome retained; no update delivery or acknowledgement inferred.'}],
               key=delivery.emitted)


def _receipt_turn_read(root: Path, project: str, operation: str, payload: dict, turn_id: str, act, result: dict,
                       pre_write_baseline, *, projection=None, bound=None, later=None, envelope=None) -> dict:
    """A turn-bound read: one writing-tool-read row, its receipt, and the context refresh it allows."""
    from laplace.writing import turn_reads
    read_row={"record": "writing-tool-read", "id": "READ-"+uuid.uuid4().hex,
        "project": project, "turn_id": turn_id, "operation": operation,
        **act.row,
        "payload": {**payload, "project": project},
        **reads.record_read_basis(operation,result,payload,project=project,projection=projection),
        # the consulted semantic projection, retained so every pure replay reproduces it (writing.delivery, step 3)
        **({"projection": projection} if projection else {})}
    if operation=="source":
        read_row["source_scope"]=[{key:row.get(key) for key in
            ("file","line_start","line_end","expected_source_digest")} for row in result.get("sources") or []
            if isinstance(row,dict) and isinstance(row.get("file"),str)]
    elif operation=="read_artifact":
        read_row["artifact_path"]=result.get("artifact_path")
        read_row["artifact_scope"]=result.get("scope")
        read_row["artifact_record_id"]=result.get("recorded_id")
    elif operation=='dispatch_returns':read_row['dispatch_id']=result['dispatch_id']
    _bank_talk_row(root, read_row)
    recorded_turn = writing_records.index(root).turns.get(turn_id) or {}
    result = {**result, "read_receipt": _read_receipt(read_row, turn_id, recorded_turn.get("session_id"), project, operation)}
    if operation == 'reference_text':
        try:turn_reads.refresh_turn_read_baselines(root,project,turn_id,operation,pre_write_baseline,
            actual_views=_ACTION_VIEWS['reference_text'],owned_changes=result.get('owned_changes'))
        except ValueError:pass
    try:
        from laplace.writing import delivery
        # a bounded delivery gives the refresh what is left BEFORE it banks: a refresh that does not fit is not adopted
        fits=(lambda value:delivery.fits(result,"context_refresh",value,bound,later,envelope)) if bound else None
        context_refresh=turn_reads.refresh_context_after_read(
            root,project,turn_id,operation,payload,fits=fits)
    except (OSError,ValueError):context_refresh={"refreshed":False,"reason":"context refresh unavailable"}
    if context_refresh.get("refreshed") or context_refresh.get("deferred"):
        result={**result,"context_refresh":context_refresh}
    delivery.settle("context_refresh")
    return result


def _receipt_turn_write(root: Path, project: str, operation: str, payload: dict, turn_id: str, act, result: dict,
                        pre_write_baseline) -> dict:
    """A turn-bound write: advance only exactly attributed read baselines, then one writing-tool-action row."""
    from laplace.writing import turn_reads
    if operation in {"apply_revision", "proposal_supersede", "style"}:
        baseline = {"refreshed": 0}
    else:
        try:
            owned_changes=result.get("owned_changes") or _implicit_owned_changes(operation,result)
            baseline = turn_reads.refresh_turn_read_baselines(
                root, project, turn_id, operation, pre_write_baseline,
                actual_views=result.get("effects"),owned_changes=owned_changes)
        except ValueError:
            # CLI/test callers may supply a receipt handle without a persisted
            # authoring turn.  The write remains valid; there is simply no turn
            # baseline to advance.
            baseline = {"refreshed": 0}
    action = {"record": "writing-tool-action", "id": "ACTION-" + uuid.uuid4().hex,
              "project": project, "turn_id": turn_id, "operation": operation,
              **act.row,
              # THE WRITE'S OWN REQUEST, so the row can replay the write it records.
              # The READ row beside this one has always banked `payload` (:1017); the
              # write row banked `outcome` alone, which is why every one of the 1,536
              # recorded action rows was unreplayable (measured: probes/talk_census.py).
              # Same row, same kind, one more field -- and the field is bounded by the
              # custody seam below, not by a truncation this door invents.
              "payload": {**payload, "project": project},
              "outcome": {**_action_summary(project, operation, payload, result),
                          "refreshed_read_baselines": baseline.get("refreshed", 0),
                          "context_refreshed":bool(baseline.get("context_refreshed")),
                          "mutation_attribution":baseline.get("attribution")}}
    _bank_talk_row(root, action)
    result = {**result, "action_receipt": {"id": action["id"], **action["outcome"],
        **({"requested_by":action["requested_by"]} if "requested_by" in action else {})}}
    return result


def _bank_unbound_act(root: Path, project: str, operation: str, payload: dict, act, result: dict) -> None:
    # EVERY caller path, not only a provider turn.  The friction report measured the
    # consequence of the old condition: "the system's failure record is a census of one
    # provider's turns" (writing_tools.py:1351 and writing_provider.py:550, both
    # at 87ece9da), and a direct
    # or HTTP caller's act was banked nowhere.  One place (contract/talk.jsonl, the
    # place that already exists) and one grain (verb, concept, altitude).  No new record
    # kind and no new file, so holder_census.py counts no new holder.
    if operation in READS:
        row = {"record": "writing-tool-read", "id": "READ-" + uuid.uuid4().hex,
               "project": project, "turn_id": None, "operation": operation, **act.row,
               "payload": {**payload, "project": project}}
        try:
            row.update(reads.record_read_basis(operation,result,payload,project=project))
        except Exception:
            row["output_sha256"] = None
    else:
        # ONE SHAPE for the action row, whichever caller path banks it: the same
        # `payload` the provider-turn row above carries (:1063), bounded by the same
        # custody seam.  Until this synthesis the two sites wrote two shapes of one
        # row kind -- a provider turn's write replayed and a direct or HTTP caller's
        # did not -- which is the packet's own goal failing on half its rows.
        row = {"record": "writing-tool-action", "id": "ACTION-" + uuid.uuid4().hex,
               "project": project, "turn_id": None, "operation": operation, **act.row,
               "payload": {**payload, "project": project}}
        try:
            row["outcome"] = _action_summary(project, operation, payload, result)
        except Exception as exc:
            row["outcome"] = {"status": "SUCCEEDED", "summary_unavailable": str(exc)[:120]}
    try:
        _bank_talk_row(root, row)
    except (OSError, ValueError):
        pass


def _compact_owner_state(operation: str, payload: dict, result: dict) -> dict:
    """A write acknowledgement carries the changed object and its next revision, not the whole state."""
    if operation == "logical_plan_change" and isinstance(result.get("state"), dict):
        state = result["state"]
        selected = state.get("selected") or {}
        # Mutation acknowledgement carries the changed object and next revision,
        # not another whole-book dump. The UI still reads the full owner facade.
        selected_summary={key:selected.get(key) for key in
                          ("id","label","kind","status","parent","grade","containment_grade")
                          if selected.get(key) is not None}
        # The write acknowledgement hands back the NEXT token, so a caller that is about to act
        # again does not have to re-read to learn the identity its own write produced.
        result = {**result, "state": {**{key: state.get(key) for key in
                  ("schema_version", "project", "revision", "identities", "source_currentness")},
                  "selected":selected_summary},
                  "obligations": [row for row in state.get("obligations", [])
                                  if row.get("id") == selected.get("id")],
                  "read_more": "logical_plan with node, or structure for the chapter outline"}
    if operation == "concept_change" and isinstance(result.get("state"),dict):
        state=result["state"];focus=state.get("focus") or {};mathematics=state.get("mathematical_record") or {}
        qualification=mathematics.get("qualification") or {};verification=mathematics.get("verification") or {}
        result={**result,"state":{**{key:state.get(key) for key in
            ("schema_version","project","revision","identities","content_revision")},
            "focus":{key:focus.get(key) for key in ("id","label","kind","status")
                     if focus.get(key) is not None},
            **({"mathematics":{"revision":mathematics.get("revision"),
                "statement_origin":mathematics.get("statement_origin"),
                "qualification":qualification.get("status"),
                "proof_status":(mathematics.get("proof") or {}).get("status"),
                "verification_status":verification.get("status")}} if mathematics else {})},
            "read_more":{"operation":"concept","payload":{"node":focus.get("id")}}}
    if operation=="structure_change" and isinstance(result.get("state"),dict):
        state=result["state"];affected_node=str(payload.get("node") or "")
        bound=[row for row in state.get("evidence") or []
               if not affected_node or row.get("node_id")==affected_node]
        result={**result,"state":{key:state.get(key) for key in
            ("schema_version","project","status","revision","identities",
             "eligible_for_authoring")},
            **({"evidence":bound} if bound else {}),
            "read_more":{"operation":"structure","payload":{}}}
    return result


def _owner_frames(error: BaseException) -> tuple[str | None, list[str]]:
    """The owner frames that actually raised, innermost last, as ``src/laplace/<f>.py:<n>``.

    The verb door catches the owner's exception to answer in the grammar's refusal shape, so
    without this the raising frame -- the one fact the recorded failure census names per class
    -- would be lost at exactly the door that is supposed to publish it.  Same definition the
    oracle uses (``harness/_worker.py:50``), so a refusal through the verb door and the same
    refusal through the operation name are comparable on ``home``.
    """
    import traceback as _tb
    chain: list[str] = []
    for frame in _tb.extract_tb(error.__traceback__):
        parts = Path(frame.filename).parts
        if "laplace" not in parts:
            continue
        index = len(parts) - 1 - parts[::-1].index("laplace")
        chain.append("src/" + "/".join(parts[index:]) + ":" + str(frame.lineno))
    return (chain[-1] if chain else None), chain


def _failure_receipt_result(answer,receipt):
    result={**answer,'failure_receipt':receipt}
    if receipt.get('row_id'):
        result['failure_read']={'operation':'author_history','payload':{
            'view':'record','id':'activity:journal:'+receipt['row_id']}}
    return result


def _record_request_refusal(root, project, turn_id, operation, payload, error, answer, *, requested_by=""):
    """Bank this explicit refusal once; normal returns bypass transport catchers.

    This is not a predicate over arbitrary scientific results. The caller names
    a refused owner/shape/scope transition. No update/publication wrapper runs here.
    """
    from laplace.work import author_history_metrics as metadata
    try:
        idx=writing_records.index(root)
        admitted=[row for row in idx.by_id.get(turn_id,[]) if row.get('record')=='writing-turn']
        if not turn_id or len(admitted)!=1 or idx.project(admitted[0])!=project:
            return {**answer,'failure_receipt':{'row_id':None,
                'note':'Failure receipt unavailable: no unique bound project turn.'}}
    except (OSError,ValueError) as unavailable:
        return {**answer,'failure_receipt':{'row_id':None,
            'note':'Failure receipt unavailable: '+str(unavailable)[:500]}}
    receipt=bank_failure(root,project,operation,payload,error,turn_id,recovery=answer,requested_by=requested_by)
    return _failure_receipt_result(answer,receipt)


def request(root: Path, project: str, mode: str, req, turn_id: str | None = None, *, _incoming=None) -> dict:
    intent = req if isinstance(req,dict) else {key:getattr(req,key,None) for key in ('verb','concept','target','expected','payload','by')}
    return _native_entry(root,project,turn_id,intent,
        lambda: _request_public_impl(root,project,mode,req,turn_id),_incoming)


def _request_public_impl(root: Path, project: str, mode: str, req, turn_id: str | None = None) -> dict:
    """The verb door: one request per act, at any altitude.

    ``req`` is a ``laplace.core.grammar.Request`` (or the six-key dict of one).  The owner call is
    rebuilt by ``writing_verbs.to_owner_call`` and runs through ``execute`` -- the same
    wrapper the old names run through, so there is one code path and replay cannot diverge
    (GRAMMAR.md §6 rule 1).  Where the existing owner door accepts canonical ``expected``,
    that field crosses the boundary intact so the owner compares its home scope before any
    legacy spelling could erase it.  The answer is the grammar's receipt or refusal (§5): a status,
    not a field name; every home accounted for; ``needed`` as the resolver, built by the
    comparison and therefore present on every caller path, not only the provider's.
    """
    if turn_id:
        from laplace.writing.sealed_reader import require_not_reader
        require_not_reader(root,turn_id=turn_id)
    from laplace.core import grammar as g
    from laplace.native import verbs as writing_verbs
    from laplace.native import declarations as writing_declarations
    original = req
    try:
        if isinstance(req, dict):
            req = g.Request(verb=str(req.get("verb") or ""), concept=str(req.get("concept") or ""),
                            target=str(req.get("target") or project),
                            expected=tuple(req.get("expected") or ()),
                            payload=req.get("payload") or {}, by=str(req.get("by") or ""))
        route = writing_verbs.choose(req.verb, req.concept, req.payload)
    except ValueError as error:
        # Only pure request construction/selection lives here. Never reclassify
        # an escaped post-owner or post-effect failure as payload admission.
        fields = original if isinstance(original,dict) else {"payload":original.payload,"expected":original.expected,"by":original.by}
        try: operation = writing_verbs.choose(fields.get('verb',''),fields.get('concept',''),fields['payload']).operation
        except ValueError: operation = ""
        refused = writing_declarations.PayloadAdmissionError(operation,str(error),requested_by=fields.get('by',''))
        refused.attempt_payload = {**fields['payload'],**({"expected":list(fields['expected'])} if fields['expected'] else {})}
        raise refused from error
    from laplace.native import declarations as writing_declarations
    from laplace.writing import delivery
    attempt = {**req.payload, **({"expected":list(req.expected)} if req.expected else {})}
    # a refusal before dispatch is still an admitted act of this invocation: the route's operation and the request's
    # payload (the grammar renames no profile key) carry the delivery policy (writing.delivery, step 0); the refused
    # attribution is not re-derived here, the refusal body already carries it
    def refused(answer):
        delivery.admit_act(route.operation, req.payload, verb=route.verb, concept=route.concept, altitude=route.altitude, target=req.target)
        return answer
    try:
        writing_declarations.validate_request_payload(req, route, project=project)
    except writing_declarations.PayloadAdmissionError as error:
        return refused(_record_request_refusal(root,project,turn_id,route.operation,attempt,error,error.response(),requested_by=req.by))
    expected_target = writing_verbs.expected_request_target(req, route, project)
    if expected_target is not None:
        refusal = g.Refusal(
            kind="shape", homes=(),
            needed={"target": expected_target},
            said="request target %r does not name this route's owner target %r"
                 % (req.target, expected_target))
        answer = refusal.response()
        answer["refused"]["owner"] = {
            "operation": route.operation, "owner": route.owner, "site": route.site,
            "raised": None, "chain": []}
        answer["banked_row"] = {
            "verb": route.verb, "concept": route.concept, "altitude": route.altitude,
            "target": req.target, "dispatch": "fell-through",
            "dispatch_reason": "request target disagrees with the bound owner target"}
        return refused(_record_request_refusal(root,project,turn_id,route.operation,req.payload,
            ValueError(refusal.said),answer,requested_by=req.by))
    preserves_expected = bool(req.expected) and writing_verbs.owner_accepts_expected(route)
    scope_error = (writing_verbs.expected_scope_error(req, route, project)
                   if req.expected and not preserves_expected else None)
    if scope_error:
        answer=_request_scope_refusal(root, project, req, route, scope_error)
        return refused(_record_request_refusal(root,project,turn_id,route.operation,req.payload,
            ValueError(scope_error),answer,requested_by=req.by))
    try:
        operation, payload = writing_verbs.to_owner_call(
            req, root=root, route=route, preserve_expected=preserves_expected)
    except (ValueError, g.Refused) as error:
        # Translation may compare a valid token with fresh held counter/span
        # bytes. No baseline/effect ran; retain that cure without classify/account.
        from laplace.core import identity_doors
        answer=identity_doors.body(error,{"ok":False,"operation":route.operation,"error":str(error)[:4000]})
        if "refused" not in answer:
            answer=writing_declarations.PayloadAdmissionError(route.operation,"Guard materialization unavailable: "+str(error)).response()
        answer['banked_row']=writing_verbs.Classified(route,req,None,False,'guard materialization refused').row
        return refused(_record_request_refusal(root,project,turn_id,route.operation,attempt,error,answer,requested_by=req.by))
    # THE ENVELOPE this spelling wraps around the owner result, declared before the one owner call so the delivery
    # plan counts it exactly (writing.delivery, step 2); the outcome word is planned at the longest of its finite set
    envelope = _request_envelope(route, req, operation)
    delivery.declare_envelope({**envelope, "outcome": max(_REQUEST_OUTCOMES, key=len)}, "owner_response")
    delivery.admit_act(operation, payload, verb=route.verb, concept=route.concept, altitude=route.altitude,
                       target=req.target, **writing_verbs.requested_by_metadata(req.by))
    try:
        result = _request_owner_call(root, project, mode, req, route, operation, payload, turn_id)
    except (OwnerError, ValueError) as error:
        return _request_owner_refusal(root, project, turn_id, req, route, operation, payload, attempt, error)
    outcome = "banked" if (isinstance(result, dict) and result.get("pending")) else (
        "read" if operation in READS or route.verb=="read" else "recorded" if result.get('metadata_only') or route.operation in {"corpus/friction-report","corpus/friction-create"} else "applied")
    return {**envelope, "outcome": outcome, "owner_response": result}


#: the finite outcomes of the semantic receipt (request): the plan reserves the longest
_REQUEST_OUTCOMES = ("banked", "read", "recorded", "applied")


def _request_envelope(route, req, operation: str) -> dict:
    """The grammar receipt around an owner result, without its outcome and owner_response: one composer for the
    delivered receipt and for the delivery plan."""
    from laplace.native import verbs as writing_verbs
    return {"ok": True,
            "banked_row": {"verb": route.verb, "concept": route.concept,
                           "altitude": route.altitude, "target": req.target,
                           **writing_verbs.requested_by_metadata(req.by)},
            "owner": {"operation": operation, "owner": route.owner, "site": route.site}}


def _request_owner_call(root: Path, project: str, mode: str, req, route, operation: str, payload: dict, turn_id: str | None) -> dict:
    """The owner call of an admitted request: four declared routes answer here, every other one through execute."""
    if route.operation in {'corpus/friction-read','corpus/friction-report','corpus/friction-create'}:
        return _technical_friction_call(root, project, mode, req, route, operation, payload, turn_id)
    if route.door=='http' and route.method=='GET' and route.route=='/projection/tex':
        return _physical_source_read(root, project, mode, req, route, operation, payload, turn_id)
    if route.door=='http' and route.method=='POST' and route.route=='/authoring/proposal-decision':
        return _proposal_decision_call(root, project, mode, req, route, operation, payload, turn_id)
    if route.door == 'http' and route.method == 'GET' and route.route in {'/authoring/proposals','/authoring/proposal-preview'}:
        return _proposal_read_call(root, project, mode, req, route, operation, payload, turn_id)
    result = execute(root, project, mode, operation, payload, turn_id=turn_id,requested_by=req.by)
    if result.get('schema_version')=='laplace.paragraph-restructure/1':
        from laplace.manuscript.reader_restructure import native_projection
        result=native_projection(result,payload,payload.get('read_id') or (result.get('read_receipt') or {}).get('id'))
    return result


def _technical_friction_call(root: Path, project: str, mode: str, req, route, operation: str, payload: dict, turn_id: str | None) -> dict:
    from laplace.native import declarations as writing_declarations, verbs as writing_verbs
    writing_declarations.validate_owner_payload(operation,payload,project=project,requested_by=req.by)
    from laplace.work.technical_friction import read, report, PERMITTED_MODES
    if mode not in PERMITTED_MODES:raise ValueError('Unknown writing role')
    values={key:value for key,value in payload.items() if key not in {'by'}}
    if turn_id:
        from laplace.work import author_history_metrics as metadata
        idx=writing_records.index(root);admitted=idx.turns.get(turn_id)
        if not admitted or idx.project(admitted)!=project:raise ValueError('Technical owner call does not belong to this project turn.')
    if req.verb=='read':result=read(root,project,values)
    else:result=report(root,project,turn_id,values)
    if turn_id:
        row={'record':'writing-tool-read' if req.verb=='read' else 'writing-tool-action',
            'id':('READ-' if req.verb=='read' else 'ACTION-')+uuid.uuid4().hex,
            'project':project,'turn_id':turn_id,'operation':operation,
            'verb':route.verb,'concept':route.concept,'altitude':route.altitude,'target':req.target,
            **writing_verbs.requested_by_metadata(req.by),
            'payload':values,'by':'eigen:session'}
        if req.verb=='read':row.update(reads.record_read_basis(operation,result,payload,project=project))
        else:
            ident=(result.get('record') or {}).get('id')
            row['outcome']={'status':'RECORDED','views':['technical-report-history'],
                'identities':[ident] if ident else [],'receipts':[ident] if ident else []}
        _bank_talk_row(root,row)
        result={**result,'call_receipt':{key:row[key] for key in ('id','project','turn_id','operation','requested_by') if key in row}}
    return result


def _physical_source_read(root: Path, project: str, mode: str, req, route, operation: str, payload: dict, turn_id: str | None) -> dict:
    from laplace.native import declarations as writing_declarations, verbs as writing_verbs
    writing_declarations.validate_owner_payload(operation,payload,project=project,requested_by=req.by)
    from laplace.manuscript import manuscript_source, projection_viewer
    if payload.get('corpus')!=project:raise ValueError('The physical source read belongs to another project.')
    values={key:value for key,value in payload.items() if key!='project'}
    values=manuscript_source.validate_source_query(values)
    path=(Path(root)/values['file']).resolve()
    access=manuscript_source.source_access(project,path,root)
    result=projection_viewer._source_observation(path,repo_root=root,query=values,access=access)
    result.update(access);result.update(manuscript_source.source_handles(project,result['file'],result['expected_source_digest'],access))
    if turn_id:
        idx=writing_records.index(root);admitted=idx.turns.get(turn_id)
        if not admitted or idx.project(admitted)!=project:raise ValueError('The physical source read needs its actual project caller.')
        row={'record':'writing-tool-read','id':'READ-'+uuid.uuid4().hex,'project':project,'turn_id':turn_id,
            'operation':operation,'payload':payload,'output_sha256':reads.read_output_digest(operation,result),
            'source_scope':[{'file':result['file'],'expected_source_digest':result['expected_source_digest']}]}
        _bank_talk_row(root,row)
        result['read_receipt']={key:row[key] for key in ('id','turn_id','project','operation','output_sha256')}
    return result


def _proposal_decision_call(root: Path, project: str, mode: str, req, route, operation: str, payload: dict, turn_id: str | None) -> dict:
    from laplace.native import declarations as writing_declarations, verbs as writing_verbs
    writing_declarations.validate_owner_payload(operation,payload,project=project,requested_by=req.by)
    from laplace.manuscript import manuscript_proposals
    admitted=writing_records.index(root).turns.get(turn_id) or {}
    if admitted.get('project')!=project:raise ValueError('Proposal decisions require the actual caller turn in this project.')
    decision=payload.get('decision');read_only=decision in {'prepare-resolution','preview-resolution'}
    if read_only:raise ValueError('Prepare and preview are reads; use the returned read proposal@paragraph resolution view.')
    if not read_only and (mode=='review' or admitted.get('dispatch_id')):
        raise ValueError('Independent reviewers and dispatched children cannot apply source candidates; the authorised parent decides.')
    actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitted.get('dispatch_id')}
    result=manuscript_proposals.decide(root,project,payload,actor=actor)
    row={'record':'writing-tool-read' if read_only else 'writing-tool-action',
        'id':('READ-' if read_only else 'ACTION-')+uuid.uuid4().hex,'project':project,'turn_id':turn_id,
        'operation':operation,'verb':route.verb,'concept':route.concept,'altitude':route.altitude,
        'target':req.target,'payload':payload,**writing_verbs.requested_by_metadata(req.by)}
    if read_only:row.update(reads.record_read_basis(operation,result,payload,project=project))
    else:row['outcome']={'status':'RECORDED' if result.get('metadata_only') else 'APPLIED' if (result.get('application') or {}).get('complete') else 'RETAINED',
        'views':['review','history'] if result.get('metadata_only') else ['manuscript','document','history'],
        'identities':[result['candidate_ref']['id']] if result.get('candidate_ref') else []}
    _bank_talk_row(root,row)
    from laplace.manuscript.reconciliation import native_candidate
    result=native_candidate(result)
    return result


def _proposal_read_call(root: Path, project: str, mode: str, req, route, operation: str, payload: dict, turn_id: str | None) -> dict:
    from laplace.native import declarations as writing_declarations, verbs as writing_verbs
    writing_declarations.validate_owner_payload(operation,payload,project=project,requested_by=req.by)
    from laplace.manuscript.proposal_navigation import read
    from jsonschema import Draft202012Validator
    from laplace.native.declarations import HTTP_DECLARATIONS
    if mode not in {'work','discuss','review','revise'}:raise ValueError('Unknown writing role')
    values={key:value for key,value in payload.items() if key != 'by'}
    if values.get('project') not in (None,project):raise ValueError('Read belongs to another project.')
    values.pop('project',None)
    if values.get('view') in {'resolution','resolution-preview'} and not turn_id:
        raise ValueError('Native resolution inspection requires the actual caller turn for an exact retained read receipt.')
    error=next(Draft202012Validator(HTTP_DECLARATIONS[operation].payload).iter_errors({'project':project,**values}),None)
    if error:raise ValueError('Proposal read does not match its existing owner contract: '+error.message)
    result=read(root,project,values)
    if turn_id:
        from laplace.work import author_history_metrics as metadata
        idx=writing_records.index(root);admitted=idx.turns.get(turn_id)
        if not admitted or idx.project(admitted)!=project:raise ValueError('Read receipt does not belong to this project turn.')
        row={"record":"writing-tool-read","id":"READ-"+uuid.uuid4().hex,"project":project,"turn_id":turn_id,
             "operation":operation,"verb":route.verb,"concept":route.concept,"altitude":route.altitude,
             **writing_verbs.requested_by_metadata(req.by),
             "target":req.target,"payload":{**values,"project":project}}
        resolution=values.get('view') in {'resolution','resolution-preview'}
        from laplace.manuscript import reconciliation
        if resolution:
            row['resolution_read']=reconciliation.resolution_read_guard(result)
            result=reconciliation.native_resolution(result,values,values.get('read_id') or row['id'])
        elif result.get('proposal_version') and isinstance(result.get('edits'),list):result=reconciliation.native_candidate(result)
        row.update(reads.record_read_basis(operation,result,row['payload'],project=project))
        _bank_talk_row(root,row)
        result={**result,"read_receipt":{key:row[key] for key in
            (('id','turn_id','project','operation','output_sha256') if resolution else ('id','turn_id','project','operation','payload','output_sha256'))}}
    elif result.get('proposal_version') and isinstance(result.get('edits'),list):
        from laplace.manuscript.reconciliation import native_candidate
        result=native_candidate(result)
    return result


def _request_owner_refusal(root: Path, project: str, turn_id: str | None, req, route, operation: str, payload: dict,
                           attempt: dict, error: BaseException) -> dict:
    """An owner refusal in the grammar's refusal shape, banked once with its raising owner frames."""
    from laplace.core import grammar as g
    from laplace.native import declarations as writing_declarations, verbs as writing_verbs
    if isinstance(error,writing_declarations.PayloadAdmissionError):
        return _record_request_refusal(root,project,turn_id,operation,attempt,error,error.response(),requested_by=req.by)
    details = error.details if isinstance(error, OwnerError) else {}
    effect_details = _effect_error_details(error)
    if effect_details:
        return {**details, **effect_details, "ok":False, "operation":operation, "error":str(error)}
    if details.get("source_effect_retained") is True:
        # An owner-observed source effect with unproved tracking is not a
        # pre-effect identity refusal. Preserve its exact receipts and cure;
        # do not fabricate full operation success or invite effect replay.
        return {**details, "ok": False, "operation": operation}
    from laplace.core import identity_doors
    answer = identity_doors.body(error, {"ok": False, "error": str(error)})
    # Preserve the owner's comparison and cure across both exception and HTTP
    # transports. Only a refusal without that evidence needs a diagnostic read.
    if "refused" not in answer:
        kind = "identity-stale" if any(word in str(error).lower() for word in
                                      ("revision", "digest", "conflict")) else "shape"
        needed, homes = writing_verbs.account(req, root=root, project=project, route=route)
        refusal = g.Refusal(kind=kind, homes=homes, said=str(error)[:400],
                            needed=needed or {"expected": []})
        answer = refusal.response()
    raised, chain = _owner_frames(error)
    answer["refused"]["owner"] = {"operation": operation, "owner": route.owner,
                                  "site": route.site, "raised": raised, "chain": chain,
                                  **{k: details[k] for k in
                                     ("recovery",) if k in details}}
    answer["banked_row"] = writing_verbs.classify(operation, payload, project=project,
                                                  root=root).row
    return _record_request_refusal(root,project,turn_id,operation,payload,error,answer,requested_by=req.by)


def _request_scope_refusal(root: Path, project: str, request, route, said: str) -> dict:
    """Refuse before a legacy conversion erases a canonical home id.

    The route-only check is free on valid requests.  This path runs only after a mismatch and
    reads the route-declared homes through the existing account resolver for the exact cure.
    """
    from laplace.core import grammar as g, identity_doors
    from laplace.native import verbs as writing_verbs
    needed, homes = writing_verbs.account(
        request, root=root, project=project, route=route)
    observed = {}
    for row in homes:
        if row.get("current_token"):
            token = g.parse(row["current_token"]); observed[token.kind] = token
    try:
        g.require(request.expected, [str(token) for token in observed.values()])
    except g.Refused as error:
        refusal = identity_doors.current_home_cure(error.refusal, observed)
    else:
        refusal = g.Refusal(kind="shape", homes=homes, needed=needed, said=said)
    answer = refusal.response()
    answer["refused"]["owner"] = {
        "operation": route.operation, "owner": route.owner, "site": route.site,
        "raised": None, "chain": []}
    answer["banked_row"] = {
        "verb": route.verb, "concept": route.concept, "altitude": route.altitude,
        "target": request.target, "dispatch": "fell-through",
        "dispatch_reason": said}
    return answer


def bank_failure(root: Path, project: str, operation, payload, error, turn_id=None, *,
                 error_type=None, provider=None, tool_use_id=None, recovery=None, requested_by="") -> dict:
    """THE failure row: one producer, one bound, one shape, for every transport.

    It used to be three sites with two shapes and TWO bounds between them: the stdio
    adapter replaced a payload over 16,000 characters with {truncated, sha256, preview},
    the Codex handler banked an unbounded payload (measured at 18,152 characters where the
    stdio row was 4,125), and the Claude permission denial banked the only row that carried
    `provider` and `tool_use_id`.  The shape is the contract's
    (`writing_operating.session_policy()['failure_receipt']`); the caller supplies only
    what it knows.

    THE BOUND IS THE SEAM'S, AND THERE IS ONLY ONE (WRITING-CONSOLIDATION-W1, the whole
    synthesis).  This row goes through `_bank_talk_row` like every other writing row, so
    `_CUSTODY_FIELDS['writing-tool-failure'] = ('payload','error')` finally governs the row
    it names: over `_CUSTODY_MIN_BYTES` the field becomes a handle into
    `contract/writing_bodies` that every reader already resolves, and the request comes back
    exactly.  The hand-rolled truncation is DELETED rather than kept beside it -- it
    replaced the request instead of storing it, so the row could neither replay nor return
    the author's own words, which is the defect the storage lane was opened for.  A
    character ceiling survives on `operation` alone, because that field is an identifier and
    not a body.

    Returns {'row_id', 'note'}: `note` is non-empty only when the receipt itself could not
    be written, which the caller may carry into its reply rather than lose.
    """
    from laplace.writing import operating as writing_operating
    from laplace.native import verbs as writing_verbs
    receipt = writing_operating.session_policy()['failure_receipt']
    operation = str(operation or '')[:receipt['operation_chars_max']]
    row = {'record': receipt['row'], 'id': 'TOOLFAIL-' + uuid.uuid4().hex,
           'project': project, 'turn_id': turn_id, 'operation': operation,
           'payload': payload,
           'error_type': error_type or type(error).__name__,
           'error': str(error),
           'provider': provider, 'tool_use_id': tool_use_id}
    effect_details = _effect_error_details(error)
    recovery = dict(recovery) if isinstance(recovery, dict) else {}
    for key, value in effect_details.items():
        recovery.setdefault(key, value)
    if recovery:
        row['recovery']=recovery
        for key in ('next_reads','consumed_read_recovery'):
            if key in recovery:row[key]=recovery[key]
    try:
        row.update(writing_verbs.requested_by_metadata(requested_by))
        (Path(root) / 'contract').mkdir(parents=True, exist_ok=True)
        _bank_talk_row(Path(root), row)
    except Exception as logging_error:                                      # noqa: BLE001
        return {'row_id': None,
                'note': 'failure receipt unavailable: ' + str(logging_error)[:500]}
    return {'row_id': row['id'], 'note': ''}


def tool_failure(root: Path, project: str, mode: str, operation, payload, error,
                 turn_id=None, *, provider=None, tool_use_id=None) -> dict:
    """The banked row AND the repair body, for a transport that must answer the model. An exception that escaped
    writing_tools.call carries its invocation (delivery.carry): the failure is finished for that admitted act, its
    resolved operation, payload, profile and attribution, whatever spelling the transport caught it under."""
    from laplace.writing import delivery, source_execution
    with delivery.invocation(delivery.carried(error)) as invocation:
        if isinstance(error, source_execution.AllowanceRefused):
            holder = invocation['native']
            standing = error.source_allowance if holder.source_unknown or not holder.source_attachment else source_execution.status(root,holder.source_attachment)
            return {'ok':False,'error':str(error),'source_allowance':standing}

        act = invocation['act']
        if act:
            operation, payload = act['operation'], act['payload']
        holder = invocation['native']
        if delivery.carried(error) is None and holder.source_claim:
            source_execution.settle_native(root,holder,'DELIVERY_UNCERTAIN')
        answer = _tool_failure(root, project, mode, operation, payload, error, turn_id, act=act,
                               provider=provider, tool_use_id=tool_use_id)
        if holder.source_attachment:
            answer = {**answer,'source_allowance':source_execution.status(root,holder.source_attachment)}
            answer = delivery.admit(answer,act['profile'] if act else delivery.profile(operation,payload if isinstance(payload,dict) else None))
        return answer


def _tool_failure(root, project, mode, operation, payload, error, turn_id, *, act, provider, tool_use_id):
    from laplace.native.declarations import PayloadAdmissionError
    from laplace.writing import delivery
    # every refusal, like every success, leaves through the one final admission (writing.delivery, step 5)
    bound = act['profile'] if act else delivery.profile(operation, payload if isinstance(payload, dict) else None)
    requested_by = getattr(error, "requested_by", "") or ((act or {}).get("requested_by") or {}).get("text", "")
    if isinstance(error,PayloadAdmissionError):
        answer = _record_request_refusal(root,project,turn_id,error.operation,getattr(error,"attempt_payload",payload),error,error.response(),requested_by=error.requested_by)
        return delivery.admit(_with_project_updates(root,project,turn_id,answer,bound=bound),bound)
    try:
        recovery = failure_response(root, project, mode, str(operation or ''), payload, error,
                                    turn_id)
    except Exception as formatting_error:  # preserve the original failure even if help is unavailable
        recovery = {'ok':False,'operation':str(operation or ''),'error':str(error),
                    'recovery_unavailable':type(formatting_error).__name__+': '+str(formatting_error)[:500]}
        from laplace.work import project_work
        if isinstance(error,project_work.WorkConflict):recovery.update(error.details)
    receipt = bank_failure(root, project, operation, payload, error, turn_id,
                           provider=provider, tool_use_id=tool_use_id,recovery=recovery,
                           requested_by=requested_by)
    if receipt['note']:
        recovery['failure_receipt_note'] = str(error)[:4000] + '; ' + receipt['note']
    return delivery.admit(_with_project_updates(root,project,turn_id,_failure_receipt_result(recovery,receipt),bound=bound),bound)


def _bounded_reads(items, budget=6000):
    """The failure response's one read bound: at most 8 handles, each at most 1600 encoded characters, 6000 in total."""
    kept, omitted = [], 0
    for read in items:
        encoded = json.dumps(read, ensure_ascii=False, default=str)
        if len(kept) >= 8 or len(encoded) > 1600 or len(encoded) > budget:
            omitted += 1
            continue
        kept.append(read)
        budget -= len(encoded)
    return kept, omitted


def failure_response(root: Path, project: str, mode: str, operation: str, payload, error: Exception, turn_id=None) -> dict:
    """Bounded, non-mutating repair guidance shared by both provider adapters."""
    from laplace.native import declarations as writing_declarations
    operation = str(operation or "")
    payload = payload if isinstance(payload,dict) else {}
    message = str(error)[:4000]
    response = {"ok":False,"operation":operation,"error":message}
    # `retry_instruction` is DELETED.  It was a sentence built here, in the response formatter,
    # which is why it reached two of the four caller paths (its callers at 87ece9da were
    # :1240 and writing_provider.py:555; they are now :1241 and `tool_failure` at :1231,
    # which both adapters call); a direct `execute` caller and an HTTP caller got neither it
    # nor the recovery revision -- synthesis.md §1.10).  Its replacement is `refused.needed`,
    # which `identity_doors.gate` builds inside THE COMPARISON, so it exists wherever the
    # refusal exists and cannot be reachable from one path only.  A caller retries with
    # {**payload, **refused.needed} and guesses nothing.
    from laplace.core import identity_doors
    response = identity_doors.body(error, response)
    response.update(_effect_error_details(error))
    from laplace.work import project_work
    if isinstance(error,project_work.WorkConflict):
        response.update(error.details)
    # The owner's typed recovery reads (WorkConflict details.next_reads) are authoritative: they lead the bounded
    # next_reads below, deduplicated, and a generic per-operation suggestion may only follow them, never replace them.
    # Only exact handles the shared classifier calls a read survive; a write-shaped entry never becomes a next read.
    owner_reads=[]
    if isinstance(error,project_work.WorkConflict):
        for item in error.details.get('next_reads') or []:
            if not isinstance(item,dict) or item.get('operation') not in READS|WRITES or not isinstance(item.get('payload'),dict):continue
            try:
                if reads.effect(item['operation'],item['payload'])!='read':continue
            except Exception:
                continue
            if item not in owner_reads:owner_reads.append(item)
        # The owner's raw list never survives: only its filtered, read-classified, bounded handles (possibly none) remain,
        # including on the unknown-operation early return below.
        response['next_reads']=_bounded_reads(owner_reads)[0]
    # Owned observations survive opaque wrappers; wording is only the legacy
    # fallback discriminator, never the authority for carrying a typed refusal.
    from laplace.writing import turn_reads
    from laplace.manuscript import proposal_currentness
    owner_recovery=proposal_currentness.proposal_refusal_details(error).get('consumed_read_recovery')
    if owner_recovery:
        response['consumed_read_recovery']=owner_recovery
        response['next_reads']=owner_recovery.get('next_reads') or []
    if isinstance(error,OwnerError):
        response.update({key:error.details[key] for key in
                         ("revision","mutation_revision","source_revision","recovery") if key in error.details})
    if operation not in READS | WRITES:
        response["help"]={"operation":"help","payload":{}}
        return response
    contract_operation=operation
    if operation=="help":
        requested=payload.get("operation") or payload.get("topic") or payload.get("request")
        if isinstance(requested,str) and requested in READS|WRITES:contract_operation=requested
    response["help"]={"operation":"help","payload":{"operation":contract_operation}}
    permitted = mode != "review" or reads.effect(contract_operation, payload) == 'read' or contract_operation in {"note","note_status","task","work_review"}
    if not permitted:
        # Independent review's refusal to store artifacts or change source is a permission,
        # not a dead end: the findings go through the doors review DOES hold, and the
        # artifact itself is author follow-through (dossier 2026-10-13, RW-20261013-141729).
        response["review_routes"]={
            "findings":{"operation":"note","payload":{"kind":"note","scope":"project","text":"<findings, with the exact edition/page anchors>"}},
            "follow_up":{"operation":"task","payload":{"title":"<correction or artifact the author should produce>","goal":"<what the author stores or changes, naming the note id>"}},
            "reply_to":"a second note may carry reply_to:<first note receipt id> to thread findings",
            "author_follow_through":"the reviewed project's author stores any requested artifact from these notes; review mode writes no reviewed artifact unless an admitted dispatch judge publishes its own declared return path (help store_artifact names it)"}
    # The repair block is the declaration, rendered for the variant the caller actually
    # sent, with this project's live tokens in `expected`.  Everything this function used
    # to do by hand is now one call: it chose a variant out of the oneOf, looked up a
    # hand-written example for it, and when there was none built a template with its own
    # second example generator (the old :1120-1131).  `expected` is what makes the block a
    # resolver rather than an instruction --- the measurement is that `retry_instruction`
    # reaches two caller paths of four because it is built in the response formatter, and
    # a token minted from the home reaches every path because it is built in the
    # comparison (synthesis.md section 1.10).
    resolved = writing_declarations.supported_suboperation(
        contract_operation, {} if operation == "help" else payload)
    suboperation = resolved["supplied"]
    table = writing_declarations.variants(contract_operation)
    variant = resolved["variant"]
    action=writing_declarations.help_payload(
        contract_operation,permitted=permitted,project=project,root=root,
        variant=variant,payload=payload)
    if variant:
        # ONE name for the chosen variant. This response used to carry `selected_kind`
        # for visual_create and `selected_suboperation` for everything else -- two names
        # for one fact, which is the defect this lane exists to end.
        action["selected_variant"]=variant
    elif resolved["supported"]:
        action["selected_suboperation"] = suboperation
    elif suboperation and resolved["choices"]:
        action["unknown_suboperation"] = suboperation
        action["choose_from"] = resolved["choices"]
    if "input" in action and len(json.dumps(action,ensure_ascii=False,default=str))>9500:
        # An unknown variant needs its chooser, not every nested schema body. The
        # matching variant is one help call away and the response names it.
        schema=action.pop("input",{})
        action["input_summary"]=({"operation_variants":[{"operation":name,"required":row.get("required",[])}
                                                        for name,row in sorted(table.items())]}
                                if table else {"required":schema.get("required",[]),
                                               "property_names":sorted(schema.get("properties",{}))})
        action["input_summary_note"]="Full nested schema omitted from this failure response; use the exact help call."
        action["full_schema"]=response["help"]
    response["contract"]=action
    # `suggested`, never `reads`: that name is the imported owner module used above (reads.effect); a local list of the
    # same name made it function-local and raised UnboundLocalError on every review-mode failure.
    suggested=[]
    def add(op,values):
        item={"operation":op,"payload":values}
        if item not in suggested and op in READS:suggested.append(item)
    if operation in {"apply_revision","propose_revision"}:
        proposal=payload.get("proposal",payload)
        if isinstance(proposal,dict):
            files=list(dict.fromkeys(str(edit.get("file")) for edit in proposal.get("edits",[]) if isinstance(edit,dict) and isinstance(edit.get("file"),str) and edit.get("file")))[:8]
            if files:
                if turn_id:
                    from laplace.manuscript import proposal_preflight
                    turn=writing_records.fold_records(root).get('turns',{}).get(turn_id) or {}
                    if turn.get('project')==project:
                        files=proposal_preflight.canonical_consumed_files(Path(root).resolve(),project,turn,files)
                add("source",{"files":files})
    elif operation in {"structure_change","section_change","chapter","block_change"}:
        add("structure",{})
        raw=payload.get("source_file") or (payload.get("block") or {}).get("file") if isinstance(payload.get("block",{}),dict) else payload.get("source_file")
        if raw:add("source",{"files":[raw]})
    elif operation in {"concept_change","logical_plan_change"}:
        node=payload.get("node") or payload.get("id")
        add("logical_plan",{"node":node} if node and suboperation not in {"add_node","add_object"} else {})
        if operation=="concept_change":add("concept",{"node":node} if node and suboperation!="add_node" else {})
    elif operation=="literature_bind":
        if payload.get("claim_id") and "claim_id must identify" not in message:add("concept",{"node":payload["claim_id"]})
        else:add("logical_plan",{})
        if payload.get("key"):add("reference_text",{"key":payload["key"]})
        else:add("references_attached",{})
    elif operation in {"task","task_status","work_review","dispatch_plan","dispatch_launch","dispatch_continue","development_source","work_delivery"}:add("project",{})
    elif operation in {"research_record","research_producer","research_reconcile"}:add("research",{})
    elif operation in {'visual_create','visual_render','visual_place'}:
        ident=payload.get('id') or ((payload.get('spec') or {}).get('id') if isinstance(payload.get('spec'),dict) else None)
        add('visuals',{'id':ident} if isinstance(ident,str) and ident else {'view':'index'})
        if operation=='visual_place':
            target=payload.get('file') or payload.get('section')
            if target:add('source',{'files':[target]})
    elif operation=="proof_check":add("proofs",{});add("proof_targets",{"node":payload["concept"]} if payload.get("concept") else {})
    # Return the exact old scope when a narrow replacement would leave another
    # consulted read stale. These are pure replays, never observation writes.
    context_reads=[];observed_reads=(owner_recovery.get('next_reads') or []) if owner_recovery else []
    if turn_id and (owner_recovery or any(word in message.lower() for word in ("changed","stale","conflict","consumed"))):
        try:
            helper=getattr(turn_reads,'failure_recovery_reads',None)
            if helper:
                recovered=(helper(root,project,turn_id,operation,payload,message,
                    observed_context_reasons=owner_recovery.get('context_reasons') or [],include_named_reads=False)
                    if owner_recovery else helper(root,project,turn_id,operation,payload,message))
                context_reads=[{"operation":item["operation"],"payload":{
                    key:value for key,value in (item.get("payload") or {}).items() if key!="project"}}
                    for item in recovered.get("reads") or [] if item.get("operation") in READS]
                reasons=(recovered.get("context_reasons") or [])[:12]
                if reasons:
                    response["context_reasons"]=reasons
                    correction_ids=[reason.partition(":")[2] for reason in reasons
                                    if str(reason).startswith("correction-unconsumed:")]
                    response["recovery_cause"]={"kind":"unconsumed-author-correction"
                        if correction_ids else "turn-context-changed",
                        "correction_ids":correction_ids,"reasons":reasons,
                        "required_reads":context_reads}
                    # The second `retry_instruction`, also deleted.  `recovery_cause` already
                    # carries the kind, the correction ids and `required_reads`; the sentence
                    # repeated them in prose and, like the first one, only on this path.
                    response["recovery_cause"]["retry"]={"reads":context_reads,
                        "then":"resend the same act with the identities those reads publish "
                               "in their `identities` block"}
                for item in context_reads:add(item["operation"],item["payload"])
            turn=writing_records.fold_records(root).get("turns",{}).get(turn_id) or {}
            import re
            families=stale_evidence_families(message)
            if families and not owner_recovery:
                observations=[]
                for read in (turn.get("tool_reads") or {}).values():
                    if read.get("operation") not in families:continue
                    try:
                        value=replay_read(root,project,mode,read,turn_id)
                        digest=reads.comparison_digest(read["operation"],value,read,root=root)
                        state='UNAVAILABLE' if isinstance(value,dict) and value.get('exists') is False else 'CHANGED'
                    except (OSError,ValueError):digest=None;state='UNAVAILABLE';value=None
                    if digest!=reads.consumed_digest(read):
                        observations.append(proposal_currentness.read_currentness_observation(read,value,digest,state))
                fallback=proposal_currentness.consumed_read_recovery(turn,
                    {'record_id':turn_id,'tool_reads':turn.get('tool_reads') or {}},observations)
                response['consumed_read_recovery']={**fallback,'observation_source':'fallback diagnostic replay; no validation observation carried'}
                observed_reads=fallback.get('next_reads') or []
        except (OSError,ValueError,KeyError,TypeError):
            response["recovery_note"]="Current read recovery is unavailable; use the exact operation help and inspect current project state."
    priority=list(owner_reads)
    for item in observed_reads+context_reads:
        if item not in priority:priority.append(item)
    if priority:
        suggested=priority+[item for item in suggested if item not in priority]
    bounded_reads=[];omitted=0;budget=6000
    for read in suggested:
        encoded=json.dumps(read,ensure_ascii=False,default=str)
        if len(bounded_reads)>=8 or len(encoded)>1600 or len(encoded)>budget:omitted+=1;continue
        bounded_reads.append(read);budget-=len(encoded)
    if bounded_reads or isinstance(error,project_work.WorkConflict):response["next_reads"]=bounded_reads
    if omitted:response["recovery_reads_omitted"]={"count":omitted,"reason":"Exact payload exceeds the bounded failure response. Inspect the named operation with help and read the actual file using source files/line bounds."}
    advice=routing_advice_for_refusal(message)
    if advice is not None:response["routing_advice"]=advice
    return response


# The two advisory seams of the `jev-routing` lane.  Both are OFF unless
# LAPLACE_ROUTING_ADVISOR is set in the environment, and the OFF path is one
# `os.environ` read and a return: no laplace import, no module loaded, nothing
# touched, which `test_the_off_path_loads_no_module` asserts over `sys.modules`.
# The lane's replay parity run measures the response BYTES, which is a weaker
# statement than that, so the import order is what makes the stronger one true.
# Neither seam can act --- `laplace.native.routing` returns a suggestion and its import
# closure contains no owner (tests/test_routing.py).
#
# The flag NAME is spelled here, not imported, precisely so that reading it costs
# no import; `test_the_two_spellings_of_the_flag_agree` fails if this spelling or
# these truth values ever differ from `laplace.native.routing.ADVISOR_FLAG` and
# `laplace.native.routing.enabled`, so the duplication cannot drift in silence.
ROUTING_ADVISOR_FLAG="LAPLACE_ROUTING_ADVISOR"
ROUTING_FLAG_TRUE={"1","true","yes","on"}
# One line per distinct advisor failure, appended once and never raised: a seam that
# swallowed an ImportError in silence would hide a grammar module that is absent or
# raises at import --- a live possibility, since the grammar is a stage-1 artefact the
# lanes install by `cp`.  Read it with `routing_advisor_notices()`.
_ROUTING_NOTICES={}


def routing_advisor_flag_on():
    """The flag, read straight from the environment.  No import on the off path."""
    import os
    return str(os.environ.get(ROUTING_ADVISOR_FLAG,"")).strip().lower() in ROUTING_FLAG_TRUE


def routing_advisor_notices():
    """The distinct advisor failures this process has seen; empty when nothing failed."""
    return dict(_ROUTING_NOTICES)


def _note_routing_failure(where:str,exc:BaseException):
    """Record one advisor failure per (site, exception class, text); never raise."""
    key="%s/%s/%s"%(where,type(exc).__name__,exc)
    if key not in _ROUTING_NOTICES:
        _ROUTING_NOTICES[key]={"where":where,"error_class":type(exc).__name__,
                               "message":str(exc)[:400],"advice":"the routing advisor is "
                               "flagged on and silent; this is why. Fix the deposit or "
                               "unset "+ROUTING_ADVISOR_FLAG+"."}
    return None


def routing_advice_for_refusal(message:str):
    """D4, in the refusal path: which KIND of refusal this is, and the read that cures it.

    The live decision beside it is the four-word substring test at
    src/laplace/writing_tools.py:1576, which answers 'recover the turn context' or
    nothing at all; on the 286 labelled refusals it names a kind for 110 and is silent
    on 171.  This names one of the grammar's four kinds with a calibrated probability
    and abstains below the threshold, in which case the whole contract is returned ---
    which :1592 already does by size."""
    if not routing_advisor_flag_on():return None
    try:
        from laplace.native import routing
    except Exception as exc:
        return _note_routing_failure("import-routing-d4",exc)
    try:
        decider=_routing_head("d4")
        if decider is None:return None
        return routing.advise_refusal(message,decider=decider).as_row()
    except Exception as exc:
        return _note_routing_failure("advise-d4",exc)


# Keyed on (which, resolved path, st_mtime_ns, st_size), so a head that arrives, is
# replaced or is rewritten after the first refusal of the process IS picked up: the
# deposit this lane calls refittable is refittable in a running server.  Nothing
# negative is cached, so a transient read failure is not permanent.  At most one entry
# per `which` is kept, so a server that refits in a loop does not grow.
_ROUTING_HEADS={}
ROUTING_HEAD_ENV={"d1":"LAPLACE_ROUTING_HEAD_D1","d4":"LAPLACE_ROUTING_HEAD_D4"}


def _routing_head(which:str):
    """The fitted head, read from the JSONL the lane deposits; never trained in a door.

    Two heads, two env paths, because D1 scores payload features and D4 scores refusal
    prose.  A missing or unreadable file means no advice --- never an exception and never
    a guess.  The fit is memoised against the FILE'S IDENTITY, not against `which`: the
    key carries the resolved path, its mtime in ns and its size, so pointing
    LAPLACE_ROUTING_HEAD_D4 at a different deposit, or rewriting the deposit in place,
    refits on the next call rather than at the next restart."""
    import os
    path=os.environ.get(ROUTING_HEAD_ENV[which],"")
    if not path:return None
    try:
        source=Path(path)
        stat=source.stat()
        if not source.is_file():return None
        key=(which,str(source.resolve()),stat.st_mtime_ns,stat.st_size)
        held=_ROUTING_HEADS.get(key)
        if held is not None:return held
        from laplace.native import routing
        rows=[json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        if which=="d4":
            examples=[(routing.refusal_features(row["error"]),row["label"]) for row in rows]
        else:
            examples=[(routing.features(routing.RouteState(**row["state"])),row["label"])
                      for row in rows]
        head=routing.PriorDecider(name="prior/"+which).fit(examples)
        for stale in [k for k in _ROUTING_HEADS if k[0]==which]:del _ROUTING_HEADS[stale]
        _ROUTING_HEADS[key]=head
        return head
    except Exception as exc:
        return _note_routing_failure("head-"+which,exc)


def routing_advice_for_request(door:str,mode:str,payload:dict,target:str="",path:str=""):
    """D1, BEFORE the call: the (verb, concept) pair this request is, or an abstention.

    This is the pre-call seam.  It is deliberately not inside `_execute`
    (src/laplace/writing_tools.py:181): a pre-call advisor that ran inside the door it
    advises would be advising after the route was chosen.  A caller asks this, reads
    the suggestion or the abstention, and then calls the door exactly as it does
    today; the owners' guards are untouched, so a wrong suggestion costs a refusal and
    never a write."""
    if not routing_advisor_flag_on():return None
    try:
        from laplace.native import routing
    except Exception as exc:
        return _note_routing_failure("import-routing-d1",exc)
    try:
        decider=_routing_head("d1")
        if decider is None:return None
        state=routing.RouteState(door=door,mode=mode,payload=payload or {},target=target,path=path)
        return routing.advise(state,decider=decider).as_row()
    except Exception as exc:
        return _note_routing_failure("advise-d1",exc)

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--turn-id")
    parser.add_argument("--mode", choices=("discuss", "revise", "work", "review"), default="discuss")
    parser.add_argument("--dispatch-id",
                        help="THE CHILD'S OWN ENTRY for its dispatch membership, passed by "
                             "`authoring_surface.launch_dispatch` through "
                             "`start_turn`'s detached host and never readable from a turn "
                             "request's body, which `start_turn` refuses outright.")
    parser.add_argument("--parent-turn-id",
                        help="The dispatching turn this child belongs to; same entry, same "
                             "reason as --dispatch-id.")
    parser.add_argument("--start-child-turn", action="store_true",
                        help="ONE-SHOT HOST for a dispatched child's turn instead of the MCP "
                             "loop: read the turn payload from stdin, start it in THIS "
                             "process, print {session_id, turn_id} on stdout, and stay alive "
                             "until the turn it started is finished. "
                             "`authoring_surface.start_turn` spawns this, detached, for every "
                             "child of a dispatch, because a turn is supervised by the "
                             "process that started it and the parent's own adapter dies with "
                             "the parent's turn (research_surface.py:1609 is the same move "
                             "for a research run).")
    parser.add_argument("--source-event",
                        help="With --start-child-turn: THE ONE-SHOT HOST of a Work delivery's Source review "
                             "(turn_admission.start_source_turn, called from the transient adapter). Only the "
                             "event id travels; the host replays its canonical reservation "
                             "(work_delivery.start_source_review) and refuses any other request.")
    parser.add_argument("--source-return",
                        help="With --start-child-turn: THE ONE-SHOT HOST of a settled Source event's once-only return "
                             "into its original parent session; replays only the already-banked continuation "
                             "reservation (work_delivery.start_source_return).")
    args = parser.parse_args(argv)
    if args.start_child_turn:
        # No MCP envelope here: one turn, one answer, then this process waits for the turn it
        # started.  `_CHILD_HOST` is what stops `start_turn` detaching again, and the wait is
        # the job's OWN completion through `active_turn_count` -- no bound of this module's,
        # because nothing may hand-set a dispatch's budget.  A Source review host does NOT set
        # `_CHILD_HOST`: that flag skips the cross-process RUNNING check of a session, and this
        # host admits the reviewer's once-only parent continuation, which must still defer to a
        # parent turn running in another process.
        import time
        from laplace.writing import turn_execution, turn_jobs
        payload = json.loads(sys.stdin.read() or "{}")
        try:
            if args.source_event or args.source_return:
                from laplace.work import work_delivery
                started = (work_delivery.start_source_review(Path(args.root), args.project, args.source_event, payload) if args.source_event
                           else work_delivery.start_source_return(Path(args.root), args.project, args.source_return, payload))
            else:
                turn_jobs.set_child_host(True)
                from laplace.writing import turn_admission
                started = turn_admission.start_turn(
                    Path(args.root), payload,
                    dispatch={key: value for key, value in
                              (("dispatch_id", args.dispatch_id),
                               ("parent_turn_id", args.parent_turn_id)) if value} or None)
        except Exception as exc:
            print(json.dumps({"error": "%s: %s" % (type(exc).__name__, exc)}), flush=True)
            return 1
        print(json.dumps({key: started.get(key) for key in ("turn_id", "session_id")}),
              flush=True)
        sys.stdout.close()
        # The turn threads, not only their jobs: settlement and the parent return run after job.done.
        while turn_execution.running() or any(not job["done"] for job in turn_jobs._JOBS.values()):
            time.sleep(0.5)
        return 0
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if "id" not in request:
                continue
            method = request.get("method")
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                          "serverInfo": {"name": "laplace-project", "version": "1"}}
            elif method == "tools/list":
                result = {"tools": [{"name": "laplace_project", "description": DESCRIPTION,
                                      "inputSchema": INPUT_SCHEMA}]}
            elif method == "tools/call":
                params = request.get("params") or {}
                if params.get("name") != "laplace_project":
                    raise ValueError("Unknown project tool.")
                from laplace.writing import delivery
                with delivery.incoming(transport_kind='claude-mcp',request_id=request['id']) as holder:
                    fields = params.get("arguments", {})
                    try:
                        output = call(Path(args.root), args.project, args.mode, fields, turn_id=args.turn_id, _incoming=holder)
                        from laplace.projects.writing_sources import content_items
                        result = {"content": content_items(output, "claude")}
                    except Exception as exc:
                        if delivery.carried(exc) is None:delivery.delivery_uncertain(holder)
                        fields_dict=fields if isinstance(fields,dict) else {}
                        recovery=tool_failure(Path(args.root),args.project,args.mode,
                                              fields_dict.get('operation'),fields_dict.get('payload'),exc,args.turn_id)
                        result = {"isError": True, "content": [{"type": "text", "text": json.dumps(recovery,ensure_ascii=False,default=str)}]}
                    print(json.dumps({"jsonrpc":"2.0","id":request['id'],"result":result}),flush=True)
                continue
            elif method == "ping":
                result = {}
            else:
                raise ValueError("Unsupported MCP method.")
            print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
        except Exception as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": locals().get("request", {}).get("id"),
                              "error": {"code": -32602, "message": str(exc)}}), flush=True)




if __name__ == "__main__":
    main()
