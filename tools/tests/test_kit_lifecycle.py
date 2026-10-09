"""Trial, golden path, kit update, init and adopt (template checkout only) (split from the former single test_kit.py, #43)."""

from __future__ import annotations

import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import (TOOLS, Scratch, clean_env, git_in, run_cli, template_only)  # noqa: E402

from kit import (core, docmeta)  # noqa: E402


class TrialTests(Scratch):
    """make trial: the build-trial request format, setup, and friction analysis."""

    def test_analysis_counts_spend_commands_and_friction(self) -> None:
        from kit import trial
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "make next && make done"}},
                {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "git commit --no-verify -m x"}},
                {"type": "tool_use", "id": "c", "name": "Bash", "input": {"command": "make issue BODY=x"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "Not finished:\n- docs/a.md covers src/a.py"},
                {"type": "tool_result", "tool_use_id": "c", "is_error": True, "content": "repoctl: issue needs Summary"}]}},
            {"type": "result", "subtype": "success", "num_turns": 7, "total_cost_usd": 1.5, "duration_ms": 120000, "result": "Done."},
            {"type": "result", "subtype": "success", "num_turns": 2, "total_cost_usd": 0.25, "duration_ms": 60000, "result": "Fixed."},
        ]
        with tempfile.TemporaryDirectory() as folder:
            transcript = Path(folder) / "t.jsonl"
            transcript.write_text("\n".join(json.dumps(e) for e in events) + "\nnot json\n")
            analysis = trial.analyze_transcript(transcript)
        self.assertEqual((analysis["cost_usd"], analysis["turns"], analysis["minutes"]), (1.75, 9, 3.0))
        self.assertEqual(analysis["make_targets"], {"next": 1, "done": 1, "issue": 1})
        self.assertEqual(len(analysis["gate_blocks"]), 1)
        self.assertIn("docs/a.md", analysis["gate_blocks"][0]["message"])
        self.assertEqual(len(analysis["failed_make"]), 1)
        self.assertEqual(len(analysis["bypasses"]), 1)
        self.assertEqual(analysis["final_message"], "Fixed.")

    def test_request_validation(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / trial.TRIALS).mkdir(parents=True)
            (root / trial.TRIALS / "x.toml").write_text('id = "x"\nkind = "web"\nprompt = "Build it."\n')
            self.assertEqual(trial.load_trial(root, "x")["mode"], "new")
            (root / trial.TRIALS / "y.toml").write_text('id = "y"\nkind = "cli"\nmode = "adopt"\nprompt = "Go."\n')
            with self.assertRaisesRegex(Exception, "adopt mode needs seed"):
                trial.load_trial(root, "y")
            with self.assertRaisesRegex(Exception, "known: x, y"):
                trial.load_trial(root, "z")

    def test_every_shipped_request_loads(self) -> None:
        from kit import trial
        for path in sorted((TOOLS.parent / trial.TRIALS).glob("*.toml")):
            self.assertEqual(trial.load_trial(TOOLS.parent, path.stem)["id"], path.stem)

    @template_only
    def test_new_mode_prepares_an_initialized_copy(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "demo"
            trial.prepare(TOOLS.parent, {"id": "demo", "kind": "web", "mode": "new", "prompt": "x"}, project)
            self.assertIn('name = "demo"', (project / "project.toml").read_text())
            self.assertEqual(git_in(project, "status", "--porcelain").stdout, "")
            self.assertIn("intake", run_cli(project, "next").stdout)
            for command in ("check", "finish"):  # a fresh project starts green, so its first gate failure is the agent's
                result = run_cli(project, command)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@template_only
class GoldenPathTests(Scratch):
    """The promise of the template: an agent that does the intake meets no template bug.

    init -> minimal intake (accepted vision and stack, owner, one real surface) -> make done
    green -> a commit through the git gate. make done also runs the kit's own suite inside the
    new project. Any template bug on this path fails here, before it reaches ten projects.
    """

    def intake(self, project: Path, fill: bool = True) -> None:
        today = core.today().isoformat()
        for record in ("VISION.md", "docs/STACK-DECISION.md"):
            path = project / record
            text = path.read_text()
            if fill:
                text = re.sub(r"\[REQUIRED: ([^\]]+)\]", lambda m: "Decided: " + m.group(1).split(",")[0] + ".", text)
            path.write_text(text.replace("Status: pending", "Status: accepted").replace("Date: [YYYY-MM-DD]", f"Date: {today}"))
        manifest = project / "project.toml"
        text = re.sub(r'(?ms)(\[vision\]\s*\nstatus\s*=\s*)"pending"', r'\1"accepted"', manifest.read_text())
        text = re.sub(r'(?ms)^\[\[surfaces\]\]\nid = "template-bootstrap".*?verification = \[\]\n',
                      '[[surfaces]]\nid = "hello"\npath = "hello.py"\nkind = "script"\nstatus = "active"\nowner = "trial-owner"\n'
                      'quality_oracle = "prints the greeting"\nverification = [["python3", "hello.py"]]\n', text)
        manifest.write_text(text)
        (project / "hello.py").write_text('print("hello")\n')

    def test_init_intake_done_commit(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "demo"
            trial.prepare(TOOLS.parent, {"id": "demo", "kind": "cli", "mode": "new", "prompt": "x"}, project)
            self.assertIn("[REQUIRED:", (project / "VISION.md").read_text(), "init leaves a fresh record, not the template's")
            self.assertNotIn("AI_TEMPLATE", (project / "VISION.md").read_text())
            make = lambda *args: subprocess.run(["make", *args], cwd=project, capture_output=True, text=True, timeout=1200,
                                                  env=clean_env(**({} if os.environ.get("KIT_SLOW") == "1" else {"KIT_INNER": "1"})))
            self.intake(project, fill=False)
            self.assertIn("placeholders", make("check").stderr, "an accepted record with placeholders is refused")
            self.intake(project)
            done = make("done")
            self.assertEqual(done.returncode, 0, (done.stdout + done.stderr)[-3000:])
            self.assertEqual(make("start").returncode, 0)
            git_in(project, "add", "-A")
            commit = git_in(project, "commit", "-qm", "feat: hello surface", check=False)
            self.assertEqual(commit.returncode, 0, commit.stderr)

    def test_a_project_made_from_this_readme_passes_check(self) -> None:
        """#16: the generated command block must never read as un-rewritten template scaffolding."""
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "demo"
            trial.prepare(TOOLS.parent, {"id": "demo", "kind": "cli", "mode": "new", "prompt": "x"}, project)
            readme = project / "README.md"
            self.assertNotIn("Template mode", readme.read_text(), "make init rewrote the template's own line")
            self.assertIn("Project initialized: **demo** (`cli`)", readme.read_text())
            check = lambda: run_cli(project, "check")
            generated = check()
            self.assertEqual(generated.returncode, 0, (generated.stdout + generated.stderr)[-2000:])
            readme.write_text(readme.read_text().replace(
                "# This project is initialized.", "make init NAME=my-project KIND=web OWNER=your-handle"))
            bootstrap = check()
            self.assertEqual(bootstrap.returncode, 1, "column-0 quickstart prose is still template scaffolding")
            self.assertIn("still contains template bootstrap text", bootstrap.stderr)


@template_only
class KitUpdateTests(Scratch):
    """Template fixes reach projects already made from it, without overwriting the project's changes."""

    def git(self, where: Path, *args: str) -> str:
        return git_in(where, *args).stdout

    def snapshot(self, folder: Path) -> None:
        self.git(folder, "add", "-A")
        self.git(folder, "commit", "-qm", "snapshot")

    def test_update_applies_fixes_and_keeps_project_changes(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as temp:
            kit, project = Path(temp) / "kit", Path(temp) / "project"
            trial._copy(TOOLS.parent, core.repository_files(TOOLS.parent), kit)
            (kit / "tools/kit/obsolete.py").write_text("OLD = 1\n")
            self.git(kit, "init", "-q", "-b", "main")
            self.snapshot(kit)
            trial.prepare(kit, {"id": "demo", "kind": "cli", "mode": "new", "prompt": "x"}, project)
            lock = json.loads((project / "tools/kit-lock.json").read_text())
            self.assertIn("tools/kit/navigate.py", lock["files"])
            self.assertNotIn("project.toml", lock["files"], "project-owned files are never kit files")
            same = run_cli(project, "kit-update", "--kit", str(kit))
            self.assertIn("0 updated, 0 added, 0 removed, 0 to merge", same.stdout, "init and update agree")
            # The project customizes a kit doc and adds its own make target.
            (project / "docs/delegation.md").write_text((project / "docs/delegation.md").read_text() + "\nOur team rule.\n")
            (project / "project.mk").write_text("hello:\n\techo hi\n")
            self.snapshot(project)
            # The template ships version B: a fix, a new file, a removal, and a change to the customized doc.
            (kit / "tools/kit/navigate.py").write_text((kit / "tools/kit/navigate.py").read_text() + "\n# fixed in B\n")
            (kit / "tools/kit/extra_helper.py").write_text("NEW = 2\n")
            (kit / "tools/kit/obsolete.py").unlink()
            (kit / "docs/delegation.md").write_text((kit / "docs/delegation.md").read_text() + "\nKit B note.\n")
            self.snapshot(kit)
            update = lambda: run_cli(project, "kit-update", "--kit", str(kit))
            result = update()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "tools/kit/navigate.py").read_text().endswith("# fixed in B\n"))
            self.assertTrue((project / "tools/kit/extra_helper.py").is_file())
            self.assertFalse((project / "tools/kit/obsolete.py").exists())
            self.assertIn("Our team rule.", (project / "docs/delegation.md").read_text(), "the project's change stays")
            self.assertIn("merge: docs/delegation.md", result.stdout)
            self.assertIn("Kit B note.", (project / ".agent/kit-update/docs/delegation.md").read_text())
            from kit import kitupdate
            self.assertIn("docs/delegation.md", " ".join(kitupdate.pending_merges(project)), "garden keeps listing it")
            self.assertEqual((project / "project.mk").read_text(), "hello:\n\techo hi\n")
            head = self.git(kit, "rev-parse", "HEAD").strip()
            self.assertEqual(json.loads((project / "tools/kit-lock.json").read_text())["kit_version"], head)
            check = run_cli(project, "check")
            self.assertEqual(check.returncode, 0, check.stderr)
            self.snapshot(project)
            again = update()
            self.assertIn("0 updated, 0 added, 0 removed, 0 to merge", again.stdout, "reported once, not on every update")
            (kit / "docs/delegation.md").write_text((kit / "docs/delegation.md").read_text() + "\nKit C note.\n")
            self.snapshot(kit)
            self.assertIn("merge: docs/delegation.md", update().stdout, "a new kit change to the same file is reported again")
            self.assertIn("Our team rule.", (project / "docs/delegation.md").read_text())


    def test_reverted_conflict_updates_again_and_first_update_names_its_origin(self) -> None:
        # Issue #15: a conflicted file the project reverted to its shipped version gets later kit fixes;
        # a genuinely edited file is still left alone; a lock without a version says so plainly.
        from kit import trial
        with tempfile.TemporaryDirectory() as temp:
            kit, project = Path(temp) / "kit", Path(temp) / "project"
            trial._copy(TOOLS.parent, core.repository_files(TOOLS.parent), kit)
            self.git(kit, "init", "-q", "-b", "main")
            self.snapshot(kit)
            trial.prepare(kit, {"id": "demo", "kind": "cli", "mode": "new", "prompt": "x"}, project)
            lock_path = project / "tools/kit-lock.json"
            lock = json.loads(lock_path.read_text())
            lock["kit_version"] = "unknown"
            lock_path.write_text(json.dumps(lock))
            shipped = (project / "docs/delegation.md").read_text()
            (project / "docs/delegation.md").write_text(shipped + "\nOur team rule.\n")
            (project / "docs/operations.md").write_text((project / "docs/operations.md").read_text() + "\nOur runbook.\n")
            self.snapshot(project)
            for doc in ("docs/delegation.md", "docs/operations.md"):
                (kit / doc).write_text((kit / doc).read_text() + "\nKit B note.\n")
            self.snapshot(kit)
            update = lambda: run_cli(project, "kit-update", "--kit", str(kit))
            first = update()
            self.assertIn("no version recorded before", first.stdout, first.stdout + first.stderr)
            self.assertNotIn("was unknown", first.stdout)
            self.assertIn("merge: docs/delegation.md", first.stdout)
            (project / "docs/delegation.md").write_text(shipped)  # the project gives up its edit
            for staged in (project / ".agent/kit-update").rglob("*"):
                if staged.is_file():
                    staged.unlink()
            self.snapshot(project)
            for doc in ("docs/delegation.md", "docs/operations.md"):
                (kit / doc).write_text((kit / doc).read_text() + "\nKit C note.\n")
            self.snapshot(kit)
            second = update()
            self.assertIn("Kit C note.", (project / "docs/delegation.md").read_text(), second.stdout)
            self.assertIn("Our runbook.", (project / "docs/operations.md").read_text(), "a real edit stays")
            self.assertNotIn("Kit C note.", (project / "docs/operations.md").read_text())
            self.assertIn("merge: docs/operations.md", second.stdout)
            head = self.git(kit, "rev-parse", "HEAD").strip()
            self.assertEqual(json.loads(lock_path.read_text())["kit_version"], head, "a known version is recorded")


@template_only
class InitOwnerTests(Scratch):
    def test_init_names_the_owner_everywhere_and_refuses_emails(self) -> None:
        from kit import trial
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            trial._copy(TOOLS.parent, core.repository_files(TOOLS.parent), project)
            def init(owner: str) -> subprocess.CompletedProcess[str]:
                return run_cli(project, "init", "--name", "demo", "--kind", "web", "--owner", owner)
            self.assertIn("not an email", init("me@example.com").stderr)
            self.assertEqual(init("octocat").returncode, 0)
            self.assertIn('owners = ["octocat"]', (project / "project.toml").read_text())
            self.assertNotIn("project-owner", (project / "project.toml").read_text())
            self.assertIn("Owner: octocat", (project / "VISION.md").read_text())


@template_only
class AdoptTests(Scratch):
    """make adopt brings the kit into an existing repository without overwriting it."""

    def setUp(self) -> None:
        super().setUp()
        shutil.copytree(TOOLS.parent / ".agents/trials/seeds/notes-api", self.root / "notes")
        self.root = self.root / "notes"
        git_in(self.root, "init", "-q", "-b", "main")
        git_in(self.root, "add", "-A")
        git_in(self.root, "commit", "-q", "-m", "existing")

    def adopt(self) -> subprocess.CompletedProcess[str]:
        return self.cli("adopt", "--from", str(TOOLS.parent),
                        "--name", "notes-api", "--kind", "api", "--owner", "notes-team")

    def test_adopt_merges_instead_of_overwriting(self) -> None:
        readme_before = (self.root / "README.md").read_text()
        result = self.adopt()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("renamed: kit-help, kit-test", result.stdout)
        self.assertIn("runs only the toolchain-free gate", result.stdout, "adopt says what kit-ci does not run (#67)")
        self.assertTrue((self.root / "README.md").read_text().startswith(readme_before), "the project's README is kept")
        self.assertIn("Copyright (c) 2025 Notes Team", (self.root / "LICENSE").read_text())
        self.assertIn('license = "MIT"', (self.root / "project.toml").read_text())
        self.assertTrue((self.root / ".github/workflows/kit-ci.yml").is_file(), "colliding workflow written beside it")
        self.assertIn("<!-- index: design | Notes API |", (self.root / "docs/api.md").read_text())
        make = lambda *args: subprocess.run(["make", "-s", *args], cwd=self.root, capture_output=True, text=True,
                                            env=clean_env())
        self.assertIn("make test     run the tests", make().stdout, "the project's default goal stays first")
        self.assertIn("Next (intake)", make("next").stdout, "kit targets work through include kit.mk")
        check = self.cli("check")
        problems = [line for line in check.stderr.splitlines() if line.startswith("- ")]
        self.assertTrue(problems and all("unregistered product surface" in line for line in problems), check.stderr)
        self.assertIn("infrastructure_paths", check.stderr, "the message names the fix")
        from kit import docs
        docs.check_markdown_links(self.root)  # links to pruned template material point at the template source
        # Trial specs have exactly one owner doc (docs/evals.md binds .agents/trials/**). An adopted
        # project prunes the specs, so every binding to them must go with them (EL-002): nothing in
        # the project may claim them any more, and in the template they are claimed exactly once.
        def trial_binders(root: Path, files: list[str]) -> set[str]:
            bindings = docmeta.bindings(root, files)
            return {doc for doc, globs in bindings.items() if any(".agents/trials" in glob for glob in globs)}

        self.assertEqual(trial_binders(self.root, core.repository_files(self.root)), set(),
                         "a binding to pruned trial specs must be dropped, or check reports it dead")
        self.assertEqual(trial_binders(TOOLS.parent, core.repository_files(TOOLS.parent)),
                         {"docs/evals.md"}, "the evals owner doc binds trial specs, and it alone")
        finish = self.cli("finish")
        self.assertEqual(finish.returncode, 0, finish.stdout)
        self.assertEqual(self.adopt().returncode, 1, "adopting twice is refused")
        self.git("add", "-A")
        self.git("commit", "-qm", "adopt")
        update = self.cli("kit-update", "--kit", str(TOOLS.parent))
        self.assertIn("0 updated, 0 added, 0 removed, 0 to merge", update.stdout, update.stdout + update.stderr)

    def test_adopt_records_that_the_product_existed_already(self) -> None:
        """#58: `make next` can only skip competitor research for an adopted project if adopt
        leaves a trace; `make init` must record the opposite, or the step never comes back."""
        self.assertEqual(self.adopt().returncode, 0)
        self.assertIn('project_mode = "adopt"', (self.root / "project.toml").read_text())
        self.assertNotIn("Next (research)", self.cli("next").stdout)

    def test_adopted_project_passes_the_kit_suite_and_keeps_its_own_kit_paths_quiet(self) -> None:
        # The project's own ci.yml and a doc at a kit path stay the project's, and the kit suite still passes.
        (self.root / "docs/operations.md").write_text("# How we run it\n\nOur runbook.\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "runbook")
        self.assertEqual(self.adopt().returncode, 0)
        self.assertIn("Our runbook.", (self.root / "docs/operations.md").read_text())
        suite = subprocess.run(["make", "kit-test"], cwd=self.root, capture_output=True, text=True, timeout=900,
                               env=clean_env(**({} if os.environ.get("KIT_SLOW") == "1" else {"KIT_INNER": "1"})))
        self.assertEqual(suite.returncode, 0, suite.stderr[-2500:])
        self.git("add", "-A")
        self.git("commit", "-qm", "adopt")
        update = self.cli("kit-update", "--kit", str(TOOLS.parent))
        self.assertIn("0 updated, 0 added, 0 removed, 0 to merge", update.stdout, update.stdout + update.stderr)

    def test_adopt_refuses_uncommitted_work(self) -> None:
        (self.root / "notes/new.py").write_text("X = 1\n")
        self.assertIn("commit or stash", self.adopt().stderr)


if __name__ == "__main__":
    unittest.main()
