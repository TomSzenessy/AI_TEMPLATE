"""Tests for the self-healing kit: bindings, markers, adapters, hooks, navigation."""

from __future__ import annotations

import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import tomllib
import unittest
from datetime import date, timedelta
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPOCTL = TOOLS / "repoctl.py"
sys.path.insert(0, str(TOOLS))

from kit import (ci, commands, coupling, derive, docsync, evals, garden, hygiene, navigate, product,  # noqa: E402
                  reachability, registry, risk, signatures, structure, uireview)
from kit.gitinfo import path_matches  # noqa: E402

# Built by concatenation so this test file never trips the marker scanner itself.
# Template-maintenance tests need the uninitialized template (its seeds and trial requests);
# in a project made from it they skip, so a fresh project's make done stays green.
IN_TEMPLATE = tomllib.loads((TOOLS.parent / "project.toml").read_text(encoding="utf-8")).get("kind") == "template"
template_only = unittest.skipUnless(IN_TEMPLATE, "template maintenance: runs in the template checkout only")

# Fixture dates follow the calendar so the suite never expires (#10).
RECENT = (date.today() - timedelta(days=30)).isoformat()
TASK = "TO" + "DO"
DEPRECATED = "DEPRE" + "CATED"
ANNOTATION = "@" + "deprecated"


