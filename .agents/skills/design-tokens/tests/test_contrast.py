# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Jake Schincariol. Adapted from https://github.com/Jakeschincariol/replica-skill (revision: see project.toml [[skills]]).

import io
import os
import unittest
from contextlib import redirect_stdout

from _load import load, ROOT

contrast = load("contrast")

# The same table lives in brand-sweep/tests/test_sweep.py: each skill stays
# self-contained, so the accepted forms are pinned in both places.
HEX_FORMS = {
    "#006bff": "#006bff", "006bff": "#006bff", "#06f": "#0066ff", "06f": "#0066ff",
    "#006bffaa": "#006bff", "006bff80": "#006bff", "#06fa": "#0066ff", "#0066FF": "#0066ff",
}
BAD_HEX = ("rgb(0,107,255)", "#12345", "zzzzzz", "#12", "")


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

    def test_hex_forms_match_brand_sweep(self):
        for form, want in HEX_FORMS.items():
            self.assertEqual(contrast.norm_hex(form), want, form)
            self.assertEqual(contrast.parse_hex(form),
                             tuple(int(want[i:i + 2], 16) for i in (1, 3, 5)), form)
        for bad in BAD_HEX:
            with self.assertRaises(ValueError):
                contrast.parse_hex(bad)

    def test_bare_and_alpha_hex_work_in_ratio_and_cli(self):
        self.assertAlmostEqual(contrast.ratio("000000", "ffffffff"), 21.0, places=2)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(contrast.main(["222222", "ffffff"]), 0)
            self.assertEqual(contrast.main(["aaaaaa", "#ffffffff"]), 1)

    def test_bare_and_alpha_hex_in_a_token_file(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.json")
            with open(path, "w") as fh:
                json.dump({"color": {"text": "111111", "bg": "#ffffffff"},
                           "pairs": [["text", "bg"]]}, fh)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(contrast.main([path]), 0)

    def test_tokens_template_has_warning_and_focus_that_pass(self):
        import json
        with open(os.path.join(ROOT, "tokens.json")) as fh:
            tokens = json.load(fh)
        cols = contrast.colours(tokens)
        self.assertIn("warning", cols)
        self.assertIn("focus", cols)
        pairs = tokens["pairs"]
        self.assertIn(["focus", "bg", "ui"], pairs)
        self.assertIn(["warning", "bg"], pairs)
        rows = contrast.check(cols, pairs)
        self.assertTrue(all(r.get("aa") for r in rows), rows)

    def test_cli_pair_failure_exit_code(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(contrast.main(["#aaaaaa", "#ffffff"]), 1)
            self.assertEqual(contrast.main(["#222222", "#ffffff"]), 0)


if __name__ == "__main__":
    unittest.main()
