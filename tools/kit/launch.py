"""Public-launch evidence and readiness gates."""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from .core import (
    KEBAB,
    RepoctlError,
    check_failed,
    date_is_stale,
    date_problem,
    declared_surfaces,
    ensure_inside_root,
    governance_profile,
    is_placeholder,
    load_project,
    normalized_relative_path,
    parse_iso_date,
    secret_matches,
)
from .github import github_target_configured
from .skills import check_skill_provenance
from .uireview import review_status
from .structure import (
    check_vision,
    validate_critic_evidence,
    validation_commands,
)


# A private reporting route must be a real, public host: these names and everything under them are not.
NON_ROUTABLE_HOSTS = ("localhost", "example.com", "example.org", "example.net", "local", "internal", "test", "invalid")


def valid_private_route(value: str) -> bool:
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        return True
    if not re.fullmatch(r"https://[^\s]+", value):
        return False
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower()
    if not hostname or any(hostname == name or hostname.endswith("." + name) for name in NON_ROUTABLE_HOSTS):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        return False
    return not parsed.username and not parsed.password and not parsed.query and not parsed.fragment


def read_evidence_file(
    root: Path,
    value: str,
    label: str,
    markers: tuple[str, ...],
    project_name: str | None = None,
) -> tuple[str | None, str | None]:
    try:
        path = ensure_inside_root(root, root / value, label)
        if path.stat().st_size > 1_000_000:
            return None, f"{label} is larger than 1 MB"
        content = path.read_text(encoding="utf-8")
    except (RepoctlError, OSError, UnicodeDecodeError) as error:
        return None, str(error)
    if secret_matches(content):
        return None, f"{label} contains possible secret material"
    for field in ("Status", "Counsel review", "Evidence type", "Legal owner", "Reviewer", "Observed", "Date"):
        for value in re.findall(rf"(?im)^{re.escape(field)}:\s*(.+?)\s*$", content):
            if is_placeholder(value) or re.search(r"[\[\]]", value):
                return None, f"{label} contains placeholders"
    if re.search(r"\[(?:REQUIRED|pending|TBD|name/team|YYYY-MM-DD)|DRAFT TEMPLATE|REPLACE_WITH|UNSELECTED|^\s*(?:Status|Counsel review|Evidence type|Legal owner|Reviewer|Observed|Date):\s*(?:pending|tbd|required|unknown|none|placeholder)\b", content, re.I | re.M):
        return None, f"{label} contains placeholders"
    for marker in markers:
        if not re.search(marker, content, re.I | re.MULTILINE):
            return None, f"{label} is missing {marker}"
    if project_name is not None:
        expected = re.escape(project_name)
        if not re.search(rf"(?im)^Project:\s*{expected}\s*$", content):
            return None, f"{label} is not bound to project {project_name}"
    dates = re.findall(r"(?im)^Date:\s*(\d{4}-\d{2}-\d{2})\s*$", content)
    if not dates:
        return None, f"{label} is missing a dated review"
    parsed_dates = [parse_iso_date(value) for value in dates]
    if None in parsed_dates:
        return None, f"{label} has an invalid review date"
    if any(date_is_stale(date_value) for date_value in parsed_dates):
        return None, f"{label} review date is stale or in the future"
    for field in ("Reviewer", "Legal owner", "Observed"):
        matches = re.findall(rf"(?im)^{field}:\s*(.+?)\s*$", content)
        if matches and any(len(match.strip()) < 3 or match.strip().lower() in {"x", "n/a", "none"} for match in matches):
            return None, f"{label} has an unverified {field.lower()}"
    return content, None


def _read_inside(root: Path, relative: str, label: str) -> tuple[str | None, str, str]:
    """(text, state, detail) for a repository file; state is ok, escapes (detail says why), missing, or unreadable."""
    try:
        path = ensure_inside_root(root, root / relative, label)
    except RepoctlError as error:
        return None, "escapes", str(error)
    if not path.is_file():
        return None, "missing", ""
    try:
        return path.read_text(encoding="utf-8"), "ok", ""
    except (OSError, UnicodeDecodeError):
        return None, "unreadable", ""


