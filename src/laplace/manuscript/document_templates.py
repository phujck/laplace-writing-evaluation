"""Source-preserving template candidates in existing PROP/CAS/DEC/WA custody.

Document composition owns current source; dependency/build owners own closure and
BLD proof. This family adapter seals authored changes and validates that exact
proof inside the existing physical source transaction. It owns no manuscript,
settings store, scheduler or independent application writer.
"""
from __future__ import annotations

from laplace.core import scoped as core_scoped
import copy
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode
import uuid
import zipfile

from laplace.manuscript.template_contracts import SCHEMA, MAX_PART, REF, read_contract, change_contract


class TemplateRefused(ValueError):
    def __init__(self, project, reason):
        super().__init__(reason)
        self.details={'code':'TEMPLATE_INSPECTION_REQUIRED','next_reads':[current_document_read(project)],
            'reason':reason,'source_changed':False}


def legacy_refusal(project, reason):
    return TemplateRefused(project, reason)


def error_details(error):
    for _ in range(8):
        if isinstance(error,TemplateRefused):return dict(error.details)
        if error is None:break
        error=error.__cause__ or error.__context__
    return {}


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def pin(content):
    return 'sha256:' + hashlib.sha256(content if isinstance(content, bytes) else content.encode()).hexdigest()


def _validate(value, schema):
    from jsonschema import Draft202012Validator
    error = next(Draft202012Validator(schema).iter_errors(value), None)
    if error:
        raise ValueError('Template request does not match its owner contract: ' + error.message[:600])


def handle(project, payload, *, write=False):
    from laplace.core import grammar
    operation = 'style' if write else 'document'
    route = '/work/style' if write else '/authoring/document'
    fields = {key: json.dumps(value, separators=(',', ':')) if isinstance(value, (dict, list)) else value
              for key, value in payload.items()}
    return {'operation': operation, 'project': project, 'permitted': True,
        'payload': {'project': project, **copy.deepcopy(payload)},
        'http': {'method': 'POST' if write else 'GET', 'url': route if write else route+'?'+urlencode({'project': project, **fields})},
        'native_request': {'verb': 'change' if write else 'read', 'concept': 'document-form@project',
            'target': project, 'expected': [], 'payload': grammar.to_payload(payload), 'by': ''}}


def candidate(project, ref, root):
    from laplace.writing import records
    _validate(ref, REF)
    row = records.selected_journal_fields(project, ref['id'], root, fields=['record', 'id', 'project',
        'candidate_kind', 'proposal', 'proposal_instance_version', 'author', 'origin_turn_id'])
    body = row.get('proposal') or {}
    if (row.get('record') != 'writing-proposal' or row.get('candidate_kind') != 'document-template'
            or row.get('proposal_instance_version') != ref['version'] or body.get('schema_version') != SCHEMA
            or body.get('project') != project or digest(body) != ref['version']):
        raise ValueError('Select the exact immutable document-template candidate and version.')
    return {'record': row, 'proposal': body}


def _actor(project, root, actor, *, apply=False):
    from laplace.writing import records
    actor = copy.deepcopy(actor or {'kind': 'human'})
    if actor.get('kind') not in {'human', 'agent'}:
        raise ValueError('Template actions require the actual human or admitted native caller.')
    if actor['kind'] == 'agent':
        index = records.index(root); turn = index.turns.get(actor.get('turn_id'))
        if not turn or index.project(turn) != project:
            raise ValueError('The template action needs its actual admitted project caller turn.')
        if turn.get('mode') == 'review' or actor.get('mode') == 'review':
            raise ValueError('Reviewers inspect template candidates; an author prepares and applies source changes.')
        if apply and (turn.get('parent_turn_id') or turn.get('dispatch_id') or actor.get('dispatch_id')):
            raise ValueError('A dispatched child may prepare a candidate; its authorised parent applies it.')
    return actor


def _material_inputs(root, selectors):
    """Resolve exact declared material, never a basename or writable alias."""
    from laplace.projects import writing_sources
    result = []
    for selected in selectors:
        _, path = writing_sources._path(root, selected)
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('Template material must be an exact readable file inside this workspace.')
        raw = path.read_bytes(); source = copy.deepcopy(selected)
        if selected.get('member'):
            member = PurePosixPath(selected['member'])
            if member.is_absolute() or '..' in member.parts:
                raise ValueError('Choose the exact safe retained archive member.')
            import io
            archive_raw=raw
            with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
                info = archive.getinfo(str(member))
                from laplace.manuscript.reconciliation import MAX_TEXT
                if info.file_size > MAX_TEXT:
                    raise ValueError('The template member exceeds the existing source-text resource bound.')
                raw = archive.read(info)
            source['archive_sha256'] = pin(archive_raw)
            alias = None  # Provenance witness, never a guessed install destination.
        else:
            alias = path.relative_to(root).as_posix()
        result.append({'path': alias, 'content': raw.decode('utf-8'), 'sha256': pin(raw), 'source': source})
    return result


