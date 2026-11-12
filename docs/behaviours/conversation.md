# conversation: 12 declared controls

## Concrete case

Actual provider/proposal/application/HOLD/expanded-scope ACCEPT/synthesis/DONE

- App route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Supplied inputs/records: WORK-example, WS-23cab0222b494423948273b51de9e07b, PHASE-61747cdeb8bcb6d4b3f06e0c, PHASE-75f0760033cdaf1f56e477cb, PHASE-4a27c19da7afb99095e77c9d.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all conversation controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### conversation:toggle

- Control: Conversation
- View: `shell`
- Declared host/test route: workspace.mjs header [data-talk]
- Behaviour: Shows or hides the conversation panel beside the page. Nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:context

- Control: Inspect context
- View: `conversation`
- Declared host/test route: workspace-session.mjs context door [data-context-open] (C10)
- Behaviour: Shows what the next message will carry as context, as the owner reads it. It only reads.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:turn

- Control: Turn facets
- View: `conversation`
- Declared host/test route: workspace-session.mjs thread row chips (saved changes, failed attempts, reply standing)
- Behaviour: Shows or hides the facets of one turn: saved changes, failed attempts and the reply's standing. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:artifact

- Control: Saved artifacts
- View: `conversation`
- Declared host/test route: workspace-session.mjs relation rows of a turn's saved artifacts
- Behaviour: Shows or hides the artifacts one turn saved. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:target

- Control: Message target
- View: `conversation`
- Declared host/test route: workspace-session.mjs target chip row (target, attached reading, intent)
- Behaviour: Shows or hides what the next message is aimed at: its target, the reading attached and its intent. Nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:next-message

- Control: Model & settings
- View: `conversation`
- Declared host/test route: workspace-session.mjs selected-conversation next-message inspector; staged preferences and exact original request recovery
- Behaviour: Shows or hides the model, effort and other settings the next message will use, and recovery of an unconfirmed earlier request. Nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:add-document

- Control: Add local document
- View: `conversation`
- Declared host/test route: workspace-session.mjs conversation Context toolbar; shares the Material document form
- Behaviour: Opens the form for adding a local document from the conversation. No file is chosen or uploaded until the form is used.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:send

- Control: Send
- View: `conversation`
- Declared host/test route: workspace-session.mjs composer Send; with nothing typed it says 'Write a message first.' beside Send and sends nothing (workspace-sessions.mjs refuseEmptySend)
- Behaviour: Sends the message to the conversation. With nothing typed it says 'Write a message first.' and sends nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:reading-next

- Control: Continue reading
- View: `conversation`
- Declared host/test route: conversation-reading.mjs the reader of one saved message in the conversation panel; tests/workspace_control_coverage.test.mjs 'conversation/reading-*'
- Behaviour: Reads the next page of this saved message from the owner's own continuation and adds it below; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:reading-retry

- Control: Retry reading
- View: `conversation`
- Declared host/test route: conversation-reading.mjs the reader of one saved message in the conversation panel; tests/workspace_control_coverage.test.mjs 'conversation/reading-*'
- Behaviour: Reads the page that failed again, from the owner; the text already shown is kept and nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:reading-restart

- Control: Restart reading
- View: `conversation`
- Declared host/test route: conversation-reading.mjs the reader of one saved message in the conversation panel; tests/workspace_control_coverage.test.mjs 'conversation/reading-*'
- Behaviour: Reads this saved message again from its first page, as it is now; the text shown is replaced only when the read succeeds.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### conversation:reading-details

- Control: Message details
- View: `conversation`
- Declared host/test route: conversation-reading.mjs the reader of one saved message in the conversation panel; tests/workspace_control_coverage.test.mjs 'conversation/reading-*'
- Behaviour: Shows which saved message this is, the revision it was read at and how many characters of it are shown; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
