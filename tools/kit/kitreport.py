"""Projects improve the template they came from (issue #88).

A project that changes a kit file (a file `tools/kit-lock.json` lists) found a kit bug or a better way. Fixing it
only in the project leaves every other project with the old version, so the change is reported upstream:
`make kit-report` writes only a local draft (ignored `.agent/kit-reports/`). The owner reviews it and uses
`make kit-publish` to file it on `[template].source` with the same contract, labels and duplicate check as
`make issue`. Drafting sends nothing; the tooling never appends the project's repository or commit. User-authored text needs review. The `kit-upstream`
gate check holds `make done` and the stop gate until each changed kit file is drafted, reported, or recorded as
project-specific (`REASON="..."`). In the template itself there is no lock, so nothing is asked.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from .core import RepoctlError, ensure_inside_root, load_project
from .kitlock import digest, project_path, read_lock

RECORD = ".agent/kit-reports.json"  # ignored: which kit file versions this checkout drafted, reported or explained
DRAFTS = ".agent/kit-reports"
UPSTREAM_DRAFTS = ".agent/upstream-reports"  # ignored (.agent/)


def _recorded(root: Path) -> dict[str, str]:
    try:
        data = json.loads((root / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _key(root: Path, path: str) -> str:
    """One kit file version: a later, different edit of a recorded path is asked about again."""
    return f"{path}@{digest(root / path)[:16]}" if (root / path).is_file() else f"{path}@deleted"


def _record(root: Path, paths: list[str], note: str) -> None:
    data = _recorded(root)
    data.update({_key(root, path): note for path in paths})
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
    # A deleted kit file is a change too: the template may need to know it is not wanted.
    return sorted(v for k, v in wanted.items() if not (root / v).is_file() or digest(root / v) != files[k])


def _owed(root: Path, paths: list[str] | None = None) -> list[str]:
    recorded = _recorded(root)
    return [path for path in changed_kit_paths(root, paths) if _key(root, path) not in recorded]


def upstream_findings(root: Path, paths: list[str]) -> list[str]:
    owed = _owed(root, paths)
    if not owed:
        return []
    return [f"changed kit file(s) {', '.join(owed[:5])}{' …' if len(owed) > 5 else ''}: draft a report for the "
            "template with `make kit-report TITLE=... BODY=... TYPE=bug|enhancement PRIORITY=... TOPIC=...` (local; the "
            "owner files it with `make kit-publish`), or record why it is project-specific (a hand-merged kit update "
            "included) with `make kit-report REASON=\"...\"`"]


def template_repository(root: Path) -> str:
    from .github import github_target_from_remote
    template = load_project(root).get("template", {})
    source = str(template.get("source", "")) if isinstance(template, dict) else ""
    target = github_target_from_remote(source) if source else None
    if not target:
        raise RepoctlError("[template].source names no GitHub repository to report to")
    return target


def report(root: Path, args) -> str:
    """Draft the kit report for the template (nothing is sent), or record a project-specific reason."""
    upstream = getattr(args, "upstream", None)
    if isinstance(upstream, str) and upstream:
        return upstream_draft(root, args)
    paths = _owed(root)
    if args.reason:
        _record(root, paths, f"project-specific: {args.reason}")
        return f"Recorded {len(paths)} kit path(s) as project-specific."
    missing = [flag for flag in ("title", "body_file", "type", "priority", "topic") if not getattr(args, flag)]
    if missing:
        raise RepoctlError("kit-report needs " + ", ".join("--" + flag.replace("_", "-") for flag in missing)
                           + ' (or --reason "why it is project-specific")')
    body_path = ensure_inside_root(root, root / args.body_file, "kit report body")
    version = str(read_lock(root).get("kit_version", "unknown"))[:12]
    # Never the project's repository or commit: the template may be public while the project is not.
    footer = (f"\n\nReported by `make kit-report` from a project on kit {version}; kit file(s): "
              f"{', '.join(paths) or 'none named'}.\n")
    slug = "".join(ch if ch.isalnum() else "-" for ch in args.topic.lower()).strip("-") or "report"
    draft = ensure_inside_root(root, root / DRAFTS / f"{slug}.md", "kit report draft")
    number = 2
    while draft.exists():  # a second report on the same topic never overwrites the first draft
        draft = draft.with_name(f"{slug}-{number}.md")
        number += 1
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(body_path.read_text(encoding="utf-8") + footer, encoding="utf-8")
    relative = draft.relative_to(root)
    _record(root, paths, f"drafted: {relative}")
    return (f"Drafted {relative} for {template_repository(root)} (nothing was sent). The owner reviews it and files it "
            f"with: make kit-publish TITLE=\"{args.title}\" BODY={relative} TYPE={args.type} PRIORITY={args.priority} "
            f"TOPIC={args.topic}")


def upstream_draft(root: Path, args) -> str:
    """Local draft for an upstream repository (#131). No network, no gh; the owner files it by hand."""
    from .upstream import _pick
    entry = _pick(root, args.upstream)[0]
    if not args.title or not args.body_file:
        raise RepoctlError("kit-report UPSTREAM=<id> needs TITLE=\"...\" and BODY=path")
    body_path = ensure_inside_root(root, root / args.body_file, "upstream report body")
    slug = "".join(ch if ch.isalnum() else "-" for ch in args.title.lower()).strip("-")[:40] or "report"
    draft = ensure_inside_root(root, root / UPSTREAM_DRAFTS / f"{entry['id']}-{slug}.md", "upstream report draft")
    draft.parent.mkdir(parents=True, exist_ok=True)
    relative = draft.relative_to(root)
    draft.write_text(
        f"# {args.title}\n\nRepository: {entry['repo']}\nPinned revision: {entry['revision']}\n\n"
        f"{body_path.read_text(encoding='utf-8')}\n\n---\nDraft only; nothing was sent. The owner files it with:\n"
        f"gh issue create -R {entry['repo']} --title {shlex.quote(args.title)} --body-file {shlex.quote(str(relative))}\n", encoding="utf-8")
    return f"Drafted {relative} for {entry['repo']}@{entry['revision'][:7]} (nothing was sent; the owner files it)."


def publish(root: Path, args) -> str:
    """File a reviewed draft on the template repository: the owner's step (Claude Code asks before running it)."""
    missing = [flag for flag in ("title", "body_file", "type", "priority", "topic") if not getattr(args, flag)]
    if missing:
        raise RepoctlError("kit-publish needs " + ", ".join("--" + flag.replace("_", "-") for flag in missing))
    draft = ensure_inside_root(root, root / args.body_file, "kit report draft")
    if not draft.resolve().is_relative_to((root / DRAFTS).resolve()):
        raise RepoctlError(f"kit-publish files only a draft from {DRAFTS}/ (written by make kit-report)")
    from .issues import file_issue
    return file_issue(root, args.title, args.body_file, args.type, args.priority, "repo", args.topic,
                      "triage", None, None, True, None, repository=template_repository(root))
