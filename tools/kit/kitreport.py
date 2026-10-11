"""Projects improve the template they came from (issue #88).

A project that changes a kit file (a file `tools/kit-lock.json` lists) found a kit bug or a better way. Fixing it
only in the project leaves every other project with the old version, so the change is reported upstream:
`make kit-report` files an issue on `[template].source` (same contract, labels and duplicate check as
`make issue`), and the `kit-upstream` gate check holds `make done` and the stop gate until each changed kit file
is reported or recorded as project-specific (`REASON="..."`). In the template itself there is no lock, so
nothing is asked.
"""

from __future__ import annotations

import json
from pathlib import Path

from .core import RepoctlError, ensure_inside_root, load_project
from .gitinfo import git
from .kitlock import digest, project_path, read_lock

RECORD = ".agent/kit-reports.json"  # ignored: which kit paths this checkout already reported or explained


def _recorded(root: Path) -> dict[str, str]:
    try:
        data = json.loads((root / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _record(root: Path, paths: list[str], note: str) -> None:
    data = _recorded(root)
    data.update({path: note for path in paths})
    target = ensure_inside_root(root, root / RECORD, "kit report record")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


def changed_kit_paths(root: Path, paths: list[str] | None = None) -> list[str]:
    """Kit files whose content differs from what the kit shipped (the lock's hash), among `paths` if given.
    None in the template itself: it has no lock."""
    try:
        lock = read_lock(root)
    except RepoctlError:
        return []
    files, moved = lock.get("files", {}), lock.get("moved", {})
    if not isinstance(files, dict):
        return []
    # A merged file (AGENTS.md after adopt), one the project kept as its own, and the Makefile (regenerated per
    # project as kit.mk with its renames) are the project's by design, not kit edits to report.
    own = {"Makefile", *(lock.get("merged") or {}), *(lock.get("kept") or {})}
    moved = moved if isinstance(moved, dict) else {}
    local = {path: project_path(root, path, moved) for path in files if path not in own}
    wanted = local if paths is None else {k: v for k, v in local.items() if k in paths or v in paths}
    return sorted(v for k, v in wanted.items() if (root / v).is_file() and digest(root / v) != files[k])


def upstream_findings(root: Path, paths: list[str]) -> list[str]:
    owed = [path for path in changed_kit_paths(root, paths) if path not in _recorded(root)]
    if not owed:
        return []
    return [f"changed kit file(s) {', '.join(owed[:5])}{' …' if len(owed) > 5 else ''}: report the improvement to "
            "the template with `make kit-report TITLE=... BODY=... TYPE=bug|enhancement PRIORITY=... TOPIC=...`, or "
            "record why it is project-specific with `make kit-report REASON=\"...\"`"]


def template_repository(root: Path) -> str:
    from .github import github_target_from_remote
    template = load_project(root).get("template", {})
    source = str(template.get("source", "")) if isinstance(template, dict) else ""
    target = github_target_from_remote(source) if source else None
    if not target:
        raise RepoctlError("[template].source names no GitHub repository to report to")
    return target


def report(root: Path, args) -> str:
    """File the kit report upstream (or record a project-specific reason) for the kit files changed here."""
    paths = [path for path in changed_kit_paths(root) if path not in _recorded(root)]
    if args.reason:
        _record(root, paths, f"project-specific: {args.reason}")
        return f"Recorded {len(paths)} kit path(s) as project-specific."
    missing = [flag for flag in ("title", "body_file", "type", "priority", "topic") if not getattr(args, flag)]
    if missing:
        raise RepoctlError("kit-report needs " + ", ".join("--" + flag.replace("_", "-") for flag in missing)
                           + ' (or --reason "why it is project-specific")')
    from .github import origin_target
    from .issues import file_issue
    body_path = ensure_inside_root(root, root / args.body_file, "kit report body")
    origin = origin_target(root) or "a project without a GitHub remote"
    head = (git(root, "rev-parse", "--short", "HEAD") or "").strip()
    footer = (f"\n\nReported from {origin} @ {head} by `make kit-report`; kit file(s): "
              f"{', '.join(paths) or 'none named'}.\n")
    staged = ensure_inside_root(root, root / ".agent" / "bodies" / "kit-report.md", "kit report body")
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(body_path.read_text(encoding="utf-8") + footer, encoding="utf-8")
    url = file_issue(root, args.title, staged.relative_to(root), args.type, args.priority, "repo", args.topic,
                     "triage", None, None, False, None, repository=template_repository(root))
    _record(root, paths, f"reported: {url}")
    return url
