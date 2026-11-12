"""Source-bound, same-request passage comments over canonical feedback custody.

The feedback ledger owns the comment text; authoring projects its original AC
alias. This leaf owns no store, provider effect, Work route or retry loop.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from collections.abc import Mapping

from laplace.core.identity import canonical_digest, bytes_digest

BASIS='laplace.passage-comment-basis/1'
ORIGIN='laplace.feedback-origin/1'
CUSTODY='laplace.feedback-origin-custody/1'
SETTLEMENT='laplace.feedback-origin-settlement/1'
SETTLEMENT_RECORD='feedback-origin-settlement'
SELECTION='laplace.comment-source-selection/1'
ASSOCIATION='laplace.feedback-request-association/1'
COMPARISON='laplace.feedback-request-comparison/1'
_BASIS_FIELDS={'schema_version','project','file','selection_identity','source_sha256',
               'line_start','line_end','source_ref','source_quote','ledger'}
_REF_FIELDS={'schema_version','project','correction_id','feedback_id','material_revision','ledger'}
_SAVE_FIELDS={'project','request_id','source_basis','base_revision','text','kind','scope','anchor',
              'by','review_route'}


def contracts():
    text={'type':'string','minLength':1};pin={'type':'string','pattern':r'^sha256:[0-9a-f]{64}$'}
    def obj(required,properties):
        return {'type':'object','required':sorted(required),'properties':properties,'additionalProperties':False}
    # A rendered reader selection names its exact raw target in the inspected extent; the displayed text is an
    # observation only. Offsets are Unicode code points of the extent text, the tokenizer's own units.
    selection=obj(('schema','kind','units','start','end'),{'schema':{'const':SELECTION},
        'kind':{'enum':['whole-block','piece-span']},'units':{'const':'unicode-codepoints'},
        'start':{'type':'integer','minimum':0},'end':{'type':'integer','minimum':1},
        'display_quote':{'type':'string','maxLength':10000}})
    anchor=obj(('file','line_start','line_end'),{'file':text,
        'line_start':{'type':'integer','minimum':1},'line_end':{'type':'integer','minimum':1},
        **{key:{'type':'string'} for key in ('quote','section','section_id','node_id','block')},
        'source_selection':selection})
    basis=obj(_BASIS_FIELDS,{'schema_version':{'const':BASIS},'project':text,'file':text,
        'selection_identity':pin,'source_sha256':{'type':'string','pattern':r'^[0-9a-f]{64}$'},
        'line_start':{'type':'integer','minimum':1},'line_end':{'type':'integer','minimum':1},
        'source_ref':text,'source_quote':{'type':'string'},'ledger':text})
    ref=obj(_REF_FIELDS,{'schema_version':{'const':ORIGIN},'project':text,'correction_id':text,
        'feedback_id':text,'material_revision':pin,'ledger':text})
    save=obj(('project','request_id','source_basis','base_revision','text','kind','scope','anchor'),{
        'project':text,'request_id':{'type':'string','pattern':r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$'},
        'source_basis':basis,'base_revision':{'type':'integer','minimum':0},'text':text,
        'kind':{'enum':sorted(_owner()._CORRECTION_KINDS)},'scope':{'const':'passage'},'anchor':anchor,
        'by':text,'review_route':{'type':'object'}})
    prepare=obj(('project',),{'project':text,'anchor':anchor,
        'request_id':save['properties']['request_id'],
        'expected':{'type':'array','minItems':1,'items':text},'selection_identity':pin,
        'source_sha256':basis['properties']['source_sha256'],'source_basis':basis,
        'base_revision':{'type':'integer','minimum':0}})
    prepare['anyOf']=[{'required':['source_basis']},{'required':['anchor','expected']}]
    settle=obj(('project','submission'),{'project':text,'submission':save,
        'request_id':save['properties']['request_id'],'ledger':text})
    return {'prepare':prepare,'save':save,'origin':ref,'settle':settle,
        'request':obj(('project','request_id','ledger'),{'project':text,'request_id':save['properties']['request_id'],'ledger':text,
            'submission':{'type':'string','minLength':2,
                'description':'Optional exact retained ORIGINAL Save JSON; the owner compares its canonical intent only.'}})}


def _owner():
    from laplace.pipeline import authoring
    return authoring


def _closed(payload,schema):
    from jsonschema import Draft202012Validator
    error=next(Draft202012Validator(schema).iter_errors(payload),None)
    if error is not None:
        coordinate='.'.join(str(key) for key in error.absolute_path)
        raise ValueError('Comment request does not match the closed origin contract'+(' at '+coordinate if coordinate else '')+'.')


def _request(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}',value):
        raise ValueError('Comment request_id must be a bounded stable request identity.')
    return value


def _target(anchor,basis):
    """The exact raw source target of a typed reader selection, revalidated against this inspected extent.

    Whole block: the complete extent. Piece span: boundaries on the tokenizer's own piece offsets, never inside a
    math, citation, macro or group piece and never across source that is not displayed. No TeX is stripped or
    inverted; the displayed quote stays an observation and is never authority."""
    selection=anchor.get('source_selection')
    if selection is None:return None
    raw=basis['source_quote']
    if (not isinstance(selection,Mapping) or selection.get('schema')!=SELECTION
            or selection.get('units')!='unicode-codepoints' or set(selection)-{'schema','kind','units','start','end','display_quote'}):
        raise ValueError('Comment source selection is not an owner-supported carrier.')
    lo,hi=selection.get('start'),selection.get('end')
    if type(lo)!=int or type(hi)!=int or not 0<=lo<hi<=len(raw):
        raise ValueError('Comment source selection lies outside the inspected source extent; retain the draft and choose the passage again.')
    if selection.get('kind')=='whole-block':
        if (lo,hi)!=(0,len(raw)):raise ValueError('A whole-paragraph comment must name the complete inspected source extent.')
    elif selection.get('kind')=='piece-span':
        from laplace.manuscript import walk
        covered=sorted((piece['o_start'],piece['o_end'],piece.get('t')) for piece in walk.tex_pieces(raw)
                       if piece['o_end']>lo and piece['o_start']<hi)
        if not covered:raise ValueError('Comment selection names no displayed source; choose the whole paragraph explicitly.')
        position=lo
        for start,end,kind in covered:
            if kind!='text' and (start<lo or end>hi):
                raise ValueError('Comment selection starts or ends inside a math, citation or macro piece; choose the whole piece or paragraph explicitly.')
            if start>position:
                raise ValueError('Comment selection spans source that is not displayed; choose the whole paragraph explicitly.')
            position=max(position,end)
        if position<hi or (lo>0 and raw[lo-1]=='\\') or raw[hi-1]=='\\':
            raise ValueError('Comment selection boundary is not a deterministic source position; choose the whole paragraph explicitly.')
    else:raise ValueError('Comment source selection kind is unsupported.')
    target=raw[lo:hi]
    if 'quote' in anchor and anchor['quote']!=target:
        raise ValueError('Comment quote differs from its qualified source target; retain the draft and compare explicitly.')
    return target


def _quote(anchor,basis):
    if 'source_selection' in anchor:
        _target(anchor,basis);return
    if 'quote' in anchor:
        quote=anchor['quote']
        if isinstance(quote,str) and quote.strip() and quote in basis['source_quote']:return
        from laplace.manuscript import walk
        # Reuse the inspected prose owner's controlled TeX pieces and spacing;
        # never infer a semantic paraphrase or search outside this exact extent.
        visible=walk._flatten_pieces(walk.tex_pieces(basis['source_quote']))
        normalize=lambda text:re.sub(r'\s+',' ',walk._text_norm(text)).strip()
        if not isinstance(quote,str) or not quote.strip() or normalize(quote) not in normalize(visible):
            raise ValueError('Displayed quote is not an exact selection inside the inspected source extent; retain the draft and compare explicitly.')


def _settle_action(project,ledger,request_id=None):
    return {'http':{'method':'POST','url':'/authoring/correction-settle',
        'body':{'project':project,'ledger':ledger,**({'request_id':request_id} if request_id else {})}},
        'requires':['submission'],'meaning':'Settle the original exact Save; preserve any already saved comment.'}


def _request_read(project,ledger,request_id):
    from urllib.parse import urlencode
    return {'http':{'method':'GET','url':'/authoring/correction-request?'+urlencode(
        {'project':project,'request_id':request_id,'ledger':ledger})}}


def _compare(project,ledger,request_id):
    """Owner-issued pure comparison template: a client fills only `field` with its retained original wire."""
    return {'schema_version':COMPARISON,'kind':'origin','project':project,'context':ledger,'request_id':request_id,
            'requires':['submission'],'carrier':'query-json','field':'submission','read':_request_read(project,ledger,request_id),
            'meaning':'Pure read: compares the original Save intent in the owner domain; it saves, settles and retries nothing.'}


def _ledger(root,project,value):
    """A retained locator is not authority outside this registered project.

    Ownership is the registry's most specific resolved content home (registry.content_owners, through
    Project.path, so an external-rooted website's "." home names its sibling clone, never this checkout).
    A nested registered home owns its own subtree, equal homes are ambiguous, and no component below the
    checkout may be a symbolic link that could carry custody into another home.
    """
    from laplace.pipeline import registry
    if not isinstance(value,str) or not value or Path(value).is_absolute() or '..' in Path(value).parts:
        raise ValueError('Comment ledger must be an owner-issued project-relative locator.')
    base=Path(root).resolve();parts=Path(value).parts
    if len(parts)<2 or parts[-1]!='feedback.jsonl' or parts[-2]!='feedback':
        raise ValueError('Comment ledger locator is outside canonical feedback custody.')
    current=base
    for part in parts:
        current=current/part
        if current.is_symlink():raise ValueError('Comment feedback custody cannot traverse a symbolic link.')
    path=current.resolve()
    if not path.is_relative_to(base):
        raise ValueError('Comment ledger locator is outside canonical feedback custody.')
    if registry.resolve(project,repo_root=base) is None:raise ValueError('Comment project is not registered.')
    owners=registry.content_owners(path,base)
    if project not in owners:
        raise ValueError('Comment ledger is claimed by another registered project.' if owners
                         else 'Comment ledger does not belong to this project.')
    if len(owners)>1:raise ValueError('Comment ledger is claimed by another registered project.')
    return path


def canonical_ledger(root,project):
    """The existing registered feedback home, independent of selected edition."""
    from laplace.pipeline import registry
    value=registry.comment_feedback_home(project,root)
    _ledger(root,project,value)
    return value


def _basis(project,value):
    if not isinstance(value,dict) or set(value)!=_BASIS_FIELDS or value.get('schema_version')!=BASIS:
        raise ValueError('A complete owner-issued passage comment basis is required.')
    if value['project']!=project:raise ValueError('Comment source basis belongs to another project.')
    if any(not isinstance(value[key],str) or not value[key] for key in
           ('file','selection_identity','source_sha256','source_ref','ledger')):
        raise ValueError('Comment source basis identities are malformed.')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',value['selection_identity']) or not re.fullmatch(
            r'[0-9a-f]{64}',value['source_sha256']):
        raise ValueError('Comment source basis requires exact selection and raw-source hashes.')
    if (type(value['line_start'])!=int or type(value['line_end'])!=int
            or not 1<=value['line_start']<=value['line_end'] or not isinstance(value['source_quote'],str)):
        raise ValueError('Comment source extent is malformed.')
    return copy.deepcopy(value)


def _selected(root,project,file):
    from laplace.manuscript import manuscript_source as source_owner
    source=_owner()._source(project,root)
    if not source.get('root') or source.get('status') not in {'resolved','empty'}:
        raise ValueError('Choose a current manuscript source before preparing a passage comment.')
    md=(root/str(source.get('manuscript_dir') or '')).resolve()
    path=source_owner.source_path(root,md,file)
    if not path.is_relative_to(root):raise ValueError('Comment source is outside this project checkout.')
    return source,path


def _observe(root,project,payload,source,path):
    from laplace.manuscript import manuscript_source as source_owner, source_anchor
    from laplace.core import identity_doors
    anchor=payload.get('anchor')
    if not isinstance(anchor,Mapping):raise ValueError('A passage anchor is required.')
    lo,hi=anchor.get('line_start'),anchor.get('line_end')
    if type(lo)!=int or type(hi)!=int:raise ValueError('Select an exact inclusive source line extent.')
    tree=source_owner.traversal(root/source['root'],root)
    source_owner.source_access(project,path,root,source=source,source_tree=tree)
    if path.relative_to(root).as_posix() not in tree['files']:
        raise ValueError('Passage comments require selected manuscript source, not a dependency.')
    raw=path.read_bytes();text=raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n');lines=text.split('\n')
    if not 1<=lo<=hi<=len(lines):raise ValueError('Comment extent is outside the inspected source.')
    quote='\n'.join(lines[lo-1:hi]);selection=source_owner.selection_identity(source,project)
    if payload.get('selection_identity',selection)!=selection:
        raise ValueError('Selected manuscript changed; retain the comment draft and inspect explicitly.')
    sha=bytes_digest(raw).removeprefix('sha256:')
    if payload.get('source_sha256',sha)!=sha:
        raise ValueError('Raw source changed; retain the comment draft and inspect explicitly.')
    identity_doors.expected_tokens(payload.get('expected'))
    identity_doors.gate('comment@paragraph',supplied={'expected':payload['expected']},
        homes=[('prose',f"{project}::{path.relative_to(root/source['manuscript_dir']).as_posix()}:{lo}-{hi}",quote.encode())],
        said='The passage is no longer the source you inspected; retain your comment draft.')
    ledger=canonical_ledger(root,project)
    try:locator=source_anchor.anchor(lines,lo,hi)
    except source_anchor.AnchorError as exc:raise ValueError(str(exc)) from None
    return {'schema_version':BASIS,'project':project,'file':path.relative_to(root).as_posix(),
        'selection_identity':selection,'source_sha256':sha,'line_start':lo,'line_end':hi,
        'source_ref':path.relative_to(root).as_posix()+':'+locator,'source_quote':quote,'ledger':ledger}


def _current(root,project,basis,source=None,path=None):
    from laplace.manuscript import manuscript_source as source_owner, source_anchor
    basis=_basis(project,basis)
    source,path=(source,path) if source is not None else _selected(root,project,basis['file'])
    if source_owner.selection_identity(source,project)!=basis['selection_identity']:
        raise ValueError('Selected manuscript changed; retain the original comment draft.')
    tree=source_owner.traversal(root/source['root'],root)
    source_owner.source_access(project,path,root,source=source,source_tree=tree)
    if path.relative_to(root).as_posix() not in tree['files'] or path.relative_to(root).as_posix()!=basis['file']:
        raise ValueError('The original passage is not current selected source.')
    raw=path.read_bytes()
    if bytes_digest(raw).removeprefix('sha256:')!=basis['source_sha256']:
        raise ValueError('Raw source changed; retain the original comment draft and compare explicitly.')
    lines=raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n').split('\n')
    try:
        file,locator=source_anchor.parse_ref(basis['source_ref'])
        if file!=basis['file']:raise ValueError('Comment anchor names another source file.')
        lo,hi=source_anchor.locate(lines,locator)
    except source_anchor.AnchorError as exc:raise ValueError(str(exc)) from None
    if (lo,hi)!=(basis['line_start'],basis['line_end']) or '\n'.join(lines[lo-1:hi])!=basis['source_quote']:
        raise ValueError('Original passage extent changed; no automatic reanchoring was performed.')
    if canonical_ledger(root,project)!=basis['ledger']:
        raise ValueError('The current feedback home differs from the retained origin home.')
    return source


def prepare(project,payload,repo_root=None):
    from laplace.manuscript import manuscript_source as source_owner
    root=_owner()._root(repo_root)
    _closed({**dict(payload),'project':project} if isinstance(payload,Mapping) else payload,contracts()['prepare'])
    allowed={'project','anchor','expected','selection_identity','source_sha256','source_basis','base_revision','request_id'}
    if not isinstance(payload,Mapping) or set(payload)-allowed or payload.get('project',project)!=project:
        raise ValueError('Comment preparation accepts only its exact project, anchor and inspected guards.')
    anchor=payload.get('anchor') or {}
    with source_owner.selection_mutation(project,root):
        source,path=_selected(root,project,(payload.get('source_basis') or {}).get('file') or anchor.get('file'))
        with source_owner.source_mutation([root/source['root'],path]):
            if 'source_basis' in payload:
                basis=_basis(project,payload['source_basis']);_current(root,project,basis,source,path)
                if any(key in anchor and anchor[key]!=basis[key] for key in ('file','line_start','line_end')):
                    raise ValueError('Retained comment anchor differs from its original source basis; no reanchoring was performed.')
            else:basis=_observe(root,project,payload,source,path)
            _quote(anchor,basis);target=_target(anchor,basis)
            state_path,_=_owner()._state_path(project,root,_observed_source=source)
            with _owner()._locked(state_path):state=_owner()._read(state_path,project,root,contexts=False)
    revision=payload.get('base_revision',state['revision'])
    if type(revision)!=int or revision<0:raise ValueError('Original authoring base_revision must be a nonnegative integer.')
    prepared_anchor={**dict(anchor),'file':basis['file'],'line_start':basis['line_start'],'line_end':basis['line_end'],
        **({'quote':target} if target is not None else {})}
    lookup={'method':'GET','route':'/authoring/correction-request','query':{'project':project,'ledger':basis['ledger']}}
    if 'request_id' in payload:lookup['query']['request_id']=_request(payload['request_id'])
    return {'project':project,'source_basis':basis,'base_revision':revision,'anchor':prepared_anchor,
        'meaning':'This comment applies as an ordinary author instruction to its passage.',
        'instruction_eligible':True,'save':{'http':{'method':'POST','url':'/authoring/correction'}},
        'reconcile':{'http':lookup,'requires':[] if 'request_id' in payload else ['request_id']},
        'settle':_settle_action(project,basis['ledger'],payload.get('request_id'))}


def _rows(path):
    from laplace.pipeline.ledger import read_jsonl_diagnosed
    rows,diagnostics=read_jsonl_diagnosed(path)
    if diagnostics:raise ValueError('Canonical comment feedback custody is incomplete or unreadable.')
    return rows


def _material(row):
    origin=row['authoring_origin']
    anchor={key:value for key,value in row['anchor'].items() if key not in
        {'authoring_scope','correction_kind','context_role','correction_id'}}
    return {'project':row['project'],'text':row['comment'],'kind':origin['kind'],'scope':origin['scope'],
        'anchor':anchor,'by':row['by'],'source_basis':origin['source_basis']}


def projection(row):
    origin=row.get('authoring_origin')
    if not isinstance(origin,dict) or origin.get('schema_version')!=CUSTODY:
        raise ValueError('Canonical comment origin metadata is unavailable or unsupported.')
    required={'schema_version','request_id','intent_sha256','correction_id','created','kind','scope',
              'context_role','base_revision','authoring_revision','source_basis','material_revision'}
    if not required.issubset(origin) or set(origin)-required-{'review_route'} or not isinstance(row.get('anchor'),dict):
        raise ValueError('Canonical comment origin metadata is incomplete.')
    _basis(row['project'],origin['source_basis'])
    if canonical_digest(_material(row))!=origin.get('material_revision'):
        raise ValueError('Canonical comment material no longer matches its retained origin.')
    value=_material(row)
    return {**value,'id':origin['correction_id'],'feedback_id':row['id'],'origin_ref':_ref(row),
        'request_id':origin['request_id'],'intent_sha256':origin['intent_sha256'],
        'material_revision':origin['material_revision'],'context_role':origin['context_role'],
        'created':origin['created'],'base_revision':origin['base_revision'],
        'status':row.get('status','open'),'status_note':row.get('status_note'),
        'status_history':copy.deepcopy(row.get('status_history') or []),'_ledger_projection':True,
        **({'review_route_spec':copy.deepcopy(origin['review_route'])} if 'review_route' in origin else {})}


def _ref(row):
    origin=row['authoring_origin']
    return {'schema_version':ORIGIN,'project':row['project'],'correction_id':origin['correction_id'],
        'feedback_id':row['id'],'material_revision':origin['material_revision'],
        'ledger':origin['source_basis']['ledger']}


def _receipt(row):
    origin=row['authoring_origin']
    from urllib.parse import urlencode
    ref=_ref(row)
    receipt={'project':row['project'],'revision':origin['authoring_revision'],
        'correction':projection(row),'origin_ref':ref,'source_basis':origin['source_basis'],
        'request_id':origin['request_id'],'intent_sha256':origin['intent_sha256'],'effect':'RECORDED',
        **({'review_route_spec':copy.deepcopy(origin['review_route'])} if 'review_route' in origin else {}),
        'reconcile':{'http':{'method':'GET','url':'/authoring/correction-request?'+urlencode({
            'project':row['project'],'request_id':origin['request_id'],'ledger':ref['ledger']})}},
        'read':{'http':{'method':'GET','url':'/authoring/correction-origin?'+urlencode({
            'project':row['project'],'origin_ref':json.dumps(ref,separators=(',',':'))})}}}
    if 'review_route' in origin:
        from laplace.work import work_delivery
        read=getattr(work_delivery,'origin_route_read',None)
        if callable(read):
            try:receipt['review_route_read']=read(row['project'],ref,origin['review_route'])
            except (ValueError,KeyError,TypeError) as exc:
                receipt['review_route_read_unavailable']=str(exc)[:240]
    return receipt


def locked_outcome(root,project,path,request_id,*,intent=None,required=False):
    """Existing append precondition only: caller already holds feedback lock."""
    if required and not path.is_file():raise ValueError('Established canonical feedback custody is unavailable.')
    rows=_rows(path)
    matching=[row for row in rows if any(isinstance(row.get(field),dict)
        and row[field].get('request_id')==request_id
        for field in ('authoring_origin','authoring_origin_settlement'))]
    if len(matching)>1:raise ValueError('Comment request outcome is ambiguous.')
    if not matching:return None
    row=matching[0]
    if row.get('project')!=project:raise ValueError('Comment request belongs to another project.')
    if 'authoring_origin' in row:
        meta=row['authoring_origin'];receipt=_receipt(row)
        result={'project':project,'request_id':request_id,'ledger':path.relative_to(root).as_posix(),
                'effect':'RECORDED','intent_sha256':meta['intent_sha256'],'receipt':receipt}
    else:
        meta=row['authoring_origin_settlement']
        if (row.get('record')!=SETTLEMENT_RECORD or meta.get('schema_version')!=SETTLEMENT
                or set(meta)!={'schema_version','request_id','intent_sha256','code','by'}
                or meta.get('code')!='AUTHOR_SETTLED_UNCOMMITTED_REQUEST' or meta.get('by')!='author'
                or not re.fullmatch(r'sha256:[0-9a-f]{64}',str(meta.get('intent_sha256') or ''))):
            raise ValueError('Canonical comment settlement is malformed or unsupported.')
        result={'project':project,'request_id':request_id,'ledger':path.relative_to(root).as_posix(),
            'effect':'NOT_ADMITTED','terminal':True,'intent_sha256':meta['intent_sha256'],'receipt':None,
            'settlement':{'id':row['id'],'code':meta['code'],'by':meta['by'],'at':row['ts']}}
    if intent is not None and result['intent_sha256']!=intent:
        raise ValueError('Comment request_id was already used for different intent.')
    return {**result,'settle':_settle_action(project,result['ledger'],request_id),
            'reconcile':_request_read(project,result['ledger'],request_id),
            'compare':_compare(project,result['ledger'],request_id)}


def request(project,request_id,repo_root=None,*,ledger,submission=None):
    """The exact lookup; with an ORIGINAL submission, also its scoped owner-domain association (pure).

    The submission's canonical intent is computed by this owner's own `_intent`; nothing is saved, settled or
    refreshed and no current source, guard or binding is adopted for the historical request."""
    intent=None
    if submission not in (None,''):
        try:value=json.loads(submission) if isinstance(submission,str) else submission
        except ValueError:raise ValueError('The original submission must be exact JSON.') from None
        if (not isinstance(value,Mapping) or value.get('request_id')!=request_id or value.get('project',project)!=project
                or not isinstance(value.get('source_basis'),Mapping) or value['source_basis'].get('ledger')!=ledger):
            raise ValueError('The original submission belongs to another project, feedback home or request; nothing is compared.')
        intent=_intent(project,value)
    found=_lookup(project,request_id,repo_root,ledger=ledger)
    return found if intent is None else _associate(project,ledger,request_id,intent,found)


def _associate(project,ledger,request_id,intent,found):
    effect=found['effect']
    state=(('MATCH' if found.get('intent_sha256')==intent else 'MISMATCH') if effect in ('RECORDED','NOT_ADMITTED')
           else 'UNRECORDED' if effect=='NONE' else 'UNKNOWN')
    association={'schema_version':ASSOCIATION,'kind':'origin','project':project,'context':ledger,
                 'request_id':request_id,'state':state,'intent_sha256':intent}
    if state=='MISMATCH':
        # Same id, another intent: nothing of the recorded request is disclosed or settleable from this copy.
        return {'project':project,'request_id':request_id,'ledger':ledger,'effect':'MISMATCH','association':association,
                'compare':copy.deepcopy(found['compare']),'reconcile':copy.deepcopy(found['reconcile']),
                'meaning':'This request_id records another exact intent; retain this copy and do not settle or retry it.'}
    return {**found,'association':association}


def _lookup(project,request_id,repo_root=None,*,ledger):
    from filelock import FileLock
    root=_owner()._root(repo_root);request_id=_request(request_id);path=_ledger(root,project,ledger)
    common={'project':project,'request_id':request_id,'ledger':ledger,
            'settle':_settle_action(project,ledger,request_id),
            'reconcile':_request_read(project,ledger,request_id),
            'compare':_compare(project,ledger,request_id)}
    try:
        canonical=canonical_ledger(root,project)
        if not (root/canonical).parent.parent.is_dir():
            raise ValueError('The registered canonical feedback home is unavailable.')
        original=root/ledger
        if original.is_symlink() and not original.exists():
            raise ValueError('The retained canonical feedback ledger is unavailable.')
        if path.parent.exists():
            with FileLock(str(path)+'.lock',timeout=10):
                if not path.is_file():raise ValueError('Established canonical feedback custody is unavailable.')
                found=locked_outcome(root,project,path,request_id,required=True)
        else:found=None
        if found is None:
            if ledger!=canonical:raise ValueError('Retained custody differs from the registered canonical home; absence is unknown.')
            return {**common,'effect':'NONE','receipt':None,'absence_scope':'registered canonical project feedback home at read'}
        return {**common,**found}
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return {**common,'effect':'UNKNOWN','receipt':None,'reason':str(exc)[:240]}


def inspect(project,origin_ref,repo_root=None):
    root=_owner()._root(repo_root)
    if (not isinstance(origin_ref,dict) or set(origin_ref)!=_REF_FIELDS
            or origin_ref.get('schema_version')!=ORIGIN or origin_ref.get('project')!=project):
        raise ValueError('An exact owner-issued feedback origin reference is required.')
    path=_ledger(root,project,origin_ref['ledger'])
    from filelock import FileLock
    if not path.parent.exists():raise ValueError('Comment origin is unavailable.')
    with FileLock(str(path)+'.lock',timeout=10):
        all_rows=_rows(path)
        rows=[row for row in all_rows if row.get('id')==origin_ref['feedback_id']]
    if len(rows)!=1:raise ValueError('Comment origin is unavailable, changed or ambiguous.')
    projection(rows[0])
    if _ref(rows[0])!=origin_ref:raise ValueError('Comment origin is unavailable, changed or ambiguous.')
    receipt=_receipt(rows[0]);basis=receipt['source_basis']
    if any(row.get('supersedes')==origin_ref['feedback_id'] for row in all_rows):
        receipt['correction']['status']='superseded'
    try:_current(root,project,basis);_quote(receipt['correction']['anchor'],basis);current={'state':'CURRENT'}
    except OSError as exc:current={'state':'UNAVAILABLE','reason':str(exc)[:240]}
    except ValueError as exc:current={'state':'CHANGED','reason':str(exc)[:240]}
    from urllib.parse import urlencode
    read={'http':{'method':'GET','url':'/authoring/correction-origin?'+urlencode(
        {'project':project,'origin_ref':json.dumps(origin_ref,separators=(',',':'))})}}
    return {'origin_ref':origin_ref,'correction':receipt['correction'],'source_basis':basis,
            **({'review_route_spec':receipt['review_route_spec']} if 'review_route_spec' in receipt else {}),
            **({'review_route_read':receipt['review_route_read']} if 'review_route_read' in receipt else {}),
            'currentness':current,'read':read}


def _intent(project,payload):
    _closed({**dict(payload),'project':project} if isinstance(payload,Mapping) else payload,contracts()['save'])
    if not isinstance(payload,Mapping) or set(payload)-_SAVE_FIELDS or payload.get('project',project)!=project:
        raise ValueError('Request-bound comments accept only the declared origin and route fields.')
    _request(payload.get('request_id'));basis=_basis(project,payload.get('source_basis'))
    if payload.get('scope')!='passage' or payload.get('kind') not in _owner()._CORRECTION_KINDS:
        raise ValueError('Request-bound comment origin requires an ordinary passage correction.')
    if type(payload.get('base_revision'))!=int or payload['base_revision']<0:
        raise ValueError('The original authoring base_revision is required.')
    anchor=payload.get('anchor')
    if (not isinstance(anchor,dict) or anchor.get('file')!=basis['file']
            or anchor.get('line_start')!=basis['line_start'] or anchor.get('line_end')!=basis['line_end']):
        raise ValueError('Comment anchor must retain the prepared canonical file and extent.')
    if set(anchor)-{'file','line_start','line_end','quote','section','section_id','node_id','block','source_selection'}:
        raise ValueError('Comment anchor contains unsupported control metadata.')
    # New origin is the passage instruction slice, never a disguised response effect.
    if any(key in anchor for key in ('feedback_target','feedback_effect','correction_id')):
        raise ValueError('Passage origins do not accept another feedback target or AC alias.')
    text=payload.get('text')
    if not isinstance(text,str) or not text.strip():raise ValueError('correction text is required')
    normalized={**dict(payload),'project':project,'text':text.strip(),'by':str(payload.get('by') or 'author')}
    try:return canonical_digest(normalized)
    except (TypeError,ValueError):raise ValueError('Comment intent must be exact JSON.') from None


def recover(project,payload,root,intent):
    found=request(project,payload['request_id'],root,ledger=payload['source_basis']['ledger'])
    if found['effect']=='UNKNOWN':raise ValueError(found['reason'])
    if found['effect']=='NONE':return None
    if found['intent_sha256']!=intent:raise ValueError('Comment request_id was already used for different intent.')
    if found['effect']=='NOT_ADMITTED':return found
    return found['receipt']


def custody(project,payload,row,revision):
    value={'schema_version':CUSTODY,'request_id':payload['request_id'],'intent_sha256':_intent(project,payload),
        'correction_id':row['id'],'created':row['created'],'kind':row['kind'],'scope':row['scope'],
        'context_role':row['context_role'],'base_revision':row['base_revision'],
        'authoring_revision':revision,'source_basis':copy.deepcopy(payload['source_basis'])}
    material={'project':project,'text':row['text'],'kind':row['kind'],'scope':row['scope'],
        'anchor':row['anchor'],'by':row['by'],'source_basis':value['source_basis']}
    value['material_revision']=canonical_digest(material)
    if 'review_route' in payload:value['review_route']=copy.deepcopy(payload['review_route'])
    return value


def save(project,payload,repo_root=None):
    from laplace.manuscript import manuscript_source as source_owner
    root=_owner()._root(repo_root);intent=_intent(project,payload)
    saved=recover(project,payload,root,intent)
    if saved:return saved
    basis=payload['source_basis'];_ledger(root,project,basis['ledger'])
    if basis['ledger']!=canonical_ledger(root,project):
        raise ValueError('New comment requests must use the registered canonical feedback home.')
    with source_owner.selection_mutation(project,root):
        # Replay after acquiring selection as well: another exact copy may have
        # committed while this invocation waited. No fresh guard is borrowed.
        saved=recover(project,payload,root,intent)
        if saved:return saved
        source,path=_selected(root,project,basis['file'])
        with source_owner.source_mutation([root/source['root'],path]):
            _current(root,project,basis,source,path)
            _quote(payload['anchor'],basis)
            return _owner()._bank_correction(project,payload,root,_origin={
                'intent':intent,'source':source,'ledger':basis['ledger']})


def settle(project,payload,repo_root=None):
    """Explicit author settlement of one retained submission, never a retry."""
    from laplace.manuscript import manuscript_bridge
    import datetime,uuid
    _closed(payload,contracts()['settle'])
    if payload['project']!=project:raise ValueError('Comment settlement belongs to another project.')
    submission=payload['submission'];intent=_intent(project,submission)
    request_id=submission['request_id'];ledger=submission['source_basis']['ledger']
    if payload.get('request_id',request_id)!=request_id or payload.get('ledger',ledger)!=ledger:
        raise ValueError('Settlement must retain its original request and canonical home.')
    root=_owner()._root(repo_root);path=_ledger(root,project,ledger)
    observed=request(project,request_id,root,ledger=ledger)
    if observed['effect']!='NONE':
        if observed['effect']!='UNKNOWN' and observed['intent_sha256']!=intent:
            raise ValueError('Comment request_id was already used for different intent.')
        return observed
    required=path.is_file()
    row={'record':SETTLEMENT_RECORD,'id':'FRS-'+uuid.uuid4().hex,'project':project,
        'ts':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'authoring_origin_settlement':{'schema_version':SETTLEMENT,'request_id':request_id,
            'intent_sha256':intent,'code':'AUTHOR_SETTLED_UNCOMMITTED_REQUEST','by':'author'}}
    def guard():
        found=locked_outcome(root,project,path,request_id,intent=intent,required=required)
        return {'origin_outcome':found} if found else None
    outcome=manuscript_bridge.append_feedback_record(path,row,origin_guard=guard)
    if outcome:return outcome['origin_outcome']
    # Only verified published custody may claim a terminal result. A failed or
    # partial append remains unknown, and the next exact read owns recovery.
    return request(project,request_id,root,ledger=ledger)
