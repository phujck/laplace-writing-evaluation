// Closed pointer carried with authored conversation intent. The object owner
// validates scope/currentness at admission; this helper grants no read or effect.
import {checkedReference,copy} from './research-workbench-state.mjs';
export function objectContextInput(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!['reference','expected_basis','coordinate'].includes(key))||!/^sha256:[a-f0-9]{64}$/.test(value.expected_basis||''))throw Error('Inspect this object before attaching it to a conversation. Its exact owner reference and basis are required.');
  if(value.coordinate&&(!['workflow-step','work-phase','delivery-event'].includes(value.coordinate.kind)||typeof value.coordinate.id!=='string'||!value.coordinate.id||Object.keys(value.coordinate).some(key=>!['kind','id'].includes(key))))throw Error('The object coordinate must be an exact local target under its parent.');
  return {reference:checkedReference(value.reference),expected_basis:value.expected_basis,...(value.coordinate?{coordinate:copy(value.coordinate)}:{})};
}
export const objectContextCopy=value=>copy(objectContextInput(value));
