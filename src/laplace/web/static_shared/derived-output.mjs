
// wave 13 id sweep: control ids by tag and label (begin)
import {declareControl} from './workspace-presentation.mjs';
// wave 13 id sweep: control ids (end)// derived-output.mjs — derived (reader-plan) output and build-job custody (M5 C7).
// Purpose: the derived output card (object header with the owner's status word as its chip,
//   Build derived PDF, Read derived PDF, Refresh, Target and build details) and the shared
//   build cancellation control used by the manuscript band, Figures & output and the template
//   inspector.
// Ownership: /work/derived-output (status, build_target, pdf_read), /authoring/build (jobs),
//   /authoring/build/cancel; every target, job and preview ref is validated against the project
//   before it is sent (validDerivedTarget, validBuildJob, validTemplatePreviewRef, ...).
// Public contract: mountDerivedOutput(host,{project,request,initial,onReadPdf,readOnly});
//   mountBuildCancellation(host,{project,request,onStatus,onTerminal,onInspect,onError});
//   derivedBuildSubmission, derivedStatusURL, derivedPdfURL, buildJobStatusURL,
//   buildCancelSubmission, buildCancelAcknowledged, sameBuildJob, sameBuildTarget.
// Currentness: the displayed basis is the inspected value; a click never swaps in an unseen
//   target; a running job is followed through its status read until terminal.
// Storage: none.
const targetFields = ['schema_version', 'kind', 'project', 'root', 'plan_path',
  'plan_revision', 'selection_identity', 'input_revision'];
const pin = value => typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value);
const relative = value => typeof value === 'string' && value.length > 0 &&
  !value.startsWith('/') && !value.includes('\\') &&
  !value.split('/').includes('..') && !/[\u0000-\u001f]/.test(value);

export function validDerivedTarget(target, project = target?.project) {
  return !!target && typeof target === 'object' && !Array.isArray(target) &&
    Object.keys(target).length === targetFields.length &&
    targetFields.every(key => typeof target[key] === 'string' && target[key]) &&
    target.schema_version === 'laplace.build-target/1' && target.kind === 'derived' &&
    target.project === project && relative(target.root) && /\.tex$/i.test(target.root) &&
    relative(target.plan_path) && pin(target.plan_revision) &&
    pin(target.selection_identity) && pin(target.input_revision);
}

const candidateTargetFields=['schema_version','kind','project','root','candidate_ref','selection_identity','input_revision'];
export function validCandidateTarget(target,project=target?.project){
  const ref=target?.candidate_ref;
  return !!target&&typeof target==='object'&&!Array.isArray(target)&&Object.keys(target).length===candidateTargetFields.length&&candidateTargetFields.every(key=>Object.hasOwn(target,key))&&
    target.schema_version==='laplace.build-target/1'&&target.kind==='candidate'&&target.project===project&&typeof project==='string'&&!!project&&
    relative(target.root)&&/\.tex$/i.test(target.root)&&pin(target.selection_identity)&&pin(target.input_revision)&&
    !!ref&&Object.keys(ref).sort().join(',')==='id,version'&&/^PROP-[0-9a-f]{32}$/.test(ref.id||'')&&pin(ref.version);
}
// A publication edition (writing.publication_editions): one named PDF edition of the canonical source.
const editionTargetFields=['schema_version','kind','project','edition','root','source_root','selection_identity','definition_revision','preparation_revision','input_revision'];
export function validEditionTarget(target,project=target?.project){
  return !!target&&typeof target==='object'&&!Array.isArray(target)&&Object.keys(target).length===editionTargetFields.length&&
    editionTargetFields.every(key=>typeof target[key]==='string'&&target[key])&&target.schema_version==='laplace.build-target/1'&&
    target.kind==='publication-edition'&&target.project===project&&/^[a-z0-9][a-z0-9-]{0,47}$/.test(target.edition)&&
    relative(target.root)&&/\.tex$/i.test(target.root)&&relative(target.source_root)&&/\.tex$/i.test(target.source_root)&&
    ['selection_identity','definition_revision','preparation_revision','input_revision'].every(key=>pin(target[key]));
}
export const sameEditionTarget=(left,right)=>validEditionTarget(left)&&validEditionTarget(right)&&editionTargetFields.every(key=>left[key]===right[key]);
export const validBuildTarget=(target,project=target?.project)=>validDerivedTarget(target,project)||validCandidateTarget(target,project)||validEditionTarget(target,project);
export function sameBuildTarget(left,right){
  return validBuildTarget(left)&&validBuildTarget(right)&&left.kind===right.kind&&
    (left.kind==='derived'?sameDerivedTarget(left,right):left.kind==='publication-edition'?sameEditionTarget(left,right):candidateTargetFields.filter(key=>key!=='candidate_ref').every(key=>left[key]===right[key])&&
      left.candidate_ref.id===right.candidate_ref.id&&left.candidate_ref.version===right.candidate_ref.version);
}

