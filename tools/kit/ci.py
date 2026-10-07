"""CI checks as tested repository code, so CI runs what agents can run locally.

Workflows only check out the repository and call `repoctl ci <check>`; the
logic lives here as pure functions (unit-tested) plus thin GitHub adapters.
Logic hidden in workflow YAML is untestable until the first pull request, so
`make check` rejects long inline `run:` blocks (see hygiene.workflow_errors).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .core import RepoctlError, load_project, reject_secret_text
from .issues import validate_issue_body, validate_issue_content, validate_issue_state

try:
    from issue_contract import disclosure_class, sensitive_issue_content
except ImportError:  # pragma: no cover - module import from a package context
    from tools.issue_contract import disclosure_class, sensitive_issue_content

CANONICAL = {
    "regulated": [
        "Summary", "What happens", "Where", "When", "Why", "How to reproduce", "Impact and scope",
        "Acceptance criteria", "Evidence", "Disclosure classification", "Dependencies and handoff",
    ],
    "agent-first": ["Summary", "Acceptance criteria", "Evidence", "Disclosure classification", "Dependencies and handoff"],
}
REQUIRED_FAMILIES = ("type", "priority", "area", "topic", "status")
TOPIC = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def profile_of(root: Path) -> str:
    governance = load_project(root).get("governance", {})
    if not isinstance(governance, dict):
        raise RepoctlError("governance must be a table")
    profile = governance.get("profile", "agent-first")
    if profile not in {"agent-first", "regulated", "minimal"}:
        raise RepoctlError("invalid governance.profile")
    return profile


# --- pull request: linked issue contract -----------------------------------------


def pr_reference_check(
    body: str,
    labels: set[str],
    author_association: str,
    profile: str,
    fetch_issue: Callable[[str], dict],
) -> str:
    """Validate a PR's linked issues; return a success message or raise RepoctlError."""
    if profile == "minimal":
        return "Minimal profile delegates issue/reference validation to the host organization"
    closing_references = sorted(set(re.findall(r"\b(?:Closes|Fixes)\s+#([1-9][0-9]*)\b", body, re.I)))
    private_reference = re.search(
        r"(?im)^\s*Security-Reference:\s*(?:GHSA-[0-9a-z-]{4,}|https://github\.com/[^\s]+/security/advisories/[^\s]+)\s*$",
        body,
    )
    attested = bool(re.search(r"(?im)^\s*Security-Review:\s*maintainer-attested\s*$", body))
    owner = re.search(r"(?im)^\s*Security-Owner:\s*@?[A-Za-z0-9][A-Za-z0-9-]{1,39}\s*$", body)
    trusted = author_association in {"OWNER", "MEMBER", "COLLABORATOR"}
    private_gate = bool(attested and owner and "security-reviewed" in labels and trusted)
    if private_reference and not private_gate:
        raise RepoctlError(
            "Private security PRs require a maintainer-applied security-reviewed label, Security-Owner, and trusted author association"
        )
    if "security-reviewed" in labels and not private_gate:
        raise RepoctlError("The security-reviewed label requires the trusted private-review attestation")
    if not private_gate and not closing_references:
        raise RepoctlError("PR body must include Closes/Fixes #<number> or the trusted private-review attestation")
    for number in closing_references:
        issue = fetch_issue(number)
        if "pull_request" in issue:
            raise RepoctlError(f"#{number} is a pull request, not an issue")
        if issue.get("state") != "open":
            raise RepoctlError(f"#{number} must be an open issue")
        issue_body = issue.get("body") or ""
        if not all(re.search(rf"(?m)^### {re.escape(h)}\s*$", issue_body) for h in CANONICAL[profile]):
            raise RepoctlError(f"#{number} does not contain the expected canonical issue contract")
        if not re.search(r"(?im)^Duplicate check:\s*searched\s+title,\s*symptom,\s+and\s+path\s+for\s+.+;", issue_body):
            raise RepoctlError(f"#{number} is missing the duplicate-search record")
    return "Validated open issue contracts: " + ", ".join("#" + n for n in closing_references) if closing_references else "Private review attested"


