# nav: 17 declared controls

## Concrete case

Actual public project, current source/PDF, Work and conversations

- App route: `/project?workspace=writing&corpus=behaviour-example&view=overview`.
- Supplied inputs/records: behaviour-example, WORK-example.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all nav controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### nav:skip

- Control: Skip to content
- View: `shell`
- Declared host/test route: project shell and global application entry; tests/human_workspace_shell.test.mjs
- Behaviour: Moves the keyboard focus past the navigation to the page's main content. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:backlog

- Control: All tasks
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=backlog
- Behaviour: Opens All tasks for this project. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:overview

- Control: Home
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=overview
- Behaviour: Opens the project's Home page. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:work

- Control: Tasks
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=work
- Behaviour: Opens the project's Tasks. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:material

- Control: Sources
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=material
- Behaviour: Opens the project's Sources: its files, readers and references. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:history

- Control: Activity
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=history
- Behaviour: Opens Activity: what changed in the project and when. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:settings

- Control: Settings
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=settings
- Behaviour: Opens the project's Settings. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:argument

- Control: Argument & evidence
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=argument
- Behaviour: Opens Argument and evidence: the project's claims and what supports them. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:reader-plan

- Control: Reader plan
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=reader-plan
- Behaviour: Opens the Reader plan: the order in which the paper is meant to be read. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:research

- Control: Research
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=research
- Behaviour: Opens Research: the project's results and producers. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:manuscript

- Control: Writing
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=manuscript
- Behaviour: Opens Writing: the manuscript, as source, TeX or PDF. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:review

- Control: Review & notes
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=review
- Behaviour: Opens Review and notes: proposed changes and comments. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:presentation

- Control: Figures & output
- View: `shell`
- Declared host/test route: workspace.mjs nav button data-view=presentation
- Behaviour: Opens Figures and output: the manuscript PDF and derived outputs. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:menu

- Control: Menu
- View: `shell`
- Declared host/test route: workspace.mjs header [data-nav]; shown in the compact and drawer navigation layouts
- Behaviour: Shows or hides the project navigation on a narrow window. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:more-tools

- Control: More project tools
- View: `shell`
- Declared host/test route: workspace-chrome.mjs project navigation; tests/human_workspace_shell.test.mjs
- Behaviour: Shows the project's rarer pages: Review & notes, Activity, Settings, Argument & evidence, Reader plan and Figures & output.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:live-task

- Control: Current task
- View: `shell`
- Declared host/test route: workspace-chrome.mjs the project navigation, Running now, while the conversation owner observes a turn running; tests/workspace_control_coverage.test.mjs 'shell/running-now'
- Behaviour: Opens the task the running turn is working on, named by the Work owner; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### nav:live-conversation

- Control: Active conversation
- View: `shell`
- Declared host/test route: workspace-chrome.mjs the project navigation, Running now, while the conversation owner observes a turn running; tests/workspace_control_coverage.test.mjs 'shell/running-now'
- Behaviour: Opens the conversation the owner observes running, so its turn can be followed; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
