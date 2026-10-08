"""Docs, hygiene, navigation and change coupling (split from the former single test_kit.py, #43)."""

from __future__ import annotations

import sys
import textwrap
import tomllib
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import (TOOLS, KitRepository, Scratch, template_only)  # noqa: E402

from kit import (checkrun, commands, coupling, derive, docmeta, docsync, hygiene, navigate, reachability, registry, risk, structure)  # noqa: E402
from kit.gitinfo import path_matches  # noqa: E402


# Built by concatenation so this test file never trips the marker scanner itself.

TASK = "TO" + "DO"
DEPRECATED = "DEPRE" + "CATED"
ANNOTATION = "@" + "deprecated"


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
        doc_bindings = docmeta.bindings(self.root, self.files())
        self.assertEqual(doc_bindings, {"docs/billing.md": ["src/billing/**"]})
        self.assertEqual(docsync.owners(doc_bindings, "src/billing/invoice.py"), ["docs/billing.md"])

    def test_inline_code_examples_are_not_bindings(self) -> None:
        self.write("docs/guide.md", "# Guide\n\nWrite `<!-- covers: nowhere/** -->` near the top.\n")
        self.assertNotIn("docs/guide.md", docmeta.bindings(self.root, self.files() + ["docs/guide.md"]))

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
        hard, advisory = checkrun.run_checks(self.root, blocking_only=False, skip=self.CONTRACT)
        self.assertIn("over its 200-byte budget", "\n".join(advisory))  # advisory since #9: reported, never blocking
        self.assertNotIn("byte budget", "\n".join(hard))


class ChangeCouplingTests(Scratch):
    """Issue #24: recent history reports the areas that co-change, and never blocks."""

    def commit_touching(self, paths: list[str], message: str) -> None:
        for path in paths:
            self.write(path, f"{message}\n")
            self.git("add", path)
        self.git("commit", "-q", "-m", message)

    def history(self) -> None:
        self.git("init", "-q", "-b", "main")

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
        hard, advisory = checkrun.run_checks(self.root, blocking_only=False)
        self.assertNotIn("co-change", "\n".join(hard), "make check never reports coupling")
        self.assertIn("co-change", "\n".join(advisory), "make garden reports it")

    def write_manifest(self) -> None:
        self.write("project.toml", 'schema = 1\nname = "Demo"\nkind = "cli"\nphase = "development"\n')
        self.git("add", "project.toml")
        self.git("commit", "-q", "-m", "manifest")

    def test_the_history_scan_is_a_bounded_window_not_a_stopwatch(self) -> None:
        """#24's cost claim is the bounded window, so assert the window (#43 T-08), never elapsed time."""
        self.history()
        for number in range(coupling.MIN_SHARED + 1):
            self.commit_touching(["src/a/one.py", "src/b/two.py"], f"old pair {number}")
        for number in range(coupling.MIN_SHARED + 1):
            self.commit_touching(["src/c/three.py", "src/d/four.py"], f"recent pair {number}")
        deep = coupling.coupling_findings(self.root, limit=100)
        self.assertTrue(any("src/a" in item and "src/b" in item for item in deep), deep)
        shallow = coupling.coupling_findings(self.root, limit=coupling.MIN_SHARED + 1)
        self.assertFalse(any("src/a" in item and "src/b" in item for item in shallow),
                         "history past the window is never read")
        self.assertTrue(any("src/c" in item and "src/d" in item for item in shallow), shallow)
        self.assertIsInstance(coupling.coupling_findings(TOOLS.parent), list,
                              "the kit's own history goes through the same bounded scan")


