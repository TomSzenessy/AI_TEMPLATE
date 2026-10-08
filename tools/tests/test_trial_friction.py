"""The trial friction counter counts gates that blocked the agent, not test fixtures (#9).

In the 2026-10-08 Haiku ledger-cli trial, `make done 2>&1 | tail -100` printed the
kit suite's own fixture output ("Commit blocked ... src/a.py:1"), and the report
counted it as a gate block.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kit import trial  # noqa: E402

FIXTURE_NOISE = (
    "....Commit blocked by the self-healing gate (docs/self-healing.md):\n- [markers] task marker without issue reference: src/a.py:1\n"
    "......\n----------------------------------------------------------------------\nRan 369 tests in 140.2s\n\nOK\n"
    "All gates passed. Get the review your risk tier requires, then hand over or open the PR.\n"
)
REAL_AFTER_TESTS = (
    "....\n----------------------------------------------------------------------\nRan 12 tests in 0.1s\n\nOK\n"
    "repository check failed:\n- [manifest-structure] unregistered product surface: cmd\n"
)


def analyse(output: str) -> dict[str, object]:
    events = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "make done 2>&1 | tail -100"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a", "content": output}]}},
    ]
    with tempfile.TemporaryDirectory() as folder:
        transcript = Path(folder) / "t.jsonl"
        transcript.write_text("\n".join(json.dumps(event) for event in events) + "\n")
        return trial.analyze_transcript(transcript)


class FrictionCounterTests(unittest.TestCase):
    def test_gate_phrases_printed_by_the_test_suite_are_not_blocks(self) -> None:
        self.assertEqual(analyse(FIXTURE_NOISE)["gate_blocks"], [])

    def test_a_gate_that_fails_after_the_suite_still_counts(self) -> None:
        blocks = analyse(REAL_AFTER_TESTS)["gate_blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertIn("unregistered product surface", blocks[0]["message"])

    def test_without_a_suite_the_whole_output_is_judged(self) -> None:
        self.assertEqual(len(analyse("Commit blocked by the self-healing gate:\n- docs/a.md")["gate_blocks"]), 1)


if __name__ == "__main__":
    unittest.main()
