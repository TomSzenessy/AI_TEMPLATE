"""Public-launch evidence and readiness gates."""

from __future__ import annotations

import ipaddress
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .core import (
    PROJECT_KIND_PATTERN,
    RepoctlError,
    date_is_stale,
    declared_surfaces,
    ensure_inside_root,
    governance_profile,
    is_placeholder,
    load_project,
    normalized_relative_path,
    secret_matches,
)
from .docs import check_docs_index, check_file_hygiene, check_markdown_links
from .github import github_target_configured
from .skills import check_skill_provenance
from .uireview import review_status
from .structure import (
    check_readme_identity,
    check_structure,
    check_vision,
    validate_critic_evidence,
    validation_commands,
)


def valid_private_route(value: str) -> bool:
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        return True
    if not re.fullmatch(r"https://[^\s]+", value):
        return False
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname in {"localhost", "example.com", "attacker"} or hostname.endswith((".local", ".internal")):
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
    try:
        parsed_dates = [datetime.strptime(value, "%Y-%m-%d").date() for value in dates]
    except ValueError:
        return None, f"{label} has an invalid review date"
    if any(date_is_stale(date_value) for date_value in parsed_dates):
        return None, f"{label} review date is stale or in the future"
    for field in ("Reviewer", "Legal owner", "Observed"):
        matches = re.findall(rf"(?im)^{field}:\s*(.+?)\s*$", content)
        if matches and any(len(match.strip()) < 3 or match.strip().lower() in {"x", "n/a", "none"} for match in matches):
            return None, f"{label} has an unverified {field.lower()}"
    return content, None


