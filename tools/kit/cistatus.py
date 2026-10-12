"""The CI outcome of what was pushed (issue #76).

A red run on the default branch went unnoticed for five pushes in a project built from this kit: every
local gate passed and no step read CI. `ci_status` targets one commit for `ci-red` and `make ci-status`;
the brief classifies HEAD/default from one bounded diagnostic snapshot. Both share event classification.
Every failure to ask (no `gh`, no remote, offline,
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
TIMEOUT_S = 8  # targeted manual/gate queries; the diagnostic brief has a shorter bound
RED = {"failure", "timed_out", "startup_failure"}  # cancelled or awaiting approval is not a defect of the commit


def _gh_runner(root: Path, timeout_s: float = TIMEOUT_S) -> Runner:
    def run(args: list[str]) -> str:
        result = subprocess.run(["gh", *args], cwd=root, capture_output=True, text=True, timeout=timeout_s, check=False)
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


CACHE = ".agent/ci-status.json"  # ignored; one gh call per commit, not per start, done and stop (#83)
CACHE_SCOPE = "commit-verification-v1"  # pre-#97 answers included unrelated issue events; never reuse them
FINAL = {"green"}  # red is asked again: a re-run on the same commit can turn it green
GREEN_S = 86400  # a green answer is asked again after a day: a later re-run or new workflow can turn it red (#85)
RETRY_S = 300  # pending, none, or unknown (offline) is asked again after this long, not on every gate


def _cached(root: Path, sha: str) -> tuple[str, str] | None:
    import time
    try:
        entry = json.loads((root / CACHE).read_text(encoding="utf-8")).get(sha)
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(entry, list) or len(entry) != 4 or entry[3] != CACHE_SCOPE:
        return None
    state, detail, at, _ = entry
    try:
        age = time.time() - float(at)
    except (TypeError, ValueError):
        return None  # a damaged entry is asked again, never trusted
    return (state, detail) if age < (GREEN_S if state in FINAL else RETRY_S) else None


def _store(root: Path, sha: str, result: tuple[str, str]) -> None:
    import time
    path = root / CACHE
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        data = data if isinstance(data, dict) else {}
        data[sha] = [*result, time.time(), CACHE_SCOPE]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(list(data.items())[-50:])), encoding="utf-8")
    except (OSError, ValueError):
        pass  # a cache that cannot be written only costs another call


def ci_status(root: Path, sha: str | None = None, runner: Runner | None = None,
              fresh: bool = False) -> tuple[str, str]:
    """(state, detail) for one commit's CI runs: green, red, pending, inconclusive, none, unpushed, or unknown.
    With the real `gh` (no `runner`) the answer is cached per commit in CACHE."""
    if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true":
        return "unknown", "running inside CI"
    sha = sha or pushed_head(root)
    if sha is None:
        return "unpushed", "HEAD is not on its upstream yet"
    if runner is None and (hit := _cached(root, sha)) is not None and not (fresh and hit[0] != "green"):
        return hit
    result = _ask(root, sha, runner)
    if runner is None:
        _store(root, sha, result)
    return result


def _ask(root: Path, sha: str, runner: Runner | None) -> tuple[str, str]:
    try:
        raw = (runner or _gh_runner(root))(
            ["run", "list", "--commit", sha, "--limit", "100", "--json", "workflowName,status,conclusion,url,event"])
        runs = json.loads(raw or "[]")
    except FileNotFoundError:
        return "unknown", "GitHub CLI (gh) is not installed"
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        return "unknown", f"cannot read CI: {error}"
    return _classify(sha, runs)


def _classify(sha: str, runs: object) -> tuple[str, str]:
    """The shared commit-verification classification for targeted and brief queries."""
    if isinstance(runs, list):
        # Issue validation uses the default-branch SHA, but does not verify that commit (#97).
        # Keep every other event (including missing metadata) so real CI failures stay visible.
        runs = [r for r in runs if not isinstance(r, dict) or r.get("event") not in {"issues", "issue_comment"}]
    if not isinstance(runs, list) or not runs:
        return "none", f"no applicable commit verification run for {sha[:7]}"
    failed = [r for r in runs if isinstance(r, dict) and r.get("status") == "completed"
              and r.get("conclusion") in RED]
    if failed:
        names = ", ".join(f"{r.get('workflowName')} ({r.get('conclusion')}) {r.get('url', '')}".strip() for r in failed[:3])
        return "red", f"CI failed on {sha[:7]}: {names}"
    if any(isinstance(r, dict) and r.get("status") != "completed" for r in runs):
        return "pending", f"CI still running on {sha[:7]}"
    if not any(isinstance(r, dict) and r.get("conclusion") == "success" for r in runs):
        return "inconclusive", f"no CI run succeeded on {sha[:7]} (cancelled, skipped, or awaiting approval)"
    return "green", f"CI passed on {sha[:7]}"


BRIEF_CACHE = ".agent/ci-brief.json"  # diagnostic snapshot only; never feeds targeted gate/manual results
BRIEF_TIMEOUT_S = 2


def brief_ci_lines(root: Path, session_id: str | None = None, runner: Runner | None = None) -> list[str]:
    """HEAD/default conclusions from one bounded run list, cached by existing hook session and target pair."""
    import time
    from .core import RepoctlError, default_branch, load_project
    if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true":
        return ["CI brief: unknown (running inside CI)"]
    head = (git(root, "rev-parse", "HEAD") or "").strip()
    pushed = pushed_head(root)
    try:
        default = default_branch(load_project(root), fallback=None)
    except (RepoctlError, OSError):
        default = None
    # No main/master guess: only an explicitly configured branch and its actual local remote ref.
    default_sha = (git(root, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{default}^{{commit}}") or "").strip() if default else ""
    # Only the current invocation owns this identity; an unwritable baseline may belong to an older host.
    session = session_id if isinstance(session_id, str) and session_id and session_id != "local" else None
    key = [CACHE_SCOPE, session, head, pushed, default, default_sha]
    path = root / BRIEF_CACHE
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - float(cached["at"])
        lines = cached["lines"]
        if (cached["key"] == key and isinstance(lines, list) and len(lines) == 2
                and all(isinstance(line, str) for line in lines) and age >= 0
                and (session is not None or age < RETRY_S)):
            return lines
    except (OSError, ValueError, TypeError, KeyError):
        pass
    results = {}
    targets = {sha for sha in (pushed, default_sha) if sha}
    if targets:
        try:
            raw = (runner or _gh_runner(root, timeout_s=BRIEF_TIMEOUT_S))(
                ["run", "list", "--limit", "100", "--json", "workflowName,status,conclusion,url,event,headSha"])
            runs = json.loads(raw or "[]")
            if not isinstance(runs, list):
                raise ValueError("run list is not an array")
            results = {sha: _classify(sha, [r for r in runs if isinstance(r, dict) and r.get("headSha") == sha])
                       for sha in targets}
        except (FileNotFoundError, RuntimeError, OSError, subprocess.TimeoutExpired, ValueError, TypeError) as error:
            results = {sha: ("unknown", f"cannot read CI: {error}") for sha in targets}
    head_result = results.get(pushed, ("unpushed", "HEAD is not on its upstream yet")) if head else ("unknown", "cannot resolve HEAD")
    default_result = results.get(default_sha, ("unknown", "cannot resolve configured default-branch remote ref"))
    lines = [f"HEAD: {head_result[0]} — {head_result[1]}",
             f"default branch {default or '(unconfigured)'} (as of the last fetch): {default_result[0]} — {default_result[1]}"]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"key": key, "at": time.time(), "lines": lines}), encoding="utf-8")
    except OSError:
        pass  # an unwritable cache costs another bounded query, never changes the verdict
    return lines


def red_findings(root: Path, since: str | None = None, runner: Runner | None = None) -> list[str]:
    """The stop/done finding: this session's pushed HEAD has a failed CI run (nothing to say otherwise)."""
    head = (git(root, "rev-parse", "HEAD") or "").strip()
    if since and head.startswith(since):
        return []  # the session committed nothing: a red run that was already there is not its to fix
    state, detail = ci_status(root, runner=runner, fresh=True)  # a gate never blocks on a cached red
    if state != "red":
        return []
    return [f"{detail}; fix it (`gh run view --log-failed`) and push, or re-run a flaky workflow: red is never done"]
