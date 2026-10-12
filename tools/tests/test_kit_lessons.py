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


class ReadmeTemplateSectionsTests(Scratch):
    def test_an_initialized_readme_with_template_sections_is_listed(self) -> None:
        self.write("README.md", "# app\n\n## Why\ntemplate prose\n\n## Start a project\nx\n")
        project = {"name": "app", "repository": {"is_template": False}}
        self.assertEqual(structure.readme_template_sections(self.root, project), ["## Why", "## Start a project"])

    def test_the_template_and_a_clean_project_readme_are_not_listed(self) -> None:
        """Negative case: the template keeps its sections; a project README without them is clean."""
        self.write("README.md", "# app\n\n## Why\n")
        self.assertEqual(structure.readme_template_sections(self.root, {"name": "x", "repository": {"is_template": True}}), [])
        self.write("README.md", "# app\n\n## About\nours\n")
        self.assertEqual(structure.readme_template_sections(self.root, {"name": "app"}), [])


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

    def test_issue_events_do_not_turn_successful_push_verification_red(self) -> None:
        """#97: issue validation shares a SHA, not the commit verification contract."""
        for event in ("issues", "issue_comment"):
            with self.subTest(event=event):
                state, detail = self.status(runs(
                    {"workflowName": "ci", "event": "push", "status": "completed", "conclusion": "success"},
                    {"workflowName": "Issue contract", "event": event, "status": "completed",
                     "conclusion": "failure", "url": "https://x/issue"},
                ))
                self.assertEqual(state, "green")
                self.assertNotIn("Issue contract", detail)

    def test_real_verification_failures_stay_red_with_unrelated_issue_success(self) -> None:
        for event in ("push", "pull_request", "pull_request_target", "workflow_dispatch", "schedule", None):
            with self.subTest(event=event):
                state, detail = self.status(runs(
                    {"workflowName": "verification", "event": event, "status": "completed",
                     "conclusion": "failure", "url": "https://x/real-failure"},
                    {"workflowName": "Issue contract", "event": "issues", "status": "completed",
                     "conclusion": "success"},
                ))
                self.assertEqual(state, "red")
                self.assertIn("verification (failure) https://x/real-failure", detail)

    def test_issue_only_results_have_no_applicable_commit_verification(self) -> None:
        for event in ("issues", "issue_comment"):
            for status, conclusion in (("completed", "success"), ("completed", "failure"), ("queued", "")):
                with self.subTest(event=event, status=status, conclusion=conclusion):
                    state, detail = self.status(runs(
                        {"workflowName": "Issue contract", "event": event, "status": status,
                         "conclusion": conclusion},
                    ))
                    self.assertEqual(state, "none")
                    self.assertIn("no applicable commit verification", detail)

    def test_query_requests_event_and_ignores_pending_issue_validation(self) -> None:
        calls = []
        def runner(args: list[str]) -> str:
            calls.append(args)
            return json.dumps([
                {"workflowName": "ci", "event": "push", "status": "completed", "conclusion": "success"},
                {"workflowName": "Issue contract", "event": "issue_comment", "status": "in_progress"},
            ])
        self.assertEqual(self.status(runner)[0], "green")
        self.assertIn("event", calls[0][calls[0].index("--json") + 1].split(","))

    def test_green_pending_and_none(self) -> None:
        self.assertEqual(self.status(runs({"workflowName": "ci", "status": "completed", "conclusion": "success"}))[0],
                         "green")
        self.assertEqual(self.status(runs({"workflowName": "ci", "status": "in_progress", "conclusion": ""}))[0],
                         "pending")
        self.assertEqual(self.status(runs())[0], "none")
        cancelled = runs({"workflowName": "ci", "status": "completed", "conclusion": "cancelled"})
        self.assertEqual(self.status(cancelled)[0], "inconclusive", "cancelled is not a pass")

    def test_without_gh_or_inside_ci_it_says_why_instead_of_failing(self) -> None:
        def missing(args: list[str]) -> str:
            raise FileNotFoundError("gh")
        self.assertEqual(self.status(missing)[0], "unknown")
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            self.assertEqual(cistatus.ci_status(Path("."), sha=self.SHA, runner=runs())[0], "unknown")

    def test_a_session_that_committed_nothing_is_not_blamed(self) -> None:
        """Negative case: a red run that was already there is not this session's finding."""
        red = runs({"workflowName": "ci", "status": "completed", "conclusion": "failure"})
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "git", return_value=self.SHA + "\n"), \
             mock.patch.object(cistatus, "pushed_head", return_value=self.SHA):
            self.assertEqual(cistatus.red_findings(Path("."), since=self.SHA[:12], runner=red), [])
            self.assertEqual(len(cistatus.red_findings(Path("."), since="b" * 12, runner=red)), 1)


class SurfaceSetupTests(unittest.TestCase):
    SURFACE = {"id": "web", "setup": [["npm", "ci", "--ignore-scripts"]], "verification": [["npm", "test"]]}

    def test_setup_commands_validate_like_verification(self) -> None:
        self.assertEqual(structure.validation_commands(self.SURFACE, "setup"), [["npm", "ci", "--ignore-scripts"]])
        with self.assertRaises(RepoctlError):
            structure.validation_commands({"id": "web", "setup": [[""]]}, "setup")

    def test_setup_runs_only_on_the_workflow_opt_in(self) -> None:
        """#84: CI=true alone (a local tool may export it) never runs installs."""
        with mock.patch.dict(os.environ, {"REPOCTL_SETUP": "", "CI": "true", "GITHUB_ACTIONS": "true"}):
            self.assertFalse(structure.in_ci())
        with mock.patch.dict(os.environ, {"REPOCTL_SETUP": "1"}):
            self.assertTrue(structure.in_ci())


