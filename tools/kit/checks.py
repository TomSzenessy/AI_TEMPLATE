"""The kit's checks, each declared with whether it blocks and why.

A check is a function of a `checkrun.Context` that returns findings, each naming
its fix. Blocking checks run in `make check`, `make verify`, the session brief,
and CI; advisory ones only in `make garden`. The rule for blocking is in
docs/self-healing.md#when-a-check-may-block. A project adds its own check as a
new file in `.agents/checks/` (`make new KIND=check`), never by editing this one.
"""

from __future__ import annotations

import re

from . import derive, docs, docsync, gatechecks, github, hygiene, product, skills, structure
from .config import setting
from .core import (
    FILE_SURFACE_KINDS,
    RepoctlError,
    declared_surfaces,
    parse_iso_date,
    surface_extra_paths,
    today,
)
from .gitinfo import changed_paths, has_history, path_matches
from .names import DESIGN
from .registry import check


def _raised(function, *arguments) -> list[str]:
    """Findings from an older check that raises one error listing its problems."""
    try:
        function(*arguments)
    except RepoctlError as error:
        return list(error.findings) or [str(error)]
    return []


# --- Repository contract ---------------------------------------------------------

@check("manifest-structure", "project.toml surfaces, governance, vision, and verification are coherent; run by make check",
       blocks=True, reason="Every command reads project.toml; in the 2026-10-08 Haiku trials every hit was a real defect "
              "(unregistered surfaces, unaccepted vision or stack decision).")
def manifest_structure(context) -> list[str]:
    typed = structure.manifest_type_errors(context.project)
    if typed:
        return typed
    return _raised(structure.check_structure, context.root, context.project) + _raised(
        structure.check_readme_identity, context.root, context.project)


@check("skill-provenance", "Third-party skills carry source, revision, digest, and review; before trusting a skill",
       blocks=True, reason="Unreviewed third-party instructions are an injection path; the digest makes tampering visible.")
def skill_provenance(context) -> list[str]:
    return _raised(skills.check_skill_provenance, context.project)


@check("file-hygiene", "No secrets, key files, or escaping symlinks in tracked files; on every change",
       blocks=True, reason="A committed secret is a public incident; the fix (remove the file) is cheap and deterministic.")
def file_hygiene(context) -> list[str]:
    return _raised(docs.check_file_hygiene, context.root)


@check("markdown-links", "Relative Markdown links resolve to real files; on every change",
       blocks=False)  # advisory since #9: in 13 Haiku trials no run was held up by a dead link
def markdown_links(context) -> list[str]:
    return _raised(docs.check_markdown_links, context.root)


@check("orphan-files", "Tracked files nothing in the tree names; import or bind each one, or delete what is dead",
       blocks=False)
def orphan_files(context) -> list[str]:
    return context.advisories[0]


@check("host-read-config", "Tracked host configuration no file names (editor, git, hosting, or scanner conventions); "
                          "reference it or declare it in [repository].infrastructure_paths",
       blocks=False)
def host_read_config(context) -> list[str]:
    return context.advisories[1]


# --- Derived files and the docs index ----------------------------------------------

@check("derived-drift", "Generated files (host adapters, docs index, Makefile commands, rules) match their sources; run make sync",
       blocks=True, reason="Hosts read the generated copies; drift means agents follow stale instructions (a Haiku tidepool "
              "trial committed stale adapters); make sync fixes it.")
def derived_drift(context) -> list[str]:
    return derive.drift(context.root)


@check("docs-index", "Every document is reachable from docs/README.md; when a doc is added",
       blocks=True, reason="An unindexed doc is never read; Haiku trials wrote design and research docs no index linked. "
              "make sync fixes it from the doc's index line.")
def docs_index(context) -> list[str]:
    return _raised(docs.check_docs_index, context.root) + docsync.index_errors(context.root, context.files)


# --- Docs that track the code ------------------------------------------------------

