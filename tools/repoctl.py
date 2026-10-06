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

from kit.bootstrap import initialize_project
from kit.core import RepoctlError, ensure_inside_root, load_project
from kit.docs import check_docs_index, check_file_hygiene, check_markdown_links
from kit.github import sync_issue_labels
from kit.issues import (
    check_issue_for_duplicates,
    create_incident,
    print_review_packet,
    validate_issue_file,
)
from kit.launch import check_readiness, check_readiness_gate
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

    return parser


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
            if isinstance(project.get("vision"), dict) and project["vision"].get("status") != "accepted":
                print("Vision intake is pending; complete VISION.md and docs/STACK-DECISION.md before declaring readiness.")
            print("Repository structure is coherent.")
        elif arguments.command == "doctor":
            check_readiness(arguments.root.resolve())
        elif arguments.command == "readiness":
            check_readiness_gate(arguments.root.resolve())
        elif arguments.command == "verify":
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
    except (OSError, RepoctlError) as error:
        print(f"repoctl: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
