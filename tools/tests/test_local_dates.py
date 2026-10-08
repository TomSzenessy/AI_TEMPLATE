"""A person's local date is never "in the future" (#51, mixed clocks).

The kit's freshness day is UTC, but reviewers write their local date. At
00:09 CEST on 2026-10-08 it is still 2026-10-07 in UTC, and the kit used to
reject the reviewer's correct date as future-dated.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kit import core  # noqa: E402

UTC_NOW = datetime(2026, 10, 7, 22, 9, tzinfo=timezone.utc)  # 00:09 on 2026-10-08 in Berlin


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return UTC_NOW if tz else UTC_NOW.replace(tzinfo=None)


class LocalDateTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(core, "datetime", FrozenDatetime)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_local_date_ahead_of_utc_is_not_future(self) -> None:
        self.assertEqual(core.today(), date(2026, 10, 7))
        self.assertFalse(core.date_is_future(date(2026, 10, 8)))
        self.assertFalse(core.date_is_stale(date(2026, 10, 8)))
        self.assertIsNone(core.reviewer_problem("- **Reviewer/date:** octocat 2026-10-08"))

    def test_a_date_beyond_every_timezone_is_future(self) -> None:
        self.assertTrue(core.date_is_future(date(2026, 10, 9)))
        self.assertEqual(core.reviewer_problem("- **Reviewer/date:** octocat 2026-10-09"),
                         "Reviewer/date is in the future (a typo?)")

    def test_staleness_still_counts_from_the_utc_day(self) -> None:
        self.assertFalse(core.date_is_stale(date(2025, 10, 7)))
        self.assertTrue(core.date_is_stale(date(2025, 10, 6)))


class OneClockTests(unittest.TestCase):
    def test_no_kit_or_test_module_reads_the_local_calendar_day(self) -> None:
        """A comparison against the local day is the mixed-clock defect; `core.today()` (UTC) is the one clock."""
        offenders = []
        for folder in (Path(__file__).resolve().parents[1] / "kit", Path(__file__).resolve().parent):
            for path in folder.glob("*.py"):
                if path.name != Path(__file__).name and "date.today()" in path.read_text(encoding="utf-8"):
                    offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_today_names_its_clock(self) -> None:
        self.assertIn("UTC", core.today.__doc__)


if __name__ == "__main__":
    unittest.main()
