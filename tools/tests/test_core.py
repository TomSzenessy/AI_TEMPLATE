"""Table-driven unit tests for the core safety helpers (#33).

Token-shaped strings are built at runtime so this file never trips the
repository's own sensitive-content scan.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kit import core  # noqa: E402
from kit.core import RepoctlError  # noqa: E402

A20 = "a" * 20
DASH = "-" * 5


class SecretMatchTests(unittest.TestCase):
    def test_every_pattern_has_a_positive_and_a_near_miss(self) -> None:
        pem = lambda kind: f"{DASH}BEGIN {kind}{DASH}\nabc\n{DASH}END {kind}{DASH}"
        table = [
            ("private key", pem("RSA PRIVATE KEY"), pem("RSA PUBLIC KEY")),
            ("private key", pem("PGP PRIVATE KEY BLOCK"), f"{DASH}BEGIN RSA PRIVATE KEY{DASH}\nno end marker"),
            ("GitHub token", "gh" + "p_" + A20, "gh" + "p_" + "a" * 19),
            ("GitHub token", "github" + "_pat_" + A20, "xgh" + "p_" + A20),
            ("AWS access key", "AK" + "IA" + "A" * 16, "AK" + "IA" + "A" * 15),
            ("authorization credential", "Authorization" + ": Bearer " + "tok123", "Authorization" + ": tok123"),
            ("credential assignment", "api_key" + " = " + "x" * 12, "api_key" + " = " + "x" * 11),
            ("credential assignment", "password" + ": " + "y" * 12, "passwords are" + " rotated"),
        ]
        for label, positive, negative in table:
            with self.subTest(label=label, case=positive[:12]):
                self.assertIn(label, core.secret_matches(positive))
                self.assertNotIn(label, core.secret_matches(negative))

    def test_all_five_patterns_are_covered_by_the_table(self) -> None:
        self.assertEqual(len(core.SENSITIVE_CONTENT_PATTERNS), 5)
        self.assertEqual(core.secret_matches("plain prose, nothing secret"), [])

    def test_reject_secret_text_names_the_label(self) -> None:
        with self.assertRaises(RepoctlError) as caught:
            core.reject_secret_text("gh" + "p_" + A20, "title")
        self.assertIn("title", str(caught.exception))
        core.reject_secret_text("fine", "title")


class PathHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve() / "repo"
        (self.root / "real").mkdir(parents=True)
        (self.root / "real/file.txt").write_text("x")
        self.outside = Path(self._tmp.name).resolve() / "outside"
        self.outside.mkdir()

    def link(self, name: str, target: Path) -> Path:
        path = self.root / name
        try:
            os.symlink(target, path)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        return path

    def test_ensure_inside_root_table(self) -> None:
        ok = [self.root / "real/file.txt", self.root / "real/../real/file.txt", self.root]
        for path in ok:
            with self.subTest(path=str(path)):
                self.assertEqual(core.ensure_inside_root(self.root, path, "p"), Path(os.path.normpath(path)))
        bad = [
            self.root / ".." / "outside",
            self.root / "real/../../outside",
            Path("/etc/passwd"),
            self.outside / "f",
        ]
        for path in bad:
            with self.subTest(path=str(path)):
                with self.assertRaisesRegex(RepoctlError, "inside the repository"):
                    core.ensure_inside_root(self.root, path, "p")

    def test_symlink_escaping_the_root_is_refused(self) -> None:
        escape = self.link("escape", self.outside)
        with self.assertRaisesRegex(RepoctlError, "symlinks"):
            core.ensure_inside_root(self.root, escape / "f", "p")
        with self.assertRaisesRegex(RepoctlError, "symlinks"):
            core.ensure_inside_root(self.root, escape, "p")

    def test_has_link_component(self) -> None:
        inside = self.link("alias", self.root / "real")
        table = [
            (self.root / "real/file.txt", False),
            (self.root / "missing/file.txt", False),
            (inside, True),
            (inside / "file.txt", True),
            (self.outside / "x", False),  # not under the root: nothing to traverse
        ]
        for path, expected in table:
            with self.subTest(path=str(path)):
                self.assertIs(core.has_link_component(self.root, path), expected)

    def test_normalized_relative_path_table(self) -> None:
        good = [("./a", "a"), ("a/", "a"), ("a/b/", "a/b"), ("a/./b", "a/b"), (".", ".")]
        for value, expected in good:
            with self.subTest(value=value):
                self.assertEqual(core.normalized_relative_path(value, "path"), expected)
        bad = ["", "   ", "../x", "a/../../x", "a/..", "/abs", "C:\\x", "a\\b", None, 3]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(RepoctlError):
                    core.normalized_relative_path(value, "path")


class TextHelperTests(unittest.TestCase):
    def test_markdown_link_target_table(self) -> None:
        table = [
            ("a.md", "a.md"),
            ("  a.md  ", "a.md"),
            ('a.md "Title"', "a.md"),
            ("<a b.md>", "a b.md"),
            ("<a b.md> 'T'", "a b.md"),
            ("#anchor", "#anchor"),
        ]
        for raw, expected in table:
            with self.subTest(raw=raw):
                self.assertEqual(core.markdown_link_target(raw), expected)

    def test_safe_markdown_text_escapes_and_collapses(self) -> None:
        table = [
            ("plain", "plain"),
            ("a  b\n c", "a b c"),
            ("*x* `y`", r"\*x\* \`y\`"),
            ("[l](u)", r"\[l\]\(u\)"),
            ("# h | t > q", r"\# h \| t \> q"),
            ("a\\b", "a\\\\b"),
        ]
        for value, expected in table:
            with self.subTest(value=value):
                self.assertEqual(core.safe_markdown_text(value), expected)

    def test_is_placeholder_table(self) -> None:
        yes = ["", "  ", None, 3, "[X]", "[REQUIRED: owner]", "TBD", " pending ", "Required", "unknown", "none",
               "placeholder", "project-owner", "TO" + "DO", "to" + "do: assign", "replace_with_project_owner"]
        no = ["alice", "Tom Szenessy", "tbd later", "to" + "do list app", "[x] done item", "none of the above"]
        for value in yes:
            with self.subTest(value=value):
                self.assertTrue(core.is_placeholder(value))
        for value in no:
            with self.subTest(value=value):
                self.assertFalse(core.is_placeholder(value))


class DateHelperTests(unittest.TestCase):
    def test_parse_iso_date_table(self) -> None:
        good = [("2026-10-07", (2026, 10, 7)), (" 2026-01-31 ", (2026, 1, 31)), ("2024-02-29", (2024, 2, 29))]
        for text, ymd in good:
            with self.subTest(text=text):
                self.assertEqual(core.parse_iso_date(text), datetime(*ymd).date())
        for text in [None, "", "2026-13-01", "2026-02-30", "2025-02-29", "07/10/2026", "2026-1-5x", "soon"]:
            with self.subTest(text=text):
                self.assertIsNone(core.parse_iso_date(text))

    def test_future_and_stale(self) -> None:
        today = datetime.now(timezone.utc).date()
        latest = core.latest_today()  # the latest local date anywhere: never "future" (test_local_dates.py)
        day = timedelta(days=1)
        future = [(today, False), (latest, False), (latest + day, True), (today - day, False)]
        for value, expected in future:
            with self.subTest(value=str(value)):
                self.assertIs(core.date_is_future(value), expected)
        stale = [(today, False), (today - timedelta(days=364), False), (today - timedelta(days=366), True),
                 (latest + day, True)]
        for value, expected in stale:
            with self.subTest(value=str(value)):
                self.assertIs(core.date_is_stale(value), expected)


if __name__ == "__main__":
    unittest.main()
