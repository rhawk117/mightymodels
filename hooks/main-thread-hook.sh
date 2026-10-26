#!/bin/sh
set -u

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
root=${CLAUDE_PLUGIN_ROOT:-${here%/*}}
export UV_PROJECT="${root}"
export UV_PROJECT_ENVIRONMENT="${root}/.venv"
limit_seconds=${MIGHTYMODELS_MAIN_THREAD_SECONDS:-8}
input=$(cat)

run_launcher() {
  if test -n "${MIGHTYMODELS_MAIN_THREAD_LAUNCHER:-}"; then
    exec "${MIGHTYMODELS_MAIN_THREAD_LAUNCHER}" main-thread-hook
  fi
  exec uv run --locked --no-dev --package mightymodels-hooks mightymodels-hooks main-thread-hook
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

if output=$(launcher_within_limit); then
  test -z "${output}" || printf '%s\n' "${output}"
  exit 0
fi

compact=$(printf '%s' "${input}" | tr -d '[:space:]')
case ${compact} in
  *'"agent_type":"mightymodels:'*)
    exit 0
    ;;
esac
test -d "${CLAUDE_PROJECT_DIR:-.}/.mightymodels" || exit 0
case ${compact} in
  *'"tool_name":"Edit"'* | *'"tool_name":"Write"'*)
    printf '%s\n' '{"systemMessage":"mightymodels: the main-thread hook could not run, so this edit was not checked against an unclosed ticket"}'
    exit 0
    ;;
  *'"tool_name":"Bash"'*) ;;
  *)
    exit 0
    ;;
esac
case ${compact} in
  *'"command":"'*git*push*)
    printf '%s\n' 'mightymodels: the main-thread hook could not run, so it cannot tell whether the landing is proven and this push is refused' >&2
    exit 2
    ;;
esac
exit 0
