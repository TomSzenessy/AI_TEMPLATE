"""`make adopt`: bring the agent kit into an existing repository.

`make init` turns a copy of the template into a project. Most real projects
already exist, so adoption copies the kit into one without overwriting anything
the project owns, then runs the same initialization:

- files the project does not have are copied;
- a project file is never overwritten; known collisions are merged instead:
  the Makefile (kit targets go to `kit.mk`, included at the end, with any target
  the project already defines renamed `kit-<name>`), `.gitignore` (missing
  lines appended), `README.md` (the identity block appended), `docs/README.md`
  (the generated index appended), and workflows (written as `kit-<name>`);
- the project's existing docs get an index line so `make check` can route them;
- the kit's LICENSE is never copied into a repository without one (its manifest label is `UNSELECTED`);
- everything else that collides is kept as the project's and listed.

Run it from the existing repository: `make -f <kit>/Makefile adopt KIT=<kit>`
or `python3 <kit>/tools/repoctl.py --root . adopt --from <kit> --name ... --kind ...`.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import derive
from .bootstrap import initialize_project
from .core import RepoctlError, repository_files
from .gitinfo import git
from .kitlock import colliding_targets, kit_paths, RENAMED_TEXT, project_path, rename_mentions, renamed_targets, render_kit_makefile, write_lock

H1 = re.compile(r"(?m)^# (.+)$")
INDEX_LINE = re.compile(r"<!--\s*index:")


def merge_makefile(target: Path, kit_makefile: str) -> list[str]:
    """Write kit.mk; include it at the end of the project Makefile, so the project's default goal stays."""
    project_makefile = (target / "Makefile").read_text(encoding="utf-8")
    renamed = colliding_targets(project_makefile, kit_makefile)
    (target / "kit.mk").write_text(render_kit_makefile(project_makefile, kit_makefile), encoding="utf-8")
    if not re.search(r"(?m)^-?include\s+kit\.mk\s*$", project_makefile):
        separator = "" if project_makefile.endswith("\n") else "\n"
        include = ("\n# Agent kit: " + rename_mentions("make start, make next, make done", renamed) + " (see AGENTS.md)\ninclude kit.mk\n")
        (target / "Makefile").write_text(project_makefile + separator + include, encoding="utf-8")
    return renamed


def merge_gitignore(target: Path, kit_text: str) -> int:
    path = target / ".gitignore"
    current = path.read_text(encoding="utf-8")
    present = {line.strip() for line in current.splitlines()}
    missing = [line for line in kit_text.splitlines() if line.strip() and not line.startswith("#") and line.strip() not in present]
    if missing:
        separator = "" if current.endswith("\n") else "\n"
        path.write_text(current + separator + "\n# Agent kit\n" + "\n".join(missing) + "\n", encoding="utf-8")
    return len(missing)


def index_existing_docs(target: Path, before: set[str]) -> list[str]:
    """Give the project's own Markdown docs an index line so the docs index can route them."""
    indexed = []
    for relative in sorted(before):
        if not (relative.startswith("docs/") and relative.endswith(".md")) or relative == "docs/README.md":
            continue
        path = target / relative
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # not UTF-8: leave the project's document byte-for-byte unchanged
        if INDEX_LINE.search(text):
            continue
        title_match = H1.search(text)
        title = (title_match.group(1) if title_match else Path(relative).stem.replace("-", " ")).replace("|", "/").strip()
        line = f"<!-- index: design | {title} | Working on {title.lower()}. -->"
        if title_match:
            text = text[:title_match.end()] + "\n\n" + line + text[title_match.end():]
        else:
            text = line + "\n\n" + text
        path.write_text(text, encoding="utf-8")
        indexed.append(relative)
    return indexed


LICENSES = (("MIT License", "MIT"), ("Apache License", "Apache-2.0"), ("GNU GENERAL PUBLIC LICENSE", "GPL-3.0-or-later"),
            ("Mozilla Public License", "MPL-2.0"), ("BSD 3-Clause", "BSD-3-Clause"), ("BSD 2-Clause", "BSD-2-Clause"))


def keep_project_license(target: Path, project_had_one: bool) -> str | None:
    """The project's LICENSE stays; the manifest label follows it instead of the kit's."""
    manifest = target / "project.toml"
    text = manifest.read_text(encoding="utf-8")
    if not project_had_one:
        manifest.write_text(re.sub(r'(?m)^license\s*=\s*"[^"]*"', 'license = "UNSELECTED"', text, count=1), encoding="utf-8")
        return ('no LICENSE of yours: none was added (a license is your choice, not the kit\'s); '
                'license = "UNSELECTED" in project.toml until you add a LICENSE and set it')
    head = (target / "LICENSE").read_text(encoding="utf-8", errors="replace")[:400]
    label = next((spdx for marker, spdx in LICENSES if marker.lower() in head.lower()), "UNSELECTED")
    manifest.write_text(re.sub(r'(?m)^license\s*=\s*"[^"]*"', f'license = "{label}"', text, count=1), encoding="utf-8")
    return f"license label set to {label} from your LICENSE" + (" (set it by hand)" if label == "UNSELECTED" else "")


