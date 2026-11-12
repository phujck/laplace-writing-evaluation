"""voice_corpus_ingest.py — wire the committed voice-corpus .tex exemplars into a sealed,
embedded passage store so the voice pass grounds on the author's REAL prose (show-not-tell).

The committed sources live at ``voice_corpus/exemplars/<slug>/*.tex`` — his own manuscript
LaTeX (9 files, ~924 KB). This module:

  1. strips each ``.tex`` to readable prose (preamble / comments / math / macros removed,
     paragraph boundaries preserved) and splits it into paragraph-grade passages in the
     voice-bearing length band, REUSING ``chunk_source.py``'s provenance machinery
     (``paragraph_spans`` / ``byte_offsets`` / ``chunk_id`` / ``digest`` / ``Span``) — the
     same containment layer the ``voice_corpus_reader`` skill defines. That script was
     imported by zero modules; this is its first caller (the "wire chunk_source" seam);
  2. embeds every passage once via ``embed_router`` (the vendored open-weight bge-small over
     ONNX; content-hash cached so an unchanged passage never re-embeds);
  3. answers ``nearest_authored_passage(span, k)`` — the k nearest passages of HIS real prose
     to a query span, by cosine. This is the substrate the voice-retrieval path was missing:
     the exemplar path dead-ended when only prose-less PDF stubs were available; the committed
     ``.tex`` revives it.

Cache locality (NOT the seal — the raw .tex is committed; nothing here is sealed):
the derived store lives under ``corpus_stores/`` (tracked) and is regenerated per machine
from the committed ``.tex`` — the SOURCES travel, the vectors don't (mirrors
``.self_embeddings.json`` / ``.voice_exemplar_vectors.json``). ``ingest`` prints counts and
paths only (``voice_corpus_reader`` discipline); a deliberate ``query`` prints his prose,
which is the point of grounding — not a leak.

Usage:
    python -m laplace.engine.voice_corpus_ingest ingest [--exemplar-dir DIR] [--rebuild]
    python -m laplace.engine.voice_corpus_ingest query "the operator evolves the state" --k 5
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from laplace.representation.embed_router import get_backend

# --------------------------------------------------------------------------- #
# locations — the committed sources, and the sealed (gitignored) derived store
# --------------------------------------------------------------------------- #
_REPO_ROOT = source_tree()
_DEFAULT_EXEMPLAR_DIR = _REPO_ROOT / "voice_corpus" / "exemplars"
_DEFAULT_CACHE_ROOT = _REPO_ROOT / "corpus_stores" / "voice_corpus_cache"
_STORE_SUBDIR = "exemplar_passages"

# the voice-bearing prose band (chars) — shorter blocks are headings/fragments, longer are
# usually un-split multi-topic dumps. Matches scripts/voice_retrieve.py's _MIN_PARA/_MAX_PARA
# so the sealed store and the live retrieve stage agree on what counts as a passage.
MIN_PARA = 280
MAX_PARA = 2400
SCHEMA = "voice-exemplar-passages/0.1"

_CHUNK_SOURCE_PATH = (
    _REPO_ROOT / "src" / "laplace" / "pipeline" / "canon" / "skills"
    / "voice_corpus_reader" / "scripts" / "chunk_source.py"
)
_CHUNK_SOURCE: ModuleType | None = None


def chunk_source() -> ModuleType:
    """Load ``chunk_source.py`` by path and cache it.

    It is a skill script (no ``__init__.py`` along its path), so it cannot be imported as
    ``laplace.pipeline.canon.skills...``. Loading it by file spec is the wiring seam: we run its real
    code and reuse its provenance/ID/hash primitives rather than re-implementing them.
    """
    global _CHUNK_SOURCE
    if _CHUNK_SOURCE is None:
        spec = importlib.util.spec_from_file_location(
            "laplace._voice_chunk_source", _CHUNK_SOURCE_PATH
        )
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise ImportError(f"cannot load chunk_source at {_CHUNK_SOURCE_PATH}")
        mod = importlib.util.module_from_spec(spec)
        # register before exec so chunk_source's @dataclass (with `from __future__ import
        # annotations`) can resolve its own module namespace during class creation.
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _CHUNK_SOURCE = mod
    return _CHUNK_SOURCE


# --------------------------------------------------------------------------- #
# LaTeX -> readable prose (crude by design; a band filter, not a parser)
# --------------------------------------------------------------------------- #
_MATH_ENV = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath|figure|table|tabular|"
    r"tikzpicture|algorithm|algorithmic|lstlisting|verbatim|thebibliography)\*?\}"
    r".*?\\end\{\1\*?\}",
    re.S,
)
_DROP_MACRO = re.compile(
    r"\\(?:cite[a-zA-Z]*|ref|eqref|autoref|cref|Cref|pageref|label|includegraphics|input|"
    r"include|usepackage|documentclass|newcommand|renewcommand|providecommand|def|"
    r"bibliographystyle|bibliography|footnote|url|href)\s*"
    r"(?:\[[^\]]*\])?(?:\{[^{}]*\})?(?:\{[^{}]*\})?"
)
_ESCAPES = {r"\%": "%", r"\&": "&", r"\_": "_", r"\#": "#", r"\$": "$", r"\{": "{", r"\}": "}"}


#: The inline/display math forms ``strip_latex`` deletes by default. Ordered widest-first so a
#: ``$$…$$`` is never mis-read as two empty ``$…$`` (the same order the deletion pass used).
_MATH_FORMS: tuple[re.Pattern[str], ...] = (
    _MATH_ENV,
    re.compile(r"\\\[.*?\\\]", re.S),
    re.compile(r"\$\$.*?\$\$", re.S),
    re.compile(r"(?<!\\)\$.*?(?<!\\)\$", re.S),
)

#: Under ``keep_math`` only the MATH environments are protected; ``figure``/``table``/``tabular``/
#: ``tikzpicture``/``algorithm``/``lstlisting``/``verbatim``/``thebibliography`` stay deleted —
#: they are non-prose payload, not his notation, and restoring them verbatim would drown the row.
_MATH_ENV_ONLY = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath)\*?\}"
    r".*?\\end\{\1\*?\}",
    re.S,
)
_KEEP_MATH_FORMS: tuple[re.Pattern[str], ...] = (
    _MATH_ENV_ONLY,
    re.compile(r"\\\[.*?\\\]", re.S),
    re.compile(r"\$\$.*?\$\$", re.S),
    re.compile(r"(?<!\\)\$.*?(?<!\\)\$", re.S),
)

#: The placeholder carrying one protected math span through the macro-stripping passes. Chosen
#: from a private-use codepoint so no real tex body can collide with it, and shaped so the
#: surrounding whitespace/brace passes leave it untouched.
_MATH_SLOT = "\ue000M{}\ue001"
_MATH_SLOT_RX = re.compile("\ue000M(\\d+)\ue001")


def _keep_math_number(raw: str) -> bool:
    """True iff a math span carries a NUMERIC literal or a unit-bearing token — the grain the
    default strip silently deletes mid-sentence ("a pulse duration of $190$ fs" -> "of fs").
    A purely symbolic span is kept too (it is his notation); this predicate exists only to name
    what the deletion cost, and is used by the tests, not the strip."""
    return bool(re.search(r"\d", raw))


def strip_latex(tex: str, keep_math: bool = False) -> str:
    """A ``.tex`` source -> readable prose with paragraph boundaries (blank lines) preserved.

    Deliberately crude and paired with the length-band filter downstream: it drops the
    preamble, comments, display/inline math and known non-prose environments, unwraps a few
    text-bearing macros (``\\emph{x}`` -> ``x``, ``\\section{Intro}`` -> ``Intro``) and deletes
    reference/structural macros. It is NOT a LaTeX parser; it aims to leave real sentences
    intact so cosine sees his prose, not his markup.

    ``keep_math=True`` (the extraction-lens mode) PRESERVES every math span VERBATIM instead of
    deleting it — the ``derivation_walk`` lens already keeps raw LaTeX and reads correctly, while
    the default deletion silently removes numeric literals mid-sentence and leaves the sentence
    grammatical, so nothing signals the loss ("a pulse duration of $190$ fs, $400\\,\\mu$J pulse
    energy" -> "a pulse duration of fs, J pulse energy").

    THE PARAGRAPH SHAPE IS INVARIANT under the flag. A math span that stood ALONE on its lines is
    a *display*, not part of a sentence — the default strip turns it into the blank line that ends
    a paragraph, so keep_math drops it too, and every other span is single-lined in place. Hence
    ``strip_latex(t)`` and ``strip_latex(t, keep_math=True)`` have the SAME paragraphs in the SAME
    order: a stored row can be re-minted by its paragraph index without the row set moving under
    it, and the display equations live in ``spine_chain`` / ``derivation_walk`` where they belong.
    """
    # keep only the document body when delimited; always cut a bibliography tail
    m = re.search(r"\\begin\{document\}", tex)
    if m:
        tex = tex[m.end():]
    tex = re.split(r"\\end\{document\}", tex, maxsplit=1)[0]
    tex = re.split(r"\\begin\{thebibliography\}|\\bibliography\b", tex, maxsplit=1)[0]

    # comments: full-line then inline (leaving escaped \% alone)
    tex = re.sub(r"(?m)^\s*%.*$", "", tex)
    tex = re.sub(r"(?<!\\)%.*", "", tex)

    # math: DELETED by default; PROTECTED verbatim under keep_math (restored after the macro
    # passes, which would otherwise eat \frac, \mu, the braces and the digits' companions).
    kept: list[str] = []
    if keep_math:
        def _protect(mm: re.Match[str]) -> str:
            kept.append(" ".join(mm.group(0).split()))   # single-lined: paragraph shape preserved
            return _MATH_SLOT.format(len(kept) - 1)
        for rx in _KEEP_MATH_FORMS:
            tex = rx.sub(_protect, tex)
        tex = _MATH_ENV.sub(" ", tex)                    # the non-prose environments still go
    else:
        for rx in _MATH_FORMS:
            tex = rx.sub(" ", tex)

    # reference/structural macros: delete outright (with any bracket/brace args)
    tex = _DROP_MACRO.sub(" ", tex)
    # environment tags: drop \begin{env}/\end{env} but KEEP the environment's prose contents
    tex = re.sub(r"\\(?:begin|end)\s*\{[^{}]*\}(?:\[[^\]]*\])?", " ", tex)

    # unwrap text-bearing macros: \cmd[..]{arg} -> arg (loop for shallow nesting)
    for _ in range(4):
        new = re.sub(r"\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", tex)
        if new == tex:
            break
        tex = new

    # restore a few common escapes, then remove leftover bare macros and stray braces
    for src, dst in _ESCAPES.items():
        tex = tex.replace(src, dst)
    tex = re.sub(r"\\[a-zA-Z]+\*?", " ", tex)
    tex = re.sub(r"\\[^a-zA-Z]", " ", tex)  # \\, \,, \; ...
    tex = tex.replace("{", " ").replace("}", " ").replace("~", " ")

    # tidy whitespace while KEEPING paragraph (blank-line) boundaries
    if kept:
        # a line holding NOTHING but protected math is a DISPLAY: the default strip empties it and
        # so ends the paragraph there. Empty it here too, before the tidy — that is the whole of
        # the paragraph-shape invariance (see the docstring).
        tex = re.sub(r"(?m)^[ \t]*(?:" + _MATH_SLOT_RX.pattern + r"[ \t]*)+$", "", tex)

    tex = re.sub(r"[ \t]+", " ", tex)
    tex = re.sub(r" *\n *", "\n", tex)
    tex = re.sub(r"\n{3,}", "\n\n", tex)

    if kept:
        # restore LAST: the math spans go back verbatim, untouched by the brace/macro passes.
        tex = _MATH_SLOT_RX.sub(lambda mm: kept[int(mm.group(1))], tex)
    return tex.strip()


def math_segments(text: str) -> list[tuple[bool, str]]:
    """Split a keep_math rendering into ``(is_math, chunk)`` segments in order. A math span is ONE
    segment however many spaces it contains — which is why a caller budgeting prose must never
    tokenise on whitespace first (``$\\hat c^\\dagger_j \\hat c_j$`` is one span, not two words)."""
    spans: list[tuple[int, int]] = []
    for rx in _KEEP_MATH_FORMS:
        for mm in rx.finditer(text):
            if not any(s <= mm.start() < e for s, e in spans):
                spans.append((mm.start(), mm.end()))
    spans.sort()
    out: list[tuple[bool, str]] = []
    cur = 0
    for s, e in spans:
        if s < cur:
            continue
        if s > cur:
            out.append((False, text[cur:s]))
        out.append((True, text[s:e]))
        cur = e
    if cur < len(text):
        out.append((False, text[cur:]))
    return out


def demath(text: str) -> str:
    """A keep_math rendering back to its DEFAULT-strip rendering: every restored math span
    removed. The alignment primitive — a paragraph is "blank in the default strip" iff its
    ``demath`` is whitespace, and a passage's LENGTH BAND is judged on its ``demath`` so the
    keep_math row set is identical to the math-free one (the re-mint changes text, never rows)."""
    for rx in _KEEP_MATH_FORMS:
        text = rx.sub(" ", text)
    return text


def prose_aligned_with_math(tex: str) -> str:
    """The ``keep_math`` prose — PARAGRAPH-ALIGNED to ``strip_latex(tex)`` by construction (see
    :func:`strip_latex`'s paragraph-shape invariance). Named separately because that alignment is
    the contract the in-place re-mint depends on, and a caller should be able to say so."""
    return strip_latex(tex, keep_math=True)


def prose_paragraphs(
    tex: str, min_chars: int = MIN_PARA, max_chars: int = MAX_PARA
) -> list[str]:
    """Band-filtered, whitespace-collapsed prose paragraphs from a ``.tex`` source.

    The public list form (parity with the retrieve stage). The store builder uses the
    span-carrying path below so passages keep provenance, but yields the same texts.
    """
    out: list[str] = []
    for block in re.split(r"\n\s*\n", strip_latex(tex)):
        b = " ".join(block.split())
        if min_chars <= len(b) <= max_chars and not b.startswith("\\"):
            out.append(b)
    return out


def _slug_for(tex_path: Path, exemplar_dir: Path) -> str:
    """The paper slug: the immediate sub-directory of the exemplar root (his files are mostly
    named ``main.tex``, so the directory carries the identity), falling back to the stem."""
    try:
        rel = tex_path.relative_to(exemplar_dir)
    except ValueError:
        return tex_path.stem
    return rel.parts[0] if len(rel.parts) > 1 else tex_path.stem


def passages_for_source(tex_path: Path, exemplar_dir: Path,
                        keep_math: bool = False) -> list[dict[str, Any]]:
    """Provenance-carrying passage records for one ``.tex`` file, built through chunk_source.

    ``keep_math=True`` is the EXTRACTION-LENS mode (WO-20260820-extraction-lens-keeps-math): each
    passage's ``text`` keeps his math verbatim instead of having it deleted mid-sentence. The row
    set is unchanged — paragraphs are aligned through :func:`prose_aligned_with_math` and the
    length band is judged on the math-free rendering (:func:`demath`) — so the same paper yields
    the same passages, in the same order, with the same paragraph indices, only richer text."""
    cs = chunk_source()
    slug = _slug_for(tex_path, exemplar_dir)
    handle = "VOICE-" + re.sub(r"[^A-Z0-9]+", "-", slug.upper()).strip("-")

    text = cs.normalise_newlines(cs.read_text(tex_path))
    prose = prose_aligned_with_math(text) if keep_math else strip_latex(text)
    offsets = cs.byte_offsets(prose)

    records: list[dict[str, Any]] = []
    for span in cs.paragraph_spans(prose, offsets):
        collapsed = " ".join(span.text.split())
        # the band + the "not a bare macro" guard read the MATH-FREE text in both modes, so the
        # kept-math store is row-for-row the same store.
        banded = " ".join(demath(collapsed).split()) if keep_math else collapsed
        if not (MIN_PARA <= len(banded) <= MAX_PARA) or banded.startswith("\\"):
            continue
        records.append(
            {
                "passage_id": cs.chunk_id(handle, span),
                "slug": slug,
                "source_handle": handle,
                "file": tex_path.name,
                "rel_path": _rel(tex_path),
                "paragraph_start": span.paragraph_start,
                "paragraph_end": span.paragraph_end,
                "char_start": span.char_start,
                "char_end": span.char_end,
                "char_count": len(collapsed),
                "sha256": cs.digest(collapsed),
                "text": collapsed,
            }
        )
    return records


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_dir(cache_root: Path | str) -> Path:
    return Path(cache_root) / _STORE_SUBDIR


# --------------------------------------------------------------------------- #
# build: chunk -> embed -> seal
# --------------------------------------------------------------------------- #
def build_store(
    exemplar_dir: Path | str = _DEFAULT_EXEMPLAR_DIR,
    cache_root: Path | str = _DEFAULT_CACHE_ROOT,
    *,
    rebuild: bool = False,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Chunk every committed ``.tex`` into passages, embed them (content-hash cached), and
    write the sealed store (``passages.jsonl`` + ``manifest.json`` + ``embeddings.json``).

    Returns a summary dict (counts + paths + backend). ``backend`` may be injected (tests use
    the deterministic ``HashBackend``); by default the vendored bge-small router is used.
    """
    exemplar_dir = Path(exemplar_dir)
    tex_files = sorted(exemplar_dir.rglob("*.tex"))
    if not tex_files:
        raise SystemExit(f"voice_corpus_ingest: no .tex under {exemplar_dir}")

    passages: list[dict[str, Any]] = []
    for tf in tex_files:
        passages.extend(passages_for_source(tf, exemplar_dir))
    if not passages:
        raise SystemExit(
            f"voice_corpus_ingest: {len(tex_files)} .tex file(s) under {exemplar_dir} but no "
            f"prose passages survived the {MIN_PARA}-{MAX_PARA} char band — check strip_latex."
        )

    if backend is None:
        backend = get_backend()
    if backend is None:
        raise SystemExit(
            "voice_corpus_ingest: no embedding backend (models/fastembed unavailable). "
            "The passage store built, but cannot embed; re-run where the vendored model loads."
        )

    store_dir = _store_dir(cache_root)
    store_dir.mkdir(parents=True, exist_ok=True)
    emb_path = store_dir / "embeddings.json"

    cached: dict[str, list[float]] = {}
    if emb_path.is_file() and not rebuild:
        try:
            disk = json.loads(emb_path.read_text(encoding="utf-8"))
            if disk.get("backend") == backend.name:
                cached = disk.get("items", {})
        except (OSError, json.JSONDecodeError):
            cached = {}

    shas = [p["sha256"] for p in passages]
    stale = [i for i, s in enumerate(shas) if s not in cached]
    if stale:
        vecs = backend.embed([passages[i]["text"] for i in stale])
        for i, v in zip(stale, vecs, strict=True):
            cached[shas[i]] = list(v)
    # keep only live keys (drop vectors for passages that no longer exist)
    live = {s: cached[s] for s in shas if s in cached}
    dim = len(next(iter(live.values()))) if live else 0
    emb_path.write_text(
        json.dumps({"backend": backend.name, "dim": dim, "items": live}),
        encoding="utf-8",
    )

    # passages.jsonl — the sealed store (carries text; lives under tracked corpus_stores/)
    (store_dir / "passages.jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in passages),
        encoding="utf-8",
    )

    # manifest.json — provenance + per-passage metadata, NO passage text
    sources: dict[str, dict[str, Any]] = {}
    for p in passages:
        s = sources.setdefault(
            p["slug"],
            {"slug": p["slug"], "source_handle": p["source_handle"],
             "rel_path": p["rel_path"], "passage_count": 0},
        )
        s["passage_count"] += 1
    manifest = {
        "schema_version": SCHEMA,
        "created_at": _now(),
        "exemplar_dir": _rel(exemplar_dir),
        "backend": backend.name,
        "dim": dim,
        "source_count": len(sources),
        "passage_count": len(passages),
        "band_chars": [MIN_PARA, MAX_PARA],
        "sources": sorted(sources.values(), key=lambda s: s["slug"]),
        "passages": [{k: v for k, v in p.items() if k != "text"} for p in passages],
    }
    (store_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return {
        "store_dir": str(store_dir),
        "backend": backend.name,
        "dim": dim,
        "source_count": len(sources),
        "passage_count": len(passages),
        "embedded_now": len(stale),
        "manifest": str(store_dir / "manifest.json"),
        "passages_jsonl": str(store_dir / "passages.jsonl"),
        "embeddings": str(emb_path),
    }


# --------------------------------------------------------------------------- #
# query: nearest authored passage
# --------------------------------------------------------------------------- #
def load_store(cache_root: Path | str = _DEFAULT_CACHE_ROOT) -> tuple[list[dict], Any, str]:
    """Load the sealed store: passage records, a unit-normalized vector matrix, backend name."""
    store_dir = _store_dir(cache_root)
    pj, ej = store_dir / "passages.jsonl", store_dir / "embeddings.json"
    if not pj.is_file() or not ej.is_file():
        raise SystemExit(
            f"voice_corpus_ingest: no store at {store_dir}. Run "
            f"`python -m laplace.engine.voice_corpus_ingest ingest` first."
        )
    passages = [json.loads(line) for line in pj.read_text(encoding="utf-8").splitlines() if line.strip()]
    emb = json.loads(ej.read_text(encoding="utf-8"))
    items = emb.get("items", {})
    missing = [p["passage_id"] for p in passages if p["sha256"] not in items]
    if missing:
        raise SystemExit(
            f"voice_corpus_ingest: store out of sync ({len(missing)} passage(s) unembedded); "
            f"re-run ingest --rebuild."
        )
    import numpy as np

    X = np.asarray([items[p["sha256"]] for p in passages], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    return passages, X, emb.get("backend", "?")


def nearest_authored_passage(
    span: str,
    k: int = 5,
    *,
    cache_root: Path | str = _DEFAULT_CACHE_ROOT,
    backend: Any | None = None,
    exclude: Any | None = None,
    store: tuple[list[dict], Any, str] | None = None,
) -> list[dict[str, Any]]:
    """The k nearest passages of the author's REAL prose to ``span``, by cosine.

    ``span`` is embedded with the same (document) embedding as the store — symmetric
    prose-to-prose similarity, matching scripts/voice_retrieve.py. Each result carries its
    provenance (slug / file / paragraph range), the cosine, and the passage text.

    ``exclude`` is an iterable of ``passage_id``s already claimed by an earlier
    query: a collision takes the NEXT-nearest instead (voice_descent rule 3 —
    multiplicity comes from the corpus, not from rule). This is the per-passage
    ``used``-set the voice wash threads across a whole document so two paragraphs
    never fence the same exemplar. ``store`` lets a caller inject an already-loaded
    :func:`load_store` result so a per-paragraph sweep pays the load once, not once
    per paragraph. With both absent this is the plain top-``k`` query.
    """
    passages, X, _ = store if store is not None else load_store(cache_root)
    if backend is None:
        backend = get_backend()
    if backend is None:
        raise SystemExit("voice_corpus_ingest: no embedding backend for the query.")
    import numpy as np

    q = np.asarray(backend.embed([span])[0], dtype=np.float64)
    q /= max(float(np.linalg.norm(q)), 1e-12)
    scores = X @ q
    keep = ("passage_id", "slug", "file", "rel_path",
            "paragraph_start", "paragraph_end", "char_count", "text")
    excl = set(exclude or ())
    hits: list[dict[str, Any]] = []
    for i in (int(j) for j in np.argsort(-scores)):
        if passages[i]["passage_id"] in excl:
            continue
        hits.append({**{key: passages[i][key] for key in keep}, "cos": float(scores[i])})
        if len(hits) >= max(1, k):
            break
    return hits


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_ingest(args: argparse.Namespace) -> int:
    summary = build_store(
        exemplar_dir=args.exemplar_dir,
        cache_root=args.cache_root,
        rebuild=args.rebuild,
    )
    print("# Voice exemplar passage store")
    print(f"Backend:        {summary['backend']} (dim {summary['dim']})")
    print(f"Sources:        {summary['source_count']} paper(s)")
    print(f"Passages:       {summary['passage_count']} (embedded now: {summary['embedded_now']})")
    print(f"Store:          {summary['store_dir']}")
    print(f"Manifest:       {summary['manifest']}")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    hits = nearest_authored_passage(args.span, k=args.k, cache_root=args.cache_root)
    print(f"# nearest-authored-passage  (k={args.k})")
    print(f"query span: {args.span!r}\n")
    for rank, h in enumerate(hits, 1):
        loc = f"{h['slug']}/{h['file']}  P{h['paragraph_start']}"
        if h["paragraph_end"] != h["paragraph_start"]:
            loc += f"-P{h['paragraph_end']}"
        print(f"[{rank}] cos {h['cos']:.3f}  {loc}")
        print(f"    {h['text']}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m laplace.engine.voice_corpus_ingest",
        description="Ingest the committed voice-corpus .tex exemplars and query his nearest prose.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="chunk + embed the committed .tex into the sealed store")
    pi.add_argument("--exemplar-dir", default=str(_DEFAULT_EXEMPLAR_DIR),
                    help="root of the committed .tex exemplars (default: voice_corpus/exemplars)")
    pi.add_argument("--cache-root", default=str(_DEFAULT_CACHE_ROOT),
                    help="sealed cache root, tracked+travels (default: corpus_stores/voice_corpus_cache)")
    pi.add_argument("--rebuild", action="store_true", help="ignore the embedding cache")
    pi.set_defaults(func=_cmd_ingest)

    pq = sub.add_parser("query", help="k nearest passages of his real prose to a span")
    pq.add_argument("span", help="the query span, e.g. 'the operator evolves the state'")
    pq.add_argument("--k", type=int, default=5, help="number of passages to return")
    pq.add_argument("--cache-root", default=str(_DEFAULT_CACHE_ROOT))
    pq.set_defaults(func=_cmd_query)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
