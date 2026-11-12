// WALK PIECES (S2 F4). Purpose: the pure inline renderer: a block's owner-issued pieces (text,
// math, citations, references, links, lists) become DOM, with the piece map that inverts rendered
// offsets back to source pieces. Owns: no state. Public contract: renderPieces, renderPiecesMapped,
// refreshPieceMap/usableMap, renderListInto, renderTexInline, headText, cssEscape. Inputs: pieces and
// D's macros/citations/refs; it never edits source or selection. The exact NBSP tie is preserved.
import store from "/shared/store.mjs";
import {
  artifactHumanTarget, isKnownArtifactReadRoute, isKnownOwnerReadRoute, ownerHumanTarget
} from "/shared/writing-owner-read.mjs";
import {el, emit} from './walk-base.mjs';
import {D, blockById} from './walk-document.mjs';
import {S, jumpToBlock} from './walk-position.mjs';
import {appendEquation, mathNode} from './walk-media.mjs';
import {readCitation} from './walk-source-client.mjs';
import {asChrome} from './walk-blocks.mjs';
import {hostText, readableDOM} from './walk-selection.mjs';
import {islandSource} from './walk-edit-input.mjs';

/** A control sequence the payload left in plain text is MARKED, never silently shown as
 *  if it were prose. Honesty is the whole point of this canvas. */
function appendText(host, s) {
  const str = String(s == null ? "" : s);
  if (!str) return;
  const re = /\\[a-zA-Z@]+\*?/g;
  let last = 0, m;
  while ((m = re.exec(str))) {
    if (m.index > last) host.appendChild(document.createTextNode(str.slice(last, m.index)));
    host.appendChild(el("span", "unknown", m[0]));
    D.unknown += 1;
    last = re.lastIndex;
  }
  if (last < str.length) host.appendChild(document.createTextNode(str.slice(last)));
}

function citeNode(keys) {
  const wrap = el("span", "cite-wrap");
  const list = (Array.isArray(keys) ? keys : [keys]).filter(Boolean).map(String);
  wrap.appendChild(document.createTextNode("["));
  list.forEach((k, i) => {
    if (i) wrap.appendChild(document.createTextNode(", "));
    const rec = D.citations[k];
    const b = el("button", "cite", rec && rec.num != null ? String(rec.num) : "?");
    b.type = "button";
    b.dataset.key = k;
    if (!rec) b.dataset.unknown = "1";
    b.setAttribute("aria-label", "open the source of the citation " + k);
    b.title = (rec && rec.entry ? rec.entry + ' · ' : '') + 'Click to read the bibliography entry · Shift+click to edit this citation in TeX';
    b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      ev.preventDefault();
      if (ev.shiftKey || ev.altKey) islandSource(wrap, k);
      else readCitation(wrap, k);
    });
    b.addEventListener("keydown", (ev) => {
      if (ev.key === 'Enter' && ev.shiftKey) { ev.preventDefault(); ev.stopPropagation(); islandSource(wrap, k); }
    });
    wrap.appendChild(b);
  });
  if (!list.length) wrap.appendChild(el("span", "unknown", "?"));
  wrap.appendChild(document.createTextNode("]"));
  return wrap;
}

/** Attribute-selector safety without depending on CSS.escape being present. */
function cssEscape(s) {
  return String(s).replace(/["\\]/g, "\\$&");
}

function refNode(label, command='ref') {
  const key = String(label || "");
  const target=D.labelTargets?.get(key);
  const n = target ? D.refs[key] : undefined;
  const value=n != null ? String(n) : "??";
  const span = el("span", "ref", command==='eqref'?'('+value+')':value);
  if (n == null) { span.dataset.unknown = "1"; D.unknown += 1; }
  span.dataset.label = key;
  span.setAttribute('role','link');span.tabIndex=0;
  const follow=()=>{if(target)jumpToBlock(target.id);};
  span.addEventListener('dblclick',follow);
  span.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();follow();}});
  span.title=target?'Double-click to go to '+key:'Reference target not found: '+key;
  return span;
}

