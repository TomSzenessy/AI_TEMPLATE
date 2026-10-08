"""Hooks, the commit gate, the critic record and project guardrails (split from the former single test_kit.py, #43)."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import (RECENT, TOOLS, KitRepository, fake_gh)  # noqa: E402

from kit import (session)  # noqa: E402
from kit.core import load_project  # noqa: E402


DUPLICATE_LINE = "Duplicate check: searched title, symptom, and path for x; no duplicate found\n"


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
        blocked = self.git_result("commit", "-q", "-m", "x")
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
        self.assertEqual(self.git_result("config", "--get", "core.hooksPath").stdout.strip(), "")

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
        verbose = self.git_result(
            "-c", "core.hooksPath=/dev/null", "commit", "-q", "-v",
            "-m", "change\n\nDocs-Unaffected: docs/billing.md comment only")
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


class CriticRecordGateTests(KitRepository):
    """The completion gate that reads a critic's verdict: every way it can refuse, guarded.

    This gate blocks `make done` on high-risk work, so each refusal needs a test rather
    than a hand check.
    """

    def project(self) -> dict:
        return load_project(self.root)

    def findings(self) -> str:
        return "\n".join(session.critic_findings(self.root, self.project(), "main"))

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    def high_risk_change(self) -> None:
        """A committed change on a branch: a critic reviews a diff, not the base commit."""
        self.git("checkout", "-q", "-b", "feature")
        self.write("src/auth/login.py", "def login():\n    return 'changed'\n")
        self.commit("fix(auth): rotate the session token")

    def record(self, body: str) -> None:
        self.write(".agent/critic.md", body)
        self.git("add", "-f", ".agent/critic.md")

    def test_low_risk_work_needs_no_critic(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n")
        self.commit("docs: clarify billing")
        self.assertEqual(self.findings(), "", "the gate only judges high-risk changes")

    def test_a_high_risk_change_with_no_record_is_refused(self) -> None:
        self.high_risk_change()
        finding = self.findings()
        self.assertIn("no critic evidence", finding)
        self.assertIn("src/auth/login.py", finding, "the finding names the risky work")
        self.assertIn(".agent/critic.md", finding, "and the record to write")

    def test_a_verdict_outside_the_vocabulary_is_refused(self) -> None:
        self.high_risk_change()
        self.record(f"Verdict: looks good\nCommit: {self.head()}\n")
        finding = self.findings()
        self.assertIn("outside the fixed vocabulary", finding)
        self.assertIn("'looks'", finding, "the message quotes the word it refused")

    def test_a_record_with_no_verdict_is_refused(self) -> None:
        self.high_risk_change()
        self.record(f"Commit: {self.head()}\n")
        self.assertIn("states no verdict", self.findings())

    def test_a_record_with_no_commit_line_is_refused(self) -> None:
        self.high_risk_change()
        self.record("Verdict: ship-with-residuals\n")
        finding = self.findings()
        self.assertIn("no 'Commit: <40-hex>' line", finding)
        self.assertIn("not bound to a reviewed change set", finding)

    def test_a_stale_commit_line_is_refused(self) -> None:
        self.high_risk_change()
        self.write(".agent/critic.md", f"Verdict: ship-with-residuals\nCommit: {'a' * 40}\n")
        self.assertIn("the critic read older work", self.findings())

    def test_a_blocker_verdict_is_refused(self) -> None:
        self.high_risk_change()
        self.write(".agent/critic.md", f"Verdict: blocker\nCommit: {self.head()}\n")
        finding = self.findings()
        self.assertIn("verdict is blocker", finding)
        self.assertIn("ask the critic again", finding)

    def test_ship_with_residuals_at_head_passes(self) -> None:
        self.high_risk_change()
        self.write(".agent/critic.md", f"Verdict: ship-with-residuals\nCommit: {self.head()}\n")
        self.assertEqual(self.findings(), "", "the only passing verdict is the one bound to HEAD")

    def test_the_minimal_profile_opts_out_of_the_gate(self) -> None:
        self.high_risk_change()
        manifest = (self.root / "project.toml").read_text(encoding="utf-8")
        self.write("project.toml", manifest.replace("[governance]\n", "")
                   if "[governance]" in manifest else manifest + '\n[governance]\nprofile = "minimal"\n')
        self.assertEqual(self.findings(), "", "a minimal-profile project owns its own review")


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
        fake_gh(bin_dir, repo="example/demo", url="https://github.com/example/demo/issues/7")
        environment = {"PATH": f"{bin_dir}:{os.environ['PATH']}"}
        self.write("project.toml", (self.root / "project.toml").read_text().replace("[adapters]", '[repository]\ngithub = "example/demo"\n\n[adapters]', 1))
        filing = lambda: self.cli("issue", "--wal", "all", env=environment)
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


if __name__ == "__main__":
    unittest.main()
