#!/bin/sh
set -u

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=/dev/null
. "${here}/lib.sh"
limit_seconds=${MIGHTYMODELS_MAIN_THREAD_SECONDS:-8}
input=$(cat)

if output=$(launcher_within_limit "${MIGHTYMODELS_MAIN_THREAD_LAUNCHER:-}" "${limit_seconds}" main-thread-hook "${input}"); then
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
