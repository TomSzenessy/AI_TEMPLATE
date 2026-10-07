"""Issue filing: duplicate guard, label creation, marker comment, workflow triggers (fake gh, no network)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from kit import ci, github  # noqa: E402
from kit.core import RepoctlError  # noqa: E402

FAKE = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
state = json.loads(Path(os.environ["GH_STATE"]).read_text())
with open(os.environ["GH_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["issue", "list"]:
    print(json.dumps(state.get("issues", [])))
elif args[:2] == ["label", "list"]:
    print(json.dumps([{"name": n} for n in state.get("labels", [])]))
elif args[:1] == ["api"] and "-X" not in args:
    print("\\n".join(str(i) for i in state.get("comment_ids", [])))
elif args[:2] == ["issue", "create"]:
    print("https://github.com/o/r/issues/1")
"""


class FakeGh(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        (base / "bin").mkdir()
        gh = base / "bin" / "gh"
        gh.write_text(FAKE)
        gh.chmod(0o755)
        self.state, self.log = base / "state.json", base / "log"
        self.log.write_text("")
        self.set_state()
        saved = {k: os.environ.get(k) for k in ("PATH", "GH_STATE", "GH_LOG")}
        os.environ.update(PATH=f"{base / 'bin'}:{os.environ['PATH']}", GH_STATE=str(self.state), GH_LOG=str(self.log))
        self.addCleanup(self.restore, saved)
        self.root = base

    @staticmethod
    def restore(saved: dict[str, str | None]) -> None:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def set_state(self, **state: object) -> None:
        self.state.write_text(json.dumps(state))

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]


class DuplicateGuard(FakeGh):
    def hit(self, issues: list[dict], title: str, topic: str = "", where: str = "") -> list[int]:
        self.set_state(issues=issues)
        found = github.check_github_duplicates(self.root, title, "o/r")
        return [i["number"] for i in found if github.duplicate_result_matches(i, title, topic, where)]

    def test_listing_does_not_use_search(self) -> None:
        self.hit([], "x")
        self.assertNotIn("--search", self.calls()[0])

    def test_identical_title_is_blocked(self) -> None:
        issue = {"number": 18, "title": "Fix the thing!", "body": ""}
        self.assertEqual(self.hit([issue], "fix the thing"), [18])

    def test_topic_is_not_a_title_substring(self) -> None:
        issue = {"number": 5, "title": "Fix repository link rot", "body": "", "labels": []}
        self.assertEqual(self.hit([issue], "Other", topic="repo"), [])

    def test_topic_matches_label(self) -> None:
        issue = {"number": 5, "title": "Other words", "body": "", "labels": [{"name": "topic:issue-filing"}]}
        self.assertEqual(self.hit([issue], "New", topic="issue-filing"), [5])

    def test_one_shared_path_is_not_a_duplicate(self) -> None:
        issue = {"number": 7, "title": "A", "body": "touches tools/kit/github.py and v1.2 notes", "labels": []}
        self.assertEqual(self.hit([issue], "B", where="see tools/kit/github.py version 1.2 e.g."), [])

    def test_two_shared_paths_are_a_duplicate(self) -> None:
        issue = {"number": 7, "title": "A", "body": "tools/kit/github.py and Makefile and ci.py", "labels": []}
        self.assertEqual(self.hit([issue], "B", where="tools/kit/github.py, ci.py"), [7])

    def test_urls_and_qualifiers_do_not_count(self) -> None:
        self.assertEqual(github.path_tokens("https://github.com/o/r/issues/1 label:bug is:open"), set())
        self.assertEqual(github.strip_qualifiers("fix label:bug is:open now"), "fix now")


class Labels(FakeGh):
    def test_only_missing_labels_are_created_once_without_force(self) -> None:
        self.set_state(labels=["type:bug"])
        github.create_github_issue(self.root, "o/r", "T", "B", ["type:bug", "topic:new"])
        creates = [c for c in self.calls() if c[:2] == ["label", "create"]]
        self.assertEqual([c[2] for c in creates], ["topic:new"])
        self.assertEqual(sum(c[:2] == ["label", "list"] for c in self.calls()), 1)
        self.assertTrue(all("--force" not in c for c in creates))


class MarkerComment(FakeGh):
    def writes(self) -> list[list[str]]:
        return [c for c in self.calls() if "-X" in c]

    def test_existing_marker_comment_is_updated(self) -> None:
        self.set_state(comment_ids=[99])
        ci.post_contract_comment("o/r", "4", "problem")
        (write,) = self.writes()
        self.assertIn("PATCH", write)
        self.assertTrue(any(a.startswith("repos/o/r/issues/comments/99") for a in write))
        self.assertTrue(any(a.startswith("body=<!-- issue-contract -->") for a in write))

    def test_first_failure_creates_comment(self) -> None:
        ci.post_contract_comment("o/r", "4", "problem")
        (write,) = self.writes()
        self.assertIn("POST", write)

    def test_mentions_are_stripped(self) -> None:
        self.assertEqual(ci.strip_mentions("type: @octocat"), "type: octocat")


class GhWrapper(FakeGh):
    def test_missing_gh_is_a_repoctl_error(self) -> None:
        os.environ["PATH"] = "/nonexistent"  # restored by FakeGh cleanup
        with self.assertRaises(RepoctlError):
            github._gh(self.root, ["issue", "list"])


class Workflow(unittest.TestCase):
    def test_concurrency_and_triggers(self) -> None:
        text = (ROOT / ".github/workflows/issue-contract.yml").read_text()
        self.assertIn("group: issue-contract-${{ github.event.issue.number }}", text)
        self.assertIn("cancel-in-progress: true", text)
        # label edits by people still re-validate; the group collapses the burst from one filing
        self.assertIn("labeled", text)


if __name__ == "__main__":
    unittest.main()
