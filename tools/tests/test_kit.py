"""Tests for the self-healing kit: bindings, markers, adapters, hooks, navigation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import date
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPOCTL = TOOLS / "repoctl.py"
sys.path.insert(0, str(TOOLS))

from kit import adapters, ci, derive, docsync, evals, garden, hygiene, navigate, product, risk, uireview  # noqa: E402
from kit.gitinfo import path_matches  # noqa: E402

# Built by concatenation so this test file never trips the marker scanner itself.
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
            [[mcp]]
            id = "browser"
            transport = "stdio"
            command = ["npx", "-y", "@example/mcp@1.2.3"]
            enabled = true
            purpose = "Drive a browser."
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

    def self_heal(self) -> str:
        """The self-healing findings `make check` adds on top of the structure checks."""
        return "\n".join(garden.self_heal_errors(self.root))

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
        self.write("resources.toml", (self.root / "resources.toml").read_text().replace("enabled = true", "enabled = false"))
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
        text = (self.root / "resources.toml").read_text().replace("@example/mcp@1.2.3", "@example/mcp@latest")
        self.write("resources.toml", text)
        with self.assertRaisesRegex(Exception, "must pin its package"):
            adapters.mcp_routes(self.root)

    def test_frontmatter_colon_must_be_quoted(self) -> None:
        self.write(".agents/agents/scout.md", "---\nname: scout\ndescription: Locator: finds files.\naccess: read-only\ntier: fast\n---\n")
        with self.assertRaisesRegex(Exception, "quote it"):
            adapters.canonical_roles(self.root)


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
        self.assertIn("quality_oracle must include the ux-quality", findings)
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
                   "- **Public-safe:** yes\n- **Security/privacy review:** not applicable\n- **Reviewer/date:** tester 2026-10-01\n"
                   "### Dependencies and handoff\n- **Owner / next action:** maintainer\n")
        result = self.cli("issue", "--title", "First slice", "--body-file", "issue.md", "--type", "task",
                          "--priority", "P2", "--area", "web", "--topic", "first-slice", "--status", "ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Local-WAL-001", result.stdout)
        self.assertTrue((self.root / ".agent/wal/001-first-slice.md").is_file())


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
        self.assertEqual(self.phase(), "stack")
        self.write("docs/STACK-DECISION.md", "# Stack\n\nStatus: accepted\n")
        self.assertEqual(self.phase(), "skeleton")
        surface = '[[surfaces]]\nid = "app"\npath = "src"\nkind = "code"\nquality_oracle = "tests plus ux-quality review"\nverification = [["true"]]\n'
        self.write("project.toml", (self.root / "project.toml").read_text() + surface)
        self.assertEqual(self.phase(), "preview")
        self.write("project.toml", (self.root / "project.toml").read_text()
                   + '[surfaces.preview]\ncommand = ["true"]\nurl = "http://localhost:4999"\n')
        step = product.next_step(self.root)
        self.assertEqual(step["phase"], "build")
        self.assertIn("Add a habit", step["action"])
        self.features("Add a habit,core,must,yes,src/billing/invoice.py,Adding takes one tap,owner")
        self.assertEqual(self.phase(), "review")
        self.assertIn("never had a UI review", product.next_step(self.root)["action"])

    def test_score_and_evidence(self) -> None:
        self.features(
            "A,core,must,yes,src/billing/invoice.py,works,owner",
            "B,core,must,partial,missing/file.py,works,owner",
            "C,core,should,no,,,owner",
            "D,core,could,skip,,,owner",
        )
        percent, open_must = product.score(product.load_features(self.root))
        self.assertAlmostEqual(percent, 100 * (3 + 1.5) / 8)
        self.assertEqual([row["feature"] for row in open_must], ["B"])
        errors = product.feature_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("'B' is marked partial without existing evidence", errors[0])

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
        fake = bin_dir / "npx"  # stands in for Playwright: writes the screenshot file it was asked for
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

    def test_dead_preview_fails_fast(self) -> None:
        text = (self.root / "project.toml").read_text()
        text = text.replace(f'command = ["{sys.executable}", "-m", "http.server", "{{port}}", "--bind", "127.0.0.1"]',
                            f'command = ["{sys.executable}", "-c", "raise SystemExit(7)"]')
        self.write("project.toml", text)
        result = self.review()
        self.assertEqual(result.returncode, 1)
        self.assertIn("exited with code 7", result.stderr)

    def test_review_captures_sizes_and_schemes_then_needs_verdict_and_freshness(self) -> None:
        self.assertIn("never had a UI review", " ".join(uireview.review_status(self.root)))
        result = self.review()
        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads((self.root / uireview.LATEST).read_text())["app"]["run"]
        shots = sorted(path.name for path in (self.root / run).glob("*.png"))
        self.assertEqual(len(shots), 4)
        self.assertIn("app-home-default-phone-dark.png", shots)
        self.assertIn("has no verdict yet", " ".join(uireview.review_status(self.root)))
        review = self.root / run / "REVIEW.md"
        review.write_text(review.read_text().replace(uireview.VERDICT_PENDING, "Verdict: pass"))
        self.assertEqual(uireview.review_status(self.root), [])
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 42\n")
        self.assertIn("changed since its last UI review", " ".join(uireview.review_status(self.root)))


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

    def test_handover_prefills_git_facts_and_never_overwrites(self) -> None:
        self.write("docs/handoffs/TEMPLATE.md", "# Handoff\n\n- **Created (UTC):** `<timestamp>`\n- **Working tree:** `<clean or exact uncommitted paths>`\n")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 7\n")
        self.assertIn("Wrote HANDOVER.md", self.cli("handover").stdout)
        text = (self.root / "HANDOVER.md").read_text()
        self.assertIn("`src/billing/invoice.py`", text)
        self.assertIn("docs/billing.md (covers src/billing/invoice.py)", text)
        self.assertIn("already exists", self.cli("handover").stdout)


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
            + "- **Security/privacy review:** not applicable\n- **Reviewer/date:** tester 2026-10-01\n"
            + "### Dependencies and handoff\n- **Owner / next action:** maintainer\n"
            + "### Type\nbug\n### Priority\nP2\n### Area\nrepo\n### Topic\nci-checks\n### Status\ntriage\n"
        )
        valid, labels = ci.issue_contract_check(body, set(), "agent-first", registry, today=date(2026, 10, 7))
        self.assertTrue(valid)
        self.assertIn("topic:ci-checks", labels)
        def rejected(text: str) -> bool:
            try:
                return not ci.issue_contract_check(text, set(), "agent-first", registry, today=date(2026, 10, 7))[0]
            except Exception:  # noqa: BLE001 - an early validator raising is also a rejection
                return True

        self.assertTrue(rejected(body.replace("2026-10-01", "2024-01-01")))
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


if __name__ == "__main__":
    unittest.main()
