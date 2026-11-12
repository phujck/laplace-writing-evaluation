"""The tension panel: the organ's judgement layer, above the mechanical meters.

His meta-law (gm-007, DESIGN_2026-08-08b section 10): corrections are samples of one
judgement, not statutes; register is physics, all physics; a defect is one element
locally beating another, and the verdict quotes where. This module compiles the panel
prompt from the two-sided calibration pool (calibration_pool.json) so no pole is judged
blind; the model calls are dispatched (opus-or-below, explicit stamp), never made here.

Run: python3 -m laplace.pipeline.writing_organ.panel <file.tex> [...]   (prints the compiled prompt)
"""

from __future__ import annotations

import json
import sys
import pathlib

POOL_PATH = pathlib.Path(__file__).with_name("calibration_pool.json")

PANEL_TEMPLATE = """You are one judge on a tension panel for a physics manuscript. Your job is NOT rule-checking against banned-word lists - it is judgement: for each element-pair below, decide whether the tension is balanced or one pole is locally beating the other, and quote where.

THE ELEMENTS IN TENSION:
{elements}

THE AUTHOR'S CALIBRATION (verdicts sampling his judgement, BOTH directions of every tension - a pole can lose either way):
{exemplars}

STANDING LAWS:
{laws}

THE PASSAGE(S):
{text}

Return EXACTLY this format per section:
SECTION: <name>
<for each element 1-{n}: one line "N BALANCED" or "N <losing pole> LOSES: '<quoted words, <=15>' - <one-clause diagnosis>">
WORST SENTENCE: '<quote>' - <why it most needs the author's attention>
ONE MOVE: <the single highest-value change, one sentence>"""


#: the tag unplaced verdicts compile under. Rows the mechanical fold (pool_fold.py) could
#: not confidently assign a side still reach the judges under this tag rather than waiting
#: for a hand to place them.
UNPLACED_TAG = "unplaced - his verdict"

#: the panel is a prompt, not the archive. A hand-typed exemplar is one line; a folded
#: ledger row can be a page, and a page of one verdict buries twenty samples of the rest
#: of his judgement. Every line enters at this width. The pool file keeps the verdict
#: whole beside its row id, so the receipt stays complete while the prompt stays bounded.
MAX_EXEMPLAR_CHARS = 280

#: how many unplaced verdicts reach one panel: the most recent, up to this many. Unplaced
#: entries are one-sided by construction - nothing decided which pole they sample - so an
#: unbounded block of them is the calibration failure the two-sided pool exists to fix.
MAX_PENDING = 8


def load_pool(path: pathlib.Path | None = None) -> dict:
    """The pool, read as UTF-8. His verdicts carry the characters his sources carry, and
    the fold writes them; the platform default encoding decodes them wrong or not at
    all."""
    return json.loads((path or POOL_PATH).read_text(encoding="utf-8"))


ELISION = " [...] "


def _excerpt(text: str, limit: int = MAX_EXEMPLAR_CHARS) -> str:
    """One line of roughly ``limit`` characters, paragraph breaks flattened. What is cut
    is the middle, never an end: a folded entry runs ``'the passage' -> 'his replacement'
    - his note``, so a head cut would keep the prose he rejected and drop the prose he
    wrote. Both ends survive; the elision marks what sits between them."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head_budget = 2 * limit // 3
    head = text[:head_budget]
    end = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
    head = head[:end + 1] if end >= head_budget // 2 else head.rsplit(" ", 1)[0]
    tail = text[-(limit - head_budget):]
    return head + ELISION + (tail.split(" ", 1)[-1] if " " in tail else tail)


def _entry_text(entry) -> str:
    """One exemplar's words. A hand-typed entry is a plain string; a folded entry is
    ``{text, from, ts, ledger}`` carrying its ledger provenance. Both render as the same
    line, at the same width."""
    if isinstance(entry, str):
        return _excerpt(entry.strip())
    if isinstance(entry, dict):
        return _excerpt(str(entry.get("text") or "").strip())
    return ""


def compile_panel(text: str, pool: dict | None = None) -> str:
    pool = pool or load_pool()
    elements = "\n".join(f"{i+1}. {e['pair'].upper().replace('_', ' ')}: {e['law']}"
                         for i, e in enumerate(pool["elements"]))
    lines = [f"[{side}] {t}"
             for side, vs in pool["exemplars"].items()
             for t in (_entry_text(v) for v in vs) if t]
    pending = (pool.get("pending_exemplars") or [])[-MAX_PENDING:]
    lines += [f"[{UNPLACED_TAG}] {t}"
              for t in (_entry_text(v) for v in pending) if t]
    exemplars = "\n".join(lines)
    laws = "\n".join(f"- {l}" for l in pool["standing_laws"])
    return PANEL_TEMPLATE.format(elements=elements, exemplars=exemplars, laws=laws,
                                 text=text, n=len(pool["elements"]))


def main() -> int:
    text = "\n\n".join(pathlib.Path(a).read_text(encoding="utf-8") for a in sys.argv[1:])
    print(compile_panel(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
