"""Local CI: run the workflow jobs a laptop can reproduce, on the exact tree (#160).

Workflows own what CI does; `project.toml [ci.local]` maps each of their jobs to
the command that does the same work here. A mapped job is `PASS`, `FAIL`, or
`SKIP` (a missing toolchain is never a pass), and a run with a skip is
`INCOMPLETE` (exit 3) unless the caller explicitly allows it. Jobs that genuinely
cannot run locally are declared `[[ci.local.not_local]]` with a reason; they are
listed in every summary and are never counted as passed.

The map can go stale the moment a workflow changes, so every mapped job stores
the digest of its reviewed workflow block. `make check` (and `ci-local --check`)
fails on a workflow job that is neither mapped nor `not_local`, and on a digest
that no longer matches; `ci-local --bless` updates the digests after a human or
agent has re-read the workflow diff.

Nothing here reads a provider key, talks to the network, or runs a `not_local`
job: the runner only executes the commands the manifest declares. A local pass
proves those commands on this tree, not runner images, the OS matrix, or
GitHub-only permissions (`docs/local-ci.md`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .core import RepoctlError, load_project, read_text_file
from .gitinfo import git

WORKFLOW_DIR = ".github/workflows"
STATE_DIR = ".agent/ci-local"
LAST_RUN = "last-run.json"
PASS, FAIL, SKIP, NOT_LOCAL = "PASS", "FAIL", "SKIP", "NOT LOCAL"
EXIT_PASSED, EXIT_FAILED, EXIT_MISUSE, EXIT_INCOMPLETE = 0, 1, 2, 3
JOBS_START = re.compile(r"""^(?:"jobs"|'jobs'|jobs):\s*(?:#.*)?$""")  # block-style jobs mapping
JOBS_KEY = re.compile(r"""^(?:"jobs"|'jobs'|jobs):""")  # any `jobs:` line, for the unreadable-form finding
JOB_KEY = re.compile(r"""^(?:"([A-Za-z0-9_-]+)"|'([A-Za-z0-9_-]+)'|([A-Za-z0-9_-]+)):(?:\s|$)""")
WORKFLOW_KEY = re.compile(r"^[A-Za-z0-9_.@/-]+\.ya?ml$")
VERSION = re.compile(r"(\d+(?:\.\d+)+)")
VERSION_MINIMUM = re.compile(r"\d+(?:\.\d+)*")
TRUTHY = {"1", "true", "yes", "on"}


# --- The manifest and the workflows it mirrors -------------------------------------


@dataclass(frozen=True)
class Job:
    """One workflow job mapped to the commands that reproduce it locally."""

    group: str
    workflow: str
    name: str
    tools: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]
    slow: bool = False
    digest: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.workflow, self.name)


@dataclass(frozen=True)
class NotLocal:
    """One workflow job that deliberately cannot run on a laptop."""

    workflow: str
    name: str
    reason: str


@dataclass
class Plan:
    jobs: list[Job] = field(default_factory=list)
    not_local: list[NotLocal] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    digest_problems: list[str] = field(default_factory=list)  # the subset BLESS=1 may repair
    tools: dict[str, str] = field(default_factory=dict)
    guard: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.jobs or self.not_local)


@dataclass
class Options:
    """What the command line asked for; the make targets feed the same fields."""

    group: str = ""
    check: bool = False
    list_jobs: bool = False
    plan_only: bool = False
    bless: bool = False
    allow_skip: bool = False
    slow: bool = False
    dirty: bool = False
    guard: bool = False


def _local_table(project: dict[str, object]) -> dict[str, object] | None:
    """The `[ci.local]` table, or None when malformed (a finding, never a crash)."""
    ci = project.get("ci")
    local = ci.get("local") if isinstance(ci, dict) else {}
    if local is None or local == {}:
        return {}
    return local if isinstance(local, dict) else None


