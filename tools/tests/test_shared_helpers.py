"""One fact, one owner: the shared helpers issue #49 consolidated stay consolidated.

Most guards here grep the kit's own sources (the acceptance criterion allows
"grep or a unit test"): a fact written a second time in another module fails
this suite. The behavioral guards cover what a grep cannot see: trial setup
runs git only through gitinfo (its timeout and quotepath handling), and
`verify` runs each blocking check exactly once, never twice.
"""

from __future__ import annotations

import contextlib
import io
import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import Scratch  # noqa: E402  isolated git for the behavioural tests (#43)

from kit import checks as kit_checks  # noqa: E402
from kit import commands, core, gitinfo, registry, structure, trial  # noqa: E402

KIT = Path(__file__).resolve().parents[1] / "kit"
REPOCTL = Path(__file__).resolve().parents[1] / "repoctl.py"
SOURCES = {path.name: path.read_text(encoding="utf-8") for path in sorted(KIT.glob("*.py"))}

# (fact, its literal spelling, the one module allowed to write it; None = written nowhere)
SINGLE_LITERALS = [
    ("kebab-case regex", "[a-z0-9]+(?:-[a-z0-9]+)*", "core.py"),
    ("fenced-code regex", "```.*?```", "core.py"),
    ("inline-code regex", "`[^`\\n]*`", "core.py"),
    ("UTC today", "datetime.now(timezone.utc).date()", "core.py"),
    ("date parsing", "strptime(", "core.py"),
    ("date parsing", "fromisoformat(", None),
    ("package spec split", 'partition("@', "core.py"),
    ("package spec split", 'split("@', None),
    ("local-clock date", "date.today(", None),
    ("reader file name", '"VISION.md"', "names.py"),
    ("reader file name", '"docs/STACK-DECISION.md"', "names.py"),
    ("reader file name", '"docs/design.md"', "names.py"),
    ("reader file name", '"docs/ERROR_LOG.md"', "names.py"),
    ("reader file name", '"HANDOVER.md"', "names.py"),
    ("gate phrase", "Commit blocked", "core.py"),
    ("gate phrase", "Not finished:", "core.py"),
    ("gate phrase", "check failed", "core.py"),
    ("gate phrase", "Self-healing gate before stopping", "core.py"),
    ("hook event", '"session-start"', "session.py"),
    ("hook event", '"pre-compact"', "session.py"),
    ("hook event", '"after-edit"', "session.py"),
    ("hook event", '"stop"', "session.py"),
    ("hook event", '"commit-msg"', "session.py"),
    ("changed-path diff parse", '"diff", "--name-only"', "gitinfo.py"),
    ("worktree walk", "os.walk(", "core.py"),
    ("ignored directory set", '".mypy_cache", ".pytest_cache", ".ruff_cache"', "core.py"),
    ("default branch", '.get("default_branch"', "core.py"),
]

# (fact, regex over kit sources, the one module allowed to match; None = no module)
SINGLE_REGEXES = [
    ("capability kinds list", r"skill[\"', ]+agent", "registry.py"),
]


class OneDefinitionTests(unittest.TestCase):
    """Each fact of issue #49 is written in exactly one kit module."""

    def assert_single(self, fact: str, found: set[str], owner: str | None) -> None:
        allowed = {owner} if owner else set()
        self.assertEqual(found, allowed, f"{fact}: written in {sorted(found)}; owner is {owner or 'nobody'}")

    def test_common_regexes_live_in_core(self) -> None:
        for fact, literal, owner in SINGLE_LITERALS:
            if "regex" not in fact:
                continue
            with self.subTest(fact=fact, literal=literal):
                self.assert_single(fact, {n for n, t in SOURCES.items() if literal in t}, owner)

    def test_date_and_package_facts_live_in_core(self) -> None:
        for fact, literal, owner in SINGLE_LITERALS:
            if fact not in {"date parsing", "package spec split", "UTC today", "local-clock date"}:
                continue
            with self.subTest(fact=fact, literal=literal):
                self.assert_single(fact, {n for n, t in SOURCES.items() if literal in t}, owner)

    def test_reader_file_names_come_from_names(self) -> None:
        for fact, literal, owner in SINGLE_LITERALS:
            if fact != "reader file name":
                continue
            with self.subTest(literal=literal):
                self.assert_single(fact, {n for n, t in SOURCES.items() if literal in t}, owner)

    def test_gate_phrases_are_written_once(self) -> None:
        for fact, literal, owner in SINGLE_LITERALS:
            if fact != "gate phrase":
                continue
            with self.subTest(literal=literal):
                self.assert_single(fact, {n for n, t in SOURCES.items() if literal in t}, owner)

    def test_kinds_and_hook_events_have_one_owner(self) -> None:
        for fact, literal, owner in SINGLE_LITERALS:
            if fact != "hook event":
                continue
            with self.subTest(literal=literal):
                self.assert_single(fact, {n for n, t in SOURCES.items() if literal in t}, owner)
        for fact, pattern, owner in SINGLE_REGEXES:
            with self.subTest(fact=fact):
                self.assert_single(fact, {n for n, t in SOURCES.items() if re.search(pattern, t)}, owner)

    def test_git_invocation_and_file_listing_have_one_owner(self) -> None:
        for fact, literal, owner in SINGLE_LITERALS:
            if fact not in {"changed-path diff parse", "worktree walk", "ignored directory set", "default branch"}:
                continue
            with self.subTest(literal=literal):
                self.assert_single(fact, {n for n, t in SOURCES.items() if literal in t}, owner)
        self.assertFalse(hasattr(gitinfo, "listed_files"), "core.repository_files is the single file-lister")
        self.assertNotIn("ModuleNotFoundError", "".join(SOURCES.values()), "the tomllib fail-fast is the launcher's")
        self.assertIn("except ModuleNotFoundError", REPOCTL.read_text(encoding="utf-8"))


