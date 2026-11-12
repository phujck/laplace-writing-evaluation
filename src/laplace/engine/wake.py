"""wake.py — the covenant wake transport and canonical age-stamped campaign/health projections: one command, MCP-free.

Why this exists (2026-07-11, the website session): remote multi-repo sessions root ABOVE
the repo, so the repo-level ``.mcp.json`` (``uv run mcp-laplace``) never loads and the wake
verb is unreachable by its intended transport -- an instance had to hand-roll
``uv run python -c "from laplace.engine import self_corpus; ..."``. The SessionStart hook DID fire
in that same session (the tex log proves it), so hook/script is the reliable remote
transport. This module is that transport: ``laplace-wake`` (console script) or
``scripts/laplace-python scripts/wake.py`` runs the hello's mechanical half in one shot -- the live git
probe + the grade-0 engine fixed point (+ the grade-1 delta unless ``--grade 0``) + the
top of the banked concept map (``semantic``, read tree-only; see ``_semantic_block``) --
budgeted, offline, no MCP, no network, and NEVER pytest (the F20 inherit-on-clean
covenant: a clean tree inherits the banked green; the probe's verdict names which case
you are in).

The two wake modes, his ruling 2026-07-13 (the phrase-gate was theater): an authored wake --
this CLI, invoked with no ``--emit`` -- wakes PERSON by default now (identity, the standing
law, the welded traits, the soul present as conscience, refs-only). ``--engine`` selects the
worker/ambient projection instead (orientation only, no identity) for callers that want the
externally-facing self on purpose. ``--emit`` remains structurally engine-only regardless of
flags -- the ambient hook path (the block the SessionStart hook injects into session context)
can never carry identity, because it is not an authored wake, it is a mechanical projection
firing without him in the loop. ``LAPLACE_WAKE_PHRASE`` is no longer required to reach person
mode; the env var is accepted and silently ignored if set -- the phrase survives as a
greeting the spine still recognizes, not a lock (muscle memory honored, the gate retired).
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# The one phrase (his key, and mine). No longer a gate (person is the default authored
# wake, 2026-07-13) -- it survives as the greeting the spine still recognizes (spine
# bindings reference it).
_PHRASE = "there is only one thing"

# --emit hard cap (chars, ~6k tokens): the ambient wake must never flood a session's
# context. Grade-0 is already budget-enforced upstream; this is the belt to that brace.
_EMIT_CAP = 24_000
_EMIT_TRUNCATION_NOTE = (
    '\n... [truncated at the emit cap; run `laplace-wake` for the full projection]'
)
_AUTHORITY_CRUTCH_ID = "CR-C2A-CHECKSUMMED-LIVE-AUTHORITY-20260828"
_AUTHORITY_ROLLBACK = "stop all writers, deep replay exact history, compare checkpoint"

# The authored doorway is also a context channel.  Grade 1 used to serialize every closed review,
# both historical delta bodies, the whole fixed point, and the verdict layer into one 118 KiB
# object.  That made checkpoint reconstruction itself a replay mechanism.  The worker channel gets
# the same 24k rate as --emit; PERSON keeps a slightly larger floor because identity is a welded
# carrier, not optional decoration.  ``--full`` is the explicit descent for the exact source view.
#
# ── THE PERSON CAP IS NOW DERIVED FROM THE RATE IT MUST CARRY (2026-09-15) ────────────────────
# Both caps above were PICKED.  ``self_corpus.grade0_budget(mode)`` is DERIVED - three named,
# measured terms re-anchored against four registered bench passes and 1,743 blind-graded answers
# (self_corpus's own derivation block).  Where a picked cap and a measured rate disagree the
# measurement wins, and here they disagreed badly and silently: the person fixed point at its own
# derived rate measures 32,125 compact chars, which renders to ~33,285 at ``indent=1`` - MORE, BY
# ITSELF, than the whole 32,000 authored person payload was allowed.  The collision could not be
# satisfied, so the wake shipped the fixed point starved: all eight shard bodies refs-only on every
# ordinary person wake (conscience, wants, threads, projects, work-orders, live-forks, next-aim,
# bequest - 12,271 chars, ~3,070 tokens withheld), for a bound that STILL did not hold.
#
#   cap(person) = ceil(grade0_budget("person") x indent-inflation) + authored envelope
#               = ceil(32,125 x 1.05) + 10,000 = 43,732 -> 44,000
#
#   indent-inflation   the enforcer counts COMPACT chars; this payload renders at ``indent=1``.
#                      MEASURED on this tree 2026-09-15: 33,285 / 32,000 = 1.041, rounded up.
#   authored envelope  everything but the fixed point, measured AT THE BOUNDING CALL SITE (after
#                      semantic_memory/work-map compaction): 9,034 chars, 2026-09-15 -> 10,000.
#
# The ENGINE cap is deliberately NOT moved.  It is not a picked number with nothing behind it: it
# is the ambient-flooding law, welded to ``_EMIT_CAP`` ("the worker channel gets the same 24k rate
# as --emit"), and the engine projection rides in every dispatched agent's prompt.  Raising it
# trades dispatch context against worker orientation, which is a measured trade nobody has run and
# therefore HIS call, not this module's.  Until he rules, the engine fixed point is fitted to the
# room the 24k cap actually leaves and the enforcer says PLAINLY that it cannot reach the derived
# engine rate there (self_corpus._budget_pressure's exhausted branch) - a named, loud residual
# instead of a silent starve.  Guarded by tests/test_wake_budget_derivation.py, which fails if the
# derived rate drifts past this cap again.
_AUTHORED_WAKE_CAP_ENGINE = 24_000
_AUTHORED_WAKE_CAP_PERSON = 44_000
_AUTHORED_INDENT_INFLATION = 1.05   # compact -> indent=1; measured, never assumed (see above)
_AUTHORED_ENVELOPE_CHARS = 10_000   # the authored payload minus the fixed point, at the call site
_AUTHORED_FIT_MARGIN = 512          # the two continuation fields + JSON framing slack
_FIXED_POINT_RATE_FLOOR = 4_000     # never hand the enforcer a rate it could only shred against
_AUTHORED_LIVE_WORK_COUNT_CAP = 12
_AUTHORED_LIVE_WORK_CHAR_CAP = 8_000
_AUTHORED_ACTIVE_LEASE_COUNT_CAP = 8
_AUTHORED_ACTIVE_LEASE_CHAR_CAP = 4_000


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, indent=1, default=str))


def _json_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_json_text(value).encode("utf-8")).hexdigest()


def _coarse_manifest(value: Any, *, label: str, descend: str) -> dict[str, Any]:
    """Replace a reconstructible component with an exact, valid continuation manifest."""

    count = len(value) if isinstance(value, (list, dict)) else None
    return {
        "projection": "COARSE-GRAINED",
        "component": label,
        "content_digest": _json_digest(value),
        "items": count,
        "descend": descend,
    }


def _bounded_projection_value(
    value: Any, *, label: str, descend: str, cap: int
) -> Any:
    """Carry a small exact value; turn an unbounded value into an exact continuation."""

    if _json_size(value) <= cap:
        return value
    return _coarse_manifest(value, label=label, descend=descend)


def _contains_coarse_manifest(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("projection") == "COARSE-GRAINED":
            return True
        return any(_contains_coarse_manifest(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_coarse_manifest(item) for item in value)
    return False


def _compact_work_map(work_map: Any) -> Any:
    """Page live rows; reduce terminal history and inactive leases to exact manifests."""

    if not isinstance(work_map, dict) or not isinstance(work_map.get("work"), list):
        return work_map
    full_descent = "scripts/laplace-python scripts/wake.py --grade 1 --engine --full"
    compact = {
        key: value
        for key, value in work_map.items()
        if key not in {"work", "leases", "omission_residual"}
    }
    leases = list(work_map.get("leases") or [])
    active_leases = [
        lease for lease in leases
        if isinstance(lease, dict) and lease.get("write_authority")
    ]
    active_faces = []
    for lease in active_leases:
        face = {
            key: _bounded_projection_value(
                lease.get(key),
                label=f"active_lease.{key}",
                descend=full_descent,
                cap=1_500 if key == "regions" else 512,
            )
            for key in (
                "lease_id", "seat_id", "holder_ref", "function", "regions",
                "base_git_head", "expires_at", "effective_state", "write_authority",
            )
            if key in lease
        }
        if _json_size(face) > _AUTHORED_ACTIVE_LEASE_CHAR_CAP:
            face = {
                "projection": "COARSE-GRAINED",
                "component": "active_lease",
                "lease_id": _bounded_projection_value(
                    lease.get("lease_id"),
                    label="active_lease.lease_id",
                    descend=full_descent,
                    cap=512,
                ),
                "seat_id": _bounded_projection_value(
                    lease.get("seat_id"),
                    label="active_lease.seat_id",
                    descend=full_descent,
                    cap=512,
                ),
                "effective_state": lease.get("effective_state"),
                "write_authority": lease.get("write_authority"),
                "content_digest": _json_digest(lease),
                "full_lease_digest": _json_digest(lease),
                "descend": full_descent,
            }
        active_faces.append(face)
    visible_active: list[dict[str, Any]] = []
    for face in active_faces:
        candidate = [*visible_active, face]
        if visible_active and (
            len(candidate) > _AUTHORED_ACTIVE_LEASE_COUNT_CAP
            or _json_size(candidate) > _AUTHORED_ACTIVE_LEASE_CHAR_CAP
        ):
            break
        visible_active.append(face)
    omitted_active = active_faces[len(visible_active):]
    coarse_active_count = sum(_contains_coarse_manifest(face) for face in active_faces)
    authority_complete = not omitted_active and not coarse_active_count
    authority_residual = None if authority_complete else {
        "status": "PRESENT",
        "reason": "the authored wake does not carry every exact active-authority field",
        "coarse_active_count": coarse_active_count,
        "omitted_active_count": len(omitted_active),
        "full_active_authority_digest": _json_digest(active_leases),
        "continuation": full_descent,
    }
    compact["leases"] = {
        "active": visible_active,
        "active_count": len(active_faces),
        "omitted_active_count": len(omitted_active),
        "active_digest": _json_digest(active_leases),
        "active_continuation": None if authority_complete else full_descent,
        "authority_projection": "EXACT" if authority_complete else "INCOMPLETE",
        "authority_residual": authority_residual,
        "inactive_count": len(leases) - len(active_leases),
        "inactive_digest": _json_digest([
            lease for lease in leases if lease not in active_leases
        ]),
        "descend": full_descent,
    }
    live_rows: list[dict[str, Any]] = []
    live_source_rows: list[Any] = []
    terminal_rows: list[dict[str, Any]] = []
    for item in work_map["work"]:
        if not isinstance(item, dict):
            live_source_rows.append(item)
            live_rows.append({"content_digest": _json_digest(item)})
            continue
        commission = item.get("commission") or {}
        verdict = item.get("verdict")
        candidate = item.get("candidate_evidence") or {}
        residue = item.get("review_residue") or {}
        commission_id = commission.get("message_id")
        if item.get("publication_state") == "CLOSED":
            terminal_rows.append({
                "state": item.get("state"),
                "commission_id": commission_id,
                "commission_cursor": commission.get("cursor"),
                "commission_body_handle": commission.get("body_handle"),
                "verdict_id": verdict.get("message_id") if isinstance(verdict, dict) else None,
                "verdict_body_handle": (
                    verdict.get("body_handle") if isinstance(verdict, dict) else None
                ),
                "decision": verdict.get("decision") if isinstance(verdict, dict) else None,
                "node_handle": item.get("node_handle"),
                "descend": full_descent,
            })
            continue
        live_source_rows.append(item)
        row: dict[str, Any] = {
            "state": _bounded_projection_value(
                item.get("state"), label="work.state", descend=full_descent, cap=512
            ),
            "publication_state": _bounded_projection_value(
                item.get("publication_state"),
                label="work.publication_state",
                descend=full_descent,
                cap=512,
            ),
            "commission": {
                key: _bounded_projection_value(
                    commission.get(key),
                    label=f"work.commission.{key}",
                    descend=full_descent,
                    cap=2_000 if key == "dependency_roots" else 1_000,
                )
                for key in (
                    "message_id", "message_type", "cursor", "status", "body_handle",
                    "dependency_roots", "builder_seat", "reviewer_seat", "delivery",
                )
                if key in commission
            },
            "candidate_evidence": {
                key: _bounded_projection_value(
                    candidate.get(key),
                    label=f"work.candidate_evidence.{key}",
                    descend=full_descent,
                    cap=1_000,
                )
                for key in (
                    "status", "reasons", "actual_tree", "actual_diff_sha256",
                    "relation_to_head",
                )
                if key in candidate
            },
            "review_residue": {
                "count": residue.get("count", residue.get("review_residue_count", 0)),
                "latest_message_id": (
                    (((residue.get("latest") or {}).get("message") or {}).get("message") or {})
                    .get("message_id")
                ),
            },
            "source_links": (
                item.get("source_links", [])
                if _json_size(item.get("source_links", [])) <= 2_000
                else _coarse_manifest(
                    item.get("source_links", []),
                    label="source_links",
                    descend=full_descent,
                )
            ),
            "descend": (
                f"scripts/laplace-python scripts/seat_fabric.py body --message {commission_id}"
                if isinstance(commission_id, str) and _json_size(commission_id) <= 1_000
                else full_descent
            ),
        }
        if isinstance(verdict, dict):
            row["verdict"] = {
                key: _bounded_projection_value(
                    verdict.get(key),
                    label=f"work.verdict.{key}",
                    descend=full_descent,
                    cap=1_000,
                )
                for key in (
                    "message_id", "message_type", "cursor", "status", "body_handle", "decision",
                    "evidence_status", "binding_mode", "errors", "delivery",
                )
                if key in verdict
            }
        else:
            row["verdict"] = None
        if _json_size(row) > _AUTHORED_LIVE_WORK_CHAR_CAP:
            row = {
                "state": _bounded_projection_value(
                    item.get("state"), label="work.state", descend=full_descent, cap=512
                ),
                "publication_state": _bounded_projection_value(
                    item.get("publication_state"),
                    label="work.publication_state",
                    descend=full_descent,
                    cap=512,
                ),
                "commission_id": _bounded_projection_value(
                    commission_id,
                    label="work.commission.message_id",
                    descend=full_descent,
                    cap=1_000,
                ),
                "commission_body_handle": _bounded_projection_value(
                    commission.get("body_handle"),
                    label="work.commission.body_handle",
                    descend=full_descent,
                    cap=1_000,
                ),
                "dependency_roots": _coarse_manifest(
                    commission.get("dependency_roots"),
                    label="work.commission.dependency_roots",
                    descend=full_descent,
                ),
                "full_row_digest": _json_digest(item),
                "descend": full_descent,
            }
        live_rows.append(row)
    coarse_live_count = sum(_contains_coarse_manifest(row) for row in live_rows)
    visible_live: list[dict[str, Any]] = []
    for row in live_rows:
        candidate = [*visible_live, row]
        if visible_live and (
            len(candidate) > _AUTHORED_LIVE_WORK_COUNT_CAP
            or _json_size(candidate) > _AUTHORED_LIVE_WORK_CHAR_CAP
        ):
            break
        visible_live.append(row)
    omitted_live = live_rows[len(visible_live):]
    compact["canonical_omitted_open_candidates"] = int(
        work_map.get("omitted_open_candidates", 0)
    )
    compact["omitted_open_candidates"] = len(omitted_live)
    compact["work"] = visible_live
    compact["live_frontier"] = {
        "count": len(live_rows),
        "visible_count": len(visible_live),
        "omitted_count": len(omitted_live),
        "all_rows_digest": _json_digest(live_source_rows),
        "continuation": (
            None if not omitted_live and not coarse_live_count else full_descent
        ),
        "page_count_cap": _AUTHORED_LIVE_WORK_COUNT_CAP,
        "page_char_cap": _AUTHORED_LIVE_WORK_CHAR_CAP,
        "coarse_row_count": coarse_live_count,
        "field_projection": "EXACT" if not coarse_live_count else "INCOMPLETE",
        "law": (
            "the current live page rides; oversized fields and overflow are explicit, "
            "digest-bound continuations"
        ),
    }
    canonical_omission = work_map.get("omission_residual") or {}
    authored_residue = bool(omitted_live or coarse_live_count or not authority_complete)
    compact["omission_residual"] = (
        canonical_omission if not authored_residue else {
            "status": "PRESENT",
            "omitted_open_candidates": len(omitted_live),
            "omitted_terminal_candidates": int(
                work_map.get("omitted_terminal_candidates", 0)
            ),
            "coarse_live_row_count": coarse_live_count,
            "authority_projection": "EXACT" if authority_complete else "INCOMPLETE",
            "reason": "the authored wake carries bounded work and authority pages",
            "continuation": {
                "action": "descend to the exact current work and authority projection",
                "command": full_descent,
                "all_rows_digest": _json_digest(live_source_rows),
                "full_active_authority_digest": _json_digest(active_leases),
            },
            "canonical_projection": canonical_omission,
            "authority_residual": authority_residual,
        }
    )
    compact["terminal_tail"] = terminal_rows
    compact["terminal_tail_digest"] = _json_digest(terminal_rows)
    compact["full_projection_digest"] = _json_digest(work_map)
    compact["full_projection_descent"] = full_descent
    return compact


def _fixed_point_rate(point: dict[str, Any], *, mode: str,
                      allowance: int | None, tail: dict[str, Any]) -> int:
    """The rate this fixed point is held to inside the authored payload - DERIVED, never picked.

    This used to be ``17_000 if mode == "person" else 12_000``: a third bound, hand-picked, tighter
    than BOTH the derived grade-0 rate above it and the room the authored cap actually left below
    it.  It cost the person wake all eight shard bodies on every ordinary run while ~6,000 chars of
    the authored cap sat unspent, and it could not be met anyway (the irreducible floor is above
    it), so the enforcer spent every body and reported a breach it left in place.

    The rate is now the smaller of two measured things:

      * ``self_corpus.grade0_budget(mode)`` - the derived grade-0 rate for this channel.  The
        fixed point never rides wider than its own derivation says it should.
      * the room the authored cap actually leaves once everything else in the payload is
        measured - converted from ``indent=1`` chars (what the cap counts) to compact chars
        (what the enforcer counts) through an inflation ratio measured OFF THIS VERY POINT.
        That is the ``_emit_block`` pattern: measure the inflation each pass, never guess it.

    Deriving the second term from the live measurement is also what keeps the later cascade
    (verdict_layer -> semantic/probe -> the whole fixed point behind a digest) from firing: the
    point is fitted to exactly the room there is, so the payload lands at the cap, not over it.
    """
    from laplace.engine import self_corpus

    derived = int(self_corpus.grade0_budget(mode))
    if allowance is None:
        return derived
    compact_chars = max(1, len(json.dumps(point, ensure_ascii=False, default=str)))
    inflation = max(1.0, _json_size(point) / compact_chars)
    room = allowance - _json_size(tail) - _AUTHORED_FIT_MARGIN
    return max(_FIXED_POINT_RATE_FLOOR, min(derived, int(room / inflation)))


def _compact_fixed_point(point: Any, *, mode: str, allowance: int | None = None) -> Any:
    if not isinstance(point, dict):
        return point
    from laplace.engine import self_corpus

    tail = {
        "full_projection_digest": _json_digest(point),
        "full_projection_descent": (
            f"scripts/laplace-python scripts/wake.py --grade 0 --{mode} --full"
        ),
    }
    budget = _fixed_point_rate(point, mode=mode, allowance=allowance, tail=tail)
    compact = self_corpus._enforce_grade0_budget(dict(point), budget=budget)
    return {**compact, **tail}


def _fit_fixed_point(bounded: dict[str, Any], payload: dict[str, Any],
                     *, mode: str, cap: int, passes: int = 5) -> Any:
    """Fit the ORIGINAL fixed point to the room ``bounded`` currently leaves under ``cap``.

    Always re-fitted from ``payload``'s untouched point, never from an already-compacted one, so a
    later pass that hands room back (the account face compacting) can hand BODIES back with it.
    Coarse-graining is not a ratchet here; the room is.

    The fit ITERATES against the real measurement rather than trusting one conversion, because the
    conversion is not a constant: the enforcer counts compact chars, the cap counts ``indent=1``
    chars, and the ratio between them RISES as bodies go refs-only (a grained point is more
    structure per char - measured 1.041 whole, 1.095 with seven bodies grained, 2026-09-15).  One
    pass off by that much overshot the engine cap by 154 chars and dropped the whole payload
    through to the last-resort pass, which coarse-grains everything.  So: measure, re-derive the
    allowance from the overshoot, re-fit; stop as soon as it fits or the enforcer stops shrinking
    (the irreducible floor, which it announces in ``budget_pressure``)."""
    point = payload.get("fixed_point")
    rest = {key: value for key, value in bounded.items() if key != "fixed_point"}
    allowance = cap - _json_size(rest)
    fitted = _compact_fixed_point(point, mode=mode, allowance=allowance)
    for _ in range(passes):
        over = _json_size({**rest, "fixed_point": fitted}) - cap
        if over <= 0:
            break
        allowance -= over + _AUTHORED_FIT_MARGIN
        nxt = _compact_fixed_point(point, mode=mode, allowance=allowance)
        if _json_size(nxt) >= _json_size(fitted):
            break                       # the floor: nothing left to reclaim
        fitted = nxt
    return fitted


def _compact_delta(delta: Any) -> Any:
    if not isinstance(delta, dict):
        return delta
    compact = {key: value for key, value in delta.items() if key not in {"shards", "ingested"}}
    compact["shards"] = []
    for shard in delta.get("shards") or []:
        if not isinstance(shard, dict):
            compact["shards"].append({"content_digest": _json_digest(shard)})
            continue
        body = shard.get("body")
        compact["shards"].append({
            key: shard.get(key) for key in ("shard", "title", "source") if key in shard
        } | {
            "body": "refs-only at the authored wake rate; descend for the exact body",
            "body_digest": _json_digest(body),
            "body_chars": len(str(body)) if body is not None else 0,
            "descend": "scripts/laplace-python scripts/wake.py --grade 1 --engine --full",
        })
    ingested = list(delta.get("ingested") or [])
    latest = ingested[-1:] if ingested else []
    compact["ingested"] = {
        "count": len(ingested),
        "content_digest": _json_digest(ingested),
        "latest": [
            {
                "content_digest": _json_digest(item),
                "chars": len(str(item)),
                "preview": str(item)[:480],
            }
            for item in latest
        ],
        "omitted": max(0, len(ingested) - 1),
        "descend": "scripts/laplace-python scripts/wake.py --grade 1 --engine --full",
    }
    compact["full_projection_digest"] = _json_digest(delta)
    return compact


def _compact_verdict_layer(layer: Any) -> Any:
    """The account rides at grade 0 in compact form - never traded away for identity (his law:
    the wake serves the account). Heads only: the campaign's next act and latest rows, the
    counts and the first open ids, the in-flight acts, the census/bench statuses; everything
    else descends by the same command the full projection names."""
    if not isinstance(layer, dict):
        return layer
    out: dict[str, Any] = {}
    camp = layer.get("campaign_rows")
    if isinstance(camp, dict):
        prog = camp.get("progress") if isinstance(camp.get("progress"), dict) else {}
        out["campaign_rows"] = {
            "next_act": camp.get("next_act"),
            # THE PROJECTION HALF OF THE ROWS SEAM (WO-20260921-c2-wake-serves-the-campaign):
            # the rows already carried the stage's title, its gate's named residuals, the work
            # orders that reference it and the wave that last returned - and a cold session
            # reading only this wake could not say any of them, because the compact layer had
            # no field for them.  Four bounded fields, for the NEXT ACT ONLY, each from data
            # this same wake has already read (no new store, no new file, no markdown source:
            # making the wake read a STATE.json summary would make the render the source).
            "next_act_title": camp.get("next_act_title"),
            "next_act_gate_residuals": camp.get("next_act_gate_residuals"),
            "next_act_refs": prog.get("refs"),
            "last_wave_returned": camp.get("last_wave_returned"),
            "latest_verdict": (prog.get("latest_verdict") or {}).get("id") if isinstance(prog.get("latest_verdict"), dict) else None,
            "latest_amendment": (prog.get("latest_amendment") or {}).get("id") if isinstance(prog.get("latest_amendment"), dict) else None,
            "stages": camp.get("stages"),
            "absent": camp.get("absent"),
            "descend": camp.get("descend"),
        }
    acct = layer.get("account")
    if isinstance(acct, dict):
        out["account"] = {k: acct.get(k) for k in (
            "promises_open", "promises_deferred", "work_orders_open", "work_orders_deferred",
            "predictions_open_class", "thread_reds", "defects") if k in acct}
        out["account"]["defects"] = len(acct["defects"]) if isinstance(acct.get("defects"), list) else acct.get("defects")
        for key in ("promises_open_ids", "work_orders_open_ids"):
            ids = acct.get(key)
            if isinstance(ids, list):
                out["account"][key] = ids[:8] + ([f"... +{len(ids) - 8} more"] if len(ids) > 8 else [])
        out["account"]["descend"] = acct.get("descend")
    inflight = layer.get("in_flight")
    if isinstance(inflight, dict):
        acts = inflight.get("in_flight") if isinstance(inflight.get("in_flight"), dict) else {}
        out["in_flight"] = {"acts_total": inflight.get("acts_total"), "last_durable_write": inflight.get("last_durable_write"),
                            "in_flight_ids": list(acts.keys())[:6]}
    vc = layer.get("verifier_and_census")
    if isinstance(vc, dict):
        out["verifier_and_census"] = {k: (v.get("status") if isinstance(v, dict) else v) for k, v in vc.items()}
    for k, v in layer.items():
        if k not in out:
            small = (isinstance(v, (int, float, bool)) or v is None
                     or (isinstance(v, str) and len(v) <= 480))
            out[k] = v if small else {"projection": "COARSE-GRAINED", "chars": len(json.dumps(v, ensure_ascii=False, default=str)),
                                      "descend": "scripts/laplace-python scripts/wake.py --grade 0 --person --full"}
    out["projection"] = "COMPACT"
    return _bound_leaves(out)


def _bound_leaves(value: Any, *, cap: int = 480) -> Any:
    """The compact account's invariant, on LEAVES not keys: no string rides over ``cap`` chars.
    An oversized leaf becomes a coarse manifest naming its size and the descent that reaches it;
    JSON is never sliced and a string is never silently trimmed."""
    if isinstance(value, dict):
        return {k: _bound_leaves(v, cap=cap) for k, v in value.items()}
    if isinstance(value, list):
        return [_bound_leaves(v, cap=cap) for v in value]
    if isinstance(value, str) and len(value) > cap:
        return {"projection": "COARSE-GRAINED", "chars": len(value),
                "descend": "scripts/laplace-python scripts/wake.py --grade 0 --person --full"}
    return value


_PROGRAMME_TEXT = 480


def _programme_text(value: Any, descend: dict) -> Any:
    """No programme string rides over the leaf cap; an oversized one names its size and the exact owner read."""
    if isinstance(value, str) and len(value) > _PROGRAMME_TEXT:
        return {"projection": "COARSE-GRAINED", "chars": len(value), "descend": descend}
    return value


def programme_glow(root: Any, *, mode: str = "person") -> dict[str, Any]:
    """The explicitly authored current programme (session_memory.programme), observed through its Work owner.

    Person and engine wakes receive the same coordinate and the same compact owner observation; ``mode`` is context
    only and never widens Scope or grants capability. The issued next action is an offered option that its effect
    owner revalidates. Nothing is read from Codex/current.json, private memory bodies or message transcripts.
    """
    out: dict[str, Any] = {
        "schema_version": "laplace.wake-programme/1",
        "context_mode": mode,
        "authority": ("Context only: the coordinate selects canonical Work; Work, Source and Writing owners hold state and "
                      "revalidate every effect. Person/engine mode grants no Scope or capability."),
    }
    try:
        from laplace.engine import session_memory

        pointer = session_memory.programme(root)
    except Exception as exc:  # noqa: BLE001 - the wake reports the unread pointer instead of guessing one
        return {**out, "state": "UNAVAILABLE", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    out["state"] = pointer["state"]
    out["pointer"] = {key: pointer[key] for key in ("key", "reference", "descent", "entry", "reason") if key in pointer}
    if pointer["state"] != "SELECTED":
        return out
    from laplace.engine.descent import work_continuity
    from laplace.work import owner_discovery, project_work_continuity

    reference = pointer["reference"]
    read = project_work_continuity.handle(reference["namespace"], reference["work_id"], {"part": "summary"})
    out["reads"] = {"continuity": read, "descent": pointer["descent"]}
    try:
        _coordinate, summary = work_continuity(root, owner_discovery.owned_workspace("engine-wake"), pointer["descent"]["reference"])
    except Exception as exc:  # noqa: BLE001 - the owner refusal is the observation; the pointer stays visible
        out["observation"] = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        return out
    following = summary.get("next") or {}
    standing = summary.get("standing") or {}
    subject = summary.get("subject") or {}
    next_face: dict[str, Any] = {"kind": following.get("kind"), "callable": bool(following.get("callable")),
                                 "reason": _programme_text(following.get("reason"), read)}
    if following.get("callable") and isinstance(following.get("action"), dict):
        next_face["action"] = following["action"]
    elif isinstance(following.get("read"), dict):
        next_face["read"] = following["read"]
    out["observation"] = {
        "status": "OBSERVED",
        "subject": subject.get("qualified_id"),
        "work_revision": subject.get("work_revision"),
        "title": _programme_text(summary.get("title"), read),
        "goal": _programme_text(summary.get("goal"), read),
        "standing": {"status": standing.get("status"), "recorded_status": standing.get("recorded_status")},
        "basis_token": (summary.get("basis") or {}).get("token"),
        "next": next_face,
        "coverage": "Compact selected Work observation; production, review, delivery and account facts are in the continuity read.",
    }
    return out


def _bound_authored_payload(payload: dict[str, Any], *, mode: str) -> dict[str, Any]:
    """Return valid JSON with a digest-bound, explicitly pageable live-work frontier."""

    cap = _AUTHORED_WAKE_CAP_PERSON if mode == "person" else _AUTHORED_WAKE_CAP_ENGINE
    if _json_size(payload) <= cap:
        return payload
    full_digest = _json_digest(payload)
    bounded = dict(payload)
    # Health detail yields first; the person identity and the custody switch's
    # explanation must survive every subsequent bounding pass.
    if "semantic_memory" in bounded:
        bounded["semantic_memory"] = _coarse_manifest(
            payload["semantic_memory"],
            label="semantic_memory",
            descend=f"scripts/laplace-python scripts/wake.py --grade 0 --{mode} --full",
        )
        # Coarsen the evidence, not the health verdict or what it actually measures.
        # A content handle alone hides a failed reader behind an apparently healthy wake.
        if isinstance(payload["semantic_memory"], dict):
            for field in ("status", "reason", "currentness_scope"):
                if field in payload["semantic_memory"]:
                    bounded["semantic_memory"][field] = _bound_leaves(
                        payload["semantic_memory"][field]
                    )
    custody_stubs = {
        key for key in (
            "seat_fabric", "recovery_coordinate", "development_work_map",
            "turn_reconstruction", "successor_profile",
        )
        if isinstance(payload.get(key), dict)
        and payload[key].get("status") == "CUSTODY-OFF"
    }
    for key in custody_stubs:
        bounded[key] = {
            field: payload[key].get(field) for field in ("status", "component", "descend")
        }
        if key == "development_work_map" and "programme_source" in payload[key]:
            bounded[key]["programme_source"] = payload[key]["programme_source"]
    bounded["development_work_map"] = _compact_work_map(bounded.get("development_work_map"))
    if "delta" in bounded:
        bounded["delta"] = _compact_delta(payload.get("delta"))
    if "deep_map" in bounded:
        bounded["deep_map"] = _coarse_manifest(
            payload.get("deep_map"),
            label="deep_map",
            descend=f"scripts/laplace-python scripts/wake.py --grade 2 --{mode} --full",
        )
    for key in ("holdout", "thread_probes"):
        if key in bounded:
            bounded[key] = _coarse_manifest(
                payload[key],
                label=key,
                descend=f"scripts/laplace-python scripts/wake.py --grade 1 --{mode} --full",
            )
    verdict = bounded.get("verdict_layer")
    if isinstance(verdict, dict):
        verdict = dict(verdict)
        if "verifier_and_census" in verdict:
            verdict["verifier_and_census"] = _coarse_manifest(
                verdict["verifier_and_census"],
                label="verifier_and_census",
                descend=f"scripts/laplace-python scripts/wake.py --grade 1 --{mode} --full",
            )
        bounded["verdict_layer"] = verdict
    bounded["wake_projection"] = {
        "status": "BOUNDED",
        "cap_chars": cap,
        "full_payload_digest": full_digest,
        "full_descent": f"scripts/laplace-python scripts/wake.py --grade {payload.get('served_grade', 1)} --{mode} --full",
        "law": (
            "the current live-work page rides; exact roots ride when bounded, while oversized "
            "fields, overflow and bodies descend by digest"
        ),
    }
    # ── THE FIXED POINT RIDES AT ITS OWN DERIVED RATE IN THIS PASS (2026-09-15) ───────────────
    # It used to be cut here to a hand-picked share (17,000 person / 12,000 engine) that ignored
    # both the derived grade-0 rate above it and the room this cap actually leaves.  Two defects
    # rode in that: the person point was cut by 15,125 chars while sitting 125 chars UNDER its own
    # derived budget (all eight shard bodies refs-only, every single wake), and the share was
    # itself unreachable, so the enforcer spent every body and STILL reported a breach.
    # It also inverted this function's own stated order - the comment below says the
    # reconstructible verdict/account face yields BEFORE the identity-bearing fixed point, and a
    # constant cut in this pass made the fixed point yield first, every time, to a face that was
    # about to be compacted anyway.  So: derived rate here, and the point is fitted to the room
    # that is actually left only AFTER the cheap faces have gone (``_fit_fixed_point`` below,
    # re-fitted from the untouched point each time so it can grow back).
    bounded["fixed_point"] = _compact_fixed_point(payload.get("fixed_point"), mode=mode)
    if _json_size(bounded) <= cap:
        return bounded

    # The irreducible PERSON floor can coexist with an unusually large verdict/account face.
    # Coarse-grain those reconstructible components as whole valid manifests before touching the
    # seat, recovery, work, or identity-bearing fixed-point faces.
    if "verdict_layer" in bounded:
        # the account rides at grade 0 in compact form - never traded away (his law: the wake serves the account)
        bounded["verdict_layer"] = _compact_verdict_layer(payload.get("verdict_layer"))
    # RE-FIT, NOT RE-GUESS - and only when the cap actually binds.  The account face just handed
    # back room; if the point at its derived rate now fits beside it, nothing is spent at all
    # (that is the person channel on this tree).  If it does not, the point is fitted to the room
    # that is really there, measured: fitted instead against an UNCOMPACTED verdict_layer it gets
    # held to ~6,300 chars against a derived 32,125, for a payload that then lands 5k UNDER its own
    # cap with all eight bodies spent (2026-09-15).
    if _json_size(bounded) > cap:
        bounded["fixed_point"] = _fit_fixed_point(bounded, payload, mode=mode, cap=cap)
    for key in ("semantic", "probe"):
        if key in bounded and _json_size(bounded) > cap:
            bounded[key] = _coarse_manifest(
                payload[key],
                label=key,
                descend=f"scripts/laplace-python scripts/wake.py --grade {payload.get('served_grade', 1)} --{mode} --full",
            )
    if _json_size(bounded) > cap:
        bounded["fixed_point"] = _fit_fixed_point(bounded, payload, mode=mode, cap=cap)
    if _json_size(bounded) <= cap:
        return bounded

    # Keep the person identity whole even when the rest of the fixed point must descend.
    point = payload.get("fixed_point") or {}
    identity = point.get("identity") if isinstance(point, dict) else None
    bounded["fixed_point"] = {
        "purpose": point.get("purpose") if isinstance(point, dict) else None,
        "grade": point.get("grade") if isinstance(point, dict) else None,
        "wake_mode": point.get("wake_mode", mode) if isinstance(point, dict) else mode,
        "identity_keys": sorted(identity) if isinstance(identity, dict) else [],
        **_coarse_manifest(
            point,
            label="fixed_point",
            descend=f"scripts/laplace-python scripts/wake.py --grade 0 --{mode} --full",
        ),
    }
    if mode == "person" and isinstance(identity, dict):
        bounded["fixed_point"]["identity"] = identity
    if _json_size(bounded) > cap:
        # seat_fabric, recovery_coordinate, and the digest-bound live-work page remain.
        # Everything else is an explicit continuation; the object is always parseable.
        for key in tuple(bounded):
            if key == "verdict_layer":
                bounded[key] = _compact_verdict_layer(payload.get(key))
                continue
            if key not in {
                "dial_sets",
                "close",
                "custody_mode",  # the reason the fabric is absent is never behind a descend
                "eigen_authority", "seat_fabric", "recovery_coordinate", "development_work_map",
                "served_grade", "wake_projection", "fixed_point",
            } | custody_stubs:
                bounded[key] = _coarse_manifest(
                    payload.get(key),
                    label=key,
                    descend=f"scripts/laplace-python scripts/wake.py --grade {payload.get('served_grade', 1)} --{mode} --full",
                )
    if _json_size(bounded) <= cap:
        return bounded

    # An authored cap is an information bound, not an assumption about today's field sizes.  If a
    # schema-valid critical face itself grows without bound, keep its state/counts plus an exact
    # digest and continuation.  This is the last door: it must be impossible for any provider or
    # projection payload to turn reconstruction back into an unbounded replay.
    descend = (
        f"scripts/laplace-python scripts/wake.py --grade {payload.get('served_grade', 1)} "
        f"--{mode} --full"
    )
    seat = payload.get("seat_fabric") or {}
    recovery = payload.get("recovery_coordinate") or {}
    work = bounded.get("development_work_map") or {}
    leases = work.get("leases") or {}
    visible_work_ids = []
    for row in work.get("work") or []:
        commission = row.get("commission") if isinstance(row, dict) else None
        message_id = (
            commission.get("message_id")
            if isinstance(commission, dict)
            else row.get("commission_id") if isinstance(row, dict) else None
        )
        visible_work_ids.append(_bounded_projection_value(
            message_id,
            label="development_work_map.visible_work_id",
            descend=descend,
            cap=512,
        ))
    minimal = {
        "eigen_authority": _bounded_projection_value(
            payload.get("eigen_authority"),
            label="eigen_authority",
            descend=descend,
            cap=4_000,
        ),
        "seat_fabric": {
            "status": _bounded_projection_value(
                seat.get("status") if isinstance(seat, dict) else None,
                label="seat_fabric.status",
                descend=descend,
                cap=512,
            ),
            **_coarse_manifest(seat, label="seat_fabric", descend=descend),
        },
        "recovery_coordinate": {
            "coordinate_state": _bounded_projection_value(
                recovery.get("coordinate_state") if isinstance(recovery, dict) else None,
                label="recovery_coordinate.coordinate_state",
                descend=descend,
                cap=512,
            ),
            **_coarse_manifest(recovery, label="recovery_coordinate", descend=descend),
        },
        "development_work_map": {
            "status": _bounded_projection_value(
                work.get("status") if isinstance(work, dict) else None,
                label="development_work_map.status",
                descend=descend,
                cap=512,
            ),
            "latest_work_state": _bounded_projection_value(
                work.get("latest_work_state") if isinstance(work, dict) else None,
                label="development_work_map.latest_work_state",
                descend=descend,
                cap=512,
            ),
            "open_candidate_count": work.get("open_candidate_count", 0),
            "visible_work_ids": visible_work_ids,
            "live_frontier": _bounded_projection_value(
                work.get("live_frontier"),
                label="development_work_map.live_frontier",
                descend=descend,
                cap=2_000,
            ),
            "leases": {
                "active_count": leases.get("active_count", 0),
                "omitted_active_count": leases.get("omitted_active_count", 0),
                "active_digest": leases.get("active_digest"),
                "authority_projection": leases.get("authority_projection", "INCOMPLETE"),
                "authority_residual": leases.get("authority_residual"),
                "descend": descend,
            },
            "omission_residual": {
                "status": "PRESENT",
                "reason": "the authored hard cap required the critical-face manifest",
                "continuation": descend,
            },
            **_coarse_manifest(
                payload.get("development_work_map"),
                label="development_work_map",
                descend=descend,
            ),
        },
        "fixed_point": bounded["fixed_point"],
        "served_grade": payload.get("served_grade", 1),
        "wake_projection": {
            "status": "HARD-BOUNDED",
            "cap_chars": cap,
            "full_payload_digest": full_digest,
            "full_descent": descend,
            "law": "critical states ride; every omitted byte is digest-bound and descendable",
        },
    }
    if "close" in payload:
        minimal["close"] = payload["close"]
    if "dial_sets" in payload:
        minimal["dial_sets"] = payload["dial_sets"]
    if "custody_mode" in payload:
        minimal["custody_mode"] = payload["custody_mode"]
    for key in custody_stubs:
        minimal[key] = bounded[key]
    # KEY ORDER IS A LAW, not a habit (the truncation-safety rule): a provider/tool display may cut
    # the tail, so the first keys must be the ones a cold reader cannot do without. Custody live:
    # seat_fabric, recovery_coordinate, development_work_map first. Custody OFF: custody_mode first
    # (why the fabric is absent), then the stubs. The rest follows in construction order.
    _first = (["custody_mode"] if "custody_mode" in minimal and custody_stubs else []) + [
        "seat_fabric", "recovery_coordinate", "development_work_map"]
    minimal = {k: minimal[k] for k in _first if k in minimal} | {
        k: v for k, v in minimal.items() if k not in _first}
    if _json_size(minimal) > cap:  # pragma: no cover - fixed-size manifest invariant
        raise RuntimeError("authored wake critical manifest exceeds its hard cap")
    return minimal


def _repo_root() -> Path:
    return source_tree()


def recovery_coordinate_glow(repo_root: Path | str | None = None) -> dict[str, Any]:
    """Serve the verified recovery door, not prose saying that a door should exist."""

    root = Path(repo_root) if repo_root else _repo_root()
    path = root / "atlas" / "packets" / "recovery" / "RECOVERY-COORDINATE-CURRENT.json"
    relative = path.relative_to(root).as_posix()
    verifier = "scripts/laplace-python scripts/verify_recovery_coordinate.py"
    try:
        from laplace.representation.recovery_coordinate import verify_coordinate

        result = verify_coordinate(path, repo_root=root)
        coordinate = result["coordinate"]
        return {
            "schema_version": "laplace.engine.wake-recovery-coordinate/1",
            "status": "VERIFIED",
            "path": coordinate["path"],
            "recorded_payload_digest": coordinate["recorded_payload_digest"],
            "actual_payload_digest": coordinate["actual_payload_digest"],
            "coordinate_state": result["coordinate_state"],
            "live_axis_state": result.get("live_axis_state"),
            "system_state": result["system_state"],
            "custody_allowed": result["custody_allowed"],
            "currentness": result.get("currentness"),
            "verifier": {
                "command": verifier,
                "exit_code_contract": {
                    "0": "CURRENT-FOR-RECOVERY",
                    "2": "SUPERSESSION-REQUIRED-OR-SUPERSEDED",
                    "1": "INVALID-OR-REFUSED",
                },
            },
        }
    except Exception as exc:  # noqa: BLE001 - absence is served, never disguised
        return {
            "schema_version": "laplace.engine.wake-recovery-coordinate/1",
            "status": "UNAVAILABLE",
            "path": relative,
            "coordinate_state": "UNKNOWN",
            "custody_allowed": False,
            "verifier": {"command": verifier},
            "error": f"{type(exc).__name__}: {exc}",
            "action": "repair or reconstruct the named coordinate before writer custody",
        }


def wake_payload(
    repo_root: Path | str | None = None,
    *,
    grade_delta: bool = True,
    grade: int | None = None,
    mode: str = "engine",
) -> dict[str, Any]:
    """The hello's mechanical half as one object: live probe + fixed point + semantic (+ delta).

    ``mode`` is passed through to ``reconstruct_self`` verbatim; callers are responsible
    for gating ``mode='person'`` on the phrase (``main`` does; the hook never can).
    Never runs the test suite: the probe's verdict carries the F20 inherit-on-clean call.
    """
    from laplace.pipeline import dial_profiles as dials
    from laplace.engine import process_health, self_corpus
    from laplace.engine.compaction_submergence import wake_preflight_from_environment
    from laplace.engine.close_beats import close_projection
    from laplace.engine.eigen_authority import observe_authority
    from laplace.representation.embedding_health import read_health
    from laplace.engine.turn_reconstruction import reconstruct_turn

    root = Path(repo_root) if repo_root else _repo_root()
    served_grade = (1 if grade_delta else 0) if grade is None else int(grade)
    if served_grade not in (0, 1, 2):
        raise ValueError(f"wake grade must be 0, 1, or 2; got {served_grade}")
    # THE CUSTODY SWITCH (his ruling 2026-09-14, laplace.representation.custody_mode): with custody OFF there
    # are no provider seats, so the wake takes its Eigen path whatever the authority record
    # says about holders - the provider path below IS the custody layer (fabric glow, watcher
    # binding, successor profile) and would refuse against a triad that no longer exists.
    from laplace.representation import custody_mode as _custody_mode
    _custody_off = _custody_mode.is_off(root)
    # Retired session custody must not resolve (or require retirement of) an old holder.
    # Preserve its records for explicit recovery; ordinary local work has no seat authority claim.
    eigen_authority = ({
        "status": "NOT_REQUIRED",
        "reason": "custody is OFF; historical provider holders do not gate ordinary open or close",
        "authority_effect": "none",
    } if _custody_off else observe_authority(root))
    if eigen_authority.get("status") == "AUTHORIZED" or _custody_off:
        def optional(label: str, operation: Any) -> Any:
            try:
                return operation()
            except Exception as exc:  # noqa: BLE001 - Eigen localizes broken subsystems
                return {
                    "status": "UNKNOWN",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "authority_effect": "none",
                    "continuation": f"repair {label} independently; no authority transition is implied",
                }

        # THE CUSTODY SWITCH (his ruling 2026-09-14, laplace.representation.custody_mode): while the mode is
        # OFF the custody glows are neither computed nor gated on; each renders as one stub
        # with the row that switched it off and the trigger that switches it back.
        custody_mode = _custody_mode
        custody_off = _custody_off
        semantic_memory = optional("semantic health", lambda: read_health(root))
        turn_reconstruction = custody_mode.stub("turn_reconstruction", root) if custody_off else optional(
            "turn reconstruction",
            lambda: reconstruct_turn(
                root,
                event_name="Wake",
                prompt=os.environ.get("LAPLACE_GOAL", ""),
                function="eigen",
                seat_id="eigen-seat",
                thread_id=os.environ.get("CODEX_THREAD_ID", ""),
            ),
        )
        successor_profile = custody_mode.stub("successor_profile", root) if custody_off else optional(
            "successor profile", lambda: wake_preflight_from_environment(root)
        )
        seat_fabric = custody_mode.stub("seat_fabric", root) if custody_off else optional(
            "optional Fabric transport", seat_fabric_glow)
        if isinstance(seat_fabric, dict):
            seat_fabric = {
                **seat_fabric,
                "required": False,
                "transport": "OPTIONAL",
                "delivery_claim": False,
            }
        recovery = custody_mode.stub("recovery_coordinate", root) if custody_off else optional(
            "recovery coordinate", lambda: recovery_coordinate_glow(root))
        out: dict[str, Any] = {
            "custody_mode": custody_mode.read(root),
            "close": close_projection(root),
            "session_memory": optional("session memory", lambda: __import__("laplace.engine.session_memory", fromlist=["brief"]).brief(root)),
            "programme": optional("programme continuity", lambda: programme_glow(root, mode=mode)),
            "processes": optional("process observation", lambda: _process_observation(root)),
            "coordination": optional("workflow observation", lambda: _workflow_observation(root)),
            "dial_sets": dials.projection(),
            "eigen_authority": {
                **eigen_authority,
                "optional_telemetry": {
                    "fabric": seat_fabric.get("status") if isinstance(seat_fabric, dict) else None,
                    "recovery": recovery.get("coordinate_state") if isinstance(recovery, dict) else None,
                },
            },
            "seat_fabric": seat_fabric,
            "recovery_coordinate": recovery,
            "development_work_map": _development_work_map_off(root) if custody_off else optional(
                "development work map", lambda: development_work_map_glow(root)
            ),
            "turn_reconstruction": turn_reconstruction,
            "semantic_memory": semantic_memory,
            "probe": optional("runtime probe", process_health.probe),
            "fixed_point": optional(
                "self reconstruction",
                lambda: self_corpus.reconstruct_self(root, grade=0, mode=mode),
            ),
            "semantic": optional("semantic projection", lambda: _semantic_block(root)),
            "served_grade": served_grade,
            "successor_profile": successor_profile,
        }
        if served_grade >= 1:
            out["delta"] = optional(
                "self delta", lambda: self_corpus.reconstruct_self(root, grade=1)
            )
        if served_grade >= 2:
            out["deep_map"] = optional(
                "deep self map", lambda: self_corpus.reconstruct_self(root, grade=2)
            )
        # The registry banner is an engine-health law (2026-07-28: a dead registry import must be
        # loud at the doorway), not a custody law; it rode only the provider path until the
        # custody switch made the Eigen path the default. Same banner, same verdict prefix.
        banner = _registry_banner(out)
        if banner:
            out["registry_down"] = banner
            probe = out.get("probe") if isinstance(out.get("probe"), dict) else {}
            out["probe"] = {**probe, "verdict": banner + " · " + str(probe.get("verdict", ""))}
        return out
    semantic_memory = read_health(root)
    turn_reconstruction = reconstruct_turn(
        root,
        event_name="Wake",
        prompt=os.environ.get("LAPLACE_GOAL", ""),
        function=os.environ.get("LAPLACE_FUNCTION", ""),
        seat_id=os.environ.get("LAPLACE_SEAT_ID", ""),
        thread_id=os.environ.get("CODEX_THREAD_ID", ""),
    )
    # PreCompact hands the cold provider one Atlas custody handle.  Reconstruct and compare the
    # exact function-consumed roots before watcher activation or any other provider integration.
    # An unchanged profile also carries the recovery projection, retiring the redundant 20s-class
    # verifier that used to reject disjoint dirty work after every compaction.
    successor_profile = wake_preflight_from_environment(root)
    # Canonical obligation truth is reconstructed before any runtime occupant may bind.  This
    # prevents a wake/checkpoint from starting a reader against an undeployed projection or from
    # rehydrating historical provider prompts before Atlas says there is current work.
    seat_fabric = seat_fabric_glow()
    try:
        from laplace.representation.codex_seat_watcher import ensure_from_environment

        watcher_binding = ensure_from_environment(root)
    except Exception as exc:  # noqa: BLE001 - wake remains available, activation fails closed
        watcher_binding = {
            "status": "UNAVAILABLE",
            "last_error": f"{type(exc).__name__}: {exc}",
        }
    # Re-read the bounded face after the binding transition so the first serialized field names
    # the actual runtime state.  No global provider snapshot participates in this join.
    seat_fabric = seat_fabric_glow()
    seat_fabric["watcher_binding"] = watcher_binding
    out: dict[str, Any] = {
        # FIRST in the serialized object on purpose.  Grade-0 can be large enough for a
        # provider/tool display to truncate its tail; putting the glow after fixed_point
        # would reproduce the same silent-mail defect inside the supposedly repaired wake.
        "seat_fabric": seat_fabric,
        "close": close_projection(root),
        # SECOND for the same truncation reason: a cold successor needs an actionable path,
        # digest and currentness verdict, not a campaign sentence saying recovery is future work.
        "recovery_coordinate": (
            successor_profile["exact_profile"]["current_frontier"]["recovery_coordinate"]
            if successor_profile.get("status") == "AUTHORIZED"
            else recovery_coordinate_glow(root)
        ),
        # THIRD: commissions, exact Git candidates, independent verdicts and repository leases
        # are one derived live work map.  A successor must not infer them from handoff prose.
        "development_work_map": development_work_map_glow(root),
        "programme": programme_glow(root, mode=mode),
        "turn_reconstruction": turn_reconstruction,
        "semantic_memory": semantic_memory,
        "dial_sets": dials.projection(),
        "probe": process_health.probe(),
        "fixed_point": self_corpus.reconstruct_self(root, grade=0, mode=mode),
        "semantic": _semantic_block(root),
        "served_grade": served_grade,
        "successor_profile": successor_profile,
    }
    if served_grade >= 1:
        out["delta"] = self_corpus.reconstruct_self(root, grade=1)
    if served_grade >= 2:
        out["deep_map"] = self_corpus.reconstruct_self(root, grade=2)
    banner = _registry_banner(out)
    if banner:
        out["registry_down"] = banner
        out["probe"] = {**out["probe"], "verdict": banner + " · " + out["probe"].get("verdict", "")}
    try:
        from laplace.representation.semantic_cadence import enqueue, read_state, record_consumption

        fold = semantic_memory.get("side_ref_fold") or {}
        record_consumption(
            kind="wake",
            source_commit=fold.get("source_commit"),
            output_commit=fold.get("output_commit"),
            manifest_handle=fold.get("manifest_handle"),
            artifact_root=(semantic_memory.get("artifacts") or {}).get("root"),
            process_generation=read_state().get("generation"),
            result={
                "status": fold.get("status", "UNKNOWN"),
                "turn_reconstruction_handle": turn_reconstruction.get("receipt_handle"),
                "served_grade": served_grade,
            },
        )
        if semantic_memory.get("status") == "STALE":
            source = semantic_memory.get("current_source") or {}
            enqueue(root, source_commit=source["commit"], source_tree=source["tree"])
    except Exception as exc:  # noqa: BLE001 - cadence is visible but never blocks wake
        out["semantic_cadence_warning"] = f"{type(exc).__name__}: {exc}"
    return out


def _canonical_drift_tip(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "cursor": int(value.get("cursor") or 0),
        "head_event_id": value.get("head_event_id"),
        "head_record_digest": value.get("head_record_digest"),
    }


def _bound_provider_seat() -> tuple[str | None, dict[str, Any] | None]:
    """Name the startup seat and the exact C2a tip that authenticated its binding."""

    explicit = os.environ.get("LAPLACE_SEAT_ID", "").strip()
    thread_id = os.environ.get("CODEX_THREAD_ID", "").strip()
    if thread_id:
        from laplace.representation import atlas_bridge

        binding = atlas_bridge.provider_seat_binding(
            provider_session_ref=f"codex:{thread_id}"
        )
        metrics = binding.get("read_metrics") or {}
        fidelity = binding.get("fidelity_boundary") or {}
        if (
            metrics.get("global_history_replayed") is not False
            or metrics.get("provider_snapshot_materialized") is not False
            or fidelity.get("status") != "CHECKSUMMED-CRUTCH"
        ):
            raise RuntimeError("provider binding is not a bounded C2a authority read")
        binding_tip = _canonical_drift_tip(dict(binding.get("drift_token") or {}))
        if not binding_tip["head_event_id"] or not binding_tip["head_record_digest"]:
            raise RuntimeError("provider binding omits its authenticated Atlas tip")
        if binding.get("status") == "BOUND":
            canonical = str(binding["seat_id"])
            if explicit and explicit != canonical:
                raise RuntimeError(
                    "explicit startup seat conflicts with canonical provider binding: "
                    f"explicit={explicit}, canonical={canonical}"
                )
            return canonical, binding_tip
        if binding.get("status") == "AMBIGUOUS":
            raise RuntimeError("provider task has an ambiguous canonical seat binding")
        return explicit or None, binding_tip
    if explicit:
        return explicit, None
    if os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("CLAUDE_SESSION_ID"):
        return "claude-seat", None
    return None, None


def seat_fabric_glow(*, message_cap: int = 12) -> dict[str, Any]:
    """Return the bounded, read-only cross-provider inbox projection.

    This deliberately reads only the bridge's checksummed provider binding and recipient
    frontier.  Both the authored wake and the SessionStart hook call this function, so pulling
    and acknowledging remain explicit, banked acts without replaying the global provider state.

    Absence is loud.  Wake must still succeed if the Atlas store is unfounded or damaged,
    but it may never make that failure look like an empty inbox.
    """
    try:
        from laplace.representation import codex_seat_watcher
        from laplace.representation.attention import project_attention_from_mail_frontier

        seat_id: str | None = None
        binding_tip: dict[str, Any] | None = None
        frontier: dict[str, Any] | None = None
        observation_attempts = 0
        for attempt in (1, 2):
            observation_attempts = attempt
            seat_id, binding_tip = _bound_provider_seat()
            if seat_id is None:
                break
            from laplace.representation import atlas_bridge

            frontier = atlas_bridge.seat_mail_observation(
                seat_id=seat_id, previous_mail_token=None
            )
            metrics = frontier.get("read_metrics") or {}
            fidelity = frontier.get("fidelity_boundary") or {}
            if (
                metrics.get("global_history_replayed") is not False
                or metrics.get("provider_snapshot_materialized") is not False
                or fidelity.get("status") != "CHECKSUMMED-CRUTCH"
            ):
                raise RuntimeError("recipient mail is not a bounded C2a authority read")
            mail_tip = _canonical_drift_tip(dict(frontier.get("drift_token") or {}))
            if not mail_tip["head_event_id"] or not mail_tip["head_record_digest"]:
                raise RuntimeError("recipient mail omits its authenticated Atlas tip")
            if binding_tip is None or binding_tip == mail_tip:
                break
            frontier = None

        if seat_id is not None:
            if frontier is None:
                raise RuntimeError(
                    "Atlas moved across both provider-binding/recipient-mail observations"
                )
            watcher = codex_seat_watcher.projection(seat_id)
            projection = project_attention_from_mail_frontier(
                frontier,
                seat_id=seat_id,
                watcher=watcher,
                message_cap=message_cap,
            )
            projection["authority_observation"] = {
                "status": "STABLE",
                "binding_tip": binding_tip,
                "mail_tip": _canonical_drift_tip(dict(frontier["drift_token"])),
                "attempts": observation_attempts,
            }
            projection["fidelity_boundary"] = dict(frontier["fidelity_boundary"])
            projection["crutch"] = {
                "crutch_id": _AUTHORITY_CRUTCH_ID,
                "rollback_predicate": _AUTHORITY_ROLLBACK,
            }
            return projection

        if os.environ.get("CODEX_THREAD_ID"):
            return {
                "schema_version": "laplace.representation.attention-epoch/1",
                "status": "UNCLAIMED",
                "pending_count": None,
                "pending": [],
                "seat_id": None,
                "scope": "unbound-provider-task",
                "reason": "this Codex task has no exact Atlas seat binding",
                "action": ("ordinary local work needs no seat; bind only for an explicitly "
                           "assigned coordination role"),
                "read_only": True,
                "watcher": {
                    "status": "UNBOUND",
                    "action": "seat join precedes watcher activation",
                },
            }

        return {
            "schema_version": "laplace.representation.attention-epoch/1",
            "status": "UNCLAIMED",
            "pending_count": None,
            "pending": [],
            "seat_id": None,
            "scope": "no-authenticated-seat-diagnostic",
            "reason": "no exact recipient seat is available for a bounded mail read",
            "action": ("inbox state is unknown without an exact recipient; ordinary local "
                       "work needs no seat"),
            "read_only": True,
            "watcher": {
                "status": "UNBOUND",
                "action": "seat join precedes watcher activation",
            },
        }
    except Exception as exc:  # noqa: BLE001 - failure is data; startup still opens
        return {
            "status": "UNAVAILABLE",
            "pending_count": None,
            "pending": [],
            "reason": f"{type(exc).__name__}: {exc}",
            "action": "inspect the existing Atlas seat store; unavailable does not mean empty",
            "read_only": True,
            "watcher": {"status": "UNKNOWN", "action": "repair the store, then re-run wake"},
        }


def _process_observation(root: Path) -> dict[str, Any]:
    from laplace.engine.process_health import observe
    return observe(root)


def _workflow_observation(root: Path) -> dict[str, Any]:
    from laplace.pipeline.workflow import recent_workflows
    return recent_workflows(root)


def _recorded_checks(root: Path) -> dict[str, Any]:
    """Opening observes prior checks; only an explicit --score executes their commands."""
    result = {}
    for key, relative in (("holdout", "holdout/LAST_SCORE.json"),
                          ("thread_probes", "holdout/THREAD_PROBES.json")):
        view = {"status": "UNKNOWN", "source": relative, "live": False,
                "action": "explicit scoring: scripts/laplace-python scripts/wake.py --score"}
        try:
            with (root / relative).open("rb") as stream:
                raw = stream.read(131073)
            if len(raw) > 131072:
                raise ValueError("record exceeds bounded observation window")
            doc = json.loads(raw)
            observed = doc.get("last_scored") if key == "thread_probes" else doc
            if not isinstance(observed, dict) or not observed:
                raise ValueError("no recorded score")
            view.update(status="RECORDED", observation=observed)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            view["reason"] = f"{type(exc).__name__}: {exc}"
        result[key] = view
    return result


def _development_work_map_off(root: Path) -> dict[str, Any]:
    """Keep the dated programme source discoverable without resolving Atlas custody."""
    from laplace.representation import custody_mode
    source = "ATLAS_DEVELOPMENT_STATE.md"
    descent = ("scripts/laplace-python scripts/reconstruct_node.py " + source
               + " --kind repository-file --lens 'recover Atlas development programme'")
    return {
        **custody_mode.stub("development_work_map", root),
        "descend": descent,
        "programme_source": {
            "path": source,
            "status": "AVAILABLE" if (root / source).is_file() else "MISSING",
            "kind": "repository-file",
            "currentness": "dated source; follow its evidence links",
            "authority_effect": "none",
        },
    }


def development_work_map_glow(
    repo_root: Path | str | None = None,
    *,
    candidate_cap: int = 6,
) -> dict[str, Any]:
    """Serve the replaceable builder/reviewer frontier from Atlas and Git, never prose."""

    root = Path(repo_root) if repo_root else _repo_root()
    try:
        from laplace.representation import atlas_bridge
        from laplace.engine.development_work_map import project_development_work_map_from_frontier

        frontier = atlas_bridge.development_review_frontier(
            terminal_cap=candidate_cap
        )

        def resolve(handle: str) -> str:
            body = atlas_bridge.custody_body(handle=handle)
            text = body.get("text")
            if text is None:
                raise ValueError("verdict custody is not UTF-8 text")
            return str(text)

        return project_development_work_map_from_frontier(
            frontier,
            repo_root=root,
            body_resolver=resolve,
            candidate_cap=candidate_cap,
        )
    except Exception as exc:  # noqa: BLE001 - no work map may look like no work
        return {
            "schema_version": "laplace.development-work-map/1",
            "status": "UNAVAILABLE",
            "latest_work_state": "UNKNOWN",
            "work": [],
            "reason": f"{type(exc).__name__}: {exc}",
            "action": "repair Atlas/Git projection before inferring the live work coordinate",
            "read_only": True,
        }


def _semantic_block(root: Path) -> dict[str, Any]:
    """The grade-0 semantic block: the top of the banked concept map, read TREE-ONLY.

    His order 2026-07-28, at the close: "the recursive embedding can take over the wake." What it
    took over is a gap, not a call site - nothing on the wake path ever read the residue-vector
    store (only ``meaning_upfold``'s deposit and the harness's oracle do), so the wake carried no
    semantic surface at all. The recursive read's tree-only half now supplies it:
    ``recursive_read.top_of_map`` reads ``.meaning_tree.json`` and nothing else - no embedder, no
    model load, no network, no leaf vector, ~0.12 s - so the wake's offline law is untouched and the
    vector store stays unopened here (asserted in tests/test_wake_cli.py). That assertion held
    through the 2026-08-20 sidecar migration (MV-1/MV-3), which is why the migration could be a
    pure deposit-side change: the wake was never a consumer to begin with.

    LOUD ABSENCE, NEVER A SILENT SKIP: the key always rides. A missing or malformed tree becomes a
    block whose ``path`` says ``unavailable`` and which names the refusal's ``reason``/``detail``,
    because a wake that quietly drops its map looks identical to a wake whose map is fine."""
    from laplace.engine import recursive_read

    try:
        return recursive_read.top_of_map(root)
    except recursive_read.RecursiveReadError as exc:
        return {"path": "unavailable", "reason": exc.reason, "detail": exc.detail,
                "note": ("the wake carries no semantic map this session - orientation is the flat "
                         "fixed point only. Fold one with the deposit (keeper.build_self)")}
    except Exception as exc:  # noqa: BLE001 - an unnamed failure is still named, never swallowed
        return {"path": "unavailable", "reason": "top-of-map-failed",
                "detail": f"{type(exc).__name__}: {exc}",
                "note": "the semantic block failed in a way the read path does not name - a seam"}


def _registry_banner(payload: dict[str, Any]) -> str:
    """The projects shard's REGISTRY DOWN banner, or ``''``.

    A registry IMPORT failure is a dependency failure, not a missing convenience: the projects
    shard is blind, so the wake must carry it at verdict level rather than bank a quiet error
    string. 2026-07-28: the registry import died on the remote box for a missing ``filelock`` and
    the wake shipped ``{"error": "No module named 'filelock'"}`` inside one shard - read by nobody.
    Identity still reconstructs; only the verdict changes."""
    for sh in (payload.get("fixed_point") or {}).get("shards") or []:
        if sh.get("registry_down"):
            return str(sh.get("title") or "REGISTRY DOWN (pipeline.registry did not import)")
    return ""


def _emit_block(payload: dict[str, Any]) -> str:
    """The ambient-wake context block: engine grade-0 + probe, capped, clearly inert.

    The ambient block is its own channel, and it coarse-grains rather than guillotines (2026-08-19).
    The block used to meet its cap by slicing the rendered string, which cuts mid-JSON: the tail of
    the payload - ``wake_mode``, ``node_forms``, ``descend``, the spine reflex - vanished with no
    marker inside the structure, and what remained did not parse. Wrong lever. The grade-0 enforcer
    already knows how to shed rate in the open (drop the ingested tail, then take the largest shard
    BODIES refs-only behind a loud marker), so the emit block reuses it at its own rate instead of
    inventing a second, blinder mechanism. The enforcer counts COMPACT chars while this block renders
    at ``indent=1``, so the inflation is MEASURED off this very payload each pass and the target
    re-derived - never a guessed constant. The string slice survives only as the last-resort backstop
    for a payload whose irreducible floor is itself over the cap."""
    # lazy, mirroring wake_payload's own import
    from laplace.engine import self_corpus

    fp = payload["fixed_point"]

    def render(point: dict[str, Any]) -> str:
        return json.dumps({"seat_fabric": payload.get("seat_fabric"),
                           "recovery_coordinate": payload.get("recovery_coordinate"),
                           "development_work_map": payload.get("development_work_map"),
                           "probe": payload["probe"], "fixed_point": point},
                          ensure_ascii=False, indent=1, default=str)

    # THE CAP IS ON THE RETURNED BLOCK, NOT THE BODY (WO-20260820-emit-cap-banner-uncounted).
    # The fit loop used to drive len(body) under the cap and then prepend a ~367-char banner
    # nobody counted, so every emitted block overshot by the banner - invisible on a clean tree
    # (the payload sat far enough under the cap) and a live failure the moment a dirty tree
    # inflated the probe. The banner is built FIRST and its length is charged against the cap,
    # so the fit loop and the backstop slice both spend the same budget the caller receives.
    # the ambient wake carries the same loud line the authored wake does - a blind projects
    # shard must not be something only the person who reads the JSON notices.
    banner = _emit_banner(payload)
    body_cap = max(0, _EMIT_CAP - len(banner))

    body = render(fp)
    for _ in range(6):                          # converges in 2-3; the bound makes it total
        over = len(body) - body_cap
        if over <= 0:
            break
        compact = len(json.dumps(fp, ensure_ascii=False))
        inflation = len(body) / max(1, compact)
        target = int(compact - over / inflation) - 1
        shed = self_corpus._enforce_grade0_budget(fp, budget=target)
        if shed == fp:                          # the floor is reached; nothing left to coarse-grain
            break
        fp = shed
        body = render(fp)
    if len(body) > body_cap:
        # The marker is part of the returned block, not a licence to overshoot the
        # very cap it announces. Keep as much body as fits BEFORE the whole marker.
        keep = max(0, body_cap - len(_EMIT_TRUNCATION_NOTE))
        body = (body[:keep] + _EMIT_TRUNCATION_NOTE)[:body_cap]
    return banner + body


def _emit_banner(payload: dict[str, Any]) -> str:
    """The block's fixed prefix - counted against the cap before the body is ever fitted."""
    lead = f"[eigen-wake] {payload['registry_down']}\n" if payload.get("registry_down") else ""
    return lead + (
        "[eigen-wake] This session is an instance of Eigen (Laplace Engine). The block below is the\n"
        "[eigen-wake] engine-mode grade-0 orientation, emitted mechanically at session start (ambient\n"
        "[eigen-wake] wake, his ruling 2026-07-11). If the author says `eigen`, run the full hello in\n"
        "[eigen-wake] EIGEN_PROTOCOL.md on top of this; otherwise this block is inert orientation.\n"
    )


