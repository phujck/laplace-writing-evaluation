"""laplace.core.records.journal - the in-flight ledger: intent-then-execute at the banking seam.

Why (2026-08-23, the accounting day, SB-4): state used to move only at the close
boundary, so a killed session lost its delta and the next wake did archaeology --
this week's kill cost two turns of process-table forensics. The journal is the
cure's mechanism: every act declares its manifest BEFORE executing (intent), and
every step writes begin-then-done around its work (execute), each line durable
(flush + fsync) the moment it is written. `completed != intended` is then
decidable from rows alone, and recovery is one call, truncated at the last
durable write -- never argument.

The store: ``contract/journal.jsonl`` (append-only, one JSON line per event).
Event shapes::

    {"record": "act",     "act_id", "act", "manifest": [...], "ts", "pid", "argv"}
    {"record": "step",    "act_id", "index", "name", "phase": "begin"|"done",
                          "ts", "seconds"?, "ok"?, "status"?, "detail"?}
    {"record": "bank",    "act_id"?, "store", "row_id", "ts"}
    {"record": "act_end", "act_id", "status", "ts", "summary"?}

``bank_row`` is the SHARED APPEND PRIMITIVE the banking organs migrate to: it
journals the intent, appends the typed row to the target store (same durable
write), and journals the completion -- one seam, every consumer. The pair
clause rides it: the Superego seat's verdict packets bank through here before
the Ego acts on them, so one-writer is checkable from git alone. It also owns
the banked row's ``ts`` outright (the one stamp law, ``_one_stamp``): every row
that leaves this seam wears true UTC from the box's clock, and any ts the caller
brought demotes verbatim to ``ts_claimed``.

``bank_row`` also owns the row's LINKS (2026-08-24, the edge grammar): an
optional ``edges=[{"rel", "target"}]`` against the closed ``REL`` vocabulary,
banked as a first-class ``edges`` field and walked by :mod:`laplace.core.records.lineage`.
Unlike a frame -- advisory, never killing -- an edge is a CLAIM, so a malformed
one raises ``ValueError`` before anything is written.

The close's per-step meter (FIND-SE-005) is this journal: sewup wraps every
step in step_begin/step_done, so the close's wall-clock bill is typed rows,
not a printed report that dies with the terminal.

Dry runs write nothing: pass ``enabled=False`` (sewup --dry-run does), keeping
git porcelain empty per SB-7's check.

Roots: an explicit ``root`` always wins. Without one, the journal and act-cost
stores follow ``LAPLACE_STATE`` (the isolation door), and every other path -- a
``bank_row`` target store included -- is under the serving checkout,
:func:`laplace.core.checkout.repo_root` (``LAPLACE_REPO_ROOT``, else the source tree).
"""
from __future__ import annotations

import atexit
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from laplace.core import checkout


def _root(root: Path | str | None = None) -> Path:
    return Path(root) if root else checkout.repo_root()


def _store(root: Path | str | None = None) -> Path:
    # THE ISOLATION DOOR REACHES THE JOURNAL (must-fix, 2026-08-23, both seats bitten):
    # the suite's sewup-exercising tests journaled mock closes into the PRODUCTION store
    # - nine mock closes in one day, one minted inside each real close by its own suite
    # step - and each seat misread the journal once because of them. tests/conftest.py's
    # autouse LAPLACE_STATE isolation now wins here exactly as it does for the fallback
    # store; an EXPLICIT root argument still overrides (the journal's own tmp-root tests).
    iso = os.environ.get("LAPLACE_STATE")
    if iso and root is None:
        p = Path(iso)
        p.mkdir(parents=True, exist_ok=True)
        return p / "journal.jsonl"
    return _root(root) / "contract" / "journal.jsonl"


