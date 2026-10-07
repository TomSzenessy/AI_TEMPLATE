"""Test-only clock shift: `make test-future` runs the suite SHIFT_DAYS ahead.

Loaded through PYTHONPATH, so the kit subprocesses the tests start are shifted
too. A suite that passes today but fails in two years has calendar rot (#10):
fixtures and checks must follow the calendar, never a fixed date.

Limits (#43 T-15): this shifts `date.today()`, `datetime.now()` and
`datetime.date()` only. It does NOT shift git dates (author/committer dates in
history stay real) and it does NOT touch `time.time()`/`time.monotonic()`.
Tests must therefore never derive expectations from git history dates or epoch
seconds; those stay real-time and unshifted even under `make test-future`.
"""

import datetime as _dt
import os

_SHIFT = _dt.timedelta(days=int(os.environ.get("SHIFT_DAYS", "0")))
_RealDate, _RealDateTime = _dt.date, _dt.datetime


class _Date(_dt.date):
    @classmethod
    def today(cls):
        shifted = _RealDate.today() + _SHIFT
        return cls(shifted.year, shifted.month, shifted.day)


class _DateTime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        r = _RealDateTime.now(tz) + _SHIFT
        return cls(r.year, r.month, r.day, r.hour, r.minute, r.second, r.microsecond, r.tzinfo)

    def date(self):
        return _Date(self.year, self.month, self.day)


_dt.date, _dt.datetime = _Date, _DateTime
