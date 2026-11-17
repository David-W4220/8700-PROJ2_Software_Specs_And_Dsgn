"""Station Clock: the only source of UTC for station logic (K15, K16)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Optional

from ssir.domain_rules import CLOCK_TOLERANCE

# Decision (Nov 16, 2026, Claude): until two corrections have measured the drift
# rate, assume 50 ppm, a common quartz-oscillator tolerance (about 30 s per week).
ASSUMED_DRIFT_RATE = 50e-6


class StationClock:
    def __init__(self, system_time: Callable[[], datetime],
                 tolerance: timedelta = CLOCK_TOLERANCE) -> None:
        self._system_time = system_time
        self._tolerance = tolerance
        self._offset = timedelta(0)     # Earth time minus system time; set at each sync (K16)
        self._corrected_at: Optional[datetime] = None   # system time of the last correction
        self._uncertainty = timedelta(0)                # half the last round trip
        self._rate: Optional[float] = None              # measured drift, seconds per second

    def now(self) -> datetime:
        return self._system_time() + self._offset

    def apply_earth_time(self, earth_time: datetime, round_trip: timedelta) -> None:
        """Correct the offset from a handshake reply that arrived just now: Earth
        stamped it about half a round trip ago (NFR-005, K16)."""
        if earth_time.tzinfo is None:
            raise ValueError("earth_time must be timezone-aware")
        system = self._system_time()
        offset = earth_time + round_trip / 2 - system
        if self._corrected_at is not None:
            elapsed = (system - self._corrected_at).total_seconds()
            if elapsed > 0:
                self._rate = abs((offset - self._offset).total_seconds()) / elapsed
        self._offset, self._corrected_at, self._uncertainty = offset, system, round_trip / 2

    def drift_bound(self) -> timedelta:
        if self._corrected_at is None:
            return timedelta.max          # never corrected: no bound is known
        rate = ASSUMED_DRIFT_RATE if self._rate is None else self._rate
        elapsed = max((self._system_time() - self._corrected_at).total_seconds(), 0.0)
        return self._uncertainty + timedelta(seconds=elapsed * rate)

    def drift_warning(self) -> bool:
        return self.drift_bound() > self._tolerance
