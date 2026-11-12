// Scoped local-document task custody. Original bytes live only in this instance's
// File/Blob; browser storage contains compact intent and owner standing, never content.
const copy=value=>JSON.parse(JSON.stringify(value));
export async function intakeDigest(bytes){
 const digest=await crypto.subtle.digest('SHA-256',bytes);
 return 'sha256:'+Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('');
}
export async function inspectLocalDocument(file,mediaType,maximum){
 if(!file||typeof file.arrayBuffer!=='function'||!Number.isSafeInteger(file.size)||file.size<0)throw Error('Choose one local file.');
 if(!Number.isSafeInteger(maximum)||file.size===0||file.size>maximum)throw Error('Choose a nonempty file within the selected document type’s permitted size.');
 if(!['application/pdf','text/plain; charset=utf-8'].includes(mediaType))throw Error('Choose PDF or UTF-8 text.');
 const bytes=await file.arrayBuffer();
 if(bytes.byteLength!==file.size)throw Error('The selected file changed while being read. Choose it again.');
 if(mediaType==='application/pdf'){
  const head=new Uint8Array(bytes,0,Math.min(5,bytes.byteLength));
  if(String.fromCharCode(...head)!=='%PDF-')throw Error('The selected file does not have a PDF header.');
 }else try{new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{throw Error('The selected document is not valid UTF-8 text. Choose its original PDF or save a UTF-8 copy.');}
 return {display_name:String(file.name||'Local document'),media_type:mediaType,size:file.size,sha256:await intakeDigest(bytes)};
}
export function sameLocalDocument(left,right){return !!left&&!!right&&['display_name','media_type','size','sha256'].every(key=>left[key]===right[key]);}
export function materialReadingInput(value,{project=null}={}){
 const keys=['schema_version','project','artifact_id','sha256','read_payload','material_id'],payloadKeys=['id','expected_sha256','offset','limit','page','page_count','view','pointer'];
 const hash=raw=>typeof raw==='string'&&/^(?:sha256:)?[a-f0-9]{64}$/.test(raw),normal=raw=>String(raw).replace(/^sha256:/,'');
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!keys.includes(key))||value.schema_version!=='laplace.material-reading/1'||typeof value.project!=='string'||!value.project||project&&value.project!==project||typeof value.artifact_id!=='string'||!value.artifact_id.startsWith('ART-')||!hash(value.sha256))throw Error('The selected document reading is incomplete or belongs to another project.');
 const p=value.read_payload;if(!p||typeof p!=='object'||Array.isArray(p)||Object.keys(p).some(key=>!payloadKeys.includes(key))||p.id!==value.artifact_id||!hash(p.expected_sha256)||normal(p.expected_sha256)!==normal(value.sha256))throw Error('The document reading lost its exact artifact and source pin.');
 if(value.material_id!==undefined&&(typeof value.material_id!=='string'||!value.material_id.startsWith('MAT-')))throw Error('The selected Material identity is invalid.');
 for(const [key,min,max]of [['offset',0,1000000000],['limit',1,40000],['page',1,Number.MAX_SAFE_INTEGER],['page_count',1,4]])if(p[key]!==undefined&&(!Number.isSafeInteger(p[key])||p[key]<min||p[key]>max))throw Error('The selected document page controls are invalid.');
 if(p.view!==undefined&&!['text','page'].includes(p.view)||p.pointer!==undefined&&(typeof p.pointer!=='string'||p.pointer.length>4096))throw Error('The selected document reading mode is invalid.');
 return copy(value);
}

