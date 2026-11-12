// Continuous PDF reading, with page canvases kept only near the viewport.
import {artifactHumanTarget,ownerHumanTarget,isKnownArtifactReadRoute,isKnownOwnerReadRoute} from './writing-owner-read.mjs';
import {sharedInspector,replacedByInspector} from './workspace-inspector.mjs';

export function pdfAnnotationAction(annotation,url,base=globalThis.location?.href){
  if(annotation.dest!=null)return {kind:'destination',destination:annotation.dest};
  if(['NextPage','PrevPage','FirstPage','LastPage','GoBack','GoForward'].includes(annotation.action))return {kind:'page-action',action:annotation.action};
  const raw=annotation.unsafeUrl||annotation.url;if(typeof raw!=='string'||!raw.trim())return null;
  if(raw.startsWith('#')){try{return {kind:'destination',destination:decodeURIComponent(raw.slice(1))};}catch{return null;}}
  const source=new URL(url,base),origin=new URL(base).origin,project=source.searchParams.get('project')||source.searchParams.get('corpus');
  if(source.origin===origin){
    const artifact=artifactHumanTarget(raw,{project,base});
    if(artifact)return {kind:'artifact',project,...artifact,label:artifact.path};
    const ownerRead=ownerHumanTarget(raw,{base});
    if(ownerRead&&ownerRead.project===project)return {kind:'owner-read',project,ownerRead,label:'Linked '+ownerRead.kind+' reading'};
    if(isKnownArtifactReadRoute(raw,{base})||isKnownOwnerReadRoute(raw,{base}))return null;
  }
  if(/^[a-z][a-z\d+.-]*:/i.test(raw)){try{const target=new URL(raw);if(['http:','https:','mailto:'].includes(target.protocol))return {kind:'external',url:target.href};}catch{}return null;}
  if(raw.startsWith('/')||raw.includes('\\'))return null;
  if(source.origin!==origin)return {kind:'external',url:new URL(raw,source).href};
  const path=source.pathname==='/research/artifact'?source.searchParams.get('path'):source.pathname==='/projection/pdf'?source.searchParams.get('file'):null;
  if(!project||!path)return {kind:'unavailable',reason:'This PDF has no project file identity for resolving a relative companion.'};
  return {kind:'companion',url:'/research/artifact?'+new URLSearchParams({project,path,scope:source.searchParams.get('scope')||'project',resolve:'pdf-link',uri:raw,...(source.searchParams.get('expected_sha256')?{expected_sha256:source.searchParams.get('expected_sha256')}:{})}),label:raw};
}

export function pdfAnnotationRect(rect,viewport){
  if(!Array.isArray(rect)||rect.length!==4||rect.some(value=>!Number.isFinite(value)))return null;
  const [x1,y1]=viewport.convertToViewportPoint(rect[0],rect[1]);
  const [x2,y2]=viewport.convertToViewportPoint(rect[2],rect[3]);
  return {left:Math.min(x1,x2),top:Math.min(y1,y2),width:Math.abs(x2-x1),height:Math.abs(y2-y1)};
}

export function appendPdfAnnotations(host,annotations,viewport,{url,base,onAction}){
  for(const annotation of annotations){const action=pdfAnnotationAction(annotation,url,base),rect=pdfAnnotationRect(annotation.rect,viewport);if(!action||!rect||!rect.width||!rect.height)continue;
    const link=document.createElement('a');link.className='wp-annotation';
    const label=annotation.contentsObj?.str||annotation.titleObj?.str||action.label||action.url||(action.kind==='destination'?'Go to '+(typeof action.destination==='string'?action.destination:'referenced PDF passage'):action.action||action.reason);
    const description=action.kind==='companion'?label+' · Open current project companion.':label;
    link.setAttribute('aria-label',description);link.title=description;Object.assign(link.style,Object.fromEntries(Object.entries(rect).map(([key,value])=>[key,value+'px'])));
    if(action.kind==='external'){link.href=action.url;link.target='_blank';link.rel='noopener noreferrer';}
    else{link.href='#';link.onclick=event=>{event.preventDefault();onAction(action);};}
    host.append(link);
  }
}

export async function pdfDestination(pdf,destination){
  const resolved=typeof destination==='string'?await pdf.getDestination(destination):destination;
  if(!Array.isArray(resolved)||!resolved.length)throw Error('The PDF destination is unavailable.');
  const index=Number.isInteger(resolved[0])?resolved[0]:await pdf.getPageIndex(resolved[0]);
  if(index<0||index>=pdf.numPages)throw Error('The PDF destination is outside the document.');
  return {page:index+1,destination:resolved};
}

