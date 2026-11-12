"""Local document originals in the artifact home; requests stay in Writing records.

No provider, host file selector or new store. The caller supplies bounded bytes.
Material membership is an independently guarded registry effect.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlencode
from filelock import FileLock
from laplace.projects import artifacts, library
from laplace.writing import records

MEDIA = {'application/pdf': 16_000_000, 'text/plain; charset=utf-8': 2_000_000}
RECORD = 'writing-material-intake'
PREFIX = '.artifacts/originals/'
REQUEST = re.compile(r'[A-Za-z0-9._:-]{8,96}')


class IntakeRefusal(ValueError):
    def __init__(self, code, message, *, status=422):
        super().__init__(message); self.code=code; self.http_status=status
    def body(self):
        value={'error':str(self),'code':self.code,'recovery':'Inspect the original project/request before another write; this refusal is not a terminal request settlement.'}
        if self.code in {'INTAKE_METADATA','INTAKE_NAME','INTAKE_SIZE','INTAKE_HASH','INTAKE_MEDIA','INTAKE_UTF8','INTAKE_CONTENT_TYPE','INTAKE_FRAMING','INTAKE_REQUEST'}:
            value['intake_admission']='NOT_ADMITTED_THIS_INVOCATION'
        else:value['effect']='INSPECT_REQUEST'
        return value


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def metadata_contract():
    return {'type':'object','additionalProperties':False,
        'required':['request_id','display_name','media_type','declared_size','expected_sha256','attach_material','expected_revision'],
        'properties':{'request_id':{'type':'string','pattern':r'^[A-Za-z0-9._:-]{8,96}$'},
            'display_name':{'type':'string','minLength':1,'maxLength':240},
            'media_type':{'enum':list(MEDIA)},'declared_size':{'type':'integer','minimum':1,'maximum':16_000_000},
            'expected_sha256':{'type':'string','pattern':r'^(sha256:)?[0-9a-f]{64}$'},
            'attach_material':{'type':'boolean'},'expected_revision':{'type':'string','minLength':1,'maxLength':160}}}


def _metadata(payload):
    from jsonschema import Draft202012Validator
    error=next(Draft202012Validator(metadata_contract()).iter_errors(payload),None)
    if error:raise IntakeRefusal('INTAKE_METADATA',error.message[:500])
    value=copy.deepcopy(payload);value['expected_sha256']=value['expected_sha256'].removeprefix('sha256:')
    if value['declared_size']>MEDIA[value['media_type']]:raise IntakeRefusal('INTAKE_SIZE','The selected media exceeds its byte limit.',status=413)
    if any(ord(c)<32 for c in value['display_name']):raise IntakeRefusal('INTAKE_NAME','Display name contains control characters.')
    return value


def _request(value):
    if not isinstance(value,str) or not REQUEST.fullmatch(value):raise IntakeRefusal('INTAKE_REQUEST','Retain one exact request_id of 8..96 safe characters.')
    return value


def _key(project,request_id):return 'MI-'+digest([project,_request(request_id)])


def read_handle(project,view='describe',request_id=None):
    payload={'view':'intake',**({'request_id':request_id} if request_id else {})}
    request={'view':view,**({'request_id':request_id} if request_id else {})}
    return {'project':project,'operation':'material_references','payload':payload,
        'http':{'method':'GET','url':'/projects/material-intake?'+urlencode({'project':project,'request':json.dumps(request,separators=(',',':'))})}}


def describe(root,project):
    artifacts._artifact_context(root,project)
    meta=library.metadata(project,root)
    return {'schema_version':'laplace.material-intake/1','project':project,'project_revision':meta['revision'],
        'limits':dict(MEDIA),'metadata':metadata_contract(),'read':read_handle(project),
        'actions':{'upload':{'permitted':True,'http':{'method':'POST','url':'/projects/material-intake/upload'},
            'query':{'project':project},'request_field':'request','headers':{'X-Laplace-Writing':'1'},
            'authority':'Human writing HTTP or explicitly trusted local SDK; not a native mutation.',
            'requires':metadata_contract()['required']},
            'status':{'permitted':True,'http':{'method':'GET','url':'/projects/material-intake?'+urlencode({'project':project})},
                'request_field':'request','payload':{'view':'status'},'requires':['request_id']}}}


def _row(root,project,ident):
    found=records.exact_record(project,ident,root)
    return found[0] if found else None


def _coverage(root):
    idx=records.index(root)
    return not idx.malformed_rows and (not idx.path.exists() or idx.offset==idx.path.stat().st_size)


def _known(root,project,request_id):
    key=_key(project,request_id);row=_row(root,project,key)
    if row is not None and (row.get('record')!=RECORD or row.get('request_id')!=request_id or row.get('intent_sha256')!=digest(row.get('intent'))):
        raise ValueError('Retained intake request custody is inconsistent.')
    if row is not None and row.get('destination') is not None:
        path,rel,ident=_file(root,project,row['intent'])
        destination={'path':path.relative_to(root).as_posix(),'artifact_path':rel,'artifact_id':ident,'scope':'project'}
        if row['destination']!=destination:raise ValueError('Retained original destination no longer matches the admitted project home; no home migration was performed.')
    return key,row


def _bank(root,project,key,state,**values):
    ident=key if state=='INTENT' else key+'-'+state.lower()
    existing=_row(root,project,ident)
    if existing is not None:return existing
    row={'record':RECORD,'id':ident,'project':project,'state':state,**values}
    records.bank(root,row);saved=_row(root,project,ident)
    if saved is None:raise OSError('Intake record publication could not be observed.')
    return saved


def _coordinates(project,intent):
    sha=intent['expected_sha256'];kind='pdf' if intent['media_type']=='application/pdf' else 'text'
    rel=PREFIX+kind+'/'+sha+('.pdf' if kind=='pdf' else '.txt')
    return rel,'ART-'+digest([project,intent['media_type'],sha])[:32]


def _file(root,project,intent):
    rel,ident=_coordinates(project,intent)
    return artifacts._artifact(root,project,rel),rel,ident


def _original(root,project,intent):
    path,rel,ident=_file(root,project,intent);target={'owner':'artifact','project':project,'path':rel,'scope':'project'}
    state='NOT_RETAINED';sha=None
    if path.is_file():
        if path.stat().st_size!=intent['declared_size']:state='UNAVAILABLE'
        else:
            with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
            state='RETAINED' if sha==intent['expected_sha256'] else 'UNAVAILABLE'
    art=_row(root,project,ident)
    if art and (art.get('record')!='writing-artifact' or art.get('artifact_path')!=rel or art.get('path')!=path.relative_to(root).as_posix() or art.get('sha256')!=intent['expected_sha256']):state='UNAVAILABLE'
    value={'state':state,'artifact_id':ident if art else None,'sha256':intent['expected_sha256'],
        'bytes':intent['declared_size'],'media_type':intent['media_type'],'display_name':intent['display_name'],
        'target':target,'read_only':True,'artifact_publication':'RECORDED' if art else 'NOT_OBSERVED'}
    if state=='RETAINED' and art:
        base={'id':ident,'expected_sha256':intent['expected_sha256']}
        value['material_read']=reading_context(root,project,ident,base)
        from laplace.research import literature
        value['literature']=literature.retained_capability(project,ident,intent['expected_sha256'],root)
        value.update(original_read=artifact_handle(project,base,route='original'),
            text_read=artifact_handle(project,base),
            page_image_read=artifact_handle(project,{**base,'view':'page','page':1}) if intent['media_type']=='application/pdf' else None)
    return value


def artifact_handle(project,payload,route='read'):
    params={'project':project}
    if route=='original':params.update(payload)
    else:params['request']=json.dumps(payload,separators=(',',':'))
    return {'project':project,**({'operation':'read_artifact','payload':copy.deepcopy(payload)} if route=='read' else {}),
        'http':{'method':'GET','url':'/projects/material-intake/'+route+'?'+urlencode(params)}}


def reading_context(root,project,artifact_id,payload=None,material_id=None):
    """Issue one exact explicit reading pointer, never original content or execution."""
    fields={} if payload is None else dict(payload)
    fields.pop('id',None)
    # The native door binds the scoped project into every payload; it is custody, not a read control.
    if 'project' in fields and fields.pop('project')!=project:
        raise ValueError('Material reading belongs to another project.')
    from laplace.writing.schemas import SCHEMAS
    from jsonschema import Draft202012Validator
    request={'id':artifact_id,**fields}
    error=next(Draft202012Validator(SCHEMAS['read_artifact']).iter_errors(request),None)
    if error:raise ValueError('Material reading payload must be an exact bounded artifact read.')
    for key,minimum,maximum in [('offset',0,1_000_000_000),('limit',1,40_000),('page',1,1_000_000),('page_count',1,4)]:
        if key in request and (type(request[key])!=int or not minimum<=request[key]<=maximum):raise ValueError('Material reading has invalid bounded controls.')
    identity=artifacts.identity(root,project,request)
    if identity['media_type']!='application/pdf' and any(key in request for key in ('page','page_count','view')):raise ValueError('PDF controls cannot select a text artifact.')
    value={'schema_version':'laplace.material-reading/1','project':project,'artifact_id':artifact_id,
        'sha256':identity['revision'],'read_payload':{**request,'expected_sha256':identity['revision']}}
    if material_id:value['material_id']=material_id
    return value


def validate_reading(root,project,value):
    if not isinstance(value,dict) or set(value)-{'schema_version','project','artifact_id','sha256','read_payload','material_id'} or not {'schema_version','project','artifact_id','sha256','read_payload'}<=set(value):
        raise ValueError('material_read must be the closed owner-issued reading pointer.')
    if value.get('schema_version')!='laplace.material-reading/1' or value.get('project')!=project or not isinstance(value.get('read_payload'),dict):raise ValueError('Material reading belongs to another project or schema.')
    payload=value['read_payload']
    if set(payload)-{'id','expected_sha256','offset','limit','page','page_count','view','pointer'} or payload.get('id')!=value['artifact_id'] or payload.get('expected_sha256')!=value['sha256']:
        raise ValueError('Material reading must retain the exact ART identity, raw source pin and read controls.')
    observed=reading_context(root,project,value['artifact_id'],payload,value.get('material_id'))
    if observed!=value:raise ValueError('Material reading source identity changed; inspect before selecting it again.')
    if value.get('material_id'):
        from laplace.pipeline import registry
        record=registry.resolve(project,root)
        binding=next((x for x in record.manifest.get('material_references',[]) if x.get('id')==value['material_id']),None)
        art=artifacts.identity(root,project,{'id':value['artifact_id']})
        if not binding or binding.get('target')!={'owner':'artifact','project':project,'path':art['artifact_path'],'scope':art['scope']}:
            raise ValueError('The selected Material membership is no longer present in this project.')
    return copy.deepcopy(value)


def _membership(root,project,target):
    from laplace.pipeline import registry
    proj=registry.resolve(project,root)
    if proj is None:raise ValueError('The selected project is unavailable.')
    return next((copy.deepcopy(x) for x in proj.manifest.get('material_references',[]) if x.get('target')==target),None)


def status(root,project,request_id):
    artifacts._artifact_context(root,project);key=_key(project,request_id)
    result={'schema_version':'laplace.material-intake-result/1','project':project,'request_id':request_id,
        'state':'NONE','read':read_handle(project,'status',request_id),'actions':{'status':read_handle(project,'status',request_id)},
        'meaning':'NONE is a captured lookup, not terminal non-admission. Retain the original metadata and bytes; explicit exact retry only.'}
    try:
        key,row=_known(root,project,request_id)
        if not row:
            idx=records.index(root)
            if idx.malformed_rows or idx.path.exists() and idx.offset!=idx.path.stat().st_size:
                result.update(state='UNKNOWN',meaning='Request custody has incomplete coverage; retain original intent.')
            return result
        intent=row['intent'];complete=_row(root,project,key+'-complete')
        if not complete and not _coverage(root):
            result.update(state='UNKNOWN',meaning='Incomplete request-stage coverage; retain original intent and inspect.')
            return result
        original=_original(root,project,intent)
        target=original['target'];present=_membership(root,project,target)
        membership={'state':'NOT_REQUESTED' if not intent['attach_material'] else 'PENDING',
            'reference':None,'current_present':bool(present),'attribution':'NONE'}
        if complete:
            membership=copy.deepcopy(complete['membership']);membership['current_present']=bool(present)
            if membership.get('reference') and (not present or present['id']!=membership['reference']['id']):membership['state']='REMOVED'
        elif present and intent['attach_material']:
            membership.update(state='OBSERVED',reference=present,attribution='OBSERVED_STANDING')
        result.update(state='RECORDED' if complete and original['state']=='RETAINED' and original['artifact_publication']=='RECORDED' else 'PARTIAL',
            intent_sha256=row['intent_sha256'],intent=copy.deepcopy(intent),original=original,membership=membership,
            meaning='Original custody and registry membership are separate; replay never restores removed membership.')
        if original['state']!='RETAINED':
            result['actions']['retry_upload']={'permitted':original['state']!='UNAVAILABLE','http':{'method':'POST','url':'/projects/material-intake/upload'},
                'query':{'project':project},'request_field':'request','metadata':copy.deepcopy(intent),'requires':['same_original_bytes'],
                'reason':'Reselect exact bytes if needed; no automatic retry.'}
        elif original['artifact_publication']!='RECORDED' or intent['attach_material'] and not complete:
            result['actions']['link']={'permitted':True,'http':{'method':'POST','url':'/projects/material-intake/link'},
                'payload':{'project':project,'request_id':request_id},'requires':['expected_revision'],
                'inspect_destination':read_handle(project),'meaning':'Recover retained original receipt and, only if originally requested, link Material.'}
        return result
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result.update(state='UNKNOWN',meaning='The retained request could not be fully inspected. Keep its original intent.',diagnostic=str(exc)[:500])
        return result


def _publish_retained_receipt(root,project,intent):
    """Recover only the exact already-retained original; no browser bytes are needed."""
    original=_original(root,project,intent)
    if original['state']!='RETAINED':raise IntakeRefusal('INTAKE_ORIGINAL_UNAVAILABLE','Exact original bytes are not currently retained.')
    path,rel,ident=_file(root,project,intent)
    with FileLock(str(path)+'.lock'):
        if _row(root,project,ident) is None:
            records.bank(root,{'record':'writing-artifact','id':ident,'project':project,'path':path.relative_to(root).as_posix(),
                'artifact_path':rel,'scope':'project','sha256':intent['expected_sha256'],'before':None,'before_sha256':None,
                'original_metadata':{'schema_version':'laplace.artifact-original/1','media_type':intent['media_type'],
                    'bytes':intent['declared_size'],'display_name':intent['display_name'],'immutable':True},'reason':'Retained immutable local document original'})


def _complete_link(root,project,key,row,expected_revision):
    intent=row['intent'];original=_original(root,project,intent)
    if original['state']!='RETAINED' or original['artifact_publication']!='RECORDED':raise IntakeRefusal('INTAKE_ORIGINAL_UNAVAILABLE','Retain/inspect the original before linking it.')
    if _row(root,project,key+'-complete'):return status(root,project,intent['request_id'])
    if not intent['attach_material']:
        _bank(root,project,key,'COMPLETE',request_id=intent['request_id'],membership={'state':'NOT_REQUESTED','reference':None,'attribution':'NONE'})
        return status(root,project,intent['request_id'])
    # This write-ahead phase prevents upload replay from repeating an uncertain registry effect.
    _bank(root,project,key,'LINK_ATTEMPT',request_id=intent['request_id'])
    if library.metadata(project,root)['revision']!=expected_revision:raise IntakeRefusal('INTAKE_PROJECT_CHANGED','Inspect the current destination before explicit linking.',status=409)
    target=original['target'];present=_membership(root,project,target)
    if present:
        membership={'state':'OBSERVED','reference':present,'attribution':'OBSERVED_STANDING'}
    else:
        changed=library.change_material_reference(project,{'action':'attach','expected_revision':expected_revision,
            'target':target,'consumed_revision':intent['expected_sha256'],'by':'author','reason':'Explicit local document intake'},root)
        membership={'state':'LINKED','reference':changed['reference'],'attribution':'COMMITTED','receipt':changed}
    _bank(root,project,key,'COMPLETE',request_id=intent['request_id'],membership=membership)
    return status(root,project,intent['request_id'])


def _check_bytes(intent,raw):
    if not isinstance(raw,bytes) or len(raw)!=intent['declared_size'] or len(raw)>MEDIA[intent['media_type']]:raise IntakeRefusal('INTAKE_SIZE','Actual bytes differ from the admitted size.',status=413)
    if hashlib.sha256(raw).hexdigest()!=intent['expected_sha256']:raise IntakeRefusal('INTAKE_HASH','The selected bytes do not match the original request.')
    pdf=bool(re.match(rb'%PDF-[0-9]\.[0-9]',raw[:8]))
    if intent['media_type']=='application/pdf':
        if not pdf:raise IntakeRefusal('INTAKE_MEDIA','The PDF header does not match the chosen media.')
    else:
        try:raw.decode('utf-8')
        except UnicodeDecodeError as exc:raise IntakeRefusal('INTAKE_UTF8','The document is not valid UTF-8.') from exc
        if pdf:raise IntakeRefusal('INTAKE_MEDIA','PDF bytes require PDF media, not text.')


def upload(root,project,metadata,raw):
    root=Path(root).resolve();intent=_metadata(metadata);_check_bytes(intent,raw)
    from laplace.work import project_work
    with project_work.dispatch_lock(root):
        artifacts._artifact_context(root,project);key,row=_known(root,project,intent['request_id'])
        if row and row['intent_sha256']!=digest(intent):raise IntakeRefusal('INTAKE_REQUEST_CONFLICT','The request_id already names another exact intake intent.',status=409)
        if row:
            observed=status(root,project,intent['request_id'])
            if observed['state']=='UNKNOWN':raise IntakeRefusal('INTAKE_CUSTODY_UNKNOWN','Retained request custody is unavailable.',status=409)
            if observed.get('original',{}).get('state')=='UNAVAILABLE':raise IntakeRefusal('INTAKE_ORIGINAL_CONFLICT','The retained original is unavailable at its admitted coordinates; no overwrite or home migration.',status=409)
            if observed.get('original',{}).get('state')=='RETAINED' and observed['original']['artifact_publication']=='RECORDED':
                return {**observed,'replayed':True}
        else:
            if not _coverage(root):raise IntakeRefusal('INTAKE_CUSTODY_UNKNOWN','The request index has incomplete coverage; no new admission.',status=409)
            library.metadata(project,root)  # The project must still have registered, admitted metadata/home.
            path,rel,ident=_file(root,project,intent)
            destination={'path':path.relative_to(root).as_posix(),'artifact_path':rel,'artifact_id':ident,'scope':'project'}
            # Metadata revision guards membership, not independent immutable original retention.
            row=_bank(root,project,key,'INTENT',request_id=intent['request_id'],intent=intent,intent_sha256=digest(intent),destination=destination)
        path,rel,ident=_file(root,project,intent);path.parent.mkdir(parents=True,exist_ok=True)
        with FileLock(str(path)+'.lock'):
            if path.exists():
                if not path.is_file() or path.read_bytes()!=raw:raise IntakeRefusal('INTAKE_ORIGINAL_CONFLICT','The immutable original path contains different bytes.',status=409)
            else:
                tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
                try:
                    tmp.write_bytes(raw)
                    # Hardlink publication refuses replacement even by another process.
                    import os
                    os.link(tmp,path)
                finally:tmp.unlink(missing_ok=True)
            art=_row(root,project,ident)
            if art is None:
                records.bank(root,{'record':'writing-artifact','id':ident,'project':project,'path':path.relative_to(root).as_posix(),
                    'artifact_path':rel,'scope':'project','sha256':intent['expected_sha256'],'before':None,'before_sha256':None,
                    'original_metadata':{'schema_version':'laplace.artifact-original/1','media_type':intent['media_type'],
                        'bytes':len(raw),'display_name':intent['display_name'],'immutable':True},'reason':'Retained immutable local document original'})
            elif art.get('sha256')!=intent['expected_sha256'] or art.get('artifact_path')!=rel:raise IntakeRefusal('INTAKE_ARTIFACT_CONFLICT','Artifact identity custody disagrees with this original.',status=409)
        _bank(root,project,key,'RETAINED',request_id=intent['request_id'])
        if _row(root,project,key+'-link_attempt') or _row(root,project,key+'-complete'):return status(root,project,intent['request_id'])
        try:return _complete_link(root,project,key,row,intent['expected_revision'])
        except (OSError,ValueError) as exc:return {**status(root,project,intent['request_id']),'link_diagnostic':str(exc)[:500]}


def link(root,project,payload):
    if not isinstance(payload,dict) or set(payload)!={'request_id','expected_revision'} or not isinstance(payload['expected_revision'],str):raise IntakeRefusal('INTAKE_LINK_METADATA','Link requires original request_id and freshly inspected expected_revision.')
    from laplace.work import project_work
    with project_work.dispatch_lock(root):
        key,row=_known(root,project,payload['request_id'])
        if row is None:raise IntakeRefusal('INTAKE_REQUEST_UNKNOWN','Inspect the retained original request first.')
        _publish_retained_receipt(root,project,row['intent'])
        return _complete_link(root,project,key,row,payload['expected_revision'])


def read_upload_body(headers,stream):
    """Only the scanner's exact raw-upload branch consumes this framed bounded body."""
    lengths=headers.get_all('Content-Length') if hasattr(headers,'get_all') else [headers.get('Content-Length')]
    length=lengths[0] if lengths and len(lengths)==1 else None
    if headers.get('Transfer-Encoding') or not isinstance(length,str) or not re.fullmatch(r'[0-9]{1,9}',length):raise IntakeRefusal('INTAKE_FRAMING','One finite nonnegative Content-Length and no transfer encoding are required.',status=400)
    length=int(length)
    if length>16_000_000:raise IntakeRefusal('INTAKE_SIZE','Upload exceeds the 16000000 byte ceiling.',status=413)
    raw=stream.read(length)
    if len(raw)!=length:raise IntakeRefusal('INTAKE_FRAMING','The upload ended before Content-Length bytes arrived.',status=400)
    return raw


