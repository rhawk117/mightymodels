#!/usr/bin/env bash
set -euo pipefail

readonly LOGGING_UTILS="./scripts/log.sh"
readonly SHARED_UTILS="./scripts/lib.sh"

FAILURES=()

setup_environment() {
  local repository_root
  repository_root=$(git rev-parse --show-toplevel)
  cd "$repository_root"

  # shellcheck disable=SC1090
  source "$LOGGING_UTILS"
  # shellcheck disable=SC1090
  source "$SHARED_UTILS"
}

run_step() {
  local label=$1
  local exit_code=0
  shift

  log::step "$label"
  "$@" || exit_code=$?
  log::step_end

  if ((exit_code != 0)); then
    FAILURES+=("$label")
  fi

  return 0
}

ruff_format_tracked() {
  local pattern
  local status=0
  for pattern in '*.py' '*.pyi' '*.ipynb' '*.md'; do
    files_with_extension "$pattern" uv run ruff format --force-exclude || status=$?
  done
  return "$status"
}

write_format() {
  run_step "ruff format" ruff_format_tracked
  run_step "ruff lint autofix" uv run ruff check --fix --unsafe-fixes --fix-only .
  run_step "shfmt" files_with_extension '*.sh' uv run shfmt -w -i 2 -ci
  run_step "mdformat" files_with_extension '*.md' uv run mdformat
}

main() {
  setup_environment
  write_format

  if [[ -n "${FAILURES[*]-}" ]]; then
    log::error "Failed checks: ${FAILURES[*]}"
    exit 1
  fi
}

main "$@"
