#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

workspace=${LAPLACE_WORKSPACE_ROOT:-/workspace}
if [ ! -f "$workspace/registry_projects.json" ]; then
  echo "Laplace Writing refused: $workspace/registry_projects.json is missing." >&2
  echo "Mount the exported workspace at /workspace; no host-home state is consulted." >&2
  exit 2
fi
if [ ! -d "$workspace/profiles" ]; then
  echo "Laplace Writing refused: $workspace/profiles is missing." >&2
  exit 2
fi

exec python -m laplace.web.writing_server --root "$workspace" \
  --state "${LAPLACE_STATE:-$workspace/.laplace-state}" --host 0.0.0.0 --port 8771
