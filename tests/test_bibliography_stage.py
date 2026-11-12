"""The bibliography stage — hermetic plumbing tests + a real compile probe.

builder != judge: the resolution / wiring / intent-typing tests are hermetic
set arithmetic and text mutation. The compile-probe test is the one that proves
the References RENDER — it drives a real ``latexmk -bibtex`` on a tiny
self-contained fixture and reads the ``.bbl`` back; it SKIPS when latexmk is
absent so the suite stays portable, but where a toolchain exists it is the
acceptance test the arming demands (bib renders: yes/no, proved not asserted).
"""
import json
import shutil
from pathlib import Path

import pytest

from laplace.pipeline import bibliography_stage as bs


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_S1 = r"""% s1
Foundational work~\cite{alpha} and the follow-up~\citep{beta} set the frame.
A third strand~\cite{gamma} is cited but has no source yet.
"""

_S2 = r"""% s2
We combine \cite{alpha,beta} in the synthesis.
"""

_BIB = """\
@article{alpha,
  title = {The Alpha Result},
  author = {Ada Lovelace},
  journal = {J. Testing},
  year = {2020},
}

@article{beta,
  title = {The Beta Result},
  author = {Alan Turing},
  journal = {J. Testing},
  year = {2021},
}
"""


def _manuscript(tmp_path: Path, wired: bool = False) -> Path:
    m = tmp_path / "manuscript"
    m.mkdir()
    (m / "s1.tex").write_text(_S1, encoding="utf-8")
    (m / "s2.tex").write_text(_S2, encoding="utf-8")
    (m / "refs.bib").write_text(_BIB, encoding="utf-8")
    bib_line = "\\bibliography{refs}\n" if wired else ""
    (m / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\usepackage{cite}\n"
        "\\begin{document}\n"
        "\\input{s1}\n\\input{s2}\n"
        f"{bib_line}"
        "\\end{document}\n",
        encoding="utf-8")
    return m


# --------------------------------------------------------------------------- #
# Enumeration + resolution
# --------------------------------------------------------------------------- #


def test_enumerate_citations_distinct_and_sorted(tmp_path):
    m = _manuscript(tmp_path)
    assert bs.enumerate_citations(m) == ["alpha", "beta", "gamma"]


def test_bib_keys_reads_defined(tmp_path):
    m = _manuscript(tmp_path)
    assert bs.bib_keys(m / "refs.bib") == ["alpha", "beta"]


def test_resolve_splits_resolved_and_dangling(tmp_path):
    m = _manuscript(tmp_path)
    cited = bs.enumerate_citations(m)
    defined = bs.bib_keys(m / "refs.bib")
    resolved, dangling = bs.resolve(cited, defined)
    assert resolved == ["alpha", "beta"]
    assert dangling == ["gamma"]


# --------------------------------------------------------------------------- #
# Dangling -> literature-class intent (never a faked entry)
# --------------------------------------------------------------------------- #


def test_run_dry_types_dangling_as_literature_intent(tmp_path):
    m = _manuscript(tmp_path)
    res = bs.run(m, bib_basename="refs", apply=False)
    assert res.dangling == ["gamma"]
    assert len(res.intents) == 1
    it = res.intents[0]
    assert it["cls"] == "literature"
    assert it["key"] == "gamma"
    assert it["id"] == "RI-LIT-gamma"
    # resolved keys must NOT mint intents
    assert not any(i["key"] in ("alpha", "beta") for i in res.intents)


def test_run_dry_does_not_mutate_or_compile(tmp_path):
    m = _manuscript(tmp_path, wired=False)
    before = (m / "main.tex").read_text(encoding="utf-8")
    res = bs.run(m, bib_basename="refs", apply=False)
    assert (m / "main.tex").read_text(encoding="utf-8") == before
    assert res.probe.get("renders") is None
    assert not (m / "bibliography_manifest.json").exists()


# --------------------------------------------------------------------------- #
# Wiring — idempotent \bibliography insertion
# --------------------------------------------------------------------------- #


