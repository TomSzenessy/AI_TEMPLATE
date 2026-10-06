#!/usr/bin/env python3
"""Portable repository governance CLI. Standard library only.

This file is only the command-line router; behavior lives in focused modules
under tools/kit/ (see tools/kit/__init__.py for the module map).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import tomllib  # noqa: F401 - fail fast with a clear message on old Pythons
except ModuleNotFoundError as error:  # pragma: no cover - exercised on Python 3.10
    raise SystemExit("repoctl requires Python 3.11 or newer") from error

from kit import derive, scaffold, session
from kit.bootstrap import initialize_project
from kit.capabilities import print_capabilities
from kit.core import RepoctlError, ensure_inside_root, load_project
from kit.docs import check_docs_index, check_file_hygiene, check_markdown_links
from kit.evals import run_evals
from kit.garden import garden_report, self_heal_errors
from kit.config import setting
from kit.github import sync_issue_labels, sync_repository_metadata
from kit.issues import (
    check_issue_for_duplicates,
    create_incident,
    print_review_packet,
    validate_issue_file,
)
from kit.launch import check_readiness, check_readiness_gate
from kit.navigate import print_map, skill_overlap, where
from kit.risk import print_risk
from kit.skills import check_skill_provenance, directory_digest, print_resources
from kit.structure import check_readme_identity, check_structure, print_inventory, run_verification


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repoctl")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="set project identity")
    init_parser.add_argument("--name", required=True)
    init_parser.add_argument("--kind", required=True, help="lowercase kebab-case project kind")

    subparsers.add_parser("inventory", help="show detected and declared product surfaces")
    subparsers.add_parser("resources", help="show the validated read-only resource router")
    skill_digest_parser = subparsers.add_parser("skill-digest", help="hash a reviewed skill directory for provenance")
    skill_digest_parser.add_argument("path", type=Path)
    subparsers.add_parser("check", help="check manifests, structure, docs, and hygiene")
    subparsers.add_parser("doctor", help="check initialization and launch readiness")
    subparsers.add_parser("readiness", help="enforce public-launch evidence gates")
    subparsers.add_parser("verify", help="run every active surface's declared verification")

    incident_parser = subparsers.add_parser("incident", help="create an incident regression record")
    incident_parser.add_argument("--title", required=True)
    incident_parser.add_argument("--summary", required=True)
    incident_parser.add_argument(
        "--public-safe",
        action="store_true",
        help="promote a redacted incident into the tracked docs/incidents register",
    )
    incident_parser.add_argument("--review-evidence")

    issue_parser = subparsers.add_parser("issue", help="validate and file a duplicate-aware issue")
    issue_parser.add_argument("--title", required=True)
    issue_parser.add_argument("--body-file", type=Path, required=True)
    issue_parser.add_argument("--type", required=True)
    issue_parser.add_argument("--priority", required=True)
    issue_parser.add_argument("--area", required=True)
    issue_parser.add_argument("--topic", required=True)
    issue_parser.add_argument("--status", default="triage")
    issue_parser.add_argument("--surface")
    issue_parser.add_argument("--gate")
    issue_parser.add_argument(
        "--public-reviewed",
        action="store_true",
        help="confirm the body is reviewed and safe for public filing",
    )
    issue_parser.add_argument(
        "--review-evidence",
        help="repository-relative reviewed disclosure record",
    )

    validate_parser = subparsers.add_parser("validate-issue", help="validate a canonical issue body")
    validate_parser.add_argument("--body-file", type=Path, required=True)
    validate_parser.add_argument("--status", default="triage")

    review_parser = subparsers.add_parser(
        "review-packet", help="print a fresh-agent critic prompt for an issue"
    )
    review_parser.add_argument("--issue-file", type=Path, required=True)

    labels_parser = subparsers.add_parser("labels", help="manage the canonical GitHub issue taxonomy")
    labels_parser.add_argument("--sync", action="store_true", help="create/update registry labels")

    # Self-healing and navigation commands (docs/self-healing.md, docs/delegation.md).
    sync_parser = subparsers.add_parser("sync", help="regenerate derived files: host adapters, docs index, README description")
    sync_parser.add_argument("--check", action="store_true", help="report drift without writing")
    hook_parser = subparsers.add_parser("hook", help="run a host lifecycle hook (reads optional host JSON on stdin)")
    hook_parser.add_argument("event", choices=["session-start", "pre-compact", "after-edit", "stop", "commit-msg"])
    hook_parser.add_argument("message_file", nargs="?", help="commit message file (commit-msg only)")
    subparsers.add_parser("start", help="print the session brief (for hosts without hooks)")
    subparsers.add_parser("finish", help="completion gate for this branch's change set")
    new_parser = subparsers.add_parser("new", help="scaffold a skill, agent role, or doc and wire it in")
    new_parser.add_argument("--kind", required=True, choices=["skill", "agent", "doc"])
    new_parser.add_argument("--name", required=True)
    new_parser.add_argument("--description", required=True)
    new_parser.add_argument("--group", default="operate")
    new_parser.add_argument("--covers", default="")
    new_parser.add_argument("--access", default="read-only")
    new_parser.add_argument("--tier", default="balanced")
    new_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("handover", help="create HANDOVER.md from the template with git facts filled in")
    subparsers.add_parser("map", help="print the one-screen repository map")
    where_parser = subparsers.add_parser("where", help="find paths, symbols, headings, owners, and past failures")
    where_parser.add_argument("query", nargs="+")
    risk_parser = subparsers.add_parser("risk", help="classify this branch's changes into a ceremony tier")
    risk_parser.add_argument("--base")
    subparsers.add_parser("github-sync", help="apply project.toml description, topics, and template flag to GitHub")
    subparsers.add_parser("capabilities", help="report tools, agent hosts, and MCP routes available here")
    garden_parser = subparsers.add_parser("garden", help="aggregate rot report (docs, deprecations, budgets, surfaces)")
    garden_parser.add_argument("--output", type=Path, help="also write the Markdown report to this path")
    overlap_parser = subparsers.add_parser("similar", help="find existing skills/roles similar to a proposed capability")
    overlap_parser.add_argument("description", nargs="+")
    eval_parser = subparsers.add_parser("eval", help="run the fresh-agent navigation benchmark")
    eval_parser.add_argument("--host", default="claude")
    eval_parser.add_argument("--tasks", help="comma-separated task ids")
    eval_parser.add_argument("--timeout", type=int, default=300)
    eval_parser.add_argument("--model", help="model for hosts that accept one (default: [kit].eval_model for claude)")

    return parser


def require_self_heal(root: Path) -> None:
    errors = self_heal_errors(root)
    if errors:
        raise RepoctlError("self-healing check failed:\n- " + "\n- ".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "init":
            initialize_project(arguments.root.resolve(), arguments.name, arguments.kind)
        elif arguments.command == "inventory":
            print_inventory(arguments.root.resolve())
        elif arguments.command == "resources":
            print_resources(arguments.root.resolve())
        elif arguments.command == "skill-digest":
            repository_root = arguments.root.resolve()
            skill_path = ensure_inside_root(repository_root, repository_root / arguments.path, "skill directory")
            if not skill_path.is_dir():
                raise RepoctlError("skill-digest path must be a directory")
            print(directory_digest(skill_path))
        elif arguments.command == "check":
            repository_root = arguments.root.resolve()
            project = load_project(repository_root)
            check_skill_provenance(project)
            check_structure(repository_root, project)
            check_readme_identity(repository_root, project)
            check_docs_index(repository_root)
            check_markdown_links(repository_root)
            check_file_hygiene(repository_root)
            require_self_heal(repository_root)
            if isinstance(project.get("vision"), dict) and project["vision"].get("status") != "accepted":
                print("Vision intake is pending; complete VISION.md and docs/STACK-DECISION.md before declaring readiness.")
            print("Repository structure is coherent.")
        elif arguments.command == "doctor":
            check_readiness(arguments.root.resolve())
        elif arguments.command == "readiness":
            check_readiness_gate(arguments.root.resolve())
        elif arguments.command == "verify":
            require_self_heal(arguments.root.resolve())
            run_verification(arguments.root.resolve())
        elif arguments.command == "incident":
            create_incident(arguments.root.resolve(), arguments.title, arguments.summary, arguments.public_safe, arguments.review_evidence)
        elif arguments.command == "issue":
            check_issue_for_duplicates(
                arguments.root.resolve(),
                arguments.title,
                arguments.body_file,
                arguments.type,
                arguments.priority,
                arguments.area,
                arguments.topic,
                arguments.status,
                arguments.surface,
                arguments.gate,
                arguments.public_reviewed,
                arguments.review_evidence,
            )
        elif arguments.command == "validate-issue":
            validate_issue_file(arguments.root.resolve(), arguments.body_file, arguments.status)
            print("Issue body contract passed.")
        elif arguments.command == "review-packet":
            print_review_packet(arguments.root.resolve(), arguments.issue_file)
        elif arguments.command == "labels":
            if not arguments.sync:
                raise RepoctlError("labels currently requires --sync")
            sync_issue_labels(arguments.root.resolve())
        elif arguments.command == "sync":
            repository_root = arguments.root.resolve()
            if arguments.check:
                drift = derive.drift(repository_root)
                if drift:
                    raise RepoctlError("derived content drift:\n- " + "\n- ".join(drift))
                print("Derived files match their sources.")
            else:
                changed = derive.sync(repository_root)
                print("\n".join(changed) if changed else "Derived files already up to date.")
        elif arguments.command == "hook":
            return session.run_hook(arguments.root.resolve(), arguments.event, arguments.message_file)
        elif arguments.command == "start":
            session.session_start(arguments.root.resolve())
        elif arguments.command == "new":
            for line in scaffold.create(
                arguments.root.resolve(), arguments.kind, arguments.name, arguments.description,
                group=arguments.group, covers=arguments.covers, access=arguments.access,
                tier=arguments.tier, force=arguments.force,
            ):
                print(line)
        elif arguments.command == "handover":
            print(session.write_handover(arguments.root.resolve()))
        elif arguments.command == "finish":
            return session.finish(arguments.root.resolve())
        elif arguments.command == "map":
            print_map(arguments.root.resolve())
        elif arguments.command == "where":
            hits = where(arguments.root.resolve(), " ".join(arguments.query))
            print("\n".join(hits) if hits else "No match. Try fewer or different terms, or ask the scout role.")
        elif arguments.command == "risk":
            print_risk(arguments.root.resolve(), arguments.base)
        elif arguments.command == "github-sync":
            applied = sync_repository_metadata(arguments.root.resolve())
            print("Applied: " + " ".join(applied) if applied else "GitHub metadata already matches project.toml.")
        elif arguments.command == "capabilities":
            print_capabilities(arguments.root.resolve())
        elif arguments.command == "garden":
            report, status = garden_report(arguments.root.resolve())
            print(report, end="")
            if arguments.output:
                arguments.output.write_text(report, encoding="utf-8")
            return status
        elif arguments.command == "similar":
            repository_root = arguments.root.resolve()
            matches = skill_overlap(repository_root, " ".join(arguments.description))
            limit = float(setting(repository_root, "overlap_limit"))
            for score, name, text in matches:
                print(f"{score:.2f}  {name}: {text}")
            if matches and matches[0][0] >= limit:
                print(f"Verdict: reuse or extend {matches[0][1]} (edit its canonical file in .agents/).")
            elif matches and matches[0][0] >= limit / 2:
                print(f"Verdict: read {matches[0][1]} first; extend it if it covers the need, otherwise create a new one with make new.")
            else:
                print('Verdict: nothing similar. Create it: make new KIND=skill|agent|doc NAME=... DESC="...; ..."')
        elif arguments.command == "eval":
            return run_evals(arguments.root.resolve(), arguments.host, arguments.tasks, arguments.timeout, arguments.model)
    except (OSError, RepoctlError) as error:
        print(f"repoctl: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
