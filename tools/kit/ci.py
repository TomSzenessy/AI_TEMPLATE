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
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable

from .github import _gh, load_label_registry
from .config import project_setting
from .core import RepoctlError, load_project, markdown_without_fenced_code, reject_secret_text
from .core import today as core_today
from .issues import contract, issue_problems, parse_sections

CANONICAL = contract.HEADINGS  # the contract owns the headings; the name stays for callers
REQUIRED_FAMILIES = contract.REQUIRED_FAMILIES
TOPIC = contract.TOPIC


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
        if not all(h in parse_sections(issue_body) for h in contract.required_headings(profile)):
            raise RepoctlError(f"#{number} does not contain the expected canonical issue contract")
        if not contract.DUPLICATE_CHECK.search(markdown_without_fenced_code(issue_body)):
            raise RepoctlError(f"#{number} is missing the duplicate-search record")
    if not closing_references:
        return "Private review attested"
    return "Validated open issue contracts: " + ", ".join("#" + n for n in closing_references)


def github_issue_fetcher(repository: str, api_root: str, token: str) -> Callable[[str], dict]:
    def fetch(number: str) -> dict:
        request = urllib.request.Request(
            f"{api_root.rstrip('/')}/repos/{repository}/issues/{number}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RepoctlError(f"could not fetch issue #{number} from {repository}: {error}") from error

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


def issue_contract_check(
    text: str, labels: set[str], profile: str, registry: dict, today: date | None = None
) -> tuple[bool, list[str], list[str]]:
    """Return (valid, labels_to_add, reasons) for a natively filed issue body; reasons name each fix."""
    today = today or core_today()
    if profile == "minimal":
        raise RepoctlError("Minimal profile delegates issue intake to the host organization; remove native forms")
    if profile == "regulated":
        raise RepoctlError("Regulated profile uses the CLI/private issue route; remove native forms")
    structural = markdown_without_fenced_code(text)
    status_values = [label.split(":", 1)[1] for label in labels if label.startswith("status:")]
    status = status_values[0] if len(status_values) == 1 else "triage"
    reject_secret_text(text, "issue body")
    reasons: list[str] = issue_problems(text, profile, status)

    label_values: dict[str, str] = {}
    for label in labels:
        if ":" not in label:
            continue
        family, value = label.split(":", 1)
        if family in REQUIRED_FAMILIES:
            if family in label_values:
                reasons.append(f"more than one {family}: label")
            label_values[family] = value
        allowed = registry.get(family)
        if family == "topic" and not TOPIC.fullmatch(value):
            reasons.append(f"topic label must be kebab-case: {value}")
        elif family in REQUIRED_FAMILIES and family != "topic" and (not isinstance(allowed, list) or value not in allowed):
            reasons.append(f"unknown {family} label: {value} (see .github/issue-labels.json)")
    field_values: dict[str, str] = {}
    for field in ("Type", "Priority", "Area", "Topic", "Status"):
        match = re.search(rf"(?im)^### {field}\s*$\n\s*([^\n]+)", structural)
        if match:
            field_values[field.lower()] = match.group(1).strip().strip("`")
    if field_values:
        if set(field_values) != set(REQUIRED_FAMILIES):
            reasons.append("fill every form field: Type, Priority, Area, Topic, Status")
        for family, value in field_values.items():
            allowed = registry.get(family)
            if family == "topic":
                if not TOPIC.fullmatch(value):
                    reasons.append(f"Topic must be kebab-case: {value}")
            elif not isinstance(allowed, list) or value not in allowed:
                reasons.append(f"unknown {family}: {value} (see .github/issue-labels.json)")
            if family in label_values and label_values[family] != value:
                reasons.append(f"{family} field ({value}) conflicts with its label ({label_values[family]})")
    elif set(label_values) != set(REQUIRED_FAMILIES):
        reasons.append("needs one label (or form field) each for type, priority, area, topic, and status")
    if set(contract.REFUSED_PUBLIC["type"]) & {label_values.get("type"), field_values.get("type")}:
        reasons.append("security issues use the private route in SECURITY.md")
    labels_to_add = [f"{family}:{value}" for family, value in field_values.items()]
    for desired in labels_to_add:
        family, value = desired.split(":", 1)
        if {label for label in labels if label.startswith(family + ":") and label != desired}:
            reasons.append(f"conflicting {family}: labels")
    labels_to_add = [label for label in labels_to_add if label not in labels]
    reasons = list(dict.fromkeys(reasons))
    return not reasons, labels_to_add, reasons


INCOMPLETE = (
    "Issue contract incomplete. Use docs/ISSUE_TEMPLATE.md, include every canonical heading, and complete the "
    "public disclosure review. Active vulnerabilities, secrets, and personal data belong in the private security route."
)


CONTRACT_MARKER = "<!-- issue-contract -->"


def strip_mentions(value: str) -> str:
    """Echoed issue text must not ping anyone: drop the @ of every mention."""
    return re.sub(r"@(?=[\w-])", "", value)


def post_contract_comment(repository: str, number: str, comment: str) -> None:
    """Keep exactly one marker comment per issue: edit it if present, else create it."""
    body = f"{CONTRACT_MARKER}\n{comment}"
    found = _gh(
        None,
        [
            "api", f"repos/{repository}/issues/{number}/comments", "--paginate",
            "--jq", f'.[] | select(.body | contains("{CONTRACT_MARKER}")) | .id',
        ],
    ).split()
    if found:
        _gh(None, ["api", "-X", "PATCH", f"repos/{repository}/issues/comments/{found[0]}", "-f", f"body={body}"])
    else:
        _gh(None, ["api", "-X", "POST", f"repos/{repository}/issues/{number}/comments", "-f", f"body={body}"])


def run_issue_contract(root: Path) -> str:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = event.get("issue", {})
    registry = load_label_registry(root)
    valid, labels_to_add, reasons = issue_contract_check(
        issue.get("body") or "", {label.get("name", "") for label in issue.get("labels", [])}, profile_of(root), registry
    )
    number, repository = os.environ["ISSUE_NUMBER"], os.environ["GH_REPOSITORY"]
    if not valid:
        comment = INCOMPLETE + "\n\nTo fix:\n" + "\n".join(f"- {strip_mentions(reason)}" for reason in reasons)
        post_contract_comment(repository, number, comment)
        raise RepoctlError("Issue contract validation failed")
    if labels_to_add:
        subprocess.run(
            ["gh", "issue", "edit", number, "--repo", repository, *sum((["--add-label", label] for label in labels_to_add), [])],
            check=True,
        )
    return "Canonical issue contract passed"


# --- the verification gate ---------------------------------------------------------


def gate_command(root: Path, python: str) -> list[str]:
    """The command the `kit-ci` verify job runs, pinned to the interpreter that runs it.

    An adopted project's surfaces need toolchains this workflow never installs (Node, Go, ...), so
    kit CI there runs only the toolchain-free gate, `repoctl check`; the surfaces' own tests belong
    to the project's CI. The template itself (and `make init` projects) keep the full `make verify`.
    """
    if project_setting(load_project(root), "project_mode") == "adopt":
        return [python, str(Path(__file__).resolve().parents[1] / "repoctl.py"), "--root", str(root), "check"]
    return ["make", "--no-print-directory", f"PYTHON={python}", "verify"]


def run_gate(root: Path) -> str:
    python = sys.executable
    command = gate_command(root, python)
    print(f"kit-ci gate on Python {sys.version.split()[0]}: {' '.join(command)}", flush=True)
    done = subprocess.run(command, cwd=root)
    if done.returncode:
        raise RepoctlError(f"the verification gate failed (exit {done.returncode})")
    return "Verification gate passed"
