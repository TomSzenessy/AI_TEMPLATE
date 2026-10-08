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
BROKEN = "# Billing\n\n<!-- covers: src/billing/** -->\n\nSee [the guide](./missing-guide.md).\n"


class StopRunsRepositoryChecksTests(KitRepository):
    def stop(self) -> str:
        return self.cli("hook", "stop", stdin=SESSION).stdout

    def test_a_session_edit_that_breaks_make_check_blocks(self) -> None:
        self.cli("hook", "session-start", stdin=SESSION)
        self.write("docs/billing.md", BROKEN)
        self.assertIn("[markdown-links]", self.cli("check").stderr, "the fixture must break make check")
        decision = json.loads(self.stop())
        self.assertEqual(decision["decision"], "block")
        self.assertIn("[markdown-links]", decision["reason"])

    def test_a_session_that_changed_nothing_is_not_blocked_by_old_findings(self) -> None:
        self.write("docs/billing.md", BROKEN)
        self.commit("broken before the session")
        self.cli("hook", "session-start", stdin=SESSION)
        self.assertEqual(self.stop(), "")

    def test_findings_from_before_the_session_do_not_block_an_unrelated_edit(self) -> None:
        self.write("docs/billing.md", BROKEN)
        self.commit("broken before the session")
        self.cli("hook", "session-start", stdin=SESSION)
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 3\n")
        self.write("docs/billing.md", BROKEN + "\nReturns 3.\n")
        self.assertEqual(self.stop(), "")

    def test_a_clean_session_edit_passes(self) -> None:
        self.cli("hook", "session-start", stdin=SESSION)
        self.write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nReturns 3. `make check`.\n")
        self.assertEqual(self.stop(), "")


if __name__ == "__main__":
    unittest.main()
