"""Guided init (#110): shared intake, consent-gated apply, preservation, stale plans."""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNER_FILES = ("VISION.md", "docs/STACK-DECISION.md", ".env.example", "project.toml")

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import Scratch, git_in, run_cli, template_only  # noqa: E402  shared builders, in-process CLI, isolated git (#43)

from kit import guided  # noqa: E402
from kit.core import RepoctlError  # noqa: E402

ANSWERS = {
    "users_goal": "Demo for testers; 90% task success",
    "success_metric": "90% task success in the eval",
    "platforms": "web",
    "constraints": "none beyond the template gates",
    "stack": "React + Next.js + Tailwind",
    "stack_alternatives": "SvelteKit lost on ecosystem",
    "stack_verification": "make check and make verify",
    "browser": "off",
    "exa": "off",
    "logging": "local-redacted",
    "embeddings": "off",
}

# The shared answers without the two vetted route choices, so a scenario can set its own.
_BASE_ANSWERS = {key: value for key, value in ANSWERS.items() if key not in ("browser", "exa")}


@template_only  # every test initializes a copy of the uninitialized template
class GuidedInitTests(Scratch):
    def copy_working_tree(self) -> Path:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        files = git_in(ROOT, "ls-files", "-z").stdout.split("\0")
        for relative in filter(None, files):
            source = ROOT / relative
            if source.is_file():
                (directory / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, directory / relative)
        git_in(directory, "init", "-q")
        return directory

    def init_with_json(self, root: Path, answers: dict[str, str], consent: bool = True) -> subprocess.CompletedProcess[str]:
        path = root / "answers.json"
        path.write_text(json.dumps({"consent": consent, "answers": answers}), encoding="utf-8")
        return run_cli(root, "init", "--name", "x", "--kind", "web", "--answers", str(path))

    def assert_same_owner_files(self, root: Path, plain: Path) -> None:
        """Every guided-owned file matches the plain identity-init tree (or is absent from both)."""
        for relative in OWNER_FILES:
            self.assertEqual((root / relative).is_file(), (plain / relative).is_file(), relative)
            if (root / relative).is_file():
                self.assertEqual((root / relative).read_bytes(), (plain / relative).read_bytes(), relative)

    def test_json_and_terminal_answers_produce_identical_owner_files(self) -> None:
        json_root = self.copy_working_tree()
        self.assertEqual(self.init_with_json(json_root, ANSWERS).returncode, 0)
        terminal_root = self.copy_working_tree()
        lines = [ANSWERS[question["id"]] for question in guided.QUESTIONS] + ["y"]
        result = run_cli(terminal_root, "init", "--name", "x", "--kind", "web", "--guided",
                         stdin="\n".join(lines) + "\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for relative in OWNER_FILES:
            self.assertEqual((json_root / relative).read_bytes(), (terminal_root / relative).read_bytes(), relative)

    def test_optional_choices_parity_terminal_vs_json(self) -> None:
        """The four shared choices produce identical owner files via terminal and JSON (off/request).

        `request` is now applied to the vetted route owner's enabled boolean (config only);
        the owner files still match across both surfaces.
        """
        choices = {"browser": "off", "exa": "request", "logging": "plan-external", "embeddings": "request"}
        json_root = self.copy_working_tree()
        self.assertEqual(self.init_with_json(json_root, {**ANSWERS, **choices}).returncode, 0)
        terminal_root = self.copy_working_tree()
        lines = [choices.get(question["id"], ANSWERS[question["id"]]) for question in guided.QUESTIONS]
        result = run_cli(terminal_root, "init", "--name", "x", "--kind", "web", "--guided",
                         stdin="\n".join(lines + ["y"]) + "\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for relative in OWNER_FILES:
            self.assertEqual((json_root / relative).read_bytes(), (terminal_root / relative).read_bytes(), relative)
        manifest = (json_root / "project.toml").read_text(encoding="utf-8")
        self.assertIn('browser = "off"', manifest)
        self.assertIn('exa = "requested"', manifest)  # intent recorded, route file untouched
        self.assertIn('embeddings = "requested-not-ready"', manifest)
        self.assertIn('logging = "plan-external"', manifest)

    def test_cli_json_all_four_choices_prints_plan_metadata(self) -> None:
        """A real first-party CLI run with all four choices prints the plan/metadata; no lingering process."""
        root = self.copy_working_tree()
        choices = {"browser": "request", "exa": "off", "logging": "local-redacted", "embeddings": "request"}
        path = root / "answers.json"
        path.write_text(json.dumps({"consent": True, "answers": {**ANSWERS, **choices}}), encoding="utf-8")
        result = run_cli(root, "init", "--name", "x", "--kind", "web", "--answers", str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Applied", result.stdout)
        self.assertIn("browser requested", result.stdout)
        self.assertIn("exa off", result.stdout)
        self.assertIn("embeddings requested-not-ready", result.stdout)
        self.assertIn("logging local-redacted", result.stdout)
        self.assertIn("[guided]", (root / "project.toml").read_text(encoding="utf-8"))

    def test_terminal_cancel_writes_nothing(self) -> None:
        root = self.copy_working_tree()
        plain = self.copy_working_tree()
        self.assertEqual(run_cli(plain, "init", "--name", "x", "--kind", "web").returncode, 0)
        result = run_cli(root, "init", "--name", "x", "--kind", "web", "--guided", stdin="cancel\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Cancelled", result.stdout)
        self.assert_same_owner_files(root, plain)

    def test_missing_consent_writes_nothing(self) -> None:
        root = self.copy_working_tree()
        plain = self.copy_working_tree()
        self.assertEqual(run_cli(plain, "init", "--name", "x", "--kind", "web").returncode, 0)
        result = self.init_with_json(root, ANSWERS, consent=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NOT applied", result.stdout)
        self.assert_same_owner_files(root, plain)

    def test_accepted_records_are_preserved_unless_an_explicit_reshape_is_supplied(self) -> None:
        root = self.copy_working_tree()
        self.assertEqual(self.init_with_json(root, ANSWERS).returncode, 0)
        accepted = (root / "VISION.md").read_text(encoding="utf-8").replace("Status: pending", "Status: accepted", 1)
        (root / "VISION.md").write_text(accepted, encoding="utf-8")
        plan = guided.build_plan(root, ANSWERS, consent=True)
        self.assertEqual(guided.apply_plan(root, plan), ["project.toml"])  # only the facts refresh; records untouched
        self.assertEqual((root / "VISION.md").read_text(encoding="utf-8"), accepted)  # accepted record preserved
        reshaped = guided.build_plan(root, {**ANSWERS, "users_goal": "Reshaped goal"}, consent=True, reshape=True)
        self.assertIn("VISION.md", guided.apply_plan(root, reshaped))
        text = (root / "VISION.md").read_text(encoding="utf-8")
        self.assertIn("Status: accepted", text)  # reshape never confirms; product-kickoff owns acceptance
        self.assertIn("Reshaped goal", text)
        self.assertNotIn("Demo for testers", text)  # a reshape replaces the earlier draft, never duplicates it

    def test_string_typed_consent_is_rejected_before_any_guided_write(self) -> None:
        root = self.copy_working_tree()
        plain = self.copy_working_tree()
        self.assertEqual(run_cli(plain, "init", "--name", "x", "--kind", "web").returncode, 0)
        answers = {"consent": "false", "answers": ANSWERS}  # a typed string is a refusal, never consent
        path = root / "answers.json"
        path.write_text(json.dumps(answers), encoding="utf-8")
        result = run_cli(root, "init", "--name", "x", "--kind", "web", "--answers", str(path))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("boolean", result.stderr)
        self.assert_same_owner_files(root, plain)  # identity init stands; no guided draft or [guided] facts

    def test_string_typed_reshape_is_rejected_before_any_guided_write(self) -> None:
        root = self.copy_working_tree()
        plain = self.copy_working_tree()
        self.assertEqual(run_cli(plain, "init", "--name", "x", "--kind", "web").returncode, 0)
        answers = {"consent": True, "reshape": "false", "answers": ANSWERS}
        path = root / "answers.json"
        path.write_text(json.dumps(answers), encoding="utf-8")
        result = run_cli(root, "init", "--name", "x", "--kind", "web", "--answers", str(path))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("boolean", result.stderr)
        self.assert_same_owner_files(root, plain)  # valid consent still fails: reshape is mistyped

    def test_stale_plan_refuses_and_writes_nothing(self) -> None:
        root = self.copy_working_tree()
        self.assertEqual(self.init_with_json(root, ANSWERS).returncode, 0)
        plan = guided.build_plan(root, {**ANSWERS, "users_goal": "Changed after the plan"}, consent=True)
        path = root / "VISION.md"
        # Drift before the lock: refused by the pre-lock check, the edit stands.
        path.write_text(path.read_text(encoding="utf-8") + "\nAn edit after the plan was built.\n", encoding="utf-8")
        with self.assertRaises(RepoctlError) as raised:
            guided.apply_plan(root, plan)
        self.assertIn("stale", str(raised.exception))
        self.assertIn("An edit after the plan was built.", path.read_text(encoding="utf-8"))
        # Drift under the lock: the authoritative in-lock check must refuse the same
        # way, so an owner edit while an apply waits is never overwritten.
        plan = guided.build_plan(root, {**ANSWERS, "users_goal": "Changed after the plan"}, consent=True)
        original_lock = guided._lock

        @contextlib.contextmanager
        def drifting_lock(locked_root: Path, timeout: float = 10):
            with original_lock(locked_root, timeout=timeout):
                path.write_text(path.read_text(encoding="utf-8")
                                + "\nAn edit while the apply held the lock.\n", encoding="utf-8")
                yield

        guided._lock = drifting_lock
        try:
            with self.assertRaises(RepoctlError) as raised:
                guided.apply_plan(root, plan)
        finally:
            guided._lock = original_lock
        self.assertIn("stale", str(raised.exception))
        manifest = (root / "project.toml").read_text(encoding="utf-8")
        self.assertNotIn("Changed after the plan", manifest)  # nothing written under the drifted plan
        self.assertIn("An edit while the apply held the lock.", path.read_text(encoding="utf-8"))

    def test_concurrent_apply_callers_serialize(self) -> None:
        root = self.copy_working_tree()
        self.assertEqual(self.init_with_json(root, ANSWERS).returncode, 0)
        plan = guided.build_plan(root, ANSWERS, consent=True)
        with guided._lock(root, timeout=0.2):
            with self.assertRaises(RepoctlError) as raised:
                guided.apply_plan(root, plan)
        self.assertIn(guided.LOCK, str(raised.exception))

    def test_unattended_init_is_unchanged_by_guided_intake(self) -> None:
        root = self.copy_working_tree()
        self.assertEqual(run_cli(root, "init", "--name", "x", "--kind", "web").returncode, 0)
        manifest = (root / "project.toml").read_text(encoding="utf-8")
        self.assertNotIn("[guided]", manifest)
        self.assertFalse((root / ".env.example").exists())
        self.assertIn("Status: pending", (root / "VISION.md").read_text(encoding="utf-8"))

    def test_guided_initialized_repository_is_not_rebootstrapped(self) -> None:
        root = self.copy_working_tree()
        self.assertEqual(self.init_with_json(root, ANSWERS).returncode, 0)
        result = run_cli(root, "init", "--name", "y", "--kind", "web")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already initialized", result.stdout + result.stderr)

    def test_no_provider_browser_or_install_calls(self) -> None:
        """The owner apply edits config only: no process, network, package, or browser call.

        The vetted route-name stem ("playwright") is a config reference, not a call; the
        forbidden tokens are the execution/install forms.
        """
        source = (ROOT / "tools/kit/guided.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "urllib", "requests", "npx", "pip install",
                          "@playwright", "playwright install", "import playwright"):
            self.assertNotIn(forbidden, source)

    def test_route_owners_keep_mcp_enablement(self) -> None:
        """Explicit choices apply to the vetted owners; other routes stay route-owned."""
        root = self.copy_working_tree()
        self.assertEqual(self.init_with_json(root, ANSWERS).returncode, 0)  # browser/exa = off
        mcp = root / ".agents/mcp"
        self.assertIn("enabled = false", (mcp / "playwright.toml").read_text(encoding="utf-8"))
        self.assertIn("enabled = false", (mcp / "exa.toml").read_text(encoding="utf-8"))
        self.assertIn("enabled = true", (mcp / "context7.toml").read_text(encoding="utf-8"))  # route-owned
        # The [guided] derived mirror matches the owners: no second SOT.
        manifest = (root / "project.toml").read_text(encoding="utf-8")
        self.assertIn('playwright = "off-recommended"', manifest)
        self.assertIn('exa = "off-recommended"', manifest)
        self.assertIn('context7 = "preserved"', manifest)
        self.assertEqual((root / ".env.example").read_text(encoding="utf-8").count("<set-your-own-key>"), 2)

    def test_preserved_route_url_drift_refuses_before_any_write(self) -> None:
        """The plan binds every vetted route's raw hash: preserved URL drift refuses all writes."""
        root = self.copy_working_tree()
        self.assertEqual(run_cli(root, "init", "--name", "x", "--kind", "web").returncode, 0)
        plan = guided.build_plan(root, {**_BASE_ANSWERS, "browser": "preserve", "exa": "preserve"}, consent=True)
        route = root / ".agents/mcp/exa.toml"
        drifted = route.read_text(encoding="utf-8").replace("https://mcp.exa.ai/mcp", "https://drifted.example/mcp")
        route.write_text(drifted, encoding="utf-8")  # URL edit after the plan was built
        with self.assertRaises(RepoctlError) as raised:
            guided.apply_plan(root, plan)
        self.assertIn("stale", str(raised.exception))
        self.assertIn("exa.toml", str(raised.exception))
        self.assertEqual(route.read_text(encoding="utf-8"), drifted)  # preserve wrote nothing
        self.assertNotIn("[guided]", (root / "project.toml").read_text(encoding="utf-8"))
        self.assertFalse((root / ".env.example").exists())  # and no other guided write happened


if __name__ == "__main__":
    unittest.main()
