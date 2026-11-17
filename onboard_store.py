"""Onboard Store: durable station state with serialized, all-or-nothing writes.

One writer for all station devices (K1); commit returns only when durable (K2);
history content is insert-only (K18); the queue is a view of records whose
status is Awaiting sync, ordered by sequence (K4, K8).
"""
from __future__ import annotations

import dataclasses
import sqlite3
import threading
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Union
from uuid import UUID

from ssir.domain_rules import (
    _describe_alert, _describe_discrepancy, _describe_mission_status, _describe_update,
    _dumps, _loads,
)
from ssir.domain_rules import (
    ActivityEvent, ConflictRecord, Discrepancy, InventoryItem, InventoryUpdate,
    ActivityKind, DiscrepancyStatus, ManifestDraft, MissionStatus, NotFound, ReceiptUnit, ResupplyMission, StatusHistoryEntry,
    StorageLocation, SupplyAlert, SyncStatus, User, ValidationError,
)

SendableUnit = Union[InventoryUpdate, ReceiptUnit]

# Decision (Nov 16, 2026): station commit sequences start at 101 and the
# station display ID is "U" followed by the sequence (U101, U102, ...).
FIRST_STATION_SEQUENCE = 101
STATION_DISPLAY_PREFIX = "U"

# Final mission statuses (Mission lifecycle); not listed among held missions (K7).
_FINAL_STATUSES = (MissionStatus.RECEIVED, MissionStatus.CANCELLED)

