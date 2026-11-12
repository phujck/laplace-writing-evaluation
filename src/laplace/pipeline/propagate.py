"""The PROPAGATE operator — from a perturbation, the MINIMAL propagation.

P3 of the pipeline: given a perturbation — an L1 change-set since a mark, or
intake/feedback records through the one door (``schema.FEEDBACK_FIELDS``) —
compute what actually has to move: the dirty sections classified cheap or
expensive, and the typed worklist DAG for substance that does not exist yet
(``schema.WORK_KINDS``, routed by ``schema.KIND_TO_WORK``, shaped by
``schema.WORK_ITEM_FIELDS``).

The operator is a PURE READ. It emits a report; executing work items is
dispatch's job (P4). Nothing here appends to a ledger, writes a plan, or
touches a manuscript — the purity test banks that as bytes-unchanged.

The dirty machinery is WIRED, never reimplemented: ``storyboard.dirty_report``
supplies the plan-vs-tex reality (the ``% NODES`` marker diff), the schema
supplies membership accessors and op classes, and ``corpus_ingest``'s
``corpus_network`` supplies the substrate edges (``edge_index``) that order the
worklist.
"""

from __future__ import annotations

import json
from pathlib import Path

from laplace.pipeline import registry, schema

#: Worker route per work kind — OBJECT-side routing data, consumed by dispatch.
WORKERS = {
    "derive": "agent:derivation-builder",
    "mint": "agent:derivation-builder",
    "simulate": "script-or-agent:numerics",
    "figure": "script:provenance-generator",
    "prose": "agent:prose-realiser",
    "structure": "agent:structural-resolver",
    "narrative": "agent:narrative-planner",
    "render": "script:tex-backend",
}

#: L1 kinds whose whole effect is ORDER or audit status — no section's node set
#: or content moves, so the holder recompiles cheaply (the L1 analogue of
#: ``schema.CHEAP_OPS``). ``confirm-edge`` only banks a ``confirmed::`` audit
#: marker; everything else in ``schema.REWIRE_KINDS`` reshapes substance.
ORDER_ONLY_KINDS = frozenset({"set-spine", "unset-spine", "confirm-edge"})


# ---------------------------------------------------------------------------
# the change-set — L1 records after a mark
# ---------------------------------------------------------------------------

def changeset_since(project: str, mark=None, repo_root: Path | str | None = None) -> list[dict]:
    """The L1 friction records deposited after ``mark``. Both mark forms accepted:

    - an ``int`` (or all-digit string) is a BYTE OFFSET into the ledger file:
      records whose line starts at or after it. This is exactly the shape
      ``pipeline.ledger.Transaction`` marks (``st_size`` before its appends)
      and ``freeze`` manifests bank (``bytes``) — "everything since that
      snapshot" is ``changeset_since(p, snapshot_bytes)``.
    - any other ``str`` is a RECORD ID: records strictly after the LAST record
      carrying that id (ids repeat in the live ledger — the reconcile pass
      mints one id per flushed pair — so the last occurrence is the mark).
    - ``None`` yields the whole ledger.

    An unknown project or an id mark absent from the ledger raises ValueError:
    a silently-wrong mark would mis-size the propagation in either direction.
    Malformed lines are skipped (the tolerant-read law) but still advance the
    byte accounting.
    """
    proj = registry.resolve(project)
    if proj is None:
        raise ValueError(f"unknown project {project!r} (registry.resolve)")
    path = proj.path(proj.ledger, Path(repo_root) if repo_root else None)
    if path is None or not path.is_file():
        return []
    records: list[tuple[int, dict]] = []   # (line start offset, record)
    offset = 0
    for raw in path.read_bytes().split(b"\n"):
        line = raw.strip()
        if line:
            try:
                records.append((offset, json.loads(line.decode("utf-8"))))
            except (ValueError, UnicodeDecodeError):
                pass
        offset += len(raw) + 1
    if mark is None:
        return [r for _, r in records]
    if isinstance(mark, int) or (isinstance(mark, str) and mark.isdigit()):
        at = int(mark)
        return [r for o, r in records if o >= at]
    last = max((i for i, (_, r) in enumerate(records) if r.get("id") == mark), default=None)
    if last is None:
        raise ValueError(f"mark id {mark!r} not present in {proj.ledger}")
    return [r for _, r in records[last + 1:]]