def _strings(value: object) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def load_plan(root: Path) -> Plan:
    """The manifest entries and the workflows they claim to mirror. Findings never raise."""
    local = _local_table(load_project(root))
    if local is None:
        plan = Plan()
        plan.problems.append("project.toml [ci.local] must be a table of jobs, not_local, and tools")
        return plan
    tools = local.get("tools") or {}
    if not isinstance(tools, dict):
        plan = Plan()
        plan.problems.append("project.toml [ci.local.tools] must be a table of minimum version strings")
        return plan
    plan = Plan(tools={str(key): str(value) for key, value in tools.items()})
    for tool, minimum in plan.tools.items():
        if not VERSION_MINIMUM.fullmatch(minimum):
            plan.problems.append(f"[ci.local.tools] {tool} minimum '{minimum}' must be a version like 3.11")
    if local.get("guard", False) not in (True, False):
        plan.problems.append("project.toml [ci.local] guard must be true or false")
    plan.guard = local.get("guard", False) is True

    raw_jobs = local.get("jobs", [])
    raw_not_local = local.get("not_local", [])
    if not isinstance(raw_jobs, list) or not isinstance(raw_not_local, list):
        plan.problems.append("project.toml [ci.local] jobs and not_local must be arrays of tables")
        return plan

    seen: dict[tuple[str, str], str] = {}
    for kind, entries in (("a mapped job", raw_jobs), ("not_local", raw_not_local)):
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                plan.problems.append(f"[ci.local] {kind} entry {index} must be a table")
                continue
            workflow, name = entry.get("workflow"), entry.get("job")
            if not isinstance(workflow, str) or not isinstance(name, str) or not workflow or not name:
                plan.problems.append(f"[ci.local] {kind} entry {index} needs string 'workflow' and 'job' fields")
                continue
            key = (workflow, name)
            if key in seen:
                plan.problems.append(f"{workflow}:{name} is declared twice (as {seen[key]} and {kind}); keep one entry")
                continue
            seen[key] = kind

    for entry in raw_jobs:
        if not isinstance(entry, dict):
            continue
        workflow, name = entry.get("workflow"), entry.get("job")
        if not isinstance(workflow, str) or not isinstance(name, str):
            continue
        commands = entry.get("commands")
        parsed: list[tuple[str, ...]] = []
        if not isinstance(commands, list) or not commands:
            plan.problems.append(f"{workflow}:{name} needs a non-empty commands array (a command is an array of strings)")
        else:
            for command in commands:
                parts = _strings(command)
                if not parts or not all(part.strip() for part in parts):
                    plan.problems.append(f"{workflow}:{name} has a command that is not a non-empty array of strings")
                    break
                parsed.append(tuple(parts))
        tools = _strings(entry.get("tools", []))
        if tools is None:
            plan.problems.append(f"{workflow}:{name} tools must be an array of tool names")
            tools = []
        group = entry.get("group", "default")
        if not isinstance(group, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", group):
            plan.problems.append(f"{workflow}:{name} group must be a name of letters, digits, dots, dashes, "
                                 "or underscores")
            group = "default"
        slow = entry.get("slow", False)
        if not isinstance(slow, bool):
            plan.problems.append(f"{workflow}:{name} slow must be true or false")
            slow = False
        digest = entry.get("digest", "")
        if not isinstance(digest, str):
            plan.problems.append(f"{workflow}:{name} digest must be a string")
            digest = ""
        plan.jobs.append(Job(group=group.strip(), workflow=workflow, name=name, tools=tuple(tools),
                             commands=tuple(parsed), slow=slow, digest=digest))

    for entry in raw_not_local:
        if not isinstance(entry, dict):
            continue
        workflow, name, reason = entry.get("workflow"), entry.get("job"), entry.get("reason")
        if not isinstance(workflow, str) or not isinstance(name, str):
            continue
        if not isinstance(reason, str) or not reason.strip():
            plan.problems.append(f"{workflow}:{name} not_local needs a reason: what runs only in CI and what "
                                 "substitute evidence the PR should carry")
            reason = ""
        plan.not_local.append(NotLocal(workflow=workflow, name=name, reason=reason.strip()))

    if not plan.configured:
        return plan
    _check_against_workflows(root, plan)
    return plan


def workflow_jobs(text: str) -> dict[str, str]:
    """Job id -> its YAML block, read as text so the kit needs no YAML parser.

    The first key under the column-zero `jobs:` line fixes the indentation, so
    two-space and four-space (or any consistent) block-style mappings both work.
    A job block ends at the next key at that indentation or at a dedent out of
    the `jobs` mapping. Flow-style `jobs: {...}` is not a block we can digest;
    `_unreadable_jobs` makes that visible instead of silently empty.
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


def _unreadable_jobs(text: str) -> bool:
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


def _normalized(lines: list[str]) -> str:
    body = [line.rstrip() for line in lines]
    while body and not body[-1]:
        body.pop()
    while body and not body[0]:
        body.pop(0)
    return "\n".join(body)


def block_digest(block: str) -> str:
    return "sha256:" + hashlib.sha256(block.encode("utf-8")).hexdigest()


def _workflow_paths(root: Path) -> list[str]:
    directory = root / WORKFLOW_DIR
    try:
        names = sorted(path.relative_to(root).as_posix() for path in directory.iterdir()
                       if path.is_file() and path.suffix in {".yml", ".yaml"})
    except OSError:
        return []
    return names


def _check_against_workflows(root: Path, plan: Plan) -> None:
    workflows: dict[str, dict[str, str]] = {}
    for relative in _workflow_paths(root):
        text = read_text_file(root, relative)
        if text is None:
            continue
        workflows[relative] = workflow_jobs(text)
        if _unreadable_jobs(text):
            plan.problems.append(f"{relative}: its jobs are not block-style under `jobs:`, so the local CI map "
                                 "cannot see them; use one key per line (docs/local-ci.md)")
    declared = {job.key for job in plan.jobs} | {(item.workflow, item.name) for item in plan.not_local}
    for job in plan.jobs:
        if not WORKFLOW_KEY.match(job.workflow):
            plan.problems.append(f"{job.workflow}:{job.name} workflow must be a path like "
                                 f"{WORKFLOW_DIR}/ci.yml")
            continue
        jobs = workflows.get(job.workflow)
        if jobs is None:
            plan.problems.append(f"{job.workflow} does not exist (declared by {job.name}); fix the path or remove the entry")
            continue
        if job.name not in jobs:
            plan.problems.append(f"{job.workflow}: no job '{job.name}' (renamed or removed); update project.toml [ci.local]")
            continue
        if not job.digest:
            message = (f"{job.workflow}:{job.name} has no digest: re-read the workflow job, then run "
                       "make ci-local BLESS=1")
            plan.problems.append(message)
            plan.digest_problems.append(message)
        elif job.digest != block_digest(jobs[job.name]):
            message = (f"{job.workflow}:{job.name} changed since it was reviewed (stale digest); "
                       "re-read the job diff, then run make ci-local BLESS=1")
            plan.problems.append(message)
            plan.digest_problems.append(message)
    for item in plan.not_local:
        jobs = workflows.get(item.workflow)
        if jobs is None:
            plan.problems.append(f"{item.workflow} does not exist (declared not_local by {item.name}); fix the path")
        elif item.name not in jobs:
            plan.problems.append(f"{item.workflow}: no job '{item.name}' (renamed or removed); update project.toml [ci.local]")
    for relative, jobs in workflows.items():
        for name in jobs:
            if (relative, name) not in declared:
                plan.problems.append(f"{relative}:{name} is neither mapped in [[ci.local.jobs]] nor declared in "
                                     "[[ci.local.not_local]]: add one (docs/local-ci.md)")


def findings(root: Path) -> list[str]:
    """The drift check behind `make check` and `ci-local --check`; empty only when there is nothing to judge."""
    plan = load_plan(root)
    return plan.problems if (plan.configured or plan.problems) else []


# --- Tools ------------------------------------------------------------------------


def tool_version(tool: str) -> str | None:
    """The first dotted version a tool prints, or None when it is missing or unreadable."""
    executable = shutil.which(tool)
    if not executable:
        return None
    command = [executable, "version"] if tool == "go" else [executable, "--version"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = VERSION.search(f"{result.stdout}\n{result.stderr}")
    return match.group(1) if match else None


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def version_at_least(found: str, minimum: str) -> bool:
    left, right = _version_tuple(found), _version_tuple(minimum)
    length = max(len(left), len(right))
    return left + (0,) * (length - len(left)) >= right + (0,) * (length - len(right))


def tool_skip(job: Job, minimums: dict[str, str]) -> str:
    """Why this job cannot run here, or "" when every declared tool is installed and new enough."""
    for tool in job.tools:
        if shutil.which(tool) is None:
            return f"tool '{tool}' not installed"
        minimum = minimums.get(tool)
        if minimum:
            found = tool_version(tool)
            if found and not version_at_least(found, minimum):
                return f"tool '{tool}' {found} < required {minimum}"
    return ""


# --- Running ----------------------------------------------------------------------


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUTHY


def _git_head(root: Path) -> tuple[str, str]:
    commit = (git(root, "rev-parse", "HEAD") or "").strip()
    tree = (git(root, "rev-parse", "HEAD^{tree}") or "").strip()
    if not commit or not tree:
        raise RepoctlError("local CI needs a git checkout with one commit to record the verified tree")
    return commit, tree


def _dirty(root: Path) -> bool:
    """Uncommitted tracked/untracked content, ignoring the runner's own recorded evidence."""
    status = git(root, "status", "--porcelain", "--untracked-files=all") or ""
    for line in status.splitlines():
        path = line[3:].strip().strip('"')
        if path == STATE_DIR or path.startswith(STATE_DIR + "/"):
            continue
        if path:
            return True
    return False


def _selected(jobs: list[Job], group_spec: str) -> list[Job]:
    wanted = [name for name in re.split(r"[,\s]+", group_spec.strip()) if name]
    if not wanted:
        return jobs
    known = {job.group for job in jobs}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise RepoctlError(f"unknown local CI group(s) {', '.join(unknown)}; available: {', '.join(sorted(known))}")
    return [job for job in jobs if job.group in wanted]


def _run_id(commit: str, dirty: bool) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    return f"{stamp}-{commit[:7]}{'-dirty' if dirty else ''}-{time.time_ns() % 1_000_000:06d}"


def _tail(path: Path, limit: int = 20) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-limit:])


