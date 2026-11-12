# Eigen — Writing and research evaluation

This repository combines the Laplace Writing application with four standalone scientific manuscripts and their editable figure/source inputs. Start with the overview, then follow the topic that interests you. Reading the papers and using the editor require no model account.

## Read the papers

1. [Eigen: Choosing What a Computation Must Retain](<writing_projects/eigen-technical-due-diligence-briefing/manuscript/working-draft/Eigen-A-Theory-of-Efficient-Representation-and-Its-Working-Prototypes.pdf>) — the general introduction, mathematical ideas, prototypes and software.
2. [Dynamic Memory](<synthetics papers/corpus-as-a-state/reconstruction/output/pdf/v2.1/skein.pdf>) — retained representations, reconstruction and task-dependent memory.
3. [Self-Consistent Loss Geometries and the Laws of Learning](<synthetics papers/self-consistent-loss-geometries-coupled-evaluators/manuscript/imported/main.pdf>) — learning dynamics and coupled evaluators.
4. [Adaptive Normal Form](<synthetics papers/adaptive-normal-form/manuscript/tex/main.pdf>) — the hierarchy construction and its mathematical argument.

The corresponding `.tex` roots sit beside each PDF. [The selection manifest](release/selection-manifest.json) records copied bytes, source provenance and each declared local build input. The current papers are being given a final editorial pass; release acceptance identifies the final bytes.

## Run the application

Use Python 3.12. From this repository, create a fresh environment and install the two local packages:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install ./atlas .
.venv/bin/python -m laplace.web.writing_server --root . --host 127.0.0.1 --port 8772
```

Open <http://127.0.0.1:8772/project?workspace=writing>. Stop the foreground server with Ctrl-C. It stores local runtime state in `.laplace-state` in this checkout. It does not use the author's shared state or start a model automatically.

On Windows PowerShell use `py -3.12 -m venv .venv` and replace `.venv/bin/python` with `.venv\Scripts\python.exe`.

Open a paper from the project selector. Inspect its source, edit a disposable copy, and use the manuscript/research/reference views to explore the application. [Start here](docs/writing-start-here.md), [the workspace guide](docs/writing-workspace.md), and [source navigation](docs/writing-source-map.md) explain the existing controls. Some detailed guides retain historical release examples; the commands and selected papers on this page describe this repository.

TeX builds need a local TeX distribution with `pdflatex`, `bibtex`/`biber` and the packages requested by each paper. PDF inspection uses Poppler. Numerical figure generation uses optional Python dependencies: `pip install '.[research]'`. Node is needed for JavaScript tests. These capabilities are separate from opening the app. Missing tools must remain visible as unavailable.

Model-assisted authoring is optional. Install and authenticate a supported provider CLI using your own existing account, then select its model in the app. No credentials, provider transcripts or local reader qualifications are distributed here. A local model action uses that account's quota; startup and ordinary reading perform no inference. See [account setup](docs/writing-account-setup.md).

## Inspect and reproduce

Check all selected source and derived-document pins without installing anything:

```sh
python3.12 scripts/check_evaluation_selection.py
```

- [Application code map](docs/writing-code-overview.md) and [owner/source map](docs/writing-source-map.md).
- [Research workspace](docs/writing-research-workbench.md) and [Work lifecycle](docs/writing-work-review-lifecycle.md).
- [Release contents and exclusions](release/README.md).
- [Rights and third-party notices](RIGHTS.md).

This is a fresh repository without the author's Git history, private correspondence, private due-diligence edition, personal records, sessions, credentials or runtime caches. The selected manuscripts are scientific documents; the presence of a result or a test fixture does not claim an independent rerun of its experiments.
