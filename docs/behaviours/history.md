# history: 17 declared controls

## Concrete case

Exact atomic source deletion/refusal/inverse/reopen

- App route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Supplied inputs/records: examples/verification/default-owner-suite.json, examples/verification/manual-undo-save-reopen.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups core,source`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all history controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### history:entry

- Control: Activity entry
- View: `history`
- Declared host/test route: workspace-history.mjs timeline row
- Behaviour: Opens one activity record to show its exact details. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:category

- Control: Activity category
- View: `history`
- Declared host/test route: workspace-history.mjs category select bound to the owner category filter (manuscript by default)
- Behaviour: Chooses which category of activity the timeline lists; manuscript activity is the default. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:tab

- Control: Changes or Graphs
- View: `history`
- Declared host/test route: workspace-history.mjs tab strip; Changes is the default, Graphs opens the analytics projections
- Behaviour: Switches between the list of changes and the graphs drawn from the same record. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:open-target

- Control: Open affected object
- View: `history`
- Declared host/test route: workspace-history.mjs record links (repo_file match or the record's saved text)
- Behaviour: Opens the object an activity record affected, when the record names one. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:actor

- Control: Activity actor
- View: `history`
- Declared host/test route: workspace-history.mjs and history-telemetry.mjs Activity
- Behaviour: Narrows the timeline to the actor you choose; the timeline is read again with that filter.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:tab-changes

- Control: Changes
- View: `history`
- Declared host/test route: workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'
- Behaviour: Shows the timeline of recorded changes; it is the page's current tab.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:tab-graphs

- Control: Graphs
- View: `history`
- Declared host/test route: workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'
- Behaviour: Replaces the timeline with the session analytics graphs for this project.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:coverage

- Control: What this history contains
- View: `history`
- Declared host/test route: workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'
- Behaviour: Lists which records this history draws on and what it cannot establish.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:refresh

- Control: Refresh history
- View: `history`
- Declared host/test route: workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'
- Behaviour: Reads the project's recorded activity again from the first page; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:overview

- Control: Show activity overview
- View: `history`
- Declared host/test route: workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'
- Behaviour: Shows the activity overview: who acted, when, and what was recorded.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:telemetry-limits

- Control: Call-count coverage
- View: `history`
- Declared host/test route: history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'
- Behaviour: Shows what the recorded call counts cover and what they leave out.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:overview-details

- Control: Project activity, actors and recorded evidence
- View: `history`
- Declared host/test route: history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'
- Behaviour: Shows the activity by actor and by record kind for this project.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:measurement-limits

- Control: What these measurements cover
- View: `history`
- Declared host/test route: history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'
- Behaviour: Shows what these activity measurements cover and what they leave out.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:telemetry-filter

- Control: Telemetry filter
- View: `history`
- Declared host/test route: history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'
- Behaviour: Narrows the activity to the bar, cell or time bucket you pressed, by the filter the owner issued for it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:telemetry-select

- Control: Telemetry scope
- View: `history`
- Declared host/test route: history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'
- Behaviour: Chooses the provider or other scope the call telemetry is shown for.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:tool-view

- Control: Tool frequency view
- View: `history`
- Declared host/test route: history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'
- Behaviour: Chooses how tool frequency is drawn: histogram or rank on linear or logarithmic axes.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### history:download-state

- Control: Download full saved state
- View: `history`
- Declared host/test route: workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'
- Behaviour: Downloads the project's whole saved authoring state as a file, read from the owner; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
