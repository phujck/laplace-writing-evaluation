# projects: 9 declared controls

## Concrete case

Project, definitions, Work and owner discovery

- App route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Supplied inputs/records: examples/verification/default-owner-suite.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups core`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all projects controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### projects:task-write

- Control: Start writing
- View: `projects`
- Declared host/test route: project-work.mjs the Projects page; tests/workspace_control_coverage.test.mjs 'projects/page'
- Behaviour: Chooses 'start writing': the list below then opens each project at its Writing page.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### projects:task-source

- Control: Read a source
- View: `projects`
- Declared host/test route: project-work.mjs the Projects page; tests/workspace_control_coverage.test.mjs 'projects/page'
- Behaviour: Chooses 'read a source': the list below then opens each project at its Sources page.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### projects:task-tasks

- Control: Organise tasks
- View: `projects`
- Declared host/test route: project-work.mjs the Projects page; tests/workspace_control_coverage.test.mjs 'projects/page'
- Behaviour: Chooses 'organise tasks': the list below then opens each project at its Tasks page.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### projects:task-open

- Control: Open existing project
- View: `projects`
- Declared host/test route: project-work.mjs the Projects page; tests/workspace_control_coverage.test.mjs 'projects/page'
- Behaviour: Chooses 'open an existing project': the list below then opens each project at its Home page.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### projects:create-toggle

- Control: Create a project
- View: `projects`
- Declared host/test route: project-work.mjs the Projects page; tests/workspace_control_coverage.test.mjs 'projects/page'
- Behaviour: Shows the form that creates a project; nothing is created until you press Create project.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### projects:create

- Control: Create project
- View: `projects`
- Declared host/test route: project-work.mjs the Projects page; tests/workspace_control_coverage.test.mjs 'projects/page'
- Behaviour: Creates the project from the title, category, purpose and audience you typed, then opens it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### projects:find-existing

- Control: Find existing manuscripts
- View: `projects`
- Declared host/test route: project-work.mjs the Projects page; tests/workspace_control_coverage.test.mjs 'projects/page'
- Behaviour: Asks the project owner to list manuscripts it can register from this computer; it only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### projects:category

- Control: Project category
- View: `projects`
- Declared host/test route: project-work.mjs the Projects page; tests/workspace_control_coverage.test.mjs 'projects/page'
- Behaviour: Chooses the kind of project to create: general, article, book, software, company, transcript or campaign.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### projects:project

- Control: Project
- View: `projects`
- Declared host/test route: project-work.mjs the project list of Projects; tests/workspace_control_coverage.test.mjs 'projects/page'
- Behaviour: Opens this project in the way chosen above the list: writing, a source, tasks or its Home; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
