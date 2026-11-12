"""The growth ladder — the conceptric growth stage's per-project state machine.

The conjugate of :mod:`laplace.pipeline.release` at the *growth* grade (his ruling,
2026-07-22: the growth stage is the seed of all generation AND its interface — one
object). Release drives an assembled artefact ``STAGED -> ... -> RELEASED``; growth
drives the *stock itself* up a ladder whose rungs are the element legs and the
judged/authored gates:

    SEEDED  ->  STOCKED  ->  WIRED  ->  GRADED  ->  READY      (+ REGOALED)

Each rung declares a **bar** (``ARMING_2026-07-22_the-growth-stage.md`` §2), and a
transition *consumes evidence* for that bar — it never asserts the rung on nothing
(the ``candidate_lock.lock_eligible`` pattern release uses at CANDIDATE_LOCKED). The
three bars, structural:

  * **mechanical** — a fact the engine can check itself. ``STOCKED`` demands the
    element-leg floors that land in G3/G4, so in this wave it **FAILS CLOSED** with a
    typed refusal naming the un-built gate (silence never reads as success — his line,
    "green does not mean passed"). ``WIRED`` consumes the REAL connectivity/provenance
    machinery (:func:`verify.check_connectivity` + :func:`corpus_ingest.gaps` over the
    ``PROVENANCE_EXEMPT`` kinds).
  * **judged** — a banked non-builder verdict. ``GRADED`` reads
    :func:`superego.verdicts_for` for a resolving ``STANDS`` verdict whose claim
    identifies THIS project and THIS transition, judge != builder. Production never
    self-certifies; a mechanical green is a floor on judgement, not a pass.
  * **author** — his ruling through an actor-guarded door. ``READY`` needs BOTH a
    judged verdict AND his waiver (an actor-guarded record with ``by`` an author
    actor — a defaulted actor is refused, mirroring desk's ``/desk/act`` guard).
    ``REGOALED`` likewise: a goal-tension card he ruled REGOAL bumps the goal version
    and the ladder resumes at SEEDED-of-the-new-version (growth feeds back into the
    goal — his ruling 4).

**The write discipline** (the arming's §1 critique of release's bare ``write_text``):
the per-project sidecar is written under the dashboard lock pattern — a process-local
:class:`threading.Lock` nested in a cross-process ``FileLock`` — around the whole
read-modify-write, and committed with ``tmp + os.replace`` so a concurrent transition
from two threads resolves to exactly one winner (the loser gets the forward-only
refusal) and the file never tears.

**Where the sidecar lives:** ``corpus_friction/<name>.growth.json`` — chosen over
release's ``<target_dir>/release/state.json`` because (1) the friction seed ledger
``corpus_friction/<name>.jsonl`` is already written at birth by the New Project door,
so the growth sidecar is its sibling and birth writes both in one place; (2) it is
keyed by project NAME under a flat, always-present dir, so it resolves identically for
a bare scaffold with no compiled artefact (whose ``target_dir`` may be empty) and a
finished paper — the arming's hard requirement; (3) ``corpus_friction/`` is already
the lock home (the dashboard filelock lives there) and ``.gitignore *.lock`` already
covers the ``.growth.json.lock`` sidecar; (4) it is repo-root-fenced by construction
(``root / "corpus_friction" / "<name>.growth.json"`` with a containment belt).

**Reads bind to the registry** (:func:`registry.conceptric_projects` /
:func:`registry.project_states` — G0's one door), NEVER to ``resolve_corpus``.

**Backfill never fakes a rung:** a project with a minted release or ``rounds > 0`` is
never retro-laddered — the absence of a sidecar renders as a plain ``pre_ladder`` null,
not a fake SEEDED on a finished paper (:func:`growth_state`).
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import datetime as _dt
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# the ladder + the bars
# ---------------------------------------------------------------------------

#: the forward ladder, in order. Conjugate to ``release.STATES``.
STATES: tuple[str, ...] = ("SEEDED", "STOCKED", "WIRED", "GRADED", "READY")

#: the reopen-at-this-grade escape hatch (conjugate to ``release.REOPENED``): a
#: goal-tension card ruled REGOAL bumps the goal version and the ladder resumes at
#: SEEDED-of-the-new-version. Reachable only from a state at/after STOCKED (before the
#: stock is stocked there is nothing to regoal — the initial seed is just re-seeded).
REGOALED = "REGOALED"

#: the bar each transition must clear, as data (the arming §2 table). SEEDED is the
#: birth rung (established by :func:`seed`, not climbed into).
BARS: dict[str, str] = {
    "SEEDED": "mechanical",
    "STOCKED": "mechanical",
    "WIRED": "mechanical",
    "GRADED": "judged",
    "READY": "author",
    REGOALED: "author",
}

#: the state a REGOAL resumes the ladder at (its effective ladder index is one below
#: this, so SEEDED is reachable from REGOALED and STOCKED-and-later are not — the
#: single forward step re-seats the new goal version at SEEDED).
_REGOAL_RESUME = "SEEDED"

#: the ladder index at/after which REGOAL is reachable (before this the stock is not
#: yet stocked, so there is nothing to regoal).
_REGOAL_FROM = "STOCKED"


# ---------------------------------------------------------------------------
# small io / time helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _repo_root() -> Path:
    # src/laplace/pipeline/growth.py -> parents[3] == the repo root (matches release).
    return source_tree()


def _safe_name(name: str) -> str:
    """The one name fence: reject empty / path-shaped names (mirrors
    ``registry.resolve``'s check) so a sidecar path can never be a traversal shape."""
    n = (name or "").strip()
    if not n or "/" in n or "\\" in n or ".." in n:
        raise ValueError(f"unsafe or empty project name {name!r} — the growth sidecar "
                         "path is fenced against traversal shapes")
    return n


def _sidecar_path(root: Path | str, name: str) -> Path:
    """``<root>/corpus_friction/<name>.growth.json`` with a containment belt: the
    resolved path must sit under ``<root>/corpus_friction`` (path-fenced under the
    repo root by construction)."""
    root = Path(root).resolve()
    n = _safe_name(name)
    base = (root / "corpus_friction").resolve()
    p = (base / f"{n}.growth.json").resolve()
    if not str(p).startswith(str(base) + os.sep):
        raise ValueError(f"growth sidecar path {p} escapes {base} — refused")
    return p


def _lock_path(sidecar: Path) -> Path:
    # matches ``.gitignore *.lock`` — the transient cross-process lock never travels.
    return sidecar.with_name(sidecar.name + ".lock")


#: process-local serialisation of the sidecar read-modify-write. Nested INSIDE the
#: OS-level FileLock (below) so this process's threads take the critical section one at
#: a time — a bare filelock would let two threads of one process both "hold" it
#: (fcntl locks are per-process). Together: thread-safe AND process-safe. Mirrors
#: ``dashboard._SHARED_WRITE_LOCK``.
_GROWTH_WRITE_LOCK = threading.Lock()


def _read_sidecar(sidecar: Path) -> Optional[dict]:
    if not sidecar.is_file():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _atomic_write(sidecar: Path, obj: dict) -> None:
    """Commit the sidecar with ``tmp + os.replace`` (atomic on POSIX) so a reader
    never sees a half-written file and a concurrent writer never tears it."""
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(sidecar.parent),
                               prefix=sidecar.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False, indent=2))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, sidecar)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# the ladder order — forward-only, skip-allowed (release's model), plus REGOALED
