"""Each rule is enforced in one place, so a fix cannot half-apply (#22).

Behaviour first: a blocking check runs once per `make verify`, and the commit and finish gates
take their blocking decision from the registry (a project downgrade changes them too). The source
scans at the end fail if a gate grows its own copy of a rule the registry already owns.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import Scratch  # noqa: E402

from kit import session  # noqa: E402

REPO = TOOLS.parent
MANIFEST = 'schema = 1\nname = "Demo"\nkind = "template"\nphase = "bootstrap"\nlicense = "UNSELECTED"\nowners = []\n' \
           '[governance]\nprofile = "regulated"\n'
PROBE = '''"""Counts how often the runner executes it."""
from pathlib import Path

from kit.registry import check


@check("run-probe", "Counts its own executions so a test can prove no check runs twice", blocks=True,
       reason="Test probe: the evidence that a blocking check ran more than once in one gate invocation.")
def run(context) -> list[str]:
    with (context.root / "probe.log").open("a") as log:
        log.write("ran\\n")
    return []
'''


def verify_recipe() -> list[str]:
    """The repoctl subcommands `make verify` runs, read from the real Makefile."""
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    block = re.search(r"(?m)^verify:.*\n((?:\t.*\n)+)", text).group(1)
    return [line.split("$(REPOCTL)", 1)[1].split() for line in block.splitlines() if "$(REPOCTL)" in line]


class NoCheckRunsTwice(Scratch):
    def test_make_verify_runs_each_blocking_check_once(self) -> None:
        self.write("project.toml", MANIFEST)
        self.write(".agents/checks/run-probe.py", PROBE)
        steps = verify_recipe()
        self.assertGreaterEqual(len(steps), 2, steps)  # repoctl verify, then doctor
        for step in steps:
            self.cli(*step)  # outcomes do not matter here: this scratch repo is not an initialized project
        runs = (self.root / "probe.log").read_text(encoding="utf-8").count("ran")
        self.assertEqual(runs, 1, f"`make verify` ran a blocking check {runs} times via {steps}")

    def test_doctor_alone_still_runs_the_blocking_checks(self) -> None:
        self.write("project.toml", MANIFEST)
        self.write(".agents/checks/run-probe.py", PROBE)
        self.cli("doctor")
        self.assertEqual((self.root / "probe.log").read_text(encoding="utf-8").count("ran"), 1)


class GatesTakeBlockingFromTheRegistry(Scratch):
    def setUp(self) -> None:
        super().setUp()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        self.write("project.toml", MANIFEST)
        self.write("docs/README.md", "# Docs\n")
        self.commit("base")
        self.write("src/a.py", "# " + "TO" + "DO tidy this\n")
        self.git("add", "-A")

    def downgrade(self, name: str) -> None:
        self.write("project.toml", MANIFEST + f'\n[checks.{name}]\nseverity = "advisory"\nreason = "this repository tolerates it"\n')
        self.git("add", "-A")

    def test_commit_gate_blocks_on_an_unreferenced_task_marker(self) -> None:
        self.assertTrue(any(item.startswith("[markers]") for item in session.commit_findings(self.root, None)))

    def test_commit_gate_honours_a_downgrade(self) -> None:
        self.downgrade("markers")
        self.assertFalse(any(item.startswith("[markers]") for item in session.commit_findings(self.root, None)))

    def test_finish_gate_agrees_with_the_commit_gate(self) -> None:
        self.assertTrue(any(item.startswith("[markers]") for item in session.finish_findings(self.root)))
        self.downgrade("markers")
        self.assertFalse(any(item.startswith("[markers]") for item in session.finish_findings(self.root)))

    def test_commit_gate_exit_status_comes_from_its_findings(self) -> None:
        self.assertEqual(session.commit_gate(self.root, None), session.GATE_BLOCKED)
        self.downgrade("markers")
        self.assertEqual(session.commit_gate(self.root, None), 0)


class NoSecondImplementation(unittest.TestCase):
    """Source guards: these fail when a rule the registry owns is written again elsewhere."""

    def source(self, name: str) -> str:
        return (TOOLS / "kit" / name).read_text(encoding="utf-8")

    def test_gates_do_not_call_the_rules_the_registry_owns(self) -> None:
        text = self.source("session.py")
        for needle in ("scan_markers", "derive.drift", "dead_bindings", "plugin_errors"):
            self.assertNotIn(needle, text, f"session.py calls {needle} itself; name the check in registry_findings instead")

    def test_doctor_does_not_rerun_checks_a_gate_already_ran(self) -> None:
        self.assertIn("doctor --checks-done", (REPO / "Makefile").read_text(encoding="utf-8"))

    def test_date_staleness_has_one_implementation(self) -> None:
        text = self.source("structure.py")
        for needle in ("timedelta", "today()", "datetime.now"):
            self.assertNotIn(needle, text, f"structure.py computes dates with {needle}; call core.date_out_of_policy")
        self.assertIn("date_out_of_policy", text)


if __name__ == "__main__":
    unittest.main()
