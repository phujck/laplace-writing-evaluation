// WORKSPACE CONTEXT (M5 S2 F1). Purpose: what the next conversation message is attached to: the selected
// History entry or scope, the manuscript's source attention, inspection or reading place (the walk's own
// place memo, never rebuilt from block rows), the reader-plan selection, the argument surface or concept,
// the research attention, or the current view with the selected Work. Ownership: every attention belongs to
// its view controller; this controller only asks them, in that order. Public contract: mountContext(services)
// -> {read()}. Services: views (current view), labels, work (selected task), activity, manuscript, readerHome,
// argument, research, shellState (structure mode, active section, structure read, place memo).

export function mountContext({views,labels,work,activity,manuscript,readerHome,argument,research,shellState}){
  const context=()=>{
    if(views.current()==='history')return activity.historyContext(work.task());
    if(views.current()==='manuscript'){
      const sourceAttention=manuscript.editor()?.attention();if(sourceAttention)return {...sourceAttention,task_id:work.task()?.id};
      const inspection=manuscript.sourceWindow()?.walk?.inspection?.();if(inspection)return {...inspection,task_id:work.task()?.id};
      // the place memo (plan §11 producer_defects): the walk already said where the person is
      if(shellState.placeMemo()&&shellState.placeMemo().source===manuscript.sourceWindow())return {surface:'manuscript',label:shellState.placeMemo(
        ).label||'Manuscript',task_id:work.task()?.id,selection:shellState.placeMemo().selection||undefined};
      const walk=manuscript.sourceWindow()?.walk,pos=walk?.readingPosition?.(),blocks=walk?.blocks?.({text:false})||[],block=blocks.find(item=>
        item.id===pos?.blockId),scope=blocks.filter(item=>item.section===pos?.sectionId&&item.file===block?.file);
      return {surface:'manuscript',label:pos?.label||'Manuscript',task_id:work.task()?.id,selection:block?{files:[block.file],section_ids:[
        pos.sectionId],line_start:scope.length?Math.min(...scope.map(item=>item.line_start)):block.line_start,line_end:scope.length?Math.max(
        ...scope.map(item=>item.line_end)):block.line_end}:undefined};
    }
    if(views.current()==='reader-plan')return {...(readerHome.context()||{surface:'structure',label:'Reader plan',section_ids:[]}),task_id:work.task()?.id};
    if(views.current()==='argument'){
      const argumentFocus=shellState.mode()==='graph'?argument.context(work.task(),shellState.structure()):null;if(argumentFocus)return argumentFocus;
      return {surface:'structure',label:shellState.mode()==='plan'&&shellState.activeSection()?shellState.activeSection().title:'Logical objects',
        task_id:work.task()?.id,section_ids:shellState.mode()==='plan'&&shellState.activeSection()?[shellState.activeSection().id]:[]};
    }
    const researchFocus=views.current()==='research'?research.attention():null;if(researchFocus)return {surface:'research',label:researchFocus.label||
      'Selected research',node_id:researchFocus.concept_id||researchFocus.claim_id,task_id:work.task()?.id,section_ids:[]};
    return {surface:['overview','work','material','settings'].includes(views.current())?'project':views.current(),label:labels[views.current()]+(
      work.task()?' · '+work.task().title:''),task_id:work.task()?.id,section_ids:[]};
  };
  return {read:context};
}