class KitRepository(unittest.TestCase):
    """A throwaway git repository with one bound doc, one skill, and one role."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.write("project.toml", """\
            schema = 1
            name = "Demo"
            kind = "web"
            phase = "development"
            [adapters]
            hosts = ["claude"]
            [budgets]
            "AGENTS.md" = 200
            [risk]
            high = ["src/auth/**"]
            low = ["docs/**"]
            """)
        self.write("resources.toml", """\
            schema = 1
            [[resources]]
            id = "docs"
            kind = "library-docs"
            source = "https://example.com/"
            trust = "official"
            access = "read-only"
            scope = "web"
            summary = "Example docs."
            """)
        self.write(".agents/mcp/browser.toml", """\
            name = "browser"
            description = "Drive a browser for UI checks."
            transport = "stdio"
            command = ["npx", "-y", "@example/mcp@1.2.3"]
            enabled = true
            """)
        self.write("Makefile", "check:\n\t@true\nverify:\n\t@true\n")
        self.write("AGENTS.md", "# Agents\n")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 1\n")
        self.write("src/auth/login.py", "def login():\n    return True\n")
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nRun `make check`.\n")
        self.write(".agents/skills/demo-skill/SKILL.md", "---\nname: demo-skill\ndescription: Render invoices for billing customers.\n---\n\n# Demo\n")
        self.write(".agents/agents/scout.md", "---\nname: scout\ndescription: Read-only locator for files.\naccess: read-only\ntier: fast\n---\n\n# Scout\n")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        derive.sync(self.root)
        self.commit("initial")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
        return path

    def git(self, *arguments: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *arguments], check=True, capture_output=True, text=True).stdout

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def cli(self, *arguments: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPOCTL), "--root", str(self.root), *arguments],
            input=stdin, capture_output=True, text=True, check=False,
        )

    # The fixture is a bare repository, not an initialized project: skip the repository-contract checks.
    # Its files (a role, a skill, an MCP route, resources.toml) are capability carriers nothing names,
    # so the compactness gate would report every one of them; OrphanFileTests covers that gate directly.
    CONTRACT = frozenset({"manifest-structure", "skill-provenance", "file-hygiene", "markdown-links", "docs-index",
                          "orphan-files", "host-read-config"})

    def self_heal(self) -> str:
        """The self-healing findings `make check` adds on top of the repository-contract checks."""
        hard, _ = registry.run_checks(self.root, blocking_only=True, skip=self.CONTRACT)
        return "\n".join(hard + docsync.index_errors(self.root, self.files()))

    def files(self) -> list[str]:
        return [line for line in self.git("ls-files").splitlines() if line]


class GlobTests(unittest.TestCase):
    def test_repository_globs(self) -> None:
        self.assertTrue(path_matches("src/a/b.py", "src/**"))
        self.assertTrue(path_matches("b.md", "**/*.md"))
        self.assertTrue(path_matches("docs/x/y.md", "**/*.md"))
        self.assertTrue(path_matches(".agents/skills/x/SKILL.md", ".agents/skills/*/SKILL.md"))
        self.assertTrue(path_matches("src/a.py", "./src/a.py"))
        self.assertFalse(path_matches("src/a/b.py", "src/*.py"))
        self.assertFalse(path_matches("xsrc/a.py", "src/**"))


class DocSyncTests(KitRepository):
    def test_binding_and_owner_lookup(self) -> None:
        doc_bindings = docsync.bindings(self.root, self.files())
        self.assertEqual(doc_bindings, {"docs/billing.md": ["src/billing/**"]})
        self.assertEqual(docsync.owners(doc_bindings, "src/billing/invoice.py"), ["docs/billing.md"])

    def test_inline_code_examples_are_not_bindings(self) -> None:
        self.write("docs/guide.md", "# Guide\n\nWrite `<!-- covers: nowhere/** -->` near the top.\n")
        self.assertNotIn("docs/guide.md", docsync.bindings(self.root, self.files() + ["docs/guide.md"]))

    def test_dead_binding_is_a_finding(self) -> None:
        (self.root / "src/billing/invoice.py").unlink()
        self.commit("remove billing")
        self.assertIn("covers pattern matches no file: src/billing/**", self.self_heal())

    def test_stale_document_fails_until_doc_or_trailer(self) -> None:
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 2\n")
        self.commit("change billing")
        self.assertIn("docs/billing.md: stale since", self.self_heal())
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nReturns 2. Run `make check`.\n")
        self.commit("update billing doc")
        self.assertEqual(self.self_heal(), "")

    def test_docs_unaffected_trailer_exempts_commit(self) -> None:
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 1  # clearer\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "refactor billing\n\nDocs-Unaffected: docs/billing.md comment only")
        self.assertEqual(self.self_heal(), "")

    def test_missing_make_target_reference_fails(self) -> None:
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nRun `make deploy`.\n")
        errors = docsync.command_reference_errors(self.root, self.files())
        self.assertEqual(errors, ["docs/billing.md: references missing make target: make deploy"])

    def test_make_references_resolve_to_the_nearest_makefile(self) -> None:
        self.write("services/api/Makefile", "serve:\n\techo serve\n")
        self.write("services/api/README.md", "# API\n\nRun `make serve`.\n")
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nRun `make serve`.\n")
        errors = docsync.command_reference_errors(self.root, self.files())
        self.assertEqual(errors, ["docs/billing.md: references missing make target: make serve"])


class HygieneTests(KitRepository):
    def test_markers(self) -> None:
        self.write("src/old.py", textwrap.dedent(f"""\
            # {DEPRECATED}(remove-by=2020-01-01, use=new)
            # {DEPRECATED}(remove-by=2999-01-01, use=new)
            # {TASK}: tidy this
            # {TASK}(#12): tracked
            # {ANNOTATION} without a date
            """))
        report = hygiene.scan_markers(self.root, ["src/old.py"], today=date(2026, 1, 1))
        self.assertEqual(report.expired, ["src/old.py:1 (remove-by 2020-01-01)"])
        self.assertEqual(report.orphan_tasks, ["src/old.py:3"])
        self.assertEqual(report.undated, ["src/old.py:5"])
        soon = hygiene.scan_markers(self.root, ["src/old.py"], today=date(2998, 12, 20))
        self.assertIn("src/old.py:2 (remove-by 2999-01-01)", soon.upcoming)

    def test_markdown_task_words_are_not_code_markers(self) -> None:
        self.write("docs/notes.md", f"# Notes\n\nA {TASK} in prose belongs in an issue, but prose is not scanned.\n")
        self.assertEqual(hygiene.scan_markers(self.root, ["docs/notes.md"]).errors, [])

    def test_repeated_paragraph_is_reported(self) -> None:
        paragraph = " ".join(f"word{index}" for index in range(60))
        self.write("docs/a.md", f"# A\n\n{paragraph}\n")
        self.write("docs/b.md", f"# B\n\nIntro.\n\n{paragraph}\n")
        findings = hygiene.duplicate_paragraphs(self.root, ["docs/a.md", "docs/b.md", "docs/billing.md"])
        self.assertEqual(len(findings), 1)
        self.assertIn("docs/a.md and docs/b.md repeat a paragraph", findings[0])

    def test_long_inline_workflow_script_is_a_finding(self) -> None:
        script = "\n".join(f"          echo step {index}" for index in range(12))
        self.write(".github/workflows/x.yml", f"jobs:\n  a:\n    steps:\n      - name: s\n        run: |\n{script}\n      - name: t\n        run: make verify\n")
        findings = hygiene.workflow_errors(self.root, [".github/workflows/x.yml"])
        self.assertEqual(len(findings), 1)
        self.assertIn("x.yml:5: inline run block of 12 lines", findings[0])

    def test_budget_is_a_finding(self) -> None:
        self.write("AGENTS.md", "# Agents\n" + "x" * 400)
        self.commit("grow router")
        self.assertIn("over its 200-byte budget", self.self_heal())


class AdapterTests(KitRepository):
    def test_generated_stubs_redirect_without_content(self) -> None:
        skill = (self.root / ".claude/skills/demo-skill/SKILL.md").read_text()
        self.assertIn("description: \"Render invoices for billing customers.\"", skill)
        self.assertIn(".agents/skills/demo-skill/SKILL.md", skill)
        self.assertNotIn("# Demo", skill)
        role = (self.root / ".claude/agents/scout.md").read_text()
        self.assertIn("tools: Read, Grep, Glob, Bash", role)
        self.assertIn("model: haiku", role)
        mcp = json.loads((self.root / ".mcp.json").read_text())
        self.assertEqual(mcp["mcpServers"]["browser"], {"command": "npx", "args": ["-y", "@example/mcp@1.2.3"]})
        settings = json.loads((self.root / ".claude/settings.json").read_text())
        self.assertIn("Stop", settings["hooks"])
        self.assertNotIn("enabledMcpjsonServers", settings, "servers must stay approved per person")

    def test_folded_description_survives_into_stub(self) -> None:
        self.write(".agents/skills/demo-skill/SKILL.md", "---\nname: demo-skill\ndescription: >-\n  Render invoices: for billing\n  customers \"fast\".\n---\n")
        derive.sync(self.root)
        stub = (self.root / ".claude/skills/demo-skill/SKILL.md").read_text()
        self.assertIn('description: "Render invoices: for billing customers \\"fast\\"."', stub)
        self.assertEqual(navigate.skill_overlap(self.root, "render invoices billing")[0][1], "skill:demo-skill")

    def test_disabling_every_route_clears_host_mcp_config(self) -> None:
        self.write(".agents/mcp/browser.toml", (self.root / ".agents/mcp/browser.toml").read_text().replace("enabled = true", "enabled = false"))
        derive.sync(self.root)
        self.assertEqual(json.loads((self.root / ".mcp.json").read_text()), {"mcpServers": {}})

    def test_drift_and_stray_files_fail_check(self) -> None:
        self.write(".agents/skills/demo-skill/SKILL.md", "---\nname: demo-skill\ndescription: Changed purpose.\n---\n")
        self.write(".claude/commands/handwritten.md", "# my own command\n")
        result = self.cli("sync", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("derived file out of date: .claude/skills/demo-skill/SKILL.md", result.stderr)
        self.assertIn("hand-authored file in a generated host directory: .claude/commands/handwritten.md", result.stderr)

    def test_sync_removes_only_generated_orphans(self) -> None:
        (self.root / ".agents/skills/demo-skill/SKILL.md").unlink()
        changed = derive.sync(self.root)
        self.assertIn("removed .claude/skills/demo-skill/SKILL.md", changed)
        self.assertFalse((self.root / ".claude/skills/demo-skill").exists())

    def test_unpinned_stdio_route_is_rejected(self) -> None:
        text = (self.root / ".agents/mcp/browser.toml").read_text().replace("@example/mcp@1.2.3", "@example/mcp@latest")
        self.write(".agents/mcp/browser.toml", text)
        with self.assertRaisesRegex(Exception, "must pin its package"):
            registry.Registry(self.root).of("mcp")

    def test_frontmatter_colon_must_be_quoted(self) -> None:
        self.write(".agents/agents/scout.md", "---\nname: scout\ndescription: Locator: finds files.\naccess: read-only\ntier: fast\n---\n")
        with self.assertRaisesRegex(Exception, "quote it"):
            registry.Registry(self.root).of("agent")


class HookTests(KitRepository):
    def test_stop_blocks_once_when_covered_code_changes_without_doc(self) -> None:
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 3\n")
        result = self.cli("hook", "stop", stdin=json.dumps({"stop_hook_active": False}))
        decision = json.loads(result.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("docs/billing.md covers changed src/billing/invoice.py", decision["reason"])
        again = self.cli("hook", "stop", stdin=json.dumps({"stop_hook_active": True}))
        self.assertEqual(again.stdout, "")
        self.assertEqual(self.cli("finish").returncode, 1)

    def test_stop_passes_when_doc_updated(self) -> None:
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 3\n")
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nReturns 3. `make check`.\n")
        self.assertEqual(self.cli("hook", "stop", stdin="{}").stdout, "")
        self.assertEqual(self.cli("finish").returncode, 0)

    def test_stop_checks_branch_commits_not_only_worktree(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 4\n")
        self.commit("feature change")
        decision = json.loads(self.cli("hook", "stop", stdin="{}").stdout)
        self.assertIn("docs/billing.md", decision["reason"])

    def test_finish_predicts_the_commit_gate(self) -> None:
        # The doc changed earlier on the branch, but the next commit gate asks again.
        self.git("checkout", "-q", "-b", "feature")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 4\n")
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nReturns 4. `make check`.\n")
        self.commit("feature change with doc")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 5\n")
        self.assertEqual(self.cli("finish").returncode, 1)
        self.git("add", "-A")
        self.assertEqual(self.cli("hook", "commit-msg", str(self.write(".git/MSG", "more\n"))).returncode, 3)

    def test_docs_unaffected_trailer_satisfies_stop_gate(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 1  # comment only\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "tidy\n\nDocs-Unaffected: docs/billing.md comment only")
        self.assertEqual(self.cli("hook", "stop", stdin="{}").stdout, "")
        self.assertEqual(self.cli("finish").returncode, 0)
        self.assertEqual(self.self_heal(), "")

    def test_hooks_survive_a_broken_manifest(self) -> None:
        self.write("resources.toml", "schema = [broken\n")
        for event in ("session-start", "stop", "after-edit", "pre-compact"):
            result = self.cli("hook", event, stdin="{}")
            self.assertEqual(result.returncode, 0, (event, result.stderr))
            self.assertNotIn("Traceback", result.stderr)

    def test_after_edit_names_owner_once_and_heals_adapters(self) -> None:
        event = {"session_id": "s1", "tool_input": {"file_path": str(self.root / "src/billing/invoice.py")}}
        first = json.loads(self.cli("hook", "after-edit", stdin=json.dumps(event)).stdout)
        self.assertIn("documented by docs/billing.md", first["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.cli("hook", "after-edit", stdin=json.dumps(event)).stdout, "")
        self.write(".agents/skills/demo-skill/SKILL.md", "---\nname: demo-skill\ndescription: New purpose.\n---\n")
        event = {"session_id": "s1", "tool_input": {"file_path": str(self.root / ".agents/skills/demo-skill/SKILL.md")}}
        healed = json.loads(self.cli("hook", "after-edit", stdin=json.dumps(event)).stdout)
        self.assertIn("regenerated", healed["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.cli("sync", "--check").returncode, 0)

    def test_session_start_and_pre_compact(self) -> None:
        self.write("HANDOVER.md", "# Handover\nNext action: ship billing.\n")
        brief = self.cli("hook", "session-start", stdin="{}").stdout
        self.assertIn("Next action: ship billing.", brief)
        self.assertIn("docs/billing.md ← src/billing/**", brief)
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 5\n")
        self.cli("hook", "pre-compact", stdin="{}")
        checkpoint = (self.root / ".agent/checkpoint.md").read_text()
        self.assertIn("docs/billing.md (covers src/billing/invoice.py)", checkpoint)

    def test_hook_never_crashes_on_garbage_input(self) -> None:
        result = self.cli("hook", "after-edit", stdin="not json")
        self.assertEqual(result.returncode, 0)


class CommitGateTests(KitRepository):
    def message(self, text: str) -> str:
        path = self.root / ".git" / "COMMIT_EDITMSG"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_blocks_staged_covered_change_without_doc(self) -> None:
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 9\n")
        self.git("add", "src/billing/invoice.py")
        result = self.cli("hook", "commit-msg", self.message("change billing\n"))
        self.assertEqual(result.returncode, 3)
        self.assertIn("docs/billing.md covers staged src/billing/invoice.py", result.stderr)

    def test_trailer_or_staged_doc_passes(self) -> None:
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 9\n")
        self.git("add", "src/billing/invoice.py")
        trailer = self.message("tidy\n\nDocs-Unaffected: docs/billing.md rename only\n")
        self.assertEqual(self.cli("hook", "commit-msg", trailer).returncode, 0)
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nReturns 9. `make check`.\n")
        self.git("add", "docs/billing.md")
        self.assertEqual(self.cli("hook", "commit-msg", self.message("change billing\n")).returncode, 0)

    def test_commented_trailer_does_not_count(self) -> None:
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 9\n")
        self.git("add", "src/billing/invoice.py")
        commented = self.message("change\n# Docs-Unaffected: docs/billing.md\n")
        self.assertEqual(self.cli("hook", "commit-msg", commented).returncode, 3)

    def test_merge_commit_defers_to_merged_commits(self) -> None:
        # The branch commit recorded its decision; merging it must not ask again.
        self.git("checkout", "-q", "-b", "side")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 9\n")
        self.git("add", "src/billing/invoice.py")
        self.git("commit", "-q", "-m", "tidy\n\nDocs-Unaffected: docs/billing.md rename only")
        self.git("checkout", "-q", "-")
        self.write("README.md", "# Other work\n")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "other")
        self.git("merge", "-q", "--no-commit", "--no-ff", "side")
        self.assertEqual(self.cli("hook", "commit-msg", self.message("Merge side\n")).returncode, 0)
        # Code staged on top of the merge is not covered by the merged commits' decisions.
        self.write("src/billing/extra.py", "X = 1\n")
        self.git("add", "src/billing/extra.py")
        self.assertEqual(self.cli("hook", "commit-msg", self.message("Merge side\n")).returncode, 3)

    def test_installed_git_hook_blocks_commit(self) -> None:
        hooks = self.root / ".githooks"
        hooks.mkdir()
        (hooks / "commit-msg").write_text((TOOLS.parent / ".githooks" / "commit-msg").read_text())
        (hooks / "commit-msg").chmod(0o755)
        (self.root / "tools").symlink_to(TOOLS, target_is_directory=True)
        self.assertIn("installed git hooks", self.cli("hook", "session-start", stdin="{}").stdout)
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 9\n")
        self.git("add", "src/billing/invoice.py")
        blocked = subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "x"], capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("Commit blocked", blocked.stderr)

    def test_deleted_tracked_file_does_not_break_checks(self) -> None:
        (self.root / "src/auth/login.py").unlink()
        self.assertNotIn("No such file", self.self_heal())


class CriticRegressionTests(KitRepository):
    """Round-two critic findings: hook safety and one trailer parser everywhere."""

    def gate(self, message: str) -> int:
        path = self.root / ".git" / "COMMIT_EDITMSG"
        path.write_text(message, encoding="utf-8")
        return self.cli("hook", "commit-msg", str(path)).returncode

    def stage_billing_change(self) -> None:
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 11\n")
        self.git("add", "src/billing/invoice.py")

    def test_existing_git_hooks_are_never_disabled(self) -> None:
        (self.root / ".githooks").mkdir()
        (self.root / ".githooks" / "commit-msg").write_text("#!/bin/sh\nexit 0\n")
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 0\n")
        hook.chmod(0o755)
        brief = self.cli("hook", "session-start", stdin="{}").stdout
        self.assertIn("git commit gate NOT installed", brief)
        result = subprocess.run(["git", "-C", str(self.root), "config", "--get", "core.hooksPath"], capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "")

    def test_bare_or_misplaced_trailer_exempts_nothing_in_gate_or_history(self) -> None:
        self.stage_billing_change()
        self.assertEqual(self.gate("change\n\nDocs-Unaffected:\n"), 3)
        self.assertEqual(self.gate("change\n\nDocs-Unaffected: docs/billing.md\n"), 3, "a reason is required")
        self.assertEqual(self.gate("change\n\nDocs-Unaffected: docs/billing.md cosmetic\n\nMore text.\n"), 3)
        self.git("commit", "-q", "-m", "change\n\nDocs-Unaffected:")
        self.assertIn("docs/billing.md: stale since", self.self_heal())

    def test_non_document_scope_exempts_nothing(self) -> None:
        # Build trial: a preemptive "tools/** untouched" silently exempted every doc.
        self.stage_billing_change()
        self.assertEqual(self.gate("change\n\nDocs-Unaffected: tools/** untouched\n"), 3)
        self.assertEqual(self.gate("change\n\nDocs-Unaffected: src/billing/** renamed only\n"), 3)
        self.assertEqual(self.gate("change\n\nDocs-Unaffected: src/billing/invoice.py renamed only\n"), 3)
        self.assertEqual(self.gate("change\n\nDocs-Unaffected: UI/UX wording only\n"), 0, "prose stays a reason")
        self.assertEqual(self.gate("change\n\nDocs-Unaffected: rename only, no behavior change\n"), 0)

    def test_trailer_with_trailing_period_names_only_that_doc(self) -> None:
        self.stage_billing_change()
        self.assertEqual(self.gate("change\n\nDocs-Unaffected: docs/billing.md. cosmetic rename\n"), 0)
        self.git("commit", "-q", "-m", "change\n\nDocs-Unaffected: docs/billing.md. cosmetic rename")
        self.assertEqual(self.self_heal(), "")

    def test_verbose_commit_diff_below_scissors_is_ignored(self) -> None:
        self.stage_billing_change()
        message = (
            "change\n\nDocs-Unaffected: docs/billing.md comment only\n"
            "# Please enter the commit message.\n"
            "# ------------------------ >8 ------------------------\n"
            "# Do not modify or remove the line above.\n"
            "diff --git a/src/billing/invoice.py b/src/billing/invoice.py\n+    return 11\n"
        )
        self.assertEqual(self.gate(message), 0)
        verbose = subprocess.run(
            ["git", "-C", str(self.root), "-c", "core.hooksPath=/dev/null", "commit", "-q", "-v",
             "-m", "change\n\nDocs-Unaffected: docs/billing.md comment only"],
            capture_output=True, text=True,
        )
        self.assertEqual(verbose.returncode, 0, verbose.stderr)
        self.assertEqual(self.self_heal(), "")

    def test_unstaged_derived_drift_does_not_block_unrelated_commit(self) -> None:
        self.write(".agents/agents/scout.md", "---\nname: scout\ndescription: Changed locator text.\naccess: read-only\ntier: fast\n---\n")
        self.write("notes.txt", "notes\n")
        self.git("add", "notes.txt")
        self.assertEqual(self.gate("notes\n"), 0)

    def test_similar_names_are_refused(self) -> None:
        self.write("project.toml", (self.root / "project.toml").read_text() + "[capabilities]\nlocal_skills = []\n")
        result = self.cli("new", "--kind", "skill", "--name", "demo-renderer",
                          "--description", "Produce billing documents for invoice workflows quickly.")
        self.assertEqual(result.returncode, 1)
        self.assertIn("too similar to skill:demo-skill", result.stderr)


class ProjectGuardrailTests(KitRepository):
    """Steps a fresh agent skipped in the build trial are now checked."""

    def ui_project(self, oracle: str = "typecheck and tests") -> None:
        text = (self.root / "project.toml").read_text().replace('kind = "web"', 'kind = "web"\nowners = ["me@example.com"]')
        text += f'''[vision]
status = "accepted"
[[surfaces]]
id = "app"
path = "src"
kind = "code"
owner = "me@example.com"
quality_oracle = "{oracle}"
verification = [["true"]]
'''
        self.write("project.toml", text)

    def test_guardrails_name_each_skipped_step(self) -> None:
        self.ui_project()
        self.write("docs/LOCAL-WAL.md", "# WAL\n")
        findings = self.self_heal()
        self.assertIn("docs/LOCAL-WAL.md: live work belongs in issues", findings)
        self.assertIn("UI project without docs/design.md", findings)
        self.assertNotIn("quality_oracle", findings, "retired: a keyword in prose is not a review")
        self.assertEqual(findings.count("looks like an email"), 1)
        self.assertNotIn("has no owning doc", findings, "docs/billing.md covers src/billing/**")

    def test_surface_without_owning_doc(self) -> None:
        self.ui_project("tests plus ux-quality screenshot review")
        self.write("docs/billing.md", "# Billing\n\nNo binding any more.\n")
        self.assertIn('surface app (src) has no owning doc', self.self_heal())

    def test_issue_without_github_target_becomes_local_wal(self) -> None:
        self.write("project.toml", (self.root / "project.toml").read_text() + '[governance]\nprofile = "agent-first"\n')
        self.write(".github/issue-labels.json", (TOOLS.parent / ".github/issue-labels.json").read_text())
        self.write("issue.md", DUPLICATE_LINE + "### Summary\nAdd a habit and check in today.\n"
                   "### Acceptance criteria\n- [ ] The add test passes.\n- [ ] An empty name does not pass.\n"
                   "### Evidence\nTest: unit output\n### Disclosure classification\n- **Disclosure class:** ordinary\n"
                   "- **Public-safe:** yes\n- **Security/privacy review:** not applicable\n- **Reviewer/date:** tester " + RECENT + "\n"
                   "### Dependencies and handoff\n- **Owner / next action:** maintainer\n")
        result = self.cli("issue", "--title", "First slice", "--body-file", "issue.md", "--type", "task",
                          "--priority", "P2", "--area", "web", "--topic", "first-slice", "--status", "ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Local-WAL-001", result.stdout)
        self.assertTrue((self.root / ".agent/wal/001-first-slice.md").is_file())

    def test_local_wal_drafts_are_filed_once_a_remote_exists(self) -> None:
        self.write(".github/issue-labels.json", (TOOLS.parent / ".github/issue-labels.json").read_text())
        self.write("draft.md", "### Summary\nShare a trip by link.\n### Acceptance criteria\n- [ ] A second browser sees the trip.\n")
        arguments = ("issue", "--title", "Share by link", "--body-file", "draft.md", "--type", "task",
                     "--priority", "P2", "--area", "web", "--topic", "share-link")
        self.assertIn("Local-WAL-001", self.cli(*arguments).stdout)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text("#!/bin/sh\ncase \"$1 $2\" in\n  'issue list') echo '[]';;\n"
                                    "  'issue create') echo https://github.com/example/demo/issues/7;;\nesac\n")
        (bin_dir / "gh").chmod(0o755)
        environment = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
        self.write("project.toml", (self.root / "project.toml").read_text().replace("[adapters]", '[repository]\ngithub = "example/demo"\n\n[adapters]', 1))
        filing = lambda: subprocess.run([sys.executable, str(REPOCTL), "--root", str(self.root), "issue", "--wal", "all"],
                                        capture_output=True, text=True, env=environment)
        first = filing()
        self.assertEqual(first.returncode, 1, "a draft must meet the full contract before it is public")
        self.assertIn("missing headings", first.stdout)
        draft = next((self.root / ".agent/wal").glob("001-*.md"))
        header, _, _ = draft.read_text().partition("### Summary")
        full = (DUPLICATE_LINE + "### Summary\nShare a trip by link.\n### Acceptance criteria\n- [ ] A second browser sees "
                "the trip (e2e test).\n- [ ] A wrong link does not open a trip.\n### Evidence\nTest: e2e\n"
                "### Disclosure classification\n- **Disclosure class:** ordinary\n- **Public-safe:** yes\n"
                "- **Security/privacy review:** not applicable\n- **Reviewer/date:** tester " + RECENT + "\n"
                "### Dependencies and handoff\n- **Owner / next action:** maintainer\n")
        draft.write_text(header + full)
        second = filing()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("Local-WAL-001 -> https://github.com/example/demo/issues/7", second.stdout)
        self.assertTrue(draft.read_text().startswith("Filed: https://github.com/example/demo/issues/7"))
        self.assertEqual(filing().returncode, 0, "a filed draft is skipped")

    def test_local_draft_needs_only_outcome_and_criteria(self) -> None:
        self.write(".github/issue-labels.json", (TOOLS.parent / ".github/issue-labels.json").read_text())
        arguments = ("issue", "--title", "Second slice", "--body-file", "draft.md", "--type", "task",
                     "--priority", "P2", "--area", "web", "--topic", "second-slice", "--status", "triage")
        self.write("draft.md", "### Summary\nShare a trip by link.\n### Acceptance criteria\n- [ ] A second browser sees the trip.\n")
        result = self.cli(*arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Local-WAL-001", result.stdout)
        self.write("draft.md", "### Summary\nShare a trip by link.\n")
        self.assertIn("at least one '- [ ]", self.cli(*arguments).stderr)
        self.write("project.toml", (self.root / "project.toml").read_text().replace("[adapters]", '[repository]\ngithub = "example/demo"\n\n[adapters]', 1))
        self.write("draft.md", "### Summary\nShare a trip by link.\n### Acceptance criteria\n- [ ] A second browser sees the trip.\n")
        self.assertIn("missing headings", self.cli(*arguments).stderr, "the full contract applies when filing for real")


class ProductDriverTests(KitRepository):
    """make next walks a UI product from intake to launch; done means features evidenced."""

    def phase(self) -> str:
        return product.next_step(self.root)["phase"]

    def accept_vision(self) -> None:
        self.write("project.toml", (self.root / "project.toml").read_text() + '[vision]\nstatus = "accepted"\n')

    def features(self, *rows: str) -> None:
        self.write(product.FEATURES, "feature,area,priority,status,evidence,acceptance,source\n" + "\n".join(rows) + "\n")

    def test_phases_in_order(self) -> None:
        self.assertEqual(self.phase(), "intake")
        self.accept_vision()
        self.assertEqual(self.phase(), "research")
        self.write(product.RESEARCH, "# Research\nhttps://a.example https://b.example https://c.example\n")
        self.assertEqual(self.phase(), "features")
        self.features("Add a habit,core,must,no,,Adding takes one tap,owner")
        self.assertEqual(self.phase(), "design")
        self.write("docs/design.md", "# Design\n")
        self.assertEqual(self.phase(), "design", "a stub design doc is not a design record")
        self.write("docs/design.md", "# Design\n\n" + "Calm, minimal direction with one indigo accent. " * 10)
        self.assertEqual(self.phase(), "stack")
        self.write("docs/STACK-DECISION.md", "# Stack\n\n**Status:** accepted\n")
        self.assertEqual(self.phase(), "skeleton")
        surface = '[[surfaces]]\nid = "app"\npath = "src"\nkind = "code"\nquality_oracle = "tests plus ux-quality review"\nverification = [["true"]]\n'
        self.write("project.toml", (self.root / "project.toml").read_text() + surface)
        self.assertEqual(self.phase(), "preview")
        self.write("project.toml", (self.root / "project.toml").read_text()
                   + '[surfaces.preview]\ncommand = ["true"]\nurl = "http://localhost:4999"\n')
        step = product.next_step(self.root)
        self.assertEqual(step["phase"], "build")
        self.assertIn("Add a habit", step["action"])
        self.write("tests/test_habits.py", "def test_add():\n    assert True\n")
        self.features("Add a habit,core,must,yes,tests/test_habits.py,Adding takes one tap,owner")
        self.assertEqual(self.phase(), "review")
        self.assertIn("never had a UI review", product.next_step(self.root)["action"])

    def test_score_and_evidence(self) -> None:
        self.write("tests/test_a.py", "def test_a():\n    assert True\n")
        self.features(
            "A,core,must,yes,tests/test_a.py,works,owner",
            "B,core,must,partial,missing/file.py,works,owner",
            "C,core,should,no,,,owner",
            "D,core,could,skip,,,owner",
        )
        percent, open_must = product.score(product.load_features(self.root))
        self.assertAlmostEqual(percent, 100 * (3 + 1.5) / 8)
        self.assertEqual([row["feature"] for row in open_must], ["B"])
        errors = product.feature_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("'B' (partial) cites evidence that is not an existing file: missing/file.py", errors[0])

    def test_evidence_cannot_be_gamed(self) -> None:
        self.features("A,core,must,yes,README.md,works,owner", "B,core,should,yes,.,works,owner")
        self.write("README.md", "# Demo\n")
        errors = " ".join(product.feature_errors(self.root))
        self.assertIn("without a test file", errors)
        self.assertIn("not an existing file: .", errors)
        self.features("C,core,should,no,,,owner")
        self.assertIn("needs at least one must row", " ".join(product.feature_errors(self.root)))

    def test_must_needs_acceptance_and_valid_values(self) -> None:
        self.features("A,core,must,no,,,owner")
        self.assertIn("needs an acceptance criterion", product.feature_errors(self.root)[0])
        self.features("A,core,urgent,no,,x,owner")
        self.assertIn("priority must be", product.feature_errors(self.root)[0])

    def test_research_required_for_ui_product_surface(self) -> None:
        self.accept_vision()
        self.write("project.toml", (self.root / "project.toml").read_text()
                   + '[[surfaces]]\nid = "app"\npath = "src"\nkind = "code"\nquality_oracle = "ux-quality"\n')
        project = garden.load_project(self.root)
        self.assertIn("at least three cited sources", product.research_errors(self.root, project)[0])
        self.write(product.RESEARCH, "https://a.example https://b.example https://c.example\n")
        self.assertEqual(product.research_errors(self.root, project), [])

    def test_done_prints_product_summary(self) -> None:
        self.features("A,core,must,no,,works,owner")
        self.assertIn("NOT done: 1 must feature(s) open (A)", product.product_summary(self.root))


class UiReviewTests(KitRepository):
    def setUp(self) -> None:
        super().setUp()
        import socket
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.write("project.toml", (self.root / "project.toml").read_text()
                   + '[[surfaces]]\nid = "app"\npath = "src"\nkind = "code"\nquality_oracle = "ux-quality"\n'
                   + f'[surfaces.preview]\ncommand = ["{sys.executable}", "-m", "http.server", "{{port}}", "--bind", "127.0.0.1"]\n'
                   + 'url = "http://localhost:{port}"\nroutes = ["/"]\n')
        bin_dir = self.root / "fakebin"
        bin_dir.mkdir()
        for name in ("npx", "playwright"):  # stand in for Playwright: write the screenshot file asked for
            fake = bin_dir / name
            fake.write_text("#!/bin/sh\nfor last; do :; done\nprintf png > \"$last\"\n")
            fake.chmod(0o755)
        self.environment = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}

    def review(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(REPOCTL), "--root", str(self.root), "ui-review"],
                              capture_output=True, text=True, env=self.environment, check=False)

    def test_refuses_a_server_it_did_not_start(self) -> None:
        foreign = subprocess.Popen([sys.executable, "-m", "http.server", str(self.port), "--bind", "127.0.0.1"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(1)
            text = (self.root / "project.toml").read_text().replace("{port}", str(self.port))
            self.write("project.toml", text)
            result = self.review()
            self.assertEqual(result.returncode, 1)
            self.assertIn("something already answers", result.stderr)
        finally:
            foreign.terminate()
            foreign.wait()

    def test_route_without_leading_slash_is_rejected(self) -> None:
        self.write("project.toml", (self.root / "project.toml").read_text().replace('routes = ["/"]', 'routes = ["about"]'))
        result = self.review()
        self.assertEqual(result.returncode, 1)
        self.assertIn("routes must start with '/'", result.stderr)

    def test_dead_preview_fails_fast(self) -> None:
        text = (self.root / "project.toml").read_text()
        text = text.replace(f'command = ["{sys.executable}", "-m", "http.server", "{{port}}", "--bind", "127.0.0.1"]',
                            f'command = ["{sys.executable}", "-c", "raise SystemExit(7)"]')
        self.write("project.toml", text)
        result = self.review()
        self.assertEqual(result.returncode, 1)
        self.assertIn("exited with code 7", result.stderr)

    def test_review_captures_sizes_and_schemes_then_needs_verdict_and_freshness(self) -> None:
        self.write("docs/README.md", "# Index\n\n<!-- repoctl:index -->\n<!-- /repoctl:index -->\n")
        derive.sync(self.root)
        self.assertIn("never had a UI review", " ".join(uireview.review_status(self.root)))
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr)
        run = uireview.latest_records(self.root)["app"][0]
        shots = sorted(path.name for path in (self.root / uireview.SHOTS / run).glob("*.png"))
        self.assertEqual(len(shots), 4)
        self.assertIn("app-home-default-phone-dark.png", shots)
        log = self.root / uireview.LOG
        self.assertIn("is not `Verdict: pass`", " ".join(uireview.review_status(self.root)))
        log.write_text(log.read_text().replace("Verdict: pending", "Verdict: fix - contrast"))
        self.assertIn("is not `Verdict: pass`", " ".join(uireview.review_status(self.root)), "fix must not pass")
        log.write_text(log.read_text().replace("Verdict: fix - contrast", "Verdict: pass"))
        self.assertEqual(uireview.review_status(self.root), [])
        self.assertIn("<!-- index:", log.read_text(), "the tracked log indexes itself")
        self.assertEqual(derive.drift(self.root), [], "the review regenerates the docs index it changed")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 42\n")
        self.assertIn("changed since UI review", " ".join(uireview.review_status(self.root)))

    def test_installed_playwright_wins_unless_pinned(self) -> None:
        os.environ["PATH"], saved = self.environment["PATH"], os.environ["PATH"]
        try:
            self.assertTrue(uireview._playwright(self.root)[0].endswith("fakebin/playwright"))
            self.write("project.toml", (self.root / "project.toml").read_text() + '[kit]\nplaywright_version = "1.50.0"\n')
            self.assertEqual(uireview._playwright(self.root), ["npx", "-y", "playwright@1.50.0"])
        finally:
            os.environ["PATH"] = saved

    def test_review_gates_feature_and_release_not_every_change(self) -> None:
        from kit import launch, session
        self.assertIn("never had a UI review", " ".join(uireview.review_status(self.root)))
        self.assertFalse(any("UI review" in item for item in session.finish_findings(self.root)), "advisory per change")
        text = (self.root / "project.toml").read_text().replace('phase = "development"', 'phase = "private-preview"')
        self.write("project.toml", text)
        with self.assertRaises(Exception) as raised:
            launch.check_readiness(self.root)
        self.assertIn("never had a UI review", str(raised.exception))


class TrialTests(unittest.TestCase):
    """make trial: the build-trial request format, setup, and friction analysis."""

    def test_analysis_counts_spend_commands_and_friction(self) -> None:
        from kit import trial
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "make next && make done"}},
                {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "git commit --no-verify -m x"}},
                {"type": "tool_use", "id": "c", "name": "Bash", "input": {"command": "make issue BODY=x"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "Not finished:\n- docs/a.md covers src/a.py"},
                {"type": "tool_result", "tool_use_id": "c", "is_error": True, "content": "repoctl: issue needs Summary"}]}},
            {"type": "result", "subtype": "success", "num_turns": 7, "total_cost_usd": 1.5, "duration_ms": 120000, "result": "Done."},
            {"type": "result", "subtype": "success", "num_turns": 2, "total_cost_usd": 0.25, "duration_ms": 60000, "result": "Fixed."},
        ]
        with tempfile.TemporaryDirectory() as folder:
            transcript = Path(folder) / "t.jsonl"
            transcript.write_text("\n".join(json.dumps(e) for e in events) + "\nnot json\n")
            analysis = trial.analyze_transcript(transcript)
        self.assertEqual((analysis["cost_usd"], analysis["turns"], analysis["minutes"]), (1.75, 9, 3.0))
        self.assertEqual(analysis["make_targets"], {"next": 1, "done": 1, "issue": 1})
        self.assertEqual(len(analysis["gate_blocks"]), 1)
        self.assertIn("docs/a.md", analysis["gate_blocks"][0]["message"])
        self.assertEqual(len(analysis["failed_make"]), 1)
        self.assertEqual(len(analysis["bypasses"]), 1)
        self.assertEqual(analysis["final_message"], "Fixed.")

    def test_request_validation(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / trial.TRIALS).mkdir(parents=True)
            (root / trial.TRIALS / "x.toml").write_text('id = "x"\nkind = "web"\nprompt = "Build it."\n')
            self.assertEqual(trial.load_trial(root, "x")["mode"], "new")
            (root / trial.TRIALS / "y.toml").write_text('id = "y"\nkind = "cli"\nmode = "adopt"\nprompt = "Go."\n')
            with self.assertRaisesRegex(Exception, "adopt mode needs seed"):
                trial.load_trial(root, "y")
            with self.assertRaisesRegex(Exception, "known: x, y"):
                trial.load_trial(root, "z")

    def test_every_shipped_request_loads(self) -> None:
        from kit import trial
        for path in sorted((TOOLS.parent / trial.TRIALS).glob("*.toml")):
            self.assertEqual(trial.load_trial(TOOLS.parent, path.stem)["id"], path.stem)

    @template_only
    def test_new_mode_prepares_an_initialized_copy(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "demo"
            trial.prepare(TOOLS.parent, {"id": "demo", "kind": "web", "mode": "new", "prompt": "x"}, project)
            self.assertIn('name = "demo"', (project / "project.toml").read_text())
            self.assertEqual(subprocess.run(["git", "-C", str(project), "status", "--porcelain"],
                                            capture_output=True, text=True).stdout, "")
            self.assertIn("intake", subprocess.run([sys.executable, "tools/repoctl.py", "next"], cwd=project,
                                                   capture_output=True, text=True).stdout)
            for command in ("check", "finish"):  # a fresh project starts green, so its first gate failure is the agent's
                result = subprocess.run([sys.executable, "tools/repoctl.py", command], cwd=project, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@template_only
class GoldenPathTests(unittest.TestCase):
    """The promise of the template: an agent that does the intake meets no template bug.

    init -> minimal intake (accepted vision and stack, owner, one real surface) -> make done
    green -> a commit through the git gate. make done also runs the kit's own suite inside the
    new project. Any template bug on this path fails here, before it reaches ten projects.
    """

    def intake(self, project: Path, fill: bool = True) -> None:
        today = date.today().isoformat()
        for record in ("VISION.md", "docs/STACK-DECISION.md"):
            path = project / record
            text = path.read_text()
            if fill:
                text = re.sub(r"\[REQUIRED: ([^\]]+)\]", lambda m: "Decided: " + m.group(1).split(",")[0] + ".", text)
            path.write_text(text.replace("Status: pending", "Status: accepted").replace("Date: [YYYY-MM-DD]", f"Date: {today}"))
        manifest = project / "project.toml"
        text = re.sub(r'(?ms)(\[vision\]\s*\nstatus\s*=\s*)"pending"', r'\1"accepted"', manifest.read_text())
        text = re.sub(r'(?ms)^\[\[surfaces\]\]\nid = "template-bootstrap".*?verification = \[\]\n',
                      '[[surfaces]]\nid = "hello"\npath = "hello.py"\nkind = "script"\nstatus = "active"\nowner = "trial-owner"\n'
                      'quality_oracle = "prints the greeting"\nverification = [["python3", "hello.py"]]\n', text)
        manifest.write_text(text)
        (project / "hello.py").write_text('print("hello")\n')

    @template_only
    def test_init_intake_done_commit(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "demo"
            trial.prepare(TOOLS.parent, {"id": "demo", "kind": "cli", "mode": "new", "prompt": "x"}, project)
            self.assertIn("[REQUIRED:", (project / "VISION.md").read_text(), "init leaves a fresh record, not the template's")
            self.assertNotIn("AI_TEMPLATE", (project / "VISION.md").read_text())
            make = lambda *args: subprocess.run(["make", *args], cwd=project, capture_output=True, text=True, timeout=1200,
                                                  env={**os.environ, **({} if os.environ.get("KIT_SLOW") == "1" else {"KIT_INNER": "1"})})
            self.intake(project, fill=False)
            self.assertIn("placeholders", make("check").stderr, "an accepted record with placeholders is refused")
            self.intake(project)
            done = make("done")
            self.assertEqual(done.returncode, 0, (done.stdout + done.stderr)[-3000:])
            self.assertEqual(make("start").returncode, 0)
            subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
            commit = subprocess.run(["git", "-C", str(project), "commit", "-qm", "feat: hello surface"], capture_output=True, text=True)
            self.assertEqual(commit.returncode, 0, commit.stderr)

    @template_only
    def test_a_project_made_from_this_readme_passes_check(self) -> None:
        """#16: the generated command block must never read as un-rewritten template scaffolding."""
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "demo"
            trial.prepare(TOOLS.parent, {"id": "demo", "kind": "cli", "mode": "new", "prompt": "x"}, project)
            readme = project / "README.md"
            self.assertNotIn("Template mode", readme.read_text(), "make init rewrote the template's own line")
            self.assertIn("Project initialized: **demo** (`cli`)", readme.read_text())
            check = lambda: subprocess.run([sys.executable, "tools/repoctl.py", "check"], cwd=project,
                                           capture_output=True, text=True)
            generated = check()
            self.assertEqual(generated.returncode, 0, (generated.stdout + generated.stderr)[-2000:])
            readme.write_text(readme.read_text().replace(
                "# This project is initialized.", "make init NAME=my-project KIND=web OWNER=your-handle"))
            bootstrap = check()
            self.assertEqual(bootstrap.returncode, 1, "column-0 quickstart prose is still template scaffolding")
            self.assertIn("still contains template bootstrap text", bootstrap.stderr)


