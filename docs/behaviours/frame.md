# frame: 11 declared controls

## Concrete case

Actual public project, current source/PDF, Work and conversations

- App route: `/project?workspace=writing&corpus=behaviour-example&view=overview`.
- Supplied inputs/records: behaviour-example, WORK-example.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all frame controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### frame:menu

- Control: Menu
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs (every page, with or without a project)
- Behaviour: Opens the workspace places as a list on a narrow window; inside a project it shows or hides the project's own navigation. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:switch

- Control: Switch project
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs (every page, with or without a project)
- Behaviour: Opens the project switcher: the projects you opened most recently first, with a search. Nothing is changed until you choose one.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:more

- Control: More
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs (every page, with or without a project)
- Behaviour: Lists the four rarer workspace pages: Explore across projects, Workspace dependencies, System owners and App settings.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:place

- Control: Workspace place
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs place links (Now, Sessions, All tasks, Workflows, Projects)
- Behaviour: Goes to that workspace page: Now, Sessions, All tasks, Workflows or Projects. The place's name is the link's text; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:menu-place

- Control: Workspace place (menu)
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs the narrow menu's place links and Help (listed in the project navigation inside a project)
- Behaviour: Goes to that workspace page from the narrow menu: a place, or one of More's four pages.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:menu-help

- Control: Help (menu)
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs the narrow menu's Help (listed in the project navigation inside a project)
- Behaviour: Opens help for the page you are on, from the narrow menu.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:more-page

- Control: More page
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs More's list, opened
- Behaviour: Goes to one of More's pages: Explore across projects, Workspace dependencies, System owners or App settings.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:switch-all

- Control: All projects
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs the project switcher panel, opened
- Behaviour: Goes to the Projects page, the full list of your projects and writing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:switch-create

- Control: Create a project
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs the project switcher panel, opened
- Behaviour: Goes to the Projects page with the create form open; nothing is created until you save there.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:switch-row

- Control: Switch to this project
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs the project switcher panel, opened and read
- Behaviour: Opens that project on the same kind of page you are on (Writing only where it has a manuscript). Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### frame:return

- Control: Return to project
- View: `shell`
- Declared host/test route: workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs Return to project (a workspace page opened from a project)
- Behaviour: Goes back to the project page this workspace page was opened from.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
