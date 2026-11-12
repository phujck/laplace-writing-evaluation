"""adjudicate.py - the blind adjudicator's mechanical proxy (third role of the loop).

The self-judgement loop is tripartite: a **digester** (has the original, writes the digest), a
**ghost** (sees the digest only, reconstructs), and an **adjudicator** (sees the original and the
ghost ONLY, judges similarity). The adjudicator must be as blind as the ghost - it gets neither the
digest, nor the conceptric, nor any session context - because a judge that shares the maker's
context scores self-consistency, not fidelity (the same curse blind_reader / orchestrated_generation
name). This script is the adjudicator's *mechanical proxy*: it accepts exactly two artifacts and
nothing else - the interface IS the context-wall - and computes a cheap similarity signal plus the
crude gap (content present in the original but missing from the ghost, and content asserted by the
ghost but absent from the original - the confabulation candidates). The real semantic verdict is a
blind agent's; this proxy is the shape of the data we collect now, ahead of the converger.

Usage:
    python adjudicate.py <original.md> <ghost.md> [--target <id>] [--cycle N] [--no-log]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[6]

_STOP = {"the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "to", "of", "in",
         "on", "for", "it", "its", "as", "at", "by", "that", "this", "with", "from", "not", "so",
         "we", "you", "i", "he", "she", "they", "do", "does", "did", "can", "will", "would", "if"}


def _toks(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 2]


def _shingles(toks: list[str], k: int = 2) -> set[tuple]:
    return {tuple(toks[i:i + k]) for i in range(len(toks) - k + 1)} if len(toks) >= k else set()


def adjudicate(original: str, ghost: str) -> dict:
    """Compare two artifacts blind. Returns similarity + the salient lost / added content."""
    o_toks, g_toks = _toks(original), _toks(ghost)
    o_set, g_set = set(o_toks), set(g_toks)
    # Jaccard over 2-shingles: rewards shared *phrasing*, not just shared vocabulary.
    o_sh, g_sh = _shingles(o_toks), _shingles(g_toks)
    inter = o_sh & g_sh
    union = o_sh | g_sh
    similarity = round(len(inter) / len(union), 4) if union else 0.0

    # Salient lost / added: content tokens unique to one side, by frequency in that side.
    def _rank(only: set[str], toks: list[str], n: int = 12) -> list[str]:
        freq: dict[str, int] = {}
        for t in toks:
            if t in only:
                freq[t] = freq.get(t, 0) + 1
        return [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:n]]

    lost = _rank(o_set - g_set, o_toks)        # in original, absent from ghost (lost in digest)
    added = _rank(g_set - o_set, g_toks)       # in ghost, absent from original (confabulation risk)

    # Proxy fate band - the real verdict is the blind agent's; this is the cheap signal.
    if similarity >= 0.35:
        proxy = "faithful"
    elif similarity >= 0.12:
        proxy = "partial"
    else:
        proxy = "confabulated"
    return {"similarity": similarity, "proxy_fate": proxy, "lost": lost, "added": added}


def _telemetry():
    try:
        from laplace.engine import telemetry  # type: ignore
        return telemetry
    except Exception:
        sys.path.insert(0, str(_REPO / "src"))
        from laplace.engine import telemetry  # type: ignore
        return telemetry


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    original = Path(args[0]).read_text(encoding="utf-8", errors="replace")
    ghost = Path(args[1]).read_text(encoding="utf-8", errors="replace")
    target = argv[argv.index("--target") + 1] if "--target" in argv else Path(args[0]).stem
    cycle = int(argv[argv.index("--cycle") + 1]) if "--cycle" in argv else 0
    do_log = "--no-log" not in argv

    r = adjudicate(original, ghost)
    print(f"# Adjudication (mechanical proxy): {target}  cycle {cycle}")
    print("*" * 50)
    print(f"Similarity (2-shingle Jaccard): {r['similarity']}   proxy fate: {r['proxy_fate']}")
    print(f"Lost (in original, absent from ghost): {', '.join(r['lost']) or '(none)'}")
    print(f"Added (in ghost, absent from original - confab risk): {', '.join(r['added']) or '(none)'}")
    print("Note: this is the proxy. The real verdict is a BLIND agent given only {original, ghost}.")

    if do_log:
        try:
            tel = _telemetry()
            gap = "lost: " + ", ".join(r["lost"][:6]) if r["lost"] else ""
            tel.reconstruction(fate=r["proxy_fate"], target=str(target), caller="adjudicator-mechanical",
                               cycle=cycle, similarity=r["similarity"], gap=gap)
        except Exception as e:
            print(f"(telemetry not logged: {e})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
