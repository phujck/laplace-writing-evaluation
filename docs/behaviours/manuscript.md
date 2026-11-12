# manuscript: 6 declared controls

## Concrete case

Exact atomic source deletion/refusal/inverse/reopen

- App route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Supplied inputs/records: examples/verification/default-owner-suite.json, examples/verification/manual-undo-save-reopen.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups core,source`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all manuscript controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### manuscript:outline

- Control: Document outline
- View: `shell`
- Declared host/test route: workspace.mjs nav outline control
- Behaviour: Shows or hides the outline of the manuscript beside the page. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### manuscript:focus

- Control: Focus manuscript
- View: `shell`
- Declared host/test route: workspace.mjs header [data-focus]
- Behaviour: Hides the navigation so only the manuscript shows, and brings it back when pressed again. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### manuscript:document-setup

- Control: Document setup
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs Document setup panel (object header, files as relation rows, Exact build basis)
- Behaviour: Shows or hides Document setup: the files the build uses and the exact build basis. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### manuscript:undo

- Control: Undo
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs editor band (Write mode; walk undoEdit)
- Behaviour: Undoes the last edit in the editor. The document changes only through the editor's own save.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### manuscript:redo

- Control: Redo
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs editor band (Write mode; walk redoEdit)
- Behaviour: Restores the edit just undone in the editor. The document changes only through the editor's own save.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### manuscript:template-layout

- Control: Template & layout
- View: `manuscript`
- Declared host/test route: manuscript-editor.mjs Document setup primary action when the owner offers a template
- Behaviour: Opens the template and layout choices the owner offers for this document. Nothing is changed until one is applied.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
