# Personal RoboDojo development branch

- Make future RoboDojo changes on `yuna_robodojo-behavior/native`, tracking
  `origin/yuna_robodojo-behavior/native` in `https://github.com/Yiounah/rax`.
- The local checkout stays at `/home/dodo/code/rax/robodojo-behavior/isaac6`.
  Use Conda environment `rax_robodojo_isaac6` (Python 3.12, Isaac Sim 6.0.1).
- Preserve the original `robodojo-behavior/native` checkout and `rax_robodojo`
  environment, and the separate LIBERO checkout/environment. Keep NVIDIA driver
  595.99.02; the user explicitly rejected a driver downgrade.
- Keep the pinned RoboDojo and IsaacLab sources. Record changes to these ignored
  checkouts in `patches/`, update SHA-256 values in `dependencies.lock`, and verify
  that `scripts/bootstrap_sources.sh` reproduces the changes.
- `launchers/` contains the three shared installation/dashboard entry points.
  `/home/dodo/code/rax/launchers` links to these versioned files. Preserve their
  existing defaults and use `--isaac6` for this environment (dashboard port 8767).
- Use one exploration environment and one formal worker on the 24 GB GPU.
  Keep runtime files, credentials, environments, downloaded assets and diagnostic
  logs out of Git. Both RoboDojo environments share the pinned asset directory;
  check the existing asset downloader before starting another writer.
- See `docs/ISAAC6_COMPATIBILITY.md` for paths, migration limitations and validation.
  The real `make_kong` RGB-D/joint/FK/cuRobo smoke test has passed; this does not
  establish compatibility of all tasks or the legacy deformable-object API.
