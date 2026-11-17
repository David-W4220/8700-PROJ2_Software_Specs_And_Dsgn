"""Sync Endpoint: the Earth side of a sync session — handshake, signature and
revocation check, deduplication, request validation, acknowledgements and the
change feed (FR-029, FR-032, NFR-003, NFR-004, K10, K12, K13)."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from ssir.domain_rules import (
    ChangeBatch, Handshake, HandshakeReply, IdentityDirectory, InventoryUpdate,
    Outcome, ReceiptUnit, Signature, User,
)
from ssir.earth.earth_store import EarthStore
from ssir.earth.inventory_service import InventoryService
from ssir.earth.mission_service import MissionService


class SyncEndpoint:
    def __init__(self, store: EarthStore, inventory: InventoryService,
                 missions: MissionService, directory: IdentityDirectory,
                 now: Callable[[], datetime]) -> None:
        self._store = store
        self._inventory = inventory
        self._missions = missions
        self._directory = directory
        self._now = now

    def handshake(self, hello: Handshake) -> HandshakeReply:
        with self._store.transaction() as tx:
            tx.set_reported_pending_count(hello.pending_count)
            tx.set_session_open(True)
            committed = tx.committed_station_sequence()
        return HandshakeReply(earth_time=self._now(), committed_sequence=committed)

    def receive_update(self, update: InventoryUpdate) -> Outcome:
        raise NotImplementedError

    def receive_receipt(self, receipt: ReceiptUnit) -> Outcome:
        raise NotImplementedError

    def verify_signer(self, content: bytes, signature: Signature,
                      event_time: datetime) -> User:
        raise NotImplementedError

    def change_feed(self, cursor: int, before: datetime) -> ChangeBatch:
        raise NotImplementedError

    def complete_sync(self, pull_started_at: datetime) -> None:
        raise NotImplementedError

    def close_session(self) -> None:
        raise NotImplementedError
