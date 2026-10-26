#!/bin/sh
set -u

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
root=${CLAUDE_PLUGIN_ROOT:-${here%/*}}
export UV_PROJECT="${root}"
export UV_PROJECT_ENVIRONMENT="${root}/.venv"
limit_seconds=${MIGHTYMODELS_DISPATCH_SECONDS:-8}
input=$(cat)

run_launcher() {
  if test -n "${MIGHTYMODELS_DISPATCH_LAUNCHER:-}"; then
    exec "${MIGHTYMODELS_DISPATCH_LAUNCHER}" dispatch-hook
  fi
  exec uv run --locked --no-dev --package mightymodels-hooks mightymodels-hooks dispatch-hook
}

launcher_within_limit() {
  printf '%s' "${input}" | run_launcher &
  launched=$!
  { sleep "${limit_seconds}" && kill "${launched}"; } >/dev/null 2>&1 &
  timer=$!
  wait "${launched}"
  status=$?
  kill "${timer}" 2>/dev/null
  return "${status}"
}

refuse() {
  printf 'mightymodels: the dispatch hook could not run, so %s\n' "$1" >&2
  exit 2
}

if output=$(launcher_within_limit); then
  test -z "${output}" || printf '%s\n' "${output}"
  exit 0
fi

compact=$(printf '%s' "${input}" | tr -d '[:space:]')
case ${compact} in
  *'"agent_type":"mightymodels:'*)
    refuse 'this subagent dispatch is refused'
    ;;
esac
if test -d "${CLAUDE_PROJECT_DIR:-.}/.mightymodels"; then
  for implementer in engineer architect intern; do
    case ${compact} in
      *"\"subagent_type\":\"${implementer}\""* | *"\"subagent_type\":\"mightymodels:workers:${implementer}\""*)
        refuse "it cannot tell whether a task is started and this dispatch of the ${implementer} is refused"
        ;;
    esac
  done
fi
printf '%s\n' 'mightymodels: the dispatch hook could not run, so this dispatch was not checked' >&2
exit 0
