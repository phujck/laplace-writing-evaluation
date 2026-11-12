// WORKSPACE NOTICES (M5 S2 F1). Purpose: the shell's status line and control-failure channel: $ (a query
// scoped to the shell root), notice (the one status line, with an owner whose retry and detail become real
// buttons in the line), clearing an owner's refresh warning, guard (a handler whose failure is said in the
// status line), and button/actionAlert (a control whose failure is said beside it, replaced by the next
// attempt). Owns: the current notice owner. Public contract: mountNotices(root) -> {$, notice,
// clearRefreshWarning, guard, actionAlert, button}. No reads; DOM only inside the shell root.
import {E} from './workspace-dom.mjs';

export function mountNotices(root){
  let noticeOwner=null;
  const $=selector=>root.querySelector(selector),notice=(text,error=false,owner=null)=>{noticeOwner=owner;delete $(
    '[data-notice]').dataset.manuscriptChange;delete $('[data-notice]').dataset.manuscriptWait;$('[data-notice]').textContent=text;$(
    '[data-notice]').title='';$('[data-notice]').classList.toggle('error',error);noticeRecovery($('[data-notice]'),owner);};
  // repair2 R5: a failure owner may offer Try again now (its retry) and Details (its exact owner message),
  // as real buttons a keyboard or touch user can reach, inside the status line itself
  const noticeRecovery=(host,owner)=>{if(!owner)return;
    if(typeof owner.retry==='function'){const again=E('button','Try again now','act');again.type='button';again.setAttribute('data-notice-retry','');
      again.onclick=async()=>{again.disabled=true;try{await owner.retry();}finally{again.disabled=false;}};host.append(' ',again);}
    if(owner.detail){const toggle=E('button','Details','act');toggle.type='button';toggle.setAttribute('aria-expanded','false');const detail=E('span',
      owner.detail,'notice-detail');detail.hidden=true;detail.id='notice-detail-'+(owner.at||Date.now());toggle.setAttribute('aria-controls',detail.id);
      toggle.onclick=()=>{detail.hidden=!detail.hidden;toggle.setAttribute('aria-expanded',String(!detail.hidden));
        toggle.textContent=detail.hidden?'Details':'Hide details';};host.append(' ',toggle,' ',detail);}};
  const clearRefreshWarning=owner=>{if(noticeOwner===owner)notice('');};
  // THE FAILURE CHANNEL (plan §3, accepted): a control's failure is said beside the control
  // (an inline alert that the next attempt replaces); the notice row is for view-load
  // failures and owner-wide announcements only. `guard` stays for non-control handlers.
  const guard=fn=>async event=>{event?.preventDefault();try{await fn(event);}catch(error){notice(error.message,true);}};
  const actionAlert=(control,message)=>{const previous=control.nextElementSibling;if(previous?.dataset?.actionAlert!=null)previous.remove();if(
    !control.isConnected){notice(message,true);return;}const note=E('p',message,'error action-alert');note.dataset.actionAlert='';note.setAttribute(
    'role','alert');control.after(note);};
  const button=(label,fn,cls='')=>{const b=E('button',label,cls);b.type='button';b.onclick=async event=>{event?.preventDefault();
    const previous=b.nextElementSibling;if(previous?.dataset?.actionAlert!=null)previous.remove();b.disabled=true;try{await fn(event);}catch(error){
    actionAlert(b,error.message);}finally{b.disabled=false;}};return b;};
  return {$,notice,clearRefreshWarning,guard,actionAlert,button};
}
