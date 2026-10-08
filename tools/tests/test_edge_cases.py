"""Kit edge cases: each small defect from #51 has a test that fails without its fix."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import Scratch, clean_env, git_in, template_only  # noqa: E402

from kit import adopt, config, core, gitinfo, hygiene, launch, product, risk  # noqa: E402
from kit.core import RepoctlError  # noqa: E402
from kit.registry import Registry, frontmatter  # noqa: E402

MANIFEST = 'schema = 1\nname = "Demo"\nkind = "template"\nphase = "bootstrap"\nlicense = "UNSELECTED"\nowners = []\n'
AGENT = ('---\nname: x\ndescription: "A role with \\"quotes\\""\naccess: read-only\ntier: fast\n---\nBody\n')


class FrontmatterTests(Scratch):
    def test_crlf_and_bom_frontmatter_parse(self) -> None:
        for text in (AGENT.replace("\n", "\r\n"), "﻿" + AGENT):
            self.assertEqual(frontmatter(text).get("name"), "x", repr(text[:10]))

    def test_quoted_values_are_unescaped(self) -> None:
        self.assertEqual(frontmatter(AGENT)["description"], 'A role with "quotes"')
        self.assertEqual(frontmatter("---\nname: 'it''s'\n---\n")["name"], "it's")

    def test_crlf_agent_file_loads_as_a_capability(self) -> None:
        self.write("project.toml", MANIFEST)
        self.write(".agents/agents/x.md", AGENT.replace("\n", "\r\n").encode())
        names = [item.name for item in Registry(self.root).of("agent", enabled_only=False)]
        self.assertIn("x", names)

    def test_frontmatter_error_names_the_file(self) -> None:
        self.write("project.toml", MANIFEST)
        self.write(".agents/agents/x.md", "---\nname: x\ndescription: a: b\naccess: full\ntier: fast\n---\n")
        with self.assertRaisesRegex(RepoctlError, r"x\.md.*': '"):
            Registry(self.root).of("agent", enabled_only=False)


class BoolSettingTests(Scratch):
    def test_bool_is_rejected_where_a_number_is_required(self) -> None:
        with self.assertRaisesRegex(RepoctlError, r"overlap_limit must be a float"):
            config.project_setting({"kit": {"overlap_limit": True}}, "overlap_limit")
        self.assertEqual(config.project_setting({"kit": {"overlap_limit": 1}}, "overlap_limit"), 1)

    def test_bool_budget_is_rejected(self) -> None:
        self.write("a.md", "x\n")
        errors = hygiene.budget_errors(self.root, {"budgets": {"a.md": True}}, ["a.md"])
        self.assertTrue(any("positive integer" in item for item in errors), errors)


class NonUtf8PathTests(Scratch):
    """K-20: a tracked path that is not UTF-8 must not crash the git readers."""

    BAD = "caf\udce9.txt"  # surrogate-escaped 0xE9, as os.fsdecode returns it

    def _index_bad_path(self) -> None:
        # Staged by index entry, not on disk: some filesystems (APFS) refuse such names.
        git_in(self.root, "init", "-q")
        sha = subprocess.run(["git", "-C", str(self.root), "hash-object", "-w", "--stdin"], input=b"x\n",
                             capture_output=True, check=True, env=clean_env()).stdout.decode().strip()
        subprocess.run(["git", "-C", str(self.root), "update-index", "--add", "--cacheinfo", f"100644,{sha},{self.BAD}"],
                       check=True, capture_output=True, env=clean_env())

    def test_git_output_with_a_non_utf8_path_is_returned_not_raised(self) -> None:
        self._index_bad_path()
        listed = gitinfo.git(self.root, "ls-files", "-z")
        self.assertIsNotNone(listed)
        self.assertEqual(listed.split("\0")[0], self.BAD)

    def test_worktree_files_survives_a_non_utf8_tracked_path(self) -> None:
        self._index_bad_path()
        self.write("ok.txt", "fine\n")
        names = [path.name for path in core.worktree_files(self.root)]
        self.assertIn("ok.txt", names)  # the bad path is deleted from the tree, so it is skipped, not fatal

    def test_walk_fallback_differs_from_git_only_by_design(self) -> None:
        # Outside a repository there is no ignore file to read: the walk lists everything but IGNORED_WALK_DIRECTORIES.
        self.write("src/a.py", "x = 1\n")
        self.write("node_modules/dep/index.js", "x\n")
        self.assertEqual([path.name for path in core.worktree_files(self.root)], ["a.py"])
        git_in(self.root, "init", "-q")
        self.write(".gitignore", "build/\n")
        self.write("build/out.txt", "x\n")
        names = {path.relative_to(self.root).as_posix() for path in core.worktree_files(self.root)}
        self.assertIn("node_modules/dep/index.js", names)  # git, not the walk, owns the set inside a repository
        self.assertNotIn("build/out.txt", names)


class RegulatedEvidenceTests(Scratch):
    """G-22 (refuted): `Commit: <HEAD>` evidence is checkable because it is read from the working tree.

    The evidence file does not have to be committed to be filed; only a commit made *after* writing it
    moves HEAD and makes it stale, which is the intended "evidence about older work" rejection.
    """

    def evidence(self, commit: str, body: str) -> None:
        import hashlib
        digest = hashlib.sha256(body.encode()).hexdigest()
        self.write("review.md", f"Issue: #1\nCommit: {commit}\nArtifact: review.md\nReviewer: octocat\n"
                                f"Date: {core.today().isoformat()}\nResult: pass\nBody-SHA256: {digest}\n")

    def test_uncommitted_evidence_naming_head_is_accepted_and_goes_stale_after_a_commit(self) -> None:
        from kit import issues
        git_in(self.root, "init", "-q")
        self.write("a.txt", "a\n")
        self.commit("base")
        head = self.git("rev-parse", "HEAD").strip()
        self.evidence(head, "body")
        issues.validate_review_evidence(self.root, "review.md", body="body", strict=True)
        self.commit("evidence")
        with self.assertRaisesRegex(RepoctlError, "not bound to current HEAD"):
            issues.validate_review_evidence(self.root, "review.md", body="body", strict=True)

    def test_a_wrong_commit_is_rejected_and_the_agent_first_profile_does_not_compare(self) -> None:
        from kit import issues
        git_in(self.root, "init", "-q")
        self.write("a.txt", "a\n")
        self.commit("base")
        self.evidence("a" * 40, "body")
        with self.assertRaisesRegex(RepoctlError, "not bound to current HEAD"):
            issues.validate_review_evidence(self.root, "review.md", body="body", strict=True)
        issues.validate_review_evidence(self.root, "review.md", body="body", strict=False)


class EvidenceReadTests(Scratch):
    """K-24: any unreadable evidence path is a named finding, not only a missing one."""

    def test_directory_or_binary_review_evidence_is_a_named_error(self) -> None:
        from kit import issues
        self.write("evidence/placeholder.txt", "x\n")
        self.write("binary.md", b"\xff\xfe\x00bad")
        for name in ("evidence", "binary.md"):
            with self.assertRaisesRegex(RepoctlError, rf"review evidence cannot be read: {name}"):
                issues.validate_review_evidence(self.root, name)
        with self.assertRaisesRegex(RepoctlError, "does not exist"):
            issues.validate_review_evidence(self.root, "missing.md")

    def test_directory_critic_evidence_is_a_named_error(self) -> None:
        from kit import structure
        self.write("evidence/placeholder.txt", "x\n")
        surface = {"id": "app", "critic_evidence": ["evidence"]}
        with self.assertRaisesRegex(RepoctlError, "critic evidence cannot be read: evidence"):
            structure.validate_critic_evidence(self.root, surface)


class FollowUpTests(Scratch):
    """#51 follow-ups: each item is either a behaviour below or a recorded decision in the issue."""

    def test_k21_docs_index_reads_the_tracked_document_set_and_links_with_anchors(self) -> None:
        from kit import docs
        git_in(self.root, "init", "-q")
        self.write(".gitignore", "docs/scratch/\n")
        self.write("docs/README.md", "# Docs\n- [A](./a.md#top)\n- [B](sub/b.md)\n")
        self.write("docs/a.md", "# A\n")
        self.write("docs/sub/b.md", "# B\n")
        self.write("docs/scratch/ignored.md", "# Ignored\n")  # not part of the repository, so not owed a link
        docs.check_docs_index(self.root)
        self.write("docs/sub/c.md", "# C\n")
        with self.assertRaisesRegex(RepoctlError, r"not linked from docs/README.md: sub/c.md"):
            docs.check_docs_index(self.root)

    def test_k23_skill_folder_without_skill_md_is_an_advisory_finding(self) -> None:
        from types import SimpleNamespace
        from kit import checks
        files = [".agents/skills/good/SKILL.md", ".agents/skills/good/run.py", ".agents/skills/orphan/notes.md"]
        findings = checks.skill_folders_without_manifest(SimpleNamespace(files=files))
        self.assertEqual(len(findings), 1)
        self.assertIn(".agents/skills/orphan/", findings[0])
        self.write("project.toml", MANIFEST)
        by_name = {item.name: item for item in Registry(self.root).of("check", enabled_only=False)}
        self.assertFalse(by_name["skill-folders-without-manifest"].fields["blocks"])

    def test_k27_glob_brackets_and_braces_are_literal_and_the_dead_binding_says_so(self) -> None:
        from kit import docsync
        self.assertTrue(gitinfo.path_matches("app/[id]/page.tsx", "app/[id]/*.tsx"))
        self.assertFalse(gitinfo.path_matches("app/1/page.tsx", "app/[id]/*.tsx"))
        self.assertFalse(gitinfo.path_matches("src/a.py", "src/{a,b}.py"))
        message = docsync.dead_bindings({"docs/x.md": ["src/[ab].py"]}, ["src/a.py"])[0]
        self.assertIn("covers pattern matches no file: src/[ab].py", message)
        self.assertIn("literal", message)
        plain = docsync.dead_bindings({"docs/x.md": ["src/*.js"]}, ["src/a.py"])[0]
        self.assertNotIn("literal", plain)

    def test_k28_findings_travel_on_the_error_not_in_its_text(self) -> None:
        from kit import checks
        awkward = ["first\n- looks like a second item", "second: with colon"]

        def fail():
            raise core.check_failed("demo", awkward)

        def plain():
            raise RepoctlError("one problem:\n- not from a gate")

        self.assertEqual(checks._raised(fail), awkward)
        self.assertEqual(checks._raised(plain), ["one problem:\n- not from a gate"])
        self.assertEqual(checks._raised(lambda: None), [])