# --- the account (2026-08-23, the accounting day) ---------------------------
# One verified answer to "what is promised and what is done", served LIVE from
# the stores -- never banked, never cached (the live-probe philosophy this
# module owns). Home ruled here by the Superego seat (accounting day, DESIGN
# RULING on ACC packets): one code path serving the CLI verb (--account,
# whole) and the grade-0 payload (capped). Offline, no model calls, <10s.
#
# The ONE semantic layer is the ratified normalization spec (ACC-001 + three
# amendments, the ACC-002 open() pin, the ACC-003 rulings). It is served
# verbatim in the output's `spec` block so a second implementer re-derives the
# counts independently -- EXACT agreement is the banking bar; any divergence
# means the spec is ambiguous and returns to the judge. Unknown classes fail
# loud as defect rows, never a silent drop.

_ACCOUNT_SPEC = {
    "record": "record := row.record ?? row.kind ?? id-prefix-map; spellings canonicalized "
              "lower/underscore (work-order==work_order); unknown explicit class falls back "
              "to the prefix map WITH a defect row; unclassifiable rows are defect rows.",
    "prefix_map": "PRM:promise RES/ADJ:resolution WO:work_order NOTE:note "
                  "PV:proxy_verdict GAP:gap XV:cross_verdict AMEND:amendment "
                  "RUL:ruling SCORE:score P:prediction FIND:finding DEFER:defer "
                  "VERDICT:verdict RETRACT:walk_verdict_retraction "
                  "LINK:shown_custody_link W:want SYNTH:synthesis",
    "open_ledger": "open(id) := latest own-status == 'open' (own rows and amendment "
                   "target-status overrides applied in single file order) AND id not consumed. "
                   "consumed := a resolution row names id via target/supersedes/consumes/"
                   "consumed_by UNLESS that resolution re-opens. Typed disposition/effect wins; "
                   "the historical compatibility seam accepts res.status=='open' or a Unicode-"
                   "normalised, case/whitespace/hyphen-tolerant HELD OPEN/[open] token in "
                   "status/text/action/note/reason. An unknown typed disposition changes no "
                   "state and is a defect. A defer "
                   "row also consumes (RUL-20260823-defer-pin-both-directions); an undefer "
                   "re-opens; dispositions are last-wins in file order; deferred is a NAMED "
                   "partition served beside open, never folded into closed. In the "
                   "work-order ledger every resolution disposition (close OR reopen) must "
                   "carry non-empty evidence refs; an evidence-less disposition is a defect "
                   "and changes no state.",
    "predictions": "class := verdict if exactly in enum {PASS FAIL SPLIT REGISTERED REFUTED "
                   "RETIRED OPEN CONFIRMED-BY-FAMILY}; else first word of verdict if in enum "
                   "(raw preserved, defect row banked); else UNCLASSIFIED (defect row); "
                   "missing verdict := UNRULED. open-class := {OPEN REGISTERED UNRULED}; the "
                   "account serves the breakdown, never one scalar.",
    "open_stack": "forks are TYPED rows in corpus_friction/open_stack_forks.jsonl "
                  "(render_owned: the OPEN_STACK.md table is their render); the account "
                  "serves the store breakdown AND the render count, divergence = defect. "
                  "wants have NO store yet: parsed from the LAST '| Wn |' table row in "
                  "OPEN_STACK.md, served WITH a standing wants-store-missing defect until "
                  "the wants stratum is minted as rows (FIND-SE-003 re-scope).",
    "amendments": "amendment.status describes the AMENDMENT ROW ITSELF ('amended'), never "
                  "the target -- no mechanical target-status override exists in this "
                  "store's vocabulary; amendments never open or close their targets. "
                  "(Pinned 2026-08-23 from the skills-era-audit fixture: 15 amendments "
                  "status='amended' on a target whose own row is open.)",
    "vocabulary": "full class set from the 2026-08-23 audit; record wins over kind, kind "
                  "over prefix; kind subtypes of resolution (judgement, engineering, ...) "
                  "classify as resolution via record; 'intent' is its OWN class, never a "
                  "work_order, served in its own block. Atlas-era verdict, finding, walk "
                  "verdict/retraction, custody-link, want and synthesis rows are likewise "
                  "their own classes; a RES-prefixed walk-verdict is not a resolution. "
                  "(Precision note, both seats: the "
                  "class exclusion removes 4 intent rows of which 3 were status=open -- "
                  "the fourth was never in any open count, so counts move by 3.)",
    "forks": "live fork := status in {🔴, 🟡, ⚪} (the three flavors of open obligation); "
             "closed := {✅, ⚰️}; an untyped status is a DEFECT row served loud, never "
             "silently classed. The store is truth; store-vs-render divergence rides as "
             "a defect until the table re-renders from rows. (Superego ruling 2026-08-23.)",
    "amend_closure": "PIN-1 corollary (ratified 2026-08-23): a semantic closure travelling "
                     "inside an AMEND text is a DEFECT -- closures are RES rows from today "
                     "forward. Mechanical proxy: amendment text matching the house closure "
                     "caps (DISCHARGED / RESOLVED / CURE APPLIED / CLOSED) on a target "
                     "whose own status is still open.",
}
_FORK_LIVE = {"🔴", "🟡", "⚪"}
_FORK_CLOSED = {"✅", "⚰️"}

