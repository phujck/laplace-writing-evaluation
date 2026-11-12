"""Provider-neutral literature over the existing project reference associations.

Crossref verifies bibliographic identity, never an authored scientific claim.
Local provenance and reading assertions remain explicit, with file hashes where
available. Accessible full text is acquired only by an explicit fetch; Zotero databases remain read-only.
"""
from __future__ import annotations

from laplace.core.identity import revision_matches

import json
import copy
import re
import urllib.error
import threading
from collections import OrderedDict
from pathlib import Path

from laplace.research import references_surface as rs

RELATIONS = ('supports', 'contradicts', 'background', 'method', 'extends')
READING = ('unread', 'metadata-only', 'partial', 'read')


def text_read_contract():
    return {'query': {'type':'string','minLength':1,'maxLength':256},
            'expected_source_revision': {'type':'string'}}


def acquisition_candidates(item):
    """Publisher supplied full-text links, never inferred from a DOI landing page."""
    choices=[]
    for url in item.get('fulltext_urls') or []:
        parsed=urllib.parse.urlparse(str(url))
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:continue
        if any(row['url']==url for row in choices):continue
        choices.append({'id':'FETCH-'+rs._digest([item.get('key'),url])[:20],'url':url,
                        'qualification':'Publisher full-text candidate; content and publication alignment not verified'})
    return choices


def bibliography_projection(project,root,citekey,*,selected=None,entries=None,has_consumer=None,bib_revision=None,key=None):
    """Physical selected entry, distinct from retained metadata and PDF rendering."""
    from laplace.manuscript import manuscript_source
    selected=selected or manuscript_source.resolve(project,repo_root=root)
    main=Path(selected.get('root') or '')
    if not main.is_absolute():main=Path(root)/main
    if has_consumer is None:has_consumer=main.is_file() and bool(rs._bibliography_names(main))
    if not has_consumer:
        return {'state':'PENDING','entry_present':False,'rendered':'NOT_CHECKED','reason':'The selected manuscript has no bibliography consumer yet. Binding an intended claim composes the existing bibliography setup owner.'}
    bib=rs._bib_path(rs._manuscript(project,root),main).resolve()
    if not bib.is_relative_to(Path(root).resolve()):return {'state':'UNAVAILABLE','entry_present':False,'rendered':'NOT_CHECKED','reason':'Selected bibliography is outside the project source root.'}
    if entries is None:entries={entry['key']:entry for entry in rs._bib_entries(bib.read_text(encoding='utf-8'))} if bib.is_file() else {}
    entry=entries.get(citekey);present=bool(entry and entry['closed'])
    if key and present and not rs._entry_matches(entry['text'],key,set()):
        return {'state':'CONFLICT','entry_present':True,'identity_matches':False,'rendered':'NOT_CHECKED','citekey':citekey,'path':str(bib.relative_to(root)),'reason':'The citation key belongs to a different bibliography identity; its bytes were preserved.'}
    return {'state':'ATTACHED' if present else 'INVALID_ENTRY' if entry else 'MISSING_ENTRY',
            'entry_present':present,'path':str(bib.relative_to(root)),'citekey':citekey,'rendered':'NOT_CHECKED',
            'revision':bib_revision or (rs._sha256_file(bib) if bib.is_file() else None),
            'reason':None if present else 'The selected bibliography has no complete entry for this citation key.'}


def doi(value):
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', str(value or '').strip(), flags=re.I).lower()
    if not re.fullmatch(r'10\.\d{4,9}/\S+', value):
        raise ValueError('Use a DOI or doi.org URL with a valid DOI identity.')
    return value


def lookup(value):
    ident = doi(value)
    records = rs._crossref(doi=ident)
    if not records or not isinstance(records[0], dict) or doi(records[0].get('DOI')) != ident:
        raise ValueError('Crossref did not return the requested DOI identity.')
    item = rs._crossref_metadata(records[0])
    if not item.get('title'):
        raise ValueError('Crossref record has no title; metadata import is incomplete.')
    item['fulltext_urls']=[link['URL'] for link in records[0].get('link') or [] if isinstance(link,dict) and link.get('URL') and link.get('content-type') in ('application/pdf','text/plain','text/html')]
    item.update(key='doi:' + ident, version=rs._digest(item), modified='',
                provenance={'provider': 'crossref', 'url': 'https://api.crossref.org/works/' + ident,
                            'description': 'Publisher-deposited bibliographic metadata verified by DOI lookup.'})
    return {'provider': 'crossref', 'item': item, 'metadata_only': True,
            'verified_doi': ident, 'evidence_status': 'metadata-only'}


def citekey(item):
    author = (item.get('creators') or ['Reference'])[0].split()[-1]
    stem = re.sub(r'[^A-Za-z0-9]', '', author + str(item.get('year') or '')) or 'Reference'
    if not stem[0].isalpha(): stem = 'Ref' + stem
    return stem + rs._digest(item.get('key') or item)[:6]


def local_candidates(query,root,limit=5):
    from laplace.pipeline import citation_direction as cd
    from laplace.pipeline import graph
    refs=cd.probe_reference_corpus(root/'reference_corpus')
    store=root/'corpus/corpus.bib'
    if store.is_file():
        for key,fields in graph._parse_bib(store.read_text(encoding='utf-8')):
            year=str(fields.get('year') or '')
            refs.append({'id':'shared:'+key,'title':fields.get('title') or '',
                'authors':str(fields.get('author') or '').split(' and '),'year':int(year) if year.isdigit() else None,
                'doi':fields.get('doi') or '', 'url':fields.get('url') or '',
                'summary':fields.get('summary') or fields.get('claim') or '',
                'trust_status':fields.get('status') or 'unverified','_corpus':'corpus/corpus.bib'})
    intent=cd.LiteratureIntent(id='query',key='',claim=query)
    ranked=cd.reference_corpus_candidates(intent,refs,k=limit)
    index={str(row.get('id')):row for row in refs}
    return [{**candidate.as_dict(),'source_record':index.get(candidate.cand_id.removeprefix('corpus:'),{}),
             'qualification':'LOCAL_CANDIDATE_METADATA; inspect the original source before supporting a claim'} for candidate in ranked]


def canonical_rows(project, root, associations=None):
    """Read existing citation objects/typed edges; never migrate them on read."""
    from laplace.research import concepts as cs
    network = cs._network(project, root) or {}; nodes = network.get('nodes') or {}
    citations = {ident:node for ident,node in nodes.items() if node.get('kind') == 'citation'}
    if not citations: return []
    relations, _ = cs._relations(project, root, network)
    associations = associations or []; out = []
    recorded = {(row.get('key'),row.get('claim_id')) for row in associations}
    for ident,node in citations.items():
        projection = node.get('projection') or {}
        explicit = projection.get('bibliography') or {}
        title = explicit.get('title') or node.get('title') or node.get('label') or str(node.get('essence') or ident).split(', ',1)[0]
        refs = cs._source_refs(node)
        matching = next((row for row in associations if row.get('canonical_id') == ident and row.get('citekey')),None) or next((row for row in associations if row.get('canonical_id') == ident or row.get('key') == ident or row.get('citekey') and ident=='ref:'+row['citekey']),None)
        base = dict(matching) if matching else {'key':ident,'citekey':explicit.get('citekey'),'metadata':{
            'title':title,'creators':explicit.get('creators') or [],'year':explicit.get('year') or '',
            'metadata_basis':'Canonical citation description; bibliographic fields have not been inferred.'},
            'source':{'provider':'canonical','identity':rs._digest(node)},'state':'IN_ARGUMENT',
            'reading_status':'unassessed','evidence_status':'authored-argument-link'}
        base.update(canonical_id=ident,canonical_source=True,source_refs=refs,source_meaning=node.get('essence') or '',
                    bibliography_state='ATTACHED' if matching and matching.get('citekey') else 'NOT_LINKED')
        links=[]
        for relation in relations:
            other = relation.get('source') if relation.get('target') == ident else relation.get('target') if relation.get('source') == ident else None
            if not other or other in citations or other not in nodes: continue
            links.append({**base,'claim_id':other,'claim_label':cs._label(nodes[other],other),
                'relation':{'support':'supports','validated_by':'supports','counterevidence':'contradicts','implementation':'method'}.get(relation.get('rel'),'background'),
                'canonical_relation':relation,'rationale':relation.get('rationale') or '',
                'evidence_origin':'canonical typed relation','evidence_status':'authored-argument-link'})
        for row in links or [base]:
            if (row.get('key'),row.get('claim_id')) not in recorded: out.append(row)
    return out


def canonical_item(project, key, root):
    rows = canonical_rows(project, root)
    row = next((row for row in rows if row.get('key') == key), None)
    if not row: return None
    return {**row['metadata'],'key':key,'source_refs':row.get('source_refs') or [],
            'canonical_id':key,'version':row['source']['identity'],'modified':'','source_meaning':row.get('source_meaning')}


def canonical_source_path(project, item, root, source_index=0):
    from laplace.projects import writing_sources
    refs = item.get('source_refs') or []
    if not isinstance(source_index,int) or not 0 <= source_index < len(refs): raise ValueError('Choose an available source_index for this canonical citation.')
    ref = refs[source_index]
    if isinstance(ref,dict): spec = dict(ref); spec['path'] = spec.get('path') or spec.get('file')
    else:
        value, _, label = str(ref).partition('#'); prefix, sep, tail = value.partition(':')
        repositories = {row['id'] for row in writing_sources.inventory(root)['repositories']}
        spec = {'repository':prefix,'path':tail} if sep and prefix in repositories else {'path':value}
        if label: spec['label'] = label
    if spec.get('repository'):
        _, path = writing_sources._path(root,spec)
    else:
        path = (root / str(spec.get('path') or '')).resolve()
        if not path.is_relative_to(root): raise ValueError('Canonical source escapes the repository.')
        if not path.is_file():
            base = rs._manuscript(project,root)
            if base is None: raise ValueError('Unknown manuscript source.')
            path = (base / str(spec.get('path') or '')).resolve()
            if not path.is_relative_to(base.resolve()): raise ValueError('Canonical source escapes the manuscript.')
    if not path.is_file(): raise ValueError('Canonical source file is unavailable.')
    return path, {'status':'READ','file':str(path),'reference':ref,**spec}


