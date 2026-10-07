import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kit import docs  # noqa: E402


def token() -> str:
    return "gh" + "p_" + "A1b2C3d4E5" * 4


class HygieneScanTests(unittest.TestCase):
    def scan(self, data: bytes, name: str = "f.txt"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_bytes(data)
            return docs.scan_file_for_secrets(path)

    def test_large_file_with_trailing_token_is_flagged(self):
        data = (b"clean line\n" * 110_000) + token().encode()
        self.assertGreater(len(data), 1_200_000)
        labels, complete = self.scan(data)
        self.assertTrue(labels)
        self.assertTrue(complete)

    def test_clean_large_file_is_not_flagged(self):
        labels, complete = self.scan(b"clean line\n" * 110_000)
        self.assertEqual(labels, [])
        self.assertTrue(complete)

    def test_utf16_file_is_flagged(self):
        labels, _ = self.scan(("x\n" + token()).encode("utf-16"))
        self.assertTrue(labels)

    def test_token_split_across_chunk_boundary_is_flagged(self):
        tok = token().encode()
        start = docs.SCAN_CHUNK_BYTES - len(tok) // 2
        data = b"a" * (start - 1) + b"\n" + tok + b"\n" + b"b" * 100
        labels, _ = self.scan(data)
        self.assertTrue(labels)

    def test_non_utf8_text_is_scanned(self):
        labels, _ = self.scan(b"caf\xe9 " + token().encode())
        self.assertTrue(labels)

    def test_binary_nul_file_is_skipped(self):
        labels, _ = self.scan(b"\0" * 100 + token().encode())
        self.assertEqual(labels, [])

    def test_over_cap_reports_incomplete(self):
        original = docs.SCAN_CAP_BYTES
        docs.SCAN_CAP_BYTES = 2 * docs.SCAN_CHUNK_BYTES
        try:
            labels, complete = self.scan(b"a" * (3 * docs.SCAN_CHUNK_BYTES))
        finally:
            docs.SCAN_CAP_BYTES = original
        self.assertEqual(labels, [])
        self.assertFalse(complete)


if __name__ == "__main__":
    unittest.main()
