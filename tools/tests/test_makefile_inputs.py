"""Make inputs (#32): command-line values reach repoctl intact, and nothing else does.

Runs the real Makefile with PYTHON pointing at a stub that records argv, so no real repoctl runs.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUB = """#!/usr/bin/env python3
import json, sys
if sys.argv[1:2] == ["-c"]:
    sys.exit(0)
print("ARGV" + json.dumps(sys.argv[1:]))
"""


class MakeInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("make"):
            raise unittest.SkipTest("make not installed")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stub = Path(cls.tmp.name) / "stub-python"
        cls.stub.write_text(STUB)
        cls.stub.chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def make(self, *args, env=None, makefile=None, cwd=ROOT):
        full = {k: v for k, v in os.environ.items() if k not in {"MAKEFLAGS", "MFLAGS"}}
        full.update(env or {})
        cmd = ["make", "--no-print-directory", f"PYTHON={self.stub}"]
        if makefile:
            cmd += ["-f", str(makefile)]
        return subprocess.run([*cmd, *args], cwd=cwd, env=full, capture_output=True, text=True)

    def argv(self, *args, env=None, **kwargs):
        done = self.make(*args, env=env, **kwargs)
        self.assertEqual(done.returncode, 0, done.stderr)
        line = next(item for item in done.stdout.splitlines() if item.startswith("ARGV"))
        return json.loads(line[4:])

    def test_c11_ambient_environment_is_not_a_flag(self):
        argv = self.argv("new", "KIND=doc", "NAME=a", "DESC=b", env={"GROUP": "staff", "TIER": "x", "FORCE": "1"})
        self.assertNotIn("--group", argv)
        self.assertNotIn("--tier", argv)
        self.assertNotIn("--force", argv)
        issue = self.argv("issue", "TITLE=t", env={"STATUS": "zzz", "TYPE": "bug", "GROUP": "staff"})
        self.assertEqual(issue, ["tools/repoctl.py", "issue", "--title", "t"])

    def test_c11_ambient_value_does_not_satisfy_required(self):
        done = self.make("where", env={"Q": "ambient"})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Add what to look for", done.stderr)

    def test_c11_command_line_values_pass_through(self):
        argv = self.argv("new", "KIND=doc", "NAME=a", "DESC=b c", "GROUP=staff", "FORCE=yes", env={"GROUP": "ambient"})
        self.assertEqual(argv[argv.index("--group") + 1], "staff")
        self.assertEqual(argv[argv.index("--description") + 1], "b c")
        self.assertIn("--force", argv)

    def test_c12_dollar_is_data(self):
        for value in ("costs $5", "$(HOME) and $$x ${PATH}"):
            argv = self.argv("issue", f"TITLE={value}")
            self.assertEqual(argv[argv.index("--title") + 1], value)

    def test_values_are_data_never_shell_source(self):
        marker = Path(self.tmp.name) / "pwned"
        value = f"`touch {marker}` $(touch {marker}) '; touch {marker}; '\" quote"
        argv = self.argv("issue", f"TITLE={value}")
        self.assertEqual(argv[argv.index("--title") + 1], value)
        self.assertFalse(marker.exists())

    def test_c22_dash_values_are_positional(self):
        self.assertEqual(self.argv("where", "Q=-x"), ["tools/repoctl.py", "where", "--", "-x"])
        self.assertEqual(self.argv("similar", "Q=--help")[-2:], ["--", "--help"])
        self.assertEqual(self.argv("skill-digest", "SKILL_PATH=-p")[-2:], ["--", "-p"])
        trial = self.argv("trial", "NAME=-n", "MODEL=m")
        self.assertEqual(trial[trial.index("--") + 1], "-n")
        self.assertLess(trial.index("--model"), trial.index("--"))

    def test_c22_real_repoctl_searches_a_dash_value(self):
        done = subprocess.run(["python3", "tools/repoctl.py", "where", "--", "-x"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotIn("required", done.stderr)
        self.assertNotIn("usage", done.stderr)

    def test_c27_recursive_make_prints_no_directory_noise(self):
        text = (ROOT / "Makefile").read_text()
        for line in text.splitlines():
            if "$(MAKE)" in line and not line.lstrip().startswith("#"):
                self.assertIn("--no-print-directory", line)

    def adopt_kit(self, name):
        kit = Path(self.tmp.name) / name
        (kit / "tools").mkdir(parents=True)
        shutil.copy(ROOT / "Makefile", kit / "Makefile")
        (kit / "tools" / "repoctl.py").write_text("")
        return kit

    def test_c01_kit_path_with_spaces(self):
        kit = self.adopt_kit("kit with spaces/AI TEMPLATE")
        project = Path(self.tmp.name) / "project"
        project.mkdir(exist_ok=True)
        argv = self.argv("adopt", "NAME=x", "KIND=web", makefile=kit / "Makefile", cwd=project)
        self.assertEqual(argv[0], str(kit / "tools" / "repoctl.py"))
        self.assertEqual(argv[argv.index("--from") + 1], str(kit))

    def test_c01_override_and_fail_fast(self):
        kit = self.adopt_kit("override kit")
        project = Path(self.tmp.name) / "project2"
        project.mkdir(exist_ok=True)
        argv = self.argv("adopt", "NAME=x", "KIND=web", f"KIT_DIR={kit}", makefile=kit / "Makefile", cwd=project)
        self.assertEqual(argv[argv.index("--from") + 1], str(kit))
        done = self.make("adopt", "NAME=x", "KIND=web", f"KIT_DIR={project}", makefile=kit / "Makefile", cwd=project)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("KIT_DIR", done.stderr)

    def test_help_still_works(self):
        self.assertEqual(self.argv("help"), ["tools/repoctl.py", "help"])


if __name__ == "__main__":
    unittest.main()
