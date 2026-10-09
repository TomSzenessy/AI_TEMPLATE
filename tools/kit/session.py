"""Portable session lifecycle: what happens at start, before compaction, after an
edit, and before an agent declares it is done.

Hosts with hooks call `repoctl hook <event>` (Claude Code via the generated
`.claude/settings.json`); hosts without hooks run `make start` and
`make done`. Every event reads optional host JSON on stdin and never needs it.
Output is evidence about the repository, not new authority: AGENTS.md rules.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import derive, docmeta, docsync
from .core import (
    GATE_COMMIT_BLOCKED, GATE_NOT_FINISHED, GATE_STOP_BLOCKED,
    RepoctlError, default_branch, governance_profile, load_project, read_text_file, repository_files,
)
from .garden import self_heal_errors
from .kitlock import rename_mentions, renamed_targets
from .gitinfo import branch, branch_paths, changed_paths, diff_paths, git, head, path_matches, run_git
from .names import AFTER_EDIT, CHECKPOINT, COMMIT_MSG, CRITIC_RECORD, HANDOVER, PRE_COMPACT, SESSION_START, STOP
from .navigate import print_map
from .product import drive_reason, next_step, product_summary
from .checkrun import Change, run_checks
from .registry import KINDS, Registry, project_plugin_files
from .risk import assess
from .uireview import review_status


def _product_on(root: Path) -> bool:
    try:
        return Registry(root).pack_state.get("product", False)
    except RepoctlError:
        return True  # a broken manifest is reported by the checks; keep the product guidance

HANDOVER_LIMIT = 4000
MAP_LIMIT = 15
STATE = ".agent/hook-state.json"  # outside git, or when git cannot say where its directory is


def state_path(root: Path) -> Path:
    """Where the hooks keep per-session state: inside the git directory when there is one.

    Scaffolders that empty the project (`npm create vite . --overwrite`) and `git clean -fdx`
    keep `.git` and delete ignored files. In the 2026-10-08 Haiku tidepool trial that wiped
    `.agent/hook-state.json` early on, and the stop gate judged nothing for the rest of the run.
    """
    found = run_git(root, "rev-parse", "--git-path", "repoctl-hook-state.json")
    if found is not None and found.returncode == 0 and found.stdout.strip():
        path = Path(found.stdout.strip())
        return path if path.is_absolute() else root / path
    return root / STATE


def _save_state(root: Path, state: dict) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


CANONICAL_INPUTS = (".agents/", "tools/kit/commands.py", "project.toml")


def read_event() -> dict[str, object]:
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _relative(root: Path, value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    try:
        return (path if path.is_absolute() else root / path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _heal_derived(root: Path) -> list[str]:
    try:
        return derive.sync(root)
    except (RepoctlError, OSError) as error:
        return [f"adapter regeneration failed: {error}"]


def _digest(root: Path, path: str) -> str:
    try:
        return hashlib.sha256((root / path).read_bytes()).hexdigest()
    except OSError:
        return "deleted"


def _snapshot(root: Path, paths: list[str]) -> dict[str, str]:
    return {path: _digest(root, path) for path in paths}


def _record_snapshot(root: Path, session: str, changed: list[str]) -> None:
    """Remember what was already dirty, so the stop gate can tell this session's edits apart."""
    state = _load_state(root, session)
    if "snapshot" in state:
        return  # a resumed or compacted session keeps its original baseline
    state["snapshot"] = _snapshot(root, changed)
    state["snapshot_head"] = (git(root, "rev-parse", "HEAD") or "").strip()
    state["check_baseline"] = repository_findings(root)  # the stop gate blocks only on new ones
    _save_state(root, state)


def session_changes(root: Path, session: str) -> list[str] | None:
    """Dirty paths whose content differs from the session-start snapshot; None without a snapshot."""
    state = _load_state(root, session)
    snapshot = state.get("snapshot")
    if not isinstance(snapshot, dict):
        return None
    start = str(state.get("snapshot_head", ""))
    committed: list[str] = []
    if start:
        if git(root, "merge-base", "--is-ancestor", start, "HEAD") is None:
            return None  # the start commit is gone or not an ancestor: judge the whole tree
        committed = diff_paths(root, f"{start}..HEAD")
    dirty = [path for path in changed_paths(root) if snapshot.get(path) != _digest(root, path)]
    return sorted(path for path in set(dirty) | set(committed) if path and not path.startswith(".agent/"))  # .agent/ is hook scratch