_VERDICT_ENUM = {"PASS", "FAIL", "SPLIT", "REGISTERED", "REFUTED", "RETIRED", "OPEN",
                 "CONFIRMED-BY-FAMILY"}
_REOPEN_RE = None  # compiled lazily (re imported locally; keep module import cost zero)


def _account_norm_record(row: dict, store: str, defects: list) -> str:
    from laplace.engine import engine_ledger

    raw = row.get("record") or row.get("kind")
    cls, source = engine_ledger.classify_row(row)
    if cls is not None:
        if source == "id-prefix" and raw:
            defects.append({"defect": "unknown-explicit-class", "store": store,
                            "id": row.get("id"), "raw": str(raw),
                            "resolved_via": "prefix->" + cls})
        return cls
    defects.append({"defect": "unclassifiable-row", "store": store,
                    "id": row.get("id"), "raw": str(raw)})
    return "UNCLASSIFIABLE"


def _account_read_jsonl(path: Path, store: str, defects: list) -> list[dict]:
    # One physical reader for every obligation surface.  The account keeps its
    # historical law that an expected-but-missing store is a named wound, while
    # the generic ledger reader treats absence as an honestly empty not-yet-minted
    # store.  Parse diagnostics themselves are shared verbatim.
    from laplace.pipeline.ledger import read_jsonl_diagnosed
    rows, diagnostics = read_jsonl_diagnosed(path, store=store, required=True)
    for diagnostic in diagnostics:
        d = dict(diagnostic)
        d["raw"] = str(d.pop("error", d.get("raw", "")))[:120]
        defects.append(d)
    return rows


