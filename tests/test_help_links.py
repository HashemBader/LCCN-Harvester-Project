from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from src.config import help_links
from src.gui.help_tab import HelpTab


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def help_tab(qapp):
    tab = HelpTab()
    tab.show()
    qapp.processEvents()
    yield tab
    tab.close()


def test_resolve_help_link_target_builds_repo_url_from_detected_remote_and_branch(monkeypatch):
    monkeypatch.setattr(help_links, "_detect_repository_web_url", lambda: "https://github.com/example/fork")
    monkeypatch.setattr(help_links, "_detect_repository_ref", lambda: "client-docs")

    assert help_links.resolve_help_link_target("repo:docs/user_guide.md") == (
        "https://github.com/example/fork/blob/client-docs/docs/user_guide.md"
    )


def test_resolve_help_link_target_prefers_live_repo_file_for_plain_relative_path(monkeypatch, tmp_path):
    workspace_root = tmp_path / "workspace"
    bundle_root = tmp_path / "bundle"
    workspace_root.mkdir()
    bundle_root.mkdir()

    live_doc = workspace_root / "docs" / "user_guide.md"
    live_doc.parent.mkdir(parents=True)
    live_doc.write_text("# Live user guide\n", encoding="utf-8")

    bundled_doc = bundle_root / "docs" / "user_guide.md"
    bundled_doc.parent.mkdir(parents=True)
    bundled_doc.write_text("# Bundled user guide\n", encoding="utf-8")

    monkeypatch.setattr(help_links, "get_app_root", lambda: workspace_root)
    monkeypatch.setattr(help_links, "get_bundle_root", lambda: bundle_root)

    assert help_links.resolve_help_link_target("docs/user_guide.md") == live_doc.resolve()


def test_resolve_help_link_target_accepts_external_url():
    url = "https://example.com/help"
    assert help_links.resolve_help_link_target(url) == url


def test_resolve_help_link_target_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(help_links, "get_app_root", lambda: tmp_path / "workspace")
    monkeypatch.setattr(help_links, "get_bundle_root", lambda: tmp_path / "bundle")

    assert help_links.resolve_help_link_target("docs/missing.md") is None


def test_user_guide_button_opens_resolved_target(help_tab, monkeypatch):
    opened = {}

    def fake_open_url(url):
        opened["url"] = url.toString()
        return True

    guide = "https://github.com/example/fork/blob/main/docs/user_guide.md"

    monkeypatch.setattr("src.gui.help_tab.USER_GUIDE_URL", "repo:docs/user_guide.md")
    monkeypatch.setattr("src.gui.help_tab.resolve_help_link_target", lambda _target: guide)
    monkeypatch.setattr("src.gui.help_tab.QDesktopServices.openUrl", fake_open_url)

    help_tab.btn_user_guide.click()

    assert opened["url"] == guide


def test_accessibility_button_opens_resolved_target(help_tab, monkeypatch):
    opened = {}

    def fake_open_url(url):
        opened["url"] = url.toString()
        return True

    statement = "https://github.com/example/fork/blob/main/docs/wcag.md"

    monkeypatch.setattr("src.gui.help_tab.ACCESSIBILITY_STATEMENT_URL", "repo:docs/wcag.md")
    monkeypatch.setattr("src.gui.help_tab.resolve_help_link_target", lambda _target: statement)
    monkeypatch.setattr("src.gui.help_tab.QDesktopServices.openUrl", fake_open_url)

    help_tab.btn_view_accessibility_statement.click()

    assert opened["url"] == statement


def test_support_button_warns_when_target_missing(help_tab, monkeypatch):
    warnings = []

    def fake_warning(_parent, title, text):
        warnings.append((title, text))

    monkeypatch.setattr("src.gui.help_tab.SUPPORT_GUIDANCE_URL", "docs/missing.md")
    monkeypatch.setattr("src.gui.help_tab.resolve_help_link_target", lambda _target: None)
    monkeypatch.setattr("src.gui.help_tab.QMessageBox.warning", fake_warning)

    help_tab.btn_support_guidance.click()

    assert warnings == [
        ("Link Not Available", "Could not find the configured support & guidance target:\ndocs/missing.md")
    ]
