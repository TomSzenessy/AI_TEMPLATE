"""Project initialization: identity, README, vision reset, template-only pruning."""

from __future__ import annotations

import re
from pathlib import Path

from . import derive
from .core import (
    KEBAB,
    PROJECT_NAME_PATTERN,
    RepoctlError,
    declared_surfaces,
    ensure_inside_root,
    is_placeholder,
    load_project,
    read_text_file,
    replace_manifest_field,
    repository_files,
)
from .gitinfo import path_matches
from .kitlock import localize_text, read_lock, write_lock
from .names import STACK_DECISION, VISION


TEMPLATE_ONLY = re.compile(r"(?ms)^<!-- repoctl:template-only -->\n.*?^<!-- /repoctl:template-only -->\n?")
PROJECT_ABOUT = """
## About

FILL-IN: what this project does, for whom, how its success is judged, and how to run it.

## Working on this repository

People and agents start with [`AGENTS.md`](./AGENTS.md): `make start`, `make next`, `make done`; the documents
are indexed in [`docs/README.md`](./docs/README.md). The tooling comes from the kit at {source};
`make kit-update` brings its fixes.
"""


def project_readme_body(content: str, source: str, removed: list[str] | None = None) -> str:
    """The template's own prose leaves with `make init` (#75): marked sections go, an About section to fill in arrives.
    `removed` collects the sections taken out, so the caller can keep them."""
    if "<!-- repoctl:template-only -->" not in content:
        return content
    if removed is not None:
        removed.extend(match.group(0) for match in TEMPLATE_ONLY.finditer(content))
    content = TEMPLATE_ONLY.sub("", content)
    content = re.sub(r"(?m)^## Start a project\s*$", "## Quick start", content, count=1)
    end = "<!-- /repoctl:project-readme -->"
    if "\n## About\n" not in content and end in content:
        content = content.replace(end, end + "\n" + PROJECT_ABOUT.format(source=source or "the template source"), 1)
    return re.sub(r"\n{3,}", "\n\n", content)


def update_readme_identity(root: Path, name: str, kind: str, old_name: str) -> None:
    readme = ensure_inside_root(root, root / "README.md", "project README")
    try:
        content = readme.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    template = load_project(root).get("template", {})
    taken: list[str] = []
    content = project_readme_body(content, str(template.get("source", "")) if isinstance(template, dict) else "", taken)
    if taken:
        print(f"Removed {len(taken)} template-only README section(s); kept in {back_up(root, 'README.md', ''.join(taken))}.")
    from .structure import TEMPLATE_README_HEADINGS
    left = [h for h in TEMPLATE_README_HEADINGS if h in {line.strip() for line in content.splitlines()}]
    if left:  # a README older than the template-only markers: name what to replace (make garden keeps listing it)
        print(f"README.md still has the template's own section(s) {', '.join(left)}: replace them with the project's.")
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


BACKUP = ".agent/init-backup"  # ignored: what init replaced or removed, so following its advice loses nothing


def back_up(root: Path, relative: str, text: str) -> str:
    target = ensure_inside_root(root, root / BACKUP / relative, "init backup")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return f"{BACKUP}/{relative}"


def shipped(root: Path, project: dict[str, object], relative: str) -> bool:
    """Is this record still the template's own text, by the digest `[template].records` ships? (#75)"""
    import hashlib
    template = project.get("template", {})
    records = template.get("records", {}) if isinstance(template, dict) else {}
    expected = records.get(relative) if isinstance(records, dict) else None
    path = root / relative
    if not expected or not path.is_file():
        return True  # no digest to compare with: treat it as the template's, back it up, and reset it
    text = path.read_bytes().replace(b"\r\n", b"\n")  # a CRLF checkout (core.autocrlf) is still the shipped text
    return f"sha256:{hashlib.sha256(text).hexdigest()}" == expected


