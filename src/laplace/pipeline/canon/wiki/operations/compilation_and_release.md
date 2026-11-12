# Compilation and Release Pipeline

This pipeline is the compile/release half of what the manuscript form object's [Ring IV](canon://workflow/manuscript_projection.md) demands (D-house-document-class, D-forge-compiler): the form requires the artefact be projected in the house format and built through the Forge Compiler, and these axioms own the detail.

* **Automated Formatting & The Vonnegut Linter**: Do not rely purely on manual oversight to enforce the Vonnegut Rule or the 'Child Made It' rule. Always pass `.tex` files through the [`latex_forge`](canon://skills/latex_forge) linter (`build_and_lint.py`) to computationally eradicate semi-colons, em-dashes, Americanisms, and TikZ color/keyword violations (e.g., using `output` as a node style crashes TikZ positioning; use `finalnode` instead).
* **The Forge Compiler Axiom**: Never run raw `pdflatex`, `latexmk`, or `bibtex` in the terminal. You must strictly use the Forge Compiler (`latex_forge/scripts/compile_pdf.py` or `compile_orchestra.py`) for all compilations to guarantee standardized, frictionless builds. Ensure you handle PDF lock bypasses when compiling.
* **The Release CI/CD Axiom**: To eliminate PI QA friction, do not manually cobble together QA or deployments - run the full rigid pipeline (Swarm -> Epistemic Sync -> Compile -> Web Deploy) through a release orchestration rather than ad hoc. (The early `laplace_release_mechanic` / `web_deployment_mechanic` skills that named this pipeline are deprecated and unexercised; the discipline holds, the specific backing is being re-forged from real use.)

## Web decks (Slidev) - build mechanics

A web talk deck is a release artifact too. It builds with `slidev build`, and the published build must carry the correct asset base for its site path.

* **Check the published `--base` before shipping.** A deck built with the wrong asset base loads blank: every href points outside the site path. Build with the site base the deck will actually be served under, then verify one asset href in the built output rather than trusting the flag. (The MSYS/Git-Bash path-rewriting trap that made this rule and the Windows local-theme dev-server workaround were both dead-machine rules, retired 2026-08-21 with the shell-mechanic era under permanent-Linux PV-20260820T104500Z.) The applet/render harness is in [`deck_applet`](canon://skills/deck_applet); the per-slide render-and-look loop builds with `--base /` and is unaffected, the trap is only the site-base publish build.
* **Prefer build-and-shoot to a long-running dev server** in an agent loop - a persistent server is a flake/hang trap.
* **A Slidev/Vite SPA on GitHub Pages needs hash routing and a `.nojekyll`.** Two settings, both at publish time, sitting beside the `--base` above:
  - **`routerMode: hash`** in the deck config. A static host has no server-side rewrite, so the default history-mode deep link (`/talks/<name>/7`) 404s on a refresh or a shared slide URL - there is no `7` file to serve. Hash routing (`/talks/<name>/#/7`) keeps the route client-side, so a deep slide link survives a reload.
  - **A root `.nojekyll`** in the published build. Without it, GitHub Pages runs the output through Jekyll, which mangles the built SPA (it drops files and directories beginning with `_`, which Vite emits). The file makes Pages serve the build verbatim.