class CiCacheTests(Scratch):
    """#83: one gh call per commit; an offline answer is not asked again on every gate."""

    def counting(self, *items: dict):
        calls = []
        def runner(args: list[str]) -> str:
            calls.append(args)
            return json.dumps(list(items))
        return calls, (lambda root: runner)

    def test_brief_reports_head_and_default_from_one_session_cached_query(self) -> None:
        """#83: green HEAD and pending default are visible, not only failures."""
        from kit import session
        head, default = "a" * 40, "b" * 40
        self.write("project.toml", 'schema = 1\nname = "x"\nkind = "template"\n[repository]\ndefault_branch = "trunk"\n')
        self.write(".agent/hook-state.json", json.dumps({"session": "real-hook-session"}))
        calls, factory = self.counting(
            {"headSha": head, "event": "push", "workflowName": "ci", "status": "completed", "conclusion": "success"},
            {"headSha": default, "event": "push", "workflowName": "ci", "status": "in_progress"},
        )
        def refs(root, *args):
            return head if args[-1] == "HEAD" else default
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "pushed_head", return_value=head), \
             mock.patch.object(cistatus, "git", side_effect=refs), \
             mock.patch.object(cistatus, "_gh_runner", side_effect=lambda root, **kwargs: factory(root)), \
             mock.patch.object(structure, "template_in_use", return_value=None):
            first = session._attention(self.root, "real-hook-session")
            self.assertTrue(any("HEAD" in line and "green" in line for line in first), first)
            self.assertTrue(any("default branch trunk" in line and "pending" in line for line in first), first)
            self.assertEqual(session._attention(self.root, "real-hook-session"), first)
        self.assertEqual(len(calls), 1)

    def test_new_session_with_unwritable_snapshot_does_not_replay_previous_session_green(self) -> None:
        """#83: the current lifecycle invocation owns cache identity even when persistence fails."""
        import contextlib
        import io
        from kit import session
        self.write("project.toml", 'schema = 1\nname = "x"\nkind = "template"\n[repository]\ndefault_branch = "trunk"\n')
        self.write(".gitignore", ".agent/\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")
        sha = self.git("rev-parse", "HEAD").strip()
        self.git("remote", "add", "origin", "https://github.com/example/project.git")
        self.git("update-ref", "refs/remotes/origin/trunk", sha)
        self.git("branch", "--set-upstream-to=origin/trunk")
        calls = []
        def runner(args):
            calls.append(args)
            return json.dumps([{"headSha": sha, "event": "push", "status": "completed",
                                "conclusion": "success" if len(calls) == 1 else "failure"}])
        state = session.state_path(self.root)
        original_write = Path.write_text
        denied = []
        def cannot_save_baseline(path, *args, **kwargs):
            if path == state:
                denied.append(path)
                raise PermissionError("session baseline is unwritable")
            return original_write(path, *args, **kwargs)
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "_gh_runner", return_value=runner), \
             mock.patch.object(session, "_pull_at_start", return_value=[]), \
             mock.patch.object(session, "_heal_derived", return_value=[]), \
             mock.patch.object(session, "repository_findings", return_value=[]), \
             mock.patch.object(session, "install_git_hooks", return_value=None), \
             mock.patch.object(session, "print_map"), \
             mock.patch.object(session, "self_heal_errors", side_effect=lambda root: []), \
             mock.patch.object(session, "_product_on", return_value=False), \
             mock.patch.object(session, "project_plugin_files", return_value=[]), \
             mock.patch.object(structure, "template_in_use", return_value=None):
            with contextlib.redirect_stdout(io.StringIO()):
                session._session_start(self.root, {"session_id": "previous-host-session"})
            self.assertEqual(json.loads(state.read_text())["session"], "previous-host-session")
            output = io.StringIO()
            with mock.patch.object(Path, "write_text", cannot_save_baseline), contextlib.redirect_stdout(output):
                session._session_start(self.root, {"session_id": "current-host-session"})
            self.assertEqual(len(denied), 1, "real snapshot persistence was attempted and failed")
            self.assertIn("HEAD: red", output.getvalue())
            self.assertIn("default branch trunk (as of the last fetch): red", output.getvalue())
            self.assertEqual(len(calls), 2, "new invocation does not reuse previous host's diagnostic snapshot")
            resumed = io.StringIO()
            with mock.patch.object(Path, "write_text", cannot_save_baseline), contextlib.redirect_stdout(resumed):
                session._session_start(self.root, {"session_id": "current-host-session"})
            self.assertEqual(len(denied), 2)
            self.assertEqual(len(calls), 2, "same current host/pair is still reused despite failed baseline persistence")
            self.assertIn("HEAD: red", resumed.getvalue())
            self.assertNotIn("HEAD: green", resumed.getvalue())

    def brief_fixture(self):
        self.write("project.toml", 'schema = 1\nname = "x"\nkind = "template"\n[repository]\ndefault_branch = "trunk"\n')
        return "a" * 40, "b" * 40, "host-session"

    def test_brief_session_cache_survives_retry_window_but_requeries_changed_targets(self) -> None:
        import time
        head, default, identity = self.brief_fixture()
        calls, factory = self.counting({"headSha": head, "event": "push", "status": "completed", "conclusion": "success"})
        def refs(root, *args):
            return head if args[-1] == "HEAD" else default
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "pushed_head", side_effect=lambda root: head), \
             mock.patch.object(cistatus, "git", side_effect=refs):
            first = cistatus.brief_ci_lines(self.root, identity, factory(self.root))
            with mock.patch("time.time", return_value=time.time() + cistatus.GREEN_S + 1):
                self.assertEqual(cistatus.brief_ci_lines(self.root, identity, factory(self.root)), first)
            self.assertEqual(len(calls), 1, "same actual session/target pair does not ask again")
            default = "c" * 40
            cistatus.brief_ci_lines(self.root, identity, factory(self.root))
            head = "d" * 40
            cistatus.brief_ci_lines(self.root, identity, factory(self.root))
            identity = "next-host-session"
            cistatus.brief_ci_lines(self.root, identity, factory(self.root))
        self.assertEqual(len(calls), 4)

    def test_brief_without_real_hook_identity_uses_bounded_fallback_cache(self) -> None:
        import time
        head, default, identity = self.brief_fixture()
        identity = "local"
        calls, factory = self.counting()
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "pushed_head", return_value=head), \
             mock.patch.object(cistatus, "git", side_effect=lambda root, *args: head if args[-1] == "HEAD" else default):
            cistatus.brief_ci_lines(self.root, identity, factory(self.root))
            cistatus.brief_ci_lines(self.root, identity, factory(self.root))
            self.assertEqual(len(calls), 1)
            with mock.patch("time.time", return_value=time.time() + cistatus.RETRY_S + 1):
                cistatus.brief_ci_lines(self.root, identity, factory(self.root))
        self.assertEqual(len(calls), 2, "local is not a real host session ID")

    def test_brief_preserves_event_failure_scope_and_omitted_targets_are_none(self) -> None:
        head, default, identity = self.brief_fixture()
        for index, (items, expected_head, expected_default) in enumerate((
            ([{"headSha": head, "event": "push", "status": "completed", "conclusion": "success"},
              {"headSha": default, "event": "pull_request", "status": "completed", "conclusion": "failure"}], "green", "red"),
            ([{"headSha": head, "status": "completed", "conclusion": "failure"},
              {"headSha": default, "event": "push", "status": "queued"}], "red", "pending"),
            ([{"headSha": default, "event": "issues", "status": "completed", "conclusion": "success"},
              {"headSha": default, "event": "issue_comment", "status": "completed", "conclusion": "failure"}], "none", "none"),
            ([{"headSha": "f" * 40, "event": "push", "status": "completed", "conclusion": "success"}] * 100, "none", "none"),
        )):
            with self.subTest(index=index), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
                 mock.patch.object(cistatus, "pushed_head", return_value=head), \
                 mock.patch.object(cistatus, "git", side_effect=lambda root, *args: head if args[-1] == "HEAD" else default):
                identity = f"scope-case-{index}"
                lines = cistatus.brief_ci_lines(self.root, identity, runs(*items))
                self.assertIn(f"HEAD: {expected_head}", lines[0])
                self.assertIn(f": {expected_default} —", lines[1])

    def test_brief_missing_default_ref_and_unpushed_head_never_claim_green(self) -> None:
        head, default, identity = self.brief_fixture()
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "pushed_head", return_value=None), \
             mock.patch.object(cistatus, "git", side_effect=lambda root, *args: head if args[-1] == "HEAD" else None):
            runner = mock.Mock()
            lines = cistatus.brief_ci_lines(self.root, identity, runner)
            self.assertIn("HEAD: unpushed", lines[0])
            self.assertIn(": unknown —", lines[1])
            runner.assert_not_called()

    def test_brief_failures_are_unknown_and_do_not_poison_targeted_results(self) -> None:
        head, default, identity = self.brief_fixture()
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "pushed_head", return_value=head), \
             mock.patch.object(cistatus, "git", side_effect=lambda root, *args: head if args[-1] == "HEAD" else default):
            for index, response in enumerate(("not-json", "{}", "null")):
                identity = f"invalid-input-{index}"
                lines = cistatus.brief_ci_lines(self.root, identity, lambda args: response)
                self.assertTrue(all("unknown" in line for line in lines), lines)
            identity = "green-brief-session"
            lines = cistatus.brief_ci_lines(self.root, identity, runs(
                {"headSha": head, "event": "push", "status": "completed", "conclusion": "success"},
            ))
            self.assertIn("HEAD: green", lines[0])
            self.assertFalse((self.root / cistatus.CACHE).exists(), "brief never seeds targeted cache")
            failure = runs({"event": "push", "workflowName": "real CI", "status": "completed", "conclusion": "failure"})
            with mock.patch.object(cistatus, "_gh_runner", return_value=failure):
                self.assertEqual(cistatus.ci_status(self.root, sha=head)[0], "red")
                self.assertEqual(len(cistatus.red_findings(self.root)), 1)

    def test_slow_offline_cli_is_bounded_and_not_repeated_in_known_session(self) -> None:
        import time
        head, default, identity = self.brief_fixture()
        script = self.write("fake-bin/gh", "#!/bin/sh\nexec /bin/sleep 2\n")
        script.chmod(0o755)
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": "", "PATH": str(script.parent)}), \
             mock.patch.object(cistatus, "pushed_head", return_value=head), \
             mock.patch.object(cistatus, "git", side_effect=lambda root, *args: head if args[-1] == "HEAD" else default), \
             mock.patch.object(cistatus, "BRIEF_TIMEOUT_S", 0.2), \
             mock.patch.object(cistatus.subprocess, "run", wraps=cistatus.subprocess.run) as invocation:
            started = time.monotonic()
            first = cistatus.brief_ci_lines(self.root, identity)
            second = cistatus.brief_ci_lines(self.root, identity)
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertTrue(all("unknown" in line for line in first), first)
            self.assertEqual(second, first)
        self.assertEqual(invocation.call_count, 1)
        self.assertEqual(invocation.call_args.kwargs["timeout"], 0.2)

    def test_missing_cli_and_same_head_default_snapshot_are_explicit(self) -> None:
        head, default, identity = self.brief_fixture()
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "pushed_head", return_value=head), \
             mock.patch.object(cistatus, "git", return_value=head):
            missing = mock.Mock(side_effect=FileNotFoundError("gh"))
            lines = cistatus.brief_ci_lines(self.root, identity, missing)
            self.assertTrue(all("unknown" in line for line in lines), lines)
            self.assertEqual(cistatus.brief_ci_lines(self.root, identity, missing), lines)
            self.assertEqual(missing.call_count, 1)
            identity = "next-session"
            runner = mock.Mock(return_value=json.dumps([
                {"headSha": head, "event": "push", "status": "completed", "conclusion": "success"},
            ]))
            lines = cistatus.brief_ci_lines(self.root, identity, runner)
            self.assertTrue(all("green" in line for line in lines), lines)
            self.assertEqual(runner.call_count, 1)

    def test_a_final_answer_is_asked_once_per_commit(self) -> None:
        calls, factory = self.counting({"workflowName": "ci", "status": "completed", "conclusion": "success"})
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "_gh_runner", factory):
            self.assertEqual(cistatus.ci_status(self.root, sha="c" * 40)[0], "green")
            self.assertEqual(cistatus.ci_status(self.root, sha="c" * 40)[0], "green")
        self.assertEqual(len(calls), 1)

    def test_pre_event_scope_cache_is_requeried_and_replaced(self) -> None:
        """#97: old false green/red/pending results must not outlive event classification."""
        import time
        sha = "7" * 40
        (self.root / ".agent").mkdir()
        for old_state, items, expected in (
            ("red", [{"event": "push", "status": "completed", "conclusion": "success"}], "green"),
            ("green", [{"event": "issues", "status": "completed", "conclusion": "success"}], "none"),
            ("pending", [{"event": "push", "status": "completed", "conclusion": "failure",
                          "workflowName": "ci"}], "red"),
        ):
            with self.subTest(old_state=old_state):
                (self.root / cistatus.CACHE).write_text(json.dumps({sha: [old_state, "old result", time.time()]}))
                calls, factory = self.counting(*items)
                with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
                     mock.patch.object(cistatus, "_gh_runner", factory):
                    self.assertEqual(cistatus.ci_status(self.root, sha=sha)[0], expected)
                    self.assertEqual(cistatus.ci_status(self.root, sha=sha)[0], expected)
                self.assertEqual(len(calls), 1, "old scope is invalidated; new scope is cached")

    def test_a_green_answer_is_asked_again_after_a_day(self) -> None:
        """#85: a later failing re-run or a new workflow on the same commit becomes visible."""
        calls, factory = self.counting({"workflowName": "ci", "status": "completed", "conclusion": "success"})
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "_gh_runner", factory):
            cistatus.ci_status(self.root, sha="f" * 40)
            with mock.patch("time.time", return_value=__import__("time").time() + cistatus.GREEN_S + 1):
                cistatus.ci_status(self.root, sha="f" * 40)
        self.assertEqual(len(calls), 2)

    def test_a_pending_answer_is_asked_again_after_the_retry_window(self) -> None:
        calls, factory = self.counting({"workflowName": "ci", "status": "in_progress", "conclusion": ""})
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "_gh_runner", factory):
            cistatus.ci_status(self.root, sha="d" * 40)
            cistatus.ci_status(self.root, sha="d" * 40)
            self.assertEqual(len(calls), 1, "within the window: cached")
            with mock.patch("time.time", return_value=__import__("time").time() + cistatus.RETRY_S + 1):
                cistatus.ci_status(self.root, sha="d" * 40)
        self.assertEqual(len(calls), 2)


