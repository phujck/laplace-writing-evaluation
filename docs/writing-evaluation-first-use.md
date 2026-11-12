# First use of the evaluation checkout

Use [the root README](../README.md) to install the two local packages and start the foreground browser server. Reading the supplied PDFs needs neither installation nor a model account.

## Read and explore

1. Open `/project?workspace=writing&app=projects` on your chosen loopback port.
2. Choose a paper, then **Writing**. **PDF** opens its typeset document; **TeX** opens the editable source and file selector.
3. Use **Research → Open the evidence** for the selected project's registered results. The [scientific evidence guide](evaluation-scientific-evidence.md) connects the broader shared result, method and figure files.

The final supplied PDFs have 40 pages (Eigen), 21 (Dynamic Memory), 21 (Self-Consistent Loss Geometries) and 10 (Hierarchy in sampled collective feedback). Their [canonical build records](../release/paper-builds.json) pin the completed common editorial pass. Reference-numbering `.aux` and `.bbl` files are included for the source reader. The typeset PDF remains the full mathematical reading surface; some TeX commands can remain literal in the source projection.

The app may describe a supplied PDF's local build basis as unverified until a build is recorded in your own checkout. The supplied PDF still opens; the original canonical build observation is separately preserved in the release records. A new build requires a suitable TeX installation.

## Make a disposable editing project

Choose **Projects → Create a project → Article**, enter a title and purpose, then **Create project**. Open **Writing**, click the starter paragraph and add a sentence. Check **Unsaved changes**, choose **Save changes**, and wait for **Saved**. Reopen the project and inspect the saved text; **TeX → chapter-01.tex** supplies a direct source inspection and recovery route.

Project creation and saving write the registry, project manuscript/history and local records in this checkout. `.laplace-state` holds runtime state; it is not the only place where user work lives. Keep the checkout and drafts when retaining an evaluation session.

The initial clean-session exercise saved and recovered text successfully through TeX, but observed a blank Write frame after reload. Its [historical report](../release/validation/first-use-baseline.txt) preserves that finding; final repair and retest status will be recorded separately before the release is frozen.

## Run the small example

The [reviewer guide](../REVIEWER_GUIDE.md) gives the model-free Dynamic Memory update fixture and two portable core tests. The README places new fixture output under `work/`, separate from retained evidence. The fixture checks nine states and sixteen queries against exact rebuilding/oracle calculations using bundled synthetic documents. Its POSIX resource limits do not establish Windows execution parity.

The clean baseline install exercised the fixture successfully and passed the two portable core tests, both from cloned source and with installed-wheel imports. [Clean-install results](../release/validation/clean-install-baseline.json) record that exact tested cut. No provider calls or scientific benchmark sweeps were part of those tests.

## Inspect retained results

Original run indexes, jobs, results and receipts travel with narrow [portability aliases](../writing-portability.json), preserving their bytes while resolving selected historical coordinates inside this checkout. The actual [owner readback](../release/run-owner-readback.json) distinguishes successful, failed and superseded runs; missing-result failures stay failed. The shared Loss Geometries records retain their original project locations, linked in the [evidence guide](evaluation-scientific-evidence.md).

The [selection checker](../scripts/check_evaluation_selection.py) verifies recorded file bytes. Keep its initial result before editing: creating a project or changing a pinned document legitimately changes the later comparison. Detailed older guides retain their stated historical release examples; this README and first-use route describe the selected checkout.
