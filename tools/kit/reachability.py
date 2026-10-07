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

`advisories` reports them, and every one is advice rather than a gate. A blocking
finding is a claim about a file whose loader the kit has to model, and three rounds
of narrowing showed that claim failing in a new ecosystem each time: an uncovered
`src/`, an unresolvable `module:callable`, an adopted project's own `tools/`. The
honest claim is "nothing in this tree names this file", and that is a judgement for
the person who owns the file — especially in a repository with no upgrade path, where
a wrong block is permanent and there is no way out but editing kit files.

What the classification is for is making the advice trustworthy rather than noisy.
Each message says *why* a file may still be legitimate — a test tree a runner
discovers, a framework tree a migration runner walks, host configuration a tool
reads by fixed name — and names the fix for the rest. The enforcement the repository
actually relies on lives elsewhere and is exact: `covers:` bindings through
`dead-bindings` and `surface-docs`.

Every finding names its fix. The scan is one regex pass over the text already on
disk plus dict lookups, so it costs the same order as the marker and budget checks
reading the same files.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config, navigate, session
from .core import IGNORED_WALK_DIRECTORIES, REPOSITORY_INFRASTRUCTURE_DIRECTORIES, read_text_file
from .derive import DELEGATION_DOC, INDEX_DOC
from .gitinfo import path_matches
from .kitupdate import LOCK
from .names import DESIGN, HANDOVER, STACK_DECISION, VISION

# A path-like run: a name, a relative path, a directory, or `module:callable`. Starts
# with a word character so prose ("3 days") never looks like a path. The colon keeps
# `gunicorn notes.app:create_app` and `uvicorn asgi:application` in one token, so the
# callable half does not hide the module half. The constant avoids the bare word
# "token", which the secret scanner reads as a credential assignment.
PATH_TOKEN = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.:/+@-]*")
CALLED = ":"  # `module:callable` and `path:line` name the same file twice over
RELATIVE_PREFIX = re.compile(r"^(?:\./|\.\./)+")  # a Markdown link names the target relative to its document
SCAN_LIMIT = 400_000  # the size navigate.py searches; larger files are not reference sources
CONFIG_SUFFIXES = frozenset({".toml", ".yml", ".yaml", ".json", ".ini", ".cfg", ".mk"})
# Runtime files a tool loads by a fixed name and no suffix, so the suffix rule misses them.
# Their commands are real references: a Procfile's `web: app:factory` runs the module.
NAMED_CONFIGS = frozenset({"Makefile", "Procfile", "Dockerfile", "Containerfile"})
# Paths the kit itself creates or opens by name, collected from the kit's own
# constants so the list cannot drift from the code that writes them. A project must
# never declare one of these in project.toml to make a check pass: a kit artifact is
# not the project's to justify, and this is scaffolding a project adapts forever,
# with no upgrade path out of a wrong block.
KIT_OWNED = frozenset({
    "project.toml",  # core.load_project
    LOCK,  # make init / make kit-update
    INDEX_DOC, DELEGATION_DOC, "AGENTS.md", "README.md", "Makefile", "kit.mk",  # derive.render_blocks
    VISION, STACK_DECISION, DESIGN,  # make init intake, the design-record check
    HANDOVER, session.CRITIC_RECORD, session.CHECKPOINT,  # make handover, make done
    "review.md",  # the critic's record; a surface names it later in critic_evidence
    *navigate.MEMORY_FILES,  # the failure ledger `where` searches
})
# Documents the kit expects a project to carry whether or not anything binds them
# (config.DEFAULTS["unbound_docs_ok"]): policy records, not owners of code.
KIT_OWNED_PATTERNS = tuple(config.DEFAULTS["unbound_docs_ok"])
# Infrastructure a runner or a build loads by convention rather than by a path some
# file spells out, so the kit cannot tell a stray file from a discovered one. Every
# infrastructure directory except the two a person reads through a `covers:` binding
# or an import, which get the plain "nothing names it" message instead.
DISCOVERED_ROOTS = REPOSITORY_INFRASTRUCTURE_DIRECTORIES - {"docs", "tools"}
# Framework trees a Python tool walks by convention rather than by import: a migration
# runner applies `migrations/`, Django loads `management/commands/`. Neither is an
# import graph, so an unimported module there is not evidence of an orphan. Matched on
# any path segment, because a real app nests them: `apps/store/migrations/`. Reported
# with that explanation rather than dropped: silence would mask a file the framework
# stopped using, which is the one thing a gardener should hear about.
FRAMEWORK_TREES = frozenset({"migrations", "management"})
# Files a host or an external tool reads by fixed path: editors open a root
# dot-file, git reads the attributes file, a host renders the root entry documents
# and its own conventions, a scanner reads its state directory. Nothing inside the
# tree can name them, so they get their own report rather than the plain one.
ENTRY_DOCUMENTS = frozenset({"README.md", "CHANGELOG.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md",
                             "CODE_OF_CONDUCT.md"})
CONVENTION_DIRECTORIES = (".github", ".security")
AUTO_LOADED_PYTHON = frozenset({"conftest.py", "sitecustomize.py", "usercustomize.py"})


