// publication-editions.mjs — named PDF editions of the one canonical source (F-PUB-1).
// Purpose: list each declared publication edition by title with the owner's state word, and run
//   the owner-issued Prepare, Build, Read PDF and Save PDF (as its companion file name) actions;
//   a direct return to the canonical source. Target pins stay inside the details disclosure.
// Ownership: /authoring/document?target_kind=publication-edition (laplace.publication-editions/1),
//   /authoring/build (prepare, build_target), /projection/pdf (recorded output receipts).
// Public contract: mountPublicationEditions(host,{project,request,onReadPdf,onOpenSource,readOnly,status,
//   hasDocumentDraft,admitDocumentBuild}) — the same canonical-document draft admission as the Manuscript PDF card;
//   editionPrepareSubmission, editionBuildSubmission, editionPdfURL.
// Currentness: Prepare/Build re-read the canonical document and admit it (unsaved edits refuse, nothing is
//   sent), then re-read the edition and send only if its displayed identity is unchanged; a refusal is
//   shown and the list re-read; a building edition is re-read until its owner reports a terminal state.
// Storage: none.
import {validEditionTarget,sameEditionTarget} from './derived-output.mjs';
const pin=value=>typeof value==='string'&&/^sha256:[0-9a-f]{64}$/.test(value);
const SCHEMA='laplace.publication-editions/1';

function local(http,method,base){
  if(http?.method!==method||typeof(http.url||http.route)!=='string')throw Error('The edition owner supplied no matching '+method+' action.');
  const url=new URL(http.url||http.route,base);
  if(url.origin!==new URL(base).origin||url.hash||url.username||url.password)throw Error('The edition action leaves its local owner.');
  return url;
}

export function editionPrepareSubmission(row,project,base=globalThis.location?.href||'http://local/'){
  const action=row?.prepare_action,url=local(action?.http,'POST',base),payload=action?.payload||{};
  const prepare=payload.prepare||{};
  if(action.operation!=='build'||action.project!==project||url.pathname!=='/authoring/build'||url.search||
     Object.keys(payload).join(',')!=='prepare'||Object.keys(prepare).sort().join(',')!=='definition_revision,edition'||
     prepare.edition!==row.name||prepare.definition_revision!==row.definition_revision||!pin(row.definition_revision)){
    throw Error('Prepare does not match the displayed edition definition. Refresh the editions.');
  }
  return {url:url.pathname,payload:{project,...structuredClone(payload)}};
}

export function editionBuildSubmission(row,project,base=globalThis.location?.href||'http://local/'){
  const action=row?.build_action,url=local(action?.http,'POST',base);
  if(!validEditionTarget(row.build_target,project)||row.build_target.edition!==row.name||action.operation!=='build'||
     action.project!==project||url.pathname!=='/authoring/build'||url.search||Object.keys(action.payload||{}).length!==1||
     !sameEditionTarget(action.payload.build_target,row.build_target)){
    throw Error('Build does not match the displayed edition target. Refresh the editions.');
  }
  return {url:url.pathname,payload:{project,build_target:structuredClone(row.build_target)}};
}

export function editionPdfURL(row,project,base=globalThis.location?.href||'http://local/'){
  const read=row?.pdf_read;if(!read)return null;
  const url=local(read.http,'GET',base),recorded=row.recorded_output;let target;
  try{target=JSON.parse(url.searchParams.get('build_target'));}catch{target=null;}
  if(url.pathname!=='/projection/pdf'||url.searchParams.get('corpus')!==project||
     [...url.searchParams.keys()].some(key=>!['file','corpus','build_target','expected_content_revision'].includes(key)||url.searchParams.getAll(key).length!==1)||
     !validEditionTarget(read.build_target,project)||read.build_target.edition!==row.name||!sameEditionTarget(target,read.build_target)||
     !sameEditionTarget(recorded?.build_target,read.build_target)||url.searchParams.get('file')!==read.build_target.root.replace(/\.tex$/i,'.pdf')||
     !pin(read.content_revision)||read.content_revision!==recorded.content_revision||read.content_revision!==url.searchParams.get('expected_content_revision')||
     recorded.output_current!==true||typeof read.current!=='boolean'||read.current&&row.status!=='READY'){
    throw Error('The saved edition PDF has no matching target and output receipt. No other PDF was substituted.');
  }
  return url.pathname+url.search;
}

const TONE={READY:'ok',BUILDING:'running',FAILED:'blocked',STALE:'attention',PREPARATION_STALE:'attention',UNPREPARED:'neutral',UNBUILT:'neutral'};
const NOTE={READY:'PDF matches the saved canonical source.',BUILDING:'Building this edition…',FAILED:'The latest build of this edition failed.',
  STALE:'Its chapter or shared inputs changed since the last PDF.',PREPARATION_STALE:'Its definition or the shared root changed; prepare it again.',
  UNPREPARED:'Not prepared yet.',UNBUILT:'Prepared; no PDF built yet.'};