@check("dead-bindings", "Every covers glob matches a file; when code moves or dies",
       blocks=True, reason="A binding to nothing means the doc describes code that is gone; a Haiku ledger-cli trial bound "
              "docs to cmd/ paths it never created.")
def dead_bindings(context) -> list[str]:
    return docsync.dead_bindings(context.bindings, context.files)


@check("stale-docs", "A doc is updated after the code it covers changes (or a Docs-Unaffected trailer says why)",
       blocks=True, reason="Trials showed agents skip doc updates at the end of a session; this is the one point that catches it.")
def stale_docs(context) -> list[str]:
    return docsync.stale_documents(context.root, context.bindings, changed_paths(context.root))


@check("command-references", "Every `make x` and `repoctl x` named in Markdown exists; when commands or docs change",
       blocks=False)  # advisory since #9: never hit in a trial
def command_references(context) -> list[str]:
    return docsync.command_reference_errors(context.root, context.files)


# --- Code hygiene ---------------------------------------------------------------------

@check("markers", "Deprecations carry a remove-by date, task markers an issue, and FILL-IN placeholders are replaced",
       blocks=False)  # advisory since #9: trials only met it as noise from test fixtures
def markers(context) -> list[str]:
    return hygiene.scan_markers(context.root, context.scoped_files).errors


@check("budgets", "Files agents load often stay within project.toml [budgets]; when the router or a skill grows",
       blocks=False)  # advisory since #9: never hit in a trial; make garden reports it
def budgets(context) -> list[str]:
    return hygiene.budget_errors(context.root, context.project, context.files)


@check("workflow-length", "CI run blocks stay short; logic lives in tested tools/ code",
       blocks=True, reason="Untested workflow shell broke CI repeatedly; the repoctl ci commands are tested locally.")
def workflow_length(context) -> list[str]:
    return hygiene.workflow_errors(context.root, context.files)


# --- Product guardrails (each from a step a trial agent skipped) ---------------------

BACKLOG_NAMES = re.compile(r"(?i)(?:^|/)(?:backlog|todo|tasks|roadmap)\.md$|(?:^|/)docs/[^/]*wal[^/]*\.md$")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


@check("tracked-backlog", "Live work lives in issues, not a tracked backlog file",
       blocks=True, reason="A trial agent kept a tracked WAL file that went stale; issues are the one register.")
def tracked_backlog(context) -> list[str]:
    return [
        f"{path}: live work belongs in issues (or ignored .agent/wal/ via `make issue` without a remote), not a tracked backlog"
        for path in context.files
        if BACKLOG_NAMES.search(path) and not path.startswith((".agents/", ".claude/"))
    ]


@check("surface-docs", "Every active product surface has an owning doc; when a surface is declared",
       blocks=True, reason="A trial agent built a whole surface no document explained; the next agent could not navigate it.")
def surface_docs(context) -> list[str]:
    errors = []
    for surface in declared_surfaces(context.project):
        path = str(surface.get("path", "."))
        # Directory surfaces only: a single file or document surface is its own owner.
        if (surface.get("status", "active") != "active" or surface.get("kind") == "template"
                or surface.get("kind") in FILE_SURFACE_KINDS or path in {".", ""}):
            continue
        # An entry file the generator put outside the directory belongs to this surface (#57).
        owned = [path] + surface_extra_paths(surface, str(surface.get("id", "?")))
        inside = [
            file for file in context.files
            if any(file == candidate or file.startswith(candidate.rstrip("/") + "/") for candidate in owned)
        ]
        if inside and not any(path_matches(file, pattern) for file in inside
                              for patterns in context.bindings.values() for pattern in patterns):
            errors.append(
                f"surface {surface.get('id')} ({path}) has no owning doc: add `<!-- covers: {path}/** -->` to the doc that "
                f'explains it, or `make new KIND=doc NAME={surface.get("id")} GROUP=design COVERS="{path}/**" DESC="...; ..."`'
            )
    return errors


