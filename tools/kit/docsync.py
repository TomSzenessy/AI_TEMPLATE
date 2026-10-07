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
import os
import re
import subprocess
from pathlib import Path

from .core import markdown_without_fenced_code, read_text_file
from .gitinfo import git, has_history, path_matches

COVERS_PATTERN = re.compile(r"<!--\s*covers:\s*(.*?)\s*-->", re.DOTALL)
INDEX_PATTERN = re.compile(r"<!--\s*index:\s*(.*?)\s*-->", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")  # examples in code spans are not bindings
UNAFFECTED_TRAILER = "Docs-Unaffected"
HISTORY_LIMIT = 2000
META_CACHE = ".agent/cache/doc-meta.json"


def doc_meta(root: Path, files: list[str]) -> dict[str, dict[str, object]]:
    """Per-document declarations: `covers` globs and the `index` entry, cached.

    Parsed declarations are cached in ignored `.agent/cache/` by size and
    mtime, so per-edit hooks stay cheap in repositories with many documents.
    """
    cache_path = root / META_CACHE
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache = cache if isinstance(cache, dict) and cache.get("version") == 2 else {}
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
        if isinstance(cached, list) and len(cached) == 2 and cached[0] == stamp:
            meta = cached[1]
        else:
            text = INLINE_CODE.sub("", markdown_without_fenced_code(read_text_file(root, relative) or ""))
            index = INDEX_PATTERN.search(text)
            title = re.search(r"(?m)^# (.+)$", text)
            meta = {
                "covers": [p for match in COVERS_PATTERN.finditer(text) for p in match.group(1).split()],
                "index": [part.strip() for part in index.group(1).split("|")] if index else None,
                "title": title.group(1).strip() if title else relative,
            }
        fresh[relative] = [stamp, meta]
        result[relative] = meta
    if fresh != entries:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"version": 2, "entries": fresh}), encoding="utf-8")
        except OSError:
            pass  # the cache is an optimization only
    return result


def bindings(root: Path, files: list[str]) -> dict[str, list[str]]:
    """Map each Markdown document to the path globs it declares it covers."""
    return {path: list(meta["covers"]) for path, meta in doc_meta(root, files).items() if meta["covers"]}


def doc_groups(root: Path) -> dict[str, str]:
    """Docs index sections from project.toml [kit].doc_groups (key = title)."""
    from .config import setting  # local import keeps docsync importable without a manifest

    return dict(setting(root, "doc_groups"))


def index_errors(root: Path, files: list[str]) -> list[str]:
    groups = doc_groups(root)
    errors = []
    for path, meta in sorted(doc_meta(root, files).items()):
        entry = meta["index"]
        if entry is not None and (len(entry) != 3 or entry[0] not in groups or not all(entry)):
            errors.append(f"{path}: index declaration must be '<!-- index: {'|'.join(groups)} | owns | read when -->' (groups: project.toml [kit].doc_groups)")
    return errors


def render_index(root: Path, files: list[str], index_doc: str = "docs/README.md") -> str:
    """Markdown tables for every document that declares `<!-- index: -->`."""
    base = Path(index_doc).parent
    titles = doc_groups(root)
    groups: dict[str, list[str]] = {key: [] for key in titles}
    for path, meta in sorted(doc_meta(root, files).items(), key=lambda item: (item[0].count("/"), item[0])):
        entry = meta["index"]
        if not entry or len(entry) != 3 or entry[0] not in titles or path == index_doc:
            continue
        link = Path(os.path.relpath(path, base)).as_posix()
        link = link if link.startswith("../") else f"./{link}"
        groups[entry[0]].append(f"| [`{link.removeprefix('./')}`]({link}) | {entry[1]} | {entry[2]} |")
    blocks = []
    for key, title in titles.items():
        if groups[key]:
            blocks.append(f"### {title}\n\n| Read | Owns | Reach for it when |\n|---|---|---|\n" + "\n".join(groups[key]))
    return "\n\n".join(blocks)


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


# A glob, a trailing slash, or a file-like path; prose such as "UI/UX" or "and/or" stays a reason.
NON_DOC_SCOPE = re.compile(r"\*|/$|/.*/|/[^/]*[._]")


