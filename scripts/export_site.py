"""The website exporter (backlog #15): bake a corpus conceptric's synthesized views into
ONE static, server-free HTML explorer - spine rail, graded map, node inspector in the
hymn-sheet look - and seal it as an ENCRYPTED bundle safe for public hosting
(phujck.github.io).

Encrypt by default: subset-sum-itqde is an unpublished disclosure, so the public artifact
is AES-256-GCM ciphertext (PBKDF2-SHA256, 600k iterations) that decrypts entirely
in-browser via WebCrypto - the host never sees plaintext. Per-corpus plain publishing
(--plain) is THE AUTHOR'S call, never a default.

Usage:
  python scripts/export_site.py <corpus> [--out DIR] [--password PW | --plain]

Outputs <out>/<corpus>/index.html (self-contained; ship the directory to gh-pages).
Without --password an ephemeral one is generated and printed ONCE - bank it or re-export.
"""
from __future__ import annotations

import argparse
import base64
import html as html_mod
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.research import corpus_ingest as ci  # noqa: E402

PBKDF2_ITER = 600_000


def bake_data(name: str) -> dict:
    troot = ci.resolve_corpus(ROOT, name)
    if troot is None:
        raise SystemExit(f"unknown corpus {name!r}")
    net = ci.corpus_network(troot, repo_root=ROOT, name=name)
    nodes = {}
    for nid, nd in net["nodes"].items():
        proj = nd.get("projection") or (nd.get("meta") or {}).get("projection") or {}
        edges = sorted({e.replace("confirmed::", "").replace("sem::", "")
                        for e in net["edge_index"].get(nid, [])
                        if e.replace("confirmed::", "").replace("sem::", "") != nid
                        and e.replace("confirmed::", "").replace("sem::", "") in net["nodes"]})
        nodes[nid] = {"kind": nd.get("kind"), "essence": nd.get("essence") or "",
                      "term": proj.get("term"), "retired": bool(proj.get("retired")),
                      "edges": edges}
    spine = [{"id": s["id"], "ord": s["ord"], "narrative": s.get("narrative", ""),
              "kind": s.get("kind")} for s in net.get("spine", [])]
    gl = troot.parent.parent / "GLOSSARY.md"
    glossary = gl.read_text(encoding="utf-8") if gl.is_file() else ""
    return {"corpus": name, "n_nodes": len(nodes), "spine": spine, "nodes": nodes,
            "glossary": glossary}


