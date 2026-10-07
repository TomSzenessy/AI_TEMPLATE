#!/usr/bin/env python3
"""Portable repository governance CLI. Standard library only.

This file only routes: every command is declared with `@command` in
tools/kit/commands.py or a project's .agents/commands/*.py, and discovered
through tools/kit/registry.py (docs/adr/0002-one-capability-model.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import tomllib  # noqa: F401 - fail fast with a clear message on old Pythons
except ModuleNotFoundError as error:  # pragma: no cover - exercised on Python 3.10
    raise SystemExit("repoctl requires Python 3.11 or newer") from error

from kit.core import RepoctlError
from kit.registry import Registry

DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def build_parser(registry: Registry) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repoctl")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repository root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for item in registry.of("command", enabled_only=False):
        sub = subparsers.add_parser(item.name, help=item.description)
        for argument in item.fields["args"]:
            sub.add_argument(*argument.flags, **argument.options)
        sub.set_defaults(capability=item)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root_parser = argparse.ArgumentParser(add_help=False)
    root_parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    root = root_parser.parse_known_args(argv)[0].root.resolve()
    try:
        registry = Registry(root)
        arguments = build_parser(registry).parse_args(argv)
        item = arguments.capability
        if item.pack != "core" and not registry.enabled(item):
            raise RepoctlError(registry.enable_hint(item))
        return int(item.fields["run"](root, arguments) or 0)
    except (OSError, RepoctlError) as error:
        print(f"repoctl: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
