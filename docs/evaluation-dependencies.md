# Standalone source and dependency profiles

The distribution carries the complete Laplace/Atlas implementation families, build scripts, public operational resources, templates and test/helper source. [The application closure](../release/application-closure.json) enumerates those families and the explicit private-author-data exclusions. New files in a declared family are discovered by the exporter; an old selected list cannot silently omit them.

## Install the profile you will use

From a fresh Python 3.12 environment, the basic browser/editor install is:

```sh
.venv/bin/python -m pip install ./atlas .
```

For CPU research/figure, media, literature-client, browser-helper and evaluator dependencies:

```sh
.venv/bin/python -m pip install './atlas[records,bench,reconstruction]' '.[evaluation]'
```

Atlas record/tensor operations declare PyTorch explicitly; extraction also declares `regex` and `python-dateutil`. The fixture/example catalogue identifies which operations require a compatible CUDA device or optional kernels. Installing packages alone does not demonstrate those capabilities.

Embedding profiles are explicit: use `.[embed]` with `./atlas[encoders]` for the CPU FastEmbed path, or `.[gpu]` for the GPU FastEmbed/ONNX/CuPy path. Do not combine overlapping CPU and GPU distributions. Atlas additionally declares separate transformer-encoder, reconstruction-kernel and spectral extras. Choose hardware-compatible packages deliberately; no startup downloads models, installs device packages or calls a provider.

Playwright's Python package and its browser executable are separate. Browser-helper examples require an explicitly installed browser. Native GTK/WebKit uses OS packages (`python3-gi`, GTK 3 and WebKit2GTK 4.1 on the declared Linux profile); the foreground browser server needs none of them. TeX, BibTeX/Biber, Poppler, Graphviz and related renderer executables remain explicit system dependencies. The container recipe declares the CPU rendering tools; optional provider images require the user's own login.

## Bind managed commands to your local Python

After installing your chosen environment, explicitly configure this checkout:

```sh
.venv/bin/python scripts/configure_writing_runtime.py --python .venv/bin/python --replace
```

This records the actual interpreter and patch version in the local `runtime_profiles.toml`; it installs nothing. The shipped declaration has no author-home interpreter and is marked unconfigured until this step. It preserves the public artifact schema required by Source/publication imports. On POSIX, `scripts/laplace-python` then uses the same declared interpreter and this checkout's source. On Windows, the foreground server remains the portable entry; POSIX supervisor/launcher parity is not inferred.

The canonical Atlas toy fixture is [source data](../evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py). The Atlas build copies those exact bytes into its wheel, so installed ingestion does not depend on an author evidence directory.

## Replay the selected distribution

After updating and checking the explicit selection manifest:

```sh
.venv/bin/python scripts/export_writing_evaluation.py --repo-root . --destination ../evaluation-replay --curated-selection release/selection-manifest.json
```

The destination must be new. The exporter checks every selected pin, the complete declared application/resource family and the four papers' current owner-declared scientific dependencies before copying. It preserves original histories and scientific outcomes, and never crawls private author sessions to manufacture examples. Explicit private input exclusions stay recorded; public replacement producer declarations have distinct identities.
