"""The scroll law, enforced (P10 as amended 2026-07-21; the author's ruling verbatim
in DESIGN_2026-07-21_the-ui-overhaul.md).

Walks every roster surface at 1280x900 and 1536x960 for the named projects and
fails on either breach:
  (a) horizontal overflow -- the document scrolls sideways, or any element's box
      spills past the viewport width;
  (b) unbounded page scroll -- the page-level scroll height exceeds the viewport
      by more than VERTICAL_RATIO; long content must scroll inside its own pane.

The roster it walks is the shell's own ``/shared/views`` PLUS ``/walk`` — the redline
walk carries no shell chrome, so it appears on no shell roster, and a gate that never
loads the page it gates is vacuous (DESIGN_2026-08-10 Acceptance 1 names this script).

Usage:  python3 scripts/chair_walk_scroll_law.py --port 8770 [--projects a,b]
        [--routes /walk] [--shots DIR]  (screenshots of every breach, plus a JSON verdict)
Exit 0 = every page obeys the law; exit 1 = breaches, each named; exit 2 = a vacuous walk
(zero pages loaded); exit 3 = REFUSED TO GRADE — no browser resolved, no server on the
port, or the walk was INCOMPLETE (some page was unreachable). Stated, and never reported
as a pass.

THE PARTIAL-WALK HOLE, measured live 2026-08-15. The vacuous guard below only fires at
``walked == 0``. A server that dies PART WAY through a walk gives ``walked > 0`` plus a
pile of ``law: "unreachable"`` rows — which then rode the normal path and OVERWROTE the
banked verdict.json. Observed on this box: evidence/holdout_full_walk/verdict.json went
from a banked ``{"walked": 24, "breaches": []}`` to ``{"walked": 9, breaches: [15 ×
ERR_CONNECTION_REFUSED]}``. That is worse than a vacuous run, because it LOOKS graded.
An unreachable page is an ABSENCE, not a scroll-law breach; a walk carrying any of them
did not walk the roster, so it grades nothing and writes nothing over what is banked.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_probe import (  # noqa: E402
    REFUSAL_EXIT,
    port_open,
    refusal_line,
    resolve_service,
)

#: A HARD-CODED LINUX PATH IS NOT A BROWSER. The executable was pinned to one box's
#: playwright install, so on any other platform the launch raised and the run died with a
#: traceback — or, worse, a caller wrapping it read the non-zero exit as "breaches" and the
#: gate's verdict meant nothing. The path is RESOLVED (the pin first, then the platform's
#: usual installs, then playwright's own bundled chromium), and when nothing resolves the
#: run SKIPS with the reason said and exit 3 — never a false green and never a false red.
CHROME_PIN = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
VIEWPORTS = [(1280, 900), (1536, 960)]
VERTICAL_RATIO = 1.75

#: THE WALK IS ON THE ROSTER BY NAME. Acceptance 1 of DESIGN_2026-08-10 names this script
#: as the gate the walk passes before he opens it, and `/walk` is in neither the served
#: `/shared/views` roster (the walk inherits no shell chrome, so it is not a shell view)
#: nor the fallback list — so a green run proved nothing about the surface it was gating.
#: It is added to whatever roster is discovered, always, and the roster is never empty of it.
ALWAYS_WALK = ["/walk"]

# Every element wider than the viewport (excluding html/body themselves) is a
# named offender; the page-level facts ride alongside.
_PROBE_JS = """
() => {
  const doc = document.documentElement;
  const vw = window.innerWidth, vh = window.innerHeight;
  const offenders = [];
  for (const el of document.querySelectorAll('*')) {
    // svg INTERNALS report coordinate-space rects (KaTeX stretchy paths span thousands
    // of px), but an svg root clips its descendants (UA default overflow: hidden) — a
    // descendant can never paint outside it. The svg ROOT's own box is still graded.
    if (el.ownerSVGElement) continue;
    // an element painted-CLIPPED into bounds is not overflow: if the nearest
    // overflow-hidden/clip ancestor sits inside the viewport, nothing escapes (an
    // ellipsised badge's children). auto/scroll ancestors do NOT contain — a pane that
    // scrolls sideways is exactly what the law hunts, so their children stay graded;
    // and a clipping ancestor that itself escapes is flagged on its own iteration.
    let contained = false;
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const ov = getComputedStyle(a);
      if (/(hidden|clip)/.test(ov.overflowX + ' ' + ov.overflow)) {
        const ar = a.getBoundingClientRect();
        contained = ar.right <= vw + 1 && ar.left >= -1;
        break;
      }
    }
    if (contained) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && (r.right > vw + 1 || r.left < -1) &&
        el !== doc && el !== document.body) {
      const cs = getComputedStyle(el);
      if (cs.position === 'fixed' && r.width <= vw) continue;
      offenders.push({
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
        cls: (el.className && el.className.baseVal !== undefined
              ? el.className.baseVal : el.className || '').toString().slice(0, 80),
        left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width),
      });
      if (offenders.length >= 12) break;
    }
  }
  return {
    scroll_w: doc.scrollWidth, client_w: doc.clientWidth,
    scroll_h: doc.scrollHeight, viewport_h: vh,
    offenders,
  };
}
"""


def _roster(port: int) -> list[str]:
    """The served surfaces, from the shell's own roster route (one truth), PLUS the
    surfaces that carry no shell chrome and so appear on no shell roster — the redline
    walk. A gate that never loads the page it gates is vacuous."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/shared/views", timeout=10) as r:
            data = json.load(r)
        views = data.get("views", data if isinstance(data, list) else [])
        routes = [v.get("path") or v.get("route") or v.get("href")
                  for v in views if isinstance(v, dict)]
        routes = [r.split("?")[0] for r in routes if r]
    except Exception:
        routes = ["/", "/desk", "/artefact", "/storyboard", "/pipeline",
                  "/conceptric", "/altitude", "/analytics", "/assets", "/map"]
    return sorted(set(routes) | set(ALWAYS_WALK))


