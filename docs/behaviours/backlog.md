# backlog: 22 declared controls

## Concrete case

Project, definitions, Work and owner discovery

- App route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Supplied inputs/records: examples/verification/default-owner-suite.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups core`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all backlog controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### backlog:historical

- Control: Historical engine obligations
- View: `historical-obligations`
- Declared host/test route: workspace-source-inspector.mjs openHistoricalObligations
- Behaviour: Shows or hides the engine obligations recorded before this app; each is read as the owner holds it. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:catalogue

- Control: Whole Work catalogue
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs
- Behaviour: Shows every task in the workspace as the owner lists it, one page at a time. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:filters

- Control: Filter whole backlog
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs
- Behaviour: Narrows the list of all tasks by the fields the owner offers for filtering. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:inspect

- Control: Inspect exact Work
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs
- Behaviour: Opens one task from the list of all tasks, with its full record. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:planning

- Control: Save Work planning
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs
- Behaviour: Saves the planning fields of this task through the owner. The page says what the owner recorded.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:check

- Control: Check original planning save
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs
- Behaviour: Asks the owner whether the planning save already sent was recorded. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:add-task-open

- Control: Add task in a project
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Shows one link per registered project; each opens that project's Tasks page at its Add task form. Nothing is created here.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:guide

- Control: How task planning works
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Explains in a few lines what the catalogue shows, how search and filters read, and that planning changes no execution.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:queue-active

- Control: Unfinished tasks, not deferred
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Reads the owner's unfinished-and-not-deferred queue and adopts its filters.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:queue-all

- Control: All tasks and closed records
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Reads every recorded task, closed ones included, and adopts the owner's filters for it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:source-contracts

- Control: Inspect Source contracts
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Opens the Source inspector for the contracts the catalogue read lists; it only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:historical-open

- Control: Historical engine records (separate from current tasks)
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Lists the engine's historical work orders and promises, kept apart from current tasks.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:filter-options

- Control: Status and planning filters
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Shows the owner's further filters: status, planning and the rest the catalogue read offers.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:refresh

- Control: Refresh catalogue
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Reads the Work catalogue again with the filters now set; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:row-details

- Control: Status, planning and owner details
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Shows the exact status, planning and owner fields the catalogue recorded for this task.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:suggested

- Control: Suggested next to inspect
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Opens the task the catalogue read suggests next, for inspection only.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:filter

- Control: Catalogue filter
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Sets one of the owner's catalogue filters (search, namespace, lifecycle and the rest); Find Work then applies them.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:plan

- Control: Plan this Work
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Opens the planning form for this task from its owner-issued planning read; nothing is saved until you save there.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:more

- Control: More Work
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Reads the next page of the catalogue by the owner's own continuation handle.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:historical-records

- Control: Historical engine records
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Opens one of the engine's historical record lists beside the catalogue; it only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:add-task-in

- Control: Add a task in this project
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Opens that project's Tasks page at its Add task form.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### backlog:add-task-create

- Control: Create or open a project
- View: `backlog`
- Declared host/test route: workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'
- Behaviour: Goes to the Projects page when no registered project exists to add a task in.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
