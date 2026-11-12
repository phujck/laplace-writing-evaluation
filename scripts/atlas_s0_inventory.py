#!/usr/bin/env python3
"""ATLAS-S0 inventory enumerator — every stage, store, organ, skill, surface, riding item,
one disposition row each, reconciled from the graded instruments and never re-derived.

Ground (the stage row, verbatim scope): corpus_friction/campaign.jsonl#ATLAS-S0 — "every
existing campaign stage, store, organ, skill, surface, and riding item enumerated with a
disposition each (ABSORBED/RETIRED/CARRIED); reconciles-never-re-derives the graded
instruments (the audit's 167, the LIV rows)".

The instruments this reconciles (each row cites its own):
  campaign stages  -> corpus_friction/campaign.jsonl (typed stage rows)
  stores           -> the filesystem store set + CHARTER_2026-08-24 §3a (append-frozen archive)
  organs           -> AUDIT_2026-08-23_implementation.md status column + CHARTER §5 carried set
  skills           -> .claude/skills/*/SKILL.md + .claude/workflows/*
  surfaces         -> NOTE-20260824-s0-disposition-table-routes (the interface's ruled table,
                      FAMILY grain — route-level expansion is the panel's job, not this file's)
  riding items     -> laplace.engine.wake.account() (the canonical open-ledger reader; importing it
                      is the point: a reimplementation here would be a second truth)

Disposition vocabulary: ABSORBED / RETIRED / CARRIED / HOLD-FOR-RULING, with an optional
mode (programme|archive|live-store|code|quarry|riding) refining CARRIED.  Anything needing a
judgment this script cannot cite goes HOLD-FOR-RULING, loudly — never a silent default.

Output: corpus_friction/atlas_inventory.jsonl (append-only; a re-run replaces nothing and
appends a fresh generation stamped with its own run id — last-wins by (id), the house rule).

Runtime law: /usr/bin/python3, system + user site. Read-only against every instrument.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "corpus_friction" / "atlas_inventory.jsonl"
BY = "claude-seat s0 enumerator"
CHARTER = "CHARTER_2026-08-24_the-atlas-rebuild.md"
AUDIT = "AUDIT_2026-08-23_implementation.md"
ROUTE_NOTE = "NOTE-20260824-s0-disposition-table-routes"

# CHARTER §5, the carried set named exactly (carriage as CODE; everything else functional/
# partial is quarry: contracts and tests carry, implementations are rewritten).
CARRIED_AS_CODE = {
    "sources", "rows", "trace", "stream", "front_door", "seats_surface",
    "genesis", "census", "figures", "figure_audit", "figure_runner",
}
QUARRY_EXPLICIT = {"scanner"}  # §5: "scanner.py EXCLUDED, quarry only"

# The store files the rebuild still actively writes (live accounting organs) — everything
# else on disk is the append-frozen source archive of CHARTER §3a.
LIVE_STORES = {
    "corpus_friction/campaign.jsonl", "corpus_friction/work_orders.jsonl",
    "corpus_friction/methods.jsonl", "corpus_friction/edges.jsonl",
    "corpus_friction/liveness.jsonl", "corpus_friction/author_model.jsonl",
    "corpus_friction/atlas_inventory.jsonl", "corpus_friction/open_stack_wants.jsonl",
    "corpus_friction/open_stack_forks.jsonl",
    "contract/journal.jsonl", "contract/promises.jsonl", "contract/predictions.jsonl",
    "contract/seats.jsonl", "contract/talk.jsonl", "contract/bequests.jsonl",
    "contract/judged_verdicts.jsonl",
}

# The interface's ruled route table, FAMILY grain, verbatim from the NOTE (banked and
# ego-endorsed 2026-08-24T11:50). The unnamed remainder of the CARRY 15 is one row citing
# the census run — expansion is the panel's job.
ROUTE_FAMILIES: list[tuple[str, str, str]] = [
    ("/projection", "RETIRED", "page+html retired"),
    ("/review-page", "RETIRED", "the page retires; the data layer carries separately"),
    ("/dials", "RETIRED", "surface retired"),
    ("/meta", "RETIRED", "retired"),
    ("/reconstruct", "RETIRED", "retired"),
    ("/bench-tombstones", "RETIRED", "tombstones retired"),
    ("/desk", "ABSORBED", "absorb to front door"),
    ("/dashboard", "ABSORBED", "absorb to front door"),
    ("/seats", "ABSORBED", "absorb to front door"),
    ("/guide", "ABSORBED", "the stale-guide disease's home; absorb to front door"),
    ("/analytics", "ABSORBED", "face absorbed to front door"),
    ("walk_requests.py", "ABSORBED", "zero production importers; becomes S4 diff-as-review consumer"),
    ("/artefact", "CARRIED", "carries whole"),
    ("/review-data-layer", "CARRIED", "the steer spine"),
    ("/lineage+provenance", "CARRIED", "NAMED the prior-art organ's substrate — no rival builds"),
    ("/walk", "CARRIED", "carries"),
    ("/front", "CARRIED", "carries"),
    ("/altitude", "HOLD-FOR-RULING", "write lane likely folds into front-door decisions; visit named in NOTE"),
    ("/evolution", "HOLD-FOR-RULING", "write lane; visit named in NOTE"),
    ("/selection", "HOLD-FOR-RULING", "write lane; visit named in NOTE"),
    ("/derivation", "HOLD-FOR-RULING", "write lane; visit named in NOTE"),
    ("POST /dials/run-flip", "RETIRED", "KILL-ON-SIGHT: write verb declared in no yaml and no tombstone"),
    ("POST /dials/run-restore", "RETIRED", "KILL-ON-SIGHT: write verb declared in no yaml and no tombstone"),
]


def _slug(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")[:70]


def _row(cls: str, item: str, disposition: str, ground: list[str], why: str,
         mode: str | None = None) -> dict:
    row = {
        "record": "inventory",
        "id": f"INV-{cls}-{_slug(item)}",
        "class": cls,
        "item": item,
        "disposition": disposition,
        "ground": ground,
        "why": why,
        "by": BY,
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }
    if mode:
        row["mode"] = mode
    return row


def campaign_stages() -> list[dict]:
    """Inventory the campaign through its canonical reader, never a second fold."""
    from laplace.engine import wake

    rows: list[dict] = []
    stages = {r["id"]: r for r in wake.campaign(ROOT, run_gates=False)["stages"]}
    absorbed = "ATLAS-ABSORB-OLD-CAMPAIGN" in stages
    for sid in sorted(stages):
        if sid.startswith("CAMP-") and absorbed:
            rows.append(_row("campaign-stage", sid, "ABSORBED",
                             ["corpus_friction/campaign.jsonl#" + sid,
                              "corpus_friction/campaign.jsonl#ATLAS-ABSORB-OLD-CAMPAIGN"],
                             "superseded by the atlas rebuild; retained for its S0 disposition"))
        else:
            rows.append(_row("campaign-stage", sid, "CARRIED",
                             ["corpus_friction/campaign.jsonl#" + sid],
                             "the rebuild programme itself", mode="programme"))
    return rows


def stores() -> list[dict]:
    rows: list[dict] = []
    files = sorted(
        list((ROOT / "contract").glob("*.jsonl"))
        + list((ROOT / "corpus_friction").glob("*.jsonl"))
        + list((ROOT / "holdout").glob("*.json"))
    )
    for f in files:
        rel = str(f.relative_to(ROOT))
        live = rel in LIVE_STORES
        rows.append(_row(
            "store", rel, "CARRIED",
            [rel, CHARTER + "#3a"],
            "live accounting organ the rebuild still writes" if live
            else "append-frozen source archive under the rebuild (charter §3a)",
            mode="live-store" if live else "archive"))
    for special, why in (
        ("soul/", "sealed; refs-only at every travelling boundary (the perimeter law)"),
        ("evidence/", "run receipts; append-frozen archive"),
        ("diagrams/", "the bound conjugate view; render of rows"),
        ("atlas/stores/", "the greenfield's own store root"),
        (".meaning_tree.json", "the incumbent semantic map; quarry for S1, never the substrate"),
    ):
        rows.append(_row("store", special, "CARRIED", [CHARTER + "#3a"], why, mode="archive"))
    return rows


def organs() -> list[dict]:
    rows: list[dict] = []
    text = (ROOT / AUDIT).read_text(encoding="utf-8")
    seen: set[str] = set()
    # The audit's own status vocabulary, measured: OK 118 · PART 42 · RELIC 4 · DEAD 2 ·
    # STUB 1 = 167. Organ cells appear backticked and bare; accept both.
    for m in re.finditer(r"^\|\s*(DEAD|RELIC|STUB|PART|OK)\s*\|\s*`?([^`|]+?)`?\s*\|",
                         text, re.M):
        status, organ = m.group(1).upper(), m.group(2).strip()
        if organ in seen:
            # The audit grades two distinct organs under one name (measured: `analytics`,
            # engine core vs interface). Emit both; the ordinal keeps ids distinct.
            ordinal = 2
            while f"{organ}-{ordinal}" in seen:
                ordinal += 1
            organ = f"{organ}-{ordinal}"
        seen.add(organ)
        ground = [AUDIT + "#" + organ.rstrip("-0123456789")]
        base = organ.split("/")[-1].removesuffix(".py")
        if status in ("DEAD", "RELIC"):
            rows.append(_row("organ", organ, "RETIRED", ground,
                             f"audit status {status}; retirement is the graded call"))
        elif status in ("STUB",):
            rows.append(_row("organ", organ, "HOLD-FOR-RULING", ground,
                             "audit status STUB — neither dead nor load-bearing; visit at S1"))
        elif base in QUARRY_EXPLICIT:
            rows.append(_row("organ", organ, "CARRIED", ground + [CHARTER + "#5"],
                             "charter §5: scanner excluded from carriage — quarry only",
                             mode="quarry"))
        elif base in CARRIED_AS_CODE:
            rows.append(_row("organ", organ, "CARRIED", ground + [CHARTER + "#5"],
                             "charter §5 named carried set — carries as code, re-earns "
                             "INCUMBENT through the ladder", mode="code"))
        else:
            rows.append(_row("organ", organ, "CARRIED", ground + [CHARTER + "#5"],
                             "default posture: contracts and tests carry; implementation "
                             "rewritten on the substrate", mode="quarry"))
    if len(seen) != 167:
        rows.append(_row("organ", "audit-parse-shortfall", "HOLD-FOR-RULING",
                         [AUDIT], f"parser matched {len(seen)} organ rows against the "
                         "audit's own census of 167 — the table grammar drifted; reconcile "
                         "by hand before the judge pass"))
    return rows


BORN_AFTER_AUDIT = ("sources", "rows", "trace", "stream", "front_door", "seats_surface")


def born_after_audit(audit_rows: list[dict]) -> list[dict]:
    """Charter §5's carried set where the 167-organ audit has no row (judge defect b):
    these files were born at the M1 front-door commit (a55ef5e9, 2026-08-24), after the
    audit's census — enumerated here with their birth named, deduped against the audit."""
    have = {r["item"].split("/")[-1].removesuffix(".py") for r in audit_rows}
    rows = []
    for name in BORN_AFTER_AUDIT:
        if name in have:
            continue
        rows.append(_row("organ", f"src/laplace/{name}.py", "CARRIED",
                         [f"src/laplace/{name}.py", CHARTER + "#5", "commit a55ef5e9"],
                         "born after the audit's census (the M1 front-door landing, "
                         "2026-08-24) — charter §5 names it in the carried set "
                         "(born-under-the-new-laws class)", mode="code"))
    return rows


