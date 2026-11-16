"""Station Clock: the only source of UTC for station logic (K15, K16)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from ssir.domain_rules import CLOCK_TOLERANCE


class StationClock:
    def __init__(self, system_time: Callable[[], datetime],
                 tolerance: timedelta = CLOCK_TOLERANCE) -> None:
        self._system_time = system_time
        self._tolerance = tolerance
        self._offset = timedelta(0)     # Earth time minus system time; set at each sync (K16)

    def now(self) -> datetime:
        return self._system_time() + self._offset

    def apply_earth_time(self, earth_time: datetime, round_trip: timedelta) -> None:
        raise NotImplementedError

    def drift_bound(self) -> timedelta:
        raise NotImplementedError

    def drift_warning(self) -> bool:
        raise NotImplementedError
