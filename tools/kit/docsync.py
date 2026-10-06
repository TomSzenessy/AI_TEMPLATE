"""Doc-to-code binding: which document owns which paths, and whether it kept up.

A Markdown document declares the paths it describes with one HTML comment:

    <!-- covers: tools/kit/docsync.py .agents/agents/** -->

From that single declaration the kit derives ownership lookups (`where`, the
after-edit hook), dead bindings (a pattern matching nothing means code moved or
died), stale documents (a later commit touched covered paths but not the doc),
and pending documents (uncommitted covered changes without a doc change).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .core import markdown_without_fenced_code, read_text_file
from .gitinfo import git, has_history, path_matches

COVERS_PATTERN = re.compile(r"<!--\s*covers:\s*(.*?)\s*-->", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")  # examples in code spans are not bindings
UNAFFECTED_TRAILER = "Docs-Unaffected"
HISTORY_LIMIT = 2000
BINDINGS_CACHE = ".agent/cache/bindings.json"


def bindings(root: Path, files: list[str]) -> dict[str, list[str]]:
    """Map each Markdown document to the path globs it declares it covers.

    Parsed declarations are cached in ignored `.agent/cache/` by size and
    mtime, so per-edit hooks stay cheap in repositories with many documents.
    """
    cache_path = root / BINDINGS_CACHE
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache = cache if isinstance(cache, dict) and cache.get("version") == 1 else {}
    except (OSError, ValueError):
        cache = {}
    entries = cache.get("entries", {}) if isinstance(cache.get("entries"), dict) else {}
    fresh: dict[str, list] = {}
    result: dict[str, list[str]] = {}
    for relative in files:
        if not relative.endswith(".md"):
            continue
        try:
            status = (root / relative).stat()
        except OSError:
            continue
        stamp = [status.st_mtime_ns, status.st_size]
        cached = entries.get(relative)
        if isinstance(cached, list) and len(cached) == 2 and cached[0] == stamp:
            patterns = cached[1]
        else:
            text = read_text_file(root, relative) or ""
            patterns = [
                pattern
                for match in COVERS_PATTERN.finditer(INLINE_CODE.sub("", markdown_without_fenced_code(text)))
                for pattern in match.group(1).split()
            ]
        fresh[relative] = [stamp, patterns]
        if patterns:
            result[relative] = patterns
    if fresh != entries:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"version": 1, "entries": fresh}), encoding="utf-8")
        except OSError:
            pass  # the cache is an optimization only
    return result


def owners(doc_bindings: dict[str, list[str]], path: str) -> list[str]:
    """Documents whose bindings cover path (a document never owns itself)."""
    return sorted(
        doc
        for doc, patterns in doc_bindings.items()
        if doc != path and any(path_matches(path, pattern) for pattern in patterns)
    )


def dead_bindings(doc_bindings: dict[str, list[str]], files: list[str]) -> list[str]:
    errors = []
    for doc, patterns in sorted(doc_bindings.items()):
        for pattern in patterns:
            if not any(path_matches(path, pattern) for path in files):
                errors.append(f"{doc}: covers pattern matches no file: {pattern}")
    return errors


def _history(root: Path, revisions: str | None = None) -> list[tuple[str, set[str] | None, set[str]]]:
    """Newest-first (commit, Docs-Unaffected scope, paths); scope None = no trailer."""
    output = git(
        root,
        "log",
        *([revisions] if revisions else []),
        f"-n{HISTORY_LIMIT}",
        "--no-merges",
        "--name-only",
        f"--format=%x1e%h%x1f%(trailers:key={UNAFFECTED_TRAILER},valueonly,separator=%x20)%x1f",
        timeout=60,
    )
    commits = []
    for record in (output or "").split("\x1e"):
        if not record.strip():
            continue
        commit, trailer, names = (record.split("\x1f") + ["", ""])[:3]
        scope: set[str] | None = None
        if trailer.strip():
            # A trailer naming specific .md files scopes the exemption to them;
            # any other value exempts the commit for every document.
            named = {token.strip(",;") for token in trailer.split() if token.strip(",;").endswith(".md")}
            scope = named or {"*"}
        commits.append((commit.strip(), scope, {line for line in names.splitlines() if line}))
    return commits


def stale_documents(
    root: Path, doc_bindings: dict[str, list[str]], changed: list[str] | None = None
) -> list[str]:
    """Documents with a newer, non-exempt commit touching their covered paths.

    A document being edited in the working tree, or one with no commit inside
    the inspected history window, is not judged here (see pending_documents).
    """
    if not doc_bindings or not has_history(root):
        return []
    history = _history(root)
    committed_docs = {path for _, _, paths in history for path in paths}
    in_progress = set(changed or [])
    findings = []
    for doc, patterns in sorted(doc_bindings.items()):
        if doc in in_progress or doc not in committed_docs:
            continue
        for commit, scope, paths in history:
            if doc in paths:
                break
            if _exempt(scope, doc):
                continue
            touched = sorted(path for path in paths if any(path_matches(path, p) for p in patterns))
            if touched:
                findings.append(
                    f"{doc}: stale since {commit} changed {', '.join(touched[:3])}"
                    + (" …" if len(touched) > 3 else "")
                    + f" (update the doc, or add a '{UNAFFECTED_TRAILER}: {doc} <reason>' commit trailer)"
                )
                break
    return findings


def _exempt(scope: set[str] | None, doc: str) -> bool:
    return scope is not None and ("*" in scope or doc in scope)


def owed_documents(
    root: Path, doc_bindings: dict[str, list[str]], base: str, uncommitted: list[str]
) -> dict[str, list[str]]:
    """Covered paths changed on this branch (since base) or uncommitted, per untouched doc.

    Branch commits carrying a matching Docs-Unaffected trailer do not create debt.
    """
    merge_base = (git(root, "merge-base", "HEAD", base) or "").strip()
    branch_commits = _history(root, f"{merge_base}..HEAD") if merge_base else []
    touched_docs = set(uncommitted) | {path for _, _, paths in branch_commits for path in paths}
    owed: dict[str, list[str]] = {}
    for doc, patterns in sorted(doc_bindings.items()):
        if doc in touched_docs:
            continue
        candidates = set(uncommitted)
        for _, scope, paths in branch_commits:
            if not _exempt(scope, doc):
                candidates |= paths
        covered = sorted(path for path in candidates if path != doc and any(path_matches(path, p) for p in patterns))
        if covered:
            owed[doc] = covered
    return owed


def pending_documents(doc_bindings: dict[str, list[str]], changed: list[str]) -> dict[str, list[str]]:
    """Uncommitted covered changes whose owning document has not been touched."""
    changed_set = set(changed)
    pending: dict[str, list[str]] = {}
    for path in changed:
        for doc in owners(doc_bindings, path):
            if doc not in changed_set:
                pending.setdefault(doc, []).append(path)
    return pending


MAKE_REFERENCE = re.compile(r"`make ([a-z][a-z0-9_-]*)")
FENCED_MAKE = re.compile(r"(?m)^\s*(?:\$\s*)?make ([a-z][a-z0-9_-]*)")
REPOCTL_REFERENCE = re.compile(r"`(?:python3 )?(?:tools/)?repoctl(?:\.py)? ([a-z][a-z-]*)")
FENCE = re.compile(r"```.*?```", re.DOTALL)


def makefile_targets(root: Path) -> set[str]:
    text = read_text_file(root, "Makefile") or ""
    return set(re.findall(r"(?m)^([A-Za-z0-9][A-Za-z0-9_-]*):", text))


def repoctl_commands(root: Path) -> set[str]:
    text = read_text_file(root, "tools/repoctl.py") or ""
    return set(re.findall(r'add_parser\(\s*"([a-z-]+)"', text))


def command_reference_errors(root: Path, files: list[str]) -> list[str]:
    """Backticked `make X` / `repoctl X` and fenced `make X` lines must name real commands."""
    targets = makefile_targets(root)
    commands = repoctl_commands(root)
    if not targets and not commands:
        return []
    errors = []
    for relative in files:
        if not relative.endswith(".md"):
            continue
        text = read_text_file(root, relative)
        if not text:
            continue
        references = set(MAKE_REFERENCE.findall(text))
        for fence in FENCE.findall(text):
            references |= set(FENCED_MAKE.findall(fence))
        if targets:
            for target in sorted(references - targets):
                errors.append(f"{relative}: references missing make target: make {target}")
        if commands:
            for command in sorted(set(REPOCTL_REFERENCE.findall(text)) - commands):
                errors.append(f"{relative}: references missing repoctl command: {command}")
    return errors
