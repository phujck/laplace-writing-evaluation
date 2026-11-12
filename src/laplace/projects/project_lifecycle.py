"""THE PROJECT AUTHORING LIFECYCLE (M5, 2026-10-15): one guarded transition from a source-optional project to
manuscript + canonical reader/argument planning, through the owners that already exist.

Purpose. A general (source-optional, registry kind "project") workspace keeps its Work, material, references,
research and history in its own state home. When its author starts writing, the project needs a selected
manuscript (writing_projects.start_manuscript, unchanged) and the canonical plan owners: the reader plan
(project_structure, the projection plan file) and the argument/concept network (concepts_surface over
corpus_ingest, keyed by the project name). This module composes those owners; it creates no second project,
no shadow plan and no scaffold content.

The owner layout (one declaration). The project's own registry row gains manifest.planning = {"owner":
"project_structure", "plan_path": "<manuscript_dir>/projection_plan.json", "declared": PLAN-OWN-<hex32>,
"selection_identity", "by", "publication": PENDING|PUBLISHED, "journal_offset", "journal_anchor"}; registry.planning_declaration_
problem is its one exact validator. The registry then gives the SAME kind-"project" record its plan_path (only a
valid, PUBLISHED declaration of that exact path), corpus_ingest resolves its manuscript as the concept-network tex
root, and nothing else changes: the slug, project_dir, state home (manuscript_source.project_state_dir still
serves research, figures and references from it), selected source and candidates, Work, material, references,
artifacts, histories and drafts keep their bytes. The plan FILE is not written here: project_structure.state then
reports the plan MISSING and the existing guarded structure_change initialize creates it, as for every project.

States (observe):  NO_MANUSCRIPT -> start_authoring creates and selects the manuscript, then declares planning;
                   MANUSCRIPT_WITHOUT_PLAN -> start_authoring declares planning only (the already-selected
                   manuscript is adopted; its content, bibliography, artifacts and contracts are untouched);
                   PLAN_PUBLICATION_PENDING -> start_authoring completes the declaration's one receipt;
                   PLAN_OWNED / LAYOUT_OWNED -> nothing to do (idempotent ALREADY_OWNED, no write);
                   REFUSED -> read-only, foreign, ambiguous selection, a plan file that exists undeclared, a
                   declaration this owner cannot honour (never reused or overwritten), a home whose resolved
                   path leaves the project or checkout, a pending receipt that cannot be proved exactly, or
                   no data-backed registry row; nothing is written.
Guard. Every write carries the "project-lifecycle" identity, as expected_project_lifecycle or as its canonical
expected token: the revision observe() returns (the registry row, the selection and source status, and the plan
facts). A stale, missing or wrong-home guard is refused before any effect. Transitions serialise on the registry
lifecycle lock. Success is reported only when the state after the transition is PLAN_OWNED.
Recovery. Creating a manuscript and declaring planning are durable steps (manuscript-draft-start/-ready from the
manuscript owner). The declaration is a publication boundary: the row is committed PENDING with the journal size
as its offset, the project-planning-declared receipt is appended, then the row is marked PUBLISHED. If the
manuscript lands and the declaration does not, observe() reports MANUSCRIPT_WITHOUT_PLAN; if the declaration
lands and its publication does not finish, PLAN_PUBLICATION_PENDING. Either way the same call with the new
revision completes it, with the original attribution: _receipt_proof reads only the rows appended since the
offset, within hard byte/row/line bounds, and publication needs exactly one complete receipt with the
declaration's own project, id, plan path, selection and actor (appended once only when provably absent and the
journal ends on a whole row, then confirmed). The journal must also still be the file and cut the declaration
recorded (journal_anchor: device:inode and the sha256 of at most 64 KiB before the cut, _cut_anchor). A torn,
unfinished or unreadable row (never waived by its visible bytes), a same-id row with other content, a duplicate,
a moved offset, a shorter, replaced or rewritten journal or an exceeded bound is UNPROVED: REFUSED, the
declaration stays PENDING, and nothing is published, appended onto, rewritten or renewed. One receipt, one draft.
Doors. Native and HTTP: structure_change {operation: "start_authoring", expected_project_lifecycle, kind?,
title?}; read: project_metadata (authoring_lifecycle). Human: Add manuscript (POST /projects/start) runs this same
owner, and the project Home offers "Start reader plan" for MANUSCRIPT_WITHOUT_PLAN.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from filelock import FileLock

SCHEMA = "laplace.project-authoring-lifecycle/1"
PLAN_FILE = "projection_plan.json"


class LifecycleRefused(ValueError):
    """A transition that cannot run from the observed state; carries the current lifecycle for the cure."""

    def __init__(self, message, lifecycle):
        super().__init__(message)
        self.lifecycle = lifecycle


def _digest(value) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _data_row(project, root):
    from laplace.pipeline import registry
    return next((row for row in registry._data_projects(root) if row.get("name") == project), None)


def planned_path(record) -> str:
    """The one plan location of a project-layout record: its manuscript home's projection plan."""
    return f"{record.manuscript_dir}/{PLAN_FILE}"


