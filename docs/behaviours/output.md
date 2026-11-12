# output: 8 declared controls

## Concrete case

Actual tiny current PDF; guarded template preview/apply recipe

- App route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Supplied inputs/records: behaviour-example current source/artifacts and owner-issued actions.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: Declared TeX toolchain for build/template preview; current retained PDF can be read without building.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all output controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### output:document

- Control: Manuscript PDF
- View: `presentation`
- Declared host/test route: workspace-output.mjs Manuscript PDF card (object header, document chips, Build primary)
- Behaviour: Shows or hides the manuscript PDF card: its state, when it was built and the Build button. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### output:derived

- Control: Derived output
- View: `presentation`
- Declared host/test route: derived-output.mjs derived output card (object header with status chip)
- Behaviour: Shows or hides the derived output card: its state and its build. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### output:build

- Control: Build manuscript PDF
- View: `presentation`
- Declared host/test route: workspace-output.mjs Figures and output; tests/workspace_control_coverage.test.mjs 'presentation/not-built'
- Behaviour: Builds the manuscript PDF from the document the owner describes; the owner's own build request is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### output:develop-figure

- Control: Develop a figure
- View: `presentation`
- Declared host/test route: workspace-output.mjs Figures and output; tests/workspace_control_coverage.test.mjs 'presentation/not-built'
- Behaviour: Prepares a message in the conversation panel asking Eigen to develop a figure for the argument; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### output:document-setup

- Control: Open document setup
- View: `presentation`
- Declared host/test route: workspace-output.mjs Figures and output; tests/workspace_control_coverage.test.mjs 'presentation/not-built'
- Behaviour: Opens Writing with Document setup, where the document's template and preamble are set.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### output:build-details

- Control: Build details
- View: `presentation`
- Declared host/test route: workspace-output.mjs Figures and output; tests/workspace_control_coverage.test.mjs 'presentation/not-built'
- Behaviour: Shows the build's reason, error and the last lines of its log.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### output:refresh-derived

- Control: Refresh derived output
- View: `presentation`
- Declared host/test route: derived-output.mjs derived output; tests/workspace_control_coverage.test.mjs 'presentation/not-built'
- Behaviour: Reads the derived output's status again from its owner; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### output:reader-plan-absence

- Control: Reader-plan output is not configured
- View: `presentation`
- Declared host/test route: derived-output.mjs the derived output card when the owner reports no reader-plan output; tests/workspace_control_coverage.test.mjs 'presentation/seeded'
- Behaviour: Says why the project has no reader-plan output, in the owner's words, or that it is not prepared yet; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
