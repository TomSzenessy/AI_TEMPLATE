"""Structural signal: which areas of a repository keep changing together (issue #24).

A wrong seam shows up in history before it shows up in review: two areas that
should be independent keep landing in the same commit. This reads recent
`git log --name-only`, maps every changed file to the directory that owns it, and
reports the pairs that co-change most, so a bad seam is visible before it
spreads (docs/audit.md).

It is advisory and always will be. Coupling is a judgement, not a rule: the same
pair means "these belong together" in one repository and "this seam is wrong" in
another, and a project adapts this kit forever with no upgrade path. So the
signal is reported by `make garden` and never gates `make check`.

Cost is one `git log` over a bounded window plus a pair count, which is the same
order as the stale-document history the blocking checks already read.
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

from .gitinfo import git, has_history

COMMITS = 300  # bounded window: enough signal, and the cost does not grow with repository age
AREA_DEPTH = 2  # `tools/kit`, `.agents/skills`, `docs`; a root file is its own area
MIN_SHARED = 3  # a pair seen twice is a coincidence, not a seam
MAX_AREAS = 12  # a commit touching more trees is a sweep, not a coupling signal
RECORD = "%x1e"  # git's printf escape, not a raw control character in argv


def area(path: str) -> str:
    """The directory that owns a file; a root file is its own area."""
    parts = path.split("/")
    return "/".join(parts[:-1] if len(parts) <= AREA_DEPTH else parts[:AREA_DEPTH]) or path


def commit_areas(root: Path, limit: int = COMMITS) -> list[set[str]]:
    """The areas each recent non-merge commit touched, newest first, bounded window."""
    output = git(root, "log", f"-n{limit}", "--no-merges", "--name-only", f"--format={RECORD}", timeout=30)
    if output is None:
        return []
    commits = []
    for record in output.split("\x1e"):
        areas = {area(line) for line in record.splitlines() if line.strip()}
        if areas and len(areas) <= MAX_AREAS:
            commits.append(areas)
    return commits


def co_change(commits: list[set[str]]) -> dict[tuple[str, str], int]:
    """(area pair) -> commits that touched both."""
    shared: dict[tuple[str, str], int] = {}
    for areas in commits:
        for pair in combinations(sorted(areas), 2):
            shared[pair] = shared.get(pair, 0) + 1
    return shared


def coupling_findings(root: Path, limit: int = COMMITS, top: int = 5) -> list[str]:
    """The area pairs that co-change most, each naming the judgement to make."""
    if not has_history(root):
        return []  # shallow_history already reports a repository without usable history
    commits = commit_areas(root, limit)
    shared = co_change(commits)
    ranked = sorted(((count, pair) for pair, count in shared.items() if count >= MIN_SHARED), reverse=True)
    findings = []
    for count, (left, right) in ranked[:top]:
        findings.append(
            f"{left} + {right}: co-change in {count} of the last {len(commits)} commits; if these areas should be "
            "independent, one seam is missing (bind both to one owner document, or split the module)"
        )
    return findings