"""Pinned upstream records on resources.toml entries (issue #131).

An entry that sets `repo` + `revision` names the exact upstream commit it was reviewed at, optionally the local
owners it shaped (`adapted_into`) and single upstream files fetched on demand (`files`, each with a `when` trigger).
Listing and URL printing are offline. Only `check_lines` touches the network (`git ls-remote`, read-only, on explicit
request, runner injectable for tests). Nothing here files an issue anywhere.
"""

from __future__ import annotations

import re
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Callable

from .core import RepoctlError, parse_iso_date, today

SHA = re.compile(r"[0-9a-f]{40}")
NOTICES = "THIRD_PARTY_NOTICES.md"
NOTICE_SECTION = "## Workflow material distilled"
NOTICE_ROW = re.compile(r"\[[^\]]+\]\(https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\)\s*`([0-9a-f]{7})`")
Runner = Callable[[str], "str | None"]  # repo -> remote HEAD sha, or None when unreachable


def raw_url(entry: dict, path: str) -> str:
    return f"https://raw.githubusercontent.com/{entry['repo']}/{entry['revision']}/{path}"


def records(root: Path) -> list[dict]:
    from .skills import load_resource_registry
    from .core import load_project
    return [e for e in load_resource_registry(root, load_project(root)) if "repo" in e]


def _pick(root: Path, identifier: str | None) -> list[dict]:
    found = records(root)
    if identifier is None:
        return found
    chosen = [e for e in found if e["id"] == identifier]
    if not chosen:
        raise RepoctlError(f"no upstream record with id {identifier!r}; `make upstream` lists them")
    return chosen


def list_lines(root: Path, identifier: str | None = None) -> list[str]:
    """Offline. No id: one summary per record. With an id: each file's trigger and pinned raw URL."""
    chosen = _pick(root, identifier)
    if identifier is None:
        return [f"{e['id']}  {e['repo']}@{e['revision'][:7]}  {e.get('license')}  reviewed {e.get('reviewed_on')}  "
                f"adapted_into={len(e.get('adapted_into', []))}  files={len(e.get('files', []))}" for e in chosen] \
            or ["no upstream records in resources.toml"]
    entry = chosen[0]
    lines = [f"{entry['id']}: {entry['repo']}@{entry['revision']}"]
    lines += [f"  when {f['when']}: {raw_url(entry, f['path'])}" for f in entry.get("files", [])]
    return lines if len(lines) > 1 else lines + ["  (no files listed)"]


def ls_remote(repo: str) -> str | None:
    """Remote HEAD sha via `git ls-remote`; None when git, the network or the repo is unavailable."""
    try:
        result = subprocess.run(["git", "ls-remote", f"https://github.com/{repo}", "HEAD"], capture_output=True,
                                text=True, timeout=20, check=False, env={"GIT_TERMINAL_PROMPT": "0", "PATH": _path()})
    except (OSError, subprocess.TimeoutExpired):
        return None
    head = result.stdout.split()
    return head[0] if result.returncode == 0 and head and SHA.fullmatch(head[0]) else None


def _path() -> str:
    import os
    return os.environ.get("PATH", "")


def check_lines(root: Path, identifier: str | None = None, runner: Runner = ls_remote) -> list[str]:
    """Network only here, on explicit request. Advisory: reports state, never fails."""
    lines = []
    for entry in _pick(root, identifier):
        remote = runner(entry["repo"])
        if remote is None:
            lines.append(f"{entry['id']}: unreachable ({entry['repo']})")
        elif remote == entry["revision"]:
            lines.append(f"{entry['id']}: current ({entry['repo']}@{remote[:7]})")
        else:
            owners = ", ".join(entry.get("adapted_into", [])) or "none recorded"
            lines.append(f"{entry['id']}: behind (remote {remote[:7]}, pinned {entry['revision'][:7]}); "
                         f"review the changes, then revisit: {owners}")
    return lines or ["no upstream records in resources.toml"]


def review_age_findings(root: Path, days: int) -> list[str]:
    """Offline garden advisory: upstream records reviewed longer ago than the skill review window."""
    findings = []
    try:
        found = records(root)
    except RepoctlError:
        return []
    for entry in found:
        reviewed = parse_iso_date(str(entry.get("reviewed_on", "")))
        if reviewed is not None and reviewed < today() - timedelta(days=days):
            findings.append(f"upstream review older than {days} days: {entry['id']} (reviewed {entry['reviewed_on']}); "
                            f"re-review with `make upstream CHECK=1 ID={entry['id']}`")
    return findings


def notice_findings(root: Path) -> list[str]:
    """Every adapted source in THIRD_PARTY_NOTICES.md needs a record with the same repo and short revision."""
    path = root / NOTICES
    if not path.is_file():
        return []
    rows, inside = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.startswith(NOTICE_SECTION)
        elif inside and (match := NOTICE_ROW.search(line)):
            rows.append(match.groups())
    try:
        have = {(e["repo"].lower(), e["revision"][:7]) for e in records(root)}
    except RepoctlError:
        return []
    return [f"{NOTICES} lists {repo}@{short} with no matching upstream record in resources.toml: add repo/revision/"
            "license/reviewed_on to its entry (docs/resources.md#upstream-records)"
            for repo, short in rows if (repo.lower(), short) not in have]
