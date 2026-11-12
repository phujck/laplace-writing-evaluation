# reader-plan: 11 declared controls

## Concrete case

Typed section/paragraph and heading guards

- App route: `/project?workspace=writing&corpus=behaviour-example&view=reader-plan`.
- Supplied inputs/records: examples/verification/default-owner-suite.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups core,reader`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all reader-plan controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### reader-plan:open-in-manuscript

- Control: Open in manuscript
- View: `reader-plan`
- Declared host/test route: workspace-spine.mjs objectHeader primary action
- Behaviour: Opens the file the selected section was read from, at its heading when the owner knows it, else the file or the owner's suggested file; the label says which. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:item

- Control: Reader-plan item
- View: `reader-plan`
- Declared host/test route: workspace-spine.mjs ordered plan row (orderedPlan control)
- Behaviour: Selects one plan row and shows its detail, as the owner holds it. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:relation-map

- Control: Relation map
- View: `reader-plan`
- Declared host/test route: workspace-spine.mjs lazy relation map (workspace-topology)
- Behaviour: Shows or hides the map of how the plan's parts relate; it is read when opened. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:paragraph-action

- Control: Paragraph plan action
- View: `reader-plan`
- Declared host/test route: reader-state.mjs paragraph card actions (edit, move, remove) opened on a bounded subject read
- Behaviour: Opens one paragraph's plan action (edit, move or remove) on a read of that paragraph. Nothing is changed until the action is confirmed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:guard

- Control: Reader-plan guard subject
- View: `shared`
- Declared host/test route: reader-state.mjs read-only inspector of one saved/nested projection:guard subject (writing-artifact routes it; no reader-plan remount, no extra read)
- Behaviour: Opens a read-only view of one saved guard subject. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:paragraph-expand

- Control: Read whole paragraph plan
- View: `reader-plan`
- Declared host/test route: reader-state.mjs display row door (shortened or omitted fields); one owner row_read with that paragraph_id, read only
- Behaviour: Reads the whole plan of one paragraph, where the display shortened or left out fields. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:transition-expand

- Control: Read full reader transition
- View: `reader-plan`
- Declared host/test route: reader-state.mjs reader-transition door when the display shortened its text; one owner values_read, read only
- Behaviour: Reads the full text of a reader transition the display shortened. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:unit-select

- Control: Planned unit
- View: `reader-plan`
- Declared host/test route: reader-state.mjs unit row; opens one unit
- Behaviour: Opens or closes one planned unit. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:acknowledge-inputs

- Control: Record inspected inputs
- View: `reader-plan`
- Declared host/test route: reader-state.mjs Inputs and open points; one guard read, then a metadata-only observation (not review)
- Behaviour: Records that you inspected the plan's inputs and open points, after one fresh read. It records an observation, not a review.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:refresh

- Control: Refresh reader plan
- View: `reader-plan`
- Declared host/test route: workspace-spine.mjs Reader plan; tests/workspace_control_coverage.test.mjs 'reader-plan/selected'
- Behaviour: Reads the reader plan again from its owner; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### reader-plan:create-item

- Control: Create reader-plan item
- View: `reader-plan`
- Declared host/test route: workspace-spine.mjs Reader plan; tests/workspace_control_coverage.test.mjs 'reader-plan/selected'
- Behaviour: Starts a new reader-plan item for the selected scope; nothing is recorded until you save.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
