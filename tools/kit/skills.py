"""Resource registry and reviewed-skill provenance/admission."""

from __future__ import annotations

import hashlib
import re
import tomllib  # repoctl.py fails fast on Python < 3.11
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .config import project_setting
from .core import (
    KEBAB, RepoctlError, check_failed, date_is_future, ensure_inside_root, is_link_like, is_placeholder,
    load_project, package_repo, package_skill, parse_iso_date, today,
)


BUNDLED_SKILLS = {"agent-handover", "quality-loop", "repository-audit"}
RESOURCE_KINDS = {"library-docs", "platform-policy", "accessibility", "security", "media", "skills", "design"}
RESOURCE_TRUSTS = {"official", "first-party", "reviewed", "discovery"}


def load_resource_registry(root: Path, project: dict[str, object] | None = None) -> list[dict[str, object]]:
    project = project or load_project(root)
    resources = project.get("resources", {})
    if not isinstance(resources, dict):
        raise RepoctlError("resources must be a table")
    registry_value = resources.get("registry", "resources.toml")
    if not isinstance(registry_value, str) or not registry_value.strip():
        raise RepoctlError("resources.registry must be a repository-relative path")
    registry_path = ensure_inside_root(root, root / registry_value, "resource registry")
    try:
        with registry_path.open("rb") as registry_file:
            registry = tomllib.load(registry_file)
    except FileNotFoundError as error:
        raise RepoctlError(f"resource registry is missing: {registry_value}") from error
    except tomllib.TOMLDecodeError as error:
        raise RepoctlError(f"resource registry is invalid: {error}") from error
    if registry.get("schema") != 1:
        raise RepoctlError("resource registry schema must be 1")
    entries = registry.get("resources", [])
    if not isinstance(entries, list) or not entries or not all(isinstance(entry, dict) for entry in entries):
        raise RepoctlError("resource registry must contain a non-empty resources array")
    errors: list[str] = []
    identifiers: set[str] = set()
    for position, entry in enumerate(entries, start=1):
        identifier = entry.get("id")
        kind = entry.get("kind")
        source = entry.get("source")
        trust = entry.get("trust")
        access = entry.get("access")
        scope = entry.get("scope")
        summary = entry.get("summary")
        mcp = entry.get("mcp", "")
        if not isinstance(identifier, str) or not KEBAB.fullmatch(identifier):
            errors.append(f"resource #{position} id must be kebab-case")
        elif identifier in identifiers:
            errors.append(f"duplicate resource id: {identifier}")
        else:
            identifiers.add(identifier)
        if kind not in RESOURCE_KINDS:
            errors.append(f"resource #{position} kind is invalid")
        if trust not in RESOURCE_TRUSTS:
            errors.append(f"resource #{position} trust is invalid")
        if access != "read-only":
            errors.append(f"resource #{position} access must be read-only")
        if not isinstance(source, str) or not source.startswith("https://"):
            errors.append(f"resource #{position} source must be an HTTPS URL")
        else:
            parsed = urlsplit(source)
            if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                errors.append(f"resource #{position} source must be a clean HTTPS URL")
        if not isinstance(scope, str) or not KEBAB.fullmatch(scope):
            errors.append(f"resource #{position} scope must be kebab-case")
        if not isinstance(summary, str) or is_placeholder(summary):
            errors.append(f"resource #{position} summary is required")
        if mcp and (not isinstance(mcp, str) or not KEBAB.fullmatch(mcp)):
            errors.append(f"resource #{position} mcp must be a kebab-case adapter name")
    if errors:
        raise check_failed("resource registry", errors)
    return entries