export function pdfCompanionNotice(value){
  // Older resolvers verified the PDF/directory but did not pin companion bytes.
  return typeof value.notice==='string'&&value.notice?value.notice:'This link opens the current project file. Its match to this PDF edition has not been recorded.';
}

// Every PDF viewer is adopted by the one inspector at this door (workspace-inspector.mjs):
// the manuscript PDF (manuscript-editor readPdf, workspace-output), template previews and
// figure assets (writing-artifact, writing-evidence, research-card), literature PDFs and
// nested companion PDFs all arrive here. The inspector trail is the ONE return mechanism: a
// linked reader or companion PDF REPLACES this viewer, the trail entry's reopen descriptor
// carries the last reading position, and Back / Close on the child reopens this PDF there.
// Nested reads are bound to inspector.lineage(token), never to this viewer's own `closed`
// flag (replacement would falsify it). There is no viewer singleton: a second openPdf is a
// nested panel that REPLACES the first through adoption, and the first's reading position is
// pinned to its trail entry at release so the trail reopens it there. The reopen descriptor is
// the module-level factory `reopenPdf` with plain arguments. PDF bytes are never snapshotted.
// A caller's `onOpen` still runs after adoption.
const reopenPdf=(args,pin)=>openPdf(args.url,args.title,{notice:args.notice,onOpenArtifact:args.onOpenArtifact,initialPosition:pin?.position||args.initialPosition||null,onRendered:args.onRendered});
export async function openPdf(url,title='PDF preview',{notice='',onOpenArtifact=null,initialPosition=null,onRendered=null,onOpen=null}={}){
  const inspector=sharedInspector();let token=null;
  let lastPosition=initialPosition;
  if(!document.querySelector('link[data-writing-pdf]')){const css=document.createElement('link');css.rel='stylesheet';css.href='/shared/writing-pdf.css';css.dataset.writingPdf='';document.head.append(css);}
  const originRef=typeof WeakRef==='function'&&document.activeElement?new WeakRef(document.activeElement):{deref:()=>document.activeElement},dialog=document.createElement('dialog');dialog.className='writing-pdf';dialog.setAttribute('aria-labelledby','writing-pdf-title');
  dialog.innerHTML=`<div class="wp-tools"><header><h2 id="writing-pdf-title"></h2><button class="wp-close" aria-label="Close PDF preview">Close</button></header><nav aria-label="PDF pages"><button class="wp-back" disabled>Back</button><button class="wp-forward" disabled>Forward</button><button class="wp-prev">Previous</button><label>Page <input class="wp-page" type="number" min="1" value="1" aria-label="Go to PDF page"></label><button class="wp-go">Go</button><span class="wp-count"></span><button class="wp-next">Next</button><button class="wp-minus" aria-label="Zoom out">−</button><span class="wp-zoom">100%</span><button class="wp-plus" aria-label="Zoom in">+</button><button class="wp-fit">Fit width</button><a class="wp-download" download>Save PDF…</a></nav><p class="wp-status" role="status">Opening PDF…</p></div><div class="wp-pages" aria-label="Continuous PDF pages"></div>`;
  const find=s=>dialog.querySelector(s),host=find('.wp-pages'),status=find('.wp-status'),download=find('.wp-download');
  find('h2').textContent=title;download.href=url;
  const file=new URL(url,location.href).searchParams.get('file');
  download.download=file?file.split('/').pop().replace(/\.tex$/i,'.pdf'):(title==='PDF preview'?'Document':title.replace(/[^\p{L}\p{N}_-]+/gu,'-').replace(/^-|-$/g,''))+'.pdf';
  let loading,pdf,lib,observer,closed=false,renderReported=false,zoom=1,pageNumber=1,resizeTimer,version=0,fitMode='width',pageRatio=1.414;
  const fitPage=document.createElement('button');fitPage.textContent='Fit page';find('.wp-fit').after(fitPage);
  const pages=new Map(),tasks=new Map();
  function close(){if(dialog.open)dialog.close();else release();}
  function release(){if(closed)return;closed=true;version++;try{if(pdf)lastPosition=readingPosition();}catch{}if(lastPosition)inspector.pin(token,{position:lastPosition});observer?.disconnect();clearTimeout(resizeTimer);window.removeEventListener('resize',resize);for(const number of pages.keys())evict(number);loading?.destroy().catch(()=>{});dialog.remove();const origin=originRef.deref();if(origin?.isConnected&&!replacedByInspector(dialog))origin.focus();}
  function controls(){const back=backPositions.at(-1),forward=forwardPositions.at(-1);find('.wp-back').disabled=!back;find('.wp-forward').disabled=!forward;find('.wp-back').textContent=back?'Back to page '+back.page:'Back';find('.wp-forward').textContent=forward?'Forward to page '+forward.page:'Forward';find('.wp-prev').disabled=!pdf||pageNumber<=1;find('.wp-next').disabled=!pdf||pageNumber>=pdf.numPages;find('.wp-minus').disabled=!pdf||zoom<=.25;find('.wp-plus').disabled=!pdf||zoom>=2.5;}
  function goto(number){if(!pdf)return;pageNumber=Math.min(pdf.numPages,Math.max(1,Math.floor(Number(number)||1)));controls();const element=pages.get(pageNumber)?.element;if(element)dialog.scrollTop+=element.getBoundingClientRect().top-dialog.getBoundingClientRect().top-find('.wp-tools').offsetHeight-16;find('.wp-page').value=pageNumber;controls();}
  const backPositions=[],forwardPositions=[];
  function readingPosition(){const item=pages.get(pageNumber),bounds=item?.element.getBoundingClientRect(),height=bounds?.height||parseFloat(item?.element.style.height)||1;return {page:pageNumber,fraction:bounds?(dialog.getBoundingClientRect().top+find('.wp-tools').offsetHeight+16-bounds.top)/height:0};}
  function restorePosition(position){if(!position)return;goto(position.page);const item=pages.get(position.page),bounds=item?.element.getBoundingClientRect(),height=bounds?.height||parseFloat(item?.element.style.height)||1;dialog.scrollTop+=position.fraction*height;}
  async function follow(action){try{
    if(action.kind==='unavailable')throw Error(action.reason);
    if(action.kind==='destination'){
      const destination=await pdfDestination(pdf,action.destination);if(closed)return;backPositions.push(readingPosition());forwardPositions.length=0;goto(destination.page);
      const page=await pdf.getPage(destination.page),natural=page.getViewport({scale:1}),viewport=page.getViewport({scale:width()/natural.width}),dest=destination.destination;
      const top=dest[1]?.name==='XYZ'?dest[3]:['FitH','FitBH'].includes(dest[1]?.name)?dest[2]:null;
      if(Number.isFinite(top))dialog.scrollTop+=Math.max(0,viewport.convertToViewportPoint(0,top)[1]);
    }else if(action.kind==='page-action'){
      if(action.action==='GoBack'&&backPositions.length){const position=backPositions.pop();forwardPositions.push(readingPosition());restorePosition(position);}
      else if(action.action==='GoForward'&&forwardPositions.length){const position=forwardPositions.pop();backPositions.push(readingPosition());restorePosition(position);}
      else goto(({NextPage:pageNumber+1,PrevPage:pageNumber-1,FirstPage:1,LastPage:pdf.numPages})[action.action]||pageNumber);
    }else if(action.kind==='artifact'||action.kind==='owner-read'){
      const opener=document.activeElement,path=action.path||action.ownerRead.http.url;
      const options=action.kind==='artifact'?{scope:action.scope,expectedSha256:action.expectedSha256,artifactId:action.artifactId,artifactOwner:action.artifactOwner}:{ownerRead:action.ownerRead};
      options.opener=opener;options.isCurrent=inspector.lineage(token);   // current while this PDF is current or on the trail behind the reader
      status.textContent='Opening linked reading…';
      if(action.kind==='artifact'&&onOpenArtifact)await onOpenArtifact(path,action.label,{project:action.project,...options});
      else{const {openArtifact}=await import('/shared/writing-artifact.mjs');if(!options.isCurrent())return;await openArtifact({project:action.project,path,label:action.label,...options});}
      if(!closed)status.textContent='Close the linked reader to return to this PDF passage.';
    }else if(action.kind==='companion'){
      status.textContent='Opening linked companion…';const response=await fetch(action.url),value=await response.json();if(!response.ok)throw Error(value.error||'The companion could not be resolved.');if(closed)return;
      const safe=new URL(value.url,location.href);if(safe.origin!==location.origin||safe.pathname!=='/research/artifact')throw Error('The companion did not resolve to a project artifact.');
      const companionNotice=pdfCompanionNotice(value);status.textContent=companionNotice;
      if(value.kind==='pdf'){lastPosition=readingPosition();await openPdf(value.url,value.label,{notice:companionNotice,onOpenArtifact});}   // the companion REPLACES this viewer; the trail returns here at lastPosition
      else if(value.kind==='text'||value.kind==='image'){
        if(onOpenArtifact)await onOpenArtifact(value.path,value.label,{...(value.scope?{scope:value.scope}:{}),notice:companionNotice});
        else{const {openArtifact}=await import('/shared/writing-artifact.mjs');await openArtifact({project:value.project,path:value.path,label:value.label,scope:value.scope,notice:companionNotice});}
        status.textContent=companionNotice+' Close its reader to return to this PDF passage.';
      }
      else{const link=document.createElement('a');link.href=value.url;if(value.kind==='download')link.download=value.label;else{link.target='_blank';link.rel='noopener noreferrer';}document.body.append(link);link.click();link.remove();status.textContent='Opened '+value.label+'. '+companionNotice;}
    }
  }catch(error){if(!closed)status.textContent=error.message;}}
  function width(){const available=Math.max(100,Math.min(1060,host.clientWidth-24)),ds=getComputedStyle(dialog),hs=getComputedStyle(host),padding=[ds.paddingTop,ds.paddingBottom,hs.paddingTop,hs.paddingBottom].reduce((sum,n)=>sum+(parseFloat(n)||0),0);const pageFit=Math.max(80,dialog.clientHeight-find('.wp-tools').offsetHeight-padding-16)/pageRatio;return (fitMode==='page'?Math.min(available,pageFit):available)*zoom;}
  async function paint(number){
    const item=pages.get(number);if(!pdf||!item||item.canvas||tasks.has(number)||closed)return;
    const ticket=version,page=await pdf.getPage(number);if(closed||ticket!==version||!item.near||item.canvas||tasks.has(number))return;
    const natural=page.getViewport({scale:1});item.ratio=natural.height/natural.width;const w=width(),density=Math.min(devicePixelRatio||1,1.5),view=page.getViewport({scale:w/natural.width*density});
    const canvas=document.createElement('canvas');canvas.setAttribute('aria-label','PDF page '+number);canvas.width=Math.floor(view.width);canvas.height=Math.floor(view.height);canvas.style.width=w+'px';canvas.style.height=(view.height/density)+'px';
    item.element.style.height=(view.height/density)+'px';item.element.style.width=w+'px';item.element.append(canvas);item.canvas=canvas;
    const task=page.render({canvasContext:canvas.getContext('2d'),viewport:view});tasks.set(number,task);
    let rendered=false;
    try{await task.promise;rendered=true;}catch(error){if(error.name!=='RenderingCancelledException'&&!closed)status.textContent='Page '+number+': '+error.message;}
    finally{if(tasks.get(number)===task)tasks.delete(number);}
    if(closed||ticket!==version||!item.near||item.canvas!==canvas)return;
    if(rendered&&!renderReported){renderReported=true;onRendered?.({url,page:number,pages:pdf.numPages});}
    try{
      const [textResult,annotationResult]=await Promise.allSettled([page.getTextContent(),page.getAnnotations({intent:'display'})]);if(closed||ticket!==version||!item.near||item.canvas!==canvas)return;
      const viewport=page.getViewport({scale:w/natural.width}),links=document.createElement('div');links.className='wp-annotation-layer';appendPdfAnnotations(links,annotationResult.status==='fulfilled'?annotationResult.value:[],viewport,{url,base:location.href,onAction:follow});item.element.append(links);item.links=links;
      if(textResult.status!=='fulfilled')throw textResult.reason;
      const text=textResult.value,layer=document.createElement('div');layer.className='wp-text-layer';layer.style.setProperty('--scale-factor',viewport.scale);layer.style.setProperty('--total-scale-factor',viewport.scale);item.element.append(layer);item.textLayer=layer;
      item.textTask=new lib.TextLayer({textContentSource:text,container:layer,viewport});
      // Numeric dimensions also support WebKit versions without CSS round().
      layer.style.width=viewport.rawDims.pageWidth*viewport.scale+'px';layer.style.height=viewport.rawDims.pageHeight*viewport.scale+'px';await item.textTask.render();
      if(closed||ticket!==version||!item.near||item.canvas!==canvas)return;
      if(annotationResult.status!=='fulfilled')throw annotationResult.reason;
    }catch(error){if(error.name!=='AbortException'&&!closed&&ticket===version)status.textContent='Page '+number+' text or links unavailable: '+error.message;}
  }
  function evict(number){const item=pages.get(number);tasks.get(number)?.cancel();tasks.delete(number);item?.textTask?.cancel();if(item){item.textTask=null;item.textLayer?.remove();item.textLayer=null;item.links?.remove();item.links=null;}if(item?.canvas){item.canvas.width=item.canvas.height=0;item.canvas.remove();item.canvas=null;}}
  function observe(){observer?.disconnect();observer=new IntersectionObserver(entries=>{for(const entry of entries){const number=Number(entry.target.dataset.page),item=pages.get(number);item.near=entry.isIntersecting;if(item.near)paint(number);else evict(number);}},{root:dialog,rootMargin:'600px 0px'});for(const item of pages.values())observer.observe(item.element);}
  function resize(){const position=readingPosition();clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(!pdf||closed)return;version++;for(const [n,item]of pages){evict(n);item.element.style.width=width()+'px';item.element.style.height=(width()*item.ratio)+'px';}restorePosition(position);observe();},160);}
  function setZoom(value){zoom=Math.max(.25,Math.min(2.5,value));find('.wp-zoom').textContent=Math.round(zoom*100)+'%';controls();resize();}
  fitPage.onclick=()=>{fitMode='page';setZoom(1);};
  find('.wp-back').onclick=()=>follow({kind:'page-action',action:'GoBack'});find('.wp-forward').onclick=()=>follow({kind:'page-action',action:'GoForward'});
  find('.wp-close').onclick=close;dialog.addEventListener('close',release);find('.wp-prev').onclick=()=>goto(Number(find('.wp-page').value)-1);find('.wp-next').onclick=()=>goto(Number(find('.wp-page').value)+1);find('.wp-page').onchange=e=>goto(e.target.value);find('.wp-page').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();goto(e.target.value);}};find('.wp-go').onclick=()=>goto(find('.wp-page').value);find('.wp-fit').onclick=()=>setZoom(1);find('.wp-plus').onclick=()=>setZoom(zoom*1.2);find('.wp-minus').onclick=()=>setZoom(zoom/1.2);
  find('.wp-fit').onclick=()=>{fitMode='width';setZoom(1);};
  dialog.addEventListener('scroll',()=>{const top=dialog.getBoundingClientRect().top+find('.wp-tools').offsetHeight+20;for(const [n,item]of pages){const bounds=item.element.getBoundingClientRect();if(bounds.bottom>top){pageNumber=n;if(document.activeElement!==find('.wp-page'))find('.wp-page').value=n;break;}}controls();},{passive:true});
  document.body.append(dialog);
  token=inspector.adopt(dialog,{kind:'pdf',title,reopen:{factory:reopenPdf,args:{url,title,notice,onOpenArtifact,initialPosition,onRendered}}}).token;
  onOpen?.(dialog);dialog.showModal();window.addEventListener('resize',resize);
  try{
    lib=await import('/shared/pdfjs/pdf.min.mjs');lib.GlobalWorkerOptions.workerSrc='/shared/pdfjs/pdf.worker.min.mjs';loading=lib.getDocument({url});pdf=await loading.promise;if(closed)return;
    const metadata=await pdf.getMetadata();if(['PDF preview','Last compiled document','Exported document'].includes(title)&&metadata.info?.Title)find('h2').textContent=metadata.info.Title;
    if(!file&&metadata.info?.Title)download.download=metadata.info.Title.replace(/[^\p{L}\p{N}_-]+/gu,'-')+'.pdf';
    find('.wp-count').textContent='of '+pdf.numPages+' · continuous view';find('.wp-page').max=pdf.numPages;
    const first=await pdf.getPage(1),size=first.getViewport({scale:1}),ratio=size.height/size.width;pageRatio=ratio;if(pdf.numPages===1)fitMode='page';controls();
    for(let n=1;n<=pdf.numPages;n++){const element=document.createElement('section');element.className='wp-page-sheet';element.dataset.page=n;element.setAttribute('aria-label','Page '+n);element.style.width=width()+'px';element.style.height=(width()*ratio)+'px';const label=document.createElement('span');label.className='wp-page-label';label.textContent='Page '+n;element.append(label);host.append(element);pages.set(n,{element,ratio,canvas:null,near:false});}
    status.textContent=notice||'Scroll to read the document.';if(initialPosition)restorePosition(initialPosition);observe();
  }catch(error){if(!closed){status.textContent='The PDF could not be opened.';download.hidden=true;for(const control of dialog.querySelectorAll('.wp-tools nav button,.wp-tools nav input'))control.disabled=true;const detail=document.createElement('details'),summary=document.createElement('summary'),message=document.createElement('p');summary.textContent='Error details';message.textContent=error.message;detail.append(summary,message);host.append(detail);const retry=document.createElement('button');retry.textContent='Try again';retry.onclick=()=>openPdf(url,title,{notice,onOpenArtifact,initialPosition});host.append(retry);}}
}
