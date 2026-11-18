"""Read workflow job blocks and their digests without a YAML dependency (#160).

`project.toml [ci.local]` is kept honest by digesting each workflow job block as
text. This module owns that reading: job discovery at any consistent block
indentation, quoted keys, the digest, and an honest "cannot read this `jobs:`
section" signal for flow-style or malformed bodies.

A flow mapping (`jobs: {...}`) has no block to digest, so `unreadable_jobs`
returns True and the drift check reports the workflow instead of silently
finding no jobs. `localci` turns that into a finding and executes the run.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

WORKFLOW_DIR = ".github/workflows"
JOBS_START = re.compile(r"""^(?:"jobs"|'jobs'|jobs):\s*(?:#.*)?$""")  # block-style jobs mapping
JOBS_KEY = re.compile(r"""^(?:"jobs"|'jobs'|jobs):""")  # any `jobs:` line, for the unreadable-form finding
JOB_KEY = re.compile(r"""^(?:"([A-Za-z0-9_-]+)"|'([A-Za-z0-9_-]+)'|([A-Za-z0-9_-]+)):(?:\s|$)""")
WORKFLOW_KEY = re.compile(r"^[A-Za-z0-9_.@/-]+\.ya?ml$")


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


def unreadable_jobs(text: str) -> bool:
    """A `jobs:` section with content but no readable block job keys.

    Covers a flow-style mapping (on the `jobs:` line or the next one), quoted
    keys we cannot read, and malformed bodies. A block `jobs:` with no jobs is
    not flagged: there is nothing to miss.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    start = next((index for index, line in enumerate(lines) if JOBS_START.match(line)), None)
    if start is None:
        return any(JOBS_KEY.match(line) for line in lines)
    body = [line for line in lines[start + 1:] if line.strip() and not line.lstrip().startswith("#")]
    return bool(body) and not workflow_jobs(text)


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