def _home_problem(record, source, plan_rel, root) -> str | None:
    """The resolved-home fence: the project home inside the active checkout, the manuscript home inside it, and
    the plan file and selected source inside the manuscript home (a nested selected draft is inside). Lexical
    paths and source flags alone are not enough: a symlinked home that escapes is refused here, before anything."""
    try:
        home = (root / record.project_dir).resolve()
        manuscript = (root / record.manuscript_dir).resolve()
        if not home.is_relative_to(root) or not manuscript.is_relative_to(home):
            return "The project's manuscript home resolves outside its own project home in the active checkout."
        if plan_rel and not (root / plan_rel).resolve().is_relative_to(manuscript):
            return "The planned reader-plan path resolves outside the project's manuscript home."
        if source.get("root") and not (root / source["root"]).resolve().is_relative_to(manuscript):
            return "The selected manuscript resolves outside the project's manuscript home."
    except (OSError, RuntimeError):
        return "The project's homes cannot be resolved in the active checkout."
    return None


def _journal(root) -> Path:
    return root / "contract" / "talk.jsonl"


# Hard bounds of the receipt proof: bytes appended since the declaration's offset, rows in that range, and one
# row's length. Past any bound the receipt is UNPROVED: the declaration stays PENDING and nothing is appended.
PROOF_BYTES, PROOF_ROWS, PROOF_LINE = 4 << 20, 10_000, 1 << 20
RECEIPT_FIELDS = ("record", "id", "project", "plan_path", "selection_identity", "by")


def _journal_size(root) -> int:
    path = _journal(root)
    return path.stat().st_size if path.is_file() else 0


def _cut_anchor(root, offset) -> tuple[dict, bool]:
    """The bounded file-and-cut identity of the journal at ``offset`` and whether the cut is a row start. The anchor
    is the file's device:inode and the sha256 of at most registry.PLANNING_ANCHOR_BYTES immediately before the cut
    ("" file and an empty cut when no journal exists). Coverage: an atomic replacement of the file (any length or
    content, a copy of the original included, and a Git checkout that rewrites it) changes the file identity; an
    in-place rewrite of any byte in that window changes the cut. An in-place rewrite only of older bytes, keeping
    the file and the window, is not covered; this is not a whole-history tamper proof."""
    from laplace.pipeline import registry
    path = _journal(root)
    if not path.is_file():
        return {"file": "", "cut_sha256": "sha256:" + hashlib.sha256(b"").hexdigest(), "cut_bytes": 0}, offset == 0
    status, size = path.stat(), min(offset, registry.PLANNING_ANCHOR_BYTES)
    with path.open("rb") as stream:
        stream.seek(offset - size)
        window = stream.read(size)
    anchor = {"file": "%d:%d" % (status.st_dev, status.st_ino), "cut_sha256": "sha256:" + hashlib.sha256(window).hexdigest(),
              "cut_bytes": len(window)}
    return anchor, len(window) == size and (offset == 0 or window.endswith(b"\n"))


