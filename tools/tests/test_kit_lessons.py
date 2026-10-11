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
