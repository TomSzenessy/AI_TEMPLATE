"""A build session ends only when the product does (#8): invalid features fail the check; the stop hook pushes on."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import test_kit
from kit import checkrun, product

HEADER = "feature,area,priority,status,evidence,acceptance,source\n"
SURFACE = '\n[[surfaces]]\nid = "app"\npath = "src"\nkind = "code"\nquality_oracle = "tests"\nverification = [["true"]]\n'
MARK = "not the product"
PACK = Path(__file__).resolve().parents[2] / ".agents/packs/product.md"


class ProductDriveTests(test_kit.KitRepository):
    def setUp(self) -> None:
        super().setUp()
        self.write(".agents/packs/product.md", PACK.read_text())
        self.write("project.toml", (self.root / "project.toml").read_text() + SURFACE)
        self.write("docs/product/features.csv", HEADER + "Add a habit,core,must,no,,One tap,owner\n")
        self.commit("product")

    def start(self) -> None:
        self.cli("hook", "session-start", stdin=json.dumps({"session_id": "s1"}))

    def stop(self) -> str:
        return self.cli("hook", "stop", stdin=json.dumps({"session_id": "s1"})).stdout

    def reason(self) -> str:
        out = self.stop()
        self.assertTrue(out, "the stop hook should have blocked")
        decision = json.loads(out)
        self.assertEqual(decision["decision"], "block")
        return decision["reason"]

    def edit_product_code(self) -> None:
        self.write("src/habits.py", "def add():\n    return 1\n")

    def test_invalid_status_fails_the_check(self) -> None:
        self.write("docs/product/features.csv", HEADER + "Add a habit,core,must,todo,,One tap,owner\n")
        hard, _ = checkrun.run_checks(self.root, blocking_only=True, only=frozenset({"feature-evidence"}))
        text = "\n".join(hard)
        self.assertIn("docs/product/features.csv:2", text)
        self.assertIn("status must be yes, partial, no, or skip", text)

    def test_invalid_status_still_lets_next_show_the_step(self) -> None:
        self.write("project.toml", (self.root / "project.toml").read_text() + '[vision]\nstatus = "accepted"\n')
        self.write(product.RESEARCH, "# R\nhttps://a.example https://b.example https://c.example\n")
        self.write("docs/product/features.csv", HEADER + "Add a habit,core,must,todo,,One tap,owner\n")
        self.assertIn("status must be", product.next_step(self.root)["action"])

    def test_open_musts_after_product_code_edit_block_with_the_next_step(self) -> None:
        self.start()
        self.edit_product_code()
        reason = self.reason()
        self.assertIn(MARK, reason)
        self.assertIn("Add a habit", reason)
        self.assertIn("Next (", reason)

    def test_invalid_feature_list_blocks_after_product_code_edit(self) -> None:
        self.write("docs/product/features.csv", HEADER + "Add a habit,core,must,todo,,One tap,owner\n")
        self.commit("bad list")
        self.start()
        self.edit_product_code()
        reason = self.reason()
        self.assertIn(MARK, reason)
        self.assertIn("status must be", reason)

    def test_no_product_path_changed_never_blocks(self) -> None:
        self.start()
        self.write("README.md", "# Notes\n")
        self.assertNotIn(MARK, self.stop())

    def test_all_musts_done_does_not_block(self) -> None:
        self.write("tests/test_habits.py", "def test_add():\n    assert True\n")
        self.write("docs/product/features.csv", HEADER + "Add a habit,core,must,yes,tests/test_habits.py,One tap,owner\n")
        self.commit("done")
        self.start()
        self.edit_product_code()
        self.assertNotIn(MARK, self.stop())

    def test_product_pack_off_does_not_block(self) -> None:
        self.write("project.toml", (self.root / "project.toml").read_text() + "\n[packs]\nproduct = false\n")
        self.commit("pack off")
        self.start()
        self.edit_product_code()
        self.assertNotIn(MARK, self.stop())


if __name__ == "__main__":
    unittest.main()
