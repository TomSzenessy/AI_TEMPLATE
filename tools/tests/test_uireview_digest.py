"""Surface digests and UI-review freshness (#27)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kit import uireview  # noqa: E402

PROJECT = """\
schema = 1
name = "demo"
kind = "web"

[[surfaces]]
id = "app"
path = "{path}"
status = "active"

[surfaces.preview]
command = ["true"]
url = "http://localhost:{{port}}"
"""


class SurfaceDigestTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.write("app/index.html", "<h1>hi</h1>")
        self.write("other/readme.txt", "x")
        self.write("top.txt", "x")

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_root_surface_digest_covers_every_file(self) -> None:
        empty = uireview.surface_digest(self.root, "nothing-here")
        before = uireview.surface_digest(self.root, ".")
        self.assertNotEqual(before, empty)
        self.assertEqual(before, uireview.surface_digest(self.root, ""))
        self.write("other/readme.txt", "changed")
        self.assertNotEqual(before, uireview.surface_digest(self.root, "."))

    def test_equivalent_spellings_share_a_digest(self) -> None:
        self.assertEqual(uireview.surface_digest(self.root, "./app"), uireview.surface_digest(self.root, "app"))
        self.assertEqual(uireview.surface_digest(self.root, "app/"), uireview.surface_digest(self.root, "app"))
        self.assertNotEqual(uireview.surface_digest(self.root, "app"), uireview.surface_digest(self.root, "nothing-here"))

    def test_edit_outside_a_surface_does_not_change_it(self) -> None:
        before = uireview.surface_digest(self.root, "app")
        self.write("other/readme.txt", "changed")
        self.write("new-outside.txt", "y")
        self.assertEqual(before, uireview.surface_digest(self.root, "app"))
        self.write("app/index.html", "<h1>changed</h1>")
        self.assertNotEqual(before, uireview.surface_digest(self.root, "app"))

    def test_root_surface_pass_review_goes_stale_after_an_edit(self) -> None:
        self.write("project.toml", PROJECT.format(path="."))
        digest = uireview.surface_digest(self.root, ".")
        self.write(uireview.LOG, f"## Review 20260101T000000Z\n\n<!-- review: app={digest} -->\n\nVerdict: pass\n")
        self.assertEqual(uireview.review_status(self.root), [], "the review record itself must not stale the review")
        self.write("app/index.html", "<h1>changed</h1>")
        self.assertIn("changed since UI review", " ".join(uireview.review_status(self.root)))


if __name__ == "__main__":
    unittest.main()
