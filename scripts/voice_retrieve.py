"""voice_descent's retrieve stage, mechanized (canon://skills/voice_descent - the
retrieve-then-write protocol): for each prose passage of a projected manuscript, pull the
author's nearest own-prose exemplars by cosine INTO a per-section voice brief, so the
voice pass writes FROM retrieved moves at the moment of generation - never from a spec.

Exemplar store: the author's own paragraph-grade prose. MEASURED CONSTRAINT (2026-07-02,
remote): the finished-paper corpora (qde, free-snacks) are PDF-sourced STUBS - their tex
roots carry no prose and the raw PDFs are sealed local (archive/soul_dump/my papers/) -
so on the remote this stage had no substrate and said so plainly. RESOLVED (2026-07-09):
his REAL manuscript .tex sources are now committed at voice_corpus/exemplars/<slug>/*.tex
(9 files, ~924 KB of authored prose), so --exemplar-dir now DEFAULTS there and the retrieve
stage finally reads from his own prose out of the box. Pass --exemplar-dir to override with
any directory of extracted paper text (.txt/.md/.tex). The engine's own welds are never
exemplars (the v9 mistake). Embedded with the standing backend, content-hash cached.
(A sealed, embedded, queryable form of the same corpus lives in
laplace.engine.voice_corpus_ingest.nearest_authored_passage.)

Per the protocol: retrieval is PER PASSAGE (rule 2), and if two passages retrieve the same
exemplar the second takes its next-nearest (rule 3 - multiplicity from the corpus, not
from rule).

Usage: python scripts/voice_retrieve.py <target-dir-with-S*.tex> [--out DIR] [--top N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.representation.embed_router import get_backend  # noqa: E402

EXEMPLAR_PROJECTS = ["qde", "free-snacks", "law-of-laws", "cost-of-complexity"]
DEFAULT_EXEMPLAR_DIR = ROOT / "voice_corpus" / "exemplars"   # his committed .tex prose
CACHE = ROOT / ".voice_exemplar_vectors.json"
_MIN_PARA = 280      # chars: shorter blocks are headings/fragments, not voice-bearing prose
_MAX_PARA = 2400


def tex_paragraphs(tex: str) -> list[str]:
    """Prose paragraphs from a tex source: comments stripped, display math collapsed,
    environments dropped, then blank-line-split blocks in the prose length band."""
    tex = re.sub(r"(?m)^%.*$", "", tex)
    tex = re.sub(r"\\begin\{(equation|align|figure|table|tikzpicture|algorithm)\*?\}.*?"
                 r"\\end\{\1\*?\}", " [MATH] ", tex, flags=re.S)
    tex = re.sub(r"\\\[.*?\\\]", " [MATH] ", tex, flags=re.S)
    out = []
    for block in re.split(r"\n\s*\n", tex):
        b = " ".join(block.split())
        if _MIN_PARA <= len(b) <= _MAX_PARA and not b.startswith("\\"):
            out.append(b)
    return out


def exemplar_store(backend, exemplar_dir: Path | None = None) -> tuple[list[dict], list]:
    from laplace.research import corpus_ingest as ci
    paras: list[dict] = []
    if exemplar_dir:
        for tf in sorted(exemplar_dir.rglob("*")):
            if tf.suffix.lower() not in (".txt", ".md", ".tex") or not tf.is_file():
                continue
            try:
                rel = str(tf.relative_to(exemplar_dir))     # slug/file — his files are mostly main.tex
            except ValueError:
                rel = tf.name
            for p in tex_paragraphs(tf.read_text(encoding="utf-8", errors="replace")):
                paras.append({"corpus": exemplar_dir.name, "file": rel, "text": p})
    for name in EXEMPLAR_PROJECTS:
        troot = ci.resolve_corpus(ROOT, name)
        if not troot:
            continue
        for tf in sorted(Path(troot).glob("*.tex")):
            for p in tex_paragraphs(tf.read_text(encoding="utf-8", errors="replace")):
                paras.append({"corpus": name, "file": tf.name, "text": p})
    if not paras:
        raise SystemExit(
            "voice_retrieve: NO exemplar prose available. The finished-paper corpora are "
            "PDF-sourced stubs and the raw papers are sealed local. On the author's "
            "machine: extract paragraph text from archive/soul_dump/'my papers'/*.pdf "
            "(pdftotext is fine) into a directory and pass --exemplar-dir <dir>. "
            "Refusing to fall back to a spec-driven voice pass - that is the named "
            "failure mode (canon://skills/voice_descent).")
    cached: dict = {}
    if CACHE.is_file():
        try:
            disk = json.loads(CACHE.read_text(encoding="utf-8"))
            if disk.get("backend") == backend.name:
                cached = disk.get("items", {})
        except (OSError, json.JSONDecodeError):
            pass
    hashes = [hashlib.sha1(p["text"].encode()).hexdigest() for p in paras]
    stale = [i for i, h in enumerate(hashes) if h not in cached]
    if stale:
        vecs = backend.embed([paras[i]["text"] for i in stale])
        for i, v in zip(stale, vecs, strict=True):
            cached[hashes[i]] = v
        CACHE.write_text(json.dumps({"backend": backend.name, "items": cached}),
                         encoding="utf-8")
    import numpy as np
    X = np.asarray([cached[h] for h in hashes], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    return paras, X


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="directory with the projected S*.tex fragments")
    ap.add_argument("--out", default=None)
    ap.add_argument("--top", type=int, default=2)
    ap.add_argument("--exemplar-dir",
                    default=str(DEFAULT_EXEMPLAR_DIR) if DEFAULT_EXEMPLAR_DIR.is_dir() else None,
                    help="directory of the author's paper prose (.txt/.md/.tex); defaults to "
                         "the committed voice_corpus/exemplars/ when present")
    a = ap.parse_args()
    tdir = Path(a.target)
    out = Path(a.out) if a.out else tdir.parent / "voice_briefs"
    out.mkdir(parents=True, exist_ok=True)

    backend = get_backend()
    if backend is None:
        print("no embedding backend"); return 1
    paras, X = exemplar_store(backend, Path(a.exemplar_dir) if a.exemplar_dir else None)
    _src = a.exemplar_dir or EXEMPLAR_PROJECTS
    print(f"exemplar store: {len(paras)} paragraphs from {_src}")

    import numpy as np
    moves = sorted((ROOT / "soul_corpus" / "voice").glob("*.md"))
    moves_txt = "\n".join(
        f"- **{m.stem}**: " + re.sub(r"\s+", " ", re.search(
            r"\*(?:move|stance|value|aesthetic|friction)\*\s*[—-]\s*(.+?)\*\*",
            m.read_text(encoding="utf-8"), re.S).group(1)).strip()
        for m in moves if re.search(
            r"\*(?:move|stance|value|aesthetic|friction)\*\s*[—-]\s*(.+?)\*\*",
            m.read_text(encoding="utf-8"), re.S))

    used: set[int] = set()
    for tf in sorted(tdir.glob("*.tex")):
        if tf.name == "main.tex":
            continue
        passages = tex_paragraphs(tf.read_text(encoding="utf-8", errors="replace"))
        if not passages:
            continue
        Q = np.asarray(backend.embed(passages), dtype=np.float64)
        Q /= np.clip(np.linalg.norm(Q, axis=1, keepdims=True), 1e-12, None)
        S = Q @ X.T
        lines = [f"# Voice brief — {tf.name}", "",
                 "The author's distilled voice moves (the generators; write FROM the "
                 "exemplars below, these name what to listen for):", "", moves_txt, ""]
        for i, ptext in enumerate(passages):
            order = [int(j) for j in np.argsort(-S[i])]
            picks = []
            for j in order:
                if j not in used:
                    picks.append(j)
                    used.add(j)
                if len(picks) >= a.top:
                    break
            lines += [f"## Passage {i + 1}", "", f"> {ptext[:400]}…" if len(ptext) > 400
                      else f"> {ptext}", "", "**His nearest prose (write FROM these):**", ""]
            for j in picks:
                p = paras[j]
                lines += [f"*{p['corpus']}/{p['file']}* (cos {S[i, j]:.2f}):",
                          "", p["text"], ""]
        (out / f"{tf.stem}_voice.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {tf.stem}_voice.md ({len(passages)} passages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
