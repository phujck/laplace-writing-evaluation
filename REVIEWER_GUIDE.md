# Evaluation route

Start with [README.md](README.md). It gives the paper reading order and the clean foreground-server setup. Use only this repository and a fresh environment for a portability exercise; record the actual interpreter and import origins.

A useful first application check is to open all four projects, read their source and PDFs, and inspect the research/figure records supplied with the scientific support. Create a disposable project for editing, proposal or recovery exercises, preserving the supplied manuscripts.

For a bounded model-free owner/HTTP test, install `.[review]` in the fresh environment and run:

```sh
.venv/bin/python -m pytest tests/test_writing_portable_core.py -q
```

It creates synthetic workspaces and exercises real source/proposal/Work owners and the foreground server. Its own docstring describes the controls. This command is a reproducible test route, not a claimed result until executed on the selected bytes. The `tests/` selection is an evaluator subset; it is not the complete upstream monorepo test closure and `pytest tests` is not advertised as a qualified whole-suite command.

The [scientific support index](release/scientific-support.json) identifies pinned numerical inputs, result files, method code and visual provenance. Read methods and cohort definitions before comparing scores. Historical model calls are not rerun at startup. Raw third-party benchmark corpora and credentials are not included or relicensed.

The controlled Dynamic Memory update fixture is small and model-free. On Linux or macOS, from this repository:

```sh
.venv/bin/python writing_projects/memory-in-pieces/evidence/DYNAMIC_MEMORY_DEMO_2026-11-11/incremental_demo_checked.py --mode smoke --args-json '{}' --result /tmp/dynamic-memory-demo.json
```

It reads bundled synthetic weighted-source documents and compares incremental edits with exact rebuilding/oracle checks. It uses POSIX `resource` limits; this particular script is not a Windows parity claim. Its scope is the stated finite fixture, not general text-retrieval performance. Keep new outputs separate from the preserved historical results.