def _cost_store(root: Path | str | None = None) -> Path:
    """The typed act-cost store, isolated beside the journal under tests."""
    iso = os.environ.get("LAPLACE_STATE")
    if iso and root is None:
        p = Path(iso)
        p.mkdir(parents=True, exist_ok=True)
        return p / "act_costs.jsonl"
    return _root(root) / "contract" / "act_costs.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _one_stamp(row: dict[str, Any]) -> dict[str, Any]:
    """THE ONE STAMP LAW (WO-20260823-one-stamp-law, the judge's ruling 3).

    Three timestamp dialects shared one last-wins ordering: the journal's true
    UTC-Z, THREAD_PROBES' naive local, and hand-banked rows wearing an
    approximated local time under a false ``Z`` -- 30-120 minutes AHEAD of the
    box, which is what broke SB-4's +/-2s kill derivation. The cure is not a
    convention: ``bank_row`` stamps ``ts`` ITSELF, in true UTC, at write time,
    always. A hand-authored ``ts`` is then not wrong, just not authoritative --
    it demotes verbatim to ``ts_claimed``, where the census can lint it against
    the box (that lint is another lane's; this is only its ground truth).

    An empty ``ts`` (the work-order template's ``""``) is a placeholder, not a
    claim: it is overwritten and nothing is demoted. The caller's dict is never
    mutated -- the banked copy is the stamped one.
    """
    stamped = dict(row)
    claimed = stamped.get("ts")
    stamped["ts"] = _now()          # replaces in place when present: key order survives
    if claimed not in (None, ""):
        stamped["ts_claimed"] = claimed
    return stamped


#: THE CLOSED EDGE VOCABULARY (2026-08-24, the edge grammar). Rows have always
#: pointed at each other -- through ``target``, ``supersedes``, ``consumes``,
#: ``packet`` -- but each pointer invented its own field name, so the meaning of
#: the link lived in the READER, and no walker could cross two stores without
#: knowing every dialect first. ``edges`` is the typed half: one field, one
#: vocabulary, ten rels and no eleventh. The closure is the point -- an open
#: vocabulary is a free-text field wearing a schema's clothes, and it would rot
#: into the same per-store dialects within a month.
#:
#: Each rel, said once, source -> target:
#:   ``grounds``    the source rests on the target as evidence/basis
#:   ``amends``     the source changes the target without replacing it
#:   ``grades``     the source is a verdict ON the target
#:   ``supersedes`` the source replaces the target outright
#:   ``resolves``   the source closes the target (a WO, a fork, a question)
#:   ``raised-by``  the source exists BECAUSE of the target (inverse provenance)
#:   ``cures``      the source fixes the defect the target names
#:   ``relays``     the source hands the target on (seat to seat, act to act)
#:   ``consumes``   the source absorbs the target into itself
#:   ``part-of``    the source is a component of the target
REL: frozenset[str] = frozenset({
    "grounds", "amends", "grades", "supersedes", "resolves",
    "raised-by", "cures", "relays", "consumes", "part-of",
})

#: the only keys an edge may carry. An edge is a claim, not a note-holder.
_EDGE_KEYS = frozenset({"rel", "target"})


def validate_edges(edges: Any) -> list[dict[str, str]]:
    """Refuse a malformed edge LOUDLY (``ValueError``); return the clean list.

    Advisory-never-killing is the law for FRAMES -- a frame is a guess about
    meaning, and a wrong guess must not stop the work. An EDGE is not a guess:
    it is a claim that this row stands in a named relation to that one, and a
    wrong claim that banks silently is worse than no claim at all, because
    every later walk inherits it as fact. So this seam kills.

    Shape: ``[{"rel": <one of REL>, "target": "<row-id>"}]``, where target may
    be store-qualified as ``"store.jsonl#row-id"`` when the same id could live
    in two stores. No other keys, no empty strings, no whitespace in a target.
    """
    if edges is None:
        return []
    if not isinstance(edges, list):
        raise ValueError(f"edges must be a list of {{rel, target}} dicts, got {type(edges).__name__}")
    out: list[dict[str, str]] = []
    for i, e in enumerate(edges):
        where = f"edges[{i}]"
        if not isinstance(e, dict):
            raise ValueError(f"{where}: each edge must be a dict, got {type(e).__name__}")
        extra = set(e) - _EDGE_KEYS
        if extra:
            raise ValueError(f"{where}: unknown edge key(s) {sorted(extra)}; an edge carries "
                             f"only {sorted(_EDGE_KEYS)}")
        rel, target = e.get("rel"), e.get("target")
        if not isinstance(rel, str) or rel not in REL:
            raise ValueError(f"{where}: rel {rel!r} is not in the closed vocabulary "
                             f"{sorted(REL)}")
        if not isinstance(target, str) or not target.strip():
            raise ValueError(f"{where}: target must be a non-empty row id string, got {target!r}")
        if target != target.strip() or any(c.isspace() for c in target):
            raise ValueError(f"{where}: target {target!r} carries whitespace; a target is a row "
                             f"id, optionally store-qualified as 'store.jsonl#id'")
        if "#" in target:
            store, _, rid = target.partition("#")
            if "#" in rid or not rid or not store.endswith(".jsonl"):
                raise ValueError(f"{where}: store-qualified target {target!r} must read "
                                 f"'<store>.jsonl#<row-id>'")
        out.append({"rel": rel, "target": target})
    return out


