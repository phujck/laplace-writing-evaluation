"""ingest_collaborators.py - materialise the collaborator corpus from the distilled relationships.

The collaborator pour, following the atoms-g0 floor precedent (his, 2026-06-08): a COLLABORATOR is a
g1+ CLUSTER (a person), not the substrate floor; their distilled CONTRIBUTIONS are the g0 atoms beneath
them. Each person node is a real file (``collaborator_corpus/people/<key>.md``, authored essence = role +
summary) that the keeper grades atom(g0) -> person(g1) -> people(g2) -> collaborator_corpus(g3). The
contribution atoms are virtual g0 nodes (``<person>::<atom>``), materialised by
``collaborator_lens.collaborator_leaves`` (same ``::`` convention as the concept atoms).

The faithful CROSS-CORPUS wire (not vocabulary): each collaborator wires to the physics-lens themes/papers
they actually co-authored, matched from their distilled shared-themes + contribution-atom names against the
real lens slugs. Confidence rides every contribution (his spectral-radius insight): high/medium are the
faithful substrate; LOW is kept as conjectural grit (tagged, surfaced on ideation, never asserted).

Reads ``collaborator_corpus/_distillates/<key>.json`` (the sealed Haiku-swarm output). Public bibliographic
data - committed openly. No LLM here; pure deterministic materialise of the swarm's distillate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PEOPLE = REPO / "collaborator_corpus" / "people"
DISTILL = REPO / "collaborator_corpus" / "_distillates"
ATOM_SEP = "::"
# the cross-corpus matcher lives in laplace.engine.collaborator_lens (one source of truth, shared with the coupling)


def materialise(fire: bool = False) -> dict[str, object]:
    PEOPLE.mkdir(parents=True, exist_ok=True)
    fired = None
    if fire:
        try:
            from laplace.web.scanner import client_fire as fired  # type: ignore
        except Exception:  # noqa: BLE001
            fired = None

    from laplace.engine import collaborator_lens
    wires_by_person = collaborator_lens.cross_corpus_wires(REPO)   # the ONE matcher (shared with the coupling)
    voice_by_key = {(r.get("_key") or r.get("key", "")): r for r in collaborator_lens.voice_records(REPO)}

    written: list[str] = []
    n_atoms = n_conj = n_wires = 0
    for jf in sorted(DISTILL.glob("*.json")):
        rec = json.loads(jf.read_text(encoding="utf-8"))
        key = rec.get("_key") or jf.stem
        atoms = rec.get("contribution_atoms", [])

        # cross-corpus wires (faithful, co-built): split the shared matcher's result by lens kind
        wires = wires_by_person.get(f"collaborator_corpus/people/{key}.md", set())
        paper_wires = {w for w in wires if "/atoms/" in w}
        theme_wires = {w for w in wires if "/themes/" in w}
        n_wires += len(wires)

        fm = {"kind": "collaborator", "key": key, "openalex_id": rec.get("openalex_id", ""),
              "shared_themes": rec.get("shared_themes", []), "n_atoms": len(atoms)}
        body = ["---", *(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items()), "---", "",
                f"# {rec.get('name', key)}", "", f"**Role.** {rec.get('role', '')}", "",
                f"**Collaboration.** {rec.get('summary', '')}", ""]
        # the contribution atoms (the g0 substrate this person clusters) - confidence-graded
        body += ["## Contributions", ""]
        for a in atoms:
            conf = a.get("confidence", "medium")
            grit = " · _conjectural grit (surfaces on ideation)_" if conf == "low" else ""
            if conf == "low":
                n_conj += 1
            body.append(f"- **{a.get('name','')}** ({a.get('kind','concept')}, {conf}{', with McCaul' if a.get('with_mccaul') else ''})"
                        f" — {a.get('statement','')}{grit}")
            n_atoms += 1
        # the scientific voice (from the PAPERS - how they think in the literature; the
        # conjugate of the sealed chat voice, which holds how they speak to Gerard)
        vrec = voice_by_key.get(key)
        if vrec and vrec.get("voice_items"):
            body += ["## Scientific voice (from the papers)", ""]
            for v in vrec["voice_items"]:
                conf = v.get("confidence", "medium")
                grit = " · _conjectural grit (surfaces on ideation)_" if conf == "low" else ""
                works = ", ".join((v.get("works") or [])[:6])
                body.append(f"- **{v.get('name','')}** ({v.get('kind','move')}, {conf})"
                            f" — {v.get('statement','')}{grit}{f' _[{works}]_' if works else ''}")
        body += ["", "## Wires (cross-corpus, faithful — the physics he co-built with McCaul)", ""]
        for w in sorted(paper_wires):
            body.append(f"- co-authored: [[{w}]]")
        for w in sorted(theme_wires):
            body.append(f"- theme: [[{w}]]")
        if rec.get("notes"):
            body += ["", f"<!-- distiller notes: {rec['notes']} -->"]
        body += ["", "> Collaborator node (`collaborator_corpus`, g1 cluster): a person McCaul works with, "
                 "their contributions the g0 substrate beneath them; wired to the lens physics they co-built. "
                 "Distilled by a sealed Haiku swarm (forced schema), confidence-graded. Closes by retrieval."]
        (PEOPLE / f"{key}.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        written.append(f"collaborator_corpus/people/{key}.md")
        if fired:
            fired(rec.get("name", key), by="eigen")

    return {"people": written, "n_people": len(written), "n_atoms": n_atoms,
            "n_conjectural": n_conj, "n_cross_corpus_wires": n_wires}


def main() -> int:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    fire = "--fire" in sys.argv
    print(json.dumps(materialise(fire=fire), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
