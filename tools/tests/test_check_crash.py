"""A malformed file, manifest value, or crashing check is a named finding, not a traceback (#25)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import Scratch, git_in  # noqa: E402  shared builders, in-process CLI, isolated git (#43)

from kit import docsync  # noqa: E402
from kit.core import RepoctlError, markdown_link_target  # noqa: E402
from kit.checkrun import run_checks  # noqa: E402

REPOCTL = TOOLS / "repoctl.py"
MANIFEST = 'schema = 1\nname = "Demo"\nkind = "template"\nphase = "bootstrap"\nlicense = "UNSELECTED"\nowners = []\n' \
           '[governance]\nprofile = "regulated"\n'


class CrashTests(Scratch):
    def setUp(self) -> None:
        super().setUp()
        self.write("project.toml", MANIFEST)
        self.write("docs/README.md", "# Docs\n")

    def checks(self):
        return run_checks(self.root, blocking_only=False)

    def test_empty_link_target_is_a_value_not_an_error(self) -> None:
        self.assertEqual(markdown_link_target(" "), "")
        self.assertEqual(markdown_link_target(""), "")

    def test_empty_link_in_doc_does_not_crash_the_check(self) -> None:
        self.write("docs/a.md", "# A\n[x]( )\n[gone](missing.md)\n")
        hard, _ = self.checks()
        self.assertTrue(any("[markdown-links]" in item and "missing.md" in item for item in hard), hard)
        self.assertFalse(any("crashed" in item for item in hard), hard)

    def test_invalid_utf8_doc_is_a_finding(self) -> None:
        self.write("docs/a.md", b"# A\n\xff\xfe\n")
        hard, _ = self.checks()
        self.assertTrue(any("not valid UTF-8" in item and "docs/a.md" in item for item in hard), hard)
        self.assertFalse(any("crashed" in item for item in hard), hard)
        result = self.cli("check")
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_invalid_utf8_capability_file_is_a_one_line_error(self) -> None:
        self.write(".agents/skills/bad/SKILL.md", b"---\nname: bad\ndescription: \xff\n---\n")
        result = self.cli("check")
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("not valid UTF-8", result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_bad_owners_type_is_named_and_other_checks_still_report(self) -> None:
        self.write("project.toml", MANIFEST.replace("owners = []", "owners = 5"))
        self.write("docs/a.md", "# A\n[gone](missing.md)\n")
        hard, _ = self.checks()
        self.assertTrue(any("[manifest-structure]" in item and "owners" in item for item in hard), hard)
        self.assertTrue(any("[markdown-links]" in item and "missing.md" in item for item in hard), hard)

    def test_non_table_skills_and_repository_do_not_traceback(self) -> None:
        self.write("project.toml", MANIFEST.replace('owners = []', 'owners = []\nskills = [1]\nrepository = 3'))
        hard, advisory = self.checks()
        self.assertTrue(any("[manifest-structure]" in item for item in hard), hard)

    def test_project_check_raising_is_a_crashed_finding(self) -> None:
        self.write(".agents/checks/boom.py", (
            "from kit.registry import check\n\n"
            '@check("boom", "Always raises; for the crash test", blocks=True,\n'
            '       reason="Test fixture proving a crashing check becomes a blocking finding.")\n'
            "def boom(context):\n    raise ValueError('bad value')\n"))
        hard, _ = self.checks()
        self.assertTrue(any("check boom crashed: ValueError: bad value" in item for item in hard), hard)
        self.assertTrue(any("[boom]" in item for item in hard), hard)

    def test_findings_are_prefixed_and_reasons_printed_once(self) -> None:
        self.write("docs/a.md", "# A\n[gone](missing.md)\n[gone2](missing2.md)\n")
        hard, _ = self.checks()
        self.assertTrue(all(item.startswith("[") or item.startswith("known failure") for item in hard), hard)
        result = self.cli("check")
        self.assertEqual(result.stderr.count("[markdown-links] why it blocks"), 1, result.stderr)
        self.assertIn("[markdown-links] ", result.stderr)

    def test_bad_eval_regex_and_bad_eval_toml_are_one_line_errors(self) -> None:
        from kit import evals
        self.write(".agents/evals/a.toml", '[[tasks]]\nid = "t"\nprompt = "p"\nexpect = "("\n')
        with self.assertRaisesRegex(RepoctlError, r"a\.toml.*regex"):
            evals.load_tasks(self.root)
        self.write(".agents/evals/a.toml", "not = [valid\n")
        with self.assertRaisesRegex(RepoctlError, r"a\.toml.*invalid TOML"):
            evals.load_tasks(self.root)

    def test_bad_trial_toml_is_one_line_error(self) -> None:
        from kit import trial
        self.write(".agents/trials/t.toml", "id = \n")
        with self.assertRaisesRegex(RepoctlError, r"t\.toml.*invalid TOML"):
            trial.load_trial(self.root, "t")

    def test_broken_pipe_exits_quietly(self) -> None:
        process = subprocess.run(
            f'"{sys.executable}" "{REPOCTL}" --root "{TOOLS.parent}" map | head -c10 >/dev/null',
            shell=True, capture_output=True, text=True, check=False)
        self.assertEqual(process.stderr, "")
        direct = subprocess.Popen([sys.executable, str(REPOCTL), "--root", str(TOOLS.parent), "map"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        direct.stdout.read(10)
        direct.stdout.close()
        error = direct.stderr.read()
        direct.stderr.close()
        self.assertEqual(direct.wait(), 0)
        self.assertEqual(error, "")

    def test_internal_error_is_one_line_and_debug_reraises(self) -> None:
        sys.path.insert(0, str(TOOLS))
        import repoctl
        with mock.patch.object(repoctl, "Registry", side_effect=ValueError("boom")):
            with mock.patch("sys.stderr") as stderr:
                self.assertEqual(repoctl.main(["--root", str(self.root), "check"]), 1)
            written = "".join(call.args[0] for call in stderr.write.call_args_list)
            self.assertIn("repoctl: internal error: ValueError: boom (rerun with REPOCTL_DEBUG=1", written)
            with mock.patch.dict(os.environ, {"REPOCTL_DEBUG": "1"}), self.assertRaises(ValueError):
                repoctl.main(["--root", str(self.root), "check"])
        with mock.patch.object(repoctl, "Registry", side_effect=KeyboardInterrupt):
            self.assertEqual(repoctl.main(["--root", str(self.root), "check"]), 130)

    def test_root_flag_works_after_the_subcommand(self) -> None:
        result = subprocess.run([sys.executable, str(REPOCTL), "check", "--root", str(self.root)],
                                capture_output=True, text=True, check=False)
        self.assertNotIn("unrecognized", result.stderr)

    def test_new_advisory_checks_report(self) -> None:
        self.write("docs/a.md", "# A")
        self.write("CLAUDE.md", "# Claude\nsame\n")
        self.write("GEMINI.md", "# Gemini\ndifferent\n")
        _, advisory = self.checks()
        self.assertTrue(any(item.startswith("[final-newline]") and "docs/a.md" in item for item in advisory), advisory)
        self.assertTrue(any(item.startswith("[host-twins]") for item in advisory), advisory)

    def test_failed_history_read_is_an_advisory(self) -> None:
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        self.write("docs/b.md", "<!-- covers: project.toml -->\n# B\n")
        with mock.patch.object(docsync, "history_read", return_value=None):
            _, advisory = self.checks()
        self.assertTrue(any("history read failed or timed out" in item for item in advisory), advisory)
        _, advisory = self.checks()
        self.assertFalse(any("history read failed" in item for item in advisory), advisory)


if __name__ == "__main__":
    unittest.main()
