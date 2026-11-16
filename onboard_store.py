"""Onboard Store: durable station state with serialized, all-or-nothing writes.

One writer for all station devices (K1); commit returns only when durable (K2);
history content is insert-only (K18); the queue is a view of records whose
status is Awaiting sync, ordered by sequence (K4, K8).
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
import threading
from contextlib import AbstractContextManager, contextmanager
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Optional, Union
from uuid import UUID

from ssir import domain_rules
from ssir.domain_rules import (
    ActivityEvent, ConflictRecord, Discrepancy, InventoryItem, InventoryUpdate,
    ManifestDraft, NotFound, ReceiptUnit, ResupplyMission, StatusHistoryEntry,
    StorageLocation, SupplyAlert, SyncStatus, User, ValidationError,
)

SendableUnit = Union[InventoryUpdate, ReceiptUnit]

# Decision (Nov 16, 2026): station commit sequences start at 101 and the
# station display ID is "U" followed by the sequence (U101, U102, ...).
FIRST_STATION_SEQUENCE = 101
STATION_DISPLAY_PREFIX = "U"

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
-- sync_status and rejected_at are the only mutable columns (NFR-006); they
-- take precedence over the same fields inside the insert-only data column.
CREATE TABLE IF NOT EXISTS updates (
    update_id   TEXT PRIMARY KEY,
    sequence    INTEGER NOT NULL UNIQUE,
    item_id     TEXT NOT NULL,
    sync_status TEXT NOT NULL,
    rejected_at TEXT,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS updates_status_sequence ON updates (sync_status, sequence);
CREATE TRIGGER IF NOT EXISTS updates_no_delete
    BEFORE DELETE ON updates
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS updates_only_status_changes
    BEFORE UPDATE OF update_id, sequence, item_id, data ON updates
    BEGIN SELECT RAISE(ABORT, 'only syncStatus may change'); END;
"""


# --------------------------------------------------------------------------
# Tagged JSON encoding of the Domain Rules value types
# --------------------------------------------------------------------------

def _encode(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Enum):
        return {"$enum": type(value).__name__, "v": value.value}
    if isinstance(value, Decimal):
        return {"$dec": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("times must be timezone-aware UTC")
        return {"$dt": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, (tuple, list)):
        return {"$tuple": [_encode(v) for v in value]}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"$dc": type(value).__name__,
                "f": {f.name: _encode(getattr(value, f.name)) for f in dataclasses.fields(value)}}
    if isinstance(value, dict) or hasattr(value, "items"):
        return {"$map": [[_encode(k), _encode(v)] for k, v in value.items()]}
    raise TypeError(f"cannot store value of type {type(value).__name__}")


def _domain_type(name: str) -> type:
    cls = getattr(domain_rules, name, None)
    if not isinstance(cls, type):
        raise TypeError(f"unknown stored type {name!r}")
    return cls