# ---------------------------------------------------------------------------
# membership + the affected-section map
# ---------------------------------------------------------------------------

def _membership(plan: dict) -> list[tuple[str, set[str]]]:
    """(section id, everything it holds) in document order — pinned nodes plus
    beats plus figures, through the schema's accessors."""
    out = []
    for sec in schema.plan_sections(plan):
        held = set(schema.section_nodes(sec))
        held.update(sec.get("beats") or [])
        held.update(sec.get("figures") or [])
        out.append((sec.get("id"), held))
    return out


def _beat_owner(plan: dict, ref: str) -> set[str]:
    """The section owning a ``section_ref`` referent. ``section_ref`` is a
    node→spine-BEAT edge (storyboard B1), so the section whose ``beats`` hold
    the referent wins; a direct section-id match is kept as the legacy shape."""
    owners = {sec.get("id") for sec in schema.plan_sections(plan)
              if ref in (sec.get("beats") or [])}
    if not owners:
        owners = {sec.get("id") for sec in schema.plan_sections(plan)
                  if sec.get("id") == ref}
    return owners


def _record_sections(rec: dict, member: list[tuple[str, set[str]]], plan: dict) -> set[str]:
    """The section ids one L1 record perturbs. Membership hits every current
    holder; a ``set-projection`` carrying ``section_ref`` re-homes the node, so
    the referenced beat's owner joins the holders — both old and new owner
    sections are affected. Auxiliary pass-through records (data/schematic/txn)
    perturb nothing."""
    kind, node = rec.get("kind"), rec.get("node")
    if not node or kind in schema.AUXILIARY_RECORD_KINDS:
        return set()
    hit = {sid for sid, held in member if node in held}
    if kind == "set-projection" and isinstance(rec.get("value"), dict):
        ref = rec["value"].get("section_ref")
        if ref:
            hit |= _beat_owner(plan, ref)
    return hit


def affected_sections(change_records: list[dict], plan: dict) -> dict[str, set[str]]:
    """section id → the changed node ids it holds. Order-only records (spine
    reorder, edge confirmation) still land here — their holders must recompile —
    but they change ORDER, not membership: the cheap/expensive split is a
    property of the record KINDS and lives in :func:`changeset_classes`."""
    member = _membership(plan)
    out: dict[str, set[str]] = {}
    for rec in change_records:
        for sid in _record_sections(rec, member, plan):
            out.setdefault(sid, set()).add(rec.get("node"))
    return out


def changeset_classes(change_records: list[dict], plan: dict) -> dict[str, str]:
    """section id → ``cheap`` | ``expensive`` for the sections the change-set
    touches. A section is cheap only when EVERY record reaching it is
    order-only (``ORDER_ONLY_KINDS``); any substance record — essence edits,
    node CRUD, edge changes, projection re-homing — makes it expensive
    (fail-safe toward rebuild, the same posture as ``dirty_report``)."""
    member = _membership(plan)
    out: dict[str, str] = {}
    for rec in change_records:
        cls = "cheap" if rec.get("kind") in ORDER_ONLY_KINDS else "expensive"
        for sid in _record_sections(rec, member, plan):
            if out.get(sid) != "expensive":
                out[sid] = cls
    return out


# ---------------------------------------------------------------------------
# the intake door — feedback records → typed work items
# ---------------------------------------------------------------------------

