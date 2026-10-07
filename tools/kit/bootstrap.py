"""Project initialization: identity, README, vision reset, template-only pruning."""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import derive
from .core import (
    PROJECT_KIND_PATTERN,
    PROJECT_NAME_PATTERN,
    RepoctlError,
    ensure_inside_root,
    is_placeholder,
    load_project,
    read_text_file,
    replace_manifest_field,
    repository_files,
)
from .gitinfo import path_matches


def update_readme_identity(root: Path, name: str, kind: str) -> None:
    readme = ensure_inside_root(root, root / "README.md", "project README")
    try:
        content = readme.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    content = re.sub(r"^\s*# (?:Agent Template|AI_TEMPLATE)\s*$", f"# {name}", content, count=1, flags=re.MULTILINE)
    marker = "<!-- repoctl:project-readme -->"
    replacement = (
        f"{marker}\n> Project initialized: **{name}** (`{kind}`). Keep this identity,\n"
        "> launch state, and project-specific quick start current."
    )
    content = re.sub(
        rf"(?ms)^\s*{re.escape(marker)}\s*\n\s*> \*\*Template mode:\*\*.*?(?=\n\s*\n)",
        replacement,
        content,
        count=1,
        flags=re.DOTALL,
    )
    content = re.sub(
        r"(?m)^> Project initialized: \*\*[^*]+\*\* \(`[^`]+`\)\.",
        f"> Project initialized: **{name}** (`{kind}`).",
        content,
    )
    initialized_quickstart = '''<!-- repoctl:quickstart -->
```bash
# This project is initialized. Complete the intake and replace the
# template-bootstrap surface before treating checks as product evidence.
make inventory
make check
```
<!-- /repoctl:quickstart -->'''
    content = re.sub(
        r"(?ms)^<!-- repoctl:quickstart -->\s*.*?^<!-- /repoctl:quickstart -->$",
        initialized_quickstart,
        content,
        count=1,
    )
    if "<!-- repoctl:quickstart -->" not in content:
        content = re.sub(
            r"(?ms)(^## Start in five minutes\s*\n\s*```bash\s*\n).*?(\n\s*```)",
            r"\1# This project is initialized. Complete the intake and replace the template-bootstrap surface before treating checks as product evidence.\nmake inventory\nmake check\2",
            content,
            count=1,
        )
    content = re.sub(
        r"```bash\s*\n\s*cp -R AGENT_TEMPLATE my-project\s*\n.*?```",
        "```bash\nmake inventory\nmake check\n```",
        content,
        count=1,
        flags=re.DOTALL,
    )
    content = re.sub(
        r"(?ms)^`make init` sets identity and phase only;.*?then rerun the doctor\.",
        "This project is initialized. Complete `VISION.md`, `docs/STACK-DECISION.md`, the accountable owner, and the first real surface in `project.toml`; rerun `make doctor` when those gates are resolved.",
        content,
        count=1,
    )
    readme.write_text(content, encoding="utf-8")


def reset_template_surface(manifest: str) -> str:
    pattern = re.compile(
        r'(?ms)^\[\[surfaces\]\]\s*\nid = "template"\s*\npath = "\.".*?(?=^\[\[?[^\]]+\]\]?\s*$|^\Z)'
    )
    replacement = '''[[surfaces]]
id = "template-bootstrap"
path = "."
kind = "template"
status = "planned"
# Replace this bootstrap declaration with the first real product surface.
verification = []
'''
    updated, count = pattern.subn(replacement, manifest, count=1)
    if count == 0:
        return manifest
    return updated


def reset_vision_for_project(root: Path, manifest: str, project_name: str) -> str:
    manifest = re.sub(
        r'(?ms)(\[vision\]\s*\n\s*status\s*=\s*)"[^"]+"',
        r'\1"pending"',
        manifest,
        count=1,
    )
    vision_path = ensure_inside_root(root, root / "VISION.md", "vision record")
    try:
        content = vision_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = "# Project vision\n\nStatus: pending\n"
    content = re.sub(r"(?m)^Status:\s*.*$", "Status: pending", content, count=1)
    content = re.sub(r"(?m)^Project:\s*.*$", f"Project: {project_name}", content, count=1)
    content = re.sub(r"(?m)^Owner:\s*.*$", "Owner: project-owner", content, count=1)
    content = re.sub(r"(?m)^Date:\s*.*$", "Date: [YYYY-MM-DD]", content, count=1)
    vision_path.write_text(content, encoding="utf-8")
    stack_path = ensure_inside_root(root, root / "docs" / "STACK-DECISION.md", "stack decision record")
    try:
        stack_content = stack_path.read_text(encoding="utf-8")
        stack_content = re.sub(r"(?m)^Status:\s*.*$", "Status: pending", stack_content, count=1)
        stack_content = re.sub(r"(?m)^Project:\s*.*$", f"Project: {project_name}", stack_content, count=1)
        stack_content = re.sub(r"(?m)^Owner:\s*.*$", "Owner: project-owner", stack_content, count=1)
        stack_content = re.sub(r"(?m)^Date:\s*.*$", "Date: [YYYY-MM-DD]", stack_content, count=1)
        stack_path.write_text(stack_content, encoding="utf-8")
    except FileNotFoundError:
        pass
    return manifest