# ---------------------------------------------------------------------------

def _order_index(state: str) -> int:
    if state == REGOALED:
        # resumes at SEEDED: one below the resume point, so SEEDED is the reachable
        # single forward step and the earlier rungs are not (there are none).
        return STATES.index(_REGOAL_RESUME) - 1
    if state not in STATES:
        raise ValueError(f"unknown growth state {state!r}; known: {STATES + (REGOALED,)}")
    return STATES.index(state)


# ---------------------------------------------------------------------------
# the bar readers — each CONSUMES the evidence that flips its rung
# ---------------------------------------------------------------------------

def growth_claim_tag(name: str, to_state: str) -> str:
    """The canonical identifier a judged verdict's ``claim`` must carry to resolve a
    growth transition: ``growth:<name>:<TO_STATE>``. The judged tier banks a verdict
    whose claim contains this tag; the GRADED/READY bars read it back (never a private
    parser — :func:`superego.verdicts_for` is the reader)."""
    return f"growth:{_safe_name(name)}:{to_state}"


def _quote(law: str) -> str:
    return law


def _bar_stocked(root: Path, name: str, evidence: dict) -> None:
    """STOCKED — FAIL CLOSED. The element-leg floors (every load-bearing claim carries
    a typed edge per demanded axis) land in G3/G4; the gate is not built, so this rung
    refuses rather than passing on nothing. Silence never reads as success."""
    raise ValueError(
        "STOCKED refused — gate not built: element-leg floors land in G3/G4 "
        "(every load-bearing claim needs ≥1 typed edge per demanded axis; the "
        "axis floors + coverage gauges are G3/G4's rungs). "
        + _quote("'mechanical work can only go so far ... green does not mean passed' "
                 "— a rung never passes on nothing; silence never reads as success."))


