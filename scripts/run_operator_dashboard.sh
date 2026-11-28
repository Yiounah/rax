#!/usr/bin/env bash
# Start the trusted, loopback-only RoboDojo operator dashboard.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
runtime_root="${ROBODOJO_RUNTIME_ROOT:-$PROJECT_ROOT/runtime}"
environment_root="$(readlink -f "${ROBODOJO_ENV_ROOT:-$runtime_root/envs/robodojo}")"
conda_init="$runtime_root/miniforge3/etc/profile.d/conda.sh"
[[ -f "$conda_init" && -x "$environment_root/bin/python" ]] || {
    echo 'Missing RoboDojo Conda environment; see docs/ISAAC6_COMPATIBILITY.md.' >&2; exit 2;
}
# Compiler activation hooks are not nounset-safe.
source "$conda_init"
conda activate "$environment_root"
export CUDA_PATH="$CONDA_PREFIX" PYTHONNOUSERSITE=1
source "$SCRIPT_DIR/robodojo_env.sh"
set -u
PYTHON="$ROBODOJO_PYTHON"

# Compatibility with commands saved before the Isaac Sim 6 consolidation.
if [[ "${1:-}" == --isaac6 ]]; then
    shift
fi

[[ -x "$PYTHON" ]] || { echo "Missing RoboDojo Python: $PYTHON" >&2; exit 2; }
cd "$PROJECT_ROOT"
exec "$PYTHON" -m services.dashboard.server --project-root "$PROJECT_ROOT" --port 8767 "$@"
