"""The mechanical bundle assembler — paper_eigen writing loop, discipline rule 1.

A section's drafter sees ONLY its bundle. This script builds each bundle from mechanical
sources: the outline rung (OUTLINE_SEED.md ladder, embedded spec), the cited CLAIMS_LEDGER
entries verbatim (the only place numbers may come from), the blueprint beats verbatim (the
blind-read-closed spine), the network's reach for the section's goal (one POST /fire, file
handles resolved through SELF_SHARD_INDEX.md), the graded lexicon plan (terms taught earlier =
available; terms this section may coin, each with its plain-ground teaching seed), and the
allowed citekeys (drawn from the blueprint's cite lines — the corpus gate).

Usage: assemble_section_bundle.py [--no-fire]
"""
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
LOOP = ROOT / "paper_eigen" / "_loop"
FIRE_URL = "http://127.0.0.1:8770/fire"
REACH_CAP = 12

RULES = """You are drafting ONE section of a paper for a reader who is an expert in NOTHING.
Hold their hand the whole way. Rules, all binding:
1. Use ONLY this bundle. If something is not in it, you may not assert it. A gap you feel is
   a FRICTION to report (see 9), never something to invent.
2. NUMBERS: a numeral may appear in your prose ONLY if it appears verbatim in one of the
   bundle's claim texts, and the sentence carrying it ends with the claim id in square
   brackets, e.g. [C3]. No other numerals anywhere (section numbering aside).
3. CITATIONS: only keys listed in cites_allowed, written inline as [@key]. No others exist.
4. COIN-THEN-TEACH: you may coin ONLY the terms in lexicon.to_teach. On first use, bold the
   term and teach it from its seed in plain words with one concrete example BEFORE reusing it.
   Terms in lexicon.available were taught in earlier sections - use them plainly, do not
   re-teach. NO other internal jargon of any kind.
5. REGISTER: derive, do not assert. Open on the motive as embodied prose (why this matters,
   shown not announced). BANNED: "in this section we", roadmap sentences, em-dashes,
   semicolons, antithesis-as-content, gnomic subtitles, hedging as armour.
6. NO FIGURES: do not render or reference figures; intents are registered elsewhere.
7. LENGTH: 450-750 words of body prose.
8. OUTPUT: markdown. First line: "## {n}. {title}". Then the prose.
9. FRICTION: if the bundle lacks something the section needs, append an HTML comment block:
   <!-- FRICTION type:CONTENT|FORM|TENSION ... one line each -->. Honest gaps over smooth prose.
"""

SECTIONS = [
    {
        "n": 1, "id": "problem", "title": "What a stateless assistant cannot do",
        "goal": "what is missing in a stateless assistant - no compounding memory, no held judgement, facts leaned on but unreferenced",
        "claims": [], "beats": ["problem"],
        "cites": ["hernandezespinosa2026superarc"],
        "teach": [], "figures": [],
    },
    {
        "n": 2, "id": "one_move", "title": "One move, recurred: group, then compute the interaction",
        "goal": "one fold operator recurred - shard a corpus by its own structure, grades by construction, upfold the generators, insert the missing middle",
        "claims": ["C1"], "beats": ["core_idea", "recursogram"],
        "cites": ["mehta2014exact", "tishby2015deep", "kochjanusz2018mutual",
                   "hernandezespinosa2026superarc", "parker2019universal", "white1992density"],
        "teach": [
            ["conceptric", "the one map the system grows: concepts connected by computed links, readable at several levels of detail"],
            ["grade", "a level of detail in the map; the bottom grade is the raw record, and each grade above holds fewer, broader concepts"],
            ["upfold", "the grouping step: concepts that share enough structure are folded into one broader concept that stands above them"],
        ],
        "figures": ["fig:compression_lineage", "fig:recursogram"],
    },
    {
        "n": 3, "id": "response_functions", "title": "Nodes are instructions, not summaries",
        "goal": "node content as goal-conditioned instructions - what to pull from below and what to return up - essences as the network's coupling rows",
        "claims": [], "beats": ["conceptric", "growth", "substrate"],
        "cites": [],
        "teach": [
            ["fire", "sending a question into the map: the question is matched against every level and the concepts that answer it light up"],
            ["response function", "a node's content is not a summary but instructions: given a question, what to fetch from the detail below and what to send back up"],
        ],
        "figures": ["fig:conceptric"],
    },
    {
        "n": 4, "id": "conjugacy", "title": "Two representations, and where checking is free",
        "goal": "lexical and vector as conjugate representations - move every check to the representation where it is mechanical - closure, identity, cluster quality, novelty",
        "claims": ["C2", "C4", "C5", "C7"], "beats": ["grounded"],
        "cites": [],
        "teach": [
            ["closure", "a built concept is closed when its stated description can be re-derived from its own members; closure can be checked"],
            ["margin", "how much closer a member sits to its own concept than to the nearest rival concept; a small margin marks a boundary case"],
            ["bleed", "when members sit nearly as close to a rival concept as to their own; heavy mutual bleed across a level means the split was not earned"],
            ["inversion", "a member that sits strictly closer to a rival concept than to its own; the strongest mechanical warning"],
            ["residue", "the part of a new input that no existing concept can express; its size measures how much of the input is genuinely new"],
        ],
        "figures": [],
    },
    {
        "n": 5, "id": "economics", "title": "The loop must get cheaper, and it did",
        "goal": "non-termination economics - each loop must make the next cheaper - the engine's own operations as deposited routable nodes a cold instance reads",
        "claims": ["C3"], "beats": ["metaloop"],
        "cites": ["parker2019universal"],
        "teach": [
            ["operations lens", "the system's own procedures stored as ordinary nodes in its map, so a fresh instance looks up how to do a thing instead of re-deriving it"],
        ],
        "figures": [],
    },
    {
        "n": 6, "id": "instrument", "title": "The instrument turned on its builder",
        "goal": "the build record sharded by the same operator - the blind structural reading of the self - pre-registration as the discipline for self-measurement",
        "claims": ["C6"], "beats": ["grounded"],
        "cites": [],
        "teach": [],
        "figures": ["fig:spectra_self_vs_physics"],
    },
    {
        "n": 7, "id": "auditability", "title": "Every weight has an address",
        "goal": "every weight locatored, every verdict banked, builder separated from judge, citation discipline enforced mechanically",
        "claims": ["C8"], "beats": ["memory", "grounded"],
        "cites": [],
        "teach": [
            ["locator", "a pointer to the exact place a piece of evidence lives, attached to the weight it justifies, so any link can be traced to its source line"],
        ],
        "figures": [],
    },
    {
        "n": 8, "id": "limits", "title": "Limits, honestly",
        "goal": "the patchy global map - the router's upper-grade miscalibration - what is deliberately excluded and why - the open problems",
        "claims": [], "beats": ["metaloop", "frontier", "continuity"],
        "cites": ["hernandezespinosa2026superarc"],
        "teach": [],
        "figures": [],
    },
]


