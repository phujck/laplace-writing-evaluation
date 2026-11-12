#!/usr/bin/env python3
"""export_demo.py — bake the PUBLIC, READ-ONLY TOUR bundle of the live engine interface.

HIS RULINGS (2026-07-23, the eigenengine-page redesign session) — the bundle law:
  * The published demo is REPLACED by a slice of the CURRENT engine interface: the real
    surfaces the scanner serves at HEAD, not a bespoke re-implementation of them.
  * PUBLIC and READ-ONLY: no passphrase gate, no visitor identity, no comment dock, no
    outbox, no token slot. Every non-GET is refused by the shim; the refusal message is
    itself the demonstration of the actor-guarded door.
  * A structured TOUR walks the principal surfaces in production order — conceptric →
    storyboard → artefact → lineage — with the visitor free to click around at every
    station and continue when ready. Subject: the falqon manuscript corpus.
  * SEAL LAW stays absolute (the denylist scan below, unchanged), and a second guard is
    added on his instruction: NO SSG / subset-sum / ITQDE content may enter the bundle.

MECHANISM — bake-by-crawl, never re-implement:
  The exporter raises (or reuses) the real scanner on localhost, crawls the exact GET
  endpoints the four surfaces fetch (enumerated from the panes' own fetchJSON calls),
  and freezes each response into ``data.json`` as a canonical-URL → response table. The
  prepended shim overrides ``fetch``: GETs are served from the table, non-GETs are
  refused, URLs that name real bundle files fall through to disk. The surfaces
  themselves are copied from ``src/laplace`` verbatim (plus the /shared/ asset-path and
  ESM-specifier rewrites the old bundle already proved), so what the visitor uses IS the
  current instrument over frozen real data — stated as such, with the bake commit.

Shape of the bundle (write-set: ``phujck.github.io/demo/`` ONLY)::

    demo/
      index.html       the tour front door — what this is, the four stations, no gate
      conceptric.html  station 1: the graded concept graph (cockpit surface)
      storyboard.html  station 2: the narrative plan over the graph
      artefact.html    station 3: the compiled manuscript + margin (reader surface)
      lineage.html     station 4: the joins — node → section → paragraph
      data.json        {meta, responses:{"<path?sorted-query>": {status, body|json}}}
      baked/           the compiled falqon PDF (pdf.js reads it as a plain file)
      shared/          hymn.css, shell.js, the .mjs module closure, katex/, pdfjs/,
                       vendor/ (copied verbatim; public assets)

    python scripts/export_demo.py [--out <site>/demo] [--port 8770]

Exit: 0 baked · 2 a guard refused the build (seal / SSG violation) · 3 REFUSED TO BAKE —
no scanner could be reached or raised, so nothing was crawled and NOTHING was written
(the existing bundle at --out is left exactly as it was).

NOTE, measured 2026-08-15: when this script has to RAISE a scanner it does not reap it —
the server keeps running on --port after the bake returns. That is load-bearing for a
human re-running the bake, and hostile to any probe that afterwards asks "is a service
up?". The bake now says so out loud rather than leaving it to be discovered.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from service_probe import REFUSAL_EXIT, port_open, refusal_line  # noqa: E402

SHARED_SRC = ROOT / "src" / "laplace" / "web" / "static_shared"
# bundle file ← the template the LIVE ROUTE serves (scanner.py): /conceptric is the
# link-graph map (conceptric_map.html); the growth cockpit (conceptric.html) is its door.
SURFACE_SRC = {
    "conceptric.html": ROOT / "src" / "laplace" / "web" / "conceptric_map.html",
    "conceptric-cockpit.html": ROOT / "src" / "laplace" / "web" / "conceptric.html",
    "storyboard.html": ROOT / "src" / "laplace" / "web" / "storyboard.html",
    "artefact.html": ROOT / "src" / "laplace" / "web" / "artefact.html",
    "lineage.html": ROOT / "src" / "laplace" / "web" / "lineage.html",
}
DEFAULT_OUT = ROOT.parent / "phujck.github.io" / "demo"
DEFAULT_PORT = 8770

CORPUS = "paper_falqon"          # the tour's one subject (his ruling: the falqon example)
PUBLIC_SITE_EMAIL = "eigen@gmccaul.co.uk"   # the engine's public address (his ruling 2026-07-23)
# addresses allowed to ride the bundle: the engine's own, plus the author's published
# byline address (already public on every page footer and in the falqon PDF)
PUBLIC_EMAILS = {PUBLIC_SITE_EMAIL, "gerard.mccaul@gmail.com"}

# ── seal-law denylist (UNCHANGED from the sealed bundle — the law is absolute) ──
_DENY = [
    r"soul/", r"soul_corpus", r"life_corpus", r"collaborator_corpus", r"profiles/",
    r"gerard\.mccaul(?!@gmail\.com)",   # private marker (the public email is allowed, below)
    r'by\s*[:=]\s*["\']gerard',         # the author-identity literal the demo must never carry
    r"\bEIGEN_DIARY\b", r"\bsoul\b",
]
_EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# ── SSG guard (his instruction, this session): the public bundle carries none of it ──
_SSG_RX = re.compile(r"\b(ssg|subset[\s_-]?sum|itqde|qmill)\b", re.IGNORECASE)


class SealViolation(RuntimeError):
    """A denylisted string tried to enter the bundle. Refuse to build."""


class SSGViolation(RuntimeError):
    """An SSG/subset-sum/ITQDE string tried to enter the public bundle. Refuse to build."""


# vendored third-party trees: the hard denylist still runs; the email HEURISTIC does not
# (minified vendor code contains email-shaped random strings — false positives, not leaks)
_VENDORED_PREFIXES = ("shared/pdfjs/", "shared/vendor/", "shared/katex/")


def _seal_law_scan(label: str, text: str) -> None:
    """Refuse on any denylisted string. Runs over EVERY string landing in the bundle."""
    low = text.lower()
    for pat in _DENY:
        m = re.search(pat, text) or re.search(pat, low)
        if m:
            raise SealViolation(f"[{label}] denylist hit {pat!r} near {text[max(0, m.start()-30):m.start()+30]!r}")
    if label.replace("\\", "/").startswith(_VENDORED_PREFIXES):
        return
    for m in _EMAIL_RX.finditer(text):
        if m.group(0).lower() not in PUBLIC_EMAILS:
            raise SealViolation(f"[{label}] non-public email {m.group(0)!r}")


def _ssg_guard(label: str, text: str) -> None:
    """Refuse on any SSG-family string. Same posture as the seal law: refuse, never redact."""
    m = _SSG_RX.search(text)
    if m:
        raise SSGViolation(f"[{label}] SSG-family string {m.group(0)!r} near "
                           f"{text[max(0, m.start()-40):m.start()+40]!r}")


def _redact_nonpublic_emails(text: str) -> tuple[str, int]:
    """Crawled corpus text (tex source, bibliographies) may carry collaborator emails.
    Those are redacted — counted and reported, never silently — before the seal scan runs,
    which then still refuses anything the redaction missed."""
    n = 0

    def sub(m: re.Match) -> str:
        nonlocal n
        if m.group(0).lower() in PUBLIC_EMAILS:
            return m.group(0)
        n += 1
        return "[email-redacted]"      # deliberately NOT email-shaped: the seal scan re-checks

    return _EMAIL_RX.sub(sub, text), n


# ── the scanner: reuse a live one or raise our own (the REAL server, never a stub) ──
def _http_get(port: int, path_qs: str, timeout: float = 30.0) -> tuple[int, bytes, str]:
    url = f"http://127.0.0.1:{port}{path_qs}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "") if e.headers else ""


def _scanner_alive(port: int) -> bool:
    try:
        status, _, _ = _http_get(port, "/corpus/list", timeout=3.0)
        return status == 200
    except Exception:
        return False


class ScannerAbsent(RuntimeError):
    """No scanner could be reached or raised. An absence, not a guard violation and
    not a bake failure — the bundle it would have written is simply not written."""


def _ensure_scanner(port: int) -> str:
    """Reuse a live scanner, else raise one, else REFUSE. Returns a one-line note for
    the report saying which happened (and, when this call raised the server, that the
    server is still running afterwards).

    The wait is bounded and it WATCHES: the old loop was a flat 60 × sleep(1) with no
    look at whether the launcher had already died, so a box with no launcher spent a
    full minute before raising a bare RuntimeError that escaped main() as a traceback
    with exit 1 — indistinguishable, to a caller reading exit codes, from a real
    SealViolation-adjacent failure.
    """
    if _scanner_alive(port):
        return f"reused the scanner already serving on :{port} (raised by someone else)"

    exe = ROOT / ".venv" / "bin" / "laplace-review"
    cmd = [str(exe), "--no-browser", "--tabs", "never", "--port", str(port)]
    if not exe.exists():  # windows venv layout / installed entry point
        cmd = [sys.executable, "-m", "laplace.desktop.offline_launcher",
               "--no-browser", "--tabs", "never", "--port", str(port)]
    try:
        subprocess.run(cmd, check=False, cwd=ROOT, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise ScannerAbsent(
            f"no launcher to raise a scanner with ({cmd[0]}: {exc})") from None
    except subprocess.TimeoutExpired:
        raise ScannerAbsent(
            f"the launcher `{cmd[0]}` did not return inside 120s") from None

    # 30 × 1s: enough for a cold scanner to bind and index, far short of the old minute
    # spent discovering an absence. A listening socket that never answers /corpus/list
    # is reported as exactly that — something is on the port, but it is not the scanner.
    for _ in range(30):
        if _scanner_alive(port):
            return (f"RAISED a scanner on :{port} — it is STILL RUNNING after this bake "
                    "(this script does not reap it; kill it before running any probe "
                    "that asks whether a service is up)")
        time.sleep(1)
    holder = ("something is listening on the port but does not answer /corpus/list"
              if port_open("127.0.0.1", port) else "nothing is listening on the port")
    raise ScannerAbsent(
        f"no scanner on :{port} after raising one and waiting 30s ({holder})")


# ── canonical URL keys: path + sorted query (baker and shim MUST agree) ──────
def _canon(path: str, params: dict | None = None) -> str:
    parsed = urllib.parse.urlsplit(path)
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    for k, v in (params or {}).items():
        pairs.append((k, str(v)))
    pairs.sort()
    qs = urllib.parse.urlencode(pairs)
    return parsed.path + (("?" + qs) if qs else "")


# ── the crawl manifest: exactly the GETs the four surfaces make (from their panes) ──
_VOLATILE_KEYS = {"minted_at", "generated_ts"}   # server stamp-times; frozen to the bake


def _stabilize(obj, bake_iso: str):
    """Replace server stamp-times with the bake commit's own timestamp so a rebuild at
    the same commit is byte-stable (the bundle SAYS everything is frozen at that commit)."""
    if isinstance(obj, dict):
        return {k: (bake_iso if k in _VOLATILE_KEYS and isinstance(v, str)
                    else _stabilize(v, bake_iso)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stabilize(v, bake_iso) for v in obj]
    return obj


def _crawl(port: int, bake_iso: str) -> tuple[dict, bytes, dict]:
    """Return (responses, pdf_bytes, meta_counts). Keys are canonical URLs; every value is
    {"status": int, "json": obj} or {"status": int, "text": str}. Read-only against the
    live scanner; the slice filters below are the bundle's honest boundary."""
    table: dict[str, dict] = {}
    redactions = 0

    def put(path: str, params: dict | None = None, *, required: bool = True,
            postprocess=None) -> dict | None:
        nonlocal redactions
        key = _canon(path, params)
        status, body, ctype = _http_get(port, key)
        if status != 200 and required:
            raise RuntimeError(f"crawl: {key} → {status} (required endpoint)")
        try:
            obj = json.loads(body.decode("utf-8"))
            if postprocess is not None:
                obj = postprocess(obj)
            obj = _stabilize(obj, bake_iso)
            table[key] = {"status": status, "json": obj}
            return obj
        except (UnicodeDecodeError, json.JSONDecodeError):
            text = body.decode("utf-8", errors="replace")
            text, n = _redact_nonpublic_emails(text)
            redactions += n
            if postprocess is not None:
                text = postprocess(text)
            table[key] = {"status": status, "text": text}
            return None

    # the slice boundary: this bundle carries ONE corpus; the list says so honestly
    put("/corpus/list", postprocess=lambda o: {"corpora": [CORPUS], "default": CORPUS})

    # ── station 1: the conceptric map (+ the growth cockpit, its door) ──
    cmap = put("/corpus/map", {"corpus": CORPUS})
    for path in ("/corpus/meta", "/corpus/spine", "/corpus/macros", "/corpus/friction",
                 "/corpus/candidates", "/corpus/grade_stats", "/corpus/co-cited",
                 "/corpus/techniques", "/corpus/gaps", "/corpus/goals"):
        put(path, {"corpus": CORPUS}, required=False)
    for g in (0, 1, 2, 3):
        put("/corpus/grade", {"corpus": CORPUS, "g": g}, required=False)
    put("/surface/contract", {"surface": "conceptric"}, required=False)
    for g in ("tensions", "queue", "coverage", "work-orders", "brief"):
        put(f"/growth/{g}", {"corpus": CORPUS}, required=False)

    # node ids: union over the map + the plan + the lineage index (the inspector's reads)
    node_ids: list[str] = []

    def _collect_ids(obj) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("id", "node", "node_id") and isinstance(v, str) and v not in node_ids:
                    node_ids.append(v)
                else:
                    _collect_ids(v)
        elif isinstance(obj, list):
            for v in obj:
                _collect_ids(v)

    _collect_ids(cmap)

    # ── station 2: the storyboard ──
    plan = put("/storyboard/plan", {"corpus": CORPUS})
    for s in ("spine", "arc", "brief", "coverage"):
        put(f"/storyboard/{s}", {"corpus": CORPUS}, required=False)
    _collect_ids(plan)

    # ── station 3: the artefact reader ──
    def _ctx_post(o: dict) -> dict:
        # the pdf rides the bundle as a plain file; the shim absolutises this at runtime
        o["pdf_endpoint"] = "baked/paper_falqon.pdf"
        return o

    ctx = put("/artefact/context", {"corpus": CORPUS}, postprocess=_ctx_post)
    findings = put("/review/findings", {"corpus": CORPUS}, required=False)
    nodemap = put("/review/nodemap", {"corpus": CORPUS}, required=False)
    put("/review/dismissals", {"corpus": CORPUS}, required=False)
    art = (ctx or {}).get("current_artefact") or {}
    tex_file = art.get("tex", "")
    pdf_file = art.get("pdf", "")
    # every tex fragment the margin can open (the nodemap rows carry repo-relative paths)
    tex_paths: list[str] = []

    def _collect_tex(obj) -> None:
        if isinstance(obj, str):
            if obj.lower().endswith(".tex") and obj not in tex_paths:
                tex_paths.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect_tex(v)
        elif isinstance(obj, list):
            for v in obj:
                _collect_tex(v)

    _collect_tex(nodemap)
    if tex_file and tex_file not in tex_paths:
        tex_paths.insert(0, tex_file)
    for tp in tex_paths[:200]:
        put("/projection/tex", {"corpus": CORPUS, "file": tp}, required=False)
        put("/review/his-hand", {"corpus": CORPUS, "file": tp}, required=False)
        put("/review/compile-log", {"corpus": CORPUS, "file": tp}, required=False)
        put("/projection/follow", {"corpus": CORPUS, "file": tp}, required=False)

    # ── station 4: the lineage ──
    whole = put("/lineage/whole", {"corpus": CORPUS}, required=False)
    put("/lineage/brief", {"corpus": CORPUS}, required=False)
    object_ids: list[str] = []

    def _collect_objects(obj) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("object", "object_id", "oid") and isinstance(v, str) and v not in object_ids:
                    object_ids.append(v)
                else:
                    _collect_objects(v)
        elif isinstance(obj, list):
            for v in obj:
                _collect_objects(v)

    _collect_objects(whole)
    for oid in object_ids[:200]:
        put("/lineage/object", {"corpus": CORPUS, "object": oid}, required=False)
    for nid in node_ids:
        put("/lineage/node", {"corpus": CORPUS, "node": nid}, required=False)

    # ── the per-node reads (the map's descent + the inspector; server param is `id`,
    #     feedback's is `node` — scanner.py's own routing) ──
    for nid in node_ids:
        for path in ("/corpus/content", "/corpus/node", "/corpus/neighborhood",
                     "/corpus/explode", "/corpus/derivation"):
            put(path, {"corpus": CORPUS, "id": nid}, required=False)
        put("/corpus/feedback", {"corpus": CORPUS, "node": nid}, required=False)

    # ── the shared shell's reads ──
    def _journey_post(o):
        # door paths: the four stations map to bundle files; home is the front door.
        route_map = {"/": "index.html", "/conceptric": "conceptric.html",
                     "/conceptric/cockpit": "conceptric-cockpit.html",
                     "/conceptric/map": "conceptric.html",
                     "/storyboard": "storyboard.html", "/artefact": "artefact.html",
                     "/lineage": "lineage.html"}

        def walk(x):
            if isinstance(x, dict):
                if isinstance(x.get("path"), str):
                    p = x["path"].split("?")[0]
                    if p in route_map:
                        x["path"] = route_map[p]
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        walk(o)
        return o

    for params in ({}, {"corpus": CORPUS}):
        for view in (None, "conceptric", "storyboard", "artefact", "lineage"):
            q = dict(params)
            if view:
                q["view"] = view
            put("/shared/journey", q, required=False, postprocess=_journey_post)
    put("/shared/plan", {"corpus": CORPUS}, required=False)
    put("/shared/versions", {"corpus": CORPUS}, required=False)
    put("/shared/ladder", {"corpus": CORPUS}, required=False)
    put("/shared/views", required=False)
    # the slice boundary again: .cockpit.json is the AUTHOR'S personal state (layout,
    # last-visited surfaces across every corpus) — the bundle has no author, so it ships
    # empty. Freezing it raw leaked whatever corpus routes the live session had touched.
    put("/cockpit/state", required=False, postprocess=lambda o: {})

    def _staleness_post(o):
        # the slice boundary again: only the subject corpus's rows ride
        if isinstance(o, dict) and isinstance(o.get("rows"), list):
            o["rows"] = [r for r in o["rows"]
                         if not isinstance(r, dict) or r.get("corpus") in (None, CORPUS)]
        return o

    put("/shared/staleness", required=False, postprocess=_staleness_post)
    put("/shared/staleness", {"corpus": CORPUS}, required=False, postprocess=_staleness_post)

    # ── the pdf (binary; baked as a plain file, NOT a table row) ──
    if not pdf_file:
        raise RuntimeError("crawl: /artefact/context carries no current_artefact.pdf")
    status, pdf_bytes, _ = _http_get(port, _canon("/projection/pdf", {"file": pdf_file}),
                                     timeout=120.0)
    if status != 200 or not pdf_bytes.startswith(b"%PDF"):
        raise RuntimeError(f"crawl: /projection/pdf → {status} (need the compiled falqon pdf)")

    counts = {
        "nodes": len(node_ids),
        "responses": len(table),
        "email_redactions": redactions,
        "version_id": ((ctx or {}).get("current_artefact") or {}).get("version_id", ""),
        "sections": len(((plan or {}).get("sections") or [])) or None,
        "findings": len(((findings or {}).get("findings") or [])) if isinstance(findings, dict) else None,
    }
    return table, pdf_bytes, counts


