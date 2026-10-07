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
MAKE_BLOCK = re.compile(rb"(?ms)(^# <repoctl:([a-z-]+)>\n).*?(^# </repoctl:\2>)")


def normalized(content: bytes) -> bytes:
    """Content without generated blocks (make sync owns those), so regenerated tables are not your edits."""
    return MAKE_BLOCK.sub(rb"\1\3", DERIVED_BLOCK.sub(rb"\1\3", content))


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(normalized(content)).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


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


def write_lock(root: Path, kit: Path, paths: list[str] | None = None, kept: list[str] = ()) -> None:
    """Record what the project now has from the kit (init and adopt). `kept` are the project's own files
    at kit paths (make adopt never overwrites them); only the kit's version of those is remembered."""
    shipped = paths if paths is not None else kit_paths(kit)
    files = {path: digest(root / project_path(root, path)) for path in shipped if (root / project_path(root, path)).is_file()}
    _save_lock(root, _kit_version(kit), files, {path: digest_bytes(_new_content(kit, root, path)) for path in kept})


def _save_lock(root: Path, version: str, files: dict[str, str], kept: dict[str, str],
               bases: dict[str, str] | None = None) -> None:
    previous = read_lock(root) if (root / LOCK).is_file() else {}
    if version == "unknown" and previous.get("kit_version") not in (None, "none", "unknown"):
        version = str(previous["kit_version"])  # a non-git kit checkout does not erase a known version
    data: dict[str, object] = {"kit_version": version, "files": dict(sorted(files.items()))}
    if kept:
        data["kept"] = dict(sorted(kept.items()))
    if bases:  # conflicted files: the version they had from the kit before the project's edit
        data["bases"] = dict(sorted(bases.items()))
    (root / LOCK).parent.mkdir(parents=True, exist_ok=True)
    (root / LOCK).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


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
        ours = (root / "Makefile").read_text(encoding="utf-8") if (root / "Makefile").is_file() else ""
        return render_kit_makefile(ours, (kit / path).read_text(encoding="utf-8")).encode()
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
    kept: dict[str, str] = dict(lock.get("kept", {}))  # type: ignore[arg-type]
    bases: dict[str, str] = dict(lock.get("bases", {}))  # type: ignore[arg-type]
    new_paths = kit_paths(kit)
    updated, added, removed, conflicts = [], [], [], []
    files: dict[str, str] = {}
    # A conflict is reported once per kit change: the lock then remembers the version offered, so an
    # unchanged kit stays quiet about a file the project chose to keep its way.
    for path in new_paths:
        local = project_path(root, path)
        target = root / local
        content = _new_content(kit, root, path)
        offered = digest_bytes(content)
        if path in kept:  # the project's own file at a kit path (make adopt kept it)
            if offered != kept[path]:
                conflicts.append(f"{local} is yours; the kit changed its version (see {_stage(root, local, content)})")
                kept[path] = offered
            continue
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            added.append(local)
        elif digest(target) == offered:
            bases.pop(path, None)  # merged by hand, or never differed
        elif path in bases and digest(target) == bases[path]:
            # The project reverted a conflicted file to what the kit gave it: its edit is gone, so update it (#15).
            target.write_bytes(content)
            updated.append(local)
            bases.pop(path)
        elif path in locked and digest(target) == locked[path]:
            target.write_bytes(content)
            updated.append(local)
        elif path in locked and offered == locked[path]:
            files[path] = locked[path]  # the kit did not change it; the project's edit stands
            continue
        else:  # changed by the project, or a file of its own where the kit now ships one
            conflicts.append(f"{local} (new version: {_stage(root, local, content)})")
            if path in locked:
                bases.setdefault(path, locked[path])
        files[path] = offered
    for path in sorted(set(locked) - set(new_paths)):
        local = project_path(root, path)
        target = root / local
        if target.is_file() and digest(target) == locked[path]:
            target.unlink()
            removed.append(local)
        elif target.is_file():
            conflicts.append(f"{local} (removed from the kit; yours was changed, so it stays)")
    kept = {path: value for path, value in kept.items() if path in new_paths}
    _save_lock(root, _kit_version(kit), files, kept, {path: value for path, value in bases.items() if path in files})
    derive.sync(root)
    before = str(lock["kit_version"])
    origin = "no version recorded before" if before in ("unknown", "none") else f"was {before[:12]}"
    print(f"Kit updated to {read_lock(root)['kit_version'][:12]} ({origin}): "
          f"{len(updated)} updated, {len(added)} added, {len(removed)} removed, {len(conflicts)} to merge by hand.")
    for label, items in (("updated", updated), ("added", added), ("removed", removed)):
        if items:
            print(f"  {label}: {', '.join(items[:10])}{' …' if len(items) > 10 else ''}")
    for item in conflicts:
        print(f"  merge: {item}")
    print("Next: review the diff, merge anything listed (then delete its staged copy; make garden lists what is left), "
          "run make done, and commit.")
    return 0


def update_from_source(root: Path, kit: str | None, ref: str | None = None) -> int:
    """KIT is a template checkout; without it, clone [template].source into a temporary directory.
    KIT_REF pins the clone to one commit instead of the template's moving HEAD."""
    if kit:
        if ref:
            raise RepoctlError("KIT_REF applies to the clone of [template].source; with KIT=<checkout>, check out that commit yourself")
        return update(root, Path(kit))
    template = load_project(root).get("template", {})
    source = str(template.get("source", "")) if isinstance(template, dict) else ""
    if not source:
        raise RepoctlError("set KIT=<template checkout> or [template].source in project.toml")
    if ref and (ref.startswith("-") or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._/-]{0,199}", ref)):
        raise RepoctlError(f"KIT_REF {ref!r} is not a commit SHA, tag, or branch name")
    with tempfile.TemporaryDirectory() as folder:
        cloning = ["git", "clone", "-q", *([] if ref else ["--depth", "1"]), source, folder]
        result = subprocess.run(cloning, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RepoctlError(f"could not clone {source}: {result.stderr.strip()[-300:]} (or pass KIT=<checkout>)")
        if ref:
            checkout = subprocess.run(["git", "-C", folder, "checkout", "-q", "--detach", f"{ref}^{{commit}}"],
                                      capture_output=True, text=True, timeout=60)
            if checkout.returncode != 0:
                raise RepoctlError(f"KIT_REF {ref!r} is not a commit of {source}: {checkout.stderr.strip()[-200:]}")
        before = str(read_lock(root).get("kit_version", "none"))
        print(f"Applying kit commits {before[:12] if before not in ('none', 'unknown') else 'unrecorded'}"
              f"..{_kit_version(Path(folder))[:12]} from {source}")
        return update(root, Path(folder))


def pending_merges(root: Path) -> list[str]:
    """Advisory for make garden: kit versions staged by kit-update that nobody has merged yet.
    Delete a staged file once you have merged (or deliberately declined) it."""
    staging = root / STAGING
    if not staging.is_dir():
        return []
    return [f"kit change waiting to merge: {path.relative_to(staging).as_posix()} (staged at {path.relative_to(root).as_posix()}; "
            "merge it, then delete the staged file)" for path in sorted(staging.rglob("*")) if path.is_file()]


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