def _label(workflow: str, name: str) -> str:
    return f"{Path(workflow).name}:{name}"


def _print_plan(root: Path, jobs: list[Job], not_local: list[NotLocal], plan: Plan) -> None:
    print(f"Local CI plan ({len(jobs)} mapped, {len(not_local)} not local)")
    print(f"{'GROUP':<10} {'WORKFLOW:JOB':<40} {'TOOLS':<18} COMMANDS")
    for job in jobs:
        commands = " && ".join(shlex.join(command) for command in job.commands)
        print(f"{job.group:<10} {_label(job.workflow, job.name):<40} {','.join(job.tools) or '-':<18} {commands}")
    for item in not_local:
        print(f"{'not_local':<10} {_label(item.workflow, item.name):<40} {'-':<18} {item.reason}")
    if plan.problems:
        print(f"\nDrift: {len(plan.problems)} problem(s); run make ci-local CHECK=1")


def _print_states(root: Path, jobs: list[Job], plan: Plan, options: Options) -> None:
    slow_enabled = options.slow or _truthy(os.environ.get("CI_LOCAL_SLOW"))
    print(f"\n{'GROUP':<10} {'WORKFLOW:JOB':<40} STATE")
    for job in jobs:
        reason = tool_skip(job, plan.tools)
        if not reason and job.slow and not slow_enabled:
            reason = "slow; set CI_LOCAL_SLOW=1 (or SLOW=1)"
        print(f"{job.group:<10} {_label(job.workflow, job.name):<40} {'READY' if not reason else 'SKIP (' + reason + ')'}")


