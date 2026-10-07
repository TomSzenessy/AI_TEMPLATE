"""Doc ownership: one rule, one owner doc, and a split that stays split (#47).

Every rule below must be defined in exactly one document; the others link to
it. The covers and size limits keep `docs/` split by concern, so a reader who
needs one concern lands on one document instead of one growing page. These
checks run against this template's own docs tree; a project made from the
template keeps its own docs, so they skip there (#47).
"""

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"

# Template-maintenance tests need the template's own docs; in a project made
# from it they skip, so a fresh project's `make done` stays green (EL-001).
IN_TEMPLATE = tomllib.loads((REPO / "project.toml").read_text(encoding="utf-8")).get("kind") == "template"
template_only = unittest.skipUnless(IN_TEMPLATE, "doc ownership: template checkout only")

# Rules whose defining wording must live in exactly one document (#47). The
# value is the only document allowed to contain the phrase; every other
# document links to it instead of restating it.
RULE_OWNERS = {
    "ship-with-residuals": "docs/delegation.md",  # critic verdict vocabulary
    "evidence-producing acceptance criteria": "docs/ISSUE_TEMPLATE.md",  # write-ahead rule
    "a reason with no path exempts all documents": "docs/bindings.md",  # Docs-Unaffected parsing
    "community example": "docs/resources.md",  # source precedence ladder
    "maps a pack name to": "docs/capabilities.md",  # [packs] shape
    "at least 12 characters": "docs/operations.md",  # error-ledger matchable literal
}

MAX_COVER_GLOBS = 10  # one concern per doc; the pre-split self-healing.md listed 25
MAX_DOC_BYTES = 12_000  # a reader lands on one short document, not one growing page

COVERS = re.compile(r"<!--\s*covers:\s*(.*?)\s*-->")


def owner_docs() -> dict[str, Path]:
    """Rule documents in scope: the durable tree, minus records and snapshots."""
    skip = ("research/", "handoffs/")  # bannered snapshots and transient records
    return {
        path.relative_to(REPO).as_posix(): path
        for path in sorted(DOCS.rglob("*.md"))
        if not path.relative_to(DOCS).as_posix().startswith(skip)
    }


@template_only
class RuleOwnershipTests(unittest.TestCase):
    """Each rule in docs/ has one owner document (#47)."""

    def test_each_rule_is_defined_in_exactly_one_document(self) -> None:
        for phrase, owner in RULE_OWNERS.items():
            with self.subTest(phrase=phrase):
                stated = [name for name, path in owner_docs().items() if phrase in path.read_text(encoding="utf-8")]
                self.assertEqual(
                    stated, [owner],
                    f"the rule {phrase!r} must be defined only in {owner}; "
                    f"found it in {stated}. Move the wording into {owner} and "
                    f"link to it from the others.",
                )


@template_only
class SplitStaysSplitTests(unittest.TestCase):
    """docs/ stays split by concern, with narrow covers lines (#47)."""

    def test_no_doc_covers_more_than_ten_globs(self) -> None:
        for name, path in owner_docs().items():
            for match in COVERS.finditer(path.read_text(encoding="utf-8")):
                globs = match.group(1).split()
                with self.subTest(doc=name):
                    self.assertLessEqual(
                        len(globs), MAX_COVER_GLOBS,
                        f"{name} covers {len(globs)} globs; split it so each "
                        f"document owns one concern with at most {MAX_COVER_GLOBS} globs.",
                    )

    def test_no_doc_grows_past_a_page(self) -> None:
        ledger = "docs/ERROR_LOG.md"  # append-only ledger; it grows by design
        for name, path in owner_docs().items():
            if name == ledger:
                continue
            with self.subTest(doc=name):
                self.assertLessEqual(
                    path.stat().st_size, MAX_DOC_BYTES,
                    f"{name} is {path.stat().st_size} bytes; split it so a "
                    f"reader of one concern lands on one short document.",
                )


if __name__ == "__main__":
    unittest.main()
