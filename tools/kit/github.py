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


OWNER_NAME = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"


def github_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("GH_REPO", None)
    environment.pop("GH_HOST", None)
    return environment


def _gh(root: Path | None, args: list[str], *, input: str | None = None, timeout: int = 60) -> str:
    """Run `gh` and return stdout; every failure mode becomes a RepoctlError."""
    label = " ".join(args[:2])
    try:
        result = subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=True,
            input=input,
            timeout=timeout,
            cwd=root,
            env=github_environment(),
        )
    except FileNotFoundError as error:
        raise RepoctlError("GitHub CLI (gh) is required for this command") from error
    except subprocess.TimeoutExpired as error:
        raise RepoctlError(f"gh {label} timed out") from error
    if result.returncode != 0:
        raise RepoctlError(f"gh {label} failed: {result.stderr.strip()[-300:]}")
    return result.stdout


def _gh_json(root: Path | None, args: list[str], what: str, kind: type) -> object:
    try:
        data = json.loads(_gh(root, args) or ("[]" if kind is list else "{}"))
    except json.JSONDecodeError as error:
        raise RepoctlError(f"GitHub CLI returned invalid {what} JSON") from error
    if not isinstance(data, kind):
        raise RepoctlError(f"GitHub CLI {what} must be a JSON {kind.__name__}")
    return data


def origin_target(root: Path) -> str | None:
    """owner/name of the checkout's origin remote, or None when unknown."""
    try:
        remote = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return github_target_from_remote(remote.stdout) if remote.returncode == 0 else None


def resolve_github_repo(root: Path) -> str:
    project = load_project(root)
    repository = project.get("repository", {})
    configured = repository.get("github") if isinstance(repository, dict) else None
    if configured:
        if not isinstance(configured, str) or not re.fullmatch(OWNER_NAME, configured):
            raise RepoctlError("repository.github must be an owner/name string")
        remote_target = origin_target(root)
        if remote_target and remote_target != configured:
            raise RepoctlError(
                f"repository.github conflicts with checkout origin: {configured} != {remote_target}"
            )
        return configured
    try:
        data = _gh_json(root, ["repo", "view", "--json", "nameWithOwner"], "repository", dict)
    except RepoctlError as error:
        if "invalid" in str(error) or "must be" in str(error):
            raise
        raise RepoctlError(
            "could not resolve the GitHub repository; set repository.github in project.toml"
        ) from error
    name = data.get("nameWithOwner")
    if not isinstance(name, str) or not re.fullmatch(OWNER_NAME, name):
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


def check_github_duplicates(root: Path, title: str, repository: str) -> list[dict[str, object]]:
    """Recent issues (any state), fetched without --search so the index lag cannot hide a duplicate."""
    issues = _gh_json(
        root,
        [
            "issue", "list", "--state", "all", "--limit", "200",
            "--json", "number,title,url,state,body,labels", "--repo", repository,
        ],
        "issue list",
        list,
    )
    return [issue for issue in issues if isinstance(issue, dict)]


def label_attributes(label: str) -> tuple[str, str]:
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:6].upper()
    return digest, f"Repository issue classification: {label.split(':', 1)[0]}"


def github_label_args(repository: str, label: str, *, force: bool = False) -> list[str]:
    color, description = label_attributes(label)
    args = ["label", "create", label, "--color", color, "--description", description, "--repo", repository]
    return args + ["--force"] if force else args


def existing_labels(root: Path, repository: str) -> dict[str, dict[str, object]]:
    """Existing repo labels keyed by casefolded name (one call); {} when gh cannot list them."""
    try:
        rows = _gh_json(
            root,
            ["label", "list", "--limit", "1000", "--json", "name,color,description", "--repo", repository],
            "label list",
            list,
        )
    except RepoctlError:
        return {}
    return {str(row["name"]).casefold(): row for row in rows if isinstance(row, dict) and "name" in row}


def sync_issue_labels(root: Path) -> None:
    project = load_project(root)
    if governance_profile(project) == "minimal":
        raise RepoctlError("minimal profile delegates issue labels to the host organization")
    repository = resolve_github_repo(root)
    print(f"Synchronizing issue labels in {repository}.")
    registry = load_label_registry(root, project)
    existing = existing_labels(root, repository)
    for family, values in registry.items():
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise RepoctlError(f"label family {family} must be an array of strings")
        for value in values:
            label = f"{family}:{value}"
            current = existing.get(label.casefold())
            color, description = label_attributes(label)
            if (
                current
                and str(current.get("color", "")).upper() == color
                and current.get("description") == description
            ):
                continue
            _gh(root, github_label_args(repository, label, force=True))
    print("Issue label taxonomy synchronized.")


def ensure_labels(root: Path, repository: str, labels: list[str]) -> None:
    existing = existing_labels(root, repository)
    for label in labels:
        if label.casefold() in existing:
            continue
        try:
            _gh(root, github_label_args(repository, label))
        except RepoctlError as error:
            if "already exists" not in str(error):
                raise


def create_github_issue(
    root: Path, repository: str, title: str, body: str, labels: list[str]
) -> str:
    ensure_labels(root, repository, labels)
    args = ["issue", "create", "--title", title, "--body-file", "-", "--repo", repository]
    for label in labels:
        args.extend(("--label", label))
    url = _gh(root, args, input=body).strip()
    if not re.fullmatch(r"https://github\.com/[^\s]+/issues/\d+", url):
        raise RepoctlError("GitHub CLI returned an invalid issue URL")
    return url


