"""Test-only clock shift: `make test-future` runs the suite SHIFT_DAYS ahead.

Loaded through PYTHONPATH, so the kit subprocesses the tests start are shifted
too. A suite that passes today but fails in two years has calendar rot (#10):
fixtures and checks must follow the calendar, never a fixed date.
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
