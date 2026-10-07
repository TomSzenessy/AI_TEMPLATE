"""A project plugin that fails to import never disables the kit or the commit gate (#28)."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from kit.registry import Registry, run_checks  # noqa: E402
from kit import session  # noqa: E402

REPOCTL = TOOLS / "repoctl.py"
HOOK = TOOLS.parent / ".githooks" / "commit-msg"
MANIFEST = 'schema = 1\nname = "Demo"\nkind = "template"\nphase = "bootstrap"\nlicense = "UNSELECTED"\nowners = []\n' \
           '[governance]\nprofile = "regulated"\n'
GOOD_COMMAND = (
    "from kit.registry import command\n\n"
    '@command("hello-plugin", "Say hello from a project plugin; for the isolation tests", make=None)\n'
    "def hello(root, args):\n    print('hello from plugin')\n"
)


class PluginIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.write("project.toml", MANIFEST)
        self.write("docs/README.md", "# Docs\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, name: str, content: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def cli(self, *args: str):
        return subprocess.run([sys.executable, str(REPOCTL), "--root", str(self.root), *args],
                              capture_output=True, text=True, check=False)

    def break_plugin(self) -> None:
        self.write(".agents/commands/bad.py", "raise ValueError('x')\n")

    def test_kit_commands_survive_a_broken_plugin(self) -> None:
        self.break_plugin()
        self.assertEqual(self.cli("help").returncode, 0)
        made = self.cli("new", "--kind", "doc", "--name", "notes", "--desc", "Notes for isolation; read when testing")
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(self.cli("sync").returncode, 0, self.cli("sync").stderr)

    def test_check_reports_plugin_load_and_fails(self) -> None:
        self.break_plugin()
        result = self.cli("check")
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("[plugin-load] .agents/commands/bad.py:", output)
        self.assertIn("ValueError: x", output)

    def test_other_plugins_still_load(self) -> None:
        self.break_plugin()
        self.write(".agents/commands/good.py", GOOD_COMMAND)
        result = self.cli("hello-plugin")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "hello from plugin"), result.stderr)

    def test_valid_plugin_loads_and_check_has_no_plugin_finding(self) -> None:
        self.write(".agents/commands/good.py", GOOD_COMMAND)
        self.assertEqual(self.cli("hello-plugin").stdout.strip(), "hello from plugin")
        hard, advisory = run_checks(self.root, blocking_only=False)
        self.assertFalse([item for item in hard + advisory if "[plugin-load]" in item])

    def test_dataclass_plugin_loads(self) -> None:
        self.write(".agents/commands/data.py", "from __future__ import annotations\n"
                   "from dataclasses import dataclass\nfrom kit.registry import command\n\n"
                   "@dataclass\nclass Row:\n    name: str\n\n"
                   '@command("data-plugin", "A plugin that declares a dataclass; for loader tests", make=None)\n'
                   "def run(root, args):\n    print(Row('ok').name)\n")
        result = self.cli("data-plugin")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "ok"), result.stderr)
        self.assertEqual(Registry(self.root).plugin_errors, [])

    def test_plugin_importing_a_kit_check_registers_it_once(self) -> None:
        self.write(".agents/checks/reuse.py", "from kit.checks import final_newline\nfrom kit.registry import check\n\n"
                   '@check("reuse-newline", "Reuse of a kit check inside a plugin; for loader tests", blocks=False)\n'
                   "def reuse(context):\n    return final_newline(context)\n")
        registry = Registry(self.root)
        self.assertEqual(registry.plugin_errors, [])
        names = [item.name for item in registry.of("check", enabled_only=False)]
        self.assertEqual(names.count("final-newline"), 1)
        self.assertEqual(names.count("reuse-newline"), 1)

    def test_session_brief_lists_plugin_files(self) -> None:
        self.write(".agents/commands/good.py", GOOD_COMMAND)
        self.break_plugin()
        out = io.StringIO()
        with redirect_stdout(out):
            session.session_start(self.root)
        brief = out.getvalue()
        self.assertIn(".agents/commands/good.py", brief)
        self.assertIn(".agents/commands/bad.py", brief)


class PluginCommitGateTests(unittest.TestCase):
    """The installed git hook, in a temp repository carrying a copy of the kit."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        shutil.copytree(TOOLS, self.root / "tools", ignore=shutil.ignore_patterns("__pycache__", "tests"))
        (self.root / ".githooks").mkdir()
        shutil.copy(HOOK, self.root / ".githooks" / "commit-msg")
        (self.root / "project.toml").write_text(MANIFEST, encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "README.md").write_text("# Docs\n", encoding="utf-8")
        for args in (("init", "-q"), ("config", "user.email", "t@example.com"), ("config", "user.name", "T"),
                     ("config", "commit.gpgsign", "false"), ("config", "core.hooksPath", ".githooks")):
            self.git(*args)
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "base")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str):
        env = {**os.environ, "REPOCTL_PYTHON": sys.executable}
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=False, env=env)

    def stage_change(self) -> None:
        (self.root / "notes.txt").write_text("hello\n", encoding="utf-8")
        self.git("add", "notes.txt")

    def test_commit_is_blocked_and_names_the_plugin(self) -> None:
        (self.root / ".agents/commands").mkdir(parents=True)
        (self.root / ".agents/commands/bad.py").write_text("raise ValueError('x')\n", encoding="utf-8")
        self.stage_change()
        result = self.git("commit", "-q", "-m", "change")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(".agents/commands/bad.py", result.stderr)
        self.assertNotIn("skipped", result.stderr)

    def test_commit_passes_with_a_valid_plugin(self) -> None:
        (self.root / ".agents/commands").mkdir(parents=True)
        (self.root / ".agents/commands/good.py").write_text(GOOD_COMMAND, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "plugin")
        self.stage_change()
        result = self.git("commit", "-q", "-m", "change")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unloadable_registry_blocks_and_missing_python_warns(self) -> None:
        (self.root / "tools/kit/commands.py").write_text("raise RuntimeError('kit broken')\n", encoding="utf-8")
        self.stage_change()
        result = self.git("commit", "-q", "-m", "change")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("skipped", result.stderr)
        (self.root / "tools/kit/commands.py").unlink()
        broken = self.git("-c", "core.hooksPath=.githooks", "commit", "-q", "-m", "change")
        self.assertNotEqual(broken.returncode, 0)

    def test_missing_interpreter_is_a_loud_skip(self) -> None:
        self.stage_change()
        env = {**os.environ, "REPOCTL_PYTHON": "/nonexistent/python"}
        result = subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "change"],
                                capture_output=True, text=True, check=False, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARNING: commit gate NOT RUN", result.stderr)


if __name__ == "__main__":
    unittest.main()
