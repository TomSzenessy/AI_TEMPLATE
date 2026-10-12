"""Work stays shared: fetch at the start, push before stopping, pull before a run others rely on (issue #90).

AGENTS.md said "pull at start, push each step", but nothing enforced it, and a team member once measured and
reported a result on code nobody else had. The session brief fetches (bounded, never in CI) and fast-forwards a clean tree that is
only behind; the stop gate names this session's uncommitted and unpushed work; `make pull-first` is the one call a
script makes before a run whose result others rely on (a release build, a deploy, a benchmark). Without a remote there is nothing to share, so none
of this says anything.
"""

from __future__ import annotations

import os
from pathlib import Path

from .gitinfo import changed_paths, git, run_git

FETCH_S = 10  # the brief waits for it once; offline it must not stall the start
PULLED = 3  # pull-first's exit code when it brought new commits: restart the run on the new code


def _off() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"


def _has_remote(root: Path) -> bool:
    return bool((git(root, "remote") or "").strip())


def _upstream(root: Path) -> str | None:
    found = (git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") or "").strip()
    return found or None


def fetch(root: Path) -> bool:
    """Fetch the upstream's remote within FETCH_S; False offline, without an upstream, or in CI."""
    upstream = _upstream(root)
    if _off() or upstream is None:
        return False
    prompt = os.environ.get("GIT_TERMINAL_PROMPT")
    os.environ["GIT_TERMINAL_PROMPT"] = "0"  # a credential prompt would wait out the timeout unseen
    try:
        done = run_git(root, "-c", "credential.interactive=false", "fetch", "-q", upstream.split("/", 1)[0],
                       timeout=FETCH_S)
    finally:
        if prompt is None:
            os.environ.pop("GIT_TERMINAL_PROMPT", None)
        else:
            os.environ["GIT_TERMINAL_PROMPT"] = prompt
    return done is not None and done.returncode == 0


def ahead_behind(root: Path) -> tuple[int, int] | None:
    """(commits HEAD has that its upstream lacks, commits the upstream has that HEAD lacks); None without one."""
    if _upstream(root) is None:
        return None
    counts = (git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}") or "").split()
    return (int(counts[0]), int(counts[1])) if len(counts) == 2 and all(c.isdigit() for c in counts) else None


def brief_lines(root: Path, pull: bool = True) -> list[str]:
    """The session brief's sync facts: fetch, then (with `pull`) fast-forward a clean tree that is strictly behind."""
    if not fetch(root):
        return []
    counts = ahead_behind(root)
    if counts is None:
        return []
    ahead, behind = counts
    if pull and behind and not ahead and not changed_paths(root):
        merged = run_git(root, "merge", "--ff-only", "-q", "@{u}")
        if merged is not None and merged.returncode == 0:
            return [f"pulled {behind} new commit(s) from upstream (fast-forward): read them before new work"]
    lines = []
    if behind:
        lines.append(f"{behind} commit(s) behind upstream: `git pull --rebase --autostash` before new work")
    if ahead:
        lines.append(f"{ahead} local commit(s) not pushed: push them, or say why they stay local")
    return lines


def unpushed_findings(root: Path, session_paths: list[str] | None, since: str | None) -> list[str]:
    """The stop gate's push rule: this session's uncommitted paths and the commits it made but did not push."""
    if _off() or not _has_remote(root):
        return []
    found = []
    dirty = sorted(set(session_paths or ()) & set(changed_paths(root)))
    if dirty:
        found.append(f"uncommitted work of this session ({', '.join(dirty[:5])}{' …' if len(dirty) > 5 else ''}): "
                     "commit and push it, or tell the user what stays uncommitted and why")
    head = (git(root, "rev-parse", "HEAD") or "").strip()
    if since and head and not head.startswith(since):
        counts = ahead_behind(root)
        if counts is None and (git(root, "symbolic-ref", "-q", "HEAD") or "").strip():
            found.append("this session's commits are on a branch without upstream: `git push -u origin HEAD`")
        elif counts is None:
            found.append("this session committed on a detached HEAD: `git switch -c <branch>`, then push it")
        elif counts[0]:
            found.append(f"{counts[0]} commit(s) not pushed: push them (teammates and CI see only what is pushed)")
    return found


def pull_first(root: Path, check_only: bool = False) -> tuple[int, str]:
    """Before a run others rely on: (exit code, message). 0 run as is, PULLED new code was pulled (restart on it),
    1 refuse (dirty tree, unpushed commits, diverged, or the upstream cannot be read)."""
    if _off():
        return 0, "inside CI: the checked-out commit is the one that runs"
    if changed_paths(root):
        return 1, "uncommitted changes: commit and push first, so the result names a commit others have"
    if _upstream(root) is None:
        return 1, "no upstream branch: `git push -u origin HEAD` first"
    if not fetch(root):
        return 1, "cannot fetch the upstream (offline?): a run on possibly stale code is refused"
    counts = ahead_behind(root)
    if counts is None:
        return 1, "cannot compare with the upstream"
    ahead, behind = counts
    if ahead and behind:
        return 1, f"diverged ({ahead} local, {behind} upstream): `git pull --rebase`, rerun the tests, push"
    if ahead:
        return 1, f"{ahead} commit(s) not pushed: push first, so the result names a commit others have"
    if not behind:
        return 0, f"current with the upstream at {(git(root, 'rev-parse', '--short', 'HEAD') or '').strip()}"
    if check_only:
        return 1, f"{behind} new commit(s) upstream (check only: nothing pulled)"
    merged = run_git(root, "merge", "--ff-only", "-q", "@{u}")
    if merged is None or merged.returncode != 0:
        return 1, "fast-forward failed: pull by hand and rerun the tests"
    return PULLED, f"pulled {behind} new commit(s): restart the run on the new code"
