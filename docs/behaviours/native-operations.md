# Native operation recipes

Use the registered public project `behaviour-example`. Read current owner-issued forms/guards; retained IDs are inspection anchors, not authority to resume a provider. Each operation below has a concrete owner family, supplied input, source and verification route. Observed calls are distinguished from prerequisite recipes.

## apply-revision

- Example family: `source`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `apply_revision` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: TOOLFAIL-17fce2cf089e40f0a1052c40bcc91617, TOOLFAIL-d3dc307976e8474d9eb220b63398804c, ACTION-79c130a289a045d28dc3bc3294b886ec

## argument

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `argument` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## author-changes

- Example family: `source`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `author_changes` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json, examples/verification/manual-undo-save-reopen.json

## author-history

- Example family: `source`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `author_history` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-f0aa1d16530f4602ab7719d8c532c942, TOOLFAIL-85c3e9d596c34a9daec7a43069bd0e7f, READ-51cf9f017ad74a2e9a3d626482b2063e, READ-afbc7e1c33e549f8aa37441f28a431ed

## block-change

- Example family: `source`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `block_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-fdd6314a70144c089683d5e9ded46a76, ACTION-26070bba637c47b995fa1c0d30c6526c

## build

- Example family: `template-output`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Declared TeX toolchain for build/template preview; current retained PDF can be read without building.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `build` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-33ad9cb3a1234db8a056095b7bc07adf

## build-status

- Example family: `template-output`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Declared TeX toolchain for build/template preview; current retained PDF can be read without building.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `build_status` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-19f3a66ab7404510a18f05ae97dd995e

## chapter

- Example family: `template-output`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Declared TeX toolchain for build/template preview; current retained PDF can be read without building.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `chapter` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: behaviour-example supplied project/artifact inputs

## concept

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `concept` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-15d69d56ac774d3d9fc356331eb8ec28, READ-23d5660a06ac439bacd36b8d593111f8

## concept-change

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `concept_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## concept-history

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `concept_history` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## concept-tree

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `concept_tree` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## session-settings

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `session_settings` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-67c32647bdd54ea3ac3b79094140fbd9, READ-32b6795f9966444f87b698fb1a855f6e

## session-settings-change

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `session_settings_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: WORK-example, WS-23cab0222b494423948273b51de9e07b, PHASE-61747cdeb8bcb6d4b3f06e0c, PHASE-75f0760033cdaf1f56e477cb

## dispatch-plan

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `dispatch_plan` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: WORK-example, WS-23cab0222b494423948273b51de9e07b, PHASE-61747cdeb8bcb6d4b3f06e0c, PHASE-75f0760033cdaf1f56e477cb

## dispatch

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `dispatch` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: WORK-example, WS-23cab0222b494423948273b51de9e07b, PHASE-61747cdeb8bcb6d4b3f06e0c, PHASE-75f0760033cdaf1f56e477cb

## dispatch-launch

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `dispatch_launch` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: WORK-example, WS-23cab0222b494423948273b51de9e07b, PHASE-61747cdeb8bcb6d4b3f06e0c, PHASE-75f0760033cdaf1f56e477cb

## dispatch-continue

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `dispatch_continue` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: WORK-example, WS-23cab0222b494423948273b51de9e07b, PHASE-61747cdeb8bcb6d4b3f06e0c, PHASE-75f0760033cdaf1f56e477cb

## dispatch-status

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `dispatch_status` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: WORK-example, WS-23cab0222b494423948273b51de9e07b, PHASE-61747cdeb8bcb6d4b3f06e0c, PHASE-75f0760033cdaf1f56e477cb

## dispatch-returns

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `dispatch_returns` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: WORK-example, WS-23cab0222b494423948273b51de9e07b, PHASE-61747cdeb8bcb6d4b3f06e0c, PHASE-75f0760033cdaf1f56e477cb

## conversation-history

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `conversation_history` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-89d1b79d3c3c4ab1bdb70dee04ad222d

## document

- Example family: `template-output`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Declared TeX toolchain for build/template preview; current retained PDF can be read without building.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `document` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-3e3552465ffc491991d1c767170b72e6, READ-cb3f865b78e849518746d8ba51256ca4, READ-9633d188c435404d82e8879b689cb7be

## experiment-run

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `experiment_run` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-bdd714422a0549e19c7fea584d72450b, ACTION-5651c07202ec4934b4f38f809b342b7e, ACTION-0b270751b06e4a8d97245ba1c2c078da

## export-pdf

- Example family: `template-output`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Declared TeX toolchain for build/template preview; current retained PDF can be read without building.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `export_pdf` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: behaviour-example supplied project/artifact inputs

## framing

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `framing` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## help

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `help` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-2bacbc3903e440008dee6ae891b63b54, READ-4bf3879ed2ed46f086e00f9c6b4ca4cd, READ-15099a125a7e47a38c91bdd4cbff616a, READ-9b307d590cf445388d0e64fd6494a5e7

## literature-bind

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `literature_bind` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-7fd8cf893f034f2bac0a51c1660f052c

## literature-discover

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `literature_discover` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## literature-import

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `literature_import` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-b5fc7a754d2a49e4ba81d07941e3a6dd

## literature-lookup

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `literature_lookup` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## literature-scope

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `literature_scope` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-757619eab54c490fb14e5a040220ff01

## literature-uses

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `literature_uses` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-b223643e0fc54a25b6d1e1f4f9105b3c

## logical-plan

- Example family: `reader`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=reader-plan`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `logical_plan` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## logical-plan-change

