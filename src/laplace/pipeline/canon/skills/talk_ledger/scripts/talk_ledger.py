"""The deck-aware talk ledger - verify the RENDERED talk, not the source alone.

[`talk_smith`]'s refine stage. A talk is the manuscript voice in a freer medium,
so its checks are deck-aware: the voice must hold in the slide *prose* (not the
JS/CSS/KaTeX around it), and every live applet must actually render. This runs
the three checks a deck needs, all of which were exercised by hand the session
this was forged:

  1. VOICE - run the masking slop detector (lint_voice.py) over the slide source
     (slides.md) and the applets (public/viz/*.html). Deck-tuned: it masks code,
     markup, KaTeX, and Slidev frontmatter, so it only flags prose.
  2. APPLETS - run every tools/verify-*.mjs the deck ships (the per-applet
     headless render harnesses: no console error, canvas paints, no overflow,
     the stepper walks). Each is one node process.
  3. DEPLOY (optional, --deploy) - tools/verify-deploy.mjs: load the built deck
     under its real base and fail on a console error or a broken same-origin
     request. The slow one (it builds + serves + drives a browser).

A leg that could not run is named, never dropped. A deck with no verify-*.mjs
and no applets under public/viz reports the applet leg as SKIP; a deck that
ships applets with no harness for them reports FAIL, so the aggregate can never
narrate a sweep that did not happen. Same for --deploy with no
tools/verify-deploy.mjs: SKIP, printed.

Exit: 2 on a bad target, 1 if any check fails, 0 if all pass. Default skips the
slow deploy check so it fits a bounded runner; pass --deploy for the full sweep.

Usage:
    python talk_ledger.py <deck-dir> [--deploy] [--strict-voice]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# The masking slop detector is a sibling script: skills/talk_ledger/scripts ->
# skills/voice_linter/scripts. The voice_linter SKILL's enforcement mandate was
# retired by the 2026-07-09 rebuild ruling; lint_voice.py survives under this
# owner and blind_reader as a detector, which is what is called here.
_VOICE = os.path.normpath(os.path.join(_HERE, "..", "..", "voice_linter", "scripts", "lint_voice.py"))


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 120) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as e:
        return 127, str(e)


def voice_check(deck: str, strict: bool) -> dict:
    targets = [t for t in (os.path.join(deck, "slides.md"), os.path.join(deck, "public", "viz")) if os.path.exists(t)]
    if not targets:
        targets = [deck]
    flags = 0
    detail = []
    for t in targets:
        code, out = _run([sys.executable, _VOICE, t, "--json"], timeout=60)
        try:
            n = json.loads(out).get("total", 0)
        except json.JSONDecodeError:
            n = -1
        flags += max(n, 0)
        detail.append({"target": os.path.relpath(t, deck), "flags": n})
    ok = (flags == 0) if strict else True
    return {"name": "voice", "pass": ok, "flags": flags, "detail": detail,
            "note": "" if strict else "advisory (pass --strict-voice to gate)"}


def _shipped_applets(deck: str) -> list[str]:
    """The applet sources the deck ships (public/viz/*.html), which are what a
    verify-*.mjs harness exists to render."""
    viz = os.path.join(deck, "public", "viz")
    if not os.path.isdir(viz):
        return []
    return sorted(f for f in os.listdir(viz) if f.endswith((".html", ".htm")))


def applet_checks(deck: str) -> list[dict]:
    """One row per verify-*.mjs harness, or one honest non-PASS row when there are none.

    An empty harness set is never silence: with applets shipped it is a FAIL (the
    leg the ledger promises cannot run), with no applets shipped it is a stated
    SKIP. Either way the aggregate line reports what was actually observed.
    """
    tools = os.path.join(deck, "tools")
    out = []
    harnesses = []
    if os.path.isdir(tools):
        harnesses = [f for f in sorted(os.listdir(tools))
                     if f.startswith("verify-") and f.endswith(".mjs") and f != "verify-deploy.mjs"]
    if not harnesses:
        applets = _shipped_applets(deck)
        if applets:
            return [{"name": "applets", "pass": False, "skipped": False,
                     "problems": [f"deck ships {len(applets)} applet(s) under public/viz "
                                  f"({', '.join(applets[:3])}{'...' if len(applets) > 3 else ''}) "
                                  "and no tools/verify-*.mjs harness renders any of them"]}]
        return [{"name": "applets", "pass": True, "skipped": True,
                 "note": "SKIP - no tools/verify-*.mjs harness and no applets under public/viz"}]
    for f in harnesses:
        code, log = _run(["node", os.path.join("tools", f)], cwd=deck, timeout=120)
        verdict = None
        try:
            verdict = json.loads(log[log.index("{"): log.rindex("}") + 1]).get("pass")
        except (ValueError, json.JSONDecodeError):
            pass
        out.append({"name": f, "pass": code == 0 and verdict is not False,
                    "exit": code, "problems": _grep_problems(log)})
    return out


def _grep_problems(log: str) -> list[str]:
    try:
        d = json.loads(log[log.index("{"): log.rindex("}") + 1])
        return d.get("problems", []) or ([d["fatal"]] if d.get("fatal") else [])
    except (ValueError, json.JSONDecodeError):
        return []


def deploy_check(deck: str) -> dict:
    vd = os.path.join(deck, "tools", "verify-deploy.mjs")
    if not os.path.exists(vd):
        return {"name": "deploy", "pass": True, "skipped": True,
                "note": "SKIP - deck ships no tools/verify-deploy.mjs"}
    code, log = _run(["node", "tools/verify-deploy.mjs"], cwd=deck, timeout=180)
    return {"name": "deploy", "pass": code == 0, "exit": code, "problems": _grep_problems(log)}


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args or not os.path.isdir(args[0]):
        print("Usage: python talk_ledger.py <deck-dir> [--deploy] [--strict-voice]", file=sys.stderr)
        return 2
    deck = args[0]
    checks = [voice_check(deck, "--strict-voice" in argv)]
    checks += applet_checks(deck)
    if "--deploy" in argv:
        checks.append(deploy_check(deck))

    print("# Talk Ledger")
    print("*" * 50)
    for c in checks:
        mark = "SKIP" if c.get("skipped") else ("PASS" if c["pass"] else "FAIL")
        extra = c.get("note") or (f"flags={c['flags']}" if "flags" in c else "")
        print(f"[{mark}] {c['name']}  {extra}".rstrip())
        for p in c.get("problems", [])[:5]:
            print(f"     - {p}")
    failed = [c["name"] for c in checks if not c["pass"]]
    skipped = [c["name"] for c in checks if c.get("skipped")]
    print("*" * 50)
    if failed:
        print(f"LEDGER: FAIL ({', '.join(failed)})")
    elif skipped:
        print(f"LEDGER: PASS with {len(skipped)} leg(s) SKIPPED ({', '.join(skipped)}) - "
              "not a full sweep")
    else:
        print("LEDGER: PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
