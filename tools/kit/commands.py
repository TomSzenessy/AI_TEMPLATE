"""The kit's commands, each declared once: its help line, `make help` group, and arguments.

`tools/repoctl.py` builds its parser from these declarations, and `make sync`
generates the Makefile's command block from them, so neither grows by hand.
A project adds its own command as a new file in `.agents/commands/`
(`make new KIND=command`), never by editing this one.
"""

from __future__ import annotations

from pathlib import Path

from . import ci, derive, scaffold, session
from .core import RepoctlError, check_failed, ensure_inside_root, load_project
from .registry import KINDS, arg, command

# make help groups, in display order.
GROUPS = {
    "session": "EVERY SESSION (this is all most tasks need)",
    "extend": "EXTEND THE SYSTEM (one path for every kind of capability)",
    "when-needed": "WHEN NEEDED",
    "setup": "PROJECT SETUP AND MAINTENANCE",
}
# Targets the Makefile writes by hand because they chain other targets or run the test suites.
RECIPES = {
    "done": ("session", "make done", 'Before saying "done": heal derived files, gates, all tests'),
    "verify": ("setup", "make verify", "Tests, every surface's verification, and doctor (CI runs this)"),
    "test": ("setup", "make test", "The kit's and every skill's unit tests"),
    "test-future": ("setup", "make test-future", "The suite 800 days ahead: catches checks that rot with the calendar"),
}


def _require_self_heal(root: Path) -> None:
    from .garden import self_heal_errors
    errors = self_heal_errors(root)
    if errors:
        from .registry import Registry, blocking_reasons
        reasons = blocking_reasons(Registry(root), errors)
        raise check_failed("self-healing", errors,
                           "\nWhy these block:\n  " + "\n  ".join(reasons) if reasons else "")


# --- Every session ---------------------------------------------------------------

@command("start", "Print the session brief: branch, handover, map, next step, what needs attention", group="session",
         usage="make start")
def start(root: Path, args) -> None:
    session.session_start(root)


@command("next", "The single next step toward a complete product", group="session", pack="product", usage="make next")
def next_step(root: Path, args) -> None:
    from .product import print_next
    print_next(root)


@command("where", "Find files, symbols, owning docs, rules, capabilities, and past failures", group="session",
         usage='make where Q="login form"',
         args=(arg("query", nargs="+", var="Q", hint='Add what to look for: make where Q="login form"'),))
def where(root: Path, args) -> None:
    from .navigate import where as find
    hits = find(root, " ".join(args.query))
    print("\n".join(hits) if hits else "No match. Try fewer or different terms, or ask the scout role.")


@command("ui-review", "Screenshot the UI (phone/desktop, light/dark) for a judged review", group="session",
         pack="product", usage="make ui-review")
def ui_review(root: Path, args) -> int:
    from .uireview import run_review
    return run_review(root)


@command("finish", "Completion gate for this branch's change set (run by make done)", make=None)
def finish(root: Path, args) -> int:
    return session.finish(root)


@command("hook", "Run a host lifecycle hook (reads optional host JSON on stdin)", make=None, args=(
    arg("event", choices=list(session.HOOK_EVENTS)),
    arg("message_file", nargs="?", help="commit message file (commit-msg only)"),
))
def hook(root: Path, args) -> int:
    return session.run_hook(root, args.event, args.message_file)


# --- Extend the system -------------------------------------------------------------

@command("new", "Create any capability with valid metadata and wire it in", group="extend",
         usage=f'make new KIND={"|".join(KINDS)} NAME=x DESC="what; when"', args=(
    arg("--kind", required=True, choices=list(KINDS), var="KIND",
        hint=f"Choose what to create: make new KIND={'|'.join(KINDS)} NAME=my-name DESC=\"what it does; when to use it\""),
    arg("--name", required=True, var="NAME", hint="Name it: NAME=kebab-case-name"),
    arg("--description", required=True, var="DESC", hint='Describe it: DESC="what it does; when to use it"'),
    arg("--pack", default="", var="PACK", help="pack the capability belongs to (default: core, always on)"),
    arg("--group", default="operate", var="GROUP", help="docs index group (doc)"),
    arg("--covers", default="", var="COVERS", help="paths a doc describes or a rule applies to"),
    arg("--access", default="read-only", var="ACCESS", help="agent access"),
    arg("--tier", default="balanced", var="TIER", help="agent model tier"),
    arg("--force", action="store_true", var="FORCE", help="create despite a similar capability"),
))
def new(root: Path, args) -> None:
    for line in scaffold.create(root, args.kind, args.name, args.description, pack=args.pack, group=args.group,
                                covers=args.covers, access=args.access, tier=args.tier, force=args.force):
        print(line)