def adopt(target: Path, kit: Path, name: str, kind: str, owner: str | None) -> None:
    target, kit = target.resolve(), kit.resolve()
    if target == kit:
        raise RepoctlError("run adopt from the existing repository, with --from pointing at the kit")
    if (target / "tools" / "kit").exists() or ((target / "AGENTS.md").exists() and (target / "project.toml").exists()):
        raise RepoctlError("this repository already has the agent kit (AGENTS.md and project.toml); edit it instead")
    if git(target, "rev-parse", "--git-dir") is None:
        raise RepoctlError("adopt needs a git repository (git init and commit the existing code first)")
    if (git(target, "status", "--porcelain") or "").strip():
        raise RepoctlError("commit or stash the existing changes first, so the adoption is one reviewable change")
    before = set((git(target, "ls-files", "-z") or "").split("\0")) - {""}
    copied, kept, merged = [], [], []
    renamed: list[str] = []  # known before any file is written, so every mention agrees with kit.mk
    if (target / "Makefile").is_file() and (kit / "Makefile").is_file():
        renamed = colliding_targets((target / "Makefile").read_text(encoding="utf-8"), (kit / "Makefile").read_text(encoding="utf-8"))
    for relative in repository_files(kit, walk=False):  # template-only material too; init prunes it as make init does
        source, destination = kit / relative, target / relative
        if relative.startswith(".github/workflows/") and destination.exists():
            destination = destination.with_name("kit-" + destination.name)
        if relative == "LICENSE" and not destination.exists():
            continue  # the kit's own license is not the adopter's to inherit
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(destination.relative_to(target).as_posix())  # a renamed workflow is reported as renamed
        elif relative == "Makefile":
            renamed = merge_makefile(target, source.read_text(encoding="utf-8"))
            note = f"; renamed: {', '.join('kit-' + n for n in renamed)}" if renamed else ""
            merged.append(f"Makefile (kit targets in kit.mk{note})")
        elif relative == ".gitignore":
            merged.append(f".gitignore ({merge_gitignore(target, source.read_text(encoding='utf-8'))} line(s) added)")
        elif relative == "README.md":
            text = destination.read_text(encoding="utf-8")
            if "<!-- repoctl:project-readme -->" not in text:
                block = (f"\n<!-- repoctl:project-readme -->\n> Project initialized: **{name}** (`{kind}`). Agents start "
                         + rename_mentions("with [`AGENTS.md`](./AGENTS.md): `make start`, `make next`, `make done`.\n", renamed))
                destination.write_text(text + ("" if text.endswith("\n") else "\n") + block, encoding="utf-8")
            merged.append("README.md (identity block appended)")
        elif relative == "docs/README.md":
            text = destination.read_text(encoding="utf-8")
            if "<!-- repoctl:index -->" not in text:
                section = "\n## Documentation index\n\n<!-- repoctl:index -->\n<!-- /repoctl:index -->\n"
                destination.write_text(text + section, encoding="utf-8")
            merged.append("docs/README.md (generated index appended)")
        else:
            kept.append(relative)
    indexed = index_existing_docs(target, before)
    initialize_project(target, name, kind, owner, mode="adopt")
    shipped = kit_paths(kit)  # your kept files are never kit files; only the kit's version of them is remembered
    targets = renamed_targets(target)
    for relative in [*shipped, "project.toml"]:  # prose follows the renamed targets (make kit-update renders the same way)
        path = target / project_path(target, relative)  # a renamed workflow, never the project's own
        if relative.endswith(RENAMED_TEXT) and relative not in kept and path.is_file():
            text = path.read_text(encoding="utf-8")
            if rename_mentions(text, targets) != text:
                path.write_text(rename_mentions(text, targets), encoding="utf-8")
    license_note = keep_project_license(target, (target / "LICENSE").is_file())
    derive.sync(target)
    write_lock(target, kit, [path for path in shipped if path not in kept], [path for path in kept if path in shipped])
    print(f"Adopted the agent kit: {len(copied)} file(s) added, {len(merged)} merged, {len(kept)} of yours kept.")
    for item in merged:
        print(f"  merged: {item}")
    if kept:
        print(f"  kept yours: {', '.join(kept[:12])}{' …' if len(kept) > 12 else ''}")
    if license_note:
        print(f"  {license_note}")
    if indexed:
        print(f"  index lines added to your docs (edit the wording): {', '.join(indexed[:8])}{' …' if len(indexed) > 8 else ''}")
    print("  CI: .github/workflows/kit-ci.yml runs only the toolchain-free gate (repoctl check); it installs no Node/Go/etc., "
          "so run your surfaces' own tests in your project's CI (docs/ADAPTATION.md#kit-ci-and-your-toolchains).")
    print("Next: declare your existing code as surfaces (make inventory shows candidates), then make next.")
