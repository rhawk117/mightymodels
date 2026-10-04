#!/usr/bin/env bash
set -eu
mkdir -p fixtures/plugin/.claude-plugin
cat > fixtures/plugin/.claude-plugin/plugin.json <<'JSON'
{
  "name": "infra-tools",
  "version": "0.1.0",
  "description": "Infrastructure helpers for the platform team",
  "author": { "name": "Platform Team" }
}
JSON
