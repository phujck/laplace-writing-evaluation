#!/usr/bin/env python3
"""build_og_image.py — the eigenengine page's social sharing card (1200x630).

Drawn from the same generated data file the page uses (the real falqon concept graph,
real counts), rendered by headless chromium, written to the site's assets. Rerun after
build_eigenengine_page_data.py when the data moves.

    python scripts/site_assets/build_og_image.py [--out <site>/assets/img/og-eigenengine.png]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SITE = ROOT.parent / "phujck.github.io"
DEFAULT_OUT = SITE / "assets" / "img" / "og-eigenengine.png"
DATA = SITE / "assets" / "js" / "eigenengine-page-data.js"
CHROMIUM = "/opt/pw-browsers/chromium"

KIND_HUES = {"def": "#16A085", "claim": "#4A90D9", "limitation": "#D35400",
             "result": "#9B5DE5"}
NEUTRAL = "#6b7280"

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;width:1200px;height:630px;background:#0a0e1a;color:#e8e6e3;
    font-family:Georgia,'Times New Roman',serif;overflow:hidden;position:relative}
  .wrap{position:absolute;inset:0;padding:64px 72px;box-sizing:border-box}
  h1{font-size:88px;margin:0;letter-spacing:-1px;font-weight:700;
    font-family:Verdana,Geneva,sans-serif}
  .mark{font-style:italic;color:#9ca3af;font-size:30px;margin-left:18px}
  .def{font-size:31px;line-height:1.5;color:#c9cdd6;max-width:660px;margin-top:26px}
  .def b{color:#c9a96e;font-weight:600}
  .band{position:absolute;left:72px;bottom:64px;display:flex;gap:14px;align-items:center;
    font-family:'Courier New',monospace;font-size:21px;color:#8b93a3}
  .band .stage{border:1px solid rgba(255,255,255,0.16);border-radius:8px;
    padding:10px 18px;color:#e8e6e3}
  .band .stage.hot{border-color:#c9a96e;color:#c9a96e}
  .band .arr{color:#4b5563}
  svg{position:absolute;right:-110px;top:-70px;opacity:0.8}
  .site{position:absolute;right:72px;top:76px;font-family:'Courier New',monospace;
    font-size:22px;color:#c9a96e;background:rgba(10,14,26,0.85);padding:4px 10px;
    border-radius:6px}
</style></head><body>
  <svg width="620" height="700" viewBox="0 0 1000 620">__GRAPH__</svg>
  <div class="wrap">
    <h1>EigenEngine<span class="mark">Ê|gen&#x27E9;</span></h1>
    <p class="def">A <b>learning engine</b>: work deposits into a graded concept memory,
      and everything it publishes is a projection of the structure it has learned.</p>
    <div class="band">
      <span class="stage">corpus</span><span class="arr">&#8594;</span>
      <span class="stage hot">conceptric</span><span class="arr">&#8594;</span>
      <span class="stage">storyboard</span><span class="arr">&#8594;</span>
      <span class="stage">review</span><span class="arr">&#8594;</span>
      <span class="stage">artefact</span>
    </div>
    <div class="site">gmccaul.co.uk/eigenengine</div>
  </div>
</body></html>"""


def graph_svg() -> str:
    txt = DATA.read_text(encoding="utf-8")
    d = json.loads(txt[len("window.EE = "):].rstrip().rstrip(";"))
    nodes = d["conceptric"]["nodes"]
    edges = d["conceptric"]["edges"]
    by_id = {n["id"]: n for n in nodes}
    deg: dict[str, int] = {}
    for e in edges:
        deg[e["src"]] = deg.get(e["src"], 0) + 1
        deg[e["dst"]] = deg.get(e["dst"], 0) + 1
    parts = []
    for e in edges:
        a, b = by_id.get(e["src"]), by_id.get(e["dst"])
        if a and b:
            parts.append(f'<line x1="{a["x"]}" y1="{a["y"]}" x2="{b["x"]}" y2="{b["y"]}" '
                         'stroke="rgba(255,255,255,0.14)" stroke-width="1.4"/>')
    for n in nodes:
        r = min(15, 5 + deg.get(n["id"], 0) * 0.8)
        hue = KIND_HUES.get(n["kind"], NEUTRAL)
        parts.append(f'<circle cx="{n["x"]}" cy="{n["y"]}" r="{r:.1f}" fill="{hue}"/>')
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    html = HTML.replace("__GRAPH__", graph_svg())
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as td:
        page_path = Path(td) / "og.html"
        page_path.write_text(html, encoding="utf-8")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROMIUM)
            pg = browser.new_context(viewport={"width": 1200, "height": 630}).new_page()
            pg.goto(page_path.as_uri())
            pg.wait_for_timeout(400)
            out = Path(a.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            pg.screenshot(path=str(out))
            browser.close()
    print(json.dumps({"out": str(out), "bytes": out.stat().st_size}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