@check("owner-handles", "project.toml owners are handles or team names, never emails",
       blocks=True, reason="Manifests are public; an email there is personal data published by default.")
def owner_handles(context) -> list[str]:
    project = context.project
    listed = project.get("owners", [])
    owners = [*(listed if isinstance(listed, list) else []), *(surface.get("owner", "") for surface in declared_surfaces(project))]
    return [
        f"project.toml owner {owner!r} looks like an email; manifests are public, use a handle or team name"
        for owner in sorted({owner for owner in owners if isinstance(owner, str)})
        if isinstance(owner, str) and EMAIL.fullmatch(owner.strip())
    ]


@check("design-record", "A UI product records its visual direction in docs/design.md before building",
       blocks=True, pack="product",
       reason="Trial agents without a design record built inconsistent screens; product-kickoff step 5 writes it.")
def design_record(context) -> list[str]:
    project = context.project
    vision = project.get("vision", {})
    accepted = isinstance(vision, dict) and vision.get("status") == "accepted"
    building = any(surface.get("status", "active") == "active" and surface.get("kind") != "template"
                   for surface in declared_surfaces(project))
    if accepted and project.get("kind") in setting(context.root, "ui_kinds") and building and DESIGN not in context.files:
        return ['UI project without docs/design.md: record the chosen direction (product-kickoff step 5): '
                'make new KIND=doc NAME=design GROUP=design DESC="Visual direction, tokens, and UX principles; before any UI work"']
    return []


@check("feature-evidence", "Feature-list rows marked done cite real evidence; must rows have acceptance criteria",
       blocks=True, pack="product",
       reason="A trial agent marked features done with no test behind them; the evidence is a file, so it is cheap to check.")
def feature_evidence(context) -> list[str]:
    return product.feature_errors(context.root)


@check("research-record", "A UI product cites at least three researched sources before building",
       blocks=True, pack="product",
       reason="Trial products built without references looked generic; three sources take minutes with the research step.")
def research_record(context) -> list[str]:
    return product.research_errors(context.root, context.project)


# --- Advisory: reported by make garden, never blocking --------------------------------

@check("upcoming-deprecations", "Deprecation markers whose remove-by date is near; plan the removal", blocks=False)
def upcoming_deprecations(context) -> list[str]:
    report = hygiene.scan_markers(context.root, context.files, warning_days=int(setting(context.root, "deprecation_warning_days")))
    return [f"deprecation due soon: {item}" for item in report.upcoming]


@check("duplicate-paragraphs", "Paragraphs repeated across documents; merge them into their owner doc", blocks=False)
def duplicate_paragraphs(context) -> list[str]:
    return hygiene.duplicate_paragraphs(context.root, context.files)


@check("unbound-docs", "Documents without a covers binding; bind docs that explain behavior", blocks=False)
def unbound_docs(context) -> list[str]:
    unbound = sorted(
        path for path in context.files
        if path.startswith("docs/") and path.endswith(".md") and path not in context.bindings
        and not any(path_matches(path, pattern) for pattern in setting(context.root, "unbound_docs_ok"))
    )
    return ["documents without a covers binding (fine for pure policy docs): " + ", ".join(unbound)] if unbound else []


@check("skill-folders-without-manifest", "Folders under .agents/skills with no SKILL.md; add it or remove the folder",
       blocks=False)
def skill_folders_without_manifest(context) -> list[str]:
    files = set(context.files)
    folders = {path.split("/")[2] for path in files if path.startswith(".agents/skills/") and path.count("/") >= 3}
    return [f".agents/skills/{name}/ has no SKILL.md, so it is not a skill and is ignored; add SKILL.md or delete the folder"
            for name in sorted(folders) if f".agents/skills/{name}/SKILL.md" not in files]


