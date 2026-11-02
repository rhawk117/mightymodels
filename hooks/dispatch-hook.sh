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
for phase in investigation planning implementation review; do
  case ${compact} in
    *"\"subagent_type\":\"${phase}\""* | *"\"subagent_type\":\"mightymodels:${phase}\""*)
      refuse "a phase agent runs as the main thread, so this dispatch of the ${phase} agent is refused"
      ;;
  esac
done
case ${compact} in
  *'"agent_type":"mightymodels:'*)
    case ${compact} in
      *'"agent_id":'*)
        refuse 'this subagent dispatch is refused'
        ;;
    esac
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
