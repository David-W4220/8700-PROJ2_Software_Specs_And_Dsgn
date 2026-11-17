"""Earth Store: durable Earth state with atomic transactions, a synchronous
replica and point-in-time backups (NFR-001, NFR-006, NFR-008, K5, K18, K19)."""
from __future__ import annotations

import dataclasses
import sqlite3
import threading
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterator, Optional
from uuid import UUID

from ssir.domain_rules import (
    _describe_alert, _describe_discrepancy, _describe_mission_status,
    _describe_update, _dumps, _loads,
)
from ssir.domain_rules import (
    ActivityEvent, ActivityKind, ChangeBatch, ConflictRecord, Discrepancy,
    DiscrepancyStatus, FieldChange, NotFound, InventoryItem, InventoryUpdate, LoadingIssue,
    ManifestDraft, Outcome, ResupplyMission, StatusHistoryEntry, StorageLocation,
    SupplyAlert, SyncStatus,
)

# Decision (Nov 16, 2026): Earth-made updates are numbered from 101 and shown
# as "E" + sequence (E101, E102, ...), like station updates (U101...).
FIRST_EARTH_SEQUENCE = 101
EARTH_DISPLAY_PREFIX = "E"

# Decision (Nov 16, 2026): the backend is SQLite ("sqlite:///<path>" or
# "sqlite:///:memory:"). K5's synchronous replica is not provided by SQLite
# and stays open (plan.md).
_SQLITE_PREFIX = "sqlite:///"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS locations (
    location_id TEXT PRIMARY KEY,
    data        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    data    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS barcodes (
    barcode TEXT PRIMARY KEY,
    item_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS barcodes_item ON barcodes (item_id);
-- Insert-only history (K18): only sync_status may change.
CREATE TABLE IF NOT EXISTS updates (
    commit_order INTEGER PRIMARY KEY AUTOINCREMENT,
    update_id    TEXT NOT NULL UNIQUE,
    item_id      TEXT NOT NULL,
    event_time   TEXT NOT NULL,
    sync_status  TEXT NOT NULL,
    data         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS updates_item ON updates (item_id, commit_order);
CREATE INDEX IF NOT EXISTS updates_event_time ON updates (event_time);
CREATE TRIGGER IF NOT EXISTS updates_no_delete BEFORE DELETE ON updates
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS updates_only_status_changes
    BEFORE UPDATE OF commit_order, update_id, item_id, event_time, data ON updates
    BEGIN SELECT RAISE(ABORT, 'only syncStatus may change'); END;
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    data       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS status_history (
    row_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL,
    time       TEXT NOT NULL,
    data       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS status_history_mission ON status_history (mission_id, row_id);
CREATE TRIGGER IF NOT EXISTS status_history_no_delete BEFORE DELETE ON status_history
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS status_history_no_update BEFORE UPDATE ON status_history
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
-- A discrepancy's resolution is a new row (NFR-006). recorded_at is the
-- time the row was written (decision Nov 16, 2026).
CREATE TABLE IF NOT EXISTS discrepancies (
    row_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    discrepancy_id TEXT NOT NULL,
    mission_id     TEXT NOT NULL,
    status         TEXT NOT NULL,
    recorded_at    TEXT NOT NULL,
    data           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS discrepancies_id ON discrepancies (discrepancy_id, row_id);
CREATE TRIGGER IF NOT EXISTS discrepancies_no_delete BEFORE DELETE ON discrepancies
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS discrepancies_no_update BEFORE UPDATE ON discrepancies
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
-- Source of every Earth-side field change (FR-030, Further decisions).
CREATE TABLE IF NOT EXISTS field_changes (
    row_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id   TEXT NOT NULL,
    field     TEXT NOT NULL,
    version   INTEGER NOT NULL,
    data      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS field_changes_item ON field_changes (item_id, version);
-- Manifest versions are insert-only; earlier versions stay read-only (CargoManifest).
CREATE TABLE IF NOT EXISTS manifests (
    mission_id TEXT NOT NULL,
    version    INTEGER NOT NULL,
    data       TEXT NOT NULL,
    PRIMARY KEY (mission_id, version)
);
CREATE TRIGGER IF NOT EXISTS manifests_no_delete BEFORE DELETE ON manifests
    BEGIN SELECT RAISE(ABORT, 'manifest versions are read-only'); END;
CREATE TRIGGER IF NOT EXISTS manifests_no_update BEFORE UPDATE ON manifests
    BEGIN SELECT RAISE(ABORT, 'manifest versions are read-only'); END;
-- Loaded quantities of the current version (FR-022); cleared on reopen (FR-020).
CREATE TABLE IF NOT EXISTS loaded_quantities (
    mission_id TEXT NOT NULL,
    item_id    TEXT NOT NULL,
    quantity   TEXT NOT NULL,
    PRIMARY KEY (mission_id, item_id)
);
-- Loading issues are insert-only and kept on reopen (LoadingIssue, NFR-006).
CREATE TABLE IF NOT EXISTS loading_issues (
    row_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL,
    data       TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS loading_issues_no_delete BEFORE DELETE ON loading_issues
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
CREATE TRIGGER IF NOT EXISTS loading_issues_no_update BEFORE UPDATE ON loading_issues
    BEGIN SELECT RAISE(ABORT, 'history is insert-only'); END;
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    item_id  TEXT NOT NULL,
    status   TEXT NOT NULL,
    data     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS alerts_one_active ON alerts (item_id) WHERE status = 'Active';
"""


def _update_row(sync_status: str, data: str) -> InventoryUpdate:
    return dataclasses.replace(_loads(data), sync_status=SyncStatus(sync_status))


def _utc_text(moment: datetime) -> str:
    """Sortable UTC text for time columns."""
    return moment.astimezone(timezone.utc).isoformat()


class EarthTx:
    """One atomic Earth Store transaction; reads may lock rows for conditional writes."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- private helpers --------------------------------------------------

    def _meta(self, key: str, default: str) -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return default if row is None else row[0]

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))

    def _item_or_none(self, item_id: Optional[str]) -> Optional[InventoryItem]:
        if item_id is None:
            return None
        row = self._conn.execute("SELECT data FROM items WHERE item_id = ?", (item_id,)).fetchone()
        return None if row is None else _loads(row[0])

    # items and locations
    def get_item(self, item_id: str, for_update: bool = False) -> InventoryItem:
        # Every Earth transaction already holds the write lock (BEGIN IMMEDIATE),
        # so for_update needs no extra locking on this backend.
        item = self._item_or_none(item_id)
        if item is None:
            raise NotFound([f"no item {item_id}"])
        return item

    def list_items(self) -> list[InventoryItem]:
        return [_loads(data) for (data,) in
                self._conn.execute("SELECT data FROM items ORDER BY item_id")]

    def put_item(self, item: InventoryItem) -> InventoryItem:
        if item.quantity < 0:
            raise ValueError(f"{item.item_id}: quantity must be at least 0")
        row = self._conn.execute(
            "SELECT version FROM items WHERE item_id = ?", (item.item_id,)).fetchone()
        stored = dataclasses.replace(item, record_version=1 if row is None else row[0] + 1)
        self._conn.execute(
            "INSERT INTO items (item_id, version, data) VALUES (?, ?, ?) "
            "ON CONFLICT (item_id) DO UPDATE SET version = excluded.version, data = excluded.data",
            (stored.item_id, stored.record_version, _dumps(stored)))
        self._conn.execute("DELETE FROM barcodes WHERE item_id = ?", (stored.item_id,))
        try:
            self._conn.executemany(
                "INSERT INTO barcodes (barcode, item_id) VALUES (?, ?)",
                [(code, stored.item_id) for code in stored.barcodes])
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"{stored.item_id}: barcode already used by another item") from exc
        return stored

    def list_locations(self) -> list[StorageLocation]:
        return [_loads(data) for (data,) in
                self._conn.execute("SELECT data FROM locations ORDER BY location_id")]

    def put_location(self, location: StorageLocation) -> None:
        try:
            self._conn.execute("INSERT INTO locations (location_id, data) VALUES (?, ?)",
                               (location.location_id, _dumps(location)))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"location {location.location_id} already exists") from exc

    def append_field_change(self, change: FieldChange) -> None:
        self._conn.execute(
            "INSERT INTO field_changes (item_id, field, version, data) VALUES (?, ?, ?, ?)",
            (change.item_id, change.field.value, change.version, _dumps(change)))

    def field_changes_since(self, item_id: str, version: int) -> list[FieldChange]:
        raise NotImplementedError

    # updates, outcomes, conflicts
    def append_update(self, update: InventoryUpdate) -> InventoryUpdate:
        key = str(update.update_id)
        if self._conn.execute("SELECT 1 FROM updates WHERE update_id = ?", (key,)).fetchone():
            raise ValueError(f"update {key} already exists")
        stored = update
        if update.display_id == "":
            # Decision (Nov 16, 2026): an update with no display ID was made on
            # Earth; station updates arrive with their U... ID and keep it.
            sequence = int(self._meta("next_earth_sequence", str(FIRST_EARTH_SEQUENCE)))
            self._set_meta("next_earth_sequence", str(sequence + 1))
            stored = dataclasses.replace(update, display_id=f"{EARTH_DISPLAY_PREFIX}{sequence}")
        self._conn.execute(
            "INSERT INTO updates (update_id, item_id, event_time, sync_status, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, stored.item_id, _utc_text(stored.event_time),
             stored.sync_status.value, _dumps(stored)))
        return stored

    def get_update(self, update_id: UUID) -> InventoryUpdate:
        raise NotImplementedError

    def set_sync_status(self, update_id: UUID, status: SyncStatus) -> None:
        raise NotImplementedError

    def item_history(self, item_id: str) -> list[InventoryUpdate]:
        rows = self._conn.execute(
            "SELECT sync_status, data FROM updates WHERE item_id = ? ORDER BY commit_order",
            (item_id,))
        return [_update_row(*row) for row in rows]

    def get_outcome(self, key: UUID) -> Optional[tuple[bytes, Outcome]]:
        raise NotImplementedError

    def put_outcome(self, key: UUID, content_hash: bytes, outcome: Outcome) -> None:
        raise NotImplementedError

    def get_conflict(self, update_id: UUID, for_update: bool = False) -> ConflictRecord:
        raise NotImplementedError

    def list_open_conflicts(self) -> list[ConflictRecord]:
        raise NotImplementedError

    def append_conflict(self, conflict: ConflictRecord) -> None:
        raise NotImplementedError

    def append_resolution(self, conflict: ConflictRecord) -> None:
        raise NotImplementedError

    # alerts and activity
    def get_active_alert(self, item_id: str) -> Optional[SupplyAlert]:
        row = self._conn.execute(
            "SELECT data FROM alerts WHERE item_id = ? AND status = 'Active'", (item_id,)).fetchone()
        return None if row is None else _loads(row[0])

    def list_active_alerts(self) -> list[SupplyAlert]:
        return [_loads(data) for (data,) in self._conn.execute(
            "SELECT data FROM alerts WHERE status = 'Active' ORDER BY alert_id")]

    def put_alert(self, alert: SupplyAlert) -> None:
        try:
            self._conn.execute(
                "INSERT INTO alerts (alert_id, item_id, status, data) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (alert_id) DO UPDATE SET item_id = excluded.item_id, "
                "status = excluded.status, data = excluded.data",
                (alert.alert_id, alert.item_id, alert.alert_status.value, _dumps(alert)))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"{alert.item_id} already has an Active alert") from exc

    def recent_events(self, since: datetime) -> list[ActivityEvent]:
        events: list[ActivityEvent] = []
        for (data,) in self._conn.execute(
                "SELECT data FROM updates WHERE event_time >= ? ORDER BY commit_order",
                (_utc_text(since),)):
            update: InventoryUpdate = _loads(data)
            events.append(ActivityEvent(update.event_time, ActivityKind.INVENTORY_UPDATE,
                                        _describe_update(update, self._item_or_none(update.item_id))))
        for mission_id, data in self._conn.execute(
                "SELECT mission_id, data FROM status_history WHERE time >= ? ORDER BY row_id",
                (_utc_text(since),)):
            entry: StatusHistoryEntry = _loads(data)
            events.append(ActivityEvent(entry.time, ActivityKind.MISSION_STATUS,
                                        _describe_mission_status(mission_id, entry)))
        for recorded_at, data in self._conn.execute(
                "SELECT recorded_at, data FROM discrepancies WHERE recorded_at >= ? ORDER BY row_id",
                (_utc_text(since),)):
            discrepancy: Discrepancy = _loads(data)
            kind = (ActivityKind.DISCREPANCY_RESOLVED
                    if discrepancy.status is DiscrepancyStatus.RESOLVED
                    else ActivityKind.DISCREPANCY_RECORDED)
            events.append(ActivityEvent(
                datetime.fromisoformat(recorded_at), kind,
                _describe_discrepancy(discrepancy, self._item_or_none(discrepancy.item_id))))
        for (data,) in self._conn.execute("SELECT data FROM alerts"):
            alert: SupplyAlert = _loads(data)
            item = self._item_or_none(alert.item_id)
            if alert.raised_at >= since:
                events.append(ActivityEvent(alert.raised_at, ActivityKind.ALERT_RAISED,
                                            _describe_alert(item, alert.item_id, raised=True)))
            if alert.resolved_at is not None and alert.resolved_at >= since:
                events.append(ActivityEvent(alert.resolved_at, ActivityKind.ALERT_RESOLVED,
                                            _describe_alert(item, alert.item_id, raised=False)))
        events.sort(key=lambda event: event.time)
        return events

    # missions
    def next_mission_id(self) -> str:
        # Decision (Nov 16, 2026): mission IDs start at R1 ("R1, R2…").
        number = int(self._meta("next_mission_number", "1"))
        self._set_meta("next_mission_number", str(number + 1))
        return f"R{number}"

    def get_mission(self, mission_id: str, for_update: bool = False) -> ResupplyMission:
        return self._mission_with_history(mission_id)

    def list_missions(self) -> list[ResupplyMission]:
        ids = [mid for (mid,) in self._conn.execute("SELECT mission_id FROM missions ORDER BY mission_id")]
        return [self._mission_with_history(mid) for mid in ids]

    def _mission_with_history(self, mission_id: str) -> ResupplyMission:
        row = self._conn.execute("SELECT data FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
        if row is None:
            raise NotFound([f"no mission {mission_id}"])
        history = tuple(_loads(data) for (data,) in self._conn.execute(
            "SELECT data FROM status_history WHERE mission_id = ? ORDER BY row_id", (mission_id,)))
        return dataclasses.replace(_loads(row[0]), status_history=history)

    def put_mission(self, mission: ResupplyMission) -> None:
        # Status history is insert-only (NFR-006): entries beyond those already
        # stored are appended; stored entries are never rewritten or removed.
        stored = self._conn.execute(
            "SELECT COUNT(*) FROM status_history WHERE mission_id = ?",
            (mission.mission_id,)).fetchone()[0]
        for entry in mission.status_history[stored:]:
            self.append_status_history(mission.mission_id, entry)
        self._conn.execute(
            "INSERT INTO missions (mission_id, data) VALUES (?, ?) "
            "ON CONFLICT (mission_id) DO UPDATE SET data = excluded.data",
            (mission.mission_id, _dumps(dataclasses.replace(mission, status_history=()))))

    def get_manifest(self, mission_id: str, version: Optional[int] = None) -> ManifestDraft:
        if version is None:
            row = self._conn.execute(
                "SELECT data FROM manifests WHERE mission_id = ? ORDER BY version DESC LIMIT 1",
                (mission_id,)).fetchone()
        else:
            row = self._conn.execute(
                "SELECT data FROM manifests WHERE mission_id = ? AND version = ?",
                (mission_id, version)).fetchone()
        if row is None:
            raise NotFound([f"no manifest for {mission_id}" + ("" if version is None else f" version {version}")])
        draft: ManifestDraft = _loads(row[0])
        if version is not None:
            return draft                       # earlier versions exactly as saved
        loaded = dict(self._conn.execute(
            "SELECT item_id, quantity FROM loaded_quantities WHERE mission_id = ?", (mission_id,)))
        return dataclasses.replace(draft, lines=tuple(
            dataclasses.replace(line, loaded_quantity=Decimal(loaded[line.item_id]))
            if line.item_id in loaded else line for line in draft.lines))

    def set_loaded_quantity(self, mission_id: str, item_id: str, quantity: Decimal) -> None:
        """Addition (Nov 16, 2026, not in contracts.md): loaded quantity of a line
        of the current version; not part of any manifest version."""
        self._conn.execute(
            "INSERT INTO loaded_quantities (mission_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT (mission_id, item_id) DO UPDATE SET quantity = excluded.quantity",
            (mission_id, item_id, str(quantity)))

    def clear_loaded_quantities(self, mission_id: str) -> None:
        """Addition (Nov 16, 2026, not in contracts.md): reopen clears loading (FR-020)."""
        self._conn.execute("DELETE FROM loaded_quantities WHERE mission_id = ?", (mission_id,))

    def append_manifest_version(self, mission_id: str, version: int,
                                draft: ManifestDraft) -> None:
        try:
            self._conn.execute("INSERT INTO manifests (mission_id, version, data) VALUES (?, ?, ?)",
                               (mission_id, version, _dumps(draft)))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"{mission_id} manifest version {version} already exists") from exc

    def append_status_history(self, mission_id: str, entry: StatusHistoryEntry) -> None:
        self._conn.execute(
            "INSERT INTO status_history (mission_id, time, data) VALUES (?, ?, ?)",
            (mission_id, _utc_text(entry.time), _dumps(entry)))

    def append_loading_issue(self, issue: LoadingIssue) -> None:
        self._conn.execute("INSERT INTO loading_issues (mission_id, data) VALUES (?, ?)",
                           (issue.mission_id, _dumps(issue)))

    def list_loading_issues(self, mission_id: str) -> list[LoadingIssue]:
        return [_loads(data) for (data,) in self._conn.execute(
            "SELECT data FROM loading_issues WHERE mission_id = ? ORDER BY row_id", (mission_id,))]

    def append_discrepancy(self, discrepancy: Discrepancy) -> None:
        # Decision (Nov 16, 2026): the row is stamped with the UTC time it is written.
        self._conn.execute(
            "INSERT INTO discrepancies (discrepancy_id, mission_id, status, recorded_at, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (discrepancy.discrepancy_id, discrepancy.mission_id, discrepancy.status.value,
             _utc_text(datetime.now(timezone.utc)), _dumps(discrepancy)))

    def get_discrepancy(self, discrepancy_id: str, for_update: bool = False) -> Discrepancy:
        raise NotImplementedError

    def list_discrepancies(self, mission_id: str) -> list[Discrepancy]:
        raise NotImplementedError

    # sync bookkeeping
    def committed_station_sequence(self) -> int:
        return int(self._meta("committed_station_sequence", "0"))

    def set_committed_station_sequence(self, sequence: int) -> None:
        raise NotImplementedError

    def record_station_contact(self, at: datetime) -> None:
        self._set_meta("last_station_contact", at.isoformat())

    def last_station_contact(self) -> Optional[datetime]:
        value = self._meta("last_station_contact", "")
        return datetime.fromisoformat(value) if value else None

    def set_reported_pending_count(self, count: int) -> None:
        self._set_meta("reported_pending_count", str(count))

    def reported_pending_count(self) -> int:
        return int(self._meta("reported_pending_count", "0"))

    def set_session_open(self, is_open: bool) -> None:
        self._set_meta("session_open", "1" if is_open else "0")

    def session_open(self) -> bool:
        return self._meta("session_open", "0") == "1"

    def record_full_sync(self, at: datetime) -> None:
        self._set_meta("last_full_sync", at.isoformat())

    def last_full_sync(self) -> Optional[datetime]:
        value = self._meta("last_full_sync", "")
        return datetime.fromisoformat(value) if value else None

    def change_feed(self, after_cursor: int, before: datetime, limit: int) -> ChangeBatch:
        raise NotImplementedError


class EarthStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    def open(self) -> None:
        if not self._dsn.startswith(_SQLITE_PREFIX):
            raise ConnectionError(f"unsupported Earth Store DSN: {self._dsn}")
        target = self._dsn[len(_SQLITE_PREFIX):]
        try:
            conn = sqlite3.connect(target, timeout=30, isolation_level=None,
                                   check_same_thread=False)
            conn.execute("PRAGMA synchronous = FULL")
            if target != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA)
        except sqlite3.Error as exc:
            raise ConnectionError(f"cannot open Earth Store: {exc}") from exc
        self._conn = conn

    def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass

    def transaction(self) -> AbstractContextManager[EarthTx]:
        if self._conn is None:
            raise ConnectionError("Earth Store is not open")
        return self._transaction(self._conn)

    @contextmanager
    def _transaction(self, conn: sqlite3.Connection) -> Iterator[EarthTx]:
        # One connection, one transaction at a time: every Earth write is
        # serialized, so conditional writes see the current state (NFR-001).
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield EarthTx(conn)
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
