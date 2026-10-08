"""Project initialization: identity, README, vision reset, template-only pruning."""

from __future__ import annotations

import re
from pathlib import Path

from . import derive
from .core import (
    KEBAB,
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
from .kitlock import localize_text, write_lock
from .names import STACK_DECISION, VISION


def update_readme_identity(root: Path, name: str, kind: str, old_name: str) -> None:
    readme = ensure_inside_root(root, root / "README.md", "project README")
    try:
        content = readme.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    heading = rf"^\s*# (?:Agent Template|{re.escape(old_name)})\s*$"
    content = re.sub(heading, lambda _: f"# {name}", content, count=1, flags=re.MULTILINE)
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
            r"\1# This project is initialized. Complete the intake and replace the template-bootstrap surface "
            r"before treating checks as product evidence.\nmake inventory\nmake check\2",
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
        "This project is initialized. Complete `VISION.md`, `docs/STACK-DECISION.md`, the accountable owner, "
        "and the first real surface in `project.toml`; rerun `make doctor` when those gates are resolved.",
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


VISION_SKELETON = """# Project vision

<!-- index: operate | Accepted product direction, constraints, and success evidence | Starting a project or making a high-impact scope decision. -->

Status: pending
Project: {name}
Owner: project-owner
Date: [YYYY-MM-DD]

The `product-kickoff` skill fills this in with the owner. Replace every bracketed
REQUIRED line, then set `Status: accepted` with the owner and today's date, and
`[vision].status = "accepted"` in `project.toml`. Checks refuse an accepted
record that still has a placeholder.

## Outcome

[REQUIRED: who it is for, the problem it solves, and what success looks like (one metric)]

## Users and context

[REQUIRED: the people who use it, where, and what they use today]

## Platforms and constraints

[REQUIRED: platforms, offline needs, budget, deadline, data and privacy limits]

## Non-goals

[REQUIRED: what this version deliberately does not do]

## Success evidence

[REQUIRED: how we will know it works: tests, observed real artifacts, the metric]
"""

STACK_SKELETON = """# Stack decision record

<!-- index: operate | Framework/toolchain decision and rationale | Choosing a project stack or replacing an assumed tool. -->

Status: pending
Project: {name}
Owner: project-owner
Date: [YYYY-MM-DD]

Record the stack after the vision is accepted (`product-kickoff`, then
`stack-foundation`). Confirm current versions from primary sources before
accepting.

## Decision

[REQUIRED: language, framework, data store, hosting, with pinned versions]

## Why this, and what else was considered

[REQUIRED: the alternatives and why they lost for this product]

## Verification and rollback

[REQUIRED: the commands that prove it works, and how to back out]
"""


def _template_record(path: Path, template_name: str) -> bool:
    """True for a missing record or the template's own one; a project's own record is never replaced."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return True
    return bool(re.search(rf"(?m)^Project:\s*({re.escape(template_name)}|REPLACE_WITH_PROJECT_NAME)\s*$", text))


def reset_vision_for_project(root: Path, manifest: str, project_name: str, template_name: str) -> str:
    """Pending intake records for the new project, never the template's own vision and stack text."""
    manifest = re.sub(
        r'(?ms)(\[vision\]\s*\n\s*status\s*=\s*)"[^"]+"',
        r'\1"pending"',
        manifest,
        count=1,
    )
    for relative, skeleton in ((VISION, VISION_SKELETON), (STACK_DECISION, STACK_SKELETON)):
        path = ensure_inside_root(root, root / relative, "intake record")
        if _template_record(path, template_name):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(skeleton.format(name=project_name), encoding="utf-8")
    return manifest


def prune_template_material(root: Path, project: dict[str, object]) -> list[str]:
    """Remove [template].prune files; localize every remaining Markdown file (links, bindings)."""
    template = project.get("template", {})
    if not isinstance(template, dict):
        return []
    patterns = list(template.get("prune", []))
    source = str(template.get("source", "")).rstrip("/")
    files = repository_files(root)
    removed = [path for path in files if any(path_matches(path, pattern) for pattern in patterns)]
    removed_set = set(removed)
    for relative in files:
        if not relative.endswith(".md") or relative in removed_set:
            continue
        text = read_text_file(root, relative)
        if text is None:
            continue
        updated = localize_text(relative, text, removed_set, patterns, source)
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


PACKS_TABLE = re.compile(r"(?ms)^\[packs\]\n.*?(?=^\[)")


def reset_packs(manifest: str) -> str:
    """A new project starts with each pack's default; the template's own overrides (measure) stay behind."""
    return PACKS_TABLE.sub(
        "[packs]\n# Capability packs (.agents/packs/, make capabilities): omitted packs keep their default.\n"
        "# Example: switch off the product pack for a repository that is not a product.\n# product = false\n\n",
        manifest, count=1)


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
    if not KEBAB.fullmatch(kind):
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
    template_name = current_name.group(1)
    current = load_project(root)
    if template_name != "REPLACE_WITH_PROJECT_NAME" and current.get("kind") != "template":
        raise RepoctlError("project is already initialized; edit project.toml deliberately")
    old_owners = [str(o) for o in current.get("owners", []) if isinstance(o, str)]

    manifest = replace_manifest_field(manifest, "name", name)
    manifest = replace_manifest_field(manifest, "kind", kind)
    manifest = replace_manifest_field(manifest, "phase", "development")
    manifest = re.sub(r'(?m)^github\s*=\s*"[^"]*"$', 'github = ""', manifest, count=1)
    manifest = re.sub(r'(?m)^owners\s*=\s*\[[^\]]*\]', 'owners = ["project-owner"]', manifest, count=1)
    for old_owner in old_owners:
        manifest = manifest.replace(f'owner = "{old_owner}"', 'owner = "project-owner"')
    manifest = reset_template_surface(manifest)
    manifest = reset_vision_for_project(root, manifest, name, template_name)
    removed = prune_template_material(root, load_project(root))
    manifest = reset_repository_metadata(manifest)
    manifest = reset_packs(manifest)
    if owner:
        # Name the accountable owner once here instead of failing later checks on a placeholder.
        manifest = manifest.replace('"project-owner"', f'"{owner}"')
        for record in (VISION, STACK_DECISION):
            path = root / record
            if path.is_file():
                path.write_text(path.read_text(encoding="utf-8").replace("Owner: project-owner", f"Owner: {owner}"), encoding="utf-8")
    manifest_path.write_text(manifest, encoding="utf-8")
    update_readme_identity(root, name, kind, template_name)
    derive.sync(root)
    write_lock(root, root)  # what this project got from the kit, so make kit-update can tell your edits apart
    if removed:
        print(f"Removed {len(removed)} template-only file(s); links now point to the template source.")
    print(f"Initialized {name} ({kind}). Declare real surfaces before implementation.")
    if not owner:
        print('Owner is the placeholder "project-owner": set owners = ["<handle>"] in project.toml (or init with OWNER=<handle>).')
