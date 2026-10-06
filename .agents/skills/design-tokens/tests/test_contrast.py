# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Jake Schincariol. Adapted from https://github.com/Jakeschincariol/replica-skill @ 77c9436fb3d18c3d58169efb8caf4fe906b0dc51.

import io
import os
import unittest
from contextlib import redirect_stdout

from _load import load, ROOT

contrast = load("contrast")


class Contrast(unittest.TestCase):
    def test_known_ratios(self):
        self.assertAlmostEqual(contrast.ratio("#000", "#fff"), 21.0, places=2)
        self.assertAlmostEqual(contrast.ratio("#ffffff", "#ffffff"), 1.0, places=2)
        # #767676 on white is the classic just-passes-AA grey
        self.assertGreaterEqual(contrast.ratio("#767676", "#ffffff"), 4.5)
        self.assertLess(contrast.ratio("#777777", "#ffffff"), 4.5)

    def test_nested_tokens_flatten(self):
        cols = contrast.colours({"color": {"text": {"default": "#111", "muted": {"value": "#999"}},
                                           "bg": "#fff", "$type": "color"}})
        self.assertEqual(cols, {"text-default": "#111", "text-muted": "#999", "bg": "#fff"})

    def test_default_pairs_and_large_text(self):
        cols = {"text": "#111111", "text-muted": "#949494", "bg": "#ffffff", "accent": "#2563eb"}
        pairs = contrast.default_pairs(cols)
        self.assertIn(["text", "bg"], pairs)
        self.assertNotIn(["accent", "bg"], pairs)
        rows = contrast.check(cols, [["text-muted", "bg"], ["text-muted", "bg", "large"]])
        self.assertFalse(rows[0]["aa"])
        self.assertTrue(rows[1]["aa"])

    def test_shipped_tokens_template_passes(self):
        path = os.path.join(ROOT, "tokens.json")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(contrast.main([path]), 0)

    def test_cli_pair_failure_exit_code(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(contrast.main(["#aaaaaa", "#ffffff"]), 1)
            self.assertEqual(contrast.main(["#222222", "#ffffff"]), 0)


if __name__ == "__main__":
    unittest.main()
