"""Read canonical source relationships and their observed passage provenance.

The graph owns claim/source relationships; references.json owns bibliographic and
reading observations. This projection creates neither a graph nor a truth ledger.
It deliberately never calls concept state or formal state, avoiding recursive
qualification reads.
"""
from __future__ import annotations
import hashlib,json
from functools import lru_cache
from pathlib import Path

CLAIM_KINDS={'theorem','lemma','result','intermediate-result','postulate','definition','derivation-step','claim','proposition','corollary','technique'}

def network(project,root):
    from laplace.research import corpus_ingest as ci
    tex=ci.resolve_corpus(root,project)
    return ci.corpus_network(tex,repo_root=root,name=project) if tex else {'nodes':{},'relations':[]}

@lru_cache(maxsize=128)
def _source_digest(path,mtime,ctime,size):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()

def receipt_current(receipt, *, project=None, root=None):
    if receipt.get('original'):
        if project is None or root is None:return False
        try:
            from laplace.research import literature
            original=receipt['original']
            if original.get('project')!=project:return False
            _original,path,_meta=literature.retained_original(project,{k:v for k,v in original.items() if k!='project'},root)
            return literature.rs._sha256_file(path)==receipt.get('source_sha256')
        except (OSError,ValueError,KeyError,TypeError):return False
    path=Path(str(receipt.get('source_path') or ''))
    try:
        stat=path.stat()
        return _source_digest(str(path),stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size)==receipt.get('source_sha256')
    except OSError:return False

def observed_passage(receipt):
    """A reading observation must include actual returned source characters."""
    offset,length,total=(receipt.get(key) for key in ('offset','length','total_characters'))
    return (all(isinstance(value,int) and not isinstance(value,bool) for value in (offset,length,total))
            and 0<=offset<total and 0<length<=total-offset)

def source_receipt_current(project,row,receipt,root):
    if not receipt_current(receipt,project=project,root=root):return False
    if (row.get('source') or {}).get('provider')!='canonical':return True
    from laplace.research import literature
    try:
        info,path=literature.source_info(project,row.get('key') or '',root,source_index=receipt.get('source_index',0))
        return (bool(path) and info.get('currentness')=='CURRENT'
                and receipt_current({'source_path':str(path),'source_sha256':receipt.get('source_sha256')}))
    except (OSError,ValueError,TypeError):return False


def citation_context(project,root,citations=None,*,structure=None,selected_source=None,
                     heading_spans_by_file=None):
    """Attribute exact citation occurrences to their canonical source sections."""
    from laplace.research import references_surface as rs
    from laplace.manuscript import project_structure, proposal_basis
    if citations is None:
        source,citations,_=rs.citation_spans(project,root)
        if selected_source is None:selected_source=source
    if structure is None:structure=project_structure.state(project,root)
    if selected_source is None:
        from laplace.manuscript import manuscript_source
        selected_source=manuscript_source.resolve(project,repo_root=root)
    if heading_spans_by_file is None:heading_spans_by_file={}
    placement_cache={}
    for span in citations:
        if 'claim_ids' in span:continue
        if str(span.get('text') or '').lstrip().startswith(r'\nocite'):
            span.update(claim_ids=[],section_ids=[],attribution='bibliography-only');continue
        sections,limits=proposal_basis._sections_for_edit(
            root,project,structure,span,selected_source=selected_source,
            heading_spans_by_file=heading_spans_by_file,placement_cache=placement_cache)
        span.update(section_ids=[section['id'] for section in sections],
                    claim_ids=list(dict.fromkeys(ident for section in sections for ident in list(section.get('node_ids') or [])+list(section.get('beat_ids') or []))),
                    attribution='canonical-section' if sections else 'unplaced',attribution_limits=limits)
    return citations


