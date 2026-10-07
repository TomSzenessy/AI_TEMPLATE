"""The stop gate honours Docs-Unaffected trailers on this session's own commits.

A session that commits covered code with a valid trailer has settled that doc
decision; `make done` agrees. The stop gate used to re-raise it because it fed
the session's committed paths to the uncommitted-only check.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import KitRepository  # noqa: E402

SESSION = json.dumps({"session_id": "s-trailer"})


class StopSessionCommitTests(KitRepository):
    def start_session(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.cli("hook", "session-start", stdin=SESSION)

    def test_a_session_commit_with_a_trailer_does_not_block(self) -> None:
        self.start_session()
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 1  # comment only\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "tidy\n\nDocs-Unaffected: docs/billing.md comment only")
        self.assertEqual(self.cli("hook", "stop", stdin=SESSION).stdout, "")
        self.assertEqual(self.cli("finish").returncode, 0)

    def test_a_session_commit_without_a_trailer_still_blocks(self) -> None:
        self.start_session()
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 4\n")
        self.commit("change without a doc")
        decision = json.loads(self.cli("hook", "stop", stdin=SESSION).stdout)
        self.assertIn("docs/billing.md covers changed src/billing/invoice.py", decision["reason"])

    def test_uncommitted_edits_after_a_trailer_commit_still_block(self) -> None:
        self.start_session()
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 1  # comment only\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "tidy\n\nDocs-Unaffected: docs/billing.md comment only")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 9\n")
        decision = json.loads(self.cli("hook", "stop", stdin=SESSION).stdout)
        self.assertIn("docs/billing.md covers changed src/billing/invoice.py", decision["reason"])


if __name__ == "__main__":
    unittest.main()
