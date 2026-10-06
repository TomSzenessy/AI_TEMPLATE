"""The gardener: one aggregate of every rot detector, shared by check, finish, and CI.

`self_heal_errors` is the hard gate used by `make check`. `garden_report`
adds advisory findings (upcoming deprecations, unbound docs, skill review age)
and each surface's own `garden` commands (for example a dead-code finder), and
renders Markdown suitable for a CI job summary or a gardener agent's brief.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

from . import adapters, docsync, hygiene
from .core import declared_surfaces, ensure_inside_root, load_project, repository_files
from .gitinfo import changed_paths, has_history

SKILL_REVIEW_DAYS = 365


def self_heal_errors(root: Path, project: dict[str, object] | None = None) -> list[str]:
    project = project or load_project(root)
    files = repository_files(root)
    doc_bindings = docsync.bindings(root, files)
    errors = adapters.drift(root)
    errors += docsync.dead_bindings(doc_bindings, files)
    errors += docsync.stale_documents(root, doc_bindings, changed_paths(root))
    errors += docsync.command_reference_errors(root, files)
    errors += hygiene.scan_markers(root, files).errors
    errors += hygiene.budget_errors(root, project, files)
    return errors


def surface_garden_commands(project: dict[str, object]) -> list[tuple[str, list[str], str]]:
    commands = []
    for surface in declared_surfaces(project):
        if surface.get("status", "active") != "active":
            continue
        for command in surface.get("garden", []):
            if isinstance(command, list) and command and all(isinstance(part, str) for part in command):
                commands.append((str(surface.get("id")), command, str(surface.get("path", "."))))
    return commands


def garden_report(root: Path) -> tuple[str, int]:
    project = load_project(root)
    files = repository_files(root)
    doc_bindings = docsync.bindings(root, files)
    hard = self_heal_errors(root, project)
    markers = hygiene.scan_markers(root, files)
    advisory = [f"deprecation due soon: {item}" for item in markers.upcoming]
    unbound = sorted(
        path
        for path in files
        if path.startswith("docs/") and path.endswith(".md") and path not in doc_bindings
        and not path.startswith(("docs/legal/", "docs/research/", "docs/incidents/", "docs/handoffs/", "docs/adr/"))
    )
    if unbound:
        advisory.append("documents without a covers binding (fine for pure policy docs): " + ", ".join(unbound))
    for entry in project.get("skills", []):
        reviewed = str(entry.get("reviewed_on", ""))
        try:
            age = (date.today() - date.fromisoformat(reviewed)).days
        except ValueError:
            continue
        if age > SKILL_REVIEW_DAYS:
            advisory.append(f"skill review older than a year: {entry.get('package')} (reviewed {reviewed})")
    if not has_history(root):
        advisory.append("git history unavailable or shallow: stale-document detection skipped (use fetch-depth: 0 in CI)")

    surface_results = []
    failures = 0
    for identifier, command, path in surface_garden_commands(project):
        cwd = ensure_inside_root(root, root / path, f"surface {identifier} path")
        try:
            result = subprocess.run(command, cwd=cwd if cwd.is_dir() else cwd.parent, capture_output=True, text=True, timeout=900, check=False)
            output = (result.stdout + result.stderr).strip().splitlines()[-15:]
            status = "ok" if result.returncode == 0 else f"exit {result.returncode}"
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            output, status = [str(error)], "did not run"
        failures += status != "ok"
        surface_results.append((identifier, " ".join(command), status, output))

    lines = ["# Garden report", ""]
    lines.append(f"Hard findings (fail `make check`): {len(hard)} · advisory: {len(advisory)} · surface garden commands: {len(surface_results)}")
    for title, items in (("Hard findings", hard), ("Advisory", advisory)):
        lines += ["", f"## {title}", ""] + ([f"- {item}" for item in items] or ["- none"])
    if surface_results:
        lines += ["", "## Surface garden commands", ""]
        for identifier, command, status, output in surface_results:
            lines.append(f"- `{identifier}`: `{command}` → {status}")
            lines += [f"    {line}" for line in output]
    lines += ["", "Fix with the doc-gardener role (docs) or an implementer (code); one root cause per change."]
    return "\n".join(lines) + "\n", 1 if hard or failures else 0