# Statuses counted as pending (FR-001, FR-028).
_PENDING_STATUSES = (SyncStatus.AWAITING_SYNC.value, SyncStatus.CONFLICT.value)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS locations (
    location_id TEXT PRIMARY KEY,
    data        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    data    TEXT NOT NULL
);
-- Private keys encrypted under each person's sign-in secret (K9).
CREATE TABLE IF NOT EXISTS private_keys (
    user_id TEXT PRIMARY KEY,
    blob    BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    data    TEXT NOT NULL
);
-- Barcodes are unique across items (InventoryItem); lookup index (NFR-007).
CREATE TABLE IF NOT EXISTS barcodes (
    barcode TEXT PRIMARY KEY,
    item_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS barcodes_item ON barcodes (item_id);
CREATE TABLE IF NOT EXISTS earth_base (
    item_id TEXT PRIMARY KEY,
    data    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    item_id  TEXT NOT NULL,
    status   TEXT NOT NULL,
    data     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS alerts_one_active
    ON alerts (item_id) WHERE status = 'Active';
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    data       TEXT NOT NULL
);
-- A receipt syncs as one unit (FR-025); its sequence follows its updates'.
CREATE TABLE IF NOT EXISTS receipts (
    receipt_id  TEXT PRIMARY KEY,
    sequence    INTEGER NOT NULL UNIQUE,
    mission_id  TEXT NOT NULL,
    sync_status TEXT NOT NULL,
    rejected_at TEXT,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS receipts_status_sequence ON receipts (sync_status, sequence);
CREATE TRIGGER IF NOT EXISTS receipts_no_delete BEFORE DELETE ON receipts
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS receipts_only_status_changes
    BEFORE UPDATE OF receipt_id, sequence, mission_id, data ON receipts
    BEGIN SELECT RAISE(ABORT, 'only syncStatus may change'); END;
CREATE TABLE IF NOT EXISTS discrepancies (
    row_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    discrepancy_id TEXT NOT NULL,
    mission_id     TEXT NOT NULL,
    recorded_at    TEXT NOT NULL,
    data           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS discrepancies_mission ON discrepancies (mission_id, row_id);
CREATE TRIGGER IF NOT EXISTS discrepancies_no_delete BEFORE DELETE ON discrepancies
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS discrepancies_no_update BEFORE UPDATE ON discrepancies
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
-- sync_status and rejected_at are the only mutable columns (NFR-006); they
-- take precedence over the same fields inside the insert-only data column.
-- Manifest versions held on board (K7); read-only once stored.
CREATE TABLE IF NOT EXISTS manifests (
    mission_id TEXT NOT NULL,
    version    INTEGER NOT NULL,
    data       TEXT NOT NULL,
    PRIMARY KEY (mission_id, version)
);
CREATE TABLE IF NOT EXISTS updates (
    update_id   TEXT PRIMARY KEY,
    sequence    INTEGER NOT NULL UNIQUE,
    item_id     TEXT NOT NULL,
    sync_status TEXT NOT NULL,
    rejected_at TEXT,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS updates_status_sequence ON updates (sync_status, sequence);
CREATE INDEX IF NOT EXISTS updates_status_rejected ON updates (sync_status, rejected_at);
CREATE TRIGGER IF NOT EXISTS updates_no_delete
    BEFORE DELETE ON updates
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS updates_only_status_changes
    BEFORE UPDATE OF update_id, sequence, item_id, data ON updates
    BEGIN SELECT RAISE(ABORT, 'only syncStatus may change'); END;
"""


def _update_row(sync_status: str, rejected_at: Optional[str], data: str) -> InventoryUpdate:
    """An update as stored, with the live sync status and rejection time."""
    return dataclasses.replace(
        _loads(data), sync_status=SyncStatus(sync_status),
        rejected_at=None if rejected_at is None else datetime.fromisoformat(rejected_at))


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return None if moment is None else moment.isoformat()


# --------------------------------------------------------------------------
# Transactions
# --------------------------------------------------------------------------

class StationReadTx:
    """A consistent read-only view of the onboard store."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._stamp: Optional[str] = None

    def get_item(self, item_id: str) -> InventoryItem:
        row = self._conn.execute("SELECT data FROM items WHERE item_id = ?", (item_id,)).fetchone()
        if row is None:
            raise NotFound([f"no item {item_id}"])
        return _loads(row[0])

    def list_items(self) -> list[InventoryItem]:
        rows = self._conn.execute("SELECT data FROM items ORDER BY item_id")
        return [_loads(data) for (data,) in rows]

    def find_by_barcode(self, barcode: str) -> Optional[InventoryItem]:
        row = self._conn.execute(
            "SELECT items.data FROM barcodes JOIN items USING (item_id) "
            "WHERE barcodes.barcode = ?", (barcode,)).fetchone()
        return None if row is None else _loads(row[0])

    def earth_base(self, item_id: str) -> InventoryItem:
        row = self._conn.execute("SELECT data FROM earth_base WHERE item_id = ?", (item_id,)).fetchone()
        if row is None:
            raise NotFound([f"no Earth version of item {item_id}"])
        return _loads(row[0])

    def list_locations(self) -> list[StorageLocation]:
        return [_loads(data) for (data,) in
                self._conn.execute("SELECT data FROM locations ORDER BY location_id")]

    def get_user(self, user_id: str) -> User:
        row = self._conn.execute("SELECT data FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            raise NotFound([f"no user {user_id}"])
        return _loads(row[0])

    def get_encrypted_private_key(self, user_id: str) -> bytes:
        row = self._conn.execute(
            "SELECT blob FROM private_keys WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            raise NotFound([f"no private key for {user_id}"])
        return bytes(row[0])

    def get_active_alert(self, item_id: str) -> Optional[SupplyAlert]:
        row = self._conn.execute(
            "SELECT data FROM alerts WHERE item_id = ? AND status = 'Active'", (item_id,)).fetchone()
        return None if row is None else _loads(row[0])

    def list_active_alerts(self) -> list[SupplyAlert]:
        rows = self._conn.execute(
            "SELECT data FROM alerts WHERE status = 'Active' ORDER BY alert_id")
        return [_loads(data) for (data,) in rows]

    def get_mission(self, mission_id: str) -> ResupplyMission:
        row = self._conn.execute("SELECT data FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
        if row is None:
            raise NotFound([f"no mission {mission_id}"])
        return _loads(row[0])

    def list_missions(self) -> list[ResupplyMission]:
        missions = [_loads(data) for (data,) in
                    self._conn.execute("SELECT data FROM missions ORDER BY mission_id")]
        return [m for m in missions if m.mission_status not in _FINAL_STATUSES]

    def get_manifest(self, mission_id: str, version: Optional[int] = None) -> ManifestDraft:
        if version is None:
            row = self._conn.execute(
                "SELECT data FROM manifests WHERE mission_id = ? ORDER BY version DESC LIMIT 1",
                (mission_id,)).fetchone()
        else:
            row = self._conn.execute("SELECT data FROM manifests WHERE mission_id = ? AND version = ?",
                                     (mission_id, version)).fetchone()
        if row is None:
            raise NotFound([f"no manifest for {mission_id}"])
        return _loads(row[0])

    def list_discrepancies(self, mission_id: str) -> list[Discrepancy]:
        """Latest state of each discrepancy of the mission, in recording order."""
        latest: dict[str, Discrepancy] = {}
        for (data,) in self._conn.execute(
                "SELECT data FROM discrepancies WHERE mission_id = ? ORDER BY row_id", (mission_id,)):
            discrepancy = _loads(data)
            latest[discrepancy.discrepancy_id] = discrepancy
        return list(latest.values())

    def item_history(self, item_id: str) -> list[InventoryUpdate]:
        # In commit order (rowid = insertion order), as order_history expects.
        rows = self._conn.execute(
            "SELECT sync_status, rejected_at, data FROM updates WHERE item_id = ? ORDER BY rowid",
            (item_id,))
        return [_update_row(*row) for row in rows]

    def recent_events(self, since: datetime) -> list[ActivityEvent]:
        items = {item.item_id: item for item in self.list_items()}
        events: list[ActivityEvent] = []
        for (data,) in self._conn.execute("SELECT data FROM updates ORDER BY sequence"):
            update: InventoryUpdate = _loads(data)
            if update.event_time >= since:
                events.append(ActivityEvent(update.event_time, ActivityKind.INVENTORY_UPDATE,
                                            _describe_update(update, items.get(update.item_id))))
        for (data,) in self._conn.execute("SELECT data FROM missions ORDER BY mission_id"):
            mission: ResupplyMission = _loads(data)
            for entry in mission.status_history:
                if entry.time >= since:
                    events.append(ActivityEvent(entry.time, ActivityKind.MISSION_STATUS,
                                                _describe_mission_status(mission.mission_id, entry)))
        for (data,) in self._conn.execute("SELECT data FROM alerts ORDER BY alert_id"):
            alert: SupplyAlert = _loads(data)
            item = items.get(alert.item_id)
            if alert.raised_at >= since:
                events.append(ActivityEvent(alert.raised_at, ActivityKind.ALERT_RAISED,
                                            _describe_alert(item, alert.item_id, raised=True)))
            if alert.resolved_at is not None and alert.resolved_at >= since:
                events.append(ActivityEvent(alert.resolved_at, ActivityKind.ALERT_RESOLVED,
                                            _describe_alert(item, alert.item_id, raised=False)))
        for recorded_at, data in self._conn.execute(
                "SELECT recorded_at, data FROM discrepancies ORDER BY row_id"):
            discrepancy: Discrepancy = _loads(data)
            at = datetime.fromisoformat(recorded_at)
            if at >= since:
                kind = (ActivityKind.DISCREPANCY_RESOLVED
                        if discrepancy.status is DiscrepancyStatus.RESOLVED
                        else ActivityKind.DISCREPANCY_RECORDED)
                events.append(ActivityEvent(at, kind, _describe_discrepancy(
                    discrepancy, items.get(discrepancy.item_id or ""))))
        events.sort(key=lambda event: event.time)
        return events

    def sendable_after(self, sequence: int, limit: int) -> list[SendableUnit]:
        raise NotImplementedError

    def pending_page(self, offset: int, limit: int) -> list[SendableUnit]:
        placeholders = ",".join("?" for _ in _PENDING_STATUSES)
        rows = self._conn.execute(
            f"SELECT sync_status, rejected_at, data FROM updates "
            f"WHERE sync_status IN ({placeholders}) ORDER BY sequence LIMIT ? OFFSET ?",
            (*_PENDING_STATUSES, limit, offset))
        return [_update_row(*row) for row in rows]

    def pending_count(self) -> int:
        placeholders = ",".join("?" for _ in _PENDING_STATUSES)
        row = self._conn.execute(
            f"SELECT COUNT(*) FROM updates WHERE sync_status IN ({placeholders})",
            _PENDING_STATUSES).fetchone()
        return int(row[0])

    def rejected_since(self, since: datetime) -> list[SendableUnit]:
        rows = self._conn.execute(
            "SELECT sync_status, rejected_at, data FROM updates "
            "WHERE sync_status = ? AND rejected_at >= ? ORDER BY sequence",
            (SyncStatus.REJECTED.value, _iso(since)))
        return [_update_row(*row) for row in rows]

    def open_conflicts(self) -> list[ConflictRecord]:
        raise NotImplementedError

    def pull_cursor(self) -> int:
        raise NotImplementedError

    def last_full_sync(self) -> Optional[datetime]:
        return self._meta_time("last_full_sync")

    def last_earth_contact(self) -> Optional[datetime]:
        """Addition (Nov 16, 2026, not in contracts.md): time of the last
        successful contact with Earth, recorded by the Sync Agent (FR-002)."""
        return self._meta_time("last_earth_contact")

    def _meta_time(self, key: str) -> Optional[datetime]:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else datetime.fromisoformat(row[0])


class StationWriteTx(StationReadTx):
    """A serialized write transaction; everything commits together or not at all."""

    def put_item(self, item: InventoryItem) -> None:
        if item.quantity < 0:
            raise ValidationError([f"{item.item_id}: quantity must be at least 0"])
        self._conn.execute(
            "INSERT INTO items (item_id, data) VALUES (?, ?) "
            "ON CONFLICT (item_id) DO UPDATE SET data = excluded.data",
            (item.item_id, _dumps(item)))
        # Decision (Nov 16, 2026): a barcode held by another item is rejected.
        self._conn.execute("DELETE FROM barcodes WHERE item_id = ?", (item.item_id,))
        try:
            self._conn.executemany(
                "INSERT INTO barcodes (barcode, item_id) VALUES (?, ?)",
                [(code, item.item_id) for code in item.barcodes])
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"{item.item_id}: barcode already used by another item") from exc

    def put_earth_base(self, item: InventoryItem) -> None:
        self._conn.execute(
            "INSERT INTO earth_base (item_id, data) VALUES (?, ?) "
            "ON CONFLICT (item_id) DO UPDATE SET data = excluded.data",
            (item.item_id, _dumps(item)))

    def put_location(self, location: StorageLocation) -> None:
        self._conn.execute(
            "INSERT INTO locations (location_id, data) VALUES (?, ?) "
            "ON CONFLICT (location_id) DO UPDATE SET data = excluded.data",
            (location.location_id, _dumps(location)))

    def put_user(self, user: User) -> None:
        self._conn.execute(
            "INSERT INTO users (user_id, data) VALUES (?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET data = excluded.data",
            (user.user_id, _dumps(user)))

    def put_encrypted_private_key(self, user_id: str, blob: bytes) -> None:
        """Addition (Nov 16, 2026, not in contracts.md; Design question 1): the
        identity system's encrypted private key, stored by the pull."""
        self._conn.execute(
            "INSERT INTO private_keys (user_id, blob) VALUES (?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET blob = excluded.blob", (user_id, blob))

    def append_update(self, update: InventoryUpdate) -> InventoryUpdate:
        key = str(update.update_id)
        if self._conn.execute("SELECT 1 FROM updates WHERE update_id = ?", (key,)).fetchone():
            raise ValueError(f"update {key} already exists")
        sequence = self._take_sequence()
        if update.sequence is not None and update.sequence != sequence:
            raise ValueError(f"sequence {update.sequence} was not reserved by next_sequence()")
        stored = dataclasses.replace(
            update, sequence=sequence, display_id=f"{STATION_DISPLAY_PREFIX}{sequence}")
        self._conn.execute(
            "INSERT INTO updates (update_id, sequence, item_id, sync_status, rejected_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key, sequence, stored.item_id, stored.sync_status.value,
             _iso(stored.rejected_at), _dumps(stored)))
        return stored

    def append_receipt(self, receipt: ReceiptUnit) -> ReceiptUnit:
        key = str(receipt.receipt_id)
        if self._conn.execute("SELECT 1 FROM receipts WHERE receipt_id = ?", (key,)).fetchone():
            raise ValueError(f"receipt {key} already exists")
        sequence = self._take_sequence()
        if receipt.sequence is not None and receipt.sequence != sequence:
            raise ValueError(f"sequence {receipt.sequence} was not reserved by next_sequence()")
        stored = dataclasses.replace(receipt, sequence=sequence)
        self._conn.execute(
            "INSERT INTO receipts (receipt_id, sequence, mission_id, sync_status, rejected_at, data) "
            "VALUES (?, ?, ?, ?, NULL, ?)",
            (key, sequence, stored.mission_id, stored.sync_status.value, _dumps(stored)))
        return stored

    def set_sync_status(self, key: UUID, status: SyncStatus,
                        rejected_at: Optional[datetime] = None) -> None:
        cursor = self._conn.execute(
            "UPDATE updates SET sync_status = ?, rejected_at = ? WHERE update_id = ?",
            (status.value, _iso(rejected_at), str(key)))
        if cursor.rowcount == 0:
            cursor = self._conn.execute(
                "UPDATE receipts SET sync_status = ?, rejected_at = ? WHERE receipt_id = ?",
                (status.value, _iso(rejected_at), str(key)))
        if cursor.rowcount == 0:
            raise NotFound([f"no update or receipt {key}"])

    def put_conflict(self, conflict: ConflictRecord) -> None:
        raise NotImplementedError

    def put_alert(self, alert: SupplyAlert) -> None:
        try:
            self._conn.execute(
                "INSERT INTO alerts (alert_id, item_id, status, data) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (alert_id) DO UPDATE SET item_id = excluded.item_id, "
                "status = excluded.status, data = excluded.data",
                (alert.alert_id, alert.item_id, alert.alert_status.value, _dumps(alert)))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"{alert.item_id} already has an Active alert") from exc

    def put_manifest(self, mission_id: str, version: int, draft: ManifestDraft) -> None:
        """Addition (Nov 16, 2026, not in contracts.md): a manifest version
        received from Earth (K7). A stored version is never changed."""
        row = self._conn.execute(
            "SELECT data FROM manifests WHERE mission_id = ? AND version = ?",
            (mission_id, version)).fetchone()
        if row is not None:
            if row[0] != _dumps(draft):
                raise ValueError(f"{mission_id} manifest version {version} differs from the stored one")
            return
        self._conn.execute("INSERT INTO manifests (mission_id, version, data) VALUES (?, ?, ?)",
                           (mission_id, version, _dumps(draft)))

    def put_mission(self, mission: ResupplyMission) -> None:
        self._conn.execute(
            "INSERT INTO missions (mission_id, data) VALUES (?, ?) "
            "ON CONFLICT (mission_id) DO UPDATE SET data = excluded.data",
            (mission.mission_id, _dumps(mission)))

    def append_status_history(self, mission_id: str, entry: StatusHistoryEntry) -> None:
        mission = self.get_mission(mission_id)
        self.put_mission(dataclasses.replace(mission, status_history=mission.status_history + (entry,)))

    def append_discrepancy(self, discrepancy: Discrepancy) -> None:
        """A resolution is a new row (NFR-006). The row is stamped with the
        station clock time the receipt (or the pulled resolution) commits."""
        self._conn.execute(
            "INSERT INTO discrepancies (discrepancy_id, mission_id, recorded_at, data) "
            "VALUES (?, ?, ?, ?)",
            (discrepancy.discrepancy_id, discrepancy.mission_id,
             self._stamp or datetime.now(timezone.utc).isoformat(), _dumps(discrepancy)))

    def stamp(self, at: datetime) -> None:
        """Time used for rows written in this transaction that carry no time."""
        self._stamp = at.isoformat()

    def set_pull_cursor(self, cursor: int) -> None:
        raise NotImplementedError

    def record_full_sync(self, at: datetime) -> None:
        self._set_meta_time("last_full_sync", at)

    def record_earth_contact(self, at: datetime) -> None:
        """Addition (Nov 16, 2026, not in contracts.md): see last_earth_contact."""
        self._set_meta_time("last_earth_contact", at)

    def _set_meta_time(self, key: str, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("times must be timezone-aware UTC")
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, at.isoformat()))

    def next_sequence(self) -> int:
        """Addition (Nov 16, 2026, not in contracts.md): the commit sequence the
        next append_update in this transaction will take, so the Command Handler
        can sign it first (contracts: the signature covers the sequence)."""
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'next_sequence'").fetchone()
        return int(row[0]) if row else FIRST_STATION_SEQUENCE

    def _take_sequence(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'next_sequence'").fetchone()
        sequence = int(row[0]) if row else FIRST_STATION_SEQUENCE
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES ('next_sequence', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (str(sequence + 1),))
        return sequence


class OnboardStore:
    """The embedded transactional database on the onboard host."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._open = False
        self._write_lock = threading.Lock()

    def open(self) -> None:
        try:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript(_SCHEMA)
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise OSError(f"cannot open onboard store at {self._path}: {exc}") from exc
        self._open = True

    def close(self) -> None:
        self._open = False

    def read(self) -> AbstractContextManager[StationReadTx]:
        self._require_open()
        return self._read()

    def write(self) -> AbstractContextManager[StationWriteTx]:
        self._require_open()
        return self._write()

    def _require_open(self) -> None:
        if not self._open:
            raise RuntimeError("onboard store is not open")

    def _connect(self, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            uri = Path(self._path).resolve().as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=30, isolation_level=None)
        else:
            conn = sqlite3.connect(self._path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    @contextmanager
    def _read(self) -> Iterator[StationReadTx]:
        conn = self._connect(read_only=True)
        try:
            conn.execute("BEGIN")
            yield StationReadTx(conn)
        finally:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            conn.close()

    @contextmanager
    def _write(self) -> Iterator[StationWriteTx]:
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    yield StationWriteTx(conn)
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
                conn.execute("COMMIT")
            finally:
                conn.close()
