#!/bin/sh
# Legacy uv provisioning only; ordinary Laplace uses scripts/laplace-python.
set -u

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")
MODE=build
PROFILE=
LEGACY=0

usage() {
  echo "usage: sh scripts/standup.sh --legacy-development [--check] --profile cpu|gpu"
  echo "  build is an explicit networked operator act; --check never installs"
  echo "  ordinary runtime: ./scripts/laplace-python (LAPLACE_PYTHON may select its package interpreter)"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --legacy-development) LEGACY=1 ;;
    --check) MODE=check ;;
    --profile)
      shift
      PROFILE=${1:-}
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "standup: FAILED unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ "$LEGACY" != 1 ]; then
  echo "standup: LEGACY ONLY; no action taken. Use ./scripts/laplace-python for current Laplace." >&2
  usage >&2
  exit 2
fi

case "$PROFILE" in
  cpu|gpu) ;;
  *) echo "standup: FAILED choose exactly one --profile cpu|gpu" >&2; exit 2 ;;
esac

EXPECTED=$(/usr/bin/python3 -I -S -B -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["legacy_development"]["expected_python"])' "$ROOT/runtime_profiles.toml")
VENV=${UV_PROJECT_ENVIRONMENT:-"$ROOT/.venv"}
case "$VENV" in
  /*) ;;
  *) VENV="$ROOT/$VENV" ;;
esac
VENV_PY="$VENV/bin/python"

root_key=$(printf '%s' "$ROOT" | sha256sum | cut -d' ' -f1)
LOCK_DIR=${XDG_RUNTIME_DIR:-/tmp}
LOCK_FILE="$LOCK_DIR/laplace-runtime-$root_key.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "standup: BUSY/UNVERIFIED another operator build or check holds $LOCK_FILE" >&2
  exit 75
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "standup: FAILED uv is required; no pip fallback is permitted" >&2
  exit 1
fi

uv_check() {
  if [ "$PROFILE" = gpu ]; then
    (cd "$ROOT" && UV_PROJECT_ENVIRONMENT="$VENV" uv sync --check --locked --python "$EXPECTED" \
      --extra analysis --extra dev --extra docs --extra figures --extra gpu)
  else
    (cd "$ROOT" && UV_PROJECT_ENVIRONMENT="$VENV" uv sync --check --locked --python "$EXPECTED" \
      --extra analysis --extra dev --extra docs --extra figures --extra embed)
  fi
}

verify() {
  if [ ! -x "$VENV_PY" ]; then
    echo "standup: FAILED no interpreter at $VENV_PY" >&2
    return 1
  fi
  actual=$($VENV_PY -c 'import platform; print(platform.python_version())')
  if [ "$actual" != "$EXPECTED" ]; then
    echo "standup: FAILED $VENV uses Python $actual; profile requires $EXPECTED" >&2
    return 1
  fi
  uv_check || {
    echo "standup: FAILED $VENV is not synchronized exactly with the selected uv.lock profile" >&2
    return 1
  }
  # uv_check already checks this legacy lock exactly. The current package-capability
  # verifier belongs to scripts/laplace-python and must not certify a legacy venv.
  if [ "$PROFILE" = gpu ]; then
    (cd "$ROOT" && "$VENV_PY" scripts/runtime_gpu_proof.py) || return 1
  fi
}

if [ "$MODE" = check ]; then
  verify || exit 1
  echo "standup: SUCCESS profile $PROFILE verified; no work done"
  exit 0
fi

if [ -x "$VENV_PY" ]; then
  actual=$($VENV_PY -c 'import platform; print(platform.python_version())')
  if [ "$actual" != "$EXPECTED" ]; then
    echo "standup: REFUSED existing $VENV uses Python $actual; expected $EXPECTED" >&2
    echo "standup: preserve or archive it, then choose an empty UV_PROJECT_ENVIRONMENT" >&2
    exit 1
  fi
fi

set -- --locked --python "$EXPECTED" --extra analysis --extra dev --extra docs --extra figures
if [ "$PROFILE" = gpu ]; then
  set -- "$@" --extra gpu
else
  set -- "$@" --extra embed
fi

echo "standup: START explicit exact sync into $VENV (profile $PROFILE; Python $EXPECTED)"
(cd "$ROOT" && UV_PROJECT_ENVIRONMENT="$VENV" uv sync "$@") || {
  echo "standup: FAILED locked sync; environment and uv cache preserved" >&2
  exit 1
}
verify || {
  echo "standup: FAILED execution verification; environment preserved" >&2
  exit 1
}
printf '%s\n' "$PROFILE" > "$VENV/.laplace-runtime-profile"
echo "standup: SUCCESS exact locked profile $PROFILE at $VENV"
