"""Tests for the DETECTOR-ORGANS runner (detector_organs) — the durable growth-leg
caller that fires the four organs and banks the census. The reproducibility organ
the infrastructure law demands (replacing the vanished scratchpad runner)."""
from __future__ import annotations

import json
from pathlib import Path

from laplace.pipeline import detector_organs as DO
from laplace.pipeline import gap_ledger as GL

# the pure conjugate READER (top-level module, THE CONJUGATE WAVE Lane 0) — a
# thin loader distinct from the heavy runner above.
from laplace.engine import detector_organs as RDO


def _write_project(tmp_path, source_span):
    """A minimal project tree: a source draft carrying a load-bearing reasoning
    sentence, and a projection that DROPPED it (so source_delta fires)."""
    proj = tmp_path / "paper_demo"
    ms = proj / "manuscript"
    ms.mkdir(parents=True)
    (proj / "PAPER_DEMO_V1.md").write_text(
        "# Demo\n\n" + source_span + "\n\nA second unrelated source sentence.\n",
        encoding="utf-8")
    # projection: does NOT contain the reasoning sentence -> a source-delta loss
    (ms / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n"
        "The system evolves across layers under a fixed schedule.\n"
        "\\end{document}\n", encoding="utf-8")
    (ms / "projection_plan.json").write_text(
        json.dumps({"sections": [{"id": "s1"}, {"id": "s2"}]}), encoding="utf-8")
    return proj


def test_runner_fires_and_types_source_delta_mineable(tmp_path, monkeypatch):
    span = ("Because no measurement intervenes between layers, no re-preparation "
            "is required, so the coherent evolution advances without collapse.")
    _write_project(tmp_path, span)
    # meta_leak_scrub resolves the project via the registry; stub it to a clean pass
    # so the runner exercises the source-delta + gap-ledger path without the registry.
    from laplace.pipeline import meta_leak_scrub as MLS
    monkeypatch.setattr(MLS, "scrub_project",
                        lambda project, **kw: {"pass": True, "project": project,
                                               "core": {"pass": True, "n": 0},
                                               "source_tier": {"pass": True, "n": 0},
                                               "hits": [], "n": 0, "by_class": {}})
    ev = DO.run_detector_organs("paper_demo", root=str(tmp_path))
    # the source-delta organ found the dropped reasoning sentence
    assert ev["source_delta"]["n"] >= 1
    census = ev["gap_ledger"]["census"]
    # and it is NOT mistyped as a novel conjecture: the source-aware quarry recovered
    # it from the draft, so no source-delta gap re-typed to 'novel'.
    assert census["by_research_class"].get("novel", 0) == 0


def test_bank_writes_reproducible_file(tmp_path, monkeypatch):
    span = ("The reason the flag fires is that appreciable errors are reliably "
            "detected rather than silently accepted across the layer boundary.")
    _write_project(tmp_path, span)
    from laplace.pipeline import meta_leak_scrub as MLS
    monkeypatch.setattr(MLS, "scrub_project",
                        lambda project, **kw: {"pass": True, "project": project,
                                               "core": {"pass": True, "n": 0},
                                               "source_tier": {"pass": True, "n": 0},
                                               "hits": [], "n": 0, "by_class": {}})
    path, ev = DO.bank_detector_organs("paper_demo", root=str(tmp_path))
    assert path.is_file()
    banked = json.loads(path.read_text(encoding="utf-8"))
    assert banked["project"] == "paper_demo"
    assert banked["gap_ledger"]["census"] == ev["gap_ledger"]["census"]
    # rerunning re-mints the same gap-ledger census (deterministic typing)
    _, ev2 = DO.bank_detector_organs("paper_demo", root=str(tmp_path))
    assert ev2["gap_ledger"]["census"] == ev["gap_ledger"]["census"]


def test_missing_source_degrades_not_crashes(tmp_path):
    # no source draft present -> source-aware quarry over a missing file must not
    # crash the runner build; the resolver still yields a path, read errors degrade.
    proj = tmp_path / "paper_demo"
    (proj / "manuscript").mkdir(parents=True)
    (proj / "manuscript" / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\nx\n\\end{document}\n",
        encoding="utf-8")
    q = GL.source_aware_quarry_fn("paper_demo", proj / "PAPER_DEMO_V1.md")
    # a source-delta gap probed against a missing source -> 0.0 (source-recoverable),
    # never an exception.
    from laplace.pipeline.gap_ledger import Gap
    g = Gap(id="GAP-x", gap_class="ungrounded", where="source-vs-projection",
            section="", kind="source-motivation-lost", issue="i", quote="q")
    assert q(g) == 0.0


# --- the pure READER (read_detector_organs) — the /pipeline detectors card's
# view=mechanism reader; a thin loader that never re-fires the runner ----------

def _bank_census(rounds_dir, date, *, gaps=30, conceptric=8, research=0,
                 sd_n=30, meta_n=0, promise_counts=None, promise_n=0):
    """Bank a census file shaped exactly like the runner's output
    (run_detector_organs :103-133) under rounds/detector_organs_<date>.json."""
    rounds_dir.mkdir(parents=True, exist_ok=True)
    ev = {
        "generated": f"{date}T03:56:30",
        "by": "detector_organs.run_detector_organs (test fixture)",
        "read_only": True,
        "project": "paper_demo",
        "promise": {"pass": promise_n == 0, "present": {}, "counts": promise_counts or {},
                    "n": promise_n},
        "source_delta": {"pass": sd_n == 0, "present": {},
                         "counts": {"source-argument-lost": 16,
                                    "source-motivation-lost": 8,
                                    "source-connective-lost": 6},
                         "n": sd_n, "examples": []},
        "meta_leak_scrub": {"pass": meta_n == 0, "n": meta_n, "core": {},
                            "source_tier": {}, "by_class": {}, "examples": []},
        "gap_ledger": {
            "census": {"discovered": gaps, "capped": 8,
                       "by_gap_class": {"ungrounded": gaps}, "spine_critical": 0,
                       "substrate_absent": 0, "by_research_class": {},
                       "conceptric_intents": conceptric, "research_intents": research},
            "all_gaps_n": gaps, "capped_gaps": [], "conceptric_intents": [],
            "research_intents": []},
    }
    p = rounds_dir / f"detector_organs_{date}.json"
    p.write_text(json.dumps(ev, indent=2), encoding="utf-8")
    return p


