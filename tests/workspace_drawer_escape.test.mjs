// M5 (2026-10-20): Escape closes the open drawer, locally. Only the drawer layout, only while open, only from the
// Menu or from inside the navigation; the keyboard returns to Menu and aria-expanded is true to the state. An event an
// overlay already handled (defaultPrevented), a key pressed outside the drawer, or the compact layout's nav are not
// the drawer's to close. Nothing is persisted.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {register} from 'node:module';
register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
import {installHTMLDocument} from './helpers/html_dom.mjs';
const {mountChrome}=await import('../src/laplace/web/static_shared/workspace-chrome.mjs');
const el=(tag,attrs={},text='')=>{const node=document.createElement(tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);if(text)node.textContent=text;return node;};
function chrome(width){
  const dom=installHTMLDocument({width});
  const root=el('div',{class:'workspace'});document.body.append(root);
  const nav=el('nav',{class:'workspace-nav'});root.append(nav);
  for(const name of ['data-nav','data-focus','data-talk','data-guide'])root.append(el('button',{[name]:''}));
  root.append(el('aside',{'data-session':''}));const main=el('main',{'data-main':''});root.append(main);
  const ui={root,$:selector=>root.querySelector(selector),button:(label,run)=>{const b=el('button',{},label);b.onclick=run;return b;}};
  const views={current:()=>'overview',show:async()=>true,info:()=>({capabilities:{manuscript:true,work:true,materials:true,history:true,settings:true}})};
  const session={catalogueOpened(){},setLibrary(){},expand(){}};
  const listeners=[];const pageListen=(target,type,fn)=>{target.addEventListener(type,fn);listeners.push([target,type,fn]);};
  mountChrome('book',{views,ui,discussion:{session:()=>session},help:{followLayout(){}},initialQuery:new URLSearchParams(''),pageListen,outline:{render:async()=>{}}});
  const menu=root.querySelector('[data-nav]');
  const press=(target,{prevented=false}={})=>{const event={type:'keydown',key:'Escape',target,defaultPrevented:prevented,prevented:false,preventDefault(){this.prevented=true;this.defaultPrevented=true;}};document.dispatchEvent(event);return event;};
  return {dom,root,nav,menu,main,press,open:()=>menu.onclick(),closed:()=>root.classList.contains('nav-closed')};
}

test('719: Escape from the navigation closes the open drawer, returns the keyboard to Menu and keeps aria-expanded true to the state',()=>{
  const c=chrome(719);
  try{
    assert.equal(c.root.dataset.navLayout,'drawer');assert.equal(c.closed(),true,'the drawer starts closed');
    c.open();assert.equal(c.closed(),false);assert.equal(c.menu.getAttribute('aria-expanded'),'true');
    const button=el('button',{'data-view':'history'},'Activity');c.nav.append(button);button.focus();
    const event=c.press(button);
    assert.equal(c.closed(),true,'Escape from inside the navigation closed the drawer');assert.equal(event.prevented,true);
    assert.equal(c.menu.getAttribute('aria-expanded'),'false');assert.equal(document.activeElement,c.menu,'the keyboard is back on Menu');
    assert.equal(localStorage.getItem('laplace:workspace:nav-closed'),null,'the drawer never writes the preference');
    // Escape from Menu itself while the drawer is open
    c.open();c.menu.focus();c.press(c.menu);assert.equal(c.closed(),true);assert.equal(document.activeElement,c.menu);
  }finally{c.dom.restore();}
});

test('Escape outside the drawer, an already-handled Escape, a closed drawer and the compact layout are left alone',()=>{
  const c=chrome(719);
  try{
    c.open();const outside=el('button',{},'Send');c.main.append(outside);outside.focus();
    c.press(outside);assert.equal(c.closed(),false,'a key pressed in the main region is not the drawer\'s');assert.equal(document.activeElement,outside);
    const button=el('button',{'data-view':'history'},'Activity');c.nav.append(button);button.focus();
    const handled=c.press(button,{prevented:true});assert.equal(c.closed(),false,'an overlay that already handled Escape keeps it');assert.equal(handled.prevented,false,'the drawer did not touch an event another owner handled');
    c.menu.onclick();assert.equal(c.closed(),true);const idle=c.press(button);assert.equal(idle.prevented,false,'a closed drawer takes no Escape');
  }finally{c.dom.restore();}
  const compact=chrome(1000);
  try{
    assert.equal(compact.root.dataset.navLayout,'compact');compact.root.classList.remove('nav-closed');
    const button=el('button',{'data-view':'history'},'Activity');compact.nav.append(button);button.focus();
    const event=compact.press(button);assert.equal(compact.closed(),false,'the compact nav is a column, not a drawer');assert.equal(event.prevented,false);
  }finally{compact.dom.restore();}
});
