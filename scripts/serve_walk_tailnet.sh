#!/usr/bin/env bash
# Serve the walk from a remote container over his tailnet.
#
# Run inside a remote (Linux) session container from the repo root:
#   TS_AUTHKEY=<tailscale auth key> bash scripts/serve_walk_tailnet.sh
#
# Requires: TS_AUTHKEY in the environment (a reusable or ephemeral key from the
# Tailscale admin console, placed in the remote environment's secrets by the
# author). The author's browsing device must be on the same tailnet.
#
# What it does, in order:
#   1. Fetch the static tailscale binaries if absent (container has no root tun
#      device - tailscaled runs in userspace-networking mode).
#   2. Join the tailnet as hostname "laplace-walk".
#   3. Start the scanner serving the walk. LAPLACE_WALK_ONLY=1 arms the
#      walk-scoped route gate (only /walk, /walk/*, /shared/*, /review/*,
#      /projection/*, /artefact/context serve; everything else refuses) once
#      that mode lands in walk.py; until then the full scanner serves and this
#      script says so plainly.
#   4. Expose 8770 on the tailnet with TLS via `tailscale serve`.
#
# Single-user by his ruling 2026-08-10: no multi-user server, no public tunnel.
# The walk token is defense in depth on top of the tailnet boundary.
set -euo pipefail

TS_DIR="${TS_DIR:-$HOME/.local/tailscale}"
TS_VERSION="${TS_VERSION:-1.86.2}"

if [ -z "${TS_AUTHKEY:-}" ]; then
  echo "TS_AUTHKEY is not set. Generate an auth key in the Tailscale admin console" >&2
  echo "and place it in the remote environment's secrets as TS_AUTHKEY." >&2
  exit 1
fi

if ! command -v tailscale >/dev/null 2>&1 && [ ! -x "$TS_DIR/tailscale" ]; then
  mkdir -p "$TS_DIR"
  arch="$(uname -m)"; case "$arch" in x86_64) a=amd64 ;; aarch64) a=arm64 ;; *) echo "unsupported arch $arch" >&2; exit 1 ;; esac
  curl -fsSL "https://pkgs.tailscale.com/stable/tailscale_${TS_VERSION}_${a}.tgz" \
    | tar -xz -C "$TS_DIR" --strip-components=1
fi
TS_BIN="$(command -v tailscale || echo "$TS_DIR/tailscale")"
TSD_BIN="$(command -v tailscaled || echo "$TS_DIR/tailscaled")"

if ! "$TS_BIN" --socket="$TS_DIR/tailscaled.sock" status >/dev/null 2>&1; then
  "$TSD_BIN" --tun=userspace-networking \
    --socket="$TS_DIR/tailscaled.sock" --statedir="$TS_DIR" >"$TS_DIR/tailscaled.log" 2>&1 &
  sleep 2
  "$TS_BIN" --socket="$TS_DIR/tailscaled.sock" up \
    --authkey="$TS_AUTHKEY" --hostname=laplace-walk
fi

WALK_TOKEN="${WALK_TOKEN:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')}"
export LAPLACE_WALK_ONLY=1 LAPLACE_WALK_TOKEN="$WALK_TOKEN"
if ! grep -q "LAPLACE_WALK_ONLY" src/laplace/manuscript/walk.py 2>/dev/null; then
  echo "note: the walk-scoped gate is not in walk.py yet - the FULL scanner will serve." >&2
fi
python3 -m laplace.desktop.offline_launcher --no-browser --tabs never &
sleep 3

"$TS_BIN" --socket="$TS_DIR/tailscaled.sock" serve --bg 8770
echo
echo "serving. Open on a tailnet device:"
echo "  https://laplace-walk.<tailnet>.ts.net/walk?corpus=paper_roland_qrc&actor=gerard&token=$WALK_TOKEN"
"$TS_BIN" --socket="$TS_DIR/tailscaled.sock" status | head -5
