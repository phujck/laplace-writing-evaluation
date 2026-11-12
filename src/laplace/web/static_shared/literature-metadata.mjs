// The existing local Literature metadata fields, shared by manual and retained-source entry.
// This leaf only edits human metadata. The caller owns source identity, transport and recovery.
import {declareControl} from './workspace-presentation.mjs';
const el=(tag,text='')=>{const node=document.createElement(tag);node.textContent=text;return node;};
export function renderLiteratureMetadataForm(host,{values={},retainedSource=null,onChange=()=>{},onSave=()=>{},saveLabel='Save source to project library',disabled=false}={}){
 const form=el('form');form.className='literature-form';const controls={};
 const field=(parent,label,name,{kind='input',choices=null,required=false,placeholder='',type='text'}={})=>{const wrap=el('label',label),node=el(choices?'select':kind);node.name=name;if(kind==='input'&&!choices)node.type=type;node.required=required;node.placeholder=placeholder;if(choices)for(const [value,label]of choices){const option=el('option',label);option.value=value;node.append(option);}node.value=values[name]??'';node.oninput=()=>onChange(name,node.value);node.onchange=node.oninput;wrap.append(node);parent.append(wrap);if(choices&&name==='item_type')declareControl(node,retainedSource?'literature:item-type':'literature-library:local-item-type');controls[name]=node;return node;};
 field(form,'Title','title',{required:true});
 const description=(parent)=>field(parent,'Source provenance','description',{kind:'textarea',required:true,placeholder:'For example: author-supplied draft, received 29 September 2026.'});
 const extra=retainedSource?el('details'):form;if(retainedSource){description(form);const identity=el('details');identity.append(declareControl(el('summary','Exact retained source'),'literature:exact-source'),el('pre',typeof retainedSource==='string'?retainedSource:JSON.stringify(retainedSource,null,2)));form.append(identity);extra.append(declareControl(el('summary','More bibliography details'),'literature:more-fields'));}
 field(extra,'Authors (one per line)','creators',{kind:'textarea'});field(extra,'Year','year');field(extra,'Source type','item_type',{choices:[...(retainedSource?[['','Not specified']]:[]),['unpublished','Unpublished paper / notes'],['book','Book'],['journalArticle','Journal article'],['preprint','Preprint'],['thesis','Thesis'],['bookSection','Book chapter'],['misc','Other source']]});field(extra,'Publisher / institution (optional)','publisher');
 if(!retainedSource){description(form);field(form,'Local file path (optional)','path',{placeholder:'An existing PDF, text or TeX file'});}
 if(!retainedSource)field(extra,'Original source URL (optional)','url',{type:'url'});field(extra,'Citation key (optional)','citekey');field(extra,'Journal or collection (optional)','publication_title');field(extra,'ISBN (optional)','isbn');field(extra,'Pages (optional)','pages');
 const save=declareControl(el('button',saveLabel),retainedSource?'literature:save':'literature-library:local-save');save.type='submit';save.className='primary';form.append(save);if(retainedSource)form.append(extra);host.append(form);
 const snapshot=()=>Object.fromEntries(Object.entries(controls).map(([name,node])=>[name,node.value]));
 const setDisabled=value=>{for(const node of Object.values(controls))node.disabled=!!value;save.disabled=!!value;};setDisabled(disabled);
 form.onsubmit=event=>{event.preventDefault();return onSave(snapshot());};
 return {form,controls,save,snapshot,setDisabled,setBusy:value=>{save.disabled=!!value;}};
}
