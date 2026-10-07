"""Kit edge cases: each small defect from #51 has a test that fails without its fix."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import Scratch, git_in  # noqa: E402

from kit import adopt, config, hygiene, launch, product, risk  # noqa: E402
from kit.core import RepoctlError  # noqa: E402
from kit.registry import Registry, frontmatter  # noqa: E402

MANIFEST = 'schema = 1\nname = "Demo"\nkind = "template"\nphase = "bootstrap"\nlicense = "UNSELECTED"\nowners = []\n'
AGENT = ('---\nname: x\ndescription: "A role with \\"quotes\\""\naccess: read-only\ntier: fast\n---\nBody\n')


class FrontmatterTests(Scratch):
    def test_crlf_and_bom_frontmatter_parse(self) -> None:
        for text in (AGENT.replace("\n", "\r\n"), "﻿" + AGENT):
            self.assertEqual(frontmatter(text).get("name"), "x", repr(text[:10]))

    def test_quoted_values_are_unescaped(self) -> None:
        self.assertEqual(frontmatter(AGENT)["description"], 'A role with "quotes"')
        self.assertEqual(frontmatter("---\nname: 'it''s'\n---\n")["name"], "it's")

    def test_crlf_agent_file_loads_as_a_capability(self) -> None:
        self.write("project.toml", MANIFEST)
        self.write(".agents/agents/x.md", AGENT.replace("\n", "\r\n").encode())
        names = [item.name for item in Registry(self.root).of("agent", enabled_only=False)]
        self.assertIn("x", names)

    def test_frontmatter_error_names_the_file(self) -> None:
        self.write("project.toml", MANIFEST)
        self.write(".agents/agents/x.md", "---\nname: x\ndescription: a: b\naccess: full\ntier: fast\n---\n")
        with self.assertRaisesRegex(RepoctlError, r"x\.md.*': '"):
            Registry(self.root).of("agent", enabled_only=False)


class BoolSettingTests(Scratch):
    def test_bool_is_rejected_where_a_number_is_required(self) -> None:
        with self.assertRaisesRegex(RepoctlError, r"overlap_limit must be a float"):
            config.project_setting({"kit": {"overlap_limit": True}}, "overlap_limit")
        self.assertEqual(config.project_setting({"kit": {"overlap_limit": 1}}, "overlap_limit"), 1)

    def test_bool_budget_is_rejected(self) -> None:
        self.write("a.md", "x\n")
        errors = hygiene.budget_errors(self.root, {"budgets": {"a.md": True}}, ["a.md"])
        self.assertTrue(any("positive integer" in item for item in errors), errors)


class RiskTests(Scratch):
    def test_non_table_repository_is_not_an_attribute_error(self) -> None:
        self.write("project.toml", MANIFEST + "repository = 3\n")
        git_in(self.root, "init", "-q")
        tier, _ = risk.assess(self.root)  # already handled before this change; the test keeps it so
        self.assertEqual(tier, "normal")
        self.assertNotIn("Traceback", self.cli("risk").stderr)


class FeaturesTests(Scratch):
    def test_malformed_features_csv_does_not_kill_next(self) -> None:
        self.write("project.toml", MANIFEST.replace('"template"', '"web"').replace("bootstrap", "development"))
        self.write("features.csv", "feature,priority,status\nlogin,urgent,no\n")
        step = product.next_step(self.root)
        self.assertIn(step["phase"], {"intake", "features"})
        if step["phase"] == "features":
            self.assertIn("priority must be", step["action"])


class AdoptTests(Scratch):
    def test_non_utf8_doc_survives_indexing_unchanged(self) -> None:
        raw = b"# Caf\xe9 notes\nbody\n"
        self.write("docs/old.md", raw)
        self.write("docs/ok.md", "# Fine\n")
        adopt.index_existing_docs(self.root, {"docs/old.md", "docs/ok.md"})
        self.assertEqual((self.root / "docs/old.md").read_bytes(), raw)
        self.assertIn("<!-- index:", (self.root / "docs/ok.md").read_text())


class LaunchRouteTests(unittest.TestCase):
    def test_placeholder_hosts_and_subdomains_are_rejected(self) -> None:
        for host in ("localhost", "example.com", "foo.example.com", "box.local", "x.internal"):
            self.assertFalse(launch.valid_private_route(f"https://{host}/report"), host)
        self.assertTrue(launch.valid_private_route("https://security.acme.io/report"))
        self.assertTrue(launch.valid_private_route("https://attacker.io/report"))


if __name__ == "__main__":
    unittest.main()
