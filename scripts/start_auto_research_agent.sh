#!/usr/bin/env bash
# Trusted operator launcher; no arbitrary Codex configuration/command passthrough.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$PROJECT_ROOT"
# Keep this checkout's model login independent of other RAX projects. Explicit
# --provider-home/--profile arguments still override these local defaults.
provider_args=()
if [[ -f "$PROJECT_ROOT/runtime/operator/codex-provider/experiment-profile" ]]; then
    provider_args=(--provider-home "$PROJECT_ROOT/runtime/operator/codex-provider")
fi
exec "$PROJECT_ROOT/runtime/envs/robodojo/bin/python" -m harness.codex_cli.auto_research "${provider_args[@]}" "$@"
