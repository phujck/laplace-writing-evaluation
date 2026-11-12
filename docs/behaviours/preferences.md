# preferences: 4 declared controls

## Concrete case

Actual neutral writing-style selection and public app preference recipe

- App route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Supplied inputs/records: profiles/voice/public-demo-v1.md.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all preferences controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### preferences:refresh

- Control: Refresh preferences
- View: `settings`
- Declared host/test route: workspace-app.mjs, workspace-writing-style.mjs and profile-preferences.mjs App settings > Writing & voice, Structural preferences and Storage & recovery; tests/workspace_control_coverage.test.mjs 'settings/writing-voice', 'settings/storage-recovery*', 'settings/architecture'
- Behaviour: Reads the effective preferences and their saved suggestions again from the profile owner; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### preferences:read-effective

- Control: Read effective preferences
- View: `settings`
- Declared host/test route: workspace-app.mjs, workspace-writing-style.mjs and profile-preferences.mjs App settings > Writing & voice, Structural preferences and Storage & recovery; tests/workspace_control_coverage.test.mjs 'settings/writing-voice', 'settings/storage-recovery*', 'settings/architecture'
- Behaviour: Reads the complete effective preferences from the owner and shows them; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### preferences:generate

- Control: Generate suggestion
- View: `settings`
- Declared host/test route: workspace-app.mjs, workspace-writing-style.mjs and profile-preferences.mjs App settings > Writing & voice, Structural preferences and Storage & recovery; tests/workspace_control_coverage.test.mjs 'settings/writing-voice', 'settings/storage-recovery*', 'settings/architecture'
- Behaviour: Prepares a request in a conversation asking Eigen for a preference suggestion from your recent work; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### preferences:edit

- Control: Edit structural preferences
- View: `settings`
- Declared host/test route: workspace-app.mjs, workspace-writing-style.mjs and profile-preferences.mjs App settings > Writing & voice, Structural preferences and Storage & recovery; tests/workspace_control_coverage.test.mjs 'settings/writing-voice', 'settings/storage-recovery*', 'settings/architecture'
- Behaviour: Opens the structural preferences for editing against the revision read; nothing is saved until you preview and save.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
