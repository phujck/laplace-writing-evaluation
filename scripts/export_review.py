"""export_review.py — bake ANY projected manuscript into a static, password-gated review
bundle for reading, annotating and commenting off-session (phone or desktop).

PORTED (2026-07-17, WO-20260717-002125-exporter-port · his word PV-20260717T002125Z
"Bank the port, then delete"): the bundle is now baked onto THE ONE ARTEFACT SURFACE —
``artefact.html`` + ``artefact-panes.mjs`` over the shared ``store.mjs`` model (the W-series
front-end rebuild) — exactly as ``export_demo.py`` was ported off the tombstoned
``conceptric_editor2.html``. The retired bespoke self-contained app (``review_static.html``,
laplaceUnlock/window.CFG over baked WebP pages) is GONE; the successor is a live pdf.js reader
served against a BAKED read layer (no LaTeX, no engine, no CDN), gated by the password seal.

GENERAL BY CONSTRUCTION (his standing directive, 2026-07-03): point it at any paper's
compile root + its project conceptric and you get a remote review surface. Nothing about one
project is baked in — every path derives from the two arguments.

    python scripts/export_review.py <manuscript_root.tex> --corpus <name> \
        [--out DIR] [--slug LEAF] [--password PW] [--actor NAME] [--publish SITE_DIR]

Shape of the bundle (``<out>/<slug>/``), the SAME multi-file self-contained shape the demo
port ships (works from any static host, offline of the engine — the shim answers every read
from the sealed blob; no backend, no network but the one comment-bank host)::

    <slug>/
      index.html   the GATE — passphrase → laplaceUnlock decrypts data.enc, stashes the
                   plaintext in sessionStorage, hops to app.html.
      app.html     the real artefact surface (artefact.html) adapted by a THIN shim only:
                   /shared/ asset paths → relative (href/src AND the inline module's ESM
                   specifier), a prepended fetch shim that answers every /artefact/* +
                   /shared/* + /review/* + /projection/* GET from the baked blob (and the
                   pdf via /projection/pdf), and banks a comment through the GitHub Contents
                   API (the ONE allowed off-page write); every author verb is refused.
      data.enc     site_seal.encrypt(json(DB), passphrase) — the ONLY sealed artefact. DB =
                   the exact live-producer responses (context / versions / plan / nodemap /
                   findings / dismissals / node briefs) + the compiled pdf (base64) + the tex
                   sources + the comment-bank config. The whole paper decrypts once, reads
                   offline.
      shared/      hymn.css, shell.js, the ESM module graph (store.mjs + artefact-panes.mjs,
                   imports rewritten relative), pdfjs/, vendor/codemirror/, katex/ (verbatim).

VIEW = MECHANISM (the anti-reimplementation law): every baked read is the byte-for-byte output
of the SAME handler the live surface calls (``artefact.handle`` / ``shared_ui.handle`` /
``review_surface.handle`` / ``projection_viewer.handle``) — replayed here at bake time, never
re-derived. The anti-staleness law holds: the exporter recompiles a missing pdf first, so no
artefact whose source moved on is ever baked.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import posixpath
import re
import secrets
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.web import artefact as af            # noqa: E402  — /artefact/context (the authority)
from laplace.manuscript import manuscript_bridge as mb   # noqa: E402  — the generic ingest path (still alive)
from laplace.manuscript import projection_viewer as pv   # noqa: E402  — the pdf/tex/node producers
from laplace.manuscript import review_surface as rs       # noqa: E402  — the /review/* producers
from laplace.web import review_http
from laplace.web import shared_ui as su           # noqa: E402  — the /shared/* producers
from laplace.web import site_seal                  # noqa: E402  — the ONE reused engine module (the scramble)

# ── the artefact surface = the template (W-series rebuild) ───────────────────
ARTEFACT_SRC = ROOT / "src" / "laplace" / "web" / "artefact.html"          # the rebuilt review surface
SHARED_SRC = ROOT / "src" / "laplace" / "web" / "static_shared"           # hymn.css/shell.js/*.mjs/pdfjs/…
GH_REPO_DEFAULT = "phujck/laplace"                                # the inbox repo (name only; no secret)

# the verbatim /shared/ subdir assets the surface + shell pull off disk (copied, never fetched):
# pdf.js (the reader + its worker), codemirror (the editor), katex (the shell injects it).
_VERBATIM_DIRS = ("pdfjs", "vendor", "katex")


# ── ESM-import rewrite (the demo-port idiom, verbatim) ───────────────────────
_ESM_ABS_IMPORT_RX = re.compile(r'((?:from|import)\s*\(?\s*["\'])(/shared/[^"\']+\.mjs)(["\'])')


def _shared_mjs_imports(text: str) -> list[str]:
    """The /shared/*.mjs specifiers a script imports, source order, de-duplicated. Catches
    `from "…"`, bare `import "…"` and dynamic `import("…")` alike."""
    out: list[str] = []
    for m in _ESM_ABS_IMPORT_RX.finditer(text):
        spec = m.group(2)
        if spec not in out:
            out.append(spec)
    return out


def _rewrite_esm_imports(text: str, referrer_dir: str) -> str:
    """Rewrite every absolute `/shared/…mjs` import specifier to a RELATIVE one that resolves,
    from a script whose own location is ``referrer_dir`` (posix, relative to the bundle root;
    "" for a page at the bundle root), to the same physical file — the JS-import twin of the
    href/src attribute rewrite, adjusted for ES-module semantics (a module IN shared/ importing
    a sibling needs "./x.mjs", never "shared/x.mjs")."""
    def sub(m: re.Match) -> str:
        target = m.group(2)[1:]                      # "/shared/x.mjs" -> "shared/x.mjs"
        rel = posixpath.relpath(target, start=referrer_dir or ".")
        if not rel.startswith(("./", "../")):
            rel = "./" + rel
        return m.group(1) + rel + m.group(3)
    return _ESM_ABS_IMPORT_RX.sub(sub, text)


def _rel(p: Path) -> str:
    """Repo-relative posix — the shape every producer entrypoint expects."""
    return p.resolve().relative_to(ROOT.resolve()).as_posix()


# ── the freshness gate (self-heal): the reader needs a compiled pdf on disk ──
def _ensure_pdf(pdf_rel: str | None, root_rel: str) -> tuple[str | None, Path | None, int]:
    """Resolve the pdf the reader shows to a real file, recompiling if it is missing so no
    artefact whose source moved on is baked. Returns (pdf_rel, pdf_path, n_recompiles).
    A None pdf_rel (a project with no built artefact) bakes cleanly — the reader shows the
    rail's banked-rebuild affordance, and the bundle still opens."""
    if pdf_rel:
        p = ROOT / pdf_rel
        if p.is_file():
            return pdf_rel, p, 0
    # no baked-current pdf on disk — compile the given root and re-resolve.
    print("  compiling (no built pdf for the current artefact) …")
    res = pv.compile_tex(root_rel)
    if not res.get("ok"):
        print("  WARNING: compile failed — baking without a pdf (reader shows the rail rebuild):\n" +
              (res.get("log_tail") or "")[-600:])
        return None, None, 1
    src = pv._safe_path(root_rel)
    pdf = pv.resolve_root(src).with_suffix(".pdf") if src is not None else None
    if pdf is not None and pdf.is_file():
        return _rel(pdf), pdf, 1
    return None, None, 1


# ── replay a live handler and keep its exact body (view = mechanism) ─────────
def _replay_json(fn, path: str, query: dict, *rest) -> dict | list | None:
    """Call one route handler exactly as the server would and parse its JSON body. ``None``
    when the handler declines the path or the body is not JSON — the caller bakes a safe empty
    so a producer that is absent for a corpus never fails the build."""
    try:
        res = fn(path, query, *rest)
    except Exception as e:                              # a producer that raises degrades to empty
        print(f"    · {path}: producer raised ({type(e).__name__}: {e}) — baking empty")
        return None
    if res is None:
        return None
    _status, _ctype, body = res
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, AttributeError):
        return None


def bake(root_rel: str, corpus: str, actor: str, github_token: str = "") -> dict:
    """Bake the full read layer: every response the artefact panes fetch, replayed from the
    SAME producers the live surface calls, plus the compiled pdf + the tex sources."""
    q = {"corpus": [corpus]}

    # THE authority — /artefact/context (registry.project_context serialized). Everything the
    # reader/editor/annotator agree on rides this one fact.
    context = _replay_json(af.handle, "/artefact/context", q, "GET", b"")
    if context is None:
        raise SystemExit(f"no artefact context for corpus {corpus!r} — not a registry project? "
                         "(the surface resolves the paper through registry.project_context)")
    cur = context.get("current_artefact") or {}
    manuscript_dir = context.get("manuscript_dir") or str(Path(root_rel).parent.as_posix())
    md = ROOT / manuscript_dir

    # the compiled pdf the reader renders through pdf.js (self-heal if missing).
    pdf_rel, pdf_path, recompiles = _ensure_pdf(cur.get("pdf"), root_rel)
    print(f"  pdf: {pdf_rel or '(none — rail rebuild)'} (recompiles: {recompiles})")

    # the static read table — one baked body per GET path the panes + shell fetch.
    table: dict[str, object] = {}
    for path, fn, rest in (
        ("/artefact/context",  af.handle, ("GET", b"")),
        ("/shared/versions",   su.handle, ()),
        ("/shared/plan",       su.handle, ()),
        ("/shared/views",      su.handle, ()),
        ("/shared/staleness",  su.handle, ()),
        ("/review/nodemap",    review_http.handle, ("GET", b"")),
        ("/review/findings",   review_http.handle, ("GET", b"")),
        ("/review/dismissals", review_http.handle, ("GET", b"")),
    ):
        body = _replay_json(fn, path, q, *rest)
        if body is not None:
            table[path] = body
    # the reader/editor authority is ALWAYS present (asserted above).
    table["/artefact/context"] = context

    # node briefs — one per anchorable node (the nodemap entries) + every planned node, so a
    # ¶-click or a finding-jump resolves its essence offline. Replayed through /projection/node.
    node_ids: set[str] = set()
    nm = table.get("/review/nodemap") or {}
    node_ids.update((nm.get("entries") or {}).keys())
    plan = table.get("/shared/plan") or {}
    node_ids.update((plan.get("node_index") or {}).keys())
    nodes: dict[str, object] = {}
    for nid in sorted(node_ids):
        brief = _replay_json(pv.handle, "/projection/node", {"id": [nid], "corpus": [corpus]}, "GET", b"")
        if isinstance(brief, dict) and "error" not in brief:
            nodes[nid] = brief
    print(f"  baked {len(nodes)} node briefs; {len((nm.get('entries') or {}))} nodemap anchors")

    # the tex sources — the current tex + every .tex under the manuscript dir, so the editor
    # opens and the version diff aligns offline (they are small; the reader pdf dwarfs them).
    tex: dict[str, str] = {}
    tex_files = set()
    if cur.get("tex"):
        tex_files.add(cur["tex"])
    if md.is_dir():
        for f in sorted(md.rglob("*.tex")):
            tex_files.add(_rel(f))
    for rel in sorted(tex_files):
        fp = ROOT / rel
        if fp.is_file():
            try:
                tex[rel] = fp.read_text(encoding="utf-8")
            except OSError:
                pass

    # the pdf bytes (base64), keyed by its repo-rel path (what /projection/pdf?file= resolves).
    pdfs: dict[str, str] = {}
    if pdf_rel and pdf_path is not None:
        pdfs[pdf_rel] = base64.b64encode(pdf_path.read_bytes()).decode("ascii")

    import subprocess
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                               capture_output=True, encoding="utf-8", timeout=10).stdout.strip()
    except Exception:
        head = ""

    return {
        "corpus": corpus,
        "manuscript_dir": manuscript_dir,
        "git_head": head,
        "responses": table,          # path -> baked live-producer body
        "nodes": nodes,              # nid  -> /projection/node brief
        "tex": tex,                  # repo-rel -> tex source
        "pdfs": pdfs,                # repo-rel -> base64 pdf bytes
        "config": {
            # the bankable-comment target: repo/branch are global, inbox_path is this paper's.
            "corpus": corpus,
            "repo": GH_REPO_DEFAULT,
            "branch": "master",
            "inbox_path": f"{manuscript_dir}/feedback/inbox",
            "actor": actor,
            # a baked write-token lives INSIDE the encrypted blob, so it is only readable by
            # someone who has the password (his ask 2026-07-03). Empty unless a token is given.
            "github_token": github_token,
        },
    }


# ── the fetch shim + review layer (prepended into app.html; the ONLY logic edit) ──
# It (1) hydrates the decrypted blob from the gate's sessionStorage handoff, (2) overrides
# fetch to answer every baked engine read + serve the pdf, (3) refuses author verbs, and
# (4) banks a comment through the GitHub Contents API (the ONE allowed off-page write).
SHIM_JS = r"""
(function(){
  "use strict";
  // __REVIEW SHIM__ (WO-20260717 exporter port): the artefact surface, served against the
  // sealed blob — no engine, no LaTeX, no CDN. Every store.fetchJSON + the pdf.js getDocument
  // land here; nothing escapes to the network but the one comment-bank host.
  var RAW=null;
  try { RAW=sessionStorage.getItem("__review_payload"); } catch(e){}
  if(!RAW){ location.replace("index.html"); return; }
  var DB; try { DB=JSON.parse(RAW); } catch(e){ location.replace("index.html"); return; }
  window.__REVIEW=DB;
  var TABLE=DB.responses||{};      // path -> baked body
  var NODES=DB.nodes||{};          // nid  -> brief
  var TEX=DB.tex||{};              // repo-rel -> tex text
  var PDFS=DB.pdfs||{};            // repo-rel -> base64 pdf
  var CFG=DB.config||{};
  window.CFG=CFG;                  // anything reading window.CFG gets the bank config (no secret leaks: sealed)

  function J(obj, status){ return new Response(JSON.stringify(obj),
    {status:status||200, headers:{"Content-Type":"application/json"}}); }
  function firstKey(o){ for(var k in o) if(Object.prototype.hasOwnProperty.call(o,k)) return k; return null; }
  function b64ToBytes(b64){ var bin=atob(b64), n=bin.length, u=new Uint8Array(n);
    for(var i=0;i<n;i++) u[i]=bin.charCodeAt(i); return u; }
  function parseQS(url){ var qs={}; (url.split("?")[1]||"").split("&").forEach(function(kv){ if(!kv) return;
    var p=kv.split("="); qs[decodeURIComponent(p[0])]=decodeURIComponent((p[1]||"").replace(/\+/g," ")); });
    return qs; }

  // ── the bankable write: mint a review comment, push via the GitHub Contents API ──
  function pad(n){ return String(n).padStart(2,"0"); }
  function b64utf8(s){ return btoa(unescape(encodeURIComponent(s))); }
  function ghToken(){ try{ return (localStorage.getItem("review_gh_pat")||"").trim() || (CFG.github_token||""); }
    catch(e){ return CFG.github_token||""; } }
  function mintRecord(payload){
    var now=new Date();
    var focus=(payload && payload.node_id) || "unknown";
    var nodePart=String(focus).split("#").pop().split(":").pop();
    var id="FB-"+now.getFullYear()+pad(now.getMonth()+1)+pad(now.getDate())+"-"+
      pad(now.getHours())+pad(now.getMinutes())+pad(now.getSeconds())+"-"+nodePart+"-"+
      Math.random().toString(36).slice(2,6);
    return {id:id, project:CFG.corpus, ts:now.toISOString().slice(0,19),
      node_id:focus, kind:(payload&&payload.kind)||"note",
      comment:(payload&&payload.comment)||"", by:(CFG.actor||"author"),
      anchor:(payload&&payload.anchor)||{}, status:"open"};
  }
  function queueLocal(rec){
    try{ var k="review_outbox_"+CFG.corpus; var q=JSON.parse(localStorage.getItem(k)||"[]");
      q.push(rec); localStorage.setItem(k, JSON.stringify(q)); }catch(e){}
  }
  async function bankFeedback(init){
    var payload={}; try{ payload=JSON.parse((init&&init.body)||"{}"); }catch(e){}
    var rec=mintRecord(payload);
    var tok=ghToken();
    if(!tok || !navigator.onLine){
      queueLocal(rec);
      return J({ok:true, queued:true, record:rec,
        note: tok ? "offline — the comment is safe on this device" :
                    "no push token in this bundle — the comment is queued locally"});
    }
    var path=CFG.inbox_path+"/"+rec.id+".json";
    var url="https://api.github.com/repos/"+CFG.repo+"/contents/"+
      path.split("/").map(encodeURIComponent).join("/");
    try{
      var r=await fetch(url,{method:"PUT",
        headers:{Authorization:"Bearer "+tok, Accept:"application/vnd.github+json",
                 "Content-Type":"application/json"},
        body:JSON.stringify({message:"review comment "+rec.id, branch:(CFG.branch||"master"),
          content:b64utf8(JSON.stringify(rec,null,2))})});
      if(r.status===201||r.status===200||r.status===422){ rec._pushed=true; return J({ok:true, record:rec}); }
      queueLocal(rec);
      return J({ok:false, queued:true, record:rec, error:"push failed ("+r.status+") — queued locally"}, 200);
    }catch(e){ queueLocal(rec);
      return J({ok:false, queued:true, record:rec, error:"network error — queued locally"}, 200); }
  }

  // ── the fetch override: baked reads, the pdf, refused verbs ──
  var _fetch=window.fetch.bind(window);
  window.fetch=function(input, init){
    var url=(typeof input==="string")?input:(input&&input.url)||"";
    var method=((init&&init.method)||(input&&input.method)||"GET").toUpperCase();
    if(/^https?:\/\//i.test(url)){
      if(url.indexOf("https://api.github.com/")===0) return _fetch(input, init);   // the one write host
      return J({error:"external requests are not in this offline review bundle"}, 403);
    }
    var path=url.split("?")[0], qs=parseQS(url);
    // the one author write the review bundle keeps: bank a comment.
    if(path==="/projection/feedback" && method==="POST") return bankFeedback(init);
    // every other author verb (compile/recompile/restore/adjudicate/rebuild/visit) is refused.
    if(method!=="GET")
      return J({error:"author verbs are not in this offline review bundle", ok:false, applied:false}, 403);
    // the reader's pdf (pdf.js getDocument fetches this; served from the sealed blob).
    if(path==="/projection/pdf"){
      var f=qs.file||"";
      var b=PDFS[f] || (/\.tex$/i.test(f)? PDFS[f.replace(/\.tex$/i,".pdf")] : null) || PDFS[firstKey(PDFS)];
      if(!b) return J({error:"no baked pdf for "+f}, 404);
      return new Response(b64ToBytes(b), {status:200,
        headers:{"Content-Type":"application/pdf", "Accept-Ranges":"none"}});
    }
    // the tex source (raw text — store.fetchJSON {raw:true} reads .text()).
    if(path==="/projection/tex"){
      var t=TEX[qs.file||""];
      if(t==null) return new Response("", {status:404});
      return new Response(t, {status:200, headers:{"Content-Type":"text/plain; charset=utf-8"}});
    }
    // a node brief.
    if(path==="/projection/node"){
      var nb=NODES[qs.id||""];
      return nb ? J(nb) : J({id:qs.id||"", error:"no baked brief for this node in the bundle"}, 404);
    }
    // the static baked read table (context/versions/plan/views/staleness/nodemap/findings/dismissals).
    if(Object.prototype.hasOwnProperty.call(TABLE, path)) return J(TABLE[path]);
    // any other engine read → honest empty (the panes catch + degrade).
    if(path.indexOf("/artefact/")===0 || path.indexOf("/shared/")===0 ||
       path.indexOf("/review/")===0 || path.indexOf("/projection/")===0)
      return J({error:"not in this offline review bundle", records:[], rows:[], nodes:[], entries:{}}, 404);
    return _fetch(input, init);   // same-page relative assets (shared/*) fall through to disk
  };
})();
"""


# ── build the gate (index.html) — passphrase → decrypt → hop to app.html ─────
def build_index_html() -> str:
    return r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Laplace — remote review (sealed)</title>
<style>
  :root{ color-scheme: dark; }
  html,body{margin:0;height:100%;background:#0e1116;color:#d7dee8;
    font:14px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;display:flex;align-items:center;justify-content:center}
  .card{max-width:440px;width:92%;background:#141a23;border:1px solid #2d3744;border-radius:14px;
    padding:26px 26px 22px;box-shadow:0 10px 40px rgba(0,0,0,.5)}
  h1{font-size:18px;margin:0 0 4px}h1 b{color:#7aa2f7}
  p.sub{color:#9aa5b4;font-size:12.5px;margin:0 0 18px}
  label{display:block;font-size:12px;color:#9aa5b4;margin:12px 0 4px}
  input{width:100%;background:#0e1116;color:#d7dee8;border:1px solid #2d3744;border-radius:8px;
    padding:10px;font:14px inherit}
  input:focus{outline:none;border-color:#7aa2f7}
  button{margin-top:18px;width:100%;background:#7aa2f7;color:#0e1116;border:0;border-radius:8px;
    padding:11px;font-weight:700;font-size:14px;cursor:pointer}
  .msg{min-height:16px;font-size:12px;margin-top:10px;color:#f7768e}
  .use{font-size:11.5px;color:#6b7689;margin-top:16px;border-top:1px solid #222a36;padding-top:12px}
</style>
</head>
<body>
  <div class="card">
    <h1><b>Laplace</b> · remote review</h1>
    <p class="sub">The artefact surface — read the compiled paper, follow a paragraph to its
      nodes, and bank a comment — served offline against a sealed snapshot.</p>
    <label for="pass">passphrase</label>
    <input id="pass" type="password" autocomplete="off" placeholder="passphrase">
    <button id="go">unlock</button>
    <div id="msg" class="msg"></div>
    <div class="use">The whole paper decrypts once, then reads offline. Comments bank to the
      paper's inbox on GitHub when a push token is set; otherwise they queue on this device.</div>
  </div>
<script>
__UNLOCK_JS__

async function boot(){
  var pass=document.getElementById("pass").value;
  var msg=document.getElementById("msg");
  if(!pass){ msg.textContent="enter the passphrase"; return; }
  msg.style.color="#9aa5b4"; msg.textContent="unlocking…";
  try{
    var resp=await fetch("data.enc"); var buf=new Uint8Array(await resp.arrayBuffer());
    var pt=await laplaceUnlock(buf, pass);
    var text=new TextDecoder().decode(pt);
    JSON.parse(text);   // sanity — a wrong passphrase throws in decrypt, not here
    sessionStorage.setItem("__review_payload", text);
    location.href="app.html";
  }catch(e){ msg.style.color="#f7768e"; msg.textContent="wrong passphrase (or corrupt bundle)"; }
}
document.getElementById("go").onclick=boot;
document.getElementById("pass").addEventListener("keydown",function(e){ if(e.key==="Enter") boot(); });
</script>
</body>
</html>
""".replace("__UNLOCK_JS__", site_seal.UNLOCK_JS)


# ── build app.html: the real surface + prepended shim + asset-path rewrite ───
def build_app_html() -> str:
    src = ARTEFACT_SRC.read_text(encoding="utf-8")
    # asset paths: the surface references /shared/* absolutely; under <slug>/ they must be
    # relative so they resolve to <slug>/shared/*. The href/src rewrite covers the head tags
    # (hymn.css, shell.js); _rewrite_esm_imports covers the inline module's ESM specifier.
    src = src.replace('href="/shared/', 'href="shared/').replace('src="/shared/', 'src="shared/')
    src = _rewrite_esm_imports(src, "")            # app.html sits at the bundle root
    # prepend the shim as the FIRST head script so the fetch override installs before the
    # deferred shell script and the inline module's load-time boot.
    src = src.replace("<head>", "<head>\n<script>\n" + SHIM_JS + "\n</script>\n", 1)
    return src


def _patch_shell(text: str) -> str:
    """The shared shell self-bootstraps hymn.css + KaTeX with ABSOLUTE /shared/ hrefs (and its
    presence-guard checks the absolute href). Under <slug>/ those root paths 404 — rewrite the
    injection + guard paths to relative so they resolve to <slug>/shared/*. The /shared/* data
    fetches stay absolute for the shim to answer."""
    out = text
    for a, b in (("/shared/hymn.css", "shared/hymn.css"), ("/shared/katex/", "shared/katex/")):
        if a not in out:
            raise RuntimeError(f"shell.js changed — {a!r} asset injection moved; re-audit the shell")
        out = out.replace(a, b)
    return out


def _patch_artefact_panes(text: str) -> str:
    """The pdf.js worker source is a STRING (not an import), so the ESM-import rewrite never
    touches it — rewrite it to a bundle-root-relative path so the worker resolves under
    <slug>/ (pdf.js resolves workerSrc against the document, app.html at the root)."""
    lit = '"/shared/pdfjs/pdf.worker.min.mjs"'
    if lit not in text:
        raise RuntimeError("artefact-panes.mjs changed — the pdf.worker src literal moved; re-audit")
    return text.replace(lit, '"shared/pdfjs/pdf.worker.min.mjs"')


def _copy_shared(out: Path) -> list[str]:
    """Copy the public /shared/ assets verbatim (hymn.css, shell.js patched, pdfjs/, vendor/,
    katex/) PLUS the transitive top-level .mjs module graph the surface imports, each with its
    import specifiers rewritten relative (see _rewrite_esm_imports) so the graph resolves under
    <slug>/. The seed set is derived MECHANICALLY from the surface source, never hardcoded.
    Returns the copied top-level .mjs paths (for reporting)."""
    dst = out / "shared"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    shutil.copy2(SHARED_SRC / "hymn.css", dst / "hymn.css")
    (dst / "shell.js").write_text(
        _patch_shell((SHARED_SRC / "shell.js").read_text(encoding="utf-8")), encoding="utf-8")
    for d in _VERBATIM_DIRS:
        src_dir = SHARED_SRC / d
        if src_dir.is_dir():
            shutil.copytree(src_dir, dst / d)

    # the ESM graph: mechanical transitive closure over TOP-LEVEL /shared/*.mjs imports only
    # (subdir modules — pdfjs/*, vendor/* — are the verbatim bundles copied above, never
    # re-rewritten). A module carrying a non-import /shared/ string literal (the pdf.worker src)
    # is patched by filename before the import-specifier rewrite.
    mjs_patchers = {"artefact-panes.mjs": _patch_artefact_panes}
    pending = [s for s in _shared_mjs_imports(ARTEFACT_SRC.read_text(encoding="utf-8"))
               if "/" not in s[len("/shared/"):]]
    copied: list[str] = []
    seen: set[str] = set()
    while pending:
        spec = pending.pop(0)
        if spec in seen:
            continue
        seen.add(spec)
        rel = spec[len("/shared/"):]                 # e.g. "artefact-panes.mjs"
        src_path = SHARED_SRC / rel
        if not src_path.is_file():
            raise RuntimeError(f"the surface imports {spec!r} but {src_path} is absent — "
                               "the ESM module graph is broken")
        module_text = src_path.read_text(encoding="utf-8")
        for dep in _shared_mjs_imports(module_text):
            leaf = dep[len("/shared/"):]
            if "/" not in leaf and dep not in seen and dep not in pending:
                pending.append(dep)
        patch = mjs_patchers.get(rel)
        if patch is not None:
            module_text = patch(module_text)
        (dst / rel).write_text(_rewrite_esm_imports(module_text, "shared"), encoding="utf-8")
        copied.append(rel)
    return copied


def _verify_self_contained(out: Path, index_html: str, app_html: str) -> None:
    """Refuse to ship a bundle whose import graph is not fully rewritten: no baked .html/.mjs
    may carry a surviving absolute `/shared/…mjs` import (that would resolve to the SITE root,
    not the bundle) — the mechanical proof the bundle is self-contained (offline of the engine
    and any CDN)."""
    stray: list[str] = []
    for label, text in (("index.html", index_html), ("app.html", app_html)):
        if _ESM_ABS_IMPORT_RX.search(text):
            stray.append(label)
    for p in (out / "shared").rglob("*.mjs"):
        # the verbatim vendored bundles (pdfjs/, vendor/) are exempt — they carry no /shared/
        # imports and are copied whole; only the rewritten top-level graph is checked.
        if any(part in _VERBATIM_DIRS for part in p.relative_to(out / "shared").parts[:-1]):
            continue
        if _ESM_ABS_IMPORT_RX.search(p.read_text(encoding="utf-8", errors="ignore")):
            stray.append(str(p.relative_to(out)))
    if stray:
        raise SystemExit("bundle is NOT self-contained — surviving absolute /shared/ imports in: "
                         + ", ".join(stray))


def write_bundle(data: dict, out_dir: Path, password: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    index_html = build_index_html()
    app_html = build_app_html()
    copied = _copy_shared(out_dir)

    _verify_self_contained(out_dir, index_html, app_html)

    blob = site_seal.encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"), password)
    (out_dir / "data.enc").write_bytes(blob)
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")
    (out_dir / "app.html").write_text(app_html, encoding="utf-8")
    return {
        "out": str(out_dir),
        "data_enc_bytes": len(blob),
        "index_html_bytes": len(index_html),
        "app_html_bytes": len(app_html),
        "shared_mjs_modules": copied,
        "n_nodes": len(data.get("nodes") or {}),
        "n_tex": len(data.get("tex") or {}),
        "n_pdfs": len(data.get("pdfs") or {}),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="bake a manuscript into a sealed remote-review bundle "
                                             "on the artefact surface")
    ap.add_argument("root", help="the manuscript compile root (a main.tex), repo path or absolute")
    ap.add_argument("--corpus", required=True, help="the project conceptric name")
    ap.add_argument("--slug", default=None, help="short URL-friendly leaf dir (default: the corpus name)")
    ap.add_argument("--out", default="site_export/review")
    ap.add_argument("--password", default=None)
    ap.add_argument("--actor", default="author",
                    help="the by: identity minted onto a banked comment (default: author)")
    ap.add_argument("--github-token", default=None,
                    help="bake a write-token INTO the encrypted bundle (or set env "
                         "LAPLACE_REVIEW_GITHUB_TOKEN) so no per-device token is needed. It is "
                         "only exposed to someone with the password.")
    ap.add_argument("--use-gh-token", action="store_true",
                    help="bake the local `gh` CLI's token (read internally, never printed).")
    ap.add_argument("--publish", default=None,
                    help="copy the bundle into this site dir and stage it (never pushes)")
    a = ap.parse_args()
    slug = a.slug or a.corpus
    gh_token = a.github_token or os.environ.get("LAPLACE_REVIEW_GITHUB_TOKEN", "")
    if not gh_token and a.use_gh_token:
        import subprocess
        try:
            gh_token = subprocess.run(["gh", "auth", "token"], capture_output=True,
                                      encoding="utf-8", timeout=15).stdout.strip()
        except Exception as e:
            raise SystemExit(f"--use-gh-token: could not read gh token ({e})")
        if not gh_token:
            raise SystemExit("--use-gh-token: gh returned no token (run `gh auth login`)")
        print("  baking gh CLI token into the bundle (encrypted; not printed)")

    root_p = Path(a.root)
    root_rel = _rel(root_p if root_p.is_absolute() else (ROOT / a.root))

    print(f"exporting review bundle: {root_rel}  (corpus: {a.corpus})")
    data = bake(root_rel, a.corpus, a.actor, github_token=gh_token)
    out_dir = Path(a.out) / slug
    pw = a.password or os.environ.get("LAPLACE_REVIEW_PASSWORD") or secrets.token_urlsafe(10)
    rep = write_bundle(data, out_dir, pw)

    kb = (rep["data_enc_bytes"] + rep["index_html_bytes"] + rep["app_html_bytes"]) // 1024
    print(f"\nbundle: {out_dir}  ({kb} KB core, {rep['n_pdfs']} pdf, {rep['n_nodes']} nodes, "
          f"{rep['n_tex']} tex, modules: {', '.join(rep['shared_mjs_modules'])})")
    if not a.password and not os.environ.get("LAPLACE_REVIEW_PASSWORD"):
        print(f"generated passphrase (printed ONCE — bank it or re-export): {pw}")

    if a.publish:
        dst = Path(a.publish) / slug
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(out_dir, dst)
        print(f"published to {dst} — review, then commit + push the site repo yourself")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
