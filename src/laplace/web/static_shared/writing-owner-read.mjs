// OWNER READ COORDINATES. Purpose: pure parsing and admission of the reading routes the human
// surfaces open (artifact, concept, structure, work, profile, material, help, recovery, passage
// history) so a link is opened only when its owner, project and selector are exactly what the
// owner publishes. Ownership: every route's path fence, currentness and action authority stay
// with the backend owner; this module admits coordinates and never resolves a label into a
// destination. Public contract: artifactHumanTarget, conceptHumanTarget, ownerHumanTarget,
// isKnownArtifactReadRoute, isKnownOwnerReadRoute, currentHelpRead, recordedRecoveryRead,
// passageHistoryRead, passageProvenancePresentation, qualifiedOwnerHTTP, passageContinuationURL, continuityRequest.
// A Work continuity read (/work/state view continuity) is typed only under the Work owner's closed request contract.
// Inputs: URLs or handles; outputs: typed targets or null (refusal). Structure reads admit
// view summary/detail/plan/full/outline/restructure/delivery/architecture-profile, projection
// guard (one subject) or display, exactly one canonical section_ids entry under a projection.
// Storage: none.
import {validDerivedTarget,sameDerivedTarget,validBuildJob,sameBuildJob,validBuildTarget,sameBuildTarget,validTemplateCandidateRef,validTemplatePreviewRef} from './derived-output.mjs';
// Pure transport coordinates for existing reading owners. Backend owners retain
// path fences, source/currentness and action authority. Shared by conversation,
// Markdown/artifact and manuscript links; malformed known routes stay refused.
export function artifactHumanTarget(raw,{project,base=globalThis.location?.href||'http://localhost/'}={}){
  try{const url=new URL(raw,base);if(url.origin!==new URL(base).origin||url.pathname!=='/research/artifact'||url.hash||url.username||url.password)return null;
    const q=url.searchParams;if(q.get('project')!==project||!['project','manuscript'].includes(q.get('scope')))return null;
    if([...q.keys()].some(key=>!['project','path','scope','artifact_id','expected_sha256','owner'].includes(key)||q.getAll(key).length!==1))return null;
    const artifactOwner=q.get('owner');if(artifactOwner&&artifactOwner!=='writing-artifact')return null;
    const path=q.get('path'),artifactId=q.get('artifact_id'),pin=q.get('expected_sha256');
    if(!path||path.startsWith('/')||path.includes('\\')||path.split('/').includes('..')||/[\u0000-\u001f]/.test(path)||q.has('owner')&&!artifactOwner||q.has('artifact_id')&&!artifactId||q.has('expected_sha256')&&!pin||pin&&!/^(?:sha256:)?[a-fA-F0-9]{64}$/.test(pin)||artifactId&&!/^ART-[a-zA-Z0-9-]+$/.test(artifactId))return null;
    return {path,scope:q.get('scope'),...(artifactOwner?{artifactOwner}:{}),...(pin?{expectedSha256:pin}:{}),...(artifactId?{artifactId}:{})};
  }catch{return null;}
}
export function conceptHumanTarget(raw,{base=globalThis.location?.href||'http://localhost/'}={}){
  try{const url=new URL(raw,base),q=url.searchParams;
    const scope=q.has('project')?'project':'corpus';
    if(url.origin!==new URL(base).origin||!['/concepts/state','/concepts/context'].includes(url.pathname)||url.hash||q.has('project')&&q.has('corpus')||
       [...q.keys()].some(key=>!['project','corpus','node'].includes(key))||
       [scope,'node'].some(key=>q.getAll(key).length!==1||!q.get(key)?.trim()))return null;
    const project=q.get(scope),node=q.get('node');
    return {project,node,href:'/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:'argument',node})};
  }catch{return null;}
}
// Transport coordinates only. The existing backend owners retain target/path
// validation, source/currentness and all action authority. Known malformed owner
// routes must never become filenames under the active project.
const HELP_SELECTOR_FIELDS=['operation','concept','variant','context','door','route','method','http_operation'];
const READING_OWNERS=new Set(['/work/profiles','/work/state','/work/structure','/work/style/pdf','/projects/material-references','/concepts/state','/concepts/context','/authoring/history','/authoring/help','/references/attached','/research/result','/authoring/document','/authoring/build']);
function localReadingURL(raw,base){
  if(typeof raw!=='string'||!(/^(?:https?:\/\/|\/)/i.test(raw)))return null;
  try{const url=new URL(raw,base);return url.origin===new URL(base).origin?url:null;}catch{return null;}
}
// The closed request of the Work view continuity (project_work_continuity.contract): part summary|completion|preflight,
// intent_id CI-<24 hex>, as_of a sha256 pin, payload an object; completion requires intent_id and preflight requires payload.
const CONTINUITY_PARTS=['summary','completion','preflight','subject'];
// part subject: exactly project_work_continuity.subject_page_schema (one recorded subject section page of one handoff).
const SUBJECT_SECTIONS=['changed_files','hunks','readonly_carry','effects','inputs','initial_reads'];
function subjectPagePayload(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!['phase_id','section','path','obligation_id','offset','limit','cut','item_sha256','item_offset'].includes(key)))return false;
  const count=(v,min,max)=>Number.isInteger(v)&&v>=min&&(max===undefined||v<=max);
  // issued continuations: the section cut a page series is pinned to, and a NOT_EXPANDED row's exact descent (both or neither)
  const pin=v=>v===undefined||typeof v==='string'&&/^sha256:[0-9a-f]{64}$/.test(v);
  if(!pin(value.cut)||!pin(value.item_sha256)||(value.item_sha256===undefined)!==(value.item_offset===undefined)||
     value.item_offset!==undefined&&!count(value.item_offset,0))return false;
  return typeof value.phase_id==='string'&&/^PHASE-[A-Za-z0-9._:-]{1,96}$/.test(value.phase_id)&&SUBJECT_SECTIONS.includes(value.section)&&
    (value.path===undefined||typeof value.path==='string'&&value.path.length>=1&&value.path.length<=400)&&
    (value.obligation_id===undefined||typeof value.obligation_id==='string'&&value.obligation_id.length>=1&&value.obligation_id.length<=96)&&
    (value.offset===undefined||count(value.offset,0))&&(value.limit===undefined||count(value.limit,1,256))&&
    (value.section!=='hunks'||value.path!==undefined)&&(!['inputs','initial_reads'].includes(value.section)||value.obligation_id!==undefined);
}
export function continuityRequest(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!['part','intent_id','as_of','payload'].includes(key)))return null;
  if(value.part!==undefined&&!CONTINUITY_PARTS.includes(value.part)||
     value.intent_id!==undefined&&!(typeof value.intent_id==='string'&&/^CI-[0-9a-f]{24}$/.test(value.intent_id))||
     value.as_of!==undefined&&!(typeof value.as_of==='string'&&/^sha256:[0-9a-f]{64}$/.test(value.as_of))||
     value.payload!==undefined&&!(value.payload&&typeof value.payload==='object'&&!Array.isArray(value.payload))||
     value.part==='completion'&&value.intent_id===undefined||value.part==='preflight'&&value.payload===undefined||
     value.part==='subject'&&!subjectPagePayload(value.payload))return null;
  return value;
}
export function ownerHumanTarget(raw,{base=globalThis.location?.href||'http://localhost/'}={}){
  const url=localReadingURL(raw,base);if(!url||url.hash||url.username||url.password)return null;const q=url.searchParams;
  const unique=allowed=>[...q.keys()].every(key=>allowed.includes(key)&&q.getAll(key).length===1);
  const text=key=>typeof q.get(key)==='string'&&!!q.get(key).trim()&&!/[\u0000-\u001f]/.test(q.get(key));
  const integer=(key,max)=>!q.has(key)||/^\d+$/.test(q.get(key))&&Number.isSafeInteger(Number(q.get(key)))&&Number(q.get(key))<=(max??1e9);
  const http={method:'GET',url:url.pathname+url.search};
  if(['/concepts/state','/concepts/context'].includes(url.pathname)){const target=conceptHumanTarget(raw,{base});return target?{kind:'concept',...target,http}:null;}
  if(url.pathname==='/research/result'){
    if(!unique(['project','id'])||!text('project')||!text('id'))return null;
    return {kind:'research-result',project:q.get('project'),id:q.get('id'),http,href:http.url};
  }
  if(url.pathname==='/authoring/document'){
    if(['template','template-candidates'].includes(q.get('view'))){
      if(!unique(['project','view','candidate_ref','preview_ref','part','file','offset','limit','page'])||!text('project')||!integer('offset')||!integer('limit',8000)||q.has('limit')&&Number(q.get('limit'))<1)return null;
      const project=q.get('project'),view=q.get('view'),part=q.get('part')||'metadata',payload={view};let ref=null,proof=null;
      if(view==='template-candidates'){
        if(['candidate_ref','preview_ref','part','file','page'].some(key=>q.has(key)))return null;
      }else{
        try{ref=JSON.parse(q.get('candidate_ref'));if(q.has('preview_ref'))proof=JSON.parse(q.get('preview_ref'));}catch{return null;}
        if(q.has('part')&&!text('part')||q.has('preview_ref')&&!validTemplatePreviewRef(proof,project,ref)||!validTemplateCandidateRef(ref)||!['metadata','original','proposed','diff','closure','diagnostics','preview-output','preview-image'].includes(part))return null;
        payload.candidate_ref=ref;if(q.has('part'))payload.part=part;
        if(proof){if(!validTemplatePreviewRef(proof,project,ref)||!['metadata','preview-output','preview-image'].includes(part))return null;payload.preview_ref=proof;}
        if(['preview-output','preview-image'].includes(part)){
          if(!proof||['file','offset','limit'].some(key=>q.has(key))||part==='preview-image'&&(!integer('page')||Number(q.get('page'))<1)||part==='preview-output'&&q.has('page'))return null;
          if(part==='preview-image')payload.page=Number(q.get('page'));
        }else{
          if(q.has('page')||part==='metadata'&&['file','offset','limit'].some(key=>q.has(key)))return null;
          if(['original','proposed','diff'].includes(part)){
            const file=q.get('file');if(!file||file.startsWith('/')||file.includes('\\')||file.split('/').includes('..')||/[\u0000-\u001f]/.test(file))return null;payload.file=file;
          }else if(q.has('file'))return null;
        }
      }
      for(const key of ['offset','limit'])if(q.has(key))payload[key]=Number(q.get(key));
      return {kind:view==='template'?'template-candidate':'template-candidates',project,view,part,candidateRef:ref,previewRef:proof,http,
        read_handle:{operation:'document',payload},href:'/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:'manuscript'})};
    }
    if(!unique(['project','target_kind'])||!text('project')||q.has('target_kind')&&!['manuscript','derived'].includes(q.get('target_kind')))return null;
    const project=q.get('project'),derived=q.get('target_kind')==='derived';
    return {kind:derived?'derived-output':'manuscript-document',project,http,
      href:'/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:derived?'presentation':'manuscript'})};
  }
  if(url.pathname==='/work/style/pdf'){
    if(!unique(['project','candidate_ref','preview_ref','format','page'])||!text('project'))return null;
    const project=q.get('project');let ref,proof;
    try{ref=JSON.parse(q.get('candidate_ref'));proof=JSON.parse(q.get('preview_ref'));}catch{return null;}
    const image=q.has('format');
    if(!validTemplatePreviewRef(proof,project,ref)||image&&(q.get('format')!=='png'||!integer('page')||Number(q.get('page'))<1)||!image&&q.has('page'))return null;
    const payload={view:'template',candidate_ref:ref,preview_ref:proof,part:image?'preview-image':'preview-output',...(image?{page:Number(q.get('page'))}:{})};
    return {kind:'template-preview',project,candidateRef:ref,previewRef:proof,part:payload.part,http,
      read_handle:{operation:'document',payload},href:'/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:'manuscript'})};
  }
  if(url.pathname==='/authoring/build'){
    if(!unique(['project','build_target','build_job'])||!text('project')||q.has('build_target')&&q.has('build_job'))return null;
    const project=q.get('project');let target=null,job=null;
    if(q.has('build_target')){try{target=JSON.parse(q.get('build_target'));}catch{return null;}if(!validBuildTarget(target,project))return null;}
    if(q.has('build_job')){try{job=JSON.parse(q.get('build_job'));}catch{return null;}if(!validBuildJob(job,project))return null;target=job.build_target||null;}
    return {kind:target?.kind==='candidate'?'candidate-build-status':target?'derived-build-status':'manuscript-build-status',project,...(target?{buildTarget:target}:{}),...(job?{buildJob:job}:{}),http,href:'/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:target?.kind==='derived'?'presentation':'manuscript'})};
  }
  if(url.pathname==='/work/profiles'){
    if(!unique(['project','family','scope','view','profile','candidate_ref','part','offset','limit'])||!text('project')||!integer('offset')||!integer('limit',8000)||q.has('limit')&&Number(q.get('limit'))<1)return null;
    const project=q.get('project'),view=q.get('view')||'summary',payload={view};
    if(!['summary','content','candidate','candidates'].includes(view))return null;
    for(const key of ['family','scope','profile','part'])if(q.has(key))payload[key]=q.get(key);
    for(const key of ['offset','limit'])if(q.has(key))payload[key]=Number(q.get(key));
    if(view==='candidate'){
      if(!q.has('candidate_ref')||['family','scope','profile'].some(key=>q.has(key)))return null;
      try{payload.candidate_ref=JSON.parse(q.get('candidate_ref'));}catch{return null;}
      const ref=payload.candidate_ref;if(!ref||Object.keys(ref).sort().join(',')!=='id,version'||!/^PROP-[a-f0-9]{32}$/.test(ref.id)||!/^sha256:[a-f0-9]{64}$/.test(ref.version)||q.has('part')&&!['metadata','current','proposed'].includes(q.get('part')))return null;
    }else{
      if(q.has('candidate_ref')||q.has('part'))return null;
      if(view!=='candidates'&&(!['architecture','voice'].includes(payload.family)||!['workspace','project'].includes(payload.scope)))return null;
      if(payload.family&& !['architecture','voice'].includes(payload.family)||payload.scope&&!['workspace','project'].includes(payload.scope)||payload.family==='architecture'&&payload.scope&&payload.scope!=='workspace')return null;
      if(payload.profile&&!(payload.family==='voice'&&payload.scope==='workspace'&&payload.profile.startsWith('profiles/voice/')&&payload.profile.endsWith('.md')&&!payload.profile.split('/').includes('..')&&!payload.profile.includes('\\')))return null;
    }
    return {kind:'profile',project,view,http,read_handle:{operation:'profile',payload},href:'/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:'settings'})};
  }
  if(url.pathname==='/work/structure'){
    const view=q.get('view');
    const pageFields=['section_offset','section_limit','object_offset','object_limit','member_offset','member_limit','gap_offset','gap_limit','spine_offset','spine_limit'];
    const allowed={restructure:['project','view','section_ids','receipt_id','intent_artifact_id','reconcile_current'],outline:['project','view','files','offset','limit','as_of'],summary:['project','view','section_ids','as_of',...pageFields],plan:['project','view'],detail:['project','view','section_ids','sections','files','line_start','line_end','node_id','node_ids','section_offset','section_limit','member_offset','member_limit','member_cut','paragraph_offset','paragraph_limit','paragraph_id','paragraph_as_of','edit_choices','projection','subject','spine_offset'],full:['project','view'],'architecture-profile':['project','view'],delivery:['project','view','context_id','part','expected_token']};
    if(!allowed[view]||!unique(allowed[view])||!text('project')||q.has('as_of')&&!text('as_of')||q.has('member_cut')&&!text('member_cut')||q.has('paragraph_as_of')&&!text('paragraph_as_of')||q.has('paragraph_id')&&!text('paragraph_id'))return null;
    // the bounded guard projection (N1): one subject per read; a subject needs the projection
    // projection:display (ACTUAL-C6-DETAIL-BYTES) is the bounded human page of one section and takes no subject
    // spine_offset on a detail read is the display's beat page only (ACTUAL-C1011-DISPLAY-BYTES): a whole number, display, no paragraph_id
    if(view==='detail'&&q.has('spine_offset')&&(q.get('projection')!=='display'||!/^(0|[1-9][0-9]{0,5})$/.test(q.get('spine_offset'))||q.has('paragraph_id')))return null;
    if(q.has('projection')&&!['guard','display'].includes(q.get('projection'))||q.has('subject')&&(q.get('projection')!=='guard'||!['contract','paragraph','create','reorder','section','structure'].includes(q.get('subject')))||['paragraph','structure'].includes(q.get('subject'))&&!q.has('paragraph_id'))return null;
    if(view==='restructure'&&(!text('receipt_id')||!text('intent_artifact_id')||q.has('reconcile_current')&&q.get('reconcile_current')!=='true'))return null;
    if(view==='delivery'&&(!/^CTX-[0-9a-f]{32}$/.test(q.get('context_id')||'')||
      !/^[0-9a-f]{32}$/.test(q.get('expected_token')||'')||
      !['canonical_structure','direct_prerequisites','mathematical_record','section_notes','local_source_refs'].includes(q.get('part'))))return null;
    const lists={};
    for(const key of ['section_ids','sections','files','node_ids'])if(q.has(key)){
      try{lists[key]=JSON.parse(q.get(key));}catch{return null;}
      if(!Array.isArray(lists[key])||lists[key].some(value=>typeof value!=='string'||!value.trim()||/[\u0000-\u001f]/.test(value)))return null;
      if(key==='files'&&lists[key].some(file=>file.startsWith('/')||file.includes('\\')||file.split('/').includes('..')))return null;
    }
    if(view==='restructure'&&(!lists.section_ids||lists.section_ids.length!==1))return null;
    // a guard read names exactly ONE canonical section (Sol guard-selector-policy): a guard link
    // selected by files, node_id, node_ids or the sections alias is not an admitted owner read,
    // so no read is issued and no inspector opens for it; the plain detail resolves those selectors
    if(q.has('projection')&&(!lists.section_ids||lists.section_ids.length!==1||q.has('sections')||q.has('files')||q.has('node_ids')||q.has('node_id')))return null;
    for(const key of ['offset','limit','line_start','line_end','paragraph_offset','paragraph_limit',...pageFields])if(q.has(key)&&(!integer(key,key==='paragraph_limit'?50:key.endsWith('limit')?200:undefined)||(key.endsWith('limit')||key.startsWith('line_'))&&Number(q.get(key))<1))return null;
    if(q.has('line_end')&&(!q.has('line_start')||Number(q.get('line_end'))<Number(q.get('line_start'))))return null;
    if(q.has('node_id')&&!text('node_id')||q.has('edit_choices')&&!['true','false'].includes(q.get('edit_choices')))return null;
    const project=q.get('project'),sectionIds=lists.section_ids||lists.sections||[];
    const payload=Object.fromEntries([...q].filter(([key])=>key!=='project').map(([key,value])=>[key,lists[key]||['edit_choices','reconcile_current'].includes(key)? (lists[key]||value==='true'):['offset','limit','line_start','line_end','paragraph_offset','paragraph_limit',...pageFields].includes(key)?Number(value):value]));
    return {kind:'structure',project,view,sectionIds,files:lists.files||[],http,read_handle:{operation:'structure',payload},
      href:view==='delivery'?http.url:'/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:view==='outline'?'manuscript':'reader-plan',...(view==='outline'?{outline:'1'}:{}),...(sectionIds.length===1?{section:sectionIds[0]}:{})})};
  }
  if(url.pathname==='/references/attached'){
    if(!unique(['project','citekey'])||!text('project')||!text('citekey'))return null;
    return {kind:'bibliography-entry',project:q.get('project'),citekey:q.get('citekey'),http,href:http.url};
  }
  if(url.pathname==='/work/state'){
    if(q.get('view')==='provenance'){
      if(!unique(['project','view','id','request'])||!text('project')||!text('id')||!q.has('request'))return null;
      let request;try{request=JSON.parse(q.get('request'));}catch{return null;}
      if(!request||typeof request!=='object'||Array.isArray(request)||Object.keys(request).some(k=>!['demand','offset','limit','as_of'].includes(k))||!['aggregate','relationships','evidence','choices'].includes(request.demand)||
        request.offset!==undefined&&(!Number.isSafeInteger(request.offset)||request.offset<0)||request.limit!==undefined&&(!Number.isSafeInteger(request.limit)||request.limit<1||request.limit>24)||request.as_of!==undefined&&!/^sha256:[0-9a-f]{64}$/.test(request.as_of))return null;
      const project=q.get('project'),id=q.get('id'),payload={namespace:project,view:'provenance',id,request};
      return {kind:'work-provenance',project,id,view:'provenance',request,http,read_handle:{operation:'project',payload},href:http.url};
    }

    // the Work view continuity: exactly its owner's closed request (the summary, a prepared completion or a preflight)
    if(q.get('view')==='continuity'){
      if(!unique(['project','view','id','request'])||!text('project')||!text('id')||!q.has('request'))return null;
      let request;try{request=JSON.parse(q.get('request'));}catch{return null;}
      if(!continuityRequest(request))return null;
      const project=q.get('project'),id=q.get('id'),payload={namespace:project,view:'continuity',id,request};
      return {kind:'work-continuity',project,id,view:'continuity',request,part:request.part||'summary',http,read_handle:{operation:'project',payload},href:http.url};
    }
    if(q.get('view')==='review'&&q.has('phase_revision')){
      if(!unique(['project','view','id','phase_id','phase_revision','offset'])||!text('project')||!text('id')||!text('phase_id')||!/^sha256:[0-9a-f]{64}$/.test(q.get('phase_revision'))||!integer('offset'))return null;
      const project=q.get('project'),payload={namespace:project,view:'review',id:q.get('id'),phase_id:q.get('phase_id'),phase_revision:q.get('phase_revision')};
      // an owner-issued body page of a header-only phase: the same pinned phase read at its declared character offset
      if(q.has('offset'))payload.offset=Number(q.get('offset'));
      return {kind:'work-review-phase',project,id:payload.id,view:'review',http,read_handle:{operation:'project',payload},href:http.url};
    }
    if(q.get('view')==='review'&&q.has('obligation_id')){
      if(!unique(['project','view','id','obligation_id','offset','limit','as_of'])||!text('project')||!text('id')||!text('obligation_id')||
        !integer('offset')||!integer('limit',100)||q.has('limit')&&Number(q.get('limit'))<1||q.has('as_of')&&!/^sha256:[0-9a-f]{64}$/.test(q.get('as_of')))return null;
      const project=q.get('project'),payload={namespace:project,view:'review',id:q.get('id'),obligation_id:q.get('obligation_id')};
      for(const key of ['offset','limit'])if(q.has(key))payload[key]=Number(q.get(key));
      if(q.has('as_of'))payload.as_of=q.get('as_of');
      return {kind:'work-review-obligation',project,id:payload.id,view:'review',http,read_handle:{operation:'project',payload},href:http.url};
    }
    if(q.get('view')==='review-evidence'){
      if(!unique(['project','view','id','request'])||!text('project')||!text('id'))return null;
      let request;
      if(q.has('request')){
        try{request=JSON.parse(q.get('request'));}catch{return null;}
        if(!request||typeof request!=='object'||Array.isArray(request))return null;
        const demand=request.demand===undefined?'aggregate':request.demand,selector=request.selector===undefined?'all':request.selector,pin=value=>typeof value==='string'&&/^sha256:[0-9a-f]{64}$/.test(value);
        if(!['aggregate','enumerate','support'].includes(demand)||!['all','required','remaining-required'].includes(selector))return null;
        const keys=demand==='aggregate'?['demand','selector']:demand==='enumerate'?['demand','selector','observation','offset','limit']:['demand','selector','observation','offset','limit','enumeration','ids'];
        if(Object.keys(request).some(key=>!keys.includes(key))||demand!=='aggregate'&&!pin(request.observation)||
          request.offset!==undefined&&(!Number.isSafeInteger(request.offset)||request.offset<0)||
          request.limit!==undefined&&(!Number.isSafeInteger(request.limit)||request.limit<1||request.limit>24))return null;
        if(demand==='support'&&(!pin(request.enumeration)||!Array.isArray(request.ids)||request.ids.length<1||request.ids.length>24||
          request.ids.some(id=>typeof id!=='string'||!id.trim())||new Set(request.ids).size!==request.ids.length))return null;
      }
      const project=q.get('project'),id=q.get('id'),payload={namespace:project,view:'review-evidence',id,...(request!==undefined?{request}:{})};
      return {kind:'work-review-evidence',project,id,view:'review-evidence',request,http,read_handle:{operation:'project',payload},href:http.url};
    }
    if(!unique(['project','view','id','parent_work_id','limit','offset','as_of'])||!text('project')||!integer('limit',100)||q.has('limit')&&Number(q.get('limit'))<1||!integer('offset')||q.has('as_of')&&!text('as_of'))return null;
    const project=q.get('project'),view=q.get('view');if(!['detail','summary','graph'].includes(view)||view==='detail'&&!text('id')||view!=='detail'&&q.has('id')||view!=='graph'&&q.has('parent_work_id')||q.has('parent_work_id')&&!text('parent_work_id'))return null;
    return {kind:'work',project,view,...(view==='detail'?{id:q.get('id')}:{}),...(q.has('parent_work_id')?{parentWorkId:q.get('parent_work_id')}:{}),http,
      href:'/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:'work',...(view==='detail'?{work:q.get('id')}:{})})};
  }
  if(url.pathname==='/projects/material-references'){
    // A raw-source pin guards both plain excerpts and JSON-pointer reads; pointer remains optional and validated.
    if(q.has('pointer')&&(q.getAll('pointer').length!==1||q.get('pointer').length>4096||q.get('pointer')!==''&&!q.get('pointer').startsWith('/'))||q.has('expected_sha256')&&(q.getAll('expected_sha256').length!==1||!/^(sha256:)?[0-9a-fA-F]{64}$/.test(q.get('expected_sha256'))))return null;
    if(!unique(['project','view','id','target','consumer','offset','limit','page','page_count','pointer','expected_sha256'])||!(q.get('view')==='workspace-source'?text('consumer'):text('project'))||!integer('offset')||!integer('limit',40000)||q.has('limit')&&Number(q.get('limit'))<1||!integer('page')||q.has('page')&&Number(q.get('page'))<1||!integer('page_count',4)||q.has('page_count')&&Number(q.get('page_count'))<1)return null;
    const project=q.get('project')||q.get('consumer'),view=q.get('view');if(view==='workspace-source'&&q.has('project')&&project!==q.get('consumer'))return null;let target=null;
    if(view==='preview'){
      if(!text('target')||q.has('id')||q.has('consumer'))return null;
      try{target=JSON.parse(q.get('target'));}catch{return null;}
      if(!target||typeof target!=='object'||Array.isArray(target))return null;
      const fields=target.owner==='repository'?['owner','repository','path']:target.owner==='artifact'?['owner','project','path','scope']:null;
      if(!fields||Object.keys(target).length!==fields.length||fields.some(key=>typeof target[key]!=='string'||!target[key].trim())||target.owner==='artifact'&&!['project','manuscript'].includes(target.scope))return null;
    }else if(view==='source'||view==='workspace-source'){
      if(!text('id')||q.has('target')||view==='source'&&q.has('consumer')||view==='workspace-source'&&!text('consumer'))return null;
    }else return null;
    return {kind:'material-source',project,view,...(target?{target}:{}),...(q.has('id')?{id:q.get('id')}:{}),...(q.has('consumer')?{consumer:q.get('consumer')}:{}),...(q.has('pointer')?{pointer:q.get('pointer')}:{}),http,href:http.url};
  }
  if(url.pathname==='/authoring/help'){
    const fields=HELP_SELECTOR_FIELDS;
    if(!unique(['project','turn_id',...fields])||!text('project')||!text('turn_id'))return null;
    const selector={};for(const key of fields)if(q.has(key)){
      if(key==='context'){try{selector.context=JSON.parse(q.get(key));}catch{return null;}if(!selector.context||typeof selector.context!=='object'||Array.isArray(selector.context))return null;}
      else{if(!text(key))return null;selector[key]=q.get(key);}
    }
    // Transport validation only; the existing help owner validates selector schema and names.
    return {kind:'current-help',project:q.get('project'),turnId:q.get('turn_id'),selector,http,href:http.url};
  }
  if(url.pathname==='/authoring/history'){
    if(!unique(['project','view','id'])||!text('project')||q.get('view')!=='record'||!text('id'))return null;
    return {kind:'history-record',project:q.get('project'),id:q.get('id'),http,href:http.url};
  }
  if(url.pathname==='/authoring/proposal-preview'&&q.get('view')==='changed-reads'){
    // a refused candidate's changed consulted reads, one bounded owner page at a time (read-only; CR-R1)
    if(!unique(['project','id','record_id','proposal_version','view','cursor','limit'])||!text('project')||!text('id')||!integer('limit',20)
      ||q.has('limit')&&Number(q.get('limit'))<1||['record_id','proposal_version','cursor'].some(key=>q.has(key)&&!text(key)))return null;
    // the exact candidate and continuation coordinates are kept, so a returned page can be checked against them
    return {kind:'changed-reads',project:q.get('project'),id:q.get('id'),recordId:q.get('record_id'),version:q.get('proposal_version'),
      cursor:q.get('cursor'),limit:q.has('limit')?Number(q.get('limit')):null,http,href:http.url};
  }
  return null;
}
export function isKnownArtifactReadRoute(raw,{base=globalThis.location?.href||'http://localhost/'}={}){
  return localReadingURL(raw,base)?.pathname==='/research/artifact';
}
export function isKnownOwnerReadRoute(raw,{base=globalThis.location?.href||'http://localhost/'}={}){
  return READING_OWNERS.has(localReadingURL(raw,base)?.pathname);
}

// Bound inspection of retained native help guidance, not execution of the failed operation.
export function currentHelpRead(record){
 const handle=record?.recovery?.help,payload=handle?.payload;
 if(handle?.operation!=='help'||!payload||typeof payload!=='object'||Array.isArray(payload)||!record.project||!record.turn_id)return null;
 const fields=HELP_SELECTOR_FIELDS;
 if(Object.keys(payload).some(key=>key!=='project'&&!fields.includes(key))||payload.project&&payload.project!==record.project)return null;
 const q=new URLSearchParams({project:record.project,turn_id:record.turn_id});
 for(const key of fields)if(Object.hasOwn(payload,key)){const value=payload[key];if(key==='context'){if(!value||typeof value!=='object'||Array.isArray(value))return null;q.set(key,JSON.stringify(value));}else{if(typeof value!=='string')return null;q.set(key,value);}}
 return ownerHumanTarget('/authoring/help?'+q);
}


// Validate a canonical emitted recovery READ transport, never synthesize a URL
// from an arbitrary native operation. The original failure owns P/WT binding.
export function recordedRecoveryRead(record,{project,turnId}={}){
 const recovery=record?.recovery_read,handle=recovery?.read_handle,payload=handle?.payload;
 if(!project||!turnId||record.project&&record.project!==project||record.turn_id&&record.turn_id!==turnId||
    typeof recovery?.read_id!=='string'||!recovery.read_id||handle?.operation!=='author_history'||
    !payload||typeof payload!=='object'||Array.isArray(payload)||payload.view!=='record'||
    payload.id!=='activity:journal:'+recovery.read_id||
    Object.keys(payload).some(key=>!['project','view','id'].includes(key))||payload.project&&payload.project!==project||
    handle.http?.method!=='GET')return null;
 const target=ownerHumanTarget(handle.http.url);
 return target?.kind==='history-record'&&target.project===project&&target.id===payload.id?target:null;
}

// Exact record inspection from passage discovery. A retained candidate is not
// automatically an origin or a current binding to the displayed paragraph.
export function passageHistoryRead(handle, project) {
  const payload = handle?.payload;
  if (handle?.operation !== 'author_history' || !payload || payload.view !== 'record' ||
      typeof payload.id !== 'string' || !payload.id ||
      Object.keys(payload).some(key => !['view','id','project'].includes(key)) ||
      payload.project && payload.project !== project) return null;
  return ownerHumanTarget('/authoring/history?' + new URLSearchParams({project,view:'record',id:payload.id}));
}

export function passageProvenancePresentation(passage, project) {
  const coverage = passage?.accepted_proposal_coverage;
  const uncertain = !!coverage && coverage.status !== 'COMPLETE';
  const links = [], seen = new Set();
  for (const row of passage?.accepted_proposals || []) {
    const read = passageHistoryRead(row.read_more, project);
    if (!read) continue;
    const key = read.id;
    if (seen.has(key)) continue;
    seen.add(key);
    links.push({read, label:'Inspect recorded source change', state:({LIVE_CURRENT_BASIS:'Current source and proposal basis',LIVE_TEXT_STALE_BASIS:'The text remains; its proposal basis has changed',LIVE_TEXT_REVIEW_REQUIRED:'Current source revision; scientific review remains required',STALE_OR_AMBIGUOUS:'Source link stale or ambiguous'})[row.status] || 'Standing not established', membership:!!row.anchor});
  }
  for (const row of passage?.accepted_proposal_recovery || []) {
    const read = passageHistoryRead(row.read_more, project);
    if (!read || seen.has(read.id)) continue;
    seen.add(read.id);
    links.push({read,label:'Inspect retained candidate history',state:row.reason || 'Its relation to this passage has not been established.',membership:false});
  }
  return {uncertain,links,
    message:uncertain ? 'Some recorded changes could not be tied conclusively to this passage. Inspect their retained records below.' : '',
    continuation:passage?.accepted_proposal_next_read || null};
}

// Only owner-issued HTTP companions become generic inspector destinations.
// Native-only structure/history continuations use their separately declared adapters.
export function qualifiedOwnerHTTP(handle, project) {
  const http=handle?.http;
  if(http?.method==='GET'&&typeof http.url==='string'){
    const owner=ownerHumanTarget(http.url);if(owner){
      if(owner.project!==project)return null;
      if(handle.operation){
        const payload=handle.payload||{};
        if(payload.project&&payload.project!==project)return null;
        if(['derived-output','manuscript-document'].includes(owner.kind)&&
          (handle.operation!=='document'||payload.target_kind!==undefined&&!['manuscript','derived'].includes(payload.target_kind)||Object.keys(payload).some(key=>!['project','target_kind'].includes(key))||
           (payload.target_kind==='derived')!==(owner.kind==='derived-output')))return null;
        if(['derived-build-status','manuscript-build-status','candidate-build-status'].includes(owner.kind)&&
          (handle.operation!=='build_status'||Object.keys(payload).some(key=>!['project','build_target','build_job'].includes(key))||
           (owner.buildJob?(!sameBuildJob(payload.build_job,owner.buildJob)||payload.build_target!==undefined):
             payload.build_job!==undefined||(owner.buildTarget?!sameBuildTarget(payload.build_target,owner.buildTarget):payload.build_target!==undefined))))return null;
        if(['template-candidate','template-candidates','template-preview'].includes(owner.kind)){
          const stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):value;
          if(handle.operation!=='document'||Object.keys(payload).some(key=>key!=='project'&&!Object.hasOwn(owner.read_handle.payload,key))||
            Object.keys(owner.read_handle.payload).some(key=>JSON.stringify(stable(payload[key]))!==JSON.stringify(stable(owner.read_handle.payload[key]))))return null;
        }
        if(owner.kind==='profile'&&(handle.operation!=='profile'||Object.keys(payload).filter(key=>key!=='project').some(key=>JSON.stringify(payload[key])!==JSON.stringify(owner.read_handle.payload[key]))||Object.keys(owner.read_handle.payload).some(key=>JSON.stringify(payload[key])!==JSON.stringify(owner.read_handle.payload[key]))))return null;
        if(owner.kind==='research-result'&&(handle.operation!=='research'||payload.view!=='result'||payload.id!==owner.id||Object.keys(payload).some(key=>!['project','view','id'].includes(key))))return null;
        if(['work-review-evidence','work-provenance','work-continuity'].includes(owner.kind)){
          const stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):value;
          if(handle.operation!=='project'||Object.keys(payload).some(key=>!['project','namespace','view','id','request'].includes(key))||
            payload.namespace!==undefined&&payload.namespace!==project||payload.view!==owner.view||payload.id!==owner.id||
            JSON.stringify(stable(payload.request))!==JSON.stringify(stable(owner.request)))return null;
        }
        if(owner.kind==='work-review-phase'&&(handle.operation!=='project'||
          Object.keys(payload).some(key=>!['project','namespace','view','id','phase_id','phase_revision','offset'].includes(key))||
          payload.namespace!==undefined&&payload.namespace!==project||
          ['view','id','phase_id','phase_revision','offset'].some(key=>payload[key]!==owner.read_handle.payload[key])))return null;
        if(owner.kind==='work-review-obligation'&&(handle.operation!=='project'||
          Object.keys(payload).some(key=>!['project','namespace','view','id','obligation_id','offset','limit','as_of'].includes(key))||
          payload.namespace!==undefined&&payload.namespace!==project||
          ['view','id','obligation_id','offset','limit','as_of'].some(key=>payload[key]!==owner.read_handle.payload[key])))return null;
        if(owner.kind==='structure'&&owner.view==='restructure'&&
          (handle.operation!=='structure'||Object.keys(payload).some(key=>!['project','view','section_ids','receipt_id','intent_artifact_id','reconcile_current'].includes(key))||
           payload.view!==owner.view||JSON.stringify(payload.section_ids)!==JSON.stringify(owner.sectionIds)||payload.receipt_id!==owner.read_handle.payload.receipt_id||payload.intent_artifact_id!==owner.read_handle.payload.intent_artifact_id||payload.reconcile_current!==owner.read_handle.payload.reconcile_current))return null;
        if(owner.kind==='structure'&&owner.view==='delivery'&&
          (handle.operation!=='structure'||Object.keys(payload).some(key=>!['project','view','context_id','part','expected_token'].includes(key))||
           ['view','context_id','part','expected_token'].some(key=>payload[key]!==owner.read_handle.payload[key])))return null;
      }
      return {url:http.url,owner};
    }
    const artifact=artifactHumanTarget(http.url,{project});return artifact?{url:http.url,artifact}:null;
  }
  if(http?.method!=='GET'||typeof http.route!=='string'||!http.route.startsWith('/')||!http.query||typeof http.query!=='object'||Array.isArray(http.query))return null;
  if((http.query.project||http.query.corpus)!==project)return null;
  const query=new URLSearchParams();
  for(const[key,value]of Object.entries(http.query)){
    if(value===undefined||value===null)continue;
    if(!['string','number','boolean'].includes(typeof value)&&!Array.isArray(value))return null;
    query.set(key,Array.isArray(value)?JSON.stringify(value):String(value));
  }
  const url=http.route+'?'+query;
  const owner=ownerHumanTarget(url);
  if(owner)return qualifiedOwnerHTTP({...handle,http:{method:'GET',url}},project);
  const artifact=artifactHumanTarget(url,{project});if(artifact)return {url,artifact};
  if(http.route==='/research/result'&&handle.operation==='research'&&handle.payload?.view==='result'&&http.query.id===handle.payload.id&&typeof http.query.id==='string'&&Object.keys(http.query).every(key=>['project','id'].includes(key)))return {url,research:{id:http.query.id}};
  if(http.route==='/references/literature-uses'&&handle.operation==='literature_uses'&&http.query.key===handle.payload?.key&&typeof http.query.key==='string'&&Object.keys(http.query).every(key=>['project','key'].includes(key)))return {url,literature:{key:http.query.key}};

  if(http.route==='/projection/tex'&&http.query.view==='source'&&typeof http.query.file==='string'&&Object.keys(http.query).every(key=>['corpus','view','file'].includes(key))){
    const file=http.query.file;
    if(file&&!file.startsWith('/')&&!file.includes('\\')&&!file.split('/').includes('..')&&!/[\u0000-\u001f]/.test(file))return {url,source:{file}};
  }
  return null;
}

export function passageContinuationURL(handle,project,anchor){
  const payload=handle?.payload,http=handle?.http;
  const allowed=['file','line_start','line_end','accepted_offset','accepted_limit','accepted_as_of'];
  if(handle?.operation!=='logical_plan'||!payload||http?.method!=='GET'||http.route!=='/concepts/plan/context'||
     http.query?.corpus!==project||Object.keys(payload).some(key=>!allowed.includes(key))||
     Object.keys(http.query).some(key=>key!=='corpus'&&!allowed.includes(key))||
     ['file','line_start','line_end'].some(key=>payload[key]!==anchor?.[key])||
     !Number.isInteger(payload.accepted_offset)||payload.accepted_offset<0||
     !Number.isInteger(payload.accepted_limit)||payload.accepted_limit<1||payload.accepted_limit>100||
     typeof payload.accepted_as_of!=='string'||!payload.accepted_as_of||
     Object.entries(payload).some(([key,value])=>http.query[key]!==value))throw Error('This continuation does not belong to the inspected passage. Refresh its context.');
  return http.route+'?'+new URLSearchParams(http.query);
}
