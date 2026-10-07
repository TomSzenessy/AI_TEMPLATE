"""`make kit-update`: deliver template fixes to projects already made from it.

A bug in the template is copied into every project, so fixes must flow the
other way too. `make init` and `make adopt` record `tools/kit-lock.json`: the
SHA-256 of every kit file as shipped. `make kit-update KIT=<template checkout>`
then compares three states per file, without needing shared git history (a
GitHub "Use this template" repository has none):

- unchanged since shipped (hash matches the lock): replaced by the new version;
- changed by the project: left alone; the new version is saved under
  `.agent/kit-update/` and reported for a merge;
- new in the kit: added (unless the project already has its own file there);
- removed from the kit: deleted when unchanged, reported otherwise.

Project-owned files (identity, intake records, product docs, generated host
files) are never kit files. Project make targets belong in `project.mk`, which
the kit Makefile includes, so the Makefile itself stays kit-owned.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import derive
from .core import RepoctlError, load_project, repository_files
from .gitinfo import git, path_matches

LOCK = "tools/kit-lock.json"
STAGING = ".agent/kit-update"
# Never kit files: the project's identity, decisions, product docs, and generated output.
PROJECT_OWNED = (
    LOCK, "project.toml", "VISION.md", "README.md", "LICENSE", "CONTEXT.md", ".gitignore", "project.mk",
    "docs/STACK-DECISION.md", "docs/README.md", "docs/design.md", "docs/ERROR_LOG.md",
    "docs/architecture/**", "docs/product/**", "docs/adr/**", "docs/incidents/**", ".security/**",
    ".claude/**", ".mcp.json", "HANDOVER.md",
)


DERIVED_BLOCK = re.compile(rb"(?s)(<!-- repoctl:([a-z-]+) -->).*?(<!-- /repoctl:\2 -->)")


def normalized(content: bytes) -> bytes:
    """Content without generated blocks (make sync owns those), so regenerated tables are not your edits."""
    return DERIVED_BLOCK.sub(rb"\1\3", content)


def digest(path: Path) -> str:
    return hashlib.sha256(normalized(path.read_bytes())).hexdigest()


def kit_paths(kit: Path) -> list[str]:
    """Files the template ships as kit, excluding project-owned and template-only material."""
    template = load_project(kit).get("template", {})
    prune = list(template.get("prune", [])) if isinstance(template, dict) else []
    return [path for path in repository_files(kit) if (kit / path).is_file()
            and not any(path_matches(path, pattern) for pattern in (*PROJECT_OWNED, *prune))]


def _kit_version(kit: Path) -> str:
    return (git(kit, "rev-parse", "HEAD") or "").strip() or "unknown"


def project_path(root: Path, path: str) -> str:
    """Where a kit file lives in this project: adopted projects keep the kit Makefile as kit.mk and
    colliding workflows as kit-<name>."""
    if path == "Makefile" and (root / "kit.mk").is_file():
        return "kit.mk"
    if path.startswith(".github/workflows/"):
        renamed = str(Path(path).with_name("kit-" + Path(path).name))
        if (root / renamed).is_file():
            return renamed
    return path


def write_lock(root: Path, kit: Path, paths: list[str] | None = None) -> None:
    """Record what the project now has from the kit (called by init, adopt, and update)."""
    shipped = paths if paths is not None else kit_paths(kit)
    files = {}
    for path in shipped:
        local = project_path(root, path)
        if (root / local).is_file():
            files[path] = digest(root / local)
    (root / LOCK).parent.mkdir(parents=True, exist_ok=True)
    (root / LOCK).write_text(json.dumps({"kit_version": _kit_version(kit), "files": dict(sorted(files.items()))},
                                        indent=1) + "\n", encoding="utf-8")


def read_lock(root: Path) -> dict[str, object]:
    try:
        data = json.loads((root / LOCK).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"kit_version": "none", "files": {}}
    except json.JSONDecodeError as error:
        raise RepoctlError(f"{LOCK} is not valid JSON: {error}") from error
    if not isinstance(data.get("files"), dict):
        raise RepoctlError(f"{LOCK} needs a files table")
    return data


def _new_content(kit: Path, root: Path, path: str) -> bytes:
    """The kit file as this project should have it (kit.mk is regenerated with the project's renames)."""
    if path == "Makefile" and project_path(root, path) == "kit.mk":
        from .adopt import render_kit_makefile
        return render_kit_makefile((root / "Makefile").read_text(encoding="utf-8"), (kit / path).read_text(encoding="utf-8")).encode()
    if path.endswith(".md"):  # the same localization make init applied when the project was made
        from .bootstrap import localize_text
        template = load_project(kit).get("template", {})
        prune = list(template.get("prune", [])) if isinstance(template, dict) else []
        pruned = {file for file in repository_files(kit) if any(path_matches(file, pattern) for pattern in prune)}
        source = str(template.get("source", "")).rstrip("/") if isinstance(template, dict) else ""
        return localize_text(path, (kit / path).read_text(encoding="utf-8"), pruned, prune, source).encode()
    return (kit / path).read_bytes()


def _stage(root: Path, local: str, content: bytes) -> str:
    staged = root / STAGING / local
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(content)
    return staged.relative_to(root).as_posix()


def update(root: Path, kit: Path) -> int:
    root, kit = root.resolve(), kit.resolve()
    if root == kit:
        raise RepoctlError("run kit-update in a project, with KIT pointing at the template checkout")
    if (git(root, "status", "--porcelain") or "").strip():
        raise RepoctlError("commit or stash your changes first, so the kit update is one reviewable change")
    lock = read_lock(root)
    locked: dict[str, str] = lock["files"]  # type: ignore[assignment]
    new_paths = kit_paths(kit)
    updated, added, removed, conflicts = [], [], [], []
    conflicted: set[str] = set()
    if (root / STAGING).exists():
        shutil.rmtree(root / STAGING)
    for path in new_paths:
        local = project_path(root, path)
        target = root / local
        content = _new_content(kit, root, path)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            added.append(local)
        elif normalized(target.read_bytes()) == normalized(content):
            continue
        elif path in locked and digest(target) == locked[path]:
            target.write_bytes(content)
            updated.append(local)
        else:  # changed by the project, or never recorded: do not guess
            conflicts.append(f"{local} (new version: {_stage(root, local, content)})")
            conflicted.add(path)
    for path in sorted(set(locked) - set(new_paths)):
        local = project_path(root, path)
        target = root / local
        if target.is_file() and digest(target) == locked[path]:
            target.unlink()
            removed.append(local)
        elif target.is_file():
            conflicts.append(f"{local} (removed from the kit; yours was changed, so it stays)")
    write_lock(root, kit, [path for path in new_paths if path not in conflicted])
    if conflicted:  # a conflicted file keeps its old hash, so the next update still sees the project's change
        data = read_lock(root)
        data["files"].update({path: locked[path] for path in conflicted if path in locked})  # type: ignore[union-attr]
        data["files"] = dict(sorted(data["files"].items()))  # type: ignore[union-attr]
        (root / LOCK).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    derive.sync(root)
    print(f"Kit updated to {read_lock(root)['kit_version'][:12]} (was {str(lock['kit_version'])[:12]}): "
          f"{len(updated)} updated, {len(added)} added, {len(removed)} removed, {len(conflicts)} to merge by hand.")
    for label, items in (("updated", updated), ("added", added), ("removed", removed)):
        if items:
            print(f"  {label}: {', '.join(items[:10])}{' …' if len(items) > 10 else ''}")
    for item in conflicts:
        print(f"  merge: {item}")
    print("Next: review the diff, merge anything listed, run make done, and commit.")
    return 0


def update_from_source(root: Path, kit: str | None) -> int:
    """KIT is a template checkout; without it, clone [template].source into a temporary directory."""
    if kit:
        return update(root, Path(kit))
    template = load_project(root).get("template", {})
    source = str(template.get("source", "")) if isinstance(template, dict) else ""
    if not source:
        raise RepoctlError("set KIT=<template checkout> or [template].source in project.toml")
    with tempfile.TemporaryDirectory() as folder:
        result = subprocess.run(["git", "clone", "-q", "--depth", "1", source, folder], capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RepoctlError(f"could not clone {source}: {result.stderr.strip()[-300:]} (or pass KIT=<checkout>)")
        return update(root, Path(folder))


def behind_template(root: Path) -> str | None:
    """Advisory for make garden: the template has moved past this project's kit version."""
    lock = read_lock(root)
    template = load_project(root).get("template", {})
    source = str(template.get("source", "")) if isinstance(template, dict) else ""
    if not source or not re.fullmatch(r"[0-9a-f]{40}", str(lock.get("kit_version", ""))):
        return None
    try:
        result = subprocess.run(["git", "ls-remote", source, "HEAD"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    head = result.stdout.split()[0] if result.returncode == 0 and result.stdout.split() else ""
    if head and head != lock["kit_version"]:
        return f"the template ({source}) has moved past this kit ({str(lock['kit_version'])[:12]}): run make kit-update"
    return None
