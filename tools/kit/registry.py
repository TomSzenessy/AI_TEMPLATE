"""One capability model: every skill, role, rule, pack, MCP route, check, command, and doc.

docs/adr/0002-one-capability-model.md is the decision. Every capability is a
file that declares `name`, `description` ("<what>; <when>"), and an optional
`pack`; this module is the only reader. Adding a file adds the capability:
nothing is registered by hand. Kit checks and commands live in
`tools/kit/checks.py` and `tools/kit/commands.py`; a project adds its own as
new files in `.agents/checks/` and `.agents/commands/`, which `make kit-update`
never touches.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Callable

try:
    import tomllib
except ModuleNotFoundError as error:  # pragma: no cover - exercised on Python 3.10
    raise SystemExit("repoctl requires Python 3.11 or newer") from error

from .core import RepoctlError, load_project, repository_files

KINDS = ("skill", "agent", "rule", "pack", "mcp", "check", "command", "doc")
CORE = "core"
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
BLOCK_SCALAR = re.compile(r"[>|][+-]?")
MAX_DESCRIPTION = 1024  # host skill catalogs truncate or reject longer descriptions
ROLE_ACCESS = {"read-only", "docs-only", "web", "full"}
ROLE_TIERS = {"fast", "balanced", "deep", "inherit"}
PINNED_PACKAGE = re.compile(r"@\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$|==\d+(?:\.\d+)*$")
PLUGIN_DIRS = {"check": ".agents/checks", "command": ".agents/commands"}


@dataclass(frozen=True)
class Capability:
    kind: str
    name: str
    description: str
    path: str
    pack: str = CORE
    fields: dict = field(default_factory=dict, compare=False)

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.name}"


# --- Markdown carriers -------------------------------------------------------

def frontmatter(text: str) -> dict[str, str]:
    """Parse flat YAML frontmatter: plain, quoted, and folded/literal block scalars."""
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    values: dict[str, str] = {}
    lines = match.group(1).splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        key, separator, value = line.partition(":")
        if not separator or line.startswith((" ", "\t")):
            continue
        key, value = key.strip(), value.strip()
        if BLOCK_SCALAR.fullmatch(value):
            block = []
            while index < len(lines) and (not lines[index].strip() or lines[index].startswith((" ", "\t"))):
                block.append(lines[index].strip())
                index += 1
            joiner = "\n" if value.startswith("|") else " "
            values[key] = joiner.join(part for part in block if part).strip()
            continue
        if value[:1] in {"'", '"'}:
            values[key] = value[1:-1] if len(value) > 1 and value[-1] == value[0] else value
            continue
        if ": " in value:
            raise RepoctlError(f"frontmatter value for {key} contains ': '; quote it so every host parses it as YAML")
        values[key] = value
    return values


def yaml_string(value: str) -> str:
    """A double-quoted scalar (JSON strings are valid YAML) on a single line."""
    return json.dumps(" ".join(value.split()), ensure_ascii=False)


def _markdown(root: Path, kind: str, relative: str, name: str) -> Capability:
    values = frontmatter((root / relative).read_text(encoding="utf-8"))
    if values.get("name") != name or not values.get("description"):
        raise RepoctlError(f"{relative} needs name: {name} and a description")
    if len(values["description"]) > MAX_DESCRIPTION:
        raise RepoctlError(f"{relative} description exceeds {MAX_DESCRIPTION} characters")
    extra = {key: value for key, value in values.items() if key not in {"name", "description", "pack"}}
    if kind == "agent":
        if extra.get("access") not in ROLE_ACCESS:
            raise RepoctlError(f"{relative} access must be one of {', '.join(sorted(ROLE_ACCESS))}")
        if extra.get("tier") not in ROLE_TIERS:
            raise RepoctlError(f"{relative} tier must be one of {', '.join(sorted(ROLE_TIERS))}")
    if kind == "rule":
        extra["scope"] = extra.get("scope", "").split()
    if kind == "pack":
        if extra.get("default", "on") not in {"on", "off"}:
            raise RepoctlError(f"{relative} default must be on or off")
        return Capability(kind, name, values["description"], relative, name, extra)
    return Capability(kind, name, values["description"], relative, values.get("pack") or CORE, extra)


def _markdown_kind(root: Path, kind: str, pattern: str) -> list[Capability]:
    items = []
    for path in sorted(root.glob(pattern)):
        if path.name == "README.md" or not path.is_file():
            continue
        name = path.parent.name if path.name == "SKILL.md" else path.stem
        items.append(_markdown(root, kind, path.relative_to(root).as_posix(), name))
    return items


# --- MCP routes --------------------------------------------------------------

def _mcp(root: Path) -> list[Capability]:
    routes, errors = [], []
    for path in sorted((root / ".agents" / "mcp").glob("*.toml")):
        relative = path.relative_to(root).as_posix()
        try:
            route = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            errors.append(f"{relative} is invalid TOML: {error}")
            continue
        label = relative
        if route.get("name") != path.stem:
            errors.append(f"{label} needs name = \"{path.stem}\"")
        if not isinstance(route.get("description"), str) or not route["description"].strip():
            errors.append(f"{label} needs a description")
        transport = route.get("transport")
        if transport == "http":
            url = route.get("url")
            if not isinstance(url, str) or not url.startswith("https://") or "?" in url:
                errors.append(f"{label} url must be HTTPS without query parameters (keys go in env headers)")
        elif transport == "stdio":
            command = route.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
                errors.append(f"{label} command must be a non-empty string array")
            elif command[0] in {"npx", "uvx", "pipx"} and not any(PINNED_PACKAGE.search(part) for part in command[1:]):
                errors.append(f"{label} must pin its package to an exact version")
        else:
            errors.append(f"{label} transport must be http or stdio")
        headers = route.get("env_headers", {})
        if not isinstance(headers, dict) or not all(
            isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", value) for value in headers.values()
        ):
            errors.append(f"{label} env_headers must map header names to UPPER_CASE environment variable names")
        extra = {key: value for key, value in route.items() if key not in {"name", "description", "pack"}}
        routes.append(Capability("mcp", path.stem, str(route.get("description", "")), relative, str(route.get("pack") or CORE), extra))
    if errors:
        raise RepoctlError("mcp routes check failed:\n- " + "\n- ".join(errors))
    return routes


# --- Python plugins: checks and commands --------------------------------------

@dataclass(frozen=True)
class Arg:
    """One command argument: argparse keywords plus the make variable that feeds it."""

    flags: tuple[str, ...]
    var: str | None = None
    hint: str | None = None  # make refuses with this message when `var` is empty
    options: dict = field(default_factory=dict, compare=False)

    @property
    def positional(self) -> bool:
        return not self.flags[0].startswith("-")

    @property
    def boolean(self) -> bool:
        return self.options.get("action") == "store_true"


def arg(*flags: str, var: str | None = None, hint: str | None = None, **options: object) -> Arg:
    return Arg(tuple(flags), var, hint, options)


def command(name: str, description: str, *, group: str = "more", pack: str = CORE, args: tuple[Arg, ...] = (),
            usage: str = "", make: str | None = "", make_extra: str = "", target: str = "") -> Callable:
    """Declare a `repoctl` command. `make=None` means no make target; `make` set to a
    string overrides the generated recipe (adopt runs from the kit's own Makefile);
    `target` names the make target when it differs from the command."""
    def decorate(function: Callable) -> Callable:
        function.__capability__ = Capability("command", name, description, "", pack, {
            "run": function, "group": group, "args": args, "usage": usage, "make": make, "make_extra": make_extra,
            "target": target or name,
        })
        return function
    return decorate


def check(name: str, description: str, *, blocks: bool, reason: str = "", pack: str = CORE) -> Callable:
    """Declare a check: a function of a Context returning findings that each name their fix.
    A blocking check names its evidence (docs/self-healing.md#when-a-check-may-block)."""
    def decorate(function: Callable) -> Callable:
        function.__capability__ = Capability("check", name, description, "", pack, {
            "run": function, "blocks": blocks, "reason": reason,
        })
        return function
    return decorate


def _module_capabilities(module: object, relative: str) -> list[Capability]:
    found = []
    for value in vars(module).values():
        capability = getattr(value, "__capability__", None)
        if isinstance(capability, Capability):
            found.append(Capability(capability.kind, capability.name, capability.description, relative,
                                    capability.pack, capability.fields))
    return found


def _plugins(root: Path) -> list[Capability]:
    found = []
    for module_name, relative in (("kit.checks", "tools/kit/checks.py"), ("kit.commands", "tools/kit/commands.py")):
        found += _module_capabilities(importlib.import_module(module_name), relative)
    for kind, directory in PLUGIN_DIRS.items():
        for path in sorted((root / directory).glob("*.py")):
            relative = path.relative_to(root).as_posix()
            spec = importlib.util.spec_from_file_location(f"project_{kind}_{path.stem.replace('-', '_')}", path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as error:  # noqa: BLE001 - a broken project plugin is a finding, not a crash
                raise RepoctlError(f"{relative} failed to load: {type(error).__name__}: {error}") from error
            declared = _module_capabilities(module, relative)
            if not any(item.kind == kind for item in declared):
                raise RepoctlError(f"{relative} declares no @{kind}; see docs/adr/0002-one-capability-model.md")
            found += declared
    for item in found:
        if not NAME.fullmatch(item.name):
            raise RepoctlError(f"{item.path}: {item.kind} name {item.name!r} must be kebab-case")
        if len(item.description) < 20:
            raise RepoctlError(f"{item.path}: {item.label} needs a description of what it does and when (20+ characters)")
        if item.kind == "check" and item.fields["blocks"] and len(item.fields["reason"].strip()) < 20:
            raise RepoctlError(
                f"{item.path}: blocking {item.label} must give its reason (the evidence that skipping it hurt; "
                "docs/self-healing.md#when-a-check-may-block), or declare blocks=False"
            )
    return found


# --- Docs ----------------------------------------------------------------------

def _docs(root: Path, files: list[str]) -> list[Capability]:
    from .docsync import doc_meta  # docsync owns the comment carrier and its cache
    items = []
    for relative, meta in doc_meta(root, files).items():
        index = meta.get("index")
        if not relative.startswith("docs/") or not index or len(index) < 3:
            continue
        name = relative.removeprefix("docs/").removesuffix(".md").replace("/", "-").lower()
        items.append(Capability("doc", name, f"{index[1]}; {index[2]}", relative, CORE,
                                {"group": index[0], "covers": list(meta.get("covers", []))}))
    return items


# --- The registry --------------------------------------------------------------

class Registry:
    """Every capability of a repository, with pack state. Build once per command."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @cached_property
    def project(self) -> dict[str, object]:
        return load_project(self.root)

    def _load(self, kind: str) -> list[Capability]:
        root = self.root
        loaders = {
            "skill": lambda: self._with_provenance_packs(_markdown_kind(root, "skill", ".agents/skills/*/SKILL.md")),
            "agent": lambda: _markdown_kind(root, "agent", ".agents/agents/*.md"),
            "rule": lambda: _markdown_kind(root, "rule", ".agents/rules/*.md"),
            "pack": lambda: _markdown_kind(root, "pack", ".agents/packs/*.md"),
            "mcp": lambda: _mcp(root),
            "check": lambda: [item for item in self._plugins if item.kind == "check"],
            "command": lambda: [item for item in self._plugins if item.kind == "command"],
            "doc": lambda: _docs(root, repository_files(root)),
        }
        items = loaders[kind]()
        packs = {CORE} | ({item.name for item in items} if kind == "pack" else {item.name for item in self.of("pack", enabled_only=False)})
        seen: dict[str, str] = {}
        for item in items:
            if item.name in seen:
                raise RepoctlError(f"duplicate {item.label}: {seen[item.name]} and {item.path}")
            seen[item.name] = item.path
            # A project's typo is an error; a kit capability whose pack file this repository
            # does not carry (an old or trimmed checkout) simply stays on.
            if item.pack not in packs and item.path.startswith(".agents/"):
                raise RepoctlError(f"{item.path}: unknown pack {item.pack!r} (packs: {', '.join(sorted(packs))})")
        return items

    def _with_provenance_packs(self, skills: list[Capability]) -> list[Capability]:
        """A third-party skill's files are pinned by digest, so its pack is recorded with its provenance."""
        packs = {}
        for entry in self.project.get("skills", []):
            if isinstance(entry, dict) and isinstance(entry.get("pack"), str):
                packs[str(entry.get("package", "")).rpartition("@")[2]] = entry["pack"]
        return [Capability(item.kind, item.name, item.description, item.path, packs.get(item.name, item.pack), item.fields)
                for item in skills]

    @cached_property
    def _plugins(self) -> list[Capability]:
        return _plugins(self.root)

    @cached_property
    def _kinds(self) -> dict[str, list[Capability]]:
        return {}

    @property
    def items(self) -> list[Capability]:
        return [item for kind in KINDS for item in self.of(kind, enabled_only=False)]

    @cached_property
    def pack_state(self) -> dict[str, bool]:
        """Each pack's state: its declared default, overridden by project.toml [packs]."""
        overrides = self.project.get("packs", {})
        if not isinstance(overrides, dict) or not all(isinstance(value, bool) for value in overrides.values()):
            raise RepoctlError("project.toml [packs] must map pack names to true or false")
        state = {item.name: item.fields.get("default", "on") == "on" for item in self.of("pack", enabled_only=False)}
        unknown = sorted(set(overrides) - set(state))
        if unknown:
            raise RepoctlError(f"project.toml [packs] names unknown packs: {', '.join(unknown)} (known: {', '.join(sorted(state))})")
        state.update(overrides)
        state[CORE] = True
        return state

    def enabled(self, item: Capability) -> bool:
        return self.pack_state.get(item.pack, True)

    def of(self, kind: str, *, enabled_only: bool = True) -> list[Capability]:
        if kind not in self._kinds:
            self._kinds[kind] = self._load(kind)
        return [item for item in self._kinds[kind] if not enabled_only or self.enabled(item)]

    def get(self, kind: str, name: str) -> Capability | None:
        return next((item for item in self.of(kind, enabled_only=False) if item.name == name), None)

    def enable_hint(self, item: Capability) -> str:
        return f"{item.label} is in the {item.pack!r} pack, which is off: set `{item.pack} = true` under [packs] in project.toml"


class Context:
    """What a check sees: the repository root plus shared, lazily computed facts."""

    def __init__(self, root: Path, registry: Registry | None = None) -> None:
        self.root = root
        self.registry = registry or Registry(root)

    @property
    def project(self) -> dict[str, object]:
        return self.registry.project

    @cached_property
    def files(self) -> list[str]:
        return repository_files(self.root)

    @cached_property
    def bindings(self) -> dict[str, list[str]]:
        from .docsync import bindings
        return bindings(self.root, self.files)

    @cached_property
    def derived(self) -> set[str]:
        """Files `make sync` writes; a generated file is referenced by its generator."""
        from .derive import render_all  # local import: derive imports this module
        return set(render_all(self.root))

    @cached_property
    def orphans(self) -> tuple[list[str], list[str]]:
        """(blocking, advisory) tracked files nothing references; computed once per run."""
        from .reachability import orphans
        return orphans(self)

    @cached_property
    def signatures(self) -> tuple:
        """The failure signatures in docs/ERROR_LOG.md, so a repeat is recognised in one step."""
        from .signatures import signatures
        return signatures(self.root)


def run_checks(root: Path, *, blocking_only: bool, context: Context | None = None,
               skip: frozenset[str] = frozenset()) -> tuple[list[str], list[str]]:
    """(blocking findings, advisory findings) from every check of an enabled pack, minus `skip`.

    A finding that repeats a signature already in docs/ERROR_LOG.md is followed by that
    signature's key and permanent fix, so a known failure is recognised rather than
    diagnosed again.
    """
    context = context or Context(root)
    hard: list[str] = []
    advisory: list[str] = []
    for item in context.registry.of("check"):
        if (blocking_only and not item.fields["blocks"]) or item.name in skip:
            continue
        try:
            findings = list(item.fields["run"](context))
        except RepoctlError as error:
            findings = [str(error)]
        (hard if item.fields["blocks"] else advisory).extend(findings)
    if hard:
        from .signatures import recognition
        hard += recognition(hard, context.signatures)
    return hard, advisory