class RiskTests(Scratch):
    def test_non_table_repository_is_not_an_attribute_error(self) -> None:
        self.write("project.toml", MANIFEST + "repository = 3\n")
        git_in(self.root, "init", "-q")
        tier, _ = risk.assess(self.root)  # already handled before this change; the test keeps it so
        self.assertEqual(tier, "normal")
        self.assertNotIn("Traceback", self.cli("risk").stderr)


class FeaturesTests(Scratch):
    def test_malformed_features_csv_does_not_kill_next(self) -> None:
        self.write("project.toml", MANIFEST.replace('"template"', '"web"').replace("bootstrap", "development"))
        self.write("features.csv", "feature,priority,status\nlogin,urgent,no\n")
        step = product.next_step(self.root)
        self.assertIn(step["phase"], {"intake", "features"})
        if step["phase"] == "features":
            self.assertIn("priority must be", step["action"])


class AdoptTests(Scratch):
    def test_non_utf8_doc_survives_indexing_unchanged(self) -> None:
        raw = b"# Caf\xe9 notes\nbody\n"
        self.write("docs/old.md", raw)
        self.write("docs/ok.md", "# Fine\n")
        adopt.index_existing_docs(self.root, {"docs/old.md", "docs/ok.md"})
        self.assertEqual((self.root / "docs/old.md").read_bytes(), raw)
        self.assertIn("<!-- index:", (self.root / "docs/ok.md").read_text())