def exemption_scope(values: list[str]) -> set[str] | None:
    """Docs exempted by Docs-Unaffected trailer values; None when nothing valid.

    Each value is `<doc.md ...> <reason>` (named docs only) or `<reason>` (all
    docs). A value without a reason, or one that starts with a non-document path
    or glob, exempts nothing, so an empty or bare trailer
    cannot silence the gate. The commit gate and the history check share this.
    """
    scope: set[str] = set()
    for value in values:
        tokens = value.split()
        docs = {token.rstrip(".,;:") for token in tokens if token.rstrip(".,;:").endswith(".md")}
        reason = [token for token in tokens if token.rstrip(".,;:") not in docs]
        # "tools/** untouched" names a scope that is not a document: in the build trial it
        # silently exempted every doc in a 15k-line commit. Name the doc instead.
        if not docs and tokens and NON_DOC_SCOPE.search(tokens[0]):
            continue
        if reason:
            scope |= docs or {"*"}
    return scope or None


def message_trailers(root: Path, message: str) -> list[str]:
    """Docs-Unaffected values exactly as git parses commit trailers."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "interpret-trailers", "--parse"],
            input=message, capture_output=True, text=True, timeout=30, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    values = []
    for line in result.stdout.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == UNAFFECTED_TRAILER.lower():
            values.append(value.strip())
    return values


def _history(root: Path, revisions: str | None = None) -> list[tuple[str, set[str] | None, set[str]]]:
    """Newest-first (commit, Docs-Unaffected scope, paths); scope None = no trailer."""
    output = git(
        root,
        "log",
        *([revisions] if revisions else []),
        f"-n{HISTORY_LIMIT}",
        "--no-merges",
        "--name-only",
        f"--format=%x1e%h%x1f%(trailers:key={UNAFFECTED_TRAILER},valueonly,separator=%x1d)%x1f",
        timeout=60,
    )
    commits = []
    for record in (output or "").split("\x1e"):
        if not record.strip():
            continue
        commit, trailer, names = (record.split("\x1f") + ["", ""])[:3]
        scope = exemption_scope([value for value in trailer.split("\x1d") if value.strip()])
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


def makefile_targets(root: Path, directory: str = "") -> set[str]:
    makefile = f"{directory}/Makefile" if directory else "Makefile"
    text = read_text_file(root, makefile) or ""
    for included in re.findall(r"(?m)^-?include\s+(\S+)\s*$", text):  # e.g. kit.mk after make adopt
        text += "\n" + (read_text_file(root, f"{directory}/{included}" if directory else included) or "")
    return set(re.findall(r"(?m)^([A-Za-z0-9][A-Za-z0-9_-]*):", text))


def nearest_makefile_dir(files: set[str], relative: str) -> str:
    """A document's `make X` means the closest Makefile above it (subprojects, fixtures, monorepos)."""
    directory = str(Path(relative).parent)
    while directory not in {"", "."}:
        if f"{directory}/Makefile" in files:
            return directory
        directory = str(Path(directory).parent)
    return ""


def repoctl_commands(root: Path) -> set[str]:
    if not (root / "tools" / "repoctl.py").is_file():
        return set()
    from .registry import Registry
    return {item.name for item in Registry(root).of("command", enabled_only=False)}


def command_reference_errors(root: Path, files: list[str]) -> list[str]:
    """Backticked `make X` / `repoctl X` and fenced `make X` lines must name real commands."""
    targets = makefile_targets(root)
    commands = repoctl_commands(root)
    if not targets and not commands:
        return []
    file_set = set(files)
    nested: dict[str, set[str]] = {}
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
        directory = nearest_makefile_dir(file_set, relative)
        local = targets if not directory else nested.setdefault(directory, makefile_targets(root, directory))
        if local:
            for target in sorted(references - local):
                errors.append(f"{relative}: references missing make target: make {target}")
        if commands:
            for command in sorted(set(REPOCTL_REFERENCE.findall(text)) - commands):
                errors.append(f"{relative}: references missing repoctl command: {command}")
    return errors
