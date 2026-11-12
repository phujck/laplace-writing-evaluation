# editor-frame: 38 declared controls

## Concrete case

Exact atomic source deletion/refusal/inverse/reopen

- App route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Supplied inputs/records: examples/verification/default-owner-suite.json, examples/verification/manual-undo-save-reopen.json.
- Runnable command: `.venv/bin/python -B -s examples/run_behaviours.py --package-root "$SITE" --output /absolute/NEW/example-run --groups core,source`.
- Prerequisites: Installed local packages; explicit generated/public demo workspace.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all editor-frame controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### editor-frame:zoom-out

- Control: Smaller text
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Makes the manuscript text in the editor smaller; the size is a view choice kept for this browser and nothing in the manuscript changes.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:zoom-in

- Control: Larger text
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Makes the manuscript text in the editor larger; the size is a view choice kept for this browser and nothing in the manuscript changes.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:questions

- Control: Questions & context
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Opens the questions and context the project holds for the passage you are reading; it reads from the owners and changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:find

- Control: Find
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Opens the Find and replace box over the manuscript text; finding reads the text on the page and changes nothing, and Replace next there edits and saves a passage.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:reading-options

- Control: Reading options
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Shows the reading choices of the editor: open points, text width, whether your changes are marked, and autosave; nothing is changed by opening it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:open-points

- Control: Open points
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Opens the open points the project's plan records; it reads from the owners and changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:width

- Control: Manuscript width
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Chooses how wide the manuscript text is drawn: fill the pane, wide text or reading width; a view choice kept for this browser.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:author-changes

- Control: Your changes
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Turns the marks that show your own edits and their revisions on or off in the text; a view choice kept for this browser and nothing in the manuscript changes.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:autosave

- Control: Autosave
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Turns autosave on or off in this browser; it is off until you turn it on. Off, your edits are saved only by Save changes in the editor band beside the Write, TeX and PDF buttons, which shows while Write edits are unsaved, or by Ctrl-S, and until then they are kept in the editor, also across a reload. On, the paragraph you are typing in is saved a short pause after you stop typing, that paragraph only, and never while its previous save is still out: words typed meanwhile are saved once that save answers; a paragraph another writer changed under your draft, or one the file no longer has, waits for Save changes, Ctrl-S or Keep my text and save it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:keep-my-text

- Control: Keep my text and save it
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Saves every paragraph you have typed in exactly as it stands in the editor: your text is written over that passage as the file holds it now, and a paragraph of yours the file no longer has is put back at its place as a paragraph of its own; any text it replaces is kept in the manuscript's change record. It is the first control beside every save warning on the frame's status line, and in the box above the manuscript that keeps a paragraph of yours the file no longer has.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:show-other-version

- Control: Show the other version
- View: `manuscript`
- Declared host/test route: writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'
- Behaviour: Opens a panel above the manuscript showing what the file holds now at the paragraph another writer changed while your draft was open; nothing is saved or changed, and your text stays in its paragraph until you save or discard it. It stands beside Keep my text and save it on the frame's status line while such a draft is open.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:bubble-comment

- Control: Comment
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the selection toolbar of the editor frame, shown when text is selected in the manuscript; tests/workspace_control_coverage.test.mjs 'manuscript/frame-bubble'
- Behaviour: Opens the comment dialog for the selected text, or says in the frame's status line why it cannot (for example unsaved manuscript edits are held); the dialog saves nothing until you press Save comment there, or Save comment and request reviews when the Work's saved settings are automatic.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:bubble-discuss

- Control: Discuss
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the selection toolbar of the editor frame, shown when text is selected in the manuscript; tests/workspace_control_coverage.test.mjs 'manuscript/frame-bubble'
- Behaviour: Prepares a message in the conversation panel about the selected text, to discuss it with the agent; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:bubble-revise

- Control: Revise
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the selection toolbar of the editor frame, shown when text is selected in the manuscript; tests/workspace_control_coverage.test.mjs 'manuscript/frame-bubble'
- Behaviour: Prepares a message in the conversation panel asking the agent to revise the selected text; nothing is sent and nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:bubble-reference

- Control: Reference
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the selection toolbar of the editor frame, shown when text is selected in the manuscript; tests/workspace_control_coverage.test.mjs 'manuscript/frame-bubble'
- Behaviour: Opens the choice of a label to insert as a reference at the selection; nothing is inserted until you choose one, and choosing one inserts it and saves the passage at once (when the exact-source box is open it inserts into that box instead, written by the box's Save changes, the editor band's Save changes or Ctrl-S).
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:bubble-citation

- Control: Citation
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the selection toolbar of the editor frame, shown when text is selected in the manuscript; tests/workspace_control_coverage.test.mjs 'manuscript/frame-bubble'
- Behaviour: Opens the choice of a source to insert as a citation at the selection; nothing is inserted until you choose one, and choosing one inserts it and saves the passage at once (when the exact-source box is open it inserts into that box instead, written by the box's Save changes, the editor band's Save changes or Ctrl-S).
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:bubble-queue

- Control: Queue request
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the selection toolbar of the editor frame, shown when text is selected in the manuscript; tests/workspace_control_coverage.test.mjs 'manuscript/frame-bubble'
- Behaviour: Opens a box to queue a written request about the selected text for later; nothing is queued until you press Queue request there.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-insert-reference

- Control: Insert reference…
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens the choice of a label to insert as a reference at the place you pressed; nothing is inserted until you choose one, and choosing one inserts it there and saves that passage at once. Only when you press the passage whose exact TeX source box is open, while text in that box is selected, does it insert into the box instead, written by that box's Save changes, Save changes in the editor band or Ctrl-S.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-insert-citation

