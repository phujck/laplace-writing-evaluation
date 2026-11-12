# review: 44 declared controls

## Concrete case

Actual provider/proposal/application/HOLD/expanded-scope ACCEPT/synthesis/DONE

- App route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Supplied inputs/records: WORK-example, WS-23cab0222b494423948273b51de9e07b, PHASE-61747cdeb8bcb6d4b3f06e0c, PHASE-75f0760033cdaf1f56e477cb, PHASE-4a27c19da7afb99095e77c9d.
- Runnable command: `Open the concrete app route and supplied input/owner recipe below`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source and per-operation requests: [native recipes](native-operations.md).

## Execution standing

The named case has its own exact receipt or explicit prerequisite recipe. This page does not claim all review controls/states were exercised. Preserve unavailable/retained/refused dispositions; follow the live owner-issued actions in the actual demo.

## Exact registered controls

### review:responses

- Control: Request reviews / Review responses
- View: `review`
- Declared host/test route: workspace-review.mjs saved passage comment routing/results entry
- Behaviour: Opens the review route for this saved comment: Request reviews when none exists, Review responses when one does. Nothing is sent by opening it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:refresh

- Control: Refresh review
- View: `review`
- Declared host/test route: workspace-review.mjs Review and notes; tests/workspace_control_coverage.test.mjs 'review/pending'
- Behaviour: Reads the proposals and notes again; it changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:commission

- Control: Commission a review
- View: `review`
- Declared host/test route: workspace-review.mjs Review and notes; tests/workspace_control_coverage.test.mjs 'review/pending'
- Behaviour: Prepares a message in the conversation panel asking for an independent review of the manuscript; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:filter

- Control: Review list
- View: `review`
- Declared host/test route: workspace-review.mjs Review and notes; tests/workspace_control_coverage.test.mjs 'review/pending'
- Behaviour: Switches the list to comments, notes, global notes, other notes, closed items, proposals or proposal versions; it reads the owner's list for that choice.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:response-close

- Control: Close response
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackReply, the box that reads one complete review response; tests/workspace_control_coverage.test.mjs 'review/response-*'
- Behaviour: Closes the box that shows one complete review response; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:response-continue

- Control: Continue reading response
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackReply, the box that reads one complete review response; tests/workspace_control_coverage.test.mjs 'review/response-*'
- Behaviour: Reads the next page of this saved review response from the owner's own continuation and adds it below; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:response-retry

- Control: Retry response read
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackReply, the box that reads one complete review response; tests/workspace_control_coverage.test.mjs 'review/response-*'
- Behaviour: Reads the page that failed again, from the owner; the text already shown is kept and nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:response-restart

- Control: Restart response read
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackReply, the box that reads one complete review response; tests/workspace_control_coverage.test.mjs 'review/response-*'
- Behaviour: Reads this saved review response again from its first page, as it is now; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:response-basis

- Control: Exact response basis
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackReply, the box that reads one complete review response; tests/workspace_control_coverage.test.mjs 'review/response-*'
- Behaviour: Shows which saved response this is, the revision it was read at and how many characters of it are shown; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-routing

- Control: Reviewers and limits
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Opens the choice of an existing review Work, its saved review settings and limits; opening reads the Work list from the owner, and the route preview of a Work chosen earlier, and changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-save

- Control: Save comment
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Saves your comment on this passage as written, with the original request kept if the owner's answer is lost; the dialog says what the owner recorded. When the chosen Work's saved review settings are automatic, this button reads Save comment and request reviews and also requests the reviews the owner's preview permits.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-send

- Control: Save and request reviews
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Saves your comment and requests the reviews you previewed in one explicit decision; nothing is requested without it. It is hidden when the Work's saved settings are automatic, because Save comment then requests the reviews.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-close

- Control: Close comment
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Closes the dialog; the comment you typed is kept as a draft for this passage (the dialog says so if it could not be kept) and nothing is saved by closing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-work

- Control: Existing review Work
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Chooses which existing Work the reviews of this comment belong to; choosing reads the owner's preview of that Work's review route and requests nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-more-work

- Control: More existing Work
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Reads the next page of Work from the owner's own continuation and adds it to the list; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-policy

