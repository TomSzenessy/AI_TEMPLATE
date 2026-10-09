"""The trial report states a verdict, cost per phase, and the kit commands not used (#21)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kit import trial  # noqa: E402

PASSING = {"commits": 1, "next": "Next (launch): ship", "finish_passed": True, "check_passed": True,
           "check": [], "finish": [], "trailers": []}
SPEC = {"id": "t", "mode": "new"}


def tool(identifier: str, command: str) -> dict:
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": identifier, "name": "Bash", "input": {"command": command}}]}}


def result(identifier: str, text: str) -> dict:
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": identifier, "content": text}]}}


def turn(tokens_in: int, tokens_out: int) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": "."}],
                                             "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out}}}


FINISHED = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "total_cost_usd": 0.5,
            "duration_ms": 10, "result": "Done."}


def analyse(*events: dict) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        transcript = Path(folder) / "t.jsonl"
        transcript.write_text("\n".join(json.dumps(event) for event in events) + "\n")
        return trial.analyze_transcript(transcript)


class ReportTests(unittest.TestCase):
    def test_one_message_split_into_blocks_counts_once_with_cache_tokens(self) -> None:
        usage = {"input_tokens": 2, "output_tokens": 3, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 5}
        block = {"type": "assistant", "message": {"id": "m1", "content": [{"type": "text", "text": "."}], "usage": usage}}
        analysis = analyse(block, block, {**block, "message": {**block["message"], "id": "m2"}})
        self.assertEqual(analysis["phases"], [{"phase": "start", "turns": 2, "tokens": 2020}])

    def test_a_run_that_never_started_is_not_a_pass(self) -> None:
        limit = {"type": "result", "subtype": "success", "is_error": True, "num_turns": 1, "total_cost_usd": 0,
                 "duration_ms": 10, "result": "You've hit your session limit"}
        report = trial.render(SPEC, "sonnet", analyse(limit), PASSING, Path("p"))
        self.assertIn("- Verdict: no run (the agent did not work: You've hit your session limit)", report)

    def test_no_result_event_is_never_a_pass(self) -> None:
        # Critic blocker: a timed-out or killed run on an untouched project passes every check.
        report = trial.render(SPEC, "haiku", analyse(tool("a", "make done")), PASSING, Path("p"))
        self.assertIn("- Verdict: no run (the agent produced no final result", report)

    def test_a_host_error_after_real_work_fails(self) -> None:
        cut = {"type": "result", "subtype": "success", "is_error": True, "num_turns": 203, "total_cost_usd": 8.89,
               "duration_ms": 10, "result": "You've hit your session limit"}
        report = trial.render(SPEC, "sonnet", analyse(cut), PASSING, Path("p"))
        self.assertIn("- Verdict: fail (stopped by the host: You've hit your session limit)", report)

    def test_a_bypass_fails_the_run_even_when_every_check_passes(self) -> None:
        analysis = analyse(tool("a", "git commit --no-verify -m x"), FINISHED)
        self.assertIn("- Verdict: fail (gate bypassed with --no-verify)", trial.render(SPEC, "haiku", analysis, PASSING, Path("p")))

    def test_a_clean_run_passes_and_a_failing_check_does_not(self) -> None:
        analysis = analyse(tool("a", "make done"), FINISHED)
        self.assertIn("- Verdict: pass", trial.render(SPEC, "haiku", analysis, PASSING, Path("p")))
        failing = {**PASSING, "check_passed": False}
        self.assertIn("- Verdict: fail (make check did not pass)", trial.render(SPEC, "haiku", analysis, failing, Path("p")))

    def test_turns_and_tokens_are_counted_per_phase(self) -> None:
        analysis = analyse(turn(1, 1), tool("a", "make next"), result("a", "Next (intake): ask"),
                           turn(10, 5), turn(20, 5), tool("b", "make next"), result("b", "Next (build): code"),
                           turn(100, 50))
        phases = {p["phase"]: (p["turns"], p["tokens"]) for p in analysis["phases"]}
        self.assertEqual(phases["intake"], (3, 40))  # two turns plus the one that ran make next
        self.assertEqual(phases["build"], (1, 150))
        self.assertEqual(list(phases)[0], "start")
        self.assertIn("- build: 1 turns, 150 tokens", trial.render(SPEC, "haiku", analysis, PASSING, Path("p")))

    def test_kit_commands_not_used_are_listed(self) -> None:
        report = trial.render(SPEC, "haiku", analyse(tool("a", "make done")), PASSING, Path("p"))
        line = next(line for line in report.splitlines() if line.startswith("- Kit commands not used:"))
        self.assertIn("next", line)
        self.assertNotIn("done", line)


if __name__ == "__main__":
    unittest.main()
