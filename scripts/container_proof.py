#!/usr/bin/env python
"""FRESH-CONTAINER PROOF (Leg C, bite C3) -- prove a cold clone surfaces the whole pipeline.

The fear this mechanises: HIS local machine clones this branch and something silently
does not work. This is the scripted, repeatable precondition for the author's Leg D
review. ONE entry, ONE argument (a work dir), a JSON proof report, exit 0 (all green) /
2 (any leg FAILED — the clone is broken) / 3 (any leg REFUSED — this box is missing the
INSTRUMENT that leg needs, so the leg measured nothing; not a pass, not a graded fail).

The legs (each emits one report line: {step, command, exit, duration}):

  1. clone            COLD CLONE via a LOCAL file:// url (no network dependency on
                      GitHub): the committed branch, checked out fresh.
  2a. bootstrap_venv  the REAL hook bootstrap reconstructed from
                      .claude/hooks/session-start.mjs: `uv venv` + editable install with
                      the dev,figures,analysis extras (the vendored embedding model rides
                      the checkout at models/fastembed). Default = a TRUE COLD VENV in the
                      clone (Path A). Sanctioned fallback when disk is tight: reuse the
                      parent venv READ-ONLY + PYTHONPATH at the clone's src (Path B) -- the
                      true cold-venv leg then rides only the close run / his machine.
  2b. bootstrap_tex   the FIXED scripts/ensure_tex.sh: on a box that already has pdflatex
                      it must no-op with the loud SUCCESS verdict (proves idempotency +
                      the fail-loud contract).
  3. wake             the grade-0 self-reconstruction returns NON-EMPTY from the CLONE
                      (laplace.engine.self_corpus.reconstruct_self(<clone>, grade=0), the headless
                      surface the MCP verb laplace_reconstruct_self wraps). The fixed point
                      must carry shards.
  4. detect           ONE mechanical round on SSG in the clone -- the header/usage form of
                      .claude/workflows/fixedpoint_mechround.py, project passed explicitly,
                      findings poured to a THROWAWAY ledger. Asserts the organ RUNS cold and
                      emits its evidence file with a sane structure (NOT asserting zero
                      findings). The fresh-compile variant (the JS driver's `... compile`
                      form) rides the close run / his machine.
  5. serve_smoke      serve `python -m laplace.web.scanner --port <high>` FROM THE CLONE, drive
                      /review?corpus=subset-sum-itqde with the banked B-1 Playwright idiom
                      (chromium at /opt/pw-browsers, never `playwright install`): the landing
                      view renders the NAMED artefact (ssg-whitepaper-2026-07-10-r2) and the
                      escalation queue. Kill the server after.
  6. suite            `python -m pytest tests/ -q` IN THE CLONE: green modulo the NAMED
                      sets only -- the environmental set (the synctex visual-gate tests)
                      and the banked fresh-clone-hostile defect (see FRESH_CLONE_HOSTILE).
                      A NEW failure -- one outside those named sets -- fails the proof.

Invoke:
  python scripts/container_proof.py [workdir]           # direct
  LAPLACE_RUN_CONTAINER_PROOF=1 python -m pytest \
      tests/test_container_proof.py -q                  # as a test (slow/e2e gate)

Env overrides:
  CONTAINER_PROOF_BRANCH   branch to clone (default: the source repo's current branch)
  CONTAINER_PROOF_VENV     'cold' (force Path A) | 'reuse' (force Path B) | auto (default)
  CONTAINER_PROOF_KEEP     if set, do NOT delete the workdir on a green run
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT.parent))
from service_probe import REFUSAL_EXIT, refusal_line  # noqa: E402

CORPUS = "subset-sum-itqde"
NAMED_ARTEFACT = "ssg-whitepaper-2026-07-10-r2"
WP_REL = "synthetics papers/subset-sum-itqde/manuscript/whitepaper"
MECH_REL = ".claude/workflows/fixedpoint_mechround.py"

# The named environmental failure set (bite C3): the synctex/rasteriser-gated visual
# gate tests that cannot pass without the synctex binary present. A failure OUTSIDE
# this set is a NEW failure and fails the proof.
KNOWN_ENV_FAILURES = {
    "tests/test_visual_gate.py::test_equation_region_maps_a_label",
    "tests/test_visual_gate.py::test_inspect_pdf_produces_all_mandatory_views_and_findings",
}

# BANKED C3 FINDING (run 1, 2026-07-10) -- FRESH-CLONE-HOSTILE tests, named separately
# from the environmental set so the defect stays VISIBLE, not blessed. The C2 surfacing
# audit's live-repo test asserts that gitignored latexmk artifacts (.aux/.bbl/.fls)
# exist in the working tree; they do in a lived-in checkout (a compile ran there) but
# CANNOT exist in a fresh clone (gitignored => never committed), so a cold
# `pytest tests/` is red at this node until the first compile. The FIX belongs in
# tests/test_surfacing_audit.py (a fresh-clone skip-guard or a compiled fixture) --
# outside this bite's pathspec, banked as a fork for the C2 owner. Until then the
# proof tolerates EXACTLY this node and keeps reporting it in the suite leg's note.
FRESH_CLONE_HOSTILE = {
    "tests/test_surfacing_audit.py::test_real_repo_recognises_latexmk_artifacts_as_reconstructable",
}

# The mechround round file's load-bearing keys (probed from a live run, never assumed):
# the evidence file is "sane" iff these are all present, round==1, and panel is a list.
MECH_REQUIRED_KEYS = {"round", "panel", "contract", "complete", "target", "workflow"}


def _run(cmd, cwd=None, env=None, timeout=None):
    """Run a command; return (exit, duration_s, stdout, stderr). Never raises on non-zero."""
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, cwd=cwd, env=env, timeout=timeout,
            capture_output=True, text=True,
        )
        return p.returncode, round(time.time() - t0, 2), p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        return 124, round(time.time() - t0, 2), (e.stdout or ""), f"TIMEOUT after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return 125, round(time.time() - t0, 2), "", f"{type(e).__name__}: {e}"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _git(args, cwd) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True,
    ).stdout.strip()


class Proof:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.steps: list[dict] = []
        self.venv_path_taken = "unknown"
        self.source_repo = Path(_git(["rev-parse", "--show-toplevel"], SCRIPT.parent))
        self.branch = os.environ.get("CONTAINER_PROOF_BRANCH") or _git(
            ["rev-parse", "--abbrev-ref", "HEAD"], self.source_repo
        )
        self.clone = self.workdir / "laplace-cold"
        self.clone_py: Path | None = None
        self.base_env: dict = dict(os.environ)
        # never let the SUITE-in-clone re-enter this proof (recursion guard):
        self.base_env.pop("LAPLACE_RUN_CONTAINER_PROOF", None)

    # -- report plumbing ---------------------------------------------------
    def record(self, step, command, exit_code, duration, ok, note=""):
        self.steps.append({
            "step": step, "command": command, "exit": exit_code,
            "duration": duration, "ok": ok, "note": note,
        })
        flag = "OK " if ok else "XX "
        print(f"[{flag}] {step:16s} exit={exit_code} {duration}s  {note}", flush=True)
        return ok

    def skip(self, step, why):
        self.steps.append({
            "step": step, "command": "(skipped)", "exit": None,
            "duration": 0, "ok": False, "note": "SKIPPED: " + why,
        })
        print(f"[-- ] {step:16s} SKIPPED: {why}", flush=True)

    def refuse(self, step, absent, tried=None):
        """REFUSED TO GRADE — the leg's INSTRUMENT is missing, so the leg measured
        nothing. Distinct from a failed leg (the clone is broken) and from a skipped
        leg (an earlier leg failed): an unmeasured leg makes the whole proof a
        refusal, never a PASS and never a graded FAIL.

        The distinction is the whole point of the leg. `serve_smoke` proves the CLONE
        serves; if the clone's own scanner will not boot that is a real FAIL. If the
        node driver that watches it is not installed on this box, nothing about the
        clone was learned — and calling that a proof failure blames the patient for
        the missing stethoscope."""
        self.steps.append({
            "step": step, "command": "(refused)", "exit": None, "duration": 0,
            "ok": None, "refused": True,
            "note": "REFUSED TO GRADE: " + absent
                    + (" | probed: " + "; ".join(tried) if tried else ""),
        })
        print(f"[?? ] {step:16s} REFUSED TO GRADE: {absent}", flush=True)
        if tried:
            for t in tried:
                print(f"       probed: {t}", flush=True)
        return None

    @staticmethod
    def _smoke_driver_deps() -> list[str]:
        """What the node smoke driver needs before it can drive anything. These are the
        PROOF'S INSTRUMENT, not the artefact under proof — their absence refuses."""
        absent: list[str] = []
        if not shutil.which("node"):
            absent.append("node on PATH (the smoke driver is an ES module)")
            return absent
        try:
            npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True,
                                      text=True, timeout=20).stdout.strip()
        except Exception as exc:                                   # noqa: BLE001
            return absent + [f"npm root -g would not answer ({type(exc).__name__})"]
        if npm_root and not (Path(npm_root) / "playwright").is_dir():
            absent.append(f"the global playwright package at {npm_root}/playwright "
                          "(the driver does require(<npm root -g>/playwright))")
        if not sorted(Path("/opt").glob("pw-browsers/chromium-*/chrome-linux/chrome")):
            absent.append("the vendored chromium at "
                          "/opt/pw-browsers/chromium-*/chrome-linux/chrome "
                          "(the driver resolves it with `ls` and dies if absent)")
        return absent

    # -- legs --------------------------------------------------------------
    def leg_clone(self) -> bool:
        src_url = "file://" + str(self.source_repo)
        cmd = ["git", "clone", "--branch", self.branch, src_url, str(self.clone)]
        rc, dur, out, err = _run(cmd, timeout=600)
        ok = rc == 0 and (self.clone / ".git").is_dir()
        note = "" if ok else (err or out).strip()[-300:]
        return self.record("clone", " ".join(cmd), rc, dur, ok, note)

    def leg_bootstrap_venv(self) -> bool:
        mode = os.environ.get("CONTAINER_PROOF_VENV", "auto")
        parent_py = self.source_repo / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "python"

        def take_reuse(reason):
            self.venv_path_taken = f"reused-parent-venv READ-ONLY (Path B): {reason}"
            self.clone_py = parent_py
            # PYTHONPATH at the clone's src so `import laplace` (and _repo_root) resolve
            # to the CLONE even though the interpreter is the parent's.
            self.base_env["PYTHONPATH"] = str(self.clone / "src") + os.pathsep + self.base_env.get("PYTHONPATH", "")

        if mode == "reuse":
            take_reuse("forced by CONTAINER_PROOF_VENV=reuse")
            ok = parent_py.exists()
            return self.record("bootstrap_venv", f"reuse {parent_py}", 0 if ok else 1, 0, ok, self.venv_path_taken)

        # Path A: a TRUE COLD VENV in the clone (the default; disk permitting).
        clone_venv = self.clone / ".venv"
        env = dict(self.base_env)
        env["VIRTUAL_ENV"] = str(clone_venv)
        rc1, d1, o1, e1 = _run(["uv", "venv", str(clone_venv)], cwd=self.clone, env=env, timeout=300)
        rc2, d2, o2, e2 = _run(
            ["uv", "pip", "install", "--quiet", "-e", ".[dev,figures,analysis]"],
            cwd=self.clone, env=env, timeout=1200,
        )
        cold_py = clone_venv / ("Scripts" if os.name == "nt" else "bin") / "python"
        cmd = "uv venv .venv && uv pip install -e '.[dev,figures,analysis]'"
        if rc1 == 0 and rc2 == 0 and cold_py.exists():
            self.venv_path_taken = "true-cold-venv in the clone (Path A)"
            self.clone_py = cold_py
            # PATH-prepend the cold venv bin so `python -m ...` and console scripts resolve there.
            self.base_env["VIRTUAL_ENV"] = str(clone_venv)
            self.base_env["PATH"] = str(cold_py.parent) + os.pathsep + self.base_env.get("PATH", "")
            return self.record("bootstrap_venv", cmd, 0, round(d1 + d2, 2), True, self.venv_path_taken)

        if mode == "cold":
            note = "COLD venv forced but failed: " + ((e1 or o1 or e2 or o2).strip()[-300:])
            return self.record("bootstrap_venv", cmd, rc2 or rc1 or 1, round(d1 + d2, 2), False, note)

        # auto: fall back to Path B (sanctioned when the cold venv can't be built).
        take_reuse("cold venv bootstrap failed: " + ((e2 or e1).strip()[-160:]))
        ok = parent_py.exists()
        return self.record("bootstrap_venv", cmd + " -> FALLBACK reuse", rc2 or rc1, round(d1 + d2, 2), ok, self.venv_path_taken)

    def leg_bootstrap_tex(self) -> bool:
        script = self.clone / "scripts" / "ensure_tex.sh"
        cmd = ["sh", str(script)]
        rc, dur, out, err = _run(cmd, cwd=self.clone, env=self.base_env, timeout=1200)
        last = ""
        for line in (out.strip().splitlines() or [""]):
            if line.strip():
                last = line.strip()
        # idempotent no-op on a box with pdflatex => exit 0 and a loud SUCCESS verdict.
        ok = rc == 0 and "ensure_tex: SUCCESS" in out
        note = f"verdict={last!r}" if ok else f"rc={rc} last={last!r} err={err.strip()[-160:]}"
        return self.record("bootstrap_tex", " ".join(cmd), rc, dur, ok, note)

    def leg_wake(self) -> bool:
        checker = self.workdir / "wake_check.py"
        checker.write_text(
            "import json, sys\n"
            "from laplace.engine import self_corpus\n"
            "clone = sys.argv[1]\n"
            "proj = self_corpus.reconstruct_self(clone, grade=0)\n"
            "shards = proj.get('shards') or []\n"
            "print('WAKE_JSON:' + json.dumps({\n"
            "    'n_shards': len(shards), 'keys': sorted(proj.keys()),\n"
            "    'laplace_file': self_corpus.__file__,\n"
            "    'first_source': (shards[0].get('source') if shards else None)}))\n"
            "sys.exit(0 if shards else 3)\n",
            encoding="utf-8",
        )
        cmd = [str(self.clone_py), str(checker), str(self.clone)]
        rc, dur, out, err = _run(cmd, cwd=self.clone, env=self.base_env, timeout=180)
        info = {}
        for line in out.splitlines():
            if line.startswith("WAKE_JSON:"):
                info = json.loads(line[len("WAKE_JSON:"):])
        n = info.get("n_shards", 0)
        from_clone = str(self.clone) in (info.get("laplace_file") or "")
        ok = rc == 0 and n > 0
        note = f"n_shards={n} code_from_clone={from_clone} first={info.get('first_source')!r}"
        if not ok:
            note += " ERR=" + (err.strip()[-200:] or out.strip()[-200:])
        return self.record("wake", str(self.clone_py) + " wake_check.py <clone>", rc, dur, ok, note)

    def leg_detect(self) -> bool:
        wp = self.clone / WP_REL
        round_file = self.workdir / "mech_round.json"
        throwaway = self.workdir / "mech_feedback_throwaway.jsonl"
        # header/usage form (mechround.py docstring argv 1..10): main_tex project corpus
        # log_path incumbent(-) candidate round round_file feedback dials(-)
        cmd = [
            str(self.clone_py), MECH_REL,
            str(wp / "main.tex"), CORPUS, CORPUS,
            str(wp / "main.log"), "-", str(wp / "main.pdf"),
            "1", str(round_file), str(throwaway), "-",
        ]
        rc, dur, out, err = _run(cmd, cwd=self.clone, env=self.base_env, timeout=600)
        ok = False
        note = ""
        if round_file.exists():
            try:
                d = json.loads(round_file.read_text(encoding="utf-8"))
                keys = set(d.keys())
                sane = MECH_REQUIRED_KEYS.issubset(keys) and d.get("round") == 1 and isinstance(d.get("panel"), list)
                ok = rc == 0 and sane
                note = (f"round={d.get('round')} panel_len={len(d.get('panel') or [])} "
                        f"flags_routed={d.get('flags_routed')} required_keys_present={MECH_REQUIRED_KEYS.issubset(keys)}")
            except Exception as e:  # noqa: BLE001
                note = f"round file unparseable: {e}"
        else:
            note = "no round file emitted; err=" + (err.strip()[-200:] or out.strip()[-200:])
        return self.record("detect", str(self.clone_py) + " fixedpoint_mechround.py <ssg header-form>", rc, dur, ok, note)

    def leg_serve_smoke(self):
        # THE INSTRUMENT FIRST. Probed before a scanner is spawned, so a box without the
        # node-side driver refuses in milliseconds instead of booting a server, driving
        # nothing at it, and recording a proof failure that describes the box, not the clone.
        absent = self._smoke_driver_deps()
        if absent:
            return self.refuse("serve_smoke",
                               "a dependency of the node smoke driver", absent)
        driver = self.workdir / "smoke_driver.mjs"
        driver.write_text(_SMOKE_DRIVER, encoding="utf-8")
        port = _free_port()
        serve_log = self.workdir / "scanner_serve.log"
        serve_cmd = [str(self.clone_py), "-m", "laplace.web.scanner", "--port", str(port)]
        server = None
        t0 = time.time()
        try:
            with open(serve_log, "wb") as lf:
                server = subprocess.Popen(
                    serve_cmd, cwd=self.clone, env=self.base_env,
                    stdout=lf, stderr=lf, start_new_session=True,
                )
            # Wait for the CLONE's scanner to bind + answer /review. This one stays a
            # graded FAIL when it does not: the clone serving is exactly what this leg
            # proves. Bounded by a wall-clock deadline (the old `range(80)` could spend
            # 200s when every connect attempt itself timed out) and it watches the child.
            up = False
            deadline = time.time() + 60
            while time.time() < deadline:
                if server.poll() is not None:
                    break
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/review", timeout=2)
                    up = True
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.5)
            if not up:
                dur = round(time.time() - t0, 2)
                tail = serve_log.read_text(errors="replace")[-300:]
                return self.record("serve_smoke", " ".join(serve_cmd), 1, dur, False, "server never came up: " + tail)

            dcmd = ["node", str(driver), str(port), CORPUS, NAMED_ARTEFACT]
            rc, ddur, out, err = _run(dcmd, cwd=self.clone, env=self.base_env, timeout=180)
            dur = round(time.time() - t0, 2)
            ok = rc == 0 and "ALL_GREEN" in out
            note = out.strip().splitlines()[-1] if out.strip() else (err.strip()[-200:])
            return self.record("serve_smoke", f"serve :{port} + node smoke_driver.mjs", rc, dur, ok, note)
        finally:
            if server is not None:
                try:
                    os.killpg(os.getpgid(server.pid), 9)
                except Exception:  # noqa: BLE001
                    try:
                        server.kill()
                    except Exception:  # noqa: BLE001
                        pass

    def leg_suite(self) -> bool:
        cmd = [str(self.clone_py), "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider", "--tb=no"]
        rc, dur, out, err = _run(cmd, cwd=self.clone, env=self.base_env, timeout=1800)
        failed = set()
        for line in out.splitlines():
            if line.startswith("FAILED "):
                node = line[len("FAILED "):].split(" - ")[0].strip()
                failed.add(node)
        tolerated = KNOWN_ENV_FAILURES | FRESH_CLONE_HOSTILE
        new_failures = failed - tolerated
        # PASS iff no failure outside the named tolerated sets (a NEW failure fails the proof).
        ok = len(new_failures) == 0
        summary = ""
        for line in out.splitlines():
            if " passed" in line or " failed" in line:
                summary = line.strip()
        note = (f"failed={sorted(failed)} new_failures={sorted(new_failures)} "
                f"env_set={sorted(failed & KNOWN_ENV_FAILURES)} "
                f"fresh_clone_hostile_BANKED_DEFECT={sorted(failed & FRESH_CLONE_HOSTILE)} | {summary}")
        return self.record("suite", str(self.clone_py) + " -m pytest tests/ -q", rc, dur, ok, note)

    # -- driver ------------------------------------------------------------
    def run(self) -> int:
        print(f"container_proof: source={self.source_repo} branch={self.branch}")
        print(f"container_proof: workdir={self.workdir}")
        legs = [
            ("clone", self.leg_clone),
            ("bootstrap_venv", self.leg_bootstrap_venv),
            ("bootstrap_tex", self.leg_bootstrap_tex),
            ("wake", self.leg_wake),
            ("detect", self.leg_detect),
            ("serve_smoke", self.leg_serve_smoke),
            ("suite", self.leg_suite),
        ]
        aborted = False
        for name, fn in legs:
            if aborted:
                self.skip(name, "a prerequisite leg failed")
                continue
            try:
                ok = fn()
            except Exception as e:  # noqa: BLE001
                ok = self.record(name, "(exception)", 126, 0, False, f"{type(e).__name__}: {e}")
            # clone / bootstrap_venv are hard prerequisites for everything after. A leg
            # that REFUSED (ok is None) is neither pass nor fail, so it never aborts —
            # the remaining legs still have something to say.
            if ok is False and name in ("clone", "bootstrap_venv"):
                aborted = True

        # THREE OUTCOMES, NOT TWO. A failed leg (the clone is broken) FAILs the proof;
        # a refused leg (this box lacks the instrument) makes the proof a REFUSAL, which
        # is neither the green it never earned nor the red it never measured.
        refused = [s for s in self.steps if s.get("refused")]
        failed = [s for s in self.steps if s["ok"] is False]
        if failed:
            overall, word = 2, "FAIL"
        elif refused:
            overall, word = REFUSAL_EXIT, "REFUSED"
        else:
            overall, word = 0, "PASS"
        report = {
            "source_repo": str(self.source_repo),
            "branch": self.branch,
            "workdir": str(self.workdir),
            "clone": str(self.clone),
            "venv_path_taken": self.venv_path_taken,
            "proof_steps": self.steps,
            "overall": word,
            "overall_exit": overall,
            "refused_legs": [s["step"] for s in refused],
        }
        report_path = self.workdir / "proof_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\ncontainer_proof: report -> {report_path}")
        if refused and not failed:
            print(refusal_line("CONTAINER PROOF",
                               f"{len(refused)} leg(s)' instrument"
                               f" ({', '.join(s['step'] for s in refused)})",
                               [s["note"] for s in refused]))
        print(f"container_proof: OVERALL {word} (exit {overall})")
        # clean the heavy clone on a green run unless asked to keep it (keep the report).
        if overall == 0 and not os.environ.get("CONTAINER_PROOF_KEEP"):
            try:
                shutil.rmtree(self.clone, ignore_errors=True)
                print(f"container_proof: cleaned clone {self.clone} (report retained)")
            except Exception:  # noqa: BLE001
                pass
        return overall


