"""Sync Agent: the only station module that talks to Earth (FR-029, FR-030
station side, FR-025, NFR-004, K12–K14)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol, Union

from ssir.domain_rules import (
    Change, ChangeBatch, Handshake, HandshakeReply, InventoryUpdate, LinkStatus,
    Outcome, ReceiptUnit,
)
from ssir.station.clock import StationClock
from ssir.station.onboard_store import OnboardStore

LINK_CHECK_INTERVAL = timedelta(seconds=30)   # NFR-004
BACKOFF_CAP = timedelta(seconds=60)           # NFR-004


class SyncTransport(Protocol):
    """The encrypted, mutually authenticated channel to the Earth Gateway (K11).
    Injected; this is the interface the Sync Agent needs, not a module."""

    def ping(self, hello: Handshake) -> bool: ...
    def handshake(self, hello: Handshake) -> HandshakeReply: ...
    def send(self, unit: Union[InventoryUpdate, ReceiptUnit]) -> Outcome: ...
    def pull(self, cursor: int, before: datetime) -> ChangeBatch: ...
    def complete(self, pull_started_at: datetime) -> None: ...


@dataclass(frozen=True)
class SyncReport:
    sent: int
    conflicts: int
    rejected: int
    pulled: int
    fully_completed: bool
    completed_at: Optional[datetime]


class SyncAgent:
    def __init__(self, store: OnboardStore, clock: StationClock, transport: SyncTransport,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._store = store
        self._clock = clock
        self._transport = transport
        self._sleep = sleep

    def run(self, stop: threading.Event) -> None:
        raise NotImplementedError

    def check_link(self) -> bool:
        raise NotImplementedError

    def sync_now(self) -> SyncReport:
        raise NotImplementedError

    def handshake(self) -> HandshakeReply:
        raise NotImplementedError

    def send_pending(self, committed_sequence: int) -> int:
        raise NotImplementedError

    def apply_outcome(self, outcome: Outcome) -> None:
        raise NotImplementedError

    def pull_changes(self, pull_started_at: datetime) -> int:
        raise NotImplementedError

    def apply_change(self, change: Change) -> None:
        raise NotImplementedError

    def link_status(self) -> LinkStatus:
        raise NotImplementedError
