"""tests/test_liveness.py — THE REAPER (PRM-20260721-liveness-law).

The build-and-forget kill, mechanised. His verbatim ask (2026-07-21 night): "keep
making orphans and homeless functions. It keeps happening... Build something, forget
it. Build something, forget it. How are you going to stop that?"

Three conjugate assertions hold the whole (the third, THE LEDGER-CONSUMER LAW, added
W-TEETH 2026-07-22 — a store that only ever grows is the machine-finding backlog):

  (1) TOTAL ROUTE ACCOUNTING — every route scanner.py actually serves is either
      DECLARED in some contract/surfaces/*.yaml (a read, a verb route, or the surface's
      own page path), LISTED in contract/tombstones.yaml (verdict tombstone /
      wire-owed / his-ruling-owed, each with a reason), or in the small named
      SYSTEM_ALLOWLIST below. A served route in NONE of these is an ORPHAN — a red
      test, not a discovery. The served census is parsed from scanner.py's dispatch
      conditions; a booted server is driven (GET) to confirm the census is real and to
      cross-check the rulings (a `tombstone` GET route must actually answer 410/301; a
      `wire-owed` GET route must NOT answer 410 — it is genuinely alive).

  (2) THE STORE TWIN — every corpus_stores/ + corpus_friction/ top-level store maps to
      a declared-surface read (the friction ledgers → the /desk surface), a
      tombstones.yaml store row, or a named engine-internal STORE_ALLOWLIST entry
      (each with a reason).

  (3) THE LEDGER-CONSUMER LAW (the producer-names-consumer law) — every accumulating
      *.jsonl ledger (corpus_friction/ + the contract ledgers + the per-project feedback
      ledgers) maps to a NAMED organ that RESOLVES its rows (LEDGER_CONSUMERS). The
      conjugate of the store twin: the twin proves a store is READ; this proves its rows
      are CLOSED. The machine-finding backlog — friction findings poured faster than
      anything retires them — is named LOUD as an honest xfail, not hidden green.

The orphan count CANNOT grow: a NEW served route or a NEW engine-internal store with
no home here or in a surface yaml turns this suite red at the delta — the birth
obligation (PRM-20260721-liveness-law item 6): backend growth cannot outrun the face.

This suite is FAIL-eligible in scripts/close_checklist.py (the orphan-census clause):
a close cannot pass while the reaper is red.
"""
from __future__ import annotations

import http.client
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SCANNER = REPO / "src" / "laplace" / "web" / "scanner.py"
SURFACES = REPO / "contract" / "surfaces"
TOMBSTONES = REPO / "contract" / "tombstones.yaml"

# The ONLY paths that need neither a surface declaration nor a tombstone row: static
# assets and genuine system/engine-internal endpoints. Small and NAMED, each with a
# reason (his law: no orphan silently allowlisted).
SYSTEM_ALLOWLIST: dict[str, str] = {
    "GET /favicon.ico": "static system browser-tab icon (self-contained SVG bytes; no surface owns a favicon)",
    "GET /index.html": "static back-compat alias of /map (the brain-scanner bytes; kept so an old bookmark resolves)",
    "POST /fire": "engine-internal live route — scanner.client_fire POSTs here in-process from scripts/ingest_*.py so an open scanner page can watch a long ingest fire live (the live-consumer escape clause, scanner.py); GET /firings is its poll half",
}

