"""Reduce a corpus-friction event log to the current projection node state.

The friction ledger is an append-only event log. It is useful for history and
candidate discovery, but it is a poor direct input to manuscript projection:
superseded names and old postures remain present in the raw rows. This reducer
builds the current per-node state used by an evolutionary projection pass.

Usage:
    python scripts/reduce_projection_state.py \
        corpus_friction/subset-sum-itqde.jsonl \
        "synthetics papers/subset-sum-itqde/manuscript/projection_plan.json" \
        --out "synthetics papers/subset-sum-itqde/manuscript/v2_reprojection/node_state_reduction.json"
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return rows


def planned_nodes(plan: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    sections: dict[str, list[str]] = defaultdict(list)
    roles: dict[str, list[str]] = defaultdict(list)
    for block in list(plan.get("sections", [])) + list(plan.get("appendices", [])):
        sid = block.get("id", "")
        for role_name in ("beats", "nodes_in_order"):
            for node in block.get(role_name, []) or []:
                if sid and sid not in sections[node]:
                    sections[node].append(sid)
                role = f"{sid}:{role_name}"
                if role not in roles[node]:
                    roles[node].append(role)
    return dict(sections), dict(roles)


def reduce_rows(rows: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    sections_by_node, roles_by_node = planned_nodes(plan)
    nodes: dict[str, dict[str, Any]] = {}
    edge_state: dict[tuple[str, str], dict[str, Any]] = {}
    event_counts = Counter()
    status_counts = Counter()

    def ensure(node_id: str) -> dict[str, Any]:
        if node_id not in nodes:
            nodes[node_id] = {
                "node": node_id,
                "node_kind": None,
                "parent": None,
                "essence": None,
                "projection": {},
                "spine": [],
                "event_count": 0,
                "event_kinds": {},
                "authors": [],
                "statuses": [],
                "first_event_ts": None,
                "last_event_ts": None,
                "planned_sections": sections_by_node.get(node_id, []),
                "planned_roles": roles_by_node.get(node_id, []),
                "incoming": [],
                "outgoing": [],
            }
        return nodes[node_id]

    for row in rows:
        kind = row.get("kind") or ""
        node_id = row.get("node")
        target = row.get("target")
        event_counts[kind] += 1
        status_counts[row.get("status") or ""] += 1
        if not node_id:
            continue
        node = ensure(node_id)
        node["event_count"] += 1
        node["event_kinds"][kind] = node["event_kinds"].get(kind, 0) + 1
        by = row.get("by")
        if by and by not in node["authors"]:
            node["authors"].append(by)
        status = row.get("status") or ""
        if status not in node["statuses"]:
            node["statuses"].append(status)
        ts = row.get("ts")
        if ts and node["first_event_ts"] is None:
            node["first_event_ts"] = ts
        if ts:
            node["last_event_ts"] = ts

        if kind == "add-node":
            node["node_kind"] = row.get("node_kind", node.get("node_kind"))
            node["parent"] = row.get("parent", node.get("parent"))
            if row.get("essence") is not None:
                node["essence"] = row["essence"]
        elif kind == "edit-essence":
            node["essence"] = row.get("value")
        elif kind == "set-kind":
            node["node_kind"] = row.get("value")
        elif kind == "set-projection":
            value = row.get("value")
            if isinstance(value, dict):
                node["projection"].update(value)
            elif value is not None:
                node["projection"]["value"] = value
        elif kind == "set-spine":
            spine = {
                "ord": row.get("ord"),
                "narrative": row.get("narrative"),
                "ts": row.get("ts"),
            }
            node["spine"].append(spine)
        elif kind == "unset-spine":
            node["spine"] = []
        elif kind == "add-edge" and target:
            edge_state[(node_id, target)] = {
                "source": node_id,
                "target": target,
                "value": row.get("value"),
                "last_event_ts": row.get("ts"),
            }
            ensure(target)
        elif kind == "remove-edge" and target:
            edge_state.pop((node_id, target), None)
            ensure(target)

    for edge in edge_state.values():
        source = edge["source"]
        target = edge["target"]
        nodes[source]["outgoing"].append(target)
        nodes[target]["incoming"].append(source)

    planned = set(sections_by_node)
    for node_id, node in nodes.items():
        node["incoming"] = sorted(set(node["incoming"]))
        node["outgoing"] = sorted(set(node["outgoing"]))
        node["is_planned"] = node_id in planned

    output_nodes = {
        node_id: nodes[node_id]
        for node_id in sorted(nodes, key=lambda n: (not nodes[n]["is_planned"], n))
    }

    return {
        "project": plan.get("meta", {}).get("project"),
        "artefact": plan.get("meta", {}).get("artefact"),
        "source": {
            "friction_rows": len(rows),
            "plan_sections": len(plan.get("sections", [])),
            "plan_appendices": len(plan.get("appendices", [])),
        },
        "counts": {
            "events_by_kind": dict(event_counts),
            "events_by_status": dict(status_counts),
            "reduced_nodes": len(nodes),
            "reduced_edges": len(edge_state),
            "planned_nodes": len(planned),
            "planned_nodes_missing_from_reduction": sorted(planned - set(nodes)),
            "unplanned_reduced_nodes": sorted(set(nodes) - planned),
        },
        "warnings": [
            "The raw friction ledger is an append-only event log; use this reduction, not raw replay, for projection.",
            "Projection terms and aliases remain author-gated where the plan marks them as working names.",
        ],
        "nodes": output_nodes,
        "edges": sorted(edge_state.values(), key=lambda e: (e["source"], e["target"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("friction_jsonl", type=Path)
    parser.add_argument("projection_plan", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = read_jsonl(args.friction_jsonl)
    plan = json.loads(args.projection_plan.read_text(encoding="utf-8"))
    reduced = reduce_rows(rows, plan)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reduced, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    counts = reduced["counts"]
    print(
        "reduced "
        f"{reduced['source']['friction_rows']} events -> "
        f"{counts['reduced_nodes']} nodes, {counts['reduced_edges']} edges; "
        f"planned missing: {len(counts['planned_nodes_missing_from_reduction'])}"
    )


if __name__ == "__main__":
    main()
