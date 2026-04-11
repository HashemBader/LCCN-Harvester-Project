"""Configurable Help-page link targets and resolvers.

The constants below are intentionally easy to find and edit:

- Use a normal web URL like ``https://example.com/help`` to open an external page.
- Use ``repo:docs/user_guide.md`` to open the repository-hosted document in the
  browser. When a Git checkout is present, the app derives the current fork and
  branch from ``origin`` and ``HEAD`` so downstream forks point at their own docs.
- Use a plain repo-relative path like ``docs/user_guide.md`` only if you
  explicitly want local-file behaviour.
"""

from __future__ import annotations

import configparser
from pathlib import Path
from urllib.parse import urlparse

from .app_paths import get_app_root, get_bundle_root

# Client-editable Help-page destinations. Use ``repo:...`` to force a browser page.
SUPPORT_GUIDANCE_URL = "repo:docs/README.md"
USER_GUIDE_URL = "repo:docs/user_guide.md"
ACCESSIBILITY_STATEMENT_URL = "repo:docs/wcag.md"
REPOSITORY_WEB_URL = "https://github.com/HashemBader/LCCN-Harvester-Project"
REPOSITORY_DEFAULT_REF = "main"


def _git_dir_from_root(root: Path) -> Path | None:
    """Return the Git metadata directory for *root*, if available."""
    git_entry = root / ".git"
    if git_entry.is_dir():
        return git_entry
    if not git_entry.is_file():
        return None

    try:
        text = git_entry.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    prefix = "gitdir:"
    if not text.lower().startswith(prefix):
        return None

    raw_path = text[len(prefix):].strip()
    git_dir = Path(raw_path)
    if not git_dir.is_absolute():
        git_dir = (root / git_dir).resolve()
    return git_dir


def _normalize_repository_web_url(remote_url: str) -> str | None:
    """Convert a Git remote URL into a browser-friendly repository URL."""
    remote_url = remote_url.strip()
    if not remote_url:
        return None

    if remote_url.startswith("git@"):
        host_and_path = remote_url[4:]
        if ":" not in host_and_path:
            return None
        host, repo_path = host_and_path.split(":", 1)
        return f"https://{host}/{repo_path.removesuffix('.git')}".rstrip("/")

    parsed = urlparse(remote_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return remote_url.removesuffix(".git").rstrip("/")

    if parsed.scheme == "ssh" and parsed.hostname and parsed.path:
        clean_path = parsed.path.lstrip("/").removesuffix(".git")
        return f"https://{parsed.hostname}/{clean_path}".rstrip("/")

    return None


def _detect_repository_web_url() -> str | None:
    """Return the current checkout's browser repository URL, if discoverable."""
    root = get_app_root()
    git_dir = _git_dir_from_root(root)
    if git_dir is None:
        return None

    config_path = git_dir / "config"
    if not config_path.exists():
        return None

    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except (configparser.Error, OSError):
        return None

    section = 'remote "origin"'
    if not parser.has_section(section):
        return None
    remote_url = parser.get(section, "url", fallback="").strip()
    return _normalize_repository_web_url(remote_url)


def _detect_repository_ref() -> str | None:
    """Return the current branch name from Git metadata, if available."""
    root = get_app_root()
    git_dir = _git_dir_from_root(root)
    if git_dir is None:
        return None

    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    prefix = "ref: refs/heads/"
    if head.startswith(prefix):
        return head[len(prefix):]
    return None


def build_repository_file_url(repo_relative_path: str) -> str:
    """Return a browser URL for a repository-hosted file."""
    repo_base = _detect_repository_web_url() or REPOSITORY_WEB_URL
    repo_ref = _detect_repository_ref() or REPOSITORY_DEFAULT_REF
    clean_path = repo_relative_path.lstrip("/")
    return f"{repo_base}/blob/{repo_ref}/{clean_path}"


def resolve_help_link_target(target: str) -> Path | str | None:
    """Resolve a Help-page target into either a URL string or a local file path."""
    parsed = urlparse(target)
    if parsed.scheme and parsed.netloc:
        return target
    if target.startswith("repo:"):
        return build_repository_file_url(target[len("repo:"):])

    normalized = Path(target)
    search_roots: list[Path] = []
    for root in (get_app_root(), get_bundle_root()):
        if root not in search_roots:
            search_roots.append(root)

    for root in search_roots:
        candidate = (root / normalized).resolve()
        if candidate.exists():
            return candidate

    return None
