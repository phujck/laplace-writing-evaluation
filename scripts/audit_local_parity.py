"""audit_local_parity.py - the pull-back parity gate (his ruling, 2026-07-14).

Remote sessions build in a Linux container; the author's box is Windows. On
2026-07-14 the local walk found four container leaks that had survived a "complete"
remote weld: a hardcoded /root/.local/bin/uv default, ``uv run`` rebuilding the host
project inside an "isolated" subprocess, every localstate.json check dying in
cmd.exe (so ALL staleness verdicts were false), and printed fix commands the author
could not paste. Each was found by hand. This gate makes the CLASS mechanical.

Run it on any box::

    python scripts/audit_local_parity.py

A remote seal runs it in-container; the local pull re-runs it here - THE VERDICT
THAT COUNTS IS THE LOCAL ONE. Every check calls the code's REAL resolver (view =
mechanism), never a lookalike. PSU-safe by construction: file reads, ``which``
lookups, and sub-second manifest checks - no compile, no embedding, no rebuild.

Last line is always greppable::

    parity: VERDICT=PASS failed=[]
    parity: VERDICT=FAIL failed=[tex-latexmk,manifest-checks]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # runnable with any python, venv or not

ROWS: list[tuple[str, str, str]] = []  # (name, PASS|FAIL|WARN, detail)


def row(name: str, ok: bool, detail: str, warn_only: bool = False) -> None:
    ROWS.append((name, "PASS" if ok else ("WARN" if warn_only else "FAIL"), detail))


# ---------------------------------------------------------------------------
# 1. git posture - the banned mechanisms stay OFF (his ruling: "turned right off")
# ---------------------------------------------------------------------------

def check_git_posture() -> None:
    def cfg(key: str) -> str:
        p = subprocess.run(["git", "config", key], cwd=REPO, capture_output=True, text=True)
        return (p.stdout or "").strip()

    sparse = cfg("core.sparseCheckout")
    row("git-sparse-checkout", sparse in ("", "false"),
        f"core.sparseCheckout={sparse or '(unset)'} - must never be true again")
    ntfs = cfg("core.protectNTFS")
    row("git-protectNTFS", ntfs == "",
        f"core.protectNTFS={ntfs or '(unset)'} - the workaround era is over; unset is the law")
    sc_file = REPO / ".git" / "info" / "sparse-checkout"
    row("git-sparse-file", not sc_file.exists(),
        f"{sc_file.relative_to(REPO)} {'EXISTS - delete it' if sc_file.exists() else 'absent'}")


# ---------------------------------------------------------------------------
# 2. venv layout + uv resolution (the real resolvers, imported)
# ---------------------------------------------------------------------------

def check_python_layout() -> None:
    venv_py = REPO / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    row("venv-python", venv_py.is_file(), f"expected at {venv_py.relative_to(REPO)}")

    try:
        from laplace.pipeline.readers.restart_reader import _resolve_uv
        uv = _resolve_uv()
        row("uv-resolve", uv is not None, f"restart_reader._resolve_uv() -> {uv or 'None (set LAPLACE_UV_BIN)'}")
    except Exception as exc:  # noqa: BLE001 - a gate reports, never crashes
        row("uv-resolve", False, f"import/resolve failed: {exc!r}")

    try:
        from laplace.pipeline.visual_gate import DEFAULT_UV
        ok = bool(DEFAULT_UV) and (shutil.which(DEFAULT_UV) is not None or Path(DEFAULT_UV).is_file())
        row("uv-default", ok, f"visual_gate.DEFAULT_UV={DEFAULT_UV!r} "
            f"{'resolves' if ok else 'does NOT resolve on this box (the /root leak class)'}")
    except Exception as exc:  # noqa: BLE001
        row("uv-default", False, f"import failed: {exc!r}")


# ---------------------------------------------------------------------------
# 3. the TeX law - env -> which -> honest absent, via the code's own resolvers
# ---------------------------------------------------------------------------

def check_tex_law() -> None:
    try:
        from laplace.manuscript import projection_viewer as pv
        latexmk = pv._latexmk_bin()
        synctex = pv._synctex_bin()
        row("tex-latexmk", latexmk is not None,
            f"-> {latexmk or 'ABSENT: set LAPLACE_LATEXMK_BIN or put latexmk on PATH'}")
        row("tex-synctex", synctex is not None,
            f"-> {synctex or 'ABSENT: set LAPLACE_SYNCTEX_BIN or put synctex on PATH'}")
    except Exception as exc:  # noqa: BLE001
        row("tex-latexmk", False, f"resolver import failed: {exc!r}")
    pdflatex = shutil.which("pdflatex")
    row("tex-pdflatex", pdflatex is not None, f"-> {pdflatex or 'ABSENT on PATH'}")


# ---------------------------------------------------------------------------
# 4. manifest checks actually RUN here (the cmd.exe false-staleness class)
# ---------------------------------------------------------------------------

_CMDEXE_NOISE = ("is not recognized", "not recognized as the name",
                 "CommandNotFoundException", "cannot find the path")


def check_manifest_runnable() -> None:
    manifest = REPO / "localstate.json"
    if not manifest.is_file():
        row("manifest-checks", False, "localstate.json missing at repo root")
        return
    try:
        from laplace.core.process import _sh_exe, run_manifest_cmd
    except Exception as exc:  # noqa: BLE001
        row("manifest-checks", False, f"laplace.core.process missing: {exc!r}")
        return
    if os.name == "nt" and _sh_exe() is None:
        row("manifest-checks", False,
            "no sh.exe found (Git Bash) - POSIX manifest checks cannot run on this box")
        return
    bad: list[str] = []
    for e in json.loads(manifest.read_text(encoding="utf-8")).get("entries", []):
        name, check = e.get("name", "?"), e.get("check")
        if not check:
            continue
        try:
            proc = run_manifest_cmd(check, REPO, timeout=120)
            out = (proc.stdout or "") + (proc.stderr or "")
            if any(n in out for n in _CMDEXE_NOISE):
                bad.append(f"{name} (cmd.exe noise: check never ran)")
            # rc 0 (fresh) and rc 1 (honest miss) are both healthy verdicts here -
            # this gate proves the checks RUN, ensure_state owns fresh-vs-stale.
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{name} ({exc.__class__.__name__})")
    row("manifest-checks", not bad,
        "all checks executed with POSIX semantics" if not bad else "; ".join(bad))


# ---------------------------------------------------------------------------
# 5. vendored assets travel (offline law: no CDN, no network, no container cache)
# ---------------------------------------------------------------------------

_VENDORED = [
    "src/laplace/web/static_shared/pdfjs/pdf.min.mjs",
    "src/laplace/web/static_shared/pdfjs/pdf.worker.min.mjs",
    "src/laplace/web/static_shared/vendor/codemirror/codemirror.bundle.mjs",
    "src/laplace/web/static_shared/katex/katex.min.js",
    "models/fastembed/fast-bge-small-en-v1.5.tar.gz",
]

# Our own shipped surface source the /pipeline board is BUILT from (not third-party
# vendor code) - a missing or untracked one paints a blank/broken board after a pull.
# Present + nonzero + TRACKED (stronger than _VENDORED, which asserts presence only).
_TRACKED_ASSETS = [
    "src/laplace/web/pipeline.html",
    "src/laplace/web/static_shared/pipeline-panes.mjs",
    "src/laplace/web/static_shared/run-tray.mjs",
    "src/laplace/web/evolution_surface.py",
    "src/laplace/pipeline/fitness_panel.py",
    # THE SELECTION FACE (2026-07-21): the selection desk's door, its sheet reader,
    # the heredity generation ledger it joins, and the versioned DRAFT rule the sheet
    # proposes against — a missing/untracked one blanks the selection card after a pull.
    "src/laplace/web/selection_surface.py",
    "src/laplace/pipeline/selection_sheet.py",
    "src/laplace/pipeline/generation_ledger.py",
    "profiles/selection/draft-psi-v1.yaml",
    # THE DERIVATION FACE (2026-07-21): the aspiration-first reach organ's reader and
    # its interaction doors — a missing/untracked one blanks the derivation card after
    # a pull (the per-project aspiration/ artifacts travel via check_caches_travel).
    "src/laplace/web/derivation_surface.py",
    "src/laplace/pipeline/derivation_organ.py",
]


def check_vendored() -> None:
    for rel in _VENDORED:
        p = REPO / rel
        row(f"vendored:{Path(rel).name}", p.is_file() and p.stat().st_size > 0, rel)
    for rel in _TRACKED_ASSETS:
        p = REPO / rel
        present = p.is_file() and p.stat().st_size > 0
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(p)],
                                 cwd=REPO, capture_output=True).returncode == 0
        row(f"tracked-asset:{Path(rel).name}", present and tracked,
            rel if present and tracked
            else f"{rel} - MISSING or empty" if not present
            else f"{rel} - UNTRACKED (will not travel to the next pull)")


# ---------------------------------------------------------------------------
# 6. container-literal sweep (WARN tier: hits need a reader's judgment - a
#    honoured-last fallback is lawful, a bare default is the leak)
# ---------------------------------------------------------------------------

_LITERALS = ("/root/", "/usr/bin/", "/usr/local/bin/")
# core.process owns the platform translation; this gate names the class it hunts.
_ALLOW = ("src/laplace/core/process.py", "scripts/audit_local_parity.py")


def check_container_literals() -> None:
    hits: list[str] = []
    for base in ("src", "scripts"):
        for p in (REPO / base).rglob("*.py"):
            if p.relative_to(REPO).as_posix() in _ALLOW:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if "/usr/bin/env" in line:  # shebangs and env-lookups are portable
                    continue
                if any(lit in line for lit in _LITERALS):
                    hits.append(f"{p.relative_to(REPO)}:{i}")
    row("container-literals", not hits,
        "no container-path literals outside core.process"
        if not hits else f"{len(hits)} hit(s) to judge (fallback-last is lawful): " + ", ".join(hits[:12]),
        warn_only=True)


# ---------------------------------------------------------------------------
# 7. caches TRAVEL (law 6, ARMING_2026-07-14 §2, his ruling: "make sure those
#    bloody caches are all committed - and the metric too"). Every derived
#    artifact a surface reads at boot must arrive by git pull, committed by
#    the remote session; .gitignore may not exclude it, and it may not sit
#    untracked. This is the mechanical check that class grows.
#
#    Paths come from two places, both resolved the REAL way (never a
#    lookalike): the four shared_ui.py read_* staleness helpers (:285-395)
#    name what a surface reads at boot (router cache, metric, voice store,
#    nodemap) - CACHE_FILE/METRIC_FILE are imported from embed_router; the
#    voice-store directory mirrors read_voice_store's own construction (it
#    exposes no path constant to import). localstate.json's nodemap-* entries
#    name the concrete per-project manuscripts (nodemap_fresh's own argument,
#    parsed out of the check command, not re-typed by hand) - the voice-store
#    entry's check already targets manifest.json directly.
# ---------------------------------------------------------------------------

def _caches_travel_paths() -> list[tuple[str, Path]]:
    """The concrete surface-read-at-boot paths, resolved the same way the real
    code resolves them. Returns (name, absolute path) pairs."""
    paths: list[tuple[str, Path]] = []
    try:
        from laplace.representation import embed_router as er
        paths.append(("router-cache", REPO / er.CACHE_FILE))
        paths.append(("metric-M", REPO / er.METRIC_FILE))
    except Exception as exc:  # noqa: BLE001 - a gate reports, never crashes
        row("caches-travel:router-cache/metric-M", False, f"embed_router import failed: {exc!r}")

    # read_voice_store checks passages.jsonl + embeddings.json
    # present under this directory; localstate.json's voice-store check additionally
    # gates freshness on exemplar_passages/manifest.json - all three travel together.
    voice_dir = REPO / "corpus_stores" / "voice_corpus_cache" / "exemplar_passages"
    paths.append(("voice-store:passages", voice_dir / "passages.jsonl"))
    paths.append(("voice-store:embeddings", voice_dir / "embeddings.json"))
    paths.append(("voice-store:manifest", voice_dir / "manifest.json"))

    manifest = REPO / "localstate.json"
    try:
        entries = json.loads(manifest.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, json.JSONDecodeError):
        entries = []
    for e in entries:
        name = e.get("name", "")
        if not name.startswith("nodemap-"):
            continue  # NOT scratch/bench state (rounds-*, metric-M etc handled above/elsewhere)
        m = re.search(r"nodemap_fresh\('([^']+)'\)", e.get("check", ""))
        if not m:
            continue
        main_tex = REPO / m.group(1)
        # the same convention review_surface.nodemap_state uses: md / (main.stem + ".nodemap.json")
        jp = main_tex.parent / (main_tex.stem + ".nodemap.json")
        paths.append((name, jp))

    # the evolution-desk / fitness-panel organ state the /pipeline cards read at board
    # paint (2026-07-21): the two engine-global banks named ROOT-scoped by their own
    # readers (author_proxy._ledger_path -> proxy_verdicts.jsonl at repo root, NOT
    # corpus_friction/; fitness_panel reads root/corpus_friction/suite_baseline.json),
    # plus the per-manuscript run artifacts (present-only, resolved below).
    paths.append(("proxy-verdicts", REPO / "proxy_verdicts.jsonl"))
    paths.append(("suite-baseline", REPO / "corpus_friction" / "suite_baseline.json"))
    paths.extend(_evolution_desk_paths())
    return paths


def _evolution_desk_paths() -> list[tuple[str, Path]]:
    """The per-manuscript evolution-desk / fitness-panel artifacts, resolved through
    the registry the same way read_ratify_queue / read_fitness resolve them (md =
    proj.manuscript_dir). PRESENT-ONLY: a project with no run yet legitimately has
    none, so absence is not a finding here - only a present artifact is gated (it
    must be tracked, not ignored). Files outside the repo (the website submodule)
    are skipped - this gate only rules on what a pull carries."""
    out: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    try:
        from laplace.pipeline import registry
    except Exception as exc:  # noqa: BLE001 - a gate reports, never crashes
        row("caches-travel:evolution-desk", False, f"registry import failed: {exc!r}")
        return out
    for name, proj in registry.all_projects().items():
        md = proj.path(proj.manuscript_dir, REPO) if proj.manuscript_dir else None
        if md is None:
            continue
        cands: list[tuple[str, Path]] = [
            (f"feedback:{name}", md / "feedback" / "feedback.jsonl"),            # evolution_consumer ratify queue
            (f"run-record:{name}", md / "reprojection" / "run_record.json"),     # fitness debt trajectory
            (f"freeze:{name}", md / "reprojection" / "freeze_verdict.json"),     # fitness freeze verdicts
            (f"generations:{name}", md / "generations.jsonl"),                    # THE SELECTION FACE — the heredity generation ledger the sheet rules
            # THE DERIVATION FACE — the aspiration boundary condition, the isnad chain,
            # and the appended re-scope history the card reads at board paint. Each
            # forged .tex fragment (served read-only by GET /derivation/fragment) and
            # each computation output must travel too, or an attested link reads as an
            # unforged gap after a pull.
            (f"aspiration:{name}", md / "aspiration" / "aspiration.json"),
            (f"aspiration-chain:{name}", md / "aspiration" / "chain.jsonl"),
            (f"aspiration-history:{name}", md / "aspiration" / "aspiration_history.jsonl"),
        ]
        adir = md / "aspiration" / "derivations"
        for p in sorted(adir.glob("*.tex")):
            cands.append((f"derivation-frag:{name}:{p.stem}", p))
        cdir = md / "aspiration" / "computed"
        for p in sorted(cdir.glob("*")):
            if p.is_file():
                cands.append((f"derivation-computed:{name}:{p.name}", p))
        # the DATED reprojection archives the selection sheet resolves per generation
        # row (a row's reprojection.run_record / freeze_verdict ref points at the dated
        # snapshot, not just the live file) — each must travel or the sheet reads a
        # generation's debt/freeze as absent after a pull.
        rdir = md / "reprojection"
        for p in sorted(rdir.glob("run_record_*.json")) + sorted(rdir.glob("freeze_verdict_*.json")):
            cands.append((f"reproj-archive:{name}:{p.stem}", p))
        hdir = md / "rounds" / "harnessed"
        for p in sorted(hdir.glob("detect_pre_*.json")) + sorted(hdir.glob("detect_post_*.json")):
            cands.append((f"harnessed:{name}:{p.stem.replace('detect_', '')}", p))
        # read_fitness reads the census from md.parent/rounds first, md/rounds as fallback
        census = sorted((md.parent / "rounds").glob("detector_organs_*.json")) or \
                 sorted((md / "rounds").glob("detector_organs_*.json"))
        for p in census:
            cands.append((f"census:{name}:{p.stem.replace('detector_organs_', '')}", p))
        for label, p in cands:
            if not p.exists():
                continue
            try:
                p.relative_to(REPO)
            except ValueError:
                continue  # outside the repo (e.g. the website submodule) - a pull can't carry it
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            out.append((label, p))
    return out


def _worktree_dirty(p: Path) -> bool:
    """git status --porcelain names a tracked file only when its worktree copy differs
    from the index/HEAD - the class a plain tracked check reads as PASS (the dirty
    copy stays local; a pull elsewhere gets the committed HEAD, not this edit)."""
    r = subprocess.run(["git", "status", "--porcelain", "--", str(p)],
                       cwd=REPO, capture_output=True, text=True)
    return bool((r.stdout or "").strip())


def check_caches_travel() -> None:
    for name, p in _caches_travel_paths():
        rel = p.relative_to(REPO)
        if not p.exists():
            row(f"caches-travel:{name}", False,
                f"{rel} absent (absent-but-lawful - a project that never built one; "
                f"staleness is ensure_state's business, not this gate's)", warn_only=True)
            continue
        ignored = subprocess.run(["git", "check-ignore", "-q", str(p)],
                                 cwd=REPO, capture_output=True).returncode == 0
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(p)],
                                 cwd=REPO, capture_output=True).returncode == 0
        if ignored:
            row(f"caches-travel:{name}", False,
                f"{rel} is git-ignored - law 6 forbids excluding a boot-read artifact")
        elif not tracked:
            row(f"caches-travel:{name}", False,
                f"{rel} exists but is UNTRACKED - it will not travel to the next pull")
        else:
            row(f"caches-travel:{name}", True, f"{rel} tracked, not ignored - travels")
            if _worktree_dirty(p):
                row(f"caches-travel:{name}:worktree", False,
                    f"{rel} tracked-but-dirty: a pull elsewhere gets the stale HEAD copy",
                    warn_only=True)


# ---------------------------------------------------------------------------
# 8. release artifacts TRAVEL (law 6's other half, found via test_c6): the minted
#    PDF a release record NAMES (release/finalize.json's pdf_path) is a shipped
#    object every surface may read - it must never be gitignored (a nested
#    wholesale *.pdf ate eigenengine-2026-07-14-r1.pdf: minted remote, never
#    committed, ABSENT in every fresh container) and must be tracked when present.
#    Project dirs come from laplace.pipeline.registry (read-only import), checking
#    both manuscript_dir and resolved_target_dir (the whitepaper case).
# ---------------------------------------------------------------------------

def _release_artifact_paths() -> list[tuple[str, Path]]:
    """(project, absolute pdf path) for every finalize.json-named artifact,
    resolved through the registry the same way review_surface reads the record
    (``md / rec['pdf_path']``). Deduped on the resolved path."""
    out: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    try:
        from laplace.pipeline import registry
    except Exception as exc:  # noqa: BLE001 - a gate reports, never crashes
        row("release-travel", False, f"registry import failed: {exc!r}")
        return out
    for name, proj in registry.all_projects().items():
        dirs = []
        if proj.manuscript_dir:
            dirs.append(proj.path(proj.manuscript_dir, REPO))
        dirs.append(proj.resolved_target_dir(REPO))
        for md in dirs:
            if md is None:
                continue
            fj = md / "release" / "finalize.json"
            if not fj.is_file():
                continue
            try:
                rec = json.loads(fj.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                row(f"release-travel:{name}", False,
                    f"{fj.relative_to(REPO)} unreadable: {exc}")
                continue
            pdf_rel = rec.get("pdf_path")
            if not pdf_rel:
                continue
            p = (md / pdf_rel).resolve()
            if p in seen:
                continue
            seen.add(p)
            out.append((name, p))
    return out


def check_release_artifacts_travel() -> None:
    for name, p in _release_artifact_paths():
        rel = p.relative_to(REPO)
        ignored = subprocess.run(["git", "check-ignore", "-q", str(p)],
                                 cwd=REPO, capture_output=True).returncode == 0
        if ignored:
            # even when absent: an ignored release artifact can never travel.
            row(f"release-travel:{name}", False,
                f"{rel} is git-ignored - a finalize-named release artifact can never travel")
            continue
        if not p.exists():
            row(f"release-travel:{name}", False,
                f"{rel} absent but named by finalize.json - recovery is a work order, "
                f"not a parity fix", warn_only=True)
            continue
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(p)],
                                 cwd=REPO, capture_output=True).returncode == 0
        if not tracked:
            row(f"release-travel:{name}", False,
                f"{rel} exists but is UNTRACKED - the minted object will not travel")
        else:
            row(f"release-travel:{name}", True, f"{rel} tracked, not ignored - travels")


# ---------------------------------------------------------------------------

def main() -> int:
    check_git_posture()
    check_python_layout()
    check_tex_law()
    check_manifest_runnable()
    check_vendored()
    check_container_literals()
    check_caches_travel()
    check_release_artifacts_travel()

    width = max(len(n) for n, _, _ in ROWS)
    for name, verdict, detail in ROWS:
        print(f"  {name:<{width}}  {verdict:<4}  {detail}")
    failed = [n for n, v, _ in ROWS if v == "FAIL"]
    print(f"parity: VERDICT={'FAIL' if failed else 'PASS'} failed=[{','.join(failed)}]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
