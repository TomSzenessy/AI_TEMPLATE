"""Stale-docs: Dependabot `uses:` pin bumps are exempt; K-04 quotepath; K-13 failed read."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kit import docsync  # noqa: E402

BOT = ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")
HUMAN = ("Hu Man", "human@example.com")
WORKFLOW = ".github/workflows/x.yml"
BASE = "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v3\n      - run: echo one\n"


def git(root: Path, *args: str, author: tuple[str, str] = HUMAN) -> None:
    env = {
        "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
        "GIT_COMMITTER_NAME": author[0], "GIT_COMMITTER_EMAIL": author[1],
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(root),
    }
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


class StaleDocsDependabot(unittest.TestCase):
    def repo(self, covered: str = WORKFLOW) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q")
        git(root, "config", "commit.gpgsign", "false")
        self.write(root, WORKFLOW, BASE)
        self.write(root, "src/é.py", "x = 1\n")
        self.write(root, "docs/d.md", f"# D\n<!-- covers: {covered} -->\n")
        self.commit(root, "init")
        return root

    def write(self, root: Path, path: str, text: str) -> None:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def commit(self, root: Path, message: str, author: tuple[str, str] = HUMAN) -> None:
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", message, author=author)

    def stale(self, root: Path, covered: str = WORKFLOW) -> list[str]:
        return docsync.stale_documents(root, {"docs/d.md": [covered]})

    def test_bot_uses_bump_is_not_stale(self):
        root = self.repo()
        self.write(root, WORKFLOW, BASE.replace("checkout@v3", "checkout@v4"))
        self.commit(root, "bump", BOT)
        self.assertEqual(self.stale(root), [])

    def test_human_uses_bump_is_stale(self):
        root = self.repo()
        self.write(root, WORKFLOW, BASE.replace("checkout@v3", "checkout@v4"))
        self.commit(root, "bump")
        self.assertEqual(len(self.stale(root)), 1)

    def test_bot_commit_also_changing_run_is_stale(self):
        root = self.repo()
        self.write(root, WORKFLOW, BASE.replace("checkout@v3", "checkout@v4").replace("echo one", "echo two"))
        self.commit(root, "bump", BOT)
        self.assertEqual(len(self.stale(root)), 1)

    def test_non_ascii_path_is_matched(self):
        root = self.repo("src/**")
        self.write(root, "src/é.py", "x = 2\n")
        self.commit(root, "edit")
        findings = self.stale(root, "src/**")
        self.assertEqual(len(findings), 1)
        self.assertIn("é.py", findings[0])

    def test_failed_history_read_is_not_empty_history(self):
        root = self.repo()
        self.assertEqual(docsync.history_read(Path(tempfile.gettempdir()) / "no-such-repo-dir"), None)
        with mock.patch.object(docsync, "git", return_value=None):
            self.assertIsNone(docsync.history_read(root))
        with mock.patch.object(docsync, "git", return_value=""):
            self.assertEqual(docsync.history_read(root), [])

    def test_pin_only_diff(self):
        self.assertTrue(docsync.pin_only_diff("@@ -1 +1 @@\n-      - uses: a/b@1\n+      - uses: a/b@2 # v2\n"))
        self.assertFalse(docsync.pin_only_diff("@@\n-  run: a\n+  run: b\n"))
        self.assertFalse(docsync.pin_only_diff(""))


if __name__ == "__main__":
    unittest.main()