def meaning_revision(project,node_id,root,net=None,*,relations=None,read_context=None):
    """Proposition identity; placement, citation and engineering acknowledgement do not alter it."""
    from laplace.research import references_surface as rs, mathematical_records as mr
    net=net or network(project,root);nodes=net.get('nodes') or {};node=nodes.get(node_id) or {}
    def statement(value):
        mathematics=(value.get('projection') or {}).get('mathematics') or {}
        return {'kind':value.get('kind'),'meaning':value.get('essence'),
                'mathematics':{key:mathematics.get(key) for key in ('statement_tex','domain','assumptions','primary_source','sources')},
                'source_refs':value.get('source') or value.get('sources') or value.get('ref') or []}
    value=statement(node)
    # Code locators pin engineering inputs. They cannot provide a TeX statement;
    # don't read/allocate/hash entire source bodies merely to derive pure P.
    refs=value['source_refs'] if isinstance(value['source_refs'],list) else [value['source_refs']]
    def code_ref(ref):
        return Path(ref.get('path','') if isinstance(ref,dict) else str(ref)).suffix.lower() in {'.py','.js','.mjs','.ts','.rs','.go','.c','.cpp','.h'}
    textual_refs=[ref for ref in refs if not code_ref(ref)]
    code_only=bool(refs) and not textual_refs
    if not value['mathematics'].get('statement_tex') and value['source_refs'] and node.get('kind') in mr.KINDS and code_only:
        value['resolved_statement']=None;value['source_variants']=[]
    elif not value['mathematics'].get('statement_tex') and value['source_refs'] and node.get('kind') in mr.KINDS:
        semantic_node=node
        if len(textual_refs)!=len(refs):
            semantic_node={**node,'source':textual_refs,'sources':[],'ref':[]}
            projection=dict(node.get('projection') or {});mathematics=dict(projection.get('mathematics') or {})
            if 'sources' in mathematics:mathematics['sources']=[ref for ref in mathematics['sources'] if not code_ref(ref)]
            projection['mathematics']=mathematics;semantic_node['projection']=projection
        resolved=mr.read(project,node_id,semantic_node,root,include_verification=False,read_context=read_context)
        value['resolved_statement']=resolved.get('statement_tex')
        value['source_variants']=[source.get('statement_tex') for source in resolved.get('source_ambiguity') or []]
    value['premises']={relation['target']:statement(nodes.get(relation['target']) or {}) for relation in (relations if relations is not None else net.get('relations') or [])
                       if relation.get('source')==node_id and relation.get('rel')=='prerequisite'}
    return 'sha256:'+rs._digest(value)


def _scope_inputs(project,root,read_context,*,network_snapshot=None):
    """An ephemeral owner snapshot shared only within one caller's read request."""
    from laplace.research import references_surface as rs
    from laplace.manuscript import manuscript_source
    from laplace.research import research_context, research_records
    from laplace.pipeline import visual_production
    key=('literature-support',str(root),project)
    if key in read_context:return read_context[key]
    source,citations,traversal=rs.citation_spans(project,root)
    net=network_snapshot if network_snapshot is not None else network(project,root)
    manuscript=Path(manuscript_source.project_state_dir(source,root)) if source.get('manuscript_dir') else rs._manuscript(project,root)
    if manuscript is not None and not manuscript.is_absolute():manuscript=root/manuscript
    associations=rs._load_associations(manuscript) if manuscript else []
    item,store=research_context.project(project,root)
    project_root=research_context.project_root(item,root) if item else None
    records=research_records._records(store) if store else ([],None)
    try:visual_specs=visual_production.load(store).get('specs') or [] if store else []
    except (OSError,ValueError,TypeError):visual_specs=[]
    relations={};by_source={}
    for relation in net.get('relations') or []:relations.setdefault(relation.get('source'),[]).append(relation)
    for row in associations:
        for ident in dict.fromkeys([row.get('canonical_id'),row.get('key')]):
            if ident:by_source.setdefault(ident,[]).append(row)
    context={'source':source,'citations':citations,'traversal':traversal,'net':net,
             'manuscript':manuscript,'associations':associations,'relations_by_source':relations,
             'associations_by_source':by_source,'support_by_node':{},'heading_cache':{},
             'research_store':store,'research_project_root':project_root,'research_records_snapshot':records,
             'research_run_cache':{},'research_digest_cache':{},'research_visual_specs':visual_specs,
             'research_bindings_by_id':{},'research_observed_ids':set(),'scopes':{}}
    read_context[key]=context
    return context


