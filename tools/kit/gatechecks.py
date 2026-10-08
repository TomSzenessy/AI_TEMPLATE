"""Change-set rules the commit and stop gates ask the registry about (issue #22).

`doc-coupling` and `critic-evidence` judge a change set, so they only run when a gate hands the
`checkrun.Context` a `Change`; `make check` (no change set) finds nothing for them. Registered in
`checks.py`; the logic lives here so the registry file stays a list of declarations.
"""

from __future__ import annotations

import re

from . import docsync
from .core import governance_profile, read_text_file
from .gitinfo import changed_paths, committed_paths, git
from .names import CRITIC_RECORD
from .risk import classify, tier_rules

CRITIC_VERDICTS = ("blocker", "ship-with-residuals")


def owed_docs(context) -> list[str]:
    """Documents that cover the change set but were not updated with it."""
    change = context.change
    if change is None:
        return []
    root, bindings = context.root, context.bindings
    if change.kind == "commit":
        pending = docsync.pending_documents(bindings, [p for p in change.paths if p not in change.merged_in])
        return [
            f"{doc} covers staged {', '.join(paths[:4])} but is not staged"
            for doc, paths in pending.items()
            if "*" not in change.exempt and doc not in change.exempt
        ]
    if change.scoped:
        dirty = set(changed_paths(root))
        uncommitted = [path for path in change.paths if path in dirty]
        owed = docsync.owed_since(root, bindings, f"{change.since}..HEAD", uncommitted) if change.since else {}
    else:
        uncommitted = changed_paths(root)
        owed = docsync.owed_documents(root, bindings, change.base, uncommitted)
    # Predict the commit gate too: it asks per commit, so a doc touched earlier on the
    # branch does not cover uncommitted code. Two gates that disagree cost a round trip.
    for doc, paths in docsync.pending_documents(bindings, uncommitted).items():
        owed.setdefault(doc, paths)
    return [
        f"{doc} covers changed {', '.join(paths[:4])}{' …' if len(paths) > 4 else ''} but was not updated"
        " (update it, or record why in the commit with a 'Docs-Unaffected: <doc> <reason>' trailer)"
        for doc, paths in owed.items()
    ]


def critic_evidence(context) -> list[str]:
    """High-risk work needs an independent critic whose verdict this gate can read.

    The record is the critic's return saved verbatim to `.agent/critic.md`; a
    verdict outside the fixed vocabulary is a failure, not a softer pass.
    """
    change = context.change
    if change is None or change.kind != "finish":
        return []
    root, project = context.root, context.project
    if governance_profile(project) == "minimal":
        return []  # the host owns issues, review, and ceremony
    rules = tier_rules(project)
    if change.scoped and not any(classify(path, rules) == "high" for path in change.paths):
        return []  # a session scope demands evidence only for high-risk work it changed
    risky = [path for path in committed_paths(root, change.base) if classify(path, rules) == "high"]
    if not risky:
        return []
    vocabulary = " | ".join(CRITIC_VERDICTS)
    content = read_text_file(root, CRITIC_RECORD) or ""
    if not content.strip():
        return [
            f"high-risk change ({', '.join(risky[:4])}) has no critic evidence: run the critic role on this change"
            f" set and save its return verbatim to {CRITIC_RECORD}"
        ]
    verdict = re.search(r"(?im)^Verdict:\s*(\S+)", content)
    if verdict is None:
        return [f"{CRITIC_RECORD} states no verdict; the critic returns exactly one of: {vocabulary}"]
    word = verdict.group(1).strip().lower()
    if word not in CRITIC_VERDICTS:
        return [f"{CRITIC_RECORD} verdict {word!r} is outside the fixed vocabulary ({vocabulary}); prose is not a verdict"]
    if word == CRITIC_VERDICTS[0]:
        return [f"{CRITIC_RECORD} verdict is {word}: fix what it lists, then ask the critic again"]
    reviewed = re.search(r"(?im)^Commit:\s*([0-9a-f]{40})\b", content)
    if not reviewed:
        return [f"{CRITIC_RECORD} has no 'Commit: <40-hex>' line, so it is not bound to a reviewed change set"]
    current = (git(root, "rev-parse", "HEAD") or "").strip()
    if current and reviewed.group(1) != current:
        return [f"{CRITIC_RECORD} reviews {reviewed.group(1)[:12]}, not HEAD {current[:12]}: the critic read older work"]
    return []
