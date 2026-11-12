// WORKSPACE INSPECTION (M5 S2 F1). Purpose: the shell's reading doors: saved Markdown rendered with its
// artifact, claim and owner links; a project artifact opened in the one shared inspector (writing-artifact's
// openEvidenceArtifact); and a qualified owner read opened in the same inspector, or the profile-preferences
// inspector for a profile read. Ownership: every artifact and owner read belongs to its owner; the one
// inspector adopts each dialog at its own door; this controller owns no state. Public contract:
// mountInspection(project, services) -> {savedMarkdown(host, text, options), projectArtifact(path, label,
// options), ownerRead(read, label, options)}. Services: discussion (session, profile generation), work
// (reload), home (style refresh).
import {E} from './workspace-dom.mjs';
import {projectRequest as api,artifactHumanTarget,markdownProtectedRanges,messageLinkParts,ownerHumanTarget} from "/shared/workspace-session.mjs";
import {inspectProfilePreferences} from './profile-preferences.mjs';
import {openArtifact as openEvidenceArtifact} from "/shared/writing-artifact.mjs";
import {qualifiedOwnerHTTP} from './writing-owner-read.mjs';
import {scientificText} from "/shared/concept-reader.mjs";

export function artifactMarkdownBlocks(value){
  const lines=String(value||'').replace(/\r\n?/g,'\n').split('\n'),out=[];let at=0;
  const special=line=>/^\s*(?:#{1,6}\s|```|>\s?|[-*+]\s+|\d+[.)]\s+)/.test(line);
  const cells=line=>{
    const text=line.trim(),protectedRanges=markdownProtectedRanges(text),parts=[];let value='',separators=0,rangeIndex=0;
    for(let i=0;i<text.length;i++){
      while(rangeIndex<protectedRanges.length&&protectedRanges[rangeIndex][1]<=i)rangeIndex++;
      const range=protectedRanges[rangeIndex],protectedPart=range&&i>=range[0]&&i<range[1]?range:null;
      if(text[i]==='\\'&&text[i+1]==='|'){value+=protectedPart&&text[protectedPart[0]]==='`'?'|':'\\|';i++;}
      else if(text[i]==='|'&&!protectedPart){parts.push(value.trim());value='';separators++;}
      else value+=text[i];
    }
    parts.push(value.trim());if(text.startsWith('|')&&parts[0]==='')parts.shift();if(text.endsWith('|')&&parts.at(-1)==='')parts.pop();
    return separators?parts:null;
  };
  const tableAt=index=>{
    const header=cells(lines[index]||''),delimiter=cells(lines[index+1]||'');
    if(!header||!delimiter||header.length!==delimiter.length||!delimiter.every(value=>/^:?-{3,}:?$/.test(value)))return null;
    const align=delimiter.map(value=>value.startsWith(':')&&value.endsWith(':')?'center':value.endsWith(':')?'right':value.startsWith(':')?'left':null),rows=[];let next=index+2;
    while(next<lines.length&&lines[next].trim()&&!special(lines[next])){const row=cells(lines[next]);if(!row)break;if(row.length!==header.length)return null;rows.push(row);next++;}
    return {kind:'table',header,align,rows,next};
  };
  while(at<lines.length){if(!lines[at].trim()){at++;continue;}let match;
    if((match=/^\s*```(.*)$/.exec(lines[at]))){const language=match[1].trim(),body=[];at++;while(at<lines.length&&!/^\s*```/.test(lines[
      at]))body.push(lines[at++]);if(at<lines.length)at++;out.push({kind:'code',text:body.join('\n'),language});continue;}
    const table=tableAt(at);if(table){const {next,...block}=table;out.push(block);at=next;continue;}
    if((match=/^\s*(#{1,6})\s+(.*)$/.exec(lines[at]))){out.push({kind:'heading',level:match[1].length,text:match[2].replace(/\s+#+$/,'')});at++;continue;}
    if((match=/^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(lines[at]))){const ordered=/^\d/.test(match[1]),items=[];while(at<lines.length&&(
      match=/^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(lines[at]))&&/^\d/.test(match[1])===ordered){items.push(match[2]);at++;}out.push({kind:'list',ordered,items});continue;}
    if(/^\s*>/.test(lines[at])){const body=[];while(at<lines.length&&/^\s*>/.test(lines[at]))body.push(lines[at++].replace(/^\s*>\s?/,''));out.push({
      kind:'quote',text:body.join('\n')});continue;}
    const body=[lines[at++]];while(at<lines.length&&lines[at].trim()&&!special(lines[at])&&!tableAt(at))body.push(lines[at++]);out.push({kind:'paragraph',text:body.join('\n')});
  }
  return out;
}
export function artifactInlineParts(value){
  const text=String(value||''),parts=[];let buffer='',at=0;
  const flush=()=>{if(buffer){parts.push({kind:'text',text:buffer});buffer='';}};
  const escaped=index=>{let count=0;while(index>0&&text[--index]==='\\')count++;return count%2===1;};
  const mathAt=index=>{if(escaped(index))return null;let close='',start='';if(text.startsWith('$$',index)){start='$$';close='$$';}else if(text[
    index]==='$'){start='$';close='$';}else if(text.startsWith('\\[',index)){start='\\[';close='\\]';}else if(text.startsWith('\\(',index)){
    start='\\(';close='\\)';}else{const env=/^\\begin\{((?:equation|align|gather|multline|displaymath)\*?)\}/.exec(text.slice(index));if(env){
    start=env[0];close='\\end{'+env[1]+'}';}}if(!start)return null;let end=text.indexOf(close,index+start.length);while(end>=0&&escaped(
    end))end=text.indexOf(close,end+close.length);return end<0?null:{end:end+close.length,text:text.slice(index,end+close.length)};};
  const codeAt=index=>{if(text[index]!=='`')return null;const run=/^`+/.exec(text.slice(index))[0];const end=text.indexOf(run,index+run.length);
    return end<0?null:{end:end+run.length,text:text.slice(index+run.length,end)};};
  const whitespace=char=>!char||/\s/u.test(char),punctuation=char=>!!char&&/[\p{P}\p{S}]/u.test(char),word=char=>!!char&&/[\p{L}\p{N}_]/u.test(char);
  const flank=(index,length)=>{const before=text[index-1]||'',after=text[index+length]||'';return {left:!whitespace(after)&&(!punctuation(after)||
    whitespace(before)||punctuation(before)),right:!whitespace(before)&&(!punctuation(before)||whitespace(after)||punctuation(after)),intraword:word(before)&&word(after)};};
  while(at<text.length){const math=mathAt(at);if(math){flush();parts.push({kind:'math',text:math.text});at=math.end;continue;}const code=codeAt(at);
    if(code){flush();parts.push({kind:'code',text:code.text});at=code.end;continue;}
    if(text[at]==='\\'&&at+1<text.length&&/[!"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~]/.test(text[at+1])){buffer+=text[at+1];at+=2;continue;}
    if(text[at]==='*'||text[at]==='_'){
      const delimiter=text[at],run=new RegExp('^'+(delimiter==='*'?'\\*':'_')+'+').exec(text.slice(at))[0],open=flank(at,run.length);
      // Intraword delimiters are literal in scientific notes: postfix stars and
      // identifiers such as π_*μ* must not become typographic emphasis.
      if(run.length<=2&&open.left&&!open.intraword){let end=at+run.length;while(end<text.length){const protectedPart=mathAt(end)||codeAt(end);if(
        protectedPart){end=protectedPart.end;continue;}if(text.startsWith(run,end)&&!escaped(end)&&text[end-1]!==delimiter&&text[
        end+run.length]!==delimiter){const close=flank(end,run.length);if(close.right&&!close.intraword){flush();parts.push({
        kind:run.length===2?'strong':'em',children:artifactInlineParts(text.slice(at+run.length,end))});at=end+run.length;break;}}end++;}if(end<text.length)continue;}
    }
    buffer+=text[at++];
  }
  flush();return parts;
}

// The same safe reading surface serves saved research notes and final replies.
export async function renderArtifactMarkdown(host,text,{project,onOpenArtifact,onInspectClaim=null,onInspectOwner=null,resultLinks=[],renderMath=scientificText}={}){
  host.replaceChildren();const pending=[];
  const inline=(parent,value)=>{
    const render=(target,parts,codeLinks=true)=>{for(const part of parts){if(part.kind==='text')target.append(document.createTextNode(part.text));
      else if(part.kind==='math')pending.push(renderMath(target,part.text));else if(part.kind==='code'){const literal=E('code',part.text),
      read=!/\s/.test(part.text)?artifactHumanTarget(part.text,{project}):null;const owner=codeLinks?ownerHumanTarget(part.text):null;if(owner&&
      onInspectOwner){const link=E('a');link.href=owner.href;link.append(literal);link.onclick=event=>{event.preventDefault();return onInspectOwner(
      owner,part.text);};target.append(link);}else if(codeLinks&&read?.artifactOwner==='writing-artifact'&&read.expectedSha256){const link=E('a');
      link.href=part.text;link.append(literal);link.onclick=event=>{event.preventDefault();onOpenArtifact?.(read.path,read.path,read);};target.append(
      link);}else target.append(literal);}else{const node=E(part.kind);target.append(node);render(node,part.children||[],codeLinks);}}};
    for(const part of messageLinkParts(value,{project,resultLinks})){if(part.text!=null)render(parent,artifactInlineParts(part.text));else{
      const link=E('a');render(link,artifactInlineParts(part.label),false);if(part.kind==='concept'){link.href=part.href;if(
      onInspectClaim)link.onclick=event=>{event.preventDefault();return onInspectClaim(part.conceptRead);};else if(onInspectOwner)link.onclick=event=>
      {event.preventDefault();return onInspectOwner(part.ownerRead,part.label);};}else if(part.kind==='owner-read'){link.href=part.href;if(
      onInspectOwner)link.onclick=event=>{event.preventDefault();return onInspectOwner(part.ownerRead,part.label);};}else if(
      part.kind==='human-artifact'){link.href=part.href;link.onclick=event=>{event.preventDefault();onOpenArtifact?.(part.humanRead.path,part.label,
      part.humanRead);};}else if(part.kind==='artifact'){link.href='/research/artifact?'+new URLSearchParams({project,path:part.target,
      scope:'project'});link.onclick=event=>{event.preventDefault();onOpenArtifact?.(part.target,part.label);};}else{link.href=part.target;
      link.target='_blank';link.rel='noopener noreferrer';}parent.append(link);}}
  };
  for(const block of artifactMarkdownBlocks(text)){
    if(block.kind==='code'){const pre=E('pre');pre.append(E('code',block.text));host.append(pre);}
    else if(block.kind==='table'){const scroll=E('div','','artifact-markdown-table'),table=E('table'),head=E('thead'),header=E('tr'),body=E('tbody');
      for(const [index,value] of block.header.entries()){const cell=E('th');cell.setAttribute('scope','col');if(block.align[
      index])cell.style.textAlign=block.align[index];inline(cell,value);header.append(cell);}head.append(header);for(const values of block.rows){
      const row=E('tr');for(const [index,value] of values.entries()){const cell=E('td');if(block.align[index])cell.style.textAlign=block.align[index];
      inline(cell,value);row.append(cell);}body.append(row);}table.append(head,body);scroll.append(table);host.append(scroll);}
    else if(block.kind==='list'){const list=E(block.ordered?'ol':'ul');for(const item of block.items){const li=E('li');list.append(li);inline(li,item);}host.append(list);}
    else{const node=E(block.kind==='heading'?'h'+Math.min(6,block.level+1):block.kind==='quote'?'blockquote':'p');host.append(node);inline(node,block.text);}
  }
  await Promise.all(pending);
}
export function mountInspection(project,{discussion,work,home}){
  function renderSavedMarkdown(host,text,{project:ownerProject=project,scope='project',resultLinks=[],onInspectClaim=null,onInspectOwner=null}={}){
    return renderArtifactMarkdown(host,text,{project:ownerProject,resultLinks,onInspectClaim,onInspectOwner:onInspectOwner||((read,label)=>
    discussion.session().guard(()=>inspectOwnerRead(read,label))),onOpenArtifact:(path,label,options)=>discussion.session().guard(()=>
    inspectProjectArtifact(path,label,{project:ownerProject,scope,...options}))});}
  // Every reading dialog is adopted by the one inspector AT ITS DOOR (writing-artifact,
  // writing-pdf, workspace-material); the shell only routes.
  async function inspectProjectArtifact(path,label,options={}){
    if(options.ownerRead)return inspectOwnerRead(options.ownerRead,label,options);
    const ownerProject=options.project||project;
    return openEvidenceArtifact({project:ownerProject,path,label,scope:options.scope||'project',
      notice:options.notice||'',expectedSha256:options.expectedSha256||null,artifactId:options.artifactId||null,artifactOwner:options.artifactOwner||
        null,opener:options.opener||null,isCurrent:options.isCurrent||(()=>true),request:api,renderMarkdown:renderSavedMarkdown});
  }
  async function inspectOwnerRead(read,label='Owner reading',options={}){
    const target=qualifiedOwnerHTTP(read,project)?.owner;
    if(target?.kind==='profile'){const observed=await api(target.http.url);return inspectProfilePreferences({project,family:observed.family,
      scope:observed.scope,profile:observed.family==='voice'&&observed.scope==='workspace'?observed.profile:null,
      initialCandidate:observed.candidate_ref?{project,custody_project:project,candidate_ref:observed.candidate_ref}:null,request:api,
      opener:options.opener,onGenerate:discussion.generateProfile,onChanged:async()=>{await work.reload();await home.refreshStyle();}});}
    return openEvidenceArtifact({ownerRead:read,label,request:api,renderMarkdown:renderSavedMarkdown,...options});
  }
  return {savedMarkdown:renderSavedMarkdown,projectArtifact:inspectProjectArtifact,ownerRead:inspectOwnerRead};
}
