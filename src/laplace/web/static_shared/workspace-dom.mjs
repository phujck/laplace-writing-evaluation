// WORKSPACE DOM (M5 S2 F1). Purpose: the element and form-field helpers the shell and its domain
// controllers share: E (an element with text and class), slug, title (the concept display label),
// and field/area/section, which build labelled inputs with unique ids. Owns: the field id sequence
// only. Public contract: E, slug, title, field, area, section. No reads, no state beyond the counter.
import {displayLabel} from '/shared/concept-reader.mjs';
export const E=(tag,text='',cls='')=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e;};
export const slug=text=>text.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,70);
export const title=displayLabel;
let workspaceFieldId=0;
export function field(form,label,name,value='',options){const l=E('label',label),input=E(options?'select':'input');input.name=name;
  input.id='workspace-field-'+(++workspaceFieldId);l.htmlFor=input.id;input.setAttribute('aria-label',label);if(options)for(const [v,t]of options){
  const option=E('option',t);option.value=v;input.append(option);}input.value=value??'';l.append(input);form.append(l);return input;}
export function area(form,label,name,value='',rows=4){const l=E('label',label),input=E('textarea');input.name=name;input.id='workspace-field-'+(
  ++workspaceFieldId);l.htmlFor=input.id;input.setAttribute('aria-label',label);input.rows=rows;input.value=value||'';l.append(input);form.append(l);return input;}
export function section(host,label,description){const c=E('section','','work-card');c.append(E('h3',label));if(description)c.append(E('p',description,
  'muted'));host.append(c);return c;}