class CiCacheRedTests(Scratch):
    def test_a_cached_red_is_asked_again_by_the_gate(self) -> None:
        """Critic finding: a re-run that turned the same commit green must clear the gate."""
        import time
        sha = "e" * 40
        (self.root / ".agent").mkdir()
        (self.root / cistatus.CACHE).write_text(json.dumps({sha: ["red", "CI failed", time.time() - 86400, cistatus.CACHE_SCOPE]}))
        green = lambda root: (lambda args: json.dumps([{"workflowName": "ci", "status": "completed",
                                                        "conclusion": "success"}]))
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}), \
             mock.patch.object(cistatus, "_gh_runner", green), \
             mock.patch.object(cistatus, "pushed_head", return_value=sha), \
             mock.patch.object(cistatus, "git", return_value=sha + "\n"):
            self.assertEqual(cistatus.red_findings(self.root), [])
            self.assertEqual(cistatus.ci_status(self.root, sha=sha)[0], "green")


class ShippedCrlfTests(Scratch):
    def test_a_crlf_checkout_still_matches_the_shipped_digest(self) -> None:
        import hashlib
        self.write("VISION.md", "Project: x\nline\n")
        digest = "sha256:" + hashlib.sha256(b"Project: x\nline\n").hexdigest()
        (self.root / "VISION.md").write_bytes(b"Project: x\r\nline\r\n")
        self.assertTrue(bootstrap.shipped(self.root, {"template": {"records": {"VISION.md": digest}}}, "VISION.md"))
        (self.root / "VISION.md").write_bytes(b"Project: x\r\nour own line\r\n")
        self.assertFalse(bootstrap.shipped(self.root, {"template": {"records": {"VISION.md": digest}}}, "VISION.md"))


