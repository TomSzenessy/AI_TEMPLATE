"""Eligible-code inventory for semantic code similarity (#115, split out of semantic.py).

Owns which git-tracked files may be indexed (exclusions, budgets, hygiene scan)
and the bounded line chunking. Pure over the tree and config: nothing is sent,
stored, or authorized here. `semantic.py` re-exports these names.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .core import DIRECTORY_ROLES, RepoctlError, code_secret_matches, has_link_component, is_link_like, read_utf8
from .docs import BINARY_SUFFIXES
from .gitinfo import git, is_repository

# The same environment and key files the tracked-file hygiene scanner
# (tools/kit/docs.py) blocks: the index never holds them.
KEY_SUFFIXES = frozenset({".key", ".p12", ".pfx", ".pem", ".ppk", ".jks", ".keystore"})
KEY_NAMES = frozenset({
    "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa", ".netrc", ".npmrc", ".pypirc", ".git-credentials",
})
CODE_NAMES = frozenset({"Dockerfile", "Makefile", "GNUmakefile", "CMakeLists.txt", "Rakefile", "Gemfile"})
SKIP_PREFIXES = (".claude/", ".agent/", ".codex/", ".cursor/", ".gemini/", ".github/", ".githooks/", ".security/", ".review/")
SKIP_NAMES = frozenset({".mcp.json", ".DS_Store", ".gitignore", ".gitattributes", ".editorconfig"})
# Every directory the kit already treats as ignored, generated, or infrastructure
# (tools/kit/core.py DIRECTORY_ROLES): product code is what remains.
SKIP_DIRS = frozenset(DIRECTORY_ROLES)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- Eligible code inventory ---------------------------------------------------


def _excluded(root: Path, relative: str, path: Path, config: dict) -> str | None:
    """Why a tracked file is not eligible code, or None when it is."""
    parts = relative.split("/")
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return "infrastructure or generated directory"
    if relative.startswith(tuple(config["skip_prefixes"])):
        return "skipped prefix"
    name = parts[-1].lower()
    if name in SKIP_NAMES or name.startswith(".env") or name in KEY_NAMES or Path(name).suffix in KEY_SUFFIXES:
        return "environment or key file"
    if Path(name).suffix in BINARY_SUFFIXES:
        return "binary"
    if Path(name).suffix not in frozenset(config["code_extensions"]) and name not in CODE_NAMES:
        return "not textual code"
    if is_link_like(path) or has_link_component(root, path):
        return "symlink"
    return None


def _eligible_files(root: Path, config: dict) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """(relative, text) for every eligible tracked code file within the file/chunk budgets, plus skip counts."""
    listed = git(root, "ls-files", "--cached", "-z")
    candidates = [item for item in (listed or "").split("\0") if item]
    eligible: list[tuple[str, str]] = []
    skipped: dict[str, int] = {}
    chunks = 0
    for relative in candidates:
        if len(eligible) >= config["max_files"]:
            skipped["file budget reached"] = skipped.get("file budget reached", 0) + 1
            continue
        path = root / relative
        reason = _excluded(root, relative, path, config)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        try:
            if path.stat().st_size > config["max_file_bytes"]:
                skipped["over file byte budget"] = skipped.get("over file byte budget", 0) + 1
                continue
            text = read_utf8(path)
        except (OSError, RepoctlError):
            skipped["unreadable or not UTF-8"] = skipped.get("unreadable or not UTF-8", 0) + 1
            continue
        if code_secret_matches(text):
            skipped["flagged by the hygiene scanner"] = skipped.get("flagged by the hygiene scanner", 0) + 1
            continue
        file_chunks = chunk_text(text, config)
        if chunks + len(file_chunks) > config["max_chunks"]:
            file_chunks = file_chunks[: config["max_chunks"] - chunks]
        if not file_chunks:
            continue
        chunks += len(file_chunks)
        eligible.append((relative, text))
    return eligible, skipped


def inventory(root: Path, config: dict) -> dict:
    """Eligible git-tracked textual code within every budget.

    Returns {"files": ["path:sha256", ...] (sorted), "chunks": n, "bytes": n,
    "skipped": {reason: n}, "reason": str (empty when files were found)}.
    """
    if not is_repository(root):
        return {"files": [], "chunks": 0, "bytes": 0, "skipped": {}, "reason": "not a git repository"}
    listed = git(root, "ls-files", "--cached", "-z")
    if listed is None:
        return {"files": [], "chunks": 0, "bytes": 0, "skipped": {}, "reason": "git unavailable"}
    candidates = [item for item in listed.split("\0") if item]
    result = {"files": [], "chunks": 0, "bytes": 0, "skipped": {}}
    if candidates:
        eligible, skipped = _eligible_files(root, config)
        result["skipped"] = skipped
        result["files"] = sorted(f"{relative}:{_sha256(text)}" for relative, text in eligible)
        result["chunks"] = sum(len(chunk_text(text, config)) for _, text in eligible)
        result["bytes"] = sum(len(text.encode("utf-8")) for _, text in eligible)
    result["reason"] = "" if result["files"] else (
        "no tracked files (new repository)" if not candidates else "no textual code in scope"
    )
    return result


def chunk_text(text: str, config: dict) -> list[dict]:
    """Bounded UTF-8-safe line chunks: line boundaries only, byte and line budgets enforced."""
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode("utf-8")))
    chunks: list[dict] = []
    start = 0
    while start < len(lines):
        end = start
        while (end < len(lines) and end - start < config["chunk_lines"]
               and offsets[end + 1] - offsets[start] <= config["chunk_bytes"]):
            end += 1
        if end == start:
            end = start + 1  # one oversized line is still a bounded chunk
        body = "".join(lines[start:end])
        chunks.append({"start_line": start + 1, "end_line": end, "byte_start": offsets[start],
                       "byte_end": offsets[end], "text": body, "sha256": _sha256(body)})
        start = end
    return chunks