export const validTemplateCandidateRef=value=>!!value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')==='id,version'&&/^PROP-[0-9a-f]{32}$/.test(value.id||'')&&pin(value.version);
export function validTemplatePreviewRef(value,project,candidateRef){
  const fields=['schema_version','build_job','build_receipt_id','observed_input_revision','output'];
  return !!value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===fields.length&&fields.every(key=>Object.hasOwn(value,key))&&
    value.schema_version==='laplace.template-preview-ref/1'&&validBuildJob(value.build_job,project)&&value.build_job.target_kind==='candidate'&&
    validTemplateCandidateRef(candidateRef)&&(value.build_job.build_target.candidate_ref.id===candidateRef.id&&value.build_job.build_target.candidate_ref.version===candidateRef.version)&&
    /^ART-[0-9a-f]{32}$/.test(value.build_receipt_id||'')&&pin(value.observed_input_revision)&&
    !!value.output&&Object.keys(value.output).sort().join(',')==='content_revision,file'&&relative(value.output.file)&&/\.pdf$/i.test(value.output.file)&&pin(value.output.content_revision);
}
export function sameDerivedTarget(left, right) {
  return validDerivedTarget(left) && validDerivedTarget(right) &&
    targetFields.every(key => left[key] === right[key]);
}

export function validBuildJob(job, project = job?.project) {
  const keys=['schema_version','id','project','root','target_kind','selection_identity','input_revision'];
  if(['derived','candidate','publication-edition'].includes(job?.target_kind))keys.push('build_target');
  return !!job && typeof job==='object' && !Array.isArray(job) &&
    Object.keys(job).length===keys.length && keys.every(key=>Object.hasOwn(job,key)) &&
    job.schema_version==='laplace.build-job/1' && /^BLD-[0-9a-f]{32}$/.test(job.id||'') &&
    typeof project==='string' && !!project && job.project===project && relative(job.root) && /\.tex$/i.test(job.root) &&
    ['manuscript','derived','candidate','publication-edition'].includes(job.target_kind) && pin(job.selection_identity) && pin(job.input_revision) &&
    (job.target_kind==='manuscript' || validBuildTarget(job.build_target,project) && job.build_target.kind===job.target_kind &&
      job.root===job.build_target.root && job.selection_identity===job.build_target.selection_identity && job.input_revision===job.build_target.input_revision);
}

export function sameBuildJob(left,right) {
  return validBuildJob(left) && validBuildJob(right) &&
    ['schema_version','id','project','root','target_kind','selection_identity','input_revision'].every(key=>left[key]===right[key]) &&
    (left.target_kind==='manuscript' || sameBuildTarget(left.build_target,right.build_target));
}

export function buildJobStatusURL(value,project,base=globalThis.location?.href||'http://local/') {
  const read=value?.job_status_read,url=localURL(read?.http,'GET',base);
  let job;try{job=JSON.parse(url.searchParams.get('build_job'));}catch{job=null;}
  if(!validBuildJob(value?.build_job,project)||read.operation!=='build_status'||
    Object.keys(read.payload||{}).length!==1||!sameBuildJob(read.payload.build_job,value.build_job)||
    url.pathname!=='/authoring/build'||url.searchParams.get('project')!==project||!sameBuildJob(job,value.build_job)||
    [...url.searchParams.keys()].some(key=>!['project','build_job'].includes(key)||url.searchParams.getAll(key).length!==1)) {
    throw Error('The build status read does not match this exact job. Inspect the current output.');
  }
  return url.pathname+url.search;
}

