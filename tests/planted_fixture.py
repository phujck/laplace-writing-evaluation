"""Test-support for the planted-failure calibration fixture.

Disposable manuscript builders plus the two committed convergence-loop workflow
scripts driven as the real surfaces. Nothing here touches a canonical tree: every
fixture lives in the test's ``tmp_path``, and the two workflow scripts
(``.claude/workflows/fixedpoint_{mechround,route}.py``) are executed IN-PROCESS
via ``runpy`` with ``registry.resolve`` monkeypatched to a THROWAWAY project — the
registration idiom the calibration brief offers. The scripts read ``sys.argv`` and
print ``MECH_JSON:``/``ROUTE_JSON:`` exactly as the JS control-flow invokes them,
so the real panel-assembly / routing code runs against a tmp manuscript without
registering anything globally (a subprocess could not see a monkeypatch; runpy in
the parent process can).
"""
from __future__ import annotations

import io
import json
import runpy
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

from laplace.pipeline import registry

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".claude" / "workflows"

#: the throwaway project name every driver registers under.
THROWAWAY = "fixture_throwaway"


# ---------------------------------------------------------------------------
# throwaway project + the resolve monkeypatch (the offered registration idiom)
# ---------------------------------------------------------------------------

def make_project(*, target_dir="", manuscript_dir="", plan_path="",
                 feedback_ledger="", tex_root="", name=THROWAWAY):
    """A THROWAWAY ``registry.Project``. Absolute paths override the repo-root
    join (``Project.path``), so ``target_dir``/``plan_path`` can point straight at
    the tmp fixture. An empty ``tex_root`` makes ``propagate._net`` an empty net
    (no substrate), which is all the routing tests need."""
    return registry.Project(
        name=name, kind="conceptric",
        target_dir=str(target_dir), manuscript_dir=str(manuscript_dir),
        plan_path=str(plan_path), feedback_ledger=str(feedback_ledger),
        tex_root=str(tex_root))


def install_resolve(monkeypatch, proj):
    """Point ``registry.resolve`` at the throwaway (undone per test), and neutralise
    the voice-profile shingle scan in ``check_meta_leak`` so the meta-leak scan is
    hermetic — it never reads a repo voice profile whose wording could otherwise
    policy-echo into a clean fixture."""
    monkeypatch.setattr(registry, "resolve",
                        lambda name: proj if name == proj.name else None)
    import laplace.pipeline.dispatch as _dispatch
    monkeypatch.setattr(_dispatch, "VOICE_PROFILE_PATH", "", raising=False)


# ---------------------------------------------------------------------------
# disposable manuscript sources (one instance of each mechanical fault planted)
# ---------------------------------------------------------------------------

_DIRTY_MAIN = (
    "\\documentclass{article}\n\\begin{document}\n"
    "\\input{N1}\n\\input{N2}\n\\end{document}\n")

# N1 plants: evidence-ledger prose (class 6), a raw node-id in prose (class 7),
# a numbered equation never \ref'd (class 3, semantic-prefix label res:).
_DIRTY_N1 = r"""\section{Method}\label{sec:method}
Every statement here is typed by evidence class before it is written.
The bound def:main-bound then governs the estimate for the reader.
\begin{equation}\label{res:orphan-eq}
E = m c^2 .
\end{equation}
The relation states the mass energy equivalence in plain words for the reader here.
"""

# N2 plants: an undefined citation (class 2), a stale cross-reference (class 4),
# a single-token overfull hbox far past the 6pt floor (class 1), a caption whose
# second sentence is Q3 claim-support spec-debris (class 5).
_DIRTY_N2 = (
    "\\section{Results}\n"
    "We lean on prior work \\cite{ghost-key} and point back to \\ref{sec:ghost-target}.\n\n"
    "\\noindent " + ("X" * 128) + " here.\n\n"
    "\\begin{figure}\n"
    "\\caption{Measured spectral gap versus lattice size. "
    "This figure supports the claim that the bound is tight.}\n"
    "\\end{figure}\n")

