/* ═══════════════════════════════════════════════════════════════════════
   shell.js — the ONE shell over all six applets.

   Injects a slim persistent header: engine mark · VIEW switcher
   (map · conceptric · manuscript · projection · navigator) · corpus
   selector · node search. The corpus rides ?corpus= across every view
   switch, so hopping applets never loses context.

   Self-contained (no CDN). Graceful no-op: each applet includes this via
   <script defer src="/shared/shell.js"> — if /shared/ is absent the tag
   404s and the applet renders exactly as before. All fetches inside
   degrade silently too.

   Page hook: an applet may set window.__hymnOpenNode = fn(id) so the
   shell's node search focuses in-page instead of navigating away.

   Served by src/laplace/web/shared_ui.py at GET /shared/shell.js.
   ═══════════════════════════════════════════════════════════════════════ */
(function(){
  "use strict";
  if(window.HymnShell) return;

  // ── tab self-dedupe (2026-07-15, "a million tabs") ────────────────────────
  // Duplicate instances of the SAME surface URL (pathname+search; hash ignored)
  // find each other over a BroadcastChannel and converge to ONE: the newest
  // clean instance survives; a tab reporting dirty (window.__hymnTabDirty, a
  // page-settable hook) NEVER self-closes. Session-restored and launcher-minted
  // duplicates evaporate as they load; a page opts out with
  // window.__hymnNoDedupe = true. window.close() is best-effort: Chrome allows
  // it for single-history-entry tabs (exactly what webbrowser.open mints); a
  // refused close marks the tab unkillable and it simply stays — never an error.
  (function dedupe(){
    if(window.__hymnNoDedupe || typeof BroadcastChannel === "undefined") return;
    const KEY = location.pathname + location.search;
    const ID = Math.random().toString(36).slice(2);
    const BORN = Date.now();
    const FRESH_MS = 90e3;              // background-tab timers throttle to ~1/min
    const peers = new Map();            // id -> {born, dirty, seen}
    let ch, unkillable = false;
    try{ ch = new BroadcastChannel("hymn-tab-dedupe"); }catch(e){ return; }
    const isDirty = () => { try{ return !!(window.__hymnTabDirty && window.__hymnTabDirty()); }catch(e){ return false; } };
    const ping = () => { try{ ch.postMessage({key: KEY, id: ID, born: BORN, dirty: isDirty()}); }catch(e){} };
    function evaluate(){
      if(unkillable || isDirty()) return;
      const now = Date.now();
      for(const [pid, p] of peers){
        if(now - p.seen > FRESH_MS){ peers.delete(pid); continue; }
        // survivor law: dirty beats clean; among clean, newest born (then highest id) wins
        if(p.dirty || p.born > BORN || (p.born === BORN && pid > ID)){
          window.close();
          setTimeout(() => { unkillable = true; }, 100);  // still here => Chrome refused; stay, quietly
          return;
        }
      }
    }
    ch.onmessage = (ev) => {
      const m = ev.data || {};
      if(m.key !== KEY || !m.id || m.id === ID) return;
      const known = peers.has(m.id);
      peers.set(m.id, {born: m.born || 0, dirty: !!m.dirty, seen: Date.now()});
      if(!known) ping();                // introduce ourselves to the newcomer once
      evaluate();
    };
    // the debug handle: read-only observability (which instance am I, who do I see)
    window.__hymnDedupe = {key: KEY, id: ID, born: BORN, peers: peers};
    ping();
    setInterval(ping, 20e3);
  })();

  const ec = encodeURIComponent;
  const params = new URLSearchParams(location.search);
  let corpus = params.get("corpus") || "";

  // THE NAV IS NOT HARDCODED HERE. The one authored roster lives server-side in
  // shared_ui._VIEWS and is served at GET /shared/views {views:[{id,title,path,
  // purpose,group}]}; the shell fetches it once and renders nav from it (W0.1).
  // Add a surface there, not here. VIEWS is the fetched roster (view objects);
  // empty until the fetch lands, and it degrades to an empty nav offline rather
  // than reintroducing a stale hardcoded copy.
  let VIEWS = [];
  async function loadViews(){
    if(VIEWS.length) return VIEWS;
    try{
      const r = await fetch("/shared/views");
      if(r.ok) VIEWS = (await r.json()).views || [];
    }catch(e){ /* offline — nav stays empty rather than lying about the roster */ }
    return VIEWS;
  }

  // THE JOURNEY (the final-authorship shell, 2026-07-22): the nav renders the
  // PROCESS a paper walks — Home · Grow → Shape → Read · Judge → Machine · Desk —
  // with one live, server-composed state word per stage (GET /shared/journey).
  // The shell renders these words verbatim; it composes no meaning of its own.
  let JOURNEY = null;
  async function loadJourney(){
    if(JOURNEY) return JOURNEY;
    try{
      const q = corpus ? "?corpus="+ec(corpus) : "";
      const r = await fetch("/shared/journey"+q);
      if(r.ok) JOURNEY = await r.json();
    }catch(e){ /* offline — the roster floor below still renders a nav */ }
    return JOURNEY;
  }

  function ensureCss(){
    if(document.querySelector("link[href='/shared/hymn.css']")) return;
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "/shared/hymn.css";
    document.head.appendChild(l);
  }

  // W8 — the tutorial overlay's layout CSS, injected ONCE (idempotent), the run-tray
  // ensureCSS idiom. Every colour rides a hymn var (or a color-mix DERIVED from one —
  // the scrim); no literal. Injected at build so the '? tour' chip is styled before
  // the first open. Full engine + step tables live in THE TUTORIAL OVERLAY, below.
  function ensureTourCss(){
    if(document.getElementById("hy-tour-css")) return;
    const st = document.createElement("style");
    st.id = "hy-tour-css";
    st.textContent =
      ".hy-tour-btn{background:var(--panel2);color:var(--ink2);border:1px solid var(--edge2);"+
        "border-radius:6px;padding:3px 9px;font-family:var(--mono);font-size:11px;cursor:pointer;white-space:nowrap}"+
      ".hy-tour-btn:hover{border-color:var(--accent);color:var(--ink)}"+
      ".hy-tour-spot{position:fixed;z-index:2147482000;border:2px solid var(--accent);border-radius:8px;"+
        "box-shadow:0 0 0 100vmax color-mix(in srgb,var(--bg) 74%,transparent);"+
        "pointer-events:none;transition:top .18s ease,left .18s ease,width .18s ease,height .18s ease}"+
      ".hy-tour-card{position:fixed;z-index:2147482001;max-width:344px;width:min(344px,calc(100vw - 24px));"+
        "background:var(--panel);color:var(--ink);border:1px solid var(--edge2);border-radius:10px;"+
        "box-shadow:var(--hy-pop-shadow);padding:13px 14px}"+
      ".hy-tour-card .tc-title{font-weight:700;color:var(--ink);font-size:13px;line-height:1.35;margin-bottom:6px}"+
      ".hy-tour-card .tc-body{color:var(--ink2);font-size:12px;line-height:1.55}"+
      ".hy-tour-card .tc-body b{color:var(--ink);font-weight:600}"+
      ".hy-tour-card .tc-body code{font-family:var(--mono);font-size:11px;color:var(--teal)}"+
      ".hy-tour-card .tc-foot{display:flex;align-items:center;gap:8px;margin-top:12px}"+
      ".hy-tour-card .tc-count{font-family:var(--mono);font-size:10px;color:var(--dim);margin-right:auto}"+
      ".hy-tour-nav{background:var(--panel2);color:var(--ink2);border:1px solid var(--edge2);border-radius:6px;"+
        "padding:4px 12px;font-family:var(--mono);font-size:11px;cursor:pointer}"+
      ".hy-tour-nav:hover:not([disabled]){border-color:var(--accent);color:var(--ink)}"+
      ".hy-tour-nav[disabled]{opacity:.4;cursor:default}"+
      ".hy-tour-nav.is-primary{border-color:var(--accent);color:var(--accent)}"+
      ".hy-tour-x{background:none;border:none;color:var(--dim);cursor:pointer;font-size:16px;line-height:1;padding:0 3px;margin-left:2px}"+
      ".hy-tour-x:hover{color:var(--ink)}"+
      ".hy-tour-esc{font-family:var(--mono);font-size:9px;color:var(--dim);margin-top:9px}"+
      ".hy-tour-esc b{color:var(--ink2);font-weight:600}";
    document.head.appendChild(st);
  }

  // a roster row can carry more than one path it answers: `path` (the pinned label)
  // and `served` (where a bare-page redirect actually lands — Machine's row keeps
  // /pipeline but serves at /project). Both must resolve the row so the chrome lights
  // on the served page too. Returns the row's candidate paths, longest-first-agnostic.
  function viewPaths(v){
    const out = [];
    if(v.path) out.push(v.path);
    if(v.served && v.served !== v.path) out.push(v.served);
    return out;
  }
  function pathHit(vp, p){
    return vp === "/" ? (p === "/" || p === "/index.html")
                      : (p === vp || p.startsWith(vp));
  }

  // the active view is derived FROM the roster (never a second hardcoded map):
  // the row whose path (or served alias) is the longest prefix of the current
  // pathname wins, so "/" only matches home and "/conceptric" matches
  // "/conceptric/inspect", and "/project" matches Machine's served alias.
  function activeView(){
    const p = location.pathname;
    let best = "", bestLen = -1;
    for(const v of VIEWS){
      for(const vp of viewPaths(v)){
        if(pathHit(vp, p) && vp.length > bestLen){ best = v.id; bestLen = vp.length; }
      }
    }
    return best;
  }

  // the projection view needs a file= — derived from the corpus' projection plan.
  let PLAN = null;
  async function planTarget(){
    if(!corpus) return null;
    if(PLAN !== null) return PLAN;
    try{
      const r = await fetch("/shared/plan?corpus="+ec(corpus));
      PLAN = r.ok ? await r.json() : false;
    }catch(e){ PLAN = false; }
    return PLAN;
  }

  function viewHref(path){
    const q = corpus ? "?corpus="+ec(corpus) : "";
    return path + q;
  }

  function esc(s){ return String(s == null ? "" : s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }

  // the journey's floor when /shared/journey is unreachable: a flat strip from the
  // roster (every view still reachable — an honest degrade, never an empty chrome).
  function floorLink(v, act){
    return "<div class='hy-stage-wrap'><a class='hy-stage' data-view='"+esc(v.id)+"'"+
      " data-path='"+esc(v.path)+"' href='"+esc(viewHref(v.path))+"'"+
      " title='"+esc(v.purpose||"")+"'"+(v.id === act ? " aria-current='page'" : "")+">"+
      "<span class='st-t"+(v.id === act ? " on" : "")+"'>"+esc(v.title||v.id)+"</span></a></div>";
  }

  // ONE STAGE of the journey: the stage link (title + live state word) and its
  // hover/focus card (what this stage is + its doors). Hover REVEALS the card —
  // out of flow, geometrically stable; click navigates. The card also opens on
  // keyboard focus (focus-within), so every door stays reachable without a mouse.
  function stageEl(st, act){
    const isHere = st.view === act;
    const doorHere = !isHere && (st.doors || []).some(d => d.view === act);
    // standing inside one of this stage's door-surfaces (Assets/Analytics/Altitude/
    // Guide): name the door-surface ON the lit stage so the spine alone answers
    // where-am-I, not only the underline (finding 8).
    const activeDoor = doorHere ? (st.doors || []).find(d => d.view === act) : null;
    const doorHereEl = activeDoor
      ? "<span class='st-door-here'>"+esc(activeDoor.title)+"</span>" : "";
    // THE CAPTION LINE — always reserved (finding 4): a stage with a live word shows it; a
    // wordless stage (every stage on Home) renders a MUTED PLACEHOLDER caption so the roster
    // keeps ONE constant height across surfaces, never jumping ~6px between one- and two-line
    // states. The desk keeps its dynamic #hy-desk-word span (setDeskBadge fills it or returns
    // it to the placeholder), so a decision count never grows the roster either.
    const word = st.word
      ? "<span class='st-w"+(st.ask ? " is-ask" : "")+"'>"+esc(st.word)+"</span>"
      : (st.id === "desk"
          ? "<span class='st-w is-placeholder' id='hy-desk-word' aria-hidden='true'> </span>"
          : "<span class='st-w is-placeholder' aria-hidden='true'> </span>");
    const badge = st.id === "desk"
      ? "<span class='hy-badge' id='hy-desk-badge' title='open on your desk' hidden></span>" : "";
    const doors = (st.doors || []).map(d =>
      "<a class='sc-door' "+(d.view ? "data-view='"+esc(d.view)+"' " : "")+
      "data-path='"+esc(d.path)+"' href='"+esc(viewHref(d.path))+"'"+
      (d.view === act ? " aria-current='page'" : "")+">"+
        "<span class='scd-t"+(d.view === act ? " on" : "")+"'>"+esc(d.title)+"</span>"+
        "<span class='scd-p'>"+esc(shortPurpose(d.purpose))+"</span>"+
      "</a>").join("");
    return "<div class='hy-stage-wrap"+(st.flank ? " is-flank" : "")+
        (st.align === "right" ? " is-right" : "")+"'>"+
      "<a class='hy-stage"+(isHere ? " on" : "")+(doorHere ? " on-door" : "")+"'"+
        " data-view='"+esc(st.view)+"' data-path='"+esc(st.path)+"'"+
        " href='"+esc(viewHref(st.path))+"'"+(isHere ? " aria-current='page'" : "")+">"+
        "<span class='st-t'>"+esc(st.stage)+"</span>"+word+badge+doorHereEl+
      "</a>"+
      "<div class='hy-stage-card' role='group' aria-label='"+esc(st.stage)+"'>"+
        "<div class='sc-head'>"+esc(st.stage)+
          (isHere ? "<span class='sc-here'>you are here</span>" : "")+"</div>"+
        (st.word ? "<div class='sc-word'>"+esc(st.word)+"</div>" : "")+
        "<div class='sc-purpose'>"+esc(st.purpose||"")+"</div>"+
        (doors ? "<div class='sc-doors'>"+doors+"</div>" : "")+
      "</div>"+
    "</div>";
  }

  // the journey nav html: flanks sit at the ends; the four process stages flow
  // left→right with the arrow naming the direction the paper travels.
  function journeyHTML(act){
    const stages = (JOURNEY && JOURNEY.stages) || [];
    if(!stages.length)
      return VIEWS.map(v => floorLink(v, act)).join("");   // the roster floor
    const parts = [];
    stages.forEach((st, i) => {
      // the last two wraps anchor their cards right so nothing spills the viewport
      st.align = i >= stages.length - 2 ? "right" : "";
      if(i > 0){
        const flowing = !st.flank && !stages[i-1].flank;
        parts.push("<span class='hy-flow'"+(flowing ? "" : " data-quiet='1'")+
          " aria-hidden='true'>"+(flowing ? "→" : "·")+"</span>");
      }
      parts.push(stageEl(st, act));
    });
    return parts.join("");
  }

  async function build(){
    ensureCss();
    if(document.getElementById("hy-shell")) return;
    await Promise.all([loadViews(), loadJourney()]);   // the roster + the composed spine
    const bar = document.createElement("div");
    bar.id = "hy-shell";
    const act = activeView();
    // THE MASTHEAD — the mark, the active project with its live position, and the
    // right cluster; THE JOURNEY beneath it — the process spine with you-are-here.
    bar.innerHTML =
      "<div class='hy-top'>"+
      "<a class='hy-mark' href='"+esc(viewHref("/"))+"'"+
      " title='home — every paper at a glance'>"+
        "⌁ eigen<small>engine</small>"+
      "</a>"+
      // THE ACTIVE PROJECT — front and centre, its live state; a door back to the
      // dashboard. Hidden until wireProj() finds the current project (needs a corpus).
      "<a class='hy-proj' id='hy-proj' href='/' hidden"+
      " title='back home — every paper at a glance'>"+
        "<span class='pj-name' id='hy-proj-name'></span>"+
        "<span class='hy-chip' id='hy-proj-chip'></span>"+
        "<span class='pj-pos' id='hy-proj-pos'></span>"+
      "</a>"+
      // the right cluster — the tour toggle + switch + find, one instrument. The find
      // placeholder is SCOPED to the active project (find in <project>…).
      "<div class='hy-cluster'>"+
        // W8: the guided-tour toggle — a '? tour' the shell renders on EVERY surface.
        // Click → the in-place tutorial overlay (see THE TUTORIAL OVERLAY below).
        "<button type='button' class='hy-tour-btn' id='hy-tour-btn' aria-haspopup='dialog'"+
        " title='guided tour of this surface — what each thing is, where its data comes"+
        " from, and what acting on it does'>? tour</button>"+
        // W-guide: the '?' affordance — one universal mechanism the shell renders on EVERY
        // surface. Opens a per-surface guide panel (this surface's purpose + every verb
        // answering 'what will this do', each with its PSU class) and a door to the full
        // /guide. Distinct from '? tour' (which spotlights live elements); this reads the
        // contract so it can't drift, and degrades honestly when /guide isn't routed yet.
        "<button type='button' class='hy-tour-btn' id='hy-guide-btn' aria-haspopup='dialog'"+
        " title='what does this surface do — its purpose and, for every verb, what firing"+
        " it will do (what it writes, its cost, its PSU class), before you click'>?</button>"+
        "<div class='hy-switch' id='hy-switch'>"+
          "<input id='hy-switch-input' autocomplete='off' spellcheck='false'"+
          " placeholder='switch project…'"+
          " title='switch project — type to filter, ↑↓ + enter; your place is kept per project'>"+
          "<div class='hy-switch-list' id='hy-switch-list' role='listbox'></div>"+
        "</div>"+
        "<div class='hy-search'>"+
          "<input id='hy-q' autocomplete='off' placeholder='"+
            esc(corpus ? "find in "+corpus+"…" : "find node…")+"'>"+
          "<div class='hy-sres' id='hy-sres'></div>"+
        "</div>"+
      "</div>"+
      "</div>"+
      "<nav class='hy-journey' aria-label='the process'>"+journeyHTML(act)+"</nav>";
    document.body.insertBefore(bar, document.body.firstChild);
    wireBrand(bar);
    wireProj(bar);     // the active-project chip (fetches /dashboard/data once, cached)
    recordSurface();   // J5: bank THIS surface as the current project's place (server-side)

    // the shell claims its strip: pages lay out below it, whatever their scheme
    document.body.style.boxSizing = "border-box";
    // keep the page's top inset === the bar's ACTUAL height. The nav wraps to a second
    // line (and the project name / find input fill in) AFTER build, growing the bar past
    // its initial min-height; a one-shot pad() then leaves the context header (and its
    // ladder trigger) occluded behind the fixed bar — a dead click. A ResizeObserver on
    // the bar re-runs pad() on every reflow so the header always clears the bar.
    const pad = () => {
      document.body.style.paddingTop = bar.offsetHeight + "px";
      // sticky rails and page anchors read the bar's REAL height from this var
      // (the journey wraps on narrow viewports, so the height is dynamic).
      document.documentElement.style.setProperty("--hy-shell-real", bar.offsetHeight + "px");
    };
    pad();
    window.addEventListener("resize", pad);
    if(window.ResizeObserver){ try{ new ResizeObserver(pad).observe(bar); }catch(e){ /* pad() + resize still hold */ } }

    // resolve the corpus at CLICK time — an in-page corpus switch (an applet's own
    // selector that history.replaceState'd the URL) still carries across the hop.
    // Every journey link (stage or door) carries data-path; the handler appends
    // the live corpus so a hop never loses which paper is in view.
    bar.querySelectorAll("nav a[data-path]").forEach(a => {
      a.addEventListener("click", e => {
        e.preventDefault();
        const cur = new URLSearchParams(location.search).get("corpus") || corpus;
        location.href = a.dataset.path + (cur ? "?corpus="+ec(cur) : "");
      });
    });

    wireSwitch(bar);
    wireSearch(bar);
    wireTour(bar);       // W8: the '? tour' chip opens the in-place tutorial overlay
    wireGuide(bar);      // W-guide: the '?' chip opens the per-surface guide panel
    wireOriginStamp();   // D15: bank THIS surface as the navigation origin on the way out
    injectContext(bar);  // L1: the shared context header, under the bar, on every surface
  }

  // W8 — wire the '? tour' chip to the tutorial overlay. Styled at build (ensureTourCss);
  // the engine only mounts on the first click, so an untouched surface pays nothing.
  function wireTour(bar){
    ensureTourCss();
    const b = bar.querySelector("#hy-tour-btn");
    if(b) b.addEventListener("click", e => { e.preventDefault(); startTour(); });
  }

  // the brand chip is HOME (/) and carries the corpus at click time, the same
  // contract the nav links honour — an in-page corpus switch still rides home.
  function wireBrand(bar){
    const a = bar.querySelector("a.hy-mark");
    if(!a) return;
    a.addEventListener("click", e => {
      e.preventDefault();
      const cur = new URLSearchParams(location.search).get("corpus") || corpus;
      location.href = "/" + (cur ? "?corpus="+ec(cur) : "");
    });
  }

  // THE ACTIVE PROJECT (his 2026-07-15 ruling: the bar carries live state, not grey links).
  // Fetched ONCE from /dashboard/data (cheap, cached for the page's life) and only when a
  // corpus is in view; the chip wears the project's state family, the door returns to /.
  // Degrades silently — offline / no-project, the door just stays hidden (never a false state).
  let DASH = null;
  async function loadDash(){
    if(DASH !== null) return DASH;
    try{ const r = await fetch("/dashboard/data"); DASH = r.ok ? await r.json() : false; }
    catch(e){ DASH = false; }
    return DASH;
  }
  // state -> chip family (mirrors the dashboard's stateChipClass; colour is meaning):
  // live/running -> accent, released/accepted -> ok, never-run -> neutral, else -> warn.
  function projStateClass(state){
    if(state === "NEVER_RUN") return "is-never";
    if(state === "UNDER_CONVERGENCE" || state === "REOPENED") return "is-live";
    if(state === "RELEASED" || state === "AUTHOR_ACCEPTED" || state === "FINAL_GATES_PASSED") return "is-ok";
    return "is-warn";
  }
  const niceState = s => String(s == null ? "" : s).toLowerCase().replace(/_/g, " ");
  async function wireProj(bar){
    try{
      const a = bar.querySelector("#hy-proj");
      if(!a) return;
      const c = new URLSearchParams(location.search).get("corpus") || corpus;
      if(!c) return;                        // no project in view → the door stays hidden
      a.setAttribute("href", "/?corpus=" + ec(c));
      const name = bar.querySelector("#hy-proj-name");
      // seed identity IMMEDIATELY from the corpus name and reveal the door, so the
      // masthead never flickers absent while /dashboard/data is in flight; the live
      // state chip below enriches when the fetch lands (finding 7).
      if(name) name.textContent = c;
      a.hidden = false;
      const data = await loadDash();
      if(!data || !data.projects) return;
      const p = data.projects.find(x => x.name === c);
      if(!p) return;
      const chip = bar.querySelector("#hy-proj-chip");
      const pos  = bar.querySelector("#hy-proj-pos");
      if(name) name.textContent = p.name;
      const stateNice = niceState(p.state);
      // ONE TRUTH IN THE CHROME (P2, the critic's blocking find): the pill speaks the
      // truth-layer's position words when the server provides them (p.position from
      // shared_ui.position_words — e.g. "pre-release · GEN-3"), so the header can never
      // say "never run" beside a page whose body knows the paper is minted. Raw machine
      // state remains the fallback for rows the truth layer has nothing richer about.
      const pillText = p.position || stateNice;
      if(chip){ chip.className = "hy-chip " + projStateClass(p.state); chip.textContent = pillText; }
      // BADGES RENDER ONCE (P10/job4): pipeline_position echoes state for most projects
      // ("never run" · NEVER RUN via .pj-pos's uppercase CSS) — the doubled-badge defect
      // his walk named. Show the position chip only when it says something the pill chip
      // does not; an echo of the same word stays silent rather than shouting it twice.
      if(pos){
        const posNice = niceState(p.pipeline_position);
        pos.hidden = !posNice || posNice === stateNice || posNice === niceState(pillText);
        pos.textContent = pos.hidden ? "" : posNice;
      }
      a.hidden = false;
    }catch(e){ /* the bar never breaks the surface — the door just stays hidden */ }
  }

  // the desk badge slot: W1.3 calls HymnShell.setDeskBadge(n) with the desk's open
  // count. Absent / 0 / non-positive renders as no badge (graceful until wired).
  // The Desk STAGE carries the badge (its count belongs to its place on the
  // journey) plus a state word speaking the same number as a phrase.
  function setDeskBadge(n){
    const b = document.getElementById("hy-desk-badge");
    if(!b) return;
    const v = Number(n);
    const w = document.getElementById("hy-desk-word");
    if(!isFinite(v) || v <= 0){
      b.hidden = true; b.textContent = "";
      // return the desk word to the reserved PLACEHOLDER (finding 4), never hidden, so the
      // roster keeps its constant height whether or not a decision count is present.
      if(w){ w.hidden = false; w.textContent = " "; w.classList.add("is-placeholder"); }
      return;
    }
    b.textContent = v > 99 ? "99+" : String(Math.floor(v));
    b.hidden = false;
    if(w){ w.textContent = v === 1 ? "1 decision waits" : v + " decisions wait";
           w.hidden = false; w.classList.remove("is-placeholder"); }
  }

  // J5 — THE PROJECT QUICK-SWITCH (the topbar corpus select, demoted to a searchable,
  // keyboardable combo per the conception). Type to filter, ↑/↓ move, Enter switches;
  // a click switches too. Switching lands on the TARGET project's LAST SURFACE (per-project
  // place kept server-side in .cockpit.json) — never a blind reset. The corpus rides the
  // URL either way (store.mjs-canonical). Shared chrome: every surface gets this.
  async function wireSwitch(bar){
    const wrap = bar.querySelector("#hy-switch");
    if(!wrap) return;
    const inp = wrap.querySelector("#hy-switch-input");
    const list = wrap.querySelector("#hy-switch-list");
    let corpora = [];
    try{
      const r = await fetch("/corpus/list");
      if(r.ok) corpora = (await r.json()).corpora || [];
    }catch(e){ /* offline — the switch just stays empty */ }
    if(corpus) inp.value = corpus;
    let active = -1;

    function matches(){
      const q = inp.value.trim().toLowerCase();
      // input still showing the current corpus verbatim ⇒ browse ALL (open to switch away)
      const showAll = !q || q === (corpus || "").toLowerCase();
      return corpora.filter(c => showAll || c.toLowerCase().includes(q));
    }
    function render(open){
      const rows = matches();
      if(active >= rows.length) active = rows.length - 1;
      list.innerHTML = rows.length
        ? rows.map((c, i) => "<div class='hy-switch-row"+(i === active ? " active" : "")+
            (c === corpus ? " cur" : "")+"' role='option' data-corpus='"+esc(c)+"'>"+esc(c)+"</div>").join("")
        : "<div class='hy-switch-none'>no project matches</div>";
      wrap.classList.toggle("open", !!open && (rows.length > 0 || inp.value.trim().length > 0));
      list.querySelectorAll(".hy-switch-row").forEach(el =>
        el.addEventListener("mousedown", e => { e.preventDefault(); switchTo(el.dataset.corpus); }));
    }

    // select-all-on-focus (his ACT5/job3 ruling): clicking the input selects the existing
    // text so typing immediately replaces it, rather than appending to the current corpus.
    inp.addEventListener("focus", () => { active = -1; render(true); inp.select(); });
    inp.addEventListener("input", () => { active = -1; render(true); });
    inp.addEventListener("keydown", e => {
      const rows = matches();
      if(e.key === "ArrowDown"){ e.preventDefault(); active = Math.min(active + 1, rows.length - 1); render(true); }
      else if(e.key === "ArrowUp"){ e.preventDefault(); active = Math.max(active - 1, 0); render(true); }
      else if(e.key === "Enter"){ e.preventDefault();
        const pick = active >= 0 ? rows[active] : rows[0];
        if(pick) switchTo(pick); }
      else if(e.key === "Escape"){ wrap.classList.remove("open"); inp.blur(); }
    });
    document.addEventListener("click", e => { if(!wrap.contains(e.target)) wrap.classList.remove("open"); });
  }

  // switch to project `c`: KEEP THE CURRENT SURFACE — never jump to the target project's
  // own last-visited place (ACT5/job3 ruling: switching projects changes WHICH paper is in
  // view, not WHERE in the interface he is standing). The carried SELECTION (node / asset /
  // version / section / beat / round / anchor) DROPS on the hop — a selection token is
  // scoped to the project it was made in, and dragging it into an unrelated paper (e.g.
  // sec:abstract surviving a switch to a paper with no such section) is exactly the
  // confusion his 2026-07-21 walk named. The corpus rides the URL (store.mjs-canonical).
  function switchTo(c){
    if(!c) return;
    const u = new URL(location.href);
    u.searchParams.set("corpus", c);
    for(const k of ["node","asset","version","section","beat","round","anchor"])
      u.searchParams.delete(k);
    location.href = u.pathname + u.search;
  }

  // per-project PLACE (J5): the surface last seen for a project, server-persisted in
  // .cockpit.json (survives a browser wipe, like review_last_visit). CLIENT-SIDE MERGE —
  // read the whole cockpit, set ONE key, write the whole last_surface map back — so a
  // shallow cockpit_state POST never clobbers a sibling project's place. Recorded on every
  // normal visit (recordSurface, below); no longer read by switchTo (ACT5/job3: a project
  // switch keeps the current surface instead of jumping to this recorded place).
  async function readCockpit(){
    try{ const r = await fetch("/cockpit/state"); if(r.ok) return await r.json(); }catch(e){}
    return {};
  }
  async function recordSurface(){
    const c = new URLSearchParams(location.search).get("corpus") || corpus;
    if(!c) return;
    const st = await readCockpit();
    const ls = Object.assign({}, st.last_surface || {});
    ls[c] = location.pathname + location.search;
    try{ await fetch("/cockpit/state", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ last_surface: ls }) }); }catch(e){ /* offline — place just isn't kept */ }
  }

  // W2: the old wireProjectionHref (injecting file= into the /projection nav link) is
  // retired — the Artefact surface resolves its own current-artefact server-side through
  // registry.project_context (/artefact/context), so the nav link needs only ?corpus=.

  function wireSearch(bar){
    const inp = bar.querySelector("#hy-q");
    const res = bar.querySelector("#hy-sres");
    let t = null;
    inp.addEventListener("input", () => {
      clearTimeout(t);
      const q = inp.value.trim();
      if(!q || !corpus){ res.classList.remove("on"); res.innerHTML = ""; return; }
      t = setTimeout(async () => {
        let rows = [];
        try{
          const r = await fetch("/corpus/search?corpus="+ec(corpus)+"&q="+ec(q));
          if(r.ok) rows = (await r.json()).results || [];
        }catch(e){ /* silent */ }
        if(!rows.length){ res.classList.remove("on"); res.innerHTML = ""; return; }
        res.innerHTML = rows.slice(0, 14).map(n =>
          "<div class='hy-srow' data-id='"+esc(n.id)+"'>"+
          "<button type='button' class='hy-srow-ladder' data-id='"+esc(n.id)+"'"+
            " aria-haspopup='listbox' title='open the ladder for this node — no navigation'>⋮ ladder</button>"+
          esc((n.essence || n.id).slice(0, 90))+
          "<div class='sid'>"+esc(n.id)+" · "+esc(n.kind || "")+"</div></div>").join("");
        res.classList.add("on");
        res.querySelectorAll(".hy-srow").forEach(el => el.onclick = (e) => {
          if(e.target.closest(".hy-srow-ladder")) return;   // the glyph opens the ladder in place
          res.classList.remove("on"); inp.value = "";
          openNode(el.dataset.id);
        });
        // the ⋮ ladder glyph: six rungs over the hit WITHOUT leaving the find (D15: not a nav)
        res.querySelectorAll(".hy-srow-ladder").forEach(g => g.onclick = (e) => {
          e.preventDefault(); e.stopPropagation();
          openLadder({target: g.dataset.id, kind: "node", anchorEl: g});
        });
      }, 160);
    });
    document.addEventListener("click", e => {
      if(!res.contains(e.target) && e.target !== inp) res.classList.remove("on");
    });
  }

  function openNode(id){
    if(typeof window.__hymnOpenNode === "function"){ window.__hymnOpenNode(id); return; }
    location.href = "/conceptric?corpus="+ec(corpus)+"&node="+ec(id);
  }

  // ---- the .hy-stale atom (W1.2): the ONE stale-banner idiom over every derived
  // read, replacing the per-page variants (review's #stale, storyboard's #sb-stale,
  // altitude's plan/prose badge). hyStale(read) renders a
  // {present,fresh,reason,producer,built_ts,fix,degraded} row; the THREE states render
  // DISTINCTLY — is-fresh (in sync), is-stale (present but out of date), is-absent (not
  // built). A degraded (absent|stale) read SAYS SO — the DEGRADED plumb. The atom NEVER
  // fires a rebuild: the `fix` field only NAMES the deliberate gesture, it is not a POST.
  function hyStale(read){
    if(!read) return "";
    const state = !read.present ? "absent" : (read.fresh ? "fresh" : "stale");
    const label = esc(read.label || read.id || "derived read");
    if(state === "fresh")
      return "<span class='hy-stale is-fresh' data-read='"+esc(read.id||"")+"'>"+
        "<b class='hy-stale-dot'></b>"+label+" · in sync</span>";
    const badge = state === "absent" ? "missing" : "stale";
    const reason = esc(read.reason || (state === "absent" ? "not built" : "out of date"));
    const ts = read.built_ts ? "<span class='hy-stale-ts'>built "+esc(read.built_ts)+"</span>" : "";
    const prod = read.producer ? "<span class='hy-stale-prod'>producer: "+esc(read.producer)+"</span>" : "";
    const fix = read.fix ? "<span class='hy-stale-fix'>fix: "+esc(read.fix)+"</span>" : "";
    return "<div class='hy-stale is-"+state+"' data-read='"+esc(read.id||"")+"'>"+
        "<span class='hy-stale-badge'>"+badge+"</span>"+
        "<span class='hy-stale-msg'><b>"+label+"</b> — "+reason+ts+prod+"</span>"+
        fix+
      "</div>";
  }

  // fill a `.hy-stale-strip` container with the DEGRADED reads of a /shared/staleness
  // payload (fresh reads stay silent — no banner noise on a healthy tree). The strip
  // shows itself (.on) only when something is degraded. Returns the count rendered.
  function renderStale(el, payload){
    if(!el) return 0;
    const bad = ((payload && payload.reads) || []).filter(r => r.degraded);
    el.innerHTML = bad.map(hyStale).join("");
    el.classList.toggle("on", bad.length > 0);
    return bad.length;
  }

  // read the staleness contract (pure GET; never triggers a rebuild). Degrades to null
  // offline rather than lying "fresh".
  async function fetchStale(c){
    try{
      const q = (c || corpus) ? "?corpus="+ec(c || corpus) : "";
      const r = await fetch("/shared/staleness"+q);
      if(r.ok) return await r.json();
    }catch(e){ /* offline — silent, no false 'fresh' */ }
    return null;
  }

  // ---- shared math: KaTeX (vendored under /shared/katex/), loaded lazily ONCE.
  // Any surface calls window.renderMath(el) after injecting content and every
  // $...$ / $$...$$ / \(..\) / \[..\] in it renders. Editable regions and form
  // controls are skipped (a KaTeX span inside a contenteditable breaks editing).
  let mathReady = null;
  function ensureMath(){
    if(mathReady) return mathReady;
    mathReady = new Promise(res => {
      const css = document.createElement("link");
      css.rel = "stylesheet"; css.href = "/shared/katex/katex.min.css";
      document.head.appendChild(css);
      const s1 = document.createElement("script");
      s1.src = "/shared/katex/katex.min.js";
      s1.onload = () => {
        const s2 = document.createElement("script");
        s2.src = "/shared/katex/auto-render.min.js";
        s2.onload = () => res(true); s2.onerror = () => res(false);
        document.head.appendChild(s2);
      };
      s1.onerror = () => res(false);
      document.head.appendChild(s1);
    });
    return mathReady;
  }
  window.renderMath = async function(el){
    if(!el) return;
    if(!(await ensureMath()) || !window.renderMathInElement) return;
    if(el.isContentEditable) return;
    try{
      window.renderMathInElement(el, {
        delimiters: [
          {left: "$$", right: "$$", display: true},
          {left: "\\[", right: "\\]", display: true},
          {left: "$", right: "$", display: false},
          {left: "\\(", right: "\\)", display: false},
        ],
        throwOnError: false,
        ignoredTags: ["script","style","textarea","pre","code","input","select","button"],
        ignoredClasses: ["no-math"],
      });
    }catch(e){}
  };

  // ---- the VERSION RAIL (W3.3): the ONE version-history idiom, shared by /review,
  // /guide, /analytics — one implementation here, consumed by three surfaces (never
  // three copies). A right-side drawer that renders GET /shared/versions as a timeline
  // grouped snapshot/round/release, each row deep-linking its evidence (a round into
  // /review, a release PDF through the /projection viewer, a snapshot's paths as detail).
  //
  // LAZY — the W2.4 first-paint law: openRail() is the ONLY caller of /shared/versions,
  // and it is bound to a user gesture on every surface, so the versions payload is
  // fetched ON OPEN, NEVER at first paint (opening /review, /guide, /analytics touches
  // none of it). Honest empty (the F10 distinction, rendered): a never-run project reads
  // as never-run, an emptied versions/ dir reads present-but-empty, a failed fetch reads
  // "unavailable" — never a claim of "no history" it can't back, and NEVER a spinner that
  // spins forever (every branch replaces the loading line).
  let RAIL_EL = null;          // the drawer (built once, reused)
  const RAIL_CACHE = {};       // corpus -> successful payload (re-opening is instant; failures never cache)
  const RAIL_GROUPS = [        // the timeline's fixed grouping order
    {kind: "snapshot", title: "snapshots"},
    {kind: "round",    title: "rounds"},
    {kind: "release",  title: "releases"},
  ];

  // the evidence deep-link for one row — a LIVE route, or null (null => the row shows its
  // paths as the detail, never a dead link). W2 CONSOLIDATION: every kind opens in the ONE
  // artefact surface at its revision (?version=<id>), which loads that revision in the
  // reader (the standing rail's in-place load) — never the retired /review / /projection.
  function railHref(row, c){
    if(!c) return null;
    const paths = row.paths || [];
    const hasArtefact = paths.some(p => /\.(pdf|tex)$/i.test(p));
    if(row.kind === "round" || row.kind === "release" || row.kind === "snapshot")
      return hasArtefact ? "/artefact?corpus=" + ec(c) + "&version=" + ec(row.id) : null;
    return null;
  }

  function railRowEl(row, c){
    const el = document.createElement("div");
    el.className = "hy-rail-row kind-" + esc(row.kind);
    el.dataset.id = row.id != null ? String(row.id) : "";
    const href = railHref(row, c);
    const ts = row.ts ? esc(String(row.ts).replace("T", " ").slice(0, 19)) : "—";
    const state = row.state ? "<span class='hy-rail-state'>" + esc(row.state) + "</span>" : "";
    const label = esc(row.label || row.id || row.kind);
    const paths = (row.paths || []).map(p => "<code>" + esc(p) + "</code>").join(" · ");
    const action = href
      ? "<a class='hy-rail-open' href='" + esc(href) + "'>open ↗</a>"
      : "<span class='hy-rail-detail' title='no viewer route — the evidence path is the detail'>detail</span>";
    el.innerHTML =
      "<div class='hy-rail-line'>" +
        "<span class='hy-rail-kind'>" + esc(row.kind) + "</span>" +
        "<span class='hy-rail-label'>" + label + "</span>" +
        action +
      "</div>" +
      "<div class='hy-rail-meta'>" + ts + " " + state + "</div>" +
      (paths ? "<div class='hy-rail-paths'>" + paths + "</div>" : "");
    return el;
  }

  function renderRail(body, payload, c){
    if(!payload){
      // a failed / 404 fetch: honest UNAVAILABLE, never a false "no history" and never a spinner.
      body.innerHTML = "<div class='hy-rail-empty'>version history is <b>unavailable</b> " +
        "(the /shared/versions read did not return) — not a claim that there is none.</div>";
      return;
    }
    const rows = payload.rows || [];
    if(payload.never_run || !rows.length){
      const snaps = (payload.sources || {}).snapshots || {};
      const emptied = snaps.present && snaps.empty;
      body.innerHTML = "<div class='hy-rail-empty'>" +
        (payload.never_run
          ? "this project has <b>never</b> been through the machine — no snapshots, rounds, or releases yet."
          : (emptied
              ? "the <code>versions/</code> dir is present but <b>empty</b> — snapshots were cleared, not never-made."
              : "no version history on disk yet.")) +
        "</div>";
      return;
    }
    const frag = document.createDocumentFragment();
    for(const g of RAIL_GROUPS){
      const grp = rows.filter(r => r.kind === g.kind);
      if(!grp.length) continue;
      const sec = document.createElement("div");
      sec.className = "hy-rail-group";
      sec.innerHTML = "<div class='hy-rail-gtitle'>" + esc(g.title) +
        " <span class='hy-rail-gn'>" + grp.length + "</span></div>";
      for(const r of grp) sec.appendChild(railRowEl(r, c));
      frag.appendChild(sec);
    }
    body.innerHTML = "";
    body.appendChild(frag);
    if(payload.truncated){
      const t = document.createElement("div");
      t.className = "hy-rail-trunc";
      t.textContent = "showing the newest — " + (payload.omitted || 0) +
        " older row(s) omitted (16KB budget)";
      body.appendChild(t);
    }
  }

  function focusRailRow(id){
    if(!RAIL_EL || id == null) return;
    let sel;
    try{ sel = ".hy-rail-row[data-id='" + (window.CSS && CSS.escape ? CSS.escape(String(id)) : String(id)) + "']"; }
    catch(e){ return; }
    const row = RAIL_EL.querySelector(sel);
    if(row){
      RAIL_EL.querySelectorAll(".hy-rail-row.focus").forEach(r => r.classList.remove("focus"));
      row.classList.add("focus");
      row.scrollIntoView({block: "center"});
    }
  }

  function ensureRailEl(){
    if(RAIL_EL) return RAIL_EL;
    const back = document.createElement("div");
    back.className = "hy-rail-back"; back.id = "hy-rail-back";
    const panel = document.createElement("div");
    panel.className = "hy-rail"; panel.id = "hy-rail";
    panel.innerHTML =
      "<div class='hy-rail-head'>" +
        "<span class='hy-rail-title'>version history</span>" +
        "<span class='hy-rail-corpus' id='hy-rail-corpus'></span>" +
        "<button type='button' class='hy-rail-x' id='hy-rail-x' title='close (Esc)'>×</button>" +
      "</div>" +
      "<div class='hy-rail-body' id='hy-rail-body'></div>";
    document.body.appendChild(back);
    document.body.appendChild(panel);
    back.addEventListener("click", closeRail);
    panel.querySelector("#hy-rail-x").addEventListener("click", closeRail);
    document.addEventListener("keydown", e => { if(e.key === "Escape") closeRail(); });
    RAIL_EL = panel;
    return panel;
  }

  function closeRail(){
    if(RAIL_EL) RAIL_EL.classList.remove("open");
    const b = document.getElementById("hy-rail-back");
    if(b) b.classList.remove("open");
  }

  // OPEN the rail for a corpus — the ONLY caller of GET /shared/versions. The fetch runs
  // HERE, on the open gesture (never at first paint); a successful payload is cached so
  // re-opening the same corpus is instant and re-fetch-free; a failure is not cached (it
  // retries next open) and renders "unavailable" rather than a stuck spinner.
  async function openRail(opts){
    opts = opts || {};
    const c = opts.corpus || corpus || "";
    const panel = ensureRailEl();
    const back = document.getElementById("hy-rail-back");
    const body = document.getElementById("hy-rail-body");
    document.getElementById("hy-rail-corpus").textContent = c || "(no corpus)";
    panel.classList.add("open");
    if(back) back.classList.add("open");
    if(!c){
      body.innerHTML = "<div class='hy-rail-empty'>no corpus selected — pick a project to see its history.</div>";
      return;
    }
    if(Object.prototype.hasOwnProperty.call(RAIL_CACHE, c)){
      renderRail(body, RAIL_CACHE[c], c);
      if(opts.focus) focusRailRow(opts.focus);
      return;
    }
    body.innerHTML = "<div class='hy-rail-loading'>loading version history…</div>";
    let payload = null;
    try{
      const r = await fetch("/shared/versions?corpus=" + ec(c));
      if(r.ok) payload = await r.json();
    }catch(e){ payload = null; }   // null => honest 'unavailable', never a spinner-forever
    if(payload) RAIL_CACHE[c] = payload;
    renderRail(body, payload, c);
    if(opts.focus) focusRailRow(opts.focus);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // THE FOUR UNIVERSAL ATOMS (W0) — built ONCE in the shared chrome so every surface
  // that boots the shell inherits them: L1 context header, D15 arrival echo, D16 rule
  // in place. (L2's hover family is pure hymn.css — no shell code.)
  // ═══════════════════════════════════════════════════════════════════════════

  // roster helpers: the active row (surface title + purpose) and an arbitrary path's row
  // (for naming where an arrival came FROM). Both derive from the ONE fetched roster.
  function viewRow(id){ return VIEWS.find(v => v.id === id) || null; }
  function viewForPath(pathname){
    let best = null, bestLen = -1;
    for(const v of VIEWS){
      for(const vp of viewPaths(v)){        // path + served alias (Machine's /project)
        if(pathHit(vp, pathname) && vp.length > bestLen){ best = v; bestLen = vp.length; }
      }
    }
    return best;
  }

  // the roster purpose truncated at its first sentence / em-dash clause (the full text
  // rides the title attr) — the header wants the short prose label, not the paragraph.
  function shortPurpose(p){
    p = String(p == null ? "" : p).trim();
    if(!p) return "";
    let cut = p.length;
    const em = p.search(/[—–]/);       if(em  >= 0) cut = Math.min(cut, em);
    const dot = p.search(/\.(\s|$)/);  if(dot >= 0) cut = Math.min(cut, dot);
    const head = p.slice(0, cut).trim();
    return head || p;
  }

  // the most specific selection token in view (node ≻ asset ≻ version ≻ section ≻ beat ≻
  // round ≻ anchor), read straight from the URL so the header/echo/ladder never depend on
  // the model being imported. `asset` (the evidence door's key) and `anchor` (altitude's
  // generic resolver key) join the set in W0.5 so the ladder trigger names them too — the
  // key doubles as the ladder's kind= hint (asset ∈ the server's hint kinds; anchor falls
  // to the server grammar, which is honest).
  function currentSelection(){
    const p = new URLSearchParams(location.search);
    for(const k of ["node","asset","version","section","beat","round","anchor"]){
      const v = p.get(k);
      if(v) return {key: k, val: v};
    }
    return null;
  }

  // ── L1 · THE CONTEXT HEADER ────────────────────────────────────────────────
  // One shared line under the bar: <surface> — a view of <purpose> · <project> ·
  // <selection>. Source of truth: the roster row for the active view + the URL's
  // {corpus, selection}. Honest scope (`all projects`) when no project is in view (R1).
  // Idempotent (never double-renders); skips entirely when the page hand-authors its own
  // line (body[data-l1="own"]) — per-surface adoption is Waves 1..n.
  function injectContext(bar){
    if(document.getElementById("hy-context")) return;                 // idempotent
    if(document.body && document.body.dataset && document.body.dataset.l1 === "own") return;
    bar = bar || document.getElementById("hy-shell");
    if(!bar) return;
    const row = viewForPath(location.pathname);
    if(!row) return;                       // unrostered route — no authored purpose to name
    const cur = new URLSearchParams(location.search).get("corpus") || corpus || "";
    const purpose = row.purpose || "";
    const sel = currentSelection();
    const sep = "<span class='hy-ctx-sep'>·</span>";
    // THE SELECTION TOKEN IS THE LADDER TRIGGER (W0.5): a real <button aria-haspopup> + caret,
    // opening six rungs over THIS target. The project token gets the same affordance
    // (kind=project — the corpus-but-no-node answer). The `all projects` scope token stays a
    // plain inert <span> (no button, no aria, no cursor) — nothing to open when no corpus.
    const projTok = cur
      ? "<button type='button' class='hy-ctx-proj hy-ctx-ladder' data-role='project'"+
        " aria-haspopup='listbox' aria-expanded='false'"+
        " title='open the six-rung ladder for this project'>"+
          esc(cur)+"<span class='hy-ctx-caret' aria-hidden='true'>▾</span></button>"
      : "<span class='hy-ctx-proj is-scope'>all projects</span>";
    // the selection token rides in a wrapper (separator + button), hidden when no selection —
    // refreshSelToken() toggles + relabels it live so an SPA store.set never leaves it stale.
    const selTok =
      "<span class='hy-ctx-selwrap'"+(sel ? "" : " hidden")+">"+sep+
        "<button type='button' class='hy-ctx-sel is-ladder hy-ctx-ladder' data-role='sel'"+
        " aria-haspopup='listbox' aria-expanded='false'"+
        " title='open the six-rung ladder for this selection'>"+
          "<span class='hy-ctx-sel-val'>"+esc(sel ? sel.val : "")+"</span>"+
          "<span class='hy-ctx-caret' aria-hidden='true'>▾</span></button></span>";
    let html =
      "<span class='hy-ctx-surface'>"+esc(row.title || row.id)+"</span>"+
      "<span class='hy-ctx-purpose'>— "+esc(shortPurpose(purpose))+"</span>"+
      sep+projTok+selTok;
    const ctx = document.createElement("div");
    ctx.id = "hy-context";
    ctx.className = "hy-context hy-rulable";
    if(purpose) ctx.title = purpose;       // the full purpose text, per the truncation law
    ctx.innerHTML = html;
    document.body.insertBefore(ctx, bar.nextSibling);   // just under the (fixed) bar, in flow
    wireLadderTriggers(ctx);               // W0.5: the tokens open the anchored ladder popover
    renderEcho(ctx);                       // D15: the arrival echo rides the header line
    // D16 first consumer: the header carries the mouth — "rule on THIS surface"
    hyRule.attach(ctx, {
      surface: row.id, title: row.title || row.id, purpose: purpose,
      project: cur, selection: sel, node: "surface:" + row.id,
    });
  }

  // ── D15 · THE ARRIVAL ECHO ─────────────────────────────────────────────────
  // ORIGIN_KEY mirrors store.mjs (the model owns the same stamp when it is imported;
  // this inline copy keeps the echo working on surfaces that never load the model).
  const ORIGIN_KEY = "hymn.origin";
  const ORIGIN_FRESH_MS = 5 * 60 * 1000;

  function readOrigin(){
    try{
      if(window.HymnStore && typeof window.HymnStore.readOrigin === "function")
        return window.HymnStore.readOrigin();
      const raw = sessionStorage.getItem(ORIGIN_KEY);
      return raw ? JSON.parse(raw) : null;
    }catch(e){ return null; }
  }
  function stampOrigin(){
    try{
      if(window.HymnStore && typeof window.HymnStore.stampOrigin === "function"){
        window.HymnStore.stampOrigin(); return;
      }
      sessionStorage.setItem(ORIGIN_KEY, JSON.stringify({
        path: location.pathname + location.search,
        surface: activeView() || null,
        project: new URLSearchParams(location.search).get("corpus") || corpus || null,
        selection: currentSelection(),
        ts: Date.now(),
      }));
    }catch(e){ /* private-mode / quota — the echo just won't render next hop */ }
  }
  // bank the origin on the way OUT (pagehide fires on both nav and tab-close, more
  // reliable than unload); nav clicks that set location.href trip it too.
  let originWired = false;
  function wireOriginStamp(){
    if(originWired) return;
    originWired = true;
    window.addEventListener("pagehide", stampOrigin);
  }

  // render the echo into the header IF the stored origin is another surface, still fresh
  // (<5 min), and real. The echo is a real <a> back to exactly where you came from, plus a
  // × that removes it (and clears the origin — provenance is an offer, not a fixture).
  function renderEcho(ctx){
    let o = readOrigin();
    const freshSession = o && o.path && o.ts && (Date.now() - o.ts) <= ORIGIN_FRESH_MS;
    if(!freshSession){
      // COLD DEEP LINK (§10): no fresh session origin, but the URL may state its thread
      // with ?via= (a surface id or a path). Resolve it through the roster so a shared or
      // emailed link still offers a named door back to the thread it declares.
      const via = new URLSearchParams(location.search).get("via");
      const row = via
        ? (viewRow(via) || viewForPath(via.charAt(0) === "/" ? via : "/" + via))
        : null;
      if(!row) return;                          // no fresh origin and no resolvable via
      o = {path: viewHref(row.path), surface: row.id, selection: null, ts: Date.now()};
    }
    let oPath;
    try{ oPath = new URL(o.path, location.origin).pathname; }catch(e){ oPath = o.path; }
    if(oPath === location.pathname) return;    // same surface — Back stays honest, no echo
    // THE ORIGIN NAMES A SURFACE, NEVER A RAW PATH (finding 2): resolve through the roster
    // to journey vocabulary (the served alias resolves /project → "Machine"). A path that
    // resolves to no row yields NO door rather than leaking a raw path into the chrome.
    const fromRow = viewForPath(oPath) || (o.surface ? viewRow(o.surface) : null);
    const surfaceLabel = fromRow ? (fromRow.title || fromRow.id) : null;
    if(!surfaceLabel) return;
    const sel = o.selection && o.selection.val;
    const label = sel ? (sel + " · " + surfaceLabel) : String(surfaceLabel);
    const wrap = document.createElement("span");
    wrap.className = "hy-fromwrap";
    wrap.innerHTML =
      "<a class='hy-from' href='"+esc(o.path)+"'"+
      " title='"+esc(surfaceLabel)+" — where this landing came from; the door returns exactly'>"+
        "← from "+esc(label)+"</a>"+
      "<button type='button' class='hy-from-x' title='dismiss the arrival echo'>×</button>";
    ctx.appendChild(wrap);
    wrap.querySelector(".hy-from-x").addEventListener("click", e => {
      e.preventDefault();
      wrap.remove();
      try{ sessionStorage.removeItem(ORIGIN_KEY); }catch(err){}
    });
  }

  // ── D16 · RULE IN PLACE ────────────────────────────────────────────────────
  // hyRule.attach(el, ctx): mark a host rulable, inject the quiet ✎ chip. Click the chip →
  // an inline capture (textarea + bank + destination); bank POSTs the typed draft to the
  // friction ledger door and NEVER navigates. On 2xx+record → `banked ✓ <id>`; on failure →
  // the honest server error, his words KEPT in the textarea. Also event-delegated on the
  // .hy-rulable class, so a surface can raise the mouth with markup alone.
  const RULE_CTX = new WeakMap();
  // the friction ledger's HTTP write door (scanner.py do_POST → corpus_ingest.friction_add):
  // the ONE sanctioned gate for friction/fork records — typed, draft-only (status: open),
  // never a bare append. A fork is an author decision the machine cannot make; the capture
  // is exactly that, banked where the drain already reads.
  const RULE_ENDPOINT = "/corpus/friction";
  let ruleDelegated = false;

  const hyRule = {
    attach: function(el, ctx){
      if(!el || el.__hyRuled) return;
      el.__hyRuled = true;
      el.classList.add("hy-rulable");
      RULE_CTX.set(el, ctx || {});
      if(!el.querySelector(":scope > .rule-chip")){
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "rule-chip";
        chip.title = "rule right here — banks to the friction ledger, draft-only (D16)";
        chip.innerHTML = "&#9998; rule";
        el.appendChild(chip);
      }
      ensureRuleDelegate();
    },
  };

  function ensureRuleDelegate(){
    if(ruleDelegated) return;
    ruleDelegated = true;
    document.addEventListener("click", e => {
      const bank = e.target.closest && e.target.closest(".rule-bank");
      if(bank){ e.preventDefault(); ruleBank(bank.closest(".rule-cap")); return; }
      const chip = e.target.closest && e.target.closest(".rule-chip");
      if(chip){ e.preventDefault(); ruleOpen(chip.closest(".hy-rulable")); return; }
    });
  }

  function ruleOpen(host){
    if(!host) return;
    let cap = host.querySelector(":scope > .rule-cap");
    if(cap){
      const on = cap.classList.toggle("on");
      host.classList.toggle("rule-open", on);
      if(on){ const ta = cap.querySelector("textarea"); if(ta) ta.focus(); }
      return;
    }
    cap = document.createElement("div");
    cap.className = "rule-cap on";
    cap.innerHTML =
      "<textarea placeholder='rule on this — banks draft-only to the friction ledger'></textarea>"+
      "<div class='rule-row'>"+
        "<button type='button' class='rule-bank'>bank</button>"+
        "<span class='rule-dest'>→ friction ledger · draft-only</span>"+
        "<span class='rule-msg'></span>"+
      "</div>";
    host.appendChild(cap);
    host.classList.add("rule-open");
    const ta = cap.querySelector("textarea");
    if(ta) ta.focus();
  }

  function ruleMsg(cap, text, bad){
    const m = cap.querySelector(".rule-msg");
    if(m){ m.textContent = text; m.classList.toggle("bad", !!bad); }
  }

  function ruleBank(cap){
    if(!cap) return;
    const host = cap.closest(".hy-rulable");
    const ctx = (host && RULE_CTX.get(host)) || {};
    const ta = cap.querySelector("textarea");
    const btn = cap.querySelector(".rule-bank");
    const text = ta ? ta.value.trim() : "";
    if(!text){ if(ta) ta.focus(); ruleMsg(cap, "type a rule first", true); return; }
    if(btn) btn.disabled = true;
    ruleMsg(cap, "banking…", false);
    const cur = new URLSearchParams(location.search).get("corpus") || corpus || "";
    const surface = ctx.surface || activeView() || location.pathname;
    const payload = {
      kind: "fork", owning_layer: "interface", by: "author",
      corpus: cur,
      node: ctx.node || ("surface:" + surface),
      value: text, text: text, surface: surface,
      ctx: {project: cur || null, selection: ctx.selection || null,
            purpose: ctx.purpose || "", path: location.pathname + location.search},
      ts: new Date().toISOString(),
    };
    fetch(RULE_ENDPOINT, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    }).then(r => r.text().then(t => {
      let j = {}; try{ j = JSON.parse(t) || {}; }catch(e){}
      return {ok: r.ok, status: r.status, j};
    })).then(res => {
      const rec = res.j && res.j.record;
      if(res.ok && !res.j.error && rec && rec.id){
        cap.innerHTML = "<span class='rule-banked'>banked ✓ "+esc(rec.id)+
          " — typed, draft-only; drains through the evidence door</span>";
        if(host) host.classList.remove("rule-open");
      }else{
        // honest failure — his words stay in the textarea, never lost
        const err = (res.j && res.j.error) || ("bank failed (HTTP "+res.status+")");
        ruleMsg(cap, err, true);
        if(btn) btn.disabled = false;
      }
    }).catch(e => {
      ruleMsg(cap, "offline — not banked (your words are kept): "+String(e && e.message || e), true);
      if(btn) btn.disabled = false;
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // ── LADDER-COMPONENT-START (W0.5) — THE LADDER (client). The selection token is
  //    the trigger; the anchored .hy-ladder popover holds six rungs over ONE target
  //    (concept·argument·prose·evidence·judgment·machine). Every string below is
  //    bound by the text law — a fact, a count, a reason, a route, or a state.
  //    Server-authored strings (rung labels, subs, absence reasons, fix labels,
  //    stale reasons) ride the payload; only the loading line, the failure text, the
  //    retry, the close/aria titles, and the truncation foot are client-authored.
  // ═══════════════════════════════════════════════════════════════════════════
  let LADDER_EL = null;            // the popover (built once, reused)
  const LADDER_CACHE = {};         // "corpus\0kind\0target" -> payload (SUCCESSES ONLY)
  let LADDER_ANCHOR = null;        // the trigger element — refocus target on close
  let LADDER_ABORT = null;         // the in-flight AbortController (10s / superseded / close)
  let ladderRungEls = [];          // the rung elements in order (↑/↓ + Enter)
  let ladderActive = -1;           // the active rung index (aria-activedescendant)
  let ladderKeyWired = false;
  let ladderPopWired = false;

  // repair the header's selection token to the LIVE URL (SPA store.set moves the URL
  // without a reload — the token would otherwise lie). Called on open + popstate.
  function refreshSelToken(){
    const ctx = document.getElementById("hy-context");
    if(!ctx) return;
    const cur = new URLSearchParams(location.search).get("corpus") || corpus || "";
    const proj = ctx.querySelector(".hy-ctx-proj");
    if(proj && !proj.classList.contains("is-scope") && cur){
      const first = proj.firstChild;                       // the leading text node (caret follows)
      if(first && first.nodeType === 3) first.nodeValue = cur;
    }
    const wrap = ctx.querySelector(".hy-ctx-selwrap");
    if(wrap){
      const sel = currentSelection();
      const valEl = wrap.querySelector(".hy-ctx-sel-val");
      if(sel){ if(valEl) valEl.textContent = sel.val; wrap.hidden = false; }
      else { wrap.hidden = true; }
    }
  }

  function ensureLadderPopstate(){
    if(ladderPopWired) return;
    ladderPopWired = true;
    window.addEventListener("popstate", () => refreshSelToken());
  }

  // wire the header token triggers: click / Enter / Space / ↓ opens; the target is read
  // LIVE at fire (never a stale dataset) — role names which token, openLadder resolves it.
  function wireLadderTriggers(ctx){
    ensureLadderPopstate();
    ctx.querySelectorAll(".hy-ctx-ladder").forEach(btn => {
      const fire = () => openLadder({role: btn.dataset.role, anchorEl: btn});
      btn.addEventListener("click", e => { e.preventDefault(); e.stopPropagation(); fire(); });
      btn.addEventListener("keydown", e => {
        if(e.key === "Enter" || e.key === " " || e.key === "ArrowDown"){ e.preventDefault(); fire(); }
      });
    });
  }

  function ensureLadderEl(){
    if(LADDER_EL) return LADDER_EL;
    const el = document.createElement("div");
    el.className = "hy-ladder";
    el.id = "hy-ladder";
    el.setAttribute("role", "dialog");
    document.body.appendChild(el);
    // outside-click closes (open/close is NOT a navigation — no origin stamp fires)
    document.addEventListener("click", e => {
      if(!el.classList.contains("open")) return;
      if(el.contains(e.target)) return;
      if(e.target.closest && e.target.closest(".hy-ctx-ladder")) return;   // the trigger toggles itself
      closeLadder();
    });
    ensureLadderKeys();
    LADDER_EL = el;
    return el;
  }

  // the keyboard, CAPTURE-PHASE: Escape closes the ladder BEFORE the rail (topmost-transient
  // law — stopPropagation so the rail's bubble-phase Escape never sees it); ↑/↓ move the
  // active rung; Enter follows the active rung's door (the fix door when the rung is absent).
  function ensureLadderKeys(){
    if(ladderKeyWired) return;
    ladderKeyWired = true;
    document.addEventListener("keydown", e => {
      if(!LADDER_EL || !LADDER_EL.classList.contains("open")) return;
      if(e.key === "Escape"){
        e.stopPropagation(); e.preventDefault();
        closeLadder(true);
      } else if(e.key === "ArrowDown" || e.key === "ArrowUp"){
        if(!ladderRungEls.length) return;
        e.preventDefault(); e.stopPropagation();
        const d = e.key === "ArrowDown" ? 1 : -1;
        let i = ladderActive < 0 ? (d > 0 ? 0 : ladderRungEls.length - 1) : ladderActive + d;
        setLadderActive(Math.max(0, Math.min(ladderRungEls.length - 1, i)));
      } else if(e.key === "Enter"){
        if(ladderActive < 0) return;
        e.preventDefault(); e.stopPropagation();
        const rung = ladderRungEls[ladderActive];
        const door = rung.matches("a.hy-ladder-rung") ? rung
          : rung.querySelector("a.hy-ladder-fix, button.hy-ladder-fix");
        if(door) door.click();     // a real <a> nav (or the judgment ✎ button) — the door acts
      }
    }, true);
  }

  function setLadderActive(i){
    ladderActive = i;
    const box = LADDER_EL.querySelector(".hy-ladder-rungs");
    ladderRungEls.forEach((el, k) => {
      const on = k === i;
      el.classList.toggle("active", on);
      el.setAttribute("aria-selected", on ? "true" : "false");
    });
    const active = ladderRungEls[i];
    if(box && active){ box.setAttribute("aria-activedescendant", active.id); active.scrollIntoView({block: "nearest"}); }
  }

  // anchor the popover under the trigger; clamp the left so it never spills the right edge.
  function positionLadder(anchorEl){
    const el = LADDER_EL;
    const vw = window.innerWidth, m = 8;
    let top = 48, left = m;
    if(anchorEl && anchorEl.getBoundingClientRect){
      const r = anchorEl.getBoundingClientRect();
      top = Math.round(r.bottom + 4); left = Math.round(r.left);
    }
    el.style.top = top + "px";
    const w = el.offsetWidth || 360;
    el.style.left = Math.max(m, Math.min(left, vw - w - m)) + "px";
  }

  // OPEN the ladder over a target. role="sel"|"project" resolve LIVE from the URL; an
  // explicit {target,kind} (the find-row glyph, external callers) rides through unchanged.
  function openLadder(opts){
    opts = opts || {};
    refreshSelToken();
    const cur = new URLSearchParams(location.search).get("corpus") || corpus || "";
    let target = opts.target || "", kind = opts.kind || "";
    if(opts.role === "project"){ target = cur; kind = "project"; }
    else if(opts.role === "sel"){ const s = currentSelection(); if(!s) return; target = s.val; kind = s.key; }
    const anchorEl = opts.anchorEl || null;
    // clicking the SAME trigger again closes (a toggle)
    if(LADDER_EL && LADDER_EL.classList.contains("open") && anchorEl && LADDER_ANCHOR === anchorEl){
      closeLadder(true); return;
    }
    const el = ensureLadderEl();
    if(LADDER_ANCHOR && LADDER_ANCHOR !== anchorEl) LADDER_ANCHOR.setAttribute("aria-expanded", "false");
    LADDER_ANCHOR = anchorEl;
    if(anchorEl) anchorEl.setAttribute("aria-expanded", "true");
    el.setAttribute("aria-label", (target || cur || "project") + " ladder — six altitudes");
    ladderRungEls = []; ladderActive = -1;
    el.innerHTML = "<div class='hy-ladder-loading'>reading the six rungs…</div>";
    el.classList.add("open");
    positionLadder(anchorEl);
    loadLadder(cur, target, kind, anchorEl);
  }

  // the lazy fetch — only on open, cache keyed corpus\0kind\0target, successes only. A 404
  // relays the server's unknown-project body + a door to /; every other failure is an honest
  // in-panel card (timeout at 10s, retry) — never a blank, never a false empty.
  async function loadLadder(corpusName, target, kind, anchorEl){
    const el = LADDER_EL;
    const key = corpusName + "\0" + kind + "\0" + (target || "");
    if(LADDER_ABORT){ try{ LADDER_ABORT.abort(); }catch(e){} LADDER_ABORT = null; }
    if(Object.prototype.hasOwnProperty.call(LADDER_CACHE, key)){
      renderLadder(el, LADDER_CACHE[key], corpusName, anchorEl); return;
    }
    const ctrl = new AbortController();
    LADDER_ABORT = ctrl;
    const timer = setTimeout(() => { try{ ctrl.abort(); }catch(e){} }, 10000);
    const url = "/shared/ladder?corpus="+ec(corpusName)+"&target="+ec(target || "")+"&kind="+ec(kind || "");
    try{
      const r = await fetch(url, {signal: ctrl.signal});
      clearTimeout(timer);
      if(ctrl !== LADDER_ABORT) return;                      // superseded by a newer open
      if(r.status === 404){
        let body = {}; try{ body = await r.json(); }catch(e){}
        renderLadderNotFound(el, body); return;
      }
      if(!r.ok){ renderLadderFail(el, {status: r.status, corpus: corpusName, target, kind}); return; }
      const payload = await r.json();
      LADDER_CACHE[key] = payload;                           // successes only
      renderLadder(el, payload, corpusName, anchorEl);
    }catch(e){
      clearTimeout(timer);
      if(ctrl !== LADDER_ABORT) return;                      // superseded or closed — no render
      renderLadderFail(el, {status: 0, timeout: !!(e && e.name === "AbortError"),
        corpus: corpusName, target, kind});
    }
  }

  function renderRung(r){
    const id = "hy-rung-" + r.id;
    const label = "<span class='hy-ladder-rlabel'>"+esc(r.label || r.id)+"</span>";
    const cnt = "<span class='hy-ladder-count"+(r.count ? "" : " is-zero")+"'>"+esc(String(r.count))+"</span>";
    const stale = r.stale
      ? "<span class='hy-ladder-stale hy-chip is-warn' title='"+esc(r.stale.fix || "")+"'>"+
          esc(r.stale.reason || "")+"</span>"
      : "";
    if(r.present){
      return "<a class='hy-ladder-rung' role='option' id='"+id+"' aria-selected='false' href='"+
        esc(r.href)+"'>"+label+cnt+"<span class='hy-ladder-sub'>"+esc(r.sub || "")+"</span>"+stale+"</a>";
    }
    const a = r.absent || {};
    // the judgment fix RULES the target — it fires the head ✎ (the D16 POST bank), never a
    // GET-navigation to /corpus/friction (that route dumps JSON and banks nothing). Every
    // other fix is a real <a> into the surface whose banked verb owns the work.
    const fixEl = r.id === "judgment"
      ? "<button type='button' class='hy-ladder-fix is-rule'>"+esc(a.fix || "")+"</button>"
      : "<a class='hy-ladder-fix' href='"+esc(a.fix_href || "")+"'>"+esc(a.fix || "")+"</a>";
    return "<div class='hy-ladder-rung is-absent' role='option' id='"+id+"' aria-selected='false'>"+
      label+cnt+"<span class='hy-ladder-sub'>"+esc(a.reason || "")+"</span>"+
      fixEl+stale+"</div>";
  }

  function renderLadder(el, payload, corpusName, anchorEl){
    if(!el.classList.contains("open")) return;
    const t = payload.target || {};
    const kindChip = "<span class='hy-ladder-kind hy-chip'>"+esc(t.kind || "")+"</span>";
    const unresolved = t.known === false
      ? "<span class='hy-ladder-kind hy-chip is-warn'"+
        " title='this target resolves to nothing — the rungs name where to place it'>unresolved</span>"
      : "";
    const head =
      "<div class='hy-ladder-head hy-rulable'>"+
        "<span class='hy-ladder-target'>"+esc(t.label || t.raw || corpusName)+"</span>"+
        kindChip + unresolved +
        "<button type='button' class='rule-chip'"+
          " title='rule on this target — banks a fork to the friction ledger'>&#9998; rule</button>"+
        "<button type='button' class='hy-ladder-x' title='close (Esc)'>×</button>"+
      "</div>";
    const foot = payload.truncated
      ? "<div class='hy-ladder-foot'>showing ≤6 per rung — "+(payload.omitted || 0)+
        " exemplar(s) shed (16KB budget)</div>"
      : "";
    el.innerHTML = head +
      "<div class='hy-ladder-rungs' role='listbox' aria-label='six altitudes' aria-activedescendant=''>"+
        (payload.rungs || []).map(renderRung).join("")+
      "</div>" + foot;
    // the ✎ head mouth (D16): banks ladder:<target> forks through /corpus/friction — the
    // pre-placed .rule-chip means attach wires the ctx without appending a second chip.
    hyRule.attach(el.querySelector(".hy-ladder-head"), {
      surface: activeView() || "ladder", title: (t.label || t.raw || corpusName),
      project: corpusName, selection: {key: t.kind, val: t.raw},
      node: "ladder:" + (t.raw || corpusName),
    });
    el.querySelector(".hy-ladder-x").addEventListener("click", () => closeLadder(true));
    // the judgment absent-fix fires the head ✎ (opens the D16 capture over this target) —
    // the same mouth hyRule.attach wired to the .rule-chip; no navigation, banks a fork.
    const ruleFix = el.querySelector(".hy-ladder-fix.is-rule");
    if(ruleFix){
      const chip = el.querySelector(".rule-chip");
      ruleFix.addEventListener("click", e => { e.preventDefault(); if(chip) chip.click(); });
    }
    ladderRungEls = Array.prototype.slice.call(el.querySelectorAll(".hy-ladder-rung"));
    ladderActive = -1;
    positionLadder(anchorEl);
  }

  function renderLadderFail(el, info){
    if(!el.classList.contains("open")) return;
    const what = info.timeout ? "the ladder read timed out after 10s"
      : (info.status ? "the ladder read failed (HTTP "+info.status+")"
                     : "the ladder read did not return");
    el.innerHTML =
      "<div class='hy-ladder-head'>"+
        "<span class='hy-ladder-target'>"+esc(info.target || info.corpus || "")+"</span>"+
        "<button type='button' class='hy-ladder-x' title='close (Esc)'>×</button>"+
      "</div>"+
      "<div class='hy-ladder-fail'>"+
        "<div class='hy-ladder-fail-msg'>"+esc(what)+"</div>"+
        "<button type='button' class='hy-ladder-retry'>retry</button>"+
      "</div>";
    el.querySelector(".hy-ladder-x").addEventListener("click", () => closeLadder(true));
    el.querySelector(".hy-ladder-retry").addEventListener("click", () => {
      el.innerHTML = "<div class='hy-ladder-loading'>reading the six rungs…</div>";
      loadLadder(info.corpus, info.target, info.kind, LADDER_ANCHOR);
    });
    ladderRungEls = []; ladderActive = -1;
    positionLadder(LADDER_ANCHOR);
  }

  function renderLadderNotFound(el, body){
    if(!el.classList.contains("open")) return;
    const msg = (body && body.error) || "no project for this corpus";
    el.innerHTML =
      "<div class='hy-ladder-head'>"+
        "<button type='button' class='hy-ladder-x' title='close (Esc)'>×</button>"+
      "</div>"+
      "<div class='hy-ladder-fail'>"+
        "<div class='hy-ladder-fail-msg'>"+esc(msg)+"</div>"+
        "<a class='hy-ladder-fix' href='/'>open the dashboard</a>"+
      "</div>";
    el.querySelector(".hy-ladder-x").addEventListener("click", () => closeLadder(true));
    ladderRungEls = []; ladderActive = -1;
    positionLadder(LADDER_ANCHOR);
  }

  function closeLadder(refocus){
    if(LADDER_ABORT){ try{ LADDER_ABORT.abort(); }catch(e){} LADDER_ABORT = null; }
    if(LADDER_EL) LADDER_EL.classList.remove("open");
    if(LADDER_ANCHOR){
      LADDER_ANCHOR.setAttribute("aria-expanded", "false");
      if(refocus && LADDER_ANCHOR.focus){ try{ LADDER_ANCHOR.focus(); }catch(e){} }
    }
    ladderRungEls = []; ladderActive = -1;
  }
  // ── LADDER-COMPONENT-END ────────────────────────────────────────────────────

  // ═══════════════════════════════════════════════════════════════════════════
  // ── TUTORIAL-OVERLAY-START (W8) — THE IN-PLACE GUIDED TOUR.
  //    The old /guide explainer + /tutorial PAGE died in the face rewrite (their desk
  //    rehoused to /desk); this resurrects NO route. It is a walkthrough LAYERED over
  //    the LIVE surface: the '? tour' chip in the chrome opens it, one step at a time,
  //    each SPOTLIGHTING a real element (a ring + a backdrop dimmed to it, scrolled into
  //    view) beside a card naming three things honestly — what this is, where its data
  //    comes from (the endpoint/organ), and what acting on it does (incl. the law
  //    semantics that surprise: model-heavy BANKS a work-order; ratify is arm-then-apply
  //    with a 30s disarm; an empty panel usually means the corpus selector).
  //
  //    It DESCRIBES — zero fetch, zero mutation. Steps are an authored per-route table
  //    keyed by the roster view id (activeView()). GRACEFUL ABSENCE: a step whose
  //    selector matches nothing is SKIPPED and the counter stays honest ("3 of 7");
  //    a surface with no matches at all says so plainly. The step is remembered per
  //    route in sessionStorage (by title) so reopening resumes. Esc closes; ←/→ move.
  // ═══════════════════════════════════════════════════════════════════════════

  // the shared-chrome steps — the bar rides every surface, so they lead every tour.
  const TOUR_SHARED = [
    { selector: "#hy-shell", title: "the journey — this chrome rides every surface",
      body: "the spine reads the process a paper walks: <b>Grow → Shape → Read · Judge → "+
        "Machine</b>, with Home and Desk at the ends. each stage wears its live state in "+
        "small type; hover a stage for what it is and the doors it holds; the lit stage is "+
        "where you are standing. <b>switch project…</b> hops between papers; <b>find…</b> "+
        "searches nodes in the project in view." },
    { selector: ".hy-context", title: "where you are — and the ladder",
      body: "names this surface, the project in view, and the current selection. the <b>▾</b> on a "+
        "token opens the six-rung ladder — one target seen at concept · argument · prose · evidence "+
        "· judgment · machine altitude (<code>/shared/ladder</code>, pure read). <b>✎ rule</b> banks "+
        "a note to the friction ledger, draft-only — it fires nothing." },
  ];

  // the per-route tables (keyed by the roster view id, i.e. activeView()). Each step:
  // {selector, title, body}. Selectors are pointed at the ids/classes the panes render
  // TODAY; steps whose anchor is absent (a mode-specific element behind a summon, a
  // pane mid-churn) SKIP gracefully (tourVisible), so the tour never re-stubs to the
  // chrome. Each rostered surface leads with a container present at rest (#eng-root /
  // #dash-live / #art-reader …) so the walk always exceeds the 2 shared steps.
  const TOUR_ROUTES = {
    walk: [
      { selector: "#doc", title: "the content-faithful canvas",
        body: "the paper as content — math, citations and figures rendered, every block " +
          "carrying its source span. click into a paragraph and TYPE: the edit banks " +
          "through the rewrite door on pause; a floating card at the caret names the " +
          "source lines, takes the altitude, and shows the receipt." },
      { selector: "#spine", title: "the spine",
        body: "sections with coverage tints and deposit badges. click a row to jump " +
          "(the scroll runs continuously — direction and distance kept); shift-click " +
          "extends a span for a structural deposit." },
      { selector: "#rail", title: "the linkages pane and the session band",
        body: "the right rail at rest is a slim strip; opened, it shows the current " +
          "section's linkages — beats, nodes, refs — and this walk's own deposits. " +
          "it opens on your click and in the frame of a bank, never on its own." },
    ],
    dashboard: [
      { selector: "#eng-root", title: "the composed brief of the whole",
        body: "the resting altitude — the delta-and-ask across every project, in one glance, before "+
          "you open a single card. read live from <code>/dashboard/data</code>." },
      { selector: "#dash-live", title: "every project, at a glance",
        body: "one card per project — its release state, its position in the pipeline, its one next "+
          "action. click a card to open that paper (the corpus rides with you across every view)." },
      { selector: "#scaffold-strip", title: "scaffolds — start from a shape",
        body: "the new-paper scaffolds: a shape to begin from, rather than a blank page. picking one "+
          "seeds the stock the rest of the pipeline descends." },
      { selector: "#newproj", title: "a new project, from nothing",
        body: "opens the New Project door in place — a name and a template. creating it mints a "+
          "conceptric; it appears on the live board above with state <b>never run</b> until the "+
          "machine first touches it." },
    ],
    conceptric: [
      { selector: "#eng-root", title: "the growth brief — where this project stands",
        body: "the resting altitude of the growth cockpit: the goal, the ladder rung, the open "+
          "tensions and coverage — the one decision waiting on you, and why. materialised behind "+
          "one open, never all at once." },
      { selector: ".ck-shape, .ck-shape-station", title: "the shape — tensions and stations",
        body: "the argument's shape at a glance: the stations it passes through and the tensions "+
          "still open. a tension is a four-verb decision; ruling it is where growth happens." },
      { selector: ".ck-count", title: "counts that materialise on open",
        body: "queues, coverage, the ladder — each a one-line count that expands its rows in place "+
          "when you open it. nothing heavy loads until you ask for it." },
      { selector: ".ck-door", title: "the doors into the work",
        body: "the doors this brief keeps — into the stock map (<code>/conceptric/map</code>, the "+
          "graded descent you read and quarry), the storyboard, the artefact." },
      // the stock-map door (/conceptric/map) shares this route id — its anchors light there
      { selector: "#cx-strata", title: "the stock as graded descent",
        body: "the corpus sliced by grade — the goal at the top, the spine beneath, the fine nodes "+
          "below. click a grade to load that stratum into the board." },
      { selector: "#cx-board", title: "the node cards",
        body: "each node with its essence. <b>↑ fold</b> folds it into its parent, <b>↓ open</b> opens "+
          "its constituents — you walk the graph in place, with the evidence lane and the “argues in” "+
          "doors on each card." },
      { selector: "#cx-find-in", title: "find within this corpus",
        body: "a lexical, local filter over the nodes in view — fewer letters, more hits. it narrows "+
          "the board; it does not fetch or grade." },
    ],
    lineage: [
      { selector: ".lin-glance", title: "the lineage brief — how this paper links across the map",
        body: "the resting altitude: a composed reading of how many concepts the paper holds, how "+
          "many reached the manuscript, and how many rendered objects trace their origin. read live "+
          "from <code>/lineage/brief</code>." },
      { selector: ".lin-band", title: "the unresolved band, stated",
        body: "the objects the concept graph does not yet place — paragraphs that realise no concept, "+
          "figures nothing claims — counted with their reason. absence is a first-class citizen here, "+
          "never hidden." },
      { selector: "#lin-pick-node", title: "a concept, outward",
        body: "pick a concept and see everything it became: its descendants tree, the sections it "+
          "touches, and the paragraphs and equations that realise it — each with its join provenance "+
          "worded. doors carry you into the editor and the growth cockpit." },
      { selector: "#lin-pick-obj", title: "a rendered object, backward",
        body: "pick an equation or figure and walk it back through its chain — paragraph, concept, and "+
          "the derivation origin where it was authored (the resolving rung)." },
      { selector: "#lin-pick-whole", title: "the whole graph",
        body: "the sections as regions weighted by how much realises in each, with the unresolved band "+
          "drawn as its own region." },
    ],
    storyboard: [
      { selector: "#eng-root", title: "the storyboard brief — what is planned, what moved",
        body: "the resting altitude: what the spine plans, what has moved since you last looked, and "+
          "the one thing that needs you. the board materialises when you summon it." },
      { selector: ".sb-decision", title: "the one decision that needs you",
        body: "the single structural decision the storyboard surfaces first — summon it to open its "+
          "rows in place. a storyboard with nothing owed stays quiet." },
      { selector: "#sb-mat", title: "the spine, materialised",
        body: "the sections as a board — their weight and order, planned and edited in place. this is "+
          "the narrative structure; edit here and the projection plan moves with it." },
      { selector: ".sb-cards", title: "the sections as cards",
        body: "one card per section; each expands to plan and realise its prose. the load-bearing "+
          "order is argumentative weight, not page order." },
      { selector: ".sb-railcov", title: "coverage — planned vs realised",
        body: "how much of the planned spine is realised, both directions. a read, never a gate: it "+
          "tells you where prose is still owed." },
      { selector: "#sb-run-host", title: "the run pane — where the law bites",
        body: "the run's live state and the launch doors. the profile rides every launch. <b>local-safe</b> "+
          "fires the real executor (a dry-run first, then arm); <b>model-heavy</b> banks a work-order — "+
          "the offer law: nothing runs now, it fires the next remote session, no tokens spent here." },
    ],
    artefact: [
      { selector: "#art-reader", title: "the artefact, rendered",
        body: "the real compiled PDF via vendored pdf.js — the current version, or any revision the rail "+
          "loads. this one surface is the reader, annotator and editor over the artefact." },
      { selector: "#art-rail", title: "the version rail, standing",
        body: "every snapshot, round and release down the side. click one to load that revision into the "+
          "reader without leaving — the history is a place you read from, not a detour." },
      { selector: "#art-tray-sec", title: "the findings tray",
        body: "node-precise findings on this artefact. each expands into the same cockpit the desk uses — "+
          "context, consequences, tools — so a finding is ruled where you read it. a destructive verb "+
          "arms before it fires." },
      { selector: "#art-edit-toggle", title: "edit in place",
        body: "switches into edit mode over the artefact source — save writes, recompile re-renders. the "+
          "reader, the rail and the editor are three modes of one surface, not three pages." },
    ],
    desk: [
      { selector: ".dkb-prose", title: "what needs you now",
        body: "the desk rests at a composed brief — the decisions owed to you today, led by the one "+
          "that most matters and why. a desk with nothing owed says so in one line and stays quiet." },
      { selector: ".dkb-counts", title: "every summonable class",
        body: "one line per provenance store, with its open count. open a class to materialise its "+
          "rows; open a row to reallocate into its full cockpit in place — <b>context</b> (what it is), "+
          "<b>consequences</b> (what a ruling does), <b>tools</b> (every verb inline), <b>deep-links</b> "+
          "to the exact spot — with a named return door back to the brief. a destructive or applying "+
          "verb is <b>arm-then-fire</b>; nothing fires on a single click." },
    ],
    pipeline: [
      { selector: "#eng-root", title: "the project brief — where this paper sits",
        body: "the resting altitude of the Machine: the truthful state, the generation, the debt "+
          "trajectory and the next act — the composed brief before the chain materialises." },
      { selector: "#pipe-ladder", title: "the chain, from the state machine",
        body: "the ladder IS the release states — which passed, which is current, which lie ahead. no drawn "+
          "diagram: it renders straight from <code>/pipeline/chain</code>. this is the whole pipeline map." },
      { selector: "#pipe-cur", title: "where this project sits",
        body: "the current release state, named. the chain above is the road; this is the mile-marker the "+
          "project is standing on right now." },
      { selector: "#pipe-board", title: "the organ board",
        body: "one card per stage. click a card to expand it — its <b>dials in place</b>, its <b>dry-run</b> "+
          "'what would fire', and its <b>scoped arm/fire</b>. expand the converge stage and its inner cards "+
          "hold the evolution desk, the fitness panel and the run tray (reopen this tour and those steps "+
          "light up)." },
      { selector: ".hy-card[data-organ]", title: "an organ, opened",
        body: "expanding a stage shows its knobs and its verbs. a <b>dial edit</b> rides "+
          "<code>/dials/op</code> (the one write path, with undo); the <b>dry-run</b> is a pure read that "+
          "fires nothing; a <b>scoped fire</b> obeys the offer law — local-safe runs, model-heavy banks a "+
          "work-order." },
      { selector: ".pipe-runtray", title: "the run tray",
        body: "the converge stage's live run. the <b>profile rides every launch</b>. <b>local-safe</b> fires "+
          "the real executor; <b>model-heavy BANKS a work-order</b> (runs next remote session, no tokens "+
          "now) and lists it under open work orders. every fire dry-runs, then arms." },
      { selector: ".pipe-evo-list", title: "the evolution desk",
        body: "the ratify queue — drafted contracts waiting on your word. <b>ratify</b> is a deliberate "+
          "arm-then-apply: the first click previews, the second applies, with a <b>30s disarm countdown</b> "+
          "(Esc disarms too). under the <b>bulk-arm</b> dial the queue offers <b>ratify-all</b> — one armed "+
          "word applied per-item, each its own record. <b>hold</b> banks a typed defer; <b>reject</b> revokes "+
          "without applying. an empty queue here usually means the corpus selector — it names which other "+
          "project has open intents." },
      { selector: ".pipe-fit", title: "the fitness panel",
        body: "the debt trajectory, the freeze verdict, the mechround pre/post/Δ, the suite floor. "+
          "<b>readings only</b> — this panel has no controls; it watches the numbers, "+
          "it does not impose them." },
      { selector: ".pipe-sel", title: "the selection sheet",
        body: "each generation's readings + a <b>DRAFT verdict</b> — the versioned rule the sheet names "+
          "on its DRAFT chip, inspectable. its <b>reach gate</b> holds the aspiration + attested-chain "+
          "depth from falling, generation over generation. ψ/φ stay yours — your overrides are the "+
          "calibration signal." },
      { selector: ".pipe-sel-actions", title: "the rule door",
        body: "arm-then-bank with a <b>30s disarm</b>; agreeing ratifies, differing overrides; a ruled "+
          "generation is contested by a later record, never re-ruled." },
      { selector: ".pipe-der-claim", title: "the aspiration — the boundary condition",
        body: "the <b>maximal true claim</b>, asserted before achievability is known — the endpoint set "+
          "first, then the game is to build the chain to it. below it the <b>isnad</b>: each link "+
          "attested (a forged derivation, a computation, a cite) or a <b>NAMED gap</b>. reach is how far "+
          "UP the aspiration the attested chain got — the chain must actually be true." },
      { selector: ".pipe-der-actions", title: "the derivation doors",
        body: "<b>re-scope</b> the boundary claim is yours (the prior banks to history, arm-then-bank); a "+
          "<b>gap arms its next forging</b> (banks a model-heavy work-order — the offer law, nothing runs "+
          "now); a link can be <b>contested</b> by a later record (its status stays until re-attested). "+
          "open a forged derivation to read its <code>.tex</code> in place." },
      { selector: ".pipe-dials", title: "dials in place",
        body: "this organ's knobs, edited where it runs (<code>/dials/op</code>, with undo). a knob guarded "+
          "by a gate <b>refuses to arm</b> until its holdout gate passes — the dial cannot override the "+
          "gate, and it tells you why." },
    ],
    assets: [
      { selector: "#eng-root", title: "your assets, briefed",
        body: "every derivation and every figure gathered as an addressable object of work — the "+
          "resting brief, with the roster materialising behind one open." },
      { selector: "#as-mat", title: "every figure and derivation, materialised",
        body: "the assets as cards — the rendered figure or the derivation steps. pick one to open its "+
          "cockpit: step/panel-anchored assessment, a banked-edit door, and manifest-only regen." },
      { selector: ".as-fig", title: "the rendered figure, framed as an object",
        body: "the figure sits toned to paper and framed as an object on the desk — never a glaring "+
          "lightbox. its landings in the reader and its nodes in the conceptric are one click away." },
    ],
    analytics: [
      { selector: "#lt-board", title: "the loop census",
        body: "the convergence loop read across projects — closure vs discovery, round by round. a rollup "+
          "over the release machine's own records." },
      { selector: "#an-rollup", title: "the cross-project rollup",
        body: "convergence at a glance across every project — including never-run: a project the "+
          "machine has not touched reads as never-run, not as zero." },
      { selector: "#an-roster", title: "the per-project series",
        body: "each project's round series — the shape of its descent over time. a read; it fires nothing." },
    ],
    altitude: [
      { selector: "#shells", title: "one substrate, rising altitudes",
        body: "the grade shells — the same material seen from nodes up through grade-shells to spine, plan "+
          "and prose. a read-only network instrument." },
      { selector: "#ladder", title: "the altitude ladder",
        body: "the rungs you move between: each altitude is one view of the same substrate, opened at an "+
          "anchor and shiftable up or down." },
      { selector: "#up", title: "trace up · drill down",
        body: "<b>trace up</b> moves toward the prose skin; <b>drill down</b> moves toward the node "+
          "substrate. the substrate never changes — only the altitude you read it from." },
    ],
    guide: [
      { selector: "#gd-surfaces", title: "every surface, and what it does",
        body: "the per-surface account, rendered FROM the operating contract "+
          "(<code>contract/surfaces/*.yaml</code>) so it cannot drift from behaviour: what each "+
          "surface is for, and for every verb what it writes, its cost, and its PSU class." },
      { selector: "#gd-story", title: "the session story",
        body: "what this session has done and where it stands — the account read straight off the "+
          "engine's own record, not a hand-kept log." },
      { selector: "#gd-promises", title: "the open promises, both directions",
        body: "what the engine still owes and what it is owed — the open work orders and intents, "+
          "so nothing outstanding hides." },
    ],
    map: [
      { selector: "#ringbar", title: "the firing ring",
        body: "the engine's own reconstruction network — the brain scanner. the ring shows the firing "+
          "front: goal, pull, fire. this is a view of the ENGINE, not of any one paper." },
      { selector: "#stage", title: "the live graph",
        body: "the reconstruction network drawn live — nodes and their wiring as the engine rebuilds "+
          "itself. rebuilt in seconds from JSON; a view, never an edit surface." },
      { selector: "#births", title: "the growth pulse",
        body: "new nodes as they arrive — the growth pulse of the network. it reads the same graph the "+
          "firing ring does, from the birth side." },
    ],
  };

  function tourStepsFor(route){
    return TOUR_SHARED.concat(TOUR_ROUTES[route] || []);
  }

  let TOUR = null;   // {route, steps(visible), i, spot, card, onMove, onKey}

  function tourVisible(steps){
    return steps.filter(s => { try{ return !!document.querySelector(s.selector); }catch(e){ return false; } });
  }

  // OPEN the tour for the current surface. Filters the authored steps to those whose
  // anchor is actually on screen (graceful absence), resumes the remembered step, and
  // mounts the spotlight + card. A surface with NO matching anchors says so plainly.
  function startTour(){
    ensureTourCss();
    if(TOUR){ closeTour(); return; }                 // the chip toggles
    const route = activeView() || "";
    const visible = tourVisible(tourStepsFor(route));
    if(!visible.length){ openTourEmpty(); return; }
    let i = 0;
    try{
      const saved = sessionStorage.getItem("hymn.tour." + route);
      if(saved){ const k = visible.findIndex(s => s.title === saved); if(k >= 0) i = k; }
    }catch(e){ /* private-mode — start at 0 */ }
    mountTour(route, visible, i);
    showTourStep();
  }

  function mountTour(route, visible, i){
    const spot = document.createElement("div"); spot.className = "hy-tour-spot";
    const card = document.createElement("div");
    card.className = "hy-tour-card"; card.setAttribute("role", "dialog");
    card.setAttribute("aria-label", "guided tour");
    document.body.appendChild(spot); document.body.appendChild(card);
    const onMove = () => { if(TOUR) positionTour(); };
    const onKey = e => {
      if(!TOUR) return;
      if(e.key === "Escape"){ e.preventDefault(); e.stopPropagation(); closeTour(); }
      else if(e.key === "ArrowRight" || e.key === "Enter"){ e.preventDefault(); e.stopPropagation(); tourGo(1); }
      else if(e.key === "ArrowLeft"){ e.preventDefault(); e.stopPropagation(); tourGo(-1); }
    };
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    document.addEventListener("keydown", onKey, true);
    TOUR = { route, steps: visible, i, spot, card, onMove, onKey };
  }

  // the empty-surface card: no spot, a plain centred panel. Honest — the tour anchors to
  // live elements and none are on screen (never a blank spotlight).
  function openTourEmpty(){
    const card = document.createElement("div");
    card.className = "hy-tour-card"; card.setAttribute("role", "dialog");
    card.style.left = "50%"; card.style.top = "80px"; card.style.transform = "translateX(-50%)";
    card.innerHTML =
      "<div class='tc-title'>nothing to point at here yet</div>"+
      "<div class='tc-body'>the tour anchors to live elements on this surface, and none are on "+
        "screen right now — the surface may still be loading, or empty for the project in view. "+
        "pick a project in the bar and reopen.</div>"+
      "<div class='tc-foot'><span class='tc-count'></span>"+
        "<button type='button' class='hy-tour-nav is-primary' data-tour='close'>close</button></div>";
    document.body.appendChild(card);
    const onKey = e => { if(e.key === "Escape"){ e.preventDefault(); closeTour(); } };
    document.addEventListener("keydown", onKey, true);
    TOUR = { route: "", steps: [], i: 0, spot: null, card, onMove: null, onKey };
    card.querySelector("[data-tour='close']").addEventListener("click", closeTour);
  }

  function showTourStep(){
    if(!TOUR || !TOUR.steps.length) return;
    if(TOUR.i < 0) TOUR.i = 0;
    if(TOUR.i >= TOUR.steps.length) TOUR.i = TOUR.steps.length - 1;
    // re-verify the anchor is still live (a fold may have closed since open); drop it and
    // re-show if it vanished, keeping the counter honest.
    let el = null;
    try{ el = document.querySelector(TOUR.steps[TOUR.i].selector); }catch(e){ el = null; }
    if(!el){
      TOUR.steps.splice(TOUR.i, 1);
      if(!TOUR.steps.length){ closeTour(); return; }
      if(TOUR.i >= TOUR.steps.length) TOUR.i = TOUR.steps.length - 1;
      return showTourStep();
    }
    const step = TOUR.steps[TOUR.i];
    try{ sessionStorage.setItem("hymn.tour." + TOUR.route, step.title); }catch(e){}
    try{ el.scrollIntoView({ block: "center", inline: "nearest" }); }catch(e){}
    const last = TOUR.i === TOUR.steps.length - 1;
    TOUR.card.innerHTML =
      "<div class='tc-title'>"+esc(step.title)+"</div>"+
      "<div class='tc-body'>"+step.body+"</div>"+          // body is authored trusted markup
      "<div class='tc-foot'>"+
        "<span class='tc-count'>"+(TOUR.i + 1)+" of "+TOUR.steps.length+"</span>"+
        "<button type='button' class='hy-tour-nav' data-tour='back'"+(TOUR.i === 0 ? " disabled" : "")+">back</button>"+
        "<button type='button' class='hy-tour-nav is-primary' data-tour='next'>"+(last ? "done" : "next")+"</button>"+
        "<button type='button' class='hy-tour-x' data-tour='close' title='close (Esc)'>×</button>"+
      "</div>"+
      "<div class='hy-tour-esc'><b>←</b>/<b>→</b> move · <b>Esc</b> closes</div>";
    TOUR.card.querySelector("[data-tour='back']").addEventListener("click", () => tourGo(-1));
    TOUR.card.querySelector("[data-tour='next']").addEventListener("click", () => tourGo(1));
    TOUR.card.querySelector("[data-tour='close']").addEventListener("click", closeTour);
    // position after layout settles (scrollIntoView + card reflow)
    requestAnimationFrame(positionTour);
  }

  function tourGo(delta){
    if(!TOUR || !TOUR.steps.length) return;
    if(delta > 0 && TOUR.i === TOUR.steps.length - 1){ closeTour(); return; }   // 'done'
    TOUR.i = Math.max(0, Math.min(TOUR.steps.length - 1, TOUR.i + delta));
    showTourStep();
  }

  // place the ring over the anchor and the card beside it (below if it fits, else above),
  // clamped to the viewport. Fixed coords match getBoundingClientRect (viewport-relative).
  function positionTour(){
    if(!TOUR || !TOUR.spot || !TOUR.steps.length) return;
    let el = null;
    try{ el = document.querySelector(TOUR.steps[TOUR.i].selector); }catch(e){ el = null; }
    if(!el){ return; }
    const r = el.getBoundingClientRect();
    const vw = window.innerWidth, vh = window.innerHeight, pad = 6, gap = 10, m = 12;
    TOUR.spot.style.top = Math.max(0, r.top - pad) + "px";
    TOUR.spot.style.left = Math.max(0, r.left - pad) + "px";
    TOUR.spot.style.width = Math.min(vw, r.width + pad * 2) + "px";
    TOUR.spot.style.height = Math.min(vh, r.height + pad * 2) + "px";
    const card = TOUR.card;
    const cw = card.offsetWidth || 344, ch = card.offsetHeight || 160;
    let top = r.bottom + gap;
    if(top + ch > vh - m) top = r.top - gap - ch;        // no room below → above
    if(top < m) top = Math.min(Math.max(m, r.bottom + gap), vh - ch - m);  // clamp
    let left = r.left;
    left = Math.max(m, Math.min(left, vw - cw - m));
    card.style.top = Math.round(top) + "px";
    card.style.left = Math.round(left) + "px";
    card.style.transform = "";
  }

  function closeTour(){
    if(!TOUR) return;
    const t = TOUR; TOUR = null;
    try{ if(t.onMove){ window.removeEventListener("scroll", t.onMove, true); window.removeEventListener("resize", t.onMove); } }catch(e){}
    try{ if(t.onKey) document.removeEventListener("keydown", t.onKey, true); }catch(e){}
    if(t.spot && t.spot.remove) t.spot.remove();
    if(t.card && t.card.remove) t.card.remove();
  }
  // ── TUTORIAL-OVERLAY-END ────────────────────────────────────────────────────

  // ═══════════════════════════════════════════════════════════════════════════
  // ── GUIDE-PANEL-START (W-guide) — THE '?' PER-SURFACE GUIDE.
  //    The '?' chip in the chrome opens a panel naming, for the CURRENT surface: its
  //    purpose, and every verb answering "WHAT WILL THIS DO?" (what it writes, its cost,
  //    its PSU class), plus a door to the full /guide. One universal mechanism — every
  //    surface that boots the shell gets it free.
  //
  //    THE HONESTY: the panel ALWAYS shows the surface purpose immediately, from the roster
  //    the shell already fetched (/shared/views) — never a spinner-forever, never a blank.
  //    It then ENRICHES with the verb detail from GET /guide/data?surface=<id>. When that
  //    route is not wired yet (the guide surface's live route lands at the orchestrator's
  //    seam — until then it 404s), the panel degrades HONESTLY: purpose stands, and the
  //    verb block says the full detail arrives with /guide, with the door offered anyway.
  //    It DESCRIBES — zero mutation. Every colour rides a hymn var (ensureGuideCss).
  // ═══════════════════════════════════════════════════════════════════════════
  let GUIDE_EL = null;

  function ensureGuideCss(){
    if(document.getElementById("hy-guide-css")) return;
    const st = document.createElement("style");
    st.id = "hy-guide-css";
    st.textContent =
      ".hy-guide-back{position:fixed;inset:0;z-index:2147481500;background:color-mix(in srgb,var(--bg) 55%,transparent);"+
        "display:none}"+
      ".hy-guide-back.open{display:block}"+
      ".hy-guide{position:fixed;z-index:2147481501;top:0;right:0;height:100%;width:min(420px,94vw);"+
        "display:none;flex-direction:column;background:var(--panel);border-left:1px solid var(--edge2);"+
        "box-shadow:var(--hy-pop-shadow);color:var(--ink);"+
        "font:12.5px/1.55 -apple-system,'Segoe UI',Roboto,sans-serif}"+
      ".hy-guide.open{display:flex}"+
      ".hy-guide-head{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;padding:13px 15px;"+
        "border-bottom:1px solid var(--edge2)}"+
      ".hy-guide-head .g-t{font-size:14px;font-weight:700;color:var(--ink)}"+
      ".hy-guide-head .g-p{font-family:var(--mono);font-size:10.5px;color:var(--accent)}"+
      ".hy-guide-head .g-x{margin-left:auto;background:none;border:none;color:var(--dim);cursor:pointer;"+
        "font-size:18px;line-height:1;padding:0 3px}"+
      ".hy-guide-head .g-x:hover{color:var(--ink)}"+
      ".hy-guide-body{overflow:auto;padding:13px 15px;flex:1}"+
      ".hy-guide-purpose{color:var(--ink2);font-size:12.5px;line-height:1.55;margin-bottom:12px}"+
      ".hy-guide-h{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--dim);"+
        "font-family:var(--mono);margin:14px 0 8px}"+
      ".hy-guide-verb{border:1px solid var(--edge);border-radius:8px;background:var(--panel2);"+
        "padding:8px 11px;margin-bottom:7px}"+
      ".hy-guide-verb .gv-top{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}"+
      ".hy-guide-verb .gv-nm{font-family:var(--mono);font-weight:700;font-size:11px;color:var(--ink)}"+
      ".hy-guide-verb .gv-route{font-family:var(--mono);font-size:9.5px;color:var(--dim)}"+
      ".hy-guide-verb .gv-does{margin-top:4px;font-size:11.5px;line-height:1.5;color:var(--ink2)}"+
      ".hy-guide-verb .gv-does.pending{color:var(--dim);font-style:italic}"+
      ".hy-guide-psu{font-family:var(--mono);font-size:9px;font-weight:700;text-transform:uppercase;"+
        "letter-spacing:.05em;padding:1px 6px;border-radius:999px;border:1px solid var(--edge2);margin-left:3px}"+
      ".hy-guide-psu.local{color:var(--ok);border-color:rgba(158,206,106,.4)}"+
      ".hy-guide-psu.heavy{color:var(--warn);border-color:rgba(224,175,104,.4)}"+
      ".hy-guide-none{font-size:11.5px;color:var(--dim);font-style:italic}"+
      ".hy-guide-degraded{font-size:11.5px;color:var(--ink2);border:1px dashed var(--edge2);"+
        "border-radius:8px;padding:9px 11px;line-height:1.5}"+
      ".hy-guide-foot{padding:11px 15px;border-top:1px solid var(--edge2)}"+
      ".hy-guide-foot a{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);"+
        "font-size:11.5px;color:var(--accent);border:1px solid var(--edge2);border-radius:7px;"+
        "padding:5px 11px;text-decoration:none}"+
      ".hy-guide-foot a:hover{border-color:var(--accent);background:var(--bg)}";
    document.head.appendChild(st);
  }

  function ensureGuideEl(){
    if(GUIDE_EL) return GUIDE_EL;
    ensureGuideCss();
    const back = document.createElement("div");
    back.className = "hy-guide-back"; back.id = "hy-guide-back";
    const panel = document.createElement("div");
    panel.className = "hy-guide"; panel.id = "hy-guide";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "surface guide");
    document.body.appendChild(back);
    document.body.appendChild(panel);
    back.addEventListener("click", closeGuide);
    document.addEventListener("keydown", e => {
      if(e.key === "Escape" && panel.classList.contains("open")){ e.stopPropagation(); closeGuide(); }
    });
    GUIDE_EL = panel;
    return panel;
  }

  function closeGuide(){
    if(GUIDE_EL) GUIDE_EL.classList.remove("open");
    const b = document.getElementById("hy-guide-back");
    if(b) b.classList.remove("open");
  }

  // the PSU class named inside a verb's "does" line (read, never invented): the same
  // convention the guide surface uses — local-safe / model-heavy, else none.
  function guidePsu(does){
    const d = String(does || "").toLowerCase();
    if(d.includes("model-heavy")) return {cls: "heavy", label: "model-heavy"};
    if(d.includes("local-safe"))  return {cls: "local", label: "local-safe"};
    return null;
  }

  function guideVerbHtml(v){
    const nm = (v.class && v.name) ? (v.class + " · " + v.name) : (v.name || v.class || "verb");
    const psu = guidePsu(v.does);
    const does = v.does
      ? "<div class='gv-does'>"+esc(v.does)+
          (psu ? " <span class='hy-guide-psu "+psu.cls+"'>"+esc(psu.label)+"</span>" : "")+"</div>"
      : "<div class='gv-does pending'>what this does is not yet declared for this verb.</div>";
    return "<div class='hy-guide-verb'><div class='gv-top'>"+
      "<span class='gv-nm'>"+esc(nm)+"</span>"+
      (v.route ? "<span class='gv-route'>"+esc(v.route)+"</span>" : "")+
    "</div>"+does+"</div>";
  }

  // OPEN the guide panel for the current surface. Purpose renders IMMEDIATELY from the
  // already-fetched roster (never a spinner); the verb detail enriches from /guide/data,
  // degrading honestly (purpose stands, the door is still offered) when the route 404s.
  async function openGuide(){
    const act = activeView();
    const row = viewRow(act) || viewForPath(location.pathname) || null;
    const title = (row && (row.title || row.id)) || "this surface";
    const path = (row && row.path) || location.pathname;
    const purpose = (row && row.purpose) || "";
    const panel = ensureGuideEl();
    const back = document.getElementById("hy-guide-back");
    const cur = new URLSearchParams(location.search).get("corpus") || corpus || "";
    const guideHref = "/guide" + (cur ? "?corpus=" + ec(cur) : "");
    // toggle: clicking '?' again closes
    if(panel.classList.contains("open")){ closeGuide(); return; }
    panel.innerHTML =
      "<div class='hy-guide-head'>"+
        "<span class='g-t'>"+esc(title)+"</span>"+
        "<span class='g-p'>"+esc(path)+"</span>"+
        "<button type='button' class='g-x' title='close (Esc)'>×</button>"+
      "</div>"+
      "<div class='hy-guide-body' id='hy-guide-body'>"+
        (purpose ? "<div class='hy-guide-purpose'>"+esc(purpose)+"</div>" : "")+
        "<div class='hy-guide-h'>what will this do</div>"+
        "<div id='hy-guide-verbs'><div class='hy-guide-none'>reading the verbs…</div></div>"+
      "</div>"+
      "<div class='hy-guide-foot'><a href='"+esc(guideHref)+"'>open the full guide →</a></div>";
    panel.querySelector(".g-x").addEventListener("click", closeGuide);
    panel.classList.add("open");
    if(back) back.classList.add("open");

    const verbsEl = panel.querySelector("#hy-guide-verbs");
    // the honest degrade: /guide/data may 404 until the guide route is wired at the seam.
    let data = null;
    try{
      const r = await fetch("/guide/data?surface=" + ec(act || ""));
      if(r.ok) data = await r.json();
    }catch(e){ data = null; }
    if(!panel.classList.contains("open")) return;         // closed while fetching
    if(!data){
      verbsEl.innerHTML =
        "<div class='hy-guide-degraded'>the per-verb detail lives on the guide surface, which "+
        "isn’t routed on this server yet. The purpose above is live now; open the full guide "+
        "for what every verb writes, costs, and its PSU class.</div>";
      return;
    }
    // the surface may enrich its purpose from the contract (a fuller line than the roster's)
    if(data.purpose && data.purpose !== purpose){
      const pel = panel.querySelector(".hy-guide-purpose");
      if(pel) pel.textContent = data.purpose;
      else {
        const body = panel.querySelector("#hy-guide-body");
        const d = document.createElement("div");
        d.className = "hy-guide-purpose"; d.textContent = data.purpose;
        body.insertBefore(d, body.firstChild);
      }
    }
    const verbs = data.verbs || [];
    if(!data.declared){
      verbsEl.innerHTML = "<div class='hy-guide-none'>this surface has no contract file yet — "+
        "its verbs are not declared.</div>";
    } else if(verbs.length){
      verbsEl.innerHTML = verbs.map(guideVerbHtml).join("");
    } else {
      verbsEl.innerHTML = "<div class='hy-guide-none'>read-only surface — no verb here writes anything.</div>";
    }
  }

  function wireGuide(bar){
    ensureGuideCss();
    const b = bar.querySelector("#hy-guide-btn");
    if(b) b.addEventListener("click", e => { e.preventDefault(); openGuide(); });
  }
  // ── GUIDE-PANEL-END ─────────────────────────────────────────────────────────

  window.HymnShell = {
    corpus: () => corpus,
    openGuide: openGuide,          // W-guide: open the per-surface '?' guide panel
    closeGuide: closeGuide,        // W-guide: close it
    startTour: startTour,          // W8: open the in-place tutorial overlay for this surface
    // the count of tour steps whose anchor is live on THIS surface right now (shared +
    // per-route, after graceful skip) — the walk assertion reads it to prove every
    // rostered surface tours its real room, never degrades silently to the 2 shared steps.
    tourStepCount: () => tourVisible(tourStepsFor(activeView() || "")).length,
    activeView: activeView,        // the roster view id for the current path (served-alias aware)
    openNode: openNode,
    openLadder: (opts) => openLadder(opts || {}),   // W0.5: open the ladder over a target
    refreshSelToken: refreshSelToken,               // W0.5: repair the header token to the live URL
    viewHref: viewHref,
    renderMath: (el) => window.renderMath(el),
    setDeskBadge: setDeskBadge,   // W1.3 wires the count here; slot is graceful until then
    hyStale: hyStale,             // W1.2: the one stale-banner atom (render one read)
    renderStale: renderStale,     // W1.2: fill a .hy-stale-strip with the degraded reads
    fetchStale: fetchStale,       // W1.2: GET /shared/staleness (pure read, no rebuild)
    openRail: openRail,           // W3.3: open the version rail (lazy — fetches on open, not first paint)
    closeRail: closeRail,         // W3.3: close the version rail
    hyRule: hyRule,               // W0/D16: attach the rule-in-place mouth to any host (el, ctx)
    injectContext: injectContext, // W0/L1: (re)render the shared context header
  };

  if(document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", build);
  else build();
})();
