"""The operating contract, enforced (contract/README.md; DESIGN_2026-07-21 KEYSTONE).

Reads ``contract/surfaces/*.yaml`` + ``contract/promises.jsonl`` and generates one check
per clause. A clause marked ``red: <wave>`` is honestly red today without blocking the
suite, and LOUD the moment the behavior lands without its marker being flipped — the
wave's PR must turn the marker green.

G5 — THE GENERALIZED RUNNER (ARMING_2026-07-22_the-growth-stage.md §3;
PRM-20260722-bars-on-clauses). The runner iterates EVERY surface yaml — not just desk +
pipeline — and generates one test per structural clause and per counts law. Honest scope
(the arming's note 4): generalizing the loader is NOT mere iteration — a red clause only
goes loud through a *bespoke failing assertion body* (a no-op body under strict xfail
xpasses backwards). Each clause's probe lives in :mod:`tests.clause_runners`, keyed by
clause id; a clause with no bespoke verifier yet gets an honest SKIP-with-reason, never a
false green.

THE THREE HONEST STATES a red clause can render (never a silent partial delivery):
  * xfail-red — the behavioral floor is absent (the wave has not landed);
  * xfail-<bar>-verdict-owed — the floor holds but the clause carries ``bar: judged|author``
    and no resolving STANDS verdict is banked (production never self-certifies);
  * XPASS (a hard fail) — the floor holds AND (for a barred clause) a resolving verdict is
    banked, yet the marker still says red: FLIP THE MARKER.

THE BAR LAW: a clause's ``bar`` (mechanical | judged | author) names whose verdict can
flip it. The clause-runner is competent to flip only ``mechanical``. A ``judged``/``author``
clause needs a banked verdict resolving in ``contract/judged_verdicts.jsonl`` (read only
through :func:`laplace.engine.superego.verdicts_for`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clause_runners  # noqa: E402  (sibling helper; tests/ has no __init__)

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "contract"
SURFACES = sorted((CONTRACT / "surfaces").glob("*.yaml"))


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _red(clause: dict, ident: str):
    """The desk verb-axis marker idiom (kept for :func:`test_desk_verb...`): xfail ONLY when
    the yaml row carries ``red``, so flipping the marker on delivery turns the test green."""
    mark = ()
    if clause.get("red"):
        mark = (pytest.mark.xfail(
            strict=True,
            reason=f"RED - owed by {clause['red']} (contract clause, flip on delivery)"),)
    return pytest.param(clause, id=ident, marks=mark)


# ---------------------------------------------------------------------------
# Contract hygiene - the lookup itself stays well-formed
# ---------------------------------------------------------------------------
def test_every_surface_contract_is_well_formed():
    assert SURFACES, "contract/surfaces/ is empty - the lookup died"
    for p in SURFACES:
        doc = _load(p)
        assert doc.get("surface"), f"{p.name}: no surface name"
        assert doc.get("purpose"), f"{p.name}: no purpose line"


def test_promises_ledger_rows_are_typed_and_delivered_rows_carry_evidence():
    rows = [json.loads(line) for line in
            (CONTRACT / "promises.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows, "the promise ledger is empty"
    for r in rows:
        if r.get("record") == "defer":
            # the aging-teeth defer note row (W-TEETH, ledger-local by design): a typed
            # sidecar record, not a promise — it must carry its own spine.
            for key in ("target", "defer_until", "deferred_by"):
                assert r.get(key), f"defer note: missing {key}"
            continue
        if r.get("record") == "note":
            # a sidecar annotation on a promise (partial supersession, amendment record):
            # typed like the defer, never a promise row (grown 2026-08-07; the ledger cut
            # NOTE- rows before the runner typed them).
            for key in ("id", "target", "ts", "note", "author"):
                assert r.get(key), f"note row: missing {key}"
            continue
        if r.get("record") == "undefer":
            # the defer's conjugate: a deferral's gate fired and the row is live again.
            for key in ("id", "target", "ts", "reason", "released_by"):
                assert r.get(key), f"undefer row: missing {key}"
            continue
        if r.get("record") == "resolution":
            # a promise discharge as its own typed row (ruled 2026-08-23, the accounting
            # day, both seats: WO-20260821-promises-ledger-untypes-resolutions taken by
            # its own cheap reading - the stores are append-only either way, so the
            # discharge lives beside the promise, keyed like the note/defer sidecars,
            # and its text names the run that observed the delivery).
            for key in ("id", "target", "ts", "status", "text"):
                assert r.get(key), f"resolution row: missing {key}"
            continue
        for key in ("id", "date", "ask", "owner", "status"):
            assert r.get(key), f"{r.get('id', '?')}: missing {key}"
        assert r["status"] in ("open", "delivered", "declined"), r["id"]
        if r["status"] == "delivered":
            assert r.get("evidence"), f"{r['id']}: delivered without evidence - the ledger lies"
            # The superego consumption law (his ruling 2026-07-22; PRM-20260722-bars-on-
            # clauses): a delivered promise must name a judged verdict - a SEV- ref that
            # resolves in contract/judged_verdicts.jsonl - so no promise flips on its
            # builder's word. The ONLY grandfathered rows are the two deliveries that
            # predate the bar, frozen here BY ID - never by creation date (the G0
            # judge's catch: a date gate exempted every pre-bar-created promise however
            # late it was delivered).
            if r["id"] not in ("PRM-20260721-window-spam", "PRM-20260721-false-stale"):
                sev_path = CONTRACT / "judged_verdicts.jsonl"
                sev_ids = {json.loads(line)["id"] for line in
                           sev_path.read_text(encoding="utf-8").splitlines()
                           if line.strip()} if sev_path.exists() else set()
                cited = [e for e in r["evidence"] if isinstance(e, str) and "SEV-" in e]
                assert cited, (
                    f"{r['id']}: a bar-era delivery names no SEV- verdict ref - "
                    "production never self-certifies")
                assert any(sid in e for e in cited for sid in sev_ids), (
                    f"{r['id']}: its SEV- ref does not resolve in "
                    "contract/judged_verdicts.jsonl")


# ---------------------------------------------------------------------------
# Desk verb axis (P3) — a verb is live or it is absent. (Verbs are a different axis
# from the structural clauses the generalized runner below covers.)
# ---------------------------------------------------------------------------
_DESK = _load(CONTRACT / "surfaces" / "desk.yaml")


@pytest.mark.parametrize("verb", [
    _red(v, f"desk-verb-{v['class']}-{v['name']}") for v in _DESK["verbs"]
])
def test_desk_verb_declared_live_is_not_deferred(verb):
    """P3: a verb is live or it is absent. Declared-live verbs must not sit in the
    deferred table (a served button that always 422s is a decorative lie)."""
    from laplace.web import desk
    if verb["state"] != "live":
        pytest.skip("absent verbs are checked by the not-served clause (fleet, Wave F)")
    assert (verb["class"], verb["name"]) not in desk._DEFERRED_VERBS, (
        f"{verb['class']}.{verb['name']} is served but deferred - decorative verb")


# ---------------------------------------------------------------------------
# THE GENERALIZED STRUCTURAL RUNNER — one test per structural clause across EVERY surface.
# ---------------------------------------------------------------------------
def _structural_params():
    out = []
    for p in SURFACES:
        doc = _load(p)
        surface = doc.get("surface") or p.stem
        for clause in (doc.get("structural") or []):
            if not isinstance(clause, dict) or not clause.get("clause"):
                continue
            out.append(pytest.param(surface, clause, id=f"{surface}::{clause['clause']}"))
    return out


def _run_structural_clause(surface: str, clause: dict) -> None:
    cid = clause["clause"]
    red = clause.get("red")
    bar = clause.get("bar")
    verifier = clause_runners.STRUCTURAL_VERIFIERS.get(cid)

    if verifier is None:
        # honest SKIP-with-reason naming the missing verifier — never a false green (a no-op
        # body under strict xfail xpasses backwards; the arming names that trap).
        pytest.skip(
            f"no bespoke verifier for '{surface}::{cid}' yet — author its probe before this "
            f"clause can be enforced (red={red!r}, bar={bar!r})")

    # run the behavioral probe; an AssertionError means the FLOOR is absent (xfail-red).
    try:
        verifier(REPO)
        floor_holds, msg = True, ""
    except AssertionError as e:
        floor_holds, msg = False, str(e)

    if not floor_holds:
        if red:
            pytest.xfail(f"xfail-red · {cid} owed by {red} (bar:{bar or 'mechanical'}) · {msg}")
        pytest.fail(f"{surface}::{cid} is NOT red but its verifier failed: {msg}")

    # the floor holds — apply the bar law for judged/author clauses.
    if bar in ("judged", "author"):
        resolved, why = clause_runners.resolving_verdict(REPO, cid, red, bar)
        if not resolved:
            reason = "judged-verdict-owed" if bar == "judged" else "author-ruling-owed"
            if red:
                pytest.xfail(f"xfail-{reason} · {cid} floor holds (bar:{bar}) · {why}")
            pytest.fail(f"{surface}::{cid} floor holds, bar:{bar}, but no resolving verdict: {why}")
        if red:
            pytest.fail(f"XPASS · {cid} floor holds AND a resolving {bar} verdict is banked, "
                        f"yet still marked red:{red} — FLIP THE MARKER ({why})")
        return  # green: floor + a resolving verdict, marker already flipped

    # mechanical (or unbarred) clause, floor holds.
    if red:
        pytest.fail(f"XPASS · {cid} mechanical floor holds, yet still marked red:{red} — "
                    "FLIP THE MARKER (the behavior landed)")
    return  # green: not red, floor holds


@pytest.mark.parametrize("surface,clause", _structural_params())
def test_structural_clause(surface, clause):
    _run_structural_clause(surface, clause)


# ---------------------------------------------------------------------------
# THE GENERALIZED COUNTS RUNNER — one test per surface declaring law chip-equals-filter.
# Every count is its filter (P2): a chip's number equals the rows the client can reach.
# ---------------------------------------------------------------------------
def _counts_params():
    out = []
    for p in SURFACES:
        doc = _load(p)
        counts = doc.get("counts")
        if isinstance(counts, dict) and counts.get("law"):
            surface = doc.get("surface") or p.stem
            out.append(pytest.param(surface, counts["law"],
                                    id=f"{surface}::counts:{counts['law']}"))
    return out


@pytest.mark.parametrize("surface,law", _counts_params())
def test_counts_law(surface, law):
    assert law == "chip-equals-filter", f"{surface}: unknown counts law {law!r}"
    verifier = clause_runners.COUNTS_VERIFIERS.get(surface)
    if verifier is None:
        pytest.skip(f"no counts verifier for '{surface}::{law}' yet — author one to enforce it")
    try:
        note = verifier(REPO)
    except clause_runners.CountsSkip as e:
        pytest.skip(f"{surface}::{law} not reachable in-process — {e}")
    assert note  # a verified counts law returns its human note
