# Local Isaac Sim 6 compatibility environment

This checkout uses the personal `yuna_robodojo-behavior/native` branch in
[`Yiounah/rax`](https://github.com/Yiounah/rax/tree/yuna_robodojo-behavior/native).
It contains the experimental Isaac Sim 6 migration. RoboDojo upstream
validates Isaac Sim 5.1 only; see [upstream issue 24](https://github.com/RoboDojo-Benchmark/RoboDojo/issues/24).
The original checkout and `rax_robodojo` environment are preserved. The host NVIDIA
595.99.02 driver is unchanged.

## Environment and entry points

| Item | Value |
| --- | --- |
| Checkout | `/home/dodo/code/rax/robodojo-behavior/isaac6` |
| Branch / upstream | `yuna_robodojo-behavior/native` / `origin/yuna_robodojo-behavior/native` |
| Conda environment | `/home/dodo/system/miniconda3/envs/rax_robodojo_isaac6` |
| Python / Isaac Sim | 3.12 / 6.0.1.0 |
| PyTorch / CUDA toolkit | 2.11.0+cu128 / 12.8 |
| NumPy / Warp | 2.3.1 / 1.13.0 |
| Dashboard | loopback port 8767 |
| Simulator concurrency | one exploration environment, one formal worker |

Resume installation with the existing shared installer:

```bash
bash /home/dodo/code/rax/launchers/install-simulator-robodojo.sh --isaac6 --accept-nvidia-eula
```

Start the dashboard:

```bash
bash /home/dodo/code/rax/launchers/start-dashboard-robodojo.sh --isaac6
```

Omitting `--isaac6` selects the original 5.1 environment and dashboard port 8766.
That original simulator currently crashes with the retained 595 driver. LIBERO keeps
its own environment and port 8765.

The three shared launchers are versioned under this checkout's `launchers/` directory;
`/home/dodo/code/rax/launchers/` links to those files. They retain this machine's
absolute Conda and checkout paths. Continue editing and committing in this checkout;
its directory name remains `isaac6` even though its Git branch has changed.

The environment preloads its own `libstdc++.so.6` only while activated. Its sandbox
environment mapping lives outside the checkout at
`/home/dodo/system/miniconda3/rax-runtime-envs/robodojo-isaac6`.

## Assets and download state

Both checkouts use the same pinned asset repository. Actual asset files live at:

```text
/home/dodo/code/rax/robodojo-behavior/native/.local-runtime/robodojo-cache/robodojo_assets_repo/Assets
```

The complete `Assets/` tree is 38.44 GiB. The Hugging Face repository contains other,
much larger datasets that are not part of this download. `RoboDojo/Assets` in each
checkout links to this tree. No second asset copy is needed for the 6.x environment.

Full asset download progress and file-verification status are recorded in the original
checkout's `runtime/checks/assets-progress.json`. The local downloader verifies actual
file sizes and SHA-256 hashes against the pinned LFS manifest; directory existence
alone does not establish completeness. Assets for the `make_kong` smoke check were
downloaded and verified separately.

Isaac Sim also requires its extension caches. A Python-package-only install cannot
start the standard 6.0.1 experience because some schema extensions are absent from
the runtime registries; see [NVIDIA issue 679](https://github.com/isaac-sim/IsaacSim/issues/679).
The shared installer installs `isaacsim[all,extscache]` by default.

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
conda activate rax_robodojo_isaac6
cd /home/dodo/code/rax/robodojo-behavior/isaac6
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

All four source patches replay successfully from the pinned source commits and
reproduce the installed files; rerunning source bootstrap is idempotent. The original
5.1 checkout and IsaacLab sources remain unchanged by the 6.x migration.

This establishes the tested rigid-body task's rendering and control path. It does
not establish equal benchmark scores or compatibility of every task on 6.x. The
full shared asset download is still running; the 366 files needed by this smoke
check are verified complete. Consult `assets-progress.json` for live full-download
status before running other tasks.
