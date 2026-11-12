# Concrete case routes

Execution evidence is written only by an actual run. The names below are expected output coordinates, not pre-existing success claims. Every case currently awaits the coordinator's isolated candidate execution receipt.

## core

Run `--groups core`. Open **Behaviour example** in the generated workspace, then Tasks -> WORK-example and Materials -> examples/README.md. The source entry is sources/behaviour-example/main.tex, with S1.tex included. Inspect evidence/core-project-import.json, core-work-read.json, core-artifact-read.json and core-work-stale-guard.json. Owners: projects.library, work.project_work, research.corpus_ingest, pipeline.authoring and sdk.describe. Setup is scoped from tests/test_writing_portable_core.py but copies none of its banked synthetic provider history. Artifact guards follow tests/test_writing_artifacts.py.

## reader

Run `--groups core,reader`. Open Reader plan -> Setting. Inspect the exact heading binding, section transition and stable paragraph item in evidence/reader-final-detail.json. The case records a native six-key request and the human HTTP adapter for the same guarded owner. Evidence: reader-native-contract.json, reader-http-adapter.json, reader-stale-transition.json. Source: manuscript.project_structure, native.verbs and web.project_work_surface. Verification basis: tests/test_reader_plan_owner.py. No UI rendering or reader-review judgement is inferred.

## research

Run `--groups core,research`. Open Research and Materials. Read the exact producer, CSV, run logs, result bytes and two distinct result records. evidence/research-terminal-run.json and research-current-terminal-run.json retain actual terminal states. research-currentness.json and research-stale-currentness.json compare the old run before and after an owner-custodied producer edit. With existing matplotlib, sequence-plot is created, rendered and placed by the actual visual owners. Verification basis: the deterministic producer and visual algorithms in tests/test_reader_plan_owner.py. These sums are workflow fixtures, not new scientific evidence.

## literature

Run `--groups core,reader,literature`. Open Research -> Literature, AuthoredSequenceExample, then its exact original and the def:sequence claim relation. evidence/literature-read.json holds the actual reading receipt, literature-bind.json the exact claim revision and locator, and literature-stale-claim.json the refusal. Source: research.literature and literature_support. Algorithms are scoped from tests/test_literature_joined_workflow.py. The document explicitly declares itself synthetic. It is not a published paper or verified DOI.

## source

Run `--groups core,source`. Open Writing -> S1.tex and Changes/history. The example deletes one exact authored atomic equation while refusing an ordinary paragraph, follows its owner-issued structural inverse, applies that inverse and reopens source. evidence/source-delete.json, source-inverse-read.json, source-undo.json and source-reopen.json retain the real chain. Source: manuscript.blocks and work.history. Verification basis: the no-turn owner calls in tests/test_native_structural_inverse.py. Browser Manual Undo is a separate coordinator proof.

## http

Run `--groups core,http`. The existing loopback server opens the generated project and frontend asset, reads the source owner's current Save handle, saves, refuses a stale overwrite, reopens and restores through a new exact Save. It also exercises the real Work HTTP guard. Inspect evidence/http-server.log, http-source-save.json, http-source-stale-refusal.json and http-source-reopen.json. Source: web.writing_server, manuscript.projection_viewer and web.project_work_surface. Transport setup is scoped from tests/test_writing_portable_core.py. Actual browser keyboard/lifecycle observation remains separate.

## atlas

Run `--groups atlas`. Read workspace/atlas-example independently of Laplace. Good content-addressed blobs and hives remain intact beside deliberately corrupted control stores. A real Atlas event chain declares an authored input object, reopens cold, removes only the disposable projection and reconstructs it from retained ledger/hives. The snapshot returns exact span bytes and refuses sealed, missing and corrupted inputs. Evidence: atlas-events.json, atlas-query.json, atlas-history.json, atlas-snapshot.json, atlas-span.json and refusal records. Source: atlas.store, history, state, snapshot and schema. Scoped algorithms: atlas/tests/test_store.py, test_store_projection.py and test_snapshot.py. Exact object lookup/event replay is not spectral semantic reconstruction coverage.

## atlas-cuda

Run `--groups atlas_cuda` only in an explicitly selected existing local CUDA environment. The shipped toy owner reads its clearly synthetic fixture, builds actual rows and rejects a planted unsupported surface. Evidence: group-atlas_cuda.json. Owner prerequisite absence remains UNAVAILABLE_OPTIONAL. Verification basis: atlas/tests/test_record_toy_fixture.py. No private corpus or model transcript is read.

## manual-undo-save-reopen

Coordinator-owned real browser case. On the generated toy project: open Writing, change the selected paragraph, use the actual Manual Undo control, Save, leave and reopen. Retain before/edited/undone/saved/reopened source pins, exact application/history receipts and visible browser captures. Reload/reopen must not resurrect a parked edit. The source and HTTP cases above supply useful records but cannot satisfy this UI obligation.

## full-document-equivalence

Coordinator-owned full selected-document case. Read every selected TeX input, bibliography, local class/style/template and macro dependency. Compare the same source closure through source reader, editable projection and actual built PDF, including equations, figures, citations, headings and template macros. A fixture result cannot qualify the complete selected documents. Record each unsupported construct or mismatch with exact file/span, consumed pins and visible output. Apply no template without the owner-issued candidate and reviewed preview identities.
