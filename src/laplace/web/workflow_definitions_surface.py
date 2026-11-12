"""The local owned-workspace HTTP door to pipeline.workflow definitions."""
from __future__ import annotations
import json
from laplace.pipeline import workflow_definitions as owner
from laplace.work import owner_discovery


def handle(path, query, method, body=b'', repo_root=None):
    scope = owner_discovery.owned_workspace('http')
    try:
        if any(isinstance(value,list) and len(value)!=1 for value in query.values()):
            raise owner.Refused('DUPLICATE_WORKFLOW_QUERY')
        lens=query.get('project_lens')
        if lens is not None:
            from laplace.pipeline import registry
            if isinstance(lens,list):
                if len(lens)!=1:raise owner.Refused('PROJECT_LENS_NOT_IN_SCOPE')
                lens=lens[0]
            if not isinstance(lens,str) or lens not in registry.all_projects(repo_root=repo_root):raise owner.Refused('PROJECT_LENS_NOT_IN_SCOPE')
            scope=owner_discovery.project_scope(lens,'http')
        if path == '/work/workflow-definitions' and method == 'GET':
            payload = {key: value[0] if isinstance(value, list) else value for key, value in query.items()}
            for key in ('offset', 'limit', 'fan_out_max','body_offset','body_limit','capture_max_bytes','metadata_max_rows'):
                if key in payload:
                    payload[key] = int(payload[key])
            if 'reference' in payload:
                payload['reference'] = json.loads(payload['reference'],object_pairs_hook=owner.W._unique)
            for key in ('step_ids','inputs','selection','definition','scope','original_request'):
                if key in payload:payload[key]=json.loads(payload[key],object_pairs_hook=owner.W._unique)
            result = owner.read(repo_root, scope, payload)
        elif method == 'POST' and path == '/work/workflow-definitions':
            from laplace.pipeline import workflow_operations
            if len(body) > 1_000_000:
                raise owner.Refused('REQUEST_TOO_LARGE')
            payload = json.loads(body, object_pairs_hook=owner.W._unique)
            if not isinstance(payload, dict) or payload.get('facet') not in workflow_operations.FACETS:
                raise owner.Refused('INVALID_OPERATION_READ')
            body_lens = payload.get('project_lens')
            if body_lens is not None:
                from laplace.pipeline import registry
                if lens is not None and body_lens != lens:
                    raise owner.Refused('PROJECT_LENS_NOT_IN_SCOPE')
                if not isinstance(body_lens, str) or body_lens not in registry.all_projects(repo_root=repo_root):
                    raise owner.Refused('PROJECT_LENS_NOT_IN_SCOPE')
                scope = owner_discovery.project_scope(body_lens, 'http')
            result = owner.read(repo_root, scope, payload)
            import hashlib
            from laplace.work import project_work_navigation as navigation
            result = {**result, 'transport_request': {
                'sha256': 'sha256:' + hashlib.sha256(body).hexdigest(),
                'encoding': 'utf8-exact-request-body'}}
            if navigation.emitted(result) > navigation.line():
                raise owner.Refused('WORKFLOW_OPERATION_DELIVERY_BOUND')
        elif method == 'POST' and path == '/work/workflow-definitions/withdraw':
            if len(body) > 1_000_000:
                raise owner.Refused('REQUEST_TOO_LARGE')
            payload = json.loads(body, object_pairs_hook=owner.W._unique)
            result = owner.withdraw(repo_root, scope, payload)
        elif method == 'POST' and path in {'/work/workflow-definitions/save', '/work/workflow-definitions/prepare', '/work/workflow-definitions/restore'}:
            if len(body) > 1_000_000:
                raise owner.Refused('REQUEST_TOO_LARGE')
            payload = json.loads(body)
            action = {'save': owner.save, 'prepare': owner.prepare, 'restore': owner.restore}[path.rsplit('/', 1)[1]]
            result = action(repo_root, scope, payload)
        else:
            return None
        return 200, 'application/json', json.dumps(result, ensure_ascii=False).encode()
    except (ValueError, TypeError, KeyError, owner.W.WorkflowRefused) as exc:
        details = getattr(exc, 'details', {})
        code = 409 if details.get('code') in {'STALE_EDIT', 'STALE_TARGET', 'REQUEST_CONFLICT', 'RESTORE_IDENTITY_CONFLICT'} else 422
        return code, 'application/json', json.dumps({'error': str(exc), **details}, ensure_ascii=False).encode()

    except OSError as exc:
        return 503, 'application/json', json.dumps({'error': type(exc).__name__, 'effect': 'unknown',
            'recovery': owner.handle(facet='request'), 'message': 'Reinspect the same request ID; no new request was started'}).encode()