class CiCacheDamageTests(Scratch):
    def test_a_damaged_cache_entry_is_asked_again_not_trusted(self) -> None:
        """A non-numeric timestamp in the cache must never break the session brief."""
        sha = "9" * 40
        (self.root / ".agent").mkdir()
        (self.root / cistatus.CACHE).write_text(json.dumps({sha: ["green", "ok", "not-a-time", cistatus.CACHE_SCOPE]}))
        self.assertIsNone(cistatus._cached(self.root, sha))


class PruneBackupTests(Scratch):
    def test_pruned_files_move_into_the_backup(self) -> None:
        """#82: an undeclared project folder listed in prune is kept in the ignored backup, not lost."""
        self.write("project.toml", 'schema = 1\nname = "x"\nkind = "template"\n[template]\nprune = ["notes/**"]\n')
        self.write("notes/idea.md", "# our idea\n")
        self.git("init", "-q")
        self.git("add", "-A")
        from kit.core import load_project
        removed = bootstrap.prune_template_material(self.root, load_project(self.root))
        self.assertEqual(removed, ["notes/idea.md"])
        self.assertFalse((self.root / "notes/idea.md").exists())
        self.assertEqual((self.root / bootstrap.BACKUP / "notes/idea.md").read_text(encoding="utf-8"), "# our idea\n")


