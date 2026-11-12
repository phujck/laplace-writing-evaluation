#!/usr/bin/env python3
"""run_playwright_walks.py — batch-run the browser walks, so the intent-level net is one command.

AUDIT_2026-07-15 §C3 (the pipeline-workflow audit) banked the finding: the ONLY intent-level
instrument — real Chromium + real scanner + real DOM/JSON assertions — is never collected by
pytest, has no batch runner, no CI, and runs only when someone remembers the banked pull-back
protocol. This runner is the batch half that finding asked for. It discovers every
`tests/*.playwright.mjs` walk and runs them SERIALLY (each walk spawns its own scanner on a free
port; serial avoids port/artifact collisions), streaming a one-line verdict per walk and a summary
block, exiting nonzero iff any ran walk failed. A hung walk is FAIL(timeout), never a hung runner.

MUTATING WALKS (AUDIT_2026-07-15 §C5). The Wave-1 baseline run proved j9_crank is SIDE-EFFECTING:
it drives the real new-project/run-panel doors and rewrites live ledgers (work_orders.jsonl, the
crank record, the crank friction ledger, registry_projects.json, projection_plan.json,
feedback.jsonl). A regression net must be idempotent — it must not rewrite the tree it guards —
so walks named in :data:`MUTATING_WALKS` are EXCLUDED from default runs and reported as excluded.
Run them deliberately with `--include-mutating` when the write-path proof is what you want, on a
tree you are prepared to restore. `--list` marks them.

  run:   .venv/bin/python scripts/run_playwright_walks.py            # every NON-MUTATING walk
         .venv/bin/python scripts/run_playwright_walks.py --list     # enumerate, don't run
         .venv/bin/python scripts/run_playwright_walks.py --only j5  # scoped re-run (repeatable)
         .venv/bin/python scripts/run_playwright_walks.py --include-mutating   # j9_crank too
         .venv/bin/python scripts/run_playwright_walks.py --json baseline.json # machine record
  deps:  node on PATH, the global `playwright` npm package + Chromium at PLAYWRIGHT_BROWSERS_PATH,
         the repo venv python on PATH as python3 (the walks spawn `python -m laplace.web.scanner`).
         The environment is honored AS-IS — the parent env is passed straight through to every
         `node <walk>` child; this runner sets nothing (PLAYWRIGHT_BROWSERS_PATH included).

Stdlib only — no pytest, no third-party deps: the runner is itself the kind of always-runnable
net the audit wants standing over the walks. Exit 0 iff every ran walk passed, else 1, and 3
when the runner REFUSES TO GRADE — the walks' own preconditions (node, the global playwright,
the vendored chromium, a python3 that can import laplace) are not on this box, so no walk could
have run. Measured 2026-08-15: without that fence every walk returned "FAIL" in 0.5s with
`ModuleNotFoundError: No module named 'laplace'` in its tail, the summary read
"passed 0  failed 39", and --json banked that as a machine record. Zero assertions had run.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_probe import REFUSAL_EXIT, refusal_line  # noqa: E402

WALK_GLOB = "*.playwright.mjs"
TESTS_DIR = "tests"
DEFAULT_TIMEOUT = 300  # seconds per walk — a hung walk is FAIL(timeout), never a hung runner
TAIL_LINES = 40        # last N lines of a failing walk's output, so a FAIL is diagnosable

# §C5: walks that WRITE to the live tree (ledgers, registries, records). Excluded from default
# runs — a standing net must not rewrite what it guards. Run deliberately via --include-mutating.
MUTATING_WALKS = {
    "j9_crank.playwright.mjs",  # drives the real new-project/run-panel doors; rewrites
                                # work_orders.jsonl, CRANK_RECORD, the crank friction ledger,
                                # registry_projects.json, projection_plan.json, feedback.jsonl
    "wave05_ladder_bank.playwright.mjs",  # W-L28 the up-loop: the panel-head ✎ banks a real
                                # fork through POST /corpus/friction into
                                # corpus_friction/subset-sum-itqde.jsonl (the desk then carries it)
    "wave4_storyboard.playwright.mjs",  # W4 click-reorder round-trip: the move-picker slot fires
                                # a real POST /storyboard/plan reorder-sections against the live
                                # projection_plan.json (restored in the walk's finally, but a real write)
    "waveF_desk_landing.playwright.mjs",  # WAVE F: the ✎ rule-in-place round-trip banks a REAL typed
                                # fork through POST /corpus/friction onto a throwaway corpus ledger
                                # (corpus_friction/wavef-seal-probe.jsonl) and proves it LANDS OPEN on
                                # /desk/data; the ledger is removed in the walk's finally, but a real write
    "engine_assets.playwright.mjs",  # W-HANDS: drives POST /assets/assess (a probe finding into
                                # subset-sum's feedback.jsonl) + POST /assets/regen (a probe work-order),
                                # proving the assess echo + the regen desk door; both cleaned in the finally
    "engine_cockpit.playwright.mjs",  # W-HANDS: drives the node-scoped comment composer — a REAL POST
                                # /corpus/feedback into paper_falqon's feedback ledger — proving the echo;
                                # the probe comment is removed in the walk's finally
    "engine_dashboard.playwright.mjs",  # W-HANDS: drives the New Project door (a real scaffold in the
                                # registry) to prove the confirmation survives the re-render; torn down in
                                # the finally exactly as j6_new_project does
}

EXCLUDED_NOTE = "excluded: mutating (write-path proof — run deliberately with --include-mutating)"


#: The interpreter every walk spawns its scanner with, hardcoded inside the .mjs files
#: (``const PY = 'python3'``). The runner probes THAT interpreter, not its own — the walks
#: do not inherit sys.executable, so a green venv here proves nothing about them.
WALK_PYTHON = "python3"


def repo_root() -> Path:
    """The repo root — this script lives in scripts/, the root is its parent."""
    return Path(__file__).resolve().parent.parent


def walk_preconditions(root: Path) -> list[str]:
    """What every walk needs before it can assert anything, probed here rather than
    discovered one traceback at a time. Returns the list of ABSENT preconditions
    (empty list = the box can run walks).

    Each probe is bounded and cheap; the whole fence costs well under a second, which is
    the point — a runner that spends 39 × 0.5s discovering the same missing module and
    calls the result "39 failures" has graded nothing and said the opposite.
    """
    missing: list[str] = []
    node = shutil.which("node")
    if not node:
        missing.append("node on PATH (the walks are .mjs; nothing can run them)")
        return missing              # everything below needs node to be probed at all

    try:
        npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True,
                                  text=True, timeout=20).stdout.strip()
    except Exception as exc:        # noqa: BLE001
        npm_root = ""
        missing.append(f"npm root -g would not answer ({type(exc).__name__})")
    if npm_root and not (Path(npm_root) / "playwright").is_dir():
        missing.append(f"the global playwright package (looked in {npm_root}/playwright; "
                       "every walk does require(<npm root -g>/playwright))")

    if not sorted(Path("/opt").glob("pw-browsers/chromium-*/chrome-linux/chrome")):
        missing.append("the vendored chromium at "
                       "/opt/pw-browsers/chromium-*/chrome-linux/chrome "
                       "(each walk resolves it with `ls`, and dies if it is not there)")

    # The one that bit: the walks spawn `python3 -m laplace.web.scanner`. The ambient python3
    # is NOT necessarily the repo venv, and when it cannot import laplace every walk dies
    # before its first assertion — which the runner used to call a walk failure.
    try:
        p = subprocess.run([WALK_PYTHON, "-c", "import laplace"],
                           cwd=str(root), capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            tail = (p.stderr or "").strip().splitlines()
            missing.append(
                f"a `{WALK_PYTHON}` that can import laplace — every walk spawns "
                f"`{WALK_PYTHON} -m laplace.web.scanner`, so its scanner never starts "
                f"({tail[-1] if tail else 'import failed'}). Run this runner under, or put "
                "on PATH as python3, the interpreter that carries laplace (the repo venv).")
    except FileNotFoundError:
        missing.append(f"`{WALK_PYTHON}` on PATH (the walks spawn their scanner with it)")
    except Exception as exc:        # noqa: BLE001
        missing.append(f"a probe-able `{WALK_PYTHON}` ({type(exc).__name__}: {exc})")
    return missing


def discover_walks(root: Path, include_mutating: bool = False) -> list[Path]:
    """Every browser walk under tests/, sorted. A walk is a `*.playwright.mjs` file and nothing
    else — a bare `*.mjs` (store.mjs, a pane module) is NOT a walk and is excluded by the glob.
    Default discovery EXCLUDES the :data:`MUTATING_WALKS` (§C5 — the net must not rewrite what
    it guards); pass include_mutating=True for the full set (the deliberate write-path run, and
    `--list`'s marked enumeration)."""
    tests = root / TESTS_DIR
    if not tests.is_dir():
        return []
    walks = sorted(tests.glob(WALK_GLOB))
    if not include_mutating:
        walks = [w for w in walks if w.name not in MUTATING_WALKS]
    return walks


def is_mutating(walk: Path) -> bool:
    return walk.name in MUTATING_WALKS


def filter_walks(walks: list[Path], only: list[str] | None) -> list[Path]:
    """Keep walks whose repo-relative path contains ANY of the `--only` substrings (OR: `--only j1
    --only j5` runs both). No `--only` → the full set unfiltered."""
    if not only:
        return walks
    return [w for w in walks if any(sub in str(w) for sub in only)]


def _rel(root: Path, walk: Path) -> str:
    return str(walk.relative_to(root))


def run_walk(root: Path, walk: Path, timeout: int) -> tuple[str, float, str]:
    """Run one walk with `node <file>`, parent env passed straight through, cwd at the repo root
    (matching the by-hand `node tests/jX....playwright.mjs` invocation). Returns
    (status, seconds, output) where status is 'pass' | 'fail' | 'timeout'."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            ["node", str(walk)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.monotonic() - start
        output = (proc.stdout or "") + (proc.stderr or "")
        status = "pass" if proc.returncode == 0 else "fail"
        return status, elapsed, output
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        out = ""
        if exc.stdout:
            out += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", "replace")
        if exc.stderr:
            out += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", "replace")
        out += f"\n<runner: walk exceeded {timeout}s timeout — killed>"
        return "timeout", elapsed, out
    except OSError as exc:
        elapsed = time.monotonic() - start
        return "fail", elapsed, f"<runner: could not launch node: {exc}>"


def _tail(output: str, n: int = TAIL_LINES) -> str:
    lines = output.splitlines()
    return "\n".join(lines[-n:])


def run_weld_python(root: Path, timeout: int) -> int:
    """``--weld-python`` — a faithful Python port of tests/engine_weld.playwright.mjs,
    run through the venv's own sync_playwright instead of node-playwright. This is the
    box-general fallback: the Windows dev box has no node-side Playwright install (no
    node_modules/playwright, no global npm playwright) so the .mjs cannot resolve a
    `chromium` there at all, but the repo venv already carries playwright + a managed
    Chromium — so THIS is the path that must run green on that box.

    Same four legs, same assertion messages, same exit semantics (0 = every assertion
    passed, 1 = an assertion failed or setup errored — printed to stderr, matching the
    .mjs's top-level `.catch`). Kept in lockstep with the .mjs BY HAND — there is no
    single source both run from, so a change to the walk's grammar or leg content must
    be mirrored here too.

    The spawned scanner gets LAPLACE_EMBED_BUDGET=0 explicitly in its own env (never
    assumed inherited) — 0 is the documented OFF posture (embed_router._env_budget /
    the local launcher default); this walk must never trip an embedding run.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        # An absent library is not a failed assertion. This used to return 1 — the same
        # code a real weld breach returns — so a box without playwright reported the
        # weld BROKEN when the weld had never been looked at.
        print(refusal_line("ENGINE WELD (python)",
                           f"playwright under {sys.executable}", [str(exc)]),
              file=sys.stderr)
        print("  install it in the interpreter actually running this script "
              "(pip install playwright && playwright install chromium) and retry.",
              file=sys.stderr)
        return REFUSAL_EXIT

    import socket
    import urllib.error
    import urllib.request

    CORPUS = "paper_falqon"
    PY = sys.executable  # the interpreter running THIS script — same contract as the
                          # .mjs's resolvePython(): the venv on Windows, python3 on Linux
                          # when this script itself is invoked under that interpreter.

    def free_port() -> int:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    class ScannerAbsent(RuntimeError):
        """The spawned scanner never answered. An absent instrument, not a breach."""

    def wait_for(url: str, proc: "subprocess.Popen | None" = None,
                 budget: float = 20.0) -> None:
        """A SHORT BOUNDED WAIT THAT WATCHES THE CHILD. The old loop was 80 tries of
        (2s connect + 0.25s sleep) — up to three minutes of waiting on a scanner that
        had usually already exited — and it ended in a RuntimeError swallowed by the
        broad `except Exception` below, which returned 1: an absence graded as a
        failed weld. Now the child's death ends the wait at once, and the refusal is
        typed so it cannot be mistaken for an assertion failure."""
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            if proc is not None and proc.poll() is not None:
                raise ScannerAbsent(
                    f"the scanner exited immediately (rc={proc.returncode}) — "
                    f"`{PY} -m laplace.web.scanner` will not run here")
            try:
                urllib.request.urlopen(url, timeout=2).close()
                return
            except Exception:
                time.sleep(0.25)
        raise ScannerAbsent(f"the scanner never answered {url} inside {budget:g}s")

    state = {"passed": 0}

    def ok(cond: bool, msg: str) -> None:
        if not cond:
            raise AssertionError("ASSERT FAILED: " + msg)
        state["passed"] += 1
        print("  ok -", msg)

    scanner: subprocess.Popen | None = None
    try:
        port = free_port()
        env = os.environ.copy()
        env["LAPLACE_EMBED_BUDGET"] = "0"
        scanner = subprocess.Popen(
            [PY, "-m", "laplace.web.scanner", "--port", str(port)],
            cwd=str(root), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            wait_for(base + "/", scanner)
        except ScannerAbsent as exc:
            print(refusal_line("ENGINE WELD (python)", "the weld's own scanner",
                               [str(exc)]), file=sys.stderr)
            return REFUSAL_EXIT

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:                              # noqa: BLE001
                print(refusal_line("ENGINE WELD (python)", "a launchable chromium",
                                   [f"p.chromium.launch(): {str(exc)[:200]}"]),
                      file=sys.stderr)
                return REFUSAL_EXIT
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errs: list[str] = []
                page.on("pageerror", lambda exc: errs.append(str(exc)))

                # the grammar every stop must wear — ported 1:1 from the .mjs `grammar()`
                def grammar(name: str, lit_stage: str | None = None, need_context: bool = True):
                    page.wait_for_selector("#hy-shell", timeout=15000)
                    page.wait_for_timeout(600)
                    g = page.evaluate("""() => {
                        const lit = [...document.querySelectorAll('.hy-stage.on, .hy-stage.on-door')]
                            .map((a) => (a.querySelector('.st-t') || a).textContent.trim());
                        const ctx = document.querySelector('#hy-context');
                        const from = document.querySelector('.hy-from');
                        return {
                            lit,
                            hasContext: !!ctx,
                            fromText: from ? from.textContent.trim() : null,
                            hymn: !!document.querySelector('link[href*="hymn.css"]'),
                            hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
                        };
                    }""")
                    ok(g["hymn"], f"{name}: rides the one hymn sheet")
                    ok(not g["hscroll"], f"{name}: no horizontal scroll at 1440")
                    if need_context:
                        ok(g["hasContext"], f"{name}: the context header is present")
                    if lit_stage:
                        joined = "|".join(g["lit"]) or "none"
                        ok(any(lit_stage in t for t in g["lit"]),
                           f"{name}: the {lit_stage} stage is lit (lit: {joined})")
                    if g["fromText"]:
                        ok("/" not in g["fromText"].replace("← from", ""),
                           f'{name}: the return door speaks journey vocabulary ("{g["fromText"]}")')
                    return g

                # ═══ LEG A — the process spine, crossed in paper order ═══
                print("\n=== leg A: the spine, Home through Desk ===")
                page.goto(f"{base}/?corpus={CORPUS}", wait_until="domcontentloaded")
                grammar("Home", lit_stage="Home", need_context=False)
                spine_words = page.evaluate("""() =>
                    [...document.querySelectorAll('.hy-stage')].map((a) => ({
                        t: (a.querySelector('.st-t') || a).textContent.trim(),
                        w: (a.querySelector('.st-w') || {}).textContent || '',
                    }))""")
                worded = [s for s in spine_words if s["w"].strip()]
                ok(len(worded) >= 4,
                   f"Home: live state words ride the spine ({len(worded)} stages worded)")
                # MECHANISM, not data: the Desk word depends on live corpus state
                # (owed_to_author) — asserting it non-empty was coupled to whatever
                # paper_falqon happens to owe right now (rots green-to-red or red-to-green
                # as the desk empties/fills). Instead fetch the SAME /shared/journey feed
                # the page itself renders from and assert the rendered DOM word agrees
                # with the served word — true whether the desk is empty or full today.
                journey_feed = json.loads(
                    urllib.request.urlopen(f"{base}/shared/journey?corpus={CORPUS}", timeout=5).read())
                desk_stage_feed = next(
                    (s for s in journey_feed.get("stages", []) if s.get("id") == "desk"), None)
                desk_feed_word = (desk_stage_feed or {}).get("word")
                desk_feed_text = str(desk_feed_word).strip() if desk_feed_word else ""
                desk_dom_text = next(
                    (s["w"] for s in spine_words if "desk" in s["t"].lower()), "").strip()
                ok(desk_dom_text == desk_feed_text,
                   f"Home: the Desk stage word agrees with the served journey feed "
                   f"('{desk_dom_text}' == '{desk_feed_text}')")

                spine = [("Grow", "Grow"), ("Shape", "Shape"), ("Read", "Read"),
                         ("Machine", "Machine"), ("Desk", "Desk")]
                for label, lit in spine:
                    page.evaluate("""(l) => {
                        const a = [...document.querySelectorAll('.hy-stage')].find((x) => x.textContent.includes(l));
                        if (a) a.click();
                    }""", label)
                    page.wait_for_load_state("domcontentloaded")
                    grammar(label, lit_stage=lit)
                    corpus_held = page.evaluate(
                        "() => location.search.includes('corpus=') || !!sessionStorage.length")
                    ok(corpus_held, f"{label}: the paper rides the crossing")

                # ═══ LEG B — the door crossings: Grow's card → Lineage → the editor ═══
                print("\n=== leg B: door crossings, Lineage into the editor ===")
                page.goto(f"{base}/lineage?corpus={CORPUS}&object=eq:coh-total",
                          wait_until="domcontentloaded")
                grammar("Lineage (cold object arrival)")
                lin = page.evaluate("""() => ({
                    focused: !!document.querySelector('[class*="lin-"]'),
                    editorDoor: [...document.querySelectorAll('a,button')].some((a) => /open in the editor/i.test(a.textContent)),
                })""")
                ok(lin["focused"], "Lineage: the cold ?object= arrival lands in the surface body")
                ok(lin["editorDoor"], "Lineage: the editor crossing is offered at the object")
                page.evaluate("""() => {
                    const a = [...document.querySelectorAll('a,button')].find((x) => /open in the editor/i.test(x.textContent));
                    if (a) a.click();
                }""")
                page.wait_for_load_state("domcontentloaded")
                grammar("Read·Judge (arrived from Lineage)", lit_stage="Read")

                # ═══ LEG C — the walk back: every return door heals the chain ═══
                print("\n=== leg C: the return chain, walked back ===")
                steps = 0
                while steps < 6:
                    frm = page.evaluate("""() => {
                        const f = document.querySelector('.hy-from');
                        return f ? { text: f.textContent.trim(), ok: !f.textContent.includes('/') } : null;
                    }""")
                    if not frm:
                        break
                    ok(frm["ok"],
                       f'walk-back {steps + 1}: the door names its origin in journey words ("{frm["text"]}")')
                    page.evaluate("() => document.querySelector('.hy-from').click()")
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(500)
                    steps += 1
                ok(steps >= 1, f"the return chain walked back {steps} crossing(s) without a dead end")

                # ═══ LEG D — the whole session's health ═══
                print("\n=== leg D: the session health ===")
                ok(len(errs) == 0,
                   f"zero uncaught page errors across the whole walk ({errs[0] if errs else 'clean'})")
            finally:
                browser.close()

        print(f"\nENGINE WELD — {state['passed']} assertions green.")
        return 0
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        if scanner is not None:
            scanner.kill()


def do_list(root: Path, walks: list[Path]) -> int:
    """Enumerate every discovered walk (mutating ones marked), one per line, count at the end."""
    mutating = 0
    for w in walks:
        rel = _rel(root, w)
        if is_mutating(w):
            mutating += 1
            print(f"{rel}  [mutating — excluded from default runs; --include-mutating]")
        else:
            print(rel)
    if mutating:
        print(f"{len(walks)} walks ({mutating} mutating, excluded from default runs)")
    else:
        print(f"{len(walks)} walks")
    return 0


def do_run(root: Path, walks: list[Path], excluded: list[Path],
           timeout: int, json_path: str | None) -> int:
    records: list[dict] = []
    failed: list[str] = []
    fail_output: dict[str, str] = {}

    print(f"running {len(walks)} walks serially (timeout {timeout}s each)\n")
    for w in excluded:
        print(f"{EXCLUDED_NOTE}  {_rel(root, w)}")
    for w in walks:
        rel = _rel(root, w)
        status, seconds, output = run_walk(root, w, timeout)
        records.append({"file": rel, "status": status, "seconds": round(seconds, 2)})
        if status == "pass":
            verdict = "PASS"
        elif status == "timeout":
            verdict = "FAIL(timeout)"
            failed.append(rel)
            fail_output[rel] = output
        else:
            verdict = "FAIL"
            failed.append(rel)
            fail_output[rel] = output
        print(f"{verdict:<14} {rel}  {seconds:.1f}s")

    passed = len(walks) - len(failed)
    print("\n" + "=" * 60)
    print(f"summary: passed {passed}  failed {len(failed)}  total {len(walks)}"
          + (f"  excluded {len(excluded)}" if excluded else ""))
    if failed:
        print("failed walks:")
        for rel in failed:
            print(f"  - {rel}")
        for rel in failed:
            print(f"\n----- last {TAIL_LINES} lines of {rel} -----")
            print(_tail(fail_output[rel]))

    if json_path:
        record = {
            "walks": records,
            "passed": passed,
            "failed": len(failed),
            "excluded": [_rel(root, w) for w in excluded],
        }
        Path(json_path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote machine record → {json_path}")

    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Batch-run the tests/*.playwright.mjs browser walks (AUDIT_2026-07-15 §C3/§C5)."
    )
    ap.add_argument("--list", action="store_true",
                    help="enumerate discovered walks (one per line, mutating marked, count last), do not run")
    ap.add_argument("--only", action="append", metavar="SUBSTR",
                    help="run only walks whose path contains SUBSTR (repeatable, OR-combined)")
    ap.add_argument("--include-mutating", action="store_true",
                    help="also run the MUTATING_WALKS (write-path proofs that rewrite live ledgers; "
                         "excluded from default runs — §C5)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, metavar="SECS",
                    help=f"per-walk timeout in seconds (default {DEFAULT_TIMEOUT}); a hung walk is FAIL(timeout)")
    ap.add_argument("--json", metavar="PATH", default=None,
                    help="also write a machine record {walks:[{file,status,seconds}], passed, failed, excluded}")
    ap.add_argument("--repo", default=None,
                    help="repo root (default: the repo this script lives in)")
    ap.add_argument("--weld-python", action="store_true",
                    help="run the Python port of tests/engine_weld.playwright.mjs via the "
                         "running interpreter's sync_playwright, instead of the node walks "
                         "(the box-general fallback for boxes with no node-side Playwright "
                         "install — same four legs, same assertion messages). Ignores --only "
                         "and --list; use --timeout to bound it.")
    args = ap.parse_args(argv)

    root = Path(args.repo).resolve() if args.repo else repo_root()

    if args.weld_python:
        return run_weld_python(root, args.timeout)

    all_walks = filter_walks(discover_walks(root, include_mutating=True), args.only)

    if not all_walks:
        print("no walks discovered"
              + (f" matching --only {args.only}" if args.only else ""), file=sys.stderr)
        return 1

    if args.list:
        return do_list(root, all_walks)

    # ── the refusal fence ────────────────────────────────────────────────────────
    # --list is pure discovery and needs nothing; ANY actual run needs the walks'
    # preconditions. Refuse above the run, so no walk is spawned, no verdict is
    # printed, and --json is never written with a record of nothing.
    absent = walk_preconditions(root)
    if absent:
        print(refusal_line("PLAYWRIGHT WALKS",
                           f"{len(absent)} precondition(s) the walks need", absent),
              file=sys.stderr)
        print(f"  {len(all_walks)} walk(s) were discovered and NONE was run.",
              file=sys.stderr)
        if args.json:
            print(f"  --json {args.json} was NOT written (a refusal banks nothing).",
                  file=sys.stderr)
        return REFUSAL_EXIT

    if args.include_mutating:
        runnable, excluded = all_walks, []
    else:
        runnable = [w for w in all_walks if not is_mutating(w)]
        excluded = [w for w in all_walks if is_mutating(w)]
    if not runnable:
        for w in excluded:
            print(f"{EXCLUDED_NOTE}  {_rel(root, w)}")
        print("no runnable walks (all matched walks are mutating — use --include-mutating)",
              file=sys.stderr)
        return 1
    return do_run(root, runnable, excluded, args.timeout, args.json)


if __name__ == "__main__":
    # Windows consoles default stdio to the system codepage (cp1252 etc.), not UTF-8 —
    # every unicode glyph this runner or a walk's own assertion messages print (→, ←,
    # ·, ✎, …) then raises UnicodeEncodeError mid-run instead of just printing. Linux
    # terminals are UTF-8 by default and need no override. Best-effort: a stream that
    # refuses to reconfigure (piped through something exotic) just keeps its own encoding.
    if sys.platform == "win32":
        for _stream in (sys.stdout, sys.stderr):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    sys.exit(main())