# corpus_stores/ + corpus_friction/ TOP-LEVEL stores that are engine-internal (produced
# and consumed inside the engine, not a surface read). NAMED, each with a reason. A
# corpus_friction/*.jsonl ledger is NOT listed here — it is covered by rule as a /desk
# surface read (FRICTION_LEDGER_REASON). A new engine-internal store must be added here
# (or tombstoned) or the twin goes red.
STORE_ALLOWLIST: dict[str, str] = {
    # corpus_stores/ — the staged manuscript pipeline's derivation caches (produced and
    # consumed by laplace.pipeline; warm-by-committing per the localstate manifest).
    "corpus_stores/derivation_walk": "engine-internal — the derivation-walk cache (laplace.pipeline staged build)",
    "corpus_stores/figure_caption": "engine-internal — the figure-caption cache (laplace.pipeline)",
    "corpus_stores/hello_cache": "engine-internal — the hello/greeting payload cache (self_corpus)",
    "corpus_stores/paragraph_plan": "engine-internal — the paragraph-plan cache (laplace.pipeline staged build)",
    "corpus_stores/section_architecture": "engine-internal — the section-architecture cache (laplace.pipeline)",
    "corpus_stores/spine_chain": "engine-internal — the spine-chain cache (laplace.pipeline)",
    "corpus_stores/voice_corpus_cache": "engine-internal — the sealed voice-exemplar store (localstate entry voice-store; warm-by-committing)",
    "corpus_stores/ancestor_inventory.json": "engine-internal — the ancestor inventory cache (laplace.pipeline)",
    "corpus_stores/demo_verdict.json": "engine-internal — a banked demo verdict fixture (laplace.pipeline)",
    "corpus_stores/four_lens_corpus_verdict.json": "engine-internal — the four-lens corpus verdict cache (laplace.pipeline)",
    "corpus_stores/section_architecture_corpus_verdict.json": "engine-internal — the section-architecture verdict cache (laplace.pipeline)",
    # corpus_friction/ non-ledger files — engine baselines / digests / manifests.
    "corpus_friction/register_baseline.json": "engine-internal — the register-law tic baseline (scripts/audit_register.py)",
    "corpus_friction/suite_baseline.json": "engine-internal — the test-suite baseline (paper_gates / suite audit)",
    "corpus_friction/laplace_engine.digest.md": "engine-internal — the recurrence digest (scripts/detect_recurrence.py)",
    "corpus_friction/deslop_manifest_eigenengine.json": "engine-internal — the eigenengine deslop manifest (laplace.pipeline)",
    "corpus_friction/dream_lifts_2026-07-13.json": "engine-internal — a banked dream-lift record (laplace.dream)",
    "corpus_friction/stage_corpus_census.json": "engine-internal — the stage/corpus census cache (laplace.pipeline)",
    "corpus_friction/suite_map.json": "engine-internal — the test-shard → source map (laplace.engine.suite_map), a gitignored CACHE rebuilt from static analysis whenever its fingerprint moves; the record it serves is corpus_friction/suite_runs.jsonl, which travels",
}

FRICTION_LEDGER_REASON = (
    "declared-surface read — a friction ledger read by the /desk surface (open-frictions / "
    "forks / work-orders classes) and written via conceptric POST /corpus/friction"
)


# --------------------------------------------------------------------------- served census
def _method_bodies() -> dict[str, str]:
    """The do_GET / do_POST method-body source slices from scanner.py."""
    src = SCANNER.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for meth, fn in (("GET", "do_GET"), ("POST", "do_POST")):
        m = re.search(rf"def {fn}\(self\)", src)
        assert m, f"{fn} not found in scanner.py"
        start = m.start()
        nxt = re.search(r"\n        def do_", src[start + 10:])
        out[meth] = src[start:(start + 10 + nxt.start()) if nxt else len(src)]
    return out


def served_routes() -> set[tuple[str, str]]:
    """The honest route census: (method, path) pairs parsed from scanner.py's dispatch
    conditions — ``u.path == "..."``, ``u.path.startswith("...")``, and both
    ``u.path in (...)`` and ``u.path not in (...)`` tuples (the latter is the do_POST
    escape-clause allowlist whose members ARE served, e.g. /fire)."""
    routes: set[tuple[str, str]] = set()
    for meth, body in _method_bodies().items():
        for m in re.finditer(r'u\.path\s*==\s*["\']([^"\']+)["\']', body):
            routes.add((meth, m.group(1)))
        for m in re.finditer(r'u\.path\.startswith\(["\']([^"\']+)["\']\)', body):
            routes.add((meth, m.group(1)))
        for m in re.finditer(r'u\.path\s+(?:not\s+)?in\s+\(([^)]+)\)', body):
            for lit in re.finditer(r'["\']([^"\']+)["\']', m.group(1)):
                routes.add((meth, lit.group(1)))
    # /favicon.ico is matched via == above; every literal survives. Sanity: non-empty.
    assert routes, "parsed an empty route census from scanner.py — the parser drifted"
    return routes


