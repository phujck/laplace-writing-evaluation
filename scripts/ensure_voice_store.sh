#!/bin/sh
# Ensure the DERIVED voice-exemplar passage store is present + fresh (any box).
#
# The voice wash (dispatch.compile_weld_dispatch(voice_on=True)) grounds on the
# author's REAL prose: it retrieves the nearest authored passages from a sealed,
# embedded store. That store is a DERIVED CACHE at
#   corpus_stores/voice_corpus_cache/exemplar_passages/  (tracked, travels)
# rebuilt deterministically from the RAW sources that DO travel with the repo at
#   voice_corpus/exemplars/<slug>/*.tex  (committed, ~924 KB)
# by the one command  `python -m laplace.engine.voice_corpus_ingest ingest`.
#
# THE INCIDENT this closes (2026-07-11). A voice wash refused with
#   "no store at corpus_stores/voice_corpus_cache/exemplar_passages. Run ... ingest first."
# and both the wash agent and the orchestrator read that as a HARD SEAL WALL
# ("his prose only lives on his machine") when it is nothing of the sort: the raw
# exemplars are committed and the store rebuilds anywhere with one command. A
# remedy-naming error (the message NAMED the fix) was treated as a wall. The
# structural cure is the same one TeX got: PROVISION the derived cache at session
# start from the committed raw, so it is simply present when a wash runs.
#
# Precedent: scripts/ensure_tex.sh. The session-start hook calls this in the
# BACKGROUND on every cold start (detached), and a wash can call it synchronously
# if it needs the store before that finishes.
#
# Idempotent: FAST NO-OP when the store manifest exists and the tree under
# voice_corpus/exemplars (+ the store path) is git-clean (the freshness test).
# Rebuilds only when the store is ABSENT or STALE vs voice_corpus/exemplars.
#
# FAIL-LOUD CONTRACT (mirrors ensure_tex.sh). Runs DETACHED, so its exit code is
# not observed live; the durable signal is the LAST LINE of its output (captured
# to .venv/voice-store.log): ALWAYS one of
#     ensure_voice_store: SUCCESS ...   (store present + fresh -> the wash can ground)
#     ensure_voice_store: FAILED  ...   (ingest could not build/embed the store)
# and its FIRST line is  ensure_voice_store: START ...  so a run killed mid-build
# (container reclaim) is distinguishable from "never ran" and from an honest FAILED.
#
# NOTE: deliberately NOT `set -e` -- we must always reach the verdict even when an
# intermediate step exits non-zero; the verdict is decided by whether the store
# manifest ends up present, never by an intermediate exit code.
set -u

log() { echo "ensure_voice_store: $*"; }

# START sentinel -- ALWAYS the first line.
log "START pid $$ $(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown-time)"

# Resolve repo root from this script's location (scripts/ is one level down).
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

EXEMPLAR_DIR="$REPO_ROOT/voice_corpus/exemplars"
STORE_DIR="$REPO_ROOT/corpus_stores/voice_corpus_cache/exemplar_passages"
MANIFEST="$STORE_DIR/manifest.json"

# No raw sources -> nothing to build from. This is NOT a failure of provisioning
# (a checkout without the exemplars), so report SUCCESS-as-skip and exit 0.
if [ ! -d "$EXEMPLAR_DIR" ] || [ -z "$(find "$EXEMPLAR_DIR" -name '*.tex' -print -quit 2>/dev/null)" ]; then
  log "SUCCESS no committed .tex under $EXEMPLAR_DIR -- nothing to ingest (skip)"
  exit 0
fi

# Freshness test: the store is FRESH when the manifest exists and the exemplar
# tree + the store path are git-clean (nothing locally modified/untracked there).
# WO-20260819-voice-store-mtime-fresh-clone: this used to be `find -newer`
# (manifest.json vs committed .tex mtimes), which false-positived on EVERY fresh
# clone -- checkout writes the .tex files a few seconds after the manifest, so
# mtime ordering is checkout-order noise, never a content signal. `git status
# --porcelain` is content-aware (compares against the committed blob, not a
# timestamp) and a fresh clone's clean tree always reads FRESH here, exactly the
# invariant git already guarantees.
if [ -f "$MANIFEST" ]; then
  DIRTY=$(cd "$REPO_ROOT" && git status --porcelain --untracked-files=all -- \
    voice_corpus/exemplars corpus_stores/voice_corpus_cache/exemplar_passages 2>/dev/null)
  if [ -z "$DIRTY" ]; then
    log "SUCCESS store present and fresh ($MANIFEST; git-clean) -- no-op"
    exit 0
  fi
  log "store STALE (git-dirty: $DIRTY) -- rebuilding"
else
  log "store ABSENT ($MANIFEST missing) -- building"
fi

# Resolve a Python that can import laplace. Prefer the project venv (what the
# session-start hook provisions), then `uv run`, then a bare python3.
VENV_PY="$REPO_ROOT/.venv/bin/python"
run_ingest() {
  cd "$REPO_ROOT" || return 1
  if [ -x "$VENV_PY" ]; then
    PYTHONUTF8=1 "$VENV_PY" -m laplace.engine.voice_corpus_ingest ingest
  elif command -v uv >/dev/null 2>&1; then
    PYTHONUTF8=1 uv run python -m laplace.engine.voice_corpus_ingest ingest
  else
    PYTHONUTF8=1 python3 -m laplace.engine.voice_corpus_ingest ingest
  fi
}

if ! run_ingest; then
  log "WARN ingest returned non-zero; verifying the store anyway"
fi

# THE VERDICT -- always the last line, exit code matches. Decided solely by
# whether the store manifest is now present (the wash's precondition).
if [ -f "$MANIFEST" ]; then
  log "SUCCESS ingested -> $MANIFEST"
  exit 0
else
  log "FAILED store manifest still absent after ingest ($MANIFEST); the voice wash will refuse until this is fixed (needs the vendored embedding model / network egress)"
  exit 1
fi
