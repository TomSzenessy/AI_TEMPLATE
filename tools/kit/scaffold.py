"""`make new`: add any capability, wired in from birth (docs/adr/0002-one-capability-model.md).

Creating a capability should be one low-risk command, not a checklist an agent
might half-follow. The scaffolder refuses near-duplicates of any kind (overlap
check), writes valid metadata, registers first-party skills, regenerates every
derived file (host adapters, docs index, role table, rules block, Makefile
commands), and leaves `FILL-IN:` markers that `make check` reports until the
content is real.
"""

from __future__ import annotations

import re
import shutil
import tomllib
from pathlib import Path

from . import derive
from .core import KEBAB, RepoctlError, ensure_inside_root
from .config import setting
from .docsync import doc_groups
from .navigate import skill_overlap
from .registry import CORE, KINDS, ROLE_ACCESS, ROLE_TIERS, Registry, yaml_string

FILL = "FILL" + "-IN:"  # split so the marker scanner never flags this module


def _title(name: str) -> str:
    return name.replace("-", " ").capitalize()


def _array_end(text: str, start: int) -> tuple[int, int]:
    """Scan a TOML array opened at text[start] == "[": return (index of its closing bracket, end of its last value or comma).

    Strings and comments are skipped, so a `]` or a `,` inside either never ends the scan.
    """
    depth, last, i = 0, start, start
    while i < len(text):
        char = text[i]
        if char in "\"'":
            end = i + 1
            while end < len(text) and text[end] != char:
                end += 2 if char == '"' and text[end] == "\\" else 1
            i = last = end
        elif char == "#":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return i, last
        elif not char.isspace():
            last = i
        i += 1
    raise RepoctlError("project.toml local_skills array is not closed")


def _local_skills(text: str) -> list[str] | None:
    try:
        value = tomllib.loads(text).get("capabilities", {}).get("local_skills")
    except tomllib.TOMLDecodeError as error:
        raise RepoctlError(f"project.toml is invalid: {error}") from error
    return value if isinstance(value, list) else None


def plan_local_skill(text: str, name: str) -> str:
    """Return project.toml text with `name` added to [capabilities] local_skills; comments and layout stay."""
    names = _local_skills(text)
    if names is None:
        raise RepoctlError("project.toml needs [capabilities] local_skills = [] to register a first-party skill")
    if name in names:
        return text
    match = re.search(r"(?m)^local_skills\s*=\s*\[", text)
    if not match:
        raise RepoctlError("project.toml needs local_skills written as one `local_skills = [...]` array to register a skill")
    open_at = match.end() - 1
    close_at, last = _array_end(text, open_at)
    item = f'"{name}"'
    if last == open_at:  # empty array
        edited = text[: open_at + 1] + item + text[open_at + 1 :]
    elif "\n" in text[open_at:close_at]:
        line_start = text.rfind("\n", 0, last) + 1
        indent = re.match(r"[ \t]*", text[line_start:]).group(0) or "    "
        comma = "" if text[last] == "," else ","
        edited = text[: last + 1] + comma + f"\n{indent}{item}," + text[last + 1 :]
    else:
        joiner = " " if text[last] == "," else ", "
        edited = text[: last + 1] + joiner + item + text[last + 1 :]
    if name not in (_local_skills(edited) or []):
        raise RepoctlError("could not register the skill in project.toml local_skills; add it by hand")
    return edited