- Control: Insert citation…
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens the choice of a source to insert as a citation at the place you pressed; nothing is inserted until you choose one, and choosing one inserts it there and saves that passage at once. Only when you press the passage whose exact TeX source box is open, while text in that box is selected, does it insert into the box instead, written by that box's Save changes, Save changes in the editor band or Ctrl-S.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-italic

- Control: Italic
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Wraps the selected text, or the word at the caret, in italics written as TeX in the passage, and refuses a selection that crosses an equation, citation or macro; the edit is saved by Save changes in the editor band, which shows while Write edits are unsaved, or by Ctrl-S, or a moment after you stop typing if you turned Autosave on.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-bold

- Control: Bold
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Wraps the selected text, or the word at the caret, in bold written as TeX in the passage, and refuses a selection that crosses an equation, citation or macro; the edit is saved by Save changes in the editor band, which shows while Write edits are unsaved, or by Ctrl-S, or a moment after you stop typing if you turned Autosave on.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-insert-heading

- Control: Insert heading…
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens a box for the title, level and position of a new heading beside this passage; nothing changes until you press Insert heading there, which saves your pending edits and then writes the heading to the source.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-paragraph-style

- Control: Paragraph style…
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens a box to turn this paragraph into a heading of the level you choose; nothing changes until you press Change paragraph style there, which saves your pending edits and then rewrites the paragraph as a heading in the source.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-queue-request

- Control: Queue a request…
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens a box to queue a written request about this passage for later; nothing is queued until you press Queue request there.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-delete-paragraph

- Control: Delete paragraph now
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Deletes this paragraph from the manuscript source at once, after asking who is editing if no one is named, and records the change; it does not wait for Autosave or Save changes, and a paragraph whose own save is still out is not deleted until that save answers.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-edit-passage

- Control: Edit this passage
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens this passage for typing in place; what you type is saved by Save changes in the editor band, which shows while Write edits are unsaved, or by Ctrl-S, or a moment after you stop typing if you turned Autosave on. A passage that cannot be typed in place (an equation, a heading with maths, or a passage shown as raw TeX) opens its exact TeX source box instead, which is written by three acts only: that box's Save changes, Save changes in the editor band (shown once the box's text is changed) or Ctrl-S while the box is open; Autosave never writes it. A passage held in an open proposed change is not opened: the frame's status line asks you to accept or reject the proposed change first.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-edit-source

- Control: Edit exact source
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Shows this passage as its exact TeX source in a box for editing in place, except a passage held in an open proposed change, which is not opened: the frame's status line asks you to accept or reject the proposed change first. The source is written by three acts only: that box's Save changes, Save changes in the editor band (shown once the text in the box is changed) or Ctrl-S while the box is open; Autosave never writes it, whatever it is set to, and the box's Cancel closes the box without saving.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-open-tex

- Control: Open in TeX
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens the TeX source of the file at this passage in the Writing TeX pane; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-questions

- Control: Questions & context
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens the questions and context the project holds for this passage; it reads from the owners and changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-section-concepts

- Control: Section concepts
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens the Reader plan item that covers this passage, or the Reader plan to choose one when none or several do; it reads from the owner and changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-discuss

- Control: Discuss this passage
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Prepares a message in the conversation panel about this passage, to discuss it with the agent; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:menu-comment

- Control: Comment on this passage
- View: `manuscript`
- Declared host/test route: writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'
- Behaviour: Opens the comment dialog for this passage, or says in the frame's status line why it cannot (for example unsaved manuscript edits are held); the owner inspects the passage first and nothing is saved until you press Save comment, or Save comment and request reviews when the Work's saved settings are automatic.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:queue-submit

- Control: Queue request
- View: `manuscript`
- Declared host/test route: writing-panel.mjs queueRequest, the box that Queue a request opens from the passage menu or the selection toolbar of the editor frame; tests/workspace_control_coverage.test.mjs 'manuscript/frame-queue'
- Behaviour: Queues what you typed as a request for the session about this passage, as a task the project records; nothing is queued until you press it and an empty request is not sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:queue-cancel

- Control: Cancel
- View: `manuscript`
- Declared host/test route: writing-panel.mjs queueRequest, the box that Queue a request opens from the passage menu or the selection toolbar of the editor frame; tests/workspace_control_coverage.test.mjs 'manuscript/frame-queue'
- Behaviour: Closes the box without queueing anything.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:find-next

- Control: Find next
- View: `manuscript`
- Declared host/test route: walk-card.mjs openFindDialog, the Find box that the editor frame's Find opens; tests/workspace_control_coverage.test.mjs 'manuscript/frame-find'
- Behaviour: Finds the next place in the manuscript that matches what you typed, closes the box and moves the reading there; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:find-replace

- Control: Replace next
- View: `manuscript`
- Declared host/test route: walk-card.mjs openFindDialog, the Find box that the editor frame's Find opens; tests/workspace_control_coverage.test.mjs 'manuscript/frame-find'
- Behaviour: Replaces the next match with your replacement text in the passage and saves that passage at once; it does not wait for Autosave or for Save changes in the editor band.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:find-close

- Control: Close
- View: `manuscript`
- Declared host/test route: walk-card.mjs openFindDialog, the Find box that the editor frame's Find opens; tests/workspace_control_coverage.test.mjs 'manuscript/frame-find'
- Behaviour: Closes the Find box; what you typed is kept for the next time you open it and nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### editor-frame:context-close

- Control: Close context
- View: `manuscript`
- Declared host/test route: writing-panel.mjs openPoints, the context pane that Questions & context and Open points open in the editor frame; tests/workspace_control_coverage.test.mjs 'manuscript/frame-context'
- Behaviour: Closes the questions and context pane and returns the reading position and selection you had; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
