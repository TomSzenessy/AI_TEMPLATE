"""Doc-to-code binding: which document owns which paths, and whether it kept up.

A Markdown document declares the paths it describes with one HTML comment:

    <!-- covers: tools/kit/docsync.py .agents/agents/** -->

From that single declaration the kit derives ownership lookups (`where`, the
after-edit hook), dead bindings (a pattern matching nothing means code moved or
died), stale documents (a later commit touched covered paths but not the doc),
and pending documents (uncommitted covered changes without a doc change).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .core import FENCED_CODE, read_text_file
from .docmeta import doc_meta, owners
from .gitinfo import git, has_history, path_matches
from .registry import Registry, doc_name

UNAFFECTED_TRAILER = "Docs-Unaffected"
HISTORY_LIMIT = 2000


def doc_groups(root: Path) -> dict[str, str]:
    """Docs index sections from project.toml [kit].doc_groups (key = title)."""
    from .config import setting  # local import keeps docsync importable without a manifest

    return dict(setting(root, "doc_groups"))


def index_errors(root: Path, files: list[str]) -> list[str]:
    groups = doc_groups(root)
    errors = []
    owners: dict[str, str] = {}
    for path, meta in sorted(doc_meta(root, files).items()):
        entry = meta["index"]
        if entry is not None and (len(entry) != 3 or entry[0] not in groups or not all(entry)):
            errors.append(
                f"{path}: index declaration must be '<!-- index: {'|'.join(groups)} | owns | read when -->' "
                "(groups: project.toml [kit].doc_groups)"
            )
        elif entry is not None and path.startswith("docs/"):
            name = doc_name(path)
            if name in owners:
                errors.append(f"{path}: doc name {name!r} collides with {owners[name]}")
            owners.setdefault(name, path)
    return errors


# Handoffs are transient continuation records; docs/README.md links the folder instead of listing each.
INDEX_SKIP = ("docs/handoffs/",)


def render_index(root: Path, files: list[str], index_doc: str = "docs/README.md") -> str:
    """Markdown tables for every document that declares `<!-- index: -->`."""
    base = Path(index_doc).parent
    titles = doc_groups(root)
    groups: dict[str, list[str]] = {key: [] for key in titles}
    for path, meta in sorted(doc_meta(root, files).items(), key=lambda item: (item[0].count("/"), item[0])):
        entry = meta["index"]
        if not entry or len(entry) != 3 or entry[0] not in titles or path == index_doc or path.startswith(INDEX_SKIP):
            continue
        link = Path(os.path.relpath(path, base)).as_posix()
        link = link if link.startswith("../") else f"./{link}"
        groups[entry[0]].append(f"| [`{link.removeprefix('./')}`]({link}) | {entry[1]} | {entry[2]} |")
    blocks = []
    for key, title in titles.items():
        if groups[key]:
            blocks.append(f"### {title}\n\n| Read | Owns | Reach for it when |\n|---|---|---|\n" + "\n".join(groups[key]))
    return "\n\n".join(blocks)


GLOB_LITERAL_HINT = " (in a covers glob [ ] and { } are literal characters; only * ? ** are wildcards)"


def dead_bindings(doc_bindings: dict[str, list[str]], files: list[str]) -> list[str]:
    errors = []
    for doc, patterns in sorted(doc_bindings.items()):
        for pattern in patterns:
            if not any(path_matches(path, pattern) for path in files):
                hint = GLOB_LITERAL_HINT if re.search(r"[\[\]{}]", pattern) else ""
                errors.append(f"{doc}: covers pattern matches no file: {pattern}{hint}")
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
    values = []
    for line in (git(root, "interpret-trailers", "--parse", input=message) or "").splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == UNAFFECTED_TRAILER.lower():
            values.append(value.strip())
    return values


BOT_EMAILS = {"49699333+dependabot[bot]@users.noreply.github.com"}
BOT_NAMES = {"dependabot[bot]"}
PIN_LINE = re.compile(r"^[+-]\s*-?\s*uses:\s")
DIFF_FRAMING = ("diff --git ", "index ", "@@", "--- ", "+++ ")


def pin_only_diff(diff: str) -> bool:
    """True when every changed line of a diff is a workflow `uses:` pin (and something changed)."""
    changed = False
    for line in diff.splitlines():
        if not line or line.startswith(DIFF_FRAMING):
            continue
        if not PIN_LINE.match(line):
            return False  # a run: edit, a mode change, a rename, a binary file ...
        changed = True
    return changed


def _is_pin_bump(root: Path, commit: str, email: str, name: str) -> bool:
    """A Dependabot-authored commit that changes only `uses:` pins (one git call, bot commits only)."""
    if email.strip().lower() not in BOT_EMAILS and name.strip().lower() not in BOT_NAMES:
        return False
    diff = git(root, "show", "--format=", "-U0", "--no-color", commit, timeout=60)
    return diff is not None and pin_only_diff(diff)


def history_read(
    root: Path, revisions: str | None = None
) -> list[tuple[str, set[str] | None, set[str]]] | None:
    """Newest-first (commit, Docs-Unaffected scope, paths); scope None = no trailer.

    None means the read failed or timed out; an empty list is a genuinely empty
    history. A pin-only Dependabot commit gets the all-docs scope (not stale).
    """
    output = git(
        root,
        "log",
        *([revisions] if revisions else []),
        f"-n{HISTORY_LIMIT}",
        "--no-merges",
        "--name-only",
        f"--format=%x1e%h%x1f%(trailers:key={UNAFFECTED_TRAILER},valueonly,separator=%x1d)%x1f%ae%x1f%an%x1f",
        timeout=60,
    )
    if output is None:
        return None
    commits = []
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        commit, trailer, email, name, names = (record.split("\x1f") + ["", "", "", ""])[:5]
        scope = exemption_scope([value for value in trailer.split("\x1d") if value.strip()])
        if scope is None and _is_pin_bump(root, commit.strip(), email, name):
            scope = {"*"}
        commits.append((commit.strip(), scope, {line for line in names.splitlines() if line}))
    return commits


def _history(root: Path, revisions: str | None = None) -> list[tuple[str, set[str] | None, set[str]]]:
    """history_read for callers that treat a failed read as no findings (use history_read to tell)."""
    return history_read(root, revisions) or []


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
    return owed_since(root, doc_bindings, f"{merge_base}..HEAD" if merge_base else None, uncommitted)


def owed_since(
    root: Path, doc_bindings: dict[str, list[str]], revisions: str | None, uncommitted: list[str]
) -> dict[str, list[str]]:
    """Covered paths changed in `revisions` or uncommitted, per untouched doc (trailers honoured)."""
    branch_commits = _history(root, revisions) if revisions else []
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
        for fence in FENCED_CODE.findall(text):
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