- Example family: `reader`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=reader-plan`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `logical_plan_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## note

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `note` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-efedffdbf253439c9a311fcc47208652, ACTION-cdf65a5e42814e28b02fa8f53742509f

## note-status

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `note_status` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## pipeline

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `pipeline` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## project

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `project` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-0d7e6be88ea14550998f8cb8f579b56a, READ-3ffb4188f65a408a82a60b3eb259c6b8, READ-94cec17409174b1a908e936e5e25df0f, READ-2005b6024b0a4b2f9501fb0d2228f85c

## project-guidance

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `project_guidance` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: profiles/voice/public-demo-v1.md

## project-guidance-change

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `project_guidance_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: profiles/voice/public-demo-v1.md

## project-metadata

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `project_metadata` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## project-metadata-change

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `project_metadata_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## proof-check

- Example family: `formal`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Pinned Lean/Lake4.19.0 and genuine Lake-generated dependency manifest; see examples/formal/README.md. No proof PASS is inferred.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `proof_check` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: behaviour-example supplied project/artifact inputs

## proof-targets

- Example family: `formal`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Pinned Lean/Lake4.19.0 and genuine Lake-generated dependency manifest; see examples/formal/README.md. No proof PASS is inferred.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `proof_targets` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: behaviour-example supplied project/artifact inputs

## proofs

- Example family: `formal`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Pinned Lean/Lake4.19.0 and genuine Lake-generated dependency manifest; see examples/formal/README.md. No proof PASS is inferred.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `proofs` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: behaviour-example supplied project/artifact inputs

## proposal-supersede

- Example family: `source`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `proposal_supersede` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json, examples/verification/manual-undo-save-reopen.json

## propose-revision

- Example family: `source`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `propose_revision` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-41bd6e4cf5f84fe5b0c3cd3875ecc0c6, ACTION-e969c5d4553242e78c85d627e5365578, ACTION-562b0dbe279f4af6a3c874638fff3c95, ACTION-a845babd405e475682fad9d73be6b1a2

## read-artifact

- Example family: `material`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=material`.
- Prerequisites: A locally owned/authorised document; supplied authored original and parameter artifacts are safe examples.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `read_artifact` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-ce2a4cf91b364a83affdfbafa4f353e9, READ-973f54819a2744899e9e28cdefdda9e8, READ-3b76fa1ee32e472cb1d426e2e75b4d83, READ-0e51b6691a774b569d993253cf808448

## reference

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `reference` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## reference-attach

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `reference_attach` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## reference-fetch

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `reference_fetch` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## reference-refresh

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `reference_refresh` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## reference-source

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `reference_source` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-dd26ea8d83284d969b289a3768ee3e59

## reference-text

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `reference_text` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-d975f1fac7c747ad9caf65574effedb6

## reference-update

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `reference_update` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## references

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `references` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## references-attached

- Example family: `literature`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `references_attached` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## repository

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `repository` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-a64f87a3ea3b43bcae3338f3ec3604ac, READ-1642604661664728b01ca8bd7e343294, READ-853af0c5f4de44f18db30cb1a49c8012, READ-1e205eacba0141b6aef3b6822770da34

## research

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `research` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-780fc76ff1644699afe78215422d718d, READ-7a37912b85384d26a5d74fe14526853c, READ-c76f365b20a5421b8132b4510dd8e056

## research-producer

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `research_producer` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-107c3728f4a540bea9c3cd43aec91695, TOOLFAIL-a41c941b76bd4b2babf7a3440abca96c, ACTION-3b39d4cea5f641289506500e6e35f65d

## research-reconcile

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `research_reconcile` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json, examples/verification/overview-public-control.json

## research-record

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `research_record` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-ffaed77095fc4d898ef44206c303d641, ACTION-0ef858ecebb341e98e3611c4be510425, ACTION-68385abf0f9441f1afdb0e195cbe0323

## run-cancel

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `run_cancel` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json, examples/verification/overview-public-control.json

## run-status

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `run_status` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-c20aa36137a64020811b4b48b23c3078, READ-e88de9815d314e42ab7ffcc74e1c54a8, READ-5577609ea792484087ab9b08011133b9, READ-6868d1630ef9409682f04a558721a532

## section-change

- Example family: `source`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `section_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json, examples/verification/manual-undo-save-reopen.json

## source

- Example family: `source`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=manuscript`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `source` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-8787879bf616489180535d1342857b01, READ-9b637f88d78b4c638b9b5ff3634dbdbb, READ-47a8ee0f5bb844f28d0e78abc6a39896, READ-362e55d756334f6fa6f078f0a7b387a6

## store-artifact

- Example family: `material`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=material`.
- Prerequisites: A locally owned/authorised document; supplied authored original and parameter artifacts are safe examples.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `store_artifact` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-fa7467bc2bf943c19042649bcde439fc, ACTION-545045c3cb9e4966bb23ebae455b97f2, ACTION-bf322c9e4f5142a6af38c6ff27edc88c, ACTION-47b29c4107544658be39169b78540a47