def session_start(root: Path, event: dict[str, object] | None = None) -> None:
    """The brief names the make targets this project really has (an adopted one runs a colliding target as kit-<name>)."""
    brief = io.StringIO()
    with contextlib.redirect_stdout(brief):
        _session_start(root, event)
    print(rename_mentions(brief.getvalue(), renamed_targets(root)), end="")


def _session_start(root: Path, event: dict[str, object] | None = None) -> None:
    project = load_project(root)
    changed = changed_paths(root)
    try:
        _record_snapshot(root, str((event or {}).get("session_id", "local")), changed)
    except OSError:
        pass  # without a baseline the stop gate falls back to the whole change set
    print("# Session brief (generated by `repoctl hook session-start`; repository facts, AGENTS.md rules; "
          "it also re-syncs stale derived files and may set core.hooksPath, reporting each change below)")
    print(
        f"{project.get('name')} · phase={project.get('phase')} · profile={governance_profile(project)} · "
        f"branch {branch(root)} @ {head(root)} · {len(changed)} uncommitted path(s)"
    )
    recent = (git(root, "log", "-5", "--format=- %h %s") or "").strip()
    if recent:
        print("\nRecent commits:\n" + recent)
    handover = read_text_file(root, HANDOVER)
    if handover:
        clipped = handover[:HANDOVER_LIMIT] + ("\n… (truncated; read HANDOVER.md)" if len(handover) > HANDOVER_LIMIT else "")
        print("\n## HANDOVER.md (read first; verify against the working tree)\n" + clipped)
    if (root / CHECKPOINT).is_file():
        print(f"\nPre-compaction checkpoint available: {CHECKPOINT}")
    healed = _heal_derived(root)
    hooks_note = install_git_hooks(root)
    print()
    print_map(root, limit=MAP_LIMIT)
    try:
        findings = self_heal_errors(root)
    except Exception as error:  # noqa: BLE001 - the brief must survive a broken manifest
        findings = [str(error)]
    if healed:
        findings.insert(0, "regenerated derived files: " + ", ".join(healed))
    if hooks_note:
        findings.insert(0, hooks_note)
    try:
        if _product_on(root):
            step = next_step(root)
            print(f"\n## Next step ({step['phase']})\n{step['action']}\nHow: {step['guide']}. Done when: {step['verify']}.")
    except Exception as error:  # noqa: BLE001 - the brief must survive a malformed feature list
        print(f"\n## Next step\nmake next failed: {error}")
    try:
        plugins = project_plugin_files(root)
    except OSError:
        plugins = []
    if plugins:  # plugins run on every repoctl command and hook: say which ones exist
        print("\n## Project plugins (executed by every repoctl command)\n" + "\n".join(f"- {path}" for path in plugins))
    print("\n## Needs attention")
    print("\n".join(f"- {item}" for item in findings[:15]) or "- nothing: the self-healing checks are green")
    print(
        "\n## Working agreement\n"
        "- You orchestrate and keep the goal; hand a subtask that needs its own context or independence (the critic)\n"
        "  to the roles in .agents/agents/, and do everything else directly. Each role fixes the brief it takes and the\n"
        "  block it returns; reports stay short and cite file:line.\n"
        "- The critic returns one verdict, `blocker` or `ship-with-residuals`; save that block verbatim to\n"
        f"  {CRITIC_RECORD}, which `make done` reads before a high-risk change set can be called done.\n"
        "- Navigate with `make where Q=\"...\"` before broad searching; `make risk` sets the ceremony for your change.\n"
        "- Before declaring done: update the docs that cover what you changed, then `make done`."
        f"\n- Missing a capability? `make similar Q=\"...\"`, then `make new KIND=...` ({', '.join(KINDS[:5])},"
        f"\n  {', '.join(KINDS[5:-1])}, or {KINDS[-1]}) wires it in; outside tools go through the skill-scout role first."
    )


def pre_compact(root: Path) -> None:
    changed = changed_paths(root)
    doc_bindings = docmeta.bindings(root, repository_files(root))
    pending = docsync.pending_documents(doc_bindings, changed)
    lines = [
        "# Pre-compaction checkpoint",
        "",
        f"Written: {datetime.now(timezone.utc).isoformat(timespec='seconds')} on branch {branch(root)} @ {head(root)}.",
        "Compare with `git status`; update HANDOVER.md with goal, decisions, and next action if the work continues.",
        "",
        "## Uncommitted paths",
        *(f"- {path}" for path in changed[:60]),
        "",
        "## Documents that still need updating",
        *([f"- {doc} (covers {', '.join(paths[:5])})" for doc, paths in pending.items()] or ["- none"]),
    ]
    target = root / CHECKPOINT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"checkpoint written to {CHECKPOINT}")