def doctor(root: Path) -> int:
    """Print every tool the mapped jobs need, its detected version, and the declared minimum."""
    plan = load_plan(root)
    if not plan.configured:
        print("No local CI jobs are mapped; add [[ci.local.jobs]] to project.toml (docs/local-ci.md).")
        return 0
    needs: dict[str, list[str]] = {}
    for job in plan.jobs:
        for tool in job.tools:
            needs.setdefault(tool, []).append(f"{job.group}:{job.name}")
    print("Local CI tools (project.toml [ci.local.tools] holds the minimums)")
    print(f"{'TOOL':<14} {'FOUND':<12} {'MINIMUM':<30} NEEDED BY")
    for tool in sorted(needs):
        found = tool_version(tool) or ("missing" if shutil.which(tool) is None else "unreadable")
        minimum = plan.tools.get(tool, "-")
        print(f"{tool:<14} {found:<12} {minimum:<30} {', '.join(needs[tool])}")
    return 0


def check(root: Path) -> int:
    plan = load_plan(root)
    if not plan.configured and not plan.problems:
        print("No local CI map is configured (project.toml [ci.local]); add jobs or leave the workflows to CI "
              "(docs/local-ci.md).")
        return EXIT_PASSED
    if not plan.problems:
        print(f"Local CI mirrors every workflow job ({len(plan.jobs)} mapped, {len(plan.not_local)} not local).")
        return EXIT_PASSED
    print("Local CI drift:")
    print("\n".join(f"- {problem}" for problem in plan.problems))
    print("Fix the manifest, or re-read the workflow diff and run make ci-local BLESS=1.")
    return EXIT_FAILED


