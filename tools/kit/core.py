"""Shared manifest, path-safety, worktree, and text primitives used by every command."""

from __future__ import annotations

import os
import re
import stat
import subprocess
try:
    import tomllib
except ModuleNotFoundError as error:  # pragma: no cover - exercised on Python 3.10
    raise SystemExit("repoctl requires Python 3.11 or newer") from error
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath


PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PROJECT_KIND_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CONTAINER_DIRECTORIES = {"apps", "frontends", "packages", "services", "workers"}
FILE_SURFACE_KINDS = {"file", "script", "document", "asset"}
# Ambiguous names such as tests/, config/, and fixtures/ are intentionally not
# implicit infrastructure: a project must declare them or opt in explicitly.
REPOSITORY_INFRASTRUCTURE_DIRECTORIES = {
    "docs",
    "tools",
    "incidents",
    "cache",
    "coverage",
    "tmp",
    "temp",
    "vendor",
    "node_modules",
    "build",
    "dist",
}


class RepoctlError(Exception):
    """An actionable repository governance failure."""


def replace_manifest_field(manifest: str, field: str, value: str) -> str:
    pattern = re.compile(rf'^{re.escape(field)} = "[^"]*"$', re.MULTILINE)
    replacement = f'{field} = "{value}"'
    updated, count = pattern.subn(replacement, manifest, count=1)
    if count != 1:
        raise RepoctlError(f"project.toml must contain exactly one {field} field")
    return updated


def load_project(root: Path) -> dict[str, object]:
    manifest_path = ensure_inside_root(root, root / "project.toml", "project manifest")
    try:
        with manifest_path.open("rb") as manifest_file:
            project = tomllib.load(manifest_file)
    except FileNotFoundError as error:
        raise RepoctlError("project.toml is missing") from error
    except tomllib.TOMLDecodeError as error:
        raise RepoctlError(f"project.toml is invalid: {error}") from error

    if project.get("schema") != 1:
        raise RepoctlError("project.toml schema must be 1")
    if not isinstance(project.get("name"), str) or not isinstance(project.get("kind"), str):
        raise RepoctlError("project.toml requires string name and kind fields")
    return project


def governance_profile(project: dict[str, object]) -> str:
    governance = project.get("governance", {})
    if not isinstance(governance, dict):
        raise RepoctlError("governance must be a table")
    profile = governance.get("profile", "agent-first")
    if profile not in {"agent-first", "regulated", "minimal"}:
        raise RepoctlError("governance.profile must be agent-first, regulated, or minimal")
    return profile


def declared_surfaces(project: dict[str, object]) -> list[dict[str, object]]:
    surfaces = project.get("surfaces", [])
    if not isinstance(surfaces, list) or not all(isinstance(surface, dict) for surface in surfaces):
        raise RepoctlError("project.toml surfaces must be an array of tables")
    return surfaces


def infrastructure_paths(project: dict[str, object]) -> set[str]:
    configured = project.get("repository", {})
    if not isinstance(configured, dict):
        raise RepoctlError("repository must be a table")
    paths = set(REPOSITORY_INFRASTRUCTURE_DIRECTORIES)
    custom = configured.get("infrastructure_paths", [])
    if not isinstance(custom, list) or not all(isinstance(path, str) for path in custom):
        raise RepoctlError("repository.infrastructure_paths must be an array of strings")
    for value in custom:
        normalized = normalized_relative_path(value, "infrastructure path")
        if normalized.split("/", 1)[0] in CONTAINER_DIRECTORIES:
            raise RepoctlError(f"infrastructure path cannot hide a product container: {normalized}")
        surface_paths = {
            surface.get("path")
            for surface in declared_surfaces(project)
            if isinstance(surface.get("path"), str)
        }
        if normalized in surface_paths or any(
            path.startswith(normalized + "/") for path in surface_paths
        ):
            raise RepoctlError(f"infrastructure path overlaps a declared surface: {normalized}")
        paths.add(normalized)
    return paths