def skills() -> list[dict]:
    rows: list[dict] = []
    for f in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        rows.append(_row("skill", f.parent.name, "CARRIED",
                         [str(f.relative_to(ROOT))],
                         "session instrument; unaffected by the substrate swap", mode="code"))
    for f in sorted((ROOT / ".claude" / "workflows").glob("*")):
        if f.is_file():
            rows.append(_row("skill", "workflows/" + f.name, "CARRIED",
                             [str(f.relative_to(ROOT))],
                             "pipeline-family instrument serving projects", mode="code"))
    # the canon skill registry (judge verdict on s0inv-20260824T172142Z, defect a): the
    # incumbent programme surface, enumerated live vs archived — the dream/assess loop owns
    # its lifecycle until the substrate supersedes it.
    canon_root = ROOT / "src" / "laplace" / "pipeline" / "canon" / "skills"
    for f in sorted(canon_root.glob("*/SKILL.md")):
        if f.parent.name == "_archive":
            continue
        rows.append(_row("skill", "canon/" + f.parent.name, "CARRIED",
                         [str(f.relative_to(ROOT))],
                         "live canon skill — incumbent programme in run-out; lifecycle "
                         "belongs to assess/dream until the substrate supersedes",
                         mode="programme"))
    for f in sorted(canon_root.glob("_archive/*/SKILL.md")):
        rows.append(_row("skill", "canon/_archive/" + f.parent.name, "RETIRED",
                         [str(f.relative_to(ROOT))],
                         "already archived by the canon's own lifecycle — retirement "
                         "recorded, never re-litigated"))
    return rows