def check_public_launch_evidence(root: Path, project: dict[str, object]) -> list[str]:
    errors: list[str] = []
    contact: str | None = None
    private_reporting: str | None = None
    security = project.get("security", {})
    if not isinstance(security, dict):
        errors.append("security must be a table")
    else:
        contact = security.get("contact")
        private_reporting = security.get("private_reporting")
        if not isinstance(contact, str) or not valid_private_route(contact) or re.search(
            r"\[|replace|example\.com", contact, re.I
        ):
            errors.append("public launch requires a real monitored security.contact email or HTTPS route")
        if not isinstance(private_reporting, str) or not valid_private_route(private_reporting) or re.search(
            r"\[|replace|example\.com", private_reporting, re.I
        ):
            errors.append("public launch requires a real security.private_reporting email or HTTPS route")
    security_document = root / "SECURITY.md"
    try:
        security_document = ensure_inside_root(root, security_document, "security policy")
    except RepoctlError as error:
        errors.append(str(error))
        security_document = Path("/nonexistent")
    if not security_document.is_file():
        errors.append("public launch requires SECURITY.md")
    else:
        try:
            security_text = security_document.read_text(encoding="utf-8")
            if re.search(r"\[(?:REQUIRED|pending|TBD)|REPLACE_WITH", security_text, re.I):
                errors.append("public launch requires a filled private security route in SECURITY.md")
            if isinstance(contact, str) and contact not in security_text:
                errors.append("SECURITY.md must name the manifest security.contact")
            if isinstance(private_reporting, str) and private_reporting not in security_text:
                errors.append("SECURITY.md must name the manifest security.private_reporting route")
        except (OSError, UnicodeDecodeError):
            errors.append("public security policy is unreadable")
    threat_model = root / ".security" / "threat-model.md"
    try:
        threat_model = ensure_inside_root(root, threat_model, "threat model")
        threat_text = threat_model.read_text(encoding="utf-8")
    except (RepoctlError, OSError, UnicodeDecodeError):
        errors.append("public launch requires a readable .security/threat-model.md")
    else:
        threat_date = re.search(r"(?im)^\*{0,2}Last Updated:\*{0,2}\s*(\d{4}-\d{2}-\d{2})\s*$", threat_text)
        if not threat_date:
            errors.append("threat model must record Last Updated")
        else:
            try:
                updated = datetime.strptime(threat_date.group(1), "%Y-%m-%d").date()
                if date_is_stale(updated):
                    errors.append("threat model review is stale or in the future")
            except ValueError:
                errors.append("threat model Last Updated is invalid")
    config_path = root / ".security" / "config.json"
    try:
        config_path = ensure_inside_root(root, config_path, "security configuration")
    except RepoctlError as error:
        errors.append(str(error))
        config_path = Path("/nonexistent")
    if not config_path.is_file():
        errors.append("public launch requires .security/config.json")
    else:
        try:
            security_config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(security_config, dict):
                errors.append("public security configuration must be a JSON object")
            else:
                contacts = security_config.get("security_team_contacts", [])
                if not isinstance(contacts, list) or not contacts or not all(
                    isinstance(item, str) and valid_private_route(item) for item in contacts
                ):
                    errors.append("public launch requires valid security_team_contacts")
                elif isinstance(contact, str) and contact not in contacts:
                    errors.append("security_team_contacts must include security.contact")
                reviewed_on = security_config.get("security_reviewed_on")
                reviewer = security_config.get("security_reviewer")
                if not isinstance(reviewed_on, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed_on):
                    errors.append("public security configuration needs security_reviewed_on")
                else:
                    try:
                        reviewed_date = datetime.strptime(reviewed_on, "%Y-%m-%d").date()
                        if date_is_stale(reviewed_date):
                            errors.append("security review date is stale or in the future")
                    except ValueError:
                        errors.append("security_reviewed_on is invalid")
                if not isinstance(reviewer, str) or is_placeholder(reviewer) or re.search(r"[\[\]]", reviewer) or len(reviewer.strip()) < 3:
                    errors.append("public security configuration needs a named security_reviewer")
        except (OSError, json.JSONDecodeError):
            errors.append("public security configuration is unreadable")
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
                root,
                legal_ref,
                "legal review evidence",
                (r"^Counsel review:\s*approved\s*$", r"^Reviewer:\s*\S+", r"^Date:\s*\d{4}-\d{2}-\d{2}"),
                str(project.get("name")),
            )
            if error:
                errors.append(error)
        if launch.get("production_evidence") != "verified":
            errors.append("public launch requires verified production evidence")
        refs = launch.get("production_evidence_refs", [])
        if not isinstance(refs, list) or not refs or not all(
            isinstance(ref, str) and ref.strip() for ref in refs
        ):
            errors.append("public launch requires repository production evidence paths")
        else:
            for ref in refs:
                _, error = read_evidence_file(
                    root,
                    ref,
                    "production evidence",
                    (r"^Evidence type:\s*deployed\s*$", r"^Deployment:\s*\S+", r"^Observed:\s*(?!no\b|not\b|none\b)\S+", r"^Reviewer:\s*\S+", r"^Date:\s*\d{4}-\d{2}-\d{2}"),
                    str(project.get("name")),
                )
                if error:
                    errors.append(error)
    legal_paths = launch.get("legal_document_paths", []) if isinstance(launch, dict) else []
    if not isinstance(legal_paths, list) or not legal_paths:
        errors.append("public launch requires an explicit legal_document_paths list")
    else:
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
                root,
                normalized_legal,
                "public legal document",
                (r"^Legal owner:\s*\S+", r"^Reviewer:\s*\S+", r"^Date:\s*\d{4}-\d{2}-\d{2}"),
                str(project.get("name")),
            )
            if error:
                errors.append(error)
    inventory = root / "docs" / "legal" / "data-inventory.md"
    try:
        inventory = ensure_inside_root(root, inventory, "data inventory")
        inventory_content = inventory.read_text(encoding="utf-8")
    except (RepoctlError, OSError, UnicodeDecodeError) as error:
        errors.append("public launch requires a readable docs/legal/data-inventory.md")
    else:
        if not inventory_content.strip() or re.search(r"\[(?:REQUIRED|pending|TBD)|REPLACE_WITH|UNSELECTED", inventory_content, re.I):
            errors.append("public data inventory must be complete and placeholder-free")
        if not re.search(rf"(?im)^Project:\s*{re.escape(str(project.get('name', '')))}\s*$", inventory_content):
            errors.append("public data inventory is not bound to project.toml")
        inventory_date = re.search(r"(?im)^Date:\s*(\d{4}-\d{2}-\d{2})\s*$", inventory_content)
        if not inventory_date:
            errors.append("public data inventory must record its review date")
        else:
            try:
                if date_is_stale(datetime.strptime(inventory_date.group(1), "%Y-%m-%d").date()):
                    errors.append("public data inventory review is stale or future-dated")
            except ValueError:
                errors.append("public data inventory review date is invalid")
        reviewer = re.search(r"(?im)^Reviewer:\s*(.+?)\s*$", inventory_content)
        if not reviewer or is_placeholder(reviewer.group(1)):
            errors.append("public data inventory must name a real reviewer")
        if not re.search(r"(?i)retention", inventory_content) or not re.search(r"(?i)rights|deletion|export", inventory_content):
            errors.append("public data inventory must cover retention and rights/deletion evidence")
    if not github_target_configured(root, project):
        errors.append("public launch requires a configured GitHub issue register (repository.github or origin)")
    return errors


def check_readiness(root: Path) -> None:
    project = load_project(root)
    errors: list[str] = []
    try:
        profile = governance_profile(project)
    except RepoctlError as error:
        profile = "agent-first"
        errors.append(str(error))

    try:
        check_vision(root, project)
    except RepoctlError as error:
        errors.append(str(error))
    for check in (check_structure, check_docs_index, check_markdown_links, check_file_hygiene):
        try:
            check(root) if check is not check_structure else check(root, project)
        except RepoctlError as error:
            errors.append(str(error))
    try:
        check_skill_provenance(project)
        check_readme_identity(root, project)
    except RepoctlError as error:
        errors.append(str(error))

    if project.get("name") == "REPLACE_WITH_PROJECT_NAME":
        errors.append("project name is not initialized")
    if not isinstance(project.get("kind"), str) or not PROJECT_KIND_PATTERN.fullmatch(project["kind"]):
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
        errors.append("at least one accountable owner is required")

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
                validate_critic_evidence(root, surface)
            except RepoctlError as error:
                errors.append(str(error))
    if project.get("phase") in {"private-preview", "public-launch"}:
        errors.extend(review_status(root))  # one fresh, passing UI review before anyone outside uses it

    launch = project.get("launch", {})
    if not isinstance(launch, dict):
        errors.append("launch must be a table")
    elif project.get("phase") == "public-launch":
        errors.extend(check_public_launch_evidence(root, project))

    if errors:
        raise RepoctlError("readiness check failed:\n- " + "\n- ".join(errors))
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