export function buildCancelSubmission(value,project,base=globalThis.location?.href||'http://local/') {
  const action=value?.cancel_action,url=localURL(action?.http,'POST',base);
  if(!validBuildJob(value?.build_job,project)||value.cancellation?.available!==true||action.operation!=='build'||action.project!==project||
    url.pathname!=='/authoring/build'||url.search||Object.keys(action.payload||{}).length!==2||
    action.payload.action!=='cancel'||!sameBuildJob(action.payload.build_job,value.build_job)) {
    throw Error('Stop does not match the inspected build job. Inspect the current output.');
  }
  return {url:url.pathname,payload:{project,action:'cancel',build_job:structuredClone(value.build_job)}};
}

export function buildJobActive(value) {
  return value?.running===true || value?.owned_processes_active===true || value?.replacement_blocked===true || value?.cleanup_unproved===true || value?.state==='cancelling';
}

export function buildCancelAcknowledged(payload,value) {
  return payload?.action==='cancel' && Object.keys(payload).length===3 &&
    validBuildJob(payload.build_job,payload.project) && sameBuildJob(payload.build_job,value?.build_job) &&
    (value.project||value.corpus)===payload.project &&
    ['requested','recovered','already_terminal'].includes(value.cancel_outcome);
}

// One transient control over the compiler owner's receipt. It neither records a
// second job nor substitutes the newly displayed document for an admitted job.
export function mountBuildCancellation(host,{project,request,onStatus=()=>{},onTerminal=()=>{},onInspect=()=>{},onError=()=>{}}) {
  const make=(tag,text='')=>{const node=document.createElement(tag);node.textContent=text;return node;};
  const panel=make('span');panel.className='build-cancellation';panel.hidden=true;
  const stop=make('button','Stop build'),note=make('span'),readStatus=make('button','Refresh build status'),inspect=make('button','Inspect current output');
  stop.type=readStatus.type=inspect.type='button';note.setAttribute('role','status');readStatus.hidden=inspect.hidden=true;panel.append(stop,note,readStatus,inspect);host.append(panel);
  let value=null,pending=false,failure='',timer=null,alive=true,generation=0;
  const current=()=>alive&&panel.isConnected;
  function paint(){
    if(!current())return;
    const active=buildJobActive(value),stopping=value?.state==='cancelling';
    const unavailable=value?.cancellation?.available===false;
    panel.hidden=!failure&&!active&&value?.state!=='cancelled';stop.hidden=!active||unavailable;stop.disabled=pending||stopping||!!failure;
    // The human subject leads (template preview, derived output, manuscript PDF); the
    // private stage root stays exact in the title, not as the primary display.
    const subject=({candidate:'Template preview',derived:'Derived output','publication-edition':'Publication edition',manuscript:'Manuscript PDF'})[value?.build_job?.build_target?.kind]||'Build';
    stop.textContent=stopping?'Stopping…':'Stop build';stop.title=value?.build_job?'Stop this build · '+value.build_job.root:'';
    note.textContent=failure||(unavailable&&active?value.cancellation.reason:stopping?'Stopping build; waiting for its processes to end.':value?.state==='cancelled'?'Build stopped · '+subject.toLowerCase():active?subject+' building…':'');
    note.title=value?.build_job?'Build job '+value.build_job.id+' · '+value.build_job.root:'';
    if(!failure&&active&&value.job_basis_current===false)note.textContent+=' · Inputs differ from this recorded job.';
    readStatus.hidden=inspect.hidden=!(failure||unavailable&&active);readStatus.disabled=inspect.disabled=pending;
  }
  function failed(error){failure=error.message;clearTimeout(timer);paint();onError(error);}
  function validate(next,expected=null,{status=true}={}){
    if((next?.project||next?.corpus)!==project||!validBuildJob(next?.build_job,project)||expected&&!sameBuildJob(next.build_job,expected))throw Error('Build status returned another job. Inspect the current output.');
    if(status&&(!['running','cancelling','cancelled','done','error','idle'].includes(next.state)||typeof next.running!=='boolean'))throw Error('The build owner did not report this job state. Inspect the current output.');
    buildJobStatusURL(next,project);
    if(typeof next.cleanup_unproved!=='boolean'||typeof next.cancellation?.available!=='boolean'||next.cancellation.available===false&&(typeof next.cancellation.reason!=='string'||!next.cancellation.reason||next.cancel_action!==undefined))throw Error('The build owner did not report its cancellation capability. Inspect the current output.');
    if(next.cancellation.available)buildCancelSubmission(next,project);return next;
  }
  function schedule(){clearTimeout(timer);if(current()&&value?.cleanup_unproved!==true&&
    (value?.running===true||value?.owned_processes_active===true))timer=setTimeout(()=>refresh().catch(failed),900);}
  function regresses(next){return value&&sameBuildJob(value.build_job,next.build_job)&&
    (value.state==='cancelling'&&next.state==='running'||
      ['done','error','cancelled'].includes(value.state)&&!buildJobActive(value)&&buildJobActive(next));}
  async function accept(next,{terminal=true}={}){
    if(regresses(next))return;
    const settled=value&&sameBuildJob(value.build_job,next.build_job)&&!buildJobActive(value)&&['done','error','cancelled'].includes(value.state);
    value=next;failure='';paint();onStatus(value);schedule();
    if(terminal&&!settled&&!buildJobActive(value))await onTerminal(value);
  }
  async function refresh(){
    if(!current()||!value)return;
    const ticket=generation,expected=value.build_job,url=buildJobStatusURL(value,project);
    const next=await request(url,undefined,{allowStateError:true});
    if(!current()||ticket!==generation)return;
    await accept(validate(next,expected));
  }
  stop.onclick=async()=>{
    if(pending||!value||!buildJobActive(value)||value.state==='cancelling'||value.cancellation?.available!==true||failure)return;
    const ticket=++generation,expected=value.build_job,action=buildCancelSubmission(value,project);clearTimeout(timer);pending=true;paint();
    try{const next=await request(action.url,action.payload,{allowStateError:true});if(current()&&ticket===generation)await accept(validate(next,expected));}
    catch(error){if(current()&&ticket===generation)failed(error);}
    finally{pending=false;paint();}
  };
  inspect.onclick=async()=>{if(pending)return;pending=true;paint();try{await onInspect();}catch(error){failed(error);}finally{pending=false;paint();}};
  readStatus.onclick=async()=>{if(pending)return;pending=true;paint();try{await refresh();}catch(error){failed(error);}finally{pending=false;paint();}};
  return {
    observe(next,{replace=false}={}){
      if(pending&&!replace)return;
      if(failure&&!replace)return;
      if(!next?.build_job){if(replace){++generation;clearTimeout(timer);value=null;failure='';paint();}return;}
      validate(next);
      if(regresses(next))return;
      if(value&&buildJobActive(value)&&!sameBuildJob(value.build_job,next.build_job)&&!replace)return;
      ++generation;clearTimeout(timer);value=next;failure='';paint();schedule();
    },
    async follow(receipt){validate(receipt,null,{status:false});++generation;clearTimeout(timer);value=receipt;failure='';paint();await refresh();},
    refresh,
    get data(){return value;},
    get active(){return buildJobActive(value);},
    destroy(){alive=false;++generation;clearTimeout(timer);panel.remove();}
  };
}

