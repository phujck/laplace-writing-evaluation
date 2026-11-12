// Read-only presentation shared by project material, workspace dependencies and Work.
// Membership edits stay in those controllers; an observed digest is never acceptance.
const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
// INERT MARKDOWN READING (P5, over the existing bounded owner readers). Only DOM elements and textContent are created, so
// nothing in a document executes or fetches: images, embeds, scripts, styles and raw HTML become labelled placeholders
// that point to Raw. Links show their destination and open only on deliberate activation; other schemes stay text.
// Rich reading needs the complete same-cut text; a bounded page is shown as text until it is joined.
export const MARKDOWN_READING_LIMIT=262144;
const WEB_LINK=/^(https?:|mailto:)/i;
// BOUNDED RECOGNITION: one budget per document is shared by every block, quote level, table cell, list item and inline
// node. Each recognition step advances a monotone cursor or is charged, so no suffix is rescanned per failed marker.
export const RICH_WORK_LIMIT=4000000,RICH_NODE_LIMIT=40000,JOIN_PAGE_LIMIT=128;
export class ReadingLimitError extends Error{}
// A LOCAL assembly or presentation limit of a complete reading (first page only, page count, reading size). The owner
// observation stays valid, so it is shown as a local notice: no read failure, no reader/Adopt disarm, no restart.
// Owner transport, identity and extent failures stay ordinary errors.
export class LocalReadingRefusal extends Error{}
// OWNER EXTENTS: the repository owner counts universal-newline-normalised Unicode scalars (JS code-point iteration,
// never UTF-16 code units or raw file bytes); the Artifact owner counts UTF-8 bytes (TextEncoder) against its own
// size_bytes. An unknown unit joins nothing.
export function scalarExtent(text){let n=0;for(const _ of String(text??''))n++;return n;}
const UTF8=new TextEncoder();
export const utf8Extent=text=>UTF8.encode(String(text??'')).length;
function extentOf(value){const source=value.owner_result||value,units=value.units??source.units;
 if(typeof units==='string'){if(/byte/i.test(units))return utf8Extent;if(/scalar|character|code point/i.test(units))return scalarExtent;return null;}
 return Number.isSafeInteger(source.size_bytes)?utf8Extent:null;}
// a single page reads whole only when its own terminal fields and extent agree with the owner
function pageContradiction(value){const source=value.owner_result||value;if(value.read_handle)return null;
 if(source.next_offset!=null)return 'The owner reports more text after this page but issued no continuation; this page stays as exact text.';
 if(source.complete===false)return 'The owner says this page is not the complete document; this page stays as exact text.';
 const measure=extentOf(value),start=Number(source.offset||0);
 if(measure===utf8Extent&&Number.isSafeInteger(source.size_bytes)&&typeof source.content==='string'&&start+measure(source.content)!==source.size_bytes)
  return 'This page does not reach the owner\'s reported document size; it stays as exact text.';
 return null;}
const readingBudget=()=>({work:0,nodes:0});
function charge(budget,work=0,nodes=0){
 budget.work+=work;budget.nodes+=nodes;
 if(budget.work>RICH_WORK_LIMIT||budget.nodes>RICH_NODE_LIMIT)throw new ReadingLimitError('This document is too large or too dense for the rendered reading.');
}
const made=(budget,tag,text='',cls='')=>{charge(budget,0,1);return el(tag,text,cls);};
// for every position, the next index of one character, in a single backward pass
function nextIndex(source,c){const n=source.length,next=new Int32Array(n+1);next[n]=-1;
 for(let i=n-1;i>=0;i--)next[i]=source[i]===c?i:next[i+1];return next;}