def _bar_wired(root: Path, name: str, evidence: dict) -> None:
    """WIRED — mechanical, on the REAL machinery. The derivation DAG must be connected
    (:func:`verify.check_connectivity` — no spine-unreachable orphan) and every
    provenance gap must be named-or-exempt (:func:`corpus_ingest.gaps`, which already
    excludes the ``PROVENANCE_EXEMPT`` kinds; any surviving gap must be named in
    ``evidence['named_gaps']``). Raises, naming the orphans / unnamed gaps, when the
    fact does not hold — a raised transition is the designed behaviour."""
    from laplace.pipeline import verify

    conn = verify.check_connectivity(name)
    if conn.get("pass") is None:
        raise ValueError(
            f"WIRED cannot be checked for {name!r}: {conn.get('note') or 'no network'} "
            "— the connectivity gate is manual here, and a rung never passes unchecked.")
    orphans = conn.get("orphans") or []
    if orphans:
        raise ValueError(
            f"WIRED refused — the derivation DAG is not connected: "
            f"{len(orphans)} spine-unreachable orphan(s) {orphans[:8]}"
            + (" ..." if len(orphans) > 8 else "") + ". "
            + _quote("a node no spine beat can descend to never appears in the "
                     "projection — wire it or retire it before WIRED."))

    # provenance gaps named-or-exempt: gaps() already drops PROVENANCE_EXEMPT/postulate
    # kinds; whatever survives must be explicitly named in the evidence.
    from laplace.research import corpus_ingest as _ci
    troot = _ci.resolve_corpus(root, name)
    surviving: list[str] = []
    if troot is not None:
        net = _ci.corpus_network(troot, repo_root=root, name=name)
        named = set(evidence.get("named_gaps") or [])
        surviving = [g for g in _ci.gaps(net) if g not in named]
    if surviving:
        raise ValueError(
            f"WIRED refused — {len(surviving)} provenance gap(s) neither exempt nor "
            f"named: {surviving[:8]}"
            + (" ..." if len(surviving) > 8 else "") + ". "
            + _quote("the incompleteness of a derivation sub-tree IS the confabulation "
                     "room — name each surviving gap in evidence['named_gaps'] or close it."))


def _bar_graded(root: Path, name: str, evidence: dict) -> dict:
    """GRADED — judged. A resolving verdict id from ``contract/judged_verdicts.jsonl``:
    ``STANDS``, judge != builder, claim carries this project + this transition
    (:func:`growth_claim_tag`). Read through :func:`superego.verdicts_for` — never a
    private parser. Returns the resolving verdict record. Raises, quoting the law, when
    the evidence is missing or does not resolve."""
    return _resolve_stands_verdict(root, name, evidence, require_tag=growth_claim_tag(name, "GRADED"),
                                   bar="GRADED")


