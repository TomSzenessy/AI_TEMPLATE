"""A session cannot stop on `make check` findings it introduced (#9).

In the 2026-10-08 Haiku trials, poster-press reported "MVP Complete" while its
`make check` had five blocking findings: the stop hook ran only the change-set gate.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import KitRepository  # noqa: E402

SESSION = json.dumps({"session_id": "s-check"})
BROKEN = "# Billing\n\n<!-- covers: src/billing/** -->\n<!-- covers: gone/missing-guide/** -->\n\nReturns 2.\n"


class StopRunsRepositoryChecksTests(KitRepository):
    def stop(self) -> str:
        return self.cli("hook", "stop", stdin=SESSION).stdout

    def test_a_session_edit_that_breaks_make_check_blocks(self) -> None:
        self.cli("hook", "session-start", stdin=SESSION)
        self.write("docs/billing.md", BROKEN)
        self.assertIn("[dead-bindings]", self.cli("check").stderr, "the fixture must break make check")
        decision = json.loads(self.stop())
        self.assertEqual(decision["decision"], "block")
        self.assertIn("[dead-bindings]", decision["reason"])

    def test_a_session_that_changed_nothing_is_not_blocked_by_old_findings(self) -> None:
        self.write("docs/billing.md", BROKEN)
        self.commit("broken before the session")
        self.cli("hook", "session-start", stdin=SESSION)
        self.assertEqual(self.stop(), "")

    def test_findings_from_before_the_session_do_not_block_an_unrelated_edit(self) -> None:
        self.write("docs/stray.md", "# Stray\n")  # unindexed: a docs-index finding that predates the session
        self.commit("unindexed before the session")
        self.assertIn("[docs-index]", self.cli("check").stderr, "the fixture must break make check")
        self.cli("hook", "session-start", stdin=SESSION)
        self.write("src/util.py", "def helper():\n    return 3\n")  # nothing binds this; billing.md stays as it was
        self.assertEqual(self.stop(), "")

    def test_a_clean_session_edit_passes(self) -> None:
        self.cli("hook", "session-start", stdin=SESSION)
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nReturns 3. `make check`.\n")
        self.assertEqual(self.stop(), "")


ACTIVE = json.dumps({"session_id": "s-check", "stop_hook_active": True})


class StopChainTests(KitRepository):
    """While the agent continues because of the gate, it is judged again if it made progress."""

    def stop(self, event: str) -> str:
        return self.cli("hook", "stop", stdin=event).stdout

    def break_link(self, name: str) -> None:
        self.write("docs/billing.md", BROKEN.replace("missing-guide", name))

    def test_new_findings_during_the_chain_block_again(self) -> None:
        self.cli("hook", "session-start", stdin=SESSION)
        self.break_link("first")
        self.assertIn("gone/first/", json.loads(self.stop(SESSION))["reason"])
        self.break_link("second")  # "fixed" the first, introduced another
        self.assertIn("gone/second/", json.loads(self.stop(ACTIVE))["reason"])

    def test_no_progress_in_the_chain_lets_the_agent_stop(self) -> None:
        self.cli("hook", "session-start", stdin=SESSION)
        self.break_link("same")
        self.assertTrue(self.stop(SESSION))
        self.assertEqual(self.stop(ACTIVE), "", "same findings again: the agent may stop and explain")

    def test_the_chain_is_capped(self) -> None:
        from kit import session
        self.cli("hook", "session-start", stdin=SESSION)
        self.break_link("n0")
        self.assertTrue(self.stop(SESSION))
        for number in range(1, session.STOP_REPEATS):
            self.break_link(f"n{number}")
            self.assertTrue(self.stop(ACTIVE), number)
        self.break_link("over")
        self.assertEqual(self.stop(ACTIVE), "", "the cap holds even when findings keep changing")


    def test_an_unwritable_state_never_loops(self) -> None:
        from unittest import mock
        from kit import session
        self.cli("hook", "session-start", stdin=SESSION)
        self.break_link("a")
        self.assertTrue(self.stop(SESSION))
        with mock.patch.object(session, "_save_state", side_effect=OSError("read-only")):
            for name in ("b", "c", "d", "e", "f"):
                self.break_link(name)
                self.assertEqual(self.stop(ACTIVE), "", "a push that cannot be recorded is not repeated")

    def test_a_corrupt_chain_count_ends_the_chain(self) -> None:
        from kit import session
        self.cli("hook", "session-start", stdin=SESSION)
        self.break_link("a")
        self.assertTrue(self.stop(SESSION))
        path = session.state_path(self.root)
        state = json.loads(path.read_text())
        state["stop_chain"]["count"] = "garbage"
        path.write_text(json.dumps(state))
        self.break_link("b")
        self.assertEqual(self.stop(ACTIVE), "")


if __name__ == "__main__":
    unittest.main()
