"""The generated docs index skips transient handoffs and still indexes real docs."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from kit import docsync  # noqa: E402

LINE = "<!-- index: operate | Owns it | Read when. -->"


class DocsIndexExclusionTest(unittest.TestCase):
    def render(self, root: Path, files: list[str]) -> str:
        (root / "project.toml").write_text('schema = 1\nname = "t"\nkind = "app"\n', encoding="utf-8")
        for rel in files:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(f"# T\n\n{LINE}\n", encoding="utf-8")
        return docsync.render_index(root, files)

    def test_handoff_does_not_change_index_but_real_doc_adds_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = ["docs/README.md", "docs/a.md"]
            before = self.render(root, base)
            self.assertIn("a.md", before)
            with_handoff = self.render(root, base + ["docs/handoffs/2026-01-01-0000-x.md", "docs/handoffs/README.md"])
            self.assertEqual(before, with_handoff)
            with_doc = self.render(root, base + ["docs/x.md"])
            self.assertIn("x.md", with_doc)
            self.assertNotEqual(before, with_doc)


if __name__ == "__main__":
    unittest.main()
