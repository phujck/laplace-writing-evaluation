---
name: session_closer
description: "Close a session in two re-entrant tiers: a cheap idempotent CHECKPOINT (log skills, reconcile, rewrite the handoff - safe to re-run after trailing messages, processing only new evidence) and an infrequent evidence-gated STRUCTURAL DREAM (lifecycle transitions, forge, backlog work over a cumulative window), so session evidence compounds into canon fitness without a premature close orphaning the messages that follow it."
---
# session_closer

> **Earned name: Sawbones.** The index keeps `session_closer` for discovery, but the protocol earned a bedside name the session it was forged. The close is the suture - run so the session does not bleed out: nothing dropped, nothing stale, no evidence left to evaporate on the floor.

## Purpose
A session ends the same way every time, and the close was reconstructed from first principles each time it happened. An ad hoc close drops steps - most damagingly per-skill logging, which starves the fitness loop at the source. This skill makes the close a single named protocol any model in the loop follows identically.

But a close is not a clean cliff edge: **the author reliably sends a few more messages after they think the session is done.** A one-shot close that assesses, dreams, and stamps the boundary will orphan that trailing evidence past the window - the exact bug that wrongly deprecated a structural skill on a thin slice. So the close is **two re-entrant tiers**: a cheap checkpoint that is safe to run repeatedly, and a heavy structural dream that is gated and infrequent.

This skill is the host-facing counterpart to the END-OF-SESSION ROUTINE in `canon://agents/the_dreamer.yaml`.

**One ritual with the Eigen close.** For an Eigen session this skill is the *mechanical checkpoint* of
the close ritual whose human-facing sequence is `EIGEN_PROTOCOL.md` Part C (forks · retention · soul ·
Eigen's question · bank-trace · held-out prediction). They are the **same close**, not two competing
ones: Part C supplies the author-facing beats and the trace bank; this skill supplies the per-skill
`laplace_log`, the reconcile, and the handoff rewrite. `TECHNICAL_GUIDE.md` §6 holds the single
reconciled sequence as the source of truth; keep all three in step when any one changes.

## Who runs it, and when
- **The session-closer only** - whoever is wrapping the session (the orchestrator/principal), never a result-worker mid-ladder.
- **Tier 1 every time the work is set down**, and again after any trailing messages - it is idempotent.
- **Tier 2 occasionally** - on an explicit "structurally close / dream this" intent, or when enough cumulative evidence has built since the last structural dream. Not on every checkpoint.

## Tier 1 - Checkpoint (cheap, idempotent, run freely)
Processes only the telemetry since the last checkpoint marker, so re-running it after trailing messages just folds in the new slice. It **never deprecates and never advances the structural-dream boundary.**
1. **Settle and commit.** Stage only the finished artifacts of the element being closed; one scoped commit, the project's existing convention. Follow [git mechanics](canon://operations/git_mechanics): the engine's own git layer is `src/laplace/core/versioning.py` (pure-python, path-scoped stage/commit/revert), never leave conflict markers or a half-staged tree behind a checkpoint, and clear a stuck merge/rebase/revert state with the matching `--abort` before staging anything.
2. **Log every skill used - honestly.** For each skill whose protocol was actually followed since the last checkpoint, call `laplace_log` with +1 if following it produced a verify-passing result, -1 if it caused friction. Tie each signal to the artifact it produced. Self-log behavioural +1s for verify-passing usage - the author under-vocalises praise, so silence must not read as failure (the "silence is not dissatisfaction" backstop, also enforced structurally in `assess`).
3. **Reconcile, then let the handoff render last.** Run the [`reconciler`](canon://skills/reconciler.md) pass on the active project: classify what changed (lateral / downward / upward), apply lateral changes to the ledgers, and queue structural follow-ons (see [core-outward trunk](canon://workflow/core_outward_trunk.md)).
   - **The handoff is a render, not a hand-written file.** `scripts/sewup.py` step `handoff` (`src/laplace/engine/handoff_render.py`) writes both the dated `SESSION_HANDOFF_<date>_<topic>.md` and `HANDOFF.md` from the rows this session moved, each rendered line carrying its row source. Do not hand-rewrite either file: the closer's only written contribution is the authored slot the render carries forward verbatim, and anything typed over the rendered body is lost at the next close. If a fact belongs in the handoff and no row carries it, the fix is the missing row, not a paragraph.
   - **`HANDOFF.md` is still the single live entry point** - the one file a fresh session reads when told to "read the handoff" - and the render keeps it current: the dated record linked, the outstanding top-level goals carried, settled decisions marked done. Read it back after the render rather than editing it.
4. **Sync external state.** Bring any out-of-canon record current - auto-memory, project index, dashboards, and the shared literature corpus (a [`corpus_librarian`](canon://skills/corpus_librarian.md) provenance-update for the citekeys this session drew on). The **canon project node** holds only durable facts and delegates per-result status to the `HANDOFF.md` - confirm it still points to the handoff rather than restating a specific active result.

## Tier 2 - Structural dream (heavy, evidence-gated, revertible)
The lifecycle + forge pass. Run it deliberately, not on every checkpoint.
1. **Assess over the cumulative window.** Call `laplace_assess`. Judge lifecycle on accumulated evidence, not a thin recency slice - a rail that turns over once per project-stage must be judged on a project-lifetime window, not a since-last-dream cut.
2. **Dream.** Call `laplace_dream`. Apply deterministic curation. A structural skill (one the global workflow nodes or a core skill reference) is never deprecated on silence - only on a genuine negative outcome (`assess` enforces this). Forge only against friction that genuinely recurred. Any forge brief is `host_forge` - execute it inline and locally, never via an external API.
3. **Work the backlog.** `src/laplace/engine/AUTONOMY_BACKLOG.md` is the self-improvement queue. The dream surfaces its headers; when running with structural intent, take the highest-impact item or a flagged refine, do it, and record what was cleared. This is where evolutionary self-improvement actually happens - bounded, revertible, one commit each.

## Invariants
- **Tier 1 is idempotent and never deprecates.** Re-running it after trailing messages is safe and folds in only new evidence. It must not stamp the structural boundary.
- **Tier 2 is gated and cumulative.** It runs occasionally, judges on accumulated evidence, and never deprecates a structural skill on silence.
- **Logging precedes any dream.** A dream over an unlogged window dreams over nothing.
- **The closer closes.** A result-worker mid-ladder does not run this. Role boundary before sequence.
- **Forge briefs execute inline.** The engine is self-contained; the host drafts and persists. No external LLM call.
- **The handoff renders last, every checkpoint, and `HANDOFF.md` is the single live entry point.** If the render did not run, the checkpoint is incomplete. The failure mode is no longer a stale root file but an unmoved row: a close whose handoff reads thin has rows missing, not prose missing.

## Backing
The deterministic backing exists in two pieces.

- `scripts/close_checklist.py` - the advisory close-out reporter, with a FAIL-eligible aging-teeth gate: it reads the session's evidence and reports what the close still owes.
- `scripts/sewup.py` - the mechanical close itself, run as an ordered step list (`render`, `suite`, `canon`, `reembed`, `contracts`, `probes`, `threads`, `battery`, `poolfold`, `wants`, `bequest`, `handoff`).

The judgement - which skills were genuinely used, what each earned, when to run Tier 2 - stays with the closer.
