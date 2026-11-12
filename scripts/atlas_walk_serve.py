#!/usr/bin/env python3
"""The walk serve — the founding cards at the front door (the cursor-260 agreed slice, cured).

Laws carried by construction (DESIGN_2026-08-24_the-interface-merge.md, digest fadebf57;
codex packet-refusal cures folded; his rulings RUL-20260824-organs-not-scripts and the
handle law folded):
  · CUSTODY AT MINT: every serve's digest-covered payload banks content-addressed into
    evidence/serve_custody/<digest>.json inside this producer — a shown digest ALWAYS
    resolves, by lookup, never by reconstruction script (the three pre-custody digests are
    projection-evidence RED: evidence/WALK_SERVE_SHOWN_2026-08-24/README.md).
  · THE HANDLE LAW (his, verbatim ground in that README): the shown OBJECT freezes; the
    ground HANDLE is logical — content may move beneath it, and a moved ground renders AS
    DRIFT (shown-then vs now), never a silent substitution, never a read-path refusal.
    Refusal (409) lives only on the act path: a verdict cannot cite a moved serve.
  · SPAN DIGEST CONTRACT, stated honestly (codex cure): span_text_sha256 is the sha256 of
    the LF-joined selected lines, terminators normalized away — a TEXT-span digest, not raw
    source bytes; file_sha256 is the raw-byte anchor of the whole file at read.
  · TYPED CLOSURE (codex cure): historical acts close by exact banked id allowlist; every
    future act closes only as record=walk-verdict · verdict=accepted · actor=gerard ·
    shown_handle present AND resolvable in custody. No id-suffix authority.
  · one anchor + rails (card 3 walked) · no geometry beyond typed content (card 2 walked)
  · open state derives from rows; the open count equals the cards rendered
  · residual priced by class · the card schema is his ruled shape whole.
Two registers from one producer. This module's ONLY write is serve custody (append-only,
content-addressed, replayed into the canonical G0 store when it exists — MA5); verdict rows
bank in front_door through laplace.core.records.journal.bank_row.

Runtime law: /usr/bin/python3, system + user site.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

MERGE = "DESIGN_2026-08-24_the-interface-merge.md"
CUSTODY = ROOT / "evidence" / "serve_custody"

#: pre-custody acts, preserved as author events by exact id (never suffix authority);
#: their shown objects are projection-evidence RED — see WALK_SERVE_SHOWN README.
HISTORICAL_CLOSURES = {
    "card2": "VERDICT-20260824-card2-honest-geometry-walked",
    "card3": "VERDICT-20260824-card3-one-viewport-walked",
    "card-ma6": "RES-20260824T210619-founding-card-ma6-walked",
    "card1": "RES-20260824T210700-founding-card1-walked",
    "card-attention": "RES-20260824T210739-founding-card-attention-walked",
}


def custody_resolve(digest: str) -> dict | None:
    """A shown digest resolves to its banked payload, or None — lookup, never a script."""
    p = CUSTODY / f"{digest}.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def custody_verify(digest: str) -> bool:
    """Rehash proof: the digest covers the payload WITHOUT its own serve_digest field."""
    banked = custody_resolve(digest)
    if banked is None:
        return False
    body = {k: v for k, v in banked.items() if k != "serve_digest"}
    return sha256(json.dumps(body, sort_keys=True,
                             ensure_ascii=False).encode("utf-8")).hexdigest() == digest


def resolve_handle(handle: str, root: Path = ROOT, expect_text_sha: str | None = None) -> dict:
    """Exact-span descent: 'PATH#Lstart-Lend' -> the selected lines + digests.

    Misses REFUSE loudly (never a parent echo). A mismatch against ``expect_text_sha``
    is NOT a refusal on this read path: the current content returns WITH a ``drift``
    block (shown-then vs now) — the handle law."""
    if "#L" not in handle:
        return {"handle": handle, "error": "handle must be PATH#Lstart-Lend"}
    path_part, _, span_part = handle.partition("#L")
    try:
        s, _, e = span_part.partition("-L")
        start, end = int(s), int(e)
    except ValueError:
        return {"handle": handle, "error": f"unparseable span L{span_part}"}
    if start < 1 or end < start:
        return {"handle": handle, "error": f"bad range L{start}-L{end}"}
    target = (root / path_part).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        return {"handle": handle, "error": "path escapes the repo root — refused"}
    if not target.is_file():
        return {"handle": handle, "error": f"ABSENT: {path_part} — refused, not substituted"}
    raw = target.read_bytes()
    lines = raw.decode("utf-8", errors="replace").splitlines()
    if end > len(lines):
        return {"handle": handle, "error": f"span ends at L{end} but {path_part} has "
                                           f"{len(lines)} lines — refused, not clipped"}
    span = "\n".join(lines[start - 1:end])
    out = {"handle": handle, "path": path_part, "start": start, "end": end,
           "content": span,
           "span_text_sha256": sha256(span.encode("utf-8")).hexdigest(),
           "file_sha256": sha256(raw).hexdigest()}
    if expect_text_sha and expect_text_sha != out["span_text_sha256"]:
        out["drift"] = {"expected": expect_text_sha, "found": out["span_text_sha256"],
                        "law": "content moved beneath the handle — rendered as drift, "
                               "never substituted silently; the shown-then object lives "
                               "in serve custody"}
    return out


def custody_has(digest: str) -> bool:
    """ONE custody home, extension-agnostic: a digest resolves if any content-addressed
    object carries it (json payloads, md shown-objects, whatever custody holds)."""
    return bool(digest) and any(CUSTODY.glob(f"{digest}.*"))


def _walked_cards() -> dict[str, dict]:
    """Closure state from rows: historical exact ids, else the typed rule (codex cure)."""
    state: dict[str, dict] = {}
    links: dict[str, str] = {}
    hist = {rid: card for card, rid in HISTORICAL_CLOSURES.items()}
    store = ROOT / "corpus_friction" / "work_orders.jsonl"
    rows = []
    for line in store.read_text(encoding="utf-8").splitlines():
        if ("-walked" not in line and "walk-verdict" not in line
                and "shown-custody-link" not in line):
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    for r in rows:                       # pass 1: links lift text-embedded digests to type
        if r.get("record") == "shown-custody-link" and r.get("target") in hist:
            links[str(r["target"])] = str(r.get("shown_handle", ""))
    for r in rows:                       # pass 2: closures, custody stamped from type∪links
        rid = str(r.get("id", ""))
        if rid in hist:
            shown = str(r.get("shown_handle", "") or "") or links.get(rid, "")
            state[hist[rid]] = {"row": rid, "ts": r.get("ts"), "shown": shown,
                                "custody": ("resolves" if custody_has(shown)
                                            else "projection-evidence-RED (pre-custody)")}
            continue
        stage = str(r.get("stage", ""))
        if (r.get("record") == "walk-verdict" and r.get("verdict") == "accepted"
                and r.get("actor") == "gerard" and stage.startswith("founding-")
                and r.get("shown_handle") and custody_has(str(r["shown_handle"]))):
            state[stage.removeprefix("founding-")] = {"row": rid, "ts": r.get("ts"),
                                                      "shown": str(r["shown_handle"]),
                                                      "custody": "resolves"}
    return state


def _cards() -> list[dict]:
    """The founding decision cards; grounds carry a name, a why, and a logical handle."""
    readme = "evidence/WALK_SERVE_SHOWN_2026-08-24/README.md"
    return [
        # the confirmation card lived here 2026-08-24 and RETIRED UNFIRED: the three
        # pre-custody shown objects were recovered under codex's cursor-317 receipt, all
        # rehash-equal (evidence/WALK_SERVE_SHOWN_2026-08-24/). No card content remains —
        # future founding cards are generated from the poured corpus (CR-hand-authored-cards).
    ]


def build() -> dict:
    walked = _walked_cards()
    open_cards = [c for c in _cards() if c["id"] not in walked]
    payload = {
        "serve": "founding-walk",
        "law": "RENDER OF ROWS — open state derives from work_orders at render; custody at "
               "mint (evidence/serve_custody/<digest>.json); verdicts POST to "
               "/front/walkserve citing this serve's digest; ground drift renders, "
               "never substitutes",
        "walked": {k: v for k, v in walked.items()},
        "anchor": open_cards[0] if open_cards else None,
        "rails": open_cards[1:],
        "open_count": len(open_cards),
        "queued_not_served": ["the jubilee schedule (rides the admission ruling)",
                              "stakes A-E (codex's, unchanged, next sitting)"],
        "residual": "withheld: 2 classes — 2 queued cards (named above) · the full merge "
                    "(descend: any ground handle)",
    }
    for c in open_cards:
        for key in ("grounds", "cost_of_delay", "store_write", "residual", "irreversibility"):
            if not c.get(key):
                raise ValueError(f"anti-generic gate: card {c['id']} lacks {key} — refused")
        c["ground_spans"] = []
        for g in c["grounds"]:
            r = resolve_handle(g["handle"])
            c["ground_spans"].append({"handle": g["handle"], "label": g["label"],
                                      "why": g["why"],
                                      "span_text_sha256": r.get("span_text_sha256"),
                                      "error": r.get("error")})
    payload["serve_digest"] = sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    CUSTODY.mkdir(parents=True, exist_ok=True)
    custody_file = CUSTODY / f"{payload['serve_digest']}.json"
    if not custody_file.exists():
        custody_file.write_text(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=1),
            encoding="utf-8")
    payload["produced_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return payload


def _card_html(c: dict, anchor: bool) -> str:
    gs = "".join(
        f'<div class="ground"><button class="gbtn" data-h="{quote(g["handle"], safe="")}"'
        f' data-sha="{escape(g.get("span_text_sha256") or "")}">'
        f'{escape(g["label"])}</button> <span class="dim">{escape(g["why"])}'
        f'{" · UNRESOLVED — refused, shown as such" if g.get("error") else ""}</span>'
        f'<blockquote class="gspan" hidden></blockquote></div>'
        for g in c.get("ground_spans", []))
    opts = "".join(f'<div class="opt"><b>{escape(o["o"])}</b> — {escape(o["c"])}</div>'
                   for o in c["options"])
    body = (f'<div class="why">{escape(c["why_now"])}</div>'
            f'<div class="q">{escape(c["question"])}</div>{opts}'
            f'<div class="meta">Recommend: {escape(c["recommendation"])}</div>'
            f'<div class="meta">Alternative not taken: {escape(c["alternative"])}</div>'
            f'<div class="meta">Blocks: {escape(c["blocks"])} · Cost of delay: '
            f'{escape(c["cost_of_delay"])}</div>'
            f'<div class="meta">Write: {escape(c["store_write"])} · '
            f'{escape(c["irreversibility"])}</div>'
            f'<div class="meta">Grounds — open in place:</div>{gs}'
            f'<div class="meta dim">Residual: {escape(c["residual"])}</div>'
            f'<div class="verbs" data-card="{escape(c["id"])}">'
            f'<button data-v="accept">accept</button>'
            f'<button data-v="amend">amend…</button>'
            f'<button data-v="refuse">redline…</button>'
            f'<span class="echo" aria-live="polite"></span></div>')
    if anchor:
        return f'<section class="card anchor"><h2>{escape(c["glance"])}</h2>{body}</section>'
    return f'<details class="card"><summary>{escape(c["glance"])}</summary>{body}</details>'



KEYS_SNIPPET = (
    '<script>(function(){"use strict";\n'
    '/* the same keys as the front door, derived from the same census — the keyboard\n'
    '   used to die at every page boundary: A opened this page and stranded you. */\n'
    'let P=null;fetch("/front/places").then(r=>r.json()).then(d=>{P=d.places;}).catch(()=>{});\n'
    'document.addEventListener("keydown",function(ev){\n'
    ' const t=ev.target;if(t&&(t.tagName==="INPUT"||t.tagName==="TEXTAREA"))return;\n'
    ' if(ev.metaKey||ev.ctrlKey||ev.altKey)return;\n'
    ' if(ev.key==="Escape"){location.href="/front";return;}\n'
    ' if(!P)return;\n'
    ' const p=P.find(x=>x.key&&x.key.toLowerCase()===ev.key.toLowerCase());\n'
    ' if(!p)return;\n'
    ' location.href=p.kind==="page"?p.href:"/front"+p.href;\n'
    '});})();</script>')


def render_html(b: dict, home: str | None = None) -> str:
    """``home`` is the route back to the surface that sent the reader here.

    This page is its own document, not a route of the shell, so without this argument it
    is a cul-de-sac exactly as /front/atlas was — measured 0 anchors, 0 buttons. That
    went unnoticed for as long as it did because the door was unreachable: it was served
    at /front/walk and named in none of the shell's three hand-maintained nav maps. The
    moment the places census made it reachable, its exit became owed.
    """
    head = ('<meta charset="utf-8"><title>the founding walk</title><style>'
            # THE BAR IS PINNED TO THE VIEWPORT, NOT TO THE COLUMN.
            # First cut copied the atlas board's chrome verbatim — margin:-20px -22px on a
            # sticky bar. That is correct there, where body is full-bleed
            # (margin:0;padding:18px 22px). THIS page is a centred reading column
            # (margin:0 auto;max-width:880px), so the same rule produced a 924px
            # translucent bar floating in a 1280px viewport with 178px of bare gutter
            # either side, and content sliding past it in those gutters. Measured, not
            # guessed: chrome rect x=178 width=924 against viewport 1280.
            # position:fixed with left/right:0 makes the containing block the viewport, so
            # the bar spans it regardless of the page's layout model; the inline padding
            # re-inests its contents to sit exactly on the 880px text column, and never
            # below the column's own gutter on narrow screens.
            '.chrome{position:fixed;left:0;right:0;top:0;z-index:9;'
            'background:rgba(20,22,26,.94);backdrop-filter:blur(6px);'
            'border-bottom:1px solid #2b313b;'
            'padding:10px max(22px,calc((100% - 880px)/2))}'
            '.chrome a{text-decoration:none;font-weight:600}'
            '.chrome a:hover{text-decoration:underline}'
            # fixed leaves the flow, so the page owes itself the height back explicitly
            '.chromepad{height:44px}'
            ':root{color-scheme:dark}'
            'body{background:#14161a;color:#d7dae0;font:15px/1.5 system-ui,sans-serif;'
            'margin:0 auto;max-width:880px;padding:20px 22px}'
            'h1{font-size:19px;margin:0} h2{font-size:17px;margin:0 0 6px}'
            'a{color:#7fb3ff} .dim{color:#7d8a9b;max-width:78ch}'
            '.card{background:#1b2026;border:1px solid #2b313b;border-radius:8px;'
            'padding:13px 16px;margin:11px 0}'
            '.anchor{border-color:#33528a;border-width:2px}'
            'summary{cursor:pointer;font-size:16px;color:#c8d2dd}'
            '.why{color:#98a2b0;margin:4px 0} .q{font-weight:600;margin:8px 0 4px}'
            '.opt{margin:3px 0 3px 10px;border-left:2px solid #2b313b;padding-left:8px}'
            '.meta{font-size:13px;color:#8d99a8;margin:4px 0}'
            '.verbs{margin-top:9px} .verbs button{background:none;border:1px solid #3a4250;'
            'color:#d7dae0;border-radius:5px;padding:4px 13px;margin-right:7px;cursor:pointer}'
            '.verbs textarea{width:100%;margin-top:7px;background:#14161a;color:#d7dae0;'
            'border:1px solid #3a4250;border-radius:5px;padding:6px}'
            '.echo{font-size:13px;color:#9ccc9c;margin-left:8px}'
            '.err{color:#ef9a9a}'
            '.ground{margin:5px 0} .gbtn{background:none;border:none;color:#7fb3ff;'
            'cursor:pointer;padding:0;font-size:13.5px;text-decoration:underline}'
            '.gspan{margin:7px 0 4px;border-left:2px solid #33528a;padding:8px 12px;'
            'background:#161a20;max-height:340px;overflow-y:auto;font-size:13.5px;'
            'white-space:pre-wrap;color:#b9c2cd;border-radius:0}'
            '.gspan .src{color:#5f6b7a;font-size:11.5px;font-family:monospace;'
            'margin-bottom:6px}'
            '.gspan .drift{color:#ffd54f;font-size:12px;margin-bottom:6px}</style>')
    walked_bits = ", ".join(
        f'{escape(k)}{" (RED)" if "RED" in str(v.get("custody", "")) else ""}'
        for k, v in sorted(b["walked"].items())) or "none"
    o = []
    if home:
        o.append(f'<div class="chrome"><a href="{escape(home)}">← the front door</a></div>'
                 f'<div class="chromepad"></div>')
    o += [f'<h1>the founding walk</h1>'
         f'<div class="dim" style="font-size:12px">{escape(b["law"])} · produced '
         f'{escape(b["produced_at"])} · serve digest '
         f'<code>{escape(b["serve_digest"][:20])}…</code> (custody-resolvable)</div>'
         f'<div style="margin:8px 0 2px"><b id="opencount">{b["open_count"]}</b> open '
         f'decision(s) — walked: {walked_bits}</div>']
    if b["anchor"]:
        o.append(_card_html(b["anchor"], True))
    for c in b["rails"]:
        o.append(_card_html(c, False))
    if not b["anchor"]:
        o.append('<div class="card">No open founding cards — every decision here is '
                 'walked and custody-confirmed. The queued classes are the next sitting.</div>')
    o.append(f'<div class="meta dim">{escape(b["residual"])}</div>')
    o.append(f"""<script>
