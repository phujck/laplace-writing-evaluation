"""W4.2 — the CodeMirror pane + continuous synctex-follow (both directions).

The stage's fail-closed contract, one leg per claim:

1. THE LOCAL-TEX-PATH LAW (pure) — the synctex binary resolves in one order:
   ``$LAPLACE_SYNCTEX_BIN`` → ``shutil.which('synctex')`` → honest ``None``. Never
   a hardcoded path (the banked disease). When ``which`` returns ``None`` and the
   env is unset, resolution is ``None`` and every synctex feature DEGRADES HONESTLY
   (present:false / absent:true, a reason, a fix naming the env var) — never a 500.

2. STALENESS HONESTY (pure) — ``_follow_fresh`` requires the existing build owner's
   verified consumed inputs and outputs, including the exact SyncTeX map.
   ``follow_status`` reports missing or changed evidence in the ``.hy-stale`` shape.

3. HAPPY PATH (skips without latexmk/synctex) — a tiny fixture compiled by the
   actual recompile owner resolves a known line↔page pair BOTH ways: source→pdf
   (``synctex_locate``) and pdf→source (``synctex_anchor``).

4. THE ECHO GUARD (skips without Chromium) — the bidirectional-follow suppression
   token: a follow-driven move does NOT mint a reverse resolve while the window is
   open, and DOES resolve once it elapses. Driven headless through the guard factory
   the page exposes (``window.__pvFollowGuardFactory``).

5. THE CM PANE MOUNTS (skips without Chromium) — /projection swaps the textarea for
   a real CM6 EditorView that PAINTS and loads the source, with zero console errors
   (endpoint-green is not enough — the blank-page class only shows under a renderer).

Windows discipline: pathlib throughout; the synctex/latexmk binaries resolve per
the law, so a box without them skips honestly rather than failing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from laplace.manuscript import projection_viewer as pv

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1. THE LOCAL-TEX-PATH LAW — env → which → honest None
# ---------------------------------------------------------------------------

def test_tex_bin_precedence_env_then_which_then_none(monkeypatch, tmp_path):
    # a fake binary the env override points at
    fake = tmp_path / "synctex-mine"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)

    # (a) env override wins even when `which` would resolve something else
    monkeypatch.setenv("LAPLACE_SYNCTEX_BIN", str(fake))
    monkeypatch.setattr(pv.shutil, "which",
                        lambda name: "/usr/bin/synctex" if name == "synctex" else None)
    assert pv._synctex_bin() == str(fake)

    # (b) no env → which fallback
    monkeypatch.delenv("LAPLACE_SYNCTEX_BIN", raising=False)
    assert pv._synctex_bin() == "/usr/bin/synctex"

    # (c) no env, which→None → honest None (NEVER a hardcoded literal)
    monkeypatch.setattr(pv.shutil, "which", lambda name: None)
    assert pv._synctex_bin() is None
    assert pv._tex_bin("latexmk", "LAPLACE_LATEXMK_BIN") is None


def test_binary_absent_degrades_honestly_never_500(monkeypatch):
    """FAIL-CLOSED: with the synctex binary unresolvable (which→None, env unset),
    the resolve endpoints REFUSE with an honest ``absent`` verdict — the follow
    read is a 200 pure-read row (present:false), and anchor/locate are structured
    422s naming the fix. Nothing raises; nothing 500s."""
    monkeypatch.delenv("LAPLACE_SYNCTEX_BIN", raising=False)
    monkeypatch.setattr(pv.shutil, "which", lambda name: None)
    root = "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"

    # follow read: a pure read → 200, but honestly degraded + absent-binary flagged
    st, ctype, body = pv.handle("/projection/follow", {"file": [root]}, "GET", b"")
    assert st == 200 and "json" in ctype
    import json
    d = json.loads(body)
    assert d["present"] is False and d["fresh"] is False and d["degraded"] is True
    assert d.get("absent_binary") is True
    assert "LAPLACE_SYNCTEX_BIN" in d["fix"]

    # pdf→source: honest absent, structured refusal (422), not a crash
    st, _, body = pv.handle("/projection/synctex",
                            {"file": [root], "page": ["3"], "x": ["300"], "y": ["400"]},
                            "GET", b"")
    assert st == 422
    a = json.loads(body)
    assert a.get("absent") is True and "LAPLACE_SYNCTEX_BIN" in a["fix"]

    # source→pdf: same honesty
    st, _, body = pv.handle("/projection/locate",
                            {"file": [root], "section": ["S3"]}, "GET", b"")
    assert st == 422
    lo = json.loads(body)
    assert lo.get("absent") is True and "LAPLACE_SYNCTEX_BIN" in lo["fix"]


# ---------------------------------------------------------------------------
# 2. STALENESS HONESTY — _follow_fresh + follow_status
# ---------------------------------------------------------------------------

def _touch(p: Path, mtime: float) -> None:
    p.write_bytes(b"\\documentclass{article}\n\\begin{document}Source words.\\end{document}\n" if p.suffix=='.tex' else b"x")
    os.utime(p, (mtime, mtime))


def test_follow_fresh_staleness(tmp_path,monkeypatch):
    from laplace.manuscript import tex_dependencies
    monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(pv,'_recompile_status_path',lambda path:tmp_path/'build.status.json')
    monkeypatch.setattr(pv,'_recompile_lock_path',lambda path:tmp_path/'build.lock')
    pdf = tmp_path / "main.pdf"
    syn = tmp_path / "main.synctex.gz"
    tex = tmp_path / "main.tex"
    now = time.time()
    def record():
        pv._write_recompile_status(tex,{'state':'done','ok':True,
            'dependencies':tex_dependencies.snapshot(tex,tmp_path),'outputs':pv._build_output_snapshot(tex,tmp_path,producer=False)})

    # (a) no synctex at all → stale (follow disabled)
    _touch(pdf, now)
    _touch(tex, now - 100)
    record()
    fresh, reason = pv._follow_fresh(pdf, tex)
    assert fresh is False and "synctex" in reason

    # (b) synctex OLDER than its pdf → stale (a partial/hand-copied compile)
    _touch(syn, now - 50)
    _touch(pdf, now)
    _touch(tex, now - 100)
    fresh, reason = pv._follow_fresh(pdf, tex)
    assert fresh is False and "lockstep" in reason

    # (c) synctex in lockstep with pdf but the SOURCE was edited after → stale
    _touch(pdf, now - 10)
    _touch(syn, now - 10)
    _touch(tex, now - 100)
    record()
    tex.write_text(tex.read_text().replace('Source words.','Actually changed source.'))
    fresh, reason = pv._follow_fresh(pdf, tex)
    assert fresh is False and "inputs changed" in reason

    # (d) synctex ≥ pdf and ≥ tex → FRESH (follow enabled)
    _touch(tex, now - 100)
    _touch(pdf, now - 10)
    _touch(syn, now)
    record()
    fresh, reason = pv._follow_fresh(pdf, tex)
    assert fresh is True and reason == ""


def test_follow_status_shape_is_the_hy_stale_row(monkeypatch, tmp_path):
    """follow_status returns the uniform ``.hy-stale`` shape the shared atom renders,
    and the no-pdf branch degrades honestly (present:false, a compile fix)."""
    monkeypatch.setattr("laplace.web.scanner._repo_root", lambda: tmp_path)
    # a real synctex binary must resolve so we exercise the pdf branch, not absent
    monkeypatch.setattr(pv, "_synctex_bin", lambda: "/usr/bin/synctex")
    tex = tmp_path / "main.tex"
    tex.write_text("\\documentclass{article}\\begin{document}hi\\end{document}\n",
                   encoding="utf-8")
    row = pv.follow_status("main.tex")
    for k in ("id", "label", "present", "fresh", "reason", "producer", "fix", "degraded"):
        assert k in row, k
    assert row["present"] is False and row["degraded"] is True
    assert "compile" in row["fix"] and "pdf" in row["reason"]


# ---------------------------------------------------------------------------
# 3. HAPPY PATH — a real compiled fixture resolves a known line↔page pair
# ---------------------------------------------------------------------------

_LATEXMK = shutil.which("latexmk")
_SYNCTEX = shutil.which("synctex")

_FIXTURE_TEX = r"""\documentclass{article}
\begin{document}
% PLAN:sec-alpha
% NODES:
% def:alpha-node
\section{Alpha}
First paragraph on a known early line of the document.

