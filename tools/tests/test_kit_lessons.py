"""Lessons from the first large project built from the kit (#75, #76, #77).

A clone of the template used as a project kept the template's identity (#75); red CI after a push went
unnoticed while every local gate passed (#76); a parallel session committed another's edits (#77).
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import Scratch  # noqa: E402

from kit import bootstrap, cistatus, product, structure  # noqa: E402
from kit.core import RepoctlError  # noqa: E402

MANIFEST = """\
    schema = 1
    name = "AI_TEMPLATE"
    kind = "template"
    phase = "development"
    owners = ["owner"]

    [repository]
    default_branch = "main"
    github = "owner/AI_TEMPLATE"
    is_template = true

    [template]
    source = "https://github.com/owner/AI_TEMPLATE"
    prune = ["docs/research/**"{extra_prune}]

    [[surfaces]]
    id = "template"
    path = "."
    kind = "template"
    status = "active"
    verification = []
    {surfaces}
"""
OWN_SURFACE = """
    [[surfaces]]
    id = "service"
    path = "service"
    kind = "backend"
    status = "active"
    verification = [["true"]]
"""


class TemplateInUseTests(Scratch):
    def repo(self, origin: str, surfaces: str = OWN_SURFACE, extra_prune: str = "") -> None:
        self.write("project.toml", MANIFEST.format(surfaces=surfaces, extra_prune=extra_prune))
        self.git("init", "-q")
        self.git("remote", "add", "origin", origin)

    def test_a_clone_used_as_a_project_is_named_and_routed_to_init(self) -> None:
        self.repo("https://github.com/someone/my-project.git")
        why = product.template_in_use(self.root)
        self.assertIsNotNone(why)
        self.assertIn("someone/my-project", why)
        self.assertIn("make init", why)
        self.assertIn("service", why)

    def test_the_template_itself_is_not_flagged(self) -> None:
        """Negative case: its own origin is the template source."""
        self.repo("git@github.com:owner/AI_TEMPLATE.git")
        self.assertIsNone(product.template_in_use(self.root))

    def test_a_fork_that_improves_the_template_is_not_flagged(self) -> None:
        """Negative case: a different origin but no surface of its own is template work, not a project."""
        self.repo("https://github.com/someone/AI_TEMPLATE-fork", surfaces="")
        self.assertIsNone(product.template_in_use(self.root))

    def test_prune_never_deletes_a_declared_surface(self) -> None:
        self.repo("https://github.com/someone/my-project", extra_prune=', "service/**"')
        self.write("service/main.py", "print('hi')\n")
        self.write("docs/research/notes.md", "# notes\n")
        self.git("add", "-A")
        from kit.core import load_project
        with self.assertRaises(RepoctlError) as raised:
            bootstrap.prune_template_material(self.root, load_project(self.root))
        self.assertIn("service", str(raised.exception))
        self.assertTrue((self.root / "service/main.py").exists(), "nothing is deleted when prune is refused")


class ProjectReadmeTests(unittest.TestCase):
    TEMPLATE = (
        "# AI_TEMPLATE\n\n<!-- repoctl:template-only -->\nThe template sells itself.\n\n## Why\nBecause.\n"
        "<!-- /repoctl:template-only -->\n\n## Start a project\n\nsteps\n\n<!-- repoctl:project-readme -->\n"
        "> Project initialized: **x** (`web`).\n<!-- /repoctl:project-readme -->\n\n<!-- repoctl:template-only -->\n"
        "## How it stays healthy\nkit prose\n<!-- /repoctl:template-only -->\n\n## Everyday commands\nkeep me\n"
    )

    def test_template_only_sections_leave_and_an_about_section_arrives(self) -> None:
        body = bootstrap.project_readme_body(self.TEMPLATE, "https://github.com/owner/AI_TEMPLATE")
        self.assertNotIn("sells itself", body)
        self.assertNotIn("How it stays healthy", body)
        self.assertIn("## Quick start", body)
        self.assertIn("## About\n\nFILL-IN:", body)
        self.assertIn("## Everyday commands\nkeep me", body)
        self.assertIn("https://github.com/owner/AI_TEMPLATE", body)

    def test_a_readme_without_markers_is_left_alone(self) -> None:
        """Negative case: an adopted project's own README never loses text."""
        own = "# My app\n\nOur own words.\n"
        self.assertEqual(bootstrap.project_readme_body(own, "x"), own)


