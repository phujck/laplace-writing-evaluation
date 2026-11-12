"""R2 Referee — the domain-armed sufficiency reader (checklist cat 1/4).

The one reader we hand the physics to — and the sharpest statement of the suite's
principle: **even the reader armed with the domain must be denied the intention, or
it grades the paper it MEANT to write.** R2's seal is *intent-only*: it may load the
domain and the prior art (it reuses ``hostile_redteam_swarm``'s context-bearing
Formalist/Synthesist posture), but it is denied the spec / plan / narrative packet
for THIS manuscript.

Its question is distinct from R3 Apparatus's. R3 asks *is a citation wired at all*
(mechanical). R2 asks *is every major claim's evidence SUFFICIENT, and is the claim
actually this paper's own* (semantic — the is-this-earned / is-this-yours call). It
owns hard-failure #1 (``claim-unearned``) and emits two kinds:

    referee-insufficient       — a major claim whose stated evidence is too thin
    referee-inherited-uncited  — a claim that is actually inherited, not original

Following the Phase-D2 pattern: PACKAGE the sufficiency read (the intent-only prompt
+ the seal) and PARSE the adversary's verdict — this module does not spawn the swarm.
Phase F drives the real ``hostile_redteam_swarm`` at candidate-lock. The mechanical
FLOOR reuses ``citation_audit``'s forward tell-scan (the SAME floor R3 sits on) but
surfaces each external-fact-tell-near-no-cite as a *sufficiency probe* for the
referee to adjudicate — never as a mechanical verdict (the floor cannot judge
is-this-yours; only the domain-armed reader can).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.citation_audit import check_citation_audit
from laplace.pipeline.readers.roster import READERS, reader_finding
from laplace.pipeline.readers.sealed import _coerce_json

# R2 is domain-armed, so its seal DENIES only the construction intention — a
# narrower sentinel set than the sealed-subagent organ (the domain/corpus are
# allowed). These are the spec/plan/narrative tokens the referee must not be shown.
INTENT_SENTINELS: tuple[str, ...] = (
    "POLICY", "OBJECT channel", "builder_contract", "narrative spec",
    "projection-plan", "projection_spec", "blueprint", "storyboard",
    "set-spine", "set-meta", "reading_order", "we are explicit about what is new",
)

REFEREE_INSTRUCTION = (
    "You are THE REFEREE — a hostile reviewer who KNOWS this domain and its prior "
    "art. You may use your knowledge of the field and the literature. You have NOT "
    "been shown the authors' spec, plan, or narrative packet for this manuscript, "
    "and you must not try to reconstruct their intention: judge the paper on the "
    "page, not the paper they meant to write. For every MAJOR claim, ask two "
    "questions: (1) is the evidence the paper offers SUFFICIENT to earn this claim "
    "at the strength it is stated? (2) is this claim actually THIS paper's own "
    "contribution, or is it inherited from prior work — and if inherited, is it "
    "cited? Flag a claim whose evidence is too thin (referee-insufficient) and a "
    "claim that is inherited but uncited or passed off as original "
    "(referee-inherited-uncited). Do NOT flag a genuine original contribution for "
    "lacking a citation — that is the whole point of the paper. Return ONLY JSON: a "
    'list of findings, each {"where": "<claim/section>", "issue": "<why the '
    'evidence is insufficient / why it is inherited>", "fix": "<strengthen the '
    'evidence, or cite the source>", "kind": "<referee-insufficient|'
    'referee-inherited-uncited>"}. Empty list if every major claim is earned.'
)


def _allowed_kinds() -> list[str]:
    return list(READERS["R2"].owned_kinds)


def intent_seal_holds(payload: dict[str, Any]) -> dict[str, Any]:
    """R2's seal: the domain/corpus are ALLOWED (unlike the sealed-subagent organ),
    only the construction intention is denied. Scans the prompt for the narrower
    :data:`INTENT_SENTINELS`. Returns ``{ok, leaks}``."""
    hay = (payload.get("prompt", "") or "") + "\n" + (payload.get("claim_context", "") or "")
    leaks = [{"sentinel": s, "where": "prompt"} for s in INTENT_SENTINELS if s in hay]
    return {"ok": not leaks, "leaks": leaks}


def pack_for_referee_read(target: Union[str, Path],
                          domain: Optional[str] = None,
                          claim_table: Optional[list[dict[str, Any]]] = None
                          ) -> dict[str, Any]:
    """Package the sufficiency read for Phase F to drive against
    ``hostile_redteam_swarm``. The referee reads the rendered manuscript (path
    passed through — the swarm's Formalist reads the artifact), oriented on the
    ``domain`` but NOT the spec. ``claim_table`` is the optional claim→source map
    from ``citation_audit`` (a data product, not the spec) to focus the read.

    Returns the intent-only-sealed payload; F spawns the swarm's context-bearing
    roles with ``laplace_orient(goal=...)`` for the DOMAIN and hands them this
    instruction + the manuscript path. ``parse_referee_verdict`` closes the loop."""
    prompt = REFEREE_INSTRUCTION
    if domain:
        prompt += f"\n\nDOMAIN (you may orient on this, NOT on the manuscript's plan): {domain}"
    payload = {
        "reader": "R2",
        "organ": "adversary",
        "skill": "hostile_redteam_swarm",
        "role": "Formalist/Synthesist (context-bearing — orients on the domain)",
        "target": str(Path(target)),
        "instruction": REFEREE_INSTRUCTION,
        "prompt": prompt,
        "allowed_kinds": _allowed_kinds(),
        "finding_schema": ["where", "issue", "fix", "kind"],
        "seal": {"denies": list(READERS["R2"].seal_denies),
                 "allows": list(READERS["R2"].seal_allows),
                 "statement": READERS["R2"].seal},
        "claim_table": claim_table or [],
    }
    payload["seal_check"] = intent_seal_holds(payload)
    return payload


def referee_floor(target: Union[str, Path]) -> list[dict[str, Any]]:
    """The mechanical floor — every round, no model. Reuses ``citation_audit``'s
    forward tell-scan (the SAME floor R3 sits on) and surfaces each external-fact
    tell sitting near no ``\\cite`` as a *sufficiency PROBE* for the referee: a
    location where the domain-armed reader should decide is-this-yours. These are
    ADVISORY (``floor=True``) — the floor cannot make the semantic call, so it
    never asserts insufficiency, it points the referee at the risk."""
    res = check_citation_audit(Path(target))
    out: list[dict[str, Any]] = []
    for f in res.get("findings", []):
        if f.get("kind") != "citation-uncited":
            continue
        # the forward sweep already annotates first-person markers; a tell WITHOUT
        # them is the stronger inherited-claim probe.
        has_first_person = "first-person markers present" in (f.get("issue") or "")
        kind = "referee-inherited-uncited"
        note = ("an external-fact tell near no \\cite; first-person markers present "
                "— referee: confirm this is the paper's own contribution"
                if has_first_person else
                "an external-fact tell near no \\cite and no first-person marker "
                "— referee: likely inherited, confirm and cite the source")
        out.append({**reader_finding("R2", f.get("where", "?"), note,
                                     "cite the source, or confirm as original and mark it",
                                     kind, quote=f.get("quote")),
                    "floor": True})
    return out


def parse_referee_verdict(raw: str, strict: bool = False) -> list[dict[str, Any]]:
    """Parse the referee's reply into findings in the standard shape, stamped R2 and
    routed (referee-insufficient → projection, referee-inherited-uncited →
    research-state). Unknown/missing kind coerces to ``referee-insufficient`` unless
    ``strict``. Malformed → ``[]``."""
    data = _coerce_json(raw)
    if isinstance(data, dict):
        data = data.get("findings", data.get("verdict", []))
    if not isinstance(data, list):
        return []
    allowed = set(_allowed_kinds())
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        if kind not in allowed:
            if strict:
                continue
            kind = "referee-insufficient"
        out.append(reader_finding(
            "R2", str(item.get("where", "")).strip(),
            str(item.get("issue", "")).strip(),
            (str(item.get("fix", "")).strip() or None), kind,
            quote=(str(item.get("quote", "")).strip() or None)))
    return out
