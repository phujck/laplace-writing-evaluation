"""Scanner-compatible HTTP adapter for project work."""
from __future__ import annotations
import json
from laplace.work import project_work as work

def materials(project, payload=None, repo_root=None):
    """Compatibility HTTP entry to the canonical metadata-only artifact catalogue."""
    from laplace.projects import artifacts
    return artifacts.catalogue(work._root(repo_root), project, payload)

def handle(path, query, method, body=b"", repo_root=None):
    if path.startswith("/work/workflow-definitions"):
        from laplace.web import workflow_definitions_surface
        return workflow_definitions_surface.handle(path, query, method, body, work._root(repo_root))
    try:
        if path == '/work/object-handover' and body:
            from laplace.pipeline.workflow import _unique,WorkflowRefused
            try:payload = json.loads(body.decode("utf-8"),object_pairs_hook=_unique)
            except WorkflowRefused as exc:raise ValueError(str(exc)) from exc
        else:
            payload = json.loads(body.decode("utf-8")) if body else {}
        raw_project = query.get("project", "")
        project = str(payload.get("project") or (raw_project[0] if isinstance(raw_project, list) and raw_project else raw_project))
        global_view=((query.get('view') or [''])[0] in {'namespaces','workflows','catalogue'} and path=='/work/state' and method=='GET') or (path=='/work/profiles' and method=='GET') or path in {'/work/discovery','/work/binding'}
        definition_only_handover=(path=='/work/object-handover' and method=='POST' and payload.get('definition_transport')=='lineage-v2')
        if not project and not global_view and not definition_only_handover: raise ValueError("project is required")
        if path == "/work/discovery" and method == "GET":
            # owner discovery (work.owner_discovery): the local HTTP door reads the owned workspace it serves; a query
            # field never widens or names the scope
            from laplace.work import owner_discovery
            fields={key:(value[0] if isinstance(value,list) else value) for key,value in query.items() if key!='project'}
            for key in ('offset','limit','budget','content_offset'):
                if key in fields:fields[key]=int(fields[key])
            if isinstance(fields.get('reference'),str) and fields['reference'].startswith('{'):fields['reference']=json.loads(fields['reference'])
            for name in ('coordinate','relations','selection','segments'):
                if isinstance(fields.get(name),str):fields[name]=json.loads(fields[name])
            if isinstance(fields.get('read'),str):fields['read']=json.loads(fields['read'])
            if isinstance(fields.get('object_request'),str):fields['object_request']=json.loads(fields['object_request'])
            code,result=200,owner_discovery.request(work._root(repo_root),owner_discovery.owned_workspace('http'),fields)
        elif path == '/work/object-change' and method == 'POST':
            from laplace.work import object_facets,owner_discovery
            code,result=200,object_facets.change(work._root(repo_root),owner_discovery.owned_workspace('http'),payload,door={'origin':'human'})
        elif path == '/work/object-handover' and method == 'POST':
            from laplace.projects import project_handover
            from laplace.work import owner_discovery
            code,result=200,project_handover.object_request(work._root(repo_root),owner_discovery.owned_workspace('http'),payload,door={'origin':'human'})
        elif path == "/work/binding" and method == "POST":
            # the human door of the Work owner's bindings: guarded by the Work specification and binding revisions
            from laplace.work import owner_discovery
            code,result=200,owner_discovery.bind(work._root(repo_root),{key:value for key,value in payload.items() if key!='project'},door={'origin':'human'})
        elif path == "/work/storage" and method == "GET":
            from laplace.projects import writing_storage
            code, result = 200, writing_storage.inspect(project, work._root(repo_root))
        elif path == "/work/storage/prune" and method == "POST":
            from laplace.projects import writing_storage
            code, result = 200, writing_storage.prune(project, payload, work._root(repo_root))
        elif path == "/work/state" and method == "GET":
            selected_view=(query.get("view") or [""])[0]
            scoped_query=any(view in {'review-evidence','provenance','continuity'} for view in (query.get('view') or []))
            guarded_phase='review' in (query.get('view') or []) and ('phase_revision' in query or 'obligation_id' in query)
            if (selected_view in {"catalogue","planning","planning-request"} or scoped_query or guarded_phase) and any(isinstance(v,list) and len(v)!=1 for v in query.values()):raise ValueError("Work query fields must occur exactly once.")
            fields={key:(value[0] if isinstance(value,list) else value) for key,value in query.items() if key!='project'}
            if fields.get('view')=='':fields.pop('view')
            for key in ('offset','limit'):
                if key in fields:fields[key]=int(fields[key])
            if selected_view in {'review-evidence','provenance','continuity'} or selected_view=='review' and ('phase_revision' in fields or 'obligation_id' in fields):
                from laplace.work import owner_discovery,project_work_views
                def closed_pairs(pairs):
                    value={}
                    for key,item in pairs:
                        if key in value:raise ValueError('Work read request keys must occur exactly once.')
                        value[key]=item
                    return value
                if selected_view in {'review-evidence','provenance','continuity'} and isinstance(fields.get('request'),str):
                    fields['request']=json.loads(fields['request'],object_pairs_hook=closed_pairs)
                code,result=200,project_work_views.read(project,fields,work._root(repo_root),
                    native_caller=owner_discovery.owned_workspace('http'))
            elif selected_view=='detail':
                # the Work owner issues continuity_read (or an explicit gap) from the actual HTTP Scope it receives
                from laplace.work import owner_discovery,project_work_views
                code,result=200,project_work_views.read(project,fields,work._root(repo_root),
                    native_caller=owner_discovery.owned_workspace('http'))
            else:code,result=200,work.read(project,fields,repo_root)
        elif path == "/work/materials" and method == "GET":
            page = {key: int((query.get(key) or [default])[0])
                    for key, default in (("offset", 0), ("limit", 20))}
            code, result = 200, materials(project, page, repo_root)
        elif path == "/work/session-preferences" and method in {"GET","POST"}:
            if 'request' in query or 'action' in payload:
                from laplace.writing import session_settings
                code,result=200,session_settings.http_request(work._root(repo_root),project,path,query,method,payload,raw_body=body)
            else:
                if method=='POST' and set(payload)-{'project','provider','model','effort'}:raise ValueError('Project defaults contain unsupported preference fields.')
                code, result = 200, work.session_preferences(project, payload if method == "POST" else None, repo_root)
        elif path == "/work/pipeline" and method == "GET":
            from laplace.manuscript import writing_pipeline
            from laplace.writing import stages as writing_stages
            pipeline_view=str((query.get("view") or ["summary"])[0])
            if pipeline_view not in {"summary","audit"}:raise ValueError("pipeline view must be summary or audit")
            result=writing_pipeline.inspect(project, work._root(repo_root),
                                            include_history=pipeline_view=="audit")
            stages=writing_stages.inspect(project,{},work._root(repo_root))
            code, result = 200, {**result,"writing_stage":{"operation":"writing_stage",
                "http":"/work/writing-stage?project="+project,
                "schema_version":stages.get("schema_version"),"revision":stages.get("revision"),
                "stages":stages.get("stages")}}
        elif path == "/work/writing-stage" and method == "GET":
            from laplace.writing import stages as writing_stages
            stage=(query.get("stage") or [""])[0];view=(query.get("view") or [""])[0]
            known=(query.get("known_revision") or [""])[0]
            stage_payload={**({"stage":stage} if stage else {}),**({"view":view} if view else {}),
                           **({"known_revision":known} if known else {})}
            code,result=200,writing_stages.inspect(project,stage_payload,work._root(repo_root))
        elif path == "/work/structure" and method == "GET":
            from laplace.manuscript import project_structure
            values={key:(value[0] if isinstance(value,list) else value) for key,value in query.items() if key not in {"project","corpus"}}
            for key in ("section_ids","sections","files","node_ids"):
                if key in values:
                    raw=values[key]
                    values[key]=json.loads(raw) if str(raw).startswith("[") else query[key] if isinstance(query[key],list) else [raw]
            for key in ("section_offset","section_limit","object_offset","object_limit","gap_offset","gap_limit","member_offset","member_limit","line_start","line_end","offset","limit","spine_offset","spine_limit","paragraph_offset","paragraph_limit"):
                if key in values:values[key]=int(values[key])
            for key in ("edit_choices", "reconcile_current"):
                if key in values:
                    if values[key] not in {"true", "false"}: raise ValueError(key + " must be true or false")
                    values[key] = values[key] == "true"
            if "current_occurrence_assignments" in values:
                values["current_occurrence_assignments"] = json.loads(values["current_occurrence_assignments"])
                if not isinstance(values["current_occurrence_assignments"], list):
                    raise ValueError("current_occurrence_assignments must be a JSON array")
            code, result = 200, project_structure.read(project, values, repo_root, http=True)
        elif path == "/work/structure/change" and method == "POST":
            from laplace.manuscript import project_structure
            code, result = 200, project_structure.change(project, payload, repo_root)
        elif path == "/work/profiles" and method == "GET":
            from laplace.manuscript import profiles
            values={key:(value[0] if isinstance(value,list) else value) for key,value in query.items() if key!="project"}
            if "candidate_ref" in values: values["candidate_ref"]=json.loads(values["candidate_ref"])
            for key in ("offset","limit"):
                if key in values: values[key]=int(values[key])
            code,result=200,profiles.inspect(project or None,values,work._root(repo_root))
        elif path == "/work/profiles/change" and method == "POST":
            from laplace.manuscript import profiles
            code,result=200,profiles.change(project,{key:value for key,value in payload.items() if key!="project"},work._root(repo_root),actor={"kind":"human"})
        elif path == "/work/writing-style" and method == "GET":
            from laplace.manuscript import writing_style
            view=(query.get("view") or [""])[0];profile=(query.get("profile") or [""])[0]
            code, result = 200, (writing_style.inspect(project,{**({"view":view} if view else {}),
                **({"profile":profile} if profile else {})},repo_root) if view or profile
                else writing_style.state(project, repo_root))
        elif path == "/work/writing-style/change" and method == "POST":
            from laplace.manuscript import writing_style
            code, result = 200, writing_style.save(project, payload, repo_root)
        elif path == "/work/writing-style/calibration" and method == "POST":
            from laplace.manuscript import writing_style
            code, result = 200, writing_style.calibration(
                project,{key:value for key,value in payload.items() if key!="project"},repo_root)
        elif path == "/work/writing-style/profile-change" and method == "POST":
            from laplace.manuscript import writing_style
            code, result = 200, writing_style.update_profile(
                project,{key:value for key,value in payload.items() if key!="project"},repo_root)
        elif path == "/work/framing" and method == "POST": code, result = 200, work.framing(project, payload, repo_root)
        elif path == "/work/task" and method == "POST": code, result = 201, work.task(project, payload, repo_root)
        elif path == "/work/style" and method == "POST": code, result = 200, work.style(project, payload, repo_root)
        elif path == "/work/style/preview" and method == "GET":
            from laplace.manuscript import document_style
            code, result = 200, document_style.status(project, repo_root)
        elif path == "/work/style/pdf" and method == "GET":
            from laplace.manuscript import document_style
            from laplace.manuscript import document_templates
            fields={key:(value[0] if isinstance(value,list) else value) for key,value in query.items()}
            ref=json.loads(fields.get('candidate_ref','null'));preview=json.loads(fields.get('preview_ref','null'))
            if fields.get('format')=='png':
                if not ref or not preview:raise document_templates.legacy_refusal(project,'Exact candidate/build/output proof is required for a preview image.')
                rendered=document_templates.inspect(project,{'view':'template','candidate_ref':ref,'preview_ref':preview,
                    'part':'preview-image','page':int(fields.get('page',1))},work._root(repo_root))
                import base64
                return 200,'image/png',base64.b64decode(rendered['_image_content'][0]['data'])
            return 200, "application/pdf", document_style.pdf(project, repo_root,candidate_ref=ref,preview_ref=preview)
        elif path == "/work/style/export" and method == "POST":
            from laplace.manuscript import document_style
            code, result = 201, document_style.export_pdf(
                project,repo_root,mode=str(payload.get("mode") or "selected-source"),candidate_ref=payload.get("candidate_ref"),preview_ref=payload.get("preview_ref"))
        elif path == "/work/transition" and method == "POST": code, result = 200, work.transition(project, payload, repo_root)
        elif path == "/work/review" and method == "POST":
            # the human door of the review lifecycle (project_work_review); the author is the recording identity
            from laplace.work import project_work_review
            code, result = 200, project_work_review.bounded_ack(project, project_work_review.record(
                project, payload, repo_root, door={"origin": "human"}, mode="work"))
        elif path == "/work/development" and method == "POST":
            # the human/admin door of the development-source owner: the ONLY issuer of a root grant (Root decision BOOTSTRAP)
            from laplace.work import development_source, development_adoption
            if payload.get("action") in development_adoption.ACTIONS:
                # preview, adopt and the adoption read of a lane (development_adoption); Adopt is this door's alone
                code, result = 200, development_adoption.handle(work._root(repo_root), project, payload, {"origin": "human"})
            else:
                code, result = 200, development_source.handle(work._root(repo_root), project, payload, {"origin": "human"})
        elif path == "/work/delivery" and method in {"GET","POST"}:
            # the human/admin door of the Work recipient delivery (bind, submit, recover, status)
            from laplace.work import work_delivery
            if method=='GET':
                if set(query)-{'project','request'} or any(isinstance(v,list) and len(v)!=1 for v in query.values()):
                    raise ValueError('Select one exact Work delivery read.')
                value=query.get('request')
                value=value[0] if isinstance(value,list) else value
                if not isinstance(value,str):raise ValueError('GET requires an exact delivery request object.')
                payload=json.loads(value)
                if not isinstance(payload,dict):raise ValueError('Delivery request must be an object.')
                if payload.get('action') not in {'route-preview','route-status','status','review-setup','renew-request','workflow-preview','workflow-status','workflow-bind-request','workflow-request','workflow-compose-start','workflow-impact-preview'}:
                    raise ValueError('This GET admits delivery inspection only.')
            code, result = 200, work_delivery.handle(work._root(repo_root), project, payload, {"origin": "human"})
        elif path == "/work/observation" and method == "POST":
            # the human attestation door of external execution observations (project_work_activity); no native twin
            from laplace.work import project_work_activity
            code, result = 200, project_work_activity.record(project, payload, repo_root, door={"origin": "human"})
        elif path == "/work/context" and method == "GET": code, result = 200, work.context(project, str((query.get("task") or [""])[0]), repo_root)
        else: return 404, "application/json", b'{"error":"unknown work endpoint"}'
        # UTF-8 bodies without \u escapes (C10-C11 H1): the serialized bytes a consumer receives are
        # the same bytes the owner's clips are measured in; non-ASCII text costs its UTF-8 length,
        # not six bytes a character
        return code, "application/json", json.dumps(result, ensure_ascii=False).encode("utf-8")  # JSON is UTF-8 by RFC 8259
    except (ValueError, json.JSONDecodeError) as exc:
        # The HTTP door's formatter.  `retry_instruction` never reached here (it was built in
        # writing_tools.failure_response, which this adapter does not call), so an HTTP caller
        # got the sentence and no value.  `identity_doors.body` splices the same `refused`
        # block the tool door serves, because the resolver is produced by the comparison.
        from laplace.core import identity_doors
        from laplace.manuscript.storyboard import plan_failure_details
        from laplace.writing.prepared_work import error_details as preparation_error_details
        from laplace.manuscript.document_templates import error_details as template_error_details
        from laplace.work.owner_discovery import DiscoveryRefusal   # a typed local discovery result: its code and next reads
        from laplace.writing.session_settings import error_details as settings_error_details
        detail=exc.details if isinstance(exc,(work.WorkConflict,DiscoveryRefusal)) else {
            **plan_failure_details(exc), **preparation_error_details(exc), **template_error_details(exc), **settings_error_details(exc)}
        if isinstance(exc,work.WorkConflict):
            return 409, "application/json", json.dumps(
                identity_doors.body(exc, {"error": str(exc),**detail})).encode("utf-8")
        return 422, "application/json", json.dumps(
            identity_doors.body(exc, {"error": str(exc),**detail})).encode("utf-8")
