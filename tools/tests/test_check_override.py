"""A project can downgrade a misfiring check to advisory, never silently and never to nothing (#23)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import Scratch  # noqa: E402

from kit.core import RepoctlError  # noqa: E402
from kit.checkrun import run_checks  # noqa: E402
from kit.registry import Registry  # noqa: E402

MANIFEST = 'schema = 1\nname = "Demo"\nkind = "template"\nphase = "bootstrap"\nlicense = "UNSELECTED"\nowners = []\n' \
           '[governance]\nprofile = "regulated"\n'
OVERRIDE = '\n[checks.dead-bindings]\nseverity = "advisory"\nreason = "docs describe generated build output"\n'


class CheckOverrideTests(Scratch):
    def setUp(self) -> None:
        super().setUp()
        self.write("project.toml", MANIFEST)
        self.write("docs/README.md", "# Docs\n")
        self.write("docs/a.md", "# A\n<!-- covers: missing/** -->\n")

    def downgrade(self) -> None:
        self.write("project.toml", MANIFEST + OVERRIDE)

    def test_without_the_declaration_the_check_blocks(self) -> None:
        self.assertIn("[dead-bindings]", self.cli("check").stderr)
        hard, _ = run_checks(self.root, blocking_only=True)
        self.assertTrue(any(item.startswith("[dead-bindings]") for item in hard), hard)

    def test_downgraded_check_stops_blocking_but_still_reports(self) -> None:
        self.downgrade()
        hard, advisory = run_checks(self.root, blocking_only=True)
        self.assertFalse(any(item.startswith("[dead-bindings]") for item in hard), hard)
        self.assertTrue(any(item.startswith("[dead-bindings]") and "missing/**" in item for item in advisory), advisory)
        result = self.cli("check")
        self.assertNotIn("[dead-bindings]", result.stderr)  # other baseline findings of this bare scratch repo remain
        self.assertIn("advisory (downgraded in project.toml [checks]): [dead-bindings]", result.stdout)

    def test_the_downgrade_is_listed_with_its_reason(self) -> None:
        self.downgrade()
        for command in ("capabilities", "garden"):
            result = self.cli(command)
            self.assertIn("dead-bindings: docs describe generated build output", result.stdout, command)

    def test_removing_the_declaration_restores_blocking(self) -> None:
        self.downgrade()
        self.assertNotIn("[dead-bindings]", self.cli("check").stderr)
        self.write("project.toml", MANIFEST)
        self.assertIn("[dead-bindings]", self.cli("check").stderr)

    def test_other_checks_keep_blocking(self) -> None:
        self.downgrade()
        self.write("docs/b.md", "# B\n")  # not in the docs index
        hard, _ = run_checks(self.root, blocking_only=True)
        self.assertTrue(any(item.startswith("[docs-index]") for item in hard), hard)

    def rejected(self, block: str) -> str:
        self.write("project.toml", MANIFEST + block)
        with self.assertRaises(RepoctlError) as caught:
            Registry(self.root).check_overrides  # noqa: B018 - the property raises
        return str(caught.exception)

    def test_nothing_removes_or_skips_a_check(self) -> None:
        for value in ("off", "skip", "disabled", "ignore", "blocking"):
            message = self.rejected(f'\n[checks.dead-bindings]\nseverity = "{value}"\nreason = "because I said so, loudly"\n')
            self.assertIn('severity must be "advisory"', message)
        self.assertIn("only severity", self.rejected('\n[checks.dead-bindings]\nenabled = false\nseverity = "advisory"\n'
                                                      'reason = "because I said so, loudly"\n'))

    def test_unknown_check_and_missing_reason_are_clear_errors(self) -> None:
        self.assertIn("names no check", self.rejected('\n[checks.no-such-check]\nseverity = "advisory"\nreason = "a long enough reason"\n'))
        self.assertIn("reason is required", self.rejected('\n[checks.dead-bindings]\nseverity = "advisory"\n'))
        self.assertIn("reason is required", self.rejected('\n[checks.dead-bindings]\nseverity = "advisory"\nreason = "n/a"\n'))
        self.assertIn("already advisory", self.rejected('\n[checks.orphan-files]\nseverity = "advisory"\nreason = "a long enough reason"\n'))

    def test_a_malformed_table_stops_the_gate_instead_of_passing(self) -> None:
        self.write("project.toml", MANIFEST + '\n[checks.dead-bindings]\nseverity = "off"\nreason = "a long enough reason"\n')
        self.assertNotEqual(self.cli("check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