class LaunchRouteTests(unittest.TestCase):
    def test_placeholder_hosts_and_subdomains_are_rejected(self) -> None:
        for host in ("localhost", "example.com", "foo.example.com", "box.local", "x.internal"):
            self.assertFalse(launch.valid_private_route(f"https://{host}/report"), host)
        self.assertTrue(launch.valid_private_route("https://security.acme.io/report"))
        self.assertTrue(launch.valid_private_route("https://attacker.io/report"))


class SecondPassTests(Scratch):
    def test_skill_review_message_names_the_configured_window(self) -> None:
        from types import SimpleNamespace
        from kit import checks
        self.write("project.toml", MANIFEST + "[kit]\nskill_review_days = 30\n")
        project = {"skills": [{"package": "p", "reviewed_on": "2000-01-01"}]}
        findings = checks.skill_review_age(SimpleNamespace(project=project, root=self.root))
        self.assertTrue(findings and "30 days" in findings[0], findings)

    def test_infrastructure_path_message_does_not_say_surface(self) -> None:
        from kit import core
        with self.assertRaisesRegex(RepoctlError, r"^infrastructure path must stay"):
            core.normalized_relative_path("../x", "infrastructure path")

    def test_links_in_inline_code_are_not_links_and_parens_in_targets_work(self) -> None:
        from kit import docs
        self.write("project.toml", MANIFEST)
        self.write("docs/real(1).md", "# Real\n")
        self.write("docs/a.md", "# A\nUse `[x](nowhere.md)` here, and [y](real(1).md).\n")
        git_in(self.root, "init", "-q")
        docs.check_markdown_links(self.root)

    def test_malformed_doc_meta_cache_is_recomputed(self) -> None:
        import json
        from kit import docmeta
        self.write("docs/a.md", "# A\n<!-- covers: tools/** -->\n")
        path = self.root / docmeta.META_CACHE
        status = (self.root / "docs/a.md").stat()
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = [status.st_mtime_ns, status.st_size]
        path.write_text(json.dumps({"version": 3, "entries": {"docs/a.md": [stamp, {"index": None}]}}))
        meta = docmeta.doc_meta(self.root, ["docs/a.md"])
        self.assertEqual(meta["docs/a.md"]["covers"], ["tools/**"])

    def test_doc_name_collisions_are_reported(self) -> None:
        from kit import docsync
        self.write("project.toml", MANIFEST)
        line = "<!-- index: design | owns | when -->"
        self.write("docs/a-b.md", f"# One\n{line}\n")
        self.write("docs/a/b.md", f"# Two\n{line}\n")
        errors = docsync.index_errors(self.root, ["docs/a-b.md", "docs/a/b.md"])
        self.assertTrue(any("collides" in item for item in errors), errors)

    @template_only  # adopts from the template checkout
    def test_adopt_reports_renamed_workflow_and_copied_license(self) -> None:
        import contextlib
        import io
        git_in(self.root, "init", "-q")
        self.write("src/app.py", "print(1)\n")
        self.write(".github/workflows/ci.yml", "name: ci\non: push\njobs: {}\n")
        self.commit("init")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            adopt.adopt(self.root, TOOLS.parent, "demo", "web", None)
        self.assertTrue((self.root / ".github/workflows/kit-ci.yml").is_file())
        self.assertIn("no LICENSE of yours", out.getvalue())


class RecordBindingTests(Scratch):
    """'Not bound to project.toml' says which line binds it (round-4 Haiku tidepool trial)."""

    def check(self, body: str) -> None:
        from kit import structure
        self.write("docs/STACK-DECISION.md", body)
        structure._check_record(self.root, {"name": "tidepool"}, "docs/STACK-DECISION.md", "stack decision record",
                                "project stack decision", False, status_message="must be accepted",
                                unbound_message="stack decision record is not bound to project.toml",
                                accepted_first=False)

    def test_the_message_names_the_line_and_adding_it_fixes_it(self) -> None:
        today = core.today().isoformat()
        with self.assertRaisesRegex(RepoctlError, r"needs the line 'Project: tidepool'"):
            self.check(f"# Stack\n\n**Project:** tidepool\nStatus: accepted\nOwner: o\nDate: {today}\n")
        self.check(f"# Stack\n\nProject: tidepool\nStatus: accepted\nOwner: o\nDate: {today}\n")


if __name__ == "__main__":
    unittest.main()
