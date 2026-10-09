"""Failure signatures and reference shapes (split from the former single test_kit.py, #43)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import (TOOLS, KitRepository, Scratch, template_only)  # noqa: E402

from kit import (checkrun, reachability, signatures)  # noqa: E402


class FailureSignatureTests(Scratch):
    """Issue #18: a finding that repeats a recorded signature is recognised, not re-diagnosed."""

    LEDGER = """# Error ledger

| Key | Date | Signature / symptom | Confirmed cause | Permanent fix |
|---|---|---|---|---|
| EL-001 | 2026-01-01 | `covers pattern matches no file: legacy/**` right after init | Pruning left a binding pointing at removed material | localize_text drops bindings to pruned material |
"""

    def setUp(self) -> None:
        super().setUp()
        self.write("project.toml", 'schema = 1\nname = "Demo"\nkind = "cli"\nphase = "development"\n')

    def ledger(self, text: str = LEDGER) -> None:
        self.write("docs/ERROR_LOG.md", text)

    def test_a_row_no_finding_can_match_is_reported_with_its_fix(self) -> None:
        # #59: EL-007 quoted only `make done` (9 chars) and vanished from the matcher silently.
        from kit import signatures
        self.ledger(self.LEDGER + "| EL-002 | 2026-01-02 | `make done` passed on a broken tree | x | y |\n")
        self.assertEqual([s.key for s in signatures.signatures(self.root)], ["EL-001"])
        problems = signatures.unmatchable(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("EL-002 cannot be matched", problems[0])
        self.assertIn("12+ characters", problems[0])
        self.assertIn("[ledger-signatures]", self.cli("garden").stdout + self.cli("check").stdout + self.cli("check").stderr)

    def test_a_repeated_failure_is_named_with_its_recorded_fix(self) -> None:
        self.ledger()
        records = signatures.signatures(self.root)
        hit = signatures.match("docs/api.md: covers pattern matches no file: legacy/**", records)
        self.assertIsNotNone(hit, "a recorded signature is recognised")
        self.assertEqual(hit.key, "EL-001")
        self.assertIn("localize_text drops bindings", hit.fix)

    def test_a_fresh_failure_matches_no_prior_signature(self) -> None:
        self.ledger()
        records = signatures.signatures(self.root)
        for finding in ("src/billing/invoice.py: nothing references it", "AGENTS.md: 812 bytes, over its 200-byte budget"):
            self.assertIsNone(signatures.match(finding, records), finding)
        self.assertEqual(signatures.recognition(["src/billing/invoice.py: nothing references it"], records), [])

    def test_the_check_runner_reports_the_signature_next_to_the_finding(self) -> None:
        self.ledger()
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "docs" / "api.md").write_text("# API\n\n<!-- covers: legacy/** -->\n", encoding="utf-8")
        hard, _ = checkrun.run_checks(self.root, blocking_only=True)
        findings = "\n".join(hard)
        self.assertIn("covers pattern matches no file: legacy/**", findings)
        self.assertIn("known failure EL-001", findings, "a repeat reports its key and fix")
        self.assertIn("localize_text drops bindings", findings)

    def test_no_ledger_means_no_matching_and_no_crash(self) -> None:
        self.assertEqual(signatures.signatures(self.root), ())
        self.assertIsNone(signatures.match("anything at all", ()))
        hard, _ = checkrun.run_checks(self.root, blocking_only=True, skip=KitRepository.CONTRACT)
        self.assertNotIn("known failure", "\n".join(hard))

    def test_columns_are_read_from_the_header(self) -> None:
        self.ledger("""\
            # Error ledger

            | Date | Permanent fix | Signature / symptom | Key | Confirmed cause |
            |---|---|---|---|---|
            | 2026-01-01 | shrink the router | `over its 200-byte budget` | EL-009 | an always-loaded doc grew |
            """)
        records = signatures.signatures(self.root)
        self.assertEqual([record.key for record in records], ["EL-009"])
        self.assertEqual(records[0].fix, "shrink the router")
        self.assertIsNotNone(signatures.match("AGENTS.md is 812 bytes, over its 200-byte budget (AGENTS.md)", records))

    @template_only
    def test_this_ledger_is_keyed_and_every_row_has_a_fix(self) -> None:
        # Every ledger row is a record a human wrote for a failure they had to re-diagnose.
        # The matcher was built against synthetic ledgers, so this asserts on the real one:
        # a row that stops being matchable loses its recognition, which is the whole point.
        records = signatures.signatures(TOOLS.parent)
        self.assertEqual([record.key for record in records],
                         [f"EL-{number:03d}" for number in range(1, len(records) + 1)],
                         "every ledger row is keyed, in order, and matchable")
        for record in records:
            self.assertRegex(record.key, r"^EL-\d{3}$")
            self.assertTrue(record.literals, record.key)
            self.assertTrue(record.fix, f"{record.key} records no permanent fix")