def _shadow_keys(rows):
    """Only explicit metadata identity pointers prove a legacy alias shadow."""
    primary={row.get('key'):row for row in rows if row.get('key') and row.get('citekey')}
    shadows={row['key']:str((row.get('metadata') or {})['key']) for row in rows
            if row.get('key') and not row.get('citekey')
            and (row.get('metadata') or {}).get('key') in primary
            and (row.get('metadata') or {}).get('key')!=row['key']}
    for row in rows:
        if row.get('key') and not row.get('citekey'):
            matches={key for key,value in primary.items() if value.get('canonical_id')==row['key'] and key!=row['key']}
            if len(matches)==1:shadows[row['key']]=next(iter(matches))
    return shadows


def canonical_associations(rows, key=None):
    """Repair proven alias representations in the existing association store.

    Edition identities are never inferred from titles/authors. Old representations
    remain in identity_history, and differing authored bindings require a new bind.
    """
    shadows=_shadow_keys(rows)
    if key is not None:shadows={alias:target for alias,target in shadows.items() if target==key}
    if not shadows:return rows
    primaries={key:next(row for row in rows if row.get('key')==key and row.get('citekey')) for key in set(shadows.values())}
    revised=[];indexed={}
    ordered=sorted(enumerate(rows),key=lambda pair:pair[1].get('key') in shadows)
    for _,original in ordered:
        row=dict(original);oldkey=row.get('key');key=shadows.get(oldkey,oldkey)
        if oldkey in shadows:
            primary=primaries[key]
            row['key']=key
            for field in ('citekey','bib_path','metadata','source','state','bibliography_state'):
                if field in primary:row[field]=primary[field]
            if primary.get('source_text'):row['source_text']=primary['source_text']
            row['identity_history']=list(row.get('identity_history') or [])+[{'reason':'canonical citation alias repair','association':{k:v for k,v in original.items() if k!='identity_history'}}]
        pair=(key,row.get('claim_id'))
        if pair not in indexed:
            indexed[pair]=len(revised);revised.append(row);continue
        current=revised[indexed[pair]]
        readings={item['id']:item for item in list(current.get('reading_observations') or [])+list(row.get('reading_observations') or []) if item.get('id')}
        if readings:current['reading_observations']=list(readings.values())
        current['identity_history']=list(current.get('identity_history') or [])+list(row.get('identity_history') or [])
        if row.get('claim_id') and any(current.get(field)!=row.get(field) for field in ('relation','rationale','evidence','reading_receipt','canonical_id')):
            current['identity_history'].append({'reason':'distinct prior binding retained during identity repair','association':{k:v for k,v in row.items() if k!='identity_history'}})
            current['binding_state']='IDENTITY_REVIEW_REQUIRED'
        if not current.get('source_text') and row.get('source_text'):current['source_text']=row['source_text']
        if not current.get('canonical_id') and row.get('canonical_id'):current['canonical_id']=row['canonical_id']
    return revised


def _resolve_row(rows,key):
    shadows=_shadow_keys(rows);canonical=shadows.get(key,key)
    direct=[row for row in rows if row.get('key')==canonical and row.get('key') not in shadows]
    normalized_doi=None
    try:normalized_doi=doi(key)
    except ValueError:pass
    if not direct and normalized_doi:
        direct=[row for row in rows if row.get('key')=='doi:'+normalized_doi]
    candidates=direct or [row for row in rows if row.get('citekey')==key or row.get('canonical_id')==key or
        (normalized_doi and str((row.get('metadata') or {}).get('doi') or '').lower()==normalized_doi)]
    keys={shadows.get(row.get('key'),row.get('key')) for row in candidates}
    if len(keys)>1:raise ValueError('Reference alias is ambiguous; use one exact project key: '+', '.join(sorted(keys)))
    if not keys:return None
    canonical=next(iter(keys));matches=[row for row in rows if row.get('key')==canonical]
    return next((row for row in matches if not row.get('claim_id')),matches[0] if matches else None)


def resolve_item(project, key, root, library=None, *, live=False):
    """Resolve a project identity/alias before considering an unattached Zotero key."""
    manuscript = rs._manuscript(project, root)
    rows = rs._load_associations(manuscript) if manuscript else []
    row = _resolve_row(rows,str(key))
    if not row:
        item = canonical_item(project, key, root)
        if item:return 'canonical',item
        if rs._KEY.fullmatch(key):return (library or rs.Library()).item(key)
        return 'unknown',None
    provider = (row.get('source') or {}).get('provider', 'local')
    if rs._KEY.fullmatch(str(row['key'])) and provider not in ('local','crossref','canonical'):
        provider,item=(library or rs.Library()).item(row['key'])
        if item is None:return provider,None
        item=dict(item)
    elif live and provider == 'crossref':
        item=lookup((row.get('metadata') or {}).get('doi'))['item']
    else:
        item = dict(row.get('metadata') or {})
        item['key'] = row['key']
        if provider == 'canonical':
            live_item = canonical_item(project,row.get('canonical_id') or row['key'],root)
            if live_item:item.update(source_refs=live_item.get('source_refs') or [],source_meaning=live_item.get('source_meaning'))
        revision = (row.get('source') or {}).get('revision') or {}
        item.update(version=revision.get('version', ''), modified=revision.get('modified', ''))
        if live and provider == 'local':
            provenance = item.get('provenance') or {}
            if provenance.get('path'):
                path = local_path(provenance['path'], root, provenance.get('sha256'))
                current_hash = rs._sha256_file(path)
                item['version'] = rs._digest({'metadata': {k: v for k, v in item.items() if k not in ('version', 'modified')}, 'file_sha256': current_hash})
                if current_hash == provenance.get('sha256'):item['version'] = revision.get('version', '')
                else:item['provenance'] = {**provenance, 'sha256': current_hash}
    item['key']=row['key']
    if row.get('citekey'):item['citation_key']=row['citekey']
    if row.get('canonical_id'):item['canonical_id']=row['canonical_id']
    return provider, item


def local_path(value, root, sha256=None):
    """Resolve a recorded local provenance path; with the recorded `sha256` pin, an export
    that pinned the ORIGINAL bytes of a since-changed file resolves to those bytes."""
    from laplace.projects.writing_portability import source_path
    path = source_path(str(value), root, sha256=sha256)
    if not path.is_file(): raise ValueError('Local provenance path does not name a readable file.')
    return path


def original_contract():
    return {'type':'object','additionalProperties':False,'required':['artifact_id','expected_sha256'],
        'properties':{'artifact_id':{'type':'string','pattern':'^ART-[A-Za-z0-9-]+$'},
            'expected_sha256':{'type':'string','pattern':'^(sha256:)?[0-9a-f]{64}$'}}}


def import_contract():
    """The Literature import owner's exact legacy and retained-original inputs."""
    legacy={'type': 'object', 'required': [], 'properties': {'doi': {'type': 'string'}, 'citekey': {'type': 'string'}, 'canonical_id': {'type': 'string'}, 'metadata': {'type': 'object', 'required': ['title'], 'properties': {'title': {'type': 'string'}, 'creators': {'type': 'array', 'items': {'type': 'string'}}, 'year': {'type': 'string'}, 'item_type': {'type': 'string', 'enum': ['journalArticle', 'book', 'bookSection', 'conferencePaper', 'thesis', 'preprint', 'unpublished', 'webpage', 'misc']}, 'publication_title': {'type': 'string'}, 'volume': {'type': 'string'}, 'issue': {'type': 'string'}, 'pages': {'type': 'string'}, 'publisher': {'type': 'string'}, 'place': {'type': 'string'}, 'isbn': {'type': 'string'}, 'url': {'type': 'string'}}, 'additionalProperties': False}, 'provenance': {'type': 'object', 'required': ['description'], 'properties': {'description': {'type': 'string'}, 'path': {'type': 'string'}, 'url': {'type': 'string'}}, 'additionalProperties': False}}, 'additionalProperties': False}
    return {'oneOf':[legacy,{'type':'object','additionalProperties':False,'required':['original','metadata','provenance'],'properties':{'original':original_contract(),'metadata':copy.deepcopy(legacy['properties']['metadata']),'provenance':{'type':'object','additionalProperties':False,'required':['description'],'properties':{'description':{'type':'string','minLength':1}}},'citekey':{'type':'string'}}}]}


def retained_original(project, original, root):
    """Resolve exact retained bytes only through their same-project artifact owner."""
    from jsonschema import Draft202012Validator
    from laplace.projects import artifacts
    from laplace.core import source_pin
    error=next(Draft202012Validator(original_contract()).iter_errors(original),None)
    if error:raise ValueError('Choose the exact retained ART and full original source pin.')
    selected={'artifact_id':original['artifact_id'],'expected_sha256':'sha256:'+original['expected_sha256'].removeprefix('sha256:')}
    path,rel,scope,record=artifacts.target(root,project,{'id':selected['artifact_id']})
    meta=(record or {}).get('original_metadata') or {}
    if meta.get('schema_version')!='laplace.artifact-original/1' or meta.get('immutable') is not True:
        raise ValueError('This source is not a retained immutable document original.')
    from laplace.projects.material_intake import MEDIA
    if meta.get('media_type') not in MEDIA or path.stat().st_size>MEDIA[meta['media_type']]:raise ValueError('Retained source exceeds its admitted original media/byte bounds.')
    observed=artifacts.identity(root,project,{'id':selected['artifact_id'],'expected_sha256':selected['expected_sha256']})
    source_pin.check(observed['revision'],{'expected_sha256':record.get('sha256')})
    if observed['size_bytes']!=meta.get('bytes'):raise ValueError('Retained original size disagrees with its ART receipt.')
    return selected,path,meta


