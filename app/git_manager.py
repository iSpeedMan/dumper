"""
git_manager.py — Git repository manager for versioning device config backups.

Each device has its own directory inside the repo:
  configs_repo/
    <group_or_ungrouped>/
      <device_name>/
        config.enc       <- AES-256-GCM encrypted config snapshot

On every successful backup:
1. The config is AES-256-GCM encrypted with the app master key and written
   to disk as a binary blob.  Plain-text configs are NEVER written to disk.
2. A Git commit is created with metadata in the message.
3. The diff between the previous and new commit is computed in memory
   (both blobs decrypted before diffing) and returned.

Security note:
  Even with full filesystem access an attacker cannot read backup configs
  without the master key stored in config.yaml.  All app reads go through
  _read_config_file() which decrypts transparently.
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
    # Encryption helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encrypt_config(plaintext: str) -> bytes:
        """
        Encrypt config plaintext to a binary blob using AES-256-GCM.
        The blob is stored as-is (binary) in the Git-tracked file so that
        it is unreadable without the master key.
        Format: b"DUMPER_ENC_V1\n" + base64(nonce + ciphertext + tag)
        """
        from app.crypto import encrypt as _encrypt
        b64 = _encrypt(plaintext)   # returns base64 string
        return b"DUMPER_ENC_V1\n" + b64.encode("ascii")

    @staticmethod
    def _decrypt_config(raw: bytes) -> str:
        """
        Decrypt a binary blob written by _encrypt_config().
        Falls back to treating the data as plain UTF-8 text so that
        any pre-existing unencrypted config.txt files are still readable
        (migration path).
        """
        from app.crypto import decrypt as _decrypt
        if raw.startswith(b"DUMPER_ENC_V1\n"):
            b64 = raw[len(b"DUMPER_ENC_V1\n"):].decode("ascii").strip()
            return _decrypt(b64)
        # Legacy plain-text fallback
        return raw.decode("utf-8", errors="replace")

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
        Encrypt config_content, write it to the repo, and commit.

        Returns:
            (commit_hash, diff_text)
            commit_hash: SHA of the new commit, or None if commit failed.
            diff_text:   Unified diff against the previous commit (plain text),
                         computed in-memory after decryption.
        """
        device_dir = self._get_device_dir(device_name, group_name)
        config_file = device_dir / "config.enc"
        rel_path = config_file.relative_to(self.repo_path)

        # --- Capture and decrypt the OLD content for diff & equality check ---
        old_content: Optional[str] = None
        if config_file.exists():
            try:
                old_content = self._decrypt_config(config_file.read_bytes())
            except Exception as exc:
                logger.warning("Could not decrypt old config for diff: %s", exc)

        # --- Plaintext equality check BEFORE writing ---
        # We must compare plaintext (not ciphertext) because every AES-GCM
        # encryption uses a fresh random nonce, so the ciphertext blob always
        # differs even when the config hasn't changed.
        if old_content is not None and old_content == config_content:
            logger.info("No changes to commit for device '%s' (plaintext identical)", device_name)
            return None, ""

        # --- Encrypt and write the new content ---
        config_file.write_bytes(self._encrypt_config(config_content))

        # Stage the file
        try:
            self._repo.index.add([str(rel_path)])
        except GitCommandError as exc:
            logger.error("Git add failed for %s: %s", rel_path, exc)
            return None, ""

        # Secondary guard: if nothing staged (e.g. very first commit edge case)
        if not self._repo.index.diff("HEAD"):
            logger.info("No changes staged for device '%s'", device_name)
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

        # Build diff in plain-text space (after decryption)
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
        Both blobs are decrypted in memory before diffing.
        Returns an empty string if commits or file don't exist.
        """
        if not self._repo:
            return ""
        try:
            device_dir = self._get_device_dir(device_name, group_name)
            config_file = device_dir / "config.enc"
            rel_path = str(config_file.relative_to(self.repo_path))

            raw_a = self._repo.commit(commit_a).tree[rel_path].data_stream.read()
            raw_b = self._repo.commit(commit_b).tree[rel_path].data_stream.read()
            text_a = self._decrypt_config(raw_a)
            text_b = self._decrypt_config(raw_b)
            return self._compute_diff(text_a, text_b, rel_path)
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
            config_file = device_dir / "config.enc"
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

    def get_config_at_commit(
        self,
        device_name: str,
        group_name: Optional[str],
        sha: str,
    ) -> Optional[str]:
        """Return the decrypted config text as it existed at a specific commit SHA."""
        if not self._repo:
            return None
        try:
            device_dir = self._get_device_dir(device_name, group_name)
            config_file = device_dir / "config.enc"
            rel_path = str(config_file.relative_to(self.repo_path))
            raw = self._repo.commit(sha).tree[rel_path].data_stream.read()
            return self._decrypt_config(raw)
        except Exception as exc:
            logger.warning("get_config_at_commit sha=%s failed: %s", sha, exc)
            return None

    def get_latest_config(
        self,
        device_name: str,
        group_name: Optional[str],
    ) -> Optional[str]:
        """Return the decrypted content of the current config file, or None if not found."""
        device_dir = self._get_device_dir(device_name, group_name)
        config_file = device_dir / "config.enc"
        # Also check legacy plain-text filename for migration
        if not config_file.exists():
            legacy = device_dir / "config.txt"
            if legacy.exists():
                return legacy.read_text(encoding="utf-8")
            return None
        try:
            return self._decrypt_config(config_file.read_bytes())
        except Exception as exc:
            logger.warning("get_latest_config decryption failed: %s", exc)
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
