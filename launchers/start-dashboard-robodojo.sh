#!/usr/bin/env bash
# Start the local RAX dashboard. Simulator installation and assets are separate.
set -eo pipefail
environment=rax_robodojo
checkout=/home/dodo/code/rax/robodojo-behavior/isaac6
port=8767
# Retain the old selector for commands saved before Isaac Sim 5.1 was retired.
if [[ "${1:-}" == --isaac6 ]]; then
    shift
fi
source /home/dodo/system/miniconda3/etc/profile.d/conda.sh
conda activate "$environment"
export CUDA_PATH="$CONDA_PREFIX" PYTHONNOUSERSITE=1
source "$checkout/scripts/robodojo_env.sh"
set -u
cd "$ROBODOJO_PROJECT_ROOT"
# Keep the LIBERO dashboard's default port 8765 available.
exec bash scripts/run_operator_dashboard.sh --port "$port" "$@"
