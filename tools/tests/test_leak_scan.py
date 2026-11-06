"""#152: a commit-keyed .gitleaksignore fingerprint is flagged before a squash orphans it."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import Scratch  # noqa: E402

from kit import checks  # noqa: E402


class LeakScanFingerprintTests(Scratch):
    def test_a_commit_keyed_fingerprint_is_reported(self) -> None:
        self.write(".gitleaksignore", "# comment\n" + "a" * 40 + ":tests/fixture.py:generic-api-key:3\n")
        findings = checks.leak_scan_fingerprints(SimpleNamespace(root=self.root))
        self.assertEqual(len(findings), 1)
        self.assertIn("squash merge orphans it", findings[0])

    def test_a_path_only_allowlist_is_not_reported(self) -> None:
        self.write(".gitleaksignore", "tests/fixtures/**\n")
        self.assertEqual(checks.leak_scan_fingerprints(SimpleNamespace(root=self.root)), [])

    def test_a_missing_file_is_not_reported(self) -> None:
        self.assertEqual(checks.leak_scan_fingerprints(SimpleNamespace(root=self.root)), [])


if __name__ == "__main__":
    unittest.main()
