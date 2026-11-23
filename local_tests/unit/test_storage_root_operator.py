"""Persistent local artifact storage without relocating environments or task data."""
from pathlib import Path
import pytest
from services import storage_root

def test_operator_artifact_root_and_environment_precedence(tmp_path, monkeypatch):
    project = tmp_path / "project"
    runtime = project / "runtime"
    operator = runtime / "operator"
    operator.mkdir(parents=True)
    monkeypatch.setattr(storage_root, "PROJECT", project)
    monkeypatch.delenv(storage_root.ENVIRONMENT, raising=False)
    assert storage_root.artifact_root() == runtime
    local = tmp_path / "local-artifacts"
    local.mkdir()
    (operator / "artifact-root").write_text(str(local) + "\n")
    assert storage_root.artifact_root() == local
    assert (project / "runtime").resolve() == runtime
    (runtime / "auto-research").symlink_to(local / "auto-research")
    (local / "auto-research" / "trial").mkdir(parents=True)
    assert storage_root.require_artifact_path(runtime / "auto-research" / "trial") == local / "auto-research" / "trial"
    override = tmp_path / "override"
    monkeypatch.setenv(storage_root.ENVIRONMENT, str(override))
    assert storage_root.artifact_root() == override

@pytest.mark.parametrize("value", ["", "relative/path"])
def test_invalid_operator_pointer_is_not_silently_ignored(tmp_path, monkeypatch, value):
    operator = tmp_path / "runtime" / "operator"
    operator.mkdir(parents=True)
    (operator / "artifact-root").write_text(value)
    monkeypatch.setattr(storage_root, "PROJECT", tmp_path)
    monkeypatch.delenv(storage_root.ENVIRONMENT, raising=False)
    with pytest.raises(RuntimeError, match="nonempty absolute"):
        storage_root.artifact_root()
