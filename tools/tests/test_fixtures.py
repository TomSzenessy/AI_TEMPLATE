"""The shared fixtures' own contract (#43): no ambient git config ever reaches a test.

The suite must pass under a hostile global git config (`commit.gpgsign=true`,
`core.hooksPath`, `core.fsmonitor`): these tests pin the isolation every other
test silently relies on, for fixture git, kit-internal git, and the in-process CLI.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import Scratch, git_in  # noqa: E402


def hostile_home(root: Path) -> Path:
    """A HOME whose .gitconfig breaks every commit and every history read."""
    home = root / "hostile-home"
    home.mkdir()
    (home / ".gitconfig").write_text(
        "[commit]\n\tgpgsign = true\n"
        "[core]\n\thooksPath = " + str(home / "no-such-hooks") + "\n"
        "\tfsmonitor = " + str(home / "no-such-fsmonitor") + "\n",
        encoding="utf-8")
    return home


class GitIsolationTests(Scratch):
    def test_fixture_git_ignores_a_hostile_global_git_config(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": str(hostile_home(self.root))}):
            self.git("init", "-q", "-b", "main")
            self.write("a.txt", "x\n")
            self.commit("initial")  # gpgsign would refuse this commit
            self.assertEqual(self.git("log", "-1", "--format=%s"), "initial\n")  # fsmonitor would break this read
            self.assertEqual(self.git_result("config", "--get", "commit.gpgsign").stdout, "")
            self.assertEqual(self.git_result("config", "--get", "core.hooksPath").stdout, "")


class KitGitIsolationTests(Scratch):
    def test_the_kits_own_git_commits_ignore_a_hostile_global_git_config(self) -> None:
        from kit import trial
        self.git("init", "-q", "-b", "main")
        self.write("a.txt", "x\n")
        with mock.patch.dict(os.environ, {"HOME": str(hostile_home(self.root))}):
            trial._commit(self.root, "kit-driven commit")  # gpgsign in the hostile config would refuse it
            self.assertEqual(git_in(self.root, "log", "-1", "--format=%s").stdout, "kit-driven commit\n")
            result = self.cli("check")  # and the in-process CLI entry point runs the same git
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
