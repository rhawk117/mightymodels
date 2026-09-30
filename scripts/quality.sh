#!/usr/bin/env bash

set -uo pipefail
shopt -s globstar

readonly MARKETPLACE='sre-copilot-marketplace-plugin'
readonly RUFF_CONFIG=(--config .ruff.toml --force-exclude)
readonly AGENT_PLUGINS_SCHEMA='agent-plugins.org/schemas/'
readonly LEGACY_PATHS=(
  SKILL.md agents hooks.json hooks/hooks.json .mcp.json .github/mcp.json
  lsp.json .github/lsp.json
)

repository_root=$(git rev-parse --show-toplevel) || exit 1
cd "${repository_root}" || exit 1
# shellcheck source=scripts/log.sh
source scripts/log.sh

FAILURES=()

run() {
  local label=$1
  shift

  log::info "${label}"
  "$@" || {
    FAILURES+=("${label}")
    return 1
  }
}

run_formatter() {
  run 'Ruff Format' uv run ruff format "${RUFF_CONFIG[@]}" .
  run 'Ruff Fix' uv run ruff check "${RUFF_CONFIG[@]}" --fix-only --unsafe-fixes .
  run 'Markdown Format' uv run mdformat plugins/**/*.md doc/**/*.md
}

run_linter() {
  local pyproject

  run 'Ruff Format Check' uv run ruff format "${RUFF_CONFIG[@]}" --check .
  run 'Ruff Check' uv run ruff check "${RUFF_CONFIG[@]}" .
  run 'Markdown Check' uv run mdformat --check plugins/**/*.md doc/**/*.md

  for pyproject in plugins/*/pyproject.toml; do
    lint_python_plugin "${pyproject%/pyproject.toml}"
  done

  run 'Plugin Schema' uv run check-jsonschema \
    --schemafile schemas/plugin.schema.json plugins/*/plugin.json
  run 'Marketplace Schema' uv run check-jsonschema \
    --schemafile schemas/marketplace.schema.json .github/plugin/marketplace.json

  lint_copilot_plugins
}

lint_python_plugin() {
  local plugin=$1
  local name=${plugin#plugins/}

  run "[${name}] ty" uv run --project "${plugin}" --frozen --group check \
    ty check --config-file ty.toml --config "environment.root=[\"${plugin}\"]" \
    --config "src.include=[\"${plugin}/src\"]" --no-progress "${plugin}/src"
  run "[${name}] pytest" uv run --project "${plugin}" --frozen --group check \
    pytest "${plugin}" -q
}

lint_copilot_plugins() {
  local manifest

  if ! command -v copilot >/dev/null; then
    log::error 'copilot not on PATH: npm install --global @github/copilot'
    FAILURES+=('Copilot CLI')
    return
  fi

  COPILOT_SANDBOX=$(mktemp -d)
  trap 'rm -rf -- "${COPILOT_SANDBOX}"' EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM

  run '[copilot] marketplace add' sandboxed_copilot plugin marketplace add "${PWD}" || return

  for manifest in plugins/*/plugin.json; do
    verify_plugin "${manifest%/plugin.json}"
  done
}

sandboxed_copilot() {
  COPILOT_HOME=${COPILOT_SANDBOX} copilot "$@"
}

verify_plugin() {
  local plugin=$1
  local name=${plugin#plugins/}