def _source_inputs(project, payload, root):
    from laplace.manuscript import manuscript_source, proposal_preflight
    from laplace.manuscript import proposal_currentness
    source = manuscript_source.resolve(project, repo_root=root, include_candidates=False)
    source = {**source, 'selection_identity': manuscript_source.selection_identity(source, project)}
    if source.get('read_only') or not source.get('root'):
        raise ValueError('Select an editable canonical manuscript before preparing a template change.')
    tree = manuscript_source.traversal(root/source['root'], repo_root=root)
    if tree.get('diagnostics'):
        raise ValueError('The selected source tree is incomplete; inspect its declared include diagnostics.')
    selected = set(tree['files']); guards = payload['guards']
    if guards['expected_selection'] != source['selection_identity']:
        raise ValueError('CHANGED_INPUT: the selected manuscript changed; the local draft is retained.')
    entries = payload.get('source_edits') or payload.get('edits') or []
    originals = {}; changes = {}; spans = {}
    for entry in entries:
        name = entry['file']; path = (root/name).resolve()
        if Path(name).is_absolute() or '..' in Path(name).parts or name not in selected:
            raise ValueError('Use the exact owner-issued current writable source file, never a guessed path.')
        manuscript_source.source_access(project, path, root, source=source, source_tree=tree, writable=True,
            expected_selection=guards['expected_selection'])
        physical = path.read_bytes()
        if guards['source_guards'].get(name) != pin(physical):
            raise ValueError('CHANGED_INPUT: the inspected source bytes changed; nothing was prepared or applied.')
        raw, _ = proposal_currentness._source_text_facts(physical)
        originals.setdefault(name, raw)
        if 'content' in entry:
            if name in changes:
                raise ValueError('Provide one captured buffer per exact source file.')
            changes[name] = entry['content'].replace('\r\n','\n').replace('\r','\n')
        else:
            lo, hi = entry['line_start'], entry['line_end']; lines = raw.split('\n')
            if hi < lo or hi > len(lines) or '\n'.join(lines[lo-1:hi]) != entry['before']:
                raise ValueError('CHANGED_INPUT: the exact inspected source span is unavailable.')
            if any(lo <= b and hi >= a for a,b,_ in spans.get(name, [])):
                raise ValueError('Template source edits overlap.')
            spans.setdefault(name, []).append((lo,hi,entry['after']))
    for name, edits in spans.items():
        lines = originals[name].split('\n')
        for lo, hi, after in sorted(edits, reverse=True):
            lines[lo-1:hi] = after.replace('\r\n','\n').replace('\r','\n').split('\n')
        changes[name] = '\n'.join(lines)
    from laplace.manuscript.reconciliation import MAX_TEXT
    result = []
    for name, after in changes.items():
        if len(after.encode()) > MAX_TEXT:
            raise ValueError('The proposed source exceeds the existing 2 MB source-application text bound.')
        errors = proposal_preflight.staged_integrity_errors(originals[name], after, is_root=name==source['root'])
        from laplace.manuscript import review_surface
        if review_surface._STRUCT_LINE_RE.findall(originals[name]) != review_surface._STRUCT_LINE_RE.findall(after):
            errors.append('A template change cannot rewrite protected paragraph/provenance markers.')
        if errors:
            raise ValueError('; '.join(errors))
        result.append({'file': name, 'before': originals[name], 'after': after,
            'before_sha256': guards['source_guards'][name], 'after_sha256': pin(after),
            'guards': {'expected_selection': guards['expected_selection'], 'expected_source_digest': guards['source_guards'][name]}})
    return source, result


def _read_inputs(project, root, actor, payload):
    """Exact supplied native receipts; source bytes remain independently guarded."""
    from laplace.writing import records
    rows=[]
    for key in ('source_read_ids','template_read_ids'):
        for ident in payload.get(key) or []:
            row=records.selected_journal_fields(project,ident,root,fields=['id','record','project','turn_id','operation','source_scope','payload','output_sha256'])
            if row.get('record')!='writing-tool-read' or actor.get('kind')!='agent' or row.get('turn_id')!=actor.get('turn_id'):
                raise ValueError('Use exact source/material READ receipts consumed by this actual caller.')
            if row.get('operation') not in ({'source','projection/source'} if key=='source_read_ids' else {'repository','material_references','read_artifact'}):
                raise ValueError('The supplied read is not the declared source/material owner.')
            if key=='source_read_ids':
                for scope in row.get('source_scope') or []:
                    expected=payload['guards']['source_guards'].get(scope.get('file'))
                    if expected is not None and scope.get('expected_source_digest')!=expected:
                        raise ValueError('CHANGED_INPUT: supplied source READ predates the captured source guard.')
            rows.append({name:row[name] for name in ('id','operation','output_sha256') if name in row})
    return rows


