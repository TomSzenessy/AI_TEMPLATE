"""Rot detectors: expiring deprecations, orphan task markers, and context budgets.

Markers are language-neutral comments, so they work in any stack:

- `DEPRECATED(remove-by=YYYY-MM-DD, owner=..., use=...)` fails once the date passes.
- A language `@deprecated`/`@Deprecated` annotation needs a `remove-by=` date
  on the same line or within the next three lines.
- A task marker (to-do, fix-me, hack, triple-x) must reference an issue
  (`#123`, a URL, or `Local-WAL`) so open work lives in the issue register.
- A scaffold placeholder left by `make new` is unfinished work and fails.

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
SCAFFOLD = re.compile(r"\bF[I]LL-IN:")
INLINE_CODE = re.compile(r"`[^`\n]*`")  # documentation may name the marker in code spans
TASK_REFERENCE = re.compile(r"#\d+|https?://|Local-WAL")
PROSE_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".lock", ".svg"}


@dataclass
class MarkerReport:
    expired: list[str] = field(default_factory=list)
    upcoming: list[str] = field(default_factory=list)
    undated: list[str] = field(default_factory=list)
    orphan_tasks: list[str] = field(default_factory=list)
    unfinished: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        return (
            [f"expired deprecation: {item}" for item in self.expired]
            + [f"deprecation annotation without remove-by date: {item}" for item in self.undated]
            + [f"task marker without issue reference: {item}" for item in self.orphan_tasks]
            + [f"unfinished scaffold (replace the FILL-IN text): {item}" for item in self.unfinished]
        )


def scan_markers(root: Path, files: list[str], today: date | None = None, warning_days: int = 30) -> MarkerReport:
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
            if SCAFFOLD.search(INLINE_CODE.sub("", line)):
                report.unfinished.append(location)
            for match in DEPRECATION.finditer(line):
                try:
                    deadline = date.fromisoformat(match.group(1))
                except ValueError:
                    report.undated.append(f"{location} (invalid date {match.group(1)})")
                    continue
                if deadline < today:
                    report.expired.append(f"{location} (remove-by {deadline})")
                elif deadline <= today + timedelta(days=warning_days):
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


FENCE = re.compile(r"```.*?```", re.DOTALL)
WORDS = re.compile(r"[a-z0-9]+")


def duplicate_paragraphs(root: Path, files: list[str], min_words: int = 40, threshold: float = 0.8) -> list[str]:
    """Paragraphs that substantially repeat one in another document (one owner per fact)."""
    shingles: list[tuple[str, str, set[tuple[str, ...]]]] = []
    for relative in files:
        if not relative.endswith(".md") or relative.startswith((".claude/", ".agents/")):
            continue
        text = read_text_file(root, relative)
        for paragraph in re.split(r"\n\s*\n", FENCE.sub("", text or "")):
            words = WORDS.findall(paragraph.lower())
            if len(words) >= min_words:
                grams = {tuple(words[index : index + 6]) for index in range(len(words) - 5)}
                shingles.append((relative, " ".join(paragraph.split())[:60], grams))
    findings = []
    for position, (path_a, head_a, grams_a) in enumerate(shingles):
        for path_b, head_b, grams_b in shingles[position + 1 :]:
            if path_a != path_b and len(grams_a & grams_b) / min(len(grams_a), len(grams_b)) >= threshold:
                findings.append(f"{path_a} and {path_b} repeat a paragraph (\"{head_a}…\"); keep it in one owner and link")
    return findings


RUN_BLOCK = re.compile(r"^(\s*)(?:-\s+)?run:\s*[|>][+-]?\s*$")


def workflow_errors(root: Path, files: list[str], max_lines: int = 10) -> list[str]:
    """Long inline `run:` blocks hide untested logic in CI YAML; keep it in tools/."""
    errors = []
    for relative in files:
        if not (relative.startswith(".github/workflows/") and relative.endswith((".yml", ".yaml"))):
            continue
        lines = (read_text_file(root, relative) or "").splitlines()
        for number, line in enumerate(lines, start=1):
            match = RUN_BLOCK.match(line)
            if not match:
                continue
            indent = len(match.group(1))
            body = 0
            for following in lines[number:]:
                if following.strip() and len(following) - len(following.lstrip()) <= indent:
                    break
                body += bool(following.strip())
            if body > max_lines:
                errors.append(
                    f"{relative}:{number}: inline run block of {body} lines; move the logic into tools/ "
                    "(unit-tested, runnable locally) and call it from the workflow"
                )
    return errors