HANDOVER_TEMPLATE = "docs/handoffs/TEMPLATE.md"


def write_handover(root: Path) -> str:
    """Create root HANDOVER.md from the one template with git facts pre-filled."""
    target = root / HANDOVER
    if target.exists():
        return "HANDOVER.md already exists; update it in place (it is never overwritten)."
    template = read_text_file(root, HANDOVER_TEMPLATE)
    if template is None:
        raise RepoctlError(f"{HANDOVER_TEMPLATE} is missing")
    changed = changed_paths(root)
    owed = docsync.pending_documents(docmeta.bindings(root, repository_files(root)), changed)
    facts = {
        "`<timestamp>`": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "`<branch/commit or issue links>`": f"`{branch(root)}` @ `{head(root)}`",
        "`<clean or exact uncommitted paths>`": ", ".join(f"`{path}`" for path in changed[:20]) or "clean",
    }
    text = re.sub(r"(?m)^<!-- index:.*-->\n\n?", "", template)
    for placeholder, value in facts.items():
        text = text.replace(placeholder, value, 1)
    if owed:
        lines = (f"- {doc} (covers {', '.join(paths[:4])})" for doc, paths in owed.items())
        text += "\n## Documents still owed\n\n" + "\n".join(lines) + "\n"
    target.write_text(text, encoding="utf-8")
    return "Wrote HANDOVER.md (ignored). Fill in objective, decisions, blockers, and the exact next action."


