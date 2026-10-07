"""Shared, deliberately conservative issue-disclosure classification."""

from __future__ import annotations

import re

# This is a secondary blocklist, not proof that a body is safe. The structured
# disclosure class and human/private review remain the authorization boundary.
SENSITIVE_ISSUE_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"unpatched|vulnerability|exploit|credential|secret|personal data|"
    r"privacy incident|rce|remote code execution|auth(?:entication)? bypass|"
    r"idor|sqli|sql injection|cross-tenant|privilege escalation|"
    r"exfiltration|data breach|malware|phishing|active security finding|"
    r"ssrf|server-side request forgery|path traversal|directory traversal|"
    r"xxe|xml external entity|command injection|authorization bypass"
    r")\b"
)

DISCLOSURE_CLASS_PATTERN = re.compile(
    r"(?im)^\s*(?:-\s*)?(?:\*\*)?Disclosure class:"
    r"(?:\*\*)?\s*(ordinary|public-reviewed|private-route)\s*$"
)


# The one definition of the issue contract. `make issue` (tools/kit/issues.py), the
# CI issue check, and the PR reference check (tools/kit/ci.py) all read these;
# docs/ISSUE_TEMPLATE.md and .github/ISSUE_TEMPLATE/*.yml are held to them by a test.
HEADINGS = {
    "regulated": (
        "Summary", "What happens", "Where", "When", "Why", "How to reproduce", "Impact and scope",
        "Acceptance criteria", "Evidence", "Disclosure classification", "Dependencies and handoff",
    ),
    "agent-first": ("Summary", "Acceptance criteria", "Evidence", "Disclosure classification", "Dependencies and handoff"),
}
# Sections checked for concrete content; Summary and Acceptance criteria have their own rules.
OWN_RULE_HEADINGS = ("Summary", "Acceptance criteria")

DUPLICATE_CHECK = re.compile(
    r"(?im)^Duplicate check:\s*searched\s+title,\s*symptom,\s*and\s+path\s+for\s+.+;\s*(?:reused\s+#[0-9]+|no duplicate found)\s*$"
)
PUBLIC_SAFE = {
    "regulated": re.compile(r"(?im)^\s*(?:-\s*)?(?:\*\*)?Public-safe:(?:\*\*)?\s*yes\s*$"),
    "agent-first": re.compile(r"(?im)^\s*(?:-\s*)?(?:\*\*)?Public-safe:(?:\*\*)?\s*yes\b"),
}
PRIVACY_REVIEW = re.compile(r"(?im)^\s*(?:-\s*)?(?:\*\*)?Security/privacy review:(?:\*\*)?\s*(.+?)\s*$")
OWNER_LINE = {
    "regulated": re.compile(r"(?im)^\s*(?:-\s*)?(?:\*\*)?Owner / next action:(?:\*\*)?\s*\S+"),
    "agent-first": re.compile(r"(?im)^\s*(?:-\s*)?(?:\*\*)?(?:Owner / next action|Owner):(?:\*\*)?\s*\S+"),
}
# Label values the public adapters refuse (sensitive findings use SECURITY.md).
REFUSED_PUBLIC = {"type": ("security",)}
REQUIRED_FAMILIES = ("type", "priority", "area", "topic", "status")
TOPIC = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def profile_key(profile: str) -> str:
    """Only `regulated` is strict; every other profile that reaches validation uses the compact contract."""
    return "regulated" if profile == "regulated" else "agent-first"


def required_headings(profile: str) -> tuple[str, ...]:
    return HEADINGS[profile_key(profile)]


def content_headings(profile: str) -> tuple[str, ...]:
    return tuple(h for h in required_headings(profile) if h not in OWN_RULE_HEADINGS)


def disclosure_class(markdown: str) -> str | None:
    match = DISCLOSURE_CLASS_PATTERN.search(markdown)
    return match.group(1).lower() if match else None


def sensitive_issue_content(value: str) -> bool:
    return bool(SENSITIVE_ISSUE_PATTERN.search(value))
