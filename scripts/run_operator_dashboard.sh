#!/usr/bin/env bash
# Start the trusted, loopback-only RAX operator dashboard.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
runtime_root="${RAX_RUNTIME_ROOT:-$PROJECT_ROOT/runtime}"
environment_root="$(readlink -f "${RAX_HOST_ENV_ROOT:-$runtime_root/envs/host}")"
conda_init="$runtime_root/miniforge3/etc/profile.d/conda.sh"
[[ -f "$conda_init" && -x "$environment_root/bin/python" ]] || {
    echo 'Missing LIBERO host Conda environment; see docs/SETUP.md.' >&2; exit 2;
}
# Activate the mapped host environment (rax_libero on this machine).
source "$conda_init"
conda activate "$environment_root"
set -u
PYTHON="${RAX_PYTHON:-$environment_root/bin/python}"

[[ -x "$PYTHON" ]] || { echo "Missing host Python: $PYTHON" >&2; exit 2; }
cd "$PROJECT_ROOT"
exec "$PYTHON" -m services.dashboard.server --project-root "$PROJECT_ROOT" --port 8765 "$@"