def _load_state(root: Path, session: str) -> dict:
    try:
        state = json.loads(state_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    return state if isinstance(state, dict) and state.get("session") == session else {"session": session, "noted": []}


def after_edit(root: Path, event: dict[str, object]) -> None:
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    relative = _relative(root, tool_input.get("file_path") or tool_input.get("notebook_path"))
    if not relative:
        return
    notes = []
    if relative.startswith(".claude/") or relative == ".mcp.json":
        notes.append(f"{relative} is generated. Put the change in .agents/; `make sync` regenerates it.")
    elif relative.startswith(CANONICAL_INPUTS) or relative.endswith(".md"):
        healed = _heal_derived(root)
        if healed:
            notes.append("Derived files regenerated from their sources: " + ", ".join(healed))
    session = str(event.get("session_id", "local"))
    state = _load_state(root, session)
    owned = [doc for doc in docmeta.owners(docmeta.bindings(root, repository_files(root)), relative) if doc not in state["noted"]]
    if owned:
        notes.append(f"{relative} is documented by {', '.join(owned)}; keep it true in this change (the stop gate checks).")
    # Scoped rules arrive when they apply, once per session, instead of living in the router.
    rules = [rule for rule in Registry(root).of("rule")
             if rule.path not in state["noted"] and any(path_matches(relative, pattern) for pattern in rule.fields["scope"])]
    for rule in rules:
        notes.append(f"Rule for {relative}: {rule.description} ({rule.path}).")
    if owned or rules:
        state["noted"] = sorted(set(state["noted"]) | set(owned) | {rule.path for rule in rules})
        _save_state(root, state)
    if notes:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": " ".join(notes)}}))


def finish_findings(root: Path, session_paths: list[str] | None = None, since: str | None = None) -> list[str]:
    """Fast completion gate over this branch's change set (commits since the base plus uncommitted).

    `session_paths` narrows it to the paths one session changed (the stop hook), and
    `since` is the commit that session started at: its commits are judged with their
    Docs-Unaffected trailers, as `make done` judges them. None judges the whole change
    set (`finish`, `make done`).
    """
    project = load_project(root)
    base = default_branch(project)
    scoped = session_paths is not None
    changed = session_paths if session_paths is not None else branch_paths(root, base)
    if not changed:
        return []
    file_set = set(repository_files(root))
    rules = {"dead-bindings", "doc-coupling", "critic-evidence"}
    if not scoped or any(path.startswith(CANONICAL_INPUTS) or path.endswith(".md") for path in changed):
        rules.add("derived-drift")
    change = Change("finish", changed, base=base, scoped=scoped, since=since)
    return registry_findings(root, rules, [path for path in changed if path in file_set], change)


SCISSORS = re.compile(r"(?m)^# -+ >8 -+$")
GATE_BLOCKED = 3  # the hook blocks on any non-zero status except 126/127 (no interpreter or launcher)


def registry_findings(root: Path, names: set[str], scope: list[str] | None, change: Change | None = None) -> list[str]:
    """Blocking findings of the named registry checks over `scope`: the gates' one route to a block.

    A gate decides which rules apply to its change set; the registry decides whether each blocks
    (declaration, then the project's `[checks]` downgrade). A registry that cannot load is itself
    a blocking finding: a gate must never be skipped because the kit it runs on is broken (issue #28).
    """
    try:
        return run_checks(root, blocking_only=True, only=frozenset(names), scope=scope, change=change)[0]
    except Exception as error:  # noqa: BLE001 - an unloadable registry is itself a blocking finding
        return [f"[registry] the capability registry cannot load: {type(error).__name__}: {error} "
                "(fix it, then recommit; `git commit --no-verify` bypasses the gate, say why in the PR)"]


def commit_findings(root: Path, message_file: str | None) -> list[str]:
    """What blocks the staged change set (git commit-msg gate); empty means the commit may proceed."""
    staged = diff_paths(root, "--cached")
    if not staged:
        return []
    try:
        message = Path(message_file).read_text(encoding="utf-8") if message_file else ""
    except OSError:
        message = ""
    # Like git's cleanup: drop everything below the `commit -v` scissors line, then comments.
    message = SCISSORS.split(message, maxsplit=1)[0]
    message = "\n".join(line for line in message.splitlines() if not line.startswith("#"))
    exempt = docsync.exemption_scope(docsync.message_trailers(root, message)) or set()
    file_set = set(repository_files(root))
    # A merge commit brings in commits that already passed this gate or recorded a
    # Docs-Unaffected decision; re-asking would re-litigate it. make done and CI's
    # stale-document check still read those commits' trailers.
    merged_in: set[str] = set()
    if git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD") is not None:
        merged_in = set(diff_paths(root, "HEAD...MERGE_HEAD"))
    rules = {"plugin-load", "doc-coupling"}
    # Derived drift only matters when this commit touches a source of derived files.
    if any(path.startswith(CANONICAL_INPUTS) or path.endswith(".md") for path in staged):
        rules.add("derived-drift")
    change = Change("commit", staged, exempt=frozenset(exempt), merged_in=frozenset(merged_in))
    return registry_findings(root, rules, [path for path in staged if path in file_set], change)


def commit_gate(root: Path, message_file: str | None) -> int:
    """The commit-msg hook's exit status: GATE_BLOCKED when `commit_findings` is not empty."""
    findings = commit_findings(root, message_file)
    if not findings:
        return 0
    print(f"{GATE_COMMIT_BLOCKED} by the self-healing gate (docs/self-healing.md):", file=sys.stderr)
    print("\n".join(f"- {item}" for item in findings[:15]), file=sys.stderr)
    print(
        "Owed doc: update and stage it, or add the trailer 'Docs-Unaffected: <doc.md> <reason>'\n"
        "  (name the doc itself; a code path or glob such as 'tools/** untouched' exempts nothing)\n"
        "  in the message's LAST paragraph (with any Co-Authored-By lines), as git requires.\n"
        "Derived file: run make sync and stage the result.",
        file=sys.stderr,
    )
    return GATE_BLOCKED


def install_git_hooks(root: Path) -> str | None:
    """Point git at .githooks only when that cannot disable hooks already in use."""
    if not (root / ".githooks" / COMMIT_MSG).is_file() or git(root, "rev-parse", "--git-dir") is None:
        return None
    if (git(root, "config", "--get", "core.hooksPath") or "").strip():
        return None
    hooks_dir = (git(root, "rev-parse", "--git-path", "hooks") or "").strip()
    existing = sorted(
        path.name for path in (root / hooks_dir).glob("*")
        if hooks_dir and path.is_file() and not path.name.endswith(".sample")
    )
    if existing:
        return (
            f"git commit gate NOT installed: .git/hooks already has {', '.join(existing)}; call "
            "`.githooks/commit-msg \"$1\"` from your commit-msg hook (or hook manager) to add it"
        )
    if git(root, "config", "core.hooksPath", ".githooks") is None:
        return None
    return "installed git hooks (core.hooksPath=.githooks): commits now run the self-healing gate"


STOP_REPEATS = 5  # pushes per user turn; the cap that keeps a gate from looping an agent forever


def stop(root: Path, event: dict[str, object]) -> None:
    """Block a stop on findings; while the agent continues because of this gate, block again
    only when the findings changed (it is making progress), at most STOP_REPEATS times.

    One push was not enough: in the 2026-10-08 Haiku poster-press trial the agent fixed the
    findings it was shown, introduced two new ones while doing so, and stopped unchecked.
    """
    session = str(event.get("session_id", "local"))
    reason = _stop_reason(root, session)
    state = _load_state(root, session)
    chain = state.get("stop_chain") if isinstance(state.get("stop_chain"), dict) else {}
    if reason is None:
        return
    digest = hashlib.sha256(reason.encode("utf-8")).hexdigest()
    previous = chain.get("count", 0)
    previous = previous if isinstance(previous, int) and not isinstance(previous, bool) else STOP_REPEATS
    if event.get("stop_hook_active"):
        if chain.get("last") == digest or previous >= STOP_REPEATS:
            return  # no progress since the last push, or the cap: the agent may stop and explain
        count = previous + 1
    else:
        count = 1
    state["stop_chain"] = {"count": count, "last": digest}
    try:
        _save_state(root, state)
    except OSError:
        if event.get("stop_hook_active"):
            return  # unrecorded pushes cannot be counted, so never push twice blind: no endless loop
    print(json.dumps({"decision": "block", "reason": reason}))


def _stop_reason(root: Path, session: str) -> str | None:
    paths = session_changes(root, session)
    state = _load_state(root, session)
    since = str(state.get("snapshot_head", "")) or None if paths is not None else None
    findings = finish_findings(root, paths, since)
    if not findings and paths:
        baseline = state.get("check_baseline")
        if isinstance(baseline, list):
            findings = [item for item in repository_findings(root) if item not in baseline]
    if findings:
        reason = f"{GATE_STOP_BLOCKED}:\n" + "\n".join(f"- {item}" for item in findings[:12])
        return reason + "\nFix these (delegate doc work to the doc-gardener role if large), or explain to the user why they stay."
    return _product_drive(root, paths)


def repository_findings(root: Path) -> list[str]:
    """`make check`'s blocking findings. The stop gate blocks on those a session added.

    The change-set gate is narrow by design; without this a session could stop on a
    repository whose `make check` it broke. In the 2026-10-08 Haiku trials, poster-press
    reported "MVP Complete" with five new blocking check findings and nothing stopped it.
    Findings that were there when the session started are not this session's to fix.
    """
    try:
        return run_checks(root, blocking_only=True)[0]
    except Exception as error:  # noqa: BLE001 - an unloadable registry is itself a blocking finding
        return [f"[registry] the capability registry cannot load: {type(error).__name__}: {error}"]


def _product_drive(root: Path, paths: list[str] | None) -> str | None:
    """The product pack's push to keep building; only for a session that changed product code."""
    if not paths or not _product_on(root):
        return None
    try:
        return drive_reason(root, paths)
    except RepoctlError:
        return None  # a broken manifest is the other checks' finding, not a reason to hold the session


def finish(root: Path) -> int:
    findings = finish_findings(root)
    tier, _ = assess(root)
    print(f"Change risk tier: {tier} (details: make risk)")
    if findings:
        print(f"{GATE_NOT_FINISHED}\n" + "\n".join(f"- {item}" for item in findings))
        return 1
    print("Self-healing gate passed for this branch's change set.")
    if not _product_on(root):
        return 0
    summary = product_summary(root)
    if summary:
        print(summary)
    # Advisory per change; the review gates the feature (make next) and the release (make readiness).
    for item in review_status(root):
        print(f"UI review (before the feature is done and before release): {item}")
    return 0


HANDLERS = {
    SESSION_START: lambda root, event: session_start(root, event),
    PRE_COMPACT: lambda root, event: pre_compact(root),
    AFTER_EDIT: lambda root, event: after_edit(root, event),
    STOP: lambda root, event: stop(root, event),
}
HOOK_EVENTS = (*HANDLERS, COMMIT_MSG)


def run_hook(root: Path, event_name: str, message_file: str | None = None) -> int:
    if event_name == COMMIT_MSG:
        try:
            return commit_gate(root, message_file)
        except Exception as error:  # noqa: BLE001 - a gate that crashed has not approved the commit
            print(f"{GATE_COMMIT_BLOCKED}: the gate itself failed: {type(error).__name__}: {error} "
                  "(`git commit --no-verify` bypasses it; say why in the PR)", file=sys.stderr)
            return GATE_BLOCKED
    event = read_event()
    try:
        HANDLERS[event_name](root, event)
    except Exception as error:  # noqa: BLE001 - a hook must never fail the host session
        print(f"repoctl hook {event_name}: {type(error).__name__}: {error}", file=sys.stderr)
    return 0