def runs(*items: dict) -> cistatus.Runner:
    return lambda args: json.dumps(list(items))


class CiStatusTests(unittest.TestCase):
    SHA = "a" * 40

    def status(self, runner: cistatus.Runner) -> tuple[str, str]:
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}):
            return cistatus.ci_status(Path("."), sha=self.SHA, runner=runner)

    def test_a_failed_run_is_red_and_names_the_workflow(self) -> None:
        state, detail = self.status(runs({"workflowName": "ci", "status": "completed", "conclusion": "failure",
                                          "url": "https://x/1"}))
        self.assertEqual(state, "red")
        self.assertIn("ci (failure)", detail)

    def test_green_pending_and_none(self) -> None:
        self.assertEqual(self.status(runs({"workflowName": "ci", "status": "completed", "conclusion": "success"}))[0],
                         "green")
        self.assertEqual(self.status(runs({"workflowName": "ci", "status": "in_progress", "conclusion": ""}))[0],
                         "pending")
        self.assertEqual(self.status(runs())[0], "none")

    def test_without_gh_or_inside_ci_it_says_why_instead_of_failing(self) -> None:
        def missing(args: list[str]) -> str:
            raise FileNotFoundError("gh")
        self.assertEqual(self.status(missing)[0], "unknown")
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            self.assertEqual(cistatus.ci_status(Path("."), sha=self.SHA, runner=runs())[0], "unknown")

    def test_a_session_that_committed_nothing_is_not_blamed(self) -> None:
        """Negative case: a red run that was already there is not this session's finding."""
        red = runs({"workflowName": "ci", "status": "completed", "conclusion": "failure"})
        with mock.patch.object(cistatus, "git", return_value=self.SHA + "\n"), \
             mock.patch.object(cistatus, "pushed_head", return_value=self.SHA):
            self.assertEqual(cistatus.red_findings(Path("."), since=self.SHA[:12], runner=red), [])
            self.assertEqual(len(cistatus.red_findings(Path("."), since="b" * 12, runner=red)), 1)


class SurfaceSetupTests(unittest.TestCase):
    SURFACE = {"id": "web", "setup": [["npm", "ci", "--ignore-scripts"]], "verification": [["npm", "test"]]}

    def test_setup_commands_validate_like_verification(self) -> None:
        self.assertEqual(structure.validation_commands(self.SURFACE, "setup"), [["npm", "ci", "--ignore-scripts"]])
        with self.assertRaises(RepoctlError):
            structure.validation_commands({"id": "web", "setup": [[""]]}, "setup")

    def test_setup_runs_only_inside_ci(self) -> None:
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}):
            self.assertFalse(structure.in_ci())
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            self.assertTrue(structure.in_ci())


class SessionBriefOwnershipTests(Scratch):
    def test_uncommitted_paths_at_start_carry_the_ownership_note(self) -> None:
        from fixtures import build_demo
        build_demo(self.root)  # initialized and committed
        self.write("draft.txt", "someone else's work\n")
        brief = self.cli("hook", "session-start", stdin="{}").stdout
        self.assertIn("not yours unless you made them", brief)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(__import__("fixtures").IN_TEMPLATE, "the template's own records")
class ShippedRecordDigestTests(unittest.TestCase):
    def test_template_records_match_their_shipped_digests(self) -> None:
        """Editing VISION.md or the stack record in the template needs the new digest in [template].records."""
        root = Path(__file__).resolve().parents[2]
        from kit.core import load_project
        project = load_project(root)
        for relative in ("VISION.md", "docs/STACK-DECISION.md"):
            self.assertTrue(bootstrap.shipped(root, project, relative),
                            f"update [template].records for {relative}: shasum -a 256 {relative}")


