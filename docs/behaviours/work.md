# work: 64 declared controls

## Concrete case

Project, definitions, Work and owner discovery

- App route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Supplied inputs/records: examples/verification/default-owner-suite.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups core`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all work controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### work:item

- Control: Task item
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs Inspect control of a navigator row and workspace-work.mjs flat catalogue row; instances carry data-control-owner
- Behaviour: Opens one task from the list, with its detail. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:next-step

- Control: Next step
- View: `work`
- Declared host/test route: workspace-work.mjs blocker card primary action
- Behaviour: Runs the one next step the owner offers for a blocked task. The owner's answer is shown beside it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:prerequisites

- Control: Prerequisites
- View: `work`
- Declared host/test route: workspace-work-relations.mjs Needs panel: every authored dependency with its owner standing
- Behaviour: Shows every prerequisite of this task with its own standing, as the owner records them. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:neighbourhood

- Control: Related tasks
- View: `work`
- Declared host/test route: workspace-work.mjs lazy section; one paged graph read, drawn and listed by workspace-topology
- Behaviour: Shows the tasks related to this one as a graph and a list, read one page at a time. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:disposition

- Control: Record disposition
- View: `work`
- Declared host/test route: workspace-work.mjs guarded disposition form
- Behaviour: Opens the form for recording what became of this task. Nothing is recorded until the form is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:review

- Control: Review lifecycle
- View: `work`
- Declared host/test route: workspace-work-review.mjs review facet and its allowed phase recorder
- Behaviour: Shows the review lifecycle of this task and the phase recorder the owner permits. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:review-setup

- Control: Set up reviews
- View: `work`
- Declared host/test route: workspace-work-review.mjs Work review setup entry; also offered from passage comment Reviewers and limits
- Behaviour: Opens the setup form for the reviews this task needs. Nothing is started until it is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:continuity-continue

- Control: Continue to the approved review
- View: `work`
- Declared host/test route: selected Task continuity next action; only the owner-issued HTTP Continue at READY with its exact basis and current Task cut
- Behaviour: Continues this task to the approved review through the request the owner issued. The owner's answer is shown beside it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:continuity-proof

- Control: Attach arrived proof
- View: `work`
- Declared host/test route: selected Task continuity next action; the owner-issued fillable proof template with its HTTP route and current Task cut
- Behaviour: Opens the form for attaching proof that the work arrived, using the owner's issued template. Nothing is sent until the form is.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:continuity-check

- Control: Check the original outcome
- View: `work`
- Declared host/test route: selected Task continuity; a retained uncertain original wire, checked by the pure issued summary GET (not a POST or retry)
- Behaviour: Asks the owner whether the original request, whose outcome is not known, was recorded. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:continuity-resend

- Control: Resend the original request unchanged
- View: `work`
- Declared host/test route: selected Task continuity; the exact retained original wire after the owner check reads NONE (visible label names the request kind; never automatic)
- Behaviour: Sends the original request again, unchanged, after the owner's check shows it was not recorded. It is never sent automatically.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:continuity-review

- Control: Open review form
- View: `work`
- Declared host/test route: selected Task continuity; opens the existing permitted review recorder for the owner-named phase
- Behaviour: Opens the review form for the phase the owner names. Nothing is recorded until it is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:continuity-retry

- Control: Read progress again
- View: `work`
- Declared host/test route: selected Task continuity; retries the failed progress summary GET
- Behaviour: Reads the task's progress again after the first read failed. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:step-waits-on

- Control: Read what this step waits on
- View: `work`
- Declared host/test route: workspace-work-review.mjs continuity Next; the task's own issued detail read, its blockers said beside it with the time
- Behaviour: Reads what this step waits on, from the task's own detail read, and shows it with when it was read. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:containment-save

- Control: Save containing work
- View: `work`
- Declared host/test route: workspace-work.mjs Change containing work; unchanged it says 'Nothing changed' beside Save and sends nothing; after a recorded save the redrawn card says when, and which task now contains this one, from the owner's detail read
- Behaviour: Saves which task contains this one. Unchanged, it says 'Nothing changed' and sends nothing; after a recorded save it says when and which task now contains this one.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:attempt

- Control: Last save attempt
- View: `work`
- Declared host/test route: workspace-work.mjs Edit authored work; the work port's last save attempt for this task (its status, attribution and the revision it was written against), not a control
- Behaviour: Shows the last attempt to save this task's authored work: its status, who made it and the revision it was written against. It is not a control.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:compare

- Control: Draft and current work
- View: `work`
- Declared host/test route: workspace-work.mjs Edit authored work after Compare with the current work; the port's comparison of the draft with the current owner read, with Use the displayed current work as my basis
- Behaviour: Shows the draft beside the current work after its basis changed, with a button to use the current work as the basis. It is not a control.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:result

- Control: Open the result
- View: `work`
- Declared host/test route: workspace-work.mjs Next of a completed task with one recorded comment route; checks the route, build and document with their owners, then opens the PDF
- Behaviour: Opens the finished result: checks the comment route, build and document with their owners, then opens the PDF.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:close

- Control: Close task
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Closes the open task and returns to the task list; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:edit-open

- Control: Edit title and completion condition
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Opens the authored-work editor for this task's title and completion condition; nothing is saved until you save.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:status-open

- Control: Update task status
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Opens the task-status form for this task; nothing is changed until you save there.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:use-for-message

- Control: Use for next message
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Puts this task in your next conversation message as its subject; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:related-turns

- Control: View related turns
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Opens the recorded conversation turns that name this task; it only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:authored-open

- Control: Edit authored work
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Shows the editor for the task's authored title and completion condition.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:containment-open

- Control: Change containing work
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Shows the form that moves this task under another task.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:disposition-open

- Control: Update task status
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Shows the form that records a new status for this task.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:evidence-paths

- Control: Advanced: exact evidence paths
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Shows the exact evidence paths the owner records for this task.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:save-authored

- Control: Save authored work
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Records the title and completion condition you edited, against the revision you started from; if it changed meanwhile it is refused.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:save-status

- Control: Save task status
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Records the task status you chose, with the reason, through the owner's own request.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:nav-filter

- Control: Task filter
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Narrows the task list to one group (needs attention, in progress, ready, awaiting review, waiting, closed) the owner counts.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:flat-catalogue

- Control: All task records and advanced namespace views
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Shows every recorded task of this project as one flat list, with the owner's advanced namespace views.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:namespaces

- Control: Existing work namespaces
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Lists the work namespaces that already exist, each with the read that opens it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:dev-workflows

- Control: Recorded development workflows
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Lists the development workflows already recorded, each with the read that opens it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:progress-open

- Control: Progress and next action
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Scrolls to this task's progress and next action, as the owner reports them.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:reinspect

- Control: Reinspect this work
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Reads this task again from its owner; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:completion-basis

- Control: Completion basis
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Shows what the owner counts as this task's completion basis.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:status-details

- Control: Status details
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Shows the exact recorded lifecycle and current acceptance of this task.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:open-parent

- Control: Part of the containing task
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Opens the task that contains this one.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:status-choice

- Control: Task status
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'
- Behaviour: Chooses the status to record for this task; Save task status records it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:relation-open

- Control: Open a related task
- View: `work`
- Declared host/test route: workspace-work-relations.mjs the relations panel of the open task; tests/workspace_control_coverage.test.mjs 'work/panels-open'
- Behaviour: Opens that related task beside this one.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:relation-tab

- Control: Relations tab
- View: `work`
- Declared host/test route: workspace-work-relations.mjs the relations panel of the open task; tests/workspace_control_coverage.test.mjs 'work/panels-open'
- Behaviour: Shows the tasks this task needs, the tasks that need it or the tasks it contains; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:subtasks

- Control: View subtasks
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Opens the subtasks of this task in place, read from the owner's page for it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:more-tasks

- Control: More tasks
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Reads the next page of tasks from the owner's own continuation and adds the rows not already shown; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:more-work

- Control: More work
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Reads the next page of the whole task list from the owner's own continuation; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:namespace-read

- Control: Read this exact work namespace
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Reads one recorded work namespace or workflow exactly as the owner holds it and shows it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:choose-evidence

- Control: Choose saved evidence
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Lists the saved evidence the owner offers for this task so some can be added to the status draft; nothing is saved until Save.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:action-inspect

- Control: Inspect an allowed action
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Reads what the owner would do for one allowed action of this task and shows it; nothing is done.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:action-template

- Control: Owner-issued action template
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Shows the request template the owner issued for one action; it is shown and never sent from here.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:history-read

- Control: Show recorded history
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Reads the recorded history of this task from the owner and shows it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:action-context

- Control: Actions and context
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Shows the operations the owner lists for this task and whether each is permitted here, with how many tasks it needs, affects and contains; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:location-open

- Control: Containing task
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Opens a task that contains this one, from its place in the owner's containment path; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:location-deeper

- Control: Open the deeper levels
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Opens the levels of containment between the shown root and this task in the task list; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:progress-basis

- Control: Exact progress basis and reads
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Shows the revisions and cuts the progress summary was built on, and the reads behind it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:progress-read

- Control: Read the progress records
- View: `work`
- Declared host/test route: workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'
- Behaviour: Reads the review records or the task details behind the progress summary, as the owner issued them; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:blocker-subject

- Control: Waiting-on Work
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Opens the other Work this one waits on, by the title its owner gives it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:blocker-action

- Control: Blocker next step
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Runs or reads the further step the owner offers for this blocker; the owner's answer is shown beside it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:blocker-read

- Control: Read recorded details
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Reads the exact record behind this blocker from its owner and shows it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:blocker-exact

- Control: Exact reason and required conditions
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Shows the owner's exact reason this task is blocked and what must be true to clear it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:completion-evidence

- Control: Exact completion evidence and changed inputs
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Shows the exact currentness record of this completed task, including which inputs changed since it was accepted; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:evidence-read

- Control: Read evidence
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Reads one piece of this task's completion evidence from its owner and shows it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:next-go

- Control: Go to this step
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Moves focus to the step this task waits on, lower on the page; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:review-open

- Control: Record a review phase
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Opens the form that records a review phase for this task, where you choose and save it; nothing is saved by opening it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:open-contained

- Control: Open its contained Work
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Opens the Work this task contains, in the navigator; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### work:needs-open

- Control: See what this task needs
- View: `work`
- Declared host/test route: workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states
- Behaviour: Moves focus to the list of what this task waits on, or what needs rechecking, lower on the page; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
