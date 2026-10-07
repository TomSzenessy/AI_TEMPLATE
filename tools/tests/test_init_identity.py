"""`repoctl init` takes the template's identity from project.toml, not from literals (#42)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORDS = ("project.toml", "VISION.md", "docs/STACK-DECISION.md", "README.md")

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import Scratch, git_in, run_cli, template_only  # noqa: E402  shared builders, in-process CLI, isolated git (#43)


def run_init(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return run_cli(root, "init", "--name", "x", "--kind", "web", *extra)


class InitIdentityTests(Scratch):
    def copy_working_tree(self) -> Path:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        files = git_in(ROOT, "ls-files", "-z").stdout.split("\0")
        for relative in filter(None, files):
            source = ROOT / relative
            if source.is_file():
                (directory / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, directory / relative)
        git_in(directory, "init", "-q")
        return directory

    def rename(self, root: Path, name: str, owner: str) -> None:
        for relative in RECORDS:
            path = root / relative
            text = path.read_text(encoding="utf-8")
            text = text.replace("AI_TEMPLATE", name).replace("TomSzenessy", owner)
            path.write_text(text, encoding="utf-8")

    def test_renamed_fork_resets_vision_stack_and_owner(self) -> None:
        root = self.copy_working_tree()
        self.rename(root, "my-fork", "someone")
        manifest = (root / "project.toml").read_text(encoding="utf-8")
        self.assertIn('name = "my-fork"', manifest)
        self.assertIn('owner = "someone"', manifest)
        result = run_init(root, "--owner", "carol")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for record in ("VISION.md", "docs/STACK-DECISION.md"):
            text = (root / record).read_text(encoding="utf-8")
            self.assertIn("Status: pending", text, record)
            self.assertIn("Project: x", text, record)
            self.assertNotIn("my-fork", text, record)
        manifest = (root / "project.toml").read_text(encoding="utf-8")
        self.assertNotIn('owner = "someone"', manifest)
        self.assertIn('owners = ["carol"]', manifest)
        self.assertNotRegex(manifest, r'(?m)^owner = "(?!carol)')
        self.assertEqual(re.search(r"(?m)^# (.+)$", (root / "README.md").read_text(encoding="utf-8")).group(1), "x")

    def test_a_project_that_is_not_a_template_is_not_reinitialized(self) -> None:
        root = self.copy_working_tree()
        path = root / "project.toml"
        path.write_text(path.read_text(encoding="utf-8").replace('kind = "template"', 'kind = "web"', 1), encoding="utf-8")
        result = run_init(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already initialized", result.stdout + result.stderr)

    @template_only  # it runs the previous release's bootstrap from the template's history
    def test_unmodified_template_initializes_as_the_previous_release_did(self) -> None:
        root = self.copy_working_tree()
        baseline = self.copy_working_tree()  # identical, except it runs the previous release's bootstrap
        previous = subprocess.run(["git", "show", "HEAD:tools/kit/bootstrap.py"], cwd=ROOT,
                                  capture_output=True, text=True, check=True).stdout
        (baseline / "tools/kit/bootstrap.py").write_text(previous, encoding="utf-8")
        self.assertEqual(run_init(root, "--owner", "carol").returncode, 0)
        self.assertEqual(run_init(baseline, "--owner", "carol").returncode, 0)
        for record in RECORDS:
            self.assertEqual((root / record).read_text(encoding="utf-8"),
                             (baseline / record).read_text(encoding="utf-8"), record)

    def test_bootstrap_names_no_template_literal(self) -> None:
        source = (ROOT / "tools/kit/bootstrap.py").read_text(encoding="utf-8")
        for literal in ("AI_TEMPLATE", "TomSzenessy"):
            self.assertNotIn(literal, source)


if __name__ == "__main__":
    unittest.main()
