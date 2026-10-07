"""Report what this checkout and machine can do, without revealing any secret.

First every capability of the repository by kind and pack (docs/adr/0002),
including packs that are switched off and how to switch them on; then whether
this machine can browse, search, read current docs, file issues, or run
containers, so agents learn a gap up front instead of mid-task.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .adapters import configured_hosts
from .registry import KINDS, Registry, downgrade_lines

TOOLS = {
    "git": "version control",
    "gh": "GitHub issues/PRs (issue-backed write-ahead record)",
    "node": "JavaScript runtime",
    "npx": "runs pinned stdio MCP servers such as Playwright",
    "uv": "Python tool runner",
    "docker": "containers / reproducible services",
}
AGENT_HOSTS = {
    "claude": "Claude Code", "codex": "Codex CLI", "gemini": "Gemini CLI",
    "cursor-agent": "Cursor CLI", "copilot": "Copilot CLI",
}


def _gh_authenticated() -> bool:
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=15, check=False).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def print_downgraded_checks(registry: Registry) -> None:
    registry.check_overrides  # noqa: B018 - validates the table; a bad entry is an error, not a quiet omission
    lines = downgrade_lines(registry.project)
    if lines:
        print("\n## Checks this project downgraded to advisory (project.toml [checks]; delete the entry to block again)")
        print("\n".join(f"- {line}" for line in lines))


def print_capabilities(root: Path) -> None:
    registry = Registry(root)
    print("## Packs (project.toml [packs] overrides each default)")
    for pack in registry.of("pack", enabled_only=False):
        state = "on" if registry.enabled(pack) else f"off (enable: {pack.name} = true under [packs])"
        print(f"- {pack.name} [{state}]: {pack.description}")
    print("\n## Capabilities by kind (make where Q=<name> opens one; make new KIND=<kind> adds one)")
    for kind in KINDS:
        if kind in {"pack", "doc"}:
            continue
        names = [item.name + ("" if registry.enabled(item) else f" (off: {item.pack})") for item in registry.of(kind, enabled_only=False)]
        print(f"- {kind} ({len(names)}): {', '.join(names) or 'none'}")
    print(f"- doc ({len(registry.of('doc'))}): indexed in docs/README.md")
    print_downgraded_checks(registry)
    print(f"\npython: {sys.version.split()[0]} ({'ok' if sys.version_info >= (3, 11) else 'needs 3.11+'})")
    print("\n## Tools on PATH")
    for tool, purpose in TOOLS.items():
        found = shutil.which(tool)
        status = "yes" if found else "missing"
        if tool == "gh" and found:
            status += ", authenticated" if _gh_authenticated() else ", NOT authenticated"
        print(f"- {tool}: {status} — {purpose}")
    print("\n## Agent hosts installed")
    print("- " + ", ".join(f"{label}: {'yes' if shutil.which(binary) else 'no'}" for binary, label in AGENT_HOSTS.items()))
    print(
        f"- adapters generated for: {', '.join(configured_hosts(root)) or 'none'} "
        "(Codex/Copilot/Cursor read AGENTS.md and .agents/ directly)"
    )
    print("\n## MCP routes (.agents/mcp/)")
    routes = registry.of("mcp", enabled_only=False)
    if not routes:
        print("- none declared")
    for route in routes:
        spec = route.fields
        variables = list(spec.get("env_headers", {}).values())
        keys = ", ".join(f"{name} {'set' if os.environ.get(name) else 'unset'}" for name in variables) or "no key needed"
        runnable = spec["transport"] == "http" or shutil.which(str(spec["command"][0])) is not None
        state = "enabled" if spec.get("enabled") and registry.enabled(route) else "disabled"
        print(f"- {route.name} [{state}, {spec['transport']}, {'runnable' if runnable else 'runner missing'}; {keys}]: {route.description}")
    print("\nWeb access: hosts with built-in search/fetch work without MCP; MCP routes add current docs, search, and a real browser.")