class ReachabilityAdvisoryTests(Scratch):
    """Issue #17 as it now stands: advice about files nothing names, never a gate.

    Every assertion is on message *content*, so a revert of the classification shows up as
    changed text instead of passing quietly. Fixtures use paths outside the kit's own tree
    on purpose: the blocking class that once covered only `tools/` is gone, and a test
    written around `tools/` paths would keep passing whatever the rule became.
    """

    MANIFEST = 'schema = 1\nname = "Demo"\nkind = "cli"\nphase = "development"\n'

    def setUp(self) -> None:
        super().setUp()
        self.write("project.toml", self.MANIFEST)
        self.documents()

    def documents(self, body: str = "# API\n") -> None:
        """An indexed document, so the fixture's own prose is never part of what is judged."""
        self.write("docs/README.md", "# Docs\n\n- [API](api.md)\n")
        self.write("docs/api.md", body)

    def advisories(self) -> tuple[dict[str, str], dict[str, str]]:
        unreferenced, host_read = reachability.advisories(checkrun.Context(self.root))
        return ({item.split(":")[0]: item for item in unreferenced},
                {item.split(":")[0]: item for item in host_read})

    def test_an_unnamed_file_is_reported_with_the_three_fixes(self) -> None:
        self.write("src/app/thing.py", "VALUE = 1\n")
        reported, _ = self.advisories()
        self.assertIn("src/app/thing.py", reported)
        message = reported["src/app/thing.py"]
        self.assertIn("nothing in the tree names it unambiguously", message)
        self.assertIn("import or call it", message)
        self.assertIn("<!-- covers: src/app/thing.py -->", message)
        self.assertIn("delete it if it is dead", message)

    def test_a_bound_imported_or_loaded_file_is_not_reported(self) -> None:
        # main.py is the entry point a doc binds; imported.py is named only by the import.
        self.documents("# API\n\n<!-- covers: src/app/used.py src/app/main.py -->\n")
        self.write("src/app/used.py", "VALUE = 1\n")
        self.write("src/app/imported.py", "VALUE = 2\n")
        self.write("src/app/main.py", "from . import imported\n\nprint(imported.VALUE)\n")
        self.write("tests/test_main.py", "def test_main():\n    assert True\n")
        self.write("Makefile", "test:\n\tpython3 -m unittest discover -s tests\n")
        reported, _ = self.advisories()
        self.assertEqual([path for path in reported if path.endswith(".py")], [], reported)

    def test_host_read_configuration_has_its_own_report(self) -> None:
        self.write(".editorconfig", "root = true\n")
        reported, host_read = self.advisories()
        self.assertNotIn(".editorconfig", reported, "it has its own report, not the general one")
        self.assertIn(".editorconfig", host_read)
        self.assertIn("a host reads it by fixed path", host_read[".editorconfig"])

    def test_a_discovered_tree_is_reported_with_the_runner_reason(self) -> None:
        self.write("tests/test_main.py", "def test_main():\n    assert True\n")
        self.write("Makefile", "lint:\n\ttrue\n")  # nothing loads the tree by name: the runner does
        reported, _ = self.advisories()
        self.assertIn("tests/test_main.py", reported)
        self.assertIn("a test or build runner discovers it", reported["tests/test_main.py"])

    def test_a_framework_tree_is_reported_with_its_reason(self) -> None:
        self.write("apps/store/migrations/0002_add_email.py", "def upgrade():\n    pass\n")
        reported, _ = self.advisories()
        self.assertIn("apps/store/migrations/0002_add_email.py", reported)
        self.assertIn("a framework tree a tool walks by convention", reported["apps/store/migrations/0002_add_email.py"])

    def test_a_shared_name_does_not_mask_a_dead_file(self) -> None:
        """Defends: the residual where one stray mention of a common stem hid a dead file.

        The ambiguity rule was written after `.gitignore` and `LICENSE` dropped out of this
        repository's report. The fixture uses two modules with the same name instead, which
        is the shape the rule was not written from.
        """
        self.write("tools/alpha/helper.py", "VALUE = 1\n")
        self.write("tools/beta/helper.py", "VALUE = 2\n")
        self.write("tools/user.py", "from .alpha import helper\n\nprint(helper.VALUE)\n")
        self.documents("# API\n\n<!-- covers: tools/user.py -->\n")
        reported, _ = self.advisories()
        self.assertIn("tools/beta/helper.py", reported, "the dead twin must not hide behind its name")

    def test_declared_infrastructure_is_silenced(self) -> None:
        self.write("vendor/thing.py", "VALUE = 1\n")
        self.write("project.toml", self.MANIFEST + '[repository]\ninfrastructure_paths = ["vendor"]\n')
        reported, host_read = self.advisories()
        self.assertEqual((reported, host_read), ({}, {}), "a declared tree is not judged at all")

    def test_kit_artifacts_need_no_project_declaration(self) -> None:
        self.write("review.md", "Issue: #1\nReviewer: octocat\nDate: 2026-09-01\n")
        self.write("HANDOVER.md", "# Handover\n")
        self.write("VISION.md", "# Vision\n")
        reported, host_read = self.advisories()
        self.assertEqual((reported, host_read), ({}, {}), "kit-owned paths are exempt by default")

    @template_only
    def test_this_repository_reports_no_module_of_its_own(self) -> None:
        unreferenced, _ = reachability.advisories(checkrun.Context(TOOLS.parent))
        modules = [item.split(":")[0] for item in unreferenced if item.split(":")[0].startswith("tools/")]
        self.assertEqual(modules, [], "every module of the kit is reachable from something in the tree")


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


if __name__ == "__main__":
    unittest.main()