export function intakeReadURL(project,payload={view:'describe'}){
 return '/projects/material-intake?'+new URLSearchParams({project,request:JSON.stringify(payload)});
}
export function intakeHTTP(handle,{project,method='GET',paths=null,base=globalThis.location?.href||'http://local/'}={}){
 const http=handle?.http,here=new URL(base),url=new URL(http?.url||'',here);
 if(http?.method!==method||url.origin!==here.origin||url.hash||url.username||url.password||paths&&!paths.includes(url.pathname))throw Error('The document owner handle does not match this operation.');
 const declared=handle?.query?.project||handle?.payload?.project;
 if(handle.project&&handle.project!==project||declared&&declared!==project||url.searchParams.has('project')&&(url.searchParams.getAll('project').length!==1||url.searchParams.get('project')!==project)||method==='GET'&&!url.searchParams.has('project'))throw Error('The document owner handle belongs to another project.');
 return url.pathname+url.search;
}
export function intakeDocumentReadURL(handle,{project,artifactId,sha256,allowCurrent=false,base=globalThis.location?.href||'http://local/'}={}){
 const path=intakeHTTP(handle,{project,paths:['/projects/material-intake/read'],base}),url=new URL(path,base),encoded=url.searchParams.get('request');
 if(url.searchParams.getAll('request').length!==1||[...url.searchParams.keys()].some(key=>!['project','request'].includes(key)))throw Error('The document read has unsupported coordinates.');
 const payload=JSON.parse(encoded),ordered=value=>JSON.stringify(Object.fromEntries(Object.entries(value).sort()));
 if(handle.operation&&handle.operation!=='read_artifact'||handle.payload&&ordered(payload)!==ordered(handle.payload))throw Error('The document read carrier contradicts its exact payload.');
 // An exact issued restart may inspect current bytes. The added validation pin is
 // never placed in its URL or request; the returned owner pointer is checked again.
 materialReadingInput({schema_version:'laplace.material-reading/1',project,artifact_id:artifactId,sha256,read_payload:{...payload,...(allowCurrent&&payload.expected_sha256===undefined?{expected_sha256:sha256}:{})}},{project});return path;
}
export function intakeOriginalURL(handle,{project,artifactId,sha256,base=globalThis.location?.href||'http://local/'}={}){
 const path=intakeHTTP(handle,{project,paths:['/projects/material-intake/original'],base}),url=new URL(path,base),q=url.searchParams;
 if([...q.keys()].some(key=>!['project','id','expected_sha256'].includes(key))||q.getAll('id').length!==1||q.get('id')!==artifactId||q.getAll('expected_sha256').length!==1||String(q.get('expected_sha256')).replace(/^sha256:/,'')!==String(sha256).replace(/^sha256:/,''))throw Error('The original read does not match the retained document.');return path;
}
export function inspectedIntakeReading(value,original,{project}={}){
 if(!value)return null;
 if(typeof value.coverage?.label!=='string'||!value.coverage.fields||typeof value.coverage.fields!=='object')throw Error('The last inspected coverage is unavailable. Reinspect the selected document explicitly.');
 const pointer=materialReadingInput(value.pointer,{project});
 if(pointer.artifact_id!==original?.artifact_id||pointer.sha256.replace(/^sha256:/,'')!==String(original?.sha256).replace(/^sha256:/,''))throw Error('The last inspected reading belongs to a different original. Reinspect the selected document explicitly.');
 intakeDocumentReadURL(value.handle,{project,artifactId:original.artifact_id,sha256:original.sha256});
 return copy({pointer,handle:value.handle,coverage:value.coverage});
}
// One deliberate action return, scoped until its destination resolves. A later
// focus/gesture cancels this focus intent; the destination also checks its own visit.
export async function focusIntakeDestination(open,{page=globalThis.document,isCurrent=()=>true}={}){
 let moved=false;const initial=page.activeElement;
 const change=event=>{if(event.type==='focusin'&&(event.target===initial||event.target===page.body))return;moved=true;};
 for(const name of ['focusin','pointerdown','keydown'])page.addEventListener?.(name,change,true);
 try{const destination=await open(),node=destination?.element||destination;
  if(!moved&&isCurrent()&&destination?.isCurrent?.()!==false&&node?.isConnected!==false)node?.focus?.({preventScroll:false});
 }finally{for(const name of ['focusin','pointerdown','keydown'])page.removeEventListener?.(name,change,true);}
}
export function intakeStatusHandle(action,requestId,{project,base=globalThis.location?.href||'http://local/'}={}){
 const path=intakeHTTP(action,{project,paths:['/projects/material-intake'],base}),url=new URL(path,base),payload={...copy(action.payload)};
 if(action.request_field!=='request'||payload.view!=='status'||!action.requires?.includes('request_id')&&payload.request_id!==requestId)throw Error('The owner did not issue the document request lookup.');
 payload.request_id=requestId;url.searchParams.set('request',JSON.stringify(payload));return {...copy(action),payload,http:{method:'GET',url:url.pathname+url.search}};
}
export async function retainIntakeSubmission(project,metadata,action,status){
 if(typeof metadata?.request_id!=='string'||!metadata.request_id)throw Error('The document submission needs its original request.');
 const wire=JSON.stringify(metadata);return {project,request_id:metadata.request_id,wire,wire_sha256:await intakeDigest(new TextEncoder().encode(wire)),action:copy(action),status:copy(status),observation:'UNKNOWN'};
}
export async function intakeSubmissionMetadata(pending){
 if(typeof pending?.wire!=='string'||await intakeDigest(new TextEncoder().encode(pending.wire))!==pending.wire_sha256)throw Error('The retained document submission is damaged; nothing was sent. Keep its original recovery copy.');
 const value=JSON.parse(pending.wire);if(value.request_id!==pending.request_id)throw Error('The retained document request changed.');return value;
}
export async function uploadLocalDocument(action,metadata,file,{project,base=globalThis.location?.href||'http://local/',fetcher=globalThis.fetch}={}){
 const path=intakeHTTP(action,{project,method:'POST',paths:['/projects/material-intake/upload'],base}),url=new URL(path,base);
 if(action.request_field!=='request'||action.query?.project!==project)throw Error('The owner did not issue the raw document upload carrier.');
 if(!file||file.size!==metadata.declared_size)throw Error('Reselect the exact original document before retrying this submission.');
 url.searchParams.set('project',project);url.searchParams.set('request',JSON.stringify(metadata));
 let response,value;
 try{response=await fetcher(url.pathname+url.search,{method:'POST',headers:{'X-Laplace-Writing':'1','Content-Type':metadata.media_type},body:file});}
 catch(error){throw Object.assign(Error('The upload response is unavailable. Check the original document request; its outcome is unknown.'),{cause:error,effect:'unknown',transport:'connection'});}
 try{value=await response.json();}catch(error){throw Object.assign(Error('The document owner response could not be read. Check the original request.'),{cause:error,effect:'unknown',status:response.status});}
 if(!response.ok||value.error)throw Object.assign(Error(value.error||value.reason||'The document owner did not confirm this submission.'),{result:value,status:response.status,effect:'unknown'});
 return value;
}

