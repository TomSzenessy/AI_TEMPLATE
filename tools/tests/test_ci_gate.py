"""kit-ci runs the interpreter the matrix configured (#66) and only toolchain-free gates in adopted projects (#67)."""
import ast
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import Scratch, template_only  # noqa: E402

from kit import ci  # noqa: E402
from kit.core import RepoctlError  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SHOW = "include Makefile\nshow:\n\t@echo '[$(PYTHON)]'\n"


@template_only  # it reads the template's own Makefile and workflow
class PythonSelectionTests(unittest.TestCase):
    """The Makefile picks the environment's python3 when it meets the 3.11 floor, else the newest one that does."""

    def setUp(self) -> None:
        if not shutil.which("make"):
            self.skipTest("make not installed")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.bin = Path(tmp.name) / "stubs"
        self.bin.mkdir()
        self.tools = Path(tmp.name) / "tools"  # the only real executables on PATH: no host python3.N can leak in
        self.tools.mkdir()
        for name in ("make", "dirname", "sh", "echo"):
            (self.tools / name).symlink_to(shutil.which(name))

    def interpreter(self, name: str, meets_floor: bool) -> None:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n[ \"$1\" = -c ] && exit {0 if meets_floor else 1}\nexit 0\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def selected(self, **env: str) -> str:
        search = os.pathsep.join([str(self.bin), str(self.tools)])
        full = {k: v for k, v in os.environ.items() if k not in {"MAKEFLAGS", "MFLAGS", "PYTHON"}}
        full.update(PATH=search, **env)
        done = subprocess.run(["make", "--no-print-directory", "-s", "-f", "-", "show"], input=SHOW, cwd=ROOT,
                              env=full, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()[1:-1]

    def test_the_configured_python3_wins_over_a_newer_one(self) -> None:
        self.interpreter("python3", True)  # what setup-python 3.11 puts first
        self.interpreter("python3.12", True)
        self.interpreter("python3.14", True)
        self.assertEqual(self.selected(), "python3")

    def test_an_old_python3_falls_back_to_the_newest_that_meets_the_floor(self) -> None:
        self.interpreter("python3", False)
        self.interpreter("python3.11", True)
        self.interpreter("python3.13", True)
        self.assertEqual(self.selected(), "python3.13")

    def test_an_explicit_python_is_honoured(self) -> None:
        self.interpreter("python3", True)
        self.assertEqual(self.selected(PYTHON="/opt/py/bin/python3.12"), "/opt/py/bin/python3.12")

    def test_nothing_meeting_the_floor_selects_nothing_so_python_check_fails(self) -> None:
        self.interpreter("python3", False)
        self.assertEqual(self.selected(), "")

    def test_the_launcher_applies_the_same_rule(self) -> None:
        self.interpreter("python3", True)
        self.interpreter("python3.14", True)
        for name in ("python3", "python3.14"):
            (self.bin / name).write_text(f"#!/bin/sh\n[ \"$1\" = -c ] && exit 0\necho {name}\n")
        done = subprocess.run(["/bin/sh", str(ROOT / "tools/repoctl"), "x"], env={"PATH": f"{self.bin}{os.pathsep}{self.tools}"},
                              capture_output=True, text=True)
        self.assertEqual(done.stdout.split()[0], "python3")

    def test_the_gate_workflow_runs_on_the_matrix_interpreter(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tools/repoctl.py --root . ci gate", workflow)
        self.assertIn('python: ["3.11", "3.x"]', workflow)


class FloorTests(unittest.TestCase):
    """Failure case: code that needs a newer Python than the 3.11 floor must fail the floor job."""

    def test_syntax_newer_than_the_floor_is_rejected_when_checked_against_it(self) -> None:
        with self.assertRaises(SyntaxError):
            ast.parse("def first[T](items: list[T]) -> T:\n    return items[0]\n", feature_version=(3, 11))

    def test_the_kit_sources_parse_at_the_floor(self) -> None:
        for path in sorted((ROOT / "tools").rglob("*.py")):
            if "clockshift" in path.parts:
                continue
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 11))


class GateTests(Scratch):
    def project(self, mode: str | None) -> None:
        line = f'project_mode = "{mode}"\n' if mode else ""
        self.write("project.toml", f'schema = 1\nname = "demo"\nkind = "web"\n[kit]\n{line}')

    def test_adopted_projects_run_only_the_toolchain_free_check(self) -> None:
        self.project("adopt")
        command = ci.gate_command(self.root, "/py/python3")
        self.assertEqual(command[0], "/py/python3")
        self.assertEqual(command[-1], "check")
        self.assertNotIn("verify", command)
        self.assertNotIn("make", command)

    def test_the_template_and_new_projects_run_the_full_verification(self) -> None:
        for mode in (None, "new"):
            self.project(mode)
            self.assertEqual(ci.gate_command(self.root, "/py/python3"),
                             ["make", "--no-print-directory", "PYTHON=/py/python3", "verify"])

    def test_a_failing_gate_fails_the_job_and_a_passing_one_does_not(self) -> None:
        self.project("adopt")
        with mock.patch.object(ci.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertIn("passed", ci.run_gate(self.root))
            self.assertEqual(run.call_args.kwargs["cwd"], self.root)
        with mock.patch.object(ci.subprocess, "run", return_value=subprocess.CompletedProcess([], 127)):
            with self.assertRaisesRegex(RepoctlError, "exit 127"):
                ci.run_gate(self.root)

    def test_the_adopted_check_never_needs_a_surface_toolchain(self) -> None:
        self.project("adopt")
        with mock.patch.object(ci.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            ci.run_gate(self.root)
        self.assertNotIn("npm", " ".join(run.call_args.args[0]))


if __name__ == "__main__":
    unittest.main()
