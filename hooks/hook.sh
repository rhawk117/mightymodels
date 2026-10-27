#!/bin/sh
set -u

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=/dev/null
. "${here}/lib.sh"

if output=$(run_launcher "${MIGHTYMODELS_HOOK_LAUNCHER:-}" "$@"); then
  test -z "${output}" || printf '%s\n' "${output}"
  exit 0
fi

printf 'mightymodels hook did nothing: %s could not run\n' "${1:-the hook}" >&2
exit 0