def reset_vision_for_project(root: Path, manifest: str, project_name: str, template_name: str,
                             keep: frozenset[str] = frozenset()) -> str:
    """Pending intake records for the new project, never the template's own vision and stack text.

    `keep`: records a template clone already used as a project wrote itself (#75); they stay, renamed.
    """
    for relative in sorted(keep):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        path.write_text(re.sub(rf"(?m)^Project:\s*{re.escape(template_name)}\s*$", f"Project: {project_name}", text),
                        encoding="utf-8")
        print(f"Kept {relative}: this checkout wrote it as a project. REVIEW that it describes the project.")
    if keep >= {VISION}:
        return manifest  # its own vision keeps its own status
    manifest = re.sub(
        r'(?ms)(\[vision\]\s*\n\s*status\s*=\s*)"[^"]+"',
        r'\1"pending"',
        manifest,
        count=1,
    )
    for relative, skeleton in ((VISION, VISION_SKELETON), (STACK_DECISION, STACK_SKELETON)):
        if relative in keep:
            continue
        path = ensure_inside_root(root, root / relative, "intake record")
        if _template_record(path, template_name):
            if path.is_file():
                back_up(root, relative, path.read_text(encoding="utf-8"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(skeleton.format(name=project_name), encoding="utf-8")
    return manifest


def _surface_owned(project: dict[str, object]) -> list[str]:
    """Every path a project surface owns: its `path` and its `extra_paths` (a root `index.html`, #57)."""
    from .core import surface_owned_paths
    return [str(path).strip("/") for label, paths in surface_owned_paths(project).items()
            if label not in {"template", "template-bootstrap"} for path in paths
            if str(path).strip("/") not in {"", "."}]


def guard_prune(project: dict[str, object], removed: list[str]) -> None:
    """#75: a project's own folders were once added to the template's prune list; never delete a surface's files."""
    owned = _surface_owned(project)
    guarded = sorted({p for p in removed for o in owned if p == o or p.startswith(o + "/")})
    if guarded:
        raise RepoctlError(f"[template].prune would delete {len(guarded)} file(s) of declared surfaces "
                           f"({', '.join(guarded[:5])}{' ...' if len(guarded) > 5 else ''}): remove those patterns from "
                           "[template].prune first; prune is for template-only material")


def listed_kit_files(root: Path) -> list[str]:
    """The template's own list of kit files (tools/kit-files.json); a clone older than the list gets it from kit-update."""
    import json

    from .kitlock import KIT_FILES
    try:
        listed = json.loads((root / KIT_FILES).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RepoctlError(f"{KIT_FILES} is missing: this clone predates it. Run `make kit-update` first (it adds the "
                           "list and updates the kit), commit, then `make init`, so init can tell the kit's files from "
                           "the project's") from error
    if not isinstance(listed, list) or not all(isinstance(p, str) for p in listed):
        raise RepoctlError(f"{KIT_FILES} must be a JSON list of paths")
    return [p for p in listed if (root / p).is_file()]


def drop_surface_prune(root: Path, project: dict[str, object]) -> dict[str, object]:
    """The project with every prune pattern that matches a file of one of its declared surfaces removed (#75)."""
    template = project.get("template", {})
    if not isinstance(template, dict):
        return project
    owned = _surface_owned(project)
    files = repository_files(root)
    keep, dropped = [], []
    for pattern in template.get("prune", []):
        hits = [p for p in files if path_matches(p, pattern)]
        (dropped if any(p == o or p.startswith(o + "/") for p in hits for o in owned) else keep).append(pattern)
    if dropped:
        print(f"Kept {', '.join(dropped)} out of the prune: they cover this project's own surfaces.")
    return {**project, "template": {**template, "prune": keep}}


def prune_matches(root: Path, project: dict[str, object]) -> list[str]:
    template = project.get("template", {})
    patterns = list(template.get("prune", [])) if isinstance(template, dict) else []
    return [path for path in repository_files(root) if any(path_matches(path, pattern) for pattern in patterns)]


def prune_template_material(root: Path, project: dict[str, object]) -> list[str]:
    """Remove [template].prune files; localize every remaining Markdown file (links, bindings)."""
    template = project.get("template", {})
    if not isinstance(template, dict):
        return []
    patterns = list(template.get("prune", []))
    source = str(template.get("source", "")).rstrip("/")
    files = repository_files(root)
    removed = [path for path in files if any(path_matches(path, pattern) for pattern in patterns)]
    guard_prune(project, removed)
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
    for relative in removed:  # #82: a project folder listed in prune by mistake is kept, not lost
        target = ensure_inside_root(root, root / BACKUP / relative, "init backup")
        target.parent.mkdir(parents=True, exist_ok=True)
        (root / relative).replace(target)  # moved, byte for byte, into the ignored backup
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


def initialize_project(root: Path, name: str, kind: str, owner: str | None = None,
                       mode: str = "new") -> None:
    if not PROJECT_NAME_PATTERN.fullmatch(name):
        raise RepoctlError(
            "project name must be 1-64 characters using letters, digits, '.', '_' or '-'"
        )
    if not KEBAB.fullmatch(kind):
        raise RepoctlError("project kind must be lowercase kebab-case")
    if mode not in {"new", "adopt"}:
        raise RepoctlError("project mode must be new or adopt")
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
    from .structure import template_in_use
    in_use = template_in_use(root, current) is not None
    if in_use:  # a clone already used as a project: patterns over its own surfaces were never template material
        current = drop_surface_prune(root, current)
        listed_kit_files(root)  # a clone older than the list is sent to kit-update first
        read_lock(root)  # a damaged lock is refused before init writes anything
    guard_prune(current, prune_matches(root, current))  # before any write: a refused init changes nothing
    keep = frozenset(r for r in (VISION, STACK_DECISION) if in_use and not shipped(root, current, r))
    old_owners = [str(o) for o in current.get("owners", []) if isinstance(o, str)]

    manifest = replace_manifest_field(manifest, "name", name)
    manifest = replace_manifest_field(manifest, "kind", kind)
    manifest = replace_manifest_field(manifest, "phase", "development")
    # Whether this repository already had a product when the kit arrived (#58).
    manifest = re.sub(r'(?m)^(# preview_kinds = .*\n)', rf'\1project_mode = "{mode}"\n', manifest, count=1)
    if f'project_mode = "{mode}"' not in manifest:
        manifest = re.sub(r"(?m)^\[kit\]\s*$", f'[kit]\nproject_mode = "{mode}"', manifest, count=1)
    manifest = re.sub(r'(?m)^github\s*=\s*"[^"]*"$', 'github = ""', manifest, count=1)
    manifest = re.sub(r'(?m)^owners\s*=\s*\[[^\]]*\]', 'owners = ["project-owner"]', manifest, count=1)
    for old_owner in old_owners:
        manifest = manifest.replace(f'owner = "{old_owner}"', 'owner = "project-owner"')
    manifest = reset_template_surface(manifest)
    manifest = reset_vision_for_project(root, manifest, name, template_name, keep=keep)
    removed = prune_template_material(root, current)  # with the prune list this init decided on
    manifest = reset_repository_metadata(manifest)
    manifest = reset_packs(manifest)
    if owner:
        # Name the accountable owner once here instead of failing later checks on a placeholder.
        manifest = manifest.replace('"project-owner"', f'"{owner}"')
        for record in (VISION, STACK_DECISION):
            path = root / record
            if path.is_file():
                text = path.read_text(encoding="utf-8").replace("Owner: project-owner", f"Owner: {owner}")
                for old_owner in old_owners if record in keep else ():  # a kept record still names the template's
                    text = re.sub(rf"(?m)^Owner:\s*{re.escape(old_owner)}\s*$", f"Owner: {owner}", text)
                path.write_text(text, encoding="utf-8")
    manifest_path.write_text(manifest, encoding="utf-8")
    update_readme_identity(root, name, kind, template_name)
    derive.sync(root)
    # What this project got from the kit, so make kit-update can tell your edits apart. A clone already used as a
    # project may have edited kit files, so its current content is not what the kit shipped: it keeps the lock an
    # earlier kit-update wrote, else gets an empty one, and its first kit-update compares each kit file with the
    # template's history instead (#89). Never its own files: a later kit-update would delete them.
    if not in_use:
        write_lock(root, root)
    elif not read_lock(root).get("files"):
        write_lock(root, root, paths=[], version="unknown")
    if removed:
        print(f"Moved {len(removed)} template-only file(s) to .agent/init-backup/; links now point to the template source.")
    print(f"Initialized {name} ({kind}). Declare real surfaces before implementation.")
    if not owner:
        print('Owner is the placeholder "project-owner": set owners = ["<handle>"] in project.toml (or init with OWNER=<handle>).')