def _patch_digests(text: str, digests: dict[tuple[str, str], str]) -> str:
    """Rewrite `digest` inside each `[[ci.local.jobs]]` block; comments and layout stay."""
    lines = text.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != "[[ci.local.jobs]]":
            output.append(lines[index])
            index += 1
            continue
        end = index + 1
        while end < len(lines) and not lines[end].startswith("["):
            end += 1
        block = lines[index:end]
        workflow = name = ""
        for line in block:
            match = re.match(r"""\s*workflow\s*=\s*["']([^"']+)["']""", line)
            workflow = match.group(1) if match else workflow
            match = re.match(r"""\s*job\s*=\s*["']([^"']+)["']""", line)
            name = match.group(1) if match else name
        digest = digests.get((workflow, name))
        if digest:
            replaced = False
            for position, line in enumerate(block):
                if re.match(r"\s*digest\s*=", line):
                    block[position] = f'digest = "{digest}"'
                    replaced = True
            if not replaced:
                at = next((position for position, line in enumerate(block)
                           if re.match(r"\s*job\s*=", line)), len(block) - 1)
                block.insert(at + 1, f'digest = "{digest}"')
        output.extend(block)
        index = end
    return "\n".join(output) + ("\n" if text.endswith("\n") else "")


def bless(root: Path) -> int:
    """Refresh reviewed digests after a human or agent re-read the workflow diff."""
    plan = load_plan(root)
    if not plan.configured:
        print("No local CI jobs are mapped; nothing to bless (docs/local-ci.md).")
        return EXIT_MISUSE
    structural = [problem for problem in plan.problems if problem not in plan.digest_problems]
    if structural:
        print("Cannot bless until the manifest matches the workflows:")
        print("\n".join(f"- {problem}" for problem in structural))
        return EXIT_FAILED
    digests: dict[tuple[str, str], str] = {}
    for job in plan.jobs:
        text = read_text_file(root, job.workflow)
        if text is None:
            continue
        block = workflow_jobs(text).get(job.name)
        if block is not None:
            digests[job.key] = block_digest(block)
    manifest = root / "project.toml"
    try:
        original = manifest.read_text(encoding="utf-8")
    except OSError as error:
        raise RepoctlError(f"cannot read project.toml: {error}") from error
    updated = _patch_digests(original, digests)
    if updated == original:
        print("Local CI digests are already current.")
        return EXIT_PASSED
    manifest.write_text(updated, encoding="utf-8")
    print(f"Updated {len(digests)} local CI digest(s) in project.toml; review the workflow diff and commit them.")
    return EXIT_PASSED


def _result_line(state: str, job: Job, duration: float, reason: str = "") -> str:
    line = f"  {state:<9} {job.group:<10} {_label(job.workflow, job.name):<36} {duration:6.1f}s"
    return f"{line}  {reason}" if reason else line


