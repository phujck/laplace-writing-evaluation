#!/bin/sh
# Ensure a REVTeX-capable LaTeX toolchain is present (remote Linux container).
#
# The manuscript pipeline's compile + typography-lint leg needs pdflatex/latexmk
# with revtex4-2 + the usual math/figure packages. The remote container ships
# without TeX and is ephemeral, so this is the single authoritative installer:
# the session-start hook calls it in the background on every cold start, and the
# compile stage can call it synchronously if it needs TeX before that finishes.
# Idempotent: a no-op when pdflatex is already on PATH.
#
# FAIL-LOUD CONTRACT (legC-C3). This runs DETACHED from the session-start hook,
# so its exit code is not observed live. The durable signal is therefore the LAST
# LINE of its output (captured to .venv/tex-install.log): it is ALWAYS one of
#     ensure_tex: SUCCESS ...      (pdflatex resolvable -> the leg is ready)
#     ensure_tex: FAILED  ...      (pdflatex still absent -> the leg is broken)
# An earlier revision died SILENTLY at `apt-get update` when a repo re-published
# its Release file (exit non-zero under `set -e`, no verdict, pdflatex quietly
# absent). This revision (a) tolerates that with --allow-releaseinfo-change and
# proceeds on cached lists, and (b) always emits the verdict + a matching exit
# code. The hook greps that last line on the next cold start and surfaces a prior
# FAILED loudly instead of leaving a compile to trip over a missing pdflatex.
#
# Durable fix (like /opt/pw-browsers for Playwright and models/fastembed for the
# embedder): bake this package set into the environment image / setup script so
# it is not re-downloaded each session. This script is the repo-side fallback.
#
# NOTE: deliberately NOT `set -e`. We must always reach the SUCCESS/FAILED verdict
# even when a sub-step (apt-get update on a changed Release file, a transient
# mirror) exits non-zero; the verdict is decided by whether pdflatex ends up on
# PATH, never by an intermediate exit code.
set -u

log() { echo "ensure_tex: $*"; }

# START sentinel -- ALWAYS the first line. A log that carries START but no
# SUCCESS/FAILED verdict means the install was killed mid-run (container
# reclaim, OOM) before the verdict could be emitted: a third state the hook
# must distinguish from "never ran" and from an honest FAILED. Observed live
# 2026-07-11: a log ending at apt's "Reading package lists..." with pdflatex
# absent and the hook silent about it.
log "START pid $$ $(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown-time)"

if command -v pdflatex >/dev/null 2>&1; then
  log "SUCCESS pdflatex already present ($(command -v pdflatex))"
  exit 0
fi

PKGS="texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-publishers texlive-science latexmk"
log "installing REVTeX toolchain ($PKGS)"

# apt-get update is the classic silent-death point: a re-published Release/InRelease
# makes it exit non-zero. --allow-releaseinfo-change tolerates that; and even if
# update still returns non-zero (transient mirror), PROCEED to install on the
# cached package lists rather than aborting.
if ! apt-get update --allow-releaseinfo-change; then
  log "WARN apt-get update returned non-zero; proceeding to install on cached lists"
fi
if ! apt-get install -y --no-install-recommends $PKGS; then
  log "WARN apt-get install returned non-zero; verifying pdflatex anyway"
fi

# THE VERDICT -- always the last line, exit code matches.
if command -v pdflatex >/dev/null 2>&1; then
  log "SUCCESS installed -> $(pdflatex --version 2>/dev/null | head -1)"
  exit 0
else
  log "FAILED pdflatex still absent after install ($PKGS)"
  exit 1
fi