def _retained_key(project,original):
    return 'local:'+rs._digest({'project':project,'original':original})[:24]


def _retained_home(project,root):
    from laplace.research import research_context
    from laplace.projects import artifacts
    from laplace.manuscript import manuscript_source
    home=research_context.owner_home(project,root)
    if home is None or not home.is_dir():return home,'The existing Research state home is unavailable for this project. The original remains readable.'
    if not home.resolve().is_relative_to(artifacts.project_root(root,project)):
        return None,'Research state is not inside this selected project artifact/data home.'
    source=manuscript_source.resolve(project,repo_root=root)
    if source.get('read_only') or source.get('foreign'):return home,'The selected source is read-only. Keep the original or choose a writable project source before saving Literature metadata.'
    return home,None


def retained_capability(project,artifact_id,sha256,root=None):
    original={'artifact_id':artifact_id,'expected_sha256':'sha256:'+sha256.removeprefix('sha256:')}
    url='/references/source?'+rs.urllib.parse.urlencode({'project':project,'original':json.dumps(original,separators=(',',':'))})
    permitted,reason=True,None
    if root is not None:
        try:_home,reason=_retained_home(project,root);permitted=reason is None
        except (OSError,ValueError) as exc:permitted=False;reason=str(exc)
    return {'project':project,'operation':'reference_source','payload':{'original':original},
        'http':{'method':'GET','url':url},'permitted':permitted,'reason':reason}


def _reference_handle(project,key,operation,route,**fields):
    payload={'key':key,**fields}
    return {'project':project,'operation':operation,'payload':payload,
        'http':{'method':'GET','url':route+'?'+rs.urllib.parse.urlencode({'project':project,**payload})}}


def retained_source(project,original,root):
    original,path,meta=retained_original(project,original,root)
    read=retained_capability(project,original['artifact_id'],original['expected_sha256'],root)
    from laplace.projects import material_intake
    source={'display_name':meta.get('display_name'),'media_type':meta['media_type'],'sha256':original['expected_sha256'],
        'original_read':material_intake.artifact_handle(project,{'id':original['artifact_id'],'expected_sha256':original['expected_sha256']},route='original')}
    home,reason=_retained_home(project,root);standing={'state':'NONE','metadata_saved':False,'bibliography':{'state':'PENDING','entry_present':False,'rendered':'NOT_CHECKED'}}
    try:
        rows=rs._load_associations(home,require_supported=True) if home and home.is_dir() else []
        prior=_resolve_row(rows,_retained_key(project,original))
        if prior:
            recorded=(prior.get('metadata') or {}).get('provenance',{}).get('original')
            if recorded!=dict(project=project,**original):raise ValueError('Saved source identity and original provenance disagree.')
            association={key:copy.deepcopy(prior[key]) for key in ('key','citekey','metadata','source','state','bibliography_state','bib_path','canonical_id','bibliography_follow_through') if key in prior}
            standing.update(state='RECORDED',metadata_saved=True,key=prior['key'],association=association,
                bibliography=bibliography_projection(project,root,prior.get('citekey'),key=prior['key']),
                bibliography_follow_through=copy.deepcopy(prior.get('bibliography_follow_through') or {'state':'NOT_RECORDED'}))
    except (OSError,ValueError,TypeError) as exc:
        standing.update(state='UNKNOWN',reason=str(exc));reason='Source metadata standing is unavailable. Keep the original intent and inspect again.'
    action={'permitted':reason is None,'reason':reason,'operation':'literature_import','http':{'method':'POST','url':'/references/literature-import'},
        'payload':{'project':project,'original':copy.deepcopy(original)},'requires':['metadata','provenance'],'optional':['citekey']}
    result={'schema_version':'laplace.retained-source-literature/1','project':project,'original':original,'source':source,
        'support':{'permitted':reason is None,'reason':reason},'standing':standing,'read':read,
        'actions':{'import':action,'reconcile':read},'reconciliation':'Saved standing by stable source identity, not attribution of an uncertain response. Differing saved metadata is never overwritten by import.'}
    if standing['state']=='RECORDED':
        key=standing['key'];result.update(source_read=_reference_handle(project,key,'reference_source','/references/source'),
            text_read=_reference_handle(project,key,'reference_text','/references/text',offset=0,limit=24000,expected_source_revision=original['expected_sha256']))
    return result


class RetainedImportRejected(ValueError):
    def __init__(self, details):
        self.details=details
        super().__init__(details['error'])


def retained_import_validation(payload):
    """Only known retained-input rejection, before original/home/lock/effects."""
    from jsonschema import Draft202012Validator
    fields={key:value for key,value in payload.items() if key!='project'}
    error=next(Draft202012Validator(import_contract()).iter_errors(fields),None)
    reason,message=None,None
    if error:
        reason='INVALID_RETAINED_IMPORT';message='Retained source import must match its closed metadata/original contract: '+error.message[:500]
    elif not payload['metadata']['title'].strip() or not payload['provenance']['description'].strip():
        reason='BLANK_REQUIRED_DETAILS';message='Explicit title and provenance description are required.'
    if reason:
        return {'error':message,'metadata_saved':False,'disposition':{'state':'REJECTED_BEFORE_EFFECTS','operation':'literature_import','reason_code':reason}}
    return None


def retained_import_disposition(details):
    """Bounded public input-refusal fields; adapters unwrap their own errors."""
    if not isinstance(details,dict):return {}
    disposition=details.get('disposition') or {}
    if not isinstance(disposition,dict) or disposition.get('state')!='REJECTED_BEFORE_EFFECTS' or disposition.get('operation')!='literature_import' or disposition.get('reason_code') not in {'INVALID_RETAINED_IMPORT','BLANK_REQUIRED_DETAILS'}:return {}
    return {'metadata_saved':False,'disposition':copy.deepcopy(disposition)}


def retained_import_error_details(error):
    if not isinstance(error,RetainedImportRejected):return {}
    return retained_import_disposition(error.details)


def _import_retained(project,payload,root):
    rejected=retained_import_validation(payload)
    if rejected:return 422,rejected
    original,path,meta=retained_original(project,payload['original'],root)
    home,reason=_retained_home(project,root)
    if reason:return 422,{'error':reason,'retained_source':retained_source(project,original,root),'metadata_saved':False}
    metadata=payload['metadata'];description=payload['provenance']['description']
    item={key:value for key,value in rs._metadata(metadata).items() if key not in {'key','version','modified','provenance'}}
    item['provenance']={'description':description,'original':dict(project=project,**original),'media_type':meta['media_type']}
    item.update(key=_retained_key(project,original));item.update(version=rs._digest(item),modified='')
    from filelock import FileLock
    with FileLock(str(home/'.references.lock'),timeout=15):
        # Revalidate original and home after the existing reference lease, before effects.
        retained_original(project,original,root);current,reason=_retained_home(project,root)
        if reason or current!=home:return 409,{'error':reason or 'Research source home changed before import.','metadata_saved':False}
        try:rows=rs._load_associations(home,require_supported=True)
        except ValueError as exc:
            observed=retained_source(project,original,root)
            return 409,{'error':str(exc),'metadata_saved':False,'retained_source':observed,'read':observed['read']}
        prior=_resolve_row(rows,item['key'])
        before_rows=copy.deepcopy(rows);association_path=home/rs._ASSOCIATIONS
        before_bytes=association_path.read_bytes() if association_path.is_file() else None
        if prior:
            recorded=(prior.get('metadata') or {}).get('provenance',{}).get('original')
            if recorded!=dict(project=project,**original):return 409,{'error':'Recorded source identity has conflicting original provenance.'}
            row=prior;code=200
        else:
            cite=payload.get('citekey') or citekey(item)
            if not isinstance(cite,str) or not rs._CITEKEY.fullmatch(cite):return 422,{'error':'citekey is not BibTeX-safe'}
            if any(r.get('citekey')==cite and r.get('key')!=item['key'] for r in rows):return 409,{'error':'citekey collision: '+cite}
            row=rs._pending_association('local',item,cite);row['bibliography_follow_through']={'state':'PENDING','read':_reference_handle(project,item['key'],'reference_source','/references/source')}
            rows.append(row)
            rs._write_associations(home,rows);code=201
        result={'ok':True,'reused':bool(prior),'association':copy.deepcopy(row),
            'note':'Metadata saved; bibliography and claim binding are independent. Reused differing metadata requires explicit reference_update.'}
        actual=row.get('metadata') or {}
        unchanged=({k:v for k,v in actual.items() if k not in {'key','version','modified'}}=={k:v for k,v in item.items() if k not in {'key','version','modified'}}
            and ('citekey' not in payload or row['citekey']==payload['citekey']))
        from laplace.manuscript import manuscript_source,source_effects
        selected=manuscript_source.resolve(project,repo_root=root)
        main=Path(selected.get('root') or '')
        if not main.is_absolute():main=root/main
        # Only the already-wired bibliography is optional follow-through here. No source setup.
        if unchanged and row.get('bibliography_state')=='PENDING' and main.is_file() and rs._bibliography_names(main):
            row['bibliography_follow_through']={'state':'ATTEMPTING','read':_reference_handle(project,item['key'],'reference_source','/references/source'),'qualification':'Metadata is saved; optional bibliography completion is not yet confirmed.'}
            rs._write_associations(home,rows)
            owned=[];changes=[];effect=None
            try:
                updated=_materialize(project,row,root,owned,source_changes=changes,require_existing_consumer=True)
                effect=updated.pop('source_effect',None);row.update(updated)
                if effect:source_effects.finish({},project,root,effect,heading_sync={'status':'NOT_NEEDED','updated':[]})
                row['bibliography_follow_through']={'state':'COMPLETE',**({'source_effect':copy.deepcopy(effect)} if effect else {}),'read':_reference_handle(project,item['key'],'reference_source','/references/source')}
                rs._write_associations(home,rows)
                if effect:result['source_effect']=effect
            except (OSError,ValueError) as exc:
                details=source_effects.error_details(exc)
                if effect and not details:
                    effect['complete']=False;effect['follow_through']['required'].append({'owner':'reference-association','status':'UNPROVED','reason':str(exc)})
                    details={'source_effect':effect,'recovery':'Inspect retained metadata and exact bibliography effect before another action.'}
                if isinstance(details.get('source_effect'),dict):source_effects.finish({},project,root,details['source_effect'],heading_sync={'status':'NOT_NEEDED','updated':[]})
                result.update(partial={'bibliography':str(exc)},**details)
                retained_rows=rs._load_associations(home,require_supported=True);retained_row=_resolve_row(retained_rows,item['key'])
                retained_row['bibliography_follow_through']={'state':'PARTIAL','reason':str(exc),**copy.deepcopy(details),'read':_reference_handle(project,item['key'],'reference_source','/references/source')}
                try:rs._write_associations(home,retained_rows)
                except OSError:result['partial']['observation']='Metadata and ATTEMPTING stage retained; final effect receipt publication is unconfirmed. Inspect the current bibliography owner.'
            if owned:result['bibliography_owned_files']=owned
        current_rows=rs._load_associations(home,require_supported=True)
        result['owned_changes']=rs._owned_associations(root,home,before_bytes,before_rows,current_rows,['references','research','pipeline'])
        result['association']=copy.deepcopy(_resolve_row(current_rows,item['key']))
        prepared=retained_source(project,original,root)
        result.update(retained_source=prepared,read=prepared['read'],metadata_saved=prepared['standing']['metadata_saved'],bibliography=prepared['standing']['bibliography'])
        if prepared['standing']['state']=='RECORDED':
            saved=prepared['standing']['association'];actual=saved.get('metadata') or {}
            result['submitted_matches_saved']={'metadata':{k:v for k,v in actual.items() if k not in {'key','version','modified','provenance'}}=={k:v for k,v in item.items() if k not in {'key','version','modified','provenance'}},
                'provenance':actual.get('provenance')==item['provenance'],'citekey':'citekey' not in payload or saved.get('citekey')==payload['citekey']}
        return code,result


