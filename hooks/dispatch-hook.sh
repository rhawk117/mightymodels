#!/bin/sh
set -u

here=$(cd -- "$(dirname -- "$0")" && pwd -P)
# shellcheck source=/dev/null
. "${here}/lib.sh"
limit_seconds=${MIGHTYMODELS_DISPATCH_SECONDS:-8}
input=$(cat)

refuse() {
  printf 'mightymodels: the dispatch hook could not run, so %s\n' "$1" >&2
  exit 2
}

if output=$(launcher_within_limit "${MIGHTYMODELS_DISPATCH_LAUNCHER:-}" "${limit_seconds}" dispatch-hook "${input}"); then
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