def prepare(project, payload, root, actor):
    from laplace.manuscript import tex_dependencies
    from laplace.writing import records as writing_records
    from laplace.writing import records
    from laplace.representation import writing_bodies as bodies
    source, changes = _source_inputs(project, payload, root)
    material = _material_inputs(root, payload.get('template_sources') or [])
    closure = tex_dependencies.prepare_closure(project, root, source,
        {row['file']: row['after'] for row in changes}, template_sources=material)
    body = {'schema_version': SCHEMA, 'project': project,
        'selected_source': {key: source.get(key) for key in ('root','manuscript_dir','edition','selection_identity')},
        'source_edits': changes, 'template_inputs': material, 'declaration_closure': closure,
        'consumed_reads': _read_inputs(project, root, actor, payload), 'reason': payload['reason']}
    if payload.get('draft_basis'):
        draft=payload['draft_basis']; included=next((row for row in changes if row['file']==draft['file']),None)
        if included is None:raise ValueError('The captured draft belongs to a different source file.')
        body['included_draft']={**draft,'input_content_sha256':included['after_sha256']}
    version=digest(body)
    # Exact content/basis identity is a metadata lookup, never a project history/body scan.
    key=(project,version);previous=records.index(root).template_candidates_by_version.get(key)
    if previous:
        return inspect(project,{'view':'template','candidate_ref':{'id':previous['id'],'version':version}},root)
    ident='PROP-'+uuid.uuid4().hex
    retained=bodies.retain_leaves(root,body,texts=('before','after','content'))
    writing_records.bank(root,{'record':'writing-proposal','id':ident,'project':project,
        'candidate_kind':'document-template','proposal_instance_version':version,'proposal_content_sha256':version,
        'template_selection':source['selection_identity'],'proposal':retained,'author':actor,'origin_turn_id':actor.get('turn_id')})
    return inspect(project,{'view':'template','candidate_ref':{'id':ident,'version':version}},root)


def _applications(project, ref, root):
    from laplace.writing import records
    return [row for row in records.index(root).by_candidate.get(ref['id'], [])
        if row.get('record')=='writing-application' and row.get('candidate_version')==ref['version']]


def _currentness(project, body, root, *, postimage=False):
    from laplace.manuscript import manuscript_source, tex_dependencies
    source=manuscript_source.resolve(project,repo_root=root,include_candidates=False)
    source={**source,'selection_identity':manuscript_source.selection_identity(source,project)}
    changed=[]
    if source.get('selection_identity')!=body['selected_source']['selection_identity'] or source.get('read_only'):
        changed.append('selected-source')
    for row in body['source_edits']:
        path=root/row['file'];expected=row['after_sha256'] if postimage else row['before_sha256']
        if not path.is_file() or pin(path.read_bytes())!=expected:changed.append(row['file'])
    # Dependency owner supplies the same original/proposed pins for preparation,
    # build and Apply. Source files replaced by the candidate are checked above.
    closure=body['declaration_closure']
    for name in tex_dependencies.closure_changes(closure,root,ignore_files={row['file'] for row in body['source_edits']}):
        if name not in {row['file'] for row in body['source_edits']}:
            changed.append(name)
    for entry in body.get('template_inputs') or []:
        source_ref=entry['source']
        if _material_inputs(root,[{key:source_ref[key] for key in ('repository','path','member') if key in source_ref}])[0]['sha256']!=entry['sha256']:
            changed.append('template-material:'+source_ref['path'])
    return {'status':'CHANGED_INPUT' if changed else 'CURRENT','changed_inputs':list(dict.fromkeys(changed))}


def _pending(project, ref, root):
    from laplace.writing import records
    rows=records.index(root).by_candidate.get(ref['id'],[])
    closed={row.get('application_intent_id') for row in rows if row.get('decision')=='template-no-source-effect'}
    return next((row for row in reversed(rows) if row.get('id') not in closed and row.get('record')=='writing-proposal-decision'
        and row.get('decision')=='template-application-start' and row.get('proposal_version')==ref['version']),None)


def _application_permitted(project, root, actor):
    if actor is None or actor.get('kind')=='human':return True
    from laplace.writing import records
    index=records.index(root);turn=index.turns.get(actor.get('turn_id')) or {}
    return bool(index.project(turn)==project and turn.get('mode')!='review' and actor.get('mode')!='review'
        and not turn.get('parent_turn_id') and not turn.get('dispatch_id') and not actor.get('dispatch_id'))


