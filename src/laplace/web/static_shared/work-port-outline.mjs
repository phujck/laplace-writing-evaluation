// WORK PORT OUTLINE (P1). Purpose: a minimal plain-DOM renderer of one selected Work's title and purpose over the
// renderer-neutral Work port (work-port.mjs), independent of the Work card: it paints the port's immutable snapshot
// and issues the port's intents, and owns no draft, guard, attempt, comparison or owner rule. Public contract:
// mountWorkOutline(host,port,{onReturn}) -> {destroy()}. destroy() removes this mount's nodes and its one port
// subscription; the port, its draft and its attempts live on for the next mount. Field identity: the title and
// purpose fields belong to ONE qualified Work; when the selection becomes another Work (select or Return) they are
// replaced by new fields for that Work, even if one was focused, and every edit names the Work it was typed for, so
// words typed for one Work never edit another. Within the same Work a repaint never overwrites a focused field.
// Comparison: the port's comparison is painted; adopting it is a separate explicit action carrying exactly the
// displayed basis. Keyboard: Enter in the title submits; every action is a plain button reachable by Tab, no drag.
// Lifetime (selected-lifetime.mjs): this mount's subscription and nodes are its owned cleanups; an outcome is shown
// while the mount is live, attached or still being prepared, and never after destroy().
import {createLifetime} from './selected-lifetime.mjs';
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
const identity=selection=>selection?selection.project+'::'+selection.id:null;
export function mountWorkOutline(host,port,{onReturn=null}={}){
  const life=createLifetime();
  const root=el('section','','work-outline');root.setAttribute('aria-label','Selected Work title and purpose');
  const heading=el('h3'),facts=el('p','','muted'),io=el('p','','muted'),absent=el('ul','','work-outline-absent'),status=el('p','','work-status');
  status.setAttribute('role','status');io.dataset.readIo='';
  const form=el('form','','work-outline-form'),titleLabel=el('label','Title'),goalLabel=el('label','Purpose (completion condition)');
  let title=null,goal=null,fieldsFor=null,painted=null;
  const save=el('button','Save title and purpose');save.type='submit';
  const act=(label,intent)=>{const b=el('button',label,'act');b.type='button';b.onclick=()=>run(typeof intent==='function'?intent():intent);return b;};   // onclick returns the intent's promise
  const cancel=act('Discard my draft',{type:'cancel-local'}),again=act('Reinspect',{type:'reinspect'}),compare=act('Compare with the current Work',{type:'compare'}),
    adopt=act('Use the displayed current Work as my basis',()=>({type:'adopt-current',basis:painted?.comparison?.current?.basis??null})),back=el('button','Return','act');back.type='button';
  back.onclick=()=>{onReturn?.();return run({type:'return'});};
  const comparison=el('div','','work-outline-compare');
  form.append(titleLabel,goalLabel,save,cancel,again,compare,adopt,back);root.append(heading,facts,io,absent,form,comparison,status);host.append(root);
  async function run(intent){try{await port.dispatch(intent);}catch(error){if(!life.disposed){status.textContent=error.message;status.className='work-status error';}}}
  // the fields of ONE qualified Work: built for it, and replaced when the selection becomes another Work
  function mountFields(snap){
    const target=snap.selection?{...snap.selection}:null;fieldsFor=identity(snap.selection);
    // this field set's own nodes and Work: a late event from a replaced set still names ITS Work and is refused
    const ownTitle=el('input'),ownGoal=el('textarea');ownTitle.name='title';ownGoal.name='goal';ownTitle.dataset.work=ownGoal.dataset.work=fieldsFor||'';
    let base={title:null,goal:null};
    const typed=()=>{const fields={};if(ownTitle.value!==base.title)fields.title=ownTitle.value;if(ownGoal.value!==base.goal)fields.goal=ownGoal.value;return fields;};
    ownTitle.oninput=ownGoal.oninput=()=>{const fields=typed();return Object.keys(fields).length?run({type:'edit',fields,target}):Promise.resolve();};
    ownTitle.rebase=ownGoal.rebase=values=>{base=values;};
    title=ownTitle;goal=ownGoal;
    titleLabel.replaceChildren(document.createTextNode?.('Title')||'Title',title);goalLabel.replaceChildren(document.createTextNode?.('Purpose (completion condition)')||'Purpose (completion condition)',goal);
  }
  form.onsubmit=event=>{event?.preventDefault?.();return run({type:'submit'});};
  function paint(snap){
    painted=snap;const read=snap.read,owner=read?.owner,draft=snap.draft,attempt=snap.attempt,focus=globalThis.document?.activeElement;
    const remounted=identity(snap.selection)!==fieldsFor;if(remounted||!title)mountFields(snap);
    heading.textContent=owner?.title??(snap.selection?snap.selection.id:'No Work selected');
    facts.textContent=owner?[owner.status&&'Standing: '+owner.status,owner.activity?.qualification,read.at&&'Read at '+read.at].filter(Boolean).join(' · '):'';
    io.textContent=read?.io==='reading'?'Reading from the owner…':read?.io==='error'?'Last read failed: '+String(read.error).replace(/\.?$/,'.')+(owner?' The values shown are from the last successful read.':''):'';
    absent.replaceChildren(...(owner?.unavailable||[]).map(item=>el('li',item)));
    const values={title:draft?.fields?.title??owner?.title??'',goal:draft?.fields?.goal??owner?.goal??''};title.rebase(values);
    for(const [node,name]of [[title,'title'],[goal,'goal']])if(remounted||focus!==node)node.value=values[name];
    const editable=!!(draft||owner?.action?.permitted);
    title.disabled=goal.disabled=!editable;save.disabled=!draft||attempt?.status==='pending';cancel.disabled=!draft;
    adopt.hidden=!snap.comparison;back.hidden=!snap.visit?.depth;
    comparison.replaceChildren();
    if(snap.comparison){const c=snap.comparison;comparison.append(el('p',c.same_basis?'Your draft was written against the current Work.':'The Work changed since your draft was written.'),
      el('p','Current title: '+(c.current.fields.title??'not returned')),el('p','Your title: '+(c.draft.fields.title??'(unchanged)')),
      el('p','Current purpose: '+(c.current.fields.goal??'not returned')),el('p','Your purpose: '+(c.draft.fields.goal??'(unchanged)')),
      el('p','Current revision: '+(c.current.work_revision??'not returned'),'muted'));}
    const lines=[];
    if(draft)lines.push(draft.stale?'Your draft keeps its original guard; the current Work has changed.':'Draft kept against the Work as you read it.');
    if(attempt){lines.push('Attempt '+attempt.id+': '+attempt.status+'. '+(attempt.effect||''));
      if(attempt.status==='refused')lines.push('Owner refusal: '+(attempt.refusal?.code||'')+' '+(attempt.error||''));
      if(attempt.postimage)lines.push('Observed after saving: '+attempt.postimage.fields.title);
      if(attempt.observed)lines.push(attempt.observed.matches_attempt?'The owner now shows the fields you attempted.':'The owner does not show the fields you attempted.');}
    status.textContent=lines.join(' ');status.className='work-status'+(attempt?.status==='refused'||attempt?.status==='uncertain'?' error':'');
  }
  life.own(()=>root.remove?.());life.own(port.subscribe(paint));paint(port.snapshot());
  return {destroy(){life.dispose();}};
}
