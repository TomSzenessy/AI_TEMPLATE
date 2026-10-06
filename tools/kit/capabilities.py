"""Report what this machine and checkout can do, without revealing any secret.

Agents should know up front whether they can browse, search, read current docs,
file issues, or run containers, instead of discovering a gap mid-task.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .adapters import configured_hosts, mcp_routes

TOOLS = {
    "git": "version control",
    "gh": "GitHub issues/PRs (issue-backed write-ahead record)",
    "node": "JavaScript runtime",
    "npx": "runs pinned stdio MCP servers such as Playwright",
    "uv": "Python tool runner",
    "docker": "containers / reproducible services",
}
AGENT_HOSTS = {"claude": "Claude Code", "codex": "Codex CLI", "gemini": "Gemini CLI", "cursor-agent": "Cursor CLI", "copilot": "Copilot CLI"}


def _gh_authenticated() -> bool:
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=15, check=False).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def print_capabilities(root: Path) -> None:
    print(f"python: {sys.version.split()[0]} ({'ok' if sys.version_info >= (3, 11) else 'needs 3.11+'})")
    print("\n## Tools on PATH")
    for tool, purpose in TOOLS.items():
        found = shutil.which(tool)
        status = "yes" if found else "missing"
        if tool == "gh" and found:
            status += ", authenticated" if _gh_authenticated() else ", NOT authenticated"
        print(f"- {tool}: {status} — {purpose}")
    print("\n## Agent hosts installed")
    print("- " + ", ".join(f"{label}: {'yes' if shutil.which(binary) else 'no'}" for binary, label in AGENT_HOSTS.items()))
    print(f"- adapters generated for: {', '.join(configured_hosts(root)) or 'none'} (Codex/Copilot/Cursor read AGENTS.md and .agents/ directly)")
    print("\n## MCP routes (resources.toml)")
    routes = mcp_routes(root)
    if not routes:
        print("- none declared")
    for route in routes:
        variables = list(route.get("env_headers", {}).values())
        keys = ", ".join(f"{name} {'set' if os.environ.get(name) else 'unset'}" for name in variables) or "no key needed"
        runnable = route["transport"] == "http" or shutil.which(str(route["command"][0])) is not None
        print(
            f"- {route['id']} [{'enabled' if route.get('enabled') else 'disabled'}, {route['transport']}, "
            f"{'runnable' if runnable else 'runner missing'}; {keys}]: {route['purpose']}"
        )
    print("\nWeb access: hosts with built-in search/fetch work without MCP; MCP routes add current docs, search, and a real browser.")
