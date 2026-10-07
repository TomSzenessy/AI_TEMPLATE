"""One owner for the issue contract: tools/issue_contract.py (headings, patterns, refused values).

`make issue` and the CI check both call `issues.issue_problems`; the docs and the native
forms are held to the same definitions here.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import issue_contract as contract  # noqa: E402
from kit import ci, issues  # noqa: E402
from kit.core import RepoctlError  # noqa: E402

REGISTRY = json.loads((ROOT / ".github/issue-labels.json").read_text(encoding="utf-8"))
FORMS = sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml"))
FORMS = [path for path in FORMS if path.name != "config.yml"]
TODAY = date.today().isoformat()

VALID = f"""### Summary
A concrete outcome for the single-source contract test.

Duplicate check: searched title, symptom, and path for contract; no duplicate found

### Acceptance criteria
- [ ] A unit test verifies the positive case passes.
- [ ] A negative test verifies the bad case does not pass.

### Evidence
Test evidence: unit output

### Disclosure classification
- **Disclosure class:** ordinary
- **Public-safe:** yes
- **Security/privacy review:** not applicable
- **Reviewer/date:** test reviewer {TODAY}

### Dependencies and handoff
- **Owner / next action:** maintainer
"""


def form_options(path: Path, field_id: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"id: {field_id}\n    attributes:\n(?:      [^\n]*\n)*?      options: \[([^\]]*)\]", text)
    if not match:
        raise AssertionError(f"{path.name}: {field_id} is not a dropdown with inline options")
    return [item.strip() for item in match.group(1).split(",")]


def ci_problems(body: str, profile: str = "agent-first", status: str = "triage") -> list[str]:
    labels = {f"status:{status}"}
    return ci.issue_contract_check(body, labels, profile if profile != "regulated" else "agent-first", REGISTRY)[2]


class SingleSourceTests(unittest.TestCase):
    def test_each_rule_is_defined_once(self) -> None:
        for path in (ROOT / "tools/kit").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("Duplicate check:\\s", text)
                self.assertNotIn('"What happens"', text, "heading tuples live in issue_contract.py")
                self.assertNotIn("Public-safe:(?:", text)

    def test_forms_match_the_registry_minus_refused_values(self) -> None:
        for family in ("type", "priority", "area", "status"):
            refused = set(contract.REFUSED_PUBLIC.get(family, ()))
            expected = [value for value in REGISTRY[family] if value not in refused]
            for path in FORMS:
                with self.subTest(form=path.name, family=family):
                    self.assertEqual(form_options(path, family), expected)

    def test_forms_carry_every_required_heading(self) -> None:
        for path in FORMS:
            labels = set(re.findall(r"label: ([^\n]+)", path.read_text(encoding="utf-8")))
            for heading in contract.HEADINGS["agent-first"]:
                with self.subTest(form=path.name, heading=heading):
                    self.assertIn(heading, labels)

    def test_doc_headings_equal_regulated_headings(self) -> None:
        text = (ROOT / "docs/ISSUE_TEMPLATE.md").read_text(encoding="utf-8")
        body = text.split("## Required body", 1)[1].split("## Resolution record", 1)[0]
        self.assertEqual(tuple(re.findall(r"(?m)^### (.+)$", body)), contract.HEADINGS["regulated"])

    def test_pr_template_keywords_match_the_pr_check(self) -> None:
        template = (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")
        line = next(line for line in template.splitlines() if "#<number>" in line)
        self.assertEqual(line.strip(), "Fixes/Closes #<number>")
        for keyword in line.split("#")[0].strip().split("/"):
            ci.pr_reference_check(f"{keyword} #6", set(), "OWNER", "agent-first",
                                  lambda number: {"state": "open", "body": VALID})
        with self.assertRaisesRegex(RepoctlError, "Closes/Fixes"):
            ci.pr_reference_check("Refs #6", set(), "OWNER", "agent-first", lambda number: {"state": "open", "body": VALID})


class CliAndCiAgreeTests(unittest.TestCase):
    def test_valid_body_passes_both(self) -> None:
        self.assertEqual(issues.issue_problems(VALID, "agent-first", "triage"), [])
        issues.validate_issue(VALID, "triage", "agent-first")

    def test_same_problems_for_cli_and_ci(self) -> None:
        bad_headings = VALID.replace("### Evidence", "### Proof")
        bad_duplicate = VALID.replace("symptom, and path", "symptom and path")
        private = VALID.replace("ordinary", "private-route")
        for name, body in {"heading": bad_headings, "duplicate": bad_duplicate, "private": private}.items():
            with self.subTest(case=name):
                cli = issues.issue_problems(body, "agent-first", "triage")
                self.assertTrue(cli, "the CLI must reject it")
                # CI = the same problems first, then label/field rules only.
                self.assertEqual(ci_problems(body)[: len(cli)], cli)
                with self.assertRaises(RepoctlError):
                    issues.validate_issue(body, "triage", "agent-first")

    def test_loose_duplicate_spacing_passes_both_the_pr_and_issue_check(self) -> None:
        loose = VALID.replace("symptom, and path", "symptom,and path")
        self.assertIsNotNone(contract.DUPLICATE_CHECK.search(loose))
        self.assertEqual(issues.issue_problems(loose, "agent-first", "triage"), [])
        ci.pr_reference_check("Fixes #6", set(), "OWNER", "agent-first", lambda n: {"state": "open", "body": loose})

    def test_fenced_code_never_satisfies_the_contract(self) -> None:
        fenced = "```\n" + VALID + "```\n"
        self.assertEqual(len(issues.issue_problems(fenced, "agent-first", "triage")), 1)

    def test_sections_are_parsed_once_and_first_heading_wins(self) -> None:
        sections = issues.parse_sections("### A\none\n### B\ntwo\n### A\nthree\n```\n### C\n```\n")
        self.assertEqual(sections, {"A": "one", "B": "two"})


if __name__ == "__main__":
    unittest.main()
