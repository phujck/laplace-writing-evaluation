# workflow: 117 declared controls

## Concrete case

Actual saved public WDEF and real independent Work delivery; saved definition is not claimed executed

- App route: `/project?workspace=writing&app=workflows`.
- Supplied inputs/records: WDEF-6d272e5718bb4e1f87523767a13c95f4.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: Existing configured provider and explicit parent/role bindings to execute saved steps. The saved WDEF is inspectable without inference.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all workflow controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### workflow:purpose

- Control: Workflow purpose
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs
- Behaviour: Shows or hides the workflow's full purpose text. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:saved-read

- Control: Read this saved version
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs
- Behaviour: Reads the exact body of this saved version of the workflow and shows it. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:saved-close

- Control: Close saved version
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs
- Behaviour: Closes the saved version being read and returns to the design. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:history

- Control: Browse saved versions
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs, exact issued offers; tests/workflow_history_frontend.test.mjs
- Behaviour: Lists the saved versions of this workflow, newest first, from the owner's history. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:history-next

- Control: Older saved versions
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs, exact issued offers; tests/workflow_history_frontend.test.mjs
- Behaviour: Reads the next, older page of saved versions from the owner's own continuation. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:saved-next

- Control: Read next saved-body part
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs, exact issued offers; tests/workflow_history_frontend.test.mjs
- Behaviour: Reads the next part of a saved version too long to show at once, from the owner's continuation. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:saved-workspace

- Control: Open this saved version in Workspace
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs, exact issued offers; tests/workflow_history_frontend.test.mjs
- Behaviour: Opens the complete saved version as an object in Workspace. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:design

- Control: Design
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs native progression; tests/workflow_operation_frontend.test.mjs
- Behaviour: Shows this workflow's design: its steps and settings. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:runs

- Control: Runs
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs native progression; tests/workflow_operation_frontend.test.mjs
- Behaviour: Shows the runs of this workflow and what each did. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:guide

- Control: Guide
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs native progression; tests/workflow_operation_frontend.test.mjs
- Behaviour: Shows how a design becomes a saved version, a prepared request and an admitted run; saving does not start work. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:discard

- Control: Discard unsaved edits
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design local draft only; tests/workflow_operation_frontend.test.mjs
- Behaviour: Throws away the edits made in this design that are not yet saved and returns to the saved version. Anything already saved stays.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:adapt

- Control: Use as new draft…
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design, verified saved selection through the existing ownership choice; tests/workflow_operation_frontend.test.mjs
- Behaviour: Starts a new draft from the saved version shown, through the choices the owner offers for a new workflow. The saved version itself is not changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:lineage-prepare

- Control: Prepare complete lineage export
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs actual permitted lineage descriptor; tests/workflow_history_frontend.test.mjs
- Behaviour: Asks the owner to prepare the complete lineage of this workflow for export, when its lineage description permits it. Nothing is changed in the workflow.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:preview

- Control: Check execution
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Asks the owner whether this workflow could run as designed and shows its answer. Nothing is started.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:context-read

- Control: Inspect declared context
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Reads the context a checked step declares and shows it. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:uses

- Control: Read recorded uses
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Reads where this saved version was recorded as used and shows the first page. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river

- Control: Read observed flow
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Reads the observed flow of a listed run: which steps ran and what passed between them. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:uses-more

- Control: Read more
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Reads the next page of recorded uses from the owner's continuation. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-more

- Control: Read more
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Reads the next page of the observed flow from the owner's continuation. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-read

- Control: Read a recorded response, proposal, return or run
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Reads one recorded response, proposal, return or run named in the flow and shows it. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-detail

- Control: Open run detail
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Opens the owner's full record of this run beside its summary. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:app-run-uses

- Control: Read recorded uses
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Reads where the opened run was recorded as used. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:app-run-river

- Control: Read observed flow
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Reads the observed flow of the opened run. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:app-run-reply

- Control: Read step response
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs
- Behaviour: Reads the exact reply one step of the opened run gave. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-return

