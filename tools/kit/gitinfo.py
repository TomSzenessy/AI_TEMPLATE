"""Read-only git queries and repository-relative glob matching for self-healing checks."""

from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path


def git(root: Path, *arguments: str, timeout: int = 30) -> str | None:
    """Return git stdout, or None when git is unavailable or the command fails."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def is_repository(root: Path) -> bool:
    top = git(root, "rev-parse", "--show-toplevel")
    return bool(top) and Path(top.strip()).resolve() == root.resolve()


def has_history(root: Path) -> bool:
    """True when commit history is complete enough for staleness checks."""
    if not is_repository(root) or git(root, "rev-parse", "--verify", "HEAD") is None:
        return False
    return (git(root, "rev-parse", "--is-shallow-repository") or "").strip() != "true"


def branch(root: Path) -> str:
    return (git(root, "branch", "--show-current") or "").strip() or "(detached)"


def head(root: Path) -> str:
    return (git(root, "rev-parse", "--short", "HEAD") or "").strip() or "(no commits)"


def changed_paths(root: Path) -> list[str]:
    """Uncommitted paths (staged, unstaged, untracked), repository-relative."""
    output = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if not output:
        return []
    paths: list[str] = []
    entries = output.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            index += 1  # the next field is the rename source
        paths.append(path)
    return sorted(set(paths))


def branch_paths(root: Path, base: str) -> list[str]:
    """Paths changed on this branch since it diverged from base, plus uncommitted ones."""
    committed: list[str] = []
    merge_base = git(root, "merge-base", "HEAD", base)
    if merge_base:
        diff = git(root, "diff", "--name-only", merge_base.strip(), "HEAD")
        committed = [line for line in (diff or "").splitlines() if line]
    return sorted(set(committed) | set(changed_paths(root)))


@lru_cache(maxsize=512)
def glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a repository glob (`*`, `?`, `**`) into an anchored regex."""
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(parts) + r"\Z")


def path_matches(path: str, pattern: str) -> bool:
    pattern = pattern.strip()
    if pattern.startswith("./"):
        pattern = pattern[2:]
    if pattern.endswith("/"):
        pattern += "**"
    return bool(glob_regex(pattern).match(path))