# ── bake provenance: the commit, not the wall clock (rebuilds are deterministic) ──
def _bake_meta() -> dict:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()

    return {
        "bake_commit": git("rev-parse", "--short", "HEAD"),
        "bake_date": git("log", "-1", "--format=%cs"),
        "bake_iso": git("log", "-1", "--format=%cI"),
        "corpus": CORPUS,
        "read_only": True,
    }


# ── the tour: stations, copy, overlay (register: neutral and informative) ────
def _stations(meta: dict, counts: dict) -> list[dict]:
    v = counts.get("version_id") or "the current candidate"
    return [
        {
            "file": "conceptric.html",
            "title": "The conceptric",
            "sub": "a corpus becomes a graph",
            "body": (
                "Every project starts as a corpus — source files, notes, numerics. The engine "
                "compiles it into a conceptric: a graph of typed nodes (claims, definitions, "
                "results, limitations) and their relations, graded so coarse structure sits "
                "above fine detail. This is the real concept graph of the falqon "
                "quantum-control manuscript, drawn by its links. Click a node to descend into "
                "its content and neighbourhood — the same /corpus reads the author's own "
                "surface makes against the live server. The growth cockpit, one door below, "
                "lists the graph's open tensions: each one a queued decision, kept visible "
                "rather than silently resolved."
            ),
        },
        {
            "file": "storyboard.html",
            "title": "The storyboard",
            "sub": "the graph becomes a plan",
            "body": (
                "A manuscript is not written from the graph directly. The storyboard is the "
                "section plan over it: a spine of sections, each drawing on named concepts, "
                "with coverage tracked — which claims are placed, which are not. This is "
                "the real plan behind the falqon manuscript. Dragging and re-ordering are "
                "author edits: this copy is read-only, so the door refuses them — and the "
                "refusal you see is the door's actual behaviour."
            ),
        },
        {
            "file": "artefact.html",
            "title": "The artefact",
            "sub": "the plan becomes a paper",
            "body": (
                f"The plan is projected into LaTeX and compiled; convergence rounds of "
                f"mechanical review drive the findings ledger toward zero before a version is "
                f"minted. This reader shows {v} — the falqon manuscript's current candidate "
                f"PDF — with its margin of review findings keyed to source. Compile and "
                f"edit are disabled in this read-only copy."
            ),
        },
        {
            "file": "lineage.html",
            "title": "The lineage",
            "sub": "every paragraph traces back",
            "body": (
                "Each paragraph of that PDF joins backward: artefact paragraph → storyboard "
                "section → conceptric nodes → corpus. The lineage surface walks those joins in "
                "both directions, with unresolved links shown as a first-class band rather than "
                "hidden. This is what makes the output auditable: generation is reconstruction "
                "from structure, and the trace is queryable."
            ),
        },
    ]