def is_link_like(path: Path) -> bool:
    try:
        file_stat = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if stat.S_ISLNK(file_stat.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(file_stat, "st_file_attributes", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def has_link_component(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        if part in {"", "."}:
            continue
        current = current / part
        if is_link_like(current):
            return True
    return False


def ensure_inside_root(root: Path, path: Path, label: str) -> Path:
    normalized = Path(os.path.normpath(path))
    try:
        normalized.relative_to(root)
    except ValueError as error:
        raise RepoctlError(f"{label} must stay inside the repository") from error
    if has_link_component(root, normalized):
        raise RepoctlError(f"{label} must not traverse symlinks or reparse points")
    return normalized


def normalized_relative_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RepoctlError(f"surface {field} must be a non-empty string")
    path = Path(value)
    windows_path = PureWindowsPath(value)
    if path.is_absolute() or bool(windows_path.drive) or "\\" in value or ".." in path.parts:
        raise RepoctlError(f"surface {field} must stay inside the repository: {value}")
    normalized = Path(value.replace("\\", "/")).as_posix().rstrip("/")
    return normalized or "."


def markdown_without_fenced_code(markdown: str) -> str:
    return re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)


def markdown_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    return target.split(maxsplit=1)[0]


IGNORED_WALK_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".agent",
    ".claude",
    ".codex",
    ".cursor",
    ".gemini",
    "node_modules",
    "vendor",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
SENSITIVE_CONTENT_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:[A-Z0-9 ]*PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----.*?-----END (?:[A-Z0-9 ]*PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----", re.DOTALL),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "authorization credential": re.compile(r"(?i)\b(?:authorization|proxy-authorization)\s*:\s*(?:bearer|basic)\s+[^\s]+"),
    "credential assignment": re.compile(r"(?i)\b(?:api[_-]?key|password|passwd|access[_-]?token|client[_-]?secret|token|secret)\s*[:=]\s*[^\s]{12,}"),
}


def worktree_files(root: Path) -> list[Path]:
    try:
        git_root_result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        git_root_result = None

    if git_root_result is not None and git_root_result.returncode == 0:
        git_root = Path(git_root_result.stdout.strip()).resolve()
        if git_root == root:
            listed = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                check=True,
                capture_output=True,
                text=True,
            )
            # Tracked files deleted in the working tree are gone, not hygiene subjects.
            return [
                root / relative
                for relative in listed.stdout.split("\0")
                if relative and os.path.lexists(root / relative)
            ]

    files: list[Path] = []
    for current, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current_root = Path(current)
        retained_directories: list[str] = []
        for directory_name in sorted(directory_names):
            directory = current_root / directory_name
            if is_link_like(directory):
                files.append(directory)
                continue
            if directory_name in IGNORED_WALK_DIRECTORIES:
                continue
            retained_directories.append(directory_name)
        directory_names[:] = retained_directories

        for file_name in sorted(file_names):
            path = current_root / file_name
            relative_parts = path.relative_to(root).parts
            if any(part in IGNORED_WALK_DIRECTORIES for part in relative_parts[:-1]):
                continue
            try:
                file_stat = os.lstat(path)
            except OSError:
                continue
            if (
                stat.S_ISREG(file_stat.st_mode)
                or stat.S_ISLNK(file_stat.st_mode)
                or bool(
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                    and getattr(file_stat, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                )
            ):
                files.append(path)
    return files


def parse_iso_date(text: str | None) -> "datetime.date | None":
    """A YYYY-MM-DD string as a date, or None when it is missing or not a real date."""
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date() if text else None
    except ValueError:
        return None


def date_is_future(value: "datetime.date") -> bool:
    return value > datetime.now(timezone.utc).date()


def date_is_stale(value: datetime.date) -> bool:
    today = datetime.now(timezone.utc).date()
    return value > today or value < today - timedelta(days=365)


def is_placeholder(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    normalized = value.strip()
    return bool(
        re.fullmatch(
            r"\[.*\]|\s*(?:tbd|pending|required|unknown|none|placeholder|project-owner|todo)\s*"
            r"|todo(?:\s*:\s*assign)?|replace[_-]?with[_-]?project[_-]?owner",
            normalized,
            re.I,
        )
    )


def secret_matches(content: str) -> list[str]:
    return [label for label, pattern in SENSITIVE_CONTENT_PATTERNS.items() if pattern.search(content)]


def reject_secret_text(value: str, label: str) -> None:
    matches = secret_matches(value)
    if matches:
        raise RepoctlError(f"{label} contains possible secret material: {', '.join(matches)}")


def safe_markdown_text(value: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", " ".join(value.split()))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise RepoctlError("title must contain at least one letter or number")
    return slug[:80].rstrip("-")


def repository_files(root: Path) -> list[str]:
    """Tracked and untracked-but-not-ignored regular files, repository-relative and sorted."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in worktree_files(root)
        if path.is_file() and not is_link_like(path)
    )


def read_text_file(root: Path, relative: str, limit: int = 1_000_000) -> str | None:
    """Return UTF-8 text for a small regular file, or None for binary/large/unreadable files."""
    path = root / relative
    try:
        if path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
