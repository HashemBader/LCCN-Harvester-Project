from pathlib import Path

import src.config.app_paths as app_paths


def test_get_user_data_dir_frozen_macos(monkeypatch, tmp_path):
    monkeypatch.setattr(app_paths, "_IS_FROZEN", True)
    monkeypatch.setattr(app_paths, "_find_local_workspace_root", lambda: None)
    monkeypatch.setattr(app_paths.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(app_paths.Path, "home", staticmethod(lambda: tmp_path))

    path = app_paths.get_user_data_dir()

    assert path == tmp_path / "Library" / "Application Support" / "LCCN Harvester"
    assert path.exists()


def test_get_user_data_dir_frozen_windows(monkeypatch, tmp_path):
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setattr(app_paths, "_IS_FROZEN", True)
    monkeypatch.setattr(app_paths, "_find_local_workspace_root", lambda: None)
    monkeypatch.setattr(app_paths.platform, "system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", str(appdata))

    path = app_paths.get_user_data_dir()

    assert path == appdata / "LCCN Harvester"
    assert path.exists()


def test_get_user_data_dir_frozen_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(app_paths, "_IS_FROZEN", True)
    monkeypatch.setattr(app_paths, "_find_local_workspace_root", lambda: None)
    monkeypatch.setattr(app_paths.platform, "system", lambda: "Linux")
    monkeypatch.setattr(app_paths.Path, "home", staticmethod(lambda: tmp_path))

    path = app_paths.get_user_data_dir()

    assert path == tmp_path / ".lccn_harvester"
    assert path.exists()


def test_get_user_data_dir_prefers_workspace_for_local_frozen_build(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(app_paths, "_IS_FROZEN", True)
    monkeypatch.setattr(app_paths, "_find_local_workspace_root", lambda: workspace)

    assert app_paths.get_user_data_dir() == workspace
