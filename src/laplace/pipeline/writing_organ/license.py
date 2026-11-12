"""The sentence license as a standing instrument: two tiers, mechanical and judged.

The cut law (DESIGN_2026-08-08b section 1): every sentence deposits a node or realises an
edge in its seam's cut; what does neither is filler. The meta-law of section 10 binds this
module's design: the MECHANICAL tier flags only the closed class of reflexive phrases
(process narration and assurance markers that are filler in every register), never taste;
everything else is the JUDGED tier - a compiled audit prompt for a dispatched model, with
the verdict naming counts and quoting every filler sentence. Rules are demoted to
calibration exemplars; judgement carries the law.

Run: python3 -m laplace.pipeline.writing_organ.license <file.tex> [...]   (mechanical tier only)
"""

from __future__ import annotations

import re
import sys
import pathlib

# The closed class. Additions require a banked ruling; this list is not a style opinion,
# it is the set of phrases already ruled filler in every context they appeared.
REFLEXIVE = re.compile(
    r"\b(?:we now turn to|in this (?:section|paper) we|it is worth noting|"
    r"note that|importantly|notably|as discussed above|as mentioned (?:above|earlier))\b",
    re.IGNORECASE,
)

AUDIT_TEMPLATE = """Audit this physics passage sentence by sentence against the sentence license. For each sentence decide: NODE (deposits a claim/result/definition), EDGE (realises an open dependency: names the question being answered, says why a block follows, states what a relation physically means for something downstream, hands off to a next question), or FILLER (neither: process narration, assurance, restatement of discharged material at no compression gain, generic transition naming no specific content). Count each class. Quote every FILLER sentence with the reason. license_clean = zero filler.

CALIBRATION (verdicts of the author, both directions - the license fails BOTH ways):
{calibration}

THE PASSAGE:
{text}

Return EXACTLY: SENTENCES: n | NODE: n | EDGE: n | FILLER: n, then one line per filler quote, then VERDICT: CLEAN or n ISSUES."""


def mechanical_tier(text: str) -> list[dict]:
    """The closed-class pass: cheap, deterministic, zero false judgement."""
    text = re.sub(r"(?m)^%.*$", "", text)
    hits = []
    for m in REFLEXIVE.finditer(text):
        start = max(0, m.start() - 60)
        hits.append({"phrase": m.group(0), "context": text[start:m.end() + 60].replace("\n", " ")})
    return hits


def compile_license_audit(text: str, calibration: str) -> str:
    """The judged tier's prompt. Dispatch opus-or-below with an explicit stamp."""
    return AUDIT_TEMPLATE.format(calibration=calibration, text=text)


def main() -> int:
    total = 0
    for arg in sys.argv[1:]:
        p = pathlib.Path(arg)
        hits = mechanical_tier(p.read_text())
        total += len(hits)
        for h in hits:
            print(f"{p.name}: [{h['phrase']}] ...{h['context']}...")
    print(f"mechanical tier: {total} reflexive hit(s)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