def _context_result_bindings(context,ids):
    from laplace.research import research_context, research_records
    ids=list(dict.fromkeys(ids));rows,error=context['research_records_snapshot']
    if error:return {'status':'UNRESOLVED','bindings':[],'gaps':[error]}
    missing=[ident for ident in ids if ident not in context['research_observed_ids']]
    if missing and context['research_store']:
        observed=research_records.result_bindings(context['research_store'],missing,
            context['research_project_root'],records_snapshot=context['research_records_snapshot'],
            run_cache=context['research_run_cache'],digest_cache=context['research_digest_cache'],
            visual_specs=context['research_visual_specs'])
        context['research_bindings_by_id'].update({row['id']:row for row in observed['bindings']})
    context['research_observed_ids'].update(missing)
    bindings=[];gaps=[]
    for ident in ids:
        row=context['research_bindings_by_id'].get(ident)
        if row is None:gaps.append('linked research result is unresolved: '+ident)
        else:
            bindings.append(row)
            if row['currentness']!='CURRENT':gaps.append('linked research result is '+row['currentness'].lower()+': '+ident)
    return {'status':'CURRENT' if not gaps else 'UNRESOLVED','bindings':bindings,'gaps':gaps}


def for_node(project,node_id,root,*,net=None,associations=None,citations=None,
             research_records_snapshot=None,research_store=None,
             research_project_root=None,research_currentness_snapshot=None,
             research_run_cache=None,research_digest_cache=None,
             research_visual_specs=None,support_context=None,source_record=None,read_context=None):
    from laplace.research import references_surface as rs
    root=Path(root).resolve();net=net or network(project,root);nodes=net.get('nodes') or {};node=nodes.get(node_id) or {}
    read_context=(support_context.setdefault('engineering_read_context', {}) if support_context is not None else {}) if read_context is None else read_context
    cached=(support_context or {}).get('support_by_node',{})
    if node_id in cached:return cached[node_id]
    if associations is None:
        manuscript=rs._manuscript(project,root)
        rows=rs._load_associations(manuscript) if manuscript else []
    else:rows=associations
    if citations is not None and any('claim_ids' not in span for span in citations):citation_context(project,root,citations)
    if support_context is not None and 'citations_by_claim_key' not in support_context:
        indexed={}
        for span in citations or []:
            for ident in span.get('claim_ids') or []:indexed.setdefault((ident,span.get('citekey')),[]).append(span)
        support_context['citations_by_claim_key']=indexed
    relations=(support_context or {}).get('relations_by_source',{}).get(node_id) if support_context is not None else None
    claim_revision=meaning_revision(project,node_id,root,net,relations=relations,read_context=read_context)
    links=[];gaps=[]
    for relation in (relations if relations is not None else net.get('relations') or []):
        if relation.get('source')!=node_id or relation.get('rel') not in {'support','validated_by','counterevidence','analogy'}:continue
        source_id=relation.get('target');source=nodes.get(source_id) or {}
        if source.get('kind')!='citation':continue
        candidates=(support_context['associations_by_source'].get(source_id,[]) if support_context is not None else
                    [row for row in rows if row.get('canonical_id')==source_id or row.get('key')==source_id])
        bound=next((row for row in reversed(candidates) if row.get('claim_id')==node_id),None)
        metadata=bound or next(iter(candidates),{})
        receipt=(bound or {}).get('reading_receipt') or {}
        state='UNASSESSED'
        if bound and bound.get('binding_state')=='PENDING_CANONICAL':state='PENDING_CANONICAL'
        elif receipt and not observed_passage(receipt):state='NO_PASSAGE_OBSERVED'
        elif receipt and (not source_receipt_current(project,bound,receipt,root) or (bound.get('source_text') or {}).get('sha256') not in (None,receipt.get('source_sha256'))):state='STALE'
        elif bound and bound.get('binding_state')=='BOUND' and receipt:
            state='CLAIM_CHANGED' if bound.get('claim_revision') and bound['claim_revision']!=claim_revision else 'PASSAGE_OBSERVED'
        citekey=metadata.get('citekey');uses=(support_context['citations_by_claim_key'].get((node_id,citekey),[]) if support_context is not None else
            [span for span in citations or [] if span.get('citekey')==citekey and node_id in span.get('claim_ids',[])]) if citekey else []
        entry={'source_id':source_id,'key':metadata.get('key') or source_id,'label':(metadata.get('metadata') or {}).get('title') or source.get('essence') or source_id,
               'relation':relation.get('rel'),'rationale':relation.get('rationale') or (bound or {}).get('rationale'),
               'qualification':state,'bound_claim_revision':(bound or {}).get('claim_revision'),'current_claim_revision':claim_revision,'reading_receipt':receipt or None,'citekey':citekey,'manuscript_uses':uses,
               'source_refs':source.get('source') or source.get('ref') or [],'informal_alignment':'AUTHORED_NOT_INDEPENDENTLY_VERIFIED'}
        links.append(entry)
        if relation.get('rel') in {'support','validated_by','counterevidence'} and state!='PASSAGE_OBSERVED':gaps.append({'kind':'source-not-qualified','source_id':source_id,'state':state})
        if relation.get('rel') in {'support','validated_by','counterevidence'} and (not citekey or citations is not None and not uses):gaps.append({'kind':'not-yet-cited','source_id':source_id,'citekey':citekey})
    own=[];declared=list((node.get('projection') or {}).get('result_bindings') or [])
    if declared:
        from laplace.research import research_context, research_records
        if research_store is None:
            record,research_store=research_context.project(project,root)
            research_project_root=research_context.project_root(record,root) if record else None
        observed=(_context_result_bindings(support_context,[row['id'] for row in declared if row.get('id')]) if support_context is not None else research_records.result_bindings(
            research_store,[row['id'] for row in declared if row.get('id')],
            research_project_root,records_snapshot=research_records_snapshot,
            currentness_snapshot=research_currentness_snapshot,
            run_cache=research_run_cache,digest_cache=research_digest_cache,
            visual_specs=research_visual_specs)
            if research_store else {'bindings':[]})
        indexed={row['id']:row for row in observed.get('bindings') or []}
        for binding in declared:
            live=indexed.get(binding.get('id')) or {}
            current=live.get('currentness')=='CURRENT' and live.get('revision')==binding.get('revision')
            own.append({**binding,'current_revision':live.get('revision'),'currentness':'CURRENT' if current else 'STALE_OR_UNRESOLVED'})
            if not current:gaps.append({'kind':'own-evidence-stale','id':binding.get('id'),'expected_revision':binding.get('revision'),'current_revision':live.get('revision')})
    if source_record is None and (node.get('source') or node.get('sources') or node.get('ref')):
        from laplace.research import mathematical_records as mr
        if node.get('kind') in mr.PROOF_KINDS:
            source_record=mr.read(project,node_id,node,root,include_verification=False,read_context=read_context)
    if source_record is not None and source_record.get('node')!=node_id:
        raise ValueError('Source record belongs to another claim')
    from laplace.research import engineering_support
    engineering = engineering_support.observe(project, node_id, root, net,
        read_context=read_context)
    if engineering['status'] == 'REVIEW_REQUIRED':
        gaps.extend({'kind':'engineering-support-not-current', 'work_id':row.get('work_id'),
                     'covered_scope':row.get('covered_scope'), 'state':row.get('status'),
                     'reason':row.get('reason'), 'read_handle':row.get('read_handle')}
                    for row in engineering['bindings'])
        if not engineering['bindings']:
            gaps.append({'kind':'engineering-support-malformed','reason':engineering['reason']})
    authored=((node.get('projection') or {}).get('mathematics') or {}).get('proof') or {}
    proof={'text':authored.get('text') or '', 'status':'AUTHORED_UNREVIEWED' if authored.get('text') else 'NOT_RECORDED'}
    if not proof['text'] and (node.get('source') or node.get('sources') or node.get('ref')):
        from laplace.research import mathematical_records as mr
        if node.get('kind') in mr.PROOF_KINDS:
            proof=(source_record or mr.read(project,node_id,node,root,include_verification=False,read_context=read_context)).get('proof') or proof
    declared_role='DECLARED_ASSUMPTION' if node.get('kind') in {'postulate','assumption'} else 'DECLARED_DEFINITION' if node.get('kind') in {'definition','def'} else None
    if node.get('kind') in CLAIM_KINDS and not any(link['relation'] in {'support','validated_by','counterevidence'} for link in links) and not any(row['currentness']=='CURRENT' for row in own) and not proof.get('text') and not declared_role:
        gaps.append({'kind':'unsupported','node_id':node_id,'note':'No canonical external support, current own result or documented proof is recorded.'})
    # `meaning_revision` names the `claim-meaning` home.  It is a row of
    # identity_doors.RETAINED ("concept.source_support.meaning_revision") with its live
    # consumer -- literature.py:394-396, a door the identity-tokens lane did NOT convert --
    # and that register's dated expiry.  No token is published here BECAUSE no door here was
    # converted: the expiry is the review date for the lane that converts literature_bind,
    # and the register says so in its own `deletes` cell rather than leaving a reader to guess.
    result={'node':node_id,'meaning_revision':claim_revision,'citation_assessment':'CANONICAL_SECTIONS' if citations is not None else 'NOT_REQUESTED','sources':links,'own_evidence':own,'authored_proof':bool(authored.get('text')),
            'documented_proof':{key:proof.get(key) for key in ('status','source')},'declared_role':declared_role,
            'gaps':gaps,'qualification':'OPEN' if any(gap['kind']!='not-yet-cited' for gap in gaps) else declared_role or 'AUTHORED_BASIS',
            'independent_verification':'NOT_ASSERTED', 'engineering_support':engineering}
    if support_context is not None:support_context['support_by_node'][node_id]=result
    return result


