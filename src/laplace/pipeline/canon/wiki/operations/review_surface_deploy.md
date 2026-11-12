# Review-Surface Deploy — publishing a manuscript for commentary

The **review surface** is the author's website commentary app at
`phujck.github.io/review/ssc/`: a self-contained, passphrase-gated PDF-comment tool
(pins, text-selection comments, provenance hover, comments that push straight to the
`phujck/laplace` feedback inbox). It is the terminal review bar - the automated weld gets
a manuscript close and structural; the author's review fire lands the voice
([`voice_and_style`](canon://aesthetics/voice_and_style.md)). This node owns *how a new
manuscript version reaches that surface*. It is the web-deploy leg of the
[Release pipeline](canon://operations/compilation_and_release.md), specialised to the
review artefact.

## The invariant - the bundle is a frozen snapshot of REVIEW MODE

The app is fed one encrypted blob, `review/ssc/data.enc`
(`MAGIC(LREV1\0) + salt + iv + AES-256-GCM(JSON)`, PBKDF2-SHA256 200k, decrypted
in-browser - the host never sees plaintext). Its plaintext `DATA` is **exactly what the
live REVIEW MODE (`projection_viewer`, [the manuscript-projection surface](canon://workflow/manuscript_projection.md)) computes on demand**, frozen:
rendered pages, per-page provenance anchor bands, the selectable text layer, the spans,
the seeded feedback, and the baked push token. So the packer never invents structure - it
reuses the same mechanisms the viewer already trusts (`render_pages`, `text_layer`,
`synctex_anchor`, `load_map`, `doc_model`). Build the bundle any other way and it drifts
from the surface the author actually reviews on.

## The mechanism - one committed command, not tribal knowledge

**`scripts/build_review_bundle.py`** is the reproducible packer. Do NOT hand-roll a new
one - that packer was ad-hoc and uncommitted once, which is precisely the reconstruction
gap this node closes. To deploy version N:

* **Compile the manuscript** so `main.pdf` and a *matching* `main.synctex.gz` exist (the
  Forge Compiler axiom of the [release pipeline](canon://operations/compilation_and_release.md);
  the anchors read synctex, so a hand-copied PDF with a stale synctex silently serves blank
  provenance).
* **Seal**: `LAPLACE_SITE_PASSWORD=<phrase> python scripts/build_review_bundle.py
  --old <site>/review/ssc/data.enc --out <site>/review/ssc/data.enc --git-head <commit>`.
  The packer **lifts the baked `github_token` from the existing bundle by decrypting it** -
  the token is never re-handed, and no fragment of it is ever printed.
* **Reuse the passphrase** so the link + password already shared with reviewers stay valid;
  re-keying is the author's call, not a default, because it forces re-distribution.
* **Bump `CFG.git_head`** in `review/ssc/index.html` to the version's commit. The polished
  app itself is stable - a deploy regenerates `data.enc` and bumps the head, nothing more.

## The guardrails

* **Pages are WebP.** A bare-PNG bundle is ~3x heavier - a real regression on the mobile
  surface. Re-encode preserves pixel dimensions, so `DATA.dpi` and every anchor/pin
  coordinate (all derived from `img.naturalHeight*72/dpi`) are unchanged.
* **Match the deployed `DATA` shape, not a guess.** The app is the contract: spans render
  as `L{start_line}-{end_line}`, anchor bands are `{y0,y1,section,file,line,nodes}`. Decrypt
  the current bundle and mirror its keys rather than inferring them.
* **Verify in a real browser, not the roundtrip alone** (the twice-banked lesson: use the
  thing). Unlock, confirm every page renders (the historic blank-page bug was a zero-area
  lazy-load deadlock), that anchors/pins resolve, and that the seeded comments seed. The
  packer's decrypt-after-encrypt self-check proves the seal, never the render.

## The secrets are author-forks

The passphrase and the push token are the author's to supply/preserve - stop hard here, do
not fabricate either. The token lives only inside the encrypted bundle; the passphrase lives
only with the author. A deploy needs the passphrase at build time and nothing else.

*Seeded 2026-07-04 from the first committed deploy: v5 (Spectral Surface Generation /
subset-sum-itqde) to the review surface, replacing a pre-v5 bundle. Refine when the surface
grows a second corpus or the release orchestration folds this leg in.*