def read(root,project,payload):
    """Intake HTTP reading projection; legacy native artifact responses are unchanged."""
    observed=artifacts.read(root,project,payload)
    if observed.get('media_type')=='application/pdf':return observed
    identity={'id':payload['id']} if 'id' in payload else {'path':observed['artifact_path'],'scope':observed['scope']}
    controls={**identity,**({'pointer':payload['pointer']} if 'pointer' in payload else {}),
        'limit':payload.get('limit',6000 if 'pointer' in payload else 16000)}
    pin=observed.get('revision')
    if not observed.get('exists') or not pin:return observed
    exact={**controls,'expected_sha256':pin}
    return {**observed,
        'page_read':artifact_handle(project,{**exact,'offset':observed['offset']}),
        'read_handle':artifact_handle(project,{**exact,'offset':observed['next_offset']}) if observed.get('next_offset') is not None else None,
        'restart_read':artifact_handle(project,{**controls,'offset':0}),
        'restart_read_semantics':'Explicit CURRENT source from offset0; no inherited source pin or automatic adoption.'}


def http(path,query,method,body,root):
    if path not in {'/projects/material-intake','/projects/material-intake/upload','/projects/material-intake/link','/projects/material-intake/read','/projects/material-intake/original'}:return None
    try:
        allowed={'project','id','expected_sha256'} if path.endswith('/original') else {'project','request'}
        if set(query)-allowed or any(isinstance(value,(list,tuple)) and len(value)!=1 for value in query.values()):
            raise IntakeRefusal('INTAKE_METADATA','Use one exact value per admitted query field.')
        project=library._q1(query,'project')
        raw_request=library._q1(query,'request')
        if len(raw_request.encode())>8192:raise IntakeRefusal('INTAKE_METADATA','Request metadata exceeds8192bytes.')
        request=json.loads(raw_request) if raw_request else {}
        if path.endswith('/upload'):
            if method!='POST':return library._response(405,{'error':'POST only'})
            return library._response(200,upload(root,project,request,body))
        if path.endswith('/link'):
            if method!='POST':return library._response(405,{'error':'POST only'})
            posted=json.loads(body or b'{}');project=posted.pop('project','')
            return library._response(200,link(root,project,posted))
        if method!='GET':return library._response(405,{'error':'GET only'})
        if path.endswith('/read'):
            from jsonschema import Draft202012Validator
            from laplace.writing.schemas import SCHEMAS
            error=next(Draft202012Validator(SCHEMAS['read_artifact']).iter_errors(request),None)
            if error:raise IntakeRefusal('INTAKE_READ','Read must match the closed artifact read contract.')
            return library._response(200,read(root,project,request))
        if path.endswith('/original'):
            payload={'id':library._q1(query,'id'),'expected_sha256':library._q1(query,'expected_sha256')}
            file,_,_,record=artifacts._artifact_target(root,project,payload)
            if not record or not record.get('original_metadata'):raise IntakeRefusal('INTAKE_NOT_ORIGINAL','Choose an exact retained original.')
            from laplace.core import source_pin
            maximum=MEDIA[record['original_metadata']['media_type']]
            with file.open('rb') as stream:raw=stream.read(maximum+1)
            if len(raw)>maximum:raise IntakeRefusal('INTAKE_SIZE','Original retrieval exceeds its admitted media cap.',status=413)
            source_pin.check(hashlib.sha256(raw).hexdigest(),{'expected_sha256':record['sha256']})
            source_pin.check(hashlib.sha256(raw).hexdigest(),payload)
            return 200,record['original_metadata']['media_type'],raw
        if request.get('view','describe')=='describe' and not request:return library._response(200,describe(root,project))
        if request=={'view':'describe'}:return library._response(200,describe(root,project))
        if set(request)=={'view','request_id'} and request['view']=='status':return library._response(200,status(root,project,request['request_id']))
        raise IntakeRefusal('INTAKE_READ','Choose the exact describe or request status read.')
    except IntakeRefusal as exc:return library._response(exc.http_status,exc.body())
    except (OSError,ValueError,KeyError,TypeError) as exc:
        from laplace.core import source_pin
        if isinstance(exc,source_pin.SourcePinRefusal):return library._response(409,{'error':str(exc),'code':'CHANGED_INPUT'})
        return library._response(422,{'error':str(exc)[:500],'code':'INTAKE_UNAVAILABLE','effect':'UNKNOWN'})