@command("similar", "Does a similar capability (any kind, any pack) already exist?", group="extend",
         usage='make similar Q="release notes"',
         args=(arg("description", nargs="+", var="Q", hint='Describe the capability: make similar Q="draft release notes"'),))
def similar(root: Path, args) -> None:
    from .config import setting
    from .navigate import skill_overlap
    matches = skill_overlap(root, " ".join(args.description))
    limit = float(setting(root, "overlap_limit"))
    for score, name, text in matches:
        print(f"{score:.2f}  {name}: {text}")
    if matches and matches[0][0] >= limit:
        print(f"Verdict: reuse or extend {matches[0][1]} (edit its file; make where Q=\"{matches[0][1].split(':', 1)[1]}\").")
    elif matches and matches[0][0] >= limit / 2:
        print(f"Verdict: read {matches[0][1]} first; extend it if it covers the need, otherwise create a new one with make new.")
    else:
        print("Verdict: nothing similar here. Outside capabilities: ask the skill-scout role (docs/skills.md); "
              'then make new KIND=<kind> NAME=... DESC="...; ..."')


@command("capabilities", "Every capability by kind and pack, plus tools, agent hosts, and MCP routes", group="extend",
         usage="make capabilities")
def capabilities(root: Path, args) -> None:
    from .capabilities import print_capabilities
    print_capabilities(root)


# --- When needed ---------------------------------------------------------------------

@command("risk", "How much ceremony this change needs (low, normal, high)", group="when-needed", usage="make risk",
         args=(arg("--base"),))
def risk(root: Path, args) -> None:
    from .risk import print_risk
    print_risk(root, args.base)


@command("handover", "Write HANDOVER.md before pausing (git facts pre-filled)", group="when-needed", usage="make handover")
def handover(root: Path, args) -> None:
    print(session.write_handover(root))


@command("map", "One-screen repository map", group="when-needed", usage="make map")
def repository_map(root: Path, args) -> None:
    from .navigate import print_map
    print_map(root)


@command("garden", "Full rot report: every check, advisory ones included", group="when-needed", usage="make garden",
         args=(arg("--output", type=Path, help="also write the Markdown report to this path"),))
def garden(root: Path, args) -> int:
    from .garden import garden_report
    report, status = garden_report(root)
    print(report, end="")
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    return status


@command("sync", "Regenerate derived files after editing their sources", group="when-needed", usage="make sync",
         args=(arg("--check", action="store_true", help="report drift without writing"),))
def sync(root: Path, args) -> None:
    if args.check:
        drift = derive.drift(root)
        if drift:
            raise RepoctlError("derived content drift:\n- " + "\n- ".join(drift))
        print("Derived files match their sources.")
    else:
        changed = derive.sync(root)
        print("\n".join(changed) if changed else "Derived files already up to date.")


@command("issue", "Validate and file a duplicate-aware issue (or Local-WAL drafts)", group="when-needed",
         usage='make issue BODY=path TITLE="..." TYPE=... PRIORITY=... AREA=... TOPIC=...', args=(
    arg("--wal", var="WAL", help="file Local-WAL drafts instead: an id such as Local-WAL-002, or all"),
    arg("--title", var="TITLE"),
    arg("--body-file", type=Path, var="BODY"),
    arg("--type", var="TYPE"),
    arg("--priority", var="PRIORITY"),
    arg("--area", var="AREA"),
    arg("--topic", var="TOPIC"),
    arg("--status", default="triage", var="STATUS"),
    arg("--surface", var="SURFACE"),
    arg("--gate", var="GATE"),
    arg("--public-reviewed", action="store_true", var="PUBLIC_REVIEWED",
        help="confirm the body is reviewed and safe for public filing"),
    arg("--review-evidence", var="REVIEW_EVIDENCE", help="repository-relative reviewed disclosure record"),
))
def issue(root: Path, args) -> int | None:
    from .issues import file_issue, file_local_wal
    if args.wal:
        return file_local_wal(root, args.wal, args.public_reviewed, args.review_evidence)
    missing = [flag for flag in ("title", "body_file", "type", "priority", "area", "topic") if not getattr(args, flag)]
    if missing:
        raise RepoctlError("issue needs " + ", ".join("--" + flag.replace("_", "-") for flag in missing) + " (or --wal)")
    file_issue(root, args.title, args.body_file, args.type, args.priority, args.area, args.topic,
                               args.status, args.surface, args.gate, args.public_reviewed, args.review_evidence)
    return None


@command("review-packet", "Print a fresh-agent critic brief for an issue", group="when-needed",
         usage="make review-packet ISSUE_FILE=path",
         args=(arg("--issue-file", type=Path, required=True, var="ISSUE_FILE", hint="Name the issue: ISSUE_FILE=path"),))
def review_packet(root: Path, args) -> None:
    from .issues import print_review_packet
    print_review_packet(root, args.issue_file)


