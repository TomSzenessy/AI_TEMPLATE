"""Local CI (#160): workflow drift, honest skips, exit codes, recorded evidence, and the guard."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import Scratch, template_only  # noqa: E402

from kit import checks, core, derive, localci, trial, wfmap  # noqa: E402
from kit.registry import Registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

WORKFLOW = """\
name: ci
on:
  push:
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - run: echo verify
  publish:
    runs-on: ubuntu-latest
    steps:
      - run: echo publish
"""
WORKFLOW_PATH = ".github/workflows/ci.yml"

FOUR_SPACE = """\
name: ci
on:
  push:
jobs:
    verify:
        runs-on: ubuntu-latest
        steps:
            - run: echo verify
    publish:
        runs-on: ubuntu-latest
"""

FLOW_JOBS = "name: flow\non: push\njobs: {verify: {runs-on: ubuntu-latest}}\n"

FLOW_NEXT_LINE = """\
name: flow
on: push
jobs:
  {extra: {runs-on: ubuntu-latest}}
"""

QUOTED_JOB = """\
name: quoted
on: push
jobs:
  "extra":
    runs-on: ubuntu-latest
"""

QUOTED_JOBS = """\
name: quoted
on: push
"jobs":
  verify:
    runs-on: ubuntu-latest
"""

SPACED_KEYS = """\
name: spaced
on: push
jobs :
  "extra" :
    runs-on: ubuntu-latest
"""

EMPTY_JOBS_THEN_KEY = """\
name: empty
on: push
jobs:
permissions: {}
"""

EMPTY_JOBS_THEN_NESTED = """\
name: empty
on: push
jobs:
permissions:
  contents: read
"""

EXPLICIT_JOBS_KEY = """\
name: explicit
on: push
? jobs
:
  extra:
    runs-on: ubuntu-latest
"""

EXPLICIT_JOB_KEY = """\
name: explicit
on: push
jobs:
  verify:
    runs-on: ubuntu-latest
  ? extra
  :
    runs-on: ubuntu-latest
