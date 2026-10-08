"""Markdown links, documentation index, and tracked-file hygiene."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlsplit

from .docsync import INDEX_SKIP
from .core import (
    RepoctlError,
    check_failed,
    INLINE_CODE,
    ensure_inside_root,
    has_link_component,
    is_link_like,
    markdown_link_target,
    markdown_without_fenced_code,
    read_utf8,
    secret_matches,
    worktree_files,
)


def check_markdown_links(root: Path) -> None:
    errors: list[str] = []
    link_pattern = re.compile(r"!?\[[^\]]*\]\(((?:[^()]|\([^()]*\))+)\)")  # one level of () inside a target
    documents = sorted(
        path for path in worktree_files(root) if path.suffix.lower() == ".md"
    )
    for document in documents:
        document_label = document.relative_to(root).as_posix()
        if has_link_component(root, document):  # includes the document itself
            errors.append(f"unsafe Markdown document symlink or reparse point: {document_label}")
            continue
        try:
            markdown = INLINE_CODE.sub("", markdown_without_fenced_code(document.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            errors.append(f"not valid UTF-8: {document_label}")
            continue
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
        raise check_failed("Markdown link", errors)


def check_docs_index(root: Path) -> None:
    docs = root / "docs"
    index = ensure_inside_root(root, docs / "README.md", "documentation index")
    try:
        index_content = read_utf8(index)
    except FileNotFoundError as error:
        raise RepoctlError("docs/README.md is missing") from error

    linked = set(re.findall(r"\]\((?:\./)?([^)#]+)(?:#[^)]+)?\)", index_content))  # compiled once, not per document
    errors: list[str] = []
    for document in sorted(worktree_files(root)):  # the same document set every other check reads
        if document.suffix.lower() != ".md" or document == index:
            continue
        try:
            relative = document.relative_to(docs).as_posix()
        except ValueError:
            continue
        if f"docs/{relative}".startswith(INDEX_SKIP):
            continue
        if relative not in linked:
            errors.append(
                f"document is not linked from docs/README.md: {relative} (add `<!-- index: group | owns | read when -->` "
                "under its title, then run make sync)"
            )
    if errors:
        raise check_failed("documentation index", errors)


def check_file_hygiene(root: Path) -> None:
    errors: list[str] = []
    notes: list[str] = []
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
        labels, complete = scan_file_for_secrets(path)
        for label in labels:
            errors.append(f"possible {label} in tracked file: {relative}")
        if not complete:
            notes.append(f"not fully scanned: {relative} (over {SCAN_CAP_BYTES // (1024 * 1024)} MiB)")
    if errors:
        raise check_failed("file hygiene", errors + notes)
    for note in notes:  # advisory: the check only raises blocking findings
        print(f"warning: {note}", file=sys.stderr)


SCAN_CHUNK_BYTES = 1024 * 1024
SCAN_OVERLAP_BYTES = 4096
SCAN_CAP_BYTES = 32 * 1024 * 1024
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".pdf", ".zip", ".gz", ".tgz", ".bz2",
    ".xz", ".7z", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".mov", ".wav", ".pyc",
    ".so", ".dylib", ".dll", ".exe", ".class", ".jar", ".wasm",
}


def scan_file_for_secrets(path: Path) -> tuple[list[str], bool]:
    """Scan a file in overlapping chunks; return (pattern labels, fully scanned)."""
    if path.suffix.lower() in BINARY_SUFFIXES:
        return [], True
    found: dict[str, None] = {}
    try:
        with path.open("rb") as handle:
            head = handle.read(8192)
            codec = "utf-8"
            if head.startswith(b"\xff\xfe"):
                codec = "utf-16-le"
            elif head.startswith(b"\xfe\xff"):
                codec = "utf-16-be"
            elif b"\0" in head:
                return [], True
            handle.seek(2 if codec != "utf-8" else 0)
            carry = b""
            scanned = 0
            while scanned < SCAN_CAP_BYTES:
                data = handle.read(min(SCAN_CHUNK_BYTES, SCAN_CAP_BYTES - scanned))
                if not data:
                    return list(found), True
                scanned += len(data)
                buffer = carry + data
                for label in secret_matches(buffer.decode(codec, errors="ignore")):
                    found.setdefault(label)
                carry = buffer[-SCAN_OVERLAP_BYTES:]
            return list(found), not handle.read(1)
    except OSError:
        return list(found), True


def docs_index_link_content(root: Path, marker: str, link: str) -> str:
    index = ensure_inside_root(root, root / "docs" / "README.md", "documentation index")
    content = read_utf8(index)
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


