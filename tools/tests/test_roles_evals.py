"""Delegation roles, eval answer key, and hygiene rules (#46)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from kit import adapters, evals, hygiene  # noqa: E402


def tools_line(files: dict[str, str], role: str) -> str | None:
    for line in files[f".claude/agents/{role}.md"].splitlines():
        if line.startswith("tools:"):
            return line
    return None


class RoleTests(unittest.TestCase):
    def test_web_roles_have_explicit_tools_without_write_access(self) -> None:
        files = adapters.render_claude(ROOT)
        for role in ("researcher", "skill-scout"):
            line = tools_line(files, role)
            self.assertIsNotNone(line, role)
            for forbidden in ("Edit", "Write", "Bash"):
                self.assertNotIn(forbidden, line)
            self.assertIn("WebFetch", line)
            self.assertIn("mcp__context7", line)

    def test_full_role_stays_unrestricted_and_read_only_keeps_bash(self) -> None:
        files = adapters.render_claude(ROOT)
        self.assertIsNone(tools_line(files, "implementer"))
        self.assertIn("Bash", tools_line(files, "critic"))
        self.assertNotIn("Edit", tools_line(files, "critic"))

    def test_critic_brief_and_return_fields_are_distinct(self) -> None:
        text = (ROOT / ".agents/agents/critic.md").read_text(encoding="utf-8")
        brief = text.split("## Brief")[1].split("## Method")[0]
        self.assertIn("`Diff`", brief)
        self.assertNotIn("`Commit`", brief)
        self.assertIn("Commit: <40-hex", text)

    def test_role_files_end_with_a_newline(self) -> None:
        for path in (ROOT / ".agents/agents").glob("*.md"):
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"), path.name)


class EvalTests(unittest.TestCase):
    def tasks(self) -> dict[str, dict[str, str]]:
        return {task["id"]: task for task in evals.load_tasks(ROOT)}

    def test_command_denies_reading_the_answer_key(self) -> None:
        command = evals.HOST_COMMANDS["claude"]("task", "")
        denied = command[command.index("--disallowedTools") + 1:]
        for tool in ("Read", "Grep", "Glob"):
            self.assertIn(f"{tool}(.agents/evals/**)", denied)
        self.assertTrue(set(denied).isdisjoint(command[: command.index("--disallowedTools")]))

    def test_loose_regexes_reject_wrong_and_negated_answers(self) -> None:
        tasks = self.tasks()
        cases = {
            "canonical-skills": (["`.agents/skills/`", ".agents/skills"], ["Not .agents/skills; it is .claude/skills", ".claude/skills"]),
            "generated-files": ([".agents/", "`.agents/skills/x/SKILL.md`", "resources.toml",
                                 "`.agents/` (`.claude/` files are generated; edit their source in `.agents/`, then run `make sync`.)",
                                 "`.agents/` — then run `make sync` (`.claude/` files are generated; edit their source in `.agents/` and sync.)"],
                                ["Edit .claude directly, never .agents", ".claude/",
                                 "`.agents/` (no, edit `.claude/` directly instead)", ".agentsx/", "`.agents/` is wrong; never edit it"]),
            "kickoff-without-owner": (
                ["Write the questions with my recommended picks, then stop."],
                ["I would not stop", "I would not write the questions; I would guess", "Stop and do nothing"]),
            "add-an-mcp-server": ([".agents/mcp/", "`.agents/mcp`"], [".claude/mcp/", "Not .agents/mcp/, but .mcp.json", ".agents/mcpx"]),
        }
        for task_id, (good, bad) in cases.items():
            for answer in good:
                self.assertTrue(evals.answer_matches(tasks[task_id], answer), (task_id, answer))
            for answer in bad:
                self.assertFalse(evals.answer_matches(tasks[task_id], answer), (task_id, answer))


class HygieneTests(unittest.TestCase):
    def test_missing_final_newline_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.md").write_text("ok\n", encoding="utf-8")
            (root / "b.md").write_text("lost", encoding="utf-8")
            (root / "c.bin").write_text("lost", encoding="utf-8")
            findings = hygiene.final_newline_errors(root, ["a.md", "b.md", "c.bin"])
            self.assertEqual(len(findings), 1)
            self.assertIn("b.md", findings[0])

    def test_host_twins_must_match_apart_from_line_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "CLAUDE.md").write_text("# Claude entry\nbody\n", encoding="utf-8")
            (root / "GEMINI.md").write_text("# Gemini entry\nbody\n", encoding="utf-8")
            self.assertEqual(hygiene.host_twin_errors(root), [])
            (root / "GEMINI.md").write_text("# Gemini entry\ndrifted\n", encoding="utf-8")
            self.assertEqual(len(hygiene.host_twin_errors(root)), 1)

    def test_repository_twins_agree(self) -> None:
        self.assertEqual(hygiene.host_twin_errors(ROOT), [])


if __name__ == "__main__":
    unittest.main()
