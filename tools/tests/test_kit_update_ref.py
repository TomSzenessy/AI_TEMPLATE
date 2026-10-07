"""`make kit-update KIT_REF=<sha>`: update to a pinned template commit, not the moving HEAD (#41)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import Scratch, git_in, run_cli, template_only  # noqa: E402  shared builders, in-process CLI, isolated git (#43)


def git(where: Path, *args: str) -> str:
    return git_in(where, *args).stdout


@template_only
class KitRefTests(Scratch):
    def build(self, temp: str) -> tuple[Path, Path, str, str]:
        """A local template with commits A then B, and a project made from A whose [template].source is it."""
        from kit import core, trial
        kit, project = Path(temp) / "kit", Path(temp) / "project"
        trial._copy(TOOLS.parent, core.repository_files(TOOLS.parent), kit)
        git(kit, "init", "-q", "-b", "main")
        git(kit, "add", "-A")
        git(kit, "commit", "-qm", "A")
        first = git(kit, "rev-parse", "HEAD").strip()
        trial.prepare(kit, {"id": "demo", "kind": "cli", "mode": "new", "prompt": "x"}, project)
        manifest = project / "project.toml"
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(text + f'\n[template]\nsource = "{kit}"\n' if "[template]" not in text
                            else text.replace('source = "https://github.com/TomSzenessy/AI_TEMPLATE"', f'source = "{kit}"'),
                            encoding="utf-8")
        lock = project / "tools/kit-lock.json"  # the project was made from commit A
        data = json.loads(lock.read_text())
        data["kit_version"] = first
        lock.write_text(json.dumps(data, indent=1) + "\n")
        git(project, "add", "-A")
        git(project, "commit", "-qm", "snapshot")
        navigate = kit / "tools/kit/navigate.py"
        navigate.write_text(navigate.read_text() + "\n# change in B\n")
        git(kit, "commit", "-qam", "B")
        second = git(kit, "rev-parse", "HEAD").strip()
        navigate.write_text(navigate.read_text() + "\n# change in C\n")
        git(kit, "commit", "-qam", "C")
        return kit, project, first, second

    def run_update(self, project: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return run_cli(project, "kit-update", *args)

    def test_pinned_ref_applies_that_commit_and_prints_the_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            kit, project, first, second = self.build(temp)
            result = self.run_update(project, "--ref", second)
            self.assertEqual(result.returncode, 0, result.stderr)
            content = (project / "tools/kit/navigate.py").read_text()
            self.assertIn("# change in B", content)
            self.assertNotIn("# change in C", content, "the pinned commit is applied, not HEAD")
            self.assertEqual(json.loads((project / "tools/kit-lock.json").read_text())["kit_version"], second)
            self.assertIn(f"{first[:12]}..{second[:12]}", result.stdout)

    def test_unknown_ref_fails_clearly_and_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            kit, project, first, _ = self.build(temp)
            result = self.run_update(project, "--ref", "0" * 40)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("KIT_REF", result.stderr)
            self.assertNotIn("# change in", (project / "tools/kit/navigate.py").read_text())
            self.assertEqual(json.loads((project / "tools/kit-lock.json").read_text())["kit_version"], first)

    def test_ref_with_a_checkout_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            kit, project, _, second = self.build(temp)
            result = self.run_update(project, "--kit", str(kit), "--ref", second)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("KIT_REF", result.stderr)


if __name__ == "__main__":
    unittest.main()
