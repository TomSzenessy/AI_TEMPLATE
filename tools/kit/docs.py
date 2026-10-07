"""Markdown links, documentation index, and tracked-file hygiene."""

from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlsplit

from .core import (
    RepoctlError,
    ensure_inside_root,
    has_link_component,
    is_link_like,
    markdown_link_target,
    markdown_without_fenced_code,
    secret_matches,
    worktree_files,
)


def check_markdown_links(root: Path) -> None:
    errors: list[str] = []
    link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    documents = sorted(
        path for path in worktree_files(root) if path.suffix.lower() == ".md"
    )
    for document in documents:
        document_label = document.relative_to(root).as_posix()
        if is_link_like(document) or has_link_component(root, document):
            errors.append(f"unsafe Markdown document symlink or reparse point: {document_label}")
            continue
        markdown = markdown_without_fenced_code(document.read_text(encoding="utf-8"))
        for raw_target in link_pattern.findall(markdown):
            target = markdown_link_target(raw_target)
            if not target or target.startswith("#"):
                continue
            decoded_target = unquote(target)
            parsed = urlsplit(decoded_target)
            if parsed.scheme or parsed.netloc:
                continue
            windows_target = PureWindowsPath(decoded_target)
            if (
                "\\" in decoded_target
                or decoded_target.startswith("//")
                or bool(windows_target.drive)
                or re.match(r"^[A-Za-z]:", decoded_target)
            ):
                errors.append(
                    f"unsafe local Markdown target: {document_label} -> {decoded_target}"
                )
                continue
            relative_target = parsed.path
            if not relative_target:
                continue
            destination = (
                root / relative_target.lstrip("/")
                if relative_target.startswith("/")
                else document.parent / relative_target
            )
            normalized_destination = Path(os.path.normpath(destination))
            try:
                normalized_destination.relative_to(root)
            except ValueError:
                errors.append(
                    f"Markdown link escapes repository root: {document_label} -> {relative_target}"
                )
                continue
            if has_link_component(root, normalized_destination):
                errors.append(
                    f"unsafe local Markdown target: {document_label} -> {relative_target}"
                )
                continue
            destination = normalized_destination
            if not destination.exists():
                errors.append(
                    f"broken local Markdown link: {document_label} -> {relative_target}"
                )
    if errors:
        raise RepoctlError("Markdown link check failed:\n- " + "\n- ".join(errors))


def check_docs_index(root: Path) -> None:
    docs = root / "docs"
    index = ensure_inside_root(root, docs / "README.md", "documentation index")
    try:
        index_content = index.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise RepoctlError("docs/README.md is missing") from error

    errors: list[str] = []
    for document in sorted(docs.rglob("*.md")):
        if document == index:
            continue
        relative = document.relative_to(docs).as_posix()
        link = re.compile(rf"\]\((?:\./)?{re.escape(relative)}(?:#[^)]+)?\)")
        if not link.search(index_content):
            errors.append(f"document is not linked from docs/README.md: {relative}")
    if errors:
        raise RepoctlError("documentation index check failed:\n- " + "\n- ".join(errors))


def check_file_hygiene(root: Path) -> None:
    errors: list[str] = []
    for path in worktree_files(root):
        relative = path.relative_to(root).as_posix()
        if is_link_like(path) or has_link_component(root, path):
            errors.append(f"symlink or reparse point must stay inside the repository: {relative}")
            continue
        name = path.name.lower()
        allowed_environment_suffixes = (".example", ".sample", ".template")
        if (name == ".env" or name.startswith(".env.")) and not name.endswith(
            allowed_environment_suffixes
        ):
            errors.append(f"sensitive file must not be tracked: {relative}")
        if path.suffix.lower() in {".key", ".p12", ".pfx", ".pem", ".ppk", ".jks", ".keystore"} or name in {
            "id_dsa",
            "id_ecdsa",
            "id_ed25519",
            "id_rsa",
            ".netrc",
            ".npmrc",
            ".pypirc",
            ".git-credentials",
        }:
            errors.append(f"sensitive key file must not be tracked: {relative}")
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for label in secret_matches(content):
            errors.append(f"possible {label} in tracked file: {relative}")
    if errors:
        raise RepoctlError("file hygiene check failed:\n- " + "\n- ".join(errors))


def docs_index_link_content(root: Path, marker: str, link: str) -> str:
    index = ensure_inside_root(root, root / "docs" / "README.md", "documentation index")
    content = index.read_text(encoding="utf-8")
    start_marker = f"<!-- repoctl:{marker} -->"
    end_marker = f"<!-- /repoctl:{marker} -->"
    block = f"{start_marker}\n{link}\n{end_marker}"
    if (start_marker in content) != (end_marker in content):
        raise RepoctlError(f"documentation marker is malformed: {marker}")
    if start_marker in content and end_marker in content:
        match = re.search(
            rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
            content,
            flags=re.DOTALL,
        )
        if not match:
            raise RepoctlError(f"documentation marker is malformed: {marker}")
        body = match.group(0)[len(start_marker) : -len(end_marker)].strip()
        if link in body.splitlines():
            raise RepoctlError(f"documentation marker already contains link: {marker}")
        new_body = f"\n{body}\n{link}\n" if body else f"\n{link}\n"
        updated = content[: match.start()] + start_marker + new_body + end_marker + content[match.end() :]
    else:
        updated = content.rstrip() + "\n\n" + block + "\n"
    if start_marker in content and updated == content:
        raise RepoctlError(f"documentation marker did not update: {marker}")
    return updated


def add_docs_index_link(root: Path, marker: str, link: str) -> None:
    index = ensure_inside_root(root, root / "docs" / "README.md", "documentation index")
    index.write_text(docs_index_link_content(root, marker, link), encoding="utf-8")
