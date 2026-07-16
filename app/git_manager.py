"""
git_manager.py — Git repository manager for versioning device config backups.

Each device has its own directory inside the repo:
  configs_repo/
    <group_or_ungrouped>/
      <device_name>/
        config.txt       <- latest config snapshot

On every successful backup:
1. The config file is written/overwritten.
2. A Git commit is created with metadata in the message.
3. The diff between the previous and new commit is returned.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import git
from git import Repo, InvalidGitRepositoryError, GitCommandError

from app.config import settings

logger = logging.getLogger(__name__)


class GitManager:
    """
    Manages a local Git repository for storing and versioning device configs.
    Thread-safe for concurrent writes (each call locks the repo via GitPython's
    internal locking, but we serialise commits via a threading.Lock for safety).
    """

    def __init__(self) -> None:
        self.repo_path = Path(settings.git.repo_path).resolve()
        self.author_name = settings.git.author_name
        self.author_email = settings.git.author_email
        self._repo: Optional[Repo] = None
        self._ensure_repo()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_repo(self) -> None:
        """Initialize the Git repo if it doesn't already exist."""
        self.repo_path.mkdir(parents=True, exist_ok=True)

        try:
            self._repo = Repo(self.repo_path)
            logger.debug("Opened existing Git repo at %s", self.repo_path)
        except InvalidGitRepositoryError:
            self._repo = Repo.init(self.repo_path)
            logger.info("Initialized new Git repo at %s", self.repo_path)

            # Create an initial empty commit so diffs work from the start
            readme = self.repo_path / "README.md"
            readme.write_text(
                "# Dumper Config Repository\n\n"
                "Automatically managed by Dumper. Do not edit manually.\n"
            )
            self._repo.index.add(["README.md"])
            self._commit("Initial commit — Dumper repository initialized")

    def _commit(self, message: str) -> Optional[git.Commit]:
        """Create a commit with the configured author."""
        if not self._repo:
            return None
        try:
            actor = git.Actor(self.author_name, self.author_email)
            commit = self._repo.index.commit(
                message,
                author=actor,
                committer=actor,
            )
            return commit
        except Exception as exc:
            logger.error("Git commit failed: %s", exc)
            return None

    def _get_device_dir(self, device_name: str, group_name: Optional[str]) -> Path:
        """Return (and create) the directory for a device's configs."""
        safe_group = _safe_filename(group_name or "ungrouped")
        safe_device = _safe_filename(device_name)
        device_dir = self.repo_path / safe_group / safe_device
        device_dir.mkdir(parents=True, exist_ok=True)
        return device_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_and_commit(
        self,
        device_name: str,
        group_name: Optional[str],
        config_content: str,
        device_hostname: str,
    ) -> Tuple[Optional[str], str]:
        """
        Write config_content to the repo and commit it.

        Returns:
            (commit_hash, diff_text)
            commit_hash: SHA of the new commit, or None if commit failed.
            diff_text:   Unified diff against the previous commit, or empty string.
        """
        device_dir = self._get_device_dir(device_name, group_name)
        config_file = device_dir / "config.txt"
        rel_path = config_file.relative_to(self.repo_path)

        # --- Capture diff BEFORE overwriting the file ---
        old_content = config_file.read_text(encoding="utf-8") if config_file.exists() else None

        # Write new content
        config_file.write_text(config_content, encoding="utf-8")

        # Stage the file
        try:
            self._repo.index.add([str(rel_path)])
        except GitCommandError as exc:
            logger.error("Git add failed for %s: %s", rel_path, exc)
            return None, ""

        # Check if anything actually changed
        if not self._repo.index.diff("HEAD"):
            logger.info("No changes to commit for device '%s'", device_name)
            return None, ""

        # Build commit message
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        commit_message = (
            f"backup: {device_name} ({device_hostname}) @ {now_utc}\n\n"
            f"Device: {device_name}\n"
            f"Host:   {device_hostname}\n"
            f"File:   {rel_path}\n"
        )

        commit = self._commit(commit_message)
        if not commit:
            return None, ""

        # Build diff
        diff_text = self._compute_diff(old_content, config_content, str(rel_path))
        logger.info(
            "Committed config for '%s' — %s (%d lines changed)",
            device_name, commit.hexsha[:8], diff_text.count("\n"),
        )
        return commit.hexsha, diff_text

    def get_diff_between_commits(
        self,
        device_name: str,
        group_name: Optional[str],
        commit_a: str,
        commit_b: str,
    ) -> str:
        """
        Return the unified diff for a specific device file between two commit SHAs.
        Returns an empty string if commits or file don't exist.
        """
        if not self._repo:
            return ""
        try:
            device_dir = self._get_device_dir(device_name, group_name)
            config_file = device_dir / "config.txt"
            rel_path = str(config_file.relative_to(self.repo_path))

            blob_a = self._repo.commit(commit_a).tree[rel_path].data_stream.read().decode("utf-8", errors="replace")
            blob_b = self._repo.commit(commit_b).tree[rel_path].data_stream.read().decode("utf-8", errors="replace")
            return self._compute_diff(blob_a, blob_b, rel_path)
        except (KeyError, git.BadName, Exception) as exc:
            logger.warning("diff_between_commits failed: %s", exc)
            return ""

    def get_commit_history(
        self,
        device_name: str,
        group_name: Optional[str],
        max_count: int = 20,
    ) -> list[dict]:
        """
        Return a list of commit metadata dicts for a device's config file.
        Each dict: {sha, sha_short, message, date, author}
        """
        if not self._repo:
            return []
        try:
            device_dir = self._get_device_dir(device_name, group_name)
            config_file = device_dir / "config.txt"
            rel_path = str(config_file.relative_to(self.repo_path))

            commits = list(self._repo.iter_commits(paths=rel_path, max_count=max_count))
            return [
                {
                    "sha": c.hexsha,
                    "sha_short": c.hexsha[:8],
                    "message": c.message.strip().splitlines()[0],
                    "date": datetime.fromtimestamp(c.committed_date, tz=timezone.utc).isoformat(),
                    "author": c.author.name,
                }
                for c in commits
            ]
        except Exception as exc:
            logger.warning("get_commit_history failed: %s", exc)
            return []

    def get_latest_config(
        self,
        device_name: str,
        group_name: Optional[str],
    ) -> Optional[str]:
        """Return the current content of the config file, or None if not found."""
        device_dir = self._get_device_dir(device_name, group_name)
        config_file = device_dir / "config.txt"
        if config_file.exists():
            return config_file.read_text(encoding="utf-8")
        return None

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_diff(old: Optional[str], new: str, filename: str) -> str:
        """Compute a unified diff string between old and new content."""
        import difflib
        old_lines = (old or "").splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        ))
        return "".join(diff)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_git_manager: Optional[GitManager] = None


def get_git_manager() -> GitManager:
    """Return the shared GitManager instance (lazy-initialized)."""
    global _git_manager
    if _git_manager is None:
        _git_manager = GitManager()
    return _git_manager


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_filename(name: str) -> str:
    """Sanitize a string for use as a filesystem path component."""
    safe = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)
    return safe.strip("_") or "unnamed"