def _resolve_stands_verdict(root: Path, name: str, evidence: dict, *,
                            require_tag: str, bar: str) -> dict:
    from laplace.engine import superego
    vid = str(evidence.get("verdict_id") or "").strip()
    if not vid:
        raise ValueError(
            f"{bar} refused — no verdict_id in evidence. "
            + _quote("production never self-certifies: a judged rung needs a banked "
                     "non-builder verdict, and this door defaults nowhere."))
    # project-scoped read (never a private parser): the tag is the binding identifier.
    proj_tag = f"growth:{_safe_name(name)}"
    rows = superego.verdicts_for(root, claim_substr=proj_tag, limit=200)
    match = next((r for r in rows if r.get("id") == vid), None)
    if match is None:
        raise ValueError(
            f"{bar} refused — no banked verdict {vid!r} whose claim carries {proj_tag!r} "
            "(contract/judged_verdicts.jsonl). "
            + _quote("the claim/station must identify this project and this transition."))
    if require_tag not in str(match.get("claim", "")):
        raise ValueError(
            f"{bar} refused — verdict {vid!r} does not identify this transition "
            f"(claim must carry {require_tag!r}). "
            + _quote("the claim/station must identify this project and this transition."))
    if match.get("verdict") != "STANDS":
        raise ValueError(
            f"{bar} refused — verdict {vid!r} is {match.get('verdict')!r}, not STANDS. "
            + _quote("a REFUTED verdict cannot certify a rung; green does not mean passed."))
    # defensive: bank_verdict already refuses judge==builder, but a rung never trusts
    # its own upstream — re-check through the same actor key the ledger uses.
    if superego._actor_key(str(match.get("judge", ""))) == \
       superego._actor_key(str(match.get("builder", ""))):
        raise ValueError(
            f"{bar} refused — verdict {vid!r} has judge == builder. "
            + _quote("'production never self-certifies' — a done-claim must be judged "
                     "by a non-builder instance to count."))
    # full-spine re-validation (the G2 judge's catch): a raw ledger row that would be
    # refused at the bank door (a STANDS carrying served=no, a fatal defect, a broken
    # questions spine) must be refused here too — the ladder holds the door's whole
    # law, not three fields of it.
    try:
        superego._validate_verdict({k: v for k, v in match.items()
                                    if k not in ("id", "ts")})
    except ValueError as exc:
        raise ValueError(
            f"{bar} refused — verdict {vid!r} fails the verdict spine: {exc}. "
            + _quote("a row the door would refuse certifies nothing, wherever "
                     "it was written."))
    return match


def _require_author_ruling(evidence: dict, *, bar: str, verb: Optional[str] = None) -> dict:
    """The author actor guard (mirrors desk's ``/desk/act``): the ruling must be an
    actor-guarded record whose ``by`` is an author actor and non-empty. A DEFAULTED /
    missing actor is refused BEFORE anything advances, and a non-author actor cannot
    stand in for his waiver. Returns ``{by, ref, verb?}``. Raises, quoting the law."""
    from laplace.manuscript.manuscript_bridge import AUTHOR_ACTORS
    ruling = evidence.get("ruling")
    if not isinstance(ruling, dict):
        raise ValueError(
            f"{bar} refused — evidence['ruling'] must be an actor-guarded record "
            "{by, ref}. " + _quote("an author rung is his to flip, through his door."))
    by = str(ruling.get("by") or "").strip()
    if not by:
        raise ValueError(
            f"{bar} refused — by (explicit actor) is required: this door defaults "
            "nowhere, and an unattributed ruling must never flip an author rung. "
            + _quote("production never self-certifies."))
    if by.strip().lower() not in AUTHOR_ACTORS:
        raise ValueError(
            f"{bar} refused — {by!r} is not an author actor {sorted(AUTHOR_ACTORS)}; "
            "his waiver cannot be stood in for. "
            + _quote("the author rung is HIS ruling of every surviving gap."))
    ref = str(ruling.get("ref") or ruling.get("note") or "").strip()
    if not ref:
        raise ValueError(
            f"{bar} refused — the ruling carries no ref/note; a bare actor is not a "
            "waiver. " + _quote("his waiver names what it waives."))
    if verb is not None and str(ruling.get("verb") or "").strip().upper() != verb:
        raise ValueError(
            f"{bar} refused — the ruling verb must be {verb!r} "
            f"(got {ruling.get('verb')!r}). "
            + _quote("a goal-tension card ruled REGOAL is what supersedes the goal."))
    out = {"by": by, "ref": ref}
    if verb is not None:
        out["verb"] = verb
    return out


