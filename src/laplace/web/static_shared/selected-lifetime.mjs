// SELECTED LIFETIME (P2 service spine, WORK-frontend-p2-service-spine-20261021). Purpose: the lifetime mechanics the
// selected-region consumers repeated, and no domain meaning: whether a controller is still live, a generation that
// any replacement advances, the cleanups disposal runs once, and (for a selected region) the qualified selection,
// its visit stack and the per-object delivery tokens. The Work port (work-port.mjs), the Work card
// (workspace-work.mjs), its outline (work-port-outline.mjs) and the System owners view (workspace-owners.mjs) use it;
// each keeps its own fields, guards and owner rules.
// Currentness is controller identity, never DOM attachment: a lease taken now stays valid until the controller is
// disposed or its generation advances, so a valid first preparation into a detached fragment is not suppressed and a
// stale delivery never crosses a replacement.
// Public contract:
//   createLifetime() -> {disposed, generation, advance(), lease() -> isCurrent(), live(message), own(cleanup), dispose()}
//   createSelectedLifetime({qualify}) -> the lifetime plus {selection, visitDepth, select(ref) -> changed, back() -> ref,
//     issue(key) -> token, admissible(key, token), accept(key, token), superseded(key, token), accepted(key),
//     subscribe(listener) -> unsubscribe, notify(value), listenerCount()}
// select() pushes the previous selection onto the visit stack and advances the generation when the qualified identity
// changes (the first selection advances it too); back() pops it and advances. A delivery token is admissible only
// if it is newer than every accepted token of the same key: deliveries are ordered by issue, not by owner time.
// dispose() is idempotent: it advances the generation, runs the cleanups in reverse order (one failing cleanup does
// not stop the rest) and clears the listeners; own() after disposal runs the cleanup at once.
export function createLifetime(){
  let disposed=false,generation=0;const cleanups=[];
  return {
    get disposed(){return disposed;},
    get generation(){return generation;},
    advance(){return ++generation;},
    lease(){const at=generation;return ()=>!disposed&&at===generation;},
    live(message='This view was disposed.'){if(disposed)throw Error(message);},
    own(cleanup){if(disposed)cleanup();else cleanups.push(cleanup);return cleanup;},
    dispose(){if(disposed)return false;disposed=true;++generation;for(const cleanup of cleanups.splice(0).reverse()){try{cleanup();}catch{/* the rest still run */}}return true;},
  };
}
export function createSelectedLifetime({qualify=ref=>ref.project+'::'+ref.id}={}){
  const life=createLifetime(),visits=[],tokens=new Map(),listeners=new Set();let selection=null;
  life.own(()=>listeners.clear());
  const token=key=>{if(!tokens.has(key))tokens.set(key,{issued:0,accepted:0});return tokens.get(key);};
  return {
    get disposed(){return life.disposed;},get generation(){return life.generation;},
    advance:life.advance,lease:life.lease,live:life.live,own:life.own,dispose:life.dispose,
    get selection(){return selection;},
    get visitDepth(){return visits.length;},
    select(ref){
      const changed=!selection||qualify(selection)!==qualify(ref);
      if(selection&&changed)visits.push(selection);
      if(changed)life.advance();
      selection={...ref};return changed;
    },
    back(){if(!visits.length)return null;selection=visits.pop();life.advance();return selection;},
    issue:key=>++token(key).issued,
    admissible:(key,value)=>!life.disposed&&value>token(key).accepted,
    accept(key,value){token(key).accepted=value;},
    superseded:(key,value)=>life.disposed||value<token(key).issued||value<=token(key).accepted,
    accepted:key=>token(key).accepted,
    subscribe(listener){life.live();listeners.add(listener);return ()=>listeners.delete(listener);},
    notify(value){if(life.disposed)return;for(const listener of [...listeners])listener(value);},
    listenerCount:()=>listeners.size,
  };
}
