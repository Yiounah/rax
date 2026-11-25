#!/usr/bin/env bash
# Start the LIBERO/LIBERO-PRO operator dashboard.
set -eo pipefail
source /home/dodo/system/miniconda3/etc/profile.d/conda.sh
conda activate rax_libero
set -u
cd /home/dodo/code/rax/libero-pro/native
exec bash scripts/run_operator_dashboard.sh "$@"