_TOUR_CSS = r"""
#tour-bar{position:fixed;right:14px;bottom:14px;z-index:9999;max-width:380px;
  background:var(--bg-card,#141a23);border:1px solid var(--border,#2d3744);border-radius:10px;
  box-shadow:0 8px 30px rgba(0,0,0,.5);font:12.5px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;
  color:var(--text,#d7dee8)}
#tour-bar .t-head{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer}
#tour-bar .t-step{color:var(--accent,#c9a96e);font-weight:600;white-space:nowrap}
#tour-bar .t-title{font-weight:600}
#tour-bar .t-sub{color:var(--text-muted,#8b93a3);margin-left:auto;white-space:nowrap}
#tour-bar .t-body{display:none;padding:0 12px 10px;color:var(--text-2,#aeb6c2)}
#tour-bar[data-open="1"] .t-body{display:block}
#tour-bar .t-nav{display:flex;gap:8px;padding:0 12px 10px}
#tour-bar .t-nav a{color:var(--accent,#c9a96e);text-decoration:none;border:1px solid var(--border,#2d3744);
  border-radius:6px;padding:4px 10px}
#tour-bar .t-nav a.t-next{background:var(--accent,#c9a96e);color:#10141c;font-weight:600}
#tour-toast{position:fixed;left:50%;bottom:64px;transform:translateX(-50%);z-index:9999;display:none;
  background:#141a23;border:1px solid #2d3744;border-radius:8px;padding:8px 14px;font:12px/1.4 sans-serif;
  color:#d7dee8;max-width:80vw}
#tour-banner{position:sticky;top:0;z-index:9998;background:#10141c;border-bottom:1px solid #2d3744;
  color:#8b93a3;font:11.5px/1.5 ui-monospace,monospace;padding:4px 12px;display:flex;gap:14px;flex-wrap:wrap}
#tour-banner b{color:#c9a96e;font-weight:600}
#tour-banner a{color:#7eb8da;text-decoration:none}
@media (max-width:480px){#tour-bar{left:10px;right:10px;max-width:none}}
"""

