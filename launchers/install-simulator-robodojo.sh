#!/usr/bin/env bash
# Resume the official 5.1 install, or the isolated experimental 6.0.1 install.
set -eo pipefail
accept_eula=0
with_assets=0
isaac6=0
for arg in "$@"; do
    case "$arg" in
        --accept-nvidia-eula) accept_eula=1 ;;
        --with-assets) with_assets=1 ;;
        --isaac6) isaac6=1 ;;
        *) echo "Unknown argument: $arg" >&2; exit 2 ;;
    esac
done
if [[ "$accept_eula" != 1 ]]; then
    echo 'This installs Isaac Sim, PyTorch (CUDA 12.8), Isaac Lab and cuRobo.' >&2
    echo 'Review the NVIDIA Isaac Sim EULA before accepting:' >&2
    echo 'https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html' >&2
    echo 'Usage: bash install-simulator-robodojo.sh --accept-nvidia-eula [--with-assets] [--isaac6]' >&2
    exit 2
fi
environment=rax_robodojo
checkout=/home/dodo/code/rax/robodojo-behavior/native
if [[ "$isaac6" == 1 ]]; then
    environment=rax_robodojo_isaac6
    checkout=/home/dodo/code/rax/robodojo-behavior/isaac6
    echo 'Using the independent, experimental Isaac Sim 6.0.1 environment.'
fi
source /home/dodo/system/miniconda3/etc/profile.d/conda.sh
conda activate "$environment"
# RoboDojo uses --size to bound sandbox scratch space; Ubuntu 22.04's bwrap is too old.
if ! bwrap --help 2>&1 | grep -q -- '--size'; then
    conda install -n "$environment" --override-channels -c conda-forge --freeze-installed 'bubblewrap=0.11.2' -y
fi
export ROBODOJO_ENV_ROOT="$CONDA_PREFIX"
export ROBODOJO_PYTHON="$CONDA_PREFIX/bin/python"
export CUDA_HOME="$CONDA_PREFIX" CUDA_PATH="$CONDA_PREFIX"
export PYTHONNOUSERSITE=1
source "$checkout/scripts/robodojo_env.sh"
set -u
cd "$ROBODOJO_PROJECT_ROOT"
mkdir -p runtime/wheels
export PIP_FIND_LINKS="$PWD/runtime/wheels"
# pip can prefer remote links over --find-links for the same version. Point
# cached Isaac Sim packages at their exact local wheels to avoid downloading again.
if [[ -z "${PIP_CONSTRAINT:-}" ]]; then
    "$ROBODOJO_PYTHON" - "$isaac6" <<'PY'
from pathlib import Path
import sys
runtime = Path('runtime').resolve()
patterns = ('isaacsim*.whl', 'cuda_core-0.7.0-*.whl', 'cuda_bindings-12.9.8-*.whl',
            'nvidia_cuda_nvcc_cu12-12.8.61-*.whl', 'nvidia_nvfatbin_cu12-12.8.55-*.whl',
            'viser-0.2.11-*.whl')
if sys.argv[1] == '1':
    patterns = ('*.whl',)
wheels = [p for pattern in patterns for p in sorted((runtime / 'wheels').glob(pattern))
          if not Path(str(p) + '.aria2').exists() and not p.with_suffix('.range-download').exists()]
lines = [f"{p.name.split('-')[0].replace('_', '-')} @ {p.as_uri()}" for p in wheels]
if sys.argv[1] == '1':
    wheelhouse = runtime / 'wheelhouse'
    wheelhouse.mkdir(exist_ok=True)
    for p in wheels:
        link = wheelhouse / p.name
        if not link.exists():
            link.symlink_to(p)
    (runtime / 'local-wheel-constraints.txt').write_text('\n'.join(lines) + '\n')
    sys.exit(0)
# Match Isaac Sim's packaging/typing pins and keep cuRobo on CUDA 12.
lines += ['pytest<9', 'cuda-core==0.7.0', 'cuda-bindings==12.9.8',
          'nvidia-cuda-nvcc-cu12==12.8.61', 'nvidia-nvfatbin-cu12==12.8.55',
          'setuptools-scm==10.2.1', 'vcs-versioning==2.2.2',
          'viser==0.2.11', 'tyro==0.9.17', 'typeguard==4.4.2', 'chardet<6']
(runtime / 'local-wheel-constraints.txt').write_text('\n'.join(lines) + '\n')
PY
    export PIP_CONSTRAINT="$PWD/runtime/local-wheel-constraints.txt"
fi
if [[ "$isaac6" == 1 ]]; then
    # This directory only links completed wheels; raw downloads may be partial.
    export PIP_FIND_LINKS="$PWD/runtime/wheelhouse"
fi
bash scripts/bootstrap_sources.sh
bash scripts/setup_robodojo_env.sh --accept-nvidia-eula
if [[ "$with_assets" == 1 ]]; then
    GIT_LFS_SKIP_SMUDGE=1 bash scripts/setup_assets.sh
    # Upstream checks only directory existence. Also finish any partial LFS files.
    git -C "$ROBODOJO_RUNTIME_ROOT/robodojo-cache/robodojo_assets_repo" \
        lfs pull --include='Assets/**' --exclude=''
fi