def inner_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = html_mod.escape(data["corpus"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — conceptric</title>
<style>
:root{{--bg:#0f1117;--panel:#171a23;--ink:#d8dce6;--dim:#8a91a3;--acc:#7aa2f7;--line:#262b38}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.55 Georgia,serif;height:100vh;display:flex;flex-direction:column}}
header{{padding:10px 18px;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:baseline}}
header h1{{font-size:16px;margin:0;font-weight:600}}header .dim{{color:var(--dim);font-size:12px}}
#wrap{{flex:1;display:flex;min-height:0}}
#spine{{width:270px;overflow-y:auto;border-right:1px solid var(--line);padding:10px}}
#spine h2,#list h2,#insp h2{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin:4px 0 8px}}
.beat{{padding:7px 9px;border-radius:6px;cursor:pointer;margin-bottom:4px;border:1px solid transparent}}
.beat:hover{{border-color:var(--line)}}.beat.on{{background:var(--panel);border-color:var(--acc)}}
.beat .nar{{color:var(--dim);font-size:12px}}
#list{{width:320px;overflow-y:auto;border-right:1px solid var(--line);padding:10px}}
#q{{width:100%;background:var(--panel);border:1px solid var(--line);color:var(--ink);
padding:7px 9px;border-radius:6px;font:inherit;margin-bottom:8px}}
.row{{padding:5px 8px;border-radius:5px;cursor:pointer;font-size:13px;display:flex;gap:8px}}
.row:hover,.row.on{{background:var(--panel)}}
.k{{color:var(--dim);font-size:11px;white-space:nowrap}}
#insp{{flex:1;overflow-y:auto;padding:16px 22px}}
#insp .id{{font-size:17px;font-weight:600}}#insp .kind{{color:var(--acc);font-size:12px;margin-bottom:10px}}
#insp .ess{{max-width:72ch;white-space:pre-wrap}}
.chip{{display:inline-block;background:var(--panel);border:1px solid var(--line);border-radius:999px;
padding:2px 10px;margin:3px 4px 0 0;font-size:12px;cursor:pointer}}
.chip:hover{{border-color:var(--acc)}}
.retired{{opacity:.45}}
</style></head><body>
<header><h1>{title}</h1><span class="dim" id="count"></span>
<span class="dim">static export — the live editor is the writing surface; this is a read model</span></header>
<div id="wrap">
 <nav id="spine"><h2>Spine</h2><div id="beats"></div></nav>
 <nav id="list"><h2>Nodes</h2><input id="q" placeholder="filter…"><div id="rows"></div></nav>
 <main id="insp"><h2>Inspector</h2><div id="detail" class="dim">Pick a beat or a node.</div></main>
</div>
<script id="data" type="application/json">{payload}</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const ids=Object.keys(D.nodes).sort();
document.getElementById('count').textContent=D.n_nodes+' nodes, '+D.spine.length+' beats';
const beats=document.getElementById('beats'),rows=document.getElementById('rows'),
 det=document.getElementById('detail'),q=document.getElementById('q');
function esc(s){{const d=document.createElement('div');d.textContent=s||'';return d.innerHTML}}
function show(id){{
 const n=D.nodes[id];if(!n)return;
 document.querySelectorAll('.row,.beat').forEach(e=>e.classList.toggle('on',e.dataset.id===id));
 det.innerHTML='<div class="id">'+esc(id)+(n.retired?' <span class="k">[retired]</span>':'')+'</div>'
  +'<div class="kind">'+esc(n.kind||'')+(n.term?' · term: '+esc(n.term):'')+'</div>'
  +'<div class="ess">'+esc(n.essence)+'</div>'
  +'<h2 style="margin-top:18px">Edges ('+n.edges.length+')</h2>'
  +n.edges.map(e=>'<span class="chip" onclick="show(\\''+e.replace(/'/g,"\\\\'")+'\\')">'+esc(e)+'</span>').join('');
 window.show=show;
}}
window.show=show;
D.spine.forEach(b=>{{const d=document.createElement('div');d.className='beat';d.dataset.id=b.id;
 d.innerHTML='<div>'+esc(b.id)+'</div><div class="nar">'+esc(b.narrative)+'</div>';
 d.onclick=()=>show(b.id);beats.appendChild(d)}});
function render(f){{rows.innerHTML='';ids.filter(i=>!f||i.toLowerCase().includes(f)||
 (D.nodes[i].essence||'').toLowerCase().includes(f)).slice(0,400).forEach(i=>{{
 const n=D.nodes[i],d=document.createElement('div');
 d.className='row'+(n.retired?' retired':'');d.dataset.id=i;
 d.innerHTML='<span class="k">'+esc((n.kind||'').slice(0,12))+'</span><span>'+esc(i)+'</span>';
 d.onclick=()=>show(i);rows.appendChild(d)}})}}
q.oninput=()=>render(q.value.toLowerCase());render('');
</script></body></html>"""


def encrypt_bundle(plain: str, password: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=PBKDF2_ITER).derive(password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, plain.encode("utf-8"), None)
    b64 = base64.b64encode(salt + iv + ct).decode("ascii")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>sealed</title>
<style>body{{background:#0f1117;color:#d8dce6;font:15px Georgia,serif;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0}}
form{{text-align:center}}input{{background:#171a23;border:1px solid #262b38;color:#d8dce6;
padding:9px 12px;border-radius:6px;font:inherit;width:260px}}
button{{background:#7aa2f7;border:0;color:#0f1117;padding:9px 16px;border-radius:6px;
font:inherit;margin-left:8px;cursor:pointer}}p{{color:#8a91a3;font-size:13px}}</style>
</head><body><form id="f"><div style="font-size:22px;margin-bottom:12px">&#128274;</div>
<input id="pw" type="password" placeholder="passphrase" autofocus>
<button>open</button><p id="msg">This bundle is sealed. Nothing decrypts server-side.</p></form>
<script>
const B=Uint8Array.from(atob("{b64}"),c=>c.charCodeAt(0));
const salt=B.slice(0,16),iv=B.slice(16,28),ct=B.slice(28);
document.getElementById('f').onsubmit=async e=>{{e.preventDefault();
 const msg=document.getElementById('msg');msg.textContent='deriving key…';
 try{{
  const km=await crypto.subtle.importKey('raw',new TextEncoder().encode(
    document.getElementById('pw').value),'PBKDF2',false,['deriveKey']);
  const key=await crypto.subtle.deriveKey({{name:'PBKDF2',salt,iterations:{PBKDF2_ITER},
    hash:'SHA-256'}},km,{{name:'AES-GCM',length:256}},false,['decrypt']);
  const pt=await crypto.subtle.decrypt({{name:'AES-GCM',iv}},key,ct);
  document.open();document.write(new TextDecoder().decode(pt));document.close();
 }}catch(err){{msg.textContent='wrong passphrase';}}
}};
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", nargs="?", default="subset-sum-itqde")
    ap.add_argument("--out", default="site_export")
    ap.add_argument("--password", default=None)
    ap.add_argument("--plain", action="store_true",
                    help="publish plaintext - PER-CORPUS AUTHOR CALL, never a default")
    a = ap.parse_args()

    data = bake_data(a.corpus)
    inner = inner_html(data)
    out_dir = Path(a.out) / a.corpus
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.plain:
        (out_dir / "index.html").write_text(inner, encoding="utf-8")
        print(f"PLAIN bundle (author's call): {out_dir / 'index.html'}")
    else:
        pw = a.password or os.environ.get("LAPLACE_SITE_PASSWORD") or secrets.token_urlsafe(12)
        (out_dir / "index.html").write_text(encrypt_bundle(inner, pw), encoding="utf-8")
        print(f"sealed bundle: {out_dir / 'index.html'} "
              f"({(out_dir / 'index.html').stat().st_size // 1024} KB)")
        if not a.password and not os.environ.get("LAPLACE_SITE_PASSWORD"):
            print(f"generated passphrase (printed ONCE, bank it): {pw}")
    print(f"nodes baked: {data['n_nodes']}, spine beats: {len(data['spine'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
