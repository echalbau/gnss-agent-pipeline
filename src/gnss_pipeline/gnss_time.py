"""GPS calendar helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

GPS_EPOCH = date(1980, 1, 6)


@dataclass(frozen=True)
class GnssDay:
    year: int
    doy: int
    week: int
    dow: int

    @property
    def yy(self) -> int:
        return self.year % 100

    def fmt(self) -> dict[str, int]:
        return {"year": self.year, "doy": self.doy, "week": self.week, "dow": self.dow,
                "yy": self.yy}


def gnss_day(d: date | datetime) -> GnssDay:
    if isinstance(d, datetime):
        d = d.date()
    days = (d - GPS_EPOCH).days
    return GnssDay(year=d.year, doy=d.timetuple().tm_yday, week=days // 7, dow=days % 7)


def days_spanned(first: datetime, last: datetime) -> list[GnssDay]:
    out, d = [], first.date()
    while d <= last.date():
        out.append(gnss_day(d))
        d += timedelta(days=1)
    return out
