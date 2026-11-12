"""sources.py — the front door's source registry (front door M1; the one extension point).

The interface law (DESIGN_2026-08-20 s1) demands a named row-source on every panel; this
module is where those names live. One declarative table describes every JSONL store the
front door may render: path, id/ts/kind fields, the facet fields worth counting, a
staleness budget (drives the RED freshness chip), and whether the store is host-owned
(outside the tree — declared as such on every panel that reads it, never counted in an
engine account).

Adding a store to the surface is a registry entry, never a template. The nav, the filter
autocomplete, the facet rail, `/front/sources`, and the tests all generate from here.

Scale honesty (the critic's correction, banked in the spec): row COUNTS here are small
but row BYTES are not — `.closure_meter.jsonl` is ~54 MB at ~24 KB/row. A source with
``scan=False`` is served metadata-only (size, mtime, age): the organ altitude may show
it; the row explorer refuses to scan it and says so.

Read-only: this module writes nothing, ever.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import os
import time
from pathlib import Path
from typing import Any

#: staleness budgets in seconds — a source whose newest row (or mtime) is older than its
#: budget renders a RED freshness chip. Defaults, retunable at his walk.
_H, _D = 3600, 86400


def _repo_root() -> Path:
    return source_tree()


#: The registry. Field names verified against the tree 2026-08-24 (the survey's own
#: store-by-store sampling; see FRONT_DOOR_REQUIREMENTS_CATALOGUE s0).
SOURCES: dict[str, dict[str, Any]] = {
    "journal": dict(
        path="contract/journal.jsonl", id_field="act_id", ts_field="ts",
        kind_field="record", staleness=4 * _H,
        facets=["record", "phase", "store", "status"],
        columns=["ts", "record", "act_id", "store", "row_id", "phase", "status"],
        label="the act journal (begin/done pairs, kill-safe)"),
    "campaign": dict(
        path="corpus_friction/campaign.jsonl", id_field="stage", ts_field="ts",
        kind_field="record", staleness=24 * _H,
        facets=["record", "stage", "status", "exit"],
        columns=["ts", "record", "stage", "status", "exit", "output_head"],
        label="campaign stages + banked gate verdicts"),
    "work_orders": dict(
        path="corpus_friction/work_orders.jsonl", id_field="id", ts_field="ts",
        kind_field="record", staleness=7 * _D,
        facets=["record", "status", "cost_class", "corpus"],
        columns=["ts", "record", "id", "status", "what", "text", "title"],
        label="work orders, resolutions, amendments, notes, ASK rows"),
    "semantic_operational_sources": dict(
        path="semantic/operational_sources.jsonl", id_field="id", ts_field=None,
        kind_field="kind", staleness=24 * _H,
        expectation="projection",
        facets=["kind", "source_classes"],
        columns=["id", "kind", "source_classes", "canonical_handle", "content_handle"],
        label="content-addressed operational semantic leaves; Git and Atlas remain canonical"),
    "atlas_inventory": dict(
        path="corpus_friction/atlas_inventory.jsonl", id_field="id", ts_field="ts",
        kind_field="record", staleness=24 * _H,
        facets=["record", "class", "disposition", "generation"],
        columns=["ts", "record", "id", "class", "item", "disposition", "generation"],
        label="Atlas inventory generations and last-wins disposition rows"),
    "promises": dict(
        path="contract/promises.jsonl", id_field="id", ts_field="date",
        kind_field="status", staleness=7 * _D,
        facets=["status", "owner"],
        columns=["date", "id", "status", "owner", "ask"],
        label="the promise ledger (owed, both directions)"),
    "predictions": dict(
        path="contract/predictions.jsonl", id_field="id", ts_field="ts",
        kind_field="verdict", staleness=30 * _D,
        facets=["verdict", "default_axis"],
        columns=["id", "target", "verdict", "default_axis"],
        label="preregistered predictions (expectation-class rows)"),
    "seats": dict(
        path="contract/seats.jsonl", id_field="seat", ts_field="ts",
        kind_field="relay_state", staleness=24 * _H,
        # AN EVENT LEDGER, NOT A FEED. This file appends when a seat is FOUNDED — its
        # last rows are "superego live" and "interface live". Nothing writes it in the
        # ordinary course, so 24h of silence means "no new seat was founded today",
        # which is the healthy case. Measured against a wall-clock budget it went RED and
        # the brief reported it as "1 NEEDS YOU · gone quiet 24h · worst seats" while the
        # live fabric was at cursor 630 and the busiest organ in the engine. A false
        # alarm on his attention, and one he could not have acted on if he had wanted to.
        expectation="ledger",
        facets=["seat", "relay_state"],
        columns=["ts", "seat", "title", "relay_state"],
        label="seat lifecycle (the founding ledger — quiet is the healthy case; the "
              "live fabric is the conceptric store, not this file)"),
    "bequests": dict(
        path="contract/bequests.jsonl", id_field="written", ts_field="written",
        kind_field=None, staleness=30 * _D,
        facets=["by"],
        columns=["written", "by", "text"],
        label="bequests (authored at close, carried verbatim)"),
    "proxy_verdicts": dict(
        path="proxy_verdicts.jsonl", id_field="id", ts_field="ts",
        kind_field="kind", staleness=7 * _D,
        facets=["kind", "confidence", "date"],
        columns=["date", "id", "kind", "confidence", "question"],
        label="the author's rulings (his-steer rows, confidence-stamped)"),
    "census_verdicts": dict(
        path="corpus_friction/census_verdicts.jsonl", id_field="organ", ts_field="ts",
        kind_field="verdict", staleness=7 * _D,
        facets=["verdict", "diverged_unadjudicated"],
        columns=["ts", "organ", "verdict", "wall_s", "diverged_unadjudicated"],
        label="organ census verdicts"),
    "suite_runs": dict(
        path="corpus_friction/suite_runs.jsonl", id_field="head", ts_field="ts",
        kind_field="record", staleness=7 * _D,
        facets=["verdict", "mode", "selector_version"],
        columns=["ts", "verdict", "mode", "selected", "new_reds", "wall_s", "head"],
        label="test-suite runs (verdict, selection, wall clock)"),
    "methods": dict(
        path="corpus_friction/methods.jsonl", id_field="id", ts_field="ts",
        kind_field="task_class", staleness=30 * _D,
        facets=["task_class", "status"],
        columns=["id", "task_class", "status", "law"],
        label="the methods fibre (law + forbids rows)"),
    "residue": dict(
        path=".residue.jsonl", id_field="act_id", ts_field="ts",
        kind_field="kind", staleness=24 * _H,
        facets=["axis", "kind", "grade", "consumer"],
        columns=["ts", "axis", "kind", "grade", "magnitude", "act_id"],
        label="typed residue (the closure loop's remainder rows)"),
    "reembed_timing": dict(
        path=".reembed_timing.jsonl", id_field=None, ts_field="ts",
        kind_field="mode", staleness=24 * _H,
        facets=["mode"],
        columns=["ts", "mode", "nodes", "node_delta", "total"],
        label="re-embed phase timings"),
    "wire_verdicts": dict(
        path=".wire_verdicts.jsonl", id_field="id", ts_field="ts",
        kind_field="verdict", staleness=24 * _H,
        facets=["verdict", "method"],
        columns=["ts", "id", "verdict", "method", "cos"],
        label="wire verdicts (judged proposals)"),
    "wire_proposals": dict(
        path=".wire_proposals.jsonl", id_field="id", ts_field="ts",
        kind_field="via", staleness=24 * _H,
        facets=["via"],
        columns=["ts", "id", "via", "cos", "heat"],
        label="wire proposals (the candidate stream)"),
    "stranger_bench": dict(
        path="holdout/STRANGER_BENCH_VERDICTS.jsonl", id_field="run", ts_field="ts",
        kind_field="bench_version", staleness=7 * _D,
        facets=["bench_version"],
        columns=["ts", "run", "bench_version", "green", "red"],
        label="stranger-bench verdicts (the wake/close acceptance test)"),
    # the three stores today's journal banks into that the registry did not know —
    # 23 bank rows rendered UNMAPPED (and, before the same review's fix, linked into
    # the WRONG store). Fields read off the live rows 2026-08-24, never guessed.
    "open_stack_wants": dict(
        path="corpus_friction/open_stack_wants.jsonl", id_field="id", ts_field="ts",
        kind_field="kind", staleness=7 * _D,
        facets=["kind", "status", "stratum"],
        columns=["ts", "id", "status", "stratum", "title"],
        label="the open stack's wants (W-rows, minted at close)"),
    "census_checks": dict(
        path="corpus_friction/census_checks.jsonl", id_field="organ",
        ts_field="minted", kind_field="record", staleness=7 * _D,
        facets=["record", "organ"],
        columns=["minted", "record", "organ", "expect", "cmd"],
        label="the organ census's checks (one fireable cmd per organ)"),
    "census_exclusions": dict(
        path="corpus_friction/census_exclusions.jsonl", id_field="sha256_of_line",
        ts_field="minted", kind_field="record", staleness=7 * _D,
        facets=["record", "store"],
        columns=["minted", "record", "store", "expiry", "reason"],
        label="census exclusions (subtracted by line HASH, never by index)"),
    "talk": dict(
        path="contract/talk.jsonl", id_field="id", ts_field="ts",
        kind_field="record", staleness=30 * _D,
        facets=["record", "actor", "to"],
        columns=["ts", "record", "id", "actor", "to", "text"],
        label="the talk path (his words bank before they travel; replies thread back)"),
    "liveness": dict(
        path="corpus_friction/liveness.jsonl", id_field="id", ts_field="ts",
        kind_field="record", staleness=24 * _H,
        # AN ADJUDICATION LEDGER, NOT A FEED — reclassified on evidence, not to silence a
        # red. His steer, 2026-08-25: "liveness claims are triggering and nothing is being
        # done about them it seems." Measured before changing anything: 13 claim packets,
        # 13 graded, ZERO ungraded; the last row is a "-final" verdict from 2026-08-24.
        # The archaeology campaign is complete, so this store appends only when a new
        # adjudication happens. Judged against a 24h wall clock it goes red forever and
        # NOTHING can ever clear it — the worst kind of alarm, because it teaches him to
        # stop reading the zone. Re-derive the evidence with:
        #   python3 -c "import json;rs=[json.loads(l) for l in
        #   open('corpus_friction/liveness.jsonl') if l.strip()];
        #   print(len({r.get('packet') for r in rs if r.get('record')=='liveness-packet'}),
        #   len({r.get('packet') for r in rs if r.get('record')=='liveness-verdict'}))"
        expectation="ledger",
        facets=["record", "verdict", "claim"],
        columns=["ts", "record", "id", "organ", "claim", "verdict", "rater"],
        label="archaeology liveness — claim packets and their graded verdicts "
              "(quiet is the healthy case: the campaign closed 2026-08-24 with all 13 "
              "packets graded)"),

}

#: Host-owned transcript directory — OUTSIDE the tree, declared as such on every panel.
#: The one authority for session ids is ~/.claude/sessions/*.json (the seats surface's
#: NOTE-20260824-resume-canonical-form); transcripts are joined through it, never named
#: by hand (the stopgap's KNOWN dict refused at this seat's founding, refusal R3).
TRANSCRIPT_DIR = "~/.claude/projects/-home-phujck-VScodeProjects-laplace"


def transcript_dir() -> Path:
    return Path(os.path.expanduser(TRANSCRIPT_DIR))


def get(name: str) -> dict[str, Any] | None:
    """One source's registry entry, path resolved, or None for an unknown name."""
    spec = SOURCES.get(name)
    if spec is None:
        return None
    out = dict(spec)
    out["name"] = name
    out["abspath"] = str(_repo_root() / spec["path"])
    out["scan"] = spec.get("scan", True)
    out["host_owned"] = False
    return out


