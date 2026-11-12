---
name: falsifiable_core
description: "[EXPERIMENTAL] A result may not lock as established until it passes the refusal test - an oracle the drafter cannot pre-answer, standing in front of a prediction written before the oracle is consulted, that the oracle could contradict. Confirmation is not discovery; seek the experiment the author would refuse."
---
# falsifiable_core

**Status: [EXPERIMENTAL]**

## Why this exists
Forged by the dreamer from a session where the engine ran the generative loop
backwards. With author = model there is no external oracle, so "ask, do not assert"
has nobody to ask and every result is answered from the drafter's own priors - the
conceptric then *records* a result already fixed rather than *generating* it. The
one result face that improved came from a numerical check that returned a number the
drafter had not placed by hand, and it improved the claim only because a prediction
was standing in front of it to be contradicted. This skill makes that the rule, not
the accident.

## The refusal test (the gate)
A result may not be marked `established` until it passes both clauses. Either clause
alone is inert.

1. **An oracle the drafter cannot pre-answer.** A computation whose output the drafter
   cannot reliably guess, a real measurement, a genuine literature fetch whose verdict
   can propagate, or the human. Re-deriving your own algebra with your own priors is
   not an oracle - it returns green and verifies nothing (the clean-room lesson). Rank
   the available oracles by un-simulability and use the strongest.
2. **A registered prediction the oracle could contradict.** Write the predicted
   outcome - a number, a sign, a scaling, a yes/no - into the result's machine map
   *before* consulting the oracle, and state what outcome would falsify the claim. If
   nothing could falsify it, the oracle is decoration and the result stays `partial`.

Record three things on the result: the prediction, the oracle's verdict, and whether
the verdict forced a change. **A verdict that merely confirms what was already written
does not promote the result to `established` - confirmation is not discovery.** Only a
prediction that survived a contradiction it could have failed earns `established`. A
prediction the oracle overturned re-opens the result, and that is the most valuable
outcome, not the worst.

## Seek the experiment the author would refuse
The highest-value oracle is the one whose result could fold the work - the test an
author = model will never volunteer because its answer threatens the thesis. Find it
and run it first. Refusing it to protect the write-up is the proceed-anyway path
wearing a humility costume. If the strongest oracle available for a result is one you
can pre-answer, say so in the ledger and hold the status at `partial`.

## Pairing
This is the gate [`result_foundry`](canon://skills/result_foundry) locks against and
the discipline [`reconciler`](canon://skills/reconciler) propagates - a re-opened
result must push its restriction upward, not be quietly relabelled.
[`clean_room_check`](canon://skills/clean_room_check) is a weak oracle by
construction: use it to catch process defects, never as the verification that earns
`established`.

## Invariants
- No `established` without a survived, falsifiable prediction against a
  non-pre-answerable oracle.
- Confirmation holds status at `partial`. Only a survived contradiction promotes.
- Name the oracle and the prediction in the ledger, or the result is a stub.
- Prefer the oracle that could fold the work. The experiment you least want to run is
  the one to run first.

*Experimental and coarse by design. Refine when a result teaches a sharper standard
for what counts as an oracle the drafter cannot pre-answer.*
