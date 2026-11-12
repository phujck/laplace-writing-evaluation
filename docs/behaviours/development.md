# development: 11 declared controls

## Concrete case

Owned disposable Git Source recipe with runnable source/test inputs

- App route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Supplied inputs/records: behaviour-example current source/artifacts and owner-issued actions.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: New owned local Git repository, real Source grant and approved reviewer; provided sample_module.py/test_sample.py are runnable inputs.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all development controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### development:read

- Control: Read again
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: Reads the Work's development status again from the development owner; nothing changes.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:cut-lane

- Control: Cut a lane
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: Sends the owner's lane offer: a lean copy of the app source (src, tests, scripts, profiles) is cut at the serving checkout's commit, and this session is granted to read, write and check in it, never in the live tree.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:discard-lane

- Control: Discard the lane
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: First press asks again; Discard now sends the owner's discard offer: the lane grant is revoked and the lane folder, with anything in it that was not adopted, is removed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:keep-lane

- Control: Keep the lane
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: Withdraws the pending Discard; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:run-check

- Control: Run a check profile
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: Sends the owner's offer to run this fixed check profile in the lane's isolated sandbox, with the file names typed beside it when the profile takes them; the result lists the failing test names read from the runner's output.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:check-targets

- Control: Files for a check
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: The test or source files this check runs, separated by spaces; the owner refuses a name outside the profile's globs. Kept in this browser until it is cleared.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:more-checks

- Control: Show older checks
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: Reads the next page of checks through the owner's next_read.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:failing-all

- Control: Show all listed names
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: Shows or hides every failing test name the owner listed for this check; the first eight are always shown.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:adopt-preview

- Control: Preview Adopt
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment paintPreview and paintAdopt, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: Reads what Adopt would change in the live tree: the files (tool and profile files flagged), the checks and any newly failing tests against the live commit, the reviews that would no longer be current and the publication inputs the close re-reads; nothing changes.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:adopt

- Control: Adopt
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment paintPreview and paintAdopt, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: First press asks again; Adopt now sends the preview's adopt offer: the lane diff is applied to the live tree and committed locally with a Work-Id trailer, the lane grant is revoked and the lane folder removed. Nothing is pushed. Refused, with the owner's sentence beside it, while a close or another development action holds its lock, the live tree moved or a check is newly failing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### development:adopt-cancel

- Control: Not now
- View: `shell`
- Declared host/test route: workspace-development.mjs mountDevelopment paintPreview and paintAdopt, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs
- Behaviour: Withdraws the pending Adopt; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
