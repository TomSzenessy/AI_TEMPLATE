"""The reference graph: which tracked files something actually points at (issue #17).

A repository stays compact only while every file earns its place, and "earns its
place" has to be checkable rather than asserted. A tracked file is *reachable*
when its owner is declared or named:

- a document's `<!-- covers: -->` glob (the same declaration `where` and the
  after-edit hook use, so this adds no second inventory to drift from),
- the generator that writes it (`make sync` owns `.claude/`, `.mcp.json`, and
  the `repoctl` blocks),
- `[repository].infrastructure_paths`, the project's declared escape hatch,
- another file's text naming it by path (`tools/kit/checks.py`, `checks.py`),
- a Python file importing it by module name (`from . import checks`),
- toolchain configuration naming a directory it loads as a unit (a Makefile
  `PYTHONPATH`, a test search root). Prose naming a tree is not a reference:
  a reader still has to know which file they want.

Globs outside a `covers:` binding are deliberately not references. A `[risk]`
tier or a `[budgets]` glob says how careful to be with a path, not that anything
uses it, and treating them as references would let a manifest silence the whole
check.

What is left is an orphan: no code imports it, no test exercises it, no config
reads it, and no document claims it, so every reader pays for a file nobody owns.
`orphans` splits them by how certain the kit can be, and each finding names its
fix. Blocking: files a person reads through a binding or an import, where nothing
else could have meant it. Advisory: files a runner, a build, or a host reads by
convention (`tests/`, `.editorconfig`, `.github/pull_request_template.md`), where
the kit cannot tell a stray file from a discovered one — a wrongly blocked project
has no upgrade path, and this is scaffolding a project adapts forever.

The scan is one regex pass over the text already on disk plus dict lookups, so
it costs the same order as the marker and budget checks reading the same files.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config, navigate, session
from .core import IGNORED_WALK_DIRECTORIES, REPOSITORY_INFRASTRUCTURE_DIRECTORIES, read_text_file
from .derive import DELEGATION_DOC, INDEX_DOC
from .gitinfo import path_matches
from .kitupdate import LOCK

# A path-like run: a name, a relative path, or a directory. Starts with a word
# character so prose ("3 days") never looks like a path. The constant avoids the
# bare word "token", which the secret scanner reads as a credential assignment.
PATH_TOKEN = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.*/+@-]*")
RELATIVE_PREFIX = re.compile(r"^(?:\./|\.\./)+")  # a Markdown link names the target relative to its document
SCAN_LIMIT = 400_000  # the size navigate.py searches; larger files are not reference sources
CONFIG_SUFFIXES = frozenset({".toml", ".yml", ".yaml", ".json", ".ini", ".cfg", ".mk"})
# Paths the kit itself creates or opens by name, collected from the kit's own
# constants so the list cannot drift from the code that writes them. A project must
# never declare one of these in project.toml to make a check pass: a kit artifact is
# not the project's to justify, and this is scaffolding a project adapts forever,
# with no upgrade path out of a wrong block.
KIT_OWNED = frozenset({
    "project.toml",  # core.load_project
    LOCK,  # make init / make kit-update
    INDEX_DOC, DELEGATION_DOC, "AGENTS.md", "README.md", "Makefile", "kit.mk",  # derive.render_blocks
    "VISION.md", "docs/STACK-DECISION.md", "docs/design.md",  # make init intake, the design-record check
    "HANDOVER.md", session.CRITIC_RECORD, session.CHECKPOINT,  # make handover, make done
    "review.md",  # the critic's record; a surface names it later in critic_evidence
    *navigate.MEMORY_FILES,  # the failure ledger `where` searches
})
# Documents the kit expects a project to carry whether or not anything binds them
# (config.DEFAULTS["unbound_docs_ok"]): policy records, not owners of code.
KIT_OWNED_PATTERNS = tuple(config.DEFAULTS["unbound_docs_ok"])
# Infrastructure a runner or a build loads by convention rather than by a path some
# file spells out, so the kit cannot tell a stray file from a discovered one. Every
# infrastructure directory except the two a person reads through a `covers:` binding
# or an import; `docs/` and `tools/` stay blocking, because nothing else reads them.
DISCOVERED_ROOTS = REPOSITORY_INFRASTRUCTURE_DIRECTORIES - {"docs", "tools"}
# Files a host or an external tool reads by fixed path: editors open a root
# dot-file, git reads the attributes file, a host renders the root entry
# documents and its own conventions, a scanner reads its state directory.
# Nothing inside the tree can name them, so the kit reports them (with the fix)
# but never blocks: this is scaffolding a project adapts forever, and a wrongly
# blocked project has no upgrade path out.
ENTRY_DOCUMENTS = frozenset({"README.md", "CHANGELOG.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md",
                             "CODE_OF_CONDUCT.md"})
CONVENTION_DIRECTORIES = (".github", ".security")


def _is_configuration(path: str) -> bool:
    """Toolchain configuration: the one place a directory names a load path."""
    return path == "Makefile" or path.startswith("Makefile.") or path.endswith(tuple(CONFIG_SUFFIXES))


def _suffix_index(paths: list[str]) -> dict[str, list[str]]:
    """Every trailing path segment a reference could use: `x.md`, `legal/x.md`, `docs/legal/x.md`."""
    index: dict[str, list[str]] = {}
    for path in paths:
        parts = path.split("/")
        for position in range(len(parts)):
            index.setdefault("/".join(parts[position:]), []).append(path)
    return index


def _directory_members(paths: list[str]) -> dict[str, list[str]]:
    """Directory -> the files directly inside it, minus importable packages.

    A package is named module by module; a plain directory (a `PYTHONPATH`, a
    test search root) is loaded as a unit, so naming it names what is in it.
    """
    members: dict[str, list[str]] = {}
    packages = {str(Path(path).parent) for path in paths if path.endswith("__init__.py")}
    for path in paths:
        directory = str(Path(path).parent)
        if "/" not in path or directory in packages:
            continue
        members.setdefault(directory, []).append(path)
    return members


def _modules(paths: list[str]) -> dict[str, list[str]]:
    """Module name -> the Python files an import can reach."""
    modules: dict[str, list[str]] = {}
    for path in paths:
        if path.endswith(".py"):
            modules.setdefault(path.rsplit("/", 1)[-1][:-3], []).append(path)
    return modules


def _resolve(candidate: str, index: dict[str, list[str]], modules: dict[str, list[str]],
             members: dict[str, list[str]], kind: int) -> tuple[str, ...]:
    """The files one run of text names. `kind` is 1 for Python sources and 2 for configuration."""
    candidate = RELATIVE_PREFIX.sub("", candidate.rstrip(".-+").rstrip("/"))  # `../legal/x.md` names `legal/x.md`
    if len(candidate) < 3 or "*" in candidate or "?" in candidate:
        return ()  # a glob: ownership comes from `covers:`, not from a stray pattern
    hits = list(index.get(candidate, []))
    if kind & 1:  # a relative or dotted import names the module it resolves to
        hits += modules.get(candidate.lstrip("."), []) + modules.get(candidate.rsplit(".", 1)[-1], [])
    if kind & 2 and "/" in candidate:  # configuration names a directory it loads as a unit
        hits += members.get(candidate, [])
    return tuple(hits)


def referrers(root: Path, files: list[str]) -> dict[str, set[str]]:
    """Each file mapped to the files whose text names it. Self-mentions do not count."""
    index = _suffix_index(files)
    modules = _modules(files)
    members = _directory_members(files)
    resolved: dict[tuple[str, int], tuple[str, ...]] = {}
    found: dict[str, set[str]] = {path: set() for path in files}
    for source in files:
        text = read_text_file(root, source, limit=SCAN_LIMIT)
        if text is None:
            continue
        kind = (1 if source.endswith(".py") else 0) | (2 if _is_configuration(source) else 0)
        for candidate in set(PATH_TOKEN.findall(text)):
            key = (candidate, kind)
            targets = resolved.get(key)
            if targets is None:
                targets = resolved[key] = _resolve(candidate, index, modules, members, kind)
            for target in targets:
                found[target].add(source)
    return found


def declared_owners(files: list[str], bindings: dict[str, list[str]], derived: set[str]) -> set[str]:
    """Files whose owner is declared rather than named: a kit artifact, a binding, or generated output."""
    owned = set(derived) | KIT_OWNED
    for pattern in (*KIT_OWNED_PATTERNS, *(p for document in bindings.values() for p in document)):
        owned |= {path for path in files if path_matches(path, pattern)}
    return owned


def _scratch(path: str) -> bool:
    """A file inside one of the kit's or the host's working directories, not repository content."""
    return any(part in IGNORED_WALK_DIRECTORIES for part in path.split("/")[:-1])


def _conventional(path: str) -> bool:
    """True when a host reads this file by fixed name, so no reference can exist."""
    parts = path.split("/")
    if len(parts) == 1:
        return path in ENTRY_DOCUMENTS or path.startswith(".")
    return parts[0] in CONVENTION_DIRECTORIES and len(parts) == 2


def orphans(context) -> tuple[list[str], list[str]]:
    """(blocking, advisory) tracked files nothing references, each naming its fix."""
    files = [path for path in context.files if not _scratch(path)]
    owned = declared_owners(files, context.bindings, context.derived)
    repository = context.project.get("repository", {})
    declared = repository.get("infrastructure_paths", []) if isinstance(repository, dict) else []
    infrastructure = {path for pattern in declared if isinstance(pattern, str)
                      for path in files if path_matches(path, pattern)}
    referenced = referrers(context.root, files)
    blocking, advisory = [], []
    for path in files:
        if path in owned or path in infrastructure or referenced[path] - {path}:
            continue
        if _conventional(path):
            advisory.append(f"{path}: no file in the tree references this host-read configuration; reference it, "
                            "or list it in [repository].infrastructure_paths in project.toml to stop seeing it")
        elif path.split("/")[0] in DISCOVERED_ROOTS:
            advisory.append(f"{path}: a test, example, or build tree nothing names; import it where it is used, "
                            "or list its directory in [repository].infrastructure_paths in project.toml")
        else:
            blocking.append(
                f"{path}: nothing references it; import or call it, add `<!-- covers: {path} -->` to the document "
                "that explains it, or delete it (a file a tool loads by convention belongs in "
                "[repository].infrastructure_paths in project.toml)"
            )
    return blocking, advisory