const SPACE=/\s/;
function inlineInto(parent,source,budget){
 const n=source.length;charge(budget,8*n);
 const close=nextIndex(source,']'),paren=nextIndex(source,')'),angle=nextIndex(source,'>'),star=nextIndex(source,'*'),under=nextIndex(source,'_'),tick=nextIndex(source,'`');
 let literal=0,i=0;
 const flush=end=>{if(end>literal)parent.append(made(budget,'span',source.slice(literal,end)));};
 const emit=(start,end,...nodes)=>{flush(start);parent.append(...nodes);literal=i=end;};
 const run=at=>{let end=at;while(end<n&&source[end]==='`')end++;return end-at;};
 // [text](destination): the first ']' and then the first ')' after '(' (one constant-time lookup each)
 const bracketed=open=>{const c=open+1<=n?close[open+1]:-1;if(c<0||source[c+1]!=='(')return null;const p=c+2<=n?paren[c+2]:-1;return p<0?null:[c,p];};
 const destination=(c,p)=>{let end=c+2;while(end<p&&!SPACE.test(source[end]))end++;return source.slice(c+2,end);};
 while(i<n){
  const ch=source[i];
  if(ch==='`'){const length=run(i),after=i+length,next=after<n?tick[after]:-1;
   if(next>=0&&run(next)===length){emit(i,next+length,made(budget,'code',source.slice(after,next)));continue;}
   i=after;continue;}
  if(ch==='!'&&source[i+1]==='['){const found=bracketed(i+1);
   if(found){const [c,p]=found,alt=source.slice(i+2,c),dest=destination(c,p);
    emit(i,p+1,made(budget,'span','[Image not loaded: '+(alt||'no description')+(dest?' · '+dest:'')+'. See Raw.]','markdown-placeholder'));continue;}
   i++;continue;}
  if(ch==='['){const found=bracketed(i);
   if(found&&found[0]>i+1){const [c,p]=found,label=source.slice(i+1,c),href=destination(c,p);
    if(WEB_LINK.test(href)){const link=made(budget,'a',label);link.setAttribute('href',href);link.setAttribute('rel','noopener noreferrer nofollow');link.setAttribute('referrerpolicy','no-referrer');link.setAttribute('target','_blank');
     emit(i,p+1,link,made(budget,'span',' ('+href+')','markdown-destination'));}
    else emit(i,p+1,made(budget,'span',label),made(budget,'span',' ('+(href||'no destination')+'; not opened from here)','markdown-destination'));
    continue;}
   i++;continue;}
  if((ch==='*'||ch==='_')&&source[i+1]===ch){const k=(ch==='*'?star:under)[i+2];
   if(k>i+2&&source[k+1]===ch){emit(i,k+2,made(budget,'strong',source.slice(i+2,k)));continue;}
   i++;continue;}
  if(ch==='*'&&i+1<n&&!SPACE.test(source[i+1])){const k=star[i+1];
   if(k>i+1){emit(i,k+1,made(budget,'em',source.slice(i+1,k)));continue;}
   i++;continue;}
  if(ch==='<'){const k=angle[i+1];   // inline HTML stays visible text, never markup
   if(k>i+1){emit(i,k+1,made(budget,'span',source.slice(i,k+1),'markdown-inline-html'));continue;}
   i++;continue;}
  i++;
 }
 flush(n);   // failed markers stay in one coalesced literal span
}
const LIST_ITEM=/^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
// block recognition by simple linear scans, never overlapping whitespace quantifiers
function headingOf(line){let h=0;while(h<line.length&&h<7&&line[h]==='#')h++;
 if(h<1||h>6||h>=line.length||!SPACE.test(line[h]))return null;
 let end=line.length;while(end>h&&SPACE.test(line[end-1]))end--;while(end>h&&line[end-1]==='#')end--;
 return {level:h,text:line.slice(h,end).trim()};}
function isRule(line){const t=line.trim(),c=t[0];if(t.length<3||(c!=='-'&&c!=='*'&&c!=='_'))return false;let count=0;
 for(const ch of t){if(ch===c)count++;else if(!SPACE.test(ch))return false;}return count>=3;}
