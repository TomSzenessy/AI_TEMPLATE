"""#98: authorized technical recon routing and a real owned-fixture trial."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents/skills/technical-recon"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import template_only  # noqa: E402
from kit import adapters, skills  # noqa: E402


class TrialTests(unittest.TestCase):
    def trial(self):
        spec = importlib.util.spec_from_file_location("technical_recon_trial", SKILL / "examples/trial.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_without_explicit_owned_fixture_scope_nothing_executes(self):
        runner = Mock()
        report = self.trial().run_trial(approved=False, runner=runner)
        self.assertFalse(report["verified"])
        self.assertEqual(report["status"], "scope-required")
        runner.assert_not_called()

    def test_actual_fixture_held_out_agent_and_replay_match(self):
        report = self.trial().run_trial(approved=True)
        self.assertTrue(report["verified"], report)
        self.assertEqual(report["evidence_type"], "synthetic")
        self.assertEqual(report["mismatches"], [])
        self.assertGreater(report["held_out_cases"], 1)
        self.assertGreater(report["agent_actions"], 1)
        self.assertTrue(report["replay_equal"])
        self.assertEqual(len(report["target_digest"]), 64)
        self.assertIn("not real-target parity", report["limitations"])
        self.assertEqual(len(report["traces"]), 4)
        comparison = report["agent_comparison"]
        self.assertTrue(comparison["actions_equal"])
        self.assertTrue(comparison["outputs_equal"])
        self.assertEqual(comparison["observed"], comparison["predicted"])
        self.assertEqual(len(comparison["observed"]["actions"]), 4)

    def test_observation_drift_changes_independently_reacting_agent_actions(self):
        report = self.trial().run_trial(approved=True, inject_observation_drift=True)
        self.assertFalse(report["verified"], report)
        self.assertEqual(report["status"], "compared")
        self.assertIn("held-out-agent-actions", report["mismatches"])
        comparison = report["agent_comparison"]
        self.assertFalse(comparison["actions_equal"])
        self.assertFalse(comparison["outputs_equal"])
        self.assertEqual(comparison["observed"]["actions"], [
            {"op": "reserve", "amount": 6}, {"op": "release", "amount": 6},
            {"op": "reserve", "amount": 6}, {"op": "release", "amount": 6},
        ])
        self.assertEqual(comparison["predicted"]["actions"], [
            {"op": "reserve", "amount": 6}, {"op": "reserve", "amount": 1},
            {"op": "reserve", "amount": 1}, {"op": "reserve", "amount": 1},
        ])
        self.assertEqual(comparison["observed"]["trace"][0]["observation"]["available"], 0)
        self.assertEqual(comparison["predicted"]["trace"][0]["observation"]["available"], 1)
        self.assertEqual(comparison["predicted"]["trace"][1]["result"], "rejected")
        self.assertNotIn("held-out-agent", [trace["case"] for trace in report["traces"]])

    def test_deliberately_wrong_model_is_detected(self):
        report = self.trial().run_trial(approved=True, inject_drift=True)
        self.assertFalse(report["verified"], report)
        self.assertTrue(report["mismatches"])

    def test_timeout_is_unknown_not_verified(self):
        runner = Mock(side_effect=subprocess.TimeoutExpired(["owned-fixture"], 0.1))
        report = self.trial().run_trial(approved=True, runner=runner)
        self.assertFalse(report["verified"])
        self.assertEqual(report["status"], "unknown")

    def test_malformed_output_is_not_parity_evidence(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "not JSON", ""))
        report = self.trial().run_trial(approved=True, runner=runner)
        self.assertFalse(report["verified"])
        self.assertEqual(report["status"], "unknown")

    def test_cli_requires_scope_and_emits_actual_report(self):
        command = [sys.executable, str(SKILL / "examples/trial.py")]
        denied = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(json.loads(denied.stdout)["status"], "scope-required")
        allowed = subprocess.run(command + ["--run-owned-fixture"], capture_output=True, text=True, timeout=5)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertTrue(json.loads(allowed.stdout)["verified"])
        for control in ("--inject-drift", "--inject-observation-drift"):
            with self.subTest(control=control):
                wrong = subprocess.run(command + ["--run-owned-fixture", control],
                                       capture_output=True, text=True, timeout=5)
                self.assertEqual(wrong.returncode, 1, wrong.stdout + wrong.stderr)
                report = json.loads(wrong.stdout)
                self.assertFalse(report["verified"])
                self.assertEqual(report["status"], "compared")
                self.assertTrue(report["mismatches"])
                if control == "--inject-observation-drift":
                    self.assertFalse(report["agent_comparison"]["actions_equal"])


@template_only
class RoutingTests(unittest.TestCase):
    def test_skill_is_registered_and_has_a_generated_redirect(self):
        from kit.core import load_project
        self.assertIn("technical-recon", load_project(ROOT)["capabilities"]["local_skills"])
        redirect = adapters.render_claude(ROOT)[".claude/skills/technical-recon/SKILL.md"]
        self.assertIn(".agents/skills/technical-recon/SKILL.md", redirect)
        self.assertNotIn("FILL-IN:", (SKILL / "SKILL.md").read_text())

    def test_rea_is_pinned_read_only_candidate_not_enabled_mcp(self):
        entries = skills.load_resource_registry(ROOT)
        rea = next(entry for entry in entries if entry["id"] == "rea-authorized-analysis")
        self.assertIn("79156e5bed1d72b83ade0483246f457b337b7e59", rea["source"])
        self.assertEqual(rea["access"], "read-only")
        self.assertEqual(rea["trust"], "discovery")
        self.assertNotIn("mcp", rea)


if __name__ == "__main__":
    unittest.main()
