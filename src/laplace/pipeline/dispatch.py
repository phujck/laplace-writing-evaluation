"""compile_dispatch — the one path from (target, goal) to an agent prompt.

The law this mechanises (his, 2026-06-13, made structural 2026-07-08): an agent
prompt is ``reconstruct(node, goal)``, never ``read(file)``. Every compiled
prompt opens with the graded-node kernel — the grade-0 handle of the WHOLE and
where this piece sits — then the local OBJECT at depth, then POLICY as handles
into the global canon. The local and the global, in every dispatch, so no
instance can act without seeing both.

Hand-written briefs cease to exist as a path: the storyboard's headless rebuild
and the project-fixedpoint workflow both consume this compiler's output, and
every compile logs the canon skills it rides (``telemetry`` ``execute`` events —
the fitness signal the assess loop was starving for).

Worker types (schema.WORK_KINDS): ``prose`` compiles from the section's CLOSED
narrative packet (the 2026-07-09 staged rebuild — the retired briefs are no
longer a path) with the versioned voice profile joined ONLY here and at the
weld; ``structure``/``narrative`` compile the staged planning workers;
``derive``/``mint`` compile a node-local reconstruction frame from the corpus
network; ``figure``/``simulate`` are script-backed when the node's provenance
names its generator (mechanical work stays mechanical) and agent-backed
otherwise; ``render`` is always script-backed (the deterministic tex backend).

Context isolation (mandate §13): the prose prompt carries NO graded-node
kernel and NO policy handles — engine framing in a prose context is the §1.8
scaffolding-leak class. The packet, the registries, the profile: nothing else.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from laplace.pipeline import narrative, pathsafe, registry, schema, structural

#: The one voice artifact (overridable per manuscript via the spec record's
#: ``voice_profile`` field — §14 versioning). Supplied ONLY to the prose
#: realiser and the weld.
VOICE_PROFILE_PATH = "profiles/voice/gerard-technical-v1.md"


def _voice_dispatch_context(project, root, contract=None):
    """Use the real selection owner, retaining a recorded section override.

    Ordinary project selection/genre/guidance comes from manuscript_spec.
    A legacy explicit section-contract profile remains local to that packet.
    """
    from laplace.manuscript import writing_style
    override = (contract or {}).get('voice_profile')
    value = writing_style.context(project, root, profile_override=override)
    text = value['content']
    if value.get('guidance'):
        text += '\n\nPROJECT VOICE GUIDANCE\n' + value['guidance']
    if value.get('genre'):
        text += '\n\nPROJECT GENRE\n' + value['genre']
    return value, text

#: canon handles ridden by a compiled dispatch → the skill whose fitness they feed
_HANDLE_SKILLS = {
    "canon://skills/figure_standard": "figure_standard",
    "canon://skills/latex_forge": "latex_forge",
    "canon://skills/welder": "welder",
}


#: The methods fibre (``corpus_friction/methods.jsonl``): house style, working
#: methods and standards as typed ``law``/``forbids`` rows, so they reconstruct WITH
#: the task instead of being re-derived from narrative per session.
METHODS_STORE = "corpus_friction/methods.jsonl"

#: worker kind → the fibre task class its packet carries. The compiler knows the
#: worker; the fibre is filed by what the work IS.
WORKER_TASK_CLASS = {
    "prose": "manuscript",
    "narrative": "manuscript",
    "structure": "manuscript",
    "mint": "manuscript",
    "render": "manuscript",
    "figure": "figures",
    "simulate": "figures",
    "derive": "verification",
}

#: a method row banked without a ``task_class`` is a house law nobody scoped: it
#: rides as ``all`` rather than riding nothing (a fibre row nothing reads is a row
#: that does not exist — the defect this wiring cures).
_UNCLASSED_TASK_CLASS = "all"

#: ``meta`` is the fibre's own design (M-README). It documents the wiring; it is not
#: law for a builder, so it never rides a packet.
_METHODS_EXCLUDED_CLASSES = frozenset({"meta"})

#: The voice severance, applied to the fibre. ``VOICE_PROFILE_PATH`` above states the
#: standing rule: the voice artifact is supplied ONLY to the prose realiser and the
#: weld. A method row that talks about voice IS voice instruction, so it rides only the
#: workers voice already reaches — the narrative planner, the structure planner and
#: every node worker are severed from it, exactly as they are severed from the profile.
#: Without this the fibre would re-open the seam the severance closes: a planner told
#: how the prose should sound plans to a register it does not own.
_VOICE_BEARING_WORKERS = frozenset({"prose"})

#: textual and fail-closed, the same mechanism the invariant test uses: the cost of
#: dropping a borderline row from a planner packet is one rule restated at the
#: realiser; the cost of a miss is the severance broken. ``invoice`` is the one
#: substring collision worth spelling out.
_VOICE_TOKEN = re.compile(r"(?<!in)voice", re.IGNORECASE)


# This Python boundary is D1 only.  The JavaScript/MJS ``agent()`` sites and
# RAPTOR's ``claude -p`` path remain an explicit unpaid follow-on.
_D2_OPEN = {
    "status": "OPEN",
    "scope": "22-js-mjs-agent-sites-and-raptor-claude-p",
}

_DISPATCH_RECONSTRUCTION_SCHEMA = "laplace.dispatch-reconstruction/1"
_RECONSTRUCTION_CLAIM_SCHEMA = "laplace.dispatch-reconstruction-claim/1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _valid_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", value)
    )


def _reconstruction_claim(
    reconstruction: Mapping[str, Any], *, node: str, goal: str
) -> dict[str, Any]:
    """Return the exact receipt preimage carried by a reconstruction."""
    return {
        "schema_version": _RECONSTRUCTION_CLAIM_SCHEMA,
        "kind": reconstruction.get("kind"),
        "node": node,
        "goal_utf8": goal,
        "content_status": reconstruction.get("content_status"),
        "content_handle": reconstruction.get("content_handle"),
        "read_only": reconstruction.get("read_only"),
        "transition_claim": reconstruction.get("transition_claim"),
        "authority_write": reconstruction.get("authority_write"),
        "current_root": reconstruction.get("current_root"),
        "authority_root": reconstruction.get("authority_root"),
        "drift_token": reconstruction.get("drift_token"),
        "integrity_boundary": reconstruction.get("integrity_boundary"),
    }


STAGE_STORES = ("corpus_friction/campaign.jsonl", "corpus_friction/work_orders.jsonl")


def reconstruct_stage(reference: str, goal: str, *, repo_root: Path,
                      content_budget: int = 400_000) -> dict[str, Any]:
    """Exact latest definition by id; gate/verdict rows cannot replace a stage.

    This dispatch-specific kind is bounded to the two stage-owning stores. Missing
    admission fields remain a refusal, never inferred from titles or neighbouring rows.
    """
    found = []
    for rel in STAGE_STORES:
        path = repo_root / rel
        latest = None
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as stream:
            for line_number, raw in enumerate(stream, 1):
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except ValueError:
                    return {"kind": "stage", "reference": reference, "goal": goal,
                            "error": "STAGE_STORE_MALFORMED", "source": rel,
                            "line": line_number}
                if isinstance(row, dict) and row.get("id") == reference and row.get("record") in (
                        "stage", "work-order", "work_order"):
                    latest = (row, raw, line_number)
        if latest:
            found.append((rel, *latest))
    if len(found) != 1:
        return {"kind": "stage", "reference": reference, "goal": goal,
                "error": "STAGE_NOT_FOUND" if not found else "STAGE_AMBIGUOUS"}
    rel, row, raw, line_number = found[0]
    complete = len(raw.encode("utf-8")) <= content_budget
    return {"schema_version": "laplace.typed-descent/1", "kind": "stage",
            "reference": reference, "goal": goal, "value": row,
            "read_only": True, "transition_claim": "none", "authority_write": "none",
            "content": raw if complete else "", "content_handle": _sha256(raw.encode("utf-8")),
            "content_bytes": len(raw.encode("utf-8")), "content_budget": content_budget,
            "content_status": "COMPLETE" if complete else "BUDGET",
            "content_truncated": not complete,
            "provenance": {"path": rel, "line": line_number, "id_field": "id"}}


def _admit_typed_descent_custody_off(
    *, target: str, goal: str, worker: str, reconstruction: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """THE CUSTODY SWITCH (his ruling 2026-09-14, laplace.representation.custody_mode): while custody is OFF a
    dispatch carries an exact typed descent of its node - content verified by hash, read-only,
    no transition claim - and NOT an atlas authority proof (current_root / authority_root /
    drift_token / the checksummed-crutch boundary), which is the runtime-custody layer that
    this mode switches off. The law the kernel keeps: reconstruct(node, goal), exact bytes,
    never a filename read or a summary. What it drops: the seat. Retires with the crutch."""

    def receipt(status: str, reason: str, *, content_handle: str = "") -> dict[str, Any]:
        out = _dispatch_reconstruction_phase_receipt(
            node=target, goal=goal, reconstruction_content_handle=content_handle,
            reconstruction_receipt_handle="", current_root="", authority_root="",
            drift_token=None, worker=worker, target=target, status=status, reason=reason,
        )
        out["custody_mode"] = "OFF"
        out["receipt_handle"] = _sha256(_canonical_json({k: v for k, v in out.items() if k != "receipt_handle"}))
        return out

    if reconstruction is None:
        return receipt("REFUSED", "MISSING_RECONSTRUCTION")
    if not isinstance(reconstruction, Mapping):
        return receipt("REFUSED", "MALFORMED_RECONSTRUCTION")
    if reconstruction.get("reference") != target:
        return receipt("REFUSED", "NODE_MISMATCH")
    if reconstruction.get("goal") != goal:
        return receipt("REFUSED", "GOAL_MISMATCH")
    if reconstruction.get("kind") not in ("atlas-object", "repository-file", "node", "stage"):
        return receipt("REFUSED", "KIND_MISMATCH")
    if reconstruction.get("kind") == "stage" and reconstruction.get("error"):
        return receipt("REFUSED", str(reconstruction["error"]))
    content = reconstruction.get("content")
    content_handle = reconstruction.get("content_handle")
    if not isinstance(content, str) or not _valid_sha256(content_handle):
        return receipt("REFUSED", "MALFORMED_CONTENT")
    if reconstruction.get("content_status") != "COMPLETE" or reconstruction.get("content_truncated"):
        return receipt("REFUSED", "RECONSTRUCTION_TRUNCATED", content_handle=content_handle)
    if _sha256(content.encode("utf-8")) != content_handle:
        return receipt("REFUSED", "CONTENT_HANDLE_MISMATCH", content_handle=content_handle)
    if (
        reconstruction.get("read_only") is not True
        or reconstruction.get("transition_claim") != "none"
        or reconstruction.get("authority_write", "none") != "none"
    ):
        return receipt("REFUSED", "READ_AUTHORITY_MISMATCH", content_handle=content_handle)
    admitted = receipt("ADMITTED", "CUSTODY-OFF-TYPED-DESCENT-BY-HASH", content_handle=content_handle)
    if reconstruction.get("kind") == "stage":
        try:
            stage = json.loads(content)
        except ValueError:
            return receipt("REFUSED", "STAGE_CONTENT_MALFORMED", content_handle=content_handle)
        if not isinstance(stage, dict) or stage.get("id") != target or stage.get("record") not in (
                "stage", "work-order", "work_order"):
            return receipt("REFUSED", "STAGE_IDENTITY_MISMATCH", content_handle=content_handle)
        if not stage.get("admitted_by") or not stage.get("first_act"):
            return receipt("REFUSED", "STAGE_ADMISSION_FIELDS_MISSING", content_handle=content_handle)
        admitted["stage"] = {k: stage[k] for k in ("id", "admitted_by", "first_act")}
        admitted["receipt_handle"] = _sha256(_canonical_json({k: v for k, v in admitted.items() if k != "receipt_handle"}))
    return admitted


def _dispatch_reconstruction_phase_receipt(
    *,
    node: str,
    goal: str,
    reconstruction_content_handle: str,
    reconstruction_receipt_handle: str,
    current_root: str,
    authority_root: str,
    drift_token: Any,
    worker: str,
    target: str,
    status: str,
    reason: str,
) -> dict[str, Any]:
    body = {
        "schema_version": _DISPATCH_RECONSTRUCTION_SCHEMA,
        "node": node,
        "goal_utf8": goal,
        "goal_bytes_hex": goal.encode("utf-8").hex(),
        "reconstruction_content_handle": reconstruction_content_handle,
        "reconstruction_receipt_handle": reconstruction_receipt_handle,
        "current_root": current_root,
        "authority_root": authority_root,
        "drift_token": drift_token,
        "worker": worker,
        "target": target,
        "admission_result": {"status": status, "reason": reason},
        "integrity_boundary": {
            "status": "CHECKSUMMED-CRUTCH",
            "crutch_id": "CR-C2A-CHECKSUMMED-LIVE-AUTHORITY-20260828",
            "residual": (
                "graph-sidecar duplicate is not event/CAS-root authenticated; "
                "stopped-writer deep verification remains required"
            ),
        },
        "d2": dict(_D2_OPEN),
    }
    return {**body, "receipt_handle": _sha256(_canonical_json(body))}


def _jit_dispatch_authority(
    repo_root: Path | None,
    *,
    node: str,
    goal: str,
    expected_current_root: str,
) -> Mapping[str, Any]:
    """Mockable adapter onto the concurrent pure keyed verifier."""
    try:
        from laplace.representation import atlas_bridge

        verifier = atlas_bridge.verify_atlas_object_current_root
    except (AttributeError, ImportError) as exc:
        return {
            "status": "UNAVAILABLE",
            "reason": f"jit-verifier-unavailable:{type(exc).__name__}",
        }
    try:
        del repo_root, goal  # the stable bridge face is root/reference keyed
        result = verifier(
            reference=node,
            expected_current_root=expected_current_root,
        )
    except Exception as exc:  # noqa: BLE001 - converted to a typed closed gate
        detail = getattr(exc, "detail", {})
        status = str(detail.get("code") or detail.get("status") or "UNAVAILABLE").upper()
        return {
            "status": status,
            "reason": f"jit-verifier-refused:{type(exc).__name__}",
            **({"dirty_paths": detail["dirty_paths"]} if "dirty_paths" in detail else {}),
        }
    if not isinstance(result, Mapping):
        return {"status": "UNAVAILABLE", "reason": "jit-verifier-malformed"}
    return result


def _admit_dispatch_reconstruction(
    *,
    target: str,
    goal: str,
    worker: str,
    repo_root: Path | None,
    reconstruction: Mapping[str, Any] | None,
    perform_jit: bool = True,
) -> dict[str, Any]:
    """Validate a reconstruction without touching compiler/fence/worker faces."""

    def receipt(
        status: str,
        reason: str,
        *,
        content_handle: str = "",
        reconstruction_receipt_handle: str = "",
        current_root: str = "",
        authority_root: str = "",
        drift_token: Any = None,
    ) -> dict[str, Any]:
        return _dispatch_reconstruction_phase_receipt(
            node=target,
            goal=goal,
            reconstruction_content_handle=content_handle,
            reconstruction_receipt_handle=reconstruction_receipt_handle,
            current_root=current_root,
            authority_root=authority_root,
            drift_token=drift_token,
            worker=worker,
            target=target,
            status=status,
            reason=reason,
        )

    if reconstruction is None:
        return receipt("REFUSED", "MISSING_RECONSTRUCTION")
    if not isinstance(reconstruction, Mapping):
        return receipt("REFUSED", "MALFORMED_RECONSTRUCTION")
    node = reconstruction.get("reference")
    if not isinstance(node, str) or node != target:
        return receipt("REFUSED", "NODE_MISMATCH")
    reconstruction_goal = reconstruction.get("goal")
    if not isinstance(reconstruction_goal, str) or reconstruction_goal != goal:
        return receipt("REFUSED", "GOAL_MISMATCH")
    if reconstruction.get("kind") != "atlas-object":
        return receipt("REFUSED", "KIND_MISMATCH")

    content_status = reconstruction.get("content_status")
    if content_status != "COMPLETE":
        status_reason = {
            "BUDGET": "RECONSTRUCTION_BUDGET",
            "TRUNCATED": "RECONSTRUCTION_TRUNCATED",
            "REFUSED": "RECONSTRUCTION_REFUSED",
        }.get(content_status, "RECONSTRUCTION_NOT_COMPLETE")
        return receipt("REFUSED", status_reason)

    content = reconstruction.get("content")
    content_handle = reconstruction.get("content_handle")
    if not isinstance(content, str) or not _valid_sha256(content_handle):
        return receipt("REFUSED", "MALFORMED_CONTENT")
    if _sha256(content.encode("utf-8")) != content_handle:
        return receipt(
            "REFUSED", "CONTENT_HANDLE_MISMATCH", content_handle=content_handle
        )
    if (
        reconstruction.get("read_only") is not True
        or reconstruction.get("transition_claim") != "none"
        or reconstruction.get("authority_write") != "none"
    ):
        return receipt(
            "REFUSED", "READ_AUTHORITY_MISMATCH", content_handle=content_handle
        )

    current_root = reconstruction.get("current_root")
    authority_root = reconstruction.get("authority_root")
    drift_token = reconstruction.get("drift_token")
    if (
        not _valid_sha256(current_root)
        or not _valid_sha256(authority_root)
        or drift_token is None
    ):
        return receipt(
            "REFUSED", "MALFORMED_AUTHORITY_PROOF", content_handle=content_handle
        )
    if reconstruction.get("integrity_boundary") != "CHECKSUMMED-CRUTCH":
        return receipt(
            "REFUSED", "INTEGRITY_BOUNDARY_MISMATCH", content_handle=content_handle
        )
    supplied_claim = reconstruction.get("reconstruction_receipt")
    supplied_claim_handle = reconstruction.get("reconstruction_receipt_handle")
    claim = _reconstruction_claim(reconstruction, node=target, goal=goal)
    try:
        claim_handle = _sha256(_canonical_json(claim))
    except (TypeError, ValueError):
        return receipt(
            "REFUSED", "MALFORMED_RECONSTRUCTION", content_handle=content_handle
        )
    if supplied_claim != claim or supplied_claim_handle != claim_handle:
        return receipt(
            "REFUSED",
            "RECEIPT_HANDLE_MISMATCH",
            content_handle=content_handle,
            reconstruction_receipt_handle=(
                supplied_claim_handle if isinstance(supplied_claim_handle, str) else ""
            ),
            current_root=current_root,
            authority_root=authority_root,
            drift_token=drift_token,
        )

    common = {
        "content_handle": content_handle,
        "reconstruction_receipt_handle": claim_handle,
        "current_root": current_root,
        "authority_root": authority_root,
        "drift_token": drift_token,
    }
    if not perform_jit:
        return receipt("ADMITTED", "STATIC-EXACT", **common)

    # This is intentionally the last external operation before compilation.
    jit = _jit_dispatch_authority(
        repo_root,
        node=target,
        goal=goal,
        expected_current_root=current_root,
    )
    jit_status = str(jit.get("status") or "UNAVAILABLE").upper()
    if jit.get("moved") is True or jit_status == "MOVED":
        return receipt("REFUSED", "AUTHORITY_MOVED", **common)
    if jit.get("ambiguous") is True or jit_status == "AMBIGUOUS":
        return receipt("REFUSED", "AUTHORITY_AMBIGUOUS", **common)
    if (
        jit.get("dirty") is True
        or bool(jit.get("dirty_paths"))
        or jit_status == "DIRTY"
    ):
        return receipt("REFUSED", "AUTHORITY_DIRTY", **common)
    metrics = jit.get("read_metrics")
    if not isinstance(metrics, Mapping):
        metrics = {}
    suffix_events = jit.get("suffix_events", metrics.get("suffix_rows_loaded"))
    if (
        not isinstance(suffix_events, int)
        or isinstance(suffix_events, bool)
        or suffix_events < 0
    ):
        return receipt("REFUSED", "CHECKPOINT_UNAVAILABLE", **common)
    if suffix_events > 64:
        return receipt("REFUSED", "SUFFIX_LIMIT_EXCEEDED", **common)
    if jit_status != "CURRENT":
        return receipt("REFUSED", "CHECKPOINT_UNAVAILABLE", **common)
    if (
        jit.get("read_only") is not True
        or jit.get("transition_claim") != "none"
        or jit.get("authority_write") != "none"
    ):
        return receipt("REFUSED", "JIT_READ_AUTHORITY_MISMATCH", **common)
    if jit.get("current_root") != current_root:
        return receipt("REFUSED", "CURRENT_ROOT_MISMATCH", **common)
    if jit.get("authority_root") != authority_root:
        return receipt("REFUSED", "AUTHORITY_ROOT_MISMATCH", **common)
    if jit.get("drift_token") != drift_token:
        return receipt("REFUSED", "DRIFT_TOKEN_MISMATCH", **common)
    return receipt("ADMITTED", "EXACT", **common)


def _row_names_voice(row: dict[str, Any]) -> bool:
    """True when any part of the row a packet carries — law, forbids, refs, amendments —
    names voice. The refs count: a ref is a pointer the builder is invited to descend."""
    return bool(_VOICE_TOKEN.search(json.dumps(row, ensure_ascii=False)))


def _method_row_refs(row: dict[str, Any]) -> list[str]:
    """Evidence rides refs-only — the builder descends to it if it disputes the rule."""
    raw = row.get("evidence") or row.get("source") or ""
    parts = [p.strip() for p in re.split(r"\s*[·;]\s*|\s*,\s(?=[A-Za-z0-9_./-]+/)", str(raw))]
    return [p for p in parts if p]


def method_rows_for(task_class: str, repo_root: Path | None = None,
                    include_all: bool = True) -> list[dict[str, Any]]:
    """The methods fibre, projected onto one task class (``corpus_friction/methods.jsonl``).

    Returns the rows of ``task_class`` plus, when ``include_all``, every ``all`` row —
    each carried as ``{id, task_class, law, forbids, refs, amended}`` and nothing more.
    A row rides as law + forbids ONLY: the evidence is refs, which a builder descends to
    if it disputes the rule, and never inlined prose.

    Amendment rows (``record: amendment``) do not ride on their own; they attach to the
    row they ``target`` as ``amended``. An amendment may carry an explicit
    ``replacement_law``/``replacement_forbids``; the loader then projects that replacement
    while retaining the amendment label, so the append-only store preserves the historical
    rule without continuing to generate from it.

    Never raises: a missing or malformed store returns ``[]``, so the fibre cannot
    break a compile.
    """
    root = repo_root or source_tree()
    store = Path(root) / METHODS_STORE
    wanted = {task_class} | ({_UNCLASSED_TASK_CLASS} if include_all else set())
    wanted -= _METHODS_EXCLUDED_CLASSES
    if not wanted:
        return []
    rows: list[dict[str, Any]] = []
    amendments: dict[str, list[dict[str, Any]]] = {}
    try:
        text = store.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(r, dict) or not r.get("id"):
            continue
        if r.get("record") == "amendment":
            tgt = r.get("target")
            note = " ".join(str(r.get("note") or r.get("text") or "").split())
            if tgt and note:
                amendments.setdefault(str(tgt), []).append({
                    "id": str(r["id"]),
                    "label": f"{r['id']}: {note}",
                    "law": (" ".join(str(r.get("replacement_law") or "").split()) or None),
                    "forbids": (" ".join(str(r.get("replacement_forbids") or "").split()) or None),
                    "refs": _method_row_refs(r),
                })
            continue
        cls = r.get("task_class") or _UNCLASSED_TASK_CLASS
        if cls not in wanted:
            continue
        law = " ".join(str(r.get("law") or r.get("text") or "").split())
        if not law:
            continue
        rows.append({"id": str(r["id"]), "task_class": cls, "law": law,
                     "forbids": " ".join(str(r.get("forbids") or "").split()) or None,
                     "refs": _method_row_refs(r)})
    for row in rows:
        amend = amendments.get(row["id"])
        if amend:
            row["amended"] = [item["label"] for item in amend]
            row["amendment_refs"] = [
                {"amendment": item["id"], "refs": item["refs"]}
                for item in amend if item["refs"]
            ]
            for item in amend:
                if item["law"]:
                    row["law"] = item["law"]
                if item["forbids"]:
                    row["forbids"] = item["forbids"]
                row["refs"] = list(dict.fromkeys(row["refs"] + item["refs"]))
    return rows


def _methods_fence(rows: list[dict[str, Any]]) -> str:
    """Render the fibre rows as the packet's METHODS block — the standing law for this
    task class, stated once, refs-only for its evidence (register law)."""
    body = ("The standing methods for this task class, reconstructed from "
            f"{METHODS_STORE}. These are law, not advice: each row states what holds and "
            "what it forbids. The evidence is refs — descend to it only to dispute a rule.\n"
            + json.dumps(rows, ensure_ascii=False, indent=1))
    return schema.fence("METHODS", body)


def _log_ridden(target: str, extra: tuple[str, ...] = ()) -> list[str]:
    """Feed the fitness loop: compiling a dispatch IS exercising the
    orchestration protocol, and the handles it carries are the skills ridden."""
    from laplace.engine import telemetry
    skills = ["orchestrated_generation"] + [
        _HANDLE_SKILLS[h] for h in schema.POLICY_HANDLES if h in _HANDLE_SKILLS
    ] + list(extra)
    for sk in skills:
        telemetry.log("execute", skill=sk, ok=True, target=target)
    return skills


def _contribution_rank_block(rank: Any) -> str:
    """Format ``plan.meta.contribution_rank`` — the one authored judgement that
    binds every section (his return-path push, 2026-07-13) — into the kernel's
    CONTRIBUTION RANK block. The parse (plain claim strings, or ``{rank, claim,
    role}`` dicts with an excluded/exploratory role demoted) is shared with the
    narrative packet's content-framed block via ``schema.contribution_rank_lines``
    - ONE authored formatter, two frames (this one is POLICY voice; the prose
    packet's is CONTENT voice — §13 keeps them from crossing). Empty/None → ""
    (the block never appears, so a rank-less plan compiles byte-identically to
    today)."""
    primary, excluded = schema.contribution_rank_lines(rank)
    if not primary and not excluded:
        return ""
    lines = ["CONTRIBUTION RANK (authored once, plan meta - binds every section):"]
    lines += primary
    if excluded:
        lines.append("EXCLUDED/exploratory: " + "; ".join(excluded))
    return "\n".join(lines)


def kernel(project: registry.Project | None, target: str, goal: str,
           worker: str, rank: Any | None = None, repo_root: Path | None = None) -> str:
    """The graded-node kernel (canon://engine/graded_node, grade-0): the whole,
    the piece, the law. Rides EVERY compiled prompt — the down-guarantee.

    ``rank`` is ``plan.meta.contribution_rank`` (the one authored judgement that
    binds every section): when present it appends a CONTRIBUTION RANK block after
    the kernel header. When absent (the default) the header is byte-identical to
    before — the threading is strictly additive (his return-path push,
    2026-07-13)."""
    whole = (f"the Laplace Engine projecting '{project.name}' "
             f"({project.kind}; artefact under {project.target_dir})"
             if project else "the Laplace Engine")
    head = (
        f"You are one node in a graded hierarchy - {whole}.\n"
        f"Your piece: {target} - {goal} (worker: {worker}).\n"
        "Hold the map, not the bodies: your OBJECT channel carries your piece at "
        "depth; resolve canon:// handles on demand; reconstruct what you need and "
        "never flat-read beyond your piece. Close your own loop; an unmet demand "
        "is a typed friction to report, never a confabulation; return your piece "
        "and the caller integrates. (canon://engine/graded_node)\n"
    )
    from laplace.engine import self_corpus, session_memory
    memory_root = repo_root or source_tree()
    memory = session_memory.brief(memory_root)
    head += "\nCurrent law generation: " + memory["generation"] + " (" + memory["status"] + ").\n"
    head += "\n".join("- " + law for law in self_corpus.law_digest(memory_root))
    head += "\nResolve full clauses and preferences through scripts/laplace-python scripts/wake.py --memory."

    block = _contribution_rank_block(rank)
    return f"{head}\n\n{block}" if block else head


def _node_object(nid: str, net: dict, plan: dict | None) -> str:
    """A node-local reconstruction frame: the node at depth + 1-hop handles."""
    nodes = net["nodes"]
    nd = nodes.get(nid)
    if nd is None:
        return f"### {nid}\nMISSING FROM NETWORK\n"
    lines = [f"### {nid}  ({nd.get('kind')})", nd.get("essence") or "(empty essence)"]
    prov = schema.proj_of(nd).get("provenance") or {}
    if prov:
        lines.append(f"provenance: {json.dumps(prov, indent=1)}")
    # This reconstruction frame is derivation-bearing. General graph links
    # remain inspectable elsewhere; only canonical prerequisites belong under
    # the deliberately strong "Derives from" label.
    from laplace.research import corpus_ingest as ci
    below = ci.inferential_dependencies(net, nid)[:8]
    if below:
        lines += ["", "Derives from (1-hop handles; reconstruct on demand):"]
        for t in below:
            tess = (nodes.get(t) or {}).get("essence") or ""
            lines.append(f"- {t}: {tess[:160]}")
    if plan:
        owner = next((s["id"] for s in schema.plan_sections(plan)
                      if nid in schema.section_nodes(s) or nid in (s.get("figures") or [])),
                     None)
        if owner:
            lines += ["", f"Owning section in the projection plan: {owner}"]
    return "\n".join(lines)


def _policy_core(gates: tuple[str, ...] = schema.DEFAULT_GATE_REFS) -> str:
    lines = [f"CONTRACT: {schema.BUILDER_CONTRACT_LINE}", "",
             "Standards (resolve the handle; rules are never copied here):"]
    lines += [f"- {h}" for h in schema.POLICY_HANDLES]
    lines += ["", f"Gates that run on your output: {', '.join(gates)}."]
    return "\n".join(lines)


def _dials_mod():
    """The dials module, imported at call time (the leaf import stays local, as in
    :func:`_resolve_dials`, so importing this module never pulls yaml in)."""
    from laplace.pipeline import dials as _dials
    return _dials


def _resolve_dials(dials_profile: str | None) -> dict[str, Any] | None:
    """Resolve a per-run dials PROFILE NAME into the loaded dials dict — the lawful
    per-run override the dials-path threading gap lacked (BLOCKER-A / C01,
    ARMING_2026-07-17: 'no env var, no parameter at any hop of the compile chain',
    so a run needing dials-v2 meant hand-edit-v1-then-restore). ``None`` stays
    ``None`` (the leaf's ``load_dials()`` default — byte-identical to pre-thread).
    The name goes through ``pipeline.dials.profile_path`` — the SAME allowlist /
    traversal fence the /dials door uses (a ``DialsProfileError`` propagates: an
    unlawful profile refuses, never silently falls back to v1)."""
    if not dials_profile:
        return None
    from laplace.pipeline import dials as _dials
    return _dials.load_dials(_dials.profile_path(dials_profile))


def _inject_form_channel(parts: list[str], store: str, query_text: str,
                         target: str, proj: registry.Project | None,
                         repo_root: Path | None,
                         dials: dict[str, Any] | None = None) -> None:
    """the retrieval wire (DESIGN_2026-07-15_the-stage-stores §4), ONE injection.

    Build the gate-passed ``store``'s FORM-EXEMPLARS envelope on this stage's OBJECT
    and append it to ``parts`` IFF non-``None``. ``None`` is the inert default (dial
    off / store ungated): parts stay byte-identical to pre-wire and NO sidecar is
    written, so the wiring lands behaviour-inert until a dial is deliberately
    flipped. When an envelope IS served, bank a durable audit sidecar
    ``{store, k, exemplar row_ids+cos, query_digest, ts}`` beside this stage's
    dispatch records (``proj.stage_path("dispatches")`` — where compiled dispatches
    bank) so a flipped store is watchable mechanically. The sidecar write is best-
    effort (an audit trail, never fatal), exactly as the weld's voice sidecar. A
    dial-enabled-but-gate-refused store raises ``SystemExit`` (from the builder) —
    the dial cannot override the gate. Mirrors the weld's RETRIEVED-EXEMPLARS append
    + ``voice_retrieval`` sidecar idiom.

    The BANK — never the envelope — is additionally gated on
    :func:`derived_writes.enabled`. The record carries a wall-clock ``ts``, so an
    ungated refresh rewrites the sidecar on EVERY compile against a live project;
    a test that merely ASSERTS real repo state (test_essence_hygiene compiles a
    live narrative dispatch) therefore MUTATED it, and every tree-state probe
    after it read a dirtier tree than the change under test
    (WO-20260817-test-mutates-working-tree). Read-only under pytest, unchanged in
    a real run, opt-in via ``LAPLACE_SIDECAR_WRITE``. The envelope is served
    either way: the PROMPT is never altered by the gate, only the disk trace."""
    from laplace.pipeline import derived_writes, stage_retrieval
    rr = repo_root or source_tree()
    served = stage_retrieval.build_form_channel_and_record(
        store=store, query_text=query_text, dials=dials, root=rr)
    if served is None:
        return                          # inert: dial off / ungated → nothing at all
    envelope, record = served
    parts.append(envelope)
    if proj is not None and derived_writes.enabled():
        ddir = proj.stage_path("dispatches", rr)
        if ddir is not None:
            try:
                stage_retrieval.write_form_channel_sidecar(
                    ddir / stage_retrieval.sidecar_name(
                        store, pathsafe.encode_sid_for_path(target)),
                    record)
            except OSError:
                pass                    # best-effort audit trail, never fatal


#: The findings-consumer attach (W-CONSUMER, 2026-07-22). The N most-recent open MACHINE
#: findings anchored to a section ride its prose packet as fenced evidence (the weld's
#: DETECTOR-REPORT idiom, one level down). Bounded so a section with a deep backlog does
#: not flood the realiser's context; the remainder is COUNTED in the header, never hidden.
#: The LAND side (edits.retire_consumed_findings) retires the whole prior-round backlog for
#: the section when its regenerated fragment lands — attached or over-cap alike.
FINDINGS_ATTACH_CAP = 12


def section_packet_id(project: str, section: str) -> str:
    """The stable id of the section packet a landing retires against — names the
    (project, section) whose regeneration consumes the findings that rode it."""
    return f"pkt:{project}:{section}"


def _section_findings_channel(project: str, section: str,
                              repo_root: Path | None) -> "tuple[str, dict] | None":
    """The bounded ANCHORED-FINDINGS evidence for a section packet, or ``None`` when the
    project's feedback ledger has none (the additive floor: no findings → no channel → the
    packet is byte-identical to pre-wire). Returns ``(fence, meta)`` with
    ``meta = {packet, attached:[ids], count, capped}``.

    Selects the open MACHINE findings anchored to the section (``manuscript_bridge`` —
    the same machine/author split the desk uses) and fences the N most recent as
    CONTENT-level evidence (a defect at a node, not engine framing — so §13's prose
    isolation holds: no kernel, no policy, no ``canon://``). Best-effort: an enrichment
    failure never breaks a compile."""
    try:
        proj = registry.resolve(project)
        if proj is None or not getattr(proj, "feedback_ledger", None):
            return None
        rr = repo_root or source_tree()
        ledger_path = rr / proj.feedback_ledger
        if not ledger_path.is_file():
            return None
        from laplace.manuscript import manuscript_bridge as _mb
        from laplace.pipeline.ledger import read_jsonl
        findings = _mb.machine_findings_for_section(read_jsonl(ledger_path), section)
        if not findings:
            return None
        shown = findings[:FINDINGS_ATTACH_CAP]
        rest = len(findings) - len(shown)
        rows = [{"id": f.get("id"), "kind": f.get("kind"),
                 "node": f.get("node_id") or f.get("node") or "",
                 "issue": str(f.get("comment") or f.get("issue") or f.get("value")
                              or f.get("text") or "")[:240]}
                for f in shown]
        header = (f"Open machine findings anchored to this section ({len(findings)} open"
                  + (f"; the {len(shown)} most recent shown, {rest} more counted"
                     if rest > 0 else "") + "). Address them as you realise this fragment; "
                  "each retires when the regenerated fragment lands (its subject "
                  "superseded). A finding the packet does not let you settle is a typed "
                  "issue to RETURN, never a guess in prose.")
        fence = schema.fence("ANCHORED-FINDINGS",
                             header + "\n"
                             + json.dumps(rows, ensure_ascii=False, indent=1))
        return fence, {"packet": section_packet_id(project, section),
                       "attached": [r["id"] for r in rows],
                       "count": len(findings), "capped": rest}
    except Exception:                    # evidence enrichment — never fatal to a compile
        return None


#: how many banked rulings ride a builder packet. Bounded like every other channel —
#: the relevant SLICE with refs, never the ledger.
_RULINGS_CAP = 5


def _inject_standing_rulings(parts: list[str], context: str,
                             repo_root: Path | None) -> None:
    """The taste flywheel'S RETURN LEG, at the builder (:mod:`laplace.engine.ruling_recall`).

    A builder packet already carried DERIVED taste — the ``AUTHOR-ARCHITECTURE`` fence,
    measured off what he *did* across the published corpus. It carried nothing of what he
    *ruled*: every fork verdict and growth ruling the adjudicators bank to
    ``proxy_verdicts.jsonl`` was written and never read back into the frame of the next
    piece of work. This is that edge, in code — the LIVE rulings that bear on this
    packet's context, as TYPED ROWS with their refs, ranked by a stated heuristic.

    His rulings OUTRANK the derived profile where they meet: the profile is a measurement
    of habit, a ruling is a decision. The fence says so, and it says so in the packet
    rather than trusting the builder to guess the precedence.

    NEVER silent: when nothing matches, the fence still rides and states the truthful
    absence against the ledger it was read from (a builder must be able to tell "he has
    ruled nothing here" from "nobody looked"). Only a missing/unreadable ledger drops the
    channel entirely — and then there is no claim to be false about."""
    from laplace.engine import ruling_recall
    try:
        result = ruling_recall.recall(
            repo_root or source_tree(), context, cap=_RULINGS_CAP)
    except Exception:
        return  # no ledger reachable → no channel and no claim (the additive floor)
    if not result["provenance"]["scanned"]:
        return
    parts.append(schema.fence(
        "STANDING-RULINGS",
        ruling_recall.render_rows(
            result,
            "What he has ruled (his own banked verdicts on questions like this one, "
            "recalled from proxy_verdicts.jsonl — typed rows, refs-only; descend a ref "
            "for the whole record). These are DECISIONS, not measurements: where one "
            "meets the AUTHOR-ARCHITECTURE profile (which measures what he did), the "
            "ruling wins. Where one bears on your target, follow it; where one is "
            "silent, the specification governs.")))


def _packet_bears_derivation(packet: dict[str, Any]) -> bool:
    """Whether a prose packet carries a DERIVATION (DESIGN §4 scope for the
    derivation_walk wire): a non-empty equation ledger, or any paragraph that
    anchors or details an equation. A non-derivation section takes no derivation_walk
    exemplars — the wire stays scoped to where a derivation lens applies."""
    if packet.get("equation_ledger"):
        return True
    return any(p.get("equation_anchor") or p.get("derivation_detail")
               for p in (packet.get("paragraphs") or []))


# ---------------------------------------------------------------------------
# The composed aim head (packets-carry-the-aim, his ruling 2026-07-22,
# PV-20260722T174417Z / T174601Z: "builders should know where they're aiming ... the
# iteration should converge to the proper object. We shouldn't let builders just guess").
# Every dispatch packet OPENS with a composed head minted by the dispatcher who holds the
# manifest: the goal (version + essence), this packet's role in the whole (its job, where
# it sits in the section order, what depends on it), and what acceptance writes back (the
# stores/records its product lands in). The compose-at-write-time law applied to dispatch
# itself. A PLAIN DICT head, NOT composed.make_composed: that builder is for
# author-attention cards (glance / working / decision / audit) and its barred-vocabulary
# fence refuses the very section anchors, node ids, and source paths this head must carry;
# the aim head is builder-facing dispatch context, so a plain register is the truthful seam.
# ---------------------------------------------------------------------------

def _goal_frame(proj: registry.Project | None,
                repo_root: Path | None) -> dict[str, Any]:
    """The goal this whole projection aims at — version + essence — read at dispatch time
    from the manifest the kernel already holds. ``version`` from the growth sidecar
    (best-effort; ``None`` off the ladder); ``essence`` from the manuscript record's
    primary_contribution / purpose (the paper's own stated aim), falling back to the
    working title. Absent → a stated-empty frame, never a guess."""
    if proj is None:
        return {"version": None, "essence": ""}
    version = None
    try:
        from laplace.pipeline import growth
        rr = repo_root or source_tree()
        version = growth.growth_state(rr, proj.name).get("goal_version")
    except Exception:
        version = None
    essence = ""
    try:
        from laplace.pipeline import projection_spec
        record = (projection_spec.load_spec(proj.name, repo_root) or {}).get("manuscript") or {}
        essence = (record.get("primary_contribution") or record.get("purpose")
                   or record.get("working_title") or "")
    except Exception:
        essence = ""
    return {"version": version, "essence": " ".join(str(essence).split())[:400]}


def _acceptance_writes(proj: registry.Project | None, target: str, worker: str) -> list[str]:
    """What acceptance writes back — the stores/records this packet's product lands in.
    The conjugate half of the aim: a builder should know not only where it aims but where
    its output comes to rest (so it converges to THAT object, not a guess)."""
    if proj is None:
        return []
    try:
        stem = pathsafe.encode_sid_for_path(target)
    except Exception:
        stem = str(target)
    if worker == "prose":
        return [f"the section fragment {stem}.tex (compiled prose)",
                f"its provenance sidecar {stem}.json"]
    if worker == "narrative":
        return [f"the narrative specification narrative/{stem}.json "
                "(the closed packet the prose stage consumes)"]
    if worker == "structure":
        return ["the section contracts artifact (the structural gate must pass on it)"]
    if worker == "render":
        return ["the rendered manuscript (the deterministic tex backend)"]
    if worker in ("figure", "simulate"):
        return [f"the figure artifact for {target} and its provenance record"]
    return [f"a reconstruction fragment for {target} the caller integrates"]


def _aim_head(proj: registry.Project | None, target: str, goal: str, worker: str,
              plan: dict[str, Any], repo_root: Path | None) -> dict[str, Any]:
    """Mint the composed aim head for one dispatch (see the block comment above)."""
    goalf = _goal_frame(proj, repo_root)
    sections = list(schema.plan_sections(plan or {}))
    sids = [s.get("id") for s in sections]

    job = None
    position = None
    owner = target
    if target in sids:
        position = sids.index(target)
        job = sections[position].get("job")
    else:
        owner = next((s.get("id") for s in sections
                      if target in schema.section_nodes(s)
                      or target in (s.get("figures") or [])), None)
        if owner in sids:
            position = sids.index(owner)
            job = sections[position].get("job")

    depended_on_by: list[str] = []
    if proj is not None and owner:
        try:
            contracts = (structural.load_contracts(proj.name, repo_root) or {}).get("sections") or {}
            for sid, c in contracts.items():
                if owner in (c.get("depends_on") or []):
                    depended_on_by.append(sid)
            if not job:
                job = (contracts.get(owner) or {}).get("function")
        except Exception:
            pass

    role = {
        "section": owner,
        "job": " ".join(str(job).split())[:280] if job else None,
        "position": (f"section {position + 1} of {len(sids)}"
                     if position is not None and sids else None),
        "depended_on_by": sorted(set(x for x in depended_on_by if x)),
    }
    writes = _acceptance_writes(proj, target, worker)

    ess = goalf["essence"] or "the manuscript's stated contribution"
    where = role["position"] or "this packet's target"
    dep = role["depended_on_by"]
    dep_phrase = (f"; {len(dep)} later section(s) depend on it ({', '.join(dep)})"
                  if dep else "")
    aim = (f"This {worker} packet advances {ess}. It is {where}{dep_phrase}. "
           "Converge to the proper object the plan names — where a fact is missing, "
           "return a typed issue against the owning stage; do not guess.")
    return {"aim": aim,
            "goal": {"version": goalf["version"], "essence": goalf["essence"]},
            "goal_essence": goalf["essence"],
            "role_in_whole": role,
            "acceptance": {"writes": writes}}


def _aim_head_fence(head: dict[str, Any]) -> str:
    """Render the composed aim head as the packet's opening AIM block — the aim in plain
    words, then the goal / role / acceptance it was composed from. Content-level (§13): no
    kernel, no policy handles, no ``canon://`` — the aim is the paper's aim and this
    packet's place in it, never engine framing, so it rides even the context-isolated
    prose packet."""
    return schema.fence("AIM", head["aim"] + "\n" + json.dumps(
        {"goal": head["goal"], "role_in_whole": head["role_in_whole"],
         "acceptance": head["acceptance"]}, ensure_ascii=False, indent=1))


#: how many banked rows the advisory reconstruction fence names on a dispatch record.
_FENCE_CAP = 3


def _fence_advisory(target: str, goal: str, worker: str, repo_root: Path | None,
                    stamp: str | None) -> dict[str, Any]:
    """The advisory reconstruction fence at the dispatch moment
    (:mod:`laplace.engine.reconstruction_fence`, ``WO-20260812-reconstruction-fence``).

    Before a builder is sent to author something, the compiled record is asked whether
    the banked record already holds it: the work-order ledger, the handoff, the open
    stack. Hits ride the record as ``fence``, so the orchestrator reading a compile sees
    "this may already exist: <row id>" beside the prompt it is about to send.

    Advisory at this tier, in three specific senses. It cannot fail a compile: every
    error is caught below and returned as a field. It cannot change what the builder
    reads: the prompt's bytes are untouched, so a compile with the fence wired is
    byte-identical to one without. It cannot fill the ledger on its own: a row is banked
    only when the caller passes ``fence_stamp``, which a test run or a dry compile does
    not. Promotion to a blocking gate waits on the measured bar in
    :func:`reconstruction_fence.false_negative_report`.
    """
    try:
        from laplace.engine import reconstruction_fence
        return reconstruction_fence.advise(
            repo_root or source_tree(),
            f"{goal} {target}", site=f"compile_dispatch:{worker}:{target}",
            stamp=stamp, cap=_FENCE_CAP)
    except Exception as e:  # noqa: BLE001 - an advisory channel never breaks a compile
        return {"kind": "fence-probe", "hits": [],
                "error": f"{type(e).__name__}: {e}",
                "banked": "no row: the fence did not run"}


def compile_dispatch(target: str, goal: str, worker: str = "prose",
                     project: str | None = None,
                     repo_root: Path | None = None,
                     dials_profile: str | None = None,
                     fence_stamp: str | None = None, *,
                     reconstruction: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compile one work item into a dispatch: an agent prompt (kernel + OBJECT +
    POLICY) or, for provenance-backed figure/simulate items, the script call.

    ``target`` is a section id for prose, a node id otherwise. Returns
    ``{worker, target, goal, prompt | script, skills, model, effort, composed_head,
    fence}``.

    Every non-error dispatch carries ``model``/``effort`` from ``schema.WORKER_MODEL``
    clamped to ``schema.MAX_MODEL`` - the dispatch-model law (his, 2026-07-11: agents
    are opus-level or less; the orchestrator is the ceiling), carried by the compiler
    so callers inherit it instead of hand-writing a literal. When ``dials_profile``
    names a profile carrying ``dispatch.model_pin``, that FLOOR is applied first and
    the clamp second (pin-then-clamp), and ``dispatch.model_id`` rides the record as
    ``model_id`` — the verbatim provider string the tier vocabulary cannot express.

    Every non-error dispatch also carries a ``composed_head`` (packets-carry-the-aim,
    his ruling 2026-07-22): minted HERE, where the manifest is in scope, and prepended to
    the prompt so the builder reads WHERE it is aiming before the work. The head rides
    every packet — the aim is not optional — so a prompt-bearing dispatch opens with the
    AIM block above its kernel / preamble.

    It also carries ``methods``: the methods fibre projected onto the worker's task
    class (:func:`method_rows_for`) — the class's rows plus the ``all`` rows, as
    law + forbids with refs-only evidence, rendered into the prompt as a TRAILING
    METHODS block. It trails because the packet spine is invariant: the AIM fence is
    followed immediately by the stage's own opening (kernel or prose preamble), so the
    fibre sits below the work it governs rather than between them. Strictly additive: a
    class with no rows leaves the field off and the prompt byte-identical. The
    context-isolated prose worker (§13) carries its manuscript-class rows only, and
    every worker outside ``_VOICE_BEARING_WORKERS`` has the voice-naming rows severed
    from its projection, exactly as it is severed from the voice profile.

    Before any compiler, telemetry, fence, registry, or worker-adjacent action,
    ``reconstruction`` must carry a COMPLETE read-only ``atlas-object`` whose exact
    bytes/receipt and current authority coordinate pass the just-in-time verifier.
    Every outcome carries a recomputable ``laplace.dispatch-reconstruction/1`` phase
    receipt. This hard gate covers this first-party Python path only; the D2
    JavaScript/MJS and RAPTOR subprocess paths remain explicitly OPEN.

    It also carries ``fence``: the advisory reconstruction probe's answer to "does the
    record already hold this?" (:func:`_fence_advisory`). It is a report, not a gate —
    the prompt is unchanged by it, and it banks a ledger row only when ``fence_stamp``
    is given.
    """
    from laplace.representation import custody_mode as _custody_mode
    _custody_off = _custody_mode.is_off(repo_root or source_tree())
    if _custody_off:
        static_admission = _admit_typed_descent_custody_off(
            target=target, goal=goal, worker=worker, reconstruction=reconstruction)
        if (reconstruction and reconstruction.get("kind") == "stage"
                and static_admission["admission_result"]["status"] == "ADMITTED"):
            current = reconstruct_stage(target, goal, repo_root=repo_root or source_tree())
            if current.get("content_handle") != reconstruction.get("content_handle"):
                static_admission["admission_result"] = {
                    "status": "REFUSED", "reason": "STAGE_SOURCE_DRIFT"}
                static_admission["receipt_handle"] = _sha256(_canonical_json(
                    {k: v for k, v in static_admission.items() if k != "receipt_handle"}))
    else:
        static_admission = _admit_dispatch_reconstruction(
            target=target,
            goal=goal,
            worker=worker,
            repo_root=repo_root,
            reconstruction=reconstruction,
            perform_jit=False,
        )
    if static_admission["admission_result"]["status"] != "ADMITTED":
        return {
            "error": (
                "dispatch reconstruction admission refused: "
                f"{static_admission['admission_result']['reason']}"
            ),
            "reconstruction_admission": static_admission,
        }

    # Root seats and dispatched workers now share the same reconstruction law.  D1's exact
    # object/authority proof below remains the final JIT provider-invocation boundary; this prior
    # turn descent binds the current function profile and shared S->F semantic horizon. Missing
    # profile/fold context is carried as UNKNOWN/FOG in the prompt rather than silently replaced
    # with a platform summary or fuzzy/file routing.
    from laplace.engine.turn_reconstruction import reconstruct_turn

    turn_reconstruction = reconstruct_turn(
        repo_root or source_tree(),
        event_name="ProviderDispatch",
        prompt=f"{goal}\n{target}",
        function=os.environ.get("LAPLACE_FUNCTION", ""),
        seat_id=os.environ.get("LAPLACE_SEAT_ID", ""),
        thread_id=os.environ.get("CODEX_THREAD_ID", ""),
        record_observation=True,
    )
    continuation = turn_reconstruction.get("continuation_decision") or {}
    selected_context = any(
        isinstance(row, Mapping) and row.get("content_status") == "COMPLETE"
        for row in turn_reconstruction.get("selected") or ()
    )
    if not _custody_off and (
        turn_reconstruction.get("status") != "ADMITTED"
        or turn_reconstruction.get("claims_with_unknown_context") is not False
        or not str(turn_reconstruction.get("profile_handle") or "").startswith("sha256:")
        or not str(
            turn_reconstruction.get("semantic_fold_health_handle") or ""
        ).startswith("sha256:")
        or continuation.get("status") != "ADMITTED"
        or not str(continuation.get("decision_handle") or "").startswith("sha256:")
        or not selected_context
    ):
        return {
            "error": "dispatch turn reconstruction refused: exact current target context absent",
            "reconstruction_admission": static_admission,
            "turn_reconstruction": turn_reconstruction,
        }

    # This is deliberately after turn descent: it is the final authority read before core, so
    # profile/content acquisition cannot reopen the D1 root race.
    admission = static_admission if _custody_off else _admit_dispatch_reconstruction(
        target=target,
        goal=goal,
        worker=worker,
        repo_root=repo_root,
        reconstruction=reconstruction,
    )
    if admission["admission_result"]["status"] != "ADMITTED":
        return {
            "error": (
                "dispatch reconstruction admission refused: "
                f"{admission['admission_result']['reason']}"
            ),
            "reconstruction_admission": admission,
            "turn_reconstruction": turn_reconstruction,
        }

    # No external read belongs between the JIT authority comparison above and
    # entry into the compiler core.
    core_target, core_project = target, project
    if "stage" in admission and worker == "prose":
        stage = json.loads(reconstruction["content"])
        core_target = stage.get("section_id") or stage.get("section")
        core_project = project or stage.get("project")
        if not isinstance(core_target, str) or not core_target or not core_project:
            return {"error": "STAGE_PROSE_BINDING_MISSING: section_id and project required",
                    "reconstruction_admission": admission}
        if project and stage.get("project") and project != stage["project"]:
            return {"error": "STAGE_PROJECT_MISMATCH", "reconstruction_admission": admission}
    out = _compile_dispatch_core(core_target, goal, worker, core_project, repo_root,
                                 dials_profile=dials_profile)
    out["reconstruction_admission"] = admission
    out["turn_reconstruction"] = turn_reconstruction
    if "error" not in out:
        model, effort = schema.WORKER_MODEL.get(out.get("worker", worker),
                                                (schema.MAX_MODEL, "medium"))
        # The arm pin (B17). Without a profile the pin is None and this line is
        # the identity: the stamp stays exactly schema.WORKER_MODEL clamped. With
        # one, the profile's floor overrides the per-worker constant — the
        # config-over-constant move, and the reason a pinned arm's python leg
        # cannot quietly stamp the sonnet default while the .js leg runs opus.
        # Pin then clamp: the ceiling law is applied last and always wins.
        _dials = _resolve_dials(dials_profile)
        pin = _dials_mod().model_pin(_dials)
        out.setdefault("model", schema.clamp_model(schema.pin_model(model, pin)))
        out.setdefault("effort", effort)
        # the exact provider id, verbatim: the tier is what the audit enforces,
        # the id is what the run ledger proves (MODEL_RANK has no version grade).
        mid = _dials_mod().model_id(_dials)
        if mid:
            out.setdefault("model_id", mid)
        proj = registry.resolve(core_project) if core_project else None
        plan = (proj.read_plan(repo_root) or {}) if proj is not None else {}
        w = out.get("worker", worker)
        head = _aim_head(proj, core_target, goal, w, plan, repo_root)
        out["composed_head"] = head
        # the methods fibre, by the same motion and in the same place: the class's
        # standing law attached where the manifest is in scope, strictly additive,
        # byte-identical when the class has no rows. The prose worker is
        # context-isolated (§13) — it carries its manuscript-class craft law and NOT
        # the engine-framed `all` rows, which would be the scaffolding-leak class.
        methods = method_rows_for(WORKER_TASK_CLASS.get(w, "all"), repo_root,
                                  include_all=(w != "prose"))
        if w not in _VOICE_BEARING_WORKERS:
            methods = [r for r in methods if not _row_names_voice(r)]
        if methods:
            out["methods"] = methods
        if "prompt" in out:
            # THE PACKET SPINE IS INVARIANT: AIM fence, then the stage's own opening —
            # the graded-node kernel for engine workers, the clean stage preamble for
            # the context-isolated prose realiser (§13). Nothing may come between the
            # AIM fence and that opening line, so the fibre rides as a TRAILING block:
            # the standing law of the class, stated once, below the work it governs.
            out["prompt"] = _aim_head_fence(head) + "\n\n" + out["prompt"]
            if methods:
                out["prompt"] += "\n\n" + _methods_fence(methods)
            out["prompt"] += "\n\nTURN RECONSTRUCTION\n" + json.dumps(
                turn_reconstruction,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if "stage" in admission:
                out["stage"] = admission["stage"]
                out["prompt"] += "\n\n" + schema.fence(
                    "STAGE", json.dumps(admission["stage"], ensure_ascii=False, indent=1))
        # last, and after the prompt is final: the fence reads the record, never the
        # packet, so its position here cannot affect a single byte of what is sent.
        out["fence"] = _fence_advisory(target, goal, out.get("worker", worker),
                                       repo_root, fence_stamp)
    return out


def _compile_dispatch_core(target: str, goal: str, worker: str = "prose",
                           project: str | None = None,
                           repo_root: Path | None = None,
                           dials_profile: str | None = None) -> dict[str, Any]:
    if worker not in schema.WORK_KINDS:
        return {"error": f"unknown worker {worker!r}; one of {schema.WORK_KINDS}"}
    proj = registry.resolve(project) if project else None
    if project and proj is None:
        return {"error": f"unknown project {project!r}"}
    # the per-run dials override, resolved ONCE (allowlist-fenced); None = the
    # leaf's load_dials() default, byte-identical to pre-thread (BLOCKER-A / C01)
    dials_resolved = _resolve_dials(dials_profile)

    # resolve the plan ONCE near the top for the one authored judgement that binds
    # every section: plan.meta.contribution_rank threads into the kernel header so
    # every kernel-bearing builder packet carries it. Absent → rank is None and the
    # header is byte-identical to today (strictly additive). The prose worker is
    # context-isolated by §13 (no kernel) and legitimately never receives it.
    rank = None
    if proj is not None:
        _plan = proj.read_plan(repo_root) or {}
        rank = (_plan.get("meta") or {}).get("contribution_rank")

    head = kernel(proj, target, goal, worker, rank=rank, repo_root=repo_root)

    if worker == "prose":
        if proj is None:
            return {"error": "prose dispatch needs a project"}
        packet = narrative.narrative_packet(project, target, repo_root)
        if packet is None:
            return {"error": f"no narrative specification for section {target!r} - "
                             f"plan the narrative first (the packet IS the prose "
                             f"worker's frame; briefs are retired)"}
        rr = repo_root or source_tree()
        record = (packet.get("contract") or {})
        try:
            voice_context, voice_text = _voice_dispatch_context(project, rr, record)
        except (ValueError, OSError) as error:
            return {'error': 'voice profile unavailable: ' + str(error)}
        tex_dir = proj.resolved_target_dir(repo_root)
        prov_dir = proj.stage_path("provenance", repo_root)
        target_stem = pathsafe.encode_sid_for_path(target)
        output_contract = (
            f"OUTPUT CONTRACT\n"
            f"1. Write the fragment to \"{tex_dir}/{target_stem}.tex\". Open it with the\n"
            f"   marker comments '% PLAN:{target}' and '% NODES: <every input node id,\n"
            f"   space-separated, byte-for-byte>'. Realise every paragraph plan, but\n"
            f"   choose the expository order and paragraph boundaries. A rendered\n"
            f"   paragraph begins with all plan markers it realises on consecutive\n"
            f"   lines; repeat a marker when one plan needs more than one paragraph.\n"
            f"2. Cite only keys present in the packet's citations. Anchor equations by\n"
            f"   their ledger labels (\\begin{{equation}}\\label{{...}}). Reference\n"
            f"   figures only via \\ref{{fig:...}} - figure environments are generated\n"
            f"   by the backend, never written in prose.\n"
            f"3. Then write the provenance sidecar to \"{prov_dir}/{target_stem}.json\"\n"
            f"   (the filename is the id with ':' -> '_'; the JSON's section_id stays\n"
            f"   the TRUE id):\n"
            f"   {{\"section_id\": \"{target}\", \"paragraphs\": [one record per rendered\n"
            f"   paragraph: {{\"spec_id\": <first paragraph plan id>, \"spec_ids\":\n"
            f"   [<every plan id realised here>], \"nodes_realised\": [...],\n"
            f"   \"equations\": [...], \"qualifications\": [...], \"citations\": [...]}}]}}.\n"
            f"4. A substantive question the packet does not settle is a typed issue to\n"
            f"   RETURN (name the owning stage); never solve it in prose."
        )
        parts = [
            schema.PROSE_STAGE_PREAMBLE,
            schema.fence("VOICE-PROFILE", voice_text),
            schema.fence("PACKET", json.dumps(packet, ensure_ascii=False, indent=1)),
        ]
        # The retrieval wire (DESIGN §4): derivation_walk at the prose realiser, and
        # ONLY for DERIVATION-BEARING sections (the design's scope). Query on the
        # PACKET — this stage's content-bearing OBJECT. Dial-gated (ships OFF), so a
        # non-derivation section AND the all-off default both stay byte-identical to
        # pre-wire. Appended before the OUTPUT CONTRACT so the contract stays last.
        if _packet_bears_derivation(packet):
            _inject_form_channel(
                parts, "derivation_walk",
                json.dumps(packet, ensure_ascii=False), target, proj, repo_root,
                dials=dials_resolved)
        # The findings-consumer attach (W-CONSUMER): the open machine findings anchored to
        # this section ride the packet as bounded, fenced evidence. Additive — no findings
        # → no channel → byte-identical to pre-wire. Appended before the OUTPUT CONTRACT so
        # the contract stays last; content-level, so §13's prose isolation holds.
        findings_meta = None
        _fch = _section_findings_channel(project, target, repo_root)
        if _fch is not None:
            _fence, findings_meta = _fch
            parts.append(_fence)
        parts.append(output_contract)
        prompt = "\n\n".join(parts)
        from laplace.engine import telemetry
        telemetry.log("execute", skill="orchestrated_generation", ok=True, target=target)
        out = {"worker": worker, "target": target, "goal": goal, "prompt": prompt,
               "packet_sections": len(packet.get("paragraphs") or []),
               "skills": ["orchestrated_generation"],
               "writing_style": {key: voice_context[key] for key in ('revision', 'selected_profile', 'profile_revision', 'guidance_sha256', 'genre', 'selection_origin')}}
        if findings_meta is not None:
            out["findings"] = findings_meta
        return out

    if worker == "structure":
        if proj is None:
            return {"error": "structure dispatch needs a project"}
        seed = structural.seed_contracts(project, repo_root)
        state = structural.compute_reader_state(project, repo_root, write=False)
        from laplace.pipeline import projection_spec
        record = (projection_spec.load_spec(project, repo_root) or {}).get("manuscript") or {}
        obj = "\n\n".join([
            "## Manuscript record (the paper's contract)",
            json.dumps(record, ensure_ascii=False, indent=1),
            "## Contract skeletons (fill the authored fields)",
            json.dumps(seed, ensure_ascii=False, indent=1),
            "## Derived reader-state graph (introduction + uses per node)",
            json.dumps(state, ensure_ascii=False, indent=1),
        ])
        policy = (
            f"CONTRACT: {schema.BUILDER_CONTRACT_LINE}\n\n"
            "Fill every section contract's authored fields: function (singular and "
            "specific), question_answered, entry_state and exit_state (what the "
            "reader knows - concrete, checkable sentences), permitted_recap, "
            "forward_uses, and the section's equations list (ledger labels). Write "
            f"the completed JSON to the contracts artifact. The structural gate "
            "(laplace.pipeline.structural.gate) must pass on your output."
        )
        parts = [head, schema.fence(schema.BRIEF_CHANNEL_POLICY, policy),
                 schema.fence(schema.BRIEF_CHANNEL_OBJECT, obj)]
        # The retrieval wire (DESIGN §4): section_architecture at the structure /
        # section-planning worker — its natural stage (the OBJECT is the manuscript
        # record + contract skeletons + reader-state, the most content-bearing string
        # this stage carries). Dial-gated (ships OFF) → byte-identical to pre-wire.
        _inject_form_channel(parts, "section_architecture", obj, target, proj,
                             repo_root, dials=dials_resolved)
        # The author-architecture profile (architecture-profile-consumed, W-arch): the
        # structure planner lays the WHOLE spine, so it carries the whole-paper FORM prior
        # from profiles/author_architecture.yaml — how he opens, ladders, orders sections,
        # places figures, and closes — refs-only + summaries. Additive: no file → no fence.
        _arch_state = narrative.architecture_status(repo_root, include_content=True)
        _arch = _arch_state.get('fields')
        if _arch:
            parts.append(schema.fence(
                "AUTHOR-ARCHITECTURE",
                "How he writes (whole-paper structural FORM the spine should follow, "
                "refs-only — a form prior over the section order and weight, never a "
                "content source):\n"
                + json.dumps(
                    {f: {"summary": v["summary"], "confirmed_his": v["confirmed_his"],
                         "historical_confirmation_assertion": v.get('historical_confirmation_assertion', False),
                         **({'author_confirmation': v['author_confirmation']} if v.get('author_confirmation') else {}),
                         "ref": v["ref"]} for f, v in _arch.items()},
                    ensure_ascii=False, indent=1)))
        # The return leg: what he has RULED, beside what he is measured to DO. The
        # structure planner lays the whole spine, so it is the packet his standing
        # structural calls bear on hardest.
        # context = what NAMES this work (target, goal, the paper's own stated aim), not
        # the whole manuscript record — lexical overlap ranks by subject only while the
        # context stays about the size of a question.
        _inject_standing_rulings(
            parts, f"{target} {goal}\n"
                   f"{record.get('primary_contribution') or record.get('purpose') or ''}\n"
                   f"{record.get('working_title') or ''}", repo_root)
        prompt = "\n\n".join(parts)
        return {"worker": worker, "target": target, "goal": goal, "prompt": prompt,
                "profile_inputs": {"architecture": {key: value for key, value in _arch_state.items()
                                                    if key != "fields"}},
                "skills": _log_ridden(target, ("manuscript_spine",))}

    if worker == "narrative":
        if proj is None:
            return {"error": "narrative dispatch needs a project"}
        contracts = (structural.load_contracts(project, repo_root) or {}).get("sections") or {}
        contract = contracts.get(target)
        if not contract:
            return {"error": f"no section contract for {target!r} - resolve structure first"}
        plan = proj.read_plan(repo_root) or {}
        sec = next((s for s in schema.plan_sections(plan) if s.get("id") == target), {})
        net = None
        if proj.kind == "conceptric":
            from laplace.research import corpus_ingest as ci
            rr = repo_root or source_tree()
            net = ci.corpus_network(ci.resolve_corpus(rr, project), repo_root=rr,
                                    name=project)
        nodes_obj = "\n".join(
            _node_object(nid, net, plan) if net is not None else f"### {nid}"
            for nid in schema.section_nodes(sec))
        from laplace.pipeline import projection_spec
        spec = projection_spec.load_spec(project, repo_root) or {}
        figs = {fid: spec.get("figures", {}).get(fid, {})
                for fid in (sec.get("figures") or [])}
        ledger = {k: v for k, v in
                  projection_spec.effective_equation_ledger(project, repo_root).items()
                  if (v.get("section") or "") == target}
        carried = list(dict.fromkeys(
            schema.section_nodes(sec) + list(sec.get("figures") or [])))
        framing_lines = []
        if net is not None:
            for nid in carried:
                f = schema.proj_of(net["nodes"].get(nid) or {}).get("framing")
                if f:
                    framing_lines.append(f"- {nid}: {f}")
        obj = "\n\n".join([
            "## Section contract", json.dumps(contract, ensure_ascii=False, indent=1),
            "## Nodes, in the pinned linear order", nodes_obj,
            "## Figure specifications (settled captions - anchor, never rewrite)",
            json.dumps(figs, ensure_ascii=False, indent=1),
            "## Equation ledger for this section",
            json.dumps(ledger, ensure_ascii=False, indent=1),
        ] + (["## Framing (positioning guidance; shape the plan with it, never "
              "quote it)", "\n".join(framing_lines)] if framing_lines else []))
        policy = (
            f"CONTRACT: {schema.BUILDER_CONTRACT_LINE}\n\n"
            "Write the section's narrative specification: a JSON file "
            f"{{\"section_id\": \"{target}\", \"paragraphs\": [...]}} where each "
            "paragraph record carries: paragraph_id, function (distinct, "
            "communicative), input_nodes, proposition, explanation, "
            "derivation_detail, equation_anchor, figure_anchor, qualification, "
            "from_previous, to_next, detail_level, length_range, citations "
            "(schema.PARAGRAPH_FIELDS). Every planned node is an input to at "
            "least one paragraph; equations enter after their prerequisites; "
            "qualifications sit at the point of possible misunderstanding. This "
            "is a PLAN, not prose - propositions are declarative content "
            "statements, never sentences to copy. The narrative validator "
            "(laplace.pipeline.narrative.validate_narrative) must pass."
        )
        parts = [head, schema.fence(schema.BRIEF_CHANNEL_POLICY, policy),
                 schema.fence(schema.BRIEF_CHANNEL_OBJECT, obj)]
        # The retrieval wire (DESIGN_2026-07-15_the-stage-stores §4): the narrative
        # planner injects FORM exemplars from TWO gate-passed stores — paragraph_plan
        # AND spine_chain — each queried on this section's OBJECT (`obj`, the design's
        # "stage's current OBJECT" and the most content-bearing string this stage
        # carries). Both are dial-gated and ship OFF, so the packet stays byte-
        # identical to pre-wire; a served FORM-EXEMPLAR envelope is appended exactly
        # as compile_weld_dispatch appends its RETRIEVED-EXEMPLARS voice channel, and
        # each served store banks its audit sidecar beside the dispatch records.
        _inject_form_channel(parts, "paragraph_plan", obj, target, proj, repo_root,
                             dials=dials_resolved)
        _inject_form_channel(parts, "spine_chain", obj, target, proj, repo_root,
                             dials=dials_resolved)
        # The author-architecture profile (architecture-profile-consumed, W-arch): the
        # narrative planner's section brief carries the profiles/author_architecture.yaml
        # FORM fields that bear on WHERE this section sits — intro shape for the opener,
        # section rhythm + derivation placement for the body, conclusion posture for the
        # close, and the citation-licensed compression law wherever a derivation rides (a
        # section carrying equations). His two confirmed-his corrections ride every
        # derivation-bearing section. Refs-only + summaries, composed WITH the conceptric
        # content, never overriding it. Additive: no profile file → no fence → the packet
        # is byte-identical to pre-wire.
        sec_order = [s.get("id") for s in schema.plan_sections(plan)]
        _pos = sec_order.index(target) if target in sec_order else None
        _arch_state = narrative.architecture_status(repo_root, include_content=True)
        _abrief = narrative.architecture_brief_for_section(
            _arch_state.get('fields'),
            _pos, len(sec_order), sec.get("job"), bool(ledger))
        if _abrief is not None:
            parts.append(schema.fence(
                "AUTHOR-ARCHITECTURE",
                "How he writes (whole-paper structural FORM, refs-only — shape the plan "
                "with it, compose with the conceptric content, never let it override the "
                "content source):\n"
                + json.dumps(_abrief, ensure_ascii=False, indent=1)))
        # The return leg: his banked rulings on this section's subject, beside the
        # derived FORM prior — the planner is where a standing call on shape, placement
        # or compression actually binds.
        _inject_standing_rulings(
            parts, f"{target} {goal} {sec.get('job') or ''}\n"
                   f"{contract.get('function') or ''}", repo_root)
        prompt = "\n\n".join(parts)
        return {"worker": worker, "target": target, "goal": goal, "prompt": prompt,
                "profile_inputs": {"architecture": {key: value for key, value in _arch_state.items()
                                                    if key != "fields"}},
                "skills": _log_ridden(target, ("manuscript_spine",))}

    if worker == "render":
        return {"worker": worker, "target": target, "goal": goal,
                "script": f"scripts/render_manuscript.py {project or ''}".strip(),
                "skills": _log_ridden(target, ("latex_forge",))}

    # node-scoped workers reconstruct from the network
    net = None
    plan = proj.read_plan(repo_root) if proj else None
    if proj is not None and proj.kind == "conceptric":
        from laplace.research import corpus_ingest as ci
        rr = repo_root or source_tree()
        net = ci.corpus_network(ci.resolve_corpus(rr, proj.name),
                                repo_root=rr, name=proj.name)

    if worker in ("figure", "simulate") and net is not None:
        nd = net["nodes"].get(target) or {}
        prov = schema.proj_of(nd).get("provenance") or {}
        generator = prov.get("generator")
        if generator:
            # mechanical stays mechanical: the provenance block names the
            # generator; the dispatch is the script call, not an agent
            return {"worker": worker, "target": target, "goal": goal,
                    "script": generator, "provenance": prov,
                    "skills": _log_ridden(target, ("figure_standard",))}

    obj = (_node_object(target, net, plan) if net is not None
           else f"### {target}\n(no conceptric network for this project)")
    prompt = "\n\n".join([
        head,
        schema.fence(schema.BRIEF_CHANNEL_POLICY, _policy_core()),
        schema.fence(schema.BRIEF_CHANNEL_OBJECT, obj),
    ])
    return {"worker": worker, "target": target, "goal": goal, "prompt": prompt,
            "skills": _log_ridden(target)}


#: Above this assembled size (characters of fragment text), the weld rolls
#: section-by-section with a coherence read-back instead of one global pass —
#: adaptive staging (his, this session). Single pass is preferred (only a global
#: pass can dissolve per-section narrator announcements); rolling is the fallback
#: that keeps a very large object inside a workable context. ~4 chars/token, so
#: this is ~80k tokens of fragments before the profile/detector channels.
WELD_GLOBAL_CHAR_LIMIT = 320_000


def compile_weld_dispatch(project: str, repo_root: Path | None = None,
                          voice_on: bool = False, *, exemplar_k: int = 3,
                          cache_root: Path | str | None = None,
                          backend: Any | None = None) -> dict[str, Any]:
    """The WELD as a compiled dispatch (his re-scope, 2026-07-09). NEUTRAL-FIRST,
    VOICE-LAST (his ruling, 2026-07-09): with ``voice_on=False`` (default) the weld
    does the STRUCTURAL work only - de-seam the fragments, keep the narrator
    classes absent, fix the provenance markers, in a clear NEUTRAL register - which
    is part of neutral completion; with ``voice_on=True`` it is the final, optional
    VOICE layer that rewrites the whole in the author's own voice and must EARN its
    place against the neutral surface.

    The voice layer is RETRIEVAL-GROUNDED, not profile-fenced (Phase I2). For each
    ``% <sid>-pN`` paragraph of the neutral draft it fences the nearest passages of
    the author's REAL prose (a per-paragraph ``RETRIEVED-EXEMPLARS`` channel, built
    by :mod:`laplace.pipeline.voice_retrieval` over the sealed bge-small store), so
    the welder writes FROM his prose. The lexical profile is DEMOTED to thin
    register orientation - by ``voice_descent``'s law a description of a generator
    does not generate. FAIL LOUD: if the exemplar store is unavailable the wash
    ships neutral (``neutral_fallback``) or errors - it NEVER degrades to a
    spec-driven "sound like him" pass (the named-failure embryo). ``exemplar_k`` is
    the per-paragraph retrieval count; ``cache_root``/``backend`` are injection
    seams for tests (production reads the sealed ``corpus_stores/`` store).

    Either way it is writing, not smoothing; the fragments are CONTENT; the
    substance-freeze holds; the detector report enumerates the narrator classes
    that must not exist. Compiled fresh so a cold instance enters through the one
    compiler like every other stage."""
    proj = registry.resolve(project)
    if proj is None:
        return {"error": f"unknown project {project!r}"}
    rr = repo_root or source_tree()
    tex_dir = proj.resolved_target_dir(repo_root)
    plan = proj.read_plan(repo_root) or {}
    order = [s["id"] for s in schema.plan_sections(plan)]
    fragments = {}
    for sid in order:
        p = tex_dir / f"{pathsafe.encode_sid_for_path(sid)}.tex"
        if p.is_file():
            fragments[sid] = p.read_text(encoding="utf-8")
    voice_context, voice_text = None, None
    if voice_on:
        try:
            voice_context, voice_text = _voice_dispatch_context(project, rr)
        except (ValueError, OSError) as error:
            return {'error': 'voice profile unavailable: ' + str(error)}

    from laplace.pipeline import verify as _verify
    detector = {}
    for sid, text in fragments.items():
        v = _verify.check_voice(text)
        if v["violations"]:
            detector[sid] = [{"line": f["line"], "kind": f["kind"]}
                             for f in v["violations"]]

    decisions_dir = proj.stage_path("decisions", repo_root)
    assembled_chars = sum(len(t) for t in fragments.values())
    staging = "rolling" if assembled_chars > WELD_GLOBAL_CHAR_LIMIT else "global"

    # the per-section paragraph ids (from prose-provenance) — the weld emits one
    # % <sid>-pN marker per unit, so provenance is uniform even where a realiser
    # pass omitted them; a merge joins ids, a split repeats one.
    from laplace.pipeline import document_model as _dm
    paragraph_ids = {}
    for sid in order:
        ids = [pid for record in (_dm.load_provenance(project, sid, repo_root) or [])
               for pid in (record.get("spec_ids") or [record.get("spec_id")]) if pid]
        if ids:
            paragraph_ids[sid] = list(dict.fromkeys(ids))

    # RETRIEVAL-GROUNDED voice (Phase I2): the generative substrate is the author's
    # REAL prose, retrieved per paragraph - NOT the lexical profile. Build it before
    # the prompt so a missing store FAILS LOUD here (ship neutral / error), never a
    # silent spec-driven degrade (canon://skills/voice_descent).
    exemplar_channel = None
    retrieval_summary = None
    voice_sidecar = None
    if voice_on:
        from laplace.pipeline import voice_retrieval as _vr
        try:
            exemplar_channel, retrieval_summary = _vr.build_channel(
                {sid: fragments[sid] for sid in order if sid in fragments},
                order, k=exemplar_k, cache_root=cache_root, backend=backend)
        except SystemExit as exc:
            # the sealed store / backend is unavailable: the generative substrate
            # (his real prose) is missing. REFUSE the profile-only pass - ship the
            # neutral surface (valid per PIPELINE_GUIDE §2) or surface the error.
            return {"error": f"voice wash unavailable - {exc} Refusing a "
                             f"spec-driven pass; ship the neutral weld.",
                    "voice_on": True, "neutral_fallback": True,
                    "reason": "voice_store_unavailable", "target": project,
                    "skills": ["welder", "orchestrated_generation"]}
        if not any(u["exemplars"] for u in exemplar_channel):
            return {"error": "voice wash retrieved no authored exemplars for any "
                             "paragraph (no % <sid>-pN markers, or an empty store); "
                             "refusing a spec-driven pass - ship the neutral weld.",
                    "voice_on": True, "neutral_fallback": True,
                    "reason": "no_exemplars_retrieved", "target": project,
                    "retrieval": retrieval_summary,
                    "skills": ["welder", "orchestrated_generation"]}
        # FILE-BACK the retrieved substrate (Leg C bite C1): bank the channel +
        # summary to a sidecar beside the weld's per-section decision sidecars, so
        # the run's exemplar grounding is an auditable object, not a prompt-only
        # artefact thrown away after the dispatch compiles.
        if decisions_dir:
            try:
                voice_sidecar = str(_vr.write_channel_sidecar(
                    Path(decisions_dir) / _vr.SIDECAR_NAME,
                    exemplar_channel, retrieval_summary))
            except OSError:
                voice_sidecar = None            # best-effort audit trail, never fatal

    if voice_on:
        register_instruction = (
            "Rewrite the whole document in the AUTHOR'S OWN VOICE - but voice is not "
            "a description you apply, it is prose you write FROM. The "
            "RETRIEVED-EXEMPLARS channel below gives, per paragraph (keyed by its "
            "% <sid>-pN marker), the nearest passages of the author's REAL prose: "
            "write each paragraph FROM its exemplars - their cadence, their moves, "
            "their register - never from a lexical checklist. The "
            "REGISTER-ORIENTATION profile is thin orientation only (what to listen "
            "for), NOT the generator: a description of a generator does not "
            "generate. The retrieved exemplars are the generative substrate; the "
            "substance freeze still holds absolutely.")
    else:
        register_instruction = (
            "Rewrite the whole document in a clear, NEUTRAL technical register. Develop "
            "one connected explanation for the intended reader. Let the reasoning set "
            "paragraph boundaries, sentence rhythm and emphasis; settled steps may be "
            "plain. Preserve every scientific and evidential obligation and its "
            "provenance while improving the joins across the argument.")
    preamble = (
        "You are the WELDER - the one writer of this manuscript. Its section "
        "fragments follow, in reading order. Their CONTENT is settled and frozen: "
        "every claim, "
        "every displayed equation with its label, every \\cite key, every "
        "\\ref, every % PLAN / % NODES marker line, the section order, and the "
        "paragraph-level factual content. Their LANGUAGE is yours to write, "
        "entirely.\n"
        "FRONT MATTER IS IDENTITY, NOT LANGUAGE - frozen absolutely and OUTSIDE "
        "your write scope: the title, the author block (including a deliberate "
        "\\noaffiliation), the abstract, any document marking (CONFIDENTIAL / "
        "\\notfordistribution / invention-disclosure), the pdf-identity "
        "(\\hypersetup), and the preamble. You write ONLY the section fragments "
        "listed below; you never touch main.tex or regenerate front matter from "
        "any source, including the voice exemplars (a prior weld rewrote the "
        "author's scrubbed affiliation back in from his published-paper style - "
        "voice must never overshoot into identity). An impulse to change front "
        "matter is a typed issue, never an edit.\n"
        + register_instruction + " Explain dependencies where the reader needs them, "
        "lead with the achieved result and its physical meaning, and keep the main "
        "comparison complete in one place. Give completed work more space than pending "
        "work. State scope and uncertainty once, where they change the inference. "
        "Present a negative experiment as a finding with a causal consequence. Give "
        "difficult moves enough room to be understood. "
        "The detector report is review evidence about "
        "the incoming draft, not a list of constructions to avoid sentence by sentence.\n"
        "You may merge or split paragraphs, reorder sentences within a "
        "section, and re-derive connective tissue. You may NOT alter any "
        "frozen item, move content across sections, or introduce a claim, "
        "number, citation or qualification that is not already present. A "
        "substantive doubt goes back as a typed issue, never into prose.\n"
        "Rewrite every fragment in place. The % PLAN and % NODES lines atop each "
        "fragment stay byte-identical. Every paragraph opens with its % <sid>-pN "
        "marker - the ids per section are in PARAGRAPHS below; where a fragment "
        "lacks them, add one per paragraph in that order. You keep your freedom to "
        "MERGE or SPLIT paragraphs (a paragraph is a unit; some content needs more "
        "than one): to MERGE plan units, place their markers adjacently atop the "
        "one paragraph (% <sid>-p3 then % <sid>-p4 on consecutive lines) so the "
        "provenance joins; to SPLIT one, repeat its marker on each part. Every "
        "merge or split is a paragraph-restructure decision you RECORD (below) - "
        "the freedom is yours, backpropagating it is required.\n"
        "Surface your forks, do not bury them. Keep a decision record for each "
        "fork worth the author's eye: an ambiguity the fragments leave open that "
        "you resolve, a substantive doubt, a deliberate voice choice, or a "
        "Cross-link opportunity - two passages that should reference each other. "
        "A cross-link is SURFACED, never silently written: you do not add a "
        "\\ref, you RECORD that one belongs, for the author to rule on (the "
        "substance freeze holds).\n"
        f"OUTPUT: for each section write its decision sidecar to "
        f"\"{decisions_dir}/<sid>.json\" (the FILENAME is the id with ':' -> '_' "
        f"— e.g. sec:abstract -> sec_abstract.json; the JSON's section_id stays "
        f"the TRUE id) as "
        "{\"section_id\": <sid>, \"decisions\": [{\"spec_id\": <the % <sid>-pN "
        "paragraph it touches>, \"stage\": \"weld\", \"kind\": ambiguity-resolved "
        "| substance-doubt | cross-link-opportunity | voice-choice | "
        "paragraph-restructure, \"after\": "
        "<what you did>, \"rationale\": <why>, optional \"before\": <prior "
        "form>}]}. Empty decisions list for a section with no forks. A "
        "substantive doubt is BOTH a decision record and a typed issue you "
        "RETURN - never solved in prose."
    )
    parts = [preamble]
    if voice_on:
        # DEMOTED: the profile is thin register orientation, no longer the
        # generative substrate (that is now RETRIEVED-EXEMPLARS).
        parts.append(schema.fence("REGISTER-ORIENTATION", voice_text))
        parts.append(schema.fence("RETRIEVED-EXEMPLARS",
                                  json.dumps(exemplar_channel, ensure_ascii=False, indent=1)))
    parts.append(schema.fence("DETECTOR-REPORT", json.dumps(detector, ensure_ascii=False, indent=1)))
    parts.append(schema.fence("PARAGRAPHS", json.dumps(paragraph_ids, ensure_ascii=False, indent=1)))
    parts.append(schema.fence("FRAGMENTS", json.dumps(
        {"order": order,
         "files": {sid: f"{tex_dir}/{pathsafe.encode_sid_for_path(sid)}.tex" for sid in fragments}},
        ensure_ascii=False, indent=1)))
    prompt = "\n\n".join(parts)
    from laplace.engine import telemetry
    telemetry.log("execute", skill="welder", ok=True, target=project)
    return {"worker": "weld", "target": project, "prompt": prompt, "voice_on": voice_on,
            "sections": order, "flagged": {k: len(v) for k, v in detector.items()},
            "staging": staging, "assembled_chars": assembled_chars,
            "decisions_dir": str(decisions_dir) if decisions_dir else None,
            "retrieval": retrieval_summary,
            "voice_retrieval_sidecar": voice_sidecar,
            **({'writing_style': {key: voice_context[key] for key in ('revision', 'selected_profile', 'profile_revision', 'guidance_sha256', 'genre', 'selection_origin')}} if voice_context else {}),
            "skills": ["welder", "orchestrated_generation"]}


def compile_section_dispatches(project: str, sections: list[str] | None = None,
                               repo_root: Path | None = None,
                               dials_profile: str | None = None) -> list[Path]:
    """Materialise `<sid>_dispatch.md` under the dispatches stage dir — the
    artefact the workflow's prose builders read. One producer, compiled fresh
    from the narrative packets (never from the retired briefs)."""
    proj = registry.resolve(project)
    if proj is None:
        return []
    dp = proj.stage_path("dispatches", repo_root)
    plan = proj.read_plan(repo_root) or {}
    # injectivity enforced over the whole dispatches dir before any write: two
    # distinct sids projecting to one filename is a hard error at encode time.
    pathsafe.encode_sids_for_dir(
        [sid for sec in schema.plan_sections(plan) if (sid := sec.get("id"))])
    out: list[Path] = []
    for sec in schema.plan_sections(plan):
        sid = sec.get("id")
        if sections and sid not in sections:
            continue
        d = compile_dispatch(sid, f"realise section {sid} from its closed "
                                  f"narrative specification", "prose", project,
                             repo_root, dials_profile=dials_profile)
        if "prompt" in d and dp is not None:
            dp.mkdir(parents=True, exist_ok=True)
            p = dp / f"{pathsafe.encode_sid_for_path(sid)}_dispatch.md"
            p.write_text(d["prompt"], encoding="utf-8")
            out.append(p)
    return out


#: a fragment's paragraph marker: `% <sid>-pN` on its own line.
_PARA_MARK_RE = re.compile(r"^%\s*(N[A-Za-z0-9]+)-p(\d+)\s*$")


def _fragment_paragraph_units(text: str) -> list[dict[str, Any]]:
    """Slice a fragment's rendered text into its `% <sid>-pN` units, in order.
    Each unit carries its ``paragraph_id`` and the verbatim ``text`` from its
    marker line to the line before the next marker (or EOF) — the read-only
    context a neighbouring paragraph regen joins against."""
    from laplace.manuscript.projection_viewer import parse_paragraphs
    lines = text.splitlines()
    return [{'paragraph_id': span['spec_id'], 'spec_ids': span['spec_ids'],
             'source_section': span['section'],
             'text': '\n'.join(lines[span['start_line'] - 1:span['end_line']])}
            for span in parse_paragraphs(text)]


def compile_paragraph_dispatch(project: str, section_id: str, paragraph_id: str,
                               repo_root: Path | None = None) -> dict[str, Any]:
    """A PARAGRAPH-grain slice of the section prose dispatch (BITE B3).

    Reuses the SAME closed narrative packet the prose realiser receives
    (``narrative.narrative_packet``) — never a hand-built brief, never a duplicate
    of :func:`compile_section_dispatches` — and NARROWS it to the one
    ``% <sid>-pN`` unit named by ``paragraph_id``: the packet's paragraph plans are
    sliced to that unit, its ``objects`` to that unit's input nodes, its equation
    ledger to that unit's anchor. The two ADJACENT paragraphs' RENDERED text ride
    as a read-only ``ADJACENT-PARAGRAPHS`` fence (a paragraph regen must join its
    neighbours, never rewrite them). The output contract holds the marker lines and
    every ``% NODES:``/``% PLAN:`` comment byte-fixed and bars any new claim/number/
    citation — the substance freeze at paragraph grain."""
    proj = registry.resolve(project)
    if proj is None:
        return {"error": f"unknown project {project!r}"}
    packet = narrative.narrative_packet(project, section_id, repo_root)
    if packet is None:
        return {"error": f"no narrative specification for section {section_id!r} — "
                         f"plan the narrative first (the packet IS the paragraph "
                         f"worker's frame, sliced to one unit)"}
    paras = packet.get("paragraphs") or []
    idx = next((i for i, p in enumerate(paras)
                if (p.get("paragraph_id") or f"{section_id}-p{i + 1}") == paragraph_id),
               None)
    if idx is None:
        return {"error": f"paragraph {paragraph_id!r} is not one of section "
                         f"{section_id!r}'s {len(paras)} narrative paragraphs"}
    target = paras[idx]
    wanted = set(target.get("input_nodes") or [])

    sliced = dict(packet)                       # a shallow copy; narrow the heavy channels
    sliced["paragraphs"] = [target]
    sliced["objects"] = {nid: v for nid, v in (packet.get("objects") or {}).items()
                         if nid in wanted}
    sliced["equation_ledger"] = {
        k: v for k, v in (packet.get("equation_ledger") or {}).items()
        if k == target.get("equation_anchor")}

    rr = repo_root or source_tree()
    record = sliced.get("contract") or {}
    try:
        voice_context, voice_text = _voice_dispatch_context(project, rr, record)
    except (ValueError, OSError) as error:
        return {'error': 'voice profile unavailable: ' + str(error)}

    # the two ADJACENT paragraphs' rendered text (read-only join context), sliced
    # from the CURRENT fragment by its `% <sid>-pN` markers.
    tex_dir = proj.resolved_target_dir(repo_root)
    frag = (tex_dir / f"{pathsafe.encode_sid_for_path(section_id)}.tex") if tex_dir else None
    fences: dict[str, str] = {}
    if frag is not None and frag.is_file():
        units = _fragment_paragraph_units(frag.read_text(encoding="utf-8"))
        matches = [k for k, unit in enumerate(units) if paragraph_id in unit['spec_ids']]
        if len(matches) != 1 or len(units[matches[0]]['spec_ids']) != 1:
            return {'error': 'This logical unit has merged, split, or unlocated physical occurrences. Inspect the exact source and use shared source-change reconciliation; scalar paragraph regeneration cannot choose an occurrence.',
                    'paragraph_id': paragraph_id, 'section_id': section_id,
                    'read_more': {'operation': 'structure', 'payload': {'view': 'detail', 'section_ids': [section_id], 'paragraph_id': paragraph_id}}}
        pos = matches[0]
        if pos is not None:
            if pos > 0:
                fences["previous"] = units[pos - 1]["text"]
            if pos + 1 < len(units):
                fences["next"] = units[pos + 1]["text"]

    contract = (
        "OUTPUT CONTRACT (paragraph grain)\n"
        f"1. Rewrite ONLY paragraph {paragraph_id} in "
        f"\"{tex_dir}/{pathsafe.encode_sid_for_path(section_id)}.tex\": the text between the marker "
        f"'% {paragraph_id}' and the next actual paragraph marker in this file (regardless of its identity prefix), or the fragment end. "
        f"The observed physical unit and ADJACENT-PARAGRAPHS fences define this range. Touch no other paragraph or section.\n"
        "2. The marker line and every '% NODES:' / '% PLAN:' comment are "
        "byte-preserved (node ids are identifiers, never spell-fixed).\n"
        f"3. Discharge EXACTLY the nodes realised in this unit "
        f"({', '.join(sorted(wanted)) or 'none'}); cite only keys present in the "
        "packet; anchor equations by their ledger labels.\n"
        "4. Introduce no claim, number, citation, or qualification not already "
        "present. The ADJACENT-PARAGRAPHS fence is READ-ONLY context for the "
        "join — never rewrite it.\n"
        "5. A substantive doubt the packet does not settle is a typed issue to "
        "RETURN (name the owning stage); never solve it in prose."
    )
    prompt = "\n\n".join([
        schema.PROSE_STAGE_PREAMBLE,
        schema.fence("VOICE-PROFILE", voice_text),
        schema.fence("PACKET", json.dumps(sliced, ensure_ascii=False, indent=1)),
        schema.fence("ADJACENT-PARAGRAPHS",
                     json.dumps(fences, ensure_ascii=False, indent=1)),
        contract,
    ])
    from laplace.engine import telemetry
    telemetry.log("execute", skill="orchestrated_generation", ok=True,
                  target=paragraph_id)
    return {"worker": "prose", "target": section_id, "paragraph_id": paragraph_id,
            "prompt": prompt, "nodes": sorted(wanted),
            "fences": sorted(fences.keys()),
            "skills": ["orchestrated_generation"],
            "writing_style": {key: voice_context[key] for key in ('revision', 'selected_profile', 'profile_revision', 'guidance_sha256', 'genre', 'selection_origin')}}
