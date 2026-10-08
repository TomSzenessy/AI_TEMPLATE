"""Adapters, the capability model, CI checks and evals (split from the former single test_kit.py, #43)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import (RECENT, TOOLS, KitRepository, clean_env)  # noqa: E402

from kit import (core, ci, derive, evals, garden, navigate, registry)  # noqa: E402


CONTRACT_HEADINGS = "".join(f"### {heading}\nx\n" for heading in ci.CANONICAL["agent-first"])
DUPLICATE_LINE = "Duplicate check: searched title, symptom, and path for x; no duplicate found\n"


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
                                capture_output=True, text=True, env=clean_env())
        self.assertFalse(marker.exists(), result.stdout + result.stderr)


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
        valid, labels, reasons = ci.issue_contract_check(body, set(), "agent-first", registry, today=core.today())
        self.assertTrue(valid, reasons)
        self.assertIn("topic:ci-checks", labels)
        def rejected(text: str) -> bool:
            try:
                return not ci.issue_contract_check(text, set(), "agent-first", registry, today=core.today())[0]
            except Exception:  # noqa: BLE001 - an early validator raising is also a rejection
                return True

        self.assertFalse(rejected(body.replace(RECENT, (core.today() - timedelta(days=500)).isoformat())),
                         "a review date belongs to the text it reviewed; it never ages out")
        self.assertTrue(rejected(body.replace(RECENT, (core.today() + timedelta(days=3)).isoformat())))
        reasons = ci.issue_contract_check(body.replace("### Topic\nci-checks", "### Topic\nNot Kebab"), set(),
                                          "agent-first", registry)[2]
        self.assertIn("Topic must be kebab-case: Not Kebab", reasons, "the comment names the fix")
        self.assertTrue(rejected(body.replace("ordinary", "unclassified")))
        self.assertTrue(rejected(body.replace("### Topic\nci-checks", "### Topic\nNot Kebab")))
        with self.assertRaisesRegex(Exception, "Regulated profile uses the CLI"):
            ci.issue_contract_check(body, set(), "regulated", registry)

    def test_pr_reference_accepts_both_closing_keywords(self) -> None:
        for keyword in ("Closes", "Fixes", "closes", "FIXES"):
            with self.subTest(keyword=keyword):
                self.assertIn("#6", ci.pr_reference_check(f"{keyword} #6", set(), "OWNER", "agent-first", lambda n: self.issue()))

    def test_private_security_pr_needs_label_owner_attestation_and_a_trusted_author(self) -> None:
        reference = "Security-Reference: GHSA-abcd-efgh-ijkl\n"
        attested = reference + "Security-Review: maintainer-attested\nSecurity-Owner: @maintainer\n"
        never = lambda number: self.fail("a private review fetches no issue")  # noqa: E731
        self.assertEqual(ci.pr_reference_check(attested, {"security-reviewed"}, "OWNER", "agent-first", never),
                         "Private review attested")
        for name, body, labels, association in (
            ("no label", attested, set(), "OWNER"),
            ("untrusted author", attested, {"security-reviewed"}, "CONTRIBUTOR"),
            ("no attestation", reference, {"security-reviewed"}, "OWNER"),
            ("no owner", reference + "Security-Review: maintainer-attested\n", {"security-reviewed"}, "OWNER"),
        ):
            with self.subTest(name), self.assertRaisesRegex(Exception, "Private security PRs require"):
                ci.pr_reference_check(body, labels, association, "agent-first", never)

    def test_run_pr_reference_reads_the_event_and_the_author_association(self) -> None:
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "project.toml").write_text('schema = 1\nname = "Demo"\nkind = "web"\nphase = "development"\n')
            event = root / "event.json"
            event.write_text(json.dumps({"pull_request": {"body": "Security-Reference: GHSA-abcd-efgh-ijkl\n"
                                                                 "Security-Review: maintainer-attested\nSecurity-Owner: @maintainer\n",
                                                          "labels": [{"name": "security-reviewed"}]}}))
            environment = {"GITHUB_EVENT_PATH": str(event), "GITHUB_REPOSITORY": "o/r", "GITHUB_API_URL": "https://api.invalid",
                           "GH_TOKEN": "unused"}
            with mock.patch.dict("os.environ", {**environment, "PR_AUTHOR_ASSOCIATION": "OWNER"}):
                self.assertEqual(ci.run_pr_reference(root), "Private review attested")
            with mock.patch.dict("os.environ", {**environment, "PR_AUTHOR_ASSOCIATION": "NONE"}), \
                    self.assertRaisesRegex(Exception, "Private security PRs require"):
                ci.run_pr_reference(root)

    def test_issue_intake_is_refused_where_the_profile_owns_it(self) -> None:
        registry = json.loads((TOOLS.parent / ".github/issue-labels.json").read_text())
        for profile, expected in (("regulated", "Regulated profile uses the CLI/private issue route"),
                                  ("minimal", "Minimal profile delegates issue intake")):
            with self.subTest(profile), self.assertRaisesRegex(Exception, expected):
                ci.issue_contract_check("", set(), profile, registry)


class EvalCommandTests(unittest.TestCase):
    def test_model_flag_is_passed_only_when_set(self) -> None:
        with_model = evals.HOST_COMMANDS["claude"]("task", "haiku")
        self.assertEqual(with_model[with_model.index("--model") + 1], "haiku")
        self.assertNotIn("--model", evals.HOST_COMMANDS["claude"]("task", ""))
        self.assertIn("--sandbox", evals.HOST_COMMANDS["codex"]("task", ""))


class DecisionAgeTests(unittest.TestCase):
    def test_old_decision_only_matters_at_the_release_gate(self) -> None:
        from datetime import timedelta
        old, future = core.today() - timedelta(days=500), core.today() + timedelta(days=2)
        self.assertFalse(core.date_out_of_policy(old, release_gate=False), "make check must not rot with the calendar")
        self.assertTrue(core.date_out_of_policy(old, release_gate=True))
        self.assertTrue(core.date_out_of_policy(future, release_gate=False), "a future date is a typo")

    def test_critic_evidence_age_gates_release_only(self) -> None:
        from datetime import timedelta
        from kit import structure
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = (core.today() - timedelta(days=500)).isoformat()
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
            skill["reviewed_on"] = (core.today() - timedelta(days=500)).isoformat()
        skills.check_skill_provenance(project)  # development: make garden reports the age instead
        with self.assertRaisesRegex(Exception, "older than a year"):
            skills.check_skill_provenance(project, release_gate=True)


class PinDriftTests(KitRepository):
    def test_behind_pins_are_advisory_findings(self) -> None:
        self.write(".agents/mcp/browser.toml", 'name = "browser"\ndescription = "Real browser for UI checks."\ntransport = "stdio"\ncommand = ["npx", "-y", "@playwright/mcp@0.0.83"]\n')
        from kit.config import setting
        latest = {"playwright": str(setting(self.root, "playwright_version")), "@playwright/mcp": "0.0.90"}
        findings = garden.pin_drift(self.root, view=latest.get)
        self.assertEqual(len(findings), 1)
        self.assertIn("@playwright/mcp@0.0.83 (.agents/mcp/browser.toml) is behind 0.0.90", findings[0])
        self.assertEqual(garden.pin_drift(self.root, view=lambda package: None), [], "offline: no finding")


if __name__ == "__main__":
    unittest.main()