def import_reference(project, payload, root):
    if 'original' in payload:return _import_retained(project,payload,root)
    if payload.get('doi'):
        if payload.get('metadata') or payload.get('provenance'):
            return 422, {'error': 'Supply doi OR local metadata with provenance, not both.'}
        imported = lookup(payload['doi'])
    else:
        metadata = payload.get('metadata')
        provenance = payload.get('provenance')
        if not isinstance(metadata, dict) or not str(metadata.get('title') or '').strip():
            return 422, {'error': 'Local import requires metadata.title.'}
        if metadata.get('doi'):
            return 422, {'error': 'Import DOI-bearing works with doi so its metadata can be verified.'}
        if not isinstance(provenance, dict) or not str(provenance.get('description') or '').strip():
            return 422, {'error': 'Local import requires provenance.description; identify the supplied source.'}
        if not isinstance(metadata.get('creators', []), list) or not all(isinstance(x, str) for x in metadata.get('creators', [])):
            return 422, {'error': 'metadata.creators must be an array of names.'}
        item = {k: v for k, v in rs._metadata(metadata).items() if k not in ('key', 'version', 'modified', 'provenance')}
        provenance = {k: str(v) for k, v in provenance.items() if k in ('description', 'path', 'url')}
        if provenance.get('path'):
            path = local_path(provenance['path'], root)
            provenance.update(path=str(path), sha256=rs._sha256_file(path))
        item['provenance'] = provenance
        # Stable source identity survives metadata and local file revisions.
        identity = provenance.get('path') or provenance.get('url') or {'title': item['title'], 'creators': item.get('creators'), 'year': item.get('year')}
        item.update(key='local:' + rs._digest(identity)[:24])
        item.update(version=rs._digest(item), modified='')
        imported = {'provider': 'local', 'item': item}
    if payload.get('canonical_id') and canonical_item(project, payload['canonical_id'], root) is None:
        return 422, {'error':'canonical_id must identify an existing citation object'}
    manuscript = rs._manuscript(project, root)
    if manuscript is None or not manuscript.is_dir(): return 404, {'error': 'unknown project manuscript'}
    from filelock import FileLock
    with FileLock(str(manuscript / '.references.lock'), timeout=15):
        rows = rs._load_associations(manuscript)
        before_rows=json.loads(json.dumps(rows));association_path=manuscript/rs._ASSOCIATIONS
        before_association=association_path.read_bytes() if association_path.is_file() else None
        item = imported['item']
        prior = next((r for r in rows if r.get('key') == item['key'] or
                      (item.get('doi') and str((r.get('metadata') or {}).get('doi') or '').lower() == item['doi'])), None)
        if prior:
            if payload.get('canonical_id') and not prior.get('canonical_id'):
                for row in rows:
                    if row.get('key') == prior.get('key'): row['canonical_id'] = payload['canonical_id']
                rs._write_associations(manuscript, rows)
            return 200, {'ok': True, 'reused': True, 'association': prior,
                         'owned_changes':rs._owned_associations(root,manuscript,before_association,before_rows,rows,['references','research','pipeline']),
                         'note': 'Existing identity reused. Use reference_update to adopt changed metadata.'}
        return rs._attach_locked(project, {**payload, 'key': item['key']}, root, imported=imported)


def _materialize_bib(project, root, manuscript, main):
    """Apply the existing registered bibliography fence before taking a lease."""
    from laplace.pipeline import registry
    bib=rs._bib_path(manuscript,main).resolve();record=registry.resolve(project,repo_root=root)
    home=record.path(record.project_dir,root) if record and record.project_dir else manuscript
    shared=record.path(record.bib,root) if record and record.bib else None
    if not bib.is_relative_to(home.resolve()) and not bib.is_relative_to(manuscript.resolve()) and (not shared or bib!=shared.resolve()):
        raise ValueError('Selected bibliography escapes the project and its registered shared source.')
    return bib


def _materialize(project,row,root,owned_files=None, *, source_changes=None,require_existing_consumer=False):
    """Compose the existing bibliography setup owner with the selected .bib."""
    from laplace.manuscript import manuscript_source
    selected=manuscript_source.resolve(project,repo_root=root)
    main=Path(selected.get('root') or '')
    if not main.is_absolute():main=root/main
    if not main.is_file():return row
    if selected.get('read_only'):raise ValueError('Select an editable manuscript before materializing its bibliography.')
    manuscript=rs._manuscript(project,root)
    bib=_materialize_bib(project,root,manuscript,main)
    with manuscript_source.selection_mutation(project, root), manuscript_source.source_mutation([main,bib]):
        current=manuscript_source.resolve(project,repo_root=root)
        if current.get('root')!=selected.get('root') or current.get('manuscript_dir')!=selected.get('manuscript_dir') or current.get('read_only') or _materialize_bib(project,root,manuscript,main)!=bib:
            raise ValueError('Selected bibliography changed while waiting for its source lease; inspect and retry.')
        from laplace.manuscript import source_effects
        owned_files = owned_files if owned_files is not None else []
        first_file = len(owned_files)
        try:
            result = _materialize_locked(project,row,root,owned_files,source_changes=source_changes,
                                         selected=current, main=main, manuscript=manuscript, bib=bib,require_existing_consumer=require_existing_consumer)
        except Exception as exc:
            if len(owned_files) > first_file:
                effect = source_effects.receipt(project, manuscript_source.selection_identity(current, project),
                    owned_files[first_file:], complete=False,
                    required=[{'owner':'bibliography-materialization','status':'FAILED','reason':str(exc)}])
                raise source_effects.SourceEffectFailure(exc, effect) from exc
            raise
        if len(owned_files) > first_file:
            result['source_effect'] = source_effects.receipt(project,
                manuscript_source.selection_identity(current, project), owned_files[first_file:],
                required=[{'owner':'bibliography-materialization','status':'COMPLETE'}])
        return result