def _receipt_proof(project, root, planning, *, fresh=False) -> tuple[str, str | None]:
    """("EXACT" | "ABSENT", None) or ("UNPROVED", why), from only the journal bytes appended since the declaration's
    offset, read within PROOF_BYTES/PROOF_ROWS/PROOF_LINE. EXACT: exactly one row carries the declaration's id and
    it is the declaration's own receipt (project, plan path, selection and actor attribution). ABSENT: no row
    carries it and the journal ends on a complete row, so one append lands on its own line. Anything else (a
    same-id row with other content, two same-id rows, an unreadable row, an incomplete last row, an offset that is
    not a row start, a shorter journal, a bound exceeded) is UNPROVED: never published, appended onto or
    rewritten. An incomplete last row is never waived, whatever its visible bytes: it stays UNPROVED until its
    writer finishes. Continuity comes first: the journal must still be the file the declaration was cut from with
    the same bytes before the cut (_cut_anchor), else UNPROVED and nothing is renewed from current bytes. When no
    journal existed at the cut, continuity cannot be established, so only an EXACT receipt is accepted, except in
    the declaring call itself (``fresh``)."""
    path, offset, declared = _journal(root), planning["journal_offset"], planning["declared"]
    size = _journal_size(root)
    if size < offset:
        return "UNPROVED", "the journal is shorter than when the declaration was made (it was replaced)"
    if size - offset > PROOF_BYTES:
        return "UNPROVED", "more than %d bytes were appended to the journal since the declaration" % PROOF_BYTES
    anchor, _ = _cut_anchor(root, offset)
    original = planning["journal_anchor"]
    if original["file"] and anchor["file"] != original["file"]:
        return "UNPROVED", "the journal is not the file the declaration was cut from (it was replaced or moved)"
    if original["file"] and anchor["cut_sha256"] != original["cut_sha256"]:
        return "UNPROVED", "the journal bytes before the declaration's cut changed"
    proof = _scan(project, root, planning, offset, size)
    if proof == ("ABSENT", None) and not original["file"] and not fresh:
        return "UNPROVED", ("no journal existed when the declaration was cut, so the journal's continuity cannot be "
                            "established and the receipt is not re-appended automatically")
    return proof


def _scan(project, root, planning, offset, size) -> tuple[str, str | None]:
    """The bounded row scan of _receipt_proof over [offset, size)."""
    path, declared = _journal(root), planning["declared"]
    if size == offset == 0:
        return "ABSENT", None
    expected, found, rows, left = _receipt_row(project, planning), 0, 0, size - offset
    with path.open("rb") as stream:
        stream.seek(offset - 1 if offset else 0)
        if offset and stream.read(1) != b"\n":
            return "UNPROVED", "the declaration's journal offset is not the start of a row"
        while left > 0:
            raw = stream.readline(min(PROOF_LINE + 1, left))
            if not raw:
                break
            left -= len(raw)
            rows += 1
            if rows > PROOF_ROWS:
                return "UNPROVED", "more than %d journal rows were appended since the declaration" % PROOF_ROWS
            if len(raw) > PROOF_LINE:
                return "UNPROVED", "a journal row since the declaration is longer than %d bytes" % PROOF_LINE
            if not raw.endswith(b"\n"):
                return "UNPROVED", "the journal ends with an incomplete row (a writer may still be finishing it), and nothing is appended onto it"
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except (ValueError, RecursionError):
                row = None
            if not isinstance(row, dict):
                return "UNPROVED", "a journal row since the declaration is not readable JSON"
            if row.get("id") == declared:
                if {key: row.get(key) for key in RECEIPT_FIELDS} != expected:
                    return "UNPROVED", ("a journal row carries the declaration's identity with other content "
                                        "(record, project, plan path, selection or actor)")
                found += 1
    if found > 1:
        return "UNPROVED", "the declaration's identity appears on %d journal rows" % found
    return ("EXACT" if found else "ABSENT"), None


def _unproved(why) -> str:
    return ("The planning declaration is committed but its one receipt cannot be proved: " + why + ". It stays "
            "PENDING and is not published, appended onto or rewritten; read again, and if this persists inspect the journal.")