"""


def digest_of(text: str, name: str) -> str:
    return wfmap.block_digest(wfmap.workflow_jobs(text)[name])


def mapped(group: str = "verify", name: str = "verify", commands: str = '[["sh", "-c", "exit 0"]]',
           digest: str | None = None, tools: str = "[]", slow: bool = False) -> str:
    return (
        "[[ci.local.jobs]]\n"
        f'group = "{group}"\n'
        f'workflow = "{WORKFLOW_PATH}"\n'
        f'job = "{name}"\n'
        f"tools = {tools}\n"
        f"slow = {'true' if slow else 'false'}\n"
        f"commands = {commands}\n"
        f'digest = "{digest if digest is not None else digest_of(WORKFLOW, name)}"\n'
    )


def not_local(name: str = "publish", reason: str = "needs a release tag and a registry login") -> str:
    return (
        "[[ci.local.not_local]]\n"
        f'workflow = "{WORKFLOW_PATH}"\n'
        f'job = "{name}"\n'
        f'reason = "{reason}"\n'
    )


def manifest(jobs: str = "", others: str = "", guard: bool = False, tools: str = "") -> str:
    return (
        'schema = 1\nname = "Demo"\nkind = "web"\n\n'
        "[ci.local]\n"
        f"guard = {'true' if guard else 'false'}\n\n"
        "[ci.local.tools]\n"
        f"{tools}\n\n"
        f"{jobs}\n{others}\n"
    )


class LocalCIBase(Scratch):
    def setUp(self) -> None:
        super().setUp()
        self.git("init", "-q", "-b", "main")
        self.write("project.toml", manifest(mapped(), not_local()))
        self.workflow = self.write(WORKFLOW_PATH, WORKFLOW)
        self.commit("initial")

    def write_manifest(self, content: str) -> None:
        """Replace the manifest and commit it: the run deliberately refuses a dirty tree."""
        self.write("project.toml", content)
        self.commit("manifest")

    def run_ci(self, **options) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            code = localci.run(self.root, localci.Options(**options))
        return code, stream.getvalue()

    def run_guard(self) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            code = localci.guard(self.root)
        return code, stream.getvalue()

    def last_run(self) -> dict:
        return json.loads((self.root / localci.STATE_DIR / localci.LAST_RUN).read_text(encoding="utf-8"))


class WorkflowParsingTests(unittest.TestCase):
    def test_jobs_are_read_as_blocks_with_their_steps(self) -> None:
        jobs = wfmap.workflow_jobs(WORKFLOW)
        self.assertEqual(set(jobs), {"verify", "publish"})
        self.assertIn("echo verify", jobs["verify"])
        self.assertNotIn("echo publish", jobs["verify"])

    def test_a_workflow_without_jobs_yields_none(self) -> None:
        self.assertEqual(wfmap.workflow_jobs("name: x\non: push\n"), {})

    def test_any_consistent_job_indentation_is_read(self) -> None:
        self.assertEqual(set(wfmap.workflow_jobs(FOUR_SPACE)), {"verify", "publish"})
        self.assertIn("echo verify", wfmap.workflow_jobs(FOUR_SPACE)["verify"])

    def test_a_flow_style_jobs_mapping_is_reported_to_the_caller(self) -> None:
        self.assertEqual(wfmap.workflow_jobs(FLOW_JOBS), {})
        self.assertIn("not a block mapping", wfmap.workflow_problem(FLOW_JOBS))

    def test_a_flow_mapping_on_the_line_after_jobs_is_unreadable(self) -> None:
        self.assertEqual(wfmap.workflow_jobs(FLOW_NEXT_LINE), {})
        self.assertIn("flow mapping", wfmap.workflow_problem(FLOW_NEXT_LINE))

    def test_quoted_job_keys_and_a_quoted_jobs_key_are_read(self) -> None:
        self.assertEqual(set(wfmap.workflow_jobs(QUOTED_JOB)), {"extra"})
        self.assertIsNone(wfmap.workflow_problem(QUOTED_JOB))
        self.assertEqual(set(wfmap.workflow_jobs(QUOTED_JOBS)), {"verify"})

    def test_yaml_whitespace_before_a_colon_is_read(self) -> None:
        self.assertEqual(set(wfmap.workflow_jobs(SPACED_KEYS)), {"extra"})
        self.assertIsNone(wfmap.workflow_problem(SPACED_KEYS))
        self.assertEqual(set(wfmap.workflow_jobs('"jobs" :\n  verify :\n    runs-on: x\n')), {"verify"})

    def test_an_empty_jobs_mapping_followed_by_a_key_is_not_unreadable(self) -> None:
        self.assertEqual(wfmap.workflow_jobs(EMPTY_JOBS_THEN_KEY), {})
        self.assertIsNone(wfmap.workflow_problem(EMPTY_JOBS_THEN_KEY))
        self.assertIsNone(wfmap.workflow_problem(EMPTY_JOBS_THEN_NESTED))

    def test_a_block_workflow_with_no_jobs_is_not_unreadable(self) -> None:
        self.assertIsNone(wfmap.workflow_problem("name: x\non: push\njobs:\n"))

    def test_an_explicit_yaml_jobs_key_is_named_not_ignored(self) -> None:
        self.assertEqual(wfmap.workflow_jobs(EXPLICIT_JOBS_KEY), {})
        self.assertIn("not a conventional top-level key", wfmap.workflow_problem(EXPLICIT_JOBS_KEY))

    def test_an_explicit_job_key_inside_a_readable_block_is_named(self) -> None:
        self.assertEqual(set(wfmap.workflow_jobs(EXPLICIT_JOB_KEY)), {"verify"})
        self.assertIn("job keys cannot be read", wfmap.workflow_problem(EXPLICIT_JOB_KEY))

    def test_a_block_digest_changes_when_the_job_changes(self) -> None:
        changed = WORKFLOW.replace("echo verify", "echo verify --all")
        self.assertNotEqual(digest_of(WORKFLOW, "verify"), digest_of(changed, "verify"))


class ManifestTests(LocalCIBase):
    def test_a_complete_map_has_no_findings(self) -> None:
        self.assertEqual(localci.findings(self.root), [])

    def test_an_unmapped_workflow_job_is_a_finding(self) -> None:
        self.write_manifest(manifest(mapped()))
        problems = "\n".join(localci.findings(self.root))
        self.assertIn("ci.yml:publish is neither mapped", problems)

    def test_a_missing_digest_is_a_finding(self) -> None:
        self.write_manifest(manifest(mapped(digest=""), not_local()))
        self.assertIn("has no digest", "\n".join(localci.findings(self.root)))

    def test_a_changed_workflow_job_makes_the_digest_stale(self) -> None:
        self.workflow.write_text(WORKFLOW.replace("echo verify", "echo verify --changed"), encoding="utf-8")
        problems = "\n".join(localci.findings(self.root))
        self.assertIn("changed since it was reviewed", problems)

    def test_a_removed_job_is_a_finding(self) -> None:
        self.workflow.write_text(WORKFLOW.replace("  verify:\n", "  renamed:\n"), encoding="utf-8")
        problems = "\n".join(localci.findings(self.root))
        self.assertIn("no job 'verify'", problems)

    def test_not_local_needs_a_reason(self) -> None:
        self.write_manifest(manifest(mapped(), not_local(reason="")))
        self.assertIn("not_local needs a reason", "\n".join(localci.findings(self.root)))

    def test_a_four_space_workflow_job_is_visible_to_the_drift_check(self) -> None:
        self.write(".github/workflows/four.yml", FOUR_SPACE)
        problems = "\n".join(localci.findings(self.root))
        self.assertIn("four.yml:verify is neither mapped", problems)
        self.assertIn("four.yml:publish is neither mapped", problems)

    def test_a_spaced_jobs_key_is_visible_to_the_drift_check(self) -> None:
        self.write(".github/workflows/spaced.yml", SPACED_KEYS)
        self.assertIn("spaced.yml:extra is neither mapped", "\n".join(localci.findings(self.root)))

    def test_flow_style_jobs_are_a_named_finding_not_silence(self) -> None:
        self.write(".github/workflows/flow.yml", FLOW_JOBS)
        self.write(".github/workflows/flow-next.yml", FLOW_NEXT_LINE)
        problems = "\n".join(localci.findings(self.root))
        self.assertIn("flow.yml: its 'jobs:' value is not a block mapping", problems)
        self.assertIn("flow-next.yml: its jobs are a flow mapping", problems)

    def test_an_explicit_key_workflow_is_a_named_finding(self) -> None:
        self.write(".github/workflows/explicit.yml", EXPLICIT_JOBS_KEY)
        self.assertIn("explicit.yml: line 3 is not a conventional top-level key",
                      "\n".join(localci.findings(self.root)))

    def test_no_manifest_is_not_a_finding(self) -> None:
        self.write_manifest('schema = 1\nname = "Demo"\nkind = "web"\n')
        self.assertEqual(localci.findings(self.root), [])

    def test_the_check_is_wired_to_the_manifest(self) -> None:
        self.write_manifest(manifest(mapped()))
        self.assertEqual(checks.local_ci_map(SimpleNamespace(root=self.root)), localci.findings(self.root))
        self.assertTrue(localci.findings(self.root))

    def test_bless_refreshes_a_stale_digest_and_keeps_the_comment(self) -> None:
        self.workflow.write_text(WORKFLOW.replace("echo verify", "echo verify --changed"), encoding="utf-8")
        text = (self.root / "project.toml").read_text(encoding="utf-8").replace(
            "[[ci.local.jobs]]", "# reviewed after the workflow diff\n[[ci.local.jobs]]")
        (self.root / "project.toml").write_text(text, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(localci.bless(self.root), 0)
        self.assertEqual(localci.findings(self.root), [])
        self.assertIn("# reviewed after the workflow diff", (self.root / "project.toml").read_text(encoding="utf-8"))

    def test_bless_refuses_structural_problems(self) -> None:
        self.write_manifest(manifest(mapped()))  # publish is unmapped: not a digest problem
        before = (self.root / "project.toml").read_text(encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(localci.bless(self.root), 1)
        self.assertEqual((self.root / "project.toml").read_text(encoding="utf-8"), before)


class RunTests(LocalCIBase):
    def test_a_passing_run_records_the_commit_tree_and_logs(self) -> None:
        code, output = self.run_ci()
        self.assertEqual(code, 0)
        self.assertIn("Local CI: PASSED", output)
        record = self.last_run()
        self.assertEqual(record["commit"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(record["tree"], self.git("rev-parse", "HEAD^{tree}").strip())
        self.assertEqual(record["state"], "passed")
        self.assertEqual(record["jobs"][0]["state"], "PASS")
        self.assertTrue((self.root / record["jobs"][0]["log"]).is_file())
        self.assertIsNone(localci.evidence_note(self.root))

    def test_a_failing_command_exits_one_and_writes_the_log(self) -> None:
        self.write_manifest(manifest(mapped(commands='[["sh", "-c", "echo the-real-failure; exit 7"]]'), not_local()))
        code, output = self.run_ci()
        self.assertEqual(code, 1)
        self.assertIn("Local CI: FAILED", output)
        self.assertIn("the-real-failure", output)
        record = self.last_run()
        self.assertEqual(record["state"], "failed")
        self.assertEqual(record["exit"], 1)
        self.assertIn("the-real-failure", (self.root / record["jobs"][0]["log"]).read_text(encoding="utf-8"))

    def test_a_missing_tool_is_incomplete_never_passed(self) -> None:
        self.write_manifest(manifest(mapped(tools='["definitely-not-installed-localci"]'), not_local()))
        code, output = self.run_ci()
        self.assertEqual(code, 3)
        self.assertIn("SKIP", output)
        self.assertIn("Local CI: INCOMPLETE", output)
        self.assertNotIn("Local CI: PASSED", output)
        self.assertEqual(self.last_run()["skipped"], 1)

    def test_allow_skip_exits_zero_but_keeps_incomplete_evidence(self) -> None:
        self.write_manifest(manifest(mapped(tools='["definitely-not-installed-localci"]'), not_local()))
        code, output = self.run_ci(allow_skip=True)
        self.assertEqual(code, 0)
        self.assertIn("PASSED WITH SKIPS", output)
        self.assertEqual(self.last_run()["state"], "incomplete")
        self.assertEqual(self.last_run()["skipped"], 1)

    def test_a_slow_job_is_skipped_until_enabled(self) -> None:
        self.write_manifest(manifest(mapped(slow=True), not_local()))
        code, output = self.run_ci()
        self.assertEqual(code, 3)
        self.assertIn("slow; set CI_LOCAL_SLOW=1", output)
        code, _ = self.run_ci(slow=True)
        self.assertEqual(code, 0)

    def test_a_dirty_tree_is_refused_unless_explicitly_overridden(self) -> None:
        self.write("scratch.txt", "uncommitted\n")
        code, output = self.run_ci()
        self.assertEqual(code, 2)
        self.assertIn("refuses a dirty tree", output)
        self.assertFalse((self.root / localci.STATE_DIR / localci.LAST_RUN).exists())
        code, _ = self.run_ci(dirty=True)
        self.assertEqual(code, 0)
        self.assertTrue(self.last_run()["dirty"])
        self.assertIn("unverified", localci.evidence_note(self.root) or "")

    def test_group_selection_runs_only_that_group(self) -> None:
        second = mapped(group="docs", name="publish", commands='[["sh", "-c", "echo docs >> calls.txt"]]')
        first = mapped(commands='[["sh", "-c", "echo verify >> calls.txt"]]')
        self.write_manifest(manifest(first + second))
        code, _ = self.run_ci(group="docs")
        self.assertEqual(code, 0)
        self.assertEqual((self.root / "calls.txt").read_text(encoding="utf-8").strip(), "docs")

    def test_an_unknown_group_is_misuse(self) -> None:
        code, output = self.run_ci(group="nope")
        self.assertEqual(code, 2)
        self.assertIn("unknown local CI group", output)

    def test_not_local_jobs_are_never_executed(self) -> None:
        calls: list[list[str]] = []
        real = localci.subprocess.run

        def spy(*arguments, **keywords):
            calls.append(list(arguments[0]))
            return real(*arguments, **keywords)

        self.write_manifest(manifest(mapped(commands='[["sh", "-c", "echo mapped"]]'), not_local()))
        with mock.patch.object(localci.subprocess, "run", side_effect=spy):
            code, _ = self.run_ci()
        self.assertEqual(code, 0)
        shell_calls = [call for call in calls if call and call[0] == "sh"]
        self.assertEqual(shell_calls, [["sh", "-c", "echo mapped"]])

    def test_the_runner_never_reads_provider_keys_or_the_network(self) -> None:
        source = Path(localci.__file__).read_text(encoding="utf-8")
        for forbidden in ("urllib", "http.client", "socket.", "requests.", "GITHUB_TOKEN", "GH_TOKEN"):
            self.assertNotIn(forbidden, source)

    def test_list_and_plan_show_not_local_jobs_with_their_reason(self) -> None:
        for options in ({"list_jobs": True}, {"plan_only": True}):
            code, output = self.run_ci(**options)
            self.assertEqual(code, 0)
            self.assertIn("not_local", output)
            self.assertIn("ci.yml:publish", output)
            self.assertIn("registry login", output)
            self.assertIn("verify", output)

    def test_a_doctor_reports_the_declared_tools(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = localci.doctor(self.root)
        self.assertEqual(code, 0)
        self.assertIn("Local CI tools", stream.getvalue())


class GuardTests(LocalCIBase):
    def test_the_command_dispatches_the_guard_without_running_jobs(self) -> None:
        """The pre-push hook calls `repoctl ci-local --guard`; it must read the record, never run the suite."""
        self.write_manifest(manifest(mapped(), not_local(), guard=True))
        done = self.cli("ci-local", "--guard")
        self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
        self.assertIn("no local CI run is recorded", done.stderr)
        self.assertNotIn("RUN", done.stdout)
        self.assertFalse((self.root / localci.STATE_DIR).exists(), "the guard must not create a run directory")

    def test_the_command_guard_is_inert_when_disabled(self) -> None:
        done = self.cli("ci-local", "--guard")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")

    def test_the_guard_is_opt_in(self) -> None:
        code, _ = self.run_guard()
        self.assertEqual(code, 0)

    def test_the_guard_blocks_without_a_record(self) -> None:
        self.write_manifest(manifest(mapped(), not_local(), guard=True))
        code, output = self.run_guard()
        self.assertEqual(code, 3)
        self.assertIn("no local CI run is recorded", output)

    def test_the_guard_allows_a_passing_run_at_head(self) -> None:
        self.write_manifest(manifest(mapped(), not_local(), guard=True))
        self.assertEqual(self.run_ci()[0], 0)
        self.assertEqual(self.run_guard()[0], 0)

    def test_the_guard_blocks_a_run_recorded_for_another_commit(self) -> None:
        self.write_manifest(manifest(mapped(), not_local(), guard=True))
        self.assertEqual(self.run_ci()[0], 0)
        self.write("later.txt", "later\n")
        self.commit("later")
        code, output = self.run_guard()
        self.assertEqual(code, 3)
        self.assertIn("recorded local CI run is for", output)

    def test_the_guard_blocks_an_incomplete_run(self) -> None:
        self.write_manifest(manifest(mapped(tools='["definitely-not-installed-localci"]'), not_local(), guard=True))
        self.assertEqual(self.run_ci(allow_skip=True)[0], 0)
        code, output = self.run_guard()
        self.assertEqual(code, 3)
        self.assertIn("incomplete", output)

    def test_the_guard_blocks_a_recorded_dirty_run(self) -> None:
        self.write_manifest(manifest(mapped(), not_local(), guard=True))
        self.write("scratch.txt", "uncommitted\n")
        self.assertEqual(self.run_ci(dirty=True)[0], 0)
        code, output = self.run_guard()
        self.assertEqual(code, 3)
        self.assertIn("unverified dirty tree", output)

    def test_the_guard_blocks_a_recorded_tree_that_differs_from_head(self) -> None:
        self.write_manifest(manifest(mapped(), not_local(), guard=True))
        self.assertEqual(self.run_ci()[0], 0)
        record = self.last_run()
        record["tree"] = "0" * 40
        (self.root / localci.STATE_DIR / localci.LAST_RUN).write_text(json.dumps(record), encoding="utf-8")
        code, output = self.run_guard()
        self.assertEqual(code, 3)
        self.assertIn("tree changed since the recorded local CI run", output)

    def test_the_hook_lets_a_push_through_when_repoctl_cannot_start(self) -> None:
        hook = self.root / ".githooks" / "pre-push"
        hook.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / ".githooks" / "pre-push", hook)
        launcher = self.root / "tools" / "repoctl"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
        launcher.chmod(0o755)
        done = subprocess.run(["sh", str(hook)], cwd=self.root, capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("NOT RUN", done.stderr)

    def test_ci_local_skip_bypasses_the_guard_with_a_reason(self) -> None:
        self.write_manifest(manifest(mapped(), not_local(), guard=True))
        with mock.patch.dict(os.environ, {"CI_LOCAL_SKIP": "1"}):
            code, output = self.run_guard()
        self.assertEqual(code, 0)
        self.assertIn("bypassed by CI_LOCAL_SKIP=1", output)


class GenerationTests(LocalCIBase):
    def test_generated_makefile_has_the_local_ci_targets(self) -> None:
        block = derive.render_commands(Registry(self.root))
        self.assertIn("ci-local:", block)
        self.assertIn("ci-doctor:", block)
        self.assertIn("--guard", Path(ROOT / "tools/kit/commands.py").read_text(encoding="utf-8"))


@template_only
class GeneratedProjectTests(unittest.TestCase):
    """A freshly generated project inherits the command and a map that matches its copied workflows."""

    def test_a_fresh_project_has_the_local_ci_command_and_a_complete_map(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "demo"
            trial._copy(ROOT, core.repository_files(ROOT), project)
            done = subprocess.run(
                [sys.executable, str(project / "tools/repoctl.py"), "--root", str(project), "init",
                 "--name", "demo", "--kind", "web"],
                capture_output=True, text=True, check=False)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("ci-local:", (project / "Makefile").read_text(encoding="utf-8"))
            self.assertIn("ci-doctor:", (project / "Makefile").read_text(encoding="utf-8"))
            self.assertIn("[ci.local]", (project / "project.toml").read_text(encoding="utf-8"))
            self.assertEqual(localci.findings(project), [])


@template_only
class TemplateManifestTests(unittest.TestCase):
    """The template's own map must stay complete and much smaller than the workflows it mirrors."""

    def test_every_template_workflow_job_is_mapped_or_not_local(self) -> None:
        self.assertEqual(localci.findings(ROOT), [])

    def test_the_template_manifest_is_far_smaller_than_its_workflows(self) -> None:
        manifest_text = (ROOT / "project.toml").read_text(encoding="utf-8")
        block = manifest_text.split("[ci.local]", 1)[1].split("[security]", 1)[0]
        workflows = sum(len(path.read_text(encoding="utf-8").splitlines())
                        for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")))
        self.assertLess(len(block.splitlines()), workflows / 2)


if __name__ == "__main__":
    unittest.main()