function manuscriptLink(p,host){
  const link=el('a','ref',p.s||p.url||'');const raw=String(p.url||'');
  if(Array.isArray(p.pieces)){link.textContent='';renderPieces(p.pieces,link);}
  const artifact=artifactHumanTarget(raw,{project:S.corpus,base:location.href||location.origin+'/'});
  const owner=ownerHumanTarget(raw);
  if(artifact){
    link.href=raw;
    link.addEventListener('click',async event=>{
      if(event.defaultPrevented||event.button!=null&&event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
      event.preventDefault();event.stopPropagation();link.focus({preventScroll:true});
      try{
        if(window.parent!==window)window.parent.postMessage({type:'laplace:open-project-artifact',url:raw,label:p.s||artifact.path},location.origin);
        else{const {openArtifact}=await import('/shared/writing-artifact.mjs');if(link.isConnected===false)return;await openArtifact({
          project:S.corpus,...artifact,label:p.s||artifact.path,opener:link,isCurrent:()=>link.isConnected!==false});}
      }catch(error){if(link.isConnected!==false)emit('editor-status',{text:error.message,error:true});}
    });
  }else if(owner){
    link.href=owner.href;
    link.addEventListener('click',async event=>{event.preventDefault();event.stopPropagation();try{
      if(window.parent!==window)window.parent.postMessage({type:'laplace:open-owner-read',url:owner.http.url,label:p.s||raw},location.origin);
      else{const {openArtifact}=await import('/shared/writing-artifact.mjs');if(link.isConnected===false)return;await openArtifact({
        project:owner.project,ownerRead:owner,label:p.s||raw});}
    }catch(error){if(link.isConnected!==false)emit('editor-status',{text:error.message,error:true});}});
  }else if(isKnownOwnerReadRoute(raw)||isKnownArtifactReadRoute(raw,{base:location.href||location.origin+'/'})){
    link.removeAttribute('href');link.title='Invalid owner reading coordinates; inspect the source link.';
  }else if(/^(https?:|mailto:)/i.test(raw)){link.href=raw;link.target='_blank';link.rel='noopener noreferrer';}
  else if(raw&&!/^[a-z][a-z\d+.-]*:/i.test(raw)&&!raw.startsWith('/')&&!raw.includes('\\')){
    link.href='#';link.addEventListener('click',async event=>{event.preventDefault();event.stopPropagation();try{
      const block=blockById.get(link.closest('.blk')?.dataset.block),source=block?.src?.repo_file||block?.src?.file;
      if(!source||!S.corpus)throw Error('This link has no current project source identity.');
      const result=await store.fetchJSON('/research/artifact',{params:{project:S.corpus,path:source,scope:'project',resolve:'source-link',uri:raw}});
      const resolved=new URL(result.url,location.href||location.origin+'/');if(result.project!==S.corpus||resolved.origin!==location.origin||
        resolved.pathname!=='/research/artifact')throw Error('The link did not resolve to this project’s artifact reader.');
      if(result.kind!=='download'&&window.parent!==window){window.parent.postMessage({type:'laplace:open-project-artifact',path:result.path,
        label:p.s||result.label,scope:result.scope,notice:result.notice||''},location.origin);}
      else if(result.kind!=='download'){const {openArtifact}=await import('/shared/writing-artifact.mjs');await openArtifact({project:S.corpus,
        path:result.path,label:p.s||result.label,scope:result.scope,notice:result.notice||''});}
      else{const target=el('a');target.href=result.url;if(result.kind==='download')target.download=result.label;else{target.target='_blank';
        target.rel='noopener noreferrer';}document.body.append(target);target.click();target.remove();}
    }catch(error){emit('editor-status',{text:error.message,error:true});}});
  }else{link.removeAttribute('href');link.title='Unsupported link target; inspect its source to edit it.';}
  host.appendChild(link);
}

/** One piece of a paragraph. Unknown piece types are rendered MARKED, never dropped. */
function renderPiece(p, host) {
  if (p == null) return;
  if (typeof p === "string") { appendText(host, p); return; }
  const t = String(p.t || p.type || "");
  const s = p.s != null ? String(p.s) : (p.text != null ? String(p.text) : "");
  const kids = Array.isArray(p.pieces) ? p.pieces : null;
  const into = (node) => {
    if (kids) renderPieces(kids, node); else appendText(node, s);
    host.appendChild(node);
  };
  switch (t) {
    case "presentation": return;
    case "group": if(kids)renderPieces(kids,host);return;
    case "text": case "": if(kids)renderPieces(kids,host);else appendText(host, s); return;
    case "emph": case "it": case "textit": into(el("em")); return;
    // `bold` is the type the door actually emits for `\textbf` (walk.py's `_BOLD_CMDS`
    // branch). It had no case here, so bold prose fell to the default and read back as
    // "the payload carried no expansion" — the honest-unknown mark, on text that was
    // understood perfectly.
    case "strong": case "bold": case "bf": case "textbf": into(el("strong")); return;
    case "code": case "tt": case "texttt": case "verb": {
      if(p.literal===true&&!kids){const code=el('code');code.appendChild(document.createTextNode(s));host.appendChild(code);}
      else into(el("code"));
      return;
    }
    case "sup": into(el("sup")); return;
    case "sub": into(el("sub")); return;
    case "provenance-label": { const label=el('sup','provenance-label structural-piece');
      label.title='Authored claim label; this is not a verification status.';label.setAttribute('contenteditable','false');into(label);return; }
    case "footnote": { const note=el('span','inline-footnote structural-piece');note.setAttribute('contenteditable','false');note.appendChild(el(
      'span','footnote-label',' (Note: '));if(kids)renderPieces(kids,note);else appendText(note,s);note.appendChild(document.createTextNode(') '));host.appendChild(note);return; }
    // display math inside a paragraph run (`$$…$$`, `\[…\]`) — the door sets `display`
    // and it was being dropped, so the formula rendered inline.
    case "math": case "inlinemath":
      if(p.display&&p.env){const equation=el('span','nested-equation structural-piece');appendEquation({...p,math:s||p.math},equation);host.appendChild(equation);}
      else host.appendChild(mathNode(s || p.math, !!p.display)); return;
    case "dmath": case "displaymath": host.appendChild(mathNode(s || p.math, true)); return;
    case "cite": host.appendChild(citeNode(p.keys || p.key || [])); return;
    case "ref": case "eqref": case "cref":
      host.appendChild(refNode(p.label || s,p.cmd||t)); return;
    case "url": case "href": {
      manuscriptLink(p,host);
      return;
    }
    case "break": case "newline": host.appendChild(el("br")); return;
    case "symbol": into(el('span','structural-piece')); return;
    case "parbox": {
      const box=el('span','parbox structural-piece');
      box.setAttribute('contenteditable','false');
      const geometry=p.geometry||{};
      for(const key of ['position','height','inner_position','width'])if(geometry[key])box.setAttribute('data-'+key.replaceAll('_','-'),String(geometry[key]));
      renderPieces(kids||[],box);host.appendChild(box);return;
    }
    case "placeholder": {
      const pending=el('span','evidence-gap structural-piece','[Unresolved: '+s+']');
      pending.title=p.reason||'This value is unresolved in the manuscript source.';
      pending.setAttribute('contenteditable','false');host.appendChild(pending);return;
    }
    case "list": {
      const list=el(p.env==='description'?'ul':p.ordered?'ol':'ul','lst structural-piece');
      if(p.env==='description')list.classList.add('description-list');
      list.setAttribute('contenteditable','false');host.appendChild(list);
      renderListInto(list,p.items,[],list,0);return;
    }
    case "semantic-label": {
      const label=el('strong','semantic-label structural-piece');
      label.setAttribute('contenteditable','false');renderPieces(kids||[],label);host.appendChild(label);return;
    }
    case "algorithm": {
      const algorithm=el('div','algorithm-block structural-piece');
      algorithm.setAttribute('contenteditable','false');renderPieces(kids||[],algorithm);host.appendChild(algorithm);return;
    }
    case "algorithm-keyword": {
      if(p.new_line)host.appendChild(el('br'));
      const word=el('strong','algorithm-keyword',s);host.appendChild(word);
      if(kids)renderPieces(kids,host);return;
    }
    // A macro the preamble defines is not an unknown. The door types every unrecognised
    // control sequence as `macro` and says whether the preamble knows it (`known`). A
    // known one had no case here and was marked red beside the genuinely unexpanded ones,
    // which is the opposite of what the mark means. Known and text-shaped: expand it.
    // Known but brace- or argument-shaped, or unknown: show it and mark it, never drop.
    case "macro": {
      const name = "\\" + String(p.name || "");
      const exp = D.macros && Object.prototype.hasOwnProperty.call(D.macros, name)
        ? String(D.macros[name]) : "";
      if (p.known && exp && !/[\\{}#]/.test(exp) && !(p.args && p.args.length)) {
        host.appendChild(document.createTextNode(exp));
        return;
      }
      const n = el("span", "unknown", s || name);
      n.title = p.known ? name + " is defined in the preamble, but its expansion is not "
                        + "plain text, so it is shown as source rather than guessed at"
                        : name + " is defined nowhere this door could read";
      D.unknown += 1;
      host.appendChild(n);
      return;
    }
    case "raw": case "unknown": {
      const n = el("span", "unknown", s);
      if(p.reason)n.title=String(p.reason);
      D.unknown += 1;
      host.appendChild(n);
      return;
    }
    default: {
      // a piece type this canvas does not know is SHOWN and MARKED — never dropped, and
      // never silently rendered as if it had been understood.
      const n = el("span", "unknown", s || ("[" + t + "]"));
      D.unknown += 1;
      host.appendChild(n);
    }
  }
}

function renderPieces(pieces, host) {
  for (const p of pieces) renderPiece(p, host);
}

/** RENDER, and record where each piece landed. The piecewise-exact locator needs both
 *  halves of the map: the source span the door emits (`o_start`/`o_end`) and the RENDERED
 *  span this canvas draws. Only the renderer knows the second — a citation draws `[12]`
 *  from the built bibliography and KaTeX draws whatever it draws — so it is measured here,
 *  against the BLOCK's host, as each piece goes in. `host` may be nested (a list item);
 *  the measurement is always against `blockHost`, so one flat map covers the whole block. */
function renderPiecesMapped(pieces, host, map, blockHost) {
  let cursor=map.at(-1)?.rEnd||0;
  for (const p of pieces) {
    const inlineTags={group:'span',emph:'em',it:'em',textit:'em',strong:'strong',bold:'strong',bf:'strong',textbf:'strong',code:'code',tt:'code',texttt:'code'};
    if(inlineTags[p?.t]&&Array.isArray(p.pieces)){
      const wrapper=el(inlineTags[p.t]);host.appendChild(wrapper);renderPiecesMapped(p.pieces,wrapper,map,blockHost);cursor=map.at(-1)?.rEnd||cursor;continue;
    }
    const first=host.childNodes.length;
    renderPiece(p, host);
    const nodes=Array.from(host.childNodes).slice(first);
    const rendered=nodes.map(node=>node.nodeType===3?node.nodeValue||'':hostText(node)).join('');
    map.push({ t: String((p && p.t) || "text"), rStart: cursor, rEnd: cursor+rendered.length,
               rText: rendered, nodes,
               oStart: Number(p && p.o_start), oEnd: Number(p && p.o_end) });
    cursor+=rendered.length;
  }
}

/** Rendering math changes its visible text length. Rebuild the inverse map from
 * stable piece hosts, in one walk, before any new edit/annotation can consume it. */
function refreshPieceMap(block) {
  const map=block.pieceMap,host=block.bodyEl;
  if(!map?.length||!host)return;
  const owners=new WeakMap();
  for(const entry of map){entry.rStart=null;entry.rEnd=null;entry.rText='';for(const node of entry.nodes||[])owners.set(node,entry);}
  for(const span of readableDOM(host).segments){
    const node=span.node;if(!node)continue;
    let current=node,entry;
    while(current&&current!==host){entry=owners.get(current);if(entry)break;current=current.parentNode;}
    const value=node.nodeValue||'';
    if(entry){if(entry.rStart===null)entry.rStart=span.start;entry.rEnd=span.end;entry.rText+=value;}
  }
  let previous=0;
  for(const entry of map){if(entry.rStart===null){entry.rStart=previous;entry.rEnd=previous;}previous=entry.rEnd;}
}

/** A map is usable only if EVERY entry carries real source offsets in order. A payload
 *  from a door that predates the piece offsets carries none, and half a map is worse than
 *  no map: the locator would place some boundaries exactly and guess at the rest. */
function usableMap(map) {
  if (!map.length) return false;
  let last = -1;
  for (const m of map) {
    if (!Number.isFinite(m.oStart) || !Number.isFinite(m.oEnd)) return false;
    if (m.oStart < last || m.oEnd < m.oStart) return false;
    last = m.oEnd;
  }
  return true;
}

/** itemize / enumerate / description as a REAL list (GAP-20260810-raw-block-fidelity).
 *  Items ride the same piece pipeline the prose does, so math, citations and cross-refs
 *  inside an item render and carry their source offsets; nesting stops at one level, which
 *  is what the door emits. Tables use the same piece renderer in their cells. */
function renderListInto(node, items, map, blockHost, depth) {
  for (const it of (Array.isArray(items) ? items : [])) {
    const li = el("li");
    node.appendChild(li);
    if (it && it.term) {
      const term = el("strong", it.bibliography ? "bibliography-label" : "lst-term");
      li.appendChild(term);
      if(it.bibliography){asChrome(term);term.contentEditable='false';li.dataset.citekey=it.key;term.append(document.createTextNode('['));if(
        it.term_pieces?.length)renderPieces(it.term_pieces,term);else appendText(term,it.term);term.append(document.createTextNode(']'));}
      else if (Array.isArray(it.term_pieces)) renderPiecesMapped(it.term_pieces, term, map, blockHost);
      else appendText(term, it.term);
      li.appendChild(document.createTextNode(" "));
    }
    renderPiecesMapped(Array.isArray(it && it.pieces) ? it.pieces : [], li, map, blockHost);
    if (it && it.sub && depth < 16) {
      const sub = el(it.sub.ordered ? "ol" : "ul", "lst");
      li.appendChild(sub);
      renderListInto(sub, it.sub.items, map, blockHost, depth + 1);
    }
    if (it && Array.isArray(it.tail_pieces)) {
      renderPiecesMapped(it.tail_pieces, li, map, blockHost);
    }
  }
}

/** `$…$` inside a tex string the payload gave no pieces for (captions, heads). */
function renderTexInline(s, host) {
  const src = String(s == null ? "" : s);
  const re = /\$([^$]+)\$/g;
  let last = 0, m;
  while ((m = re.exec(src))) {
    if (m.index > last) appendText(host, src.slice(last, m.index));
    host.appendChild(mathNode(m[1], false));
    last = re.lastIndex;
  }
  if (last < src.length) appendText(host, src.slice(last));
}

const HEAD_RE = /\\(?:sub)*(?:section|paragraph|chapter)\*?\s*\{([\s\S]*?)\}\s*$/;

function headText(b) {
  if (b.title) return b.title;
  if (b.text) return b.text;
  const m = HEAD_RE.exec(String(b.tex || "").trim());
  return m ? m[1] : String(b.tex || "");
}

export {
  cssEscape, headText, refreshPieceMap, renderListInto, renderPieces, renderPiecesMapped, renderTexInline,
  usableMap
};