def observe(project: str, root) -> dict:
    """The project's authoring lifecycle state, its guard revision and the one legitimate next action."""
    from laplace.pipeline import registry
    from laplace.manuscript import manuscript_source
    root = Path(root).resolve()
    record = registry.resolve(project, repo_root=root)
    if record is None:
        raise ValueError("Unknown project")
    row = _data_row(project, root)
    source = manuscript_source.resolve(project, repo_root=root)
    status = source.get("status") or "unknown"
    manuscript = {"status": status, "root": source.get("root"), "read_only": bool(source.get("read_only")),
                  "foreign": bool(source.get("foreign")),
                  "selection_identity": manuscript_source.selection_identity(source, project) if status == "resolved" else None}
    plan_rel = record.plan_path or (planned_path(record) if record.kind == "project" and record.manuscript_dir else None)
    plan_file = (root / plan_rel) if plan_rel else None
    manifest = (row or {}).get("manifest")
    declared = manifest.get("planning") if isinstance(manifest, dict) else None
    plan = {"owned": bool(record.plan_path), "plan_path": plan_rel, "file_exists": bool(plan_file and plan_file.is_file()),
            "declared": declared}
    reason = None
    if record.kind != "project":
        state = "LAYOUT_OWNED" if record.plan_path else "REFUSED"
        reason = None if record.plan_path else "This project layout has no reader-plan owner."
    elif row is None or not record.manuscript_dir:
        state, reason = "REFUSED", "Only a data-backed source-optional project with a manuscript home can start authoring."
    elif (problem := _home_problem(record, source, plan_rel, root)):
        state, reason = "REFUSED", problem
    elif declared is not None and (problem := registry.planning_declaration_problem(declared, record.manuscript_dir)):
        state, reason = "REFUSED", ("This project carries a planning declaration this owner did not make or cannot honour ("
                                    + problem + "); it is neither reused nor overwritten.")
    elif declared is not None and declared["publication"] == "PENDING":
        proof, why = _receipt_proof(project, root, declared)
        state, reason = ("REFUSED", _unproved(why)) if proof == "UNPROVED" else ("PLAN_PUBLICATION_PENDING", None)
    elif declared is not None and record.plan_path == declared["plan_path"]:
        state = "PLAN_OWNED"
    elif manuscript["read_only"] or manuscript["foreign"]:
        state, reason = "REFUSED", "The selected manuscript is read-only or foreign; its plan cannot be owned here."
    elif status == "ambiguous":
        state, reason = "REFUSED", "Several manuscript editions are present; choose one before starting the plan."
    elif plan["file_exists"]:
        state, reason = "REFUSED", ("A projection plan file already exists at the planned path without a declaration; "
                                    "inspect it before any plan ownership is declared.")
    elif status == "resolved":
        state = "MANUSCRIPT_WITHOUT_PLAN"
    else:
        state = "NO_MANUSCRIPT"
    revision = _digest({"row": row, "source": {key: source.get(key) for key in ("status", "root", "manuscript_dir", "edition", "read_only", "foreign")},
                        "selection": manuscript["selection_identity"], "plan": {key: plan[key] for key in ("owned", "plan_path", "file_exists")}})
    does = {"NO_MANUSCRIPT": "create and select the manuscript, then own its reader/argument plan",
            "MANUSCRIPT_WITHOUT_PLAN": "own the reader/argument plan of the selected manuscript; its content is not changed",
            "PLAN_PUBLICATION_PENDING": "complete the declaration's one receipt; nothing else is changed"}
    next_action = None
    if state in does:
        next_action = {"operation": "structure_change", "payload": {"operation": "start_authoring", "expected_project_lifecycle": revision},
                       "does": does[state]}
    elif state in {"PLAN_OWNED", "LAYOUT_OWNED"}:
        next_action = {"operation": "structure", "payload": {"view": "summary"},
                       "does": "read the reader plan; a MISSING plan is created by structure_change initialize"}
    return {"schema_version": SCHEMA, "project": project, "layout": record.kind, "state": state, "revision": revision,
            "manuscript": manuscript, "plan": plan, "reason": reason, "next_action": next_action}


def _set_planning(project, root, change):
    """One registry write of this project's planning declaration; ``change(current)`` returns the new value."""
    from laplace.projects import library as writing_projects

    def mutate(rows):
        row = next((row for row in rows if row.get("name") == project), None)
        if row is None or row.get("kind") != "project":
            raise ValueError("The project's registry row changed; read the lifecycle again.")
        manifest = row.setdefault("manifest", {})
        manifest["planning"] = change(manifest.get("planning"))
        return dict(manifest["planning"])
    return writing_projects._registry_write(root, mutate)


def _receipt_row(project, planning):
    """The declaration's one receipt, from the declaration's own original attribution."""
    return {"record": "project-planning-declared", "id": planning["declared"], "project": project,
            "plan_path": planning["plan_path"], "selection_identity": planning["selection_identity"], "by": planning["by"]}