def inspect(project, payload, root, *, actor=None):
    from laplace.writing import records
    from laplace.manuscript import build_targets
    _validate(payload,read_contract());root=Path(root).resolve()
    if payload['view']=='template-candidates':
        rows=records.index(root).template_candidates_by_project.get(project,[])
        offset=payload.get('offset',0);limit=min(payload.get('limit',20),20)
        result = {'project':project,'schema_version':SCHEMA,'candidates':[{
            'candidate_ref':{'id':row['id'],'version':row['proposal_instance_version']},'author':row.get('author'),
            'read_handle':handle(project,{'view':'template','candidate_ref':{'id':row['id'],'version':row['proposal_instance_version']}})}
            for row in reversed(rows[max(0,len(rows)-offset-limit):len(rows)-offset])],
            'coverage':{'total':len(rows),'offset':offset,'returned':min(limit,max(0,len(rows)-offset)),'bodies_loaded':0}}
        if offset+limit<len(rows):result['next_read']=handle(project,{'view':'template-candidates','offset':offset+limit,'limit':limit})
        return result
    ref=payload['candidate_ref'];selected=candidate(project,ref,root);row=selected['record'];body=selected['proposal']
    part=payload.get('part','metadata')
    if part in {'preview-output','preview-image'}:
        observed=build_targets.inspect_preview(project,ref,payload['preview_ref'],root)
        result={'schema_version':SCHEMA,'project':project,'candidate_ref':ref,'preview_ref':payload['preview_ref'],
            'output':observed['output'],'observed_input_revision':observed['observed_input_revision']}
        current=_currentness(project,body,root)
        action=handle(project,{'action':'apply','candidate_ref':ref,'preview_ref':payload['preview_ref']},write=True)
        action['permitted']=(current['status']=='CURRENT' and not _pending(project,ref,root)
            and not any(item.get('complete') for item in _applications(project,ref,root))
            and any(entry['before']!=entry['after'] for entry in body['source_edits'])
            and not observed.get('current_input_changes') and _application_permitted(project,root,actor))
        if not action['permitted']:action['reason']='Source/proof changed, application retained, or no source change is required; inspect the exact candidate.'
        result.update(currentness=current,apply_action=action)
        if part=='preview-image':
            from laplace.projects import writing_sources
            rendered=writing_sources.render_pdf_page(observed['path'],payload['page'])
            result.update(rendered)
            if pin(Path(observed['path']).read_bytes())!=payload['preview_ref']['output']['content_revision']:
                raise ValueError('The reviewed PDF changed during image rendering; no substitute output was selected.')
        return result
    if part!='metadata':
        if part in {'original','proposed','diff'}:
            name=payload.get('file');entry=next((item for item in body['source_edits'] if item['file']==name),None)
            if not entry:raise ValueError('Use the exact owner-issued changed-file read handle.')
            text=entry['before' if part=='original' else 'after'] if part!='diff' else ''.join(difflib.unified_diff(
                entry['before'].splitlines(keepends=True),entry['after'].splitlines(keepends=True),fromfile=name,tofile=name))
        else:text=json.dumps(body['declaration_closure'] if part=='closure' else body['declaration_closure'].get('diagnostics',[]),ensure_ascii=False,indent=2)
        from laplace.manuscript.reconciliation import _text_part
        chunk,_=_text_part(text,payload.get('offset',0),payload.get('limit',MAX_PART))
        result={'schema_version':SCHEMA,'project':project,'candidate_ref':ref,'part':part,'file':payload.get('file'),**chunk}
        if chunk['coverage']['has_more']:result['next_read']=handle(project,{**payload,'offset':chunk['coverage']['end']})
        return result
    applications=_applications(project,ref,root);application=next((item for item in reversed(applications) if item.get('complete')),None)
    current=_currentness(project,body,root,postimage=bool(application));pending=_pending(project,ref,root)
    if payload.get('preview_ref'):
        preview_ref=payload['preview_ref']
        try:
            verified=build_targets.inspect_preview(project,ref,preview_ref,root)
            latest={'state':'done','ok':True,'preview_ref':preview_ref,
                'build_job':preview_ref['build_job'],'observed_input_revision':verified['observed_input_revision']}
        except (ValueError,OSError) as error:
            latest={'state':'unavailable','ok':False,'requested_preview_ref':preview_ref,'reason':str(error)}
            preview_ref=None
    else:
        latest=build_targets.latest_preview(project,ref,root)
        preview_ref=latest.get('preview_ref') if isinstance(latest,dict) else None
    apply_action=None
    if not application and not pending and preview_ref:
        apply_action=handle(project,{'action':'apply','candidate_ref':ref,'preview_ref':preview_ref},write=True)
        apply_action.update(permitted=_application_permitted(project,root,actor) and current['status']=='CURRENT' and any(entry['before']!=entry['after'] for entry in body['source_edits']))
        if not apply_action['permitted']:apply_action['reason']='No source change is required.' if not any(entry['before']!=entry['after'] for entry in body['source_edits']) else 'Consumed source/template inputs changed. The candidate and draft remain retained.'
    files=[{key:entry[key] for key in ('file','before_sha256','after_sha256')}
        | {'changed':entry['before']!=entry['after'],'reads':{part:handle(project,{'view':'template','candidate_ref':ref,'part':part,'file':entry['file']})
            for part in ('original','proposed','diff')}} for entry in body['source_edits']]
    result={'schema_version':SCHEMA,'project':project,'candidate_ref':ref,'candidate_kind':'document-template','author':row['author'],
        'read_handle':handle(project,{'view':'template','candidate_ref':ref}),'selected_source':body['selected_source'],
        'currentness':current,'source_changes':files,'reason':body['reason'],'included_draft':body.get('included_draft'),
        'closure':{key:value for key,value in body['declaration_closure'].items() if key in {'status','revision','input_revision','diagnostics','counts','local_bytes'}},
        'closure_read':handle(project,{'view':'template','candidate_ref':ref,'part':'closure'}),
        'build':latest,'apply_action':apply_action,'semantic_currentness':'NOT_ASSERTED',
        'application_recording':{'status':'RECORDED' if application else 'UNPUBLISHED' if pending else 'NOT_APPLIED',
            **({'application_id':application['id']} if application else {})},
        'application_id':application['id'] if application else None}
    actions=build_targets.handles(project,build_targets.candidate_target(project,ref,body,root))
    result['build_status_read']=actions['status_read']
    if not application:
        result['build_action']=actions['build_action']
    if pending and not application:
        observations=[item for item in records.index(root).by_candidate.get(ref['id'],[]) if item.get('decision')=='template-source-observation'
            and item.get('application_intent_id')==pending['id'] and item.get('proposal_version')==ref['version']]
        if len(observations)==1:
            result['recovery_action']=handle(project,{'action':'recover','candidate_ref':ref,'application_intent_id':pending['id']},write=True)
        else:
            result['application_recording']['status']='UNKNOWN'
            result['recording_gap']='Application admission is retained; the exact physical effect/recording observation is unavailable. Inspect current source; no replay action is issued.'
    from laplace.projects import writing_storage
    result['cache']=writing_storage.candidate_cache(project,ref,root)
    if preview_ref:
        result['preview_pdf_read']=output_handle(project,ref,preview_ref)
        result['preview_image_read']=image_handle(project,ref,preview_ref,1)
    return result