function localURL(http, method, base) {
  if (http?.method !== method || typeof (http.url || http.route) !== 'string') {
    throw Error('The derived-output owner supplied no matching ' + method + ' action.');
  }
  const url = new URL(http.url || http.route, base);
  if (url.origin !== new URL(base).origin || url.hash || url.username || url.password) {
    throw Error('The derived-output action leaves its local owner.');
  }
  return url;
}

export function derivedBuildSubmission(value, project, base = globalThis.location?.href || 'http://local/') {
  const action = value?.build_action;
  const url = localURL(action?.http, 'POST', base);
  if (value.schema_version !== 'laplace.derived-output/1' || value.project !== project ||
      !validDerivedTarget(value.build_target, project) || action.operation !== 'build' ||
      action.project !== project || url.pathname !== '/authoring/build' || url.search ||
      Object.keys(action.payload || {}).length !== 1 ||
      !sameDerivedTarget(action.payload.build_target, value.build_target)) {
    throw Error('The build action does not match the inspected derived target. Refresh this output before building.');
  }
  return {url: url.pathname, payload: {project, build_target: structuredClone(value.build_target)}};
}

export function derivedStatusURL(value, project, base = globalThis.location?.href || 'http://local/') {
  const read = value?.status_read;
  const url = localURL(read?.http, 'GET', base);
  let target;
  try { target = JSON.parse(url.searchParams.get('build_target')); } catch { target = null; }
  if (value.schema_version !== 'laplace.derived-output/1' || value.project !== project || value.target_kind !== 'derived' ||
      read.operation !== 'build_status' || Object.keys(read.payload || {}).length !== 1 || url.pathname !== '/authoring/build' ||
      [...url.searchParams.keys()].some(key => !['project', 'build_target'].includes(key) || url.searchParams.getAll(key).length !== 1) ||
      url.searchParams.get('project') !== project ||
      !sameDerivedTarget(target, value.build_target) ||
      !sameDerivedTarget(read.payload?.build_target, value.build_target)) {
    throw Error('The status read does not belong to this inspected derived build.');
  }
  return url.pathname + url.search;
}