def github_issue_fetcher(repository: str, api_root: str, token: str) -> Callable[[str], dict]:
    def fetch(number: str) -> dict:
        request = urllib.request.Request(
            f"{api_root.rstrip('/')}/repos/{repository}/issues/{number}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)

    return fetch


def run_pr_reference(root: Path) -> str:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pull = event.get("pull_request", {})
    return pr_reference_check(
        pull.get("body") or "",
        {label.get("name", "") for label in pull.get("labels", [])},
        os.environ.get("PR_AUTHOR_ASSOCIATION", ""),
        profile_of(root),
        github_issue_fetcher(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_API_URL"], os.environ["GH_TOKEN"]),
    )


# --- issues: native form intake contract -----------------------------------------


def issue_contract_check(text: str, labels: set[str], profile: str, registry: dict, today: date | None = None) -> tuple[bool, list[str]]:
    """Return (valid, labels_to_add) for a natively filed issue body."""
    today = today or date.today()
    if profile == "minimal":
        raise RepoctlError("Minimal profile delegates issue intake to the host organization; remove native forms")
    if profile == "regulated":
        raise RepoctlError("Regulated profile uses the CLI/private issue route; remove native forms")
    structural = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    status_values = [label.split(":", 1)[1] for label in labels if label.startswith("status:")]
    status = status_values[0] if len(status_values) == 1 else "triage"
    reject_secret_text(text, "issue body")
    validate_issue_body(text, profile)
    validate_issue_content(text, status, profile)
    validate_issue_state(text, status, profile)

    missing = [h for h in CANONICAL[profile] if not re.search(rf"^### {re.escape(h)}$", structural, re.MULTILINE)]
    public_safe = bool(re.search(r"(?im)^\s*(?:-\s*)?(?:\*\*)?Public-safe:(?:\*\*)?\s*yes\b", structural))
    duplicate = bool(re.search(
        r"(?im)^Duplicate check:\s*searched\s+title,\s*symptom,\s*and\s+path\s+for\s+.+;\s*(?:reused\s+#[0-9]+|no duplicate found)\s*$",
        structural,
    ))
    reviewer = re.search(r"(?im)^\s*(?:-\s*)?(?:\*\*)?Reviewer/date:(?:\*\*)?\s*(.+?)\s*$", structural)
    invalid = bool(missing) or not public_safe or not duplicate or disclosure_class(structural) not in {"ordinary", "public-reviewed"}

    label_values: dict[str, str] = {}
    for label in labels:
        if ":" not in label:
            continue
        family, value = label.split(":", 1)
        if family in REQUIRED_FAMILIES:
            invalid |= family in label_values
            label_values[family] = value
        allowed = registry.get(family)
        if family == "topic":
            invalid |= not TOPIC.fullmatch(value)  # open kebab-case vocabulary
        elif family in REQUIRED_FAMILIES and (not isinstance(allowed, list) or value not in allowed):
            invalid = True
    field_values: dict[str, str] = {}
    for field in ("Type", "Priority", "Area", "Topic", "Status"):
        match = re.search(rf"(?im)^### {field}\s*$\n\s*([^\n]+)", structural)
        if match:
            field_values[field.lower()] = match.group(1).strip().strip("`")
    if field_values:
        invalid |= set(field_values) != set(REQUIRED_FAMILIES)
        for family, value in field_values.items():
            allowed = registry.get(family)
            if family == "topic":
                invalid |= not TOPIC.fullmatch(value)
            elif not isinstance(allowed, list) or value not in allowed:
                invalid = True
            invalid |= family in label_values and label_values[family] != value
    elif set(label_values) != set(REQUIRED_FAMILIES):
        invalid = True
    invalid |= "security" in {label_values.get("type"), field_values.get("type")}
    labels_to_add = [f"{family}:{value}" for family, value in field_values.items()]
    for desired in labels_to_add:
        family, value = desired.split(":", 1)
        conflicting = {label for label in labels if label.startswith(family + ":") and label != desired}
        invalid |= bool(conflicting) or label_values.get(family, value) != value
    labels_to_add = [label for label in labels_to_add if label not in labels]
    invalid |= bool(sensitive_issue_content(structural))
    if reviewer is None or re.search(r"\[|required|tbd|never|pending", reviewer.group(1), re.I):
        invalid = True
    else:
        name = re.split(r"\s+\d{4}-\d{2}-\d{2}\b", reviewer.group(1).strip(), maxsplit=1)[0].strip(" *_`")
        invalid |= len(name) < 3 or name.lower() in {"x", "none", "n/a", "pending", "tbd"}
        reviewed = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", reviewer.group(1))
        try:
            reviewed_on = date.fromisoformat(reviewed.group(1)) if reviewed else None
        except ValueError:
            reviewed_on = None
        invalid |= reviewed_on is None or reviewed_on > today or reviewed_on < today - timedelta(days=365)
    return not invalid, labels_to_add


INCOMPLETE = (
    "Issue contract incomplete. Use docs/ISSUE_TEMPLATE.md, include every canonical heading, and complete the "
    "public disclosure review. Active vulnerabilities, secrets, and personal data belong in the private security route."
)


def run_issue_contract(root: Path) -> str:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = event.get("issue", {})
    governance = load_project(root).get("governance", {})
    registry_value = governance.get("label_registry", ".github/issue-labels.json") if isinstance(governance, dict) else ".github/issue-labels.json"
    registry_path = Path(registry_value)
    if registry_path.is_absolute() or ".." in registry_path.parts:
        raise RepoctlError("governance.label_registry must stay inside the repository")
    registry = json.loads((root / registry_path).read_text(encoding="utf-8"))
    valid, labels_to_add = issue_contract_check(
        issue.get("body") or "", {label.get("name", "") for label in issue.get("labels", [])}, profile_of(root), registry
    )
    number, repository = os.environ["ISSUE_NUMBER"], os.environ["GH_REPOSITORY"]
    if not valid:
        subprocess.run(["gh", "issue", "comment", number, "--repo", repository, "--body", INCOMPLETE], check=True)
        raise RepoctlError("Issue contract validation failed")
    if labels_to_add:
        subprocess.run(
            ["gh", "issue", "edit", number, "--repo", repository, *sum((["--add-label", label] for label in labels_to_add), [])],
            check=True,
        )
    return "Canonical issue contract passed"
