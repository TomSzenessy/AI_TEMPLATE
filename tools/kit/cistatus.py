"""The CI outcome of what was pushed (issue #76).

A red run on the default branch went unnoticed for five pushes in a project built from this kit: every
local gate passed and no step read CI. `ci_status` asks `gh` for the runs of one commit; the session brief,
the `ci-red` stop/done check and `make ci-status` share it. Every failure to ask (no `gh`, no remote, offline,
inside CI itself) degrades to a state of its own instead of a finding, so it never blocks unfairly.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from .gitinfo import git

Runner = Callable[[list[str]], str]
TIMEOUT_S = 8  # the session brief waits for it once; offline it must not stall the start
RED = {"failure", "timed_out", "startup_failure"}  # cancelled or awaiting approval is not a defect of the commit


def _gh_runner(root: Path) -> Runner:
    def run(args: list[str]) -> str:
        result = subprocess.run(["gh", *args], cwd=root, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[-200:] or f"gh exited {result.returncode}")
        return result.stdout
    return run


def pushed_head(root: Path) -> str | None:
    """HEAD's full sha when its upstream contains it (it was pushed), else None."""
    sha = (git(root, "rev-parse", "HEAD") or "").strip()
    upstream = (git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") or "").strip()
    if not upstream:  # pushed without -u: the remote branch of the same name still says whether it is there
        name = (git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
        upstream = f"origin/{name}" if name and name != "HEAD" and git(root, "rev-parse", "--verify", "-q",
                                                                            f"origin/{name}") else ""
    if not sha or not upstream:
        return None
    contained = git(root, "merge-base", "--is-ancestor", sha, upstream)
    return sha if contained is not None else None


def ci_status(root: Path, sha: str | None = None, runner: Runner | None = None) -> tuple[str, str]:
    """(state, detail) for one commit's CI runs: green, red, pending, none, unpushed, or unknown."""
    if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true":
        return "unknown", "running inside CI"
    sha = sha or pushed_head(root)
    if sha is None:
        return "unpushed", "HEAD is not on its upstream yet"
    try:
        raw = (runner or _gh_runner(root))(
            ["run", "list", "--commit", sha, "--limit", "20", "--json", "workflowName,status,conclusion,url"])
        runs = json.loads(raw or "[]")
    except FileNotFoundError:
        return "unknown", "GitHub CLI (gh) is not installed"
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        return "unknown", f"cannot read CI: {error}"
    if not isinstance(runs, list) or not runs:
        return "none", f"no CI run for {sha[:7]}"
    failed = [r for r in runs if isinstance(r, dict) and r.get("status") == "completed"
              and r.get("conclusion") in RED]
    if failed:
        names = ", ".join(f"{r.get('workflowName')} ({r.get('conclusion')}) {r.get('url', '')}".strip() for r in failed[:3])
        return "red", f"CI failed on {sha[:7]}: {names}"
    if any(isinstance(r, dict) and r.get("status") != "completed" for r in runs):
        return "pending", f"CI still running on {sha[:7]}"
    return "green", f"CI passed on {sha[:7]}"


def red_findings(root: Path, since: str | None = None, runner: Runner | None = None) -> list[str]:
    """The stop/done finding: this session's pushed HEAD has a failed CI run (nothing to say otherwise)."""
    head = (git(root, "rev-parse", "HEAD") or "").strip()
    if since and head.startswith(since):
        return []  # the session committed nothing: a red run that was already there is not its to fix
    state, detail = ci_status(root, runner=runner)
    if state != "red":
        return []
    return [f"{detail}; fix it (`gh run view --log-failed`) and push again: a red default branch is never done"]
