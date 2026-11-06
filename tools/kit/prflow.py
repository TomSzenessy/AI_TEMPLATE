"""Batch finished work into one reviewed change set (#152).

`make ready` puts a finished branch on the exact tree it will merge (default
branch merged, full gate run once, one push, then `gh pr ready`). `make
integrate` merges several finished branches locally into one branch, runs the
gate once, and opens one pull request that carries every closing reference.

The commands refuse the states that make a green result meaningless: a dirty
tree, the default branch itself, a failed `make done`, a merge conflict, or a
batch with no closing issue reference.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .core import default_branch, load_project
from .gitinfo import git

CLOSING_REFERENCE = re.compile(r"(?im)^\s*(?:Fixes|Closes|Resolves)\s+#([1-9][0-9]*)\s*$")
ANY_REFERENCE = re.compile(r"#([1-9][0-9]*)\b")


def _run(root: Path, arguments: list[str]) -> int:
    try:
        return subprocess.run(arguments, cwd=root, check=False).returncode
    except OSError:
        return 127


def _capture(root: Path, arguments: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(arguments, cwd=root, check=False, capture_output=True, text=True)
    except OSError as error:
        return 127, str(error)
    return done.returncode, (done.stdout + done.stderr).strip()


def dirty(root: Path) -> bool:
    return bool((git(root, "status", "--porcelain") or "").strip())


def current_branch(root: Path) -> str:
    return (git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()


def closing_references(text: str) -> list[int]:
    """Issue numbers this commit set closes, in first-seen order."""
    seen: list[int] = []
    for match in CLOSING_REFERENCE.finditer(text):
        number = int(match.group(1))
        if number not in seen:
            seen.append(number)
    return seen


def named_references(text: str) -> list[int]:
    """Every issue number named in a commit message, for a PR body that explains the batch."""
    seen: list[int] = []
    for match in ANY_REFERENCE.finditer(text):
        number = int(match.group(1))
        if number not in seen:
            seen.append(number)
    return seen


def _merge_default(root: Path, base: str) -> tuple[int, str]:
    remotes = (git(root, "remote") or "").split()
    if "origin" not in remotes or not git(root, "rev-parse", "--verify", "-q", f"origin/{base}"):
        return 0, f"no origin/{base}; default-branch merge skipped"
    code, output = _capture(root, ["git", "fetch", "origin", base])
    if code:
        return 1, f"could not fetch origin/{base}: {output}"
    code, output = _capture(root, ["git", "merge", "--no-edit", f"origin/{base}"])
    if code:
        _run(root, ["git", "merge", "--abort"])
        return 1, f"merging origin/{base} conflicted; resolve it, then run make ready again: {output}"
    return 0, f"merged origin/{base}"


def ready(root: Path, verify=None, push=None, pr_ready=None) -> tuple[int, str]:
    """Merge the default branch, run the full gate once on that tree, push, and mark ready."""
    if dirty(root):
        return 1, "refusing: commit or stash the working tree first; `make ready` never pushes half-finished work"
    name = current_branch(root)
    base = default_branch(load_project(root))
    if not name or name == "HEAD" or name == base:
        return 1, f"refusing: {name or 'detached HEAD'} is not a finished feature branch (default is {base})"
    code, message = _merge_default(root, base)
    if code:
        return code, message
    verify = verify or (lambda path: _run(path, ["make", "--no-print-directory", "done"]))
    if verify(root):
        return 1, "refusing: make done failed on the tree that would be pushed; fix it before make ready"
    if dirty(root):
        return 1, "refusing: make done changed derived files; commit them, then run make ready again"
    push = push or (lambda path, branch_name: _run(path, ["git", "push", "-u", "origin", branch_name]))
    if push(root, name):
        return 1, "make done passed, but the one push failed; nothing else was run"
    pr_ready = pr_ready or (lambda path: _run(path, ["gh", "pr", "ready"]))
    if pr_ready(root):
        return 1, "pushed once, but there is no pull request to mark ready; open one, then run gh pr ready"
    return 0, f"ready: {name} merged {base}, passed make done once, pushed once, and is marked ready"


def integrate(root: Path, branches: list[str], verify=None, push=None, create_pr=None) -> tuple[int, str]:
    """Merge finished branches into one integration branch, gate it once, and open one PR."""
    names = [name.strip() for name in branches if name.strip()]
    if not names:
        return 1, "name the finished branches: make integrate BRANCHES='feature/a feature/b'"
    if dirty(root):
        return 1, "refusing: commit or stash the working tree first"
    base = default_branch(load_project(root))
    checkout_base = f"origin/{base}" if git(root, "rev-parse", "--verify", "-q", f"origin/{base}") else base
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = f"integrate/ci-batch-{stamp}"
    code, output = _capture(root, ["git", "checkout", "-b", target, checkout_base])
    if code:
        return 1, f"could not create {target}: {output}"
    for name in names:
        code, output = _capture(root, ["git", "merge", "--no-ff", "--no-edit", name])
        if code:
            _run(root, ["git", "merge", "--abort"])
            return 1, f"merging {name} conflicted; resolve it on {target}, then run make integrate again: {output}"
    verify = verify or (lambda path: _run(path, ["make", "--no-print-directory", "done"]))
    if verify(root):
        return 1, f"make done failed on {target}; no branch was pushed and no PR was opened"
    if dirty(root):
        return 1, f"make done changed derived files on {target}; commit them, then run make integrate again"
    log = git(root, "log", "--format=%B", f"{checkout_base}..HEAD") or ""
    closing = closing_references(log)
    if not closing:
        return 1, f"{target} is gated, but no commit carries 'Fixes #N'; add the closing references before opening a PR"
    push = push or (lambda path, branch_name: _run(path, ["git", "push", "-u", "origin", branch_name]))
    if push(root, target):
        return 1, "make done passed, but the one push failed"
    body = "Integrates finished changes:\n\n" + "\n".join(f"- {name}" for name in names)
    body += "\n\n" + "\n".join(f"Fixes #{number}" for number in closing)
    create_pr = create_pr or (lambda path, head, base_name, title, body_text: _run(path, [
        "gh", "pr", "create", "--draft", "--head", head, "--base", base_name, "--title", title, "--body", body_text]))
    if create_pr(root, target, base, f"Integrate {len(names)} finished change sets", body):
        return 1, "the integration branch is pushed, but gh pr create failed; open the PR from the printed branch"
    return 0, f"integrated {len(names)} branch(es) on {target}; one PR opened with {len(closing)} closing reference(s)"