def _chrome_path() -> tuple[str | None, str]:
    """The browser binary to drive, resolved PER PLATFORM. Returns ``(path, reason)``:
    ``path`` is the executable to launch, or ``None`` with ``reason`` saying which
    candidates were tried and found absent. ``None`` for the path means playwright's own
    bundled chromium is used (``executable_path=None`` is its default resolution) — and
    only when playwright reports it installed, so a missing browser SKIPS with the reason
    rather than passing or failing on nothing."""
    import shutil

    tried: list[str] = []
    if Path(CHROME_PIN).is_file():
        return CHROME_PIN, ""
    tried.append(CHROME_PIN)
    if sys.platform.startswith("win"):
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        names = ["chrome", "msedge"]
    elif sys.platform == "darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      "/Applications/Chromium.app/Contents/MacOS/Chromium"]
        names = ["google-chrome", "chromium"]
    else:
        candidates = ["/usr/bin/google-chrome", "/usr/bin/chromium",
                      "/usr/bin/chromium-browser", "/snap/bin/chromium"]
        names = ["google-chrome", "chromium", "chromium-browser"]
    for c in candidates:
        if Path(c).is_file():
            return c, ""
        tried.append(c)
    for n in names:
        found = shutil.which(n)
        if found:
            return found, ""
        tried.append(n + " (on PATH)")
    # playwright's own bundled chromium, if it is installed
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            bundled = pw.chromium.executable_path
        if bundled and Path(bundled).is_file():
            return bundled, ""
        tried.append(str(bundled or "playwright's bundled chromium"))
    except Exception as exc:                                  # noqa: BLE001
        tried.append(f"playwright's bundled chromium ({str(exc)[:80]})")
    return None, ("no chromium-family browser resolved on this platform "
                  f"({sys.platform}); tried: " + ", ".join(tried))


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk every surface; fail on any scroll-law breach.")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--projects", default="paper_falqon,eigenengine")
    ap.add_argument("--routes", default="",
                    help="comma list to walk only these routes (default: the whole roster)")
    ap.add_argument("--shots", default="evidence/scroll_law_walk")
    ap.add_argument("--vertical-ratio", type=float, default=VERTICAL_RATIO)
    ap.add_argument("--allow-bundled-default", action="store_true",
                    help="launch playwright's default browser even when this script "
                         "could not resolve one (the caller has proved it is installed)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"SCROLL LAW: SKIPPED - playwright is not installed here ({exc}).")
        print("  no page was walked, so this run grades nothing; it is not a pass. "
              "`pip install playwright && playwright install chromium`, then run it again.")
        return 3

    chrome, why = _chrome_path()
    if chrome is None and not args.allow_bundled_default:
        print("SCROLL LAW: SKIPPED - " + why)
        print("  no page was walked, so this run grades nothing; it is not a pass. "
              "Install a chromium-family browser (or run `playwright install chromium`) "
              "and run it again.")
        return 3

    # THE SERVICE IS DISCOVERED, NOT ASSUMED. Probing the port first turns "no server"
    # from seventy seconds of driving a browser at nothing (and forty-eight
    # ERR_CONNECTION_REFUSED rows) into a sub-second refusal that says so.
    base = f"http://127.0.0.1:{args.port}"
    if not port_open("127.0.0.1", args.port):
        discovered = resolve_service()
        tried = [f"{base} (--port {args.port}): nothing listening"]
        if discovered:
            tried.append(f"but a service IS up at {discovered} — "
                         "pass --port for it if that is the one to grade")
        print(refusal_line("SCROLL LAW", f"the scanner on 127.0.0.1:{args.port}", tried))
        return REFUSAL_EXIT

    shots = Path(args.shots)
    shots.mkdir(parents=True, exist_ok=True)
    routes = ([r if r.startswith("/") else "/" + r for r in args.routes.split(",") if r]
              if args.routes else _roster(args.port))
    projects = [p for p in args.projects.split(",") if p]
    breaches: list[dict] = []
    walked = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**({"executable_path": chrome} if chrome else {}))
        for w, h in VIEWPORTS:
            page = browser.new_page(viewport={"width": w, "height": h})
            for route in routes:
                for project in projects:
                    url = f"http://127.0.0.1:{args.port}{route}?corpus={project}"
                    try:
                        page.goto(url, wait_until="networkidle", timeout=30000)
                    except Exception as exc:
                        breaches.append({"route": route, "project": project, "width": w,
                                         "law": "unreachable", "detail": str(exc)[:200]})
                        continue
                    walked += 1
                    facts = page.evaluate(_PROBE_JS)
                    name = f"{route.strip('/').replace('/', '_') or 'dashboard'}-{project}-{w}"
                    horizontal = (facts["scroll_w"] > facts["client_w"] + 1) or facts["offenders"]
                    vertical = facts["scroll_h"] > facts["viewport_h"] * args.vertical_ratio
                    if horizontal:
                        page.screenshot(path=str(shots / f"H-{name}.png"), full_page=False)
                        breaches.append({"route": route, "project": project, "width": w,
                                         "law": "horizontal", "scroll_w": facts["scroll_w"],
                                         "client_w": facts["client_w"],
                                         "offenders": facts["offenders"][:6]})
                    if vertical:
                        page.screenshot(path=str(shots / f"V-{name}.png"), full_page=False)
                        breaches.append({"route": route, "project": project, "width": w,
                                         "law": "vertical", "scroll_h": facts["scroll_h"],
                                         "viewport_h": facts["viewport_h"],
                                         "ratio": round(facts["scroll_h"] / facts["viewport_h"], 2)})
            page.close()
        browser.close()

    # Separated so a half-dead server cannot be reported as a pile of law violations.
    unreachable = [b for b in breaches if b.get("law") == "unreachable"]
    graded_breaches = [b for b in breaches if b.get("law") != "unreachable"]
    attempted = len(routes) * len(projects) * len(VIEWPORTS)
    verdict = {"walked": walked, "attempted": attempted, "served_by": base,
               "routes": routes, "projects": projects,
               "browser": chrome or "playwright's bundled chromium",
               "unreachable": unreachable, "breaches": graded_breaches,
               "law": "P10 as amended 2026-07-21"}
    if walked == 0:
        # A vacuous walk grades nothing, so it may not overwrite a banked graded
        # verdict either (measured 2026-08-15: a serverless wake clobbered three
        # banked verdict.json files with unreachable-noise). Write beside, not over.
        (shots / "verdict_vacuous.json").write_text(json.dumps(verdict, indent=2),
                                                    encoding="utf-8")
        print("SCROLL LAW: FAIL - zero pages walked (roster empty or server down); "
              "a vacuous walk never passes. Banked verdict.json left untouched; "
              "this run recorded beside it as verdict_vacuous.json")
        return 2
    if unreachable:
        # THE PARTIAL WALK. Some pages loaded, some did not: the roster was not walked,
        # so this run has no standing to overwrite a verdict produced by a run that DID
        # walk it. Same rule as the vacuous case — record beside, never over.
        (shots / "verdict_incomplete.json").write_text(json.dumps(verdict, indent=2),
                                                       encoding="utf-8")
        print(refusal_line(
            "SCROLL LAW", f"a complete walk of the roster ({len(unreachable)} of "
            f"{attempted} page-walks unreachable)",
            [f"walked {walked}/{attempted}; the server on :{args.port} answered some "
             "pages and not others, so the roster was NOT walked",
             f"first: {unreachable[0].get('route')} [{unreachable[0].get('project')}] "
             f"{str(unreachable[0].get('detail'))[:90]}"]))
        print(f"  banked verdict.json left untouched; this run recorded beside it as "
              f"{shots / 'verdict_incomplete.json'}")
        return REFUSAL_EXIT
    breaches = graded_breaches
    (shots / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    if breaches:
        print(f"SCROLL LAW: FAIL - {len(breaches)} breach(es) across {walked} page-walks")
        for b in breaches:
            print(f"  {b['law']:11} {b['route']} [{b['project']}] @{b['width']}px "
                  + (f"ratio {b.get('ratio')}" if b['law'] == 'vertical'
                     else f"{len(b.get('offenders', []))} offender(s)"
                     if b['law'] == 'horizontal' else b.get('detail', '')))
        print(f"screenshots + verdict.json in {shots}")
        return 1
    print(f"SCROLL LAW: PASS - {walked} page-walks, zero horizontal overflow, "
          f"every page bounded within {args.vertical_ratio}x viewport")
    return 0


if __name__ == "__main__":
    sys.exit(main())
