# Laplace Python package

This directory contains the Writing App backend and the shared Laplace modules
it imports. Both travel in the Writing repository. Start with the
[code overview](../../docs/writing-code-overview.md) and use the
[detailed source map](../../docs/writing-source-map.md) for exact owners and tests.

## Main areas

Each subsystem of the [system description](system/description.json) is one package; the
[operational homes](../../docs/operational-homes.md) page says where source, runtime, state and caches live.

| Package | Subsystem | Responsibility |
|---|---|---|
| [core/](core/__init__.py) | core | Identity and revision digests, payload admission, the grammar and identity doors, owned-effect receipts, scoped progress, public body references, qualified roots and the declared runtime, durable records (journal, rows, captured logs, lineage) |
| [system/](system/__init__.py) | core | The system description, its check and the generated front door |
| [writing/](writing/README.md) | domain.authoring | Sessions and turns, providers and the operating brief, the operation table, delivery, reads and the Writing records |
| [manuscript/](manuscript/__init__.py) | domain.manuscript | Source text, structure, blocks, proposals and their application, versions, plans, builds, publication editions, the reader |
| [projects/](projects/__init__.py) | domain.projects | The project library, repository sources, storage, portability, artifacts and lifecycle |
| [work/](work/__init__.py) | domain.work | Work items, review, delivery, development-source grants and the current coordination entry, author feedback and history |
| [research/](research/__init__.py) | domain.research | Research records and runs, literature, references, concepts, visuals, formal and engineering support, corpus readers, SuperARC |
| [representation/](representation/__init__.py) | domain.representation | The Atlas bridges and watchers, embedding and GPU policy, Writing's body and representation seams (the library itself is [src/atlas](../atlas/)) |
| [pipeline/](pipeline/__init__.py) | domain.pipeline | The projection pipeline, registry, dials, canon (with its resources) and the writing organ |
| [engine/](engine/__init__.py) | domain.engine | Wake, reconstruction, telemetry, shards, the engine ledger and the self-description organs |
| [native/](native/__init__.py) | adapter.native | The project tool gateway (`tools`), declarations, declared rules, the verb route table, routing advisor, contract view |
| [web/](web/__init__.py) | adapter.http | The scanner and writing servers, served pages and [static assets](web/static_shared/README.md), the /authoring, /research and /review doors |
| [desktop/](desktop/__init__.py) | adapter.desktop | The managed writing app, native window, desktop front, offline launcher and deploy units |

## Entry points

`python -m laplace.web.writing_server` starts the portable foreground server;
`laplace.desktop.writing_app` owns the managed Linux desktop service and `laplace.desktop.native_writing` its window.
Both serve through `laplace.web.scanner`. The [startup guide](../../docs/writing-agent-start.md)
and [platform guide](../../docs/writing-browser-server.md) explain the supported routes. Engine modules such as
`laplace.engine.wake` serve explicit engine operations; their presence is not a portable app startup instruction.
Use the repository's [agent entry](../../AGENTS.md) to orient a repository session.

Atlas is the second local package at [src/atlas](../atlas/), beside this one (its distribution metadata stays in [atlas/](../../atlas/)).
Install it from this repository together with the main package; optional numerical
or provider capabilities follow their declared dependency profiles.