- Control: Return to workflow
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Leaves the runs and returns to this workflow's design; nothing is stopped or changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-refresh

- Control: Refresh status
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Reads the selected run again from the workflow owner; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:runs-back

- Control: Back to runs
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Returns to the list of this saved version's agent runs.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-step

- Control: A step of this run
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens this step's one card in the river: its state, times, provider and model, and its recorded result, conversation and exact data; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-session

- Control: Open its session
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens the project page with this stage's session, where you can read it, write to it or stop its turn.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-explain

- Control: What is a step?
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Shows or hides two sentences explaining a step.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-guide

- Control: More in Guide
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens this workflow's Guide view.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-view

- Control: Graph view or List view
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Shows the run's stages as a free graph or as a list.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-fit

- Control: Fit workflow
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Scales the run graph to fit its box.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-center

- Control: Center selected
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Centres the run graph on the chosen stage.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-start

- Control: Prepare start message
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Composes the owner's start message for this prepared run in its original conversation; you send it there.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-parent

- Control: Open original conversation
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens the conversation in which this run was prepared.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-preparation

- Control: Preparation and launch
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Shows or hides which session and turn prepared and launched this run.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-exact

- Control: Show exact recorded data
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Shows or hides the exact recorded owner data this part of the run view was painted from.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-step-result

- Control: Read full public result and actions
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens this step's saved public result and its actions in the saved-turn reader.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-step-conversation

- Control: Open step conversation
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens this step's conversation, where you can send it a message or stop it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-continue

- Control: Prepare review continuation message
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Composes the owner's continuation message for a failed review; you send it in the conversation.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-attempts

- Control: Earlier attempts
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Shows or hides this step's earlier attempts.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-earlier-result

- Control: Read earlier public result
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens an earlier attempt's saved public result.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-typed-return

- Control: Open exact typed return
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens this step's typed return as the owner saved it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:run-retained-output

- Control: Retained worker output
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens a retained worker output this step reused.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-mark

- Control: A mark of the observed flow
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens one card for this turn, tool call, reply or dependency, with the owner's reads for it; nothing is read until you choose one.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-step

- Control: A step's lane
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens one card for this step: its state in words, provider and model, its times, and its recorded result, conversation and exact data.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-follow

- Control: Follow
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Returns the river to now and keeps it there as new marks arrive; it shows how many arrived while you looked back.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-waiting

- Control: Waiting for you
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens the first step where an owner field says the next act is yours.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-identity

- Control: Identity
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Shows or hides the exact session, turn and event ids and the raw owner state behind this card.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-list

- Control: List every mark
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Shows or hides every mark of the river as a line of text, in time order.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-conversation

- Control: Open conversation
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens the project page with this step's session.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-card-close

- Control: Close
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Closes the card; the river keeps its place.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:river-reply-more

- Control: Read more of it
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Reads the next page of the opened reply through the owner's continuation.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:runs-open

- Control: Open agent run
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs
- Behaviour: Opens this run: its drawing with each stage's marks and the river of observed flow under it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:overview

- Control: All workflows
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Returns to the list of saved workflows and templates; an unsaved draft stays in this tab.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:topology

- Control: The drawing
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows the workflow's steps and the routes between them; in an opened run, each step with its marks.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:explain

- Control: What is a step, a role, a hand-over or a review loop?
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides two sentences explaining this part of a workflow.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:explain-guide

- Control: More in Guide
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Opens this workflow's Guide view.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:save

- Control: Save definition
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Sends this draft to the workflow owner as a new saved version; saving starts no work.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stage

- Control: A step on the drawing
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Chooses this step; the column beside the drawing then shows its role, its settings with where each value comes from, what it reads and its instructions.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stage-add

- Control: Add step
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Adds a builder step with no arrows to this draft and chooses it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stage-insert

- Control: Add a step after this one
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Adds a builder step straight after the chosen one: what the chosen step passed forward now leaves from the new step, and the chosen step passes forward to it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stage-earlier

