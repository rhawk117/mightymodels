# shellcheck shell=sh
# Sourced by hook.sh, dispatch-hook.sh and main-thread-hook.sh. The caller sets `here`.

root=${CLAUDE_PLUGIN_ROOT:-${here%/*}}
export UV_PROJECT="${root}"
export UV_PROJECT_ENVIRONMENT="${root}/.venv"

# run_launcher OVERRIDE ARGS...: run OVERRIDE when set, else the packaged launcher.
run_launcher() {
  override=$1
  shift
  if test -n "${override}"; then
    exec "${override}" "$@"
  fi
  exec uv run --locked --no-dev --package mightymodels-hooks mightymodels-hooks "$@"
}

# launcher_within_limit OVERRIDE SECONDS SUBCOMMAND INPUT: feed INPUT to the launcher, killing it after SECONDS.
launcher_within_limit() {
  printf '%s' "$4" | run_launcher "$1" "$3" &
  launched=$!
  { sleep "$2" && kill "${launched}"; } >/dev/null 2>&1 &
  timer=$!
  wait "${launched}"
  status=$?
  kill "${timer}" 2>/dev/null
  return "${status}"
}