def output_handle(project, ref, preview_ref):
    payload={'view':'template','candidate_ref':ref,'preview_ref':preview_ref,'part':'preview-output'}
    result=handle(project,payload)
    result['http']={'method':'GET','url':'/work/style/pdf?'+urlencode({'project':project,'candidate_ref':json.dumps(ref,separators=(',',':')),
        'preview_ref':json.dumps(preview_ref,separators=(',',':'))})}
    result['kind']='pdf';return result


def image_handle(project, ref, preview_ref, page):
    result=handle(project,{'view':'template','candidate_ref':ref,'preview_ref':preview_ref,'part':'preview-image','page':page})
    result['http']={'method':'GET','url':output_handle(project,ref,preview_ref)['http']['url']+'&format=png&page='+str(page)}
    result['kind']='image';return result


def discovery(project, root, source=None):
    from laplace.manuscript import manuscript_source
    root=Path(root).resolve()
    source=source or manuscript_source.resolve(project,repo_root=root,include_candidates=False)
    source={**source,'selection_identity':manuscript_source.selection_identity(source,project)}
    if not source.get('root'):return {'available':False,'reason':'Select a manuscript source.'}
    file=source['root'];path=root/file;revision=pin(path.read_bytes())
    access=manuscript_source.source_access(project,path,root,source=source)
    action=handle(project,{'action':'prepare','guards':{'expected_selection':source['selection_identity'],
        'source_guards':{file:revision}},'reason':'Reviewed template source change'},write=True)
    action.update(permitted=not source.get('read_only'),authored_fields=['source_edits OR edits','reason'])
    return {'available':True,'current_source_file':file,'expected_source_digest':revision,
        'expected_selection':source['selection_identity'],
        'current_source_read':{**manuscript_source.source_handles(project,file,revision,access)['read_handle'],
            'native_request':{'verb':'read','concept':'source-file@paragraph','target':project+'::'+file,'expected':[],
                'payload':__import__('laplace.core.grammar',fromlist=['to_payload']).to_payload({'corpus':project,'file':file,'view':'source','offset':0,'limit':4096}),'by':''}},
        'candidates_read':handle(project,{'view':'template-candidates'}),'prepare_action':action,
        'input_instruction':'Use exact saved-source read guards and bounded edits, or explicitly capture the existing writable TeX draft. No Save is required for preview.',
        'preview_changes_source':False,'source_class_authoritative':True}


