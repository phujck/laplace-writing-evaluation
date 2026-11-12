"""Reconstruct a node's local view of the conceptric - the ONE thing a firing runs to orient
itself at a node, instead of being handed a baked brief (his correction 2026-06-13: tell it to
reconstruct, not to read a json). The same object the navigator renders, so what he sees and what
the reconstructor sees is provably the same. Essences are attached so the view is self-sufficient
to judge from; sealed nodes stay content-free by construction.

  python scripts/reconstruct_node.py "<node-id>" [--grade N] [--lens L] [--radius R]

Typed CLI reconstruction is authority-read-only by default.  ``--record-telemetry`` is an
explicit write act for callers that intentionally want movement/materialization events.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.engine import conceptric as C  # noqa: E402
from laplace.engine import descent as D  # noqa: E402

_PATH_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".css",
    ".csv",
    ".go",
    ".h",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".mjs",
    ".py",
    ".rs",
    ".sh",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

_ATLAS_OBJECT_PREFIXES = frozenset(
    {
        "acknowledgement",
        "boundary",
        "content",
        "context",
        "event",
        "filesystem-observation",
        "join",
        "lease",
        "message-migration-supersession",
        "message-preserve-fork",
        "message-supersession",
        "reconstruction",
        "region",
        "region-lease",
        "representation",
        "revision-act",
        "revision-node",
        "seat",
        "session",
        "source",
        "subscription",
        "watch-checkpoint",
        "watcher",
    }
)


def looks_like_repository_path(node: str) -> bool:
    """Recognise path-shaped claims before semantic name routing can reinterpret them."""

    raw = str(node or "").strip()
    if not raw or raw.startswith(("canon://", "message:")):
        return False
    path = Path(raw)
    return (
        path.is_absolute()
        or "/" in raw
        or "\\" in raw
        or raw.startswith(".")
        or path.suffix.lower() in _PATH_SUFFIXES
    )


def looks_like_atlas_object_id(node: str) -> bool:
    """Claim only canonical object namespaces; bare hashes remain typed-ambiguous."""

    raw = str(node or "").strip()
    prefix, separator, suffix = raw.partition(":")
    return bool(
        separator
        and prefix in _ATLAS_OBJECT_PREFIXES
        and suffix
        and not any(character.isspace() for character in raw)
    )


def typed_target(
    node: str, explicit_kind: str | None, source: str | None, fold: str = ""
) -> tuple[str, str] | None:
    """Compatibility tuple over the single engine target registry/normalizer."""

    target = D.normalize_target(
        node, explicit_kind=explicit_kind, source=source or "", fold=fold
    )
    return None if target is None else (target["kind"], target["source"])


def _exact_descent_command(node_id: str) -> str:
    """Return the exact second leg after a semantic route chooses a handle."""

    return "/usr/bin/python3 scripts/reconstruct_node.py " + shlex.quote(node_id)


def semantic_route_frame(net: dict, query: str, *, limit: int = 8) -> dict:
    """Route a human phrase semantically without pretending ambiguity is one exact node.

    Geometry chooses a bounded frame of handles.  Resolution remains a separate, exact next
    act, carried on every candidate.  This is the conjugate boundary between semantic routing
    and typed descent: useful ambiguity is returned, not collapsed or called an unknown node.
    """

    routed = C.fire_by_grade(ROOT, net, query, limit=limit)
    candidates = []
    for hit in routed.get("hits", ()):
        node_id = str(hit.get("recovered") or "")
        if not node_id:
            continue
        candidates.append(
            {
                "id": node_id,
                "score": hit.get("score"),
                "salience": hit.get("salience"),
                "essence": hit.get("essence"),
                "why": hit.get("why"),
                "path": hit.get("path"),
                "descend_exact": _exact_descent_command(node_id),
            }
        )
    return {
        "schema_version": "laplace.semantic-route-frame/1",
        "query": query,
        "resolution_mode": "explicit-semantic-frame",
        "router": routed.get("router"),
        "geometry": routed.get("geometry"),
        "candidates": candidates,
        "candidate_count": len(candidates),
        "selection": None,
        "selection_law": (
            "routing may propose handles; resolution and mutation require an exact selected "
            "handle, so an ambiguous frame never silently becomes one leaf"
        ),
    }


def semantic_reconstruction(net: dict, node: str, *, allow_fuzzy: bool, **kwargs) -> dict:
    """Keep approximate human-name routing explicit at the mandatory CLI boundary."""

    if node in net.get("nodes", {}) or allow_fuzzy:
        result = C.reconstruct_node(net, node, **kwargs)
        if allow_fuzzy and result.get("resolved_from"):
            result["resolution_mode"] = "explicit-fuzzy-human-name"
        elif allow_fuzzy and result.get("error"):
            frame = semantic_route_frame(net, node)
            if frame["candidates"]:
                return frame
        return result
    candidates = C.resolve_name(net, node)
    return {
        "error": f"exact node does not resolve: {node}",
        "resolution_mode": "exact-refusal",
        "fuzzy_routing": "disabled; pass --fuzzy to request approximate human-name routing",
        "did_you_mean": [{"id": candidate, "score": score} for score, candidate in candidates],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("node")
    ap.add_argument(
        "--grade",
        type=int,
        default=1,
        help="target reconstruction grade; 0 is a handle, 1+ carries bounded content",
    )
    ap.add_argument("--lens", default=None)
    ap.add_argument("--radius", type=float, default=None)
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--seat", default="", help="logical seat emitting descent telemetry")
    ap.add_argument("--provider", default="", help="provider identity for descent telemetry")
    ap.add_argument("--model", default="", help="model identity for descent telemetry")
    ap.add_argument("--correlation-id", default="", help="shared goal trace id")
    ap.add_argument(
        "--record-telemetry",
        action="store_true",
        help=(
            "explicitly append reconstruction movement/materialization telemetry; absent by "
            "default so mandatory orientation cannot move the live Atlas head"
        ),
    )
    ap.add_argument(
        "--content-budget",
        type=int,
        default=D.DEFAULT_CONTENT_BUDGET,
        help="maximum exact content bytes carried by this descent; 0 returns typed BUDGET",
    )
    ap.add_argument(
        "--content-offset",
        type=int,
        default=0,
        help="exact byte continuation offset from a prior content_next_offset",
    )
    ap.add_argument(
        "--kind",
        choices=D.KINDS,
        default=None,
        help="explicit typed descent; required for lexically ambiguous handles such as sha256",
    )
    ap.add_argument(
        "--source",
        default=None,
        help="registered row source when --kind=ledger-row",
    )
    ap.add_argument(
        "--fold",
        default="",
        help="exact laplace.semantic-fold-receipt/1 handle for semantic-fold-object",
    )
    ap.add_argument(
        "--fuzzy",
        action="store_true",
        help="explicitly permit approximate human-name routing after an exact node miss",
    )
    a = ap.parse_args()

    target = typed_target(a.node, a.kind, a.source, a.fold)
    if target is not None:
        kind, source = target
        try:
            result = D.descend(
                kind=kind,
                reference=a.node,
                source=source,
                fold=a.fold,
                goal=a.lens or f"reconstruct {a.node}",
                seat_id=a.seat,
                provider=a.provider,
                model=a.model,
                correlation_id=a.correlation_id,
                content_budget=a.content_budget,
                content_offset=a.content_offset,
                record_telemetry=bool(a.record_telemetry),
            )
        except D.DescentRefused as exc:
            print(json.dumps(D.refusal_result(kind, a.node, exc), ensure_ascii=False, indent=1))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=1))
        if result.get("content_status") == "BUDGET":
            return 3
        if result.get("content_status") == "RESIDUE":
            return 1
        return 0

    net = C.load_network(ROOT)
    v = semantic_reconstruction(
        net,
        a.node,
        allow_fuzzy=bool(a.fuzzy),
        grade=a.grade,
        lens=a.lens,
        radius=a.radius,
        width=a.width,
    )
    if "error" in v:
        print(json.dumps(v))
        return 1
    if v.get("resolution_mode") == "explicit-semantic-frame":
        print(json.dumps(v, ensure_ascii=False, indent=1))
        return 0

    # attach essences so the firing sees what its neighbours ARE, not just their ids
    def ess(nid):
        return C.essence(ROOT, net, nid)

    v["essence"] = ess(v["id"])
    for link in v.get("identity", []):
        link["essence"] = ess(link["id"])
    for kid in v.get("children", []):
        kid["essence"] = kid.get("essence") or ess(kid["id"])  # keep inline section-handle text
    for lat in v.get("lateral", []):
        lat["essence"] = ess(lat["id"])
    for idn in v.get("identities", []):  # the cross-lens person + the entity's other-lens portraits
        idn["essence"] = idn.get("essence") or ess(idn["id"])
        for cor in idn.get("correlates", []):
            cor["essence"] = ess(cor["id"])
    for band in v.get("cross_lens", []):
        for nb in band.get("neighbours", []):
            nb["essence"] = ess(nb["id"])
    if int(v.get("target_grade") or 0) >= 1:
        if (v.get("flags") or {}).get("sealed"):
            v.update(
                content=None,
                content_status="RESIDUE",
                content_truncated=False,
                content_omitted=0,
                content_handle=None,
                content_residue={
                    "schema_version": "laplace.engine.descent-residue/1",
                    "code": "SEALED",
                    "guidance": "the sealed node remains refs-only at every grade",
                },
            )
        else:
            path = ROOT / v["id"]
            try:
                if path.is_file():
                    projection = D.bounded_file_content(
                        repo_root=ROOT,
                        reference=v["id"],
                        budget=a.content_budget,
                        offset=a.content_offset,
                    )
                else:
                    materialized = C.node_content(ROOT, v["id"])
                    if materialized.get("error"):
                        raise D.DescentRefused(
                            str(materialized["error"]),
                            residue={
                                "schema_version": "laplace.engine.descent-residue/1",
                                "code": "UNRESOLVABLE",
                                "node": v["id"],
                            },
                        )
                    content = materialized.get("content", materialized.get("profile"))
                    if content is None:
                        raise D.DescentRefused(
                            "node has no exact content source",
                            residue={
                                "schema_version": "laplace.engine.descent-residue/1",
                                "code": "UNRESOLVABLE",
                                "node": v["id"],
                            },
                        )
                    if isinstance(content, str):
                        raw = content
                        media_type = "text/plain; charset=utf-8"
                    else:
                        raw = json.dumps(
                            content,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            default=str,
                        )
                        media_type = "application/json"
                    projection = D.bounded_content(
                        handle=v["id"],
                        content=raw,
                        media_type=media_type,
                        budget=a.content_budget,
                        offset=a.content_offset,
                    )
                    projection["media_type"] = media_type
                    projection["provenance"] = {
                        key: value
                        for key, value in materialized.items()
                        if key not in {"content", "profile"}
                    }
                v["content_contract_schema"] = projection.pop("schema_version")
                v.update(projection)
            except D.DescentRefused as exc:
                v.update(
                    content=None,
                    content_status="RESIDUE",
                    content_truncated=False,
                    content_omitted=0,
                    content_handle=None,
                    content_residue=exc.details.get(
                        "residue",
                        {
                            "schema_version": "laplace.engine.descent-residue/1",
                            "code": "UNRESOLVABLE",
                            "error": str(exc),
                        },
                    ),
                )
    print(json.dumps(v, ensure_ascii=False, indent=1))
    if v.get("content_status") == "BUDGET":
        return 3
    if v.get("content_status") == "RESIDUE":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
