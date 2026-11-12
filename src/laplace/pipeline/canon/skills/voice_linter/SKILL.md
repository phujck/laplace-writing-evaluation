---
name: voice_linter
description: The medium-general voice check. Lints markdown, HTML, Slidev/Vue decks, and plain prose for the Laplace voice - the no-slop rules latex_forge enforces on LaTeX, applied everywhere else - by masking non-prose regions (code, markup, math) first, so a violation is only ever flagged in prose.
---

# Voice Linter

One voice, many media. [The Laplace Voice](canon://aesthetics/voice_and_style) runs through every made thing - the paper, the reply, the slide, the canon. [`latex_forge`](canon://skills/latex_forge) enforces it on the manuscript. This is its counterpart for everything else: markdown, HTML, Slidev/Vue decks, plain prose. It supersedes the archived `html_mechanic`, which only saw HTML.

**Scope (the Vonnegut subset).** Run this on **public-facing artefacts** - manuscripts, talks, the website, published replies and figures. The **Vonnegut rule (semicolons, em-dashes) does not apply to internal working artefacts** - canon prose, SKILL and wiki nodes, handoffs, substrate and blueprint, dreams - so do not lint them for it (see [the voice](canon://aesthetics/voice_and_style), "public-facing artefacts only"). The other checks (British English, AI slop) are cheap to run anywhere, but the semicolon and dash hunt is a public-face concern, not worth the editing churn on internal notes.

## What it checks
- **The Vonnegut rule** - no semicolons, no em-dashes or en-dashes (use spaced hyphens). The single highest-value check for a web deck - the talk-finetune session found em-dashes everywhere.
- **British English** - analyse, behaviour, colour, parametrise, centre, and the rest.
- **AI slop** - delve, tapestry, crucial, "it's worth noting", seamless, showcase, and the usual filler.
- **Forced antithesis** - the `X, not Y` / `not X, it is Y` construction whose only content is the contrast. Flagged for review: intent matters, so this one is advisory.
- **Gnomic subtitles** are named in the report as a manual check. A portentous fragment under a title is too context-bound to catch mechanically - the report reminds rather than guesses.

## The masking principle (why it is quiet)
A semicolon in a code fence, `color` in a CSS block, an em-dash inside `$...$` KaTeX, a `%` in a LaTeX comment - none are prose, and flagging them is noise. The linter blanks every non-prose region first, length-preserving so line numbers hold, and extension-aware: code fences and inline code everywhere; HTML `<script>` / `<style>` / `<pre>` / `<code>` / comments / tags for HTML and Vue; LaTeX math, environments, `tikzpicture`, and `%` comments for `.tex`; KaTeX `$...$` for markdown and decks. It runs the rules on what remains.

It is **deck-aware** beyond the generic masking, from the v3 deck pass - three Slidev/markdown shapes that read as prose but are markup. It masks **Slidev per-slide frontmatter** (the `---`-fenced YAML between slides, not just the leading document block). It skips a **standalone `---` line** (a slide separator or a thematic-break horizontal rule is structure, never an em-dash or a sentence). And it masks **HTML entities** (`&amp;`, `&copy;`, `&#8230;` and the rest) so the terminating entity-semicolon is read as markup, not as a Vonnegut-rule semicolon.

## Usage
```
laplace_run(skill="voice_linter", target="<file-or-dir>")
laplace_run(skill="voice_linter", target="<dir>", args=["--strict"])   # exit 1 if any flag (gating)
laplace_run(skill="voice_linter", target="<file>", args=["--json"])    # machine-readable
```

A directory target walks for `.md` / `.html` / `.vue` / `.tex` / `.txt`, skipping `node_modules`, `dist`, and the like. The exit contract mirrors [`latex_forge`](canon://skills/latex_forge): 2 on an unreadable target, 0 on a completed run (flagging slop is the skill working, not failing), and 1 under `--strict` when any flag is found - the gate a deck-aware [`talk_smith`](canon://skills/talk_smith) `talk_ledger` runs the slide source through before a deck ships.