\section{Beta target}
This paragraph sits on a deliberately distinctive line so synctex can
round-trip it: the line-to-page map must place it, and the page-click
must resolve back into this same neighbourhood.

\section{Gamma}
A closing paragraph, further down the single page.
\end{document}
"""


@pytest.mark.skipif(_LATEXMK is None or _SYNCTEX is None,
                    reason="no latexmk/synctex toolchain on this box")
def test_follow_happy_path_line_page_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("laplace.web.scanner._repo_root", lambda: tmp_path)
    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(pv, "_recompile_status_path", lambda path: tmp_path / "build.status.json")
    monkeypatch.setattr(pv, "_recompile_lock_path", lambda path: tmp_path / "build.lock")
    main = tmp_path / "main.tex"
    main.write_text(_FIXTURE_TEX, encoding="utf-8")

    # before any compile: follow honestly reports "no pdf yet"
    pre = pv.follow_status("main.tex")
    assert pre["present"] is False and "compile" in pre["fix"]

    code, queued = pv.recompile("main.tex", "", "test", repo_root=tmp_path)
    assert code == 200 and queued["status"] == "started"
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        built = pv.recompile_status("main.tex", repo_root=tmp_path)
        if not built.get("running"):
            break
        time.sleep(.02)
    assert built.get("ok") is True, built
    assert built["outputs"]["files"]["main.synctex.gz"]

    # The real producer bound the source, PDF and map; no fabricated receipt.
    post = pv.follow_status("main.tex")
    assert post["present"] is True and post["fresh"] is True and post["degraded"] is False

    # SOURCE → PDF: the "Beta target" paragraph line locates onto the page
    beta_line = _FIXTURE_TEX.splitlines().index(
        r"\section{Beta target}") + 1               # 1-indexed tex line
    loc = pv.synctex_locate("main.tex", "", beta_line)
    assert "error" not in loc, loc
    assert loc["page"] >= 1 and loc["y"] > 0

    # PDF → SOURCE: clicking near that resolved point comes back to a line in the
    # same neighbourhood (synctex granularity is a box, not an exact line).
    anc = pv.synctex_anchor("main.tex", loc["page"], loc["x"], loc["y"])
    assert "error" not in anc, anc
    assert anc["file"].endswith("main.tex")
    assert abs(anc["line"] - beta_line) <= 3, (anc["line"], beta_line)


# ---------------------------------------------------------------------------
# 4 + 5.  Headless: the echo guard, and the CM pane actually paints
# ---------------------------------------------------------------------------

from browser_fence import CHROME as _CHROME, NO_CHROME_REASON as _NO_CHROME  # noqa: E402

_WHITEPAPER = "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"


def _serve():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


# The echo guard, exercised purely: build a tiny-window guard from the page's own
# factory, then simulate the bidirectional loop. A reverse-follow that suppress()es
# before moving the cursor must make the FORWARD resolver a no-op while the window
# is open (no reverse resolve is minted), then resolve once it elapses.
_ECHO_JS = r"""
async () => {
  const make = window.__pvFollowGuardFactory;
  if (!make) return {err: "no guard factory exposed"};
  const g = make(80);                       // an 80ms suppression window
  let forwardResolves = 0;
  // the forward resolver, exactly as the page gates it: skip while suppressed
  const forward = () => { if (g.isSuppressed()) return; forwardResolves++; };

  const before = g.isSuppressed();          // a fresh guard suppresses nothing
  g.suppress();                             // reverse-follow opens the window...
  const during = g.isSuppressed();
  forward();                                // ...the echoed forward call is swallowed
  const resolvesWhileSuppressed = forwardResolves;

  await new Promise(r => setTimeout(r, 130));  // let the window elapse
  const after = g.isSuppressed();
  forward();                                // a genuine later move DOES resolve
  const resolvesAfter = forwardResolves;

  return {before, during, after, resolvesWhileSuppressed, resolvesAfter};
}
"""


@pytest.mark.skipif(_CHROME is None, reason=_NO_CHROME)
def test_echo_guard_suppresses_the_reverse_resolve():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    httpd, port = _serve()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1100, "height": 800})
            import urllib.parse
            q = urllib.parse.urlencode({"file": _WHITEPAPER, "corpus": "subset-sum-itqde"})
            pg.goto(f"http://127.0.0.1:{port}/projection?{q}",
                    wait_until="domcontentloaded")
            pg.wait_for_function("() => !!window.__pvFollowGuardFactory", timeout=10000)
            r = pg.evaluate(_ECHO_JS)
            b.close()
    finally:
        httpd.shutdown()

    assert "err" not in r, r
    assert r["before"] is False, "a fresh guard must suppress nothing"
    assert r["during"] is True, "suppress() must open the window"
    assert r["resolvesWhileSuppressed"] == 0, "a follow move minted a reverse resolve (echo!)"
    assert r["after"] is False, "the window must be time-bounded, not a latch"
    assert r["resolvesAfter"] == 1, "a genuine move after the window must resolve"


_CM_JS = r"""
() => {
  const host = document.querySelector("#art-cm .cm-editor");
  if (!host) return {mounted: false};
  const box = host.getBoundingClientRect();
  const view = window;  // the façade is closured; read the painted DOM instead
  return {
    mounted: true,
    area: box.width * box.height,
    lines: document.querySelectorAll("#art-cm .cm-line").length,
    hasTextarea: !!document.getElementById("tex"),   // the retired surface must be gone
  };
}
"""


@pytest.mark.skipif(_CHROME is None, reason=_NO_CHROME)
def test_cm_pane_mounts_and_loads_source_no_errors():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    httpd, port = _serve()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1100, "height": 800})
            errors: list[str] = []
            # playwright ConsoleMessage.text / .type are PROPERTIES in this build
            # (not methods); calling m.text() raises inside the listener and the
            # failure only surfaces at the next await. Read them as attributes.
            # Exclude the browser's automatic /favicon.ico 404 (the scanner serves
            # no favicon) — the same environmental noise the response channel below
            # already filters; it is not a defect of the CM projection page.
            def _oncon(m):
                if m.type != "error":
                    return
                if (m.location or {}).get("url", "").endswith("/favicon.ico"):
                    return
                errors.append("CONSOLE:" + m.text)
            pg.on("console", _oncon)
            pg.on("pageerror", lambda e: errors.append("PAGEERROR:" + str(e)))
            pg.on("response", lambda r: errors.append(f"HTTP{r.status}:{r.url}")
                  if r.status >= 400 and not r.url.endswith("/favicon.ico") else None)
            import urllib.parse
            q = urllib.parse.urlencode({"file": _WHITEPAPER, "corpus": "subset-sum-itqde"})
            pg.goto(f"http://127.0.0.1:{port}/projection?{q}",
                    wait_until="domcontentloaded")
            pg.wait_for_selector("#art-cm .cm-editor", timeout=10000)
            pg.wait_for_function(
                "() => document.querySelectorAll('#art-cm .cm-line').length > 3",
                timeout=10000)
            info = pg.evaluate(_CM_JS)
            b.close()
    finally:
        httpd.shutdown()

    assert not errors, f"console/http errors on the CM projection page: {errors}"
    assert info["mounted"] is True, "the CM6 editor did not mount"
    assert info["area"] > 0, "the CM editor painted zero area (blank pane)"
    assert info["lines"] > 3, f"the source did not load into CM (lines={info['lines']})"
    assert info["hasTextarea"] is False, "the retired #tex textarea is still in the DOM"


_WIRED_ECHO_JS = r"""
async () => {
  // THE WIRED PATH, not the factory in isolation (the judge's coverage gap,
  // 2026-07-14): a real pdf-click reverse-follow must not mint a forward
  // /projection/locate resolve as its echo. We count actual network requests.
  const counts = {locate: 0, synctex: 0};
  const orig = window.fetch;
  window.fetch = (...a) => {
    const u = String(a[0]);
    if (u.includes("/projection/locate")) counts.locate++;
    if (u.includes("/projection/synctex")) counts.synctex++;
    return orig(...a);
  };
  const line = () => {
    const el = document.querySelector("#art-cm .cm-line.cm-activeLine");
    return el ? el.textContent : null;
  };
  const canvas = document.querySelector("canvas.pgcv.loaded") || document.querySelector("canvas.pgcv");
  if (!canvas) { window.fetch = orig; return {err: "no rendered pdf canvas"}; }
  const box = canvas.getBoundingClientRect();
  const cursorBefore = line();
  // a genuine reverse gesture: click the middle of the rendered page.
  canvas.dispatchEvent(new MouseEvent("click", {
    bubbles: true, clientX: box.x + box.width / 2, clientY: box.y + box.height / 2,
  }));
  // let the reverse resolve land AND any echoed forward fire if the guard leaks
  // (the forward leg debounces 380ms, so this window is comfortably past it).
  await new Promise(r => setTimeout(r, 1500));
  const cursorAfter = line();
  const echoed = counts.locate;
  // THE ANTI-VACUITY CONTROL. `locate === 0` is only evidence of the guard if the
  // forward leg is LIVE on this page — a broken forward resolver would also read
  // zero. So make a genuine (unguarded) selection move afterwards and require that
  // it DOES mint a locate: the same code path the echo would have taken.
  const cm = document.querySelector("#art-cm .cm-content");
  if (cm) {
    const ln = document.querySelectorAll("#art-cm .cm-line");
    const target = ln[Math.min(4, ln.length - 1)];
    if (target) {
      const r = document.createRange();
      r.selectNodeContents(target);
      const sel = window.getSelection();
      sel.removeAllRanges(); sel.addRange(r);
      cm.dispatchEvent(new Event("focus"));
      document.dispatchEvent(new Event("selectionchange"));
    }
  }
  await new Promise(r => setTimeout(r, 900));
  window.fetch = orig;
  return {locate: echoed, synctex: counts.synctex, cursorBefore, cursorAfter,
          forwardLegAlive: counts.locate > echoed};
}
"""


@pytest.mark.skipif(_CHROME is None, reason=_NO_CHROME)
@pytest.mark.skipif(_LATEXMK is None or _SYNCTEX is None,
                    reason="no latexmk/synctex toolchain on this box")
def test_echo_guard_holds_on_the_wired_gesture_path(monkeypatch, tmp_path):
    """A real pdf click fires the reverse resolve and the echo guard swallows the
    forward echo: >=1 /projection/synctex request, exactly 0 /projection/locate.
    (The factory-in-isolation test above proves the guard mechanism; THIS proves
    suppress()/isSuppressed() are actually wired into the resolvers — the
    regression the judge named that the isolated test cannot catch.)

    Runs on a tiny compiled fixture, not the 37-page whitepaper: the live paper's
    self-heal (stale synctex -> full recompile) would stall any bounded wait, and
    the guard's wiring is identical on one page.

    THE FIXTURE IS NOW A REGISTERED PROJECT, not a loose main.tex at the root. The
    W2 consolidation moved this surface behind ``registry.project_context``: the
    bare /projection route 301s to /artefact, which resolves its pdf/tex through the
    registry rather than from the query alone. A bare ``file=main.tex`` under a
    monkeypatched scanner root therefore resolves the AMBIENT active corpus (whose
    dirs do not exist under tmp_path), the reader paints "not compiled yet", and no
    canvas ever appears. So plant the fixture in the ``synthetics papers/<name>/
    manuscript/whitepaper`` layout `_conceptric` declares, declare it in the
    ``registry_projects.json`` data door, and point BOTH roots (scanner's, for the
    file reads; the registry's, for the project lookup) at tmp_path."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    name = "echoguard-fixture"
    ms = tmp_path / "synthetics papers" / name / "manuscript" / "whitepaper"
    ms.mkdir(parents=True)
    (ms / "main.tex").write_text(_FIXTURE_TEX, encoding="utf-8")
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [
        {"name": name, "tex_root": f"synthetics papers/{name}/manuscript"}]}),
        encoding="utf-8")
    monkeypatch.setattr("laplace.web.scanner._repo_root", lambda: tmp_path)
    monkeypatch.setattr("laplace.pipeline.registry._repo_root", lambda: tmp_path)

    r = subprocess.run(
        [_LATEXMK, "-pdf", "-synctex=1", "-interaction=nonstopmode", "main.tex"],
        cwd=str(ms), capture_output=True, encoding="utf-8",
        errors="replace", timeout=180)
    if not (ms / "main.pdf").is_file():
        pytest.skip(f"fixture failed to compile: {r.stdout[-400:]}")

    rel = f"synthetics papers/{name}/manuscript/whitepaper/main.tex"
    httpd, port = _serve()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1100, "height": 800})
            import urllib.parse
            q = urllib.parse.urlencode({"file": rel, "corpus": name})
            pg.goto(f"http://127.0.0.1:{port}/projection?{q}",
                    wait_until="domcontentloaded")
            pg.wait_for_function("() => !!window.__pvFollowGuardFactory", timeout=10000)
            # THE RENDER GATE. The W2 consolidation retired /projection's own chrome:
            # the artefact surface renders the pdf at first paint (initArtefact →
            # loadReader), so there is no review tab to click — the old
            # `#midbar .mtab[data-m="review"]` gesture named a surface that no longer
            # exists. Wait on the PAINTED canvas instead: `.loaded` lands only after
            # page.render() resolves.
            pg.wait_for_selector("canvas.pgcv.loaded", timeout=30000)
            # the CM pane must be mounted too — the echo the guard swallows is the
            # CM update-listener's, so an unmounted editor would make this vacuous.
            pg.wait_for_selector("#art-cm .cm-editor", timeout=20000)
            res = pg.evaluate(_WIRED_ECHO_JS)
            b.close()
    finally:
        httpd.shutdown()

    assert "err" not in res, res
    assert res["synctex"] >= 1, "the click never fired the reverse resolve — gesture not wired"
    # the reverse resolve LANDED (the cursor really moved to the synctex-named line):
    # without this, locate==0 below would also hold for a resolve that 422'd and never
    # reached gotoSourceLine — a green that proves nothing about the guard.
    assert res["cursorAfter"] and res["cursorAfter"] != res["cursorBefore"], (
        f"the reverse resolve never moved the CM cursor: {res}")
    # and the forward leg is genuinely live on this page (the anti-vacuity control):
    # a later, UNGUARDED selection move does mint a locate through the same path.
    assert res["forwardLegAlive"] is True, (
        f"the forward (CM→pdf) resolver never fired at all — locate==0 proves "
        f"nothing about the guard here: {res}")
    assert res["locate"] == 0, (
        f"the reverse follow echoed {res['locate']} forward resolve(s) — the guard is unwired")
