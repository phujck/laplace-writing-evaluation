"""Complete selected project-data handover, using the existing closure owner.

Fresh destination only. External dependencies are standing, never copying authority.
Application source/runtime, process state and provider credentials are not payload.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import tempfile
import sys
from . import project_data as C
from laplace.core.identity import canonical_bytes, canonical_digest, revision_matches

SCHEMA = 'laplace.project-data-plan/1'
RECEIPT = 'laplace.project-data-handover/1'
MANIFEST = 'project-handover.json'
PER_FILE = 100 * 1024 * 1024
SCAN_ROWS = 100_000


class Refused(ValueError):
    def __init__(self, code, **details):
        self.details = {'code': code, **details}
        super().__init__(code + (': ' + str(details) if details else ''))


def encoded(value):
    return canonical_bytes(value) + b'\n'


def _budgets(max_files, max_rows, max_bytes):
    result = dict(max_files=max_files, max_rows=max_rows, max_bytes=max_bytes)
    if any(type(v) is not int or v <= 0 for v in result.values()):
        raise Refused('POSITIVE_BUDGETS_REQUIRED', budgets=result)
    return result


def _bounded_rows(root, relative):
    path = C._safe(root, relative)
    if not path.exists():
        return []
    if path.stat().st_size > C.MAX_JSON:
        raise Refused('LEDGER_SCAN_BOUND', file=relative, max_bytes=C.MAX_JSON)
    result = C._rows(root, relative, max_bytes=C.MAX_JSON, max_rows=SCAN_ROWS)
    if len(result) > SCAN_ROWS:
        raise Refused('LEDGER_SCAN_BOUND', file=relative, max_rows=SCAN_ROWS)
    return result



def _selected_artifact_rows(root, project, ids, *, max_rows, max_bytes):
    """Existing immutable-ID metadata/captured-row custody; no global raw-row materialisation."""
    from laplace.writing import records
    from laplace.core.records import capture
    root=Path(root);path=C._safe(root,'contract/talk.jsonl')
    if len(ids)!=len(set(ids)) or len(ids)>max_rows:raise Refused('SELECTED_ARTIFACT_ROW_BUDGET')
    def selected():
        idx=records.index(root)
        if idx.source_status!='AVAILABLE' or idx.malformed_rows or idx.offset!=path.stat().st_size:
            raise Refused('SELECTED_ARTIFACT_CUSTODY_UNKNOWN')
        meta=[]
        for ident in ids:
            matches=idx.by_id.get(ident,())
            if idx.journal_id_counts.get(ident)!=1 or len(matches)!=1:raise Refused('SELECTED_ARTIFACT_CUSTODY')
            item=matches[0]
            if item.get('record')!='writing-artifact' or item.get('project')!=project:raise Refused('SELECTED_ARTIFACT_CUSTODY')
            meta.append(dict(item))
        if sum(item['_end']-item['_offset'] for item in meta)>max_bytes:raise Refused('SELECTED_ARTIFACT_ROW_BUDGET')
        return meta
    before=selected();rows=[]
    for meta in before:
        row,raw=capture.read_captured_row(path,meta['_offset'],meta['_end'],meta['_hash'])
        if row.get('id')!=meta['id'] or row.get('record')!='writing-artifact' or row.get('project')!=project:raise Refused('SELECTED_ARTIFACT_CUSTODY')
        rows.append(('contract/talk.jsonl',meta['_order'],raw,row))
    fields=('id','project','record','_offset','_end','_order','_hash')
    if [{k:item[k] for k in fields} for item in before]!=[{k:item[k] for k in fields} for item in selected()]:
        raise Refused('SELECTED_ARTIFACT_CUT_CHANGED')
    return sorted(rows,key=lambda item:item[1])


def _objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _dependencies(root, project, entry, values, directory):
    config = C._json(C._safe(root, 'profiles/writing_sources.json'))
    declared = config.get('repositories', {})
    if not isinstance(declared, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in declared.items()):
        raise Refused('INVALID_REPOSITORY_CONFIG')
    used = {o['repository'] for v in values for o in _objects(v) if isinstance(o.get('repository'), str)}
    local, unbound, dispositions = {}, {}, []
    for alias, raw in declared.items():
        # Lexical source configuration is not permission to inspect an external root.
        absolute = Path(os.path.abspath(root / raw))
        if absolute == root:
            local[alias] = '.'
        elif absolute.is_relative_to(root / directory):
            relative = absolute.relative_to(root).as_posix()
            C._safe(root, relative)
            local[alias] = relative
        elif alias in used:
            unbound[alias] = {'reason': 'External repository requires explicit target binding; original host path omitted.'}
    for alias in sorted(used - set(local)):
        unbound.setdefault(alias, {'reason': 'Repository alias is not locally bound.'})
    # A usable self reader exists even for an initially minimal configuration.
    if not local and not declared:
        local['workspace'] = '.'
    for target in entry.get('manifest', {}).get('material_references', []):
        target = target.get('target', {})
        if target.get('owner') == 'repository':
            alias = target.get('repository')
            raw = declared.get(alias)
            absolute = Path(os.path.abspath(root / raw)) if isinstance(raw, str) else None
            relative = (absolute / str(target.get('path', ''))) if absolute is not None else None
            if alias in local and relative is not None and relative.is_relative_to(root / directory):
                safe = C._safe(root, relative.relative_to(root).as_posix())
                if not safe.is_file():
                    raise Refused('OWNED_MATERIAL_UNAVAILABLE', target=target)
            else:
                dispositions.append({'kind': 'repository-resource', 'target': target, 'status': 'UNBOUND' if alias in unbound else 'UNAVAILABLE', 'copy_permission': False})
    for alias in sorted(unbound):
        dispositions.append({'kind': 'repository', 'repository': alias, 'status': 'UNBOUND', 'copy_permission': False})
    for v in values:
        for obj in _objects(v):
            if isinstance(obj.get('owner'), str) and obj['owner'] in {'artifact', 'writing-artifact'} and obj.get('project') not in (None, project):
                dispositions.append({'kind': 'foreign-artifact', 'target': obj, 'status': 'UNAVAILABLE', 'copy_permission': False})
            if obj.get('owner') == 'domain.work' and obj.get('identity', {}).get('namespace') not in (None, project):
                dispositions.append({'kind': 'foreign-work', 'target': obj, 'status': 'UNAVAILABLE', 'copy_permission': False})
            if obj.get('owner') == 'pipeline.workflow' and obj.get('kind') == 'workflow-definition':
                dispositions.append({'kind': 'workflow-reference', 'target': obj, 'status': 'REQUIRES_OWNER_OBSERVATION', 'copy_permission': False})
    return {'repositories': local, 'unbound_repositories': unbound}, sorted({canonical_digest(d): d for d in dispositions}.values(), key=canonical_digest)


def _unique_history(rows):
    unique = {'writing-session', 'writing-turn', 'writing-reply', 'writing-tool-read', 'writing-artifact'}
    seen = set()
    for item in rows:
        row = item[3]
        if row.get('record') in unique:
            key = row['record'], row.get('id')
            if key in seen or not key[1]:
                raise Refused('AMBIGUOUS_HISTORY_ID', record=key[0], id=key[1])
            seen.add(key)


def plan(data_root, project, *, max_files, max_rows, max_bytes, selection=None, caller=None):
    """Read-only exact plan; refusals retain caller budgets and honest partial counts."""
    budgets = _budgets(max_files, max_rows, max_bytes)
    # This direct Python/CLI data owner is a trusted local boundary. Public
    # object-handover supplies its actual host Scope explicitly; JSON never does.
    if selection is not None and caller is None:
        from laplace.work.owner_discovery import owned_workspace
        caller=owned_workspace('sdk')
    try:
        return _selected_plan(data_root,project,selection,caller=caller,**budgets) if selection is not None else _plan(data_root, project, **budgets)
    except ValueError as exc:
        details = getattr(exc, 'details', None)
        if isinstance(details, dict):
            details.setdefault('budgets', budgets)
            details.setdefault('counts', {'complete': False})
            raise
        raise Refused('DATA_CLOSURE_REFUSED', reason=str(exc), budgets=budgets,
                      counts={'complete': False}) from exc


def _plan(data_root, project, *, max_files, max_rows, max_bytes):
    """Pin one complete owned-data cut. No files, locks, telemetry or providers started."""
    budgets = _budgets(max_files, max_rows, max_bytes)
    root = Path(data_root).absolute()
    if root.is_symlink() or root.resolve() != root:
        raise Refused('UNSAFE_SOURCE_ROOT')
    registry = C._json(C._safe(root, 'registry_projects.json'))
    entries = [r for r in registry.get('projects', []) if r.get('name') == project]
    if len(entries) != 1:
        raise Refused('EXACT_REGISTERED_PROJECT_REQUIRED')
    entry = entries[0]
    from laplace.pipeline import registry as R
    resolved = R.resolve(project, repo_root=root)
    directory = resolved.project_dir if resolved and not resolved.external_root else None
    if not directory or directory == '.' or not C._safe(root, directory).is_dir():
        raise Refused('LOCAL_PROJECT_HOME_REQUIRED')
    defs, definition_bodies, packages = C.collect_definitions(root, project, read_rows=_bounded_rows, max_rows=max_rows, max_bytes=max_bytes)
    selected, history_lineage = C.select_history(root, project, additional=defs, read_rows=_bounded_rows, with_lineage=True)
    selected.sort(key=lambda r: (r[0], r[1]))
    if len(selected) > max_rows:
        raise Refused('ROW_BUDGET', selected_rows=len(selected), budgets=budgets)
    _unique_history(selected)
    paths = C._project_files(root, project, directory, max_files=max_files, extra_excluded=('.laplace-state', '.laplace-cache', '.auth', '.credentials'), max_directories=SCAN_ROWS)
    for other in registry.get('projects', []):
        home = other.get('project_dir')
        if other.get('name') != project and isinstance(home, str) and any(p.relative_to(root).is_relative_to(home) for p in paths):
            raise Refused('FOREIGN_PROJECT_HOME', project=other.get('name'))
    file_rows = {p.relative_to(root).as_posix(): C._file_record(root, p) for p in paths}
    if sum(r["bytes"] for r in file_rows.values()) + sum(len(r[2]) for r in selected) > max_bytes:
        raise Refused("TOTAL_BUDGET", budgets=budgets)
    values = [entry, *[r[3] for r in selected]]
    values.extend(C._json(p) for p in paths if p.suffix == '.json')
    bodies, missing, unresolved = C._body_closure(root, values, max_files=max_files, max_bytes=max_bytes)
    if missing or unresolved:
        raise Refused('PUBLIC_BODY_CLOSURE', missing=missing, unresolved=unresolved)
    file_rows.update({r['path']: r for r in bodies})
    file_rows.update({r['path']: r for r in definition_bodies})
    values.extend(version['definition'] for package in packages for version in package['versions'])
    # A historical deletion is absence, while the latest owned artifact must exist exactly.
    from laplace.projects import artifacts
    latest = {}
    for item in selected:
        r = item[3]
        if r.get('record') == 'writing-artifact':
            latest[(r.get('artifact_path') or r.get('path'), r.get('scope', 'project'))] = r
    for (path, scope), row in latest.items():
        target = artifacts._artifact_target(root, project, {'id': row['id']}, record_lookup=lambda ident: row, allow_read_only=True)[0]
        if row.get('sha256') is not None and (not target.is_file() or not revision_matches(row['sha256'], C._file_record(root, target)['sha256'])):
            raise Refused('OWNED_ARTIFACT_UNAVAILABLE', path=path, scope=scope)
        if target.is_file():
            if C._excluded(target.relative_to(root)) or {'.laplace-state', '.laplace-cache', '.auth', '.credentials'} & set(target.relative_to(root).parts):
                raise Refused('REQUIRED_PRIVATE_INPUT', file=target.relative_to(root).as_posix())
            file_rows[target.relative_to(root).as_posix()] = C._file_record(root, target)
    # Current owned material targets are required bytes, unless their owner explicitly recorded absence.
    for binding in entry.get('manifest', {}).get('material_references', []):
        target = binding.get('target', {})
        if target.get('owner') == 'artifact' and target.get('project') == project:
            path = artifacts.resolve_path(root, project, target['path'], target['scope'], allow_read_only=True)
            known_absence = any(r.get('sha256') is None and (r.get('artifact_path') == target['path']) and r.get('scope', 'project') == target['scope'] for r in latest.values())
            if not path.is_file():
                if known_absence:
                    continue
                raise Refused('OWNED_MATERIAL_UNAVAILABLE', target=target)
            rel = path.relative_to(root).as_posix()
            if C._excluded(Path(rel)) or {'.laplace-state', '.laplace-cache', '.auth', '.credentials'} & set(Path(rel).parts):
                raise Refused('REQUIRED_PRIVATE_INPUT', file=rel)
            file_rows[rel] = C._file_record(root, path)
    config, dependencies = _dependencies(root, project, entry, values, directory)
    originals = [C._row_record(r) for r in selected]
    sessions = sorted({r[3]['id'] for r in selected if r[3].get('record') == 'writing-session'})
    result = {'schema': SCHEMA, 'source_root': str(root), 'project': project, 'registry_row': entry,
              'project_dir': directory, 'budgets': budgets, 'files': sorted(file_rows.values(), key=lambda r: r['path']),
              'rows': originals, 'sessions': sessions, 'workflow_definitions': packages,
              'repository_config': config, 'dependencies': dependencies,
              'qualification': 'Complete selected project data within caller authority and existing private/runtime exclusions. Selection does not certify publication permission. External dependencies may remain UNBOUND/UNAVAILABLE; not self-contained or executable-ready.',
              'lineage': 'Exact selected original rows; legacy WDEF bank row_id=? is unattributable and not inferred.',
              'scan_limits': {'per_ledger_bytes': C.MAX_JSON, 'per_ledger_rows': SCAN_ROWS, 'project_directories': SCAN_ROWS, 'per_file_bytes': PER_FILE}}
    if history_lineage:
        result['history_lineage'] = history_lineage
    result['counts'] = {'selected_files': len(file_rows), 'selected_rows': len(selected),
                        'selected_file_bytes': sum(r['bytes'] for r in file_rows.values()),
                        'selected_row_bytes': sum(len(r[2]) for r in selected), 'planned_output': None}
    for _ in range(8):
        result['manifest_digest'] = canonical_digest({k: v for k, v in result.items() if k != 'manifest_digest'})
        _, receipt = _outputs(root, result)
        if result['counts']['planned_output'] == receipt['counts']:
            return result
        result['counts']['planned_output'] = receipt['counts']
    raise Refused('PLAN_SIZE_UNSTABLE')



def _selected_plan(data_root,project,selection,*,max_files,max_rows,max_bytes,caller,_metadata_only=False):
    """Same publication engine, explicit selected files/ART/WDEF custody only.

    No directory walk, default project history, external source read or permission
    inferred from a hash. Scientific snapshot ARTs are created by their actual
    Work/domain preparation before this data-custody projection.
    """
    budgets=_budgets(max_files,max_rows,max_bytes);root=Path(data_root).absolute()
    if root.is_symlink() or root.resolve()!=root:raise Refused('UNSAFE_SOURCE_ROOT')
    if not isinstance(selection,dict) or set(selection)!={'files','artifact_ids','definitions','manifest_id','manifest_sha256'}:
        raise Refused('SELECTED_CLOSURE_REQUIRED')
    registry=C._json(C._safe(root,'registry_projects.json'));entries=[r for r in registry.get('projects',[]) if r.get('name')==project]
    if len(entries)!=1:raise Refused('EXACT_REGISTERED_PROJECT_REQUIRED')
    from laplace.pipeline import registry as R
    from laplace.projects import artifacts
    record=R.resolve(project,repo_root=root);directory=record.project_dir if record and not record.external_root else None
    if not directory or directory=='.':raise Refused('LOCAL_PROJECT_HOME_REQUIRED')
    C._safe(root,directory)
    files={}
    if not isinstance(selection['files'],list) or not isinstance(selection['artifact_ids'],list) or not isinstance(selection['definitions'],list):raise Refused('INVALID_SELECTED_INPUTS')
    for item in selection['files']:
        if not isinstance(item,dict) or set(item)!={'path','sha256'}:raise Refused('INVALID_SELECTED_FILE')
        relative=Path(item['path'])
        if not relative.is_relative_to(directory) or C._excluded(relative):raise Refused('SELECTED_FILE_NOT_OWNED_OR_PERMITTED')
        path=C._safe(root,item['path']);observed=C._file_record(root,path)
        if not revision_matches(item['sha256'],observed['sha256']):raise Refused('SELECTED_INPUT_CHANGED')
        files[item['path']]=observed
    ids=selection['artifact_ids']
    if len(ids)!=len(set(ids)) or any(not isinstance(i,str) or not i.startswith('ART-') for i in ids):raise Refused('INVALID_SELECTED_ARTIFACTS')
    if selection['manifest_id'] not in ids:raise Refused('SELECTED_MANIFEST_REQUIRED')
    talk=_selected_artifact_rows(root,project,ids,max_rows=max_rows,max_bytes=max_bytes);selected=[]
    for ident in ids:
        rows=[r for r in talk if r[3].get('id')==ident]
        if len(rows)!=1 or rows[0][3].get('record')!='writing-artifact' or rows[0][3].get('project')!=project:raise Refused('SELECTED_ARTIFACT_CUSTODY')
        item=rows[0];row=item[3];path,rel,scope,indexed=artifacts._artifact_target(root,project,{'id':ident},record_lookup=lambda _id,row=row:row,allow_read_only=True)
        actual=C._file_record(root,path)
        if not revision_matches(row.get('sha256'),actual['sha256']):raise Refused('SELECTED_ARTIFACT_CHANGED')
        if not path.relative_to(root).is_relative_to(directory) or C._excluded(path.relative_to(root)):raise Refused('SELECTED_ARTIFACT_NOT_PERMITTED')
        if ident==selection['manifest_id'] and not revision_matches(selection['manifest_sha256'],actual['sha256']):raise Refused('SELECTED_MANIFEST_CHANGED')
        files[actual['path']]=actual;selected.append(item)
    # Explicitly empty is no definition custody request. Nonempty definitions
    # retain the existing exact-version collector and its bounded scan policy.
    defs,bodies,packages=C.collect_definitions(root,project,read_rows=_bounded_rows,max_rows=max_rows,max_bytes=max_bytes,references=selection['definitions'],caller=caller) if selection['definitions'] else ([],[],[])
    selected.extend(defs);selected.sort(key=lambda r:(r[0],r[1]));_unique_history(selected)
    closure,missing,unresolved=C._body_closure(root,[r[3] for r in selected],max_files=max_files,max_bytes=max_bytes)
    if missing or unresolved:raise Refused('PUBLIC_BODY_CLOSURE_UNAVAILABLE')
    files.update({r['path']:r for r in [*bodies,*closure]})
    if len(files)>max_files or len(selected)>max_rows:raise Refused('SELECTED_CLOSURE_BUDGET')
    # Only selected namespace/home coordinates. Other manifest memberships,
    # titles, prompts and private dependencies are not copied for explanation.
    registry_row={'name':project,'project_dir':directory,'kind':'project','manifest':{'writing':{'kind':'general','display_name':project}}}
    manifest_row=next(r[3] for r in selected if r[3].get('id')==selection['manifest_id'])
    manifest_path=artifacts._artifact_target(root,project,{'id':selection['manifest_id']},record_lookup=lambda _id:manifest_row,allow_read_only=True)[0]
    manifest=C._json(manifest_path)
    if manifest.get('schema_version')!='laplace.research-handover/1':raise Refused('INVALID_SELECTED_MANIFEST')
    dependencies=[copy for copy in manifest.get('entries',[]) if copy.get('class')!='included']
    result={'schema':SCHEMA,'source_root':'owned-workspace:'+canonical_digest(str(root)).removeprefix('sha256:'),
        'project':project,'registry_row':registry_row,'project_dir':directory,'budgets':budgets,
        'files':sorted(files.values(),key=lambda r:r['path']),'rows':[C._row_record(r) for r in selected],
        'sessions':[],'workflow_definitions':packages,'repository_config':{'repositories':{'workspace':'.'}},
        'dependencies':dependencies,'selection':json.loads(encoded(selection)),
        'qualification':'Explicit permitted selected bytes and frozen public snapshots. Scientific identities/bases are retained as provenance; snapshots are not new live scientific assertions. No unrelated project history, credentials, host proof or provider binding.',
        'lineage':'Exact selected ART/WDEF rows and bodies; public object snapshots resolve at ordinary artifact owners.',
        'counts':{'selected_files':len(files),'selected_rows':len(selected),'selected_file_bytes':sum(r['bytes'] for r in files.values()),'selected_row_bytes':sum(len(r[2]) for r in selected),'planned_output':None}}
    if _metadata_only:
        result['manifest_digest']=canonical_digest(result)
        return result
    for _ in range(8):
        result['manifest_digest']=canonical_digest({k:v for k,v in result.items() if k!='manifest_digest'})
        _,receipt=_outputs(root,result,caller=caller)
        if result['counts']['planned_output']==receipt['counts']:return result
        result['counts']['planned_output']=receipt['counts']
    raise Refused('PLAN_SIZE_UNSTABLE')

def _admit_plan(value):
    required = {'schema', 'source_root', 'project', 'project_dir', 'budgets', 'files', 'rows', 'sessions',
                'workflow_definitions', 'repository_config', 'dependencies', 'manifest_digest'}
    if not isinstance(value, dict) or not required <= set(value) or value.get('schema') != SCHEMA:
        raise Refused('INVALID_PLAN')
    if canonical_digest({k: v for k, v in value.items() if k != 'manifest_digest'}) != value['manifest_digest']:
        raise Refused('PLAN_DIGEST')
    _budgets(**value['budgets'])


def _validate_output_paths(paths):
    folded = {}
    for rel in paths:
        key = rel.casefold()
        if '\\' in rel or ':' in rel or PureWindowsPath(rel).drive or any(part.rstrip(' .') != part for part in Path(rel).parts):
            raise Refused('UNSAFE_OUTPUT_PATH', file=rel)
        if key in folded or any(Path(key) in Path(x.casefold()).parents or Path(x.casefold()) in Path(key).parents for x in paths if x != rel):
            raise Refused('NORMALIZED_OUTPUT_COLLISION', file=rel)
        folded[key] = rel


def _outputs(root, value, *, caller=None):
    _admit_plan(value)
    outputs = {}
    for row in value['files']:
        path = C._safe(root, row['path'])
        if row['bytes'] > PER_FILE:
            raise Refused('FILE_BOUND', file=row['path'], bytes=row['bytes'])
        outputs[row['path']] = path.read_bytes()
        if len(outputs[row['path']]) != row['bytes'] or C._sha(outputs[row['path']]) != row['sha256']:
            raise Refused('SELECTED_INPUT_CHANGED', file=row['path'])
    for rel in sorted({r['file'] for r in value['rows']}):
        wanted = {r['line']: r for r in value['rows'] if r['file'] == rel}
        if value.get('selection') is not None and rel=='contract/talk.jsonl':
            source_rows=_selected_artifact_rows(root,value['project'],[item['id'] for item in wanted.values()],max_rows=value['budgets']['max_rows'],max_bytes=value['budgets']['max_bytes'])
        elif value.get('selection') is not None and rel=='contract/dispatches.jsonl':
            from laplace.pipeline import workflow_definitions as D
            refs=[D.reference(p['definition_id'],p['versions'][-1]['row']['definition_revision']) for p in value['workflow_definitions']]
            source_rows,_,packages=C.collect_definitions(root,value['project'],references=refs,caller=caller,
                max_rows=value['budgets']['max_rows'],max_bytes=value['budgets']['max_bytes'])
            if packages!=value['workflow_definitions']:raise Refused('SELECTED_DEFINITIONS_CHANGED')
        else:source_rows=_bounded_rows(root,rel)
        rows = {number: raw for _, number, raw, _ in source_rows if number in wanted}
        if set(rows) != set(wanted) or any(C._sha(raw) != wanted[n]['row_sha256'] for n, raw in rows.items()):
            raise Refused('SELECTED_ROWS_CHANGED', file=rel)
        if rel in outputs:
            raise Refused('OUTPUT_PATH_COLLISION', file=rel)
        outputs[rel] = b''.join(rows[n] for n in sorted(rows))
    if not any(Path(rel).is_relative_to(value['project_dir']) for rel in outputs):
        outputs[value['project_dir'] + '/' + C.HOME_MARKER] = C.home_marker(value['project'], value['project_dir'])
    imports = C._import_rows(value['project'], value['sessions'], value['manifest_digest'])
    for rel, raw in {'registry_projects.json': encoded({'projects': [value['registry_row']]}),
                     'profiles/writing_sources.json': encoded(value['repository_config'])}.items():
        if rel in outputs:
            raise Refused('OUTPUT_PATH_COLLISION', file=rel)
        outputs[rel] = raw
    outputs['contract/talk.jsonl'] = outputs.get('contract/talk.jsonl', b'') + b''.join(encoded(r) for r in imports)
    if MANIFEST in outputs:
        raise Refused('OUTPUT_PATH_COLLISION', file=MANIFEST)
    _validate_output_paths(outputs)
    receipt = {'schema': RECEIPT, 'plan': value, 'outputs': [{'path': p, 'sha256': C._sha(raw), 'bytes': len(raw)} for p, raw in sorted(outputs.items())], 'counts': {}}
    for _ in range(8):
        raw = encoded(receipt)
        counts = {'files': len(outputs) + 1, 'rows': len(value['rows']), 'bytes': sum(map(len, outputs.values())) + len(raw)}
        if counts == receipt['counts']:
            break
        receipt['counts'] = counts
    else:
        raise Refused('RECEIPT_SIZE_UNSTABLE')
    limits = value['budgets']
    if counts['files'] > limits['max_files'] or counts['rows'] > limits['max_rows'] or counts['bytes'] > limits['max_bytes']:
        raise Refused('TOTAL_BUDGET', counts=counts, budgets=limits)
    if any(len(raw) > PER_FILE for raw in outputs.values()) or len(raw) > PER_FILE:
        raise Refused('FILE_BOUND')
    outputs[MANIFEST] = raw
    return outputs, receipt


def _publish(stage, destination):
    sys.audit("laplace.project_handover.publish", str(stage), str(destination))
    if os.name == 'nt':
        os.rename(stage, destination)  # Windows refuses an existing destination.
        return
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None:
        raise Refused('ATOMIC_NOREPLACE_UNAVAILABLE')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(stage), -100, os.fsencode(destination), 1) != 0:
        err = ctypes.get_errno()
        raise Refused('DESTINATION_OCCUPIED' if err in (errno.EEXIST, errno.ENOTEMPTY) else 'PUBLICATION_REFUSED', errno=err)


def export(data_root, destination, value, *, caller=None):
    """Revalidate under reached owner locks, publish a fresh no-replace directory."""
    _admit_plan(value)
    if value.get('selection') is not None and caller is None:
        from laplace.work.owner_discovery import owned_workspace
        caller=owned_workspace('sdk')
    value = json.loads(encoded(value))
    root = Path(data_root).absolute();dest = Path(destination).absolute()
    expected_source=('owned-workspace:'+canonical_digest(str(root)).removeprefix('sha256:')) if value.get('selection') is not None else str(root)
    if value['source_root'] != expected_source:
        raise Refused('PLAN_SOURCE_ROOT_MISMATCH')
    if '..' in Path(destination).parts or dest.resolve() != dest or dest.exists() or dest.is_symlink() or dest.is_relative_to(root) or root.is_relative_to(dest):
        raise Refused('FRESH_DESTINATION_REQUIRED')
    if not dest.parent.is_dir():
        raise Refused('DESTINATION_PARENT_REQUIRED')
    from filelock import FileLock
    from laplace.writing import records
    stage = None
    try:
        with ExitStack() as locks:
            for rel in ['registry_projects.json.lock', 'corpus_friction/work_orders.jsonl.lock', 'contract/.writing-apply.lock', 'contract/workflow-definitions.lock', value['project_dir'] + '/manuscript/.authoring.lock']:
                path = C._safe(root, rel)
                if rel.endswith('/manuscript/.authoring.lock') and not path.parent.is_dir():
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                locks.enter_context(FileLock(str(path), timeout=20))
            current = plan(root, value['project'], **value['budgets'], **({'selection':value['selection'],'caller':caller} if 'selection' in value else {}))
            if current != value:
                raise Refused('PLAN_STALE', expected=value.get('manifest_digest'), observed=current['manifest_digest'])
            outputs, receipt = _outputs(root, value,caller=caller)
            stage = Path(tempfile.mkdtemp(prefix='.' + dest.name + '-handover-', dir=dest.parent))
            for rel, raw in outputs.items():
                target = stage / rel;target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(raw);stream.flush();os.fsync(stream.fileno())
            if plan(root, value['project'], **value['budgets'], **({'selection':value['selection'],'caller':caller} if 'selection' in value else {})) != value:
                raise Refused('INPUT_CHANGED_DURING_STAGING')
            _publish(stage, dest);stage = None
        return {'status': 'EXPORTED', 'destination': str(dest), 'manifest_digest': value['manifest_digest'], 'receipt_sha256': C._sha((dest / MANIFEST).read_bytes()), 'counts': receipt['counts'], 'dependencies': value['dependencies'], 'providers_started': 0}
    finally:
        if stage is not None:
            shutil.rmtree(stage)


def inspect_handover(data_root):
    """Verify transported bytes and consume ordinary project owners; never launch."""
    root = Path(data_root).absolute();receipt = C._json(C._safe(root, MANIFEST))
    if receipt.get('schema')=='laplace.project-data-handover/2':
        from . import project_handover_lineage
        return project_handover_lineage.inspect(root)
    if receipt.get('schema') != RECEIPT:
        raise Refused('UNKNOWN_HANDOVER')
    value = receipt['plan'];digest = value['manifest_digest']
    if canonical_digest({k: v for k, v in value.items() if k != 'manifest_digest'}) != digest:
        raise Refused('PLAN_DIGEST')
    _admit_plan(value)
    for row in value['files']:
        if C._file_record(root, C._safe(root, row['path'])) != row:
            raise Refused('HANDOVER_PLAN_FILE_DRIFT', file=row['path'])
    for rel in sorted({r['file'] for r in value['rows']}):
        expected = [r for r in value['rows'] if r['file'] == rel]
        actual = C._safe(root, rel).read_bytes().splitlines(keepends=True)
        if len(actual) < len(expected) or any(C._sha(raw) != row['row_sha256'] for raw, row in zip(actual, expected)):
            raise Refused('HANDOVER_PLAN_ROW_DRIFT', file=rel)
    for row in receipt['outputs']:
        if C._file_record(root, C._safe(root, row['path'])) != row:
            raise Refused('HANDOVER_DRIFT', file=row['path'])
    from laplace.projects import library, artifacts
    from laplace.work import project_work, owner_discovery as O
    from laplace.pipeline import workflow_definitions as D
    from laplace.writing import session_reads
    project = value['project']
    sessions = [session_reads.session_state(root, sid, view='summary', limit=2) for sid in value['sessions']]
    if any(s['session'].get('native_id') or s['active'] or not s['session'].get('imported_history') for s in sessions):
        raise Refused('FOREIGN_BINDING_NOT_CLEARED')
    definitions = [D.read(root, O.owned_workspace('sdk') if value.get('selection') is not None else O.project_scope(project,'sdk'), {'definition_id':p['definition_id'],'facet':'export'}) for p in value['workflow_definitions']]
    return {'status': 'INSPECTED', 'project': project, 'manifest_digest': digest, 'counts': receipt['counts'], 'qualification': value['qualification'],
            'metadata': library.metadata(project, root), 'work': project_work.state(project, root),
            'artifacts': artifacts.catalogue(root, project), 'materials': library.material_references(project, root),
            'definitions': [{'definition_id': p['definition_id'], 'versions': len(p['versions']), 'read': D.handle(p['definition_id'], p['versions'][-1]['row']['definition_revision'])} for p in definitions],
            'sessions': sessions, 'dependencies': value['dependencies'], 'providers_started': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'export', 'inspect'])
    parser.add_argument('--root', type=Path, required=True);parser.add_argument('--project')
    parser.add_argument('--max-files', type=int);parser.add_argument('--max-rows', type=int);parser.add_argument('--max-bytes', type=int)
    parser.add_argument('--plan', type=Path);parser.add_argument('--destination', type=Path);parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == 'plan':
            result = plan(args.root, args.project, max_files=args.max_files, max_rows=args.max_rows, max_bytes=args.max_bytes)
        elif args.action == 'export':
            if args.plan is None or args.destination is None:raise Refused('PLAN_AND_DESTINATION_REQUIRED')
            result = export(args.root, args.destination, C._json(args.plan))
        else:result = inspect_handover(args.root)
        raw = encoded(result)
        if args.output:args.output.write_bytes(raw)
        else:print(raw.decode(), end='')
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps(getattr(exc, 'details', {'error': str(exc)})))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())


# Selected research-object manifests are ARTs of this same project-data owner.
OBJECT_SCHEMA='laplace.research-handover/1'
OMISSION_CLASSES={'excluded','private_not_included','unavailable'}


def object_contract():
    return {'type':'object','additionalProperties':False,'required':['action'], 'properties':{
        'action':{'enum':['prepare','request','read','export','inspect','continue']},'project':{'type':'string'},
        'request_id':{'type':'string','minLength':1,'maxLength':96},'reference':{'type':'object'},
        'entries':{'type':'array','minItems':1,'maxItems':80,'items':{'type':'object'}},
        'expected_basis':{'type':'string'},'destination':{'type':'string'},
        'max_files':{'type':'integer','minimum':1},'max_rows':{'type':'integer','minimum':1},'max_bytes':{'type':'integer','minimum':1},
        **__import__('laplace.projects.project_handover_lineage',fromlist=['contract_properties']).contract_properties()}}


def object_handle(project,payload):
    from urllib.parse import urlencode
    return {'http':{'method':'POST','url':'/work/object-handover','payload':{**({'project':project} if project is not None else {}),**payload}},
        'native':{'operation':'research_handover','payload':payload},
        'sdk':{'method':'research_handover','payload':{**({'project':project} if project is not None else {}),**payload}}}


def _object_path(request_id):
    if not isinstance(request_id,str) or not 1<=len(request_id)<=96:raise Refused('STABLE_REQUEST_REQUIRED')
    return 'handover/manifests/'+canonical_digest(request_id).removeprefix('sha256:')+'.json'


def _json_artifact(root,project,ident):
    from laplace.projects import artifacts
    meta=artifacts.identity(root,project,{'id':ident});parts=[];offset=0
    while True:
        page=artifacts.read(root,project,{'id':ident,'offset':offset,'limit':40000,'expected_sha256':meta['revision']})
        parts.append(page['content']);offset=page.get('next_offset')
        if offset is None:break
    return json.loads(''.join(parts)),meta


def _retained_manifest(root,project,ident):
    from laplace.projects import artifacts
    row=artifacts._artifact_record(Path(root),project,ident)
    value,meta=_json_artifact(root,project,ident);marker=artifacts.reader_receipt(Path(root),project,ident)
    if (value.get('schema_version')!=OBJECT_SCHEMA or value.get('project')!=project
            or marker.get('schema_version')!=OBJECT_SCHEMA or marker.get('request_id')!=value.get('request_id')
            or marker.get('intent')!=value.get('intent') or row.get('artifact_path')!=_object_path(value.get('request_id'))
            or not revision_matches(row.get('sha256'),meta['revision'])):raise Refused('MANIFEST_OWNER_CUSTODY_UNAVAILABLE')
    return value,meta


def _object_recovery(root,project,request_id):
    from laplace.projects import artifacts
    from laplace.writing import records
    path=_object_path(request_id);target=artifacts.resolve_path(root,project,path,'project')
    rows=[r for r in records.index(root).by_project.get(project,[]) if r['record']=='writing-artifact' and r.get('artifact_path')==path and r.get('scope','project')=='project']
    if not rows:
        return {'state':'UNKNOWN' if target.exists() else 'NONE','request_id':request_id,
            'reason':'An unacknowledged publication may still be in flight; no new request is authorised by absence.'}
    if len(rows)!=1:return {'state':'UNKNOWN','request_id':request_id,'reason':'Manifest publication custody is ambiguous.'}
    row=rows[0]
    try:value,meta=_retained_manifest(root,project,row['id'])
    except (OSError,ValueError,KeyError):return {'state':'UNKNOWN','request_id':request_id,'reason':'Original manifest publication is unavailable.'}
    if value.get('schema_version')!=OBJECT_SCHEMA or value.get('request_id')!=request_id:return {'state':'UNKNOWN','request_id':request_id}
    from laplace.core.identity import reference
    return {'state':'RECORDED','request_id':request_id,'manifest':value,'reference':reference('domain.projects','artifact',{'project':project,'id':row['id']}),'basis':meta['revision']}


def _redacted_snapshot(observed,allowed,selected_paths):
    """Only explicitly selected public object meaning, not nested hidden context."""
    reference=observed['reference'];kind=reference['kind'];value=observed.get('value') or {}
    result={'subject':reference,'basis':observed['basis'],'purpose':observed['facets']['purpose'].get('value'),
        'standing':{'label':(observed['facets']['standing'].get('value') or {}).get('label'),'scientific_validity':'NOT_ASSERTED'},'representation':'frozen-owner-snapshot'}
    if kind=='concept':
        result['content']={k:value.get(k) for k in ('id','kind','essence') if k in value}
        result['consumed_bases']=[x for x in (value.get('projection') or {}).get('consumed_bases') or [] if canonical_digest(x['reference']) in allowed]
    elif kind=='research-record':
        result['content']={k:value[k] for k in ('id','kind','revision','title','question','summary','limitations','measures') if k in value}
        included={}
        for key in ('config','source','result'):
            if key in value and value[key] in selected_paths:included[key]=value[key]
        if isinstance(value.get('data'),list):included['data']=[v for v in value['data'] if v in selected_paths]
        result['selected_paths']=included
        result['consumed_bases']=[x for x in value.get('consumed_bases') or [] if canonical_digest(x['reference']) in allowed]
    elif kind=='research-concern':
        result['content']={k:value[k] for k in ('id','state','change_kind','summary','disposition') if k in value}
        result['evidence']=[r for r in value.get('evidence') or [] if canonical_digest(r) in allowed]
    elif kind=='work':
        from laplace.work import backlog
        from laplace.core.identity import reference as work_ref
        namespace=reference['identity']['namespace']
        result['content']={k:value[k] for k in ('id','title','goal','status','task_kind') if k in value}
        # The already observed Work row is the owner's input; never fold another
        # ledger, infer planning from export order or transfer a live capability.
        result['planning']=backlog.projection(namespace,value)
        result['work_observation']={k:value[k] for k in ('work_revision','work_status_revision','dependency_revision','recorded_status') if k in value}
        for field,keys in [('lifecycle',('status','completed','closed')),
                           ('current_acceptance',('status','review_required','kind')),
                           ('readiness',('status',)),('currentness',('status','kind'))]:
            result[field]={k:value[field][k] for k in keys if k in (value.get(field) or {})}
        subject=work_ref('domain.work','work',{'namespace':namespace,'id':value['id']})
        relations=[]
        if value.get('parent_work_id'):
            relations.append({'relation':'contains','source':work_ref('domain.work','work',{'namespace':namespace,'id':value['parent_work_id']}),'target':subject,'basis':value.get('work_revision')})
        for ident in dict.fromkeys(value.get('depends_on') or []):
            relations.append({'relation':'requires','source':subject,'target':work_ref('domain.work','work',{'namespace':namespace,'id':ident}),'basis':value.get('dependency_revision')})
        result['relationships']={'items':relations,'coverage':'Recorded parent and prerequisites of this selected Work only; no child/network discovery.',
            'resolution':'Original Work references are provenance, not imported live Work. Selected counterparts may resolve as frozen ARTs through the manifest; all other targets remain external/unavailable here.'}
        result['qualification']='Frozen owner observations: planning is preference, recorded completion is historical and current acceptance/readiness keep their observed meaning. This carries no live Work, action, approval, binding or execution grant; later source changes are not revalidated here.'
    elif kind=='section':
        result['content']={k:value[k] for k in ('id','title','job','text','standing') if k in value}
    elif kind=='reference':
        result['content']={k:value[k] for k in ('key','title','citation_key') if k in value}
        result['content']['metadata']={k:v for k,v in (value.get('metadata') or {}).items() if k in {'title','creators','year','date','doi','url','abstract'}}
    else:result['content']={k:value[k] for k in ('definition','reference') if k in value}
    return result


def _prepare_object(root,scope,payload):
    from laplace.work import object_facets as F,project_work
    from laplace.projects import artifacts
    project=payload['project'];request_id=payload['request_id'];entries=payload.get('entries')
    if not isinstance(entries,list) or not 1<=len(entries)<=80:raise Refused('EXPLICIT_SELECTION_REQUIRED')
    intent=canonical_digest({k:v for k,v in payload.items() if k not in {'action'}})
    # Replay original material before consulting mutable source state.
    prior=_object_recovery(root,project,request_id)
    if prior['state']=='RECORDED':
        if prior['manifest']['intent']!=intent:raise Refused('REQUEST_INTENT_CHANGED')
        return _read_object(root,scope,prior['reference'])|{'state':'RECORDED','reused':True}
    if prior['state']=='UNKNOWN':return prior
    from laplace.pipeline import registry
    custody=registry.resolve(project,repo_root=root)
    if not custody or custody.external_root or not custody.project_dir or custody.project_dir=='.':raise Refused('EXISTING_LOCAL_METADATA_CUSTODY_REQUIRED')
    C._safe(root,custody.project_dir)
    budgets=_budgets(*(payload.get(k) for k in ('max_files','max_rows','max_bytes')))
    allowed={canonical_digest(e['reference']) for e in entries if isinstance(e,dict) and e.get('class')=='included' and isinstance(e.get('reference'),dict)}
    selected_paths={e.get('reference',{}).get('identity',{}).get('path') for e in entries if isinstance(e,dict) and e.get('class')=='included'}
    planned=[]
    for entry in entries:
        if not isinstance(entry,dict):raise Refused('INVALID_SELECTION')
        kind=entry.get('class')
        if kind in OMISSION_CLASSES:
            if set(entry)-{'class','reason_code'}:raise Refused('OMISSION_METADATA_NOT_PERMITTED')
            # Never copy caller-supplied private identifiers or arbitrary reason text.
            planned.append({'class':kind,'reason_code':'NOT_INCLUDED' if kind!='unavailable' else 'UNAVAILABLE'});continue
        if kind=='external':
            if set(entry)!={'class','public_locator'}:raise Refused('PUBLIC_LOCATOR_REQUIRED')
            from urllib.parse import urlsplit
            uri=urlsplit(entry['public_locator'])
            if uri.scheme not in {'https','http'} or not uri.hostname or uri.username or uri.password:raise Refused('PUBLIC_LOCATOR_REQUIRED')
            planned.append({'class':'external','public_locator':entry['public_locator']});continue
        if kind=='runtime-unbound':
            import re
            if set(entry)-{'class','provider','model','version'} or not all(isinstance(entry.get(k),str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,159}',entry[k]) for k in ('provider','model')) or ('version' in entry and (not isinstance(entry['version'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,159}',entry['version']))):raise Refused('PUBLIC_RUNTIME_ID_REQUIRED')
            planned.append({**entry,'qualification':'No executable, credentials, host qualification or effective binding is transferred.'});continue
        if kind!='included' or set(entry)-{'class','reference','expected_basis','permit_export'} or entry.get('permit_export') is not True:raise Refused('EXPLICIT_PERMITTED_ENTRY_REQUIRED')
        reference=entry.get('reference')
        from laplace.core.identity import reference_problems
        if reference_problems(reference):raise Refused('INVALID_SELECTED_REFERENCE')
        foreign=F._project(reference) not in (None,project)
        # Only a trusted workspace selection may freeze Work metadata from another
        # namespace. Storage project is custody, never that Work's identity or a
        # newly registered execution scope. Ordinary/natively scoped doors are
        # refused by object_request before any selected metadata is observed.
        if foreign and not (scope.kind=='owned-workspace' and reference.get('kind')=='work'):raise Refused('FOREIGN_SELECTED_OBJECT')
        observed=F._observe(root,scope,reference)
        if not revision_matches(entry.get('expected_basis'),observed['basis']):raise Refused('SELECTED_INPUT_CHANGED')
        if reference['kind'] in {'artifact','source-file'}:
            source=F._source(root,scope,reference);path=source['path']
            from laplace.pipeline import registry
            record=registry.resolve(project,repo_root=root);base=root/record.project_dir
            if not path.is_relative_to(base) or C._excluded(path.relative_to(root)):raise Refused('SELECTED_BYTES_NOT_LOCAL_OR_PERMITTED')
            planned.append({'class':'included','reference':reference,'basis':observed['basis'],'carried':{'path':path.relative_to(base).as_posix(),'sha256':C._file_record(root,path)['sha256']},
                'artifact_id':reference['identity']['id'] if reference['kind']=='artifact' else None,'source_path':path.relative_to(root).as_posix()})
        elif reference['kind']=='repository-file':raise Refused('REPOSITORY_BYTES_REQUIRE_EXPLICIT_LOCAL_RETENTION')
        elif reference['kind']=='workflow-definition':planned.append({'class':'included','reference':reference,'basis':observed['basis'],'definition':True})
        else:
            snapshot=_redacted_snapshot(observed,allowed,selected_paths)
            path='handover/objects/'+canonical_digest([request_id,reference]).removeprefix('sha256:')+'.json'
            planned.append({'class':'included','reference':reference,'basis':observed['basis'],'snapshot':snapshot,'snapshot_path':path})
    # All permissions, source bases and omissions are checked before the first ART.
    selection={'files':[],'artifact_ids':[],'definitions':[]};public=[]
    with project_work.dispatch_lock(root):
        observed_request=_object_recovery(root,project,request_id)
        if observed_request['state']=='RECORDED':
            if observed_request['manifest']['intent']!=intent:raise Refused('REQUEST_INTENT_CHANGED')
            return _read_object(root,scope,observed_request['reference'])|{'state':'RECORDED','reused':True}
        if observed_request['state']=='UNKNOWN':return observed_request
        for item in planned:
            if item.get('class')!='included':public.append(item);continue
            if item.get('definition'):
                selection['definitions'].append(item['reference']);public.append({k:v for k,v in item.items() if k!='definition'});continue
            if 'snapshot' in item:
                path=item['snapshot_path'];content=encoded(item['snapshot']).decode()
                existing=[r for r in __import__('laplace.writing.records',fromlist=['index']).index(root).by_project.get(project,[]) if r['record']=='writing-artifact' and r.get('artifact_path')==path]
                if existing:
                    observed_snapshot,meta=_json_artifact(root,project,existing[-1]['id'])
                    if observed_snapshot!=item['snapshot']:raise Refused('SNAPSHOT_CUSTODY_UNKNOWN')
                    ident=existing[-1]['id'];pin=meta['revision']
                else:
                    saved=artifacts.store(root,project,{'path':path,'scope':'project','before':None,'content':content},owner_metadata={'schema_version':'laplace.research-handover-snapshot/1','request_id':request_id})
                    ident=saved['id'];pin=saved['revision']
                selection['artifact_ids'].append(ident)
                public.append({'class':'included','reference':item['reference'],'basis':item['basis'],'representation':'frozen-owner-snapshot','carried':{'path':path,'sha256':'sha256:'+str(pin).removeprefix('sha256:')},'artifact_id':ident})
            else:
                selection['files'].append({'path':item['source_path'],'sha256':item['carried']['sha256']})
                if item['artifact_id']:selection['artifact_ids'].append(item['artifact_id'])
                public.append({k:v for k,v in item.items() if k not in {'source_path'}})
        selection['artifact_ids']=list(dict.fromkeys(selection['artifact_ids']))
        manifest={'schema_version':OBJECT_SCHEMA,'project':project,'request_id':request_id,'intent':intent,
            'source_scope_id':__import__('laplace.pipeline.workflow_definitions',fromlist=['_scope_id'])._scope_id(root,scope),
            'entries':public,'selection':selection,'budgets':budgets,
            'qualification':'Selected permitted frozen bytes/snapshots; omitted metadata redacted; scientific acceptance and runnable provider binding are not inferred.'}
        saved=artifacts.store(root,project,{'path':_object_path(request_id),'scope':'project','before':None,'content':encoded(manifest).decode()},owner_metadata={'schema_version':OBJECT_SCHEMA,'request_id':request_id,'intent':intent})
    from laplace.core.identity import reference
    return _read_object(root,scope,reference('domain.projects','artifact',{'project':project,'id':saved['id']}))|{'state':'RECORDED','reused':False}


def _read_object(root,scope,reference):
    from laplace.work import object_facets as F
    project=F._project(reference);F._scope(scope,project)
    if reference.get('owner')!='domain.projects' or reference.get('kind')!='artifact':raise Refused('MANIFEST_ART_REQUIRED')
    value,meta=_retained_manifest(root,project,reference['identity']['id'])
    if value.get('schema_version')!=OBJECT_SCHEMA:raise Refused('MANIFEST_ART_REQUIRED')
    from laplace.core.identity import reference as make_reference
    entries=[]
    for item in value['entries']:
        row=json.loads(encoded(item))
        if item.get('class')=='included':
            try:
                now=F._observe(root,scope,item['reference']);row['currentness']='CURRENT' if revision_matches(item['basis'],now['basis']) else 'STALE'
                if item['reference']['kind']=='workflow-definition':
                    from laplace.pipeline import workflow_definitions as D
                    from laplace.work import owner_discovery as O
                    context=O.project_scope(now['project'],scope.door) if now.get('project') else scope
                    row['frozen_read']=D.scoped_handle(context,item['reference']['identity']['id'],item['reference'].get('version',{}).get('definition_revision'))
                    row['adapter']={'kind':'workflow-definition-editor','reference':item['reference']}
            except (OSError,ValueError):row['currentness']='UNAVAILABLE'
            if item.get('carried'):
                if item.get('artifact_id'):
                    from laplace.projects import material_intake
                    row['frozen_read']=material_intake.artifact_handle(project,{'id':item['artifact_id'],'expected_sha256':item['carried']['sha256'],'offset':0,'limit':4000})
                else:
                    frozen=make_reference('domain.projects','source-file',{'project':project,'path':item['carried']['path'],'scope':'project'})
                    row['frozen_read']=F.handle({'facet':'object','reference':frozen,'section':'body','as_of':item['carried']['sha256'],'offset':0,'limit':4000})
        entries.append(row)
    read=F.handle({'facet':'handover','reference':reference})
    lineage_action=None
    if value['selection'].get('definitions'):
        fields=[{'name':'destination','label':'Fresh local recipient directory','type':'text','required':True},
            *[{'name':k,'label':label,'type':'number','required':True,'value':value['budgets'][k]} for k,label in
                [('max_files','Maximum output files'),('max_rows','Maximum selected rows'),('max_bytes','Maximum output bytes')]]]
        lineage_action={'id':'export-lineage','title':'Prepare complete lineage export (v2)','permitted':scope.kind=='owned-workspace',
            'fields':fields,**object_handle(project,{'action':'request','definition_transport':'lineage-v2','reference':reference,
                'expected_basis':meta['revision'],'request_id':'lineage-'+canonical_digest([value['request_id'],reference]).removeprefix('sha256:')[:32]})}
    return {'schema_version':OBJECT_SCHEMA,'project':project,'reference':reference,'basis':meta['revision'],'request_id':value['request_id'],'intent_sha256':value['intent'],'entries':entries,
        'reconcile':object_handle(project,{'action':'request','request_id':value['request_id']}),
        'scope_id':__import__('laplace.pipeline.workflow_definitions',fromlist=['_scope_id'])._scope_id(root,scope),
        'read':read,'actions':[{'id':'export','title':'Export selected handover','permitted':scope.kind=='owned-workspace',
            'fields':[{'name':'destination','label':'Fresh local recipient directory','type':'text','required':True}],
            **object_handle(project,{'action':'export','reference':reference,'expected_basis':meta['revision']}),
            'reconcile':{**object_handle(project,{'action':'inspect','reference':reference,'expected_basis':meta['revision']}),'field':'destination'}},*([lineage_action] if lineage_action else [])],
        'qualification':value['qualification']}


def object_request(root,scope,payload,*,door):
    """Human/local operator selected export; native readers cannot mint share consent."""
    from jsonschema import Draft202012Validator
    from laplace.work import object_facets as F
    issue=next(Draft202012Validator(object_contract()).iter_errors(payload),None)
    if issue:raise Refused('INVALID_HANDOVER_REQUEST')
    if payload.get('definition_transport')=='lineage-v2' and payload['action'] in {'request','export','continue','inspect'}:
        from laplace.projects import project_handover_lineage as lineage
        return lineage.request(root,scope,payload,door=door)
    from laplace.projects import project_handover_lineage as lineage
    if set(lineage.contract_properties())&set(payload) or 'definitions' in payload:raise Refused('LINEAGE_PROFILE_ACTION_REQUIRED')
    root=Path(root).resolve();action=payload['action'];project=payload.get('project') or F._project(payload.get('reference') or {})
    F._scope(scope,project)
    if action in {'prepare','export','inspect'} and (scope.kind!='owned-workspace' or door.get('origin') not in {'human','sdk'}):raise Refused('EXPLICIT_AUTHOR_EXPORT_SELECTION_REQUIRED')
    if action=='prepare':return _prepare_object(root,scope,{**payload,'project':project})
    if action=='request':
        value=_object_recovery(root,project,payload['request_id'])
        if value['state']=='RECORDED':return _read_object(root,scope,value['reference'])|{'state':'RECORDED','reused':True}
        return value
    if action=='read':return _read_object(root,scope,payload['reference'])
    if action=='inspect':
        destination=Path(payload['destination']).absolute()
        # Exact named inspection is local human/SDK only; no selected source is
        # re-resolved just to discover whether this original export published.
        if '..' in Path(payload['destination']).parts or destination.resolve()!=destination or destination.is_symlink():raise Refused('UNSAFE_DESTINATION')
        if not destination.exists():return {'state':'NONE','terminal':False,'destination':str(destination),'reason':'No completed directory is visible; an original export may still be in flight.'}
        try:
            result=inspect_handover(destination);selected=result
            if payload.get('reference'):
                reference=payload['reference'];original,meta=_retained_manifest(root,project,reference['identity']['id'])
                if not revision_matches(payload.get('expected_basis'),meta['revision']):raise Refused('SELECTED_MANIFEST_CHANGED')
                transported=C._json(C._safe(destination,MANIFEST))['plan'].get('selection') or {}
                if transported.get('manifest_id')!=reference['identity']['id'] or not revision_matches(transported.get('manifest_sha256'),meta['revision']):raise Refused('DESTINATION_OTHER_MANIFEST')
                manifest,_meta=_retained_manifest(destination,project,reference['identity']['id'])
                if manifest!=original:raise Refused('DESTINATION_OTHER_MANIFEST')
            return {**result,'state':'COMPLETE_MATCH','destination':str(destination),'research_handover':_inspect_object(destination)}
        except (OSError,ValueError,KeyError):return {'state':'UNKNOWN','destination':str(destination),'reason':'Destination is incomplete, changed or does not prove this exact exported manifest. Preserve the original export request.'}

    if action=='export':
        reference=payload['reference'];manifest,meta=_retained_manifest(root,project,reference['identity']['id'])
        if not revision_matches(payload.get('expected_basis'),meta['revision']):raise Refused('SELECTED_MANIFEST_CHANGED')
        selection={**manifest['selection'],'manifest_id':reference['identity']['id'],'manifest_sha256':meta['revision']}
        selection['artifact_ids']=list(dict.fromkeys([*selection['artifact_ids'],reference['identity']['id']]))
        planned=plan(root,project,**manifest['budgets'],selection=selection,caller=scope);destination=Path(payload['destination']).absolute()
        if destination.exists():
            prior=inspect_handover(destination)
            if prior['manifest_digest']!=planned['manifest_digest']:raise Refused('DESTINATION_OCCUPIED')
            return {'status':'EXPORTED','reused':True,'destination':str(destination),'receipt':prior['manifest_digest'],'inspection':_inspect_object(destination)}
        result=export(root,destination,planned,caller=scope)
        return {**result,'inspection':_inspect_object(destination)}
    raise Refused('UNSUPPORTED_HANDOVER_ACTION')


def _inspect_object(root):
    from laplace.projects import artifacts
    root=Path(root);receipt=C._json(root/MANIFEST);selection=receipt['plan'].get('selection')
    if not selection:return None
    value,meta=_retained_manifest(root,receipt['plan']['project'],selection['manifest_id']);project=value['project'];checked=[]
    for item in value['entries']:
        if item.get('class')!='included':checked.append({'class':item['class'],'state':'EXPLICIT_NOT_CARRIED'});continue
        if item.get('carried'):
            target,relative,pin=C.selected_file(root,project,item['carried']['path'],'project')
            if not revision_matches(pin['sha256'],item['carried']['sha256']):raise Refused('RECIPIENT_INCLUDED_BYTES_CHANGED')
            checked.append({'reference':item['reference'],'basis':item['basis'],'class':'included','state':'RESOLVED_FROZEN_BYTES','sha256':pin['sha256']})
        else:checked.append({'reference':item['reference'],'class':'included','state':'OWNER_TRANSFERRED_DEFINITION'})
    return {'state':'REOPENED','entries':checked,'origin_reads':0,'providers_started':0,
        'qualification':'Ordinary recipient artifact/file/definition owners resolve selected frozen bytes. Original scientific references identify the snapshot subject; they do not silently become new live scientific assertions.'}
