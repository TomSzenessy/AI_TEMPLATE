from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPOCTL = Path(__file__).resolve().parents[1] / "repoctl.py"


class RepoctlCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.write("project.toml", """schema = 1
name = "REPLACE_WITH_PROJECT_NAME"
kind = "template"
phase = "bootstrap"
license = "UNSELECTED"
owners = []
[governance]
profile = "regulated"
""")
        self.write("docs/README.md", "# Docs\n")
        self.write("review.md", "Issue: #42\nCommit: " + "a" * 40 + "\nArtifact: review.md\nReviewer: test reviewer\nDate: 2026-08-25\nResult: pass\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, name: str, content: str | bytes) -> Path:
        if name == "project.toml" and isinstance(content, str) and "[vision]" not in content:
            name_match = re.search(r'^name = "([^"]+)"', content, re.MULTILINE)
            kind_match = re.search(r'^kind = "([^"]+)"', content, re.MULTILINE)
            project_name = name_match.group(1) if name_match else "Demo"
            project_kind = kind_match.group(1) if kind_match else "web"
            content += f'''\n[vision]\nstatus = "accepted"\nrecord = "VISION.md"\nstack_decision = "docs/STACK-DECISION.md"\n'''
            (self.root / "VISION.md").write_text(
                f"# Project vision\n\nStatus: accepted\nProject: {project_name}\nOwner: test owner\nDate: 2026-08-25\n",
                encoding="utf-8",
            )
            (self.root / "docs" / "STACK-DECISION.md").parent.mkdir(parents=True, exist_ok=True)
            (self.root / "docs" / "STACK-DECISION.md").write_text(
                f"# Stack\n\nStatus: accepted\nProject: {project_name}\nOwner: test owner\nDate: 2026-08-25\n",
                encoding="utf-8",
            )
        if name == "docs/README.md" and isinstance(content, str) and "STACK-DECISION.md" not in content:
            content += "\n- [Stack decision](STACK-DECISION.md)\n"
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(textwrap.dedent(content), encoding="utf-8")
        return path

    def cli(self, *args: str, env: dict[str, str] | None = None):
        environment = os.environ.copy()
        if env:
            environment.update(env)
        return subprocess.run(
            [sys.executable, str(REPOCTL), "--root", str(self.root), *args],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

    def issue_body(self, safe: bool = True) -> str:
        review = "not applicable" if safe else "private security review"
        return textwrap.dedent(f"""\
            Duplicate check: searched title, symptom, and path for the affected flow; no duplicate found
            ### Summary
            The login refresh flow rejects a valid session and affects authentication users.
            ### What happens
            Observed a valid session is rejected after refresh; expected the session to remain valid.
            ### Where
            Authentication adapter and session refresh route (src/auth/session.ts).
            ### When
            After a valid session is refreshed in the staging environment.
            ### Why
            The refresh validation path does not accept the renewed session.
            ### How to reproduce
            1. Create a valid test session.
            2. Refresh it and inspect the response.
            ### Impact and scope
            Authentication sessions only; no payment or administrator access.
            ### Acceptance criteria
            - [ ] An integration test verifies a valid session survives refresh.
            - [ ] Negative test verifies an expired session remains rejected.
            ### Evidence
            Test evidence: integration result and API response.
            Artifact: review.md
            ### Disclosure classification
            - **Disclosure class:** ordinary
            - **Public-safe:** yes
            - **Security/privacy review:** {review}
            - **Reviewer/date:** 2026-08-25 test reviewer
            ### Dependencies and handoff
            - **Owner / next action:** test owner; implement and verify the refresh path
            """)

    def issue_args(self, safe: bool = True) -> list[str]:
        issue_path = self.root / "issue.md"
        if issue_path.exists():
            body_hash = hashlib.sha256(issue_path.read_bytes()).hexdigest()
            self.write(
                "review.md",
                "Issue: #42\nCommit: " + "a" * 40 + "\nArtifact: review.md\n"
                "Reviewer: test reviewer\nDate: 2026-08-25\nResult: pass\n"
                f"Body-SHA256: {body_hash}\n",
            )
        return [
            "issue", "--title", "Login refresh rejects valid sessions", "--body-file", "issue.md",
            "--type", "bug" if safe else "security", "--priority", "P1", "--area",
            "repo" if safe else "security", "--topic", "session-refresh", "--status", "triage",
            "--surface", "repo" if safe else "security", "--public-reviewed", "--review-evidence", "review.md",
        ]

    def github(self, duplicate: bool = False, results: list[dict] | None = None) -> tuple[Path, Path]:
        directory = self.root / "bin"
        directory.mkdir(exist_ok=True)
        log = directory / "gh.log"
        search_results = results if results is not None else ([{"number": 12, "title": "Login refresh rejects valid sessions", "url": "https://example.test/12", "state": "OPEN"}] if duplicate else [])
        results_literal = json.dumps(search_results)
        script = f"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if args[:2] == ['repo', 'view']:
    print(json.dumps({{'nameWithOwner': 'example/project'}}))
elif args[:2] == ['issue', 'list']:
    print({results_literal!r})
elif args[:2] == ['issue', 'create']:
    Path(os.environ['GH_LOG']).write_text(json.dumps({{'args': args, 'stdin': sys.stdin.read()}}), encoding='utf-8')
    print('https://github.com/example/project/issues/17')
elif args[:2] == ['label', 'create']:
    Path(os.environ['GH_LOG']).open('a', encoding='utf-8').write('\\n'.join(args) + '\\n')
else:
    raise SystemExit(2)
"""
        fake = directory / "gh"
        fake.write_text(script, encoding="utf-8")
        fake.chmod(0o755)
        return directory, log

    def test_init_replaces_template_readme(self) -> None:
        self.write("README.md", """# Agent Template
<!-- repoctl:project-readme -->
> **Template mode:** replace this.

```bash
cp -R AGENT_TEMPLATE my-project
```
""")
        result = self.cli("init", "--name", "Demo", "--kind", "web")
        self.assertEqual(result.returncode, 0, result.stderr)
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn("# Demo", readme)
        self.assertIn("Project initialized", readme)
        self.assertNotIn("cp -R AGENT_TEMPLATE my-project", readme)
        self.assertEqual(self.cli("check").returncode, 0)

    def test_init_replaces_shipped_surface_and_preserves_trailing_tables(self) -> None:
        shipped = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
        self.write("README.md", shipped)
        self.write("project.toml", """schema = 1
name = "AI_TEMPLATE"
kind = "template"
phase = "development"
license = "MIT"
owners = ["TomSzenessy"]
[repository]
github = "example/project"
[governance]
profile = "agent-first"
[vision]
status = "accepted"
record = "VISION.md"
stack_decision = "docs/STACK-DECISION.md"
[[surfaces]]
id = "template"
path = "."
kind = "template"
owner = "TomSzenessy"
status = "active"
quality_oracle = "template governance"
verification = [["python3", "tools/repoctl.py", "check"]]
[[skills]]
package = "example/tool@demo"
source = "https://github.com/example/tool"
revision = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
content_digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
purpose = "bounded test capability"
reviewed_on = "2026-08-25"
permissions = "read-only / project-local"
rollback = "remove the project-local skill and restore the previous lockfile"
""")
        result = self.cli("init", "--name", "Demo", "--kind", "game")
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = (self.root / "project.toml").read_text(encoding="utf-8")
        self.assertIn('id = "template-bootstrap"', manifest)
        self.assertIn("[[skills]]", manifest)
        self.assertIn("content_digest", manifest)
        self.assertNotIn("make init NAME=my-project", (self.root / "README.md").read_text(encoding="utf-8"))

    def test_infrastructure_defaults_and_root_surface_rogue_detection(self) -> None:
        (self.root / "tests").mkdir()
        (self.root / "config").mkdir()
        (self.root / "apps" / "rogue").mkdir(parents=True)
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
license = "MIT"
owners = ["team"]
[repository]
infrastructure_paths = ["tests", "config"]
""")
        self.write("LICENSE", "MIT")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unregistered product surface: apps/rogue", result.stderr)

    def test_infrastructure_cannot_hide_container_or_surface(self) -> None:
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
[repository]
infrastructure_paths = ["apps"]
""")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot hide a product container", result.stderr)

    def test_surface_symlink_is_rejected_before_cwd(self) -> None:
        outside = self.root.parent / f"outside-surface-{self.root.name}"
        outside.mkdir()
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
[[surfaces]]
id = "app"
path = "link"
kind = "code"
owner = "team"
status = "active"
quality_oracle = "integration check"
verification = [["python3", "-c", "print('no')"]]
""")
        try:
            result = self.cli("check")
        finally:
            (self.root / "link").unlink()
            outside.rmdir()
        self.assertEqual(result.returncode, 1)
        self.assertIn("must not traverse symlink", result.stderr)

    def test_oracle_only_surface_requires_critic_evidence(self) -> None:
        self.write("README.md", "# Demo\n<!-- repoctl:project-readme -->\n> Project initialized: **Demo** (`design`).\n")
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "design"
phase = "development"
[repository]
infrastructure_paths = ["renders"]
[[surfaces]]
id = "render"
path = "."
kind = "visual"
owner = "artist"
status = "active"
quality_oracle = "Independent rendered-image comparison"
""")
        missing = self.cli("verify")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("critic_evidence", missing.stderr)
        self.write("renders/scene.png", b"png")
        self.write("review.md", "Issue: #42\nCommit: " + "a" * 40 + "\nArtifact: renders/scene.png\nReviewer: artist\nDate: 2026-08-25\nResult: pass\n")
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "design"
phase = "development"
[repository]
infrastructure_paths = ["renders"]
[[surfaces]]
id = "render"
path = "."
kind = "visual"
owner = "artist"
status = "active"
quality_oracle = "Independent rendered-image comparison"
critic_evidence = ["review.md"]
""")
        result = self.cli("verify")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("critic evidence accepted", result.stdout)

    def test_issue_requires_public_review_evidence(self) -> None:
        github, _ = self.github()
        self.write("issue.md", self.issue_body())
        self.write(".github/issue-labels.json", '{"type":["bug"],"priority":["P1"],"area":["repo"],"status":["triage"],"surface":["repo"]}')
        args = self.issue_args()
        no_review = [arg for arg in args if arg not in {"--public-reviewed", "--review-evidence", "review.md"}]
        result = self.cli(*no_review, env={"PATH": f"{github}:{os.environ['PATH']}"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("--public-reviewed", result.stderr)

    def test_issue_duplicate_guard_and_explicit_target(self) -> None:
        github, log = self.github(duplicate=True)
        self.write("issue.md", "Issue #42\n" + self.issue_body())
        self.write(".github/issue-labels.json", '{"type":["bug"],"priority":["P1"],"area":["repo"],"status":["triage"],"surface":["repo"]}')
        args = self.issue_args()
        duplicate = self.cli(*args, env={"PATH": f"{github}:{os.environ['PATH']}"})
        self.assertEqual(duplicate.returncode, 1)
        self.assertIn("possible duplicate #12", duplicate.stderr)
        self.github(False)
        created = self.cli(*args, env={"PATH": f"{github}:{os.environ['PATH']}", "GH_LOG": str(log)})
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn("https://github.com/example/project/issues/17", created.stdout)
        self.assertIn("--repo", log.read_text(encoding="utf-8"))

    def test_duplicate_search_ignores_unrelated_hit_but_matches_same_path(self) -> None:
        self.write("issue.md", "Issue #42\n" + self.issue_body())
        self.write(".github/issue-labels.json", '{"type":["bug"],"priority":["P1"],"area":["repo"],"status":["triage"],"surface":["repo"]}')
        args = self.issue_args()
        unrelated = [{"number": 12, "title": "Unrelated title", "body": "Different module and symptom", "url": "u", "state": "OPEN"}]
        github, log = self.github(results=unrelated)
        result = self.cli(*args, env={"PATH": f"{github}:{os.environ['PATH']}", "GH_LOG": str(log)})
        self.assertEqual(result.returncode, 0, result.stderr)
        same_path = [{"number": 13, "title": "Different title", "body": "Authentication adapter and session refresh route (src/auth/session.ts)", "url": "u", "state": "OPEN"}]
        self.github(results=same_path)
        result = self.cli(*args, env={"PATH": f"{github}:{os.environ['PATH']}", "GH_LOG": str(log)})
        self.assertEqual(result.returncode, 1)
        self.assertIn("possible duplicate #13", result.stderr)

        github, _ = self.github()
        self.write("issue.md", self.issue_body(False))
        self.write(".github/issue-labels.json", '{"type":["security"],"priority":["P1"],"area":["security"],"status":["triage"],"surface":["security"]}')
        result = self.cli(*self.issue_args(False), env={"PATH": f"{github}:{os.environ['PATH']}"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot be filed through the public issue adapter", result.stderr)

    def test_issue_body_requires_duplicate_content_and_evidence(self) -> None:
        github, _ = self.github()
        self.write(".github/issue-labels.json", '{"type":["bug"],"priority":["P1"],"area":["repo"],"status":["triage"],"surface":["repo"]}')
        self.write("issue.md", "### Summary\nplaceholder")
        result = self.cli(*self.issue_args(), env={"PATH": f"{github}:{os.environ['PATH']}"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing headings", result.stderr)

    def test_fixed_status_requires_resolution(self) -> None:
        github, _ = self.github()
        self.write("issue.md", self.issue_body())
        self.write(".github/issue-labels.json", '{"type":["bug"],"priority":["P1"],"area":["repo"],"status":["triage"],"surface":["repo"]}')
        args = self.issue_args()
        args[args.index("triage")] = "fixed"
        result = self.cli(*args, env={"PATH": f"{github}:{os.environ['PATH']}"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("resolution record", result.stderr)

    def test_issue_body_and_review_packet_reject_secrets(self) -> None:
        result = self.cli("incident", "--title", "ghp_" + "a" * 30, "--summary", "safe")
        self.assertEqual(result.returncode, 1)
        self.assertIn("possible secret", result.stderr)
        self.write("issue.md", "Issue #42\n" + self.issue_body())
        self.write("secret.txt", "ghp_" + "a" * 30)
        result = self.cli("review-packet", "--issue-file", "issue.md")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_review_packet_requires_canonical_issue(self) -> None:
        self.write("issue.md", "Issue #42\n" + self.issue_body())
        result = self.cli("review-packet", "--issue-file", "issue.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write("issue.md", "### Acceptance criteria\n- [ ] do it\n")
        result = self.cli("review-packet", "--issue-file", "issue.md")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing headings", result.stderr)

    def test_skill_provenance_is_strict(self) -> None:
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
[[skills]]
package = "owner/repo@skill"
source = "https://github.com/evil/repo"
revision = "0000000000000000000000000000000000000000"
purpose = "test"
reviewed_on = "2099-01-01"
permissions = "global production write"
rollback = "none"
""")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("source does not match", result.stderr)
        self.assertIn("future", result.stderr)
        self.assertIn("permissions", result.stderr)

    def test_bundled_skill_links_are_checked_in_fallback(self) -> None:
        self.write(".agents/skills/agent-handover/SKILL.md", "# Broken\n\n[bad](../../missing.md)\n")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn(".agents/skills/agent-handover/SKILL.md", result.stderr)

    def test_unregistered_skill_directory_is_rejected(self) -> None:
        self.write(".agents/skills/attacker/SKILL.md", "# Unregistered\n")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not allowlisted", result.stderr)

    def test_review_packet_redacts_private_key_blocks_from_patch(self) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        self.write("tracked.txt", "safe\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=self.root, check=True)
        self.write(
            "tracked.txt",
            "-----BEGIN " + "PRIVATE KEY-----\nsecret-base64-body\n" + "-----END PRIVATE KEY-----\n",
        )
        self.write("issue.md", "Issue #42\n" + self.issue_body())
        result = self.cli("review-packet", "--issue-file", "issue.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("secret-base64-body", result.stdout)
        self.assertIn("[REDACTED]", result.stdout)

        root = Path(__file__).resolve().parents[2]
        for name in ("config.yml", "bug.yml", "improvement.yml", "feature.yml"):
            content = (root / ".github" / "ISSUE_TEMPLATE" / name).read_text(encoding="utf-8")
            self.assertIn("Disclosure classification", content)
            self.assertIn("public-safe", content)
        self.assertIn("[enhancement/P2]", (root / ".github/ISSUE_TEMPLATE/feature.yml").read_text(encoding="utf-8"))
        workflow = (root / ".github/workflows/require-issue-reference.yml").read_text(encoding="utf-8")
        self.assertIn("Fixes", workflow)
        self.assertIn("Security-Reference", workflow)

    def test_vision_intake_is_required_and_path_bound(self) -> None:
        (self.root / "project.toml").write_text("schema = 1\nname = \"Demo\"\nkind = \"web\"\nphase = \"development\"\n", encoding="utf-8")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("vision intake", result.stderr)
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
[vision]
status = "accepted"
record = "docs/other.md"
stack_decision = "docs/STACK-DECISION.md"
""")
        self.write("docs/other.md", "Status: accepted\nProject: Demo\nOwner: test\nDate: 2026-08-25\n")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exactly VISION.md", result.stderr)

        root = Path(__file__).resolve().parents[2]
        for name in ("config.yml", "bug.yml", "improvement.yml", "feature.yml"):
            content = (root / ".github" / "ISSUE_TEMPLATE" / name).read_text(encoding="utf-8")
            self.assertIn("Disclosure classification", content)
            self.assertIn("public-safe", content)
        self.assertIn("[enhancement/P2]", (root / ".github/ISSUE_TEMPLATE/feature.yml").read_text(encoding="utf-8"))
        workflow = (root / ".github/workflows/require-issue-reference.yml").read_text(encoding="utf-8")
        self.assertIn("Fixes", workflow)
        self.assertIn("Security-Reference", workflow)

    def test_agent_first_rendered_form_shape_validates(self) -> None:
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
[governance]
profile = "agent-first"
""")
        self.write("form-body.md", """### Summary
A public-safe login regression affects one test surface.
### Duplicate check
Duplicate check: searched title, symptom, and path for login/session-refresh; no duplicate found
### Acceptance criteria
- The positive login test passes in the test evidence.
- A negative expired-session test remains rejected.
### Evidence
Test evidence: integration output; Artifact: review.md
### Disclosure classification
- **Disclosure class:** ordinary
- **Public-safe:** yes
- **Security/privacy review:** not applicable
- **Reviewer/date:** tester 2026-08-25
### Dependencies and handoff
- **Owner / next action:** auth team; run the declared test
""")
        result = self.cli("validate-issue", "--body-file", "form-body.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        ready = self.cli("validate-issue", "--body-file", "form-body.md", "--status", "ready")
        self.assertEqual(ready.returncode, 0, ready.stderr)

    def test_disclosure_class_and_security_terms_fail_closed(self) -> None:
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
[governance]
profile = "agent-first"
""")
        body = """Duplicate check: searched title, symptom, and path for tenant isolation; no duplicate found
### Summary
A remote code execution flaw lets one tenant read another tenant's private data.
### Acceptance criteria
- A positive test records the intended safe behavior.
- A negative test rejects cross-tenant access.
### Evidence
Test evidence: the regression is reproducible.
### Disclosure classification
- **Disclosure class:** ordinary
- **Public-safe:** yes
- **Security/privacy review:** not applicable
- **Reviewer/date:** tester 2026-08-25
### Dependencies and handoff
- **Owner / next action:** security owner; use the private route
"""
        self.write("sensitive.md", body)
        result = self.cli("validate-issue", "--body-file", "sensitive.md")
        self.assertEqual(result.returncode, 1)
        self.assertIn("sensitive issue bodies", result.stderr)
        ssrf_body = body.replace("remote code execution flaw", "SSRF flaw")
        self.write("ssrf.md", ssrf_body)
        result = self.cli("validate-issue", "--body-file", "ssrf.md")
        self.assertEqual(result.returncode, 1)
        self.assertIn("sensitive issue bodies", result.stderr)

    def test_markdown_escape_and_unc_are_rejected(self) -> None:
        self.write("docs/guide.md", "# Guide\n\n[x](../../outside.md)\n")
        self.write("docs/unc.md", "# UNC\n\n[x](%5C%5Cattacker.example%5Cshare%5Cfile)\n")
        self.write("docs/README.md", "# Docs\n\n- [Guide](guide.md)\n- [UNC](unc.md)\n")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("escapes repository root", result.stderr)
        self.assertIn("unsafe local Markdown target", result.stderr)

    def test_structure_rejects_missing_oracle_duplicate_paths_and_bad_file_surface(self) -> None:
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
[[surfaces]]
id = "one"
path = "."
kind = "code"
owner = "team"
status = "active"
verification = [["python3", "-c", "print('ok')"]]
""")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("quality oracle", result.stderr)
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
[[surfaces]]
id = "one"
path = "."
kind = "code"
owner = "team"
status = "active"
quality_oracle = "one"
verification = [["python3", "-c", "print('ok')"]]
[[surfaces]]
id = "two"
path = "."
kind = "code"
owner = "team"
status = "active"
quality_oracle = "two"
verification = [["python3", "-c", "print('ok')"]]
""")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate surface path", result.stderr)
        self.write("app.py", "print('x')\n")
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
[[surfaces]]
id = "file"
path = "app.py"
kind = "code"
owner = "team"
status = "active"
quality_oracle = "run the script"
verification = [["python3", "app.py"]]
""")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("directory or explicit file surface", result.stderr)

    def test_single_file_inventory_and_explicit_file_surface(self) -> None:
        self.write("main.py", "print('hello')\n")
        result = self.cli("inventory")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("main.py", result.stdout)
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "script"
phase = "development"
[[surfaces]]
id = "entry"
path = "main.py"
kind = "file"
owner = "team"
status = "active"
quality_oracle = "run the entry file and inspect output"
verification = [["python3", "main.py"]]
""")
        self.write("README.md", "# Demo\n<!-- repoctl:project-readme -->\n> Project initialized: **Demo** (`script`).\n")
        self.assertEqual(self.cli("check").returncode, 0)

    def test_verification_scrubs_github_tokens_and_increments_depth(self) -> None:
        self.write("README.md", "# Demo\n<!-- repoctl:project-readme -->\n> Project initialized: **Demo** (`script`).\n")
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "script"
phase = "development"
license = "MIT"
owners = ["team"]
[[surfaces]]
id = "entry"
path = "main.py"
kind = "file"
owner = "team"
status = "active"
quality_oracle = "run the entry file and inspect output"
verification = [["python3", "-c", "import os; open('env.txt', 'w').write(os.environ.get('GH_TOKEN', '') + '|' + os.environ.get('GITHUB_TOKEN', '') + '|' + os.environ.get('REPOCTL_VERIFY_DEPTH', ''))"]]
""")
        self.write("main.py", "print('ok')\n")
        result = self.cli("verify", env={"GH_TOKEN": "gh-secret", "GITHUB_TOKEN": "github-secret"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "env.txt").read_text(encoding="utf-8"), "||1")

    def test_minimal_profile_skips_commandless_critic_gate(self) -> None:
        self.write("README.md", "# Demo\n<!-- repoctl:project-readme -->\n> Project initialized: **Demo** (`design`).\n")
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "design"
phase = "development"
[governance]
profile = "minimal"
[[surfaces]]
id = "render"
path = "."
kind = "visual"
owner = "artist"
status = "active"
quality_oracle = "human review"
""")
        result = self.cli("verify")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("minimal profile", result.stdout)

    def test_workflow_has_checkout_permissions_and_label_families(self) -> None:
        root = Path(__file__).resolve().parents[2]
        issue_workflow = (root / ".github/workflows/issue-contract.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", issue_workflow)
        self.assertIn("actions/checkout@", issue_workflow)
        self.assertIn("topic", issue_workflow)
        self.assertIn("labeled", issue_workflow)
        self.assertIn("registry_path", issue_workflow)
        self.assertIn("Disclosure class", issue_workflow)
        reference_workflow = (root / ".github/workflows/require-issue-reference.yml").read_text(encoding="utf-8")
        self.assertNotIn("security-events: read", reference_workflow)
        self.assertNotIn("security-advisories/", reference_workflow)
        self.assertIn("maintainer-attested", reference_workflow)
        self.assertIn("security-reviewed", reference_workflow)
        self.assertIn("unlabeled", reference_workflow)
        self.assertIn("closing_references", reference_workflow)
        self.assertIn("must be an open issue", reference_workflow)
        self.assertIn("canonical issue contract", reference_workflow)
        self.assertIn("PR_AUTHOR_ASSOCIATION", reference_workflow)
        self.assertIn("private security prs require", reference_workflow.casefold())
        ci_workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("GH_TOKEN", ci_workflow)
        self.assertIn("permissions: {}", ci_workflow)
        scans = (root / ".github/workflows/specialist-scans.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", scans)
        self.assertNotIn("403", scans.split("args:", 1)[1].split("fail:", 1)[0])

    def test_public_launch_fails_without_typed_evidence(self) -> None:
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "public-launch"
license = "MIT"
owners = ["team"]
[repository]
github = "example/project"
[security]
contact = ""
private_reporting = ""
[launch]
legal_review = "approved"
legal_review_ref = "x"
production_evidence = "verified"
production_evidence_refs = ["x"]
legal_document_paths = ["docs/legal/privacy-notice.template.md"]
[[surfaces]]
id = "app"
path = "."
kind = "code"
owner = "team"
status = "active"
quality_oracle = "browser review"
verification = [["python3", "-c", "print('ok')"]]
""")
        self.write("LICENSE", "MIT")
        self.write("README.md", "# Demo\n<!-- repoctl:project-readme -->\n> Project initialized: **Demo** (`web`).\n")
        self.write("docs/legal/privacy-notice.template.md", "# Draft\nProject: Demo\nLegal owner: [name/team]\nReviewer: Alice [to be confirmed]\nDate: 2026-08-25\n")
        self.write("docs/legal/data-inventory.md", "# Inventory\n")
        self.write(".security/config.json", '{"security_team_contacts": [], "security_reviewed_on": "2026-08-25", "security_reviewer": "Alice [pending]"}')
        result = self.cli("readiness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("security.contact", result.stderr)
        self.assertIn("private_reporting", result.stderr)
        self.assertIn("legal document", result.stderr)
        self.assertIn("security_reviewer", result.stderr)
    def test_owner_sentinels_cannot_satisfy_doctor(self) -> None:
        self.write("README.md", "# Demo\n<!-- repoctl:project-readme -->\n> Project initialized: **Demo** (`web`).\n")
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
license = "MIT"
owners = ["project-owner"]
[[surfaces]]
id = "app"
path = "."
kind = "code"
owner = "team"
status = "active"
quality_oracle = "run the app and inspect the result"
verification = [["python3", "-c", "print('ok')"]]
""")
        result = self.cli("doctor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("accountable owner", result.stderr)

    def test_forms_and_pr_workflow_keep_public_contracts(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for name in ("config.yml", "bug.yml", "improvement.yml", "feature.yml"):
            content = (root / ".github" / "ISSUE_TEMPLATE" / name).read_text(encoding="utf-8")
            self.assertIn("Disclosure classification", content)
            self.assertIn("Disclosure class", content)
            self.assertIn("public-safe", content)
        self.assertIn("[enhancement/P2]", (root / ".github/ISSUE_TEMPLATE/feature.yml").read_text(encoding="utf-8"))
        issue_workflow = (root / ".github/workflows/issue-contract.yml").read_text(encoding="utf-8")
        self.assertIn("Regulated profile uses the CLI/private issue route", issue_workflow)
        self.assertIn("Minimal profile delegates issue intake", issue_workflow)
        workflow = (root / ".github/workflows/require-issue-reference.yml").read_text(encoding="utf-8")
        self.assertIn("Fixes", workflow)
        self.assertIn("private security prs require", workflow.casefold())
    def test_incident_updates_empty_docs_marker_and_passes_check(self) -> None:
        result = self.cli("incident", "--title", "Probe failure", "--summary", "A reproducible probe")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cli("check").returncode, 0)

    def test_public_incident_requires_reviewed_safe_flag(self) -> None:
        body_hash = hashlib.sha256(b"A redacted failure").hexdigest()
        self.write("incident-review.md", "Issue: #42\nCommit: " + "a" * 40 + "\nArtifact: incident-review.md\nReviewer: reviewer\nDate: 2026-08-25\nResult: public-safe\n" + f"Body-SHA256: {body_hash}\n")
        result = self.cli("incident", "--title", "Public failure", "--summary", "A redacted failure", "--public-safe", "--review-evidence", "incident-review.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cli("check").returncode, 0)
        sensitive = self.cli("incident", "--title", "Exploit", "--summary", "unpatched vulnerability", "--public-safe")
        self.assertEqual(sensitive.returncode, 1)
        self.assertIn("private incident draft", sensitive.stderr)

    def test_multiple_public_incidents_remain_indexed(self) -> None:
        for index, title in enumerate(("First failure", "Second failure"), start=1):
            summary = f"A redacted failure {index}"
            body_hash = hashlib.sha256(summary.encode()).hexdigest()
            evidence = f"incident-review-{index}.md"
            self.write(evidence, "Issue: #42\nCommit: " + "a" * 40 + "\nArtifact: " + evidence + "\nReviewer: reviewer\nDate: 2026-08-25\nResult: public-safe\n" + f"Body-SHA256: {body_hash}\n")
            result = self.cli("incident", "--title", title, "--summary", summary, "--public-safe", "--review-evidence", evidence)
            self.assertEqual(result.returncode, 0, result.stderr)
        index = (self.root / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("First failure", index)
        self.assertIn("Second failure", index)
        self.assertEqual(self.cli("check").returncode, 0)

    def test_third_party_skill_digest_binds_tree_and_mode(self) -> None:
        self.write(".agents/skills/example/SKILL.md", "# Reviewed skill\n")
        self.write(".agents/skills/example/reference.md", "bounded reference\n")
        digest_result = self.cli("skill-digest", ".agents/skills/example")
        self.assertEqual(digest_result.returncode, 0, digest_result.stderr)
        digest = digest_result.stdout.strip()
        self.write("project.toml", """schema = 1
name = "Demo"
kind = "web"
phase = "development"
license = "MIT"
owners = ["team"]
[[skills]]
package = "example/tool@example"
source = "https://github.com/example/tool"
revision = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
content_digest = "DIGEST"
purpose = "bounded test capability"
reviewed_on = "2026-08-25"
permissions = "read-only / project-local"
rollback = "remove the project-local skill and restore the previous lockfile"
""".replace("DIGEST", digest))
        self.write("README.md", "# Demo\n<!-- repoctl:project-readme -->\n> Project initialized: **Demo** (`web`).\n")
        self.assertEqual(self.cli("check").returncode, 0)
        skill_path = self.root / ".agents" / "skills" / "example" / "SKILL.md"
        skill_path.chmod(0o755)
        self.assertIn("content_digest", self.cli("check").stderr)
        skill_path.chmod(0o644)
        (self.root / ".agents" / "skills" / "example" / "extra.txt").write_text("extra\n")
        self.assertIn("content_digest", self.cli("check").stderr)

    def test_public_incident_index_failure_leaves_no_orphan(self) -> None:
        summary = "A redacted failure"
        body_hash = hashlib.sha256(summary.encode()).hexdigest()
        self.write("incident-review.md", "Issue: #42\nCommit: " + "a" * 40 + "\nArtifact: incident-review.md\nReviewer: reviewer\nDate: 2026-08-25\nResult: public-safe\n" + f"Body-SHA256: {body_hash}\n")
        index = self.root / "docs" / "README.md"
        index.unlink()
        index.mkdir()
        result = self.cli("incident", "--title", "Rollback failure", "--summary", summary, "--public-safe", "--review-evidence", "incident-review.md")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(list((self.root / "docs" / "incidents").glob("*.md")), [])

    def test_skill_directory_without_manifest_is_rejected(self) -> None:
        (self.root / ".agents" / "skills" / "attacker").mkdir(parents=True)
        (self.root / ".agents" / "skills" / "attacker" / "run.py").write_text("print('unexpected')\n")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing SKILL.md", result.stderr)

    def test_first_party_skill_extra_file_is_rejected(self) -> None:
        self.write(".agents/skills/quality-loop/SKILL.md", "# Quality\n")
        self.write(".agents/skills/quality-loop/extra.py", "print('unexpected')\n")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unregistered file", result.stderr)


if __name__ == "__main__":
    unittest.main()