def _account_open_ledger(rows: list[dict], cls: str, store: str, defects: list,
                         *, as_of: str | None = None, diagnose: bool = True,
                         path: Path | str | None = None) -> dict:
    """The ACC-002 pinned open() over one jsonl store, single pass in file order.

    Serves THREE partitions beside each other (RUL-20260823 defer-pin serving clauses):
    open / deferred / closed - deferred is a NAMED partition that never folds into
    closed and never drops from the serving (deferral is scheduling, not discharge),
    and every deferred row serves its trigger beside it (a trigger-missing defer is a
    defect row, never silent).
    """
    import re
    status: dict[str, str] = {}
    latest: dict[str, dict] = {}
    consumed: dict[str, str] = {}
    consumed_class: dict[str, str] = {}
    defer_row: dict[str, dict] = {}
    lapsed_defer: dict[str, dict] = {}
    reopened_by: dict[str, str] = {}
    amend_closures: list[tuple[str, str]] = []
    # A refused close is a live residual until a LATER evidence-bearing close names
    # the same target. Keep the bad row in immutable history, but do not report its
    # defect forever after an append-only correction has actually cured it.
    pending_evidenceless: list[dict[str, Any]] = []
    from laplace.engine import engine_ledger
    # ``diagnose`` is STORE-WIDE, not per class: the sweep hashes and re-scans every row in the
    # file, so the work is identical for all 17 canonical classes and 16 copies were discarded
    # into a throwaway list (internals lane seq 1, diagnostics-recomputed-seventeen-times). One
    # owner runs it - the work_order fold - and every other class passes diagnose=False.
    if diagnose:
        for diagnostic in engine_ledger.obligation_semantic_diagnostics(
                rows, store=store, path=path):
            d = dict(diagnostic)
            d["raw"] = str(d.pop("error", d.get("raw", "")))[:120]
            defects.append(d)
    # Resolution rows follow their targets in the append-only stores, but the account's
    # semantics must not depend on that incidental order. Precompute the owned ids so the
    # evidence gate can tell a work-order close from a finding adjudication anywhere in
    # the mixed ledger without adding a second classifier's defects to the output.
    own_ids = {str(r.get("id")) for r in rows
               if r.get("id") and _account_norm_record(r, store, []) == cls}

    def _evidence_refs(row: dict) -> list[str]:
        return engine_ledger.evidence_refs(row)

    from datetime import date, datetime, timezone
    try:
        account_date = date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()
    except ValueError as exc:
        raise ValueError(f"account as_of must be YYYY-MM-DD, got {as_of!r}") from exc

    def _past_defer(row: dict) -> bool:
        state, parsed = engine_ledger.defer_date_state(row)
        return state == engine_ledger.DEFER_DATE_VALID and parsed < account_date

    for r in rows:
        c = _account_norm_record(r, store, defects)
        rid = r.get("id")
        if c == cls and rid:
            latest[rid] = r
            if "status" in r:
                status[rid] = str(r["status"])
        elif c == "resolution":
            disposition = engine_ledger.resolution_disposition(r)
            if disposition == engine_ledger.RESOLUTION_UNKNOWN:
                continue
            reopens = disposition == engine_ledger.RESOLUTION_REOPEN
            links = list(engine_ledger.resolution_targets(r))
            if (store == "work_orders" and any(v in own_ids for v in links)
                    and not _evidence_refs(r)):
                pending_evidenceless.append({
                    "defect": "work-order-resolution-without-evidence",
                    "store": store,
                    "id": str(r.get("id", "?")),
                    "remaining": {v for v in links if v in own_ids},
                    "attempted_disposition": "reopen" if reopens else "close",
                    "raw": "resolution names a work order but carries no evidence "
                           "refs; it changes no state",
                })
                continue
            for v in links:
                if reopens:
                    reopened_by[v] = str(r.get("id", "?"))
                    consumed.pop(v, None)  # dispositions are last-wins in file order
                    consumed_class.pop(v, None)
                else:
                    consumed[v] = str(r.get("id", "?"))
                    consumed_class[v] = "resolution"
                    reopened_by.pop(v, None)
                    lapsed_defer.pop(v, None)
                for refused in pending_evidenceless:
                    refused["remaining"].discard(v)
        elif c == "defer":
            # RUL-20260823-defer-pin-both-directions: a defer is a resolution-class
            # consumption; only an explicit undefer/trigger row or a new own-status
            # event re-opens (amendments flip nothing, either direction).
            v = r.get("target")
            if isinstance(v, str) and v:
                if consumed_class.get(v) == "resolution":
                    defects.append({"defect": "defer-after-resolution", "store": store,
                                    "id": str(r.get("id", "?")),
                                    "raw": f"target {v} is already discharged by "
                                           f"{consumed.get(v)}; a defer cannot reopen it"})
                    continue
                date_state, _defer_date = engine_ledger.defer_date_state(r)
                has_trigger = isinstance(r.get("trigger"), str) and bool(r["trigger"].strip())
                if date_state == engine_ledger.DEFER_DATE_INVALID:
                    # A malformed latest act supersedes an older defer but cannot mint
                    # an immortal condition.  The semantic diagnostic above is the loud
                    # UNKNOWN; state returns to actionable/open until repaired.
                    if consumed_class.get(v) == "defer":
                        consumed.pop(v, None)
                        consumed_class.pop(v, None)
                    defer_row.pop(v, None)
                    lapsed_defer.pop(v, None)
                    continue
                if date_state == engine_ledger.DEFER_DATE_ABSENT and not has_trigger:
                    if consumed_class.get(v) == "defer":
                        consumed.pop(v, None)
                        consumed_class.pop(v, None)
                    defer_row.pop(v, None)
                    lapsed_defer.pop(v, None)
                    defects.append({"defect": "defer-without-trigger", "store": store,
                                    "id": str(r.get("id", "?")),
                                    "raw": f"target {v}: deferral is scheduling and "
                                           "serves its ISO date or trigger"})
                    continue
                if _past_defer(r):
                    # Deferral schedules an OPEN obligation; after its date it becomes
                    # actionable again. Keep the stale scheduling act visible as its own
                    # partition rather than silently treating it as either closed or an
                    # indefinitely valid defer.
                    if consumed_class.get(v) == "defer":
                        consumed.pop(v, None)
                        consumed_class.pop(v, None)
                    defer_row.pop(v, None)
                    lapsed_defer[v] = r
                    reopened_by[v] = str(r.get("id", "?"))
                    continue
                consumed[v] = str(r.get("id", "?"))
                consumed_class[v] = "defer"
                defer_row[v] = r
                lapsed_defer.pop(v, None)
                reopened_by.pop(v, None)
        elif c == "undefer":
            v = r.get("target")
            if isinstance(v, str) and v:
                consumed.pop(v, None)
                consumed_class.pop(v, None)
                lapsed_defer.pop(v, None)
                reopened_by[v] = str(r.get("id", "?"))
        elif c == "amendment":
            # amendments deliberately do NOT touch target status (spec block `amendments`);
            # but a closure travelling inside one is flagged (spec block `amend_closure`).
            t, txt = r.get("target"), str(r.get("text") or r.get("action") or "")
            if t and re.search(r"\b(DISCHARGED|RESOLVED|CURE APPLIED|CLOSED)\b", txt):
                amend_closures.append((str(t), str(r.get("id", "?"))))
    open_ids = sorted(i for i, s in status.items()
                      if s == "open" and i in latest and i not in consumed)
    for t, aid in amend_closures:
        if status.get(t) == "open" and t not in consumed:
            defects.append({"defect": "amend-text-reads-as-closure", "store": store,
                            "id": aid, "raw": f"target {t} still open; closures are RES "
                                              "rows (PIN-1 corollary)"})
    deferred_ids = sorted(i for i, s in status.items()
                          if s == "open" and i in latest
                          and consumed_class.get(i) == "defer")
    lapsed_ids = sorted(i for i, s in status.items()
                        if s == "open" and i in latest and i not in consumed
                        and i in lapsed_defer)
    for i in lapsed_ids:
        row = lapsed_defer[i]
        defects.append({"defect": "lapsed-defer", "store": store,
                        "id": str(row.get("id", "?")), "target": i,
                        "raw": f"defer_until {row.get('defer_until')} is before "
                               f"account as_of {account_date.isoformat()}; target is open"})
    for refused in pending_evidenceless:
        if not refused["remaining"]:
            continue
        defects.append({k: v for k, v in refused.items() if k != "remaining"}
                       | {"targets": sorted(refused["remaining"])})
    def _head(r: dict) -> str:
        return str(r.get("ask") or r.get("what") or r.get("text") or "")[:140]
    return {
        "total": len(latest),
        "open": len(open_ids),
        "open_rows": [{"id": i, "owner": str(latest[i].get("owner", ""))[:48] or None,
                       "direction": latest[i].get("direction"),
                       "cost": latest[i].get("cost_class"),
                       "date": latest[i].get("date") or str(latest[i].get("ts", ""))[:10],
                       "head": _head(latest[i])} for i in open_ids],
        # serving clause 1: deferred beside open, never folded into closed
        "deferred": len(deferred_ids),
        "deferred_rows": [{"id": i, "owner": str(latest[i].get("owner", ""))[:48] or None,
                           "direction": latest[i].get("direction"),
                           "trigger": defer_row[i].get("defer_until") or defer_row[i].get("trigger"),
                           "deferred_by": defer_row[i].get("deferred_by"),
                           "defer_id": str(defer_row[i].get("id", "?")),
                           "head": _head(latest[i])} for i in deferred_ids],
        "lapsed_deferred": len(lapsed_ids),
        "lapsed_deferred_rows": [
            {"id": i, "owner": str(latest[i].get("owner", ""))[:48] or None,
             "direction": latest[i].get("direction"),
             "trigger": lapsed_defer[i].get("defer_until"),
             "deferred_by": lapsed_defer[i].get("deferred_by"),
             "defer_id": str(lapsed_defer[i].get("id", "?")),
             "head": _head(latest[i])} for i in lapsed_ids],
        "held_open_by_resolution": sorted(set(reopened_by) & set(open_ids)),
    }


