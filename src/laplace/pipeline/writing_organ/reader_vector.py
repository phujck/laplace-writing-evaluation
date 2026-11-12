"""Vectorised comprehension: the mechanical half of the bounded reader, no model in the loop.

Embeds paragraphs (fastembed, same substrate as the meaning tree) and computes:
  novelty curve   - prefix novelty per paragraph; near-zero = repetition/empty prose
  duplicate pairs - cross-section near-duplicates (the told-three-times detector)
  return map      - topic re-entries after absence (fragmentation as a number)
  forward refs    - \\ref before \\label, lexical, zero models
  economy         - marginal novelty per token

This is the cheap inner-loop fitness for the draft->score->rewrite convergence loop:
draft -> vector-score -> rewrite failing spans -> rescore -> converge. The LLM reader
and the claim auditor remain the expensive gates at entry and exit; vectors cannot see
wrong derivations or register.

Run: python3 -m laplace.pipeline.writing_organ.reader_vector <manuscript_dir> <file1.tex> <file2.tex> ...
"""

from __future__ import annotations

import re
import sys
import pathlib

import numpy as np

PARA_ANCHOR = re.compile(r"^%\s*([\w:./-]+-p\d+)\s*$", re.MULTILINE)
CMD = re.compile(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?|\{|\}|\$|%.*")
REF = re.compile(r"\\(?:eq)?ref\{([^}]+)\}")
LABEL = re.compile(r"\\label\{([^}]+)\}")


def paragraphs(tex: str, fname: str) -> list[tuple[str, str]]:
    pieces = PARA_ANCHOR.split(tex)
    out = []
    if len(pieces) > 1:
        for i in range(1, len(pieces) - 1, 2):
            body = pieces[i + 1].strip()
            if body:
                out.append((pieces[i], body))
        tail = pieces[-1].strip() if len(pieces) % 2 == 0 else None
    else:
        for j, block in enumerate(p for p in tex.split("\n\n") if p.strip()):
            out.append((f"{fname}-blk{j:02d}", block))
    return out


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", CMD.sub(" ", text)).strip()


def embed(texts: list[str]) -> np.ndarray:
    from fastembed import TextEmbedding
    model = TextEmbedding("BAAI/bge-small-en-v1.5")
    vecs = np.array(list(model.embed(texts)))
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


def analyse(files: list[pathlib.Path]) -> dict:
    paras, ref_positions, label_positions = [], [], {}
    pos = 0
    for f in files:
        tex = f.read_text()
        file_first_pos = pos
        for m in LABEL.finditer(tex):
            label_positions.setdefault(m.group(1), file_first_pos)
        for anchor, body in paragraphs(tex, f.stem):
            for m in REF.finditer(body):
                ref_positions.append((pos, m.group(1), anchor))
            p = plain(body)
            if len(p.split()) >= 5:
                paras.append((anchor, p))
                pos += 1
    texts = [p for _, p in paras]
    E = embed(texts)
    S = E @ E.T

    novelty, flags = [], []
    for i in range(len(paras)):
        n = 1.0 if i == 0 else float(1 - S[i, :i].max())
        novelty.append(n)
        if i and n < 0.10:
            j = int(S[i, :i].argmax())
            flags.append(("repetition", paras[i][0],
                          f"novelty {n:.3f}; near-duplicates {paras[j][0]} (cos {S[i,j]:.3f})"))

    dupes = [("duplicate-pair", paras[i][0],
              f"~= {paras[j][0]} (cos {S[i,j]:.3f}), {j - i} paragraphs apart")
             for i in range(len(paras)) for j in range(i + 1, len(paras))
             if S[i, j] > 0.92 and j - i > 3]

    k = min(8, len(paras))
    from scipy.cluster.vq import kmeans2
    _, assign = kmeans2(E, k, minit="++", seed=7)
    returns, seen, absent = [], set(), set()
    prev = None
    for i, c in enumerate(assign):
        c = int(c)
        if c != prev:
            if c in seen and c in absent:
                returns.append(("topic-return", paras[i][0], f"re-enters topic cluster {c}"))
            if prev is not None:
                absent.add(prev)
            seen.add(c)
            absent.discard(c)
        prev = c

    fwd = [("forward-ref", anchor, f"\\ref{{{key}}} at paragraph {p} but label "
            + ("undefined in scanned files" if key not in label_positions else f"defined at paragraph {label_positions[key]}"))
           for p, key, anchor in ref_positions
           if key not in label_positions or label_positions[key] > p]

    words = [len(t.split()) for t in texts]
    economy = [(paras[i][0], novelty[i] / max(words[i], 1) * 1000) for i in range(len(paras))]

    return {"paras": [a for a, _ in paras], "novelty": novelty, "flags": flags,
            "dupes": dupes, "returns": returns, "forward_refs": fwd,
            "economy": economy, "total_words": sum(words)}


def report(r: dict) -> str:
    lines = [f"paragraphs {len(r['paras'])}  words {r['total_words']}"]
    lines.append(f"repetition flags (novelty < 0.10): {len(r['flags'])}")
    for kind, anchor, detail in r["flags"]:
        lines.append(f"  {anchor}: {detail}")
    lines.append(f"cross-section near-duplicates (cos > 0.92, >3 apart): {len(r['dupes'])}")
    for kind, anchor, detail in r["dupes"][:12]:
        lines.append(f"  {anchor} {detail}")
    lines.append(f"topic returns (fragmentation): {len(r['returns'])}")
    for kind, anchor, detail in r["returns"]:
        lines.append(f"  {anchor}: {detail}")
    lines.append(f"forward references: {len(r['forward_refs'])}")
    for kind, anchor, detail in r["forward_refs"][:12]:
        lines.append(f"  {anchor}: {detail}")
    worst = sorted(r["economy"], key=lambda x: x[1])[:8]
    lines.append("lowest marginal-novelty-per-token paragraphs (economy):")
    for anchor, e in worst:
        lines.append(f"  {anchor}: {e:.2f}")
    return "\n".join(lines)


def main() -> int:
    base = pathlib.Path(sys.argv[1])
    files = [base / f for f in sys.argv[2:]]
    print(report(analyse(files)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
