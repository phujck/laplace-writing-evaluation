"""The orientation probe as a standing module: the economy meter's conjugate.

The cut law (DESIGN_2026-08-08b section 5): at every seam, a cold reader holding only the
bounded local window must be able to state the question being answered and why the block
follows. This module owns the probe's compilation, caps, verdict parsing, and bench
fixtures; the model call itself is dispatched (opus-or-below, explicit stamp), never made
here. The reader.py treatment: architecture enforces the bounded window, so the probe
cannot cheat by holding the whole artefact.

Run: python3 -m laplace.pipeline.writing_organ.probe <manuscript_dir>   (compiles the seam prompts
from the current assembly + breath_report.json and writes probe_prompts/ for dispatch)
"""

from __future__ import annotations

import json
import re
import sys
import pathlib

# The bounded window: what the cold reader holds. Architecturally enforced - the
# compiled prompt physically contains no more than this.
WINDOW_PREV_WORDS = 240
WINDOW_CUR_WORDS = 340

VERDICTS = ("breathing", "adequate", "starved")

PROBE_TEMPLATE = """You are the orientation probe of a physics-manuscript instrument battery. A cold reader holds ONLY the window below - nothing else of the paper. Test whether the seam gives them enough to reconstruct the argument state.

THE SEAM: {seam}.
THE INTENDED SUB-QUESTION of the incoming section (you know it; judge whether the WINDOW alone delivers it): {question}

THE WINDOW (end of previous section, then start of incoming section):
--- previous section, final passage ---
{prev}
--- incoming section, opening passage ---
{cur}
--- end window ---

Answer as the cold reader, in EXACTLY this compact format (no other text):
VERDICT: breathing|adequate|starved
QUESTION_INFERABLE: yes|no
BRIDGE_PRESENT: yes|no
AS_READ: <the sub-question as you would state it from the window alone, one sentence>
MISSING: <the most important thing the seam leaves silent that the reader needs, or 'none', one sentence>"""


def _prose(path: pathlib.Path) -> str:
    text = path.read_text()
    return re.sub(r"(?m)^%.*$", "", text).strip()


def _words(text: str, n: int, tail: bool = False) -> str:
    w = text.split()
    return " ".join(w[-n:] if tail else w[:n])


def compile_probe(seam: str, question: str, prev_text: str, cur_text: str) -> str:
    """The bounded probe prompt. Truncation happens HERE, so no caller can widen the window."""
    return PROBE_TEMPLATE.format(
        seam=seam, question=question,
        prev=_words(prev_text, WINDOW_PREV_WORDS, tail=True),
        cur=_words(cur_text, WINDOW_CUR_WORDS),
    )


def parse_verdict(text: str) -> dict:
    """Parse the probe's compact return. Unknown verdicts surface as 'unparsed', never crash."""
    out = {"verdict": "unparsed", "question_inferable": None, "bridge_present": None,
           "as_read": "", "missing": ""}
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("VERDICT:"):
            v = line.split(":", 1)[1].strip().lower()
            out["verdict"] = v if v in VERDICTS else "unparsed"
        elif line.upper().startswith("QUESTION_INFERABLE:"):
            out["question_inferable"] = line.split(":", 1)[1].strip().lower().startswith("y")
        elif line.upper().startswith("BRIDGE_PRESENT:"):
            out["bridge_present"] = line.split(":", 1)[1].strip().lower().startswith("y")
        elif line.upper().startswith("AS_READ:"):
            out["as_read"] = line.split(":", 1)[1].strip()
        elif line.upper().startswith("MISSING:"):
            out["missing"] = line.split(":", 1)[1].strip()
    return out


def seams_from_assembly(manuscript_dir: pathlib.Path, order: list[tuple[str, str, str]]) -> list[dict]:
    """Build seam records from an ordered assembly: [(name, filename, question), ...]."""
    seams = []
    for i in range(len(order) - 1):
        pn, pf, _ = order[i]
        cn, cf, cq = order[i + 1]
        seams.append({
            "seam": f"{pn}->{cn}", "question": cq,
            "prompt": compile_probe(f"{pn}->{cn}", cq,
                                    _prose(manuscript_dir / pf), _prose(manuscript_dir / cf)),
        })
    return seams


def load_fixtures(repo_root: pathlib.Path) -> list[dict]:
    """The labelled bench: seam windows with expected verdicts, banked from the breathing
    rounds (evidence/breathing_round_2026-08-08/). A probe change is benched by re-running
    these prompts and comparing verdict agreement - the Gate-1 discipline."""
    p = repo_root / "evidence" / "breathing_round_2026-08-08" / "probe_fixtures.json"
    return json.loads(p.read_text()) if p.exists() else []


def main() -> int:
    md = pathlib.Path(sys.argv[1])
    manifest = json.loads((md / "battery_manifest.json").read_text())
    order = [(s["name"], s["file"], s["question"]) for s in manifest["sections"]]
    seams = seams_from_assembly(md, order)
    out = md / "probe_prompts"
    out.mkdir(exist_ok=True)
    for s in seams:
        (out / (s["seam"].replace("->", "_") + ".txt")).write_text(s["prompt"])
    print(f"compiled {len(seams)} seam probes -> {out} (dispatch opus-or-below, explicit stamp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
