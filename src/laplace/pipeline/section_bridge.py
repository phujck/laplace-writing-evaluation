"""section_bridge.py — The section bridge (productized from ``scripts/demo_stage_stores.py``).

The proven UP operator ``corpus_ingest.build_corpus_network`` discovers sections through the
multi-file ``\\input{}`` layout — the shape the registered papers and the falqon pour ship in
(``corpus_ingest.atomise_paper`` walks ``main.tex``'s ``\\input`` reading order). The author's
PUBLISHED papers ship as SINGLE-FILE tex with INLINE ``\\section{}``; fed to the operator as-is
they atomise to a 2-node conceptric (``paper://`` + ``references`` only — no sections, no
equations, no figures). The Wave-4 demo bridged that gap with an ad-hoc splitter
(``demo_stage_stores.build_paper_net``); this module is that bridge, productized.

``bridged_network(tex_path, paper_id, workdir=None)`` splits a single-file paper's ``\\section``
blocks into the ``\\input{}`` layout the atomiser consumes — In an isolated workdir — builds the
full-fidelity conceptric through ``build_corpus_network``, and re-attaches per-section REAL prose
keyed by the net's OWN section ids (``section_prose`` / ``section_meta``), so a downstream view's
``embed_text`` is his real prose and its ``span_ref`` traces to conceptric node ids. This is the
exact behaviour ``build_paper_net`` proved; the demo now calls this function.

THE CONTRACT (the audit's readiness precondition — "the inline-``\\section`` → ``\\input{}`` bridge
productized"):

  * NEVER writes inside the source tree. The split lands in ``workdir`` (a fresh OS tempdir by
    default, removed before return since the built net is fully in-memory); the source tex and
    ``voice_corpus/`` are read only.
  * DETERMINISTIC node ids for the same input. Section files are named ``sec00``, ``sec01``, …
    in reading order, so ``build_corpus_network`` mints the same section/equation/figure ids on
    every run regardless of the tempdir path (ids derive from block ``\\label``s and the
    ``sec<NN>`` stems, never from the workdir).
  * PASS-THROUGH, don't force. A paper ALREADY in ``\\input{}`` layout (a ``main.tex`` whose
    ``\\input`` directives resolve to real sibling section files) is built directly from its
    source dir — zero writes, no splitting — and its per-section prose is read from those files
    in place. Detection ignores commented-out directives.

A paper with neither inline ``\\section`` nor a resolving ``\\input`` layout cannot be bridged;
:func:`bridged_network` raises :class:`SectionBridgeError` naming why (the corpus driver catches
it and reports the paper as unhandled — a finding, never a silent 2-node conceptric).
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from laplace.research.corpus_ingest import build_corpus_network
from laplace.engine.voice_corpus_ingest import demath, math_segments, strip_latex

# repo root = src/laplace/pipeline/section_bridge.py -> parents[3]
_REPO_ROOT = source_tree()

# lifted verbatim from demo_stage_stores.build_paper_net so the bridged net stays byte-identical
_SEC_RX = re.compile(r"(?m)^\s*\\section\*?\s*\{")
_LABEL_RX = re.compile(r"\\label\{([^}]+)\}")
_TITLE_RX = re.compile(r"\\section\*?\s*\{(.*?)\}", re.S)
_CLEAN_LABEL_RX = re.compile(r"\\label\{[^}]*\}?")
_INPUT_RX = re.compile(r"\\input\{([^}]+)\}")
_COMMENT_RX = re.compile(r"(?<!\\)%.*")


class SectionBridgeError(ValueError):
    """A paper the bridge cannot lift into the ``\\input{}`` layout: no inline ``\\section`` to
    split AND no resolving ``\\input`` layout to pass through (e.g. a paper with no section
    structure, or one whose ``\\section``s are all commented out). Carries ``paper_id`` so the
    corpus driver can report the paper by name."""

    def __init__(self, message: str, *, paper_id: str | None = None) -> None:
        super().__init__(message)
        self.paper_id = paper_id


# --------------------------------------------------------------------------- #
# helpers (lifted from the demo so the bridged net is byte-identical)
# --------------------------------------------------------------------------- #
def _paragraph_count(block: str) -> int:
    """Blank-line prose blocks in a section body (the census's mechanical paragraph proxy)."""
    b = re.sub(r"(?m)^\s*%.*$", "", block)
    return sum(1 for blk in re.split(r"\n\s*\n", b)
               if len(" ".join(blk.split())) >= 120 and not blk.strip().startswith("\\"))


#: The section ``embed_text`` window: head + tail character budgets, and the length above which a
#: section is windowed at all (the demo's 600/600/1300, unchanged).
_HEAD, _TAIL, _WINDOW_ABOVE = 600, 600, 1300

#: The SALVAGE band's budget, in the same prose currency as ``_HEAD``/``_TAIL``. The head+tail
#: window elides the middle, and in his papers the middle is where the methods paragraph lives —
#: the one that names the drive frequency, the lattice constant, the field amplitude and the
#: solver. Measured on ``SA-nuodfgnl-s2``: ``L=10`` and ``t_0=0.52`` eV sit in the head, and
#: ``\omega_0 = 32.7`` THz, ``a=4\AA``, ``F_0=10`` MV/cm, ``QuSpin`` and ``SCOOP`` all sat in the
#: elided middle (WO-20260820-section-window-caps-the-arcana). This band buys the DENSEST arcana
#: sentences of that middle back, in reading order.
_SALVAGE = 420

#: The floor the head and tail narrow to before the salvage band is touched (see
#: :func:`_fit_to_model_window`). Two thirds of the full budget: enough that the section's opening
#: claim and closing consequence still bracket the arcana.
_FLOOR = 400

#: The units his quantities are quoted in. A bare integer is not arcana ("Figure 3", "10 sites");
#: a number CARRYING one of these is. Ordered longest-first so ``MV/cm`` wins over ``V``.
_UNIT_ALT = "|".join([
    r"MV/cm", r"kV/cm", r"V/cm", r"V/m", r"W/cm\^?2", r"J/m\^?3",
    r"meV", r"keV", r"eV", r"THz", r"GHz", r"MHz", r"kHz", r"Hz",
    r"GPa", r"MPa", r"kPa", r"Pa", r"nm", r"pm", r"mm", r"cm", r"km", r"\\AA", "Å",
    r"fs", r"ps", r"ns", r"ms", r"kJ", r"mJ", r"uJ", r"nJ", r"J", r"eV", r"K", r"T",
])
#: number-with-unit, in the math-bearing text (``$F_0=10$MV/cm``, ``$T=2$ periods``, ``a=4\AA``).
_QUANTITY_RX = re.compile(r"\d(?:[\d.,]*\d)?\s*\$?\s*(?:" + _UNIT_ALT + r")\b")
#: a named tool/package/method: internal capitalisation (``QuSpin``) or an all-caps run (``SCOOP``,
#: ``DMRG``). Mechanical — no model, no vocabulary list to go stale.
_TOOLNAME_RX = re.compile(r"\b(?:[A-Za-z]*[a-z][A-Z][A-Za-z]*|[A-Z]{4,})\b")
#: any math span carrying a digit — the weakest arcana signal (near-ubiquitous in his sections),
#: so it scores one where a quantity or a tool name scores two.
_DIGIT_MATH_RX = re.compile(r"\d")
#: sentence-final punctuation on a prose token, minus the abbreviations that are not sentence ends.
_ABBREV = {"eq.", "eqs.", "fig.", "figs.", "ref.", "refs.", "sec.", "al.", "e.g.", "i.e.",
           "cf.", "vs.", "approx.", "no.", "ca."}


#: The EMBEDDER'S window, in its own tokens. ``bge-small-en-v1.5`` reads 512 wordpiece tokens and
#: fastembed truncates the rest SILENTLY — the same defect one mechanism down from this window, and
#: it was already biting before the salvage band existed (measured 2026-08-21: ``SA-dgoenzbv-s1``
#: 595 tokens, ``SA-wor2-s4`` 549, both cut with nothing said). A prose-character budget cannot
#: bound it, because his LaTeX costs ~2.9 chars/token where his prose costs ~5. So the window fits
#: itself to the model's window in the MODEL'S OWN tokenizer, and ``embed_text`` is by construction
#: what the embedder reads. 500 leaves headroom for the [CLS]/[SEP] pair and any batch prefix.
_MODEL_TOKENS = 500
_TOKENIZER_DIR = "fast-bge-small-en-v1.5"
_VENDOR_TARBALL = _REPO_ROOT / "models" / "fastembed" / f"{_TOKENIZER_DIR}.tar.gz"
_VENDOR_EXTRACT = Path.home() / ".cache" / "laplace" / "fastembed"   # embed_router's own cache
_TOKENIZER: Any = None
_TOKENIZER_TRIED = False


def _tokenizer() -> Any:
    """The EMBEDDING MODEL'S OWN tokenizer, from the vendored bundle ``embed_router`` ships and
    extracts (``models/fastembed/fast-bge-small-en-v1.5.tar.gz`` → ``~/.cache/laplace/fastembed``).
    Loaded lazily and cached; ``None`` when it cannot be had.

    ``None`` is not a silent degradation: an environment with no tokenizer has no embedder either
    (they come out of the same bundle), so there is nothing there for the window to be honest
    ABOUT — the unfitted window is emitted and no vector is ever minted from it."""
    global _TOKENIZER, _TOKENIZER_TRIED
    if _TOKENIZER_TRIED:
        return _TOKENIZER
    _TOKENIZER_TRIED = True
    try:
        from tokenizers import Tokenizer                      # fastembed's own dependency
        path = _VENDOR_EXTRACT / _TOKENIZER_DIR / "tokenizer.json"
        if not path.is_file() and _VENDOR_TARBALL.is_file():
            import tarfile
            _VENDOR_EXTRACT.mkdir(parents=True, exist_ok=True)
            with tarfile.open(_VENDOR_TARBALL, "r:gz") as tf:
                tf.extractall(_VENDOR_EXTRACT)
        if path.is_file():
            _TOKENIZER = Tokenizer.from_file(str(path))
    except Exception:                                          # no tokenizer => no embedder either
        _TOKENIZER = None
    return _TOKENIZER


def _model_tokens(text: str) -> int | None:
    """``text``'s length in the embedding model's tokens, or ``None`` when it cannot be measured."""
    tk = _tokenizer()
    return None if tk is None else len(tk.encode(text).ids)


def _fits_model(text: str) -> bool:
    """True when ``text`` fits the embedder's window — or when there is no embedder to measure
    against (see :func:`_tokenizer`), which is the same thing for this text's purposes."""
    n = _model_tokens(text)
    return n is None or n <= _MODEL_TOKENS


def _arcana_score(sentence: str) -> int:
    """How much arcana grain one sentence carries. Mechanical and additive: a number with a unit
    or a named tool scores 2, a digit inside a math span scores 1. Zero means the sentence is
    connective prose, and the salvage band never spends its budget on it."""
    score = 2 * len(_QUANTITY_RX.findall(sentence)) + 2 * len(_TOOLNAME_RX.findall(sentence))
    for is_math, chunk in math_segments(sentence):
        if is_math and _DIGIT_MATH_RX.search(chunk):
            score += 1
    return score


def _sentences(units: list[tuple[str, int]]) -> list[list[tuple[str, int]]]:
    """Group a unit run into sentences. A sentence ends on a PROSE token ending in ``.``/``!``/
    ``?`` that is not a known abbreviation; math spans never end a sentence (``$U=0$.`` is one
    token followed by the period-carrying word)."""
    out: list[list[tuple[str, int]]] = []
    cur: list[tuple[str, int]] = []
    for tok, cost in units:
        cur.append((tok, cost))
        if cost and tok[-1:] in ".!?" and tok.lower() not in _ABBREV:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


#: A salvage CANDIDATE: ``(order, score, cost, text)`` — reading position, arcana density, its
#: cost in the prose currency, and the sentence itself. ``order`` is a global monotone int (head
#: sentences below :data:`_MID_BASE`, the elided middle's above it, the tail's above
#: :data:`_TAIL_BASE`) so a band assembled from all three still reads in his order.
_MID_BASE, _TAIL_BASE = 1_000_000, 2_000_000
Candidate = tuple[int, int, int, str]


def _candidates(units: list[tuple[str, int]], base: int) -> list[Candidate]:
    """The arcana-bearing sentences of a unit run. A sentence scoring zero is connective prose and
    is never a candidate — which is what keeps an arcana-free section byte-identical to the demo's
    rule."""
    out: list[Candidate] = []
    for i, sent in enumerate(_sentences(units)):
        text = " ".join(t for t, _ in sent)
        if (score := _arcana_score(text)):
            out.append((base + i, score, sum(c for _, c in sent), text))
    return out


def _select(pool: list[Candidate], cap: int) -> list[Candidate]:
    """The salvage band: the densest arcana the pool offers, within ``cap``, in READING ORDER.

    Ranked by :func:`_arcana_score` (ties broken by position, so the earlier of two equally dense
    sentences wins) and taken greedily — a sentence too long to fit is SKIPPED, never allowed to
    end the selection — then re-sorted into reading order so the band reads as his prose rather
    than as a bag of numbers."""
    chosen: list[Candidate] = []
    used = 0
    for cand in sorted(pool, key=lambda c: (-c[1], c[0])):
        if used + cand[2] > cap:
            continue
        chosen.append(cand)
        used += cand[2]
    return sorted(chosen)


def _assemble(head: str, band: list[Candidate], tail: str) -> str:
    """head ``...`` [salvage ``...``] tail — the elision markers stay, so the row still reads as a
    WINDOW and never as a claim to be the whole section."""
    mid = " ".join(c[3] for c in band)
    return head + " ... " + (mid + " ... " if mid else "") + tail


def _fit_to_model_window(head_u: list[tuple[str, int]], pool: list[Candidate],
                         tail_u: list[tuple[str, int]]) -> str:
    """Shrink the window until it fits :data:`_MODEL_TOKENS` in the embedder's own tokenizer, so
    ``embed_text`` IS what the model reads rather than a text the model quietly cuts.

    The give order is named, never arbitrary, and it PAYS FOR THE ARCANA rather than dropping it —
    the arcana is the point of the window; the prose around it is context. So the window narrows at
    its INNER edges, the head losing its last SENTENCE and the tail its first, down to
    :data:`_FLOOR` each: the same head+tail window at a smaller radius. Narrowing is sentence-
    granular, and a narrowed-off sentence that CARRIES ARCANA does not leave — it joins the salvage
    pool and competes on density with the middle's, so shrinking the head can never silently cost
    the reader ``$t_0 = 0.52$ eV`` (the very line the previous work order in this chain won back).
    Only below the floor does the band itself start giving up its least dense sentences, and only
    after that does the window narrow without a floor. Unmeasurable (no tokenizer, hence no
    embedder) returns the window unfitted."""
    def join(u: list[tuple[str, int]]) -> str:
        return " ".join(t for t, _ in u)

    head_s = _sentences(head_u)
    tail_s = _sentences(tail_u)
    pool = list(pool)

    def state() -> tuple[bool, str, list[Candidate]]:
        band = _select(pool, _SALVAGE)
        text = _assemble(join([u for s in head_s for u in s]), band,
                         join([u for s in tail_s for u in s]))
        n = _model_tokens(text)
        return (n is not None and n > _MODEL_TOKENS), text, band

    bad, text, band = state()
    if not bad:
        return text

    def narrow(floor: int, *, salvage: bool = True) -> tuple[bool, str]:
        nonlocal pool
        hc = sum(c for s in head_s for _, c in s)
        tc = sum(c for s in tail_s for _, c in s)
        tail_pops = 0
        bad, text, _ = state()                                  # never return an unset window
        while (hc > floor and len(head_s) > 1) or (tc > floor and len(tail_s) > 1):
            wide_head = (hc >= tc and len(head_s) > 1 and hc > floor) or not (
                len(tail_s) > 1 and tc > floor)
            sent = head_s.pop() if wide_head else tail_s.pop(0)
            cost = sum(c for _, c in sent)
            if wide_head:
                hc -= cost
                order = len(head_s)                             # its own index in reading order
            else:
                tc -= cost
                tail_pops += 1
                order = _TAIL_BASE + tail_pops
            stext = " ".join(t for t, _ in sent)
            if salvage and (score := _arcana_score(stext)):     # narrowed off, not thrown away
                pool.append((order, score, cost, stext))
            bad, text, _ = state()
            if not bad:
                break
        return bad, text

    bad, text = narrow(_FLOOR)
    if not bad:
        return text

    densest = _select(pool, _SALVAGE)[:1]                       # everything this section knows
    while pool:
        pool.remove(min(pool, key=lambda c: (c[1], -c[0])))     # lowest score, latest position
        bad, text, _ = state()
        if not bad:
            return text
    # LAST RESORT: a section so math-dense that head and tail alone outrun the embedder. Narrow
    # without a floor, and stop re-salvaging — a math-dense sentence costs almost nothing in the
    # prose currency but hundreds of wordpieces, so a band that keeps refilling from what the
    # narrowing sheds never converges. The ONE densest sentence stays: when the window has to
    # collapse to almost nothing, the arcana is the last thing to go, not the first.
    pool = list(densest)
    return narrow(0, salvage=False)[1]


def _prose_window(prose: str) -> str:
    """The head+tail window over a section's prose, BUDGETED IN PROSE, not in characters.

    The demo sliced raw characters. With the math kept (which is the point — the numbers stop
    being deleted) a raw slice spends its budget on ``\\hat{c}^\\dagger_{j\\uparrow}`` and drops
    real sentences that used to fit: the measured casualty was the ``non-uniqueness`` §2 line "In
    all cases, we use an $L=10$ site system … $t_0 = 0.52$ eV", which fell out of the head. So the
    budget counts each token's cost IN THE MATH-FREE RENDERING: a token that is pure math cost
    nothing there (it collapsed to nothing between two spaces) and costs nothing here, so the
    window admits the SAME sentences the old rule admitted — now carrying their numbers.

    AND THE MIDDLE NO LONGER SWALLOWS THE ARCANA. head+tail elides everything between, and that is
    where his methods paragraph lives; measured on ``SA-nuodfgnl-s2``, ``\\omega_0 = 32.7`` THz,
    ``a=4\\AA``, ``F_0=10`` MV/cm, ``QuSpin`` and ``SCOOP`` were all inside the ellipsis. A third
    band — the SALVAGE band (:func:`_salvage`) — buys the densest arcana sentences of that middle
    back, in reading order, inside its own budget (WO-20260820-section-window-caps-the-arcana). A
    middle carrying NO arcana salvages nothing and the window is byte-identical to the demo rule,
    math-free sections included.

    A section SHORT enough not to be windowed is still checked against the model window: a prose
    budget cannot bound wordpieces, and a math-dense short section can outrun the embedder on its
    own (measured: ``SA-wor2-s4``, 1546 chars of prose budget 1300, 549 tokens — cut silently
    where nobody was looking). Such a section is windowed rather than handed over to be truncated.
    """
    plain = demath(prose)
    if plain == prose:                                    # no math: the old raw-character slice
        if len(prose) <= _WINDOW_ABOVE and _fits_model(prose):
            return prose
        pool = _candidates([(w, len(w) + 1) for w in prose[_HEAD:-_TAIL].split(" ") if w],
                           _MID_BASE)
        text = _assemble(prose[:_HEAD], _select(pool, _SALVAGE), prose[-_TAIL:])
        if _fits_model(text):
            return text                                   # the demo's slice, byte-for-byte
        return _fit_to_model_window(
            [(w, len(w) + 1) for w in prose[:_HEAD].split(" ") if w], pool,
            [(w, len(w) + 1) for w in prose[-_TAIL:].split(" ") if w])

    # UNITS: a math span is ONE unit costing 0 (it costs nothing in the math-free rendering, where
    # it collapsed away between two spaces); every other word costs its own length + its space.
    units: list[tuple[str, int]] = []
    for is_math, chunk in math_segments(prose):
        if is_math:
            units.append((chunk, 0))
        else:
            for w in chunk.split(" "):
                if w:
                    units.append((w, len(w) + 1))
    if sum(c for _, c in units) - 1 <= _WINDOW_ABOVE and _fits_model(prose):
        return prose

    def take(seq: list[tuple[str, int]], cap: int) -> int:
        """How many leading units of ``seq`` fit in ``cap`` (the budget is a prefix, as before)."""
        used = n = 0
        for _, c in seq:
            if used + c > cap:
                break
            used += c
            n += 1
        return n

    nh = take(units, _HEAD)
    # zero-cost math units are admitted freely, so a run of them can carry head and tail into each
    # other; clamp so no unit is emitted twice.
    nt = min(take(list(reversed(units)), _TAIL), len(units) - nh)
    head = units[:nh]
    tail = units[len(units) - nt:] if nt else []
    pool = _candidates(units[nh:len(units) - nt], _MID_BASE)
    text = _assemble(" ".join(t for t, _ in head), _select(pool, _SALVAGE),
                     " ".join(t for t, _ in tail))
    return text if _fits_model(text) else _fit_to_model_window(head, pool, tail)


def _section_enrichment(block: str, sid_fallback_stem: str, idx: int) -> tuple[str, str, dict[str, Any]]:
    """Compute the per-section enrichment triple (sid, embed_text, meta) for one ``\\section``
    block, replicating the demo's rule so section ids match the net's OWN atomised ids: the
    section id is the first ``\\label{sec:…}`` in the block, else ``sec:<stem>`` (the atomiser's
    fallback). Deterministic and content-only — no path leaks in.

    THE MATH IS KEPT (``strip_latex(..., keep_math=True)``). The default strip DELETES every math
    span, which removes numeric literals mid-sentence and leaves the sentence grammatical, so
    nothing signals the loss — measured on the blind bench as "In all cases, we use " where the
    paper says ``$L=10$`` sites, ``$t_0 = 0.52$`` eV, ``$\\omega_0 = 32.7$`` THz. The
    ``derivation_walk`` lens already keeps raw LaTeX and reads correctly; this lens now matches it
    (WO-20260820-extraction-lens-keeps-math)."""
    sec_label = next((lab for lab in _LABEL_RX.findall(block) if lab.startswith("sec:")), None)
    sid = sec_label or f"sec:{sid_fallback_stem}"
    any_label = next(iter(_LABEL_RX.findall(block)), None)
    tm = _TITLE_RX.search(block)
    title = _CLEAN_LABEL_RX.sub("", tm.group(1)).strip() if tm else sid_fallback_stem
    prose = " ".join(strip_latex(block, keep_math=True).split())
    embed_text = _prose_window(prose)
    meta: dict[str, Any] = {
        "idx": idx, "title": title, "label": sec_label or any_label,
        "para_count": _paragraph_count(block),
    }
    return sid, (embed_text or title), meta


def _repo_relative(p: Path) -> str:
    """The path as a repo-relative string when it sits under the repo (the demo's ``source_file``
    shape), else its absolute string — so a bridged net built from ``voice_corpus/…`` carries the
    same ``source_file`` the demo wrote."""
    rp = Path(p).resolve()
    try:
        return str(rp.relative_to(_REPO_ROOT))
    except ValueError:
        return str(rp)


def _resolves_input_layout(tex_path: Path, text: str) -> bool:
    """True iff ``tex_path`` is a ``main.tex`` whose (non-commented) ``\\input`` directives resolve
    to real sibling ``.tex`` files — i.e. the paper is ALREADY in the layout the atomiser consumes,
    so it passes through unbridged. Commented directives (``% \\input{…}``) are ignored: detection
    reads the comment-stripped text, so a "please do not use ``\\input``" banner never trips it."""
    if tex_path.name != "main.tex":
        # the atomiser enters at <dir>/main.tex; a differently-named single file has no \input
        # entry point to build directly, so it is never a pass-through candidate.
        return False
    src_dir = tex_path.parent
    stripped = _COMMENT_RX.sub("", text)
    for inc in _INPUT_RX.findall(stripped):
        path = src_dir / inc
        if path.suffix != ".tex":
            path = path.with_suffix(".tex")
        if path.is_file():
            return True
    return False


# --------------------------------------------------------------------------- #
# the bridge
# --------------------------------------------------------------------------- #
def _bridge_inline_sections(tex_path: Path, paper_id: str, text: str,
                            workdir: Path | None) -> dict[str, Any]:
    """Split inline ``\\section`` blocks into the ``\\input{}`` layout in an isolated workdir, build
    the conceptric, and enrich it — the demo's ``build_paper_net`` body, generalised to any tex."""
    m = re.search(r"\\begin\{document\}", text)
    doc_start = m.end() if m else 0
    doc_end = text.find(r"\end{document}")
    doc_end = doc_end if doc_end != -1 else len(text)
    body = text[doc_start:doc_end]

    starts = [mm.start() for mm in _SEC_RX.finditer(body)]
    if not starts:
        raise SectionBridgeError(
            f"no inline \\section blocks in {tex_path.name} (and no resolving \\input layout) — "
            "nothing to bridge", paper_id=paper_id)

    owns_workdir = workdir is None
    root = Path(workdir) if workdir is not None else Path(
        tempfile.mkdtemp(prefix="section_bridge_"))
    work = root / paper_id
    try:
        work.mkdir(parents=True, exist_ok=True)
        inputs: list[str] = []
        section_prose: dict[str, str] = {}
        section_meta: dict[str, dict[str, Any]] = {}
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else len(body)
            block = body[s:e]
            fn = f"sec{i:02d}"
            (work / f"{fn}.tex").write_text(block, encoding="utf-8")
            inputs.append(fn)
            sid, embed_text, meta = _section_enrichment(block, fn, i)
            meta["char_start"] = doc_start + s
            meta["char_end"] = doc_start + e
            section_prose[sid] = embed_text
            section_meta[sid] = meta
        (work / "main.tex").write_text(
            "\n".join(f"\\input{{{fn}}}" for fn in inputs) + "\n", encoding="utf-8")

        net = build_corpus_network(work)
    finally:
        if owns_workdir:
            shutil.rmtree(root, ignore_errors=True)

    net["section_prose"] = section_prose
    net["section_meta"] = section_meta
    net["source_file"] = _repo_relative(tex_path)
    net["paper_id"] = paper_id
    net["bridged"] = True
    return net


def _passthrough_network(tex_path: Path, paper_id: str) -> dict[str, Any]:
    """Build a paper ALREADY in ``\\input{}`` layout directly from its source dir (zero writes),
    then attach per-section prose read in place from the ``\\input``'d files, keyed by the net's
    own section ids (the same id rule the atomiser and the bridge share)."""
    src_dir = tex_path.parent
    net = build_corpus_network(src_dir)

    text = tex_path.read_text(encoding="utf-8", errors="ignore")
    stripped = _COMMENT_RX.sub("", text)
    section_prose: dict[str, str] = {}
    section_meta: dict[str, dict[str, Any]] = {}
    idx = 0
    for inc in _INPUT_RX.findall(stripped):
        path = src_dir / inc
        if path.suffix != ".tex":
            path = path.with_suffix(".tex")
        if not path.is_file():
            continue
        block = path.read_text(encoding="utf-8", errors="ignore")
        if not _SEC_RX.search(block):
            continue  # a preamble/macro \input, not a section file — skip
        sid, embed_text, meta = _section_enrichment(block, path.stem, idx)
        if sid in net["nodes"]:
            section_prose[sid] = embed_text
            section_meta[sid] = meta
            idx += 1

    net["section_prose"] = section_prose
    net["section_meta"] = section_meta
    net["source_file"] = _repo_relative(tex_path)
    net["paper_id"] = paper_id
    net["bridged"] = False
    return net


def bridged_network(tex_path: Path | str, paper_id: str,
                    workdir: Path | str | None = None) -> dict[str, Any]:
    """Build the full-fidelity per-paper conceptric for a single-file (or ``\\input``-layout) paper.

    The up operator + THE BRIDGE. Runs the proven ``corpus_ingest.build_corpus_network`` over the
    ``\\input{}`` layout it consumes: a paper already in that layout passes through unbridged, an
    inline-``\\section`` paper is split into it (in ``workdir``, an OS tempdir by default — the
    source tree is never written). The returned net carries the demo's enrichment
    (``section_prose`` / ``section_meta`` keyed by the net's own section ids, ``source_file``,
    ``paper_id``) plus a ``bridged`` bool, so the ``stage_store`` derivers see his real prose.

    Args:
        tex_path: the paper's tex file (a single-file inline-``\\section`` paper, or a ``main.tex``
            in resolving ``\\input`` layout).
        paper_id: the census paper id (stamped on ``net["paper_id"]``; the derivers key row ids off
            it).
        workdir: an isolated directory to split section files into. ``None`` (default) mints a fresh
            OS tempdir and removes it before returning (the built net is fully in-memory). Ignored
            on the pass-through path (no split). NEVER the source tree.

    Returns:
        the ``{nodes, edge_index, ctx, spine, …}`` net ``build_corpus_network`` returns, enriched
        with ``section_prose`` / ``section_meta`` / ``source_file`` / ``paper_id`` / ``bridged``.

    Raises:
        SectionBridgeError: the paper has neither inline ``\\section`` nor a resolving ``\\input``
            layout (nothing to bridge) — reported by name, never silently degraded.
    """
    tex_path = Path(tex_path)
    if not tex_path.is_file():
        raise SectionBridgeError(f"tex not found: {tex_path}", paper_id=paper_id)
    text = tex_path.read_text(encoding="utf-8", errors="ignore")

    # detect \input layout FIRST — pass through unbridged, don't force a split (the contract).
    if _resolves_input_layout(tex_path, text):
        return _passthrough_network(tex_path, paper_id)
    return _bridge_inline_sections(tex_path, paper_id, text, workdir)
