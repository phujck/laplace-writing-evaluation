# settings: 27 declared controls

## Concrete case

Actual neutral writing-style selection and public app preference recipe

- App route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Supplied inputs/records: profiles/voice/public-demo-v1.md.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all settings controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### settings:family

- Control: Settings family
- View: `settings`
- Declared host/test route: workspace-app.mjs family head (scope chip and one sentence of effect)
- Behaviour: Shows or hides one family of settings with the scope it comes from and what it affects. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:stage

- Control: Writing stage
- View: `settings`
- Declared host/test route: workspace-project.mjs ordered plan of writing stages (in-place guidance)
- Behaviour: Shows or hides the guidance for one writing stage, in place. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:save-defaults

- Control: Save future defaults
- View: `settings`
- Declared host/test route: workspace-project.mjs Settings, New conversation defaults, after Change future defaults is opened; issues POST /work/session-preferences with the chosen provider, model and effort; after a recorded save it says the values the owner recorded (or that they were already saved), after NOT_ADMITTED that the save was not recorded and the choices are kept, and with no known outcome it says so and reads the saved defaults again
- Behaviour: Saves the chosen provider, model and effort as the defaults for new conversations. The page says what the owner recorded, or that nothing was recorded and the choices are kept.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:category-models

- Control: Models & providers
- View: `settings`
- Declared host/test route: workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'
- Behaviour: Shows the providers and models the catalogue reports, and the model policy they follow.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:category-voice

- Control: Writing & voice
- View: `settings`
- Declared host/test route: workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'
- Behaviour: Shows the shared writing voice profile and lets you edit it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:category-architecture

- Control: Structural preferences
- View: `settings`
- Declared host/test route: workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'
- Behaviour: Shows saved structural-preference suggestions to compare.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:category-runtime

- Control: Runtime
- View: `settings`
- Declared host/test route: workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'
- Behaviour: Shows the runtime the app observed and the one it declares.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:category-storage

- Control: Storage & recovery
- View: `settings`
- Declared host/test route: workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'
- Behaviour: Shows what is stored and how it is recovered.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:refresh-providers

- Control: Refresh provider availability
- View: `settings`
- Declared host/test route: workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'
- Behaviour: Asks each configured provider whether it is available now, then shows what they report.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:model-policy-source

- Control: Model policy source
- View: `settings`
- Declared host/test route: workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'
- Behaviour: Shows where the model policy is declared.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:provider-models

- Control: Reported models and exact state
- View: `settings`
- Declared host/test route: workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'
- Behaviour: Shows the models this provider reports and its exact authentication state, as the catalogue gives them.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:refresh

- Control: Refresh settings
- View: `settings`
- Declared host/test route: workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Reads the project's settings and writing stages again; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:edit-writing

- Control: Edit writing settings
- View: `settings`
- Declared host/test route: workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Opens the writing-style editor for this project; nothing is saved until you save there.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:future-defaults

- Control: Change future defaults
- View: `settings`
- Declared host/test route: workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Shows the provider, model and effort new conversations start with, and lets you change them.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:identities

- Control: Engine and profile identities
- View: `settings`
- Declared host/test route: workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Shows the exact engine and profile identities this project's tools run under.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:inspect-history

- Control: Inspect project history
- View: `settings`
- Declared host/test route: workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Opens the project's history in the inspector; it only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:stage-use

- Control: Use in conversation
- View: `settings`
- Declared host/test route: workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Prepares a request in the conversation panel from this writing stage's guidance; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:stage-refresh

- Control: Refresh stage
- View: `settings`
- Declared host/test route: workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Reads this writing stage's guidance again; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:profile-identities

- Control: Exact profile identities and tool route
- View: `settings`
- Declared host/test route: workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Shows the exact profile identities and the tool route this stage uses.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:default-select

- Control: Default provider, model or effort
- View: `settings`
- Declared host/test route: workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Chooses the provider, model or effort new conversations start with; Save future defaults records them.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:storage

- Control: Storage and cleanup
- View: `settings`
- Declared host/test route: workspace-material.mjs the storage panel of project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Shows how much space the project uses and which empty session folders could be removed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:storage-measure

- Control: Re-measure storage
- View: `settings`
- Declared host/test route: workspace-material.mjs the storage panel of project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'
- Behaviour: Measures the project's stored files again; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:unverified-processes

- Control: Unverified process observations
- View: `settings`
- Declared host/test route: workspace-material.mjs Storage and cleanup in project Settings; tests/workspace_control_coverage.test.mjs 'settings/seeded'
- Behaviour: Lists the process ids the owner saw but could not verify as belonging to this project; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:cleanup-remove

- Control: Remove empty unused session folders
- View: `settings`
- Declared host/test route: workspace-material.mjs Storage and cleanup in project Settings; tests/workspace_control_coverage.test.mjs 'settings/seeded'
- Behaviour: Removes only the session folders the owner verified as empty and unused, after the confirmation box is ticked; it is off while the owner reports none or the cleanup unavailable.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:voice-profile

- Control: Global voice profile
- View: `settings`
- Declared host/test route: workspace-app.mjs, workspace-writing-style.mjs and profile-preferences.mjs App settings > Writing & voice, Structural preferences and Storage & recovery; tests/workspace_control_coverage.test.mjs 'settings/writing-voice', 'settings/storage-recovery*', 'settings/architecture'
- Behaviour: Chooses which shared voice profile file this page shows and edits; it does not change the voice profile any project selects.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:storage-project

- Control: Open project storage and recovery
- View: `settings`
- Declared host/test route: workspace-app.mjs, workspace-writing-style.mjs and profile-preferences.mjs App settings > Writing & voice, Structural preferences and Storage & recovery; tests/workspace_control_coverage.test.mjs 'settings/writing-voice', 'settings/storage-recovery*', 'settings/architecture'
- Behaviour: Opens the Settings of the project you came from, where its storage and recovery are shown; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### settings:storage-choose

- Control: Choose a project to inspect its saved data
- View: `settings`
- Declared host/test route: workspace-app.mjs, workspace-writing-style.mjs and profile-preferences.mjs App settings > Writing & voice, Structural preferences and Storage & recovery; tests/workspace_control_coverage.test.mjs 'settings/writing-voice', 'settings/storage-recovery*', 'settings/architecture'
- Behaviour: Opens the Projects page so you can choose a project whose saved data to inspect; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
