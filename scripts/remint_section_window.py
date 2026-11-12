#!/usr/bin/env python3
"""remint_section_window.py — RE-MINT ``section_architecture`` ``embed_text`` under the widened
window, so the elided middle stops swallowing his arcana.

WO-20260820-section-window-caps-the-arcana. With the extraction lens repaired
(WO-20260820-extraction-lens-keeps-math, RESOLVED at b17378c2) the numbers survive the strip — and
are then thrown away by the WINDOW. Measured on ``SA-nuodfgnl-s2``: ``L=10`` and ``t_0=0.52`` eV
sit in the 600-char head, while ``\\omega_0 = 32.7`` THz, ``a=4\\AA``, ``F_0=10`` MV/cm, ``QuSpin``
and ``SCOOP`` all sit in the elided middle. ``section_bridge._prose_window`` now carries a third
band — the SALVAGE band — and fits the result to the EMBEDDER's own 512-token window, which was
never checked and was already cutting two rows silently.

WHY IN PLACE, not a rebuild — unchanged from ``remint_lens_math.py``: the store carries MODEL
RESIDUE folded in by the reader merges (``arc`` / ``question_class`` / ``normalized_job``), and
re-running the corpus driver would mint a fresh mechanical skeleton and DESTROY it. This re-mint
refreshes exactly one field per row — ``embed_text`` — from the row's OWN provenance
(``span_ref.{file,char_start,char_end}``, raw tex offsets the bridge stamps).

THE SAFETY GATE. Before writing anything, every row is re-derived under the PREVIOUS window rule —
:func:`_prose_window_v1`, lifted verbatim from ``section_bridge`` at HEAD 41966f26 — and required
to reproduce the STORED ``embed_text`` byte-for-byte. A row that fails is not the row this script
thinks it is: it is REPORTED and SKIPPED, and nothing is written for its store. Nothing is written
unless the store's own text is reproducible from its own provenance.

AFTER THIS SCRIPT the store's vectors are stale by construction and its gate verdict with them:

    .venv/bin/python scripts/remint_section_window.py          # re-mint + re-embed
    .venv/bin/python scripts/regate_stores.py --rewrite        # re-derive the stamped verdicts

Usage:
    .venv/bin/python scripts/remint_section_window.py --dry-run   # report only, write nothing
    .venv/bin/python scripts/remint_section_window.py --no-embed  # re-mint, leave vectors stale
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from laplace.engine import voice_corpus_ingest as vci  # noqa: E402
from laplace.pipeline import section_bridge  # noqa: E402

STORES_ROOT = _REPO_ROOT / "corpus_stores"
STORE = "section_architecture"

#: The provenance stamp naming the window an ``embed_text`` was produced by. A row without it was
#: written by the head+tail rule that elided its middle (the defect this work order names).
TEXT_WINDOW = "prose_window(salvage+model_window_fit)"


# --------------------------------------------------------------------------- #
# the PREVIOUS rule, frozen — the safety gate's reference, never edited again
# --------------------------------------------------------------------------- #
_HEAD_V1, _TAIL_V1, _WINDOW_ABOVE_V1 = 600, 600, 1300


def _prose_window_v1(prose: str) -> str:
    """``section_bridge._prose_window`` as it stood at HEAD 41966f26 — head + tail, middle elided,
    budgeted in prose. Lifted VERBATIM: this is what the stored rows were written by, so it is what
    the safety gate must reproduce them with. It is a frozen reference, not a live rule."""
    plain = vci.demath(prose)
    if plain == prose:
        return ((prose[:_HEAD_V1] + " ... " + prose[-_TAIL_V1:])
                if len(prose) > _WINDOW_ABOVE_V1 else prose)

    units: list[tuple[str, int]] = []
    for is_math, chunk in vci.math_segments(prose):
        if is_math:
            units.append((chunk, 0))
        else:
            for w in chunk.split(" "):
                if w:
                    units.append((w, len(w) + 1))
    if sum(c for _, c in units) - 1 <= _WINDOW_ABOVE_V1:
        return prose

    def take(seq: list[tuple[str, int]], cap: int) -> list[str]:
        out: list[str] = []
        used = 0
        for tok, c in seq:
            if used + c > cap:
                break
            out.append(tok)
            used += c
        return out

    head = take(units, _HEAD_V1)
    tail = list(reversed(take(list(reversed(units)), _TAIL_V1)))
    return " ".join(head) + " ... " + " ".join(tail)


def _prose(block: str) -> str:
    """The bridge's own text rule up to the window (``strip_latex(keep_math=True)``, collapsed)."""
    return " ".join(vci.strip_latex(block, keep_math=True).split())


