// Selected public message pages. The session orchestrates navigation; this leaf owns
// exact owner-handle validation, contiguous assembly and its small in-place reader.
// Only target/basis/extent intent is persisted; message words remain in memory.
import {createLifetime} from './selected-lifetime.mjs';
import {pendingRead} from './pending-read.mjs';
import {declareControl} from './workspace-presentation.mjs';
const fields=['project','session_id','turn_id','part'];
const same=(a,b)=>fields.every(k=>a?.[k]===b?.[k]);
export function messageReadURL(handle,target){
  if(!same(handle?.identity,target)||handle?.http?.method!=='GET')throw Error('The message read has another target.');
  const url=new URL(handle.http.url,'http://message.invalid');
  if(url.origin!=='http://message.invalid'||url.pathname!=='/authoring/session-turn'||url.searchParams.get('view')!=='message'||fields.some(k=>url.searchParams.get(k==='turn_id'?'id':k)!==target[k]))throw Error('The message read is not qualified for this conversation.');
  return url.pathname+url.search;
}
export function firstMessageRead(target){return {identity:{...target},http:{method:'GET',url:'/authoring/session-turn?'+new URLSearchParams({project:target.project,session_id:target.session_id,id:target.turn_id,part:target.part,view:'message'})}};}
export function createMessageReading({target,request,changed=()=>{},remember=()=>{},intent=null,initialRead=null}){
  if(initialRead)messageReadURL(initialRead,target);
  const life=createLifetime();let current=()=>true,ticket=0,last=null;
  const state={target:{...target},content:null,basis:null,end:0,total:null,complete:false,absent:false,busy:false,error:null,changed:false,first:null,next:null,restart:initialRead||firstMessageRead(target),stream:''};
  const notify=()=>changed(state);
  function valid(value,handle){
    if(!same(value,target)||value.schema_version!=='laplace.writing-message-part/1')throw Error('The saved message belongs to another conversation or part.');
    messageReadURL(value.restart_read,target);
    if(value.state==='ABSENT')return;
    const url=new URL(messageReadURL(handle,target),'http://message.invalid'),offset=Number(url.searchParams.get('offset')||0),basis=url.searchParams.get('expected_basis');
    if(value.state!=='AVAILABLE'||typeof value.content!=='string'||typeof value.basis!=='string'||!/^sha256:[0-9a-f]{64}$/.test(value.basis)||basis&&value.basis!==basis||!Number.isInteger(value.end)||value.offset!==offset||value.end<offset||!Number.isInteger(value.total_characters)||value.total_characters<value.end||value.end===offset&&value.end<value.total_characters)throw Error('The owner message extent or basis is inconsistent.');
    messageReadURL(value.page_read,target);if(value.next_read)messageReadURL(value.next_read,target);
  }
  async function read(handle,mode='append'){
    if(state.busy||life.disposed||!current())return false;
    const mine=++ticket,lease=life.lease(),live=()=>mine===ticket&&lease()&&current();last={handle,mode};state.busy=true;state.error=null;notify();
    try{
      const value=await request(messageReadURL(handle,target));if(!live())return false;valid(value,handle);
      if(value.state==='ABSENT'){
        if(state.basis)throw Error('The saved message is unavailable; prior text is retained.');
        state.absent=true;state.restart=value.restart_read;state.error=null;notify();return true;
      }
      if(mode==='check'&&state.basis===value.basis){state.error=null;state.changed=false;notify();return true;}
      const fresh=mode==='restart'||state.basis===null;
      if(fresh&&value.offset!==0||!fresh&&(value.basis!==state.basis||value.offset!==state.end))throw Error('Message pages are not contiguous under the same basis.');
      state.content=fresh?value.content:state.content+value.content;state.basis=value.basis;state.end=value.end;state.total=value.total_characters;state.totalBytes=value.total_utf8_bytes;state.complete=value.end===value.total_characters;state.absent=false;state.changed=false;state.error=null;state.first=fresh?value.page_read:state.first;state.next=value.next_read;state.restart=value.restart_read;state.facts={source_record_id:value.source_record_id,source_row_sha256:value.source_row_sha256,presentation_origin:value.presentation_origin,units:value.units,currentness:value.currentness};
      remember({target:{...target},basis:state.basis,end:state.end,page_read:state.first});notify();return true;
    }catch(error){
      if(!live())return false;state.error=error.message;const refusal=error.result?.message_refusal;
      if(refusal?.code==='CHANGED_MESSAGE'&&same(refusal,target)&&refusal.expected_basis===(state.basis||new URL(messageReadURL(handle,target),'http://message.invalid').searchParams.get('expected_basis'))){messageReadURL(refusal.restart_read,target);state.restart=refusal.restart_read;state.changed=true;}
      notify();return false;
    }finally{if(mine===ticket){state.busy=false;notify();}}
  }
  return {state,
    activate(isCurrent){current=isCurrent;},deactivate(){++ticket;life.advance();state.busy=false;},
    async open(){if(state.content!==null||state.absent)return;const held=intent&&same(intent.target,target)&&intent.page_read;const ok=await read(held||state.restart);if(ok&&held){while(!state.complete&&state.end<intent.end&&state.next&&!state.error&&current()){if(!await read(state.next))break;}}},
    next:()=>state.next?read(state.next):Promise.resolve(false),retry:()=>last?read(last.handle,last.mode):read(state.restart),
    restart:()=>read(state.restart,'restart'),refresh:()=>read(state.first||state.restart,state.basis?'check':'append'),
    stream(text){state.stream=text;notify();},dispose(){++ticket;life.dispose();},
  };
}
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
export function mountMessageReading(row,{target,request,renderMarkdown,isCurrent,storage,changed=()=>{},initialRead=null}){
  const key='laplace:message-reading:'+JSON.stringify(target);let intent=null;try{intent=JSON.parse(storage?.getItem(key)||'null');}catch{/* optional extent restoration */}
  const body=row.querySelector('.session-body'),controls=el('div','','session-message-reading'),note=el('p','','session-help'),next=declareControl(el('button','Continue reading'),'conversation:reading-next'),retry=declareControl(el('button','Retry reading'),'conversation:reading-retry'),restart=declareControl(el('button','Restart reading'),'conversation:reading-restart'),details=el('details','','session-message-basis'),summary=declareControl(el('summary','Message details'),'conversation:reading-details'),facts=el('pre'),stream=el('div','','session-body session-retained-stream');
  for(const b of [next,retry,restart])b.type='button';details.append(summary,facts);controls.append(note,next,retry,restart,details);row.insertBefore(controls,body.nextSibling);row.insertBefore(stream,controls);let rendered=null,renderTicket=0,reader,live=isCurrent;
  function paint(state){
    const text=state.content;
    if(text!==null&&(rendered?.text!==text||rendered?.complete!==state.complete)){
      rendered={text,complete:state.complete};const mine=++renderTicket;
      if(state.complete&&target.part==='reply'&&renderMarkdown){
        const apply=write=>{if(mine!==renderTicket)return;if(!live()){rendered=null;return;}changed(write);};
        const staged=el('div');Promise.resolve(renderMarkdown(staged,text)).then(()=>apply(()=>{body.replaceChildren(...staged.childNodes);body.classList.add('is-rendered');})).catch(()=>apply(()=>{body.textContent=text;body.classList.remove('is-rendered');}));
      }else changed(()=>{body.textContent=text;body.classList.remove('is-rendered');});
    }
    stream.hidden=!state.stream||state.complete;stream.textContent=stream.hidden?'':state.stream;
    // a pending owner read says for how long it has waited (pending-read.mjs): timed when the words first change to it
    const words=state.error?(state.changed?'Message changed. Prior text is retained. ':'Reading unavailable. Prior text is retained. ')+state.error:state.busy?'Reading…':state.absent?(state.stream?'Live text retained; no saved reply yet.':'No saved reply yet.'):state.content===null?'Reading saved message…':state.complete?(state.content===''?'Saved empty message.':''):'Continue for the rest of this message.';
    if(note.textContent!==words){if(words.endsWith('…'))pendingRead(note,words);else note.textContent=words;}
    note.classList.toggle('error',!!state.error);note.hidden=!note.textContent;
    next.hidden=!state.next||!!state.error;retry.hidden=!state.error||state.changed;restart.hidden=!state.error;for(const b of [next,retry,restart])b.disabled=state.busy;
    details.hidden=state.content===null;facts.textContent=JSON.stringify({...target,basis:state.basis,characters:{start:0,end:state.end,total:state.total},total_utf8_bytes:state.totalBytes,complete:state.complete,...state.facts},null,2);
  }
  body.tabIndex=-1;
  reader=createMessageReading({target,request,intent,initialRead,changed:paint,remember:value=>{try{storage?.setItem(key,JSON.stringify(value));}catch{/* Reading does not depend on local persistence. */}}});reader.activate(isCurrent);const act=(button,work)=>async()=>{const focused=document.activeElement===button;await work();if(focused&&button.hidden&&live())body.focus({preventScroll:true});};next.onclick=act(next,()=>reader.next());retry.onclick=act(retry,()=>reader.retry());restart.onclick=act(restart,()=>reader.restart());paint(reader.state);
  return {...reader,activate(check){live=check;reader.activate(check);if(live())paint(reader.state);},deactivate(){++renderTicket;rendered=null;reader.deactivate();},dispose(){++renderTicket;rendered=null;reader.dispose();},row,controls};
}
