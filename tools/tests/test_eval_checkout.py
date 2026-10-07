"""Evals meet the committed repository, not the live checkout (#46).

A live `make eval` once failed `doc-owner-lookup` because the agent under test
inherited a stop-gate finding about an unrelated uncommitted file and answered
that instead of the question.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import KitRepository  # noqa: E402

from kit import evals  # noqa: E402


class CommittedCheckoutTests(KitRepository):
    def test_agents_see_head_without_uncommitted_edits_and_it_is_removed(self) -> None:
        self.write("scratch-uncommitted.md", "# Not committed\n")
        self.write("docs/billing.md", "# Edited, not committed\n")
        with evals.committed_checkout(self.root) as checkout:
            self.assertNotEqual(checkout, self.root)
            self.assertFalse((checkout / "scratch-uncommitted.md").exists())
            self.assertTrue((checkout / "project.toml").is_file())
            self.assertNotIn("Edited, not committed", (checkout / "docs/billing.md").read_text())
            self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no").strip() != "", True)
        self.assertFalse(checkout.exists(), "the throwaway worktree is removed")
        self.assertEqual(len(self.git("worktree", "list").splitlines()), 1)

    def test_outside_git_the_checkout_itself_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with evals.committed_checkout(Path(temp)) as checkout:
                self.assertEqual(checkout, Path(temp))


if __name__ == "__main__":
    unittest.main()