PATH_EXTENSIONS = (
    "py|ts|tsx|js|jsx|mjs|md|toml|json|yml|yaml|sh|go|rs|css|html|mk|txt|swift|kt|java|rb|sql|cfg|ini"
)
PATH_TOKEN = re.compile(rf"[\w.-]+/[\w./-]+|[\w-]+(?:\.[\w-]+)*\.(?:{PATH_EXTENSIONS})\b")
QUALIFIER = re.compile(r"\b(?:label|is|in|state|author|assignee|type|no|sort|repo|org|user):\S*", re.I)


def strip_qualifiers(value: str) -> str:
    """Drop GitHub search qualifiers (label:, is:, ...) so text can never act as a query."""
    return " ".join(QUALIFIER.sub(" ", value).split())


def path_tokens(text: str) -> set[str]:
    """Path-shaped tokens only: dir/file paths or filenames with a code/doc extension."""
    text = re.sub(r"https?://\S+", " ", text)
    tokens = (match.strip(".,;:()[]`'\"").casefold() for match in PATH_TOKEN.findall(text))
    return {token for token in tokens if len(token) > 2}


def issue_topics(issue: dict[str, object]) -> set[str]:
    topics = set()
    for label in issue.get("labels") or []:
        name = label.get("name") if isinstance(label, dict) else label
        if isinstance(name, str) and name.casefold().startswith("topic:"):
            topics.add(name.split(":", 1)[1].casefold())
    return topics


def duplicate_result_matches(
    issue: dict[str, object], title: str, topic: str, where: str
) -> bool:
    if normalized_title(str(issue.get("title", ""))) == normalized_title(strip_qualifiers(title)):
        return True
    if topic and topic.strip().casefold() in issue_topics(issue):
        return True
    text = f"{issue.get('title', '')} {issue.get('body', '')}"
    return len(path_tokens(where) & path_tokens(text)) >= 2


def github_target_from_remote(value: str) -> str | None:
    value = value.strip()
    if value.startswith("git@github.com:"):
        match = re.fullmatch(rf"git@github\.com:({OWNER_NAME}?)(?:\.git)?", value)
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
        not isinstance(configured, str) or not re.fullmatch(OWNER_NAME, configured)
    ):
        return False
    remote_target = origin_target(root)
    if configured and remote_target and configured != remote_target:
        return False
    target = configured or remote_target
    # Readiness is a local evidence gate. Live GitHub API confirmation belongs
    # to a separate privileged job/evidence record and must not receive a token
    # in general repository verification.
    return isinstance(target, str) and bool(target)


TOPIC_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")


def declared_metadata(project: dict[str, object]) -> dict[str, object]:
    """Repository metadata declared in project.toml [repository]."""
    repository = project.get("repository", {})
    repository = repository if isinstance(repository, dict) else {}
    description = str(repository.get("description", "")).strip()
    topics = repository.get("topics", [])
    if not isinstance(topics, list) or not all(isinstance(t, str) and TOPIC_PATTERN.fullmatch(t) for t in topics):
        raise RepoctlError("repository.topics must be lowercase kebab-case strings of at most 50 characters")
    if len(description) > 350 or len(topics) > 20:
        raise RepoctlError("repository.description is limited to 350 characters and topics to 20")
    return {"description": description, "topics": sorted(topics), "is_template": bool(repository.get("is_template", False))}


def live_metadata(repository: str) -> dict[str, object] | None:
    try:
        data = _gh_json(
            None, ["repo", "view", repository, "--json", "description,repositoryTopics,isTemplate"],
            "repository", dict, 
        )
    except RepoctlError as error:
        if "invalid" in str(error):
            raise RepoctlError("gh returned invalid repository JSON") from error
        return None
    topics = [item.get("name") for item in (data.get("repositoryTopics") or []) if isinstance(item, dict)]
    return {"description": (data.get("description") or "").strip(), "topics": sorted(topics), "is_template": bool(data.get("isTemplate"))}


def metadata_drift(root: Path) -> list[str]:
    """Read-only comparison of GitHub metadata with project.toml (empty when unknowable)."""
    project = load_project(root)
    repository = project.get("repository", {})
    target = repository.get("github") if isinstance(repository, dict) else None
    if not target:
        return []
    declared = declared_metadata(project)
    if not declared["description"] and not declared["topics"]:
        return []  # nothing declared yet (fresh project): never report or clear
    live = live_metadata(str(target))
    if live is None:
        return []
    return [
        f"GitHub {field} differs from project.toml (run `make github-sync`)"
        for field in ("description", "topics", "is_template")
        if live[field] != declared[field]
    ]


def sync_repository_metadata(root: Path) -> list[str]:
    """Apply project.toml [repository] description, topics, and template flag to GitHub."""
    project = load_project(root)
    declared = declared_metadata(project)
    repository = resolve_github_repo(root)
    live = live_metadata(repository)
    if live is None:
        raise RepoctlError(f"cannot read {repository} with gh; authenticate the GitHub CLI first")
    base = ["repo", "edit", repository]
    command = list(base)
    if declared["description"] and live["description"] != declared["description"]:
        command += ["--description", str(declared["description"])]
    for topic in sorted(set(declared["topics"]) - set(live["topics"])):
        command += ["--add-topic", topic]
    for topic in sorted(set(live["topics"]) - set(declared["topics"])):
        command += ["--remove-topic", topic]
    if live["is_template"] != declared["is_template"]:
        command += [f"--template={'true' if declared['is_template'] else 'false'}"]
    if command == base:
        return []
    _gh(root, command)
    return [part for part in command[len(base):] if part.startswith("--")]
