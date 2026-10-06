"""Rot detectors: expiring deprecations, orphan task markers, and context budgets.

Markers are language-neutral comments, so they work in any stack:

- `DEPRECATED(remove-by=YYYY-MM-DD, owner=..., use=...)` fails once the date passes.
- A language `@deprecated`/`@Deprecated` annotation needs a `remove-by=` date
  on the same line or within the next three lines.
- A task marker (to-do, fix-me, hack, triple-x) must reference an issue
  (`#123`, a URL, or `Local-WAL`) so open work lives in the issue register.

Budgets bound files that agents load often, in bytes (~4 bytes per token).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .core import RepoctlError, read_text_file
from .gitinfo import path_matches

# Character classes keep these patterns from matching their own source text.
DEPRECATION = re.compile(r"DEPRECATED\(remove-by=(\d{4}-\d{2}-\d{2})([^)]*)\)")
ANNOTATION = re.compile(r"@[Dd]eprecated\b")
TASK = re.compile(r"\b(T[O]DO|F[I]XME|H[A]CK|X[X]X)\b")
TASK_REFERENCE = re.compile(r"#\d+|https?://|Local-WAL")
PROSE_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".lock", ".svg"}
UPCOMING_DAYS = 30


@dataclass
class MarkerReport:
    expired: list[str] = field(default_factory=list)
    upcoming: list[str] = field(default_factory=list)
    undated: list[str] = field(default_factory=list)
    orphan_tasks: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        return (
            [f"expired deprecation: {item}" for item in self.expired]
            + [f"deprecation annotation without remove-by date: {item}" for item in self.undated]
            + [f"task marker without issue reference: {item}" for item in self.orphan_tasks]
        )


def scan_markers(root: Path, files: list[str], today: date | None = None) -> MarkerReport:
    today = today or date.today()
    report = MarkerReport()
    for relative in files:
        suffix = Path(relative).suffix.lower()
        text = read_text_file(root, relative)
        if text is None:
            continue
        lines = text.splitlines()
        for number, line in enumerate(lines, start=1):
            location = f"{relative}:{number}"
            for match in DEPRECATION.finditer(line):
                try:
                    deadline = date.fromisoformat(match.group(1))
                except ValueError:
                    report.undated.append(f"{location} (invalid date {match.group(1)})")
                    continue
                if deadline < today:
                    report.expired.append(f"{location} (remove-by {deadline})")
                elif deadline <= today + timedelta(days=UPCOMING_DAYS):
                    report.upcoming.append(f"{location} (remove-by {deadline})")
            if suffix in PROSE_SUFFIXES:
                continue
            if ANNOTATION.search(line) and not any(
                "remove-by=" in candidate for candidate in lines[number - 1 : number + 3]
            ):
                report.undated.append(location)
            if TASK.search(line) and not TASK_REFERENCE.search(line):
                report.orphan_tasks.append(location)
    return report


def budget_errors(root: Path, project: dict[str, object], files: list[str]) -> list[str]:
    budgets = project.get("budgets", {})
    if not isinstance(budgets, dict):
        raise RepoctlError("budgets must be a table of glob = max_bytes")
    errors = []
    for pattern, limit in budgets.items():
        if not isinstance(limit, int) or limit <= 0:
            errors.append(f"budget for {pattern} must be a positive integer byte count")
            continue
        for relative in files:
            if not path_matches(relative, pattern):
                continue
            size = (root / relative).stat().st_size
            if size > limit:
                errors.append(
                    f"{relative} is {size} bytes (~{size // 4} tokens), over its {limit}-byte budget ({pattern});"
                    " move detail to a linked owner document"
                )
    return errors