# ---------------------------------------------------------------------------
# the write door — birth, forward transition, regoal
# ---------------------------------------------------------------------------

def _birth_queues() -> dict:
    """The demand-audit queues populated AT BIRTH — the token-free demand FORM walked
    before any compile exists (the birth bridge's queue-population conjunct,
    ``birth-lands-on-the-ladder``). A fresh scaffold has no compiled substrate, so the
    substrate audit (``demand.audit``, which needs a rendered/atomised net) cannot run;
    what CAN run, deterministically and token-free, is the walk of the demand REGISTRY
    itself — every demand of the FORM object grouped into its CONTENT/FORM/TENSION queue,
    each row carrying its ring and owning check. This is the pre-compile audit: the
    queues name WHAT will be checked (the FORM), rendered ``pre-compile`` until the
    first compile lets the substrate audit sharpen each row into red / floor-holds /
    judged-pending. The word ``passed`` never appears — a birth queue is all-owed by
    construction. Deterministic, no net, no model, never raises."""
    from laplace.pipeline import demand
    friction: dict[str, list[dict]] = {f: [] for f in demand.FRICTION_TYPES}
    for d in demand.DEMANDS:
        oc = d["owning_check"]
        stance = ("judged-pending" if oc.startswith("oracle:")
                  else "pre-compile")   # a mechanical/rendered row is owed until compiled
        friction.setdefault(d["default_friction_type"], []).append({
            "demand_id": d["id"], "ring": d["ring"], "owning_check": oc,
            "goal_activation": d["goal_activation"], "stance": stance,
        })
    counts = {f: len(rows) for f, rows in friction.items()}
    return {
        "audit": "registry-skeleton",
        "populated_at": "birth",
        "n_demands": len(demand.DEMANDS),
        "friction": friction,
        "counts": counts,
        "note": "the demand FORM walked at birth (token-free, pre-compile); every row is "
                "owed until the first compile lets the substrate audit sharpen it — a birth "
                "queue never reads 'passed'.",
    }


def seed(root: Path | str, name: str, *, by: Optional[str] = None) -> dict:
    """Birth: establish the sidecar at SEEDED (goal_version 1) AND populate the demand
    queues (:func:`_birth_queues`). Called by the New Project door inside its existing
    lock. Idempotent — a project already on the ladder is returned unchanged, never
    clobbered back to SEEDED (a re-birth would erase a climb); a legacy sidecar missing
    the birth queues is back-filled with them in place (additive, never a state change).
    Fenced on name-safety only (the caller has already validated + created the project);
    membership binds on the READ path, not here (the registry row may be written in the
    same critical section)."""
    root = Path(root).resolve()
    name = _safe_name(name)
    sidecar = _sidecar_path(root, name)
    with _GROWTH_WRITE_LOCK:
        from filelock import FileLock
        with FileLock(str(_lock_path(sidecar)), timeout=30):
            existing = _read_sidecar(sidecar)
            if existing is not None and existing.get("state"):
                # additive back-fill: an already-laddered project that predates the birth
                # queues gets them without any state/rung change (never clobbered).
                if not existing.get("queues"):
                    existing["queues"] = _birth_queues()
                    _atomic_write(sidecar, existing)
                return existing
            now = _now()
            side = {
                "project": name,
                "state": "SEEDED",
                "goal_version": 1,
                "bar": BARS["SEEDED"],
                "created": now,
                "updated": now,
                # the demand audit runs ONCE at birth, populating the queues before any
                # compile exists (the birth bridge's queue conjunct).
                "queues": _birth_queues(),
                "history": [{"from": None, "to": "SEEDED", "bar": BARS["SEEDED"],
                             "ts": now, "by": (by or "dashboard-new-project"),
                             "note": "birth: the ladder begins, the demand queues populated"}],
            }
            _atomic_write(sidecar, side)
            return side