def check_skill_provenance(project: dict[str, object], release_gate: bool = False) -> None:
    """Provenance must be complete. Review age is a release gate; make garden reports it earlier."""
    skills = project.get("skills", [])
    if not isinstance(skills, list) or not all(isinstance(skill, dict) for skill in skills):
        raise RepoctlError("project.toml skills must be an array of tables")
    errors: list[str] = []
    for position, skill in enumerate(skills, start=1):
        package = skill.get("package")
        source = skill.get("source")
        revision = skill.get("revision")
        package_match = (
            isinstance(package, str)
            and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:@[A-Za-z0-9_.-]+)?", package)
        )
        if not package_match:
            errors.append(f"skill #{position} package must be owner/repository[@skill]")
        source_match = (
            isinstance(source, str)
            and re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source)
        )
        if not source_match:
            errors.append(f"skill #{position} source must be a GitHub HTTPS repository URL")
        if package_match and source_match:
            repository = package_repo(package)
            source_parts = urlsplit(source).path.strip("/").split("/")
            if source_parts != repository.split("/"):
                errors.append(f"skill #{position} source does not match package")
        if not isinstance(revision, str) or not revision.strip():
            errors.append(f"skill #{position} revision is required")
        elif not (
            re.fullmatch(r"[0-9a-f]{40}", revision)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", revision)
        ):
            errors.append(f"skill #{position} revision must be a full commit SHA or sha256 digest")
        elif set(revision.replace("sha256:", "")) == {"0"}:
            errors.append(f"skill #{position} revision must not be an all-zero digest")
        content_digest = skill.get("content_digest")
        if not isinstance(content_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", content_digest):
            errors.append(f"skill #{position} content_digest must be sha256:<64-hex-digest>")
        elif set(content_digest.removeprefix("sha256:")) == {"0"}:
            errors.append(f"skill #{position} content_digest must not be an all-zero digest")
        for field in ("purpose", "reviewed_on", "permissions", "rollback"):
            if is_placeholder(skill.get(field)):
                errors.append(f"skill #{position} {field} is required and concrete")
        reviewed_on = skill.get("reviewed_on")
        if isinstance(reviewed_on, str) and reviewed_on.strip():
            reviewed_date = parse_iso_date(reviewed_on)
            if reviewed_date is None:
                errors.append(f"skill #{position} reviewed_on must be YYYY-MM-DD")
            elif date_is_future(reviewed_date):
                errors.append(f"skill #{position} reviewed_on is in the future")
            elif release_gate and reviewed_date < today() - timedelta(days=int(project_setting(project, "skill_review_days"))):
                errors.append(f"skill #{position} reviewed_on is older than a year: re-review it before release")
        permissions = skill.get("permissions")
        if isinstance(permissions, str):
            tokens = {token.strip().lower() for token in permissions.split("/") if token.strip()}
            allowed = {"read-only", "project-local", "host-adapter", "none"}
            if not tokens or not tokens <= allowed:
                errors.append(f"skill #{position} permissions must use only read-only/project-local/host-adapter")
        rollback = skill.get("rollback")
        if isinstance(rollback, str):
            if re.search(r"(?i)\b(?:unknown|unclear|none|tbd|pending|never)\b", rollback) or not re.search(
                r"(?i)\b(remove|revoke|restore|delete|uninstall|pin)\b", rollback
            ):
                errors.append(f"skill #{position} rollback must name a concrete removal/revocation action")
    if errors:
        raise check_failed("skill provenance", errors)


def directory_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if is_link_like(path):
            raise RepoctlError(f"skill contains an unsupported file type: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise RepoctlError(f"skill contains an unsupported file type: {path}")
        relative_path = path.relative_to(directory)
        # Generated bytecode is .gitignore output, not skill content: excluding
        # it keeps the digest identical before and after a Python test run.
        if "__pycache__" in relative_path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        relative = relative_path.as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(b"X" if path.stat().st_mode & 0o111 else b"F")
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return f"sha256:{digest.hexdigest()}"


def check_skill_admission(root: Path, project: dict[str, object]) -> None:
    entries = project.get("skills", [])
    if not isinstance(entries, list):
        raise RepoctlError("skills must be an array of tables")
    provenance = {
        package_skill(entry.get("package", "")): entry
        for entry in entries
        if isinstance(entry, dict) and "@" in str(entry.get("package", ""))
    }
    capabilities = project.get("capabilities", {})
    local_skills = set(capabilities.get("local_skills", [])) if isinstance(capabilities, dict) else set()
    skill_root = root / ".agents" / "skills"
    if not skill_root.exists():
        return
    for skill_directory in sorted(skill_root.iterdir()):
        if not skill_directory.is_dir() or skill_directory.name.startswith("."):
            continue
        skill_file = skill_directory / "SKILL.md"
        skill_directory = ensure_inside_root(root, skill_directory, "skill directory")
        skill_file = ensure_inside_root(root, skill_file, "bundled skill")
        if not skill_file.is_file():
            raise RepoctlError(f"skill directory is missing SKILL.md: {skill_directory.relative_to(root).as_posix()}")
        name = skill_directory.name
        if name in BUNDLED_SKILLS:
            for child in skill_file.parent.iterdir():
                if child.name == "SKILL.md" or child.name.startswith("."):
                    continue
                raise RepoctlError(
                    f"first-party skill contains an unregistered file: {child.relative_to(root).as_posix()}"
                )
            continue
        if name in local_skills:
            continue  # authored here (make new); reviewed like any other code in this repository
        entry = provenance.get(name)
        if entry is None:
            raise RepoctlError(
                f"skill {name} is neither first-party ([capabilities].local_skills, see `make new`) "
                "nor recorded in [[skills]] provenance (third-party, see docs/skills.md)"
            )
        expected = entry.get("content_digest")
        try:
            actual = directory_digest(skill_file.parent)
        except (OSError, RepoctlError) as error:
            raise RepoctlError(f"cannot digest third-party skill {name}: {error}") from error
        if actual != expected:
            raise RepoctlError(
                f"third-party skill {name} content_digest does not match project provenance"
            )


def print_resources(root: Path) -> None:
    project = load_project(root)
    resources = load_resource_registry(root, project)
    print(f"Resource registry: {project.get('resources', {}).get('registry', 'resources.toml')}")
    for resource in resources:
        mcp = resource.get("mcp") or "none"
        print(f"- {resource['id']} [{resource['kind']}; trust={resource['trust']}; scope={resource['scope']}; mcp={mcp}]: {resource['source']}")