class CiRedWiringTests(Scratch):
    """Critic finding B1: the check must run inside the real done/stop gate, not only when called directly."""

    def test_the_done_gate_reports_a_red_pushed_head(self) -> None:
        from fixtures import build_demo
        from kit import session
        build_demo(self.root)
        self.git("switch", "-q", "-c", "work")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 2\n")
        self.commit("change")
        red = ("red", "CI failed on abc1234: ci (failure)")
        with mock.patch.object(cistatus, "ci_status", return_value=red):
            findings = session.finish_findings(self.root)
        self.assertTrue(any("[ci-red]" in item for item in findings), findings)
        with mock.patch.object(cistatus, "ci_status", return_value=("green", "ok")):
            self.assertFalse(any("[ci-red]" in item for item in session.finish_findings(self.root)))


@unittest.skipUnless(__import__("fixtures").IN_TEMPLATE, "initializes a copy of the template")
class GraduationInitTests(Scratch):
    """Critic finding B2: following the brief's "run make init" advice must lose no project text."""

    def clone_in_use(self, extra_prune: str = "", edit_vision: bool = True) -> Path:
        import shutil
        from fixtures import git_in
        root = Path(__file__).resolve().parents[2]
        for relative in filter(None, git_in(root, "ls-files", "-z").stdout.split("\0")):
            source = root / relative
            if source.is_file():
                (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, self.root / relative)
        manifest = (self.root / "project.toml").read_text(encoding="utf-8")
        manifest = manifest.replace("prune = [", f"prune = [{extra_prune}", 1)
        manifest += '\n[[surfaces]]\nid = "app"\npath = "app"\nkind = "backend"\nstatus = "active"\nverification = [["true"]]\n'
        (self.root / "project.toml").write_text(manifest, encoding="utf-8")
        self.write("app/main.py", "print('ours')\n")
        vision = self.root / "VISION.md"
        if edit_vision:
            vision.write_text(vision.read_text(encoding="utf-8") + "\nOur own goal: ship the app.\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("remote", "add", "origin", "https://github.com/someone/my-project.git")
        return vision

    def test_init_keeps_the_records_of_a_clone_in_use_and_backs_up_the_readme(self) -> None:
        vision = self.clone_in_use()
        done = self.cli("init", "--name", "my-project", "--kind", "web")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Our own goal: ship the app.", vision.read_text(encoding="utf-8"))
        self.assertTrue((self.root / bootstrap.BACKUP / "README.md").is_file())
        self.assertTrue((self.root / "app/main.py").is_file())

    def test_an_untouched_template_vision_is_reset_not_kept(self) -> None:
        """Critic finding: a clone that never ran kickoff still has the template's vision; it must not become the project's."""
        vision = self.clone_in_use(edit_vision=False)
        done = self.cli("init", "--name", "my-project", "--kind", "web", "--owner", "someone")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = vision.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^Status: pending$")
        self.assertIn("Owner: someone", text)
        self.assertTrue((self.root / bootstrap.BACKUP / "VISION.md").is_file())

    def test_a_kept_record_names_the_new_owner(self) -> None:
        vision = self.clone_in_use()
        done = self.cli("init", "--name", "my-project", "--kind", "web", "--owner", "someone")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Owner: someone", vision.read_text(encoding="utf-8"))
        self.assertIn("REVIEW", done.stdout)

    def test_a_refused_prune_changes_nothing(self) -> None:
        """Negative case: a prune pattern over a surface stops init before its first write."""
        vision = self.clone_in_use(extra_prune='"app/**", ')
        before = vision.read_text(encoding="utf-8"), (self.root / "project.toml").read_text(encoding="utf-8")
        done = self.cli("init", "--name", "my-project", "--kind", "web")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("app/main.py", done.stdout + done.stderr)
        self.assertEqual(before, (vision.read_text(encoding="utf-8"), (self.root / "project.toml").read_text(encoding="utf-8")))
