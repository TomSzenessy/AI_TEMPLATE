"""Pinned upstream records (#131): validation, offline listing, injected drift check, draft-only reports."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kit import kitreport, upstream  # noqa: E402
from kit.core import RepoctlError, today  # noqa: E402
from kit.skills import load_resource_registry  # noqa: E402

SHA = "c63b8dd7dd5a5f3c32eaabe1af76d0694f863ed2"
BASE = ('id = "ref"\nkind = "skills"\nsource = "https://github.com/o/r"\ntrust = "discovery"\n'
        'access = "read-only"\nscope = "ux"\nsummary = "Use when testing."\n')


class UpstreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "owner.md").write_text("x")
        (self.root / "project.toml").write_text("schema = 1\nname = \"t\"\nkind = \"app\"\n[resources]\nregistry = \"resources.toml\"\n")

    def registry(self, extra: str = "", reviewed: str | None = None) -> None:
        reviewed = reviewed or today().isoformat()
        full = f'repo = "o/r"\nrevision = "{SHA}"\nlicense = "MIT"\nreviewed_on = "{reviewed}"\n'
        (self.root / "resources.toml").write_text(
            f"schema = 1\n[[resources]]\n{BASE}{full if extra != 'bare' else ''}{'' if extra == 'bare' else extra}")

    def load(self):
        return load_resource_registry(self.root, {"resources": {}})

    def rejects(self, extra: str, text: str, **kw) -> None:
        self.registry(extra, **kw)
        with self.assertRaisesRegex(RepoctlError, "resource registry") as caught:
            self.load()
        self.assertIn(text, "\n".join(caught.exception.findings) + str(caught.exception))

    def test_accepts_full_record_and_plain_entry(self) -> None:
        self.registry('adapted_into = ["owner.md"]\nfiles = [{ path = "a/b.md", when = "typography" }]\n')
        self.assertEqual(len(self.load()), 1)
        self.registry("bare")
        self.assertEqual(len(self.load()), 1)

    def test_rejects_bad_records(self) -> None:
        (self.root / "resources.toml").write_text(
            f'schema = 1\n[[resources]]\n{BASE}repo = "o/r"\nrevision = "abc123"\nlicense = "MIT"\nreviewed_on = "2026-01-01"\n')
        with self.assertRaises(RepoctlError) as caught:
            self.load()
        self.assertIn("40-hex", str(caught.exception.findings))
        (self.root / "resources.toml").write_text(
            f'schema = 1\n[[resources]]\n{BASE}revision = "{SHA}"\nlicense = "MIT"\nreviewed_on = "2026-01-01"\n')
        with self.assertRaises(RepoctlError) as caught:
            self.load()
        self.assertIn("repo is required", str(caught.exception.findings))
        for path in ("/abs.md", "../x.md", "a/../x.md", "a.md?x=1", "a.md#frag", "a%2e.md", "a b.md"):
            self.rejects(f'files = [{{ path = "{path}", when = "x y" }}]\n', "files path")
        self.rejects('files = [{ path = "a.md", when = "" }]\n', "when")
        self.rejects('adapted_into = ["missing.md"]\n', "adapted_into")

    def test_list_and_urls_are_offline_and_pinned(self) -> None:
        self.registry('files = [{ path = "a/b.md", when = "typography" }]\n')
        with mock.patch("subprocess.run", side_effect=AssertionError("network")):
            self.assertIn(f"o/r@{SHA[:7]}", upstream.list_lines(self.root)[0])
            lines = upstream.list_lines(self.root, "ref")
        urls = [line for line in lines if "http" in line]
        self.assertEqual(urls, [f"  when typography: https://raw.githubusercontent.com/o/r/{SHA}/a/b.md"])
        with self.assertRaises(RepoctlError):
            upstream.list_lines(self.root, "nope")

    def test_check_reports_drift_with_fake_runner(self) -> None:
        self.registry('adapted_into = ["owner.md"]\n')
        self.assertIn("current", upstream.check_lines(self.root, runner=lambda r: SHA)[0])
        behind = upstream.check_lines(self.root, runner=lambda r: "f" * 40)[0]
        self.assertIn("behind (remote fffffff", behind)
        self.assertIn("owner.md", behind)
        self.assertIn("unreachable", upstream.check_lines(self.root, runner=lambda r: None)[0])

    def test_ls_remote_failure_is_unreachable(self) -> None:
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 20)):
            self.assertIsNone(upstream.ls_remote("o/r"))

    def test_garden_review_age_is_offline(self) -> None:
        old = (today() - timedelta(days=400)).isoformat()
        self.registry(reviewed=old)
        with mock.patch("subprocess.run", side_effect=AssertionError("network")):
            self.assertEqual(len(upstream.review_age_findings(self.root, 365)), 1)
            self.assertEqual(upstream.review_age_findings(self.root, 500), [])

    def test_report_is_a_local_draft_only(self) -> None:
        self.registry()
        (self.root / "body.md").write_text("It breaks.")
        args = SimpleNamespace(upstream="ref", title='Bug "in" $(typeset)', body_file=Path("body.md"))
        with mock.patch("subprocess.run", side_effect=AssertionError("no gh/network")):
            message = kitreport.upstream_draft(self.root, args)
        drafts = list((self.root / ".agent/upstream-reports").glob("ref-*.md"))
        self.assertEqual(len(drafts), 1)
        text = drafts[0].read_text()
        self.assertIn("o/r", text)
        self.assertIn(SHA, text)
        self.assertIn("gh issue create -R o/r", text)
        self.assertIn("--title 'Bug \"in\" $(typeset)'", text, "the filing line quotes the title for the shell")
        self.assertIn("nothing was sent", message)
        self.assertIn(".agent/", (Path(__file__).resolve().parents[2] / ".gitignore").read_text())

    def test_notices_need_matching_records(self) -> None:
        self.registry()
        notices = ("## Workflow material distilled from x\n\n| a | b | c |\n| - | - | - |\n"
                   f"| [o/r](https://github.com/o/r) `{SHA[:7]}` | MIT | `x` |\n"
                   "| [p/q](https://github.com/p/q) `1234567` | MIT | `x` |\n\n## Other\n"
                   "| [z/z](https://github.com/z/z) `abcdefa` | MIT | `x` |\n")
        (self.root / "THIRD_PARTY_NOTICES.md").write_text(notices)
        findings = upstream.notice_findings(self.root)
        self.assertEqual(len(findings), 1)
        self.assertIn("p/q@1234567", findings[0])

    def test_command_and_check_are_registered(self) -> None:
        from kit.registry import Registry
        registry = Registry(Path(__file__).resolve().parents[2])
        self.assertTrue(any(c.name == "upstream" for c in registry.of("command")))
        names = {c.name for c in registry.of("check")}
        self.assertLessEqual({"upstream-notices", "upstream-review-age"}, names)


if __name__ == "__main__":
    unittest.main()