def _is_configuration(path: str) -> bool:
    """Toolchain configuration: where a directory, a module, or a command names a load path."""
    return (path.rsplit("/", 1)[-1] in NAMED_CONFIGS or path.endswith(tuple(CONFIG_SUFFIXES)))


def _suffix_index(paths: list[str]) -> dict[str, list[str]]:
    """Every trailing path segment a reference could use: `x.md`, `legal/x.md`, `docs/legal/x.md`.

    A segment two files share (`README.md`, two `index.py`) is not evidence about either:
    `_resolve` drops ambiguous names, so a mention cannot mask a dead file.
    """
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
    """Module name -> the Python files an import can reach.

    A package's `__init__.py` is reachable under two names, and both matter: `__init__`
    when something imports the file directly, and the package name (`kit`) because
    `import kit.checks` or `importlib.import_module("kit.checks")` executes it first.
    Keying only by stem made every package initialiser look like a dead module.
    """
    modules: dict[str, list[str]] = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        stem = path.rsplit("/", 1)[-1][:-3]
        modules.setdefault(stem, []).append(path)
        if stem == "__init__":
            modules.setdefault(str(Path(path).parent.name), []).append(path)
    return modules


def _resolve(candidate: str, index: dict[str, list[str]], modules: dict[str, list[str]],
             members: dict[str, list[str]], kind: int) -> tuple[str, ...]:
    """The files one run of text names.

    `kind` is 0 for prose (a document), 1 when the source is code, and 2 when it is toolchain
    configuration. Code and configuration both name modules — by import, or by
    `module:callable` in a Dockerfile, compose file, or Procfile — while prose does not,
    because a word in a sentence is not a reference.
    """
    candidate = RELATIVE_PREFIX.sub("", candidate.rstrip(".-+").rstrip("/"))  # `../legal/x.md` names `legal/x.md`
    if len(candidate) < 3 or "*" in candidate or "?" in candidate:
        return ()  # a glob: ownership comes from `covers:`, not from a stray pattern
    # `module:callable`, `path:line` and `dotted.module` all name their first part too.
    names = [candidate] + ([part for part in candidate.split(CALLED) if part] if CALLED in candidate else [])
    hits: list[str] = []
    for name in names:
        hits += _unambiguous(index.get(name, []))
        if kind:  # code or configuration: an import, or `module:callable`, names the module
            # `pkg.mod` names `pkg` too: importing a submodule executes every package
            # initialiser on the way, which is why an `__init__.py` is keyed by its package name.
            for part in (name, *name.split("."), name.rsplit(".", 1)[-1]):
                hits += _unambiguous(modules.get(part.lstrip("."), []))
        if kind & 2:
            # A load root is named precisely BECAUSE it has several members (`discover -s
            # tests`, `PYTHONPATH=tools/tests`), so ambiguity is the signal here, not a
            # guess: a single-segment directory counts too.
            hits += members.get(name, [])
    return tuple(dict.fromkeys(hits))


def _unambiguous(candidates: list[str]) -> list[str]:
    """One name several files answer to (`index.py` in two packages) references none of them.

    Otherwise a single stray mention of a common file name would mark every file with
    that name as used, and a dead one would never be reported again.
    """
    return candidates if len(candidates) == 1 else []


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
        kind = (1 if source.endswith(".py") else 0) | (2 if _is_configuration(source) else 0)  # 0 is prose
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


def advisories(context) -> tuple[list[str], list[str]]:
    """(unreferenced, host-read) findings: every tracked file nothing names, and why each may be fine.

    Both lists are advice. The split only routes each finding to the check that explains
    it: host-read configuration has its own report, everything else the general one.
    """
    files = [path for path in context.files if not _scratch(path)]
    owned = declared_owners(files, context.bindings, context.derived)
    repository = context.project.get("repository", {})
    declared = repository.get("infrastructure_paths", []) if isinstance(repository, dict) else []
    infrastructure = {path for pattern in declared if isinstance(pattern, str)
                      for path in files if path_matches(path, pattern)}
    referenced = referrers(context.root, files)
    unreferenced, host_read = [], []
    for path in files:
        if path in owned or path in infrastructure or referenced[path] - {path}:
            continue
        if _conventional(path):
            host_read.append(f"{path}: nothing names this unambiguously and a host reads it by fixed path, so it is "
                             "advice rather than a judgement; reference it, or list it in "
                             "[repository].infrastructure_paths in project.toml to stop seeing it")
        elif path.split("/")[0] in DISCOVERED_ROOTS:
            unreferenced.append(f"{path}: nothing names this unambiguously and a test or build runner discovers it, "
                                "so it is worth a look, not a judgement; import it where it is used, or list its "
                                "directory in [repository].infrastructure_paths in project.toml")
        elif FRAMEWORK_TREES.intersection(path.split("/")[:-1]):
            unreferenced.append(f"{path}: a framework tree a tool walks by convention (a migration runner, a management "
                                "command), so no file is named and that is expected; delete it only if the framework "
                                "stopped using it")
        else:
            unreferenced.append(f"{path}: nothing in the tree names it unambiguously; import or call it, add "
                                f"`<!-- covers: {path} -->` to the document that explains it, or delete it if it is "
                                "dead (confirm first: a framework, manifest, or runner may load it by convention)")
    return unreferenced, host_read
