"""The `<!-- index: -->` / `<!-- covers: -->` comment carrier: one parser, one cache.

A Markdown document declares the paths it covers and its docs-index entry in
HTML comments under its title. This module is the only reader of that syntax,
so `registry` (capability lookup) and `docsync` (binding checks) share one
declaration instead of each parsing it (docs/bindings.md).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .core import INLINE_CODE, markdown_without_fenced_code, read_text_file
from .gitinfo import path_matches

COVERS_PATTERN = re.compile(r"<!--\s*covers:\s*(.*?)\s*-->", re.DOTALL)
INDEX_PATTERN = re.compile(r"<!--\s*index:\s*(.*?)\s*-->", re.DOTALL)
META_CACHE = ".agent/cache/doc-meta.json"


def doc_meta(root: Path, files: list[str]) -> dict[str, dict[str, object]]:
    """Per-document declarations: `covers` globs and the `index` entry, cached.

    Parsed declarations are cached in ignored `.agent/cache/` by size and
    mtime, so per-edit hooks stay cheap in repositories with many documents.
    """
    cache_path = root / META_CACHE
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache = cache if isinstance(cache, dict) and cache.get("version") == 3 else {}
    except (OSError, ValueError):
        cache = {}
    entries = cache.get("entries", {}) if isinstance(cache.get("entries"), dict) else {}
    fresh: dict[str, list] = {}
    result: dict[str, dict[str, object]] = {}
    for relative in files:
        if not relative.endswith(".md"):
            continue
        try:
            status = (root / relative).stat()
        except OSError:
            continue
        stamp = [status.st_mtime_ns, status.st_size]
        cached = entries.get(relative)
        if (isinstance(cached, list) and len(cached) == 2 and cached[0] == stamp
                and isinstance(cached[1], dict) and isinstance(cached[1].get("covers"), list)
                and isinstance(cached[1].get("index", []), (list, type(None)))):
            meta = cached[1]
        else:
            text = INLINE_CODE.sub("", markdown_without_fenced_code(read_text_file(root, relative) or ""))
            index = INDEX_PATTERN.search(text)
            meta = {
                "covers": [p for match in COVERS_PATTERN.finditer(text) for p in match.group(1).split()],
                "index": [part.strip() for part in index.group(1).split("|")] if index else None,
            }
        fresh[relative] = [stamp, meta]
        result[relative] = meta
    if fresh != entries:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_name(cache_path.name + f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps({"version": 3, "entries": fresh}), encoding="utf-8")
            os.replace(temporary, cache_path)  # atomic: a concurrent reader never sees half a file
        except OSError:
            pass  # the cache is an optimization only
    return result


def bindings(root: Path, files: list[str]) -> dict[str, list[str]]:
    """Map each Markdown document to the path globs it declares it covers."""
    return {path: list(meta["covers"]) for path, meta in doc_meta(root, files).items() if meta["covers"]}


def owners(doc_bindings: dict[str, list[str]], path: str) -> list[str]:
    """Documents whose bindings cover path (a document never owns itself)."""
    return sorted(
        doc
        for doc, patterns in doc_bindings.items()
        if doc != path and any(path_matches(path, pattern) for pattern in patterns)
    )