# The shim: fetch table + read-only refusal + nav lock + tour overlay. Prepended into
# every station page as the FIRST head script so the override installs before any module.
_SHIM_TEMPLATE = r"""
(function(){
  "use strict";
  var META = __META__;
  var STATIONS = __STATIONS__;
  var HERE = location.pathname.split("/").pop() || "index.html";

  // ── the response table: fetched once; every intercepted call awaits it ──
  var TABLE = null;
  var READY = fetch(new URL("data.json", document.baseURI)).then(function(r){ return r.json(); })
    .then(function(db){ TABLE = db.responses || {}; return TABLE; })
    .catch(function(e){ TABLE = {}; toast("data.json failed to load — the slice cannot serve reads"); throw e; });

  function canon(url){
    var u = new URL(url, document.baseURI);
    var pairs = []; u.searchParams.forEach(function(v,k){ pairs.push([k,v]); });
    pairs.sort(function(a,b){ return a[0]<b[0]?-1:a[0]>b[0]?1:a[1]<b[1]?-1:a[1]>b[1]?1:0; });
    var qs = pairs.map(function(p){ return encodeURIComponent(p[0])+"="+encodeURIComponent(p[1]); }).join("&");
    return u.pathname + (qs ? "?"+qs : "");
  }

  var _fetch = window.fetch.bind(window);
  window.fetch = function(input, init){
    var url = (typeof input === "string") ? input : (input && input.url) || "";
    var method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
    var u = new URL(url, document.baseURI);
    if (u.origin !== location.origin) {
      return Promise.resolve(new Response(JSON.stringify({error:"offline bundle — no external hosts"}),
        {status:403, headers:{"Content-Type":"application/json"}}));
    }
    // real bundle files carry an extension (shared assets, the baked pdf, data.json);
    // API paths never do (/shared/journey, /corpus/co-cited) — those ride the table.
    if (/\.[a-z0-9]+$/i.test(u.pathname)) {
      return _fetch(input, init);
    }
    if (method !== "GET") {
      return Promise.resolve(new Response(JSON.stringify(
        {error:"read-only slice — author verbs run only in the local engine, behind its actor guard"}),
        {status:403, headers:{"Content-Type":"application/json"}}));
    }
    return READY.then(function(T){
      var row = T[canon(u.href)];
      if (!row && !u.searchParams.has("corpus")) {
        // a naked load (no ?corpus=) still lands on the slice's one subject
        var u2 = new URL(u.href); u2.searchParams.set("corpus", META.corpus);
        row = T[canon(u2.href)];
      }
      if (!row) {
        return new Response(JSON.stringify({error:"not in this baked slice"}),
          {status:404, headers:{"Content-Type":"application/json"}});
      }
      var body, ctype;
      if ("json" in row) {
        var obj = row.json;
        if (canon(u.href).indexOf("/artefact/context") === 0 && obj && obj.pdf_endpoint) {
          obj = JSON.parse(JSON.stringify(obj));
          obj.pdf_endpoint = new URL(obj.pdf_endpoint, document.baseURI).href;
        }
        body = JSON.stringify(obj); ctype = "application/json";
      } else {
        body = row.text; ctype = "text/plain; charset=utf-8";
      }
      return new Response(body, {status: row.status || 200, headers: {"Content-Type": ctype}});
    });
  };

  // ── nav lock: station routes go to station files; anything else gets an honest note ──
  var ROUTES = {"/": "index.html", "/conceptric": "conceptric.html",
                "/conceptric/cockpit": "conceptric-cockpit.html",
                "/conceptric/map": "conceptric.html",
                "/storyboard": "storyboard.html", "/artefact": "artefact.html",
                "/lineage": "lineage.html"};
  document.addEventListener("click", function(ev){
    var a = ev.target && ev.target.closest && ev.target.closest("a[href]");
    if (!a) return;
    var href = a.getAttribute("href") || "";
    if (!href.startsWith("/")) return;                       // relative links are bundle-local
    var path = href.split("?")[0];
    ev.preventDefault();
    if (ROUTES[path]) {
      var q = href.indexOf("?") >= 0 ? href.slice(href.indexOf("?")) : "";
      location.href = ROUTES[path] + q;
    } else {
      toast("that surface is not in this baked slice — it runs in the local engine");
    }
  }, true);

  function toast(msg){
    var t = document.getElementById("tour-toast");
    if (!t) return;
    t.textContent = msg; t.style.display = "block";
    clearTimeout(toast._h); toast._h = setTimeout(function(){ t.style.display = "none"; }, 3200);
  }

  // ── the guarded navigator: every programmatic navigation in the baked surfaces is
  //    routed here (bake-time patch), so a live-only door shows a notice, never a 404 ──
  window.__demoNav = function(href){
    href = String(href || "");
    var qi = href.indexOf("?");
    var q = qi >= 0 ? href.slice(qi) : "";
    var p = qi >= 0 ? href.slice(0, qi) : href;
    if (!p || p === "/") { location.href = "index.html"; return; }
    if (p.charAt(0) !== "/") { location.href = href; return; }      // bundle-relative: real file
    if (/\.html$/.test(p)) { location.href = href; return; }        // absolute file path: real
    if (ROUTES[p]) { location.href = ROUTES[p] + q; return; }
    toast("that door opens a live surface that is not in this baked copy — it runs in the local engine");
  };

  // ── banner + tour bar ──
  function mount(){
    var css = document.createElement("style"); css.textContent = __TOUR_CSS__;
    document.head.appendChild(css);

    var banner = document.createElement("div"); banner.id = "tour-banner";
    banner.innerHTML = "<span><b>EigenEngine</b> — read-only slice of the live interface</span>" +
      "<span>corpus: " + META.corpus + "</span>" +
      "<span>baked at commit " + META.bake_commit + " · " + META.bake_date + "</span>" +
      "<span><a href='/eigenengine.html'>about the engine</a></span>";
    document.body.prepend(banner);

    var t = document.createElement("div"); t.id = "tour-toast"; document.body.appendChild(t);

    var idx = -1;
    for (var i = 0; i < STATIONS.length; i++) if (STATIONS[i].file === HERE) idx = i;
    if (idx < 0) {
      // a door off the main path (e.g. the growth cockpit): keep the way back visible
      var d = document.createElement("div"); d.id = "tour-bar"; d.setAttribute("data-open","0");
      d.innerHTML = "<div class='t-nav' style='padding:10px 12px'>" +
        "<a href='conceptric.html'>&#8592; back to the tour</a></div>";
      document.body.appendChild(d);
      return;
    }
    var s = STATIONS[idx];
    var bar = document.createElement("div"); bar.id = "tour-bar";
    var open = (sessionStorage.getItem("__tour_open") || "1") === "1";
    bar.setAttribute("data-open", open ? "1" : "0");
    var q = "?corpus=" + encodeURIComponent(META.corpus);
    var prev = (idx > 0 ? STATIONS[idx-1].file + q : "index.html");
    var next = idx < STATIONS.length - 1 ? STATIONS[idx+1].file + q : null;
    bar.innerHTML =
      "<div class='t-head'><span class='t-step'>" + (idx+1) + "/" + STATIONS.length + "</span>" +
      "<span class='t-title'>" + s.title + "</span><span class='t-sub'>" + s.sub + "</span></div>" +
      "<div class='t-body'>" + s.body + "</div>" +
      "<div class='t-nav'><a href='" + prev + "'>&#8592; back</a>" +
      (next ? "<a class='t-next' href='" + next + "'>continue the tour &#8594;</a>"
            : "<a class='t-next' href='index.html'>finish &#8594;</a>") + "</div>";

    bar.querySelector(".t-head").addEventListener("click", function(){
      var v = bar.getAttribute("data-open") === "1" ? "0" : "1";
      bar.setAttribute("data-open", v); sessionStorage.setItem("__tour_open", v);
    });
    document.body.appendChild(bar);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
"""


