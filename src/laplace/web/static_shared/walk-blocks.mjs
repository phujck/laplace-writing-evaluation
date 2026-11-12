// WALK BLOCKS (S2 F4). Purpose: the live block renderers: one block body per kind (prose, lists,
// environments, theorems, equations, figures, raw) and the whole-canvas render that indexes blocks.
// Owns: no state of its own; renderDoc rebuilds S.blocks/blockById from D and releases the previous
// canvas's media first (releaseMediaForRender). Public contract: renderDoc, buildBlock,
// renderBlockBody, asChrome.
import {compiledEnvironmentPreviewRoute} from "/shared/manuscript-editing.mjs";
import {docEl, docNote, el} from './walk-base.mjs';
import {D, blockById} from './walk-document.mjs';
import {S} from './walk-position.mjs';
import {FIGS, appendEquation, drawFigure, releaseMediaForRender} from './walk-media.mjs';
import {
  headText, refreshPieceMap, renderListInto, renderPieces, renderPiecesMapped, renderTexInline, usableMap
} from './walk-pieces.mjs';
import {paintMarks} from './walk-composer.mjs';
import {srcOf} from './walk-selection.mjs';
import {showStructuralOutcome} from './walk-edit-history.mjs';
import {flipBlock} from './walk-flip.mjs';
import {sealIslands, setEditable} from './walk-editing.mjs';
import {ATOMIC_KINDS} from './walk-paragraph-ops.mjs';

/** Mark a node the CANVAS minted about a block — a badge, a note. It is drawn, it is
 *  read, and it is never part of the block's text (see `textWalker`). */
function asChrome(node) {          // not `chrome`: that name is a browser global
  node.dataset.chrome = "1";node.contentEditable="false";
  return node;
}

/** Every path that (re)builds a block's body ends here: the islands are sealed atomic and
 *  the host's editability is derived — ONE place, so a re-render can never leave a block
 *  typable that should not be, or inert when it has an exact splice to offer. */
function renderBlockBody(b, host) {
  renderBlockBodyCore(b,host);
  refreshPieceMap(b);
}

function renderBlockBodyCore(b, host) {
  renderBlockBodyInner(b, host);
  sealIslands(host);
  setEditable(b, host);
}