_CLEAN_MAIN = (
    "\\documentclass{article}\n\\begin{document}\n"
    "\\input{C1}\n\\input{C2}\n\\end{document}\n")

# the negative control: the SAME structure with NONE of the plants — plain prose,
# a referenced equation (no orphan), a resolvable cross-reference, a clean caption.
_CLEAN_C1 = r"""\section{Method}\label{sec:method}
The apparatus is measured against a fixed reference lattice throughout.
\begin{equation}\label{res:gap}
E = m c^2 .
\end{equation}
The gap in \ref{res:gap} scales with the reference size, as the table records.
"""

_CLEAN_C2 = r"""\section{Results}
The estimate established in Sec.~\ref{sec:method} holds across the sampled sizes.

\begin{figure}
\caption{Measured spectral gap versus lattice size.}
\end{figure}
"""


def write_dirty(md):
    """Write the planted (dirty) manuscript; return its ``main.tex`` path."""
    md = Path(md)
    md.mkdir(parents=True, exist_ok=True)
    (md / "main.tex").write_text(_DIRTY_MAIN, encoding="utf-8")
    (md / "N1.tex").write_text(_DIRTY_N1, encoding="utf-8")
    (md / "N2.tex").write_text(_DIRTY_N2, encoding="utf-8")
    return md / "main.tex"


def write_clean(md):
    """Write the plant-free (clean) manuscript; return its ``main.tex`` path."""
    md = Path(md)
    md.mkdir(parents=True, exist_ok=True)
    (md / "main.tex").write_text(_CLEAN_MAIN, encoding="utf-8")
    (md / "C1.tex").write_text(_CLEAN_C1, encoding="utf-8")
    (md / "C2.tex").write_text(_CLEAN_C2, encoding="utf-8")
    return md / "main.tex"


def compile_latexmk(md, main="main.tex", timeout=240):
    """Compile ``main`` in ``md`` with latexmk; return ``{log, pdf, returncode}``.
    ``-interaction=nonstopmode`` so a planted fault (undefined cite/ref) does not
    halt the build — the .log still records it, which is what the loop reads."""
    md = Path(md)
    proc = subprocess.run(
        ["latexmk", "-pdf", "-interaction=nonstopmode", main],
        cwd=str(md), capture_output=True, text=True, timeout=timeout)
    stem = Path(main).stem
    return {"log": md / f"{stem}.log", "pdf": md / f"{stem}.pdf",
            "returncode": proc.returncode}


# ---------------------------------------------------------------------------
# plan + feedback-ledger records (the shapes the mech panel pours / the fixer reads)
# ---------------------------------------------------------------------------

def write_plan(path, section_ids, project=THROWAWAY):
    """A minimal projection plan: ``meta.project`` + one section per id."""
    plan = {"meta": {"project": project},
            "sections": [{"id": sid, "title": sid, "nodes_in_order": []}
                         for sid in section_ids]}
    Path(path).write_text(json.dumps(plan), encoding="utf-8")
    return plan


def finding(kind, *, scope="section", section="", node_id="", where="",
            text="planted fault", fid="FB-1", project=THROWAWAY):
    """One OPEN feedback finding, shaped as the mech panel pours it (the fields
    ``fixedpoint_route`` and ``propagate.intake_items`` read)."""
    return {"id": fid, "record": "finding", "project": project,
            "ts": "2026-07-09T00:00:00", "scope": scope, "kind": kind,
            "section": section, "node_id": node_id, "text": text,
            "source": "planted",
            "anchor": {"section": section or where, "text": "",
                       "where": where or section or node_id},
            "status": "open"}


def write_feedback(path, records):
    """Append feedback records to a jsonl ledger via the shared ledger writer."""
    from laplace.pipeline.ledger import append_jsonl
    p = Path(path)
    for rec in records:
        append_jsonl(p, rec)
    return p


# ---------------------------------------------------------------------------
# the two workflow-script drivers (runpy, in-process, real script code)
# ---------------------------------------------------------------------------

