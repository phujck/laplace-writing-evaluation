// OWNER REQUEST (P2 service spine, WORK-frontend-p2-service-spine-20261021). Purpose: the one neutral carrier of a
// same-origin owner request: GET without a payload, POST with a JSON payload, an optional AbortSignal, and the exact
// status and owner body back. It interprets nothing: no source effect, plan completion, owner error, retry or
// authority. Writing's meaning of a reply lives in its own adapter (workspace-session.mjs writingOwnerResponse, used
// by projectRequest); any other consumer adds its own.
// Public contract: ownerRequest(path, payload, {signal, headers, base}) -> {ok, status, value, contentType}.
// value is the parsed JSON body, or {content: text} for any other content type (the existing projectRequest shape).
// Refusals and failures (thrown Error, extra fields only): a path outside the page's origin is refused before any
// network (transport 'refused-origin', effect 'none'); no response is transport 'connection' and an abort is
// 'aborted', both with effect 'unknown' for a POST (the owner may have recorded it) and 'none' for a GET; a body that
// cannot be parsed keeps its original error with transport 'unreadable-response' and the same effect rule. Nothing
// is ever resent. Owner-issued handles (http/native) stay separate carriers: this module takes the path a caller
// already chose and never copies transport metadata into a payload.
const effectOf=method=>method==='POST'?'unknown':'none';
const failure=(error,transport,method,extra={})=>Object.assign(error,{transport,method,effect:effectOf(method),...extra});
function sameOrigin(path,base){
  const here=new URL(base||'http://same-origin.invalid/'),url=new URL(String(path),here);
  if(url.origin!==here.origin)throw Object.assign(Error('This owner request leaves the page\'s origin; it was not sent.'),{transport:'refused-origin',effect:'none'});
}
export async function ownerRequest(path,payload,{signal=null,headers=null,base=globalThis.location?.href}={}){
  sameOrigin(path,base);
  const method=payload?'POST':'GET',init={method,headers:payload?{'Content-Type':'application/json',...(headers||{})}:{...(headers||{})},body:payload?JSON.stringify(payload):undefined};
  if(signal)init.signal=signal;
  let response;
  try{response=await fetch(path,init);}
  catch(error){throw failure(error instanceof Error?error:Error(String(error)),signal?.aborted?'aborted':'connection',method);}
  const contentType=response.headers.get('content-type')||'';
  let value;
  try{value=contentType.includes('application/json')?await response.json():{content:await response.text()};}
  catch(error){throw failure(error,signal?.aborted?'aborted':'unreadable-response',method,{status:response.status});}
  return {ok:response.ok,status:response.status,value,contentType};
}
