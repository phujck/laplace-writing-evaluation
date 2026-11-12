#!/usr/bin/env bash
# Serve the walk from a remote container over a cloudflared quick tunnel.
# The no-account fallback to scripts/serve_walk_tailnet.sh - single-user (his
# ruling 2026-08-10), gated by the walk token; the URL is unlisted but public,
# so the walk-scoped mode + token are the boundary, not the network.
#
# Run inside a remote (Linux) session container from the repo root:
#   bash scripts/serve_walk_quicktunnel.sh
set -euo pipefail

CF_DIR="${CF_DIR:-$HOME/.local/cloudflared}"
if ! command -v cloudflared >/dev/null 2>&1 && [ ! -x "$CF_DIR/cloudflared" ]; then
  mkdir -p "$CF_DIR"
  arch="$(uname -m)"; case "$arch" in x86_64) a=amd64 ;; aarch64) a=arm64 ;; *) echo "unsupported arch $arch" >&2; exit 1 ;; esac
  curl -fsSL -o "$CF_DIR/cloudflared" \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${a}"
  chmod +x "$CF_DIR/cloudflared"
fi
CF_BIN="$(command -v cloudflared || echo "$CF_DIR/cloudflared")"

WALK_TOKEN="${WALK_TOKEN:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')}"
export LAPLACE_WALK_ONLY=1 LAPLACE_WALK_TOKEN="$WALK_TOKEN"
if ! grep -q "LAPLACE_WALK_ONLY" src/laplace/manuscript/walk.py 2>/dev/null; then
  echo "note: the walk-scoped gate is not in walk.py yet - the FULL scanner will serve." >&2
  echo "      do not open the tunnel for real use until the gate lands." >&2
fi
python3 -m laplace.desktop.offline_launcher --no-browser --tabs never &
sleep 3

echo "opening the quick tunnel (the URL prints below; append the path):"
echo "  /walk?corpus=paper_roland_qrc&actor=gerard&token=$WALK_TOKEN"
"$CF_BIN" tunnel --no-autoupdate --url http://127.0.0.1:8770
