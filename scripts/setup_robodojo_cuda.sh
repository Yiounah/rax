#!/usr/bin/env bash
# Install environment-local CUDA hooks without changing the user's shell defaults.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target_prefix="$(readlink -f "${1:?Usage: setup_robodojo_cuda.sh CONDA_PREFIX}")"
[[ -d "$target_prefix/conda-meta" && -x "$target_prefix/bin/python" ]] || {
    echo "Not an installed Conda environment: $target_prefix" >&2; exit 1;
}
for phase in activate deactivate; do
    install -D -m 644 "$SCRIPT_DIR/conda/$phase.d/rax-cuda.sh" \
        "$target_prefix/etc/conda/$phase.d/rax-cuda.sh"
done
"$target_prefix/bin/python" - "$target_prefix" <<'PY'
import json
import os
from pathlib import Path
import sys
import tempfile

path = Path(sys.argv[1]) / 'conda-meta/state'
if path.exists():
    state = json.loads(path.read_text())
    variables = state.get('env_vars', {})
    if any(name in variables for name in ('CUDA_HOME', 'CUDA_PATH')):
        # Remove these keys entirely: `conda env config vars unset` leaves sentinels
        # that would unset the values restored by our deactivation hook.
        for name in ('CUDA_HOME', 'CUDA_PATH'):
            variables.pop(name, None)
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
            json.dump(state, f, indent=2)
            f.write('\n')
        os.chmod(f.name, path.stat().st_mode & 0o777)
        os.replace(f.name, path)
PY
