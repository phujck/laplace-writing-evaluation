// ACTIVITY (plan §5). Purpose: every recorded change of the project, by day, with one opened
// record at a time: lead (actor, time, targets, status chip, file identity chip), hunk cards paged
// six at a time or the saved text lazily, exact byte identities, coverage and limitations from
// the owner. Ownership: /authoring/history (author_history) owns the fold, the pages
// (offset/limit/total/next_offset, D7), the category filter and the record detail; this module
// paints and pages. Public contract: the default mount, historyScope/historyQuery (the one
// admitted query shape), historyActor/Time/Attention, historyEvidenceStatus,
// historyComparisonTitle/Kind. Inputs: a scope and the owner pages; outputs: DOM.
// Currentness: the owner's as_of cut on continuation; a changed cut refuses. Errors: unavailable
// with Retry; a detached host cannot paint. Open target rule: match repo_file against the walk's
// identities, else the saved text in the inspector with Back to Activity. Telemetry: Graphs tab
// only (history-telemetry.mjs). Storage: laplace:history:<project> keeps the last scope and
// expansion for the session. Controls: history:entry, history:category, history:tab,
// history:open-target.
import {readAnalyticsRecord,renderRecordedMeasurements,renderRecordedSourceComparison} from './workspace-analytics.mjs';
import {renderHistoryTelemetry,telemetryFilter} from './history-telemetry.mjs';
import {presentationStyles,evidenceChip,stateChip,lazySection,clippedText,declareControl} from './workspace-presentation.mjs';
import {pendingRead} from './pending-read.mjs';
const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
const categories=[['','All activity'],['manuscript','Manuscript'],['structure','Logical structure'],['notes','Notes and review'],['research','Results'],['formal','Formal checks'],['literature','Literature'],['session','Session activity']];
const actors=[['','Everyone'],['human','Author'],['agent','Agents'],['unknown','Unattributed']];
const labels={MATCH:'Matches recorded bytes',CURRENT:'Matches recorded bytes',CHANGED:'Changed since this record',MISSING:'File is missing',UNAVAILABLE:'Identity unavailable',UNRECORDED:'No recorded hash',SNAPSHOT_MATCH:'Saved snapshot verified',SNAPSHOT_MISMATCH:'Saved snapshot differs'};
// `row` is a fourth scope dimension beside file/node/result_id: it names a banked row
// (today, a dispatch's own task id) rather than a manuscript or concept target, so the
// SAME scope chip, SAME "All project history" clear button and SAME query-string
// mechanism every other scope already uses now also finds a child turn WITH its parent
// (author_history.py `_filter`'s `row` key, matched against each item's derived
// `dispatch_ids`) -- one filter over rows the fold already walks, never a second query.
export function historyScope(value={}){
  // `file_scope` is the owner's own continuation handle for a file walk (author_history scope.continuation): it
  // travels with the scope so later pages, the remembered scope and the Graphs tab keep the first page's basis
  const scope={};for(const key of ['file','file_scope','node','result_id','row'])if(typeof value?.[key]==='string'&&value[key].trim())scope[key]=value[key].trim();
  if(scope.file_scope&&!scope.file)delete scope.file_scope;
  if(Object.keys(scope).length&&typeof value.label==='string')scope.label=value.label;
  return scope;
}
export function historyQuery(project,state={},id,view='activity'){
  const query=new URLSearchParams({project,view});
  if(id)query.set('id',id);
  else{if(view==='activity'){query.set('offset',String(Math.max(0,Number(state.offset)||0)));query.set('limit',String(Number.isSafeInteger(state.limit)&&state.limit>=1&&state.limit<=20?state.limit:20));}for(const key of ['file','file_scope','node','result_id','row'])if(state.scope?.[key])query.set(key,state.scope[key]);for(const key of ['category','actor','provider','model','day','from','to','outcome','operation','session_id','event_kind','as_of'])if(state[key])query.set(key,state[key]);}
  return '/authoring/history?'+query;
}
export function historyActor(actor){
  if(typeof actor==='string')return actor||'Actor not recorded';
  if(!actor)return 'Actor not recorded';
  const name=actor.label||({human:'Author',agent:'Agent',unknown:'Actor not recorded'}[actor.kind])||'Actor not recorded';
  return [name,actor.provider,actor.model].filter((value,index,values)=>value&&!values.slice(0,index).some(prior=>String(prior).includes(value))).join(' · ');
}
export function historyTime(value,{date=false}={}){
  if(!value)return date?'Date not recorded':'Time not recorded';const time=new Date(typeof value==='number'&&Math.abs(value)<1e12?value*1000:value);if(!Number.isFinite(time.getTime()))return String(value);
  return new Intl.DateTimeFormat(undefined,date?{year:'numeric',month:'long',day:'numeric'}:{hour:'2-digit',minute:'2-digit'}).format(time);
}
export function historyAttention(item={},scope={}){
  const summary=String(item.summary||'Selected history entry').replace(/\s+/g,' ').trim();
  const target=(item.targets||[]).map(target=>target.label||target.file?.split('/').at(-1)).find(Boolean)||scope.label||'';
  const when=item.at?[historyTime(item.at,{date:true}),historyTime(item.at)].join(' at '):'';
  return {id:item.id||null,label:[summary.length>150?summary.slice(0,147)+'…':summary,target&&!summary.includes(target)?target:'',when].filter(Boolean).join(' · ')};
}
export function historyEvidenceStatus(row={}){
  if(row.kind==='response'&&row.recorded)return 'Recorded response fingerprint';
  if(row.current&&!row.recorded)return row.kind==='file'?'Current file identity only':'Current record identity only';
  return labels[String(row.status||'').toUpperCase()]||String(row.status||'Recorded').replaceAll('_',' ');
}
export function historyComparisonTitle(value={},item={}){
  const title=value.title||'What changed',known=/^recorded proposed or applied edit$/i.test(title);
  if(!known)return title;
  const status=String(item.status||'').toLowerCase();
  if(status==='applied')return 'Applied revision';
  if(status==='partial')return 'Partially applied revision';
  return title;
}
// A whole-file snapshot (no before) is a saved text, not a change: it stays behind a read.
// A recorded hunk whose owner omitted one side for size (`omitted: ['before']`) is still a
// hunk: it keeps its line-range title and its omission notice.
export function historyComparisonKind(value={}){
  if(value?.format!=='tex')return 'fields';
  if(Array.isArray(value.omitted)&&value.omitted.length)return 'hunk';
  if((value.before===null||value.before===undefined)&&typeof value.after==='string'&&/banked|snapshot|saved/i.test(String(value.basis||value.title||'')))return 'snapshot';
  return 'hunk';
}
function timeNode(value){const node=el('time',historyTime(value));if(value){node.dateTime=value;node.title=value;}return node;}
function simpleValue(value){if(value==null)return 'Not recorded';if(typeof value==='boolean')return value?'Yes':'No';if(typeof value!=='object')return String(value);if(Array.isArray(value))return value.map(simpleValue).join('\n');return value.text||value.label||value.title||value.id||'Structured record; inspect its object for complete context.';}
function styles(){presentationStyles();if(document.querySelector('[data-workspace-history]'))return;const css=el('link');css.rel='stylesheet';css.href='/shared/workspace-history.css';css.dataset.workspaceHistory='';document.head.append(css);}
// ACTIVITY · CHANGES (M5 C5). Owner: author_history (activity pages with offset/limit/total/
// next_offset and the category filter; record detail with hunks paged by comparison_offset,
// G4). This view paints one owner page as a timeline by day, opens one record lazily (lead,
// Open target, summary, paged hunk cards, Exact byte identities behind one disclosure, Read
// complete record), and keeps its place in sessionStorage laplace:history:<project>. Defaults:
// the category selector is bound to the owner filter and starts at manuscript for an
// unscoped mount (a file/node/result/row scope keeps the owner's whole-scope page); the
// telemetry overview is read only on request. Graphs (session analytics) is the other tab,
// opened through onGraphs. No consumer-side grouping of rows: the page is the owner's.
// Controls: history:tab, history:category, history:entry, history:open-target.
export async function mountHistory(host,{project,request,status=()=>{},scope={},initialState={},onState=()=>{},onOpenTarget,onOpenConversation,onDiscuss,onGraphs=null,canOpenTarget=()=>null,renderText}={}){
  styles();host.classList.add('workspace-history');let alive=true,epoch=0,data=null,detail=null,opening=null,telemetry=null,telemetryKey='',telemetryError='';
  let inspection=null;
  const initialScope=historyScope(initialState.scope||scope);
  const state={scope:initialScope,overview_expanded:initialState.overview_expanded??false,category:initialState.category??(Object.keys(initialScope).some(key=>key!=='label')?'':'manuscript'),actor:initialState.actor||'',provider:initialState.provider||'',model:initialState.model||'',day:initialState.day||'',from:initialState.from||'',to:initialState.to||'',outcome:initialState.outcome||'',operation:initialState.operation||'',session_id:initialState.session_id||'',event_kind:initialState.event_kind||'',toolScope:telemetryFilter(initialState.toolScope||{}),toolFrequencyView:['linear','log'].includes(initialState.toolFrequencyView)?initialState.toolFrequencyView:'histogram',offset:Math.max(0,Number(initialState.offset)||0),as_of:initialState.as_of||'',expanded:initialState.expanded||null,attention:initialState.attention?.id===initialState.expanded?initialState.attention:null,scrollTop:initialState.scrollTop||0};
  const current=()=>alive&&host.isConnected!==false;
  const main=()=>host.closest('.workspace-main')||host;
  const capture=()=>({...state,scope:{...state.scope},scrollTop:main().scrollTop||0});
  const remember=()=>{if(current())onState(capture());};
  const run=fn=>async()=>{try{await fn();}catch(error){if(current())status(error.message,true);}};
  // the explicit action's intent is read before the control is disabled (M5-R2): a real browser drops focus from a disabled control
  const button=(label,fn,cls='')=>{const node=el('button',label,cls);node.type='button';node.onclick=run(async()=>{const intent={active:node};node.disabled=true;try{await fn(node,intent);}finally{node.disabled=false;}});return node;};
  const text=async(node,value)=>{if(renderText)await renderText(node,String(value||''));else node.textContent=String(value||'');};
  const openTarget=async(target,intent)=>{remember();await onOpenTarget?.(target,intent);};
  function controls() {
    const contextual = !!state.scope.file;
    const header = el('div', '', 'history-heading');
    const heading = el('div');
    heading.append(el('span', contextual ? 'File history' : 'Work, evidence and decisions', 'history-eyebrow'),
      el('h2', contextual ? state.scope.file.split('/').pop() : 'Activity'));
    if (!contextual) {
      // the two tabs: Changes (this owner page) and Graphs (session analytics, on request)
      const tabs = el('nav', '', 'history-tabs'); tabs.setAttribute('aria-label', 'Activity views'); tabs.setAttribute('data-control','history:tab');
      const changes = declareControl(el('button', 'Changes', 'history-tab'),'history:tab-changes'); changes.type = 'button'; changes.setAttribute('aria-current', 'page'); changes.disabled = true; tabs.append(changes);
      if (onGraphs) tabs.append(declareControl(button('Graphs', () => onGraphs(), 'history-tab'),'history:tab-graphs'));
      heading.append(tabs);
    }
    const actions = el('div', '', 'history-actions');
    actions.append(declareControl(button('Refresh history', () => load({offset:0, as_of:'', expanded:null})),'history:refresh'));
    const saved = declareControl(el('a', 'Download full saved state', 'history-state-download'), 'history:download-state');
    saved.href = '/authoring/state?' + new URLSearchParams({project, view:'full'});
    saved.download = project + '-authoring-state.json';
    if (!contextual) actions.append(saved);
    header.append(heading, actions);
    host.append(header);
    const bar = el('div', '', 'history-controls');
    const filters = contextual ? el('details', '', 'history-filter-details') : bar;
    if (contextual) filters.append(el('summary', 'Filter changes and export'));
    for (const [key, label, choices] of [['category','Activity',categories], ['actor','By',actors]]) {
      const wrap = el('label', label), select = el('select');
      select.setAttribute('aria-label', label);
      if (key === 'category') select.setAttribute('data-control','history:category'); else select.dataset.control = 'history:actor';
      for (const [value, name] of choices) {
        const option = el('option', name); option.value = value; select.append(option);
      }
      select.value = state[key];
      select.onchange = run(() => load({[key]:select.value, offset:0, as_of:'', expanded:null}));
      wrap.append(select); filters.append(wrap);
      if (contextual && state[key]) bar.append(button(label + ': ' + (choices.find(row=>row[0]===state[key])?.[1]||state[key]) + ' · clear',
        () => load({[key]:'', offset:0, as_of:'', expanded:null})));
    }
    const chosen = state.scope;
    if (Object.keys(chosen).some(key=>key!=='label')) {
      const chip = el('div', '', 'history-scope');
      chip.append(el(contextual?'code':'span', contextual ? chosen.file : 'For ' + (chosen.label||chosen.file||chosen.node||chosen.result_id)),
        button('All project history', () => load({scope:{}, offset:0, as_of:'', expanded:null})));
      bar.append(chip);
    } else bar.append(el('span','All project','history-scope-label'));
    if (state.day||state.from||state.to) {
      const chip=el('div','','history-filter-chip');
      chip.append(el('span',state.day||[state.from,state.to].filter(Boolean).map(value=>value.replace('T',' ').replace(':00Z',' UTC')).join(' → ')),
        button('Clear time filter',()=>load({day:'',from:'',to:'',toolScope:{...state.toolScope,day:'',from:'',to:''},offset:0,expanded:null})));
      bar.append(chip);
    }
    if (state.provider||state.model) bar.append(button('Clear provider: '+[state.provider,state.model].filter(Boolean).join(' · '),()=>load({provider:'',model:'',toolScope:{...state.toolScope,provider:'',model:''},offset:0,expanded:null})));
    if (state.outcome) bar.append(button('Clear outcome: '+state.outcome,()=>load({outcome:'',toolScope:{...state.toolScope,outcome:''},offset:0,expanded:null})));
    if (state.event_kind==='tool-attempt') bar.append(button('Tool calls only · clear',()=>load({event_kind:'',operation:'',offset:0,expanded:null})));
    if (state.operation) bar.append(button('Clear tool: '+state.operation.replaceAll('_',' '),()=>load({operation:'',offset:0,expanded:null})));
    if (state.session_id) bar.append(button('Clear conversation filter',()=>load({session_id:'',toolScope:{...state.toolScope,session_id:''},offset:0,expanded:null})));
    host.append(bar);
    if (contextual) {filters.append(saved);host.append(filters);}
    host.append(declareControl(button(state.overview_expanded?'Hide activity overview':'Show activity overview',()=>load({overview_expanded:!state.overview_expanded})),'history:overview'));
  }
  function links(host,targets=[],conversation){
    const actions=el('div','','history-actions');
    // The target travels with its record id, so a consumer that cannot place an UNPROVED
    // historical file in the manuscript can still open the record's saved text.
    for(const target of targets){if(!onOpenTarget)continue;const name=target.label||target.file||target.id||'Affected object';const link=button(target.action_label||'Open '+name,(_node,intent)=>openTarget({...target,history_id:target.history_id||state.expanded||null},intent),actions.children.length?'':'primary'),reason=canOpenTarget(target);link.setAttribute('data-control','history:open-target');link.setAttribute('data-control-owner',(target.history_id||state.expanded||'')+'::'+actions.children.length);if(reason){link.disabled=true;link.title=reason;link.setAttribute('aria-label',link.textContent+' — '+reason);}actions.append(link);}
    if(conversation?.session_id&&onOpenConversation)actions.append(button('Open conversation',async()=>{remember();await onOpenConversation(conversation);}));
    if(actions.children.length)host.append(actions);
  }
  // Field comparisons (non-source records) keep their before/after columns.
  async function fieldComparison(parent,value,item){
    const changes=Array.isArray(value.changes)?value.changes.filter(change=>!(!Object.hasOwn(change,'before')&&['record','operation','status'].includes(change.field))):null;
    if(changes&&!changes.length)return;
    const section=el('section','','history-comparison');section.append(el('h4',historyComparisonTitle(value,item)));
    if(changes){
      const facts=el('dl','','history-record-facts');
      for(const change of changes){const label=change.label||String(change.field||'Value').replaceAll('_',' ');if(Object.hasOwn(change,'before')){const field=el('section','','history-field-change');field.append(el('h5',label));const columns=el('div','','history-comparison-columns');for(const [key,title]of [['before','Before'],['after','After']]){const side=el('div');side.append(el('strong',title));const body=el('div');await text(body,simpleValue(change[key]));side.append(body);columns.append(side);}field.append(columns);section.append(field);}else{facts.append(el('dt',label));const body=el('dd');await text(body,simpleValue(change.after));facts.append(body);}}
      if(facts.children.length)section.append(facts);
    }else if(value.before!==undefined||value.after!==undefined){const columns=el('div','','history-comparison-columns');for(const [key,label]of [['before','Before'],['after','After']]){const side=el('section');side.append(el('h5',label));const body=el('div');await text(body,value[key]===''?'[Empty passage]':simpleValue(value[key]));side.append(body);columns.append(side);}section.append(columns);}
    if(value.note)section.append(el('p',value.note,'history-note'));
    if(value.basis&&value.basis!=='exact stored journal row')section.append(el('p',typeof value.basis==='string'?value.basis:value.basis.reason||value.basis.status,'history-note'));
    parent.append(section);
  }
  // Source changes: the bounded hunks first, a whole-file snapshot behind a read, and
  // many hunks paged in the DOM. Nothing is diffed here; the owner supplied the hunks.
  // Recorded source comparisons arrive one owner page at a time (comparisons_pagination, G4).
  // Every delivered comparison is painted in owner order by its kind (hunk card, including
  // hunks with an omitted side and their notice; saved-text snapshot behind a read; field
  // comparison), and "Show more" reads the owner's next page and paints it the same way, so
  // no kind and no page is dropped.
  function paintSnapshot(section,value){
    const chars=String(value.after||'').length,heading=value.title||'Saved file text';
    section.append(el('h4',heading));
    section.append(el('p','Whole saved text, not a change: '+chars.toLocaleString()+' characters'+(value.note?' · '+value.note:'.'),'history-note'));
    section.append(lazySection({label:'Show saved text',load:async()=>value.after,render:(body,saved)=>{body.append(clippedText(saved,{lines:40}));}}));
    if(value.basis)section.append(el('p',typeof value.basis==='string'?value.basis:JSON.stringify(value.basis),'history-note'));
  }
  async function comparisons(parent,values,item,pagination=null){
    const rows=values.filter(Boolean);if(!rows.length)return;
    const total=pagination?.total??rows.length;
    const section=el('section','','history-comparison history-source-changes'),list=el('div','','history-hunks');
    const firstHunk=rows.find(value=>historyComparisonKind(value)==='hunk');
    if(firstHunk)section.append(el('h4',total===1?historyComparisonTitle(firstHunk,item):total+' recorded changes · '+historyComparisonTitle(firstHunk,item)));
    section.append(list);let shown=0;
    const paint=async page=>{for(const value of page){shown+=1;const kind=historyComparisonKind(value);
      if(kind==='fields')await fieldComparison(list,value,item);
      else if(kind==='snapshot')paintSnapshot(list,value);
      else renderRecordedSourceComparison(list,value,historyComparisonTitle(value,item),{index:shown,total});}};
    await paint(rows);
    let next=pagination?.next_read||null;
    if(next){const more=button('Show '+(total-shown)+' more changes',async()=>{const token=epoch,page=await request(next.http.url);if(!current()||token!==epoch)return;await paint((page.comparisons||[]).filter(Boolean));next=page.comparisons_pagination?.next_read||null;if(next)more.textContent='Show '+(total-shown)+' more changes';else more.remove();});section.append(more);}
    parent.append(section);
  }
  // Exact byte identities stay behind one quiet disclosure; the lead line carries their
  // state as a chip (HISTORY_BASIS_DOMINATES_DETAIL).
  function hashes(parent,rows=[]){
    if(!rows.length)return;
    const actual=rows.filter(row=>row.recorded||row.current),section=el('details','','history-identities operator-exact');section.append(el('summary','Exact byte identities'));
    if(!actual.length){section.append(el('p',rows.find(row=>row.note)?.note||'This event did not retain a content identity.','history-note'));parent.append(section);return;}
    const kinds={file:'File contents',snapshot:'Saved snapshot','record-revision':'Record revision',response:'Tool response fingerprint'};
    for(const row of actual){const kind=row.kind||'identity',card=el('article','','history-identity'),heading=el('div','','history-evidence-heading');card.dataset.evidenceState=String(row.status||'').toLowerCase();
      const state=row.kind==='response'&&row.recorded?{label:historyEvidenceStatus(row),tone:'neutral'}:row.current&&!row.recorded?{label:historyEvidenceStatus(row),tone:'neutral'}:evidenceChip(row.status);
      const chip=stateChip(state);chip.classList.add('history-identity-state');
      // copy (plan §10): the chip carries the content-identity caveat as its title, not a sentence below
      chip.title='Content identity does not establish scientific validity.';heading.append(el('strong',kinds[kind]||'Recorded identity'),chip);card.append(heading);
      if(row.label&&row.label!==kinds[kind])card.append(el('p',row.label,'history-evidence-label'));if(row.path)card.append(el('small',row.path,'history-evidence-path'));
      const values=el('dl','','history-hash-values');for(const [key,label]of [['recorded','Recorded'],['current','Current']])if(row[key]){values.append(el('dt',label));const value=el('dd');value.append(el('code',row[key]));values.append(value);}card.append(values);if(row.note)card.append(el('p',row.note,'history-note'));section.append(card);
    }
    // copy (plan §10): the content-identity disclaimer is the chip's title and Help → States, not a sentence here
    parent.append(section);
  }
  function fullRecord(parent,item,detail={}){
    const panel=el('section','','history-complete-record'),actions=el('div','','history-actions'),openLabel=detail.record_kind==='writing-reply'&&detail.saved_text_available?'Read complete saved response':'Read complete saved record';
    // Disable only until dialog creation; pending reads never hold return focus hostage.
    const open=button(openLabel,async(opener)=>readAnalyticsRecord({operation:'author_history',payload:{view:'record',id:item.id},http:{method:'GET',url:historyQuery(project,state,item.id,'record')}},{project,request,opener,
      isCurrent:()=>current()&&state.expanded===item.id,
      onOpen:dialog=>{opener.disabled=false;inspection?.close();inspection=dialog;}}));
    if(detail.response_body_status==='summary-only')panel.append(el('p','This event retains a structured summary and its recorded evidence; an original response body is not stored.','history-note'));
    const download=el('a','Download complete record','history-state-download');download.href=historyQuery(project,state,item.id,'record');download.download='history-record.json';actions.append(open,download);panel.append(actions);parent.append(panel);
  }
  // The event itself in one line: who, when, what it touched, how it stands.
  function lead(container,item,row,hashRows=[]){
    const line=el('p','','history-lead');
    const names=[...new Set((item.targets||row.targets||[]).map(target=>target.label||target.file?.split('/').at(-1)||target.id).filter(Boolean))];
    line.append(el('span',historyActor(item.actor||row.actor),'history-lead-actor'));
    if(item.at||row.at)line.append(el('span',' · '+[historyTime(item.at||row.at,{date:true}),historyTime(item.at||row.at)].join(' at ')));
    if(names.length)line.append(el('span',' · '+names.slice(0,2).join(', ')+(names.length>2?' +'+(names.length-2):'')));
    if(item.status||row.status){const chip=stateChip({label:String(item.status||row.status),tone:/applied|saved|completed|accepted/i.test(item.status||row.status)?'historical':/fail|refus|error|reject/i.test(item.status||row.status)?'blocked':/pending|open|partial/i.test(item.status||row.status)?'attention':'neutral'});line.append(document.createTextNode(' '));line.append(chip);}
    // The file identity state in one chip; the exact hashes stay under Exact byte identities.
    const fileRow=(hashRows||[]).find(entry=>entry.kind==='file'&&entry.recorded&&entry.current&&entry.status);
    if(fileRow){line.append(document.createTextNode(' '));line.append(stateChip({...evidenceChip(fileRow.status),title:fileRow.note||''}));}
    container.append(line);
  }
  async function showDetail(row,container,toggle){
    inspection?.close();inspection=null;const token=++epoch;state.expanded=row.id;state.attention=historyAttention(row,state.scope);detail=null;opening=row.id;remember();toggle.setAttribute('aria-expanded','true');container.hidden=false;container.replaceChildren(pendingRead(el('p','Loading this record…','history-note')));
    try{
      const result=await request(historyQuery(project,state,row.id));if(!current()||token!==epoch||state.expanded!==row.id)return;
      opening=null;detail=result;container.replaceChildren();const item=result.item||row;
      lead(container,item,row,result.hashes||[]);
      links(container,result.links||item.targets||row.targets,result.conversation||item.conversation||row.conversation);
      const description=result.description||item.description;if(description&&String(description).trim()!==String(item.summary||'').trim()){const body=el('div','','history-detail-prose');body.append(el('span','Summary','history-summary-label'));const prose=el('div');await text(prose,description);if(!current()||token!==epoch)return;body.append(prose);container.append(body);}
      renderRecordedMeasurements(container,result.measurements);
      if(onDiscuss)container.append(button('Discuss this change',()=>{remember();return onDiscuss(item);}));
      await comparisons(container,result.comparisons||[result.comparison],item,result.comparisons_pagination||null);if(!current()||token!==epoch)return;
      hashes(container,[...(result.hashes||[]),...(result.record_identities||[]).map(row=>({kind:'record-revision',label:'Research record revision',...row}))]);
      fullRecord(container,item,result);
      const warnings=[...(result.limitations||[]),...(result.warnings||[])];if(warnings.length){const notes=el('details','','history-limitations operator-exact');notes.append(el('summary','Record limits'));const list=el('ul');for(const warning of warnings)list.append(el('li',typeof warning==='string'?warning:warning.message||warning.note||warning.status));notes.append(list);container.append(notes);}
      if(!container.children.length)container.append(el('p','This record contains the activity receipt only. Open its affected object for current context.','history-note'));
      const identity=el('details','','history-record-id operator-exact');identity.append(el('summary','Record identifier'),el('code',row.id));container.append(identity);remember();
    }catch(error){if(!current()||token!==epoch)return;opening=null;container.replaceChildren(el('p','This record could not be loaded: '+error.message,'error'),button('Retry this record',()=>showDetail(row,container,toggle)));}
  }
  async function paint(){
    host.replaceChildren();controls();if(state.overview_expanded&&telemetry){const overview=el('section');host.append(overview);renderHistoryTelemetry(overview,telemetry,{state,onScope:filter=>{const selected=telemetryFilter(filter);return load({category:'',actor:'',operation:'',provider:'',model:'',session_id:'',day:'',from:'',to:'',outcome:'',event_kind:'',...selected,toolScope:selected,offset:0,expanded:null,scrollTop:0});},onFilter:filter=>{const selected=telemetryFilter(filter),scope={...state.scope};for(const key of ['file','node','result_id'])if(selected[key])scope[key]=selected[key];return load({category:'',actor:'',provider:'',model:'',day:'',from:'',to:'',outcome:'',operation:'',session_id:'',event_kind:'',...selected,scope,offset:0,expanded:null,scrollTop:0});}});}else if(state.overview_expanded&&telemetryError){const warning=el('p','Activity overview could not load. The event timeline remains available.','history-note');warning.append(button('Retry overview',()=>{telemetryKey='';return load();}));host.append(warning);}const info=el('p','','history-count');info.setAttribute('role','status');const page=data.pagination||{},items=data.items||[];info.textContent=items.length?`${state.offset+1}–${state.offset+items.length} of ${page.total??items.length} activities`:'No recorded activity matches this scope.';host.append(info);
    const timeline=el('div','','history-timeline');host.append(timeline);let day=null,group=null,restore=null;
    for(const row of items){const nextDay=historyTime(row.at,{date:true});if(nextDay!==day){day=nextDay;group=el('section','','history-day');group.append(el('h3',day));timeline.append(group);}
      const article=el('article','','history-entry');article.dataset.historyId=row.id;article.setAttribute('data-control','history:entry');article.setAttribute('aria-label','Activity · '+(row.title||row.summary||row.kind||row.id));const meta=el('div','','history-meta');meta.append(el('span',historyActor(row.actor)),timeNode(row.at));article.append(meta);
      const toggle=button(row.summary||'Recorded activity',async()=>{if(state.expanded===row.id){++epoch;state.expanded=null;state.attention=null;detail=null;opening=null;container.hidden=true;container.replaceChildren();toggle.setAttribute('aria-expanded','false');remember();}else{for(const other of timeline.querySelectorAll('.history-detail')){other.hidden=true;other.replaceChildren();}for(const other of timeline.querySelectorAll('[aria-expanded]'))other.setAttribute('aria-expanded','false');await showDetail(row,container,toggle);}},'history-entry-title');toggle.setAttribute('aria-expanded','false');toggle.title=row.summary||'Recorded activity';article.append(toggle);
      const context=el('p','','history-entry-context');const names=[...new Set((row.targets||[]).map(target=>target.label||target.file||target.id).filter(Boolean))];context.textContent=[row.status,names.slice(0,2).join(' · '),names.length>2?`+${names.length-2} objects`:''].filter(Boolean).join(' · ');if(context.textContent)article.append(context);
      const container=el('div','','history-detail');container.hidden=true;article.append(container);group.append(article);if(state.expanded===row.id)restore=()=>showDetail(row,container,toggle);
    }
    const paging=el('nav','','history-pagination');paging.setAttribute('aria-label','History pages');if(state.offset>0)paging.append(button('Newer activity',()=>load({offset:Math.max(0,state.offset-20),expanded:null})));if(page.next_offset!=null)paging.append(button('Older activity',()=>load({offset:page.next_offset,expanded:null})));host.append(paging);
    if(data.coverage?.length||data.limitations?.length){const coverage=el('details','','history-coverage operator-exact');coverage.append(declareControl(el('summary','What this history contains'),'history:coverage'));const list=el('ul');for(const row of data.coverage||[])list.append(el('li',[row.label||row.owner,row.note||row.status,row.omitted?`${row.omitted} earlier records unavailable`:null].filter(Boolean).join(' · ')));for(const note of data.limitations||[])list.append(el('li',typeof note==='string'?note:note.note||note.message));coverage.append(list);host.append(coverage);}
    if(!restore&&state.expanded){const selected=el('section','','history-selected-record'),toggle=button('Selected recorded event',()=>{}),container=el('div','','history-detail');selected.append(toggle,container);host.append(selected);restore=()=>showDetail({id:state.expanded,summary:'Selected recorded event'},container,toggle);}
    if(restore)await restore();
  }
  async function load(patch={}){
    const token=++epoch;Object.assign(state,patch);state.scope=historyScope(state.scope);if(!state.expanded)state.attention=null;if(['offset','scope','category','actor','day','from','to','outcome','operation','session_id','toolScope'].some(key=>key in patch))state.scrollTop=0;detail=null;opening=null;remember();host.replaceChildren(el('h2','History'),pendingRead(el('p','Loading recorded activity…','history-note')));
    try{const result=await request(historyQuery(project,state));if(!current()||token!==epoch)return;data=result;state.as_of=result.as_of||state.as_of;
      // the owner's continuation handle (M5-R1): the first page's whole basis (stable source and admitted recorded
      // names) travels with every later page, the remembered scope and the Graphs tab, so a changed source selection
      // cannot re-resolve a walk already under way and no offset lands on a changed membership
      const continuation=result.scope?.continuation;if(continuation?.file&&continuation.file_scope&&state.scope.file&&(state.scope.file!==continuation.file||state.scope.file_scope!==continuation.file_scope))state.scope={...state.scope,file:continuation.file,file_scope:continuation.file_scope};const key=historyQuery(project,{...state.toolScope,scope:state.scope,as_of:state.as_of},null,'telemetry');if(state.overview_expanded&&key!==telemetryKey){telemetryKey=key;telemetryError='';try{const summary=await request(key);if(!current()||token!==epoch)return;telemetry=summary?.totals?summary:null;}catch(error){if(!current()||token!==epoch)return;telemetry=null;telemetryError=error.message;}}if(!current()||token!==epoch)return;await paint();if(current()){main().scrollTop=state.scrollTop;remember();}}
    catch(error){if(!current()||token!==epoch)return;host.replaceChildren();controls();host.append(el('p','History could not be loaded: '+error.message,'error'),button('Retry history',()=>load()));status(error.message,true);}
  }
  await load();
  return {capture,refresh:()=>load({offset:0,as_of:'',expanded:null}),setScope:value=>load({scope:historyScope(value),offset:0,as_of:'',expanded:null}),destroy(){inspection?.close();alive=false;++epoch;},get detail(){return detail;},get loadingDetail(){return opening;}};
}