def _launch_routes(project: dict[str, object]) -> tuple[list[str], object, object]:
    security = project.get("security", {})
    if not isinstance(security, dict):
        return ["security must be a table"], None, None
    errors: list[str] = []
    contact, private_reporting = security.get("contact"), security.get("private_reporting")
    if not isinstance(contact, str) or not valid_private_route(contact) or re.search(r"\[|replace|example\.com", contact, re.I):
        errors.append("public launch requires a real monitored security.contact email or HTTPS route")
    if not isinstance(private_reporting, str) or not valid_private_route(private_reporting) or re.search(
        r"\[|replace|example\.com", private_reporting, re.I
    ):
        errors.append("public launch requires a real security.private_reporting email or HTTPS route")
    return errors, contact, private_reporting


def _check_security_policy(root: Path, contact: object, private_reporting: object) -> list[str]:
    text, state, detail = _read_inside(root, "SECURITY.md", "security policy")
    errors = [detail] if state == "escapes" else []
    if state in {"escapes", "missing"}:
        return errors + ["public launch requires SECURITY.md"]
    if state == "unreadable":
        return ["public security policy is unreadable"]
    if re.search(r"\[(?:REQUIRED|pending|TBD)|REPLACE_WITH", text, re.I):
        errors.append("public launch requires a filled private security route in SECURITY.md")
    if isinstance(contact, str) and contact not in text:
        errors.append("SECURITY.md must name the manifest security.contact")
    if isinstance(private_reporting, str) and private_reporting not in text:
        errors.append("SECURITY.md must name the manifest security.private_reporting route")
    return errors


def _check_threat_model(root: Path) -> list[str]:
    text, state, _ = _read_inside(root, ".security/threat-model.md", "threat model")
    if state != "ok":
        return ["public launch requires a readable .security/threat-model.md"]
    found = re.search(r"(?im)^\*{0,2}Last Updated:\*{0,2}\s*(\d{4}-\d{2}-\d{2})\s*$", text)
    if not found:
        return ["threat model must record Last Updated"]
    problem = date_problem(found.group(1), "threat model review is stale or in the future", "threat model Last Updated is invalid")
    return [problem] if problem else []


def _check_security_config(root: Path, contact: object) -> list[str]:
    text, state, detail = _read_inside(root, ".security/config.json", "security configuration")
    errors = [detail] if state == "escapes" else []
    if state in {"escapes", "missing"}:
        return errors + ["public launch requires .security/config.json"]
    try:
        config = json.loads(text) if text is not None else None
    except json.JSONDecodeError:
        config = None
        state = "unreadable"
    if state == "unreadable":
        return ["public security configuration is unreadable"]
    if not isinstance(config, dict):
        return ["public security configuration must be a JSON object"]
    contacts = config.get("security_team_contacts", [])
    if not isinstance(contacts, list) or not contacts or not all(isinstance(item, str) and valid_private_route(item) for item in contacts):
        errors.append("public launch requires valid security_team_contacts")
    elif isinstance(contact, str) and contact not in contacts:
        errors.append("security_team_contacts must include security.contact")
    reviewed_on, reviewer = config.get("security_reviewed_on"), config.get("security_reviewer")
    if not isinstance(reviewed_on, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed_on):
        errors.append("public security configuration needs security_reviewed_on")
    else:
        problem = date_problem(reviewed_on, "security review date is stale or in the future", "security_reviewed_on is invalid")
        if problem:
            errors.append(problem)
    if not isinstance(reviewer, str) or is_placeholder(reviewer) or re.search(r"[\[\]]", reviewer) or len(reviewer.strip()) < 3:
        errors.append("public security configuration needs a named security_reviewer")
    return errors