def prune_template_material(root: Path, project: dict[str, object]) -> list[str]:
    """Remove [template].prune files and point links to them at the template source."""
    template = project.get("template", {})
    if not isinstance(template, dict):
        return []
    patterns = template.get("prune", [])
    source = str(template.get("source", "")).rstrip("/")
    files = repository_files(root)
    removed = [path for path in files if any(path_matches(path, pattern) for pattern in patterns)]
    if not removed:
        return []
    removed_set = set(removed)
    link = re.compile(r"(\]\()([^)\s]+)(\))")
    for relative in files:
        if not relative.endswith(".md") or relative in removed_set:
            continue
        text = read_text_file(root, relative)
        if text is None:
            continue

        def absolute(match: re.Match[str]) -> str:
            target = match.group(2)
            if "://" in target or target.startswith("#"):
                return match.group(0)
            path, _, anchor = target.partition("#")
            resolved = os.path.normpath(os.path.join(os.path.dirname(relative), path)).replace(os.sep, "/")
            if resolved not in removed_set or not source:
                return match.group(0)
            return f"{match.group(1)}{source}/blob/main/{resolved}{'#' + anchor if anchor else ''}{match.group(3)}"

        updated = link.sub(absolute, text)
        if updated != text:
            (root / relative).write_text(updated, encoding="utf-8")
    for relative in removed:
        (root / relative).unlink()
    for directory in sorted({str(Path(path).parent) for path in removed}, key=len, reverse=True):
        candidate = root / directory
        while candidate != root and candidate.is_dir() and not any(candidate.iterdir()):
            candidate.rmdir()
            candidate = candidate.parent
    return removed


def reset_repository_metadata(manifest: str) -> str:
    manifest = re.sub(r'(?m)^description\s*=\s*".*"$', 'description = ""', manifest, count=1)
    manifest = re.sub(r"(?m)^topics\s*=\s*\[[^\]]*\]", "topics = []", manifest, count=1)
    manifest = re.sub(r"(?m)^is_template\s*=\s*true$", "is_template = false", manifest, count=1)
    return re.sub(r"(?m)^prune\s*=\s*\[[^\]]*\]", "prune = []", manifest, count=1)


OWNER_HANDLE = re.compile(r"@?[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.-]+)?")


def initialize_project(root: Path, name: str, kind: str, owner: str | None = None) -> None:
    if not PROJECT_NAME_PATTERN.fullmatch(name):
        raise RepoctlError(
            "project name must be 1-64 characters using letters, digits, '.', '_' or '-'"
        )
    if not PROJECT_KIND_PATTERN.fullmatch(kind):
        raise RepoctlError("project kind must be lowercase kebab-case")
    if owner is not None and (not OWNER_HANDLE.fullmatch(owner) or is_placeholder(owner)):
        raise RepoctlError("owner must be a handle or team name such as octocat or acme/web-team, not an email")

    manifest_path = ensure_inside_root(root, root / "project.toml", "project manifest")
    try:
        manifest = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise RepoctlError("project.toml is missing") from error

    current_name = re.search(r'^name = "([^"]*)"$', manifest, re.MULTILINE)
    if not current_name:
        raise RepoctlError("project.toml must contain a name field")
    if current_name.group(1) not in {"REPLACE_WITH_PROJECT_NAME", "AI_TEMPLATE"}:
        raise RepoctlError("project is already initialized; edit project.toml deliberately")

    manifest = replace_manifest_field(manifest, "name", name)
    manifest = replace_manifest_field(manifest, "kind", kind)
    manifest = replace_manifest_field(manifest, "phase", "development")
    manifest = re.sub(r'(?m)^github\s*=\s*"[^"]*"$', 'github = ""', manifest, count=1)
    manifest = re.sub(r'(?m)^owners\s*=\s*\[[^\]]*\]', 'owners = ["project-owner"]', manifest, count=1)
    manifest = manifest.replace('owner = "TomSzenessy"', 'owner = "project-owner"')
    manifest = reset_template_surface(manifest)
    manifest = reset_vision_for_project(root, manifest, name)
    removed = prune_template_material(root, load_project(root))
    manifest = reset_repository_metadata(manifest)
    if owner:
        # Name the accountable owner once here instead of failing later checks on a placeholder.
        manifest = manifest.replace('"project-owner"', f'"{owner}"')
        for record in ("VISION.md", "docs/STACK-DECISION.md"):
            path = root / record
            if path.is_file():
                path.write_text(path.read_text(encoding="utf-8").replace("Owner: project-owner", f"Owner: {owner}"), encoding="utf-8")
    manifest_path.write_text(manifest, encoding="utf-8")
    update_readme_identity(root, name, kind)
    derive.sync(root)
    if removed:
        print(f"Removed {len(removed)} template-only file(s); links now point to the template source.")
    print(f"Initialized {name} ({kind}). Declare real surfaces before implementation.")
    if not owner:
        print('Owner is the placeholder "project-owner": set owners = ["<handle>"] in project.toml (or init with OWNER=<handle>).')