@command("incident", "Create a private incident regression record", group="when-needed",
         usage='make incident TITLE="..." SUMMARY="..."', args=(
    arg("--title", required=True, var="TITLE", hint='Title it: make incident TITLE="..." SUMMARY="..."'),
    arg("--summary", required=True, var="SUMMARY", hint='Summarize it: SUMMARY="..."'),
    arg("--public-safe", action="store_true", var="PUBLIC_SAFE",
        help="promote a redacted incident into the tracked docs/incidents register"),
    arg("--review-evidence", var="REVIEW_EVIDENCE"),
))
def incident(root: Path, args) -> None:
    from .issues import create_incident
    create_incident(root, args.title, args.summary, args.public_safe, args.review_evidence)


# --- Project setup and maintenance --------------------------------------------------

@command("init", "Turn the template into your project", group="setup", usage="make init NAME=my-project KIND=web [OWNER=you]",
         args=(
    arg("--name", required=True, var="NAME", hint="Name the project: make init NAME=my-project KIND=web"),
    arg("--kind", required=True, var="KIND", help="lowercase kebab-case project kind",
        hint="Give its kind: make init NAME=my-project KIND=web"),
    arg("--owner", var="OWNER", help="accountable owner handle or team (replaces the project-owner placeholder)"),
))
def init(root: Path, args) -> None:
    from .bootstrap import initialize_project
    initialize_project(root, args.name, args.kind, args.owner)


@command("adopt", "Bring this kit into an existing repository (--root) without overwriting it", group="setup",
         usage="make -f <kit>/Makefile adopt NAME=x KIND=web OWNER=you",
         make=('$(if $(KIT_IN_NAME),,$(error Name the project: make -f <kit>/Makefile adopt NAME=my-app KIND=web OWNER=you; '
               'if the kit path is not found add KIT_DIR=<kit>))\n'
               '\t$(if $(shell test -f "$(KIT_DIR)/tools/repoctl.py" && echo ok),,$(error KIT_DIR is not a kit checkout: '
               'pass KIT_DIR=<kit> (the directory holding tools/repoctl.py)))\n'
               '\t$(PYTHON) "$${KIT_DIR}/tools/repoctl.py" --root "$(CURDIR)" adopt --from "$${KIT_DIR}" --name "$${KIT_IN_NAME}" '
               '--kind "$${KIT_IN_KIND}" $(if $(KIT_IN_OWNER),--owner "$${KIT_IN_OWNER}",)'),
         args=(
    arg("--from", dest="kit", type=Path, required=True, help="the kit (template) checkout"),
    arg("--name", required=True),
    arg("--kind", required=True),
    arg("--owner"),
))
def adopt(root: Path, args) -> None:
    from .adopt import adopt as run_adopt
    run_adopt(root, args.kit, args.name, args.kind, args.owner)


@command("kit-update", "Pull template fixes into this project (keeps your changes)", group="setup",
         usage="make kit-update [KIT=<template checkout>] [KIT_REF=<sha>]",
         args=(arg("--kit", var="KIT", help="template checkout (default: clone [template].source)"),
               arg("--ref", var="KIT_REF", help="pin the update to this template commit (default: its HEAD)")))
def kit_update(root: Path, args) -> int:
    from .kitupdate import update_from_source
    return update_from_source(root, args.kit, args.ref)


@command("check", "Every blocking check of the enabled packs", group="setup", usage="make check")
def check(root: Path, args) -> None:
    _require_self_heal(root)
    vision = load_project(root).get("vision")
    if isinstance(vision, dict) and vision.get("status") != "accepted":
        print("Vision intake is pending; complete VISION.md and docs/STACK-DECISION.md before declaring readiness.")
    print("Repository structure is coherent.")


@command("verify", "Run every active surface's declared verification (make verify adds tests and doctor)", make=None)
def verify(root: Path, args) -> None:
    from .structure import run_verification
    _require_self_heal(root)
    run_verification(root)


@command("doctor", "Check initialization and the readiness of the declared phase", group="setup", usage="make doctor")
def doctor(root: Path, args) -> None:
    from .launch import check_readiness
    check_readiness(root)


@command("readiness", "Enforce public-launch evidence gates", group="setup", usage="make readiness")
def readiness(root: Path, args) -> None:
    from .launch import check_readiness_gate
    check_readiness_gate(root)


@command("inventory", "Show detected and declared product surfaces", group="setup", usage="make inventory")
def inventory(root: Path, args) -> None:
    from .structure import print_inventory
    print_inventory(root)


@command("resources", "Show the validated read-only resource router", group="setup", usage="make resources")
def resources(root: Path, args) -> None:
    from .skills import print_resources
    print_resources(root)


@command("skill-digest", "Hash a reviewed skill directory for provenance", group="setup",
         usage="make skill-digest SKILL_PATH=.agents/skills/name",
         args=(arg("path", type=Path, var="SKILL_PATH", hint="Name the skill: SKILL_PATH=.agents/skills/name"),))