const DIGEST={json.dumps(b["serve_digest"])};
document.querySelectorAll('.gbtn').forEach(g=>g.onclick=async()=>{{
 const bq=g.parentElement.querySelector('.gspan');
 if(!bq.hidden){{bq.hidden=true;return;}}
 if(!bq.dataset.loaded){{
  const r=await fetch('/front/walk?handle='+g.dataset.h+'&expect='+g.dataset.sha+'&format=json');
  const j=await r.json();
  if(j.error){{bq.textContent=j.error;}}
  else{{
   let head='<div class="src">'+j.path+' · L'+j.start+'-L'+j.end+' · text-span sha256:'
    +j.span_text_sha256.slice(0,20)+'…</div>';
   if(j.drift){{head+='<div class="drift">DRIFT — this ground moved since the serve was '
    +'minted (shown-then '+j.drift.expected.slice(0,16)+'…, now '
    +j.drift.found.slice(0,16)+'…). Current content below; the shown-then object lives '
    +'in serve custody.</div>';}}
   bq.innerHTML=head;
   bq.appendChild(document.createTextNode(j.content));}}
  bq.dataset.loaded='1';
 }}
 bq.hidden=false;
}});
document.querySelectorAll('.verbs').forEach(v=>{{
 const card=v.dataset.card, echo=v.querySelector('.echo');
 v.querySelectorAll('button').forEach(btn=>btn.onclick=async()=>{{
  const verdict=btn.dataset.v; let text='';
  if(verdict!=='accept'){{
   let ta=v.querySelector('textarea');
   if(!ta){{ta=document.createElement('textarea');
    ta.placeholder=verdict==='amend'?'your amendment, in your words':'your redline — what failed your eye';
    v.appendChild(ta);ta.focus();return;}}
   text=ta.value.trim();
   if(!text){{echo.textContent='words first — a bare '+verdict+' cures nothing';echo.className='echo err';return;}}
  }}
  const r=await fetch('/front/walkserve',{{method:'POST',headers:{{'Content-Type':'application/json','X-Front-Door':'1'}},
   body:JSON.stringify({{card,verdict,text,shown_handle:DIGEST}})}});
  const j=await r.json();
  if(!r.ok){{echo.textContent=j.error||('refused '+r.status);echo.className='echo err';return;}}
  echo.textContent='banked '+j.banked+' — open count is now '+j.open_count;echo.className='echo';
  document.getElementById('opencount').textContent=j.open_count;
  v.querySelectorAll('button').forEach(x=>x.disabled=true);
 }});
}});
</script>""")
    return head + "\n" + "\n".join(o) + (KEYS_SNIPPET if home else "")


def main() -> int:
    b = build()
    print(json.dumps({"open": b["open_count"], "digest": b["serve_digest"],
                      "walked": sorted(b["walked"]),
                      "custody": str(CUSTODY.relative_to(ROOT))}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
