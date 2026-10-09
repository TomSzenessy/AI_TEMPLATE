"""Manifest surfaces, vision intake, README identity, inventory, and declared verification."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .core import (
    verification_environment,
    CONTAINER_DIRECTORIES,
    FILE_SURFACE_KINDS,
    KEBAB,
    REPOSITORY_INFRASTRUCTURE_DIRECTORIES,
    RepoctlError,
    check_failed,
    date_out_of_policy,
    read_utf8,
    repository_files,
    declared_surfaces,
    ensure_inside_root,
    governance_profile,
    infrastructure_paths,
    is_link_like,
    is_placeholder,
    load_project,
    parse_iso_date,
    normalized_relative_path,
    secret_matches,
    surface_extra_paths,
    surface_owned_paths,
)
from .gitinfo import git, run_git
from .names import STACK_DECISION, VISION
from .skills import check_skill_admission, load_resource_registry


def discover_candidate_surfaces(
    root: Path, project: dict[str, object] | None = None
) -> list[str]:
    project = project or load_project(root)
    ignored = infrastructure_paths(project)
    candidates: set[str] = set()
    top_level_directories: set[str] = set()
    product_files = {
        "main.py", "app.py", "index.html", "index.ts", "index.tsx",
        "main.ts", "main.tsx", "design.blend", "scene.blend", "Cargo.toml",
    }
    for child in root.iterdir():
        if is_link_like(child):
            continue
        try:
            if child.is_file() and child.name in product_files:
                candidates.add(child.name)
            elif child.is_dir() and not child.name.startswith(".") and child.name not in ignored:
                top_level_directories.add(child.name)
        except OSError:
            continue
    for directory in sorted(top_level_directories):
        path = root / directory
        if directory in CONTAINER_DIRECTORIES:
            for child in sorted(path.iterdir()):
                if is_link_like(child):
                    continue
                try:
                    is_directory = child.is_dir()
                    is_file = child.is_file()
                except OSError:
                    continue
                child_relative = child.relative_to(root).as_posix()
                if (is_directory and not child.name.startswith(".")) or (is_file and child.name in product_files):
                    if child_relative not in ignored:
                        candidates.add(child_relative)
        else:
            candidates.add(path.relative_to(root).as_posix())
    held = _held_paths(repository_files(root))
    return sorted((candidates & held) - _git_ignored(root, candidates))


def _held_paths(files: list[str]) -> set[str]:
    """Every listed file plus each ancestor directory of one. A directory holding only ignored output is absent."""
    held: set[str] = set()
    for relative in files:
        parts = relative.split("/")
        for depth in range(1, len(parts) + 1):
            held.add("/".join(parts[:depth]))
    return held


def _git_ignored(root: Path, paths: set[str]) -> set[str]:
    """The paths git ignores. Build output such as *.egg-info/ or .next/ is never a product surface.

    A round-5 Haiku trial was told to register `ledger_cli.egg-info` as a surface while
    .gitignore already ignored it. Outside git nothing is known to be ignored.
    """
    if not paths:
        return set()
    found = run_git(root, "check-ignore", "--stdin", input="\n".join(sorted(paths)) + "\n")
    if found is None or found.returncode not in (0, 1):
        return set()
    return {line.strip().rstrip("/") for line in found.stdout.splitlines() if line.strip()}


def validation_commands(surface: dict[str, object]) -> list[list[str]]:
    commands = surface.get("verification", [])
    if not isinstance(commands, list):
        raise RepoctlError(f"surface {surface.get('id', '<missing id>')} verification must be an array")
    normalized: list[list[str]] = []
    for position, command in enumerate(commands, start=1):
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(argument, str) and argument for argument in command)
        ):
            raise RepoctlError(
                f"surface {surface.get('id', '<missing id>')} verification command #{position} must contain non-empty strings"
            )
        if command and command[0].rsplit("/", 1)[-1] in {"make", "gmake"} and "verify" in command[1:]:
            raise RepoctlError("surface verification must not call the aggregate make verify command")
        if any(
            argument.rstrip("/\\").split("/")[-1].split("\\")[-1] in {"repoctl", "repoctl.py"}
            or argument in {"tools.repoctl"}
            for argument in command
        ) and "verify" in command:
            raise RepoctlError("surface verification must not call the aggregate verify command")
        normalized.append(command)
    return normalized


def critic_evidence_paths(surface: dict[str, object]) -> list[str]:
    value = surface.get("critic_evidence", [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise RepoctlError(
            f"surface {surface.get('id', '<missing id>')} critic_evidence must be an array of paths"
        )
    return value


def validate_critic_evidence(root: Path, surface: dict[str, object], release_gate: bool = False) -> None:
    paths = critic_evidence_paths(surface)
    if not paths:
        raise RepoctlError(
            f"surface {surface.get('id', '<missing id>')} needs critic_evidence when no automated verification exists"
        )
    for value in paths:
        if Path(value).is_absolute():
            raise RepoctlError("critic evidence paths must be repository-relative")
        path = ensure_inside_root(root, root / value, "critic evidence")
        try:
            content = read_utf8(path)
        except FileNotFoundError as error:
            raise RepoctlError(f"critic evidence does not exist: {value}") from error
        except OSError as error:  # a directory, or a file the process cannot read
            raise RepoctlError(f"critic evidence cannot be read: {value} ({error.strerror})") from error
        if secret_matches(content):
            raise RepoctlError(f"critic evidence contains possible secret material: {value}")
        for pattern, message in (
            (r"(?im)^Issue:\s*#?[0-9]+", "issue reference"),
            (r"(?im)^Commit:\s*[0-9a-f]{40}\b", "immutable commit"),
            (r"(?im)^Artifact:\s*\S+", "artifact reference"),
            (r"(?im)^Reviewer:\s*\S+", "reviewer"),
            (r"(?im)^Date:\s*\d{4}-\d{2}-\d{2}", "review date"),
            (r"(?im)^Result:\s*(?:pass|approved)\b", "passing result"),
        ):
            if not re.search(pattern, content):
                raise RepoctlError(f"critic evidence {value} is missing {message}")
        critic_reviewer = re.search(r"(?im)^Reviewer:\s*(.+?)\s*$", content)
        if not critic_reviewer or is_placeholder(critic_reviewer.group(1)):
            raise RepoctlError(f"critic evidence reviewer is not named: {value}")
        artifact = re.search(r"(?im)^Artifact:\s*(\S+)", content)
        if artifact and not artifact.group(1).startswith("https://"):
            artifact_path = ensure_inside_root(root, root / artifact.group(1), "critic artifact")
            if not artifact_path.is_file():
                raise RepoctlError(f"critic artifact does not exist: {artifact.group(1)}")
        reviewed = re.search(r"(?im)^Date:\s*(\d{4}-\d{2}-\d{2})", content)
        if reviewed:
            reviewed_date = parse_iso_date(reviewed.group(1))
            if reviewed_date is None:
                raise RepoctlError(f"critic evidence has an invalid date: {value}")
            if date_out_of_policy(reviewed_date, release_gate):
                raise RepoctlError(f"critic evidence is {'stale or ' if release_gate else ''}future-dated: {value}")
        commit = re.search(r"(?im)^Commit:\s*([0-9a-f]{40})\b", content)
        if commit:
            head = git(root, "rev-parse", "HEAD", timeout=10)
            if head is not None and head.strip() != commit.group(1):
                raise RepoctlError(f"critic evidence is not bound to current HEAD: {value}")


def check_structure(root: Path, project: dict[str, object]) -> None:
    errors: list[str] = []
    try:
        profile = governance_profile(project)
    except RepoctlError as error:
        profile = "agent-first"
        errors.append(str(error))
    surfaces = declared_surfaces(project)
    try:
        governance = project.get("governance", {})
        if not isinstance(governance, dict):
            raise RepoctlError("governance must be a table")
        for field in ("issue_template", "label_registry"):
            if field not in governance:
                continue
            value = governance[field]
            if not isinstance(value, str) or not value.strip():
                raise RepoctlError(f"governance.{field} must be a repository-relative path")
            configured_path = ensure_inside_root(root, root / value, f"governance.{field}")
            if not configured_path.is_file():
                raise RepoctlError(f"governance.{field} does not exist: {value}")
    except RepoctlError as error:
        errors.append(str(error))
    try:
        if "resources" in project:
            load_resource_registry(root, project)
    except RepoctlError as error:
        errors.append(str(error))
    try:
        check_vision(root, project, enforce=False)
        check_skill_admission(root, project)
    except RepoctlError as error:
        errors.append(str(error))
    if profile in {"minimal", "regulated"}:
        issue_templates = root / ".github" / "ISSUE_TEMPLATE"
        if issue_templates.exists() and any(issue_templates.glob("*.yml")):
            route = "host" if profile == "minimal" else "CLI/private"
            errors.append(f"{profile} profile must remove or disable native issue forms; use the {route} route")
    surface_ids: set[str] = set()
    surface_paths_seen: set[str] = set()
    declared_paths: set[str] = set()
    claimed_by: dict[str, str] = {}

    for position, surface in enumerate(surfaces, start=1):
        identifier = surface.get("id")
        if not isinstance(identifier, str) or not KEBAB.fullmatch(identifier):
            errors.append(f"surface #{position} needs a kebab-case id")
        elif identifier in surface_ids:
            errors.append(f"duplicate surface id: {identifier}")
        else:
            surface_ids.add(identifier)

        try:
            path_value = normalized_relative_path(surface.get("path"), "surface path")
            surface_path = ensure_inside_root(
                root, root / path_value, f"surface {identifier or position} path"
            )
        except RepoctlError as error:
            errors.append(str(error))
            continue
        declared_paths.add(path_value)
        status = surface.get("status", "active")

        # A surface owns its path plus any entry files its generator put outside it (#57).
        label = str(identifier or f"#{position}")
        try:
            extras = surface_extra_paths(surface, label)
        except RepoctlError as error:
            errors.append(str(error))
            extras = []
        if path_value in claimed_by:
            errors.append(f"duplicate surface path: {path_value} (already an extra_paths entry of {claimed_by[path_value]})")
        claimed_by.setdefault(path_value, label)
        for extra in extras:
            previous = claimed_by.setdefault(extra, label)
            if previous != label:
                errors.append(f"duplicate surface path: {extra} (owned by both {previous} and {label})")
            declared_paths.add(extra)
            try:
                extra_path = ensure_inside_root(root, root / extra, f"surface {label} extra path")
            except RepoctlError as error:
                errors.append(str(error))
                continue
            if status == "active" and not extra_path.exists():
                errors.append(f"active surface {label} extra path does not exist: {extra}")

        if status in {"active", "planned"} and path_value in surface_paths_seen:
            errors.append(f"duplicate surface path: {path_value}")
        surface_paths_seen.add(path_value)
        if status not in {"active", "planned", "retired"}:
            errors.append(f"surface {identifier or position} has invalid status: {status}")
        surface_kind = surface.get("kind")
        if not isinstance(surface_kind, str) or not KEBAB.fullmatch(surface_kind):
            errors.append(f"surface {identifier or position} needs a kebab-case kind")
        if status == "active" and not surface_path.exists():
            errors.append(f"active surface path does not exist: {path_value}")
        elif status == "active" and not surface_path.is_dir() and surface_kind not in FILE_SURFACE_KINDS:
            errors.append(f"active surface path must be a directory or explicit file surface: {path_value}")
        if status == "active" and (
            is_placeholder(surface.get("owner"))
        ):
            errors.append(f'active surface {identifier or position} needs an owner: owner = "<handle>" in its [[surfaces]] table')
        if status == "active" and (
            is_placeholder(surface.get("quality_oracle"))
        ):
            errors.append(f"active surface {identifier or position} needs a quality oracle")
        if status == "retired" and (root / path_value).exists():
            errors.append(f"retired surface path still exists: {path_value}")
        try:
            commands = validation_commands(surface)
        except RepoctlError as error:
            errors.append(str(error))
            commands = []
        if status == "active" and not commands and profile != "minimal":
            try:
                validate_critic_evidence(root, surface)
            except RepoctlError as error:
                errors.append(str(error))

    for candidate in discover_candidate_surfaces(root, project):
        if candidate not in declared_paths:
            errors.append(
                f"unregistered product surface: {candidate} (if it belongs to an existing surface, such as the root "
                f"index.html a web generator writes beside the app code, add it to that surface's "
                f'extra_paths = ["{candidate}"]; or declare it as its own [[surfaces]] entry with '
                f'path = "{candidate}", kind, owner, quality_oracle, and verification commands; or, when it only '
                "supports another surface such as its tests, add it to [repository].infrastructure_paths)"
            )

    if len([surface for surface in surfaces if surface.get("status", "active") in {"active", "planned"}]) > 1:
        architecture_path = root / "docs" / "architecture" / "README.md"
        try:
            architecture = ensure_inside_root(root, architecture_path, "architecture map")
            architecture_text = architecture.read_text(encoding="utf-8")
        except (RepoctlError, OSError, UnicodeDecodeError):
            errors.append("multi-surface project requires docs/architecture/README.md")
        else:
            for surface in surfaces:
                if surface.get("status", "active") not in {"active", "planned"}:
                    continue  # a retired surface needs no architecture row
                identifier = str(surface.get("id", ""))
                if identifier and not re.search(rf"(?m)^\|\s*`?{re.escape(identifier)}`?\s*\|", architecture_text):
                    errors.append(f"architecture map is missing declared surface: {identifier}")

    if errors:
        raise check_failed("structure", errors)


def check_vision(root: Path, project: dict[str, object], enforce: bool = True, release_gate: bool = False) -> None:
    if "vision" not in project:
        raise RepoctlError("project.toml must declare the vision intake record")
    vision = project.get("vision", {})
    if not isinstance(vision, dict):
        raise RepoctlError("vision must be a table")
    status = vision.get("status")
    record = vision.get("record")
    if status != "accepted":
        if enforce:
            raise RepoctlError(
                "project vision must be accepted before scaffolding: run the product-kickoff intake (make next), "
                'then set Status: accepted with Owner and Date in VISION.md and [vision].status = "accepted" in project.toml'
            )
        return
    if record != VISION:
        raise RepoctlError("vision.record must be exactly VISION.md")
    _check_record(
        root, project, record, "vision record", "accepted vision record", release_gate,
        status_message="VISION.md must record Status: accepted", unbound_message="VISION.md is not bound to project.toml",
        accepted_first=True, placeholders="accepted vision record still contains intake placeholders",
    )
    stack = vision.get("stack_decision")
    if stack != STACK_DECISION:
        raise RepoctlError("vision.stack_decision must be exactly docs/STACK-DECISION.md")
    _check_record(
        root, project, stack, "stack decision record", "project stack decision", release_gate,
        status_message="project stack decision must be accepted before scaffolding" if project.get("kind") != "template" else None,
        unbound_message="stack decision record is not bound to project.toml", accepted_first=False,
    )


def _check_record(root: Path, project: dict[str, object], relative: str, label: str, noun: str, release_gate: bool, *,
                  status_message: str | None, unbound_message: str, accepted_first: bool,
                  placeholders: str | None = None) -> None:
    """One validation for an owner-accepted record (the vision, the stack decision): readable, bound to this
    project, accepted (when `status_message` is given), and carrying an owner and a date inside the window."""
    try:
        content = ensure_inside_root(root, root / relative, label).read_text(encoding="utf-8")
    except (RepoctlError, OSError, UnicodeDecodeError) as error:
        raise RepoctlError(f"{label} is unavailable or outside the repository") from error
    unaccepted = status_message is not None and not re.search(r"(?im)^Status:\s*accepted\s*$", content)
    if unaccepted and accepted_first:
        raise RepoctlError(status_message)
    if not re.search(rf"(?im)^Project:\s*{re.escape(str(project.get('name', '')))}\s*$", content):
        # Say what "bound" means: a round-4 Haiku trial spent its whole budget guessing at key names.
        raise RepoctlError(f"{unbound_message}: {relative} needs the line 'Project: {project.get('name', '')}' "
                           "(the name in project.toml)")
    if unaccepted:
        raise RepoctlError(status_message)
    if placeholders and re.search(r"\[(?:REQUIRED|TBD|pending)|\bTBD\b", content, re.I):
        raise RepoctlError(placeholders)
    if status_message is None:
        return  # the template's own record is a placeholder; only its binding matters
    owner = re.search(r"(?im)^Owner:\s*(.+?)\s*$", content)
    found = re.search(r"(?im)^Date:\s*(\d{4}-\d{2}-\d{2})\s*$", content)
    if not owner or is_placeholder(owner.group(1)) or not found:
        raise RepoctlError(f"{noun} must name an owner and valid date: lines 'Owner: <handle>' and 'Date: YYYY-MM-DD' in {relative}")
    recorded = parse_iso_date(found.group(1))
    if recorded is None:
        raise RepoctlError(f"{noun} date is invalid")
    if date_out_of_policy(recorded, release_gate):
        raise RepoctlError(f"{noun} date is stale or future-dated")


def is_template(project: dict[str, object]) -> bool:
    repository = project.get("repository")
    return isinstance(repository, dict) and repository.get("is_template") is True


def manifest_type_errors(project: dict[str, object]) -> list[str]:
    """Findings for manifest fields whose type other checks index into (checked once, here)."""
    errors = []
    owners = project.get("owners", [])
    if not isinstance(owners, list) or not all(isinstance(owner, str) for owner in owners):
        errors.append("project.toml owners must be an array of strings (handles or team names)")
    skills = project.get("skills", [])
    if not isinstance(skills, list) or not all(isinstance(entry, dict) for entry in skills):
        errors.append("project.toml [[skills]] must be an array of tables")
    if not isinstance(project.get("repository", {}), dict):
        errors.append("project.toml repository must be a table")
    surfaces = project.get("surfaces", [])
    if isinstance(surfaces, list):
        for surface in surfaces:
            if isinstance(surface, dict) and not isinstance(surface.get("garden", []), list):
                errors.append(f"surface {surface.get('id', '<missing id>')} garden must be an array of command arrays")
    return errors


def check_readme_identity(root: Path, project: dict[str, object]) -> None:
    if project.get("name") == "REPLACE_WITH_PROJECT_NAME" or is_template(project):
        return  # the template states template mode; only `make init` writes a project identity
    readme = root / "README.md"
    try:
        content = read_utf8(readme)
    except (FileNotFoundError, OSError) as error:
        raise RepoctlError("initialized project README.md is missing") from error
    marker = "<!-- repoctl:project-readme -->"
    if marker not in content:
        raise RepoctlError(f"initialized project README.md needs the project identity marker: restore the line "
                           f"'{marker}' near its top (make init wrote it)")
    identity = re.search(
        r"(?m)^> Project initialized: \*\*(?P<name>[^*]+)\*\* \(`(?P<kind>[^`]+)`\)",
        content,
    )
    if not identity:
        raise RepoctlError("initialized project README.md needs a project identity marker value: the line "
                           f"'> Project initialized: **{project.get('name')}** (`{project.get('kind')}`)' under the marker")
    if identity.group("name") != project.get("name") or identity.group("kind") != project.get("kind"):
        raise RepoctlError("README project identity does not match project.toml")
    # Column 0 is hand-written quickstart prose; a generated block (the `make help` listing
    # renders `make init NAME=my-project ...` indented) is `make sync`'s, not template scaffolding.
    if project.get("name") != "AI_TEMPLATE" and re.search(
            r"(?m)^# Agent Template$|^cp -R AGENT_TEMPLATE my-project|^make init NAME=my-project", content):
        raise RepoctlError("initialized project README.md still contains template bootstrap text")


def run_verification(root: Path) -> None:
    try:
        depth = int(os.environ.get("REPOCTL_VERIFY_DEPTH", "0"))
    except ValueError as error:
        raise RepoctlError("REPOCTL_VERIFY_DEPTH must be an integer") from error
    if depth > 2:
        raise RepoctlError("surface verification recursion depth exceeded")
    project = load_project(root)
    profile = governance_profile(project)
    # The registry's blocking checks (structure, docs, hygiene, provenance) already ran in
    # `repoctl verify` before this; running them again here made each run twice.
    for surface in declared_surfaces(project):
        if surface.get("status", "active") != "active":
            continue
        identifier = surface["id"]
        surface_path = ensure_inside_root(
            root, root / surface["path"], f"surface {identifier} path"
        )
        surface_root = surface_path if surface_path.is_dir() else surface_path.parent
        commands = validation_commands(surface)
        if not commands:
            if profile != "minimal":
                validate_critic_evidence(root, surface)
                print(f"{identifier}: critic evidence accepted; independent confirmation remains required")
            else:
                print(f"{identifier}: no automated command; minimal profile leaves review to the host")
            continue
        for command in commands:
            print(f"{identifier}: running {' '.join(command)}")
            try:
                command_environment = verification_environment()
                command_environment["REPOCTL_VERIFY_DEPTH"] = str(depth + 1)
                result = subprocess.run(
                    command,
                    cwd=surface_root,
                    check=False,
                    timeout=1800,
                    env=command_environment,
                )
            except (OSError, subprocess.TimeoutExpired) as error:  # not found, not executable, ...
                raise RepoctlError(f"{identifier}: verification command failed to run: {error}") from error
            if result.returncode != 0:
                raise RepoctlError(
                    f"{identifier}: verification command exited {result.returncode}: {' '.join(command)}"
                )
        print(f"{identifier}: verification passed")


def print_inventory(root: Path) -> None:
    project = load_project(root)
    candidates = discover_candidate_surfaces(root, project)
    surfaces = declared_surfaces(project)
    owned = surface_owned_paths(project)
    declared_paths = {path for paths in owned.values() for path in paths}

    print(f"Project: {project['name']} ({project['kind']})")
    print("Infrastructure defaults: " + ", ".join(sorted(REPOSITORY_INFRASTRUCTURE_DIRECTORIES)))
    repository = project.get("repository", {})
    configured_paths = repository.get("infrastructure_paths", []) if isinstance(repository, dict) else []
    if configured_paths and isinstance(configured_paths, list):
        print("Configured infrastructure paths: " + ", ".join(sorted(configured_paths)))
    print("Candidate product surfaces:")
    if candidates:
        for candidate in candidates:
            marker = "declared" if candidate in declared_paths else "unregistered"
            print(f"- {candidate} [{marker}]")
    else:
        print("- none detected")

    if surfaces:
        print("Declared surfaces:")
        for surface in surfaces:
            extras = owned.get(str(surface.get("id", "<missing id>")), [])[1:]
            tail = f" (+ {', '.join(extras)})" if extras else ""
            print(
                f"- {surface.get('id', '<missing id>')}: {surface.get('path', '<missing path>')}{tail} "
                f"({surface.get('status', 'active')})"
            )
    else:
        print("Declared surfaces: none")