def _materialize_locked(project,row,root,owned_files=None, *, source_changes=None,
                        selected, main, manuscript, bib,require_existing_consumer=False):
    # All root and bibliography reads/commits share the parent's fixed lease set.
    from laplace.pipeline import bibliography_stage
    if selected.get('read_only'):raise ValueError('Select an editable manuscript before materializing its bibliography.')
    original=main.read_text(encoding='utf-8')
    if not rs._bibliography_names(main):
        if require_existing_consumer:raise ValueError('Selected bibliography consumer changed; metadata is retained without wiring a manuscript.')
        planned=bibliography_stage.wired_text(original)
        if '\\bibliographystyle' not in planned:planned=planned.replace('\\bibliography{','\\bibliographystyle{plain}\n\\bibliography{',1)
        from laplace.manuscript import review_surface, manuscript_source
        result=review_surface.adjudicate(manuscript,project,{'verb':'rewrite','file':str(main.relative_to(manuscript)),
            'expected_selection':manuscript_source.selection_identity(selected, project),
            'line_start':1,'line_end':len(original.split('\n')),'before':original,'after':planned,
            'by':'literature-bibliography','note':'Materialize the bibliography for an explicitly used source.','scope':'sentence'}, source_changes=source_changes, repo_root=root)
        if not result.get('ok') or result.get('pending'):raise ValueError(result.get('error') or 'Bibliography setup encountered a concurrent source change; inspect and retry.')
        if owned_files is not None:owned_files.append(rs._owned_file(root,main,original.encode(),planned.encode()))
    existed=bib.is_file();existing=bib.read_text(encoding='utf-8') if existed else ''
    entry=next((entry for entry in rs._bib_entries(existing) if entry['key']==row['citekey']),None)
    item={**row.get('metadata',{}),'key':row['key']}
    if entry and not rs._entry_matches(entry['text'],row['key'],{item.get('doi') or ''}):raise ValueError('Existing citation key has a different identity; reconcile it before use.')
    if not entry:
        bib.parent.mkdir(parents=True,exist_ok=True);pending=bib.with_suffix('.bib.pending')
        expected=existing+('\n' if existing and not existing.endswith('\n') else '')+rs._bib_entry(item,row['citekey'])
        pending.write_text(expected,encoding='utf-8')
        if (bib.read_text(encoding='utf-8') if bib.is_file() else '')!=existing:
            pending.unlink(missing_ok=True);raise ValueError('Bibliography changed while preparing the entry; retry without overwriting it.')
        from laplace.manuscript.source_effects import publish
        publish(pending, bib)
        if source_changes is not None:
            source_changes.append((bib, existing, expected))
        if owned_files is not None:owned_files.append(rs._owned_file(root,bib,existing.encode() if existed else None,expected.encode()))
    return {**row,'bib_path':str(bib.relative_to(root)),'bibliography_state':'ATTACHED'}


def bind(project, payload, root):
    from laplace.manuscript.manuscript_source import SourceLeaseError
    source_changes = []
    try:
        status, result = _bind(project, payload, root, source_changes=source_changes)
    except SourceLeaseError as exc:
        status, result = 409, {'error':str(exc), 'reason':'source-lease-unavailable',
                               'recovery':'Inspect references and current source before retrying literature_bind.'}
    except ValueError as exc:
        from laplace.manuscript.source_effects import error_details
        details = error_details(exc)
        if not details:
            raise
        status, result = 409, {'ok':False, 'error':str(exc), **details}
    if source_changes:
        from laplace.manuscript.review_surface import mirror_source_changes
        try:
            result['plan_sync'] = mirror_source_changes(project, source_changes, root,
                expected_selection=(result.get('source_effect') or {}).get('selection_identity'))
        except Exception as exc:
            result['plan_sync'] = {'status':'UNPROVED', 'reason':str(exc), 'source_effect_retained':True}
    if isinstance(result.get('source_effect'), dict):
        from laplace.manuscript import source_effects
        source_effects.finish(result, project, root, result['source_effect'], changes=source_changes,
            heading_sync=result.get('plan_sync'))
    return status, result


def _bind(project, payload, root, *, source_changes):
    key, claim = payload.get('key'), payload.get('claim_id')
    relation, rationale = payload.get('relation'), payload.get('rationale')
    reading = payload.get('reading_status', 'unread')
    if not key or not claim or relation not in RELATIONS or not isinstance(rationale, str) or not rationale.strip():
        return 422, {'error': 'Require key, canonical claim_id, relation and nonempty rationale.'}
    if reading not in READING: return 422, {'error': 'Invalid reading_status.'}
    evidence = payload.get('evidence') or {}
    if not isinstance(evidence, dict) or (evidence and not str(evidence.get('locator') or '').strip()):
        return 422, {'error': 'Passage evidence requires a source locator (page, section or line).'}
    if evidence and reading not in ('partial', 'read'):
        return 422, {'error': 'Passage evidence requires an explicitly authored partial/read status.'}
    if relation != 'background' and (not evidence or reading not in ('partial','read')):
        return 422, {'error':'A relied-on source link requires an inspected passage locator and partial/read status. Use background for metadata-only relevance; unsupported claims remain open.'}
    from laplace.research import literature_support
    selected_node=(literature_support.network(project,root).get('nodes') or {}).get(claim)
    if not selected_node:
        return 404, {'error': 'claim_id must identify an existing logical-plan object.'}
    if selected_node.get('kind') not in literature_support.CLAIM_KINDS:
        return 422, {'error':'Choose a meaningful scientific claim, definition, assumption or method; a citation/section/administrative object is not a claim target.'}
    if not payload.get('claim_revision'):
        return 422, {'error':'Inspect the intended claim meaning first and supply its source_support.meaning_revision as claim_revision.'}
    manuscript = rs._manuscript(project, root)
    if manuscript is None: return 404, {'error': 'unknown project manuscript'}
    from filelock import FileLock
    from laplace.research import corpus_ingest as ci
    from laplace.research import literature_support
    with FileLock(str(manuscript / '.references.lock'), timeout=15):
        rows = rs._load_associations(manuscript)
        before_rows=json.loads(json.dumps(rows));association_path=manuscript/rs._ASSOCIATIONS
        before_association=association_path.read_bytes() if association_path.is_file() else None
        ledger=ci._rewire_path(root,project);ledger_before=ledger.read_bytes() if ledger.is_file() else None
        provider,item=resolve_item(project,key,root)
        if item is None:return 404,{'error':'Import or select the source before binding.'}
        key=str(item['key']);rows=canonical_associations(rows,key=key)
        source = next((r for r in rows if r.get('key') == key and not r.get('claim_id')),None) or next((r for r in rows if r.get('key') == key), None)
        if source is None: source = next((row for row in canonical_rows(project,root) if row.get('key') == key),None)
        if source is None: return 404, {'error':'Import or select the source before binding.'}
        observations=[]
        for candidate in rows:
            if candidate.get('key')!=key:continue
            observations.extend(candidate.get('reading_observations') or [])
            if candidate.get('reading_receipt'):observations.append(candidate['reading_receipt'])
        observations=list({item['id']:item for item in observations if item.get('id')}.values())
        if not observations and source.get('canonical_id'):
            observations=[item for candidate in rows if candidate.get('canonical_id')==source['canonical_id'] or candidate.get('key')==source['canonical_id'] for item in candidate.get('reading_observations') or []]
        selected=next((item for item in reversed(observations) if not payload.get('reading_id') or item.get('id')==payload['reading_id']),None)
        if relation!='background':
            active_source,_=source_info(project,key,root,source_index=(selected or {}).get('source_index',0))
            if not selected or not literature_support.observed_passage(selected) or not literature_support.receipt_current(selected,project=project,root=root) or selected.get('source_sha256')!=active_source.get('sha256'):
                return 409, {'error':'Read a current source passage with reference_text before binding relied-on support.', 'recovery':'reference_text {key, offset?, limit?}, then literature_bind with reading_id'}
            selected_path=(retained_original(project,{k:v for k,v in selected['original'].items() if k!='project'},root)[1] if selected.get('original') else Path(selected['source_path']))
            content=_content(selected_path,selected['source_sha256'])
            fragment=content[selected['offset']:selected['offset']+selected['length']]
            if selected.get('text_sha256') and selected['text_sha256']!='sha256:'+rs.hashlib.sha256(fragment.encode()).hexdigest():
                return 409,{'error':'The extracted passage no longer matches its exact reading proof; reread the intended passage before binding.'}
            if evidence.get('excerpt') and evidence['excerpt'] not in fragment:
                return 422, {'error':'The supplied excerpt is not in the selected observed passage.'}
            if reading=='read':
                end=0
                for observed in sorted((item for item in observations if item.get('source_sha256')==selected['source_sha256'] and literature_support.observed_passage(item)),key=lambda item:item['offset']):
                    if observed['offset']<=end:end=max(end,observed['offset']+observed['length'])
                if end<len(content):return 422, {'error':'Whole-source reading coverage is incomplete; use partial or continue reference_text at the returned next_offset.'}
        claim_revision=literature_support.meaning_revision(project,claim,root)
        if payload.get('claim_revision') and not revision_matches(payload['claim_revision'],claim_revision):
            return 409,{'error':'The claim meaning changed; inspect its current source_support.meaning_revision before binding.'}
        current=next((r for r in rows if r.get('key')==key and r.get('claim_id')==claim),None)
        citation=(current or {}).get('canonical_id') or source.get('canonical_id') or ('ref:'+source['citekey'] if source.get('citekey') else 'cite:source-'+rs._digest(key)[:16])
        row=dict(current or source)
        # Source reading history has one source-level home. A claim retains its
        # exact selected proof, not a growing duplicate of every later read.
        row.pop('reading_observations',None)
        row.update(canonical_id=citation,claim_id=claim,claim_revision=claim_revision,relation=relation,rationale=rationale,reading_status=reading,
                   evidence=evidence,evidence_status='authored-passage' if selected else 'metadata-only',
                   reading_receipt=selected,reading_assertion='passage observed; interpretation authored, not independently verified',
                   evidence_source_identity=(source.get('source') or {}).get('identity'),binding_state='PENDING_CANONICAL')
        if current is not None:rows[rows.index(current)]=row
        else:rows.append(row)
        # Persist recoverable intent first. Readers never qualify a pending pair;
        # retrying the same key+claim repairs it without duplicate nodes/edges.
        rs._write_associations(manuscript,rows)
        pending_association=rs._association_bytes(rows)
        net=literature_support.network(project,root);nodes=net.get('nodes') or {}
        metadata=source.get('metadata') or {};mutations=[];records=[];owned_files=[]
        if citation not in nodes:
            reference={'reference_key':key}
            if selected:reference.update(path=selected['source_path'],sha256=selected['source_sha256'],locator=selected['locator'])
            made=ci.rewire_add(root,project,{'kind':'add-node','node':citation,'node_kind':'citation',
                'parent':net.get('root'),'essence':metadata.get('title') or key,'ref':reference,
                'projection':{'bibliography':{'reference_key':key,'citekey':source.get('citekey'),'title':metadata.get('title'),'creators':metadata.get('creators') or [],'year':metadata.get('year')},
                              'literature_source':{'reference_key':key}},'by':'literature-bind'})
            if made.get('error'):return 409,{'error':made['error'],'binding_state':'PENDING_CANONICAL','recovery':'Retry literature_bind with the same key and claim after resolving the canonical error.'}
            mutations.append(made.get('record',{}).get('id'));records.append(made['record'])
        elif source.get('citekey') and ((nodes[citation].get('projection') or {}).get('bibliography') or {}).get('citekey')!=source['citekey']:
            projection=dict(nodes[citation].get('projection') or {})
            projection['bibliography']={**(projection.get('bibliography') or {}),'reference_key':key,'citekey':source['citekey'],
                'title':metadata.get('title'),'creators':metadata.get('creators') or [],'year':metadata.get('year')}
            projection['literature_source']={**(projection.get('literature_source') or {}),'reference_key':key}
            made=ci.rewire_add(root,project,{'kind':'set-projection','node':citation,'value':projection,'by':'literature-bind'})
            if made.get('error'):return 409,{'error':made['error'],'binding_state':'PENDING_CANONICAL'}
            mutations.append(made.get('record',{}).get('id'));records.append(made['record'])
        edge_relation={'supports':'support','method':'support','extends':'support','contradicts':'counterevidence','background':'analogy'}[relation]
        net=literature_support.network(project,root)
        prior_edge=next((r for r in net.get('relations') or [] if r.get('source')==claim and r.get('target')==citation),None)
        if not prior_edge or prior_edge.get('rel')!=edge_relation or prior_edge.get('rationale')!=rationale:
            made=ci.rewire_add(root,project,{'kind':'retype-edge' if prior_edge else 'add-edge','node':claim,'target':citation,
                'rel':edge_relation,'rationale':rationale,'by':'literature-bind'})
            if made.get('error'):return 409,{'error':made['error'],'binding_state':'PENDING_CANONICAL','recovery':'Retry this same binding; the source node already exists and will be reused.'}
            mutations.append(made.get('record',{}).get('id'));records.append(made['record'])
        if literature_support.meaning_revision(project,claim,root)!=claim_revision:
            return 409,{'error':'The claim changed during source admission; the pending binding was preserved for reassessment.','binding_state':'PENDING_CANONICAL'}
        if relation!='background':
            observed_source,_=source_info(project,key,root,source_index=selected.get('source_index',0))
            if not literature_support.receipt_current(selected,project=project,root=root) or observed_source.get('sha256')!=selected['source_sha256']:
                return 409,{'error':'The source changed during admission; read the current passage and retry.','binding_state':'PENDING_CANONICAL'}
        materialized_effect = None
        materialized=row.get('bibliography_state')=='PENDING'
        if materialized:
            updated=_materialize(project,row,root,owned_files,source_changes=source_changes)
            materialized_effect = updated.pop('source_effect', None)
            row.update(updated)
        if association_path.read_bytes()!=pending_association:
            error = ValueError('Reference metadata changed during admission; inspect retained source effects before further action.')
            if materialized_effect:
                from laplace.manuscript.source_effects import SourceEffectFailure
                materialized_effect['complete'] = False
                materialized_effect['follow_through']['required'].append({'owner':'reference-binding','status':'FAILED','reason':str(error)})
                raise SourceEffectFailure(error, materialized_effect)
            raise error
        row['binding_state']='BOUND';row['canonical_records']=[value for value in mutations if value]
        try:
            rs._write_associations(manuscript,rows)
        except Exception as exc:
            if materialized_effect:
                from laplace.manuscript.source_effects import SourceEffectFailure
                materialized_effect['complete'] = False
                materialized_effect['follow_through']['required'].append({'owner':'reference-binding','status':'UNPROVED','reason':str(exc)})
                raise SourceEffectFailure(exc, materialized_effect) from exc
            raise
        owned=rs._owned_associations(root,manuscript,before_association,before_rows,rows,['references','concepts','structure','research','pipeline']+(['manuscript'] if materialized else []))
        owned['files'].extend(owned_files);owned['rewire_records']=records
        if records:
            expected=(ledger_before or b'')+''.join(json.dumps(record,ensure_ascii=False)+'\n' for record in records).encode('utf-8')
            owned['files'].append(rs._owned_file(root,ledger,ledger_before,expected))
            owned['objects'].extend({'owner':'concepts','id':record.get('node'),'target':record.get('target'),'record_id':record['id'],
                'before_revision':None,'after_revision':'sha256:'+rs._digest(record),'revision_kind':'owned-rewire-record'} for record in records)
    maintenance_warnings = []
    try:
        support = literature_support.for_node(project, claim, root)
    except Exception as exc:
        support = {'status':'UNAVAILABLE', 'reason':str(exc)}
        maintenance_warnings.append({'operation':'literature-support-read','reason':str(exc)})
    return 200, {'ok':True,'association':row,'claim':claim,'canonical_source':citation,'owned_changes':owned,
                 **({'source_effect':materialized_effect} if materialized_effect else {}),
                 'effects':['references','concepts','structure','research','pipeline']+(['manuscript'] if materialized else []),
                 'support':support, **({'maintenance_warnings':maintenance_warnings} if maintenance_warnings else {}),
                 'note':'Canonical source relation and passage provenance are joined; informal alignment remains authored.'}


