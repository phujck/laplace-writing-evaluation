# Read a saved conversation

Open **Conversation**, choose **Conversations**, and select a saved conversation.
The selected conversation keeps one reading surface for your saved requests and
the displayed public replies. Close the library with **Return to reading**.
Reading does not send a message, resume a provider or alter your composer draft.

Short messages appear in place. A long message offers **Continue reading**;
choose it until the remaining-message notice disappears. Each explicit read
appends the next contiguous page under the same exact basis. The complete saved
reply is then rendered as Markdown. Partial replies remain text so an unfinished
Markdown fragment does not hide what has actually been read.

**Message details** shows the selected project, conversation, turn, part, basis
and exact character/byte extent. It is optional. **Audit saved turn** opens the
separate retained actions, errors and source-edit receipts; it is not required
to read the public response. Downloading that exact saved turn is also an audit
action. Neither view includes private model reasoning or a provider transcript.

If a read fails, the prior text stays visible. **Retry reading** repeats the
failed read. If the owner reports a changed basis, **Restart reading** explicitly
begins a current observation instead of mixing new words with the earlier pages.
An absent saved reply means **No saved reply yet**, not a completed empty answer.
A genuinely saved empty message is reported separately. Live streamed text can
remain visible while its saved reply is not yet available.

Switching conversations and returning preserves the selected reading and unsent
draft. Reload recovery retains the message identity, basis and reading extent;
it rereads the words through their owner rather than storing a second message
body in the browser. These are saved-public-message observations, not a promise
that a provider is running or that all model context has been inspected.

## Exact agent, HTTP and SDK reads

The existing `conversation_history` operation accepts `view: "message"` for the
actual caller's logical conversation. Ask its current help first, then use the
qualified owner handles. A first native read has this shape, with actual issued
identities substituted:

```json
{"operation":"conversation_history","payload":{"view":"message","session_id":"WS-…","turn_id":"WT-…","part":"reply","offset":0,"limit":4000}}
```

The native caller supplies project authority; do not add a top-level `project`
or use this route to read another conversation. The selected `part` is `request`
or `reply`. A child-control permission does not widen this message-read scope.

The corresponding human-owned HTTP read is:

```text
GET /authoring/session-turn?project=PROJECT&session_id=WS&id=WT&view=message&part=reply
```

The installed SDK delegates to the same owner:

```python
from laplace import sdk

page = sdk.conversation_message({
    "project": "public-project", "session_id": "WS-…", "turn_id": "WT-…",
    "part": "reply", "offset": 0, "limit": 4000,
}, root="/absolute/selected/workspace")
```

These are identity templates, not executable receipts. Follow the returned
`page_read`, `next_read` and `restart_read` descriptors for the selected transport.
The SDK descriptor names `conversation_message` and its exact payload; the HTTP
descriptor uses `id`, while native/SDK payloads use `turn_id`.

Offsets and extents count Unicode scalar-value characters, not UTF-8 bytes.
Default page sizes are 2,000 request or 4,000 reply characters, with at most
40,000 per read. This bounds transport pages, not the complete saved message.
The basis qualifies project/session/turn/part, captured session/turn/source rows,
presentation policy and full displayed text. A content hash, source-row hash and
basis are different facts. Same/next handles carry `expected_basis`; a
`CHANGED_MESSAGE` refusal returns no replacement text and supplies a separate
explicit restart. Currentness is **current at that read**, not a permanent claim.

Only selected public text leaves are resolved for this route; it does not fold
the whole context or recursively open manuscript-edit bodies. Existing exact
turn audit routes remain available when their richer records are needed.
