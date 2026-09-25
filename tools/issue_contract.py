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


def disclosure_class(markdown: str) -> str | None:
    match = DISCLOSURE_CLASS_PATTERN.search(markdown)
    return match.group(1).lower() if match else None


def sensitive_issue_content(value: str) -> bool:
    return bool(SENSITIVE_ISSUE_PATTERN.search(value))