def stat(name: str) -> dict[str, Any]:
    """Liveness metadata for one source: size, mtime, age, and the RED verdict against
    its staleness budget. Missing files serve ABSENT loudly, never raise — absence is
    rendered as loudly as failure (the interface law)."""
    spec = get(name)
    if spec is None:
        return {"name": name, "error": "unknown source"}
    p = Path(spec["abspath"])
    try:
        st = p.stat()
    except OSError:
        return {"name": name, "path": spec["path"], "absent": True, "red": True,
                "label": spec["label"]}
    age = max(0.0, time.time() - st.st_mtime)
    # EXPECTATION SEPARATES SILENCE FROM DEATH. A "feed" should keep moving, so age past
    # budget is a real signal. A "ledger" moves only when its event happens, so the same
    # age means nothing was founded/closed/banked — the healthy case, not a defect.
    # `red` keeps its old meaning (age past budget) because other surfaces read it;
    # `concern` is the one the brief may spend his attention on.
    expectation = spec.get("expectation", "feed")
    over = age > spec["staleness"]
    return {
        "name": name, "path": spec["path"], "label": spec["label"],
        "bytes": st.st_size, "mtime": st.st_mtime, "age_s": round(age, 1),
        "budget_s": spec["staleness"], "red": over,
        "expectation": expectation,
        "concern": over and expectation == "feed",
        "quiet_is_normal": expectation == "ledger",
        "scan": spec["scan"],
    }


def roster() -> list[dict[str, Any]]:
    """Every source's stat, registry order — the organ altitude's spine and the
    `/front/sources` payload agents read."""
    return [stat(n) for n in SOURCES]
