// WORK OBSERVER (WORK-source-state-work-review-context-20261015, Sol D2-B). Purpose: notice that the project's
// Work, the selected Work or their qualified activity may have changed, and hand that hint to the Work controller,
// which makes bounded owner rereads. Ownership: project_work_navigation.observe owns the token
// ('wo1.<records>.<selected>.<activity>', project- and selection-scoped; the ledger stat only invalidates the owner's
// cache) and names which components differ from the token this loop carries; this module keeps only that one
// token, its delay and its timer. Public contract: observeWork({project, request, selected(), isCurrent(),
// onChange(value), basis(), clock, doc}) -> {stop(), tick(), state()}. Delivery (repair1 WI-R3): the token is the
// APPLIED basis; it advances only after onChange resolves. A failed delivery (a transient owner read or paint failure)
// keeps the prior token, backs off and delivers the same hint again on the next read, with no new owner event needed.
// Baseline: the first read after mount or after a selection change is compared with basis(), the token components the
// mounted reads consumed (their observe_basis), so a change between the detail read and the first observation is
// delivered, not absorbed; without a basis it is a plain baseline. An unchanged read backs off by poll.backoff up to
// poll.max_ms; a change resets the delay to poll.after_ms; the next read is brought forward to the owner's
// expires_next_at (an observation expiry changes the token without any write); errors back off the same way.
// Hidden: no timer runs and becoming visible reads once at once. Destroyed: stop() clears the timer and the
// listener, and a late reply is dropped. It only ever issues GET /work/state view=observe and never writes.
export function observeWork({project,request,selected,isCurrent,onChange,basis=()=>null,clock={setTimeout:(...a)=>globalThis.setTimeout(...a),clearTimeout:(...a)=>globalThis.clearTimeout(...a),now:()=>Date.now()},doc=globalThis.document,start=0}){
  let token=null,tokenFor,delay=null,timer=null,stopped=false,inflight=false,reads=0,failures=0,poll={};
  const hidden=()=>doc?.visibilityState==='hidden';
  const schedule=ms=>{clock.clearTimeout(timer);timer=null;if(stopped||hidden())return;timer=clock.setTimeout(tick,ms);};
  async function tick(){
    timer=null;if(stopped||inflight||hidden()||!isCurrent())return;
    inflight=true;const id=selected()||null;if(id!==tokenFor){token=null;tokenFor=id;}
    let wait;
    try{
      reads++;let value=await request('/work/state?'+new URLSearchParams({project,view:'observe',...(id?{id}:{}),...(token?{since:token}:{})}));
      if(stopped||!isCurrent())return;
      if(value?.project!==project||value.view!=='observe'||typeof value.token!=='string')throw Error('The Work owner returned a different observation.');
      if(value.poll)poll=value.poll;const base=poll.after_ms||5000,max=poll.max_ms||60000;
      let changed=!!token&&value.changed===true&&id===(selected()||null);
      if(!token){
        // baseline: what did the mounted reads consume? a differing component is a change to deliver now
        const mounted=basis(),parts=String(value.token).split('.');
        const missed=mounted?[['records',parts[1]],['selected',parts[2]],['activity',parts[3]]].filter(([name,part])=>mounted[name]!=null&&mounted[name]!==part).map(([name])=>name):[];
        if(missed.length){changed=true;value={...value,changed:true,changes:missed};}
      }
      if(changed)await onChange(value);   // throws on a failed delivery: the token below is not advanced
      if(stopped||!isCurrent())return;
      token=value.token;delay=changed?base:Math.min(max,delay?delay*(poll.backoff||2):base);
      wait=delay;if(value.expires_next_at){const ms=Date.parse(value.expires_next_at)-clock.now()+250;if(ms>0)wait=Math.min(wait,ms);}
    }catch{failures++;delay=Math.min(poll.max_ms||60000,(delay||poll.after_ms||5000)*(poll.backoff||2));wait=delay;}
    finally{inflight=false;}
    if(!stopped&&wait!=null)schedule(Math.max(1000,wait));
  }
  const visibility=()=>{if(stopped)return;if(hidden()){clock.clearTimeout(timer);timer=null;}else schedule(0);};
  doc?.addEventListener?.('visibilitychange',visibility);
  schedule(start);
  return {stop(){stopped=true;clock.clearTimeout(timer);timer=null;doc?.removeEventListener?.('visibilitychange',visibility);},
    tick,state:()=>({token,delay,scheduled:!!timer,stopped,inflight,reads,failures})};
}
