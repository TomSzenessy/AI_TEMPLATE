"""`make new`: add a skill, subagent role, or document that is wired in from birth.

Creating a capability should be one low-risk command, not a checklist an agent
might half-follow. The scaffolder refuses near-duplicates (overlap check),
writes valid metadata, registers first-party skills, regenerates every derived
file (host adapters, docs index, role table), and leaves `FILL-IN:` markers
that `make check` reports until the content is real.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import derive
from .adapters import ROLE_ACCESS, ROLE_TIERS, yaml_string
from .core import RepoctlError, ensure_inside_root
from .config import setting
from .docsync import doc_groups
from .navigate import skill_overlap

KINDS = ("skill", "agent", "doc")
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FILL = "FILL" + "-IN:"  # split so the marker scanner never flags this module


def _title(name: str) -> str:
    return name.replace("-", " ").capitalize()


def _register_local_skill(root: Path, name: str) -> None:
    manifest = root / "project.toml"
    text = manifest.read_text(encoding="utf-8")
    match = re.search(r"(?m)^local_skills\s*=\s*\[([^\]]*)\]", text)
    if not match:
        raise RepoctlError("project.toml needs [capabilities] local_skills = [] to register a first-party skill")
    names = [item.strip().strip('"') for item in match.group(1).split(",") if item.strip()]
    rendered = "local_skills = [" + ", ".join(f'"{item}"' for item in sorted({*names, name})) + "]"
    manifest.write_text(text[: match.start()] + rendered + text[match.end() :], encoding="utf-8")


def create(
    root: Path,
    kind: str,
    name: str,
    description: str,
    *,
    group: str = "operate",
    covers: str = "",
    access: str = "read-only",
    tier: str = "balanced",
    force: bool = False,
) -> list[str]:
    if kind not in KINDS:
        raise RepoctlError(f"KIND must be one of: {', '.join(KINDS)}")
    if not NAME.fullmatch(name or ""):
        raise RepoctlError("NAME must be lowercase kebab-case, for example NAME=release-notes")
    description = " ".join((description or "").split())
    if len(description) < 20:
        raise RepoctlError(
            'DESC must say what it does and when to use it (20+ characters), e.g. DESC="Drafts release notes from merged PRs; use before tagging a release."'
        )
    messages: list[str] = []
    if kind in {"skill", "agent"}:
        overlap = skill_overlap(root, description, name)
        if overlap:
            messages += [f"overlap {score:.2f} with {label}" for score, label, _ in overlap[:3]]
        if overlap and overlap[0][0] >= float(setting(root, "overlap_limit")) and not force:
            raise RepoctlError(
                f"too similar to {overlap[0][1]} (overlap {overlap[0][0]:.2f}); extend that one instead, "
                "or re-run with FORCE=1 if it is genuinely different"
            )

    if kind == "skill":
        target = root / ".agents" / "skills" / name / "SKILL.md"
        body = (
            f"---\nname: {name}\ndescription: {yaml_string(description)}\n---\n\n# {_title(name)}\n\n"
            f"{FILL} one paragraph on the outcome and the trigger that should load this skill.\n\n"
            f"## Steps\n\n1. {FILL} concrete, checkable steps; link owner docs instead of copying them.\n\n"
            f"## Done when\n\n- {FILL} the observable check or artifact that proves success.\n"
        )
    elif kind == "agent":
        if access not in ROLE_ACCESS or tier not in ROLE_TIERS:
            raise RepoctlError(
                f"ACCESS must be one of {', '.join(sorted(ROLE_ACCESS))}; TIER one of {', '.join(sorted(ROLE_TIERS))}"
            )
        target = root / ".agents" / "agents" / f"{name}.md"
        body = (
            f"---\nname: {name}\ndescription: {yaml_string(description)}\naccess: {access}\ntier: {tier}\n---\n\n"
            f"# {_title(name)}\n\n{FILL} the one job this role owns and why a fresh context does it better.\n\n"
            f"## Method\n\n1. {FILL} steps, starting from `make where` and the owner docs.\n\n"
            f"## Never\n\n{FILL} edits, commands, or scope this role must not touch.\n\n"
            f"## Report (at most 200 words)\n\n```text\nAnswer: {FILL} answer format\nEvidence: <path:line or command output>\n```\n"
        )
    else:
        if group not in doc_groups(root):
            raise RepoctlError(f"GROUP must be one of: {', '.join(doc_groups(root))} (project.toml [kit].doc_groups)")
        owns, _, when = description.partition(";")
        if not when.strip():
            raise RepoctlError('for a doc, DESC is "<what it owns>; <when to read it>"')
        target = root / "docs" / f"{name}.md"
        covers_line = f"<!-- covers: {covers} -->\n" if covers.strip() else ""
        body = (
            f"# {_title(name)}\n\n<!-- index: {group} | {owns.strip()} | {when.strip()} -->\n{covers_line}\n"
            f"{FILL} the durable facts this document owns. Describe what the code does now,\n"
            "link related owners instead of copying them, and keep live status in issues.\n"
        )

    target = ensure_inside_root(root, target, f"new {kind}")
    if target.exists():
        raise RepoctlError(f"{target.relative_to(root).as_posix()} already exists; edit it instead")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    if kind == "skill":
        _register_local_skill(root, name)
    changed = derive.sync(root)
    messages.append(f"created {target.relative_to(root).as_posix()}")
    if changed:
        messages.append("integrated: " + ", ".join(changed))
    messages.append(f"next: replace every {FILL} line (make check lists them), then make done")
    return messages