def text(project, key, root, offset=0, limit=24000, source_index=0):
    if rs._KEY.fullmatch(key): return rs.extract_text(key, limit=limit, offset=offset)
    if not 0 <= offset <= 20_000_000 or not 1000 <= limit <= 48000:
        raise ValueError('Use nonnegative offset and limit from 1000 to 48000.')
    provider, item = resolve_item(project, key, root)
    if item is None: raise ValueError('Reference not found.')
    provenance = item.get('provenance') or {}
    if not provenance.get('path') and not provenance.get('original') and provider != 'canonical':
        return {'provider': provider, 'item': item, 'source_state': 'metadata-only', 'reason': 'No local source path; read the source before making a claim.'}
    path = (retained_original(project,{k:v for k,v in provenance['original'].items() if k!='project'},root)[1] if provenance.get('original') else canonical_source_path(project,item,root,source_index)[0] if provider == 'canonical' else local_path(provenance['path'], root, provenance.get('sha256')))
    if path.suffix.lower() == '.pdf':
        if not rs.shutil.which('pdftotext'):
            return {'provider': provider, 'item': item, 'source_state': 'metadata-only', 'reason': 'pdftotext unavailable'}
        run = rs.subprocess.run(['pdftotext', str(path), '-'], capture_output=True, text=True, timeout=20)
        if run.returncode: return {'provider': provider, 'item': item, 'source_state': 'extraction-failed', 'reason': run.stderr[-1200:]}
        content = run.stdout
    else:
        content = path.read_text(encoding='utf-8')
    passage = content[offset:offset+limit]
    return {'provider': provider, 'item': item, 'source_state': 'extracted', 'text': passage,
            'attachment': {'path': str(path), 'sha256': rs._sha256_file(path)},
            'offset': offset, 'next_offset': offset+len(passage) if len(content) > offset+limit else None,
            'truncated': len(content) > offset+limit, 'total_characters': len(content),
            'source_currentness': 'OBSERVED_NOW' if provider == 'canonical' else 'CURRENT' if rs._sha256_file(path) == provenance.get('sha256') else 'STALE',
            'reading_status': 'passage-returned; whole-source reading not established'}