def test_ensure_wired_inserts_once(tmp_path):
    m = _manuscript(tmp_path, wired=False)
    assert bs.is_wired(m / "main.tex") is None
    did = bs.ensure_wired(m / "main.tex", "refs")
    assert did is True
    assert bs.is_wired(m / "main.tex") == "refs"
    # second call is a no-op
    again = bs.ensure_wired(m / "main.tex", "refs")
    assert again is False
    text = (m / "main.tex").read_text(encoding="utf-8")
    assert text.count("\\bibliography{refs}") == 1
    # inserted BEFORE \end{document}
    assert text.index("\\bibliography{refs}") < text.index("\\end{document}")


def test_already_wired_manuscript_detected(tmp_path):
    m = _manuscript(tmp_path, wired=True)
    assert bs.is_wired(m / "main.tex") == "refs"


# --------------------------------------------------------------------------- #
# Intent banking — deduped, shared ledger with the figures organ
# --------------------------------------------------------------------------- #


def test_bank_intents_dedups_by_id(tmp_path):
    m = tmp_path / "man"
    m.mkdir()
    it = bs.ResearchIntent(id="RI-LIT-gamma", cls="literature",
                           key="gamma", note="n")
    bs._bank_intents(m, [it])
    bs._bank_intents(m, [it])
    lines = [ln for ln in (m / "research_intents.jsonl").read_text(
        encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1


# --------------------------------------------------------------------------- #
# THE ACCEPTANCE TEST — the References actually RENDER (real toolchain)
# --------------------------------------------------------------------------- #

_HAS_LATEX = bool(shutil.which("latexmk") and shutil.which("bibtex"))


# --------------------------------------------------------------------------- #
# The lawful reader — the /pipeline card's telemetry (view=mechanism, pure read)
# --------------------------------------------------------------------------- #


def test_read_manifest_honest_facts_from_banked_tree(tmp_path):
    # run() with apply=True + probe=False banks a real manifest (wires the .tex,
    # writes bibliography_manifest.json) without a compile — the reader reads it back.
    m = _manuscript(tmp_path, wired=False)
    res = bs.run(m, bib_basename="refs", apply=True, probe=False)
    assert res.dangling == ["gamma"]  # the fixture's one dangling key

    facts = bs.read_manifest(m)
    assert facts["present"] is True
    assert facts["manuscript"] == str(m)
    assert facts["cited_n"] == 3          # alpha, beta, gamma
    assert facts["defined_n"] == 2        # alpha, beta
    assert facts["resolved_n"] == 2       # alpha, beta
    assert facts["dangling_n"] == 1       # gamma
    assert facts["dangling_keys"] == ["gamma"]
    assert facts["wired"] is True         # run(apply=True) wired the root .tex
    assert facts["intents_n"] == 1        # one literature-class intent for gamma
    assert facts["renders"] is None       # probe=False → not proved, honestly None


def test_read_manifest_surfaces_probe_and_literature_filter(tmp_path):
    # a directly-written artifact (the falqon shape): 11 resolved, 0 dangling, the
    # References proved to render; a stray non-literature intent must NOT be counted.
    m = tmp_path / "manuscript"
    m.mkdir()
    keys = [f"k{i}" for i in range(11)]
    manifest = {
        "cited": keys, "defined": keys, "resolved": keys, "dangling": [],
        "wired": True,
        "intents": [{"id": "RI-OTHER-x", "cls": "computation", "key": "x"}],
        "probe": {"renders": True, "bibitems": 13, "undefined": 0},
    }
    (m / "bibliography_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")

    facts = bs.read_manifest(m)
    assert facts["present"] is True
    assert facts["cited_n"] == 11
    assert facts["resolved_n"] == 11
    assert facts["dangling_n"] == 0
    assert facts["dangling_keys"] == []
    assert facts["renders"] is True
    assert facts["intents_n"] == 0  # the computation-class intent is not literature


def test_read_manifest_honest_empty_when_absent(tmp_path):
    m = tmp_path / "manuscript"
    m.mkdir()
    # no bibliography_manifest.json banked → honest-empty, never a raise, never None
    facts = bs.read_manifest(m)
    assert facts is not None
    assert facts["present"] is False
    assert facts["manuscript"] == str(m)
    assert facts["cited_n"] == 0
    assert facts["defined_n"] == 0
    assert facts["resolved_n"] == 0
    assert facts["dangling_n"] == 0
    assert facts["intents_n"] == 0
    assert facts["wired"] is False
    assert facts["renders"] is None
    assert facts["dangling_keys"] == []


def test_read_manifest_honest_empty_on_malformed_json(tmp_path):
    m = tmp_path / "manuscript"
    m.mkdir()
    (m / "bibliography_manifest.json").write_text("{not json", encoding="utf-8")
    facts = bs.read_manifest(m)  # must not raise on a corrupt artifact
    assert facts["present"] is False
    assert facts["cited_n"] == 0


def test_read_manifest_read_path_is_pure(tmp_path, monkeypatch):
    # BINDING LAW: pure reads on GET — the card's reader touches no
    # subprocess / compile / network / writes.
    m = _manuscript(tmp_path, wired=False)
    bs.run(m, bib_basename="refs", apply=True, probe=False)  # bank a manifest first

    def _boom(*a, **k):  # any spawn/compile on the read path is a purity breach
        raise AssertionError("read_manifest must not spawn a subprocess / compile")

    monkeypatch.setattr(bs.subprocess, "run", _boom)
    monkeypatch.setattr(bs, "compile_probe", _boom)

    before = sorted(p.name for p in m.iterdir())
    facts = bs.read_manifest(m)
    assert facts["present"] is True
    after = sorted(p.name for p in m.iterdir())
    assert before == after  # zero writes on the read path

    # code-level (not a docstring grep): the names the compiled read path actually
    # references — the forbidden compile / network / write verbs appear in none.
    names = (set(bs.read_manifest.__code__.co_names)
             | set(bs._empty_manifest.__code__.co_names))
    for banned in ("subprocess", "compile_probe", "ensure_wired", "run",
                   "urllib", "requests", "socket", "write_text", "Popen", "system"):
        assert banned not in names, f"read path references a forbidden verb: {banned}"


@pytest.mark.skipif(not _HAS_LATEX, reason="latexmk/bibtex not installed")
def test_compile_probe_renders_resolved_bibliography(tmp_path):
    # only the two defined keys are cited here, so a clean render must produce a
    # .bbl with two bibitems and zero undefined-citation warnings.
    m = tmp_path / "manuscript"
    m.mkdir()
    (m / "s1.tex").write_text(
        r"Work~\cite{alpha} and~\cite{beta}.", encoding="utf-8")
    (m / "refs.bib").write_text(_BIB, encoding="utf-8")
    (m / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n\\input{s1}\n"
        "\\bibliographystyle{plain}\n\\bibliography{refs}\n"
        "\\end{document}\n",
        encoding="utf-8")
    res = bs.run(m, bib_basename="refs", apply=True, probe=True)
    assert res.wired is True
    assert res.probe["renders"] is True, res.probe
    assert res.probe["bibitems"] == 2
    assert res.probe["undefined"] == 0
    assert (m / "bibliography_manifest.json").exists()


def test_root_wiring_uses_shared_source_lease_and_probe_runs_after_release(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from laplace.manuscript import manuscript_source
    m = _manuscript(tmp_path)
    main = m / 'main.tex'; before = main.read_bytes()
    lease = manuscript_source.source_mutation
    monkeypatch.setattr(manuscript_source, 'source_mutation', lambda paths, **kw: lease(paths, timeout=0))
    with lease([main]):
        with ThreadPoolExecutor(max_workers=1) as pool:
            refused = pool.submit(bs.ensure_wired, main)
            with pytest.raises(manuscript_source.SourceLeaseTimeout): refused.result()
        assert main.read_bytes() == before
    def probe(*a, **kw):
        assert not manuscript_source.source_mutation_active()
        return {'renders': True}
    monkeypatch.setattr(bs, 'compile_probe', probe)
    assert bs.run(m, apply=True).wired
    assert '\\bibliography{refs}' in main.read_text()
