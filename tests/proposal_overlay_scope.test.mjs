import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {walkSource} from './helpers/walk_source.mjs';

const source=walkSource();
const scope=source.slice(source.indexOf('function suspendAuthorChanges('),source.indexOf('\n// ',source.indexOf('function suspendAuthorChanges(')));
test('candidate comparison suspends saved-author overlays without changing history or preference and restores its exact reading',async()=>{
 const records=new Map([['chapter.tex','CHANGE-kept']]),prior={hunk:{before:'Prior text',after:'Current text'},data:{id:'CHANGE-kept'}},reads=[];
 const context={authorChangesSuspended:false,authorChangesGeneration:2,authorChangesEnabled:true,authorComparisonBeforeReview:null,
  authorChangeRecords:records,docEl:{querySelector:()=>({changePreview:prior})},clearAuthorChanges(){context.cleared=(context.cleared||0)+1;},
  refreshAuthorChanges:async options=>reads.push(options),emit(){}};
 vm.createContext(context);vm.runInContext(scope,context);
 context.suspendAuthorChanges();context.suspendAuthorChanges();assert.equal(context.cleared,1);assert.equal(context.authorChangesGeneration,3);assert.equal(context.authorChangesEnabled,true);assert.equal(records.get('chapter.tex'),'CHANGE-kept');
 context.resumeAuthorChanges();await Promise.resolve();assert.equal(reads.length,1);assert.equal(reads[0].restoreComparison,prior);assert.equal(reads[0].focus,false);assert.equal(context.authorChangesSuspended,false);assert.equal(records.size,1);
 context.suspendAuthorChanges();context.authorChangesEnabled=false;context.resumeAuthorChanges();await Promise.resolve();assert.equal(reads.length,1,'Closing a comparison must respect a deliberately disabled history display.');
 context.authorChangesEnabled=true;context.suspendAuthorChanges();context.resumeAuthorChanges(false);await Promise.resolve();assert.equal(reads.length,1,'Explicitly opening another history scope should not start a competing restore read.');
});
