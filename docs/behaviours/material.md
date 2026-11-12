# material: 24 declared controls

## Concrete case

Owner-custodied original artifacts and local-document intake recipe

- App route: `/project?workspace=writing&corpus=behaviour-example&view=material`.
- Supplied inputs/records: behaviour-example current source/artifacts and owner-issued actions.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: A locally owned/authorised document; supplied authored original and parameter artifacts are safe examples.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all material controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### material:add-document

- Control: Add local document
- View: `material`
- Declared host/test route: workspace-material.mjs Add local document entry; opens the form without selecting or uploading a file
- Behaviour: Opens the form for adding a local document. No file is chosen or uploaded until the form is used.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:add-literature

- Control: Add to Literature
- View: `material`
- Declared host/test route: workspace-material.mjs retained-original entry; also on intake and exact-source readers; opens explicit metadata form
- Behaviour: Opens the form for adding a retained original to Literature, with its metadata to fill in. Nothing is added until the form is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:reader

- Control: Project reader
- View: `material`
- Declared host/test route: workspace-material.mjs relation rows of the project readers
- Behaviour: Opens one of the project's readers. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:file

- Control: Recorded file
- View: `material`
- Declared host/test route: workspace-material.mjs recorded file card (availability chip, Read primary); a region, not a control: selecting a card has no owner meaning, its Read, Add to Literature and More are the controls
- Behaviour: Marks one recorded file's card; selecting a card has no meaning of its own, and its Read, Add to Literature and More buttons are the controls.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:binding

- Control: Shared material binding
- View: `material`
- Declared host/test route: workspace-material.mjs shared material card (currentness chip)
- Behaviour: Opens one shared material binding with its currentness, as the owner records it. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:refresh-sources

- Control: Refresh sources
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Reads the project's recorded source files again; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:refresh-shared

- Control: Refresh shared material
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Reads the project's shared material links again; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:file-manage

- Control: Manage
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Shows what you can do with this recorded file: inspect it, adopt a newer revision or remove its reference.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:owner

- Control: Material owner
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Chooses which source repository or project artifact owner the material you link comes from.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:owner-type

- Control: Material owner type
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Chooses whether the material you link is a source-repository file or a project artifact.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:file-more

- Control: More
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Shows more actions and the exact identity of this recorded file.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:link-options

- Control: Link another source
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Shows the form that links another repository file or project artifact to this project.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:readers

- Control: Other project reading views
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Lists the other pages that read this project's material: Writing, Research, Review and Figures.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:prepare-reader

- Control: Prepare text-only reader
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Prepares a text-only reader for this source from its inspected revision; nothing is changed in the source.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:adopt

- Control: Adopt inspected revision
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Records this binding against the revision you just inspected, through the material owner's own request.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:remove-reference

- Control: Remove reference
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Removes this project's reference to the source; the source itself is not touched.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:discuss

- Control: Prepare a question about this file
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Prepares a message about this file in the conversation panel; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:file-history

- Control: Related file history
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Opens the recorded history that names this file; it only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:inspect

- Control: Inspect material
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Reads the material you described and shows what its owner says now; nothing is linked yet.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:link

- Control: Link inspected revision
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Links the inspected revision to this project through the material owner's request.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:read

- Control: Read a recorded file
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Opens this recorded file in the reader; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:inspect-binding

- Control: Inspect a shared binding
- View: `material`
- Declared host/test route: workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'
- Behaviour: Reads the exact stored owner of this shared binding and shows what it says now; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:open-owner

- Control: Open material owner
- View: `material`
- Declared host/test route: workspace-material.mjs the Manage panel of a shared material binding; tests/workspace_control_coverage.test.mjs 'material/panels-open'
- Behaviour: Opens the page of the owner of this material, or its read record when a repository owns it; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### material:artifact-scope

- Control: Artifact scope
- View: `material`
- Declared host/test route: workspace-material.mjs Sources > shared material, the link form; tests/workspace_control_coverage.test.mjs 'material/bindings-artifact'
- Behaviour: Chooses whether the artifact path is read in the project's files or in the manuscript's files; it applies when you inspect the material.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