- Control: Move earlier
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Swaps the chosen step with the one before it; every arrow keeps its place.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stage-later

- Control: Move later
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Swaps the chosen step with the one after it; every arrow keeps its place.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stage-remove

- Control: Remove this step
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Removes the chosen step from this draft; a step that passed forward to it now passes forward to the step after it. A route pattern is removed the same way, step by step.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:pattern-review

- Control: Add a review of this step
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Inserts one reviewer step (role adversary, titled Review of the chosen step) straight after the chosen step, with a solid arrow from the chosen step to it and a dashed findings-back arrow from it to the chosen step; the reviewer sets no provider or model of its own. Offered only where the owner's execution check, asked about the draft it makes (its instructions still to be written), runs it; otherwise it is greyed with the owner's sentence beside it and pressing applies nothing. Reads Check first when that check cannot be read.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:pattern-reciprocal

- Control: Make these two review each other
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Inserts a reviewer after each of two builder steps, the chosen one and the one paired with it (or a new copy of the chosen step), each with a solid arrow from its builder and a dashed findings-back arrow to it: four steps and four arrows in all. The reviewer of each builder takes the other builder's provider, model and effort. Offered only where the owner's execution check, asked about the draft it makes (its instructions still to be written), runs it; otherwise it is greyed with the owner's sentence beside it and pressing applies nothing. Reads Check first when that check cannot be read.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:pattern-partner

- Control: Paired with
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Chooses the step the reciprocal review pairs with the chosen one, or a new copy of the chosen step; the owner's execution check says whether the pair runs.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:pattern-reads

- Control: The synthesis reads
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Chooses a step whose result the synthesis reads; the choice is kept only on the screen until the synthesis is added.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:pattern-synthesis

- Control: Add a synthesis that reads these
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Inserts one step titled Synthesis with the owner's synthesis role (written in the original conversation) and a dotted data-input arrow from each chosen step; it adds no other arrow. Offered only where the owner's execution check, asked about the draft it makes (its instructions still to be written), runs it; otherwise it is greyed with the owner's sentence beside it and pressing applies nothing. Reads Check first when that check cannot be read.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:policy-edit

- Control: Change these limits
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Opens Workflow details and defaults, where this workflow's review rounds, time limit and advance setting are edited.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:policy-advance

- Control: When the next step starts
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Sets the workflow's one advance setting: review starts by itself after each response, or the next step waits for your decision.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:compare

- Control: Compare draft with current
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Reads the current saved version beside this draft; nothing is saved.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:reinspect

- Control: Reinspect current
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Reads the selected saved workflow again from its owner; the draft is kept.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:prepare-external

- Control: Prepare external run…
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Opens or closes the form that prepares the saved version for an external run; preparing starts nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:prepare-agent

- Control: Prepare agent run…
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Opens or closes the form that prepares the saved version as an agent run in a project conversation.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:agent-runs

- Control: Agent runs
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows the recorded agent runs of this saved version.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:inspector-part

- Control: Step, Settings, Connections or Instructions
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Jumps to that part of the chosen step in the column.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stage-nest

- Control: Nest inside
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Puts the chosen step inside a group step, or at the top level; a group passes on only declared settings.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stage-position

- Control: Canvas position
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides the buttons that nudge the step on the free graph.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stage-nudge

- Control: Move left, up, down or right
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Moves the chosen step 24 pixels on the free graph.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:setting-step

- Control: Set for this step
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Writes this step's own provider, model, effort or input policy; Inherit removes its value here, so a containing group or the workflow defaults decide.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:setting-workflow

- Control: Set for the whole workflow
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Writes the workflow defaults for provider, model, effort or input policy, read by every step that sets no value of its own.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:setting-identity

- Control: Identity
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides the exact origin, lineage and boundary the settings owner returned for each of this step's settings.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:relation-add

- Control: Add relation
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Adds an arrow of the chosen kind from the chosen step to the step named here.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:design-view

- Control: Graph view or List view
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows the same steps as a free graph or as a list with their relations.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:graph-mode

