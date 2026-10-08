"""A trial ends when the agent's result is in, not when its leftover background work does."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kit import evals, trial  # noqa: E402

LINGERING = [sys.executable, "-c",
             "import sys, time; print('{\"type\":\"result\"}', flush=True); time.sleep(60)"]


class FinishedAgentTests(unittest.TestCase):
    def test_a_finished_agent_with_lingering_work_is_ended_after_the_grace(self) -> None:
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(evals, "FINISHED_GRACE", 1):
            transcript = Path(folder) / "t.jsonl"
            started = time.monotonic()
            with transcript.open("w") as output:
                evals.run_headless(LINGERING, Path(folder), 120, stdout=output,
                                   finished=lambda: trial._has_result(transcript))
            self.assertLess(time.monotonic() - started, 30, "the runner waited for the lingering process")
            self.assertIn('"type":"result"', transcript.read_text())

    def test_an_unfinished_agent_still_hits_the_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            transcript = Path(folder) / "t.jsonl"
            with transcript.open("w") as output, self.assertRaises(Exception):
                evals.run_headless([sys.executable, "-c", "import time; time.sleep(60)"], Path(folder), 2,
                                   stdout=output, finished=lambda: trial._has_result(transcript))


if __name__ == "__main__":
    unittest.main()
