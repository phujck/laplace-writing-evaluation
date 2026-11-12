// The shell's named services (M5 S2 F1) for tests that run a domain controller's own functions in a small
// sandbox. A test's setup declares the plain shell names it controls (show, notice, state, task, dirty, ...);
// SERVICE_PRELUDE, placed after that setup, builds the service objects the moved functions now call
// (views.show(), ui.notice(), workState.get(), work.task(), ...) from those names. A name the setup does not
// declare becomes a no-op. Nothing here is a second implementation: every service only forwards.
const pick = (name, fallback) => `(typeof ${name}!=='undefined'?${name}:${fallback})`;
const call = (name, fallback = 'undefined') => `(...a)=>typeof ${name}==='function'?${name}(...a):${fallback}`;
const assign = name => `v=>{if(typeof ${name}!=='undefined')${name}=v;}`;
export const SERVICE_PRELUDE = `
const views={current:()=>${pick('currentView', "'overview'")},show:${call('show')},generation:()=>${pick('loadVersion', '0')},
  info:()=>${pick('info', '{}')},mode:()=>${pick('structureMode', "'graph'")},setMode:${assign('structureMode')},changed:${call('navigationChanged')}};
const forms={dirty:()=>${pick('dirty', 'false')},setDirty:${assign('dirty')},leave:${call('leaveForm', 'true')},guard:fn=>typeof guard==='function'?guard(fn):fn,
  wire:${call('wireForm')},changed:${call('changed')}};
const ui={notice:${call('notice')},button:${call('button')},actionAlert:${call('actionAlert')},$:${call('$', 'null')},root:${pick('root', '{isConnected:true}')},
  main:()=>typeof $==='function'?$('[data-main]'):null};
const workState={get:()=>${pick('state', 'undefined')},set:${assign('state')},reload:${call('reloadState')},summaryRead:${pick('WORK_SUMMARY_READ', "''")}};
const structures={get:()=>${pick('structure', 'null')},set:${assign('structure')}};
const work={task:()=>${pick('task', 'null')},requested:()=>${pick('requestedWork', 'null')},open:${call('openWork')},admit:${call('admitRequestedWork')},
  request:${call('requestWorkSelection')},reload:${call('reloadState')},clearSelection:()=>{if(typeof task!=='undefined')task=null;}};
const discussion={session:()=>${pick('session', '{}')},talk:${call('talk')},open:${call('openSession')},conversation:${call('openConversation')},
  savedTurn:${call('readSavedTurn')},generateProfile:${call('generateProfile')}};
const inspect={savedMarkdown:${call('renderSavedMarkdown')},projectArtifact:${call('inspectProjectArtifact')},ownerRead:${call('inspectOwnerRead')}};
const help={openGuide:${call('openGuide')}},navigation={refresh:${call('refreshCapabilityNavigation')}};
const diagnostics={counters:${call('pageCounters', '({})')},page:${pick('pageDiagnostics', 'false')}};
const place={remember:${call('rememberReaderReturn')}};
`;
