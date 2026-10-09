"""Failure signatures: a known failure recognised in one step, not re-diagnosed (issue #18).

`docs/ERROR_LOG.md` records solved failure signatures and their permanent fixes,
and `make where` surfaces them by keyword. Storing them is half the value; the
other half is *matching* them, so a check that fails the way a recorded failure
failed reports "this is EL-003, and here is its fix" instead of sending the next
reader back to the beginning.

A signature is a row of the ledger's Markdown table:

    | Key | Date | Signature / symptom | Confirmed cause | Permanent fix | ... |

The key (`EL-001`) is the stable name a finding cites. The backticked spans in
the symptom are the literals that identify it, and the permanent-fix cell is what
the match reports. So matching reads the ledger the reader already maintains: no
second index, nothing to drift, and a rewritten row keeps working.

A literal counts only when it is long enough and shaped like a message, a path, or
a command rather than a word: `make check` appears in instructions that are not
this failure, and `examples` appears in any directory listing. A row whose symptom
offers no such literal is not matched, which errs in the direction that matters —
a new failure stays a new failure. Cost is one small file read, and only when
there is a finding to match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .core import read_text_file
from .names import ERROR_LOG

LEDGER = ERROR_LOG  # the failure ledger this module reads is the error log
KEY = re.compile(r"EL-\d{3}")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
# A literal that identifies one failure rather than sharing vocabulary with many:
# long enough to be a message fragment, a path, or a command, and shaped like one.
MINIMUM_LITERAL = 12
SHAPED_LITERAL = re.compile(r"[ /:]")
LEDGER_LIMIT = 200_000


@dataclass(frozen=True)
class Signature:
    """One recorded failure: its stable key, the literals that identify it, and its fix."""

    key: str
    literals: tuple[str, ...]
    symptom: str
    fix: str


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _rows(root: Path) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """(key, symptom, permanent fix, matchable literals) for every keyed ledger row.

    Columns are read from the header, so reordering the table keeps matching honest.
    """
    text = read_text_file(root, LEDGER, limit=LEDGER_LIMIT) or ""
    rows: list[tuple[str, str, str, tuple[str, ...]]] = []
    columns: dict[str, int] = {}
    for line in text.splitlines():
        cells = _cells(line)
        if "Key" in cells and any(name.lower().startswith("signature") for name in cells):
            columns = {name.lower(): index for index, name in enumerate(cells)}
            continue
        if len(cells) != len(columns) or "key" not in columns:
            continue
        key = cells[columns["key"]]
        if not KEY.fullmatch(key):
            continue
        symptom = cells[columns.get("signature / symptom", 2)]
        literals = tuple(dict.fromkeys(
            literal.strip() for literal in CODE_SPAN.findall(symptom)
            if len(literal.strip()) >= MINIMUM_LITERAL and SHAPED_LITERAL.search(literal)
        ))
        rows.append((key, " ".join(symptom.split()), cells[columns.get("permanent fix", 4)], literals))
    return rows


def signatures(root: Path) -> tuple[Signature, ...]:
    """Every keyed row of the ledger that can be matched. Empty when a project carries no ledger."""
    return tuple(Signature(key, literals, symptom, fix) for key, symptom, fix, literals in _rows(root) if literals)


def unmatchable(root: Path) -> list[str]:
    """Ledger rows no finding can ever match, each with the fix (#59).

    A row is matched by a backticked literal of at least MINIMUM_LITERAL characters shaped like a
    message or path; a row quoting `make done` or nothing at all used to vanish silently.
    """
    return [f"{LEDGER} {key} cannot be matched: quote at least one backticked literal of "
            f"{MINIMUM_LITERAL}+ characters from the real message or path in its symptom"
            for key, _symptom, _fix, literals in _rows(root) if not literals]


def match(finding: str, records: tuple[Signature, ...]) -> Signature | None:
    """The recorded signature a finding repeats, or None when it is a new failure."""
    for signature in records:
        if any(literal in finding for literal in signature.literals):
            return signature
    return None


def recognition(findings: list[str], records: tuple[Signature, ...]) -> list[str]:
    """One line per recorded signature a finding repeats, carrying that signature's fix."""
    seen: dict[str, str] = {}
    for finding in findings:
        signature = match(finding, records)
        if signature is None:
            continue
        seen.setdefault(signature.key, f"known failure {signature.key} ({LEDGER}): {signature.symptom} — "
                                       f"permanent fix: {signature.fix}")
    return list(seen.values())