def source_info(project, key, root, *, library=None, source_index=0):
    """Resolve only a reference identity, never a client-supplied filesystem path."""
    library = library or rs.Library()
    provider, item = resolve_item(project, key, root, library)
    if item is None: raise ValueError('Reference not found.')
    requested_key=key;key=str(item['key'])
    path = None
    manuscript=rs._manuscript(project,root)
    stored=next((row.get('source_text') for row in canonical_associations(rs._load_associations(manuscript),key=key) if row.get('key')==key and row.get('source_text')),None) if manuscript else None
    source_association=_resolve_row(rs._load_associations(manuscript),key) if manuscript else None
    original=(item.get('provenance') or {}).get('original')
    if original:
        if original.get('project')!=project:raise ValueError('Retained source provenance belongs to another project.')
        _original,path,_meta=retained_original(project,{k:v for k,v in original.items() if k!='project'},root)
    elif stored:
        path=local_path(stored['path'],root,stored.get('sha256'))
    elif rs._KEY.fullmatch(key) and provider not in ('local','crossref','canonical'):
        path = rs._attachment(library, item)
        if path is None and provider == 'api':
            try:
                local = library.sqlite.item(key)
                if local: path = rs._attachment(library, local)
            except (OSError, ValueError): pass
    elif provider == 'canonical':
        path, resolved = canonical_source_path(project,item,root,source_index)
    elif (item.get('provenance') or {}).get('path'):
        path = local_path(item['provenance']['path'], root, item['provenance'].get('sha256'))
    elif item.get('canonical_id'):
        canonical=canonical_item(project,item['canonical_id'],root)
        if canonical and canonical.get('source_refs'):
            path,_resolved=canonical_source_path(project,canonical,root,source_index)
            item={**item,'source_refs':canonical['source_refs']}
    kind = 'pdf' if path and path.suffix.lower() == '.pdf' else 'text' if path else None
    provenance = (item.get('provenance') or {}) if original else stored or item.get('provenance') or {}
    digest=rs._sha256_file(path) if path else None
    currentness = 'STALE' if path and provenance.get('sha256') and digest != provenance['sha256'] else 'CURRENT' if path else 'UNAVAILABLE'
    from laplace.research.literature_support import CLAIM_KINDS
    query = rs.urllib.parse.urlencode({'project':project,'key':key,'source_index':source_index})
    return {'provider':provider,'key':key,'requested_key':requested_key,'citekey':item.get('citation_key'),'available':bool(path),'kind':kind,'title':item.get('title'),
            'path':str(path) if path else None,'source_index':source_index,
            'sources':[{'index':i,'reference':ref,'label':str(ref.get('path') or ref) if isinstance(ref,dict) else str(ref)} for i,ref in enumerate(item.get('source_refs') or [])],
            'source_state':'local-source-available' if path else 'metadata-only','currentness':currentness,
            'pdf_url':'/references/source?' + query + '&format=pdf' if kind == 'pdf' else None,
            'text_url':'/references/text?' + query if path else None,
            'publisher_url':item.get('url') or ('https://doi.org/' + item['doi'] if item.get('doi') else None),
            'fulltext_candidates':[] if original else acquisition_candidates(item),
            **({'original':copy.deepcopy(original),'original_read':__import__('laplace.projects.material_intake',fromlist=['artifact_handle']).artifact_handle(project,{'id':original['artifact_id'],'expected_sha256':original['expected_sha256']},route='original')} if original else {}),
            'bibliography':bibliography_projection(project,root,item.get('citation_key'),key=key if original else None),
            **({'bibliography_follow_through':copy.deepcopy(source_association.get('bibliography_follow_through'))} if source_association and source_association.get('bibliography_follow_through') else {}),
            'acquisition_state':'RETAINED_ORIGINAL' if original else 'ACQUIRED_UNREAD' if stored else 'LOCAL_SOURCE_AVAILABLE' if path else 'METADATA_ONLY',
            'binding_contract':{'target_kinds':sorted(CLAIM_KINDS),'claim_read':'concept source_support.meaning_revision','meaning_guard':'claim_revision'},
            'reason':None if path else 'No local full text is available. Bibliographic metadata does not establish what the source proves.',
            'sha256':digest}, path


def handle(path, query, method, body, root=None):
    root = Path(root or rs._root()).resolve()
    project, key = rs._q1(query, 'project'), rs._q1(query, 'key')
    if path not in ('/references/item','/references/text','/references/fetch','/references/literature-scope','/references/source', '/references/literature-lookup', '/references/literature-import', '/references/literature-bind'):
        return None
    try:
        if path == '/references/literature-scope':
            from laplace.research.literature_support import scope
            if method!='GET':return rs._response(405,{'error':'GET only'})
            return rs._response(200,scope(project,root,node=rs._q1(query,'node'),task_id=rs._q1(query,'task_id'),offset=int(rs._q1(query,'offset') or 0),limit=int(rs._q1(query,'limit') or 40),as_of=rs._q1(query,'as_of')))
        if path == '/references/fetch':
            if method!='POST':return rs._response(405,{'error':'POST only'})
            payload=json.loads(body or b'{}')
            if not isinstance(payload,dict):raise ValueError('body must be an object')
            return rs._response(200,fetch_source(project or payload.get('project',''),payload,root))
        if path == '/references/text':
            if method!='GET':return rs._response(405,{'error':'GET only'})
            return rs._response(200,observe_read(project,key,root,int(rs._q1(query,'offset') or 0),int(rs._q1(query,'limit') or 24000),int(rs._q1(query,'source_index') or 0),
                query=rs._q1(query,'query'),expected_source_revision=rs._q1(query,'expected_source_revision')))
        if path == '/references/source':
            if method != 'GET': return rs._response(405, {'error':'GET only'})
            if rs._q1(query,'original'):
                if any(isinstance(v,(list,tuple)) and len(v)!=1 for v in query.values()):raise ValueError('Use one exact retained source query per field.')
                if key or set(query)-{'project','original'}:raise ValueError('Choose retained original or reference key, not mixed source coordinates.')
                return rs._response(200,retained_source(project,json.loads(rs._q1(query,'original')),root))
            info, local = source_info(project, key, root, source_index=int(rs._q1(query,'source_index') or 0))
            if rs._q1(query, 'format') == 'pdf':
                if not local or info['kind'] != 'pdf': return rs._response(404, {'error':'No local PDF is available for this reference.'})
                raw=local.read_bytes()
                if info.get('original') and 'sha256:'+rs.hashlib.sha256(raw).hexdigest()!=info['sha256']:raise ValueError('CHANGED_INPUT: retained PDF changed before retrieval.')
                return 200, 'application/pdf', raw
            return rs._response(200, info)
        if path in ('/references/literature-import', '/references/literature-bind'):
            if method != 'POST': return rs._response(405, {'error': 'POST only'})
            payload = json.loads(body or b'{}')
            if not isinstance(payload, dict): return rs._response(400, {'error': 'body must be an object'})
            if 'original' in payload and project and payload.get('project',project)!=project:raise ValueError('Retained source body and query name different projects.')
            project = project or payload.get('project', '')
            result = import_reference(project, payload, root) if path.endswith('import') else bind(project, payload, root)
            return rs._response(*result)
        if method != 'GET': return rs._response(405, {'error': 'GET only'})
        if path.endswith('literature-lookup'): return rs._response(200, lookup(rs._q1(query, 'doi')))
        if path.endswith('/text'):
            return rs._response(200, text(project, key, root, int(rs._q1(query, 'offset') or 0), int(rs._q1(query, 'limit') or 24000), int(rs._q1(query,'source_index') or 0)))
        provider, item = resolve_item(project, key, root)
        return rs._response(200, {'provider': provider, 'item': item, 'metadata_only': True}) if item else rs._response(404, {'error': 'reference not found'})
    except urllib.error.HTTPError as exc:
        fetching = path == '/references/fetch'
        return rs._response(404 if exc.code == 404 else 502, {
            'error': ('Full-text retrieval failed' if fetching else 'Crossref metadata lookup failed') + f' (HTTP {exc.code})',
            'provider_status': exc.code, 'retryable': exc.code != 404,
            **({'recovery': 'The imported reference is preserved. Supply another accessible full-text URL with the same key; do not reimport its metadata.'} if fetching else {})})
    except (urllib.error.URLError, TimeoutError) as exc:
        return rs._response(502, {'error': str(exc), 'retryable': True})
    except (ValueError, TypeError) as exc:
        from laplace.manuscript.source_effects import error_details
        details = error_details(exc)
        return rs._response(409 if details or str(exc).startswith('CHANGED_INPUT:') else 422,
                            {'error':str(exc), **details, **({'retryable':False} if details else {})})
    except OSError as exc:
        return rs._response(409, {'error': str(exc), 'retryable': True})


_EXTRACTION_CACHE=OrderedDict()
_EXTRACTION_LOCK=threading.RLock()
_EXTRACTION_CACHE_CHARACTERS=8_000_000


def _content(path, source_sha256=None):
    """Disposable derived text, qualified by source bytes and extractor identity."""
    path=Path(path);digest=source_sha256 or rs._sha256_file(path)
    tool=rs.shutil.which('pdftotext') if path.suffix.lower()=='.pdf' else None
    extractor=None
    if tool:
        try:stat=Path(tool).stat();extractor=(tool,stat.st_mtime_ns,stat.st_size)
        except OSError:extractor=(tool,None,None)
    key=(str(path.resolve()),digest,extractor,'utf8/pdftotext-v1')
    with _EXTRACTION_LOCK:
        if key in _EXTRACTION_CACHE:
            _EXTRACTION_CACHE.move_to_end(key);return _EXTRACTION_CACHE[key]
    content=_extract_content(path)
    if rs._sha256_file(path)!=digest:raise ValueError('Source changed during extraction; no mixed text was retained.')
    with _EXTRACTION_LOCK:
        if len(content)<=_EXTRACTION_CACHE_CHARACTERS:
            for old in [old for old in _EXTRACTION_CACHE if old[0]==key[0] and old!=key]:_EXTRACTION_CACHE.pop(old)
            _EXTRACTION_CACHE[key]=content
            while sum(len(value) for value in _EXTRACTION_CACHE.values())>_EXTRACTION_CACHE_CHARACTERS:_EXTRACTION_CACHE.popitem(last=False)
    return content


def _extract_content(path):
    if path.suffix.lower()=='.pdf':
        tool=rs.shutil.which('pdftotext')
        if not tool: raise ValueError('pdftotext unavailable; source is not recorded as read.')
        run=rs.subprocess.run([tool,str(path),'-'],capture_output=True,text=True,timeout=25)
        if run.returncode: raise ValueError('PDF extraction failed: '+run.stderr[-500:])
        return run.stdout
    if path.stat().st_size>16_000_000:raise ValueError('Source exceeds the bounded text reader.')
    return path.read_text(encoding='utf-8')


