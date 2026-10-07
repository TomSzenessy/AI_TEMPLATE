"""Subprocess hygiene (#39): timeouts end the whole group, children keep default SIGTERM, garden env is reduced."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kit import evals, garden, trial  # noqa: E402
from kit.core import RepoctlError  # noqa: E402


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class HeadlessTests(unittest.TestCase):
    def test_timeout_kills_the_whole_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "grandchild.pid"
            script = f"sleep 30 & echo $! > '{pidfile}'; wait"
            with self.assertRaises(subprocess.TimeoutExpired):
                evals.run_headless(["sh", "-c", script], Path(tmp), 1)
            pid = int(pidfile.read_text())
            for _ in range(20):
                if not alive(pid):
                    break
                time.sleep(0.1)
            self.assertFalse(alive(pid), "the grandchild must not outlive the timeout")

    def test_children_get_default_sigterm(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = evals.run_headless(["sh", "-c", "kill -TERM $$; echo survived"], Path(tmp), 10)
            self.assertNotIn("survived", result.stdout)
            self.assertEqual(result.returncode, -15)

    def test_success_returns_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = evals.run_headless(["sh", "-c", "echo out; echo err >&2"], Path(tmp), 10)
            self.assertEqual((result.returncode, result.stdout.strip(), result.stderr.strip()), (0, "out", "err"))

    def test_runner_survives_its_own_sigterm(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = evals.run_headless(["sh", "-c", f"kill -TERM {os.getpid()}; echo done"], Path(tmp), 10)
            self.assertIn("done", result.stdout)

    def test_unknown_task_id_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agents" / "evals").mkdir(parents=True)
            (root / ".agents" / "evals" / "s.toml").write_text('[[tasks]]\nid = "a"\nprompt = "p"\nexpect = "x"\n')
            self.assertEqual([t["id"] for t in evals.load_tasks(root, "a")], ["a"])
            with self.assertRaisesRegex(RepoctlError, "nope"):
                evals.load_tasks(root, "a,nope")


class GardenEnvironmentTests(unittest.TestCase):
    def test_surface_command_does_not_see_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = [sys.executable, "-c", "import os; print('TOKEN=' + os.environ.get('GH_TOKEN', 'absent'))"]
            with mock.patch.dict(os.environ, {"GH_TOKEN": "secret"}), \
                    mock.patch.object(garden, "load_project", return_value={}), \
                    mock.patch.object(garden, "run_checks", return_value=([], [])), \
                    mock.patch.object(garden, "surface_garden_commands", return_value=[("s", command, ".")]):
                report, _ = garden.garden_report(root)
            self.assertIn("TOKEN=absent", report)
            self.assertNotIn("secret", report)


class TrialTimeoutTests(unittest.TestCase):
    def test_report_written_when_project_state_times_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "reports"
            report_dir.mkdir()
            transcript = report_dir / "transcript.jsonl"
            transcript.write_text("")
            spec = {"id": "t", "mode": "new"}
            with mock.patch.object(trial, "project_state", side_effect=subprocess.TimeoutExpired("x", 1800)):
                code = trial.write_report(root, spec, "sonnet", transcript, root, report_dir)
            self.assertEqual(code, 0)
            self.assertIn("timed out", (report_dir / "report.md").read_text())
            self.assertTrue((report_dir / "report.json").is_file())


if __name__ == "__main__":
    unittest.main()