const isTableRow=line=>{const t=line.trim();return t.length>=2&&t[0]==='|'&&t[t.length-1]==='|';};
const outerPipes=row=>{let t=row.trim();if(t.startsWith('|'))t=t.slice(1);if(t.endsWith('|'))t=t.slice(0,-1);return t;};
function isTableRule(line,budget){const t=outerPipes(line);charge(budget,t.length);if(!t.trim())return false;let start=0;
 for(let i=0;i<=t.length;i++)if(i===t.length||t[i]==='|'){let cell=t.slice(start,i).trim();start=i+1;
  if(cell.startsWith(':'))cell=cell.slice(1);if(cell.endsWith(':'))cell=cell.slice(0,-1);
  if(cell.length<3)return false;for(const ch of cell)if(ch!=='-')return false;}
 return true;}
// Quote nesting is bounded; deeper levels stay visible as their exact remaining text instead of being parsed again.
export const QUOTE_NESTING_LIMIT=8;
// Builds a detached tree. Over the shared budget it throws ReadingLimitError; callers then show exact Raw and say why.
export function renderInertMarkdown(text,{budget=readingBudget(),depth=0}={}){
 const source=String(text??'');charge(budget,source.length);
 const root=made(budget,'div','','markdown-reading'),lines=source.replace(/\r\n?/g,'\n').split('\n'),para=[];let i=0;
 const flush=()=>{if(para.length){const p=made(budget,'p');inlineInto(p,para.join(' '),budget);root.append(p);para.length=0;}};
 const cells=row=>{const t=outerPipes(row);charge(budget,t.length);return t.split('|').map(cell=>cell.trim());};
 while(i<lines.length){
  const line=lines[i];charge(budget,line.length+1);
  const fence=/^\s*(```|~~~)(.*)$/.exec(line);
  if(fence){flush();const code=[];i++;while(i<lines.length&&!lines[i].trim().startsWith(fence[1])){charge(budget,lines[i].length+1);code.push(lines[i]);i++;}i++;
   const pre=made(budget,'pre','','markdown-code');pre.append(made(budget,'code',code.join('\n')));if(fence[2].trim())pre.setAttribute('data-language',fence[2].trim().slice(0,40));root.append(pre);continue;}
  if(!line.trim()){flush();i++;continue;}
  const heading=headingOf(line);
  if(heading){flush();const node=made(budget,'h'+Math.min(6,heading.level+3),'','markdown-heading');inlineInto(node,heading.text,budget);root.append(node);i++;continue;}
  if(isRule(line)){flush();root.append(made(budget,'hr'));i++;continue;}
  if(/^\s*>/.test(line)){flush();const quoted=[];while(i<lines.length&&/^\s*>/.test(lines[i])){charge(budget,lines[i].length+1);quoted.push(lines[i].replace(/^\s*>\s?/,''));i++;}
   const quote=made(budget,'blockquote');
   if(depth>=QUOTE_NESTING_LIMIT)quote.append(made(budget,'p','[Quote nesting deeper than '+QUOTE_NESTING_LIMIT+' levels is shown as text here. Raw has the exact source.]','markdown-placeholder'),
    made(budget,'pre',quoted.join('\n'),'markdown-quoted-text'));
   else quote.append(renderInertMarkdown(quoted.join('\n'),{budget,depth:depth+1}));
   root.append(quote);continue;}
  if(isTableRow(line)&&i+1<lines.length&&isTableRule(lines[i+1],budget)){flush();
   const table=made(budget,'table','','markdown-table'),head=made(budget,'thead'),top=made(budget,'tr'),rows=made(budget,'tbody');
   for(const cell of cells(line)){const th=made(budget,'th');th.setAttribute('scope','col');inlineInto(th,cell,budget);top.append(th);}head.append(top);i+=2;
   while(i<lines.length&&isTableRow(lines[i])){const tr=made(budget,'tr');for(const cell of cells(lines[i])){const td=made(budget,'td');inlineInto(td,cell,budget);tr.append(td);}rows.append(tr);i++;}
   table.append(head,rows);const wrap=made(budget,'div','','markdown-table-wrap');wrap.append(table);root.append(wrap);continue;}
  const item=LIST_ITEM.exec(line);
  if(item){flush();const ordered=/\d/.test(item[2]),list=made(budget,ordered?'ol':'ul');
   while(i<lines.length){const row=LIST_ITEM.exec(lines[i]);if(!row||/\d/.test(row[2])!==ordered)break;charge(budget,lines[i].length+1);const li=made(budget,'li');inlineInto(li,row[3],budget);i++;
    while(i<lines.length&&/^\s{2,}\S/.test(lines[i])&&!LIST_ITEM.test(lines[i])){charge(budget,lines[i].length+1);li.append(made(budget,'span',' '));inlineInto(li,lines[i].trim(),budget);i++;}
    list.append(li);}
   root.append(list);continue;}
  if(/^\s*<\/?[A-Za-z!][^>]*>/.test(line)){flush();let count=0;while(i<lines.length&&lines[i].trim()){count++;i++;}
   root.append(made(budget,'p','[HTML block not rendered: '+count+' line'+(count===1?'':'s')+'. Read it under Raw.]','markdown-placeholder'));continue;}
  para.push(line.trim());i++;
 }
 flush();return root;
}
// Initial and clicked Reading share one eligibility: complete text within the reading limit, otherwise exact Raw and why.
export function readingEligibility(text,{complete=true}={}){
 if(!complete)return 'This is a bounded page. The rendered reading needs the complete document at this same source revision.';
 if(String(text??'').length>MARKDOWN_READING_LIMIT)return 'This document is longer than the rendered-reading limit.';
 return null;
}
// Reading is the default and Raw is the exact text; a pressed toggle, so Enter or Space switches and focus fetches nothing.
export function markdownReading(text,{complete=true}={}){
 const box=el('div','','document-reading'),modes=el('div','','reading-switch'),surface=el('div','','reading-surface');
 const reading=el('button','Reading','act'),raw=el('button','Raw','act');reading.type='button';raw.type='button';
 const notice=el('p','','muted reading-notice');notice.setAttribute('role','status');
 // an ineligible, over-budget or failed rich reading shows the exact Raw text with one local notice; the visit is unaffected
 const select=mode=>{let rendered=null;notice.textContent='';
  if(mode==='reading'){const refused=readingEligibility(text,{complete});
   if(refused){mode='raw';notice.textContent=refused+' Raw shows the exact text.';}
   else try{rendered=renderInertMarkdown(text);}
   catch(error){mode='raw';notice.textContent=(error instanceof ReadingLimitError?error.message:'The rendered reading could not be built ('+(error?.message||'render failed')+').')+' Raw shows the exact text.';}}
  reading.setAttribute('aria-pressed',String(mode==='reading'));raw.setAttribute('aria-pressed',String(mode==='raw'));box.setAttribute('data-mode',mode);
  surface.replaceChildren(rendered||el('pre',text,'material-source-reading'));};
 reading.onclick=()=>select('reading');raw.onclick=()=>select('raw');modes.append(reading,raw);box.append(modes,notice,surface);
 select('reading');
 return box;
}
const MARKDOWN_NAME=/\.(md|markdown)$/i;
export function materialReadURL(handle,base=globalThis.location?.href||'http://local/'){
 const route=handle?.http;
 if(!route||route.method!=='GET'||typeof route.url!=='string')throw Error('The source owner has not supplied a GET continuation.');
 const url=new URL(route.url,base);
 if(url.origin!==new URL(base).origin)throw Error('Source observation route is outside this local engine.');
 return url.pathname+url.search;
}
const status=value=>({UNBOUND:'UNBOUND · observed source; not linked or accepted',CURRENT:'CURRENT · consumed source revision matches; acceptance is separate',CHANGED_INPUT:'Owner changed; consumed revision is retained',UNRESOLVED:'Owner is unavailable; consumed revision is retained'}[value.currentness]||'Source observation; acceptance is not established');
export function documentReadingCoverage(value){
 const source=value.owner_result||value,fields={};for(const key of ['offset','next_offset','size_bytes','units','pdf_page','pdf_page_start','pdf_page_end','pdf_total_pages','extraction_state'])if(source[key]!=null)fields[key]=source[key];
 const number=value=>Number(value).toLocaleString();let label;
 if(source.pdf_page)label='PDF page '+number(source.pdf_page)+(source.pdf_total_pages?' of '+number(source.pdf_total_pages):'')+' · rendered image';
 else if(source.pdf_page_start)label='PDF text · pages '+number(source.pdf_page_start)+'–'+number(source.pdf_page_end)+' of '+number(source.pdf_total_pages)+(typeof source.content==='string'?' · '+number(Array.from(source.content).length)+' characters shown':'');
 else if(Number.isSafeInteger(source.offset)&&Number.isSafeInteger(source.size_bytes))label='Text · bytes '+number(source.offset)+'–'+number(source.next_offset??source.size_bytes)+' of '+number(source.size_bytes);
 else label=typeof source.content==='string'?'Text · '+number(Array.from(source.content).length)+' characters shown':'Reading coverage unavailable';
 if(source.extraction_state==='UNAVAILABLE')label='PDF text extraction unavailable';return {label,fields};
}
export function renderMaterialObservation(parent,initial,{request,isCurrent=()=>true,initialHandle=null,consumedRevision=null,workEvidence=false,onInvalidated=()=>{},onObservation=()=>{},onReadError=()=>{},documentLabel=null,onAddToLiterature=null,completeReading=false}){
 let sequence=0,basis=null,destroyed=false,restartOffered=false,standing=null,bar=null,autoJoin=completeReading===true,paged=0;
 const alive=()=>!destroyed&&isCurrent()&&parent.isConnected;
 const identity=value=>{const source=value.owner_result||value;return {revision:value.current_revision||source.source?.sha256||(!value.owner_result?source.revision:null)||null,
  target:JSON.stringify(value.target||source.source||null),units:value.units||null,record:source.json_record?.pointer??null};};
 const restart=initial.restart_read||initialHandle;
 // a late focus return never takes focus the person has since placed elsewhere: only nothing, the page body, a removed
 // node or this read's own removed Cancel count as unowned
 const focusUnowned=token=>{const active=globalThis.document?.activeElement;return !active||active===globalThis.document?.body||active===token.cancel||active.isConnected===false;};
 // ONE owned notice for a limited, refused or failed read, in the reading bar above the text and beside the complete action
 // (never appended below a long page); a newer notice replaces the earlier one
 let lastNotice=null;const notice=node=>{if(lastNotice){lastNotice.hidden=true;lastNotice.remove?.();}lastNotice=node;(bar||parent).append(node);};
 let activeToken=null;   // the pending record of the read the current gesture is starting; each read binds to its own record
 const button=(label,run,{disable=true,pending=true}={})=>{const node=el('button',label);node.type='button';let waiting=false;node.onclick=async()=>{if(waiting)return;waiting=true;if(disable)node.disabled=true;const wait=pending?pendingRead(node):{token:null,done(){}};activeToken=wait.token;let started;try{started=run();}catch(error){started=Promise.reject(error);}finally{activeToken=null;}try{await started;}catch(error){if(wait.token?.cancelled)return;if(alive()&&error instanceof LocalReadingRefusal){const note=el('p',error.message,'muted reading-notice');note.setAttribute('role','status');notice(note);}else if(alive()){if(standing)standing.textContent='Earlier observation retained · latest source read failed';onReadError();const note=el('p',error.message,'error');note.setAttribute('role','alert');notice(note);if(initial.restart_read)offerRestart(initial.restart_read);}}finally{wait.done();waiting=false;if(disable)node.disabled=false;if(wait.token?.cancelled&&wait.token.focusBack&&node.isConnected!==false&&focusUnowned(wait.token))node.focus?.({preventScroll:true});}};return node;};
 // a selected read in flight: its Cancel is bound to that one GET (aborted through the request signal where the transport
 // supports it; its late reply or rejection is dropped by this read's own record, never by advancing the shared sequence, so a
 // newer pending read keeps its own fence and page). What is already shown is untouched. Focus returns to the control that
 // issued the read only while the Cancel row still owns it. Guarded effects (Add to Literature) are not reads: no Cancel row.
 function pendingRead(opener=null){const row=el('p','','muted reading-pending');row.setAttribute('role','status');const token={cancelled:false,focusBack:false,controller:typeof AbortController==='function'?new AbortController():null};const cancel=el('button','Cancel this read');cancel.type='button';token.cancel=cancel;
  cancel.onclick=()=>{token.cancelled=true;token.focusBack=globalThis.document?.activeElement===cancel;token.controller?.abort();row.textContent='';row.hidden=true;row.remove?.();if(token.focusBack&&opener&&opener.isConnected!==false&&!opener.disabled)opener.focus?.({preventScroll:true});};row.append(el('span','Reading from the owner… '),cancel);(bar||parent).append(row);
  return {token,done(){row.textContent='';row.hidden=true;row.remove?.();}};}
 const dropped=(ticket,token)=>!alive()||ticket!==sequence||!!token?.cancelled;
 function offerRestart(handle=restart){if(handle&&!restartOffered){restartOffered=true;(bar||parent).append(button('Restart source observation',()=>read(handle,{reset:true})));}}
 async function read(handle,{reset=false}={}){
  if(!alive())return;
  const ticket=++sequence,token=activeToken;let value;
  try{value=await request(materialReadURL(handle),undefined,token?.controller?{signal:token.controller.signal}:undefined);}catch(error){if(dropped(ticket,token))return;throw error;}
  if(dropped(ticket,token))return;
  if(reset)basis=null;
  show(value);
  // a new page starts at its own top, with its controls, rather than wherever the previous page was left
  if(alive())parent.scrollIntoView?.({block:'start'});
 }
 function show(value){
  if(!alive())return;
  restartOffered=false;
  const observed=identity(value),source=value.owner_result||value;let more=null;
  if(basis&&(basis.revision!==observed.revision||basis.target!==observed.target||basis.units!==observed.units||basis.record!==observed.record)){
   onInvalidated();bar=null;parent.replaceChildren(el('p','Source changed between pages. This observation cannot mix read bases. Restart to inspect the current source.','error'),el('p','Earlier observed: '+(basis.revision||'Unavailable')),el('p','Now observed: '+(observed.revision||'Unavailable')));
   offerRestart();
   return;
  }
  basis=observed;
  const evidence=workEvidence||consumedRevision!=null;
  const digest=revision=>String(revision).replace(/^sha256:/,'');
  const comparison=!consumedRevision?'consumed revision unavailable':!observed.revision?'current source revision unavailable':digest(consumedRevision)===digest(observed.revision)?'recorded revision matches observed source':'source changed since recorded completion';
  standing=el('p',evidence?'Work evidence: '+comparison:status(value),'material-currentness');let metadata=parent;
  if(documentLabel){const details=el('details','','material-disclosure');details.append(el('summary','Exact source observation'));metadata=el('div');metadata.append(standing);details.append(metadata);parent.replaceChildren(el('h3',documentLabel),el('p',documentReadingCoverage(value).label,'document-reading-coverage'));parent.append(details);}
  // exact provenance stays one click away under Details; the standing line and the reading lead
  else{const details=el('details','','material-details material-disclosure');details.append(el('summary','Details'));metadata=details;parent.replaceChildren(standing,details);}
  // reading controls stay in reach above the text: the complete action, the bounded-page notice and Back
  bar=el('div','','material-reading-bar');parent.append(bar);
  if(paged>0&&restart)bar.append(button('Back to the first page',()=>{paged=0;return read(restart,{reset:true});}));
  const target=value.target||source.source;
  if(target)metadata.append(el('p','Source: '+Object.entries(target).map(([k,v])=>k+'='+v).join(' · '),'project-source-path'));
  if(evidence){
   metadata.append(el('p','Recorded evidence consumed: '+(consumedRevision||'Unavailable')+' · observation does not renew this receipt','project-source-path'));
   if(value.currentness){const binding=el('details','','material-disclosure');binding.append(el('summary','Workspace material binding'),el('p',status(value)),el('p','Workspace material consumed: '+(value.consumed_revision||'Not linked'),'project-source-path'));metadata.append(binding);}
  }else if(!documentLabel||Object.hasOwn(value,'consumed_revision'))metadata.append(el('p','Consumed: '+(value.consumed_revision||'Not linked'),'project-source-path'));
  metadata.append(el('p',(documentLabel?'Source pin: ':'Current: ')+(observed.revision||'Unavailable'),'project-source-path'));
  if(value.units)metadata.append(el('p','Offsets: '+value.units,'muted'));
  if(documentLabel&&source.material_read)metadata.append(el('pre',JSON.stringify(source.material_read,null,2)));
  // one JSON value of the source (campaign bounded source reading): which value, its size and identity
  const record=source.json_record;
  if(record)metadata.append(el('p','JSON record '+(record.pointer===''?'(whole document)':record.pointer)+' · '+record.type+(record.members!=null?' of '+record.members+(record.type==='array'?' items':' fields'):'')+' · '+record.value_chars+' characters · value '+record.value_sha256,'project-source-path'));
  if(source.pdf_page_start)metadata.append(el('p','PDF pages '+source.pdf_page_start+'–'+source.pdf_page_end+' of '+source.pdf_total_pages,'muted'));
  // a linked Material reference proves availability and project membership, never a produced Work result
  if(!evidence&&value.currentness&&value.currentness!=='UNBOUND')metadata.append(el('p','Linked source: availability and project membership only. It is not a produced Work result, authorship, delivery or acceptance.','muted material-membership'));
  const markdownName=String(documentLabel||target?.path||source.source?.path||'');
  if(source.content!=null&&MARKDOWN_NAME.test(markdownName)&&!record){
   const contradiction=pageContradiction(value);
   const whole=!value.read_handle&&!source.truncated&&!(Number(source.offset)>0)&&!contradiction;
   const place=el('div','','material-markdown');parent.append(place);
   if(whole)place.append(markdownReading(source.content));
   else{place.append(el('pre',source.content,'material-source-reading'));
    // the notice and the complete action sit above the page, so a long first page is never scrolled through to reach them
    bar.append(el('p',contradiction||'Bounded text page. The rendered reading needs the complete document at this same source revision.',contradiction?'error':'muted'));
    // only the exact first page may start a complete reading; a later page stays paged
    if(value.read_handle&&Number(source.offset)===0){
     const whole=button('Read the complete document',async()=>{const joined=await complete(value);if(joined==null||!alive())return;
      // the joined reading replaces the page; the continuation controls it consumed are terminal and leave, and the
      // reading starts at its top with Reading and Raw in reach
      place.replaceChildren(markdownReading(joined));bar.replaceChildren(el('p','Complete document at this source revision.','muted reading-extent'));
      if(more){more.hidden=true;more.remove?.();more=null;}
      const active=globalThis.document?.activeElement;if(active===whole||(active&&active===globalThis.document?.body)){place.tabIndex=-1;place.focus?.({preventScroll:true});}
      parent.scrollIntoView?.({block:'start'});});
     whole.className='primary';bar.append(whole);
     // the ordinary Read entry asks for the formatted document straight away: the same bounded, cancellable join, started once
     if(autoJoin){autoJoin=false;whole.onclick();}}
    else if(value.read_handle)bar.append(el('p','Only the first page can start a complete reading; this page stays paged.','muted'));}
  }else if(source.content!=null)parent.append(el('pre',source.content,'material-source-reading'));
  const images=(source._image_content||[]).filter(item=>item.mime_type==='image/png'&&typeof item.data==='string'&&/^[A-Za-z0-9+/\r\n]*={0,2}$/.test(item.data));
  for(const item of images){const image=el('img');image.src='data:image/png;base64,'+item.data;image.alt='Rendered source page'+(source.pdf_page?' '+source.pdf_page:'');image.style.maxWidth='100%';parent.append(image);}
  if(source.content==null&&!images.length)parent.append(el('p',value.diagnostic||source.note||'No readable source content returned.','muted'));
  if(source.note&&source.content!=null)parent.append(el('p',source.note,'muted'));
  if(source.literature&&onAddToLiterature){const add=button('Add to Literature',()=>onAddToLiterature(source.literature),{disable:false,pending:false});add.dataset.control='material:add-literature';add.dataset.controlOwner=(source.literature.project||'')+'::'+(source.literature.payload?.original?.artifact_id||'original');parent.append(add);}
  if(value.read_handle){more=button('Read more source',()=>{paged++;return read(value.read_handle);});parent.append(more);}
  else if(source.truncated)parent.append(el('p','Source is truncated but the owner supplied no continuation. Reinspect the source owner.','error'));
  onObservation(value);
 }
 // joins this observation's own continuations under one basis; a changed revision, target or unit refuses the join
 // Joins from the exact first page through the owner's issued continuations only. Each page must keep the revision,
 // target and units, start exactly where the previous one ended in the owner's own coordinates (never JS code units),
 // and make progress; attempts, accumulated and final text are bounded. Any refusal joins nothing.
 async function complete(first){
  const ticket=++sequence,token=activeToken,start=identity(first),head=first.owner_result||first;
  if(Number(head.offset)!==0)throw new LocalReadingRefusal('Only the first page can start a complete reading; this page stays paged.');
  const measure=extentOf(first);if(!measure)throw Error('The owner gave no unit for its page offsets, so nothing was joined.');
  const total=measure===utf8Extent&&Number.isSafeInteger(head.size_bytes)?head.size_bytes:null;
  let text=head.content||'',handle=first.read_handle,at=head.next_offset,attempts=0;
  if(handle&&Number.isSafeInteger(at)&&at<=0)throw Error('The first page made no progress, so nothing was joined.');
  // the owner's claimed offsets must match the actual returned text, so a claimed jump cannot hide a gap
  if(handle&&Number.isSafeInteger(at)&&at!==measure(text))throw Error('The first page\'s own text does not end where the owner says the next page starts, so nothing was joined.');
  while(handle){
   if(++attempts>JOIN_PAGE_LIMIT)throw new LocalReadingRefusal('The document needs more pages than a complete reading allows. Keep reading its pages, or use Raw.');
   if(!Number.isSafeInteger(at))throw Error('The owner gave no position for the next page, so nothing was joined.');
   if(text.length>MARKDOWN_READING_LIMIT)throw new LocalReadingRefusal('This document is longer than the rendered-reading limit. Keep reading its pages, or use Raw.');
   // the same sequence fence as an ordinary read: a superseded reply or rejection never touches the newer observation
   let next;try{next=await request(materialReadURL(handle),undefined,token?.controller?{signal:token.controller.signal}:undefined);}catch(error){if(dropped(ticket,token))return null;throw error;}
   if(dropped(ticket,token))return null;
   const seen=identity(next),page=next.owner_result||next,chunk=page.content||'';
   if(seen.revision!==start.revision||seen.target!==start.target||seen.units!==start.units)throw Error('Source changed between pages, so nothing was joined. Restart to inspect the current source.');
   if(page.offset!==at)throw Error('The next page does not continue where the previous one ended, so nothing was joined.');
   if(next.read_handle&&(!Number.isSafeInteger(page.next_offset)||page.next_offset<=page.offset||!chunk))throw Error('The next page made no progress, so nothing was joined.');
   if(next.read_handle&&page.next_offset!==page.offset+measure(chunk))throw Error('A page\'s own text does not end where the owner says the next page starts, so nothing was joined.');
   if(total!=null&&page.size_bytes!==total)throw Error('Source changed between pages, so nothing was joined. Restart to inspect the current source.');
   // terminal metadata must agree with the issued continuation and, where the owner reports it, the exact total
   if(!next.read_handle&&(page.truncated||page.next_offset!=null||page.complete===false))throw Error('The last page says the document continues, but the owner issued no continuation, so nothing was joined.');
   if(!next.read_handle&&total!=null&&page.offset+measure(chunk)!==total)throw Error('The pages do not add up to the owner\'s reported document size, so nothing was joined.');
   text+=chunk;
   if(text.length>MARKDOWN_READING_LIMIT)throw new LocalReadingRefusal('This document is longer than the rendered-reading limit. Keep reading its pages, or use Raw.');
   at=page.next_offset;handle=next.read_handle;
  }
  return text;
 }
 show(initial);
 return {destroy(){destroyed=true;sequence++;}};
}