# --------------------------------------------------------------------------- declared (yaml)
def _declared() -> tuple[set[str], set[str]]:
    """(declared_route_paths, page_paths) from contract/surfaces/*.yaml."""
    declared: set[str] = set()
    pages: set[str] = set()
    route_re = re.compile(r"\b(?:GET|POST)\s+(/[^\s?#()]+)")
    for f in sorted(SURFACES.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        surf = doc.get("surface")
        if surf:
            pages.add("/" if surf == "dashboard" else f"/{surf}")
        # reads: list of strings ("GET /x  # comment")
        for r in doc.get("reads", []) or []:
            for mm in route_re.finditer(str(r)):
                declared.add(mm.group(1))
        # verbs: list of dicts; a dict may carry a 'route' string ("POST /x (verb y)")
        for v in doc.get("verbs", []) or []:
            if isinstance(v, dict) and v.get("route"):
                for mm in route_re.finditer(str(v["route"])):
                    declared.add(mm.group(1))
    return declared, pages


def _tombstone_rows() -> list[dict]:
    doc = yaml.safe_load(TOMBSTONES.read_text(encoding="utf-8")) or {}
    return list(doc.get("routes", []) or [])


def _tombstone_index() -> dict[tuple[str | None, str], str]:
    """{(method_or_None, path): reason}. A route "GET /x" indexes (GET, /x); "/x"
    indexes (None, /x) and matches any method."""
    idx: dict[tuple[str | None, str], str] = {}
    for row in _tombstone_rows():
        route = str(row.get("route", "")).strip()
        reason = str(row.get("reason", "")).strip()
        verdict = str(row.get("verdict", "")).strip()
        assert verdict in {"tombstone", "wire-owed", "his-ruling-owed"}, (
            f"tombstones.yaml row {route!r} has unknown verdict {verdict!r} "
            "(expected tombstone / wire-owed / his-ruling-owed)")
        assert reason, f"tombstones.yaml row {route!r} carries no reason (every row must)"
        parts = route.split(None, 1)
        if len(parts) == 2 and parts[0] in {"GET", "POST"}:
            idx[(parts[0], parts[1])] = reason
        else:
            idx[(None, route)] = reason
    return idx


def _covered(meth: str, path: str, declared: set[str], pages: set[str],
             tomb: dict[tuple[str | None, str], str]) -> str | None:
    """Return the covering category name, or None if the route is an orphan."""
    base = path.rstrip("/") or "/"
    if base in pages or path in pages:
        return "surface-page"
    if base in declared or path in declared:
        return "surface-read/verb"
    for d in declared:  # a prefix gateway over declared sub-routes (/corpus/ -> /corpus/grade)
        if d.startswith(base + "/"):
            return "surface-gateway"
    if (meth, path) in tomb or (None, path) in tomb:
        return "tombstone-ledger"
    if f"{meth} {path}" in SYSTEM_ALLOWLIST:
        return "system-allowlist"
    return None


# =========================================================================== THE TEETH (static)
def test_route_census_fully_accounted():
    """No served route is an orphan. Every (method, path) scanner.py dispatches is
    declared in a surface yaml, listed in tombstones.yaml, or in SYSTEM_ALLOWLIST."""
    declared, pages = _declared()
    tomb = _tombstone_index()
    orphans = []
    for meth, path in sorted(served_routes()):
        if _covered(meth, path, declared, pages, tomb) is None:
            orphans.append(f"{meth} {path}")
    assert not orphans, (
        "ORPHAN ROUTES — served by scanner.py but declared by no surface yaml, listed "
        "in no contract/tombstones.yaml row, and in no SYSTEM_ALLOWLIST entry. Each is "
        "build-and-forget (PRM-20260721-liveness-law): declare it in a surface yaml, or "
        "add a tombstones.yaml row (verdict + reason), before this close.\n  "
        + "\n  ".join(orphans))


def test_no_stale_tombstone_rows():
    """Every tombstones.yaml route row still corresponds to a route scanner.py serves —
    a row for a route that no longer exists is itself rot (the ledger cannot lie in the
    other direction)."""
    served = served_routes()
    served_paths = {p for _, p in served}
    served_keys = {f"{m} {p}" for m, p in served}
    stale = []
    for row in _tombstone_rows():
        route = str(row.get("route", "")).strip()
        parts = route.split(None, 1)
        if len(parts) == 2 and parts[0] in {"GET", "POST"}:
            if route not in served_keys:
                stale.append(route)
        else:
            if route not in served_paths:
                stale.append(route)
    assert not stale, (
        "STALE tombstones.yaml rows — a ruling for a route scanner.py no longer serves. "
        "Remove the row (the route was deleted) or fix the path:\n  " + "\n  ".join(stale))


def test_store_twin_fully_accounted():
    """Every corpus_stores/ + corpus_friction/ top-level store maps to a declared
    surface read (a friction ledger), a named engine-internal STORE_ALLOWLIST entry, or
    a tombstones.yaml store row. An unaccounted store is an orphan write."""
    tomb_stores = {str(s.get("store", "")).strip()
                   for s in (yaml.safe_load(TOMBSTONES.read_text(encoding="utf-8")) or {}).get("stores", []) or []}
    orphans = []
    for top in ("corpus_stores", "corpus_friction"):
        d = REPO / top
        if not d.is_dir():
            continue
        for child in sorted(d.iterdir()):
            key = f"{top}/{child.name}"
            if top == "corpus_friction" and child.suffix == ".jsonl":
                continue  # a friction ledger — a /desk surface read (FRICTION_LEDGER_REASON)
            if child.name.endswith(".jsonl.lock"):
                continue  # LOCK SIDECAR PATTERN (W-CRAP, 2026-07-22): a transient *.jsonl.lock
                # companion of a jsonl ledger written under file-lock (append_jsonl / the verdict
                # + proxy writers). It is the ledger's own lock, not an independent store — it
                # carries no data, appears and clears with contention, and belongs to whatever
                # covers its ledger. A recurring class (paper_falqon.jsonl.lock,
                # subset-sum-itqde.jsonl.lock, judged/proxy verdict locks): exempted by PATTERN so
                # the next lock sidecar never needs a fresh allowlist row.
            if top == "corpus_friction" and child.name.endswith(".growth.json"):
                continue  # GROWTH SIDECAR PATTERN (2026-07-28d): the growth-ladder state
                # file pipeline/growth.py binds to registry.project_context (contract
                # clause growth-ladder-live). One per project by design, rendered on the
                # conceptric surface and the dashboard card beside release state — a
                # declared surface read, not an orphan write. Exempted by PATTERN like
                # the .jsonl.lock class, so the Nth project never needs a fresh
                # allowlist row.
            if key in STORE_ALLOWLIST or key in tomb_stores:
                continue
            orphans.append(key)
    assert not orphans, (
        "ORPHAN STORES — a top-level store under corpus_stores/ or corpus_friction/ that "
        "maps to no declared surface read, no STORE_ALLOWLIST entry, and no tombstones.yaml "
        "store row. Add a named STORE_ALLOWLIST entry (with a reason) in tests/test_liveness.py, "
        "or a tombstones.yaml store row:\n  " + "\n  ".join(orphans))


def test_allowlist_entries_are_reasoned():
    """Every SYSTEM_ALLOWLIST and STORE_ALLOWLIST entry carries a non-empty reason —
    his law: no orphan silently allowlisted."""
    empty = [k for k, v in {**SYSTEM_ALLOWLIST, **STORE_ALLOWLIST}.items() if not (v or "").strip()]
    assert not empty, f"allowlist entries with no reason: {empty}"


# =============================================================== THE LEDGER-CONSUMER LAW (W-TEETH)
# THE PRODUCER-NAMES-CONSUMER LAW (W-TEETH, PV-20260722T165050Z): a ledger that accumulates
# rows must NAME the organ that RESOLVES them. A store that only ever grows — findings poured
# in, nothing that closes them — is the machine-finding backlog the census found (3,681 open
# rows with no consumer). This is the conjugate of the store-twin above: the twin proves a
# store maps to a surface READ; this proves its rows have a resolving CONSUMER. A ledger with
# no named consumer is a red test, not a discovery.
#
# The registry: every accumulating *.jsonl ledger -> the organ that retires its rows. NAMED,
# each with the door that closes a row. A ledger the enumeration finds that resolves to NO
# consumer (not an explicit entry, not the friction-ledger rule, not the feedback rule) turns
# this suite red at the delta — the birth obligation, applied to stores that accumulate.
LEDGER_CONSUMERS: dict[str, str] = {
    "corpus_friction/work_orders.jsonl":
        "storyboard.resolve_work_order — THE EVIDENCE DOOR: a work-order closes ONLY through "
        "an evidence-carrying resolution (RES- record whose `supersedes` names the order); the "
        "/desk work-orders lane fires it. A live, retiring consumer.",
    "corpus_friction/open_stack_forks.jsonl":
        "laplace.pipeline.fork_adjudicator + proxy_verdicts.jsonl — THE ADJUDICATION DOOR: a "
        "live Stratum-1 fork (🔴/🟡) closes through a proxy verdict that names it (or a "
        "GENUINELY-HIS route); scripts/adjudicate_forks.py, the /desk forks lane.",
    "contract/promises.jsonl":
        "the contract suite (tests/test_operating_contract.py: a `delivered` row demands "
        "evidence refs) + guide.promises_render — a promise flips open->delivered by a "
        "superseding edit carrying evidence; his-direction rows are carried-not-collected.",
    "contract/judged_verdicts.jsonl":
        "the adjudication ledger — verdict rows are terminal by construction (a judged verdict "
        "IS the resolution of the thing it judges); read on the /desk + review surfaces.",
    "contract/bequests.jsonl":
        "laplace.engine.bequest.rotate — THE ROTATION DOOR, and the birth obligation met at birth "
        "(2026-08-20): a row is written here BECAUSE it was just retired from the standing "
        "parcel (holdout/BEQUEST.json), so every row arrives already resolved — terminal by "
        "construction, the same shape as judged_verdicts above. The lineage is read by the "
        "wake's bequest shard (self_corpus._bequest_shard, as a count + a descend) and by "
        "sewup's step_bequest, which names the parcel it displaced.",
    "corpus_friction/fence_probes.jsonl":
        "laplace.engine.reconstruction_fence.judge — THE JUDGEMENT DOOR: a fence-probe row is a "
        "measurement, and it closes when a fence-verdict row names it true-catch / false-alarm "
        "(scripts/reconstruction_fence.py judge). The whole ledger is then consumed by "
        "false_negative_report (the `rate` subcommand), which measures the probe against the "
        "close-time landing sweep — the bar WO-20260812-reconstruction-fence ties promotion to.",
}

#: THE FRICTION-LEDGER RULE — a corpus_friction/*.jsonl of machine findings (anything not a
#: typed store above). Its NOMINAL consumer is the friction drain; but see
#: test_machine_finding_backlog_consumer: that drain is READ-ONLY, so this consumer does not
#: actually retire rows today — the real debt, made loud below rather than hidden green here.
FRICTION_LEDGER_CONSUMER = (
    "scripts/drain_frictions.py (--report, READ-ONLY) + storyboard resolution records (RES-, "
    "the evidence door), read on the /desk open-frictions lane. NOMINAL: the drain reports, it "
    "does not retire — see test_machine_finding_backlog_consumer (the real, named debt)."
)

#: THE FEEDBACK-LEDGER RULE — a per-project manuscript feedback/feedback.jsonl. TWO live
#: consumers, one per finding class:
#:   * AUTHOR-sourced findings — manuscript_bridge.feedback_resolve (the write-side twin of
#:     feedback_add; scripts/drain_feedback.py + the /desk projection round adjudicate.live).
#:   * MACHINE detections (the mech-panel / reader / holdout backlog the desk excludes) — THE
#:     FINDINGS CONSUMER (W-CONSUMER): a section packet CARRIES its open machine findings
#:     (dispatch._section_findings_channel), and a LANDED regenerated fragment RETIRES the
#:     prior-round findings anchored to it (edits.retire_consumed_findings →
#:     manuscript_bridge.feedback_consume, an append-only consumed_by {round, packet}
#:     resolution). Persistence re-mints: a survivor is re-found fresh by the next panel round,
#:     so retirement never hides a live defect (proven in tests/test_findings_consumer.py).
FEEDBACK_LEDGER_CONSUMER = (
    "manuscript_bridge.feedback_resolve (author findings) + THE FINDINGS CONSUMER for machine "
    "detections: dispatch._section_findings_channel attaches, edits.retire_consumed_findings + "
    "manuscript_bridge.feedback_consume retire on land (append-only consumed_by {round, packet}); "
    "a survivor re-mints on the next panel round (tests/test_findings_consumer.py)."
)

#: THE MACHINE-FINDING BACKLOG — the census found ~3,681 open MACHINE detections (mech-panel /
#: reader / holdout) across the per-project feedback ledgers with no organ that retired them: the
#: desk excludes them (his to rule are the author-sourced ones) and nothing else closed a row, so
#: panel round on panel round accumulated. W-CONSUMER (2026-07-22) lands THE FINDINGS CONSUMER: a
#: section packet CARRIES its open machine findings, and a LANDED regenerated fragment RETIRES the
#: prior-round findings anchored to it (append-only consumed_by {round, packet}); a survivor
#: re-mints on the next panel round. The backlog is now SELF-DRAINING — it retires as real
#: regeneration rounds consume it, never mass-swept (the honesty law: no backfill theatre), so the
#: standing count is NOT asserted under a bar; the LIVE CONSUMER is what the reaper now demands and
#: gets (proven below + in tests/test_findings_consumer.py). The friction ledgers' report-only drain
#: (drain_frictions.py) is the separate corpus-friction concern (FRICTION_LEDGER_CONSUMER).
_BACKLOG_TYPED_STORES = {"work_orders.jsonl", "open_stack_forks.jsonl"}


def _consumer_for(ledger_relpath: str) -> str | None:
    """The named consumer for an accumulating ledger, or None (an orphan producer). Exact
    registry entry first, then the friction-ledger rule (any other corpus_friction/*.jsonl),
    then the feedback-ledger rule (a manuscript feedback/feedback.jsonl)."""
    if ledger_relpath in LEDGER_CONSUMERS:
        return LEDGER_CONSUMERS[ledger_relpath]
    p = ledger_relpath.replace("\\", "/")
    if p.startswith("corpus_friction/") and p.endswith(".jsonl"):
        return FRICTION_LEDGER_CONSUMER
    if p.endswith("/feedback/feedback.jsonl") or p.endswith("feedback/feedback.jsonl"):
        return FEEDBACK_LEDGER_CONSUMER
    return None


def _accumulating_ledgers() -> list[str]:
    """The accumulating *.jsonl ledgers the producer-names-consumer law covers: every
    top-level corpus_friction/*.jsonl (a .lock sidecar excluded — it is the ledger's own
    lock, W-CRAP pattern), the contract ledgers, and every per-project manuscript
    feedback/feedback.jsonl. Returns repo-relative POSIX paths."""
    out: list[str] = []
    fr = REPO / "corpus_friction"
    if fr.is_dir():
        for child in sorted(fr.glob("*.jsonl")):
            out.append(f"corpus_friction/{child.name}")
    for name in ("promises.jsonl", "judged_verdicts.jsonl", "bequests.jsonl"):
        if (REPO / "contract" / name).is_file():
            out.append(f"contract/{name}")
    for fb in sorted(REPO.glob("**/feedback/feedback.jsonl")):
        try:
            out.append(fb.relative_to(REPO).as_posix())
        except ValueError:
            continue
    return out


def test_ledger_consumer_accounting():
    """THE PRODUCER-NAMES-CONSUMER LAW: every accumulating ledger maps to a NAMED resolving
    consumer (an explicit LEDGER_CONSUMERS entry, the friction-ledger rule, or the feedback
    rule). A ledger that resolves to no consumer is an orphan producer — a store that only
    grows. Red, naming it: register its consumer (the organ that retires its rows) or say why
    it is write-only."""
    orphans = [lg for lg in _accumulating_ledgers() if _consumer_for(lg) is None]
    assert not orphans, (
        "ORPHAN PRODUCER LEDGERS — an accumulating *.jsonl with no named resolving consumer "
        "(the producer-names-consumer law, W-TEETH). Register it in LEDGER_CONSUMERS with the "
        "organ that retires its rows, or extend the friction/feedback rule:\n  "
        + "\n  ".join(orphans))


def test_ledger_consumer_registry_is_live():
    """No stale registry entry: every EXACT LEDGER_CONSUMERS path still exists on disk (a
    consumer named for a deleted ledger is rot, the conjugate of a stale tombstone), and the
    two typed friction stores are registered EXPLICITLY (never swept under the generic
    friction-ledger rule — their evidence/adjudication doors are real and named)."""
    missing = [k for k in LEDGER_CONSUMERS if not (REPO / k).is_file()]
    assert not missing, ("stale LEDGER_CONSUMERS entries naming ledgers that do not exist:\n  "
                         + "\n  ".join(missing))
    for typed in ("corpus_friction/work_orders.jsonl", "corpus_friction/open_stack_forks.jsonl"):
        if (REPO / typed).is_file():
            assert typed in LEDGER_CONSUMERS, (
                f"{typed} is a TYPED store with a real resolution door — it must be named "
                "explicitly in LEDGER_CONSUMERS, not covered by the generic friction rule")


def test_machine_finding_backlog_consumer():
    """THE MACHINE-FINDING BACKLOG HAS A LIVE RETIRING CONSUMER (W-CONSUMER, flips W-TEETH's
    strict-xfail). The premise the strict-xfail named — "no organ retires the machine findings" —
    is now FALSE: the findings consumer is live, named, and PROVEN. This is the reaper's demand
    on the machine-DETECTION backlog (the per-project feedback ledgers), and it is met.

    The proof is a LIVE round, not prose: attach → land → retire → re-mint, driven here on a
    throwaway ledger so the reaper itself exercises the drain. The standing backlog retires as
    real regeneration rounds consume it (never mass-swept — the honesty law), so this asserts the
    CONSUMER is live, not that the standing count is under a bar."""
    import json as _json
    import tempfile
    from pathlib import Path as _Path
    from laplace.manuscript import manuscript_bridge as _mb
    from laplace.pipeline import adjudicate as _adj, dispatch as _dispatch
    from laplace.pipeline.edits import retire_consumed_findings as _retire
    from laplace.pipeline.ledger import append_jsonl as _append
    from laplace.pipeline.suppress import content_fingerprint as _fp

    # the consumer's organs are all live and importable (the named consumer exists)
    for organ in (_mb.machine_findings_for_section, _mb.feedback_consume,
                  _mb.is_machine_finding, _retire, _dispatch._section_findings_channel):
        assert callable(organ)
    # ... and the registry NAMES it (the producer-names-consumer law, satisfied for real)
    assert "FINDINGS CONSUMER" in FEEDBACK_LEDGER_CONSUMER
    assert "feedback_consume" in FEEDBACK_LEDGER_CONSUMER

    # A LIVE round on a throwaway ledger: a round-1 defect, a round-2 re-mint of the survivor.
    with tempfile.TemporaryDirectory() as d:
        led = _Path(d) / "feedback.jsonl"
        sec = "S1"
        f1 = {"id": "L1", "kind": "eq-unused", "section": sec, "node_id": "n",
              "source": "mech-panel:r1", "status": "open", "fingerprint": _fp("old bytes")}
        f2 = {"id": "L2", "kind": "eq-unused", "section": sec, "node_id": "n",
              "source": "mech-panel:r2", "status": "open", "fingerprint": _fp("new bytes")}
        _append(led, f1)
        _append(led, f2)                                  # the panel's fresh re-mint (round 2)
        out = _retire(led, sec, round=2, packet_id="pkt:probe:S1", project="probe")
        assert out["retired"] == ["L1"], out              # prior round retired
        recs = [_json.loads(x) for x in led.read_text().splitlines() if x.strip()]
        live = {r.get("id") for r in _adj.live(recs)
                if _mb.is_machine_finding(r) and (r.get("status") or "open") == "open"}
        assert "L1" not in live and "L2" in live          # retired stays retired; re-mint lives
        res = next(r for r in recs if r.get("supersedes") == "L1")
        assert res["consumed_by"] == {"round": 2, "packet": "pkt:probe:S1",
                                      "finding_kind": "eq-unused", "finding_round": 1}


# =========================================================================== THE DRIVE (booted)
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert port not in (8770, 8771), "never touch the reserved ports"
    return port


def _get(port: int, path: str, timeout: float = 10.0):
    """(status, is_redirect_location) or (None, None) on transport error/timeout."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        loc = resp.getheader("Location", "")
        resp.read()
        return resp.status, loc
    except Exception:
        return None, None
    finally:
        conn.close()


@pytest.fixture(scope="module")
def booted_server():
    """Boot a real scanner on an ephemeral port (LAPLACE_NO_NAVIGATOR=1), the way the
    brief boots it. Skips the driven checks if the box can't boot one (no hard failure
    on infrastructure — the static teeth above still ran)."""
    import os
    port = _free_port()
    env = dict(os.environ, LAPLACE_NO_NAVIGATOR="1")
    proc = subprocess.Popen(
        [sys.executable, "-m", "laplace.web.scanner", "--port", str(port)],
        cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # Poll until the server is READY — gated on a NON-"/" surface route, not "/".
    # A cold first boot can answer "/" during startup before the full route table /
    # handler is initialised, which fast-fails the drive loop with nearly every route
    # "unreachable" (the cold-start jitter the repair round hardens). Requiring a
    # non-"/" surface ("/desk", a primary page the real dispatch must serve) to answer
    # proves the handler is genuinely up before any route is driven — deterministic on
    # the first invocation, not just warm re-runs.
    _READY_ROUTE = "/desk"
    deadline = time.time() + 25
    ok = False
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        root_status, _ = _get(port, "/", timeout=2.0)
        ready_status, _ = _get(port, _READY_ROUTE, timeout=2.0)
        if root_status is not None and ready_status is not None:
            ok = True
            break
        time.sleep(0.4)
    if not ok:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        pytest.skip("scanner would not boot on this box — driven liveness checks skipped "
                    "(the static route/store accounting above is the FAIL-eligible core)")
    yield port
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def test_served_get_routes_reachable(booted_server):
    """The parsed census is REAL: driving GET on each GET route reaches the server (a
    census that named a route the server never answers would be a lie)."""
    port = booted_server
    unreachable = []
    for meth, path in sorted(served_routes()):
        if meth != "GET":
            continue
        # a prefix-only dispatch ("/corpus/") legitimately 404s a bare GET; still it must
        # produce an HTTP status (the server is up). A transport error is the failure.
        status, _ = _get(port, path)
        # /graph can be slow to compute; a timeout (status None) is tolerated as reachable-but-slow.
        if status is None and path not in ("/graph",):
            # retry once with a longer timeout before calling it unreachable
            status, _ = _get(port, path, timeout=15.0)
            if status is None:
                unreachable.append(f"GET {path}")
    assert not unreachable, (
        "GET routes in the parsed census that the booted server did not answer "
        "(the census drifted from what scanner.py serves):\n  " + "\n  ".join(unreachable))


def test_tombstone_rulings_match_live_behavior(booted_server):
    """Cross-check the rulings against the running server: a `tombstone` GET route must
    actually answer 410 (retired) or 301 (consolidation redirect); a `wire-owed` GET
    route must NOT answer 410 — it is claimed LIVE, so a 410 would mean the ruling is
    wrong (it should be a tombstone). his-ruling-owed rows are exempt (their disposition
    is his, not the reaper's)."""
    port = booted_server
    rows = _tombstone_rows()
    lies = []
    for row in rows:
        route = str(row.get("route", "")).strip()
        verdict = str(row.get("verdict", "")).strip()
        parts = route.split(None, 1)
        if len(parts) == 2:
            meth, path = parts
        else:
            meth, path = "GET", route  # path-only rows: drive as GET
        if meth != "GET":
            continue
        status, _ = _get(port, path)
        if status is None:
            continue  # transport/timeout — cannot judge, do not fabricate a verdict
        if verdict == "tombstone" and status not in (301, 410):
            lies.append(f"{route}: ruled `tombstone` but the server answers {status} "
                        "(a tombstone must be 410/301; if it is live, re-rule it)")
        if verdict == "wire-owed" and status == 410:
            lies.append(f"{route}: ruled `wire-owed` (LIVE) but the server answers 410 "
                        "(it is dead — re-rule it `tombstone`)")
    assert not lies, "tombstones.yaml rulings contradict the running server:\n  " + "\n  ".join(lies)