function renderBlockBodyInner(b, host) {
  host.textContent = "";
  b.pieceMap = null;                 // rebuilt below wherever pieces actually render
  const kind = b.kind || "para";
  // TEX FACE: does this block's rendered face show its source? A `raw` block does by
  // construction, and any block whose math fell back to unrendered tex does in fact. The
  // flag is what keeps raw LaTeX out of the right rail — see `arm`.
  b.texFace = kind === "raw";
  if(b.presentation_only){b.texFace=true;const source=asChrome(el('button','presentation-source','Page presentation settings'));source.type='button';
    source.setAttribute('aria-label','Edit page presentation settings');source.onclick=()=>flipBlock(b);host.appendChild(source);return;}
  if (kind === "equation") {
    const m = appendEquation(b,host);
    if (m.classList.contains("unknown")) b.texFace = true;
    return;
  }
  if (kind === "figure") {
    const fig = el("div", "fig");
    host.appendChild(fig);
    if(b.preview_image)drawFigure(fig,b.preview_image);
    else if(b.images?.length){
      for(const [index,image]of b.images.entries()){
        const panel=el('div','figure-panel');panel.setAttribute('role','group');panel.setAttribute('aria-label','Figure panel '+(
          index+1)+' of '+b.images.length);fig.appendChild(panel);
        if(image.route)drawFigure(panel,image.route,image);else panel.appendChild(asChrome(el('p','fig-note','The declared image is unavailable: '+(
          image.arg||image.file||'unnamed image'))));
      }
    }
    else if (b.image) drawFigure(fig, b.image);
    else fig.appendChild(asChrome(el("div", "fig-note",
      "Figure preview unavailable. Open its exact source or view the compiled PDF.")));
    if (!b.caption_separate && (b.caption_pieces || b.caption)) {
      const cap = el("div", "cap");
      if (b.caption_pieces) renderPieces(b.caption_pieces, cap);
      else renderTexInline(b.caption, cap);
      host.appendChild(cap);
    }
    return;
  }
  if (kind === "list") {
    const ordered = !!b.ordered || String(b.env || "") === "enumerate";
    const bibliography=b.env==='thebibliography';
    if(bibliography)host.appendChild(asChrome(el('h3','bibliography-title',b.title||'References')));
    const listEl = el(ordered ? "ol" : "ul", bibliography ? "lst bibliography" : "lst");
    host.appendChild(listEl);
    const map = [];
    renderListInto(listEl, b.items, map, host, 0);
    if (!listEl.childNodes.length && bibliography) {listEl.remove();host.appendChild(asChrome(el('p','bibliography-empty','No bibliography entries yet.')));return;}
    if (!listEl.childNodes.length) {
      // the door typed it as a list and the payload carried no items: say so rather than
      // print an empty list where the source has content.
      listEl.remove();
      host.appendChild(asChrome(el("span", "raw-badge",
        "list source — the payload carried no items for this " + (b.env || "list"))));
      host.appendChild(el("pre", "raw", b.tex || ""));
      b.texFace = true;
      return;
    }
    b.pieceMap = usableMap(map) ? map : null;
    return;
  }
  if (kind === "theorem" || kind === "custom") {
    if(kind==='custom'&&b.custom_kind==='compiled'&&b.preview_image){const preview=el('div','custom-environment-preview');host.appendChild(preview);
      drawFigure(preview,compiledEnvironmentPreviewRoute(b.preview_image),{scaleToText:true,label:b.title||b.env});b.texFace=true;return;}
    const box = el("div", kind === "custom" ? "custom-environment" : "theorem");
    if(kind === "custom")box.dataset.environment=b.env;
    if(kind==='custom'){const colors=b.presentation||{};if(colors.colframe)box.style.borderColor=colors.colframe;if(colors.colback){
      box.style.background=colors.colback;box.style.color='var(--green-10)';}}
    host.appendChild(box);
    const heading=el("strong", "theorem-name");box.appendChild(heading);
    if(kind==='custom'&&b.presentation?.colbacktitle)heading.style.background=b.presentation.colbacktitle;
    const map = [];
    if(kind==='theorem'&&b.theorem_label){
      const label=asChrome(el('span',null,b.theorem_label+(b.number?' '+b.number:'')));label.setAttribute('contenteditable','false');heading.appendChild(label);
      if(b.theorem_optional_title){const open=asChrome(el('span',null,' (')),close=asChrome(el('span',null,')'));open.setAttribute('contenteditable',
        'false');close.setAttribute('contenteditable','false');heading.appendChild(open);if(b.title_pieces?.length)renderPiecesMapped(b.title_pieces,
        heading,map,host);else heading.appendChild(asChrome(el('span',null,b.title||'')));heading.appendChild(close);}
    }else{
    if(b.title_prefix){const prefix=asChrome(el('span',null,b.title_prefix));prefix.setAttribute('contenteditable','false');heading.appendChild(prefix);}
    if(b.title_pieces?.length)renderPiecesMapped(b.title_pieces,heading,map,host);
    else {heading.textContent=b.title||b.env||'Statement';asChrome(heading);}
    if(kind==='theorem'&&b.number&&!new RegExp('(^|\\s)'+String(b.number).replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'($|[\\s.:])').test(b.title||'')){
      const number=asChrome(el('span','theorem-number',' '+b.number));number.contentEditable='false';heading.appendChild(number);}
    if(b.title_suffix){const suffix=asChrome(el('span',null,b.title_suffix));suffix.setAttribute('contenteditable','false');heading.appendChild(suffix);}
    }
    const body=el('div','environment-body');box.appendChild(body);
    if (Array.isArray(b.pieces)) renderPiecesMapped(b.pieces, body, map, host);
    else renderTexInline(b.tex || "", box);
    if(kind==='custom'&&b.preview_image){const detail=asChrome(el('details','custom-typeset'));detail.setAttribute('contenteditable','false');
      detail.appendChild(el('summary',null,'Typeset appearance'));const preview=el('div','custom-environment-preview');detail.appendChild(preview);
      detail.addEventListener('toggle',()=>{if(detail.open&&!preview.childNodes.length)drawFigure(preview,compiledEnvironmentPreviewRoute(
      b.preview_image),{scaleToText:true,label:b.title||b.env});});box.appendChild(detail);}
    b.pieceMap = usableMap(map) ? map : null; return;
  }
  if (kind === "table") {
    const table = el("table", "tex-table");
    const map = [];
    for (const rowSpec of (Array.isArray(b.rows) ? b.rows : [])) {
      const row = Array.isArray(rowSpec) ? rowSpec : (Array.isArray(rowSpec?.cells) ? rowSpec.cells : []);
      const tr = el("tr"); table.appendChild(tr);
      for (const cellSpec of row) {
        const td = el(!Array.isArray(rowSpec) && rowSpec.header ? "th" : "td");
        if (cellSpec && typeof cellSpec === "object") {
          if (Number(cellSpec.colspan) > 1) td.colSpan = Number(cellSpec.colspan);
          if (Array.isArray(cellSpec.pieces)) renderPiecesMapped(cellSpec.pieces, td, map, host);
          else renderTexInline(cellSpec.tex || "", td);
        } else renderTexInline(cellSpec, td);
        tr.appendChild(td);
      }
    }
    if (!table.rows.length) { host.appendChild(el("pre", "raw", b.tex || "")); b.texFace = true; return; }
    host.appendChild(table);
    if (b.caption_pieces || b.caption) {
      const cap = el("div", "cap");
      if (b.caption_pieces) renderPiecesMapped(b.caption_pieces, cap, map, host);
      else renderTexInline(b.caption, cap);
      host.appendChild(cap);
    }
    b.pieceMap = usableMap(map) ? map : null;
    return;
  }
  if (kind === "raw") {
    const detail = el("details", "source-preview");
    detail.appendChild(asChrome(el("summary", "raw-badge",
      (b.env || "This block") + " · source preview")));
    detail.appendChild(el("pre", "raw", b.tex || ""));
    host.appendChild(detail);
    return;
  }
  if (kind === "head") { if(b.title_pieces?.length)renderPieces(b.title_pieces,host);else renderTexInline(headText(b), host);if(
    b.tail_pieces?.length){const tail=el('span','heading-tail');renderPieces(b.tail_pieces,tail);host.appendChild(tail);}return; }
  if (Array.isArray(b.pieces)) {
    const map = [];
    renderPiecesMapped(b.pieces, host, map, host);
    b.pieceMap = usableMap(map) ? map : null;
  } else renderTexInline(b.text || b.tex || "", host);
  // a formula the vendored KaTeX could not render shows its tex: the block's face IS
  // source at that point, and the composer must not offer it as prose to type over.
  if (host.querySelector(".mathq.unknown")) b.texFace = true;
}

