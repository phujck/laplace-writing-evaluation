"""Stage C — structural resolution (rebuild mandate §6).

The projection spec says WHAT the paper contains; this stage settles WHERE
every object lives and what the reader knows at each boundary. Two artifacts:

- ``section_contracts.json`` (§6.1): one contract per plan section — function,
  question answered, reader entry/exit states, permitted recap. The ordered
  node list is NOT duplicated here: the plan's ``nodes_in_order`` stays the
  single source (the storyboard edits it; contracts reference it).
- ``reader_state.json`` (§6.2): the DERIVED reader-state graph — for every
  planned node, where it is introduced and where it is used afterwards,
  computed from plan order + substrate edges.

The §6.3 structural completion gate is :func:`gate` — the boundary no
narrative or prose work may cross while red.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from laplace.pipeline import registry, schema


# Define-before-use is a DIRECTIONAL constraint: it only means something for edge
# kinds whose semantics are "A REQUIRES B" — B must be established before A is
# used. A SYMMETRIC kind ("A and B co-occur / share a theme") carries no ordering
# obligation, so a forward reference over it is reported as an *advisory*, never a
# failure. Any kind not named symmetric is treated as directional: the gate
# defaults to ENFORCING an unrecognised relation rather than silently waiving it.
DIRECTIONAL_EDGE_KINDS = frozenset({"draws", "prerequisite", "implementation"})
SYMMETRIC_EDGE_KINDS = frozenset({"shares", "analogy"})
# "A validated_by B": B is the evidence artifact for A, not expository substrate.
# A claim may precede the artifact that validates it (reproduction nodes pool in
# a protocols appendix by convention), so a forward reference over an evidential
# kind is an advisory, never a failure. First bearer: paper_roland_qrc (2026-08-06);
# falqon/eigenengine carry no such edges, so this set changes nothing for them.
EVIDENTIAL_EDGE_KINDS = frozenset({"validated_by", "support", "implementation"})


def _edge_kinds(proj, repo_root: Path | None, net: dict | None = None) -> dict[tuple[str, str], str]:
    """(src, dst) -> rel for the conceptric substrate's edges. The runtime rewire
    ledger flattens every dependency to an undifferentiated add-edge, so the rel
    kind (draws vs shares) is recovered here from the hand-built substrate graph —
    the only artifact where the directional/symmetric distinction survives."""
    # Current rewire records carry relation semantics directly.  They outrank
    # the historical conceptric_v1 sidecar, which remains a compatibility read.
    out: dict[tuple[str, str], str] = {}
    for relation in (net or {}).get("relations") or []:
        if relation.get("source") and relation.get("target") and relation.get("rel"):
            out[(relation["source"], relation["target"])] = relation["rel"]
    try:
        from laplace.research import corpus_ingest as ci
        for row in ci.rewire_list(repo_root or registry._repo_root(), proj.name):
            if row.get("kind") in {"add-edge", "confirm-edge"} and row.get("node") and row.get("target") and row.get("rel"):
                out[(row["node"], row["target"])] = row["rel"]
            elif row.get("kind") == "remove-edge" and row.get("node") and row.get("target"):
                out.pop((row["node"], row["target"]), None)
    except Exception:
        pass
    sp = (proj.path(f"{proj.manuscript_dir}/conceptric_v1.json", repo_root)
          if proj.manuscript_dir else None)
    if sp is None or not sp.is_file():
        return out
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    for e in data.get("edges") or []:
        src, dst, rel = e.get("src"), e.get("dst"), e.get("rel")
        if src and dst and rel and (src, dst) not in out:
            out[(src, dst)] = rel
    return out


def _paths(project: str, repo_root: Path | None):
    proj = registry.resolve(project, repo_root=repo_root)
    if proj is None:
        raise ValueError(f"unknown project {project!r}")
    return (proj, proj.stage_path("contracts", repo_root),
            proj.stage_path("reader_state", repo_root))


def load_contracts(project: str, repo_root: Path | None = None) -> dict | None:
    _, cp, _ = _paths(project, repo_root)
    if cp is None or not cp.is_file():
        return None
    try:
        return json.loads(cp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_contracts(project: str, contracts: dict, repo_root: Path | None = None) -> Path:
    _, cp, _ = _paths(project, repo_root)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(contracts, ensure_ascii=False, indent=1) + "\n",
                  encoding="utf-8")
    return cp


def seed_contracts(project: str, repo_root: Path | None = None) -> dict:
    """A contract skeleton per plan section: ids, titles, node/figure joins,
    and document-order dependencies prefilled mechanically. The authored
    fields (function, question, entry/exit states, permitted recap) start
    empty — an agent or the author fills them; the gate refuses empties."""
    proj = registry.resolve(project, repo_root=repo_root)
    plan = proj.read_plan(repo_root) or {}
    sections = list(schema.plan_sections(plan))
    contracts: dict[str, Any] = {"project": project, "sections": {}}
    for i, sec in enumerate(sections):
        sid = sec["id"]
        contracts["sections"][sid] = {
            "section_id": sid,
            "title": sec.get("title", ""),
            "function": "",
            "question_answered": "",
            "entry_state": "",
            "exit_state": "",
            "equations": [],
            "figures": list(sec.get("figures") or []),
            "tables": [],
            "depends_on": [s["id"] for s in sections[:i]][-2:],
            "forward_uses": [],
            "permitted_recap": "",
            "citations": list(sec.get("refs") or []),
        }
    return contracts


def compute_reader_state(project: str, repo_root: Path | None = None,
                         write: bool = True) -> dict[str, Any]:
    """§6.2 — the reader-state graph, derived: introduction = the owning
    section (first appearance in plan document order — the storyboard's
    dedup law makes this unique); uses = later sections whose planned nodes
    touch it through 1-hop substrate edges."""
    proj, _, rp = _paths(project, repo_root)
    plan = proj.read_plan(repo_root) or {}
    order: list[tuple[str, list[str]]] = [
        (sec["id"], schema.section_nodes(sec)) for sec in schema.plan_sections(plan)]
    sec_index = {sid: i for i, (sid, _) in enumerate(order)}

    introduced: dict[str, str] = {}
    for sid, nids in order:
        for nid in nids:
            introduced.setdefault(nid, sid)

    relations: list[dict] = []
    if proj.kind == "conceptric":
        from laplace.research import corpus_ingest as ci
        rr = Path(repo_root) if repo_root else registry._repo_root()
        net = ci.corpus_network(ci.resolve_corpus(rr, project), repo_root=rr,
                                name=project)
        relations = list(net.get("relations") or [])

    uses: dict[str, list[str]] = {nid: [] for nid in introduced}
    for sid, nids in order:
        for nid in nids:
            for tgt in [row.get("target") for row in relations if row.get("source") == nid]:
                if tgt in introduced and introduced[tgt] != sid \
                        and sec_index[introduced[tgt]] < sec_index[sid] \
                        and sid not in uses[tgt]:
                    uses[tgt].append(sid)

    state = {"project": project,
             "nodes": {nid: {"introduced": introduced[nid], "uses": uses[nid]}
                       for nid in sorted(introduced)}}
    if write and rp is not None:
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    return state


def gate(project: str, repo_root: Path | None = None) -> dict[str, Any]:
    """§6.3 — the structural completion gate. Red = narrative and prose stages
    are closed. Checks are mechanical:

    - every plan section has a contract; authored fields are non-empty;
    - no node appears in two sections' ordered lists (unique introduction);
    - dependency order: a planned node's 1-hop substrate targets that are
      planned anywhere are introduced no later than the node's own section
      (define-before-use at node granularity). This is enforced ONLY for
      directional (``requires``) edge kinds; a forward reference over a
      symmetric kind (see ``SYMMETRIC_EDGE_KINDS``) is an ``advisory``, and a
      forward reference the plan lists in ``meta.sanctioned_forward`` is
      recorded as ``sanctioned`` — both visible, neither a failure;
    - depends_on points strictly backwards, forward_uses strictly forwards;
    - every planned figure carries a settled spec caption (join to stage B).
    """
    proj, _, _ = _paths(project, repo_root)
    plan = proj.read_plan(repo_root) or {}
    contracts = (load_contracts(project, repo_root) or {}).get("sections") or {}
    issues: list[dict[str, str]] = []

    sections = list(schema.plan_sections(plan))
    sec_index = {sec["id"]: i for i, sec in enumerate(sections)}

    _repool_sanctioned = {
        (s.get("source"), s.get("target")): s.get("why", "")
        for s in ((plan.get("meta") or {}).get("sanctioned_forward") or [])}
    sanctioned_dups: list[dict[str, str]] = []

    seen: dict[str, str] = {}
    for sec in sections:
        sid = sec["id"]
        c = contracts.get(sid)
        if c is None:
            issues.append({"where": sid, "issue": "no section contract"})
            continue
        for f in ("function", "question_answered", "entry_state", "exit_state"):
            if not c.get(f):
                issues.append({"where": sid, "issue": f"contract field {f!r} empty"})
        for dep in c.get("depends_on") or []:
            if dep not in sec_index or sec_index[dep] >= sec_index[sid]:
                issues.append({"where": sid, "issue": f"depends_on {dep!r} not earlier"})
        for fwd in c.get("forward_uses") or []:
            if fwd not in sec_index or sec_index[fwd] <= sec_index[sid]:
                issues.append({"where": sid, "issue": f"forward_uses {fwd!r} not later"})
        for nid in schema.section_nodes(sec):
            if nid in seen and seen[nid] != sid:
                if (nid, sid) in _repool_sanctioned:
                    # author-sanctioned repooling (plan meta.sanctioned_forward with
                    # a section target): the node is stated early and derived late,
                    # and the plan says so — visible, not a failure
                    sanctioned_dups.append(
                        {"where": sid, "node": nid,
                         "sanctioned": f"repooled from {seen[nid]}",
                         "why": _repool_sanctioned[(nid, sid)]})
                else:
                    issues.append({"where": sid,
                                   "issue": f"{nid} already introduced in {seen[nid]}"})
            seen.setdefault(nid, sid)

    state = compute_reader_state(project, repo_root, write=False)["nodes"]
    net: dict = {"relations": []}
    if proj.kind == "conceptric":
        from laplace.research import corpus_ingest as ci
        rr = Path(repo_root) if repo_root else registry._repo_root()
        net = ci.corpus_network(ci.resolve_corpus(rr, project), repo_root=rr,
                                name=project)
    relations = list(net.get("relations") or [])
    edge_kind = _edge_kinds(proj, repo_root, net) if proj.kind == "conceptric" else {}
    sanctioned_pairs = _repool_sanctioned
    advisories: list[dict[str, str]] = []
    sanctioned: list[dict[str, str]] = []
    for nid, info in state.items():
        for relation in [row for row in relations if row.get("source") == nid]:
            tgt = relation.get("target")
            ti = state.get(tgt)
            if not (ti and sec_index.get(ti["introduced"], 0)
                    > sec_index.get(info["introduced"], 0)):
                continue
            detail = (f"uses {tgt} introduced later "
                      f"({ti['introduced']} > {info['introduced']})")
            rel = edge_kind.get((nid, tgt))
            if not relation.get("inferential"):
                # symmetric co-occurrence, not a dependency: no ordering obligation
                advisories.append({"where": nid, "rel": rel,
                                   "advisory": detail + " — non-inferential relation; "
                                   "it does not impose define-before-use ordering"})
            elif (nid, tgt) in sanctioned_pairs:
                # author-sanctioned forward reference (plan meta.sanctioned_forward)
                sanctioned.append({"where": nid, "target": tgt,
                                   "sanctioned": detail,
                                   "why": sanctioned_pairs[(nid, tgt)]})
            else:
                issues.append({"where": nid, "issue": detail})

    from laplace.pipeline import projection_spec
    spec = projection_spec.load_spec(project, repo_root) or {}
    spec_figs = spec.get("figures") or {}
    for sec in sections:
        for fid in sec.get("figures") or []:
            if not (spec_figs.get(fid) or {}).get("caption"):
                issues.append({"where": fid, "issue": "planned figure caption "
                                                      "not settled in spec"})

    return {"pass": not issues, "project": project, "issues": issues,
            "advisories": advisories, "sanctioned": sanctioned + sanctioned_dups,
            "n_sections": len(sections), "n_nodes": len(seen),
            "relation_diagnostics": list(net.get("relation_diagnostics") or [])}