class SessionBriefOwnershipTests(Scratch):
    def test_uncommitted_paths_at_start_carry_the_ownership_note(self) -> None:
        from fixtures import build_demo
        build_demo(self.root)  # initialized and committed
        self.write("draft.txt", "someone else's work\n")
        brief = self.cli("hook", "session-start", stdin="{}").stdout
        self.assertIn("not yours unless you made them", brief)



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

    def test_graduation_locks_only_kit_files_so_a_later_update_keeps_the_project(self) -> None:
        """Critic finding: init in a clone once locked the project's own files as kit, and the next kit-update
        deleted them. The lock now lists only what tools/kit-files.json names."""
        import json as _json
        self.clone_in_use()
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "clone in use")
        done = self.cli("init", "--name", "my-project", "--kind", "web")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lock = _json.loads((self.root / "tools/kit-lock.json").read_text(encoding="utf-8"))
        # Review finding: a clone may have edited kit files before init, so their content is not what the kit
        # shipped; the first kit-update compares them with the template's history instead (empty lock).
        self.assertEqual(lock["files"], {})
        from kit import kitreport
        self.write("app/main.py", "print('changed')\n")
        self.assertEqual(kitreport.upstream_findings(self.root, ["app/main.py"]), [], "project code is not kit")
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init and edit")
        update = self.cli("kit-update", "--kit", str(Path(__file__).resolve().parents[2]))
        self.assertEqual(update.returncode, 0, update.stdout + update.stderr)
        self.assertTrue((self.root / "app/main.py").is_file(), update.stdout)

    def test_graduation_keeps_the_lock_an_earlier_kit_update_wrote(self) -> None:
        """Review finding: init once replaced the lock of the advised pre-init kit-update with current digests."""
        import json as _json
        self.clone_in_use()
        earlier = {"kit_version": "abc123", "files": {"tools/kit/core.py": "0" * 64}, "bases": {"x": "1" * 64}}
        self.write("tools/kit-lock.json", _json.dumps(earlier))
        done = self.cli("init", "--name", "my-project", "--kind", "web")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(_json.loads((self.root / "tools/kit-lock.json").read_text(encoding="utf-8")), earlier)

    def test_prune_never_touches_a_surface_extra_path(self) -> None:
        """Review finding: a surface's extra_paths (a root index.html) were not protected from the prune."""
        project = {"template": {"prune": ["index.html", "docs/old.md"]},
                   "surfaces": [{"id": "web", "path": "app", "kind": "web", "extra_paths": ["index.html"]}]}
        self.write("index.html", "<html></html>\n")
        self.write("docs/old.md", "# old\n")
        self.git("init", "-q")
        self.git("add", "-A")
        with self.assertRaises(RepoctlError):
            bootstrap.guard_prune(project, ["index.html"])
        bootstrap.guard_prune(project, ["docs/old.md"])  # negative: template material is still pruned
        self.assertEqual(bootstrap.drop_surface_prune(self.root, project)["template"]["prune"], ["docs/old.md"])

    def test_graduation_does_not_record_the_projects_own_head_as_kit_version(self) -> None:
        import json as _json
        self.clone_in_use()
        done = self.cli("init", "--name", "my-project", "--kind", "web")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lock = _json.loads((self.root / "tools/kit-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["kit_version"], "unknown")

    def test_a_clone_without_the_kit_list_is_told_to_update_first(self) -> None:
        """Negative case: without tools/kit-files.json init refuses before any write and names kit-update."""
        vision = self.clone_in_use()
        (self.root / "tools/kit-files.json").unlink()
        before = vision.read_text(encoding="utf-8")
        done = self.cli("init", "--name", "my-project", "--kind", "web")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("make kit-update", done.stdout + done.stderr)
        self.assertEqual(before, vision.read_text(encoding="utf-8"))

    def test_a_prune_pattern_over_its_own_surface_is_dropped_not_obeyed(self) -> None:
        """A clone used as a project once listed its own folders in prune (793 files on a real project): init keeps
        them, says so, and still prunes the template-only material."""
        vision = self.clone_in_use(extra_prune='"app/**", ')
        done = self.cli("init", "--name", "my-project", "--kind", "web")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("app/**", done.stdout)
        self.assertTrue((self.root / "app/main.py").is_file())
        self.assertIn("Our own goal: ship the app.", vision.read_text(encoding="utf-8"))


class KitUpstreamTests(Scratch):
    """#88: a kit file changed in a project is reported to the template or recorded as project-specific."""

    def project(self) -> None:
        import hashlib
        self.write("project.toml", 'schema = 1\nname = "p"\nkind = "web"\n[template]\n'
                                   'source = "https://github.com/owner/AI_TEMPLATE"\n')
        self.write("tools/kit/x.py", "ORIGINAL = 1\n")
        shipped = hashlib.sha256(b"ORIGINAL = 1\n").hexdigest()
        from kit.kitlock import digest
        self.write("tools/kit-lock.json", json.dumps({"kit_version": "none",
                                                      "files": {"tools/kit/x.py": digest(self.root / "tools/kit/x.py")}}))
        self.assertTrue(shipped)

    def test_a_changed_kit_file_holds_the_gate_until_reported_or_explained(self) -> None:
        from kit import kitreport
        self.project()
        self.assertEqual(kitreport.upstream_findings(self.root, ["tools/kit/x.py"]), [])  # unchanged: nothing owed
        self.write("tools/kit/x.py", "ORIGINAL = 2  # better\n")
        owed = kitreport.upstream_findings(self.root, ["tools/kit/x.py"])
        self.assertEqual(len(owed), 1)
        self.assertIn("make kit-report", owed[0])
        self.git("init", "-q")
        args = mock.Mock(reason="only this project needs it", title=None, body_file=None, type=None,
                         priority=None, topic=None)
        self.assertIn("project-specific", kitreport.report(self.root, args))
        self.assertEqual(kitreport.upstream_findings(self.root, ["tools/kit/x.py"]), [])

    def test_the_template_itself_is_never_asked(self) -> None:
        """Negative case: no lock, no kit files to report."""
        from kit import kitreport
        self.write("tools/kit/x.py", "changed\n")
        self.assertEqual(kitreport.upstream_findings(self.root, ["tools/kit/x.py"]), [])

    def report_args(self) -> mock.Mock:
        return mock.Mock(reason=None, title="Better x", body_file=Path(".agent/bodies/r.md"), type="enhancement",
                         priority="P3", topic="x")

    def test_a_report_is_only_a_local_draft_without_the_owner_opt_in(self) -> None:
        """Critic finding: nothing leaves a (possibly private) project for a public template repository by default."""
        from kit import kitreport
        self.project()
        self.write("tools/kit/x.py", "ORIGINAL = 2\n")
        self.write(".agent/bodies/r.md", "### Summary\nbetter x\n")
        self.git("init", "-q")
        self.git("remote", "add", "origin", "https://github.com/acme/secret-app.git")
        with mock.patch("kit.issues.file_issue") as filed:
            message = kitreport.report(self.root, self.report_args())
        filed.assert_not_called()
        self.assertIn("nothing was sent", message)
        draft = (self.root / kitreport.DRAFTS / "x.md").read_text(encoding="utf-8")
        self.assertNotIn("acme/secret-app", draft)
        self.assertIn("kit file(s): tools/kit/x.py", draft)
        self.assertEqual(kitreport.upstream_findings(self.root, ["tools/kit/x.py"]), [], "a draft clears the gate")

    def test_publishing_a_draft_files_it_on_the_template_without_the_project_name(self) -> None:
        from kit import kitreport
        self.project()
        self.write("tools/kit/x.py", "ORIGINAL = 2\n")
        self.write(".agent/bodies/r.md", "### Summary\nbetter x\n")
        self.git("init", "-q")
        self.git("remote", "add", "origin", "https://github.com/acme/secret-app.git")
        kitreport.report(self.root, self.report_args())
        second = kitreport.report(self.root, self.report_args())
        self.assertIn("x-2.md", second, "a second draft on the same topic does not overwrite the first")
        seen = {}
        def fake_file_issue(root, title, body, *rest, repository=None):
            seen.update(body=(root / body).read_text(), repository=repository, public=rest[-2])
            return "https://github.com/owner/AI_TEMPLATE/issues/1"
        draft = mock.Mock(title="Better x", body_file=kitreport.Path(kitreport.DRAFTS) / "x.md", type="enhancement",
                          priority="P3", topic="x")
        with mock.patch("kit.issues.file_issue", fake_file_issue):
            url = kitreport.publish(self.root, draft)
        self.assertEqual(seen["repository"], "owner/AI_TEMPLATE")
        self.assertNotIn("acme", seen["body"])
        self.assertTrue(seen["public"])
        self.assertTrue(url.endswith("/issues/1"))

    def test_the_host_asks_before_a_public_filing(self) -> None:
        """Claude Code asks the person before `make kit-publish`; drafting needs no approval."""
        settings = json.loads((Path(__file__).resolve().parents[2] / ".claude/settings.json").read_text())
        self.assertIn("Bash(make kit-publish:*)", settings["permissions"]["ask"])
        self.assertIn("Bash(tools/repoctl kit-publish:*)", settings["permissions"]["ask"])
        self.assertNotIn("Bash(make kit-publish:*)", settings["permissions"]["allow"])

    def test_a_deleted_kit_file_is_asked_about_too(self) -> None:
        from kit import kitreport
        self.project()
        (self.root / "tools/kit/x.py").unlink()
        self.assertEqual(len(kitreport.upstream_findings(self.root, ["tools/kit/x.py"])), 1)
        self.git("init", "-q")
        kitreport.report(self.root, mock.Mock(reason="removed on purpose"))
        self.assertEqual(kitreport.upstream_findings(self.root, ["tools/kit/x.py"]), [])

    def test_publish_refuses_a_body_that_is_not_a_draft(self) -> None:
        """Negative case: kit-publish files only what kit-report drafted, never an arbitrary file."""
        from kit import kitreport
        self.project()
        self.write(".agent/bodies/r.md", "### Summary\nraw\n")
        args = mock.Mock(title="x", body_file=Path(".agent/bodies/r.md"), type="bug", priority="P3", topic="x")
        with mock.patch("kit.issues.file_issue") as filed, self.assertRaises(RepoctlError):
            kitreport.publish(self.root, args)
        filed.assert_not_called()

    def test_a_later_different_edit_is_asked_again(self) -> None:
        from kit import kitreport
        self.project()
        self.write("tools/kit/x.py", "ORIGINAL = 2\n")
        self.git("init", "-q")
        kitreport.report(self.root, mock.Mock(reason="local", public_reviewed=False))
        self.assertEqual(kitreport.upstream_findings(self.root, ["tools/kit/x.py"]), [])
        self.write("tools/kit/x.py", "ORIGINAL = 3\n")
        self.assertEqual(len(kitreport.upstream_findings(self.root, ["tools/kit/x.py"])), 1)


class LocklessKitUpdateTests(Scratch):
    """#89: without a lock, a file identical to any past kit version is updated, a real edit is staged."""

    def test_old_kit_versions_update_and_real_edits_stay(self) -> None:
        import shutil
        import tempfile
        from fixtures import git_in
        from kit import kitupdate
        kit = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, kit, True)
        git_in(kit, "init", "-q")
        (kit / "tools").mkdir()
        for name, old in (("a.py", "A = 1\n"), ("b.py", "B = 1\n")):
            (kit / "tools" / name).write_text(old)
        git_in(kit, "add", "-A")
        git_in(kit, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "v1")
        for name, new in (("a.py", "A = 2\n"), ("b.py", "B = 2\n")):
            (kit / "tools" / name).write_text(new)
        git_in(kit, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "v2")
        target = self.root / "tools"
        target.mkdir()
        (target / "a.py").write_text("A = 1\n")  # the old kit version, never edited
        (target / "b.py").write_text("B = 1  # ours\n")  # edited by the project
        self.assertTrue(kitupdate._past_kit_version(kit, "tools/a.py", target / "a.py"))
        self.assertFalse(kitupdate._past_kit_version(kit, "tools/b.py", target / "b.py"))

    def test_a_blob_only_on_another_branch_of_the_kit_is_not_shipped(self) -> None:
        """Review finding: `--all` matched blobs of an unshipped experiment branch, so an edit was overwritten."""
        import shutil
        import tempfile
        from fixtures import git_in
        from kit import kitupdate
        kit = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, kit, True)
        commit = ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q"]
        git_in(kit, "init", "-q", "-b", "main")
        (kit / "c.py").write_text("C = 1\n")
        git_in(kit, "add", "-A")
        git_in(kit, *commit, "-m", "v1")
        git_in(kit, "checkout", "-q", "-b", "experiment")
        (kit / "c.py").write_text("C = 99\n")
        git_in(kit, *commit, "-am", "experiment")
        git_in(kit, "checkout", "-q", "main")
        self.write("c.py", "C = 99\n")
        self.write("d.py", "C = 1\n")
        kitupdate._HISTORY.clear()
        self.assertFalse(kitupdate._past_kit_version(kit, "c.py", self.root / "c.py"))
        self.assertTrue(kitupdate._past_kit_version(kit, "c.py", self.root / "d.py"))


