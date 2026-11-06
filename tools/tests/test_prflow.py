"""Batching finished work: make ready and make integrate refusals (#152)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import Scratch  # noqa: E402

from kit import prflow  # noqa: E402


class ReadyTests(Scratch):
    def repo(self) -> None:
        self.write("project.toml", 'schema = 1\nname = "Demo"\nkind = "web"\n[repository]\ndefault_branch = "main"\n')
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "initial")
        self.git("checkout", "-q", "-b", "feature")

    def test_a_dirty_tree_is_refused_before_anything_runs(self) -> None:
        self.repo()
        self.write("notes.txt", "unfinished\n")
        called = []
        code, message = prflow.ready(self.root, verify=lambda root: called.append("verify") or 0)
        self.assertEqual(code, 1)
        self.assertIn("commit or stash", message)
        self.assertEqual(called, [])

    def test_a_failing_make_done_is_never_pushed(self) -> None:
        self.repo()
        pushed = []
        code, message = prflow.ready(
            self.root, verify=lambda root: 1,
            push=lambda root, branch: pushed.append(branch) or 0)
        self.assertEqual(code, 1)
        self.assertIn("make done failed", message)
        self.assertEqual(pushed, [])

    def test_a_clean_branch_pushes_once_and_marks_ready(self) -> None:
        self.repo()
        calls = []
        code, message = prflow.ready(
            self.root,
            verify=lambda root: calls.append("done") or 0,
            push=lambda root, branch: calls.append(("push", branch)) or 0,
            pr_ready=lambda root: calls.append("ready") or 0)
        self.assertEqual(code, 0, message)
        self.assertEqual(calls, ["done", ("push", "feature"), "ready"])
        self.assertIn("pushed once", message)

    def test_a_gate_that_leaves_derived_files_is_not_pushed(self) -> None:
        self.repo()

        def verify(root: Path) -> int:
            (root / "Makefile").write_text("regenerated\n")
            return 0

        pushed = []
        code, message = prflow.ready(
            self.root, verify=verify,
            push=lambda root, branch: pushed.append(branch) or 0)
        self.assertEqual(code, 1)
        self.assertIn("changed derived files", message)
        self.assertEqual(pushed, [])

    def test_the_default_branch_itself_is_refused(self) -> None:
        self.repo()
        self.git("checkout", "-q", "main")
        code, message = prflow.ready(self.root, verify=lambda root: 0)
        self.assertEqual(code, 1)
        self.assertIn("not a finished feature branch", message)


class IntegrateTests(Scratch):
    def test_a_batch_needs_at_least_one_branch(self) -> None:
        code, message = prflow.integrate(self.root, [])
        self.assertEqual(code, 1)
        self.assertIn("BRANCHES", message)

    def test_closing_references_are_deduplicated_in_order(self) -> None:
        text = "Fixes #12\n\nwork\n\nCloses #13\n\nResolves #14\n\nFixes #12\n"
        self.assertEqual(prflow.closing_references(text), [12, 13, 14])
        self.assertEqual(prflow.named_references("refs #4, fixes #5 and #4"), [4, 5])


if __name__ == "__main__":
    unittest.main()
