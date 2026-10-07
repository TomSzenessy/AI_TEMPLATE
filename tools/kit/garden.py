"""The gardener: every check's findings in one report, plus each surface's garden commands.

The checks themselves are declared in kit/checks.py (and a project's
.agents/checks/). `self_heal_errors` is the hard gate used by `make check`;
`garden_report` adds the advisory checks and each surface's own `garden`
commands (for example a dead-code finder) and renders Markdown suitable for a
CI job summary or a gardener agent's brief.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .config import setting
from .core import declared_surfaces, ensure_inside_root, load_project, verification_environment
from .registry import Registry, run_checks



def self_heal_errors(root: Path) -> list[str]:
    """Findings of every blocking check in an enabled pack: the hard gate behind make check."""
    return run_checks(root, blocking_only=True)[0]


NPM_PIN = re.compile(r"^(@?[a-z0-9][\w.-]*(?:/[\w.-]+)?)@(\d+\.\d+\.\d+[\w.-]*)$")


def npm_pins(root: Path) -> list[tuple[str, str, str]]:
    """(package, pinned version, where) for npm pins the kit itself chooses."""
    pins = [("playwright", str(setting(root, "playwright_version")), "[kit].playwright_version")]
    for route in Registry(root).of("mcp", enabled_only=False):
        for token in route.fields.get("command", []):
            match = NPM_PIN.match(token)
            if match:
                pins.append((match.group(1), match.group(2), route.path))
    return pins


def pin_drift(root: Path, view=None) -> list[str]:
    """Advisory: a pinned tool behind its latest release. Bump deliberately, never automatically."""
    if view is None:
        if shutil.which("npm") is None:
            return []

        def view(package: str) -> str | None:
            try:
                result = subprocess.run(["npm", "view", package, "version"], capture_output=True, text=True, timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired):
                return None
            return result.stdout.strip() if result.returncode == 0 else None
    findings = []
    for package, pinned, where in npm_pins(root):
        latest = view(package)
        if latest and latest != pinned:
            findings.append(
                f"pin {package}@{pinned} ({where}) is behind {latest}: "
                "check its changelog, then bump and re-run the affected checks"
            )
    return findings


def surface_garden_commands(project: dict[str, object]) -> list[tuple[str, list[str], str]]:
    commands = []
    for surface in declared_surfaces(project):
        if surface.get("status", "active") != "active":
            continue
        garden = surface.get("garden", [])
        for command in garden if isinstance(garden, list) else []:
            if isinstance(command, list) and command and all(isinstance(part, str) for part in command):
                commands.append((str(surface.get("id")), command, str(surface.get("path", "."))))
    return commands


def garden_report(root: Path) -> tuple[str, int]:
    project = load_project(root)
    hard, advisory = run_checks(root, blocking_only=False)

    surface_results = []
    failures = 0
    for identifier, command, path in surface_garden_commands(project):
        cwd = ensure_inside_root(root, root / path, f"surface {identifier} path")
        try:
            result = subprocess.run(
                command, cwd=cwd if cwd.is_dir() else cwd.parent, capture_output=True, text=True,
                timeout=900, check=False, env=verification_environment(),
            )
            output = (result.stdout + result.stderr).strip().splitlines()[-15:]
            status = "ok" if result.returncode == 0 else f"exit {result.returncode}"
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            output, status = [str(error)], "did not run"
        failures += status != "ok"
        surface_results.append((identifier, " ".join(command), status, output))

    lines = ["# Garden report", ""]
    lines.append(
        f"Hard findings (fail `make check`): {len(hard)} · advisory: {len(advisory)} · "
        f"surface garden commands: {len(surface_results)}"
    )
    for title, items in (("Hard findings", hard), ("Advisory", advisory)):
        lines += ["", f"## {title}", ""] + ([f"- {item}" for item in items] or ["- none"])
    if surface_results:
        lines += ["", "## Surface garden commands", ""]
        for identifier, command, status, output in surface_results:
            lines.append(f"- `{identifier}`: `{command}` → {status}")
            lines += [f"    {line}" for line in output]
    lines += ["", "Fix with the doc-gardener role (docs) or an implementer (code); one root cause per change."]
    return "\n".join(lines) + "\n", 1 if hard or failures else 0