def _run_script(script, argv_tail, monkeypatch, proj):
    install_resolve(monkeypatch, proj)
    path = str(WORKFLOWS / script)
    saved_argv = sys.argv
    sys.argv = [path] + [str(a) for a in argv_tail]
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            try:
                runpy.run_path(path, run_name="__main__")
            except SystemExit:
                pass          # the scripts sys.exit(0) only on their error paths
    finally:
        sys.argv = saved_argv
    return buf.getvalue()


def _tagged(out, tag):
    for line in out.splitlines():
        if line.startswith(tag):
            return json.loads(line[len(tag):])
    raise AssertionError(f"no {tag!r} line in workflow output:\n{out}")


def run_route(main_tex, feedback_path, repo_root, monkeypatch, proj,
              corpus=THROWAWAY, round_no=1, dials_path="-"):
    """Drive ``fixedpoint_route.py`` and return its parsed ``ROUTE_JSON`` dict.
    ``dials_path`` (7th argv) selects a dials profile — ``"-"`` (default) means
    code defaults, so existing callers are byte-unchanged."""
    out = _run_script(
        "fixedpoint_route.py",
        [main_tex, proj.name, corpus, feedback_path, repo_root, round_no, dials_path],
        monkeypatch, proj)
    return _tagged(out, "ROUTE_JSON:")


def run_adjudicate(main_tex, feedback_path, repo_root, monkeypatch, proj,
                   corpus=THROWAWAY, round_no=1, dials_path="-"):
    """Drive ``fixedpoint_adjudicate.py`` (the B1 machine-adjudication organ) and
    return its parsed ``ADJUDICATE_JSON`` dict. Mirrors :func:`run_route`'s argv
    convention (main_tex, project, corpus, feedback, repo_root, round, dials)."""
    out = _run_script(
        "fixedpoint_adjudicate.py",
        [main_tex, proj.name, corpus, feedback_path, repo_root, round_no, dials_path],
        monkeypatch, proj)
    return _tagged(out, "ADJUDICATE_JSON:")


def run_harnessed(subcommand, argv_tail, monkeypatch, proj, *, stdin=None):
    """Drive ``.claude/workflows/harnessed_stage.py`` (the Leg A harnessed driver)
    in-process via runpy and return its parsed ``HARNESSED_JSON`` dict.

    The driver itself runs the built stage scripts (mechround/adjudicate/route) via
    runpy in the SAME process, so the ``registry.resolve`` monkeypatch installed here
    is inherited all the way down (a subprocess could not see it — hence in-process).
    ``stdin`` (a string) is fed to the driver for the ``pour`` subcommand."""
    install_resolve(monkeypatch, proj)
    path = str(WORKFLOWS / "harnessed_stage.py")
    saved_argv = sys.argv
    saved_stdin = sys.stdin
    sys.argv = [path, subcommand] + [str(a) for a in argv_tail]
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            try:
                runpy.run_path(path, run_name="__main__")
            except SystemExit:
                pass
    finally:
        sys.argv = saved_argv
        sys.stdin = saved_stdin
    return _tagged(buf.getvalue(), "HARNESSED_JSON:")


def run_mechround(main_tex, log_path, round_file, feedback_path, repo_root,
                  monkeypatch, proj, corpus=THROWAWAY, round_no=1,
                  inc_pdf="-", cand_pdf="-", dials_path="-"):
    """Drive ``fixedpoint_mechround.py`` (the every-round panel) and return
    ``(MECH_JSON summary, round_doc)`` — the compact summary line plus the full
    round file with the byte-exact panel."""
    out = _run_script(
        "fixedpoint_mechround.py",
        [main_tex, proj.name, corpus, log_path, inc_pdf, cand_pdf, round_no,
         round_file, feedback_path, dials_path],
        monkeypatch, proj)
    summary = _tagged(out, "MECH_JSON:")
    round_doc = json.loads(Path(round_file).read_text(encoding="utf-8"))
    return summary, round_doc
