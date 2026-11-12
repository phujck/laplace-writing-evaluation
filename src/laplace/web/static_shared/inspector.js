/* ═══════════════════════════════════════════════════════════════════════
   inspector.js — the ONE node inspector, shared across the applets.

   The node is the atomic unit; wherever one renders (a conceptric node
   card, projection-viewer node cards) it renders STRUCTURED, through this
   module: kind badge + canonical TERM as the title (id secondary), the
   essence (in-place editable → POST /corpus/rewire edit-essence), edges
   in/out as clickable chips, the emit-time slots (latex_label, retired +
   reason, provenance), and an ancestry breadcrumb back to the nearest
   spine beat.

   Self-contained: no CDN, no framework. Styles live in hymn.css (.hy-*).
   Every applet still works if this file never loads — pages keep a legacy
   fallback and only delegate when window.HymnInspector exists.

   Served by src/laplace/web/shared_ui.py at GET /shared/inspector.js.
   ═══════════════════════════════════════════════════════════════════════ */
(function(){
  "use strict";
  if(window.HymnInspector) return;

  const esc = s => String(s == null ? "" : s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  const ec = encodeURIComponent;
  async function jget(u){ const r = await fetch(u); return r.json(); }
  async function jpost(u, body){
    const r = await fetch(u, {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(body)});
    return r.json();
  }

  const SHORT_KIND = {"derivation-step":"step","intermediate-result":"ires","definition":"def",
    "postulate":"pos","result":"res","theorem":"thm","lemma":"lem","support":"sup",
    "technique":"tech","figure":"fig","citation":"ref"};
  function shortKind(k){ return SHORT_KIND[k] || (k||"").slice(0,4) || "?"; }

  // canonical TERM: projection.term when the projector coined one, else a readable
  // fallback derived from the id (strip the kind prefix, hyphens → spaces).
  function termOf(content){
    const p = content && content.projection;
    if(p && p.term) return p.term;
    const id = (content && content.id) || "";
    const tail = id.includes(":") ? id.slice(id.indexOf(":")+1) : id;
    return tail.replace(/[-_]/g, " ") || id || "?";
  }

  // ── data ────────────────────────────────────────────────────────────────
  // One node's inspector model = /corpus/content + /corpus/neighborhood
  // (both view-path endpoints: cached nets, never embedding).
  async function load(corpus, id, pre){
    pre = pre || {};
    const [content, nb] = await Promise.all([
      pre.content ? Promise.resolve(pre.content)
                  : jget("/corpus/content?corpus="+ec(corpus)+"&id="+ec(id)),
      pre.nb ? Promise.resolve(pre.nb)
             : jget("/corpus/neighborhood?corpus="+ec(corpus)+"&id="+ec(id)),
    ]);
    return {corpus: corpus, id: id, content: content, nb: nb};
  }

  // projection plan (section map), fetched once per corpus via /shared/plan.
  // null when the corpus has no plan — every consumer degrades gracefully.
  const PLAN_CACHE = {};
  async function getPlan(corpus){
    if(corpus in PLAN_CACHE) return PLAN_CACHE[corpus];
    let plan = null;
    try{
      const r = await fetch("/shared/plan?corpus="+ec(corpus));
      if(r.ok) plan = await r.json();
    }catch(e){ /* plan is optional */ }
    PLAN_CACHE[corpus] = plan;
    return plan;
  }

  // ── ancestry: BFS up the derives-from graph to the nearest spine beat ──
  const NB_CACHE = {};       // corpus::id -> neighborhood
  const PATH_CACHE = {};     // corpus::id -> path array | null
  async function nbFor(corpus, id){
    const key = corpus+"::"+id;
    if(!NB_CACHE[key])
      NB_CACHE[key] = await jget("/corpus/neighborhood?corpus="+ec(corpus)+"&id="+ec(id));
    return NB_CACHE[key];
  }
  // Returns [beatId, ..., id] (nearest spine ancestor first) or null. Bounded:
  // depth ≤ 4, ≤ 14 neighborhood fetches — the breadcrumb is a hint, not a proof.
  async function spinePath(corpus, id, spineIds){
    const key = corpus+"::"+id;
    if(key in PATH_CACHE) return PATH_CACHE[key];
    if(spineIds.has(id)){ PATH_CACHE[key] = [id]; return [id]; }
    let frontier = [[id]];
    const seen = new Set([id]);
    let budget = 14;
    for(let depth = 0; depth < 4 && frontier.length; depth++){
      const next = [];
      for(const path of frontier){
        if(budget-- <= 0){ PATH_CACHE[key] = null; return null; }
        let nb;
        try{ nb = await nbFor(corpus, path[path.length-1]); }
        catch(e){ continue; }
        for(const up of (nb && nb.above) || []){
          if(seen.has(up.id)) continue;
          seen.add(up.id);
          const p2 = [...path, up.id];
          if(spineIds.has(up.id)){ const out = p2.reverse(); PATH_CACHE[key] = out; return out; }
          next.push(p2);
        }
      }
      frontier = next;
    }
    PATH_CACHE[key] = null;
    return null;
  }

  // ── cross-links (open in conceptric / show in projection) ─────────────
  async function crossLinks(corpus, id, opts){
    opts = opts || {};
    const links = [];
    if(!opts.hideConceptric)
      links.push({label: "open in conceptric ↗",
                  href: "/conceptric?corpus="+ec(corpus)+"&node="+ec(id)});
    const plan = await getPlan(corpus);
    if(plan && plan.target_dir){
      const hit = (plan.node_index || {})[id];
      const file = plan.target_dir.replace(/\/+$/,"") + "/main.tex";
      let href = "/projection?file="+ec(file)+"&corpus="+ec(corpus);
      let label = "show in projection ↗";
      if(hit){ href += "&sec="+ec(hit.section); label = "show in projection · "+hit.section+" ↗"; }
      if(!opts.hideProjection) links.push({label: label, href: href, title: hit ? hit.title : ""});
    }
    return links;
  }

  // ── render ──────────────────────────────────────────────────────────────
  function edgeChip(d, m, removable){
    const prov = d.prov ? "<span class='eprov "+esc(d.prov)+"'>"+esc(d.prov)+"</span>" : "";
    const x = removable
      ? "<button class='ex' data-x='"+esc(d.id)+"' title='remove edge'>×</button>" : "";
    return "<span class='hy-echip' data-go='"+esc(d.id)+"' title='"+esc(d.essence||d.id)+"'>"+
      "<span class='eid'>"+esc(d.id)+"</span>"+prov+x+"</span>";
  }

  function slotRows(content){
    const p = content.projection || {};
    const rows = [];
    if(content.grade != null) rows.push(["grade", "g"+content.grade, ""]);
    if(p.latex_label) rows.push(["latex_label", p.latex_label, ""]);
    if(p.section_ref) rows.push(["section_ref", p.section_ref, ""]);
    if(p.data_source) rows.push(["data_source", p.data_source, ""]);
    if(p.provenance)  rows.push(["provenance", p.provenance, ""]);
    const retired = content.retired || p.retired;
    if(retired) rows.push(["retired", "yes" + (p.reason ? " — "+p.reason : ""), "retired"]);
    return rows;
  }

  // m: {corpus, id, content, nb, spine, renderEssence(content)->html, onFocus(id),
  //     edit:{enabled,onRemoveOut(id),onAddOut(),onAddIn()}, compact, hideLinks:{...},
  //     roles:[{label,cls}], extraHTML, onSaved()}
  function render(host, m){
    const c = m.content || {};
    const nb = m.nb || {};
    const above = nb.above || [], below = nb.below || [];
    const edit = m.edit && m.edit.enabled;
    const retired = c.retired || (c.projection || {}).retired;

    const roles = (m.roles || []).map(r =>
      "<span class='hy-role "+esc(r.cls)+"'>"+esc(r.label)+"</span>");
    if(c.spine && !((m.roles||[]).some(r => r.cls === "spine")))
      roles.push("<span class='hy-role spine'>spine #"+esc(c.spine.ord)+"</span>");
    if(c.postulate && !((m.roles||[]).some(r => r.cls === "post")))
      roles.push("<span class='hy-role post'>postulate</span>");
    if(retired) roles.push("<span class='hy-role retired'>retired</span>");
    roles.push("<span class='hy-role grade'>g"+(c.grade != null ? c.grade : "?")+"</span>");

    const essHTML = m.renderEssence ? m.renderEssence(c)
      : esc(c.essence || "(no essence)");

    const slots = slotRows(c);

    const html = [
      "<div class='hy-ins"+(m.compact ? " compact" : "")+"'>",
      " <div class='hy-ins-head'>",
      "  <div class='hy-titlerow'>",
      "   <span class='hy-kbadge "+esc(c.kind||"")+"'>"+esc(shortKind(c.kind))+"</span>",
      "   <span class='hy-term'>"+esc(termOf(c))+"</span>",
      "  </div>",
      "  <div class='hy-roles'>"+roles.join("")+"</div>",
      "  <div class='hy-nid'>"+esc(m.id)+"</div>",
      " </div>",
      // essence — the in-place editable atom
      " <div class='hy-sec'>",
      "  <div class='hy-sec-h'>essence"+
           "<span class='hy-act' data-essedit='1'>edit</span></div>",
      "  <div class='hy-ess-body'>"+essHTML+"</div>",
      "  <div class='hy-ess-editor'>",
      "   <textarea>"+esc(c.essence || "")+"</textarea>",
      "   <div class='hy-ess-btns'>",
      "    <button class='pri' data-esssave='1'>save</button>",
      "    <button data-esscancel='1'>cancel</button>",
      "    <span class='hy-ess-msg'></span>",
      "   </div>",
      "  </div>",
      " </div>",
      // edges in (used by · consumers)
      " <div class='hy-sec'>",
      "  <div class='hy-sec-h'>used by · "+above.length+
           (edit && m.edit.onAddIn ? "<span class='hy-act' data-addin='1'>+ add</span>" : "")+"</div>",
      "  <div class='hy-edges'>"+
           (above.length ? above.map(d => edgeChip(d, m, false)).join("")
                         : "<span class='hy-none'>none — nothing derives from this yet</span>")+
      "  </div>",
      " </div>",
      // edges out (depends on · derives from)
      " <div class='hy-sec'>",
      "  <div class='hy-sec-h'>depends on · "+below.length+
           (edit && m.edit.onAddOut ? "<span class='hy-act' data-addout='1'>+ add</span>" : "")+"</div>",
      "  <div class='hy-edges'>"+
           (below.length ? below.map(d => edgeChip(d, m, edit && !!m.edit.onRemoveOut)).join("")
                         : "<span class='hy-none'>none — a floor node (postulate or gap)</span>")+
      "  </div>",
      " </div>",
      // slots
      (slots.length ?
      " <div class='hy-sec'><div class='hy-sec-h'>slots</div><div class='hy-slots'>"+
        slots.map(([k,v,cls]) =>
          "<span class='sk'>"+esc(k)+"</span><span class='sv "+cls+"'>"+esc(v)+"</span>").join("")+
      " </div></div>" : ""),
      // comments — review signal ON the node without touching its essence
      // (his ask, 2026-07-08). Same ledger as the projection viewer's review
      // mode (<target_dir>/feedback/feedback.jsonl), listed + banked here.
      " <div class='hy-sec hy-fb-sec'>",
      "  <div class='hy-sec-h'>comments <span class='hy-fb-n'></span>"+
           "<span class='hy-act' data-fbadd='1'>+ comment</span></div>",
      "  <div class='hy-fb-list'><span class='hy-none'>loading…</span></div>",
      "  <div class='hy-fb-editor' style='display:none'>",
      "   <select class='hy-fb-kind'><option>note</option><option>off-voice</option>"+
           "<option>imprecise</option><option>missing-derivation</option><option>refute</option></select>",
      "   <textarea placeholder='the comment — banked verbatim, never edits the essence'></textarea>",
      "   <div class='hy-ess-btns'>",
      "    <button class='pri' data-fbsave='1'>bank</button>",
      "    <button data-fbcancel='1'>cancel</button>",
      "    <span class='hy-fb-msg hy-ess-msg'></span>",
      "   </div>",
      "  </div>",
      " </div>",
      // ancestry breadcrumb (filled async)
      " <div class='hy-sec'><div class='hy-sec-h'>ancestry · nearest spine beat</div>",
      "  <div class='hy-anc'><span class='hy-none'>tracing…</span></div>",
      " </div>",
      // cross-links (filled async)
      " <div class='hy-sec hy-links-sec' style='display:none'>",
      "  <div class='hy-sec-h'>open elsewhere</div><div class='hy-links'></div>",
      " </div>",
      m.extraHTML || "",
      "</div>",
    ].join("\n");
    host.innerHTML = html;
    if(window.renderMath) window.renderMath(host);   // KaTeX over essences/edges (shared, lazy)

    const $ = sel => host.querySelector(sel);
    const focus = id => { if(m.onFocus) m.onFocus(id); else mount(host, {...m, id: id, content: null, nb: null}); };

    // edge chips → focus that node
    host.querySelectorAll(".hy-echip[data-go]").forEach(el => {
      el.addEventListener("click", e => {
        if(e.target.dataset && e.target.dataset.x) return;   // the × button
        focus(el.dataset.go);
      });
    });
    host.querySelectorAll(".ex[data-x]").forEach(el =>
      el.addEventListener("click", e => { e.stopPropagation(); m.edit.onRemoveOut(el.dataset.x); }));
    const addIn = $("[data-addin]");  if(addIn)  addIn.onclick  = () => m.edit.onAddIn();
    const addOut = $("[data-addout]"); if(addOut) addOut.onclick = () => m.edit.onAddOut();

    // comments — list + bank against the node, never the essence
    (async () => {
      const list = $(".hy-fb-list"), nEl = $(".hy-fb-n");
      if(!list) return;
      const fill = async () => {
        try{
          const d = await jget("/corpus/feedback?corpus="+encodeURIComponent(m.corpus)+
                               "&node="+encodeURIComponent(m.id));
          const recs = (d && d.records) || [];
          nEl.textContent = recs.length ? "· "+recs.length : "";
          list.innerHTML = recs.length ? recs.map(r =>
            "<div class='hy-fb-row"+(r.status!=="open"?" resolved":"")+"'>"+
            "<span class='hy-fb-kind-tag'>"+esc(r.kind||"note")+"</span> "+
            esc(r.comment||"")+
            "<div class='hy-fb-meta'>"+esc(r.by||"")+" · "+esc((r.ts||"").slice(0,16))+
            (r.status!=="open"?" · "+esc(r.status):"")+"</div></div>").join("")
            : "<span class='hy-none'>none — the node has no review signal yet</span>";
          if(window.renderMath) window.renderMath(list);
        }catch(e){ list.innerHTML = "<span class='hy-none'>comments unavailable</span>"; }
      };
      await fill();
      const box = $(".hy-fb-editor"), ta = box.querySelector("textarea"),
            msg = $(".hy-fb-msg"), addBtn = $("[data-fbadd]");
      addBtn.onclick = () => {
        box.style.display = box.style.display === "none" ? "" : "none";
        if(box.style.display === "") ta.focus();
      };
      $("[data-fbcancel]").onclick = () => { box.style.display = "none"; };
      $("[data-fbsave]").onclick = async () => {
        const v = ta.value.trim();
        if(!v){ msg.textContent = "empty comment"; msg.className = "hy-fb-msg hy-ess-msg bad"; return; }
        msg.textContent = "banking…"; msg.className = "hy-fb-msg hy-ess-msg";
        const out = await jpost("/corpus/feedback", {corpus: m.corpus, node_id: m.id,
          kind: box.querySelector(".hy-fb-kind").value, comment: v, by: "author"});
        if(out && out.error){ msg.textContent = out.error; msg.className = "hy-fb-msg hy-ess-msg bad"; return; }
        ta.value = ""; msg.textContent = ""; box.style.display = "none";
        await fill();
      };
    })();

    // essence editing → POST /corpus/rewire {kind:'edit-essence'} then refresh
    const edBtn = $("[data-essedit]"), edBox = $(".hy-ess-editor"),
          edTa = edBox.querySelector("textarea"), edMsg = edBox.querySelector(".hy-ess-msg");
    edBtn.onclick = () => {
      edBox.classList.toggle("on");
      if(edBox.classList.contains("on")){ edTa.value = c.essence || ""; edTa.focus(); }
    };
    $("[data-esscancel]").onclick = () => edBox.classList.remove("on");
    $("[data-esssave]").onclick = async () => {
      const v = edTa.value;
      if(v === (c.essence || "")){ edBox.classList.remove("on"); return; }
      edMsg.textContent = "saving…"; edMsg.className = "hy-ess-msg";
      const out = await jpost("/corpus/rewire",
        {corpus: m.corpus, kind: "edit-essence", node: m.id, value: v, by: "author"});
      if(out && out.error){ edMsg.textContent = out.error; edMsg.className = "hy-ess-msg bad"; return; }
      NB_CACHE[m.corpus+"::"+m.id] = null; delete NB_CACHE[m.corpus+"::"+m.id];
      if(m.onSaved) m.onSaved(v);
      else mount(host, {...m, content: null, nb: null});
    };

    // ancestry — async, bounded, cached
    const spineIds = new Set((m.spine || []).map(s => s.id));
    const ancHost = $(".hy-anc");
    if(!spineIds.size){
      ancHost.innerHTML = "<span class='hy-none'>no spine on this corpus yet</span>";
    } else {
      spinePath(m.corpus, m.id, spineIds).then(path => {
        if(!ancHost.isConnected) return;
        if(!path){
          ancHost.innerHTML = "<span class='hy-none'>no spine ancestor within 4 hops</span>";
          return;
        }
        const beat = (m.spine || []).find(s => s.id === path[0]);
        const beatLab = beat ? "beat #"+beat.ord+(beat.term ? " · "+beat.term : "") : path[0];
        ancHost.innerHTML = path.map((nid, i) => {
          const lab = i === 0 ? beatLab : nid;
          const cls = i === 0 ? "hop beat" : "hop";
          const self = nid === m.id ? " style='cursor:default;opacity:.75'" : "";
          return "<span class='"+cls+"' data-go='"+esc(nid)+"' title='"+esc(nid)+"'"+self+">"+
                 esc(lab)+"</span>";
        }).join("<span class='sep'>›</span>");
        ancHost.querySelectorAll(".hop[data-go]").forEach(el =>
          el.addEventListener("click", () => { if(el.dataset.go !== m.id) focus(el.dataset.go); }));
      });
    }

    // cross-links — async (needs the plan)
    crossLinks(m.corpus, m.id, m.hideLinks || {}).then(links => {
      const sec = host.querySelector(".hy-links-sec");
      if(!sec || !sec.isConnected || !links.length) return;
      sec.style.display = "";
      sec.querySelector(".hy-links").innerHTML = links.map(l =>
        "<a href='"+esc(l.href)+"' title='"+esc(l.title||"")+"'>"+esc(l.label)+"</a>").join("");
    });
  }

  // mount = load + render into host. The one entry point most callers need.
  async function mount(host, m){
    if(!m.content || !m.nb){
      host.innerHTML = "<div class='hy-ins"+(m.compact ? " compact" : "")+"'>"+
        "<div class='hy-sec'><span class='hy-none'>loading "+esc(m.id)+"…</span></div></div>";
      try{
        const got = await load(m.corpus, m.id, {content: m.content, nb: m.nb});
        m = {...m, content: got.content, nb: got.nb};
      }catch(e){
        host.innerHTML = "<div class='hy-ins compact'><div class='hy-sec'>"+
          "<span class='hy-none'>failed to load "+esc(m.id)+" — "+esc(e.message)+"</span></div></div>";
        return;
      }
    }
    if(m.content && m.content.error){
      host.innerHTML = "<div class='hy-ins compact'><div class='hy-sec'>"+
        "<span class='hy-none'>"+esc(m.content.error)+"</span></div></div>";
      return;
    }
    render(host, m);
  }

  window.HymnInspector = {load, mount, render, termOf, getPlan, crossLinks, spinePath};
})();
