"""GitHub CLI adapter: repository resolution, labels, filing, and duplicate search."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from .core import RepoctlError, ensure_inside_root, governance_profile, load_project


def github_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("GH_REPO", None)
    environment.pop("GH_HOST", None)
    return environment


def resolve_github_repo(root: Path) -> str:
    project = load_project(root)
    repository = project.get("repository", {})
    configured = repository.get("github") if isinstance(repository, dict) else None
    if configured:
        if not isinstance(configured, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", configured
        ):
            raise RepoctlError("repository.github must be an owner/name string")
        try:
            remote = subprocess.run(
                ["git", "-C", str(root), "remote", "get-url", "origin"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            remote = None
        if remote is not None and remote.returncode == 0:
            remote_target = github_target_from_remote(remote.stdout)
            if remote_target and remote_target != configured:
                raise RepoctlError(
                    f"repository.github conflicts with checkout origin: {configured} != {remote_target}"
                )
        return configured
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=root,
            env=github_environment(),
        )
    except FileNotFoundError as error:
        raise RepoctlError("GitHub CLI (gh) is required to resolve the target repository") from error
    except subprocess.TimeoutExpired as error:
        raise RepoctlError("GitHub repository resolution timed out") from error
    if result.returncode != 0:
        raise RepoctlError(
            "could not resolve the GitHub repository; set repository.github in project.toml"
        )
    try:
        data = json.loads(result.stdout or "{}")
        name = data.get("nameWithOwner") if isinstance(data, dict) else None
    except json.JSONDecodeError as error:
        raise RepoctlError("GitHub CLI returned invalid repository JSON") from error
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
        raise RepoctlError("GitHub CLI returned an invalid owner/name repository")
    return name


def load_label_registry(root: Path, project: dict[str, object] | None = None) -> dict[str, list[str]]:
    project = project or load_project(root)
    governance = project.get("governance", {})
    configured = governance.get("label_registry", ".github/issue-labels.json") if isinstance(governance, dict) else ".github/issue-labels.json"
    if not isinstance(configured, str) or not configured.strip():
        raise RepoctlError("governance.label_registry must be a repository-relative path")
    registry_path = ensure_inside_root(root, root / configured, "label registry")
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RepoctlError(f"configured label registry is missing: {configured}") from error
    except json.JSONDecodeError as error:
        raise RepoctlError(f"configured label registry is invalid: {error}") from error
    if not isinstance(registry, dict):
        raise RepoctlError("issue label registry must be a JSON object")
    return registry


def normalized_title(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE))


def check_github_duplicates(
    root: Path, title: str, repository: str, search_terms: tuple[str, ...] = ()
) -> list[dict[str, object]]:
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "all",
                "--search",
                " ".join((title,) + search_terms),
                "--json",
                "number,title,url,state,body",
                "--limit",
                "100",
                "--repo",
                repository,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=root,
            env=github_environment(),
        )
    except FileNotFoundError as error:
        raise RepoctlError("GitHub CLI (gh) is required to file issues") from error
    except subprocess.TimeoutExpired as error:
        raise RepoctlError("GitHub duplicate search timed out") from error
    if result.returncode != 0:
        raise RepoctlError(f"GitHub duplicate search failed: {result.stderr.strip()}")
    try:
        issues = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as error:
        raise RepoctlError("GitHub CLI returned invalid issue search JSON") from error
    if not isinstance(issues, list):
        raise RepoctlError("GitHub CLI issue search must return a list")
    return [issue for issue in issues if isinstance(issue, dict)]


def github_label_command(repository: str, label: str) -> list[str]:
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:6].upper()
    family = label.split(":", 1)[0]
    return [
        "gh",
        "label",
        "create",
        label,
        "--color",
        digest,
        "--description",
        f"Repository issue classification: {family}",
        "--repo",
        repository,
        "--force",
    ]


def sync_issue_labels(root: Path) -> None:
    project = load_project(root)
    if governance_profile(project) == "minimal":
        raise RepoctlError("minimal profile delegates issue labels to the host organization")
    repository = resolve_github_repo(root)
    print(f"Synchronizing issue labels in {repository}.")
    registry = load_label_registry(root, project)
    for family, values in registry.items():
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise RepoctlError(f"label family {family} must be an array of strings")
        for value in values:
            label = f"{family}:{value}"
            command = github_label_command(repository, label)
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=root,
                    env=github_environment(),
                )
            except FileNotFoundError as error:
                raise RepoctlError("GitHub CLI (gh) is required to sync labels") from error
            except subprocess.TimeoutExpired as error:
                raise RepoctlError(f"GitHub label sync timed out for {label}") from error
            if result.returncode != 0:
                raise RepoctlError(f"GitHub label sync failed for {label}: {result.stderr.strip()}")
    print("Issue label taxonomy synchronized.")


def create_github_issue(
    root: Path, repository: str, title: str, body: str, labels: list[str]
) -> str:
    for label in labels:
        try:
            ensure_result = subprocess.run(
                github_label_command(repository, label),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=root,
                env=github_environment(),
            )
        except FileNotFoundError as error:
            raise RepoctlError("GitHub CLI (gh) is required to file issues") from error
        except subprocess.TimeoutExpired as error:
            raise RepoctlError(f"GitHub label creation timed out for {label}") from error
        if ensure_result.returncode != 0:
            raise RepoctlError(
                f"GitHub label creation failed for {label}: {ensure_result.stderr.strip()}"
            )
    command = [
        "gh",
        "issue",
        "create",
        "--title",
        title,
        "--body-file",
        "-",
        "--repo",
        repository,
    ]
    for label in labels:
        command.extend(("--label", label))
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            input=body,
            timeout=60,
            cwd=root,
            env=github_environment(),
        )
    except FileNotFoundError as error:
        raise RepoctlError("GitHub CLI (gh) is required to file issues") from error
    except subprocess.TimeoutExpired as error:
        raise RepoctlError("GitHub issue creation timed out") from error
    if result.returncode != 0:
        raise RepoctlError(f"GitHub issue creation failed: {result.stderr.strip()}")
    url = result.stdout.strip()
    if not re.fullmatch(r"https://github\.com/[^\s]+/issues/\d+", url):
        raise RepoctlError("GitHub CLI returned an invalid issue URL")
    return url


def duplicate_result_matches(
    issue: dict[str, object], title: str, topic: str, where: str
) -> bool:
    if normalized_title(str(issue.get("title", ""))) == normalized_title(title):
        return True
    issue_title = str(issue.get("title", ""))
    text = " ".join(
        str(issue.get(field, ""))
        for field in ("title", "body")
    ).casefold()
    if topic and topic.casefold() in issue_title.casefold():
        return True
    path_terms = []
    for token in where.split():
        cleaned = token.strip(".,;()[]")
        if ("/" in cleaned or "." in cleaned) and len(cleaned) > 2:
            path_terms.append(cleaned)
    return any(term.casefold() in text for term in path_terms)


def github_target_from_remote(value: str) -> str | None:
    value = value.strip()
    if value.startswith("git@github.com:"):
        match = re.fullmatch(r"git@github\.com:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", value)
        return match.group(1) if match else None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https", "ssh"} or (parsed.hostname or "").lower() != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
        return None
    return f"{parts[0]}/{parts[1][:-4] if parts[1].endswith('.git') else parts[1]}"


def github_target_configured(root: Path, project: dict[str, object]) -> bool:
    repository = project.get("repository", {})
    configured = repository.get("github") if isinstance(repository, dict) else None
    if configured is not None and (
        not isinstance(configured, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", configured)
    ):
        return False
    remote_target: str | None = None
    try:
        remote = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        remote_target = None
    else:
        if remote.returncode == 0:
            remote_target = github_target_from_remote(remote.stdout)
    if configured and remote_target and configured != remote_target:
        return False
    target = configured or remote_target
    # Readiness is a local evidence gate. Live GitHub API confirmation belongs
    # to a separate privileged job/evidence record and must not receive a token
    # in general repository verification.
    return isinstance(target, str) and bool(target)