def _owning_section(member: list[tuple[str, set[str]]], node: str, anchor_sec: str) -> str | None:
    """The plan section that owns a feedback record. Plan membership outranks
    the anchor (anchors pre-date restructures); when the node is multi-homed the
    anchor disambiguates if it names one of the holders, else the first holder
    in document order wins; a node held nowhere falls back to the anchor."""
    holders = [sid for sid, held in member if node and node in held]
    if anchor_sec and anchor_sec in holders:
        return anchor_sec
    if holders:
        return holders[0]
    return anchor_sec or None


def non_finding_record_kinds() -> set:
    """The one definition of the record kinds that are VERDICTS/ACTIONS about
    findings, never findings — excluded at the intake door before the kind gate.
    The adjudication family, suppressions/revocations, author-edits, and
    ``reader-report`` (R10's banked whole-artefact verdict, restart_reader.bank —
    C-wave 5 started banking it into live ledgers and intake choked on the first
    one, the C5.7 triage's headline regression; same class as the
    calibration-intent choke this comment block already records). The
    routing-completeness test imports THIS set — one producer, no drift."""
    from laplace.pipeline import adjudicate as _adj
    from laplace.pipeline import edits as _edits
    from laplace.pipeline import suppress as _sup
    return (set(_adj.ADJ_RECORD_KINDS)
            | {_sup.RECORD_KIND, _sup.REVOKE_KIND, _edits.RECORD_KIND,
               "reader-report",
               # generation-open: a generation-lifecycle ACTION marker (a run was
               # opened), carrying kind=None — never a finding. Excluded here so a live
               # ledger that has opened a generation does not choke the intake door
               # (paper_falqon, 2026-07-22, alongside the author-read/ratification fix).
               "generation-open"})


def intake_items(feedback_records: list[dict], plan: dict, net_nodes: dict) -> list[dict]:
    """One typed work item (``schema.WORK_ITEM_FIELDS``) per feedback record
    that demands generation. Routing is ``schema.KIND_TO_WORK``: a kind mapped
    to None is a comment (no item — propagate reports it as comment routing);
    a kind ABSENT from the map raises ValueError naming it, the mechanical gate
    that catches a new feedback kind arriving without routing. Records with
    ``status: resolved`` are spent — no item, no routing. A record named by a
    later record's ``supersedes`` is retired the same way: the door stays
    append-only and a correction (wrong kind, wrong routing, withdrawn)
    propagates by superseding, never by editing history.

    ``target`` is the record's node id when the node is known to the substrate
    or the plan (a ``mint`` item's node is being created, so it passes unknown);
    otherwise the owning section carries the work. ``goal`` is OBJECT-side
    routing info — the feedback kind plus the text head — never policy. The
    live ledger banks the text under ``comment``; the schema names ``text``;
    both are read.
    """
    member = _membership(plan)
    project = (plan.get("meta") or {}).get("project") or ""
    superseded = {rec["supersedes"] for rec in feedback_records
                  if rec.get("supersedes")}
    items: list[dict] = []
    # Adjudication-family records are VERDICTS about findings, never findings:
    # they ride the same ledger (the one door) but carry no generation work.
    # The first live auto-minted calibration-intent (B1's meta-signal,
    # 2026-07-10) proved intake choked on them — exclude the family exactly as
    # the route and the review surface already do (the one live-view law).
    _non_finding = non_finding_record_kinds()
    for rec in feedback_records:
        if rec.get("record") in _non_finding:
            continue
        if (rec.get("status") or "open") == "resolved":
            continue
        if rec.get("id") in superseded:
            continue
        kind = rec.get("kind")
        if kind not in schema.KIND_TO_WORK:
            raise ValueError(
                f"feedback kind {kind!r} has no routing in schema.KIND_TO_WORK — "
                "add it there; the intake door refuses unrouted kinds")
        work = schema.KIND_TO_WORK[kind]
        if work is None:
            continue
        anchor = rec.get("anchor") or {}
        node = (rec.get("node_id") or "").strip()
        section = _owning_section(member, node, (anchor.get("section") or "").strip())
        known = bool(node) and (node in net_nodes or any(node in held for _, held in member))
        target = node if node and (known or work == "mint") else (section or "")
        text = " ".join(str(rec.get("text") or rec.get("comment") or "").split())
        head = text[:140] + ("…" if len(text) > 140 else "")
        # scope (INSTRUCTION_SCOPES) decides local-vs-generic application: a
        # node/section record edits only THIS manuscript; a project/global record
        # is generic — a candidate for the author-gated profile / canon revision,
        # NOT a per-manuscript edit — so the consumer gates on `local` (this is the
        # learning-without-contamination boundary). owning_stage is the earliest
        # layer that owns the fix (WORK_TO_LAYER), attached so routing never
        # re-derives it. Scope defaults to `node` (local) so an unscoped comment
        # never silently promotes into a reusable profile. (2026-07-09: wires the
        # dormant INSTRUCTION_SCOPES into the intake door.)
        scope = (rec.get("scope") or "node").strip() or "node"
        items.append({
            "id": f"WK-{len(items) + 1:03d}-{work}",
            "kind": work,
            "owning_stage": schema.WORK_TO_LAYER.get(work),
            "scope": scope,
            "local": scope in ("node", "section"),
            "project": rec.get("project") or project,
            "target": target,
            "section": section,
            "goal": f"{kind}: {head}" if head else kind,
            "blocked_by": [],
            "source_feedback": rec.get("id"),
            "worker": WORKERS[work],
        })
    return items