def run(root: Path, options: Options) -> int:
    """Execute the selected jobs and record the evidence; 0 passed, 1 failed, 3 incomplete.

    Also the one command entry point: `--guard` is the pre-push policy and must
    dispatch here (the hook calls `repoctl ci-local --guard`), never into a run.
    """
    if options.guard:
        return guard(root)
    plan = load_plan(root)
    if options.check:
        return check(root)
    if options.bless:
        return bless(root)
    if options.list_jobs or options.plan_only:
        _print_plan(root, plan.jobs, plan.not_local, plan)
        if options.plan_only:
            _print_states(root, plan.jobs, plan, options)
        return EXIT_PASSED
    if plan.problems:
        print("Local CI cannot run while the manifest and workflows disagree:", file=sys.stderr)
        print("\n".join(f"- {problem}" for problem in plan.problems), file=sys.stderr)
        print("Run make ci-local BLESS=1 after re-reading the workflow diff, or fix the manifest.", file=sys.stderr)
        return EXIT_MISUSE
    if not plan.jobs:
        print("No local CI jobs are mapped; add [[ci.local.jobs]] to project.toml (docs/local-ci.md).", file=sys.stderr)
        return EXIT_MISUSE
    try:
        jobs = _selected(plan.jobs, options.group)
        commit, tree = _git_head(root)
    except RepoctlError as error:
        print(str(error), file=sys.stderr)
        return EXIT_MISUSE
    dirty = _dirty(root)
    if dirty and not options.dirty:
        print("Local CI refuses a dirty tree: commit or stash first, or run make ci-local DIRTY=1 "
              "(the run is then recorded as unverified).", file=sys.stderr)
        return EXIT_MISUSE
    allow_skip = options.allow_skip or _truthy(os.environ.get("ALLOW_SKIP"))
    slow_enabled = options.slow or _truthy(os.environ.get("CI_LOCAL_SLOW"))
    run_id = _run_id(commit, dirty)
    log_dir = root / STATE_DIR / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    wall_start = time.monotonic()
    print(f"Local CI: {len(jobs)} job(s) on {commit[:7]}{' (dirty tree)' if dirty else ''} "
          f"{'(slow jobs enabled)' if slow_enabled else ''}")

    records: list[dict[str, object]] = []
    passed = failed = skipped = 0
    for job in jobs:
        reason = tool_skip(job, plan.tools)
        if not reason and job.slow and not slow_enabled:
            reason = "slow; set CI_LOCAL_SLOW=1 (or SLOW=1)"
        if reason:
            skipped += 1
            print(_result_line(SKIP, job, 0.0, reason))
            records.append({"group": job.group, "workflow": job.workflow, "job": job.name, "state": SKIP,
                            "reason": reason, "duration_s": 0.0, "tools": list(job.tools)})
            continue
        log = log_dir / f"{job.group}-{job.name}.log".replace("/", "-")
        print(f"  RUN      {job.group:<10} {_label(job.workflow, job.name):<36}", flush=True)
        job_start = time.monotonic()
        ok = True
        with log.open("w", encoding="utf-8") as handle:
            for command in job.commands:
                handle.write(f"$ {shlex.join(command)}\n")
                handle.flush()
                try:
                    done = subprocess.run(list(command), cwd=root, stdout=handle, stderr=subprocess.STDOUT,
                                          text=True, check=False)
                except OSError as error:
                    handle.write(f"cannot run: {error}\n")
                    ok = False
                    break
                if done.returncode != 0:
                    handle.write(f"\nexit {done.returncode}\n")
                    ok = False
                    break
        duration = time.monotonic() - job_start
        state = PASS if ok else FAIL
        if ok:
            passed += 1
        else:
            failed += 1
        print(_result_line(state, job, duration))
        if not ok:
            print(f"  --- {log.relative_to(root).as_posix()} (last lines) ---")
            print("\n".join(f"  {line}" for line in _tail(log).splitlines()))
        records.append({"group": job.group, "workflow": job.workflow, "job": job.name, "state": state,
                        "duration_s": round(duration, 3), "tools": list(job.tools),
                        "log": log.relative_to(root).as_posix()})

    state = "failed" if failed else ("incomplete" if skipped else "passed")
    elapsed = time.monotonic() - wall_start
    print(f"\nLocal CI summary: {passed} passed, {failed} failed, {skipped} skipped, "
          f"{len(plan.not_local)} not local ({elapsed:.1f}s)")
    for item in plan.not_local:
        print(f"  {NOT_LOCAL:<9} {item.workflow}:{item.name}: {item.reason}")
    if failed:
        print("Local CI: FAILED")
        code = EXIT_FAILED
    elif skipped and not allow_skip:
        print("Local CI: INCOMPLETE (a skipped job is never a pass; install the tool or set ALLOW_SKIP=1 to accept it)")
        code = EXIT_INCOMPLETE
    elif skipped:
        print("Local CI: PASSED WITH SKIPS (evidence is incomplete; say which gates you accepted in the PR)")
        code = EXIT_PASSED
    else:
        print("Local CI: PASSED")
        code = EXIT_PASSED
    print(f"Logs: {log_dir.relative_to(root).as_posix()}")
    print(f"Evidence: {(Path(STATE_DIR) / LAST_RUN).as_posix()}")

    evidence = {
        "schema": 1,
        "run": run_id,
        "started": started_at,
        "commit": commit,
        "tree": tree,
        "dirty": dirty,
        "state": state,
        "exit": code,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration_s": round(elapsed, 3),
        "jobs": records,
        "not_local": [{"workflow": item.workflow, "job": item.name, "reason": item.reason}
                      for item in plan.not_local],
        "tools": {tool: tool_version(tool) for tool in sorted({tool for job in plan.jobs for tool in job.tools})},
    }
    (root / STATE_DIR).mkdir(parents=True, exist_ok=True)
    (root / STATE_DIR / LAST_RUN).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return code


