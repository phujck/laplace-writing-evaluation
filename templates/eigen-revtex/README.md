# eigen-revtex — the EigenEngine house layer on REVTeX4-2

The shipped, reusable manuscript template. **REVTeX4-2 is the base**; the eigen
signature is a thin, portable layer on top of it (`eigen-revtex.sty`), not a
bespoke document class.

## Use

```latex
\documentclass[reprint,aps,prx,superscriptaddress,nofootinbib]{revtex4-2}
\usepackage{eigen-revtex}
```

`main.tex` is a minimal, compiling skeleton. Build with `pdflatex main.tex`
(twice, to resolve references) or `latexmk -pdf main.tex`.

## Lineage — refined from `eigenengine.sty`

The predecessor `eigenengine.sty` (still present under `eigenengine/`,
`paper_self_theory/` and the subset-sum whitepapers) is an **article-class**
style: `\documentclass[twocolumn,10pt]{article}` + `\usepackage{eigenengine}`.
Because the base was `article`, a projection could silently compile as plain
article with no house discipline. Gerard's decision (2026-07): keep REVTeX4-2 as
the base and carry only the portable eigen signature on top.

**Dropped (the cringe — article-class branding chrome that fights REVTeX or
over-styles the page):** the `\EigenEngine` wordmark, the `\eigencolophon`
eigen-equation mark, the `fancyhdr` running header, `titlesec`-coloured section
numbers (`titlesec` is unsupported under REVTeX), the `\maketitleeigen` branded
title block, and the `\eigensign` self-promotional sign-off. REVTeX supplies its
own title block, sectioning, columns and running heads.

**Kept (the load-bearing signature):** portable microtypography, the canonical
maths / notation / float stack from `profiles/typography/prx-revtex4-2.json`, the
shared figure palette (`ink`/`phys`/`acc`/`faint`), phys-coloured hyperlinks, and
the `\claim` provenance tag.

> Note: `microtype` runs with `expansion=false` because font expansion needs
> scalable outline fonts (lmodern / cm-super), which are not guaranteed on every
> TeX install. Protrusion (the larger visual win) stays on.

## The gate and the lint

`src/laplace/pipeline/tex_template.py` enforces this template mechanically:

- `check_template(tex_source)` — the **gate**. Asserts the manuscript is on the
  `revtex4-2` base, carries `\usepackage{eigen-revtex}`, and has the required
  packages (satisfied transitively by the layer). Returns `{"pass", ...}`.
- `lint_typography(log_text, tex_source=None)` — the **lint**. Parses a real
  pdflatex `.log` for overfull/underfull boxes, undefined refs/citations,
  multiply-defined labels, missing figures/inputs, font substitutions, and
  hyperref/float warnings; with the `.tex` source it also enforces the
  no-titles-on-figures rule. Returns structured findings.
