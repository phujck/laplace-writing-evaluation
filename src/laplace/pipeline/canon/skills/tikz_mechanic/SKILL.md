---
name: tikz_mechanic
description: The structural safety layer for TikZ architectures. Catches and repairs invalid xcolor nesting and geometric opacity failures before they crash the LaTeX compilation.
---

# TikZ Mechanic

A static sanitiser for `tikzpicture` environments. Generated diagrams often carry nested `xcolor`
mixings the package cannot parse (`blue!80!black!5!white`), and an unparseable colour is a fatal
compile hang rather than a warning. (The visual conventions these properties implement are defined
in [TikZ Guidelines](canon://aesthetics/tikz_guidelines.md).)

## Usage

Run the sanitiser before compiling a newly generated or modified TikZ diagram, then compile via
[`latex_forge`](canon://skills/latex_forge):

```
.venv/bin/python src/laplace/pipeline/canon/skills/tikz_mechanic/scripts/sanitize_xcolor.py <path_to_tex_file>
```

That is the invocation the script's own usage line prints.

### What it does:
1. **Color Flattening**: Scans the document for excessively nested `xcolor` mixings (more than one `!` operation, such as `red!50!black!20!white`).
2. **Opacity Standardisation**: Truncates invalid trailing color nodes to standard opacity rules (e.g., reduces `color1!X!color2!Y!color3` down to valid standard mappings or safe two-color mixings `color1!X!color2`).
3. **In-Place Healing**: Automatically patches the `.tex` file if requested, avoiding manual find-and-replace friction.

## What flattening costs
The sanitiser flattens any `xcolor` mix deeper than one `!` and truncates trailing colour nodes, so
the diagram compiles but its colour balance may shift. That balance is a final-surface question for
the author: check the rendered PDF against the intended palette before the figure ships. The
sanitiser guarantees a parseable colour, not the one that was meant.