class GitSyncTests(Scratch):
    """#90: fetch in the brief, the stop gate's push rule, and pull-first before a run that counts."""

    def setUp(self) -> None:
        super().setUp()
        import shutil
        import tempfile
        from fixtures import git_in
        self.env = mock.patch.dict(os.environ, {"CI": "", "GITHUB_ACTIONS": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.remote = Path(tempfile.mkdtemp())
        self.other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.remote, True)
        self.addCleanup(shutil.rmtree, self.other, True)
        git_in(self.remote, "init", "-q", "--bare", "-b", "main")
        self.ci = ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q"]
        self.git("init", "-q", "-b", "main")
        self.write("a.txt", "1\n")
        self.git("add", "-A")
        self.git(*self.ci, "-m", "one")
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-q", "-u", "origin", "main")
        git_in(self.other, "clone", "-q", str(self.remote), ".")

    def teammate_pushes(self) -> None:
        from fixtures import git_in
        (self.other / "b.txt").write_text("2\n")
        git_in(self.other, "add", "-A")
        git_in(self.other, *self.ci, "-m", "two")
        git_in(self.other, "push", "-q")

    def test_the_brief_fast_forwards_a_clean_tree_that_is_only_behind(self) -> None:
        from kit import gitsync
        self.teammate_pushes()
        lines = gitsync.brief_lines(self.root)
        self.assertIn("pulled 1 new commit", lines[0])
        self.assertTrue((self.root / "b.txt").is_file())

    def test_commits_the_brief_pulled_are_not_this_sessions_work(self) -> None:
        """Critic blocker: the pull ran after the snapshot, so the stop gate judged a teammate's commits."""
        import contextlib
        import io
        from test_plugin_isolation import MANIFEST
        from kit import session
        self.write("project.toml", MANIFEST)
        self.write("docs/README.md", "# Docs\n")
        self.git("add", "-A")
        self.git(*self.ci, "-m", "manifest")
        self.git("push", "-q")
        from fixtures import git_in
        git_in(self.other, "pull", "-q")
        self.teammate_pushes()
        with contextlib.redirect_stdout(io.StringIO()) as brief:
            session.session_start(self.root, {"session_id": "s"})
        self.assertIn("pulled 1 new commit", brief.getvalue())
        self.assertTrue((self.root / "b.txt").is_file())
        self.assertEqual(session.session_changes(self.root, "s"), [])

    def test_a_resumed_session_never_takes_pulled_commits_as_its_own(self) -> None:
        """Critic blocker: on resume or compaction the snapshot is kept, so a pull then looked like the session's."""
        import contextlib
        import io
        from test_plugin_isolation import MANIFEST
        from fixtures import git_in
        from kit import session
        self.write("project.toml", MANIFEST)
        self.write("docs/README.md", "# Docs\n")
        self.write(".gitignore", ".agent/\n")  # as in every kit project: hook scratch is never committed
        self.git("add", "-A")
        self.git(*self.ci, "-m", "manifest")
        self.git("push", "-q")
        git_in(self.other, "pull", "-q")

        def start() -> str:
            with contextlib.redirect_stdout(io.StringIO()) as brief:
                session.session_start(self.root, {"session_id": "s"})
            return brief.getvalue()

        start()
        self.teammate_pushes()  # nothing committed here yet: the resumed brief pulls and moves the baseline
        self.assertIn("pulled 1 new commit", start())
        self.assertEqual(session.session_changes(self.root, "s"), [])
        self.write("mine.txt", "x\n")
        self.git("add", "-A")
        self.git(*self.ci, "-m", "mine")
        self.git("push", "-q")
        (self.other / "c.txt").write_text("3\n")
        git_in(self.other, "pull", "-q")
        git_in(self.other, "add", "-A")
        git_in(self.other, *self.ci, "-m", "three")
        git_in(self.other, "push", "-q")
        brief = start()  # the session has its own commits now: it is told, never fast-forwarded
        self.assertIn("1 commit(s) behind upstream", brief)
        self.assertEqual(session.session_changes(self.root, "s"), ["mine.txt"])

    def healing_session(self):
        from fixtures import build_demo, git_in
        from kit import session
        build_demo(self.root)
        self.write(".gitignore", ".agent/\n")
        self.commit("demo with ignored hook scratch")
        self.git("push", "-q")
        git_in(self.other, "pull", "-q")

        def start() -> str:
            result = self.cli("hook", "session-start", stdin='{"session_id": "s-heal"}')
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        start()
        return start, session

    def peer_changes_role(self, *, remove_skill: bool = False, blocked: bool = False) -> str:
        from fixtures import git_in
        source = self.other / ".agents/agents/scout.md"
        content = source.read_text().replace("Read-only locator", "Peer locator").replace("Own locator", "Peer locator")
        source.write_text(content)
        if remove_skill:
            (self.other / ".agents/skills/demo-skill/SKILL.md").unlink()
        if blocked:  # actual generator write failure, without breaking registry loading
            target = self.other / ".claude/agents/scout.md"
            target.unlink()
            target.mkdir()
            (target / "blocker.txt").write_text("not a writable adapter file\n")
            git_in(self.other, "add", ".claude")
        git_in(self.other, "add", ".agents")
        git_in(self.other, *self.ci, "-m", "peer canonical change without regeneration")
        git_in(self.other, "push", "-q")
        return git_in(self.other, "rev-parse", "HEAD").stdout.strip()

    def test_resume_heals_pulled_adapter_without_owning_it(self) -> None:
        start, session = self.healing_session()
        before = session._load_state(self.root, "s-heal")
        peer = self.peer_changes_role(remove_skill=True)
        brief = start()
        self.assertIn("pulled 1 new commit", brief)
        self.assertIn(".claude/agents/scout.md", brief)
        after = session._load_state(self.root, "s-heal")
        self.assertNotEqual(before["snapshot_head"], peer)
        self.assertEqual(after["snapshot_head"], peer)
        self.assertIn("Peer locator", (self.root / ".claude/agents/scout.md").read_text())
        self.assertEqual(session.session_changes(self.root, "s-heal"), [])
        orphan = ".claude/skills/demo-skill/SKILL.md"
        self.assertFalse((self.root / orphan).exists())
        self.assertIn("removed " + orphan, brief)
        self.assertEqual(after["snapshot"][orphan], "deleted")

    def test_resume_regeneration_error_is_not_a_snapshot_path(self) -> None:
        start, session = self.healing_session()
        baseline = session._load_state(self.root, "s-heal")
        self.peer_changes_role(blocked=True)
        brief = start()
        self.assertIn("pulled 1 new commit", brief)
        self.assertIn("adapter regeneration failed:", brief)
        self.assertEqual(session._load_state(self.root, "s-heal")["snapshot"], baseline["snapshot"])

    def test_resume_keeps_own_native_source_and_unrelated_edits_owned(self) -> None:
        start, session = self.healing_session()
        baseline = session._load_state(self.root, "s-heal")
        source = ".agents/agents/scout.md"  # native hosts read the canonical role directly
        self.write(source, (self.root / source).read_text().replace("Read-only locator", "Own locator"))
        self.write("mine.txt", "own non-generated edit\n")
        self.peer_changes_role()  # dirty canonical work must prevent the automatic pull/exemption
        self.assertIn("1 commit(s) behind upstream", start())
        self.assertEqual(session.session_changes(self.root, "s-heal"),
                         [source, ".claude/agents/scout.md", "mine.txt"])
        after = session._load_state(self.root, "s-heal")
        self.assertEqual(after["snapshot"], baseline["snapshot"])
        self.assertEqual(after["snapshot_head"], baseline["snapshot_head"])
        self.assertEqual(after["check_baseline"], baseline["check_baseline"])
        stopped = json.loads(self.cli("hook", "stop", stdin='{"session_id": "s-heal"}').stdout)
        self.assertIn(source, stopped["reason"])
        self.assertIn("uncommitted work of this session", stopped["reason"])

    def test_resume_keeps_own_committed_native_source_history_before_peer_pull(self) -> None:
        start, session = self.healing_session()
        baseline = session._load_state(self.root, "s-heal")
        source = ".agents/agents/scout.md"
        self.write(source, (self.root / source).read_text().replace("Read-only locator", "Own locator"))
        self.commit("own native canonical change without regeneration")
        self.git("push", "-q")
        from fixtures import git_in
        git_in(self.other, "pull", "-q")
        self.peer_changes_role()
        self.assertIn("1 commit(s) behind upstream", start())
        self.assertEqual(session.session_changes(self.root, "s-heal"), [source, ".claude/agents/scout.md"])
        self.assertEqual(session._load_state(self.root, "s-heal")["snapshot_head"], baseline["snapshot_head"])
        self.assertEqual(session._load_state(self.root, "s-heal")["check_baseline"], baseline["check_baseline"])
        stopped = json.loads(self.cli("hook", "stop", stdin='{"session_id": "s-heal"}').stdout)
        self.assertIn(".claude/agents/scout.md", stopped["reason"])

    def test_the_brief_never_pulls_into_a_dirty_tree(self) -> None:
        """Negative case: local edits are never merged into; the brief says to pull instead."""
        from kit import gitsync
        self.teammate_pushes()
        self.write("a.txt", "mine\n")
        lines = gitsync.brief_lines(self.root)
        self.assertIn("1 commit(s) behind upstream", lines[0])
        self.assertFalse((self.root / "b.txt").exists())

    def test_the_stop_gate_names_uncommitted_and_unpushed_work_of_this_session(self) -> None:
        from kit import gitsync
        start = self.git("rev-parse", "HEAD").strip()
        self.write("c.txt", "3\n")
        self.assertIn("uncommitted work of this session (c.txt)",
                      gitsync.unpushed_findings(self.root, ["c.txt"], start)[0])
        self.git("add", "-A")
        self.git(*self.ci, "-m", "three")
        self.assertIn("1 commit(s) not pushed", gitsync.unpushed_findings(self.root, ["c.txt"], start)[0])
        self.git("push", "-q")
        self.assertEqual(gitsync.unpushed_findings(self.root, ["c.txt"], start), [])

    def test_no_remote_or_ci_means_nothing_to_push(self) -> None:
        """Negative case: without a remote, or inside CI, the push rule says nothing."""
        from kit import gitsync
        self.write("c.txt", "3\n")
        with mock.patch.dict(os.environ, {"CI": "true"}):
            self.assertEqual(gitsync.unpushed_findings(self.root, ["c.txt"], None), [])
        self.git("remote", "remove", "origin")
        self.assertEqual(gitsync.unpushed_findings(self.root, ["c.txt"], None), [])
        self.assertEqual(gitsync.brief_lines(self.root), [])

    def test_pull_first_inside_ci_runs_the_checked_out_commit(self) -> None:
        from kit import gitsync
        self.write("a.txt", "dirty\n")
        with mock.patch.dict(os.environ, {"CI": "true"}):
            self.assertEqual(gitsync.pull_first(self.root)[0], 0)

    def test_pull_first_exit_codes(self) -> None:
        from kit import gitsync
        self.assertEqual(gitsync.pull_first(self.root)[0], 0)
        self.teammate_pushes()
        self.assertEqual(gitsync.pull_first(self.root, check_only=True)[0], 1)
        self.assertFalse((self.root / "b.txt").exists(), "check only never pulls")
        self.assertEqual(gitsync.pull_first(self.root)[0], gitsync.PULLED)
        self.write("a.txt", "dirty\n")
        self.assertEqual(gitsync.pull_first(self.root)[0], 1)
        self.git("checkout", "--", "a.txt")
        self.git(*self.ci, "--allow-empty", "-m", "local")
        self.assertIn("not pushed", gitsync.pull_first(self.root)[1])

    def test_the_append_only_error_log_merges_by_union(self) -> None:
        """#93: two branches that each append an ERROR_LOG entry merge without a conflict."""
        root = Path(__file__).resolve().parents[2]
        lines = (root / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("docs/ERROR_LOG.md merge=union", lines)
        self.assertFalse(any("AGENTS.md" in line and "union" in line for line in lines), "never an edited file")


if __name__ == "__main__":
    unittest.main()
