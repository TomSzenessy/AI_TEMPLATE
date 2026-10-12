"""The adoption split keeps navigation and project-owned bindings correct (#72)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import Scratch, template_only
from kit import docmeta, docsync

REPO = Path(__file__).resolve().parents[2]


@template_only
class AdoptDocPointersTests(Scratch):
    def test_index_keeps_the_full_adopt_command(self) -> None:
        self.write("project.toml", 'schema = 1\nname = "app"\nkind = "web"\n')
        self.write("docs/adopt.md", (REPO / "docs/adopt.md").read_text(encoding="utf-8"))
        rendered = docsync.render_index(self.root, ["docs/adopt.md"])
        self.assertIn("make adopt: what it merges, renames, and keeps", rendered)

    def test_project_owned_makefile_and_ci_do_not_stale_adaptation(self) -> None:
        self.write("docs/ADAPTATION.md", (REPO / "docs/ADAPTATION.md").read_text(encoding="utf-8"))
        self.write("Makefile", "all:\n\ttrue\n")
        self.write(".github/workflows/ci.yml", "name: project-ci\n")
        self.git("init", "-q")
        self.commit("adopted project")
        self.write("Makefile", "all:\n\techo changed\n")
        self.write(".github/workflows/ci.yml", "name: changed-project-ci\n")
        self.commit("project-owned build changes")
        bindings = docmeta.bindings(self.root, ["docs/ADAPTATION.md"])
        for path in ("Makefile", ".github/workflows/ci.yml"):
            self.assertNotIn("docs/ADAPTATION.md", docmeta.owners(bindings, path))
        self.assertEqual(docsync.stale_documents(self.root, bindings), [])

    def test_runtime_adoption_reminder_points_to_the_existing_section(self) -> None:
        source = (REPO / "tools/kit/adopt.py").read_text(encoding="utf-8")
        self.assertIn("docs/adopt.md#kit-ci-and-your-toolchains", source)
        self.assertNotIn("docs/ADAPTATION.md#kit-ci-and-your-toolchains", source)

    def test_adopted_workflow_source_points_to_the_adopt_owner(self) -> None:
        workflow = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("docs/adopt.md", workflow)
        self.assertNotIn("docs/ADAPTATION.md", workflow)


if __name__ == "__main__":
    unittest.main()