class SignatureLiteralTests(Scratch):
    """A literal that shares vocabulary with ordinary findings must not match them."""

    LEDGER = """# Error ledger

| Key | Date | Signature / symptom | Confirmed cause | Permanent fix |
|---|---|---|---|---|
| EL-001 | 2026-01-01 | `make check` starts failing a year later on an unchanged repo | Ages blocked every phase | Ages gate releases only |
| EL-002 | 2026-01-01 | Every trial blocked by `unregistered product surface: tests` (or `e2e`, `test-results`, `examples`) | Test folders were not infrastructure | Infrastructure by default |
"""

    def setUp(self) -> None:
        super().setUp()
        self.write("docs/ERROR_LOG.md", self.LEDGER)
        self.records = signatures.signatures(self.root)

    def test_instructions_are_not_a_failure(self) -> None:
        self.assertIsNone(signatures.match("run make check before pushing", self.records),
                          "a command in prose is not this failure")

    def test_a_directory_name_is_not_a_failure(self) -> None:
        self.assertIsNone(signatures.match("examples/demo.md: surface demo has no owning doc", self.records),
                          "the word in a path is not this failure")

    def test_the_distinctive_part_still_matches(self) -> None:
        hit = signatures.match("src/notes: unregistered product surface: tests", self.records)
        self.assertIsNotNone(hit, "the literal that identifies the failure still matches")
        self.assertEqual(hit.key, "EL-002")

    def test_a_row_with_no_distinctive_literal_is_simply_not_matched(self) -> None:
        self.assertNotIn("EL-001", [record.key for record in self.records],
                         "a row whose symptom offers only shared vocabulary cannot cause a false match")


