"""offline_launcher.py - the one launch authority for the local interface.

The author works his manuscripts in the browser (laplace.web.scanner, the live
conceptric viewer + reader). Two callers need to raise that interface, and
before this module there were TWO copies of the same port-free/spawn/browser
dance: the session-start hook (Windows branch) did it in inline PowerShell, and
there was no standalone path at all - the author could only get the interface up
when a Claude session opened it for him. His ruling (2026-07-13): give the launch
ONE home, callable BOTH from the hook AND by double-clicking on his Windows box
with no Claude present. This module is that home.

  * :func:`free_port`      - reap whatever stale scanner is squatting on the port.
  * :func:`preflight`      - an DECLARED capability table (never blocks launch).
  * :func:`scanner_status` - probe the port WITHOUT touching it: cold / fresh /
                             stale / wedged / foreign / unknown.
  * :func:`launch`         - IDEMPOTENT: reuse a fresh scanner, restart a stale
                             one, spawn on cold; open browser tabs per policy.
  * :func:`main`           - the ``laplace-review`` console script + ``python -m``
                             entry; defaults to opening the dashboard landing page (/).

The launch is idempotent (his complaint, 2026-07-15: every session start killed a
healthy scanner and opened two MORE browser tabs). A running scanner is derived
state: its producer is this launcher, its freshness invariant is "process started
after the newest src/laplace mtime", and the self-heal is a restart. Reuse never
opens tabs under ``--tabs cold`` (the hook's policy): tabs are only opened when
the server was actually cold - at most one pair per boot, not per session.

Everything here is stdlib + ``psutil`` only (psutil is already a core dep). The
process/browser handling is deliberately Windows-first but POSIX-safe: no
signals beyond the psutil API, no ``start_new_session`` on Windows, no
``shell=True``. See the "Offline feedback (no live Claude)" section of
``OPERATOR_STARTUP_GUIDE.md`` for the operator-facing runbook.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared core dep; this is the safety net
    psutil = None  # type: ignore

DEFAULT_PORT = 8770
GUIDE_PATH = "/"  # W5: the dashboard is home (/); the /guide explainer died (its desk rehoused to /desk)

#: env override for the pre-serve state offer, in the same setdefault/override spirit as the PSU
#: guards in _scanner_env (LAPLACE_EMBED_BUDGET/THREADS). Default ON; set to 0/false/no to skip
#: (a remote/CI escape hatch). It NEVER changes the fire policy -- an expensive rebuild is never
#: auto-fired regardless of this flag; this only silences the offer entirely.
STATE_OFFER_ENV = "LAPLACE_STATE_OFFER"


# ---------------------------------------------------------------------------
# the pre-serve state OFFER - warm the cheap, offer the expensive (never fire it)
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    # src/laplace/desktop/offline_launcher.py -> parents[2] == the repo root (src/laplace/..)
    return source_tree()


def offer_state(root: Path | None = None, manifest: Path | None = None) -> dict:
    """Pre-serve derived-state posture: WARM the cheap state, OFFER the expensive, FIRE nothing
    expensive -- the PSU law (the exact class that crashed his box twice: a launch must never
    trigger a heavy rebuild).

    Two moves, each subprocess-observable:

      1. ``ensure_state.py --cheap-only`` -- fires ONLY ``cost=cheap`` entries (by the forward
         law a cheap entry never induces PSU-class compute), so warming them at launch is safe.
      2. Every ``cost=expensive`` entry is CHECK-ONLY here (its ``check`` command, never its
         ``rebuild``): a failing check becomes an OFFER line -- the entry name + its exact fix
         command -- printed for the author to fire deliberately. The rebuild is never invoked.

    Returns ``{skipped}`` when disabled via :data:`STATE_OFFER_ENV`, else
    ``{cheap_verdict, offers:[{name, fix}, ...]}``. Never raises: a missing/unreadable manifest
    or a missing ensure_state script degrades to a printed WARN and an empty offer, so a launch
    is never sunk by the offer step (mirrors the browser/preflight best-effort posture)."""
    flag = os.environ.get(STATE_OFFER_ENV, "1").strip().lower()
    if flag in ("0", "false", "no", "off", ""):
        print(f"[offline-launcher] state offer disabled ({STATE_OFFER_ENV}={flag!r})")
        return {"skipped": True}

    root = Path(root) if root else _repo_root()
    manifest = Path(manifest) if manifest else root / "localstate.json"
    ensure_state = _repo_root() / "scripts" / "ensure_state.py"

    # 1. warm the cheap state (safe, non-PSU by the forward law). Best-effort: a failure here
    #    is reported, never fatal.
    cheap_verdict = "(not run)"
    if ensure_state.is_file():
        try:
            proc = subprocess.run(
                [sys.executable, str(ensure_state), "--manifest", str(manifest),
                 "--root", str(root), "--cheap-only"],
                capture_output=True, text=True, cwd=str(root), timeout=600,
            )
            lines = (proc.stdout or "").rstrip().splitlines()
            cheap_verdict = lines[-1] if lines else "(no output)"
            print(f"[offline-launcher] ensure_state --cheap-only: {cheap_verdict}")
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[offline-launcher] WARN: ensure_state --cheap-only failed to run: {exc}")
    else:
        print(f"[offline-launcher] WARN: {ensure_state} not found; skipping cheap warm")

    # 2. OFFER the expensive misses -- CHECK ONLY, never a rebuild (the PSU law).
    offers: list[dict] = []
    try:
        entries = json.loads(manifest.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[offline-launcher] WARN: manifest {manifest} unreadable ({exc}); no offer")
        return {"cheap_verdict": cheap_verdict, "offers": [], "error": str(exc)}

    from laplace.core.process import normalize_cmd, run_manifest_cmd
    for e in entries:
        if e.get("cost") != "expensive" or "check" not in e or "rebuild" not in e:
            continue
        try:
            # POSIX semantics on every platform (core.process) - a manifest check run
            # through cmd.exe reports a false miss on everything (`test`/`find`/`[`).
            rc = run_manifest_cmd(e["check"], root).returncode
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[offline-launcher] WARN: check for {e.get('name')!r} failed to run: {exc}")
            rc = 1  # a check that cannot run is treated as a miss -> offer it, still never fire
        if rc != 0:
            # the fix is shown normalized for the root it runs in: the copy-paste command for THIS box
            offers.append({"name": e["name"], "fix": normalize_cmd(e["rebuild"], root)})

    if offers:
        print(f"[offline-launcher] {len(offers)} expensive derived-state item(s) STALE/MISSING "
              f"-- OFFERED, not fired (PSU law: a launch never triggers an expensive rebuild):")
        for o in offers:
            print(f"    {o['name']}: {o['fix']}")
    else:
        print("[offline-launcher] expensive derived-state present+fresh (nothing to offer)")

    return {"cheap_verdict": cheap_verdict, "offers": offers}


# ---------------------------------------------------------------------------
# free the port
# ---------------------------------------------------------------------------

def _listening_pids(port: int) -> set[int]:
    """PIDs LISTENING on ``port`` (empty when none, psutil missing, or permission denied)."""
    if psutil is None:
        return set()
    pids: set[int] = set()
    try:
        for conn in psutil.net_connections(kind="inet"):
            if (
                conn.laddr
                and conn.laddr.port == port
                and conn.status == psutil.CONN_LISTEN
                and conn.pid
            ):
                pids.add(conn.pid)
    except (psutil.AccessDenied, PermissionError):  # pragma: no cover - needs root on some OSes
        print(f"[offline-launcher] permission denied enumerating port {port}")
    return pids


def free_port(port: int = DEFAULT_PORT) -> int:
    """Terminate whatever process is LISTENING on ``port`` so a fresh scanner can bind.

    Returns the count of processes reaped (0 when nothing was listening, or when
    psutil is missing / permission is denied - a no-op in every one of those
    cases, never an exception). Windows-safe: only the psutil terminate/kill API
    is used, no POSIX signals.
    """
    if psutil is None:
        print(f"[offline-launcher] free_port: psutil unavailable, skipping port {port}")
        return 0

    pids = _listening_pids(port)

    if not pids:
        print(f"[offline-launcher] free_port: nothing listening on {port}")
        return 0

    reaped = 0
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            reaped += 1
            print(f"[offline-launcher] free_port: reaped pid {pid} on port {port}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue  # already gone, or not ours to touch - fine
    return reaped


# ---------------------------------------------------------------------------
# scanner_status - probe the port WITHOUT touching it (the reuse decision)
# ---------------------------------------------------------------------------

def _http_alive(port: int) -> bool:
    """One-shot: does anything answer HTTP on the port? (even a 4xx means bound+serving)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2.0) as resp:  # noqa: S310 - localhost only
            return resp.status < 500
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def _code_mtime(root: Path | None = None) -> float:
    """Newest mtime under src/laplace - the scanner's serving surface (code + static).

    Docs/manuscripts are read per-request and need no restart; only the installed
    code and its static assets go stale in a running process. __pycache__ is
    skipped (a .pyc write must not mark the live server stale)."""
    root = root or (_repo_root() / "src" / "laplace")
    newest = 0.0
    try:
        for p in root.rglob("*"):
            if "__pycache__" in p.parts:
                continue
            try:
                if p.is_file():
                    newest = max(newest, p.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        pass
    return newest


def scanner_status(port: int = DEFAULT_PORT) -> dict:
    """Probe the port read-only and classify what is there. Never kills anything.

    States (the ``state`` key):
      * ``cold``    - nothing bound, nothing answering: a spawn is needed.
      * ``fresh``   - OUR scanner, answering, started after the newest src/laplace
                      mtime: reuse it, restart nothing.
      * ``stale``   - our scanner, answering, but the code moved after it started
                      (a pull, an edit): restart to self-heal the freshness invariant.
      * ``wedged``  - bound but not answering HTTP: restart.
      * ``foreign`` - the listener's cmdline is not laplace.web.scanner: reclaim the port
                      (the old unconditional behavior, now scoped to actual squatters).
      * ``unknown`` - answering but uninspectable (no psutil / no visible pid):
                      reuse with a WARN - freshness unproven, but churn is worse.
    """
    alive = _http_alive(port)
    pids = _listening_pids(port)

    if not alive and not pids:
        return {"state": "cold", "detail": f"nothing on port {port}"}
    if not alive:
        return {"state": "wedged", "detail": f"pid(s) {sorted(pids)} bound but not answering"}
    if psutil is None or not pids:
        return {"state": "unknown", "detail": "answering, but the listener is uninspectable"}

    for pid in sorted(pids):
        try:
            proc = psutil.Process(pid)
            cmdline = " ".join(proc.cmdline())
            started = proc.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
        if "laplace.web.scanner" not in cmdline:
            return {"state": "foreign", "pid": pid, "detail": f"pid {pid}: {cmdline[:120]}"}
        code = _code_mtime()
        if code > started:
            age = code - started
            return {"state": "stale", "pid": pid,
                    "detail": f"pid {pid}: src/laplace moved {age:.0f}s after the scanner started"}
        return {"state": "fresh", "pid": pid, "detail": f"pid {pid}, serving current code"}
    return {"state": "unknown", "detail": "answering, but no listener pid was inspectable"}


# ---------------------------------------------------------------------------
# preflight - an honest capability table, never a gate
# ---------------------------------------------------------------------------

def _embed_model_present() -> bool:
    """True if the vendored embedding model is reachable WITHOUT network.

    Reuses embed_router's path logic (the vendored tarball, the extracted cache,
    or fastembed's own HF/GCS cache) rather than re-authoring it. Side-effect
    free: we check for the tarball / extracted onnx, we never trigger extraction.
    """
    try:
        from laplace.representation import embed_router as _er
    except Exception:  # noqa: BLE001 - launcher must not depend on the embedder importing
        return False

    # 1. tarball vendored in the repo (extracts on first real load)
    if _er._VENDOR_TARBALL.exists():
        return True
    # 2. already extracted to the local cache
    extracted = _er._VENDOR_EXTRACT / "fast-bge-small-en-v1.5" / "model_optimized.onnx"
    if extracted.exists():
        return True
    # 3. fastembed's own HF/GCS cache (the fallback layout)
    cache = getattr(_er, "MODEL_CACHE", None)
    if cache is not None and Path(cache).exists() and any(Path(cache).iterdir()):
        return True
    return False


def preflight() -> dict:
    """Report local capability as a dict; PRINT a plain table. NEVER blocks launch.

    Keys: ``pdflatex``, ``latexmk``, ``pdftoppm``, ``pdftotext`` (bool: on PATH),
    and ``embed_model`` (bool: vendored/cached model reachable offline). The
    printed notes are deliberately reassuring where they should be:

      * poppler (pdftoppm/pdftotext) is OPTIONAL for *viewing* - pdf.js renders
        the PDF client-side in the browser; poppler only sharpens the text-layer
        search and the PNG fallback path.
      * TeX (pdflatex/latexmk) only blocks *recompiles*; re-projecting a
        manuscript needs a live Claude instance anyway, so its absence never
        stops the reader/feedback loop from coming up.
    """
    caps = {
        "pdflatex": shutil.which("pdflatex") is not None,
        "latexmk": shutil.which("latexmk") is not None,
        "pdftoppm": shutil.which("pdftoppm") is not None,
        "pdftotext": shutil.which("pdftotext") is not None,
        "embed_model": _embed_model_present(),
    }

    def mark(ok: bool) -> str:
        return "found  " if ok else "MISSING"

    print("[offline-launcher] preflight (nothing here blocks launch):")
    print(f"    pdflatex    {mark(caps['pdflatex'])}   TeX - only needed to RECOMPILE (a re-projection needs a live instance anyway)")
    print(f"    latexmk     {mark(caps['latexmk'])}   TeX - as above")
    print(f"    pdftoppm    {mark(caps['pdftoppm'])}   poppler - OPTIONAL for viewing (pdf.js renders in-browser; poppler only sharpens PNG fallback)")
    print(f"    pdftotext   {mark(caps['pdftotext'])}   poppler - OPTIONAL (only sharpens the text-layer search)")
    print(f"    embed_model {mark(caps['embed_model'])}   vendored bge-small - recall runs offline when found")
    return caps


# ---------------------------------------------------------------------------
# launch - free, spawn, wait, open
# ---------------------------------------------------------------------------

def _scanner_env() -> dict:
    """The child env: inherit ours, force UTF-8 stdio as the session-start hook does.

    The PSU guard rides here (2026-07-13, the two Kernel-Power 41 hard crashes): this launcher
    is the one home for the LOCAL scanner (the hook and review.bat both route through it). F1
    ESCALATED freeze-class -> PSU-class (ARMING_2026-07-15 SS3; WALK_2026-07-15 F1): the
    128-node serving-path drip still starved the box 30-60s on the first post-pull clicks, and
    the same evening the box PSU-crashed, so by standing law (local-numerics-trip-the-psu) the
    stricter rule wins -- the LOCAL box must not embed on the serving path AT ALL. Default
    ``LAPLACE_EMBED_BUDGET=0`` turns the drip OFF: the serving path serves the vectors as-is
    (degraded-but-plain, staleness named in the UI) and NEVER embeds; the vector warm runs
    REMOTE or at the supervised close deposit (the ``bulk=True`` producer fold, which ignores
    the budget), never on first click. The thread cap stays a belt-and-braces bound for any
    explicit override. ``setdefault`` so an explicit env still wins (a remote/supervised caller
    may set a positive budget to drip deliberately, or unset it for the pre-guard unlimited
    posture). Provenance: WO-20260715-233320-psu-embed-off."""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # THE CAPACITY AMENDMENT (his ruling 2026-07-23, amending WO-20260715-233320-psu-embed-off:
    # "let's actually give ourselves the capacity we need rather than crippling ourselves. If
    # it trips the PSU it's annoying but we'll know at least"): a SMALL SERIAL drip, not the
    # 128-node first-click starve that earned the OFF posture. Budget 6 × one thread is a few
    # seconds of single-core work per call; the loud per-batch DRIP lines in embed_router are
    # the tripwire — any regression is visible and attributable, and 0 remains one env var away.
    env.setdefault("LAPLACE_EMBED_BUDGET", "6")
    env.setdefault("LAPLACE_EMBED_THREADS", "1")
    # THE SERVING CONTRACT rides to the child EXPLICITLY and is SAID. `dict(os.environ)`
    # already carries it, but a gate whose activation is invisible is a gate nobody can
    # trust: the launcher is where the scanner is born, so it is where the narrowing is
    # announced. The token itself is never printed — only that one is set.
    from laplace.manuscript import walk as _wk
    if _wk._truthy(env.get(_wk.WALK_ONLY_ENV, "")):
        env[_wk.WALK_ONLY_ENV] = env.get(_wk.WALK_ONLY_ENV, "1")
        tok = (env.get(_wk.WALK_TOKEN_ENV) or "").strip()
        if tok:
            env[_wk.WALK_TOKEN_ENV] = tok
        print(f"[offline-launcher] {_wk.WALK_ONLY_ENV} set -- this scanner serves the "
              "redline walk only (/walk, /walk/*, /shared/*, /review/*, /projection/*, "
              "/artefact/context); every other route answers 403 in words"
              + (f"; {_wk.WALK_TOKEN_ENV} is set, so every request must carry the token"
                 if tok else
                 f"; {_wk.WALK_TOKEN_ENV} is unset, so no token is required"))
    return env


def _spawn_scanner(port: int) -> subprocess.Popen:
    """Spawn a DETACHED scanner so the launcher can exit while the server keeps serving.

    On Windows we pass ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`` (and never
    ``start_new_session``, which is POSIX-only). On POSIX we use
    ``start_new_session`` to escape the launcher's process group.
    """
    cmd = [sys.executable, "-m", "laplace.web.scanner", "--port", str(port)]
    kwargs: dict = {
        "env": _scanner_env(),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """Poll the scanner until it answers on / (the dashboard landing). True if it came up."""
    deadline = time.monotonic() + timeout
    urls = [f"http://127.0.0.1:{port}/", f"http://127.0.0.1:{port}{GUIDE_PATH}"]
    while time.monotonic() < deadline:
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:  # noqa: S310 - localhost only
                    if resp.status < 500:
                        return True
            except urllib.error.HTTPError:
                return True  # it answered (even a 4xx means the server is bound)
            except (urllib.error.URLError, OSError):
                pass
        time.sleep(0.25)
    return False


def _should_open_tabs(tabs: str, state: str) -> bool:
    """The tab policy, pure: ``always`` opens; ``never`` doesn't; ``cold`` opens ONLY
    when nothing was serving beforehand (so a reused/restarted server - whose tabs
    are already sitting in the browser - never spawns more)."""
    if tabs == "never":
        return False
    if tabs == "always":
        return True
    return state == "cold"


def launch(
    open_urls: list[str] | None = None,
    port: int = DEFAULT_PORT,
    spawn_browser: bool = True,
    tabs: str = "always",
    force_restart: bool = False,
) -> subprocess.Popen | None:
    """Bring the local interface up IDEMPOTENTLY; open browser tabs per policy.

    A ``fresh`` scanner (ours, answering, started after the newest src/laplace
    mtime) is REUSED - no kill, no respawn. ``stale``/``wedged``/``foreign``
    listeners are reclaimed and a fresh scanner spawned; ``cold`` just spawns.
    ``tabs`` is one of ``always`` / ``cold`` / ``never`` (see
    :func:`_should_open_tabs`); ``spawn_browser=False`` is the legacy spelling of
    ``never``. Returns the new scanner's Popen handle, or None when reused or the
    spawn failed. Browser opening stays best-effort - a failure never raises.
    """
    if open_urls is None:
        open_urls = [f"http://127.0.0.1:{port}{GUIDE_PATH}"]
    if not spawn_browser:
        tabs = "never"

    status = scanner_status(port)
    state = status["state"]
    print(f"[offline-launcher] scanner status: {state} ({status['detail']})")

    proc: subprocess.Popen | None = None
    if not force_restart and state in ("fresh", "unknown"):
        if state == "unknown":
            print("[offline-launcher] WARN: freshness unproven (uninspectable listener); reusing anyway")
        print(f"[offline-launcher] reusing the running scanner on port {port}")
    else:
        free_port(port)
        try:
            proc = _spawn_scanner(port)
        except Exception as exc:  # noqa: BLE001 - report and bail, don't traceback at the user
            print(f"[offline-launcher] ERROR: could not spawn scanner: {exc}")
            return None
        print(f"[offline-launcher] scanner spawned (pid {proc.pid}) on port {port}")

        if _wait_for_port(port):
            print(f"[offline-launcher] scanner is answering on port {port}")
        else:
            print(f"[offline-launcher] WARN: scanner did not answer within timeout; pages retry on load")

    if _should_open_tabs(tabs, state):
        for url in open_urls:
            try:
                webbrowser.open(url)
                print(f"[offline-launcher] opened {url}")
            except Exception as exc:  # noqa: BLE001 - a browser failure never sinks the launch
                print(f"[offline-launcher] WARN: could not open {url}: {exc}")
    else:
        for url in open_urls:
            print(f"[offline-launcher] tab NOT opened (tabs={tabs}, state={state}): {url}")

    return proc


# ---------------------------------------------------------------------------
# main - the console-script / python -m entry
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="laplace-review",
        description="Raise the local Laplace interface (reader + feedback) with no Claude present.",
    )
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to serve on (default 8770)")
    p.add_argument(
        "--no-browser",
        dest="spawn_browser",
        action="store_false",
        help="free the port and spawn the scanner, but do not open a browser",
    )
    p.add_argument(
        "--url",
        dest="urls",
        action="append",
        default=None,
        help="URL to open (repeatable); defaults to the dashboard landing page (/)",
    )
    p.add_argument(
        "--tabs",
        choices=("always", "cold", "never"),
        default="always",
        help="when to open browser tabs: always (default - a deliberate launch gets its tab), "
        "cold (only when nothing was serving - the session-start hook's policy, so repeated "
        "sessions stop stacking duplicate tabs), never",
    )
    p.add_argument(
        "--restart",
        dest="force_restart",
        action="store_true",
        help="force a kill+respawn even when the running scanner is fresh",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # LAPLACE_NO_NAVIGATOR is enforced HERE, in the one launch home, so every
    # caller (hook, review.bat, a bare python -m) honors the same kill-switch --
    # the hook's own early-exit check merely saves an interpreter spawn.
    if os.environ.get("LAPLACE_NO_NAVIGATOR", "").strip().lower() not in ("", "0", "false", "no", "off"):
        args.tabs = "never"
        print("[offline-launcher] LAPLACE_NO_NAVIGATOR set -- browser tabs suppressed")
    preflight()
    offer_state()  # warm the cheap derived state, OFFER the expensive (never fire it -- the PSU law)
    urls = args.urls if args.urls else [f"http://127.0.0.1:{args.port}{GUIDE_PATH}"]
    launch(
        open_urls=urls,
        port=args.port,
        spawn_browser=args.spawn_browser,
        tabs=args.tabs,
        force_restart=args.force_restart,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
