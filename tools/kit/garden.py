"""The gardener: one aggregate of every rot detector, shared by check, finish, and CI.

`self_heal_errors` is the hard gate used by `make check`. `garden_report`
adds advisory findings (upcoming deprecations, unbound docs, skill review age)
and each surface's own `garden` commands (for example a dead-code finder), and
renders Markdown suitable for a CI job summary or a gardener agent's brief.
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

from . import derive, docsync, github, hygiene, product
from .core import FILE_SURFACE_KINDS, declared_surfaces, ensure_inside_root, load_project, repository_files
from .config import setting
from .gitinfo import changed_paths, has_history, path_matches



def self_heal_errors(root: Path, project: dict[str, object] | None = None) -> list[str]:
    project = project or load_project(root)
    files = repository_files(root)
    doc_bindings = docsync.bindings(root, files)
    errors = derive.drift(root)
    errors += docsync.index_errors(root, files)
    errors += docsync.dead_bindings(doc_bindings, files)
    errors += docsync.stale_documents(root, doc_bindings, changed_paths(root))
    errors += docsync.command_reference_errors(root, files)
    errors += hygiene.scan_markers(root, files).errors
    errors += hygiene.budget_errors(root, project, files)
    errors += hygiene.workflow_errors(root, files)
    errors += project_errors(root, project, files, doc_bindings)
    errors += product.feature_errors(root) + product.research_errors(root, project)
    return errors


BACKLOG_NAMES = re.compile(r"(?i)(?:^|/)(?:backlog|todo|tasks|roadmap)\.md$|(?:^|/)docs/[^/]*wal[^/]*\.md$")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def project_errors(root: Path, project: dict[str, object], files: list[str], doc_bindings: dict[str, list[str]]) -> list[str]:
    """Guardrails a fresh agent skipped in the build trial; each names its fix."""
    errors = [
        f"{path}: live work belongs in issues (or ignored .agent/wal/ via `make issue` without a remote), not a tracked backlog"
        for path in files
        if BACKLOG_NAMES.search(path) and not path.startswith((".agents/", ".claude/"))
    ]
    for surface in declared_surfaces(project):
        path = str(surface.get("path", "."))
        # Directory surfaces only: a single file or document surface is its own owner.
        if (surface.get("status", "active") != "active" or surface.get("kind") == "template"
                or surface.get("kind") in FILE_SURFACE_KINDS or path in {".", ""}):
            continue
        inside = [file for file in files if file == path or file.startswith(path.rstrip("/") + "/")]
        if inside and not any(path_matches(file, pattern) for file in inside for patterns in doc_bindings.values() for pattern in patterns):
            errors.append(
                f"surface {surface.get('id')} ({path}) has no owning doc: add `<!-- covers: {path}/** -->` to the doc that "
                f'explains it, or `make new KIND=doc NAME={surface.get("id")} GROUP=design COVERS="{path}/**" DESC="...; ..."`'
            )
    vision = project.get("vision", {})
    accepted = isinstance(vision, dict) and vision.get("status") == "accepted"
    ui_project = project.get("kind") in setting(root, "ui_kinds")
    building = any(
        surface.get("status", "active") == "active" and surface.get("kind") != "template"
        for surface in declared_surfaces(project)
    )
    if accepted and ui_project and building and "docs/design.md" not in files:
        errors.append(
            'UI project without docs/design.md: record the chosen direction (product-kickoff step 5): '
            'make new KIND=doc NAME=design GROUP=design DESC="Visual direction, tokens, and UX principles; before any UI work"'
        )
    owners = [*project.get("owners", []), *(surface.get("owner", "") for surface in declared_surfaces(project))]
    errors += [
        f"project.toml owner {owner!r} looks like an email; manifests are public, use a handle or team name"
        for owner in sorted(set(owners))
        if isinstance(owner, str) and EMAIL.fullmatch(owner.strip())
    ]
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
    markers = hygiene.scan_markers(root, files, warning_days=int(setting(root, "deprecation_warning_days")))
    advisory = [f"deprecation due soon: {item}" for item in markers.upcoming]
    advisory += hygiene.duplicate_paragraphs(root, files)
    unbound = sorted(
        path
        for path in files
        if path.startswith("docs/") and path.endswith(".md") and path not in doc_bindings
        and not any(path_matches(path, pattern) for pattern in setting(root, "unbound_docs_ok"))
    )
    if unbound:
        advisory.append("documents without a covers binding (fine for pure policy docs): " + ", ".join(unbound))
    for entry in project.get("skills", []):
        reviewed = str(entry.get("reviewed_on", ""))
        try:
            age = (date.today() - date.fromisoformat(reviewed)).days
        except ValueError:
            continue
        if age > int(setting(root, "skill_review_days")):
            advisory.append(f"skill review older than a year: {entry.get('package')} (reviewed {reviewed})")
    try:
        advisory += github.metadata_drift(root)
    except Exception as error:  # noqa: BLE001 - metadata drift is advisory only
        advisory.append(f"GitHub metadata check skipped: {error}")
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