class ReferenceShapesTests(Scratch):
    """Reference shapes the resolver had to grow, each from a layout the fix did not target.

    Each test names the shape it defends and why the fix was not written with it in mind,
    and each asserts on what the resolver *reported*, so reverting the resolution change
    puts the fixture's file back into the report and the test fails. A fixture invented
    alongside its fix is a comment, not a test.
    """

    MANIFEST = 'schema = 1\nname = "Demo"\nkind = "cli"\nphase = "development"\n'

    def setUp(self) -> None:
        super().setUp()
        self.write("project.toml", self.MANIFEST)
        self.write("docs/README.md", "# Docs\n\n- [API](api.md)\n")
        self.write("docs/api.md", "# API\n")

    def reported(self) -> set[str]:
        unreferenced, host_read = reachability.advisories(checkrun.Context(self.root))
        return {item.split(":")[0] for item in (*unreferenced, *host_read)}

    def test_a_procfile_callable_names_its_module(self) -> None:
        """Defends: a Procfile, not a Dockerfile.

        `module:callable` support was written from `CMD gunicorn app:app` in a Dockerfile.
        A Procfile puts the same grammar in a colon-separated line (`web: notes.app:create_app`)
        where the line's own colon must not eat the module, and the release line has no
        callable at all (`python3 -m notes.migrate`), so it defends the dotted-module half
        of the same change.
        """
        self.write("Procfile", "web: gunicorn notes.app:create_app\nrelease: python3 -m notes.migrate\n")
        self.write("notes/app.py", "def create_app():\n    return None\n")
        self.write("notes/migrate.py", "def main():\n    return None\n")
        reported = self.reported()
        self.assertNotIn("notes/app.py", reported, "the Procfile's callable names the module")
        self.assertNotIn("notes/migrate.py", reported, "and so does a dotted `python -m`")
        self.assertIn("Procfile", reported, "and the control: the report still has teeth")

    def test_a_compose_command_array_names_its_module(self) -> None:
        """Defends: a compose YAML command list, not an image Dockerfile.

        The change was written for a shell-form `CMD`. A JSON-array command
        (`command: ["uvicorn", "asgi:application"]`) has the same grammar in YAML the kit
        never shell-parses, and it is what an adopted service ships.
        """
        self.write("compose.yaml", "services:\n  web:\n    command: [\"uvicorn\", \"asgi:application\"]\n")
        self.write("asgi.py", "application = None\n")
        reported = self.reported()
        self.assertNotIn("asgi.py", reported, "a compose command names the module it serves")
        self.assertIn("compose.yaml", reported, "and the control: the report still has teeth")

    def test_a_framework_tree_nested_under_an_app_package_is_reported_as_such(self) -> None:
        """Defends: `apps/store/migrations/`, not a top-level `migrations/`.

        The framework-tree rule was written from the first reading of its own comment — a
        root-level `migrations/` — and matched only `path.split("/")[0]`, so it was dead
        code for the layout Django and Alembic actually produce.
        """
        self.write("apps/store/migrations/0002_add_email.py", "def upgrade():\n    pass\n")
        self.write("apps/store/management/commands/reindex.py", "def handle():\n    pass\n")
        unreferenced, _ = reachability.advisories(checkrun.Context(self.root))
        message = {item.split(":")[0]: item for item in unreferenced}
        self.assertIn("a framework tree a tool walks by convention", message["apps/store/migrations/0002_add_email.py"])
        self.assertIn("a framework tree a tool walks by convention", message["apps/store/management/commands/reindex.py"])

    def test_a_package_imported_by_its_dotted_path_reaches_its_initialiser(self) -> None:
        """Defends: `importlib.import_module("pkg.mod")`, not `import pkg`.

        The initialiser change was written from the plain `import pkg` reading. The kit
        itself loads modules by dotted name (`registry._plugins`), which never spells the
        package alone, so keying the initialiser by `__init__` alone left it looking dead.
        The control package in the same fixture is the other side of that rule.
        """
        self.write("tools/pkg/__init__.py", "NAME = 'pkg'\n")
        self.write("tools/pkg/mod.py", "VALUE = 1\n")
        self.write("tools/abandoned/__init__.py", "NAME = 'abandoned'\n")
        self.write("tools/abandoned/mod.py", "VALUE = 2\n")
        self.write("tools/loader.py", "import importlib\n\nmod = importlib.import_module('pkg.mod')\n")
        self.write("docs/api.md", "# API\n\n<!-- covers: tools/loader.py -->\n")
        reported = self.reported()
        self.assertNotIn("tools/pkg/__init__.py", reported, "importing pkg.mod executes pkg/__init__.py")
        self.assertIn("tools/abandoned/__init__.py", reported, "a package nobody imports is still reported")
        self.assertIn("tools/abandoned/mod.py", reported, "and so is the module inside it")

    def test_a_path_with_a_callable_suffix_still_resolves(self) -> None:
        """Defends: `file.py:12`, a traceback frame, which the fix did not consider.

        The colon split was added for `module:callable`; it also has to keep a path
        reference intact when a stack-trace line appends `:line`, and keep a Windows-free
        `path:line` in a Makefile recipe from becoming two unrelated names.
        """
        self.write("docs/api.md", "# API\n\n<!-- covers: tools/used.py -->\n")
        self.write("tools/used.py", "VALUE = 1\n")
        self.write("Makefile", "trace:\n\tpython3 -X dev tools/used.py:12\n")
        self.assertNotIn("tools/used.py", self.reported(), "a path with a line number still names the file")


class BareLiteralSignatureTests(Scratch):
    """A ledger row whose symptom quotes one bare filename is not matched, and that is correct.

    Defends: a row whose only backticked span is `kit-lock.json`, the shape a maintainer
    writes when recording "the lock file was stale". The matcher was written around
    message-shaped spans, so a single token is dropped rather than risking a match on any
    path that happens to share a name. The alternative failure mode, a row that silently
    stops being recognised, is what the restored count assertion above exists to catch.
    """

    LEDGER = """# Error ledger

| Key | Date | Signature / symptom | Confirmed cause | Permanent fix |
|---|---|---|---|---|
| EL-010 | 2026-01-01 | A stale `kit-lock.json` after adopt | The lock kept the template revision | Re-run `make kit-update` |
"""

    def setUp(self) -> None:
        super().setUp()
        self.write("docs/ERROR_LOG.md", self.LEDGER)

    def test_a_bare_filename_does_not_become_a_match(self) -> None:
        records = signatures.signatures(self.root)
        self.assertEqual(records, (), "no message-shaped literal, no matcher")
        self.assertIsNone(signatures.match("tools/kit-lock.json is stale: re-run make kit-update", records))

    def test_adding_one_shaped_literal_restores_recognition(self) -> None:
        (self.root / "docs" / "ERROR_LOG.md").write_text(
            self.LEDGER.replace("A stale `kit-lock.json` after adopt", "A stale `kit-lock.json`: `0 updated, 0 added` is wrong"),
            encoding="utf-8")
        records = signatures.signatures(self.root)
        self.assertEqual([record.key for record in records], ["EL-010"])
        hit = signatures.match("kit-update reports: 0 updated, 0 added, 3 removed", records)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.key, "EL-010")


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
