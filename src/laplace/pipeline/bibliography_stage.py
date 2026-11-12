"""The bibliography stage — the References made to RENDER, reproducibly.

The guard gap this closes (PV-20260717T005612Z): a body carrying 39 bracketed
citations with no ``References`` section is not a paper. The July-12 record noted
bib mismatches (cite keys the ``.bib`` did not define); nothing in the pipeline
paid them mechanically. This stage is that organ: it enumerates the ``\\cite``
keys, reads the ``.bib`` source, resolves what is mechanically resolvable
(every key defined in the ``.bib`` renders), ensures ``\\bibliography`` is wired
into the root ``.tex``, runs the bibtex+compile probe, and banks a
literature-class research intent for every DANGLING citation — a key the prose
cites that no ``.bib`` entry defines and that therefore needs a real source.

Design discipline (the asset_model idiom):

* **filesystem-first + plain.** :func:`enumerate_citations` and
  :func:`bib_keys` read the ``.tex`` / ``.bib`` off disk; resolution is set
  arithmetic. No compile is required to compute what is resolvable.
* **the paid mismatches are literature-class.** A dangling key does not get a
  faked entry — it becomes a :class:`ResearchIntent` of class ``literature``:
  directed external retrieval, entailment-checked admission, adjudicated. The
  arming doc's literature door.
* **the render is proved, not asserted.** :func:`compile_probe` runs
  ``latexmk -bibtex`` and reads the ``.bbl`` + ``.aux`` back: bibitems present,
  ``\\bibcite`` for every distinct key, zero ``undefined citation`` warnings. The
  probe returns evidence, not a boolean alone.
* **idempotent wiring.** :func:`ensure_wired` inserts ``\\bibliography`` only when
  absent; re-running mints the same ``.tex``.
* **pure at import.** No module-level filesystem or network work.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


@dataclass
class ResearchIntent:
    """A literature-class intent for a dangling citation — a key cited with no
    ``.bib`` source. The citation-direction organ's queue."""

    id: str
    cls: str
    key: str
    note: str
    status: str = "open"
    record: str = "research-intent"


@dataclass
class BibResult:
    """The stage's manifest: what was cited, what resolved, what dangles, and the
    compile-probe evidence."""

    cited: list[str]
    defined: list[str]
    resolved: list[str]
    dangling: list[str]
    wired: bool
    intents: list[dict]
    probe: dict


# --------------------------------------------------------------------------- #
# Enumeration
# --------------------------------------------------------------------------- #