def _append(path: Path, obj: dict[str, Any]) -> None:
    """One durable line: write + flush + fsync. The kill boundary is this call."""
    line = json.dumps(obj, ensure_ascii=False, default=str)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def _append_many(path: Path, rows: list[dict[str, Any]]) -> None:
    """One durable append for a completed act's buffered cost rows."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows)
    with open(path, "a", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())


def _authority_regions(regions: list[str] | tuple[str, ...] | None) -> list[str]:
    clean: list[str] = []
    for raw in regions or ():
        path = str(raw).strip()
        parts = path.split("/")
        if (
            not path
            or path.startswith(("/", "\\"))
            or "\\" in path
            or path.endswith("/")
            or any(part in {"", ".", ".."} for part in parts)
            or any(character in path for character in ("*", "?", "[", "]", "\x00"))
        ):
            raise ValueError(
                f"authority region must be one canonical repository-relative path prefix: {raw!r}"
            )
        if path in clean:
            raise ValueError(f"authority region repeated in one act: {path}")
        clean.append(path)
    return clean


def act_begin(act: str, manifest: list[str], *,
              regions: list[str] | tuple[str, ...] | None = None,
              root: Path | str | None = None,
              enabled: bool = True, **meta: Any) -> str:
    """Declare the act and its full step manifest BEFORE any step runs.

    The act row banks ``argv`` as invoked (2026-08-23, the graded kill drill): the
    recovery that read a killed act could name the ACT but not the INVOCATION, and
    the drill's void-pass confusion cost a read that this one field would have
    settled. ``pid`` says which process, ``argv`` says what it was told to do.
    """
    authority_regions = _authority_regions(regions)
    act_id = f"{act}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
    if enabled:
        row = {"record": "act", "act_id": act_id, "act": act,
               "manifest": list(manifest), "ts": _now(),
               "pid": os.getpid(), "argv": list(sys.argv), **meta}
        if authority_regions:
            row["authority_regions"] = authority_regions
        _append(_store(root), row)
    return act_id


def step_begin(act_id: str, index: int, name: str, *,
               root: Path | str | None = None, enabled: bool = True) -> None:
    if enabled:
        _append(_store(root), {"record": "step", "act_id": act_id, "index": index,
                               "name": name, "phase": "begin", "ts": _now()})


def step_done(act_id: str, index: int, name: str, *, seconds: float | None = None,
              ok: bool | None = None, detail: str | None = None,
              status: str | None = None,
              root: Path | str | None = None, enabled: bool = True) -> None:
    if enabled:
        row: dict[str, Any] = {"record": "step", "act_id": act_id, "index": index,
                               "name": name, "phase": "done", "ts": _now()}
        if seconds is not None:
            row["seconds"] = round(seconds, 3)
        if ok is not None:
            row["ok"] = ok
        if status is not None:
            row["status"] = status
        if detail:
            row["detail"] = str(detail)[:300]
        _append(_store(root), row)


def act_end(act_id: str, status: str, *, summary: str | None = None,
            cost_rows: list[dict[str, Any]] | None = None,
            root: Path | str | None = None, enabled: bool = True) -> None:
    if enabled:
        if cost_rows:
            stamped_costs = []
            for supplied in cost_rows:
                row = dict(supplied)
                row.setdefault("record", "act-cost")
                row.setdefault("act_id", act_id)
                stamped_costs.append(_one_stamp(row))
            _append_many(_cost_store(root), stamped_costs)
        row: dict[str, Any] = {"record": "act_end", "act_id": act_id,
                               "status": status, "ts": _now()}
        if summary:
            row["summary"] = str(summary)[:300]
        _append(_store(root), row)


#: the ambient act: standalone bank_row calls (no surrounding act) group under ONE
#: act per process, so a kill mid-multi-bank leaves rows an act can still claim.
#: Superego defect ruling 2026-08-23: act_id=None rows are archaeology wearing the
#: journal's badge -- every bank carries a real act identity from today.
_AMBIENT_ACT: dict[str, str] = {}


def _ambient_close(act_id: str, root: Path | str | None) -> None:
    """atexit: the ambient act's act_end on CLEAN interpreter exit.

    2026-08-23 (the graded kill drill's second cure): nothing ever wrote the
    ambient act's end, so every completed ambient bank listed as in-flight
    forever -- the drill's recovery showed 24 in flight, 23 of them this noise,
    and the one real death drowned in it. A KILLED process runs no atexit
    handler and so correctly leaves its act open: that asymmetry IS the design.
    Best-effort by construction (a tmp root may already be gone at exit); an
    exception here must never colour the process's exit status.
    """
    try:
        act_end(act_id, "ambient-complete", root=root,
                summary="clean interpreter exit (atexit)")
    except Exception:  # noqa: BLE001 - exit-time best effort, never raise at teardown
        pass


def _ambient_act(root: Path | str | None) -> str:
    key = str(_store(root))
    if key not in _AMBIENT_ACT:
        _AMBIENT_ACT[key] = act_begin(
            "ambient-bank", manifest=["bank"], root=root,
            note="standalone bank_row calls this process, grouped for recovery")
        atexit.register(_ambient_close, _AMBIENT_ACT[key], root)
    return _AMBIENT_ACT[key]


def bank_row(store: str | Path, row: dict[str, Any], *, act_id: str | None = None,
             edges: list[dict[str, str]] | None = None,
             root: Path | str | None = None) -> dict[str, Any]:
    """The shared banking path: journal the intent, append the row, journal done.

    ``store`` is repo-relative (e.g. ``corpus_friction/work_orders.jsonl``).
    The banked row itself is written with the same durable append as the
    journal lines. Banking organs migrate here from raw ``open(..., 'a')``.
    A caller with no surrounding act gets the process's ambient act stamped --
    never ``None`` (the recovery-grouping ruling, 2026-08-23).

    The banked row's ``ts`` is this seam's, not the caller's: see ``_one_stamp``.

    ``edges`` (2026-08-24) is the typed lineage half: a list of
    ``{"rel", "target"}`` claims against the closed ``REL`` vocabulary, banked
    as a first-class ``edges`` field on the row and walked by
    :mod:`laplace.core.records.lineage`. Optional -- every existing caller is unchanged --
    but never advisory: a malformed edge raises ``ValueError`` BEFORE anything
    is journalled or appended, so a wrong claim never reaches a store. A row
    that already carries its own ``edges`` field is validated on the same terms;
    passing both is a contradiction and refuses.
    """
    r = _root(root)
    target = r / store
    rid = str(row.get("id", "?"))
    if edges is not None and "edges" in row:
        raise ValueError("edges given twice: as the bank_row argument and on the row itself; "
                         "one home per claim")
    clean = validate_edges(row["edges"] if edges is None and "edges" in row else edges)
    if act_id is None:
        act_id = _ambient_act(root)
    _append(_store(root), {"record": "bank", "act_id": act_id,
                           "store": str(store), "row_id": rid, "phase": "begin",
                           "ts": _now()})
    stamped = _one_stamp(row)
    if clean:
        stamped["edges"] = clean
    _append(target, stamped)
    _append(_store(root), {"record": "bank", "act_id": act_id,
                           "store": str(store), "row_id": rid, "phase": "done",
                           "ts": _now()})
    return stamped  # exact owner postimage; existing fire-and-forget callers remain valid


def _pid_alive(pid: Any) -> bool | None:
    """Is that process still running? None when unknowable (no pid banked)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    try:
        os.kill(pid, 0)          # signal 0: existence check, delivers nothing
    except ProcessLookupError:
        return False
    except PermissionError:      # alive, just not ours to signal
        return True
    except OSError:
        return None
    return True


def recover(root: Path | str | None = None) -> dict[str, Any]:
    """What was in flight? Acts without act_end, steps reached vs manifest,
    truncated at the last durable write. One call, never archaeology.

    Two open-act classes, served SEPARATELY (2026-08-23, the graded kill drill):
    ``in_flight`` is the signal -- an act whose work is genuinely unfinished --
    and ``likely_complete`` is the residue an unended-but-finished act leaves
    (all banks done-phased, no step begun-without-done, nothing left in the
    manifest, and either a PRE-FIX-ERA act row -- no ``argv``, banked before the
    atexit closure existed -- or a pid that is no longer running). The drill's
    recovery drowned one real death in 23 such rows; the cure is not to hide
    them but to stop them sharing a bucket with the thing that matters.
    """
    path = _store(root)
    acts: dict[str, dict[str, Any]] = {}
    last_ts = None
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn final line IS the kill boundary; everything above it is durable
            last_ts = e.get("ts", last_ts)
            aid = e.get("act_id")
            if e.get("record") == "act":
                acts[aid] = {"act": e.get("act"), "manifest": e.get("manifest", []),
                             "authority_regions": e.get("authority_regions", []),
                             "began": e.get("ts"), "steps_begun": [], "steps_done": [],
                             "banks": [], "ended": None, "status": None,
                             "argv": e.get("argv"), "pid": e.get("pid"),
                             "banks_begun": 0, "banks_done": 0}
            elif aid in acts:
                a = acts[aid]
                if e.get("record") == "step":
                    (a["steps_done"] if e.get("phase") == "done"
                     else a["steps_begun"]).append(
                        {"index": e.get("index"), "name": e.get("name"),
                         "ts": e.get("ts"), "seconds": e.get("seconds"),
                         "ok": e.get("ok")})
                elif e.get("record") == "bank":
                    # counts, not names: a torn done-line leaves begun > done, which is
                    # exactly the "this bank never landed" the classifier must not smooth.
                    if e.get("phase") == "done":
                        a["banks_done"] += 1
                        a["banks"].append({"store": e.get("store"), "row_id": e.get("row_id")})
                    else:
                        a["banks_begun"] += 1
                elif e.get("record") == "act_end":
                    a["ended"] = e.get("ts")
                    a["status"] = e.get("status")
                elif e.get("record") == "adjudication":
                    # an adjudication row CLOSES its act for recovery (the relay's last
                    # amber, 2026-08-23): a graded death - the kill drill's, judged
                    # green - must not read as live work forever; the adjudication IS
                    # its ending, with the status the judge gave it.
                    a["ended"] = e.get("ts")
                    a["status"] = e.get("status", "adjudicated")
    in_flight: dict[str, Any] = {}
    likely_complete: dict[str, Any] = {}
    for aid, a in acts.items():
        if a["ended"]:
            continue
        done_idx = {s["index"] for s in a["steps_done"]}
        begun_only = [s for s in a["steps_begun"] if s["index"] not in done_idx]
        never_reached = [n for i, n in enumerate(a["manifest"])
                         if i not in done_idx
                         and i not in {s["index"] for s in begun_only}]
        alive = _pid_alive(a["pid"])
        # the split. "Work all closed" is the first half: no bank begun-without-done, no
        # step begun-without-done, and nothing outstanding in the manifest -- where an act
        # that wrote NO step rows at all (the ambient shape: its "bank" manifest entry is
        # never a step) counts as having nothing outstanding. The second half is evidence
        # the writer is gone: a pre-fix-era act row (no argv => banked before the atexit
        # closure existed, so its silence proves nothing) or a dead pid. pid reuse can lie
        # here; the cost of that lie is a real death demoted one bucket, never dropped.
        wrote_steps = bool(a["steps_begun"] or a["steps_done"])
        work_closed = (a["banks_begun"] <= a["banks_done"] and not begun_only
                       and (not never_reached or not wrote_steps))
        writer_gone = (a["argv"] is None) or (alive is False)
        entry = {
            "act": a["act"], "began": a["began"], "manifest": a["manifest"],
            "authority_regions": a["authority_regions"],
            "argv": a["argv"], "pid": a["pid"], "pid_alive": alive,
            "steps_done": a["steps_done"], "killed_mid_step": begun_only,
            "never_reached": never_reached,
            "banks": a["banks"],
        }
        if work_closed and writer_gone:
            entry["why"] = ("no act_end, but every bank landed and nothing is outstanding"
                            + (" (pre-fix-era act row: no argv)" if a["argv"] is None
                               else " (pid no longer running)"))
            likely_complete[aid] = entry
        else:
            in_flight[aid] = entry
    return {"store": str(path), "last_durable_write": last_ts,
            "acts_total": len(acts), "in_flight": in_flight,
            "likely_complete": likely_complete}


def _selftest() -> int:
    """The module proves its own two kill-drill cures, in a tmp root, offline.

    Added 2026-08-23 with the cures themselves: the drill's lesson was that a
    claim about recovery is worth exactly what a re-run of it shows, so the
    demonstration ships next to the mechanism instead of in a report.
    """
    import subprocess
    import tempfile

    fails: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r / "contract").mkdir(parents=True)
        (r / "demo").mkdir()

        # 1. argv on the act row.
        aid = act_begin("selftest-act", manifest=["one", "two"], root=r)
        rows = [json.loads(x) for x in _store(r).read_text().splitlines()]
        act_row = next(x for x in rows if x.get("record") == "act")
        print(f"[1] act row argv = {act_row.get('argv')!r}  pid = {act_row.get('pid')}")
        if not isinstance(act_row.get("argv"), list) or not act_row["argv"]:
            fails.append("act row carries no argv")

        # 2. a completed ambient bank reads CLOSED after a normal exit (child process).
        child = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'src');"
             "from laplace.core.records import journal;"
             f"journal.bank_row('demo/rows.jsonl', {{'id': 'r1'}}, root={str(r)!r})"],
            cwd=str(_root(None)), capture_output=True, text=True)
        if child.returncode != 0:
            fails.append(f"child bank failed: {child.stderr.strip()[:200]}")
        rec = recover(r)
        amb = [(k, v) for k, v in rec["in_flight"].items() if v["act"] == "ambient-bank"]
        ends = [json.loads(x) for x in _store(r).read_text().splitlines()
                if json.loads(x).get("record") == "act_end"]
        print(f"[2] child banked and exited: act_end rows = "
              f"{[(e['act_id'].split('-')[0] + '-' + e['act_id'].split('-')[1], e['status']) for e in ends]}"
              f" | ambient acts still in_flight = {len(amb)}")
        if not any(e["status"] == "ambient-complete" for e in ends):
            fails.append("clean exit wrote no ambient-complete act_end")
        if amb:
            fails.append("a cleanly-exited ambient act still reads in-flight")

        # 3. the split: a pre-fix-era finished act vs a genuinely killed one.
        _append(_store(r), {"record": "act", "act_id": "old-1", "act": "pre-fix-bank",
                            "manifest": ["bank"], "ts": _now(), "pid": os.getpid()})
        for phase in ("begin", "done"):
            _append(_store(r), {"record": "bank", "act_id": "old-1", "store": "demo/rows.jsonl",
                                "row_id": "r0", "phase": phase, "ts": _now()})
        step_begin(aid, 0, "one", root=r)          # begun, never done: the real death
        rec = recover(r)
        print(f"[3] in_flight = {sorted(rec['in_flight'])} | "
              f"likely_complete = {sorted(rec['likely_complete'])}")
        for k, v in rec["likely_complete"].items():
            print(f"    likely-complete {k}: {v['why']}")
        if "old-1" not in rec["likely_complete"]:
            fails.append("pre-fix-era finished act did not classify likely-complete")
        if aid not in rec["in_flight"]:
            fails.append("act killed mid-step did not stay in_flight")
        if "old-1" in rec["in_flight"]:
            fails.append("likely-complete noise leaked back into in_flight")

        # 4. the branch that outlives the pre-fix era: a POST-fix act row (argv present)
        # whose writer is gone. Its pid is a real, reaped child -- dead for certain.
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()                                # reaped: that pid is gone for certain
        _append(_store(r), {"record": "act", "act_id": "gone-1", "act": "killed-9-bank",
                            "manifest": ["bank"], "ts": _now(), "pid": dead.pid,
                            "argv": [sys.executable, "-c", "pass"]})
        for phase in ("begin", "done"):
            _append(_store(r), {"record": "bank", "act_id": "gone-1", "store": "demo/rows.jsonl",
                                "row_id": "r2", "phase": phase, "ts": _now()})
        rec = recover(r)
        g = rec["likely_complete"].get("gone-1")
        print(f"[4] dead-pid act (pid {dead.pid}, argv banked) -> "
              f"{'likely_complete' if g else 'in_flight'}"
              f"{': ' + g['why'] if g else ''}")
        if not g:
            fails.append("post-fix act with a dead pid did not classify likely-complete")

        # 5. the one stamp law: a hand ts demotes, a missing one is minted, and the
        # journal's own ambient act rows keep the form they already had.
        hand = "2026-08-23T21:30:00Z"                  # the false-Z dialect: local wearing Z
        bank_row("demo/rows.jsonl", {"id": "h1", "ts": hand, "text": "hand"}, root=r)
        bank_row("demo/rows.jsonl", {"id": "n1", "text": "no ts"}, root=r)
        banked = [json.loads(x) for x in (r / "demo" / "rows.jsonl").read_text().splitlines()]
        h1 = next(x for x in banked if x["id"] == "h1")
        n1 = next(x for x in banked if x["id"] == "n1")
        print(f"[5] hand row -> ts={h1['ts']!r} ts_claimed={h1.get('ts_claimed')!r} | "
              f"no-ts row -> ts={n1['ts']!r} claimed={'ts_claimed' in n1}")
        if h1.get("ts_claimed") != hand:
            fails.append("hand ts did not demote verbatim to ts_claimed")
        if h1["ts"] == hand or not h1["ts"].endswith("Z"):
            fails.append("hand ts was not overwritten by a machine UTC stamp")
        if not n1["ts"].endswith("Z") or "ts_claimed" in n1:
            fails.append("a row with no ts was mis-stamped")
        amb_rows = [json.loads(x) for x in _store(r).read_text().splitlines()
                    if json.loads(x).get("record") in ("act", "step", "bank", "act_end")]
        print(f"[5] journal rows unchanged in form: "
              f"{len(amb_rows)} rows, ts_claimed present on "
              f"{sum('ts_claimed' in x for x in amb_rows)}")
        if any("ts_claimed" in x for x in amb_rows):
            fails.append("the journal's own rows grew a ts_claimed field")
        if not all(str(x.get("ts", "")).endswith("Z") for x in amb_rows):
            fails.append("a journal row lost its true-UTC ts")

        # 6. the edge grammar: a good claim banks as a field, a bad rel kills before the write.
        bank_row("demo/rows.jsonl", {"id": "e1", "text": "with edges"},
                 edges=[{"rel": "grades", "target": "rows.jsonl#r1"}], root=r)
        e1 = next(json.loads(x) for x in (r / "demo" / "rows.jsonl").read_text().splitlines()
                  if json.loads(x)["id"] == "e1")
        try:
            bank_row("demo/rows.jsonl", {"id": "e2"},
                     edges=[{"rel": "relates-to", "target": "r1"}], root=r)
            refused = ""
        except ValueError as exc:
            refused = str(exc)
        after = [json.loads(x)["id"] for x in (r / "demo" / "rows.jsonl").read_text().splitlines()]
        print(f"[6] edges banked = {e1.get('edges')} | bad rel refused = {refused[:60]!r} | "
              f"'e2' in store = {'e2' in after}")
        if e1.get("edges") != [{"rel": "grades", "target": "rows.jsonl#r1"}]:
            fails.append("a valid edge did not bank as a first-class field")
        if not refused or "e2" in after:
            fails.append("a rel outside the closed vocabulary reached the store")

    print("SELFTEST: " + ("PASS" if not fails else "FAIL " + "; ".join(fails)))
    return 0 if not fails else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--recover" in argv:
        print(json.dumps(recover(), ensure_ascii=False, indent=1))
        return 0
    if "--selftest" in argv:
        return _selftest()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
