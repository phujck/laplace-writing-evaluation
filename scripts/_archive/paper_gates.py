"""The mechanical gates for the paper_eigen writing loop (discipline rules 2, 3, 5).

Run over the section drafts in paper_eigen/_loop/: (a) NUMBER DIFF - every numeral in a draft
must appear verbatim in one of its bundle's cited claim texts, and every [Cn] tag must point at
a claim the bundle carries; (b) DIALECT ORDER - over the assembled full draft, every coined
term's first use must be its bold-marked teaching, and no term may appear before the section
that teaches it; banned internal jargon must not appear at all; (c) REGISTER - banned
constructions (em-dash, semicolon in prose, announcement openers). Also assembles
_loop/draft_full.md (mechanical concatenation in ladder order) for the whole-object passes.

Output: JSON report to stdout. Free, seconds, no model anywhere.
"""
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
LOOP = ROOT / "paper_eigen" / "_loop"

BANNED_JARGON = ["keeper", "spine", "dreamer", "sew-up", "salience", "regrade",
                 "conceptric ledger", "soul"]
BANNED_CONSTRUCTIONS = [("em-dash", "—"), ("semicolon", "; "),
                        ("announcement", "in this section"), ("announcement", "this section ")]


def prose_of(text: str) -> str:
    """The judged surface: body prose only - header line, HTML comment blocks (friction
    reports), claim tags, and citation groups are not prose and are masked first."""
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    body = "\n".join(l for l in body.splitlines() if not l.startswith("## "))
    body = re.sub(r"\[C\d+\]", "", body)
    body = re.sub(r"\[@[^\]]+\]", "", body)
    return body


def numerals(text: str) -> set[str]:
    """Pure digit-runs in the prose - formatting-independent so 6→15→46 and
    '6 then 15 then 46' compare equal."""
    return set(re.findall(r"\d+", prose_of(text)))


def main() -> int:
    report = {"sections": {}, "full": {}}
    full_parts = []
    for n in range(1, 9):
        draft_p, bundle_p = LOOP / f"draft_{n}.md", LOOP / f"bundle_{n}.json"
        if not draft_p.is_file():
            report["sections"][n] = {"error": "draft missing"}
            continue
        draft = draft_p.read_text(encoding="utf-8")
        bundle = json.loads(bundle_p.read_text(encoding="utf-8"))
        full_parts.append(draft.strip())

        claim_text = " ".join(bundle["claims"].values())
        claim_nums = set(re.findall(r"\d+", claim_text))
        draft_nums = numerals(draft)
        orphan_nums = sorted(draft_nums - claim_nums)

        tags = set(re.findall(r"\[(C\d+)\]", draft))
        bad_tags = sorted(tags - set(bundle["claims"]))
        cites = set(re.findall(r"\[@([\w:]+)\]", draft))
        bad_cites = sorted(cites - set(bundle["cites_allowed"]))

        constructions = []
        prose = prose_of(draft)
        for name, pat in BANNED_CONSTRUCTIONS:
            k = prose.lower().count(pat.lower())
            if k:
                constructions.append(f"{name} x{k}")

        report["sections"][n] = {
            "words": len(draft.split()),
            "orphan_numerals": orphan_nums,
            "bad_claim_tags": bad_tags,
            "bad_citekeys": bad_cites,
            "banned_constructions": constructions,
            "friction_blocks": draft.count("FRICTION"),
        }

    full = "\n\n".join(full_parts) + "\n"
    (LOOP / "draft_full.md").write_text(full, encoding="utf-8")

    # the lexicon ladder over the whole object: taught-before-used, bold on first use
    lexicon = []
    for n in range(1, 9):
        b = json.loads((LOOP / f"bundle_{n}.json").read_text(encoding="utf-8"))
        for t in b["lexicon"]["to_teach"]:
            lexicon.append((t["term"], n))
    lex_report = {}
    section_starts = {}
    pos = 0
    masked_parts = [re.sub(r"<!--.*?-->", "", p, flags=re.S) for p in full_parts]
    for part in masked_parts:
        m = re.match(r"## (\d+)\.", part)
        if m:
            section_starts[int(m.group(1))] = pos
        pos += len(part) + 2
    low = "\n\n".join(masked_parts).lower()
    for term, taught_in in lexicon:
        first = low.find(term.lower())
        if first < 0:
            lex_report[term] = "UNUSED"
            continue
        taught_at = section_starts.get(taught_in, 0)
        bold = f"**{term.lower()}" in low[max(0, first - 2):first + len(term) + 2] or \
               low[max(0, first - 2):first] == "**"
        status = []
        if first < taught_at:
            status.append(f"USED-BEFORE-TAUGHT (first at char {first}, teaching section starts {taught_at})")
        if not bold:
            status.append("first use not bold-taught")
        lex_report[term] = " / ".join(status) if status else "ok"
    low_prose = prose_of(full).lower()
    jargon_hits = {j: len(re.findall(rf"\b{re.escape(j)}\b", low_prose)) for j in BANNED_JARGON}
    report["full"] = {
        "words": len(full.split()),
        "lexicon_ladder": lex_report,
        "banned_jargon": {k: v for k, v in jargon_hits.items() if v},
    }
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
