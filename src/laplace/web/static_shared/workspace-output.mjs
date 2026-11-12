// workspace-output.mjs — Figures & output (M5 C7).
// Purpose: the Manuscript PDF card (object header with document chips and the owner's
//   freshness sentence; Build primary; Read / Save; Build details on failure), the derived output
//   card (derived-output.mjs), the publication editions card (publication-editions.mjs) and the figure gallery (name, readiness, preview, caption, Open in
//   manuscript, Edit caption, Render, Place, Evidence).
// Ownership: /authoring/document (status, current_build, read_handles), /authoring/build,
//   /visuals/state and /visuals/render; the walk document (/walk/doc) only for figure blocks.
// Public contract: mountOutput(host,{project,request,status,onOpenPassage,onOpenArtifact,
//   onDiscuss,onPlace,onEvidence,onDocumentSetup,onOpenSource,hasDocumentDraft,admitDocumentBuild,...}).
// Currentness: Build re-reads the document basis and admits it through the caller before the
//   build request; a running build is followed by the shared cancellation control.
// Storage: none.
import {mountDerivedOutput,mountBuildCancellation} from './derived-output.mjs';
import {mountPublicationEditions} from './publication-editions.mjs';
import {manuscriptPdfState,documentPdfURL,documentPdfNotice} from './manuscript-document-view.mjs';
import {renderVisualReadiness,visualRepairPrompt,visualPlacementReason} from '/shared/research-card.mjs';
import {openPdf} from '/shared/writing-pdf.mjs';
import {objectHeader,documentChips,stateChip,presentationStyles,declareControl} from './workspace-presentation.mjs';
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
const url=(path,args)=>path+'?'+new URLSearchParams(args);
export async function mountOutput(host,options){
  const {project,request,status=()=>{},onOpenPassage,onOpenArtifact,onDiscuss,onPlace,onEvidence,onDirty=()=>{},onChanged=()=>{},onDocumentSetup=null,onOpenSource=null,hasDocumentDraft=()=>false,admitDocumentBuild=()=>{}}=options;
  if(!document.querySelector('[data-writing-workflows]')){const css=el('link');css.rel='stylesheet';css.href='/shared/workspace-workflows.css';css.dataset.writingWorkflows='';document.head.append(css);}
  const readPdf=(url,title)=>openPdf(url,title,{onOpenArtifact});
  host.classList.add('workspace-output');host.replaceChildren(el('h2','Figures & output'));
  const run=fn=>async()=>{try{await fn();}catch(error){status(error.message,true);}};
  const button=(label,fn,cls='')=>{const b=el('button',label,cls);b.type='button';b.onclick=run(async()=>{b.disabled=true;try{await fn();}finally{b.disabled=false;}});return b;};
  const [doc,visuals]=await Promise.all([request(url('/walk/doc',{corpus:project})),request(url('/visuals/state',{project}))]);
  if(!host.isConnected)return;
  // THE MANUSCRIPT PDF CARD (M5 C7): an object header (eyebrow, title, document chips, the
  // owner's freshness sentence) with one primary action (Build) and the read/save actions.
  presentationStyles();
  const output=el('section','','output-document');output.setAttribute('data-control','output:document');const headerHost=el('div');const buildStatus=el('p','','workflow-state'),buildActions=el('div','','workflow-actions action-row');output.append(headerHost,buildStatus,buildActions);host.append(output);
  const buildControls=mountBuildCancellation(output,{project,request,onTerminal:()=>paintBuild(),onInspect:()=>paintBuild(true),onError:error=>status(error.message,true)});
  async function paintBuild(){
    const replaceJob=arguments[0]===true;
    if(!output.isConnected)return;const current=await request(url('/authoring/document',{project}));if(!output.isConnected)return;
    const build=current.current_build||{},dirty=hasDocumentDraft(current),failed=current.status==='FAILED';buildControls.observe(build,{replace:replaceJob});
    headerHost.replaceChildren(objectHeader({eyebrow:'Manuscript PDF',title:doc.title||'Manuscript PDF',chips:documentChips(current,dirty),summary:documentPdfNotice(current,dirty)}));
    buildStatus.textContent=build.running?'Building…':'';buildActions.replaceChildren();
    const compile=button(build.running?'Building…':'Build manuscript PDF',async()=>{const basis=await request(url('/authoring/document',{project}));await admitDocumentBuild(basis);const receipt=await request('/authoring/build',{project});if(receipt?.build_job)await buildControls.follow(receipt);await paintBuild();},'primary');declareControl(compile,'output:build');compile.disabled=!!build.running||buildControls.active||dirty;if(dirty)compile.title='Save the current manuscript edits before building.';buildActions.append(compile);
    const pdf=documentPdfURL(current);if(pdf){buildActions.append(button(current.status==='READY'?'Read PDF':'Read saved PDF',()=>openPdf(pdf,doc.title||'Manuscript PDF',{notice:documentPdfNotice(current,hasDocumentDraft(current)),onOpenArtifact})));const save=el('a',current.status==='READY'?'Save PDF':'Save existing PDF','workflow-link');save.href=pdf;save.download=(doc.title||'manuscript')+'.pdf';buildActions.append(save);}
    output.querySelector('details')?.remove();if(failed||build.reason){const details=el('details');details.open=failed;details.append(declareControl(el('summary',build.state==='cancelled'?'Stopped build':failed?'Build error':'Build details'),'output:build-details'));if(build.reason||build.error)details.append(el('p',build.reason||build.error));if(build.log_tail)details.append(el('pre',build.log_tail));output.append(details);}if(build.running&&!build.build_job)setTimeout(()=>run(paintBuild)(),1000);
  }
  await paintBuild();
  await mountDerivedOutput(host,{project,request,status,onReadPdf:(url,title,options)=>openPdf(url,title,{...options,onOpenArtifact})});
  await mountPublicationEditions(host,{project,request,status,onOpenSource,hasDocumentDraft,admitDocumentBuild,onReadPdf:(url,title,options)=>openPdf(url,title,{...options,onOpenArtifact})});
  const figures=(doc.sections||[]).flatMap(section=>(section.blocks||[]).filter(b=>b.kind==='figure').map(b=>({...b,section_title:section.title}))),used=new Set();
  const gallery=el('section');const head=el('div','','output-section-heading');head.append(el('h3',`Figures · ${(visuals.specs||[]).length+figures.filter(b=>!(visuals.specs||[]).some(s=>b.label==='fig:'+s.id||b.spec_id===s.id)).length}`),declareControl(button('Develop a figure',()=>onDiscuss('Develop a figure for the current argument. Read the relevant concepts, evidence and manuscript passage, produce and inspect the figure, link its source/results and place it where it explains the argument.')),'output:develop-figure'));gallery.append(head);const cards=el('div','','figure-gallery');gallery.append(cards);host.append(gallery);
  const addFigure=(spec,block)=>{
    const card=el('article','','output-figure');if(spec)card.dataset.visualId=spec.id;
    const name=spec?.title||block?.label||'Manuscript figure';card.append(el('h4',name));const current=spec?.render_freshness||'MANUSCRIPT SOURCE';card.append(el('p',current==='CURRENT'?'Rendered from current inputs':current==='STALE'?'Last render · inputs or evidence changed':current==='MANUSCRIPT SOURCE'?'Included in manuscript':'Not rendered','workflow-state'));
    const png=spec?.render?.outputs?.find(p=>p.endsWith('.png'));
    const included=block?.images?.[0],includedPath=included?.file?.startsWith(doc.manuscript_dir+'/')?included.file.slice(doc.manuscript_dir.length+1):null;
    // PDF-only renders use the artifact door's existing PNG preview.
    const pdfOutput=spec?.render?.outputs?.find(p=>p.endsWith('.pdf'));
    const imageUrl=png?url('/research/artifact',{project,path:png,scope:'manuscript'}):includedPath&&/\.pdf$/i.test(includedPath)?url('/research/artifact',{project,path:includedPath,scope:'manuscript',preview:'png'}):pdfOutput?url('/research/artifact',{project,path:pdfOutput,scope:'manuscript',preview:'png'}):block?.image;
    if(imageUrl){const image=el('img');image.src=imageUrl;image.alt=block?.caption||spec?.caption||name;image.loading='lazy';image.onerror=()=>image.replaceWith(el('p','This preview file is unavailable. Open the manuscript figure or render it again.','workflow-empty'));image.onclick=run(async()=>{const pdf=spec?.render?.outputs?.find(p=>p.endsWith('.pdf'));if(pdf)await readPdf(url('/research/artifact',{project,path:pdf,scope:'manuscript'}),name);else if(block?.src)await onOpenPassage(block.src);});card.append(image);}else card.append(el('p','A rendered preview will appear here.','workflow-empty'));
    if(spec?.currentness?.output_error)card.append(el('p','The displayed file differs from the recorded render. '+spec.currentness.output_error,'error'));
    if(spec?.placement_caption?.status==='DIFFERS')card.append(el('p','The figure brief caption differs from the manuscript. Use Edit caption to change the authored manuscript text.','workflow-state'));
    card.append(el('p',block?block.caption||'No caption in the manuscript.':spec?.caption||spec?.question||''));
    if(block)card.append(el('p',block.section_title||block.src?.file,'muted'));else card.append(el('p','Not placed in the manuscript','muted'));
    const actions=el('div','','workflow-actions');if(block?.src)actions.append(button('Open in manuscript',()=>onOpenPassage(block.src)),button('Edit caption',()=>onOpenPassage(block.caption_src||block.src,{edit:true})));
    if(spec){const readiness=renderVisualReadiness(card,spec),render=button(spec.render?'Render again':'Render figure',async()=>{await request('/visuals/render',{project,id:spec.id});await mountOutput(host,options);await onChanged();});render.disabled=readiness.blocked;if(readiness.blocked)render.title=readiness.reason;actions.append(render);if(!block){const reason=visualPlacementReason(spec),place=button('Place in manuscript',()=>onPlace(spec));place.disabled=!!reason;if(reason)place.title=reason;actions.append(place);}
      if(spec.result_ids?.length)for(const id of spec.result_ids)actions.append(button('Evidence · '+id,()=>onEvidence(id)));
      actions.append(button(readiness.blocked?'Complete with Eigen':'Revise with Eigen',()=>onDiscuss(visualRepairPrompt(spec))));
      const details=el('details');details.append(el('summary','Figure brief and source'));
      const form=el('form');for(const [key,label]of [['title','Title'],['question','Question this figure answers'],['caption','Caption']]){const l=el('label',label),input=el(key==='caption'?'textarea':'input');input.name=key;input.value=spec[key]||'';input.oninput=()=>onDirty(true);l.append(input);form.append(l);}form.append(el('button','Save figure brief'));form.onsubmit=async event=>{event.preventDefault();await run(async()=>{const {render_readiness,...authored}=spec;const changed={...authored,...Object.fromEntries(new FormData(form))};await request('/visuals/create',{project,spec:changed,expected_revision:spec.spec_revision});onDirty(false);status('Figure brief saved. Render again to update the figure; use Edit caption for the current manuscript caption.');await mountOutput(host,options);})();};details.append(form);
      const source=spec.source||spec.source_data;if(source)details.append(el('p',source,'muted'),button('Inspect source',async()=>{const data=await request(url('/research/artifact',{project,path:source,scope:'project',format:'json'}));details.querySelector('[data-visual-source]')?.remove();const pre=el('pre',data.content||'Source is not readable text.');pre.dataset.visualSource='';details.append(pre);}));card.append(actions,details);
    }else card.append(actions);
    cards.append(card);
  };
  for(const spec of visuals.specs||[]){const block=figures.find(b=>b.label==='fig:'+spec.id||b.spec_id===spec.id);if(block)used.add(block.id);addFigure(spec,block);}
  for(const block of figures)if(!used.has(block.id))addFigure(null,block);
  if(!cards.children.length)cards.append(el('p','No figures yet. Develop one from a manuscript request or add figure source directly in the editor.','workflow-empty'));
  if(onDocumentSetup)host.append(declareControl(button('Open document setup',onDocumentSetup),'output:document-setup'));
}
