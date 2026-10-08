# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Jake Schincariol. Adapted from https://github.com/Jakeschincariol/replica-skill (revision: see project.toml [[skills]]).

import csv
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT

parity = load("parity")

MATRIX = """feature,area,priority,status,evidence,acceptance,source
Pick a time slot,booking page,must,yes,tests/a.py,,product-recon
Confirmation email,booking page,must,partial,,no calendar file yet,product-recon
Reschedule link,booking page,must,no,,,product-recon
Round-robin across a team,team,should,no,,,product-recon
Custom booking questions,booking page,should,yes,,,product-recon
Embed on a website,sharing,could,no,,,product-recon
Their partner marketplace,integrations,could,skip,,their network not ours,product-recon
SMS reminders,notifications,should,no,,the top request in reviews,review-mining
"""

LEGACY = """feature,area,priority,original,clone,notes
Pick a time slot,booking page,must,yes,yes,
Reschedule link,booking page,must,yes,no,
SMS reminders,notifications,should,no,yes,ours
"""


def write(d, name, text):
    path = os.path.join(d, name)
    with open(path, "w") as fh:
        fh.write(text)
    return path


class Score(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = write(self.tmp.name, "features.csv", MATRIX)

    def tearDown(self):
        self.tmp.cleanup()

    def test_weighted_score(self):
        r = parity.score(parity.load(self.path))
        # counted weights: 3+3+3+2+2+1 = 14, earned: 3 + 1.5 + 0 + 0 + 2 + 0 = 6.5
        self.assertAlmostEqual(r["feature_score"], round(100 * 6.5 / 14, 1))
        self.assertEqual(r["counted"], 6)
        self.assertEqual((r["must_have_done"], r["must_have_total"]), (1, 3))

    def test_skip_and_extras_are_not_scored_but_listed(self):
        r = parity.score(parity.load(self.path))
        self.assertEqual([m["feature"] for m in r["skipped"]], ["Their partner marketplace"])
        self.assertEqual([m["feature"] for m in r["extras"]], ["SMS reminders"])

    def test_missing_is_in_build_order(self):
        r = parity.score(parity.load(self.path))
        order = [m["feature"] for m in r["missing"]]
        self.assertEqual(order[0], "Reschedule link")          # must, not started
        self.assertEqual(order[1], "Confirmation email")       # must, partial
        self.assertEqual(order[2], "Round-robin across a team")
        self.assertEqual(order[-1], "Embed on a website")
        self.assertEqual(r["missing"][0]["priority"], "must")

    def test_weakest_area_first(self):
        r = parity.score(parity.load(self.path))
        self.assertEqual(r["by_area"][0]["score"], 0.0)
        self.assertIn(r["by_area"][0]["area"], ("team", "sharing"))

    def test_render_says_not_shippable(self):
        r = parity.combine(parity.score(parity.load(self.path)), [])
        text = parity.render(r)
        self.assertIn("Not shippable yet: 2 must-have", text)
        self.assertIn("their network not ours", text)

    def test_visual_folds_in_at_20_percent(self):
        d = self.tmp.name
        v1 = write(d, "a.json", json.dumps({"score": 80.0, "mode": "layout",
                                            "files": {"clone": "clone/home.png"}}))
        v2 = write(d, "b.json", json.dumps({"score": 60.0, "mode": "layout"}))
        r = parity.combine(parity.score(parity.load(self.path)),
                           parity.visual_scores([v1, v2]))
        self.assertEqual(r["layout_score"], 70.0)
        self.assertAlmostEqual(r["overall"], round(0.8 * r["feature_score"] + 14.0, 1))

    def test_bad_values_are_reported_not_fatal(self):
        p = write(self.tmp.name, "bad.csv",
                  "feature,priority,status\nThing,urgent,maybe\n")
        r = parity.score(parity.load(p))
        self.assertEqual(len(r["problems"]), 2)
        self.assertEqual(r["feature_score"], 0.0)

    def test_missing_column_is_an_error(self):
        p = write(self.tmp.name, "nocol.csv", "feature,area\nx,y\n")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(parity.main([p]), 2)

    def test_cli_fail_under(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(parity.main([self.path, "--fail-under", "80"]), 1)
            self.assertEqual(parity.main([self.path, "--fail-under", "10"]), 0)

    def test_shipped_template_parses(self):
        # The feature matrix template ships with product-recon.
        path = os.path.join(ROOT, os.pardir, "product-recon", "features.csv")
        r = parity.score(parity.load(path))
        self.assertGreater(r["counted"], 0)
        self.assertEqual(r["problems"], [])

    def test_shipped_templates_have_one_field_count_per_row(self):
        for name in (("product-recon", "features.csv"),
                     ("product-kickoff", "production-features.csv")):
            with open(os.path.join(ROOT, os.pardir, *name), newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual({len(r) for r in rows}, {len(rows[0])}, name)
            self.assertEqual(rows[0], ["feature", "area", "priority", "status",
                                       "evidence", "acceptance", "source"])

    def test_kickoff_schema_scores_without_error(self):
        # Regression: the kickoff/make next schema has no 'clone' column and
        # used to exit 2.
        path = os.path.join(ROOT, os.pardir, "product-kickoff", "production-features.csv")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(parity.main([path]), 0)
        r = parity.score(parity.load(path))
        self.assertEqual(r["problems"], [])
        self.assertEqual(r["feature_score"], 0.0)
        self.assertGreater(r["must_have_total"], 0)

    def test_legacy_clone_column_still_scores_with_a_deprecation_note(self):
        p = write(self.tmp.name, "legacy.csv", LEGACY)
        r = parity.score(parity.load(p))
        self.assertEqual(r["feature_score"], 50.0)
        self.assertEqual([m["feature"] for m in r["extras"]], ["SMS reminders"])
        self.assertTrue(any("DEPRECATED" in x for x in r["problems"]))

    def test_pixel_mode_scores_are_not_averaged_into_layout(self):
        d = self.tmp.name
        a = write(d, "a.json", json.dumps({"score": 80.0, "mode": "layout"}))
        b = write(d, "b.json", json.dumps({"score": 10.0, "mode": "pixel",
                                           "files": {"clone": "px.png"}}))
        blank = write(d, "c.json", json.dumps({"score": 0.0, "mode": "layout",
                                               "comparable": False}))
        r = parity.combine(parity.score(parity.load(self.path)),
                           parity.visual_scores([a, b, blank]))
        self.assertEqual(r["layout_score"], 80.0)
        self.assertEqual([v["file"] for v in r["visual_ignored"]], ["px.png", blank])
        self.assertIn("Ignored", parity.render(r))
        only_pixel = parity.combine(parity.score(parity.load(self.path)),
                                    parity.visual_scores([b]))
        self.assertNotIn("layout_score", only_pixel)
        self.assertEqual(only_pixel["overall"], only_pixel["feature_score"])

    def test_ragged_row_extra_columns_are_ignored(self):
        # Regression: a row with more values than the header used to crash
        # load() with AttributeError on the DictReader None key.
        p = write(self.tmp.name, "ragged.csv",
                  MATRIX + "Extra bits,sharing,could,no,,surprise,kickoff,extra1,extra2\n")
        rows = parity.load(p)
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[-1]["feature"], "Extra bits")
        self.assertEqual(rows[-1]["acceptance"], "surprise")
        self.assertNotIn("", rows[-1])          # extras land in no '' key
        r = parity.score(rows)
        self.assertEqual(r["problems"], [])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(parity.main([p]), 0)


class BadVisualJson(unittest.TestCase):
    """--visual files that are not imgdiff.py --json output exit 2 and name the file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.matrix = write(self.tmp.name, "features.csv", MATRIX)

    def run_with(self, content):
        path = os.path.join(self.tmp.name, "diff.json")
        with open(path, "wb") as fh:
            fh.write(content if isinstance(content, bytes) else content.encode("utf-8"))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = parity.main([self.matrix, "--visual", path])
        return code, out.getvalue(), err.getvalue(), path

    def test_malformed_visual_files_exit_2_naming_the_file(self):
        bad = [b"", b"{not json", b"\xff\xfe\x00", "[]", "[1, 2]", "3", "null", '"score"', "{}",
               '{"score": null}', '{"score": "high"}', '{"score": [1]}', '{"score": {"a": 1}}',
               '{"score": NaN}', '{"score": Infinity}', '{"score": -5}', '{"score": 101}', '{"score": true}']
        for content in bad:
            code, out, err, path = self.run_with(content)
            self.assertEqual(code, 2, content)
            self.assertIn("parity:", err, content)
            self.assertIn(os.path.basename(path), err, content)
            self.assertEqual(out, "", content)

    def test_good_visual_file_still_scores_and_unicode_names_survive(self):
        code, out, _, _ = self.run_with('{"score": 90, "mode": "layout", "files": {"clone": "écran-日本.png"}}')
        self.assertEqual(code, 0)
        self.assertIn("écran-日本.png", out)

    def test_odd_file_labels_fall_back_to_the_path(self):
        for label in ('"clone.png"', '{"clone": 5}', "null"):
            code, out, _, path = self.run_with('{"score": 90, "files": %s}' % label)
            self.assertEqual(code, 0, label)
            self.assertIn(path, out)

    def test_missing_visual_file_exits_2(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(parity.main([self.matrix, "--visual", os.path.join(self.tmp.name, "nope.json")]), 2)


if __name__ == "__main__":
    unittest.main()
