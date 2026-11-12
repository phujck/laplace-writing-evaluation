---
name: latex_forge
description: The mechanical proofing engine. Use this skill to structurally lint and compile LaTeX manuscripts to enforce the house typesetting standards (REVTeX house format, Nature-style TikZ, layout integrity) before presenting drafts. Prose voice is not linted here - it is owned by the versioned voice profile at the final leg (2026-07-09 rebuild mandate).
---

# The LaTeX Forge [EXPERIMENTAL]

This skill enforces the mechanical typesetting axioms of the McCaul Protocol. It acts as a pre-compilation sieve to ensure no structural or visual defect survives to the Principal Investigator's desk.

It is the standard the manuscript form object's [Ring IV](canon://workflow/manuscript_projection.md) points at for the artefact's physical form: D-house-document-class (the house REVTeX4-2 / APS format, not plain `article`), D-house-typography-mechanics (Nature-style TikZ, keyword and layout integrity — linted here before a draft is presented), and D-forge-compiler (the Forge Compiler chain below, never raw `pdflatex`). The form demands the house mark; this node owns the detail of what the mark is. The voice-lint half of this skill was retired root-and-branch on 2026-07-09 (the rebuild mandate): prose register belongs to `profiles/voice/` at the final leg, never to a lint riding the generation path.

## Usage

When you finish a major rewrite of a `.tex` file, you must run the linting engine:

```
laplace_run(skill="latex_forge", target="<path_to_tex_file>")                  # report only
laplace_run(skill="latex_forge", target="<path_to_tex_file>", args=["--auto-fix"])
```

The engine runs the backing `scripts/build_and_lint.py`, which outputs a Markdown review of the file, flagging:
1. **TikZ Violations** (e.g., raw `red` or `blue` instead of `blue!80!black` or custom muted colors).
2. **TikZ Keyword Collisions** (e.g., using `output` as a style or node name, which is a reserved keyword in the TikZ `positioning` library and causes severe compilation crashes. Use `finalnode` instead).
3. **Layout Distortions** (e.g., using `\linewidth` for single-column figures inside full-page `\begin{figure*}` environments).
4. **Variable Inconsistencies** (e.g., default `x` or `z` labels in TikZ instead of manuscript variables like `\mathcal{M}` or `\theta`).

(The retired voice classes - Americanisms and slop vocabulary - are no longer part of this
skill's runbook. Their regex machinery remains in the backing script as dormant detector
material for the validation boundary, never as a generation-path lint.)

## Protocol
Do not fail the compilation aggressively. The engine will flag concerns "at a glance." You are expected to read the generated flags and address any structural failures before presenting the final PDF to the PI.

## Compilation 

**CRITICAL RULE:** Never compile manuscripts using raw `latexmk`, `pdflatex`, or `bibtex` commands in the terminal (see [Compilation and Release](canon://operations/compilation_and_release.md)). You must **STRICTLY** default to the Forge Compiler to eliminate manual friction and enforce standard compilation loops.

The Forge Compiler is the auxiliary `scripts/compile_pdf.py` in this skill (resolve its directory via `laplace_skill("latex_forge").backing_path`). Run it with the engine python from the repo root:

```
.venv/bin/python src/laplace/pipeline/canon/skills/latex_forge/scripts/compile_pdf.py <path_to_tex_file>
```
This single command automates the `pdflatex -> bibtex -> pdflatex -> pdflatex` chain and suppresses standard output unless an error occurs.

### Global Orchestration

If you are coordinating multiple subagents or require the entire SGO to be compiled simultaneously, use the Orchestration Compiler (`scripts/compile_orchestra.py`). It recursively finds all `main.tex` files in a target directory and compiles them concurrently:

```
.venv/bin/python src/laplace/pipeline/canon/skills/latex_forge/scripts/compile_orchestra.py <target_directory>
```
