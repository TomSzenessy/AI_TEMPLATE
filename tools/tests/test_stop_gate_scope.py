"""The Stop hook asks only about paths this session changed; finish judges the whole branch (#29)."""

from __future__ import annotations

import json
import unittest

import test_kit


class StopGateScopeTests(test_kit.KitRepository):
    def setUp(self) -> None:
        super().setUp()
        self.write("docs/auth.md", "# Auth\n\n<!-- covers: src/auth/** -->\n\nRun `make check`.\n")
        self.commit("auth doc")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 2\n")  # dirty before the session

    def start(self) -> None:
        self.cli("hook", "session-start", stdin=json.dumps({"session_id": "s1"}))

    def stop(self) -> str:
        return self.cli("hook", "stop", stdin=json.dumps({"session_id": "s1"})).stdout

    def test_read_only_session_is_not_blocked_by_existing_edits(self) -> None:
        self.start()
        self.assertEqual(self.stop(), "")

    def test_session_edit_reports_only_that_files_doc(self) -> None:
        self.start()
        self.write("src/auth/login.py", "def login():\n    return False\n")
        reason = json.loads(self.stop())["reason"]
        self.assertIn("docs/auth.md covers changed src/auth/login.py", reason)
        self.assertNotIn("docs/billing.md", reason)

    def test_finish_still_judges_the_whole_change_set(self) -> None:
        self.start()
        result = self.cli("finish")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/billing.md covers changed src/billing/invoice.py", result.stdout)

    def test_edit_reverted_to_the_snapshot_is_not_reported(self) -> None:
        self.start()
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 9\n")
        self.assertIn("docs/billing.md", json.loads(self.stop())["reason"])
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 2\n")
        self.assertEqual(self.stop(), "")

    def test_no_snapshot_keeps_the_whole_tree_behaviour(self) -> None:
        reason = json.loads(self.stop())["reason"]
        self.assertIn("docs/billing.md covers changed src/billing/invoice.py", reason)

    def test_session_commit_of_high_risk_file_still_reported(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.start()
        self.write("src/auth/login.py", "def login():\n    return False\n")
        self.git("add", "src/auth/login.py")
        self.git("commit", "-q", "-m", "auth change")
        reason = json.loads(self.stop())["reason"]
        self.assertIn("docs/auth.md covers changed src/auth/login.py", reason)
        self.assertIn("no critic evidence", reason)
        self.assertNotIn("docs/billing.md", reason)

    def test_unresolvable_start_commit_falls_back_to_whole_tree(self) -> None:
        self.start()
        from kit import session
        path = session.state_path(self.root)
        state = json.loads(path.read_text())
        state["snapshot_head"] = "0" * 40
        path.write_text(json.dumps(state))
        self.assertIn("docs/billing.md", json.loads(self.stop())["reason"])

    def test_hook_state_keeps_existing_keys(self) -> None:
        from kit import session
        session.state_path(self.root).write_text(json.dumps({"session": "s1", "noted": ["docs/billing.md"]}))
        self.start()
        state = json.loads(session.state_path(self.root).read_text())
        self.assertEqual(state["noted"], ["docs/billing.md"])
        self.assertIn("src/billing/invoice.py", state["snapshot"])


    def test_session_state_survives_a_scaffolder_that_empties_the_folder(self) -> None:
        # `npm create vite . --overwrite` keeps .git and deletes everything else, ignored files included.
        from kit import session
        self.start()
        self.assertIn(".git", session.state_path(self.root).parts)
        import shutil
        for child in self.root.iterdir():
            if child.name != ".git":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        self.git("checkout", "--", ".")  # the agent restores the tracked files
        self.assertIn("snapshot", json.loads(session.state_path(self.root).read_text()))


if __name__ == "__main__":
    unittest.main()
