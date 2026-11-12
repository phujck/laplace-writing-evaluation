import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {paragraphSourceIdentity,manuscriptBlockRows} from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {walkSource} from './helpers/walk_source.mjs';
const long='N1-p340282366920938463463374607431768211455';
test('rendered merged/split occurrences preserve all opaque logical units without claiming a primary attachment',()=>{
 const merged={id:'occurrence-A',sectionId:'rendered-heading',source_section:'N2',spec_id:long,spec_ids:[long,'N1-p2'],src:{file:'main.tex',line_start:10,line_end:12}};
 assert.deepEqual(paragraphSourceIdentity(merged),{specIds:[long,'N1-p2'],specId:'',specIdsComplete:true,sourceSection:'N2'});
 const split={...merged,id:'occurrence-B',spec_ids:[long]};assert.equal(paragraphSourceIdentity(split).specId,long);
 const rows=manuscriptBlockRows([merged,split]);assert.deepEqual(rows.map(row=>row.spec_ids),[[long,'N1-p2'],[long]]);assert.notEqual(rows[0].id,rows[1].id);
 assert.equal(paragraphSourceIdentity({...merged,spec_ids:undefined}).specId,'','legacy primary is not complete provenance');
});
test('Walk section joins use explicit current source section rather than ID prefix or title similarity',async()=>{
 const source=walkSource();
 const code=source.slice(source.indexOf('function planSectionFor('),source.indexOf('async function renderJoins'));
 const context={};vm.createContext(context);vm.runInContext(code+';this.join=planSectionFor;',context);
 const plan={sections:[{id:'N1',title:'Same title'},{id:'N2',title:'Same title'}]};
 assert.equal(context.join({spec_id:long,source_section:'N2',sectionId:'N1'},plan).id,'N2');
 assert.equal(context.join({spec_id:long,sectionId:'N1'},plan),null);
 assert.equal(context.join({source_section:'N2'},{sections:[plan.sections[1],plan.sections[1]]}),null);
});

test('legacy PDF section index uses emitted occurrence section and refreshes on same-size new maps',async()=>{
 const source=await readFile(new URL('../src/laplace/web/static_shared/artefact-panes.mjs',import.meta.url),'utf8');
 const start=source.indexOf('function _firstPos('),end=source.indexOf('// resolve one finding',start),code=source.slice(start,end);
 const context={entries:{[long]:[{kind:'paragraph',source_section:'N2',spec_ids:[long],source_file:'main.tex',occurrence:0,page:2,y0:20}]},PLAN:{sections:[{id:'N2',nodes_in_order:[]}]}};
 vm.createContext(context);vm.runInContext('let SEC_FIRST,NODE2SEC,MARK_IDX_KEY,MARK_IDX_ENTRIES,MARK_IDX_PLAN;const _corpus=()=>"book";const _nmEntries=()=>entries;'+code+';this.read=()=>{_buildAnchorIndex();return [...SEC_FIRST.keys()];};',context);
 assert.equal(JSON.stringify(context.read()),JSON.stringify(['N2']));
 context.entries={[long]:[{kind:'paragraph',source_section:'N3',spec_ids:[long],source_file:'main.tex',occurrence:0,page:2,y0:20}]};
 assert.equal(JSON.stringify(context.read()),JSON.stringify(['N3']));
 context.entries={[long]:[{kind:'paragraph',page:2,y0:20}]};assert.equal(context.read().length,0,'legacy missing section is not reconstructed from ID prefix');
});
