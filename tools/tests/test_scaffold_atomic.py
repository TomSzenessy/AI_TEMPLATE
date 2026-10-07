"""#40: `make new` never leaves partial files behind and edits project.toml safely."""

from __future__ import annotations

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from kit import scaffold  # noqa: E402
from kit.core import RepoctlError  # noqa: E402

BASE = 'schema = 1\nname = "Demo"\nkind = "web"\nphase = "development"\n[adapters]\nhosts = ["claude"]\n'
SKILL = ("release-notes", "Drafts release notes from merged pull requests; before tagging a release.")


class ScaffoldAtomicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "AGENTS.md").write_text("# Agents\n\n<!-- repoctl:rules -->\n<!-- /repoctl:rules -->\n")
        (self.root / "Makefile").write_text("check:\n\t@true\n\n# <repoctl:commands>\n# </repoctl:commands>\n")
        (self.root / "docs").mkdir()
        (self.root / "docs/README.md").write_text("# Index\n\n<!-- repoctl:index -->\n<!-- /repoctl:index -->\n")

    def manifest(self, extra: str) -> Path:
        path = self.root / "project.toml"
        path.write_text(BASE + extra)
        return path

    def skills(self) -> list[str]:
        return tomllib.loads((self.root / "project.toml").read_text())["capabilities"]["local_skills"]

    def test_missing_local_skills_leaves_nothing_and_retry_succeeds(self) -> None:
        path = self.manifest("")
        before = path.read_bytes()
        with self.assertRaises(RepoctlError):
            scaffold.create(self.root, "skill", *SKILL)
        self.assertFalse((self.root / ".agents/skills").exists())
        self.assertEqual(path.read_bytes(), before)
        self.manifest("[capabilities]\nlocal_skills = []\n")
        scaffold.create(self.root, "skill", *SKILL)
        self.assertTrue((self.root / ".agents/skills/release-notes/SKILL.md").exists())
        self.assertEqual(self.skills(), ["release-notes"])

    def test_failure_after_writing_rolls_back_files_and_manifest(self) -> None:
        path = self.manifest("[capabilities]\nlocal_skills = []\n")
        before = path.read_bytes()
        original = scaffold.derive.sync
        scaffold.derive.sync = lambda root: (_ for _ in ()).throw(RepoctlError("boom"))
        try:
            with self.assertRaises(RepoctlError):
                scaffold.create(self.root, "skill", *SKILL)
        finally:
            scaffold.derive.sync = original
        self.assertFalse((self.root / ".agents/skills").exists())
        self.assertEqual(path.read_bytes(), before)

    def test_array_with_comments_and_trailing_comma(self) -> None:
        self.manifest('[capabilities]\nlocal_skills = [\n    "a-skill",  # first ] one\n    # a comment line\n    "b]skill",\n]\nother = 1\n')
        scaffold.create(self.root, "skill", *SKILL)
        text = (self.root / "project.toml").read_text()
        self.assertIn("# a comment line", text)
        self.assertIn("# first ] one", text)
        self.assertEqual(self.skills(), ["a-skill", "b]skill", "release-notes"])
        self.assertEqual(tomllib.loads(text)["capabilities"]["other"], 1)

    def test_inline_array_with_items(self) -> None:
        self.manifest('[capabilities]\nlocal_skills = ["a-skill", "b-skill"]\n')
        scaffold.create(self.root, "skill", *SKILL)
        self.assertEqual(self.skills(), ["a-skill", "b-skill", "release-notes"])

    def test_other_kinds_are_unchanged(self) -> None:
        path = self.manifest("[capabilities]\nlocal_skills = []\n")
        scaffold.create(self.root, "agent", "test-writer", "Writes missing regression tests for one module; when seam coverage is thin.")
        scaffold.create(self.root, "doc", "pricing", "Pricing rules and discounts; when prices change", group="operate")
        self.assertTrue((self.root / ".agents/agents/test-writer.md").exists())
        self.assertTrue((self.root / "docs/pricing.md").exists())
        self.assertEqual(self.skills(), [])
        scaffold.create(self.root, "skill", *SKILL)
        self.assertTrue((self.root / ".agents/skills/release-notes/SKILL.md").exists())
        self.assertIn("release-notes", path.read_text())


if __name__ == "__main__":
    unittest.main()