@check("skill-review-age", "Third-party skill reviews older than the review window; re-review before release", blocks=False)
def skill_review_age(context) -> list[str]:
    findings = []
    entries = context.project.get("skills", [])
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        reviewed = str(entry.get("reviewed_on", ""))
        reviewed_date = parse_iso_date(reviewed)
        if reviewed_date is None:
            continue
        age = (today() - reviewed_date).days
        if age > int(setting(context.root, "skill_review_days")):
            findings.append(
                f"skill review older than {setting(context.root, 'skill_review_days')} days: "
                f"{entry.get('package')} (reviewed {reviewed})"
            )
    return findings


@check("github-metadata", "GitHub description and topics match project.toml; run make github-sync", blocks=False)
def github_metadata(context) -> list[str]:
    try:
        return github.metadata_drift(context.root)
    except Exception as error:  # noqa: BLE001 - metadata drift is advisory only
        return [f"GitHub metadata check skipped: {error}"]


@check("pin-drift", "Tool versions the kit pins that are behind their latest release; bump deliberately", blocks=False)
def pin_drift(context) -> list[str]:
    from .garden import pin_drift as drift
    return drift(context.root)


@check("change-coupling", "Directory pairs that keep changing together; a wrong seam shows up in history first",
       blocks=False)
def change_coupling(context) -> list[str]:
    from .coupling import coupling_findings
    return coupling_findings(context.root)


@check("kit-updates", "Template fixes not yet merged into this project, or a template that moved on; run make kit-update",
       blocks=False)
def kit_updates(context) -> list[str]:
    from .kitupdate import behind_template, pending_merges
    behind = behind_template(context.root)
    return pending_merges(context.root) + ([behind] if behind else [])


@check("shallow-history", "Stale-doc detection needs git history; use fetch-depth: 0 in CI", blocks=False)
def shallow_history(context) -> list[str]:
    if has_history(context.root):
        return []
    return ["git history unavailable or shallow: stale-document detection skipped (use fetch-depth: 0 in CI)"]


@check("history-read", "Stale-doc detection could not read git history (failed or timed out); rerun with a full clone",
       blocks=False)
def history_read_failed(context) -> list[str]:
    if not context.bindings or not has_history(context.root) or docsync.history_read(context.root) is not None:
        return []
    return ["history read failed or timed out: stale-document detection skipped (rerun, or fetch full history)"]


@check("final-newline", "Tracked text files that end without a newline; append one", blocks=False)
def final_newline(context) -> list[str]:
    return hygiene.final_newline_errors(context.root, context.files)


@check("host-twins", "CLAUDE.md and GEMINI.md differ beyond the host name; keep the twins identical", blocks=False)
def host_twins(context) -> list[str]:
    return hygiene.host_twin_errors(context.root)



@check("plugin-load", "A project plugin under .agents/commands or .agents/checks failed to import; fix or delete the file",
       blocks=True, reason="Issue #28: one plugin that failed to import used to disable every command and let "
                           "commits skip the gate; it is now isolated, so this finding is the only place its "
                           "capability's absence is visible.")
def plugin_load(context) -> list[str]:
    return [f"{path}: {error}" for path, error in context.registry.plugin_errors]


# --- Change-set rules the commit and stop gates name (no change set, no findings) ----

@check("doc-coupling", "A covered document is updated with the code it covers; asked per commit and per session by the gates",
       blocks=True, reason="Trials showed agents skip doc updates; the gates ask this per change set, where the "
                           "branch-wide stale-docs check cannot say which commit owes the update.")
def doc_coupling(context) -> list[str]:
    return gatechecks.owed_docs(context)


@check("critic-evidence", "High-risk work carries a critic verdict bound to HEAD in .agent/critic.md; asked by the stop and done gates",
       blocks=True, reason="High-risk changes need an independent read; on 2026-10-08 a critic found an unbounded stop-hook "
              "loop the builder had missed. The gate reads the saved verdict so the claim is checkable.")
def critic_evidence(context) -> list[str]:
    return gatechecks.critic_evidence(context)
