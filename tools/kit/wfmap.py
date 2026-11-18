"""Read workflow job blocks and their digests without a YAML dependency (#160).

`project.toml [ci.local]` is kept honest by digesting each workflow job block as
text. This module owns that reading: conventional block YAML with GitHub's
documented top-level keys, job discovery at any consistent indentation, quoted
keys and key spacing, the digest, and an honest "cannot read this workflow"
signal.

The reader is deliberately conservative. Without a YAML parser it cannot
understand explicit keys (`? jobs`), flow mappings, unknown top-level keys, or
a jobs body with no readable job; `workflow_problem` names each of those so the
drift check fails instead of silently finding no jobs.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

WORKFLOW_DIR = ".github/workflows"
JOBS_START = re.compile(r"""^(?:"jobs"|'jobs'|jobs)\s*:\s*(?:[&!]\S+\s*)?(?:#.*)?$""")
JOB_KEY = re.compile(r"""^(?:"([A-Za-z0-9_-]+)"|'([A-Za-z0-9_-]+)'|([A-Za-z0-9_-]+))\s*:(?:\s|$)""")
TOP_KEY = re.compile(r"""^(?:"([A-Za-z_][A-Za-z0-9_-]*)"|'([A-Za-z_][A-Za-z0-9_-]*)'|([A-Za-z_][A-Za-z0-9_-]*))\s*:(.*)$""")
DOCUMENT_MARKER = re.compile(r"^(?:---|\.\.\.)\s*(?:#.*)?$")
BLOCK_LEAD = re.compile(r"^[&!]\S+$")  # an anchor or tag on the jobs value, with the block beneath
WORKFLOW_KEY = re.compile(r"^[A-Za-z0-9_.@/-]+\.ya?ml$")
# GitHub's documented top-level keys. Anything else is not a workflow the kit can
# claim to mirror; unknown keys are GitHub errors too, so reporting is honest.
TOP_KEYS = {"name", "run-name", "on", "permissions", "env", "defaults", "concurrency", "jobs"}


def workflow_paths(root: Path) -> list[str]:
    """Workflow files directly under `.github/workflows/`, repository-relative."""
    directory = root / WORKFLOW_DIR
    try:
        return sorted(path.relative_to(root).as_posix() for path in directory.iterdir()
                      if path.is_file() and path.suffix in {".yml", ".yaml"})
    except OSError:
        return []


def is_workflow_path(value: str) -> bool:
    """Whether a manifest `workflow` value looks like a repository-relative workflow file."""
    return bool(WORKFLOW_KEY.fullmatch(value))


def workflow_jobs(text: str) -> dict[str, str]:
    """Job id -> its YAML block, read as text so the kit needs no YAML parser.

    The first key under the column-zero `jobs:` line fixes the indentation, so
    two-space and four-space (or any consistent) block-style mappings both work.
    Quoted keys are read. A job block ends at the next key at that indentation
    or at a dedent out of the `jobs` mapping.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    start = next((index + 1 for index, line in enumerate(lines) if JOBS_START.match(line)), None)
    if start is None:
        return {}
    indent = next((len(line) - len(line.lstrip()) for line in lines[start:]
                   if line.strip() and not line.lstrip().startswith("#")), 0)
    if indent == 0:  # a flow mapping or malformed content, never a block of job keys
        return {}
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[start:]:
        content_indent = len(line) - len(line.lstrip())
        heading = JOB_KEY.match(line[indent:]) if line.startswith(" " * indent) and content_indent == indent else None
        if heading:
            current = next(group for group in heading.groups() if group)
            blocks[current] = [line]
            continue
        if current is None:
            continue
        if line and content_indent < indent:  # dedented to the next top-level key
            current = None
            continue
        blocks[current].append(line)
    return {name: _normalized(body) for name, body in blocks.items()}


def workflow_problem(text: str) -> str | None:
    """Why this workflow cannot be mirrored, or None when its jobs are readable.

    Reads the conventional block form of GitHub's documented top-level keys.
    An explicit key (`? jobs`), a flow mapping, an unknown top-level key, a
    `jobs:` body with no readable job, or a workflow with no `jobs:` at all is a
    named problem, never an empty job list. A workflow must define at least one
    job, so an empty or anchored-null `jobs:` is a problem too.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    jobs_index: int | None = None
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#") or line.startswith((" ", "\t")):
            continue
        if DOCUMENT_MARKER.match(line):
            continue
        match = TOP_KEY.match(line)
        if not match:
            return f"line {index + 1} is not a conventional top-level key ({line.strip()[:60]!r})"
        name = next(group for group in match.groups()[:3] if group)
        if name not in TOP_KEYS:
            return f"line {index + 1} has unsupported top-level key {name!r}"
        if name == "jobs":
            jobs_index = index
            value = match.group(4).split("#", 1)[0].strip()
            if value and not BLOCK_LEAD.match(value):
                return "its 'jobs:' value is not a block mapping"
    if jobs_index is None:
        return "it has no 'jobs:' mapping"
    body: list[str] = []
    for line in lines[jobs_index + 1:]:
        if line.strip() and not line.lstrip().startswith("#") and not line.startswith((" ", "\t")):
            break  # the next top-level key ends this section
        body.append(line)
    meaningful = [line for line in body if line.strip() and not line.lstrip().startswith("#")]
    if not meaningful:
        return "it has no readable jobs"
    if meaningful[0].lstrip().startswith(("{", "[")):
        return "its jobs are a flow mapping, not a block"
    indent = len(meaningful[0]) - len(meaningful[0].lstrip())
    for line in meaningful:
        if len(line) - len(line.lstrip()) == indent and not JOB_KEY.match(line[indent:]):
            return f"its job keys cannot be read as block-style jobs ({line.strip()[:60]!r})"
    if not workflow_jobs(text):
        return "its job keys cannot be read as block-style jobs"
    return None


def block_digest(block: str) -> str:
    """The reviewed digest of one job block, normalized so trailing whitespace cannot churn it."""
    return "sha256:" + hashlib.sha256(block.encode("utf-8")).hexdigest()


def _normalized(lines: list[str]) -> str:
    body = [line.rstrip() for line in lines]
    while body and not body[-1]:
        body.pop()
    while body and not body[0]:
        body.pop(0)
    return "\n".join(body)
