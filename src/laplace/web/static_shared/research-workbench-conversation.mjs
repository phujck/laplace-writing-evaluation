// The existing project conversation, situated by an explicit object pointer.
// Opening/reading never changes the authored target; only Use does so.
import {WorkspaceSession} from './workspace-session.mjs';
import {objectContextInput} from './research-object-context.mjs';
import {renderArtifactMarkdown} from './workspace-inspection.mjs';
import {el,button} from './research-workbench-view.mjs';
export async function mountSituatedConversation(host,{project,pointer,label,isCurrent=()=>true,onClose=()=>{},onRead=()=>{},onWork=null,onChanged=()=>{}}={}){
  if(typeof project!=='string'||!project)throw Error('The object owner has not supplied a conversation project.');
  let held=pointer?objectContextInput(pointer):null;const section=el('section','','rw-conversation workspace'),heading=el('h3','Discuss '+label),status=el('p','','rw-status'),tools=el('div','','rw-actions'),body=el('div');status.setAttribute('role','status');
  const close=button('Close conversation',()=>{destroy();onClose();}),use=button('Use this object for the next message',()=>{
    try{if(!current()||!held)return;const target=session.localDocumentTarget();session.useResearchObject(held,label,target,{epoch:session.viewEpoch,intentRevision:session.intentRevision||0});session.find('[data-message]').focus();status.textContent='Object selected. Your exact message draft is retained; Send remains explicit.';}catch(error){status.textContent=error.message;}
  },{disabled:true,control:'research:action'});tools.append(use,close);section.append(heading,el('p','Choose an ordinary conversation or a new one. Use explicitly attaches this inspected object; reading elsewhere keeps the original message target.','rw-qualification'),tools,status,body);host.append(section);
  let alive=true;const current=()=>alive&&isCurrent()&&section.isConnected!==false;
  const session=new WorkspaceSession(body,{project,getContext:()=>({surface:'project',label:'Project'}),onClose:()=>{destroy();onClose();},onOpenOwner:handle=>onRead(handle,'Owner reading'),onOpenWork:onWork,onChanged,renderFinalMessage:(host,text,options={})=>renderArtifactMarkdown(host,text,{project,...options,onInspectOwner:read=>onRead(read,'Owner reading')}),onOpenArtifact:handle=>onRead(handle,'Artifact')});
  // The global object pane supplies only actual supported doors. Manuscript
  // proposal controls remain in their existing project surface.
  for(const selector of ['[data-proposals]','[data-review]','[data-add-local-document]']){const node=session.find(selector);if(node)node.hidden=true;}
  use.hidden=!held;await session.ready;if(!current()){session.destroy();section.remove();return null;}use.disabled=false;
  function destroy(){if(!alive)return;alive=false;session.destroy();section.remove();}
  return {session,section,setObject(pointer,nextLabel){held=objectContextInput(pointer);use.hidden=false;label=nextLabel;heading.textContent='Discuss '+label;},get hasDraft(){return !!session.find('[data-message]')?.value||!!session.messageIntent?.submission;},destroy};
}