# --- Evidence and the guard --------------------------------------------------------


def recorded(root: Path) -> dict[str, object] | None:
    try:
        data = json.loads((root / STATE_DIR / LAST_RUN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def evidence_note(root: Path) -> str | None:
    """A one-line warning when the recorded local run no longer describes HEAD, or None when it does."""
    data = recorded(root)
    if data is None:
        return None
    try:
        commit, tree = _git_head(root)
    except RepoctlError:
        return None
    if data.get("dirty") is True:
        return "local CI evidence is from an unverified dirty tree: commit and rerun make ci-local before relying on it"
    if data.get("commit") != commit or data.get("tree") != tree:
        return (f"local CI evidence is stale: it was recorded for {str(data.get('commit'))[:7]} "
                f"(tree {str(data.get('tree'))[:7]}), HEAD is {commit[:7]}; rerun make ci-local")
    if data.get("state") != "passed" or data.get("skipped"):
        return (f"local CI evidence is {data.get('state') or 'unknown'} "
                f"({data.get('skipped', 0)} skipped): it does not verify this tree as CI would")
    return None


def guard(root: Path) -> int:
    """Pre-push policy: opt-in per project, and it reads the record instead of running the suite."""
    plan = load_plan(root)
    if not plan.guard:
        return EXIT_PASSED  # opt-in: [ci.local] guard = true
    if _truthy(os.environ.get("CI_LOCAL_SKIP")):
        print("Local CI guard bypassed by CI_LOCAL_SKIP=1; say why in the PR.", file=sys.stderr)
        return EXIT_PASSED
    data = recorded(root)
    if data is None:
        reason = "no local CI run is recorded"
    elif data.get("dirty") is True:
        reason = "the recorded local CI run used an unverified dirty tree"
    elif data.get("state") != "passed" or data.get("skipped"):
        reason = f"the recorded local CI run is {data.get('state') or 'unknown'} ({data.get('skipped', 0)} skipped)"
    else:
        try:
            commit, tree = _git_head(root)
        except RepoctlError:
            return EXIT_PASSED
        if data.get("commit") != commit:
            reason = f"the recorded local CI run is for {str(data.get('commit'))[:7]}, HEAD is {commit[:7]}"
        elif data.get("tree") != tree:
            reason = f"the tree changed since the recorded local CI run (recorded {str(data.get('tree'))[:7]})"
        else:
            return EXIT_PASSED
    print(f"Local CI guard: {reason}.", file=sys.stderr)
    print("Push blocked: run make ci-local on this tree, or set CI_LOCAL_SKIP=1 and say why in the PR "
          "(docs/local-ci.md).", file=sys.stderr)
    return EXIT_INCOMPLETE
