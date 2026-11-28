# Personal RoboDojo development branch

- Make future RoboDojo changes on `yuna_robodojo-behavior/native`, tracking
  `origin/yuna_robodojo-behavior/native` in `https://github.com/Yiounah/rax`.
- The single local checkout is `/home/dodo/code/rax/robodojo-behavior/native`.
  Use Conda environment `rax_robodojo` (Python 3.12, Isaac Sim 6.0.1).
- Manage `CUDA_HOME` and `CUDA_PATH` with the environment-local Bash hooks
  installed by `scripts/setup_robodojo_cuda.sh`. Keep these keys out of Conda's
  `env_vars` configuration to avoid overwrite warnings; preserve the system CUDA
  defaults in `.bashrc` and restore them when deactivating the environment.
- This checkout's Codex launcher uses the local profile in
  `runtime/operator/codex-provider`, referencing the existing ChatGPT login.
  Preserve this project-specific setup; do not change global provider defaults
  or require an OpenRouter key unless the user selects that service. New sessions
  default to native model vision (`external_perception=false`).
- The user removed the old Isaac Sim 5.1 installation on 2026-11-25, then renamed
  the retained Isaac Sim 6 environment to `rax_robodojo`. This name now refers to
  Isaac Sim 6. Code, Git metadata, assets and runtime storage are consolidated in
  `native`; do not recreate the temporary `isaac6` worktree. Preserve the separate
  LIBERO checkout/environment. Keep NVIDIA driver
  595.99.02; the user explicitly rejected a driver downgrade.
- Keep the pinned RoboDojo and IsaacLab sources. Record changes to these ignored
  checkouts in `patches/`, update SHA-256 values in `dependencies.lock`, and verify
  that `scripts/bootstrap_sources.sh` reproduces the changes.
- Use `scripts/run_operator_dashboard.sh` as the only dashboard entry point in
  each checkout. RoboDojo activates `rax_robodojo` and uses port 8767; LIBERO's
  own script activates `rax_libero` and uses port 8765. `--isaac6` remains a
  compatibility alias. The user requested the official script layout on
  2026-11-28; do not recreate `launchers/` directories, shortcut scripts or the
  completed-installation wrapper. Retain setup tools under `scripts/`.
- Use one exploration environment and one formal worker on the 24 GB GPU.
  Keep runtime files, credentials, environments, downloaded assets and diagnostic
  logs out of Git. The retained environment uses the existing pinned asset directory;
  check the existing asset downloader before starting another writer.
- See `docs/ISAAC6_COMPATIBILITY.md` for paths, migration limitations and validation.
  The real `make_kong` RGB-D/joint/FK/cuRobo smoke test has passed; this does not
  establish compatibility of all tasks or the legacy deformable-object API.
