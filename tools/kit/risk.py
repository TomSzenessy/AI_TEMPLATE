"""Ceremony scales with blast radius: classify changed paths into risk tiers.

`project.toml [risk]` lists `high` and `low` globs (first match wins, high
first); everything else is `normal`. The tier tells an agent how much process
the change needs, so small edits stay cheap and dangerous ones never skip review.
"""

from __future__ import annotations

from pathlib import Path

from .core import RepoctlError, load_project
from .gitinfo import branch_paths, path_matches

CEREMONY = {
    "low": "make check; no issue needed unless behavior or a contract changes.",
    "normal": "issue-backed write-ahead record, focused test, make verify, observed artifact.",
    "high": "normal ceremony + independent critic (critic role / make review-packet) + security/privacy doc review.",
}
ORDER = ("low", "normal", "high")


def tier_rules(project: dict[str, object]) -> dict[str, list[str]]:
    rules = project.get("risk", {})
    if not isinstance(rules, dict):
        raise RepoctlError("risk must be a table with high/low glob arrays")
    result = {}
    for tier in ("high", "low"):
        patterns = rules.get(tier, [])
        if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
            raise RepoctlError(f"risk.{tier} must be an array of globs")
        result[tier] = patterns
    return result


def classify(path: str, rules: dict[str, list[str]]) -> str:
    for tier in ("high", "low"):
        if any(path_matches(path, pattern) for pattern in rules[tier]):
            return tier
    return "normal"


def assess(root: Path, base: str | None = None) -> tuple[str, dict[str, list[str]]]:
    project = load_project(root)
    rules = tier_rules(project)
    base = base or str(project.get("repository", {}).get("default_branch", "main"))
    grouped: dict[str, list[str]] = {tier: [] for tier in ORDER}
    for path in branch_paths(root, base):
        grouped[classify(path, rules)].append(path)
    overall = max((tier for tier in ORDER if grouped[tier]), key=ORDER.index, default="low")
    return overall, grouped


def print_risk(root: Path, base: str | None = None) -> None:
    overall, grouped = assess(root, base)
    print(f"Risk tier: {overall} — {CEREMONY[overall]}")
    for tier in reversed(ORDER):
        if grouped[tier]:
            shown = grouped[tier][:12]
            more = f" (+{len(grouped[tier]) - 12} more)" if len(grouped[tier]) > 12 else ""
            print(f"- {tier}: {', '.join(shown)}{more}")