def change(project, payload, root, *, actor=None):
    from laplace.writing import records as writing_records
    root=Path(root).resolve();_validate(payload,change_contract())
    actor=_actor(project,root,actor,apply=payload['action']!='prepare')
    with writing_records.proposal_write_lock(root):
        if payload['action']=='prepare':return prepare(project,payload,root,actor)
        if payload['action']=='recover':return recover(project,payload,root,actor)
        return apply(project,payload,root,actor)


def _application_proposal(body):
    """Linear exact common-frame reduction, never a similarity rebase."""
    from laplace.manuscript import proposal_preflight
    edits=[]
    for entry in body['source_edits']:
        if entry['before']==entry['after']:continue
        old=entry['before'].split('\n');new=entry['after'].split('\n');prefix=0
        while prefix<min(len(old),len(new)) and old[prefix]==new[prefix]:prefix+=1
        suffix=0
        while suffix<min(len(old)-prefix,len(new)-prefix) and old[len(old)-1-suffix]==new[len(new)-1-suffix]:suffix+=1
        # An insertion is witnessed by its adjacent old line, not an invented
        # empty numerical range outside the source owner contract.
        if prefix==len(old):prefix=max(0,prefix-1)
        hi=len(old)-suffix
        if hi<=prefix:
            hi=prefix+1;suffix=len(old)-hi
        after_end=len(new)-suffix if suffix else len(new)
        lo=prefix+1
        edits.append({'file':entry['file'],'line_start':lo,'line_end':hi,
            'before':'\n'.join(old[prefix:hi]),'after':'\n'.join(new[prefix:after_end]),
            'source_anchor':proposal_preflight.source_anchor(entry['before'],lo,hi)})
    return {'answer':'Reviewed document-template source change; scientific acceptance is not asserted.','edits':edits}


def validate_candidate(root, project, subject, *, source=None):
    """Called inside the existing physical transaction, before any source write."""
    from laplace.manuscript import build_targets
    ref=subject['candidate_ref'];body=candidate(project,ref,root)['proposal']
    current=_currentness(project,body,Path(root))
    if current['status']!='CURRENT':raise ValueError('CHANGED_INPUT: template consumed inputs changed: '+', '.join(current['changed_inputs']))
    preview=build_targets.inspect_preview(project,ref,subject['preview_ref'],root)
    if preview.get('current_input_changes'):raise ValueError('CHANGED_INPUT: recorded preview inputs changed: '+', '.join(preview['current_input_changes']))
    if subject['proposal']!=_application_proposal(body):raise ValueError('The proposed physical edits differ from the sealed template candidate.')
    return {'currentness':'CURRENT','basis_kind':'document-template','semantic_currentness':core_scoped.semantic_currentness([]),
        'review_obligations':[],'transition_ids':[], 'preview_ref':copy.deepcopy(subject['preview_ref'])}


def _subject(project, row, proposal, preview_ref, actor, root):
    from laplace.writing import records
    version=row['proposal_instance_version'];ref={'id':row['id'],'version':version}
    applications=[records.selected_journal_fields(project,item['id'],root,fields=['id','record','project','candidate_id',
        'candidate_ref','candidate_version','candidate_edit_ids','complete','source_effect','owned_changes','actor','receipts','rollbacks','status'])
        for item in _applications(project,ref,root)]
    return {**row,'candidate_ref':ref,'proposal':proposal,'pending_proposal':proposal,
        '_selected_proposal_version':version,'proposal_versions':{version:proposal},'proposal_bases':{version:{}},
        'document':row['proposal']['selected_source'],'applications':applications,'proposal_decisions':[],
        'application_actor':actor,'preview_ref':preview_ref}


