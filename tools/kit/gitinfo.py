"""Read-only git queries and repository-relative glob matching for self-healing checks."""

from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path


def run_git(root: Path | None, *arguments: str, timeout: int = 30, input: str | None = None) -> subprocess.CompletedProcess[str] | None:
    """The one place the kit runs git: unquoted paths, a timeout, and None when git cannot run.

    `root=None` runs outside any repository (clone, ls-remote). Output decodes with
    `surrogateescape`, so a non-UTF-8 filename round-trips to the filesystem instead of raising.
    """
    where = ["-C", str(root)] if root is not None else []
    try:
        return subprocess.run(
            ["git", *where, "-c", "core.quotepath=false", *arguments],
            check=False, capture_output=True, text=True, errors="surrogateescape", timeout=timeout, input=input,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def git(root: Path | None, *arguments: str, timeout: int = 30, input: str | None = None) -> str | None:
    """Return git stdout, or None when git is unavailable or the command fails."""
    result = run_git(root, *arguments, timeout=timeout, input=input)
    return result.stdout if result is not None and result.returncode == 0 else None


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


def diff_paths(root: Path, *revisions: str) -> list[str]:
    """Paths in `git diff --name-only <revisions>`: the one parser for every changed-path list."""
    return [line for line in (git(root, "diff", "--name-only", *revisions) or "").splitlines() if line]


def committed_paths(root: Path, base: str) -> list[str]:
    """Paths committed on this branch since it diverged from base (a critic reviews a diff, not a dirty tree)."""
    merge_base = (git(root, "merge-base", "HEAD", base) or "").strip()
    if not merge_base:
        return []
    return diff_paths(root, merge_base, "HEAD")


def branch_paths(root: Path, base: str) -> list[str]:
    """Paths changed on this branch since it diverged from base, plus uncommitted ones."""
    return sorted(set(committed_paths(root, base)) | set(changed_paths(root)))


@lru_cache(maxsize=512)
def glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a repository glob (`*`, `?`, `**`) into an anchored regex.

    `[abc]` and `{a,b}` are literal on purpose: paths such as `app/[id]/page.tsx` exist.
    """
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