def surfaces() -> list[dict]:
    rows = [
        _row("surface", family, disp, [ROUTE_NOTE], why)
        for family, disp, why in ROUTE_FAMILIES
    ]
    rows.append(_row("surface", "route-note-arithmetic-defect", "HOLD-FOR-RULING",
                     [ROUTE_NOTE],
                     "the NOTE claims 32 families but its named buckets sum to 31 — one "
                     "family unaccounted; the panel must reconcile before the surface "
                     "table is trusted at family grain (judge verdict on "
                     "s0inv-20260824T172142Z, defect d)"))
    rows.append(_row("surface", "route-families-carry-remainder", "CARRIED",
                     [ROUTE_NOTE, "census run wf_1a74e7f7-188"],
                     "the CARRY-15 members not named in the NOTE; family grain per the "
                     "ruled table, route-level expansion is the panel's job"))
    return rows


def riding() -> list[dict]:
    from laplace.engine import wake as wk
    acct = wk.account(ROOT)
    rows: list[dict] = []

    def ledger(name: str, store: str, cls: str) -> None:
        led = acct.get(name) or {}
        for state in ("open_rows", "deferred_rows"):
            for r in led.get(state, []) or []:
                rid = str(r.get("id") or "")
                if not rid:
                    continue
                rows.append(_row(cls, rid, "CARRIED", [store + "#" + rid],
                                 f"{name[:-1] if name.endswith('s') else name} "
                                 f"{state.split('_')[0]} per the canonical account reader",
                                 mode="riding"))

    ledger("promises", "contract/promises.jsonl", "riding-promise")
    ledger("work_orders", "corpus_friction/work_orders.jsonl", "riding-work-order")
    os_ = acct.get("open_stack") or {}
    for wid in (os_.get("wants_store") or {}).get("live", []) or []:
        rows.append(_row("riding-want", wid, "CARRIED",
                         ["corpus_friction/open_stack_wants.jsonl#" + wid, "OPEN_STACK.md"],
                         "live want per the canonical account reader (judge defect c)",
                         mode="riding"))
    for fid in (os_.get("forks_store") or {}).get("live", []) or []:
        rows.append(_row("riding-fork", fid, "CARRIED",
                         ["OPEN_STACK.md#" + str(fid)],
                         "live fork per the canonical account reader (judge defect c)",
                         mode="riding"))
    for pid in acct.get("predictions", {}).get("open_class_ids", []):
        rows.append(_row("riding-prediction", pid, "CARRIED",
                         ["contract/predictions.jsonl#" + pid],
                         "prediction open-class per the canonical reader", mode="riding"))
    return rows