def apply(project, payload, root, actor):
    from laplace.manuscript import manuscript_source
    from laplace.manuscript import source_application
    from laplace.manuscript import source_effects
    from laplace.writing import records as writing_records
    from laplace.manuscript import build_targets, source_effects
    ref=payload['candidate_ref'];selected=candidate(project,ref,root);body=selected['proposal'];proposal=_application_proposal(body)
    previous=next((item for item in reversed(_applications(project,ref,root)) if item.get('complete')),None)
    if previous:
        return {**inspect(project,{'view':'template','candidate_ref':ref},root),'reused':True,'changed':False}
    if _pending(project,ref,root):
        raise ValueError('A template application is already retained. Inspect its exact recording/recovery; do not replay source.')
    subject=_subject(project,selected['record'],proposal,payload['preview_ref'],actor,root)
    changes=[]
    # Same lock order as the shared source owner: selection, then exact physical
    # inputs. Dependency leases guard inputs, never confer write permission.
    closure=body['declaration_closure']
    paths={(root/name).resolve() for name in closure['basis']}
    with manuscript_source.selection_mutation(project,root), manuscript_source.source_mutation(paths):
        validate_candidate(root,project,subject)
        if not proposal['edits']:
            files=[source_effects.observed_file(root,root/row['file'],(root/row['file']).read_bytes(),(root/row['file']).read_bytes()) for row in body['source_edits']]
            return {**inspect(project,{'view':'template','candidate_ref':ref},root),'changed':False,'complete':True,
                'source_effect':source_effects.receipt(project,body['selected_source']['selection_identity'],files),
                'application_recording':{'status':'NOT_NEEDED'},'current_document_read':current_document_read(project)}
        intent_id='DEC-'+uuid.uuid4().hex
        writing_records.bank(root,{'record':'writing-proposal-decision','id':intent_id,'project':project,
            'candidate_kind':'document-template','candidate_id':ref['id'],'proposal_version':ref['version'],
            'decision':'template-application-start','actor':actor,'preview_ref':payload['preview_ref']})
        try:
            application=source_application._apply_proposal_locked(root,{'project':project,'candidate_id':ref['id']},
                proposal_override=proposal,candidate_subject=subject,candidate_version=ref['version'],
                proposal_digest=ref['version'],allow_multiple=True,human_reviewed=True,
                application_origin='document-template',source_changes=changes)
        except Exception:
            if all((root/entry['file']).is_file() and pin((root/entry['file']).read_bytes())==entry['before_sha256'] for entry in body['source_edits']):
                writing_records.bank(root,{'record':'writing-proposal-decision','id':'DEC-'+uuid.uuid4().hex,
                    'project':project,'candidate_kind':'document-template','candidate_id':ref['id'],'proposal_version':ref['version'],
                    'decision':'template-no-source-effect','application_intent_id':intent_id,
                    'qualification':'At refusal the exact original source preimages remain unchanged.'})
            raise
    if changes:source_effects.finish_source_changes(root,project,application,changes)
    effect=application.get('source_effect')
    recorded=bool(application.get('id'))
    observation_id=None;recording_error=None
    if not recorded and effect and effect['state'] in {'COMMITTED','UNCHANGED'}:
        observation_id='DEC-'+uuid.uuid4().hex
        try:
            writing_records.bank(root,{'record':'writing-proposal-decision','id':observation_id,'project':project,
                'candidate_kind':'document-template','candidate_id':ref['id'],'proposal_version':ref['version'],
                'decision':'template-source-observation','application_intent_id':intent_id,
                'source_effect':effect,'actor':actor,'receipts':application.get('receipts',[]),
                'owned_changes':application.get('owned_changes'),
                'allocated_application_id':(application.get('application_tracking') or {}).get('attempted_id')})
        except (ValueError,OSError) as error:
            observation_id=None;recording_error=str(error)
    result={**inspect(project,{'view':'template','candidate_ref':ref},root),
        'application_recording':{'status':'RECORDED' if recorded else 'UNPUBLISHED' if observation_id else 'UNKNOWN',
            **({'application_id':application['id']} if recorded else {}),
            **({'application_intent_id':intent_id,'source_observation_id':observation_id} if observation_id else {}),
            **({'allocated_application_id':application.get('application_tracking',{}).get('attempted_id')} if not recorded else {}),
            **({'reason':recording_error} if recording_error else {})},
        'application':{key:application[key] for key in ('id','complete','status','actor','application_tracking','warning') if key in application},
        'source_effect':effect,'complete':bool(application.get('complete')),'changed':bool(changes),
        'included_draft':body.get('included_draft'),'current_document_read':current_document_read(project),
        'applied_source_reads':applied_source_reads(project,body,root)}
    if not observation_id and not recorded:
        result.pop('recovery_action',None)
        result['recording_gap']='The allocated application identity is not a durable WA. Inspect actual source/effect receipts; replay is not permitted.'
    return result


def current_document_read(project):
    return {'operation':'document','payload':{},'http':{'method':'GET','url':'/authoring/document?'+urlencode({'project':project})}}


def applied_source_reads(project, body, root):
    from laplace.manuscript import manuscript_source
    source=manuscript_source.resolve(project,repo_root=root,include_candidates=False);result=[]
    for row in body['source_edits']:
        path=root/row['file']
        if not path.is_file():continue
        try:
            access=manuscript_source.source_access(project,path,root,source=source)
            result.append({'file':row['file'],'content_revision':pin(path.read_bytes()),
                **manuscript_source.source_handles(project,row['file'],pin(path.read_bytes()),access)})
        except manuscript_source.SourceAccessError:continue
    return result