export function derivedPdfURL(value, project, base = globalThis.location?.href || 'http://local/') {
  const read = value?.pdf_read;
  if (!read) return null;
  const url = localURL(read.http, 'GET', base);
  let target;
  try { target = JSON.parse(url.searchParams.get('build_target')); } catch { target = null; }
  const output = value.recorded_output;
  if (value.schema_version !== 'laplace.derived-output/1' || value.project !== project || value.target_kind !== 'derived' ||
      !validDerivedTarget(value.build_target, project) || url.pathname !== '/projection/pdf' ||
      [...url.searchParams.keys()].some(key => !['file', 'corpus', 'build_target', 'expected_content_revision'].includes(key) || url.searchParams.getAll(key).length !== 1) ||
      url.searchParams.get('corpus') !== project ||
      !relative(url.searchParams.get('file')) || !/\.pdf$/i.test(url.searchParams.get('file')) ||
      url.searchParams.get('file') !== read.build_target?.root?.replace(/\.tex$/i, '.pdf') ||
      !validDerivedTarget(read.build_target, project) ||
      !sameDerivedTarget(target, read.build_target) ||
      !sameDerivedTarget(output?.build_target, read.build_target) ||
      !pin(read.content_revision) || read.content_revision !== output.content_revision ||
      read.content_revision !== url.searchParams.get('expected_content_revision') ||
      output.output_current !== true || typeof read.current !== 'boolean' ||
      read.current && (value.status !== 'READY' || value.current_build?.fresh !== true ||
        value.current_build?.running === true || output.inputs_current !== true ||
        output.target_basis_current !== true || output.output_bundle_current !== true ||
        !sameDerivedTarget(value.build_target, read.build_target))) {
    throw Error('The saved derived PDF has no matching target and output receipt. No other PDF was substituted.');
  }
  return url.pathname + url.search;
}