def observe_read(project,key,root,offset=0,limit=24000,source_index=0,*,persist=True,query='',expected_source_revision=''):
    if not 0<=offset<=20_000_000 or not 1000<=limit<=48000:raise ValueError('Use nonnegative offset and limit from 1000 to 48000.')
    info,path=source_info(project,key,root,source_index=source_index)
    key=info['key']
    if path is None:return {**info,'source_state':'metadata-only'}
    before=info['sha256']
    if expected_source_revision and not revision_matches(expected_source_revision,before):raise ValueError('CHANGED_INPUT: source changed between passages; inspect it again before continuing.')
    content=_content(path,before);hit=None
    if query:
        if not isinstance(query,str) or not 1<=len(query)<=256:raise ValueError('Use a source text query from1to256characters.')
        hit=re.search(re.escape(query),content[offset:],re.I)
        if hit is None:
            if rs._sha256_file(path)!=before:raise ValueError('Source changed while searching; inspect the current source.')
            return {**info,'source_state':'extracted','text':'','offset':offset,'total_characters':len(content),'query':query,'search_state':'NO_MATCH','next_offset':None,'query_next_offset':None}
        hit_start=offset+hit.start();hit_end=offset+hit.end();offset=max(0,hit_start-min(400,limit//4))
        hit={'character_start':hit_start,'character_end':hit_end,'locator':f'characters {hit_start}–{hit_end}'}
    fragment=content[offset:offset+limit]
    if not content.strip():return {**info,'source_state':'text-unavailable','reason':'No readable text was extracted. Inspect the original PDF; no text-reading receipt was created.'}
    if rs._sha256_file(path)!=before:raise ValueError('Source changed while reading; retry before binding.')
    if not fragment:
        return {**info,'source_state':'exhausted','text':'','offset':offset,'total_characters':len(content),
                'next_offset':None,'reason':'This offset is beyond the source text. No passage was returned and no reading receipt was created.'}
    receipt={'reference_key':key,'source_path':str(path),'source_sha256':before,'offset':offset,'length':len(fragment),
             'total_characters':len(content),'text_sha256':'sha256:'+rs.hashlib.sha256(fragment.encode()).hexdigest(),
             'locator':f'characters {offset}–{offset+len(fragment)}','source_index':source_index,
             'page_start':content.count('\f',0,offset)+1,'page_end':content.count('\f',0,offset+len(fragment))+1,
             'observation':'passage returned by reference_text; not independent comprehension or entailment'}
    if info.get('original'):receipt['original']=copy.deepcopy(info['original'])
    receipt['id']='READ-'+rs._digest(receipt)[:24]
    owned=None
    if persist:
        manuscript=rs._manuscript(project,root)
        if manuscript is None:raise ValueError('A project is required to retain this source reading observation.')
        from filelock import FileLock
        with FileLock(str(manuscript/'.references.lock'),timeout=15):
            rows=rs._load_associations(manuscript);before_rows=json.loads(json.dumps(rows));association_path=manuscript/rs._ASSOCIATIONS
            before_association=association_path.read_bytes() if association_path.is_file() else None
            rows=canonical_associations(rows,key=key)
            matched=[row for row in rows if row.get('key')==key]
            if not matched:
                provider,item=resolve_item(project,key,root)
                if item is None:raise ValueError('Reference identity is unavailable.')
                base=next((row for row in canonical_rows(project,root) if row.get('key')==key),None)
                base=dict(base) if base else {'key':key,'metadata':rs._metadata(item),'source':{'provider':provider},'state':'CURRENT','bibliography_state':'NOT_LINKED'}
                base.pop('claim_id',None);base.pop('canonical_relation',None);rows.append(base);matched=[base]
            base=next((row for row in matched if not row.get('claim_id')),None)
            if base is None:
                base={name:value for name,value in matched[0].items() if name not in {'claim_id','claim_revision','relation','rationale','evidence','reading_receipt','binding_state','canonical_records'}}
                rows.append(base)
            readings={item['id']:item for row in matched for item in row.get('reading_observations') or [] if item.get('id')}
            readings[receipt['id']]=receipt;base['reading_observations']=list(readings.values())
            if rows!=before_rows:rs._write_associations(manuscript,rows)
            owned=rs._owned_associations(root,manuscript,before_association,before_rows,rows,['references','research'])
    handles={'page_read':_reference_handle(project,key,'reference_text','/references/text',offset=offset,limit=limit,source_index=source_index,expected_source_revision=before),
        'read_handle':_reference_handle(project,key,'reference_text','/references/text',offset=offset+len(fragment),limit=limit,source_index=source_index,expected_source_revision=before) if offset+len(fragment)<len(content) else None,
        'restart_read':_reference_handle(project,key,'reference_text','/references/text',offset=0,limit=limit,source_index=source_index)}
    return {**info,**handles,**({'owned_changes':owned} if owned is not None else {}),'source_currentness':info.get('currentness'),'source_state':'extracted','text':fragment,'reading_receipt':receipt,
            **({'query':query,'search_state':'MATCH','hit':hit,'query_next_offset':hit['character_end']} if hit else {}),
            'attachment':{'path':str(path),'sha256':before},'offset':offset,
            'truncated':offset+len(fragment)<len(content),'next_offset':offset+len(fragment) if offset+len(fragment)<len(content) else None,
            'total_characters':len(content),'reading_status':'passage-observed'}


def _download(url):
    """Bound public full-text retrieval; redirects retain the same address fence."""
    import ipaddress,socket,os
    from urllib.parse import urlparse
    from urllib.request import Request,build_opener,HTTPRedirectHandler
    def validate(value):
        parsed=urlparse(value)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use a public HTTP(S) full-text URL without credentials.')
        if os.environ.get('LAPLACE_TEST_PROCESS')!='1':
            addresses=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80))
            if any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
                raise ValueError('Full-text retrieval requires a public source address.')
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            validate(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
    validate(url)
    with build_opener(Redirect()).open(Request(url,headers={'User-Agent':'Laplace source reader/1.0','Accept-Encoding':'identity'}),timeout=25) as response:
        validate(response.geturl());data=response.read(16_000_001)
        if len(data)>16_000_000:raise ValueError('Full text exceeds the 16 MB retrieval bound; choose a smaller source or a local copy.')
        return data,response.headers.get_content_type(),response.geturl()


def fetch_source(project,payload,root):
    key=str(payload.get('key') or '');url=str(payload.get('url') or '').strip()
    provider,item=resolve_item(project,key,root)
    if item is None:raise ValueError('Import or select an existing source identity before fetching full text.')
    key=str(item['key'])
    if (item.get('provenance') or {}).get('original'):raise ValueError('This source already names an exact retained original. Inspect it or explicitly import a different source; fetch cannot replace its original authority.')
    if payload.get('candidate_id'):
        chosen=next((choice for choice in acquisition_candidates(item) if choice['id']==payload['candidate_id']),None)
        if chosen is None:raise ValueError('The full-text candidate changed or is unavailable; inspect reference_source again.')
        if url and url!=chosen['url']:raise ValueError('candidate_id and URL do not identify the same full-text candidate.')
        url=chosen['url']
    if not url:
        choices=item.get('fulltext_urls') or []
        if len(choices)!=1:raise ValueError('Supply the exact accessible full-text URL; a DOI landing page is not assumed to be the full source.')
        url=choices[0]
    data,mime,final_url=_download(url)
    if data.startswith(b'%PDF-'):ext='.pdf';content=data
    elif mime in ('text/plain','text/x-tex','application/x-tex'):ext='.txt';content=data.decode('utf-8').encode()
    elif mime in ('text/html','application/xhtml+xml'):
        from html.parser import HTMLParser
        class Text(HTMLParser):
            def __init__(self):super().__init__();self.ignore=0;self.parts=[]
            def handle_starttag(self,tag,attrs):
                if tag in ('script','style','nav','noscript'):self.ignore+=1
                if tag in ('p','div','section','article','h1','h2','h3','br'):self.parts.append('\n')
            def handle_endtag(self,tag):
                if tag in ('script','style','nav','noscript') and self.ignore:self.ignore-=1
            def handle_data(self,text):
                if not self.ignore:self.parts.append(text)
        parser=Text();parser.feed(data.decode('utf-8',errors='replace'));plain='\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
        if len(plain)<100:raise ValueError('The fetched page has no usable source text; it has not been read.')
        ext='.txt';content=plain.encode()
    else:raise ValueError('Response is not a supported PDF or text document; source remains unread.')
    manuscript=rs._manuscript(project,root)
    if manuscript is None:raise ValueError('Unknown project source workspace.')
    directory=manuscript/'literature_sources';directory.mkdir(parents=True,exist_ok=True)
    digest='sha256:'+rs.hashlib.sha256(content).hexdigest();path=directory/(digest.split(':')[1]+ext)
    artifact_before=path.read_bytes() if path.is_file() else None
    if artifact_before is not None and artifact_before!=content:raise ValueError('Stored source bytes do not match their hash identity; the conflicting artifact was preserved.')
    if not path.exists():
        pending=path.with_suffix(path.suffix+'.pending');pending.write_bytes(content);pending.replace(path)
    observation={'path':str(path),'sha256':digest,'url':url,'resolved_url':final_url,'media_type':mime,'bytes':len(content),
                 'qualification':'ACQUIRED_UNREAD; publication identity and claim alignment still require source inspection'}
    from filelock import FileLock
    with FileLock(str(manuscript/'.references.lock'),timeout=15):
        rows=rs._load_associations(manuscript);before_rows=json.loads(json.dumps(rows));association_path=manuscript/rs._ASSOCIATIONS
        before_association=association_path.read_bytes() if association_path.is_file() else None
        rows=canonical_associations(rows,key=key)
        matched=[row for row in rows if row.get('key')==key]
        if not matched:
            row={'key':key,'metadata':rs._metadata(item),'source':{'provider':provider},'state':'CURRENT','bibliography_state':'NOT_LINKED'}
            rows.append(row);matched=[row]
        for row in matched:row['source_text']=observation
        rs._write_associations(manuscript,rows)
        owned=rs._owned_associations(root,manuscript,before_association,before_rows,rows,['references','research','pipeline'])
        if artifact_before!=content:owned['files'].append(rs._owned_file(root,path,artifact_before,content))
    return {'ok':True,'key':key,'source_text':observation,'owned_changes':owned,'next':'reference_text to inspect a bounded passage; acquisition alone is not reading or support.'}