def recover(project, payload, root, actor):
    from laplace.writing import records as writing_records
    from laplace.writing import records
    ref=payload['candidate_ref'];body=candidate(project,ref,root)['proposal']
    if payload.get('application_id'):
        row=records.selected_journal_fields(project,payload['application_id'],root,fields=['record','id','candidate_id','candidate_version','complete'])
        if row.get('record')!='writing-application' or row.get('candidate_id')!=ref['id'] or row.get('candidate_version')!=ref['version'] or not row.get('complete'):
            raise ValueError('Recover only the exact retained completed template application; source replay is refused.')
        return {**inspect(project,{'view':'template','candidate_ref':ref},root),'metadata_only':True,'complete':True,
            'application_recording':{'status':'RECORDED','application_id':row['id']}}
    intent_id=payload['application_intent_id']
    intent=records.selected_journal_fields(project,intent_id,root,fields=['record','decision','candidate_id','proposal_version','actor','preview_ref'])
    if (intent.get('record')!='writing-proposal-decision' or intent.get('decision')!='template-application-start'
            or intent.get('candidate_id')!=ref['id'] or intent.get('proposal_version')!=ref['version']):
        raise ValueError('The exact durable application intent belongs to a different candidate.')
    previous=next((item for item in reversed(_applications(project,ref,root)) if item.get('complete')),None)
    if previous:return {**inspect(project,{'view':'template','candidate_ref':ref},root),'metadata_only':True,'complete':True}
    observations=[item for item in records.index(root).by_candidate.get(ref['id'],[]) if item.get('decision')=='template-source-observation'
        and item.get('application_intent_id')==intent_id and item.get('proposal_version')==ref['version']]
    if len(observations)!=1:raise ValueError('The original source observation is unavailable or ambiguous; inspect source, do not replay it.')
    observed=records.selected_journal_fields(project,observations[0]['id'],root,fields=['source_effect','owned_changes','receipts','actor'])
    effect=copy.deepcopy(observed['source_effect'])
    if effect.get('state') not in {'COMMITTED','UNCHANGED'} or effect.get('selection_identity')!=body['selected_source']['selection_identity']:
        raise ValueError('The retained source fate is not a proved completed template effect.')
    expected={entry['file']:(entry['before_sha256'],entry['after_sha256']) for entry in body['source_edits'] if entry['before']!=entry['after']}
    actual={entry['path']:(entry['before_sha256'],entry['after_sha256']) for entry in effect['files']}
    if actual!=expected:raise ValueError('Retained source observation differs from the exact sealed candidate effect.')
    effect['follow_through']['required']=[entry for entry in effect['follow_through']['required'] if entry['owner']!='application-tracking']
    effect['complete']=True
    proposal=_application_proposal(body)
    row={'record':'writing-application','id':'WA-'+uuid.uuid4().hex,'project':project,'candidate_kind':'document-template',
        'candidate_id':ref['id'],'candidate_ref':ref,'candidate_version':ref['version'],'complete':True,
        'actor':intent['actor'],'recovery_actor':actor,'application_intent_id':intent_id,
        'source_observation_id':observations[0]['id'],'status':'RECOVERED_RECORDING','metadata_only':True,
        'edits':proposal['edits'],'source_effect':effect,'owned_changes':observed.get('owned_changes'),
        'receipts':observed.get('receipts') or [],'validation_basis':{'semantic_currentness':'NOT_ASSERTED','preview_ref':intent['preview_ref']},
        'document':body['selected_source'],'recording_qualification':'Original WA publication failed; this row records the exact retained earlier source observation. No source was replayed.'}
    writing_records.bank(root,row)
    return {**inspect(project,{'view':'template','candidate_ref':ref},root),'metadata_only':True,'complete':True,
        'application_recording':{'status':'RECORDED','application_id':row['id']},'source_effect':effect,
        'source_currentness':'HISTORICAL_RETAINED_EFFECT','included_draft':body.get('included_draft'),
        'current_document_read':current_document_read(project),'applied_source_reads':applied_source_reads(project,body,root)}


def native_projection(value):
    """Native discovery keeps one image/proof route; exact inspection yields Apply.

    The human metadata keeps its PDF and actions. Native image/output inspection
    returns the same unchanged Apply handle after verifying the selected proof;
    discovery does not repeat that large proof in three parallel handles.
    """
    def compact(item):
        if isinstance(item,list):return [compact(child) for child in item]
        if not isinstance(item,dict):return item
        if 'native_request' in item:
            return {key:compact(child) for key,child in item.items() if key not in {'http','payload'}}
        if 'operation' in item and 'payload' in item:
            return {key:compact(child) for key,child in item.items() if key!='http'}
        return {key:compact(child) for key,child in item.items()}
    result=compact(value)
    if 'source_changes' in result:
        result.pop('apply_action',None)
        result.pop('preview_pdf_read',None)
        if isinstance(result.get('build'),dict):
            result['build']={key:item for key,item in result['build'].items() if key!='preview_ref'}
        result['native_instruction']='Inspect preview_image_read for real PNG media and the exact owner-issued Apply handle; preview-output also inspects that same pinned proof. Human metadata retains its PDF/actions.'
    return result
