"""The shared core: mechanisms every owner uses and no domain decides.

  identity     content and canonical-JSON digests, revision matching and the schema-version gate
  receipts     owned-effect receipts: what an owner wrote, as before/intended/observed byte identities
  scoped       scoped progress: what an effect consumes, what it consulted, typed local obligations, grades
  json_record  bounded pinned reading of one JSON value by RFC 6901 pointer from bytes a reader admitted
  bodies       public body references: contract, canonical codec, retention, bounded reads, resolution, read budget
  perimeter    which repository paths may be cited as public evidence
  checkout     one resolver per qualified root: source tree, package resources, serving checkout, state home
  runtime      the declared runtime selection, stdlib-only, loaded by the launcher before Laplace is importable
  process      manifest one-liners rendered and run for one directory, and the default-off watchdog
  versioning   path-scoped Dulwich versioning with a guarded read-only git log fast path
  records      durable records (journal, rows, captured logs, lineage): see records/__init__.py

Core modules import nothing from domains or adapters and have no import-time effects. Domain owners
(writing, Work, research, pipeline) and adapters (native, HTTP, CLI, desktop) qualify them; the system
description (laplace.system) records which subsystem owns what.
"""