def current_growth_state(root: Path | str, name: str) -> Optional[str]:
    """The current rung (the sidecar's ``state``), or ``None`` when the project has no
    sidecar (never seeded / pre-ladder). A plain read, no fence beyond name-safety."""
    side = _read_sidecar(_sidecar_path(root, name))
    return side.get("state") if side else None


def transition(root: Path | str, name: str, to_state: str, *,
               evidence: Optional[dict] = None, by: Optional[str] = None) -> dict:
    """Advance the growth ladder one climb, enforcing forward-only order AND the target
    rung's bar. The whole read-modify-write runs under the lock (thread lock nested in
    a cross-process FileLock) and commits with ``tmp + os.replace``, so two concurrent
    transitions resolve to exactly one winner and the file never tears.

    Raises ``ValueError`` on any illegal transition — an unknown state, a backward /
    same-rung slide (forward-only), an un-seeded project, or an unmet bar (the refusal
    quotes the law it serves). ``REGOALED`` is not a forward target here — call
    :func:`regoal`.

    ``by`` is the actor performing the climb (recorded on the history row). The AUTHOR
    rungs additionally require the actor-guarded ``evidence['ruling']`` — see
    :func:`_require_author_ruling`.
    """
    root = Path(root).resolve()
    name = _safe_name(name)
    evidence = dict(evidence or {})
    if to_state == REGOALED:
        raise ValueError("transition() does not target REGOALED; call regoal(root, name, ...)")
    if to_state not in STATES:
        raise ValueError(f"unknown target growth state {to_state!r}; known: {STATES}")

    sidecar = _sidecar_path(root, name)
    with _GROWTH_WRITE_LOCK:
        from filelock import FileLock
        with FileLock(str(_lock_path(sidecar)), timeout=30):
            side = _read_sidecar(sidecar)
            if side is None or not side.get("state"):
                raise ValueError(
                    f"{name!r} is not on the growth ladder (no sidecar) — seed() it "
                    "at birth before a transition.")
            cur = side["state"]
            # forward-only (skip-allowed, release's model): STOCKED is a real rung whose
            # bar fails closed this wave, so the real G2 climb routes around it while
            # each targeted rung still enforces its own bar.
            if _order_index(to_state) <= _order_index(cur):
                raise ValueError(
                    f"illegal growth transition {cur} -> {to_state}: forward-only "
                    "(the ladder never slides backward; regoal() is the only reopen).")

            # --- the bar for THIS rung consumes its evidence -----------------------
            evidence_ref: dict[str, Any] = {}
            ruling_by = by
            if to_state == "STOCKED":
                _bar_stocked(root, name, evidence)                      # always raises
            elif to_state == "WIRED":
                _bar_wired(root, name, evidence)
                evidence_ref = {"gate": "connectivity+gaps",
                                "named_gaps": list(evidence.get("named_gaps") or [])}
            elif to_state == "GRADED":
                v = _bar_graded(root, name, evidence)
                evidence_ref = {"verdict_id": v.get("id"), "station": v.get("station"),
                                "judge": v.get("judge")}
            elif to_state == "READY":
                # BOTH: a judged verdict for this project AND his waiver.
                v = _resolve_stands_verdict(
                    root, name, evidence,
                    require_tag=f"growth:{name}", bar="READY")
                ruling = _require_author_ruling(evidence, bar="READY")
                ruling_by = ruling["by"]
                evidence_ref = {"verdict_id": v.get("id"), "judge": v.get("judge"),
                                "waiver_by": ruling["by"], "waiver_ref": ruling["ref"]}

            # --- commit (refs-only history: no blobs, the seal holds) --------------
            now = _now()
            entry = {"from": cur, "to": to_state, "bar": BARS[to_state], "ts": now,
                     "by": ruling_by, "evidence": evidence_ref}
            if evidence.get("note"):
                entry["note"] = str(evidence["note"])
            side["state"] = to_state
            side["bar"] = BARS[to_state]
            side["updated"] = now
            side.setdefault("history", []).append(entry)
            _atomic_write(sidecar, side)
            return side