def _decode(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if "$enum" in value:
        return _domain_type(value["$enum"])(value["v"])
    if "$dec" in value:
        return Decimal(value["$dec"])
    if "$dt" in value:
        return datetime.fromisoformat(value["$dt"])
    if "$date" in value:
        return date.fromisoformat(value["$date"])
    if "$uuid" in value:
        return UUID(value["$uuid"])
    if "$bytes" in value:
        return bytes.fromhex(value["$bytes"])
    if "$tuple" in value:
        return tuple(_decode(v) for v in value["$tuple"])
    if "$dc" in value:
        cls = _domain_type(value["$dc"])
        return cls(**{k: _decode(v) for k, v in value["f"].items()})
    if "$map" in value:
        return {_decode(k): _decode(v) for k, v in value["$map"]}
    raise TypeError("unrecognized stored value")


def _dumps(obj: Any) -> str:
    return json.dumps(_encode(obj), separators=(",", ":"), sort_keys=True)


def _loads(text: str) -> Any:
    return _decode(json.loads(text))


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return None if moment is None else _encode(moment)["$dt"]


# --------------------------------------------------------------------------
# Transactions
# --------------------------------------------------------------------------

class StationReadTx:
    """A consistent read-only view of the onboard store."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_item(self, item_id: str) -> InventoryItem:
        raise NotImplementedError

    def list_items(self) -> list[InventoryItem]:
        rows = self._conn.execute("SELECT data FROM items ORDER BY item_id")
        return [_loads(data) for (data,) in rows]

    def find_by_barcode(self, barcode: str) -> Optional[InventoryItem]:
        row = self._conn.execute(
            "SELECT items.data FROM barcodes JOIN items USING (item_id) "
            "WHERE barcodes.barcode = ?", (barcode,)).fetchone()
        return None if row is None else _loads(row[0])

    def earth_base(self, item_id: str) -> InventoryItem:
        raise NotImplementedError

    def list_locations(self) -> list[StorageLocation]:
        raise NotImplementedError

    def get_user(self, user_id: str) -> User:
        raise NotImplementedError

    def get_encrypted_private_key(self, user_id: str) -> bytes:
        raise NotImplementedError

    def get_active_alert(self, item_id: str) -> Optional[SupplyAlert]:
        raise NotImplementedError

    def list_active_alerts(self) -> list[SupplyAlert]:
        raise NotImplementedError

    def get_mission(self, mission_id: str) -> ResupplyMission:
        raise NotImplementedError

    def list_missions(self) -> list[ResupplyMission]:
        raise NotImplementedError

    def get_manifest(self, mission_id: str, version: Optional[int] = None) -> ManifestDraft:
        raise NotImplementedError

    def list_discrepancies(self, mission_id: str) -> list[Discrepancy]:
        raise NotImplementedError

    def item_history(self, item_id: str) -> list[InventoryUpdate]:
        raise NotImplementedError

    def recent_events(self, since: datetime) -> list[ActivityEvent]:
        raise NotImplementedError

    def sendable_after(self, sequence: int, limit: int) -> list[SendableUnit]:
        raise NotImplementedError

    def pending_page(self, offset: int, limit: int) -> list[SendableUnit]:
        raise NotImplementedError

    def pending_count(self) -> int:
        placeholders = ",".join("?" for _ in _PENDING_STATUSES)
        row = self._conn.execute(
            f"SELECT COUNT(*) FROM updates WHERE sync_status IN ({placeholders})",
            _PENDING_STATUSES).fetchone()
        return int(row[0])

    def rejected_since(self, since: datetime) -> list[SendableUnit]:
        raise NotImplementedError

    def open_conflicts(self) -> list[ConflictRecord]:
        raise NotImplementedError

    def pull_cursor(self) -> int:
        raise NotImplementedError

    def last_full_sync(self) -> Optional[datetime]:
        raise NotImplementedError


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

    def append_update(self, update: InventoryUpdate) -> InventoryUpdate:
        key = str(update.update_id)
        if self._conn.execute("SELECT 1 FROM updates WHERE update_id = ?", (key,)).fetchone():
            raise ValueError(f"update {key} already exists")
        sequence = self._take_sequence()
        stored = dataclasses.replace(
            update, sequence=sequence, display_id=f"{STATION_DISPLAY_PREFIX}{sequence}")
        self._conn.execute(
            "INSERT INTO updates (update_id, sequence, item_id, sync_status, rejected_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key, sequence, stored.item_id, stored.sync_status.value,
             _iso(stored.rejected_at), _dumps(stored)))
        return stored

    def append_receipt(self, receipt: ReceiptUnit) -> ReceiptUnit:
        raise NotImplementedError

    def set_sync_status(self, key: UUID, status: SyncStatus,
                        rejected_at: Optional[datetime] = None) -> None:
        cursor = self._conn.execute(
            "UPDATE updates SET sync_status = ?, rejected_at = ? WHERE update_id = ?",
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

    def put_mission(self, mission: ResupplyMission) -> None:
        self._conn.execute(
            "INSERT INTO missions (mission_id, data) VALUES (?, ?) "
            "ON CONFLICT (mission_id) DO UPDATE SET data = excluded.data",
            (mission.mission_id, _dumps(mission)))

    def append_status_history(self, mission_id: str, entry: StatusHistoryEntry) -> None:
        raise NotImplementedError

    def append_discrepancy(self, discrepancy: Discrepancy) -> None:
        raise NotImplementedError

    def set_pull_cursor(self, cursor: int) -> None:
        raise NotImplementedError

    def record_full_sync(self, at: datetime) -> None:
        raise NotImplementedError

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
