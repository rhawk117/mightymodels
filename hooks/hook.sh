#!/bin/sh
set -u

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
root=${CLAUDE_PLUGIN_ROOT:-${here%/*}}
export UV_PROJECT="${root}"
export UV_PROJECT_ENVIRONMENT="${root}/.venv"

run_launcher() {
  if test -n "${MIGHTYMODELS_HOOK_LAUNCHER:-}"; then
    exec "${MIGHTYMODELS_HOOK_LAUNCHER}" "$@"
  fi
  exec uv run --locked --no-dev --package mightymodels-hooks mightymodels-hooks "$@"
}

if output=$(run_launcher "$@"); then
  test -z "${output}" || printf '%s\n' "${output}"
  exit 0
fi

printf 'mightymodels hook did nothing: %s could not run\n' "${1:-the hook}" >&2
exit 0