def _publish(project, root, planning, *, fresh=False):
    """Complete the publication boundary exactly once: append the receipt only when the proof finds it ABSENT
    (a failed append can still have landed), confirm the one exact receipt, and only then mark PUBLISHED."""
    from laplace.writing import records as writing_records
    proof, why = _receipt_proof(project, root, planning, fresh=fresh)
    if proof == "ABSENT":
        writing_records.bank(root, _receipt_row(project, planning))
        proof, why = _receipt_proof(project, root, planning)
        why = why or "the appended receipt is not in the journal"
    if proof != "EXACT":
        raise LifecycleRefused(_unproved(why), observe(project, root))
    expected = planning["declared"]

    def published(current):
        if not isinstance(current, dict) or current.get("declared") != expected:
            raise ValueError("The planning declaration changed during publication; read the lifecycle again.")
        return {**current, "publication": "PUBLISHED"}
    return _set_planning(project, root, published)


def start_authoring(project: str, payload: dict, root, *, actor=None) -> dict:
    """The guarded transition (see the module text). Returns the outcome and the lifecycle after it."""
    from laplace.projects import library as writing_projects
    from laplace.core import identity_doors
    from laplace.pipeline import registry
    root = Path(root).resolve()
    allowed = {"operation", "expected_project_lifecycle", "expected", "kind", "title", "project"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError("start_authoring accepts expected_project_lifecycle and optional kind and title")
    with FileLock(str(root / registry.DATA_PROJECTS_FILE) + ".lifecycle.lock", timeout=30):
        before = observe(project, root)
        if before["state"] in {"PLAN_OWNED", "LAYOUT_OWNED"}:
            return {"status": "ALREADY_OWNED", "unchanged": True, "project": project, "lifecycle": before}
        if before["state"] == "REFUSED":
            raise LifecycleRefused(before["reason"], before)
        # the one identity comparison (legacy name or canonical token): a missing or stale guard is refused
        identity_doors.gate("structure_change start_authoring", supplied=payload,
                            homes=[("project-lifecycle", project, before["revision"])],
                            required=["expected_project_lifecycle"],
                            said="The project lifecycle changed or was not read; read project_metadata (authoring_lifecycle) and retry.")
        created = None
        if before["state"] == "PLAN_PUBLICATION_PENDING":
            # the declaration landed and its receipt did not (or did, and was not confirmed): finish that one receipt
            planning = _publish(project, root, before["plan"]["declared"])
            status = "PUBLISHED"
        else:
            if before["state"] == "NO_MANUSCRIPT":
                kind = payload.get("kind", "paper")
                title = payload.get("title") or (writing_projects.metadata(project, root).get("title") or project)
                code, created = writing_projects._start_manuscript_unplanned({"project": project, "kind": kind, "title": title}, root)
                if code != 201:
                    raise LifecycleRefused(created.get("error") or "The manuscript could not be started.", observe(project, root))
            middle = observe(project, root)
            if middle["state"] != "MANUSCRIPT_WITHOUT_PLAN":
                raise LifecycleRefused(middle["reason"] or "The manuscript is not ready for planning.", middle)
            offset = _journal_size(root)
            anchor, row_start = _cut_anchor(root, offset)
            if not row_start:
                raise LifecycleRefused("The journal ends with an incomplete row; no declaration is made onto it. Read again, "
                                       "and if this persists inspect the journal.", middle)
            record = registry.resolve(project, repo_root=root)
            declaration = {"owner": "project_structure", "plan_path": planned_path(record), "declared": "PLAN-OWN-" + uuid.uuid4().hex,
                           "selection_identity": middle["manuscript"]["selection_identity"],
                           "by": "agent" if isinstance(actor, dict) and actor.get("kind") == "agent" else "author",
                           "publication": "PENDING", "journal_offset": offset, "journal_anchor": anchor}

            def declare(current):
                if current is not None:
                    raise ValueError("A planning declaration appeared concurrently; read the lifecycle again.")
                return declaration
            _set_planning(project, root, declare)
            planning = _publish(project, root, declaration, fresh=True)
            status = "STARTED" if created else "PLAN_OWNED"
        after = observe(project, root)
    if after["state"] != "PLAN_OWNED" or after["plan"]["plan_path"] != planning["plan_path"]:
        raise LifecycleRefused("The declaration did not result in plan ownership; nothing is reported as owned.", after)
    return {"status": status, "unchanged": False, "project": project, "receipt_id": planning["declared"],
            "manuscript_started": created, "planning": planning, "lifecycle": after,
            "next": {"operation": "structure", "payload": {"view": "summary"},
                     "says": "The plan is MISSING until structure_change initialize creates it with the returned revisions."}}