def regoal(root: Path | str, name: str, *, evidence: Optional[dict] = None,
           by: Optional[str] = None) -> dict:
    """Reopen at the growth grade (the conjugate of ``release.reopen``): a goal-tension
    card he ruled REGOAL bumps the sidecar's goal version and the ladder resumes at
    SEEDED-of-the-new-version. Author-gated (``evidence['ruling']`` with an author actor
    and ``verb == 'REGOAL'``; a defaulted actor is refused). Reachable only from a state
    at/after STOCKED (before the stock is stocked there is nothing to regoal).

    The pairing debt (the G2 judge's catch): the version bump here is
    not the goal-node supersede — the substrate half (a goal-v2 ``add-node`` carrying
    ``supersedes`` through the rewire ledger, landed by G1) is the caller's obligation,
    and the full REGOAL → supersede → dirty-scoped re-audit loop is G6's deliverable.
    Until the caller banks that record, the sidecar carries ``pending_goal_supersede``
    so the divergence between sidecar version and live goal node is VISIBLE, never
    silent. Pass ``evidence['supersede_record_id']`` (the RW- id of the banked goal-v2
    record) to clear the flag at regoal time.

    Raises ``ValueError`` when the project is un-seeded, when the current rung is below
    STOCKED, or when the author ruling is missing/defaulted (quoting the law)."""
    root = Path(root).resolve()
    name = _safe_name(name)
    evidence = dict(evidence or {})
    sidecar = _sidecar_path(root, name)
    with _GROWTH_WRITE_LOCK:
        from filelock import FileLock
        with FileLock(str(_lock_path(sidecar)), timeout=30):
            side = _read_sidecar(sidecar)
            if side is None or not side.get("state"):
                raise ValueError(f"{name!r} is not on the growth ladder — nothing to regoal.")
            cur = side["state"]
            if cur != REGOALED and _order_index(cur) < STATES.index(_REGOAL_FROM):
                raise ValueError(
                    f"cannot regoal from {cur}: nothing is stocked yet "
                    f"(regoal is reachable only from {_REGOAL_FROM} onward).")
            ruling = _require_author_ruling(evidence, bar="REGOALED", verb="REGOAL")
            now = _now()
            new_version = int(side.get("goal_version") or 1) + 1
            entry = {"from": cur, "to": REGOALED, "bar": BARS[REGOALED], "ts": now,
                     "by": ruling["by"], "goal_version": new_version,
                     "evidence": {"verb": "REGOAL", "ruling_ref": ruling["ref"]}}
            if evidence.get("note"):
                entry["note"] = str(evidence["note"])
            # the pairing debt: without the banked goal-v2 supersede record id, the
            # sidecar names the divergence instead of hiding it (docstring law).
            sup_id = str(evidence.get("supersede_record_id") or "").strip()
            if sup_id:
                entry["evidence"]["supersede_record_id"] = sup_id
                side.pop("pending_goal_supersede", None)
            else:
                side["pending_goal_supersede"] = True
            side["history"].append(entry)
            # the ladder resumes at SEEDED-of-the-new-goal-version.
            reseat = {"from": REGOALED, "to": _REGOAL_RESUME, "bar": BARS[_REGOAL_RESUME],
                      "ts": now, "by": ruling["by"], "goal_version": new_version,
                      "note": "regoal: the ladder resumes at SEEDED of the new goal version"}
            side["history"].append(reseat)
            side["state"] = _REGOAL_RESUME
            side["goal_version"] = new_version
            side["bar"] = BARS[_REGOAL_RESUME]
            side["updated"] = now
            _atomic_write(sidecar, side)
            return side


# ---------------------------------------------------------------------------
# the read — the ONE producer surfaces read (dashboard cards, /corpus/meta,
# project_state.project_verdict). Binds to the registry, never resolve_corpus.
# ---------------------------------------------------------------------------