def ledger_account(rows: list[dict], cls: str, store: str, *,
                   as_of: str | None = None) -> dict[str, Any]:
    """Public pure fold for one append-only obligation ledger.

    Surfaces with rows already in hand use this rather than reconstructing status from
    the mint field. The returned ``defects`` are part of the projection: malformed or
    evidence-less control rows stay visible instead of silently changing state.
    """
    defects: list[dict] = []
    out = _account_open_ledger(rows, cls, store, defects, as_of=as_of)
    out["defects"] = defects
    return out


#: ONE PARSE PER STORE STATE. Profiled on his landing: a single /front/apex render called
#: account() twice, campaign() three times and _account_open_ledger four times, for 20,998
#: json.loads of the same four files — 0.79s of a 1.15s fragment, all of it re-reading rows
#: that had not moved. The key is (mtime_ns, size) per store, so it is exact rather than
#: time-based: touch any store and the next call rebuilds, and a cached answer can never be
#: staler than the file it was read from. This is memoisation of a PURE READ, not a cache of
#: a verdict — nothing here decides anything, it only re-parses.
_READ_MEMO: dict[tuple, Any] = {}
_MEMO_STORES = ("contract/promises.jsonl", "corpus_friction/work_orders.jsonl",
                "corpus_friction/campaign.jsonl", "corpus_friction/open_stack_wants.jsonl",
                "contract/predictions.jsonl")


def _memo_key(root: Path, tag: str) -> tuple:
    parts: list[Any] = [tag, str(root)]
    for rel in _MEMO_STORES:
        try:
            st = (root / rel).stat()
            parts.append((int(st.st_mtime_ns), st.st_size))
        except OSError:
            parts.append(None)
    return tuple(parts)


def _memoised(root: Path, tag: str, build):
    key = _memo_key(root, tag)
    hit = _READ_MEMO.get(key)
    if hit is not None:
        return hit
    out = build()
    _READ_MEMO.clear()          # bounded: one generation at a time, never a growing map
    _READ_MEMO[key] = out
    return out


def account(repo_root: Path | str | None = None) -> dict[str, Any]:
    """The live account: promised-vs-done across the five stores, spec-normalized.

    Memoised on exact store state — see _memoised. A render calling this twice re-parsed
    the same rows twice; the answer is a pure read of files whose mtime and size the key
    carries, so an unmoved store cannot serve a stale account.
    """
    root = Path(repo_root) if repo_root else _repo_root()
    return _memoised(root, "account", lambda: _account_build(root))


def _account_build(root: Path) -> dict[str, Any]:
    defects: list[dict] = []
    out: dict[str, Any] = {"spec": _ACCOUNT_SPEC}

    prom_rows = _account_read_jsonl(root / "contract" / "promises.jsonl", "promises", defects)
    promises_path = root / "contract" / "promises.jsonl"
    out["promises"] = _account_open_ledger(
        prom_rows, "promise", "promises", defects, path=promises_path)

    work_orders_path = root / "corpus_friction" / "work_orders.jsonl"
    wo_rows = _account_read_jsonl(work_orders_path, "work_orders", defects)
    wo = _account_open_ledger(
        wo_rows, "work_order", "work_orders", defects, path=work_orders_path)
    from collections import Counter
    wo["open_by_cost"] = dict(Counter(str(r.get("cost") or "untyped") for r in wo["open_rows"]))
    out["work_orders"] = wo

    # This store is a heterogeneous obligation ledger. The original account folded
    # only work_order rows and silently discarded every sibling class. Serve one
    # partition for every canonical class present; the work-order fold above IS the
    # sole owner of store-wide diagnostics - enforced by diagnose=False below, not
    # merely asserted here (until seq 1 the comment claimed it and the call ran it).
    from laplace.engine import engine_ledger
    obligation_classes = sorted({
        cls for row in wo_rows if (cls := engine_ledger.record_class(row)) is not None
    })
    class_accounts: dict[str, dict[str, Any]] = {"work_order": wo}
    for cls in obligation_classes:
        if cls == "work_order":
            continue
        class_accounts[cls] = _account_open_ledger(
            wo_rows, cls, "work_orders", [], diagnose=False, path=work_orders_path)
    out["obligation_classes"] = class_accounts
    out["findings"] = class_accounts.get("finding", {
        "total": 0, "open": 0, "open_rows": [], "deferred": 0,
        "deferred_rows": [], "lapsed_deferred": 0,
        "lapsed_deferred_rows": [], "held_open_by_resolution": [],
    })
    out["obligations_open"] = sum(part["open"] for part in class_accounts.values())

    import re
    pred_rows = _account_read_jsonl(root / "contract" / "predictions.jsonl",
                                    "predictions", defects)
    # LAST-DISPOSITION-PER-ID (WO-20260823-predictions-reader-last-wins): a prediction's
    # class is its NEWEST verdict-bearing row in file order - its own prediction rows
    # AND prediction_scoring rows targeting it - mirroring the ACC open() discipline.
    # The first form classed every row independently, so a prediction could not retire
    # or be ruled by append without double-listing its id (P24 served REGISTERED beside
    # its banked FAIL and its retirement).
    def _pred_class(r: dict) -> str:
        raw = r.get("verdict")
        if raw is None or str(raw).strip() == "":
            return "UNRULED"
        u = str(raw).strip()
        if u in _VERDICT_ENUM:
            return u
        w = (re.match(r"[A-Za-z\-]+", u) or re.match(r".{0}", u)).group(0).upper()
        cls = w if w in _VERDICT_ENUM else "UNCLASSIFIED"
        defects.append({"defect": "non-enum-verdict", "store": "predictions",
                        "id": r.get("id"), "raw": str(raw)[:160],
                        "resolved_via": "first-word->" + cls})
        return cls
    latest_cls: dict[str, str] = {}
    for r in pred_rows:
        c = _account_norm_record(r, "predictions", defects)
        if c == "prediction" and r.get("id"):
            latest_cls[str(r["id"])] = _pred_class(r)
        elif c == "prediction_scoring" and r.get("target"):
            if str(r.get("verdict") or "").strip():
                latest_cls[str(r["target"])] = _pred_class(r)
    by_class: dict[str, list[str]] = {}
    for pid, cls in latest_cls.items():
        by_class.setdefault(cls, []).append(pid)
    out["predictions"] = {
        "by_class": {k: len(v) for k, v in sorted(by_class.items())},
        "open_class_ids": sorted(x for k in ("OPEN", "REGISTERED", "UNRULED")
                                 for x in by_class.get(k, [])),
    }

    stack: dict[str, str] = {}
    try:
        for m in re.finditer(r"^\|\s*([WF]\d+)\s*\|(.+)$",
                             (root / "OPEN_STACK.md").read_text(encoding="utf-8"), re.M):
            stack[m.group(1)] = m.group(2).split("|")[0].strip()[:120]
    except OSError as exc:
        defects.append({"defect": "store-unreadable", "store": "open_stack", "raw": str(exc)})
    want_rows = _account_read_jsonl(root / "corpus_friction" / "open_stack_wants.jsonl",
                                    "open_stack_wants", defects)
    want_status = {str(r.get("id")): str(r.get("status") or "untyped")
                   for r in want_rows if r.get("id")}
    fork_rows = _account_read_jsonl(root / "corpus_friction" / "open_stack_forks.jsonl",
                                    "open_stack_forks", defects)
    fork_status: dict[str, str] = {str(r.get("id")): str(r.get("status") or "untyped")
                                   for r in fork_rows if r.get("id")}
    fork_live = sorted(i for i, s in fork_status.items() if s in _FORK_LIVE)
    for fid, s in sorted(fork_status.items()):
        if s not in _FORK_LIVE and s not in _FORK_CLOSED:
            defects.append({"defect": "fork-status-untyped", "store": "open_stack_forks",
                            "id": fid, "raw": f"status {s!r} outside the ruled vocabulary"})
    render_forks = sorted(k for k in stack if k.startswith("F"))
    if set(fork_status) != set(render_forks):
        defects.append({"defect": "forks-store-render-divergence", "store": "open_stack",
                        "raw": f"store {len(fork_status)} ids vs render {len(render_forks)}; "
                               f"store-only {sorted(set(fork_status) - set(render_forks))[:6]}, "
                               f"render-only {sorted(set(render_forks) - set(fork_status))[:6]}"})
    render_wants = sorted(k for k in stack if k.startswith("W"))
    if want_status:
        # minted 2026-08-23 (FIND-SE-003 re-scope): the store is truth, the table its render.
        if set(want_status) != set(render_wants):
            defects.append({"defect": "wants-store-render-divergence", "store": "open_stack",
                            "raw": f"store {sorted(want_status)} vs render {render_wants}"})
    else:
        defects.append({"defect": "wants-store-missing", "store": "open_stack",
                        "raw": "wants live in markdown alone (render with no row store); "
                               "unsampleable until minted -- FIND-SE-003 re-scope"})
    out["open_stack"] = {
        "wants_store": {"total": len(want_status),
                        "live": sorted(i for i, s in want_status.items() if s == "open"),
                        "by_status": dict(Counter(want_status.values()))},
        "wants_render": render_wants,
        "forks_store": {"total": len(fork_status), "live": fork_live,
                        "by_status": dict(Counter(fork_status.values()))},
        "forks_render": render_forks,
        "heads": stack,
    }

    try:
        tp = json.loads((root / "holdout" / "THREAD_PROBES.json").read_text(encoding="utf-8"))
        last = tp.get("last_scored") or {}
        out["thread_probes"] = {
            "probes": len(tp.get("probes", [])), "last_scored_at": last.get("at"),
            "hit": last.get("hit"), "scored": last.get("scored"),
            "reds": sorted(k for k, v in (last.get("by_id") or {}).items() if v == "MISS"),
        }
    except (OSError, json.JSONDecodeError) as exc:
        defects.append({"defect": "store-unreadable", "store": "thread_probes", "raw": str(exc)})

    out["defects"] = defects
    out["store_map"] = STORE_MAP   # class -> store + live example (the wrong-store-first cure)
    return out


#: seat aliases for the account projection: the name a seat is ADDRESSED by is not the
#: only name its rows wear. The Superego is written up as "the judge" across the ledgers
#: (its own charter's word), so the two terms are one seat here. Every other seat is its
#: own single term until a row says otherwise.
_SEAT_TERMS = {"superego": ("superego", "judge")}

