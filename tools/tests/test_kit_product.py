"""Product driver, UI review and scaffolding (split from the former single test_kit.py, #43)."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import (KitRepository, http_server)  # noqa: E402

from kit import (derive, garden, product, uireview)  # noqa: E402


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

    def test_a_list_with_nothing_countable_is_never_called_complete(self) -> None:
        """#55: `all()` over an empty list is vacuously true, so 0% read as 'all evidenced'."""
        # Intake and research come first, so walk the project to the features phase once.
        self.accept_vision()
        self.write(product.RESEARCH, "https://a.example https://b.example https://c.example\n")
        for label, text in (
            ("header only", "feature,area,priority,status,evidence,acceptance,source\n"),
            ("every row skipped", "A,core,must,skip,,works,owner\n"),
        ):
            with self.subTest(label):
                self.write(product.FEATURES, text)
                summary = product.product_summary(self.root)
                self.assertIn("completeness is unknown", summary)
                self.assertNotIn("all must features evidenced", summary)
                self.assertNotIn("0% complete", summary)
                self.assertIn("countable row", " ".join(product.feature_errors(self.root)))
                self.assertEqual(product.next_step(self.root)["phase"], "features")

    def test_a_countable_list_still_scores_and_reports(self) -> None:
        self.features("A,core,must,yes,tests/test_a.py,works,owner", "B,core,could,skip,,works,owner")
        self.write("tests/test_a.py", "def test_a():\n    assert True\n")
        self.assertIn("100% complete", product.product_summary(self.root))
        self.assertEqual(product.feature_errors(self.root), [])


class UiReviewTests(KitRepository):
    def setUp(self) -> None:
        super().setUp()
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
        self.environment = {"PATH": f"{bin_dir}:{os.environ['PATH']}"}

    def review(self) -> subprocess.CompletedProcess[str]:
        return self.cli("ui-review", env=self.environment)

    def test_refuses_a_server_it_did_not_start(self) -> None:
        # A real HTTP answer on a port the operating system picked: no free-port probe to race on (#43 T-08).
        with http_server() as port:
            text = (self.root / "project.toml").read_text().replace("{port}", str(port))
            self.write("project.toml", text)
            result = self.review()
        self.assertEqual(result.returncode, 1)
        self.assertIn("something already answers", result.stderr)

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
        # patch.dict restores the process environment even when the assertion fails (#43 T-08).
        with mock.patch.dict(os.environ, self.environment):
            self.assertTrue(uireview._playwright(self.root)[0].endswith("fakebin/playwright"))
            self.write("project.toml", (self.root / "project.toml").read_text() + '[kit]\nplaywright_version = "1.50.0"\n')
            self.assertEqual(uireview._playwright(self.root), ["npx", "-y", "playwright@1.50.0"])

    def test_review_gates_feature_and_release_not_every_change(self) -> None:
        from kit import launch, session
        self.assertIn("never had a UI review", " ".join(uireview.review_status(self.root)))
        self.assertFalse(any("UI review" in item for item in session.finish_findings(self.root)), "advisory per change")
        text = (self.root / "project.toml").read_text().replace('phase = "development"', 'phase = "private-preview"')
        self.write("project.toml", text)
        with self.assertRaises(Exception) as raised:
            launch.check_readiness(self.root)
        self.assertIn("never had a UI review", str(raised.exception))


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


if __name__ == "__main__":
    unittest.main()
