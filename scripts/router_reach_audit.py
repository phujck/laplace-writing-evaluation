#!/usr/bin/env python3
"""Router-reach audit — the standing gate for "shipping is not reaching".

A canon node the router cannot reach on a clean session is amnesia: it is
committed but invisible to the goal-routing the next cold session uses to find
it (the lesson the 2026-06-05 session learned three times, each time by hand).
This makes that check a tool instead of a memory.

The test, per node: build the most natural probe for it — its own title — and
ask whether ``Canon.route`` surfaces the node for that probe on a *fresh* canon.
A node that does not surface for a query *about itself* is buried below the cut;
that is the friction signal that the node needs routing tags (regrow the kernel),
exactly the operatorial_self move (the friction names what the index lacks).

Usage:
    python scripts/router_reach_audit.py                 # full audit, all nodes
    python scripts/router_reach_audit.py <ref|name> "<probe>"   # gate one node

The single-node form is the build-time gate: after forging a node, confirm it
reaches before trusting the commit. Exit code is non-zero when any node misses,
so it can run in CI / a pre-commit check.
"""
from __future__ import annotations

import json
import sys

from laplace.pipeline.canon import get_canon


def _reaches(route_result: dict, *, wiki_ref: str | None = None, skill_name: str | None = None) -> bool:
    hits = route_result.get("canon", {})
    if wiki_ref is not None:
        return f"canon://{wiki_ref}" in hits.get("wiki", [])
    return skill_name in hits.get("skills", [])


def _is_deprecated(text: str) -> bool:
    return "[DEPRECATED]" in (text or "").upper()


def audit_all() -> int:
    """Audit every node, separating true misses from expected non-reach.

    A hard MISS is a *global*, *non-deprecated* node that does not surface for a
    query about itself — genuine reachability debt. Two buckets are advisory, not
    failures: **domain-scoped** nodes (correctly filtered out of a bare global
    probe — reachable only when their domain is active) and **deprecated** nodes
    (which *should* be unreachable). Only hard misses set the exit code.
    """
    canon = get_canon(fresh=True)
    misses: list[tuple[str, str]] = []
    domain_scoped: list[str] = []
    deprecated: list[str] = []
    n = 0
    for ref, node in canon.wiki.items():
        n += 1
        if _is_deprecated(node.title) or _is_deprecated(getattr(node, "source", "")):
            deprecated.append(f"canon://{ref}")
            continue
        if getattr(node, "scope", "global") == "domain":
            if not _reaches(canon.route(f"{node.title} ({node.domain})"), wiki_ref=ref):
                domain_scoped.append(f"canon://{ref}")
            continue
        if not _reaches(canon.route(node.title), wiki_ref=ref):
            misses.append((f"canon://{ref}", node.title))
    for name, sk in canon.skills.items():
        n += 1
        probe = (getattr(sk, "title", "") or sk.description.split(".")[0] or name)
        if _is_deprecated(sk.description) or _is_deprecated(probe):
            deprecated.append(name)
            continue
        if not _reaches(canon.route(probe), skill_name=name):
            misses.append((name, probe[:70]))

    print(
        f"router-reach audit: {n} nodes probed — {len(misses)} hard MISS, "
        f"{len(domain_scoped)} domain-scoped (advisory), {len(deprecated)} deprecated (exempt)"
    )
    if misses:
        print("\nSHIP-BUT-DON'T-REACH (global nodes invisible to a query about themselves —")
        print("regrow the index with routing tags; do not let it ride on a band-aid):")
        for ident, probe in misses:
            print(f"  MISS  {ident}")
            print(f"        probe: {probe}")
    else:
        print("all global nodes reach themselves on a clean session.")
    if domain_scoped:
        print("\nDOMAIN-SCOPED (advisory — reach only with their domain active):")
        for ident in domain_scoped:
            print(f"  ~ {ident}")
    return 1 if misses else 0


def _resolve(canon, target: str) -> tuple[str | None, str | None]:
    """Resolve a user-given target (short name or full ref) to (wiki_ref, skill_name).

    Accepts a skill name, a full wiki ref (``engine/operatorial_self``), a
    ``canon://`` URL, or a bare leaf (``operatorial_self``) — the bare leaf is
    matched against the tail of every wiki ref so the build-time gate does not
    demand the caller already know the full path.
    """
    t = target.replace("canon://", "")
    if t in canon.skills:
        return None, t
    if t in canon.wiki:
        return t, None
    leaf = t.rsplit("/", 1)[-1]
    matches = [ref for ref in canon.wiki if ref.rsplit("/", 1)[-1] == leaf]
    if len(matches) == 1:
        return matches[0], None
    return None, None  # unresolved or ambiguous


def audit_one(target: str, probe: str) -> int:
    canon = get_canon(fresh=True)
    wiki_ref, skill_name = _resolve(canon, target)
    if wiki_ref is None and skill_name is None:
        print(f"UNRESOLVED: {target!r} is not a known node (or is an ambiguous leaf)")
        return 2
    r = canon.route(probe)
    ok = _reaches(r, wiki_ref=wiki_ref, skill_name=skill_name)
    resolved = wiki_ref or skill_name
    verdict = "REACHES" if ok else "MISS"
    print(f"{verdict}: {resolved}  for probe {probe!r}")
    if not ok:
        print("  surfaced instead:", json.dumps(r.get("canon", {}), default=str)[:400])
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) == 1:
        return audit_all()
    if len(sys.argv) == 3:
        return audit_one(sys.argv[1], sys.argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