def _check_launch_evidence(root: Path, project: dict[str, object]) -> list[str]:
    """Legal approval, production evidence, and the public legal documents."""
    errors: list[str] = []
    name = str(project.get("name"))
    launch = project.get("launch", {})
    if not isinstance(launch, dict):
        errors.append("launch must be a table")
    else:
        if launch.get("legal_review") != "approved":
            errors.append("public launch requires legal approval")
        legal_ref = launch.get("legal_review_ref")
        if not isinstance(legal_ref, str) or not legal_ref.strip():
            errors.append("public launch requires a legal review artifact path")
        else:
            _, error = read_evidence_file(
                root, legal_ref, "legal review evidence",
                (r"^Counsel review:\s*approved\s*$", r"^Reviewer:\s*\S+", r"^Date:\s*\d{4}-\d{2}-\d{2}"), name,
            )
            if error:
                errors.append(error)
        if launch.get("production_evidence") != "verified":
            errors.append("public launch requires verified production evidence")
        refs = launch.get("production_evidence_refs", [])
        if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref.strip() for ref in refs):
            errors.append("public launch requires repository production evidence paths")
        else:
            for ref in refs:
                _, error = read_evidence_file(
                    root, ref, "production evidence",
                    (r"^Evidence type:\s*deployed\s*$", r"^Deployment:\s*\S+", r"^Observed:\s*(?!no\b|not\b|none\b)\S+",
                     r"^Reviewer:\s*\S+", r"^Date:\s*\d{4}-\d{2}-\d{2}"), name,
                )
                if error:
                    errors.append(error)
    legal_paths = launch.get("legal_document_paths", []) if isinstance(launch, dict) else []
    if not isinstance(legal_paths, list) or not legal_paths:
        return errors + ["public launch requires an explicit legal_document_paths list"]
    for value in legal_paths:
        if not isinstance(value, str) or Path(value).is_absolute() or not value.startswith("docs/legal/"):
            errors.append("public legal documents must be repository-relative paths under docs/legal/")
            continue
        try:
            normalized_legal = normalized_relative_path(value, "public legal document")
            if not normalized_legal.startswith("docs/legal/"):
                raise RepoctlError("public legal document escapes docs/legal/")
        except RepoctlError as error:
            errors.append(str(error))
            continue
        _, error = read_evidence_file(
            root, normalized_legal, "public legal document",
            (r"^Legal owner:\s*\S+", r"^Reviewer:\s*\S+", r"^Date:\s*\d{4}-\d{2}-\d{2}"), name,
        )
        if error:
            errors.append(error)
    return errors


def _check_data_inventory(root: Path, project: dict[str, object]) -> list[str]:
    text, state, _ = _read_inside(root, "docs/legal/data-inventory.md", "data inventory")
    if state != "ok":
        return ["public launch requires a readable docs/legal/data-inventory.md"]
    errors: list[str] = []
    if not text.strip() or re.search(r"\[(?:REQUIRED|pending|TBD)|REPLACE_WITH|UNSELECTED", text, re.I):
        errors.append("public data inventory must be complete and placeholder-free")
    if not re.search(rf"(?im)^Project:\s*{re.escape(str(project.get('name', '')))}\s*$", text):
        errors.append("public data inventory is not bound to project.toml")
    found = re.search(r"(?im)^Date:\s*(\d{4}-\d{2}-\d{2})\s*$", text)
    if not found:
        errors.append("public data inventory must record its review date")
    else:
        problem = date_problem(found.group(1), "public data inventory review is stale or future-dated",
                         "public data inventory review date is invalid")
        if problem:
            errors.append(problem)
    reviewer = re.search(r"(?im)^Reviewer:\s*(.+?)\s*$", text)
    if not reviewer or is_placeholder(reviewer.group(1)):
        errors.append("public data inventory must name a real reviewer")
    if not re.search(r"(?i)retention", text) or not re.search(r"(?i)rights|deletion|export", text):
        errors.append("public data inventory must cover retention and rights/deletion evidence")
    return errors


def check_public_launch_evidence(root: Path, project: dict[str, object]) -> list[str]:
    errors, contact, private_reporting = _launch_routes(project)
    errors += _check_security_policy(root, contact, private_reporting)
    errors += _check_threat_model(root)
    errors += _check_security_config(root, contact)
    errors += _check_launch_evidence(root, project)
    errors += _check_data_inventory(root, project)
    if not github_target_configured(root, project):
        errors.append("public launch requires a configured GitHub issue register (repository.github or origin)")
    return errors