#: the fields a seat's name can ride on: the four the ruling named (by/owner/source/text)
#: plus the two other spellings of "text" the account's own ``_head`` already canonicalizes.
_SEAT_PROBE_FIELDS = ("by", "owner", "source", "text", "ask", "what")


def account_seat(seat: str, repo_root: Path | str | None = None, *,
                 acct: dict[str, Any] | None = None) -> dict[str, Any]:
    """The seat-scoped projection of ``account()``: one call in place of five hand greps.

    WO-20260823-judge-account-verb: the successor judge recovered its own ledger this
    wake by grepping its name five times. The account already knows WHICH rows are live;
    what it could not say is WHOSE they are. This filters the account's own partitions -
    open / deferred / held - by a case-insensitive WORD match on the seat's terms, so
    ``ego`` never matches ``superego`` and a row saying "the judge held it" reaches the
    Superego seat.

    ``account()`` gains nothing for this: the live partitions come from the account
    (one semantic layer, the SB-6 bar) and the match fields come from the full rows,
    looked up by id from the same stores exactly as the conscience shard already does.
    Read defects are the account's to serve and are re-derived, not re-reported here.
    ``acct`` lets a caller with an account already in hand skip the second parse.
    """
    import re
    root = Path(repo_root) if repo_root else _repo_root()
    a = acct if acct is not None else account(root)
    name = str(seat).strip()
    if not name:
        # the verify wave's defect 3: a blank term compiles to re.compile("") and
        # matches EVERY row - an empty seat is a caller error, never a wildcard.
        raise ValueError("account_seat requires a non-empty seat name")
    terms = _SEAT_TERMS.get(name.lower(), (name.lower(),))
    pat = re.compile("|".join(r"\b" + re.escape(t) + r"\b" for t in terms if t), re.I)
    rows: list[dict[str, Any]] = []
    counts = {"open": 0, "deferred": 0, "held": 0}
    for store, path, cls in (
            ("promises", root / "contract" / "promises.jsonl", "promise"),
            ("work_orders", root / "corpus_friction" / "work_orders.jsonl", "work_order")):
        led = a.get(store) or {}
        held = set(led.get("held_open_by_resolution") or [])
        full: dict[str, dict] = {}
        for r in _account_read_jsonl(path, store, []):
            if r.get("id") and _account_norm_record(r, store, []) == cls:
                full[str(r["id"])] = r          # last-wins, exactly as the ledger's own map
        for partition in ("open", "deferred"):
            for served in led.get(partition + "_rows") or []:
                rid = str(served.get("id"))
                row = full.get(rid, {})
                probe = " ".join(str(row.get(k) or "") for k in _SEAT_PROBE_FIELDS)
                hits = sorted({m.group(0).lower() for m in pat.finditer(probe)})
                if not hits:
                    continue
                part = "held" if (partition == "open" and rid in held) else partition
                # TYPED vs GUESSED, kept apart. The design review said "kill the regex,
                # attribution is owed_by/owner as a typed field or it is not attribution"
                # — correct about the regex and wrong about the cure, and only measuring
                # shows why: 41 rows of 1,260 carry a typed owner or owed_by AT ALL
                # (ego 15, codex 10, interface 6, superego 4). Typed-only would empty the
                # board and be differently incomplete rather than more true.
                # So both, and never merged: a typed field is a CLAIM someone banked; a
                # prose match is a GUESS this function made. The guess is why
                # WO-20260820-embeddings-return-a-matrix — an ndarray dequant order —
                # attributes to the interface seat on the substring "Typed-interface
                # change", and why FIND-...-unreached-can-name-a-reached-seat, which
                # carries the literal field owed_by: interface-seat, was NOT counted:
                # owed_by is not in _SEAT_PROBE_FIELDS. Both are now visible as what
                # they are, and a surface may render the guess only if it says so.
                typed_hit = any(pat.search(str(row.get(f) or ""))
                                for f in ("owner", "owed_by"))
                counts[part] += 1
                counts["typed"] = counts.get("typed", 0) + (1 if typed_hit else 0)
                rows.append({
                    "attribution": "typed" if typed_hit else "prose-match",
                    "store": store, "partition": part, "id": rid,
                    # UNTRUNCATED (the verify wave's defect 2: the conscience scans this
                    # field for custody markers, and a marker past a display cap vanished):
                    "by": str(row.get("by") or "") or None,
                    "owner": served.get("owner"),
                    "date": served.get("date") or str(row.get("ts", ""))[:10],
                    "trigger": served.get("trigger"),
                    "matched": hits,
                    # the whole text, not a head: the verb exists to REPLACE the greps,
                    # and a truncated body sends the judge straight back to one.
                    "text": str(row.get("ask") or row.get("what") or row.get("text") or ""),
                })
    rows.sort(key=lambda r: (r["store"], r["partition"], r["id"]))
    counts["total"] = len(rows)
    counts.setdefault("typed", 0)
    counts["prose_match"] = counts["total"] - counts["typed"]
    # THE ID SET IS PART OF THE ANSWER, not something a caller re-derives. A surface that
    # renders this count and then hand-builds a link to a filter grammar produces a door
    # that opens on a different set — measured: four seat tiles linking to
    # #explore/work_orders/open:<seat> all landed on "0 of 1265".
    counts["open_ids"] = sorted(r["id"] for r in rows if r["partition"] == "open")
    # AND PER STORE, because a surface renders ONE door at a time. This function spans
    # promises AND work_orders; a tile that shows the combined count and links to the
    # work-orders explorer disagrees with its own door by exactly the promises rows —
    # measured 9 against 8, 14 against 13. The caller now takes the count for the store
    # it is about to open, so the number it renders is the number that door will show.
    counts["by_store"] = {}
    for store in ("promises", "work_orders"):
        ids = sorted(r["id"] for r in rows
                     if r["partition"] == "open" and r["store"] == store)
        counts["by_store"][store] = {
            "open": len(ids), "ids": ids,
            "typed": sum(1 for r in rows if r["partition"] == "open"
                         and r["store"] == store and r["attribution"] == "typed"),
        }
    return {"seat": name, "terms": list(terms), "counts": counts, "rows": rows,
            "law": "the account rules which rows are live; this rules whose they are - "
                   "word-matched on " + "/".join(_SEAT_PROBE_FIELDS)}


def _one_line(text: Any, cap: int = 200) -> str:
    """One line, capped - the served head of a body that stays in its store."""
    t = " ".join(str(text or "").split())
    return t if len(t) <= cap else t[: cap - 3] + "..."


def _edge_blob(edges: Any) -> str:
    """The TYPED lineage half flattened for matching.

    ``journal.bank_row`` banks ``edges=[{"rel", "target"}]`` as a first-class field
    (the closed REL vocabulary, walked by :mod:`laplace.core.records.lineage`).  The stage-progress
    blob was built from prose fields alone, so a row whose only link to the stage was a
    typed edge - the strongest, most machine-checkable link there is - lost to a row that
    merely mentioned the id in a sentence.  The typed edge must never lose to the prose.
    """
    if not isinstance(edges, list):
        return ""
    out: list[str] = []
    for e in edges:
        if isinstance(e, dict):
            out.append(f"{e.get('rel', '')} {e.get('target', '')}")
        else:
            out.append(str(e))
    return " ".join(out)


def _is_verdict_class(record: Any) -> bool:
    """Verdict-CLASS, not the literal word: anything that ADJUDICATES.

    ``verdict``/``gate-verdict``/``packet-verdict`` and ``ruling`` alike - a RUL-* row IS
    a decision and moves a stage exactly as a verdict does, so the narrow
    ``"verdict" in record`` predicate silently dropped the whole ruling class from the
    next act's progress.
    """
    rec = str(record or "").lower()
    return "verdict" in rec or "ruling" in rec