def bibliography_observation(project,root,source):
    from laplace.manuscript import projection_viewer
    import re
    main=Path(source.get('root') or '')
    if not main.is_absolute():main=root/main
    if not main.is_file():return {'current':False,'reason':'No selected manuscript root','rendered_keys':[]}
    pdf=main.with_suffix('.pdf');keys=set();visited=set();parsed_pins={}
    def read_output(path):
        relative=path.relative_to(root).as_posix()
        try:
            data=path.read_bytes()
        except OSError:
            parsed_pins[relative]=None
            return None
        # The proof must cover the bytes parsed, not a later reread of the path.
        parsed_pins[relative]=hashlib.sha256(data).hexdigest()
        return data.decode('utf-8',errors='replace')
    def read_aux(path):
        path=path.resolve()
        if path in visited or path.suffix!='.aux' or not path.is_relative_to(main.parent.resolve()):return
        visited.add(path);text=read_output(path)
        if text is None:return
        keys.update(re.findall(r'\\bibcite\s*\{([^}]+)\}',text))
        keys.update(re.findall(r'\\abx@aux@cite\{[^}]*\}\{([^}]+)\}',text))
        for name in re.findall(r'\\@input\{([^}]+)\}',text):read_aux(main.parent/name)
    read_aux(main.with_suffix('.aux'))
    bbl=main.with_suffix('.bbl');rendered=set()
    text=read_output(bbl)
    if text is not None:
        rendered.update(re.findall(r'\\bibitem(?:\[[^]]*\])?\s*\{([^}]+)\}',text))
        rendered.update(re.findall(r'\\entry\s*\{([^}]+)\}',text))
    keys &= rendered
    # Read the same owner proof used by HTTP/native build_status after inspecting
    # aux/bbl. Changed or legacy output bytes are observations, never render proof.
    status=projection_viewer.recompile_status(main.relative_to(root).as_posix(),repo_root=root)
    pins=(status.get('outputs') or {}).get('files') or {}
    mismatches=sorted(path for path,digest in parsed_pins.items()
                      if path not in pins or pins[path]!=digest)
    current=bool(status.get('fresh') and not mismatches)
    return {'current':current,'reason':('Bibliography outputs changed while being read; inspect the current build again.'
            if mismatches and status.get('fresh') else status.get('reason')),
            'rendered_keys':sorted(keys) if current else [],
            'observed_keys':sorted(keys),'render_observation':'AUX_CITATION_AND_BBL_ENTRY; verified successful build outputs required',
            'bibliography_output_sha256':pins.get(bbl.relative_to(root).as_posix()) if current else None,
            'changed_inputs':status.get('dependency_changes') or [],
            'changed_outputs':sorted(set(status.get('output_changes') or [])|set(mismatches)),
            'output_proof':'READ_CHANGED' if mismatches and status.get('fresh') else status.get('output_proof','UNAVAILABLE'),'pdf':str(pdf),
            'pdf_sha256':pins.get(pdf.relative_to(root).as_posix()) if current else None,
            'source_receipt':str(projection_viewer._recompile_status_path(main))}



