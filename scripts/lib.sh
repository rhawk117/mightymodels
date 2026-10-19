#!/usr/bin/env bash
# Shared helpers for scripts/format.sh and scripts/lint.sh. Source it from the repository root.

# Runs CMD ARGS -- FILES... over the tracked files matching PATTERN that exist in the
# working tree. `git ls-files` also lists paths deleted but not yet staged, so those are
# filtered out. Runs nothing when no file matches, and returns git's status when it fails.
files_with_extension() {
  local pattern=$1
  shift
  local path
  local -a existing=()
  while IFS= read -r -d '' path; do
    if [[ -e $path ]]; then
      existing+=("$path")
    fi
  done < <(git ls-files -z -- "$pattern")
  wait $! || return

  if ((${#existing[@]} == 0)); then
    return 0
  fi
  "$@" -- "${existing[@]}"
}
