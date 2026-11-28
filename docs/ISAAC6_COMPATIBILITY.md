# Local Isaac Sim 6 compatibility environment

This checkout uses the personal `yuna_robodojo-behavior/native` branch in
[`Yiounah/rax`](https://github.com/Yiounah/rax/tree/yuna_robodojo-behavior/native).
It contains the experimental Isaac Sim 6 migration. RoboDojo upstream
validates Isaac Sim 5.1 only; see [upstream issue 24](https://github.com/RoboDojo-Benchmark/RoboDojo/issues/24).
Code, Git metadata, assets and runtime storage now live in one checkout, `native`.
At the user's request, the old Isaac Sim 5.1 environment was removed on 2026-11-25 and the retained
Isaac Sim 6 environment was renamed to `rax_robodojo`. This name now refers to
Isaac Sim 6.0.1. The host NVIDIA 595.99.02 driver is unchanged.

## Environment and entry points

| Item | Value |
| --- | --- |
| Checkout | `/home/dodo/code/rax/robodojo-behavior/native` |
| Branch / upstream | `yuna_robodojo-behavior/native` / `origin/yuna_robodojo-behavior/native` |
| Conda environment | `/home/dodo/system/miniconda3/envs/rax_robodojo` |
| Python / Isaac Sim | 3.12 / 6.0.1.0 |
| PyTorch / CUDA toolkit | 2.11.0+cu128 / 12.8 |
| NumPy / Warp | 2.3.1 / 1.13.0 |
| Dashboard | loopback port 8767 |
| Simulator concurrency | one exploration environment, one formal worker |

Start the dashboard with this checkout's launcher:

```bash
cd /home/dodo/code/rax/robodojo-behavior/native
bash scripts/run_operator_dashboard.sh
```

It activates the retained 6.0.1 environment automatically; `--isaac6` remains an
optional compatibility alias. The dashboard uses port 8767. LIBERO's launcher
lives at `/home/dodo/code/rax/libero-pro/native/scripts/run_operator_dashboard.sh`,
using its own environment and port 8765.

Each checkout uses `scripts/run_operator_dashboard.sh` as its only dashboard entry
point. The additional `launchers/` directories, top-level shortcuts and the
completed-installation wrapper were removed at the user's request.
Continue editing and committing RoboDojo in `native` on
`yuna_robodojo-behavior/native`. The temporary `isaac6` worktree has been retired.

The simulator and assets are installed. If the environment needs rebuilding,
the underlying setup scripts remain available:

```bash
cd /home/dodo/code/rax/robodojo-behavior/native
bash scripts/bootstrap_sources.sh
bash scripts/setup_robodojo_env.sh --accept-nvidia-eula
```

`scripts/setup_assets.sh` manages the pinned asset checkout separately. Keep the
existing asset cache; do not download another copy for normal dashboard use.

The environment preloads its own `libstdc++.so.6` only while activated. Its sandbox
environment mapping lives outside the checkout at
`/home/dodo/system/miniconda3/rax-runtime-envs/robodojo-native`.

Environment-local Bash hooks set `CUDA_HOME` and `CUDA_PATH` to the active Conda
prefix and restore their previous values on deactivation. The environment setup deploys
these hooks through `scripts/setup_robodojo_cuda.sh`; keep these two variables out
of `conda env config vars` so activation does not conflict with the system CUDA
settings in `.bashrc`.

The local Codex model profile lives in `runtime/operator/codex-provider/` and is
selected by `scripts/start_auto_research_agent.sh`. It references the existing
ChatGPT login at `/home/dodo/.codex/auth.json`; credentials are not copied into
the repository. Explicit `--provider-home` and `--profile` flags override this
checkout's defaults. New sessions use native model vision by default
(`--external-perception off`), so a ChatGPT login does not also require an
OpenRouter key for the optional Gemini tool. Enable that tool with
`--external-perception on` only after configuring its separate OpenRouter key.

## Assets and download state

The retained environment uses the original pinned asset repository. Actual asset files live at:

```text
/home/dodo/code/rax/robodojo-behavior/native/.local-runtime/robodojo-cache/robodojo_assets_repo/Assets
```

The complete `Assets/` tree is 38.44 GiB. The Hugging Face repository contains other,
much larger datasets that are not part of this download. `RoboDojo/Assets` links to
this tree. Consolidating the directories does not move or duplicate these assets.

Full asset download progress and file-verification status are recorded in
`runtime/checks/assets-progress.json`. The local downloader verifies actual
file sizes and SHA-256 hashes against the pinned LFS manifest; directory existence
alone does not establish completeness. On 2026-11-28 the progress report shows
all 15,365 files complete, with no failures. The downloader uses
`rax_robodojo`; its progress survives retiring the old environment.
Assets for the `make_kong` smoke check were
downloaded and verified separately.

Isaac Sim also requires its extension caches. A Python-package-only install cannot
start the standard 6.0.1 experience because some schema extensions are absent from
the runtime registries; see [NVIDIA issue 679](https://github.com/isaac-sim/IsaacSim/issues/679).
`scripts/setup_robodojo_env.sh` installs `isaacsim[all,extscache]` by default.

## Compatibility changes

`scripts/bootstrap_sources.sh` applies `patches/robodojo-isaac6.patch` and
`patches/isaaclab-isaac6.patch` to the pinned RoboDojo and IsaacLab sources, with
checksums in `dependencies.lock`:

- Keep the fork's Torch tensors, WXYZ quaternions and legacy Core API integration.
- Match NumPy, Pillow and packaging to the Isaac Sim 6.0.1 runtime.
- Use `dex-retargeting` 0.5.0, whose requirements support NumPy 2.
- Remove the unavailable asset-browser extension and use the bundled Python 3.12
  URDF importer instead of pinning the 5.1 binary.
- Select the Kit 110 extension registry and a 6.0.1 application namespace, keeping
  the original application's settings and logs separate.
- Use `omni.physics.tensors.api` and `omni.physx.get_physx_interface`, replacing
  removed module paths and entry points.
- Check for legacy soft-body schemas before using them in generic material binding.
  Defer legacy soft-body type annotations so rigid assets can load; explicitly reject
  constructing the old `DeformableObject` on 6.x instead of silently aliasing its API.

The installer uses the patched editable packages directly. Running the fork's
`isaaclab.sh --install` would reinstall older Torch/runtime pins and should be avoided.
BEHAVIOR-1K retains separate 5.1 / Torch 2.7 / NumPy 1.26 pins. Its simulator was not
migrated by this work. The old IsaacLab deformable-object API is not supported.
This branch does not establish compatibility of the old URDF conversion code,
XR teleoperation, or all IsaacLab examples with 6.x; RoboDojo loads its existing USD
assets directly.

## Verification

Static installation checks:

```bash
source /home/dodo/system/miniconda3/etc/profile.d/conda.sh
conda activate rax_robodojo
cd /home/dodo/code/rax/robodojo-behavior/native
bash scripts/robodojo_doctor.sh
```

Real simulator check, without model API calls:

```bash
bash scripts/check_isaac6_compatibility.sh
```

It checks three RGB-D cameras, measured movement of a robot joint, agreement between
URDF FK and measured end-effector poses, and cuRobo planning and execution. Reports
and images are saved under `runtime/integration-tests/robodojo-smoke-*`; a successful
report is also written to `runtime/checks/isaac6-smoke-report.json`.

Current verification state is recorded in `runtime/checks/migration-status.json`.
Python dependency consistency, Torch GPU matrix operations, dashboard startup and
authentication passed. Standalone cuRobo GPU warmup and X5 trajectory planning also
passed (21 samples, six arm joints, endpoint position error below 0.001 mm).
Non-GPU tests: 1152 passed, 10 skipped, 8 deselected, and two
failures also present in the original environment: the sandbox test assumes `/home`
does not exist despite the Conda installation being below it, and the workspace
golden for `transfer-handoff/SKILL.md` differs from the pinned source.

The full extension caches are installed. A real Isaac Sim GPU startup, render loop
and shutdown passed with driver 595.99.02 (`runtime/logs/isaacsim6-gpu-smoke-full.log`).
The task-level check passed on 2026-11-25 (`runtime/logs/robodojo6-smoke-assets.log`):

- `make_kong`, seed 0, saved layout collection 0, one simulator, 24 control steps.
- Three 640 × 480 RGB-D cameras, each with 307,200 valid depth pixels. Saved RGB
  images were also visually inspected.
- Actual joint movement, with tracking error below 0.000001 radians.
- Both arms' measured end-effector poses agree with URDF FK within 0.0002 mm.
- cuRobo planned and executed six control blocks; measured final position error
  was 0.0087 mm and rotation error was below 0.0001 radians.
- The simulator shut down cleanly. No model API calls were made.

After renaming the retained environment to `rax_robodojo`, all 321 installed Python
package versions were unchanged. Dependency checks, both dashboard entry modes and
the full 24-step robot check passed again using the new environment path
(`runtime/logs/robodojo6-smoke-renamed.log`). Conda activation variables and the
external sandbox environment mapping point to the new prefix.

All four source patches replay successfully from the pinned source commits and
reproduce the installed files; rerunning source bootstrap is idempotent. During
consolidation, these patches were applied to the existing sources in `native` and
all six editable packages were reinstalled from that location. The active runtime
and wheel cache were merged into `native/.local-runtime`; superseded files are kept
under `runtime/archive/isaac5`.

The consolidated `native` checkout passed the full 24-step RGB-D, joint, FK and
cuRobo check (`runtime/logs/robodojo6-smoke-consolidated.log`). After removing the
temporary worktree, all editable-package imports and both dashboard entry modes
were checked again. Only `native` remains under `robodojo-behavior/`.

This establishes the tested rigid-body task's rendering and control path. It does
not establish equal benchmark scores or compatibility of every task on 6.x. The
full shared asset download is still running; the 366 files needed by this smoke
check are verified complete. Consult `assets-progress.json` for live full-download
status before running other tasks.