def skill_digest(root: Path, args) -> None:
    from .skills import directory_digest
    skill_path = ensure_inside_root(root, root / args.path, "skill directory")
    if not skill_path.is_dir():
        raise RepoctlError("skill-digest path must be a directory")
    print(directory_digest(skill_path))


@command("validate-issue", "Validate a canonical issue body", group="setup", usage="make validate BODY=path", target="validate",
         args=(
    arg("--body-file", type=Path, required=True, var="BODY", hint="Name the body: BODY=path"),
    arg("--status", default="triage", var="STATUS"),
))
def validate_issue(root: Path, args) -> None:
    from .issues import validate_issue_file
    validate_issue_file(root, args.body_file, args.status)
    print("Issue body contract passed.")


@command("labels", "Create or update the canonical GitHub issue labels", group="setup", usage="make labels",
         args=(arg("--sync", action="store_true", help="create/update registry labels"),), make_extra="--sync")
def labels(root: Path, args) -> None:
    from .github import sync_issue_labels
    if not args.sync:
        raise RepoctlError("labels currently requires --sync")
    sync_issue_labels(root)


@command("github-sync", "Apply project.toml description, topics, and template flag to GitHub", group="setup",
         usage="make github-sync")
def github_sync(root: Path, args) -> None:
    from .github import sync_repository_metadata
    applied = sync_repository_metadata(root)
    print("Applied: " + " ".join(applied) if applied else "GitHub metadata already matches project.toml.")


@command("ci", "Run a CI check (the same tested code GitHub Actions runs)", make=None,
         args=(arg("check", choices=["pr-reference", "issue-contract"]),))
def run_ci(root: Path, args) -> None:
    runner = ci.run_pr_reference if args.check == "pr-reference" else ci.run_issue_contract
    print(runner(root))


@command("eval", "Fresh-agent navigation benchmark (cheap model by default)", group="setup", pack="measure",
         usage="make eval AGENT=claude [MODEL=haiku]", args=(
    arg("--host", default="claude", var="AGENT"),
    arg("--tasks", var="TASKS", help="comma-separated task ids"),
    arg("--timeout", type=int, default=300),
    arg("--model", var="MODEL", help="model for hosts that accept one (default: [kit].eval_model for claude)"),
))
def run_eval(root: Path, args) -> int:
    from .evals import run_evals
    return run_evals(root, args.host, args.tasks, args.timeout, args.model)


@command("trial", "Build trial: an agent builds a product from a request; friction report", group="setup",
         pack="measure", usage="make trial NAME=<request> [MODEL=sonnet] [BUDGET=25]", args=(
    arg("id", var="NAME", hint="Name a request in .agents/trials/: make trial NAME=waypoint"),
    arg("--model", default="sonnet", var="MODEL"),
    arg("--budget", type=float, var="BUDGET", help="spend cap in USD (default: the request's budget_usd)"),
    arg("--dir", help="project directory (default: a new temporary directory)"),
    arg("--analyze", metavar="TRANSCRIPT", help="only report on an existing stream-json transcript"),
    arg("--project", help="with --analyze: the project directory the run used"),
))
def trial(root: Path, args) -> int:
    from .trial import analyze_existing, run_trial
    if args.analyze:
        if not args.project:
            raise RepoctlError("--analyze needs --project (the directory the run built in)")
        return analyze_existing(root, args.id, args.analyze, args.project, args.model)
    return run_trial(root, args.id, args.model, args.budget, args.dir)


@command("help", "List the make commands by when you need them", make="", usage="make help")
def show_help(root: Path, args) -> None:
    from .registry import Registry
    print(help_text(Registry(root)))


def help_text(registry) -> str:
    """`make help`: every command of an enabled pack, grouped; disabled packs are named, not hidden."""
    rows: dict[str, list[tuple[str, str]]] = {group: [] for group in GROUPS}
    off: list[str] = []
    for item in registry.of("command", enabled_only=False):
        if item.fields["make"] is None or item.name == "help":
            continue
        if not registry.enabled(item):
            off.append(item.name)
            continue
        group = item.fields["group"] if item.fields["group"] in GROUPS else "when-needed"
        rows[group].append((item.fields["usage"] or f"make {item.name}", item.description))
    for group, usage, text in RECIPES.values():
        rows[group].append((usage, text))
    lines = []
    for group, title in GROUPS.items():
        lines += ([""] if lines else []) + [title]
        for usage, text in rows[group]:
            lines.append(f"  {usage:<34} {text}" if len(usage) <= 34 else f"  {usage}\n  {'':<34} {text}")
    if off:
        lines += ["", f"Packs switched off hide: {', '.join(sorted(off))} (make capabilities shows how to enable them)"]
    return "\n".join(lines)