export function createLocalDocumentDraft({project,storage=globalThis.sessionStorage,backup=globalThis.localStorage}){
 if(typeof project!=='string'||!project)throw Error('A local document needs its selected project.');
 const key='laplace:local-document-intake:'+JSON.stringify(project);let state={},generation=0,error='',damaged=false,file=null,fileIdentity=null;
 for(const store of [storage,backup]){
  let raw;try{raw=store?.getItem(key);}catch{continue;}if(!raw)continue;
  try{const held=JSON.parse(raw);if(held.schema!=='laplace.local-document-draft/1'||held.project!==project||!held.state||typeof held.state!=='object'||Array.isArray(held.state))throw Error();if((held.generation||0)>=generation){generation=held.generation||0;state=held.state;}}
  catch{damaged=true;error='The retained document request is unreadable. Its recovery copy is preserved; another Add is unavailable.';}
 }
 function persist(){
  if(damaged)return false;
  const wire=JSON.stringify({schema:'laplace.local-document-draft/1',project,generation:++generation,state});let saved=false;
  for(const store of [storage,backup])try{store?.setItem(key,wire);if(store?.getItem(key)===wire)saved=true;}catch{}
  error=saved?'':'The document request could not be retained. Keep this panel open; Add needs a recovery copy.';return saved;
 }
 return {
  snapshot:()=>copy(state),persist,get error(){return error;},get damaged(){return damaged;},
  update(fields){state={...state,...copy(fields)};persist();return copy(state);},
  retainFile(value,identity){file=value;fileIdentity=copy(identity);},
  selectedFile(identity){return sameLocalDocument(fileIdentity,identity)?file:null;},
  releaseFile(){file=null;fileIdentity=null;}
 };
}
