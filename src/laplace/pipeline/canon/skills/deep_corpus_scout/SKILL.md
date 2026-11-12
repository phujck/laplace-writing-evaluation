---
name: deep_corpus_scout
description: Map a large corpus before distilling it. Recursively flattens a dense source tree, multi-file repo, or archive into a navigable, size-bounded skeleton (file map + structural digest + reading order) cached outside git, so an unknown corpus can be read in deliberate passes rather than one impossible gulp. Scout first; reference_archaeologist distils second.
---

# Deep Corpus Scout

A generating-stage retrieval skill for *volume*. [`reference_archaeologist`](canon://skills/reference_archaeologist) distils ONE known source past its framing. This maps an UNKNOWN large corpus first - a dense tree, a multi-file repository, a tarball of papers - so you know what is in it before spending a context pass reading it.

## What it does
Walks a directory or archive (`.tar`, `.tar.gz`, `.zip`) and writes, to a cache OUTSIDE git (the [voice corpus](canon://voice_corpus/index) firewall pattern - raw stays cached, only the skeleton surfaces into a working context):
- **`manifest.json`** - the full file tree: path, size, line count, coarse type. The map.
- **`skeleton.md`** - a bounded structural digest: headings for prose, `def` / `class` / `function` / `export` signatures for code, the first lines for the rest. Bounded by a byte budget, and any truncation is stated, never silent.
- **`chunks.txt`** - a reading order, signal-bearing files first, so a reader processes the corpus in deliberate passes.

Decoupled and host-executed: standard library only, no network, no external API. A prior dreamer forged a version coupled to external API modules; it was reverted to keep the engine self-contained. This is the decoupled re-forge.

## Usage
```
laplace_run(skill="deep_corpus_scout", target="<dir-or-archive>")
laplace_run(skill="deep_corpus_scout", target="<dir>", args=["--budget", "400000"])
```

## The boundary with reference_archaeologist
Scout when you do not yet know what is in the corpus and it is too large for one pass - the output is a map and a reading order. Distil ([`reference_archaeologist`](canon://skills/reference_archaeologist)) when you know the source and need its content carried across a firewall as a clean skeleton. Scout fills the gap before distillation - it does not replace it. The two stand distinct: volume versus targeting.