def create(
    root: Path,
    kind: str,
    name: str,
    description: str,
    *,
    pack: str = "",
    group: str = "operate",
    covers: str = "",
    access: str = "read-only",
    tier: str = "balanced",
    force: bool = False,
) -> list[str]:
    if kind not in KINDS:
        raise RepoctlError(f"KIND must be one of: {', '.join(KINDS)}")
    if not KEBAB.fullmatch(name or ""):
        raise RepoctlError("NAME must be lowercase kebab-case, for example NAME=release-notes")
    description = " ".join((description or "").split())
    if len(description) < 20:
        raise RepoctlError(
            'DESC must say what it does and when to use it (20+ characters), e.g. DESC="Drafts release notes from merged PRs; use before tagging a release."'
        )
    pack = pack.strip() or CORE
    if kind != "pack" and pack != CORE and not Registry(root).get("pack", pack):
        raise RepoctlError(f"PACK={pack} does not exist; create it first with make new KIND=pack NAME={pack} DESC=\"...; ...\"")
    pack_line = f"pack: {pack}\n" if pack != CORE else ""
    messages: list[str] = []
    if kind != "doc":
        overlap = skill_overlap(root, description, name)
        if overlap:
            messages += [f"overlap {score:.2f} with {label}" for score, label, _ in overlap[:3]]
        # Refuse only a near-duplicate of the same kind; a similar capability of another kind is reported above.
        same = [item for item in overlap if item[1].startswith(f"{kind}:")]
        if same and same[0][0] >= float(setting(root, "overlap_limit")) and not force:
            raise RepoctlError(
                f"too similar to {same[0][1]} (overlap {same[0][0]:.2f}); extend that one instead, "
                "or re-run with FORCE=1 if it is genuinely different"
            )

    if kind == "skill":
        target = root / ".agents" / "skills" / name / "SKILL.md"
        body = (
            f"---\nname: {name}\ndescription: {yaml_string(description)}\n{pack_line}---\n\n# {_title(name)}\n\n"
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
            f"---\nname: {name}\ndescription: {yaml_string(description)}\naccess: {access}\ntier: {tier}\n{pack_line}---\n\n"
            f"# {_title(name)}\n\n{FILL} the one job this role owns and why a fresh context does it better.\n\n"
            f"## Method\n\n1. {FILL} steps, starting from `make where` and the owner docs.\n\n"
            f"## Never\n\n{FILL} edits, commands, or scope this role must not touch.\n\n"
            f"## Report (at most 200 words)\n\n```text\nAnswer: {FILL} answer format\nEvidence: <path:line or command output>\n```\n"
        )
    elif kind == "doc":
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
    elif kind == "rule":
        target = root / ".agents" / "rules" / f"{name}.md"
        scope_line = f"scope: {covers.strip()}\n" if covers.strip() else ""
        body = (
            f"---\nname: {name}\ndescription: {yaml_string(description)}\n{scope_line}{pack_line}---\n\n# {_title(name)}\n\n"
            f"{FILL} why this rule exists (the incident, trial, or decision behind it) and what to do instead.\n"
            "A rule without a scope is one line in AGENTS.md; a scoped rule reaches the agent when it edits a matching path.\n"
        )
    elif kind in {"check", "command"}:
        target = root / ".agents" / f"{kind}s" / f"{name}.py"
        pack_argument = f", pack={pack!r}" if pack != CORE else ""
        if kind == "check":
            body = (
                f'"""{FILL} what this check protects and the evidence behind it (docs/self-healing.md#when-a-check-may-block)."""\n\n'
                "from kit.registry import check\n\n\n"
                f"@check({name!r}, {description!r}, blocks=False{pack_argument})\n"
                "def run(context) -> list[str]:\n"
                f'    """Return findings that each name their fix. context.root, .project, .files, .bindings are available."""\n'
                f"    findings: list[str] = []  # {FILL} the check; switch to blocks=True with a reason once a trial proves it\n"
                "    return findings\n"
            )
        else:
            body = (
                f'"""{FILL} what this command does for the project; make sync adds `make {name}`."""\n\n'
                "from kit.registry import arg, command\n\n\n"
                f"@command({name!r}, {description!r}, group=\"when-needed\", usage=\"make {name}\"{pack_argument},\n"
                f"         args=())  # e.g. arg(\"--title\", var=\"TITLE\") passes `make {name} TITLE=...`\n"
                "def run(root, args) -> int:\n"
                f"    print(\"{FILL} implement {name}\")\n"
                "    return 0\n"
            )
    elif kind == "mcp":
        target = root / ".agents" / "mcp" / f"{name}.toml"
        body = (
            f"# {FILL} source, license, and review of this server (docs/resources.md); keep it disabled until reviewed.\n"
            f"name = \"{name}\"\ndescription = {yaml_string(description)}\n"
            "transport = \"http\"  # or stdio with command = [\"npx\", \"-y\", \"@scope/server@1.2.3\"] (pin exactly)\n"
            f"url = \"https://mcp.example.com/{name}\"\n"
            "env_headers = {}  # header name -> UPPER_CASE environment variable; keys never live here\n"
            "enabled = false\n" + (f"pack = \"{pack}\"\n" if pack != CORE else "")
        )
    else:  # pack
        target = root / ".agents" / "packs" / f"{name}.md"
        body = (
            f"---\nname: {name}\ndescription: {yaml_string(description)}\ndefault: off\n---\n\n# {_title(name)} pack\n\n"
            f"{FILL} what the pack is for and who switches it on. Add capabilities to it with PACK={name};\n"
            f"switch it on with `{name} = true` under [packs] in project.toml.\n"
        )

    target = ensure_inside_root(root, target, f"new {kind}")
    if target.exists():
        raise RepoctlError(f"{target.relative_to(root).as_posix()} already exists; edit it instead")
    manifest = root / "project.toml"
    original = manifest.read_bytes() if kind == "skill" else b""
    # Validate and compute the manifest edit before anything is written.
    edited = plan_local_skill(original.decode("utf-8"), name) if kind == "skill" else ""
    new_dir = None  # topmost directory this call creates, removed on failure
    probe = target.parent
    while not probe.exists():
        new_dir, probe = probe, probe.parent
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        if kind == "skill" and edited != original.decode("utf-8"):
            manifest.write_bytes(edited.encode("utf-8"))
        changed = derive.sync(root)
    except BaseException:
        if kind == "skill":
            manifest.write_bytes(original)
        if new_dir is not None:
            shutil.rmtree(new_dir, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
        raise
    messages.append(f"created {target.relative_to(root).as_posix()}")
    if changed:
        messages.append("integrated: " + ", ".join(changed))
    messages.append(f"next: replace every {FILL} line (make check lists them), then make done")
    return messages