RELEASE_PHASES = {"private-preview", "public-launch"}


def check_readiness(root: Path) -> None:
    project = load_project(root)
    releasing = project.get("phase") in RELEASE_PHASES  # record ages and UI reviews gate releases, not development
    errors: list[str] = []
    try:
        profile = governance_profile(project)
    except RepoctlError as error:
        profile = "agent-first"
        errors.append(str(error))

    try:
        check_vision(root, project, release_gate=releasing)
    except RepoctlError as error:
        errors.append(str(error))
    from .registry import run_checks  # the registry owns the blocking-check list; doctor adds only what it alone knows
    errors += run_checks(root, blocking_only=True)[0]
    try:
        check_skill_provenance(project, release_gate=releasing)  # the release-gated variant of a registry check
    except RepoctlError as error:
        errors.append(str(error))

    if project.get("name") == "REPLACE_WITH_PROJECT_NAME":
        errors.append("project name is not initialized")
    if not isinstance(project.get("kind"), str) or not KEBAB.fullmatch(project["kind"]):
        errors.append(f"project kind is invalid: {project.get('kind')}")
    if project.get("phase") not in {"bootstrap", "development", "private-preview", "public-launch"}:
        errors.append(f"project phase is invalid: {project.get('phase')}")

    license_name = project.get("license")
    if not isinstance(license_name, str) or license_name in {"", "UNSELECTED"}:
        errors.append("license is not selected")
    elif not (root / "LICENSE").is_file():
        errors.append(f"selected license has no root LICENSE file: {license_name}")

    owners = project.get("owners", [])
    if (
        not isinstance(owners, list)
        or not owners
        or not all(isinstance(owner, str) and owner.strip() and not is_placeholder(owner) for owner in owners)
    ):
        errors.append('at least one accountable owner is required: set owners = ["<handle>"] in project.toml (a handle or team, not an email)')

    surfaces = declared_surfaces(project)
    active_surfaces = [surface for surface in surfaces if surface.get("status", "active") == "active"]
    planned_surfaces = [surface for surface in surfaces if surface.get("status", "active") == "planned"]
    if not active_surfaces and project.get("phase") == "public-launch":
        errors.append("public launch requires at least one active product surface")
    if planned_surfaces and project.get("phase") == "public-launch":
        errors.append("public launch has unresolved planned surfaces")
    if any(surface.get("id") == "template-bootstrap" for surface in planned_surfaces):
        errors.append("template-bootstrap surface must be replaced with the first real product surface")
    if not active_surfaces and not planned_surfaces:
        errors.append("declare at least one active or planned product surface")
    for surface in surfaces:
        if surface.get("status", "active") != "active":
            continue
        if profile != "minimal" and not validation_commands(surface):
            try:
                validate_critic_evidence(root, surface, release_gate=releasing)
            except RepoctlError as error:
                errors.append(str(error))
    if releasing:
        errors.extend(review_status(root))  # one fresh, passing UI review before anyone outside uses it

    launch = project.get("launch", {})
    if project.get("phase") == "public-launch":
        errors.extend(check_public_launch_evidence(root, project))  # reports a non-table launch itself
    elif not isinstance(launch, dict):
        errors.append("launch must be a table")

    if errors:
        raise check_failed("readiness", errors)
    if project.get("phase") == "public-launch":
        print(
            "Configured public-launch gates passed; this is not a full production-readiness "
            "certification. Follow docs/production.md for the complete evidence matrix."
        )
    else:
        print(
            f"Repository is structurally ready for its declared phase ({project.get('phase')}); "
            "public-launch security, legal, and production evidence gates remain inactive."
        )


def check_readiness_gate(root: Path) -> None:
    project = load_project(root)
    if project.get("phase") != "public-launch":
        print("Public launch gate is not active for this project phase.")
        return
    check_readiness(root)
