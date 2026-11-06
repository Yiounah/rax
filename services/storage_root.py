"""The fast storage tier that must hold session artifacts.

RAX_ARTIFACT_ROOT selects it explicitly. An operator can alternatively persist an
absolute path in runtime/operator/artifact-root. Otherwise use the repository's
runtime link. Environment and simulator data paths remain independent of this setting.
"""
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ENVIRONMENT = "RAX_ARTIFACT_ROOT"


def artifact_root() -> Path:
    configured = os.environ.get(ENVIRONMENT)
    if configured:
        return Path(configured).resolve()
    runtime = PROJECT / "runtime"
    pointer = runtime / "operator" / "artifact-root"
    try:
        configured = pointer.read_text().strip()
    except FileNotFoundError:
        configured = None
    except OSError as exc:
        raise RuntimeError(f"Cannot read artifact-root configuration {pointer}: {exc}") from exc
    if configured is not None:
        if not configured or not Path(configured).is_absolute():
            raise RuntimeError(f"{pointer} must contain a nonempty absolute directory path")
        return Path(configured).resolve()
    if runtime.exists():
        return runtime.resolve()
    raise RuntimeError(
        f"No artifact root: set {ENVIRONMENT} or create a 'runtime' symlink in {PROJECT}"
    )


def require_artifact_path(path, what="Controller artifacts") -> Path:
    path = Path(path).resolve()
    root = artifact_root()
    if not path.is_relative_to(root):
        raise ValueError(f"{what} must be under {root} (set {ENVIRONMENT} to change it)")
    return path