# ---------------------------------------------------------------------------
# the worklist DAG — dependency-ordered, asserted acyclic
# ---------------------------------------------------------------------------

def _deps(net: dict, nid: str) -> set[str]:
    """A node's depth-1 documented logical prerequisites."""
    from laplace.research import corpus_ingest as ci
    return set(ci.inferential_dependencies(net, nid))


def _kahn(items: list[dict], ids: set[str]) -> list[dict] | None:
    """Deterministic topological order (ready set sorted by id), or None on a
    cycle. Blockers naming ids outside the worklist stay in the field but do
    not gate the ordering."""
    pending = {it["id"]: {b for b in it["blocked_by"] if b in ids} for it in items}
    by_id = {it["id"]: it for it in items}
    done: set[str] = set()
    order: list[dict] = []
    while pending:
        ready = sorted(i for i, blockers in pending.items() if blockers <= done)
        if not ready:
            return None
        for i in ready:
            order.append(by_id[i])
            done.add(i)
            del pending[i]
    return order


def worklist(items: list[dict], net: dict) -> list[dict]:
    """The dependency DAG over work items, returned in topological order.

    Blocking rules (deduped, blocker lists sorted):

    - prose ⇐ substance, SAME SECTION: a prose item for section S is blocked by
      every derive/simulate/figure/mint item whose owning section is S. Where
      substance lands and no prose item exists for S, one is synthesised — new
      substance always demands its section's prose re-run.
    - prose ⇐ substance, DEPTH-1 ANCESTRY: a substance item whose target is a
      direct derives-from dependency (``edge_index``, depth 1) of another
      item's target also blocks that item's section's prose. Depth 1 only, by
      design — the transitive climb belongs to the builder's own reconstruction
      frame, not the router. Section membership is proxied by the items
      themselves (target, section pairs); the plan is not re-read here.
    - figure ⇐ simulate, DATA: a figure item is blocked by simulate items whose
      target is the figure node's ``projection.data_source``, or whose target
      node declares the same ``data_source`` (one bank, regenerated then drawn).

    The result is asserted acyclic. On a cycle the weakest edge class is
    dropped first (ancestor, then data, then section), each drop recorded on
    the blocked item under ``cycle_dropped``; a cycle surviving all three
    classes raises.
    """
    items = [dict(it) | {"blocked_by": sorted(set(it.get("blocked_by") or []))}
             for it in items]
    nodes = net.get("nodes") or {}
    edge_class: dict[tuple[str, str], str] = {}

    def block(blocker: dict, blocked: dict, cls: str) -> None:
        if blocker["id"] == blocked["id"]:
            return
        key = (blocker["id"], blocked["id"])
        if key not in edge_class:
            edge_class[key] = cls
            blocked["blocked_by"] = sorted(set(blocked["blocked_by"]) | {blocker["id"]})

    substance = [it for it in items if it.get("kind") != "prose"]
    prose_by_sec: dict[str, list[dict]] = {}
    for it in items:
        if it.get("kind") == "prose" and it.get("section"):
            prose_by_sec.setdefault(it["section"], []).append(it)

    # same-section rule, synthesising the section's prose re-run where absent
    by_sec: dict[str, list[dict]] = {}
    for it in substance:
        if it.get("section"):
            by_sec.setdefault(it["section"], []).append(it)
    for sec in sorted(by_sec):
        if sec not in prose_by_sec:
            synth = {"id": f"WK-prose-{sec}", "kind": "prose",
                     "owning_stage": schema.WORK_TO_LAYER.get("prose"),
                     "scope": "section", "local": True,
                     "project": by_sec[sec][0].get("project", ""),
                     "target": sec, "section": sec,
                     "goal": f"prose: re-integrate new substance into section {sec}",
                     "blocked_by": [], "source_feedback": None,
                     "worker": WORKERS["prose"]}
            items.append(synth)
            prose_by_sec[sec] = [synth]
        for p in prose_by_sec[sec]:
            for s in by_sec[sec]:
                block(s, p, "section")

    # depth-1 ancestry: substance under another item's target blocks that
    # item's section's prose (existing prose items only — synthesis stays the
    # same-section rule's job)
    for s in substance:
        if s.get("target") not in nodes:
            continue
        for other in items:
            sec = other.get("section")
            if not sec or other["id"] == s["id"]:
                continue
            if s["target"] in _deps(net, other.get("target") or ""):
                for p in prose_by_sec.get(sec, []):
                    block(s, p, "ancestor")

    # figure ⇐ simulate through the shared data source
    sims = [it for it in substance if it.get("kind") == "simulate"]
    for fig in (it for it in substance if it.get("kind") == "figure"):
        fnode = nodes.get(fig.get("target"))
        ds = schema.proj_of(fnode).get("data_source") if fnode else None
        if not ds:
            continue
        for sim in sims:
            tgt = sim.get("target")
            if tgt == ds or (tgt in nodes and schema.proj_of(nodes[tgt]).get("data_source") == ds):
                block(sim, fig, "data")

    ids = {it["id"] for it in items}
    order = _kahn(items, ids)
    for weakest in ("ancestor", "data", "section"):
        if order is not None:
            break
        dropped = [key for key, cls in edge_class.items() if cls == weakest]
        by_id = {it["id"]: it for it in items}
        for blocker, blocked in dropped:
            it = by_id[blocked]
            it["blocked_by"] = [b for b in it["blocked_by"] if b != blocker]
            it.setdefault("cycle_dropped", []).append(blocker)
            del edge_class[(blocker, blocked)]
        order = _kahn(items, ids)
    assert order is not None, "worklist cycle survives every droppable edge class"
    return order