def parse_claims() -> dict[str, str]:
    text = (ROOT / "paper_eigen" / "CLAIMS_LEDGER.md").read_text(encoding="utf-8")
    blocks = re.split(r"^## ", text, flags=re.M)[1:]
    out = {}
    for b in blocks:
        m = re.match(r"(C\d+)", b)
        if m:
            out[m.group(1)] = "## " + b.strip().split("\n---")[0].strip()
    return out


def parse_beats() -> dict[str, str]:
    text = (ROOT / "talks" / "explaining-eigen" / "blueprint.md").read_text(encoding="utf-8")
    blocks = re.split(r"^## ", text, flags=re.M)[1:]
    out = {}
    for b in blocks:
        name = b.split("|")[0].strip()
        out[name] = "## " + b.strip()
    return out


def parse_index() -> dict[str, str]:
    out = {}
    for line in (ROOT / "SELF_SHARD_INDEX.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"- \*\*(.+?)\*\* - (.+)", line)
        if m:
            out[m.group(1)] = m.group(2).split(" Â·")[0].split(" ·")[0][:200]
    return out


def fire(goal: str) -> list[dict]:
    body = json.dumps({"goal": goal, "by": "eigen-paper-loop"}).encode()
    req = urllib.request.Request(FIRE_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode())
    return d.get("fired", [])


def main() -> int:
    no_fire = "--no-fire" in sys.argv
    LOOP.mkdir(parents=True, exist_ok=True)
    claims, beats, index = parse_claims(), parse_beats(), parse_index()

    taught_so_far: list[dict] = []
    for s in SECTIONS:
        reach = []
        if not no_fire:
            try:
                for h in fire(s["goal"])[:REACH_CAP]:
                    nid = h.get("id", "")
                    entry = {"id": nid, "channel": h.get("channel", "")}
                    if nid.startswith("file:") and nid[5:] in index:
                        entry["essence"] = index[nid[5:]]
                    reach.append(entry)
            except Exception as e:  # noqa: BLE001 - reach is enrichment, not load-bearing
                reach = [{"error": f"fire failed: {e}"}]
        bundle = {
            "section": s["n"], "id": s["id"], "title": s["title"],
            "rules": RULES,
            "goal": s["goal"],
            "claims": {c: claims[c] for c in s["claims"]},
            "beats": {b: beats[b] for b in s["beats"]},
            "reach": reach,
            "cites_allowed": s["cites"],
            "lexicon": {
                "available": list(taught_so_far),
                "to_teach": [{"term": t, "seed": seed} for t, seed in s["teach"]],
            },
            "figure_intents_registered_elsewhere": s["figures"],
        }
        path = LOOP / f"bundle_{s['n']}.json"
        path.write_text(json.dumps(bundle, indent=1, ensure_ascii=False), encoding="utf-8")
        taught_so_far += [{"term": t, "taught_in_section": s["n"], "seed": seed}
                          for t, seed in s["teach"]]
        print(f"bundle_{s['n']}  {s['id']:<20} claims={len(bundle['claims'])} "
              f"beats={len(bundle['beats'])} reach={len(reach)} "
              f"teach={len(s['teach'])} cites={len(s['cites'])}  -> {path.name}")
    print(f"\nlexicon ladder: {sum(len(s['teach']) for s in SECTIONS)} terms across 8 sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