export async function mountPublicationEditions(host,{project,request,onReadPdf,onOpenSource=null,readOnly=false,status=()=>{},
  hasDocumentDraft=()=>false,admitDocumentBuild=()=>{}}){
  const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
  const panel=el('section','','output-document publication-editions');panel.hidden=true;host.append(panel);
  let alive=true,pending=false,timer=null,value=null,message='',dirty=false;
  const documentURL='/authoring/document?'+new URLSearchParams({project}),editionsURL='/authoring/document?'+new URLSearchParams({project,target_kind:'publication-edition'});
  // The Manuscript PDF card's admission: the canonical document, re-read now, must have no unsaved draft;
  // then the edition, re-read now, must still carry the identity the author was shown.
  async function admitted(row,same){
    await admitDocumentBuild(await request(documentURL));
    const fresh=(await request(editionsURL))?.editions?.find(other=>other.name===row.name);
    if(!fresh||!same(fresh))throw Error('This edition changed since it was displayed; review it and try again.');
    return fresh;
  }
  const current=()=>alive&&panel.isConnected;
  const act=(label,run,cls='')=>{const b=el('button',label,cls);b.type='button';b.onclick=async()=>{if(pending)return;pending=true;b.disabled=true;
    try{await run();message='';}catch(error){message=error.message;status(error.message,true);}finally{pending=false;if(current())await load().catch(fail);}};return b;};
  function fail(error){if(!current())return;message=error.message;paint();}
  function paint(){
    if(!current()||!value)return;
    panel.hidden=!(value.editions||[]).length;panel.replaceChildren();
    const head=el('header','','object-header');head.append(el('span','Publication editions','object-eyebrow'),el('h3','Editions of this manuscript','object-title'));
    const source=value.canonical_source||{};
    const back=el('p','Canonical source: '+(source.root||'unavailable'));
    if(onOpenSource&&source.read)back.append(' ',act('Open canonical source',()=>onOpenSource(source.read)));
    panel.append(head,back);if(dirty)panel.append(el('p','Unsaved manuscript edits are not included in edition PDFs; save them first.'));if(message){const note=el('p',message,'error');note.setAttribute('role','status');panel.append(note);}
    for(const row of value.editions||[]){
      const card=el('article','','publication-edition');card.dataset.edition=row.name;
      const title=el('div','','chip-row');const chip=el('span',String(row.status).toLowerCase().replaceAll('_',' '),'state-chip');chip.setAttribute('data-tone',TONE[row.status]||'neutral');
      title.append(el('h4',row.title),chip);card.append(title,el('p',row.reason&&!NOTE[row.status]?row.reason:(NOTE[row.status]||'Inspect this edition.')));
      const actions=el('div','','workflow-actions');
      const held='Save the current manuscript edits before preparing or building an edition.';
      if(!readOnly&&['UNPREPARED','PREPARATION_STALE'].includes(row.status)){const b=act('Prepare edition',async()=>{
        const a=editionPrepareSubmission(await admitted(row,fresh=>fresh.definition_revision===row.definition_revision),project);await request(a.url,a.payload);},'primary');
        b.disabled=dirty;if(dirty)b.title=held;actions.append(b);}
      if(!readOnly&&row.build_target){const b=act(row.status==='BUILDING'?'Building…':'Build edition PDF',async()=>{
        const a=editionBuildSubmission(await admitted(row,fresh=>sameEditionTarget(fresh.build_target,row.build_target)),project);await request(a.url,a.payload);});
        b.disabled=row.status==='BUILDING'||dirty;if(dirty)b.title=held;actions.append(b);}
      const pdf=editionPdfURL(row,project);
      if(pdf){actions.append(act(row.pdf_read.current?'Read PDF':'Read saved PDF',()=>onReadPdf?.(pdf,row.title,{notice:row.pdf_read.current?'This edition PDF matches the saved canonical source.':'Saved edition PDF; current inputs or the latest build differ.'})));
        const save=el('a',row.pdf_read.current?'Save PDF':'Save saved PDF','workflow-link');save.href=pdf;save.download=row.download_name;save.title='Saved as '+row.download_name+' so companion links resolve beside its siblings';actions.append(save);}
      card.append(actions);
      const details=el('details');details.append(el('summary','Edition details'));
      details.append(el('p','Chapters: '+row.chapters.join(', ')),el('p','Companions: '+((row.companions||[]).map(c=>c.title+' ('+c.file+')').join('; ')||'none')),el('p','Wrapper: '+row.file));
      for(const ref of row.unsupported_references||[])details.append(el('p','Unsupported reference '+ref.label+' in '+ref.file+(ref.companion?' — read edition '+ref.companion:'')));
      if(row.build_target)details.append(el('p','Target input revision: '+row.build_target.input_revision));
      if(row.current_build?.log_tail&&row.status==='FAILED')details.append(el('pre',row.current_build.log_tail));
      details.open=row.status==='FAILED';card.append(details);panel.append(card);
    }
  }
  async function load(){
    clearTimeout(timer);
    const next=await request(editionsURL);
    if(!current())return;
    if(next?.schema_version!==SCHEMA||next.project!==project||!Array.isArray(next.editions))throw Error('The edition owner returned another project or an incomplete observation.');
    const canonical=next.editions.length&&!readOnly?await request(documentURL):null;
    if(!current())return;
    dirty=!!canonical&&!!hasDocumentDraft(canonical);value=next;paint();
    if(next.editions.some(row=>row.status==='BUILDING'))timer=setTimeout(()=>load().catch(fail),1000);
  }
  try{await load();}catch(error){value=null;panel.hidden=true;}
  return {refresh:()=>load(),get data(){return value;},destroy(){alive=false;clearTimeout(timer);panel.remove();}};
}
