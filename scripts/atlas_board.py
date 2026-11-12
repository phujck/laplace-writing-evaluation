#!/usr/bin/env python3
"""The Atlas board — a source-derived interface over campaign, walk, bench, health, and diffusion observability.

His steer (2026-08-24, in-session): "the interface... sitting pretty well unbuilt and we
may as well grow from the top." The top is this: ONE page produced FROM ROWS ONLY —
the campaign spine, the S0 disposition panel he bulk-ratifies, the walk strip, the
live seat fabric, and the named bench/health/observability planes — in BOTH registers from one producer (the two-views law: his render
and the engine-readable payload, never a human-only panel). Every claim carries its row
source. This is a RENDER; it goes stale the moment rows move — regenerate, never edit.

Laws honored: rows-before-renders (each pane names its store) · the attention law
(non-linear, anchored, dense — no prose walls) · the walk stays HIS (the walked axis is
SeatRole.AUTHOR-reserved in atlas.migration; the board can only hand him the act) ·
canonical readers imported, never reimplemented (laplace.engine.wake.campaign is the one truth
for stage status).

Mount path: built to be absorbed at the front door (the ruled ABSORB target,
NOTE-20260824-s0-disposition-table-routes) when the codex pen allows; serves static
until then. Output: atlas/board/board.{json,html}.

Runtime law: /usr/bin/python3, system + user site, read-only against every store.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "atlas" / "board"

DISPO_ORDER = ["RETIRED", "ABSORBED", "HOLD-FOR-RULING", "HOLD-UNTIL-PROVEN",
               "EVIDENCE-AND-GENERATOR-RULE-HOLD", "EVIDENCE-AND-EXPLICIT-DIAL-HOLD",
               "QUARRY-EVIDENCE", "DESIGNED-INHERITANCE", "CARRIED"]

#: A class token plus the dated coordinates that follow it: the machine half of a house
#: handle. ``WO-20260716-145343-adjudication-lenses`` and ``CAMP-00-opener-deposit-cures``
#: both open with one, and what follows it is the part a person wrote on purpose.
#: A coordinate segment must START with a digit but need not be pure digits — the store
#: carries ``WO-20260801b-…`` (a same-day disambiguator) and ``WO-20260824T164032-…``
#: (compact ISO); a ``\d+`` coordinate left both of those leading with their timestamps.
_HANDLE_HEAD = re.compile(r"^[A-Z][A-Z0-9]{1,7}-(?:\d[\dA-Za-z]*-)*")
#: An authored gloss the row's own author appended in parentheses, e.g.
#: ``src/atlas/updown.py (the clean canonical UP/DOWN kernel)``.
_HANDLE_GLOSS = re.compile(r"^(?P<handle>[^(]+?)\s*\((?P<gloss>.+)\)\s*$")


def _face(handle: str) -> tuple[str, str]:
    """Split one house handle into (face, handle) — the reading half and the machine half.

    CONJUGATE HANDLES, measured 2026-08-25 on the served board: 227 of the 466 disposition
    rows led with a bare slug in bold — ``WO-20260716-145343-adjudication-lenses``,
    ``PRM-20260721-artefact-editor-overleaf`` — with the authored gloss demoted to grey
    underneath. That is the law inverted on one page 227 times: the id led, the face
    followed. A reader arriving with zero context cannot act on a timestamp.

    This SELECTS the authored substring; it never composes language (authored-vocabulary:
    derivation is right for facts and wrong for words). A parenthetical gloss wins, then
    the slug tail with its class token and dated coordinates dropped. Anything that is
    already a person's name for the thing — ``walk_requests.py``, ``analytics-2``,
    ``corpus_friction/atlas_inventory.jsonl`` — is returned unchanged, because a path IS
    its own face and rewriting it would be the invention this rule forbids.
    """
    text = str(handle).strip()
    gloss = _HANDLE_GLOSS.match(text)
    if gloss:
        return gloss.group("gloss").strip(), gloss.group("handle").strip()
    tail = _HANDLE_HEAD.sub("", text)
    # The tail must actually BE words. ``ATLAS-S0`` leaves "S0", which is a coordinate,
    # not a face — stripping there would trade a readable id for an unreadable fragment.
    words = ("-" in tail or "_" in tail) or (len(tail) >= 6 and tail.isalpha())
    if tail and tail != text and words and not tail[0].isdigit():
        return tail.replace("-", " ").replace("_", " "), text
    return text, text


def _first_clause(text: str, cap: int = 96) -> str:
    """The first clause of a row's own prose — the convention front_door._row_face sets.

    A fold whose header is a bare id tells the reader nothing about whether to open it;
    28 of the crutch folds shipped exactly that. The row's own sentence is the header.
    """
    head = re.split(r"(?<=[.;:])\s", str(text).strip(), maxsplit=1)[0]
    head = head[:cap].rstrip(" -–,(:")
    if head.count("(") > head.count(")"):
        head = head.split("(", 1)[0].strip()
    return head


def campaign_pane() -> dict:
    from laplace.engine import wake as wk
    c = wk.campaign(ROOT, run_gates=False)
    stages = [
        {"id": s["id"], "stage": s.get("stage"), "title": s.get("title", ""),
         "status": s["status"], "why": (s.get("why") or "")[:180]}
        for s in c.get("stages", []) if str(s["id"]).startswith("ATLAS-")
    ]
    return {"source": "corpus_friction/campaign.jsonl via laplace.engine.wake.campaign",
            "next_act": c.get("next_act"), "stages": stages,
            "schema_residuals": c.get("schema_residuals", [])}


def inventory_pane() -> dict:
    store = ROOT / "corpus_friction" / "atlas_inventory.jsonl"
    generation = None
    rows_by_id: dict[str, dict] = {}
    for line in store.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("record") == "inventory-generation":
            generation = r["id"]
        elif r.get("record") == "inventory":
            rows_by_id[r["id"]] = r      # last-wins by id, the house rule
    latest = [r for r in rows_by_id.values() if r.get("generation") == generation]
    classes: dict[str, dict] = {}
    for r in sorted(latest, key=lambda x: (x["class"], x["disposition"], x["id"])):
        cls = classes.setdefault(r["class"], {"count": 0, "by_disposition": {}, "rows": []})
        cls["count"] += 1
        cls["by_disposition"][r["disposition"]] = cls["by_disposition"].get(r["disposition"], 0) + 1
        cls["rows"].append({"id": r["id"], "item": r["item"], "disposition": r["disposition"],
                            "mode": r.get("mode"), "why": r["why"], "ground": r["ground"]})
    return {"source": f"corpus_friction/atlas_inventory.jsonl generation {generation} "
                      "(last-wins by id)",
            "generation": generation, "total_rows": len(latest), "classes": classes}


def walk_pane() -> dict:
    # The S0 verdict comes from the gate, consumed VERBATIM (its author's contract:
    # re-deriving verdict/residuals here would be a defect in the contract, not a feature).
    gate: dict = {}
    gate_note = ""
    proc = subprocess.run(["/usr/bin/python3", str(ROOT / "scripts" / "atlas_s0_gate.py")],
                          capture_output=True, text=True, cwd=ROOT)
    try:
        gate = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        gate_note = f"gate output unparseable (exit {proc.returncode}) — shown loudly, not hidden"
    judged = gate.get("judged_row")
    migration: dict = {"status": "unread"}
    try:
        from laplace.representation import atlas_bridge as ab
        replay = ab.replay_migration(ab._store())
        st = replay.stages.get("ATLAS-S0")
        migration = ({"status": "REPLAYED", "revision": st.revision, "material": st.material,
                      "judged": st.judged, "walked": st.walked,
                      "event": replay.event_ids.get("ATLAS-S0", "")[:30]}
                     if st else {"status": "ATLAS-S0 undeclared in the canonical store"})
    except Exception as exc:  # noqa: BLE001 - a refusing store is shown, never papered
        migration = {"status": f"REFUSED: {type(exc).__name__}: {exc}"}
    walked = bool(migration.get("walked"))
    return {
        "source": "scripts/atlas_s0_gate.py (atlas_s0_gate/1, verdict consumed verbatim) "
                  "· atlas.migration.replay_migration over the canonical store (walked axis, "
                  "replayed live on this render)",
        "gate_verdict": gate.get("verdict"),
        "gate_residuals": gate.get("residuals", []),
        "gate_note": gate_note,
        "judged_row": judged,
        "migration": migration,
        "walked_row": (migration.get("event") if walked else None),
        "author_command": ("/usr/bin/python3 scripts/atlas_walk.py ATLAS-S0 "
                           "--accept \"<your walk verdict, verbatim>\" [--veto INV-...]"),
        "the_walk_is_his": ("HONEST BOUNDARY (per the codex mount audit): the AUTHOR guard at "
                            "migration.py:372 validates a role label, not your identity — the "
                            "command CARRIES your hand procedurally (run it yourself, or a seat "
                            "runs it in-session on your explicit words) and banks a forensic "
                            "receipt (user/tty/cwd) in the canonical event. The canonical "
                            "migration event is the SOLE walked truth; the work-order row is a "
                            "derived projection appended only after it succeeds. Vetoed INV-* "
                            "ids re-enter HOLD-FOR-RULING at the next generation."),
    }


def live_pane() -> dict:
    git = subprocess.run(["git", "log", "--oneline", "-9"], capture_output=True,
                         text=True, cwd=ROOT).stdout.strip().splitlines()
    # TEMPORAL DEIXIS IS A DECAYING CLAIM. The section this feeds was headed "tonight's
    # commits" — true for a few hours after the build and false every morning after, on a
    # render that is served from a day-keyed cache. The commit's own date is the fact;
    # the heading now carries it, so the page cannot age into a lie.
    git_date = subprocess.run(["git", "log", "-1", "--format=%cs"], capture_output=True,
                              text=True, cwd=ROOT).stdout.strip()
    fabric: dict = {"status": "unread"}
    try:
        from laplace.representation import atlas_bridge as ab
        state = ab.snapshot()["provider"]
        msgs = sorted(state.get("messages", {}).values(),
                      key=lambda m: -int(m["message"].get("cursor", 0)))[:8]
        fabric = {
            "status": "LIVE (chain verified on this read)",
            "seats": sorted(state.get("seats", {})),
            "recent": [{"cursor": m["message"].get("cursor"),
                        "type": m["message"].get("message_type"),
                        "from": m["message"].get("sender_seat_id"),
                        "to": m["message"].get("recipient_seat_id"),
                        "status": m.get("status")} for m in msgs],
        }
    except Exception as exc:  # noqa: BLE001 - the outage story is data, shown loudly
        fabric = {"status": f"REFUSED: {type(exc).__name__} — the store's loud-refusal "
                            "posture; see contract/talk.jsonl outage rows"}
    demo = {}
    rep = ROOT / "evidence" / "ATLAS_UPDOWN_V0_2026-08-24" / "REPORT_bge-small-en-v1.5.json"
    if rep.exists():
        r = json.loads(rep.read_text())
        demo = {"source": str(rep.relative_to(ROOT)),
                "headline": r["headline"],
                "corpus": {k: r["corpus"][k] for k in ("files", "spans", "handles",
                                                        "handle_to_corpus_ratio")},
                "note": "generation 1 (bge-small, CPU-observed); bge-base comparison running"}
    acceptance = {"status": "no audit-lane fabric rows readable",
                  "source": "fabric messages, type-filtered, latest by cursor"}
    try:
        from laplace.representation import atlas_bridge as ab
        blobs = ab._blobs()
        state = ab.snapshot()["provider"]
        # EXPLICIT lane allowlist (codex mount-refusal cure): only the acceptance
        # verdict/cure lane itself — never adjacent audit traffic like board-audit.
        LANE = {"s1-planted-acceptance-ready-for-audit", "s1-acceptance-audit-claim",
                "s1-acceptance-audit-verdict", "acceptance-cure",
                "acceptance-cure-amendment"}
        lane = [m for m in state.get("messages", {}).values()
                if str(m["message"].get("message_type", "")) in LANE]
        if lane:
            latest = max(lane, key=lambda m: int(m["message"].get("cursor", 0)))
            msg = latest["message"]
            body = blobs.get(msg["body_handle"]) if hasattr(blobs, "get") else                 blobs.read(msg["body_handle"])
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")
            acceptance = {"source": "fabric messages, type-filtered, latest by cursor",
                          "cursor": msg.get("cursor"), "type": msg.get("message_type"),
                          "from": msg.get("sender_seat_id"), "status": latest.get("status"),
                          "head": body[:260]}
    except Exception as exc:  # noqa: BLE001 - shown loudly
        acceptance = {"status": f"REFUSED: {type(exc).__name__}", "source": "fabric"}
    return {"git_head": git, "git_head_date": git_date or "unknown",
            "fabric": fabric, "updown_demo": demo, "acceptance_audit": acceptance}


def _json_receipt(rel: str) -> tuple[dict, str | None]:
    """Read one immutable receipt, preserving absence/corruption as payload data."""
    path = ROOT / rel
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a missing receipt is a visible red
        return {}, f"{rel}: {type(exc).__name__}: {exc}"
    if not isinstance(body, dict):
        return {}, f"{rel}: top level is {type(body).__name__}, expected object"
    return body, None


def bench_pane() -> dict:
    """S0's measured demand, reconstruction and storage planes — receipts, not reruns.

    The board is a serve path. It must not quietly turn into a benchmark runner, an
    embedder or a migration probe, so every number below is selected from a named,
    banked receipt and carries the receipt's own scope. Refreshing a measurement is a
    separate act which mints a successor receipt.
    """
    demand_rel = "evidence/ATLAS_BENCH_2026-08-24/DEMAND_INVENTORY.json"
    recall_rel = "evidence/ATLAS_UPDOWN_V0_2026-08-24/REPORT_bge-small-en-v1.5.json"
    storage_rel = "evidence/ATLAS_HIVED_STORAGE_2026-08-25/" \
                  "CURRENT_SOURCE_REATTACK_RECEIPT.json"
    amendment_rel = "evidence/ATLAS_HIVED_STORAGE_2026-08-25/" \
                    "NAMING_AND_MEASUREMENT_AMENDMENT.json"
    demand, demand_error = _json_receipt(demand_rel)
    recall, recall_error = _json_receipt(recall_rel)
    storage, storage_error = _json_receipt(storage_rel)
    amendment, amendment_error = _json_receipt(amendment_rel)

    aspects = []
    for row in demand.get("aspect_classes", []):
        aspects.append({
            "aspect_class": row.get("aspect_class"),
            "count": row.get("count"),
            "coverage_hint": row.get("current_coverage_hint"),
            "coverage_basis": row.get("coverage_basis"),
            "measured_fraction": row.get("measured_fraction"),
        })
    totals = demand.get("totals", {})
    headline = recall.get("headline", {})
    source = storage.get("source", {})
    candidate = storage.get("candidate", {})
    equivalence = storage.get("equivalence", {})
    scope = amendment.get("authorization_scope", {})
    return {
        "source": " · ".join((demand_rel, recall_rel, storage_rel, amendment_rel)),
        "source_paths": {
            "demand": demand_rel,
            "recall": recall_rel,
            "storage": f"{storage_rel} · {amendment_rel}",
        },
        "staleness": "banked receipts only; each sub-plane names its observed generation "
                     "or timestamp and is never recomputed by the board",
        "errors": [x for x in (demand_error, recall_error, storage_error,
                                amendment_error) if x],
        "demand": {
            "generated_at": demand.get("generated_at"),
            "repo_head": demand.get("repo_head"),
            "queries_total": totals.get("queries_total"),
            "queries_unresolved_provenance": totals.get("queries_unresolved_provenance"),
            "aspect_classes_total": totals.get("aspect_classes"),
            "aspects": aspects,
            "gaps": demand.get("gaps", []),
        },
        "recall": {
            "generation": recall.get("generation"),
            "encoder": (recall.get("version_axes") or {}).get("encoder_id"),
            "probes": headline.get("probes"),
            "descent_hit_at_1": headline.get("descent_hit_at_1"),
            "descent_hit_at_3": headline.get("descent_hit_at_3"),
            "flat_handle_hit_at_3": headline.get("flat_handle_hit_at_3"),
            "content_ceiling_hit_at_3": headline.get("content_ceiling_hit_at_3"),
            "historic_misses_reasked": headline.get("historic_misses_reasked", []),
            "scale_posture": recall.get("scale_posture"),
        },
        "storage": {
            "observed_at": storage.get("observed_at"),
            "store_role": (amendment.get("store_roles") or {}).get(
                "blueprint-generation", {}),
            "source_schema": source.get("schema_version"),
            "source_bytes": source.get("allocated_bytes"),
            "source_events": source.get("events"),
            "candidate_schema": candidate.get("schema_version"),
            "thin_ledger_bytes": candidate.get("thin_ledger_bytes"),
            "event_hive_logical_bytes": candidate.get("event_hive_logical_bytes"),
            "derived_index_bytes": candidate.get("derived_index_bytes"),
            "tree_allocated_bytes": candidate.get("tree_allocated_bytes"),
            "allocated_reduction_percent": candidate.get("allocated_reduction_percent"),
            "equivalence": {
                "materialized_state_equal": equivalence.get("materialized_state_equal"),
                "head_event_id_preserved": equivalence.get("head_event_id_preserved"),
                "event_count_preserved": equivalence.get("event_count_preserved"),
                "reachability_status": equivalence.get("reachability_status"),
            },
            "measurement_scope": scope,
            "production_mutated": storage.get("production_store_mutated"),
        },
    }


def health_pane() -> dict:
    """The verdict layer's cheap/read-only health data, mounted without firing it."""
    from laplace.engine import wake
    from laplace.core.records import journal

    bench_rel = "holdout/STRANGER_BENCH.json"
    verdicts_rel = "holdout/STRANGER_BENCH_VERDICTS.jsonl"
    bench, bench_error = _json_receipt(bench_rel)
    verdict_rows: list[dict] = []
    residuals: list[dict] = []
    try:
        for number, line in enumerate((ROOT / verdicts_rel).read_text(
                encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:  # noqa: BLE001 - named, never skipped silently
                residuals.append({"line": number, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if row.get("record") == "check" and row.get("check") == "sb6-budget":
                verdict_rows.append(row)
    except Exception as exc:  # noqa: BLE001
        residuals.append({"line": None, "error": f"{type(exc).__name__}: {exc}"})
    latest_wake = verdict_rows[-1] if verdict_rows else {}

    try:
        verdict_layer = wake.banked_verdicts_with_age(ROOT)
    except Exception as exc:  # noqa: BLE001
        verdict_layer = {"absent": f"verdict reader failed: {type(exc).__name__}: {exc}"}
    try:
        recovered = journal.recover(ROOT)
        in_flight = {
            "acts_total": recovered.get("acts_total"),
            "last_durable_write": recovered.get("last_durable_write"),
            "acts": {
                key: {"act": value.get("act"), "began": value.get("began"),
                      "killed_mid_step": [x.get("name") for x in
                                           value.get("killed_mid_step", [])],
                      "never_reached": value.get("never_reached", [])}
                for key, value in recovered.get("in_flight", {}).items()
            },
        }
    except Exception as exc:  # noqa: BLE001
        in_flight = {"absent": f"journal recover failed: {type(exc).__name__}: {exc}"}
    budget = bench.get("budget", {})
    return {
        "source": " · ".join((
            "laplace.engine.wake.banked_verdicts_with_age",
            bench_rel,
            verdicts_rel,
            "laplace.core.records.journal.recover(contract/journal.jsonl)",
        )),
        "staleness": "census and stranger-bench are banked-with-age; journal recovery is "
                     "live on each board build; no health probe is fired on the serve path",
        "errors": ([bench_error] if bench_error else []) + residuals,
        "verdicts": verdict_layer,
        "wake_budget": {
            "bar_seconds": budget.get("wake_grade0_total_s_max"),
            "baseline_seconds": budget.get("wake_grade0_baseline_s"),
            "latest_banked_seconds": latest_wake.get("seconds"),
            "latest_banked_status": latest_wake.get("status"),
            "latest_banked_at": latest_wake.get("ts"),
            "latest_banked_run": latest_wake.get("run"),
            "detail": latest_wake.get("detail"),
        },
        "in_flight": in_flight,
    }


def observability_pane(health: dict) -> dict:
    """Organ status plus the first banked instrument-class view."""
    from laplace.representation import instrument_serve

    instrument = instrument_serve.project(ROOT, "diffusion-scissors/1")
    paths = instrument_serve.source_paths(ROOT, "diffusion-scissors/1")
    return {
        "source": "corpus_friction/census_verdicts.jsonl via the health pane · "
                  + " · ".join(paths),
        "source_paths": {
            "organ_health": "corpus_friction/census_verdicts.jsonl via the health pane",
            "instrument": " · ".join(paths),
        },
        "staleness": "organ health retains the verdict reader's age stamp; the instrument "
                     "serves banked samples only after detached custody and every named "
                     "input digest verify on cache rebuild; the producer remains a separate act",
        "errors": instrument.get("errors", []),
        "organ_health": (health.get("verdicts") or {}).get("census", {}),
        "instruments": [instrument],
    }


#: stores whose rows ADJUDICATE a target. The act journal is deliberately NOT here:
#: it records that an act happened, not that anything was decided.
_LIVENESS_STORES = ("corpus_friction/work_orders.jsonl", "contract/promises.jsonl",
                    "corpus_friction/open_stack_forks.jsonl")
#: a record that DECIDES the target — the only kind that counts as returning to it.
_ADJUDICATES = {"resolution", "amendment", "ruling", "verdict", "walk-verdict",
                "finding", "undefer"}
#: commentary: real thinking, but it changes no state. Counted separately ON PURPOSE —
#: whether a note counts as "returned to" moves the answer from 33 rows to 2, so the
#: surface shows both and lets HIM set the predicate rather than picking one for him.
_COMMENTS = {"note"}


def liveness_pane() -> dict:
    """LIVE-AND-NECESSARY vs BANKED-AND-NEVER-RETURNED-TO — his question, 2026-08-25:
    "when all these orders accumulate I can't tell what's live and necessary versus what
    was simply banked and never returned to."

    THE FINDING THIS PANE EXISTS TO SHOW: activity is not adjudication. The aging teeth
    (scripts/ledger_age_audit.py) currently return PASS — failing=0 — because they ask
    "does this row carry a dated defer with an owner?", not "did anyone return to it?".
    Measured at first mount: of 52 open deferred/exempt rows, 33 had NEVER been
    adjudicated, while only 2 had never been touched at all. The other 31 are camouflaged
    by the noise made AROUND them — one carries 7 notes and 0 rulings. A "recent activity"
    pane would render every one of them healthy.

    CLASSIFIER IMPORTED, NEVER REIMPLEMENTED (the board's standing law): the open/deferred/
    exempt split is ``ledger_age_audit.audit()`` verbatim — the same code the close gate
    runs. This pane only DERIVES the history the teeth do not compute: how often a row was
    deferred, the chain of dates that defer walked, whether anything ever decided it, and
    the size of the cohort it was deferred with (a cohort of 10 stamped one date on one day
    is a sweep, not a judgement).
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "laplace_ledger_age_audit", ROOT / "scripts" / "ledger_age_audit.py")
    teeth = importlib.util.module_from_spec(spec)
    # registered BEFORE exec: ledger_age_audit defines @dataclass types, and the
    # decorator resolves annotations through sys.modules[cls.__module__]
    sys.modules[spec.name] = teeth
    spec.loader.exec_module(teeth)
    # EXPLICIT DATE, NAMED IN THE PAYLOAD. audit() defaults to date.today() internally,
    # which makes the verdict a function of the clock while looking like a function of
    # the rows. Passing it in — and rendering it — means a reader can SEE which day the
    # teeth were asked about instead of assuming it was this one. Paired with the `day`
    # component in front_door._atlas_drift_key, which expires the receipt at midnight.
    judged_on = date.today()
    report = teeth.audit(ROOT, judged_on)

    # every act that names a target, from the adjudicating stores only
    acts: dict[str, list[dict]] = {}
    cohort: dict[tuple, int] = {}
    # The teeth already performed the one diagnosed read.  Enrich those exact
    # rows; do not reparse through another skip policy and risk a PASS/count pair
    # derived from a different physical projection.
    from laplace.pipeline.ledger import integrity_projection
    integrity = integrity_projection(report.residuals, cap=24)
    malformed = integrity["residuals"]
    for rel in _LIVENESS_STORES:
        for r in report.records.get(rel, []):
            rec = r.get("record") or "(none)"
            if rec == "defer":
                cohort[(str(r.get("ts", ""))[:10], r.get("defer_until"))] = \
                    cohort.get((str(r.get("ts", ""))[:10], r.get("defer_until")), 0) + 1
            targets = {r[k] for k in ("target", "work_order", "wo", "promise")
                       if isinstance(r.get(k), str)}
            targets |= {x for x in (r.get("refs") or []) if isinstance(x, str)}
            for t in targets:
                acts.setdefault(t, []).append(
                    {"ts": r.get("ts", ""), "record": rec,
                     "until": r.get("defer_until"), "trigger": r.get("trigger")})

    # THE LAPSED DEFER WAS STRUCTURALLY INVISIBLE HERE — the interface probe's BREAK-4
    # against the account fold, and it landed on the one pane built to answer "what is
    # live versus what was merely banked". The teeth set deferred_until=None the moment
    # a defer expires, so `row.deferred` goes False and the row dropped out of this loop
    # entirely: a promise whose own date has passed is the PUREST case of banked-and-
    # never-returned-to, and it was the only case this pane could not see.
    # The account names them (lapsed_deferred, plus a lapse defect), so ask it.
    lapsed_ids: set[str] = set()
    try:
        from laplace.engine import wake as _wake
        _acct = _wake.account(ROOT)
        for _d in _acct.get("defects", []):
            if "lapse" in str(_d.get("defect", "")).lower():
                for _k in ("id", "target", "row_id"):
                    if isinstance(_d.get(_k), str):
                        lapsed_ids.add(_d[_k])
    except Exception:  # noqa: BLE001 - the account refusing is not this pane's crash
        lapsed_ids = set()

    # A PANE THAT SAYS FAIL MUST SHOW WHAT FAILED. The re-attack of 2026-08-25 reached
    # the retired BREAK-4 shape by a different road: one defer carrying a typo'd date
    # ("2026-13-45") makes wake treat it as a never-expiring condition and emit no lapse
    # defect, while the teeth skip the unparseable date and fall back to the older defer
    # and FAIL. The row then matched none of deferred/exempt/lapsed and fell out, so the
    # pane rendered teeth_verdict=FAIL with open_carried=0 — a verdict with an empty
    # body, which is the same unknown-collapse this pane exists to end. Anything the
    # teeth are FAILING on is admitted here whatever else it is or is not.
    failing_ids = {r.id for r in report.failing}
    rows = []
    for row in report.rows:
        lapsed = row.id in lapsed_ids
        failing = row.id in failing_ids
        if not (row.deferred or row.exempt_reason or lapsed or failing):
            continue
        ev = sorted(acts.get(row.id, []), key=lambda e: e["ts"])
        defers = [e for e in ev if e["record"] == "defer"]
        chain = [(e.get("trigger") and "condition") or e.get("until") or "?"
                 for e in defers]
        # a condition-defer is honest (it can fire); a date-defer is a promise to think
        # later. condition -> date is a REGRESSION, and nothing else notices it.
        regressed = any(chain[i] == "condition" and chain[i + 1] != "condition"
                        for i in range(len(chain) - 1))
        big = max((cohort.get((str(e["ts"])[:10], e.get("until")), 1) for e in defers),
                  default=1)
        rows.append({
            "id": row.id, "ledger": row.ledger, "cls": row.cls,
            "quiet_age": row.quiet_age, "deferred_until": row.deferred_until,
            "exempt": row.exempt_reason is not None,
            "lapsed": lapsed,
            "failing_the_teeth": failing,
            "touches": len(ev),
            "defers": len(defers), "defer_chain": chain,
            "adjudications": sum(1 for e in ev if e["record"] in _ADJUDICATES),
            "notes": sum(1 for e in ev if e["record"] in _COMMENTS),
            "max_cohort": big, "regressed": regressed,
        })
    rows.sort(key=lambda r: (-(r["quiet_age"] or 0), r["id"]))

    never = [r for r in rows if not r["adjudications"]]
    untouched = [r for r in never if not r["touches"]]
    loud = [r for r in never if r["touches"]]
    return {
        "source": "scripts/ledger_age_audit.py::audit() for the open/deferred/exempt "
                  "split (the same classifier the close gate runs), enriched from "
                  + ", ".join(_LIVENESS_STORES),
        "staleness": "recomputed on every board build; the teeth read the ledgers live, "
                     "so this pane is exactly as fresh as the rows",
        "teeth_verdict": "FAIL" if report.failed else "PASS",
        "judged_on": judged_on.isoformat(),
        "predicate": "adjudicated = a resolution/amendment/ruling/verdict/finding/undefer "
                     "names this row. defers and notes are NOT adjudications.",
        "residuals": malformed,
        "cracked": integrity["cracked"],
        "residual_count": integrity["residual_count"],
        "residuals_truncated": integrity["residuals_truncated"],
        "residuals_omitted": integrity["residuals_omitted"],
        "residual_handle": integrity["residual_handle"],
        "counts": {
            "open_carried": len(rows),
            "never_adjudicated": len(never),
            # These two are a partition. The first candidate ignored defers when
            # defining untouched, so a defer/no-note row appeared in BOTH buckets
            # while the prose called one "the other".
            "never_touched_at_all": len(untouched),
            "loud_but_undecided": len(loud),
            "regressed_defers": sum(1 for r in rows if r["regressed"]),
            "lapsed_defers": sum(1 for r in rows if r.get("lapsed")),
            "failing_the_teeth": sum(1 for r in rows if r.get("failing_the_teeth")),
            "swept_in_a_cohort": sum(1 for r in rows if r["max_cohort"] >= 5),
        },
        "rows": rows,
    }


def crutches_pane() -> dict:
    """WHAT IS PROPPED UP — the declared-shortcut ledger, on a surface for the first time.

    His question, 2026-08-25, on being told two crutches had retired: "If you've retired
    the crutch is that reflected?" It was not. corpus_friction/crutches.jsonl has 36 rows
    and appeared on no surface at all — a ledger whose entire purpose is to stop shortcuts
    banking silently was itself only readable by grep. A crutch nobody can see is exactly
    the thing the crutch law exists to prevent.

    THE ROW IS THE TRIGGER. A standing crutch without a retirement trigger is just debt;
    with one it is a bet with a settlement date. So the pane leads with the trigger, not
    the excuse — what has to become true for this prop to come out.

    Disposition is LAST-WINS BY ID in file order (the ledger's own stated rule), so a
    retirement supersedes its own banking rather than appending a contradiction.
    """
    store = ROOT / "corpus_friction" / "crutches.jsonl"
    by_id: dict[str, dict] = {}
    malformed = 0
    if store.is_file():
        for _n, line in enumerate(store.read_text(encoding="utf-8",
                                                  errors="replace").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                malformed += 1
                continue
            if r.get("record") == "crutch" and r.get("id"):
                by_id[r["id"]] = r

    standing, retired = [], []
    for r in by_id.values():
        row = {"id": r["id"], "what": (r.get("what") or "")[:300],
               "trigger": (r.get("retirement") or "")[:400],
               "must_become": (r.get("must_become") or "")[:300],
               "retired_by": (r.get("retired_by") or "")[:300],
               "date": r.get("date") or (r.get("ts") or "")[:10]}
        (retired if r.get("status") == "retired" else standing).append(row)
    standing.sort(key=lambda x: x["id"])
    retired.sort(key=lambda x: x["date"], reverse=True)

    no_trigger = [r["id"] for r in standing if not r["trigger"]]
    return {
        "source": "corpus_friction/crutches.jsonl (last-wins by id, the ledger's own rule)",
        "staleness": "recomputed on every board build; the ledger is append-only, so this "
                     "pane is exactly as fresh as the rows",
        "standing": standing, "retired": retired[:6],
        "counts": {"standing": len(standing), "retired": len(retired),
                   "without_trigger": len(no_trigger), "malformed": malformed},
        "without_trigger": no_trigger,
    }


def build() -> dict:
    health = health_pane()
    return {
        "board": "atlas",
        "produced_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
                       .replace("+00:00", "Z"),
        "law": "RENDER OF ROWS — stale the moment rows move; regenerate with "
               "python3 scripts/atlas_board.py; both registers from this one producer",
        "campaign": campaign_pane(),
        "inventory": inventory_pane(),
        "walk": walk_pane(),
        "bench": bench_pane(),
        "health": health,
        "observability": observability_pane(health),
        "liveness": liveness_pane(),
        "crutches": crutches_pane(),
        "live": live_pane(),
    }


STATUS_HUE = {"DONE": "#2e7d32", "DONE-PENDING-WALK": "#558b2f", "OPEN": "#8d6e63",
              "ABSORBED": "#546e7a", "BLOCKED-ON-AUTHOR": "#c62828", "UNRUN": "#9e9e9e"}
DISPO_HUE = {"RETIRED": "#b71c1c", "ABSORBED": "#37474f", "CARRIED": "#1b5e20",
             "HOLD-FOR-RULING": "#b34700", "HOLD-UNTIL-PROVEN": "#b34700",
             "QUARRY-EVIDENCE": "#4e342e", "DESIGNED-INHERITANCE": "#283593",
             "EVIDENCE-AND-GENERATOR-RULE-HOLD": "#b34700",
             "EVIDENCE-AND-EXPLICIT-DIAL-HOLD": "#b34700"}



ASK_SNIPPET = (
    '<script>(function(){"use strict";\n'
    '/* ask about a pane, from the pane. The question banks through /front/talk — the\n'
    '   same door the front door talks through, one act one producer — and carries an\n'
    '   `about` naming the section and its row-source, so the answering seat is not\n'
    '   guessing what he was looking at. */\n'
    'document.addEventListener("click",function(ev){\n'
    ' const b=ev.target.closest(".askbtn");if(!b)return;\n'
    ' const h=b.closest("h2");if(h.nextElementSibling&&h.nextElementSibling.className==="askbox")\n'
    '  {h.nextElementSibling.remove();return;}\n'
    ' const src=(function(n){while(n){if(n.classList&&n.classList.contains("src"))return n.textContent;n=n.nextElementSibling;}return "";})(h.nextElementSibling);\n'
    ' const box=document.createElement("div");box.className="askbox";\n'
    ' const ta=document.createElement("textarea");\n'
    ' ta.placeholder="what do you want to know about \\u201c"+b.dataset.ask+"\\u201d?";\n'
    ' const send=document.createElement("button");send.type="button";send.className="act";\n'
    ' send.textContent="ask";const echo=document.createElement("span");echo.className="stale";\n'
    ' send.addEventListener("click",async function(){\n'
    '  const text=ta.value.trim();if(!text){echo.textContent="say what you want to know";return;}\n'
    '  send.disabled=true;echo.textContent="banking\\u2026";\n'
    '  try{const r=await fetch("/front/talk",{method:"POST",\n'
    '    headers:{"Content-Type":"application/json","X-Front-Door":"1"},\n'
    '    body:JSON.stringify({text:text,about:("the atlas board \\u00b7 "+b.dataset.ask+\n'
    '      (src?" \\u00b7 "+src.slice(0,160):""))})});\n'
    '   const j=await r.json();\n'
    '   echo.textContent=r.ok?"asked \\u2014 a seat picks this up at its next round":\n'
    '     ("refused: "+(j.error||r.status));\n'
    '   if(r.ok){ta.disabled=true;}\n'
    '  }catch(e){echo.textContent="the talk door did not answer: "+e;send.disabled=false;}\n'
    ' });\n'
    ' box.appendChild(ta);box.appendChild(send);box.appendChild(echo);\n'
    ' h.parentNode.insertBefore(box,h.nextElementSibling);ta.focus();\n'
    '});})();</script>')

KEYS_SNIPPET = (
    '<script>(function(){"use strict";\n'
    '/* the same keys as the front door, derived from the same census — the keyboard\n'
    '   used to die at every page boundary: A opened this page and stranded you. */\n'
    'let P=null;fetch("/front/places").then(r=>r.json()).then(d=>{P=d.places;}).catch(()=>{});\n'
    'document.addEventListener("keydown",function(ev){\n'
    ' const t=ev.target;if(t&&(t.tagName==="INPUT"||t.tagName==="TEXTAREA"))return;\n'
    ' if(ev.metaKey||ev.ctrlKey||ev.altKey)return;\n'
    ' if(ev.key==="Escape"){location.href="/front";return;}\n'
    ' if(!P)return;\n'
    ' const p=P.find(x=>x.key&&x.key.toLowerCase()===ev.key.toLowerCase());\n'
    ' if(!p)return;\n'
    ' location.href=p.kind==="page"?p.href:"/front"+p.href;\n'
    '});})();</script>')

INSTRUMENT_SNIPPET = (
    '<script>(function(){"use strict";\n'
    'document.querySelectorAll("input.diffusion-dial").forEach(function(dial){\n'
    ' const box=dial.closest(".instrument");const series=JSON.parse(dial.dataset.series);\n'
    ' const paint=function(){const row=series[Number(dial.value)]||{};\n'
    '  box.querySelector(".dialvalue").textContent="t = "+row.t;\n'
    '  box.querySelectorAll("[data-metric]").forEach(function(cell){\n'
    '   const v=row[cell.dataset.metric];cell.textContent=(v===undefined?"?":Number(v).toFixed(4));\n'
    '  });\n'
    ' };dial.addEventListener("input",paint);paint();\n'
    '});})();</script>')


def render_html(b: dict, home: str | None = None, receipt: str = "") -> str:
    """The human register. ``home`` is the route back to the surface that sent the
    reader here (the front door passes ``/front``); ``None`` renders the standalone
    file, which has no server to return to. ``receipt`` is the serving layer's own
    freshness sentence — build() may be served from a drift-keyed cache, and a cache
    that cannot say so is stale-presented-as-live.

    NAVIGATION IS DERIVED, NEVER ASSERTED (the mechanism ego-seat made me name before
    I cured it): this producer emitted no ``<a>`` at all — its whole tag vocabulary was
    div/h2/code/b/span/br/td/summary/details/tr/table — while its own CSS declared
    ``a{color:#7fb3ff}``, styling links it could not produce. The cure is the mechanism:
    ``h2()`` is now the ONLY way a section heading enters the page, and it registers the
    section as it renders it. The index is built from that register, so an index entry
    cannot outlive, precede, or contradict its section.
    """
    sections: list[tuple[str, str]] = []

    def chip(text: str, hue: str) -> str:
        # one class, one custom property. The hue is the only thing that varied across
        # 1,087 of these; the other 55 characters were repeated verbatim every time.
        return f'<span class="t" style="--t:{hue}">{escape(text)}</span>'

    def src(s: str, standing: str = "live", *,
            renew: str = "python3 -m atlas.tools.pour_notes") -> str:
        """The row-source line, plus how the pane STANDS TO TIME.

        His challenge, 2026-08-25: "colour coding freshness is all well and good, but
        isn't the better solution simply to make sure everything is fresh?" Right — and
        measuring the panes showed a blanket age chip was the wrong instrument, because
        three different things were wearing it:

          live    recomputed on every build. The walk gate is EXECUTED here by
                  subprocess each render; the first cut aged scripts/atlas_s0_gate.py
                  and printed "20.3h old" beside a live computation — a false signal in
                  the worst direction, and mine. A live pane shows no age at all.
          held    frozen deliberately. The S0 inventory generation is the exact one his
                  walk ratifies; re-minting it would move what he is approving. It says
                  WHY it is held, not how old it is.
          receipt the banked output of an act that must be RE-RUN to refresh. Age is
                  real here and worth showing, WITH the act that renews it. (The first
                  cut of this line claimed "nothing in the tree regenerates it" — false,
                  and written before I had finished looking: atlas.tools.pour_notes
                  writes exactly this report. Asserting instead of deriving, on his
                  surface, in the same commit that was about honesty.)

        Age is derived from the first repo path the source names, so it cannot drift.
        """
        note = ""
        if standing == "held":
            note = ' <span class="held">held for your walk — refreshing it would move '\
                   'what you are approving</span>'
        elif standing == "receipt":
            for token in re.findall(r"[\w./-]+\.(?:jsonl|json)", s):
                path = ROOT / token
                if not path.is_file():
                    continue
                hours = (datetime.now(timezone.utc).timestamp()
                         - path.stat().st_mtime) / 3600
                cls = "old" if hours >= 18 else ""
                note = (f' <span class="age {cls}">banked {hours:.0f}h ago · renew it '
                        f'with <code>{escape(renew)}</code></span>')
                break
        return f'<div class="src">{escape(s)}{note}</div>'

    def h2(text: str, style: str = "") -> str:
        """Emit a section heading AND register it. Ids collide-suffix, never overwrite."""
        base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
        sid, n = base, 2
        while any(existing == sid for existing, _ in sections):
            sid, n = f"{base}-{n}", n + 1
        sections.append((sid, text))
        st = f' style="{style}"' if style else ""
        # ASK FROM HERE. His steer, 2026-08-25: "if there's anything like that, why
        # don't I have the option to address or query it from there?" Every section can
        # be questioned in place, and the question carries the section and its ground
        # so the seat that answers is not guessing what he was looking at.
        ask = (f'<button type="button" class="askbtn" data-ask="{escape(text)}">'
               f'ask about this</button>')
        return f'<h2 id="{sid}"{st}>{escape(text)}{ask}</h2>'

    head = ['<meta charset="utf-8"><title>the atlas board</title><style>',
            'body{background:#14161a;color:#d7dae0;font:14px/1.45 system-ui,sans-serif;'
            'margin:0;padding:18px 22px}',
            'h1{font-size:19px;margin:0 0 2px} h2{font-size:15px;margin:18px 0 6px;'
            'color:#9fb3c8} a{color:#7fb3ff}',
            '.src{color:#7d8a9b;font-size:11px;font-family:monospace;margin:2px 0 8px;max-width:78ch}',
            # age rides the source line: a pane that names its ground must name how old
            # that ground is, or a frozen receipt reads exactly like a live computation
            '.age{color:#b08a4a}',
            '.held{color:#7d8a9b}',
            '.age.old{color:#e06c50;font-weight:600}',
            # ask-from-the-pane: summonable, and quiet until summoned
            '.askbtn{margin-left:10px;font-size:10.5px;font-weight:400;color:#7d8a9b;'
            'background:none;border:1px solid #2b313b;border-radius:999px;'
            'padding:2px 9px;cursor:pointer;vertical-align:middle}',
            '.askbtn:hover{color:#e6eaf0;border-color:#4c6a9c}',
            '.askbox{margin:6px 0 10px;display:flex;gap:7px;align-items:flex-start;'
            'flex-wrap:wrap;max-width:78ch}',
            '.askbox textarea{flex:1 1 380px;min-height:52px;background:#101216;'
            'color:#d7dae0;border:1px solid #2b313b;border-radius:5px;padding:7px 9px;'
            'font:13px/1.45 system-ui,sans-serif}',
            '.askbox .act{min-height:32px;background:none;border:1px solid #2b313b;'
            'color:#d7dae0;border-radius:5px;padding:0 14px;cursor:pointer;'
            'font:600 11px/1 system-ui,sans-serif;letter-spacing:.05em;'
            'text-transform:uppercase}',
            '.askbox .act:hover{border-color:#4c6a9c}',
            '.grid{display:grid;grid-template-columns:1.5fr 1fr;gap:22px;align-items:start}',
            'details{margin:4px 0;border-left:2px solid #2b313b;padding-left:9px}',
            'summary{cursor:pointer;color:#c8d2dd} tr:hover td{background:rgba(232,230,225,.05)}'
            ' table{border-collapse:collapse;width:100%;'
            'margin:5px 0} td{border-bottom:1px solid #232830;padding:2px 7px;font-size:12.5px;'
            'vertical-align:top} code{color:#9ccc9c;font-size:12px}',
            '.t{background:var(--t);color:#fff;border-radius:3px;padding:1px 7px;'
            'font-size:12px;white-space:nowrap}',
            '.spine{display:flex;gap:7px;flex-wrap:wrap;margin:9px 0 3px}',
            '.stale,.why,.chainrow{max-width:78ch}',
            '.walk{background:#1b2026;border:1px solid #33528a;border-radius:6px;'
            'padding:11px 14px} .stale{color:#b08a4a;font-size:11.5px}',
            # the chrome: this page is ~218KB of one column — the reader must be able to
            # leave it, and to reach any section, from wherever they have scrolled to.
            '.chrome{position:sticky;top:0;z-index:9;background:rgba(20,22,26,.94);'
            'backdrop-filter:blur(6px);border-bottom:1px solid #2b313b;'
            'margin:-18px -22px 15px;padding:9px 22px 10px}',
            '.chrome .home{color:#7fb3ff;text-decoration:none;font-weight:600}',
            '.chrome .home:hover{text-decoration:underline}',
            '.chrome .away{color:#7d8a9b;font-size:12px}',
            '.toc{margin-top:7px;display:flex;gap:6px;flex-wrap:wrap}',
            '.toc a{font-size:11.5px;color:#9fb3c8;text-decoration:none;background:#1a1e24;'
            'border:1px solid #2b313b;border-radius:999px;padding:2px 10px}',
            '.toc a:hover{color:#e6eaf0;border-color:#4c6a9c;background:#20262e}',
            # anchors must not land under the sticky bar
            'h2{scroll-margin-top:132px}',
            # --- the liveness field: 2-D on purpose. A list sorts on ONE axis; these
            # rows are dangerous on two (old AND loud AND never decided), so the quadrant
            # shows in one glance what no ordering can.
            '.field{position:relative;height:190px;margin:11px 0 6px;border-left:1px solid '
            '#2b313b;border-bottom:1px solid #2b313b;background:'
            'linear-gradient(135deg,transparent 55%,rgba(160,54,38,.13) 100%)}',
            '.dot{position:absolute;width:9px;height:9px;border-radius:50%;margin:-4px;'
            'background:#a03626;border:1px solid #d4744f;cursor:help}',
            '.dot[data-adj]:not([data-adj="0"]){background:#2e7d32;border-color:#7fc27f}',
            '.ax{position:absolute;font-size:11px;color:#7d8a9b;letter-spacing:.04em}',
            '.ax-x{bottom:-15px;right:0} .ax-y{top:-2px;left:3px}',
            '.ax.danger{top:6px;right:6px;color:#c2705a}',
            # the predicate is HIS to set: whether a note counts as "returning to it"
            # moves the answer from 33 rows to 2. CSS-only — no script, no tollbooth.
            '.pred{display:none}',
            '.predlab{display:inline-block;font-size:11.5px;color:#9fb3c8;cursor:pointer;'
            'border:1px solid #2b313b;border-radius:999px;padding:2px 10px;'
            'background:#1a1e24;margin:2px 0 4px}',
            '.pred:checked+.predlab{color:#e6eaf0;border-color:#4c6a9c;background:#20262e}',
            '.pred:checked~.field .dot[data-n]:not([data-n="0"])'
            '{background:#2e7d32;border-color:#7fc27f}',
            '.pred:checked~.lrows .lrow[data-n]:not([data-n="0"]) .stale{color:#7f9c7f}',
            '.lrows{margin-top:8px} .lrow{padding:4px 0;border-bottom:1px solid #1e232a}',
            '.chainrow{font-size:11.5px;color:#8d99a8;margin-top:2px;font-family:monospace}',
            '.why{color:#98a2b0;font-size:12.5px;margin:3px 0}',
            '.plane{border:1px solid #2b313b;border-radius:6px;padding:10px 12px;'
            'margin:8px 0;max-width:86ch}',
            '.scope{color:#e0a35b;font-size:11.5px;border-left:2px solid #8a5d2d;'
            'padding-left:8px;margin:7px 0}',
            '.instrument{border:1px solid #36506f;border-radius:6px;padding:10px 12px;'
            'margin:8px 0;max-width:86ch;background:rgba(54,80,111,.08)}',
            '.diffusion-dial{width:min(520px,80vw);vertical-align:middle;accent-color:#7fb3ff}',
            '.dialvalue{display:inline-block;min-width:60px;margin-left:9px;color:#9ccc9c;'
            'font-family:monospace}',
            # the trigger is the point of a crutch row — it reads as a condition, not prose
            '.trigger{font-size:12.5px;color:#c8d2dd;margin:4px 0;border-left:2px solid '
            '#5d7a3a;padding-left:9px;background:rgba(93,122,58,.08)}'
            '</style>']
    o = [f"<h1>the atlas board</h1><div class='stale'>{escape(b['law'])} · "
         f"produced {b['produced_at']}</div>"]

    c = b["campaign"]
    o.append(h2("the campaign spine") + src(c["source"]))
    o.append('<div class="spine">')
    for s in c["stages"]:
        hue = STATUS_HUE.get(s["status"], "#616161")
        star = " ◀ next" if s["id"] == c.get("next_act") else ""
        o.append(chip(f'{s["id"]} · {s["status"]}{star}', hue))
    o.append("</div>")
    for s in c["stages"]:
        # The stage TITLE opens the fold and the id trails it in the demoted register:
        # the id is still on the page (it is the join back to the chip above) but it no
        # longer decides whether a reader opens the fold.
        o.append(f'<details><summary title="{escape(s["id"])}">{escape(s["title"])}'
                 f' <span class="stale">{escape(s["id"])}</span></summary>'
                 f'<div style="color:#98a2b0;font-size:12.5px">{escape(s["why"])}</div></details>')

    inv = b["inventory"]
    o.append(h2(f"the S0 disposition panel — {inv['total_rows']} rows, one bulk act")
             + src(inv["source"], "held"))
    for cls, data in sorted(inv["classes"].items()):
        chips = " ".join(chip(f"{d} {n}", DISPO_HUE.get(d, "#616161"))
                         for d, n in sorted(data["by_disposition"].items(),
                                            key=lambda kv: DISPO_ORDER.index(kv[0])
                                            if kv[0] in DISPO_ORDER else 99))
        o.append(f"<details><summary><b>{escape(cls)}</b> · {data['count']} {chips}</summary>"
                 "<table>")
        # FACE FIRST, HANDLE SUMMONABLE — see _face(). What led here before was the raw
        # item token, which for 227 of these 466 rows is a dated slug. The reading order
        # is now face → why it is disposed that way → the machine line (item handle and
        # its ground paths), with the INV-* row id in title= where it can be summoned
        # and cannot compete for the reader's first look.
        for r in data["rows"]:
            mode = f' <code>{escape(r["mode"])}</code>' if r.get("mode") else ""
            hue = DISPO_HUE.get(r["disposition"], "#616161")
            face, handle = _face(str(r["item"]))
            ground = "; ".join(map(str, r["ground"]))[:130]
            mech = ground if face == handle else f"{handle} ⇢ {ground}"
            o.append(f"<tr><td>{chip(r['disposition'], hue)}{mode}</td>"
                     f'<td><b title="{escape(handle)}">{escape(face[:90])}</b><br>'
                     f"<span style='color:#8d99a8'>{escape(r['why'][:220])}</span><br>"
                     f'<code title="{escape(str(r["id"]))}">{escape(mech)}</code>'
                     f"</td></tr>")
        o.append("</table></details>")

    w = b["walk"]
    o.append('<div class="walk">' + h2("the walk — yours alone", "margin-top:0")
             + src(w["source"]))
    if w.get("gate_verdict"):
        o.append(f"<div>gate: <b>{escape(str(w['gate_verdict']))}</b>"
                 + (f" · residuals: {escape('; '.join(map(str, w['gate_residuals'])))}"
                    if w.get("gate_residuals") else " · residuals: none") + "</div>")
    if w.get("gate_note"):
        o.append(f"<div class='stale'>{escape(w['gate_note'])}</div>")
    if w["judged_row"]:
        o.append(f"<div>judged ✓ <code>{escape(str(w['judged_row'].get('id')))}</code> "
                 f"<span style='color:#8d99a8'>{escape(str(w['judged_row'].get('ts') or ''))}"
                 f"</span></div>")
    mg = w.get("migration", {})
    if mg.get("status") == "REPLAYED":
        o.append("<div style='margin-top:6px'>canonical migration axes: "
                 + " ".join(chip(f"{k} {'✓' if mg.get(k) else '—'}",
                                 "#2e7d32" if mg.get(k) else "#616161")
                            for k in ("material", "judged", "walked"))
                 + f" <code>r{mg.get('revision')}</code></div>")
    else:
        o.append(f"<div class='stale'>migration replay: {escape(str(mg.get('status')))}</div>")
    o.append(f"<div style='margin-top:7px'>{escape(w['the_walk_is_his'])}</div>")
    o.append(f"<div style='margin-top:7px'><b>the one command</b>:<br>"
             f"<code style='color:#ffd54f'>{escape(w['author_command'])}</code></div></div>")

    # ---------------------------------------------------------- bench / health / eyes
    # These are RECEIPTS ON THE WALK, not new computations hidden in a GET. The reader
    # sees the demand field, the current reconstruction result, the storage measurement's
    # explicit non-authorizing scope, the health rows and the first instrument-class view.
    bp = b["bench"]
    paths = bp["source_paths"]
    o.append(h2("the S0 bench — demand, recall, storage"))
    o.append(src(paths["demand"], "receipt", renew=(
        "/usr/bin/python3 evidence/ATLAS_BENCH_2026-08-24/demand_inventory.py")))
    o.append(src(paths["recall"], "receipt",
                 renew="/usr/bin/python3 -m atlas.tools.pour_notes"))
    o.append(src(paths["storage"], "receipt", renew=(
        "mint a separate non-authorizing measurement receipt under future_receipt_rule")))
    o.append(f'<div class="stale">{escape(bp["staleness"])}</div>')
    for err in bp.get("errors", []):
        o.append(f'<div class="stale">RECEIPT RED — {escape(str(err))}</div>')
    demand = bp["demand"]
    o.append(f'<div class="plane"><b>demand coverage</b> · '
             f'<b>{escape(str(demand.get("queries_total")))}</b> real queries · '
             f'{escape(str(demand.get("aspect_classes_total")))} aspect classes · '
             f'{escape(str(demand.get("queries_unresolved_provenance")))} unresolved '
             f'provenance · banked {escape(str(demand.get("generated_at")))}</div>')
    o.append("<table><tr><td><b>aspect</b></td><td><b>demand</b></td>"
             "<td><b>measured coverage</b></td></tr>")
    for aspect in demand.get("aspects", []):
        hint = str(aspect.get("coverage_hint") or "unmeasured").upper()
        hue = "#a03626" if hint == "RED" else "#2e7d32" if hint == "GREEN" else "#616161"
        o.append(f'<tr><td>{escape(str(aspect.get("aspect_class")))}</td>'
                 f'<td>{escape(str(aspect.get("count")))}</td>'
                 f'<td>{chip(hint, hue)} {escape(str(aspect.get("measured_fraction") or ""))}'
                 f'<br><span class="stale">{escape(str(aspect.get("coverage_basis") or ""))}'
                 f'</span></td></tr>')
    o.append("</table>")
    recall = bp["recall"]
    o.append(f'<div class="plane"><b>reconstruction receipt</b> · generation '
             f'<code>{escape(str(recall.get("generation")))}</code> · '
             f'hit@1 <b>{escape(str(recall.get("descent_hit_at_1")))}</b>/'
             f'{escape(str(recall.get("probes")))} · hit@3 '
             f'<b>{escape(str(recall.get("descent_hit_at_3")))}</b>/'
             f'{escape(str(recall.get("probes")))} · encoder '
             f'<code>{escape(str(recall.get("encoder")))}</code>')
    for miss in recall.get("historic_misses_reasked", []):
        o.append(f'<div style="color:#9ccc9c">historic miss re-asked → rank '
                 f'{escape(str(miss.get("descent_rank")))} · '
                 f'{escape(str(miss.get("query")))}</div>')
    o.append(f'<div class="stale">{escape(str(recall.get("scale_posture") or ""))}</div>'
             '</div>')
    storage = bp["storage"]
    eq = storage.get("equivalence", {})
    o.append(f'<div class="plane"><b>storage morphology receipt</b> · observed '
             f'{escape(str(storage.get("observed_at")))} · '
             f'{escape(str(storage.get("source_events")))} events · source '
             f'{escape(str(storage.get("source_bytes")))} B → candidate '
             f'{escape(str(storage.get("tree_allocated_bytes")))} B · compact ledger '
             f'{escape(str(storage.get("thin_ledger_bytes")))} B · event hives '
             f'{escape(str(storage.get("event_hive_logical_bytes")))} B · rebuildable index '
             f'{escape(str(storage.get("derived_index_bytes")))} B<br>'
             f'equivalence: material {escape(str(eq.get("materialized_state_equal")))} · '
             f'head {escape(str(eq.get("head_event_id_preserved")))} · '
             f'event count {escape(str(eq.get("event_count_preserved")))} · '
             f'reachability {escape(str(eq.get("reachability_status")))} · production mutated '
             f'{escape(str(storage.get("production_mutated")))}')
    scope = storage.get("measurement_scope", {})
    o.append(f'<div class="scope"><b>NON-AUTHORIZING MEASUREMENT</b> — '
             f'{escape(str(scope.get("reason") or "scope receipt absent"))}</div></div>')

    hp = b["health"]
    o.append(h2("system health — verdicts, budget, in-flight") + src(hp["source"]))
    o.append(f'<div class="stale">{escape(hp["staleness"])}</div>')
    for err in hp.get("errors", []):
        o.append(f'<div class="stale">HEALTH RESIDUAL — {escape(str(err))}</div>')
    verdicts = hp.get("verdicts", {})
    stranger = verdicts.get("stranger_bench", {})
    census = verdicts.get("census", {})

    # SYNTH-20260825-the-unknown-collapses, at the RENDER boundary. The rows below carry
    # every state by name; a pane that shows only the rollup re-commits the collapse the
    # fold was cured of. THREE axes are kept apart deliberately:
    #   EXISTENCE (ABSENT / UNREAD)  - "is there a run to report at all"
    #   FRESHNESS (STALE / FRESH)    - "have the stores moved since this ran"
    #   VERDICT   (the counts)       - "what did the run actually find"
    # One red chip doing both of the last two is why a passing-but-stale bench read as a
    # failing one. Collapsing the FIRST into the second is the defect measured 2026-08-25:
    # wake.banked_verdicts_with_age emits a bare {"status": "RED", "absent": "<file> does
    # not exist yet"} for a run that never happened, and this render mapped that RED onto
    # STALE plus the sentence "stores moved since this ran" — so a stranger-bench that had
    # never been run, or whose store was unreadable, reported to him as "ran a while ago".
    # The producer's own `absent` string had two writers here and no reader anywhere.
    def standing(block: dict) -> str:
        status = str(block.get("status") or "")
        absent = block.get("absent")
        if absent:
            return (chip("ABSENT", "#a03626")
                    + f'<span class="stale"> — {escape(str(absent))}; there is no run to '
                      'be fresh or stale about</span>')
        if status == "RED":
            return (chip("ABSENT", "#a03626")
                    + '<span class="stale"> — the verdict reader returned RED without '
                      'naming a cause; unknown, never a passing run</span>')
        if not status:
            return (chip("UNREAD", "#a03626")
                    + '<span class="stale"> — no status reached this render; unknown, '
                      'never a passing run</span>')
        if "STALE" in status:
            return (chip("STALE", "#8a6d1f")
                    + '<span class="stale"> — stores moved since this ran; a freshness '
                      'axis, not a verdict</span>')
        return chip("FRESH", "#2e7d32")

    def ran(block: dict) -> str:
        """Absence has no run date. Printing "ran ?" beside an ABSENT chip re-opens the
        same hole one column over."""
        return f'ran {escape(str(block["ran"]))} · ' if block.get("ran") else ""

    # The whole layer can fail as one — health_pane() banks {"absent": ...} when
    # wake.banked_verdicts_with_age raises. Every per-plane .get() below then reads {},
    # which is exactly the shape that used to paint FRESH.
    if verdicts.get("absent"):
        o.append(f'<div class="plane">{chip("VERDICT LAYER ABSENT", "#a03626")} '
                 f'<span class="stale">{escape(str(verdicts["absent"]))} — every verdict '
                 f'below is unknown, not passing</span></div>')

    checks = stranger.get("checks", {}) or {}
    probes = stranger.get("probes", {}) or {}
    judge = stranger.get("judge", {}) or {}
    o.append('<div class="plane">'
             f'<b>stranger bench</b> · {ran(stranger)}{standing(stranger)}')
    if checks:
        o.append(f'<div class="chainrow">checks · {escape(str(checks.get("total", "?")))} total · '
                 f'{chip(str(checks.get("pass", "?")) + " PASS", "#2e7d32")} '
                 f'{chip(str(checks.get("fail", "?")) + " FAIL", "#a03626")} '
                 f'{chip(str(checks.get("awaiting_judge", "?")) + " AWAITING-JUDGE", "#8a6d1f")} '
                 f'{chip(str(checks.get("not_recorded", "?")) + " NOT-RECORDED", "#5c5c5c")}'
                 '<span class="stale"> — AWAITING-JUDGE is UNJUDGED, not failed. The one '
                 'number that is a failure count is FAIL.</span></div>')
    if probes:
        o.append('<div class="chainrow">probes · ' + " · ".join(
            f'{escape(k)} {escape(str(v))}'
            for k, v in (probes.get("states") or {}).items()) + '</div>')
    if judge.get("probes_graded"):
        o.append(f'<div class="chainrow">the judge graded {escape(str(judge["probes_graded"]))} '
                 f'probe(s) in {escape(", ".join(map(str, judge.get("runs", []))) or "?")} · '
                 + " · ".join(f'{escape(k)} {escape(str(v))}'
                              for k, v in (judge.get("verdicts") or {}).items())
                 + '<span class="stale"> — a SEPARATE act from the self-run above and not '
                   'merged into it; a self-run cannot resolve an AWAITING-JUDGE check.'
                   '</span></div>')
    o.append('</div>')

    obs = census.get("observation", {}) or {}
    unobserved = census.get("unobserved", {}) or {}
    o.append('<div class="plane">'
             f'<b>census</b> · {ran(census)}{standing(census)}')
    # An absent census has no observation to enumerate. Rendering the counts row anyway
    # printed "? organs · dead none" — absence dressed as a clean run, the exact defect
    # class this pane was rebuilt to end.
    if census.get("verdicts") or census.get("organs") is not None:
        o.append(f'<div class="chainrow">this observation · '
                 f'{escape(str(census.get("organs", "?")))} organs · '
                 + " ".join(chip(f'{n} {v}', "#2e7d32" if v == "FUNCTIONAL" else "#a03626")
                            for v, n in sorted((census.get("verdicts") or {}).items()))
                 + f' · dead {escape(", ".join(map(str, census.get("dead", []))) or "none")}'
                 '</div>')
    if unobserved:
        o.append('<div class="chainrow">not observed in this run · ' + " · ".join(
            f'<code>{escape(o_)}</code> last {escape(str(b.get("last_verdict")))} '
            f'{escape(str(b.get("age_hours")))}h ago'
            for o_, b in unobserved.items())
            + '<span class="stale"> — UNOBSERVED: neither functional nor dead. Folding '
              'these into the run above is how a fixture last seen DEAD two days earlier '
              'was served as this run\'s dead organ.</span></div>')
    if obs:
        o.append(f'<div class="stale">observation scope · {escape(str(obs.get("rows_in_window", "?")))} '
                 f'of {escape(str(obs.get("rows_total", "?")))} rows, within '
                 f'{escape(str(obs.get("window_seconds", "?")))}s of the newest · CRUTCH '
                 f'{escape(str(obs.get("crutch", "—")))}: the census store carries no run '
                 f'id, so the run boundary is inferred from time. Retires when census '
                 f'generation stamps one.</div>')
    if census.get("organs_ever") not in (None, census.get("organs")):
        o.append(f'<div class="stale">{escape(str(census.get("organs_ever")))} organs have '
                 f'ever been recorded in this store — provenance, beside the count, never '
                 f'inside it.</div>')
    o.append('</div>')
    wb = hp["wake_budget"]
    o.append(f'<div class="plane"><b>wake budget</b> · latest banked '
             f'{escape(str(wb.get("latest_banked_seconds")))}s / '
             f'{escape(str(wb.get("bar_seconds")))}s · '
             f'{chip(str(wb.get("latest_banked_status") or "ABSENT"), "#2e7d32" if wb.get("latest_banked_status") == "PASS" else "#a03626")} '
             f'· {escape(str(wb.get("latest_banked_at")))} · '
             f'<span class="stale">{escape(str(wb.get("detail") or ""))}</span></div>')
    flight = hp.get("in_flight", {})
    acts = flight.get("acts", {})
    if flight.get("absent"):
        # health_pane() banks {"absent": ...} when journal.recover raises. len({}) is 0,
        # so a journal that could not be read rendered "0 in flight" — the strongest
        # possible reassurance produced by the total absence of evidence.
        o.append(f'<div class="plane"><b>recovered journal</b> · '
                 f'{chip("ABSENT", "#a03626")} '
                 f'<span class="stale">{escape(str(flight["absent"]))} — in-flight acts '
                 f'are UNKNOWN here, never zero</span></div>')
    else:
        o.append(f'<div class="plane"><b>recovered journal</b> · '
                 f'{escape(str(flight.get("acts_total", "?")))} acts · '
                 f'{len(acts)} in flight · last durable write '
                 f'{escape(str(flight.get("last_durable_write", "?")))}')
        for act_id, act in acts.items():
            # the act's own name leads; the journal key is the machine register
            o.append(f'<div class="chainrow" title="{escape(act_id)}">'
                     f'{escape(str(act.get("act")))} · began {escape(str(act.get("began")))} · '
                     f'killed {escape(", ".join(map(str, act.get("killed_mid_step", []))) or "none")}'
                     '</div>')
        o.append('</div>')

    obs = b["observability"]
    o.append(h2("observability — organ health and instruments"))
    o.append(src(obs["source_paths"]["organ_health"]))
    renew = next((str(row.get("renew")) for row in obs.get("instruments", [])
                  if row.get("renew")), "(no registered renewal act)")
    o.append(src(obs["source_paths"]["instrument"], "receipt", renew=renew))
    o.append(f'<div class="stale">{escape(obs["staleness"])}</div>')
    for err in obs.get("errors", []):
        o.append(f'<div class="stale">INSTRUMENT RED — {escape(str(err))}</div>')
    for instrument in obs.get("instruments", []):
        series = instrument.get("series", [])
        current = instrument.get("status") == "CURRENT"
        o.append(f'<div class="instrument"><b>{escape(str(instrument.get("class")))}</b> · '
                 f'<b>{escape(str(instrument.get("instrument")))}</b> '
                 f'{chip(str(instrument.get("status")), "#2e7d32" if current else "#a03626")} '
                 f'· generation '
                 f'<code>{escape(str(instrument.get("generation")))}</code><br>'
                 f'<span class="stale">receipt content handle '
                 f'<code>{escape(str(instrument.get("receipt_content_handle")))}</code> · '
                 f'custody {escape(str((instrument.get("custody") or {}).get("status")))} · '
                 f'census <code>{escape(str((instrument.get("census") or {}).get("organ")))}</code> '
                 f'{escape(str((instrument.get("census") or {}).get("status")))}</span><br>'
                 f'<b>reader</b> — {escape(str(instrument.get("reader")))}<br>'
                 f'<b>preimage</b> — {escape(" · ".join(map(str, instrument.get("preimage", []))))}<br>'
                 f'<b>retirement</b> — {escape(str(instrument.get("retirement")))}<br>'
                 f'<b>DECLARED dial</b> — {escape(str(instrument.get("dial")))} ∈ '
                 f'{escape(str(instrument.get("dial_values")))}<br>'
                 f'<b>{escape(str(instrument.get("channel_class")))}</b> channels — '
                 f'{escape(" · ".join(map(str, instrument.get("derived_channels", []))))}<br>'
                 f'<span class="stale">{escape(str(instrument.get("operator", {}).get("kind")))} '
                 f'· {escape(str(instrument.get("graph", {}).get("kind")))} · '
                 f'{escape(str(instrument.get("solver", {}).get("kind")))}</span><br>'
                 f'<span class="stale">fidelity preview↔real ARI '
                 f'{escape(str(instrument.get("fidelity_preview_vs_real_ari")))} at k_sub '
                 f'{escape(str(instrument.get("fidelity_k_sub")))} · eigenvalues head '
                 f'{escape(str(instrument.get("eigenvalues_head")))}</span>')
        for row in instrument.get("inputs", []):
            hue = "#2e7d32" if row.get("status") == "PASS" else "#a03626"
            o.append(f'<div class="chainrow">{chip(str(row.get("status")), hue)} '
                     f'<code>{escape(str(row.get("path")))}</code> · '
                     f'{escape(str(row.get("observed") or "ABSENT"))}</div>')
        if series:
            first = series[0]
            maximum = max(0, len(series) - 1)
            data = escape(json.dumps(series, separators=(",", ":")), quote=True)
            o.append(f'<input class="diffusion-dial" type="range" min="0" max="{maximum}" '
                     f'step="1" value="0" data-series="{data}">'
                     f'<span class="dialvalue">t = {escape(str(first.get("t")))}</span>'
                     '<table><tr><td>legacy sha slices g1</td>'
                     f'<td data-metric="legacy_sha_slices_g1">{float(first.get("legacy_sha_slices_g1", 0)):.4f}</td></tr>'
                     '<tr><td>candidate spectral preview k114</td>'
                     f'<td data-metric="codex_spectral_preview_k114">{float(first.get("codex_spectral_preview_k114", 0)):.4f}</td></tr>'
                     '<tr><td>intrinsic k-means k114</td>'
                     f'<td data-metric="intrinsic_kmeans_k114">{float(first.get("intrinsic_kmeans_k114", 0)):.4f}</td></tr>'
                     '<tr><td>intrinsic k-means k12</td>'
                     f'<td data-metric="intrinsic_kmeans_k12">{float(first.get("intrinsic_kmeans_k12", 0)):.4f}</td></tr></table>')
        else:
            o.append('<div class="stale">no valid banked samples</div>')
        o.append(f'<div class="scope"><b>NON-CLAIM</b> — '
                 f'{escape(str(instrument.get("non_claim")))}</div></div>')

    # ---------------------------------------------------------------- liveness
    # His question, verbatim: "when all these orders accumulate I can't tell what's live
    # and necessary versus what was simply banked and never returned to."
    # The picture answers it in one glance BECAUSE it is 2-D: a list sorts on one axis,
    # and the dangerous rows are dangerous on two — old AND loud AND never decided. The
    # predicate toggle is CSS-only (a checkbox + sibling selectors, no script, no
    # tollbooth): he sets whether a note counts as "returning to it" and watches the
    # field re-partition, rather than trusting one fused number.
    ln_ = b["liveness"]
    cn = ln_["counts"]
    o.append(h2("what is live — and what was only ever banked"))
    o.append(src(ln_["source"]))
    o.append(f'<div class="stale">{escape(ln_["staleness"])}</div>')
    # THE COUNT IS THE TRUE COUNT, NEVER THE LENGTH OF THE SAMPLE. Commit 4b6fb7c6 replaced
    # the unbounded residual list with integrity_projection(cap=24) — correctly, a poisoned
    # store must not be able to blow up this page — and added residual_count beside it. This
    # sentence went on printing len(residuals). Measured against a 10,001-row poisoning
    # shape: true malformed 10001, payload residual_count 10001, printed 24 — a 416x
    # under-report standing directly beside the promise that "its counts are not presented
    # as complete", which reads as an assurance that the COUNTS are the honest part.
    # src/laplace/front_places.py:190 projects the same wound and reports residual_count;
    # this matches it. Gate on the COUNT, not the sample — a cap of 0 would otherwise hide
    # the whole wound, which is the same bug one step further along.
    if ln_.get("residual_count"):
        shown, omitted = len(ln_.get("residuals") or []), ln_.get("residuals_omitted") or 0
        o.append(f'<div class="stale">PARSE RESIDUAL — '
                 f'<b>{escape(str(ln_["residual_count"]))}</b> malformed completed row(s); '
                 f'the usable projection is shown, but its counts are not presented as '
                 f'complete. {shown} listed in the payload'
                 + (f', {escape(str(omitted))} omitted by the surface cap'
                    if omitted else '')
                 + (' · sample truncated' if ln_.get("residuals_truncated") else '')
                 + f' · full-set handle <code>{escape(str(ln_.get("residual_handle")))}'
                   f'</code></div>')
    # A FAIL IS NOT PAINTED GREEN. teeth_verdict is set to "FAIL" if report.failed, and this
    # line hardcoded #8bc34a on it while every other verdict on the board picks its hue from
    # the value — so a reader scanning by colour read a failing aging-teeth gate as passing.
    teeth_pass = ln_["teeth_verdict"] == "PASS"
    o.append(
        f'<div style="margin:7px 0 9px">the aging teeth say '
        f'<b style="color:{"#8bc34a" if teeth_pass else "#e06c50"}">'
        f'{escape(ln_["teeth_verdict"])}</b> '
        f'<span class="stale">judged against {escape(str(ln_.get("judged_on", "?")))}</span>'
        + ('' if teeth_pass else
           f' on <b>{cn["failing_the_teeth"]}</b> row(s), each admitted in the field below')
        + f' — a verdict on whether '
        f'a row carries a dated defer with an owner, never on whether '
        f'anyone returned to it. Of <b>{cn["open_carried"]}</b> carried rows, '
        f'<b style="color:#e06c50">{cn["never_adjudicated"]}</b> have never been '
        f'adjudicated; only <b>{cn["never_touched_at_all"]}</b> were never touched at all. '
        f'The other <b>{cn["loud_but_undecided"]}</b> are camouflaged by the noise made '
        f'around them. <b>{cn["swept_in_a_cohort"]}</b> were deferred in a cohort '
        f'(one date, one act, many rows — a sweep, not a judgement) and '
        f'<b>{cn["regressed_defers"]}</b> regressed from a condition back to a date.</div>')
    o.append(f'<div class="src">predicate · {escape(ln_["predicate"])}</div>')

    o.append('<input type="checkbox" id="notescount" class="pred"><label for="notescount" '
             'class="predlab">count a note as returning to it — re-partitions the field'
             '</label>')

    rows_ = ln_["rows"]
    maxq = max((r["quiet_age"] or 0) for r in rows_) or 1
    maxa = max((r["notes"] + r["defers"]) for r in rows_) or 1
    dots = []
    for r in rows_:
        x = 100.0 * (r["quiet_age"] or 0) / maxq
        y = 100.0 * (r["notes"] + r["defers"]) / maxa
        dots.append(
            f'<i class="dot" data-adj="{r["adjudications"]}" data-n="{r["notes"]}" '
            f'style="left:{x:.1f}%;bottom:{y:.1f}%" '
            f'title="{escape(r["id"])} · {r["quiet_age"]}d quiet · {r["defers"]} defers · '
            f'{r["adjudications"]} adjudications · {r["notes"]} notes"></i>')
    o.append('<div class="field">' + "".join(dots)
             + '<span class="ax ax-x">quiet age →</span>'
             + '<span class="ax ax-y">activity →</span>'
             + '<span class="ax danger">old · loud · never decided</span></div>')

    o.append('<div class="lrows">')
    for r in rows_[:18]:
        chain = ""
        if r["defer_chain"]:
            links = " → ".join(
                '<b style="color:#8bc34a">condition</b>' if c == "condition"
                else escape(str(c)) for c in r["defer_chain"])
            chain = (f'<div class="chainrow">deferred {r["defers"]}× · {links}'
                     + (' <b style="color:#e06c50">↓ regressed to a date</b>'
                        if r["regressed"] else "") + '</div>')
        badge = (chip(f'{r["adjudications"]} adjudicated', "#2e7d32")
                 if r["adjudications"] else chip("never adjudicated", "#a03626"))
        if r.get("lapsed"):
            # its own date has passed: not deferred any more, just open and unowned
            badge += " " + chip("its defer date has passed", "#a03626")
        cohort = (chip(f'swept with {r["max_cohort"]}', "#5d4037")
                  if r["max_cohort"] >= 5 else "")
        # the row's authored slug leads; the full dated id is summonable on hover
        face, handle = _face(r["id"])
        o.append(f'<div class="lrow" data-adj="{r["adjudications"]}" data-n="{r["notes"]}" '
                 f'title="{escape(handle)}">'
                 f'<b>{escape(face[:52])}</b> {badge} {cohort} '
                 f'<span class="stale">{r["quiet_age"]}d quiet · {r["notes"]} notes</span>'
                 f'{chain}</div>')
    if len(rows_) > 18:
        o.append(f'<div class="stale">… +{len(rows_) - 18} more carried rows '
                 f'(descend: the payload register, /front/atlas?format=json)</div>')
    o.append("</div>")

    # ---------------------------------------------------------------- crutches
    # "If you've retired the crutch is that reflected?" — it was not. 36 rows whose whole
    # purpose is to stop shortcuts banking silently, and the ledger itself was invisible.
    # The TRIGGER leads, not the excuse: a standing crutch is a bet with a settlement
    # condition, and the only question worth putting in front of him is what has to become
    # true for the prop to come out.
    cr = b["crutches"]
    cc = cr["counts"]
    o.append(h2("what is propped up — the declared shortcuts"))
    o.append(src(cr["source"]))
    o.append(f'<div style="margin:6px 0 9px"><b>{cc["standing"]}</b> standing · '
             f'<b>{cc["retired"]}</b> retired · '
             + (f'<b style="color:#e06c50">{cc["without_trigger"]}</b> with NO retirement '
                f'trigger (debt, not a bet)' if cc["without_trigger"]
                else 'every standing crutch names what would retire it')
             + (f' · <b style="color:#e06c50">{cc["malformed"]}</b> malformed row(s)'
                if cc["malformed"] else "") + '</div>')
    # THE FOLD HEADER IS A SENTENCE, NOT A KEY. Every one of these summaries was a bare
    # CR-* id: a reader deciding whether to open 30 folds had 30 slugs to choose from and
    # no way to tell which prop mattered. The crutch's own first clause is the header now,
    # with the id trailing in the demoted register and repeated in title=.
    for r in cr["standing"]:
        o.append(f'<details><summary title="{escape(r["id"])}">'
                 f'{escape(_first_clause(r["what"]) or _face(r["id"])[0])}'
                 f' <span class="stale">{escape(r["id"])}</span>'
                 + (" " + chip("no trigger", "#a03626") if not r["trigger"] else "")
                 + f'</summary><div class="why">{escape(r["what"])}</div>'
                 + (f'<div class="trigger"><b>retires when:</b> {escape(r["trigger"])}</div>'
                    if r["trigger"] else "")
                 + (f'<div class="why" style="color:#7f8c9b"><b>must become:</b> '
                    f'{escape(r["must_become"])}</div>' if r["must_become"] else "")
                 + '</details>')
    if cr["retired"]:
        o.append('<div style="margin-top:9px" class="stale">recently retired — the trigger '
                 'fired and the prop came out:</div>')
        for r in cr["retired"]:
            o.append(f'<div class="lrow" title="{escape(r["id"])}">'
                     f'{chip("retired", "#2e7d32")} '
                     f'<b>{escape(_face(r["id"])[0])}</b> '
                     f'<span class="stale">{escape(r["date"])}</span>'
                     + (f'<div class="chainrow">{escape(r["retired_by"][:220])}</div>'
                        if r["retired_by"] else "") + '</div>')

    lv = b["live"]
    # NAMED FOR WHAT IT SHOWS. This section was headed "the live causal strip" and rendered
    # flat transport rows — sender, recipient, message type, delivery status. The heading
    # said "the live causal strip" and drew no causation, so the rename is right.
    #
    # THE REASON WRITTEN HERE BEFORE THIS WAS FALSE, and it was worse than the defect it
    # replaced. It asserted "dependency_roots names the message's OWN body handle, not
    # another message. There is no causal relation in this projection to draw" — inferred
    # from ONE message, and it instructed the next reader never to build the causal view
    # the finding actually asked for. Measured across all 323 live fabric messages:
    #   dependency_roots values that ARE another message's message_id   46
    #   dependency_roots values that ARE another message's body_handle  10
    #   message -> message edges total                                  56
    #   (self-only dependency_roots: 57 of 323)
    # under root names including inbound, verdict, prior, attack_request,
    # amendment_message, handshake_reply, original_message, refused_message.
    #
    # So the edges EXIST and this projection simply does not read them yet. The door stays
    # open: draw those 56 edges and the causal name is earned. Until then the heading says
    # what the render does, which is show the latest messages.
    o.append(h2("the live seat fabric — latest messages"))
    o.append(f"<div><b>fabric</b>: {escape(str(lv['fabric'].get('status')))}</div>")
    for m in lv["fabric"].get("recent", [])[:6]:
        # seat ids ARE the readable names here; the cursor is the machine ordering key
        o.append(f"<div style='font-size:12px;color:#8d99a8' "
                 f"title='fabric cursor #{escape(str(m['cursor']))}'>"
                 f"{escape(str(m['from']))} → {escape(str(m['to']))} · "
                 f"{escape(str(m['type']))} · {escape(str(m['status']))}</div>")
    if lv.get("updown_demo"):
        d = lv["updown_demo"]
        h = d["headline"]
        o.append(h2("ingest → reconstruct, first receipt")
                     + src(d["source"], "receipt"))
        o.append(f"<div>{d['corpus']['files']} files · {d['corpus']['spans']} spans · "
                 f"{d['corpus']['handles']} handles ({d['corpus']['handle_to_corpus_ratio']:.0%}"
                 f" of corpus bytes)</div>"
                 f"<div>descent hit@1 <b>{h['descent_hit_at_1']}</b>/{h['probes']} · hit@3 "
                 f"<b>{h['descent_hit_at_3']}</b>/{h['probes']} · flat {h['flat_handle_hit_at_3']}"
                 f" · ceiling {h['content_ceiling_hit_at_3']}</div>")
        for hm in h["historic_misses_reasked"]:
            o.append(f"<div style='color:#9ccc9c'>historic miss re-asked → rank "
                     f"{hm['descent_rank']}: {escape(hm['query'][:60])}</div>")
        o.append(f"<div class='stale'>{escape(d['note'])}</div>")
    aa = lv["acceptance_audit"]
    o.append(h2("the acceptance lane — latest fabric row") + src(aa.get("source", "")))
    if aa.get("head"):
        o.append(f"<div style='font-size:12px' "
                 f"title='fabric cursor #{escape(str(aa['cursor']))}'>"
                 f"{escape(str(aa['from']))} · {escape(str(aa['type']))} · "
                 f"{escape(str(aa['status']))}</div>"
                 f"<div style='font-size:12px;color:#8d99a8'>{escape(aa['head'])}…</div>")
    else:
        o.append(f"<div class='stale'>{escape(str(aa.get('status')))}</div>")
    # "tonight's commits" was temporal deixis on a cached render: true at build, false by
    # morning, and unanchored to anything a reader could check. The newest commit's own
    # date is the fact — see live_pane().
    o.append(h2(f'the last {len(lv["git_head"])} commits · newest '
                f'{lv.get("git_head_date", "unknown")}'))
    for g in lv["git_head"]:
        o.append(f"<div style='font-size:11.5px;font-family:monospace;color:#8d99a8'>"
                 f"{escape(g[:110])}</div>")

    # THE CHROME, assembled last because the index is DERIVED from the sections that
    # actually rendered — h2() is the only door into `sections`, so an index entry
    # cannot name a section that is not on the page, and a section cannot hide from
    # the index. The board's law line moves up here: it is the reader's first fact.
    back = (f'<a class="home" href="{escape(home)}">← the front door</a>' if home
            else '<span class="away">standalone render — this register has no front '
                 'door to return to; open it through the engine to navigate</span>')
    toc = "".join(f'<a href="#{sid}">{escape(t)}</a>' for sid, t in sections)
    rcpt = (f'<span class="away" style="margin-left:12px">{escape(receipt)}</span>'
            if receipt else "")
    chrome = (f'<div class="chrome">{back}{rcpt}'
              f'<div class="toc">{toc}</div></div>')
    keys = ((KEYS_SNIPPET + ASK_SNIPPET) if home else "") + INSTRUMENT_SNIPPET
    return "\n".join(head) + "\n" + chrome + "\n" + "\n".join(o) + keys


def main() -> int:
    b = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "board.json").write_text(json.dumps(b, indent=1, ensure_ascii=False),
                                    encoding="utf-8")
    (OUT / "board.html").write_text(render_html(b), encoding="utf-8")
    print(json.dumps({"board": str(OUT.relative_to(ROOT)),
                      "campaign_next": b["campaign"]["next_act"],
                      "inventory_generation": b["inventory"]["generation"],
                      "inventory_rows": b["inventory"]["total_rows"],
                      "fabric": b["live"]["fabric"].get("status", "?")[:60]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