function buildBlock(b) {
  const art = el("article", "blk");
  art.dataset.kind = b.kind || "para";
  if(b.presentation_only)art.dataset.presentationOnly='true';
  if(b.level) art.dataset.level = b.level;
  if(b.kind==='head'){art.setAttribute('role','heading');art.setAttribute('aria-level',String(({part:1,chapter:1,section:2,subsection:3,
    subsubsection:4,paragraph:5})[b.level]||2));}
  art.dataset.block = b.id;
  art.tabIndex = -1;
  const body = el("div", "blk-body");
  art.appendChild(body);
  b.el = art; b.bodyEl = body;
  renderBlockBody(b, body);
  if(!b.suggestion&&ATOMIC_KINDS.has(b.kind)&&srcOf(b).file){const handle=asChrome(el('button','manuscript-object-handle','⋮⋮'));handle.type='button';
    handle.draggable=true;handle.dataset.objectHandle='';const objectName=b.env==='thebibliography'?'bibliography':b.kind;handle.setAttribute(
    'aria-label','Select or drag '+objectName);handle.title='Select or drag '+objectName;art.append(handle);art.dataset.atomicObject=b.kind;}
  return art;
}

/** The whole canvas, in document order. Sections in order, blocks in order, nothing
 *  reordered and nothing hidden. */
function sectionReadingHead(sec,wrap,headEl){
  if(headEl)return headEl;
  if(sec.id==='front'){wrap.setAttribute('aria-label',sec.title||'Front matter');return sec.blocks.find(block=>!block.presentation_only)?.el||wrap;}
  const heading=el('div','doc-head',sec.title);wrap.insertBefore(heading,wrap.firstChild);return heading;
}

function renderDoc() {
  releaseMediaForRender();
  docEl.textContent = "";
  blockById.clear();
  S.blocks = [];
  FIGS.length = 0;
  D.unknown = 0;

  D.sections.forEach((sec, si) => {
    const wrap = el("section", "sec-block");
    wrap.dataset.section = sec.id;
    let headEl = null;
    sec.blocks.forEach((b, bi) => {
      const node = buildBlock(b);
      wrap.appendChild(node);
      blockById.set(b.id, b);
      S.blocks.push(b);
      if (!headEl && bi === 0 && b.kind === "head") headEl = node;
    });
    headEl=sectionReadingHead(sec,wrap,headEl);
    sec.headEl = headEl;
    sec.wrapEl = wrap;
    docEl.appendChild(wrap);
  });

  docNote.hidden = true;
  paintMarks();
  if (D.pending_restructures?.length) showStructuralOutcome(D.pending_restructures[0]);
}

export {asChrome, buildBlock, renderBlockBody, renderDoc};
