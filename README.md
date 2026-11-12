# Eigen — Writing and research evaluation

This repository combines the Laplace Writing application with four standalone scientific manuscripts and their editable figure/source inputs. Start with the overview, then follow the topic that interests you. Reading the papers and using the editor require no model account.

## Read the papers

1. [Eigen: Choosing What a Computation Must Retain](<writing_projects/eigen-technical-due-diligence-briefing/manuscript/working-draft/Eigen-A-Theory-of-Efficient-Representation-and-Its-Working-Prototypes.pdf>) — the general introduction, mathematical ideas, prototypes and software.
2. [Dynamic Memory](<synthetics papers/corpus-as-a-state/reconstruction/output/pdf/v2.1/skein.pdf>) — retained representations, reconstruction and task-dependent memory.
3. [Self-Consistent Loss Geometries and the Laws of Learning](<synthetics papers/self-consistent-loss-geometries-coupled-evaluators/manuscript/imported/main.pdf>) — learning dynamics and coupled evaluators.
4. [Hierarchy in sampled collective feedback](<synthetics papers/adaptive-normal-form/manuscript/tex/main.pdf>) — the hierarchy construction and its mathematical argument.

The corresponding `.tex` roots sit beside each PDF. [The selection manifest](release/selection-manifest.json) records copied bytes, source provenance and each declared local build input. The four papers include the completed common editorial pass. [Canonical build records](release/paper-builds.json) identify their exact final inputs and PDF/reference outputs.

## Run the application

Use Python 3.12. From this repository, create a fresh environment and install the two local packages:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install ./atlas .
.venv/bin/python -m laplace.web.writing_server --root . --host 127.0.0.1 --port 8772
```

Open <http://127.0.0.1:8772/project?workspace=writing&app=projects>. If port 8772 is in use, choose another unused loopback port and use the same number in the command and URL. Stop the foreground server with Ctrl-C. Runtime state defaults to `.laplace-state`; creating projects and saving edits also writes project files and the registry in this checkout. It does not start a model automatically.

On Windows PowerShell use `py -3.12 -m venv .venv` and replace `.venv/bin/python` with `.venv\Scripts\python.exe`.

Open one of the four titles, then choose **Writing**. **PDF** opens the supplied typeset document; **TeX** opens its editable source. For a safe editing exercise, use **Projects → Create a project → Article**, then edit that new project. Follow the [evaluation first-use route](docs/writing-evaluation-first-use.md) for expected states, the save/reopen journey and known limitations.

The [task recipes](docs/writing-tasks.md) explain the controls, and [source navigation](docs/writing-source-map.md) locates their implementation. The longer workspace, evaluator and container guides include historical host/release examples, excluded projects and acceptance records. Their project counts, account checks, desktop instructions and missing acceptance links are not results for this four-paper checkout; use this README and the [reviewer guide](REVIEWER_GUIDE.md) for the evaluation commands.

TeX builds need a local TeX distribution with `pdflatex`, `bibtex`/`biber` and the packages requested by each paper. PDF inspection uses Poppler. Numerical figure generation uses optional Python dependencies: `.venv/bin/python -m pip install '.[research]'`. Node is needed for JavaScript tests. These capabilities are separate from opening the app. Missing tools must remain visible as unavailable.

Model-assisted authoring is optional. Install and authenticate a supported provider CLI using your own existing account, then select its model in the app. No credentials, provider transcripts or local reader qualifications are distributed here. A local model action uses that account's quota; startup and ordinary reading perform no inference. See [account setup](docs/writing-account-setup.md).

## Inspect and reproduce

Check all selected source and derived-document pins without installing anything:

```sh
python3.12 scripts/check_evaluation_selection.py
```

Run the small model-free [Dynamic Memory update fixture](REVIEWER_GUIDE.md) on Linux or macOS:

```sh
mkdir -p work
.venv/bin/python writing_projects/memory-in-pieces/evidence/DYNAMIC_MEMORY_DEMO_2026-11-11/incremental_demo_checked.py --mode smoke --args-json '{}' --result work/dynamic-memory-demo.json
```

It checks nine states and sixteen queries over bundled synthetic documents. Its conditional values are `4/5 → 3/4 → 3/5 → 3/4`, followed by replay/merge/split checks, `0` and `UNDEFINED`. Successful local checks do not reproduce the historical language-model or GPU benchmarks. Keep the new output separate from the retained evidence.

- [Application code map](docs/writing-code-overview.md) and [owner/source map](docs/writing-source-map.md).
- [Research workspace](docs/writing-research-workbench.md) and [Work lifecycle](docs/writing-work-review-lifecycle.md).
- [How the four manuscripts were made](release/manuscript-production.json).
- [Scientific evidence and reproduction paths](docs/evaluation-scientific-evidence.md).
- [Release contents and exclusions](release/README.md).
- [Rights and third-party notices](RIGHTS.md).

This is a fresh repository without the author's Git history, private correspondence, private due-diligence edition, personal records, sessions, credentials or runtime caches. The selected manuscripts are scientific documents; the presence of a result or a test fixture does not claim an independent rerun of its experiments.