@template_only
class KitUpdateTests(unittest.TestCase):
    """Template fixes reach projects already made from it, without overwriting the project's changes."""

    def git(self, where: Path, *args: str) -> str:
        return subprocess.run(["git", "-C", str(where), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                              check=True, capture_output=True, text=True).stdout

    def snapshot(self, folder: Path) -> None:
        self.git(folder, "add", "-A")
        self.git(folder, "commit", "-qm", "snapshot")

    def test_update_applies_fixes_and_keeps_project_changes(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as temp:
            kit, project = Path(temp) / "kit", Path(temp) / "project"
            trial._copy(TOOLS.parent, trial.listed_files(TOOLS.parent), kit)
            (kit / "tools/kit/obsolete.py").write_text("OLD = 1\n")
            self.git(kit, "init", "-q", "-b", "main")
            self.snapshot(kit)
            trial.prepare(kit, {"id": "demo", "kind": "cli", "mode": "new", "prompt": "x"}, project)
            lock = json.loads((project / "tools/kit-lock.json").read_text())
            self.assertIn("tools/kit/navigate.py", lock["files"])
            self.assertNotIn("project.toml", lock["files"], "project-owned files are never kit files")
            same = subprocess.run([sys.executable, "tools/repoctl.py", "kit-update", "--kit", str(kit)],
                                  cwd=project, capture_output=True, text=True)
            self.assertIn("0 updated, 0 added, 0 removed, 0 to merge", same.stdout, "init and update agree")
            # The project customizes a kit doc and adds its own make target.
            (project / "docs/delegation.md").write_text((project / "docs/delegation.md").read_text() + "\nOur team rule.\n")
            (project / "project.mk").write_text("hello:\n\techo hi\n")
            self.snapshot(project)
            # The template ships version B: a fix, a new file, a removal, and a change to the customized doc.
            (kit / "tools/kit/navigate.py").write_text((kit / "tools/kit/navigate.py").read_text() + "\n# fixed in B\n")
            (kit / "tools/kit/extra_helper.py").write_text("NEW = 2\n")
            (kit / "tools/kit/obsolete.py").unlink()
            (kit / "docs/delegation.md").write_text((kit / "docs/delegation.md").read_text() + "\nKit B note.\n")
            self.snapshot(kit)
            update = lambda: subprocess.run([sys.executable, "tools/repoctl.py", "kit-update", "--kit", str(kit)],
                                            cwd=project, capture_output=True, text=True)
            result = update()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "tools/kit/navigate.py").read_text().endswith("# fixed in B\n"))
            self.assertTrue((project / "tools/kit/extra_helper.py").is_file())
            self.assertFalse((project / "tools/kit/obsolete.py").exists())
            self.assertIn("Our team rule.", (project / "docs/delegation.md").read_text(), "the project's change stays")
            self.assertIn("merge: docs/delegation.md", result.stdout)
            self.assertIn("Kit B note.", (project / ".agent/kit-update/docs/delegation.md").read_text())
            from kit import kitupdate
            self.assertIn("docs/delegation.md", " ".join(kitupdate.pending_merges(project)), "garden keeps listing it")
            self.assertEqual((project / "project.mk").read_text(), "hello:\n\techo hi\n")
            head = self.git(kit, "rev-parse", "HEAD").strip()
            self.assertEqual(json.loads((project / "tools/kit-lock.json").read_text())["kit_version"], head)
            check = subprocess.run([sys.executable, "tools/repoctl.py", "check"], cwd=project, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.snapshot(project)
            again = update()
            self.assertIn("0 updated, 0 added, 0 removed, 0 to merge", again.stdout, "reported once, not on every update")
            (kit / "docs/delegation.md").write_text((kit / "docs/delegation.md").read_text() + "\nKit C note.\n")
            self.snapshot(kit)
            self.assertIn("merge: docs/delegation.md", update().stdout, "a new kit change to the same file is reported again")
            self.assertIn("Our team rule.", (project / "docs/delegation.md").read_text())


    def test_reverted_conflict_updates_again_and_first_update_names_its_origin(self) -> None:
        # Issue #15: a conflicted file the project reverted to its shipped version gets later kit fixes;
        # a genuinely edited file is still left alone; a lock without a version says so plainly.
        from kit import trial
        with tempfile.TemporaryDirectory() as temp:
            kit, project = Path(temp) / "kit", Path(temp) / "project"
            trial._copy(TOOLS.parent, trial.listed_files(TOOLS.parent), kit)
            self.git(kit, "init", "-q", "-b", "main")
            self.snapshot(kit)
            trial.prepare(kit, {"id": "demo", "kind": "cli", "mode": "new", "prompt": "x"}, project)
            lock_path = project / "tools/kit-lock.json"
            lock = json.loads(lock_path.read_text())
            lock["kit_version"] = "unknown"
            lock_path.write_text(json.dumps(lock))
            shipped = (project / "docs/delegation.md").read_text()
            (project / "docs/delegation.md").write_text(shipped + "\nOur team rule.\n")
            (project / "docs/operations.md").write_text((project / "docs/operations.md").read_text() + "\nOur runbook.\n")
            self.snapshot(project)
            for doc in ("docs/delegation.md", "docs/operations.md"):
                (kit / doc).write_text((kit / doc).read_text() + "\nKit B note.\n")
            self.snapshot(kit)
            update = lambda: subprocess.run([sys.executable, "tools/repoctl.py", "kit-update", "--kit", str(kit)],
                                            cwd=project, capture_output=True, text=True)
            first = update()
            self.assertIn("no version recorded before", first.stdout, first.stdout + first.stderr)
            self.assertNotIn("was unknown", first.stdout)
            self.assertIn("merge: docs/delegation.md", first.stdout)
            (project / "docs/delegation.md").write_text(shipped)  # the project gives up its edit
            for staged in (project / ".agent/kit-update").rglob("*"):
                if staged.is_file():
                    staged.unlink()
            self.snapshot(project)
            for doc in ("docs/delegation.md", "docs/operations.md"):
                (kit / doc).write_text((kit / doc).read_text() + "\nKit C note.\n")
            self.snapshot(kit)
            second = update()
            self.assertIn("Kit C note.", (project / "docs/delegation.md").read_text(), second.stdout)
            self.assertIn("Our runbook.", (project / "docs/operations.md").read_text(), "a real edit stays")
            self.assertNotIn("Kit C note.", (project / "docs/operations.md").read_text())
            self.assertIn("merge: docs/operations.md", second.stdout)
            head = self.git(kit, "rev-parse", "HEAD").strip()
            self.assertEqual(json.loads(lock_path.read_text())["kit_version"], head, "a known version is recorded")


@template_only
class InitOwnerTests(unittest.TestCase):
    def test_init_names_the_owner_everywhere_and_refuses_emails(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            trial._copy(TOOLS.parent, trial.listed_files(TOOLS.parent), project)
            def init(owner: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run([sys.executable, "tools/repoctl.py", "init", "--name", "demo", "--kind", "web",
                                       "--owner", owner], cwd=project, capture_output=True, text=True)
            self.assertIn("not an email", init("me@example.com").stderr)
            self.assertEqual(init("octocat").returncode, 0)
            self.assertIn('owners = ["octocat"]', (project / "project.toml").read_text())
            self.assertNotIn("project-owner", (project / "project.toml").read_text())
            self.assertIn("Owner: octocat", (project / "VISION.md").read_text())


@template_only
class AdoptTests(unittest.TestCase):
    """make adopt brings the kit into an existing repository without overwriting it."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "notes"
        shutil.copytree(TOOLS.parent / ".agents/trials/seeds/notes-api", self.root)
        for command in (["init", "-q", "-b", "main"], ["add", "-A"],
                        ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "existing"]):
            subprocess.run(["git", "-C", str(self.root), *command], check=True, capture_output=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def adopt(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(REPOCTL), "--root", str(self.root), "adopt", "--from", str(TOOLS.parent),
                               "--name", "notes-api", "--kind", "api", "--owner", "notes-team"], capture_output=True, text=True)

    def test_adopt_merges_instead_of_overwriting(self) -> None:
        readme_before = (self.root / "README.md").read_text()
        result = self.adopt()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("renamed: kit-help, kit-test", result.stdout)
        self.assertTrue((self.root / "README.md").read_text().startswith(readme_before), "the project's README is kept")
        self.assertIn("Copyright (c) 2025 Notes Team", (self.root / "LICENSE").read_text())
        self.assertIn('license = "MIT"', (self.root / "project.toml").read_text())
        self.assertTrue((self.root / ".github/workflows/kit-ci.yml").is_file(), "colliding workflow written beside it")
        self.assertIn("<!-- index: design | Notes API |", (self.root / "docs/api.md").read_text())
        make = lambda *args: subprocess.run(["make", "-s", *args], cwd=self.root, capture_output=True, text=True)
        self.assertIn("make test     run the tests", make().stdout, "the project's default goal stays first")
        self.assertIn("Next (intake)", make("next").stdout, "kit targets work through include kit.mk")
        check = subprocess.run([sys.executable, "tools/repoctl.py", "check"], cwd=self.root, capture_output=True, text=True)
        problems = [line for line in check.stderr.splitlines() if line.startswith("- ")]
        self.assertTrue(problems and all("unregistered product surface" in line for line in problems), check.stderr)
        self.assertIn("infrastructure_paths", check.stderr, "the message names the fix")
        from kit import docs
        docs.check_markdown_links(self.root)  # links to pruned template material point at the template source
        self.assertNotIn(".agents/trials", (self.root / "docs/self-healing.md").read_text().split("-->")[1])
        finish = subprocess.run([sys.executable, "tools/repoctl.py", "finish"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(finish.returncode, 0, finish.stdout)
        self.assertEqual(self.adopt().returncode, 1, "adopting twice is refused")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "adopt"], check=True, capture_output=True)
        update = subprocess.run([sys.executable, "tools/repoctl.py", "kit-update", "--kit", str(TOOLS.parent)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertIn("0 updated, 0 added, 0 removed, 0 to merge", update.stdout, update.stdout + update.stderr)

    def test_adopted_project_passes_the_kit_suite_and_keeps_its_own_kit_paths_quiet(self) -> None:
        # The project's own ci.yml and a doc at a kit path stay the project's, and the kit suite still passes.
        (self.root / "docs/operations.md").write_text("# How we run it\n\nOur runbook.\n")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "runbook"], check=True, capture_output=True)
        self.assertEqual(self.adopt().returncode, 0)
        self.assertIn("Our runbook.", (self.root / "docs/operations.md").read_text())
        suite = subprocess.run(["make", "kit-test"], cwd=self.root, capture_output=True, text=True, timeout=900,
                               env={**os.environ, **({} if os.environ.get("KIT_SLOW") == "1" else {"KIT_INNER": "1"})})
        self.assertEqual(suite.returncode, 0, suite.stderr[-2500:])
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "adopt"], check=True, capture_output=True)
        update = subprocess.run([sys.executable, "tools/repoctl.py", "kit-update", "--kit", str(TOOLS.parent)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertIn("0 updated, 0 added, 0 removed, 0 to merge", update.stdout, update.stdout + update.stderr)

    def test_adopt_refuses_uncommitted_work(self) -> None:
        (self.root / "notes/new.py").write_text("X = 1\n")
        self.assertIn("commit or stash", self.adopt().stderr)


class PinDriftTests(KitRepository):
    def test_behind_pins_are_advisory_findings(self) -> None:
        self.write(".agents/mcp/browser.toml", 'name = "browser"\ndescription = "Real browser for UI checks."\ntransport = "stdio"\ncommand = ["npx", "-y", "@playwright/mcp@0.0.83"]\n')
        from kit.config import setting
        latest = {"playwright": str(setting(self.root, "playwright_version")), "@playwright/mcp": "0.0.90"}
        findings = garden.pin_drift(self.root, view=latest.get)
        self.assertEqual(len(findings), 1)
        self.assertIn("@playwright/mcp@0.0.83 (.agents/mcp/browser.toml) is behind 0.0.90", findings[0])
        self.assertEqual(garden.pin_drift(self.root, view=lambda package: None), [], "offline: no finding")


class DecisionAgeTests(unittest.TestCase):
    def test_old_decision_only_matters_at_the_release_gate(self) -> None:
        from datetime import timedelta
        from kit import structure
        old, future = date.today() - timedelta(days=500), date.today() + timedelta(days=2)
        self.assertFalse(structure._too_old_or_future(old, release_gate=False), "make check must not rot with the calendar")
        self.assertTrue(structure._too_old_or_future(old, release_gate=True))
        self.assertTrue(structure._too_old_or_future(future, release_gate=False), "a future date is a typo")

    def test_critic_evidence_age_gates_release_only(self) -> None:
        from datetime import timedelta
        from kit import structure
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = (date.today() - timedelta(days=500)).isoformat()
            (root / "review.md").write_text(f"Issue: #1\nCommit: {'a' * 40}\nArtifact: review.md\nReviewer: octocat\n"
                                            f"Date: {old}\nResult: pass\n")
            surface = {"id": "app", "critic_evidence": ["review.md"]}
            structure.validate_critic_evidence(root, surface)  # make check: an old review is still a review
            with self.assertRaisesRegex(Exception, "stale or future-dated"):
                structure.validate_critic_evidence(root, surface, release_gate=True)

    def test_skill_review_age_gates_release_only(self) -> None:
        import tomllib
        from datetime import timedelta
        from kit import skills
        project = tomllib.loads((TOOLS.parent / "project.toml").read_text())
        for skill in project.get("skills", []):
            skill["reviewed_on"] = (date.today() - timedelta(days=500)).isoformat()
        skills.check_skill_provenance(project)  # development: make garden reports the age instead
        with self.assertRaisesRegex(Exception, "older than a year"):
            skills.check_skill_provenance(project, release_gate=True)


class DerivedContentTests(KitRepository):
    def test_index_is_generated_from_declarations(self) -> None:
        self.write("docs/README.md", "# Index\n\n<!-- repoctl:index -->\n<!-- /repoctl:index -->\n")
        self.write("docs/billing.md", "# Billing\n\n<!-- index: design | Invoice rules | Billing changes. -->\n<!-- covers: src/billing/** -->\n\n`make check`.\n")
        self.assertIn("derived file out of date: docs/README.md", self.self_heal())
        derive.sync(self.root)
        index = (self.root / "docs/README.md").read_text()
        self.assertIn("| [`billing.md`](./billing.md) | Invoice rules | Billing changes. |", index)
        self.assertNotIn("docs/README.md", self.self_heal())

    def test_bad_index_group_is_reported(self) -> None:
        self.write("docs/billing.md", "# Billing\n\n<!-- index: misc | x | y -->\n<!-- covers: src/billing/** -->\n")
        self.assertIn("index declaration must be", self.self_heal())

    def test_readme_description_comes_from_manifest(self) -> None:
        self.write("README.md", "# Demo\n\n<!-- repoctl:description -->\nold\n<!-- /repoctl:description -->\n")
        text = (self.root / "project.toml").read_text().replace("[adapters]", '[repository]\ndescription = "Invoices for everyone."\n\n[adapters]')
        self.write("project.toml", text)
        derive.sync(self.root)
        self.assertIn("\nInvoices for everyone.\n", (self.root / "README.md").read_text())

    def test_readme_command_list_is_make_help_and_a_hand_edit_is_drift(self) -> None:
        self.write("README.md", "# Demo\n\n<!-- repoctl:description -->\nold\n<!-- /repoctl:description -->\n"
                                "## Commands\n\n<!-- repoctl:commands -->\n<!-- /repoctl:commands -->\n")
        derive.sync(self.root)
        readme = (self.root / "README.md").read_text()
        self.assertIn(f"<!-- repoctl:commands -->\n```bash\n{commands.help_text(registry.Registry(self.root))}\n```\n"
                      "<!-- /repoctl:commands -->", readme)
        self.write("README.md", readme.replace("make where", "make wherever"))
        self.assertIn("derived file out of date: README.md", self.self_heal())

    def test_a_removed_command_leaves_the_readme(self) -> None:
        self.write("README.md", "# Demo\n\n<!-- repoctl:commands -->\n<!-- /repoctl:commands -->\n")
        self.write(".agents/commands/seed-demo.py", "from kit.registry import command\n\n"
                   "@command('seed-demo', 'Load demo data for a walkthrough of the product')\n"
                   "def run(root, args):\n    print('seeded')\n")
        derive.sync(self.root)
        self.assertIn("make seed-demo", (self.root / "README.md").read_text())
        (self.root / ".agents/commands/seed-demo.py").unlink()
        derive.sync(self.root)
        self.assertNotIn("seed-demo", (self.root / "README.md").read_text())

    def test_handover_prefills_git_facts_and_never_overwrites(self) -> None:
        self.write("docs/handoffs/TEMPLATE.md", "# Handoff\n\n- **Created (UTC):** `<timestamp>`\n- **Working tree:** `<clean or exact uncommitted paths>`\n")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 7\n")
        self.assertIn("Wrote HANDOVER.md", self.cli("handover").stdout)
        text = (self.root / "HANDOVER.md").read_text()
        self.assertIn("`src/billing/invoice.py`", text)
        self.assertIn("docs/billing.md (covers src/billing/invoice.py)", text)
        self.assertIn("already exists", self.cli("handover").stdout)


class TemplateReadmeTests(KitRepository):
    """#16: the template states template mode; only `make init` writes a project identity."""

    MODE = "# Demo\n\n<!-- repoctl:project-readme -->\n> **Template mode:** the template itself.\n"
    INITIALIZED = "# Demo\n\n<!-- repoctl:project-readme -->\n> Project initialized: **Demo** (`web`).\n"

    def manifest(self, template: bool) -> dict:
        text = (self.root / "project.toml").read_text().replace(
            "[adapters]", f"[repository]\nis_template = {str(template).lower()}\n\n[adapters]")
        self.write("project.toml", text)
        return tomllib.loads(text)

    def test_the_template_repository_ships_template_mode(self) -> None:
        self.write("README.md", self.MODE)
        structure.check_readme_identity(self.root, self.manifest(True))

    def test_an_initialized_project_still_needs_its_identity_line(self) -> None:
        self.write("README.md", self.MODE)
        with self.assertRaisesRegex(Exception, "needs a project identity marker value"):
            structure.check_readme_identity(self.root, self.manifest(False))

    def test_a_generated_command_list_is_not_template_bootstrap_prose(self) -> None:
        self.write("README.md", self.INITIALIZED + "\n## Commands\n\n<!-- repoctl:commands -->\n<!-- /repoctl:commands -->\n")
        derive.sync(self.root)
        structure.check_readme_identity(self.root, self.manifest(False))
        self.assertIn("make init NAME=my-project", (self.root / "README.md").read_text())

    def test_unrewritten_quickstart_prose_still_fails(self) -> None:
        self.write("README.md", self.INITIALIZED + "\n```bash\nmake init NAME=my-project KIND=web OWNER=you\n```\n")
        with self.assertRaisesRegex(Exception, "still contains template bootstrap text"):
            structure.check_readme_identity(self.root, self.manifest(False))


class ScaffoldTests(KitRepository):
    def setUp(self) -> None:
        super().setUp()
        self.write("project.toml", (self.root / "project.toml").read_text() + "[capabilities]\nlocal_skills = []\n")
        self.write("docs/README.md", "# Index\n\n<!-- repoctl:index -->\n<!-- /repoctl:index -->\n")
        self.write("docs/delegation.md", "# Delegation\n\n<!-- repoctl:roles -->\n<!-- /repoctl:roles -->\n")

    def test_new_skill_is_registered_wired_and_unfinished_until_filled(self) -> None:
        result = self.cli("new", "--kind", "skill", "--name", "release-notes",
                          "--description", "Drafts release notes from merged pull requests before tagging a release.")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('local_skills = ["release-notes"]', (self.root / "project.toml").read_text())
        self.assertTrue((self.root / ".claude/skills/release-notes/SKILL.md").is_file())
        self.assertIn("unfinished scaffold", self.self_heal())

    def test_new_agent_appears_in_generated_role_table(self) -> None:
        result = self.cli("new", "--kind", "agent", "--name", "test-writer", "--access", "full",
                          "--description", "Writes missing regression tests for one module when seam coverage is thin.")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[`test-writer`]", (self.root / "docs/delegation.md").read_text())
        self.assertTrue((self.root / ".claude/agents/test-writer.md").is_file())

    def test_near_duplicate_is_refused_unless_forced(self) -> None:
        arguments = ["new", "--kind", "skill", "--name", "invoice-renderer", "--description", "Render invoices for billing customers."]
        refused = self.cli(*arguments)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("too similar to skill:demo-skill", refused.stderr)
        self.assertEqual(self.cli(*arguments, "--force").returncode, 0)

    def test_new_doc_indexes_itself_with_configurable_groups(self) -> None:
        bad = self.cli("new", "--kind", "doc", "--name", "pricing", "--group", "misc", "--description", "Pricing rules; when prices change")
        self.assertIn("GROUP must be one of", bad.stderr)
        self.write("project.toml", (self.root / "project.toml").read_text() + '[kit]\ndoc_groups = { misc = "Miscellany" }\n')
        ok = self.cli("new", "--kind", "doc", "--name", "pricing", "--group", "misc", "--covers", "src/billing/**",
                      "--description", "Pricing rules; when prices change")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        index = (self.root / "docs/README.md").read_text()
        self.assertIn("### Miscellany", index)
        self.assertIn("| [`pricing.md`](./pricing.md) | Pricing rules | when prices change |", index)


class CapabilityModelTests(KitRepository):
    """docs/adr/0002-one-capability-model.md: every kind is added by one command and found the same way."""

    def setUp(self) -> None:
        super().setUp()
        self.write("project.toml", (self.root / "project.toml").read_text() + "[capabilities]\nlocal_skills = []\n")
        self.write("docs/README.md", "# Index\n\n<!-- repoctl:index -->\n<!-- /repoctl:index -->\n")
        self.write("AGENTS.md", "# Agents\n\n<!-- repoctl:rules -->\n<!-- /repoctl:rules -->\n")
        self.write("Makefile", "check:\n\t@true\n\n# <repoctl:commands>\n# </repoctl:commands>\n")
        derive.sync(self.root)

    def new(self, kind: str, name: str, description: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.cli("new", "--kind", kind, "--name", name, "--description", description, *extra)

    def test_every_kind_is_created_by_make_new_and_found_by_where_and_capabilities(self) -> None:
        cases = [
            ("skill", "release-notes", "Drafts release notes from merged pull requests; before tagging a release."),
            ("agent", "test-writer", "Writes missing regression tests for one module; when seam coverage is thin."),
            ("doc", "pricing", "Pricing rules and discounts; when prices change"),
            ("rule", "money-in-cents", "Store money as integer cents, never floats; when touching amounts."),
            ("check", "license-headers", "Source files carry the license header; before publishing source."),
            ("command", "seed-data", "Loads demo data into the local database; before a demo or a UI review."),
            ("mcp", "issue-tracker", "Reads tickets from the team's tracker; when an issue links a ticket."),
            ("pack", "payments", "Payment flows, refunds, and receipts; for products that take money."),
        ]
        for kind, name, description in cases:
            result = self.new(kind, name, description)
            self.assertEqual(result.returncode, 0, f"{kind}: {result.stderr}")
            expected = r"docs/pricing\.md  \[path\]" if kind == "doc" else rf"\[{kind}[^\]]*\] {name}"
            self.assertRegex("\n".join(navigate.where(self.root, name.replace("-", " "))), expected, f"make where finds the {kind}")
        report = self.cli("capabilities").stdout
        for kind, name, _ in cases:
            if kind != "doc":
                self.assertIn(name, report, f"make capabilities lists the {kind}")
        self.assertIn("pricing.md", (self.root / "docs/README.md").read_text())
        self.assertIn("seed-data:", (self.root / "Makefile").read_text(), "a project command gets a make target")
        self.assertIn("unfinished scaffold", self.self_heal(), "stubs fail until their FILL-IN lines are replaced")
        self.assertEqual(self.cli("seed-data").returncode, 0, "the project command runs through repoctl")

    def test_blocking_check_must_give_its_reason(self) -> None:
        self.write(".agents/checks/loud.py", "from kit.registry import check\n\n"
                   "@check('loud', 'A check that blocks without saying why it may', blocks=True)\n"
                   "def run(context):\n    return []\n")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("must give its reason", result.stderr)

    def test_project_check_runs_in_the_gate_and_names_its_fix(self) -> None:
        self.write(".agents/checks/no-print.py", "from kit.registry import check\n\n"
                   "@check('no-print', 'Source files never call print; logging is configured centrally', blocks=True,\n"
                   "       reason='A stray print leaked a token in an incident; the fix is one line.')\n"
                   "def run(context):\n"
                   "    return [f'{path}: replace print with the logger' for path in context.files\n"
                   "            if path.endswith('.py') and path.startswith('src/') and 'print(' in (context.root / path).read_text()]\n")
        self.write("src/billing/report.py", "print('x')\n")
        self.assertIn("src/billing/report.py: replace print with the logger", self.self_heal())

    def test_a_disabled_pack_costs_no_context_but_stays_findable(self) -> None:
        self.assertEqual(self.new("pack", "billing-extras", "Billing exports and dunning flows; for finance teams.").returncode, 0)
        self.assertEqual(self.new("skill", "dunning-emails", "Writes dunning email sequences for overdue invoices; for finance.",
                                  "--pack", "billing-extras").returncode, 0)
        self.write(".agents/checks/dunning.py", "from kit.registry import check\n\n"
                   "@check('dunning', 'Dunning templates exist for every overdue stage', blocks=True, pack='billing-extras',\n"
                   "       reason='Finance shipped a stage with no template in an incident.')\n"
                   "def run(context):\n    return ['dunning templates missing: add them']\n")
        self.write(".agents/commands/export-ledger.py", "from kit.registry import command\n\n"
                   "@command('export-ledger', 'Exports the ledger as CSV for the finance team', pack='billing-extras')\n"
                   "def run(root, args):\n    print('exported')\n")
        derive.sync(self.root)
        self.assertFalse((self.root / ".claude/skills/dunning-emails").exists(), "a pack that is off is not rendered for hosts")
        self.assertNotIn("dunning templates missing", self.self_heal(), "its checks do not run")
        refused = self.cli("export-ledger")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("billing-extras = true", refused.stderr, "the refusal names the switch")
        self.assertIn("dunning-emails (off: billing-extras)", self.cli("capabilities").stdout)
        self.assertIn("pack billing-extras off", "\n".join(navigate.where(self.root, "dunning email")))
        self.write("project.toml", (self.root / "project.toml").read_text() + "[packs]\nbilling-extras = true\n")
        derive.sync(self.root)
        self.assertTrue((self.root / ".claude/skills/dunning-emails/SKILL.md").is_file())
        self.assertIn("dunning templates missing", self.self_heal())
        self.assertEqual(self.cli("export-ledger").stdout.strip(), "exported")
        self.write("project.toml", (self.root / "project.toml").read_text() + "typo-pack = true\n")
        self.assertIn("unknown packs: typo-pack", self.cli("capabilities").stderr)

    def test_global_rules_live_in_agents_md_and_scoped_rules_arrive_on_edit(self) -> None:
        self.assertEqual(self.new("rule", "small-commits", "Keep each commit to one root cause; always.").returncode, 0)
        self.assertEqual(self.new("rule", "money-in-cents", "Store money as integer cents; in billing code.",
                                  "--covers", "src/billing/**").returncode, 0)
        agents = (self.root / "AGENTS.md").read_text()
        self.assertIn("Keep each commit to one root cause", agents)
        self.assertNotIn("money as integer cents", agents, "a scoped rule stays out of the router")
        event = json.dumps({"session_id": "s1", "tool_input": {"file_path": str(self.root / "src/billing/invoice.py")}})
        first = self.cli("hook", "after-edit", stdin=event).stdout
        self.assertIn("Store money as integer cents", first)
        self.assertNotIn("integer cents", self.cli("hook", "after-edit", stdin=event).stdout, "once per session")
        self.assertIn("[rule] money-in-cents", "\n".join(navigate.where(self.root, "src/billing/invoice.py")))

    def test_makefile_commands_are_generated_and_drift_fails(self) -> None:
        makefile = (self.root / "Makefile").read_text()
        self.assertIn('@$(REPOCTL) where -- "$${KIT_IN_Q}"', makefile)
        self.assertIn("$(error Add what to look for", makefile)
        self.write("Makefile", makefile.replace("@$(REPOCTL) where", "@$(REPOCTL) wherever"))
        self.assertIn("derived file out of date: Makefile", self.self_heal())

    def test_a_kit_makefile_without_its_command_block_is_drift(self) -> None:
        self.write("Makefile", "REPOCTL := python3 tools/repoctl.py\ncheck:\n\t$(REPOCTL) check\n")
        self.assertIn("lost its generated command block", self.self_heal())

    def test_make_variables_reach_repoctl_as_data(self) -> None:
        marker = self.root / "pwned"
        result = subprocess.run(["make", "-s", "where", f"Q=x\"; touch {marker}; echo \""], cwd=self.root,
                                capture_output=True, text=True)
        self.assertFalse(marker.exists(), result.stdout + result.stderr)


CONTRACT_HEADINGS = "".join(f"### {heading}\nx\n" for heading in ci.CANONICAL["agent-first"])
DUPLICATE_LINE = "Duplicate check: searched title, symptom, and path for x; no duplicate found\n"


class CiCheckTests(unittest.TestCase):
    """The logic GitHub Actions runs, tested locally (tools/kit/ci.py)."""

    def issue(self, **overrides: object) -> dict:
        return {"state": "open", "body": DUPLICATE_LINE + CONTRACT_HEADINGS, **overrides}

    def test_pr_reference_accepts_open_canonical_issue(self) -> None:
        message = ci.pr_reference_check("Closes #6", set(), "OWNER", "agent-first", lambda number: self.issue())
        self.assertIn("#6", message)

    def test_pr_reference_rejections(self) -> None:
        cases = {
            "must include Closes/Fixes": ("Refs #6", set(), self.issue()),
            "must be an open issue": ("Fixes #6", set(), self.issue(state="closed")),
            "is a pull request": ("Fixes #6", set(), self.issue(pull_request={})),
            "canonical issue contract": ("Fixes #6", set(), self.issue(body=DUPLICATE_LINE)),
            "duplicate-search record": ("Fixes #6", set(), self.issue(body=CONTRACT_HEADINGS)),
            "requires the trusted private-review": ("Fixes #6", {"security-reviewed"}, self.issue()),
        }
        for expected, (body, labels, issue) in cases.items():
            with self.subTest(expected=expected), self.assertRaisesRegex(Exception, expected):
                ci.pr_reference_check(body, labels, "OWNER", "agent-first", lambda number, issue=issue: issue)

    def test_minimal_profile_delegates(self) -> None:
        self.assertIn("Minimal", ci.pr_reference_check("", set(), "", "minimal", lambda number: {}))

    def test_issue_contract_accepts_complete_form_and_adds_labels(self) -> None:
        registry = json.loads((TOOLS.parent / ".github/issue-labels.json").read_text())
        body = (
            DUPLICATE_LINE
            + "### Summary\nA concrete outcome for the issue contract test.\n"
            + "### Acceptance criteria\n- The positive test passes.\n- A negative test does not pass.\n"
            + "### Evidence\nTest evidence: unit output\n"
            + "### Disclosure classification\n- **Disclosure class:** ordinary\n- **Public-safe:** yes\n"
            + "- **Security/privacy review:** not applicable\n- **Reviewer/date:** tester " + RECENT + "\n"
            + "### Dependencies and handoff\n- **Owner / next action:** maintainer\n"
            + "### Type\nbug\n### Priority\nP2\n### Area\nrepo\n### Topic\nci-checks\n### Status\ntriage\n"
        )
        valid, labels, reasons = ci.issue_contract_check(body, set(), "agent-first", registry, today=date.today())
        self.assertTrue(valid, reasons)
        self.assertIn("topic:ci-checks", labels)
        def rejected(text: str) -> bool:
            try:
                return not ci.issue_contract_check(text, set(), "agent-first", registry, today=date.today())[0]
            except Exception:  # noqa: BLE001 - an early validator raising is also a rejection
                return True

        self.assertFalse(rejected(body.replace(RECENT, (date.today() - timedelta(days=500)).isoformat())),
                         "a review date belongs to the text it reviewed; it never ages out")
        self.assertTrue(rejected(body.replace(RECENT, (date.today() + timedelta(days=3)).isoformat())))
        reasons = ci.issue_contract_check(body.replace("### Topic\nci-checks", "### Topic\nNot Kebab"), set(),
                                          "agent-first", registry)[2]
        self.assertIn("Topic must be kebab-case: Not Kebab", reasons, "the comment names the fix")
        self.assertTrue(rejected(body.replace("ordinary", "unclassified")))
        self.assertTrue(rejected(body.replace("### Topic\nci-checks", "### Topic\nNot Kebab")))
        with self.assertRaisesRegex(Exception, "Regulated profile uses the CLI"):
            ci.issue_contract_check(body, set(), "regulated", registry)


class EvalCommandTests(unittest.TestCase):
    def test_model_flag_is_passed_only_when_set(self) -> None:
        with_model = evals.HOST_COMMANDS["claude"]("task", "haiku")
        self.assertEqual(with_model[with_model.index("--model") + 1], "haiku")
        self.assertNotIn("--model", evals.HOST_COMMANDS["claude"]("task", ""))
        self.assertIn("--sandbox", evals.HOST_COMMANDS["codex"]("task", ""))


class NavigationTests(KitRepository):
    def test_where_finds_symbol_with_owner(self) -> None:
        hits = navigate.where(self.root, "render invoice")
        self.assertTrue(any("src/billing/invoice.py:1  [symbol] render_invoice" in hit for hit in hits), hits)
        self.assertTrue(any("documented in docs/billing.md" in hit for hit in hits), hits)

    def test_where_searches_failure_memory(self) -> None:
        self.write("docs/ERROR_LOG.md", "# Errors\n\n- ECONNRESET during invoice export: retry with backoff\n")
        hits = navigate.where(self.root, "ECONNRESET")
        self.assertTrue(any("[seen-before]" in hit for hit in hits), hits)

    def test_skill_overlap_ranks_existing_capability(self) -> None:
        best = navigate.skill_overlap(self.root, "render invoices for customers")[0]
        self.assertEqual(best[1], "skill:demo-skill")
        self.assertGreaterEqual(best[0], 0.3)

    def test_risk_tiers(self) -> None:
        rules = risk.tier_rules({"risk": {"high": ["src/auth/**"], "low": ["docs/**"]}})
        self.assertEqual(risk.classify("src/auth/login.py", rules), "high")
        self.assertEqual(risk.classify("docs/a.md", rules), "low")
        self.assertEqual(risk.classify("src/billing/invoice.py", rules), "normal")
        self.write("src/auth/login.py", "def login():\n    return False\n")
        overall, grouped = risk.assess(self.root)
        self.assertEqual(overall, "high")
        self.assertEqual(grouped["high"], ["src/auth/login.py"])



class OrphanFileTests(unittest.TestCase):
    """Issue #17: a tracked file nothing references fails `make check`; a named one does not."""

    MANIFEST = 'schema = 1\nname = "Demo"\nkind = "cli"\nphase = "development"\n'

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, files: dict[str, str], manifest: str = MANIFEST) -> None:
        self.write("project.toml", manifest)
        for name, content in files.items():
            self.write(name, content)
        for command in (("init", "-q", "-b", "main"), ("config", "user.email", "test@example.com"),
                        ("config", "user.name", "Test"), ("add", "-A"), ("commit", "-q", "-m", "fixture")):
            subprocess.run(["git", "-C", str(self.root), *command], check=True, capture_output=True, text=True)

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
        return path

    def orphans(self) -> tuple[list[str], list[str]]:
        return reachability.orphans(registry.Context(self.root))

    def test_an_unreferenced_file_is_a_finding_that_names_its_fix(self) -> None:
        self.build({
            "docs/README.md": "# Docs\n\n- [API](api.md)\n",
            "docs/api.md": "# API\n\n<!-- covers: src/used.py -->\n",
            "src/used.py": "VALUE = 1\n",
            "src/leftover.py": "VALUE = 2\n",
        })
        blocking, _ = self.orphans()
        self.assertEqual([item.split(":")[0] for item in blocking], ["src/leftover.py"])
        self.assertIn("<!-- covers: src/leftover.py -->", blocking[0])
        self.assertIn("[repository].infrastructure_paths", blocking[0])

    def test_a_named_file_is_not_an_orphan(self) -> None:
        # A module an import reaches, a file a binding claims, and one a test root loads.
        self.build({
            "docs/README.md": "# Docs\n\n- [API](api.md)\n",
            "docs/api.md": "# API\n\n<!-- covers: src/bound.py src/app.py -->\n",
            "src/bound.py": "VALUE = 1\n",
            "src/imported.py": "VALUE = 2\n",
            "src/app.py": "from . import imported\n\nprint(imported.VALUE)\n",
            "tests/test_app.py": "def test_app():\n    assert True\n",
            "Makefile": "test:\n\tpython3 -m unittest discover -s tests\n",
        })
        blocking, _ = self.orphans()
        self.assertEqual(blocking, [], "a bound, imported, or discovered file is not an orphan")

    def test_host_read_configuration_is_reported_without_blocking(self) -> None:
        self.build({"docs/README.md": "# Docs\n\n- [API](api.md)\n",
                    "docs/api.md": "# API\n\n<!-- covers: src/kept.py -->\n",
                    ".editorconfig": "root = true\n", "src/kept.py": "VALUE = 1\n"})
        blocking, advisory = self.orphans()
        self.assertEqual(blocking, [], "a host-read configuration file never blocks")
        self.assertTrue(any(item.startswith(".editorconfig:") for item in advisory), advisory)

    def test_declared_infrastructure_silences_the_finding(self) -> None:
        self.build({"docs/README.md": "# Docs\n\n- [API](api.md)\n", "docs/api.md": "# API\n",
                    "vendor/thing.py": "VALUE = 1\n"},
                   manifest=self.MANIFEST + '[repository]\ninfrastructure_paths = ["vendor"]\n')
        self.assertEqual(self.orphans(), ([], []))

    def test_a_kit_artifact_never_needs_a_project_declaration(self) -> None:
        self.build({"docs/README.md": "# Docs\n\n- [API](api.md)\n", "docs/api.md": "# API\n",
                    "review.md": "Issue: #1\nReviewer: octocat\nDate: 2026-09-01\n",
                    "HANDOVER.md": "# Handover\n"})
        self.assertEqual(self.orphans(), ([], []), "kit-owned paths are exempt by default")

    def test_it_runs_in_the_blocking_gate(self) -> None:
        self.build({"docs/README.md": "# Docs\n\n- [API](api.md)\n",
                    "docs/api.md": "# API\n\n<!-- covers: src/used.py -->\n", "src/used.py": "VALUE = 1\n",
                    "src/leftover.py": "VALUE = 2\n"})
        hard, _ = registry.run_checks(self.root, blocking_only=True,
                                     skip=KitRepository.CONTRACT - {"orphan-files"})
        self.assertIn("src/leftover.py", "\n".join(hard), "make check reports an orphan file")

    @template_only
    def test_this_repository_has_no_blocking_orphan(self) -> None:
        # Naming a path here would itself make it a reference, so this asserts the shape, not the names.
        blocking, advisory = reachability.orphans(registry.Context(TOOLS.parent))
        self.assertEqual(blocking, [], "the kit's own files are all named by code, binding, or configuration")
        self.assertTrue(all("host-read configuration" in item for item in advisory), advisory)


class ChangeCouplingTests(unittest.TestCase):
    """Issue #18: recent history reports the areas that co-change, and never blocks."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *arguments: str) -> None:
        subprocess.run(["git", "-C", str(self.root), *arguments], check=True, capture_output=True, text=True)

    def commit_touching(self, paths: list[str], message: str) -> None:
        for path in paths:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{message}\n", encoding="utf-8")
            self.git("add", path)
        self.git("commit", "-q", "-m", message)

    def history(self) -> None:
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")

    def test_areas_are_directories_and_root_files(self) -> None:
        self.assertEqual(coupling.area("tools/kit/checks.py"), "tools/kit")
        self.assertEqual(coupling.area(".agents/skills/demo/SKILL.md"), ".agents/skills")
        self.assertEqual(coupling.area("Makefile"), "Makefile")
        self.assertEqual(coupling.area("docs/README.md"), "docs")

    def test_the_pair_that_keeps_changing_together_is_named(self) -> None:
        self.history()
        for number in range(coupling.MIN_SHARED + 1):
            self.commit_touching(["src/billing/invoice.py", "tools/tests/test_billing.py"], f"billing {number}")
        self.commit_touching(["docs/notes.md"], "notes")
        findings = coupling.coupling_findings(self.root)
        self.assertTrue(any(item.startswith("src/billing + tools/tests:") for item in findings), findings)
        self.assertEqual(sum("co-change" in item for item in findings), 1, findings)

    def test_a_pair_seen_twice_is_a_coincidence_not_a_seam(self) -> None:
        self.history()
        for number in range(2):
            self.commit_touching(["src/a/one.py", "src/b/two.py"], f"pair {number}")
        self.assertEqual(coupling.coupling_findings(self.root), [])

    def test_a_sweeping_commit_is_not_a_coupling_signal(self) -> None:
        self.history()
        for number in range(3):
            self.commit_touching([f"area{index}/file.py" for index in range(coupling.MAX_AREAS + 1)], f"sweep {number}")
        self.assertEqual(coupling.coupling_findings(self.root), [])

    def test_it_stays_advisory_and_out_of_the_blocking_gate(self) -> None:
        self.history()
        for number in range(coupling.MIN_SHARED + 1):
            self.commit_touching(["src/billing/invoice.py", "tools/tests/test_billing.py"], f"billing {number}")
        declared = registry.Registry(self.root).get("check", "change-coupling")
        self.assertIsNotNone(declared, "the check is declared")
        self.assertFalse(declared.fields["blocks"], "coupling is a judgement, so it never blocks")
        self.write_manifest()
        hard, advisory = registry.run_checks(self.root, blocking_only=False)
        self.assertNotIn("co-change", "\n".join(hard), "make check never reports coupling")
        self.assertIn("co-change", "\n".join(advisory), "make garden reports it")

    def write_manifest(self) -> None:
        (self.root / "project.toml").write_text('schema = 1\nname = "Demo"\nkind = "cli"\nphase = "development"\n',
                                                encoding="utf-8")
        self.git("add", "project.toml")
        self.git("commit", "-q", "-m", "manifest")

    def test_it_costs_nothing_measurable_on_this_repository(self) -> None:
        started = time.perf_counter()
        coupling.coupling_findings(TOOLS.parent)
        self.assertLess(time.perf_counter() - started, 5.0, "one bounded git log stays well inside the garden budget")


class FailureSignatureTests(unittest.TestCase):
    """Issue #19: a finding that repeats a recorded signature is recognised, not re-diagnosed."""

    LEDGER = """# Error ledger

| Key | Date | Signature / symptom | Confirmed cause | Permanent fix |
|---|---|---|---|---|
| EL-001 | 2026-01-01 | `covers pattern matches no file: legacy/**` right after init | Pruning left a binding pointing at removed material | localize_text drops bindings to pruned material |
"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / "project.toml").write_text('schema = 1\nname = "Demo"\nkind = "cli"\nphase = "development"\n',
                                                encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def ledger(self, text: str = LEDGER) -> None:
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "docs" / "ERROR_LOG.md").write_text(textwrap.dedent(text), encoding="utf-8")

    def test_a_repeated_failure_is_named_with_its_recorded_fix(self) -> None:
        self.ledger()
        records = signatures.signatures(self.root)
        hit = signatures.match("docs/api.md: covers pattern matches no file: legacy/**", records)
        self.assertIsNotNone(hit, "a recorded signature is recognised")
        self.assertEqual(hit.key, "EL-001")
        self.assertIn("localize_text drops bindings", hit.fix)

    def test_a_fresh_failure_matches_no_prior_signature(self) -> None:
        self.ledger()
        records = signatures.signatures(self.root)
        for finding in ("src/billing/invoice.py: nothing references it", "AGENTS.md: 812 bytes, over its 200-byte budget"):
            self.assertIsNone(signatures.match(finding, records), finding)
        self.assertEqual(signatures.recognition(["src/billing/invoice.py: nothing references it"], records), [])

    def test_the_check_runner_reports_the_signature_next_to_the_finding(self) -> None:
        self.ledger()
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "docs" / "api.md").write_text("# API\n\n<!-- covers: legacy/** -->\n", encoding="utf-8")
        hard, _ = registry.run_checks(self.root, blocking_only=True)
        findings = "\n".join(hard)
        self.assertIn("covers pattern matches no file: legacy/**", findings)
        self.assertIn("known failure EL-001", findings, "a repeat reports its key and fix")
        self.assertIn("localize_text drops bindings", findings)

    def test_no_ledger_means_no_matching_and_no_crash(self) -> None:
        self.assertEqual(signatures.signatures(self.root), ())
        self.assertIsNone(signatures.match("anything at all", ()))
        hard, _ = registry.run_checks(self.root, blocking_only=True, skip=KitRepository.CONTRACT)
        self.assertNotIn("known failure", "\n".join(hard))

    def test_columns_are_read_from_the_header(self) -> None:
        self.ledger("""\
            # Error ledger

            | Date | Permanent fix | Signature / symptom | Key | Confirmed cause |
            |---|---|---|---|---|
            | 2026-01-01 | shrink the router | `over its 200-byte budget` | EL-009 | an always-loaded doc grew |
            """)
        records = signatures.signatures(self.root)
        self.assertEqual([record.key for record in records], ["EL-009"])
        self.assertEqual(records[0].fix, "shrink the router")
        self.assertIsNotNone(signatures.match("AGENTS.md is 812 bytes, over its 200-byte budget (AGENTS.md)", records))

    @template_only
    def test_this_ledger_is_keyed_and_every_row_has_a_fix(self) -> None:
        records = signatures.signatures(TOOLS.parent)
        self.assertGreaterEqual(len(records), 5)
        for record in records:
            self.assertRegex(record.key, r"^EL-\d{3}$")
            self.assertTrue(record.literals, record.key)
            self.assertTrue(record.fix, f"{record.key} records no permanent fix")


if __name__ == "__main__":
    unittest.main()
