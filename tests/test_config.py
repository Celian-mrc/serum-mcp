from __future__ import annotations

import pytest

from serum_mcp import config


def test_env_var_used_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_VAR, str(tmp_path))
    assert config.get_presets_dir() == tmp_path


def test_env_var_pointing_to_missing_dir_raises(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_VAR, str(tmp_path / "does-not-exist"))
    with pytest.raises(config.PresetsFolderNotFoundError):
        config.get_presets_dir()


def test_missing_everything_raises(monkeypatch):
    monkeypatch.delenv(config.ENV_VAR, raising=False)
    monkeypatch.setattr(
        config.Path, "home", staticmethod(lambda: config.Path("/nonexistent-home-xyz"))
    )
    with pytest.raises(config.PresetsFolderNotFoundError):
        config.get_presets_dir()
