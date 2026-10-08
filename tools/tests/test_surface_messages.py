"""Round-5 Haiku trial findings: messages name their fix; ignored build output is not a surface."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import Scratch  # noqa: E402

from kit import structure  # noqa: E402
from kit.core import RepoctlError  # noqa: E402

PROJECT = {"name": "ledger", "kind": "cli"}


class IgnoredOutputIsNotASurfaceTests(Scratch):
    def test_a_git_ignored_directory_is_not_a_candidate(self) -> None:
        self.git("init", "-q")
        self.write(".gitignore", "*.egg-info/\n")
        self.write("ledger_cli.egg-info/PKG-INFO", "Name: ledger\n")
        self.write("ledger/__init__.py", "")
        candidates = structure.discover_candidate_surfaces(self.root, PROJECT)
        self.assertIn("ledger", candidates)
        self.assertNotIn("ledger_cli.egg-info", candidates)

    def test_outside_git_nothing_is_dropped(self) -> None:
        self.write("ledger_cli.egg-info/PKG-INFO", "Name: ledger\n")
        self.assertIn("ledger_cli.egg-info", structure.discover_candidate_surfaces(self.root, PROJECT))


class ReadmeIdentityMessageTests(Scratch):
    def test_the_messages_quote_the_lines_to_write(self) -> None:
        self.write("README.md", "# Ledger\n")
        with self.assertRaisesRegex(RepoctlError, r"restore the line '<!-- repoctl:project-readme -->'"):
            structure.check_readme_identity(self.root, PROJECT)
        self.write("README.md", "# Ledger\n<!-- repoctl:project-readme -->\n")
        with self.assertRaisesRegex(RepoctlError, r"> Project initialized: \*\*ledger\*\* \(`cli`\)"):
            structure.check_readme_identity(self.root, PROJECT)
        self.write("README.md", "# Ledger\n<!-- repoctl:project-readme -->\n> Project initialized: **ledger** (`cli`)\n")
        structure.check_readme_identity(self.root, PROJECT)


if __name__ == "__main__":
    unittest.main()