_SMOKE_DRIVER = r"""
import { createRequire } from 'module';
import { execSync } from 'child_process';
const require = createRequire(import.meta.url);
const PW_ROOT = execSync('npm root -g').toString().trim() + '/playwright';
const { chromium } = require(PW_ROOT);
const CHROME = execSync('ls /opt/pw-browsers/chromium-*/chrome-linux/chrome').toString().trim().split('\n')[0];
const PORT = process.argv[2], CORPUS = process.argv[3], NAMED = process.argv[4];
let passed = 0;
const ok = (c, m) => { if (!c) throw new Error('ASSERT FAILED: ' + m); passed++; console.log('  ok -', m); };
(async () => {
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
    const bad = [];
    pg.on('response', r => { if (r.status() >= 400 && !r.url().endsWith('/favicon.ico') && !r.url().includes('/shared/plan')) bad.push([r.status(), r.url()]); });
    pg.on('pageerror', e => bad.push(['PAGEERROR', String(e)]));
    const url = `http://127.0.0.1:${PORT}/review?corpus=${CORPUS}`;
    console.log('[smoke]', url);
    await pg.goto(url, { waitUntil: 'networkidle' });
    await pg.waitForSelector('.subq .qi', { timeout: 15000 });
    const qi = await pg.$$('.subq .qi');
    ok(qi.length >= 1, `escalation queue renders items (got ${qi.length})`);
    const artName = (await (await pg.$('#arttitle .atname'))?.innerText()) || '';
    ok(artName.includes(NAMED), `landing header names ${NAMED} (got ${JSON.stringify(artName)})`);
    ok(bad.length === 0, `no failed requests / page errors (${JSON.stringify(bad)})`);
    console.log(`ALL_GREEN ${passed} assertions`);
  } finally { await b.close(); }
})().then(() => process.exit(0)).catch(e => { console.error('FAILED:', e.message); process.exit(1); });
"""


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv:
        workdir = Path(argv[0]).resolve()
    else:
        scratch = os.environ.get("CLAUDE_SCRATCHPAD") or tempfile.gettempdir()
        workdir = Path(tempfile.mkdtemp(prefix="container_proof_", dir=scratch))
    workdir.mkdir(parents=True, exist_ok=True)
    return Proof(workdir).run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