- Control: Saved review settings
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Chooses between manual review settings and a saved set of review settings for this Work; choosing reads the owner's preview and saves nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-limit

- Control: Review limits
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Sets one limit for this comment's reviews: reviews allowed, connection attempts per review, time to start reviews or review time limit; it takes effect only through Preview reviews and a save.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-preview

- Control: Preview reviews
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Reads from the owner what reviews your settings would request for this Work, without requesting any.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-auto-save

- Control: Save automatic review settings
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Records your recipients and limits as the automatic review settings of this Work through the owner's policy action; it saves no comment.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-check

- Control: Check save
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Reads from the owner whether the save whose answer was lost was recorded; it sends and changes nothing.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-retry

- Control: Retry same save
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Sends the retained save again exactly as it was, after a check found no record of it; the owner's answer is shown beside it.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:comment-settle

- Control: Resolve uncertain save
- View: `review`
- Declared host/test route: feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'
- Behaviour: Asks the owner to settle the retained save as never admitted, keeping any comment already saved; the dialog says what the owner recorded.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:new-note

- Control: New project note
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Opens a box to write a note about the whole project; nothing is saved until you press Save note.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:note-save

- Control: Save note
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Saves the note, or the reply, through the history owner against the revision you reviewed; the page says what was recorded and keeps your text if it was not.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:note-cancel

- Control: Cancel
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Closes this note box and forgets its draft; nothing is saved.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:note-review-revision

- Control: Review current save revision
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Reads the project's present revision from the history owner and shows it beside the draft; nothing is saved.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:note-use-revision

- Control: Use reviewed revision for this draft
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Makes the revision you just reviewed the one this draft is saved against; nothing is saved yet.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-inspect

- Control: Inspect full record
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Reads this one note or comment from the history owner and shows it alone; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-open-passage

- Control: Open passage
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Opens the manuscript passage this note or comment is about, read exactly from the owner; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-address

- Control: Address with Eigen
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Prepares a message in the conversation panel asking Eigen to address this comment, with its passage; nothing is sent.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-resolve

- Control: Resolve
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Marks this comment resolved through the history owner, against the revision it was read at; the page says what was recorded.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-dismiss

- Control: Dismiss
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Marks this comment dismissed through the history owner, against the revision it was read at; the page says what was recorded.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-reply

- Control: Reply
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Opens a box to reply to this comment as a new note linked to it; nothing is saved until you press Save reply.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-reopen

- Control: Reopen
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Marks this resolved, dismissed or superseded comment open again through the history owner; its earlier history stays.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-reply-to

- Control: Reply to note
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Shows the earlier note this reply answers, read exactly from the owner; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-change

- Control: Review change in manuscript
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Opens the saved manuscript edit this record points to, with its changes shown; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:record-history

- Control: Status history
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Shows each status this record had, with when and by whom; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:more

- Control: More records
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Reads the next page of records from the history owner's own continuation; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:previous

- Control: Previous records
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Reads the page of records before this one; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:back

- Control: Back to review page
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Leaves the single record and returns to the review page where you were; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:retry

- Control: Retry this page
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Reads the review page again after a failed read; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:proposal-open

- Control: Review in manuscript
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Opens this proposed change in the manuscript with its changes shown; the choice is yours there.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:proposal-provenance

- Control: Provenance
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Shows where this proposal came from, its version and its recorded state; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

### review:proposal-more

- Control: Inspect more proposal candidates
- View: `review`
- Declared host/test route: workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'
- Behaviour: Reads the next page of proposal candidates from the proposal owner's own continuation; nothing is changed.
- Verification: find this exact `data-control` in its host, execute the named behaviour, retain its owner receipt or read result and visible outcome. A declared host or test name is not an executed check.

## Declaration basis

Help controls version `sha256:873630591a0c9b17eb48443f2370f00fd3edb25174dfda57f0cedd78ecdfa3e3`, exact action digest `sha256:fcf09f337f7f677d8c75c2b06a4b440c3d4b2e2dc78be9f828e8d2e655719f80`, read `READ-d393cb2e19aa413eb22fb82c296e51b5`. This is the observed authoring basis, not a promise that later candidate declarations have the same bytes. The runtime catalogue rereads and pins the installed generation. Owner: `src/laplace/native/declarations.py`. Frontend ownership is declared per control above.