# ---------------------------------------------------------------------------
# the operator
# ---------------------------------------------------------------------------

def _net(proj: registry.Project, repo_root: Path) -> dict:
    from laplace.research import corpus_ingest as ci
    troot = proj.path(proj.tex_root, repo_root)
    if troot is None or not (troot / "main.tex").is_file():
        return {"nodes": {}, "edge_index": {}}
    return ci.corpus_network(troot, repo_root=repo_root, name=proj.name)


def propagate(project_name: str, since=None, feedback: bool = True,
              repo_root: Path | str | None = None) -> dict:
    """The propagate operator — PURE READ, emits the report; dispatch (P4)
    executes it.

    Inputs: the L1 change-set after ``since`` (see :func:`changeset_since` for
    both mark forms; ``None`` skips the change-set leg) and, when ``feedback``
    is true, the project's intake ledger. ``repo_root`` redirects ledger, plan
    and substrate reads (isolated copies in tests); ``storyboard.dirty_report``
    always reads the live repo through its own registry fence.

    Report::

        {project, since, changeset: n, comments_routed: n,
         sections: {id: {dirty, class: cheap|expensive|None, cause: [...],
                         changed_nodes, plan_vs_tex?}},
         worklist: [work items, topologically ordered],
         minimum_dispatch: [section ids needing builder re-runs, plan order]}

    Causes: ``plan-vs-tex`` (the %NODES marker diff — always expensive),
    ``changeset``/``changeset-order`` (L1 substance vs order-only), and
    ``worklist`` (new substance lands in the section, so its prose re-runs —
    expensive). ``minimum_dispatch`` is the dirty-and-expensive set; cheap-only
    sections recompile without a builder.
    """
    proj = registry.resolve(project_name)
    if proj is None:
        raise ValueError(f"unknown project {project_name!r} (registry.resolve)")
    rr = Path(repo_root) if repo_root is not None else registry._repo_root()
    plan = proj.read_plan(rr)
    if plan is None:
        raise ValueError(f"no projection plan for {project_name!r}")

    change = changeset_since(project_name, since, rr) if since is not None else []
    affected = affected_sections(change, plan)
    classes = changeset_classes(change, plan)

    fb_records = []
    if feedback and proj.feedback_ledger:
        from laplace.pipeline.ledger import read_jsonl, live_findings
        fb_path = proj.path(proj.feedback_ledger, rr)
        # the LIVE view: the mechanical panel re-scans fully each round, so
        # only its latest round is current - older panel rounds are history
        # (ledger.live_findings, the one definition every consumer shares).
        fb_records = live_findings(read_jsonl(fb_path)) if fb_path else []
    net = _net(proj, rr)
    wl = worklist(intake_items(fb_records, plan, net.get("nodes") or {}), net)
    # comments share intake's LIVE view exactly: a record retired by a later
    # ``supersedes`` is spent, so it is neither work nor a routed comment. Without
    # this the count double-reads a superseded comment intake already dropped —
    # the same append-only correction the worklist honours (a mismatch a rejected
    # challenger / a superseding re-pour would otherwise open).
    _superseded = {r["supersedes"] for r in fb_records if r.get("supersedes")}
    comments = sum(1 for r in fb_records
                   if (r.get("status") or "open") != "resolved"
                   and r.get("id") not in _superseded
                   and schema.KIND_TO_WORK.get(r.get("kind")) is None)

    from laplace.manuscript import storyboard
    dirty = {d["id"]: d for d in storyboard.dirty_report(proj.name)}

    wl_sections: dict[str, list[str]] = {}
    for it in wl:
        if it.get("section"):
            wl_sections.setdefault(it["section"], []).append(it["id"])

    sections: dict[str, dict] = {}
    for sec in schema.plan_sections(plan):
        sid = sec.get("id")
        cause, cls = [], None
        d = dirty.get(sid) or {}
        if d.get("dirty"):
            cause.append("plan-vs-tex")
            cls = "expensive"
        if sid in affected:
            order_only = classes.get(sid) == "cheap"
            cause.append("changeset-order" if order_only else "changeset")
            if not order_only:
                cls = "expensive"
            elif cls is None:
                cls = "cheap"
        if sid in wl_sections:
            cause.append("worklist")
            cls = "expensive"
        entry = {"dirty": bool(cause), "class": cls, "cause": cause,
                 "changed_nodes": sorted(affected.get(sid, ()))}
        if d.get("dirty"):
            entry["plan_vs_tex"] = {"added": d.get("added", []),
                                    "removed": d.get("removed", [])}
        sections[sid] = entry

    return {
        "project": proj.name,
        "since": since,
        "changeset": len(change),
        "comments_routed": comments,
        "sections": sections,
        "worklist": wl,
        "minimum_dispatch": [sid for sid, s in sections.items()
                             if s["dirty"] and s["class"] == "expensive"],
    }