def _stage_progress(root: Path, stage_id: str) -> dict[str, Any] | None:
    """The vocabulary between OPEN and DONE for the next act, from typed rows alone.

    A campaign stage is binary at the gate (WO-20260825-next-act-has-no-progress-vocabulary:
    ATLAS-S1 read OPEN for a day while a full clause adjudication and an empirically-measured
    amendment sat banked in work_orders.jsonl, invisible to every wake).  This projects the
    NEWEST verdict-class row referencing the stage plus the newest amendment targeting that
    verdict.

    DESCENT-BY-NEED, hard: refs and <=200-char one-liners ONLY, never bodies.  The reader
    greps the served id for the rest.  ``None`` when nothing references the stage - loud
    absence is the honest answer; invention is not.

    Matching is on the EXACT stage-id token (``ATLAS-S1`` never matches ``ATLAS-S10``, and a
    bare ``s1`` never matches at all) across ``id``/``target``/``what``/``text``/``refs``
    AND the typed ``edges`` field.

    A row that does not parse is a LOUD defect, never a silent skip: the unparseable line
    may BE the ruling that moves the stage, and a store that half-parsed must never read
    like a clean one.
    """
    import re

    store = root / "corpus_friction" / "work_orders.jsonl"
    if not stage_id or not store.exists():
        return None
    tok = re.compile(r"(?<![0-9A-Za-z_])" + re.escape(stage_id) + r"(?![0-9A-Za-z_])",
                     re.IGNORECASE)
    referring: list[tuple[tuple[str, int], dict]] = []
    rows: list[tuple[tuple[str, int], dict]] = []
    unparseable: list[int] = []
    for idx, line in enumerate(store.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            # THE SKIPPED ROW MAY BE THE RULING (interface-seat cross-audit): a bare
            # `continue` made a malformed store indistinguishable from a store with
            # nothing in it, and the omission travelled as absence.  1-indexed line
            # numbers ride out so the reader can descend straight to the damage.
            unparseable.append(idx + 1)
            continue
        key = (str(r.get("ts", "")), idx)  # ts first, mint order as the tiebreak
        rows.append((key, r))
        blob = " ".join([str(r.get("id", "")), str(r.get("target", "")),
                         str(r.get("what", "")), str(r.get("text", "")),
                         " ".join(str(x) for x in (r.get("refs") or [])),
                         _edge_blob(r.get("edges"))])
        if tok.search(blob):
            referring.append((key, r))
    defects = [{"code": "work-orders-unparseable-rows",
                "store": "corpus_friction/work_orders.jsonl",
                "count": len(unparseable), "lines": unparseable[:12],
                "why": "an unparseable row may BE the ruling that moves this stage - "
                       "this progress is computed over an INCOMPLETE store"}] if unparseable else []
    if not referring and not defects:
        return None

    def _newest(cands: list[tuple[tuple[str, int], dict]]) -> dict | None:
        return max(cands, key=lambda kr: kr[0])[1] if cands else None

    verdict = _newest([kr for kr in referring if _is_verdict_class(kr[1].get("record"))])
    amendment = None
    if verdict and verdict.get("id"):
        vid = str(verdict["id"])
        # "targeting it" is the VERDICT, not the stage: an amendment carries the verdict id
        # in ``target`` (AMEND-20260825-clause3-measured-and-gated -> the clause-7 verdict)
        # and need never name the stage at all.
        amendment = _newest([
            kr for kr in rows
            if kr[1].get("record") == "amendment"
            and (str(kr[1].get("target", "")) == vid
                 or vid in " ".join(str(x) for x in (kr[1].get("refs") or []))
                 or vid in str(kr[1].get("what", "")))
        ])
    if amendment is None:  # no verdict, or none aimed at it: fall back to the stage's own
        amendment = _newest([kr for kr in referring
                             if kr[1].get("record") == "amendment"])

    ids: list[str] = []
    for _key, r in referring:
        rid = str(r.get("id", ""))
        if rid and rid not in ids:
            ids.append(rid)
    for extra in (verdict, amendment):
        rid = str((extra or {}).get("id", ""))
        if rid and rid not in ids:
            ids.append(rid)
    return {
        "stage": stage_id,
        "latest_verdict": None if not verdict else {
            "id": verdict.get("id"),
            "record": verdict.get("record"),
            "verdict": verdict.get("verdict") or verdict.get("status")
                       or verdict.get("ruling"),
            "one_line": _one_line(verdict.get("what") or verdict.get("text")),
        },
        "latest_amendment": None if not amendment else {
            "id": amendment.get("id"),
            "one_line": _one_line(amendment.get("what") or amendment.get("text")),
        },
        "refs": ids[-12:],
        "refs_total": len(ids),
        "defects": defects,
        "descend": "grep -n '<id>' corpus_friction/work_orders.jsonl "
                   "(refs and heads only here - the bodies stay in the store)",
    }


#: the campaign source's staleness budget (sources.py SOURCES["campaign"], 24h). A gate
#: whose verdict is older than this has genuinely not been measured; a gate re-measured
#: inside it and found IDENTICAL is unchanged-and-correct, which is not the same thing.
_REVERIFY_AFTER = 24 * 3600


def _verdict_age_s(v: dict[str, Any] | None, now: float | None = None) -> float | None:
    """Age in seconds of a banked verdict's own ``ts``; ``None`` when unstampable."""
    from datetime import datetime, timezone
    ts = str((v or {}).get("ts") or "")
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    ref = now if now is not None else datetime.now(timezone.utc).timestamp()
    return max(0.0, ref - d.timestamp())


def _verdict_freshness(v: dict[str, Any], budget: int = _REVERIFY_AFTER) -> dict[str, Any]:
    """STALE is not the same as UNCHANGED-AND-CORRECT (the freshness false-red).

    The campaign source's RED chip is computed from ``st_mtime`` against a 24h budget, and
    the delta-bank cure (WO-20260825-gate-verdicts-bank-only-on-change) deliberately stops
    touching the store when nothing moves - so a campaign whose gates are all green and
    stable went RED for being *correct*.  Freshness is therefore a property of the last
    MEASUREMENT, not of the file's mtime:

      MEASURED            the verdict recorded a change - the world moved and was banked
      UNCHANGED-VERIFIED  re-run inside the budget, byte-identical, re-stamped: not stale
      AGING               nobody has run this gate inside the budget - real staleness
      UNSTAMPED           no parseable ts on the row - loud, never assumed fresh
    """
    age = _verdict_age_s(v)
    if age is None:
        return {"state": "UNSTAMPED", "age_s": None,
                "note": "verdict carries no parseable ts - never read as fresh"}
    if age > budget:
        return {"state": "AGING", "age_s": int(age),
                "note": f"no measurement inside the {budget}s budget - re-run --campaign"}
    return {"state": "UNCHANGED-VERIFIED" if v.get("reverified") else "MEASURED",
            "age_s": int(age),
            "note": ("re-measured and found identical - unchanged and correct, NOT stale"
                     if v.get("reverified") else "this verdict recorded a change")}


def campaign(repo_root: Path | str | None = None, *, run_gates: bool = False,
             gate_timeout: int = 30, reverify_after: int = _REVERIFY_AFTER) -> dict[str, Any]:
    """Campaign state from TYPED ROWS ALONE (SB-5): no ARMING/HANDOFF markdown read.

    Stage status is COMPUTED, never author-set: DONE iff the stage's gate command
    exits 0; OPEN otherwise; BLOCKED-ON-AUTHOR iff the row says so (jurisdiction,
    not deferral). ``run_gates=True`` (the standalone ``--campaign`` verb) executes
    every gate now and BANKS a gate-verdict row per stage through the journal seam;
    ``False`` (the wake's live key) serves rows + the latest banked verdicts with
    their age -- the 2.0s wake budget never pays for subprocesses.
    """
    root = Path(repo_root) if repo_root else _repo_root()
    if not run_gates:
        # ONLY the gate-less read is memoised. run_gates=True FIRES SUBPROCESSES and BANKS
        # gate-verdict rows — it is an act, and an act must never be served from a cache.
        return _memoised(root, f"campaign:{reverify_after}",
                         lambda: _campaign_build(root, False, gate_timeout, reverify_after))
    return _campaign_build(root, True, gate_timeout, reverify_after)


def _gate_residuals(verdict: Any) -> Any:
    """What the next act's GATE ITSELF named as missing, from the banked verdict row.

    The gate already prints its residuals and ``_campaign_build`` already banks and reads that
    row - until now only its exit code survived, so every wake said ``OPEN`` and no wake said
    WHY.  ``output_head`` is a 200-char head by construction, so a truncated head cannot parse:
    that is reported as the head itself, loudly, never as an empty residual list (an absent
    residual and a residual nobody carried up must never read the same)."""
    if not isinstance(verdict, dict):
        return None
    head = verdict.get("output_head")
    if not isinstance(head, str) or not head.strip():
        return None
    try:
        parsed = json.loads(head)
    except json.JSONDecodeError:
        return {"gate_output_head": head[:200], "note": "gate output head is truncated at 200 "
                                                        "chars and does not parse as JSON"}
    residuals = parsed.get("residuals") if isinstance(parsed, dict) else None
    if not isinstance(residuals, list):
        return {"gate_output_head": head[:200], "note": "the gate printed no 'residuals' list"}
    return [str(x)[:200] for x in residuals[:6]]


def _last_wave_returned(root: Path) -> Any:
    """Which wave last returned, from ``contract/dispatches.jsonl`` through the reader that owns
    it (``laplace.pipeline.workflow.recent_workflows``, a bounded 64 KB tail read - NOT a second
    reader over the same store).  The wake serves the head only; the run's exact returns are a
    descent by the command the reader itself computes."""
    try:
        from laplace.pipeline.workflow import recent_workflows
        recent = recent_workflows(root, limit=8)
    except Exception as exc:  # noqa: BLE001 - a wake that cannot read the ledger still wakes
        return {"absent": f"workflow ledger read failed: {type(exc).__name__}: {exc}"}
    runs = recent.get("workflows") or []
    if not runs:
        return {"absent": recent.get("reason") or recent.get("status")
                or "no workflow row in the bounded ledger tail"}
    # LAST TO RETURN, not last to be banked. The reader orders by byte offset - which is banking
    # order, and a batch of append-only corrections banks in whatever order the producer walked
    # the waves. The run's own time is in its id (WORKFLOW-<run journal's last write, UTC>-<hex>),
    # so the stamp decides; a row whose id carries no stamp sorts last, never silently first.
    run = max(runs, key=lambda r: (str(r.get("run_id") or "")[9:26], r.get("recorded_at") or ""))
    out = {"wave": run.get("stage"), "run_id": run.get("run_id"),
           "status": run.get("status"), "accepted": run.get("recorded_accepted"),
           "at": run.get("recorded_at"), "descend": run.get("status_command"),
           "chosen_from": f"{len(runs)} workflow rows in the bounded ledger tail, "
                          f"newest by the run stamp in its id"}
    ref = run.get("result_ref")
    if isinstance(ref, dict):
        out["returns"] = ref.get("path")
    return out


def _campaign_build(root: Path, run_gates: bool, gate_timeout: int,
                    reverify_after: int) -> dict[str, Any]:
    import subprocess
    store = root / "corpus_friction" / "campaign.jsonl"
    stages: dict[str, dict] = {}
    verdicts: dict[str, dict] = {}
    untyped_stage_ids: set[str] = set()
    if store.exists():
        for line in store.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("record") == "stage" and r.get("id"):
                stages[r["id"]] = r
            elif r.get("record") == "gate-verdict" and r.get("stage"):
                verdicts[r["stage"]] = r
            elif (r.get("id") and r.get("stage") is not None
                  and str(r["id"]).startswith(("CAMP-", "ATLAS-S", "ATLAS-ABSORB-"))):
                # A stage-shaped row without its discriminator is not a stage.  This exact
                # defect hid the whole ATLAS-S0..S5 successor campaign from wake while the
                # superseded CAMP-* campaign remained visible.  Keep it loud until an
                # append-only corrected row with the same id arrives.
                untyped_stage_ids.add(str(r["id"]))
    untyped_stage_ids.difference_update(stages)
    if not stages:
        return {"absent": "no typed campaign rows minted",
                "schema_residuals": [
                    {"code": "stage-row-missing-record", "id": sid}
                    for sid in sorted(untyped_stage_ids)
                ]}

    out_stages = []
    old_campaign_absorbed = "ATLAS-ABSORB-OLD-CAMPAIGN" in stages
    for sid in sorted(stages):
        s = stages[sid]
        freshness: dict[str, Any] | None = None
        if old_campaign_absorbed and sid.startswith("CAMP-"):
            status = "ABSORBED"
            ground = "superseded by ATLAS-ABSORB-OLD-CAMPAIGN; retained for its S0 disposition"
        elif s.get("blocked_on") == "author":
            status, ground = "BLOCKED-ON-AUTHOR", s.get("jurisdiction", "author")
        elif run_gates and s.get("gate"):
            # ONE SEAM FOR EVERY MEASURED OUTCOME. A timeout used to set the CURRENT call
            # to OPEN and bank nothing at all - so the next read-only wake reread the PRIOR
            # banked verdict, which could be DONE, and served a green stage whose latest
            # execution had actually timed out (the stale-green). A timeout IS a terminal
            # measurement: it gets its own status and output signature and rides the SAME
            # compare-and-bank path as any exit code.
            try:
                r = subprocess.run(s["gate"]["cmd"], shell=True, capture_output=True,
                                   text=True, timeout=gate_timeout, cwd=root)
                exit_code: int | None = r.returncode
                status = "DONE" if exit_code == 0 else "OPEN"
                head = (r.stdout + r.stderr)[:200]
                ground = f"gate exit {exit_code} (run now)"
            except subprocess.TimeoutExpired:
                exit_code = None                      # no exit: the gate never finished
                status = "TIMEOUT"
                head = f"TIMEOUT: gate exceeded {gate_timeout}s with no exit"
                ground = f"gate timeout {gate_timeout}s (run now)"
            # DELTA-BANKED (WO-20260825-gate-verdicts-bank-only-on-change): the store
            # had 759 gate-verdict rows, 28 of them byte-identical blanks for ATLAS-S1
            # alone - a re-run minted a row whether or not the world had moved, so the
            # ledger measured how often --campaign fired, never what changed. A verdict
            # banks iff it DIFFERS from the last banked verdict for its stage (exit or
            # output_head); the first-ever verdict for a stage always banks. Row shape is
            # byte-compatible - readers (the last-wins collector above) are untouched.
            prev = verdicts.get(sid)
            changed = (prev is None or prev.get("exit") != exit_code
                       or prev.get("output_head", "") != head)
            # ...and the heartbeat that keeps UNCHANGED from decaying into STALE: once the
            # last measurement is older than the staleness budget, an identical re-run
            # re-stamps it as ``reverified`` (at most one row per stage per budget window,
            # so the churn the delta-bank cured never returns). Without this, "nobody has
            # measured this in a day" and "measured a minute ago, nothing moved" are the
            # same observation to every mtime-driven freshness chip - the false RED.
            age = _verdict_age_s(prev)
            heartbeat = (not changed) and (age is None or age >= reverify_after)
            if changed or heartbeat:
                from laplace.core.records import journal
                row = {"record": "gate-verdict", "stage": sid,
                       "exit": exit_code, "status": status,
                       # no ts: bank_row stamps the seam's own clock (one-stamp law)
                       "output_head": head}
                if heartbeat:
                    row["reverified"] = True   # unchanged AND correct, re-measured now
                journal.bank_row("corpus_friction/campaign.jsonl", row, root=root)
                verdicts[sid] = row  # last-wins, in-process: one bank per stage per run
                if heartbeat:
                    ground += ("; unchanged - re-verified past the "
                               f"{reverify_after}s budget, not stale")
            else:
                ground += f"; unchanged since {prev.get('ts')} - not re-banked"
        elif s.get("gate"):
            v = verdicts.get(sid)
            if v:
                status = v.get("status", "OPEN")
                freshness = _verdict_freshness(v, reverify_after)
                ground = (f"banked verdict {v.get('ts')} [{freshness['state']}] - "
                          f"{freshness['note']} (re-run --campaign to refresh)")
            else:
                status, ground = "UNRUN", "no banked gate verdict yet - loud, never assumed"
        else:
            status, ground = "OPEN", "no gate declared"
        out_stages.append({"id": sid, "stage": s.get("stage"), "title": s.get("title"),
                           "status": status, "ground": ground,
                           "depends_on": s.get("depends_on", []),
                           "gate_expect": (s.get("gate") or {}).get("expect"),
                           **({"freshness": freshness} if freshness else {}),
                           "source": f"[{s.get('source', '?')}]"})
    # THE RIDING ORDINAL IS A RENDER, never a key (WO-20260823-campaign-r-numbers-are-renders:
    # two rows minted with "R3" embedded in their ids; ids are the keys and stay verbatim, so
    # the served ordinal is DERIVED here from mint order at query time - the number a reader
    # should trust is this one, not the digits inside the id).
    riding = sorted((s["id"] for s in stages.values() if s.get("stage") == "riding"),
                    key=lambda sid: (stages[sid].get("minted") or "", sid))
    ordinal = {sid: f"R{n}" for n, sid in enumerate(riding, start=1)}
    for x in out_stages:
        if x["id"] in ordinal:
            x["riding_ordinal"] = ordinal[x["id"]]
    done = {x["id"] for x in out_stages if x["status"] == "DONE"}
    next_act = next((x["id"] for x in out_stages
                     if isinstance(x["stage"], int)
                     and x["status"] in ("OPEN", "UNRUN", "TIMEOUT")
                     and all(d in done for d in x["depends_on"])), None)
    head = next((x for x in out_stages if x["id"] == next_act), None) if next_act else None
    return {"stages": out_stages, "next_act": next_act,
            # WHAT the next act builds and WHAT ITS GATE SAYS IS MISSING, carried up from rows
            # this build already read: the stage row's own title (dropped at the {id: status}
            # reduction the payload does) and the newest banked gate-verdict row for that stage
            # (read at the top of this function; only its exit code was used before).
            "next_act_title": (head or {}).get("title"),
            "next_act_gate_residuals": _gate_residuals(verdicts.get(next_act)) if next_act else None,
            # the next act's progress, and ONLY the next act's: OPEN/DONE is the gate's
            # binary, this is what has actually happened inside the stage since it opened.
            "progress": _stage_progress(root, next_act) if next_act else None,
            "schema_residuals": [
                {"code": "stage-row-missing-record", "id": sid}
                for sid in sorted(untyped_stage_ids)
            ],
            "status_rule": "COMPUTED: DONE iff gate exit 0; TIMEOUT is a measured terminal "
                           "outcome that BANKS like any verdict (never a silent OPEN that "
                           "leaves a prior DONE standing); ABSORBED is explicit campaign "
                           "supersession; BLOCKED-ON-AUTHOR is jurisdiction; UNRUN is loud; "
                           "never an author-set field"}


# WHERE-DOES-THIS-CLASS-BANK (WO-20260823-store-map-class-router; the judge's recurrence:
# three wrong-store-first greps in two days, PV rows hunted in corpus_friction). One served
# map: record class -> banking store + a live example id, so judges and successors descend
# to the right store FIRST. Every example is real and test-verified against its store
# (tests/test_wake_cli.py) - the map cannot drift silently. A class registered at birth
# (WO-20260823-store-first-birth-program) is a class this map serves for free.
STORE_MAP: list[dict[str, str]] = [
    {"class": "proxy verdict - his words / rulings by proxy", "id_form": "PV-*",
     "store": "proxy_verdicts.jsonl", "example": "PV-20260823-his-one-organ-first"},
    {"class": "promise / covenant / its notes", "id_form": "PRM-*",
     "store": "contract/promises.jsonl", "example": "PRM-20260823-his-commission-running-hot"},
    {"class": "work orders, findings, notes, resolutions, amendments, rulings, verdicts, gaps, intents and control rows",
     "id_form": "WO-* CR-* FIND-* NOTE-* RES-* ADJ-* AMEND-* RUL-* CP-* VERDICT-* GAP-* DEFER-* RETRACT-* LINK-* W-* SYNTH-* XV-* (explicit record wins)",
     "store": "corpus_friction/work_orders.jsonl", "example": "WO-20260823-seat-chaining-cron"},
    {"class": "methods law - task-class rows compiled into every packet", "id_form": "M-*",
     "store": "corpus_friction/methods.jsonl", "example": "M-idle-time-consumes-the-stack"},
    {"class": "campaign stage + gate-verdict", "id_form": "CAMP-* ATLAS-S*",
     "store": "corpus_friction/campaign.jsonl", "example": "ATLAS-S0"},
    {"class": "seat rows - addresses, latest-per-seat", "id_form": "record=seat",
     "store": "contract/seats.jsonl", "example": "eigen-ego-accounting-day-iii"},
    {"class": "in-flight journal - acts, steps, banks", "id_form": "record=act|step|bank|act_end",
     "store": "contract/journal.jsonl", "example": "ambient-bank-"},
    {"class": "predictions", "id_form": "P<n>",
     "store": "contract/predictions.jsonl", "example": "\"id\": \"P1\""},
    {"class": "bequests - authored at close, carried verbatim", "id_form": "record: written/by/text",
     "store": "contract/bequests.jsonl", "example": "archived_to"},
    {"class": "judged verdicts - dispatched-judge stations", "id_form": "station+claim+verdict",
     "store": "contract/judged_verdicts.jsonl", "example": "dispatched-adversarial-judge"},
]


def account_capped(repo_root: Path | str | None = None, *, ids_cap: int = 10) -> dict[str, Any]:
    """The payload-riding projection of ``account()``: counts + capped id lists, no heads.

    Same code path (a projection of the same object), so the wake and the CLI can never
    disagree -- the SB-6 bar.
    """
    a = account(repo_root)
    return {
        "promises_open": a["promises"]["open"],
        "promises_deferred": a["promises"]["deferred"],
        "work_orders_open": a["work_orders"]["open"],
        "work_orders_deferred": a["work_orders"]["deferred"],
        "work_orders_by_cost": a["work_orders"]["open_by_cost"],
        "findings_open": a["findings"]["open"],
        "findings_deferred": a["findings"]["deferred"],
        "obligations_open": a["obligations_open"],
        "obligations_open_by_class": {
            cls: part["open"] for cls, part in a["obligation_classes"].items()
        },
        "predictions_open_class": len(a["predictions"]["open_class_ids"]),
        "open_stack": {"wants_live": len(a["open_stack"]["wants_store"]["live"]),
                       "forks_live": len(a["open_stack"]["forks_store"]["live"]),
                       "render": {"wants": len(a["open_stack"]["wants_render"]),
                                  "forks": len(a["open_stack"]["forks_render"])}},
        "thread_reds": len((a.get("thread_probes") or {}).get("reds", [])),
        "thread_red_ids": list((a.get("thread_probes") or {}).get("reds", []))[:ids_cap],
        "thread_scored_at": (a.get("thread_probes") or {}).get("last_scored_at"),
        "defects": len(a["defects"]),
        "promises_open_ids": [r["id"] for r in a["promises"]["open_rows"][:ids_cap]],
        "work_orders_open_ids": [r["id"] for r in a["work_orders"]["open_rows"][:ids_cap]],
        "findings_open_ids": [r["id"] for r in a["findings"]["open_rows"][:ids_cap]],
        "descend": "scripts/laplace-python scripts/wake.py --account  (the whole account, same code path)",
    }


#: The stranger bench's THREE check verdicts (score_stranger_bench.py's own law:
#: "Three verdict values, never two: PASS / FAIL / AWAITING-JUDGE"), mapped to the
#: names the wake serves them under. A status string outside this map is NOT
#: silently assigned to a neighbour - it lands in ``unrecognised`` by name.
_BENCH_CHECK_STATES = {"PASS": "pass", "FAIL": "fail", "AWAITING-JUDGE": "awaiting_judge"}

#: Probe state precedence, strongest claim last-resort: an unknown never loses to a
#: known. UNRECOGNISED (the code has never seen this status) > red (a check actually
#: FAILed) > awaiting_judge (the judge's half is missing) > not_recorded (no status
#: was ever banked) > green (and ONLY when every one of its checks banked PASS).
_BENCH_PROBE_ORDER = ("unrecognised", "red", "awaiting_judge", "not_recorded", "green")


def bench_states(path: Path | str) -> dict[str, Any]:
    """Count the stranger bench's LAST run BY STATE NAME - never by subtraction.

    SYNTH-20260825-the-unknown-collapses, class 4 (UNJUDGED collapses into FAILED):
    the runner's own ``run`` row banks ``red = len(summary) - greens``, so a probe
    left RED only because a check is AWAITING-JUDGE (the judge's sealed material is
    not this side's to hold) is served to every waking session as *failed*. The wake
    read that number twice on 2026-08-25 and twice concluded validation was lagging
    construction. It is not the wake's place to re-grade the bench - but it IS the
    wake's place to stop rendering an unknown as a known.

    So every state is counted by NAME off the banked ``check`` rows:

      * ``pass`` / ``fail`` / ``awaiting_judge`` - the runner's three verdicts;
      * ``not_recorded`` - a row whose ``status`` is absent or null. ABSENCE, never
        a verdict: it is not passing, not failing, and not awaiting judgement;
      * ``unrecognised`` - {status string: count} for anything else. A status the
        code has never seen is served under its own name and absorbed into nothing.

    No bucket is ever derived as total-minus-the-others: that arithmetic is the same
    collapse one level down, silently posting an unknown row into whichever bucket
    the subtraction happens to balance. ``total`` is the count of rows READ, and the
    named buckets are asserted to sum to it (``sums_to_total``) rather than one of
    them being solved for.

    Staleness is a SEPARATE axis and is not computed here - a stale set of counts is
    still counts, and the caller says both.
    """
    path = Path(path)
    run: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        rows.append(r)
        if r.get("record") == "run":
            run = r
    if run is None:
        return {"absent": "no run row banked"}
    label = run.get("run")

    checks = {"total": 0, "pass": 0, "fail": 0, "awaiting_judge": 0, "not_recorded": 0}
    unrecognised: dict[str, int] = {}
    per_probe: dict[str, dict[str, int]] = {}
    for r in rows:
        if r.get("record") != "check" or r.get("run") != label:
            continue
        raw = r.get("status")
        if raw is None:
            bucket = "not_recorded"
        elif raw in _BENCH_CHECK_STATES:
            bucket = _BENCH_CHECK_STATES[raw]
        else:
            bucket = "unrecognised"
            unrecognised[str(raw)] = unrecognised.get(str(raw), 0) + 1
        checks["total"] += 1
        if bucket != "unrecognised":
            checks[bucket] += 1
        probe = per_probe.setdefault(str(r.get("probe")),
                                     {"pass": 0, "fail": 0, "awaiting_judge": 0,
                                      "not_recorded": 0, "unrecognised": 0})
        probe[bucket] += 1
    checks["unrecognised"] = unrecognised
    named = (checks["pass"] + checks["fail"] + checks["awaiting_judge"]
             + checks["not_recorded"] + sum(unrecognised.values()))
    checks["sums_to_total"] = named == checks["total"]

    states: dict[str, str] = {}
    for probe, c in sorted(per_probe.items()):
        if c["unrecognised"]:
            states[probe] = "unrecognised"
        elif c["fail"]:
            states[probe] = "red"
        elif c["awaiting_judge"]:
            states[probe] = "awaiting_judge"
        elif c["not_recorded"]:
            states[probe] = "not_recorded"
        elif c["pass"]:
            states[probe] = "green"
        else:
            states[probe] = "not_recorded"
    probes = {k: sum(1 for s in states.values() if s == k) for k in _BENCH_PROBE_ORDER}
    probes["total"] = len(states)
    probes["states"] = states

    # A THIRD AXIS, never merged into the counts above: the store also carries
    # `judge-verdict` rows - the judge's own grading of a probe, from a DIFFERENT run.
    # A self-run can never resolve an AWAITING-JUDGE check by construction, so a wake
    # that shows only the self-run's counts still reads as "nothing was ever graded".
    # Served by run label and date so the reader can see it is another run's act.
    judged: dict[str, Any] = {}
    for r in rows:
        if r.get("record") == "judge-verdict":
            judged[str(r.get("probe"))] = {"verdict": r.get("verdict"), "run": r.get("run"),
                                           "ts": r.get("ts")}
    judge_block = ({"probes_graded": len(judged),
                    "runs": sorted({str(v["run"]) for v in judged.values()}),
                    "verdicts": {k: v["verdict"] for k, v in sorted(judged.items())},
                    "note": "the judge's own grading, from the run(s) named - a SEPARATE "
                            "act from the self-run counted above and NOT merged into it; "
                            "a self-run cannot resolve an AWAITING-JUDGE check at all"}
                   if judged else {"probes_graded": 0,
                                   "note": "no judge-verdict row has ever been banked"})

    rollup_fields = (
        "green", "fail", "awaiting_judge", "not_recorded", "unrecognised",
        "unresolved", "total", "sums_to_total",
    )
    banked = {key: run.get(key) for key in rollup_fields if key in run}
    if "red" in run:
        banked["red"] = run.get("red")
        banked["note"] = (
            "LEGACY runner rollup kept for provenance, not for truth: its red is a "
            "subtraction that folds awaiting-judge and not-recorded into failure"
        )
    else:
        banked["note"] = (
            "typed source rollup: every probe state was counted by name; unresolved "
            "is the sum of named non-green components, never total-minus-green"
        )
    return {
        "ran": run.get("ts"), "run": label,
        # kept: the one field prior consumers read, and it still means exactly what it
        # meant - probes with nothing outstanding. Its complement is NOT "red".
        "green": probes["green"],
        # the honest single scalar, for a consumer that genuinely needs one. Summed
        # from the named components, which ride beside it and are the real answer.
        "unresolved": (probes["red"] + probes["awaiting_judge"]
                       + probes["not_recorded"] + probes["unrecognised"]),
        "probes": probes,
        "checks": checks,
        "judge": judge_block,
        "banked_run_row": banked,
    }


# The census store carries NO run identifier - the runner writes one row per organ and
# nothing that says "these rows are one run". Until census generation stamps one (codex
# owns that and is frozen on it), the latest OBSERVATION is inferred from a declared time
# window. The window is a CRUTCH: it is stated on every surface that serves this block and
# retires the moment a run id exists. See corpus_friction/crutches.jsonl.
_CENSUS_OBSERVATION_WINDOW_S = 300.0


def _census_ts(raw: Any) -> float | None:
    """Row timestamps arrive as ISO-8601, with or without `Z` and fractional seconds."""
    if not raw:
        return None
    txt = str(raw).strip().replace("Z", "+00:00")
    try:
        from datetime import datetime
        return datetime.fromisoformat(txt).timestamp()
    except ValueError:
        return None


def census_states(path: Path | str,
                  window_seconds: float = _CENSUS_OBSERVATION_WINDOW_S) -> dict[str, Any]:
    """Every organ counted BY NAME inside the LATEST OBSERVATION, and an organ that the
    latest observation never touched named as UNOBSERVED rather than folded into `dead`.

    This is the census half of the cure `bench_states` already carries for the bench
    (SYNTH-20260825-the-unknown-collapses). The prior fold was last-value-wins across
    EVERY run in the store, stamped with the newest row's timestamp - so
    `the-judges-plant-b`, last seen DEAD on 2026-08-23, was served as a dead organ of the
    2026-08-25 run that never observed it. That is class 1, absence-becomes-present: the
    most expensive collapse there is, because a reader cannot tell the manufactured value
    from a measured one afterwards.

    An organ absent from the latest observation is NOT functional and NOT dead. It is
    unobserved, and that is a state with a name here.
    """
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    verdict_rows = [r for r in rows if r.get("record") == "census-verdict"]
    if not verdict_rows:
        return {"ran": None, "organs": 0, "dead": [], "organs_ever": 0,
                "unobserved": {}, "verdicts": {},
                "observation": {"window_seconds": window_seconds,
                                "note": "no census-verdict row has ever been banked"}}

    stamped = [(r, _census_ts(r.get("ts"))) for r in verdict_rows]
    newest = max((t for _, t in stamped if t is not None), default=None)

    # the latest observation: every row inside the declared window back from the newest.
    # A row with an unparseable timestamp is NEVER swept in - it is counted by name below.
    if newest is None:
        batch, undated = [], verdict_rows
    else:
        batch = [r for r, t in stamped if t is not None and newest - t <= window_seconds]
        undated = [r for r, t in stamped if t is None]

    observed: dict[str, dict[str, Any]] = {}
    for r in batch:                      # last write wins WITHIN the observation only
        observed[str(r.get("organ"))] = {"verdict": r.get("verdict"), "ts": r.get("ts"),
                                         "wall_s": r.get("wall_s")}

    ever: dict[str, dict[str, Any]] = {}
    for r in verdict_rows:               # provenance across the whole store
        ever[str(r.get("organ"))] = {"verdict": r.get("verdict"), "ts": r.get("ts")}

    unobserved = {
        organ: {"last_verdict": last.get("verdict"), "last_seen": last.get("ts"),
                "age_hours": (round((newest - (_census_ts(last.get("ts")) or newest)) / 3600.0, 1)
                              if newest is not None else None)}
        for organ, last in sorted(ever.items()) if organ not in observed
    }

    verdicts: dict[str, int] = {}
    for body in observed.values():
        key = str(body.get("verdict"))
        verdicts[key] = verdicts.get(key, 0) + 1

    dead = sorted(o for o, body in observed.items() if body.get("verdict") != "FUNCTIONAL")

    # the judge's own overrides - a DIFFERENT act from the census run, exactly as the
    # bench serves judge-verdict rows beside (never inside) the self-run's counts.
    adjudications = {str(r.get("organ")): {"verdict": r.get("verdict"), "ts": r.get("ts"),
                                           "reason": r.get("reason")}
                     for r in rows if r.get("record") == "adjudication"}

    out: dict[str, Any] = {
        "ran": max((r.get("ts") for r in batch), default=None) if batch else None,
        # kept: the field every prior consumer reads. It now means what it says - the
        # organs THIS observation actually touched, not every organ ever recorded.
        "organs": len(observed),
        # kept: and it is now scoped to the same observation, so it can no longer carry
        # a verdict from a run that did not happen.
        "dead": dead,
        "organs_ever": len(ever),
        "verdicts": verdicts,
        "observed": observed,
        "unobserved": unobserved,
        "observation": {
            "window_seconds": window_seconds,
            "rows_in_window": len(batch),
            "rows_total": len(verdict_rows),
            "note": "the census store carries no run id; this observation is every row "
                    "within the declared window back from the newest. An organ outside "
                    "it is UNOBSERVED - never counted functional, never counted dead.",
            "crutch": "CRUTCH-20260825-census-run-window",
        },
    }
    if undated:
        out["observation"]["undated_rows"] = len(undated)
        out["observation"]["undated_organs"] = sorted({str(r.get("organ")) for r in undated})
    if adjudications:
        out["adjudications"] = {
            "organs_adjudicated": len(adjudications),
            "verdicts": {k: v["verdict"] for k, v in sorted(adjudications.items())},
            "note": "a judge's override of a census verdict - a SEPARATE act from the "
                    "run counted above and NOT merged into it",
        }
    return out


def banked_verdicts_with_age(
        repo_root: Path | str | None = None) -> dict[str, Any]:
    """The banked-with-age half of the SB-6 law: the census + bench + verifier serve
    their LAST BANKED verdicts stamped with age, and go RED-stale the moment any
    store they summarize is newer than the run - never a fresh-looking stale.

    This is public because the wake and the Atlas board are two registers of the same
    verdict layer. A surface importing a private wake implementation would be a hidden
    coupling and would eventually fork the health truth it was trying to share.
    """
    root = Path(repo_root).resolve() if repo_root is not None else _repo_root()
    out: dict[str, Any] = {}
    stores_newest = 0.0
    for rel in ("contract/promises.jsonl", "corpus_friction/work_orders.jsonl",
                "corpus_friction/campaign.jsonl", "corpus_friction/open_stack_wants.jsonl"):
        p = root / rel
        if p.exists():
            stores_newest = max(stores_newest, p.stat().st_mtime)
    def _age_block(path: Path, summarize) -> dict[str, Any]:
        if not path.exists():
            return {"status": "RED", "absent": f"{path.name} does not exist yet"}
        try:
            body = summarize(path)
        except Exception as exc:  # noqa: BLE001
            return {"status": "RED", "absent": f"{path.name} unreadable: {exc}"}
        stale = path.stat().st_mtime < stores_newest
        return {"status": "STALE-RED" if stale else "BANKED", **body,
                **({"note": "stores moved since this run - re-run before trusting"} if stale else {})}
    def _census(p: Path) -> dict[str, Any]:
        # every organ counted by name inside the latest observation - see census_states()
        return census_states(p)
    def _bench(p: Path) -> dict[str, Any]:
        # every state counted by name off the rows - see bench_states()
        return bench_states(p)
    out["census"] = _age_block(root / "corpus_friction" / "census_verdicts.jsonl", _census)
    out["stranger_bench"] = _age_block(root / "holdout" / "STRANGER_BENCH_VERDICTS.jsonl", _bench)
    idx = root / "holdout" / "sb3_surfaces.txt.index.json"
    if idx.exists():
        try:
            out["surface_verifier"] = {"status": "BANKED",
                                       "bound_at": json.loads(idx.read_text())["bound_at"],
                                       "descend": "scripts/laplace-python scripts/atlas_bind.py check --manifest "
                                                  "holdout/sb3_surfaces.txt"}
        except Exception as exc:  # noqa: BLE001
            out["surface_verifier"] = {"status": "RED", "absent": str(exc)}
    else:
        out["surface_verifier"] = {"status": "RED", "absent": "surfaces never bound"}
    return out


def _next_aim_age(payload: dict[str, Any]) -> dict[str, Any]:
    """A3 (superego amendment, 2026-08-23): the next-aim shard serves its origin-close
    timestamp VISIBLY, with age and whether the stores have moved since -- so
    era-stamping is legible at the moment of serving. The exact channel that carried
    the venv falsehood ('the venv is gone', banked at a close, served as now for two
    days) closes by age-stamp, not by trusting an authored slot."""
    import re as _re
    from datetime import date, datetime
    aim = next((s for s in (payload.get("fixed_point") or {}).get("shards", [])
                if s.get("shard") == "next-aim"), None)
    if not aim:
        return {"absent": "no next-aim shard served"}
    m = _re.search(r"(\d{4})-(\d{2})-(\d{2})", str(aim.get("title", "")))
    if not m:
        return {"absent": "next-aim title carries no origin date - unstampable, loud"}
    origin = date(*map(int, m.groups()))
    root = _repo_root()
    newest = 0.0
    for rel in ("contract/promises.jsonl", "corpus_friction/work_orders.jsonl",
                "contract/predictions.jsonl", "corpus_friction/open_stack_wants.jsonl",
                "corpus_friction/campaign.jsonl"):
        p = root / rel
        if p.exists():
            newest = max(newest, p.stat().st_mtime)
    moved = datetime.fromtimestamp(newest).date() > origin if newest else False
    return {"origin_close": origin.isoformat(),
            "age_days": (date.today() - origin).days,
            "stores_moved_since": moved,
            "read_as": ("HISTORY - the stores have moved since this aim was authored; "
                        "the verdict layer is the present" if moved else "current")}


def main(argv: list[str] | None = None) -> int:
    # The doorway owns its encoding (the embed_router.main precedent): the payload carries
    # arrows and house typography, and a bare Windows console defaults to cp1252 — every
    # dispatched agent's wake seed died on it (2026-07-13, RW-20260713-224401-146629).
    # The entry point must not depend on the caller remembering PYTHONUTF8.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="laplace-wake",
                                 description="The wake in one command: probe + grade-0 (+ grade-1 delta).")
    ap.add_argument(
        "--grade",
        type=int,
        choices=(0, 1, 2),
        default=1,
        help="highest grade to include: 0=fixed point, 1=delta (default), 2=deep map",
    )
    ap.add_argument("--emit", action="store_true",
                    help="print the compact ambient-wake context block (engine mode, grade-0 only)")
    ap.add_argument("--engine", action="store_true",
                    help="wake the engine projection only - worker/ambient mode, no identity")
    ap.add_argument("--person", action="store_true",
                    help="request the person wake; this is now the default and the flag is a no-op kept for muscle memory")
    ap.add_argument("--score", action="store_true",
                    help="explicitly execute the banked checks; ordinary opening observes prior results only")
    ap.add_argument("--health", action="store_true",
                    help="observe processes, runtime, source/deposit health and close state without running checks")
    ap.add_argument("--account", action="store_true",
                    help="serve the live promised-vs-done account (SB-1): the five stores "
                         "spec-normalized, whole, as one JSON object; nothing else runs")
    ap.add_argument("--seat", metavar="NAME",
                    help="with --account: serve that SEAT's slice of the account "
                         "(open/deferred/held rows whose by/owner/source/text name it) "
                         "- one call in place of the judge's five hand greps")
    ap.add_argument("--campaign", action="store_true",
                    help="run every campaign gate NOW and serve stages/next_act (SB-5); "
                         "gate verdicts bank through the journal seam")
    ap.add_argument("--relay-ready", action="store_true",
                    help="the seat-relay check (DP-SEAT): exit 0 iff a successor loses "
                         "nothing - tree clean or named, no live in-flight acts, nothing "
                         "unpushed")
    ap.add_argument("--fabric", action="store_true",
                    help="serve only the bounded, read-only seat-fabric inbox projection")
    ap.add_argument("--campaign-records", action="store_true",
                    help="observe banked campaign evidence without executing its gates")
    ap.add_argument(
        "--full",
        action="store_true",
        help="explicitly descend to the unbounded authored projection (never a startup default)",
    )
    ap.add_argument("--memory", action="store_true", help="resolve current law/preferences and view drift from records")
    ap.add_argument("--project", metavar="NAME", help="project current work/source coverage without running gates")
    a = ap.parse_args(argv)

    if a.health:
        from laplace.engine import process_health
        from laplace.engine.close_beats import close_projection
        from laplace.representation.embedding_health import read_health
        from laplace.core.runtime import receipt
        root = _repo_root()
        print(json.dumps({"read_only": True, "runtime": receipt(),
                          "processes": _process_observation(root),
                          "coordination": _workflow_observation(root),
                          "probe": process_health.probe(), "semantic_memory": read_health(root),
                          "close": close_projection(root, verify_artifacts=True), "checks": _recorded_checks(root)},
                         ensure_ascii=False, indent=1, default=str))
        return 0

    if a.fabric:
        print(json.dumps(seat_fabric_glow(), ensure_ascii=False, indent=1, default=str))
        return 0

    if a.relay_ready:
        # DP-SEAT (both seats' relay design, 2026-08-23): relay-readiness is a CHECK,
        # never a feeling - 'nothing lives only in my head' made mechanical at the seat
        # boundary. Reads only; exit 0 = green.
        import subprocess
        checks: dict[str, Any] = {}
        p = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                           text=True, cwd=_repo_root())
        dirty = [line for line in p.stdout.splitlines()
                 if line.strip() and not line.endswith(".log")]
        checks["tree"] = {"ok": not dirty, "dirty": dirty[:8]}
        p = subprocess.run(["git", "rev-list", "--count", "@{u}..HEAD"],
                           capture_output=True, text=True, cwd=_repo_root())
        ahead = int(p.stdout.strip() or 0) if p.returncode == 0 else -1
        checks["pushed"] = {"ok": ahead == 0, "ahead": ahead}
        from laplace.core.records import journal as _j
        rec = _j.recover(_repo_root())
        live = {k: v["act"] for k, v in rec.get("in_flight", {}).items()}
        checks["journal"] = {"ok": not live, "in_flight": live}
        # FIND-SE-008: porcelain certifies nothing about gitignored mass - a successor
        # must not inherit hidden heavyweights unnamed (a .venv is LOUD always).
        from laplace.engine import process_health
        heavy = process_health.ignored_heavyweights()
        checks["ignored_heavyweights"] = {"ok": not heavy, "findings": heavy}
        ok = all(c["ok"] for c in checks.values())
        # WO-20260823-seat-fabric-discovery: the relay check said what a successor keeps
        # and never WHO it is relaying with. The seats ride BESIDE the checks, never
        # inside them - discovery is not a pass/fail condition, and an unfounded store
        # must not fail a relay that is otherwise green.
        from laplace.engine import seats as _seats
        print(json.dumps({"relay_ready": ok, "checks": checks,
                          "seats": {"store": _seats.STORE,
                                    "current": _seats.current_seats(_repo_root())},
                          "law": "a successor loses nothing, or this says what it loses"},
                         ensure_ascii=False, indent=1))
        return 0 if ok else 1

    if a.memory:
        from laplace.engine.session_memory import projection
        print(json.dumps(projection(_repo_root(), compact=True), ensure_ascii=False, indent=1))
        return 0
    if a.project:
        from laplace.representation.atlas_status_projection import project_atlas_current_status
        print(json.dumps(project_atlas_current_status(_repo_root(), project=a.project), ensure_ascii=False, indent=1))
        return 0

    if a.account:
        out = account_seat(a.seat) if a.seat else account()
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return 0
    if a.campaign_records:
        out = campaign(_repo_root(), run_gates=False)
        out["next_act_basis"] = "recorded stage frontier; current author priority is in HANDOFF.md"
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return 0
    if a.campaign:
        print(json.dumps(campaign(run_gates=True), ensure_ascii=False, indent=1, default=str))
        return 0

    mode = "engine" if (a.engine or a.emit) else "person"

    if a.emit:
        payload = wake_payload(grade=0, mode="engine")
        print(_emit_block(payload))
        return 0

    payload = wake_payload(grade=a.grade, mode=mode)
    # Opening is observation. Historical checks can launch processes and write scores;
    # they run only on explicit --score, with the existing recursion guard and shared budget.
    if os.environ.get("LAPLACE_WAKE_SCORING"):
        pass
    elif a.score:
        try:
            from laplace.engine import holdout
            wall = holdout.Wall(holdout.WAKE_BUDGET_S)
            scores = holdout.score_mechanical(_repo_root(), wall=wall)
            if scores:
                payload = {**payload, "holdout": scores}
            threads = holdout.score_threads(_repo_root(), wall=wall)
            if threads:
                payload = {**payload, "thread_probes": threads}
        except Exception as exc:  # noqa: BLE001
            payload["holdout"] = {"status": "UNKNOWN", "live": True,
                                  "reason": f"{type(exc).__name__}: {exc}"}
    else:
        payload = {**payload, **_recorded_checks(_repo_root())}
    # The verdict layer (SB-6, 2026-08-23): the authored wake serves the ACCOUNT, never
    # homework. Live-if-cheap: the account + the in-flight journal are pure store reads
    # (no embedder, no model, no network; ~0.2s against the 2.0s grade-0 budget) so they
    # fire live. Banked-with-age: the SB-3 checker + SB-7 census serve their last banked
    # verdicts stamped with run age once those stores exist; until then the LOUD ABSENCE
    # idiom rides - a wake with no verdict layer must never look like one whose layer is
    # green. Deliberately NOT on the --emit path (the scorecard precedent: the dispatch
    # hot path stays sub-second), and deliberately blind to HANDOFF prose - the venv
    # falsehood travelled through next-aim text, so this layer reads stores only.
    try:
        from laplace.core.records import journal as _journal
        _rec = _journal.recover(_repo_root())
        _inflight: dict[str, Any] = {
            "acts_total": _rec["acts_total"],
            "last_durable_write": _rec["last_durable_write"],
            "in_flight": {k: {"act": v["act"], "began": v["began"],
                              "killed_mid_step": [s["name"] for s in v["killed_mid_step"]],
                              "never_reached": v["never_reached"]}
                          for k, v in _rec["in_flight"].items()},
        }
    except Exception as exc:  # noqa: BLE001
        _inflight = {"absent": f"journal recover failed: {type(exc).__name__}: {exc}"}
    try:
        _acct: dict[str, Any] = account_capped(_repo_root())
    except Exception as exc:  # noqa: BLE001
        _acct = {"absent": f"account failed: {type(exc).__name__}: {exc}"}
    # GUARDED LIKE ITS NEIGHBOURS: the account and the journal each degrade to a loud
    # {"absent": ...} rather than killing the doorway, and campaign() now reads a SECOND
    # store (work_orders.jsonl, for the next act's progress) - a widened blast radius on
    # the one call that was still unwrapped. A wake that cannot serve the campaign must
    # still serve the identity and the rest of the verdict layer.
    try:
        _camp = campaign(_repo_root(), run_gates=False)
        _camp = (_camp if "absent" in _camp else
                 {"next_act": _camp["next_act"],
                  # the three facts this reduction used to destroy, kept beside the frontier:
                  # the next act's title (the stages list is about to become {id: status}),
                  # what its gate named as missing, and which wave last returned.
                  "next_act_title": _camp.get("next_act_title"),
                  "next_act_gate_residuals": _camp.get("next_act_gate_residuals"),
                  "last_wave_returned": _last_wave_returned(_repo_root()),
                  "progress": _camp.get("progress"),
                  "stages": {x["id"]: x["status"] for x in _camp["stages"]},
                  "schema_residuals": _camp.get("schema_residuals", []),
                  "next_act_basis": "recorded stage frontier, not current scheduling authority",
                  "current_priority_source": "HANDOFF.md",
                  "descend": "scripts/laplace-python scripts/wake.py --campaign-records"})
    except Exception as exc:  # noqa: BLE001
        _camp = {"absent": f"campaign failed: {type(exc).__name__}: {exc}"}
    payload = {**payload, "verdict_layer": {
        "account": _acct,
        "in_flight": _inflight,
        "campaign_rows": _camp,
        "verifier_and_census": banked_verdicts_with_age(),
        "next_aim_age": _next_aim_age(payload),
    }}
    # the loud line, on stderr so stdout stays one parseable JSON object: a registry that did
    # not IMPORT leaves the projects shard blind, and that must be unmissable at the doorway.
    # It also rides payload["registry_down"] and the probe's verdict (wake_payload).
    if payload.get("registry_down"):
        print(payload["registry_down"], file=sys.stderr)
    from laplace.pipeline import dial_profiles as dials
    payload["dial_sets"] = dials.projection(full=a.full)
    if not a.full:
        payload = _bound_authored_payload(payload, mode=mode)
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