def mathematical_inheritance() -> list[dict]:
    """The UP amendment's inheritance rows (codex s0-inventory-up-inheritance-defect,
    then s0-inventory-generation-defect: GENERATED, never hand-appended — ids match the
    2026-08-24 hand rows exactly so the append-only last-wins law supersedes them)."""
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def row(slug: str, item: str, disposition: str, ground: list[str], why: str) -> dict:
        return {"record": "inventory", "id": f"INV-math-inherit-{slug}",
                "class": "mathematical-inheritance", "item": item,
                "disposition": disposition, "ground": ground, "why": why,
                "by": BY, "ts": ts}

    return [
        row("meaning-upfold", "src/laplace/engine/meaning_upfold.py (the incumbent running UP operator)",
            "QUARRY-EVIDENCE",
            ["src/laplace/engine/meaning_upfold.py", ".reembed_timing.jsonl#2026-08-24 first honest receipt"],
            "measured behaviour (incremental triggers, scoped resplits, declared rebuild vocabulary, "
            "GPU fold) is evidence the new kernel must meet; the implementation is quarry, never "
            "foundation (the clean-code rule)"),
        row("fibred-upfold", "DESIGN_2026-07-28_the-fibred-upfold.md", "DESIGNED-INHERITANCE",
            ["DESIGN_2026-07-28_the-fibred-upfold.md", "corpus_friction/campaign.jsonl#CAMP-06-fibred-upfold"],
            "the fibred-UP design survives its stage's ABSORBED verdict; the assumption-indexed fold "
            "enters the UpAct contract as the fibre/assumption declaration"),
        row("renormalized-atlas", "DESIGN_2026-08-19_the-renormalized-atlas.md", "DESIGNED-INHERITANCE",
            ["DESIGN_2026-08-19_the-renormalized-atlas.md", "RUL-20260824-full-mathematical-arsenal"],
            "measured truncation and closure residual as the fitness law are the mathematical core "
            "binding on UpAct; the kernel's chi/phi and residual-split derive from it"),
        row("f23-per-grade", "evidence/F23_upward_operator_2026-08-07 (hand-authored per-grade evidence)",
            "EVIDENCE-AND-GENERATOR-RULE-HOLD", ["evidence/F23_upward_operator_2026-08-07"],
            "F23 proves per-grade faces were hand-authorable to quality; HOLD on any claim the "
            "mechanical face generator matches it until judged on the same corpus"),
        row("selector-hidden-chi", "evidence/SELECTOR_BENCH_2026-08-21 (the hidden-chi result)",
            "EVIDENCE-AND-EXPLICIT-DIAL-HOLD",
            ["evidence/SELECTOR_BENCH_2026-08-21", "RUL-20260820-selection-criterion-derived"],
            "the bench showed chi dependence the selector could hide; chi is therefore a DECLARED "
            "kernel input with no default - HOLD on any auto-chi until it beats the explicit dial "
            "on the closure-residual selector"),
        row("canonical-updown", "src/atlas/updown.py (the clean canonical UP/DOWN kernel)",
            "HOLD-UNTIL-PROVEN", ["src/atlas/updown.py", "atlas/tests/test_updown.py"],
            "17 LOCAL KERNEL gates green (6 audit defects cured test-first, 2 pinned "
            "counterexamples, residual-honesty + named grade contract landed, API declared final "
            "at commit 375d26fa); the five-gate planted acceptance boundary is NOT passed and NOT "
            "claimed - placed membership, G3 routing with source-chain assemblage, and store "
            "content-address diffs belong to the history/runner layer"),
    ]


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime("s0inv-%Y%m%dT%H%M%SZ")
    rows = [
        {"record": "inventory-generation", "id": run_id, "by": BY,
         "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
         "scope": "campaign-stage store organ skill surface riding mathematical-inheritance",
         "instruments": ["corpus_friction/campaign.jsonl", AUDIT, ROUTE_NOTE,
                          "laplace.engine.wake.account", CHARTER]},
    ]
    organ_rows = organs()
    rows += (campaign_stages() + stores() + organ_rows + born_after_audit(organ_rows)
             + skills() + surfaces() + riding() + mathematical_inheritance())
    for r in rows[1:]:
        r["generation"] = run_id
    with OUT.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    by_class: dict[str, int] = {}
    by_disp: dict[str, int] = {}
    for r in rows[1:]:
        by_class[r["class"]] = by_class.get(r["class"], 0) + 1
        by_disp[r["disposition"]] = by_disp.get(r["disposition"], 0) + 1
    print(json.dumps({"generation": run_id, "rows": len(rows) - 1,
                      "by_class": by_class, "by_disposition": by_disp,
                      "holds": [r["id"] for r in rows[1:]
                                if r["disposition"] == "HOLD-FOR-RULING"],
                      "out": str(OUT.relative_to(ROOT))}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
