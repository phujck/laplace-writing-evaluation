# Sensorium S0 provider face

Sensorium is a read-only, disposable conjugate projection of the one canonical
`ConceptricStore`. It consumes `atlas.conceptric-provider.v1` through
`atlas.seat-bridge.v1`; it owns no event, message, cursor, or projection store.
Every invocation verifies canonical history and folds the events through
`atlas.state.replay` before rendering.

Run either face with the system interpreter:

```sh
PYTHONPATH=src /usr/bin/python3 -m atlas.sensorium \
  --store /path/to/conceptric-store --format text

PYTHONPATH=src /usr/bin/python3 -m atlas.sensorium \
  --store /path/to/conceptric-store --format json
```

Both forms expose the same provider head, lifecycle transitions, logical seats,
provider session holders, content-addressed graph objects and typed edges,
assumption fibres and transports, reconstruction receipts, durable watcher
registrations/checkpoints, permission requests/decisions, residuals, and queued
jury work. Provider seat cursors and watcher checkpoint cursors are rendered as
canonical facts; Sensorium creates no cursor of its own.

Every message also has a joined causal face for send, pull, reconstruction,
acknowledgement, expiry, and decision stages. A separate completeness flag names
the full send→pull→reconstruction→ack chain without weakening the provider's
canonical delivery rule.

Delivery is fail-closed. Only the provider's `delivered` state joined to an
accepted acknowledgement, an extant reconstruction event, and acknowledgement
causation of both send and reconstruction renders delivered. Queued, pulled but
unacknowledged, refused, and expired work remains not delivered. Jury work cannot
render decided until it is delivered and a valid canonical `decision.recorded`
event causally follows the acknowledgement.

Watcher dispatch is explicitly not delivery. A fired checkpoint can prove that
a matched handle caused a message to be queued for a logical seat; only the
later reconstruction-bearing accepted acknowledgement can make that message
delivered. Queued, pulled-unacknowledged, refused, expired, and watcher-dispatched
but unacknowledged messages remain loud in the projection.

The former `atlas.sensorium.observation.v1` fixture adapter was retired during
the provider migration. It was never an authority or a store, and it is no
longer an importable alternate input protocol.
