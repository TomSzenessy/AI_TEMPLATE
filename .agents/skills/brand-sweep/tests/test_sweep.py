# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Jake Schincariol. Adapted from https://github.com/Jakeschincariol/replica-skill @ 77c9436fb3d18c3d58169efb8caf4fe906b0dc51.

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load

sweep = load("sweep")


def put(root, rel, text, binary=False):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if binary else "w") as fh:
        fh.write(text)
    return path


class Sweep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.root = self.tmp.name
        put(r, "src/app/page.tsx", "export default function Page() {\n"
                                   "  return <h1>Slotwise</h1>\n}\n")
        put(r, "src/components/CalendlyEmbed.tsx", "// left over\n")
        put(r, "src/lib/copy.ts", "export const hero = 'The calendly alternative'\n")
        put(r, "src/styles/tokens.css", ":root { --accent: #006BFF; --bg: #fff; }\n")
        put(r, "src/lib/links.ts", "const help = 'https://help.calendly.com/x'\n")
        put(r, "src/lib/team.ts", "export const AcuitySchedulingSync = 1\n")
        put(r, "reference/recon.md", "# Recon: Calendly\n")
        put(r, "node_modules/x/index.js", "calendly\n")
        put(r, "public/logo.png", b"\x89PNG\0calendly", binary=True)
        put(r, "package-lock.json", '{"calendly": 1}\n')

    def tearDown(self):
        self.tmp.cleanup()

    def run_sweep(self, **kw):
        return sweep.sweep(self.root, avoid=["Calendly", "Acuity Scheduling"],
                           domains=["calendly.com"], colors=["#006bff"], **kw)

    def test_finds_names_paths_domains_and_colours(self):
        hits = self.run_sweep()
        kinds = {(h["kind"], os.path.basename(h["file"].rstrip("/"))) for h in hits}
        self.assertIn(("path", "CalendlyEmbed.tsx"), kinds)
        self.assertIn(("name", "copy.ts"), kinds)
        self.assertIn(("domain", "links.ts"), kinds)
        self.assertIn(("color", "tokens.css"), kinds)
        self.assertIn(("name", "team.ts"), kinds)   # AcuitySchedulingSync

    def test_skips_planning_folder_deps_locks_and_binaries(self):
        files = {h["file"] for h in self.run_sweep()}
        self.assertFalse(any(f.startswith("reference") for f in files))
        self.assertFalse(any("node_modules" in f for f in files))
        self.assertNotIn("package-lock.json", files)
        self.assertNotIn(os.path.join("public", "logo.png"), files)
        self.assertNotIn(os.path.join("src", "app", "page.tsx"), files)

    def test_include_reference(self):
        files = {h["file"] for h in self.run_sweep(include_reference=True)}
        self.assertIn(os.path.join("reference", "recon.md"), files)

    def test_short_hex_matches_long(self):
        put(self.root, "src/a.css", "a { color: #06f }\n")
        hits = sweep.sweep(self.root, colors=["#0066FF"])
        self.assertTrue(any(h["file"].endswith("a.css") for h in hits))

    def test_cli_exit_codes_and_config(self):
        cfg = put(self.root, "brand.json", json.dumps({"avoid": ["Calendly"]}))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sweep.main([self.root, "--config", cfg]), 1)
        clean = tempfile.mkdtemp(dir=self.root)
        put(clean, "index.html", "<h1>Slotwise</h1>")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(sweep.main([clean, "--avoid", "Calendly"]), 0)
        self.assertIn("Clean", buf.getvalue())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(sweep.main([clean]), 2)

    def test_bare_and_alpha_hex_forms(self):
        put(self.root, "src/b.css", "a { color: #006bffaa; b: #06fa }\n")
        for form in ("006bff", "#006bff", "006bffff", "#006bff80"):
            hits = sweep.sweep(self.root, colors=[form])
            files = {os.path.basename(h["file"]) for h in hits}
            self.assertIn("b.css", files, form)
            self.assertIn("tokens.css", files, form)
        short = {os.path.basename(h["file"]) for h in sweep.sweep(self.root, colors=["06f"])}
        self.assertIn("b.css", short)  # #06fa is #0066ffaa

    def test_invalid_colours_raise_and_cli_exits_2(self):
        for bad in ("rgb(0,107,255)", "#12345", "zzzzzz", "#12"):
            with self.assertRaises(ValueError):
                sweep.sweep(self.root, colors=[bad])
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(sweep.main([self.root, "--colors", bad]), 2)
            self.assertIn("colour", err.getvalue())

    def test_cli_bare_hex_finds_colour(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(sweep.main([self.root, "--colors", "006bff"]), 1)
        self.assertIn("tokens.css", buf.getvalue())

    def _kickoff(self):
        d = tempfile.mkdtemp()
        put(d, "src/app.ts", "export const x = 1\n")
        put(d, "docs/product/research.md", "Comparable: Calendly (https://calendly.com)\n")
        put(d, ".agent/references/calendly.md", "Calendly notes\n")
        put(d, ".review/r.md", "Calendly\n")
        return d

    def test_kickoff_shaped_repo_sweeps_clean_with_exclude(self):
        d = self._kickoff()
        args = [d, "--avoid", "Calendly", "--domains", "calendly.com"]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sweep.main(args), 1)  # research doc still scanned
            self.assertEqual(sweep.main(args + ["--exclude", "docs/product/research.md"]), 0)
        files = {h["file"] for h in sweep.sweep(d, avoid=["Calendly"])}
        self.assertEqual(files, {os.path.join("docs", "product", "research.md")})

    def test_exclude_from_config_and_dir_glob(self):
        d = self._kickoff()
        cfg = put(tempfile.mkdtemp(), "brand.json", json.dumps({"avoid": ["Calendly"],
                                                "exclude": ["docs/product/"]}))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sweep.main([d, "--config", cfg]), 0)
            self.assertEqual(sweep.main([d, "--avoid", "Calendly", "--exclude", "*.md"]), 0)

    def test_hit_in_src_still_exits_1_with_excludes(self):
        d = self._kickoff()
        put(d, "src/copy.ts", "// calendly\n")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sweep.main([d, "--avoid", "Calendly",
                                         "--exclude", "docs/product/research.md"]), 1)


if __name__ == "__main__":
    unittest.main()
