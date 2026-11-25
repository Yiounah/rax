#!/usr/bin/env bash
# Experimental Isaac Sim 6.0.1 environment; keeps the upstream 5.1 environment separate.
# Usage: bash scripts/setup_robodojo_env.sh --accept-nvidia-eula
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/robodojo_env.sh"
source "$ROBODOJO_PROJECT_ROOT/dependencies.lock"
[[ "${1:-}" == --accept-nvidia-eula ]] || {
    echo 'Pass --accept-nvidia-eula to accept the NVIDIA Isaac Sim EULA.' >&2; exit 2;
}
[[ "$(git -C "$ROBODOJO_SOURCE" rev-parse HEAD)" == "$ROBODOJO_COMMIT" ]] || {
    echo 'Run scripts/bootstrap_sources.sh first.' >&2; exit 1;
}
if git -C "$ROBODOJO_SOURCE" submodule status | grep -q '^[-+U]'; then
    echo 'RoboDojo submodules are missing or off their pinned commits.' >&2; exit 1
fi

MINIFORGE="$ROBODOJO_RUNTIME_ROOT/miniforge3"
CONDA="$MINIFORGE/bin/conda"
[[ -x "$CONDA" ]] || { echo 'Link runtime/miniforge3 to the existing Conda installation first.' >&2; exit 1; }
if [[ ! -x "$ROBODOJO_PYTHON" ]]; then
    "$CONDA" create -y -p "$ROBODOJO_ENV_ROOT" --override-channels -c conda-forge python=3.12 pip
fi
if [[ ! -x "$ROBODOJO_ENV_ROOT/bin/nvcc" || ! -x "$ROBODOJO_ENV_ROOT/bin/bwrap" ]]; then
    "$CONDA" install -y -p "$ROBODOJO_ENV_ROOT" --override-channels \
        -c nvidia/label/cuda-12.8.0 -c conda-forge --freeze-installed \
        'cuda-nvcc=12.8.61' 'gxx_linux-64=13' 'libstdcxx-ng>=13' \
        ninja 'bubblewrap=0.11.2' git-lfs ffmpeg
fi
set +euo pipefail
source "$MINIFORGE/bin/activate" "$ROBODOJO_ENV_ROOT"
set -euo pipefail
[[ "$(command -v python)" == "$ROBODOJO_PYTHON" ]] || { echo 'Wrong Python environment.' >&2; exit 1; }
python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Isaac Sim 6 requires a separate Python 3.12 environment"'
export CUDA_HOME="$CONDA_PREFIX" CUDA_PATH="$CONDA_PREFIX" PYTHONNOUSERSITE=1 PIP_USER=0
export LD_PRELOAD="$CONDA_PREFIX/lib/libstdc++.so.6"
export OMNI_KIT_ACCEPT_EULA=YES
nvcc -V | grep -q 'release 12.8'

constraints="$SCRIPT_DIR/robodojo_isaac6_constraints.txt"
pip_install() { python -m pip install --constraint "$constraints" "$@"; }
pip_install 'setuptools<82' wheel 'setuptools-scm==10.2.1' toml
pip_install "torch==$TORCH_VERSION" 'torchvision==0.26.0+cu128' 'torchaudio==2.11.0+cu128' \
    --extra-index-url https://download.pytorch.org/whl/cu128
# Some 6.0.1 extensions are absent from the online registry; install the full cache.
pip_install "isaacsim[all,extscache]==$ISAACSIM_VERSION" --extra-index-url https://pypi.nvidia.com
pip_install -r "$ROBODOJO_SOURCE/scripts/requirements.txt"
pip_install scikit-learn 'h5py>=3.16' imageio-ffmpeg msgpack omegaconf pytest
# Keep RoboDojo's IsaacLab fork and its WXYZ/Torch data conventions. Do not run
# isaaclab.sh's installer, which would reinstall the original 5.1/PyTorch pins.
for extension in isaaclab isaaclab_assets isaaclab_tasks isaaclab_rl isaaclab_mimic; do
    pip_install --no-build-isolation -e "$ROBODOJO_SOURCE/third_party/IsaacLab/source/$extension"
done
pip_install --no-build-isolation -e "$ROBODOJO_SOURCE/third_party/curobo[cu12]"
python -m pip check
python - <<PY
import importlib.metadata as metadata
from curobo.motion_planner import MotionPlanner
expected = {'isaacsim': '$ISAACSIM_VERSION', 'torch': '$TORCH_VERSION',
            'numpy': '$NUMPY_VERSION', 'jinja2': '$JINJA2_VERSION'}
for name, want in expected.items():
    actual = metadata.version(name)
    print(f'{name}=={actual}')
    assert actual == want, (name, actual, want)
PY
echo "Experimental environment installed: $ROBODOJO_ENV_ROOT"
echo 'Run the real robot/RGB-D smoke check before treating this migration as usable.'