## structure

- Example family: `reader`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=reader-plan`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `structure` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-2c4b61f89fea443182cc39c4747a52f8, READ-1ceae054e3b042c2ab94818b3b156801, READ-82823cc9999e461e8ecf9d4af92d31d5, READ-5ff9d36bbb10430ab1e38375128891cc

## structure-change

- Example family: `reader`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=reader-plan`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `structure_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-8cff83f0b7a443f68b753aafd7ee9ae3, ACTION-cb29dcca9b3e44a39c0f09836447c298, ACTION-56f594e205a6492eb2308656db40ed77, ACTION-965f22c355704aac937edf5487f393d5

## style

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `style` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: profiles/voice/public-demo-v1.md

## task

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `task` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## work-review

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `work_review` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-82daf72e19304ee288799433d493c329, TOOLFAIL-38c4cf8d3fcf449aa5be4cb22f55e3fe, ACTION-aa50869801274dc692eed991a11afdc4, ACTION-0485cd18d85f4ce0bc79d546a452271c

## development-source

- Example family: `owned-source`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: New owned local Git repository, real Source grant and approved reviewer; provided sample_module.py/test_sample.py are runnable inputs.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `development_source` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: behaviour-example supplied project/artifact inputs

## workflow-definition-change

- Example family: `workflow-definition`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=workflows`.
- Prerequisites: Existing configured provider and explicit parent/role bindings to execute saved steps. The saved WDEF is inspectable without inference.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `workflow_definition_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: WDEF-6d272e5718bb4e1f87523767a13c95f4

## work-delivery

- Example family: `genuine-author-review`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Existing configured subscription only for NEW author/reviewer execution; retained real sessions open without inference. Never resume imported native authority.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `work_delivery` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-9ebbae6d04624f23894d07fe38a56a57, READ-8147d0d16ef248eaa557dc662fd760e3, READ-10791092379f4227aff903fbd5b69ec5, READ-24f5b27282484cb980a8d1843b3757d8

## task-status

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `task_status` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-1aacac8104ca40e6b8d3e3bd45dfbea7

## visual-create

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `visual_create` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-1335cd7a614842f09ec3d16029d42a2a

## visual-place

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `visual_place` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-e0bd4b163a13465898bb98e6d3e42d1f

## visual-render

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `visual_render` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-0b1ecab43f484e4fa2905e1fb8b4148a

## visuals

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `visuals` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json, examples/verification/overview-public-control.json

## writing-stage

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `writing_stage` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## writing-style

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `writing_style` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: READ-99e01a4c4b6b4c14988c89e713b8da28

## writing-style-calibration

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `writing_style_calibration` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: profiles/voice/public-demo-v1.md

## writing-style-change

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `writing_style_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: ACTION-5914669e723f44d093f86f45d717ceb0

## writing-style-profile-change

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `writing_style_profile_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: profiles/voice/public-demo-v1.md

## storage

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `storage` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## storage-prune

- Example family: `core`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=work`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `storage_prune` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json

## materials

- Example family: `material`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=material`.
- Prerequisites: A locally owned/authorised document; supplied authored original and parameter artifacts are safe examples.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `materials` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: behaviour-example supplied project/artifact inputs

## material-references

- Example family: `material`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=material`.
- Prerequisites: A locally owned/authorised document; supplied authored original and parameter artifacts are safe examples.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `material_references` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: behaviour-example supplied project/artifact inputs

## material-reference-change

- Example family: `material`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=material`.
- Prerequisites: A locally owned/authorised document; supplied authored original and parameter artifacts are safe examples.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `material_reference_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: behaviour-example supplied project/artifact inputs

## app-settings

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `app_settings` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: OBSERVED_OWNER_CALLS. Records: TOOLFAIL-985233e40671485598a80b95f517549c

## profile

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `profile` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: profiles/voice/public-demo-v1.md

## profile-change

- Example family: `preferences`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=settings`.
- Prerequisites: Use the fixture or a local copy; inspect current issued settings guards before changing them.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `profile_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: profiles/voice/public-demo-v1.md

## research-object-change

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `research_object_change` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json, examples/verification/overview-public-control.json

## research-handover

- Example family: `research`.
- Input: `behaviour-example`, `WORK-example`, selected `S1.tex`; related source/result/original handles come from the real example owner reads.
- Route: `/project?workspace=writing&corpus=behaviour-example&view=research`.
- Prerequisites: Installed local packages and the generated/public example project.
- Source: src/laplace/writing/operations.py
- Schema/next exact action: Help for `research_handover` in this project. Follow the issued request with its actual target/guard; do not manufacture a provider reply or approval.
- Observation: RUNNABLE_OWNER_OR_PREREQUISITE_RECIPE. Records: examples/verification/default-owner-suite.json, examples/verification/overview-public-control.json

