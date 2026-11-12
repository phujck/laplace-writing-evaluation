# tasks: 9 declared controls

## Concrete case

Project, definitions, Work and owner discovery

- App route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Supplied inputs/records: examples/verification/default-owner-suite.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups core`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all tasks controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### tasks:add-open

- Control: Add task
- View: `work`
- Declared host/test route: workspace-work-view.mjs existing task creator
- Behaviour: Opens the form for a new task, with the cursor in its title. Nothing is created until the form's own Add task is pressed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### tasks:add

- Control: Add task
- View: `work`
- Declared host/test route: workspace-work-view.mjs existing task form
- Behaviour: Holds the new task form: title, completion condition, and under it the type, containing task and prerequisites. Nothing is created until Add task is pressed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### tasks:add-summary

- Control: Add task
- View: `work`
- Declared host/test route: workspace-work-view.mjs the task creator; tests/workspace_control_coverage.test.mjs 'work/catalogue'
- Behaviour: Shows the form that adds a task to this project; nothing is added until you press Add task.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### tasks:add-more

- Control: Type, containing work and prerequisites
- View: `work`
- Declared host/test route: workspace-work-view.mjs the task creator; tests/workspace_control_coverage.test.mjs 'work/catalogue'
- Behaviour: Shows the task's type, the task that contains it and the tasks it waits on.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### tasks:add-submit

- Control: Add task
- View: `work`
- Declared host/test route: workspace-work-view.mjs the task creator; tests/workspace_control_coverage.test.mjs 'work/catalogue'
- Behaviour: Adds the task you described to this project through the owner's request.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### tasks:add-exact

- Control: Add by exact id
- View: `work`
- Declared host/test route: workspace-work-view.mjs the task creator; tests/workspace_control_coverage.test.mjs 'work/catalogue'
- Behaviour: Chooses the task whose exact id you typed as the containing or prerequisite task.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### tasks:add-type

- Control: Task type
- View: `work`
- Declared host/test route: workspace-work-view.mjs the task creator; tests/workspace_control_coverage.test.mjs 'work/catalogue'
- Behaviour: Chooses the new task's type: research, writing and the other kinds the owner offers.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### tasks:add-prerequisites

- Control: Prerequisites
- View: `work`
- Declared host/test route: workspace-work-view.mjs the task creator; tests/workspace_control_coverage.test.mjs 'work/catalogue'
- Behaviour: Chooses the tasks the new task waits on.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### tasks:add-parent

- Control: Containing work
- View: `work`
- Declared host/test route: workspace-work-view.mjs the task creator; tests/workspace_control_coverage.test.mjs 'work/catalogue'
- Behaviour: Chooses the task that will contain the new one, or the project root.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
