"""Running the checks: the context a check sees, and the one place a finding becomes blocking.

Split from `registry` because a check's context reaches up (generated files,
reachability, failure signatures) while the registry is read by those same
modules. Everything that needs `Context` or `run_checks` imports it here.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from .core import RepoctlError, repository_files
from .docmeta import bindings
from .registry import Registry


class Context:
    """What a check sees: the repository root plus shared, lazily computed facts."""

    def __init__(self, root: Path, registry: Registry | None = None, scope: list[str] | None = None) -> None:
        self.root = root
        self.registry = registry or Registry(root)
        self.scope = scope  # the paths a gate is judging; None means the whole repository

    @cached_property
    def scoped_files(self) -> list[str]:
        """Tracked files a scope-aware check inspects: the gate's scope, else every file."""
        if self.scope is None:
            return self.files
        wanted = set(self.scope)
        return [path for path in self.files if path in wanted]

    @property
    def project(self) -> dict[str, object]:
        return self.registry.project

    @cached_property
    def files(self) -> list[str]:
        return repository_files(self.root)

    @cached_property
    def bindings(self) -> dict[str, list[str]]:
        return bindings(self.root, self.files)

    @cached_property
    def derived(self) -> set[str]:
        """Files `make sync` writes; a generated file is referenced by its generator."""
        from .derive import render_all  # deferred: only the checks that need it pay for it
        return set(render_all(self.root))

    @cached_property
    def advisories(self) -> tuple[list[str], list[str]]:
        """(unreferenced, host-read) files nothing names; computed once per run."""
        from .reachability import advisories
        return advisories(self)

    @cached_property
    def signatures(self) -> tuple:
        """The failure signatures in docs/ERROR_LOG.md, so a repeat is recognised in one step."""
        from .signatures import signatures
        return signatures(self.root)


def run_checks(root: Path, *, blocking_only: bool, context: Context | None = None,
               skip: frozenset[str] = frozenset(), only: frozenset[str] | None = None,
               scope: list[str] | None = None) -> tuple[list[str], list[str]]:
    """(blocking findings, advisory findings) from every check of an enabled pack, minus `skip`.

    This is the one place a finding becomes blocking: gates (`make check`, the commit gate, the
    stop gate) name the checks they want in `only` and `scope` the files a change touches, so no
    gate keeps a rule of its own. A check the project downgraded in `project.toml [checks]`
    still runs, and its findings land in the advisory list.

    Each finding is prefixed `[check-name] ` so the reader knows its source.
    A finding that repeats a signature already in docs/ERROR_LOG.md is followed by that
    signature's key and permanent fix, so a known failure is recognised rather than
    diagnosed again.
    """
    context = context or Context(root, scope=scope)
    registry = context.registry
    hard: list[str] = []
    advisory: list[str] = []
    for item in registry.of("check"):
        blocks = registry.blocks(item)
        downgraded = item.name in registry.check_overrides
        if (blocking_only and not blocks and not downgraded) or item.name in skip or (only is not None and item.name not in only):
            continue
        try:
            findings = list(item.fields["run"](context))
        except RepoctlError as error:
            findings = [str(error)]
        except Exception as error:  # noqa: BLE001 - one broken check must not hide every other check's result
            findings = [f"check {item.name} crashed: {type(error).__name__}: {error} "
                        "(fix the check or the manifest value it reads)"]
        (hard if blocks else advisory).extend(f"[{item.name}] {finding}" for finding in findings)
    if hard:
        from .signatures import recognition
        hard += recognition(hard, context.signatures)
    return hard, advisory
