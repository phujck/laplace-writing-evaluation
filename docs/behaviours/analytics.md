# analytics: 35 declared controls

## Concrete case

CAS, event replay, projection rebuild, snapshot/spans/refusals

- App route: `/project?workspace=writing&corpus=behaviour-example&view=history`.
- Supplied inputs/records: examples/verification/default-owner-suite.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups atlas`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all analytics controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### analytics:refresh

- Control: Refresh
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Reads the shown Graphs view again from the owner; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:view-tab

- Control: Activity view
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Switches Graphs to Overview, Graphs & analysis, Selected activity, Usage, Feedback, Delivery or Coverage and reads that view from the owner; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:view-select

- Control: Activity view
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Switches Graphs to another of its views from the list shown beside the plots; it reads that view from the owner and changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:open-changes

- Control: Changes & history
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Leaves Graphs for the Activity timeline of recorded changes, with the same filters; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:open-conversations

- Control: Conversations
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Opens the list of saved conversations; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:filter-project

- Control: Project activity filter
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Chooses which project's recorded activity Graphs shows; it applies when Apply filters is pressed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:apply-filters

- Control: Apply filters
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Reads the shown Graphs view again with the filters you set; it is the only way a filter takes effect and it changes nothing recorded.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:more-filters

- Control: More call filters
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Shows the provider, conversation, operation and outcome filters for the plots; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:basis

- Control: Scope, coverage & recorded basis
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Shows the scope, the coverage counts, the limits and the recorded cut this view was read at; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:inspect-conversation

- Control: Inspect conversation activity
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Reads the recorded activity of this one conversation and shows it as Selected activity; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:open-conversation

- Control: Open conversation
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Opens this saved conversation in the conversation panel; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:open-work

- Control: Open work
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Opens the task this conversation or event is recorded against; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:read-commissioning-turn

- Control: Read commissioning turn
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Opens the saved turn that commissioned this conversation; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:note-reply

- Control: Note on latest reply
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Opens a box for a note about this conversation's latest saved reply; nothing is saved until Save response note.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:conversation-basis

- Control: Recorded conversation basis
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Shows how this conversation's title, models and live state were established; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:more

- Control: More recorded activity
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Reads the next page of this view from the owner's own continuation and adds it below; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:inspect-record

- Control: Inspect recorded basis
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Reads the exact saved record behind this row from the owner and shows it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:inspect-admission

- Control: Inspect immutable admission
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Reads the exact saved admission record of this turn from the owner and shows it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:read-turn

- Control: Read turn
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Opens the saved turn this row belongs to; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:read-target-turn

- Control: Read target turn
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Opens the saved turn this feedback record is about; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:usage-attempt

- Control: Usage attempt
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Shows one saved attempt's context counter, logical-turn and binding counts; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:audit-observations

- Control: Audit selected observations
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Shows the owner's exact selected observations for this attempt, as saved; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:audit-delivery

- Control: Audit delivery receipt
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Shows the owner's exact delivery receipt for this turn, as saved; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:feedback-lineage

- Control: Exact target and lineage
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Shows the exact feedback target and its saved lineage; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:retry

- Control: Retry this view
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Reads the failed Graphs view again from the owner; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:audit-record

- Control: Audit exact public record
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Shows the saved record exactly as the owner returned it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:note-close

- Control: Close
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Closes the response note box; the text typed there is kept for this response.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:note-save

- Control: Save response note
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Saves the note as an observation about this response; the page says what was recorded, or that nothing was and the note is kept.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:note-read-turn

- Control: Read the saved turn
- View: `history`
- Declared host/test route: workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'
- Behaviour: Opens the saved turn this response came from; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:time-bar

- Control: Calls in a recorded interval
- View: `history`
- Declared host/test route: workspace-analysis.mjs Activity > Graphs > Graphs & analysis, the plots; tests/workspace_control_coverage.test.mjs 'history/graphs-analysis'
- Behaviour: Opens the Activity timeline filtered to the calls the owner counted in this recorded interval; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:usage-bar

- Control: Reported usage count
- View: `history`
- Declared host/test route: workspace-analysis.mjs Activity > Graphs > Graphs & analysis, the plots; tests/workspace_control_coverage.test.mjs 'history/graphs-analysis'
- Behaviour: Opens the Usage view for the provider and model this bar's reported count belongs to; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:outcome-bar

- Control: Recorded outcome
- View: `history`
- Declared host/test route: workspace-analysis.mjs Activity > Graphs > Graphs & analysis, the plots; tests/workspace_control_coverage.test.mjs 'history/graphs-analysis'
- Behaviour: Opens the Activity timeline filtered to the calls the owner recorded with this outcome; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:runtime-point

- Control: Producer run duration
- View: `history`
- Declared host/test route: workspace-analysis.mjs Activity > Graphs > Graphs & analysis, the plots; tests/workspace_control_coverage.test.mjs 'history/graphs-analysis'
- Behaviour: Opens the Activity timeline filtered to the result history of this producer run; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:run-read

- Control: Producer run
- View: `history`
- Declared host/test route: workspace-analysis.mjs Activity > Graphs > Graphs & analysis, the plots; tests/workspace_control_coverage.test.mjs 'history/graphs-analysis'
- Behaviour: Opens the Activity timeline filtered to the exact recorded result of this producer run; it is off for a run with no result history.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### analytics:analysis-basis

- Control: Analysis cut and exclusions
- View: `history`
- Declared host/test route: workspace-analysis.mjs Activity > Graphs > Graphs & analysis, the plots; tests/workspace_control_coverage.test.mjs 'history/graphs-analysis'
- Behaviour: Shows the recorded cut the plots were read at and how many earlier cells and operations were left out; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