_CITE_RE = re.compile(r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
_BIBKEY_RE = re.compile(r"^\s*@\s*[a-zA-Z]+\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
_BIB_CMD_RE = re.compile(r"\\bibliography\s*\{([^}]*)\}")
_ENDDOC_RE = re.compile(r"\\end\{document\}")

_SECTION_GLOBS = ("s*.tex", "appendix_*.tex", "abstract.tex", "main.tex")


def _section_files(manuscript_dir: Path) -> list[Path]:
    out: list[Path] = []
    for g in _SECTION_GLOBS:
        for p in sorted(manuscript_dir.glob(g)):
            if p not in out:
                out.append(p)
    return out


def enumerate_citations(manuscript_dir: str | Path) -> list[str]:
    """Every distinct ``\\cite`` key across the manuscript's ``.tex``, sorted."""
    mdir = Path(manuscript_dir)
    keys: set[str] = set()
    for f in _section_files(mdir):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _CITE_RE.finditer(text):
            for k in m.group(1).split(","):
                k = k.strip()
                if k:
                    keys.add(k)
    return sorted(keys)


def bib_keys(bibfile: str | Path) -> list[str]:
    """Every entry key defined in a ``.bib`` file, sorted. CONTROL entries and
    other non-key ``@`` lines are excluded (they carry no comma-key)."""
    path = Path(bibfile)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    keys = {m.group(1) for m in _BIBKEY_RE.finditer(text)}
    # drop apsrev control markers if any slipped the comma test
    keys = {k for k in keys if not k.upper().endswith("CONTROL")}
    return sorted(keys)


def resolve(cited: list[str], defined: list[str]) -> tuple[list[str], list[str]]:
    """Split cited keys into ``(resolved, dangling)`` against the defined set."""
    dset = set(defined)
    resolved = sorted(k for k in cited if k in dset)
    dangling = sorted(k for k in cited if k not in dset)
    return resolved, dangling


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def is_wired(main_tex: str | Path) -> str | None:
    """Return the bib basename the root ``.tex`` renders, or None if unwired."""
    try:
        text = Path(main_tex).read_text(encoding="utf-8")
    except OSError:
        return None
    m = _BIB_CMD_RE.search(text)
    return m.group(1) if m else None


def wired_text(text: str, bib_basename: str = "refs") -> str:
    """Pure bibliography setup plan shared by legacy and versioned source writers."""
    if _BIB_CMD_RE.search(text):return text
    match=_ENDDOC_RE.search(text);command=f"\n\\bibliography{{{bib_basename}}}\n\n"
    return text[:match.start()]+command+text[match.start():] if match else text.rstrip()+"\n"+command


def ensure_wired(main_tex: str | Path, bib_basename: str = "refs") -> bool:
    """Wire the canonical root under the same physical lease as ordinary edits.

    The bibliography probe/build remains outside this bounded commit.
    """
    from laplace.manuscript.manuscript_source import source_mutation
    path=Path(main_tex)
    with source_mutation([path]):
        text=path.read_text(encoding='utf-8');new=wired_text(text,bib_basename)
        if text==new:return False
        import os
        from laplace.manuscript.manuscript_source import stage_source
        # Preserve this writer's prior native-text newline translation.
        staged = stage_source(path, new.replace("\n", os.linesep).encode("utf-8"))
        try:
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)
        return True


# --------------------------------------------------------------------------- #
# The compile probe — proves the References RENDER
# --------------------------------------------------------------------------- #


def compile_probe(manuscript_dir: str | Path, main_stem: str = "main",
                  timeout: int = 300) -> dict:
    """Run ``latexmk -pdf -bibtex`` and read the result back.

    Returns evidence: ``latexmk_ok``, ``bibitems`` (count in the ``.bbl``),
    ``bibcites`` (count in the ``.aux``), ``undefined`` (undefined-citation
    warnings in the ``.log``), and ``renders`` — the stage's verdict, True when a
    ``.bbl`` with bibitems exists and no citation is undefined."""
    mdir = Path(manuscript_dir)
    ok = False
    log_tail = ""
    try:
        proc = subprocess.run(
            ["latexmk", "-pdf", "-bibtex", "-interaction=nonstopmode",
             "-halt-on-error", f"{main_stem}.tex"],
            cwd=str(mdir), capture_output=True, text=True, timeout=timeout,
            env={"TEXMFOUTPUT": ".", **_env()},
        )
        ok = proc.returncode == 0
        log_tail = (proc.stdout + proc.stderr)[-1500:]
    except (OSError, subprocess.TimeoutExpired) as e:  # pragma: no cover
        return {"latexmk_ok": False, "error": f"{type(e).__name__}: {e}",
                "renders": False}

    bbl = mdir / f"{main_stem}.bbl"
    aux = mdir / f"{main_stem}.aux"
    log_f = mdir / f"{main_stem}.log"
    bibitems = 0
    if bbl.exists():
        bibitems = len(re.findall(r"\\bibitem", bbl.read_text(encoding="utf-8")))
    bibcites = 0
    if aux.exists():
        bibcites = len(re.findall(r"\\bibcite", aux.read_text(encoding="utf-8")))
    undefined = 0
    if log_f.exists():
        undefined = len(re.findall(
            r"Citation .* undefined", log_f.read_text(encoding="utf-8")))
    renders = bool(bbl.exists() and bibitems > 0 and undefined == 0)
    return {"latexmk_ok": ok, "bibitems": bibitems, "bibcites": bibcites,
            "undefined": undefined, "renders": renders, "log_tail": log_tail}


def _env() -> dict:
    import os
    return dict(os.environ)


# --------------------------------------------------------------------------- #
# The orchestration — the stage's run() entrypoint
# --------------------------------------------------------------------------- #


def run(manuscript_dir: str | Path, bib_basename: str = "refs",
        main_stem: str = "main", apply: bool = False,
        probe: bool = True) -> BibResult:
    """Resolve citations, wire + probe the bibliography, bank literature-class
    intents for dangling keys.

    ``apply=False``: pure resolution, no tree mutation, no compile.
    ``apply=True``: ensure ``\\bibliography`` wired, run the compile probe, write
    the manifest + bank dangling-key intents under ``manuscript/``."""
    mdir = Path(manuscript_dir)
    cited = enumerate_citations(mdir)
    bibfile = mdir / f"{bib_basename}.bib"
    defined = bib_keys(bibfile)
    resolved, dangling = resolve(cited, defined)

    intents = [
        ResearchIntent(
            id=f"RI-LIT-{k}", cls="literature", key=k,
            note=(f"Citation key '{k}' is cited in the prose but no entry "
                  f"defines it in {bib_basename}.bib. Literature-class: needs a "
                  f"real external source (directed retrieval, entailment-checked "
                  f"admission, adjudicated) before it renders."),
        )
        for k in dangling
    ]

    wired = is_wired(mdir / f"{main_stem}.tex") is not None
    probe_res: dict = {"renders": None, "note": "not-run"}

    if apply:
        did = ensure_wired(mdir / f"{main_stem}.tex", bib_basename)
        wired = True if did else wired
        if probe:
            probe_res = compile_probe(mdir, main_stem=main_stem)

    result = BibResult(
        cited=cited, defined=defined, resolved=resolved, dangling=dangling,
        wired=wired, intents=[asdict(i) for i in intents], probe=probe_res,
    )

    if apply:
        (mdir / "bibliography_manifest.json").write_text(
            json.dumps(asdict(result), indent=1), encoding="utf-8")
        if intents:
            _bank_intents(mdir, intents)
    return result


def _bank_intents(mdir: Path, intents: list[ResearchIntent]) -> None:
    """Append literature-class intents to the shared research-intent ledger,
    deduped by id."""
    ledger = mdir / "research_intents.jsonl"
    existing = set()
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                existing.add(json.loads(line).get("id"))
            except json.JSONDecodeError:
                pass
    with ledger.open("a", encoding="utf-8") as fh:
        for it in intents:
            if it.id in existing:
                continue
            fh.write(json.dumps(asdict(it)) + "\n")


# --------------------------------------------------------------------------- #
# The lawful reader — the /pipeline bibliography card's telemetry (view=mechanism)
# --------------------------------------------------------------------------- #


def _empty_manifest(mdir: Path) -> dict:
    """The honest-empty read shape — every fact zeroed/empty, ``present`` False, no
    raise. The ``/pipeline`` bibliography card renders its absence string off this
    (``no manifest · run resolution (dry-run: no compile)``)."""
    return {
        "present": False,
        "manuscript": str(mdir),
        "cited_n": 0,
        "defined_n": 0,
        "resolved_n": 0,
        "dangling_n": 0,
        "wired": False,
        "intents_n": 0,
        "renders": None,
        "dangling_keys": [],
    }


def read_manifest(manuscript_dir: str | Path) -> dict:
    """The lawful READER — view=mechanism: the ``/pipeline`` bibliography card calls
    THIS, never re-parses the artifact. The conjugate of :func:`run` (``apply=True``): a
    PURE read (no subprocess, no compile, no network, no writes) of the banked
    ``<manuscript_dir>/bibliography_manifest.json``.

    Facts returned (present manifest):

    * ``cited_n`` / ``defined_n`` / ``resolved_n`` / ``dangling_n`` — the resolution
      arithmetic as counts (cited keys, ``.bib`` entries, resolved-against-``.bib``, and
      the DANGLING keys a source is missing for);
    * ``wired`` — whether the root ``.tex`` renders a ``\\bibliography``;
    * ``intents_n`` — the ``literature``-class intents banked for the dangling keys (the
      citation-direction organ's queue), counted off the manifest's own ``intents``;
    * ``renders`` — the compile-probe's verdict (proved, not asserted; ``None`` when the
      manifest was written without a probe);
    * ``dangling_keys`` — the dangling keys themselves, the directed-retrieval targets.

    ``present`` is ALWAYS carried. Absent artifact (or unreadable/malformed) →
    :func:`_empty_manifest` (``present`` False, every fact zeroed) — never a raise,
    never None."""
    mdir = Path(manuscript_dir)
    manifest_path = mdir / "bibliography_manifest.json"
    if not manifest_path.exists():
        return _empty_manifest(mdir)
    # ONE boom-guard over json.loads AND the whole field extraction (the
    # detector_organs.read_detector_organs exemplar): a valid-JSON-but-wrong-typed
    # manifest (e.g. ``cited`` an int, ``intents`` an int, ``probe`` a list) must
    # degrade to _empty_manifest, never raise a 500 on this GET path.
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        dangling = [str(k) for k in (data.get("dangling") or [])]
        intents = [
            i for i in (data.get("intents") or [])
            if str(i.get("cls") or i.get("research_class") or "") == "literature"
        ]
        probe = data.get("probe") or {}
        return {
            "present": True,
            "manuscript": str(mdir),
            "cited_n": len(data.get("cited") or []),
            "defined_n": len(data.get("defined") or []),
            "resolved_n": len(data.get("resolved") or []),
            "dangling_n": len(dangling),
            "wired": bool(data.get("wired")),
            "intents_n": len(intents),
            "renders": probe.get("renders"),
            "dangling_keys": dangling,
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return _empty_manifest(mdir)


if __name__ == "__main__":  # pragma: no cover
    import argparse
    ap = argparse.ArgumentParser(description="the bibliography stage")
    ap.add_argument("manuscript")
    ap.add_argument("--bib", default="refs")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    res = run(a.manuscript, bib_basename=a.bib, apply=a.apply)
    print(json.dumps(asdict(res), indent=1))
