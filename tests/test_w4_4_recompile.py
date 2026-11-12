"""W4.4 — the debounced background recompile (single-latexmk mutex per manuscript).

The stage's FAIL-CLOSED contract, one leg per claim (all hermetic — fake TeX
binaries via the LOCAL-TEX-PATH LAW env overrides, so the tests are deterministic
regardless of what toolchain the box carries):

1. NETWORK PURITY (the W1.2 law) — a GET /projection/recompile NEVER compiles: it
   is a pure status read. compile_tex is never reached; no pdf is minted.

2. ABSENT latexmk — honest refusal naming the env var (400, present:false,
   absent_binary:true, fix names LAPLACE_LATEXMK_BIN), and NO worker is spawned.

3. DOUBLE-POST COALESCES — the single-latexmk mutex: a fake SLOW latexmk lets a
   second POST land while the first runs; it returns running/coalesced and spawns
   nothing, so exactly ONE latexmk invocation happens for the manuscript.

4. A FAILING tex — the error is surfaced with its log tail through the .hy-stale
   idiom (state:error, ok:false, no pdf), and there is NO crash-loop: further
   status polls neither compile nor flip the state back to running.

5. SUCCESS — staleness flips fresh (present+fresh+not-degraded), the pdf mtime
   MOVES, and with a synctex binary resolvable the W4.2 follow re-enables.

Windows discipline: pathlib throughout; every TeX tool resolves per the law, so a
box without a real toolchain still runs these (the fakes are the toolchain here).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from laplace.manuscript import projection_viewer as pv
from laplace.manuscript import tex_dependencies

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# fixtures: an isolated repo root + state dir, and fake TeX binaries
# ---------------------------------------------------------------------------

def _fake_bin(path: Path, script: str) -> str:
    path.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


# a fake latexmk that RECORDS each call, (optionally) sleeps, then mints a fresh
# pdf + a synctex NEWER than it (so _synctex_fresh + compile_tex both judge success).
_FAKE_LATEXMK_OK = r"""
echo call >> "$LMK_COUNTER"
sleep "${LMK_SLEEP:-0}"
job=main
for a in "$@"; do case "$a" in *.tex) job=$(basename "$a" .tex);; esac; done
: > "$job.pdf"
sleep 0.05
: > "$job.synctex.gz"
exit 0
"""

# a fake TeX tool that RECORDS its call, prints a LaTeX error, mints NOTHING, fails.
_FAKE_FAIL = r"""
echo call >> "$LMK_COUNTER"
echo "! LaTeX Error: fake deliberate failure."
echo "l.42 \\badcommand"
exit 1
"""


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Fence the viewer to a tmp repo + tmp state dir, with a real main.tex."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr("laplace.web.scanner._repo_root", lambda: repo)
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    tex = repo / "main.tex"
    tex.write_text(
        "\\documentclass{article}\\begin{document}hello\\end{document}\n",
        encoding="utf-8")
    (repo/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'c','project_dir':'.','tex_root':'.',
        'manifest':{'document':{'root':'main.tex','manuscript_dir':'.'}}}]}))
    monkeypatch.setenv("LMK_COUNTER", str(tmp_path / "calls.log"))
    return {"repo": repo, "tex": tex, "counter": tmp_path / "calls.log",
            "bin": tmp_path}


def _calls(counter: Path) -> int:
    try:
        return len([l for l in counter.read_text().splitlines() if l.strip()])
    except OSError:
        return 0


def _post(file_rel: str, corpus: str = "c", by: str = "t"):
    body = json.dumps({"corpus": corpus, "by": by}).encode("utf-8")
    st, ctype, raw = pv.handle("/projection/recompile", {"file": [file_rel]},
                               "POST", body)
    return st, json.loads(raw)


def _get(file_rel: str):
    st, ctype, raw = pv.handle("/projection/recompile", {"file": [file_rel]},
                               "GET", b"")
    return st, json.loads(raw)


def _poll_until(file_rel: str, pred, timeout: float = 20.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        _, last = _get(file_rel)
        if pred(last):
            return last
        time.sleep(0.1)
    return last


# ---------------------------------------------------------------------------
# 1. NETWORK PURITY — a GET never compiles (the W1.2 law)
# ---------------------------------------------------------------------------

def test_get_recompile_is_a_pure_read_never_compiles(env, monkeypatch):
    spy = {"n": 0}
    monkeypatch.setattr(pv, "compile_tex",
                        lambda *a, **k: spy.__setitem__("n", spy["n"] + 1))
    st, row = _get("main.tex")
    assert st == 200
    assert spy["n"] == 0, "a GET reached compile_tex — GET must be pure (W1.2)"
    # a pure status read shape: the .hy-stale row, honestly 'no pdf yet'
    for k in ("id", "label", "present", "fresh", "degraded", "state", "running",
              "reason", "fix", "producer"):
        assert k in row, k
    assert row["running"] is False and row["present"] is False
    assert not (env["repo"] / "main.pdf").exists()


# ---------------------------------------------------------------------------
# 2. ABSENT latexmk — honest refusal, no worker
# ---------------------------------------------------------------------------

def test_absent_latexmk_refuses_honestly_and_spawns_nothing(env, monkeypatch):
    monkeypatch.setattr(pv, "_latexmk_bin", lambda: None)
    spy = {"n": 0}
    monkeypatch.setattr(pv, "compile_tex",
                        lambda *a, **k: spy.__setitem__("n", spy["n"] + 1))
    st, row = _post("main.tex")
    assert st == 400
    assert row["present"] is False and row["degraded"] is True
    assert row.get("absent_binary") is True
    assert "LAPLACE_LATEXMK_BIN" in row["fix"]
    assert spy["n"] == 0, "a worker ran despite absent latexmk"
    # the status read is equally honest, still 200, never a 500
    st, srow = _get("main.tex")
    assert st == 200 and srow["absent_binary"] is True
    assert "LAPLACE_LATEXMK_BIN" in srow["fix"]


# ---------------------------------------------------------------------------
# 3. DOUBLE-POST COALESCES — exactly one latexmk (the mutex, a fake slow binary)
# ---------------------------------------------------------------------------

def test_double_post_coalesces_to_one_latexmk(env, monkeypatch):
    fake = _fake_bin(env["bin"] / "latexmk-slow", _FAKE_LATEXMK_OK)
    monkeypatch.setenv("LAPLACE_LATEXMK_BIN", fake)
    monkeypatch.setenv("LMK_SLEEP", "1.5")            # slow enough to overlap the 2nd POST

    st1, r1 = _post("main.tex")
    assert st1 == 200 and r1["status"] == "started" and r1["coalesced"] is False
    st2, r2 = _post("main.tex")                        # lands while the first still runs
    assert st2 == 200 and r2["status"] == "running" and r2["coalesced"] is True

    done = _poll_until("main.tex", lambda s: s["state"] == "done")
    assert done is not None and done["state"] == "done" and done["ok"] is True
    assert _calls(env["counter"]) == 1, (
        f"latexmk ran {_calls(env['counter'])}× — the mutex did not coalesce")
    assert (env["repo"] / "main.pdf").is_file()


# ---------------------------------------------------------------------------
# 4. A FAILING tex — log tail surfaced, no crash-loop
# ---------------------------------------------------------------------------

def test_failing_compile_surfaces_log_tail_no_crash_loop(env, monkeypatch):
    fail = _fake_bin(env["bin"] / "tex-fail", _FAKE_FAIL)
    # every tool in the chain fails hermetically (no real toolchain touched)
    monkeypatch.setenv("LAPLACE_LATEXMK_BIN", fail)
    monkeypatch.setenv("LAPLACE_PDFLATEX_BIN", fail)
    monkeypatch.setenv("LAPLACE_BIBTEX_BIN", fail)

    st, r = _post("main.tex")
    assert st == 200 and r["status"] == "started"
    err = _poll_until("main.tex", lambda s: s["state"] == "error")
    assert err is not None and err["state"] == "error"
    assert err["ok"] is False and err["running"] is False
    assert "fake deliberate failure" in (err["log_tail"] or "")
    assert err["degraded"] is True and err["fresh"] is False
    assert not (env["repo"] / "main.pdf").exists()

    # NO crash-loop: further polls neither compile again nor flip back to running.
    calls_after_fail = _calls(env["counter"])
    for _ in range(4):
        _, s = _get("main.tex")
        assert s["state"] == "error" and s["running"] is False
        time.sleep(0.1)
    assert _calls(env["counter"]) == calls_after_fail, "a status poll re-ran the toolchain"


# ---------------------------------------------------------------------------
# 5. SUCCESS — staleness flips fresh, pdf mtime moves, follow re-enables
# ---------------------------------------------------------------------------

def test_success_flips_fresh_moves_pdf_and_reenables_follow(env, monkeypatch):
    fake = _fake_bin(env["bin"] / "latexmk-ok", _FAKE_LATEXMK_OK)
    monkeypatch.setenv("LAPLACE_LATEXMK_BIN", fake)
    monkeypatch.setenv("LMK_SLEEP", "0")
    # a resolvable synctex binary so the W4.2 follow read can go fresh (never run)
    syn = _fake_bin(env["bin"] / "synctex-mine", "exit 0\n")
    monkeypatch.setenv("LAPLACE_SYNCTEX_BIN", syn)

    # a STALE pre-existing pdf, so we can prove the mtime MOVES on recompile
    stale = env["repo"] / "main.pdf"
    stale.write_bytes(b"old")
    old_mtime = time.time() - 500
    os.utime(stale, (old_mtime, old_mtime))

    # before: no fresh synctex → recompile_status is degraded (out of lockstep)
    _, pre = _get("main.tex")
    assert pre["fresh"] is False

    st, r = _post("main.tex")
    assert st == 200 and r["status"] == "started"
    done = _poll_until("main.tex", lambda s: s["state"] == "done")
    assert done is not None and done["ok"] is True

    post = pv.recompile_status("main.tex")
    assert post["present"] is True and post["fresh"] is True and post["degraded"] is False
    assert stale.stat().st_mtime > old_mtime + 1, "the pdf mtime did not move"

    # the W4.2 follow re-enables: binary resolves, pdf+synctex in lockstep, tex older
    follow = pv.follow_status("main.tex")
    assert follow["present"] is True and follow["fresh"] is True
    assert follow["degraded"] is False


# ---------------------------------------------------------------------------
# path fencing — a traversal file= is refused, never a 500
# ---------------------------------------------------------------------------

def test_recompile_refuses_paths_outside_the_repo(env):
    for bad in ["../outside.tex", "C:/Windows/win.ini"]:
        st, row = _post(bad)
        assert st in (403, 404), (bad, st)
        assert row["status"] == "refused"
        st, srow = _get(bad)
        assert st == 200 and srow["running"] is False   # status stays pure + honest


def test_dependency_snapshot_uses_fls_and_declarations_but_excludes_outputs(env, tmp_path):
    repo, tex = env["repo"], env["tex"]
    tex.write_text(
        "\\documentclass{article}\n\\usepackage{local}\n\\begin{document}\n"
        "\\includegraphics{figure}\\bibliography{refs}\\end{document}\n",
        encoding="utf-8")
    (repo / "refs.bib").write_text("@book{x,title={X}}\n", encoding="utf-8")
    (repo / "figure.png").write_bytes(b"figure")
    (repo / "local.sty").write_text("% local style\n", encoding="utf-8")
    (repo / "recorder-only.sty").write_text("% recorder style\n", encoding="utf-8")
    (repo / "unrelated.png").write_bytes(b"unused")
    (repo / "main.aux").write_text("generated", encoding="utf-8")
    (repo / "main.pdf").write_bytes(b"generated")
    (repo / "main.fls").write_text(
        "\n".join([f"INPUT {tex}", f"INPUT {repo / 'local.sty'}",
                    f"INPUT {repo / 'figure.png'}", f"INPUT {repo / 'recorder-only.sty'}",
                    f"INPUT {repo / 'main.aux'}", f"INPUT {repo / 'main.pdf'}",
                    f"OUTPUT {repo / 'main.pdf'}"]) + "\n", encoding="utf-8")

    got = tex_dependencies.snapshot(tex, repo)

    assert set(got) == {"main.tex", "refs.bib", "figure.png", "local.sty",
                        "recorder-only.sty"}
    assert all(got.values())


def test_recompile_receipt_stales_only_for_consumed_bib_or_figure(env, monkeypatch):
    repo, tex = env["repo"], env["tex"]
    tex.write_text(
        "\\documentclass{article}\\begin{document}hello"
        "\\includegraphics{figure}\\bibliography{refs}\\end{document}\n",
        encoding="utf-8")
    bib = repo / "refs.bib"; bib.write_text("@book{x,title={Old}}\n", encoding="utf-8")
    figure = repo / "figure.png"; figure.write_bytes(b"old figure")
    unused = repo / "unrelated.png"; unused.write_bytes(b"old unrelated")
    (repo / "main.fls").write_text(
        f"INPUT {tex}\nINPUT {bib}\nINPUT {figure}\nOUTPUT {repo / 'main.pdf'}\n",
        encoding="utf-8")
    fake = _fake_bin(env["bin"] / "latexmk-deps", _FAKE_LATEXMK_OK)
    monkeypatch.setenv("LAPLACE_LATEXMK_BIN", fake)

    assert _post("main.tex")[0] == 200
    done = _poll_until("main.tex", lambda row: row["state"] == "done")
    assert done["fresh"] is True
    unused.write_bytes(b"new unrelated")
    assert pv.recompile_status("main.tex")["fresh"] is True

    bib.write_text("@book{x,title={Changed}}\n", encoding="utf-8")
    bib_stale = pv.recompile_status("main.tex")
    assert bib_stale["fresh"] is False and bib_stale["dependency_changes"] == ["refs.bib"]
    assert "compiled inputs changed" in bib_stale["reason"]
    bib.write_text("@book{x,title={Old}}\n", encoding="utf-8")
    figure.write_bytes(b"new figure")
    figure_stale = pv.recompile_status("main.tex")
    assert figure_stale["fresh"] is False
    assert figure_stale["dependency_changes"] == ["figure.png"]


def test_recompile_refuses_success_if_consumed_input_changes_during_build(env, monkeypatch):
    repo, tex = env["repo"], env["tex"]
    tex.write_text("\\documentclass{article}\\begin{document}Actual fixture words.\\bibliography{refs}\\end{document}\n")
    bib = repo / "refs.bib"; bib.write_text("@book{x,title={Before}}\n")
    monkeypatch.setenv("LAPLACE_LATEXMK_BIN", _fake_bin(env["bin"] / "latexmk-guard", "exit 0\n"))

    def changing_compile(_file, **_kwargs):
        (repo / "main.pdf").write_bytes(b"pdf")
        (repo / "main.synctex.gz").write_bytes(b"synctex")
        bib.write_text("@book{x,title={During}}\n")
        return {"ok": True, "log_tail": "compiled", "pdf": "main.pdf"}

    monkeypatch.setattr(pv, "compile_tex", changing_compile)
    assert _post("main.tex")[0] == 200
    failed = _poll_until("main.tex", lambda row: row["state"] == "error")
    assert failed["ok"] is False
    assert "Consumed inputs changed during compile: refs.bib" in failed["log_tail"]