- Control: Select / move, Connect or Nest
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Sets what a click or a drag on the free graph does.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:graph-fit

- Control: Fit workflow
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Scales the free graph to fit its box.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:graph-center

- Control: Center selected
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Centres the free graph on the chosen step.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:graph-step

- Control: A step on the free graph
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Chooses this step, or with Connect or Nest joins the chosen step to it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:list-step

- Control: A step in the list
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Chooses this step.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:step-list

- Control: Step list
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides the list of steps under the free graph.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:relations

- Control: Relations
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides every arrow of this draft as a line with its Remove button.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:relation-remove

- Control: Remove relation
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Removes this one arrow from the draft.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:back

- Control: Back to prior workflow
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Returns to the workflow opened before this one.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:purpose-edit

- Control: Edit workflow purpose
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides the field for this workflow's purpose.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:purpose-full

- Control: Full workflow purpose
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides the whole purpose when it is longer than its first paragraph.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:details

- Control: Workflow details and defaults
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides this workflow's review loop limits and human boundary.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:lineage

- Control: Share complete saved lineage
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides how many saved versions this workflow has and the owner's export of them.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:saved-history

- Control: Saved history
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides the recent saved versions of this workflow.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:technical

- Control: Technical details
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Shows or hides the exact owner scope, permissions, providers, version and draft record.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:recover

- Control: Reinspect exact request
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Asks the owner what became of the original Save or Prepare request; nothing is resent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:acknowledge

- Control: Acknowledge inspected attempt
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Clears the answered Save or Prepare result from this view; the recorded effect stays.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:prepare-submit

- Control: Prepare selected steps
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Prepares the chosen steps of the saved version for an external run; it starts nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:agent-prepare-submit

- Control: Prepare in conversation
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Composes the owner's preparation message for an agent run in the project conversation; you send it there.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:inspect-manuscript

- Control: Inspect selected manuscript
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Opens the manuscript chosen as the run's target in the reader.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:adopt-guard

- Control: Keep draft and adopt compared guard
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Keeps this draft and takes the compared current version as the version it will be saved over.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:context-choice

- Control: Also deliver
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Adds or removes one context choice the owner declares for this step, such as the result of a connected earlier step; it grants no permission.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:handoff-target

- Control: Hand the result to
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Names a later connected step that receives this step's result.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:prepare-step

- Control: A saved step to prepare
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Includes or leaves out this saved step in the preparation.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:prepare-input

- Control: A selected evidence input
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Includes or leaves out this inspected input in the agent run's preparation.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:prepare-target

- Control: Manuscript to revise
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs
- Behaviour: Chooses the document or section the agent run is prepared to revise.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:withdraw

- Control: Withdraw original request
- View: `workflows`
- Declared host/test route: workspace-workflow-editor.mjs owner withdrawal offer of an uncertain original request; tests/workflow_operation_frontend.test.mjs
- Behaviour: Asks the owner to withdraw a save or preparation whose outcome is not known, so it cannot happen later. It sends the owner's own withdrawal offer.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stop-run

- Control: Stop this run
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs shared Stop, mounted by Runs Open run detail and research-workbench-run.mjs Plan & run; tests/workflow_operation_frontend.test.mjs
- Behaviour: Asks the owner to stop this run. The run stops only if the owner records it; the page says what the owner answered.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stop-check

- Control: Check original Stop request
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs shared Stop, mounted by Runs Open run detail and research-workbench-run.mjs Plan & run; tests/workflow_operation_frontend.test.mjs
- Behaviour: Asks the owner whether the Stop request already sent was recorded. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### workflow:stop-resend

- Control: Resend original Stop unchanged
- View: `workflows`
- Declared host/test route: workspace-workflow-operation.mjs shared Stop, mounted by Runs Open run detail and research-workbench-run.mjs Plan & run; tests/workflow_operation_frontend.test.mjs
- Behaviour: Sends the original Stop request again, unchanged, after the owner's check shows it was not recorded or recorded nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
