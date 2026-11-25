#!/usr/bin/env bash
# Start the local RAX dashboard. Simulator installation and assets are separate.
set -eo pipefail
environment=rax_robodojo
checkout=/home/dodo/code/rax/robodojo-behavior/native
port=8766
if [[ "${1:-}" == --isaac6 ]]; then
    shift
    environment=rax_robodojo_isaac6
    checkout=/home/dodo/code/rax/robodojo-behavior/isaac6
    port=8767
fi
source /home/dodo/system/miniconda3/etc/profile.d/conda.sh
conda activate "$environment"
export CUDA_PATH="$CONDA_PREFIX" PYTHONNOUSERSITE=1
source "$checkout/scripts/robodojo_env.sh"
set -u
cd "$ROBODOJO_PROJECT_ROOT"
# Keep the LIBERO dashboard's default port 8765 available.
exec bash scripts/run_operator_dashboard.sh --port "$port" "$@"
