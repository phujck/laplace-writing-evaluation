# Project authoring lifecycle

A source-optional project (a general, company, campaign or other non-paper workspace; registry `kind: "project"`)
holds Work, material, references, research, artifacts and conversation history in its own state home. When its
author starts writing, the same project gains a selected manuscript and the canonical reader/argument plan owners.
One guarded transition does this through the owners that already exist. It creates no second project, no shadow
plan and no scaffold content. The owner is `src/laplace/projects/project_lifecycle.py`.

## States

`project_metadata` (native) and `GET /projects/metadata` (HTTP) carry `authoring_lifecycle`:

| State | Meaning | Next action |
|---|---|---|
| `NO_MANUSCRIPT` | registered, no selected manuscript | `structure_change start_authoring` creates and selects the manuscript, then declares the plan owner |
| `MANUSCRIPT_WITHOUT_PLAN` | a selected, editable manuscript, no plan owner (for example a manuscript added before this transition existed) | `structure_change start_authoring` declares the plan owner; the manuscript is not changed |
| `PLAN_PUBLICATION_PENDING` | the declaration is committed but its receipt was not confirmed | `structure_change start_authoring` completes that one receipt |
| `PLAN_OWNED` | the project owns its plan | read `structure`; a `MISSING` plan is created by `structure_change initialize` |
| `LAYOUT_OWNED` | a conceptric (paper/book) project, whose layout owns its plan | as above |
| `REFUSED` | read-only or foreign source, several editions present, a plan file present without a declaration, a planning declaration this owner did not make (never reused or overwritten), a project, manuscript, plan or selected-source path that resolves outside its home, a pending declaration whose one receipt cannot be proved exactly (see Recovery), or no data-backed registry row | none; `reason` names the cause and nothing is written |

`next_action` is the exact request, including its guard `expected_project_lifecycle` (the `project-lifecycle`
home: the registry row, the selected-source status and identity, and the plan facts). The same guard may be sent
as its canonical token instead, `expected: [identity_doors.identities(("project-lifecycle", project, revision))]`,
or both coherently. A stale, missing or wrong-home guard is refused before any effect, with the current token
served; a malformed `expected` is refused before any read. Repeating the transition on an owning project returns
`ALREADY_OWNED` and writes nothing. Success is reported only when the state after the transition is `PLAN_OWNED`;
`capabilities.start_planning` on `project_metadata` follows the same state.

## What the transition changes

* The manuscript, when there is none: `writing_projects._start_manuscript_unplanned` (the existing start: a
  `working-draft` under the project's manuscript home, selected; receipts `manuscript-draft-start` and `-ready`).
* One declaration on the project's own registry row: `manifest.planning = {owner: "project_structure",
  plan_path: "<manuscript_dir>/projection_plan.json", declared: PLAN-OWN-<32 hex>, selection_identity, by,
  publication, journal_offset, journal_anchor: {file, cut_sha256, cut_bytes}}`, receipted as `project-planning-declared`. `registry.planning_declaration_problem`
  is the one exact validator. `pipeline.registry` then gives the same `kind: "project"` record that `plan_path`
  (only a valid, `PUBLISHED` declaration of that exact path is honoured), and `corpus_ingest.resolve_corpus` reads the concept network from the
  project's manuscript home. The rewire ledger stays `corpus_friction/<project>.jsonl`.
* Nothing else: the slug, `project_dir`, layout, state home (`manuscript_source.project_state_dir`, so research,
  figures and reference associations stay where they were), the selected source and candidates, Work, material,
  references, artifacts, histories and drafts keep their bytes. The plan file itself is created afterwards by the
  plan owner (`structure_change initialize`), exactly as for every project.

## Doors

| Door | Request |
|---|---|
| Native tool | `structure_change {operation: "start_authoring", expected_project_lifecycle, kind?, title?}` (roles work, revise, discuss; refused for review) |
| HTTP | `POST /work/structure/change` with the same body plus `project` |
| Human, no manuscript | Add manuscript (`POST /projects/start`): the same owner, manuscript and plan ownership together |
| Human, manuscript without plan | Home, "Start reader plan": posts the lifecycle owner's own `next_action` |

After the transition, `structure`, `structure_change`, `logical_plan`, `concept_change` and the section and paragraph
authoring operations are available together; the capabilities `reader_plan` and `concepts` turn on and
`start_planning` turns off.

## Recovery

Starting a manuscript and declaring the plan owner are durable steps. The declaration is a publication boundary:
the row is committed `PENDING` with the journal's size as `journal_offset`, the `project-planning-declared`
receipt is appended, then the row is marked `PUBLISHED`. If the manuscript lands and the declaration does not, the
lifecycle reads `MANUSCRIPT_WITHOUT_PLAN`; if the declaration lands and its publication does not finish (the
append failed before or after its row landed, or the mark failed), it reads `PLAN_PUBLICATION_PENDING`. Either
way the same call with the new revision completes it, with the original attribution.

Publication needs proof of exactly one complete receipt (`_receipt_proof`). The proof reads only the journal rows
appended since `journal_offset`, within hard bounds (`PROOF_BYTES` 4 MiB, `PROOF_ROWS` 10,000, `PROOF_LINE`
1 MiB per row). The one row carrying the declaration's id must have the declaration's own `record`, `project`,
`plan_path`, `selection_identity` and `by`. The receipt is appended only when it is provably absent and the
journal ends on a whole row, then confirmed before the row is marked `PUBLISHED`. Anything else is UNPROVED and
the lifecycle reads `REFUSED` with the cause; the declaration stays `PENDING` and nothing is published, appended
onto or rewritten:

* an incomplete last row (a fresh declaration is also refused onto one), or a row that is not readable JSON;
* a row with the declaration's id and other content, or the id on two rows;
* an offset that is not the start of a row, or a journal shorter than the offset;
* a journal that is not the file the declaration was cut from, or whose bytes before the cut changed;
* more bytes, rows or row length than the bounds.

An unfinished last row is never waived by what its visible bytes say: an escaped or partial id can still decode
to the declaration's. Publication stays pending until that writer finishes the row, and is then judged on the
whole decoded row.

`journal_anchor` is the declaration's bounded file-and-cut identity: the journal file's `device:inode` and the
sha256 of at most 64 KiB (`registry.PLANNING_ANCHOR_BYTES`) immediately before the cut. It covers an atomic
replacement of any length or content (a copy of the original included, and a Git checkout that rewrites the
tracked journal) and an in-place rewrite of any byte in that window. It does not cover an in-place rewrite only
of older bytes that keeps the file and the window; it is not a whole-history tamper proof. When no journal existed
at the cut (`file` is empty), continuity cannot be established: only an exact receipt that already landed is
published; the receipt is re-appended only within the declaring call itself. The shared journal append
does not itself check the tail, so a later tool row can merge a torn fragment into one malformed line; the proof
then stays UNPROVED until the journal is inspected. There is exactly one receipt and one draft. Concurrent
transitions serialise on the registry lifecycle lock.

## Tests

`tests/test_project_authoring_lifecycle.py` (owner, native, HTTP, human, preservation, canonical and legacy
guards, declaration and home fences, refusals, publication recovery) and
`tests/project_lifecycle_home.test.mjs` (the Home control).