# --------------------------------------------------------------------------- #
# the re-mint
# --------------------------------------------------------------------------- #
def _load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def remint(*, dry_run: bool) -> dict[str, Any]:
    store_dir = STORES_ROOT / STORE
    report: dict[str, Any] = {"store": STORE, "papers": [], "rows": 0, "changed": 0,
                              "unreproducible": [], "unresolved": [], "grew": 0, "shrank": 0}
    raw: dict[str, str] = {}

    for path in sorted(store_dir.glob("*.jsonl")):
        rows = _load(path)
        changed = 0
        for row in rows:
            report["rows"] += 1
            sr = row.get("provenance", {}).get("span_ref") or {}
            f = sr.get("file")
            if not f or not (_REPO_ROOT / f).is_file():
                report["unresolved"].append({"row_id": row.get("row_id"), "why": f"no source: {f}"})
                continue
            if f not in raw:
                raw[f] = (_REPO_ROOT / f).read_text(encoding="utf-8", errors="ignore")
            prose = _prose(raw[f][int(sr["char_start"]):int(sr["char_end"])])
            old_text = _prose_window_v1(prose)

            # THE SAFETY GATE: the stored text must be reproducible from the row's own provenance.
            if row.get("embed_text") != old_text:
                report["unreproducible"].append({"row_id": row.get("row_id"), "file": f})
                continue

            new_text = section_bridge._prose_window(prose)
            if new_text != old_text:
                changed += 1
                report["grew" if len(new_text) > len(old_text) else "shrank"] += 1
            row["embed_text"] = new_text
            row["provenance"]["span_ref"]["text_window"] = TEXT_WINDOW

        report["changed"] += changed
        report["papers"].append({"paper": path.stem, "rows": len(rows), "changed": changed})
        if not dry_run and not report["unreproducible"]:
            _write(path, rows)
    return report


def reembed() -> dict[str, Any]:
    """Re-embed the re-minted store — ``embed_text`` moved, so ``embeddings.json`` is stale by
    construction. Uses the SAME local ONNX backend the store was built with."""
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import demo_stage_stores as demo  # noqa: E402  (the one embedding path, reused verbatim)
    from laplace.representation.embed_router import get_backend  # noqa: E402

    backend = get_backend()
    if backend is None:
        return {"store": STORE, "embedded": False, "why": "no local embedding backend"}
    rows: list[dict[str, Any]] = []
    for p in sorted((STORES_ROOT / STORE).glob("*.jsonl")):
        rows.extend(_load(p))
    emb = demo.embed_store(STORE, rows, backend)
    return {"store": STORE, "embedded": True, "rows": len(rows), "vectors": len(emb)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--no-embed", action="store_true", help="skip the re-embed")
    args = ap.parse_args()

    print(f"# remint_section_window — carry the middle's arcana "
          f"({'DRY RUN' if args.dry_run else 'WRITING'})")
    rep = remint(dry_run=args.dry_run)
    print(f"\n{STORE}: {rep['rows']} rows, {rep['changed']} changed "
          f"({rep['grew']} wider, {rep['shrank']} fitted to the model window; "
          f"{len(rep['unreproducible'])} unreproducible, {len(rep['unresolved'])} unresolved)")
    for p in rep["papers"]:
        print(f"  {p['paper']:<58} {p['changed']:>4}/{p['rows']}")
    for u in rep["unreproducible"][:10]:
        print(f"  ! UNREPRODUCIBLE {u['row_id']} ({u['file']})")
    for u in rep["unresolved"][:10]:
        print(f"  ! UNRESOLVED {u['row_id']}: {u['why']}")

    if rep["unreproducible"]:
        return 1
    if not args.dry_run and not args.no_embed:
        print("\n" + json.dumps(reembed()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
