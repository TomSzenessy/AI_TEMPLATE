#!/usr/bin/env python3
"""Portable repository governance CLI. Standard library only.

This file only routes: every command is declared with `@command` in
tools/kit/commands.py or a project's .agents/commands/*.py, and discovered
through tools/kit/registry.py (docs/adr/0002-one-capability-model.md).
"""

from __future__ import annotations

import argparse
import os
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
    # --root is parsed once, anywhere on the line (before or after the subcommand), then removed.
    root_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    root_parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    known, remaining = root_parser.parse_known_args(argv)
    root = known.root.resolve()
    try:
        registry = Registry(root)
        arguments = build_parser(registry).parse_args(remaining)
        item = arguments.capability
        if item.pack != "core" and not registry.enabled(item):
            raise RepoctlError(registry.enable_hint(item))
        return int(item.fields["run"](root, arguments) or 0)
    except (OSError, RepoctlError) as error:
        if isinstance(error, BrokenPipeError):
            return _broken_pipe()
        print(f"repoctl: {error}", file=sys.stderr)
        return 1
    except BrokenPipeError:  # pragma: no cover - OSError branch above catches it first
        return _broken_pipe()
    except KeyboardInterrupt:
        return 130
    except Exception as error:  # noqa: BLE001 - last resort: one line, not a traceback
        if os.environ.get("REPOCTL_DEBUG") == "1":
            raise
        print(f"repoctl: internal error: {type(error).__name__}: {error} "
              "(rerun with REPOCTL_DEBUG=1 for the traceback)", file=sys.stderr)
        return 1


def _broken_pipe() -> int:
    """The reader (`| head`) closed the pipe: exit quietly with status 0 and silence the flush-at-exit error."""
    try:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except (OSError, ValueError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