def _pre_ladder(root: Path, name: str) -> bool:
    """Whether a sidecar-less project has PRE-LADDER history — a minted release or
    ``rounds > 0`` — so it renders as a plain ``pre_ladder`` null, never a fake
    SEEDED on a finished paper. Read from the registry inventory (the one door), never
    resolve_corpus."""
    from laplace.pipeline import registry
    try:
        row = next((r for r in registry.project_states(root) if r["name"] == name), None)
    except Exception:  # noqa: BLE001 — a roster hiccup degrades to "no pre-ladder history"
        return False
    if row is None:
        return False
    if int(row.get("rounds_n") or 0) > 0:
        return True
    if row.get("state") not in (None, "NEVER_RUN"):
        return True
    art = row.get("latest_artefact") or {}
    if art.get("kind") in ("release", "clean") and art.get("pdf"):
        return True
    return False


def growth_state(root: Path | str, name: str) -> dict:
    """THE one growth producer per project — the field dashboard cards, ``/corpus/meta``
    and :func:`project_state.project_verdict` all read (one truth per project).

    Returns ``{present, state, goal_version, bar, pre_ladder, reason, updated?}``:

      * a project ON the ladder (a sidecar exists): ``present=True`` with its rung,
        goal version, and bar;
      * a sidecar-less project WITH pre-ladder history (minted release / rounds>0):
        ``present=False, state=None, pre_ladder=True`` — a plain null, never a fake
        SEEDED on a finished paper;
      * a sidecar-less project with nothing yet: ``present=False, state=None,
        pre_ladder=False`` — not yet seeded.

    Never raises on a normal input — an unsafe name degrades to a plain absent row so a
    card / meta payload never 500s on this field.
    """
    try:
        root = Path(root).resolve()
        sidecar = _sidecar_path(root, name)
    except ValueError:
        return {"present": False, "state": None, "goal_version": None, "bar": None,
                "pre_ladder": False, "reason": "unsafe or unknown project name"}
    side = _read_sidecar(sidecar)
    if side is not None and side.get("state"):
        # the birth queues (the demand FORM walked at birth). A sidecar written before the
        # birth-queue conjunct landed carries none stored; surface the skeleton on the fly
        # so the read carries queues for every seeded project (never a fake empty queue).
        queues = side.get("queues") or _birth_queues()
        return {"present": True, "state": side.get("state"),
                "goal_version": side.get("goal_version", 1),
                "bar": side.get("bar") or BARS.get(side.get("state")),
                "queues": queues,
                "pre_ladder": False, "reason": "on the growth ladder",
                "updated": side.get("updated")}
    if _pre_ladder(root, name):
        return {"present": False, "state": None, "goal_version": None, "bar": None,
                "pre_ladder": True,
                "reason": "pre-ladder: a minted release / converged rounds predate the "
                          "growth ladder — not retro-laddered"}
    return {"present": False, "state": None, "goal_version": None, "bar": None,
            "pre_ladder": False, "reason": "not yet seeded (no growth sidecar)"}


def evidence_rules() -> dict[str, dict]:
    """The public, machine-readable statement of what each rung's bar consumes — the
    conjugate of ``superego.BANK_CONTRACT``, so a caller (a dispatch packet, a test,
    the future contract renderer) reads the rules from one place."""
    return {
        "SEEDED": {"bar": "mechanical",
                   "evidence": "birth — established by seed() at the New Project door"},
        "STOCKED": {"bar": "mechanical",
                    "evidence": "FAILS CLOSED this wave: element-leg axis floors land in G3/G4"},
        "WIRED": {"bar": "mechanical",
                  "evidence": "verify.check_connectivity clean (no orphan) AND corpus_ingest.gaps "
                              "named-or-exempt (evidence['named_gaps'] covers any survivor)"},
        "GRADED": {"bar": "judged",
                   "evidence": "evidence['verdict_id'] resolving to a STANDS verdict whose claim "
                               "carries growth:<name>:GRADED, judge != builder "
                               "(superego.verdicts_for)"},
        "READY": {"bar": "author",
                  "evidence": "BOTH a STANDS verdict for growth:<name> AND evidence['ruling'] = "
                              "{by: <author actor>, ref: <waiver>} — a defaulted actor is refused"},
        REGOALED: {"bar": "author",
                   "evidence": "evidence['ruling'] = {by: <author actor>, verb: REGOAL, ref: ...}; "
                               "reachable from STOCKED onward; bumps goal_version, resumes at SEEDED"},
    }
