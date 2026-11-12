// Eventful local DOM for close-owner controls. Actual browser evidence remains required.
import {installDOM,Node} from './evidence_reader_harness.mjs';
export function installInspectorCloseDOM({listenerFirst=false,deferClose=false}={}){
 const dom=installDOM(),prior={add:Node.prototype.addEventListener,remove:Node.prototype.removeEventListener,close:Node.prototype.close,show:Node.prototype.showModal,focus:Node.prototype.focus},pending=[],page=globalThis.document,events=new Map();
 page.addEventListener=(type,fn)=>{const rows=events.get(type)||[];rows.push(fn);events.set(type,rows);};page.removeEventListener=(type,fn)=>events.set(type,(events.get(type)||[]).filter(row=>row!==fn));
 Node.prototype.addEventListener=function(type,fn,options){this.eventHandlers??=new Map();const rows=this.eventHandlers.get(type)||[];rows.push({fn,once:options?.once});this.eventHandlers.set(type,rows);};
 Node.prototype.removeEventListener=function(type,fn){this.eventHandlers?.set(type,(this.eventHandlers.get(type)||[]).filter(row=>row.fn!==fn));};
 Node.prototype.focus=function(options){prior.focus.call(this,options);for(const fn of [...(events.get('focusin')||[])])fn({type:'focusin',target:this});};
 Node.prototype.showModal=function(){this.nativeOpener=page.activeElement;prior.show.call(this);};
 Node.prototype.close=function(){if(this.open===false)return;this.open=false;this.nativeOpener?.focus?.({preventScroll:true});const dispatch=()=>{const event={type:'close',target:this},listeners=()=>{for(const row of [...(this.eventHandlers?.get('close')||[])]){row.fn(event);if(row.once)this.removeEventListener('close',row.fn);}};if(listenerFirst)listeners();this.onclose?.(event);if(!listenerFirst)listeners();};if(deferClose)pending.push(dispatch);else dispatch();};
 return {...dom,page,async flushClose(){while(pending.length)pending.shift()();await new Promise(setImmediate);},restore(){Node.prototype.addEventListener=prior.add;Node.prototype.removeEventListener=prior.remove;Node.prototype.close=prior.close;Node.prototype.showModal=prior.show;Node.prototype.focus=prior.focus;dom.restore();}};
}
