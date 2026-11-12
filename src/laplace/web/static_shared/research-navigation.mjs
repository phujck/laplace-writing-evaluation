// One presentation trail for semantic moves. Owner observations stay detached in
// memory; nothing here changes a draft, input basket, request or permission.
export function createResearchNavigation({capture,restore,url,guardRestore=null,history=globalThis.history,events=globalThis.window,limit=24}={}){
  let alive=true,moving=false,serial=0,cursor=0,restoration=0,allowed=null,bounce=null;const scope='research-navigation:'+Math.random().toString(36).slice(2),frames=[{id:serial,value:capture(),url:url()}];
  const stamp=frame=>({...(history?.state||{}),research_navigation:{scope,id:frame.id}});
  const replace=()=>{const frame=frames[cursor];frame.value=capture();frame.url=url();history?.replaceState?.(stamp(frame),'',frame.url);};replace();
  function apply(at){if(!alive||at<0||at>=frames.length)return false;cursor=at;const lease=++restoration;restore(frames[at].value,{isCurrent:()=>alive&&lease===restoration});history?.replaceState?.(stamp(frames[at]),'',frames[at].url);return true;}
  const pop=event=>{const entry=event.state?.research_navigation;if(entry?.scope!==scope)return;const at=frames.findIndex(row=>row.id===entry.id);if(at<0)return;
    if(bounce&&entry.id===bounce.from){const held=bounce;bounce=null;if(held.resume&&frames[cursor]?.id===held.from){allowed=held.to;history.go?.(held.delta);}return;}
    if(allowed===entry.id){allowed=null;apply(at);return;}
    if(guardRestore&&at!==cursor){const from=frames[cursor].id,to=entry.id,delta=at-cursor;
      const resume=()=>{if(!alive||frames[cursor]?.id!==from)return;if(bounce?.from===from&&bounce.to===to){bounce.resume=true;return;}allowed=to;if(history?.go)history.go(delta);else apply(at);};
      if(guardRestore(resume)===false){if(history?.go){bounce={from,to,delta,resume:false};history.go(-delta);}else history?.replaceState?.(stamp(frames[cursor]),'',frames[cursor].url);return;}
    }
    apply(at);
  };events?.addEventListener?.('popstate',pop);
  return {get moving(){return moving;},get canBack(){return cursor>0;},remember(){if(alive&&!moving)replace();},async move(fn){if(!alive||moving)return null;++restoration;replace();moving=true;try{const result=await fn();if(result===null||result===false)return result;frames.splice(cursor+1);const frame={id:++serial,value:capture(),url:url()};frames.push(frame);if(frames.length>limit)frames.shift();cursor=frames.length-1;history?.pushState?.(stamp(frame),'',frame.url);return result;}finally{moving=false;}},back({admitted=false}={}){if(cursor<1)return false;const entry=history?.state?.research_navigation;if(entry?.scope===scope&&history?.back){if(admitted)allowed=frames[cursor-1].id;history.back();return true;}return apply(cursor-1);},destroy(){alive=false;++restoration;events?.removeEventListener?.('popstate',pop);frames.length=0;}};
}