def test_reader_returns_honest_facts_from_newest_round(tmp_path):
    """(a) the reader returns the banked per-detector facts, and picks the NEWEST
    round by the date in the filename (not the oldest, not lexical file order)."""
    rounds = tmp_path / "paper_demo" / "rounds"
    # an OLDER round with different numbers, then the newest — the reader must
    # read the newest and ignore the stale one.
    _bank_census(rounds, "2026-07-10", gaps=99, sd_n=99, conceptric=99)
    _bank_census(rounds, "2026-07-17", gaps=30, conceptric=8, research=0, sd_n=30,
                 meta_n=0, promise_counts={"promise-figure-absent": 2,
                                           "promise-citation-absent": 1}, promise_n=3)

    ev = RDO.read_detector_organs("paper_demo", root=str(tmp_path))
    assert ev["present"] is True
    assert ev["date"] == "2026-07-17"           # newest, not the 07-10 round
    assert ev["generated"] == "2026-07-17T03:56:30"
    # gap census
    assert ev["gaps"]["gaps"] == 30
    assert ev["gaps"]["conceptric_intents"] == 8
    assert ev["gaps"]["research_intents"] == 0
    assert ev["gaps"]["by_gap_class"] == {"ungrounded": 30}
    # source-delta findings by class
    assert ev["source_delta"]["n"] == 30
    assert ev["source_delta"]["by_class"]["source-argument-lost"] == 16
    # meta-leak violations
    assert ev["meta_leak"]["n"] == 0
    # promise absences by class — the two banked, the other three zeroed (stable keys)
    pbc = ev["promise"]["by_class"]
    assert ev["promise"]["n"] == 3
    assert pbc["promise-figure-absent"] == 2
    assert pbc["promise-citation-absent"] == 1
    assert pbc["promise-table-absent"] == 0
    assert set(RDO.PROMISE_CLASSES) <= set(pbc)   # every class key present


def test_reader_honest_empty_when_absent(tmp_path):
    """(b) no artifact -> present False, every fact zeroed, path None — no raise,
    no None. Covers both a missing project tree and an empty rounds dir."""
    # no project tree at all
    ev = RDO.read_detector_organs("paper_demo", root=str(tmp_path))
    assert ev["present"] is False
    assert ev["path"] is None
    assert ev["date"] == ""
    assert ev["gaps"]["gaps"] == 0
    assert ev["source_delta"]["n"] == 0
    assert ev["meta_leak"]["n"] == 0
    assert ev["promise"]["n"] == 0
    # stable key set even when empty
    assert set(RDO.PROMISE_CLASSES) <= set(ev["promise"]["by_class"])
    assert all(v == 0 for v in ev["promise"]["by_class"].values())

    # a rounds dir that exists but holds no matching census -> still honest-empty
    rounds = tmp_path / "paper_demo" / "rounds"
    rounds.mkdir(parents=True)
    (rounds / "unrelated.json").write_text("{}", encoding="utf-8")
    ev2 = RDO.read_detector_organs("paper_demo", root=str(tmp_path))
    assert ev2["present"] is False

    # a malformed newest census -> the boom-guard degrades to honest-empty, no raise
    (rounds / "detector_organs_2026-07-17.json").write_text(
        "{not valid json", encoding="utf-8")
    ev3 = RDO.read_detector_organs("paper_demo", root=str(tmp_path))
    assert ev3["present"] is False
    assert ev3["gaps"]["gaps"] == 0


def test_reader_read_path_is_pure(tmp_path, monkeypatch):
    """(c) the read path touches no subprocess / compile / network. Two clauses:
    an AST scan (the module IMPORTS none of the forbidden machinery — subprocess,
    socket, network libs — and never imports the heavy runner it would otherwise
    re-fire), and a runtime guard (subprocess/socket wired to explode; a real read
    still returns facts). AST, not a text grep, so the reader's own prose ("no
    subprocess, no compile, no network") cannot false-positive."""
    import ast

    src = Path(RDO.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden_mods = {"subprocess", "socket", "urllib", "requests", "http",
                      "ssl", "asyncio"}
    imported: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
            # the thin reader must never import the heavy pipeline runner
            assert not (node.module or "").startswith("laplace.pipeline"), (
                f"reader imports the runner: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)          # e.g. a bare compile(...) / exec(...)
    assert not (imported & forbidden_mods), (
        f"reader imports forbidden machinery: {imported & forbidden_mods}")
    assert "compile" not in called and "exec" not in called and "eval" not in called
    assert "run_detector_organs" not in src   # never re-fires the runner

    # runtime guard — arm subprocess + socket to raise, then read a real census;
    # a pure read never touches them, so it returns facts rather than exploding.
    import subprocess
    import socket

    def _boom(*a, **k):
        raise AssertionError("read path spawned a subprocess / socket")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(socket, "socket", _boom)

    _bank_census(tmp_path / "paper_demo" / "rounds", "2026-07-17")
    ev = RDO.read_detector_organs("paper_demo", root=str(tmp_path))
    assert ev["present"] is True and ev["gaps"]["gaps"] == 30