export async function mountDerivedOutput(host, {project, request, initial = null,
  readOnly = false, onReadPdf, status = () => {}}) {
  const element = (tag, text = '') => {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  };
  const panel = element('section');
  panel.className = 'output-document derived-output';
  panel.setAttribute('data-control','output:derived');
  // THE DERIVED OUTPUT CARD (M5 C7): an object header whose chip is the owner's status word;
  // the note below is the owner's one sentence; actions carry Build (primary), Read, Refresh.
  const heading = element('div');
  const paintHeading=(status,title)=>{heading.replaceChildren();const head=element('header');head.className='object-header';const eyebrow=element('span','Derived output');eyebrow.className='object-eyebrow';const h=element('h3',title||'Reader-plan output');h.className='object-title';head.append(eyebrow,h);
    if(status){const chip=element('span',String(status).toLowerCase().replaceAll('_',' '));chip.className='state-chip';chip.setAttribute('data-tone',({READY:'ok',BUILDING:'running',FAILED:'blocked',STALE:'attention',UNBUILT:'neutral',UNAVAILABLE:'attention'})[status]||'neutral');const row=element('div');row.className='chip-row';row.append(chip);head.append(row);}
    heading.append(head);};
  paintHeading(null);
  const note = element('p');
  note.setAttribute('role', 'status');
  const actions = element('div');
  actions.className = 'workflow-actions';
  const details = element('details');
  details.append(element('summary', 'Target and build details'));
  const detailBody = element('div');
  details.append(detailBody);
  const absence=element('details'),absenceSummary=declareControl(element('summary'),'output:reader-plan-absence'),absenceNote=element('p');absence.hidden=true;absence.append(absenceSummary,absenceNote);
  panel.append(heading, note, actions, details,absence);
  host.append(panel);
  let alive = true, generation = 0, value = null, pending = false, timer = null, failureMessage = '';
  const current = () => alive && panel.isConnected;
  const fail = error => {
    if (!current()) return;
    failureMessage = error.message;
    note.textContent = failureMessage;
    note.classList.add('error');
    status(error.message, true);
  };
  const button = (label, run) => {
    const control = element('button', label);
    control.type = 'button';
    control.onclick = async () => {
      if (pending) return;
      pending = true;
      control.disabled = true;
      try { await run(); } catch (error) { fail(error); }
      finally { pending = false; if (current()) paint(); }
    };
    return control;
  };
  const refresh = declareControl(button('Refresh derived output', () => load(null,true)),'output:refresh-derived');
  const build = button('Build derived PDF', async () => {
    const inspected = value;
    const action = derivedBuildSubmission(inspected, project);
    // Do not replace the displayed basis with a fresh, unseen target on click.
    const receipt=await request(action.url, action.payload);
    if(receipt?.build_job)await cancellation.follow(receipt);
    await load();
  });
  const pdf = button('Read derived PDF', () => {
    const url = derivedPdfURL(value, project);
    if (!url) throw Error('No verified derived PDF is retained.');
    if (!onReadPdf) throw Error('The PDF reader is unavailable in this view.');
    return onReadPdf(url, 'Reader-plan output', {
      notice: value.pdf_read.current ? 'Recorded derived output matches current inputs.' :
        'Saved derived output; current inputs or the latest build differ.'
    });
  });
  build.disabled = true;
  pdf.hidden = true;
  actions.append(...(readOnly ? [] : [build]), pdf, refresh);
  const cancellation=readOnly?null:mountBuildCancellation(actions,{project,request,
    onStatus:observed=>{if(value&&sameBuildJob(value.current_build?.build_job,observed.build_job))value={...value,current_build:observed};paint();},
    onTerminal:()=>load(),onInspect:()=>load(null,true),onError:fail});
  function paint() {
    if (!current() || !value) return;
    const unavailable = value.status === 'UNAVAILABLE';
    const neutral=unavailable&&['NOT_CONFIGURED','NOT_PREPARED'].includes(value.reason_code);
    panel.className=neutral?'derived-output-absence':'output-document derived-output';
    heading.hidden=note.hidden=actions.hidden=details.hidden=neutral;
    absence.hidden=!neutral;
    if(neutral){absenceSummary.textContent=value.reason_code==='NOT_CONFIGURED'?'Reader-plan output is not configured':'Reader-plan output is not prepared yet';absenceNote.textContent=value.reason_code==='NOT_CONFIGURED'?'This project has no separate reader-plan output.':'The declared reader-plan output has no generated source yet.';absence.append(refresh);}else actions.append(refresh);
    note.classList.toggle('error', !!failureMessage||unavailable&&!neutral);
    const running = value.current_build?.running === true;
    paintHeading(running?'BUILDING':value.status,value.build_target?.title);
    const labels = {BUILDING: 'Building the declared derived output…',
      READY: 'Derived output matches current inputs.',
      FAILED: 'The latest derived build failed.', STALE: 'Derived inputs changed.',
      UNBUILT: 'No verified derived PDF build.'};
    note.textContent = unavailable ? value.reason || 'Derived output is unavailable.' :
      labels[value.status] || 'Derived output needs inspection.';
    if(value.current_build?.state==='cancelling')note.textContent='Stopping the derived build…';
    else if(value.current_build?.state==='cancelled')note.textContent='The derived build was stopped.';
    if (value.pdf_read && !value.pdf_read.current) note.textContent += ' A saved derived PDF remains inspectable.';
    if (failureMessage) note.textContent = failureMessage;
    build.disabled = pending || unavailable || running || !!cancellation?.active;
    build.textContent = running ? 'Building derived PDF…' : 'Build derived PDF';
    pdf.hidden = !value.pdf_read;
    pdf.disabled = pending;
    pdf.textContent = value.pdf_read?.current ? 'Read derived PDF' : 'Read saved derived PDF';
    refresh.disabled = pending;
    detailBody.replaceChildren();
    if (value.build_target) detailBody.append(element('p', 'Derived root: ' + value.build_target.root),
      element('p', 'Plan: ' + value.build_target.plan_path));
    if (value.recorded_output) detailBody.append(element('p', 'Saved output revision: ' + value.recorded_output.content_revision),
      element('p', 'Saved inputs current: ' + value.recorded_output.inputs_current));
    const buildState = value.current_build || {};
    if (buildState.reason || buildState.error) detailBody.append(element('p', buildState.reason || buildState.error));
    if (buildState.log_tail) detailBody.append(element('pre', buildState.log_tail));
    if (value.status === 'FAILED') details.open = true;
  }
  async function load(observation = null,replaceJob=false) {
    const ticket = ++generation;
    clearTimeout(timer);
    const next = observation || await request('/authoring/document?' + new URLSearchParams({project, target_kind: 'derived'}));
    if (!current() || ticket !== generation) return;
    if (next.schema_version !== 'laplace.derived-output/1' || next.project !== project ||
        next.target_kind !== 'derived' || !['BUILDING', 'READY', 'FAILED', 'STALE', 'UNBUILT', 'UNAVAILABLE'].includes(next.status)) {
      throw Error('The derived-output owner returned a different target or incomplete observation.');
    }
    if (next.status !== 'UNAVAILABLE') {
      derivedBuildSubmission(next, project);
      derivedStatusURL(next, project);
      derivedPdfURL(next, project);
    }
    value = next;
    failureMessage = '';
    cancellation?.observe(next.current_build,{replace:replaceJob});
    paint();
    if (next.current_build?.running&&!next.current_build?.build_job) timer = setTimeout(() => poll(ticket).catch(fail), 1000);
  }
  async function poll(ticket) {
    if (!current() || ticket !== generation) return;
    const observed = value;
    const progress = await request(derivedStatusURL(observed, project), undefined, {allowStateError: true});
    if (!current() || ticket !== generation) return;
    if (!sameDerivedTarget(progress.build_target, observed.build_target)) throw Error('Build status changed target. Refresh derived output to inspect its owner.');
    if (progress.running) {
      note.textContent = 'Building the declared derived output…';
      timer = setTimeout(() => poll(ticket).catch(fail), 1000);
    } else await load();
  }
  try { await load(initial); } catch (error) { fail(error); }
  return {refresh: () => load(), get data() { return value; },
    destroy() { alive = false; ++generation; clearTimeout(timer); cancellation?.destroy(); }};
}