def scope(project,root,node='',include_dependencies=True,offset=0,limit=40,task_id='',*,read_context=None,as_of=''):
    from laplace.research import references_surface as rs
    from laplace.manuscript import manuscript_source
    from laplace.work import project_work
    from laplace.pipeline import citation_direction as cd
    root=Path(root).resolve();context=_scope_inputs(project,root,{} if read_context is None else read_context)
    net=context['net'];nodes=net.get('nodes') or {}
    task=None
    if task_id:
        task=project_work._tasks(project,root).get(task_id)
        if not task:raise ValueError('Unknown project task.')
        target=task.get('logical_target') or {}
        if not node and target.get('kind') not in (None,'node','project'):
            raise ValueError('This task targets a relation or another scope; supply the intended canonical node explicitly instead of widening to the project.')
        if not node and target.get('kind')=='node' and not target.get('node_id'):raise ValueError('Task node scope is missing node_id.')
        node=node or target.get('node_id') or ''
    if node and node not in nodes:raise ValueError('Unknown canonical scope node.')
    scope_key=(node,bool(include_dependencies),offset,limit)
    if scope_key in context['scopes']:
        cached=context['scopes'][scope_key]
        if as_of and as_of!=cached['revision']:raise ValueError('CHANGED_INPUT: literature coverage changed; refresh this scope before paging.')
        return {**cached,'task_id':task_id or None}
    adjacency={ident:[] for ident in nodes}
    for ident,value in nodes.items():
        if value.get('parent') in adjacency:adjacency[value['parent']].append(ident)
    if include_dependencies:
        for relation in net.get('relations') or []:
            if relation.get('rel')=='prerequisite' and relation.get('source') in adjacency:adjacency[relation['source']].append(relation.get('target'))
    ids=set(nodes) if not node else {node};front=list(ids)
    while front:
        for ident in adjacency.get(front.pop(),[]):
            if ident in nodes and ident not in ids:ids.add(ident);front.append(ident)
    claims=[ident for ident in sorted(ids) if nodes[ident].get('kind') in CLAIM_KINDS]
    manuscript=context['manuscript'];rows=context['associations'];source=context['source'];spans=context['citations']
    if 'structure' not in context:
        from laplace.manuscript import project_structure
        context['structure']=project_structure.state(project,root,support_context=context)
    spans=citation_context(project,root,spans,structure=context['structure'],selected_source=source,
                           heading_spans_by_file=context['heading_cache'])
    _context_result_bindings(context,[row['id'] for ident in claims for row in
        (nodes[ident].get('projection') or {}).get('result_bindings') or [] if row.get('id')])
    all_rows=[]
    for ident in claims:
        support=for_node(project,ident,root,net=net,associations=rows,citations=spans,
            research_store=context['research_store'],research_project_root=context['research_project_root'],support_context=context)
        all_rows.append({'id':ident,'label':nodes[ident].get('label') or nodes[ident].get('essence') or ident,'kind':nodes[ident].get('kind'),**support})
    intents=[]
    for row in all_rows:
        if not any(gap['kind'] in {'unsupported','source-not-qualified'} for gap in row['gaps']):continue
        key=next((link.get('citekey') for link in row['sources'] if link.get('citekey')), '')
        intents.append(cd.LiteratureIntent(id='RI-LIT-'+rs._digest(row['id'])[:16],key=key,
            claim=str(nodes[row['id']].get('essence') or ''),claim_node=row['id'],source='canonical-scope',
            lane='verification' if key else 'dangling').as_dict())
    offset=max(0,int(offset));limit=max(1,min(100,int(limit)));page=all_rows[offset:offset+limit]
    gaps=[{'node_id':row['id'],**gap} for row in all_rows for gap in row['gaps']]
    if not claims:gaps.append({'kind':'no-canonical-claims','note':'The selected scope has no canonical claims to acquire or qualify; create or select the intended claim before declaring this workflow complete.'})
    if 'bibliography' not in context:context['bibliography']=bibliography_observation(project,root,source)
    compiled=context['bibliography']
    revision='sha256:'+rs._digest({'nodes':{ident:nodes[ident] for ident in claims},'source_revision':source.get('revision'),'support':all_rows,'bibliography':compiled})
    if as_of and as_of!=revision:raise ValueError('CHANGED_INPUT: literature coverage changed; refresh this scope before paging.')
    required_keys={link['citekey'] for row in all_rows for link in row['sources'] if link.get('citekey') and link['relation'] in {'support','validated_by','counterevidence'}}
    for key in sorted(required_keys-set(compiled['rendered_keys'])):gaps.append({'kind':'citation-not-rendered','citekey':key})
    if required_keys and not compiled['current']:gaps.append({'kind':'bibliography-build-not-current','reason':compiled.get('reason')})
    completion_evidence=[]
    for value in [source.get('root'),compiled.get('pdf'),compiled.get('source_receipt')]:
        if not value:continue
        path=Path(value);path=path if path.is_absolute() else root/path
        if path.is_file() and path.resolve().is_relative_to(root):completion_evidence.append(str(path.resolve().relative_to(root)))
    result={'project':project,'node':node or None,'task_id':task_id or None,'revision':revision,'claims':page,
            'intents':intents[offset:offset+limit],'pagination':{'offset':offset,'limit':limit,'total':len(claims),'next_offset':offset+len(page) if len(claims)>offset+len(page) else None},
            'gaps':gaps[:200],'gaps_omitted':max(0,len(gaps)-200),'ready_for_completion':not gaps and bool(claims),
            'attribution_limits':'Citation occurrences are attributed to canonical sections; this does not establish paragraph-level entailment for every claim in the section.',
            'source_revision':source.get('revision'),'source_root':source.get('root'),'bibliography':compiled,'completion_evidence':completion_evidence,
            'existing_owners':{'process':'task/task_status, logical_target.node_id','intents':'citation_direction.LiteratureIntent','relationships':'canonical citation nodes and typed edges','metadata_and_read_observations':'references.json'},
            'next':'Read existing sources first; fetch accessible full text if needed, inspect exact passages, bind to canonical claims, place citekeys in the selected manuscript, build, and re-read this coverage before task completion.'}
    context['scopes'][scope_key]=result
    return result