def _shim_js(meta: dict, stations: list[dict]) -> str:
    return (_SHIM_TEMPLATE
            .replace("__META__", json.dumps(meta))
            .replace("__STATIONS__", json.dumps(stations))
            .replace("__TOUR_CSS__", json.dumps(_TOUR_CSS)))


# ── the front door: index.html — no gate, no name, the stations previewed ────
def build_index_html(meta: dict, counts: dict, stations: list[dict]) -> str:
    q = f"?corpus={meta['corpus']}"
    rows = "".join(
        f"""<a class="st" href="{s['file']}{q}"><span class="n">{i+1}</span>
        <span class="t">{s['title']}</span><span class="s">{s['sub']}</span></a>"""
        for i, s in enumerate(stations))
    n_resp = counts.get("responses", 0)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EigenEngine — a read-only slice of the live interface</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ccircle cx='8' cy='8' r='7' fill='%23c9a96e'/%3E%3C/svg%3E">
<style>
  :root{{ color-scheme: dark; }}
  html,body{{margin:0;min-height:100%;background:#0e1116;color:#d7dee8;
    font:15px/1.65 -apple-system,Segoe UI,Roboto,sans-serif}}
  .wrap{{max-width:640px;margin:0 auto;padding:48px 20px}}
  h1{{font-size:22px;margin:0 0 6px}} h1 b{{color:#c9a96e}}
  p.lede{{color:#aeb6c2;margin:0 0 22px}}
  .facts{{font:12px/1.7 ui-monospace,monospace;color:#8b93a3;border-top:1px solid #222a36;
    border-bottom:1px solid #222a36;padding:10px 0;margin:0 0 26px}}
  .st{{display:grid;grid-template-columns:28px 1fr;gap:2px 12px;align-items:baseline;
    text-decoration:none;color:inherit;border:1px solid #2d3744;border-radius:10px;
    padding:12px 16px;margin:0 0 10px;background:#141a23}}
  .st:hover{{border-color:#c9a96e}}
  .st .n{{grid-row:span 2;color:#c9a96e;font:600 18px ui-monospace,monospace}}
  .st .t{{font-weight:600}} .st .s{{color:#8b93a3;font-size:13px}}
  .begin{{display:inline-block;margin-top:14px;background:#c9a96e;color:#10141c;font-weight:700;
    border-radius:8px;padding:11px 22px;text-decoration:none}}
  .note{{font-size:12.5px;color:#8b93a3;margin-top:22px;border-top:1px solid #222a36;padding-top:14px}}
  a{{color:#7eb8da}}
</style>
</head>
<body>
  <div class="wrap">
    <h1><b>EigenEngine</b> — a slice of the live interface</h1>
    <p class="lede">These are four of the engine's real working surfaces, frozen with the real
      data of one manuscript project — the falqon quantum-control paper — and served entirely
      from this page's own files. No account, no server, nothing recorded. Click around freely
      at each station; the tour bar carries you to the next.</p>
    <div class="facts">corpus: {meta['corpus']} · {n_resp} baked reads · baked at commit
      {meta['bake_commit']} ({meta['bake_date']}) · read-only: editing is disabled, and the
      refusals shown are the doors' real behaviour</div>
    {rows}
    <a class="begin" href="{stations[0]['file']}{q}">Enter at station 1 &#8594;</a>
    <p class="note">What this is: the engine compiles a source corpus into a typed concept graph
      (the conceptric), plans a manuscript over it (the storyboard), projects and converges the
      compiled artefact under mechanical review, and keeps the full trace (the lineage). The
      surfaces here are the same HTML and modules the local instrument serves, baked at the
      commit named above. Context: <a href="/eigenengine.html">the EigenEngine page</a>.</p>
  </div>
</body>
</html>
"""


# ── ESM machinery (proven in the sealed bundle; kept) ────────────────────────
_ESM_ABS_IMPORT_RX = re.compile(
    r"""((?:from|import)\s*\(?\s*["'])(/shared/[\w./-]+\.mjs)(["'])""")


def _shared_mjs_imports(text: str) -> list[str]:
    out: list[str] = []
    for m in _ESM_ABS_IMPORT_RX.finditer(text):
        spec = m.group(2)
        if spec not in out:
            out.append(spec)
    return out


def _rewrite_esm_imports(text: str, referrer_dir: str) -> str:
    def sub(m: re.Match) -> str:
        target = m.group(2)[1:]
        rel = posixpath.relpath(target, start=referrer_dir or ".")
        if not rel.startswith(("./", "../")):
            rel = "./" + rel
        return m.group(1) + rel + m.group(3)
    return _ESM_ABS_IMPORT_RX.sub(sub, text)


# ── content patches over copied modules (audited: raise if the literal moved) ──
def _patch_shell(text: str) -> str:
    """shell.js injects hymn.css/KaTeX with absolute /shared/ hrefs; under /demo/ those
    must be document-relative. The /shared/journey etc. FETCHES stay absolute — the shim
    serves them from the table. Its three programmatic navigations (nav doors, the brand,
    the corpus switch) route through the shim's guarded navigator so a live-only door
    shows a notice instead of a static 404."""
    out = text
    for a, b in (("/shared/hymn.css", "shared/hymn.css"),
                 ("/shared/katex/", "shared/katex/")):
        if a not in out:
            raise RuntimeError(f"shell.js changed — {a!r} asset injection moved; re-audit the shell")
        out = out.replace(a, b)
    navs = [
        ('location.href = a.dataset.path + (cur ? "?corpus="+ec(cur) : "");',
         'window.__demoNav(a.dataset.path + (cur ? "?corpus="+ec(cur) : ""));'),
        ('location.href = "/" + (cur ? "?corpus="+ec(cur) : "");',
         'window.__demoNav("/" + (cur ? "?corpus="+ec(cur) : ""));'),
        ("location.href = u.pathname + u.search;",
         "window.__demoNav(u.pathname + u.search);"),
    ]
    for a, b in navs:
        if a not in out:
            raise RuntimeError(f"shell.js changed — navigation shape {a!r} moved; re-audit")
        out = out.replace(a, b)
    return out


def _patch_storyboard_panes(text: str) -> str:
    """The plan-write attribution constant and the run-tray call-site carry the author's
    name at HEAD. Author verbs are refused by the shim, but the seal law refuses to SHIP
    the literal regardless — patch to the demo idiom, raise if the shapes moved."""
    if 'const ACTOR = "gerard"' not in text:
        raise RuntimeError('storyboard-panes.mjs changed — const ACTOR literal moved; re-audit')
    if 'actor: "gerard"' not in text:
        raise RuntimeError('storyboard-panes.mjs changed — run-tray actor call-site moved; re-audit')
    return (text.replace('const ACTOR = "gerard"', 'const ACTOR = "demo-visitor"')
                .replace('actor: "gerard"', 'actor: "demo-visitor"'))


def _patch_cockpit_panes(text: str) -> str:
    if 'by: "gerard"' not in text:
        raise RuntimeError('cockpit-panes.mjs changed — by:"gerard" literal moved; re-audit')
    out = text.replace('by: "gerard"', 'by: "demo-visitor"')
    # the ownership comparison (renders HIS feedback rows with owner styling) also carries
    # the quoted name; the code-belt law admits NO author literal in shipped code, so the
    # comparison is patched to a token no data row carries — his historical rows render
    # generic in this one tray, a named cost, not an accident.
    if '=== "gerard"' in out:
        out = out.replace('=== "gerard"', '=== "__author__"')
    return out


def _patch_artefact_panes(text: str) -> str:
    """pdf.js's workerSrc is a plain root-absolute STRING (not an ESM import, so the
    specifier rewrite never touches it); under /demo/ it 404s and pdf.js falls back to a
    'fake worker' dynamic import that also fails — the reader dies. Resolve it against
    the document at runtime instead."""
    lit = 'mod.GlobalWorkerOptions.workerSrc = "/shared/pdfjs/pdf.worker.min.mjs";'
    if lit not in text:
        raise RuntimeError("artefact-panes.mjs changed — the pdf.js workerSrc literal moved; "
                           "re-audit before shipping the demo")
    out = text.replace(
        lit,
        'mod.GlobalWorkerOptions.workerSrc = '
        'new URL("shared/pdfjs/pdf.worker.min.mjs", document.baseURI).href;')
    # the finding-row door navigates to a DATA-carried target; guard it
    door = "const to = gd.dataset.goto; if (to) window.location.href = to; return; }"
    if door not in out:
        raise RuntimeError("artefact-panes.mjs changed — the adoor navigation moved; re-audit")
    return out.replace(
        door, "const to = gd.dataset.goto; if (to) window.__demoNav(to); return; }")


def _patch_lineage_panes(text: str) -> str:
    """The corpus switch navigates by pathname; guard it through the shim's navigator."""
    nav = "location.href = u.pathname + u.search;"
    if nav not in text:
        raise RuntimeError("lineage-panes.mjs changed — the corpus-switch navigation moved; re-audit")
    return text.replace(nav, "window.__demoNav(u.pathname + u.search);")


def _patch_run_tray(text: str) -> str:
    """W-era run-tray dropped the default actor deliberately. Assert the drop held."""
    if re.search(r'opts\.actor\s*\|\|\s*"gerard"', text):
        raise RuntimeError("run-tray.mjs regressed — a default author actor is back; re-audit")
    return text


_MJS_PATCHERS = {
    "shell.js": _patch_shell,
    "storyboard-panes.mjs": _patch_storyboard_panes,
    "cockpit-panes.mjs": _patch_cockpit_panes,
    "artefact-panes.mjs": _patch_artefact_panes,
    "lineage-panes.mjs": _patch_lineage_panes,
    "run-tray.mjs": _patch_run_tray,
}

# in-page route literals: navigations assigned via location.href in panes/surfaces
_ROUTE_LITERALS = [
    ("'/conceptric/cockpit?corpus=", "'conceptric-cockpit.html?corpus="),
    ('"/conceptric/cockpit?corpus=', '"conceptric-cockpit.html?corpus='),
    ("'/conceptric/map?corpus=", "'conceptric.html?corpus="),
    ('"/conceptric/map?corpus=', '"conceptric.html?corpus='),
    ("'/conceptric?corpus=", "'conceptric.html?corpus="),
    ('"/conceptric?corpus=', '"conceptric.html?corpus='),
    ("'/storyboard?corpus=", "'storyboard.html?corpus="),
    ('"/storyboard?corpus=', '"storyboard.html?corpus='),
    ("'/artefact?corpus=", "'artefact.html?corpus="),
    ('"/artefact?corpus=', '"artefact.html?corpus='),
    ("'/lineage?corpus=", "'lineage.html?corpus="),
    ('"/lineage?corpus=', '"lineage.html?corpus='),
]


def _rewrite_routes(text: str) -> str:
    for a, b in _ROUTE_LITERALS:
        text = text.replace(a, b)
    return text


def _copy_shared(out: Path) -> list[str]:
    """Copy hymn.css + shell.js + the transitive .mjs closure of the four surfaces, plus
    the vendored asset trees (katex/, pdfjs/, vendor/). Mechanical: the seed set is read
    from each surface's own source, never hardcoded."""
    dst = out / "shared"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    # hymn.css names its @font-face sources root-absolutely (/shared/fonts/...); under
    # /demo/ those resolve to the site root and 404. CSS urls resolve relative to the
    # stylesheet, so "fonts/..." lands on demo/shared/fonts/ wherever the bundle mounts.
    hymn = (SHARED_SRC / "hymn.css").read_text(encoding="utf-8")
    if "/shared/fonts/" not in hymn:
        raise RuntimeError("hymn.css changed — the /shared/fonts/ @font-face urls moved; re-audit")
    (dst / "hymn.css").write_text(hymn.replace("/shared/fonts/", "fonts/"), encoding="utf-8")
    (dst / "shell.js").write_text(
        _rewrite_routes(_patch_shell((SHARED_SRC / "shell.js").read_text(encoding="utf-8"))),
        encoding="utf-8")
    ins = SHARED_SRC / "inspector.js"
    if ins.exists():
        text = ins.read_text(encoding="utf-8")
        if 'by: "gerard"' in text or "by: 'gerard'" in text:
            raise RuntimeError("inspector.js carries an author literal again — re-audit before shipping")
        (dst / "inspector.js").write_text(_rewrite_routes(text), encoding="utf-8")
    for tree in ("katex", "pdfjs", "vendor", "fonts"):
        src_tree = SHARED_SRC / tree
        if src_tree.is_dir():
            shutil.copytree(src_tree, dst / tree)

    pending: list[str] = []
    for src_path in SURFACE_SRC.values():
        for spec in _shared_mjs_imports(src_path.read_text(encoding="utf-8")):
            if spec not in pending:
                pending.append(spec)
    copied: list[str] = []
    seen: set[str] = set()
    while pending:
        spec = pending.pop(0)
        if spec in seen:
            continue
        seen.add(spec)
        rel = spec[len("/shared/"):]
        src_path = SHARED_SRC / rel
        if not src_path.is_file():
            raise RuntimeError(f"surface imports {spec!r} but {src_path} does not exist — "
                               "the ESM module graph is broken")
        text = src_path.read_text(encoding="utf-8")
        for dep in _shared_mjs_imports(text):
            if dep not in seen and dep not in pending:
                pending.append(dep)
        patch = _MJS_PATCHERS.get(rel)
        if patch is not None:
            text = patch(text)
        text = _rewrite_routes(text)
        referrer_dir = posixpath.dirname(posixpath.join("shared", rel))
        out_path = dst / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_rewrite_esm_imports(text, referrer_dir), encoding="utf-8")
        copied.append(rel)
    return copied


def build_surface_html(name: str, shim: str) -> str:
    src = SURFACE_SRC[name].read_text(encoding="utf-8")
    src = src.replace('href="/shared/', 'href="shared/').replace('src="/shared/', 'src="shared/')
    src = _rewrite_esm_imports(src, "")
    src = _rewrite_routes(src)
    icon = ("<link rel=\"icon\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'"
            " viewBox='0 0 16 16'%3E%3Ccircle cx='8' cy='8' r='7' fill='%23c9a96e'/%3E%3C/svg%3E\">\n")
    shim_tag = icon + "<script>\n" + shim + "\n</script>\n"
    if "<head>" not in src:
        raise RuntimeError(f"{name}: no <head> to prepend the shim into")
    return src.replace("<head>", "<head>\n" + shim_tag, 1)


# ── guards over the whole bundle, then write ─────────────────────────────────
def _guard_all(label_texts: list[tuple[str, str]]) -> None:
    for label, text in label_texts:
        _seal_law_scan(label, text)
        _ssg_guard(label, text)


def export(out: Path, port: int = DEFAULT_PORT) -> dict:
    scanner_note = _ensure_scanner(port)
    meta = _bake_meta()
    table, pdf_bytes, counts = _crawl(port, meta["bake_iso"])
    stations = _stations(meta, counts)
    shim = _shim_js(meta, stations)

    db_json = json.dumps({"meta": meta, "responses": table},
                         ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    index_html = build_index_html(meta, counts, stations)
    pages = {name: build_surface_html(name, shim) for name in SURFACE_SRC}

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shared_mjs = _copy_shared(out)

    # guards: every text that lands in the bundle, INCLUDING the copied shared assets
    checks: list[tuple[str, str]] = [("data.json", db_json), ("index.html", index_html)]
    checks += [(n, t) for n, t in pages.items()]
    for p in out.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".js", ".css", ".html", ".json", ".md", ".mjs"):
            checks.append((str(p.relative_to(out)),
                           p.read_text(encoding="utf-8", errors="ignore")))
    _guard_all(checks)

    (out / "data.json").write_text(db_json, encoding="utf-8")
    (out / "index.html").write_text(index_html, encoding="utf-8")
    for name, text in pages.items():
        (out / name).write_text(text, encoding="utf-8")
    (out / "baked").mkdir(exist_ok=True)
    (out / "baked" / "paper_falqon.pdf").write_bytes(pdf_bytes)

    return {
        "out": str(out),
        "meta": meta,
        "counts": counts,
        "scanner": scanner_note,
        "pages": sorted(pages) + ["index.html"],
        "data_json_bytes": len(db_json),
        "pdf_bytes": len(pdf_bytes),
        "shared_mjs_modules": shared_mjs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="bake the public read-only tour bundle")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output demo/ dir")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="scanner port (default 8770)")
    a = ap.parse_args()
    try:
        rep = export(Path(a.out), a.port)
    except ScannerAbsent as e:
        # An absent server is not a guard violation and not a bake failure. The bundle
        # at --out is untouched: the crawl runs entirely before the output dir is
        # rebuilt, so a refusal here cannot have half-written anything.
        print(refusal_line("DEMO BAKE", f"a scanner on :{a.port}", [str(e)],
                           verb="BAKE"), file=sys.stderr)
        print(f"  {a.out} was NOT rebuilt and NOT deleted — the existing bundle stands.",
              file=sys.stderr)
        return REFUSAL_EXIT
    except (SealViolation, SSGViolation) as e:
        print(f"GUARD VIOLATION — refused to build: {e}", file=sys.stderr)
        return 2
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
