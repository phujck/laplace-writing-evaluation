"""The generic gate runner for loop-kind projects — the paper_gates.py collapse.

The bespoke path (``scripts/paper_gates.py`` + ``assemble_section_bundle.py`` +
``paper_foldback.py``, archived under ``scripts/_archive/`` 2026-07-08)
hardcoded its banned-jargon/constructions lists, loop dir, and section count.
Those are now DATA in the registry: the paper_eigen entry's ``gates_profile``
carries the lists and section count, ``loop_dir`` carries the loop directory,
and this module is the one runner any loop-kind project rides.

The checks reproduce the archived script's verdicts exactly (held to it by the
golden-master test): (a) NUMBER DIFF — every numeral in a draft appears
verbatim in a cited claim text, every [Cn] tag resolves, every [@key] cite is
allowed; (b) REGISTER — banned constructions over the prose surface;
(c) DIALECT ORDER — over the assembled full draft, each coined term is
bold-taught before use and banned internal jargon never appears. As the
archived script did, the runner also assembles ``<loop>/draft_full.md``
(mechanical concatenation in ladder order) for the whole-object passes.
Foldback (the embedding-backed projection pass) stays a separate, archived
concern — these gates are free, mechanical, model-less.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from laplace.pipeline import registry


def prose_of(text: str) -> str:
    """The judged surface: body prose only — header lines, HTML comment blocks
    (friction reports), claim tags, and citation groups are masked first."""
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    body = "\n".join(l for l in body.splitlines() if not l.startswith("## "))
    body = re.sub(r"\[C\d+\]", "", body)
    body = re.sub(r"\[@[^\]]+\]", "", body)
    return body


def numerals(text: str) -> set[str]:
    """Pure digit-runs in the prose — formatting-independent."""
    return set(re.findall(r"\d+", prose_of(text)))


def run_gates(project: str, repo_root: Path | str | None = None,
              write_draft: bool = False) -> dict:
    """Run the mechanical gates for a loop-kind project, driven entirely by its
    registry record. Returns the report dict (the archived script printed it).

    Pure reporter by default: the whole-object passes read the in-memory
    concatenation, never the file. Only ``write_draft=True`` materialises
    ``<loop>/draft_full.md`` — a caller opts in when it consumes the assembled
    draft downstream."""
    proj = registry.resolve(project)
    if proj is None:
        return {"error": f"unknown project {project!r}"}
    if proj.kind != "loop" or not proj.gates_profile or not proj.loop_dir:
        return {"error": f"project {project!r} is not a gated loop project "
                         f"(kind={proj.kind!r}, gates_profile "
                         f"{'set' if proj.gates_profile else 'empty'})"}
    prof = proj.gates_profile
    loop = proj.path(proj.loop_dir, Path(repo_root) if repo_root else None)
    n_sections = int(prof["sections"])
    banned_jargon = list(prof["banned_jargon"])
    banned_constructions = [tuple(x) for x in prof["banned_constructions"]]

    report: dict = {"sections": {}, "full": {}}
    full_parts: list[str] = []
    for n in range(1, n_sections + 1):
        draft_p, bundle_p = loop / f"draft_{n}.md", loop / f"bundle_{n}.json"
        if not draft_p.is_file():
            report["sections"][n] = {"error": "draft missing"}
            continue
        draft = draft_p.read_text(encoding="utf-8")
        bundle = json.loads(bundle_p.read_text(encoding="utf-8"))
        full_parts.append(draft.strip())

        claim_text = " ".join(bundle["claims"].values())
        claim_nums = set(re.findall(r"\d+", claim_text))
        orphan_nums = sorted(numerals(draft) - claim_nums)

        tags = set(re.findall(r"\[(C\d+)\]", draft))
        bad_tags = sorted(tags - set(bundle["claims"]))
        cites = set(re.findall(r"\[@([\w:]+)\]", draft))
        bad_cites = sorted(cites - set(bundle["cites_allowed"]))

        constructions = []
        prose = prose_of(draft)
        for name, pat in banned_constructions:
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
    if write_draft:
        (loop / "draft_full.md").write_text(full, encoding="utf-8")

    # the lexicon ladder over the whole object: taught-before-used, bold on first use
    lexicon = []
    for n in range(1, n_sections + 1):
        b = json.loads((loop / f"bundle_{n}.json").read_text(encoding="utf-8"))
        for t in b["lexicon"]["to_teach"]:
            lexicon.append((t["term"], n))
    lex_report: dict[str, str] = {}
    section_starts: dict[int, int] = {}
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
            status.append(f"USED-BEFORE-TAUGHT (first at char {first}, "
                          f"teaching section starts {taught_at})")
        if not bold:
            status.append("first use not bold-taught")
        lex_report[term] = " / ".join(status) if status else "ok"
    low_prose = prose_of(full).lower()
    jargon_hits = {j: len(re.findall(rf"\b{re.escape(j)}\b", low_prose))
                   for j in banned_jargon}
    report["full"] = {
        "words": len(full.split()),
        "lexicon_ladder": lex_report,
        "banned_jargon": {k: v for k, v in jargon_hits.items() if v},
    }
    return report
