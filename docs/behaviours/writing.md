# writing: 19 declared controls

## Concrete case

Loopback Save/reopen, stale Work/source guards

- App route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Supplied inputs/records: examples/verification/default-owner-suite.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups core,http`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all writing controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### writing:sources

- Control: Sources beside writing
- View: `manuscript`
- Declared host/test route: ready native Writing host toolbar; tests/human_workspace_shell.test.mjs
- Behaviour: Shows or hides the Sources panel beside the writing page, so a source can be read next to the text. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:mode-write

- Control: Write
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Shows the manuscript for writing in the editor.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:mode-tex

- Control: TeX
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Shows the manuscript's TeX source.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:tools

- Control: Document tools
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Shows the secondary writing tools: setup, build details and file history.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:mode-pdf

- Control: PDF
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Shows the built manuscript PDF.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:build

- Control: Build PDF
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Builds the manuscript PDF through the document owner's build request.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:build-details

- Control: Build details
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Opens Document setup at the last build's reason, error and log.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:file-history

- Control: File history
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Opens the recorded history of the manuscript's file.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:setup

- Control: Document setup
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Shows the document's template, root file and preamble, and whether a template change is offered.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:build-log

- Control: Build details
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Shows the build's reason, error and the last lines of its log, as the document owner reports them.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:build-basis

- Control: Exact build basis
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Shows the exact root file and PDF state the build is made from.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:open-root

- Control: Open root and preamble
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'
- Behaviour: Opens the manuscript's root file at its preamble in the TeX view.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:setup-file

- Control: Document file
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs Document setup, the files the build uses as relation rows; tests/workspace_control_coverage.test.mjs 'manuscript/setup-open'
- Behaviour: Opens that file of the document in the Writing editor; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:source-file

- Control: Source file
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs Writing > TeX, the source pane; tests/workspace_control_coverage.test.mjs 'manuscript/source-tex'
- Behaviour: Chooses which source file of the manuscript the TeX pane shows; unsaved edits are kept as a draft for the file they belong to.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:source-reload

- Control: Reload saved source
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs Writing > TeX, the source pane; tests/workspace_control_coverage.test.mjs 'manuscript/source-tex'
- Behaviour: Reads the shown file again from its owner and replaces the pane with what is saved; an unsent draft is kept until you discard it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:source-preamble

- Control: Preamble
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs Writing > TeX, the source pane; tests/workspace_control_coverage.test.mjs 'manuscript/source-tex'
- Behaviour: Opens the manuscript preamble (the lines before the document begins) in the pane; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:source-copy

- Control: Copy draft
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs Writing > TeX, the source pane; tests/workspace_control_coverage.test.mjs 'manuscript/source-tex'
- Behaviour: Copies the draft text you are editing to the clipboard; nothing is saved or sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:source-compare

- Control: Compare saved source
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs Writing > TeX, the source pane; tests/workspace_control_coverage.test.mjs 'manuscript/source-tex'
- Behaviour: Shows your draft beside the saved source of the file, to see what differs; nothing is saved.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### writing:source-discard

- Control: Discard source draft
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs Writing > TeX, the source pane; tests/workspace_control_coverage.test.mjs 'manuscript/source-tex'
- Behaviour: Throws away the draft of this file and shows the saved source again; what was saved is not changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