class TrialGitRoutingTests(Scratch):
    """Trial setup runs git only through gitinfo.run_git (its timeout and quotepath handling)."""

    def test_trial_setup_runs_git_only_through_gitinfo(self) -> None:
        real_run, real_run_git = subprocess.run, gitinfo.run_git
        routed: list[tuple] = []
        raw: list[list[str]] = []

        def spy_run(command, **kwargs):
            if command and command[0] == "git":
                raw.append(list(command))
            return real_run(command, **kwargs)

        def spy_run_git(where, *args, **kwargs):
            routed.append(args)
            return real_run_git(where, *args, **kwargs)

        fake_subprocess = types.SimpleNamespace(
            run=spy_run, TimeoutExpired=subprocess.TimeoutExpired, CompletedProcess=subprocess.CompletedProcess,
        )
        def fake_copy(root, files, target):
            (target / "README.md").write_text("x", encoding="utf-8")  # so the setup commit has content

        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(trial, "subprocess", fake_subprocess), \
                    mock.patch.object(trial, "run_git", spy_run_git), \
                    mock.patch.object(trial, "_run"), mock.patch.object(trial, "_copy", fake_copy):
                trial.prepare(Path(folder), {"id": "demo", "kind": "web", "mode": "new", "prompt": "x"},
                              Path(folder) / "demo")
        self.assertEqual(raw, [], "trial setup must not run git by hand; go through gitinfo.run_git")
        self.assertEqual(len(routed), 5, "init, two configs, add, and commit all route through gitinfo")

    def test_trial_block_is_compiled_from_the_shared_phrases(self) -> None:
        self.assertEqual(trial.BLOCK.pattern, "|".join(re.escape(phrase) for phrase in core.GATE_BLOCK_PHRASES))
        for phrase in core.GATE_BLOCK_PHRASES:
            self.assertTrue(trial.BLOCK.search(phrase))


class VerifyRunsBlockingChecksOnceTests(unittest.TestCase):
    """`verify` runs each blocking check exactly once (issue #49: it used to run them twice)."""

    def test_verify_runs_each_blocking_check_exactly_once(self) -> None:
        counts: dict[str, int] = {}
        restores = []
        for function in vars(kit_checks).values():
            capability = getattr(function, "__capability__", None)
            if isinstance(capability, registry.Capability) and capability.kind == "check":
                fields, original = capability.fields, capability.fields["run"]
                restores.append((fields, original))

                def counted(context, _original=original, _name=capability.name):
                    counts[_name] = counts.get(_name, 0) + 1
                    return _original(context)

                fields["run"] = counted
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / "project.toml").write_text('schema = 1\nname = "demo"\nkind = "cli"\n', encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    try:
                        commands.verify(root, None)
                    except core.RepoctlError:
                        pass  # a bare project has findings; the counting is what this guards
                    before = dict(counts)
                    structure.run_verification(root)  # the surface half of `repoctl verify`
            self.assertTrue(before, "the verify path ran the registry's blocking checks")
            self.assertEqual(counts, before, "run_verification must not re-run the registry's checks")
            self.assertEqual(set(counts.values()), {1}, "each blocking check runs exactly once")
        finally:
            for fields, original in restores:
                fields["run"] = original


if __name__ == "__main__":
    unittest.main()
